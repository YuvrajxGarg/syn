// Renders Session state into the panel. HTML builders are pure functions so they can
// be tested without a DOM. Events use delegation on data-action (UXP ignores inline handlers).

"use strict";

const STATE_LABEL = {
  queued: "Queued",
  analyzing: "Syncing",
  review: "Ready to review in SYN",
  done: "Synced",
  failed: "Failed",
  cancelled: "Cancelled",
};

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function pct(x) {
  return `${Math.round(Math.max(0, Math.min(1, Number(x) || 0)) * 100)}%`;
}

function scoreClass(c) {
  if (c == null) return "";
  if (c >= 0.85) return "high";
  if (c >= 0.6) return "mid";
  return "low";
}

function counts(clips) {
  const c = { synced: 0, low: 0, unsynced: 0 };
  for (const k of clips || []) c[k.status in c ? k.status : "unsynced"] += 1;
  return c;
}

// Clips needing attention first: unsynced, then low, then by confidence ascending.
function sortClips(clips) {
  const rank = { unsynced: 0, low: 1, synced: 2 };
  return (clips || []).slice().sort((a, b) => {
    const r = (rank[a.status] ?? 0) - (rank[b.status] ?? 0);
    return r || (a.confidence || 0) - (b.confidence || 0);
  });
}

const DOT = { synced: "#ccff4d", low: "#ffb359", unsynced: "#ff6b66" };

function jobHtml(job, expanded) {
  const st = job.state;
  const conf = job.result && job.result.confidence;
  const clips = (conf && conf.clips) || [];
  const name = (job.result && job.result.sequenceName) || job.sequenceName || job.name || "Sync";
  let badge = `<div class="badge">${esc(STATE_LABEL[st] || st)}</div>`;
  if ((st === "done" || st === "review") && conf && conf.overall != null) {
    badge = `<div class="badge ${scoreClass(conf.overall)}">${pct(conf.overall)} sure</div>`;
  }
  let body = "";
  if (st === "queued" || st === "analyzing") {
    body += `<div class="job-stage">${esc(job.stage || STATE_LABEL[st])}</div>`;
    body += `<div class="bar"><div class="bar-fill" style="width:${pct(job.progress)}"></div></div>`;
  } else if (st === "failed") {
    body += `<div class="job-stage">${esc((job.error && job.error.message) || "SYN couldn't sync this.")}</div>`;
  } else if (st === "review") {
    body += `<div class="job-stage">Check it in SYN, then hit Send to Premiere.</div>`;
  }
  if (clips.length) {
    const c = counts(clips);
    const n = clips.length;
    body += `<div class="split">` +
      (c.synced ? `<div class="split-synced" style="width:${(c.synced / n) * 100}%"></div>` : "") +
      (c.low ? `<div class="split-low" style="width:${(c.low / n) * 100}%"></div>` : "") +
      (c.unsynced ? `<div class="split-unsynced" style="width:${(c.unsynced / n) * 100}%"></div>` : "") +
      `</div>`;
    body += `<div class="legend"><div class="legend-item">${c.synced} synced</div>` +
      `<div class="legend-item">${c.low} low confidence</div>` +
      `<div class="legend-item">${c.unsynced} not synced</div></div>`;
  }
  let foot = "";
  const left = clips.length
    ? `<div class="link" data-action="toggle" data-id="${esc(job.id)}">${expanded ? "Hide clips" : `Show ${clips.length} clips`}</div>`
    : `<div></div>`;
  if (st === "done") {
    const right = job.local && job.local.imported
      ? `<div class="done-text">In your project ✓</div>`
      : job.local && job.local.importing
        ? `<div class="done-text">Importing…</div>`
        : `<div class="btn small primary" data-action="import" data-id="${esc(job.id)}">Import</div>`;
    foot = `<div class="job-foot">${left}${right}</div>`;
  } else if (st === "queued" || st === "analyzing" || st === "review") {
    foot = `<div class="job-foot">${left}<div class="link" data-action="cancel" data-id="${esc(job.id)}">Cancel</div></div>`;
  } else if (clips.length) {
    foot = `<div class="job-foot">${left}<div></div></div>`;
  }
  let list = "";
  if (expanded && clips.length) {
    list = `<div class="clips">` + sortClips(clips).map((k) =>
      `<div class="clip"><div class="clip-dot" style="background-color:${DOT[k.status] || DOT.unsynced}"></div>` +
      `<div class="clip-name">${esc(k.name)}</div>` +
      `<div class="clip-score">${k.status === "unsynced" ? "–" : pct(k.confidence)}</div></div>`
    ).join("") + `</div>`;
  }
  return `<div class="job" data-job="${esc(job.id)}"><div class="job-head"><div class="job-name">${esc(name)}</div>${badge}</div>${body}${foot}${list}</div>`;
}

