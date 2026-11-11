# Overlays as a separate layer (G3): findings

Study 2026-11-09, machine Gerald (Windows 11). CPU Intel Core i7-14700K (**measured** `results/uncompressed_intra/verify_method/cpu_topology.txt:3`). GPU seen by Chromium: NVIDIA vendorId 4318, deviceId 9348 (RTX 3070), driverVersion 32.0.16.1088 (**measured** `results/overlays/electron_*.json` → `env.gpuInfo.gpuDevice`). That this is NVIDIA driver 610.88 is **inferred** from the usual NVIDIA version mapping.

Topic folders: `research/skellycam_recording/recording_upgrade/{scripts,results}/overlays/`. Paths are relative to `research/skellycam_recording/recording_upgrade/` unless they start with `skellycam/`, `skellycam-ui/` or `freemocap`. Media: `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/overlays/` (`<raw>/overlays`).

Labels:
- **measured** = result file (path given).
- **source** = primary source (URL, quote, accessed 2026-11-09).
- **code** = file:line.
- **inferred** = reasoning, kept short.
- "PyAV 18 - background" = made with the skellycam venv (PyAV 18.0.0), not the implementation under test (PyAV 19.0.2).
- "ffmpeg CLI - background" = made with the gyan ffmpeg 9.0.2 CLI. Under the study rules the CLI may only inspect files.

This file has no timing, throughput or CPU numbers. `results/overlays/bench/` is empty and this topic has no `BENCH.md`. All timed questions are in section 5.

Provenance checks for this file:
- `electron_summary.md` was regenerated from the raw `electron_35.7.5.json` and `electron_45.2.3.json` with `summarize_electron.py`. The output is byte-identical to the committed summary after the title line. Both verifiers repeated this independently (`results/overlays/VERIFY_provenance.md`, `VERIFY_method.md`).
- The PyAV-dependent functional results were re-run on PyAV 19.0.2 at 60 frames: `results/overlays/pyav19_functional_check.json`, script `scripts/overlays/pyav19_functional_check.py`.
- Verifiers added two crash/precision checks (pure Python + numpy + msgspec, no PyAV):
  - `results/overlays/verify_method_crash_modes.json` (script `scripts/overlays/verify_method_crash_modes.py`)
  - `results/overlays/verify_method_precision.json` (script `scripts/overlays/verify_method_precision.py`)

## 1. Questions answered

1. What overlays exist today, where are they drawn, and do they overlap?
2. Which storage form for overlays, kept apart from the camera frames, is smallest and survives a crash? Options: data sidecar, SVG/ASS vector files, or an alpha video layer.
3. Can Chromium (Electron 35.7.5 and 45.2.3) draw a separate overlay frame-accurately over `<video>`, and with which method?
4. Can overlap between labels be removed deterministically?
5. Can overlays still be burned in for export or sharing, and does that work through PyAV 19.0.2?

## 2. Findings

### 2.1 Today's overlays (inventory)

- skellycam burns `camera.id{id}.idx{index}.fr{N}` into every recorded frame. It uses `cv2.putText` at (10,40), scale 0.8, with a black outline of thickness 8. No clean copy of the frame is kept (**code** `skellycam/core/camera/opencv/opencv_helpers/opencv_get_frame.py:79-90`).
- The burned stamp covers about x 5-340 and y 15-50 px. Its pixel size is the same at 720p and 1080p (**measured**, background study: `research/skellycam_recording/results/real_recording_20261109/RESULTS.md:145`).
- skellycam-ui playback draws nothing into the video pixels. It shows HTML frame and time labels absolutely positioned over each `<video>` (**code** `skellycam-ui/src/components/playback/SyncedVideoPlayer.tsx:281-308` `updateOverlays`; `:658-700` `position: 'absolute'`, `showOverlays`).
- The frame number in those labels is `Math.floor(leader.currentTime * fps)`, computed in a rAF loop (**code** `SyncedVideoPlayer.tsx:377-403`, floor at 401).
- skellycam-ui seeks with `currentTime = frame / fps` (**code** `SyncedVideoPlayer.tsx:334-335, 506-507`).
- FreeMoCap's live ChArUco renderer draws an info panel with `fillRect(5, 5, 500, 85)` (**code** freemocap `freemocap-ui/src/services/server/server-helpers/image-overlay/charuco-overlay-renderer.ts:165`).
- That panel covers skellycam's stamp area of x 5-340, y 15-50 (**inferred** from the two coordinates).
- FreeMoCap's live worker keeps only the latest overlay observation of each type and drops it after `OVERLAY_STALE_MS = 500`. Overlays are not matched to a frame number (**code** freemocap `offscreen-renderer.worker.ts:17,26-29,62-63,83`).
- FreeMoCap post-hoc burns skellytracker annotations into `annotated_videos/<stem>_annotated<source suffix>` (**code** freemocap `freemocap/core/pipeline/posthoc/video_node.py:211-219`, `f"{video_path.stem}_annotated{video_path.suffix}"`).
- FreeMoCap already sends overlays to the UI as per-frame point blocks keyed by `frame_number`, as float32 or float64 (**code** freemocap `freemocap/api/websocket/binary_keypoints_protocol.py:15` `dtype_code = Dtype.FLOAT32 | FLOAT64`, `:58-64`).
- skellytracker's "Undetected Corners" list fits 35 lines at 720p and 53 lines at 1080p before it leaves the image:
  - This is arithmetic, `(h-40)//20+1`, and counts a baseline at y = H as fitting (**code** `scripts/overlays/label_layout.py:186`, result in `results/overlays/label_layout.json`).
  - The test data never came near that limit: `max_undetected_in_a_frame: 9` (**measured** `label_layout.json`).

### 2.2 Storage formats: size, round trip, crash modes

Test data: synthetic FreeMoCap-shaped data, 300 frames, extrapolated at 30 fps. Point coordinates are pre-rounded to 0.01 px (**code** `scripts/overlays/overlay_model.py:62`, `np.round(..., 2)`). Every JSONL and WebVTT size below assumes that precision.

Software: pure Python + numpy + msgspec, with no PyAV import, so the PyAV version rule does not apply.
- **code** `scripts/overlays/formats_functional.py:15-25`
- **code** `overlay_model.py:19` ("Only numpy, cv2 and msgspec are needed")
- **code** `overlay_model.py:231,248` (msgspec imports)
- The msgspec version 0.21.1 comes from `.venv/Lib/site-packages/msgspec-0.21.1.dist-info`. It is not recorded in the result JSON.

Sizes:
- Full "all" overlay at 720p (**measured** `results/overlays/formats_functional.json`):
  - custom CRC-framed binary `.skov`: 3287.6 B/frame = 355.1 MB/h
  - JSONL: 5704.3 B/frame = 616.1 MB/h
  - length-prefixed MessagePack: 6895.6 B/frame = 744.7 MB/h
  - WebVTT, one JSON cue per frame: 5735.6 B/frame = 619.4 MB/h
