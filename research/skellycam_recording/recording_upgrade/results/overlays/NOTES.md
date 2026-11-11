# Overlays as a separate layer (G3): notes

Study date 2026-11-09, machine Gerald (Windows 11, i7-14700K, RTX 3070). Topic folder: `research/skellycam_recording/recording_upgrade/{scripts,results}/overlays/`.
Media (videos and images; they show the room) are only in `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/overlays/` (called `<raw>/overlays` below).

Labels: **measured** = a result file from this study (path given); **source** = primary source (accessed 2026-11-09); **code** = repo file:line; **inferred** = my reasoning, not a fact.
Timing rule: this stage reports **no timing, throughput or CPU numbers**. Per-frame costs are in the bench manifest (§9) for a quiet-machine run.

## 0. Summary

- Today's only recorded overlay is skellycam's text stamp, burned into every recorded frame. FreeMoCap draws richer overlays (ChArUco corners with ids, ArUco outlines, 33/133-point skeletons, boxes, status text). Its live UI composites them onto the frame bitmap in a worker. Its post-hoc pipeline burns them into a second "annotated" video (§1).
- A **data-level sidecar** keyed by frame number and timestamp survives truncation in every test: append-only records, schema in a header, per-record framing (CRC for the binary form). JSONL, length-prefixed MessagePack and a custom binary all lost no complete record at any of 28 cut points. The custom binary is the smallest for the full FreeMoCap overlay: 355 MB/hour at 30 fps against 616 MB/hour for JSONL. Render-level SVG is 6-11x larger, and a single SVG per recording becomes unreadable after a crash (§3, §4). (**measured**)
- In Chromium, a canvas overlay looked up from `requestVideoFrameCallback` `metadata.mediaTime` (nearest entry in a per-frame pts table) names the presented frame in 98-100% of callbacks at 1x (100% at CFR). In the screen captures, though, a canvas layered over `<video>` usually shows the overlay one frame behind (3/30 to 19/30 captures aligned). Drawing the video into the same canvas as the overlay gave 29/29 to 30/30. Today's UI method, `floor(currentTime*30)` in rAF, matched the shown frame in only 2-78% of samples (§5). (**measured**)
- WebVTT metadata cues lag the presented frame by one during playback, and are correct only on paused CFR seeks. Neither WebVTT-in-WebM nor ASS-in-MKV is exposed as a text track in Electron 35 or 45. ASS timing is in centiseconds, so naive per-frame events miss every third 30 fps frame when burned with libass; shifting events half a frame earlier fixes that (§6, §8). (**measured**, **source**)
- A VP9-alpha WebM overlay layer plays with alpha in Chromium and survives truncation. It costs 80 KB/frame at 720p for the full overlay, more than the camera's own JPEG (~57 KB). PNG-in-MOV and QTRLE-in-MOV do not play in Chromium and cannot be read at all after truncation (§7). (**measured**)
- Overlap avoidance: one deterministic greedy placement (8 directions x 3 rings, then side lanes with leader lines, then a hidden count), written in both Python and JS. It removed every label-label and label-marker overlap in all tested cases; the naive styles had 0-68,733 label-label overlaps (§8). (**measured**)
- Electron 45.2.3 fixes a playback bug that matters for scrubbing. In Electron 35.7.5, after a seek to the last frame, every later seek in all 5 test files fires `seeked` but never shows a new frame (§5.3). (**measured**)

## 1. Inventory of overlays today

