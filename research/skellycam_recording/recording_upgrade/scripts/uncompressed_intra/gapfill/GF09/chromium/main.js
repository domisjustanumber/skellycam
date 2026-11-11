// GF09 Chromium check (functional, NO timing): NVENC lossless H.264 / HEVC files in Electron.
// Adapted copy of scripts/chromium_codecs/harness (server.js Range logic, tasks.js mediaCollector, electron_main.js
// DevTools Media-domain decoder names). The shared harness is not modified.
// Usage (Git Bash):  env -u ELECTRON_RUN_AS_NODE <electron.exe> main.js --out <result.json>
// Media: <MEDIA>/chromium/manifest.json from prep_chromium.py.
'use strict';
const { app, BrowserWindow } = require('electron');
const http = require('http');
const fs = require('fs');
const path = require('path');

const argv = process.argv;
const arg = (n, d) => { const i = argv.indexOf(n); return i >= 0 ? argv[i + 1] : d; };
const OUT = arg('--out');
const MEDIA = 'C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/uncompressed_intra/gapfill/GF09/chromium';
const HARNESS = __dirname;
app.setPath('userData', path.join('C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step3/GF09', `electron-userdata-${process.versions.electron}`));
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
app.commandLine.appendSwitch('disable-backgrounding-occluded-windows');
app.commandLine.appendSwitch('disable-renderer-backgrounding');
app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');

