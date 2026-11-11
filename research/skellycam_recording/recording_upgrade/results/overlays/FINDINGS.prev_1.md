# Overlays as a separate layer (G3): findings

Study 2026-11-09, machine Gerald (Windows 11, i7-14700K, RTX 3070, driver 610.88). Topic folders: `research/skellycam_recording/recording_upgrade/{scripts,results}/overlays/` (paths below are relative to `research/skellycam_recording/recording_upgrade/` unless they start with `skellycam/`, `skellycam-ui/` or `freemocap`). Media: `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/overlays/` (`<raw>/overlays`).

Labels: **measured** = result file (path given); **source** = primary source (URL, quote, accessed 2026-11-09); **code** = file:line; **inferred** = reasoning, kept short. "PyAV 18 - background" = made with the skellycam venv (PyAV 18.0.0), not the implementation under test. "ffmpeg CLI - background" = made with the gyan ffmpeg 9.0.2 CLI, which may only inspect files under the study rules.

No timing, throughput or CPU numbers appear here. `results/overlays/bench/` is empty and there is no `BENCH.md` for this topic. All timed questions are in section 5.

Provenance checks made for this FINDINGS:
- `electron_summary.md` was regenerated from the raw `electron_35.7.5.json` and `electron_45.2.3.json` with `summarize_electron.py` in the scratchpad. The output is byte-identical to the committed summary apart from the title line. So the summary tables match the raw JSON.
- The PyAV-dependent functional results were re-run on PyAV 19.0.2 at 60 frames: `results/overlays/pyav19_functional_check.json`, script `scripts/overlays/pyav19_functional_check.py`.

## 1. Questions answered

1. What overlays exist today, where are they drawn, and do they overlap?
2. Which storage form for overlays, separate from the camera frames, is smallest and survives a crash (data sidecar vs SVG/ASS vector files vs an alpha video layer)?
3. Can Chromium (Electron 35.7.5 and 45.2.3) draw a separate overlay frame-accurately over `<video>`, and with which method?
4. Can overlap between labels be removed deterministically?
5. Can overlays still be burned in for export or sharing, and does that work through PyAV 19.0.2?

## 2. Findings

### 2.1 Today's overlays (inventory)

- skellycam burns `camera.id{id}.idx{index}.fr{N}` into every recorded frame with `cv2.putText` at (10,40), scale 0.8, black outline thickness 8. No clean copy of the frame is kept (**code** `skellycam/core/camera/opencv/opencv_helpers/opencv_get_frame.py:79-90`, spot-checked).
- The burned stamp spans about x 5-340 and y 15-50 px, the same pixel size at 720p and 1080p (**measured**, background verified: `research/skellycam_recording/results/real_recording_20261109/RESULTS.md:145`).
- skellycam-ui playback draws nothing on the video. Its frame label is HTML computed as `Math.floor(leader.currentTime * fps)` in a rAF loop (**code** `skellycam-ui/src/components/playback/SyncedVideoPlayer.tsx:377-403`, spot-checked).
- skellycam-ui seeks with `currentTime = frame / fps` (**code** `SyncedVideoPlayer.tsx:334-335, 506-507`, spot-checked).
- FreeMoCap's live ChArUco renderer draws an info panel with `fillRect(5, 5, 500, 85)` (**code** freemocap `freemocap-ui/src/services/server/server-helpers/image-overlay/charuco-overlay-renderer.ts:165`, spot-checked). This covers skellycam's stamp area (x 5-340, y 15-50) (**inferred** from the two coordinates).
- FreeMoCap's live worker keeps only the latest overlay observation per type and drops it after `OVERLAY_STALE_MS = 500`. Overlays are not matched to a frame number (**code** freemocap `offscreen-renderer.worker.ts:17,26-29,62-63,83`, spot-checked).
- FreeMoCap post-hoc burns skellytracker annotations into `annotated_videos/<stem>_annotated.mp4` (**code** freemocap `freemocap/core/pipeline/posthoc/video_node.py:121-157,316-358,391-411`; investigator citation, not re-checked here).
- FreeMoCap already sends overlays to the UI as per-frame float32 point blocks keyed by frame number (**code** freemocap `freemocap/api/websocket/binary_keypoints_protocol.py:1-56`; investigator citation, not re-checked here).
- skellytracker's "Undetected Corners" list fits 35 lines at 720p and 53 lines at 1080p before leaving the image (**measured** arithmetic, `results/overlays/label_layout.json`, `undetected_list_lines_that_fit_in_frame_height`).

