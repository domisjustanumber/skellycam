// GF09 page: caps / <video> play-to-end + exact YUV readback / WebCodecs decode + exact YUV readback.
// No timing values are reported (functional only).
'use strict';
const Q = new URLSearchParams(location.search);
const KEY = Q.get('key'), SERVER = Q.get('server'), MODE = Q.get('mode'), CLIP = Q.get('clip');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function post(obj) {
  await fetch(`${SERVER}/result?key=${encodeURIComponent(KEY)}`, { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: JSON.stringify(obj) });
}
const b64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));

// Exact comparison of a VideoFrame against tight NV12 reference bytes (Y plane, then interleaved UV plane).
async function compareFrame(frame, ref, w, h) {
  const r = { format: frame.format, codedWidth: frame.codedWidth, codedHeight: frame.codedHeight, timestampUs: frame.timestamp,
    visible: frame.visibleRect ? [frame.visibleRect.width, frame.visibleRect.height] : null };
  if (!['NV12', 'I420'].includes(frame.format)) { r.compared = false; r.note = 'format not NV12/I420; no exact comparison'; return r; }
  const buf = new Uint8Array(frame.allocationSize());
  const lay = await frame.copyTo(buf);
  let my = 0, mu = 0, mv = 0, ny = 0, nc = 0;
  for (let y = 0; y < h; y++) {
    const o = lay[0].offset + y * lay[0].stride, ro = y * w;
    for (let x = 0; x < w; x++) { const d = Math.abs(buf[o + x] - ref[ro + x]); if (d) { ny++; if (d > my) my = d; } }
  }
  const cbase = w * h;
  for (let y = 0; y < h / 2; y++) {
    if (frame.format === 'NV12') {
      const o = lay[1].offset + y * lay[1].stride, ro = cbase + y * w;
      for (let x = 0; x < w; x += 2) {
        const du = Math.abs(buf[o + x] - ref[ro + x]), dv = Math.abs(buf[o + x + 1] - ref[ro + x + 1]);
        if (du || dv) nc++; if (du > mu) mu = du; if (dv > mv) mv = dv;
      }
    } else {
      const ou = lay[1].offset + y * lay[1].stride, ov = lay[2].offset + y * lay[2].stride, ro = cbase + y * w;
      for (let x = 0; x < w / 2; x++) {
        const du = Math.abs(buf[ou + x] - ref[ro + 2 * x]), dv = Math.abs(buf[ov + x] - ref[ro + 2 * x + 1]);
        if (du || dv) nc++; if (du > mu) mu = du; if (dv > mv) mv = dv;
      }
    }
  }
  Object.assign(r, { compared: true, maxAbsY: my, maxAbsU: mu, maxAbsV: mv, diffSamplesY: ny, diffChromaPairs: nc, exact: my === 0 && mu === 0 && mv === 0 });
  return r;
}