const TYPES = { '.mp4': 'video/mp4', '.mkv': 'video/x-matroska', '.json': 'application/json', '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.nv12': 'application/octet-stream' };
function parseRange(header, size) { // copied from chromium_codecs/harness/server.js
  const m = /^bytes=(\d*)-(\d*)$/.exec(header || '');
  if (!m) return null;
  let start, end;
  if (m[1] === '') { const n = parseInt(m[2], 10); start = Math.max(0, size - n); end = size - 1; }
  else { start = parseInt(m[1], 10); end = m[2] === '' ? size - 1 : Math.min(parseInt(m[2], 10), size - 1); }
  if (isNaN(start) || start > end || start >= size) return 'unsatisfiable';
  return { start, end };
}
function startServer() {
  const results = new Map(); const waiters = new Map();
  const server = http.createServer((req, res) => {
    const u = new URL(req.url, 'http://x');
    const cors = { 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store' };
    if (req.method === 'POST' && u.pathname === '/result') {
      let body = ''; req.on('data', (c) => (body += c));
      req.on('end', () => {
        const key = u.searchParams.get('key'); let val;
        try { val = JSON.parse(body); } catch (e) { val = { parseError: String(e) }; }
        results.set(key, val); const w = waiters.get(key); if (w) { waiters.delete(key); w(val); }
        res.writeHead(200, cors); res.end('ok');
      });
      return;
    }
    const p = decodeURIComponent(u.pathname);
    let file;
    if (p.startsWith('/m/')) file = path.join(MEDIA, p.slice(3));
    else if (p.startsWith('/h/')) file = path.join(HARNESS, p.slice(3));
    else { res.writeHead(404, cors); return res.end(); }
    let st; try { st = fs.statSync(file); } catch { res.writeHead(404, cors); return res.end(); }
    const hdr = { ...cors, 'Content-Type': TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream', 'Accept-Ranges': 'bytes' };
    const r = req.headers.range ? parseRange(req.headers.range, st.size) : null;
    if (r === 'unsatisfiable') { res.writeHead(416, { ...hdr, 'Content-Range': `bytes */${st.size}` }); return res.end(); }
    if (r) {
      res.writeHead(206, { ...hdr, 'Content-Range': `bytes ${r.start}-${r.end}/${st.size}`, 'Content-Length': r.end - r.start + 1 });
      return fs.createReadStream(file, { start: r.start, end: r.end }).on('error', () => res.destroy()).pipe(res);
    }
    res.writeHead(200, { ...hdr, 'Content-Length': st.size });
    fs.createReadStream(file).on('error', () => res.destroy()).pipe(res);
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve({
    port: server.address().port,
    waitResult(key, ms) {
      if (results.has(key)) return Promise.resolve(results.get(key));
      return new Promise((res) => { const t = setTimeout(() => { waiters.delete(key); res({ timeout: true }); }, ms); waiters.set(key, (v) => { clearTimeout(t); res(v); }); });
    },
  })));
}
function mediaCollector() { // copied from chromium_codecs/harness/tasks.js
  let players = {};
  return {
    reset() { players = {}; },
    feed(method, p) {
      if (!method || !method.startsWith('Media.')) return;
      const id = p.playerId; if (id === undefined) return;
      const pl = (players[id] ||= { props: {}, errors: [], messages: [] });
      if (method === 'Media.playerPropertiesChanged') for (const pr of p.properties) pl.props[pr.name] = pr.value;
      else if (method === 'Media.playerErrorsRaised') for (const e of p.errors) pl.errors.push(e.errorType + ' ' + e.code + (e.data ? ' ' + JSON.stringify(e.data).slice(0, 300) : ''));
      else if (method === 'Media.playerMessagesLogged') for (const m of p.messages) if (m.level === 'error' || m.level === 'warning') pl.messages.push(m.level + ': ' + String(m.message).slice(0, 300));
    },
    snapshot() {
      const keep = ['kVideoDecoderName', 'kIsPlatformVideoDecoder', 'kResolution', 'kVideoTracks', 'kFrameUrl', 'kIsRangeHeaderSupported'];
      const out = {};
      for (const [id, pl] of Object.entries(players)) {
        const props = {}; for (const k of keep) if (k in pl.props) props[k] = pl.props[k];
        if (props.kVideoTracks) props.kVideoTracks = JSON.stringify(props.kVideoTracks).slice(0, 400);
        out[id] = { props, errors: pl.errors.slice(0, 5), messages: pl.messages.slice(0, 5) };
      }
      return out;
    },
  };
}

app.whenReady().then(async () => {
  const S = await startServer();
  const server = `http://127.0.0.1:${S.port}`;
  const M = JSON.parse(fs.readFileSync(path.join(MEDIA, 'manifest.json'), 'utf8'));
  const win = new BrowserWindow({ show: false, width: 820, height: 620, webPreferences: { backgroundThrottling: false } });
  win.showInactive();
  const media = mediaCollector();
  await win.loadURL('about:blank');
  win.webContents.debugger.attach('1.3');
  win.webContents.debugger.on('message', (_e, method, params) => media.feed(method, params));
  await win.webContents.debugger.sendCommand('Media.enable');
  const out = { runner: 'electron', versions: { electron: process.versions.electron, chrome: process.versions.chrome }, manifest: M, results: {} };
  try { const g = await app.getGPUInfo('basic'); out.gpu = (g.gpuDevice || []).map((d) => ({ vendorId: d.vendorId, deviceId: d.deviceId, active: d.active, driverVersion: d.driverVersion })); } catch (e) { out.gpuError = String(e); }
  out.featureStatus = app.getGPUFeatureStatus();
  const tasks = [];
  for (const c of M.clips) {
    tasks.push({ key: `${c.id}|caps`, q: { mode: 'caps', clip: c.id } });
    tasks.push({ key: `${c.id}|video-mkv`, q: { mode: 'video', clip: c.id, file: c.mkv.file } });
    tasks.push({ key: `${c.id}|video-mp4`, q: { mode: 'video', clip: c.id, file: c.mp4.file } });
    for (const hw of ['no-preference', 'prefer-hardware', 'prefer-software']) tasks.push({ key: `${c.id}|wc|${hw}`, q: { mode: 'wc', clip: c.id, hw } });
  }
  for (const t of tasks) {
    media.reset();
    const qs = new URLSearchParams({ ...t.q, key: t.key, server }).toString();
    try { await win.webContents.loadURL(`${server}/h/page.html?${qs}`); } catch (e) { if (!String(e).includes('ERR_ABORTED')) { out.results[t.key] = { navigateError: String(e) }; continue; } }
    const r = await S.waitResult(t.key, 60000);
    await new Promise((res) => setTimeout(res, 500));
    r.media = media.snapshot();
    out.results[t.key] = r;
    console.log(t.key, JSON.stringify({ ended: r.ended, error: r.error, readback: r.readback && r.readback.map((x) => x.exact), wcErr: r.errors, dec: Object.values(r.media).map((m) => m.props.kVideoDecoderName) }).slice(0, 300));
  }
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(out, null, 1));
  app.quit();
});
