"""A sync project: a sequence (from XML) or loose footage, its clips, and what the engine found.

Used by the window, the Premiere bridge and the command line alike.
"""

import base64
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from . import engine, media, xmeml

ENV_RATE = 10            # waveform points per second sent to the UI
ENV_MAX = 24000          # cap per clip


def _prefix(name):
    """Camera-ish prefix of a file name: A001C002.mov -> A, ZOOM0003.WAV -> ZOOM, GX010045 -> GX."""
    base = os.path.splitext(os.path.basename(name))[0]
    m = re.match(r"^([A-Za-z]+[_\-]?)", base)
    if m:
        return m.group(1).rstrip("_-").upper()[:8]
    return "#"


def group_key(path, bin_name=None):
    if bin_name:
        return bin_name
    folder = os.path.basename(os.path.dirname(os.path.abspath(path))) if path else ""
    return "%s/%s" % (folder, _prefix(path or ""))


class Project(object):
    def __init__(self, name, kind):
        self.id = uuid.uuid4().hex[:12]
        self.name = name
        self.kind = kind              # "sequence" or "footage"
        self.src = None               # xmeml.Source for sequences
        self.xml_path = None
        self.files = {}               # fid -> xmeml.MediaFile
        self.clips = {}               # fid -> engine.Clip
        self.lanes = []               # [{"id", "label", "kind", "fids": [...]}]
        self.state = "ready"          # loading, ready, analyzing, review, failed
        self.stage = ""
        self.progress = 0.0
        self.error = None
        self.overall = 0.0
        self.components = []
        self.nudge = {}               # fid -> seconds added by hand
        self.excluded = set()         # fids the user took out of the sync
        self.forced = set()           # fids the user marked as checked (counts as synced)
        self.output = None            # last exported XML path
        self.created = time.time()
        self.notes = []
        self._cancel = False
        self._lock = threading.Lock()

    # ---- loading ------------------------------------------------------------------
    @classmethod
    def from_xml(cls, path=None, text=None, base_dir=None, sequence_name=None):
        src = xmeml.read(path, text=text, base_dir=base_dir, sequence_name=sequence_name)
        p = cls(src.name, "sequence" if src.seq is not None else "footage")
        p.src = src
        p.xml_path = path
        p.files = dict(src.files)
        if src.dropped:
            p.notes.append("%d transition%s or title%s left out" % (src.dropped, "" if src.dropped == 1 else "s",
                                                                     "" if src.dropped == 1 else "s"))
        if src.seq is not None:
            for kind, count in (("video", src.video_tracks), ("audio", src.audio_tracks)):
                for n in range(1, count + 1):
                    items = sorted((it for it in src.items if it.kind == kind and it.track_no == n), key=lambda i: i.start)
                    fids = []
                    for it in items:
                        if it.fid not in fids:
                            fids.append(it.fid)
                    label = ("V%d" if kind == "video" else "A%d") % n
                    p.lanes.append({"id": label, "label": label, "kind": kind, "fids": fids,
                                    "name": _lane_name([p.files[f] for f in fids])})
        else:
            p._lanes_from_groups({fid: group_key(f.path, f.bin) for fid, f in p.files.items()})
        p._make_clips()
        return p

    @classmethod
    def from_media(cls, items, name=None, probe=True):
        """items: [{"path", "name"?, "bin"?}] or plain paths."""
        norm = []
        for it in items:
            if isinstance(it, str):
                norm.append({"path": it})
            else:
                norm.append(dict(it))
        p = cls(name or _footage_name([i["path"] for i in norm]), "footage")
        groups = {}
        infos = {}
        if probe:
            def pr(it):
                try:
                    return it["path"], media.probe(it["path"]), None
                except media.MediaError as e:
                    return it["path"], None, str(e)
            with ThreadPoolExecutor(6) as ex:
                for path, info, err in ex.map(pr, norm):
                    infos[path] = (info, err)
        for k, it in enumerate(norm, 1):
            fid = "file-%d" % k
            info, err = infos.get(it["path"], (None, None))
            if info:
                mf = xmeml.media_file_from_probe(fid, info)
            else:
                mf = xmeml.MediaFile(fid, it["path"], it.get("name") or os.path.basename(it["path"]))
                mf.channels = 1
                mf._seconds = 0.0
                mf._error = err or "Couldn't read this file"
            if it.get("name"):
                mf.name = it["name"]
            mf.bin = it.get("bin")
            p.files[fid] = mf
            groups[fid] = group_key(it["path"], it.get("bin"))
        p._lanes_from_groups(groups)
        p._make_clips()
        for fid, mf in p.files.items():
            if getattr(mf, "_error", None):
                p.clips[fid].error = mf._error
                p.clips[fid].status = "offline" if not os.path.exists(mf.path or "") else "unsynced"
        return p

    def _lanes_from_groups(self, groups):
        order = []
        for fid in self.files:
            g = groups[fid]
            if g not in order:
                order.append(g)
        # short labels: drop the folder part when the prefixes alone tell groups apart
        prefixes = [g.split("/")[-1] for g in order]
        folders = [g.split("/")[0] for g in order]
        for g in order:
            fids = [f for f in self.files if groups[f] == g]
            kind = "video" if any(self.files[f].has_video for f in fids) else "audio"
            folder, _, pre = g.rpartition("/")
            if len(set(prefixes)) == len(prefixes):
                label = pre if pre != "#" else (folder or "Clips")
            elif len(set(folders)) == len(folders):
                label = folder
            else:
                label = (folder + " · " + pre) if folder else pre
            self.lanes.append({"id": "L%d" % (len(self.lanes) + 1), "label": label, "kind": kind, "fids": fids,
                               "name": label})
        self._groups = groups

    def _make_clips(self):
        groups = getattr(self, "_groups", None)
        for fid, mf in self.files.items():
            if groups:
                g = groups[fid]
            else:
                # sequence: the track it sits on, split by camera-ish name so clips dumped on one
                # track from several cameras still get compared with each other
                g = "%s|%s" % (mf.track or "", group_key(mf.path))
            c = engine.Clip(fid, mf.path or "", mf.name, group=g, duration=mf.seconds, has_video=mf.has_video)
            if not mf.path or not os.path.isfile(mf.path):
                c.status = "offline"
                c.error = "Media not found"
            self.clips[fid] = c

    # ---- relinking -------------------------------------------------------------------
    def relink(self, folder):
        """Find offline media by file name under folder. Returns how many were found."""
        missing = {os.path.basename(f.path or f.name).lower(): fid for fid, f in self.files.items()
                   if self.clips[fid].status == "offline"}
        if not missing:
            return 0
        found = 0
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in files:
                fid = missing.pop(name.lower(), None)
                if fid:
                    path = os.path.join(root, name)
                    self.files[fid].path = path
                    c = self.clips[fid]
                    c.path, c.error, c.status, c.fp = path, None, "pending", None
                    found += 1
            if not missing:
                break
        return found

    # ---- analysis ------------------------------------------------------------------------
    def cancel(self):
        self._cancel = True

    def analyze(self, mode="fast", drift=True, on_progress=None, on_clip=None):
        """Run the engine. on_progress(project), on_clip(clip) as clips get read."""
        self._cancel = False
        self.state = "analyzing"
        self.error = None
        self.nudge = {}
        clips = [c for fid, c in self.clips.items() if fid not in self.excluded and c.status != "offline"]
        stages = {"read": (0.0, 0.55, "Listening"), "reading": (0.0, 0.55, "Listening"),
                  "match": (0.55, 0.9, "Matching"), "refine": (0.9, 0.95, "Fine-tuning"),
                  "solve": (0.95, 0.97, "Lining up"), "drift": (0.97, 1.0, "Checking clocks")}
        last = [0.0]

        def prog(stage, done, total, cid):
            a, b, label = stages.get(stage, (0, 1, stage))
            frac = (done / float(total)) if total else 1.0
            self.progress = round(a + (b - a) * frac, 4)
            if stage in ("read", "reading"):
                self.stage = "%s · %d / %d clips" % (label, done, total)
            elif stage == "match":
                self.stage = "%s · %d / %d pairs" % (label, done, total)
            else:
                self.stage = label
            if cid and on_clip and stage == "read":
                on_clip(self.clips.get(cid))
            if cid and on_clip and stage == "reading":
                on_clip(self.clips.get(cid), True)
            now = time.time()
            if on_progress and (now - last[0] > 0.08 or done == total):
                last[0] = now
                on_progress(self)

        try:
            res = engine.analyze(clips, mode=mode, drift=drift, progress=prog, cancel=lambda: self._cancel)
        except engine.Cancelled:
            self.state = "ready"
            self.stage = "Cancelled"
            for c in clips:
                if c.status not in ("offline",):
                    c.status = "pending"
            return None
        except Exception as e:  # pragma: no cover - surfaced to the UI
            self.state = "failed"
            self.error = str(e)
            raise
        self.overall = round(res.overall, 3)
        self.components = res.components
        for fid in self.excluded:
            self.clips[fid].status = "excluded"
        self.state = "review"
        self.progress = 1.0
        n = sum(1 for c in self.clips.values() if c.start is not None)
        self.stage = "Synced %d of %d clips" % (n, len(self.clips))
        return res

    # ---- results -------------------------------------------------------------------------
    def placement(self):
        """fid -> seconds on the output timeline (None = unsynced). Separate sync groups follow
        the main timeline with a gap, in order."""
        out = {fid: None for fid in self.clips}
        cursor = 0.0
        for k, comp in enumerate(self.components):
            if not comp:
                continue
            starts = [self.clips[f].start + self.nudge.get(f, 0.0) for f in comp]
            t0 = min(starts)
            end = 0.0
            for f in comp:
                c = self.clips[f]
                if f in self.excluded:
                    continue
                t = cursor + c.start + self.nudge.get(f, 0.0) - t0
                out[f] = t
                end = max(end, t + (c.duration or 0.0))
            cursor = end + xmeml.GAP_SECONDS
        return out

    def statuses(self):
        st, conf = {}, {}
        for fid, c in self.clips.items():
            s = c.status
            if fid in self.forced and s == "low":
                s = "synced"
            st[fid] = s
            conf[fid] = c.confidence
        return st, conf

    def set_nudge(self, fid, seconds):
        self.nudge[fid] = float(seconds)

    def set_excluded(self, fid, excluded):
        c = self.clips[fid]
        if excluded:
            self.excluded.add(fid)
            c.status = "excluded"
        else:
            self.excluded.discard(fid)
            c.status = "pending" if c.start is None and self.state != "review" else (
                "unsynced" if c.start is None else ("synced" if c.confidence >= engine.HIGH else "low"))

    def default_output(self, out_dir=None):
        base = re.sub(r'[\\/:*?"<>|]+', "-", self.name).strip() or "Synced"
        if out_dir is None:
            if self.xml_path:
                out_dir = os.path.dirname(os.path.abspath(self.xml_path))
            else:
                first = next((f.path for f in self.files.values() if f.path), None)
                out_dir = os.path.dirname(os.path.abspath(first)) if first else os.path.expanduser("~")
        path = os.path.join(out_dir, base + " (SYN).xml")
        k = 2
        while os.path.exists(path):
            path = os.path.join(out_dir, "%s (SYN %d).xml" % (base, k))
            k += 1
        return path

    def render(self, keep_camera_audio=True, mark_low=True, unsynced="end"):
        st, conf = self.statuses()
        pl = self.placement()
        if self.src is not None and self.src.seq is not None:
            return xmeml.write_synced(self.src, pl, st, conf, keep_camera_audio=keep_camera_audio,
                                      mark_low=mark_low, unsynced=unsynced)
        lanes = [(ln["label"], ln["fids"]) for ln in self.lanes]
        files = [self.files[f] for f in self.files if f not in self.excluded]
        return xmeml.build(files, lanes, pl, "%s (SYN)" % self.name, status=st, confidence=conf,
                           keep_camera_audio=keep_camera_audio, mark_low=mark_low, unsynced=unsynced)

    def export(self, path, **opts):
        text, info = self.render(**opts)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
        self.output = path
        info["path"] = path
        return info

    def report(self):
        """Confidence summary in the bridge contract's shape."""
        fps = self.fps
        pl = self.placement()
        clips = []
        st, conf = self.statuses()
        for fid, c in self.clips.items():
            t = pl.get(fid)
            clips.append({"id": fid, "name": c.name, "offsetFrames": int(round(t * fps)) if t is not None else None,
                          "confidence": round(conf[fid], 3),
                          "status": "synced" if st[fid] == "synced" else ("low" if st[fid] == "low" else "unsynced")})
        return {"overall": self.overall, "clips": clips}

    @property
    def fps(self):
        if self.src is not None and self.src.seq is not None:
            return self.src.fps
        vid = next((f for f in self.files.values() if f.has_video and f.rate), None)
        return xmeml.fps_of(vid.rate) if vid else 24000 / 1001.0

    # ---- for the window -------------------------------------------------------------------
    def clip_public(self, c, placement=None):
        mf = self.files.get(c.id)
        m = c.match
        other = self.clips.get(c.matched) if c.matched else None
        lanes = [ln["id"] for ln in self.lanes if c.id in ln["fids"]]
        pl_start = None
        if c.start is not None:
            pl_start = round(c.start + self.nudge.get(c.id, 0.0), 4)
        st = c.status
        if c.id in self.forced and st == "low":
            st = "synced"
        return {
            "id": c.id, "name": c.name, "path": c.path, "lanes": lanes, "duration": round(c.duration or 0.0, 3),
            "video": bool(mf and mf.has_video), "channels": mf.channels if mf else 0,
            "start": pl_start, "component": c.component, "status": st, "confidence": c.confidence,
            "error": c.error, "nudge": round(self.nudge.get(c.id, 0.0), 4), "forced": c.id in self.forced,
            "matched": other.name if other else None, "matched_id": c.matched,
            "z": round(m.z, 1) if m else None, "overlap": round(m.overlap, 1) if m else None,
            "agree": c.agree, "disagree": c.disagree, "curve": m.curve if m else None,
            "drift": c.drift_ppm, "orig": self._orig_start(c.id),
            "at": (placement or {}).get(c.id) if self.state == "review" else None,
        }

    def _orig_start(self, fid):
        """Where the clip sits in the source sequence (seconds), to animate from."""
        if self.src is None or self.src.seq is None:
            return None
        its = [it for it in self.src.items if it.fid == fid and it.start >= 0]
        if not its:
            return None
        it = min(its, key=lambda i: i.start)
        rate = it.rate or self.src.rate
        return round(it.start / self.src.fps - it.in_ / xmeml.fps_of(rate), 3)

    def env_b64(self, c):
        if c.env is None or not len(c.env):
            return None
        e = c.env
        step = max(1, int(round(20 / float(ENV_RATE))))
        if step > 1:
            n = len(e) // step * step
            e = e[:n].reshape(-1, step).max(axis=1) if n else e
        if len(e) > ENV_MAX:
            k = int(np.ceil(len(e) / float(ENV_MAX)))
            n = len(e) // k * k
            e = e[:n].reshape(-1, k).max(axis=1)
        return {"rate": len(e) / max(c.duration, 1e-6), "data": base64.b64encode(np.asarray(e, np.uint8).tobytes()).decode("ascii")}

    def public(self, with_env=False):
        pl = self.placement() if self.state == "review" else {}
        out = {
            "id": self.id, "name": self.name, "kind": self.kind, "state": self.state, "stage": self.stage,
            "progress": self.progress, "error": self.error, "overall": self.overall, "fps": round(self.fps, 5),
            "lanes": [{k: ln[k] for k in ("id", "label", "kind", "name")} for ln in self.lanes],
            "clips": [self.clip_public(c, pl) for c in self.clips.values()],
            "components": len(self.components), "notes": self.notes, "output": self.output,
            "xml": self.xml_path,
        }
        if with_env:
            out["env"] = {c.id: self.env_b64(c) for c in self.clips.values() if c.env is not None}
        return out


def _lane_name(files):
    """A readable name for a track from its clips: shared folder or name prefix."""
    if not files:
        return ""
    pres = {_prefix(f.name) for f in files}
    if len(pres) == 1 and "#" not in pres:
        return next(iter(pres))
    folders = {os.path.basename(os.path.dirname(f.path)) for f in files if f.path}
    if len(folders) == 1:
        return next(iter(folders))
    return ""


def _footage_name(paths):
    if not paths:
        return "Footage"
    folders = {os.path.dirname(os.path.abspath(p)) for p in paths}
    if len(folders) == 1:
        return os.path.basename(next(iter(folders))) or "Footage"
    common = os.path.commonpath(list(folders)) if len(folders) > 1 else ""
    return os.path.basename(common) or "Footage"
