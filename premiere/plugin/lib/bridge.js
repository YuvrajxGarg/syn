// Talks to the SYN app. Contract: docs/premiere-bridge.md.
//
// Two transports with the same messages:
//   http  - 127.0.0.1:47480..47489, paired once, Bearer token on every call.
//   file  - <app data>/Syn/bridge/ mailbox, used when http is blocked (Premiere on macOS
//           disallows http:// from UXP) or SYN's server is unreachable.
// Everything platform-specific is injected, so tests run in plain Node.

"use strict";

const API = 1;
const PORTS = [47480, 47481, 47482, 47483, 47484, 47485, 47486, 47487, 47488, 47489];
const HEARTBEAT_FRESH_MS = 6000;
const TOKEN_KEY = "syn.token";

class BridgeError extends Error {
  constructor(code, message, status) {
    super(message || code);
    this.code = code;
    this.status = status || 0;
  }
}

function joinPath(sep, ...parts) {
  return parts
    .filter((p) => p !== "" && p != null)
    .map((p, i) => (i === 0 ? String(p).replace(/[\\/]+$/, "") : String(p).replace(/^[\\/]+|[\\/]+$/g, "")))
    .join(sep);
}

// Where SYN keeps its app data. Mirrors the app: Mac ~/Library/Application Support/Syn,
// Windows %APPDATA%\Syn (UXP has no env vars, so derive it from the home folder).
function appDataDir(platform, home) {
  if (platform === "win32" || platform === "windows") {
    return joinPath("\\", home, "AppData", "Roaming", "Syn");
  }
  return joinPath("/", home, "Library", "Application Support", "Syn");
}

function newId() {
  const rnd = Math.random().toString(36).slice(2, 10);
  return `p${Date.now().toString(36)}${rnd}`;
}

function compareVersions(a, b) {
  const pa = String(a || "0").split(".").map((n) => parseInt(n, 10) || 0);
  const pb = String(b || "0").split(".").map((n) => parseInt(n, 10) || 0);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const d = (pa[i] || 0) - (pb[i] || 0);
    if (d) return d < 0 ? -1 : 1;
  }
  return 0;
}

/**
 * deps:
 *   fetch(url, init)           - WHATWG fetch
 *   files                      - { readText(path), writeText(path, text), rename(a, b),
 *                                  remove(path), list(dir) -> names, mkdir(dir), exists(path) }
 *   sep                        - path separator for the file transport ("/" or "\\")
 *   bridgeDir                  - absolute path of <app data>/bridge
 *   storage                    - { get(key) -> string|null, set(key, value), remove(key) }
 *   sleep(ms), now()
 *   clientVersion, hostVersion
 */
class Bridge {
  constructor(deps) {
    this.d = Object.assign(
      {
        sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
        now: () => Date.now(),
        sep: "/",
        probeTimeoutMs: 700,
        responseTimeoutMs: 15000,
      },
      deps
    );
    this.mode = "offline"; // "http" | "file" | "offline"
    this.base = null;
    this.hello = null;
    this.token = null;
  }

  // ---- discovery -------------------------------------------------------

  /** Finds SYN. Returns {mode, hello}. Never throws. */
  async connect() {
    const viaHttp = await this._probeHttp();
    if (viaHttp) {
      this.mode = "http";
      this.base = viaHttp.base;
      this.hello = viaHttp.hello;
      return { mode: this.mode, hello: this.hello };
    }
    const viaFile = await this._probeFile();
    if (viaFile) {
      this.mode = "file";
      this.base = null;
      this.hello = viaFile;
      return { mode: this.mode, hello: this.hello };
    }
    this.mode = "offline";
    this.hello = null;
    return { mode: "offline", hello: null };
  }

  async _probeHttp() {
    const tries = PORTS.map((port) => {
      const base = `http://127.0.0.1:${port}`;
      return this._timed(this.d.fetch(`${base}/v1/hello`, { method: "GET" }), this.d.probeTimeoutMs)
        .then(async (res) => {
          if (!res || !res.ok) return null;
          const hello = await res.json();
          return hello && hello.app === "Syn" ? { base, port, hello } : null;
        })
        .catch(() => null);
    });
    // Contract says "in order": prefer the lowest port that answers.
    const results = await Promise.all(tries);
    return results.find(Boolean) || null;
  }

