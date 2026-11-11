// Shared page helpers: result posting, index-pattern decoding, content grid check.
'use strict';
const Q = new URLSearchParams(location.search);
const SERVER = Q.get('server') || location.origin;
const KEY = Q.get('key');

async function postResult(obj) {
  if (window.__harness) { window.__harness.post(KEY, JSON.stringify(obj)); return; } // Electron preload (IPC)
  try {
    await fetch(`${SERVER}/result?key=${encodeURIComponent(KEY)}`, { method: 'POST', mode: 'cors', headers: { 'Content-Type': 'text/plain' }, body: JSON.stringify(obj) });
  } catch (e) { console.error('post failed', e); }
}
let MANIFEST = null;
async function manifest() {
  if (!MANIFEST && window.__harness) MANIFEST = JSON.parse(await window.__harness.manifest());
  if (!MANIFEST) MANIFEST = await (await fetch(`${SERVER}/m/manifest.json`, { mode: 'cors' })).json();
  return MANIFEST;
}
function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }
function withTimeout(p, ms, label) { return Promise.race([p, sleep(ms).then(() => { throw new Error('timeout:' + label); })]); }

function luma(d, i) { return 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]; }

// img: ImageData of the full frame. Returns {idx, white, black}; idx = -1 if the reference blocks are unreadable.
function readIndex(img, block, nbits) {
  const { data, width } = img;
  const blockMean = (b) => {
    const x0 = b * block + block / 4, y0 = block / 4; let s = 0, n = 0;
    for (let y = y0; y < y0 + block / 2; y++) for (let x = x0; x < x0 + block / 2; x++) { s += luma(data, (y * width + x) * 4); n++; }
    return s / n;
  };
  const white = blockMean(0), black = blockMean(1);
  if (white - black < 100) return { idx: -1, white: Math.round(white), black: Math.round(black) };
  const thr = (white + black) / 2; let idx = 0;
  for (let b = 0; b < nbits; b++) idx = (idx << 1) | (blockMean(2 + b) > thr ? 1 : 0);
  return { idx, white: Math.round(white), black: Math.round(black) };
}

// Mean abs difference between the frame's block-mean luma grid and the expected grid (block x block cells),
// sampling every 2nd pixel in x and y.
function gridMad(img, block, expected) {
  const { data, width, height } = img; const gw = width / block, gh = height / block;
  if (!expected || expected.length !== gw * gh) return null;
  let tot = 0;
  for (let gy = 0; gy < gh; gy++) for (let gx = 0; gx < gw; gx++) {
    let s = 0;
    for (let y = gy * block; y < (gy + 1) * block; y += 2) for (let x = gx * block; x < (gx + 1) * block; x += 2) s += luma(data, (y * width + x) * 4);
    tot += Math.abs(s / (block * block / 4) - expected[gy * gw + gx]);
  }
  return +(tot / (gw * gh)).toFixed(2);
}

// 16x9 grid with floor cell bounds (same as make_extras.grid16), for arbitrary image sizes.
function grid16Mad(img, expected) {
  const { data, width: w, height: h } = img; let tot = 0;
  for (let i = 0; i < 9; i++) for (let j = 0; j < 16; j++) {
    const y0 = Math.floor(i * h / 9), y1 = Math.floor((i + 1) * h / 9), x0 = Math.floor(j * w / 16), x1 = Math.floor((j + 1) * w / 16);
    let s = 0, n = 0;
    for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) { s += luma(data, (y * w + x) * 4); n++; }
    tot += Math.abs(s / n - expected[i * 16 + j]);
  }
  return +(tot / 144).toFixed(2);
}

// Draws source into the canvas, returns {idx, white, black, mad}; throws SecurityError on a tainted canvas.
function frameCheck(ctx, source, M, w, h) {
  ctx.drawImage(source, 0, 0, w, h);
  const img = ctx.getImageData(0, 0, w, h);
  const r = readIndex(img, M.block, M.nbits);
  r.mad = r.idx >= 0 && r.idx < M.frames ? gridMad(img, M.block, M.grids[r.idx]) : null;
  return r;
}
