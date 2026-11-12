// Run: node --test premiere/tests
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fsp = require("fs/promises");
const os = require("os");
const path = require("path");

const { Bridge, appDataDir, compareVersions } = require("../plugin/lib/bridge.js");
const { PremiereHost } = require("../plugin/lib/premiere.js");
const { Session } = require("../plugin/lib/session.js");
const view = require("../plugin/lib/view.js");
const F = require("./fakes.js");

async function tmpdir() {
  return fsp.mkdtemp(path.join(os.tmpdir(), "syn-plugin-"));
}

function blockedFetch() {
  // What Premiere on macOS does to http:// from UXP.
  return async () => {
    throw new TypeError("Failed to fetch");
  };
}

async function harness(dataDir, { fetchImpl = fetch, ppro, storage = F.memoryStorage(), prefs = F.memoryPrefs() } = {}) {
  const temp = await tmpdir();
  const bridge = new Bridge({
    fetch: fetchImpl,
    files: F.nodeFiles,
    sep: "/",
    bridgeDir: path.join(dataDir, "bridge"),
    storage,
    clientVersion: "1.0.0",
    hostVersion: "26.2.0",
    responseTimeoutMs: 5000,
  });
  const host = new PremiereHost({ ppro, tempDir: temp, sep: "/" });
  const session = new Session({
    bridge,
    host,
    prefs,
    readText: F.nodeFiles.readText,
    writeTemp: async (name, text) => {
      const p = path.join(temp, name);
      await fsp.writeFile(p, text);
      return p;
    },
  });
  await session.init();
  return { bridge, host, session, storage, prefs };
}

async function until(fn, ms = 8000) {
  const start = Date.now();
  while (Date.now() - start < ms) {
    const v = await fn();
    if (v) return v;
    await new Promise((r) => setTimeout(r, 60));
  }
  throw new Error("timed out");
}

// ---- unit ---------------------------------------------------------------------

test("app data folder matches the app on both OSes", () => {
  assert.equal(appDataDir("darwin", "/Users/y"), "/Users/y/Library/Application Support/Syn");
  assert.equal(appDataDir("win32", "C:\\Users\\y"), "C:\\Users\\y\\AppData\\Roaming\\Syn");
});

test("version compare", () => {
  assert.equal(compareVersions("1.0.0", "1.0.1"), -1);
  assert.equal(compareVersions("1.10.0", "1.9.9"), 1);
  assert.equal(compareVersions("2.0", "2.0.0"), 0);
});

test("sync card shows one overall score, escaped, and an Import button", () => {
  const job = { id: "j1", state: "done", result: { sequenceName: "<b>Day 1</b> (SYN)", confidence: { overall: 0.93, clips: [{ name: "a.mov" }] } }, local: { imported: false } };
  const html = view.cardHtml(job);
  assert.ok(html.includes("&lt;b&gt;Day 1&lt;/b&gt;"));
  assert.ok(!html.includes("<b>Day"));
  assert.ok(html.includes(">93%<"));
  assert.ok(html.includes("Looks great"));
  assert.ok(html.includes('data-action="import"'));
  assert.ok(!html.includes("a.mov"), "no per-clip detail in the panel");
  assert.match(view.cardHtml(Object.assign({}, job, { local: { imported: true } })), /In your project/);
  assert.equal(view.verdict(0.7).cls, "mid");
  assert.equal(view.verdict(0.4).cls, "low");
});

test("Sync button picks selected clips first, else the open sequence", () => {
  assert.equal(view.target({ sequence: { name: "S" }, selection: { media: 3, sequences: 0 } }).label, "Sync 3 clips");
  assert.equal(view.target({ sequence: { name: "S" }, selection: { media: 3, sequences: 0 } }).alt, "sequence");
  assert.equal(view.target({ sequence: { name: "S" }, selection: { media: 0, sequences: 0 } }).what, "sequence");
  assert.equal(view.target({ selection: { media: 0, sequences: 0 } }).what, null);
});

test("the card follows the sync that matters", () => {
  const jobs = [
    { id: "new", state: "done", local: { imported: true } },
    { id: "waiting", state: "done", local: { imported: false } },
    { id: "old", state: "failed", local: {} },
  ];
  assert.equal(view.currentJob(jobs).id, "waiting");
  assert.equal(view.currentJob([{ id: "run", state: "analyzing", local: {} }].concat(jobs)).id, "run");
  assert.equal(view.currentJob([]), null);
});

