"""Audio sync engine: finds where every clip sits in time from its sound alone.

How it works
1. Fingerprint. Each clip's sound (8 kHz mono) becomes an onset envelope at 100 frames
   a second: the rises in loudness across 14 frequency bands, log-compressed so a lav, a
   camera's scratch mic and a phone recording of the same moment look alike.
2. Match. Every pair of clips from different cameras/recorders is cross-correlated with
   an FFT. Each lag is scored as a z-score (normalised correlation x sqrt(overlap)), so a
   short accidental overlap can't beat a long real one. The peak's height against the
   noise floor and against the runner-up peak gives that match its confidence.
3. Refine. The best lag is refined on the raw 8 kHz audio (GCC-PHAT) to well under a frame.
4. Solve. Matches are joined strongest-first into one timeline (a maximum spanning tree).
   A match that would make two clips from the same camera overlap is rejected, since one
   camera can't record twice at once. Extra matches that agree add confidence; ones that
   disagree take it away. Positions are then settled by weighted least squares.
5. Drift (optional). Long overlaps are measured at both ends to catch recorders whose
   clocks run fast or slow.
"""

import math
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from . import media

FRATE = 100                  # fingerprint frames per second
HOP = media.RATE // FRATE    # 80 samples
WIN = 256
N_BANDS = 14
MIN_OVERLAP = 4.0            # seconds of shared sound needed to trust a match
AGREE_TOL = 0.06             # seconds: two matches "agree" if they place a clip within this
HIGH = 0.8                   # confidence at or above: synced
ACCEPT = {"fast": 0.35, "thorough": 0.25}


class Cancelled(Exception):
    pass


# ---- fingerprints -------------------------------------------------------------

def _band_edges():
    # 14 log-spaced bands from ~100 Hz to 3.9 kHz over the 129 bins of a 256-point FFT at 8 kHz.
    edges = np.unique(np.round(np.geomspace(3, 126, N_BANDS + 1)).astype(int))
    return edges


_EDGES = _band_edges()
_WINDOW = np.hanning(WIN).astype(np.float32)


def band_energies(pcm):
    """(frames, bands) power, one frame per 10 ms."""
    x = np.asarray(pcm, dtype=np.float32) / 32768.0
    n = 1 + (len(x) - WIN) // HOP if len(x) >= WIN else 0
    out = np.zeros((max(n, 0), len(_EDGES) - 1), dtype=np.float32)
    if n <= 0:
        return out
    step = 16384
    for s in range(0, n, step):
        e = min(n, s + step)
        idx = (np.arange(s, e) * HOP)[:, None] + np.arange(WIN)[None, :]
        frames = x[idx] * _WINDOW
        spec = np.abs(np.fft.rfft(frames, axis=1)).astype(np.float32) ** 2
        cs = np.concatenate([np.zeros((spec.shape[0], 1), np.float32), np.cumsum(spec, axis=1)], axis=1)
        out[s:e] = cs[:, _EDGES[1:]] - cs[:, _EDGES[:-1]]
    return out


