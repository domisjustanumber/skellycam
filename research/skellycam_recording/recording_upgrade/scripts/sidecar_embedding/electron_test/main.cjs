// Electron: load a file:// page, run the locator with real fetch(file://, Range) calls, probe suffix range / HEAD.
const { app, BrowserWindow } = require('electron');
const path = require('path'), fs = require('fs');
const dir = path.resolve(__dirname, '..');
const files = (process.env.LOC_FILES || 'appended.mkv,pyav_fp1_appended.mkv,plain_copy.mkv,stale.mkv').split(',');
app.whenReady().then(async () => {
  const win = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true } });
  await win.loadFile(path.join(__dirname, 'page.html'));
  const results = { electron: process.versions.electron, chrome: process.versions.chrome, runs: [] };
  for (const f of files) {
    const url = 'file:///' + path.join(dir, f).replace(/\\/g, '/');
    const r = await win.webContents.executeJavaScript(`runOne(${JSON.stringify(url)})`);
    r.file = f; results.runs.push(r);
  }
  const url = 'file:///' + path.join(dir, 'appended.mkv').replace(/\\/g, '/');
  results.probes = await win.webContents.executeJavaScript(`probes(${JSON.stringify(url)})`);
  results.fileSize = fs.statSync(path.join(dir, 'appended.mkv')).size;
  fs.writeFileSync(path.join(__dirname, `result_e${process.versions.electron.split('.')[0]}.json`), JSON.stringify(results, null, 1));
  console.log(JSON.stringify(results, null, 1));
  app.quit();
});
