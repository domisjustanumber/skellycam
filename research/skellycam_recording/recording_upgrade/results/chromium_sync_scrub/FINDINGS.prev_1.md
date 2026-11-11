# chromium_sync_scrub: FINDINGS (G9: synchronized, frame-accurate playback and scrubbing in the Electron UI)

Study date 2026-11-09, machine Gerald (Windows 11, i7-14700K, RTX 3070, driver 610.88). Branch dom/research.
Labels: **measured** (result file, path given), **source** (primary source: URL, exact quote, accessed 2026-11-09), **code** (file:line), **inferred** (reasoning, kept short).
Result paths are relative to `research/skellycam_recording/recording_upgrade/results/chromium_sync_scrub/` unless they are written out in full.
**No timing numbers appear here.** Every latency, sync-spread, scrub-rate and CPU question is listed in section 5.

Version note:
- The playback side under test is Chromium: Electron 35.7.5 (Chromium 134.0.6998.205) and Electron 45.2.3 (Chromium 156.0.8078.80) (measured: `functional/e35/caps.json`, `functional/e45/caps.json`, key `versions`).
- The test clips were **encoded with PyAV 18.0.0** (libavcodec 62.28.102) from the skellycam venv (measured: `clips_summary.json`, key `generator`). So the clip encoding is **background (PyAV 18)**. The Chromium results do not depend on the encoder version, apart from the bitstream and container layout (inferred).
- The recorder-index premise (explicit per-frame pts, demuxed pts and byte offsets) was re-checked with **PyAV 19.0.2** (F17 and F18).

---

## 1. Questions answered

1. How does today's UI sync and seek, and is it frame-accurate?
2. Which seek rule makes `<video>` frame-exact in Chromium? Does it depend on codec (AV1, VP9, H.264), container (MP4, fragmented MP4, WebM), GOP vs all-intra, CFR vs real VFR timing, or Electron version?
3. Are index-driven paths frame-exact? These are WebCodecs fed from a recorder index of byte offsets, and JPEG sequences.
4. Do the cameras' own JPEG bytes (G1) decode in Chromium without a transcode, and how close is the decoded output to OpenCV?
5. Can the browser rebuild the index itself (mp4box.js), and can a PyAV 19 recorder produce one?
6. What changes between Electron 35 and Electron 45?

## 2. Findings

### 2.1 Today's UI (code)

- **F1** code: there is one `<video>` per camera. The first video is the leader. A `requestAnimationFrame` loop reads `leader.currentTime` and computes `frame = leaderTime * fps`.
  - Cited: `skellycam-ui/src/components/playback/SyncedVideoPlayer.tsx:375-378` (`const leaderTime = leader.currentTime; const newFrame = leaderTime * fpsRef.current;`).
  - `requestVideoFrameCallback` does not appear anywhere in `skellycam-ui/src` (code: grep, 0 hits).
- **F2** code: followers are checked every 15 rAF ticks. A follower is re-seeked only when it is more than 2 frames from the leader.
  - Cited: `SyncedVideoPlayer.tsx:101` (`FOLLOWER_DRIFT_TOLERANCE_FRAMES = 2`), `:103` (`FOLLOWER_CHECK_INTERVAL = 15`), `:422-426` (`if (Math.abs(el.currentTime - leaderTime) > toleranceSec) { el.currentTime = leaderTime; }`).
- **F3** code: paused seek, frame step and slider drag all set `currentTime = frame / fps`. That is the start of the frame interval.
  - Cited: `SyncedVideoPlayer.tsx:332-335` (`seekAllToFrame`: `const targetTime = ... clamped / fpsRef.current`), `:506-507` (drag), `:523-526` (`handleFrameStep` calls `seekAllToFrame`).
  - The End key seeks to `totalFrames - 1` (code: `:541-544`).
- **F4** code: the fps comes from the recording list. HEAD computes it as `round(frame_count / duration, 1)` (code: `skellycam/api/http/playback/playback_router.py`, around line 230: `stats["fps"] = round(frame_count / duration, 1)`).
  - The file's own timeline is never read.
  - `totalFrames = floor(duration * fps)`, the minimum over all videos (code: `SyncedVideoPlayer.tsx:451-460`).
