// Overlay functional tests inside Chromium (Electron). See main.js for usage. Results -> POST /result.
'use strict';
const Q = new URLSearchParams(location.search);
const TESTS = (Q.get('tests') || '').split(',').filter(Boolean);
const ONLY = (Q.get('files') || '').split(',').filter(Boolean);
const MODE = Q.get('mode') || 'functional';
const W = 1280, H = 720, FPS = 30;
const stage = document.getElementById('stage');
const statusEl = document.getElementById('status');
const R = { tests: TESTS, mode: MODE, userAgent: navigator.userAgent, results: {} };
const sleep = ms => new Promise(r => setTimeout(r, ms));
function status(s) { statusEl.textContent = s; fetch('/log', { method: 'POST', body: s }).catch(() => {}); }
const MEDIA = n => `/media/${n}`;

// ---------------------------------------------------------------- barcode helpers
function decodeBits(getLuma, centres) {
  const bits = centres.map(([x, y]) => (getLuma(x, y) > 128 ? 1 : 0));
  let idx = 0; for (let k = 0; k < 12; k++) idx |= bits[k] << k;
  let chk = 0; for (let k = 0; k < 4; k++) chk |= bits[12 + k] << k;
  let pc = 0; for (let k = 0; k < 12; k++) pc += (idx >> k) & 1;
  return (pc & 15) === chk ? idx : -1;
}
const VC = Array.from({ length: 16 }, (_, k) => [k * 80 + 40, 700]);
const OC = Array.from({ length: 16 }, (_, k) => [k * 40 + 20, 80]);
const scratch = document.createElement('canvas'); scratch.width = W; scratch.height = H;
const sctx = scratch.getContext('2d', { willReadFrequently: true });
function readVideoBarcode(src, centres = VC, alphaOut) {
  sctx.clearRect(0, 0, W, H);
  sctx.drawImage(src, 0, 0, W, H);
  const y0 = centres[0][1];
  const img = sctx.getImageData(0, y0, W, 1).data;
  if (alphaOut) alphaOut.a = img[(centres[0][0]) * 4 + 3];
  return decodeBits((x) => { const o = x * 4; return 0.299 * img[o] + 0.587 * img[o + 1] + 0.114 * img[o + 2]; }, centres);
}
function readCanvasBarcode(ctx, centres) {
  const img = ctx.getImageData(0, centres[0][1], W, 1).data;
  return decodeBits((x) => { const o = x * 4; return 0.299 * img[o] + 0.587 * img[o + 1] + 0.114 * img[o + 2]; }, centres);
}
function drawOverlayBarcode(ctx, f) {
  const bits = []; for (let k = 0; k < 12; k++) bits.push((f >> k) & 1);
  let pc = 0; for (let k = 0; k < 12; k++) pc += (f >> k) & 1;
  for (let k = 0; k < 4; k++) bits.push(((pc & 15) >> k) & 1);
  bits.forEach((b, k) => { ctx.fillStyle = b ? '#fff' : '#000'; ctx.fillRect(k * 40, 60, 40, 40); });
}

