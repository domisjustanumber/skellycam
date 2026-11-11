// Seek-identity probe: does Chromium land on the same frame in an unfinalized file as in its finalized remux?
// argv: <pairs.json> <out.json>. Hidden window, webSecurity off so canvas readback of file:// video is allowed.
const { app, BrowserWindow, ipcMain } = require('electron');
const fs = require('fs'); const path = require('path');

const [listPath, outPath] = process.argv.slice(-2);
app.whenReady().then(() => {
  const w = new BrowserWindow({ show: false, width: 400, height: 300, webPreferences: { nodeIntegration: true, contextIsolation: false, webSecurity: false, backgroundThrottling: false } });
  w.webContents.on('console-message', (...a) => console.log('PAGE', JSON.stringify(a.slice(1)).slice(0,300)));
  ipcMain.on('progress', (e, m) => console.log(m));
  ipcMain.on('done', (e, res) => { res.versions = process.versions; fs.writeFileSync(outPath, JSON.stringify(res, null, 1)); app.quit(); });
  w.loadFile(path.join(__dirname, 'page3.html'), { query: { list: listPath } });
  setTimeout(() => { fs.writeFileSync(outPath, JSON.stringify({ error: 'timeout' })); app.quit(); }, 170000);
});
