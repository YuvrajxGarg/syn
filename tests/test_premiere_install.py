"""Tests for syn/premiere_install.py and premiere/build_ccx.py (no Adobe software needed)."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "premiere"))

import build_ccx  # noqa: E402
from syn import premiere_install as pi  # noqa: E402


def proc(rc=0, out="", err=""):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=out, stderr=err)


class BuildCcxTest(unittest.TestCase):
    def test_ccx_is_a_zip_with_manifest_at_root(self):
        with tempfile.TemporaryDirectory() as d:
            out = build_ccx.build(Path(d), "2.3.4")
            self.assertEqual(out.name, "Syn_premierepro.ccx")
            with zipfile.ZipFile(out) as z:
                names = set(z.namelist())
                manifest = json.loads(z.read("manifest.json"))
            self.assertIn("index.html", names)
            self.assertIn("main.js", names)
            self.assertIn("lib/bridge.js", names)
            self.assertIn("icons/panel.png", names)
            self.assertEqual(manifest["version"], "2.3.4")
            self.assertEqual(manifest["id"], pi.PLUGIN_ID)
            self.assertEqual(manifest["host"]["app"], "premierepro")
            self.assertEqual(pi.bundled_version(out), "2.3.4")

    def test_manifest_allows_every_bridge_port(self):
        m = json.loads((ROOT / "premiere" / "plugin" / "manifest.json").read_text())
        domains = m["requiredPermissions"]["network"]["domains"]
        self.assertEqual(domains, [f"http://127.0.0.1:{p}" for p in range(47480, 47490)])
        self.assertEqual(m["requiredPermissions"]["localFileSystem"], "fullAccess")

    def test_bad_version_rejected(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(SystemExit):
            build_ccx.build(Path(d), "v1")


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ccx = build_ccx.build(Path(self.tmp.name), "1.2.0")
        self.upia = Path(self.tmp.name) / "UnifiedPluginInstallerAgent"
        self.upia.write_text("")
        self.calls: list[list[str]] = []
        self.opened: list[Path] = []
        self.responses: dict[str, subprocess.CompletedProcess] = {}
        patches = [
            mock.patch.object(pi, "run", self._run),
            mock.patch.object(pi, "open_with_os", self.opened.append),
            mock.patch.object(pi, "upia_path", lambda: self.upia),
            mock.patch.object(pi, "_plugin_dirs", lambda: [Path(self.tmp.name) / "External"]),
            mock.patch.object(pi, "_is_windows", lambda: False),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def _run(self, cmd):
        self.calls.append(list(cmd))
        return self.responses.get(cmd[1], proc())

    def test_silent_install_via_upia(self):
        self.assertEqual(pi.install(self.ccx), "installed")
        self.assertEqual(self.calls[0], [str(self.upia), "--install", str(self.ccx)])
        self.assertEqual(self.opened, [])

    def test_windows_uses_slash_flags(self):
        with mock.patch.object(pi, "_is_windows", lambda: True):
            pi.install(self.ccx)
        self.assertEqual(self.calls[0][1], "/install")

    def test_upia_failure_hands_over_to_creative_cloud(self):
        self.responses["--install"] = proc(0, "Installation failed: permission denied")
        self.assertEqual(pi.install(self.ccx), "needs_user")
        self.assertEqual(self.opened, [self.ccx])

    def test_no_creative_cloud(self):
        with mock.patch.object(pi, "upia_path", lambda: None):
            self.assertEqual(pi.install(self.ccx), "needs_user")
        self.assertEqual(self.opened, [self.ccx])

    def test_missing_ccx(self):
        with mock.patch.object(pi, "bundled_ccx", lambda: None), self.assertRaises(FileNotFoundError):
            pi.install()

    def test_installed_version_from_upia_list(self):
        self.responses["--list"] = proc(0, "Status   Name   Version\nEnabled  Lut Helper  3.0.0\nEnabled  Syn  1.1.0\n")
        self.assertEqual(pi.installed_version(), "1.1.0")

    def test_installed_version_from_plugin_folder(self):
        self.responses["--list"] = proc(0, "nothing here\n")
        d = Path(self.tmp.name) / "External" / f"{pi.PLUGIN_ID}_1.0.3"
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(json.dumps({"version": "1.0.3"}))
        self.assertEqual(pi.installed_version(), "1.0.3")

    def test_not_installed(self):
        self.responses["--list"] = proc(0, "Enabled  Other  1.0.0\n")
        self.assertIsNone(pi.installed_version())

    def test_ensure_current_updates_only_older_installs(self):
        self.responses["--list"] = proc(0, "Enabled  Syn  1.0.0\n")
        self.assertEqual(pi.ensure_current(self.ccx), "installed")
        self.assertIn("--install", [c[1] for c in self.calls])

        self.calls.clear()
        self.responses["--list"] = proc(0, "Enabled  Syn  1.2.0\n")
        self.assertEqual(pi.ensure_current(self.ccx), "current")
        self.assertNotIn("--install", [c[1] for c in self.calls])

        self.responses["--list"] = proc(0, "\n")
        self.assertEqual(pi.ensure_current(self.ccx), "not_installed")

    def test_uninstall(self):
        self.assertTrue(pi.uninstall())
        self.assertEqual(self.calls[0], [str(self.upia), "--remove", "Syn"])

    def test_cli_exit_codes(self):
        self.assertEqual(pi.main(["install", str(self.ccx)]), 0)
        self.assertEqual(pi.main(["uninstall"]), 0)
        self.responses["--remove"] = proc(1, "failed")
        self.responses["--list"] = proc(0, "Enabled  Syn  1.0.0\n")
        self.assertEqual(pi.main(["uninstall"]), 1)


if __name__ == "__main__":
    unittest.main()