def fingerprint(pcm):
    """Onset envelope: positive changes of log band energy, summed. float32, zero mean, unit variance."""
    E = band_energies(pcm)
    if len(E) < 2:
        return np.zeros(max(len(E), 1), np.float32)
    ref = np.percentile(E, 95, axis=0) + 1e-12
    L = np.log1p(100.0 * E / ref)
    flux = np.maximum(0.0, np.diff(L, axis=0)).sum(axis=1)
    flux = np.concatenate([[0.0], flux]).astype(np.float32)
    # Remove the slow trend (0.5 s moving average) so only the onsets correlate.
    k = 50
    if len(flux) > k:
        cs = np.concatenate([[0.0], np.cumsum(flux, dtype=np.float64)])
        ma = (cs[k:] - cs[:-k]) / k
        ma = np.concatenate([np.full(k // 2, ma[0]), ma, np.full(len(flux) - len(ma) - k // 2, ma[-1])])
        flux = flux - ma.astype(np.float32)
    sd = float(flux.std())
    if sd < 1e-9:
        return np.zeros_like(flux)
    return ((flux - flux.mean()) / sd).astype(np.float32)


def envelope(pcm, points_per_sec=20):
    """Peak waveform for drawing: uint8 0..255, points_per_sec values per second."""
    step = max(1, media.RATE // points_per_sec)
    n = len(pcm) // step
    if n == 0:
        return np.zeros(0, np.uint8)
    a = np.abs(np.asarray(pcm[: n * step], dtype=np.int32)).reshape(n, step).max(axis=1).astype(np.float32)
    top = float(np.percentile(a, 99.5)) or 1.0
    # Square-root scale so quiet speech is still visible next to loud hits.
    return np.clip(np.sqrt(np.minimum(a / top, 1.0)) * 255.0, 0, 255).astype(np.uint8)


# ---- matching -----------------------------------------------------------------

def _nfft(n):
    return 1 << int(math.ceil(math.log2(max(2, n))))


class Match(object):
    __slots__ = ("offset", "z", "z2", "ncc", "overlap", "confidence", "curve")

    def __init__(self, offset, z, z2, ncc, overlap, confidence, curve):
        self.offset = offset          # seconds: start of b on a's clock
        self.z = z
        self.z2 = z2
        self.ncc = ncc
        self.overlap = overlap        # seconds
        self.confidence = confidence
        self.curve = curve            # list of floats: match strength around the peak, for the UI


def confidence(z, z2, overlap):
    """0..1 from the peak's z-score, the runner-up's and the overlap length.

    Unrelated clips peak around z 4.5-6 (the max of ~1e5 noise lags). Real matches run from
    ~9 for five seconds of speech through a noisy camera mic to 35+ for a clean minute. A runner-up
    close to the peak means the sound repeats (music, a metronome) and the match is ambiguous.
    """
    if z <= 0:
        return 0.0
    height = 1.0 / (1.0 + math.exp(-(z - 7.5) / 0.9))
    ratio = z2 / z if z > 0 else 1.0
    unique = 1.0 / (1.0 + math.exp((ratio - 0.72) / 0.06))
    short = min(1.0, overlap / 6.0) ** 0.5
    return max(0.0, min(1.0, height * unique * short))


def match(fa, fb, min_overlap=MIN_OVERLAP, window=None):
    """Best alignment of fingerprint fb against fa.

    window: optional (lo, hi) seconds; only offsets in it are considered.
    Returns a Match or None when they can't overlap by min_overlap.
    """
    A, B = len(fa), len(fb)
    minL = int(min(min_overlap * FRATE, 0.6 * min(A, B)))
    if minL < FRATE or A < FRATE or B < FRATE:
        return None
    n = _nfft(A + B)
    c = np.fft.irfft(np.fft.rfft(fa, n) * np.conj(np.fft.rfft(fb, n)), n)
    lags = np.arange(-(B - 1), A)
    cc = c[lags % n]
    csa = np.concatenate([[0.0], np.cumsum(fa.astype(np.float64) ** 2)])
    csb = np.concatenate([[0.0], np.cumsum(fb.astype(np.float64) ** 2)])
    sa, ea = np.maximum(0, lags), np.minimum(A, lags + B)
    sb, eb = np.maximum(0, -lags), np.minimum(B, A - lags)
    L = ea - sa
    Ea = csa[ea] - csa[sa]
    Eb = csb[eb] - csb[sb]
    valid = L >= minL
    if window is not None:
        valid &= (lags >= window[0] * FRATE) & (lags <= window[1] * FRATE)
    if valid.sum() < 3:
        return None
    ncc = np.zeros_like(cc)
    ncc[valid] = cc[valid] / np.sqrt(Ea[valid] * Eb[valid] + 1e-9)
    zz = np.zeros_like(cc)
    zz[valid] = ncc[valid] * np.sqrt(L[valid])
    v = zz[valid]
    med = float(np.median(v))
    mad = float(np.median(np.abs(v - med))) * 1.4826 or float(v.std()) or 1.0
    z = (zz - med) / mad
    z[~valid] = -np.inf
    i = int(np.argmax(z))
    z1 = float(z[i])
    # Runner-up: best peak more than 1 s away from the winner.
    guard = FRATE
    lo, hi = max(0, i - guard), min(len(z), i + guard + 1)
    z_other = np.concatenate([z[:lo], z[hi:]])
    z_other = z_other[np.isfinite(z_other)]
    z2 = float(z_other.max()) if len(z_other) else 0.0
    # Sub-frame peak by fitting a parabola through the three points around it.
    frac = 0.0
    if 0 < i < len(z) - 1 and np.isfinite(z[i - 1]) and np.isfinite(z[i + 1]):
        y0, y1, y2 = ncc[i - 1], ncc[i], ncc[i + 1]
        den = y0 - 2 * y1 + y2
        if den < 0:
            frac = float(max(-0.5, min(0.5, 0.5 * (y0 - y2) / den)))
    offset = (lags[i] + frac) / float(FRATE)
    overlap = L[i] / float(FRATE)
    # Strength around the peak (+-3 s) for the inspector's little graph.
    span = 3 * FRATE
    seg = z[max(0, i - span): i + span + 1]
    seg = np.where(np.isfinite(seg), seg, 0.0)
    if len(seg) > 120:
        k = int(math.ceil(len(seg) / 120.0))
        seg = seg[: len(seg) // k * k].reshape(-1, k).max(axis=1)
    curve = [round(float(x) / max(z1, 1e-6), 3) for x in seg]
    return Match(offset, z1, z2, float(ncc[i]), overlap, confidence(z1, max(z2, 0.0), overlap), curve)


def refine(pa, pb, offset, overlap_start, overlap_len, search=0.03):
    """Refine `offset` (seconds) on raw audio with GCC-PHAT. Returns the refined offset or the input.

    pa, pb: int16 arrays (or memmaps) at media.RATE. overlap_start: seconds on a's clock.
    """
    R = media.RATE
    seg = min(overlap_len, 20.0)
    if seg < 1.0:
        return offset
    t0 = overlap_start + (overlap_len - seg) / 2.0          # middle of the overlap, on a's clock
    b0 = int(round((t0 - offset) * R))
    nb = int(seg * R)
    m = int(search * R)
    a0 = int(round(t0 * R)) - m
    if b0 < 0 or a0 < 0 or b0 + nb > len(pb) or a0 + nb + 2 * m > len(pa):
        return offset
    xb = np.asarray(pb[b0:b0 + nb], dtype=np.float32)
    xa = np.asarray(pa[a0:a0 + nb + 2 * m], dtype=np.float32)
    if xb.std() < 1 or xa.std() < 1:
        return offset
    n = _nfft(len(xa) + len(xb))
    X = np.fft.rfft(xa, n) * np.conj(np.fft.rfft(xb, n))
    X /= np.abs(X) + 1e-9
    c = np.fft.irfft(X, n)[: 2 * m + 1]   # lags 0..2m: xb sits at xa[lag]
    k = int(np.argmax(c))
    frac = 0.0
    if 0 < k < len(c) - 1:
        den = c[k - 1] - 2 * c[k] + c[k + 1]
        if den < 0:
            frac = 0.5 * (c[k - 1] - c[k + 1]) / den
    # Weak or edge-of-window peaks mean PHAT found nothing better than the fingerprints.
    if k in (0, 2 * m) or c[k] < 4 * float(np.median(np.abs(c))) + 1e-9:
        return offset
    new_b_on_a = (a0 + k + frac) / R          # where b0 sits on a's clock
    refined = new_b_on_a - b0 / float(R)
    if abs(refined - offset) > search:
        return offset
    return float(refined)


# ---- clips and the whole job -------------------------------------------------------

class Clip(object):
    """One piece of media to place. Everything the engine learns about it lands here."""

    def __init__(self, cid, path, name=None, group=None, duration=None, has_video=False):
        self.id = cid
        self.path = path
        self.name = name or os.path.basename(path)
        self.group = group or ""
        self.duration = duration or 0.0
        self.has_video = has_video
        self.error = None
        self.fp = None            # fingerprint
        self.env = None           # waveform for drawing
        self.pcm = None           # in memory only if the disk cache failed
        self.pcm_path = None
        # results
        self.start = None         # seconds on the synced timeline (None = not placed)
        self.component = None     # 0 = main timeline, 1.. = separate synced groups
        self.confidence = 0.0
        self.status = "pending"   # pending, synced, low, unsynced, offline
        self.matched = None       # id of the clip it was matched against
        self.match = None         # Match for that pair
        self.agree = 0            # other matches that agree
        self.disagree = 0
        self.drift_ppm = None

    def audio(self):
        if self.pcm is not None:
            return self.pcm
        if self.pcm_path and os.path.isfile(self.pcm_path):
            return np.memmap(self.pcm_path, dtype="<i2", mode="r")
        return None


def read_clip(clip, cancel=None):
    """Decode + fingerprint one clip (sets clip.fp / env / error)."""
    try:
        pcm = media.decode(clip.path, cancel=cancel)
    except media.MediaError as e:
        clip.error = str(e)
        return clip
    try:
        cp = os.path.join(media._cache_dir(), media.cache_key(clip.path) + ".s16")
        clip.pcm_path = cp if os.path.isfile(cp) else None
    except OSError:
        clip.pcm_path = None
    if not clip.pcm_path:
        clip.pcm = pcm
    clip.fp = fingerprint(pcm)
    clip.env = envelope(pcm)
    if not clip.duration:
        clip.duration = len(pcm) / float(media.RATE)
    if np.count_nonzero(np.abs(pcm) > 64) < media.RATE // 2:
        clip.error = "Silent: nothing to sync to"
    return clip


def _workers():
    return max(2, min(6, (os.cpu_count() or 2)))


class Result(object):
    def __init__(self, clips, components, overall, edges_tried, drift):
        self.clips = clips
        self.components = components    # list of lists of clip ids, main first
        self.overall = overall
        self.edges_tried = edges_tried
        self.drift = drift


def pairs_for(clips, mode):
    """Which pairs to compare. Clips from the same camera never overlap, so skip those pairs
    unless grouping is unknown (everything in one group) or the mode is thorough."""
    good = [c for c in clips if c.fp is not None and not c.error]
    groups = {c.group for c in good}
    use_groups = len(groups) > 1 and mode != "thorough"
    out = []
    for i in range(len(good)):
        for j in range(i + 1, len(good)):
            a, b = good[i], good[j]
            if use_groups and a.group == b.group:
                continue
            out.append((a, b))
    return out


def analyze(clips, mode="fast", drift=False, progress=None, cancel=None, read=True):
    """Place every clip. progress(stage, done, total, clip_id) is called as work happens."""
    prog = progress or (lambda *a: None)
    stop = cancel or (lambda: False)
    by_id = {c.id: c for c in clips}

    # 1. read + fingerprint
    if read:
        todo = [c for c in clips if c.fp is None and not c.error]
        done = [0]
        lock = threading.Lock()
        prog("read", 0, len(todo), None)

        def work(c):
            if stop():
                return c
            prog("reading", done[0], len(todo), c.id)
            read_clip(c, cancel=stop)
            with lock:
                done[0] += 1
            prog("read", done[0], len(todo), c.id)
            return c

        with ThreadPoolExecutor(_workers()) as ex:
            list(ex.map(work, todo))
    if stop():
        raise Cancelled()

    # 2. match pairs
    pairs = pairs_for(clips, mode)
    results = []
    lock = threading.Lock()
    done = [0]
    prog("match", 0, len(pairs), None)

    def compare(ab):
        if stop():
            return
        a, b = ab
        m = match(a.fp, b.fp)
        with lock:
            done[0] += 1
            if m is not None:
                results.append((a, b, m))
            n = done[0]
        if n == len(pairs) or n % max(1, len(pairs) // 200) == 0:
            prog("match", n, len(pairs), None)

    with ThreadPoolExecutor(_workers()) as ex:
        list(ex.map(compare, pairs))
    if stop():
        raise Cancelled()

    # 3. refine the strong ones on raw audio
    accept = ACCEPT.get(mode, ACCEPT["fast"])
    strong = [r for r in results if r[2].confidence >= accept]
    prog("refine", 0, len(strong), None)
    for k, (a, b, m) in enumerate(strong):
        if stop():
            raise Cancelled()
        pa, pb = a.audio(), b.audio()
        if pa is not None and pb is not None:
            ov_start = max(0.0, m.offset)
            m.offset = refine(pa, pb, m.offset, ov_start, m.overlap)
        if k % 10 == 0:
            prog("refine", k + 1, len(strong), None)

    # 4. solve
    prog("solve", 0, 1, None)
    comps = solve(clips, strong)
    prog("solve", 1, 1, None)

    # 5. drift
    drift_found = []
    if drift:
        tree = [(by_id[c.matched], c) for c in clips if c.matched is not None and c.matched in by_id]
        prog("drift", 0, len(tree), None)
        for k, (a, c) in enumerate(tree):
            if stop():
                raise Cancelled()
            ppm = measure_drift(a, c, c.start - a.start)
            if ppm is not None:
                c.drift_ppm = ppm
                if abs(ppm) >= 20:
                    drift_found.append(c.id)
            prog("drift", k + 1, len(tree), None)

    main = comps[0] if comps else []
    dur = sum(by_id[i].duration for i in main)
    overall = (sum(by_id[i].confidence * by_id[i].duration for i in main) / dur) if dur and len(main) > 1 else 0.0
    return Result(clips, comps, overall, len(pairs), drift_found)


def solve(clips, matches):
    """Join matches into timelines. Sets start / component / confidence / status on each clip.

    matches: [(clip_a, clip_b, Match)] where Match.offset = start_b - start_a.
    Returns the list of components (lists of clip ids), largest total duration first.
    """
    ok = [c for c in clips if c.fp is not None and not c.error]
    groups = {c.group for c in ok}
    check_groups = len(groups) > 1
    pos = {c.id: 0.0 for c in ok}
    members = {c.id: [c.id] for c in ok}
    root = {c.id: c.id for c in ok}
    by_id = {c.id: c for c in clips}
    for c in clips:
        c.start, c.component, c.matched, c.match, c.agree, c.disagree = None, None, None, None, 0, 0
        c.confidence = 0.0
    support = {c.id: [] for c in ok}
    conflict = {c.id: 0.0 for c in ok}
    tree = []

    def overlaps(ra, rb, shift):
        if not check_groups:
            return False
        for u in members[ra]:
            cu = by_id[u]
            for v in members[rb]:
                cv = by_id[v]
                if cu.group != cv.group:
                    continue
                s1, e1 = pos[u], pos[u] + cu.duration
                s2, e2 = pos[v] + shift, pos[v] + shift + cv.duration
                if min(e1, e2) - max(s1, s2) > max(1.0, 0.02 * min(cu.duration, cv.duration)):
                    return True
        return False

    for a, b, m in sorted(matches, key=lambda r: -r[2].confidence):
        ra, rb = root[a.id], root[b.id]
        if ra == rb:
            resid = (pos[a.id] + m.offset) - pos[b.id]
            if abs(resid) <= AGREE_TOL:
                support[a.id].append(m.confidence)
                support[b.id].append(m.confidence)
                tree.append((a.id, b.id, m, False))
            else:
                conflict[a.id] = max(conflict[a.id], m.confidence)
                conflict[b.id] = max(conflict[b.id], m.confidence)
            continue
        shift = pos[a.id] + m.offset - pos[b.id]
        if overlaps(ra, rb, shift):
            conflict[a.id] = max(conflict[a.id], m.confidence * 0.5)
            conflict[b.id] = max(conflict[b.id], m.confidence * 0.5)
            continue
        # merge the smaller component into the bigger one
        if len(members[ra]) < len(members[rb]):
            ra, rb, shift = rb, ra, -shift
            a, b = b, a
        for v in members[rb]:
            pos[v] += shift
            root[v] = ra
        members[ra].extend(members[rb])
        del members[rb]
        # the clip that joined gets this match as its explanation
        b.matched, b.match = a.id, m
        if a.match is None:
            a.matched, a.match = b.id, m
        support[a.id].append(m.confidence)
        support[b.id].append(m.confidence)
        tree.append((a.id, b.id, m, True))

    # Settle positions with weighted least squares over every agreeing match.
    for r, mem in members.items():
        if len(mem) < 3:
            continue
        idx = {cid: k for k, cid in enumerate(mem)}
        rows, rhs, w = [], [], []
        for a_id, b_id, m, _ in tree:
            if a_id in idx and b_id in idx:
                row = np.zeros(len(mem))
                row[idx[b_id]], row[idx[a_id]] = 1.0, -1.0
                # recompute the sign: tree entries may be swapped relative to the match
                off = pos[b_id] - pos[a_id]
                meas = m.offset if abs(off - m.offset) <= abs(off + m.offset) else -m.offset
                rows.append(row)
                rhs.append(meas)
                w.append(max(m.confidence, 0.05))
        if len(rows) >= len(mem):
            Aw = np.array(rows) * np.sqrt(w)[:, None]
            bw = np.array(rhs) * np.sqrt(w)
            anchor = np.zeros((1, len(mem)))
            anchor[0, 0] = 1.0
            sol, *_ = np.linalg.lstsq(np.vstack([Aw, anchor * 10]), np.concatenate([bw, [pos[mem[0]] * 10]]), rcond=None)
            if np.all(np.abs(sol - np.array([pos[c] for c in mem])) < AGREE_TOL * 2):
                for cid in mem:
                    pos[cid] = float(sol[idx[cid]])

    def comp_dur(mem):
        return sum(by_id[c].duration for c in mem)

    comps = sorted(members.values(), key=lambda mem: (-(len(mem) > 1), -comp_dur(mem)))
    out = []
    for k, mem in enumerate(comps):
        if len(mem) < 2:
            continue
        t0 = min(pos[c] for c in mem)
        for cid in mem:
            c = by_id[cid]
            c.start = pos[cid] - t0
            c.component = len(out)
            sup = support[cid]
            combined = 1.0 - float(np.prod([1.0 - s for s in sup])) if sup else 0.0
            combined = min(combined, 0.995)
            c.confidence = round(max(0.0, combined * (1.0 - 0.5 * conflict[cid])), 3)
            c.agree = max(0, len(sup) - 1)
            c.disagree = int(conflict[cid] > 0)
            c.status = "synced" if c.confidence >= HIGH else "low"
        out.append(sorted(mem, key=lambda cid: pos[cid]))
    for c in clips:
        if c.start is None:
            if c.status not in ("offline",):
                c.status = "unsynced"
            c.confidence = 0.0
    return out


def measure_drift(a, b, offset):
    """Clock drift of b against a in parts per million, or None if they overlap too little."""
    fa, fb = a.fp, b.fp
    if fa is None or fb is None:
        return None
    s = max(0.0, offset)
    e = min(a.duration, offset + b.duration)
    if e - s < 240:
        return None
    win = 60.0
    pts = []
    for t in (s + 5, e - 5 - win):
        ia, ib = int(t * FRATE), int((t - offset) * FRATE)
        nb = int(win * FRATE)
        m = int(1.0 * FRATE)
        if ib < 0 or ib + nb > len(fb) or ia - m < 0 or ia + nb + m > len(fa):
            return None
        seg_b = fb[ib:ib + nb]
        seg_a = fa[ia - m:ia + nb + m]
        r = match(seg_a, seg_b, min_overlap=win * 0.9)
        if r is None or r.z < 8:
            return None
        pts.append((t, (ia - m) / float(FRATE) + r.offset - ib / float(FRATE)))
    (t1, o1), (t2, o2) = pts
    return round((o2 - o1) / (t2 - t1) * 1e6, 1)
