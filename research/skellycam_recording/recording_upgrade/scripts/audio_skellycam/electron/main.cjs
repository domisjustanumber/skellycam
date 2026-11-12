// Electron (35.7.5 / 45.2.3): what Chromium can do with skellycam's candidate audio files.
// env AUDIO_DIRS = ';'-separated dirs of test files (aligned clicks, killed files); AUDIO_OUT = result json.
// env AUDIO_CLOCK_S = seconds for the AudioContext-vs-performance.now drift probe (silent output).
const { app, BrowserWindow } = require('electron');
const path = require('path'), fs = require('fs');
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
app.whenReady().then(async () => {
  const win = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true, backgroundThrottling: false } });
  await win.loadFile(path.join(__dirname, 'page.html'));
  const dirs = (process.env.AUDIO_DIRS || '').split(';').filter(Boolean);
  const files = [];
  for (const d of dirs) for (const f of fs.readdirSync(d).sort()) {
    if (/\.(opus|oga|ogg|mka|webm|flac|wav)$/.test(f)) files.push({ dir: path.basename(d), name: f,
      url: 'file:///' + path.join(d, f).replace(/\\/g, '/'), bytes: fs.statSync(path.join(d, f)).size });
  }
  const results = { electron: process.versions.electron, chrome: process.versions.chrome };
  results.caps = await win.webContents.executeJavaScript('caps()');
  results.files = [];
  for (const f of files) {
    const r = await win.webContents.executeJavaScript(`testFile(${JSON.stringify(f.url)}, ${JSON.stringify(f.dir)})`);
    results.files.push(Object.assign({ dir: f.dir, name: f.name, bytes: f.bytes }, r));
  }
  const clockS = +(process.env.AUDIO_CLOCK_S || 0);
  if (clockS > 0) results.clock = await win.webContents.executeJavaScript(`clockProbe(${clockS})`);
  fs.writeFileSync(process.env.AUDIO_OUT, JSON.stringify(results, null, 1));
  console.log('wrote', process.env.AUDIO_OUT, results.files.length, 'files');
  app.quit();
});
