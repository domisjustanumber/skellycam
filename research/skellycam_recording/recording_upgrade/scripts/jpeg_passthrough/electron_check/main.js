// Cheap Chromium check (topic jpeg_passthrough, question g): can Electron's <video> play MJPEG in each container,
// and can its image decoders (img / createImageBitmap / WebCodecs ImageDecoder) decode the camera JPEGs
// (incl. DHT-stripped, extra-bytes-before-EOI, losslessly rotated 4:4:0)?
// Usage: electron.exe main.js <config.json> <out.json>
//   config: {"videos": [abs paths], "images": [abs paths]}
const { app, BrowserWindow } = require('electron');
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

const cfgPath = process.argv[process.argv.length - 2];
const outPath = process.argv[process.argv.length - 1];

app.whenReady().then(async () => {
  const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
  const win = new BrowserWindow({ show: false, width: 800, height: 600, webPreferences: { backgroundThrottling: false } });
  await win.loadFile(path.join(__dirname, 'page.html'));
  const result = { versions: process.versions, videos: [], images: [], mime: null };
  try {
    result.mime = await win.webContents.executeJavaScript('mimeChecks()');
    for (const v of cfg.videos) {
      const r = await win.webContents.executeJavaScript(`testVideo(${JSON.stringify(pathToFileURL(v).href)})`);
      r.file = path.basename(v);
      result.videos.push(r);
    }
    for (const im of cfg.images) {
      const b64 = fs.readFileSync(im).toString('base64');
      const r = await win.webContents.executeJavaScript(`testImage(${JSON.stringify(b64)})`);
      r.file = path.basename(im);
      result.images.push(r);
    }
  } catch (e) {
    result.error = String(e);
  }
  fs.writeFileSync(outPath, JSON.stringify(result, null, 1));
  app.quit();
});
