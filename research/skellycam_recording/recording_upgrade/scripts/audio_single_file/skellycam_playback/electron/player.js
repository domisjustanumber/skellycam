// Faithful minimal harness of skellycam-ui's planned canvas player (plan WP 1.9 + §2.8 + audio_skellycam §4.4) with audio.
// Video: per camera, JPEG bytes by Range fetch at sidecar offsets -> ImageDecoder -> canvas tile; the frame shown is PREV
// (the last frame whose sidecar arrival time <= master clock). Audio: one of three engines, chosen by cfg.engine:
//   buf : fetch whole file -> decodeAudioData -> AudioBufferSourceNode.start(when, offset)
//   wc  : windowed: index the file (WAV header / FLAC frame scan / fMP4 moof scan), decode 1 s chunks ahead
//         (WAV: PCM straight into an AudioBuffer; FLAC/Opus: WebCodecs AudioDecoder), schedule back to back
//   el  : HTMLAudioElement (src = the file through the same range scheme) -> MediaElementSource
// Master clock while playing (host seconds since take start) = map(n), n = audio sample being heard:
//   buf/wc, clock 'out'  : n = n0 + (contextTimeAt(P) - when) * SR, contextTimeAt from getOutputTimestamp (plan design)
//   buf/wc, clock 'naive': n = n0 + (ctx.currentTime - when) * SR (ignores output latency)
//   el                   : n = audio.currentTime * SR (the leader.currentTime pattern of today's SyncedVideoPlayer)
//   el, clock 'ellat'    : n = (audio.currentTime - ctx.outputLatency) * SR
// map: 'fit' = CSV footer fit t = t0 + (n - off - n0) * 1e9 / rate_hz; 'nofit' = first CSV row adc_ns + nominal 48 kHz.
// Measurement: tap.js reports the context frame of every click; A = performance time that frame is output
// (getOutputTimestamp). Every camera-0 draw is logged with its rAF timestamp V and the barcode read back from the
// decoded image. Analysis (analyse.py) pairs clicks with flash draws.
const SR = 48000, BASE = 'skr://media/', CHUNK = SR, AHEAD_S = 3, OPUS_PREROLL = 3840;
const sleep = (ms) => new Promise((q) => setTimeout(q, ms));
const url = (n) => BASE + encodeURIComponent(n);
async function fetchRange(name, start, endExcl) {
  const r = await fetch(url(name), { headers: { Range: `bytes=${start}-${endExcl - 1}` } });
  if (r.status !== 206) throw new Error('range status ' + r.status);
  return new Uint8Array(await r.arrayBuffer());
}
async function fetchAll(name) { return new Uint8Array(await (await fetch(url(name))).arrayBuffer()); }
let ctx, tap, lastTs = null, cur = null;
const ctxAt = (P) => lastTs.contextTime + (P - lastTs.performanceTime) / 1000;
const perfOf = (ctxSec, ts) => ts.performanceTime + (ctxSec - ts.contextTime) * 1000;

