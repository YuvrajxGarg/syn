"""Installs, updates and removes SYN's Premiere Pro panel without manual steps.

The panel ships inside the app as premiere/Syn_premierepro.ccx. Installation goes through
Adobe's Unified Plugin Installer Agent (UPIA), the same tool Creative Cloud uses, so it is
silent. If UPIA isn't there (no Creative Cloud desktop app) or refuses, we open the .ccx
with the OS, Creative Cloud shows its one-click install dialog, and we report "needs_user".

Public API (called by the app's --install-premiere-plugin / --uninstall-premiere-plugin
flags, onboarding, Settings -> Premiere and the post-update hook):

    install(ccx=None)      -> "installed" | "needs_user"
    uninstall()            -> bool
    installed_version()    -> str | None
    bundled_version(ccx=None) -> str | None
    ensure_current(ccx=None)  -> "current" | "installed" | "needs_user" | "not_installed"
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Callable, Sequence

PLUGIN_ID = "in.pxlvzn.syn"
PLUGIN_NAME = "Syn"
CCX_NAME = "Syn_premierepro.ccx"

_MAC_UPIA = Path(
    "/Library/Application Support/Adobe/Adobe Desktop Common/RemoteComponents/UPI/"
    "UnifiedPluginInstallerAgent/UnifiedPluginInstallerAgent.app/Contents/MacOS/"
    "UnifiedPluginInstallerAgent"
)
_WIN_UPIA_REL = Path(
    "Adobe/Adobe Desktop Common/RemoteComponents/UPI/UnifiedPluginInstallerAgent/"
    "UnifiedPluginInstallerAgent.exe"
)
_VERSION = re.compile(r"\b(\d+\.\d+\.\d+)\b")

Runner = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _default_run(cmd: Sequence[str]) -> "subprocess.CompletedProcess[str]":
    kwargs: dict = {"capture_output": True, "text": True, "timeout": 180, "cwd": str(Path(cmd[0]).parent)}
    if _is_windows():
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(list(cmd), **kwargs)


# Tests swap these out.
run: Runner = _default_run


def _open_with_os(path: Path) -> None:
    if _is_windows():
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["open", str(path)])


open_with_os: Callable[[Path], None] = _open_with_os


# ---- locating things ----------------------------------------------------------


def upia_path() -> Path | None:
    """Adobe's installer agent, or None when Creative Cloud isn't installed."""
    if _is_windows():
        roots = [os.environ.get("CommonProgramFiles"), os.environ.get("CommonProgramW6432"), r"C:\Program Files\Common Files"]
        for root in roots:
            if root:
                p = Path(root) / _WIN_UPIA_REL
                if p.is_file():
                    return p
        return None
    return _MAC_UPIA if _MAC_UPIA.is_file() else None


def bundled_ccx() -> Path | None:
    """The .ccx shipped with the app (PyInstaller bundle), or a dev build in the repo."""
    roots = []
    if getattr(sys, "_MEIPASS", None):
        roots.append(Path(sys._MEIPASS))  # type: ignore[attr-defined]
    exe = Path(sys.executable).resolve()
    roots += [exe.parent, exe.parent.parent / "Resources"]
    repo = Path(__file__).resolve().parent.parent
    roots += [repo, repo / "premiere" / "dist"]
    for root in roots:
        for cand in (root / "premiere" / CCX_NAME, root / CCX_NAME):
            if cand.is_file():
                return cand
    return None


def bundled_version(ccx: Path | None = None) -> str | None:
    ccx = ccx or bundled_ccx()
    if not ccx:
        return None
    try:
        with zipfile.ZipFile(ccx) as z:
            return str(json.loads(z.read("manifest.json")).get("version")) or None
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        return None


def _plugin_dirs() -> list[Path]:
    """Where Creative Cloud unpacks third-party UXP plugins (fallback for version checks)."""
    home = Path.home()
    if _is_windows():
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        common = Path(os.environ.get("CommonProgramFiles", r"C:\Program Files\Common Files"))
        return [appdata / "Adobe" / "UXP" / "Plugins" / "External", common / "Adobe" / "UXP" / "Plugins" / "External"]
    return [
        home / "Library" / "Application Support" / "Adobe" / "UXP" / "Plugins" / "External",
        Path("/Library/Application Support/Adobe/UXP/Plugins/External"),
    ]


def _flag(name: str) -> str:
    return f"/{name}" if _is_windows() else f"--{name}"


def _ok(proc: "subprocess.CompletedProcess[str]") -> bool:
    text = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    return proc.returncode == 0 and not re.search(r"\bfail(ed|ure)?\b", text, re.I)


def _vkey(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


# ---- public API ------------------------------------------------------------------


def installed_version() -> str | None:
    """Version of the installed panel, or None if it isn't installed."""
    upia = upia_path()
    if upia:
        try:
            proc = run([str(upia), _flag("list"), "all"])
            for line in (proc.stdout or "").splitlines():
                if re.search(rf"(^|\s){re.escape(PLUGIN_NAME)}(\s|$)", line) or PLUGIN_ID in line:
                    m = _VERSION.search(line)
                    if m:
                        return m.group(1)
        except (OSError, subprocess.SubprocessError):
            pass
    best: str | None = None
    for d in _plugin_dirs():
        try:
            entries = list(d.iterdir())
        except OSError:
            continue
        for entry in entries:
            if not entry.name.startswith(PLUGIN_ID):
                continue
            try:
                v = str(json.loads((entry / "manifest.json").read_text(encoding="utf-8")).get("version"))
            except (OSError, ValueError):
                m = _VERSION.search(entry.name)
                v = m.group(1) if m else ""
            if _VERSION.fullmatch(v or "") and (best is None or _vkey(v) > _vkey(best)):
                best = v
    return best


def install(ccx: Path | str | None = None) -> str:
    """Installs or updates the panel. Returns "installed" or "needs_user"."""
    path = Path(ccx) if ccx else bundled_ccx()
    if not path or not path.is_file():
        raise FileNotFoundError(f"{CCX_NAME} not found")
    upia = upia_path()
    if upia:
        try:
            if _ok(run([str(upia), _flag("install"), str(path)])):
                return "installed"
        except (OSError, subprocess.SubprocessError):
            pass
    # No silent route: Creative Cloud takes over with its own install dialog.
    open_with_os(path)
    return "needs_user"


def uninstall() -> bool:
    """Removes the panel. True if it's gone (or was never installed)."""
    upia = upia_path()
    if not upia:
        return installed_version() is None
    for name in (PLUGIN_NAME, PLUGIN_ID):
        try:
            if _ok(run([str(upia), _flag("remove"), name])):
                return True
        except (OSError, subprocess.SubprocessError):
            continue
    return installed_version() is None


def ensure_current(ccx: Path | str | None = None) -> str:
    """After an app update: install the bundled panel only if it's newer than the installed one.

    Leaves people who never installed the panel alone. Returns "current", "installed",
    "needs_user" or "not_installed".
    """
    path = Path(ccx) if ccx else bundled_ccx()
    have = installed_version()
    want = bundled_version(path) if path else None
    if have is None:
        return "not_installed"
    if not want or _vkey(want) <= _vkey(have):
        return "current"
    return install(path)


def main(argv: list[str] | None = None) -> int:
    """`python -m syn.premiere_install install|uninstall|version`; exit 0 on success."""
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else "install"
    if cmd == "install":
        result = install(args[1] if len(args) > 1 else None)
        print(result)
        return 0
    if cmd == "uninstall":
        ok = uninstall()
        print("removed" if ok else "failed")
        return 0 if ok else 1
    if cmd == "version":
        print(installed_version() or "not installed")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