function connView(state) {
  const v = state.hello && state.hello.version ? ` ${state.hello.version}` : "";
  switch (state.conn) {
    case "connected":
      return { dot: "on", text: `SYN${v}${state.mode === "file" ? " · local" : ""}` };
    case "pair":
      return { dot: "warn", text: "Not connected", banner: "SYN is open. Connect this panel to it once.", button: "Connect" };
    case "pairing":
      return { dot: "warn", text: "Waiting…", banner: "Click Allow in SYN to connect Premiere." };
    case "denied":
      return { dot: "off", text: "Blocked", banner: "SYN said no. Try again if that was a mistake.", button: "Try again" };
    case "mismatch":
      return { dot: "off", text: "Update needed", banner: "This panel doesn't match your SYN version. Update SYN and it updates the panel too." };
    case "offline":
      return { dot: "off", text: "Open SYN", banner: null };
    default:
      return { dot: "", text: "Looking for SYN…" };
  }
}

function drawMark(el) {
  if (!el) return;
  el.innerHTML = [8, 14, 18, 11, 6].map((h) => `<div class="mark-bar" style="height:${h}px"></div>`).join("");
}

function mount(doc, session, wave) {
  const $ = (id) => doc.getElementById(id);
  const expanded = new Set();
  let lastJobsHtml = "";

  doc.addEventListener("click", (ev) => {
    let t = ev.target;
    while (t && t !== doc.body && !(t.getAttribute && t.getAttribute("data-action"))) t = t.parentNode;
    if (!t || !t.getAttribute) return;
    const action = t.getAttribute("data-action");
    const id = t.getAttribute("data-id");
    if (t.classList && t.classList.contains("disabled")) return;
    if (action === "send-sequence") session.send("sequence");
    else if (action === "send-selection") session.send("selection");
    else if (action === "pair") session.pair();
    else if (action === "reconnect") session.ensureConnected(true);
    else if (action === "import") session.importJob(id);
    else if (action === "cancel") session.cancel(id);
    else if (action === "toggle") {
      if (expanded.has(id)) expanded.delete(id);
      else expanded.add(id);
      render(session.state, true);
    }
  });
  $("auto-import").addEventListener("change", (ev) => session.setAutoImport(ev.target.checked));

  function render(state, force) {
    const cv = connView(state);
    $("dot").className = `dot ${cv.dot}`;
    $("pill-text").textContent = cv.text;
    const banner = cv.banner || (state.updateAvailable ? "A newer SYN panel is ready. Update it from SYN → Settings → Premiere." : null);
    $("banner").className = banner ? "banner" : "banner hidden";
    $("banner-text").textContent = banner || "";
    $("banner-btn").className = cv.button ? "btn small" : "btn small hidden";
    $("banner-btn").textContent = cv.button || "";

    const ctx = state.context || {};
    $("ctx-seq").textContent = ctx.sequence ? ctx.sequence.name : ctx.project ? "None open" : "No project open";
    const sel = ctx.selection || { media: 0, sequences: 0 };
    const selParts = [];
    if (sel.media) selParts.push(`${sel.media} clip${sel.media === 1 ? "" : "s"}`);
    if (sel.sequences) selParts.push(`${sel.sequences} sequence${sel.sequences === 1 ? "" : "s"}`);
    $("ctx-sel").textContent = selParts.length ? selParts.join(", ") : "Nothing";

    const ready = state.conn === "connected" && !state.busy;
    $("send-seq").className = `btn primary${ready && ctx.sequence ? "" : " disabled"}`;
    $("send-sel").className = `btn${ready && (sel.media || sel.sequences) ? "" : " disabled"}`;
    $("send-sel").textContent = sel.media ? `Sync ${sel.media} selected clip${sel.media === 1 ? "" : "s"}` : "Sync selected clips";
    $("hint").textContent = ctx.project && !ctx.canExportXml
      ? "Premiere older than 26.2: SYN rebuilds the timeline from your media."
      : "";

    // Busy row: the wave follows the newest active job, or loops while exporting/importing.
    const active = (state.jobs || []).find((j) => j.local && j.local.mine && (j.state === "queued" || j.state === "analyzing"));
    if (state.busy || active) {
      $("busy").className = "busy";
      $("busy-text").textContent = state.busy || active.stage || "Syncing…";
      wave.set("working", state.busy ? 0.15 : active.progress || 0.05);
    } else {
      $("busy").className = "busy hidden";
      wave.set("idle");
    }

    if (state.notice) {
      $("notice").className = `notice ${state.notice.kind}`;
      $("notice").textContent = state.notice.text;
    } else {
      $("notice").className = "notice hidden";
    }
    $("auto-import").checked = !!state.autoImport;

    const jobs = (state.jobs || []).filter((j) => j.state !== "cancelled").slice(0, 20);
    const html = jobs.map((j) => jobHtml(j, expanded.has(j.id))).join("");
    if (force || html !== lastJobsHtml) {
      const box = $("jobs");
      const scroll = box.scrollTop;
      box.innerHTML = html;
      box.scrollTop = scroll;
      lastJobsHtml = html;
    }
    $("empty").className = jobs.length ? "empty hidden" : "empty";
  }

  session.on((s) => render(s));
  render(session.state, true);
}

function fatal(doc, e) {
  const n = doc.getElementById("notice");
  if (n) {
    n.className = "notice error";
    n.textContent = `SYN panel couldn't start: ${(e && e.message) || e}`;
  }
}

module.exports = { mount, fatal, drawMark, jobHtml, connView, sortClips, counts, scoreClass, esc };