- JSONL is 1.74x the size of `.skov` for "all" at 720p, with 0.01 px coordinates: 5704.3 / 3287.6 = 1.735 (**measured**, arithmetic).
- With the same frames stored as unrounded float32 values:
  - JSONL is 13,795.3 B/frame and WebVTT 13,826.6 B/frame. That puts JSONL at 4.2x `.skov` (**measured** `results/overlays/verify_method_precision.json`).
  - `.skov` and MessagePack do not change size.
  - So the JSONL/`.skov` ratio is 1.74x to 4.2x, depending on how many decimals the writer emits. Compression of either format was not tested.
- `.skov` is the smallest data form for the skeleton, charuco and "all" cases. For "text" only, MessagePack is the smallest: 31.4 B/frame, against 42.3 for `.skov` and 45.9 for JSONL (**measured** `results/overlays/formats_functional.md`).
- Render-level vector forms at 720p for "all" (**measured** `formats_functional.json`):
  - SVG per frame: 35283.3 B/frame = 3810.6 MB/h
  - one SVG per recording: 35161.9 B/frame = 3797.5 MB/h
  - ASS: 17056.0 B/frame = 1842.0 MB/h
- SVG per frame is 10.7x `.skov` and 6.2x JSONL for "all" at 720p (**measured**, arithmetic).
- 1080p sizes differ from 720p by at most 5.4% (ASS skeleton: 2770.2 vs 2628.0 B/frame). `.skov` and MessagePack sizes are identical at both resolutions (**measured** `formats_functional.md`).
- The small 1080p difference follows from the fixed 0.01 px precision (**inferred**).
- Why MessagePack is larger than JSONL in the point-heavy cases (skeleton, charuco, all): the likely reason is that msgspec writes the float64 arrays as float64 (**inferred**, not tested). This does not hold for "text", where MessagePack is smaller.

Crash and corruption modes:
- Clean tail cuts of a finished file (**code** `formats_functional.py:98-112`): JSONL, MessagePack, `.skov` and WebVTT each recovered every complete record and returned no corrupt record, at 28/28 cuts, in every case and at both resolutions (**measured** `formats_functional.json`, `trunc_recovered_all_complete`, `trunc_errors: []`).
- At one cut per text format (JSONL, WebVTT), a cut just before a record's newline also returned that record intact (**measured**, `trunc_cuts_with_extra_record_before_newline: 1`).
- Other crash modes, 300 frames, 720p, "all", using the study's own readers (**measured** `results/overlays/verify_method_crash_modes.json`):

  | mode | `.skov` | JSONL | MessagePack | WebVTT |
  |---|---|---|---|---|
  | cut + 64 KiB zero tail | 149 returned, 0 wrong | 149, 0 wrong | 149, 0 wrong | 149, 0 wrong |
  | 4 KiB zero hole mid-file | 298, 0 wrong | 299, 0 wrong | **149** (reader cannot resync after the hole) | 298, 0 wrong |
  | one byte changed in record 150 | 299, 0 wrong (CRC rejects the record) | 300, **1 wrong returned silently** | 300, **1 wrong** | 300, **1 wrong** |

- Only `.skov` detected the corrupted record (**measured**, same file).
- The single SVG per recording fails a strict XML parse at 25/25 cuts. A lenient regex reader recovers 10-288 or 11-288 groups, depending on the cut (**measured** `formats_functional.json`, `trunc_strict_parse_failures`, `trunc_lenient_groups_recovered_min_max`).
- SVG per frame: all 300/300 files parse independently (**measured**). No cut test was run on SVG per frame.
- In Chromium (Electron 35.7.5 and 45.2.3), the full single SVG loads as `<img>`. Cut at 50%, it fires the `img` `error` event and `DOMParser` reports a parser error (**measured** `electron_*.json` → `trunc`).
- A WebVTT file cut at 50% still loads 150/300 cues in Chromium, but the last cue's JSON payload fails to parse (`lastCuePayloadParses: False`) (**measured**, same).

### 2.3 Chromium alignment: overlay vs video frame

Setup:
- Electron 35.7.5 (Chromium 134.0.6998.205) and 45.2.3 (Chromium 156.0.8078.80), scaleFactor 1 (**measured** `electron_*.json` → `env`).
- Chromium's basic GPU info lists only the RTX 3070 and the Microsoft Basic Render Driver (vendorId 5140). The Intel iGPU was absent during these runs (**measured**, `env.gpuInfo.gpuDevice`).
- Whether each file was decoded in hardware or software was not recorded (**code** `scripts/overlays/electron_harness/main.js:98-100` stores only `getGPUInfo('basic')`).

How the measurements were made:
- The test videos were encoded with PyAV 18 (libx264, libvpx-vp9, libsvtav1) and with the ffmpeg CLI (**measured, PyAV 18 / ffmpeg CLI - background** `results/overlays/make_test_media.json`). These tests exercise Chromium, not the encoder.
- The reference frame in every rVFC and rAF check is the barcode read with `drawImage(video)` + `getImageData` inside that callback. It is not the frame on screen (**code** `electron_harness/harness.js:196-226`).
- "Captures" are `webContents.capturePage` snapshots requested over HTTP on every 10th rVFC callback (**code** `harness.js:206`, `main.js:81-90`). They show compositor output, not necessarily scan-out.
- Every callback runs heavy synchronous readback instrumentation: a video `drawImage` + `getImageData` and an overlay self-check readback in rVFC, plus a parallel rAF loop that reads back about 60 times a second (**code** `harness.js:196-226`).
- The rAF loop ran 598/599 times in a 10 s, 300-frame play (**measured** `electron_*.json` → `play.base_cfr_vp9.webm.raf`), which suggests a display at about 60 Hz (**inferred**).
- The machine was shared with other agents. Every count is from a single run on a loaded machine, so the counts show patterns, not stable rates.

Results:
- **rVFC lookup.** An overlay looked up from `requestVideoFrameCallback` `metadata.mediaTime` (nearest entry in a per-frame pts table) matched the frame `drawImage` read in the same callback at 1x (**measured** `electron_summary.md`):

  | Electron | CFR H.264 | CFR VP9 | CFR AV1 | VFR VP9 | VFR H.264 |
  |---|---|---|---|---|---|
  | 35.7.5 | 299/299 | 299/299 | 297/297 | 299/299 | 291/295 |
  | 45.2.3 | 299/299 | 299/299 | 296/296 | 282/287 | 290/292 |

