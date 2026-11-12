"""The Premiere bridge: how the SYN panel inside Premiere Pro talks to this app.

Implements docs/premiere-bridge.md (api 1):
- HTTP + WebSocket on 127.0.0.1:47480 (47481-47489 if taken), with pairing and bearer tokens
- the file mailbox in <app data>/bridge for Premiere builds whose UXP blocks http://

Jobs run one at a time on a worker thread. The window watches them (on_event) and the
user reviews and sends them back; headless (`Syn --serve`) can auto-send.
"""

import base64
import hashlib
import json
import os
import secrets
import socket
import socketserver
import struct
import sys
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__, xmeml
from .project import Project
from .settings import app_data_dir

API = 1
PORTS = range(47480, 47490)
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC11B85"
HEARTBEAT = 2.0
PRUNE_AFTER = 24 * 3600


class BridgeError(Exception):
    def __init__(self, code, message, status=400):
        Exception.__init__(self, message)
        self.code, self.message, self.status = code, message, status


def _atomic(path, obj):
    tmp = path + ".tmp"
    data = json.dumps(obj).encode("utf-8") if not isinstance(obj, bytes) else obj
    with open(tmp, "wb") as f:
        f.write(data)
    for _ in range(25):  # Windows won't replace a file someone has open for a moment
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.02)
    os.replace(tmp, path)


def _hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _plugin_bundled():
    try:
        from . import premiere_install

        return premiere_install.bundled_version()
    except Exception:
        return None


class Job(object):
    def __init__(self, project, body):
        self.id = uuid.uuid4().hex[:12]
        self.project = project
        self.body = body
        self.state = "queued"
        self.created = int(time.time() * 1000)
        self.imported = None
        self.imported_as = None
        self.sequence_name = body.get("sequenceName") or project.name
        self.result = None
        self.error = None
        self.client = None

    def public(self):
        p = self.project
        out = {"api": API, "id": self.id, "state": self.state, "progress": p.progress if self.state != "queued" else 0.0,
               "stage": "Waiting" if self.state == "queued" else (p.stage or ""),
               "sequenceName": self.sequence_name, "createdAt": self.created, "importedAt": self.imported,
               "projectId": p.id}
        if self.imported_as:
            out["importedAs"] = self.imported_as
        if self.state in ("review", "done") and p.state == "review":
            res = {"sequenceName": "%s (SYN)" % self.sequence_name, "confidence": p.report()}
            if self.result:
                res.update(self.result)
            out["result"] = res
        if self.error:
            out["error"] = self.error
        return out


