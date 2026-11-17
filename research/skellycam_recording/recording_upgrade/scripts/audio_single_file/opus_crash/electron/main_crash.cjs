// Crashed-file harness (2026-11-16). Serves crash_page.html, the UNCHANGED planned-player code
// ../../skellycam_playback/electron/player.js, and the test files (name -> path from the config) through the same
// protocol.handle scheme and hand-written single-range handler as ../../skellycam_playback/electron/main.cjs (copied).
// env CR_CFG = config json path, CR_OUT = result json path. Unset ELECTRON_RUN_AS_NODE before launching.
const { app, BrowserWindow, protocol } = require('electron');
const path = require('path'), fs = require('fs');

const cfg = JSON.parse(fs.readFileSync(process.env.CR_CFG, 'utf8'));
app.setPath('userData', path.join(cfg.scratch, 'userdata_e' + process.versions.electron.split('.')[0]));
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
app.commandLine.appendSwitch('disable-renderer-backgrounding');
protocol.registerSchemesAsPrivileged([{ scheme: 'skr', privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true, corsEnabled: true } }]);

const FILES = { 'crash_page.html': path.join(__dirname, 'crash_page.html'),
  'player.js': path.join(__dirname, '..', '..', 'skellycam_playback', 'electron', 'player.js') };
for (const f of cfg.files) FILES[f.name] = f.path;
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.wav': 'audio/wav', '.m4a': 'audio/mp4', '.mka': 'audio/webm' };
const fhCache = new Map();
async function fh(p) { let h = fhCache.get(p); if (!h) { h = await fs.promises.open(p, 'r'); fhCache.set(p, h); } return h; }
let requests = 0;

async function rangeHandler(req) {
  requests++;
  const p = FILES[decodeURIComponent(new URL(req.url).pathname.slice(1))];
  const base = { 'Accept-Ranges': 'bytes', 'Content-Type': (p && MIME[path.extname(p)]) || 'application/octet-stream', 'Cache-Control': 'no-store' };
  if (!p) return new Response('not found', { status: 404, headers: base });
  const size = fs.statSync(p).size;
  const rh = req.headers.get('range');
  const head = req.method === 'HEAD';
  const { Readable } = require('stream');
  if (!rh) {
    const h = { ...base, 'Content-Length': String(size) };
    return new Response(head ? null : Readable.toWeb(fs.createReadStream(p)), { status: 200, headers: h });
  }
  const m = /^bytes=(\d*)-(\d*)$/.exec(rh.trim());
  const unsat = () => new Response(null, { status: 416, headers: { ...base, 'Content-Range': `bytes */${size}` } });
  if (!m || (m[1] === '' && m[2] === '')) return unsat();
  let start, end;
  if (m[1] === '') { const n = Number(m[2]); if (n === 0) return unsat(); start = Math.max(0, size - n); end = size - 1; }
  else { start = Number(m[1]); end = m[2] === '' ? size - 1 : Math.min(Number(m[2]), size - 1); if (end < start) return unsat(); }
  if (start >= size) return unsat();
  const len = end - start + 1;
  const h = { ...base, 'Content-Range': `bytes ${start}-${end}/${size}`, 'Content-Length': String(len) };
  if (head) return new Response(null, { status: 206, headers: h });
  if (len <= (8 << 20)) {
    const buf = Buffer.allocUnsafe(len);
    const { bytesRead } = await (await fh(p)).read(buf, 0, len, start);
    return new Response(bytesRead === len ? buf : buf.subarray(0, bytesRead), { status: 206, headers: h });
  }
  return new Response(Readable.toWeb(fs.createReadStream(p, { start, end })), { status: 206, headers: h });
}

app.whenReady().then(async () => {
  protocol.handle('skr', rangeHandler);
  const win = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true, backgroundThrottling: false } });
  await win.loadURL('skr://media/crash_page.html');
  const out = { electron: process.versions.electron, chrome: process.versions.chrome, files: [] };
  for (const f of cfg.files) {
    let r;
    try { r = await win.webContents.executeJavaScript(`testFile(${JSON.stringify({ name: f.name, targets: f.targets, L: f.L })})`); }
    catch (e) { r = { error: String(e && e.message || e) }; }
    out.files.push(Object.assign({ name: f.name }, r));
    console.log(f.name, JSON.stringify(r).length);
  }
  out.requests = requests;
  fs.writeFileSync(process.env.CR_OUT, JSON.stringify(out));
  app.quit();
});
