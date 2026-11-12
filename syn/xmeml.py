"""Final Cut Pro 7 XML (xmeml): what Premiere Pro, DaVinci Resolve and FCP 7 import and export.

read(path) -> Source: the sequence (or the bin clips) and every media file it uses.
write_synced(source, placement, ...) -> the same sequence with each clip moved to its synced
time, as a new sequence "<name> (SYN)". The original sequence is never modified.
build(files, ...) -> a fresh sequence for loose footage (dropped files, Premiere bin selections).
"""

import copy
import os
import re
import sys
import urllib.parse
import uuid
import xml.etree.ElementTree as ET

LOW_LABEL = "Mango"       # Premiere label colours
UNSYNCED_LABEL = "Rose"
GAP_SECONDS = 5.0         # between separate sync groups / before unsynced clips


class XmlError(Exception):
    pass


# ---- rates ----------------------------------------------------------------------

def rate_of(el, default=None):
    """(timebase, ntsc) from a <rate> child."""
    r = el.find("rate") if el is not None else None
    if r is None:
        return default
    try:
        tb = int(float((r.findtext("timebase") or "0").strip()))
    except ValueError:
        return default
    if tb <= 0:
        return default
    return tb, (r.findtext("ntsc") or "").strip().upper() == "TRUE"


def fps_of(rate):
    tb, ntsc = rate
    return tb * 1000.0 / 1001.0 if ntsc else float(tb)


def rate_for_fps(fps):
    """Nearest editorial rate: 23.976 -> (24, True), 25 -> (25, False)..."""
    if not fps or fps <= 0:
        return 24, True
    for tb in (24, 30, 60, 48, 120):
        if abs(fps - tb * 1000 / 1001.0) < 0.02:
            return tb, True
    return int(round(fps)), False


def _rate_el(rate):
    r = ET.Element("rate")
    ET.SubElement(r, "timebase").text = str(rate[0])
    ET.SubElement(r, "ntsc").text = "TRUE" if rate[1] else "FALSE"
    return r


def _int(el, tag, default=0):
    try:
        return int(float((el.findtext(tag) or "").strip()))
    except (ValueError, AttributeError):
        return default


# ---- paths ------------------------------------------------------------------------

def path_from_url(url, base_dir=None):
    if not url:
        return None
    u = url.strip()
    if u.lower().startswith("file:"):
        rest = u[5:]
        if rest.startswith("//localhost"):
            rest = rest[len("//localhost"):]
        elif rest.startswith("///"):
            rest = rest[2:]
        elif rest.startswith("//"):
            # file://server/share -> UNC path
            rest = "//" + rest[2:] if os.name == "nt" else rest[1:]
        p = urllib.parse.unquote(rest)
    else:
        p = urllib.parse.unquote(u)
    if re.match(r"^/[A-Za-z]:[/\\]", p):
        p = p[1:]                         # /C:/Users -> C:/Users
    if os.name == "nt" and re.match(r"^[A-Za-z]:/", p):
        p = p.replace("/", "\\")
    if not os.path.isabs(p) and not re.match(r"^[A-Za-z]:", p) and base_dir:
        p = os.path.normpath(os.path.join(base_dir, p))
    return p


def url_from_path(path):
    p = os.path.abspath(path).replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", p):
        drive, rest = p[0], p[2:]
        return "file://localhost/" + drive + "%3a" + urllib.parse.quote(rest, safe="/")
    if p.startswith("//"):
        return "file:" + urllib.parse.quote(p, safe="/")
    return "file://localhost" + urllib.parse.quote(p, safe="/")


# ---- model --------------------------------------------------------------------------

class MediaFile(object):
    """One media file the sequence uses (one <file id>)."""

    def __init__(self, fid, path, name, el=None):
        self.id = fid
        self.path = path
        self.name = name or (os.path.basename(path) if path else fid)
        self.el = el                 # full <file> definition from the source, if any
        self.rate = None             # (timebase, ntsc)
        self.duration = 0            # frames at self.rate
        self.width = 0
        self.height = 0
        self.has_video = False
        self.channels = 0            # audio channels
        self.samplerate = 48000
        self.bin = None
        self.track = None            # label of the first track it sits on ("V2", "A5")
        self.timecode = None

    @property
    def seconds(self):
        return self.duration / fps_of(self.rate) if self.rate and self.duration else 0.0


