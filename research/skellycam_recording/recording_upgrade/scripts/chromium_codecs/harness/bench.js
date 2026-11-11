// Timing benchmarks (run ONLY on a quiet machine via bench suite). Query:
//   mode=multi : n simultaneous <video> elements of one clip, played for secs; reports getVideoPlaybackQuality per element
//   mode=seek  : count random paused seeks on one clip; latency = currentTime set -> 'seeked' -> next rVFC; index verified
//   mode=wc    : WebCodecs decode of the whole elementary stream as fast as possible (hw=prefer-hardware|prefer-software)
// Common: key, server, base (media URL prefix), clip (bench clip id)
'use strict';
(async () => {
  const mode = Q.get('mode'), clipId = Q.get('clip'), base = Q.get('base');
  const res = { key: KEY, mode, clip: clipId };
  try {
    const BM = await (await fetch(`${base}bench/bench_manifest.json`, { mode: 'cors' })).json();
    const c = BM.clips.find((x) => x.id === clipId);
    if (!c) throw new Error('clip not in bench manifest');
    res.clipInfo = c;
    const pct = (a, p) => { const s = [...a].sort((x, y) => x - y); return s.length ? +s[Math.min(s.length - 1, Math.floor(p * s.length))].toFixed(2) : null; };
    if (mode === 'multi') {
      const n = +Q.get('n'), secs = +Q.get('secs');
      const vids = [];
      for (let i = 0; i < n; i++) {
        const v = document.createElement('video'); v.muted = true; v.preload = 'auto'; v.width = 160; v.height = 90;
        v.src = `${base}${c.file}?copy=${i}`; document.body.append(v); vids.push(v);
      }
      await withTimeout(Promise.all(vids.map((v) => new Promise((ok, bad) => { v.addEventListener('loadeddata', ok, { once: true }); v.addEventListener('error', () => bad(new Error('media error ' + (v.error && v.error.message))), { once: true }); }))), 20000, 'load');
      const presented = vids.map(() => 0);
      vids.forEach((v, i) => { const cb = () => { presented[i]++; v.requestVideoFrameCallback(cb); }; v.requestVideoFrameCallback(cb); });
      const t0 = performance.now();
      await Promise.all(vids.map((v) => v.play()));
      await sleep(secs * 1000);
      const wall = (performance.now() - t0) / 1000;
      res.elements = vids.map((v, i) => { const q = v.getVideoPlaybackQuality(); return { total: q.totalVideoFrames, dropped: q.droppedVideoFrames, presented: presented[i], currentTime: +v.currentTime.toFixed(3) }; });
      vids.forEach((v) => v.pause());
      res.n = n; res.secs = secs; res.wallSec = +wall.toFixed(3);
      res.expectedFramesPerElement = Math.min(c.frames, Math.round(wall * c.fps));
      res.droppedTotal = res.elements.reduce((a, e) => a + e.dropped, 0);
      res.presentedMin = Math.min(...presented);
    } else if (mode === 'seek') {
      const count = +Q.get('count');
      const v = document.createElement('video'); v.muted = true; v.preload = 'auto'; v.src = base + c.file; document.body.append(v);
      await withTimeout(new Promise((ok, bad) => { v.addEventListener('loadeddata', ok, { once: true }); v.addEventListener('error', () => bad(new Error('media error')), { once: true }); }), 20000, 'load');
      const cv = document.createElement('canvas'); cv.width = c.w; cv.height = BM.block; const ctx = cv.getContext('2d', { willReadFrequently: true });
      let seed = 12345; const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
      const lat = []; let exact = 0;
      for (let i = 0; i < count; i++) {
        const k = Math.floor(rnd() * c.frames);
        const t0 = performance.now();
        const seeked = new Promise((r) => v.addEventListener('seeked', r, { once: true }));
        v.currentTime = (k + 0.5) / c.fps;
        await seeked;
        await new Promise((r) => { let d = false; v.requestVideoFrameCallback(() => { if (!d) { d = true; r(); } }); setTimeout(() => { if (!d) { d = true; r(); } }, 500); });
        lat.push(performance.now() - t0);
        ctx.drawImage(v, 0, 0, c.w, c.h);
        const r = readIndex(ctx.getImageData(0, 0, c.w, BM.block), BM.block, BM.nbits);
        if (r.idx === k) exact++;
      }
      res.count = count; res.exact = exact;
      res.latencyMs = { median: pct(lat, 0.5), p95: pct(lat, 0.95), max: +Math.max(...lat).toFixed(2), mean: +(lat.reduce((a, b) => a + b, 0) / lat.length).toFixed(2) };
    } else if (mode === 'wc') {
      const hw = Q.get('hw');
      const buf = await (await fetch(base + c.es)).arrayBuffer();
      let chunks;
      if (c.es.endsWith('.ivf')) { const { fourcc, frames } = parseIvf(buf); chunks = frames.map((f) => ({ type: isKeyIvf(fourcc, f.data) ? 'key' : 'delta', timestamp: f.ts, data: f.data })); }
      else chunks = parseAnnexB(buf, c.es.endsWith('.hevc')).map((u, i) => ({ type: u.key ? 'key' : 'delta', timestamp: Math.round(i * 1e6 / c.fps), data: u.data }));
      const config = { codec: c.codec, codedWidth: c.w, codedHeight: c.h, hardwareAcceleration: hw };
      res.isConfigSupported = (await VideoDecoder.isConfigSupported(config)).supported;
      let outputs = 0; const errors = [];
      const dec = new VideoDecoder({ output: (f) => { outputs++; f.close(); }, error: (e) => errors.push(e.name + ': ' + e.message) });
      dec.configure(config);
      const t0 = performance.now();
      for (const ch of chunks) {
        if (dec.state !== 'configured') break;
        dec.decode(new EncodedVideoChunk(ch));
        if (dec.decodeQueueSize > 16) await new Promise((r) => dec.addEventListener('dequeue', r, { once: true }));
      }
      if (dec.state === 'configured') await dec.flush();
      const ms = performance.now() - t0;
      res.outputs = outputs; res.chunks = chunks.length; res.errors = errors.slice(0, 3);
      res.decodeMs = +ms.toFixed(1); res.fps = +(outputs / (ms / 1000)).toFixed(1);
      try { dec.close(); } catch { }
    }
  } catch (e) { res.fatal = String(e); }
  postResult(res);
})();