// ---------------------------------------------------------------- overlay data + renderer
let OV = null; // {header, frames: Map}
async function loadOverlay() {
  if (OV) return OV;
  const txt = await (await fetch(MEDIA('overlay.jsonl'))).text();
  const lines = txt.split('\n').filter(Boolean);
  const header = JSON.parse(lines[0]).header; const frames = new Map();
  for (const l of lines.slice(1)) { const d = JSON.parse(l); frames.set(d.f, d); }
  OV = { header, frames };
  return OV;
}
function sideColor(n) { return n.includes('left') ? '#4488ff' : n.includes('right') ? '#ff4444' : '#00aa00'; }
const measureCache = new Map();
function drawOverlay(ctx, f, opts = {}) {
  ctx.clearRect(0, 0, W, H);
  if (opts.video) ctx.drawImage(opts.video, 0, 0, W, H); // canvas-composite mode: video pixels + overlay in one canvas commit
  const rec = OV.frames.get(f);
  ctx.save();
  ctx.beginPath(); ctx.rect(0, 0, W, 670); ctx.clip(); // keep the video barcode rows free
  if (rec) {
    const names = OV.header.skeleton_schema.points; const conn = OV.header.skeleton_schema.connections;
    const sk = rec.sk;
    if (sk) {
      ctx.lineWidth = 2;
      for (const [a, b] of conn) {
        if (sk[a * 3 + 2] < 0.5 || sk[b * 3 + 2] < 0.5) continue;
        ctx.strokeStyle = sideColor(names[a] + names[b]);
        ctx.beginPath(); ctx.moveTo(sk[a * 3], sk[a * 3 + 1]); ctx.lineTo(sk[b * 3], sk[b * 3 + 1]); ctx.stroke();
      }
      for (let i = 0; i < names.length; i++) {
        if (sk[i * 3 + 2] < 0.5) continue;
        ctx.fillStyle = sideColor(names[i]); ctx.beginPath(); ctx.arc(sk[i * 3], sk[i * 3 + 1], 4, 0, 2 * Math.PI); ctx.fill();
      }
    }
    if (rec.ci) {
      ctx.strokeStyle = '#00ff00'; ctx.lineWidth = 2;
      for (const [, c] of rec.ar) { ctx.beginPath(); ctx.moveTo(c[0], c[1]); for (let k = 2; k < 8; k += 2) ctx.lineTo(c[k], c[k + 1]); ctx.closePath(); ctx.stroke(); }
      ctx.strokeStyle = '#ff00ff';
      const items = [];
      for (let i = 0; i < rec.ci.length; i++) {
        const x = rec.cxy[2 * i], y = rec.cxy[2 * i + 1];
        ctx.beginPath(); ctx.moveTo(x, y - 5); ctx.lineTo(x + 5, y); ctx.lineTo(x, y + 5); ctx.lineTo(x - 5, y); ctx.closePath(); ctx.stroke();
        items.push({ id: rec.ci[i], x, y, text: String(rec.ci[i]) });
      }
      if (opts.labels !== false) {
        ctx.font = '12px Arial'; ctx.textBaseline = 'top';
        const measure = t => { let m = measureCache.get(t); if (!m) { m = { w: Math.ceil(ctx.measureText(t).width) + 2, h: 13 }; measureCache.set(t, m); } return m; };
        let placed;
        if (opts.layout === 'naive') placed = items.map(it => ({ id: it.id, x: it.x + 8, y: it.y - 8 - 13, ...measure(it.text), leader: null }));
        else placed = placeLabels(items, measure, { w: W, h: 670 }, { markerR: 6 }).placed;
        ctx.lineWidth = 3; ctx.strokeStyle = '#000'; ctx.fillStyle = '#00ff00';
        for (const p of placed) {
          if (p.leader) { ctx.save(); ctx.lineWidth = 1; ctx.strokeStyle = 'rgba(0,255,0,0.6)'; ctx.beginPath(); ctx.moveTo(p.leader[0], p.leader[1]); ctx.lineTo(p.leader[2], p.leader[3]); ctx.stroke(); ctx.restore(); }
          const t = String(p.id); ctx.strokeText(t, p.x + 1, p.y); ctx.fillText(t, p.x + 1, p.y);
        }
      }
    }
  }
  ctx.font = 'bold 20px monospace'; ctx.textBaseline = 'alphabetic'; ctx.lineWidth = 4; ctx.strokeStyle = '#000'; ctx.fillStyle = '#ffd2d2';
  const label = `cam ${rec ? rec.cam : '?'}  F${f}`;
  ctx.strokeText(label, 700, 90); ctx.fillText(label, 700, 90);
  drawOverlayBarcode(ctx, f);
  ctx.restore();
}

// ---------------------------------------------------------------- media helpers
function makeVideo(src, extra = {}) {
  stage.querySelectorAll('video,canvas').forEach(e => e.remove());
  const v = document.createElement('video');
  v.muted = true; v.playsInline = true; v.preload = 'auto'; v.crossOrigin = 'anonymous';
  Object.assign(v, extra);
  stage.appendChild(v);
  if (src) v.src = src;
  return v;
}
function makeOverlayCanvas() {
  const c = document.createElement('canvas'); c.width = W; c.height = H; stage.appendChild(c);
  return { c, ctx: c.getContext('2d', { willReadFrequently: true }) };
}
function waitEvent(el, ok, bad = 'error', ms = 15000) {
  return new Promise(res => {
    const t = setTimeout(() => res({ ok: false, why: 'timeout' }), ms);
    el.addEventListener(ok, () => { clearTimeout(t); res({ ok: true }); }, { once: true });
    if (bad) el.addEventListener(bad, () => { clearTimeout(t); res({ ok: false, why: bad, code: el.error ? el.error.code : null, msg: el.error ? el.error.message : null }); }, { once: true });
  });
}
function nextVFC(v, ms = 3000) {
  return new Promise(res => { const t = setTimeout(() => res(null), ms); v.requestVideoFrameCallback((now, md) => { clearTimeout(t); res(md); }); });
}
async function loadPts(name) { return (await fetch(MEDIA(`pts_${name}.json`))).json(); }
function nearest(pts, t) {
  let lo = 0, hi = pts.length - 1;
  while (lo < hi) { const m = (lo + hi) >> 1; if (pts[m] < t) lo = m + 1; else hi = m; }
  if (lo > 0 && Math.abs(pts[lo - 1] - t) <= Math.abs(pts[lo] - t)) lo--;
  return lo;
}
function rects() {
  const r = stage.getBoundingClientRect();
  const rect = { x: r.left, y: r.top, w: r.width, h: r.height };
  return { viewportW: window.innerWidth, videoRect: rect, overlayRect: rect };
}
async function capture(save) {
  const r = await fetch('/capture', { method: 'POST', body: JSON.stringify({ ...rects(), save }) });
  return r.json();
}

