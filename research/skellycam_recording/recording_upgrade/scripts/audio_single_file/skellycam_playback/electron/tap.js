// AudioWorklet tap just before the destination: passes audio through and reports each click as
// [context frame of the click's peak sample, peak]. A click = first |x| > 0.3, then the argmax over the next 480 samples;
// nothing more is reported for 4,800 samples after a peak (Opus ringing).
class Tap extends AudioWorkletProcessor {
  constructor() { super(); this.until = -1; this.best = 0; this.bestF = 0; this.quiet = -1; }
  process(inputs, outputs) {
    const inp = inputs[0], out = outputs[0];
    if (!inp.length) return true;
    for (let c = 0; c < out.length; c++) out[c].set(inp[Math.min(c, inp.length - 1)]);
    const x = inp[0], f0 = currentFrame;
    for (let i = 0; i < x.length; i++) {
      const f = f0 + i, v = Math.abs(x[i]);
      if (this.until < 0) {
        if (v > 0.3 && f > this.quiet) { this.until = f + 480; this.best = v; this.bestF = f; }
      } else {
        if (v > this.best) { this.best = v; this.bestF = f; }
        if (f >= this.until) { this.port.postMessage([this.bestF, this.best]); this.until = -1; this.quiet = this.bestF + 4800; }
      }
    }
    return true;
  }
}
registerProcessor('tap', Tap);
