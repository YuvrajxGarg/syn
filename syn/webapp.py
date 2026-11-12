"""SYN's desktop window: an HTML/CSS interface (syn/ui) in a native window via pywebview.

WebKit on macOS, Edge WebView2 on Windows. Python pushes changes to the page by calling
App.on(event, payload); the page calls the methods of Api below.
"""

import json
import os
import sys
import threading

import webview
from webview.dom import DOMEventHandler

from . import __version__, media
from .bridge import Bridge, BridgeError
from .project import Project
from .settings import SETTABLE, Settings
from .updater import Updater
from .xmeml import XmlError

UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    UI_DIR = os.path.join(sys._MEIPASS, "syn", "ui")

BG = "#0b0b0c"


def _first(res):
    if not res:
        return None
    return res[0] if isinstance(res, (list, tuple)) else res


def _plugin():
    try:
        from . import premiere_install

        return premiere_install
    except Exception:
        return None


class Api(object):
    """Everything the page can call. Only methods are public: pywebview walks public attributes."""

    def __init__(self):
        self._window = None
        self._settings = Settings()
        self._projects = {}           # id -> Project
        self._order = []
        self._current = None
        self._lock = threading.Lock()
        self._plugin_state = {"installed": None, "bundled": None, "busy": False, "result": None}
        self._updater = Updater(self._settings, lambda st: self._emit("update", st))
        self._bridge = Bridge(self._settings, on_event=self._bridge_event)

    # ---- plumbing ------------------------------------------------------------------
    def _emit(self, event, payload):
        if self._window:
            try:
                self._window.evaluate_js("window.App && App.on(%s, %s)" % (json.dumps(event), json.dumps(payload)))
            except Exception:
                pass

    def _bridge_event(self, kind, payload):
        if kind == "job_new":
            job = self._bridge.get_job(payload["jobId"])
            self._add_project(job.project, select=True, job=job)
            self._front()
        elif kind == "job":
            p = self._projects.get(payload.get("projectId"))
            if p:
                self._emit("projects", self._list())
        elif kind == "progress":
            p = self._projects.get(payload["projectId"])
            if p:
                self._emit("progress", self._progress(p))
        elif kind == "clip":
            p = self._projects.get(payload["projectId"])
            if p:
                c = p.clips.get(payload["clipId"])
                if c:
                    self._emit("clip", {"pid": p.id, "clip": p.clip_public(c), "reading": payload.get("reading"),
                                        "env": None if payload.get("reading") else p.env_b64(c)})
        elif kind == "synced":
            p = self._projects.get(payload["projectId"])
            if p:
                self._emit("synced", p.public(with_env=False))
                self._emit("projects", self._list())
        elif kind == "imported":
            self._emit("toast", {"text": "“%s” is in Premiere" % (payload.get("sequenceName") or "The sequence")})
            self._emit("projects", self._list())
        elif kind == "pair":
            self._emit("pair", payload)
            self._front()
        elif kind == "clients":
            self._emit("bridge", self._bridge.status())
        elif kind == "plugin":
            self._refresh_plugin()

    def _front(self):
        w = self._window
        if not w:
            return
        try:
            w.restore()
        except Exception:
            pass
        try:
            w.show()
        except Exception:
            pass

    def _add_project(self, p, select=True, job=None):
        with self._lock:
            self._projects[p.id] = p
            if p.id not in self._order:
                self._order.append(p.id)
            p._job = job.id if job else None
            if select:
                self._current = p.id
        self._emit("projects", self._list())
        if select:
            self._emit("project", p.public(with_env=True))

    def _progress(self, p):
        return {"pid": p.id, "state": p.state, "stage": p.stage, "progress": p.progress}

    def _list(self):
        out = []
        for pid in self._order:
            p = self._projects[pid]
            job = self._bridge.jobs.get(getattr(p, "_job", None) or "")
            n = len(p.clips)
            synced = sum(1 for c in p.clips.values() if c.start is not None)
            out.append({"id": p.id, "name": p.name, "kind": p.kind, "state": p.state, "progress": p.progress,
                        "clips": n, "synced": synced, "overall": p.overall, "premiere": bool(job),
                        "job_state": job.state if job else None, "imported": bool(job and job.imported),
                        "output": p.output})
        return out

    def _project(self, pid):
        p = self._projects.get(pid)
        if not p:
            raise ValueError("That project is closed")
        return p

    def _job_of(self, p):
        jid = getattr(p, "_job", None)
        return self._bridge.jobs.get(jid) if jid else None

    def _refresh_plugin(self):
        mod = _plugin()
        st = self._plugin_state
        if mod:
            try:
                st["installed"] = mod.installed_version()
            except Exception:
                st["installed"] = None
            try:
                st["bundled"] = mod.bundled_version()
            except Exception:
                st["bundled"] = None
        self._emit("plugin", dict(st))
        return dict(st)

    # ---- startup -----------------------------------------------------------------------
    def info(self):
        return {"version": __version__, "platform": sys.platform, "home": os.path.expanduser("~"),
                "ffmpeg": bool(media.find_ffmpeg()), "settings": self._settings.public(),
                "update": self._updater.state(), "bridge": self._bridge.status(), "plugin": dict(self._plugin_state),
                "has_plugin": _plugin() is not None, "projects": self._list(),
                "project": self._projects[self._current].public(with_env=True) if self._current in self._projects else None}

    def set_setting(self, key, value):
        if key in SETTABLE:
            self._settings.set(key, value)
            if key == "auto_install" and value and self._updater.phase == "available":
                threading.Thread(target=self._updater.stage_newest, daemon=True).start()
        return self._settings.public()

    # ---- opening things ---------------------------------------------------------------------
    def pick_inputs(self):
        types = ("XML or footage (*.xml;%s)" % ";".join("*" + e for e in sorted(media.MEDIA_EXTS)), "All files (*.*)")
        res = self._window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True, file_types=types)
        if res:
            self.open_paths(list(res))

    def pick_folder(self):
        res = _first(self._window.create_file_dialog(webview.FileDialog.FOLDER))
        if res:
            self.open_paths([res])

    def dropped(self, paths):
        self.open_paths(paths)

    def open_paths(self, paths):
        def go():
            files, xmls = media.collect(paths)
            if not files and not xmls:
                self._emit("toast", {"text": "No XML or footage there", "err": True})
                return
            self._emit("loading", {"text": "Reading %s…" % ("the XML" if xmls else "%d file%s" % (len(files), "" if len(files) == 1 else "s"))})
            opened = 0
            for x in xmls:
                try:
                    self._add_project(Project.from_xml(x))
                    opened += 1
                except XmlError as e:
                    self._emit("toast", {"text": str(e), "err": True})
                except Exception as e:
                    self._emit("toast", {"text": "Couldn't open %s: %s" % (os.path.basename(x), e), "err": True})
            if files:
                try:
                    self._add_project(Project.from_media(files))
                    opened += 1
                except Exception as e:
                    self._emit("toast", {"text": "Couldn't read the footage: %s" % e, "err": True})
            self._emit("loading", None)
        threading.Thread(target=go, daemon=True).start()

    def select(self, pid):
        if pid in self._projects:
            self._current = pid
            self._emit("project", self._projects[pid].public(with_env=True))

    def close_project(self, pid):
        p = self._projects.get(pid)
        if not p or p.state == "analyzing":
            return self._list()
        job = self._job_of(p)
        if job and job.state in ("queued", "review"):
            try:
                self._bridge.cancel(job.id)
            except BridgeError:
                pass
        with self._lock:
            self._projects.pop(pid, None)
            self._order = [i for i in self._order if i != pid]
            if self._current == pid:
                self._current = self._order[-1] if self._order else None
        self._emit("projects", self._list())
        self._emit("project", self._projects[self._current].public(with_env=True) if self._current else None)
        return self._list()

    # ---- syncing ------------------------------------------------------------------------------
    def sync(self, pid):
        p = self._project(pid)
        if p.state == "analyzing":
            return
        job = self._job_of(p)
        if job and job.state == "queued":
            return  # the bridge's worker will run it

        def prog(proj):
            self._emit("progress", self._progress(proj))

        def clip(c, reading=False):
            self._emit("clip", {"pid": p.id, "clip": p.clip_public(c), "reading": reading,
                                "env": None if reading else p.env_b64(c)})

        def go():
            p.state = "analyzing"
            p.progress = 0.0
            self._emit("progress", self._progress(p))
            self._emit("projects", self._list())
            try:
                res = p.analyze(mode=self._settings.get("mode") or "fast", drift=bool(self._settings.get("drift")),
                                on_progress=prog, on_clip=clip)
            except Exception as e:
                p.state, p.error = "failed", str(e)
                self._emit("progress", self._progress(p))
                self._emit("toast", {"text": "Sync failed: %s" % e, "err": True})
                self._emit("projects", self._list())
                return
            if res is None:
                self._emit("project", p.public(with_env=True))
            else:
                if job:
                    job.state = "review"
                    self._bridge.project_changed(p)
                self._emit("synced", p.public(with_env=False))
            self._emit("projects", self._list())
        threading.Thread(target=go, daemon=True).start()

    def cancel(self, pid):
        p = self._projects.get(pid)
        if p:
            p.cancel()

    def nudge(self, pid, fid, seconds):
        p = self._project(pid)
        p.set_nudge(fid, seconds)
        self._bridge.project_changed(p)
        return p.public()

    def set_excluded(self, pid, fid, excluded):
        p = self._project(pid)
        p.set_excluded(fid, bool(excluded))
        self._bridge.project_changed(p)
        return p.public()

    def mark_checked(self, pid, fid, checked):
        p = self._project(pid)
        (p.forced.add if checked else p.forced.discard)(fid)
        self._bridge.project_changed(p)
        return p.public()

    def relink(self, pid):
        p = self._project(pid)
        folder = _first(self._window.create_file_dialog(webview.FileDialog.FOLDER))
        if not folder:
            return None
        n = p.relink(folder)
        self._emit("toast", {"text": "Found %d missing file%s" % (n, "" if n == 1 else "s") if n else "None of the missing files are in that folder",
                             "err": not n})
        self._emit("project", p.public(with_env=True))
        return n

    # ---- output -------------------------------------------------------------------------------
    def _opts(self):
        s = self._settings
        return {"keep_camera_audio": bool(s.get("keep_camera_audio")), "mark_low": bool(s.get("mark_low")),
                "unsynced": s.get("unsynced") or "end"}

    def export(self, pid, ask=False):
        p = self._project(pid)
        if p.state != "review":
            return None
        out_dir = None
        if self._settings.get("out_mode") == "custom" and self._settings.get("custom_dir"):
            out_dir = self._settings.get("custom_dir")
        path = p.default_output(out_dir)
        if ask:
            res = self._window.create_file_dialog(webview.FileDialog.SAVE, directory=os.path.dirname(path),
                                                  save_filename=os.path.basename(path), file_types=("XML (*.xml)",))
            path = _first(res)
            if not path:
                return None
            if not path.lower().endswith(".xml"):
                path += ".xml"
        try:
            info = p.export(path, **self._opts())
        except Exception as e:
            self._emit("toast", {"text": "Couldn't save the XML: %s" % e, "err": True})
            return None
        if self._settings.get("open_after"):
            media.reveal(path)
        self._emit("projects", self._list())
        return info

    def send_to_premiere(self, pid):
        p = self._project(pid)
        job = self._job_of(p)
        if not job:
            return None
        try:
            pub = self._bridge.send(job.id)
        except BridgeError as e:
            self._emit("toast", {"text": e.message, "err": True})
            return None
        self._emit("projects", self._list())
        return pub

    def reveal(self, path):
        if path and os.path.exists(path):
            media.reveal(path)

    # ---- Premiere ---------------------------------------------------------------------------------
    def pair_decide(self, pair_id, allow):
        self._bridge.decide(pair_id, bool(allow))
        return self._bridge.status()

    def revoke_client(self, client_id):
        self._bridge.revoke(client_id)
        return self._bridge.status()

    def bridge_status(self):
        return self._bridge.status()

    def plugin_status(self):
        return self._refresh_plugin()

    def plugin_install(self):
        mod = _plugin()
        if not mod or self._plugin_state["busy"]:
            return dict(self._plugin_state)

        def go():
            self._plugin_state["busy"] = True
            self._emit("plugin", dict(self._plugin_state))
            try:
                self._plugin_state["result"] = mod.install()
            except Exception as e:
                self._plugin_state["result"] = "failed"
                self._emit("toast", {"text": "Couldn't install the Premiere panel: %s" % e, "err": True})
            self._plugin_state["busy"] = False
            self._refresh_plugin()
        threading.Thread(target=go, daemon=True).start()
        return dict(self._plugin_state, busy=True)

    def plugin_uninstall(self):
        mod = _plugin()
        if mod:
            try:
                mod.uninstall()
            except Exception as e:
                self._emit("toast", {"text": "Couldn't remove the Premiere panel: %s" % e, "err": True})
        return self._refresh_plugin()

    # ---- settings bits -------------------------------------------------------------------------------
    def choose_output(self):
        res = _first(self._window.create_file_dialog(webview.FileDialog.FOLDER))
        if res:
            self._settings.set("custom_dir", res)
            self._settings.set("out_mode", "custom")
        return self._settings.public()

    def cache_info(self):
        return {"bytes": media.cache_size()}

    def clear_cache(self):
        media.clear_cache()
        return {"bytes": media.cache_size()}

    # updates
    def check_updates(self):
        return self._updater.check(manual=True)

    def download_update(self):
        threading.Thread(target=self._updater.stage_newest, daemon=True).start()

    def install_update(self):
        def go():
            if self._updater.install() == "open_page":
                self.open_url(self._updater.state()["page"])
        threading.Thread(target=go, daemon=True).start()

    def open_url(self, url):
        if not url.startswith(("https://github.com/", "https://syn.pxlvzn.in", "https://pxlvzn.in")):
            return
        import webbrowser
        webbrowser.open(url)


