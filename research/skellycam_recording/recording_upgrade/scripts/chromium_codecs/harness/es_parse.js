// Elementary-stream parsers shared by wc.js and bench.js (IVF for AV1/VP9/VP8, Annex B with AUD for H.264/HEVC).
'use strict';
function parseIvf(buf) {
  const dv = new DataView(buf);
  const magic = String.fromCharCode(...new Uint8Array(buf, 0, 4));
  if (magic !== 'DKIF') throw new Error('not IVF');
  const hdr = dv.getUint16(6, true), den = dv.getUint32(16, true), num = dv.getUint32(20, true);
  const fourcc = String.fromCharCode(...new Uint8Array(buf, 8, 4));
  const frames = []; let off = hdr;
  while (off + 12 <= buf.byteLength) {
    const size = dv.getUint32(off, true); const pts = Number(dv.getBigUint64(off + 4, true));
    frames.push({ data: new Uint8Array(buf, off + 12, size), ts: Math.round(pts * num / den * 1e6) });
    off += 12 + size;
  }
  return { fourcc, frames };
}
function isKeyIvf(fourcc, d) {
  if (fourcc === 'VP80') return (d[0] & 1) === 0;
  if (fourcc === 'VP90') {
    let bit = 0; const rd = () => (d[bit >> 3] >> (7 - (bit++ & 7))) & 1;
    rd(); rd(); // frame_marker
    const lo = rd(), hi = rd(); const profile = (hi << 1) | lo; if (profile === 3) rd();
    if (rd()) return false; // show_existing_frame
    return rd() === 0;      // frame_type 0 = KEY_FRAME
  }
  if (fourcc === 'AV01') { // key if the temporal unit carries a sequence header OBU (type 1)
    let off = 0;
    while (off < d.length) {
      const h = d[off]; const type = (h >> 3) & 15, ext = (h >> 2) & 1, hasSize = (h >> 1) & 1;
      if (type === 1) return true;
      if (!hasSize) return false;
      let p = off + 1 + ext, size = 0, shift = 0, b;
      do { b = d[p++]; size |= (b & 0x7f) << shift; shift += 7; } while (b & 0x80);
      off = p + size;
    }
    return false;
  }
  return false;
}
// Split Annex B into access units. An AU starts at the first VCL NAL whose first-slice flag is set
// (H.264: first_mb_in_slice == 0, i.e. first ue(v) bit is 1; HEVC: first_slice_segment_in_pic_flag), together with the
// prefix non-VCL NALs (AUD, parameter sets, prefix SEI) that directly precede it. (A first version split at AUD NALs;
// ffmpeg's HEVC Annex B output places the AUD after the first IDR picture, which dropped the IDR.)
function parseAnnexB(buf, hevc) {
  const d = new Uint8Array(buf); const nals = [];
  for (let i = 0; i + 3 < d.length; i++) {
    if (d[i] === 0 && d[i + 1] === 0 && (d[i + 2] === 1 || (d[i + 2] === 0 && d[i + 3] === 1))) {
      const sc = d[i + 2] === 1 ? 3 : 4; const h = i + sc;
      const type = hevc ? (d[h] >> 1) & 63 : d[h] & 31;
      const vcl = hevc ? type <= 31 : (type >= 1 && type <= 5);
      const firstSlice = vcl ? (hevc ? (d[h + 2] & 0x80) !== 0 : (d[h + 1] & 0x80) !== 0) : false;
      const prefix = hevc ? [32, 33, 34, 35, 39].includes(type) : [6, 7, 8, 9].includes(type);
      const key = hevc ? (type >= 16 && type <= 21) : type === 5;
      nals.push({ pos: i, vcl, firstSlice, prefix, key }); i += sc;
    }
  }
  const starts = []; let pendingPrefix = null; let seenVcl = false;
  for (const n of nals) {
    if (n.prefix) { if (pendingPrefix === null) pendingPrefix = n.pos; continue; }
    if (n.vcl && n.firstSlice) { starts.push({ pos: pendingPrefix ?? n.pos, key: n.key }); seenVcl = true; }
    else if (n.vcl && n.key && starts.length) starts[starts.length - 1].key = true;
    pendingPrefix = null;
  }
  return starts.map((u, i) => ({ data: d.subarray(u.pos, i + 1 < starts.length ? starts[i + 1].pos : d.length), key: u.key }));
}

