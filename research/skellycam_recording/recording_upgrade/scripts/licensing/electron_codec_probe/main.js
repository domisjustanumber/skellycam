// Electron codec capability probe (licensing topic, no timing).
// Usage: electron.exe <this dir> --samples=<dir with make_codec_samples.sh output> --out=<result.json>
const { app, BrowserWindow, ipcMain } = require('electron');
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

function arg(name) {
  const a = process.argv.find((x) => x.startsWith(`--${name}=`));
  return a ? a.slice(name.length + 3) : null;
}
const samples = arg('samples');
const out = arg('out');
if (!samples || !out) { console.error('need --samples= and --out='); process.exit(2); }

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    show: false, width: 640, height: 480,
    webPreferences: { nodeIntegration: true, contextIsolation: false, webSecurity: false, backgroundThrottling: false },
  });
  const timer = setTimeout(() => { console.error('timeout'); app.exit(3); }, 180000);
  ipcMain.once('result', async (_e, result) => {
    clearTimeout(timer);
    let gpu = null;
    try { gpu = await app.getGPUInfo('basic'); } catch (e) { gpu = String(e); }
    const full = { electron_versions: process.versions, gpu_basic: gpu, ...result };
    fs.mkdirSync(path.dirname(out), { recursive: true });
    fs.writeFileSync(out, JSON.stringify(full, null, 1));
    console.log(`wrote ${out}; chrome=${process.versions.chrome} electron=${process.versions.electron}`);
    app.quit();
  });
  const url = pathToFileURL(path.join(__dirname, 'probe.html')).href + '?samples=' +
    encodeURIComponent(pathToFileURL(samples).href + '/');
  await win.loadURL(url);
});
