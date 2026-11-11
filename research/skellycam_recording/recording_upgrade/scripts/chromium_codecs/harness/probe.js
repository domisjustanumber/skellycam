// Capability probe: canPlayType, MediaSource.isTypeSupported, MediaCapabilities.decodingInfo,
// VideoDecoder/AudioDecoder.isConfigSupported, ImageDecoder.isTypeSupported. Posts one JSON result.
'use strict';
const CONTAINER_MIME = {
  mp4: 'video/mp4', webm: 'video/webm', mkv: 'video/x-matroska', mov: 'video/quicktime',
  avi: 'video/x-msvideo', avi2: 'video/avi', ogg: 'video/ogg',
};
// codec id -> { strings: [codec parameter strings], containers: [...] }. Lossless VP9 has no separate codec string.
const VIDEO = {
  av1_main8_420: ['av01.0.08M.08', 'av01.0.05M.08'],
  av1_main10_420: ['av01.0.08M.10'],
  av1_high8_444: ['av01.1.08M.08', 'av01.1.08M.08.0.000'],
  av1_high10_444: ['av01.1.08M.10.0.000'],
  av1_pro8_422: ['av01.2.08M.08.0.100'],
  av1_pro10_422: ['av01.2.08M.10.0.100'],
  av1_pro12_420: ['av01.2.08M.12'],
  vp9_p0_420: ['vp09.00.31.08', 'vp9'],
  vp9_p1_444: ['vp09.01.31.08.03'],
  vp9_p1_422: ['vp09.01.31.08.02'],
  vp9_p2_420_10: ['vp09.02.31.10'],
  vp9_p3_444_10: ['vp09.03.31.10.03'],
  vp8: ['vp8', 'vp08.00.31.08'],
  theora: ['theora'],
  h264_high_420: ['avc1.64001F', 'avc3.64001F'],
  h264_baseline: ['avc1.42E01F'],
  h264_high422: ['avc1.7A001F'],
  h264_high444: ['avc1.F4001F'],
  hevc_main_420: ['hvc1.1.6.L93.B0', 'hev1.1.6.L93.B0'],
  hevc_main10_420: ['hvc1.2.4.L93.B0'],
  hevc_rext_422_10: ['hvc1.4.10.L93.B0'],
  mjpeg: ['mp4v.6C', 'mjpg', 'mjpeg', 'jpeg'],
  ffv1: ['ffv1', 'FFV1'],
  rawvideo: ['raw ', 'rawvideo', 'yuv2', 'I420'],
  prores: ['apch', 'apcn'],
};
const CONTAINERS_FOR = (id) => {
  if (id.startsWith('theora')) return ['ogg', 'mkv', 'mp4', 'webm'];
  return ['mp4', 'webm', 'mkv', 'mov', 'avi', 'ogg'];
};
const AUDIO = {
  opus: [['audio/webm', 'opus'], ['audio/mp4', 'opus'], ['audio/ogg', 'opus'], ['audio/x-matroska', 'opus']],
  flac: [['audio/flac', null], ['audio/mp4', 'flac'], ['audio/ogg', 'flac'], ['audio/x-matroska', 'flac'], ['audio/webm', 'flac']],
  aac_lc: [['audio/mp4', 'mp4a.40.2'], ['audio/aac', null], ['audio/x-matroska', 'mp4a.40.2']],
  mp3: [['audio/mpeg', null], ['audio/mp4', 'mp3'], ['audio/mp4', 'mp4a.69']],
  vorbis: [['audio/ogg', 'vorbis'], ['audio/webm', 'vorbis']],
  pcm: [['audio/wav', '1'], ['audio/wav', null], ['audio/webm', 'pcm'], ['audio/x-matroska', 'pcm'], ['audio/mp4', 'ipcm']],
};
const AUDIO_WC = ['opus', 'flac', 'mp4a.40.2', 'mp3', 'vorbis', 'pcm-s16', 'pcm-f32', 'ulaw', 'alaw'];
const IMAGES = ['image/jpeg', 'image/png', 'image/webp', 'image/avif', 'image/jxl', 'image/gif', 'image/bmp', 'image/heic', 'image/tiff'];

function mimeOf(container, codec) { return codec ? `${CONTAINER_MIME[container]}; codecs="${codec}"` : CONTAINER_MIME[container]; }