// ---------------------------------------------------------------- tests
const ALLFILES = ['base_cfr_h264.mp4', 'base_cfr_vp9.webm', 'base_cfr_av1.webm', 'base_vfr_vp9.webm', 'base_vfr_h264.mp4'];
const FILES = ONLY.length ? ALLFILES.filter(f => ONLY.includes(f)) : ALLFILES;

async function testCaps() {
  const types = ['video/webm; codecs="vp9"', 'video/webm; codecs="av01.0.04M.08"', 'video/mp4; codecs="avc1.42E01F"', 'video/mp4; codecs="av01.0.04M.08"',
    'video/x-matroska', 'video/x-matroska; codecs="vp9"', 'video/x-matroska; codecs="avc1.42E01F"', 'video/quicktime', 'video/quicktime; codecs="png"',
    'video/webm; codecs="vp9"; alpha', 'text/vtt'];
  const can = {}; for (const t of types) can[t] = document.createElement('video').canPlayType(t);
  const load = {};
  const files = [...FILES, 'overlay_vp9alpha.webm', 'overlay_png.mov', 'overlay_qtrle.mov', 'base_vp9_vtt_inband.webm', 'base_vp9_ass.mkv'];
  for (const f of files) {
    const v = makeVideo(MEDIA(f));
    const r = await waitEvent(v, 'loadeddata', 'error', 10000);
    let firstFrame = null;
    if (r.ok) {
      const md = await nextVFC(v, 1500);
      firstFrame = readVideoBarcode(v);
      r.mediaTimeFirst = md ? md.mediaTime : null;
    }
    load[f] = { ...r, videoWidth: v.videoWidth, videoHeight: v.videoHeight, duration: v.duration, textTracks: v.textTracks.length, barcodeAtLoad: firstFrame };
  }
  return { canPlayType: can, load };
}

