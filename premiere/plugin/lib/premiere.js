// Everything that touches Premiere's UXP API (require("premierepro")).
// `ppro` is injected so tests can pass a fake.

"use strict";

// Stills, graphics and project files never carry sync audio, so they are left out.
const NOT_SYNCABLE = /\.(png|jpe?g|tiff?|psd|ai|eps|gif|bmp|webp|heic|exr|dpx|svg|prproj|aep|mogrt|xml|srt|vtt)$/i;

function safeName(s) {
  return String(s || "sequence").replace(/[\\/:*?"<>|]+/g, "_").slice(0, 80);
}

function guidKey(seq) {
  try {
    if (seq.guid && typeof seq.guid.toString === "function") return seq.guid.toString();
  } catch (e) {
    /* fall through */
  }
  return seq.name;
}

class PremiereHost {
  constructor({ ppro, hostVersion, tempDir, sep = "/" }) {
    this.ppro = ppro;
    this.hostVersion = hostVersion || "0";
    this.tempDir = tempDir;
    this.sep = sep;
  }

  /** Premiere 26.2+ can write FCP7 XML for a sequence. */
  canExportXml() {
    const pc = this.ppro && this.ppro.ProjectConverter;
    return !!(pc && typeof pc.exportAsFinalCutProXML === "function");
  }

  async project() {
    const p = await this.ppro.Project.getActiveProject();
    if (!p) throw new Error("Open a Premiere project first.");
    return p;
  }

  /** What the panel shows: project, active sequence and the bin selection. */
  async snapshot() {
    const out = { project: null, sequence: null, selection: { media: 0, sequences: 0 }, canExportXml: this.canExportXml() };
    let project;
    try {
      project = await this.ppro.Project.getActiveProject();
    } catch (e) {
      project = null;
    }
    if (!project) return out;
    out.project = { name: project.name, path: project.path };
    try {
      const seq = await project.getActiveSequence();
      if (seq) out.sequence = { name: seq.name };
    } catch (e) {
      /* no active sequence */
    }
    try {
      const sel = await this.collectSelection(project);
      out.selection = { media: sel.media.length, sequences: sel.sequences.length };
    } catch (e) {
      /* selection API unavailable */
    }
    return out;
  }

  // ---- reading the project ---------------------------------------------

  async _binPath(item) {
    const names = [];
    try {
      let bin = item.getParentBin && item.getParentBin();
      for (let i = 0; bin && i < 32; i++) {
        const pi = this.ppro.ProjectItem && this.ppro.ProjectItem.cast ? this.ppro.ProjectItem.cast(bin) : bin;
        const parent = pi && pi.getParentBin ? pi.getParentBin() : null;
        if (!parent) break; // the root bin has no parent; leave its name out
        names.unshift(pi.name);
        bin = parent;
      }
    } catch (e) {
      /* best effort */
    }
    return names.join("/");
  }

  async _asClip(item) {
    try {
      const c = this.ppro.ClipProjectItem.cast(item);
      if (c && typeof c.getMediaFilePath === "function") return c;
    } catch (e) {
      /* not a clip */
    }
    return null;
  }

  async _asFolder(item) {
    try {
      const f = this.ppro.FolderItem.cast(item);
      if (f && typeof f.getItems === "function") {
        await f.getItems(); // throws for non-folders on some builds
        return f;
      }
    } catch (e) {
      /* not a bin */
    }
    return null;
  }

  async _isSequence(clip) {
    try {
      if (typeof clip.isSequence === "function") return !!(await clip.isSequence());
    } catch (e) {
      /* fall through */
    }
    try {
      const t = await clip.getContentType();
      const C = this.ppro.Constants && this.ppro.Constants.ContentType;
      return !!C && t === C.SEQUENCE;
    } catch (e) {
      return false;
    }
  }

  /**
   * Selected project items, bins expanded. Returns
   * { media: [{path, name, bin}], sequences: [Sequence] }, de-duplicated by path.
   */
  async collectSelection(project) {
    const sel = await this.ppro.ProjectUtils.getSelection(project);
    const items = sel ? await sel.getItems() : [];
    const media = [];
    const sequences = [];
    const seen = new Set();
    const visit = async (item, depth) => {
      if (depth > 12) return;
      const clip = await this._asClip(item);
      if (clip) {
        if (await this._isSequence(clip)) {
          const s = await clip.getSequence();
          if (s) sequences.push(s);
          return;
        }
        let path = "";
        try {
          path = await clip.getMediaFilePath();
        } catch (e) {
          path = "";
        }
        if (!path || seen.has(path)) return;
        if (typeof clip.isOffline === "function") {
          try {
            if (await clip.isOffline()) return;
          } catch (e) {
            /* keep it */
          }
        }
        if (NOT_SYNCABLE.test(path)) return;
        seen.add(path);
        media.push({ path, name: item.name || path.split(/[\\/]/).pop(), bin: await this._binPath(item) });
        return;
      }
      const folder = await this._asFolder(item);
      if (folder) {
        for (const child of await folder.getItems()) await visit(child, depth + 1);
      }
    };
    for (const it of items || []) await visit(it, 0);
    return { media, sequences };
  }

  /** Media used on a sequence's tracks; the fallback when Premiere can't export XML. */
  async sequenceMedia(seq) {
    const media = [];
    const seen = new Set();
    const CLIP = (this.ppro.Constants && this.ppro.Constants.TrackItemType && this.ppro.Constants.TrackItemType.CLIP) || 1;
    const walk = async (count, get) => {
      for (let i = 0; i < count; i++) {
        const track = await get(i);
        if (!track) continue;
        const items = (await track.getTrackItems(CLIP, false)) || [];
        for (const ti of items) {
          try {
            const pi = await ti.getProjectItem();
            const clip = await this._asClip(pi);
            if (!clip) continue;
            const path = await clip.getMediaFilePath();
            if (!path || seen.has(path)) continue;
            seen.add(path);
            media.push({ path, name: pi.name, bin: await this._binPath(pi) });
          } catch (e) {
            /* skip unreadable items */
          }
        }
      }
    };
    await walk(await seq.getVideoTrackCount(), (i) => seq.getVideoTrack(i));
    await walk(await seq.getAudioTrackCount(), (i) => seq.getAudioTrack(i));
    return media;
  }

  async exportXml(seq) {
    const path = `${this.tempDir}${this.sep}${safeName(seq.name)}-${Date.now()}.xml`;
    const ok = await this.ppro.ProjectConverter.exportAsFinalCutProXML(seq, path, true);
    if (!ok) throw new Error("Premiere couldn't export the sequence as XML.");
    return path;
  }

  /**
   * Builds the POST /v1/jobs body.
   * what = "sequence" (active sequence) | "selection" (selected clips, bins or sequences).
   */
  async buildJob(what) {
    const project = await this.project();
    const base = { projectPath: project.path, options: { mode: "auto" } };

    if (what === "selection") {
      const sel = await this.collectSelection(project);
      if (sel.media.length) {
        const name = sel.media.length === 1 ? sel.media[0].name : `${project.name.replace(/\.prproj$/i, "")} · ${sel.media.length} clips`;
        return Object.assign(base, { sequenceName: name, source: { kind: "media", items: sel.media } });
      }
      if (sel.sequences.length) return this._sequenceJob(sel.sequences[0], base);
      throw new Error("Select clips, bins or a sequence in the Project panel first.");
    }

    const seq = await project.getActiveSequence();
    if (!seq) throw new Error("Open a sequence first, or send selected clips instead.");
    return this._sequenceJob(seq, base);
  }

  async _sequenceJob(seq, base) {
    if (this.canExportXml()) {
      const path = await this.exportXml(seq);
      return Object.assign(base, { sequenceName: seq.name, source: { kind: "xml", path } });
    }
    const items = await this.sequenceMedia(seq);
    if (!items.length) throw new Error("That sequence has no media on it.");
    return Object.assign(base, { sequenceName: seq.name, source: { kind: "media", items } });
  }

  // ---- bringing results back ---------------------------------------------

  /** Imports SYN's XML and opens the new sequence. Returns its name. */
  async importXml(xmlPath, expectedName) {
    const project = await this.project();
    const before = new Set(((await project.getSequences()) || []).map(guidKey));
    let bin = null;
    try {
      bin = await project.getInsertionBin();
    } catch (e) {
      bin = null;
    }
    if (!bin) bin = await project.getRootItem();
    const ok = await project.importFiles([xmlPath], true, bin, false);
    if (!ok) throw new Error("Premiere couldn't import the synced XML.");
    const after = (await project.getSequences()) || [];
    const fresh = after.filter((s) => !before.has(guidKey(s)));
    const pick = fresh.find((s) => s.name === expectedName) || fresh[fresh.length - 1] || after.find((s) => s.name === expectedName);
    if (pick) {
      try {
        await project.openSequence(pick);
        if (project.setActiveSequence) await project.setActiveSequence(pick);
      } catch (e) {
        /* imported fine, just not opened */
      }
      return pick.name;
    }
    return expectedName || "Synced sequence";
  }
}

module.exports = { PremiereHost, safeName, NOT_SYNCABLE };