// ---- Premiere side ------------------------------------------------------------------

test("selection: bins are expanded, stills and duplicates skipped, bin path kept", async () => {
  const camA = F.makeBin("Cam A", [F.makeClip("A001.mov", "/m/A001.mov"), F.makeClip("logo.png", "/m/logo.png")]);
  const day = F.makeBin("Day 1", [camA, F.makeClip("ZOOM0001.WAV", "/m/ZOOM0001.WAV")]);
  const root = F.makeBin("root", [day]);
  root.getParentBin = () => null;
  day.getParentBin = () => root;
  const { ppro } = F.makePpro({ selection: [day, F.makeClip("A001.mov", "/m/A001.mov")], root });
  const host = new PremiereHost({ ppro, tempDir: os.tmpdir() });
  const job = await host.buildJob("selection");
  assert.equal(job.source.kind, "media");
  assert.deepEqual(job.source.items.map((i) => i.path).sort(), ["/m/A001.mov", "/m/ZOOM0001.WAV"]);
  const a = job.source.items.find((i) => i.path === "/m/A001.mov");
  assert.equal(a.bin, "Day 1/Cam A");
});

test("Premiere 26.2+: sequence goes over as FCP XML", async () => {
  const seq = F.makeSequence("Interview", [{ name: "A.mov", path: "/m/A.mov" }]);
  const { ppro, calls } = F.makePpro({ activeSequence: seq });
  const host = new PremiereHost({ ppro, tempDir: await tmpdir() });
  const job = await host.buildJob("sequence");
  assert.equal(job.source.kind, "xml");
  assert.equal(job.source.path, calls.exported[0]);
  assert.equal(job.sequenceName, "Interview");
});

test("Premiere 25.6-26.1: no XML API, so the sequence's media goes over instead", async () => {
  const seq = F.makeSequence("Interview", [{ name: "A.mov", path: "/m/A.mov" }, { name: "B.wav", path: "/m/B.wav" }]);
  const { ppro } = F.makePpro({ canExport: false, activeSequence: seq });
  const host = new PremiereHost({ ppro, tempDir: os.tmpdir() });
  assert.equal(host.canExportXml(), false);
  const job = await host.buildJob("sequence");
  assert.equal(job.source.kind, "media");
  assert.deepEqual(job.source.items.map((i) => i.path), ["/m/A.mov", "/m/B.wav"]);
});

test("nothing open gives a clear message", async () => {
  const { ppro } = F.makePpro();
  const host = new PremiereHost({ ppro, tempDir: os.tmpdir() });
  await assert.rejects(host.buildJob("sequence"), /Open a sequence/);
  await assert.rejects(host.buildJob("selection"), /Select clips/);
});

// ---- end to end against a mock SYN ---------------------------------------------

test("HTTP: pair, send a sequence, follow progress, auto-import, confirm", async (t) => {
  const data = await tmpdir();
  const mock = await F.startMock(data, ["--auto-send"]);
  t.after(() => mock.stop());
  const seq = F.makeSequence("Interview day 1", [{ name: "A.mov", path: "/m/A.mov" }]);
  const { ppro, calls } = F.makePpro({ activeSequence: seq });
  const { session, storage, bridge } = await harness(data, { ppro });

  await session.ensureConnected(true);
  assert.equal(session.state.mode, "http");
  assert.equal(session.state.conn, "pair");
  assert.equal(await session.pair(), true);
  assert.equal(session.state.conn, "connected");
  assert.ok(storage.m.get("syn.token"));

  const progress = [];
  session.on((s) => {
    const j = s.jobs[0];
    if (j && j.state === "analyzing") progress.push(j.progress);
  });
  const jobId = await session.send("sequence");
  assert.ok(jobId, JSON.stringify(session.state.notice));

  await until(async () => {
    await session.tick();
    return calls.imported.length === 1;
  });
  assert.equal(calls.opened[0], "Interview day 1 (SYN)");
  const job = await bridge.getJob(jobId);
  assert.ok(job.importedAt, "SYN was told about the import");
  assert.ok(progress.length >= 1, "saw live progress");
  assert.match(session.state.notice.text, /is in your project/);

  // Nothing is imported twice.
  await session.tick();
  await session.tick();
  assert.equal(calls.imported.length, 1);
});