(async () => {
  const res = { key: KEY, mode: MODE, clip: CLIP, ua: navigator.userAgent };
  try {
    const M = await (await fetch(`${SERVER}/m/manifest.json`)).json();
    const c = M.clips.find((x) => x.id === CLIP);
    const W = M.w, H = M.h, FPS = M.fps;
    const cs = c.codec_string;
    res.codecString = cs;
    const refs = {};
    for (const k of M.ref_frames) refs[k] = new Uint8Array(await (await fetch(`${SERVER}/m/${c.id}.ref_f${k}.nv12`)).arrayBuffer());

    if (MODE === 'caps') {
      const wc = JSON.parse(await (await fetch(`${SERVER}/m/${c.wc}`)).text());
      const desc = b64(wc.description_b64);
      res.canPlayType = {};
      for (const mime of ['video/mp4', 'video/x-matroska', 'video/webm']) res.canPlayType[`${mime}; codecs="${cs}"`] = document.createElement('video').canPlayType(`${mime}; codecs="${cs}"`);
      res.canPlayType['video/x-matroska'] = document.createElement('video').canPlayType('video/x-matroska');
      res.mseIsTypeSupported = window.MediaSource ? MediaSource.isTypeSupported(`video/mp4; codecs="${cs}"`) : 'no MSE';
      res.isConfigSupported = {};
      for (const hw of ['no-preference', 'prefer-hardware', 'prefer-software']) {
        try { const s = await VideoDecoder.isConfigSupported({ codec: cs, description: desc, codedWidth: W, codedHeight: H, hardwareAcceleration: hw }); res.isConfigSupported[hw] = s.supported; }
        catch (e) { res.isConfigSupported[hw] = 'throws: ' + e.name + ': ' + e.message; }
      }
      try { const mc = await navigator.mediaCapabilities.decodingInfo({ type: 'file', video: { contentType: `video/mp4; codecs="${cs}"`, width: W, height: H, bitrate: 150000000, framerate: 30 } }); res.mediaCapabilities = { supported: mc.supported, smooth: mc.smooth, powerEfficient: mc.powerEfficient }; }
      catch (e) { res.mediaCapabilities = 'throws: ' + e.message; }
    }

    if (MODE === 'video') {
      const v = document.createElement('video');
      v.muted = true; v.preload = 'auto'; v.width = 320; v.height = 180; document.body.append(v);
      res.file = Q.get('file'); res.events = [];
      for (const ev of ['loadedmetadata', 'loadeddata', 'canplay', 'error', 'stalled', 'waiting', 'ended']) v.addEventListener(ev, () => res.events.push(ev));
      const ready = new Promise((r) => { v.addEventListener('loadeddata', () => r('loadeddata'), { once: true }); v.addEventListener('error', () => r('error'), { once: true }); });
      v.src = `${SERVER}/m/${res.file}`;
      res.ready = await Promise.race([ready, sleep(15000).then(() => 'timeout')]);
      if (res.ready !== 'loadeddata') { if (v.error) res.error = { code: v.error.code, message: v.error.message }; return post(res); }
      res.meta = { duration: v.duration, w: v.videoWidth, h: v.videoHeight };
      let cb = 0, maxPresented = 0;
      const onF = (_n, md) => { cb++; maxPresented = Math.max(maxPresented, md.presentedFrames); if (!v.ended) v.requestVideoFrameCallback(onF); };
      v.requestVideoFrameCallback(onF);
      const ended = new Promise((r) => v.addEventListener('ended', () => r(true), { once: true }));
      try { await v.play(); res.playOk = true; } catch (e) { res.playError = String(e); }
      res.ended = await Promise.race([ended, sleep(20000).then(() => false)]);
      res.rvfcCallbacks = cb; res.maxPresentedFrames = maxPresented; res.decodedFrames = v.getVideoPlaybackQuality().totalVideoFrames; res.droppedFrames = v.getVideoPlaybackQuality().droppedVideoFrames;
      if (v.error) res.error = { code: v.error.code, message: v.error.message };
      res.readback = [];
      for (const k of M.ref_frames) {
        const seeked = new Promise((r) => v.addEventListener('seeked', () => r(true), { once: true }));
        v.currentTime = (k + 0.5) / FPS;
        const ok = await Promise.race([seeked, sleep(5000).then(() => false)]);
        if (!ok) { res.readback.push({ k, seeked: false }); continue; }
        await Promise.race([new Promise((r) => v.requestVideoFrameCallback(() => r())), sleep(500)]);
        try {
          const f = new VideoFrame(v);
          const cmp = await compareFrame(f, refs[k], W, H); f.close();
          cmp.k = k; cmp.frameIndexFromTimestamp = Math.round(cmp.timestampUs / 1e6 * FPS); res.readback.push(cmp);
        } catch (e) { res.readback.push({ k, error: e.name + ': ' + e.message }); }
      }
      if (v.error) res.errorAfterSeek = { code: v.error.code, message: v.error.message };
    }

    if (MODE === 'wc') {
      const hw = Q.get('hw'); res.hw = hw;
      const wc = JSON.parse(await (await fetch(`${SERVER}/m/${c.wc}`)).text());
      const desc = b64(wc.description_b64);
      const cfg = { codec: cs, description: desc, codedWidth: W, codedHeight: H, hardwareAcceleration: hw };
      try { res.isConfigSupported = (await VideoDecoder.isConfigSupported(cfg)).supported; } catch (e) { res.isConfigSupported = 'throws: ' + e.message; }
      const frames = []; res.errors = [];
      const dec = new VideoDecoder({ output: (f) => frames.push(f), error: (e) => res.errors.push(e.name + ': ' + e.message) });
      try {
        dec.configure(cfg);
        const tb = wc.time_base[0] / wc.time_base[1];
        for (const p of wc.packets) {
          dec.decode(new EncodedVideoChunk({ type: p.key ? 'key' : 'delta', timestamp: Math.round(p.pts * tb * 1e6), data: b64(p.b64) }));
          await dec.flush(); // per-frame flush (intra_playback finding for h264_nvenc in WebCodecs)
        }
      } catch (e) { res.errors.push('throw ' + e.name + ': ' + e.message); }
      res.outputs = frames.length;
      res.readback = [];
      for (const k of M.ref_frames) {
        const f = frames[k];
        if (!f) { res.readback.push({ k, missing: true }); continue; }
        try { const cmp = await compareFrame(f, refs[k], W, H); cmp.k = k; cmp.frameIndexFromTimestamp = Math.round(cmp.timestampUs / 1e6 * FPS); res.readback.push(cmp); }
        catch (e) { res.readback.push({ k, error: e.name + ': ' + e.message }); }
      }
      for (const f of frames) f.close();
      try { dec.close(); } catch { }
    }
  } catch (e) { res.fatal = String(e && e.stack || e); }
  post(res);
})();