| Where | What is drawn | Per-frame data shape | Burned into a file? | Evidence |
|---|---|---|---|---|
| skellycam capture loop | `camera.id{id}.idx{index}.fr{N}`, cv2.putText at (10,40), HERSHEY_SIMPLEX 0.8, black outline thickness 8, colour BGR (255,210,210) | camera id, index, connection frame number | **Yes**: drawn into the recorded buffer; no clean copy | code `skellycam/core/camera/opencv/opencv_helpers/opencv_get_frame.py:79-90`; measured `research/skellycam_recording/results/real_recording_20261109/RESULTS.md` §6 |
| skellycam-ui live view | nothing drawn on the image; hover header with checkbox/settings buttons | - | No | code `skellycam-ui/src/components/camera-views/CameraGridCell.tsx:41`; frames shown via `bitmaprenderer` `offscreen-renderer.worker.ts:35,80` |
| skellycam-ui playback | HTML `div`s over each `<video>`: `F{frame}` (top right), camera id (bottom left), timecode (bottom right) | frame index = `floor(leader.currentTime * fps)` in a rAF loop; timestamps from the recording if present | No | code `skellycam-ui/src/components/playback/SyncedVideoPlayer.tsx:281-309, 377-408, 658-710` (identical on `upstream/sfn26`: `diff --strip-trailing-cr` empty) |
| skellycam Rust backend (`upstream/sfn26`) | no overlay | - | No | code `git grep -i overlay upstream/sfn26 -- skellycam-rust` returns nothing |
| FreeMoCap live UI, ChArUco | corners: filled circle r=5 plus id label at (+r+3, -r-3), 10 px; ArUco quads with id; info panel `fillRect(5,5,500,85)` with frame/counts/status text | `CharucoOverlayData`: camera_id, frame_number, corners [{id,x,y}], aruco [{id, 4 corners}], metadata | No (composited onto the frame bitmap in a worker) | code freemocap `freemocap-ui/src/services/server/server-helpers/image-overlay/charuco-overlay-renderer.ts:16-38,164-190`, `image-overlay-system.ts:128-163`; data `freemocap/core/viz/image_overlay/charuco_overlay_data.py:6-36` |
| FreeMoCap live UI, skeleton | points and connections coloured by side/hand/face; optional person bbox (strokeRect) | `SkeletonOverlayData`: camera_id, frame_number, tracker_id, points [{name,x,y,z,visibility}], bbox x1..y2, bbox_from_detector | No | code `skeleton_overlay_data.py:21-52`, `skeleton-overlay-renderer.ts:223-266` |
| FreeMoCap live wire format | binary blocks `SKELETON_OVERLAY_2D`/`CHARUCO_OVERLAY_2D`, float32 `[x,y,vis]` per point, frame number in the payload header | already a compact per-frame binary record | - | code `freemocap/api/websocket/binary_keypoints_protocol.py:1-56` |
| FreeMoCap live pairing | the **latest** overlay observation is drawn on whatever frame is current (no frame-number match), and dropped after 500 ms | - | - | code `freemocap-ui/src/services/server/server-helpers/offscreen-renderer.worker.ts:17,62,83,103` |
| FreeMoCap post-hoc | skellytracker `CharucoAnnotator`: diamond markers (10 px, thickness 2) with `Corner#{id}` text at (+1% H, +1% H), 15-frame fading track, ArUco polylines, an "Undetected Corners" list at x = W-200 with one line per id every 20 px. `KeypointAnnotator`: circles r=4, lines w=2, boxes with confidence label | skellytracker `Observation` per frame | **Yes**: `annotated_videos/<stem>_annotated.mp4` (cv2.VideoWriter avc1→mp4v→MJPG); new annotation layers are drawn on top of an existing annotated video | code freemocap `freemocap/core/pipeline/posthoc/video_node.py:121-157,316-358,391-411`; skellytracker @6f78af48 (the commit freemocap's `uv.lock:2236-2238` pins) `charuco_annotator.py:14-201`, `keypoint_annotator.py:15-170`; `annotation_style.py:12-125` |
| Tracker sizes | MediaPipe body: 33 points, 35 connections; RTMPose wholebody: 133 points; default board 7x5 squares (24 inner corners) | | | code skellytracker @6f78af48 `mediapipe_body.yaml`, `rtmpose_wholebody.yaml:1-4`; freemocap `api/http/calibration/calibration_router.py:68-70` |

Observed overlap problems in today's overlays:
- skellycam's burned stamp spans about x 5-340, y 15-50 px (**measured**, RESULTS.md §6). FreeMoCap's live ChArUco info panel is drawn at (5,5,500x85) (**code** `charuco-overlay-renderer.ts:165`). So the panel covers the stamp, and ChArUco corners in that strip sit under both (**inferred**).
- The skellytracker "Undetected Corners" list draws one line per id at y = 40 + 20i (**code** `charuco_annotator.py:163-187`). It fits 35 lines at 720p and 53 lines at 1080p before leaving the image (**measured** arithmetic, `results/overlays/label_layout.json`).
- Schema drift (code observation): freemocap-ui `charuco-types.ts:21` requires `metadata.has_pose`, which Python `CharucoMetadataModel` (`charuco_overlay_data.py:19-26`) does not send. Whether this breaks anything at runtime is NOT VERIFIED; live overlays now use the binary block path.

## 2. Test data and tools

- Overlay data: deterministic synthetic coordinates shaped like the FreeMoCap payloads. Script `scripts/overlays/overlay_model.py`; schema `mediapipe_body_schema.json` is extracted from skellytracker @6f78af48 by `extract_schema.py`. Cases:
  - **text**: today's stamp only.
  - **skeleton**: stamp plus the 33-point body.
  - **charuco**: stamp plus an 11x11-square board, i.e. 100 inner corners with ~95 detected per frame (5% dropout) and ~55 ArUco outlines, `Corner#id` labels and the undetected list.
  - **all**: everything above.
  - Coordinates are rounded to 0.01 px. No tracker is run.
- Video frames: the real camera JPEGs of corpus set `c930e_720p_flash`, frames 0-299 (1280x720), decoded with OpenCV 4.12.0. A 16-block barcode of the frame index is stamped into rows 680-719 (12 index bits plus a 4-bit popcount check). Overlay layers carry their own barcode in rows 60-99, x 0-639. Script `scripts/overlays/make_test_media.py` (PyAV 18.0.0 / libavcodec 62.28.102, ffmpeg 9.0.2 gyan full); log `results/overlays/make_test_media.json`.
- VFR files: pts jittered ±4 ms with a two-frame gap after frame 149, intervals 26-103 ms. The container pts read back with ffprobe equal the intended pts exactly (max diff 0.0) (**measured**, check command in §10).
- Browsers: Electron 35.7.5 (Chromium 134.0.6998.205, Node 22.16.0), as pinned by skellycam-ui, and Electron 45.2.3 (Chromium 156.0.8078.80, Node 24.22.2). Versions are from `process.versions`. Display scaleFactor 1; GPU compositing enabled (**measured**, `env` block of `results/overlays/electron_*.json`).
- Harness `scripts/overlays/electron_harness/`: `main.js` (HTTP server with Range support, `webContents.capturePage` decoding of both barcodes from screen pixels), `harness.js`, `layout.js`. No npm dependencies. A visible 1360x900 window shows the videos at 640x360 CSS px.
- The machine was shared with other agents during the Electron runs. Rows that depend on timing are marked "load-sensitive" and are rerun on a quiet machine in the bench manifest (§9).

## 3. Storage formats: size, round trip and truncation (functional)

Script `scripts/overlays/formats_functional.py --frames 300`; results `results/overlays/formats_functional.{json,md}`. Bytes/hour is extrapolated linearly from 300 frames at 30 fps.

| format (720p) | text: B/frame | skeleton: B/frame | charuco: B/frame | all: B/frame | all: MB/hour | round trip | truncation: complete records recovered at 28 cuts |
|---|---|---|---|---|---|---|---|
| (c) custom binary `.skov` (header JSON + per-record MAGIC/len/payload/CRC32, float32) | 42.3 | 445.3 | 2889.4 | 3287.6 | 355.1 | exact within float32 (tol 1e-3) | 28/28 |
| (c) JSON Lines | 45.9 | 666.9 | 5091.5 | 5704.3 | 616.1 | exact | 28/28 |
| (c) MessagePack, length-prefixed (msgspec 0.21.1, floats as float64) | 31.4 | 928.5 | 6008.9 | 6895.6 | 744.7 | exact | 28/28 |
| (d) WebVTT metadata (one cue per frame, JSON payload) | 77.2 | 698.2 | 5122.8 | 5735.6 | 619.4 | exact | 28/28 (Python reader) |
| (e) ASS (text + `\p1` drawing) | 95.4 | 2628.0 | 14621.6 | 17056.0 | 1842.0 | not parsed back | n/a |
| (a) SVG per frame (one file per frame) | 289.1 | 5161.4 | 30430.4 | 35283.3 | 3810.6 | 300/300 files parse | each file independent |
| (b) one SVG per recording (`<g id=fN>` per frame, closing tag on stop) | 167.7 | 5040.0 | 30309.0 | 35161.9 | 3797.5 | strict parse OK | strict XML parse fails at 25/25 cuts; a regex reader recovers complete groups |

- 1080p sizes are within 6% of 720p (coordinates have more digits). See `formats_functional.md` (**measured**).
- "Recovered" means every record that ended before the cut came back, and no corrupt record was returned. A cut exactly before a record's terminating newline can return that record as well; this happened at 1 cut per text format (field `trunc_cuts_with_extra_record_before_newline`) (**measured**).
- MessagePack is larger than JSON here because msgspec encodes Python floats as 8-byte float64, while JSON holds 2-decimal text (**inferred** from the msgpack float64 encoding; not separately tested). A float32 array field would shrink it (NOT TESTED).
- For the **text** case the data formats store only cam/idx/frame/timestamp; the stamp string is rebuilt at render time. The render formats store the string (**code** `overlay_model.py` `to_dict` vs `primitives`).
- Truncated files in Chromium, Electron 35 and 45 (**measured**, `electron_*.json` → `trunc`):
  - The full single SVG loads as `<img>`.
  - The same file cut at 50% fires `img.onerror`, and `DOMParser` reports `parsererror`.
  - A WebVTT file cut at 50% still loads 150/300 cues. The last cue's JSON payload is torn (fails `JSON.parse`), so a reader must skip the last cue.

## 4. Data-level vs render-level: what the format choice decides

- Today's FreeMoCap wire protocol already sends overlays as per-frame float32 point blocks keyed by frame number, with drawing done in the UI from a tracker schema sent once (**code** `binary_keypoints_protocol.py:1-56`, `skeleton_overlay_data.py:1-12`). The `.skov` binary tested here is the same idea plus file framing and a CRC per record.
- Storing pre-rendered vectors (SVG/ASS) fixes the style and label positions at record time. It is 6-11x larger than the data sidecar for the same frames (§3 table). A data sidecar can be re-rendered at any display size, with layout done at render time (§8) (**inferred** from the table and §8).

## 5. Chromium playback: overlay-to-frame alignment (functional)

Method:
- Play each file to the end at 1x (and 2x for VP9). In every `requestVideoFrameCallback`:
  - (i) read the video's barcode with `drawImage(video)` + `getImageData` (the frame actually decoded);
  - (ii) take the overlay frame index from `nearest(pts, metadata.mediaTime)`, draw the full overlay plus its own barcode on a canvas over the video, and check it;
  - every 10th callback, capture the composited window (`capturePage`) and decode both barcodes from the screen.
- In a separate rAF loop, apply today's skellycam-ui rule `floor(currentTime*30)` and compare it with the decoded barcode.
- Results: `results/overlays/electron_35.7.5.json`, `electron_45.2.3.json`; tables in `electron_summary.md` (generated by `summarize_electron.py`). (**measured**, load-sensitive)

### 5.1 Playback at 1x

| Electron | file | rVFC lookup == decoded frame | `round(mediaTime*30)` == frame | today's rAF `floor(currentTime*30)` == frame | screen captures with overlay == video |
|---|---|---|---|---|---|
| 35.7.5 | CFR H.264 MP4 | 299/299 | 299/299 | 111/597 | 11/30 |
| 35.7.5 | CFR VP9 WebM | 299/299 | 299/299 | 289/598 | 19/30 |
| 35.7.5 | CFR AV1 WebM | 297/297 | 297/297 | 464/595 | 4/30 |
| 35.7.5 | VFR VP9 WebM | 299/299 | 149/299 | 36/602 | 10/30 |
| 35.7.5 | VFR H.264 MP4 | 291/295 | 149/295 | 153/602 | 11/30 |
| 35.7.5 | CFR VP9, **video drawn into the overlay canvas** | 291/291 | 291/291 | - | **29/29** |
| 35.7.5 | VFR H.264, video drawn into the canvas | 296/296 | 147/296 | - | **30/30** |
| 45.2.3 | CFR H.264 MP4 | 299/299 | 299/299 | 35/600 | 3/30 |
| 45.2.3 | CFR VP9 WebM | 299/299 | 299/299 | 58/599 | 4/30 |
| 45.2.3 | CFR AV1 WebM | 296/296 | 296/296 | 13/596 | 11/30 |
| 45.2.3 | VFR VP9 WebM | 282/287 | 147/287 | 145/604 | 8/29 |
| 45.2.3 | VFR H.264 MP4 | 290/292 | 143/292 | 100/604 | 10/29 |
| 45.2.3 | CFR VP9, video drawn into the canvas | 299/299 | 299/299 | - | **30/30** |
| 45.2.3 | VFR H.264, video drawn into the canvas | 287/287 | 137/287 | - | **29/29** |

- At 1x, every recorded capture mismatch (the JSON keeps up to 20 per run) has the form `[video N, overlay N-1]`; at 2x some are N-2. On screen the canvas overlay lags the `<video>` layer by one frame. The rVFC spec allows this: "a callback can occasionally be fired one v-sync late, relative to when the new video frame was presented", and "drawing operations might occasionally appear on screen one v-sync after the video frame does" (**source** https://wicg.github.io/video-rvfc/ §1). Here it was the common case, not occasional (**measured**).
- Every recorded rVFC lookup mismatch (up to 20 kept per run) has the form `decoded = lookup + 1`: `drawImage(video)` inside the callback returned the frame after the one `metadata` describes. At 2x VP9 this happened in 72/241 callbacks (Electron 35) and 12/281 (Electron 45). The spec does not say which frame `drawImage` returns inside the callback (**source**, same page; NOT VERIFIED either way). So the canvas-composite method can draw a video frame one ahead of its overlay when callbacks run late (**inferred** from the 2x rows).
- `round(mediaTime*30)` is correct only for CFR. VFR needs the pts table, as in the VFR rows (**measured**).
- Today's skellycam-ui rule (`floor(currentTime*fps)` in rAF) gave the shown frame in 2%-78% of samples, varying by codec and Electron version. The mismatches are mostly -1, and +1/+2 on VFR (**measured**; code `SyncedVideoPlayer.tsx:377-403`).
- Two `<video>` elements played together (base + VP9-alpha layer): every screen capture matched (25/25 in E35, 27/27 in E45). Reading both elements with `drawImage` inside the base's callback found the layer one frame ahead in 136/250 and 195/271 callbacks. Paused seeks of both to the same time: 30/30 on the requested frame (**measured**).

### 5.2 Paused seeks (80 targets: steps forward, scattered, steps back over the VFR gap)

| file | Electron | seek to exact pts: shown == requested | seek to midpoint of [pts f, pts f+1]: shown == requested | shown == lookup(mediaTime) | screen capture immediately / +100 ms: overlay == video |
|---|---|---|---|---|---|
| CFR H.264 | 35 / 45 | 80/80 / 80/80 | 80/80 / 80/80 | all | 75/80, 80/80 / 64/79, 80/80 |
| CFR VP9 | 35 / 45 | 79/80 / 79/80 | 80/80 / 80/80 | all | 78/80, 80/80 / 80/80, 80/80 |
| VFR VP9 | 35 / 45 | 43/80 / 56/80 | 80/80 / 80/80 | all | 79/80, 80/80 / 78/80, 80/80 |
| VFR H.264 | 35 / 45 | 42/80 / 80/80 | 76/80 / 79/80 | all | 66/80, 80/80 / 74/80, 80/80 |

- On VFR, a seek to a frame's exact pts often shows the previous frame. The midpoint seek fixed it for VP9 (80/80) but not completely for H.264 in Electron 35 (76/80) (**measured**). In every case the overlay driven by the rVFC `mediaTime` matched what was shown (all rows "all"). An overlay keyed to the requested time would not have matched (**measured**).
- Paused composites always converged by +100 ms. Immediately after the seek (after two rAFs) up to 15/79 captures still showed the previous overlay (**measured**, load-sensitive).
- skellycam-ui seeks with `currentTime = frame / fps` (**code** `SyncedVideoPlayer.tsx:334,506`). That is the "exact" mode, which is reliable only for CFR files (**inferred** from the table).

### 5.3 Seek to the last frame (Electron 35 bug, fixed in 45)

| Electron | sequence 100, 298, 299 (last), 150, 0, 299, duration, 75 → frame shown |
|---|---|
| 35.7.5 (all 5 files) | 100, 298, 299, then **299 for every later seek**: `seeked` fires, no rVFC, `currentTime` reads `duration`, `ended` stays true |
| 45.2.3 (all 5 files) | 100, 298, 299, 150, 0, 299, 299 (or 298), 75 (VFR VP9: 74) |

(**measured**, `electron_*.json` → `lastframe`). A frame-stepping UI on Electron 35 should never seek to the last frame (or should reload the source afterwards). Upgrading to Electron 45 removes the problem in these files (**inferred** from the table).

## 6. WebVTT and subtitle streams in Chromium (functional)

| case | Electron 35.7.5 | Electron 45.2.3 |
|---|---|---|
| `<track kind=metadata>` CFR, cue f = [f/30, (f+1)/30): active cue == shown frame in rVFC during play | 148/299 (rest -1) | 8/299 (rest -1) |
| same, cues shifted half a frame earlier | 207/299 | 18/298 |
| VFR, cue times = container pts | 95/285 | 32/286 |
| paused seeks (CFR / VFR): active cue == shown frame | 40/40 / 30/40 | 40/40 / 32/40 |
| WebVTT muxed in WebM (`ffmpeg -c:s webvtt`): `video.textTracks.length` | 0 | 0 |
| ASS muxed in MKV: file plays, `textTracks.length` | plays, 0 | plays, 0 |
| `canPlayType('video/x-matroska')` | `''` | `'maybe'` (`; codecs="avc1.42E01F"` → `'probably'`) |

(**measured**, load-sensitive in the play rows)
- WebVTT cue times have millisecond resolution: "Three ASCII digits, representing the thousandths of a second". Metadata cues "are only useful for scripted applications", and "Metadata can be any string and is often provided as a JSON construct" (**source** https://www.w3.org/TR/webvtt1/ §4.1, §1.7).
- During playback, the active cue usually trails the shown frame by one. The half-frame shift helped in Electron 35 only. On VFR, paused seeks fail where the seek lands on the previous frame (§5.2), because cues follow `currentTime`, not the shown frame (**measured**). WebVTT is usable for a paused CFR UI but not as the frame-accurate sync source (**inferred**).
- ASS timing is centiseconds: ffmpeg's ASS demuxer parses `H:MM:SS.CC` and sets time base 1/100 (`(hh1*3600LL + mm1*60LL + ss1) * 100LL + ms1`, `avpriv_set_pts_info(st, 64, 1, 100)`) (**source** https://raw.githubusercontent.com/FFmpeg/FFmpeg/n8.0/libavformat/assdec.c). Muxed in MKV, each per-frame event became a packet of duration 0.03 s, and each Dialogue line is its own packet: 30,898 packets for 300 frames (**measured**, `make_test_media.json` → `ass_mkv_packets`).

## 7. Alpha video overlay layer (functional; size is deterministic)

| layer (720p, full "all" overlay, 300 frames) | bytes/frame | MB/hour @30 fps | plays in Chromium 134/156 | 50% truncation: frames decoded (ffmpeg) |
|---|---|---|---|---|
| VP9 alpha WebM (libvpx-vp9, yuva420p, crf 32, realtime cpu-used 8) | 80,251 | 8,667 | yes, alpha==0 on 87.5% of frame 0 (reference matte 87.3%) | 160, all with transparency |
| PNG in MOV (rgba) | 155,859 | 16,833 | no: `DEMUXER_ERROR_NO_SUPPORTED_STREAMS` | 0 (`Invalid data found when processing input`) |
| QTRLE in MOV (argb) | 290,996 | 31,428 | no: same error | 0 |
| for scale: data sidecar `.skov` | 3,288 | 355 | n/a | 28/28 cuts |
| for scale: camera's own JPEG (c930e 720p) | 56,759 median | - | - | - |

(**measured**: `make_test_media.json`, `alpha_truncation.json`, `electron_*.json` → `caps`/`alpha`, corpus `index.json`)
- ffprobe reports the VP9-alpha stream as `pix_fmt yuv420p` with tag `alpha_mode=1`. Decoded with `-c:v libvpx-vp9`, the alpha matches the source matte (mean abs diff 0.11 of 255) (**measured**).
- In ffmpeg, the overlay filter keeps alpha only when the layer is decoded with `-c:v libvpx-vp9`. With the default native vp9 decoder the layer came out opaque and covered the base in 299/300 frames: base barcode read as 0, overlay barcode correct (**measured**, `export_burnin.json` `p2` vs `p2b`).
- Generation cost (two cv2 renders plus matte, then a VP9 encode) is benchmarked only: `alpha_render`, `alpha_vp9_pipeline` in §9.

## 8. Overlap avoidance, and export with overlays burned in

### 8.1 Deterministic label placement

Algorithm (same in `scripts/overlays/label_layout.py:place_labels` and `electron_harness/layout.js:placeLabels`):
1. Process anchors in ascending id.
2. For each anchor, try 8 directions x 3 rings and take the first box that is inside the image and hits no placed label and no marker.
3. If none fits, use the nearest side lane, at the free slot closest to the anchor's y, with a leader line.
4. If both lanes are full, hide the label and count it.
5. HUD text (stamp, ChArUco counts, undetected ids) is stacked in one measured top-left column, and the undetected ids are wrapped to a fixed width.

| case (60 frames, ~95 labels/frame) | style | label-label overlaps | label-marker overlaps | out of image |
|---|---|---|---|---|
| 720p, board 55% of height | A skellytracker `Corner#id` at +1% H | 12,272 | 13,397 | 0 |
| | B freemocap-ui id at (+r+3, -r-3) | 0 | 332 | 0 |
| | C placed | **0** | **0** | 0 |
| 1080p, board 55% | A / B / C | 9,706 / 116 / **0** | 10,657 / 1,450 / **0** | 0 |
| 720p, board 20% (dense) | A / B / C | 68,733 / 7,223 / **0** | 57,092 / 21,957 / **0** | 0 (C: 1,474 labels in lanes, 0 hidden) |
| browser, 12 px Arial, Electron 35 and 45 | naive (+8,-8) vs placeLabels | 11 vs **0** | 322 vs **0** | 0 |

- Text is measured with `cv2.getTextSize` in Python and with `measureText` in the browser. Two runs gave identical placements (deterministic: true in all cases). HUD panels: 0 overlapping pairs. Images: `<raw>/overlays/layout/{A_today,C_placed}_*.png` (**measured**: `label_layout.{json,md}`, `electron_*.json` → `layout`).
- Limits:
  - Leader lines are not checked for crossings (visible in `C_placed_720p_board20.png`).
  - Placement order is by id, not importance.
  - The greedy result is collision-free but not optimal (**measured** image / **inferred**).

### 8.2 Export with overlays burned in (for sharing)

Script `scripts/overlays/export_burnin.py --frames 300`; results `results/overlays/export_burnin.json`. "Aligned" means the source-frame barcode equals the overlay-frame barcode in each decoded output frame.

| path | output | frames | aligned |
|---|---|---|---|
| P1 PyAV 18 + cv2: camera JPEG → read `.skov` sidecar → `burn_in` → libvpx-vp9 WebM | 15.2 MB | 300 | 300/300 |
| P1 same → libx264 MP4 | 11.8 MB | 300 | 300/300 |
| P2 ffmpeg `overlay` filter, base VP9 + VP9-alpha layer decoded with `-c:v libvpx-vp9` | 14.9 MB | 300 | 300/300 |
| P2b same with the default vp9 decoder | 12.1 MB | 300 | 1/300 (layer opaque) |
| P3 ffmpeg `ass` filter (libass), event f = [f/30, (f+1)/30) rounded to cs | 0.96 MB | 300 | **200/300** (every 3rd frame shows the previous event) |
| P3b libass, events shifted half a frame: [(f-0.5)/30, (f+0.5)/30) | 0.96 MB | 300 | 300/300 |

(**measured**)
- A canvas-based export in the browser was not built. WebCodecs `isConfigSupported` at 1920x1080 on this machine (identical in Electron 35 and 45):

| codec | encode, hardware | encode, software | decode, hardware |
|---|---|---|---|
| VP8 | false | true | false |
| VP9 | false | true | true |
| AV1 | false | true | true |
| H.264 | true | true | true |
| HEVC | true | false | true |

  So a royalty-free canvas export would use a software encoder in the browser (**measured** `electron_*.json` → `webcodecs`; **inferred** conclusion).

## 9. Benchmarks to run later (quiet machine, one at a time)

See the manifest returned with these notes. Each command writes JSON into `results/overlays/bench/`. Smoke runs passed: `bench_overlay_cost.py --frames 20 --repeats 1 --smoke` (all 12 methods, alpha pipeline rc 0), and the Electron `drawbench` with `reps=1`. The smoke outputs were deleted, and no smoke timings are reported.

## 10. Exact commands used (from repo root, Git Bash)

```
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/extract_schema.py
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/formats_functional.py --frames 300
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/make_test_media.py --frames 300
env -u ELECTRON_RUN_AS_NODE skellycam-ui/node_modules/electron/dist/electron.exe research/skellycam_recording/recording_upgrade/scripts/overlays/electron_harness --out=research/skellycam_recording/recording_upgrade/results/overlays/electron_35.7.5.json --tests=caps,play,seek,lastframe,vtt,inband,alpha,trunc,webcodecs,layout
env -u ELECTRON_RUN_AS_NODE C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/shared/electron-latest/node_modules/electron/dist/electron.exe research/skellycam_recording/recording_upgrade/scripts/overlays/electron_harness --out=research/skellycam_recording/recording_upgrade/results/overlays/electron_45.2.3.json --tests=caps,play,seek,lastframe,vtt,inband,alpha,trunc,webcodecs,layout
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/summarize_electron.py
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/label_layout.py --frames 60
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/export_burnin.py --frames 300
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/alpha_truncation.py
```

- `ELECTRON_RUN_AS_NODE=1` is set in this shell's environment. Without `env -u` (PowerShell: `Remove-Item Env:ELECTRON_RUN_AS_NODE`), electron.exe runs as plain Node and fails with `Cannot find module 'electron'` (**measured**).
- `nvidia-smi` around the Electron runs read `0, 10 %`, then `0, 11 %`, then `0, 14 %` (encoder sessions, GPU util). No NVENC session was opened by these tests (**measured**).
- No third-party downloads were made. Electron 45.2.3 is the shared read-only install.

## 11. Limits

- Overlay coordinates are synthetic. Real tracker output, with NaNs, a variable point count and RTMPose's 133 points, will change sizes. The per-point record cost in §3 scales roughly linearly with the point count (**inferred**).
- Only one display (scaleFactor 1, 60 Hz assumed, not measured) and one GPU were tested. Screen-capture alignment depends on compositor timing and the machine was loaded. The capture counts are evidence of the lag pattern, not stable rates.
- A capturePage sample every 10th callback is 29-30 samples per file.
- The SVG/ASS files from §3 were not rendered in Chromium; only the single-SVG `<img>` load/error was tested. ASS is not rendered by Chromium at all (no text track; §6).
- AV1 test file: the SVT-AV1 output (PyAV 18, preset 10, crf 35) has one wrong 80x40 barcode block at frames 14 and 254. libdav1d via PyAV decodes the same wrong block, so it is in the bitstream, not a player error. Those frames count as decode failures (**measured**).
- No timing numbers are given anywhere here (stage rule).

## 12. Bench manifest (copy of what was returned)

| id | priority | command (repo root, Git Bash) | writes |
|---|---|---|---|
| overlay_cost | 1 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/bench_overlay_cost.py --frames 900 --repeats 3` | `results/overlays/bench/bench_overlay_cost_<UTC>.json` |
| electron_draw_35 | 2 | `env -u ELECTRON_RUN_AS_NODE skellycam-ui/node_modules/electron/dist/electron.exe research/skellycam_recording/recording_upgrade/scripts/overlays/electron_harness --tests=drawbench --mode=bench --query=reps=5 --out=research/skellycam_recording/recording_upgrade/results/overlays/bench/electron_drawbench_35.7.5.json` | that JSON |
| electron_play_quiet_35 | 2 | `env -u ELECTRON_RUN_AS_NODE skellycam-ui/node_modules/electron/dist/electron.exe research/skellycam_recording/recording_upgrade/scripts/overlays/electron_harness --tests=play,seek,vtt,alpha --out=research/skellycam_recording/recording_upgrade/results/overlays/bench/electron_play_quiet_35.7.5.json` | that JSON (summarise with `summarize_electron.py <file>`) |
| electron_play_quiet_45 | 2 | same with `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/shared/electron-latest/node_modules/electron/dist/electron.exe` and `..._45.2.3.json` | that JSON |
| electron_draw_45 | 3 | drawbench with Electron 45.2.3 | that JSON |

Pre-requisite for the Electron benches: `<raw>/overlays/media/` must exist. If it does not, run `make_test_media.py --frames 300` first (about 2 min, not timed). The Electron window must stay visible and uncovered during the play runs.
