// Renders Session state into the panel. Kept deliberately small: one Sync button, one card
// for the current sync with a single overall score. Per-clip detail lives in the Syn app.
// HTML builders are pure so they can be tested without a DOM; events use data-action
// delegation (UXP ignores inline handlers).

"use strict";

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

/** Overall confidence in words, so a number never has to be interpreted. */
function verdict(c) {
  if (c == null) return { cls: "", word: "Synced" };
  if (c >= 0.85) return { cls: "high", word: "Looks great" };
  if (c >= 0.6) return { cls: "mid", word: "Check a few clips in Syn" };
  return { cls: "low", word: "Needs a look in Syn" };
}

/** What the Sync button will send. Selected clips win; otherwise the open sequence. */
function target(ctx) {
  const sel = (ctx && ctx.selection) || { media: 0, sequences: 0 };
  if (sel.media) return { what: "selection", label: `Sync ${sel.media} clip${sel.media === 1 ? "" : "s"}`, alt: ctx.sequence ? "sequence" : null };
  if (sel.sequences) return { what: "selection", label: "Sync selected sequence", alt: null };
  if (ctx && ctx.sequence) return { what: "sequence", label: "Sync sequence", alt: null };
  return { what: null, label: "Sync", alt: null };
}

/** The one sync worth showing: something running, then something waiting to import, then the newest. */
function currentJob(jobs) {
  const list = (jobs || []).filter((j) => j.state !== "cancelled");
  return (
    list.find((j) => j.state === "queued" || j.state === "analyzing") ||
    list.find((j) => j.state === "review") ||
    list.find((j) => j.state === "done" && !(j.local && j.local.imported)) ||
    list[0] ||
    null
  );
}

function cardHtml(job) {
  if (!job) return "";
  const name = esc((job.result && job.result.sequenceName) || job.sequenceName || "Sync");
  const conf = job.result && job.result.confidence;
  const overall = conf && conf.overall != null ? conf.overall : null;
  const st = job.state;
  if (st === "queued" || st === "analyzing") {
    return `<div class="title">${name}</div><div class="line">${esc(job.stage || "Syncing…")}</div>` +
      `<div class="bar"><div class="bar-fill" style="width:${pct(job.progress)}"></div></div>` +
      `<div class="row end"><div class="link" data-action="cancel" data-id="${esc(job.id)}">Cancel</div></div>`;
  }
  if (st === "failed") {
    return `<div class="title">${name}</div><div class="line bad">${esc((job.error && job.error.message) || "Syn couldn't sync this.")}</div>`;
  }
  const v = verdict(overall);
  const score = overall != null ? `<div class="score ${v.cls}">${pct(overall)}</div>` : "";
  let action;
  if (st === "review") action = `<div class="line">Check it in Syn, then hit Send to Premiere.</div>`;
  else if (job.local && job.local.imported) action = `<div class="line ok">In your project ✓</div>`;
  else if (job.local && job.local.importing) action = `<div class="line">Importing…</div>`;
  else action = `<div class="btn primary" data-action="import" data-id="${esc(job.id)}">Import to Premiere</div>`;
  return `<div class="row">${score}<div class="col"><div class="title">${name}</div><div class="line">${esc(v.word)}</div></div></div>${action}`;
}

function connView(state) {
  switch (state.conn) {
    case "connected":
      return { dot: "on", text: "Connected" };
    case "pair":
      return { dot: "warn", text: "Not connected", banner: "Connect this panel to Syn once.", button: "Connect" };
    case "pairing":
      return { dot: "warn", text: "Waiting…", banner: "Click Allow in Syn." };
    case "denied":
      return { dot: "off", text: "Blocked", banner: "Syn said no.", button: "Try again" };
    case "mismatch":
      return { dot: "off", text: "Update needed", banner: "Update available, open Syn to update." };
    case "offline":
      return { dot: "off", text: "Open Syn" };
    default:
      return { dot: "", text: "Looking for Syn…" };
  }
}

