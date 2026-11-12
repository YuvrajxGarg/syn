// Demo data for screenshots and UI work: open index.html?demo in a browser.
// ?demo          a 40-track sequence, ready to sync (press Sync to watch it)
// ?demo=sync     same, and the sync starts by itself
// ?demo=review   already synced, with a clip to check selected
// ?demo=empty    no project
// ?demo=welcome  first launch
const Q = new URLSearchParams(location.search);
const MODE = Q.get('demo') || 'ready';

let seed = 7;
const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);

function envFor(dur, loud) {
  const rate = 10, n = Math.max(4, Math.round(dur * rate));
  const a = new Uint8Array(n);
  let v = 80;
  for (let i = 0; i < n; i++) {
    v += (rnd() - 0.5) * 60;
    v = Math.max(10, Math.min(255, v));
    const speech = Math.sin(i / 7) > -0.3 ? 1 : 0.35;
    a[i] = Math.min(255, v * speech * loud + rnd() * 30);
  }
  let s = '';
  for (let i = 0; i < n; i++) s += String.fromCharCode(a[i]);
  return { rate: n / dur, data: btoa(s) };
}

function makeProject() {
  const CAMS = 'ABCDEFGHIJKLMNOPQRST'.split('');
  const TAKES = [0, 640, 1290, 1900, 2610];
  const lanes = [], clips = [], env = {};
  CAMS.forEach((c, i) => lanes.push({ id: 'v' + (i + 1), label: 'V' + (i + 1), kind: 'video', name: `Cam ${c}` }));
  for (let i = 0; i < 14; i++) lanes.push({ id: 'a' + (i + 1), label: 'A' + (i + 1), kind: 'audio', name: `Cam ${CAMS[i]}` });
  ['ZOOM F8 · 1', 'ZOOM F8 · 2', 'Lav Ana', 'Lav Ravi', 'Boom', 'Room'].forEach((n, i) =>
    lanes.push({ id: 'a' + (15 + i), label: 'A' + (15 + i), kind: 'audio', name: n }));

  let k = 0;
  const truth = {};
  CAMS.forEach((c, ci) => {
    TAKES.forEach((T, ti) => {
      if (ci > 11 && ti % 2 === 1) return; // the B-roll cameras skipped some takes
      const id = `f${++k}`;
      const dur = 280 + rnd() * 260;
      const at = T + (rnd() - 0.5) * 50;
      truth[id] = at;
      const ln = ['v' + (ci + 1)];
      if (ci < 14) ln.push('a' + (ci + 1));
      clips.push({ id, name: `${c}${String(ti + 1).padStart(3, '0')}_C${String(ti * 3 + ci).padStart(3, '0')}.MP4`, path: `/Volumes/SHOOT/${c}/${id}.MP4`,
        lanes: ln, duration: +dur.toFixed(3), video: true, channels: 2, orig: null });
      env[id] = envFor(dur, 0.6 + rnd() * 0.3);
    });
  });
  const rec = [['a15', 'a16'], ['a17', 'a18'], ['a19', 'a20']];
  const recName = ['ZOOM', 'LAV', 'BOOM'];
  rec.forEach((ln, ri) => TAKES.forEach((T, ti) => {
    const id = `f${++k}`;
    const dur = 560 + rnd() * 60;
    truth[id] = T - 20 - rnd() * 10;
    clips.push({ id, name: `${recName[ri]}${String(ti + 1).padStart(4, '0')}.WAV`, path: `/Volumes/SHOOT/Audio/${id}.WAV`,
      lanes: ln, duration: +dur.toFixed(3), video: false, channels: 2, orig: null });
    env[id] = envFor(dur, 0.95);
  }));
  // pre-sync: each lane laid end to end, as Premiere had them dumped
  for (const L of lanes) {
    let t = 0;
    for (const c of clips) if (c.lanes[0] === L.id) { c.orig = t; t += c.duration + 4; }
  }
  for (const c of clips) Object.assign(c, {
    start: null, component: null, status: 'pending', confidence: 0, error: null, nudge: 0, forced: false,
    matched: null, matched_id: null, z: null, overlap: null, agree: 0, disagree: 0, curve: null, drift: null, at: null,
  });
  return {
    project: { id: 'p1', name: 'Wedding · Day 2 ceremony', kind: 'sequence', state: 'ready', stage: '', progress: 0, error: null,
      overall: null, fps: 23.976, lanes, clips, components: 0, notes: [], output: null, xml: '/Volumes/SHOOT/Day2.xml', env },
    truth,
  };
}

function synced(P, truth) {
  const recs = P.clips.filter((c) => !c.video);
  const low = new Set(['f7', 'f41', 'f63']);
  const lost = new Set(['f58']);
  for (const c of P.clips) {
    const best = recs[Math.floor(rnd() * recs.length)];
    const curve = Array.from({ length: 61 }, (_, i) => Math.exp(-((i - 30) ** 2) / 6) * (low.has(c.id) ? 0.45 : 1) + rnd() * 0.12);
    if (lost.has(c.id)) {
      Object.assign(c, { status: 'unsynced', confidence: 0.08, start: null, at: null, error: 'No shared sound with any other clip', curve: null });
      continue;
    }
    const conf = low.has(c.id) ? 0.42 + rnd() * 0.25 : 0.86 + rnd() * 0.14;
    Object.assign(c, {
      status: low.has(c.id) ? 'low' : 'synced', confidence: +conf.toFixed(3), start: truth[c.id], at: truth[c.id] + 30,
      component: 0, matched: c.video ? best.name : P.clips[0].name, matched_id: c.video ? best.id : 'f1',
      z: +(low.has(c.id) ? 7 + rnd() * 2 : 14 + rnd() * 20).toFixed(1), overlap: +(120 + rnd() * 300).toFixed(1),
      agree: low.has(c.id) ? 0 : 1 + Math.floor(rnd() * 4), disagree: low.has(c.id) ? 1 : 0, curve,
      drift: !c.video && c.id.endsWith('1') ? 12.4 : null,
    });
  }
  const n = P.clips.length;
  return Object.assign(P, { state: 'review', stage: `Synced ${n - lost.size} of ${n} clips`, progress: 1, overall: 0.94, components: 1 });
}

