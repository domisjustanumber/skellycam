// GF08 copy of scripts/chromium_sync_scrub/harness/harness.mjs (2026-11-10): adds test=tssync (GF08 block before TESTS). The original file is unchanged.
// chromium_sync_scrub page logic. Tests (query ?test=):
//   caps        codec/API support probe
//   seek        random or step seeks on one clip via one path; reads back the burned-in frame index
//   sync        N streams playing together; per-tick index spread (<video> free / UI leader-follower / master clock)
//   scrub       simulated slider drag; frames shown per second
//   jpegcompat  decode the cameras' own JPEG bytes (corpus) with createImageBitmap and ImageDecoder
//   mp4box      parse MP4 clips with mp4box.js and compare its sample table with the recorder index
//   jpegmkv     (intra_playback) fetch camera JPEGs out of an MKV by byte range (recorder index), compare with the corpus
//               file byte for byte, decode with createImageBitmap and ImageDecoder
// sync path video-rvfc (intra_playback): followers steered by rVFC-reported frame index (playbackRate nudge, hard seek
//   to the leader's mid-frame target when > 6 frames off) instead of currentTime.
// medialog=1 in a batch config: GET /metrics/media after each config (decoder name per player; Electron main --medialog=1).
// bench=1 adds timing fields; without it only functional fields are recorded.
const P = Object.fromEntries(new URLSearchParams(location.search));
const BENCH = P.bench === '1';
const statusEl = document.getElementById('status');
const grid = document.getElementById('grid');
const BITS = 16, CELLS = 32;

function status(s) { statusEl.textContent = s; }
function log(s) { fetch('/log', { method: 'POST', body: String(s) }).catch(() => {}); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const now = () => performance.now();
function mulberry32(a) { return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
function pct(arr, q) { if (!arr.length) return null; const s = [...arr].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.floor(q * (s.length - 1) + 0.5))]; }
function stats(arr) { return arr.length ? { n: arr.length, p50: pct(arr, 0.5), p95: pct(arr, 0.95), max: Math.max(...arr), mean: arr.reduce((a, b) => a + b, 0) / arr.length } : { n: 0 }; }
function hist(arr) { const h = {}; for (const x of arr) h[x] = (h[x] || 0) + 1; return h; }
function once(el, ev, timeoutMs = 20000) {
  return new Promise((ok, bad) => {
    const t = setTimeout(() => bad(new Error(`timeout waiting for ${ev}`)), timeoutMs);
    el.addEventListener(ev, (e) => { clearTimeout(t); ok(e); }, { once: true });
    el.addEventListener('error', () => { clearTimeout(t); bad(new Error(`media error ${el.error && el.error.code} ${el.error && el.error.message}`)); }, { once: true });
  });
}
function hex2bytes(h) { const b = new Uint8Array(h.length / 2); for (let i = 0; i < b.length; i++) b[i] = parseInt(h.substr(2 * i, 2), 16); return b; }
async function getManifest() { return (await fetch('/media/clips/manifest.json', { cache: 'no-store' })).json(); }
function metrics(cmd) { return fetch(`/metrics/${cmd}`).then((r) => r.json()).catch(() => null); }

// ---- index pattern reader -------------------------------------------------------------
const rc = new OffscreenCanvas(CELLS * 2, 1);
const rctx = rc.getContext('2d', { willReadFrequently: true });
function readIndex(src, w, h) {
  const cw = Math.floor(w / CELLS);
  rctx.imageSmoothingEnabled = false;
  rctx.clearRect(0, 0, CELLS * 2, 1);
  rctx.drawImage(src, 0, 0, cw * CELLS, cw, 0, 0, CELLS * 2, 1);
  const d = rctx.getImageData(0, 0, CELLS * 2, 1).data;
  let v = 0;
  for (let b = 0; b < BITS; b++) {
    const i1 = (4 * b + 1) * 4, i2 = (4 * b + 3) * 4;
    const a = (d[i1] + d[i1 + 1] + d[i1 + 2]) / 3, c = (d[i2] + d[i2 + 1] + d[i2 + 2]) / 3;
    if (Math.abs(a - c) <= 64) return null;
    v = (v << 1) | (a > c ? 1 : 0);
  }
  return v;
}
function nearestIdx(pts, t) { // index of pts closest to t
  let lo = 0, hi = pts.length - 1;
  while (lo < hi) { const m = (lo + hi) >> 1; if (pts[m] < t) lo = m + 1; else hi = m; }
  if (lo > 0 && Math.abs(pts[lo - 1] - t) <= Math.abs(pts[lo] - t)) return lo - 1;
  return lo;
}
function floorIdx(pts, t) { // last index with pts <= t
  let lo = 0, hi = pts.length - 1, r = 0;
  while (lo <= hi) { const m = (lo + hi) >> 1; if (pts[m] <= t + 1e-9) { r = m; lo = m + 1; } else hi = m - 1; }
  return r;
}
function seekTarget(clip, k, mode) {
  const pts = clip.pts_s, fps = clip.nominal_fps;
  if (mode === 'ui') return k / fps;                      // what SyncedVideoPlayer does today
  if (mode === 'cfrmid') return (k + 0.5) / fps;          // mid-frame assuming CFR
  if (mode === 'ptsexact') return pts[k];                 // exactly the container pts
  const next = k + 1 < pts.length ? pts[k + 1] : pts[k] + 1 / fps;
  return (pts[k] + next) / 2;                              // 'mid': midpoint between this and next real pts
}

// ---- <video> helpers ------------------------------------------------------------------
async function openVideo(url, parent = grid) {
  const v = document.createElement('video');
  v.muted = true; v.preload = 'auto'; v.playsInline = true; v.crossOrigin = 'anonymous';
  parent.appendChild(v);
  const p = once(v, 'loadeddata');
  v.src = url;
  await p;
  return v;
}
function seekVideo(v, t) {
  return new Promise((ok) => {
    const t0 = now(); let tSeeked = null, rv = null, done = false;
    const finish = () => { if (done) return; done = true; ok({ t0, tSeeked, rv }); };
    v.requestVideoFrameCallback((n, md) => { rv = { cbNow: now(), now: n, mediaTime: md.mediaTime, presentedFrames: md.presentedFrames, expectedDisplayTime: md.expectedDisplayTime }; if (tSeeked !== null) finish(); });
    v.addEventListener('seeked', () => { tSeeked = now(); if (rv) finish(); else setTimeout(finish, 300); }, { once: true });
    v.currentTime = t;
    setTimeout(finish, 5000);
  });
}
function layout(n) { const cols = Math.ceil(Math.sqrt(n)); grid.style.gridTemplateColumns = `repeat(${cols}, 1fr)`; grid.style.gridTemplateRows = `repeat(${Math.ceil(n / cols)}, 1fr)`; }