- **`round(mediaTime*30)`** is right only for CFR: 299/299 for CFR VP9, but 149/299 for VFR VP9 in E35 and 147/287 in E45 (**measured**, same).
- **Today's UI rule, `floor(currentTime*30)` in rAF**, compared against the frame `drawImage` returned in the same rAF (**measured**, same; offsets from `electron_*.json` → `rafUiOffsets`):
  - E35 matches: 111/597, 289/598, 464/595, 36/602, 153/602 (CFR H.264, CFR VP9, CFR AV1, VFR VP9, VFR H.264).
  - E45 matches: 35/600, 58/599, 13/596, 145/604, 100/604 (same order).
  - CFR mismatches were all offset -1, except one +1 in E45 CFR H.264.
  - VFR mismatches were mostly +1/+2, with -1 in the rest. Positive vs -1 counts: E35 VP9 302 vs 264, E35 H.264 302 vs 147, E45 VP9 304 vs 155, E45 H.264 304 vs 200.
- **This rule's match rate is unstable between runs.** The same file in the same Electron version ran the identical rAF loop in two runs that differed only in draw mode (plain vs `@canvasComposite`). CFR VP9 gave 289/598 vs 522/597 in E35, and 58/599 vs 169/600 in E45 (**measured**, same). So these counts cannot rank codecs or Electron versions.
- **What the offsets show and don't show.** The VFR +1/+2 offsets show that `floor(currentTime*fps)` is wrong for VFR (**inferred**). The CFR -1 offsets are against the `drawImage` frame, which can lead the screen (see the dual-video result below), so they do not measure what the user sees (**inferred**).
- **Canvas over `<video>`.** A separate overlay canvas layered over `<video>` matched the video in 3/30 to 19/30 capturePage captures at 1x. Every mismatch had the form `[video N, overlay N-1]`, with 0 exceptions across all 10 1x runs (**measured**, `capture mismatches` column; full lists are uncapped per `harness.js:212`).
  - The direction (overlay one frame behind) is supported.
  - How often it happens is not: the readback instrumentation can delay the canvas commit (**inferred**). A run without the instrumentation was not made.
- **Video drawn into the overlay canvas** (`drawImage(video)` in rVFC) matched in the captures 29/29 (CFR VP9, E35), 30/30 (VFR H.264, E35), 30/30 (CFR VP9, E45) and 29/29 (VFR H.264, E45) (**measured**, `@canvasComposite` rows).
  - Both barcodes are read from the same canvas (**code** `harness.js:61`). So this shows that video and overlay commit together.
  - Correct pairing still depends on `drawImage` returning the `metadata` frame, which the rVFC check already counts.
- **At 2x (CFR VP9, canvas over `<video>`).** The rVFC lookup matched the `drawImage` frame in 169/241 (E35) and 269/281 (E45) callbacks. Captures matched 0/24 and 0/28 (**measured**, `@2x` rows).
  - E35: 72/241 mismatched. The harness keeps only 20 examples (**code** `harness.js:201`), and all 20 recorded examples were `drawImage` one frame ahead of the lookup.
  - E45: all 12 mismatches were recorded, and all were one ahead (**measured** `electron_*.json` → `play['base_cfr_vp9.webm@2x'].overlayMismatch`).
  - The canvas-composite path was run only at 1x (**code** `harness.js:522-523`).
