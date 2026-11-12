// Run the locator with fs reads at offsets standing in for HTTP Range requests; count reads and bytes.
const fs = require('fs'), crypto = require('crypto');
const { locateAttachment } = require('./locator.js');
(async () => {
  const [file, expect] = process.argv.slice(2);
  const fd = fs.openSync(file, 'r'); const log = [];
  const read = async (off, len) => {
    const buf = Buffer.alloc(len); const n = fs.readSync(fd, buf, 0, len, off);
    log.push([off, len, n]); return new Uint8Array(buf.buffer, buf.byteOffset, n);
  };
  const t0 = process.hrtime.bigint();
  let r;
  try { r = await locateAttachment(read, { fileName: process.argv[4] === '*' ? null : (process.argv[4] || 'skellycam_frames.skfr') }); } catch (err) { r = { ok: false, reason: 'exception: ' + err.message }; }
  const ms = Number(process.hrtime.bigint() - t0) / 1e6;
  const out = { file, ok: r.ok, reason: r.reason, name: r.name, fileDataOffset: r.fileDataOffset, fileDataSize: r.fileDataSize,
    segmentUID: r.segmentUID, reads: log.length, readLog: log, bytesRead: log.reduce((s, x) => s + x[2], 0), ms: +ms.toFixed(2) };
  if (r.ok && expect) {
    const h = (x) => crypto.createHash('sha256').update(x).digest('hex');
    out.payloadIdentical = h(r.data) === h(fs.readFileSync(expect));
  }
  console.log(JSON.stringify(out));
})();