// ---- WebCodecs source (recorder index -> EncodedVideoChunk) -----------------------------
class WcSource {
  constructor(clip, url, opts = {}) {
    this.clip = clip; this.url = url; this.opts = opts;
    this.ts = clip.pts_s.map((p) => Math.round(p * 1e6));
    this.tsToIdx = new Map(this.ts.map((t, i) => [t, i]));
    this.region = null; this.lastFed = -1; this.needKey = true; this.waiter = null;
    this.flushes = 0; this.resets = 0; this.outputs = 0; this.err = null; this.fetches = 0; this.fetchedBytes = 0;
  }
  async init() {
    const c = this.clip;
    this.config = { codec: c.codec_string, codedWidth: c.width, codedHeight: c.height, optimizeForLatency: true,
      hardwareAcceleration: this.opts.hw || 'no-preference' };
    if (c.description_hex) this.config.description = hex2bytes(c.description_hex);
    const s = await VideoDecoder.isConfigSupported(this.config);
    if (!s.supported) throw new Error(`config not supported ${JSON.stringify({ ...this.config, description: undefined })}`);
    this.dec = new VideoDecoder({ output: (f) => this._out(f), error: (e) => { this.err = String(e); if (this.waiter) this.waiter.res(null); } });
    this.dec.configure(this.config);
  }
  _out(f) {
    this.outputs++;
    const i = this.tsToIdx.get(f.timestamp);
    if (this.waiter && i === this.waiter.k) { const w = this.waiter; this.waiter = null; w.res(f); }
    else f.close();
  }
  keyFor(k) { const ks = this.clip.keyframes; let lo = 0, hi = ks.length - 1, r = 0; while (lo <= hi) { const m = (lo + hi) >> 1; if (ks[m] <= k) { r = ks[m]; lo = m + 1; } else hi = m - 1; } return r; }
  async ensure(i0, i1) {
    const c = this.clip; let a = Infinity, b = 0;
    for (let i = i0; i <= i1; i++) { a = Math.min(a, c.offsets[i]); b = Math.max(b, c.offsets[i] + c.sizes[i]); }
    if (this.region && this.region.a <= a && this.region.b >= b) return;
    const r = await fetch(this.url, { headers: { Range: `bytes=${a}-${b - 1}` }, cache: 'no-store' });
    this.region = { a, b, data: new Uint8Array(await r.arrayBuffer()) };
    this.fetches++; this.fetchedBytes += b - a;
  }
  chunk(i) {
    const c = this.clip, o = c.offsets[i] - this.region.a;
    return new EncodedVideoChunk({ type: c.keyframes.includes(i) ? 'key' : 'delta', timestamp: this.ts[i], data: this.region.data.subarray(o, o + c.sizes[i]) });
  }
  async frameAt(k) {
    const key = this.keyFor(k);
    let start;
    if (!this.needKey && this.lastFed >= key && this.lastFed < k) start = this.lastFed + 1;
    else { start = key; if (this.lastFed !== -1) { this.dec.reset(); this.dec.configure(this.config); this.resets++; } }
    await this.ensure(start, k);
    const p = new Promise((res) => { this.waiter = { k, res }; });
    for (let i = start; i <= k; i++) this.dec.decode(this.chunk(i));
    this.lastFed = k; this.needKey = false;
    if (this.opts.flushEach) { // intra_playback: every chunk is a key frame; flush() forces the decoder to emit frame k now
      this.flushes++; this.needKey = true;
      await Promise.race([this.dec.flush().catch(() => {}), sleep(5000)]);
      const f0 = await Promise.race([p, sleep(5000).then(() => null)]);
      if (f0 === null) throw new Error(`no output for frame ${k} after flush (decoder state ${this.dec.state}, err ${this.err})`);
      return { frame: f0, decoded: k - start + 1 };
    }
    let f = await Promise.race([p, sleep(this.opts.flushAfterMs || 200).then(() => undefined)]);
    if (f === undefined) {
      this.flushes++; this.needKey = true;
      await Promise.race([this.dec.flush(), sleep(5000)]);
      f = await Promise.race([p, sleep(5000).then(() => null)]);
      if (f === null) throw new Error(`no output for frame ${k} after flush (decoder state ${this.dec.state}, err ${this.err})`);
    }
    return { frame: f, decoded: k - start + 1 };
  }
  close() { try { this.dec.close(); } catch { /* */ } }
}

// ---- JPEG sequence source -------------------------------------------------------------
class JpegSource {
  constructor(clip, mode, opts = {}) { // mode: range-bitmap | range-imagedecoder | folder-bitmap | folder-imagedecoder
    this.clip = clip; this.mode = mode; this.block = opts.block || 1; this.cache = null; this.fetches = 0;
  }
  async init() { }
  async bytes(k) {
    const c = this.clip;
    if (this.mode.startsWith('folder')) {
      this.fetches++;
      const r = await fetch(`${c.folder_url}frame_${String(k).padStart(6, '0')}.jpg${this.q || ''}`, { cache: 'no-store' });
      return new Uint8Array(await r.arrayBuffer());
    }
    if (!(this.cache && k >= this.cache.k0 && k <= this.cache.k1)) {
      const k1 = Math.min(c.frames - 1, k + this.block - 1);
      const a = c.offsets[k], b = c.offsets[k1] + c.sizes[k1];
      const r = await fetch(c.url + (this.q || ''), { headers: { Range: `bytes=${a}-${b - 1}` }, cache: 'no-store' });
      this.cache = { k0: k, k1, a, data: new Uint8Array(await r.arrayBuffer()) };
      this.fetches++;
    }
    const o = c.offsets[k] - this.cache.a;
    return this.cache.data.subarray(o, o + c.sizes[k]);
  }
  async frameAt(k) {
    const b = await this.bytes(k);
    if (this.mode.endsWith('bitmap')) return { frame: await createImageBitmap(new Blob([b], { type: 'image/jpeg' })), decoded: 1 };
    const d = new ImageDecoder({ data: b, type: 'image/jpeg' });
    const r = await d.decode(); d.close();
    return { frame: r.image, decoded: 1 };
  }
  close() { }
}
function makeSource(clip, path, opts) {
  if (path === 'webcodecs' || path === 'webcodecs-hw' || path === 'webcodecs-sw') {
    return new WcSource(clip, clip.url + (opts.q || ''), { ...opts, hw: path === 'webcodecs-hw' ? 'prefer-hardware' : path === 'webcodecs-sw' ? 'prefer-software' : 'no-preference' });
  }
  const s = new JpegSource(clip, path.replace(/^jpeg-/, ''), opts); s.q = opts.q; return s;
}