export default function demo(start, App) {
  const { project, truth } = makeProject();
  let P = project;
  const settings = { mode: 'fast', drift: true, keep_camera_audio: true, mark_low: true, unsynced: 'end', out_mode: 'beside',
    custom_dir: null, open_after: false, auto_send: false, density: 'comfortable', auto_check: true, auto_install: true,
    welcomed: MODE !== 'welcome' };
  const row = () => ({ id: P.id, name: P.name, kind: P.kind, state: P.state, progress: P.progress, clips: P.clips.length,
    synced: P.clips.filter((c) => c.start != null).length, overall: P.overall, premiere: true });
  const rows = () => [row(), { id: 'p2', name: 'Interview · Studio B', kind: 'media', state: 'review', progress: 1, clips: 9, synced: 9, overall: 0.99, premiere: false }];
  const pub = () => JSON.parse(JSON.stringify(P));
  let timer = null;
  const ok = (x) => Promise.resolve(x);

  const api = {
    info: () => ok({ version: '1.0.0', platform: 'darwin', home: '/Users/you', ffmpeg: true, settings,
      update: { phase: 'idle', current: '1.0.0', latest: null, page: 'https://github.com/YuvrajxGarg/syn/releases', can_install: true },
      bridge: { connected: MODE !== 'empty', port: 47480, clients: [{ id: 'c1', name: 'Premiere Pro 2026', seen: Date.now() / 1000 }], pending: [] },
      plugin: { installed: '1.0.0', bundled: '1.0.0', busy: false, result: null }, has_plugin: true,
      projects: MODE === 'empty' || MODE === 'welcome' ? [] : rows(),
      project: MODE === 'empty' || MODE === 'welcome' ? null : (MODE === 'review' ? synced(P, truth) : P) }),
    set_setting: (k, v) => { settings[k] = v; return ok({ ...settings }); },
    sync: () => { run(); return ok(true); },
    cancel: () => { clearInterval(timer); P.state = 'ready'; App.on('progress', { pid: P.id, state: 'ready', stage: 'Cancelled', progress: 0 }); return ok(true); },
    select: () => ok(true), close_project: () => ok(rows()),
    nudge: (pid, id, v) => { const c = P.clips.find((x) => x.id === id); c.nudge = v; return ok(pub()); },
    mark_checked: (pid, id, on) => { const c = P.clips.find((x) => x.id === id); c.forced = on; if (on) c.status = 'synced'; return ok(pub()); },
    set_excluded: (pid, id, on) => { const c = P.clips.find((x) => x.id === id); c.status = on ? 'excluded' : 'pending'; return ok(pub()); },
    export: () => ok({ path: '/Volumes/SHOOT/Day2 (SYN).xml', name: 'Day2 (SYN)' }),
    send_to_premiere: () => ok({ ok: true }),
    bridge_status: () => api.info().then((i) => i.bridge),
    plugin_install: () => ok({ installed: '1.0.0', bundled: '1.0.0', busy: false, result: 'installed' }),
    plugin_uninstall: () => ok({ installed: null, bundled: '1.0.0', busy: false, result: null }),
    cache_info: () => ok({ bytes: 182e6, files: 95, path: '/Users/you/Library/Application Support/Syn/Cache' }),
    check_updates: () => ok({ phase: 'idle', current: '1.0.0', latest: '1.0.0' }),
  };
  const noop = () => ok(null);
  const proxy = new Proxy(api, { get: (o, k) => o[k] || noop });

  function run() {
    const ids = P.clips.map((c) => c.id);
    const env = P.env;
    P.state = 'analyzing';
    let i = 0, phase = 0, pairs = 0;
    const total = ids.length, totalPairs = 1700;
    timer = setInterval(() => {
      if (phase === 0) {
        const id = ids[i];
        const c = P.clips.find((x) => x.id === id);
        App.on('clip', { pid: P.id, clip: c, reading: true });
        setTimeout(() => App.on('clip', { pid: P.id, clip: c, reading: false, env: env[id] }), 260);
        i++;
        App.on('progress', { pid: P.id, state: 'analyzing', stage: `Listening · ${i} / ${total} clips`, progress: 0.55 * i / total });
        if (i >= total) phase = 1;
      } else if (phase === 1) {
        pairs = Math.min(totalPairs, pairs + 90);
        App.on('progress', { pid: P.id, state: 'analyzing', stage: `Matching · ${pairs} / ${totalPairs} pairs`, progress: 0.55 + 0.35 * pairs / totalPairs });
        if (pairs >= totalPairs) phase = 2;
      } else if (phase < 6) {
        const st = ['', '', 'Fine-tuning', 'Lining up', 'Checking clocks', 'Checking clocks'][phase];
        App.on('progress', { pid: P.id, state: 'analyzing', stage: st, progress: 0.9 + phase * 0.02 });
        phase++;
      } else {
        clearInterval(timer);
        const p = synced(P, truth);
        App.on('progress', { pid: P.id, state: 'review', stage: p.stage, progress: 1 });
        const out = pub(); delete out.env;
        App.on('synced', out);
        App.on('projects', rows());
      }
    }, 70);
  }

  start(proxy).then(() => { if (MODE === 'sync') setTimeout(() => proxy.sync(), 2400); });
}