def _after_update(api):
    """First launch of a new version: bring the Premiere panel up to the version this app carries."""
    s = api._settings
    if s.get("last_version") == __version__:
        api._refresh_plugin()
        return
    mod = _plugin()
    if mod:
        try:
            if mod.installed_version():
                mod.ensure_current()
        except Exception:
            pass
    s.set("last_version", __version__)
    api._refresh_plugin()


# ---- native window chrome -------------------------------------------------------------

def _style_mac(window):
    """Dark, transparent title bar with content running underneath (like Dwn)."""
    try:
        import AppKit
        from PyObjCTools import AppHelper

        def apply():
            w = window.native
            w.setStyleMask_(w.styleMask() | AppKit.NSWindowStyleMaskFullSizeContentView)
            w.setTitlebarAppearsTransparent_(True)
            w.setTitleVisibility_(AppKit.NSWindowTitleHidden)
            w.setAppearance_(AppKit.NSAppearance.appearanceNamed_(AppKit.NSAppearanceNameDarkAqua))
            w.setBackgroundColor_(AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(0.043, 0.043, 0.047, 1.0))
            w.setMovableByWindowBackground_(False)
            try:
                w.contentView().superview().subviews().lastObject().setBackgroundColor_(AppKit.NSColor.clearColor())
            except Exception:
                pass
            if hasattr(w, "setToolbarStyle_"):
                w.setToolbarStyle_(AppKit.NSWindowToolbarStyleUnifiedCompact)

        AppHelper.callAfter(apply)
    except Exception:
        pass


