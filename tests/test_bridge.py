"""The Premiere bridge end to end: pairing, a media job synced for real, Send to Premiere,
the WebSocket and the file mailbox."""
import base64
import http.client
import json
import os
import shutil
import socket
import sys
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["SYN_HOME"] = tempfile.mkdtemp(prefix="syn-home-")

import synth  # noqa: E402
from syn import bridge, media  # noqa: E402
from syn.settings import Settings  # noqa: E402


def req(port, method, path, body=None, token=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = dict(headers or {})
    if token:
        h["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    if data is not None:
        h["Content-Type"] = "application/json"
    c.request(method, path, body=data, headers=h)
    r = c.getresponse()
    raw = r.read()
    c.close()
    try:
        return r.status, json.loads(raw)
    except ValueError:
        return r.status, raw.decode()


def wait(cond, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        v = cond()
        if v:
            return v
        time.sleep(0.05)
    raise AssertionError("timed out")


@unittest.skipUnless(media.find_ffmpeg(), "needs ffmpeg")
class BridgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="syn-bridge-")
        W = synth.world(200, seed=21)
        lav = synth.mic(W, 1, noise=0.003)
        cam = synth.mic(W, 2, gain=0.4, noise=0.005, tilt=0.5)
        cls.items = [
            {"path": synth.write_wav(os.path.join(cls.dir, "ZOOM0001.wav"), synth.cut(lav, 0, 190)), "bin": "Audio"},
            {"path": synth.write_wav(os.path.join(cls.dir, "A001.wav"), synth.cut(cam, 30, 60)), "bin": "Cam A"},
            {"path": synth.write_wav(os.path.join(cls.dir, "A002.wav"), synth.cut(cam, 120, 50)), "bin": "Cam A"},
        ]
        cls.events = []
        cls.settings = Settings(os.path.join(cls.dir, "settings.json"))
        cls.b = bridge.Bridge(cls.settings, on_event=lambda k, p: cls.events.append((k, p)), auto_approve=False).start()
        cls.port = cls.b.port

    @classmethod
    def tearDownClass(cls):
        cls.b.stop()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def pair(self):
        st, r = req(self.port, "POST", "/v1/pair", {"client": "premiere", "clientVersion": "1.0.0", "hostVersion": "25.6"})
        self.assertEqual(st, 202)
        pid = r["pairId"]
        self.assertEqual(req(self.port, "GET", "/v1/pair/" + pid)[1]["status"], "pending")
        self.assertIn("pair", [k for k, _ in self.events])
        self.b.decide(pid, True)
        st, r = req(self.port, "GET", "/v1/pair/" + pid)
        self.assertEqual(r["status"], "approved")
        return r["token"]

    def test_hello_and_guards(self):
        st, r = req(self.port, "GET", "/v1/hello")
        self.assertEqual((st, r["app"], r["api"]), (200, "Syn", 1))
        self.assertEqual(req(self.port, "GET", "/v1/hello", headers={"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(req(self.port, "GET", "/v1/hello", headers={"Origin": "null"})[0], 200)
        self.assertEqual(req(self.port, "GET", "/v1/hello", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(req(self.port, "GET", "/v1/jobs")[0], 401)
        self.assertEqual(req(self.port, "GET", "/v1/jobs", token="nope")[0], 401)

    def test_media_job_round_trip(self):
        token = self.pair()
        ws = WS(self.port, token)
        st, r = req(self.port, "POST", "/v1/jobs", {"source": {"kind": "media", "items": self.items},
                                                    "sequenceName": "Day 1"}, token=token)
        self.assertEqual(st, 201, r)
        jid = r["jobId"]
        job = wait(lambda: (lambda j: j if j["state"] == "review" else None)(req(self.port, "GET", "/v1/jobs/" + jid, token=token)[1]))
        self.assertEqual(job["api"], 1)
        self.assertIsInstance(job["createdAt"], int)
        clips = {c["name"]: c for c in job["result"]["confidence"]["clips"]}
        self.assertEqual(clips["A001.wav"]["status"], "synced")
        self.assertGreater(job["result"]["confidence"]["overall"], 0.8)
        fps = 24000 / 1001.0
        self.assertLessEqual(abs(clips["A002.wav"]["offsetFrames"] - clips["A001.wav"]["offsetFrames"] - round(90 * fps)), 1)
        # the user clicks Send to Premiere
        self.b.send(jid)
        job = req(self.port, "GET", "/v1/jobs/" + jid, token=token)[1]
        self.assertEqual(job["state"], "done")
        self.assertTrue(os.path.isfile(job["result"]["xmlPath"]))
        self.assertEqual(job["result"]["sequenceName"], "Day 1 (SYN)")
        st, text = req(self.port, "GET", "/v1/jobs/%s/result.xml" % jid, token=token)
        self.assertEqual(st, 200)
        ET.fromstring(text.split("\n", 2)[2])
        self.assertTrue(os.path.isfile(os.path.join(self.b.dir, "send", jid + ".json")))
        msgs = ws.until(lambda m: m.get("type") == "send")
        self.assertEqual(msgs[-1]["jobId"], jid)
        st, _ = req(self.port, "POST", "/v1/jobs/%s/imported" % jid, {"sequenceName": "Day 1 (SYN)"}, token=token)
        self.assertEqual(st, 200)
        self.assertIsNotNone(req(self.port, "GET", "/v1/jobs/" + jid, token=token)[1]["importedAt"])
        ws.close()

    def test_file_mailbox(self):
        wait(lambda: os.path.isfile(os.path.join(self.b.dir, "hello.json")))
        with open(os.path.join(self.b.dir, "hello.json")) as f:
            hello = json.load(f)
        self.assertEqual(hello["app"], "Syn")
        self.assertLess(time.time() * 1000 - hello["heartbeat"], 6000)
        rq = os.path.join(self.b.dir, "requests", "r1.json")
        with open(rq + ".tmp", "w") as f:
            json.dump({"op": "job.create", "body": {"source": {"kind": "media", "items": self.items[:2]}}}, f)
        os.replace(rq + ".tmp", rq)
        resp = os.path.join(self.b.dir, "responses", "r1.json")
        wait(lambda: os.path.isfile(resp))
        with open(resp) as f:
            jid = json.load(f)["jobId"]
        self.assertFalse(os.path.exists(rq))
        jf = os.path.join(self.b.dir, "jobs", jid + ".json")
        wait(lambda: os.path.isfile(jf) and json.load(open(jf))["state"] == "review")
        # bad op answers with an error
        rq2 = os.path.join(self.b.dir, "requests", "r2.json")
        with open(rq2, "w") as f:
            json.dump({"op": "nope", "body": {}}, f)
        resp2 = os.path.join(self.b.dir, "responses", "r2.json")
        wait(lambda: os.path.isfile(resp2))
        self.assertEqual(json.load(open(resp2))["error"]["code"], "bad_op")

    def test_bad_source(self):
        token = self.pair()
        st, r = req(self.port, "POST", "/v1/jobs", {"source": {"kind": "xml", "xml": "<nope/>"}}, token=token)
        self.assertEqual(st, 400)
        self.assertEqual(r["error"]["code"], "bad_xml")


class WS(object):
    """Just enough of a WebSocket client for the test."""

    def __init__(self, port, token):
        self.s = socket.create_connection(("127.0.0.1", port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall(("GET /v1/events?token=%s HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nUpgrade: websocket\r\n"
                        "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n"
                        % (token, port, key)).encode())
        head = b""
        while b"\r\n\r\n" not in head:
            head += self.s.recv(1)
        assert b" 101 " in head.split(b"\r\n")[0], head
        self.msgs = []

    def until(self, cond):
        while True:
            fr = bridge._ws_read(self.s)
            assert fr is not None
            if fr[0] == 1:
                m = json.loads(fr[1])
                self.msgs.append(m)
                if cond(m):
                    return self.msgs

    def close(self):
        self.s.close()


if __name__ == "__main__":
    unittest.main()
