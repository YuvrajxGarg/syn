import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SYN_HOME", tempfile.mkdtemp(prefix="syn-home-"))

from syn import xmeml  # noqa: E402


def file_def(fid, name, path, video=True, channels=2, frames=2400):
    v = ("<video><samplecharacteristics><rate><timebase>24</timebase><ntsc>TRUE</ntsc></rate>"
         "<width>3840</width><height>2160</height></samplecharacteristics></video>") if video else ""
    return ('<file id="%s"><name>%s</name><pathurl>%s</pathurl><rate><timebase>24</timebase><ntsc>TRUE</ntsc></rate>'
            '<duration>%d</duration><media>%s<audio><samplecharacteristics><depth>24</depth><samplerate>48000</samplerate>'
            '</samplecharacteristics><channelcount>%d</channelcount></audio></media></file>'
            % (fid, name, xmeml.url_from_path(path), frames, v, channels))


def clipitem(cid, name, fid, start, frames, full=None, kind="video", links=(), track=1):
    f = full if full else '<file id="%s"/>' % fid
    st = ("<sourcetrack><mediatype>audio</mediatype><trackindex>%d</trackindex></sourcetrack>" % track) if kind == "audio" else ""
    ln = "".join("<link><linkclipref>%s</linkclipref><mediatype>%s</mediatype><trackindex>1</trackindex><clipindex>1</clipindex></link>"
                 % (l, k) for l, k in links)
    return ('<clipitem id="%s"><masterclipid>m-%s</masterclipid><name>%s</name><enabled>TRUE</enabled><duration>%d</duration>'
            '<rate><timebase>24</timebase><ntsc>TRUE</ntsc></rate><start>%d</start><end>%d</end><in>0</in><out>%d</out>%s%s%s</clipitem>'
            % (cid, fid, name, frames, start, start + frames, frames, f, st, ln))


def premiere_xml(d):
    """Two cameras dumped on V1/A1-A2 one after another (how Premiere drops a bin), a recorder on A3."""
    a = os.path.join(d, "Cam A", "A001.mov")
    b = os.path.join(d, "Cam B", "B001.mov")
    z = os.path.join(d, "Audio", "ZOOM0001.WAV")
    v = (clipitem("ci-1", "A001.mov", "f-a", 0, 2400, file_def("f-a", "A001.mov", a), links=[("ci-1", "video"), ("ci-3", "audio")])
         + clipitem("ci-2", "B001.mov", "f-b", 2400, 1200, file_def("f-b", "B001.mov", b), links=[("ci-2", "video"), ("ci-4", "audio")]))
    a1 = (clipitem("ci-3", "A001.mov", "f-a", 0, 2400, kind="audio", links=[("ci-1", "video"), ("ci-3", "audio")])
          + clipitem("ci-4", "B001.mov", "f-b", 2400, 1200, kind="audio", links=[("ci-2", "video"), ("ci-4", "audio")]))
    a3 = clipitem("ci-5", "ZOOM0001.WAV", "f-z", 0, 4800, file_def("f-z", "ZOOM0001.WAV", z, video=False, channels=1, frames=4800),
                  kind="audio")
    return ('<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE xmeml><xmeml version="4"><sequence id="sequence-1">'
            '<uuid>abc</uuid><name>Interview</name><duration>4800</duration><rate><timebase>24</timebase><ntsc>TRUE</ntsc></rate>'
            '<media><video><format><samplecharacteristics><rate><timebase>24</timebase><ntsc>TRUE</ntsc></rate><width>3840</width>'
            '<height>2160</height></samplecharacteristics></format><track>%s<enabled>TRUE</enabled></track></video>'
            '<audio><track premiereTrackType="Stereo">%s<enabled>TRUE</enabled></track><track><enabled>TRUE</enabled></track>'
            '<track>%s<enabled>TRUE</enabled></track></audio></media></sequence></xmeml>' % (v, a1, a3))


class PathTest(unittest.TestCase):
    def test_round_trip(self):
        for p in ("/Users/me/My Shoot/A001 #2.mov", "/Volumes/SSD/día 1/ZOOM.WAV"):
            self.assertEqual(xmeml.path_from_url(xmeml.url_from_path(p)), p)

    def test_premiere_styles(self):
        self.assertEqual(xmeml.path_from_url("file://localhost/Users/x/a%20b.mov"), "/Users/x/a b.mov")
        self.assertEqual(xmeml.path_from_url("file:///Users/x/a.mov"), "/Users/x/a.mov")
        win = xmeml.path_from_url("file://localhost/C%3a/Footage/a.mov")
        self.assertTrue(win.replace("\\", "/").endswith("C:/Footage/a.mov"))

    def test_rates(self):
        self.assertEqual(xmeml.rate_for_fps(23.976), (24, True))
        self.assertEqual(xmeml.rate_for_fps(29.97), (30, True))
        self.assertEqual(xmeml.rate_for_fps(25.0), (25, False))


class SyncedSequenceTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.src = xmeml.read(text=premiere_xml(self.dir), base_dir=self.dir)

    def test_reads_the_sequence(self):
        s = self.src
        self.assertEqual(s.name, "Interview")
        self.assertEqual(s.rate, (24, True))
        self.assertEqual((s.video_tracks, s.audio_tracks), (1, 3))
        self.assertEqual(set(s.files), {"f-a", "f-b", "f-z"})
        self.assertTrue(s.files["f-a"].has_video)
        self.assertFalse(s.files["f-z"].has_video)
        self.assertEqual(s.files["f-z"].track, "A3")
        self.assertTrue(s.files["f-a"].path.endswith(os.path.join("Cam A", "A001.mov")))

    def test_moves_clips_and_splits_overlaps_onto_new_tracks(self):
        fps = 24000 / 1001.0
        # recorder runs from 0; cam A starts 10 s in, cam B 30 s in: A and B now overlap on V1
        text, info = xmeml.write_synced(self.src, {"f-z": 0.0, "f-a": 10.0, "f-b": 30.0},
                                        status={"f-z": "synced", "f-a": "synced", "f-b": "low"},
                                        confidence={"f-b": 0.61})
        root = ET.fromstring(text.split("\n", 2)[2])
        seq = root.find("sequence")
        self.assertEqual(seq.findtext("name"), "Interview (SYN)")
        self.assertIsNone(seq.find("uuid"))
        vt = seq.findall("media/video/track")
        self.assertEqual(len(vt), 2)                   # B moved to a new video track
        starts = {ci.findtext("name"): int(ci.findtext("start")) for t in vt for ci in t.findall("clipitem")}
        self.assertEqual(starts["A001.mov"], round(10 * fps))
        self.assertEqual(starts["B001.mov"], round(30 * fps))
        at = seq.findall("media/audio/track")
        self.assertEqual(len(at), 4)
        self.assertEqual(at[0].get("premiereTrackType"), "Stereo")   # attributes carried to new tracks
        self.assertEqual(at[1].get("premiereTrackType"), "Stereo")
        # each file is fully defined exactly once
        full = [f for f in seq.iter("file") if len(f)]
        self.assertEqual(sorted(f.get("id") for f in full), ["f-a", "f-b", "f-z"])
        # links point at the partner's new track
        b_video = next(ci for t in vt for ci in t.findall("clipitem") if ci.get("id") == "ci-2")
        idx = {ln.findtext("linkclipref"): int(ln.findtext("trackindex")) for ln in b_video.findall("link")}
        self.assertEqual(idx["ci-2"], 2)
        # low confidence clip is labelled and marked
        self.assertEqual(b_video.findtext("labels/label2"), xmeml.LOW_LABEL)
        self.assertIn("0.61", b_video.findtext("marker/name"))
        self.assertEqual(int(seq.findtext("duration")), info["frames"])

    def test_unsynced_clips_go_to_the_end(self):
        text, _ = xmeml.write_synced(self.src, {"f-z": 0.0, "f-a": 10.0, "f-b": None},
                                     status={"f-b": "unsynced"})
        seq = ET.fromstring(text.split("\n", 2)[2]).find("sequence")
        b = next(ci for ci in seq.iter("clipitem") if ci.get("id") == "ci-2")
        self.assertGreater(int(b.findtext("start")), 4800)
        self.assertEqual(b.findtext("labels/label2"), xmeml.UNSYNCED_LABEL)

    def test_camera_audio_can_be_turned_off(self):
        text, _ = xmeml.write_synced(self.src, {"f-z": 0.0, "f-a": 10.0, "f-b": 30.0}, keep_camera_audio=False)
        seq = ET.fromstring(text.split("\n", 2)[2]).find("sequence")
        en = {ci.get("id"): ci.findtext("enabled") for ci in seq.iter("clipitem")}
        self.assertEqual(en["ci-3"], "FALSE")
        self.assertEqual(en["ci-5"], "TRUE")
        self.assertEqual(en["ci-1"], "TRUE")


class BuildTest(unittest.TestCase):
    def test_loose_footage(self):
        a = xmeml.MediaFile("f1", "/x/A001.mov", "A001.mov")
        a.has_video, a.rate, a.width, a.height, a.channels, a._seconds = True, (24, True), 1920, 1080, 2, 60.0
        z = xmeml.MediaFile("f2", "/x/ZOOM.WAV", "ZOOM.WAV")
        z.channels, z._seconds = 2, 120.0
        text, info = xmeml.build([a, z], [("A", ["f1"]), ("ZOOM", ["f2"])], {"f1": 12.5, "f2": 0.0}, "Shoot (SYN)")
        seq = ET.fromstring(text.split("\n", 2)[2]).find("sequence")
        self.assertEqual(info["video_tracks"], 1)
        self.assertEqual(info["audio_tracks"], 4)       # A ch1/ch2, ZOOM ch1/ch2
        v = seq.find("media/video/track/clipitem")
        self.assertEqual(int(v.findtext("start")), round(12.5 * 24000 / 1001.0))
        self.assertTrue(v.find("file").findtext("pathurl").startswith("file://localhost/x/A001.mov"))
        # A's three clipitems are linked together
        self.assertEqual(len(v.findall("link")), 3)
        st = [ci.findtext("sourcetrack/trackindex") for ci in seq.findall("media/audio/track/clipitem")]
        self.assertEqual(st, ["1", "2", "1", "2"])


if __name__ == "__main__":
    unittest.main()