def _style_windows(window):
    """Dark title bar on Windows 10/11; caption colour matches the app on Windows 11."""
    try:
        import ctypes

        hwnd = window.native.Handle.ToInt32()
        dwm = ctypes.windll.dwmapi
        on = ctypes.c_int(1)
        for attr in (20, 19):
            if dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(on), 4) == 0:
                break
        caption = ctypes.c_int(0x000C0B0B)
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), 4)
    except Exception:
        pass


def main():
    api = Api()
    webview.settings["DRAG_REGION_DIRECT_TARGET_ONLY"] = True
    window = webview.create_window(
        "SYN", url=os.path.join(UI_DIR, "index.html"), js_api=api,
        width=1380, height=860, min_size=(1040, 640), background_color=BG, easy_drag=False,
    )
    api._window = window

    def on_drop(e):
        files = (e.get("dataTransfer") or {}).get("files") or []
        paths = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
        if paths:
            api.dropped(paths)

    def on_loaded():
        try:
            window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)
        except Exception:
            pass

    def quit_for_install():
        try:
            window.destroy()
        finally:
            t = threading.Timer(3.0, lambda: os._exit(0))
            t.daemon = True
            t.start()

    def closing():
        api._bridge.stop()
        api._updater.install_on_quit()

    api._updater.on_quit_for_install = quit_for_install
    window.events.closing += closing
    window.events.loaded += lambda: api._updater.start()
    window.events.loaded += lambda: threading.Thread(target=_after_update, args=(api,), daemon=True).start()
    api._bridge.start()

    if sys.platform == "darwin":
        window.events.before_show += lambda: _style_mac(window)
    elif os.name == "nt":
        window.events.shown += lambda: _style_windows(window)
    window.events.loaded += on_loaded
    webview.start(debug=bool(os.environ.get("SYN_DEBUG")))
    if os.name == "nt":
        # The window is closed. Leave without Python's normal shutdown: tearing down pythonnet and
        # WinForms there can crash, and a crash report keeps the process alive, which stalls the
        # update swap waiting for it to exit (the app then never reopened after an update).
        os._exit(0)


if __name__ == "__main__":
    main()
