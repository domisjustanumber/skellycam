// T-S5 Electron harness. Page loads from file:// (as skellycam-ui's packaged build does: window-manager.ts loadFile).
// Transports: file://, http (skellycam route as is / fixed in real app / fixed bare), and two protocol.handle schemes:
//   skr://media/<name>  hand-written Range handler (fs read, 206 + Content-Range)
//   skn://media/<name>  net.fetch('file://...') passthrough with the request's headers
// Env: RT_CFG (json written by run_electron.ps1 / prepared cfg), RT_OUT (result path), RT_PHASES (comma list).
// Unset ELECTRON_RUN_AS_NODE before launching.
const { app, BrowserWindow, protocol, net, session } = require('electron');
const path = require('path'), fs = require('fs'), http = require('http'), { pathToFileURL } = require('url');

const cfg = JSON.parse(fs.readFileSync(process.env.RT_CFG, 'utf8'));
const major = process.versions.electron.split('.')[0];
app.setPath('userData', path.join(cfg.scratch, 'userdata_e' + major));   // fresh HTTP cache per version
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
app.commandLine.appendSwitch('disable-renderer-backgrounding');

const priv = { standard: true, secure: true, supportFetchAPI: true, stream: true, corsEnabled: true };
protocol.registerSchemesAsPrivileged([{ scheme: 'skr', privileges: priv }, { scheme: 'skn', privileges: priv }]);

const FILES = Object.assign({}, cfg.files, {   // name -> absolute path; page + locator for the skr-origin probe
  'page.html': path.join(__dirname, 'page.html'),
  'sidecar_embedding/locator.js': path.join(__dirname, '..', '..', 'sidecar_embedding', 'locator.js') });
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8' };
const seenHeaders = { skr: [], skn: [] };   // first requests' headers as the handler saw them
const counts = { skr: 0, skn: 0 };
const netErrors = { counts: {}, first: [] };
const fhCache = new Map();
async function fh(p) { let h = fhCache.get(p); if (!h) { h = await fs.promises.open(p, 'r'); fhCache.set(p, h); } return h; }
const sizeCache = new Map();
function sizeOf(p) { let s = sizeCache.get(p); if (s === undefined) { s = fs.statSync(p).size; sizeCache.set(p, s); } return s; }
const EXPOSE = 'Content-Range, Content-Length, Accept-Ranges';
function log(scheme, req) {
  counts[scheme]++;
  if (seenHeaders[scheme].length < 40) seenHeaders[scheme].push({ url: req.url, method: req.method, range: req.headers.get('range'), headers: Object.fromEntries(req.headers.entries()) });
}
function nameOf(req) { return decodeURIComponent(new URL(req.url).pathname.slice(1)); }

// Hand-written handler: single byte range only (the player never sends multi-range).
async function rangeHandler(req) {
  log('skr', req);
  const p = FILES[nameOf(req)];
  const base = { 'Accept-Ranges': 'bytes', 'Content-Type': (p && MIME[path.extname(p)]) || 'application/octet-stream', 'Access-Control-Allow-Origin': '*', 'Access-Control-Expose-Headers': EXPOSE, 'Cache-Control': 'no-store' };
  if (!p) return new Response('not found', { status: 404, headers: base });
  const size = sizeOf(p);
  const rh = req.headers.get('range');
  const head = req.method === 'HEAD';
  if (!rh) {
    const h = { ...base, 'Content-Length': String(size) };
    if (head) return new Response(null, { status: 200, headers: h });
    const { Readable } = require('stream');
    return new Response(Readable.toWeb(fs.createReadStream(p)), { status: 200, headers: h });
  }
  const m = /^bytes=(\d*)-(\d*)$/.exec(rh.trim());
  const unsat = () => new Response(null, { status: 416, headers: { ...base, 'Content-Range': `bytes */${size}` } });
  if (!m || (m[1] === '' && m[2] === '')) return unsat();          // multi-range or malformed: 416 (documented)
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
  const { Readable } = require('stream');
  return new Response(Readable.toWeb(fs.createReadStream(p, { start, end })), { status: 206, headers: h });
}

async function netHandler(req) {
  log('skn', req);
  const p = FILES[nameOf(req)];
  if (!p) return new Response('not found', { status: 404 });
  const r = await net.fetch(pathToFileURL(p).toString(), { method: req.method, headers: req.headers });
  // add CORS headers so a file:// page may read it; keep status and body as net.fetch returned them
  const h = new Headers(r.headers); h.set('Access-Control-Allow-Origin', '*'); h.set('Access-Control-Expose-Headers', EXPOSE);
  return new Response(r.body, { status: r.status, statusText: r.statusText, headers: h });
}

