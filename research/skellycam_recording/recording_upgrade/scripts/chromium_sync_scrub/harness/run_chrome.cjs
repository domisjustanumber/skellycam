// Chrome runner for the chromium_sync_scrub harness (added for intra_playback, 2026-11-09).
// Same CLI as main.cjs, but drives the installed Chrome over the DevTools protocol instead of Electron:
//   node run_chrome.cjs --test=<name> --params=<query> --out=<result.json> [--configs=<list.json>] [--timeout=900]
//        [--medialog=1] [--chrome=<chrome.exe>]
// Starts server.cjs, launches Chrome with a throw-away profile (CSS_CHROME_PROFILE_ROOT or the intra_playback
// scratchpad) and --remote-debugging-port, navigates to the harness page, waits for POST /result, writes --out.
// No Electron metrics: /metrics/start|stop are no-ops; /metrics/media returns the Media-domain players (decoder names).
// Switches as in scripts/chromium_codecs/harness/run_chrome.js (occlusion/backgrounding off, autoplay allowed).
'use strict';
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const { start } = require('./server.cjs');

function arg(name, dflt) { const a = process.argv.find((x) => x.startsWith(`--${name}=`)); return a ? a.slice(name.length + 3) : dflt; }
const TEST = arg('test', 'caps');
const PARAMS = arg('params', '');
const OUT = arg('out');
const CONFIGS = arg('configs', '');
const TIMEOUT_S = Number(arg('timeout', '900'));
const MEDIALOG = arg('medialog', '0') === '1';
const CHROME = arg('chrome', 'C:/Program Files/Google/Chrome/Application/chrome.exe');
const PROFILE_ROOT = process.env.CSS_CHROME_PROFILE_ROOT || 'C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/intra_playback/chrome_profiles';
const PORT = Number(arg('port', '9341'));
const LOG = `${OUT}.log`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function plog(s) { try { fs.mkdirSync(path.dirname(LOG), { recursive: true }); fs.appendFileSync(LOG, `${new Date().toISOString()} ${s}\n`); } catch { /* */ } console.log(s); }

function cdp(wsUrl, onEvent) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl);
    let id = 0; const pending = new Map();
    ws.onmessage = (m) => {
      const msg = JSON.parse(m.data);
      if (msg.id && pending.has(msg.id)) { const { res, rej } = pending.get(msg.id); pending.delete(msg.id); msg.error ? rej(new Error(JSON.stringify(msg.error))) : res(msg.result); }
      else if (msg.method && onEvent) onEvent(msg.method, msg.params);
    };
    ws.onerror = (e) => reject(e);
    ws.onopen = () => resolve({ send: (method, params = {}) => new Promise((res, rej) => { const i = ++id; pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params })); }), close: () => ws.close() });
  });
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

(async () => {
  let done = false, proc = null, browser = null, page = null, version = null, srv = null;
  const finish = async (result) => {
    if (done) return; done = true;
    let sysinfo = null;
    try { const si = await browser.send('SystemInfo.getInfo'); sysinfo = { gpuDevices: si.gpu.devices, videoDecoding: si.gpu.videoDecoding }; } catch (e) { sysinfo = { error: String(e) }; }
    const out = { test: TEST, runner: 'chrome-cdp', params: Object.fromEntries(new URLSearchParams(PARAMS)),
      versions: { chrome: version && version.Browser, protocol: version && version['Protocol-Version'], node: process.versions.node },
      gpu_info: sysinfo, media_players_at_end: MEDIALOG ? mediaSnapshot(0) : undefined, finished_utc: new Date().toISOString(), result };
    fs.mkdirSync(path.dirname(OUT), { recursive: true });
    fs.writeFileSync(OUT, JSON.stringify(out, null, 1));
    plog(`[chrome-runner] wrote ${OUT}`);
    // exit timer first: Browser.close may never be answered (Chrome closes the socket), which left the runner hanging
    setTimeout(() => { try { proc.kill(); } catch { /* */ } try { srv.close(); } catch { /* */ } process.exit(0); }, 1500);
    try { await Promise.race([browser.send('Browser.close'), sleep(1000)]); } catch { /* */ }
  };
  const configs = CONFIGS ? fs.readFileSync(CONFIGS, 'utf8') : '[]';
  const S = await start({ configs, onResult: finish, onLog: (s) => plog(`[page] ${s}`),
    onMetrics: async (cmd) => mediaCmd(cmd) || { ok: true, note: 'no metrics in chrome runner' } });
  srv = S.server;
  const profile = path.join(PROFILE_ROOT, `p${Date.now()}`);
  const chromeArgs = [`--user-data-dir=${profile}`, `--remote-debugging-port=${PORT}`, '--no-first-run', '--no-default-browser-check',
    '--autoplay-policy=no-user-gesture-required', '--window-position=0,0', '--window-size=1600,900',
    '--disable-backgrounding-occluded-windows', '--disable-features=CalculateNativeWinOcclusion', '--disable-renderer-backgrounding', 'about:blank'];
  proc = spawn(CHROME, chromeArgs, { stdio: 'ignore' });
  for (let i = 0; i < 100 && !version; i++) { try { version = await (await fetch(`http://127.0.0.1:${PORT}/json/version`)).json(); } catch { await sleep(200); } }
  if (!version) { await finish({ error: 'chrome did not start' }); return; }
  browser = await cdp(version.webSocketDebuggerUrl);
  const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
  page = await cdp(list.find((t) => t.type === 'page').webSocketDebuggerUrl, mediaFeed);
  await page.send('Page.enable');
  if (MEDIALOG) await page.send('Media.enable');
  const url = `http://127.0.0.1:${S.port}/harness/index.html?test=${encodeURIComponent(TEST)}&${PARAMS}`;
  plog(`[chrome-runner] ${version.Browser} loading ${url}`);
  await page.send('Page.navigate', { url });
  setTimeout(() => finish({ error: `timeout after ${TIMEOUT_S}s` }), TIMEOUT_S * 1000);
})().catch((e) => { console.error(e); process.exit(1); });
