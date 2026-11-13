// Renderer side of the MCAP-in-Electron desk test. Called by main.cjs as runAll(cfg).
// Tests (cfg.tests, or 'all'): init, seek, seq, realtime, table, trunc, audio.
const path = require('path'), fs = require('fs');
const BASE = 'skr://media/';
const now = () => performance.now();
const sleep = ms => new Promise(r => setTimeout(r, ms));
const r3 = x => Math.round(x * 1000) / 1000;
function pct(a, p) { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.min(s.length - 1, Math.floor(p / 100 * s.length))] : null; }
function dist(a) { return { n: a.length, p50: r3(pct(a, 50)), p99: r3(pct(a, 99)), max: r3(Math.max(...a)), mean: r3(a.reduce((x, y) => x + y, 0) / a.length) }; }
function rng(seed) { return () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

// IReadable over Range fetches. stats counts requests and bytes.
function rangeReadable(name, stats) {
  const url = BASE + name; let size;
  return {
    async size() {
      if (size === undefined) { stats.req++; const r = await fetch(url, { method: 'HEAD', cache: 'no-store' }); size = BigInt(r.headers.get('content-length')); }
      return size;
    },
    async read(off, len) {
      const o = Number(off), n = Number(len);
      if (n === 0) return new Uint8Array(0);
      stats.req++; stats.bytes += n;
      const r = await fetch(url, { headers: { Range: `bytes=${o}-${o + n - 1}` }, cache: 'no-store' });
      if (r.status !== 206) throw new Error(`HTTP ${r.status} for ${o}+${n}`);
      const b = new Uint8Array(await r.arrayBuffer());
      if (b.length !== n) throw new Error(`short read ${b.length} of ${n} at ${o}`);
      return b;
    },
  };
}
const newStats = () => ({ req: 0, bytes: 0 });

// Minimal protobuf reader: field number -> last value (varint as Number, length-delimited as Uint8Array).
function pb(b) {
  const out = {}; let i = 0;
  const varint = () => { let v = 0, s = 0, x; do { x = b[i++]; v += (x & 0x7f) * 2 ** s; s += 7; } while (x & 0x80); return v; };
  while (i < b.length) {
    const key = varint(), f = Math.floor(key / 8), wt = key & 7;
    if (wt === 0) out[f] = varint();
    else if (wt === 2) { const n = varint(); out[f] = b.subarray(i, i + n); i += n; }
    else if (wt === 1) i += 8; else if (wt === 5) i += 4; else throw new Error('wire type ' + wt);
  }
  return out;
}

let mc, crc32, media, canvas, ctx;
const td = new TextDecoder();

// Decode a JPEG with ImageDecoder and read the 16-bit index code from the top strip.
async function pixelIndex(jpeg) {
  const t0 = now();
  const dec = new ImageDecoder({ data: jpeg, type: 'image/jpeg' });
  const { image } = await dec.decode();
  const tDec = now() - t0;
  const { block_w: bw, height: ch, bits } = media.camera.code;
  ctx.drawImage(image, 0, 0, bw * bits, ch, 0, 0, bw * bits, ch);
  const px = ctx.getImageData(0, 0, bw * bits, ch).data;
  let v = 0;
  for (let b = 0; b < bits; b++) if (px[((ch >> 1) * bw * bits + b * bw + (bw >> 1)) * 4] > 128) v |= 1 << b;
  const wh = [image.displayWidth, image.displayHeight, image.format];
  image.close(); dec.close();
  return { index: v, decode_ms: tDec, total_ms: now() - t0, wh };
}

// Check one camera Message record against frame i. decode=false skips ImageDecoder.
async function verifyFrame(msg, i, decode) {
  const f = pb(msg.data), jpeg = f[2];
  const r = { seq_ok: msg.sequence === i, time_ok: msg.logTime === BigInt(media.camera.frame_ns[i]),
              crc_ok: crc32(jpeg) === media.camera.crc32[i], format: td.decode(f[3]) };
  if (decode) { const p = await pixelIndex(jpeg); r.pixel_ok = p.index === i; r.decode_ms = p.decode_ms; r.wh = p.wh; }
  r.ok = r.seq_ok && r.time_ok && r.crc_ok && r.format === 'jpeg' && (!decode || r.pixel_ok);
  return r;
}

const CHUNK_HDR = c => 1 + 8 + 8 + 8 + 8 + 4 + 4 + c.length + 8;   // opcode, len, start, end, usize, crc, compression str, records len

// Read one chunk by its ChunkIndex (one request) and return its Message records.
async function readChunkMessages(readable, ci) {
  const b = await readable.read(ci.chunkStartOffset, ci.chunkLength);
  const chunk = mc.parseRecord(new mc.McapByteReader(new DataView(b.buffer, b.byteOffset, b.byteLength)), true);
  if (chunk.type !== 'Chunk' || chunk.compression !== '') throw new Error('not an uncompressed chunk');
  if (chunk.uncompressedCrc !== 0 && crc32(chunk.records) !== chunk.uncompressedCrc) throw new Error('chunk crc');
  const rd = new mc.McapByteReader(new DataView(chunk.records.buffer, chunk.records.byteOffset, chunk.records.byteLength));
  const out = [];
  for (let r; (r = mc.parseRecord(rd, true));) if (r.type === 'Message') out.push(r);
  return out;
}

async function streamScan(name, blockBytes) {
  const st = newStats(), rd = rangeReadable(name, st), size = Number(await rd.size());
  const sr = new mc.McapStreamReader();
  const t0 = now(); let msgs = 0, crcOk = 0, seqDense = true, lastSeq = -1, counts = {}, error = null;
  try {
    for (let o = 0; o < size; o += blockBytes) {
      sr.append(await rd.read(BigInt(o), BigInt(Math.min(blockBytes, size - o))));
      for (let r; (r = sr.nextRecord());) {
        counts[r.type] = (counts[r.type] || 0) + 1;
        if (r.type === 'Message') {
          msgs++; if (r.sequence !== lastSeq + 1) seqDense = false; lastSeq = r.sequence;
          if (media.camera.crc32[r.sequence] === crc32(pb(r.data)[2])) crcOk++;
        }
      }
    }
  } catch (e) { error = String(e.message || e); }
  return { ms: r3(now() - t0), file_size: size, block_bytes: blockBytes, requests: st.req, bytes: st.bytes, messages: msgs,
           crc_ok: crcOk, seq_dense: seqDense, last_seq: lastSeq, record_counts: counts, done: sr.done(),
           bytes_remaining: sr.bytesRemaining(), error };
}

async function runParallel(items, conc, fn) {
  let k = 0; await Promise.all(Array.from({ length: conc }, async () => { while (k < items.length) { const j = k++; await fn(items[j], j); } }));
}

async function testInit(out) {
  out.init = [];
  for (let rep = 0; rep < 5; rep++) {
    const st = newStats(), t0 = now();
    const r = await mc.McapIndexedReader.Initialize({ readable: rangeReadable('cam0.mcap', st) });
    out.init.push({ ms: r3(now() - t0), requests: st.req, bytes: st.bytes, chunk_indexes: r.chunkIndexes.length,
                    message_count: Number(r.statistics.messageCount), summary_bytes: Number(BigInt(media.camera.file_size) - r.footer.summaryStart) });
  }
}

async function testSeek(out, reader, readable, st, table) {
  const R = rng(7), idx = Array.from({ length: 100 }, () => Math.floor(R() * media.camera.frames));
  const lib = [], tab = [];
  for (const i of idx) {
    let s0 = { ...st }, t0 = now(), got = [];
    const t = BigInt(media.camera.frame_ns[i]);
    for await (const m of reader.readMessages({ startingAt: t, endingAt: t })) got.push(m);
    const fetchMs = now() - t0;
    const v = got.length === 1 ? await verifyFrame(got[0], i, true) : { ok: false, n: got.length };
    lib.push({ i, fetch_ms: r3(fetchMs), total_ms: r3(now() - t0), requests: st.req - s0.req, bytes: st.bytes - s0.bytes, ...v });
    s0 = { ...st }; t0 = now();
    const ms = await readChunkMessages(readable, table[i]);
    const fetchMs2 = now() - t0;
    const v2 = ms.length === 1 ? await verifyFrame(ms[0], i, true) : { ok: false, n: ms.length };
    tab.push({ i, fetch_ms: r3(fetchMs2), total_ms: r3(now() - t0), requests: st.req - s0.req, bytes: st.bytes - s0.bytes, ...v2 });
  }
  const sum = a => ({ correct: a.filter(x => x.ok).length, of: a.length, fetch_ms: dist(a.map(x => x.fetch_ms)), decode_ms: dist(a.map(x => x.decode_ms || 0)),
                      total_ms: dist(a.map(x => x.total_ms)), requests: dist(a.map(x => x.requests)), bytes: dist(a.map(x => x.bytes)), first_bad: a.find(x => !x.ok) || null });
  out.seek = { indices: idx, library_readMessages: sum(lib), by_table_one_chunk_read: sum(tab), decoded_frame: lib[0].wh };
}

async function testSeq(out, reader, readable, st, table) {
  out.seq = [];
  for (let rep = 0; rep < 3; rep++) for (const mode of ['library_fetch_only', 'library_decode', 'table_fetch_only', 'table_decode']) {
    const decode = mode.endsWith('decode'), s0 = { ...st }, per = [], dec = []; let bad = 0, n = 0;
    const t0 = now(); let last = t0;
    const step = async (m) => { const v = await verifyFrame(m, n, decode); if (!v.ok) bad++; if (decode) dec.push(v.decode_ms); n++; const t = now(); per.push(t - last); last = t; };
    if (mode.startsWith('library')) { for await (const m of reader.readMessages()) await step(m); }
    else for (let i = 0; i < table.length; i++) for (const m of await readChunkMessages(readable, table[i])) await step(m);
    const s = (now() - t0) / 1000;
    out.seq.push({ rep, mode, frames: n, bad, s: r3(s), fps: r3(n / s), MB_per_s: r3((st.bytes - s0.bytes) / s / 1e6), requests: st.req - s0.req,
                   bytes: st.bytes - s0.bytes, per_frame_ms: dist(per), decode_ms: decode ? dist(dec) : null });
  }
}

async function testRealtime(out, reader) {
  const period = 1000 / media.camera.fps, late = [], service = []; let bad = 0, missed = 0, i = 0;
  const it = reader.readMessages(); const t0 = now();
  for (;;) {
    const due = t0 + i * period, w = due - now();
    if (w > 0) await sleep(w);
    const ts = now();
    const { value: m, done } = await it.next(); if (done) break;
    const v = await verifyFrame(m, i, true); if (!v.ok) bad++;
    const te = now(); service.push(te - ts); late.push(te - due); if (te > due + period) missed++;
    i++;
  }
  out.realtime = { frames: i, bad, wall_s: r3((now() - t0) / 1000), done_after_due_ms: dist(late), fetch_plus_decode_ms: dist(service), missed_next_due: missed };
}

async function testTable(out, reader, readable, st) {
  const T = { };
  // (a) summary only: frame n = n-th chunk by messageStartTime (valid here because each chunk holds one frame and none are missing)
  let t0 = now();
  for (let k = 0; k < 100; k++) [...reader.chunkIndexes].sort((a, b) => (a.messageStartTime < b.messageStartTime ? -1 : a.messageStartTime > b.messageStartTime ? 1 : 0));
  T.summary_sort_ms_per_build = r3((now() - t0) / 100);
  const table = [...reader.chunkIndexes].sort((a, b) => (a.messageStartTime < b.messageStartTime ? -1 : 1));
  T.single_message_chunks = table.every(c => c.messageStartTime === c.messageEndTime);
  T.chunk_times_match_frame_times = table.every((c, n) => c.messageStartTime === BigInt(media.camera.frame_ns[n]));
  T.chunk_index_fields = Object.keys(table[0]);
  // (b) all message indexes, concurrency 1 and 16
  for (const conc of [1, 16]) {
    const s0 = { ...st }, offsets = new Array(table.length); t0 = now();
    await runParallel(table, conc, async (ci, n) => {
      const start = [...ci.messageIndexOffsets.values()].reduce((a, b) => (a < b ? a : b));
      const b = await readable.read(start, ci.messageIndexLength);
      const rd = new mc.McapByteReader(new DataView(b.buffer, b.byteOffset, b.byteLength));
      const mi = mc.parseRecord(rd, true);
      offsets[n] = mi.records.map(([t, o]) => Number(o));
    });
    T[`message_indexes_c${conc}`] = { ms: r3(now() - t0), requests: st.req - s0.req, bytes: st.bytes - s0.bytes,
      offsets_first3: offsets.slice(0, 3), all_later_offsets_zero: offsets.slice(1).every(o => o.length === 1 && o[0] === 0) };
    T.msg_offsets = offsets;
  }
  // (c) read each Message header (31 B: opcode, length, channel, sequence, log_time, publish_time) to get the real sequence
  for (const conc of [1, 16]) {
    const s0 = { ...st }, seq = new Array(table.length); t0 = now();
    await runParallel(table, conc, async (ci, n) => {
      const at = ci.chunkStartOffset + BigInt(CHUNK_HDR(ci.compression) + T.msg_offsets[n][0]);
      const b = await readable.read(at, 31n), dv = new DataView(b.buffer, b.byteOffset, 31);
      seq[n] = b[0] === 5 && dv.getBigUint64(15, true) === ci.messageStartTime ? dv.getUint32(11, true) : -1;
    });
    T[`message_headers_c${conc}`] = { ms: r3(now() - t0), requests: st.req - s0.req, bytes: st.bytes - s0.bytes, seq_equals_ordinal: seq.every((s, n) => s === n) };
  }
  delete T.msg_offsets;
  // (d) one streaming pass over the whole file
  T.stream_scan_8MiB = await streamScan('cam0.mcap', 8 << 20);
  out.table = T;
  return table;
}

async function testTrunc(out) {
  const st = newStats(); let init;
  const t0 = now();
  try { const r = await mc.McapIndexedReader.Initialize({ readable: rangeReadable('cam0_cut60.mcap', st) }); init = { ok: true, chunks: r.chunkIndexes.length }; }
  catch (e) { init = { ok: false, error: String(e.message || e) }; }
  init.ms = r3(now() - t0); init.requests = st.req; init.bytes = st.bytes;
  out.trunc = { expected: media.camera.cut60, indexed_initialize: init, stream_scan_8MiB: await streamScan('cam0_cut60.mcap', 8 << 20) };
}

// ---- audio ----
const b64 = a => Buffer.from(a.buffer, a.byteOffset, a.byteLength).toString('base64');
async function decodePackets(pkts, config) {
  const outs = []; let error = null;
  const dec = new AudioDecoder({ output: ad => {
    const pcm = new Float32Array(ad.numberOfFrames * ad.numberOfChannels);
    ad.copyTo(pcm, { planeIndex: 0, format: 'f32-planar' });
    outs.push({ ts: ad.timestamp, n: ad.numberOfFrames, sr: ad.sampleRate, ch: ad.numberOfChannels, fmt: ad.format, dur: ad.duration, pcm });
    ad.close();
  }, error: e => { error = String(e.message || e); } });
  dec.configure(config);
  for (const p of pkts) dec.decode(new EncodedAudioChunk({ type: 'key', timestamp: p.ts, data: p.data }));
  try { await dec.flush(); } catch (e) { error = error || String(e.message || e); }
  if (dec.state !== 'closed') dec.close();
  return { outs, error };
}

async function testAudio(out) {
  const st = newStats(), t0 = now();
  const reader = await mc.McapIndexedReader.Initialize({ readable: rangeReadable('mic.mcap', st) });
  const A = { init: { ms: r3(now() - t0), requests: st.req, bytes: st.bytes, chunks: reader.chunkIndexes.length } };
  const ch = [...reader.channelsById.values()][0];
  A.channel = { topic: ch.topic, metadata: Object.fromEntries(ch.metadata) };
  const head = Uint8Array.from(Buffer.from(A.channel.metadata.opus_head, 'base64'));
  const pkts = []; const t1 = now();
  for await (const m of reader.readMessages()) { const f = pb(m.data); pkts.push({ ts: Number(m.logTime / 1000n), seq: m.sequence, data: f[2], fmt: td.decode(f[3]) }); }
  A.read_all = { ms: r3(now() - t1), requests: st.req - A.init.requests, packets: pkts.length, formats: [...new Set(pkts.map(p => p.fmt))] };
  const sr = Number(A.channel.metadata.sample_rate);
  const configs = { none: { codec: 'opus', sampleRate: sr, numberOfChannels: 1 }, head: { codec: 'opus', sampleRate: sr, numberOfChannels: 1, description: head } };
  A.full = {};
  for (const [k, c] of Object.entries(configs)) {
    A.full[k] = { supported: (await AudioDecoder.isConfigSupported(c)).supported };
    const t2 = now(); const { outs, error } = await decodePackets(pkts, c);
    const total = outs.reduce((a, o) => a + o.n, 0), pcm = new Float32Array(total); let o = 0;
    for (const x of outs) { pcm.set(x.pcm, o); o += x.n; }
    fs.writeFileSync(path.join(cfgMedia, `dec_${k}.f32`), Buffer.from(pcm.buffer));
    Object.assign(A.full[k], { ms: r3(now() - t2), error, outputs: outs.length, total_frames: total, encoded_frames: pkts.length * 960,
      first: outs.slice(0, 3).map(({ pcm, ...r }) => r), last: outs.slice(-2).map(({ pcm, ...r }) => r),
      frame_counts: [...new Set(outs.map(x => x.n))], ts_list: outs.map(x => x.ts) });
  }
  // seeks: decode from packet K with P packets of pre-roll (fresh decoder each time); outputs kept for analysis
  const R = rng(11), Ks = Array.from({ length: 20 }, () => 100 + Math.floor(R() * (pkts.length - 200)));
  const trials = [];
  for (const K of Ks) for (const [k, c] of Object.entries(configs)) for (const P of [0, 4]) {
    const { outs, error } = await decodePackets(pkts.slice(K - P, K + 6), c);
    trials.push({ K, config: k, preroll: P, target_ts: pkts[K].ts, error, outs: outs.map(o => ({ ts: o.ts, n: o.n, pcm: b64(o.pcm) })) });
  }
  fs.writeFileSync(path.join(cfgMedia, 'seek_trials.json'), JSON.stringify({ first_ts: pkts[0].ts, trials }));
  A.seek_trials = { n: trials.length, targets: Ks, errors: trials.filter(t => t.error).length };
  out.audio = A;
}

let cfgMedia;
async function runAll(cfg) {
  mc = require(path.join(cfg.nm, '@mcap', 'core'));
  crc32 = require(path.join(cfg.nm, '@foxglove', 'crc')).crc32;
  cfgMedia = cfg.media;
  media = JSON.parse(fs.readFileSync(path.join(cfg.media, 'media.json'), 'utf8'));
  canvas = new OffscreenCanvas(media.camera.code.block_w * media.camera.code.bits, media.camera.code.height);
  ctx = canvas.getContext('2d', { willReadFrequently: true });
  const want = t => cfg.tests.includes('all') || cfg.tests.includes(t);
  const out = { tests: cfg.tests, timings: {} };
  const step = async (name, fn) => { if (!want(name)) return; console.log('start ' + name); const t = now(); try { await fn(); } catch (e) { out[name + '_error'] = String(e.stack || e); } out.timings[name] = r3((now() - t) / 1000); };
  await step('init', () => testInit(out));
  const st = newStats(), readable = rangeReadable('cam0.mcap', st);
  const reader = await mc.McapIndexedReader.Initialize({ readable });
  let table;
  await step('table', async () => { table = await testTable(out, reader, readable, st); });
  if (!table) table = [...reader.chunkIndexes].sort((a, b) => (a.messageStartTime < b.messageStartTime ? -1 : 1));
  await step('seek', () => testSeek(out, reader, readable, st, table));
  await step('seq', () => testSeq(out, reader, readable, st, table));
  await step('realtime', () => testRealtime(out, reader));
  await step('trunc', () => testTrunc(out));
  await step('audio', () => testAudio(out));
  return out;
}
