# SYN ↔ Premiere bridge contract (v1)

Naming: app is `Syn.app` / `Syn.exe`, app-data folder `Syn`, product name SYN.

Owner: "Tie SYN into one workflow" thread. Implemented by the app (server side) and the
Premiere plugin (client side). Change it only by agreement; bump `api` on breaking changes.
When the syn repo exists this file moves to `docs/premiere-bridge.md` there.

## 1. Transport
- The SYN app runs an HTTP + WebSocket server on **127.0.0.1 only**, port **47480**
  (fallback 47481–47489 if taken). It runs whenever SYN is open.
- The plugin finds SYN by calling `GET /v1/hello` on 47480..47489 in order.
- The server **rejects any request whose `Origin` is an http(s) web origin** (blocks web
  pages from driving SYN). No Origin and `Origin: null` are accepted.
- The plugin is UXP only (Premiere 25.6+, id `in.pxlvzn.syn`, ships as `Syn_premierepro.ccx`).
  Premiere's UXP may block `http://` on macOS, so the app also serves the **file transport**
  (section 4b). The plugin tries HTTP first and falls back to files automatically.
- JSON in and out, UTF-8. Errors: `{"error": {"code": "...", "message": "..."}}` with 4xx/5xx.

## 2. Handshake and pairing
- `GET /v1/hello` (no auth) → `{"app":"Syn","version":"1.0.0","api":1,"platform":"mac|windows","plugin":{"bundled":"1.0.0"}}`
- `POST /v1/pair` `{"client":"premiere","clientVersion":"1.0.0","hostVersion":"25.6"}` → `202 {"pairId":"..."}`.
  SYN shows "Premiere Pro wants to connect · Allow / Deny".
- `GET /v1/pair/{pairId}` → `{"status":"pending|approved|denied","token":"..."}` (token only when approved).
- The plugin stores the token (UXP secureStorage / CEP localStorage). Every other call sends
  `Authorization: Bearer <token>`. 401 → plugin re-pairs. SYN can list/revoke paired clients in Settings.
- Version check: if `clientVersion` < `plugin.bundled`, SYN shows "Update Premiere plugin"
  and the plugin shows an "Update available" banner. Both keep working (api still 1).

## 3. Sync jobs (Premiere → SYN)
`POST /v1/jobs`
```json
{
  "source": {"kind": "xml", "path": "/abs/path/seq.xml"},   // or {"kind":"xml","xml":"<xmeml…>"} inline
  "sequenceName": "Interview day 1",
  "projectPath": "/abs/path/project.prproj",                // informational
  "options": {"mode": "auto"}                                // reserved; SYN UI owns sync settings
}
```
→ `201 {"jobId":"..."}`. SYN brings its window to the front showing the job.

- XML is **FCP7 XML (xmeml)**, what Premiere exports/imports natively. Media stays where it
  is; SYN reads media by the `pathurl`s in the XML and never moves or copies footage.
- **Media source** (bin selections, and Premiere 25.6–26.1 which has no XML export API):
  `{"kind":"media","items":[{"path":"/abs/A001_C002.mov","name":"A001_C002.mov","bin":"Day 1/Cam A"}]}`.
  SYN builds the sequence itself (frame rate/size from the first video clip or its setting);
  `bin` helps group clips by camera. The output XML references the same media paths.
