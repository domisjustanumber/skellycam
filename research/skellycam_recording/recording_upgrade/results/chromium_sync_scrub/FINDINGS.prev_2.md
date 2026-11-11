# chromium_sync_scrub: FINDINGS (G9: synchronized, frame-accurate playback and scrubbing in the Electron UI)

Study date 2026-11-09, machine Gerald (Windows 11, i7-14700K, RTX 3070, driver 610.88). Branch dom/research.
Labels: **measured** (result file, path given), **source** (primary source: URL, exact quote, accessed 2026-11-09), **code** (file:line), **inferred** (reasoning, kept short).
Result paths are relative to `research/skellycam_recording/recording_upgrade/results/chromium_sync_scrub/` unless written out in full. Script paths are relative to `research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/`.
**No timing numbers appear here.** Every latency, sync-spread, scrub-rate and CPU question is in section 5.

Scope note (HANDOFF §1 requirement 10, added 17:20): "Only intra-only formats are in scope ... Existing GOP results are background only."
- Results on intra-only files (all-intra video, JPEG sequences) are the primary evidence here.
- Every GOP result below is marked **background (GOP)**. GOP results are kept because they explain the mechanism and today's files.

Version note:
- The playback side under test is Chromium: Electron 35.7.5 (Chromium 134.0.6998.205) and Electron 45.2.3 (Chromium 156.0.8078.80) (measured: `functional/e35/caps.json`, `functional/e45/caps.json`, key `versions`).
- The test clips were **encoded with PyAV 18.0.0** (libavcodec 62.28.102) (measured: `clips_summary.json`, key `generator`). So the clip encode is **background (PyAV 18)**.
- inferred: the Chromium results do not depend on the encoder version, apart from bitstream and container layout. Supporting evidence: PyAV 18 and PyAV 19.0.2 MP4 files have the same box set (`elst` 1, no `ctts`, `stss`, faststart `moov` before `mdat`; fragmented has `moof` + `mfra`) (measured, crude byte scan: `VERIFY_method.md` V8, console only). No Electron run used a PyAV 19 file.
- The recorder-index premise and the pattern readback were re-checked with **PyAV 19.0.2** (FFmpeg libs 63.1.102) (F10, F18, F25).

---

## 1. Questions answered

1. How does today's UI sync and seek, and is it frame-accurate?
2. Which seek rule makes `<video>` frame-exact in Chromium? Does it depend on codec, container, all-intra vs GOP, CFR vs real VFR, or Electron version?
3. Are index-driven paths frame-exact? These are WebCodecs fed from a recorder index of byte offsets, and JPEG sequences.
4. Do the cameras' own JPEG bytes (G1) decode in Chromium without a transcode, and how close is the result to OpenCV?
5. Can the browser rebuild the index itself (mp4box.js), and can a PyAV 19 recorder produce one?
6. What changes between Electron 35 and Electron 45?

## 2. Findings

### 2.1 Today's UI (code)

- **F1** code: there is one `<video>` per camera. The first video is the leader. A `requestAnimationFrame` loop computes `frame = leader.currentTime * fps`.
  - `skellycam-ui/src/components/playback/SyncedVideoPlayer.tsx:375-378` (`const leaderTime = leader.currentTime; const newFrame = leaderTime * fpsRef.current;`).
  - `requestVideoFrameCallback` has 0 hits in `skellycam-ui/src` (code: grep).
- **F2** code: followers are checked every 15 rAF ticks. A follower is re-seeked only when it is more than 2 frames from the leader.
  - `SyncedVideoPlayer.tsx:101` (`FOLLOWER_DRIFT_TOLERANCE_FRAMES = 2`), `:103` (`FOLLOWER_CHECK_INTERVAL = 15`), `:422-426` (`if (Math.abs(el.currentTime - leaderTime) > toleranceSec) { el.currentTime = leaderTime; }`).
- **F3** code: paused seek, frame step and slider drag all set `currentTime = frame / fps`, which is the start of the frame interval.
  - `SyncedVideoPlayer.tsx:332-335` (`seekAllToFrame`), `:506-507` (drag), `:523-526` (`handleFrameStep`).
  - The End key seeks to `totalFrames - 1` (`:541-544`).
- **F4** code: fps comes from the recording's timestamp CSV, not from the video file.
  - `skellycam/api/http/playback/playback_router.py:205` (`frame_count = len(rows)`), `:218-220` (first/last timestamp, `duration = abs(last_ts - first_ts)`), `:230` (`stats["fps"] = round(frame_count / duration, 1)`).
  - `totalFrames = floor(duration * fps)`, minimum over all videos (`SyncedVideoPlayer.tsx:451-460`).
- **F5** measured (prior study, background): with real cameras at 30.0 fps, "all 15 videos had headers of **32.8–33.25 fps (+9–11%)**" (`research/skellycam_recording/REPORT.md:28`). The synthetic `hdr329` clip uses 32.9 fps, one point in that range.

### 2.2 What the standards and Chromium guarantee

- **F6** source: currentTime is "interpreted as being in seconds". A paused `<video>` "represents the frame of video corresponding to the current playback position". Seeking waits "until it has decoded enough data to play back that position".
  - https://html.spec.whatwg.org/multipage/media.html (accessed 2026-11-09). "frame-accurate" and "frame accurate": 0 hits.
- **F7** source: rVFC `mediaTime` is "The media presentation timestamp (PTS) in seconds of the frame presented". It is best effort: "a callback can occasionally be fired one v-sync late ... we might not get a callback for every frame".
  - https://wicg.github.io/video-rvfc/ (Draft Community Group Report, 2 August 2024; accessed 2026-11-09).
