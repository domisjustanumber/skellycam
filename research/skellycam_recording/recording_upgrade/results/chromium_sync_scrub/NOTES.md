# chromium_sync_scrub - synchronized, frame-accurate playback and scrubbing in Chromium/Electron (G9)

Study date 2026-11-09, machine Gerald (Windows 11, i7-14700K, RTX 3070, driver 610.88). Branch dom/research.
Labels: **measured** (result file cited), **source** (spec / vendor / library source, accessed 2026-11-09), **code** (file:line), **inferred** (reasoning, kept short).
TIMING RULE: this stage reports **no timing, throughput or CPU numbers**. Every timing question is a benchmark script listed in §9, to be run later on a quiet machine.

## Summary

- **Today's UI is not frame-accurate** (measured, harness re-implementation of its seek math): it seeks with `currentTime = frame / fps` (frame start) using an fps from the timestamp CSV (code §2). On CFR 30 fps GOP files that showed the requested frame in 360/600 random seeks (all misses one frame early); on real VFR capture timing 34-35/200; on a clip built like today's recordings (32.9 fps header, UI fps 30) 10/400, up to 52 frames off (§6.2).
- **Seeking to the middle of the frame interval from the file's real pts is exact** in every CFR, VFR, GOP and all-intra file, for AV1, VP9 and H.264, MP4, fragmented MP4 and WebM, in Electron 35.7.5 and 45.2.3, over 200 random seeks and 122 steps per file (measured §6.2-6.3); the one exception is a pair of frames captured 0.011 ms apart (§6.4). The cause of the misses is Chromium's seek arithmetic (seek target truncated to microseconds; last frame with timestamp <= target is kept) (code §4).
- **WebCodecs fed from a recorder index (byte offsets inside the MP4/WebM) and JPEG-sequence paths are exact by construction** and returned the requested frame in every run (every frame whose pattern was readable), including two VFR frames captured 0.011 ms apart where `<video>` fails (measured §6.4). No `flush()` was ever needed with `optimizeForLatency` (measured).
- The cameras' own JPEG bytes decode in Chromium with no transcode; `createImageBitmap` output is bit-identical to OpenCV/libjpeg-turbo (measured §6.5). mp4box.js 2.4.1 reproduces the recorder index exactly for all 20 MP4s (measured §6.6).
- Electron 45.2.3 (Chromium 156) vs 35.7.5 (Chromium 134): same codec support; adds JPEG XL to `ImageDecoder`; fixes a Chromium 134 bug where seeking exactly onto the last frame leaves the element stuck on it; improves exact-pts seeks. Mid-frame and index paths are identical in both (measured §6.1, §6.4).
- Specs give no frame-exactness guarantee for `<video>`; rVFC reports the presented frame's PTS but is best effort; WebCodecs timestamps are integer microseconds chosen by the app (source §3).
- Timing questions (seek/step latency, N-stream sync spread while playing, scrub frame rate, CPU/memory at N = 4 and 8 at 1080p) are scripted and smoke-tested, not measured: §9.


## 1. Versions tested

| item | value | label |
|---|---|---|
| Electron (skellycam-ui / freemocap pin) | 35.7.5 = Chromium 134.0.6998.205, Node 22.16.0 | measured: `functional/e35/caps.json` (`versions`) |
| Electron newest stable | 45.2.3 = Chromium 156.0.8078.80, Node 24.22.2 | measured: `functional/e45/caps.json` |
| GPU seen by Chromium | NVIDIA vendor 0x10de device 0x2484 (RTX 3070) active, driver 32.0.16.1088; plus Microsoft Basic Render (0x1414). No Intel device listed | measured: `functional/e35/caps.json` (`gpu_info.gpuDevice`) |
| mp4box.js | npm `mp4box@2.4.1` (published 2026-06-19), https://registry.npmjs.org/mp4box/-/mp4box-2.4.1.tgz, installed with `--ignore-scripts` into the scratchpad | source: `npm view mp4box@2.4.1 time` |
| Clip generator | Python 3.12, PyAV 18.0.0 (libavcodec 62.28.102), OpenCV 4.12.0, SVT-AV1 v4.1.0, libvpx-vp9, libx264 (from the skellycam venv, read-only) | measured: `clips_summary.json` (`generator`) |


## 2. How the current UI syncs today (code)

`skellycam-ui/src/components/playback/SyncedVideoPlayer.tsx` and `skellycam-ui/src/contexts/PlaybackContext.tsx` are byte-identical in HEAD (55f851e4) and `upstream/sfn26` (765bf82d) (code: `git diff --quiet HEAD upstream/sfn26 -- <both files>` exits 0). Only `playback_router.py` differs.

