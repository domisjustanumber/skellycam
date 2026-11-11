// <video> play test for one clip. Query: key, server, src (URL), mode=src|mse, mime (for mse), nopattern=1
'use strict';
(async () => {
  const src = Q.get('src'), mode = Q.get('mode') || 'src', mime = Q.get('mime'), nopattern = Q.get('nopattern') === '1';
  const res = { key: KEY, src, mode, mime, href: location.href, events: [] };
  const t0 = performance.now();
  let M;
  try { M = await manifest(); } catch (e) { res.fatal = 'manifest: ' + e; return postResult(res); }
  const W = M.w, H = M.h, FPS = M.fps;
  const FRAMES = +(Q.get('frames') || M.frames); // big clips: 600 frames (content grids exist for idx < M.frames only)
  const v = document.createElement('video');
  v.muted = true; v.playsInline = true; v.preload = 'auto'; v.width = 320; v.height = 180;
  document.body.append(v);
  for (const ev of ['loadedmetadata', 'loadeddata', 'canplay', 'canplaythrough', 'error', 'stalled', 'waiting', 'ended', 'emptied', 'abort'])
    v.addEventListener(ev, () => res.events.push(ev));
  const canvas = document.createElement('canvas'); canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  const ready = new Promise((resolve) => {
    v.addEventListener('loadeddata', () => resolve('loadeddata'), { once: true });
    v.addEventListener('error', () => resolve('error'), { once: true });
  });
  try {
    if (mode === 'mse') {
      if (!window.MediaSource) throw new Error('no MediaSource');
      res.mseTypeSupported = MediaSource.isTypeSupported(mime);
      const ms = new MediaSource();
      v.src = URL.createObjectURL(ms);
      await withTimeout(new Promise((r) => ms.addEventListener('sourceopen', r, { once: true })), 5000, 'sourceopen');
      const sb = ms.addSourceBuffer(mime);
      const buf = await (await fetch(src)).arrayBuffer();
      const appended = new Promise((resolve, reject) => {
        sb.addEventListener('updateend', resolve, { once: true });
        sb.addEventListener('error', () => reject(new Error('sourcebuffer error event')), { once: true });
      });
      sb.appendBuffer(buf);
      await withTimeout(appended, 8000, 'append');
      ms.endOfStream();
    } else {
      v.src = src;
    }
  } catch (e) { res.setupError = String(e); }
  const how = await Promise.race([ready, sleep(10000).then(() => 'timeout')]);
  res.ready = how;
  if (how !== 'loadeddata') {
    if (v.error) res.error = { code: v.error.code, message: v.error.message };
    res.readyState = v.readyState; res.networkState = v.networkState;
    return postResult(res);
  }
  const ranges = (r) => Array.from({ length: r.length }, (_, i) => [+r.start(i).toFixed(3), +r.end(i).toFixed(3)]);
  res.meta = { duration: v.duration, w: v.videoWidth, h: v.videoHeight, seekable: ranges(v.seekable) };
  const hasRVFC = 'requestVideoFrameCallback' in HTMLVideoElement.prototype; res.hasRVFC = hasRVFC;
  const nextFrame = (ms) => new Promise((r) => {
    let done = false;
    if (hasRVFC) v.requestVideoFrameCallback((now, md) => { if (!done) { done = true; r(md); } });
    setTimeout(() => { if (!done) { done = true; r(null); } }, ms);
  });
  try { res.first = frameCheck(ctx, v, M, W, H); } catch (e) { res.pixelError = String(e); }

  // play ~1.2 s of media time, check every presented frame
  const frames = [];
  let stop = false;
  const onFrame = (now, md) => {
    if (stop) return;
    if (res.pixelError || nopattern) frames.push({ mt: +md.mediaTime.toFixed(4), pf: md.presentedFrames });
    else {
      try { const r = frameCheck(ctx, v, M, W, H); frames.push({ mt: +md.mediaTime.toFixed(4), pf: md.presentedFrames, exp: Math.round(md.mediaTime * FPS), idx: r.idx, mad: r.mad }); }
      catch (e) { frames.push({ err: String(e) }); }
    }
    v.requestVideoFrameCallback(onFrame);
  };
  if (hasRVFC) v.requestVideoFrameCallback(onFrame);
  try { await withTimeout(v.play(), 5000, 'play'); res.playOk = true; } catch (e) { res.playError = String(e); }
  const tEnd = performance.now() + 4000;
  while (performance.now() < tEnd && v.currentTime < 1.2 && !v.ended && !v.error) await sleep(50);
  res.playCallbacksOnly = !hasRVFC;
  stop = true; v.pause();
  res.playCurrentTime = +v.currentTime.toFixed(3);
  const good = frames.filter((f) => f.idx >= 0);
  res.play = {
    callbacks: frames.length,
    idxValid: good.length,
    idxEqExpected: good.filter((f) => f.idx === f.exp).length,
    idxOffByOne: good.filter((f) => Math.abs(f.idx - f.exp) === 1).length,
    monotonic: good.every((f, i) => i === 0 || f.idx > good[i - 1].idx),
    madMax: good.length ? Math.max(...good.map((f) => f.mad ?? 999)) : null,
    madMean: good.length ? +(good.reduce((a, f) => a + (f.mad ?? 0), 0) / good.length).toFixed(2) : null,
    sample: frames.slice(0, 4),
  };
  if (v.error) res.playMediaError = { code: v.error.code, message: v.error.message };

  // frame-accurate seek test (paused): target the middle of frame k
  const seeks = [];
  const targets = [0, 7, 29, 30, 31, 45, 59, 12, 3, 58];
  if (FRAMES > M.frames) targets.push(150, 299, 451, FRAMES - 2, 5);
  for (const k of targets) {
    const seeked = new Promise((r) => v.addEventListener('seeked', r, { once: true }));
    v.currentTime = (k + 0.5) / FPS;
    const ok = await Promise.race([seeked.then(() => true), sleep(4000).then(() => false)]);
    if (!ok) { seeks.push({ k, seeked: false }); continue; }
    await nextFrame(300);
    if (res.pixelError || nopattern) { seeks.push({ k, ct: +v.currentTime.toFixed(4) }); continue; }
    try { const r = frameCheck(ctx, v, M, W, H); seeks.push({ k, idx: r.idx, mad: r.mad, ct: +v.currentTime.toFixed(4) }); }
    catch (e) { seeks.push({ k, err: String(e) }); }
  }
  res.seeks = seeks;
  res.seekCompleted = seeks.filter((s) => s.seeked !== false).length;
  res.seekExact = seeks.filter((s) => s.idx === s.k).length;
  res.seekTotal = seeks.length;
  res.seekableAfter = ranges(v.seekable);
  if (v.error) res.seekMediaError = { code: v.error.code, message: v.error.message };
  res.wallMs = Math.round(performance.now() - t0); // NOT reported (timing rule); only used to size timeouts
  postResult(res);
})();
