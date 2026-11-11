// Electron <video> probe for damaged / unfinalized recordings (crash_resilience topic).
// usage: electron.exe <this dir> <list.json> <out.json>
//   list.json: [{"path": "C:/.../x.mkv", "id": "...", "expected_frames": 150}, ...]
// For each file: loadedmetadata or error, duration, seekable ranges, seek to the middle, then play from 0 at
// playbackRate 4 counting requestVideoFrameCallback callbacks and getVideoPlaybackQuality().totalVideoFrames.
const { app, BrowserWindow } = require('electron');
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

const args = process.argv.slice(-2);
const listPath = args[0];
const outPath = args[1];
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');

app.whenReady().then(async () => {
  const show = process.env.PROBE_SHOW === '1';
  const win = new BrowserWindow({
    show, width: 480, height: 270, x: 0, y: 0, skipTaskbar: true, focusable: false,
    webPreferences: { backgroundThrottling: false, contextIsolation: true },
  });
  await win.loadFile(path.join(__dirname, 'probe.html'));
  const files = JSON.parse(fs.readFileSync(listPath, 'utf8'));
  const out = { versions: { electron: process.versions.electron, chrome: process.versions.chrome, node: process.versions.node }, window_shown: show, results: [] };
  for (const f of files) {
    const url = pathToFileURL(f.path).href;
    let r;
    try {
      // watchdog: a probe that never settles is recorded as probe_timeout and the page is reloaded
      r = await Promise.race([
        win.webContents.executeJavaScript(`probe(${JSON.stringify(url)}, ${Number(f.timeout_ms || 20000)})`),
        new Promise(res => setTimeout(() => res({ probe_timeout: true }), 60000))]);
      if (r && r.probe_timeout) await win.loadFile(path.join(__dirname, 'probe.html'));
    } catch (e) {
      r = { probe_exception: String(e) };
    }
    out.results.push({ ...f, ...r });
    fs.writeFileSync(outPath, JSON.stringify(out, null, 1));
  }
  fs.writeFileSync(outPath, JSON.stringify(out, null, 1));
  app.quit();
});
