// Renderer side of the single-writer MCAP desk test. Loaded after ../mcap_electron/page.js, whose globals it reuses
// (rangeReadable, newStats, dist, rng, r3, now, runParallel, mc, crc32). Called by main_sw.cjs as runSW(cfg).
// Per file: McapIndexedReader.Initialize x3, renderer memory, a per-channel frame table, 100 random one-camera fetches.
const BASE_NS = 10n ** 18n, REC0 = 49;            // REC0: chunk header bytes before its records (compression "")
const frameNs = k => BASE_NS + BigInt(k) * 1000000000n / 30n;

async function memSnap() {
  gc(); await sleep(50); gc();
  const pm = process.memoryUsage(), pi = await process.getProcessMemoryInfo();
  return { rss: pm.rss, heapUsed: pm.heapUsed, external: pm.external, arrayBuffers: pm.arrayBuffers,
           jsHeapUsed: performance.memory.usedJSHeapSize, jsHeapLimit: performance.memory.jsHeapSizeLimit,
           privateKB: pi.private, residentSetKB: pi.residentSet };
}

function parseOne(b) {
  return mc.parseRecord(new mc.McapByteReader(new DataView(b.buffer, b.byteOffset, b.byteLength)), true);
}

// Table: channel id -> { off: file offset of the Message record, len, chunk: index into chunkIndexes }, in file order.
function addRow(table, ch, off, len, ci) {
  let t = table.get(ch); if (!t) table.set(ch, t = { off: [], len: [], chunk: [] });
  t.off.push(off); t.len.push(len); t.chunk.push(ci);
}

async function buildTable(reader, readable, st, oneMsgPerChunk) {
  const cis = reader.chunkIndexes, table = new Map(), s0 = { ...st }, t0 = now();
  if (oneMsgPerChunk) {                            // summary only: the chunk holds one message at records offset 0
    for (let i = 0; i < cis.length; i++) {
      const ci = cis[i], [ch] = ci.messageIndexOffsets.keys();
      addRow(table, ch, Number(ci.chunkStartOffset) + REC0, Number(ci.uncompressedSize), i);
    }
  } else {                                         // one MessageIndex read per chunk (all channels' indexes are contiguous)
    const per = new Array(cis.length);
    await runParallel(cis.map((_c, i) => i), 16, async i => {
      const ci = cis[i], b = await readable.read(ci.chunkStartOffset + ci.chunkLength, ci.messageIndexLength);
      const rd = new mc.McapByteReader(new DataView(b.buffer, b.byteOffset, b.byteLength)), rows = [];
      for (let r; (r = mc.parseRecord(rd, true));) for (const [, o] of r.records) rows.push([Number(o), r.channelId]);
      per[i] = rows;
    });
    for (let i = 0; i < cis.length; i++) {
      const rows = per[i].sort((x, y) => x[0] - y[0]), size = Number(cis[i].uncompressedSize), start = Number(cis[i].chunkStartOffset) + REC0;
      for (let j = 0; j < rows.length; j++) addRow(table, rows[j][1], start + rows[j][0], (j + 1 < rows.length ? rows[j + 1][0] : size) - rows[j][0], i);
      per[i] = null;
    }
  }
  const counts = {}; for (const [ch, t] of table) counts[ch] = t.off.length;
  return { table, info: { ms: r3(now() - t0), requests: st.req - s0.req, bytes: st.bytes - s0.bytes, rows_per_channel: counts } };
}

const check = (m, cam, k) => !!m && m.type === 'Message' && m.channelId === cam + 1 && m.sequence === k && m.logTime === frameNs(k);

async function randomFetch(reader, readable, st, table, topics, libSt) {
  const R = rng(11), picks = Array.from({ length: 100 }, () => { const cam = Math.floor(R() * 16); return [cam, Math.floor(R() * table.get(cam + 1).off.length)]; });
  const out = {};
  const run = async (name, fn, S = st) => {        // S: the stats of the readable that the method reads through
    const rows = [];
    for (const [cam, k] of picks) {
      const s0 = { ...S }, t0 = now(), ok = await fn(cam, k);
      rows.push({ ms: now() - t0, requests: S.req - s0.req, bytes: S.bytes - s0.bytes, ok });
    }
    out[name] = { correct: rows.filter(r => r.ok).length, of: rows.length, ms: dist(rows.map(r => r.ms)),
                  requests: dist(rows.map(r => r.requests)), bytes: dist(rows.map(r => r.bytes)) };
  };
  await run('table_exact_message_read', async (cam, k) => {
    const t = table.get(cam + 1);
    return check(parseOne(await readable.read(BigInt(t.off[k]), BigInt(t.len[k]))), cam, k);
  });
  await run('table_whole_chunk_read', async (cam, k) => {
    const t = table.get(cam + 1), ci = reader.chunkIndexes[t.chunk[k]];
    const chunk = parseOne(await readable.read(ci.chunkStartOffset, ci.chunkLength));
    if (crc32(chunk.records) !== chunk.uncompressedCrc) return false;
    const o = t.off[k] - Number(ci.chunkStartOffset) - REC0;
    return check(parseOne(chunk.records.subarray(o, o + t.len[k])), cam, k);
  });
  await run('library_readMessages_topic_time', async (cam, k) => {
    const got = [];
    for await (const m of reader.readMessages({ topics: [topics[cam]], startingAt: frameNs(k), endingAt: frameNs(k) })) got.push(m);
    return got.length === 1 && check(got[0], cam, k);
  }, libSt);
  return out;
}

async function runSW(cfg) {
  mc = require(path.join(cfg.nm, '@mcap', 'core'));
  crc32 = require(path.join(cfg.nm, '@foxglove', 'crc')).crc32;
  const res = { files: {} };
  for (const name of cfg.files) {
    const r = res.files[name] = { mem_start: await memSnap(), init: [] };
    let reader, libSt;
    for (let rep = 0; rep < 3; rep++) {
      reader = null; const st = libSt = newStats(), t0 = now();
      reader = await mc.McapIndexedReader.Initialize({ readable: rangeReadable(name, st) });
      r.init.push({ ms: r3(now() - t0), requests: st.req, bytes: st.bytes, chunk_indexes: reader.chunkIndexes.length,
                    message_count: Number(reader.statistics.messageCount), summary_bytes: Number((await rangeReadable(name, newStats()).size()) - reader.footer.summaryStart) });
    }
    r.mem_after_init = await memSnap();
    const st = newStats(), readable = rangeReadable(name, st);
    const oneMsg = reader.chunkIndexes.every(ci => ci.messageIndexOffsets.size === 1) && Number(reader.statistics.messageCount) === reader.chunkIndexes.length;
    const { table, info } = await buildTable(reader, readable, st, oneMsg);
    r.table = { one_message_per_chunk: oneMsg, ...info };
    r.mem_after_table = await memSnap();
    const topics = Array.from({ length: 16 }, (_x, c) => `/cam${String(c).padStart(2, '0')}/image`);
    r.fetch = await randomFetch(reader, readable, st, table, topics, libSt);
    console.log(name, JSON.stringify({ init: r.init, table: r.table.ms, fetch: Object.fromEntries(Object.entries(r.fetch).map(([k, v]) => [k, v.correct])) }));
  }
  return res;
}
