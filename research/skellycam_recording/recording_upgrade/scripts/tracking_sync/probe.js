// Init script for the tracking-sync desk test. On every animation frame, for each Image panel in PANELS,
// reads back three pixel rows of the drawn 640x360 image and decodes:
//   img: frame-number barcode of the image (y 340: white = 1, grey = 0), null if not readable
//   ann: frame-number barcode of the overlay circles (y 270: green = 1, red = 0), -1 if no overlay, null if garbled
//   bg:  image background present at (620, 300)
// Logs a row [perf ms, panel, img, ann, playhead text] whenever any of them changes; window.__ts.cur has the latest.
// WebGL contexts get preserveDrawingBuffer: true so the canvas can be read back.
(() => {
  const PANELS = ["Image!off", "Image!on"];
  const T = (window.__ts = { log: [], cur: {}, raf: 0 });
  const gc = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (t, o) {
    if (String(t).startsWith("webgl")) o = Object.assign({}, o, { preserveDrawingBuffer: true });
    return gc.call(this, t, o);
  };
  let g = null;
  const read = (pid) => {
    const c = document.querySelector(`[data-testid="panel-mouseenter-container ${pid}"] canvas`);
    if (!c || !c.width) return null;
    if (!g) { const o = document.createElement("canvas"); o.width = 640; o.height = 3; g = o.getContext("2d", { willReadFrequently: true }); }
    // Image panel default: image fitted and centred in the canvas
    const s = Math.min(c.width / 640, c.height / 360), x0 = (c.width - 640 * s) / 2, y0 = (c.height - 360 * s) / 2;
    g.clearRect(0, 0, 640, 3);
    [340, 270, 300].forEach((y, r) => g.drawImage(c, x0, y0 + y * s, 640 * s, 1, 0, r, 640, 1));
    const d = g.getImageData(0, 0, 640, 3).data;
    const px = (x, r) => { const k = (r * 640 + x) * 4; return [d[k], d[k + 1], d[k + 2]]; };
    let img = 0, ann = 0, annNone = 0, annBad = 0;
    for (let b = 0; b < 10; b++) {
      const [r, gg, bb] = px(b * 64 + 32, 0), lum = (r + gg + bb) / 3;
      if (img !== null) {
        if (lum >= 200) img |= 1 << (9 - b);
        else if (!(lum > 70 && lum < 140)) img = null;
      }
      const [ar, ag] = px(b * 64 + 32, 1);
      if (ag > 150 && ar < 100) ann |= 1 << (9 - b);
      else if (ar > 150 && ag < 100) { /* 0 bit */ }
      else annNone++, annBad++;
    }
    const [br, bg_, bb] = px(620, 2);
    const bg = Math.max(br, bb) > 40 && bg_ < 40 && Math.abs(br - bb) > 25;
    if (!bg) img = null;
    return { img, ann: annNone === 10 ? -1 : annBad ? null : ann, bg };
  };
  const tick = () => {
    T.raf++;
    const el = document.querySelector('[data-testid="PlaybackTime-text"] input');
    const ph = el ? el.value : null;
    for (const p of PANELS) {
      let v = null;
      try { v = read(p); } catch (e) { v = null; }
      if (!v) continue;
      const o = T.cur[p];
      if (!o || o.img !== v.img || o.ann !== v.ann || o.bg !== v.bg || o.ph !== ph) {
        T.log.push([performance.now(), p, v.img, v.ann, ph]);
      }
      T.cur[p] = { ...v, ph };
    }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
})();