// playback alignment: rVFC-driven overlay vs today's rAF/currentTime approach, plus composited captures
async function playAlign(file, rate = 1, opts = {}) {
  await loadOverlay();
  const pts = await loadPts(file);
  const v = makeVideo(MEDIA(file));
  const ov = makeOverlayCanvas();
  if (opts.canvasComposite) { v.style.opacity = '0'; opts.video = v; }
  const ok = await waitEvent(v, 'canplaythrough', 'error', 15000);
  if (!ok.ok) return { file, error: ok };
  v.playbackRate = rate;
  const S = { file, rate, canvasComposite: !!opts.canvasComposite, frames: pts.length, vfc: 0, vfcDecodeFail: 0, overlayMatch: 0, overlayMismatch: [], naiveMatch: 0, naiveMismatch: 0,
    overlaySelfCheckFail: 0, presentedGaps: 0, maxPresentedGap: 0, barcodeSkips: 0, raf: 0, rafDecodeFail: 0, rafUiMatch: 0, rafUiMismatch: 0, rafUiOffsets: {},
    captures: 0, captureMatch: 0, captureMismatch: [], captureFail: 0, distinctFramesSeen: 0 };
  const seen = new Set(); let lastPresented = null; let lastCode = null; let done = false; const pend = [];
  const onVFC = (now, md) => {
    if (done) return;
    S.vfc++;
    const code = readVideoBarcode(v);
    const fi = nearest(pts, md.mediaTime);
    drawOverlay(ov.ctx, fi, opts);
    if (readCanvasBarcode(ov.ctx, OC) !== fi) S.overlaySelfCheckFail++;
    if (code < 0) { S.vfcDecodeFail++; if ((S.decodeFailAt || (S.decodeFailAt = [])).length < 10) S.decodeFailAt.push({ fi, mediaTime: md.mediaTime }); }
    else {
      seen.add(code);
      if (code === fi) S.overlayMatch++; else if (S.overlayMismatch.length < 20) S.overlayMismatch.push({ code, fi, mediaTime: md.mediaTime }); else S.overlayMismatch.push(null);
      if (Math.round(md.mediaTime * FPS) === code) S.naiveMatch++; else S.naiveMismatch++;
      if (lastCode !== null && code > lastCode + 1) S.barcodeSkips += code - lastCode - 1;
      lastCode = code;
    }
    if (lastPresented !== null) { const g = md.presentedFrames - lastPresented - 1; if (g > 0) { S.presentedGaps += g; S.maxPresentedGap = Math.max(S.maxPresentedGap, g); } }
    lastPresented = md.presentedFrames;
    if (opts.capture && S.vfc % 10 === 5) {
      pend.push(capture().then(c => {
        S.captures++;
        if (c.error || c.video < 0 || c.overlay < 0) S.captureFail++;
        else if (c.video === c.overlay) S.captureMatch++; else S.captureMismatch.push([c.video, c.overlay]);
      }));
    }
    v.requestVideoFrameCallback(onVFC);
  };
  // today's skellycam-ui approach: rAF reads currentTime, frame = floor(currentTime * fps)
  const onRAF = () => {
    if (done) return;
    S.raf++;
    const ui = Math.floor(v.currentTime * FPS);
    const code = readVideoBarcode(v);
    if (code < 0) S.rafDecodeFail++;
    else if (code === ui) S.rafUiMatch++;
    else { S.rafUiMismatch++; const d = ui - code; S.rafUiOffsets[d] = (S.rafUiOffsets[d] || 0) + 1; }
    requestAnimationFrame(onRAF);
  };
  v.requestVideoFrameCallback(onVFC);
  if (!opts.noRaf) requestAnimationFrame(onRAF);
  const ended = waitEvent(v, 'ended', null, (pts[pts.length - 1] / rate + 20) * 1000);
  await v.play();
  await ended;
  done = true;
  await Promise.all(pend);
  S.distinctFramesSeen = seen.size;
  S.droppedVideoFrames = v.getVideoPlaybackQuality ? v.getVideoPlaybackQuality().droppedVideoFrames : null;
  S.totalVideoFrames = v.getVideoPlaybackQuality ? v.getVideoPlaybackQuality().totalVideoFrames : null;
  S.overlayMismatchCount = S.overlayMismatch.length; S.overlayMismatch = S.overlayMismatch.filter(Boolean);
  return S;
}

// paused seek/step alignment + composited capture
async function seekAlign(file) {
  await loadOverlay();
  const pts = await loadPts(file);
  const v = makeVideo(MEDIA(file));
  const ov = makeOverlayCanvas();
  const ok = await waitEvent(v, 'canplaythrough', 'error', 15000);
  if (!ok.ok) return { file, error: ok };
  const n = pts.length;
  const targets = [];
  for (let i = 0; i < 30; i++) targets.push(i);                // stepping forward
  for (let i = 0; i < 30; i++) targets.push((i * 97 + 13) % n); // scattered
  for (let i = 20; i > 0; i--) targets.push(n / 2 + i - 10 | 0); // stepping backwards across the VFR gap
  for (let i = targets.length - 1; i >= 0; i--) if (targets[i] >= n - 1) targets.splice(i, 1); // last frame: see lastFrameSeek
  const S = { file, n: targets.length, modes: {} };
  for (const mode of ['exact', 'mid']) {
    const M = { requestedMatch: 0, lookupMatch: 0, decodeFail: 0, decodeFailAt: [], noVFC: 0, mism: [], captureMatch: 0, captureMismatch: [], captureFail: 0,
      capture100Match: 0, capture100Mismatch: [], capture100Fail: 0 };
    for (const f of targets) {
      const t = mode === 'exact' ? pts[f] : (f + 1 < n ? (pts[f] + pts[f + 1]) / 2 : pts[f] + 0.5 / FPS);
      const t0 = performance.now();
      const vfc = nextVFC(v, 1500);
      const sk = waitEvent(v, 'seeked', null, 3000);
      v.currentTime = t;
      const skr = await sk;
      if (!skr.ok) M.seekedTimeout = (M.seekedTimeout || 0) + 1;
      let md = await vfc;
      if (performance.now() - t0 > 1000) status(`slow seek ${file} ${mode} f=${f} t=${t} seeked=${skr.ok} vfc=${!!md}`);
      if (!md) { M.noVFC++; md = { mediaTime: v.currentTime }; }
      const code = readVideoBarcode(v);
      const fi = nearest(pts, md.mediaTime);
      drawOverlay(ov.ctx, fi);
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      if (code < 0) { M.decodeFail++; if (M.decodeFailAt.length < 10) M.decodeFailAt.push({ f, mediaTime: md.mediaTime }); }
      else { if (code === f) M.requestedMatch++; else if (M.mism.length < 10) M.mism.push({ f, code, fi, mediaTime: md.mediaTime, t }); if (code === fi) M.lookupMatch++; }
      const c = await capture();
      if (c.error || c.video < 0 || c.overlay < 0) M.captureFail++;
      else if (c.video === c.overlay) M.captureMatch++; else M.captureMismatch.push([f, c.video, c.overlay]);
      await sleep(100);
      const c2 = await capture();
      if (c2.error || c2.video < 0 || c2.overlay < 0) M.capture100Fail++;
      else if (c2.video === c2.overlay) M.capture100Match++; else M.capture100Mismatch.push([f, c2.video, c2.overlay]);
    }
    S.modes[mode] = M;
  }
  return S;
}