class Bridge(object):
    def __init__(self, settings, on_event=None, auto_approve=False, auto_send=None, http=True, files=True,
                 data_dir=None):
        self.settings = settings
        self.on_event = on_event or (lambda kind, payload: None)
        self.auto_approve = auto_approve
        self._auto_send = auto_send
        self.data = data_dir or app_data_dir()
        self.dir = os.path.join(self.data, "bridge")
        self.inbox = os.path.join(self.data, "inbox")
        self.outbox = os.path.join(self.data, "outbox")
        for d in ("requests", "responses", "jobs", "send"):
            os.makedirs(os.path.join(self.dir, d), exist_ok=True)
        os.makedirs(self.inbox, exist_ok=True)
        os.makedirs(self.outbox, exist_ok=True)
        self.jobs = {}
        self.pairs = {}
        self.lock = threading.RLock()
        self.port = None
        self.server = None
        self.sockets = {}             # websocket -> send lock
        self.stopped = threading.Event()
        self.queue = []
        self.wake = threading.Event()
        self.use_http, self.use_files = http, files
        self.export_opts = lambda: {"keep_camera_audio": bool(settings.get("keep_camera_audio")),
                                    "mark_low": bool(settings.get("mark_low")),
                                    "unsynced": settings.get("unsynced") or "end"}

    # ---- lifecycle -----------------------------------------------------------------
    def start(self):
        if self.use_http:
            for port in PORTS:
                try:
                    srv = _Server(("127.0.0.1", port), _Handler)
                except OSError:
                    continue
                srv.bridge = self
                self.server, self.port = srv, port
                threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.25}, daemon=True).start()
                break
        if self.use_files:
            threading.Thread(target=self._file_loop, daemon=True).start()
        threading.Thread(target=self._worker, daemon=True).start()
        return self

    def stop(self):
        self.stopped.set()
        self.broadcast({"type": "bye"})
        for s in list(self.sockets):
            try:
                s.close()
            except Exception:
                pass
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
        try:
            os.remove(os.path.join(self.dir, "hello.json"))
        except OSError:
            pass
        self.wake.set()

    @property
    def auto_send(self):
        return self._auto_send if self._auto_send is not None else bool(self.settings.get("auto_send"))

    def hello(self):
        return {"app": "Syn", "version": __version__, "api": API,
                "platform": "mac" if sys.platform == "darwin" else ("windows" if os.name == "nt" else "linux"),
                "plugin": {"bundled": _plugin_bundled()}}

    def status(self):
        """For the window: is Premiere connected?"""
        clients = self.settings.get("clients") or {}
        now = time.time()
        live = [c for c in clients.values() if now - (c.get("seen") or 0) < 30]
        return {"port": self.port, "clients": [dict(c, id=k) for k, c in clients.items()],
                "connected": bool(live) or bool(self.sockets) or self._recent_file_client(),
                "pending": [dict(p, id=k) for k, p in self.pairs.items() if p["status"] == "pending"]}

    def _recent_file_client(self):
        return time.time() - getattr(self, "_file_seen", 0) < 30

    # ---- pairing -------------------------------------------------------------------
    def pair_request(self, body):
        pid = uuid.uuid4().hex[:10]
        info = {"status": "pending", "client": str(body.get("client") or "premiere")[:40],
                "clientVersion": str(body.get("clientVersion") or "")[:20],
                "hostVersion": str(body.get("hostVersion") or "")[:20], "at": time.time()}
        with self.lock:
            # one pending prompt per client kind is enough
            for k, p in list(self.pairs.items()):
                if p["status"] == "pending" and p["client"] == info["client"]:
                    p["status"] = "denied"
            self.pairs[pid] = info
        if self.auto_approve:
            self.decide(pid, True)
        else:
            self.on_event("pair", dict(info, id=pid))
        return {"pairId": pid}

    def decide(self, pid, allow):
        with self.lock:
            p = self.pairs.get(pid)
            if not p or p["status"] != "pending":
                return False
            if allow:
                token = secrets.token_urlsafe(32)
                clients = dict(self.settings.get("clients") or {})
                clients[_hash(token)] = {"name": "Premiere Pro %s" % p["hostVersion"] if p["hostVersion"] else "Premiere Pro",
                                         "client": p["client"], "version": p["clientVersion"],
                                         "paired": time.time(), "seen": time.time()}
                self.settings.set("clients", clients)
                p["status"], p["token"] = "approved", token
            else:
                p["status"] = "denied"
        self.on_event("clients", self.status())
        return True

    def pair_status(self, pid):
        p = self.pairs.get(pid)
        if not p:
            raise BridgeError("not_found", "No such pairing request", 404)
        out = {"status": p["status"]}
        if p["status"] == "approved":
            out["token"] = p["token"]
        return out

    def revoke(self, client_id):
        clients = dict(self.settings.get("clients") or {})
        clients.pop(client_id, None)
        self.settings.set("clients", clients)
        self.on_event("clients", self.status())

    def check_token(self, token):
        if not token:
            return None
        h = _hash(token)
        clients = self.settings.get("clients") or {}
        c = clients.get(h)
        if not c:
            return None
        if time.time() - (c.get("seen") or 0) > 10:
            clients = dict(clients)
            clients[h] = dict(c, seen=time.time())
            self.settings.set("clients", clients)
            if time.time() - (c.get("seen") or 0) > 30:
                self.on_event("clients", self.status())
        return c

    # ---- jobs ----------------------------------------------------------------------------
    def create_job(self, body):
        src = body.get("source") or {}
        kind = src.get("kind")
        seq_name = body.get("sequenceName")
        project_dir = os.path.dirname(body["projectPath"]) if body.get("projectPath") else None
        try:
            if kind == "xml":
                if src.get("path"):
                    path = src["path"]
                    if not os.path.isfile(path):
                        raise BridgeError("not_found", "The XML isn't there: %s" % path)
                    project = Project.from_xml(path, sequence_name=seq_name)
                elif src.get("xml"):
                    path = os.path.join(self.inbox, "%s.xml" % uuid.uuid4().hex[:12])
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(src["xml"])
                    project = Project.from_xml(path, base_dir=project_dir, sequence_name=seq_name)
                else:
                    raise BridgeError("bad_source", "source needs a path or xml")
            elif kind == "media":
                items = [i for i in (src.get("items") or []) if isinstance(i, dict) and i.get("path")]
                if not items:
                    raise BridgeError("bad_source", "source.items is empty")
                project = Project.from_media(items, name=seq_name)
            else:
                raise BridgeError("bad_source", "source.kind must be xml or media")
        except xmeml.XmlError as e:
            raise BridgeError("bad_xml", str(e))
        if seq_name:
            project.name = seq_name
        job = Job(project, body)
        with self.lock:
            self.jobs[job.id] = job
            self.queue.append(job.id)
        self.wake.set()
        self._job_changed(job)
        self.on_event("job_new", {"jobId": job.id, "projectId": project.id})
        return {"jobId": job.id}

    def get_job(self, jid):
        job = self.jobs.get(jid)
        if not job:
            raise BridgeError("not_found", "No such job", 404)
        return job

    def cancel(self, jid):
        job = self.get_job(jid)
        if job.state in ("queued", "analyzing"):
            job.project.cancel()
            job.state = "cancelled"
            self._job_changed(job)
        elif job.state == "review":
            job.state = "cancelled"
            self._job_changed(job)
        return {}

    def imported(self, jid, body):
        job = self.get_job(jid)
        job.imported = int(time.time() * 1000)
        job.imported_as = body.get("sequenceName")
        self._job_changed(job)
        self.on_event("imported", {"jobId": jid, "sequenceName": job.imported_as, "projectId": job.project.id})
        return {}

    def plugin_update(self):
        try:
            from . import premiere_install
        except ImportError:
            raise BridgeError("no_plugin", "This build of SYN doesn't carry the Premiere panel", 404)
        try:
            result = premiere_install.install()
        except Exception as e:
            raise BridgeError("install_failed", str(e), 500)
        self.on_event("plugin", {"result": result})
        return {"result": result}

    def job_for_project(self, project_id):
        for j in self.jobs.values():
            if j.project.id == project_id:
                return j
        return None

    def send(self, jid):
        """The user clicked Send to Premiere: write the synced XML to the outbox and tell the panel."""
        job = self.get_job(jid)
        if job.project.state != "review":
            raise BridgeError("not_ready", "This job isn't synced yet")
        path = os.path.join(self.outbox, "%s.xml" % job.id)
        job.project.name = job.sequence_name
        info = job.project.export(path, **self.export_opts())
        job.result = {"xmlPath": path, "sequenceName": info["name"]}
        job.state = "done"
        self._job_changed(job)
        if self.use_files:
            _atomic(os.path.join(self.dir, "send", "%s.json" % job.id), {"jobId": job.id})
        self.broadcast({"type": "send", "jobId": job.id})
        return job.public()

    def project_changed(self, project):
        """The window nudged or re-synced a job's project: refresh what the panel sees."""
        job = self.job_for_project(project.id)
        if job:
            self._job_changed(job)

    def _job_changed(self, job):
        pub = job.public()
        if self.use_files:
            try:
                _atomic(os.path.join(self.dir, "jobs", "%s.json" % job.id), pub)
            except OSError:
                pass
        self.broadcast({"type": "job", "job": pub})
        self.on_event("job", pub)

    def _worker(self):
        last = [0.0]
        while not self.stopped.is_set():
            self.wake.wait(1.0)
            self.wake.clear()
            while self.queue and not self.stopped.is_set():
                with self.lock:
                    jid = self.queue.pop(0)
                job = self.jobs.get(jid)
                if not job or job.state != "queued":
                    continue
                job.state = "analyzing"
                self._job_changed(job)

                def prog(p, job=job):
                    now = time.time()
                    if now - last[0] > 0.25:
                        last[0] = now
                        self._job_changed(job)
                    self.on_event("progress", {"projectId": p.id})

                def clip(c, reading=False, job=job):
                    self.on_event("clip", {"projectId": job.project.id, "clipId": c.id, "reading": reading})

                try:
                    res = job.project.analyze(mode=self.settings.get("mode") or "fast",
                                              drift=bool(self.settings.get("drift")), on_progress=prog, on_clip=clip)
                except Exception as e:
                    job.state = "failed"
                    job.error = {"code": "sync_failed", "message": str(e)}
                    self._job_changed(job)
                    continue
                if job.state == "cancelled" or res is None:
                    job.state = "cancelled"
                    self._job_changed(job)
                    continue
                job.state = "review"
                self._job_changed(job)
                self.on_event("synced", {"jobId": job.id, "projectId": job.project.id})
                if self.auto_send:
                    try:
                        self.send(job.id)
                    except Exception as e:
                        job.error = {"code": "send_failed", "message": str(e)}
                        self._job_changed(job)

    # ---- websocket ------------------------------------------------------------------------
    def broadcast(self, msg):
        data = _ws_frame(json.dumps(msg).encode("utf-8"))
        for s, lock in list(self.sockets.items()):
            try:
                with lock:
                    s.sendall(data)
            except Exception:
                self.sockets.pop(s, None)

    # ---- file mailbox ---------------------------------------------------------------------
    def _file_loop(self):
        last_hello = 0.0
        last_prune = 0.0
        while not self.stopped.is_set():
            now = time.time()
            if now - last_hello >= HEARTBEAT:
                last_hello = now
                try:
                    _atomic(os.path.join(self.dir, "hello.json"),
                            dict(self.hello(), heartbeat=int(now * 1000), pid=os.getpid()))
                except OSError:
                    pass
            reqdir = os.path.join(self.dir, "requests")
            try:
                names = sorted(n for n in os.listdir(reqdir) if n.endswith(".json"))
            except OSError:
                names = []
            for name in names:
                path = os.path.join(reqdir, name)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        msg = json.load(f)
                except (OSError, ValueError):
                    continue
                self._file_seen = time.time()
                resp = self.handle_op(msg.get("op"), msg.get("body") or {})
                try:
                    _atomic(os.path.join(self.dir, "responses", name), resp)
                    os.remove(path)
                except OSError:
                    pass
            if now - last_prune > 600:
                last_prune = now
                self._prune()
            self.stopped.wait(0.15)
        try:
            os.remove(os.path.join(self.dir, "hello.json"))
        except OSError:
            pass

    def handle_op(self, op, body):
        try:
            if op == "job.create":
                return self.create_job(body)
            if op == "job.cancel":
                return self.cancel(body.get("jobId", ""))
            if op == "job.imported":
                return self.imported(body.get("jobId", ""), body)
            if op == "plugin.update":
                return self.plugin_update()
            raise BridgeError("bad_op", "Unknown op %s" % op)
        except BridgeError as e:
            return {"error": {"code": e.code, "message": e.message}}
        except Exception as e:
            return {"error": {"code": "internal", "message": str(e)}}

    def _prune(self):
        cutoff = time.time() - PRUNE_AFTER
        for sub in ("responses", "jobs", "send", "requests"):
            d = os.path.join(self.dir, sub)
            try:
                for n in os.listdir(d):
                    p = os.path.join(d, n)
                    if os.path.getmtime(p) < cutoff:
                        os.remove(p)
            except OSError:
                pass
        for d in (self.inbox, self.outbox):
            try:
                for n in os.listdir(d):
                    p = os.path.join(d, n)
                    if os.path.getmtime(p) < time.time() - 30 * 86400:
                        os.remove(p)
            except OSError:
                pass


