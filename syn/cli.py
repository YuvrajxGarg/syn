"""SYN on the command line.

  Syn sync Interview.xml                    sync a Premiere / Resolve XML -> "Interview (SYN).xml"
  Syn sync ~/Shoot/Day1 -o day1.xml         sync a folder of footage into a new sequence
  Syn sync A001.mov ZOOM0001.WAV --json     print the confidence report as JSON
  Syn --serve                               run only the Premiere bridge (no window)
  Syn --install-premiere-plugin / --uninstall-premiere-plugin
"""

import argparse
import json
import os
import sys
import time

from . import __version__


def _bar(p, width=28):
    n = int(round(p * width))
    return "[" + "#" * n + "-" * (width - n) + "]"


def cmd_sync(a):
    from . import media
    from .project import Project
    from .settings import Settings

    st = Settings()
    if not media.find_ffmpeg():
        print("SYN needs ffmpeg to read footage.", file=sys.stderr)
        return 2
    files, xmls = media.collect(a.inputs)
    if xmls and files:
        print("Give SYN either an XML or footage, not both.", file=sys.stderr)
        return 2
    if len(xmls) > 1:
        print("One XML at a time, please.", file=sys.stderr)
        return 2
    try:
        p = Project.from_xml(xmls[0], sequence_name=a.sequence) if xmls else Project.from_media(files)
    except Exception as e:
        print("Couldn't read that: %s" % e, file=sys.stderr)
        return 2
    if not p.clips:
        print("No footage found.", file=sys.stderr)
        return 2
    quiet = a.json or not sys.stdout.isatty()

    def prog(proj):
        if not quiet:
            sys.stdout.write("\r%s %3d%%  %-40s" % (_bar(proj.progress), proj.progress * 100, proj.stage[:40]))
            sys.stdout.flush()

    t = time.time()
    p.analyze(mode=a.mode or st.get("mode") or "fast", drift=not a.no_drift, on_progress=prog)
    if not quiet:
        sys.stdout.write("\n")
    out = a.output or p.default_output(os.path.dirname(os.path.abspath(a.output)) if a.output else None)
    info = p.export(out, keep_camera_audio=not a.mute_camera_audio, mark_low=True, unsynced="end")
    rep = p.report()
    if a.json:
        print(json.dumps(dict(rep, xml=out, seconds=round(time.time() - t, 2)), indent=2))
    else:
        for c in sorted(p.clips.values(), key=lambda c: (c.start is None, c.start or 0)):
            where = ("%9.3f s" % c.start) if c.start is not None else "    —    "
            print("  %-34s %s  %-8s %3d%%%s" % (c.name[:34], where, c.status, round(c.confidence * 100),
                                                ("  " + c.error) if c.error else ""))
        print("Overall confidence %d%% · %s · %.1f s" % (round(rep["overall"] * 100), p.stage, time.time() - t))
        print("Saved %s (%d video, %d audio tracks)" % (out, info["video_tracks"], info["audio_tracks"]))
    return 0 if any(c.start is not None for c in p.clips.values()) else 1


def cmd_serve(a):
    from .bridge import Bridge
    from .settings import Settings

    b = Bridge(Settings(), auto_approve=a.auto_approve, auto_send=a.auto_send or None,
               on_event=lambda k, pl: print("%s %s" % (k, json.dumps(pl)[:200]), flush=True)).start()
    print("SYN bridge on 127.0.0.1:%s, mailbox %s" % (b.port, b.dir), flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        b.stop()
    return 0


def cmd_plugin(install):
    try:
        from . import premiere_install
    except ImportError:
        print("This build of SYN doesn't carry the Premiere panel.", file=sys.stderr)
        return 1
    try:
        if install:
            r = premiere_install.install()
            print("Premiere panel: %s" % r)
            return 0 if r in ("installed", "needs_user") else 1
        ok = premiere_install.uninstall()
        print("Premiere panel removed" if ok else "Premiere panel wasn't installed")
        return 0
    except Exception as e:
        print("Couldn't %s the Premiere panel: %s" % ("install" if install else "remove", e), file=sys.stderr)
        return 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--install-premiere-plugin" in argv:
        return cmd_plugin(True)
    if "--uninstall-premiere-plugin" in argv:
        return cmd_plugin(False)
    ap = argparse.ArgumentParser(prog="Syn", description="Sync footage by its sound.")
    ap.add_argument("--version", action="version", version="SYN " + __version__)
    ap.add_argument("--serve", action="store_true", help="run only the Premiere bridge, no window")
    ap.add_argument("--auto-approve", action="store_true", help="with --serve: accept every pairing (testing)")
    ap.add_argument("--auto-send", action="store_true", help="with --serve: send results back without review")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("sync", help="sync an XML or footage")
    s.add_argument("inputs", nargs="+", help="a Final Cut Pro 7 XML, or footage files/folders")
    s.add_argument("-o", "--output", help="where to save the synced XML")
    s.add_argument("--sequence", help="which sequence in the XML (default: the one with the most clips)")
    s.add_argument("--mode", choices=["fast", "thorough"])
    s.add_argument("--no-drift", action="store_true", help="skip the clock drift check")
    s.add_argument("--mute-camera-audio", action="store_true", help="turn off camera scratch audio when a recorder is synced")
    s.add_argument("--json", action="store_true", help="print the confidence report as JSON")
    a = ap.parse_args(argv)
    if a.serve:
        return cmd_serve(a)
    if a.cmd == "sync":
        return cmd_sync(a)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