// edge case: seek to the LAST frame, then seek back into the middle. Does the element still present the target?
async function lastFrameSeek(file) {
  const pts = await loadPts(file);
  const v = makeVideo(MEDIA(file));
  const ok = await waitEvent(v, 'canplaythrough', 'error', 15000);
  if (!ok.ok) return { file, error: ok };
  const n = pts.length; const steps = [];
  const seq = [Math.floor(n / 3), n - 2, n - 1, Math.floor(n / 2), 0, n - 1, v.duration, Math.floor(n / 4)];
  for (const f of seq) {
    const t = f === v.duration ? v.duration : pts[f];
    const vfc = nextVFC(v, 1500); const sk = waitEvent(v, 'seeked', null, 3000);
    v.currentTime = t; const skr = await sk; const md = await vfc;
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    steps.push({ target: f === v.duration ? 'duration' : f, t, seeked: skr.ok, vfc: !!md, mediaTime: md ? md.mediaTime : null, currentTimeAfter: v.currentTime,
      ended: v.ended, barcode: readVideoBarcode(v) });
  }
  return { file, n, duration: v.duration, lastPts: pts[n - 1], steps };
}

// WebVTT metadata track: are activeCues aligned with the presented frame?
async function vttAlign(file, vtt) {
  const pts = await loadPts(file);
  const v = makeVideo(null);
  const tr = document.createElement('track'); tr.kind = 'metadata'; tr.src = MEDIA(vtt); tr.default = true; v.appendChild(tr);
  v.src = MEDIA(file);
  v.textTracks[0].mode = 'hidden';
  const ok = await waitEvent(v, 'canplaythrough', 'error', 15000);
  const trLoad = tr.readyState === 2 ? { ok: true } : await waitEvent(tr, 'load', 'error', 10000);
  const track = v.textTracks[0];
  const S = { file, vtt, trackLoad: trLoad, cues: track.cues ? track.cues.length : null, play: { vfc: 0, match: 0, empty: 0, multi: 0, mismatch: 0, offsets: {} },
    cuechange: { events: 0, matchLastVFC: 0 }, seek: { n: 0, match: 0, empty: 0, mismatch: [] } };
  if (!ok.ok) { S.error = ok; return S; }
  let done = false; let lastCode = -1;
  track.addEventListener('cuechange', () => {
    S.cuechange.events++;
    const ac = track.activeCues; if (ac && ac.length && Number(ac[ac.length - 1].id) === lastCode) S.cuechange.matchLastVFC++;
  });
  const onVFC = (now, md) => {
    if (done) return;
    const code = readVideoBarcode(v);
    const ac = track.activeCues;
    S.play.vfc++;
    if (!ac || ac.length === 0) S.play.empty++;
    else {
      if (ac.length > 1) S.play.multi++;
      const id = Number(ac[ac.length - 1].id);
      if (id === code) S.play.match++; else { S.play.mismatch++; const d = id - code; S.play.offsets[d] = (S.play.offsets[d] || 0) + 1; }
    }
    lastCode = code;
    v.requestVideoFrameCallback(onVFC);
  };
  v.requestVideoFrameCallback(onVFC);
  const ended = waitEvent(v, 'ended', null, (pts[pts.length - 1] + 20) * 1000);
  await v.play(); await ended; done = true;
  // paused seeks: activeCues right after 'seeked' + first rVFC
  for (let i = 0; i < 40; i++) {
    const f = (i * 37 + 5) % pts.length;
    const vfc = nextVFC(v); const sk = waitEvent(v, 'seeked', null, 5000);
    v.currentTime = pts[f]; await sk; await vfc;
    await sleep(0);
    const code = readVideoBarcode(v); const ac = track.activeCues;
    S.seek.n++;
    if (!ac || !ac.length) S.seek.empty++;
    else if (Number(ac[ac.length - 1].id) === code) S.seek.match++;
    else if (S.seek.mismatch.length < 10) S.seek.mismatch.push({ f, code, cue: Number(ac[ac.length - 1].id) });
  }
  return S;
}

