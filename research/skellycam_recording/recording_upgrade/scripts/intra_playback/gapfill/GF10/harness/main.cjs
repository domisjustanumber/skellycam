// GF10 copy (2026-11-10) of scripts/chromium_sync_scrub/harness/main.cjs. Changes: own userData default (step3 temp);
// GET /metrics/mark-<label> samples app.getAppMetrics() on demand (memory at fixed target counts, page-driven);
// child-process-gone events are kept in the output JSON (gpu replacement evidence); a background 500 ms sampler
// can be started with /metrics/bgstart (supplementary peak only). Original: Electron main process for the chromium_sync_scrub harness.
// Usage: electron.exe main.cjs --test=<name> --params=<urlencoded query> --out=<result.json> [--timeout=600] [--width=1600 --height=900]
// Starts server.cjs on a random localhost port, opens one window on
//   http://127.0.0.1:<port>/harness/index.html?test=<name>&<params>
// waits for the page to POST /result, adds versions + GPU info + process metrics, writes --out, quits.
// webPreferences mirror skellycam-ui/electron/main/services/window-manager.ts (sandbox, contextIsolation,
// no nodeIntegration) except backgroundThrottling:false so an occluded harness window keeps rendering.
'use strict';
const { app, BrowserWindow } = require('electron');
const fs = require('fs');
const path = require('path');
const { start } = require('./server.cjs');

function arg(name, dflt) {
  const a = process.argv.find((x) => x.startsWith(`--${name}=`));
  return a ? a.slice(name.length + 3) : dflt;
}
const TEST = arg('test', 'caps');
const CONFIGS = arg('configs', ''); // path to a JSON list of param objects (test=batch)
// served at GET /configs (a long list does not fit in the URL: Node's http server caps request headers at 16 KB)
const CONFIGS_JSON = CONFIGS ? fs.readFileSync(CONFIGS, 'utf8') : '[]';
const PARAMS = arg('params', '');
const OUT = arg('out', path.join(__dirname, `result_${TEST}.json`));
const TIMEOUT_S = Number(arg('timeout', '900'));
const W = Number(arg('width', '1600')), H = Number(arg('height', '900'));
// Opt-in additions (intra_playback, 2026-11-09); defaults leave the original behaviour unchanged:
//   --medialog=1     attach the DevTools Media domain; page can GET /metrics/media for the decoder name per player
//                    (kVideoDecoderName / kIsPlatformVideoDecoder), the snapshot is reset after each read
//   --noocclusion=1  test-app switches so a covered window keeps rendering and firing rVFC
//                    (chromium_codecs NOTES 1.3: without them a covered window never fired rVFC in E45)
const MEDIALOG = arg('medialog', '0') === '1';
if (arg('noocclusion', '0') === '1') {
  app.commandLine.appendSwitch('disable-backgrounding-occluded-windows');
  app.commandLine.appendSwitch('disable-renderer-backgrounding');
  app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');
}
let mediaPlayers = {}, mediaSeq = 0;
function mediaFeed(method, p) {
  if (method === 'Media.playersCreated') { for (const x of p.players || []) { const id = typeof x === 'object' ? x.playerId : x; if (!mediaPlayers[id]) mediaPlayers[id] = { seq: ++mediaSeq, props: {}, errors: [], messages: [] }; } return; }
  if (!method || !method.startsWith('Media.') || !p || p.playerId === undefined) return;
  const pl = (mediaPlayers[p.playerId] ||= { seq: ++mediaSeq, props: {}, errors: [], messages: [] });
  if (method === 'Media.playerPropertiesChanged') for (const pr of p.properties) pl.props[pr.name] = pr.value;
  else if (method === 'Media.playerErrorsRaised') for (const e of p.errors) pl.errors.push(`${e.errorType} ${e.code}`);
  else if (method === 'Media.playerMessagesLogged') for (const m of p.messages) if (m.level === 'error' || m.level === 'warning') pl.messages.push(`${m.level}: ${String(m.message).slice(0, 200)}`);
}
function mediaSnapshot(since = 0) { // players first seen after mark `since` (players are never deleted, so late events of
  // an earlier configuration's player cannot be attributed to a later one)
  const keep = ['kVideoDecoderName', 'kIsPlatformVideoDecoder', 'kIsVideoDecryptingDemuxerStream', 'kResolution', 'kIsStreaming', 'kIsRangeHeaderSupported', 'kFrameTitle'];
  return Object.entries(mediaPlayers).filter(([, pl]) => pl.seq > since).sort((a, b) => a[1].seq - b[1].seq)
    .map(([id, pl]) => ({ seq: pl.seq, ...Object.fromEntries(keep.filter((k) => k in pl.props).map((k) => [k, pl.props[k]])), errors: pl.errors.slice(0, 3), messages: pl.messages.slice(0, 3) }));
}
function mediaCmd(cmd) {
  if (cmd === 'mediamark') return { mark: mediaSeq };
  if (cmd.startsWith('media-')) return { players: mediaSnapshot(Number(cmd.slice(6)) || 0) };
  return null;
}
// keep Chromium's profile/cache out of %APPDATA% (scratchpad, or CSS_USER_DATA if set)
app.setPath('userData', process.env.CSS_USER_DATA || path.join('C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step3/GF10', `electron_userdata_${process.versions.electron}`));
const LOG = `${OUT}.log`;
function plog(s) { try { fs.mkdirSync(path.dirname(LOG), { recursive: true }); fs.appendFileSync(LOG, `${new Date().toISOString()} ${s}
`); } catch { /* */ } console.log(s); }

