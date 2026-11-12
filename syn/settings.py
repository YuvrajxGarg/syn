"""Small JSON settings store in the per-user app data folder."""

import json
import os
import sys
import threading

APP_NAME = "Syn"

DEFAULTS = {
    "mode": "fast",              # fast: compare across cameras only; thorough: every pair, lower bar
    "drift": True,               # measure clock drift on long overlaps
    "keep_camera_audio": True,   # off: camera scratch audio is disabled in the synced sequence
    "mark_low": True,            # label + marker on low-confidence clips
    "unsynced": "end",           # where unsynced clips go: "end" of the timeline or "drop" them
    "out_mode": "beside",        # "beside" the XML / footage, or "custom" -> custom_dir
    "custom_dir": None,
    "open_after": False,
    "auto_send": False,          # Premiere jobs: send back as soon as the sync is done
    "density": "comfortable",    # timeline lane height: comfortable / compact
    "auto_check": True,          # check GitHub Releases for updates
    "auto_install": True,        # download in the background, install on quit
    "welcomed": False,
    "staged_version": None,
    "last_checked": None,
    "notified_version": None,
    "clients": {},               # paired Premiere panels: token hash -> {name, host, paired, seen}
    "plugin_prompted": False,
    "last_version": None,        # set after each launch; a change means SYN just updated
}

PUBLIC_KEYS = ("mode", "drift", "keep_camera_audio", "mark_low", "unsynced", "out_mode", "custom_dir", "open_after",
               "auto_send", "density", "auto_check", "auto_install", "welcomed")
SETTABLE = set(PUBLIC_KEYS)


def app_data_dir():
    """Mac ~/Library/Application Support/Syn, Windows %APPDATA%\\Syn. SYN_HOME overrides (tests)."""
    if os.environ.get("SYN_HOME"):
        d = os.environ["SYN_HOME"]
    else:
        if sys.platform == "darwin":
            base = os.path.expanduser("~/Library/Application Support")
        elif os.name == "nt":
            base = os.environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
        else:
            base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
        d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


class Settings(object):
    def __init__(self, path=None):
        self.path = path or os.path.join(app_data_dir(), "settings.json")
        self.lock = threading.Lock()
        self.data = dict(DEFAULTS)
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self.data.update(json.load(f))
        except (OSError, ValueError):
            pass

    def get(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def set(self, key, value):
        with self.lock:
            self.data[key] = value
            tmp = self.path + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, indent=2)
                os.replace(tmp, self.path)
            except OSError:
                pass

    def public(self):
        return {k: self.data.get(k) for k in PUBLIC_KEYS}