  async _probeFile() {
    try {
      const text = await this.d.files.readText(this._bp("hello.json"));
      const hello = JSON.parse(text);
      if (!hello || hello.app !== "Syn") return null;
      if (!(this.d.now() - Number(hello.heartbeat || 0) < HEARTBEAT_FRESH_MS)) return null;
      return hello;
    } catch (e) {
      return null;
    }
  }

  _timed(promise, ms) {
    return new Promise((resolve, reject) => {
      const t = setTimeout(() => reject(new BridgeError("timeout", "Timed out")), ms);
      promise.then(
        (v) => {
          clearTimeout(t);
          resolve(v);
        },
        (e) => {
          clearTimeout(t);
          reject(e);
        }
      );
    });
  }

  /** True when SYN's bundled plugin is newer than this one. */
  updateAvailable() {
    const bundled = this.hello && this.hello.plugin && this.hello.plugin.bundled;
    return !!bundled && compareVersions(this.d.clientVersion, bundled) < 0;
  }

  apiMismatch() {
    return !!this.hello && Number(this.hello.api) !== API;
  }

  // ---- pairing (http only) --------------------------------------------

  async loadToken() {
    if (this.token) return this.token;
    try {
      this.token = (await this.d.storage.get(TOKEN_KEY)) || null;
    } catch (e) {
      this.token = null;
    }
    return this.token;
  }

  needsPairing() {
    return this.mode === "http" && !this.token;
  }

  /**
   * Asks SYN for access. onPending() fires once SYN shows its Allow / Deny prompt.
   * Resolves true when approved, false when denied, throws on timeout.
   */
  async pair(onPending, { timeoutMs = 120000, pollMs = 800 } = {}) {
    if (this.mode !== "http") return true;
    const res = await this._http("POST", "/v1/pair", {
      client: "premiere",
      clientVersion: this.d.clientVersion,
      hostVersion: this.d.hostVersion,
    }, { auth: false });
    if (onPending) onPending();
    const started = this.d.now();
    while (this.d.now() - started < timeoutMs) {
      await this.d.sleep(pollMs);
      const st = await this._http("GET", `/v1/pair/${encodeURIComponent(res.pairId)}`, null, { auth: false });
      if (st.status === "approved" && st.token) {
        this.token = st.token;
        try {
          await this.d.storage.set(TOKEN_KEY, st.token);
        } catch (e) {
          /* secure storage is a cache; we can re-pair */
        }
        return true;
      }
      if (st.status === "denied") return false;
    }
    throw new BridgeError("pair_timeout", "SYN didn't answer the connection request.");
  }

  async forgetToken() {
    this.token = null;
    try {
      await this.d.storage.remove(TOKEN_KEY);
    } catch (e) {
      /* ignore */
    }
  }

  // ---- jobs -------------------------------------------------------------

  createJob(body) {
    return this._call("job.create", "POST", "/v1/jobs", body);
  }

  cancelJob(id) {
    return this._call("job.cancel", "DELETE", `/v1/jobs/${encodeURIComponent(id)}`, { jobId: id });
  }

  markImported(id, sequenceName) {
    return this._call("job.imported", "POST", `/v1/jobs/${encodeURIComponent(id)}/imported`, {
      jobId: id,
      sequenceName,
    });
  }

  async getJob(id) {
    if (this.mode === "http") return this._http("GET", `/v1/jobs/${encodeURIComponent(id)}`);
    if (this.mode === "file") {
      const text = await this.d.files.readText(this._bp("jobs", `${id}.json`));
      return JSON.parse(text);
    }
    throw new BridgeError("offline", "SYN isn't running.");
  }

  async listJobs() {
    if (this.mode === "http") {
      const res = await this._http("GET", "/v1/jobs");
      return (res && res.jobs) || [];
    }
    if (this.mode === "file") {
      const dir = this._bp("jobs");
      let names = [];
      try {
        names = await this.d.files.list(dir);
      } catch (e) {
        return [];
      }
      const jobs = [];
      for (const n of names) {
        if (!/\.json$/i.test(n)) continue;
        try {
          jobs.push(JSON.parse(await this.d.files.readText(this.d.sep === "\\" ? `${dir}\\${n}` : `${dir}/${n}`)));
        } catch (e) {
          /* half-written or pruned; skip */
        }
      }
      return jobs;
    }
    return [];
  }

