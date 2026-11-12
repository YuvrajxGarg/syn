# PyInstaller build recipe for macOS (.app) and Windows (folder with .exe).
#   pyinstaller --noconfirm Syn.spec
import os
import sys

from PyInstaller.utils.hooks import collect_all

root = SPECPATH
version = open(os.path.join(root, "VERSION")).read().strip()

datas, binaries, hiddenimports = collect_all("imageio_ffmpeg")
datas += [
    (os.path.join(root, "syn", "ui"), os.path.join("syn", "ui")),
    (os.path.join(root, "VERSION"), "."),
]
# The Premiere Pro panel, installed by the setup wizard / first launch. Built before PyInstaller:
#   python premiere/build_ccx.py --version <VERSION>
ccx = os.path.join(root, "premiere", "dist", "Syn_premierepro.ccx")
if os.path.isfile(ccx):
    datas += [(ccx, "premiere")]
hiddenimports += ["certifi", "syn.premiere_install"] if os.path.isfile(os.path.join(root, "syn", "premiere_install.py")) else ["certifi"]
excludes = ["tkinter", "_tkinter", "matplotlib", "scipy", "PIL"] if sys.platform == "darwin" else ["matplotlib", "scipy", "PIL"]

a = Analysis(
    [os.path.join(root, "Syn.py")],
    pathex=[root],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    excludes=excludes,
)
pyz = PYZ(a.pure)
icon = os.path.join(root, "assets", "AppIcon.icns" if sys.platform == "darwin" else "icon.ico")

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Syn",
    console=False,
    icon=icon,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Syn")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Syn.app",
        icon=icon,
        bundle_identifier="com.yuvrajgarg.syn",
        version=version,
        info_plist={
            "CFBundleShortVersionString": version,
            "CFBundleVersion": version,
            "CFBundleDisplayName": "Syn",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "NSRequiresAquaSystemAppearance": False,
        },
    )
