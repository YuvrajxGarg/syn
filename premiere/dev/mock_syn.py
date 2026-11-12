"""A stand-in for the SYN app's Premiere bridge, for developing and testing the panel.

Implements docs/premiere-bridge.md: HTTP on 127.0.0.1 and the file mailbox. Jobs move
queued -> analyzing -> review on their own; with --auto-send they then go to done the way
they would when the user clicks "Send to Premiere" in SYN.

    python premiere/dev/mock_syn.py --data-dir /tmp/syn-mock --auto-send
"""
from __future__ import annotations

import argparse
import json
import os
import random
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORTS = range(47480, 47490)


class Mock:
    def __init__(self, data: Path, auto_send: bool, approve: str, speed: float, version: str = "1.0.0"):
        self.data = data
        self.bridge = data / "bridge"
        self.outbox = data / "outbox"
        for d in (self.bridge / "requests", self.bridge / "responses", self.bridge / "jobs", self.bridge / "send", self.outbox):
            d.mkdir(parents=True, exist_ok=True)
        self.auto_send = auto_send
        self.approve = approve  # "auto" | "deny" | "never"
        self.speed = speed
        self.version = version
        self.bundled = "1.0.0"
        self.jobs: dict[str, dict] = {}
        self.pairs: dict[str, dict] = {}
        self.tokens: set[str] = set()
        self.lock = threading.RLock()
        self.port: int | None = None
        self.stopped = threading.Event()

    # ---- shared logic ----------------------------------------------------------
    def hello(self) -> dict:
        return {"app": "Syn", "version": self.version, "api": 1, "platform": "mac", "plugin": {"bundled": self.bundled}}

    def create_job(self, body: dict) -> dict:
        src = body.get("source") or {}
        if src.get("kind") not in ("xml", "media"):
            return {"error": {"code": "bad_source", "message": "source.kind must be xml or media"}}
        jid = uuid.uuid4().hex[:12]
        n = len(src.get("items") or []) or 6
        job = {"api": 1, "id": jid, "state": "queued", "progress": 0.0, "stage": "Queued",
               "sequenceName": body.get("sequenceName") or "Sequence", "createdAt": f"{time.time():.3f}",
               "_body": body, "_n": n}
        with self.lock:
            self.jobs[jid] = job
        self._write_job(job)
        threading.Thread(target=self._run, args=(jid,), daemon=True).start()
        return {"jobId": jid}

    def public(self, job: dict) -> dict:
        return {k: v for k, v in job.items() if not k.startswith("_")}

    def _write_job(self, job: dict) -> None:
        _atomic(self.bridge / "jobs" / f"{job['id']}.json", self.public(job))

    def _update(self, jid: str, **kw) -> None:
        with self.lock:
            job = self.jobs[jid]
            job.update(kw)
        self._write_job(job)

    def _run(self, jid: str) -> None:
        job = self.jobs[jid]
        n = job["_n"]
        time.sleep(0.2 / self.speed)
        for i in range(1, n + 1):
            if self.jobs[jid]["state"] == "cancelled":
                return
            self._update(jid, state="analyzing", progress=i / n, stage=f"Matching audio · {i} / {n} clips")
            time.sleep(0.15 / self.speed)
        clips = []
        items = job["_body"]["source"].get("items") or [{"name": f"A00{i}_C00{i}.mov"} for i in range(n)]
        for i, it in enumerate(items):
            conf = round(random.uniform(0.55, 0.99), 2) if i else 0.42
            status = "synced" if conf >= 0.8 else "low" if conf >= 0.5 else "unsynced"
            clips.append({"id": f"clipitem-{i + 1}", "name": it.get("name"), "offsetFrames": random.randint(-300, 300),
                          "confidence": conf, "status": status})
        name = f"{job['sequenceName']} (SYN)"
        xml_path = self.outbox / f"{jid}.xml"
        xml_path.write_text(f'<?xml version="1.0" encoding="UTF-8"?>\n<xmeml version="4"><sequence><name>{name}</name></sequence></xmeml>\n', encoding="utf-8")
        overall = round(sum(c["confidence"] for c in clips) / len(clips), 2)
        result = {"xmlPath": str(xml_path), "sequenceName": name, "confidence": {"overall": overall, "clips": clips}}
        self._update(jid, state="review", progress=1.0, stage="Ready to review", result=result)
        if self.auto_send:
            time.sleep(0.2 / self.speed)
            self.send(jid)

    def send(self, jid: str) -> None:
        self._update(jid, state="done", stage="Sent to Premiere")
        _atomic(self.bridge / "send" / f"{jid}.json", {"jobId": jid})

    def cancel(self, jid: str) -> dict:
        if jid not in self.jobs:
            return {"error": {"code": "not_found", "message": "no such job"}}
        self._update(jid, state="cancelled")
        return {}

    def imported(self, jid: str, body: dict) -> dict:
        if jid not in self.jobs:
            return {"error": {"code": "not_found", "message": "no such job"}}
        self._update(jid, importedAt=time.time(), importedAs=body.get("sequenceName"))
        return {}

    def plugin_update(self) -> dict:
        self.updates = getattr(self, "updates", 0) + 1
        return {"result": "installed"}

    # ---- file transport -----------------------------------------------------------
    def file_loop(self) -> None:
        while not self.stopped.is_set():
            _atomic(self.bridge / "hello.json", dict(self.hello(), heartbeat=int(time.time() * 1000), pid=os.getpid()))
            for req in sorted((self.bridge / "requests").glob("*.json")):
                try:
                    msg = json.loads(req.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                op, body = msg.get("op"), msg.get("body") or {}
                if op == "job.create":
                    resp = self.create_job(body)
                elif op == "job.cancel":
                    resp = self.cancel(body.get("jobId", ""))
                elif op == "plugin.update":
                    resp = self.plugin_update()
                elif op == "job.imported":
                    resp = self.imported(body.get("jobId", ""), body)
                else:
                    resp = {"error": {"code": "bad_op", "message": f"unknown op {op}"}}
                _atomic(self.bridge / "responses" / req.name, resp)
                req.unlink(missing_ok=True)
            self.stopped.wait(0.1)
        (self.bridge / "hello.json").unlink(missing_ok=True)

    # ---- http transport --------------------------------------------------------------
    def serve(self) -> ThreadingHTTPServer:
        mock = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # quiet
                pass

            def _send(self, code: int, obj=None, text: str | None = None):
                data = (text if text is not None else json.dumps(obj if obj is not None else {})).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/xml" if text is not None else "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _body(self) -> dict:
                n = int(self.headers.get("Content-Length") or 0)
                return json.loads(self.rfile.read(n) or b"{}") if n else {}

            def _guard(self) -> bool:
                origin = self.headers.get("Origin")
                if origin and origin != "null" and origin.startswith(("http://", "https://")):
                    self._send(403, {"error": {"code": "origin", "message": "web origins are not allowed"}})
                    return False
                return True

            def _authed(self) -> bool:
                auth = self.headers.get("Authorization") or ""
                if auth.startswith("Bearer ") and auth[7:] in mock.tokens:
                    return True
                self._send(401, {"error": {"code": "unauthorized", "message": "pair first"}})
                return False

            def _err(self, resp: dict, ok: int = 200):
                if "error" in resp:
                    self._send(404 if resp["error"]["code"] == "not_found" else 400, resp)
                else:
                    self._send(ok, resp)

            def do_GET(self):
                if not self._guard():
                    return
                p = self.path.split("?")[0].rstrip("/")
                if p == "/v1/hello":
                    return self._send(200, mock.hello())
                if p.startswith("/v1/pair/"):
                    pr = mock.pairs.get(p.split("/")[-1])
                    return self._send(200, pr) if pr else self._send(404, {"error": {"code": "not_found", "message": "?"}})
                if not self._authed():
                    return
                if p == "/v1/jobs":
                    return self._send(200, {"jobs": [mock.public(j) for j in mock.jobs.values()]})
                parts = p.split("/")
                if len(parts) >= 4 and parts[2] == "jobs":
                    job = mock.jobs.get(parts[3])
                    if not job:
                        return self._send(404, {"error": {"code": "not_found", "message": "no such job"}})
                    if len(parts) == 5 and parts[4] == "result.xml":
                        return self._send(200, text=Path(job["result"]["xmlPath"]).read_text(encoding="utf-8"))
                    return self._send(200, mock.public(job))
                self._send(404, {"error": {"code": "not_found", "message": p}})

            def do_POST(self):
                if not self._guard():
                    return
                p = self.path.rstrip("/")
                if p == "/v1/pair":
                    pid = uuid.uuid4().hex[:8]
                    mock.pairs[pid] = {"status": "pending"}
                    if mock.approve != "never":
                        def decide():
                            time.sleep(0.3)
                            if mock.approve == "auto":
                                tok = uuid.uuid4().hex
                                mock.tokens.add(tok)
                                mock.pairs[pid] = {"status": "approved", "token": tok}
                            else:
                                mock.pairs[pid] = {"status": "denied"}
                        threading.Thread(target=decide, daemon=True).start()
                    return self._send(202, {"pairId": pid})
                if not self._authed():
                    return
                if p == "/v1/jobs":
                    return self._err(mock.create_job(self._body()), 201)
                if p == "/v1/plugin/update":
                    return self._send(200, mock.plugin_update())
                parts = p.split("/")
                if len(parts) == 5 and parts[4] == "imported":
                    return self._err(mock.imported(parts[3], self._body()))
                if len(parts) == 5 and parts[4] == "send":  # dev helper: simulate the SYN button
                    mock.send(parts[3])
                    return self._send(200, {})
                self._send(404, {"error": {"code": "not_found", "message": p}})

            def do_DELETE(self):
                if not self._guard() or not self._authed():
                    return
                self._err(mock.cancel(self.path.rstrip("/").split("/")[-1]))

        for port in PORTS:
            try:
                srv = ThreadingHTTPServer(("127.0.0.1", port), H)
                self.port = port
                return srv
            except OSError:
                continue
        raise SystemExit("no free port in 47480-47489")


def _atomic(path: Path, obj) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj), encoding="utf-8")
    for _ in range(20):  # Windows refuses to replace a file someone is reading
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.02)
    os.replace(tmp, path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", type=Path, required=True)
    ap.add_argument("--auto-send", action="store_true")
    ap.add_argument("--approve", choices=["auto", "deny", "never"], default="auto")
    ap.add_argument("--no-http", action="store_true", help="file transport only (like Premiere on macOS)")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--bundled", default="1.0.0", help="plugin.bundled reported by /v1/hello")
    a = ap.parse_args()
    mock = Mock(a.data_dir, a.auto_send, a.approve, a.speed)
    mock.bundled = a.bundled
    threading.Thread(target=mock.file_loop, daemon=True).start()
    if a.no_http:
        print("mock SYN: file transport only at", mock.bridge, flush=True)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return
    srv = mock.serve()
    print(f"mock SYN on 127.0.0.1:{mock.port}, bridge at {mock.bridge}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        mock.stopped.set()


if __name__ == "__main__":
    main()
