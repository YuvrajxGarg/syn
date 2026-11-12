// The panel's brain: keeps the connection alive, sends work to SYN, follows jobs and
// imports results. UI-free so it can be tested in Node.

"use strict";

const { BridgeError } = require("./bridge.js");

const ACTIVE = new Set(["queued", "analyzing", "review"]);

class Session {
  /**
   * bridge   - Bridge
   * host     - PremiereHost
   * prefs    - { load() -> object, save(object) }   (plugin-data JSON)
   * readText - (path) => Promise<string>            (reads result.xmlPath)
   * writeTemp- (name, text) => Promise<path>        (when the XML only comes over HTTP)
   */
  constructor({ bridge, host, prefs, readText, writeTemp, now = () => Date.now() }) {
    this.bridge = bridge;
    this.host = host;
    this.prefs = prefs;
    this.readText = readText;
    this.writeTemp = writeTemp;
    this.now = now;
    this.listeners = new Set();
    this.state = {
      conn: "searching", // searching | offline | pair | pairing | denied | connected | mismatch
      mode: "offline",
      hello: null,
      updateAvailable: false,
      context: null,
      jobs: [], // newest first: job payloads + {local: {...}}
      busy: null, // short text while sending / importing
      notice: null, // {kind: "error"|"ok"|"info", text}
      autoImport: true,
    };
    this._seen = new Map(); // jobId -> last state seen (so "done" transitions can auto-import)
    this._imported = new Set();
    this._mine = new Set(); // jobs this panel created
    this._importing = new Set();
    this._lastConnectTry = 0;
    this._firstList = true;
  }

  on(fn) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  _emit(patch) {
    Object.assign(this.state, patch || {});
    for (const fn of this.listeners) {
      try {
        fn(this.state);
      } catch (e) {
        /* a broken listener mustn't stop the loop */
      }
    }
  }

  async init() {
    try {
      const p = (await this.prefs.load()) || {};
      this._imported = new Set(p.imported || []);
      this.state.autoImport = p.autoImport !== false;
    } catch (e) {
      /* first run */
    }
    await this.bridge.loadToken();
  }

  async _savePrefs() {
    try {
      await this.prefs.save({ imported: Array.from(this._imported).slice(-200), autoImport: this.state.autoImport });
    } catch (e) {
      /* non-fatal */
    }
  }

  setAutoImport(on) {
    this._emit({ autoImport: !!on });
    this._savePrefs();
  }

  // ---- connection ---------------------------------------------------------

  async ensureConnected(force) {
    if (this.state.conn === "connected" && this.bridge.mode !== "offline" && !force) return true;
    if (!force && this.now() - this._lastConnectTry < 2500) return false;
    this._lastConnectTry = this.now();
    const { mode, hello } = await this.bridge.connect();
    if (mode === "offline") {
      this._emit({ conn: "offline", mode, hello: null });
      return false;
    }
    if (this.bridge.apiMismatch()) {
      this._emit({ conn: "mismatch", mode, hello });
      return false;
    }
    const patch = { mode, hello, updateAvailable: this.bridge.updateAvailable() };
    if (mode === "http") {
      await this.bridge.loadToken();
      if (this.bridge.needsPairing()) {
        this._emit(Object.assign(patch, { conn: "pair" }));
        return false;
      }
    }
    this._emit(Object.assign(patch, { conn: "connected" }));
    return true;
  }

  /** User clicked "Connect": asks SYN for permission. */
  async pair() {
    this._emit({ conn: "pairing", notice: null });
    try {
      const ok = await this.bridge.pair(() => this._emit({ conn: "pairing" }));
      this._emit({ conn: ok ? "connected" : "denied" });
      return ok;
    } catch (e) {
      this._emit({ conn: "pair", notice: { kind: "error", text: e.message } });
      return false;
    }
  }

  // ---- the loop -------------------------------------------------------------

  /** One heartbeat: call every ~1 s from the panel. */
  async tick() {
    try {
      this._emit({ context: await this.host.snapshot() });
    } catch (e) {
      /* Premiere busy; try next tick */
    }
    if (!(await this.ensureConnected())) return;
    try {
      await this._refreshJobs();
    } catch (e) {
      this._handle(e);
    }
  }

