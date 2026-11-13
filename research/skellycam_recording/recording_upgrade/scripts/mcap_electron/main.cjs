// MCAP-in-Electron desk test (2026-11-13). Page loads from file://, like skellycam-ui's packaged build.
// Files are served by protocol.handle on skr://media/<name> with the single-range handler of the range_transport
// study (scripts/range_transport/electron/main.cjs), which that study recommended for the player.
// The renderer has nodeIntegration only so it can require @mcap/core from MCAP_NM without a bundler (test shortcut).
// Env: MCAP_MEDIA (dir with the media), MCAP_NM (node_modules with @mcap/core), MCAP_OUT (result json),
//      MCAP_TESTS (comma list, see page.js). Unset ELECTRON_RUN_AS_NODE before launching.
const { app, BrowserWindow, protocol } = require('electron');
const path = require('path'), fs = require('fs');

const MEDIA = process.env.MCAP_MEDIA;
app.setPath('userData', path.join(MEDIA, 'userdata'));
app.commandLine.appendSwitch('disable-renderer-backgrounding');
protocol.registerSchemesAsPrivileged([{ scheme: 'skr', privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true, corsEnabled: true } }]);

const counts = { requests: 0 };
const fhCache = new Map();
async function fh(p) { let h = fhCache.get(p); if (!h) { h = await fs.promises.open(p, 'r'); fhCache.set(p, h); } return h; }

async function rangeHandler(req) {
  counts.requests++;
  const name = decodeURIComponent(new URL(req.url).pathname.slice(1));
  const base = { 'Accept-Ranges': 'bytes', 'Content-Type': 'application/octet-stream', 'Access-Control-Allow-Origin': '*',
                 'Access-Control-Expose-Headers': 'Content-Range, Content-Length, Accept-Ranges', 'Cache-Control': 'no-store' };
  if (name.includes('/') || name.includes('\\') || name.startsWith('.')) return new Response('bad name', { status: 404, headers: base });
  const p = path.join(MEDIA, name);
  let size;
  try { size = (await fs.promises.stat(p)).size; } catch { return new Response('not found', { status: 404, headers: base }); }
  const rh = req.headers.get('range');
  if (!rh) return new Response(req.method === 'HEAD' ? null : await fs.promises.readFile(p), { status: 200, headers: { ...base, 'Content-Length': String(size) } });
  const m = /^bytes=(\d+)-(\d*)$/.exec(rh.trim());   // the reader only sends bytes=a-b
  const start = m ? Number(m[1]) : NaN, end = m ? (m[2] === '' ? size - 1 : Math.min(Number(m[2]), size - 1)) : NaN;
  if (!m || start >= size || end < start) return new Response(null, { status: 416, headers: { ...base, 'Content-Range': `bytes */${size}` } });
  const len = end - start + 1;
  const h = { ...base, 'Content-Range': `bytes ${start}-${end}/${size}`, 'Content-Length': String(len) };
  if (req.method === 'HEAD') return new Response(null, { status: 206, headers: h });
  const buf = Buffer.allocUnsafe(len);
  const { bytesRead } = await (await fh(p)).read(buf, 0, len, start);
  return new Response(bytesRead === len ? buf : buf.subarray(0, bytesRead), { status: 206, headers: h });
}

app.whenReady().then(async () => {
  protocol.handle('skr', rangeHandler);
  const win = new BrowserWindow({ show: false, webPreferences: { nodeIntegration: true, contextIsolation: false, backgroundThrottling: false } });
  win.webContents.on('console-message', e => console.log('[page]', e.message));
  await win.loadFile(path.join(__dirname, 'page.html'));
  const cfg = { media: MEDIA, nm: process.env.MCAP_NM, tests: (process.env.MCAP_TESTS || 'all').split(',') };
  const res = { electron: process.versions.electron, chrome: process.versions.chrome, started: new Date().toISOString() };
  try { Object.assign(res, await win.webContents.executeJavaScript(`runAll(${JSON.stringify(cfg)})`)); }
  catch (e) { res.error = String(e && e.stack || e); }
  res.handler_requests = counts.requests;
  res.finished = new Date().toISOString();
  fs.writeFileSync(process.env.MCAP_OUT, JSON.stringify(res, null, 1));
  for (const h of fhCache.values()) await h.close();
  app.quit();
});
