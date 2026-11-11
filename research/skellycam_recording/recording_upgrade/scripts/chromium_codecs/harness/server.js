// Local HTTP server for the Chromium codec tests.
//   /r/<path>   media file from MEDIA dir, WITH HTTP Range support (206, Accept-Ranges: bytes)
//   /n/<path>   media file, NO Range support (always 200 full body, no Accept-Ranges)
//   /h/<path>   harness pages (this folder)
//   /m/manifest.json  clip manifest
//   POST /result?key=K   page posts its JSON result (CORS open, text/plain body)
// Every request is logged (method, path, Range header, status) so seeking behaviour can be audited.
'use strict';
const http = require('http');
const fs = require('fs');
const path = require('path');

const MEDIA = 'C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/chromium_codecs';
const HARNESS = __dirname;
const TYPES = {
  '.mp4': 'video/mp4', '.webm': 'video/webm', '.mkv': 'video/x-matroska', '.mov': 'video/quicktime',
  '.avi': 'video/x-msvideo', '.ogv': 'video/ogg', '.ivf': 'application/octet-stream', '.h264': 'application/octet-stream',
  '.hevc': 'application/octet-stream', '.jpg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp',
  '.avif': 'image/avif', '.jxl': 'image/jxl', '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json',
};

function contentType(p) { return TYPES[path.extname(p).toLowerCase()] || 'application/octet-stream'; }

// Shared Range logic (also used by the Electron custom-protocol handler).
function parseRange(header, size) {
  const m = /^bytes=(\d*)-(\d*)$/.exec(header || '');
  if (!m) return null;
  let start, end;
  if (m[1] === '') { const n = parseInt(m[2], 10); start = Math.max(0, size - n); end = size - 1; }
  else { start = parseInt(m[1], 10); end = m[2] === '' ? size - 1 : Math.min(parseInt(m[2], 10), size - 1); }
  if (isNaN(start) || start > end || start >= size) return 'unsatisfiable';
  return { start, end };
}

function start(port = 0) {
  const results = new Map();
  const waiters = new Map();
  const reqlog = [];
  const server = http.createServer((req, res) => {
    const u = new URL(req.url, 'http://x');
    const cors = { 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store' };
    if (req.method === 'OPTIONS') { res.writeHead(204, { ...cors, 'Access-Control-Allow-Headers': '*' }); return res.end(); }
    if (req.method === 'POST' && u.pathname === '/result') {
      let body = '';
      req.on('data', (c) => (body += c));
      req.on('end', () => {
        const key = u.searchParams.get('key');
        let val; try { val = JSON.parse(body); } catch (e) { val = { parseError: String(e), body: body.slice(0, 500) }; }
        results.set(key, val);
        const w = waiters.get(key); if (w) { waiters.delete(key); w(val); }
        res.writeHead(200, cors); res.end('ok');
      });
      return;
    }
    let file, ranged = false;
    const p = decodeURIComponent(u.pathname);
    if (p.startsWith('/r/')) { file = path.join(MEDIA, p.slice(3)); ranged = true; }
    else if (p.startsWith('/n/')) { file = path.join(MEDIA, p.slice(3)); }
    else if (p.startsWith('/h/')) { file = path.join(HARNESS, p.slice(3)); ranged = true; }
    else if (p === '/m/manifest.json') { file = path.join(MEDIA, 'manifest.json'); }
    else { res.writeHead(404, cors); return res.end(); }
    let st; try { st = fs.statSync(file); } catch { res.writeHead(404, cors); return res.end(); }
    const size = st.size;
    const hdr = { ...cors, 'Content-Type': contentType(file) };
    const entry = { t: Date.now(), path: p, range: req.headers.range || null, status: 0 };
    reqlog.push(entry);
    if (ranged) {
      hdr['Accept-Ranges'] = 'bytes';
      const r = req.headers.range ? parseRange(req.headers.range, size) : null;
      if (r === 'unsatisfiable') { entry.status = 416; res.writeHead(416, { ...hdr, 'Content-Range': `bytes */${size}` }); return res.end(); }
      if (r) {
        entry.status = 206;
        res.writeHead(206, { ...hdr, 'Content-Range': `bytes ${r.start}-${r.end}/${size}`, 'Content-Length': r.end - r.start + 1 });
        if (req.method === 'HEAD') return res.end();
        return fs.createReadStream(file, { start: r.start, end: r.end }).on('error', () => res.destroy()).pipe(res);
      }
    }
    entry.status = 200;
    res.writeHead(200, { ...hdr, 'Content-Length': size });
    if (req.method === 'HEAD') return res.end();
    fs.createReadStream(file).on('error', () => res.destroy()).pipe(res);
  });
  return new Promise((resolve) => {
    server.listen(port, '127.0.0.1', () => {
      const actual = server.address().port;
      resolve({
        port: actual, server, reqlog, results,
        waitResult(key, timeoutMs) {
          if (results.has(key)) return Promise.resolve(results.get(key));
          return new Promise((res) => {
            const t = setTimeout(() => { waiters.delete(key); res({ timeout: true, timeoutMs }); }, timeoutMs);
            waiters.set(key, (v) => { clearTimeout(t); res(v); });
          });
        },
        deliver(key, val) {
          results.set(key, val);
          const w = waiters.get(key); if (w) { waiters.delete(key); w(val); }
        },
        close() { server.closeAllConnections?.(); server.close(); },
      });
    });
  });
}

module.exports = { start, parseRange, contentType, MEDIA, HARNESS };