- **The rVFC spec allows a lag:** "a callback can occasionally be fired one v-sync late, relative to when the new video frame was presented" and "drawing operations might occasionally appear on screen one v-sync after the video frame does" (**source** https://wicg.github.io/video-rvfc/ §1 Introduction, accessed 2026-11-09).
- The spec defines `mediaTime` as "The media presentation timestamp (PTS) in seconds of the frame presented" (**source** https://wicg.github.io/video-rvfc/ §2.2, accessed 2026-11-09).
- **Paused seeks to a frame's exact pts** showed the requested frame in (**measured** `electron_summary.md`, paused-seek tables):

  | file | E35 | E45 |
  |---|---|---|
  | CFR H.264 | 80/80 | 80/80 |
  | CFR VP9 | 79/80 (f241->240) | 79/80 (f241->240) |
  | CFR AV1 | 78/79 (f241->240) | 78/79 (f241->240) |
  | VFR VP9 | 43/80 | 56/80 |
  | VFR H.264 | 42/80 | 80/80 |

- **Seeking to the midpoint between pts f and f+1** gave (**measured**, same):

  | file | E35 | E45 |
  |---|---|---|
  | CFR H.264 | 80/80 | 80/80 |
  | CFR VP9 | 80/80 | 80/80 |
  | CFR AV1 | 79/79 | 79/79 |
  | VFR VP9 | 80/80 | 80/80 |
  | VFR H.264 | 76/80 | 79/80 |

  The midpoint was not better everywhere: E45 VFR H.264 gave 80/80 at the exact pts but 79/80 at the midpoint.
- In every paused-seek case, the frame shown equalled the rVFC `mediaTime` lookup (80/80 or 79/79). The capturePage composites all matched at +100 ms. Immediately after the seek, as few as 64/79 matched (CFR H.264 exact, E45) (**measured**, same).
- **Electron 35.7.5 last-frame bug.** After a seek to the last frame (299), every later seek (150, 0, 299, duration, 75) still showed frame 299, with no rVFC callback and `ended` true, in all 5 files (**measured** `electron_summary.md`, last-frame tables).
- **Electron 45.2.3 is not stuck after a last-frame seek, in 5/5 files.** The CFR files showed exactly 150, 0, 299, 299, 75. Each VFR file had one off-by-one result: VFR VP9 `75->74`, VFR H.264 `duration->298` (**measured**, same).
- **Two `<video>` elements played together** (base + VP9-alpha layer) matched in every capturePage capture: 25/25 (E35) and 27/27 (E45).
  - Reading both with `drawImage` inside the base's callback found the layer one frame ahead in 136/250 (E35) and 195/271 (E45) callbacks. The offset is layer minus base (**code** `harness.js:399`).
  - Paused seeks of both elements: 30/30 on the requested frame (**measured** `electron_summary.md`, VP9-alpha section).
  - So `drawImage` can disagree with what the compositor shows (**inferred**).
- The AV1 test file has a wrong barcode at frames 14 and 254 in both Electron versions, which is why it decoded 297/297 and 296/296 rather than 299 (**measured** `electron_*.json` → `play['base_cfr_av1.webm'].decodeFailAt`, fi 14 and 254).

### 2.4 WebVTT and subtitle tracks in Chromium

Method: each check reads `track.activeCues` inside rVFC and compares it with the `drawImage` frame (**code** `harness.js:319-330`). This tests the `activeCues` mechanism. It does not test WebVTT used as a data file with cues looked up by rVFC `mediaTime`.

- **CFR cues during playback:** a `<track kind=metadata>` cue matched the `drawImage` frame in 148/299 (E35) and 8/299 (E45) callbacks. All the rest were offset -1 (**measured** `electron_summary.md`, WebVTT table). These are single runs on a loaded machine.
- **Shifted and VFR cues:**
  - cues shifted half a frame earlier: 207/299 (E35), 18/298 (E45);
  - VFR with cue times equal to the container pts: 95/285 (E35), 32/286 (E45) (**measured**, same).
- **Paused seeks:** 40/40 for CFR in both versions; VFR 30/40 (E35) and 32/40 (E45) (**measured**, same).
- **In-band tracks:** WebVTT muxed into WebM and ASS muxed into MKV both load, but expose `textTracks.length` 0 in both versions (**measured**, in-band table).
- `canPlayType('video/x-matroska')` is `''` in E35 and `'maybe'` in E45 (**measured**, MIME tables).
- WebVTT timestamps have millisecond resolution: "Three ASCII digits, representing the thousandths of a second seconds-frac as a base ten integer" (**source** https://www.w3.org/TR/webvtt1/ §4.1, accessed 2026-11-09).
- On metadata cues, the spec says "WebVTT metadata text cues are only useful for scripted applications" (**source** same URL, §4.2.1) and "Metadata can be any string and is often provided as a JSON construct" (**source** same URL, §1.7).
- **ASS timing is in centiseconds.**
  - FFmpeg's ASS demuxer computes `*start = (hh1*3600LL + mm1*60LL + ss1) * 100LL + ms1;` and calls `avpriv_set_pts_info(st, 64, 1, 100);` (**source** https://raw.githubusercontent.com/FFmpeg/FFmpeg/n8.0/libavformat/assdec.c lines 72 and 118, fetched 2026-11-09).
  - This is the FFmpeg n8.0 tag. Whether the PyAV 19.0.2 build matches is NOT VERIFIED. The point is moot for PyAV, because its wheel has no `ass` filter (2.6).
- ASS muxed into MKV produced 30,898 packets for 300 frames. The 6 packets kept in the record (`first6`) are each 0.03 s long (**measured, ffmpeg CLI - background** `make_test_media.json` → `ass_mkv_packets`).

### 2.5 Alpha video overlay layer

Sizes:
- VP9-alpha WebM (libvpx-vp9, yuva420p, crf 32, realtime, cpu-used 8, g 30, 300 frames, "all" overlay at 720p): 80,251 B/frame = 24,075,364 bytes (**measured, ffmpeg CLI - background** `make_test_media.json`).
- PNG-in-MOV: 155,859 B/frame. QTRLE-in-MOV: 290,996 B/frame (**measured, ffmpeg CLI - background**, same).
- The camera's own JPEG for this frame set: median 56,759 B (min 51,085, max 65,760) (**measured** `C:/Users/Dom/Documents/skellycam-raw/.../corpus/index.json` → `c930e_720p_flash.bytes_median`).
- PyAV 19.0.2 re-check: the same overlay encoded through PyAV 19 (libvpx-vp9, `pix_fmt yuva420p`, same options, 60 frames) gave 3,840,349 bytes = 64,006 B/frame (**measured** `results/overlays/pyav19_functional_check.json` → `alpha`).
  - The frame counts differ (60 vs 300), so this is not a like-for-like size comparison.
  - Both sizes come from one encoder setting and from synthetic labels that move every frame (**code** `make_test_media.py:186-187`, `pyav19_functional_check.py:182`).
- So the alpha layer is 19.5x (PyAV 19) to 24.4x (CLI) the `.skov` size, for this setting and content only (**measured**, arithmetic).

Chromium:
- The CLI-encoded VP9-alpha WebM loads in Chromium 134 and 156. Frame 0 has alpha==0 on 0.8746 of its pixels (**measured, CLI-encoded file - background** `electron_summary.md`, VP9-alpha section).
- PNG-MOV and QTRLE-MOV fail with `DEMUXER_ERROR_NO_SUPPORTED_STREAMS` in both versions (**measured**, load table).
- The PyAV-19-encoded alpha file was not loaded in Chromium.

Truncation:
- After a 50% cut, the CLI VP9-alpha file still decoded 160 frames, all with transparency. PNG-MOV and QTRLE-MOV decoded 0 frames (`Invalid data found when processing input`) (**measured, ffmpeg CLI - background** `results/overlays/alpha_truncation.json`).
- The MOV files were written without `movflags`. So the 0-frame result applies to non-fragmented MOV with the moov atom at the end, not to the codecs (**code** `make_test_media.py`, no `movflags`; **inferred**).
- All of these cuts were of finished files, not files from a killed writer.
- **PyAV 19.0.2 confirms the alpha truncation result.** A 50% cut of the PyAV-19-encoded file, decoded with the `libvpx-vp9` decoder through PyAV, gave 30 frames, all with transparency, and no errors (**measured** `pyav19_functional_check.json` → `alpha.trunc50`).

Decoding alpha in PyAV 19.0.2:
- **Only the `libvpx-vp9` decoder keeps alpha.** The stream reports `pix_fmt yuv420p` with metadata `alpha_mode: 1`. PyAV's default decoder (FFmpeg's native `vp9`) returns `yuv420p` frames, so alpha is dropped. `av.CodecContext.create("libvpx-vp9", "r")` returns `yuva420p` on 60/60 frames (**measured** `pyav19_functional_check.json` → `alpha`).
- With that decoder:
  - the maximum per-frame mean absolute alpha difference from the source matte is 0.4572 of 255;
  - the overlay barcode reads correctly in 60/60 frames;
  - frame 0 has exact-zero alpha on 0.8463 of its pixels, against 0.873 in the matte (**measured**, same, `libvpx_decoder`).
- The earlier CLI decode gave a frame-0 alpha mean absolute difference of 0.114 (**measured, ffmpeg CLI - background** `make_test_media.json` → `vp9alpha_decode_check`).
- The CLI's zero fraction used a `< 8` threshold (**code** `make_test_media.py:205`), so it is not comparable to the exact-zero PyAV figure.

### 2.6 Export with overlays burned in

- **P1: sidecar → cv2 burn-in → encode, 300 frames.** libvpx-vp9 WebM 300/300 aligned (15,215,723 B); libx264 MP4 300/300 aligned (11,827,653 B) (**measured, PyAV 18 - background** `results/overlays/export_burnin.json`). "Aligned" means the source-frame barcode equals the overlay-frame barcode in each decoded output frame.
- **PyAV 19.0.2: P1 works for encode, at 60 frames.** The `.skov` sidecar read back 60 frames with 0 bad. libvpx-vp9 WebM gave 60/60 aligned and libx264 MP4 60/60 aligned, with 0 decode failures (**measured** `pyav19_functional_check.json` → `p1`).
  - The script picks the sidecar record by loop index (`by_f[i]`) (**code** `pyav19_functional_check.py:122,133`).
  - So this shows no drop or reorder through encode/decode. It does not show sidecar-to-video pairing when the camera drops frames.
- **P2: ffmpeg `overlay` filter, alpha layer decoded with `-c:v libvpx-vp9`:** 300/300 aligned (**measured, ffmpeg CLI - background** `export_burnin.json`).
- **P2b: same, with the default vp9 decoder:** 1/300. The base barcode read as 0 while the overlay read correctly (**measured**, same). That the layer came out opaque is **inferred** from this barcode readout.
- **PyAV 19.0.2: the P2 compositing works inside Python.**
  - Filter graph: `overlay` with `x=0:y=0:eof_action=pass:format=yuv420`.
  - With the layer decoded by `libvpx-vp9` (`yuva420p`): 60/60 aligned.
  - With the layer from the default decoder (`yuv420p`): 1/60, with the base barcode read as 0 (**measured** `pyav19_functional_check.json` → `p2`).
  - The base input `base_cfr_vp9.webm` was encoded with PyAV 18 (**measured, PyAV 18 - background** `make_test_media.json`). PyAV 19 did the decode, filter and encode.
  - The script sets `fb.pts = fl.pts = i` before pushing both frames (**code** `pyav19_functional_check.py:249`). So it tests alpha compositing, not timestamp pairing of two demuxed files as the CLI P2 did.
- **P3: libass burn-in with per-frame events at centisecond times:** 200/300 aligned, with every third frame showing the previous event. **P3b**, events shifted half a frame earlier: 300/300 (**measured, ffmpeg CLI - background** `export_burnin.json`).
- **The PyAV 19.0.2 wheel has no `ass`, `subtitles` or `drawtext` filters** (**measured** `pyav19_functional_check.json` → `caps`; re-confirmed by the provenance verifier, `VERIFY_provenance.md`). So P3 (libass) cannot run through PyAV 19.0.2. The wheel does have:
  - filters: `overlay`, `alphamerge`, `alphaextract`, `drawbox`;
  - the libvpx-vp9 encoder and decoder, the libx264 and libsvtav1 encoders, and the libdav1d decoder;
  - the png, qtrle, webvtt and ass codecs;
  - the webm, matroska, mp4, mov, webvtt and ass muxers.
- **WebCodecs `isConfigSupported` at 1920x1080**, identical in E35 and E45 (**measured** `electron_summary.md`, WebCodecs table):
  - hardware encode: H.264 and HEVC true; VP8, VP9 and AV1 false;
  - software encode: VP8, VP9, AV1 and H.264 true; HEVC false;
  - hardware decode: VP9, AV1, H.264 and HEVC true.

  This is a capability query, not an encode test, and it was made with the Intel iGPU absent (2.3).

### 2.7 Deterministic label placement

- The placer is greedy: 8 directions x 3 rings, then side lanes with leader lines, then hide and count. It is implemented in Python (`scripts/overlays/label_layout.py`) and in JS (`scripts/overlays/electron_harness/layout.js`).
- Overlap counts for 60 frames and 5,691 labels (**measured** `results/overlays/label_layout.json`):

  | case | skellytracker `Corner#id` (label-label / label-marker) | freemocap-ui id | placed |
  |---|---|---|---|
  | 720p, board 55% of height | 12,272 / 13,397 | 0 / 332 | 0 / 0 |
  | 1080p, board 55% | 9,706 / 10,657 | 116 / 1,450 | 0 / 0 |
  | 720p, board 20% (dense) | 68,733 / 57,092 | 7,223 / 21,957 | 0 / 0 |

- In the dense case, 1,474 labels went to side lanes and 0 were hidden. Two runs were identical (`deterministic: true`), and 0 HUD panel pairs overlapped (**measured**, same).
- In the browser (12 px Arial, both Electron versions), naive +8/-8 placement gave 11 label-label and 322 label-marker overlaps. `placeLabels` gave 0 and 0, and was deterministic (**measured** `electron_summary.md`, layout table).
- Leader-line crossings are not checked. They are visible in `<raw>/overlays/layout/C_placed_720p_board20.png` (**measured**, image; investigator observation).

## 3. Comparison tables

### 3.1 Overlay storage options (720p, full "all" overlay)

| option | B/frame | MB/h @30 fps | crash / corruption behaviour | plays/renders in Chromium | PyAV 19.0.2 path | evidence |
|---|---|---|---|---|---|---|
| `.skov` binary, CRC per record | 3,287.6 | 355.1 | 28/28 clean cuts; resyncs after a zero hole; **rejects a corrupted record** | n/a (UI renders data) | pure Python, no PyAV | measured `formats_functional.json`, `verify_method_crash_modes.json` |
| JSONL (0.01 px) | 5,704.3 (13,795.3 as float32 repr) | 616.1 | 28/28 clean cuts; resyncs; returns a corrupted record silently | n/a | pure Python | same + `verify_method_precision.json` |
| MessagePack (float64) | 6,895.6 | 744.7 | 28/28 clean cuts; **stops at a zero hole** (149/300); returns a corrupted record silently | n/a | pure Python + msgspec | same |
| WebVTT metadata cues (0.01 px) | 5,735.6 | 619.4 | 28/28 clean cuts (Python); resyncs; returns a corrupted record silently; Chromium loads 150/300 cues from a 50% cut, last cue torn | as `<track>`; `activeCues` lag in play (2.4) | pure Python | same + `electron_*.json` |
| ASS | 17,056.0 | 1,842.0 | not tested | no text track exposed | no libass filter in wheel | `formats_functional.json`, `pyav19_functional_check.json` |
| SVG per frame | 35,283.3 | 3,810.6 | not cut-tested; 300/300 files parse independently | not rendered in test | pure Python | `formats_functional.json` |
| one SVG per recording | 35,161.9 | 3,797.5 | strict parse fails 25/25 cuts | 50% cut fires `img` error | pure Python | same + `electron_*.json` |
| VP9-alpha WebM | 80,251 (CLI, 300 fr); 64,006 (PyAV 19, 60 fr) | 8,667 (CLI) | one 50% cut: 160 frames (CLI); 30/30 transparent (PyAV 19) | yes, with alpha (CLI-encoded file - background); PyAV 19 file not tested | encode yes; decode only with `libvpx-vp9` | `make_test_media.json`, `alpha_truncation.json`, `pyav19_functional_check.json` |
| PNG-in-MOV / QTRLE-in-MOV | 155,859 / 290,996 | 16,833 / 31,428 | 0 frames from a 50% cut (non-fragmented MOV) | no (`DEMUXER_ERROR_NO_SUPPORTED_STREAMS`) | not tested | `make_test_media.json`, `alpha_truncation.json` |

### 3.2 Chromium overlay-sync methods (single runs on a loaded machine)

| method | 1x play, frame named == `drawImage` frame | capturePage captures, overlay == video | VFR | evidence |
|---|---|---|---|---|
| today's `floor(currentTime*fps)` in rAF | 13/596 to 464/595; unstable between runs (1.8-2.9x on one file) | not captured | wrong on both CFR and VFR. VFR adds +1/+2 offsets. Match rate is load-sensitive (E35 VFR lower than CFR, E45 VFR higher) | `electron_summary.md`, `electron_*.json` |
| rVFC `mediaTime` → pts table, canvas over `<video>` | 282/287 to 299/299 | 3/30 to 19/30; overlay 1 frame behind (frequency confounded by instrumentation) | works with the pts table | same |
| rVFC + video drawn into the overlay canvas | 287/287 to 299/299 | 29/29 to 30/30 (same-canvas commit) | works with the pts table | same |
| WebVTT metadata `activeCues` | 8/299 to 148/299 | n/a | 32/286 to 95/285 | same |
| second `<video>` with a VP9-alpha layer | `drawImage` layer one ahead in 136/250, 195/271 | 25/25, 27/27 | not tested | same |

### 3.3 Electron 35.7.5 vs 45.2.3 (overlay-relevant differences only)

| item | 35.7.5 | 45.2.3 | evidence |
|---|---|---|---|
| seek after reaching the last frame | stuck on the last frame, 5/5 files | not stuck, 5/5 files; CFR exact; each VFR file had one off-by-one seek | `electron_summary.md` |
| VFR H.264 exact-pts paused seek (single run) | 42/80 | 80/80 | same |
| `canPlayType('video/x-matroska')` | `''` | `'maybe'` | same |
| 2x CFR VP9 rVFC lookup == `drawImage` frame (single run, loaded) | 169/241 | 269/281 | same |
| in-band WebVTT/ASS text tracks | 0 | 0 | same |

## 4. Implications for the plan

All bullets below are **inferred** from the findings cited.

- **Store overlays as an append-only data sidecar keyed by frame number and timestamp.** Not as burned-in pixels, SVG or ASS.
  - The data sidecars are the smallest options (2.2, 3.1).
  - All four recovered every complete record at 28 clean cuts. SVG per frame and VP9-alpha were not tested the same way (2.2).
  - A sidecar also removes skellycam's burned stamp, which today cannot be removed after recording (2.1).
- **Choosing between `.skov` and JSONL.**
  - `.skov` is 1.74x smaller than JSONL at 0.01 px precision, and 4.2x smaller if JSON carries unrounded float32 values (2.2).
  - Only `.skov` rejected a corrupted record. JSONL, MessagePack and WebVTT returned it silently (2.2).
  - JSONL is readable without a custom reader.
  - JSONL with a per-line CRC was not tested. Compression was not tested. The per-frame write cost is pending (section 5).
  - The evidence so far favours a CRC-framed format.
- **Do not use length-prefixed MessagePack without a resync marker.** After a 4 KiB zero hole it lost every later record: 149/300 returned (2.2).
- **Do not use a single SVG per recording.** It fails strict parsing at every cut, and Chromium rejects a truncated copy (2.2).
- **Drive UI overlays from rVFC `metadata.mediaTime` mapped through a per-frame pts table, not from `floor(currentTime*fps)`.**
  - The pts-table lookup matched the `drawImage` frame in 282/287 to 299/299 callbacks at 1x (2.3).
  - Today's rule shows systematic +1/+2 offsets on VFR, and its match rate is unstable between runs (2.3).
- **Composite video and overlay in one canvas when the overlay must be frame-exact on screen.**
  - A canvas over `<video>` showed the overlay one frame behind in every mismatching capture. How often that happens without the readback instrumentation is not measured (2.3).
  - The single canvas commits both together, but correct pairing still depends on `drawImage` returning the `metadata` frame.
  - At 2x, `drawImage` mismatched the lookup in 72/241 (E35) and 12/281 (E45) callbacks on the canvas-over-video path. All recorded examples were one ahead. The composite path was not run at 2x, so pairing above 1x is unproven (2.3).
- **Seek to the midpoint between frames for all files, not only VFR, and confirm the shown frame from rVFC `mediaTime`.**
  - Exact-pts seeks missed f241 on CFR VP9 and AV1 in both versions, and missed often on VFR (2.3).
  - The midpoint was right in 79/79 or 80/80 in all but the VFR H.264 cases: 76/80 in E35, 79/80 in E45 against 80/80 exact (2.3).
  - The rVFC lookup equalled the shown frame in every paused case (2.3).
  - skellycam-ui seeks to the exact `frame/fps` today (2.1).
- **Upgrade Electron 35.7.5 → 45.x, or never seek to a video's last frame.** E35 gets stuck after a last-frame seek in all 5 files. This also affects G9 scrubbing. Workarounds such as a midpoint seek of the last frame or a reload were not tested (2.3, 3.3).
- **Do not drive overlays from `track.activeCues` or in-band subtitle streams.**
  - `activeCues` lagged one frame during playback, and in-band tracks are not exposed (2.4).
  - WebVTT as a storage format, read as data and looked up by rVFC `mediaTime`, is not ruled out but was not tested. It has no corruption detection (2.2).
- **Keep an alpha video layer only as an export or interchange option, not as the recorded overlay format.**
  - It is 19.5x to 24.4x the `.skov` size for this setting, and larger than the camera JPEG median (2.5).
  - Any Python reader must decode it with the `libvpx-vp9` decoder, because PyAV's default `vp9` decoder drops alpha (2.5, 2.6).
- **Export with burned-in overlays can stay in Python on PyAV 19.0.2.** Two paths work:
  - sidecar → cv2 burn-in → libvpx-vp9 or libx264;
  - the PyAV `overlay` filter graph with a VP9-alpha layer.

  Both were shown as encode/compositing functional, not as pairing under dropped frames (2.6). Codec licensing is for the licensing topic and is not asserted here. libass/ASS burn-in would need the ffmpeg CLI, because the PyAV 19.0.2 wheel lacks `ass` and `subtitles` (2.6).
- **Do label layout at render time with the deterministic placer; do not store layout in the file.** It removed all overlaps in Python and JS (2.7). Store the data and lay it out per display size.
- **Re-check before relying on a browser-side export (canvas → WebCodecs).** `isConfigSupported` reported no hardware VP9/AV1 encode, but that is a capability query made with the iGPU absent (2.6). Re-check now that the UHD 770 is present, and make a real encode test.

## 5. Pending tonight's bench

All timed questions. The original commands are in `results/bench_queue_from_wf_2e122ed0.json` → `overlays.bench_manifest`.

| question | bench id / command | priority |
|---|---|---|
| Per-frame write cost (median/p95 µs) of `.skov`, JSONL, MessagePack, WebVTT, SVG per frame, single SVG and ASS, at 720p and 1080p, for the text, skeleton, charuco and all cases | `overlay_cost` | 1 |
| Cost of cv2 burn-in, of burn-in with JPEG decode + re-encode, and of a plain JPEG round trip, i.e. what burn-in costs when frames would otherwise pass through untouched (G1) | `overlay_cost` | 1 |
| Cost of alpha rasterisation and of the VP9-alpha pipeline (row is ffmpeg-CLI-only: flag it) | `overlay_cost` | 1 |
| Quiet-machine rates in Electron 35.7.5: canvas-over-video vs canvas-composite captures, today's rAF rule, paused-seek convergence, WebVTT cue lag, dual-video alpha sync | `electron_play_quiet_35` | 2 |
| Same in Electron 45.2.3 | `electron_play_quiet_45` | 2 |
| Run-to-run variance of the load-sensitive play metrics: 3 repeat `play` runs per Electron version (verifier request) | see commands below | 2 |
| UI render cost per frame for the full overlay in Electron 35.7.5: canvas with placed labels, naive labels, no labels, SVG DOM replacement | `electron_draw_35` | 2 |
| Same in Electron 45.2.3 | `electron_draw_45` | 3 |

Verifier bench requests (commands as given in `VERIFY_provenance.md` and `VERIFY_method.md`):

```
# overlay_cost in a PyAV 19.0.2 environment (replaces the venv command in the manifest);
# the alpha_vp9_pipeline row still pipes to the ffmpeg CLI and must be flagged CLI-only
uv run --with av==19.0.2 --with numpy --with opencv-python==4.12.0.88 --with msgspec==0.21.1 python research/skellycam_recording/recording_upgrade/scripts/overlays/bench_overlay_cost.py --frames 900 --repeats 3

# repeat play runs, Electron 35.7.5
for i in 1 2 3; do env -u ELECTRON_RUN_AS_NODE skellycam-ui/node_modules/electron/dist/electron.exe research/skellycam_recording/recording_upgrade/scripts/overlays/electron_harness --tests=play --out=research/skellycam_recording/recording_upgrade/results/overlays/bench/electron_play_repeat_35.7.5_run$i.json; done

# repeat play runs, Electron 45.2.3
for i in 1 2 3; do env -u ELECTRON_RUN_AS_NODE C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/shared/electron-latest/node_modules/electron/dist/electron.exe research/skellycam_recording/recording_upgrade/scripts/overlays/electron_harness --tests=play --out=research/skellycam_recording/recording_upgrade/results/overlays/bench/electron_play_repeat_45.2.3_run$i.json; done
```

Notes for preparing the queue:
- In the manifest, `overlay_cost` runs with the skellycam venv (`.venv/Scripts/python.exe`).
  - Its methods use cv2, numpy and msgspec, with no PyAV (**code** `scripts/overlays/bench_overlay_cost.py:43-48,86`).
  - `alpha_vp9_pipeline` pipes to the **ffmpeg CLI** (**code** `bench_overlay_cost.py:17,171-175`), which is not the implementation under test.
  - Use the uv command above. Either switch that row to a PyAV 19 libvpx-vp9 yuva420p encode (shown functional in `pyav19_functional_check.json`) or flag it as CLI-only (**inferred**).
- The quiet Electron benches reuse the same readback-heavy harness, so they will not remove the instrumentation confounder in 2.3.
  - Not queued: a capture-only run without the rAF readback loop. `noRaf` exists (**code** `harness.js:229`) but cannot be set from the command line (**code** `main.js:18-25`). It needs a harness flag first.
- The Electron benches need `<raw>/overlays/media/`, which exists, and a visible, uncovered window.

## 6. Not tested / limits / NOT VERIFIED

Data and formats:
- The overlay data is synthetic: a MediaPipe-33 skeleton and a 100-corner ChArUco board, with no NaNs, and coordinates pre-rounded to 0.01 px. Real RTMPose 133-point output and variable point counts were not sampled. Sizes for real recordings are NOT VERIFIED.
- Untested formats: MessagePack with float32 arrays, compressed JSONL/`.skov`, JSONL with a per-line CRC, and a MessagePack reader with resync.
- Crash tests used cuts and corruptions of finished files. A writer killed mid-record or mid-flush was not tested for any format.
- SVG per frame was not cut-tested. VP9-alpha got only one 50% cut. Fragmented MOV/MP4 was not tested.
- The SVG and ASS files were not rendered in Chromium. Only `<img>` load/error of the single SVG was tested.

Chromium:
- Only one display (scaleFactor 1, about 60 Hz **inferred** from rAF counts) and one GPU path were tested: RTX 3070, iGPU absent, hardware vs software decode per file not recorded.
- Capture counts come from 29-30 capturePage samples per file, in single runs on a loaded machine, under readback instrumentation.
- Chromium alignment was tested only at 1x and 2x. Composite mode ran only at 1x. Many simultaneous videos (the multi-camera G9 case) were not tested.
- Untested: WebCodecs decode with `VideoFrame` timestamps paired to the overlay, which would guarantee pairing at any speed.
- Untested: WebVTT as data looked up by rVFC `mediaTime`, rather than through `activeCues`.
- The PyAV-19-encoded VP9-alpha file was not tested in Chromium.
- Workarounds for the E35 last-frame lock-up were not tested.
- NOT VERIFIED: whether the spec requires `drawImage` inside rVFC to return the `metadata` frame. The spec page does not say so (investigator reading, not re-checked). The dual-video data show `drawImage` can disagree with the compositor (2.3).
- NOT VERIFIED: WebCodecs `isConfigSupported` with the Intel UHD 770 present. No real WebCodecs encode was run.
- NOT VERIFIED: that the wrong barcodes at AV1 frames 14 and 254 are in the bitstream. They are measured in both Electron versions (2.3), but the libdav1d cross-check in NOTES §11 has no result file.

FreeMoCap and code citations:
- FreeMoCap schema drift: `charuco-types.ts:20` requires `has_pose: z.boolean()`, which Python does not send. The runtime effect is NOT VERIFIED.
- The skellytracker @6f78af48 citations come from the investigator and were not re-checked.

Labels and export:
- Leader-line crossings in the label placer are not handled. Placement order is by id, not by importance.
- P3 libass alignment was measured only with the ffmpeg CLI. It cannot be reproduced through PyAV 19.0.2, which has no `ass` filter.
- The PyAV 19.0.2 re-check used 60 frames, not 300. Its P1 and P2 pair frames by index, not by timestamps.

## 7. How to reproduce

Run from the repo root (`C:/Users/Dom/GitHub/freemocap/skellycam`) in Git Bash. In PowerShell, use `Remove-Item Env:ELECTRON_RUN_AS_NODE` instead of `env -u`.

```
# functional, no PyAV (pure Python / cv2); results/overlays/formats_functional.{json,md}, label_layout.{json,md}
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/formats_functional.py --frames 300
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/label_layout.py --frames 60

# verifier checks, no PyAV; results/overlays/verify_method_{crash_modes,precision}.json
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/verify_method_crash_modes.py
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/verify_method_precision.py

# test media and export (PyAV 18 + ffmpeg CLI; background)
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/make_test_media.py --frames 300
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/export_burnin.py --frames 300
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/alpha_truncation.py

# PyAV 19.0.2 functional re-check (caps, P1 export, VP9-alpha encode/decode/truncation, overlay filter graph)
uv run --script research/skellycam_recording/recording_upgrade/scripts/overlays/pyav19_functional_check.py --frames 60
#   -> results/overlays/pyav19_functional_check.json ; media -> <raw>/overlays/pyav19_check/

# Chromium functional harness
env -u ELECTRON_RUN_AS_NODE skellycam-ui/node_modules/electron/dist/electron.exe research/skellycam_recording/recording_upgrade/scripts/overlays/electron_harness --out=research/skellycam_recording/recording_upgrade/results/overlays/electron_35.7.5.json --tests=caps,play,seek,lastframe,vtt,inband,alpha,trunc,webcodecs,layout
env -u ELECTRON_RUN_AS_NODE C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/shared/electron-latest/node_modules/electron/dist/electron.exe research/skellycam_recording/recording_upgrade/scripts/overlays/electron_harness --out=research/skellycam_recording/recording_upgrade/results/overlays/electron_45.2.3.json --tests=caps,play,seek,lastframe,vtt,inband,alpha,trunc,webcodecs,layout
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/summarize_electron.py

# summary provenance check (writes next to the copies, not into results/)
S=<scratchpad>/overlays; cp research/skellycam_recording/recording_upgrade/results/overlays/electron_{35.7.5,45.2.3}.json $S/
python research/skellycam_recording/recording_upgrade/scripts/overlays/summarize_electron.py $S/electron_35.7.5.json $S/electron_45.2.3.json
diff <(tail -n +2 $S/electron_35.7.5_summary.md) <(tail -n +2 research/skellycam_recording/recording_upgrade/results/overlays/electron_summary.md)

# timed (tonight only): see section 5 and results/bench_queue_from_wf_2e122ed0.json -> overlays.bench_manifest
```

## 8. Verification

Two verifier passes challenged the draft:
- `results/overlays/VERIFY_provenance.md`: does each piece of evidence exist and say exactly what the claim says?
- `results/overlays/VERIFY_method.md`: confounders and over-reaching conclusions.

Before applying any refutation, I re-checked it against `electron_summary.md`, the raw `electron_*.json`, `harness.js`, `main.js`, the PyAV 19 check script and the FreeMoCap and skellycam-ui source. No new timing was produced.

**Refuted and corrected** (all confirmed against the evidence):
- "rAF rule: mostly offset -1, plus +1/+2 on VFR" was wrong. On VFR, positive offsets outnumber -1 in all 4 runs (302/264, 302/147, 304/155, 304/200, `rafUiOffsets`). Now: CFR -1 (one +1), VFR mostly +1/+2.
- Table 3.2, "VFR worse": true only in E35. In E45, VFR matched more often (145/604, 100/604) than CFR (35/600, 58/599, 13/596). Now: wrong on both, VFR adds +1/+2, load-sensitive.
- Table 3.3, E45 last-frame "correct, 5/5": E45 VFR VP9 `75->74` and VFR H.264 `duration->298`. Now: not stuck in 5/5, CFR exact, one off-by-one per VFR file.
- The rAF rule "matched the presented frame": its reference is `drawImage` inside rAF (**code** `harness.js:218-225`), not the screen. Now: "matched the frame `drawImage` returned"; the CFR -1 magnitude says nothing about what the user sees.
- The rAF rule range presented as a rate: the same file and version varied 289 vs 522 (E35) and 58 vs 169 (E45) between two runs. Now marked unstable between runs, and repeat runs are queued.

**Relabelled or narrowed:**
- Sidecar crash tolerance now includes zero-hole and one-byte-corruption results. Only `.skov` detects corruption, and MessagePack cannot resync. "The only kind that survived" became "all four data sidecars; others not tested the same way".
- The JSONL/`.skov` ratio changed from 1.73x to 1.74x and now carries the 4.2x float32 case and the precision assumption.
- MessagePack "float64" is inferred and limited to the point-heavy cases. "Text" is a counter-example.
- Canvas-over-`<video>` capture counts are now named capturePage captures with an instrumentation confounder: the direction is supported, the frequency is not. The composite 29/29-30/30 is described as a same-canvas commit.
- The 2x "next frame in 72/241" is now "72 mismatched; all 20 recorded examples one ahead". The single-canvas-at-2x statement is inferred, because composite at 2x was not run.
- The midpoint-seek advice now covers all files (CFR WebM exact seeks missed f241), with the VFR H.264 exceptions cited.
- The WebVTT advice is narrowed to the `activeCues` mechanism. WebVTT as a data format is not ruled out.
- VP9-alpha in Chromium is labelled as the CLI-encoded file. Alpha size is 19.5x to 24.4x `.skov` for one setting.
- PyAV 19 P1/P2 are described as encode/compositing functional, paired by index (**code** `pyav19_functional_check.py:122,133,249`). The P2 base input is labelled PyAV 18.
- P2b "opaque" is inferred from the barcodes. ASS packets: only the first 6 are recorded.
- The MOV truncation result is scoped to non-fragmented MOV. WebCodecs is a capability query only. The undetected-list numbers are code arithmetic.
- Code citations corrected and now checked:
  - `charuco-types.ts:20`
  - `video_node.py:211-219` (source suffix)
  - `binary_keypoints_protocol.py:15,58-64` (float32 or float64)
  - `SyncedVideoPlayer.tsx:281-308,658-700` (HTML labels over the video)
  - msgspec import lines in `overlay_model.py`
- Provenance fixes:
  - The AV1 bad frames are now measured (`decodeFailAt`).
  - The hardware header now has evidence: CPU from `cpu_topology.txt:3`; GPU from `env.gpuInfo`, with the 610.88 mapping inferred.
  - "libvpx-vp9 (royalty-free)" was removed because it had no source here.

**Still NOT VERIFIED or untested** (section 6):
- real-data sizes;
- the spec status of `drawImage` in rVFC;
- WebCodecs with the iGPU present, and a real encode;
- that the AV1 bad frames are in the bitstream;
- the runtime effect of the FreeMoCap `has_pose` drift;
- the skellytracker citations;
- killed-writer crashes;
- composite mode above 1x;
- multi-video sync;
- the PyAV 19 alpha file in Chromium;
- all timing (section 5).

None of the corrections reverses a recommendation. They change the `.skov` vs JSONL evidence in favour of a CRC-framed format, and they widen the midpoint-seek advice to all files.