async function testInband() {
  const out = {};
  for (const f of ['base_vp9_vtt_inband.webm', 'base_vp9_ass.mkv']) {
    const v = makeVideo(MEDIA(f));
    const r = await waitEvent(v, 'loadedmetadata', 'error', 10000);
    await sleep(500);
    const tts = []; for (let i = 0; i < v.textTracks.length; i++) { const t = v.textTracks[i]; t.mode = 'hidden'; tts.push({ kind: t.kind, label: t.label, lang: t.language }); }
    if (r.ok) { v.currentTime = 1.0; await waitEvent(v, 'seeked', null, 5000); await sleep(300); }
    const cues = []; for (let i = 0; i < v.textTracks.length; i++) cues.push(v.textTracks[i].cues ? v.textTracks[i].cues.length : null);
    out[f] = { load: r, textTracks: tts, cuesAfterSeek: cues, videoWidth: v.videoWidth, audioTracks: v.audioTracks ? v.audioTracks.length : 'n/a' };
  }
  return out;
}

async function testAlpha() {
  const out = {};
  // 1. does Chromium decode the alpha channel of VP9-alpha WebM?
  const v = makeVideo(MEDIA('overlay_vp9alpha.webm'));
  const r = await waitEvent(v, 'loadeddata', 'error', 10000);
  out.load = r;
  if (r.ok) {
    await nextVFC(v, 1500);
    sctx.clearRect(0, 0, W, H); sctx.drawImage(v, 0, 0);
    const d = sctx.getImageData(0, 0, W, H).data; let zero = 0, full = 0;
    for (let i = 3; i < d.length; i += 4) { if (d[i] < 8) zero++; else if (d[i] > 247) full++; }
    out.frame0_alpha_zero_fraction = zero / (W * H); out.frame0_alpha_full_fraction = full / (W * H);
    out.overlayBarcodeFrame0 = readVideoBarcode(v, OC);
  }
  // 2. two <video> elements (base + alpha layer) played together: are they on the same frame?
  const pts = await loadPts('base_cfr_vp9.webm');
  stage.querySelectorAll('video,canvas').forEach(e => e.remove());
  const base = document.createElement('video'); const lay = document.createElement('video');
  for (const [el, src] of [[base, 'base_cfr_vp9.webm'], [lay, 'overlay_vp9alpha.webm']]) { el.muted = true; el.preload = 'auto'; el.src = MEDIA(src); stage.appendChild(el); }
  await Promise.all([waitEvent(base, 'canplaythrough'), waitEvent(lay, 'canplaythrough')]);
  const S = { vfc: 0, match: 0, mismatch: 0, offsets: {}, decodeFail: 0, captures: 0, captureMatch: 0, captureMismatch: [], captureFail: 0 };
  let done = false; const pend = [];
  const onVFC = () => {
    if (done) return;
    S.vfc++;
    const a = readVideoBarcode(base); const b = readVideoBarcode(lay, OC);
    if (a < 0 || b < 0) S.decodeFail++; else if (a === b) S.match++; else { S.mismatch++; S.offsets[b - a] = (S.offsets[b - a] || 0) + 1; }
    if (S.vfc % 10 === 5) pend.push(capture().then(c => { S.captures++; if (c.error || c.video < 0 || c.overlay < 0) S.captureFail++; else if (c.video === c.overlay) S.captureMatch++; else S.captureMismatch.push([c.video, c.overlay]); }));
    base.requestVideoFrameCallback(onVFC);
  };
  base.requestVideoFrameCallback(onVFC);
  const ended = waitEvent(base, 'ended', null, (pts[pts.length - 1] + 20) * 1000);
  await Promise.all([base.play(), lay.play()]);
  await ended; done = true; await Promise.all(pend);
  out.dualVideoSync = S;
  // 3. same, paused seeks (both elements set to the same currentTime)
  const P = { n: 0, match: 0, mism: [] };
  for (let i = 0; i < 30; i++) {
    const f = (i * 53 + 7) % (pts.length - 1); // never the last frame (see lastFrameSeek)
    const w1 = nextVFC(base); const w2 = nextVFC(lay);
    base.currentTime = pts[f]; lay.currentTime = pts[f];
    await Promise.all([w1, w2]);
    const a = readVideoBarcode(base); const b = readVideoBarcode(lay, OC);
    P.n++; if (a === b && a === f) P.match++; else P.mism.push([f, a, b]);
  }
  out.dualVideoSeek = P;
  return out;
}