// ---------------------------------------------------------------- sidecars
function parseVideoCsv(txt) {
  const rows = txt.split('\n').filter((l) => l && l[0] >= '0' && l[0] <= '9');
  const n = rows.length, t = new Float64Array(n), off = new Float64Array(n), size = new Uint32Array(n);
  rows.forEach((l, i) => { const p = l.split(','); t[i] = +p[2] / 1e9; off[i] = +p[3]; size[i] = +p[4]; });
  return { t, off, size, n };
}
function parseAudioCsv(txt) {  // header/footer only, plus the first data row (the player needs nothing else)
  const hdr = {}; let fit = null, first = null;
  for (const l of txt.split('\n')) {
    if (l.startsWith('# fit ')) { fit = {}; for (const kv of l.slice(6).split(' ')) { const [k, v] = kv.split('='); fit[k] = +v; } }
    else if (l[0] === '#') { const m = /^# (\w+)=(.*)$/.exec(l); if (m) hdr[m[1]] = m[2]; }
    else if (!first && l && l[0] >= '0' && l[0] <= '9') { const p = l.split(','); first = { first_sample: +p[1], adc_ns: +p[4] }; }
  }
  return { hdr, fit, first, off: +(hdr.file_sample_offset || 0) };
}
function makeMap(a, mode) {
  if (mode === 'fit') {
    const f = a.fit;
    return { toHost: (n) => (f.t0_ns + (n - a.off - f.n0) * 1e9 / f.rate_hz) / 1e9, toSample: (t) => f.n0 + a.off + (t * 1e9 - f.t0_ns) * f.rate_hz / 1e9 };
  }
  const r = a.first;
  return { toHost: (n) => (r.adc_ns + (n - a.off - r.first_sample) * 1e9 / SR) / 1e9, toSample: (t) => r.first_sample + a.off + (t * 1e9 - r.adc_ns) * SR / 1e9 };
}

// ---------------------------------------------------------------- video
const stampCanvas = new OffscreenCanvas(320, 240), stampCtx = stampCanvas.getContext('2d', { willReadFrequently: true });
function readStamp(img) {
  stampCtx.drawImage(img, 0, 0, 320, 240);
  const row = stampCtx.getImageData(0, 8, 320, 1).data;
  let id = 0; for (let b = 0; b < 20; b++) if (row[(16 * b + 8) * 4] > 128) id |= 1 << b;
  return { id, flash: stampCtx.getImageData(160, 140, 1, 1).data[0] > 200 };
}
class Cam {
  constructor(name, sc, g, x, probe) { Object.assign(this, { name, sc, g, x, probe }); this.shown = -1; this.cache = new Map(); this.pending = new Map();
    this.stats = { drawn: 0, missedTicks: 0, mismatches: 0, decodeMs: 0, decodes: 0 }; }
  prev(t) { const T = this.sc.t; let lo = 0, hi = T.length - 1; if (t < T[0]) return -1; while (lo < hi) { const m = (lo + hi + 1) >> 1; if (T[m] <= t) lo = m; else hi = m - 1; } return lo; }
  decode(i) {
    if (this.cache.has(i)) return Promise.resolve();
    if (this.pending.has(i)) return this.pending.get(i);
    const p = (async () => {
      const t0 = performance.now();
      const b = await fetchRange(this.name + '.mkv', this.sc.off[i], this.sc.off[i] + this.sc.size[i]);
      const d = new ImageDecoder({ data: b, type: 'image/jpeg' }); const { image } = await d.decode(); d.close();
      const info = this.probe ? readStamp(image) : null;
      this.stats.decodeMs += performance.now() - t0; this.stats.decodes++;
      this.pending.delete(i); this.cache.set(i, { image, info });
    })();
    this.pending.set(i, p); return p;
  }
  evict() { for (const [k, e] of this.cache) if (k < this.shown || k > this.shown + 8) { e.image.close(); this.cache.delete(k); } }
  update(t, P) {
    const i = this.prev(t); if (i < 0) return;
    for (let k = i + 1; k <= Math.min(i + 4, this.sc.n - 1); k++) this.decode(k);
    if (i === this.shown) return;
    const e = this.cache.get(i);
    if (!e) { this.decode(i); this.stats.missedTicks++; return; }
    this.g.drawImage(e.image, this.x, 0, 320, 240);
    this.shown = i; this.stats.drawn++;
    if (this.probe) { if (e.info.id !== i) this.stats.mismatches++; if (cur && cur.draws) cur.draws.push([i, e.info.id, e.info.flash ? 1 : 0, +P.toFixed(3)]); }
    this.evict();
  }
}

// ---------------------------------------------------------------- audio engines
function alignedWhen(lead) { return Math.ceil((ctx.currentTime + lead) * SR) / SR; }
class BufEngine {
  async load(name) { const b = await fetchAll(name); this.bytes = b.length; const t0 = performance.now(); this.buf = await ctx.decodeAudioData(b.buffer); this.decodeMs = performance.now() - t0; this.length = this.buf.length; }
  async prepare(n) { this.stop(); this.n0 = n; }
  play() { this.when = alignedWhen(0.1); const s = ctx.createBufferSource(); s.buffer = this.buf; s.connect(tap); s.start(this.when, this.n0 / SR); this.src = s; }
  stop() { if (this.src) { try { this.src.stop(); } catch (e) {} this.src.disconnect(); this.src = null; } }
  async pcm(n, len) { return this.buf.getChannelData(0).slice(n, n + len); }
}
class WcEngine {
  async load(name) {
    this.name = name; this.decodeMs = 0; this.chunks = 0; this.gen = 0; this.srcs = [];
    if (name.endsWith('.wav')) {
      const h = await fetchRange(name, 0, 4096); const dv = new DataView(h.buffer); let p = 12;
      while (p + 8 <= h.length) { const id = String.fromCharCode(...h.subarray(p, p + 4)), sz = dv.getUint32(p + 4, true); if (id === 'data') { this.dataOff = p + 8; break; } p += 8 + sz + (sz & 1); }
      this.kind = 'wav'; this.bytes = 4096;
    } else {
      const b = await fetchAll(name); this.bytes = b.length;
      if (name.endsWith('.flac')) this.indexFlac(b); else this.indexMp4(b);
    }
  }
  indexFlac(b) {  // fixed-blocksize frames: sync 0xFFF8, header CRC-8 checked; description = fLaC + metadata blocks
    let p = 4, last = false; while (!last) { last = (b[p] & 0x80) !== 0; p += 4 + ((b[p + 1] << 16) | (b[p + 2] << 8) | b[p + 3]); }
    this.desc = b.slice(0, p); this.kind = 'flac';
    const crc8 = (s, e) => { let c = 0; for (let i = s; i < e; i++) { c ^= b[i]; for (let k = 0; k < 8; k++) c = (c & 0x80) ? ((c << 1) ^ 0x07) & 0xff : (c << 1) & 0xff; } return c; };
    const offs = [], firsts = [];
    for (let i = p; i + 6 < b.length; i++) {
      if (b[i] !== 0xff || b[i + 1] !== 0xf8) continue;
      const bsc = b[i + 2] >> 4, src = b[i + 2] & 15; let q = i + 4, v = b[q], extra = 0;
      if (v < 0x80) extra = 0; else if (v >= 0xc0 && v < 0xe0) { extra = 1; v &= 0x1f; } else if (v >= 0xe0 && v < 0xf0) { extra = 2; v &= 0x0f; } else if (v >= 0xf0 && v < 0xf8) { extra = 3; v &= 0x07; } else continue;
      for (let k = 1; k <= extra; k++) v = v * 64 + (b[q + k] & 0x3f); q += 1 + extra;
      if (bsc === 6) q += 1; else if (bsc === 7) q += 2; if (src === 12) q += 1; else if (src === 13 || src === 14) q += 2;
      if (q >= b.length || crc8(i, q) !== b[q]) continue;
      if (offs.length && v !== firsts.length) continue;  // frame numbers must run 0,1,2,...
      offs.push(i); firsts.push(v * 1024); i = q;
    }
    offs.push(b.length);
    this.off = Float64Array.from(offs); this.first = Float64Array.from(firsts); this.frames = firsts.length;
  }
  indexMp4(b) {  // fragmented MP4: tfdt + trun per moof (default-base-is-moof); description = OpusHead built from dOps
    const dv = new DataView(b.buffer, b.byteOffset); const u32 = (o) => dv.getUint32(o), typ = (o) => String.fromCharCode(b[o + 4], b[o + 5], b[o + 6], b[o + 7]);
    const s = [], off = [], size = []; let p = 0;
    const child = (o, end, want) => { while (o < end) { if (typ(o) === want) return o; o += u32(o); } return -1; };
    while (p + 8 <= b.length) {
      const sz = u32(p), t = typ(p); if (sz < 8 || p + sz > b.length) break;
      if (t === 'moov') { const i = b.subarray(p, p + sz).findIndex((x, k, a) => a[k] === 0x64 && a[k + 1] === 0x4f && a[k + 2] === 0x70 && a[k + 3] === 0x73); const d = p + i + 4;
        this.ch = b[d + 1]; this.preskip = dv.getUint16(d + 2); const head = new Uint8Array(19); head.set([79, 112, 117, 115, 72, 101, 97, 100, 1, this.ch]);
        const hv = new DataView(head.buffer); hv.setUint16(10, this.preskip, true); hv.setUint32(12, dv.getUint32(d + 4), true); hv.setInt16(16, dv.getInt16(d + 8), true); head[18] = b[d + 10];
        this.desc = head; }
      if (t === 'moof') {
        const traf = child(p + 8, p + sz, 'traf'), tfhd = child(traf + 8, traf + u32(traf), 'tfhd'), tfdt = child(traf + 8, traf + u32(traf), 'tfdt'), trun = child(traf + 8, traf + u32(traf), 'trun');
        const hf = u32(tfhd + 8) & 0xffffff; let q = tfhd + 16; if (hf & 1) q += 8; if (hf & 2) q += 4; let dDur = 0, dSize = 0; if (hf & 8) { dDur = u32(q); q += 4; } if (hf & 0x10) { dSize = u32(q); q += 4; }
        let base = b[tfdt + 8] === 1 ? Number(dv.getBigUint64(tfdt + 12)) : u32(tfdt + 12);
        const rf = u32(trun + 8) & 0xffffff, cnt = u32(trun + 12); let r = trun + 16, dataOff = 0; if (rf & 1) { dataOff = dv.getInt32(r); r += 4; } if (rf & 4) r += 4;
        let pos = p + dataOff;
        for (let k = 0; k < cnt; k++) { let dur = dDur, sz2 = dSize; if (rf & 0x100) { dur = u32(r); r += 4; } if (rf & 0x200) { sz2 = u32(r); r += 4; } if (rf & 0x400) r += 4; if (rf & 0x800) r += 4;
          s.push(base); off.push(pos); size.push(sz2); base += dur; pos += sz2; }
      }
      p += sz;
    }
    this.kind = 'opus'; this.s = Float64Array.from(s); this.off = Float64Array.from(off); this.size = Uint32Array.from(size); this.frames = s.length;
  }
  async decodeChunks(list, n, len) {  // list: [{ts (samples), data}] -> Float32Array[len] placed by output timestamp
    const out = new Float32Array(len);
    const dec = new AudioDecoder({ output: (ad) => { const k = ad.numberOfFrames, tmp = new Float32Array(k); ad.copyTo(tmp, { planeIndex: 0, format: 'f32-planar' });
      const g0 = Math.round(ad.timestamp * SR / 1e6) - n; for (let i = 0; i < k; i++) { const g = g0 + i; if (g >= 0 && g < len) out[g] = tmp[i]; } ad.close(); }, error: (e) => { this.err = String(e); } });
    dec.configure(this.kind === 'flac' ? { codec: 'flac', sampleRate: SR, numberOfChannels: 1, description: this.desc } : { codec: 'opus', sampleRate: SR, numberOfChannels: this.ch, description: this.desc });
    for (const c of list) dec.decode(new EncodedAudioChunk({ type: 'key', timestamp: Math.round(c.ts * 1e6 / SR), data: c.data }));
    await dec.flush(); dec.close(); return out;
  }
  async pcm(n, len) {
    const t0 = performance.now(); let out;
    if (this.kind === 'wav') {
      const b = await fetchRange(this.name, this.dataOff + 2 * n, this.dataOff + 2 * (n + len)); const i16 = new Int16Array(b.buffer, 0, b.length >> 1);
      out = new Float32Array(len); for (let i = 0; i < i16.length; i++) out[i] = i16[i] / 32768;
    } else if (this.kind === 'flac') {
      let f0 = Math.max(0, Math.floor(n / 1024)); let f1 = Math.min(this.frames - 1, Math.floor((n + len - 1) / 1024));
      const b = await fetchRange(this.name, this.off[f0], this.off[f1 + 1]); const list = [];
      for (let f = f0; f <= f1; f++) list.push({ ts: this.first[f], data: b.subarray(this.off[f] - this.off[f0], this.off[f + 1] - this.off[f0]) });
      out = await this.decodeChunks(list, n, len);
    } else {
      // packet start s is on the untrimmed timeline (priming included); the decoder trims pre-skip itself and its output
      // timestamps are on the trimmed timeline (prior evidence audio_skellycam §4.4; checked again by the content check)
      const want = n + this.preskip; let k0 = 0, lo = 0, hi = this.frames - 1;
      while (lo <= hi) { const m = (lo + hi) >> 1; if (this.s[m] <= want - OPUS_PREROLL) { k0 = m; lo = m + 1; } else hi = m - 1; }
      let k1 = k0; while (k1 + 1 < this.frames && this.s[k1 + 1] < want + len) k1++;
      const b = await fetchRange(this.name, this.off[k0], this.off[k1] + this.size[k1]); const list = [];
      for (let k = k0; k <= k1; k++) list.push({ ts: this.s[k], data: b.subarray(this.off[k] - this.off[k0], this.off[k] - this.off[k0] + this.size[k]) });
      out = await this.decodeChunks(list, n, len);
    }
    this.decodeMs += performance.now() - t0; this.chunks++; return out;
  }
  async prepare(n) { this.stop(); this.gen++; this.n0 = n; this.first0 = await this.pcm(n, CHUNK); }
  sched(pcm, at) { const ab = ctx.createBuffer(1, pcm.length, SR); ab.copyToChannel(pcm, 0); const s = ctx.createBufferSource(); s.buffer = ab; s.connect(tap); s.start(at); s.onended = () => { s.disconnect(); this.srcs = this.srcs.filter((x) => x !== s); }; this.srcs.push(s); }
  play() {
    this.when = alignedWhen(0.1); this.sched(this.first0, this.when); let next = this.n0 + CHUNK; const gen = this.gen;
    (async () => { while (gen === this.gen) {
      const at = this.when + (next - this.n0) / SR; if (at - ctx.currentTime > AHEAD_S) { await sleep(100); continue; }
      const pcm = await this.pcm(next, CHUNK); if (gen !== this.gen) return; if (at < ctx.currentTime) this.late = (this.late || 0) + 1;
      this.sched(pcm, at); next += CHUNK; } })();
  }
  stop() { this.gen++; for (const s of this.srcs) { s.onended = null; try { s.stop(); } catch (e) {} s.disconnect(); } this.srcs = []; }
}
class ElEngine {
  async load(name) {
    this.el = new Audio(); this.el.preload = 'auto';
    await new Promise((res, rej) => { this.el.onloadedmetadata = res; this.el.onerror = () => rej(new Error('media error ' + (this.el.error && this.el.error.code))); this.el.src = url(name); });
    this.duration = this.el.duration; this.node = ctx.createMediaElementSource(this.el); this.node.connect(tap);
  }
  async prepare(n) { this.el.pause(); const p = new Promise((q) => { this.el.onseeked = q; }); this.el.currentTime = n / SR; await p; }
  play() { this.el.play(); }
  stop() { this.el.pause(); }
}
const ENGINES = { buf: BufEngine, wc: WcEngine, el: ElEngine };

// ---------------------------------------------------------------- run
async function run(cfg) {
  if (cfg.elprobe) { window.__phase = 'probe'; const r = await elProbe(); window.__phase = 'done'; return { cfg, elprobe: r }; }
  const R = { cfg, segments: [], calib: [], outTs: [] };
  window.__phase = 'load';
  ctx = new AudioContext({ sampleRate: SR, latencyHint: 'interactive' });
  await ctx.audioWorklet.addModule(url('tap.js'));
  tap = new AudioWorkletNode(ctx, 'tap', { outputChannelCount: [1] });
  const mute = ctx.createGain(); mute.gain.value = 0; tap.connect(mute); mute.connect(ctx.destination);  // silent: nothing reaches the speakers
  tap.port.onmessage = (e) => { const ts = ctx.getOutputTimestamp(); if (cur && cur.clicks) cur.clicks.push([e.data[0], +perfOf(e.data[0] / SR, ts).toFixed(3), +e.data[1].toFixed(3)]); };
  await ctx.resume(); await sleep(300);
  R.ctx = { sampleRate: ctx.sampleRate, baseLatency: ctx.baseLatency, outputLatency: ctx.outputLatency };
  // detector calibration: a click scheduled at a known frame must be reported at exactly that frame
  for (let k = 0; k < 5; k++) {
    const ab = ctx.createBuffer(1, 4800, SR); ab.getChannelData(0)[1000] = 0.9; const s = ctx.createBufferSource(); s.buffer = ab; s.connect(tap);
    const when = alignedWhen(0.05); cur = { clicks: [] }; s.start(when); await sleep(250); R.calib.push(cur.clicks.length ? cur.clicks[0][0] - Math.round(when * SR) - 1000 : null);
  }
  cur = null;
  const g = document.getElementById('c').getContext('2d');
  const t0 = performance.now();
  const acsv = parseAudioCsv(await (await fetch(url(cfg.audio + '.csv'))).text());
  const map = makeMap(acsv, cfg.map);
  R.audioCsvMs = performance.now() - t0;
  const cams = [];
  for (const [k, name] of cfg.cams.entries()) cams.push(new Cam(name, parseVideoCsv(await (await fetch(url(name + '.csv'))).text()), g, 320 * k, k === 0));
  R.videoCsvMs = performance.now() - t0 - R.audioCsvMs;
  const engine = new ENGINES[cfg.engine]();
  const t1 = performance.now();
  try { await engine.load(cfg.audio); } catch (e) { R.loadError = String(e.message || e); window.__phase = 'done'; return R; }
  R.load = { ms: +(performance.now() - t1).toFixed(1), bytes: engine.bytes, decodeMs: engine.decodeMs, frames: engine.frames, length: engine.length, duration: engine.duration, preskip: engine.preskip };
  window.__phase = 'loaded'; await sleep(1500);
  // offline content check (buf/wc): where do the clicks land in the PCM the engine would schedule?
  if (cfg.engine !== 'el') {
    R.content = [];
    for (const t of cfg.content || []) { const n = Math.round(map.toSample(t)); const x = await engine.pcm(n, 2 * SR); const peaks = [];
      for (let i = 0; i < x.length; i++) if (Math.abs(x[i]) > 0.3) { let bi = i; for (let j = i; j < Math.min(x.length, i + 480); j++) if (Math.abs(x[j]) > Math.abs(x[bi])) bi = j; peaks.push(n + bi); i = bi + 4800; }
      R.content.push({ t, n, peaks }); }
  }
  const clockN = (P) => {
    if (cfg.engine === 'el') return (engine.el.currentTime - (cfg.clock === 'ellat' ? ctx.outputLatency : 0)) * SR;
    const c = cfg.clock === 'naive' ? ctx.currentTime : ctxAt(P);
    return c < engine.when ? engine.n0 : engine.n0 + (c - engine.when) * SR;
  };
  const showAt = async (t) => { for (const c of cams) { const i = c.prev(t); if (i >= 0) await c.decode(i); c.update(t, performance.now()); } };
  for (const op of cfg.plan) {
    if (op.op === 'scrub') {
      window.__phase = 'scrub'; engine.stop(); const seg = { op: 'scrub', lat: [] }; cur = null;
      for (const t of op.ts) { const s0 = performance.now(); await showAt(t); seg.lat.push(+(performance.now() - s0).toFixed(2)); await sleep(op.dt); }
      R.segments.push(seg); continue;
    }
    window.__phase = 'seek';
    const nFile = Math.round(map.toSample(op.t));
    const s0 = performance.now(); await engine.prepare(nFile); const prepMs = performance.now() - s0;
    await showAt(op.t);
    const seg = { op: 'play', t: op.t, nFile, prepMs: +prepMs.toFixed(2), ticks: [], draws: [], clicks: [], ts: [] };
    cur = seg; window.__phase = 'play';
    lastTs = ctx.getOutputTimestamp();
    engine.play(); seg.playAt = performance.now(); if (engine.when) seg.whenPerf = +perfOf(engine.when, ctx.getOutputTimestamp()).toFixed(3);
    const tEnd = performance.now() + op.dur * 1000;
    await new Promise((res) => {
      const tick = (P) => {
        lastTs = ctx.getOutputTimestamp();
        const n = clockN(P), th = map.toHost(n);
        seg.ticks.push([+P.toFixed(3), +n.toFixed(1)]);
        if (seg.ticks.length % 30 === 1) seg.ts.push([+lastTs.performanceTime.toFixed(3), lastTs.contextTime, ctx.currentTime, ctx.outputLatency]);
        for (const c of cams) c.update(th, P);
        if (performance.now() < tEnd) requestAnimationFrame(tick); else res();
      };
      requestAnimationFrame(tick);
    });
    engine.stop(); await sleep(150); cur = null;
    R.segments.push(seg);
  }
  R.cams = cams.map((c) => ({ name: c.name, ...c.stats }));
  R.engine = { decodeMs: engine.decodeMs, chunks: engine.chunks, late: engine.late || 0, err: engine.err || null };
  window.__phase = 'done';
  return R;
}
