// Electron runner: loads page.html from file://, runs the tests described in $AUDIO_CFG (JSON), writes $AUDIO_OUT.
// Audio is muted at the WebContents level; the page also routes element audio through a zero-gain node.
const { app, BrowserWindow } = require('electron');
const path = require('path'), fs = require('fs');
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
app.commandLine.appendSwitch('disable-backgrounding-occluded-windows');
app.commandLine.appendSwitch('disable-renderer-backgrounding');
app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');
app.whenReady().then(async () => {
  const cfg = JSON.parse(fs.readFileSync(process.env.AUDIO_CFG, 'utf8'));
  const win = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true, backgroundThrottling: false } });
  win.webContents.setAudioMuted(true);
  await win.loadFile(path.join(__dirname, 'page.html'));
  const res = await win.webContents.executeJavaScript(`runAll(${JSON.stringify(cfg)})`);
  res.electron = process.versions.electron; res.chrome = process.versions.chrome;
  fs.writeFileSync(process.env.AUDIO_OUT, JSON.stringify(res, null, 1));
  app.quit();
});