async function testTrunc() {
  const out = {};
  for (const f of ['truncated/overlay_full.svg', 'truncated/overlay_trunc.svg']) {
    const img = new Image();
    const r = await new Promise(res => { img.onload = () => res('load'); img.onerror = () => res('error'); img.src = MEDIA(f); setTimeout(() => res('timeout'), 8000); });
    const txt = await (await fetch(MEDIA(f))).text();
    const doc = new DOMParser().parseFromString(txt, 'image/svg+xml');
    const err = doc.getElementsByTagName('parsererror').length;
    out[f] = { imgEvent: r, domParserError: err > 0, groups: doc.getElementsByTagName('g').length };
  }
  for (const f of ['overlay.vtt', 'truncated/overlay_trunc.vtt']) {
    const v = makeVideo(null);
    const tr = document.createElement('track'); tr.kind = 'metadata'; tr.src = MEDIA(f); tr.default = true; v.appendChild(tr);
    v.src = MEDIA('base_cfr_vp9.webm'); v.textTracks[0].mode = 'hidden';
    const r = await waitEvent(tr, 'load', 'error', 10000);
    const cues = v.textTracks[0].cues; let lastOk = null;
    if (cues && cues.length) { try { JSON.parse(cues[cues.length - 1].text); lastOk = true; } catch (e) { lastOk = false; } }
    out[f] = { load: r, cues: cues ? cues.length : null, lastCuePayloadParses: lastOk };
  }
  return out;
}

async function testWebCodecs() {
  const out = { VideoEncoder: typeof VideoEncoder !== 'undefined', enc: {}, dec: {} };
  if (!out.VideoEncoder) return out;
  const codecs = { vp8: 'vp8', vp9: 'vp09.00.31.08', av1: 'av01.0.08M.08', h264: 'avc1.64002A', hevc: 'hvc1.1.6.L120.B0' };
  for (const [k, c] of Object.entries(codecs)) {
    for (const hw of ['prefer-hardware', 'prefer-software']) {
      try { const r = await VideoEncoder.isConfigSupported({ codec: c, width: 1920, height: 1080, framerate: 30, bitrate: 8e6, hardwareAcceleration: hw }); out.enc[`${k}/${hw}`] = r.supported; }
      catch (e) { out.enc[`${k}/${hw}`] = String(e).slice(0, 80); }
      try { const r = await VideoDecoder.isConfigSupported({ codec: c, codedWidth: 1920, codedHeight: 1080, hardwareAcceleration: hw }); out.dec[`${k}/${hw}`] = r.supported; }
      catch (e) { out.dec[`${k}/${hw}`] = String(e).slice(0, 80); }
    }
  }
  return out;
}

// label layout in the browser with real font metrics: naive offsets vs placeLabels
async function testLayout() {
  await loadOverlay();
  const c = document.createElement('canvas').getContext('2d'); c.font = '12px Arial';
  const measure = t => ({ w: Math.ceil(c.measureText(t).width) + 2, h: 13 });
  const res = { frames: 0, naive: { labelLabel: 0, labelMarker: 0, outOfBounds: 0 }, placed: { labelLabel: 0, labelMarker: 0, outOfBounds: 0, lane: 0, hidden: 0 }, deterministic: true };
  const fr = [...OV.frames.keys()].slice(0, 60);
  for (const f of fr) {
    const rec = OV.frames.get(f); if (!rec.ci) continue;
    res.frames++;
    const items = rec.ci.map((id, i) => ({ id, x: rec.cxy[2 * i], y: rec.cxy[2 * i + 1], text: String(id) }));
    const markers = items.map(it => ({ x: it.x - 6, y: it.y - 6, w: 12, h: 12 }));
    const nb = items.map(it => ({ x: it.x + 8, y: it.y - 21, ...measure(it.text) }));
    const no = countOverlaps(nb, markers); res.naive.labelLabel += no.labelLabel; res.naive.labelMarker += no.labelMarker;
    res.naive.outOfBounds += nb.filter(b => b.x < 0 || b.y < 0 || b.x + b.w > W || b.y + b.h > 670).length;
    const p1 = placeLabels(items, measure, { w: W, h: 670 }); const p2 = placeLabels(items, measure, { w: W, h: 670 });
    if (JSON.stringify(p1) !== JSON.stringify(p2)) res.deterministic = false;
    const po = countOverlaps(p1.placed, markers); res.placed.labelLabel += po.labelLabel; res.placed.labelMarker += po.labelMarker;
    res.placed.outOfBounds += p1.placed.filter(b => b.x < 0 || b.y < 0 || b.x + b.w > W || b.y + b.h > 670).length;
    res.placed.lane += p1.placed.filter(b => b.lane).length; res.placed.hidden += p1.hidden.length;
  }
  return res;
}