// ---- tests ----------------------------------------------------------------------------
async function testCaps() {
  const m = await getManifest();
  const codecs = [...new Set(Object.values(m.clips).filter((c) => c.kind === 'video').map((c) => `${c.container}|${c.codec_string}`))];
  const extra = ['mp4|hvc1.1.6.L93.B0', 'mp4|av01.0.08M.10', 'webm|vp8', 'mp4|avc1.42E01E', 'mp4|vp09.00.40.08', 'webm|av01.0.08M.08', 'mp4|av01.0.09M.08', 'webm|vp09.00.41.08'];
  const out = { userAgent: navigator.userAgent, isSecureContext, crossOriginIsolated, api: {
    VideoDecoder: typeof VideoDecoder, VideoEncoder: typeof VideoEncoder, ImageDecoder: typeof ImageDecoder, VideoFrame: typeof VideoFrame,
    requestVideoFrameCallback: 'requestVideoFrameCallback' in HTMLVideoElement.prototype, fastSeek: 'fastSeek' in HTMLMediaElement.prototype,
    MediaSource: typeof MediaSource, ManagedMediaSource: typeof ManagedMediaSource, webgpu: !!navigator.gpu,
    OffscreenCanvas: typeof OffscreenCanvas, createImageBitmap: typeof createImageBitmap }, codecs: [] , images: {} };
  const v = document.createElement('video');
  for (const cc of [...new Set([...codecs, ...extra])]) {
    const [cont, codec] = cc.split('|');
    const type = `video/${cont === 'mkv' ? 'x-matroska' : cont}; codecs="${codec}"`;
    const row = { container: cont, codec, canPlayType: v.canPlayType(type), mseIsTypeSupported: typeof MediaSource !== 'undefined' ? MediaSource.isTypeSupported(type) : null };
    for (const [w, h, fps] of [[1280, 720, 30], [1920, 1080, 30], [1280, 720, 60]]) {
      const key = `${h}p${fps}`;
      for (const hw of ['no-preference', 'prefer-hardware', 'prefer-software']) {
        try { const s = await VideoDecoder.isConfigSupported({ codec, codedWidth: w, codedHeight: h, hardwareAcceleration: hw }); row[`wc_${key}_${hw}`] = s.supported; }
        catch (e) { row[`wc_${key}_${hw}`] = `throws: ${e.name}`; }
      }
      try {
        const d = await navigator.mediaCapabilities.decodingInfo({ type: 'file', video: { contentType: type, width: w, height: h, bitrate: 8e6, framerate: fps } });
        row[`mc_${key}`] = `${d.supported ? 'supported' : 'unsupported'}/${d.smooth ? 'smooth' : 'not-smooth'}/${d.powerEfficient ? 'powerEfficient' : 'not-powerEfficient'}`;
      } catch (e) { row[`mc_${key}`] = `throws: ${e.name}`; }
    }
    out.codecs.push(row);
  }
  for (const t of ['image/jpeg', 'image/png', 'image/webp', 'image/avif', 'image/gif', 'image/bmp', 'image/jxl']) {
    out.images[t] = typeof ImageDecoder !== 'undefined' ? await ImageDecoder.isTypeSupported(t) : null;
  }
  return out;
}

