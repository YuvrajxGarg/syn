// Panel entry: wires UXP + Premiere into the Session and renders its state.

"use strict";

const uxp = require("uxp");
const ppro = require("premierepro");
const fs = require("fs");
const os = require("os");

const { Bridge, appDataDir, joinPath } = require("./lib/bridge.js");
const { PremiereHost } = require("./lib/premiere.js");
const { Session } = require("./lib/session.js");
const { Wave } = require("./lib/wave.js");
const view = require("./lib/view.js");

const platform = os.platform();
const SEP = platform === "win32" ? "\\" : "/";
const PLUGIN_VERSION = (uxp.versions && uxp.versions.plugin) || "1.0.0";
const HOST_VERSION = (uxp.host && uxp.host.version) || "0";

// ---- UXP adapters ------------------------------------------------------------

const files = {
  readText: (p) => fs.readFile(p, { encoding: "utf-8" }),
  writeText: (p, text) => fs.writeFile(p, text, { encoding: "utf-8" }),
  rename: (a, b) => fs.rename(a, b),
  remove: (p) => fs.unlink(p),
  list: (dir) => fs.readdir(dir),
  mkdir: (dir) => fs.mkdir(dir, { recursive: true }),
  exists: async (p) => {
    try {
      await fs.lstat(p);
      return true;
    } catch (e) {
      return false;
    }
  },
};

const secure = uxp.storage.secureStorage;
const storage = {
  async get(key) {
    const v = await secure.getItem(key);
    if (!v || !v.length) return null;
    return String.fromCharCode.apply(null, Array.from(v));
  },
  set: (key, value) => secure.setItem(key, value),
  remove: (key) => secure.removeItem(key),
};

const prefs = {
  async load() {
    try {
      return JSON.parse(await fs.readFile("plugin-data:/prefs.json", { encoding: "utf-8" }));
    } catch (e) {
      return {};
    }
  },
  save: (obj) => fs.writeFile("plugin-data:/prefs.json", JSON.stringify(obj), { encoding: "utf-8" }),
};

let session = null;
let timer = null;

async function boot() {
  const temp = await uxp.storage.localFileSystem.getTemporaryFolder();
  const tempDir = temp.nativePath.replace(/[\\/]+$/, "");

  const bridge = new Bridge({
    fetch: (url, init) => fetch(url, init),
    files,
    sep: SEP,
    bridgeDir: joinPath(SEP, appDataDir(platform, os.homedir()), "bridge"),
    storage,
    clientVersion: PLUGIN_VERSION,
    hostVersion: HOST_VERSION,
  });
  const host = new PremiereHost({ ppro, hostVersion: HOST_VERSION, tempDir, sep: SEP });
  session = new Session({
    bridge,
    host,
    prefs,
    readText: files.readText,
    writeTemp: async (name, text) => {
      const p = `${tempDir}${SEP}${name}`;
      await files.writeText(p, text);
      return p;
    },
  });

  const wave = new Wave(document.getElementById("wave"), { bars: 32, height: 40 });
  view.mount(document, session, wave);
  view.drawMark(document.getElementById("mark"));

  await session.init();
  await session.ensureConnected(true);
  start();
}

function start() {
  if (timer || !session) return;
  let running = false;
  const beat = async () => {
    if (running) return;
    running = true;
    try {
      await session.tick();
    } finally {
      running = false;
    }
  };
  beat();
  timer = setInterval(beat, 1000);
}

function stop() {
  if (timer) clearInterval(timer);
  timer = null;
}

uxp.entrypoints.setup({
  panels: {
    "syn.panel": {
      show() {
        if (!session) boot().catch((e) => view.fatal(document, e));
        else start();
      },
      hide() {
        stop();
      },
    },
  },
});
