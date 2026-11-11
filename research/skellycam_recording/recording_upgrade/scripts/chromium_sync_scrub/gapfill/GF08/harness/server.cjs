// Static HTTP server for the chromium_sync_scrub harness (Node built-ins only).
// Serves byte ranges (RFC 9110 Range: bytes=a-b, single range) so <video> can seek and the
// JPEG/WebCodecs paths can fetch individual samples by offset.
//   /harness/*  -> this folder (page + JS)
//   /media/*    -> MEDIA_ROOT (generated clips, never in the repo)
//   /corpus/*   -> CORPUS_ROOT (camera JPEGs, read only)
//   /vendor/mp4box/* -> MP4BOX_DIST (npm mp4box@2.4.1 dist folder, scratchpad)
//   POST /result     -> handler(resultJson)
//   POST /blob?name= -> saves raw body under MEDIA_ROOT/../blobs/<name>
//   GET  /metrics/start, /metrics/stop -> hooks (Electron main samples app.getAppMetrics)
'use strict';
const http = require('http');
const fs = require('fs');
const path = require('path');

const ROOTS = {
  harness: __dirname,
  media: process.env.CSS_MEDIA_ROOT || 'C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/chromium_sync_scrub',
  corpus: process.env.CSS_CORPUS_ROOT || 'C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus',
  vendor: process.env.CSS_MP4BOX_DIST || 'C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/chromium_sync_scrub/npm_mp4box/node_modules/mp4box/dist',
};
const TYPES = {
  '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.cjs': 'text/javascript',
  '.json': 'application/json', '.mp4': 'video/mp4', '.webm': 'video/webm', '.mkv': 'video/x-matroska',
  '.jpg': 'image/jpeg', '.mjpeg': 'application/octet-stream', '.map': 'application/json',
};

function resolve(urlPath) {
  const parts = urlPath.split('/').filter(Boolean).map(decodeURIComponent);
  if (parts.length < 1) return null;
  let root;
  if (parts[0] === 'harness') root = ROOTS.harness;
  else if (parts[0] === 'media') root = ROOTS.media;
  else if (parts[0] === 'corpus') root = ROOTS.corpus;
  else if (parts[0] === 'vendor' && parts[1] === 'mp4box') { root = ROOTS.vendor; parts.shift(); }
  else return null;
  const p = path.resolve(root, ...parts.slice(1));
  if (!p.startsWith(path.resolve(root))) return null;
  return p;
}

function serveFile(req, res, p) {
  fs.stat(p, (err, st) => {
    if (err || !st.isFile()) { res.writeHead(404); res.end('not found'); return; }
    const type = TYPES[path.extname(p).toLowerCase()] || 'application/octet-stream';
    const headers = { 'Content-Type': type, 'Accept-Ranges': 'bytes', 'Cache-Control': 'no-store',
      'Access-Control-Allow-Origin': '*' };
    const range = req.headers.range;
    if (range) {
      const m = /^bytes=(\d*)-(\d*)$/.exec(range.trim());
      if (!m) { res.writeHead(416, { 'Content-Range': `bytes */${st.size}` }); res.end(); return; }
      let start = m[1] === '' ? st.size - Number(m[2]) : Number(m[1]);
      let end = m[1] === '' ? st.size - 1 : (m[2] === '' ? st.size - 1 : Math.min(Number(m[2]), st.size - 1));
      if (start > end || start >= st.size) { res.writeHead(416, { 'Content-Range': `bytes */${st.size}` }); res.end(); return; }
      res.writeHead(206, { ...headers, 'Content-Range': `bytes ${start}-${end}/${st.size}`, 'Content-Length': end - start + 1 });
      if (req.method === 'HEAD') { res.end(); return; }
      fs.createReadStream(p, { start, end }).pipe(res);
    } else {
      res.writeHead(200, { ...headers, 'Content-Length': st.size });
      if (req.method === 'HEAD') { res.end(); return; }
      fs.createReadStream(p).pipe(res);
    }
  });
}

function readBody(req) {
  return new Promise((ok) => { const c = []; req.on('data', (d) => c.push(d)); req.on('end', () => ok(Buffer.concat(c))); });
}

function start({ onResult, onMetrics, onLog, configs } = {}) {
  const srv = http.createServer(async (req, res) => {
    const u = new URL(req.url, 'http://x');
    try {
      if (req.method === 'POST' && u.pathname === '/result') {
        const body = await readBody(req);
        res.writeHead(200); res.end('ok');
        if (onResult) onResult(JSON.parse(body.toString('utf8')));
        return;
      }
      if (req.method === 'POST' && u.pathname === '/log') {
        const body = await readBody(req); res.writeHead(200); res.end('ok');
        if (onLog) onLog(body.toString('utf8')); else console.log('[page]', body.toString('utf8'));
        return;
      }
      if (req.method === 'POST' && u.pathname === '/blob') {
        const name = path.basename(u.searchParams.get('name') || 'blob.bin');
        const dir = path.join(ROOTS.media, 'blobs');
        fs.mkdirSync(dir, { recursive: true });
        fs.writeFileSync(path.join(dir, name), await readBody(req));
        res.writeHead(200); res.end('ok'); return;
      }
      if (u.pathname === '/configs') { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(configs || '[]'); return; }
      if (u.pathname.startsWith('/metrics/')) {
        const r = onMetrics ? await onMetrics(u.pathname.slice(9)) : null;
        res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(r)); return;
      }
      const p = resolve(u.pathname);
      if (!p) { res.writeHead(404); res.end('no route'); return; }
      serveFile(req, res, p);
    } catch (e) { res.writeHead(500); res.end(String(e)); }
  });
  return new Promise((ok) => srv.listen(0, '127.0.0.1', () => ok({ server: srv, port: srv.address().port })));
}

module.exports = { start, ROOTS };
