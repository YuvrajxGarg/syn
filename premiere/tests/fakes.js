// Fakes for Premiere's UXP API and the plugin's platform adapters, for Node tests.
"use strict";

const fsp = require("fs/promises");
const path = require("path");
const { spawn } = require("child_process");

function guid(s) {
  return { toString: () => s };
}

let seqCounter = 0;

function makeSequence(name, trackMedia = []) {
  const id = `seq-${++seqCounter}`;
  const track = {
    getTrackItems: () =>
      trackMedia.map((m) => ({
        getProjectItem: async () => makeClip(m.name, m.path),
      })),
  };
  return {
    name,
    guid: guid(id),
    getVideoTrackCount: async () => (trackMedia.length ? 1 : 0),
    getVideoTrack: async () => track,
    getAudioTrackCount: async () => (trackMedia.length ? 1 : 0),
    getAudioTrack: async () => track,
  };
}

function makeBin(name, children, parent = null) {
  const bin = { kind: "bin", name, children, getParentBin() { return this._parent || parent; } };
  for (const c of children) c._parent = bin;
  return bin;
}

function makeClip(name, mediaPath, { sequence = null, offline = false } = {}) {
  const clip = {
    kind: "clip",
    name,
    getParentBin() {
      return this._parent || null;
    },
    getMediaFilePath: async () => (sequence ? "" : mediaPath),
    isSequence: async () => !!sequence,
    getSequence: async () => sequence,
    isOffline: async () => offline,
  };
  return clip;
}

/** opts.canExport: Premiere 26.2+ (ProjectConverter present). */
function makePpro({ canExport = true, activeSequence = null, selection = [], root = null } = {}) {
  const sequences = activeSequence ? [activeSequence] : [];
  const calls = { exported: [], imported: [], opened: [] };
  const rootBin = root || makeBin("root", []);
  const project = {
    name: "Shoot.prproj",
    path: "/Projects/Shoot.prproj",
    getActiveSequence: async () => activeSequence,
    getSequences: async () => sequences.slice(),
    getInsertionBin: async () => rootBin,
    getRootItem: async () => rootBin,
    importFiles: async (paths) => {
      calls.imported.push(paths[0]);
      const xml = await fsp.readFile(paths[0], "utf-8").catch(() => "");
      const m = /<name>([^<]+)<\/name>/.exec(xml);
      sequences.push(makeSequence(m ? m[1] : "Imported"));
      return true;
    },
    openSequence: async (s) => {
      calls.opened.push(s.name);
      return true;
    },
    setActiveSequence: async () => true,
  };
  const ppro = {
    Project: { getActiveProject: async () => project },
    ProjectUtils: { getSelection: async () => ({ getItems: async () => selection }) },
    ProjectItem: { cast: (x) => x },
    ClipProjectItem: {
      cast: (x) => {
        if (x.kind !== "clip") throw new Error("not a clip");
        return x;
      },
    },
    FolderItem: {
      cast: (x) => {
        if (x.kind !== "bin") throw new Error("not a bin");
        return { getItems: async () => x.children };
      },
    },
    Constants: { TrackItemType: { CLIP: 1 } },
  };
  if (canExport) {
    ppro.ProjectConverter = {
      exportAsFinalCutProXML: async (seq, p) => {
        calls.exported.push(p);
        await fsp.writeFile(p, `<xmeml version="4"><sequence><name>${seq.name}</name></sequence></xmeml>`);
        return true;
      },
    };
  }
  return { ppro, project, calls };
}

const nodeFiles = {
  readText: (p) => fsp.readFile(p, "utf-8"),
  writeText: (p, t) => fsp.writeFile(p, t, "utf-8"),
  rename: (a, b) => fsp.rename(a, b),
  remove: (p) => fsp.unlink(p),
  list: (d) => fsp.readdir(d),
  mkdir: (d) => fsp.mkdir(d, { recursive: true }),
  exists: (p) => fsp.access(p).then(() => true, () => false),
};

function memoryStorage() {
  const m = new Map();
  return {
    m,
    get: async (k) => (m.has(k) ? m.get(k) : null),
    set: async (k, v) => void m.set(k, v),
    remove: async (k) => void m.delete(k),
  };
}

function memoryPrefs(initial = {}) {
  let v = initial;
  return { load: async () => v, save: async (o) => void (v = o), get value() { return v; } };
}

async function startMock(dataDir, args = []) {
  const script = path.join(__dirname, "..", "dev", "mock_syn.py");
  const py = process.env.PYTHON || "python3";
  const child = spawn(py, [script, "--data-dir", dataDir, "--speed", "8", ...args], { stdio: ["ignore", "pipe", "inherit"] });
  await new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("mock SYN did not start")), 10000);
    child.stdout.on("data", (d) => {
      if (String(d).includes("mock SYN")) {
        clearTimeout(t);
        resolve();
      }
    });
    child.on("exit", (code) => reject(new Error(`mock exited ${code}`)));
  });
  // Wait for the first heartbeat file too.
  for (let i = 0; i < 50; i++) {
    if (await nodeFiles.exists(path.join(dataDir, "bridge", "hello.json"))) break;
    await new Promise((r) => setTimeout(r, 50));
  }
  return {
    child,
    stop: () =>
      new Promise((r) => {
        child.removeAllListeners("exit");
        child.on("exit", r);
        child.kill("SIGINT");
        setTimeout(() => child.kill("SIGKILL"), 2000);
      }),
  };
}

module.exports = { makePpro, makeSequence, makeClip, makeBin, nodeFiles, memoryStorage, memoryPrefs, startMock };
