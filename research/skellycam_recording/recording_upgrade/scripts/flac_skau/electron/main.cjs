// Runs page.html from file:// with the tests in $FLAC_CFG (written by flac_skau.py); writes $FLAC_OUT.
// Unset ELECTRON_RUN_AS_NODE before launching (VS Code sets it).
const { app, BrowserWindow } = require('electron');
const path = require('path'), fs = require('fs');
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
app.commandLine.appendSwitch('disable-renderer-backgrounding');
app.whenReady().then(async () => {
  const cfg = JSON.parse(fs.readFileSync(process.env.FLAC_CFG, 'utf8'));
  const win = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true, backgroundThrottling: false } });
  win.webContents.setAudioMuted(true);
  await win.loadFile(path.join(__dirname, 'page.html'));
  const res = await win.webContents.executeJavaScript(`runAll(${JSON.stringify(cfg)})`);
  res.electron = process.versions.electron; res.chrome = process.versions.chrome;
  fs.writeFileSync(process.env.FLAC_OUT, JSON.stringify(res, null, 1));
  app.quit();
});