class Item(object):
    """One clipitem on a track of the source sequence."""

    def __init__(self, el, kind, track_no, fid):
        self.el = el
        self.kind = kind             # "video" or "audio"
        self.track_no = track_no     # 1-based within its kind
        self.fid = fid
        self.id = el.get("id") or ""
        self.start = _int(el, "start", -1)
        self.end = _int(el, "end", -1)
        self.in_ = _int(el, "in", 0)
        self.out = _int(el, "out", 0)
        self.rate = rate_of(el)

    @property
    def length(self):
        if self.start >= 0 and self.end >= 0:
            return self.end - self.start
        return max(0, self.out - self.in_)


class Source(object):
    def __init__(self):
        self.path = None
        self.root = None
        self.seq = None              # the <sequence> element (None for bins / loose files)
        self.name = "Untitled"
        self.rate = (24, True)
        self.width = 1920
        self.height = 1080
        self.samplerate = 48000
        self.files = {}              # fid -> MediaFile (in first-use order)
        self.items = []              # [Item] (sequence sources)
        self.video_tracks = 0
        self.audio_tracks = 0
        self.dropped = 0             # transitions / generators left out

    @property
    def fps(self):
        return fps_of(self.rate)


def _file_info(mf, el):
    mf.rate = rate_of(el) or mf.rate
    mf.duration = _int(el, "duration", mf.duration)
    media = el.find("media")
    if media is not None:
        v = media.find("video")
        if v is not None:
            mf.has_video = True
            sc = v.find("samplecharacteristics")
            if sc is not None:
                mf.width = _int(sc, "width", mf.width)
                mf.height = _int(sc, "height", mf.height)
                mf.rate = rate_of(sc) or mf.rate
        a = media.find("audio")
        if a is not None:
            mf.channels = max(1, _int(a, "channelcount", 1))
            sc = a.find("samplecharacteristics")
            if sc is not None:
                mf.samplerate = _int(sc, "samplerate", mf.samplerate)
    tc = el.find("timecode")
    if tc is not None and tc.findtext("string"):
        mf.timecode = tc.findtext("string")