async function testSeek() {
  const m = await getManifest();
  const clip = m.clips[P.clip]; if (!clip) throw new Error(`no clip ${P.clip}`);
  const path = P.path || 'video', mode = P.mode || 'mid', n = Number(P.n || 200), seed = Number(P.seed || 1);
  const pattern = P.pattern || 'random';
  const rnd = mulberry32(seed);
  let seq = [];
  if (P.ks) { seq = P.ks.split(',').map(Number); } // explicit frame list
  else if (pattern === 'random') { for (let i = 0; i < n; i++) seq.push(Math.floor(rnd() * clip.frames)); }
  else { // step: from random starts, M forward then 2M back
    const M = Number(P.m || 20), starts = Math.max(1, Math.round(n / (3 * M)));
    for (let s = 0; s < starts; s++) {
      const k0 = M + Math.floor(rnd() * (clip.frames - 3 * M));
      seq.push(k0); for (let i = 1; i <= M; i++) seq.push(k0 + i); for (let i = M - 1; i >= -M; i--) seq.push(k0 + i);
    }
  }
  const rows = []; const t0all = now();
  let extra = {};
  if (path === 'video') {
    const v = await openVideo(clip.url + (P.q || ''));
    layout(1);
    await seekVideo(v, seekTarget(clip, 0, 'mid'));
    let prev = 0;
    for (const k of seq) {
      const t = seekTarget(clip, k, mode);
      const r = await seekVideo(v, t);
      const idx = readIndex(v, clip.width, clip.height);
      const mt = r.rv ? r.rv.mediaTime : null;
      const row = { k, idx, mt_idx: mt === null ? null : nearestIdx(clip.pts_s, mt), rvfc: !!r.rv, t_s: t, step: k - prev };
      if (BENCH) { row.lat_seeked_ms = r.tSeeked === null ? null : r.tSeeked - r.t0; row.lat_rvfc_ms = r.rv ? r.rv.cbNow - r.t0 : null; }
      rows.push(row); prev = k;
      if (rows.length % 25 === 0) status(`seek ${rows.length}/${seq.length}`);
    }
    extra = { readyState: v.readyState, duration: v.duration, videoWidth: v.videoWidth, videoHeight: v.videoHeight };
  } else {
    const src = makeSource(clip, path, { q: P.q, flushAfterMs: Number(P.flushms || 200), flushEach: P.wcflush === '1' });
    await src.init();
    let prev = 0;
    for (const k of seq) {
      const ta = now();
      let r, err = null;
      try { r = await src.frameAt(k); } catch (e) { err = String(e); }
      const tb = now();
      let idx = null;
      if (r && r.frame) { idx = readIndex(r.frame, clip.width, clip.height); r.frame.close(); }
      const row = { k, idx, decoded: r ? r.decoded : null, step: k - prev, err };
      if (BENCH) row.lat_ms = tb - ta;
      rows.push(row); prev = k;
      if (rows.length % 25 === 0) status(`seek ${rows.length}/${seq.length}`);
    }
    extra = { flushes: src.flushes, resets: src.resets, decoder_error: src.err, fetches: src.fetches,
      decoded_hist: hist(rows.map((r) => r.decoded)), errors: rows.filter((r) => r.err).length, first_error: (rows.find((r) => r.err) || {}).err || null };
    src.close();
  }
  const exact = rows.filter((r) => r.idx === r.k).length;
  const summary = { clip: P.clip, path, mode, pattern, n: rows.length, exact, exact_pct: 100 * exact / rows.length,
    unreadable: rows.filter((r) => r.idx === null).length, off_by_hist: hist(rows.filter((r) => r.idx !== null && r.idx !== r.k).map((r) => r.idx - r.k)),
    ...extra };
  if (path === 'video') {
    summary.rvfc_fired = rows.filter((r) => r.rvfc).length;
    summary.mediatime_idx_equals_pattern = rows.filter((r) => r.mt_idx !== null && r.mt_idx === r.idx).length;
  }
  if (pattern === 'step') {
    summary.fwd_exact = rows.filter((r) => r.step === 1 && r.idx === r.k).length; summary.fwd_n = rows.filter((r) => r.step === 1).length;
    summary.back_exact = rows.filter((r) => r.step === -1 && r.idx === r.k).length; summary.back_n = rows.filter((r) => r.step === -1).length;
  }
  if (BENCH) {
    const lat = (f) => stats(rows.filter((r) => r[f] !== null && r[f] !== undefined).map((r) => r[f]));
    if (path === 'video') { summary.lat_seeked_ms = lat('lat_seeked_ms'); summary.lat_rvfc_ms = lat('lat_rvfc_ms');
      if (pattern === 'step') { summary.lat_fwd_ms = stats(rows.filter((r) => r.step === 1).map((r) => r.lat_rvfc_ms ?? r.lat_seeked_ms)); summary.lat_back_ms = stats(rows.filter((r) => r.step === -1).map((r) => r.lat_rvfc_ms ?? r.lat_seeked_ms)); } }
    else { summary.lat_ms = lat('lat_ms');
      if (pattern === 'step') { summary.lat_fwd_ms = stats(rows.filter((r) => r.step === 1).map((r) => r.lat_ms)); summary.lat_back_ms = stats(rows.filter((r) => r.step === -1).map((r) => r.lat_ms)); } }
    summary.wall_s = (now() - t0all) / 1000;
  }
  return { summary, rows };
}

// ---- playback players for master-clock sync -------------------------------------------
class WcPlayer { // sequential decode-ahead
  constructor(clip, url, hw) { this.src = new WcSource(clip, url, { hw }); this.clip = clip; this.q = []; this.next = 0; this.stopped = false; this.chunkBlock = 30; }
  async init() {
    await this.src.init();
    this.src._out = (f) => { this.src.outputs++; this.q.push({ i: this.src.tsToIdx.get(f.timestamp), f }); };
    this.feed();
  }
  async feed() {
    const s = this.src, c = this.clip;
    while (!this.stopped && this.next < c.frames) {
      if (this.q.length + s.dec.decodeQueueSize >= 8) { await sleep(2); continue; }
      const k1 = Math.min(c.frames - 1, this.next + this.chunkBlock - 1);
      await s.ensure(this.next, k1);
      while (this.next <= k1 && !this.stopped) {
        if (this.q.length + s.dec.decodeQueueSize >= 8) { await sleep(2); continue; }
        s.dec.decode(s.chunk(this.next)); this.next++;
      }
    }
    if (!this.stopped) s.dec.flush().catch(() => {});
  }
  take(target) { // newest frame with index <= target; frames older are closed
    let best = null;
    while (this.q.length && this.q[0].i <= target) { if (best) best.f.close(); best = this.q.shift(); }
    return best;
  }
  close() { this.stopped = true; for (const x of this.q) x.f.close(); this.q = []; this.src.close(); }
}
class JpegPlayer {
  constructor(clip, mode, q) { this.src = new JpegSource(clip, mode, { block: 15 }); this.src.q = q; this.clip = clip; this.q = []; this.next = 0; this.stopped = false; }
  async init() { this.feed(); }
  async feed() {
    while (!this.stopped && this.next < this.clip.frames) {
      if (this.q.length >= 8) { await sleep(2); continue; }
      const k = this.next++;
      const r = await this.src.frameAt(k);
      if (this.stopped) { r.frame.close(); break; }
      this.q.push({ i: k, f: r.frame });
    }
  }
  take(target) { let best = null; while (this.q.length && this.q[0].i <= target) { if (best) best.f.close(); best = this.q.shift(); } return best; }
  close() { this.stopped = true; for (const x of this.q) x.f.close(); this.q = []; }
}