  /** Job ids the user sent with "Send to Premiere" (file transport signal). */
  async pendingSends() {
    if (this.mode !== "file") return [];
    try {
      const names = await this.d.files.list(this._bp("send"));
      return names.filter((n) => /\.json$/i.test(n)).map((n) => n.replace(/\.json$/i, ""));
    } catch (e) {
      return [];
    }
  }

  async clearSend(id) {
    if (this.mode !== "file") return;
    try {
      await this.d.files.remove(this._bp("send", `${id}.json`));
    } catch (e) {
      /* already gone */
    }
  }

  /** The synced XML as text, when the plugin can't read result.xmlPath itself. */
  async resultXml(id) {
    if (this.mode === "http") return this._http("GET", `/v1/jobs/${encodeURIComponent(id)}/result.xml`, null, { text: true });
    throw new BridgeError("unavailable", "No XML route over the file transport.");
  }

  // ---- plumbing ---------------------------------------------------------

  _bp(...parts) {
    return joinPath(this.d.sep, this.d.bridgeDir, ...parts);
  }

  async _call(op, method, path, body) {
    if (this.mode === "http") return this._http(method, path, method === "DELETE" ? null : body);
    if (this.mode === "file") return this._fileRequest(op, body);
    throw new BridgeError("offline", "SYN isn't running.");
  }

  async _http(method, path, body, { auth = true, text = false } = {}) {
    const headers = { Accept: text ? "application/xml" : "application/json" };
    if (body != null) headers["Content-Type"] = "application/json";
    if (auth) {
      await this.loadToken();
      if (this.token) headers.Authorization = `Bearer ${this.token}`;
    }
    let res;
    try {
      res = await this.d.fetch(`${this.base}${path}`, {
        method,
        headers,
        body: body != null ? JSON.stringify(body) : undefined,
      });
    } catch (e) {
      this.mode = "offline";
      throw new BridgeError("offline", "Lost the connection to SYN.");
    }
    if (res.status === 401) {
      await this.forgetToken();
      throw new BridgeError("unauthorized", "SYN needs you to connect Premiere again.", 401);
    }
    if (!res.ok) {
      let err = { code: `http_${res.status}`, message: `SYN answered ${res.status}.` };
      try {
        const j = await res.json();
        if (j && j.error) err = j.error;
      } catch (e) {
        /* not json */
      }
      throw new BridgeError(err.code, err.message, res.status);
    }
    if (text) return res.text();
    if (res.status === 204) return {};
    return res.json();
  }

  async _fileRequest(op, body) {
    const f = this.d.files;
    const reqId = newId();
    for (const sub of ["requests", "responses"]) {
      try {
        await f.mkdir(this._bp(sub));
      } catch (e) {
        /* exists */
      }
    }
    const target = this._bp("requests", `${reqId}.json`);
    await f.writeText(`${target}.tmp`, JSON.stringify({ op, body }));
    await f.rename(`${target}.tmp`, target);

    const respPath = this._bp("responses", `${reqId}.json`);
    const started = this.d.now();
    while (this.d.now() - started < this.d.responseTimeoutMs) {
      await this.d.sleep(150);
      let text = null;
      try {
        if (await f.exists(respPath)) text = await f.readText(respPath);
      } catch (e) {
        text = null;
      }
      if (text == null) continue;
      let resp;
      try {
        resp = JSON.parse(text);
      } catch (e) {
        continue; // mid-rename on some file systems; read again
      }
      try {
        await f.remove(respPath);
      } catch (e) {
        /* app prunes */
      }
      if (resp && resp.error) throw new BridgeError(resp.error.code, resp.error.message);
      return resp;
    }
    try {
      await f.remove(target);
    } catch (e) {
      /* app may have taken it */
    }
    throw new BridgeError("timeout", "SYN didn't pick up the request. Is it still open?");
  }
}

module.exports = { Bridge, BridgeError, appDataDir, compareVersions, joinPath, PORTS, API, HEARTBEAT_FRESH_MS };
