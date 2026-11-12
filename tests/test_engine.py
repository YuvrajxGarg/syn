import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402

import synth  # noqa: E402

os.environ.setdefault("SYN_HOME", tempfile.mkdtemp(prefix="syn-home-"))
from syn import engine, media  # noqa: E402

FRAME = 1 / 24.0


def pcm(x):
    return (np.clip(x, -1, 1) * 32000).astype(np.int16)


class MatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        W = synth.world(400, seed=1)
        cls.lav = pcm(synth.mic(W, 1, gain=0.9, noise=0.004, tilt=-0.5))
        cls.cam = pcm(synth.mic(W, 2, gain=0.3, noise=0.006, tilt=0.6, echo=0.4))
        cls.other = pcm(synth.mic(synth.world(400, seed=9), 3))
        cls.fa = engine.fingerprint(cls.lav[: 380 * 8000])

    def test_finds_offset_to_the_millisecond(self):
        for start, dur in [(37.25, 60), (200.5, 20), (300.123, 8)]:
            b = self.cam[int(start * 8000): int((start + dur) * 8000)]
            m = engine.match(self.fa, engine.fingerprint(b))
            self.assertLess(abs(m.offset - start), 0.01, (start, m.offset))
            r = engine.refine(self.lav, b, m.offset, max(0, m.offset), m.overlap)
            self.assertLess(abs(r - start), 0.002, (start, r))
            self.assertGreater(m.confidence, 0.6, (start, dur, m.z, m.confidence))

    def test_unrelated_sound_has_low_confidence(self):
        for dur in (60, 20, 8):
            b = self.other[50 * 8000: (50 + dur) * 8000]
            m = engine.match(self.fa, engine.fingerprint(b))
            self.assertLess(m.confidence, 0.2, (dur, m.z, m.z2))

    def test_clip_before_the_reference_starts(self):
        # b starts 12 s before a: negative offset
        a = self.lav[20 * 8000: 200 * 8000]
        b = self.cam[8 * 8000: 60 * 8000]
        m = engine.match(engine.fingerprint(a), engine.fingerprint(b))
        self.assertLess(abs(m.offset - (-12.0)), 0.01)


@unittest.skipUnless(media.find_ffmpeg(), "needs ffmpeg")
class ShootTest(unittest.TestCase):
    """A four-device shoot, written to real files and synced end to end."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="syn-shoot-")
        W = synth.world(600, seed=4)
        devices = {
            "ZOOM": (synth.mic(W, 1, gain=0.8, noise=0.003, tilt=-0.4), [(0, 320), (330, 270)]),
            "A": (synth.mic(W, 2, gain=0.35, noise=0.006, tilt=0.6, echo=0.3), [(20, 60), (100, 45), (250, 90), (400, 30)]),
            "B": (synth.mic(W, 3, gain=0.5, noise=0.005, tilt=0.3, echo=0.2), [(35.5, 120), (300.25, 200)]),
            "PHONE": (synth.mic(W, 4, gain=0.6, noise=0.008, tilt=-0.2), [(500.04, 40)]),
        }
        cls.truth = {}
        cls.clips = []
        for dev, (heard, takes) in devices.items():
            for k, (s, d) in enumerate(takes):
                name = "%s%03d.wav" % (dev, k + 1)
                path = synth.write_wav(os.path.join(cls.dir, name), synth.cut(heard, s, d))
                cls.truth[name] = s
                cls.clips.append(engine.Clip(name, path, group=dev))
        # a take from another day on camera A, and a silent file
        other = synth.mic(synth.world(90, seed=77), 5)
        p = synth.write_wav(os.path.join(cls.dir, "A099.wav"), other[: 60 * 8000])
        cls.clips.append(engine.Clip("A099.wav", p, group="A"))
        p = synth.write_wav(os.path.join(cls.dir, "B099.wav"), np.zeros(8000 * 10, np.float32))
        cls.clips.append(engine.Clip("B099.wav", p, group="B"))
        cls.stages = []
        cls.result = engine.analyze(cls.clips, mode="fast", drift=True,
                                    progress=lambda st, d, t, c: cls.stages.append(st))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_every_take_lands_within_a_frame(self):
        by = {c.id: c for c in self.clips}
        base = by["ZOOM001.wav"].start
        for name, t in self.truth.items():
            c = by[name]
            self.assertIsNotNone(c.start, name)
            self.assertLess(abs((c.start - base) - t), FRAME / 2, (name, c.start - base, t))
            self.assertIn(c.status, ("synced", "low"))
            self.assertEqual(c.component, 0, name)

    def test_strangers_are_left_out(self):
        by = {c.id: c for c in self.clips}
        self.assertEqual(by["A099.wav"].status, "unsynced")
        self.assertIsNone(by["A099.wav"].start)
        self.assertEqual(by["B099.wav"].status, "unsynced")
        self.assertTrue(by["B099.wav"].error)

    def test_confidence(self):
        self.assertGreater(self.result.overall, 0.85)
        long_ones = [c for c in self.clips if c.id in self.truth and c.duration >= 40]
        for c in long_ones:
            self.assertGreaterEqual(c.confidence, engine.HIGH, (c.id, c.confidence))

    def test_progress_reports_stages(self):
        for st in ("read", "match", "solve"):
            self.assertIn(st, self.stages)

    def test_no_drift_on_locked_clocks(self):
        self.assertEqual(self.result.drift, [])


class DriftTest(unittest.TestCase):
    def test_detects_a_fast_clock(self):
        W = synth.world(400, seed=12)
        a = synth.mic(W, 1, noise=0.003)
        # recorder B runs 100 ppm fast: resample its copy of the world
        ppm = 100e-6
        src = synth.mic(W, 2, noise=0.003, tilt=0.3)
        t = np.arange(int(len(src) / (1 + ppm))) * (1 + ppm)
        b = np.interp(t, np.arange(len(src)), src).astype(np.float32)
        ca = engine.Clip("a", "a", group="A")
        cb = engine.Clip("b", "b", group="B")
        ca.fp, ca.duration = engine.fingerprint(pcm(a)), len(a) / 8000.0
        cb.fp, cb.duration = engine.fingerprint(pcm(b[: 380 * 8000])), 380.0
        measured = engine.measure_drift(ca, cb, 0.0)
        self.assertIsNotNone(measured)
        # b's clock runs fast, so its sound arrives earlier and earlier: about -100 ppm
        self.assertLess(abs(abs(measured) - 100), 25, measured)


if __name__ == "__main__":
    unittest.main()