### 2.2 Storage formats: size, round trip, truncation

Synthetic FreeMoCap-shaped data, 300 frames, 30 fps extrapolation. The script is pure Python + numpy + msgspec 0.21.1 with no PyAV, so the PyAV version rule does not apply (**code** `scripts/overlays/formats_functional.py:15-25`).

- At 720p for the full "all" overlay, the custom CRC-framed binary `.skov` is 3287.6 B/frame = 355.1 MB/h. JSONL is 5704.3 B/frame = 616.1 MB/h. Length-prefixed MessagePack is 6895.6 B/frame = 744.7 MB/h. WebVTT (one JSON cue per frame) is 5735.6 B/frame = 619.4 MB/h (**measured** `results/overlays/formats_functional.json`).
- JSONL is 1.73x the size of `.skov` for "all" at 720p: 616.1 / 355.1 (**measured**, arithmetic on the same file).
- Render-level vector forms at 720p for "all": SVG per frame is 35283.3 B/frame = 3810.6 MB/h. One SVG per recording is 35161.9 B/frame = 3797.5 MB/h. ASS is 17056.0 B/frame = 1842.0 MB/h (**measured** `formats_functional.json`).
- SVG per frame is 10.7x `.skov` and 6.2x JSONL for "all" at 720p (**measured**, arithmetic).
- JSONL, MessagePack, `.skov` and WebVTT recovered every complete record, with no corrupt record returned, at 28/28 truncation cuts in every case and resolution (**measured** `formats_functional.json`, `trunc_recovered_all_complete`, `trunc_errors: []`).
- At one cut per text format (JSONL, WebVTT), a cut just before a record's newline also returned that record intact (**measured**, `trunc_cuts_with_extra_record_before_newline: 1`).
- The single SVG per recording fails a strict XML parse at 25/25 cuts. A lenient regex reader recovers 10-288 or 11-288 groups depending on the cut (**measured** `formats_functional.json`, `trunc_strict_parse_failures`, `trunc_lenient_groups_recovered_min_max`).
- SVG per frame: 300/300 files parse independently (**measured**).
- 1080p sizes differ from 720p by at most 5.4% (ASS skeleton: 2770.2 vs 2628.0 B/frame). `.skov` and MessagePack sizes are identical across resolutions (**measured** `formats_functional.md`, arithmetic).
- In Chromium (Electron 35.7.5 and 45.2.3), the full single SVG loads as `<img>`. Cut at 50%, it fires `img` `error` and `DOMParser` reports a parser error (**measured** `electron_*.json` → `trunc`).
- A WebVTT file cut at 50% still loads 150/300 cues in Chromium, but the last cue's JSON payload fails to parse (`lastCuePayloadParses: False`) (**measured**, same).
- MessagePack is larger than JSON here because msgspec writes Python floats as float64 (**inferred**; not tested separately).

### 2.3 Chromium alignment: overlay vs presented frame

Electron 35.7.5 (Chromium 134.0.6998.205) and 45.2.3 (Chromium 156.0.8078.80), scaleFactor 1 (**measured** `electron_*.json` → `env`). Chromium saw only the RTX 3070 (vendorId 4318) and the Microsoft Basic Render Driver; the Intel iGPU was absent during these runs (**measured**, `env.gpuInfo.gpuDevice`).

The test videos were encoded with PyAV 18 (libx264, libvpx-vp9, libsvtav1) and the ffmpeg CLI (**measured, PyAV 18 - background** `results/overlays/make_test_media.json`). These tests exercise Chromium, not the encoder. The machine was shared with other agents during these runs, so all play-rate and screen-capture counts are load-sensitive: they show patterns, not stable rates.

