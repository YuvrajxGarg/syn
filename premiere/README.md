# SYN for Premiere Pro

A UXP panel (Window → UXP Plugins → SYN) that hands footage to the SYN app and brings the
synced sequence back, without exporting or importing XML by hand.

- **Sync sequence** sends the open sequence. **Sync selected clips** sends whatever is
  selected in the Project panel (bins are expanded; stills and graphics are skipped).
- SYN syncs and shows confidence per clip. When you hit **Send to Premiere** in SYN, the panel
  imports `<name> (SYN)` and opens it. Your original sequence is never touched.
- Each sync shows overall confidence, a synced / low / not synced split and a clip list with
  the clips that need a look first.

Works with Premiere Pro **25.6 and later**. On 26.2+ sequences travel as FCP XML; on older
versions the panel sends the sequence's media and SYN rebuilds the timeline.

## How it talks to SYN
See `docs/premiere-bridge.md`. HTTP on `127.0.0.1:47480-47489` (paired once with Allow in SYN),
with a file mailbox in SYN's app-data `bridge/` folder as the fallback, because Premiere's UXP
blocks `http://` on macOS.

## Layout
| Path | What |
|---|---|
| `plugin/` | the panel: `manifest.json`, `index.html`, `styles.css`, `main.js`, `lib/` |
| `plugin/lib/bridge.js` | transport (HTTP + file mailbox), pairing |
| `plugin/lib/premiere.js` | Premiere API: export XML, read selection, import result |
| `plugin/lib/session.js` | connection loop, jobs, auto-import |
| `plugin/lib/view.js`, `wave.js` | UI and the JS-driven loader (UXP has no CSS animations) |
| `build_ccx.py` | builds `dist/Syn_premierepro.ccx` |
| `../syn/premiere_install.py` | silent install / update / uninstall used by the app |
| `dev/mock_syn.py` | stand-in SYN bridge for development and tests |
| `dev/preview.js` | renders the panel in a browser with fake data |

## Develop
```sh
node --test premiere/tests/plugin.test.js          # panel tests against the mock SYN
python -m unittest tests.test_premiere_install     # installer hook
python premiere/build_ccx.py                       # -> premiere/dist/Syn_premierepro.ccx
python premiere/dev/mock_syn.py --data-dir /tmp/syn --auto-send   # fake SYN for live work
```
To run the panel in Premiere while developing, load `premiere/plugin/manifest.json` in Adobe's
UXP Developer Tool (Premiere → Settings → Plugins → Enable developer mode).

## Shipping
The app build runs `build_ccx.py` and bundles the .ccx at `<app resources>/premiere/`.
SYN installs it on first launch and from Settings → Premiere via Adobe's Unified Plugin
Installer Agent, and re-installs after an app update only when the bundled panel is newer.
