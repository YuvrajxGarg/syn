// Renders the panel in a normal browser with fake state, for screenshots and design work.
//   node premiere/dev/preview.js > /tmp/preview.html   (open it in Chrome)
// Chrome supports more CSS than UXP; the panel only uses what UXP supports.
"use strict";

const fs = require("fs");
const path = require("path");

const plugin = path.join(__dirname, "..", "plugin");
const read = (p) => fs.readFileSync(path.join(plugin, p), "utf-8");
const body = read("index.html").split("<body>")[1].split("<script")[0];
const mods = ["lib/bridge.js", "lib/view.js", "lib/wave.js"]
  .map((m) => `defs[${JSON.stringify("./" + path.basename(m))}] = function (module, exports, require) {\n${read(m)}\n};`)
  .join("\n");

const clips = [];
const names = ["A001_C001", "A001_C002", "B002_C004", "C003_C001", "ZOOM0004_TR1", "ZOOM0004_TR2", "GOPRO_0091", "A001_C003", "B002_C005", "LAV_JAKE_03"];
for (let i = 0; i < 24; i++) {
  const conf = i === 3 ? 0.31 : i === 7 ? 0.64 : i === 12 ? 0.71 : 0.86 + ((i * 37) % 13) / 100;
  clips.push({ name: `${names[i % names.length]}${i >= names.length ? "_" + i : ""}.mov`, confidence: conf, status: conf < 0.5 ? "unsynced" : conf < 0.8 ? "low" : "synced" });
}

const state = {
  conn: "connected",
  mode: "http",
  hello: { app: "Syn", version: "1.0.0" },
  updateAvailable: false,
  context: { project: { name: "Shoot" }, sequence: { name: "Interview day 1" }, selection: { media: 42, sequences: 0 }, canExportXml: true },
  busy: null,
  notice: { kind: "ok", text: "“Wedding ceremony (SYN)” is in your project." },
  autoImport: true,
  jobs: [
    { id: "j3", state: "analyzing", progress: 0.58, stage: "Matching audio · 23 / 40 clips", sequenceName: "Interview day 1", local: { mine: true } },
    { id: "j2", state: "done", result: { sequenceName: "Wedding ceremony (SYN)", confidence: { overall: 0.93, clips } }, local: { imported: true } },
    { id: "j1", state: "done", result: { sequenceName: "B-roll day 2 (SYN)", confidence: { overall: 0.71, clips: clips.slice(0, 9).map((c, i) => Object.assign({}, c, i === 2 ? { status: "low", confidence: 0.58 } : {})) } }, local: { imported: false } },
  ],
};

const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><style>${read("styles.css")}
body{width:300px;min-height:640px;margin:0}</style></head><body>${body}
<script>
(function(){
  var defs = {}, cache = {};
  function req(n){ if(cache[n]) return cache[n].exports; var m = cache[n] = {exports:{}}; defs[n](m, m.exports, req); return m.exports; }
  ${mods}
  var view = req("./view.js"), Wave = req("./wave.js").Wave;
  var state = ${JSON.stringify(state)};
  var session = { state: state, on: function(){}, send: function(){}, pair: function(){}, ensureConnected: function(){}, importJob: function(){}, cancel: function(){}, setAutoImport: function(){} };
  var wave = new Wave(document.getElementById("busy-wave"), { bars: 30, height: 36 });
  view.drawMark(document.getElementById("mark"));
  view.mount(document, session, wave);
  var url = new URL(location.href);
  if (url.searchParams.get("expand")) document.querySelector('[data-action="toggle"][data-id="j1"]').click();
})();
</script></body></html>`;

process.stdout.write(html);
