// Init script for the Lichtblick desk test. Logs, with performance.now() times:
//  - every AudioBufferSourceNode.start/stop (buffer rate/length, first click sample, context clock),
//  - AudioContext resume/suspend/state, AudioDecoder.configure arguments,
//  - AudioDecoder input and output timestamps,
//  - the playhead text (PlaybackTime-text input) whenever it changes, on every animation frame,
//  - when the cam0 Image panel shows a white flash frame (one pixel read back each animation frame).
// WebGL contexts are created with preserveDrawingBuffer: true so the pixel can be read back.
(() => {
  const L = (window.__lc = { starts: [], stops: [], ctx: [], dec: [], decIn: [], decOut: [], ph: [], flash: [] });
  const gc = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (t, o) {
    if (String(t).startsWith("webgl")) o = Object.assign({}, o, { preserveDrawingBuffer: true });
    return gc.call(this, t, o);
  };
  let nextId = 0;
  const AB = AudioBufferSourceNode.prototype;
  const origStart = AB.start, origStop = AB.stop;
  AB.start = function (when = 0, offset = 0, duration) {
    const c = this.context, b = this.buffer;
    let click = -1, peak = 0;
    if (b) {
      const d = b.getChannelData(0);
      for (let i = 0; i < d.length; i++) {
        const a = Math.abs(d[i]);
        if (a > peak) peak = a;
        if (click < 0 && a > 0.2) click = i;
      }
    }
    this.__id = nextId++;
    const ts = c.getOutputTimestamp ? c.getOutputTimestamp() : {};
    L.starts.push({ id: this.__id, perf: performance.now(), ctxNow: c.currentTime, when, offset, len: b ? b.length : 0,
      sr: b ? b.sampleRate : 0, ch: b ? b.numberOfChannels : 0, rate: this.playbackRate.value, click, peak,
      outCtx: ts.contextTime, outPerf: ts.performanceTime, baseLatency: c.baseLatency, outputLatency: c.outputLatency });
    return origStart.call(this, when, offset, duration);
  };
  AB.stop = function (when = 0) {
    L.stops.push({ id: this.__id, perf: performance.now(), ctxNow: this.context.currentTime, when });
    return origStop.call(this, when);
  };
  for (const m of ["resume", "suspend"]) {
    const o = AudioContext.prototype[m];
    AudioContext.prototype[m] = function () {
      L.ctx.push({ ev: m, perf: performance.now(), ctxNow: this.currentTime, state: this.state });
      return o.call(this);
    };
  }
  const OrigAC = window.AudioContext;
  window.AudioContext = function (...a) {
    const c = new OrigAC(...a);
    L.ctx.push({ ev: "new", perf: performance.now(), opts: a[0] || null, sampleRate: c.sampleRate, state: c.state });
    c.addEventListener("statechange", () => L.ctx.push({ ev: "state", perf: performance.now(), ctxNow: c.currentTime, state: c.state }));
    return c;
  };
  window.AudioContext.prototype = OrigAC.prototype;
  if (window.AudioDecoder) {
    const OD = window.AudioDecoder;
    window.AudioDecoder = class extends OD {
      constructor(init) {
        const out = init.output;
        super({ ...init, output: (d) => { L.decOut.push([performance.now(), d.timestamp, d.numberOfFrames, d.sampleRate]); out(d); } });
      }
    };
    const od = OD.prototype.decode;
    OD.prototype.decode = function (chunk) { L.decIn.push([performance.now(), chunk.timestamp, chunk.byteLength]); return od.call(this, chunk); };
    const o = OD.prototype.configure;
    AudioDecoder.prototype.configure = function (cfg) {
      L.dec.push({ perf: performance.now(), codec: cfg.codec, sampleRate: cfg.sampleRate, numberOfChannels: cfg.numberOfChannels, hasDescription: cfg.description != null });
      return o.call(this, cfg);
    };
  }
  let g = null, lastF = null;
  const probe = () => {
    const c = document.querySelector('[data-testid="panel-mouseenter-container Image!cam0"] canvas');
    if (!c || !c.width) return;
    if (!g) { const o = document.createElement("canvas"); o.width = o.height = 1; g = o.getContext("2d", { willReadFrequently: true }); }
    // image drawn in "fit" mode, centred: sample image pixel (620, 15), always background (white on flash frames)
    const cw = c.width, ch = c.height;
    let w = cw, h = (cw * 9) / 16;
    if (h > ch) { h = ch; w = (ch * 16) / 9; }
    g.drawImage(c, (cw - w) / 2 + (w * 620) / 640, (ch - h) / 2 + (h * 15) / 360, 1, 1, 0, 0, 1, 1);
    const d = g.getImageData(0, 0, 1, 1).data;
    const on = (d[0] + d[1] + d[2]) / 3 > 200;
    if (on !== lastF) { L.flash.push([performance.now(), on]); lastF = on; }
  };
  let last = null;
  const tick = () => {
    const el = document.querySelector('[data-testid="PlaybackTime-text"] input');
    const v = el ? el.value : null;
    if (v !== last) { L.ph.push([performance.now(), v]); last = v; }
    try { probe(); } catch (e) { /* panel not ready */ }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
})();