// UI-side render cost (bench mode only; timing is reported by the bench runner, not in functional runs)
async function benchDraw() {
  await loadOverlay();
  const { ctx } = makeOverlayCanvas();
  const svgNS = 'http://www.w3.org/2000/svg';
  const out = {};
  const keys = [...OV.frames.keys()];
  const reps = Number(Q.get('reps') || 3);
  for (const [name, fn] of [
    ['canvas_full_layout', f => drawOverlay(ctx, f)],
    ['canvas_full_naive_labels', f => drawOverlay(ctx, f, { layout: 'naive' })],
    ['canvas_no_labels', f => drawOverlay(ctx, f, { labels: false })],
  ]) {
    const t = [];
    for (let r = 0; r < reps; r++) for (const f of keys) { const t0 = performance.now(); fn(f); ctx.getImageData(0, 0, 1, 1); t.push(performance.now() - t0); }
    t.sort((a, b) => a - b);
    out[name] = { n: t.length, median_ms: t[t.length >> 1], p95_ms: t[Math.floor(t.length * 0.95)], max_ms: t[t.length - 1] };
  }
  // SVG DOM: replace the content of one <g> per frame from a pre-rendered string (overlay_single.svg groups)
  const txt = await (await fetch(MEDIA('overlay_single.svg'))).text();
  const groups = [...txt.matchAll(/<g id="f(\d+)"[^>]*>(.*?)<\/g>/gs)].map(m => m[2]);
  const svg = document.createElementNS(svgNS, 'svg'); svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.style.cssText = 'position:absolute;left:0;top:0;width:640px;height:360px'; stage.appendChild(svg);
  const g = document.createElementNS(svgNS, 'g'); svg.appendChild(g);
  const t = [];
  for (let r = 0; r < reps; r++) for (const s of groups) {
    const t0 = performance.now(); g.innerHTML = s; await new Promise(rr => requestAnimationFrame(rr)); t.push(performance.now() - t0);
  }
  t.sort((a, b) => a - b);
  out.svg_dom_innerHTML_plus_raf = { n: t.length, median_ms: t[t.length >> 1], p95_ms: t[Math.floor(t.length * 0.95)], note: 'includes waiting for the next rAF (~16.7 ms at 60 Hz floor)' };
  return out;
}

(async () => {
  try {
    if (TESTS.includes('caps')) { status('caps'); R.results.caps = await testCaps(); }
    if (TESTS.includes('play')) {
      R.results.play = {};
      for (const f of FILES) { status('play ' + f); R.results.play[f] = await playAlign(f, 1, { capture: true }); }
      status('play 2x vp9'); R.results.play['base_cfr_vp9.webm@2x'] = await playAlign('base_cfr_vp9.webm', 2, { capture: true });
      for (const f of ['base_cfr_vp9.webm', 'base_vfr_h264.mp4']) { status('play canvas-composite ' + f); R.results.play[f + '@canvasComposite'] = await playAlign(f, 1, { capture: true, canvasComposite: true }); }
    }
    if (TESTS.includes('seek')) { R.results.seek = {}; for (const f of FILES) { status('seek ' + f); R.results.seek[f] = await seekAlign(f); } }
    if (TESTS.includes('lastframe')) { R.results.lastframe = {}; for (const f of FILES) { status('lastframe ' + f); R.results.lastframe[f] = await lastFrameSeek(f); } }
    if (TESTS.includes('vtt')) {
      status('vtt'); R.results.vtt = { cfr: await vttAlign('base_cfr_vp9.webm', 'overlay.vtt'), cfr_halfshift: await vttAlign('base_cfr_vp9.webm', 'overlay_half.vtt'), vfr: await vttAlign('base_vfr_vp9.webm', 'overlay_vfr.vtt') };
    }
    if (TESTS.includes('inband')) { status('inband'); R.results.inband = await testInband(); }
    if (TESTS.includes('alpha')) { status('alpha'); R.results.alpha = await testAlpha(); }
    if (TESTS.includes('trunc')) { status('trunc'); R.results.trunc = await testTrunc(); }
    if (TESTS.includes('webcodecs')) { status('webcodecs'); R.results.webcodecs = await testWebCodecs(); }
    if (TESTS.includes('layout')) { status('layout'); R.results.layout = await testLayout(); }
    if (TESTS.includes('drawbench')) { status('drawbench'); R.results.drawbench = await benchDraw(); }
  } catch (e) { R.error = String(e && e.stack || e); }
  status('done');
  await fetch('/result', { method: 'POST', body: JSON.stringify(R) });
})();