async function mc(type, contentType) {
  if (!navigator.mediaCapabilities) return { err: 'no mediaCapabilities' };
  try {
    const r = await navigator.mediaCapabilities.decodingInfo({ type, video: { contentType, width: 1280, height: 720, bitrate: 5000000, framerate: 30 } });
    return { supported: r.supported, smooth: r.smooth, powerEfficient: r.powerEfficient };
  } catch (e) { return { err: e.name + ': ' + e.message }; }
}
async function mcAudio(type, contentType) {
  try {
    const r = await navigator.mediaCapabilities.decodingInfo({ type, audio: { contentType, channels: '2', bitrate: 128000, samplerate: 48000 } });
    return { supported: r.supported, smooth: r.smooth, powerEfficient: r.powerEfficient };
  } catch (e) { return { err: e.name + ': ' + e.message }; }
}
async function vdec(codec, hw) {
  if (!window.VideoDecoder) return { err: 'no VideoDecoder' };
  try {
    const r = await VideoDecoder.isConfigSupported({ codec, codedWidth: 1280, codedHeight: 720, hardwareAcceleration: hw });
    return { supported: r.supported };
  } catch (e) { return { err: e.name + ': ' + e.message }; }
}

(async () => {
  const out = { key: KEY, ua: navigator.userAgent, uaData: null, containersBare: {}, video: {}, audio: {}, audioWebCodecs: {}, webcodecs: {}, imageDecoder: {} };
  try { out.uaData = navigator.userAgentData ? await navigator.userAgentData.getHighEntropyValues(['fullVersionList', 'platformVersion']) : null; } catch { }
  const v = document.createElement('video');
  for (const [k, m] of Object.entries(CONTAINER_MIME)) out.containersBare[k] = { canPlayType: v.canPlayType(m), mse: window.MediaSource ? MediaSource.isTypeSupported(m) : null };
  for (const extra of ['video/x-motion-jpeg', 'video/mp2t', 'application/vnd.apple.mpegurl', 'video/3gpp'])
    out.containersBare[extra] = { canPlayType: v.canPlayType(extra), mse: window.MediaSource ? MediaSource.isTypeSupported(extra) : null };
  for (const [id, strings] of Object.entries(VIDEO)) {
    out.video[id] = {};
    for (const s of strings) {
      for (const c of CONTAINERS_FOR(id)) {
        const mime = mimeOf(c, s);
        out.video[id][mime] = {
          canPlayType: v.canPlayType(mime),
          mse: window.MediaSource ? MediaSource.isTypeSupported(mime) : null,
          mcFile: await mc('file', mime),
          mcMse: await mc('media-source', mime),
        };
      }
      out.webcodecs[`${id}|${s}`] = {
        preferHardware: await vdec(s, 'prefer-hardware'),
        preferSoftware: await vdec(s, 'prefer-software'),
        noPreference: await vdec(s, 'no-preference'),
      };
    }
  }
  const a = document.createElement('audio');
  for (const [id, list] of Object.entries(AUDIO)) {
    out.audio[id] = {};
    for (const [base, codec] of list) {
      const mime = codec ? `${base}; codecs="${codec}"` : base;
      out.audio[id][mime] = { canPlayType: a.canPlayType(mime), mse: window.MediaSource ? MediaSource.isTypeSupported(mime) : null, mcFile: await mcAudio('file', mime) };
    }
  }
  for (const codec of AUDIO_WC) {
    if (!window.AudioDecoder) { out.audioWebCodecs[codec] = { err: 'no AudioDecoder' }; continue; }
    try {
      const cfg = { codec, sampleRate: 48000, numberOfChannels: 2 };
      out.audioWebCodecs[codec] = { supported: (await AudioDecoder.isConfigSupported(cfg)).supported };
    } catch (e) { out.audioWebCodecs[codec] = { err: e.name + ': ' + e.message }; }
  }
  for (const t of IMAGES) {
    if (!window.ImageDecoder) { out.imageDecoder[t] = { err: 'no ImageDecoder' }; continue; }
    try { out.imageDecoder[t] = { supported: await ImageDecoder.isTypeSupported(t) }; } catch (e) { out.imageDecoder[t] = { err: String(e) }; }
  }
  out.features = {
    rvfc: 'requestVideoFrameCallback' in HTMLVideoElement.prototype,
    MediaSource: !!window.MediaSource, ManagedMediaSource: !!window.ManagedMediaSource,
    VideoDecoder: !!window.VideoDecoder, ImageDecoder: !!window.ImageDecoder,
    VideoFrame: !!window.VideoFrame, MediaStreamTrackProcessor: !!window.MediaStreamTrackProcessor,
    webgpu: !!navigator.gpu, offscreenCanvas: !!window.OffscreenCanvas,
  };
  postResult(out);
})();
