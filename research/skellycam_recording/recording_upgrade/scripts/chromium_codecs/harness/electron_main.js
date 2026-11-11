// Electron runner for the Chromium codec tests.
// Usage: electron.exe electron_main.js --out <result.json> --suite main|serving [--only <substring>]
//   main    : probe + image + play (+MSE) + WebCodecs tests; page and media from the local HTTP server with Range
//   serving : SERVING_CLIPS under each serving mode (http-range, http-norange, file, app-range, app-netfetch,
//             app-netfetch-headers, app-range-nostream, app-full)
// Decoder names come from the DevTools Media domain via webContents.debugger.
'use strict';
const { app, BrowserWindow, protocol, net, ipcMain } = require('electron');
const fs = require('fs');
const path = require('path');
const { Readable } = require('stream');
const { pathToFileURL } = require('url');
const srv = require('./server.js');
const { mainTasks, servingTasks, benchTasks, runTasks, mediaCollector } = require('./tasks.js');

const argv = process.argv;
const arg = (n, d) => { const i = argv.indexOf(n); return i >= 0 ? argv[i + 1] : d; };
const OUT = arg('--out');
const SUITE = arg('--suite', 'main');
const ONLY = arg('--only', null);
// keep the Electron profile out of %APPDATA% (scratch dir of this topic)
app.setPath('userData', path.join('C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/chromium_codecs', `electron-userdata-${process.versions.electron}`));

// Custom schemes. app://local/h/... = harness folder, app://local/m/... = media folder (one host = one origin,
// so the page can read back decoded pixels; a first run with hosts h/m was cross-origin and tainted the canvas).
const SCHEMES = {
  app: { privileges: { standard: true, secure: true, stream: true, supportFetchAPI: true, corsEnabled: true }, impl: 'range' },
  appnf: { privileges: { standard: true, secure: true, stream: true, supportFetchAPI: true, corsEnabled: true }, impl: 'netfetch' },
  appnfh: { privileges: { standard: true, secure: true, stream: true, supportFetchAPI: true, corsEnabled: true }, impl: 'netfetch-headers' },
  appns: { privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true }, impl: 'range' },
  appfull: { privileges: { standard: true, secure: true, stream: true, supportFetchAPI: true, corsEnabled: true }, impl: 'full' },
};
protocol.registerSchemesAsPrivileged(Object.entries(SCHEMES).map(([scheme, s]) => ({ scheme, privileges: s.privileges })));
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
// When other windows cover the test window, Chromium's native occlusion tracking marks it hidden: in the first
// Electron 45 run requestVideoFrameCallback never fired during playback (0 callbacks). Test-app switches only.
app.commandLine.appendSwitch('disable-backgrounding-occluded-windows');
app.commandLine.appendSwitch('disable-renderer-backgrounding');
app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');
// extra Chromium switches for variant runs, e.g. --switch disable-accelerated-video-decode
const EXTRA_SWITCHES = argv.flatMap((a, i) => (a === '--switch' ? [argv[i + 1]] : []));
for (const sw of EXTRA_SWITCHES) app.commandLine.appendSwitch(sw);
const LABEL_SUFFIX = EXTRA_SWITCHES.length ? '+' + EXTRA_SWITCHES.join('+') : '';

const protoLog = [];
const dbg = (m) => { try { fs.mkdirSync(path.dirname(OUT), { recursive: true }); fs.appendFileSync(OUT + '.stages', `${new Date().toISOString()} ${m}
`); } catch { } };
dbg('loaded');
function resolveFile(u) {
  const p = decodeURIComponent(u.pathname);
  return p.startsWith('/h/') ? path.join(srv.HARNESS, p.slice(3)) : path.join(srv.MEDIA, p.slice(3));
}
function makeHandler(scheme, impl) {
  return async (req) => {
    const u = new URL(req.url);
    const file = resolveFile(u);
    const range = req.headers.get('range');
    const entry = { scheme, path: u.pathname, range, status: 0 };
    protoLog.push(entry);
    if (impl === 'netfetch' || impl === 'netfetch-headers') {
      const r = await net.fetch(pathToFileURL(file).toString(), impl === 'netfetch-headers' ? { headers: req.headers } : undefined);
      entry.status = r.status; entry.contentRange = r.headers.get('content-range');
      return r;
    }
    let st; try { st = fs.statSync(file); } catch { entry.status = 404; return new Response('not found', { status: 404 }); }
    const type = srv.contentType(file);
    if (impl === 'range' && range) {
      const r = srv.parseRange(range, st.size);
      if (r === 'unsatisfiable') { entry.status = 416; return new Response(null, { status: 416, headers: { 'Content-Range': `bytes */${st.size}` } }); }
      if (r) {
        entry.status = 206;
        return new Response(Readable.toWeb(fs.createReadStream(file, { start: r.start, end: r.end })), {
          status: 206,
          headers: { 'Content-Type': type, 'Accept-Ranges': 'bytes', 'Content-Range': `bytes ${r.start}-${r.end}/${st.size}`, 'Content-Length': String(r.end - r.start + 1) },
        });
      }
    }
    entry.status = 200;
    const headers = { 'Content-Type': type, 'Content-Length': String(st.size) };
    if (impl === 'range') headers['Accept-Ranges'] = 'bytes';
    return new Response(Readable.toWeb(fs.createReadStream(file)), { status: 200, headers });
  };
}

