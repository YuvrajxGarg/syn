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

const base = {
  conn: "connected",
  mode: "http",
  hello: { app: "Syn", version: "1.0.0" },
  updateAvailable: false,
  context: { project: { name: "Shoot" }, sequence: { name: "Interview day 1" }, selection: { media: 0, sequences: 0 }, canExportXml: true },
  busy: null,
  notice: null,
  jobs: [],
};
const states = {
  syncing: Object.assign({}, base, {
    jobs: [{ id: "j3", state: "analyzing", progress: 0.58, stage: "Matching audio · 23 of 40 clips", sequenceName: "Interview day 1", local: { mine: true } }],
  }),
  done: Object.assign({}, base, {
    context: Object.assign({}, base.context, { selection: { media: 42, sequences: 0 } }),
    jobs: [{ id: "j2", state: "done", result: { sequenceName: "Interview day 1 (SYN)", confidence: { overall: 0.93 } }, local: { imported: true } }],
  }),
  ready: Object.assign({}, base, {
    updateAvailable: true,
    jobs: [{ id: "j1", state: "done", result: { sequenceName: "B-roll day 2 (SYN)", confidence: { overall: 0.71 } }, local: { imported: false } }],
  }),
  offline: Object.assign({}, base, { conn: "offline", jobs: [] }),
};

const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><style>${read("styles.css")}
body{width:280px;min-height:330px;margin:0}</style></head><body>${body}
<script>
(function(){
  var defs = {}, cache = {};
  function req(n){ if(cache[n]) return cache[n].exports; var m = cache[n] = {exports:{}}; defs[n](m, m.exports, req); return m.exports; }
  ${mods}
  var view = req("./view.js"), Wave = req("./wave.js").Wave;
  var all = ${JSON.stringify(states)}; var state = all[new URL(location.href).searchParams.get("state") || "syncing"];
  var session = { state: state, on: function(){}, send: function(){}, pair: function(){}, ensureConnected: function(){}, importJob: function(){}, cancel: function(){}, setAutoImport: function(){} };
  var wave = new Wave(document.getElementById("wave"), { bars: 32, height: 40 });
  view.drawMark(document.getElementById("mark"));
  view.mount(document, session, wave);
})();
</script></body></html>`;

process.stdout.write(html);