- An overlay looked up from `requestVideoFrameCallback` `metadata.mediaTime` (nearest entry in a per-frame pts table) named the decoded frame in:
  - 299/299 (CFR H.264), 299/299 (CFR VP9), 297/297 (CFR AV1), 299/299 (VFR VP9) and 291/295 (VFR H.264) callbacks at 1x in E35;
  - 299/299, 299/299, 296/296, 282/287 and 290/292 in E45

  (**measured** `electron_summary.md`, regenerated identical from raw).
- `round(mediaTime*30)` is right only for CFR: 299/299 CFR VP9 but 149/299 VFR VP9 (E35), 147/287 (E45) (**measured**, same).
- Today's UI rule, `floor(currentTime*30)` in rAF, matched the presented frame in (**measured**, same; mostly offset -1, plus +1/+2 on VFR):
  - E35: 111/597, 289/598, 464/595, 36/602 and 153/602;
  - E45: 35/600, 58/599, 13/596, 145/604 and 100/604.
- In screen captures, an overlay canvas layered over `<video>` matched the video on 3/30 to 19/30 captures at 1x. Every recorded mismatch had the form `[video N, overlay N-1]` (**measured**, `capture mismatches` column).
- Drawing the video into the same canvas as the overlay (`drawImage(video)` in rVFC) matched on screen in 29/29 (CFR VP9, E35), 30/30 (VFR H.264, E35), 30/30 (CFR VP9, E45) and 29/29 (VFR H.264, E45) captures (**measured**, `@canvasComposite` rows).
- At 2x (CFR VP9), the rVFC lookup matched the frame read by `drawImage` in only 169/241 (E35) and 269/281 (E45) callbacks. Screen captures over `<video>` matched 0/24 and 0/28 (**measured**, `@2x` rows). The NOTES wording "drawImage returned the next frame in 72/241" is 241 - 169 = 72 (arithmetic).
- The rVFC spec allows the lag pattern: "a callback can occasionally be fired one v-sync late, relative to when the new video frame was presented" and "drawing operations might occasionally appear on screen one v-sync after the video frame does" (**source** https://wicg.github.io/video-rvfc/ Introduction, accessed 2026-11-09). Here the lag was the common case at 1x, not occasional (**measured**, above).
- The spec defines `mediaTime` as "The media presentation timestamp (PTS) in seconds of the frame presented" (**source** https://wicg.github.io/video-rvfc/ §2.2, accessed 2026-11-09).
- Paused seeks to a frame's exact pts showed the requested frame in (**measured** `electron_summary.md`, paused-seek tables):
  - VFR VP9: 43/80 (E35), 56/80 (E45);
  - VFR H.264: 42/80 (E35), 80/80 (E45);
  - CFR H.264: 80/80 in both.
- Seeking to the midpoint between pts f and f+1 gave (**measured**, same):
  - VFR VP9: 80/80 in both;
  - VFR H.264: 76/80 (E35), 79/80 (E45).
- In every paused-seek case the frame shown equalled the rVFC `mediaTime` lookup (80/80 or 79/79). Screen composites all matched by +100 ms. Immediately after the seek, as few as 64/79 matched (CFR H.264 exact, E45) (**measured**, same).
- Electron 35.7.5 bug: after a seek to the last frame (299), every later seek (150, 0, 299, duration, 75) still showed frame 299, with no rVFC callback and `ended` true, in all 5 files. Electron 45.2.3 showed 150, 0, 299, 299/298 and 75/74 (**measured** `electron_summary.md`, last-frame tables).
- Two `<video>` elements played together (base + VP9-alpha layer) matched in every screen capture: 25/25 (E35) and 27/27 (E45). But reading both with `drawImage` inside the base's callback found the layer one frame ahead in 136/250 (E35) and 195/271 (E45) callbacks. Paused seeks of both: 30/30 on the requested frame (**measured** `electron_summary.md`, VP9-alpha section).

### 2.4 WebVTT and subtitle tracks in Chromium

- A `<track kind=metadata>` CFR cue matched the presented frame during playback in 148/299 (E35) and 8/299 (E45) callbacks. The rest were offset -1 (**measured** `electron_summary.md`, WebVTT table).
- With cues shifted half a frame earlier: 207/299 (E35), 18/298 (E45). VFR with cue times equal to container pts: 95/285 (E35), 32/286 (E45) (**measured**, same).
- Paused seeks: 40/40 (CFR) in both versions; VFR 30/40 (E35) and 32/40 (E45) (**measured**, same).
- WebVTT muxed into WebM and ASS muxed into MKV both load, but expose `textTracks.length` 0 in both versions (**measured**, in-band table).
- `canPlayType('video/x-matroska')` is `''` in E35 and `'maybe'` in E45 (**measured**, MIME tables).
- WebVTT timestamps have millisecond resolution: "Three ASCII digits, representing the thousandths of a second seconds-frac as a base ten integer" (**source** https://www.w3.org/TR/webvtt1/ §4.1, accessed 2026-11-09).
- Metadata cues: "WebVTT metadata text cues are only useful for scripted applications" (**source** same URL, §4.2.1; NOTES cited §1.7, corrected here) and "Metadata can be any string and is often provided as a JSON construct" (**source** same URL, §1.7).
- ASS timing is centiseconds. FFmpeg's ASS demuxer computes `*start = (hh1*3600LL + mm1*60LL + ss1) * 100LL + ms1;` and calls `avpriv_set_pts_info(st, 64, 1, 100);` (**source** https://raw.githubusercontent.com/FFmpeg/FFmpeg/n8.0/libavformat/assdec.c lines 72 and 118, fetched 2026-11-09). This is the FFmpeg n8.0 tag; whether the PyAV 19.0.2 build matches is NOT VERIFIED, and it is moot because its wheel has no `ass` filter (2.6).
- ASS muxed in MKV produced 30,898 packets for 300 frames, each 0.03 s long (**measured, ffmpeg CLI - background** `make_test_media.json` → `ass_mkv_packets`).

### 2.5 Alpha video overlay layer

- VP9-alpha WebM (libvpx-vp9, yuva420p, crf 32, realtime, cpu-used 8, g 30, 300 frames, "all" overlay at 720p): 80,251 B/frame = 24,075,364 bytes (**measured, ffmpeg CLI - background** `make_test_media.json`).
- PNG-in-MOV was 155,859 B/frame and QTRLE-in-MOV 290,996 B/frame (**measured, ffmpeg CLI - background**, same).
- The camera's own JPEG for this set has a median of 56,759 B (min 51,085, max 65,760) (**measured** `C:/Users/Dom/Documents/skellycam-raw/.../corpus/index.json` → `c930e_720p_flash.bytes_median`).
- PyAV 19.0.2 re-check: the same overlay encoded through PyAV 19 (libvpx-vp9, `pix_fmt yuva420p`, same options, 60 frames) gave 3,840,349 bytes = 64,006 B/frame (**measured** `results/overlays/pyav19_functional_check.json` → `alpha`). Frame counts differ (60 vs 300), so this is not a like-for-like size comparison.
- The VP9-alpha WebM loads in Chromium 134 and 156. Frame 0 has alpha==0 on 0.8746 of its pixels (**measured** `electron_summary.md`, VP9-alpha section). PNG-MOV and QTRLE-MOV fail with `DEMUXER_ERROR_NO_SUPPORTED_STREAMS` in both (**measured**, load table).
- After a 50% cut, the VP9-alpha file still decoded 160 frames, all with transparency. PNG-MOV and QTRLE-MOV decoded 0 frames (`Invalid data found when processing input`) (**measured, ffmpeg CLI - background** `results/overlays/alpha_truncation.json`).
- **PyAV 19.0.2 confirms the alpha truncation result:** a 50% cut of the PyAV-19-encoded file, decoded with the `libvpx-vp9` decoder through PyAV, gave 30 frames, all with transparency, and no errors (**measured** `pyav19_functional_check.json` → `alpha.trunc50`).
- **PyAV 19.0.2 confirms which decoder keeps alpha:** the stream reports `pix_fmt yuv420p` with metadata `alpha_mode: 1`. PyAV's default decoder (FFmpeg native `vp9`) returns `yuv420p` frames, so alpha is dropped. `av.CodecContext.create("libvpx-vp9", "r")` returns `yuva420p` on 60/60 frames. Its maximum per-frame mean absolute alpha difference from the source matte is 0.4572 of 255, and the overlay barcode is read correctly in 60/60 frames (**measured** `pyav19_functional_check.json` → `alpha`).
- The earlier CLI decode gave a frame-0 alpha mean absolute difference of 0.114 (**measured, ffmpeg CLI - background** `make_test_media.json` → `vp9alpha_decode_check`).

### 2.6 Export with overlays burned in

- P1, sidecar → cv2 burn-in → encode, 300 frames: libvpx-vp9 WebM 300/300 aligned (15,215,723 B) and libx264 MP4 300/300 aligned (11,827,653 B) (**measured, PyAV 18 - background** `results/overlays/export_burnin.json`). "Aligned" means the source-frame barcode equals the overlay-frame barcode in each decoded output frame.
- **PyAV 19.0.2 confirms P1** at 60 frames: the `.skov` sidecar read back 60 frames with 0 bad. libvpx-vp9 WebM gave 60/60 aligned and libx264 MP4 60/60 aligned, with 0 decode failures (**measured** `pyav19_functional_check.json` → `p1`).
- P2, ffmpeg `overlay` filter with the alpha layer decoded by `-c:v libvpx-vp9`: 300/300 aligned. With the default vp9 decoder (P2b): 1/300, because the layer came out opaque (**measured, ffmpeg CLI - background** `export_burnin.json`).
- **PyAV 19.0.2 reproduces P2 inside Python:**
  - The `overlay` filter graph (`x=0:y=0:eof_action=pass:format=yuv420`) over `base_cfr_vp9.webm` with the layer decoded by `libvpx-vp9` (`yuva420p`) gave 60/60 aligned.
  - With the layer from the default decoder (`yuv420p`), it gave 1/60 (base barcode read as 0).
  - **Source:** **measured** `pyav19_functional_check.json` → `p2`.
- P3, libass burn-in with per-frame events at centisecond times: 200/300 aligned, with every third frame showing the previous event. P3b, events shifted half a frame earlier: 300/300 (**measured, ffmpeg CLI - background** `export_burnin.json`).
- **The PyAV 19.0.2 wheel has no `ass`, `subtitles` or `drawtext` filters.** It does have `overlay`, `alphamerge`, `alphaextract` and `drawbox`. It has the libvpx-vp9 encoder and decoder, the libx264 and libsvtav1 encoders, the libdav1d decoder, the png/qtrle/webvtt/ass codecs, and the webm/matroska/mp4/mov/webvtt/ass muxers (**measured** `pyav19_functional_check.json` → `caps`). So P3 (libass) cannot run through PyAV 19.0.2.
- WebCodecs `isConfigSupported` at 1920x1080, identical in E35 and E45 (**measured** `electron_summary.md`, WebCodecs table):
  - hardware encode: H.264 and HEVC true; VP8, VP9 and AV1 false;
  - software encode: VP8, VP9, AV1 and H.264 true; HEVC false;
  - hardware decode: VP9, AV1, H.264 and HEVC true.

  This was measured with the Intel iGPU absent (2.3).

### 2.7 Deterministic label placement

- Greedy placement (8 directions x 3 rings, then side lanes with leader lines, then hide and count), implemented in Python (`scripts/overlays/label_layout.py`) and JS (`scripts/overlays/electron_harness/layout.js`). Results for 60 frames and 5,691 labels (**measured** `results/overlays/label_layout.json`):

  | case | skellytracker `Corner#id` (label-label / label-marker) | freemocap-ui id | placed |
  |---|---|---|---|
  | 720p, board 55% of height | 12,272 / 13,397 | 0 / 332 | 0 / 0 |
  | 1080p, board 55% | 9,706 / 10,657 | 116 / 1,450 | 0 / 0 |
  | 720p, board 20% (dense) | 68,733 / 57,092 | 7,223 / 21,957 | 0 / 0 |

- In the dense case, 1,474 labels went to side lanes and 0 were hidden. Two runs were identical (`deterministic: true`), and 0 HUD panel pairs overlapped (**measured**, same).
- In the browser (12 px Arial, both Electron versions): naive +8/-8 placement gave 11 label-label and 322 label-marker overlaps; `placeLabels` gave 0 and 0, deterministic (**measured** `electron_summary.md`, layout table).
- Leader-line crossings are not checked. They are visible in `<raw>/overlays/layout/C_placed_720p_board20.png` (**measured**, image; investigator observation).

## 3. Comparison tables

### 3.1 Overlay storage options (720p, full "all" overlay)

| option | B/frame | MB/h @30 fps | complete records after truncation | plays/renders in Chromium | PyAV 19.0.2 path | evidence |
|---|---|---|---|---|---|---|
| `.skov` binary, CRC per record | 3,287.6 | 355.1 | 28/28 cuts | n/a (UI renders data) | pure Python, no PyAV | measured `formats_functional.json` |
| JSONL | 5,704.3 | 616.1 | 28/28 cuts | n/a | pure Python | same |
| MessagePack (float64) | 6,895.6 | 744.7 | 28/28 cuts | n/a | pure Python + msgspec | same |
| WebVTT metadata cues | 5,735.6 | 619.4 | 28/28 (Python); Chromium loads 150/300 cues from a 50% cut, last cue torn | as `<track>` only; cue lags 1 frame in play | pure Python | same + `electron_*.json` |
| ASS | 17,056.0 | 1,842.0 | not tested | no text track exposed | no libass filter in wheel | same + `pyav19_functional_check.json` |
| SVG per frame | 35,283.3 | 3,810.6 | each file independent | not rendered in test | pure Python | `formats_functional.json` |
| one SVG per recording | 35,161.9 | 3,797.5 | strict parse fails 25/25 | 50% cut fires `img` error | pure Python | same + `electron_*.json` |
| VP9-alpha WebM | 80,251 (CLI, 300 fr); 64,006 (PyAV 19, 60 fr) | 8,667 (CLI) | 160 frames from a 50% cut (CLI); 30/30 transparent from a 50% cut (PyAV 19) | yes, with alpha | encode yes; decode only with `libvpx-vp9` | `make_test_media.json`, `alpha_truncation.json`, `pyav19_functional_check.json` |
| PNG-in-MOV / QTRLE-in-MOV | 155,859 / 290,996 | 16,833 / 31,428 | 0 frames from a 50% cut | no (`DEMUXER_ERROR_NO_SUPPORTED_STREAMS`) | not tested | `make_test_media.json`, `alpha_truncation.json` |

### 3.2 Chromium overlay-sync methods

| method | 1x play, frame named correctly | on-screen captures overlay == video | VFR | evidence |
|---|---|---|---|---|
| today's `floor(currentTime*fps)` in rAF | 13/596 to 464/595 | not separately captured | worse (+1/+2 offsets) | `electron_summary.md` |
| rVFC `mediaTime` → pts table, canvas over `<video>` | 282/287 to 299/299 | 3/30 to 19/30 (overlay 1 frame behind) | works with the pts table | same |
| rVFC + video drawn into the overlay canvas | 287/287 to 299/299 | 29/29 to 30/30 | works with the pts table | same |
| WebVTT metadata `activeCue` | 8/299 to 148/299 | n/a | 32/286 to 95/285 | same |
| second `<video>` with a VP9-alpha layer | n/a | 25/25, 27/27 | not tested | same |

### 3.3 Electron 35.7.5 vs 45.2.3 (overlay-relevant differences only)

| item | 35.7.5 | 45.2.3 | evidence |
|---|---|---|---|
| seek after reaching the last frame | stuck on the last frame, 5/5 files | correct, 5/5 files | `electron_summary.md` |
| VFR H.264 exact-pts paused seek | 42/80 | 80/80 | same |
| `canPlayType('video/x-matroska')` | `''` | `'maybe'` | same |
| 2x CFR VP9 rVFC lookup == drawImage frame | 169/241 | 269/281 | same |
| in-band WebVTT/ASS text tracks | 0 | 0 | same |

## 4. Implications for the plan

- **Store overlays as an append-only data sidecar keyed by frame number and timestamp, not as burned-in pixels, SVG or ASS.** It is the smallest option and the only kind that recovered all complete records at every cut (2.2, 3.1). It also removes skellycam's burned stamp, which today cannot be removed after recording (2.1). (**inferred** from those findings)
- **Choice between `.skov` binary and JSONL:** `.skov` is 1.73x smaller for the full overlay (2.2). Both recovered 28/28. JSONL is readable without a custom reader. The decision is open (section 6), and the per-frame write cost is pending tonight's bench (`overlay_cost`, section 5). (**inferred**)
- **Do not use a single SVG per recording.** It fails strict parsing at every cut, and Chromium rejects a truncated copy (2.2). (**inferred**)
- **Drive UI overlays from rVFC `metadata.mediaTime` mapped through a per-frame pts table, not from `floor(currentTime*fps)`.** The pts-table lookup named the right frame in 282/287 to 299/299 callbacks at 1x, against 13/596 to 464/595 for today's rule (2.3). (**inferred**)
- **Composite video and overlay in one canvas when the overlay must be frame-exact on screen.** A canvas over `<video>` usually showed the overlay one frame behind (2.3). At 2x even the single-canvas path paired a frame one ahead in up to 72/241 callbacks (E35), so above 1x pairing is not guaranteed (2.3). (**inferred**)
- **Seek to the midpoint between frames for VFR files**, and confirm the shown frame from rVFC `mediaTime` (2.3). (**inferred**)
- **Upgrade Electron 35.7.5 → 45.x, or never seek to a video's last frame.** E35 gets stuck after a last-frame seek in all 5 files (2.3, 3.3). This also affects G9 scrubbing. (**inferred**)
- **Do not use WebVTT or in-band subtitle streams for frame-accurate sync.** Cues lag by one frame during playback, and in-band tracks are not exposed (2.4). WebVTT stays usable for paused CFR display only. (**inferred**)
- **Keep an alpha video layer only as an export or interchange option, not as the recorded overlay format.** It is about 24x the `.skov` size and larger than the camera JPEG (2.5). (**inferred**) If used, any Python reader must decode it with the `libvpx-vp9` decoder, because PyAV's default `vp9` decoder drops alpha (2.5, 2.6).
- **Export with burned-in overlays can stay in Python on PyAV 19.0.2:** sidecar → cv2 burn-in → libvpx-vp9 (royalty-free) or libx264, or the PyAV `overlay` filter graph with a VP9-alpha layer (2.6). libass/ASS burn-in would need the ffmpeg CLI, because the PyAV 19.0.2 wheel lacks `ass`/`subtitles` (2.6). (**inferred**)
- **Do label layout at render time with the deterministic placer**, not stored in the file. It removed all overlaps in Python and JS (2.7). Store the data; lay it out per display size. (**inferred**)
- **A browser-side royalty-free export (canvas → WebCodecs) would use software VP9/AV1 encode** on this machine, as measured with the iGPU absent (2.6). Re-check `isConfigSupported` now that the UHD 770 is present before relying on this. (**inferred**)

## 5. Pending tonight's bench

All timed questions. Commands are in `results/bench_queue_from_wf_2e122ed0.json` → `overlays.bench_manifest`.

| question | bench_manifest id | priority |
|---|---|---|
| Per-frame write cost (median/p95 µs) of `.skov`, JSONL, MessagePack, WebVTT, SVG per frame, single SVG and ASS, at 720p and 1080p, for the text, skeleton, charuco and all cases | `overlay_cost` | 1 |
| Cost of cv2 burn-in, burn-in with JPEG decode + re-encode, and a plain JPEG round trip, i.e. what burn-in costs when frames would otherwise pass through untouched (G1) | `overlay_cost` | 1 |
| Cost of alpha rasterisation and of the VP9-alpha pipeline | `overlay_cost` | 1 |
| Quiet-machine rates for canvas-over-video vs canvas-composite captures, today's rAF rule, paused-seek convergence, WebVTT cue lag and dual-video alpha sync, Electron 35.7.5 | `electron_play_quiet_35` | 2 |
| Same in Electron 45.2.3 | `electron_play_quiet_45` | 2 |
| UI render cost per frame for the full overlay: canvas with placed labels, naive labels, no labels, SVG DOM replacement, Electron 35.7.5 | `electron_draw_35` | 2 |
| Same in Electron 45.2.3 | `electron_draw_45` | 3 |

Notes for preparing the queue:
- `overlay_cost` runs with the skellycam venv (`.venv/Scripts/python.exe`) in the manifest. Its methods use cv2/numpy/msgspec and no PyAV (**code** `scripts/overlays/bench_overlay_cost.py:43-48,86`). But `alpha_vp9_pipeline` pipes to the **ffmpeg CLI** (**code** `bench_overlay_cost.py:17,171-175`), which is not the implementation under test.
- To meet the PyAV 19.0.2-only rule, run `overlay_cost` with `uv run --script` (deps: av==19.0.2, numpy, opencv-python==4.12.0.88, msgspec==0.21.1). Either switch `alpha_vp9_pipeline` to a PyAV 19 libvpx-vp9 yuva420p encode, shown functional in `pyav19_functional_check.json`, or flag that row as CLI-only. (**inferred**)
- The Electron benches need `<raw>/overlays/media/`, which exists, and a visible, uncovered window.

## 6. Not tested / limits / NOT VERIFIED

- Overlay data is synthetic: MediaPipe-33 skeleton and a 100-corner ChArUco board, no NaNs. Real RTMPose 133-point output and variable point counts were not sampled. Sizes for real recordings are NOT VERIFIED.
- Only one display (scaleFactor 1) and one GPU path (RTX 3070; iGPU absent) were tested in Chromium. The refresh rate was not measured. Capture counts come from 29-30 samples per file on a loaded machine.
- Chromium alignment at speeds other than 1x and 2x, and with many simultaneous videos (the multi-camera G9 case), was not tested.
- WebCodecs decode with `VideoFrame` timestamps paired to the overlay (guaranteed pairing at any speed) was not tested.
- The SVG and ASS files were not rendered in Chromium; only `<img>` load/error of the single SVG was tested.
- MessagePack with float32 arrays (smaller) was not tested.
- Whether rVFC's `drawImage` is specified to return the `metadata` frame is NOT VERIFIED. The spec page does not say (investigator reading; not re-checked here).
- FreeMoCap schema drift (`charuco-types.ts:21` requires `metadata.has_pose`, which Python does not send): runtime effect NOT VERIFIED.
- The FreeMoCap post-hoc and wire-protocol citations (`video_node.py`, `binary_keypoints_protocol.py`, skellytracker @6f78af48 files) are from the investigator and were not re-checked here.
- WebCodecs `isConfigSupported` was measured with the Intel UHD 770 absent. Results with the iGPU present are NOT VERIFIED.
- Leader-line crossings in the label placer are not handled. Placement order is by id, not importance.
- The AV1 test file (SVT-AV1 via PyAV 18) has a wrong barcode block at frames 14 and 254 in the bitstream, so those frames count as decode failures (investigator observation, NOTES §11; 297/297 and 296/296 decoded counts are consistent).
- P3 libass alignment was measured only with the ffmpeg CLI. It cannot be reproduced through PyAV 19.0.2 (no `ass` filter).
- The PyAV 19.0.2 re-check used 60 frames, not 300.

## 7. How to reproduce

From the repo root (`C:/Users/Dom/GitHub/freemocap/skellycam`) in Git Bash. In PowerShell, use `Remove-Item Env:ELECTRON_RUN_AS_NODE` instead of `env -u`.

```
# functional, no PyAV (pure Python / cv2); results/overlays/formats_functional.{json,md}, label_layout.{json,md}
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/formats_functional.py --frames 300
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/label_layout.py --frames 60

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

# timed (tonight only): see results/bench_queue_from_wf_2e122ed0.json -> overlays.bench_manifest
```