async function testSync() {
  const m = await getManifest();
  const clip = m.clips[P.clip]; const N = Number(P.n || 4); const dur = Number(P.dur || 10) * 1000;
  const path = P.path || 'video-free'; const readPat = P.readpattern === '1';
  const fps = clip.nominal_fps, pts = clip.pts_s;
  layout(N);
  const ticks = []; let corrections = 0, hardSeeks = 0, rateChanges = 0;
  const result = { clip: P.clip, path, n: N };
  if (path.startsWith('video')) {
    const vids = [];
    for (let i = 0; i < N; i++) vids.push(await openVideo(`${clip.url}?cam=${i}`));
    const last = vids.map(() => ({ idx: 0, cbs: 0, pf0: null, pf: 0, patternBad: 0, bad: [] }));
    let running = true;
    vids.forEach((v, i) => {
      const cb = (n, md) => {
        if (!running) return;
        const L = last[i]; L.idx = nearestIdx(pts, md.mediaTime); L.cbs++; if (L.pf0 === null) L.pf0 = md.presentedFrames; L.pf = md.presentedFrames;
        if (path === 'video-rvfc' && i > 0) { // steer this follower from rVFC frame indices only
          const d = L.idx - last[0].idx;
          if (Math.abs(d) > 6) { const k = Math.min(pts.length - 1, last[0].idx + 1); v.currentTime = seekTarget(clip, k, 'mid'); hardSeeks++; v.playbackRate = 1; }
          else { const r = d === 0 ? 1 : Math.max(0.8, Math.min(1.2, 1 - 0.05 * d)); if (r !== v.playbackRate) { v.playbackRate = r; rateChanges++; } }
        }
        if (readPat) { const pi = readIndex(v, clip.width, clip.height); if (pi !== L.idx) { L.patternBad++; if (L.bad.length < 20) L.bad.push({ mt_idx: L.idx, pattern: pi, mediaTime: md.mediaTime }); } }
        v.requestVideoFrameCallback(cb);
      };
      v.requestVideoFrameCallback(cb);
    });
    await metrics('start');
    const t0 = now();
    // same order as SyncedVideoPlayer.playAllVideos: leader first, then followers
    for (const v of vids) v.play().catch((e) => log(`play error ${e}`));
    let counter = 0;
    await new Promise((done) => {
      const tick = () => {
        const t = now() - t0;
        if (t > dur) { done(); return; }
        const idxs = last.map((L) => L.idx);
        ticks.push({ t, spread: Math.max(...idxs) - Math.min(...idxs), leader: idxs[0] });
        if (path === 'video-leader' && ++counter >= 15) { // SyncedVideoPlayer.tsx follower correction
          counter = 0; const lt = vids[0].currentTime; const tol = 2 / fps;
          for (let i = 1; i < N; i++) if (Math.abs(vids[i].currentTime - lt) > tol) { vids[i].currentTime = lt; corrections++; }
        }
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
    running = false;
    await metrics('stop');
    for (const v of vids) v.pause();
    result.per_stream = last.map((L) => ({ rvfc_callbacks: L.cbs, presented_frames_delta: L.pf - (L.pf0 ?? 0), pattern_mismatch: readPat ? L.patternBad : undefined,
      mismatch_examples: readPat && L.bad.length ? L.bad : undefined }));
    result.follower_corrections = corrections;
    if (path === 'video-rvfc') { result.rvfc_hard_seeks = hardSeeks; result.rvfc_rate_changes = rateChanges; }
    result.dropped = vids.map((v) => { const q = v.getVideoPlaybackQuality(); return { total: q.totalVideoFrames, dropped: q.droppedVideoFrames }; });
  } else {
    const canv = []; const players = [];
    for (let i = 0; i < N; i++) {
      const c = document.createElement('canvas'); c.width = clip.width; c.height = clip.height; grid.appendChild(c); canv.push(c.getContext('2d'));
      const p = path.startsWith('wc') ? new WcPlayer(clip, `${clip.url}?cam=${i}`, path === 'wc-master-hw' ? 'prefer-hardware' : 'no-preference')
        : new JpegPlayer(clip, path.replace(/^jpeg-master-/, ''), `?cam=${i}`);
      await p.init(); players.push(p);
    }
    // prebuffer
    const tw = now(); while (players.some((p) => p.q.length < 3) && now() - tw < 10000) await sleep(5);
    const shown = players.map(() => ({ idx: -1, draws: 0, patternBad: 0 }));
    await metrics('start');
    const t0 = now();
    await new Promise((done) => {
      const tick = () => {
        const t = now() - t0;
        if (t > dur) { done(); return; }
        const target = floorIdx(pts, t / 1000);
        players.forEach((p, i) => {
          const b = p.take(target);
          if (b) {
            canv[i].drawImage(b.f, 0, 0);
            if (readPat) { const pi = readIndex(b.f, clip.width, clip.height); if (pi !== b.i) shown[i].patternBad++; }
            b.f.close(); shown[i].idx = b.i; shown[i].draws++;
          }
        });
        const idxs = shown.map((s) => s.idx);
        ticks.push({ t, spread: Math.max(...idxs) - Math.min(...idxs), target, lag_max: target - Math.min(...idxs) });
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
    await metrics('stop');
    result.per_stream = shown.map((s) => ({ draws: s.draws, pattern_mismatch: readPat ? s.patternBad : undefined }));
    players.forEach((p) => p.close());
  }
  result.ticks = ticks.length;
  result.spread_hist = hist(ticks.map((x) => x.spread));
  result.spread_exact0_pct = 100 * ticks.filter((x) => x.spread === 0).length / Math.max(1, ticks.length);
  if (BENCH) {
    result.spread = stats(ticks.map((x) => x.spread));
    result.dur_s = dur / 1000;
    if (ticks[0] && ticks[0].lag_max !== undefined) result.lag_max = stats(ticks.map((x) => x.lag_max));
    result.rvfc_or_draws_per_s = (result.per_stream || []).map((s) => (s.rvfc_callbacks ?? s.draws) / (dur / 1000));
  }
  return result;
}

async function testScrub() {
  const m = await getManifest();
  const clip = m.clips[P.clip]; const N = Number(P.n || 1); const dur = Number(P.dur || 5) * 1000;
  const path = P.path || 'video-ui'; const speed = Number(P.speed || 90); // frames per second of slider motion
  const fps = clip.nominal_fps, F = clip.frames, pts = clip.pts_s;
  layout(N);
  const tri = (t) => { const span = F - 1; const x = (t / 1000 * speed) % (2 * span); return Math.round(x <= span ? x : 2 * span - x); };
  let target = 0; const lags = []; const res = { clip: P.clip, path, n: N, speed_frames_per_s: speed };
  if (path.startsWith('video')) {
    const vids = []; for (let i = 0; i < N; i++) vids.push(await openVideo(`${clip.url}?cam=${i}`));
    const st = vids.map(() => ({ shown: -1, presents: 0, distinct: new Set(), pending: null }));
    let running = true;
    vids.forEach((v, i) => {
      const cb = (n, md) => { if (!running) return; const s = st[i]; s.shown = nearestIdx(pts, md.mediaTime); s.presents++; s.distinct.add(s.shown); v.requestVideoFrameCallback(cb); };
      v.requestVideoFrameCallback(cb);
      v.addEventListener('seeked', () => { const s = st[i]; if (path === 'video-gated' && s.pending !== null) { const p = s.pending; s.pending = null; v.currentTime = p; } });
    });
    await metrics('start');
    const t0 = now();
    while (now() - t0 < dur) { // simulated pointer events ~ every 16 ms
      target = tri(now() - t0);
      const t = target / fps; // SyncedVideoPlayer.handleSeekDrag: currentTime = frame / fps
      vids.forEach((v, i) => { if (path === 'video-gated' && v.seeking) st[i].pending = t; else v.currentTime = t; });
      lags.push(Math.max(...st.map((s) => Math.abs(target - s.shown))));
      await sleep(16);
    }
    running = false; await metrics('stop');
    res.per_stream = st.map((s) => ({ presents: s.presents, distinct_frames: s.distinct.size }));
  } else {
    const canv = [], srcs = [];
    for (let i = 0; i < N; i++) {
      const c = document.createElement('canvas'); c.width = clip.width; c.height = clip.height; grid.appendChild(c); canv.push(c.getContext('2d'));
      const s = makeSource(clip, path, { q: `?cam=${i}`, flushEach: P.wcflush === '1' }); await s.init(); srcs.push(s);
    }
    const st = srcs.map(() => ({ shown: -1, presents: 0, distinct: new Set(), errors: 0 }));
    let running = true;
    const loops = srcs.map(async (s, i) => {
      while (running) {
        const k = target;
        if (k === st[i].shown) { await sleep(1); continue; }
        try { const r = await s.frameAt(k); if (r.frame) { canv[i].drawImage(r.frame, 0, 0); r.frame.close(); } st[i].shown = k; st[i].presents++; st[i].distinct.add(k); }
        catch (e) { st[i].errors++; await sleep(5); }
      }
    });
    await metrics('start');
    const t0 = now();
    while (now() - t0 < dur) { target = tri(now() - t0); lags.push(Math.max(...st.map((s) => Math.abs(target - s.shown)))); await sleep(16); }
    running = false; await Promise.all(loops); await metrics('stop');
    res.per_stream = st.map((s) => ({ presents: s.presents, distinct_frames: s.distinct.size, errors: s.errors }));
    srcs.forEach((s) => s.close());
  }
  res.input_events = lags.length;
  if (BENCH) { res.dur_s = dur / 1000; res.frames_shown_per_s = res.per_stream.map((s) => s.presents / (dur / 1000)); res.distinct_per_s = res.per_stream.map((s) => s.distinct_frames / (dur / 1000)); res.lag_frames = stats(lags); }
  return res;
}

async function testJpegCompat() {
  const idx = await (await fetch('/corpus/index.json', { cache: 'no-store' })).json();
  const out = {};
  const cv = new OffscreenCanvas(16, 16); const cx = cv.getContext('2d', { willReadFrequently: true });
  for (const [name, s] of Object.entries(idx)) {
    if (s.kind !== 'mjpeg') continue;
    const nf = Math.min(s.frames, Number(P.maxframes || 30));
    const r = { frames_tested: nf, bitmap_ok: 0, imagedecoder_ok: 0, errors: [], dims: null, imagedecoder_complete: 0 };
    for (let k = 0; k < nf; k++) {
      const b = new Uint8Array(await (await fetch(`/corpus/${name}/frame_${String(k).padStart(6, '0')}.jpg`, { cache: 'no-store' })).arrayBuffer());
      try {
        const bm = await createImageBitmap(new Blob([b], { type: 'image/jpeg' }), { colorSpaceConversion: 'none', premultiplyAlpha: 'none' });
        r.bitmap_ok++; r.dims = [bm.width, bm.height];
        if (k === 0) { cv.width = bm.width; cv.height = bm.height; cx.drawImage(bm, 0, 0); await fetch(`/blob?name=${name}_f0_bitmap_${P.tag || 'x'}.rgba`, { method: 'POST', body: cx.getImageData(0, 0, bm.width, bm.height).data }); }
        bm.close();
      } catch (e) { r.errors.push(`bitmap f${k}: ${e}`); }
      try {
        const d = new ImageDecoder({ data: b, type: 'image/jpeg', colorSpaceConversion: 'none' });
        const res = await d.decode(); r.imagedecoder_ok++; if (res.complete) r.imagedecoder_complete++;
        if (k === 0) { const f = res.image; r.imagedecoder_format = f.format; cv.width = f.displayWidth; cv.height = f.displayHeight; cx.drawImage(f, 0, 0); await fetch(`/blob?name=${name}_f0_imagedecoder_${P.tag || 'x'}.rgba`, { method: 'POST', body: cx.getImageData(0, 0, f.displayWidth, f.displayHeight).data }); }
        res.image.close(); d.close();
      } catch (e) { r.errors.push(`imagedecoder f${k}: ${e}`); }
    }
    out[name] = r;
  }
  return out;
}

async function testMp4box() {
  const MP4Box = await import('/vendor/mp4box/mp4box.all.mjs');
  const m = await getManifest(); const out = {};
  for (const [key, c] of Object.entries(m.clips)) {
    if (c.kind !== 'video' || c.container !== 'mp4') continue;
    const buf = await (await fetch(c.url, { cache: 'no-store' })).arrayBuffer();
    const r = { };
    try {
      const f = MP4Box.createFile();
      let info = null; f.onReady = (i) => { info = i; }; f.onError = (e) => { r.error = String(e); };
      buf.fileStart = 0;
      f.appendBuffer(buf); f.flush();
      if (!info) throw new Error('onReady not called');
      const tr = info.videoTracks[0]; r.mp4box_codec = tr.codec; r.manifest_codec = c.codec_string; r.codec_string_equal = tr.codec.toLowerCase() === c.codec_string.toLowerCase();
      r.mp4box_nb_samples = tr.nb_samples; r.fragmented = info.isFragmented;
      const samples = f.getTrackSamplesInfo(tr.id).map((s) => ({ offset: s.offset, size: s.size, cts: s.cts, ts: s.timescale, sync: s.is_sync }));
      r.samples = samples.length;
      let offOk = 0, sizeOk = 0, ptsOk = 0, syncOk = 0;
      samples.sort((a, b) => a.cts - b.cts);
      samples.forEach((s, i) => { if (s.offset === c.offsets[i]) offOk++; if (s.size === c.sizes[i]) sizeOk++; if (Math.abs(s.cts / s.ts - c.pts_s[i]) < 1e-6) ptsOk++; if (s.sync === c.keyframes.includes(i)) syncOk++; });
      Object.assign(r, { offset_match: offOk, size_match: sizeOk, pts_match: ptsOk, sync_match: syncOk, manifest_frames: c.frames });
    } catch (e) { r.error = String(e); }
    out[key] = r;
  }
  return { mp4box_version: '2.4.1', clips: out };
}

async function testJpegMkv() { // camera JPEG bytes inside an MKV, fetched by byte range from the recorder index
  const m = await getManifest();
  const out = {};
  for (const [key, c] of Object.entries(m.clips)) {
    if (c.kind !== 'camera_mkv') continue;
    const r = { frames: c.frames, range_fetches: 0, bytes_identical: 0, bitmap_ok: 0, imagedecoder_ok: 0, soi_eoi_ok: 0, errors: [] };
    const nf = Math.min(c.frames, Number(P.maxframes || c.frames));
    const rnd = mulberry32(Number(P.seed || 3));
    const order = P.order === 'random' ? Array.from({ length: nf }, () => Math.floor(rnd() * c.frames)) : [...Array(nf).keys()];
    for (const k of order) {
      try {
        const a = c.offsets[k], b = a + c.sizes[k];
        const resp = await fetch(c.url, { headers: { Range: `bytes=${a}-${b - 1}` }, cache: 'no-store' });
        if (resp.status !== 206) throw new Error(`HTTP ${resp.status}`);
        const got = new Uint8Array(await resp.arrayBuffer()); r.range_fetches++;
        const ref = new Uint8Array(await (await fetch(c.corpus_url_pattern.replace('%06d', String(k).padStart(6, '0')), { cache: 'no-store' })).arrayBuffer());
        let same = got.length === ref.length; for (let i = 0; same && i < got.length; i++) if (got[i] !== ref[i]) same = false;
        if (same) r.bytes_identical++;
        if (got[0] === 0xFF && got[1] === 0xD8 && got[got.length - 2] === 0xFF && got[got.length - 1] === 0xD9) r.soi_eoi_ok++;
        const bm = await createImageBitmap(new Blob([got], { type: 'image/jpeg' })); if (bm.width === c.width && bm.height === c.height) r.bitmap_ok++; bm.close();
        const d = new ImageDecoder({ data: got, type: 'image/jpeg' }); const res = await d.decode(); if (res.image.displayWidth === c.width) r.imagedecoder_ok++; res.image.close(); d.close();
      } catch (e) { if (r.errors.length < 5) r.errors.push(`f${k}: ${e}`); }
    }
    r.tested = order.length; r.order = P.order || 'sequential';
    out[key] = r;
  }
  return out;
}

function cleanupGrid() {
  for (const el of [...grid.children]) {
    if (el.tagName === 'VIDEO') { el.pause(); el.removeAttribute('src'); el.load(); }
    el.remove();
  }
}
async function testBatch() { // configs = JSON list of param objects, each run in turn in this renderer
  const base = { ...P }; delete base.configs;
  const cfgs = await (await fetch('/configs', { cache: 'no-store' })).json();
  const out = [];
  for (let i = 0; i < cfgs.length; i++) {
    for (const k of Object.keys(P)) delete P[k];
    Object.assign(P, base, cfgs[i]);
    status(`batch ${i + 1}/${cfgs.length} ${P.test} ${P.clip || ''} ${P.path || ''} ${P.mode || ''}`);
    let r;
    log(`batch ${i + 1}/${cfgs.length} start ${JSON.stringify(cfgs[i])}`);
    const mark = P.medialog === '1' ? await metrics('mediamark') : null;
    const limit = Number(P.testtimeout || 240) * 1000;
    try { r = await Promise.race([TESTS[P.test](), sleep(limit).then(() => { throw new Error(`test timeout ${limit / 1000}s`); })]); }
    catch (e) { r = { error: String(e) }; }
    cleanupGrid();
    if (r && r.summary && r.rows && P.keeprows !== '1') { r.wrong_rows = r.rows.filter((x) => x.idx !== x.k).slice(0, 60); delete r.rows; }
    if (P.medialog === '1' && r && typeof r === 'object') { await sleep(300); r.media = await metrics(`media-${mark && mark.mark}`); }
    out.push({ config: cfgs[i], result: r });
    log(`batch ${i + 1}/${cfgs.length} done: ${JSON.stringify(r && (r.summary || r)).slice(0, 300)}`);
  }
  return out;
}

// ---- GF08 (gap-fill, 2026-11-10): multi-camera sync by capture timestamp, exactness only -----------------
// For each master-clock tick T (integer ns, fixed list from manifest.ticks, visited in the listed shuffled order)
// and each camera, choose a frame from the per-camera sidecar timestamps only (manifest.cams[c].ts_ns):
//   PREV    = largest ts <= T. T < ts[0] -> none (before_start). Last frame and T - ts_last > P -> none (after_end).
//             Otherwise hold; status hold_stale when T - ts_k > P (inside a gap).
//   NEAREST = argmin |ts - T|, ties -> earlier frame. If 2|ts_k - T| > P: none when T is before the first / after
//             the last frame, otherwise hold_stale (inside a gap).
// Then decode the chosen frame and read its identity back:
//   jpeg   : camera bytes from the MKV by Range (index); identity = SHA-256 of the fetched bytes looked up in this
//            camera's own hash table; decoded with ImageDecoder (complete + dimensions checked)
//   jpegbc : barcoded JPEG from the MKV by Range; ImageDecoder; identity = 16-bit pattern (cam*4096 + k)
//   h264   : barcoded all-intra H.264 from the MP4 by Range; WebCodecs VideoDecoder, flush() after each chunk;
//            identity = 16-bit pattern
// Also records what the existing harness helpers floorIdx / nearestIdx (seconds) return for the same tick.
// No timing fields are recorded.
function gfPrev(ts, T, P) {
  if (T < ts[0]) return { k: -1, s: 'before_start' };
  let lo = 0, hi = ts.length - 1;
  while (lo < hi) { const m = Math.floor((lo + hi + 1) / 2); if (ts[m] <= T) lo = m; else hi = m - 1; }
  const age = T - ts[lo];
  if (lo === ts.length - 1 && age > P) return { k: -1, s: 'after_end' };
  return { k: lo, s: age > P ? 'hold_stale' : 'ok' };
}
function gfNearest(ts, T, P) {
  let lo = 0, hi = ts.length - 1;
  while (lo < hi) { const m = Math.floor((lo + hi) / 2); if (ts[m] < T) lo = m + 1; else hi = m; }
  let k = lo;
  if (lo > 0 && (T - ts[lo - 1]) <= Math.abs(ts[lo] - T)) k = lo - 1; // tie -> earlier
  const d2 = 2 * Math.abs(ts[k] - T);
  if (d2 > P && T < ts[0]) return { k: -1, s: 'before_start' };
  if (d2 > P && T > ts[ts.length - 1]) return { k: -1, s: 'after_end' };
  return { k, s: d2 > P ? 'hold_stale' : 'ok' };
}
async function gfRange(url, off, size) {
  const r = await fetch(url, { headers: { Range: `bytes=${off}-${off + size - 1}` }, cache: 'no-store' });
  if (r.status !== 206) throw new Error(`HTTP ${r.status}`);
  return new Uint8Array(await r.arrayBuffer());
}
async function gfSha(b) { const h = new Uint8Array(await crypto.subtle.digest('SHA-256', b)); return Array.from(h, (x) => x.toString(16).padStart(2, '0')).join(''); }
class GfJpeg {
  constructor(c, kind) { this.c = c; this.kind = kind; this.f = c[kind]; this.shaIdx = new Map(c.sha256.map((h, i) => [h, i])); }
  async init() { }
  async ident(k) {
    const b = await gfRange(this.f.url, this.f.offsets[k], this.f.sizes[k]);
    let byteId = null;
    if (this.kind === 'jpeg') { const h = await gfSha(b); byteId = this.shaIdx.has(h) ? this.shaIdx.get(h) : 'unknown'; }
    const d = new ImageDecoder({ data: b, type: 'image/jpeg' });
    const r = await d.decode(); d.close();
    const img = r.image; const dimsOk = img.displayWidth === this.c.width && img.displayHeight === this.c.height;
    let pat = null;
    if (this.kind === 'jpegbc') pat = readIndex(img, this.c.width, this.c.height);
    img.close();
    if (this.kind === 'jpeg') return { id: byteId, cam: null, decode_ok: dimsOk && r.complete };
    return { id: pat === null ? null : pat & 4095, cam: pat === null ? null : pat >> 12, decode_ok: dimsOk && r.complete };
  }
  close() { }
}
class GfWc {
  constructor(c) { this.c = c; this.f = c.h264; this.errors = 0; this.recreated = 0; this.out = []; }
  async init() {
    this.config = { codec: this.f.codec_string, codedWidth: this.c.width, codedHeight: this.c.height, optimizeForLatency: true,
      hardwareAcceleration: 'no-preference', description: hex2bytes(this.f.description_hex) };
    const s = await VideoDecoder.isConfigSupported(this.config);
    if (!s.supported) throw new Error('config not supported');
    this._make();
  }
  _make() {
    this.dec = new VideoDecoder({ output: (fr) => this.out.push(fr), error: (e) => { this.err = String(e); this.errors++; } });
    this.dec.configure(this.config);
  }
  async ident(k) {
    if (this.dec.state === 'closed') { this._make(); this.recreated++; }
    const b = await gfRange(this.f.url, this.f.offsets[k], this.f.sizes[k]);
    for (const x of this.out) x.close();
    this.out = [];
    this.dec.decode(new EncodedVideoChunk({ type: 'key', timestamp: k, data: b }));
    await Promise.race([this.dec.flush().catch((e) => { this.err = String(e); }), sleep(5000)]);
    const fr = this.out.find((x) => x.timestamp === k);
    const n = this.out.length;
    let pat = null;
    if (fr) pat = readIndex(fr, this.c.width, this.c.height);
    for (const x of this.out) x.close();
    this.out = [];
    return { id: pat === null ? null : pat & 4095, cam: pat === null ? null : pat >> 12, decode_ok: !!fr, outputs: n };
  }
  close() { try { this.dec.close(); } catch { /* */ } }
}
async function testTsSync() {
  const m = await (await fetch('/media/manifest.json', { cache: 'no-store' })).json();
  const PP = m.P_ns;
  const camNames = Object.keys(m.cams).sort();
  const paths = (P.paths || 'jpeg,jpegbc,h264').split(',');
  const ticks = [...m.ticks].sort((a, b) => a.order - b.order);
  const out = { isSecureContext, P_ns: PP, cams: camNames, paths, tick_count: ticks.length, row_fields:
    ['t_ns', 'path', 'rule', 'cam', 'chosen_k', 'status', 'read_id', 'read_cam', 'decode_ok', 'harness_floorIdx_s', 'harness_nearestIdx_s'],
    rows: [], per_path: {} };
  for (const path of paths) {
    const srcs = [];
    for (const cn of camNames) { const s = path === 'h264' ? new GfWc(m.cams[cn]) : new GfJpeg(m.cams[cn], path); await s.init(); srcs.push(s); }
    let errs = 0, firstErr = null;
    for (let ti = 0; ti < ticks.length; ti++) {
      const T = ticks[ti].t_ns;
      for (let c = 0; c < camNames.length; c++) {
        const cm = m.cams[camNames[c]], ts = cm.ts_ns;
        const pts_s = cm._pts_s || (cm._pts_s = ts.map((x) => x / 1e9));
        const fl = floorIdx(pts_s, T / 1e9), nr = nearestIdx(pts_s, T / 1e9);
        for (const [rule, fn] of [['PREV', gfPrev], ['NEAREST', gfNearest]]) {
          const ch = fn(ts, T, PP);
          let r = { id: null, cam: null, decode_ok: null };
          if (ch.k >= 0) {
            try { r = await srcs[c].ident(ch.k); } catch (e) { errs++; if (!firstErr) firstErr = String(e); r = { id: null, cam: null, decode_ok: false }; }
          }
          out.rows.push([T, path, rule, c, ch.k, ch.s, r.id, r.cam, r.decode_ok, fl, nr]);
        }
      }
      if (ti % 25 === 0) status(`tssync ${path} ${ti}/${ticks.length}`);
    }
    out.per_path[path] = { errors: errs, first_error: firstErr,
      wc_decoder_errors: path === 'h264' ? srcs.map((s) => s.errors) : undefined, wc_recreated: path === 'h264' ? srcs.map((s) => s.recreated) : undefined };
    srcs.forEach((s) => s.close());
  }
  return out;
}
const TESTS = { tssync: testTsSync, caps: testCaps, seek: testSeek, sync: testSync, scrub: testScrub, jpegcompat: testJpegCompat, mp4box: testMp4box, jpegmkv: testJpegMkv, batch: testBatch };
(async () => {
  let result;
  try { status(`running ${P.test}`); result = await TESTS[P.test](); }
  catch (e) { result = { error: String(e), stack: e && e.stack }; }
  status('done');
  await fetch('/result', { method: 'POST', body: JSON.stringify(result) });
})();