- One `<video>` element per camera, `src` = the backend stream URL, `preload="auto"`, muted (code: SyncedVideoPlayer.tsx:648-656).
- The first video is the "leader" and is the only clock (code: :61-74, :254-257).
- During playback a `requestAnimationFrame` loop reads `leader.currentTime` and computes `frame = leader.currentTime * fps` (code: :367-378). `requestVideoFrameCallback` is not used anywhere in the UI (code: grep of `skellycam-ui/src`).
- Followers are checked only every 15 rAF ticks, and corrected only when `|follower.currentTime - leader.currentTime| > 2 / fps`, by assigning `follower.currentTime = leaderTime` (a seek while playing) (code: :99-104, :417-431). Up to 2 frames of drift is tolerated by design.
- Paused seek, frame step and slider drag all set `el.currentTime = frame / fps` on every element: the **start** of the frame interval, not its middle (code: `seekAllToFrame` :332-340, `handleSeekDrag` :506-507, `handleFrameStep` :523-526). The slider calls `onSeekDrag` on every `onChange` of an `<input type="range">`, with no gating on `video.seeking` (code: PlaybackControls.tsx:176-193).
- `fps` is `recordingFps` from the recording list. HEAD computes it as `round(frame_count / duration, 1)` from a timestamp CSV (code: playback_router.py:173-233, line 230); upstream computes `(n - 1) / duration` from the multiframe timing file (code: `upstream/sfn26:skellycam/core/recorders/videos/recording_statistics.py:13-22`). The file's own timeline is never consulted. The Python recorder writes a CFR header of ~32.9 fps for a real 30.0 fps capture (measured in the prior study: `research/skellycam_recording/REPORT.md:28`, `research/skellycam_recording/results/real_recording_20261109/RESULTS.md:99`). So with fps = 30.0 from the CSV, `currentTime = frame/30` lands on file frame ~`frame*32.9/30` (inferred; measured with a clip built that way, `hdr329`, in §6.2).
- `totalFrames = floor(duration * fps)`, minimum over all videos (code: :451-464). With a ~9 % short file timeline and the CSV fps, roughly the last 9 % of frames cannot be reached from the slider (inferred from those numbers; not run against a real recording).
- The overlay time text uses only the **first camera's** timestamp array for every tile (`Object.keys(ts)[0]`) (code: :281-309). The per-camera arrays are fetched (code: PlaybackContext.tsx:61-78) but are not used for seeking.
- Backend: `FileResponse` (code: playback_router.py:432; upstream line 272). Starlette 1.3.1 serves `Range` requests (code: `.venv/Lib/site-packages/starlette/responses.py:361-372`), so `<video>` can seek over HTTP. HEAD transcodes non-web codecs to a `.web.mp4` sidecar (code: :115-139); upstream removed that and serves files as they are (code: upstream playback_router.py:260).

## 3. What the standards guarantee (source, accessed 2026-11-09)

| topic | quote | where |
|---|---|---|
| currentTime is a double in seconds; setting it seeks | "On setting, ... it must set the official playback position to the new value and then seek to the new value. The new value must be interpreted as being in seconds." | HTML Living Standard, https://html.spec.whatwg.org/multipage/media.html#dom-media-currenttime |
| a paused element shows "the frame" at the position | "When the video element is paused ... The video element represents the frame of video corresponding to the current playback position." | same page, `video` element rendering rules |
| which frame is "corresponding" at an exact frame boundary | no definition found (searched the page text for "frame-accurate", "accurate", "corresponding") | same page; NOT VERIFIED beyond that search |
| a seek only promises decoded data at the position | "Wait until the user agent has established whether or not the media data for the new playback position is available, and, if it is, until it has decoded enough data to play back that position." | same page, seek algorithm |
| fastSeek may snap to a key frame | "If the approximate-for-speed flag is set, adjust the new playback position to a value that will allow for playback to resume promptly ... the user agent could snap to a nearby key frame" | same page, seek algorithm. `fastSeek` is absent in both Electrons (measured: `caps.json` `api.fastSeek=false`) |
| rVFC `mediaTime` is the shown frame's PTS | "mediaTime ... The media presentation timestamp (PTS) in seconds of the frame presented (e.g. its timestamp on the video.currentTime timeline)." | WICG video-rvfc, Draft Community Group Report 2 August 2024, https://wicg.github.io/video-rvfc/ |
| rVFC is best effort | "a callback can occasionally be fired one v-sync late ... if there is a heavy load on the main thread, we might not get a callback for every frame (as measured by a discontinuity in the presentedFrames)." | same |
| WebCodecs timestamps are integer microseconds | "Presentation Timestamp: An integer value, in microseconds, indicating when a VideoFrame ... is expected to be presented" | W3C WebCodecs, Working Draft 8 November 2026, https://www.w3.org/TR/2026/WD-webcodecs-20261108/ |
| decoder output is in presentation order | "VideoDecoder requires that frames are output in the order they expect to be presented, commonly known as presentation order." | same, `decode()` note |
| flush forces a key frame next | `flush()`: "Set [[key chunk required]] to true." | same |
| latency hint | "optimizeForLatency ... Hint that the selected decoder SHOULD be configured to minimize the number of EncodedVideoChunks that have to be decoded before a VideoFrame is output." | same, VideoDecoderConfig |
| AV1 chunk format | "EncodedVideoChunk [[internal data]] is expected to be a sequence of Open Bitstream Units (OBUs) compliant to the "low-overhead bitstream format" ... forming a single temporal unit" and "description is not used for this codec." | https://w3c.github.io/webcodecs/av1_codec_registration.html |
| AVC chunk format | "If the bitstream is in avc format, [[internal data]] is assumed to be in canonical format, as defined in [iso14496-15] section 5.3.2." | https://w3c.github.io/webcodecs/avc_codec_registration.html |