- **F5** source (background, verified prior study): today's recorder writes a CFR header of about 32.9 fps for a real 30.0 fps capture (`research/skellycam_recording/REPORT.md:28`; `research/skellycam_recording/results/real_recording_20261109/RESULTS.md:99`, as cited in NOTES §2).

### 2.2 What the standards and Chromium guarantee

- **F6** source: currentTime is "interpreted as being in seconds". A paused `<video>` "represents the frame of video corresponding to the current playback position". Seeking only waits "until it has decoded enough data to play back that position".
  - URL: https://html.spec.whatwg.org/multipage/media.html (accessed 2026-11-09; quotes checked in the fetched copy).
  - No frame-exactness rule was found (searched for "frame-accurate": 0 hits).
- **F7** source: rVFC `mediaTime` is "The media presentation timestamp (PTS) in seconds of the frame presented". It is best effort: "a callback can occasionally be fired one v-sync late ... we might not get a callback for every frame".
  - URL: https://wicg.github.io/video-rvfc/ (Draft Community Group Report, 2 August 2024; accessed 2026-11-09).
- **F8** source: WebCodecs timestamps are "An integer value, in microseconds". `flush()` sets "[[key chunk required]] to true". `optimizeForLatency` is a "Hint that the selected decoder SHOULD be configured to minimize the number of EncodedVideoChunks that have to be decoded before a VideoFrame is output".
  - URL: https://www.w3.org/TR/2026/WD-webcodecs-20261108/ (W3C Working Draft, 8 November 2026; accessed 2026-11-09).
  - For AV1, "description is not used for this codec" (https://w3c.github.io/webcodecs/av1_codec_registration.html, accessed 2026-11-09).
- **F9** code (Chromium source at the release tags, from https://chromium.googlesource.com/chromium/src/+/refs/tags/<tag>/<path>):
  - `Seek(double)` calls `DoSeek(base::Seconds(seconds), true)`: `third_party/blink/renderer/platform/media/web_media_player_impl.cc:1079` @134.0.6998.205 and `:1115` @156.0.8078.80.
  - `base::Seconds` is `TimeDelta::FromInternalValue(MakeClampedNum(n) * Time::kMicrosecondsPerSecond)`: `base/time/time.h:901-904` @134.
  - Demuxed timestamps use `av_rescale_q(timestamp, time_base, kMicrosBase)`: `media/ffmpeg/ffmpeg_common.cc:112` @134 and `:124` @156.
  - Before the sink starts, the renderer resets to any frame with `frame->timestamp() <= start_timestamp_`: `media/renderers/video_renderer_impl.cc:626` @134 and `:660` @156.
  - inferred: the seek target is truncated to whole microseconds while the container pts is rounded. A target at exactly the frame start can therefore land on frame k-1. A target in the middle of the frame interval avoids both roundings.

### 2.3 Seek accuracy in Chromium (measured)

200 random seeks per clip and path, seed 1. "Exact" means the burned-in 16-bit index read back equals the requested frame. Totals were recomputed from the raw `functional/e35/seek_batch.json` and `functional/e45/seek_batch.json` (138 configurations each); they match `functional_tables.md`.

- **F10** measured: the **mid-interval target from the file's real pts** (`mid` = (pts[k] + pts[k+1]) / 2) was exact for every readable frame.
  - This held for every CFR, VFR, GOP and all-intra clip; for AV1, VP9 and H.264; in MP4, fragmented MP4 and WebM; in both Electrons.
  - Shortfalls appear only in the c1080p30 AV1 files (598/600 MP4, 398/400 WebM-family total, 198/200 fragmented). They are all `unreadable`, not wrong: the same frames are unreadable through WebCodecs and through libavcodec (NOTES §6.2, PyAV 18 one-off check, background). They are a test-pattern artefact of the crf-35 encode.
- **F11** measured: **today's rule (`ui` = k / nominal fps)** gives the results below. Errors are given as frame offsets (offset: count).

  | Clip family | Exact, e35 | Exact, e45 | Errors |
  |---|---|---|---|
  | c720p30 GOP MP4 | 360/600 | 360/600 | all -1 |
  | c720p30 GOP WebM | 240/400 | 240/400 | |
  | c720p60 GOP MP4 | 116/400 | 268/400 | |
  | vfr720p GOP MP4 | 68/400 | 68/400 | mostly +1/+2 (`1:81, 2:76, 3:3, -1:6` per AV1 file; one -12 in H.264) |
  | hdr329 (32.9 fps header, UI fps 30) | 10/400 | 10/400 | +1 to +52 |
  | all-intra CFR files | 400/400 (MP4), 200/200 (WebM) | same | |

- **F12** measured: an exact container pts as target (`ptsexact`) also fails on GOP files.
  - c720p30 GOP MP4: 360/600 in both Electrons.
  - vfr720p GOP WebM: 42/400 (e35) and 392/400 (e45).
  - vfr720p all-intra MP4: 200/200.
  - A constant-rate midpoint (`cfrmid`) on VFR timing: 38/400 GOP MP4 and 19/200 intra.
- **F13** measured: misses on CFR GOP files are always -1. The same targets are exact on all-intra files (see F11 and F12). inferred (mechanism F9): all-intra removes the earlier decoded frame that the renderer would keep.
- **F14** measured: single steps (`functional/e*/step_batch.json`; 20 forward then 40 back from random starts, 122 steps per clip):
  - `ui` on CFR30 GOP: 82/122 per file (forward 27/40, back 54/80).
  - `ui` on VFR: **0/122** per file, in GOP and intra files (+1: 61, +2: 61).
  - `ui` on c720p60 GOP MP4: 41/122 (e35), 81/122 (e45).
  - `mid`, WebCodecs and JPEG: 122/122 in every case, including backward steps across GOP boundaries.

### 2.4 Index-driven paths (measured)

- **F15** measured: **WebCodecs + recorder index** was exact for every readable frame in every seek and step run, in both Electrons (`functional/e*/seek_batch.json`, `step_batch.json`).
  - `flushes: 0` in all 30 WebCodecs seek configurations and all 16 step configurations per Electron, plus 5/5 targeted runs, with `optimizeForLatency: true`.
  - Same results: `decoder_error` null everywhere.
- **F16** measured: the **JPEG paths were exact in every run**: 800/800 per content family in both Electrons (`seek_batch.json`) and 122/122 for steps.
  - Paths: one `.mjpeg` file read by HTTP Range, or a folder of files; decoded by `createImageBitmap` or `ImageDecoder`.
  - These MJPEG clips are OpenCV q90 4:2:2 re-encodes of the pattern frames, not the cameras' own bytes (measured: `clips_summary.json`, codec `jpeg (OpenCV imencode q90 4:2:2)`).
- **F16a** measured (`functional/e*/targeted.json`): frames 81 and 82 of the VFR clip were captured 0.011 ms apart. The seek list was 79,80,81,82,83,84,82,81,80.

  | Path | e35 | e45 |
  |---|---|---|
  | WebCodecs | 9/9, all 5 VFR files | 9/9, all 5 VFR files |
  | `<video>` `mid`, GOP MP4 (AV1, H.264) | 9/9 | **7/9** (82 shows 81) |
  | `<video>` `mid`, AV1 intra MP4 | 9/9 | 9/9 |
  | `<video>` `mid`, GOP WebM (AV1, VP9) | 5/9 | 7/9 |

  - Electron 45 is therefore **not** identical to Electron 35 for `mid` on this near-duplicate pair. This corrects NOTES §6.4, which reports "MP4 7/9" for e45 without the intra case and calls mid-frame identical in both.

### 2.5 Recorder index (measured)

- **F17** measured, background (PyAV 18 clips): the recorder index matched for every coded sample (`all_samples_byte_exact: true`) in all **30 video files**. NOTES says 35; `clips_summary.json` has 30 video and 5 MJPEG entries. Decode order equaled pts order in every file.
  - Caveat (code: `scripts/chromium_sync_scrub/gen_clips.py:179-185`): `demux_index` falls back to a byte search near `packet.pos` when `pos` is not exact. So for WebM, "byte_exact" relied on that fallback (see F18).
- **F18** measured, **PyAV 19.0.2** (libavformat 63.1.102), 96-frame synthetic clips with the real VFR capture times (`pyav19_recorder_index_check.json`):
  - In all 6 variants, demuxed pts equal the requested pts, and decode order equals pts order. The variants were AV1 GOP MP4 (+faststart), AV1 GOP fragmented MP4, AV1 intra MP4, AV1 GOP WebM, VP9 GOP WebM and H.264 GOP MP4 (bf=0).
  - The burned index read back on 96/96 decoded frames in every variant.
  - In MP4 (1/90000), the 0.011 ms pair stays 1 tick apart (pts 243358, 243359).
  - In WebM (1/1000), one pts had to be bumped to stay strictly increasing (`pts_adjusted_for_monotonic: 1`).
  - `packet.pos` points directly at the packet bytes in MP4 (96/96 in all three MP4 variants, including fragmented) but **never in WebM (0/96)**.
  - The WebM payload starts **exactly 4 bytes after `packet.pos`** for every packet. This held in both PyAV 19 WebM files (96/96) and in two PyAV 18 clips (600/600 each) (`pyav19_webm_pos_delta.json`).
  - inferred: this is the Matroska SimpleBlock header (track number, timecode, flags) for single-track, unlaced blocks. NOT VERIFIED against the Matroska spec in this study.
- **F19** measured: mp4box.js 2.4.1 inside the page reproduced the recorder index for all 20 MP4 files, including both fragmented ones, in both Electrons. Sample count, offset, size, pts, sync flag and codec string all matched (`functional/e*/mp4box.json`). No in-page WebM demuxer was tested.

### 2.6 Camera JPEG bytes, codecs, Electron versions (measured)

- **F20** measured: the cameras' own JPEG frames decoded with both `createImageBitmap` and `ImageDecoder` with 0 errors in both Electrons (`functional/e*/jpegcompat.json`).
  - Frames per set: c930e_720p_flash 30, c922_720p_flash 30, c922_1080p 19, c930e_1080p 19, c922_1600x896 19, c922_720p60 10, generic_1080p 11.
  - `ImageDecoder` returned format `I422`.
- **F21** measured (`functional/jpeg_decode_compare.json`, frame 0 of each set):
  - `createImageBitmap` → canvas is bit-identical to OpenCV 4.12 `imdecode`: max abs diff 0, 100.0 % exact, all 7 sets, both Electrons.
  - `ImageDecoder` → `drawImage` differs from OpenCV by a max abs of 5 to 24 levels (81.799 % to 96.981 % exact).
  - The PyAV columns in that file are PyAV 18 (background).
- **F22** measured: codec support is the same in both Electrons (`functional/e*/caps.json`).
  - AV1, VP9 and H.264 give `canPlayType` "probably", `VideoDecoder.isConfigSupported` true for both prefer-hardware and prefer-software, and mediaCapabilities "supported/smooth/powerEfficient".
  - HEVC `hvc1.1.6.L93.B0`: prefer-hardware true, **prefer-software false**.
  - VP8: prefer-hardware false, not-powerEfficient.
  - `fastSeek` and `ManagedMediaSource` are absent.
  - `ImageDecoder` jxl: false in e35, true in e45.
  - Chromium lists only the NVIDIA GPU (0x10de/0x2484) and Microsoft Basic Render.
- **F23** measured: Chromium 134 has a "stuck at last frame" case (`functional/e35/targeted.json`). After a seek that lands exactly on frame 599, every later seek kept showing 599 and rVFC fired only 2 times in 10, giving 3/10 exact.
  - Affected: `c720p30/av1_gop.webm` and `vp9_intra.webm` with `ptsexact`; `c720p60/av1_intra.mp4` with both `ptsexact` and `ui`.
  - Electron 45: 10/10 in the same cases. `mid` targets: 10/10 in both.
  - Root cause NOT VERIFIED.
- **F24** measured: the sync and scrub harness modes ran in both Electrons with 0 errors (`functional/e*/sync_scrub_smoke.json`).
  - Modes: `video-free`, `video-leader`, `wc-master`, `jpeg-master-range-bitmap` (N=4); scrub `video-ui`, `video-gated`, `webcodecs`, `jpeg-range-imagedecoder` (N=2).
  - Pattern mismatches were 0 for every stream in the sync modes.
  - The bench smoke runs had 0 errors (`bench/e{35,45}/bench_{seek,step,sync,scrub}_smoke/_index.json`: 6, 4, 10 and 10 runs each). Their timing outputs were deleted.

## 3. Comparison tables

### 3.1 Frame-exactness by seek path (measured, both Electrons unless split)

| Path | CFR GOP | CFR all-intra | Real VFR | Today-style 32.9 fps header | 0.011 ms VFR pair | Evidence |
|---|---|---|---|---|---|---|
| `<video>`, `currentTime = k/fps` (today's UI) | 60 % (CFR30), 29 % / 67 % (60 fps MP4, e35 / e45) | ~100 % (one e35 stuck case) | 17 % seeks, 0 % steps | 2.5 % | n/a | F11, F14, F23 |
| `<video>`, exact container pts | 60 % MP4; 97.5-98.5 % WebM | 99-100 % | 17-19 % MP4; 10.5 % (e35) / 98 % (e45) WebM | not run | 0/9 MP4 GOP | F12, F16a |
| `<video>`, mid-interval from real pts | 100 % of readable | 100 % | 100 % | 100 % | 5/9 to 9/9 | F10, F16a |
| WebCodecs + recorder index | 100 % of readable | 100 % | 100 % | 100 % | 9/9 | F15, F16a |
| JPEG sequence (4 paths) | 100 % | n/a | 100 % | 100 % | not targeted | F16 |

The percentages are the exact/n totals of F10 to F16a, converted; the totals in section 2 are authoritative.

### 3.2 Electron 35.7.5 vs 45.2.3 (measured)

| Item | E35 (Chromium 134) | E45 (Chromium 156) | Evidence |
|---|---|---|---|
| Codec and API support | same | same, plus `ImageDecoder` jxl | F22 |
| `ui`, c720p60 GOP MP4 | 116/400 | 268/400 | F11 |
| `ptsexact`, vfr720p GOP WebM | 42/400 | 392/400 | F12 |
| Stuck after exact last-frame seek | yes (3/10) | no (10/10) | F23 |
| `mid`, random seeks | 100 % of readable | 100 % of readable | F10 |
| `mid`, 0.011 ms pair, GOP MP4 | 9/9 | 7/9 | F16a |
| WebCodecs and JPEG | exact | exact | F15, F16 |

### 3.3 Storage cost of all-intra (measured, background PyAV 18, `clips_summary.json`)

c720p30 has 600 distinct real frames. The settings are those in `clips_summary.json`.

| Codec | GOP (g=30) bytes | All-intra bytes |
|---|---|---|
| AV1 (SVT preset 10, crf 35) | 886,687 | 5,795,340 |
| VP9 (realtime, cpu-used 8, crf 33) | 1,915,483 (WebM) | 14,114,635 (WebM) |
| H.264 (veryfast, crf 23, bf 0) | 3,331,315 | 9,634,168 |
| MJPEG (OpenCV q90 4:2:2) | n/a | 34,704,798 |

## 4. Implications for the plan

- **I1** (F3, F4, F5, F11, F14): today's player is not frame-accurate on any GOP file or any real (VFR) recording, and is badly off on today's 32.9 fps-header files. G9 needs a player change whatever codec is chosen.
- **I2** (F10, F14, F18, F19): the smallest fix keeps `<video>`:
  - Per camera, seek to `(pts[k] + pts[k+1]) / 2` using the file's own pts. Get the pts from a recorder index, or from mp4box.js for MP4.
  - Read the shown frame back from rVFC `mediaTime` instead of `currentTime * fps`.
  - No codec change is needed. This was measured on single elements, not in the real React component (section 6).
- **I3** (F15, F16, F16a, F7): only the index-driven paths (WebCodecs or JPEG) were exact in every case, including near-duplicate VFR timestamps. A single master clock can then choose frame k for every camera. Their cost is unmeasured (section 5), so the plan must not pick between I2 and I3 until `bench_seek` and `bench_sync` have run.
- **I4** (F18, F19): if the recorder writes an index, two rules apply.
  - For MP4, `packet.pos` from a PyAV 19 demux is the sample offset.
  - For WebM, `pos` is 4 bytes before the payload in every tested file. The index must store the payload offset, or the reader must parse the block header.
  - inferred: with `+faststart`, the moov is moved at close, so byte offsets are only final after the file is finished. Fragmented MP4 does not need a moov rewrite. Whether PyAV exposes offsets at write time was not tested.
- **I5** (F10, F22, F17): AV1, VP9 and H.264 behaved the same for seek accuracy. G7 (royalty-free) and G8 (native playback) do not conflict with G9 on this machine. HEVC has no software decode path in these Electrons (F22), which counts against it for G8 and G9 on machines without HEVC hardware (inferred).
- **I6** (F13, 3.3): all-intra hides the boundary-rounding problem and simplifies backward steps. On c720p30 it costs 6.5x (AV1) to 7.4x (VP9) the GOP file size at these settings. With a mid-interval or index-based player, all-intra is not needed for accuracy.
- **I7** (F20, F21, F16): files written straight from camera JPEG bytes (G1) can be shown in the UI without a transcode, and `createImageBitmap` matches OpenCV exactly. This supports a JPEG-passthrough recording format for playback.
- **I8** (F23, F16a, 3.2): moving to Electron 45 is not required for G9 if the player uses mid-interval or index seeking. It removes the Chromium 134 stuck-frame case, which today's End key can trigger (F3; inferred: when the target equals the last pts). It is slightly worse for `mid` on a 1-tick VFR pair, so the index path is the safer choice for real VFR data.

## 5. Pending tonight's bench

Bench ids are from `results/bench_queue_from_wf_2e122ed0.json` → `chromium_sync_scrub.bench_manifest`. The runner and harness use only the Python standard library plus Electron, with no PyAV (code: imports of `scripts/chromium_sync_scrub/run_suite.py:20-29` and `summarize.py:8-12`). The PyAV 19-only rule therefore affects only the clip generation (section 6).

| Timed question | bench_manifest ids | Priority |
|---|---|---|
| Frame-index spread across N=4 and N=8 1080p streams while playing (plus 720p, VFR at N=4); dropped frames; follower corrections; CPU and working set per process; nvidia-smi decoder use. Paths: `<video>` free, today's leader/follower, WebCodecs master clock, JPEG master clock | `bench_sync_e35`, `bench_sync_e45` | 1 |
| Seek latency p50/p95/max per path, GOP vs intra, at 720p30, 1080p30 and 720p60 (`<video>` mid to rVFC and to `seeked`; WebCodecs; 4 JPEG paths) | `bench_seek_e35`, `bench_seek_e45` | 1 |
| Scrub smoothness: frames shown and distinct frames per second, lag to the slider, CPU, N=1 and 4. Paths: UI-style seek-per-input vs gated, WebCodecs, JPEG | `bench_scrub_e35`, `bench_scrub_e45` | 2 |
| Single-step latency forward and back, GOP vs intra | `bench_step_e35`, `bench_step_e45` | 2 |
| Tables from all bench JSONs | `bench_summarize` | 1 |
| Does `<video>` or WebCodecs decode on NVDEC here? (partly; only before/after nvidia-smi samples) | `bench_sync_*`, `bench_seek_*` | 1 |

## 6. Not tested, limits, NOT VERIFIED

- Clips were encoded with PyAV 18.0.0 (background).
  - Only the recorder-index premise was re-checked on PyAV 19.0.2 (F18).
  - Regenerating the 30 clips with PyAV 19 (gen_clips under `uv run` with `av==19.0.2`, `opencv-python`, `numpy`) was **not** done: it exceeds the 1-minute functional budget. Decide before 23:00 whether tonight's bench uses the existing clips (labelled PyAV 18 encode) or regenerated ones.
- `run_suite.py` hard-codes the old session's scratchpad for Electron 45.2.3 and mp4box.js (code: `scripts/chromium_sync_scrub/run_suite.py:34-38`).
  - The Electron 45 exe existed at check time; mp4box.js was not checked.
  - If that scratchpad is deleted, the e45 and mp4box runs fail with "missing ..." (code: `:238-239`).
- Single machine: Windows 11, RTX 3070, NVIDIA only. Chromium listed no Intel device during these runs (F22), although the UHD 770 is reported present now. No macOS/Linux, no Intel/AMD GPU decode, and no forced software decode was tested.
- NVDEC use by Chromium is NOT VERIFIED. Only Chromium's own `powerEfficient` / prefer-hardware answers exist (F22).
- The real UI was not run: no React component, no backend streaming, no 5-camera real recording. The harness re-implements its seek math and leader/follower rule from the code (F1 to F4).
- No multi-camera clips with different capture times were tested: all N streams in `bench_sync` are the same clip. Syncing by capture timestamp vs by frame index is an open design question.
- Clips are short: 600 to 891 frames. The 1080p and 720p60 content is 19 and 10 real frames looped. Hour-long files, large moov, many fragments and Range behaviour on multi-GB files were not tested.
- The burned-in pattern is unreadable on frames 66 and 306 (seek sample) of the c1080p30 AV1 files (F10).
- Root cause of the Chromium 134 stuck-frame case: NOT VERIFIED (F23).
- `av_rescale_q` rounding inside Chromium's FFmpeg revision, and the truncation in `base::Seconds`, are inferred from code comments, not traced to the exact FFmpeg revision. The truncation detail is NOT VERIFIED.
- The WebM 4-byte offset explanation (SimpleBlock header) is NOT VERIFIED against the Matroska spec. Laced or multi-track blocks were not tested.
- Whether PyAV can report byte offsets during writing was not tested. The index in this study was built by demuxing the finished file.
- WebM in-page demux and MSE playback were not tested.
- hdr329 `ui` got rVFC 195/200 (`functional_tables.md`). inferred: targets k/30 past the end of the 18.2 s file. Not checked.
- The CPU and memory samples were removed from the functional JSONs because the machine was shared (`note` key in each functional JSON). There are no timing numbers in this topic.

## 7. How to reproduce

From the repo root `C:/Users/Dom/GitHub/freemocap/skellycam`. Media go only under `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/chromium_sync_scrub/`.

```
# clips (PyAV 18, skellycam venv: background; existing clips + manifest.json are in the media folder)
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/gen_clips.py
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/gen_clips.py --only hdr329

# functional suites (Electron 35.7.5 and 45.2.3; run_suite removes ELECTRON_RUN_AS_NODE)
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 35 --suite functional
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 45 --suite functional
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 35 --suite functional_targeted
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 45 --suite functional_targeted
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/compare_jpeg_decode.py
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/summarize.py functional

# PyAV 19.0.2 recorder-index re-check (F18); scripts live in this session's scratchpad
S=C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/chromium_sync_scrub
M=C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/chromium_sync_scrub
R=research/skellycam_recording/recording_upgrade/results/chromium_sync_scrub
uv run --script $S/pyav19_recorder_index_check.py research/usb_cameras/results/windows/Gerald/timing/flash_run1_repositioned/capture/vid_046d_pid_0843_mi_00_8_39dec205_0_0000.frames.jsonl $M/pyav19_check $R/pyav19_recorder_index_check.json
uv run --script $S/webm_pos_delta.py $R/pyav19_webm_pos_delta.json $M/pyav19_check/pyav19_av1_gop.webm $M/pyav19_check/pyav19_vp9_gop.webm $M/clips/c720p30/av1_gop.webm $M/clips/c720p30/vp9_intra.webm

# tonight (one at a time, quiet machine): see section 5
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron <35|45> --suite <bench_sync|bench_seek|bench_scrub|bench_step>
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/summarize.py bench
```

Raw-total recomputation: the per-family totals in section 2.3 were recomputed in this session by summing `summary.exact` and `summary.n` over `result[]` in `functional/e{35,45}/{seek,step}_batch.json`, grouped by content, file family, path and mode. They match `functional_tables.md` and NOTES §6.2-6.3.