- **F8** source: WebCodecs timestamps are "An integer value, in microseconds". `flush()` sets "[[key chunk required]] to true". `optimizeForLatency` is a "Hint that the selected decoder SHOULD be configured to minimize the number of EncodedVideoChunks that have to be decoded before a VideoFrame is output".
  - https://www.w3.org/TR/2026/WD-webcodecs-20261108/ (W3C Working Draft, 8 November 2026; accessed 2026-11-09).
  - AV1: "description is not used for this codec" (https://w3c.github.io/webcodecs/av1_codec_registration.html, accessed 2026-11-09).
- **F9** code (Chromium at the release tags, https://chromium.googlesource.com/chromium/src/+/refs/tags/<tag>/<path>):
  - `Seek(double)` calls `DoSeek(base::Seconds(seconds), true)`: `third_party/blink/renderer/platform/media/web_media_player_impl.cc:1079` @134.0.6998.205, `:1115` @156.0.8078.80.
  - `base::Seconds` → `TimeDelta::FromInternalValue(MakeClampedNum(n) * Time::kMicrosecondsPerSecond)`: `base/time/time.h:901-904` @134.
  - Demuxed timestamps: `av_rescale_q(timestamp, time_base, kMicrosBase)`: `media/ffmpeg/ffmpeg_common.cc:112` @134, `:124` @156.
  - Before the sink starts, the renderer resets to any frame with `frame->timestamp() <= start_timestamp_`: `media/renderers/video_renderer_impl.cc:626` @134, `:660` @156.
  - inferred: the seek target is truncated to whole µs while the container pts is rounded, so a target exactly at a frame start can land on frame k-1 in a GOP file. A mid-interval target avoids both roundings.
  - measured support: a model of this rule, applied to the exact seed-1 sequences, matches every e45 GOP configuration within 0-2, and the CFR30 configurations in both Electrons (`verify_method_seek_model.txt`).
  - Not explained by the model (NOT VERIFIED, separate mechanism): e35 c720p60 GOP MP4 `ui` (measured 58/200 per file, model 136); e35 vfr720p GOP WebM `ptsexact` (measured 21/200, model 197); and the near-duplicate `mid` failures in F16a (the model predicts `mid` correct on every frame).

### 2.3 Seek accuracy in Chromium (measured)

Method (code: `harness/harness.mjs:19,231-233`; `run_suite.py`):
- Random seeks: 200 per file and path, **seed 1**. Every file with the same frame count used the **same sequence**. That sequence holds **169 distinct of 600** frames and **185 distinct of 891** (VFR) (recomputed from mulberry32; `VERIFY_method.md` V2). Frames 80-82 were never sampled.
- Family totals (for example 600/600) are the same frame set on several files, not independent samples. Each configuration ran once.
- "Exact" means the burned-in 16-bit index read back equals the requested frame. Totals were recomputed from `functional/e{35,45}/seek_batch.json` (138 configurations each) and match `functional_tables.md`.

- **F10** measured: the **mid-interval target from the file's real pts** (`mid` = (pts[k] + pts[k+1]) / 2) was exact on **every sampled seek** in every clip, both Electrons. Exception: frames that cannot be read (below). It was not run on every frame. It **fails on the one near-duplicate VFR pair** (F16a).
  - Each c1080p30 AV1 GOP file (`av1_gop.mp4`, `av1_gop.webm`, `av1_gop_frag.mp4`; background, GOP) is 198/200: frames 66 and 306 cannot be read.
  - These rows show the right frame, with an unreadable pattern. rVFC `mt_idx` equals k for k = 66 and 306 (measured: `functional/e35/seek_batch.json`, `wrong_rows` of `c1080p30/av1_gop.mp4`).
  - measured, PyAV 19.0.2 (libdav1d): decoding every frame, the pattern is unreadable on frames **66, 306 and 322** in all three AV1 GOP files, with 0 wrong frames. `c1080p30/av1_intra.mp4` has 0 unreadable (`pyav19_c1080p30_av1_pattern_check.json`). Frame 322 is not in the seed-1 sequence. inferred: an artefact of the crf-35 encode of the test pattern.
- **F10a** measured: **intra-only files (in scope)**, exact/n per path. Files per family: c720p30 = AV1 MP4, VP9 WebM, H.264 MP4; c1080p30 = the same 3; c720p60 = AV1 MP4, VP9 WebM; vfr720p = AV1 MP4 only. Same in both Electrons unless split (`functional/e*/seek_batch.json`).

  | Content | `ui` (k/fps) | `ptsexact` | `mid` | WebCodecs | JPEG (4 paths) |
  |---|---|---|---|---|---|
  | c720p30 | 600/600 | 598/600 e35 (stuck case F23), 600/600 e45 | 600/600 | 600/600 | 800/800 |
  | c1080p30 | 600/600 | not run | 600/600 | 600/600 | 800/800 |
  | c720p60 | 398/400 e35 (`av1_intra.mp4`, off 13 and 591, stuck case F23), 400/400 e45 | not run | 400/400 | 400/400 | 800/800 |
  | vfr720p (real capture times) | **34/200** (+1: 81, +2: 76, +3: 3, -1: 6) | 200/200 | 200/200 | 200/200 | 800/800 |
  | hdr329 | no intra video clip | | | | 800/800 |

  - So all-intra fixes the CFR misses of today's rule, but **not the VFR errors**: `ui` on the only intra VFR file is 34/200 in both Electrons.
- **F11** measured: **today's rule (`ui` = k / nominal fps)** on GOP files (**background, GOP**).

  | Clip family | Exact, e35 | Exact, e45 | Errors |
  |---|---|---|---|
  | c720p30 GOP MP4 | 360/600 | 360/600 | all -1 |
  | c720p30 GOP WebM | 240/400 | 240/400 | |
  | c720p60 GOP MP4 | 116/400 | 268/400 | |
  | vfr720p GOP MP4 | 68/400 | 68/400 | mostly +1/+2 (per AV1 file `1:81, 2:76, 3:3, -1:6`; one -12 in H.264) |
  | hdr329 GOP (32.9 fps header, UI fps 30, F4) | 10/400 | 10/400 | +1 to +52 |

  - hdr329 details (measured: `functional/e35/seek_batch.json`; `VERIFY_method.md` V5; recount of the seed-1 sequence):
    - The exact seeks per file are k = 1, 2, 8, 8 and 599. k = 599 is exact only because its target (19.97 s) is past the end of the file (about 18.24 s), so the element clamps to the last frame.
    - 21/200 targets are past the end. The 5 rows without an rVFC callback (rVFC 195/200) are among them and show frame 599.
    - The +52 maximum still holds for targets inside the file.
    - code: today's UI cannot request those 21 frames, because its slider stops at `floor(duration * fps) - 1` (F4).
- **F12** measured: an exact container pts as target (`ptsexact`).
  - c720p30 GOP MP4: 360/600, both Electrons (background, GOP).
  - vfr720p GOP WebM: 42/400 (e35), 392/400 (e45) (background, GOP).
  - vfr720p all-intra MP4: 200/200 (in scope).
  - Constant-rate midpoint (`cfrmid`) on VFR timing: 38/400 GOP MP4 (background) and 19/200 all-intra (in scope; +1: 76, +2: 66, +3: 39).
- **F13** measured (background, GOP): misses on CFR GOP files are -1 in every case except one. In e35, `ptsexact` on `c720p30/av1_gop.webm` and `vp9_gop.webm` has 2 extra misses per file (off 13 and 591), which come from the Chromium 134 stuck case (F23) (off_by_hist `{13:1, 591:1, -1:3}`). The same targets are exact on the CFR all-intra files (F10a). inferred (F9): all-intra removes the earlier decoded frame that the renderer would otherwise keep.
- **F14** measured: single steps (`functional/e*/step_batch.json`). Each run is 2 random starts (**seed 2**) × (1 seek + 20 forward + 40 back) = 122 rows: 2 seeks, 40 forward and 80 back steps (code: `harness/harness.mjs:235-239`, `run_suite.py:113-115`). Starts were 416/195 (600 frames) and 630/290 (891 frames), so frames 80-82 were not stepped.
  - Intra (in scope; `av1_intra.mp4` per content): `ui` 122/122 on c720p30, c1080p30 and c720p60; **`ui` 0/122 on vfr720p** (+1: 61, +2: 61). `mid` and WebCodecs: 122/122 everywhere.
  - GOP (background): `ui` on CFR30 GOP 82/122 per file (forward 27/40, back 54/80); `ui` on VFR GOP 0/122; `ui` on c720p60 GOP MP4 41/122 (e35), 81/122 (e45). `mid` and WebCodecs 122/122, including backward steps across GOP boundaries.
  - JPEG: only `jpeg-range-imagedecoder` was stepped (code: `run_suite.py:115`): 122/122 per content.

### 2.4 Index-driven paths (measured)

- **F15** measured: **WebCodecs + recorder index** was exact on every sampled frame that could be read: seeks 5994/6000 per Electron (the 6 misses are the unreadable c1080p30 AV1 GOP frames, F10); steps 1952/1952 (`functional/e*/seek_batch.json`, `step_batch.json`).
  - `flushes` 0 and `decoder_error` null in all 30 seek and 16 step configurations per Electron. Targeted runs: 5/5 configurations 9/9 per Electron (F16a).
  - Conditions (code, not measured): `optimizeForLatency: true`, `hardwareAcceleration: 'no-preference'` (`harness/harness.mjs:105-106`). Chromium chose the decoder on this NVIDIA machine. No run without `optimizeForLatency`.
  - Limit (code: `harness/harness.mjs:132-140`): the harness feeds index entries from the keyframe to k and waits for frame k, so it assumes decode order = pts order. Every study clip had that property (F17). See F25 for hardware encoders.
- **F16** measured: **JPEG paths were exact on every sampled seek**: 800/800 per content (4 paths × 200) in both Electrons (`seek_batch.json`). Steps: one path only (F14).
  - Paths: one `.mjpeg` file read by HTTP Range, or a folder of files; decoded by `createImageBitmap` or `ImageDecoder`.
  - These MJPEG clips are OpenCV q90 4:2:2 re-encodes of the pattern frames, not the cameras' own bytes (measured: `clips_summary.json`, codec `jpeg (OpenCV imencode q90 4:2:2)`).
- **F16a** measured: frames 81 and 82 of the VFR capture are 0.011 ms apart (measured: `pyav19_recorder_index_check.json`, `gap_81_82_ms: 0.011`, from `research/usb_cameras/results/windows/Gerald/timing/flash_run1_repositioned/capture/vid_046d_pid_0843_mi_00_8_39dec205_0_0000.frames.jsonl`). Targeted seek list 79,80,81,82,83,84,82,81,80 (`functional/e*/targeted.json`):

  | Path | e35 | e45 |
  |---|---|---|
  | WebCodecs | 9/9, all 5 VFR files | 9/9, all 5 VFR files |
  | `<video>` `mid`, AV1 intra MP4 (in scope) | 9/9 | 9/9 |
  | `<video>` `ptsexact`, AV1 intra MP4 (in scope) | 9/9 | 9/9 |
  | `<video>` `mid`, GOP MP4 (AV1, H.264) (background) | 9/9 | **7/9**: both visits to 82 show 81 |
  | `<video>` `mid`, GOP WebM (AV1, VP9) (background) | 5/9: 81 shows 80, 82 shows 81 | 7/9: both visits to 82 show 81 |
  | `<video>` `ptsexact`, GOP MP4 / WebM (background) | 0/9 / 2/9 | 0/9 / 6/9 |

  - In e45 GOP files, the `mid` target for frame 82 (2.719978 s MP4, 2.7205 s WebM) never showed frame 82, and rVFC `mt_idx` also reported 81. Other targets inside frame 82 were not tried.
  - Only one intra VFR file exists (AV1 MP4). VP9/H.264 intra on this pair was not tested.
  - This corrects NOTES §6.4, which calls `mid` identical in both Electrons.

### 2.5 Recorder index (measured)

- **F17** measured, background (PyAV 18 clips): the recorder index matched for every coded sample (`all_samples_byte_exact: true`) in all **30 video files** (`clips_summary.json`: 30 video + 5 MJPEG entries; NOTES says 35). Decode order equaled pts order in every file.
  - Caveat (code: `gen_clips.py:179-185`): `demux_index` falls back to a byte search near `packet.pos`, so for WebM "byte_exact" relied on that fallback (F18).
- **F18** measured, **PyAV 19.0.2** (libavformat 63.1.102), 96-frame synthetic clips with the real VFR capture times (`pyav19_recorder_index_check.json`):
  - In all 6 variants, demuxed pts equal the requested pts and decode order equals pts order. Variants: AV1 GOP MP4 (+faststart), AV1 GOP fragmented MP4, AV1 intra MP4, AV1 GOP WebM, VP9 GOP WebM, H.264 GOP MP4 (bf=0).
  - The burned index read back on 96/96 frames in every variant.
  - MP4 (1/90000): the 0.011 ms pair stays 1 tick apart (pts 243358, 243359).
  - WebM (1/1000): one pts had to be bumped to stay strictly increasing (`pts_adjusted_for_monotonic: 1`).
  - `packet.pos` points directly at the packet bytes in MP4 (96/96 in all three MP4 variants, including fragmented), but **never in WebM (0/96)**.
  - The WebM payload starts **exactly 4 bytes after `packet.pos`** for every packet: 96/96 in both PyAV 19 WebM files and 600/600 in `clips/c720p30/av1_gop.webm` and `clips/c720p30/vp9_intra.webm` (PyAV 18 encodes, background). Full paths are recorded in `pyav19_webm_pos_delta.json` (re-run 2026-11-09).
  - source: RFC 9559 §10.2 "SimpleBlock Structure" (https://www.rfc-editor.org/rfc/rfc9559.txt, accessed 2026-11-09): "Track Number: 8, 16, 24, 32, 40, 48, or 56 bits. An EBML VINT-coded track number." "Timestamp: 16 bits. Signed timestamp in Track Ticks." Figure 13 shows one flags octet after these. "As the TrackNumber size can vary between 1 and 8 octets, there are 8 different sizes for the SimpleBlock header." For track 1 that is 1 + 2 + 1 = 4 bytes, matching the measured delta.
  - inferred: `packet.pos` points at the start of the SimpleBlock body. Track numbers of 128 or more (a 2-octet VINT) give 5 bytes. Laced blocks were not tested.
- **F19** measured: mp4box.js 2.4.1 in the page reproduced the recorder index for all 20 MP4 files, including both fragmented ones, in both Electrons. Sample count, offset, size, pts, sync flag and codec string all matched (`functional/e*/mp4box.json`). No in-page WebM demuxer was tested.

### 2.6 Camera JPEG bytes, codecs, Electron versions, encoders (measured)

- **F20** measured: the cameras' own JPEG frames decoded with `createImageBitmap` and `ImageDecoder` with 0 errors in both Electrons (`functional/e*/jpegcompat.json`).
  - Frames per set: c930e_720p_flash 30, c922_720p_flash 30, c922_1080p 19, c930e_1080p 19, c922_1600x896 19, c922_720p60 10, generic_1080p 11.
  - `ImageDecoder` returned format `I422`.
- **F21** measured, **frame 0 of each set only** (`functional/jpeg_decode_compare.json`; code: `compare_jpeg_decode.py:36`):
  - `createImageBitmap` → canvas is bit-identical to OpenCV 4.12 `imdecode`: max abs diff 0, 100.0 % exact, all 7 sets, both Electrons.
  - `ImageDecoder` → `drawImage` differs from OpenCV by a max abs of 5 to 24 levels (81.799 % to 96.981 % exact).
  - The PyAV columns in that file are PyAV 18 (background).
- **F22** measured: codec support is the same in both Electrons (`functional/e*/caps.json`).
  - AV1, VP9, H.264: `canPlayType` "probably"; `VideoDecoder.isConfigSupported` true for prefer-hardware and prefer-software; mediaCapabilities "supported/smooth/powerEfficient".
  - HEVC `hvc1.1.6.L93.B0`: WebCodecs prefer-hardware true, **prefer-software false**. `<video>` `canPlayType` "probably" and mediaCapabilities supported.
  - VP8: prefer-hardware false, not powerEfficient.
  - `fastSeek` and `ManagedMediaSource` are absent.
  - `ImageDecoder` jxl: false in e35, true in e45.
  - Chromium listed only the NVIDIA GPU (0x10de/0x2484) and Microsoft Basic Render (0x1414).
- **F23** measured: Chromium 134 has a "stuck at last frame" case (`functional/e35/targeted.json`). After a seek that lands exactly on frame 599, later seeks kept showing 599, and rVFC fired only 2 times in 10: 3/10 exact.
  - Seen with `ptsexact` on `c720p30/av1_gop.webm`, `c720p30/vp9_intra.webm` and `c720p60/av1_intra.mp4`, and with `ui` **only** on `c720p60/av1_intra.mp4`.
  - Not triggered by `ui` on `c720p30/av1_gop.webm` (7/10, -1 misses, rVFC 10/10) or `c720p30/vp9_intra.webm` (10/10).
  - Electron 45: 10/10 in the same cases. `mid`: 10/10 in both.
  - Single run each. Root cause NOT VERIFIED.
- **F24** measured: the sync and scrub harness modes ran in both Electrons with 0 errors (`functional/e*/sync_scrub_smoke.json`).
  - Modes: `video-free`, `video-leader`, `wc-master`, `jpeg-master-range-bitmap` (N=4); scrub `video-ui`, `video-gated`, `webcodecs`, `jpeg-range-imagedecoder` (N=2). Pattern mismatches 0 for every stream in the sync modes.
  - Bench smoke runs had 0 errors (`bench/e{35,45}/bench_{seek,step,sync,scrub}_smoke/_index.json`: 6, 4, 10 and 10 runs). Their timing outputs were deleted. The `spread_*` fields still in `sync_scrub_smoke.json` come from a shared machine and must not be quoted.
- **F25** measured, **PyAV 19.0.2** (FFmpeg libs 63.1.102), 60-frame encodes (`verify_method_hw_reorder_default.json`, `verify_method_hw_reorder_bf0.json`):
  - With default options, `h264_nvenc`, `hevc_nvenc`, `h264_qsv`, `hevc_qsv` and `libx264` give decode order ≠ pts order (for example h264_nvenc pts/3000 in decode order `0,4,2,1,3,8,6,5,7,12,10,9`). `libsvtav1` does not reorder.
  - `av1_nvenc` fails to open on the RTX 3070 (`avcodec_open2` "Generic error in an external library"). `av1_qsv` raises NotImplementedError.
  - With `bf=0`, all four hardware encoders give decode order = pts order.
  - Chromium playback of NVENC/QSV-encoded files was not tested. Intra-only (`g=1`) hardware encodes were not checked for ordering. inferred: a stream where every frame is a keyframe has no B-frames.

## 3. Comparison tables

### 3.1 Frame-exactness by seek path (measured, both Electrons unless split)

Percentages are exact/n from section 2, which is authoritative. "Sampled" = 200 seed-1 seeks per file (169-185 distinct frames).

| Path | CFR all-intra (in scope) | Real VFR all-intra (in scope; 1 file) | 0.011 ms pair, intra | CFR GOP (background) | Real VFR GOP (background) | Today-style header (background, GOP) | Evidence |
|---|---|---|---|---|---|---|---|
| `<video>`, `currentTime = k/fps` (today's UI) | 100 % of sampled, except e35 c720p60 398/400 (stuck case) | 17 % seeks, 0 % steps | not run | 60 % (CFR30); 29 % / 67 % (60 fps MP4, e35 / e45) | 17 % seeks, 0 % steps | 2.5 % (1 of 10 by clamping) | F10a, F11, F14, F23 |
| `<video>`, exact container pts | 100 % (e35 c720p30 598/600, stuck case) | 100 % of sampled | 9/9 | 60 % MP4; 97.5-98.5 % WebM | 17-19 % MP4; 10.5 % (e35) / 98 % (e45) WebM | not run | F10a, F12, F16a |
| `<video>`, mid-interval from real pts | 100 % of sampled | 100 % of sampled | 9/9 | 100 % of sampled, readable | 100 % of sampled; fails at the pair (5/9 to 9/9) | not run | F10, F10a, F16a |
| WebCodecs + recorder index | 100 % of sampled | 100 % of sampled | 9/9 | 100 % of sampled, readable | 100 % of sampled; 9/9 at the pair | not run | F15, F16a |
| JPEG sequence (4 paths; steps 1 path) | 100 % of sampled | 100 % of sampled | not targeted | n/a | n/a | 100 % of sampled | F16 |

### 3.2 Electron 35.7.5 vs 45.2.3 (measured, single runs)

| Item | E35 (Chromium 134) | E45 (Chromium 156) | Evidence |
|---|---|---|---|
| Codec and API support | same | same, plus `ImageDecoder` jxl | F22 |
| `ui`, c720p60 all-intra | 398/400 (stuck case) | 400/400 | F10a |
| Stuck after exact last-frame seek | yes (3/10) | no (10/10) | F23 |
| `mid` and `ptsexact`, intra, 0.011 ms pair | 9/9 | 9/9 | F16a |
| `ui`, c720p60 GOP MP4 (background) | 116/400 | 268/400 | F11 |
| `ptsexact`, vfr720p GOP WebM (background) | 42/400 | 392/400 | F12 |
| `mid`, 0.011 ms pair, GOP MP4 / GOP WebM (background) | 9/9 / 5/9 | 7/9 / 7/9 | F16a |
| WebCodecs and JPEG | exact on all sampled frames | exact on all sampled frames | F15, F16 |

### 3.3 Storage cost of all-intra (measured, background PyAV 18, `clips_summary.json`)

c720p30: 600 frames, taken from a set of 891 distinct corpus frames (`frames`, `distinct_source_frames`). Settings as in `clips_summary.json`.

| Codec | GOP (g=30) bytes | All-intra bytes | Ratio |
|---|---|---|---|
| AV1 (SVT preset 10, crf 35) | 886,687 | 5,795,340 | 6.5x |
| VP9 (realtime, cpu-used 8, crf 33) | 1,915,483 (WebM) | 14,114,635 (WebM) | 7.4x |
| H.264 (veryfast, crf 23, bf 0) | 3,331,315 | 9,634,168 | 2.9x |
| MJPEG (OpenCV q90 4:2:2) | n/a | 34,704,798 | n/a |

## 4. Implications for the plan

- **I1** (F3, F4, F5, F10a, F11, F14): today's player is not frame-accurate on real VFR timing, even with all-intra files (34/200 seeks, 0/122 steps on the intra VFR clip). It is far off on a synthetic clip with a 32.9 fps header and UI fps 30 (measured on a synthetic clip built that way). G9 needs a player change whatever format is chosen.
- **I2** (F10, F10a, F14, F16a, F18, F19): the smallest fix keeps `<video>` with all-intra files:
  - Per camera, seek to `(pts[k] + pts[k+1]) / 2` using the file's own pts, from a recorder index or from mp4box.js for MP4.
  - Read the shown frame back from rVFC `mediaTime` instead of `currentTime * fps`.
  - On intra files, `mid` was exact on every sampled seek and on the 0.011 ms pair (one AV1 MP4 file). Exact-pts targets also worked there, but they trigger the e35 stuck case at the last frame (F23), so `mid` is the safer rule.
  - Measured only on single elements, on software encodes without reordering, and not in the real React component (section 6).
- **I3** (F15, F16, F16a, F7): only the index-driven paths (WebCodecs, JPEG) were exact in every run, including the near-duplicate pair (WebCodecs; JPEG not targeted). A single master clock can then choose frame k for every camera. Their cost is unmeasured (section 5), so the plan must not pick between I2 and I3 until tonight's bench has run.
- **I4** (F18, F19, F25): if the recorder writes an index:
  - MP4: `packet.pos` from a PyAV 19 demux is the sample offset.
  - WebM: `pos` is 4 bytes before the payload in every tested file, which fits the RFC 9559 SimpleBlock header for track 1. Store the payload offset, or parse the block header.
  - Decode order must equal pts order for the WebCodecs path as written (F15). With NVENC/QSV that needs `bf=0` or intra-only. Otherwise the index must store decode order and the player must feed past k (measured F25; code F15).
  - inferred: with `+faststart` the moov moves at close, so byte offsets are only final after the file is finished. Fragmented MP4 needs no moov rewrite. Whether PyAV reports offsets at write time was not tested.
- **I5** (F10, F10a, F22): AV1, VP9 and H.264 behaved the same for seek accuracy on these software encodes without reordering. On this machine, G7 (royalty-free) and G8 (native playback) do not conflict with G9. WebCodecs reports no software HEVC decoder. `<video>` HEVC without hardware was not tested.
- **I6** (F10a, F13, 3.3): all-intra is now required by scope (HANDOFF §1 req 10). For accuracy, it removes the GOP boundary misses of start-of-frame targets (F13), but not the VFR error of today's rule (F10a). Its size cost at these settings is 2.9x (H.264) to 7.4x (VP9) the GOP file on c720p30 (background, PyAV 18). Storage itself belongs to other topics.
- **I7** (F20, F21, F16): camera JPEG bytes (G1) decode in both Electrons without a transcode (F20, up to 30 frames per set). `createImageBitmap` matched OpenCV exactly on frame 0 of each set (F21). The seek and step exactness of JPEG paths was measured on OpenCV re-encodes (F16), not on camera bytes. This supports a JPEG-passthrough format for playback.
- **I8** (F23, F16a, 3.2): Electron 45 is not required for G9 if the player uses `mid` or index seeking on intra files. It removes the Chromium 134 stuck-frame case. That case was seen with today's rule only once, on 60 fps all-intra when the End target equalled the last pts exactly. On a today-style file End gives 546/30 = 18.2 s against a last pts of 18.2067 s, so the trigger condition is not met there (`VERIFY_method.md`, inputs from `clips/manifest.json`). On GOP files, e45 is worse than e35 for `mid` on the pair in MP4 and better in WebM (background). Only WebCodecs was exact on that pair in GOP files.

## 5. Pending tonight's bench

HANDOFF §1 requirement 11 trims the 23:00 queue for this topic to "Chromium JPEG-sequence sync/seek (N=4/8, 1080p, E35 and E45)". `results/BENCH_QUEUE_2300.md` did not exist at writing time. Bench ids are from `results/bench_queue_from_wf_2e122ed0.json` → `chromium_sync_scrub.bench_manifest`. The runner uses only the Python standard library and Electron (code: `run_suite.py:20-29`, `summarize.py:8-12`), so the PyAV 19-only rule affects only clip generation.

Decisive set (requirement 11):

| Timed question | Command selector (code: `run_suite.py` `bench_configs`, `--only` substring filter at `:204-205`) | Priority |
|---|---|---|
| Frame-index spread across N=4 and N=8 1080p JPEG streams under a master clock; dropped frames; CPU and working set per process (`jpeg-master-range-bitmap`, `jpeg-master-range-imagedecoder`) | `bench_sync_e35`, `bench_sync_e45` with `--only mjpeg` (4 configs each) | 1 |
| Seek latency p50/p95/max for the 4 JPEG paths at 1080p; also exactness on seed 11 as a second sample (`run_suite.py:151`) | `bench_seek_e35`, `bench_seek_e45` with `--only c1080p30/mjpeg` | 1 |
| Tables from the bench JSONs | `bench_summarize` | 1 |

Outside the decisive set (run only if the queue has room; GOP configurations are out of scope under requirement 10):

| Timed question | bench_manifest ids | Note |
|---|---|---|
| Sync spread and seek latency for all-intra `<video>` (`mid`) and WebCodecs at 1080p | `bench_sync_*`, `bench_seek_*` with `--only intra` | the only in-scope video alternative to JPEG (I2 vs I3) |
| Scrub smoothness: frames shown and distinct per second, lag to the slider, N=1 and 4 | `bench_scrub_e35`, `bench_scrub_e45` (`--only intra` / `--only mjpeg`) | |
| Single-step latency, intra and JPEG | `bench_step_e35`, `bench_step_e45` (`--only intra` / `--only mjpeg`) | |
| Does `<video>` or WebCodecs decode on NVDEC here? (only before/after nvidia-smi samples) | `bench_sync_*`, `bench_seek_*` | |

Verifier requests (functional, but longer than the 1-minute budget):
- Exhaustive sweep of every frame with `mid` and WebCodecs on the vfr720p and c720p30 clips, both Electrons. Decides whether F10/F15 can say "every frame": `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/verify_method/exhaustive_mid_sweep.py --electron 45` (then 35). Output: `functional/e<ver>/exhaustive/`. The script runs all 28 configurations (GOP included) and has no intra filter. Under requirement 10, add one before running, or accept the GOP configurations as background. JPEG paths are not in the sweep.
- Report bench_seek seed-11 `exact` counts next to F10/F16 as an independent sample.

## 6. Not tested, limits, NOT VERIFIED

- Clips were encoded with PyAV 18.0.0 (background). Only the recorder index, the WebM offset, the pattern readback (F10, F18) and encoder ordering (F25) were re-checked on PyAV 19.0.2. No Electron run used a PyAV 19 file. Loading `pyav19_check/*` in both Electrons was not done.
- Regenerating the clips with PyAV 19 was **not** done (over the 1-minute budget). `gen_clips.py` writes to fixed paths (`MEDIA` at `:41`, `clips_summary.json` at `:252`), so a rerun would overwrite the PyAV 18 clips and their evidence. Before a rerun, add an output-dir option or move the old clips and summary aside.
- Hard-coded paths into the old session's scratchpad (`106dc0c8-...`):
  - Electron 45.2.3: `run_suite.py:34-38`; the runner exits with "missing ..." at `:238-239` if it is absent.
  - mp4box.js: `harness/server.cjs:20` (override with env `CSS_MP4BOX_DIST`). The runner does not check it up front, so a missing copy fails only the in-page mp4box test.
  - Both were present on 2026-11-09 (checked).
- Single machine: Windows 11, RTX 3070. Chromium listed no Intel device during these runs (F22), although the UHD 770 is reported present now. No macOS/Linux, no Intel/AMD GPU decode, and no forced software decode.
- NVDEC use by Chromium: NOT VERIFIED. Only Chromium's `powerEfficient` / prefer-hardware answers exist (F22).
- Chromium playback of NVENC/QSV-encoded files (the encode target, HANDOFF §1 req 3) was not tested (F25).
- The real UI was not run: no React component, no backend streaming, no 5-camera real recording. The harness re-implements the seek math and leader/follower rule from the code (F1-F4).
- No multi-camera clips with different capture times: all N streams in `bench_sync` are the same clip. Sync by capture timestamp vs by frame index is an open design question.
- Sampling: one seed per test type, single runs, 169-185 distinct frames per file for seeks (section 2.3). "Every frame" is not shown (see the exhaustive sweep in section 5).
- Intra coverage: one intra VFR file (AV1 MP4); no intra hdr329 video clip; steps on `av1_intra.mp4` only.
- Clips are short (600 to 891 frames). The 1080p and 720p60 content is 19 and 10 real frames looped. Hour-long files, large moov, many fragments and Range on multi-GB files were not tested.
- Unreadable pattern on frames 66, 306, 322 of the c1080p30 AV1 GOP files (F10).
- NOT VERIFIED: root cause of the Chromium 134 stuck-frame case (F23); the e35-only extra misses (F9); the mechanism of the `mid` failures on the near-duplicate pair (F16a, F9).
- `av_rescale_q` rounding in Chromium's FFmpeg revision and the truncation in `base::Seconds` are read from code, not traced to the exact FFmpeg revision. The truncation detail is NOT VERIFIED. It is supported by the model match in F9.
- WebM: pos = SimpleBlock body start is inferred (F18); laced, multi-track or track ≥ 128 blocks not tested. WebM in-page demux and MSE playback not tested.
- Whether PyAV can report byte offsets during writing was not tested. The index here was built by demuxing the finished file.
- CPU and memory samples were removed from the functional JSONs because the machine was shared (`note` key in each functional JSON). There are no timing numbers in this topic.

## 7. How to reproduce

From the repo root `C:/Users/Dom/GitHub/freemocap/skellycam`. Media only under `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/chromium_sync_scrub/`. All scripts are in `research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/` (local, not committed).

```
P=research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub
R=research/skellycam_recording/recording_upgrade/results/chromium_sync_scrub
M=C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/chromium_sync_scrub

# clips (PyAV 18, skellycam venv: background; overwrites fixed paths, see section 6)
.venv/Scripts/python.exe $P/gen_clips.py
.venv/Scripts/python.exe $P/gen_clips.py --only hdr329

# functional suites (run_suite removes ELECTRON_RUN_AS_NODE)
.venv/Scripts/python.exe $P/run_suite.py --electron 35 --suite functional
.venv/Scripts/python.exe $P/run_suite.py --electron 45 --suite functional
.venv/Scripts/python.exe $P/run_suite.py --electron 35 --suite functional_targeted
.venv/Scripts/python.exe $P/run_suite.py --electron 45 --suite functional_targeted
.venv/Scripts/python.exe $P/compare_jpeg_decode.py
.venv/Scripts/python.exe $P/summarize.py functional

# PyAV 19.0.2 checks (F10, F18)
uv run --script $P/pyav19_recorder_index_check.py research/usb_cameras/results/windows/Gerald/timing/flash_run1_repositioned/capture/vid_046d_pid_0843_mi_00_8_39dec205_0_0000.frames.jsonl $M/pyav19_check $R/pyav19_recorder_index_check.json
uv run --script $P/webm_pos_delta.py $R/pyav19_webm_pos_delta.json $M/pyav19_check/pyav19_av1_gop.webm $M/pyav19_check/pyav19_vp9_gop.webm $M/clips/c720p30/av1_gop.webm $M/clips/c720p30/vp9_intra.webm
uv run --script $P/pyav19_pattern_check.py $R/pyav19_c1080p30_av1_pattern_check.json $M/clips/c1080p30/av1_gop.mp4 $M/clips/c1080p30/av1_gop.webm $M/clips/c1080p30/av1_gop_frag.mp4 $M/clips/c1080p30/av1_intra.mp4

# verifier checks (F9 model, F25 encoder ordering, exhaustive sweep): $P/verify_method/{model_seek,hw_reorder_check,hw_reorder_check_bf0,exhaustive_mid_sweep}.py

# tonight (one at a time, quiet machine): see section 5
.venv/Scripts/python.exe $P/run_suite.py --electron <35|45> --suite bench_sync --only mjpeg
.venv/Scripts/python.exe $P/run_suite.py --electron <35|45> --suite bench_seek --only c1080p30/mjpeg
.venv/Scripts/python.exe $P/summarize.py bench
```

Raw-total recomputation: every total in section 2 was recomputed by summing `summary.exact` and `summary.n` over `result[]` in `functional/e{35,45}/{seek,step}_batch.json` and `targeted.json`, grouped by content, file family, path and mode. They match `functional_tables.md`.

## 8. Verification

Challenged by `VERIFY_provenance.md` and `VERIFY_method.md` (2026-11-09). Each refutation was re-checked against the raw JSON or code before it was applied.

What changed:

| Draft claim | Check made in this revision | Change |
|---|---|---|
| F10 / 3.1: `mid` exact "for every readable frame", "Real VFR 100 %" | Rebuilt seed-1 mulberry32: 169/600 and 185/891 distinct, frames 80-82 never sampled; targeted e35 GOP WebM 5/9, e45 GOP 7/9 | Refuted. Now "every sampled seek", with the F16a exception and the seed reuse stated |
| F11 all-intra row 400/400, 200/200 | `e35/seek_batch.json`: `c720p60/av1_intra.mp4` `ui` 198/200 (off 13, 591) | Refuted. Intra results moved to F10a with the c720p60 e35 exception |
| F13 "always -1" | e35 `ptsexact` c720p30 GOP WebM off_by_hist `{13:1, 591:1, -1:3}` | Refuted. Exception added (stuck case) |
| §6 mp4box path in `run_suite.py:34-38` | `run_suite.py:34-38` has only the Electron paths; mp4box at `harness/server.cjs:20`; both paths present | Refuted. Corrected |
| I6 6.5x-7.4x | 9,634,168 / 3,331,315 = 2.89 | Refuted. Now 2.9x-7.4x, ratio column added |
| F10 libavcodec claim (no result file) | New PyAV 19.0.2 decode of all frames: 66, 306, 322 unreadable, 0 wrong (`pyav19_c1080p30_av1_pattern_check.json`); rVFC `mt_idx` = k | Upgraded to measured, PyAV 19 |
| F10 parenthetical family totals | Per-file: each AV1 GOP file 198/200 | Fixed |
| F5 label | `REPORT.md:28` | Relabelled measured (prior study); range 32.8-33.25 fps |
| F15 `optimizeForLatency` | `harness.mjs:105-106` | Relabelled code; stated as a condition |
| F14 step description | `harness.mjs:235-239`, `run_suite.py:113-115`; starts recomputed | Fixed: 2 starts, seed 2, 40 forward, 80 back, 2 seeks |
| F16 JPEG steps | `run_suite.py:115` | Limited to `jpeg-range-imagedecoder` |
| F16a gap citation | `pyav19_recorder_index_check.json` `gap_81_82_ms` | Fixed |
| F18 SimpleBlock NOT VERIFIED | RFC 9559 downloaded, quotes found verbatim in §10.2 | Upgraded to source; pos mapping stays inferred |
| F18 bare file names | Script copied, changed to store full paths, re-run: same 4-byte result | Fixed |
| §7 scratchpad scripts | Copied `pyav19_recorder_index_check.py`, `webm_pos_delta.py`, `verify_method/*.py` into `scripts/chromium_sync_scrub/` | Fixed |
| 3.3 "600 distinct frames" | `clips_summary.json`: frames 600, distinct_source_frames 891 | Fixed |
| I5 HEVC | `caps.json` | Limited to WebCodecs |
| I8 "slightly worse" | `e45/targeted.json` rows `(82 → 81, mt_idx 81)` | Rewritten: MP4 worse, WebM better; frame 82 never shown with `mid` in e45 GOP |
| I8 / F23 End key | `targeted.json` `ui` rows; hdr329 last pts 18.2067 s in `clips/manifest.json` | Scoped to the one observed case |
| I1 hdr329 | clip is synthetic | Labelled |
| I2, I5, F15 generalisation | `verify_method_hw_reorder_*.json` | Limited to non-reordering streams; new F25 |
| F9 mechanism | `verify_method_seek_model.txt` | Model support added; e35 extras and pair failure NOT VERIFIED |
| §6 hdr329 rVFC 195/200 "not checked" | Seed-1 recount: 21/200 targets ≥ k 548 past the end; k 599 sampled once | Moved to F11 as measured |
| §6 gen_clips regeneration | `gen_clips.py:41,252` fixed paths | Overwrite risk noted |
| Scope (not raised by verifiers) | HANDOFF §1 req 10-11 (added 17:20) | GOP marked background; intra table F10a added; bench list trimmed to the decisive JPEG set |

Remains NOT VERIFIED or untested:
- "Every frame" exactness for `mid`, WebCodecs and JPEG (needs the exhaustive sweep).
- Root cause of the Chromium 134 stuck case; the e35-only extra misses; the mechanism of the near-duplicate `mid` failures.
- `base::Seconds` truncation traced to the exact FFmpeg revision.
- NVDEC use by Chromium; Chromium playback of NVENC/QSV files; PyAV 19 files in Electron.
- WebM `pos` = SimpleBlock body start (inferred); laced/multi-track blocks.
- Every timing question (section 5).

Outside this file: `results/bench_queue_from_wf_2e122ed0.json` → `chromium_sync_scrub.summary` says "37 test clips". `clips_summary.json` has 35 entries (30 video + 5 MJPEG). Not edited here.
