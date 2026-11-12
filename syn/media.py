"""Reading footage: what's in a file (probe) and its sound (decode), through ffmpeg.

Audio is decoded once to 8 kHz mono 16-bit and cached on disk, so re-syncing the
same footage (a second pass, another sequence with the same clips) is instant.
"""

import hashlib
import os
import re
import shutil
import subprocess
import sys

import numpy as np

RATE = 8000  # Hz: sync works on speech and transients, 8 kHz keeps 2 h of audio at ~115 MB

VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".mxf", ".avi", ".mkv", ".mts", ".m2ts", ".mpg", ".mpeg", ".webm", ".3gp",
              ".r3d", ".braw", ".insv", ".lrv", ".dv"}
AUDIO_EXTS = {".wav", ".bwf", ".aif", ".aiff", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".caf", ".wma"}
MEDIA_EXTS = VIDEO_EXTS | AUDIO_EXTS
XML_EXTS = {".xml", ".fcpxml"}

_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class MediaError(Exception):
    pass


def find_ffmpeg():
    env = os.environ.get("SYN_FFMPEG")
    if env and os.path.isfile(env):
        return env
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.isfile(exe):
            return exe
    except Exception:
        pass
    found = shutil.which("ffmpeg")
    if found:
        return found
    for cand in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if os.path.isfile(cand):
            return cand
    return None


def kind_of(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in XML_EXTS:
        return "xml"
    return None


def collect(paths):
    """Files and folders dropped on the app -> (media files, xml files), sorted, no duplicates."""
    media, xml, seen = [], [], set()

    def add(p):
        ap = os.path.abspath(p)
        if ap in seen:
            return
        k = kind_of(p)
        if not k or os.path.basename(p).startswith("._"):
            return
        seen.add(ap)
        (xml if k == "xml" else media).append(p)

    for p in paths:
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = sorted(d for d in dirs if not d.startswith("."))
                for f in sorted(files):
                    add(os.path.join(root, f))
        elif os.path.isfile(p):
            add(p)
    return media, xml


# ---- probe ------------------------------------------------------------------

_DUR = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_START = re.compile(r"start:\s*(-?\d+(?:\.\d+)?)")
_FPS = re.compile(r"(\d+(?:\.\d+)?)\s*fps")
_TBR = re.compile(r"(\d+(?:\.\d+)?)\s*tbr")
_SIZE = re.compile(r",\s*(\d{2,5})x(\d{2,5})[\s,\[]")
_HZ = re.compile(r"(\d+)\s*Hz")
_TC = re.compile(r"timecode\s*:\s*(\d\d:\d\d:\d\d[:;.]\d\d)")
_CREATED = re.compile(r"creation_time\s*:\s*(\S+)")
_CHAN_WORDS = {"mono": 1, "stereo": 2, "2.1": 3, "quad": 4, "4.0": 4, "5.0": 5, "5.1": 6, "5.1(side)": 6, "6.1": 7,
               "7.1": 8, "7.1(wide)": 8}


def _channels(line):
    m = re.search(r"(\d+)\s*channels", line)
    if m:
        return int(m.group(1))
    after = line.split("Hz", 1)[-1]
    for tok in re.split(r"[,\s]+", after):
        if tok in _CHAN_WORDS:
            return _CHAN_WORDS[tok]
    return 1


def probe(path):
    """Duration, video size/rate and audio streams of a file, from ffmpeg's own report."""
    ff = find_ffmpeg()
    if not ff:
        raise MediaError("ffmpeg isn't available")
    if not os.path.isfile(path):
        raise MediaError("File not found")
    try:
        p = subprocess.run([ff, "-hide_banner", "-nostdin", "-i", path], capture_output=True, timeout=60,
                           creationflags=_NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise MediaError("Reading the file took too long")
    text = p.stderr.decode("utf-8", "replace")
    info = {"path": path, "duration": 0.0, "start": 0.0, "video": None, "audio": [], "timecode": None,
            "created": None}
    m = _DUR.search(text)
    if m:
        info["duration"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    m = _START.search(text)
    if m:
        info["start"] = float(m.group(1))
    m = _TC.search(text)
    if m:
        info["timecode"] = m.group(1)
    m = _CREATED.search(text)
    if m:
        info["created"] = m.group(1)
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("Stream #"):
            continue
        if ": Video:" in line and info["video"] is None and "attached pic" not in line:
            v = {"width": 0, "height": 0, "fps": 0.0}
            s = _SIZE.search(line)
            if s:
                v["width"], v["height"] = int(s.group(1)), int(s.group(2))
            f = _FPS.search(line) or _TBR.search(line)
            if f:
                v["fps"] = float(f.group(1))
            info["video"] = v
        elif ": Audio:" in line:
            hz = _HZ.search(line)
            info["audio"].append({"rate": int(hz.group(1)) if hz else 48000, "channels": _channels(line)})
    if "Invalid data" in text or (not info["video"] and not info["audio"]):
        raise MediaError("Not a video or audio file ffmpeg can read")
    return info


# ---- decode -----------------------------------------------------------------

def _cache_dir():
    from .settings import app_data_dir

    d = os.path.join(app_data_dir(), "Cache", "audio")
    os.makedirs(d, exist_ok=True)
    return d


def cache_key(path):
    st = os.stat(path)
    raw = "%s|%d|%d|%d" % (os.path.abspath(path), st.st_size, int(st.st_mtime), RATE)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def decode(path, cache=True, cancel=None):
    """The file's sound as int16 mono at RATE. Raises MediaError for files with no audio."""
    if cache:
        try:
            cpath = os.path.join(_cache_dir(), cache_key(path) + ".s16")
            if os.path.isfile(cpath) and os.path.getsize(cpath) > 0:
                return np.fromfile(cpath, dtype="<i2")
        except OSError:
            cpath = None
    else:
        cpath = None
    ff = find_ffmpeg()
    if not ff:
        raise MediaError("ffmpeg isn't available")
    cmd = [ff, "-hide_banner", "-nostdin", "-loglevel", "error", "-i", path, "-map", "0:a:0", "-vn", "-sn", "-dn",
           "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-acodec", "pcm_s16le", "-"]
    chunks = []
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=_NO_WINDOW) as proc:
        try:
            while True:
                b = proc.stdout.read(1 << 20)
                if not b:
                    break
                chunks.append(b)
                if cancel and cancel():
                    raise MediaError("Cancelled")
            err = proc.stderr.read().decode("utf-8", "replace")
        finally:
            if proc.poll() is None:
                proc.kill()
    data = b"".join(chunks)
    if not data:
        if "matches no streams" in err or "Stream map" in err:
            raise MediaError("No audio in this file")
        raise MediaError(err.strip().splitlines()[-1] if err.strip() else "Couldn't read the audio")
    pcm = np.frombuffer(data[: len(data) // 2 * 2], dtype="<i2").copy()
    if cpath:
        try:
            tmp = cpath + ".tmp"
            pcm.tofile(tmp)
            os.replace(tmp, cpath)
        except OSError:
            pass
    return pcm


def clear_cache():
    shutil.rmtree(_cache_dir(), ignore_errors=True)


def cache_size():
    total = 0
    try:
        for f in os.listdir(_cache_dir()):
            try:
                total += os.path.getsize(os.path.join(_cache_dir(), f))
            except OSError:
                pass
    except OSError:
        pass
    return total


def reveal(path):
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path] if os.path.isfile(path) else ["open", path])
        elif os.name == "nt":
            if os.path.isfile(path):
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            else:
                os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path) if os.path.isfile(path) else path])
    except Exception:
        pass
