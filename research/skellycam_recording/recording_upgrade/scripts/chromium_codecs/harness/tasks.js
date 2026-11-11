// Task lists and the generic per-page driver loop shared by the Chrome (CDP) and Electron runners.
'use strict';
const fs = require('fs');
const path = require('path');
const { MEDIA } = require('./server.js');

// WebCodecs / MSE codec strings for the clips actually encoded (profile matches the stream).
const CODEC_STRING = {
  av1_main8_420: 'av01.0.08M.08', av1_main10_420: 'av01.0.08M.10', av1_high8_444: 'av01.1.08M.08',
  av1_pro8_422: 'av01.2.08M.08', av1_main8_intra: 'av01.0.08M.08',
  vp9_p0_420: 'vp09.00.31.08', vp9_p1_444: 'vp09.01.31.08.03', vp9_p1_422: 'vp09.01.31.08.02',
  vp9_p2_420_10: 'vp09.02.31.10', vp9_p3_444_10: 'vp09.03.31.10.03', vp9_lossless_444: 'vp09.01.31.08.03',
  vp9_lossless_420: 'vp09.00.31.08', vp9_p0_intra: 'vp09.00.31.08', vp8: 'vp8',
  h264_high_420: 'avc1.64001F', h264_high422: 'avc1.7A001F', hevc_main_420: 'hvc1.1.6.L93.B0', hevc_main10_420: 'hvc1.2.4.L93.B0',
  mjpeg_422: 'mp4v.6C', ffv1_422: 'ffv1', theora: 'theora',
};
const MSE_MIME = { fmp4: 'video/mp4', webm: 'video/webm', mkv: 'video/x-matroska' };

function loadManifest() { return JSON.parse(fs.readFileSync(path.join(MEDIA, 'manifest.json'), 'utf8')); }

// pageBase: URL prefix of the harness folder ("http://127.0.0.1:P/h/", "file:///.../harness/", "app://h/")
// mediaBase: URL prefix of the MEDIA folder
function mainTasks({ server, pageBase, mediaBase, label, filter }) {
  const M = loadManifest();
  const q = (o) => Object.entries(o).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');
  const tasks = [{ key: `${label}|probe`, url: `${pageBase}probe.html?${q({ key: `${label}|probe`, server })}`, timeout: 60000 }];
  tasks.push({ key: `${label}|img`, url: `${pageBase}img.html?${q({ key: `${label}|img`, server, base: mediaBase })}`, timeout: 120000 });
  const clips = [...M.clips, ...(M.camera_clips || []).filter((c) => c.file)];
  for (const c of clips) {
    if (filter && !filter(c)) continue;
    const key = `${label}|play|${c.id}`;
    tasks.push({ key, url: `${pageBase}play.html?${q({ key, server, src: mediaBase + c.file, ...(c.nopattern ? { nopattern: 1 } : {}) })}`, timeout: 40000 });
  }
  for (const c of M.clips) {
    if (filter && !filter(c)) continue;
    if (!MSE_MIME[c.container] || !CODEC_STRING[c.codec]) continue;
    const key = `${label}|mse|${c.id}`;
    const mime = `${MSE_MIME[c.container]}; codecs="${CODEC_STRING[c.codec]}"`;
    tasks.push({ key, url: `${pageBase}play.html?${q({ key, server, src: mediaBase + c.file, mode: 'mse', mime })}`, timeout: 40000 });
  }
  for (const [cid, info] of Object.entries(M.codecs)) {
    if (!info.es || !info.es.ok) continue;
    if (filter && !filter({ codec: cid, container: 'es', id: cid })) continue;
    for (const hw of ['prefer-hardware', 'prefer-software']) {
      const key = `${label}|wc|${cid}|${hw}`;
      tasks.push({ key, url: `${pageBase}wc.html?${q({ key, server, es: mediaBase + info.es.file, codec: CODEC_STRING[cid], hw })}`, timeout: 60000 });
    }
  }
  return tasks;
}

const SERVING_CLIPS = ['av1_main8_420__mp4', 'av1_main8_420__fmp4', 'vp9_p0_420__webm', 'vp9_p0_420__mkv', 'h264_high_420__mp4', 'av1_main8_intra__mp4', 'vp9_lossless_444__webm'];
function servingTasks({ server, pageBase, mediaBase, label }) {
  const M = loadManifest();
  const q = (o) => Object.entries(o).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');
  const small = M.clips.filter((c) => SERVING_CLIPS.includes(c.id)).map((c) => {
    const key = `${label}|play|${c.id}`;
    return { key, url: `${pageBase}play.html?${q({ key, server, src: mediaBase + c.file })}`, timeout: 40000 };
  });
  const big = (M.big_clips || []).map((c) => {
    const key = `${label}|play|${c.id}`;
    return { key, url: `${pageBase}play.html?${q({ key, server, src: mediaBase + c.file, frames: c.frames })}`, timeout: 90000 };
  });
  return [...small, ...big];
}

