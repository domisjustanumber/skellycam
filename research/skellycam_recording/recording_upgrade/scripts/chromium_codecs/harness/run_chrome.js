// Chrome runner (DevTools protocol over --remote-debugging-port, Node >= 22 global WebSocket).
// Usage: node run_chrome.js --out <result.json> --suite main|serving [--chrome <chrome.exe>] [--only <substring>]
// Uses a throw-away profile in the topic scratch dir; does not touch the user's Chrome profile.
'use strict';
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const srv = require('./server.js');
const { mainTasks, servingTasks, benchTasks, runTasks, mediaCollector } = require('./tasks.js');

const argv = process.argv;
const arg = (n, d) => { const i = argv.indexOf(n); return i >= 0 ? argv[i + 1] : d; };
const OUT = arg('--out');
const SUITE = arg('--suite', 'main');
const ONLY = arg('--only', null);
const CHROME = arg('--chrome', 'C:/Program Files/Google/Chrome/Application/chrome.exe');
const SCRATCH = 'C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/chromium_codecs';
const PORT = 9339;

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
    ws.onopen = () => resolve({
      send: (method, params = {}) => new Promise((res, rej) => { const i = ++id; pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params })); }),
      close: () => ws.close(),
    });
  });
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const S = await srv.start(0);
  const server = `http://127.0.0.1:${S.port}`;
  const profile = path.join(SCRATCH, `chrome-profile-${Date.now()}`);
  const chromeArgs = [`--user-data-dir=${profile}`, `--remote-debugging-port=${PORT}`, '--no-first-run', '--no-default-browser-check',
    '--autoplay-policy=no-user-gesture-required', '--window-position=0,0', '--window-size=820,620',
    // Without these, Chrome treats the test window as hidden when other windows cover it and never starts loading
    // <video> (first full run: every play task timed out with no loadeddata/error). Test-browser flags only.
    '--disable-backgrounding-occluded-windows', '--disable-features=CalculateNativeWinOcclusion', '--disable-renderer-backgrounding',
    ...argv.flatMap((a, i) => (a === '--switch' ? ['--' + argv[i + 1]] : [])), 'about:blank'];
  const proc = spawn(CHROME, chromeArgs, { stdio: 'ignore' });
  let version;
  for (let i = 0; i < 100; i++) { try { version = await (await fetch(`http://127.0.0.1:${PORT}/json/version`)).json(); break; } catch { await sleep(200); } }
  if (!version) throw new Error('chrome did not start');
  const browser = await cdp(version.webSocketDebuggerUrl);
  const out = { runner: 'chrome', suite: SUITE, chromeArgs, version };
  try { out.systemInfoBefore = await browser.send('SystemInfo.getInfo'); } catch (e) { out.systemInfoError = String(e); }
  const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
  const pageT = list.find((t) => t.type === 'page');
  const media = mediaCollector();
  const page = await cdp(pageT.webSocketDebuggerUrl, (m, p) => media.feed(m, p));
  await page.send('Page.enable');
  await page.send('Media.enable');
  await page.send('Emulation.setFocusEmulationEnabled', { enabled: true }).catch(() => {});
  const navigate = async (url) => { await page.send('Page.bringToFront').catch(() => {}); await page.send('Page.navigate', { url }); };
  const label = `chrome${version.Browser.split('/')[1]}` + (argv.includes('--switch') ? '+' + argv.flatMap((a, i) => (a === '--switch' ? [argv[i + 1]] : [])).join('+') : '');
  let tasks = [];
  if (SUITE === 'main') {
    tasks = mainTasks({ server, pageBase: `${server}/h/`, mediaBase: `${server}/r/`, label: `${label}|http-range`, filter: ONLY ? (c) => ONLY.split(',').some((x) => c.id.includes(x)) : null });
  } else if (SUITE === 'bench' || SUITE === 'bench-quick') {
    tasks = benchTasks({ server, pageBase: `${server}/h/`, mediaBase: `${server}/r/`, label: `${label}|http-range`, quick: SUITE === 'bench-quick', onlyClip: ONLY });
  } else {
    const modes = {
      'http-range': [`${server}/h/`, `${server}/r/`],
      'http-norange': [`${server}/h/`, `${server}/n/`],
      file: [pathToFileURL(srv.HARNESS).toString() + '/', pathToFileURL(srv.MEDIA).toString() + '/'],
    };
    for (const [mode, [pageBase, mediaBase]] of Object.entries(modes)) tasks.push(...servingTasks({ server, pageBase, mediaBase, label: `${label}|${mode}` }));
  }
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT + '.log', `start ${label} ${SUITE} tasks=${tasks.length}\n`);
  out.results = await runTasks(tasks, {
    navigate, waitResult: (k, t) => S.waitResult(k, t), media,
    log: (s) => { console.log(s); fs.appendFileSync(OUT + '.log', s + '\n'); },
  });
  try { const si = await browser.send('SystemInfo.getInfo'); out.gpuFeatureStatusAfterTests = si.gpu.featureStatus; out.videoDecodingAfterTests = si.gpu.videoDecoding; } catch (e) { out.systemInfoAfterError = String(e); }
  out.httpRequestLog = SUITE === 'serving' ? S.reqlog.filter((r) => !r.path.startsWith('/h/')) : { count: S.reqlog.length, ranged: S.reqlog.filter((r) => r.range).length, status206: S.reqlog.filter((r) => r.status === 206).length };
  out.taskCount = tasks.length;
  fs.writeFileSync(OUT, JSON.stringify(out, null, 1));
  console.log('wrote', OUT);
  try { await browser.send('Browser.close'); } catch { }
  page.close(); browser.close(); S.close();
  setTimeout(() => { try { proc.kill(); } catch { } process.exit(0); }, 1500);
})().catch((e) => { console.error(e); process.exit(1); });