let metricsTimer = null, metricsSamples = [];
function sampleMetrics() {
  const t = Date.now();
  for (const m of app.getAppMetrics()) {
    metricsSamples.push({ t, pid: m.pid, type: m.type, cpu: m.cpu.percentCPUUsage, cum_cpu_s: m.cpu.cumulativeCPUUsage, ws_kb: m.memory.workingSetSize,
      peak_ws_kb: m.memory.peakWorkingSetSize, private_kb: m.memory.privateBytes });
  }
}
let markSamples = [], childGone = [];
function snap() { // same fields as sampleMetrics (app.getAppMetrics; private_kb = memory.privateBytes, raw unit)
  const t = Date.now();
  return app.getAppMetrics().map((m) => ({ t, pid: m.pid, type: m.type, ws_kb: m.memory.workingSetSize,
    peak_ws_kb: m.memory.peakWorkingSetSize, private_kb: m.memory.privateBytes }));
}
async function onMetrics(cmd) {
  if (cmd.startsWith('mark-')) { // GF10: on-demand sample tagged with a label (e.g. s0_t20 = target count 20)
    const label = decodeURIComponent(cmd.slice(5)); const procs = snap(); markSamples.push({ label, procs });
    const gpu = procs.filter((p) => p.type === 'GPU');
    return { label, gpu, child_gone_so_far: childGone.length };
  }
  if (cmd === 'bgstart') { metricsSamples = []; metricsTimer = setInterval(sampleMetrics, 500); return { ok: true }; }
  if (cmd === 'start') { metricsSamples = []; app.getAppMetrics(); metricsTimer = setInterval(sampleMetrics, 500); return { ok: true }; }
  if (cmd.startsWith('media')) return mediaCmd(cmd);
  if (cmd === 'stop') { clearInterval(metricsTimer); metricsTimer = null; sampleMetrics(); return { ok: true, n: metricsSamples.length }; }
  return { error: 'unknown' };
}