# ---- HTTP --------------------------------------------------------------------------------

class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def server_bind(self):
        if os.name == "nt":
            # Windows lets two servers bind the same port without this
            self.socket.setsockopt(socket.SOL_SOCKET, getattr(socket, "SO_EXCLUSIVEADDRUSE", 0), 1)
        # HTTPServer.server_bind also calls socket.getfqdn(), a reverse DNS lookup that can
        # stall for many seconds on some Macs. We only ever listen on 127.0.0.1.
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name, self.server_port = host, port


def _ws_frame(payload, opcode=1):
    head = bytes([0x80 | opcode])
    n = len(payload)
    if n < 126:
        head += bytes([n])
    elif n < 65536:
        head += bytes([126]) + struct.pack(">H", n)
    else:
        head += bytes([127]) + struct.pack(">Q", n)
    return head + payload


def _ws_read(sock):
    """One frame from a client: (opcode, payload) or None when the socket closes."""
    def recv(n):
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf
    h = recv(2)
    if h is None:
        return None
    opcode = h[0] & 0x0F
    masked = h[1] & 0x80
    n = h[1] & 0x7F
    if n == 126:
        ext = recv(2)
        if ext is None:
            return None
        n = struct.unpack(">H", ext)[0]
    elif n == 127:
        ext = recv(8)
        if ext is None:
            return None
        n = struct.unpack(">Q", ext)[0]
    if n > 1 << 20:
        return None
    mask = recv(4) if masked else b"\0\0\0\0"
    data = recv(n) if n else b""
    if mask is None or data is None:
        return None
    data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return opcode, data


