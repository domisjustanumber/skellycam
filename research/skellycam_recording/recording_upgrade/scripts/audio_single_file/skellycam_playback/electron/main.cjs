// Playback A/V-sync harness (2026-11-15). Serves the page and one take folder through a protocol.handle scheme with the
// hand-written single-range handler of scripts/range_transport/electron/main.cjs (plan WP 1.9 transport), runs
// run(cfg) in player.js in a shown window (real vsync rAF) and writes the result with process metrics
// (every 500 ms: phase, working set MB and cumulativeCPUUsage seconds, summed and per process type).
// env PB_CFG = config json path, PB_OUT = result json path. Unset ELECTRON_RUN_AS_NODE before launching.
const { app, BrowserWindow, protocol } = require('electron');
const path = require('path'), fs = require('fs');

const cfg = JSON.parse(fs.readFileSync(process.env.PB_CFG, 'utf8'));
app.setPath('userData', path.join(cfg.scratch, 'userdata_e' + process.versions.electron.split('.')[0]));
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
app.commandLine.appendSwitch('disable-renderer-backgrounding');
app.commandLine.appendSwitch('disable-backgrounding-occluded-windows');
app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');
protocol.registerSchemesAsPrivileged([{ scheme: 'skr', privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true, corsEnabled: true } }]);

// name -> absolute path: the page files plus the files of the take folder (basenames only, nothing else is served)
const FILES = {};
for (const f of ['player.html', 'player.js', 'tap.js', 'elprobe.js']) FILES[f] = path.join(__dirname, f);
for (const f of fs.readdirSync(cfg.take_dir)) FILES[f] = path.join(cfg.take_dir, f);
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.wav': 'audio/wav', '.flac': 'audio/flac', '.m4a': 'audio/mp4' };
const fhCache = new Map();
async function fh(p) { let h = fhCache.get(p); if (!h) { h = await fs.promises.open(p, 'r'); fhCache.set(p, h); } return h; }
const sizes = new Map();
function sizeOf(p) { let s = sizes.get(p); if (s === undefined) { s = fs.statSync(p).size; sizes.set(p, s); } return s; }
let requests = 0;

async function rangeHandler(req) {
  requests++;
  const p = FILES[decodeURIComponent(new URL(req.url).pathname.slice(1))];
  const base = { 'Accept-Ranges': 'bytes', 'Content-Type': (p && MIME[path.extname(p)]) || 'application/octet-stream', 'Cache-Control': 'no-store' };
  if (!p) return new Response('not found', { status: 404, headers: base });
  const size = sizeOf(p);
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
  const win = new BrowserWindow({ width: 1000, height: 300, x: 40, y: 40, show: true, backgroundColor: '#000000',
    webPreferences: { contextIsolation: true, backgroundThrottling: false } });
  await win.loadURL('skr://media/player.html');
  const metrics = [];
  let polling = true;
  (async () => {
    while (polling) {
      try {
        const ms = app.getAppMetrics();
        const phase = await win.webContents.executeJavaScript('window.__phase || ""');
        const by = {}; for (const m of ms) { const t = m.type; by[t] = by[t] || { ws: 0, cpu: 0 }; by[t].ws += m.memory.workingSetSize / 1024; by[t].cpu += m.cpu.cumulativeCPUUsage || 0; }
        metrics.push([Date.now(), phase, ms.reduce((a, m) => a + m.memory.workingSetSize / 1024, 0), ms.reduce((a, m) => a + (m.cpu.cumulativeCPUUsage || 0), 0), by]);
      } catch (e) { /* page busy or gone */ }
      await new Promise((q) => setTimeout(q, 500));
    }
  })();
  let page;
  try { page = await win.webContents.executeJavaScript(`run(${JSON.stringify(cfg)})`); }
  catch (e) { page = { error: String(e && e.message || e) }; }
  polling = false;
  const out = { electron: process.versions.electron, chrome: process.versions.chrome, cfg, requests, metrics, page };
  fs.writeFileSync(process.env.PB_OUT, JSON.stringify(out));
  console.log('wrote', process.env.PB_OUT);
  app.quit();
});
