// Minimal Matroska attachment locator. Head-anchored: needs no file size and no suffix range.
// read(offset, length) -> Promise<Uint8Array> (may be shorter at EOF). Works in Node and the browser.
(function (root) {
  const ID = { EBML: 0x1A45DFA3, DOCTYPE: 0x4282, SEGMENT: 0x18538067, SEEKHEAD: 0x114D9B74, SEEK: 0x4DBB,
    SEEKID: 0x53AB, SEEKPOS: 0x53AC, CRC32: 0xBF, VOID: 0xEC, INFO: 0x1549A966, SEGUID: 0x73A4,
    ATTACHMENTS: 0x1941A469, ATTACHEDFILE: 0x61A7, FILENAME: 0x466E, MEDIATYPE: 0x4660, FILEDATA: 0x465C };
  function vint(b, p, keepMarker) {
    if (p >= b.length) throw new RangeError('short');
    const first = b[p]; let n = 1, m = 0x80;
    while (n <= 8 && !(first & m)) { n++; m >>= 1; }
    if (n > 8) throw new Error('bad vint @' + p);
    if (p + n > b.length) throw new RangeError('short');
    let v = keepMarker ? first : (first & (m - 1)), allOnes = v === m - 1;
    for (let i = 1; i < n; i++) { v = v * 256 + b[p + i]; if (b[p + i] !== 0xFF) allOnes = false; }
    return { v, n, unknown: !keepMarker && allOnes };
  }
  function elem(b, p) {               // -> {id, data (offset of payload in b), size (null = unknown), hdr}
    const a = vint(b, p, true), s = vint(b, p + a.n, false);
    return { id: a.v, data: p + a.n + s.n, size: s.unknown ? null : s.v, hdr: a.n + s.n };
  }
  const uintBE = (b, o, n) => { let v = 0; for (let i = 0; i < n; i++) v = v * 256 + b[o + i]; return v; };
  const str = (b, o, n) => new TextDecoder().decode(b.subarray(o, o + n));
  const hex = (b) => Array.from(b, x => x.toString(16).padStart(2, '0')).join('');

  async function locateAttachment(read, opts = {}) {
    const headLen = opts.headLen || 4096, attProbe = opts.attProbe || 512;
    const want = opts.fileName || null, wantMime = opts.mediaType || null;
    const fail = (reason, extra) => Object.assign({ ok: false, reason }, extra || {});
    let b = await read(0, headLen);
    let e = elem(b, 0);
    if (e.id !== ID.EBML) return fail('not-ebml');
    let docType = null;
    for (let q = e.data; q < e.data + e.size;) { const c = elem(b, q); if (c.id === ID.DOCTYPE) docType = str(b, c.data, c.size); q = c.data + c.size; }
    if (docType !== 'matroska' && docType !== 'webm') return fail('doctype ' + docType);
    const segPos = e.data + e.size, seg = elem(b, segPos);
    if (seg.id !== ID.SEGMENT) return fail('no-segment');
    const segData = seg.data;
    let p = segData, c = elem(b, p);
    if (c.id === ID.CRC32) { p = c.data + c.size; c = elem(b, p); }
    if (c.id !== ID.SEEKHEAD) return fail('no-seekhead', { firstChild: c.id.toString(16), segmentUnknownSize: seg.size === null });
    if (c.data + c.size > b.length) { b = await read(0, c.data + c.size); c = elem(b, p); } // SeekHead larger than head read
    const seeks = {};
    for (let q = c.data; q < c.data + c.size;) {
      const s = elem(b, q);
      if (s.id === ID.SEEK) {
        let sid = null, spos = null;
        for (let r = s.data; r < s.data + s.size;) { const f = elem(b, r); if (f.id === ID.SEEKID) sid = uintBE(b, f.data, f.size); if (f.id === ID.SEEKPOS) spos = uintBE(b, f.data, f.size); r = f.data + f.size; }
        if (sid !== null && spos !== null && !(sid in seeks)) seeks[sid] = spos;
      }
      q = s.data + s.size;
    }
    // Segment UID from Info, if Info is inside the head read (it is for FFmpeg files): costs no extra read
    let segmentUID = null;
    if (ID.INFO in seeks && segData + seeks[ID.INFO] + 16 < b.length) {
      try {
        const inf = elem(b, segData + seeks[ID.INFO]);
        if (inf.id === ID.INFO) for (let q = inf.data; q < Math.min(inf.data + inf.size, b.length);) { const f = elem(b, q); if (f.id === ID.SEGUID) segmentUID = hex(b.subarray(f.data, f.data + f.size)); q = f.data + f.size; }
      } catch (err) { /* Info straddles the head read: leave UID null */ }
    }
    if (!(ID.ATTACHMENTS in seeks)) return fail('no-attachments-entry', { segmentUID });
    const attAbs = segData + seeks[ID.ATTACHMENTS];
    let a = await read(attAbs, attProbe), base = attAbs;
    let ae;
    try { ae = elem(a, 0); } catch (err) { return fail('attachments-past-eof'); }
    if (ae.id !== ID.ATTACHMENTS) return fail('stale-seekhead', { found: ae.id.toString(16) });
    // walk AttachedFile children until one matches; re-read when a header falls outside the buffer
    const attEnd = ae.size === null ? Infinity : base + ae.data + ae.size;
    let q = base + ae.data;
    while (q < attEnd) {
      if (q - base < 0 || q - base + 16 > a.length) { a = await read(q, attProbe); base = q; if (a.length === 0) break; }
      const af = elem(a, q - base);
      if (af.size === null) return fail('unknown-size-attachedfile');
      const afEnd = q + af.hdr + af.size;
      if (af.id === ID.ATTACHEDFILE) {
        let name = null, mime = null, fd = null, pos = q + af.hdr;   // absolute
        while (pos < afEnd) {
          if (pos - base < 0 || pos - base + 16 > a.length) { a = await read(pos, attProbe); base = pos; }
          let f = elem(a, pos - base);
          if ((f.id === ID.FILENAME || f.id === ID.MEDIATYPE) && f.data + f.size > a.length) {
            a = await read(pos, f.hdr + f.size); base = pos; f = elem(a, 0);
          }
          if (f.id === ID.FILENAME) name = str(a, f.data, f.size);
          else if (f.id === ID.MEDIATYPE) mime = str(a, f.data, f.size);
          else if (f.id === ID.FILEDATA) fd = { offset: base + f.data, size: f.size };
          pos = base + f.data + f.size;
        }
        if (fd && (!want || name === want) && (!wantMime || mime === wantMime)) {
          const data = opts.fetchData === false ? null : await read(fd.offset, fd.size);
          if (data && data.length !== fd.size) return fail('short-filedata', { got: data.length, want: fd.size });
          return { ok: true, name, mime, fileDataOffset: fd.offset, fileDataSize: fd.size, attachmentsAt: attAbs, segmentUID, data };
        }
      }
      q = afEnd;
    }
    return fail('no-matching-attachedfile', { segmentUID });
  }
  root.locateAttachment = locateAttachment;
  if (typeof module !== 'undefined') module.exports = { locateAttachment };
})(typeof globalThis !== 'undefined' ? globalThis : this);