class _Handler(BaseHTTPRequestHandler):
    server_version = "Syn"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    @property
    def bridge(self):
        return self.server.bridge

    def _send(self, code, obj=None, text=None, ctype=None):
        data = (text if text is not None else json.dumps(obj if obj is not None else {})).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype or ("application/xml; charset=utf-8" if text is not None else "application/json"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _error(self, e):
        self._send(e.status, {"error": {"code": e.code, "message": e.message}})

    def _guard(self):
        origin = self.headers.get("Origin")
        if origin and origin != "null" and origin.lower().startswith(("http://", "https://")):
            self._error(BridgeError("origin", "Web pages can't talk to SYN", 403))
            return False
        host = (self.headers.get("Host") or "").split(":")[0].strip("[]").lower()
        if host and host not in ("127.0.0.1", "localhost", "::1"):
            # a web page that rebinds a domain to 127.0.0.1 still sends its own Host
            self._error(BridgeError("host", "Unexpected Host", 403))
            return False
        return True

    def _token(self):
        auth = self.headers.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        return (q.get("token") or [None])[0]

    def _authed(self):
        if self.bridge.check_token(self._token()):
            return True
        self._error(BridgeError("unauthorized", "Pair with SYN first", 401))
        return False

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 64 << 20:
            raise BridgeError("too_large", "Request too large", 413)
        raw = self.rfile.read(n) if n else b""
        if not raw:
            return {}
        try:
            obj = json.loads(raw.decode("utf-8"))
        except ValueError:
            raise BridgeError("bad_json", "Body isn't JSON")
        if not isinstance(obj, dict):
            raise BridgeError("bad_json", "Body must be a JSON object")
        return obj

    def _route(self):
        return urllib.parse.urlparse(self.path).path.rstrip("/")

    def do_OPTIONS(self):
        if not self._guard():
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "null")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if not self._guard():
            return
        p = self._route()
        b = self.bridge
        try:
            if p == "/v1/hello":
                return self._send(200, b.hello())
            if p.startswith("/v1/pair/"):
                return self._send(200, b.pair_status(p.split("/")[-1]))
            if p == "/v1/events":
                return self._websocket()
            if not self._authed():
                return
            if p == "/v1/jobs":
                jobs = sorted(b.jobs.values(), key=lambda j: j.created)
                return self._send(200, {"jobs": [j.public() for j in jobs]})
            parts = p.split("/")
            if len(parts) >= 4 and parts[2] == "jobs":
                job = b.get_job(parts[3])
                if len(parts) == 5 and parts[4] == "result.xml":
                    if not job.result or not os.path.isfile(job.result.get("xmlPath", "")):
                        raise BridgeError("not_ready", "No result yet", 409)
                    with open(job.result["xmlPath"], "r", encoding="utf-8") as f:
                        return self._send(200, text=f.read())
                if len(parts) == 4:
                    return self._send(200, job.public())
            raise BridgeError("not_found", "Nothing at %s" % p, 404)
        except BridgeError as e:
            self._error(e)

    def do_POST(self):
        if not self._guard():
            return
        p = self._route()
        b = self.bridge
        try:
            if p == "/v1/pair":
                return self._send(202, b.pair_request(self._body()))
            if not self._authed():
                return
            if p == "/v1/jobs":
                return self._send(201, b.create_job(self._body()))
            if p == "/v1/plugin/update":
                return self._send(200, b.plugin_update())
            parts = p.split("/")
            if len(parts) == 5 and parts[2] == "jobs" and parts[4] == "imported":
                return self._send(200, b.imported(parts[3], self._body()))
            raise BridgeError("not_found", "Nothing at %s" % p, 404)
        except BridgeError as e:
            self._error(e)

    def do_DELETE(self):
        if not self._guard() or not self._authed():
            return
        parts = self._route().split("/")
        try:
            if len(parts) == 4 and parts[2] == "jobs":
                return self._send(200, self.bridge.cancel(parts[3]))
            raise BridgeError("not_found", "Nothing there", 404)
        except BridgeError as e:
            self._error(e)

    def _websocket(self):
        if (self.headers.get("Upgrade") or "").lower() != "websocket" or not self.headers.get("Sec-WebSocket-Key"):
            raise BridgeError("upgrade", "Expected a WebSocket upgrade", 426)
        if not self.bridge.check_token(self._token()):
            raise BridgeError("unauthorized", "Pair with SYN first", 401)
        accept = base64.b64encode(hashlib.sha1((self.headers["Sec-WebSocket-Key"] + WS_GUID).encode("ascii")).digest())
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept.decode("ascii"))
        self.end_headers()
        self.wfile.flush()
        sock = self.connection
        lock = threading.Lock()
        b = self.bridge
        b.sockets[sock] = lock
        b.on_event("clients", b.status())
        try:
            # catch the panel up on every job it might be waiting for
            for job in list(b.jobs.values()):
                with lock:
                    sock.sendall(_ws_frame(json.dumps({"type": "job", "job": job.public()}).encode("utf-8")))
            while not b.stopped.is_set():
                fr = _ws_read(sock)
                if fr is None:
                    break
                op, data = fr
                if op == 8:   # close
                    with lock:
                        sock.sendall(_ws_frame(b"", 8))
                    break
                if op == 9:   # ping
                    with lock:
                        sock.sendall(_ws_frame(data, 10))
        except OSError:
            pass
        finally:
            b.sockets.pop(sock, None)
            self.close_connection = True
            b.on_event("clients", b.status())