test("macOS: http blocked, falls back to the file mailbox end to end", async (t) => {
  const data = await tmpdir();
  const mock = await F.startMock(data, ["--auto-send", "--no-http"]);
  t.after(() => mock.stop());
  const clip = F.makeClip("A001.mov", "/m/A001.mov");
  const { ppro, calls } = F.makePpro({ selection: [clip, F.makeClip("ZOOM.wav", "/m/ZOOM.wav")] });
  const { session, bridge } = await harness(data, { ppro, fetchImpl: blockedFetch() });

  await session.ensureConnected(true);
  assert.equal(session.state.mode, "file");
  assert.equal(session.state.conn, "connected");

  const jobId = await session.send("selection");
  assert.ok(jobId, JSON.stringify(session.state.notice));
  await until(async () => {
    await session.tick();
    return calls.imported.length === 1;
  });
  assert.deepEqual(await bridge.pendingSends(), [], "send signal cleared");
  const job = await until(async () => {
    const j = await bridge.getJob(jobId);
    return j.importedAt ? j : null;
  });
  assert.ok(job.importedAt);
});

test("file mailbox: SYN not running reads as offline", async () => {
  const data = await tmpdir();
  await fsp.mkdir(path.join(data, "bridge"), { recursive: true });
  // A stale heartbeat from a SYN that crashed a minute ago.
  await fsp.writeFile(path.join(data, "bridge", "hello.json"), JSON.stringify({ app: "Syn", api: 1, heartbeat: Date.now() - 60000 }));
  const { ppro } = F.makePpro();
  const { session } = await harness(data, { ppro, fetchImpl: blockedFetch() });
  await session.ensureConnected(true);
  assert.equal(session.state.conn, "offline");
  await session.send("sequence");
  assert.match(session.state.notice.text, /Open SYN/);
});

test("jobs already finished when the panel opens wait for a click", async (t) => {
  const data = await tmpdir();
  const mock = await F.startMock(data, ["--auto-send", "--no-http"]);
  t.after(() => mock.stop());
  const seq = F.makeSequence("Old", [{ name: "A.mov", path: "/m/A.mov" }]);
  // Panel A sends a job then goes away before importing.
  const a = await harness(data, { ppro: F.makePpro({ activeSequence: seq }).ppro, fetchImpl: blockedFetch() });
  await a.session.ensureConnected(true);
  const jobId = await a.session.send("sequence");
  await until(async () => (await a.bridge.getJob(jobId)).state === "done");
  // The send signal stays until someone imports; clear it to model "seen long ago".
  await a.bridge.clearSend(jobId);

  const b = F.makePpro({ activeSequence: seq });
  const panel = await harness(data, { ppro: b.ppro, fetchImpl: blockedFetch() });
  await panel.session.ensureConnected(true);
  await panel.session.tick();
  await panel.session.tick();
  assert.equal(b.calls.imported.length, 0);
  const row = panel.session.state.jobs.find((j) => j.id === jobId);
  assert.equal(row.state, "done");
  assert.equal(row.local.imported, false);
  await panel.session.importJob(jobId);
  assert.equal(b.calls.imported.length, 1);
});

test("HTTP: SYN denies the connection", async (t) => {
  const data = await tmpdir();
  const mock = await F.startMock(data, ["--approve", "deny"]);
  t.after(() => mock.stop());
  const { session } = await harness(data, { ppro: F.makePpro().ppro });
  await session.ensureConnected(true);
  assert.equal(await session.pair(), false);
  assert.equal(session.state.conn, "denied");
});

test("HTTP: a revoked token sends the panel back to Connect", async (t) => {
  const data = await tmpdir();
  const mock = await F.startMock(data);
  t.after(() => mock.stop());
  const storage = F.memoryStorage();
  await storage.set("syn.token", "revoked-token");
  const { session } = await harness(data, { ppro: F.makePpro().ppro, storage });
  await session.ensureConnected(true);
  assert.equal(session.state.conn, "connected");
  await session.tick();
  assert.equal(session.state.conn, "pair");
  assert.equal(storage.m.has("syn.token"), false);
});

test("update banner: SYN bundles a newer panel and installs it on request", async (t) => {
  const data = await tmpdir();
  const mock = await F.startMock(data, ["--no-http", "--bundled", "1.4.0"]);
  t.after(() => mock.stop());
  const { session } = await harness(data, { ppro: F.makePpro().ppro, fetchImpl: blockedFetch() });
  await session.ensureConnected(true);
  assert.equal(session.state.updateAvailable, true);
  assert.equal(await session.updatePlugin(), "installed");
  assert.match(session.state.notice.text, /Panel updated/);
});
