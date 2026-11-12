// The whole workflow with nothing mocked on the SYN side: the real panel code (bridge,
// session, Premiere host) talks to the real app (`python -m syn --serve`), which really
// syncs real footage files, and the panel imports the XML SYN writes.
//
// Run: node --test premiere/tests/roundtrip.test.js   (needs python with numpy + ffmpeg)
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fsp = require("fs/promises");
const os = require("os");
const path = require("path");
const { spawn, execFileSync } = require("child_process");

const { Bridge } = require("../plugin/lib/bridge.js");
const { PremiereHost } = require("../plugin/lib/premiere.js");
const { Session } = require("../plugin/lib/session.js");
const F = require("./fakes.js");

const ROOT = path.join(__dirname, "..", "..");
const PY = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");

// A shoot: a lav recorder running the whole time, camera A rolling twice and camera B once.
// Offsets are in seconds from the start of the recorder.
const SHOOT = [
  { name: "ZOOM0001.wav", start: 0, dur: 150, mic: "lav", bin: "Audio" },
  { name: "A001.mp4", start: 20, dur: 40, mic: "camA", bin: "Cam A" },
  { name: "A002.mp4", start: 85, dur: 30, mic: "camA", bin: "Cam A" },
  { name: "B001.mp4", start: 47.5, dur: 45, mic: "camB", bin: "Cam B" },
];

function makeFootage(dir) {
  const script = `
import json, os, sys
sys.path.insert(0, ${JSON.stringify(path.join(ROOT, "tests"))})
sys.path.insert(0, ${JSON.stringify(ROOT)})
import synth
from syn import media
ff = media.find_ffmpeg()
W = synth.world(160, seed=7)
mics = {"lav": synth.mic(W, 1, noise=0.003), "camA": synth.mic(W, 2, gain=0.4, noise=0.006, tilt=0.5, echo=0.3),
        "camB": synth.mic(W, 3, gain=0.3, noise=0.008, tilt=-0.4, echo=0.5)}
for c in json.loads(sys.argv[1]):
    p = os.path.join(sys.argv[2], c["name"])
    x = synth.cut(mics[c["mic"]], c["start"], c["dur"])
    synth.write_wav(p, x) if p.endswith(".wav") else synth.write_video(p, x, ff)
`;
  execFileSync(PY, ["-c", script, JSON.stringify(SHOOT), dir], { stdio: "inherit" });
}

async function startSyn(home) {
  const child = spawn(PY, ["-m", "syn", "--serve", "--auto-approve", "--auto-send"], {
    cwd: ROOT,
    env: { ...process.env, SYN_HOME: home, PYTHONUNBUFFERED: "1" },
    stdio: ["ignore", "pipe", "inherit"],
  });
  let out = "";
  await new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("SYN did not start:\n" + out)), 30000);
    child.stdout.on("data", (d) => {
      out += d;
      if (out.includes("SYN bridge on")) {
        clearTimeout(t);
        resolve();
      }
    });
    child.on("exit", (code) => reject(new Error(`SYN exited ${code}:\n${out}`)));
  });
  for (let i = 0; i < 100; i++) {
    if (await F.nodeFiles.exists(path.join(home, "bridge", "hello.json"))) break;
    await new Promise((r) => setTimeout(r, 50));
  }
  return () =>
    new Promise((r) => {
      child.removeAllListeners("exit");
      child.on("exit", r);
      child.kill(process.platform === "win32" ? undefined : "SIGINT");
      setTimeout(() => child.kill("SIGKILL"), 3000);
    });
}

async function session(home, ppro, fetchImpl) {
  const bridge = new Bridge({
    fetch: fetchImpl || fetch,
    files: F.nodeFiles,
    sep: path.sep,
    bridgeDir: path.join(home, "bridge"),
    storage: F.memoryStorage(),
    clientVersion: "1.0.0",
    hostVersion: "26.2.0",
    responseTimeoutMs: 15000,
  });
  const host = new PremiereHost({ ppro, tempDir: os.tmpdir(), sep: path.sep });
  const s = new Session({
    bridge,
    host,
    prefs: F.memoryPrefs(),
    readText: F.nodeFiles.readText,
    writeTemp: async (name, text) => {
      const p = path.join(os.tmpdir(), name);
      await fsp.writeFile(p, text);
      return p;
    },
  });
  await s.init();
  return { s, bridge };
}

async function until(fn, ms = 120000, why = async () => "") {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (await fn()) return;
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error("timed out " + (await why()));
}

// Clip start (in frames) on the synced sequence, by file name, from the XML Premiere imports.
function placements(xml) {
  const at = {};
  for (const m of xml.matchAll(/<clipitem\b[\s\S]*?<\/clipitem>/g)) {
    const item = m[0];
    const start = /<start>(-?\d+)<\/start>/.exec(item);
    const inP = /<in>(-?\d+)<\/in>/.exec(item);
    const url = /<pathurl>([^<]+)<\/pathurl>/.exec(item);
    const name = url ? decodeURIComponent(url[1]).split(/[\\/]/).pop() : (/<name>([^<]+)<\/name>/.exec(item) || [])[1];
    if (!name || !start) continue;
    const s = Number(start[1]) - (inP ? Number(inP[1]) : 0); // where the media's first frame lands
    if (!(name in at)) at[name] = s;
  }
  return at;
}

