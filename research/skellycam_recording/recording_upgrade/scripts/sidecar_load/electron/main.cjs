// T-S4 sidecar-load harness. Runs page.html from file:// with the arm in $SL_CFG (JSON); writes $SL_OUT.
// Unset ELECTRON_RUN_AS_NODE before launching (VS Code sets it).
const { app, BrowserWindow } = require('electron');
const path = require('path'), fs = require('fs');
app.commandLine.appendSwitch('disable-renderer-backgrounding');
app.commandLine.appendSwitch('enable-precise-memory-info');
app.commandLine.appendSwitch('js-flags', '--expose-gc');

function metrics(rpid) {
  const m = app.getAppMetrics();
  const out = { total_ws_kb: 0, total_private_kb: 0, renderer: null, procs: [] };
  for (const p of m) {
    const ws = p.memory.workingSetSize, pr = p.memory.privateBytes || 0;
    out.total_ws_kb += ws; out.total_private_kb += pr;
    out.procs.push({ type: p.type, ws_kb: ws, private_kb: pr });
    if (p.pid === rpid) out.renderer = { ws_kb: ws, private_kb: pr };
  }
  return out;
}

app.whenReady().then(async () => {
  const cfg = JSON.parse(fs.readFileSync(process.env.SL_CFG, 'utf8'));
  const win = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true, backgroundThrottling: false } });
  await win.loadFile(path.join(__dirname, 'page.html'));
  const rpid = win.webContents.getOSProcessId();
  const res = { electron: process.versions.electron, chrome: process.versions.chrome, v8: process.versions.v8, arm: cfg.arm, fps: cfg.fps };
  try {
    await new Promise(r => setTimeout(r, 400));
    res.page_base = await win.webContents.executeJavaScript('gcNow()');
    res.mem_base = metrics(rpid);
    let peakR = 0, peakT = 0;
    const poll = setInterval(() => { const x = metrics(rpid); peakR = Math.max(peakR, x.renderer ? x.renderer.private_kb : 0); peakT = Math.max(peakT, x.total_private_kb); }, 20);
    res.load = await win.webContents.executeJavaScript(`runLoad(${JSON.stringify(cfg)})`);
    clearInterval(poll);
    res.page_after = await win.webContents.executeJavaScript('gcNow()');
    await new Promise(r => setTimeout(r, 200));
    res.mem_after = metrics(rpid);
    res.mem_peak = { renderer_private_kb: peakR, total_private_kb: peakT };
    res.lookups = await win.webContents.executeJavaScript(`runLookups(${JSON.stringify(cfg)})`);
    res.mem_end = metrics(rpid);
  } catch (e) { res.exception = String(e && e.stack || e); }
  fs.writeFileSync(process.env.SL_OUT, JSON.stringify(res, null, 1));
  app.quit();
});
