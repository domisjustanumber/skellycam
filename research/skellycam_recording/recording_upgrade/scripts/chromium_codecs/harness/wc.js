// WebCodecs VideoDecoder decode test of one elementary stream (IVF for AV1/VP9/VP8, Annex B for H.264/HEVC).
// Query: key, server, es (URL), codec (WebCodecs codec string), hw (prefer-hardware|prefer-software|no-preference)
// Every output frame is drawn to a canvas and its index pattern is checked against output order.
'use strict';
(async () => {
  const es = Q.get('es'), codec = Q.get('codec'), hw = Q.get('hw') || 'no-preference';
  const res = { key: KEY, es, codec, hw };
  try {
    const M = await manifest();
    const W = M.w, H = M.h, dur = 1e6 / M.fps;
    const buf = await (await fetch(es)).arrayBuffer();
    let chunks;
    if (es.endsWith('.ivf')) {
      const { fourcc, frames } = parseIvf(buf); res.fourcc = fourcc;
      chunks = frames.map((f) => ({ type: isKeyIvf(fourcc, f.data) ? 'key' : 'delta', timestamp: f.ts, data: f.data }));
    } else {
      chunks = parseAnnexB(buf, es.endsWith('.hevc')).map((u, i) => ({ type: u.key ? 'key' : 'delta', timestamp: Math.round(i * dur), data: u.data }));
    }
    res.chunks = chunks.length; res.keyChunks = chunks.filter((c) => c.type === 'key').length;
    const config = { codec, codedWidth: W, codedHeight: H, hardwareAcceleration: hw };
    res.isConfigSupported = (await VideoDecoder.isConfigSupported(config)).supported;
    const canvas = document.createElement('canvas'); canvas.width = W; canvas.height = H;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    const outs = []; const errors = [];
    const dec = new VideoDecoder({
      output: (frame) => {
        try {
          const r = frameCheck(ctx, frame, M, W, H);
          outs.push({ idx: r.idx, mad: r.mad, fmt: frame.format, cw: frame.codedWidth, ts: frame.timestamp });
        } catch (e) { outs.push({ err: String(e) }); }
        frame.close();
      },
      error: (e) => errors.push(e.name + ': ' + e.message),
    });
    dec.configure(config);
    for (const c of chunks) {
      if (dec.state !== 'configured') break;
      try { dec.decode(new EncodedVideoChunk(c)); } catch (e) { errors.push('decode(): ' + e.name + ': ' + e.message); break; }
      if (dec.decodeQueueSize > 8) await new Promise((r) => dec.addEventListener('dequeue', r, { once: true }));
    }
    if (dec.state === 'configured') { try { await withTimeout(dec.flush(), 15000, 'flush'); } catch (e) { errors.push('flush: ' + e); } }
    res.state = dec.state;
    res.errors = errors.slice(0, 3);
    res.outputs = outs.length;
    res.inOrderCorrect = outs.filter((o, i) => o.idx === i).length;
    const mads = outs.map((o) => o.mad).filter((m) => m != null);
    res.madMax = mads.length ? Math.max(...mads) : null;
    res.madMean = mads.length ? +(mads.reduce((a, b) => a + b, 0) / mads.length).toFixed(2) : null;
    res.formats = [...new Set(outs.map((o) => o.fmt))];
    res.sample = outs.slice(0, 3);
    try { dec.close(); } catch { }
  } catch (e) { res.fatal = String(e); }
  postResult(res);
})();