def read(path=None, text=None, base_dir=None, sequence_name=None):
    """Parse an xmeml file (or text). Picks the named sequence, else the one with the most clips."""
    src = Source()
    src.path = path
    try:
        if text is not None:
            root = ET.fromstring(text)
        else:
            root = ET.parse(path).getroot()
    except ET.ParseError as e:
        raise XmlError("This XML can't be read: %s" % e)
    except OSError as e:
        raise XmlError("Couldn't open the XML: %s" % e)
    if root.tag != "xmeml":
        if root.tag == "fcpxml":
            raise XmlError("This is a Final Cut Pro X file (.fcpxml). Export Final Cut Pro 7 XML instead: "
                           "in Premiere, File > Export > Final Cut Pro XML.")
        raise XmlError("Not a Final Cut Pro XML file")
    src.root = root
    base = base_dir or (os.path.dirname(os.path.abspath(path)) if path else None)

    # every full <file> definition, wherever it is
    defs = {}
    for f in root.iter("file"):
        fid = f.get("id")
        if fid and (f.find("pathurl") is not None or f.find("media") is not None) and fid not in defs:
            defs[fid] = f

    def media_file(fid, el):
        if fid in src.files:
            return src.files[fid]
        full = defs.get(fid, el)
        p = path_from_url(full.findtext("pathurl"), base)
        mf = MediaFile(fid, p, full.findtext("name") or (os.path.basename(p) if p else fid), full)
        mf.rate = rate_of(full)
        _file_info(mf, full)
        src.files[fid] = mf
        return mf

    seqs = list(root.iter("sequence"))
    seq = None
    if seqs:
        if sequence_name:
            named = [s for s in seqs if (s.findtext("name") or "") == sequence_name]
            seq = named[0] if named else None
        if seq is None:
            seq = max(seqs, key=lambda s: sum(1 for _ in s.iter("clipitem")))
            if not any(True for _ in seq.iter("clipitem")):
                seq = None
    if seq is not None:
        src.seq = seq
        src.name = seq.findtext("name") or "Sequence"
        src.rate = rate_of(seq, (24, True))
        sc = seq.find("media/video/format/samplecharacteristics")
        if sc is not None:
            src.width = _int(sc, "width", src.width)
            src.height = _int(sc, "height", src.height)
        asc = seq.find("media/audio/format/samplecharacteristics")
        if asc is not None:
            src.samplerate = _int(asc, "samplerate", src.samplerate)
        for kind in ("video", "audio"):
            tracks = seq.findall("media/%s/track" % kind)
            if kind == "video":
                src.video_tracks = len(tracks)
            else:
                src.audio_tracks = len(tracks)
            for n, tr in enumerate(tracks, 1):
                for child in list(tr):
                    if child.tag in ("transitionitem", "generatoritem"):
                        src.dropped += 1
                    if child.tag != "clipitem":
                        continue
                    f = child.find("file")
                    if f is None or not f.get("id"):
                        src.dropped += 1
                        continue
                    mf = media_file(f.get("id"), f)
                    it = Item(child, kind, n, mf.id)
                    if kind == "video":
                        mf.has_video = True
                    src.items.append(it)
                    if mf.track is None or (kind == "video" and mf.track.startswith("A")):
                        mf.track = ("V%d" if kind == "video" else "A%d") % n
        # files that only show up on audio tracks are recorders
        return src

    # No sequence: a project/bin export. Every <clip> with media becomes a file.
    def walk(el, bins):
        for child in el:
            if child.tag == "bin":
                walk(child, bins + [child.findtext("name") or "Bin"])
            elif child.tag == "clip":
                f = next(iter(child.iter("file")), None)
                if f is not None and f.get("id"):
                    mf = media_file(f.get("id"), f)
                    if mf.bin is None:
                        mf.bin = "/".join(bins) or None
            elif child.tag in ("children", "project"):
                walk(child, bins if child.tag == "children" else bins + [child.findtext("name") or ""][:0])
    walk(root, [])
    if not src.files:
        raise XmlError("There's no sequence or footage in this XML")
    first_video = next((f for f in src.files.values() if f.has_video and f.rate), None)
    if first_video:
        src.rate = first_video.rate
        src.width, src.height = first_video.width or src.width, first_video.height or src.height
    src.name = os.path.splitext(os.path.basename(path))[0] if path else "Footage"
    return src


# ---- writing helpers --------------------------------------------------------------------

def _set(el, tag, value):
    c = el.find(tag)
    if c is None:
        c = ET.SubElement(el, tag)
    c.text = str(value)
    return c


def _label(el, name):
    for old in el.findall("labels"):
        el.remove(old)
    lab = ET.SubElement(el, "labels")
    ET.SubElement(lab, "label2").text = name


def _marker(el, name, comment, at):
    m = ET.SubElement(el, "marker")
    ET.SubElement(m, "comment").text = comment
    ET.SubElement(m, "name").text = name
    ET.SubElement(m, "in").text = str(at)
    ET.SubElement(m, "out").text = "-1"