// SYN's mark: "syn" + the lime sync link (two dots joined by a line), as on the app and site.
function drawMark(el) {
  if (!el) return;
  // An image cut from the app icon, so it's identical to the app's logo on every OS and font.
  el.innerHTML = `<img class="mark" src="icons/mark.png" alt="syn" />`;
}

function mount(doc, session, wave) {
  const $ = (id) => doc.getElementById(id);
  let lastCard = "";
  let alt = null;

  doc.addEventListener("click", (ev) => {
    let t = ev.target;
    while (t && t !== doc.body && !(t.getAttribute && t.getAttribute("data-action"))) t = t.parentNode;
    if (!t || !t.getAttribute) return;
    if (t.classList && t.classList.contains("disabled")) return;
    const action = t.getAttribute("data-action");
    const id = t.getAttribute("data-id");
    if (action === "sync") {
      const tg = target(session.state.context);
      if (tg.what) session.send(tg.what);
    } else if (action === "sync-alt" && alt) session.send(alt);
    else if (action === "pair") session.pair();
    else if (action === "update") session.updatePlugin();
    else if (action === "reconnect") session.ensureConnected(true);
    else if (action === "import") session.importJob(id);
    else if (action === "cancel") session.cancel(id);
  });

  function render(state) {
    const cv = connView(state);
    $("dot").className = `dot ${cv.dot}`;
    $("status-text").textContent = cv.text;

    const update = !cv.banner && state.updateAvailable && state.conn === "connected";
    const banner = cv.banner || (update ? "Update available, open Syn to update." : null);
    const button = cv.button || (update ? "Update" : null);
    $("banner").className = banner ? "banner" : "banner hidden";
    $("banner-text").textContent = banner || "";
    $("banner-btn").className = button ? "btn small" : "btn small hidden";
    $("banner-btn").textContent = button || "";
    $("banner-btn").setAttribute("data-action", update ? "update" : "pair");

    const ctx = state.context || {};
    const tg = target(ctx);
    alt = tg.alt;
    const ready = state.conn === "connected" && !state.busy && !!tg.what;
    // One lime button at a time: while a result waits for Import, Sync steps back.
    const waiting = (state.jobs || []).some((j) => j.state === "done" && j.local && !j.local.imported);
    $("sync").className = `btn big${waiting ? "" : " primary"}${ready ? "" : " disabled"}`;
    $("sync").textContent = tg.label;
    let sub = "";
    if (state.conn === "offline") sub = "Open Syn on this computer to start.";
    else if (!ctx.project) sub = "Open a project.";
    else if (!tg.what) sub = "Open a sequence, or select clips in the Project panel.";
    else if (tg.alt) sub = `<span class="link" data-action="sync-alt">Sync “${esc(ctx.sequence.name)}” instead</span>`;
    else if (tg.what === "sequence") sub = esc(ctx.sequence.name);
    $("sub").innerHTML = sub;

    // The card: busy step, or the current sync.
    const job = currentJob(state.jobs);
    const running = job && (job.state === "queued" || job.state === "analyzing");
    let body = "";
    if (state.busy) body = `<div class="line center">${esc(state.busy)}</div>`;
    else body = cardHtml(job);
    $("card").className = body ? "card" : "card hidden";
    if (state.busy || running) {
      $("wave-box").className = "wave-box";
      wave.set("working", state.busy ? 0.15 : job.progress || 0.05);
    } else if (job && job.state === "done" && !state.busy) {
      $("wave-box").className = "hidden";
      wave.set("done");
    } else {
      $("wave-box").className = "hidden";
      wave.set("idle");
    }
    if (body !== lastCard) {
      $("card-body").innerHTML = body;
      lastCard = body;
    }

    const err = state.notice && state.notice.kind !== "ok" ? state.notice.text : "";
    $("error").className = err ? `error ${state.notice.kind}` : "error hidden";
    $("error").textContent = err;
  }

  session.on((s) => render(s));
  render(session.state);
}

function fatal(doc, e) {
  const n = doc.getElementById("error");
  if (n) {
    n.className = "error";
    n.textContent = `Syn panel couldn't start: ${(e && e.message) || e}`;
  }
}

module.exports = { mount, fatal, drawMark, cardHtml, connView, currentJob, target, verdict, esc };