  async _refreshJobs() {
    const jobs = await this.bridge.listJobs();
    const sends = new Set(await this.bridge.pendingSends());
    jobs.sort((a, b) => String(b.createdAt || b.id).localeCompare(String(a.createdAt || a.id)));
    const toImport = [];
    for (const job of jobs) {
      const prev = this._seen.get(job.id);
      this._seen.set(job.id, job.state);
      const imported = this._imported.has(job.id) || !!job.importedAt || !!job.imported;
      if (job.state !== "done" || imported || !job.result) continue;
      const justSent = sends.has(job.id) || (!this._firstList && prev !== undefined && prev !== "done") || (!this._firstList && prev === undefined);
      if (justSent && this.state.autoImport) toImport.push(job);
    }
    this._firstList = false;
    this._emit({ jobs: jobs.map((j) => this._decorate(j)) });
    for (const job of toImport) await this.importJob(job.id);
  }

  _decorate(job) {
    return Object.assign({}, job, {
      local: {
        mine: this._mine.has(job.id),
        imported: this._imported.has(job.id) || !!job.importedAt || !!job.imported,
        importing: this._importing.has(job.id),
        active: ACTIVE.has(job.state),
      },
    });
  }

  // ---- actions ---------------------------------------------------------------

  /** what = "sequence" | "selection" */
  async send(what) {
    if (this.state.busy) return null;
    if (!(await this.ensureConnected(true))) {
      this._emit({ notice: { kind: "error", text: this._connText() } });
      return null;
    }
    this._emit({ busy: what === "sequence" ? "Exporting sequence…" : "Collecting clips…", notice: null });
    try {
      const body = await this.host.buildJob(what);
      this._emit({ busy: "Handing off to SYN…" });
      const { jobId } = await this.bridge.createJob(body);
      this._mine.add(jobId);
      this._seen.set(jobId, "queued");
      const count = body.source.kind === "media" ? `${body.source.items.length} clips` : `“${body.sequenceName}”`;
      this._emit({ busy: null, notice: { kind: "ok", text: `Sent ${count} to SYN. Review it there, then hit Send to Premiere.` } });
      await this._refreshJobs().catch(() => {});
      return jobId;
    } catch (e) {
      this._emit({ busy: null });
      this._handle(e);
      return null;
    }
  }

  async cancel(jobId) {
    try {
      await this.bridge.cancelJob(jobId);
      await this._refreshJobs();
    } catch (e) {
      this._handle(e);
    }
  }

  async importJob(jobId) {
    if (this._importing.has(jobId)) return null;
    this._importing.add(jobId);
    this._emit({ busy: "Importing synced sequence…" });
    try {
      const job = (this.state.jobs.find((j) => j.id === jobId)) || (await this.bridge.getJob(jobId));
      if (!job || !job.result) throw new Error("That sync isn't finished yet.");
      const path = await this._localXml(job);
      const name = await this.host.importXml(path, job.result.sequenceName);
      this._imported.add(jobId);
      await this._savePrefs();
      await this.bridge.clearSend(jobId);
      try {
        await this.bridge.markImported(jobId, name);
      } catch (e) {
        /* the import worked; SYN just won't show the tick */
      }
      this._emit({ busy: null, notice: { kind: "ok", text: `“${name}” is in your project.` } });
      return name;
    } catch (e) {
      this._emit({ busy: null });
      this._handle(e);
      return null;
    } finally {
      this._importing.delete(jobId);
      this._emit({ jobs: this.state.jobs.map((j) => this._decorate(j)) });
    }
  }

  async _localXml(job) {
    const p = job.result.xmlPath;
    if (p) {
      try {
        await this.readText(p);
        return p;
      } catch (e) {
        /* fall back to the HTTP copy */
      }
    }
    const xml = await this.bridge.resultXml(job.id);
    return this.writeTemp(`${job.id}.xml`, xml);
  }

  _connText() {
    switch (this.state.conn) {
      case "pair":
        return "Connect to SYN first.";
      case "mismatch":
        return "This panel and SYN don't match. Update SYN.";
      default:
        return "Open SYN on this computer, then try again.";
    }
  }

  _handle(e) {
    if (e instanceof BridgeError && e.code === "unauthorized") {
      this._emit({ conn: "pair", notice: { kind: "error", text: e.message } });
      return;
    }
    if (e instanceof BridgeError && e.code === "offline") {
      this._emit({ conn: "offline", notice: { kind: "error", text: "Lost SYN. Is it still open?" } });
      return;
    }
    this._emit({ notice: { kind: "error", text: (e && e.message) || String(e) } });
  }
}

module.exports = { Session, ACTIVE };
