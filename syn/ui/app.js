// SYN UI. Talks to Python through window.pywebview.api; Python pushes changes back by
// calling App.on(event, payload). The timeline is one canvas so 40+ tracks and hundreds
// of clips stay smooth; track names are DOM beside it.
(function () {
  const ICONS = {
    upload: '<path d="M12 15V4"/><path d="m7 9 5-5 5 5"/><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
    folder: '<path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9L9.6 3.6A2 2 0 0 0 8.2 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z"/>',
    layers: '<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/>',
    film: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 3v18M17 3v18M3 8h4M3 16h4M17 8h4M17 16h4"/>',
    wave: '<path d="M3 12h2M7 8v8M11 5v14M15 9v6M19 7v10M21 12h0"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    alert: '<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
    info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    download: '<path d="M12 4v11"/><path d="m7 10 5 5 5-5"/><path d="M4 20h16"/>',
    refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.4L21 8"/><path d="M21 3v5h-5"/>',
    bolt: '<path d="M13 2 3 14h9l-1 8 10-12h-9z"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    reveal: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    rows: '<path d="M3 6h18M3 12h18M3 18h18"/>',
    fit: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
    sync: '<path d="M4 7h11M4 17h11"/><circle cx="18" cy="7" r="2"/><circle cx="18" cy="17" r="2"/><path d="M18 9v6"/>',
    send: '<path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4z"/>',
    save: '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><path d="M17 21v-8H7v8M7 3v5h8"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    minus: '<path d="M5 12h14"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    ear: '<path d="M6 8.5a6 6 0 1 1 12 0c0 6-6 6-6 11a3 3 0 0 1-5 2"/><path d="M15 8.5a3 3 0 1 0-6 0"/>',
    trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>',
  };
  const icon = (n) => `<svg class="i" viewBox="0 0 24 24">${ICONS[n] || ''}</svg>`;
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const plural = (n, w, ws) => `${n} ${n === 1 ? w : (ws || w + 's')}`;
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  document.querySelectorAll('[data-icon]').forEach((el) => {
    const svg = icon(el.dataset.icon);
    if (el.tagName === 'I') el.outerHTML = svg; else el.insertAdjacentHTML('afterbegin', svg);
  });

  let api = null, settings = {}, upd = null, bridge = { clients: [], pending: [], connected: false }, plugin = {}, hasPlugin = false;
  let projects = [], P = null, modal = null, home = '', platform = '';
  const ACCENT = '#ccff4d', WARN = '#ffb359', DANGER = '#ff6b66';

  // ======================================================================
  // project state
  // ======================================================================
  const view = { t0: 0, pps: 4, scrollY: 0, sel: null, filter: 'all', hover: null, drag: null, fitted: false };
  const envs = new Map();      // clip id -> {rate, data: Uint8Array}
  const reading = new Set();   // clip ids being listened to right now
  const anim = new Map();      // clip id -> {from, to, t0, dur, delay}
  const landed = new Map();    // clip id -> time it landed (for the lock flash)
  let lanes = [], laneY = [], sections = [], clipsById = new Map(), contentH = 0;

  const laneH = () => (settings.density === 'compact' ? 24 : 42);
  const confClass = (c) => (c >= 0.8 ? 'hi' : c >= 0.5 ? 'mid' : 'lo');
  function statusOf(c) {
    if (!P) return 'pending';
    if (c.status === 'excluded') return 'excluded';
    if (c.status === 'offline') return 'offline';
    if (P.state !== 'review') return c.status === 'unsynced' && c.error ? 'unsynced' : 'pending';
    return c.status;
  }
  const needsCheck = (c) => ['low', 'unsynced', 'offline'].includes(statusOf(c));

  function decodeEnv(e) {
    if (!e) return null;
    const bin = atob(e.data);
    const arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    return { rate: e.rate, data: arr };
  }

  function setProject(p, opts) {
    const same = P && p && P.id === p.id;
    P = p;
    if (!same) { envs.clear(); reading.clear(); anim.clear(); landed.clear(); view.sel = null; view.fitted = false; view.scrollY = 0; }
    if (!p) { renderAll(); return; }
    if (p.env) for (const [id, e] of Object.entries(p.env)) if (e) envs.set(id, decodeEnv(e));
    indexClips();
    layoutPre();
    if (!view.fitted || (opts && opts.fit)) { fit(); view.fitted = true; }
    renderAll();
  }

  function indexClips() {
    clipsById = new Map(P.clips.map((c) => [c.id, c]));
    buildLanes();
  }

  function buildLanes() {
    lanes = P.lanes.map((ln) => ({ ...ln, clips: P.clips.filter((c) => c.lanes.includes(ln.id)) }));
    // with a filter, only lanes holding matching clips stay
    if (view.filter !== 'all' && P.state === 'review') {
      const want = view.filter === 'check' ? needsCheck : (c) => ['unsynced', 'offline'].includes(statusOf(c));
      lanes = lanes.filter((ln) => ln.clips.some(want));
    }
    // sections: video tracks, then audio tracks
    laneY = []; sections = [];
    let y = 0;
    let lastKind = null;
    const h = laneH();
    for (const ln of lanes) {
      if (ln.kind !== lastKind && P.kind === 'sequence') {
        sections.push({ y, label: ln.kind === 'video' ? `Video · ${lanes.filter((l) => l.kind === 'video').length}` : `Audio · ${lanes.filter((l) => l.kind === 'audio').length}` });
        y += 22; lastKind = ln.kind;
      }
      laneY.push(y);
      y += h;
    }
    contentH = y + 40;
  }

  // Before syncing, clips sit where the sequence had them (or one after another per lane).
  const pre = new Map();
  function layoutPre() {
    pre.clear();
    for (const ln of P.lanes) {
      let t = 0;
      for (const c of P.clips.filter((c) => c.lanes.includes(ln.id))) {
        if (pre.has(c.id)) continue;
        if (c.orig != null) { pre.set(c.id, c.orig); continue; }
        pre.set(c.id, t);
        t += (c.duration || 10) + 2;
      }
    }
  }

  // Where a clip is drawn right now (seconds).
  const unsyncedAt = new Map();
  function placeUnsynced() {
    unsyncedAt.clear();
    if (!P || P.state !== 'review') return;
    let end = 0;
    for (const c of P.clips) if (c.at != null) end = Math.max(end, c.at + c.duration);
    let t = end + 5;
    for (const c of P.clips) if (c.at == null) { unsyncedAt.set(c.id, t); t += (c.duration || 10) + 1; }
  }
  function posOf(c, now) {
    const a = anim.get(c.id);
    if (a) {
      const k = clamp((now - a.t0 - a.delay) / a.dur, 0, 1);
      if (k >= 1) { anim.delete(c.id); landed.set(c.id, now); }
      const e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
      return a.from + (a.to - a.from) * e;
    }
    if (view.drag && view.drag.id === c.id) return view.drag.at;
    if (P.state === 'review') return c.at != null ? c.at : (unsyncedAt.get(c.id) ?? pre.get(c.id) ?? 0);
    return pre.get(c.id) ?? 0;
  }
  function extent() {
    let a = Infinity, b = -Infinity;
    for (const c of P.clips) {
      const s = P.state === 'review' ? (c.at != null ? c.at : unsyncedAt.get(c.id)) : pre.get(c.id);
      if (s == null) continue;
      a = Math.min(a, s); b = Math.max(b, s + (c.duration || 0));
    }
    if (!isFinite(a)) { a = 0; b = 60; }
    return [a, Math.max(b, a + 1)];
  }

  // ======================================================================
  // timeline canvas
  // ======================================================================
  const cv = $('#tl'), ctx = cv.getContext('2d');
  const ov = $('#overview'), octx = ov.getContext('2d');
  const RULER = 26;
  let W = 0, H = 0, dpr = 1, raf = 0;

  function resize() {
    dpr = window.devicePixelRatio || 1;
    const r = cv.getBoundingClientRect();
    W = r.width; H = r.height;
    cv.width = Math.max(1, W * dpr); cv.height = Math.max(1, H * dpr);
    const o = ov.getBoundingClientRect();
    ov.width = Math.max(1, o.width * dpr); ov.height = Math.max(1, o.height * dpr);
    draw();
  }
  window.addEventListener('resize', () => { resize(); renderHeads(); });

  function fit() {
    if (!P || !W) { requestAnimationFrame(() => P && W && fit()); return; }
    placeUnsynced();
    const [a, b] = extent();
    const pad = (b - a) * 0.03 + 1;
    view.pps = clamp((W - 20) / (b - a + 2 * pad), 0.005, 400);
    view.t0 = a - pad;
    view.scrollY = clamp(view.scrollY, 0, Math.max(0, contentH - (H - RULER)));
    draw(); renderHeads();
  }

  const xOf = (t) => (t - view.t0) * view.pps;
  const tOf = (x) => x / view.pps + view.t0;

  function tickStep() {
    const steps = [1 / 24, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200];
    for (const s of steps) if (s * view.pps >= 80) return s;
    return 7200;
  }
  function tc(t, frames) {
    const neg = t < 0; t = Math.abs(t);
    const fps = P ? P.fps : 24;
    const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = Math.floor(t % 60);
    const pad = (n) => String(n).padStart(2, '0');
    let out = `${pad(h)}:${pad(m)}:${pad(s)}`;
    if (frames) out += ':' + pad(Math.floor((t % 1) * Math.round(fps) + 1e-6));
    return (neg ? '−' : '') + out;
  }

  function roundRect(c, x, y, w, h, r) {
    r = Math.min(r, w / 2, h / 2);
    c.beginPath();
    c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath();
  }

  const COLORS = {
    pending: ['rgba(255,255,255,.07)', 'rgba(255,255,255,.34)', 'rgba(255,255,255,.12)'],
    synced: ['rgba(204,255,77,.13)', 'rgba(204,255,77,.85)', 'rgba(204,255,77,.4)'],
    low: ['rgba(255,179,89,.13)', 'rgba(255,179,89,.85)', 'rgba(255,179,89,.5)'],
    unsynced: ['rgba(255,107,102,.08)', 'rgba(255,107,102,.6)', 'rgba(255,107,102,.4)'],
    offline: ['rgba(255,107,102,.05)', 'rgba(255,107,102,.4)', 'rgba(255,107,102,.3)'],
    excluded: ['rgba(255,255,255,.03)', 'rgba(255,255,255,.2)', 'rgba(255,255,255,.08)'],
  };

  function draw() {
    if (raf) return;
    raf = requestAnimationFrame(frame);
  }
  function frame(now) {
    raf = 0;
    if (!P || $('#timeline').classList.contains('hidden')) return;
    const c = ctx;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, W, H);
    const h = laneH();
    const busy = P.state === 'analyzing';
    const matching = busy && /Match|Fine|Lining|Checking/.test(P.stage || '');
    // lanes
    c.save();
    c.beginPath(); c.rect(0, RULER, W, H - RULER); c.clip();
    for (const s of sections) {
      const y = RULER + s.y - view.scrollY;
      if (y > H || y + 22 < RULER) continue;
      c.fillStyle = 'rgba(255,255,255,.015)'; c.fillRect(0, y, W, 22);
    }
    const tOn = new Set();
    if (view.sel) tOn.add(view.sel);
    let animating = anim.size > 0 || reading.size > 0 || busy;
    for (let i = 0; i < lanes.length; i++) {
      const ln = lanes[i];
      const y = RULER + laneY[i] - view.scrollY;
      if (y > H || y + h < RULER) continue;
      c.fillStyle = i % 2 ? 'rgba(255,255,255,.012)' : 'rgba(0,0,0,0)';
      c.fillRect(0, y, W, h);
      c.fillStyle = 'rgba(255,255,255,.035)'; c.fillRect(0, y + h - 1, W, 1);
      for (const cl of ln.clips) {
        const st = statusOf(cl);
        if (view.filter !== 'all' && P.state === 'review') {
          const show = view.filter === 'check' ? needsCheck(cl) : ['unsynced', 'offline'].includes(st);
          if (!show) { drawClip(c, cl, ln, y, h, now, st, true); continue; }
        }
        drawClip(c, cl, ln, y, h, now, st, false);
        if (landed.has(cl.id) && now - landed.get(cl.id) < 700) animating = true;
      }
    }
    // matching sweep: a soft lime band crossing every lane while pairs are compared
    if (matching) {
      const k = (now / 1600) % 1;
      const x = k * (W + 300) - 150;
      const g = c.createLinearGradient(x - 150, 0, x + 150, 0);
      g.addColorStop(0, 'rgba(204,255,77,0)'); g.addColorStop(0.5, 'rgba(204,255,77,.07)'); g.addColorStop(1, 'rgba(204,255,77,0)');
      c.fillStyle = g; c.fillRect(x - 150, RULER, 300, H - RULER);
    }
    c.restore();
    // ruler
    c.fillStyle = '#0e0e10'; c.fillRect(0, 0, W, RULER);
    c.fillStyle = 'rgba(255,255,255,.06)'; c.fillRect(0, RULER - 1, W, 1);
    const step = tickStep();
    const first = Math.floor(view.t0 / step) * step;
    c.font = '500 10.5px ' + getComputedStyle(document.body).fontFamily;
    c.textBaseline = 'middle';
    for (let t = first; xOf(t) < W; t += step) {
      const x = Math.round(xOf(t)) + 0.5;
      if (x < -50) continue;
      c.fillStyle = 'rgba(255,255,255,.18)'; c.fillRect(x, RULER - 8, 1, 7);
      c.fillStyle = 'rgba(255,255,255,.42)';
      c.fillText(tc(t, step < 1), x + 4, RULER / 2 - 1);
      for (let k = 1; k < 4; k++) {
        const xs = Math.round(xOf(t + (step * k) / 4)) + 0.5;
        c.fillStyle = 'rgba(255,255,255,.08)'; c.fillRect(xs, RULER - 4, 1, 3);
      }
    }
    drawOverview();
    if (animating) draw();
  }

  function drawClip(c, cl, ln, y, h, now, st, dim) {
    const t = posOf(cl, now);
    const x = xOf(t), w = Math.max(2, cl.duration * view.pps);
    if (x > W || x + w < 0) return;
    const pad = h > 30 ? 4 : 3;
    const top = y + pad, ch = h - pad * 2;
    const sel = view.sel === cl.id;
    const hov = view.hover === cl.id;
    const [fill, edge, wave] = COLORS[st] || COLORS.pending;
    c.globalAlpha = dim ? 0.25 : 1;
    roundRect(c, x, top, w, ch, 5);
    c.fillStyle = fill; c.fill();
    // waveform
    const env = envs.get(cl.id);
    if (env && w > 6) {
      c.save(); roundRect(c, x, top, w, ch, 5); c.clip();
      c.fillStyle = st === 'pending' && reading.has(cl.id) ? 'rgba(204,255,77,.5)' : wave;
      const mid = top + ch / 2;
      const x0 = Math.max(0, x), x1 = Math.min(W, x + w);
      const per = env.rate / view.pps;   // env samples per pixel
      for (let px = Math.floor(x0); px < x1; px += 2) {
        const s0 = Math.floor((px - x) * per), s1 = Math.max(s0 + 1, Math.floor((px + 2 - x) * per));
        let m = 0;
        for (let s = s0; s < s1 && s < env.data.length; s++) if (env.data[s] > m) m = env.data[s];
        const a = (m / 255) * (ch / 2 - 2);
        if (a > 0.4) c.fillRect(px, mid - a, 1.4, a * 2);
      }
      c.restore();
    }
    // listening: a lime scan line sweeping the clip while its sound is read
    if (reading.has(cl.id)) {
      const k = (now / 900) % 1;
      const sx = x + k * w;
      const g = c.createLinearGradient(sx - 40, 0, sx, 0);
      g.addColorStop(0, 'rgba(204,255,77,0)'); g.addColorStop(1, 'rgba(204,255,77,.45)');
      c.save(); roundRect(c, x, top, w, ch, 5); c.clip();
      c.fillStyle = g; c.fillRect(sx - 40, top, 40, ch);
      c.fillStyle = ACCENT; c.fillRect(sx, top, 1.5, ch);
      c.restore();
    }
    // edge
    roundRect(c, x + 0.5, top + 0.5, w - 1, ch - 1, 5);
    c.lineWidth = sel ? 2 : 1;
    c.strokeStyle = sel ? '#fff' : (hov ? 'rgba(255,255,255,.5)' : edge);
    if (st === 'unsynced' || st === 'offline') c.setLineDash([4, 3]);
    c.stroke(); c.setLineDash([]);
    // lock flash when it lands
    const lt = landed.get(cl.id);
    if (lt != null && now - lt < 700) {
      const k = (now - lt) / 700;
      roundRect(c, x - 3 * k, top - 3 * k, w + 6 * k, ch + 6 * k, 6);
      c.strokeStyle = `rgba(204,255,77,${0.8 * (1 - k)})`; c.lineWidth = 2; c.stroke();
    }
    // label
    if (w > 46 && h > 20) {
      c.save(); c.beginPath(); c.rect(x + 6, top, w - 12, ch); c.clip();
      c.font = `600 ${h > 30 ? 11 : 10}px ` + getComputedStyle(document.body).fontFamily;
      c.textBaseline = 'top';
      c.fillStyle = 'rgba(255,255,255,.9)';
      const ty = h > 30 ? top + 4 : top + (ch - 11) / 2;
      // the confidence sits at the right end; the name gets whatever room is left
      let label = '', tw = 0;
      if (P.state === 'review' && (st === 'synced' || st === 'low') && w > 90) {
        label = Math.round(cl.confidence * 100) + '%';
        tw = c.measureText(label).width;
      }
      const lx = label ? Math.min(x + w - tw - 8, Math.max(x + 7, W - tw - 8)) : x + w;
      c.save(); c.beginPath(); c.rect(x + 6, top, Math.max(0, lx - x - 12), ch); c.clip();
      c.fillText(cl.name, x + 7, ty);
      c.restore();
      if (label) { c.fillStyle = st === 'synced' ? ACCENT : WARN; c.fillText(label, lx, ty); }
      c.restore();
    }
    c.globalAlpha = 1;
  }

  function drawOverview() {
    const c = octx;
    const w = ov.width / dpr, h = ov.height / dpr;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, w, h);
    if (!P || !P.clips.length) return;
    const [a, b] = extent();
    const span = b - a || 1;
    const n = Math.max(1, P.lanes.length);
    const lh = Math.max(1, (h - 4) / n);
    P.lanes.forEach((ln, i) => {
      for (const cl of P.clips) {
        if (!cl.lanes.includes(ln.id)) continue;
        const st = statusOf(cl);
        const s = P.state === 'review' ? (cl.at != null ? cl.at : unsyncedAt.get(cl.id)) : pre.get(cl.id);
        if (s == null) continue;
        c.fillStyle = st === 'synced' ? 'rgba(204,255,77,.55)' : st === 'low' ? 'rgba(255,179,89,.6)' :
          st === 'unsynced' || st === 'offline' ? 'rgba(255,107,102,.5)' : 'rgba(255,255,255,.25)';
        c.fillRect(((s - a) / span) * w, 2 + i * lh, Math.max(1, (cl.duration / span) * w), Math.max(1, lh - (lh > 3 ? 1 : 0)));
      }
    });
    // viewport
    const vx = ((view.t0 - a) / span) * w, vw = (W / view.pps / span) * w;
    c.strokeStyle = 'rgba(255,255,255,.55)'; c.lineWidth = 1;
    roundRect(c, clamp(vx, 0, w - 2) + 0.5, 0.5, Math.max(6, Math.min(vw, w)) - 1, h - 1, 4); c.stroke();
    c.fillStyle = 'rgba(255,255,255,.04)'; c.fill();
  }

  // ---- track headers ----
  function renderHeads() {
    const box = $('#heads-inner');
    if (!P) { box.innerHTML = ''; return; }
    const h = laneH();
    let html = '';
    for (const s of sections) html += `<div class="sec-head" style="top:${s.y}px">${esc(s.label)}</div>`;
    lanes.forEach((ln, i) => {
      const cl = ln.clips;
      const worst = P.state === 'review' ? (cl.some((c) => ['unsynced', 'offline'].includes(statusOf(c))) ? 'lo' : cl.some((c) => statusOf(c) === 'low') ? 'mid' : 'hi') : '';
      const sel = view.sel && cl.some((c) => c.id === view.sel);
      html += `<div class="lh ${ln.kind} ${h < 30 ? 'compact' : ''} ${sel ? 'sel' : ''}" style="top:${laneY[i]}px;height:${h}px">
        <span class="k">${esc((ln.label || '').length <= 4 ? ln.label : (ln.kind === 'video' ? 'V' : 'A'))}</span>
        <div class="t"><b>${esc(ln.name || ln.label)}</b><span>${plural(cl.length, 'clip')}</span></div>
        ${worst ? `<i class="dot ${worst}"></i>` : ''}</div>`;
    });
    box.innerHTML = html;
    box.style.height = contentH + 'px';
    syncScroll();
  }
  function syncScroll() {
    $('#heads-inner').style.transform = `translateY(${RULER - view.scrollY}px)`;
    const vh = H - RULER;
    const th = $('#vthumb');
    if (contentH <= vh) { th.style.display = 'none'; return; }
    th.style.display = '';
    const k = vh / contentH;
    th.style.height = Math.max(24, vh * k) + 'px';
    th.style.top = RULER + (view.scrollY / (contentH - vh)) * (vh - Math.max(24, vh * k)) + 'px';
  }

  // ---- interaction ----
  function hit(mx, my) {
    const h = laneH();
    const now = performance.now();
    for (let i = 0; i < lanes.length; i++) {
      const y = RULER + laneY[i] - view.scrollY;
      if (my < y || my > y + h) continue;
      for (const cl of lanes[i].clips) {
        const x = xOf(posOf(cl, now)), w = Math.max(4, cl.duration * view.pps);
        if (mx >= x && mx <= x + w) return { clip: cl, lane: i };
      }
    }
    return null;
  }
  const wrap = $('#lanes-wrap');
  wrap.addEventListener('wheel', (e) => {
    if (!P) return;
    e.preventDefault();
    const r = cv.getBoundingClientRect();
    const mx = e.clientX - r.left;
    if (e.ctrlKey || e.metaKey) {
      const t = tOf(mx);
      const f = Math.exp(-e.deltaY * (e.ctrlKey && !e.metaKey && Math.abs(e.deltaY) < 30 ? 0.02 : 0.004));
      view.pps = clamp(view.pps * f, 0.002, 600);
      view.t0 = t - mx / view.pps;
    } else if (e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
      view.t0 += (e.shiftKey ? e.deltaY : e.deltaX) / view.pps;
    } else {
      view.scrollY = clamp(view.scrollY + e.deltaY, 0, Math.max(0, contentH - (H - RULER)));
      syncScroll();
    }
    draw();
  }, { passive: false });
  wrap.addEventListener('mousemove', (e) => {
    if (!P) return;
    const r = cv.getBoundingClientRect();
    const mx = e.clientX - r.left, my = e.clientY - r.top;
    if (view.drag) {
      const d = view.drag;
      if (d.pan) { view.t0 = d.t0 - (mx - d.mx) / view.pps; draw(); return; }
      const fps = P.fps;
      const dt = Math.round(((mx - d.mx) / view.pps) * fps) / fps;
      d.moved = d.moved || Math.abs(mx - d.mx) > 3;
      if (d.moved && P.state === 'review' && d.base != null) { d.at = d.base + dt; d.dt = dt; draw(); showTip(e, d.clip, dt); }
      return;
    }
    const h = hit(mx, my);
    const id = h ? h.clip.id : null;
    if (id !== view.hover) { view.hover = id; draw(); }
    if (h) showTip(e, h.clip); else $('#tip').classList.add('hidden');
    cv.style.cursor = h && P.state === 'review' ? 'grab' : 'default';
  });
  wrap.addEventListener('mouseleave', () => { view.hover = null; $('#tip').classList.add('hidden'); draw(); });
  wrap.addEventListener('mousedown', (e) => {
    if (!P) return;
    const r = cv.getBoundingClientRect();
    const mx = e.clientX - r.left, my = e.clientY - r.top;
    const h = my > RULER ? hit(mx, my) : null;
    if (h) {
      select(h.clip.id);
      view.drag = { id: h.clip.id, clip: h.clip, mx, base: h.clip.at, at: h.clip.at, moved: false };
    } else {
      view.drag = { pan: true, mx, t0: view.t0 };
      if (my > RULER) select(null);
    }
  });
  window.addEventListener('mouseup', async () => {
    const d = view.drag;
    view.drag = null;
    if (d && !d.pan && d.moved && d.dt) {
      const c = clipsById.get(d.id);
      const p = await api.nudge(P.id, d.id, (c.nudge || 0) + d.dt);
      applyPublic(p);
      toast(`Moved ${c.name} by ${d.dt > 0 ? '+' : ''}${Math.round(d.dt * P.fps)} frames`);
    }
    $('#tip').classList.add('hidden');
    draw();
  });

  function showTip(e, c, dt) {
    const tip = $('#tip');
    const st = statusOf(c);
    const what = { synced: 'Synced', low: 'Check this one', unsynced: 'Not synced', offline: 'Media offline', excluded: 'Left out', pending: c.error || 'Not synced yet' }[st];
    tip.innerHTML = `<b>${esc(c.name)}</b><span>${esc(what)}${P.state === 'review' && (st === 'synced' || st === 'low') ? ` · ${Math.round(c.confidence * 100)}%` : ''}</span>
      ${dt != null ? `<span>${dt > 0 ? '+' : ''}${Math.round(dt * P.fps)} frames</span>` : `<span>${tc(c.duration, true)} long</span>`}`;
    const r = wrap.getBoundingClientRect();
    tip.style.left = clamp(e.clientX - r.left + 14, 0, r.width - 290) + 'px';
    tip.style.top = clamp(e.clientY - r.top + 14, 0, r.height - 80) + 'px';
    tip.classList.remove('hidden');
  }

  // overview: click or drag to move the view
  let ovDrag = false;
  const ovJump = (e) => {
    const r = ov.getBoundingClientRect();
    const [a, b] = extent();
    const t = a + ((e.clientX - r.left) / r.width) * (b - a);
    view.t0 = t - W / view.pps / 2;
    draw();
  };
  ov.addEventListener('mousedown', (e) => { ovDrag = true; ovJump(e); });
  window.addEventListener('mousemove', (e) => { if (ovDrag) ovJump(e); });
  window.addEventListener('mouseup', () => { ovDrag = false; });
  // vertical scrollbar
  let vDrag = null;
  $('#vthumb').addEventListener('mousedown', (e) => { vDrag = { y: e.clientY, s: view.scrollY }; e.preventDefault(); });
  window.addEventListener('mousemove', (e) => {
    if (!vDrag) return;
    const vh = H - RULER;
    view.scrollY = clamp(vDrag.s + ((e.clientY - vDrag.y) * contentH) / vh, 0, Math.max(0, contentH - vh));
    syncScroll(); draw();
  });
  window.addEventListener('mouseup', () => { vDrag = null; });
  $('#heads').addEventListener('wheel', (e) => {
    e.preventDefault();
    view.scrollY = clamp(view.scrollY + e.deltaY, 0, Math.max(0, contentH - (H - RULER)));
    syncScroll(); draw();
  }, { passive: false });

  document.addEventListener('keydown', (e) => {
    if (!P || modal || e.target.tagName === 'INPUT') return;
    const fps = P.fps;
    if (e.key === 'f' || e.key === 'F') fit();
    else if ((e.metaKey || e.ctrlKey) && (e.key === '=' || e.key === '+')) { zoomBy(1.6); e.preventDefault(); }
    else if ((e.metaKey || e.ctrlKey) && e.key === '-') { zoomBy(1 / 1.6); e.preventDefault(); }
    else if ((e.metaKey || e.ctrlKey) && (e.key === 'e' || e.key === 'E')) { doExport(e.shiftKey); e.preventDefault(); }
    else if (e.key === 'Escape') select(null);
    else if (view.sel && P.state === 'review' && (e.key === ',' || e.key === '.' || e.key === '<' || e.key === '>')) {
      const step = (e.key === ',' || e.key === '<' ? -1 : 1) * (e.shiftKey ? 10 : 1);
      nudgeSel(step / fps);
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Tab') {
      const list = orderedClips();
      if (!list.length) return;
      const i = list.findIndex((c) => c.id === view.sel);
      const back = e.key === 'ArrowUp' || (e.key === 'Tab' && e.shiftKey);
      const n = list[(i + (back ? -1 : 1) + list.length) % list.length];
      select(n.id, true); e.preventDefault();
    }
  });
  function orderedClips() {
    const want = view.filter === 'check' ? needsCheck : view.filter === 'unsynced' ? (c) => ['unsynced', 'offline'].includes(statusOf(c)) : () => true;
    return P.clips.filter(want).sort((a, b) => (posOf(a, 0) - posOf(b, 0)));
  }
  function zoomBy(f) {
    const mid = tOf(W / 2);
    view.pps = clamp(view.pps * f, 0.002, 600);
    view.t0 = mid - W / 2 / view.pps;
    draw();
  }

  function select(id, reveal) {
    view.sel = id;
    renderInspector();
    renderHeads();
    if (id && reveal) {
      const c = clipsById.get(id);
      const t = posOf(c, 0);
      if (xOf(t) < 0 || xOf(t + c.duration) > W) view.t0 = t - (W * 0.2) / view.pps;
      const li = lanes.findIndex((ln) => ln.clips.some((x) => x.id === id));
      if (li >= 0) {
        const y = laneY[li];
        if (y < view.scrollY || y + laneH() > view.scrollY + H - RULER) view.scrollY = clamp(y - 60, 0, Math.max(0, contentH - (H - RULER)));
        syncScroll();
      }
    }
    draw();
  }

  async function nudgeSel(dt) {
    const c = clipsById.get(view.sel);
    if (!c) return;
    applyPublic(await api.nudge(P.id, c.id, Math.round(((c.nudge || 0) + dt) * 1e4) / 1e4));
  }

  function applyPublic(p) {
    if (!p) return;
    P = { ...p, env: undefined };
    indexClips();
    placeUnsynced();
    renderAll(true);
  }

  // ======================================================================
  // inspector
  // ======================================================================
  function ring(conf, size, st) {
    const r = 15.5, C = 2 * Math.PI * r;
    const col = st === 'unsynced' || st === 'offline' ? DANGER : conf >= 0.8 ? ACCENT : conf >= 0.5 ? WARN : DANGER;
    const k = st === 'unsynced' || st === 'offline' ? 0 : conf;
    return `<svg viewBox="0 0 36 36" style="width:${size}px;height:${size}px"><circle cx="18" cy="18" r="${r}" fill="none" stroke="rgba(255,255,255,.08)" stroke-width="3"/>
      <circle cx="18" cy="18" r="${r}" fill="none" stroke="${col}" stroke-width="3" stroke-linecap="round" stroke-dasharray="${C * k} ${C}" transform="rotate(-90 18 18)" class="ring-arc"/>
      ${size >= 40 ? `<text x="18" y="18.5" text-anchor="middle" dominant-baseline="middle" fill="#fff" style="font:700 9px var(--font-display)">${st === 'unsynced' || st === 'offline' ? '—' : Math.round(conf * 100)}</text>` : ''}</svg>`;
  }

  function renderInspector() {
    const box = $('#inspector');
    const c = view.sel && clipsById.get(view.sel);
    if (!c || !P) { box.classList.add('hidden'); return; }
    box.classList.remove('hidden');
    const st = statusOf(c);
    const review = P.state === 'review';
    const title = { synced: 'Synced', low: 'Worth a look', unsynced: 'Not synced', offline: 'Media offline', excluded: 'Left out of the sync', pending: review ? 'Not synced' : 'Not synced yet' }[st];
    const sub = {
      synced: 'SYN is confident this clip is in the right place.',
      low: 'The match is likely right but weaker than usual. Check it in the timeline.',
      unsynced: c.error ? c.error : "Its sound didn't match any other clip. It goes at the end of the sequence.",
      offline: c.error || 'SYN can’t find this file.',
      excluded: 'It goes at the end of the sequence, not synced.',
      pending: c.error || (P.state === 'analyzing' ? 'Listening…' : 'Press Sync to place it.'),
    }[st];
    const why = [];
    if (review && c.matched) why.push(['good', 'link', `Matched to <b>${esc(c.matched)}</b>`]);
    if (review && c.overlap != null) why.push([c.overlap >= 10 ? 'good' : 'bad', 'wave', `${c.overlap >= 60 ? Math.round(c.overlap / 60) + ' min' : Math.round(c.overlap) + ' s'} of shared sound`]);
    if (review && c.z != null) why.push([c.z >= 12 ? 'good' : 'bad', 'ear', `Match ${Math.round(c.z / 4.5 * 10) / 10}× stronger than chance`]);
    if (review && c.agree) why.push(['good', 'check', `${plural(c.agree, 'other match agrees', 'other matches agree')}`]);
    if (review && c.disagree) why.push(['bad', 'alert', 'Another match points somewhere else']);
    if (review && c.drift != null && Math.abs(c.drift) >= 20) {
      const perFrame = 1 / P.fps / (Math.abs(c.drift) * 1e-6) / 60;
      why.push(['bad', 'clock', `Clock drifts ${c.drift > 0 ? '+' : ''}${c.drift} ppm (a frame every ${Math.round(perFrame)} min)`]);
    } else if (review && c.drift != null) why.push(['good', 'clock', 'Clocks agree, no drift']);
    const curve = review && c.curve && c.curve.length > 3 ? curveSVG(c.curve) : '';
    const placed = review && c.at != null;
    box.innerHTML = `
      <div class="ins-head"><div class="t"><b>${esc(c.name)}</b><span>${esc(tildify(c.path))}</span></div>
        <button class="btn-icon" data-a="close" title="Close (Esc)">${icon('x')}</button></div>
      <div class="ins-body">
        <div class="ins-conf">${ring(c.confidence, 64, st)}<div class="t"><b>${title}</b><span>${esc(sub)}</span></div></div>
        ${why.length ? `<div class="why">${why.map(([cls, ic, t]) => `<div class="${cls}">${icon(ic)}<span>${t}</span></div>`).join('')}</div>` : ''}
        ${curve}
        ${placed ? `<div class="pos">
          <div class="label">Position in the synced sequence</div>
          <div class="tc">${tc(c.at, true)}${c.nudge ? `<small>${c.nudge > 0 ? '+' : ''}${Math.round(c.nudge * P.fps)}f by hand</small>` : ''}</div>
          <div class="nudges"><button data-n="-10">−10f</button><button data-n="-1">−1f</button><button data-n="1">+1f</button><button data-n="10">+10f</button>
            ${c.nudge ? '<button data-n="0">Reset</button>' : ''}</div></div>` : ''}
        <div class="ins-acts">
          ${review && st === 'low' ? `<button class="btn-quiet" data-a="ok">${icon('check')}It's right, mark as checked</button>` : ''}
          ${review && c.forced ? `<button class="btn-quiet" data-a="unok">${icon('eye')}Mark as needing a check</button>` : ''}
          ${st === 'offline' ? `<button class="btn-quiet" data-a="relink">${icon('search')}Find missing media…</button>` : ''}
          ${st === 'excluded' ? `<button class="btn-quiet" data-a="include">${icon('plus')}Include in the sync</button>`
            : (st !== 'offline' ? `<button class="btn-quiet" data-a="exclude">${icon('minus')}Leave out of the sync</button>` : '')}
          ${c.path ? `<button class="btn-quiet" data-a="reveal">${icon('reveal')}Show in ${platform === 'darwin' ? 'Finder' : 'Explorer'}</button>` : ''}
        </div>
        ${placed ? `<div class="kbd"><b>,</b> <b>.</b> nudge a frame · <b>⇧</b> for 10 · drag to move · <b>↑</b> <b>↓</b> next clip</div>` : ''}
      </div>`;
  }
  $('#inspector').addEventListener('click', async (e) => {
    const n = e.target.closest('[data-n]');
    const a = e.target.closest('[data-a]');
    const c = clipsById.get(view.sel);
    if (!c) return;
    if (n) {
      const v = +n.dataset.n;
      if (v === 0) applyPublic(await api.nudge(P.id, c.id, 0)); else nudgeSel(v / P.fps);
      return;
    }
    if (!a) return;
    const act = a.dataset.a;
    if (act === 'close') select(null);
    else if (act === 'ok') applyPublic(await api.mark_checked(P.id, c.id, true));
    else if (act === 'unok') applyPublic(await api.mark_checked(P.id, c.id, false));
    else if (act === 'exclude') applyPublic(await api.set_excluded(P.id, c.id, true));
    else if (act === 'include') { applyPublic(await api.set_excluded(P.id, c.id, false)); toast('Press Sync again to place it'); }
    else if (act === 'reveal') api.reveal(c.path);
    else if (act === 'relink') api.relink(P.id);
  });

  function curveSVG(v) {
    const w = 260, h = 56;
    const n = v.length;
    const pts = v.map((y, i) => `${(i / (n - 1)) * w},${h - 4 - clamp(y, -0.2, 1) * (h - 10)}`).join(' ');
    return `<div class="curve"><svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
      <line x1="${w / 2}" y1="0" x2="${w / 2}" y2="${h}" stroke="rgba(204,255,77,.35)" stroke-dasharray="2 3"/>
      <polyline points="${pts}" fill="none" stroke="${ACCENT}" stroke-width="1.6" stroke-linejoin="round"/></svg>
      <div class="cap"><span>−3 s</span><span>How well the sound matches at each offset</span><span>+3 s</span></div></div>`;
  }
  const tildify = (p) => (home && p && p.startsWith(home) ? '~' + p.slice(home.length) : p || '');

  // ======================================================================
  // sidebar, top bar, banner
  // ======================================================================
  function renderAll(keepInspector) {
    const has = !!P;
    $('#empty').classList.toggle('hidden', has);
    $('#timeline').classList.toggle('hidden', !has);
    if (has) { resize(); placeUnsynced(); }
    renderProjects();
    renderTop();
    renderBanner();
    renderAction();
    renderHeads();
    if (!keepInspector || !has) renderInspector(); else renderInspector();
    draw();
  }

  function renderProjects() {
    $('#projects-sect').classList.toggle('hidden', !projects.length);
    $('#projects-count').textContent = projects.length > 1 ? String(projects.length) : '';
    $('#projects').innerHTML = projects.map((p) => {
      const on = P && P.id === p.id;
      const sub = p.state === 'analyzing' ? `Syncing · ${Math.round(p.progress * 100)}%` : p.state === 'review'
        ? `${p.synced} of ${plural(p.clips, 'clip')} synced${p.imported ? ' · in Premiere' : p.job_state === 'done' ? ' · sent' : ''}`
        : p.job_state === 'queued' ? 'Waiting' : plural(p.clips, 'clip');
      const badge = p.state === 'analyzing' ? '<span class="spinner"></span>' : p.state === 'review' && p.synced > 1
        ? `<span class="pct ${confClass(p.overall)}">${Math.round(p.overall * 100)}%</span>` : '';
      return `<div class="proj ${on ? 'on' : ''}" data-id="${p.id}"><span class="pi">${icon(p.premiere ? 'link' : p.kind === 'sequence' ? 'layers' : 'film')}</span>
        <div class="t"><b>${esc(p.name)}</b><span>${esc(sub)}</span></div>${badge}
        <button class="btn-icon x" data-close="${p.id}" title="Close">${icon('x')}</button></div>`;
    }).join('');
  }
  $('#projects').addEventListener('click', async (e) => {
    const x = e.target.closest('[data-close]');
    if (x) { e.stopPropagation(); projects = await api.close_project(x.dataset.close); renderProjects(); return; }
    const row = e.target.closest('.proj');
    if (row && (!P || row.dataset.id !== P.id)) api.select(row.dataset.id);
  });

  function counts() {
    const out = { total: 0, synced: 0, low: 0, unsynced: 0, video: 0, audio: 0 };
    if (!P) return out;
    out.total = P.clips.length;
    for (const c of P.clips) {
      const st = statusOf(c);
      if (st === 'synced') out.synced++;
      else if (st === 'low') out.low++;
      else if (st === 'unsynced' || st === 'offline') out.unsynced++;
    }
    out.video = P.lanes.filter((l) => l.kind === 'video').length;
    out.audio = P.lanes.filter((l) => l.kind === 'audio').length;
    return out;
  }

  function renderTop() {
    if (!P) { $('#ptitle').innerHTML = ''; $('#stats').innerHTML = ''; $('#filter').classList.add('hidden'); return; }
    const k = counts();
    const job = projects.find((p) => p.id === P.id);
    $('#ptitle').innerHTML = `<b>${esc(P.name)}</b><span>${P.kind === 'sequence' ? 'Sequence' : 'Footage'} · ${plural(k.video, 'video track')} · ${plural(k.audio, 'audio track')}${job && job.premiere ? ' · from Premiere' : ''}</span>`;
    let stats = `<span class="stat"><b>${k.total}</b>clips</span>`;
    if (P.state === 'review') {
      stats = `<span class="stat conf">${ring(P.overall, 24, P.overall ? 'synced' : 'unsynced')}<b id="overall-n">${Math.round(P.overall * 100)}%</b>confidence</span>` + stats;
      if (k.low) stats += `<span class="stat"><b style="color:var(--warn)">${k.low}</b>to check</span>`;
      if (k.unsynced) stats += `<span class="stat"><b style="color:var(--danger)">${k.unsynced}</b>not synced</span>`;
    }
    $('#stats').innerHTML = stats;
    const showFilter = P.state === 'review' && (k.low || k.unsynced);
    $('#filter').classList.toggle('hidden', !showFilter);
    $('#n-check').textContent = k.low + k.unsynced || '';
    $('#n-unsynced').textContent = k.unsynced || '';
    if (!showFilter && view.filter !== 'all') { view.filter = 'all'; setTabs('#filter', 'all'); buildLanes(); }
  }

  function renderBanner() {
    const b = $('#banner');
    if (!P || P.state !== 'analyzing') { b.classList.add('hidden'); return; }
    b.classList.remove('hidden');
    const stage = P.stage || 'Starting';
    const listening = /Listen|Start/.test(stage);
    b.classList.toggle('match', !listening);
    $('#banner-title').textContent = listening ? 'Listening to every clip' : /Match/.test(stage) ? 'Matching the sound' : /Lining/.test(stage) ? 'Lining everything up' : stage.split(' · ')[0];
    $('#banner-sub').textContent = stage;
    $('#banner-bar').style.width = Math.round((P.progress || 0) * 100) + '%';
  }
  $('#banner-cancel').onclick = () => P && api.cancel(P.id);

  function renderAction() {
    const box = $('#side-action');
    if (!P) {
      box.innerHTML = `<button class="btn-primary" disabled>${icon('sync')}<span>Add an XML or footage</span></button>`;
      return;
    }
    const job = projects.find((p) => p.id === P.id);
    const premiere = job && job.premiere;
    const usable = P.clips.filter((c) => !['offline', 'excluded'].includes(c.status)).length;
    if (P.state === 'analyzing') {
      box.innerHTML = `<div class="sync-state"><span class="spinner"></span><div class="t"><b>Syncing ${Math.round((P.progress || 0) * 100)}%</b><span>${esc(P.stage || '')}</span></div>
        <button class="btn-quiet sm" data-act="cancel">Cancel</button></div><div class="progress"><div style="width:${Math.round((P.progress || 0) * 100)}%"></div></div>`;
    } else if (P.state === 'review') {
      const sent = job && (job.job_state === 'done');
      box.innerHTML = premiere
        ? `<button class="btn-primary lime" data-act="send">${icon('send')}<span>${sent ? 'Send to Premiere again' : 'Send to Premiere'}</span></button>
           <div class="row2"><button class="btn-quiet" data-act="save">${icon('save')}Save XML…</button><button class="btn-quiet" data-act="sync">${icon('refresh')}Sync again</button></div>`
        : `<button class="btn-primary" data-act="export">${icon('download')}<span>Save synced XML</span></button>
           <div class="row2"><button class="btn-quiet" data-act="save">${icon('save')}Save as…</button><button class="btn-quiet" data-act="sync">${icon('refresh')}Sync again</button></div>`;
      if (P.output) box.insertAdjacentHTML('beforeend', `<button class="sub" data-act="reveal-out" title="${esc(P.output)}">Saved · ${esc(P.output.split(/[\\/]/).pop())}</button>`);
    } else {
      const waiting = job && job.job_state === 'queued';
      box.innerHTML = `<button class="btn-primary" data-act="sync" ${usable < 2 || waiting ? 'disabled' : ''}>${icon('sync')}<span>${waiting ? 'Waiting for the last job…' : usable < 2 ? 'Needs two clips or more' : `Sync ${plural(usable, 'clip')}`}</span></button>`;
      const off = P.clips.filter((c) => c.status === 'offline').length;
      if (off) box.insertAdjacentHTML('beforeend', `<button class="sub" data-act="relink">${plural(off, 'file')} missing · Find them…</button>`);
    }
  }
  $('#side-action').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-act]');
    if (!b || !P) return;
    const a = b.dataset.act;
    if (a === 'sync') { select(null); api.sync(P.id); }
    else if (a === 'cancel') api.cancel(P.id);
    else if (a === 'export') doExport(false);
    else if (a === 'save') doExport(true);
    else if (a === 'send') {
      const r = await api.send_to_premiere(P.id);
      if (r) toast('Sent. The synced sequence is opening in Premiere');
    } else if (a === 'reveal-out') api.reveal(P.output);
    else if (a === 'relink') api.relink(P.id);
  });
  async function doExport(ask) {
    if (!P || P.state !== 'review') return;
    const info = await api.export(P.id, !!ask);
    if (info) {
      P.output = info.path;
      renderAction();
      toast(`Saved “${info.name}” · ${plural(info.video_tracks, 'video track')}, ${plural(info.audio_tracks, 'audio track')}`, false,
        { label: 'Show', run: () => api.reveal(info.path) });
    }
  }

  // ---- Premiere card ----
  function renderPremiere() {
    const box = $('#premiere');
    const pend = (bridge.pending || []).length;
    const clients = bridge.clients || [];
    const live = bridge.connected;
    const installed = plugin.installed, bundled = plugin.bundled;
    let dot = '', title, sub, btn = '';
    if (live) {
      const c = clients.slice().sort((a, b) => (b.seen || 0) - (a.seen || 0))[0];
      dot = 'on'; title = 'Connected'; sub = `${c ? esc(c.name) : 'Premiere Pro'} · send a sequence from the SYN panel`;
    } else if (!hasPlugin) {
      title = 'Premiere panel'; sub = 'Export Final Cut Pro XML from Premiere and drop it here';
    } else if (plugin.busy) {
      dot = 'wait'; title = 'Installing the panel…'; sub = 'This takes a few seconds';
    } else if (plugin.result === 'needs_user' && !installed) {
      dot = 'wait'; title = 'Finish in Creative Cloud'; sub = 'Click Install in the window Creative Cloud opened';
      btn = `<button class="btn-quiet sm" data-p="install">Try again</button>`;
    } else if (!installed) {
      title = 'Panel not installed'; sub = 'Send sequences to SYN and get them back without exporting XML';
      btn = `<button class="btn-quiet sm" data-p="install">${icon('download')}Install</button>`;
    } else {
      dot = clients.length ? 'wait' : ''; title = 'Panel installed';
      sub = 'In Premiere: Window › UXP Plugins › SYN';
      if (bundled && installed && cmpVer(bundled, installed) > 0) btn = `<button class="btn-quiet sm" data-p="install">Update panel</button>`;
    }
    box.innerHTML = `<div class="st"><span class="pr-logo">Pr<i class="${dot}"></i></span><div class="t"><b>${title}</b><span>${sub}</span></div>${btn}</div>
      ${pend ? `<button class="btn-primary inline" data-p="pair">${icon('link')}Premiere wants to connect</button>` : ''}`;
  }
  const cmpVer = (a, b) => {
    const pa = String(a).split('.').map(Number), pb = String(b).split('.').map(Number);
    for (let i = 0; i < 3; i++) if ((pa[i] || 0) !== (pb[i] || 0)) return (pa[i] || 0) - (pb[i] || 0);
    return 0;
  };
  $('#premiere').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-p]');
    if (!b) return;
    if (b.dataset.p === 'install') { plugin = await api.plugin_install(); renderPremiere(); }
    else if (b.dataset.p === 'pair' && bridge.pending.length) showPair(bridge.pending[0]);
  });

  function showPair(p) {
    showModal('pair', `
      <div class="pair-hero"><span class="pr-logo">Pr</span><span class="pair-link"></span>
        <span class="logomark"><img class="mark" src="mark.svg" alt="SYN" style="height:16px"></span></div>
      <h2>Premiere Pro wants to connect</h2>
      <p class="about" style="font-size:13px;color:var(--text2)">The SYN panel${p.hostVersion ? ` in Premiere Pro ${esc(p.hostVersion)}` : ''} is asking to send sequences here and get them back synced. Only allow it if you just opened the panel.</p>
      <div class="foot"><button class="btn-quiet" data-m="deny">Don't allow</button><button class="btn-primary inline lime" data-m="allow">${icon('check')}Allow</button></div>`,
      async (m) => {
        if (m === 'allow' || m === 'deny') {
          bridge = await api.pair_decide(p.id, m === 'allow');
          closeModal(); renderPremiere();
          if (m === 'allow') toast('Premiere is connected');
        }
      });
  }

  // ---- sync options ----
  function renderOptions() {
    setTabs('#mode', settings.mode || 'fast');
    $('#mode-hint').textContent = settings.mode === 'thorough'
      ? 'Compares every clip with every other, even from the same camera. Slower; for tricky shoots.'
      : 'Compares clips across cameras and recorders. Right for most shoots.';
    document.querySelectorAll('.panel-row.opt[data-key]').forEach((b) => b.querySelector('.switch').classList.toggle('on', !!settings[b.dataset.key]));
    $('#density').classList.toggle('on', settings.density === 'compact');
  }
  $('#mode').addEventListener('click', async (e) => {
    const b = e.target.closest('button');
    if (b) { settings = await api.set_setting('mode', b.dataset.v); renderOptions(); }
  });
  document.querySelectorAll('.panel-row.opt[data-key]').forEach((b) => {
    b.onclick = async () => { settings = await api.set_setting(b.dataset.key, !settings[b.dataset.key]); renderOptions(); };
  });
  $('#density').onclick = async () => {
    settings = await api.set_setting('density', settings.density === 'compact' ? 'comfortable' : 'compact');
    renderOptions();
    if (P) { buildLanes(); renderHeads(); draw(); }
  };
  $('#fit').onclick = () => fit();
  $('#filter').addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    view.filter = b.dataset.v; setTabs('#filter', view.filter);
    view.scrollY = 0;
    buildLanes(); renderHeads(); draw();
    if (view.filter !== 'all') { const l = orderedClips(); if (l.length) select(l[0].id, true); }
  });
  function setTabs(sel, v) { document.querySelectorAll(sel + ' button').forEach((b) => b.classList.toggle('on', b.dataset.v === v)); }

  // ======================================================================
  // toasts, modals, settings, updates, welcome
  // ======================================================================
  function toast(text, err, action) {
    const t = document.createElement('div');
    t.className = 'toast' + (err ? ' err' : '');
    t.innerHTML = icon(err ? 'alert' : 'check') + `<span>${esc(text)}</span>`;
    if (action) {
      const b = document.createElement('button');
      b.textContent = action.label;
      b.onclick = action.run;
      t.appendChild(b);
    }
    $('#toasts').appendChild(t);
    setTimeout(() => { t.style.transition = 'opacity .3s'; t.style.opacity = 0; setTimeout(() => t.remove(), 300); }, 4500);
  }
  function closeModal() { $('#modal-root').innerHTML = ''; modal = null; }
  function showModal(name, html, onClick, cls) {
    const box = modal === name && $('#modal-root .modal');
    modal = name;
    if (box) { box.className = `modal ${cls || ''}`; box.innerHTML = html; }
    else $('#modal-root').innerHTML = `<div class="modal-back"><div class="modal ${cls || ''}">${html}</div></div>`;
    $('#modal-root .modal-back').onclick = (e) => {
      if (e.target.classList.contains('modal-back')) return closeModal();
      const el = e.target.closest('[data-m]');
      if (el) onClick(el.dataset.m, el);
    };
  }
  const sw = (on) => `<span class="switch ${on ? 'on' : ''}"></span>`;
  const opt = (key, title, detail) => `<button class="opt" data-m="toggle" data-key="${key}"><div class="t"><b>${title}</b><span>${detail}</span></div>${sw(settings[key])}</button>`;
  const ago = (iso) => {
    if (!iso) return 'Never checked';
    const s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (s < 60) return 'Checked just now';
    if (s < 3600) return `Checked ${Math.round(s / 60)} min ago`;
    if (s < 86400) return `Checked ${Math.round(s / 3600)} h ago`;
    return 'Checked ' + new Date(iso).toLocaleDateString();
  };
  function updateLine() {
    if (!upd) return ['', ''];
    switch (upd.phase) {
      case 'checking': return ['Checking for updates…', ''];
      case 'uptodate': return ["You're up to date", 'ok'];
      case 'available': return [`Version ${upd.latest} is available`, 'ok'];
      case 'downloading': return [upd.progress >= 1 ? `Preparing ${upd.latest}…` : `Downloading ${upd.latest}… ${Math.round(upd.progress * 100)}%`, ''];
      case 'ready': return [`Version ${upd.latest} is ready to install`, 'ok'];
      case 'installing': return ['Installing…', ''];
      case 'failed': return [upd.error || 'Update failed', 'bad'];
      default: return [ago(upd.last_checked), ''];
    }
  }
  function renderUpdateRow() {
    const el = $('#upd-row');
    if (!el) return;
    const [line, cls] = updateLine();
    const has = upd && ['available', 'downloading', 'ready'].includes(upd.phase);
    el.innerHTML = `<div class="t"><b>SYN ${esc(upd ? upd.current : '')}</b><span class="${cls}">${esc(line)}</span></div>
      ${has ? `<button class="btn-quiet" data-m="see-update">${icon('download')}See update</button>` : `<button class="btn-quiet" data-m="check" ${upd && upd.phase === 'checking' ? 'disabled' : ''}>${icon('refresh')}Check now</button>`}`;
  }
  const human = (n) => (n > 1e9 ? (n / 1e9).toFixed(1) + ' GB' : n > 1e6 ? Math.round(n / 1e6) + ' MB' : Math.round(n / 1e3) + ' KB');
  async function openSettings() {
    const cache = await api.cache_info();
    const clients = bridge.clients || [];
    showModal('settings', `
      <div class="modal-title"><h2>Settings</h2><button class="btn-icon" data-m="close">${icon('x')}</button></div>
      <div class="label">Updates</div>
      <div class="group">
        <div class="ver-row" id="upd-row"></div>
        ${opt('auto_check', 'Check for updates automatically', 'Looks for a new version at launch and every few hours')}
        ${opt('auto_install', 'Download and install updates automatically', 'Downloads in the background and installs when you quit')}
      </div>
      <div class="label">Premiere Pro</div>
      <div class="group">
        ${hasPlugin ? `<div class="ver-row"><div class="t"><b>SYN panel</b><span>${plugin.installed ? `Installed · ${esc(plugin.installed)}` : 'Not installed'}${plugin.bundled ? ` · this app carries ${esc(plugin.bundled)}` : ''}</span></div>
          <button class="btn-quiet" data-m="plugin-install">${plugin.installed ? 'Reinstall' : 'Install'}</button>
          ${plugin.installed ? `<button class="btn-quiet" data-m="plugin-remove">Remove</button>` : ''}</div>` : ''}
        ${opt('auto_send', 'Send back to Premiere automatically', 'Skip the review when a sequence comes from the panel')}
        ${clients.length ? clients.map((c) => `<div class="ver-row"><div class="t"><b>${esc(c.name)}</b><span>Paired ${new Date(c.paired * 1000).toLocaleDateString()}</span></div>
          <button class="btn-quiet" data-m="revoke" data-id="${esc(c.id)}">Disconnect</button></div>`).join('') : ''}
      </div>
      <div class="label">Output</div>
      <div class="group">
        <div class="ver-row"><div class="t"><b>Save synced XML to</b><span>${settings.out_mode === 'custom' && settings.custom_dir ? esc(tildify(settings.custom_dir)) : 'Next to the XML or footage'}</span></div>
          ${settings.out_mode === 'custom' ? `<button class="btn-quiet" data-m="beside">Next to it</button>` : ''}<button class="btn-quiet" data-m="choose">Choose…</button></div>
        <button class="opt" data-m="unsynced"><div class="t"><b>Clips that don't sync</b><span>${settings.unsynced === 'drop' ? 'Left out of the synced sequence' : 'Put at the end of the sequence, marked'}</span></div>${sw(settings.unsynced !== 'drop')}</button>
        ${opt('open_after', 'Show the XML after saving', 'Opens the folder in Finder or Explorer')}
      </div>
      <div class="label">Storage</div>
      <div class="group"><div class="ver-row"><div class="t"><b>Audio cache</b><span>${human(cache.bytes)} · makes re-syncing the same footage instant</span></div>
        <button class="btn-quiet" data-m="clear-cache">Clear</button></div></div>
      <div class="about">SYN listens to every clip, matches the sound between cameras and recorders, and lines them up to the frame. Everything runs on this computer; footage is never uploaded or changed. The Premiere panel talks to SYN only on this computer.</div>
      <div class="foot"><button class="foot-link" data-m="page">Release notes on GitHub</button><button class="foot-link" data-m="welcome" style="margin-right:0">Show welcome screen</button></div>`,
      async (m, el) => {
        if (m === 'close') closeModal();
        else if (m === 'toggle') {
          const k = el.dataset.key;
          settings = await api.set_setting(k, !settings[k]);
          el.querySelector('.switch').classList.toggle('on', !!settings[k]);
        } else if (m === 'unsynced') { settings = await api.set_setting('unsynced', settings.unsynced === 'drop' ? 'end' : 'drop'); openSettings(); }
        else if (m === 'check') { upd = await api.check_updates(); renderUpdateRow(); renderPill(); }
        else if (m === 'see-update') openUpdate();
        else if (m === 'page') api.open_url(upd ? upd.page : 'https://github.com/YuvrajxGarg/syn/releases');
        else if (m === 'welcome') { closeModal(); showWelcome(); }
        else if (m === 'plugin-install') { plugin = await api.plugin_install(); renderPremiere(); closeModal(); }
        else if (m === 'plugin-remove') { plugin = await api.plugin_uninstall(); renderPremiere(); openSettings(); }
        else if (m === 'revoke') { bridge = await api.revoke_client(el.dataset.id); renderPremiere(); openSettings(); }
        else if (m === 'choose') { settings = await api.choose_output(); openSettings(); }
        else if (m === 'beside') { settings = await api.set_setting('out_mode', 'beside'); openSettings(); }
        else if (m === 'clear-cache') { await api.clear_cache(); openSettings(); }
      }, 'settings');
    renderUpdateRow();
  }
  $('#open-settings').onclick = openSettings;

  function renderPill() {
    const p = $('#update-pill');
    if (!upd || !['available', 'downloading', 'ready', 'installing'].includes(upd.phase)) { p.classList.add('hidden'); return; }
    p.classList.remove('hidden');
    p.innerHTML = upd.phase === 'ready' ? `${icon('refresh')}Restart to update` :
      upd.phase === 'downloading' ? (upd.progress >= 1 ? `${icon('refresh')}Preparing update…` : `${icon('download')}Updating ${Math.round(upd.progress * 100)}%`) :
      upd.phase === 'installing' ? `${icon('refresh')}Installing…` : `${icon('download')}Update to ${esc(upd.latest)}`;
  }
  $('#update-pill').onclick = () => openUpdate();
  function patchUpdateProgress() {
    const bar = $('#modal-root .progress > div');
    const line = $('#modal-root .update-hero p');
    if (!bar || !line) return false;
    const pct = Math.round((upd.progress || 0) * 100);
    bar.style.width = pct + '%';
    line.textContent = pct >= 100 ? 'Checking and unpacking the update…' : `Downloading… ${pct}%`;
    return true;
  }
  function openUpdate() {
    if (!upd) return;
    const ph = upd.phase;
    const pct = Math.round((upd.progress || 0) * 100);
    const sub = ph === 'ready' ? 'Downloaded and ready. Restart now, or it installs the next time you quit.' :
      ph === 'downloading' ? (pct >= 100 ? 'Checking and unpacking the update…' : `Downloading… ${pct}%`) : ph === 'installing' ? 'Installing and restarting…' :
      ph === 'failed' ? (upd.error || 'Something went wrong.') : ph === 'uptodate' ? "You're on the newest version." :
      `You have ${esc(upd.current)}.` + (upd.can_install ? '' : ' This copy runs from source, so the download page opens instead.');
    const primary = ph === 'ready' ? `<button class="btn-primary inline" data-m="install">${icon('refresh')}Restart to update</button>` :
      ph === 'available' || ph === 'failed' ? `<button class="btn-primary inline" data-m="${upd.can_install ? 'download' : 'page'}">${icon('download')}${upd.can_install ? 'Download update' : 'Open download page'}</button>` : '';
    showModal('update', `
      <div class="update-hero">
        <div class="logomark lg"><img class="mark" src="mark.svg" alt="SYN" style="height:23px"></div>
        <div><h2>${upd.latest ? 'SYN ' + esc(upd.latest) : 'Updates'}</h2><p class="${ph === 'failed' ? 'err' : ''}">${sub}</p></div>
      </div>
      ${ph === 'downloading' ? `<div class="progress"><div style="width:${pct}%"></div></div>` : ''}
      ${upd.notes ? `<div class="label">What's new</div><div class="notes">${esc(upd.notes)}</div>` : ''}
      <div class="foot"><button class="foot-link" data-m="page">Release page</button><button class="btn-quiet" data-m="close">Later</button>${primary}</div>`,
      (m) => {
        if (m === 'close') closeModal();
        else if (m === 'install') api.install_update();
        else if (m === 'download') api.download_update();
        else if (m === 'page') api.open_url(upd.page);
      });
  }

  function showWelcome() {
    const w = $('#welcome');
    let page = 0;
    const pages = [
      () => `<div class="logomark lg"><img class="mark" src="mark.svg" alt="SYN" style="height:24px"></div>
        <h1>Sync every camera by sound</h1>
        <p class="lead">SYN listens to your cameras, recorders and phones, finds where each clip sits,<br>and hands back a sequence with everything lined up to the frame.</p>
        <div class="facts">
          <div class="card fact">${icon('layers')}<b>Any number of tracks</b><span>20 cameras and 20 recorders is a normal day</span></div>
          <div class="card fact">${icon('ear')}<b>A confidence score</b><span>for every clip, so you only check the ones that need it</span></div>
          <div class="card fact">${icon('link')}<b>Premiere in, Premiere out</b><span>through the SYN panel, or any FCP 7 XML</span></div>
        </div>`,
      () => `<span class="pr-logo" style="width:64px;height:64px;border-radius:16px;font-size:26px">Pr</span>
        <h1>Connect Premiere Pro</h1>
        <p class="lead">The SYN panel sends a sequence here in one click and opens the synced one in Premiere.<br>No exporting and importing XML by hand.</p>
        <div class="group"><div class="ver-row"><div class="t"><b>SYN panel for Premiere Pro</b><span>${!hasPlugin ? 'Not part of this build: use File › Export › Final Cut Pro XML' : plugin.installed ? 'Installed · open it from Window › UXP Plugins › SYN' : plugin.busy ? 'Installing…' : plugin.result === 'needs_user' ? 'Finish the install in the Creative Cloud window' : 'Needs Premiere Pro 25.6 or newer'}</span></div>
          ${hasPlugin && !plugin.installed ? `<button class="btn-quiet" data-w="plugin" ${plugin.busy ? 'disabled' : ''}>${icon('download')}Install</button>` : plugin.installed ? `<span class="pct hi">${icon('check')}</span>` : ''}</div></div>`,
      () => `<div class="logomark lg"><img class="mark" src="mark.svg" alt="SYN" style="height:24px"></div>
        <h1>Stay up to date</h1>
        <p class="lead">SYN updates itself from GitHub, like the other PXL apps.<br>Your Premiere panel updates with it.</p>
        <div class="group">
          ${opt('auto_check', 'Check for updates automatically', 'Looks for a new version at launch and every few hours')}
          ${opt('auto_install', 'Download and install updates automatically', 'Downloads in the background and installs when you quit')}
        </div>`,
    ];
    const render = () => {
      w.innerHTML = `<div class="glow"></div><div class="dots">${pages.map((_, i) => `<i class="${i <= page ? 'on' : ''} ${i === page ? 'cur' : ''}"></i>`).join('')}</div>
        <div class="page">${pages[page]()}</div>
        <div class="foot">${page ? '<button class="btn-quiet" data-w="back">Back</button>' : '<button class="foot-link" data-w="skip">Skip</button>'}
          <button class="btn-primary" data-w="next">${page === pages.length - 1 ? 'Start syncing' : 'Continue'}</button></div>`;
    };
    w.onclick = async (e) => {
      const b = e.target.closest('[data-w],[data-m]');
      if (!b) return;
      if (b.dataset.m === 'toggle') {
        const k = b.dataset.key;
        settings = await api.set_setting(k, !settings[k]);
        b.querySelector('.switch').classList.toggle('on', !!settings[k]);
        return;
      }
      const a = b.dataset.w;
      if (a === 'next' && page < pages.length - 1) { page++; render(); }
      else if (a === 'back') { page--; render(); }
      else if (a === 'plugin') { plugin = await api.plugin_install(); render(); renderPremiere(); }
      else if (a === 'next' || a === 'skip') { w.classList.add('hidden'); api.set_setting('welcomed', true); }
    };
    w.classList.remove('hidden');
    w._render = render;
    render();
  }

  // ======================================================================
  // events from Python
  // ======================================================================
  window.App = {
    on(event, p) {
      if (event === 'projects') { projects = p; renderProjects(); renderTop(); if (P && P.state !== 'analyzing') renderAction(); }
      else if (event === 'project') {
        setProject(p, { fit: true });
      } else if (event === 'progress') {
        if (P && p.pid === P.id) {
          const was = P.state;
          Object.assign(P, { state: p.state, stage: p.stage, progress: p.progress });
          if (was !== p.state) { renderTop(); renderAction(); }
          renderBanner();
          const sa = $('#side-action .sync-state .t b');
          if (sa) {
            sa.textContent = `Syncing ${Math.round(p.progress * 100)}%`;
            $('#side-action .sync-state .t span').textContent = p.stage;
            $('#side-action .progress > div').style.width = Math.round(p.progress * 100) + '%';
          } else renderAction();
          if (!/Listen/.test(p.stage)) reading.clear();
          draw();
        }
        const row = projects.find((x) => x.id === p.pid);
        if (row) { row.state = p.state; row.progress = p.progress; renderProjects(); }
      } else if (event === 'clip') {
        if (!P || p.pid !== P.id) return;
        const c = p.clip;
        const old = clipsById.get(c.id);
        if (old) Object.assign(old, c);
        if (p.reading) reading.add(c.id);
        else { reading.delete(c.id); if (p.env) envs.set(c.id, decodeEnv(p.env)); }
        draw();
      } else if (event === 'synced') {
        if (!P || p.id !== P.id) return;
        // Slide every clip from where it was to where it belongs, lane by lane, then lock.
        const now = performance.now();
        const before = new Map(P.clips.map((c) => [c.id, posOf(c, now)]));
        reading.clear();
        P = { ...p };
        indexClips();
        placeUnsynced();
        lanes.forEach((ln, i) => {
          for (const c of ln.clips) {
            if (anim.has(c.id)) continue;
            const to = c.at != null ? c.at : unsyncedAt.get(c.id);
            const from = before.get(c.id);
            if (to == null || from == null) continue;
            anim.set(c.id, { from, to, t0: now, dur: 900, delay: Math.min(i, 30) * 28 });
          }
        });
        renderAll(true);
        fit();
        countUp(p.overall);
        const k = counts();
        const n = k.synced + k.low;
        toast(`Synced ${n} of ${plural(k.total, 'clip')}${k.low + k.unsynced ? ` · ${k.low + k.unsynced} to check` : ''}`);
        if (k.low + k.unsynced) setTimeout(() => {
          const first = orderedClips().find(needsCheck);
          if (first && !view.sel) select(first.id, true);
        }, 1500);
      } else if (event === 'pair') { bridge.pending = [...(bridge.pending || []).filter((x) => x.id !== p.id), p]; renderPremiere(); showPair(p); }
      else if (event === 'bridge') { bridge = p; renderPremiere(); }
      else if (event === 'plugin') { plugin = p; renderPremiere(); const w = $('#welcome'); if (w && !w.classList.contains('hidden') && w._render) w._render(); }
      else if (event === 'toast') toast(p.text, p.err);
      else if (event === 'loading') {
        $('#loading').classList.toggle('hidden', !p);
        if (p) $('#loading-text').textContent = p.text;
      } else if (event === 'update') {
        const prev = upd && upd.phase;
        upd = p; renderPill(); renderUpdateRow();
        if (modal === 'update' && !(prev === 'downloading' && p.phase === 'downloading' && patchUpdateProgress())) openUpdate();
        if (prev !== 'ready' && p.phase === 'ready' && modal !== 'update')
          toast(`Version ${p.latest} is ready`, false, { label: 'Restart', run: () => api.install_update() });
      }
    },
  };
  function countUp(target) {
    const el = $('#overall-n');
    if (!el) return;
    const t0 = performance.now();
    const step = (now) => {
      const k = clamp((now - t0) / 900, 0, 1);
      const e = 1 - Math.pow(1 - k, 3);
      const cur = document.getElementById('overall-n');
      if (cur) cur.textContent = Math.round(target * 100 * e) + '%';
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  // ---- drop & pickers ----
  $('#dropzone').onclick = () => api.pick_inputs();
  $('#add-folder').onclick = () => api.pick_folder();
  let dragDepth = 0;
  const showDrop = (on) => { $('#drop').classList.toggle('hidden', !on); document.body.classList.toggle('dragging', on); };
  window.addEventListener('dragenter', (e) => { e.preventDefault(); dragDepth++; showDrop(true); });
  window.addEventListener('dragleave', (e) => { e.preventDefault(); if (--dragDepth <= 0) { dragDepth = 0; showDrop(false); } });
  window.addEventListener('dragover', (e) => e.preventDefault());
  window.addEventListener('drop', (e) => { e.preventDefault(); dragDepth = 0; showDrop(false); });

  // ======================================================================
  // start
  // ======================================================================
  async function start(a) {
    api = a;
    const info = await api.info();
    settings = info.settings; upd = info.update; bridge = info.bridge; plugin = info.plugin; hasPlugin = info.has_plugin;
    home = info.home; platform = info.platform; projects = info.projects;
    if (info.platform !== 'darwin') document.body.classList.add('win');
    $('#version').textContent = 'v' + info.version;
    $('#ffmpeg-note').innerHTML = info.ffmpeg ? '' : `${icon('alert')}<span>ffmpeg is missing, so footage can't be read</span>`;
    renderOptions(); renderPill(); renderPremiere();
    setProject(info.project);
    if (!settings.welcomed) showWelcome();
    document.body.classList.add('ready');
    setTimeout(() => { $('#splash').classList.add('out'); $('#app').classList.add('in'); resize(); }, 1700);
    setTimeout(() => $('#splash').remove(), 2300);
    setInterval(async () => { bridge = await api.bridge_status(); renderPremiere(); }, 5000);
  }

  // Never leave the window stuck on the splash. If startup throws, or the Python side never
  // answers, show the app anyway and say what went wrong.
  if (!location.search.includes('demo')) {
    let started = false;
    const reveal = (msg) => {
      const s = $('#splash');
      if (!s || s.classList.contains('out')) return;
      document.body.classList.add('ready');
      s.classList.add('out'); $('#app').classList.add('in');
      if (msg) toast(msg, true);
    };
    const boot = () => {
      const a = window.pywebview && window.pywebview.api;
      if (started || !a || typeof a.info !== 'function') return;
      started = true;
      start(a).catch((e) => reveal("SYN couldn't start: " + ((e && e.message) || e)));
    };
    window.addEventListener('pywebviewready', boot);
    boot();
    setTimeout(() => reveal(started ? '' : "SYN's engine didn't answer. Quit SYN and open it again."), 15000);
  } else {
    import('./demo.js').then((m) => m.default(start, window.App)).catch((e) => console.error(e));
  }
})();