function getJSON(url) {
  return new Promise((ok, bad) => http.get(url, res => { let d = ''; res.on('data', c => d += c); res.on('end', () => { try { ok(JSON.parse(d)); } catch (e) { bad(e); } }); }).on('error', bad));
}
function metrics() {
  const out = {};
  for (const m of app.getAppMetrics()) {
    const k = m.type === 'Utility' ? 'Utility:' + (m.serviceName || m.name || '') : m.type;
    const prev = out[k] || { pct: 0, cum: 0, n: 0 };
    out[k] = { pct: prev.pct + (m.cpu.percentCPUUsage || 0), cum: prev.cum + (m.cpu.cumulativeCPUUsage || 0), n: prev.n + 1 };
  }
  return out;
}

app.whenReady().then(async () => {
  protocol.handle('skr', rangeHandler);
  protocol.handle('skn', netHandler);
  session.defaultSession.webRequest.onErrorOccurred(d => {
    netErrors.counts[d.error] = (netErrors.counts[d.error] || 0) + 1;
    if (netErrors.first.length < 30) netErrors.first.push({ url: d.url.slice(0, 120), error: d.error, fromCache: d.fromCache });
  });
  const win = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true, backgroundThrottling: false } });
  win.webContents.setAudioMuted(true);
  await win.loadFile(path.join(__dirname, 'page.html'));
  const res = { electron: process.versions.electron, chrome: process.versions.chrome, started: new Date().toISOString(), phases: {} };
  const phases = (process.env.RT_PHASES || 'semantics,correct,bench').split(',');
  const run = async (expr) => win.webContents.executeJavaScript(expr);
  try {
    if (phases.includes('semantics')) res.phases.semantics = await run(`semantics(${JSON.stringify(cfg)})`);
    if (phases.includes('diag')) res.phases.diag = await run(`diag(${JSON.stringify(cfg)})`);
    if (phases.includes('origin')) {          // same probes from a page whose origin is skr://media (not file://)
      const w2 = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true, backgroundThrottling: false } });
      await w2.loadURL('skr://media/page.html');
      const c2 = Object.assign({}, cfg, { semanticsTransports: ['http_asis', 'http_fixed_real', 'http_fixed_bare', 'skn', 'file'] });
      res.phases.origin_skr = { origin: await w2.webContents.executeJavaScript('location.origin'),
                                semantics: await w2.webContents.executeJavaScript(`semantics(${JSON.stringify(c2)})`) };
      w2.destroy();
    }
    if (phases.includes('correct')) res.phases.correct = await run(`correctness(${JSON.stringify(cfg)})`);
    if (phases.includes('bench')) {
      const out = [];
      const plan = await run(`benchPlan(${JSON.stringify(cfg)})`);
      for (const item of plan) {
        const srv = item.serverPort ? await getJSON(`http://127.0.0.1:${item.serverPort}/__cpu`) : null;
        if (item.serverPort) await getJSON(`http://127.0.0.1:${item.serverPort}/__conns`);
        metrics();                                   // resets percentCPUUsage baselines
        const m0 = metrics(); const t0 = Date.now();
        const r = await run(`benchOne(${JSON.stringify(item)})`);
        const wall = (Date.now() - t0) / 1000; const m1 = metrics();
        if (srv) {
          const s1 = await getJSON(`http://127.0.0.1:${item.serverPort}/__cpu`);
          r.server_cpu_pct = +(100 * (s1.proc_s - srv.proc_s) / (s1.wall_s - srv.wall_s)).toFixed(1);
          r.server_conns = (await getJSON(`http://127.0.0.1:${item.serverPort}/__conns`)).n;
        }
        r.electron_cpu_pct = {};
        for (const k of Object.keys(m1)) {
          const cum = m0[k] && m1[k].cum && m0[k].cum ? 100 * (m1[k].cum - m0[k].cum) / wall : null;
          r.electron_cpu_pct[k] = { pct_since_last: +m1[k].pct.toFixed(1), cum_based: cum === null ? null : +cum.toFixed(1) };
        }
        out.push(r);
      }
      res.phases.bench = out;
    }
  } catch (e) { res.error = String(e && e.stack || e); }
  res.net_errors = netErrors; res.handler_seen = seenHeaders; res.handler_counts = counts;
  res.finished = new Date().toISOString();
  fs.writeFileSync(process.env.RT_OUT, JSON.stringify(res, null, 1));
  for (const h of fhCache.values()) await h.close();
  app.quit();
});