Reading of the table (inferred): `<video>` has **no frame-exactness guarantee**. rVFC tells you **which** frame was shown (its PTS), but not for every frame. WebCodecs is exact by construction: the app chooses the chunk and gets its own integer timestamp back.

## 4. What Chromium does on a seek (code, Chromium source at the exact release tags, from chromium.googlesource.com)

- `WebMediaPlayerImpl::Seek(double seconds)` calls `DoSeek(base::Seconds(seconds), true)` (code: `third_party/blink/renderer/platform/media/web_media_player_impl.cc:1076-1079` @134.0.6998.205; `:1115` @156.0.8078.80).
- `base::Seconds(double)` is `TimeDelta::FromInternalValue(ClampedNumeric(n) * kMicrosecondsPerSecond)` (code: `base/time/time.h:902` @134, `:908` @156). The double-to-int64 step is a `saturated_cast`, documented as "analogous to static_cast<> for numeric types" (code: `base/numerics/safe_conversions.h:195` @156), i.e. truncation toward zero (inferred from that comment).
- Demuxed timestamps are converted with `av_rescale_q(timestamp, time_base, kMicrosBase)` (code: `media/ffmpeg/ffmpeg_common.cc:110-114` @134, `:124` @156). `av_rescale_q` rounds to nearest (inferred from FFmpeg's documented default rounding; NOT VERIFIED against the FFmpeg revision inside Chromium).
- After a seek, the renderer keeps the **last decoded frame whose timestamp <= the seek target** as the frame to paint (`if (!sink_started_ && frame->timestamp() <= start_timestamp_) algorithm_->Reset()`), and drops frames that end before the target (code: `media/renderers/video_renderer_impl.cc:603-632, 967-981` @134; `:637-660` @156).
- Consequence (inferred, then measured in §6.2): a seek to exactly `k / fps` or to exactly the container PTS can show frame k-1 whenever the container PTS rounds **up** to whole microseconds while the seek target truncates **down**. Example: 90 kHz MP4, frame 2 at 6000/90000 s -> 66667 us; `2/30` -> 66666 us -> frame 1 is shown. A target in the middle of the frame interval is immune to both roundings.

## 5. Harness

Scripts: `research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/`.

| file | role |
|---|---|
| `gen_clips.py` | builds clips from the real corpus: decode camera JPEG (OpenCV), burn a 16-bit index pattern into the top strip (32 cells, each bit as bit + NOT bit, strip height = cell width), encode with PyAV using explicit per-frame pts, then demux again and write the "recorder index" (per frame: pts, keyframe flag, byte offset and size of the coded sample **inside the container file**, checked byte-exact against the demuxed packet) |
| `harness/` (`main.cjs`, `server.cjs`, `index.html`, `harness.mjs`, `package.json`) | Electron app. Node `http` server with single-range `Range` support; one window (1600x900; `sandbox`, `contextIsolation`, no `nodeIntegration` as in skellycam-ui `electron/main/services/window-manager.ts:24-29`, plus `backgroundThrottling:false`); the page runs one test or a batch and POSTs JSON; main adds versions, GPU info and `app.getAppMetrics()` samples. Page log lines go to `<out>.log`. Electron profile goes to the scratchpad (`app.setPath('userData', ...)`) |
| `run_suite.py` | runs `functional`, `bench_seek`, `bench_step`, `bench_sync`, `bench_scrub` in Electron 35 or 45; removes `ELECTRON_RUN_AS_NODE` from the child environment (this host sets it; Electron then runs as plain Node and `require('electron')` fails - measured on the first launch); samples `nvidia-smi --query-gpu=encoder.stats.sessionCount,utilization.gpu,utilization.decoder,memory.used` before and after every launch |
| `compare_jpeg_decode.py` | pixel comparison of Chromium's JPEG decode against OpenCV and PyAV |
| `summarize.py` | `functional` -> `functional_tables.md`; `bench` -> `bench/bench_tables.md` |

Playback paths in `harness.mjs`:

| path id | what it does |
|---|---|
| `video` | one `<video>`; seek by `currentTime`; after `seeked` (+ rVFC, 300 ms grace) the frame is read back with `drawImage(video)`; rVFC `mediaTime` mapped to the nearest container pts is recorded too |
| `webcodecs` | `VideoDecoder` (`optimizeForLatency:true`) fed from the recorder index: one `Range` request for [keyframe .. k], chunks sliced from it; decode from the previous keyframe, or continue if already inside the GOP; output matched by timestamp; `flush()` only as a fallback (counted) |
| `jpeg-range-bitmap`, `jpeg-range-imagedecoder` | MJPEG frames concatenated in one `.mjpeg` with an index; one `Range` request per frame (blocks of 15 when playing); decoded by `createImageBitmap(Blob)` or `ImageDecoder` |
| `jpeg-folder-bitmap`, `jpeg-folder-imagedecoder` | same, one file per frame (`frames/frame_NNNNNN.jpg`) |
| sync `video-free` | N `<video>` started together, no correction |
| sync `video-leader` | port of SyncedVideoPlayer's correction (2-frame tolerance, every 15 rAF ticks) |
| sync `wc-master`, `jpeg-master-*` | one rAF master clock; each stream keeps a decode-ahead queue (<= 8 frames); every tick each canvas shows the newest frame with pts <= clock |
| scrub `video-ui` | simulated input event every 16 ms; each sets `currentTime = frame/fps` on all N elements (today's UI) |
| scrub `video-gated` | same, but a new seek is only issued when the element is not `seeking` (the latest target is kept) |
| scrub `webcodecs`, `jpeg-*` | each stream decodes the latest target whenever it is idle |

Seek-target modes for `<video>`: `mid` = midpoint between this and the next container pts; `ui` = `k / nominal_fps` (today's UI); `ptsexact` = exactly the container pts; `cfrmid` = `(k + 0.5) / nominal_fps`.

Clips (media only under `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/chromium_sync_scrub/clips/`; per-clip metadata in `clips_summary.json`):

| content | source frames | frames | timing |
|---|---|---|---|
| `c720p30` | corpus `c930e_720p_flash`, 600 distinct real frames | 600 | CFR 30 |
| `c1080p30` | corpus `c922_1080p`, 19 real frames **looped** (the index pattern is still unique per frame) | 600 | CFR 30 |
| `c720p60` | corpus `c922_720p60`, 10 real frames **looped** | 600 | CFR 60 |
| `vfr720p` | corpus `c930e_720p_flash`, all 891 frames | 891 | **real capture times** (`mf_sample_time_100ns` from `research/usb_cameras/results/windows/Gerald/timing/flash_run1_repositioned/capture/vid_046d_pid_0843_mi_00_8_39dec205_0_0000.frames.jsonl`): mostly 32 ms with a 48 ms step every 12-13 frames, and one 0.011 ms pair (frames 81/82). Frame byte sizes match the corpus 891/891 (measured) |
| `hdr329` | as `c720p30` | 600 | pts = k/32.9 (today's too-fast CFR header) while the UI's fps is 30 |

Variants: `av1_gop.mp4/.webm` (SVT-AV1 preset 10, crf 35, g = fps), `av1_intra.mp4` (g = 1), `av1_gop_frag.mp4` (fragmented MP4, `frag_keyframe+empty_moov+default_base_moof`), `vp9_gop.webm/.mp4` (libvpx realtime, cpu-used 8, crf 33, g = fps), `vp9_intra.webm`, `h264_gop.mp4` / `h264_intra.mp4` (libx264 veryfast crf 23, **bf=0**), and `mjpeg/` (pattern frames re-encoded by OpenCV, q90 4:2:2, as `.mjpeg` + index and as a folder). MP4 time base 1/90000, WebM 1/1000 (Matroska milliseconds). In the VFR WebM files one pts had to be bumped by 1 ms to stay strictly increasing (the 0.011 ms pair) (measured: `clips_summary.json`, `pts_adjusted_for_monotonic`).

Generation checks (measured, `clips_summary.json`): every coded sample of all 35 video files was found byte-exact at its recorded offset (`all_samples_byte_exact`); decode order equals pts order in every file; libavcodec read the right index on 6-8 sample frames per file (`pyav_pattern_check`). WebCodecs codec strings come from the stream (avcC bytes, av1C `seq_level_idx`, VP9 level table from https://www.webmproject.org/vp9/levels/) and match mp4box.js's strings for every MP4 (§6.6).

## 6. Functional results (no timing)

Full per-clip tables: `functional_tables.md` (generated by `summarize.py functional` from `functional/e35/*.json` and `functional/e45/*.json`). Raw page logs: `functional/e*/*.json.log`. CPU/memory samples were removed from the functional JSONs (shared machine).

### 6.1 Codec and API support (measured: `functional/e35/caps.json`, `functional/e45/caps.json`)

| check | Electron 35.7.5 / Chromium 134 | Electron 45.2.3 / Chromium 156 |
|---|---|---|
| `canPlayType` for every clip's codec string (AV1 MP4/WebM, VP9 MP4/WebM, H.264 MP4) | `probably` for all | same |
| `VideoDecoder.isConfigSupported`, 720p30 / 1080p30 / 720p60, `prefer-hardware` and `prefer-software` | `true` for AV1, VP9, H.264 | same |
| `mediaCapabilities.decodingInfo` (type `file`) for AV1, VP9, H.264 at 720p30 / 1080p30 / 720p60 | supported / smooth / powerEfficient | same |
| VP8 (`webm; vp8`) | `prefer-hardware` false; not powerEfficient | same |
| HEVC `hvc1.1.6.L93.B0` | `canPlayType` probably; `prefer-hardware` true, `prefer-software` **false** | same |
| `ImageDecoder.isTypeSupported` | jpeg, png, webp, avif, gif, bmp true; **jxl false** | same, **jxl true** |
| `requestVideoFrameCallback` | present | present |
| `fastSeek` | absent | absent |
| `ManagedMediaSource` | absent | absent |
| `isSecureContext` on `http://127.0.0.1` (needed for WebCodecs) | true | true |

`powerEfficient` and `prefer-hardware: true` are what Chromium reports; whether decode really ran on NVDEC was **not verified** (no GPU-decoder counters were read in this stage; `nvidia-smi utilization.decoder` is sampled by the bench runner).

### 6.2 Seek accuracy, random seeks (measured: `functional/e*/seek_batch.json`; 200 seeks per clip and path, seed 1, uniform over all frames; "exact" = index pattern read back equals the requested frame)

Aggregated over files of the same family (sum of exact / sum of seeks). e35 | e45.

| content | files | `<video>` mid | `<video>` ui (today's UI) | `<video>` ptsexact | WebCodecs + recorder index | JPEG (4 paths) |
|---|---|---|---|---|---|---|
| c720p30 | GOP MP4 (AV1, VP9, H.264) | 600/600 \| 600/600 | 360/600 \| 360/600 (all misses -1) | 360/600 \| 360/600 (all -1) | 600/600 \| 600/600 | 800/800 \| 800/800 |
| c720p30 | GOP fragmented MP4 (AV1) | 200/200 \| 200/200 | 120/200 \| 120/200 | 120/200 \| 120/200 | 200/200 \| 200/200 | |
| c720p30 | GOP WebM (AV1, VP9) | 400/400 \| 400/400 | 240/400 \| 240/400 | 390/400 \| 394/400 | 400/400 \| 400/400 | |
| c720p30 | all-intra MP4 (AV1, H.264) | 400/400 \| 400/400 | 400/400 \| 400/400 | 400/400 \| 400/400 | 400/400 \| 400/400 | |
| c720p30 | all-intra WebM (VP9) | 200/200 \| 200/200 | 200/200 \| 200/200 | 198/200 \| 200/200 | 200/200 \| 200/200 | |
| c1080p30 | GOP MP4 + WebM + frag (5 files) | 1194/1200 \| 1194/1200 | 714/1200 \| 714/1200 | - | 1194/1200 \| 1194/1200 | 800/800 \| 800/800 |
| c1080p30 | all-intra (3 files) | 600/600 \| 600/600 | 600/600 \| 600/600 | - | 600/600 \| 600/600 | |
| c720p60 | GOP MP4 (AV1, H.264) | 400/400 \| 400/400 | **116/400 \| 268/400** | - | 400/400 \| 400/400 | 800/800 \| 800/800 |
| c720p60 | GOP WebM (VP9) | 200/200 \| 200/200 | 136/200 \| 136/200 | - | 200/200 \| 200/200 | |
| c720p60 | all-intra (AV1 MP4, VP9 WebM) | 400/400 \| 400/400 | 398/400 \| 400/400 | - | 400/400 \| 400/400 | |
| vfr720p | GOP MP4 (AV1, H.264) | 400/400 \| 400/400 | 68/400 \| 68/400 | 70/400 \| 76/400 | 400/400 \| 400/400 | 800/800 \| 800/800 |
| vfr720p | GOP WebM (AV1, VP9) | 400/400 \| 400/400 | 70/400 \| 68/400 | **42/400 \| 392/400** | 400/400 \| 400/400 | |
| vfr720p | all-intra MP4 (AV1) | 200/200 \| 200/200 | 34/200 \| 34/200 | 200/200 \| 200/200 | 200/200 \| 200/200 | |
| hdr329 | GOP MP4 (H.264, AV1) | 400/400 \| 400/400 | **10/400 \| 10/400** (+1 ... +52 frames) | - | 400/400 \| 400/400 | 800/800 \| 800/800 |

Notes on the table (each measured unless labelled):
- The 6 c1080p30 misses in `mid` and WebCodecs are the same 2 frames per AV1 file (k = 66 and 306), reported "unreadable", not wrong. libavcodec (PyAV 18) also cannot read the pattern on frames 66, 306 and 322 of `c1080p30/av1_gop.mp4`: the crf-35 encode damaged the pattern cells. It is a test-pattern artefact, not a seek error (measured: one-off PyAV check, command in §8).
- `ui` and `ptsexact` misses on CFR GOP files are always **one frame early** (-1). On all-intra files the same targets are exact. This matches §4: from a key frame the decoder passes frame k-1 (timestamp <= the truncated target) and keeps it; with all-intra the demuxer starts at frame k itself, so there is no earlier frame to keep (mechanism inferred from code §4; outcome measured).
- WebM (1 ms time base) makes `ptsexact` mostly work for CFR 30 (pts in whole ms are exact in microseconds) but not `ui` (`k/30` in ms rounds up for 1/3 of frames). MP4 at 1/90000 makes both fail for ~40 % of frames.
- Electron 45 fixes part of the 60 fps MP4 `ui` case (116 -> 268/400) and almost all of the VFR WebM `ptsexact` case (42 -> 392/400); everything else is identical between the two versions.
- In the VFR clip `ui` (frame/30) is wrong for ~83 % of seeks (mostly +1 or +2 frames, a few -1, one -12) and `cfrmid` by +1 to +3 for ~90 %: assuming a constant rate on real capture timing gives the wrong frame. `mid` from the real pts is exact.
- `hdr329` reproduces today's recordings (file header 32.9 fps, UI fps 30): `ui` lands on the right frame 10 times in 400, and the error grows linearly to +52 frames at the end of the 600-frame clip.
- rVFC fired after every `<video>` seek except where noted in `functional_tables.md`, and the frame index derived from rVFC `mediaTime` (nearest container pts) equalled the burned-in index whenever the pattern was readable (`mediatime_idx_equals_pattern`).
- WebCodecs needed **no** `flush()` fallback in any run (`flushes: 0` everywhere): with `optimizeForLatency: true`, every requested frame came out without flushing, for AV1, VP9 and H.264, GOP and intra, in both Electrons.

### 6.3 Single-frame steps (measured: `functional/e*/step_batch.json`; from random starts, 20 steps forward then 40 back; 122 steps per clip)

| content | files | `<video>` ui (today's UI) | `<video>` mid | WebCodecs | JPEG (range + ImageDecoder) |
|---|---|---|---|---|---|
| c720p30, c1080p30 | GOP (AV1 MP4, VP9 WebM, H.264 MP4) | 82/122 per file (fwd 27/40, back 54/80) \| same | 122/122 \| same | 122/122 \| same | 122/122 \| same |
| c720p30, c1080p30 | AV1 all-intra | 122/122 \| same | 122/122 | 122/122 | |
| c720p60 | GOP MP4 (AV1, H.264) | 41/122 per file \| 81/122 | 122/122 | 122/122 | 122/122 |
| c720p60 | GOP WebM (VP9) | 81/122 \| 81/122 | 122/122 | 122/122 | |
| vfr720p | GOP and intra | **0/122** per file (+1 / +2) \| same | 122/122 | 122/122 | 122/122 |

Backward steps across a GOP boundary are exact for WebCodecs (re-decode from the previous key frame) and for `<video>` with mid-frame targets.

### 6.4 Deterministic edge cases (measured: `functional/e*/targeted.json`, frame lists given explicitly)

| case | e35 | e45 |
|---|---|---|
| VFR frames 81/82 captured **0.011 ms** apart (90 kHz MP4: 1 tick apart; WebM: bumped to 1 ms apart), seek list 79,80,81,82,83,84,82,81,80, `mid` | MP4 9/9; WebM 5/9 (81 -> 80, 82 -> 81) | MP4 7/9 (82 -> 81); WebM 7/9 (82 -> 81) |
| same, WebCodecs | 9/9 for all 5 VFR files | 9/9 |
| seeks after a seek that lands exactly on the last frame (list 300,599,586,8,300,598,300,599,0,300) | **stuck**: in `c720p30/av1_gop.webm` and `vp9_intra.webm` (`ptsexact`) and `c720p60/av1_intra.mp4` (`ptsexact` and `ui`), every later seek kept showing frame 599 and no rVFC fired (3/10 exact) | not reproduced: 10/10 in the same cases |
| same with `mid` targets | 10/10 everywhere | 10/10 |

The "stuck at the last frame" case explains the two `13:1, 591:1` misses in the random runs (the random sequence visits frame 599). Its cause inside Chromium 134 was NOT VERIFIED. Today's UI can produce the triggering target: End key -> `seekAllToFrame(totalFrames - 1)` -> `currentTime = (totalFrames-1)/fps` (code: SyncedVideoPlayer.tsx:541-544), equal to the last pts in a CFR file whose rate equals the UI fps (inferred).

### 6.5 The cameras' own JPEG bytes in Chromium (measured: `functional/e*/jpegcompat.json`, `functional/jpeg_decode_compare.json`)

- All corpus MJPEG frames tested (30 per flash set, all 19/19/19/10/11 of the short sets, including `generic_1080p` with extra bytes before EOI) decoded with both `createImageBitmap` and `ImageDecoder`, 0 errors, in both Electrons. `ImageDecoder` returns `VideoFrame` format `I422` (the cameras' 4:2:2).
- `createImageBitmap` -> canvas -> `getImageData` is **bit-identical** to OpenCV 4.12 `imdecode` (libjpeg-turbo) on frame 0 of all 7 sets (max abs diff 0, 100 % exact), in both Electrons.
- `ImageDecoder` -> `VideoFrame` -> `drawImage` differs from OpenCV by up to 24 levels (81.8-97.0 % of samples exact): the YUV->RGB step is done by Chromium's canvas path, not libjpeg. OpenCV vs PyAV (libavcodec mjpeg) differ by up to 24 levels too.
- So JPEG files written straight from camera bytes (G1) can be shown in the UI without any transcode (measured for these 7 camera modes).

### 6.6 mp4box.js vs the recorder index (measured: `functional/e*/mp4box.json`)

For all 20 MP4 files (including both fragmented ones) mp4box.js 2.4.1 in the page found the same number of samples, and the same offset, size, pts and sync flag for every sample, as the Python-written recorder index; its codec string equals the manifest's in every file. Either source can drive the WebCodecs path. No WebM demuxer was tested in the page: for WebM the recorder index (offsets verified byte-exact in Python, §5) was used.

### 6.7 Sync and scrub harness smoke (measured: `functional/e*/sync_scrub_smoke.json`, 3 s / 2 s runs, functional only)

All 8 sync/scrub modes ran in both Electrons without errors. With pattern reading enabled, the index derived from rVFC `mediaTime` (for `<video>`) and the index of each drawn VideoFrame/ImageBitmap (for master-clock paths) matched the burned-in pattern on every callback / draw (0 mismatches). Spread, frame rate, lag and CPU are **not reported** (timing rule); they are what `bench_sync` / `bench_scrub` measure.

## 7. What this means for G9 (inferred unless labelled)

- Frame-exact random access and stepping in Chromium works today with any of the tested codecs **if** the UI seeks to the middle of the frame interval computed from the file's **real per-frame pts** (measured §6.2-6.3: 100 % for every CFR, VFR, GOP and intra file in both Electrons, except near-duplicate timestamps §6.4). The current UI does neither: it uses `frame / fps` (frame start) with an fps from the CSV, which measured 60 % exact on CFR 30 GOP files, 0-17 % on real VFR timing and 2.5 % on a today-style 32.9-fps-header file.
- Cheapest fix for the existing `<video>` player: per camera, map frame k -> `(pts[k] + pts[k+1]) / 2` using the file's own pts (or recorder index), and map displayed frames back via rVFC `mediaTime` instead of `currentTime * fps`. No codec change needed. This was measured only as single-element seeks/steps, not in the real component.
- An index-driven path (WebCodecs + recorder index, or camera JPEGs + index) was exact in every case including the near-duplicate VFR pair, needs no rounding rules, and lets one master clock pick frame k for every camera. Its cost (latency, CPU at N=8) is unmeasured: `bench_seek`, `bench_sync`, `bench_scrub`.
- All-intra files hide the boundary-rounding bug (measured §6.2) and make backward steps trivial; their cost is file size (measured: `clips_summary.json`, e.g. c1080p30 AV1 intra 13.8 MB vs AV1 GOP 1.24 MB for the same 600 frames; VP9 intra 48.5 MB).
- AV1, VP9 and H.264 behaved the same for seek accuracy in every test; G7 (royalty-free) and G8 (native playback) do not conflict with G9 on this machine (measured §6.1-6.2). Bumping Electron 35 -> 45 adds JPEG XL to `ImageDecoder` and removes the "stuck after last frame" bug, and improves exact-pts seeks; it changes nothing for mid-frame seeks or WebCodecs (measured).

## 8. Commands used (repo root, Git Bash or PowerShell)

```
# clips (media go to C:/Users/Dom/Documents/skellycam-raw/.../chromium_sync_scrub/clips/)
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/gen_clips.py
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/gen_clips.py --only hdr329
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/gen_clips.py --recompute-codec-strings
# mp4box.js for the page (scratchpad)
npm install --prefix C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/chromium_sync_scrub/npm_mp4box --ignore-scripts --save-exact mp4box@2.4.1
# functional suites
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 35 --suite functional
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 45 --suite functional
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 35 --suite functional_targeted
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 45 --suite functional_targeted
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/compare_jpeg_decode.py
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/summarize.py functional
# bench smoke tests (all passed on both Electrons; timing outputs deleted, only bench/e*/bench_*_smoke/_index.json kept)
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron <35|45> --suite <bench_seek|bench_step|bench_sync|bench_scrub> --smoke
```

The pattern-damage check in §6.2 was a one-off: decode `clips/c1080p30/av1_gop.mp4` with PyAV and apply `gen_clips.read_index` to every frame; result: frames 66, 306, 322 unreadable.

Sources fetched for §3-4 were kept in the scratchpad only (`scratchpad/chromium_sync_scrub/specs/`): html.spec.whatwg.org/multipage/media.html, wicg.github.io/video-rvfc/, www.w3.org/TR/webcodecs/, the AV1/AVC registrations, and Chromium files via `https://chromium.googlesource.com/chromium/src/+/refs/tags/<tag>/<path>?format=TEXT`.

## 9. Benchmarks to run later (one at a time, quiet machine)

Runner instructions:
- Run from the repo root on Gerald, display on and unlocked (the harness opens a visible 1600x900 window; `requestAnimationFrame`/rVFC can stop when the session is locked or minimised - inferred, not tested). Close other GPU apps; Parsec/Sunshine state is recorded by the `nvidia-smi` before/after columns in every result.
- Clips must exist (they do: `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/chromium_sync_scrub/clips/manifest.json`); otherwise run `gen_clips.py` and `gen_clips.py --only hdr329` first.
- Each command writes one JSON per configuration into `research/skellycam_recording/recording_upgrade/results/chromium_sync_scrub/bench/e<35|45>/<suite>/` plus `_index.json` (errors listed there), and page logs as `<file>.json.log`. After all runs: `summarize.py bench` writes `bench/bench_tables.md`.
- What each suite measures: `bench_seek` = seek latency p50/p95/max per path and GOP length (200 random seeks; `<video>` latency = `currentTime` set -> rVFC callback, also -> `seeked`; WebCodecs/JPEG = request -> decoded frame); `bench_step` = single-step forward/back latency; `bench_sync` = per-tick index spread across N streams while playing (N = 4 and 8 at 1080p, plus 720p and VFR at N = 4), dropped frames, UI-style follower corrections, and CPU (cores, from `app.getAppMetrics().cpu.cumulativeCPUUsage`) / working set per process type; `bench_scrub` = frames shown and distinct frames per second during a simulated drag (90 frames/s slider speed, input every 16 ms), lag to the slider, CPU.

| id | command | est. min | priority |
|---|---|---|---|
| bench_sync_e35 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 35 --suite bench_sync` | 15 | 1 |
| bench_sync_e45 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 45 --suite bench_sync` | 15 | 1 |
| bench_seek_e35 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 35 --suite bench_seek` | 8 | 1 |
| bench_seek_e45 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 45 --suite bench_seek` | 8 | 1 |
| bench_scrub_e35 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 35 --suite bench_scrub` | 14 | 2 |
| bench_scrub_e45 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 45 --suite bench_scrub` | 14 | 2 |
| bench_step_e35 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 35 --suite bench_step` | 5 | 2 |
| bench_step_e45 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 45 --suite bench_step` | 5 | 2 |
| summarize | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/summarize.py bench` | 1 | 1 |

## 10. Limits and open questions

- Single machine (RTX 3070, Windows 11). No macOS/Linux, no Intel/AMD GPU, no software-only decode run. Whether `<video>` used NVDEC is NOT VERIFIED (only Chromium's own `powerEfficient` / `prefer-hardware` answers).
- Clips are short (600-891 frames, 10-30 s) and 1080p content is 19 real frames looped; long-file behaviour (hour-long recordings, large moov, fragment scanning) is untested.
- The burned-in index pattern lives in the top strip of a lossy encode; 3 frames of one AV1 1080p file were unreadable (§6.2). Readback through `drawImage` adds work, so bench suites rely on rVFC `mediaTime` / known chunk timestamps by default.
- The UI itself (React component, backend streaming, 5-camera real recording) was **not** run; the harness re-implements its seek math and leader/follower rule from the code (§2).
- Sync across cameras with **different** per-camera timestamps (the real multi-camera case) was not tested: all N streams in `bench_sync` are the same clip. Matching cameras by capture time rather than frame index is a design question for the player.
- WebM in-page demux (no library) and MSE-based playback were not tested.
- The "stuck after the last frame" bug in Chromium 134 is measured but not root-caused.

