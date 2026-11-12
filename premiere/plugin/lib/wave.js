// SYN's loader: two audio waveforms (camera on top, recorder below) that start out of
// phase and slide into lock as the sync progresses. UXP has no CSS animations or
// transforms, so bars are animated from JS by changing their height.
// Everything is drawn inside a fixed box with padding, so nothing clips at the edges.

"use strict";

const COLORS = {
  idle: ["#3a3a3f", "#3a3a3f"],
  working: ["#ccff4d", "#8fa83a"],
  done: ["#ccff4d", "#ccff4d"],
  error: ["#ff6b66", "#7a3a38"],
};

function shape(i, n) {
  // A fixed "speech" envelope so both rows show the same sound.
  const x = i / n;
  return 0.25 + 0.75 * Math.abs(Math.sin(x * 9.1) * Math.sin(x * 3.3 + 0.6));
}

class Wave {
  constructor(el, { bars = 28, height = 34 } = {}) {
    this.el = el;
    this.n = bars;
    this.h = height;
    this.mode = "idle";
    this.progress = 0;
    this.t = 0;
    this.timer = null;
    this._build();
    this._draw();
  }

  _build() {
    this.el.innerHTML = "";
    this.el.className = (this.el.className || "").replace(/\bwave\b/, "") + " wave";
    this.rows = [0, 1].map((r) => {
      const row = document.createElement("div");
      row.className = `wave-row wave-row-${r}`;
      row.style.height = `${this.h / 2}px`;
      const bars = [];
      for (let i = 0; i < this.n; i++) {
        const b = document.createElement("div");
        b.className = "wave-bar";
        row.appendChild(b);
        bars.push(b);
      }
      this.el.appendChild(row);
      return bars;
    });
  }

  set(mode, progress) {
    this.mode = mode;
    if (typeof progress === "number" && isFinite(progress)) this.progress = Math.max(0, Math.min(1, progress));
    if (mode === "working" && !this.timer) {
      this.timer = setInterval(() => {
        this.t += 1;
        this._draw();
      }, 40);
    } else if (mode !== "working" && this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    this._draw();
  }

  _draw() {
    const [top, bottom] = this.rows;
    const half = this.h / 2 - 2;
    const [cTop, cBottom] = COLORS[this.mode] || COLORS.idle;
    // Offset (in bars) between the two rows: wide at 0 %, zero at 100 %.
    const offset = this.mode === "done" ? 0 : this.mode === "working" ? (1 - this.progress) * 7 + Math.sin(this.t / 9) * 1.2 * (1 - this.progress) : 4;
    const pulse = this.mode === "working" ? 0.12 : 0;
    for (let i = 0; i < this.n; i++) {
      const jitter = pulse * Math.sin(this.t / 3 + i * 0.7);
      const a = shape(i, this.n);
      const b = shape(((i - offset) % this.n + this.n) % this.n, this.n);
      top[i].style.height = `${Math.max(2, Math.round(half * Math.min(1, a + jitter)))}px`;
      bottom[i].style.height = `${Math.max(2, Math.round(half * Math.min(1, b - jitter * 0.5)))}px`;
      top[i].style.backgroundColor = cTop;
      bottom[i].style.backgroundColor = cBottom;
    }
  }

  destroy() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }
}

module.exports = { Wave };