- The plugin exports the active sequence (or selected bins' clips wrapped as a sequence) to
  its own temp folder, then sends the path. Inline `xml` is the fallback if paths are a problem.

`GET /v1/jobs/{id}` →
```json
{
  "id": "...", "state": "queued|analyzing|review|done|failed|cancelled",
  "createdAt": 1794489377919, "importedAt": null,   // unix ms; importedAt set by POST …/imported
  "progress": 0.42, "stage": "Matching audio · 12 / 40 clips",
  "result": {                                   // present when state = done
    "xmlPath": "/abs/…/SYN/outbox/<id>.xml",
    "sequenceName": "Interview day 1 (SYN)",
    "confidence": {"overall": 0.93,
      "clips": [{"id": "clipitem-3", "name": "A001_C002.mov", "offsetFrames": -142,
                 "confidence": 0.97, "status": "synced|low|unsynced"}]}
  },
  "error": {"code": "...", "message": "..."}     // present when state = failed
}
```
- `review` = synced, user is checking it in SYN. The user clicks **Send to Premiere** in SYN
  → state becomes `done`. (SYN may auto-send if the user turned that on.)
- `GET /v1/jobs/{id}/result.xml` → the same XML as text (if the plugin can't read `xmlPath`).
- `POST /v1/jobs/{id}/imported` `{"sequenceName":"…"}` → plugin confirms import; SYN shows "In Premiere ✓".
- `DELETE /v1/jobs/{id}` → cancel.
- `GET /v1/jobs` → `{"jobs":[…]}` (list). Every job payload includes `"api":1`.
- Inline `xml` sources are written to app-data `inbox/` first; relative `pathurl`s resolve against the XML's folder (inline: `projectPath`'s folder).

## 3b. Panel updates
- The panel's version always equals the app's: the release build runs
  `python premiere/build_ccx.py --version ${TAG#v}`, so `plugin.bundled` = app version and every
  app update makes `ensure_current()` refresh the panel.
- `POST /v1/plugin/update` (file op `plugin.update`) → the app runs `premiere_install.install()`
  and answers `{"result":"installed"|"needs_user"}`. The panel's "Update available" banner calls it;
  if it 404s the panel shows "Update available, open Syn to update".

## 4. Events
`GET /v1/events?token=…` upgrades to a WebSocket. Messages:
`{"type":"job","job":{…same as GET /v1/jobs/{id}…}}`, `{"type":"send","jobId":"…"}` (user hit
Send to Premiere), `{"type":"bye"}` (SYN quitting). Polling `GET /v1/jobs/{id}` every 1s is a
valid fallback. Plain RFC 6455 text frames, no subprotocol.

## 4b. File transport (same messages, no HTTP)
Folder `<app data>/bridge/` (Mac `~/Library/Application Support/Syn/bridge`, Windows
`%APPDATA%\Syn\bridge`). All writes atomic (write `name.tmp`, then rename).

| File | Writer | Content |
|---|---|---|
| `hello.json` | app, on start and every 2 s | `/v1/hello` body + `"heartbeat": <unix ms>`, `"pid"`. Running = heartbeat < 6 s old. Deleted on quit (= bye). |
| `requests/<reqId>.json` | plugin | `{"op": "job.create" \| "job.cancel" \| "job.imported", "body": {…}}` |
| `responses/<reqId>.json` | app | same JSON as the HTTP route; app deletes the request after answering, plugin deletes the response after reading |
| `jobs/<jobId>.json` | app, on every job change | same body as `GET /v1/jobs/{id}` |
| `send/<jobId>.json` | app, on Send to Premiere | `{"jobId": "…"}`; plugin deletes it after importing |

No pairing over files (only the same OS user can write there). App may prune files older than a day.

## 5. Output XML rules (SYN → Premiere)
- New sequence named `<original> (SYN)`; the original sequence is never modified.
- Same frame rate/size as the source sequence. One video/audio track per camera/recorder
  (track names = device/clip-group names), clips placed at their synced offset.
- Low-confidence clips get Premiere label colour + a marker "SYN: low confidence (0.61)";
  unsynced clips go on a track named "SYN · unsynced" at the end.
- Output files live in the SYN app-data `outbox/` (Mac `~/Library/Application Support/Syn`,
  Windows `%APPDATA%\Syn`).

## 6. Installing the plugin (the app owns this)
- The plugin build output is bundled inside the app (`<app resources>/premiere/` (Syn.app / Syn.exe)).
- SYN installs/updates it itself: on first launch ("Connect Premiere" onboarding step) and
  in Settings → Premiere, and automatically after an app self-update if the bundled plugin
  is newer than the installed one. No Adobe Exchange, no manual copying.
- Windows setup wizard also offers a "Install Premiere Pro panel" checkbox (runs the same
  install routine via `Syn.exe --install-premiere-plugin`).
- `SYN --install-premiere-plugin` / `--uninstall-premiere-plugin` CLI flags exist on both OSes
  and exit 0 on success, so the installers and CI can call them.
- Plugin install uses Adobe's Unified Plugin Installer Agent (`--install`/`--remove`/`--list`, `/install` on Windows); if it's missing, the hook opens the .ccx so Creative Cloud shows its install dialog and reports `needs_user`.
- CLI flags call `syn/premiere_install.py` (written by the plugin thread). The plugin thread provides the per-OS install routine (paths/commands); the app thread
  wires it into the CLI flags and UI.
