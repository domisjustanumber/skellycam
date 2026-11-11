// Electron harness for the overlay (G3) functional tests. No npm dependencies (node built-ins only).
//
// Usage (from repo root):
//   <electron.exe> research/skellycam_recording/recording_upgrade/scripts/overlays/electron_harness \
//       --media=C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/overlays/media \
//       --out=research/skellycam_recording/recording_upgrade/results/overlays/electron_<ver>.json \
//       [--tests=caps,play,seek,vtt,inband,alpha,trunc,webcodecs,layout] [--mode=functional|bench]
//
// The page is served over http://127.0.0.1 (same origin as the media, so canvas reads are not tainted, and
// Range requests make seeking work). POST /capture grabs the composited window (webContents.capturePage) and
// decodes the two barcodes (video strip + overlay strip) from the screen pixels. POST /result writes the JSON
// and quits.
const { app, BrowserWindow, screen } = require('electron');
const http = require('http');
const fs = require('fs');
const path = require('path');

const arg = (k, d) => { const a = process.argv.find(x => x.startsWith(`--${k}=`)); return a ? a.slice(k.length + 3) : d; };
const MEDIA = arg('media', 'C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/overlays/media');
const OUT = path.resolve(arg('out', 'electron_result.json'));
const TESTS = arg('tests', 'caps,play,seek,vtt,inband,alpha,trunc,webcodecs,layout');
const MODE = arg('mode', 'functional');
const FILESARG = arg('files', '');
const EXTRA = arg('query', '');
const MAXMIN = Number(arg('timeout_min', '20'));

app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
app.commandLine.appendSwitch('disable-renderer-backgrounding');
app.commandLine.appendSwitch('disable-background-timer-throttling');
app.commandLine.appendSwitch('disable-backgrounding-occluded-windows');
app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');

const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.webm': 'video/webm', '.mp4': 'video/mp4', '.mkv': 'video/x-matroska',
  '.mov': 'video/quicktime', '.vtt': 'text/vtt', '.svg': 'image/svg+xml', '.json': 'application/json', '.jsonl': 'application/json',
  '.ass': 'text/plain', '.png': 'image/png' };

let win = null;

function serveFile(req, res, file) {
  fs.stat(file, (err, st) => {
    if (err || !st.isFile()) { res.writeHead(404); res.end(); return; }
    const type = TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream';
    const range = req.headers.range;
    if (range) {
      const m = /bytes=(\d*)-(\d*)/.exec(range);
      let start = m[1] ? Number(m[1]) : 0; let end = m[2] ? Number(m[2]) : st.size - 1;
      if (!m[1] && m[2]) { start = st.size - Number(m[2]); end = st.size - 1; }
      end = Math.min(end, st.size - 1);
      res.writeHead(206, { 'Content-Type': type, 'Content-Range': `bytes ${start}-${end}/${st.size}`, 'Accept-Ranges': 'bytes', 'Content-Length': end - start + 1 });
      fs.createReadStream(file, { start, end }).pipe(res);
    } else {
      res.writeHead(200, { 'Content-Type': type, 'Content-Length': st.size, 'Accept-Ranges': 'bytes' });
      fs.createReadStream(file).pipe(res);
    }
  });
}

function readBody(req) { return new Promise(r => { const b = []; req.on('data', c => b.push(c)); req.on('end', () => r(Buffer.concat(b).toString())); }); }

function decodeStrip(bmp, size, sf, rect, srcW, centres) {
  // rect: CSS px rect of the element showing a srcW-wide source; centres: [[sx, sy]...] in source px
  const scale = rect.w / srcW; const bits = [];
  for (const [sx, sy] of centres) {
    const x = Math.round((rect.x + sx * scale) * sf); const y = Math.round((rect.y + sy * scale) * sf);
    if (x < 0 || y < 0 || x >= size.width || y >= size.height) return -2;
    const o = (y * size.width + x) * 4; // BGRA
    const luma = 0.114 * bmp[o] + 0.587 * bmp[o + 1] + 0.299 * bmp[o + 2];
    bits.push(luma > 128 ? 1 : 0);
  }
  let idx = 0; for (let k = 0; k < 12; k++) idx |= bits[k] << k;
  let chk = 0; for (let k = 0; k < 4; k++) chk |= bits[12 + k] << k;
  let pc = 0; for (let k = 0; k < 12; k++) pc += (idx >> k) & 1;
  return (pc & 15) === chk ? idx : -1;
}

const VIDEO_CENTRES = Array.from({ length: 16 }, (_, k) => [k * 80 + 40, 700]);
const OVERLAY_CENTRES = Array.from({ length: 16 }, (_, k) => [k * 40 + 20, 80]);

const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, 'http://x');
  if (req.method === 'POST' && u.pathname === '/capture') {
    const body = JSON.parse(await readBody(req));
    try {
      const img = await win.webContents.capturePage();
      const size = img.getSize(); const bmp = img.toBitmap();
      const sf = size.width / body.viewportW;
      const out = { sf, video: decodeStrip(bmp, size, sf, body.videoRect, 1280, VIDEO_CENTRES),
        overlay: decodeStrip(bmp, size, sf, body.overlayRect, 1280, OVERLAY_CENTRES) };
      if (body.save) fs.writeFileSync(body.save, img.toPNG());
      res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(out));
    } catch (e) { res.writeHead(200); res.end(JSON.stringify({ error: String(e) })); }
    return;
  }
  if (req.method === 'POST' && u.pathname === '/result') {
    const body = await readBody(req);
    fs.mkdirSync(path.dirname(OUT), { recursive: true });
    const obj = JSON.parse(body);
    obj.env = { electron: process.versions.electron, chrome: process.versions.chrome, node: process.versions.node,
      scaleFactor: screen.getPrimaryDisplay().scaleFactor, gpuFeatureStatus: app.getGPUFeatureStatus() };
    try { obj.env.gpuInfo = await app.getGPUInfo('basic'); } catch (e) { obj.env.gpuInfo = String(e); }
    fs.writeFileSync(OUT, JSON.stringify(obj, null, 1));
    res.writeHead(200); res.end('ok');
    console.log('wrote', OUT);
    setTimeout(() => app.quit(), 200);
    return;
  }
  if (req.method === 'POST' && u.pathname === '/log') { console.log('[page]', await readBody(req)); res.end('ok'); return; }
  if (u.pathname.startsWith('/media/')) return serveFile(req, res, path.join(MEDIA, decodeURIComponent(u.pathname.slice(7))));
  if (u.pathname.startsWith('/app/')) return serveFile(req, res, path.join(__dirname, decodeURIComponent(u.pathname.slice(5))));
  res.writeHead(404); res.end();
});

app.whenReady().then(() => {
  server.listen(0, '127.0.0.1', () => {
    const port = server.address().port;
    win = new BrowserWindow({ width: 1360, height: 900, x: 0, y: 0, show: true, useContentSize: true,
      webPreferences: { backgroundThrottling: false } });
    win.webContents.setZoomFactor(1);
    win.loadURL(`http://127.0.0.1:${port}/app/harness.html?tests=${encodeURIComponent(TESTS)}&mode=${MODE}&files=${encodeURIComponent(FILESARG)}&${EXTRA}`);
    win.webContents.on('console-message', (...a) => { const m = a.length > 2 ? a[2] : (a[0] && a[0].message); if (m) console.log('[console]', m); });
  });
  setTimeout(() => { console.error('TIMEOUT'); fs.writeFileSync(OUT, JSON.stringify({ error: 'timeout' })); app.exit(2); }, MAXMIN * 60 * 1000);
});
app.on('window-all-closed', () => app.quit());