// Benchmark tasks (timing - quiet machine only). quick=true: tiny smoke run.
function benchTasks({ server, pageBase, mediaBase, label, quick, onlyClip }) {
  const BM = JSON.parse(fs.readFileSync(path.join(MEDIA, 'bench', 'bench_manifest.json'), 'utf8'));
  const q = (o) => Object.entries(o).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');
  const tasks = [];
  const ns = quick ? [1, 2] : [1, 4, 8];
  const secs = quick ? 2 : 8;
  for (const c of BM.clips) {
    if (onlyClip && !c.id.includes(onlyClip)) continue;
    for (const n of ns) {
      const key = `${label}|multi|${c.id}|n${n}`;
      tasks.push({ key, url: `${pageBase}bench.html?${q({ key, server, base: mediaBase, clip: c.id, mode: 'multi', n, secs })}`, timeout: 60000 });
    }
    const key = `${label}|seek|${c.id}`;
    tasks.push({ key, url: `${pageBase}bench.html?${q({ key, server, base: mediaBase, clip: c.id, mode: 'seek', count: quick ? 5 : 40 })}`, timeout: 120000 });
    for (const hw of ['prefer-hardware', 'prefer-software']) {
      const k2 = `${label}|wc|${c.id}|${hw}`;
      tasks.push({ key: k2, url: `${pageBase}bench.html?${q({ key: k2, server, base: mediaBase, clip: c.id, mode: 'wc', hw })}`, timeout: 120000 });
    }
  }
  return tasks;
}

// Media-domain (CDP) event collector. feed(method, params) with every CDP event.
function mediaCollector() {
  let players = {};
  return {
    reset() { players = {}; },
    feed(method, p) {
      if (!method || !method.startsWith('Media.')) return;
      const id = p.playerId; if (id === undefined) return;
      const pl = (players[id] ||= { props: {}, errors: [], messages: [] });
      if (method === 'Media.playerPropertiesChanged') for (const pr of p.properties) pl.props[pr.name] = pr.value;
      else if (method === 'Media.playerErrorsRaised') for (const e of p.errors) pl.errors.push(e.errorType + ' ' + e.code + (e.data ? ' ' + JSON.stringify(e.data).slice(0, 300) : ''));
      else if (method === 'Media.playerMessagesLogged') for (const m of p.messages) if (m.level === 'error' || m.level === 'warning') pl.messages.push(m.level + ': ' + String(m.message).slice(0, 300));
    },
    snapshot() {
      const keep = ['kVideoDecoderName', 'kIsPlatformVideoDecoder', 'kIsRangeHeaderSupported', 'kIsStreaming', 'kResolution', 'kFramerate', 'kVideoTracks', 'kTotalBytes', 'kMaxDuration', 'kStartTime', 'kFrameUrl', 'kIsVideoDecryptingDemuxerStream', 'kVideoPlaybackRoughness', 'kVideoPlaybackFreezing'];
      const out = {};
      for (const [id, pl] of Object.entries(players)) {
        const props = {}; for (const k of keep) if (k in pl.props) props[k] = pl.props[k];
        // kVideoTracks can be long - keep codec/profile part only
        if (props.kVideoTracks) props.kVideoTracks = JSON.stringify(props.kVideoTracks).slice(0, 400);
        out[id] = { props, errors: pl.errors.slice(0, 5), messages: pl.messages.slice(0, 5) };
      }
      return out;
    },
  };
}

async function runTasks(tasks, { navigate, waitResult, media, log = console.log, settleMs = 400 }) {
  const results = {};
  let i = 0;
  for (const t of tasks) {
    i++;
    media.reset();
    try { await navigate(t.url); } catch (e) { results[t.key] = { navigateError: String(e) }; continue; }
    const r = await waitResult(t.key, t.timeout);
    await new Promise((res) => setTimeout(res, settleMs));
    r.media = media.snapshot();
    results[t.key] = r;
    const brief = r.timeout ? 'TIMEOUT' : r.fatal ? 'FATAL ' + r.fatal : r.ready ? `${r.ready} seek=${r.seekExact ?? '-'}/${r.seekTotal ?? '-'} ${r.error ? r.error.code + ':' + r.error.message.slice(0, 60) : ''}` : r.outputs !== undefined ? `out=${r.outputs} ok=${r.inOrderCorrect} ${(r.errors || []).join(';').slice(0, 80)}` : 'ok';
    log(`[${i}/${tasks.length}] ${t.key} ${brief}`);
  }
  return results;
}

module.exports = { mainTasks, servingTasks, benchTasks, runTasks, mediaCollector, CODEC_STRING, SERVING_CLIPS, loadManifest };