def _indent(el, level=0):
    pad = "\n" + "\t" * level
    if len(el):
        if not el.text or not el.text.strip():
            el.text = pad + "\t"
        for child in el:
            _indent(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = pad
    if level and (not el.tail or not el.tail.strip()):
        el.tail = pad


def _serialise(root):
    _indent(root)
    body = ET.tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n' + body + "\n"


def _fix_file_defs(seq, defs):
    """First use of each file carries the full definition, later uses just reference it."""
    seen = set()
    for ci in seq.iter("clipitem"):
        f = ci.find("file")
        if f is None:
            continue
        fid = f.get("id")
        if fid not in seen:
            seen.add(fid)
            if len(f) == 0 and fid in defs and defs[fid] is not None:
                idx = list(ci).index(f)
                ci.remove(f)
                ci.insert(idx, copy.deepcopy(defs[fid]))
        elif len(f):
            for c in list(f):
                f.remove(c)


def _fix_links(seq):
    """Links name their partner's track and position; refresh them after clips moved tracks."""
    where = {}
    for kind in ("video", "audio"):
        for tn, tr in enumerate(seq.findall("media/%s/track" % kind), 1):
            for cn, ci in enumerate(tr.findall("clipitem"), 1):
                where[ci.get("id")] = (kind, tn, cn)
    for ci in seq.iter("clipitem"):
        for ln in ci.findall("link"):
            ref = ln.findtext("linkclipref")
            if ref in where:
                kind, tn, cn = where[ref]
                _set(ln, "mediatype", kind)
                _set(ln, "trackindex", tn)
                _set(ln, "clipindex", cn)
            elif ref:
                ci.remove(ln)


def _pack(tracks_el, placed, make_track):
    """Lay clipitems on tracks without overlaps.

    placed: [(original_track_no, start, end, clipitem_el)]. A clip stays on its original track
    unless something already sits there at that time; then it goes to an extra track right
    below, made by make_track(original_track_element).
    """
    originals = tracks_el.findall("track")
    lanes = {n: [[orig, -1]] for n, orig in enumerate(originals, 1)}   # track_no -> [[track_el, last_end]]
    for tr in originals:
        for c in list(tr):
            if c.tag in ("clipitem", "transitionitem", "generatoritem"):
                tr.remove(c)
    for tn, start, end, ci in sorted(placed, key=lambda p: (p[0], p[1])):
        for lane in lanes[tn]:
            if start >= lane[1]:
                break
        else:
            new = make_track(lanes[tn][-1][0])
            pos = list(tracks_el).index(lanes[tn][-1][0]) + 1
            tracks_el.insert(pos, new)
            lane = [new, -1]
            lanes[tn].append(lane)
        _insert_item(lane[0], ci)
        lane[1] = end


def _insert_item(track, ci):
    # clipitems go before the track's own settings (<enabled>, <locked>...)
    kids = list(track)
    idx = next((k for k, c in enumerate(kids) if c.tag not in ("clipitem",)), len(kids))
    track.insert(idx, ci)


def _empty_track_like(tr):
    new = ET.Element("track", dict(tr.attrib))
    for c in tr:
        if c.tag not in ("clipitem", "transitionitem", "generatoritem"):
            new.append(copy.deepcopy(c))
    return new


# ---- synced output -------------------------------------------------------------------

def write_synced(src, placement, status=None, confidence=None, keep_camera_audio=True, mark_low=True,
                 unsynced="end", name=None):
    """The source sequence with every clip moved to its synced time. Returns (xml_text, info).

    placement: fid -> seconds where the media's first frame sits (None = not synced).
    status / confidence: fid -> "synced" | "low" | "unsynced" and 0..1, for labels and markers.
    """
    if src.seq is None:
        raise XmlError("No sequence to sync: use build() for loose footage")
    status = status or {}
    confidence = confidence or {}
    seq = copy.deepcopy(src.seq)
    seq_name = name or "%s (SYN)" % src.name
    _set(seq, "name", seq_name)
    for u in seq.findall("uuid"):
        seq.remove(u)
    seq.set("id", "sequence-syn-%s" % uuid.uuid4().hex[:8])
    fps = src.fps
    # map the copies back to the source items
    copies = {}
    for kind in ("video", "audio"):
        for tn, tr in enumerate(seq.findall("media/%s/track" % kind), 1):
            for ci in tr.findall("clipitem"):
                copies[(kind, tn, ci.get("id"))] = ci
    has_recorder = any(not f.has_video and f.channels for f in src.files.values()
                       if placement.get(f.id) is not None)

    synced, loose = {"video": [], "audio": []}, {"video": [], "audio": []}
    end_frame = 0
    for it in src.items:
        ci = copies.get((it.kind, it.track_no, it.id))
        if ci is None:
            continue
        rate = it.rate or src.rate
        in_sec = it.in_ / fps_of(rate)
        length = it.length
        at = placement.get(it.fid)
        if at is None:
            loose[it.kind].append((it, ci, length))
            continue
        start = int(round((at + in_sec) * fps))
        synced[it.kind].append((it.track_no, start, start + length, ci))
        end_frame = max(end_frame, start + length)
        st = status.get(it.fid)
        if st == "low" and mark_low:
            _label(ci, LOW_LABEL)
            if it.kind == "video" or not src.files[it.fid].has_video:
                _marker(ci, "SYN: low confidence (%.2f)" % confidence.get(it.fid, 0.0),
                        "Check this clip's sync", it.in_)
        if it.kind == "audio" and not keep_camera_audio and has_recorder and src.files[it.fid].has_video:
            _set(ci, "enabled", "FALSE")

    # shift so the timeline starts at 0
    first = min([p[1] for k in synced for p in synced[k]] or [0])
    for k in synced:
        synced[k] = [(tn, s - first, e - first, ci) for tn, s, e, ci in synced[k]]
    end_frame -= first

    # unsynced clips go after everything, one after another, on their own tracks
    if unsynced == "end":
        t = end_frame + int(GAP_SECONDS * fps) if end_frame else 0
        order = {}
        for kind in ("video", "audio"):
            for it, ci, length in loose[kind]:
                if it.fid not in order:
                    order[it.fid] = None
        cursor = t
        for fid in order:
            items = [(it, ci, ln) for kind in ("video", "audio") for it, ci, ln in loose[kind] if it.fid == fid]
            span = 0
            for it, ci, length in items:
                start = cursor + int(round(it.in_ / fps_of(it.rate or src.rate) * fps)) - \
                    min(int(round(i.in_ / fps_of(i.rate or src.rate) * fps)) for i, _, _ in items)
                synced[it.kind].append((it.track_no, start, start + length, ci))
                span = max(span, start + length - cursor)
                _label(ci, UNSYNCED_LABEL)
                if it.kind == "video" or not src.files[it.fid].has_video:
                    _marker(ci, "SYN: not synced", "SYN couldn't find this clip's sound in the other clips", it.in_)
            cursor += span + int(fps)
        end_frame = max(end_frame, cursor)

    for kind in ("video", "audio"):
        tracks_el = seq.find("media/%s" % kind)
        if tracks_el is None:
            continue
        for tn, start, end, ci in synced[kind]:
            _set(ci, "start", start)
            _set(ci, "end", end)
        _pack(tracks_el, synced[kind], _empty_track_like)
    _set(seq, "duration", end_frame)
    defs = {fid: f.el for fid, f in src.files.items()}
    _fix_file_defs(seq, defs)
    _fix_links(seq)
    root = ET.Element("xmeml", {"version": src.root.get("version", "4")})
    root.append(seq)
    info = {"name": seq_name, "video_tracks": len(seq.findall("media/video/track")),
            "audio_tracks": len(seq.findall("media/audio/track")), "frames": end_frame}
    return _serialise(root), info


# ---- sequences built from loose footage -------------------------------------------------

def _file_el(mf, rate):
    f = ET.Element("file", {"id": mf.id})
    ET.SubElement(f, "name").text = mf.name
    ET.SubElement(f, "pathurl").text = url_from_path(mf.path)
    r = mf.rate or rate
    f.append(_rate_el(r))
    ET.SubElement(f, "duration").text = str(mf.duration)
    tc = ET.SubElement(f, "timecode")
    tc.append(_rate_el(r))
    ET.SubElement(tc, "string").text = mf.timecode or "00:00:00:00"
    ET.SubElement(tc, "frame").text = "0"
    ET.SubElement(tc, "displayformat").text = "DF" if (r[1] and mf.timecode and ";" in mf.timecode) else "NDF"
    media = ET.SubElement(f, "media")
    if mf.has_video:
        v = ET.SubElement(media, "video")
        sc = ET.SubElement(v, "samplecharacteristics")
        sc.append(_rate_el(r))
        ET.SubElement(sc, "width").text = str(mf.width or 1920)
        ET.SubElement(sc, "height").text = str(mf.height or 1080)
        ET.SubElement(sc, "anamorphic").text = "FALSE"
        ET.SubElement(sc, "pixelaspectratio").text = "square"
        ET.SubElement(sc, "fielddominance").text = "none"
    if mf.channels:
        a = ET.SubElement(media, "audio")
        sc = ET.SubElement(a, "samplecharacteristics")
        ET.SubElement(sc, "depth").text = "16"
        ET.SubElement(sc, "samplerate").text = str(mf.samplerate or 48000)
        ET.SubElement(a, "channelcount").text = str(mf.channels)
    mf.el = f
    return f


def media_file_from_probe(fid, info):
    """MediaFile from media.probe() output."""
    mf = MediaFile(fid, info["path"], os.path.basename(info["path"]))
    v = info.get("video")
    if v:
        mf.has_video = True
        mf.width, mf.height = v.get("width") or 0, v.get("height") or 0
        mf.rate = rate_for_fps(v.get("fps") or 0)
    if info.get("audio"):
        a = info["audio"][0]
        mf.channels = max(1, min(8, a.get("channels") or 1))
        mf.samplerate = a.get("rate") or 48000
    mf.timecode = info.get("timecode")
    mf._seconds = info.get("duration") or 0.0
    return mf


def build(files, lanes, placement, seq_name, rate=None, size=None, status=None, confidence=None,
          keep_camera_audio=True, mark_low=True, unsynced="end", channel_tracks=True):
    """A new sequence for loose footage.

    files: [MediaFile] (rate/duration filled; for audio-only files rate may be None)
    lanes: [(label, [fid...])] one camera/recorder each, in display order
    placement: fid -> seconds (None = unsynced)
    """
    status = status or {}
    confidence = confidence or {}
    by_id = {f.id: f for f in files}
    vid = next((f for f in files if f.has_video and f.rate), None)
    rate = rate or (vid.rate if vid else (24, True))
    width, height = size or ((vid.width or 1920, vid.height or 1080) if vid else (1920, 1080))
    fps = fps_of(rate)
    for f in files:
        if not f.duration:
            secs = getattr(f, "_seconds", 0.0) or 0.0
            f.duration = int(round(secs * fps_of(f.rate or rate)))

    has_recorder = any(not f.has_video and f.channels and placement.get(f.id) is not None for f in files)
    # timeline positions in sequence frames
    starts = {fid: int(round(t * fps)) for fid, t in placement.items() if t is not None}
    first = min(starts.values()) if starts else 0
    starts = {k: v - first for k, v in starts.items()}

    def length(f):
        return max(1, int(round(f.duration / fps_of(f.rate or rate) * fps)))

    end = max([starts[f.id] + length(f) for f in files if f.id in starts] or [0])
    if unsynced == "end":
        cursor = end + int(GAP_SECONDS * fps) if end else 0
        for label, fids in lanes:
            for fid in fids:
                if fid not in starts and by_id[fid].path:
                    starts[fid] = cursor
                    cursor += length(by_id[fid]) + int(fps)
        end = max(end, cursor)

    root = ET.Element("xmeml", {"version": "4"})
    seq = ET.SubElement(root, "sequence", {"id": "sequence-syn-%s" % uuid.uuid4().hex[:8]})
    ET.SubElement(seq, "name").text = seq_name
    ET.SubElement(seq, "duration").text = str(end)
    seq.append(_rate_el(rate))
    tc = ET.SubElement(seq, "timecode")
    tc.append(_rate_el(rate))
    ET.SubElement(tc, "string").text = "00:00:00:00"
    ET.SubElement(tc, "frame").text = "0"
    ET.SubElement(tc, "displayformat").text = "NDF"
    media = ET.SubElement(seq, "media")
    video = ET.SubElement(media, "video")
    fmt = ET.SubElement(ET.SubElement(video, "format"), "samplecharacteristics")
    fmt.append(_rate_el(rate))
    ET.SubElement(fmt, "width").text = str(width)
    ET.SubElement(fmt, "height").text = str(height)
    ET.SubElement(fmt, "anamorphic").text = "FALSE"
    ET.SubElement(fmt, "pixelaspectratio").text = "square"
    ET.SubElement(fmt, "fielddominance").text = "none"
    audio = ET.SubElement(media, "audio")
    ET.SubElement(audio, "numOutputChannels").text = "2"
    afmt = ET.SubElement(ET.SubElement(audio, "format"), "samplecharacteristics")
    ET.SubElement(afmt, "depth").text = "16"
    ET.SubElement(afmt, "samplerate").text = "48000"

    n = [0]

    def clipitem(f, kind, channel=None):
        n[0] += 1
        ci = ET.Element("clipitem", {"id": "clipitem-%d" % n[0]})
        ET.SubElement(ci, "masterclipid").text = "masterclip-%s" % f.id
        ET.SubElement(ci, "name").text = f.name
        ET.SubElement(ci, "enabled").text = "TRUE"
        ET.SubElement(ci, "duration").text = str(length(f))
        ci.append(_rate_el(rate))
        s = starts[f.id]
        ET.SubElement(ci, "start").text = str(s)
        ET.SubElement(ci, "end").text = str(s + length(f))
        ET.SubElement(ci, "in").text = "0"
        ET.SubElement(ci, "out").text = str(length(f))
        ET.SubElement(ci, "file", {"id": f.id})
        if kind == "audio":
            st = ET.SubElement(ci, "sourcetrack")
            ET.SubElement(st, "mediatype").text = "audio"
            ET.SubElement(st, "trackindex").text = str(channel or 1)
            if not keep_camera_audio and has_recorder and f.has_video:
                ci.find("enabled").text = "FALSE"
        stt = status.get(f.id)
        if f.id not in placement or placement.get(f.id) is None:
            _label(ci, UNSYNCED_LABEL)
            if kind == "video" or not f.has_video:
                _marker(ci, "SYN: not synced", "SYN couldn't find this clip's sound in the other clips", 0)
        elif stt == "low" and mark_low:
            _label(ci, LOW_LABEL)
            if kind == "video" or not f.has_video:
                _marker(ci, "SYN: low confidence (%.2f)" % confidence.get(f.id, 0.0), "Check this clip's sync", 0)
        return ci

    groups = {}   # fid -> [clipitem elements] for links
    vtracks, atracks = [], []
    for label, fids in lanes:
        placed = [by_id[f] for f in fids if f in starts and by_id[f].path]
        if not placed:
            continue
        vids = [f for f in placed if f.has_video]
        if vids:
            items = []
            for f in sorted(vids, key=lambda f: starts[f.id]):
                ci = clipitem(f, "video")
                groups.setdefault(f.id, []).append(ci)
                items.append((1, starts[f.id], starts[f.id] + length(f), ci))
            vtracks.append(items)
        chans = max([f.channels for f in placed if f.channels] or [0])
        chans = chans if channel_tracks else min(chans, 1)
        for ch in range(1, chans + 1):
            items = []
            for f in sorted(placed, key=lambda f: starts[f.id]):
                if f.channels >= ch or (not channel_tracks and f.channels):
                    ci = clipitem(f, "audio", ch)
                    groups.setdefault(f.id, []).append(ci)
                    items.append((1, starts[f.id], starts[f.id] + length(f), ci))
            if items:
                atracks.append(items)

    def place(parent, tracks):
        for items in tracks:
            holder = ET.Element("holder")
            tr = ET.SubElement(holder, "track")
            ET.SubElement(tr, "enabled").text = "TRUE"
            ET.SubElement(tr, "locked").text = "FALSE"
            parent.append(holder)
            _pack(holder, items, _empty_track_like)
            for t in holder.findall("track"):
                parent.append(t)
            parent.remove(holder)

    place(video, vtracks)
    place(audio, atracks)
    # links: every clipitem of the same file is linked to the others
    for fid, cis in groups.items():
        if len(cis) < 2:
            continue
        for ci in cis:
            for other in cis:
                ln = ET.SubElement(ci, "link")
                ET.SubElement(ln, "linkclipref").text = other.get("id")
    _fix_file_defs(seq, {f.id: _file_el(f, rate) for f in files})
    _fix_links(seq)
    # <link> must come after <file>/<sourcetrack>; move label/marker/link to the end in order
    for ci in seq.iter("clipitem"):
        tail = [c for c in ci if c.tag in ("labels", "marker", "link")]
        for c in tail:
            ci.remove(c)
        for tag in ("link", "labels", "marker"):
            for c in tail:
                if c.tag == tag:
                    ci.append(c)
    info = {"name": seq_name, "video_tracks": len(video.findall("track")), "audio_tracks": len(audio.findall("track")),
            "frames": end}
    return _serialise(root), info


def default_name():
    return "SYN %s" % ("Mac" if sys.platform == "darwin" else "PC")
