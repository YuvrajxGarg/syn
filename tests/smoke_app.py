"""Smoke-test a built app: sync a recorder and two camera clips through its command line,
then read the synced XML back and check every clip landed where it was recorded.
    python tests/smoke_app.py <path to Syn executable>
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synth  # noqa: E402
from syn import media, xmeml  # noqa: E402

exe = sys.argv[1]
ff = media.find_ffmpeg()
assert ff, "the smoke test needs ffmpeg to make its test footage (pip install imageio-ffmpeg)"
d = tempfile.mkdtemp()
w = synth.world(80, seed=3)
truth = {"ZOOM0001.WAV": 0.0, "A001.mp4": 12.5, "B001.mp4": 31.0}
rec = synth.mic(w, 1, noise=0.01)
synth.write_wav(os.path.join(d, "ZOOM0001.WAV"), synth.cut(rec, 0, 75), channels=2)
for i, name in enumerate(["A001.mp4", "B001.mp4"]):
    cam = synth.mic(w, 10 + i, gain=0.6, noise=0.02, tilt=0.4)
    synth.write_video(os.path.join(d, name), synth.cut(cam, truth[name], 30), ff)

out = os.path.join(d, "synced.xml")
# The built app must find its own bundled ffmpeg, not the system one.
env = dict(os.environ)
env.pop("SYN_FFMPEG", None)
env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep) if "ffmpeg" not in p.lower())
env["SYN_HOME"] = os.path.join(d, "home")
r = subprocess.run([exe, "sync", d, "-o", out], timeout=600, env=env)
assert os.path.isfile(out), "app wrote no synced XML (exit %s)" % r.returncode

src = xmeml.read(out)
fps = src.fps
starts = {}
for it in src.items:
    name = src.files[it.fid].name
    t = it.start / fps - it.in_ / xmeml.fps_of(it.rate or src.rate)
    starts[name] = min(starts.get(name, t), t)
base = starts["ZOOM0001.WAV"]
for name, want in truth.items():
    got = starts[name] - base
    assert abs(got - want) <= 1.5 / fps, "%s landed at %.3f s, recorded at %.3f s" % (name, got, want)
print("smoke test passed: %s (exit %s), clips at %s" % (exe, r.returncode, {k: round(v - base, 3) for k, v in starts.items()}))
