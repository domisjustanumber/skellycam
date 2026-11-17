// Indirect probe: does HTMLAudioElement.currentTime include the output latency when the element plays straight to the
// device (no WebAudio), as it evidently does not when routed through MediaElementSource? A silent WAV (so nothing is
// heard; volume stays 1 so Chromium keeps the real sink) is played from 2 s, 8 times per mode; currentTime is polled
// every task for 1 s and a line fitted to the samples after it starts moving gives the performance time P0 at which
// currentTime would have been 2.000. start_ms = P0 - (time of play()). If currentTime counts audible time, direct
// playback starts about one device latency later than MediaElementSource playback.
function silentWavUrl(seconds) {
  const n = seconds * 48000, b = new ArrayBuffer(44 + 2 * n), v = new DataView(b), w = (o, s) => { for (let i = 0; i < 4; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  w(0, 'RIFF'); v.setUint32(4, 36 + 2 * n, true); w(8, 'WAVE'); w(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, 48000, true); v.setUint32(28, 96000, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, 'data'); v.setUint32(40, 2 * n, true);
  return URL.createObjectURL(new Blob([b], { type: 'audio/wav' }));
}
async function elProbe(reps = 8) {
  const ac = new AudioContext({ sampleRate: 48000 }); await ac.resume();
  const src = silentWavUrl(20), out = { outputLatency: null, direct: [], mes: [] };
  for (const mode of ['direct', 'mes']) {
    const el = new Audio(); el.preload = 'auto'; el.src = src; await new Promise((q) => { el.onloadedmetadata = q; });
    if (mode === 'mes') ac.createMediaElementSource(el).connect(ac.destination);
    for (let r = 0; r < reps; r++) {
      el.pause(); await new Promise((q) => { el.onseeked = q; el.currentTime = 2; });
      await new Promise((q) => setTimeout(q, 200));
      const tPlay = performance.now(); el.play(); const pts = [];
      while (performance.now() - tPlay < 1000) { pts.push([performance.now(), el.currentTime]); await new Promise((q) => setTimeout(q, 0)); }
      el.pause();
      const mv = pts.filter((p) => p[1] > 2.05); const n = mv.length, mx = mv.reduce((a, p) => a + p[0], 0) / n, my = mv.reduce((a, p) => a + p[1], 0) / n;
      let sxy = 0, sxx = 0; for (const p of mv) { sxy += (p[0] - mx) * (p[1] - my); sxx += (p[0] - mx) ** 2; }
      const slope = sxy / sxx, P0 = mx + (2 - my) / slope;
      const firstMove = pts.find((p) => p[1] > 2);
      out[mode].push({ start_ms: +(P0 - tPlay).toFixed(2), first_move_ms: firstMove ? +(firstMove[0] - tPlay).toFixed(2) : null, rate: +(slope * 1000).toFixed(5), polls: pts.length });
    }
  }
  out.outputLatency = ac.outputLatency; out.baseLatency = ac.baseLatency; await ac.close();
  return out;
}