function summarizeMetrics(samples) {
  // mean CPU % and max working set per process type over the sampled window (first sample per pid dropped:
  // percentCPUUsage is "since last call")
  const byType = {}; const seen = new Set();
  for (const s of samples) {
    const k = s.pid; if (!seen.has(k)) { seen.add(k); continue; }
    const b = byType[s.type] || (byType[s.type] = { cpu: [], ws: [], pids: new Set() });
    b.cpu.push(s.cpu); b.ws.push(s.ws_kb); b.pids.add(s.pid);
  }
  const out = {};
  for (const [t, b] of Object.entries(byType)) {
    const nT = new Set(samples.filter((s) => s.type === t).map((s) => s.t)).size;
    out[t] = { processes: b.pids.size, cpu_pct_sum_mean: b.cpu.reduce((a, c) => a + c, 0) / Math.max(1, nT - 1),
      ws_mb_max_single: Math.max(...b.ws) / 1024 };
  }
  // CPU from cumulativeCPUUsage (seconds of CPU time per process): sum over pids of (last - first) / window
  const firstT = Math.min(...samples.map((s) => s.t)), lastT0 = Math.max(...samples.map((s) => s.t));
  const perPid = {};
  for (const s of samples) { if (s.cum_cpu_s === undefined) continue; const p = perPid[s.pid] || (perPid[s.pid] = { type: s.type, a: s, b: s }); if (s.t < p.a.t) p.a = s; if (s.t > p.b.t) p.b = s; }
  for (const p of Object.values(perPid)) {
    const o = out[p.type] || (out[p.type] = {});
    o.cpu_cores_from_cumulative = (o.cpu_cores_from_cumulative || 0) + (p.b.cum_cpu_s - p.a.cum_cpu_s) / Math.max(1e-3, (lastT0 - firstT) / 1000);
  }
  out.cpu_cores_total_from_cumulative = Object.values(perPid).reduce((a, p) => a + (p.b.cum_cpu_s - p.a.cum_cpu_s), 0) / Math.max(1e-3, (lastT0 - firstT) / 1000);
  out.window_s = (lastT0 - firstT) / 1000;
  // total working set at the last timestamp
  const lastT = Math.max(...samples.map((s) => s.t));
  out.total_ws_mb_last = samples.filter((s) => s.t === lastT).reduce((a, s) => a + s.ws_kb, 0) / 1024;
  return out;
}

app.whenReady().then(async () => {
  let done = false;
  const finish = async (result) => {
    if (done) return; done = true;
    let gpu = null;
    try { gpu = await app.getGPUInfo('complete'); } catch (e) { gpu = { error: String(e) }; }
    const out = {
      test: TEST, params: Object.fromEntries(new URLSearchParams(PARAMS)),
      versions: { electron: process.versions.electron, chrome: process.versions.chrome, node: process.versions.node, v8: process.versions.v8 },
      gpu_feature_status: app.getGPUFeatureStatus(),
      gpu_info: TEST === 'caps' ? gpu : (gpu && gpu.gpuDevice ? { gpuDevice: gpu.gpuDevice } : null),
      metrics_summary: metricsSamples.length ? summarizeMetrics(metricsSamples) : null,
      media_players_at_end: MEDIALOG ? mediaSnapshot(0) : undefined,
      switches: { medialog: MEDIALOG, noocclusion: arg('noocclusion', '0') === '1' },
      metrics_samples: TEST === 'caps' ? undefined : metricsSamples,
      mark_samples: markSamples, child_process_gone: childGone,
      window: { width: W, height: H },
      finished_utc: new Date().toISOString(),
      result,
    };
    fs.mkdirSync(path.dirname(OUT), { recursive: true });
    fs.writeFileSync(OUT, JSON.stringify(out, null, 1));
    console.log(`[harness] wrote ${OUT}`);
    app.exit(0);
  };
  const { port } = await start({ configs: CONFIGS_JSON, onResult: finish, onMetrics, onLog: (s) => plog(`[page] ${s}`) });
  const win = new BrowserWindow({ width: W, height: H, show: true, backgroundColor: '#000000',
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true, backgroundThrottling: false } });
  win.webContents.on('console-message', (...a) => {
    const e = a[0]; const msg = e && e.message !== undefined ? e.message : a[2];
    console.log('[console]', msg);
  });
  win.webContents.on('render-process-gone', (_e, d) => { plog(`render-process-gone ${JSON.stringify(d)}`); finish({ error: 'render-process-gone', details: d }); });
  app.on('child-process-gone', (_e, d) => { childGone.push({ t: Date.now(), marks_so_far: markSamples.length, ...d }); plog(`child-process-gone ${JSON.stringify(d)}`); });
  const url = `http://127.0.0.1:${port}/harness/index.html?test=${encodeURIComponent(TEST)}&${PARAMS}`;
  console.log('[harness] loading', url);
  if (MEDIALOG) {
    try {
      await win.loadURL('about:blank'); // Media.enable never resolves on a webContents with no document (chromium_codecs electron_main.js:100)
      win.webContents.debugger.attach('1.3');
      win.webContents.debugger.on('message', (_e, method, params) => mediaFeed(method, params));
      await win.webContents.debugger.sendCommand('Media.enable');
    } catch (e) { plog(`medialog setup failed ${e}`); }
  }
  win.loadURL(url);
  setTimeout(() => finish({ error: `timeout after ${TIMEOUT_S}s` }), TIMEOUT_S * 1000);
});