app.whenReady().then(async () => {
  dbg('ready');
  for (const [scheme, s] of Object.entries(SCHEMES)) protocol.handle(scheme, makeHandler(scheme, s.impl));
  const S = await srv.start(0);
  const server = `http://127.0.0.1:${S.port}`;
  ipcMain.on('harness-result', (_e, key, json) => { let v; try { v = JSON.parse(json); } catch (e) { v = { parseError: String(e) }; } S.deliver(key, v); });
  ipcMain.handle('harness-manifest', () => fs.readFileSync(path.join(srv.MEDIA, 'manifest.json'), 'utf8'));

  const win = new BrowserWindow({
    show: false, width: 820, height: 620, x: 0, y: 0,
    webPreferences: { preload: path.join(__dirname, 'preload.js'), backgroundThrottling: false },
  });
  win.showInactive();
  dbg('window');
  const media = mediaCollector();
  await win.loadURL('about:blank'); // Media.enable never resolves on a webContents with no document loaded
  win.webContents.debugger.attach('1.3');
  win.webContents.debugger.on('message', (_e, method, params) => media.feed(method, params));
  await win.webContents.debugger.sendCommand('Media.enable');
  dbg('media enabled');
  const consoleErrors = [];
  win.webContents.on('console-message', (...a) => {
    const e = a[0]; const level = e.level ?? a[1]; const message = e.message ?? a[2];
    if (level === 'error' || level === 3) consoleErrors.push(String(message).slice(0, 300));
  });

  const out = {
    runner: 'electron', suite: SUITE, extraSwitches: EXTRA_SWITCHES, versions: process.versions,
    commandLine: process.argv.slice(1),
  };
  dbg('gpu info...');
  try { out.gpuInfoComplete = await app.getGPUInfo('complete'); } catch (e) { out.gpuInfoError = String(e); }

  const navigate = async (url) => { await win.webContents.loadURL(url).catch((e) => { if (!String(e).includes('ERR_ABORTED')) throw e; }); };
  const waitResult = (k, t) => S.waitResult(k, t);
  const label = `electron${process.versions.electron}${LABEL_SUFFIX}`;
  let tasks = [];
  const HARN_FILE = pathToFileURL(srv.HARNESS).toString() + '/';
  const MEDIA_FILE = pathToFileURL(srv.MEDIA).toString() + '/';
  if (SUITE === 'main') {
    tasks = mainTasks({ server, pageBase: `${server}/h/`, mediaBase: `${server}/r/`, label: `${label}|http-range`, filter: ONLY ? (c) => ONLY.split(',').some((x) => c.id.includes(x)) : null });
  } else if (SUITE === 'bench' || SUITE === 'bench-quick') {
    tasks = benchTasks({ server, pageBase: `${server}/h/`, mediaBase: `${server}/r/`, label: `${label}|http-range`, quick: SUITE === 'bench-quick', onlyClip: ONLY });
  } else {
    const modes = {
      'http-range': [`${server}/h/`, `${server}/r/`],
      'http-norange': [`${server}/h/`, `${server}/n/`],
      file: [HARN_FILE, MEDIA_FILE],
      'app-range': ['app://local/h/', 'app://local/m/'],
      'app-netfetch': ['appnf://local/h/', 'appnf://local/m/'],
      'app-netfetch-headers': ['appnfh://local/h/', 'appnfh://local/m/'],
      'app-range-nostream': ['appns://local/h/', 'appns://local/m/'],
      'app-full': ['appfull://local/h/', 'appfull://local/m/'],
    };
    for (const [mode, [pageBase, mediaBase]] of Object.entries(modes)) tasks.push(...servingTasks({ server, pageBase, mediaBase, label: `${label}|${mode}` }));
  }
  const t0 = Date.now();
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT + '.log', `start ${label} ${SUITE} tasks=${tasks.length}\n`);
  out.results = await runTasks(tasks, {
    navigate, waitResult, media,
    log: (s) => { console.log(s); fs.appendFileSync(OUT + '.log', s + '\n'); },
  });
  // attach the request logs (for serving: which requests carried Range, which status was returned)
  out.httpRequestLog = SUITE === 'serving' ? S.reqlog.filter((r) => !r.path.startsWith('/h/')) : { count: S.reqlog.length, ranged: S.reqlog.filter((r) => r.range).length, status206: S.reqlog.filter((r) => r.status === 206).length };
  out.protocolLog = SUITE === 'serving' ? protoLog.filter((r) => !r.path.endsWith('.js') && !r.path.endsWith('.html')) : protoLog.length;
  out.consoleErrors = consoleErrors.slice(0, 50);
  out.gpuFeatureStatusAfterTests = app.getGPUFeatureStatus(); // read after media ran (at 'ready' it reports pre-GPU-init values)
  out.taskCount = tasks.length;
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(out, null, 1));
  console.log('wrote', OUT, 'in', Math.round((Date.now() - t0) / 1000), 's');
  S.close();
  app.exit(0);
});
