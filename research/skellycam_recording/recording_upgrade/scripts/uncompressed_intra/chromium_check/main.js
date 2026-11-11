// Cheap Chromium playback check for the uncompressed_intra samples (no timing reported).
// Usage: <electron.exe> research/.../chromium_check/main.js <manifest.json> <out.json>
// For each sample: canPlayType(mime) (video), whether <video> reaches loadeddata (first frame drawn to a canvas),
// whether a seek to frame 5 completes with a changed picture, and the MediaError; for images whether <img> decodes.
// Run with ELECTRON_RUN_AS_NODE unset (VS Code terminals set it to 1).
const { app, BrowserWindow, ipcMain } = require('electron');
const fs = require('fs');
const path = require('path');
const args = process.argv.slice(2).filter(a => !a.startsWith('--') && !a.endsWith('main.js') && a !== '.');
const [manifestPath, outPath] = args.slice(-2);
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
app.whenReady().then(async () => {
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8')).filter(m => m.made);
  const win = new BrowserWindow({ show: false, width: 800, height: 600,
    webPreferences: { nodeIntegration: true, contextIsolation: false, webSecurity: false, backgroundThrottling: false } });
  ipcMain.once('done', (_e, results) => {
    const out = { electron: process.versions.electron, chrome: process.versions.chrome, platform: process.platform,
      gpu_feature_status: app.getGPUFeatureStatus(), results };
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    fs.writeFileSync(outPath, JSON.stringify(out, null, 1));
    console.log('wrote', outPath, 'electron', process.versions.electron, 'chrome', process.versions.chrome);
    app.quit();
  });
  await win.loadFile(path.join(__dirname, 'page.html'));
  win.webContents.send('run', manifest);
});
