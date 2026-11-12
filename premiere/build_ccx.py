"""Packages the Premiere panel as a .ccx (a plain zip with manifest.json at the root).

UXP .ccx files need no signing. The SYN app bundles the result under
<app resources>/premiere/ and installs it with syn/premiere_install.py.

    python premiere/build_ccx.py                 # -> premiere/dist/Syn_premierepro.ccx
    python premiere/build_ccx.py --version 1.2.0 # stamp a version into the manifest
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE / "plugin"
CCX_NAME = "Syn_premierepro.ccx"
SKIP = {".DS_Store", "Thumbs.db"}


def build(out_dir: Path, version: str | None = None) -> Path:
    manifest = json.loads((PLUGIN / "manifest.json").read_text(encoding="utf-8"))
    if version:
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise SystemExit(f"version must look like 1.2.3, got {version!r}")
        manifest["version"] = version
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / CCX_NAME
    tmp = out.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
        for path in sorted(PLUGIN.rglob("*")):
            rel = path.relative_to(PLUGIN).as_posix()
            if path.is_dir() or path.name in SKIP or rel == "manifest.json":
                continue
            z.write(path, rel)
    tmp.replace(out)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=HERE / "dist")
    ap.add_argument("--version")
    args = ap.parse_args(argv)
    out = build(args.out, args.version)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