function checkSync(xml) {
  const at = placements(xml);
  for (const c of SHOOT) assert.ok(c.name in at, `${c.name} is on the synced sequence: ${JSON.stringify(at)}`);
  const ref = at["ZOOM0001.wav"];
  // Sequence frame rate from the XML (the footage is 24 fps).
  const tb = Number(/<timebase>(\d+)<\/timebase>/.exec(xml)[1]);
  const ntsc = /<ntsc>TRUE<\/ntsc>/i.test(xml.split("<media>")[0]);
  const FPS = ntsc ? (tb * 1000) / 1001 : tb;
  for (const c of SHOOT) {
    const want = Math.round(c.start * FPS);
    assert.ok(Math.abs(at[c.name] - ref - want) <= 1, `${c.name}: at ${at[c.name] - ref} frames, want ${want}`);
  }
}

let footage;
test.before(async () => {
  footage = await fsp.mkdtemp(path.join(os.tmpdir(), "syn-shoot-"));
  makeFootage(footage);
});

for (const transport of ["http", "files"]) {
  test(`round trip over ${transport}: select clips in a bin → SYN syncs → synced sequence imported`, async (t) => {
    const home = await fsp.mkdtemp(path.join(os.tmpdir(), "syn-home-"));
    const stop = await startSyn(home);
    t.after(stop);

    const clips = SHOOT.map((c) => F.makeClip(c.name, path.join(footage, c.name)));
    const { ppro, calls } = F.makePpro({ selection: clips });
    const blocked = async () => {
      throw new TypeError("Failed to fetch");
    };
    const { s, bridge } = await session(home, ppro, transport === "files" ? blocked : undefined);

    await s.ensureConnected(true);
    assert.equal(s.state.mode, transport === "http" ? "http" : "file");
    if (transport === "http") assert.equal(await s.pair(), true);
    assert.equal(s.state.conn, "connected");

    const jobId = await s.send("selection");
    assert.ok(jobId, JSON.stringify(s.state.notice));
    await until(async () => {
      await s.tick();
      return calls.imported.length === 1;
    }, 120000, async () => JSON.stringify({ job: await bridge.getJob(jobId), notice: s.state.notice }));

    const job = await bridge.getJob(jobId);
    assert.equal(job.state, "done");
    assert.ok(job.importedAt, "SYN heard about the import");
    assert.ok(job.result.confidence.overall > 0.8, `overall confidence ${job.result.confidence.overall}`);
    for (const c of job.result.confidence.clips) assert.equal(c.status, "synced", JSON.stringify(c));
    assert.match(calls.opened[0], /\(SYN\)$/);

    const xml = await fsp.readFile(calls.imported[0], "utf-8");
    checkSync(xml);
  });
}

test("round trip from a sequence: export XML → SYN → import (needs Premiere 26.2's XML export)", async (t) => {
  const home = await fsp.mkdtemp(path.join(os.tmpdir(), "syn-home-"));
  const stop = await startSyn(home);
  t.after(stop);

  // A real FCP7 sequence XML referencing the footage (SYN's own CLI output stands in for
  // what Premiere exports); syncing it again must land every clip in the same place.
  const unsynced = path.join(footage, "unsynced.xml");
  execFileSync(PY, ["-m", "syn", "sync", ...SHOOT.map((c) => path.join(footage, c.name)), "-o", unsynced], {
    cwd: ROOT,
    env: { ...process.env, SYN_HOME: home },
  });
  const exported = (await fsp.readFile(unsynced, "utf-8"));

  const seq = F.makeSequence("Interview day 1", SHOOT.map((c) => ({ name: c.name, path: path.join(footage, c.name) })));
  const { ppro, calls } = F.makePpro({ activeSequence: seq });
  ppro.ProjectConverter.exportAsFinalCutProXML = async (_s, p) => {
    calls.exported.push(p);
    await fsp.writeFile(p, exported);
    return true;
  };
  const { s, bridge } = await session(home, ppro);
  await s.ensureConnected(true);
  assert.equal(await s.pair(), true);
  const jobId = await s.send("sequence");
  assert.ok(jobId, JSON.stringify(s.state.notice));
  await until(async () => {
    await s.tick();
    return calls.imported.length === 1;
  }, 120000, async () => JSON.stringify({ job: await bridge.getJob(jobId), notice: s.state.notice }));
  const job = await bridge.getJob(jobId);
  assert.equal(job.state, "done");
  assert.ok(job.importedAt);
  checkSync(await fsp.readFile(calls.imported[0], "utf-8"));
});
