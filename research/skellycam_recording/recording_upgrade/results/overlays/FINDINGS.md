# Overlays as a separate layer (G3): findings

Revised 2026-11-10 with the quiet timed bench (run `20261109T230007`; OV-COST re-run `20261110T053653`), then corrected after two verifier passes (see Verification at the end). The earlier functional work is from 2026-11-09. Machine: Gerald, Windows 11.

- CPU: Intel Core i7-14700K (**measured** `results/uncompressed_intra/verify_method/cpu_topology.txt:3`).
- GPUs: RTX 3070 on NVIDIA driver 610.88, and Intel UHD 770 on driver 32.0.101.7088 (**measured** `results/BENCH_RUN_2300_SUMMARY.md` §2, read with nvidia-smi and `Win32_VideoController` after the run).
- Chromium's GPU list in both runs: vendorId 4318 / deviceId 9348 (RTX 3070, driverVersion 32.0.16.1088) and vendorId 5140 (Microsoft Basic Render). Intel (32902 / 42880) appears only in the quiet run (**measured** `env.gpuInfo.gpuDevice` in `R/electron_*.json` and `B/electron_play_quiet_*.json`).

Paths are relative to `research/skellycam_recording/recording_upgrade/`, unless they start with `skellycam/`, `skellycam-ui/` or `freemocap`.

| short | path |
|---|---|
| `R/` | `results/overlays/` |
| `B/` | `results/overlays/bench/` |
| `S/` | `scripts/overlays/` |
| `H` | `S/electron_harness/harness.js` |
| `LOG` | `results/BENCH_RUN_2300_LOG.jsonl` |
| `<raw>` | `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/` |

Labels:
- **measured**: a result file (path given).
- **source**: a primary source (URL, exact quote, access date).
- **code**: file:line.
- **inferred**: reasoning, kept short.
- **arithmetic**: plain arithmetic on measured values.
- "PyAV 18, background": made with the skellycam venv (PyAV 18.0.0), not with the implementation under test (PyAV 19.0.2).
- "ffmpeg CLI, background": made with the gyan ffmpeg 9.0.2 CLI. Under the study rules the CLI may only inspect files.
- "GOP 30, background": the Chromium test clips and the VP9-alpha layers are inter-coded with `gop_size = 30` (**code** `S/make_test_media.py:88`; VP9-alpha uses `-g 30`, `:187`; PyAV 19 alpha check `S/pyav19_functional_check.py:182`).
  - Under HANDOFF requirement 8 these files are background.
  - The Chromium clips test overlay mechanics (rVFC, canvas, seeks), not an intra-only recording format.

**Quality targets: no number in this topic is at target A (SSIM-Y 0.9961) or target B (PSNR-Y 45 dB).**
- The only lossy re-encode measured here is the burn-in round trip at cv2 JPEG q90 (**code** `S/bench_overlay_cost.py:163`). Its quality was not measured, so it is at neither A nor B.
- The Chromium test clips and the VP9-alpha layer use fixed CRF settings (`R/make_test_media.json`). They are not at A or B either.

**Timing source.** Every timing number comes from the quiet run's JSON in `B/`. Nothing was re-timed for this revision.
- Each value was recomputed from the raw files: the OV-COST medians, min-max and sizes; the drawbench fields; and the play, seek, VTT and alpha counts. All of it matches `R/BENCH.md`. Both verifiers recomputed them again independently (`R/VERIFY_provenance.md`, `R/VERIFY_method.md`).
- Three results come from the raw files and are not stated in BENCH.md:
  - the drop-counter cross-check (2.3.3);
  - the cause of the composite capture mismatch, which is a second `drawImage` call (2.3.2);
  - the timestamp-truncation explanation of the f241 seek misses (2.3.4).

**Provenance of the functional results** (unchanged from the verified 2026-11-09 version):
- `R/electron_summary.md` was regenerated from `R/electron_35.7.5.json` and `R/electron_45.2.3.json`. It is byte-identical after the title line (2026-11-09 reports, now `R/VERIFY_provenance.prev.md` and `R/VERIFY_method.prev.md`).
- The PyAV-dependent functional results were re-run on PyAV 19.0.2 at 60 frames: `R/pyav19_functional_check.json`.
- The verifiers' crash and precision checks use no PyAV: `R/verify_method_crash_modes.json`, `R/verify_method_precision.json`.

## 1. Questions answered

1. What overlays exist today, where are they drawn, and do they overlap?
2. Which storage form for overlays, kept apart from the camera frames, is smallest, cheapest to write per frame, and survives a crash? The options are a data sidecar, SVG/ASS vector files, or an alpha video layer.
3. What does burning overlays in cost per frame, especially when frames would otherwise pass through as camera JPEGs (G1)?
4. Can Chromium (Electron 35.7.5 and 45.2.3) draw a separate overlay frame-accurately over `<video>`? With which method, and at what draw cost?
5. Can overlap between labels be removed deterministically?
6. Can overlays still be burned in for export or sharing, and does that work through PyAV 19.0.2?

## 2. Findings

### 2.1 Today's overlays (inventory)

- skellycam burns `camera.id{id}.idx{index}.fr{N}` into every recorded frame (**code** `skellycam/core/camera/opencv/opencv_helpers/opencv_get_frame.py:79-90`):
  - it uses `cv2.putText` at (10,40), scale 0.8, with a black outline of thickness 8;
  - no clean copy of the frame is kept.
- The burned stamp covers about x 5-340, y 15-50 px, at the same pixel size at 720p and 1080p (**measured**, background study `research/skellycam_recording/results/real_recording_20261109/RESULTS.md:145`).
- skellycam-ui playback draws nothing into the video pixels. It positions HTML frame and time labels absolutely over each `<video>` (**code** `skellycam-ui/src/components/playback/SyncedVideoPlayer.tsx:281-308` `updateOverlays`; `:658-700` `position: 'absolute'`, `showOverlays`).
- The label's frame number is `Math.floor(leader.currentTime * fps)`, computed in a rAF loop (**code** `SyncedVideoPlayer.tsx:377-403`, floor at 401).
- skellycam-ui seeks with `currentTime = frame / fps` (**code** `SyncedVideoPlayer.tsx:334-335, 506-507`).
- FreeMoCap's live ChArUco renderer draws an info panel with `fillRect(5, 5, 500, 85)` (**code** freemocap `freemocap-ui/src/services/server/server-helpers/image-overlay/charuco-overlay-renderer.ts:165`).
- That panel covers skellycam's stamp area (**inferred** from the two coordinate sets).
- FreeMoCap's live worker keeps only the latest overlay observation of each type and drops it after `OVERLAY_STALE_MS = 500`. Overlays are not matched to a frame number (**code** freemocap `offscreen-renderer.worker.ts:17,26-29,62-63,83`).
- FreeMoCap post-hoc burns skellytracker annotations into `annotated_videos/<stem>_annotated<source suffix>` (**code** freemocap `freemocap/core/pipeline/posthoc/video_node.py:211-219`).
- FreeMoCap already sends overlays to the UI as per-frame point blocks keyed by `frame_number`, as float32 or float64 (**code** freemocap `freemocap/api/websocket/binary_keypoints_protocol.py:15,58-64`).
- skellytracker's "Undetected Corners" list fits 35 lines at 720p and 53 at 1080p before it leaves the image:
  - this is code arithmetic, `(h-40)//20+1`, and it counts a baseline at y = H as fitting (**code** `S/label_layout.py:186`; result in `R/label_layout.json`);
  - the test data peaked at 9 lines (`max_undetected_in_a_frame`, **measured** `R/label_layout.json`).

### 2.2 Storage formats: size, write cost, crash modes

**Test data.** Synthetic, deterministic FreeMoCap-shaped overlays (`S/overlay_model.py` `make_frames`). Coordinates are pre-rounded to 0.01 px (**code** `S/overlay_model.py:62`). Every JSONL and WebVTT size assumes that precision.

The four cases (**code** `S/bench_overlay_cost.py:11-15`):
- `text`: today's stamp only;
- `skeleton`: stamp + 33-point body;
- `charuco`: stamp + 100 labelled corners + ArUco outlines + undetected list;
- `all`: skeleton + charuco.

**Software:** pure Python + numpy + msgspec 0.21.1 + cv2, with no PyAV import, so the PyAV version rule does not apply (**code** `S/bench_overlay_cost.py:1-7,50-55`; `S/formats_functional.py:15-25`).

**Write cost per frame, quiet run** (**measured** `B/bench_overlay_cost_20261110T103707Z.json`):
- How to read the numbers:
  - each value is the median of 3 per-rep medians, with the min-max of those medians, over 900 frames per rep;
  - each timed call is "generate the record + buffered append", with no flush or fsync per frame (**code** `S/bench_overlay_cost.py:16,118-121`);
  - every call ran in a process the runner pinned to the P-cores; the actual per-process affinity was not recorded (section 5).
- The four data sidecars, "all" overlay:

  | sidecar | 720p µs/frame | 1080p µs/frame |
  |---|---|---|
  | `.skov` (CRC per record) | 29.3 (29.1-29.5) | 29.1 |
  | MessagePack | 23.7 (23.2-24.4) | 24.0 |
  | JSONL | 125.4 (125.3-125.7) | 129.3 |
  | WebVTT | 128.3 (128.2-128.4) | 131.6 |

- Text only (today's stamp): 0.4-3.3 µs for every sidecar at both sizes.
- JSONL costs 4.3x `.skov` per frame for "all" at 720p: 125.4 / 29.3 (**arithmetic**).
- Each data sidecar costs at most 0.4% of a 33.3 ms (30 fps) frame period per stream: 131.6 / 33,333 µs (**arithmetic**).
- The render-level vector forms cost more ("all", 720p, same file):
  - single SVG: 653.4 µs (651.4-655.8);
  - SVG per frame: 934.9 µs (916.3-939.5);
  - ASS: 326.8 µs (325.5-331.8).
- Each `.skov` record is written as `_MAGIC + len + payload + crc32` (**code** `S/overlay_model.py:269,304`).

**Sizes, quiet run** (**measured** `B/bench_overlay_cost_20261110T103707Z.json`; identical in all 3 reps):
- "all" at 720p:
  - `.skov`: 3,282.9 B/frame = 354.55 MB/h at 30 fps;
  - JSONL: 5,697.7 B = 615.35 MB/h;
  - MessagePack: 6,890.3 B = 744.15 MB/h;
  - WebVTT: 5,731.5 B = 619.00 MB/h.
- These agree within 7 B/frame with the 300-frame functional run: `.skov` 3,287.6, JSONL 5,704.3, MessagePack 6,895.6 and WebVTT 5,735.6 B/frame (**measured** `R/formats_functional.json`). The likely cause is the header amortised over 900 vs 300 frames (**inferred**).
- JSONL is 1.74x `.skov` at 0.01 px precision: 5,697.7 / 3,282.9 = 1.736 (**arithmetic**).
- **The JSONL/`.skov` ratio depends on how many decimals the writer emits.**
  - With unrounded float32 coordinates, JSONL is 13,795.3 B/frame and WebVTT 13,826.6, which is 4.2x `.skov` (**measured** `R/verify_method_precision.json`).
  - `.skov` and MessagePack do not change size.
  - Compression was not tested.
- `.skov` is the smallest data form for skeleton, charuco and all. For text only, MessagePack is smallest: 31.8 B/frame, against 40.1 for `.skov` and 44.6 for JSONL (**measured** `B/bench_overlay_cost_20261110T103707Z.json`).
- Render-level forms, "all" at 720p (same file):
  - SVG per frame: 35,279.7 B = 3,810.21 MB/h;
  - single SVG: 35,156.6 B = 3,796.92 MB/h;
  - ASS: 17,053.1 B = 1,841.73 MB/h.
- 720p vs 1080p:
  - `.skov` and MessagePack sizes are identical at both resolutions;
  - the text formats grow 0-5.0% at 1080p, the largest being ASS skeleton at 2,757.1 vs 2,627.0 B (**measured**, same file; **arithmetic**);
  - the likely cause is longer coordinate strings at fixed 0.01 px precision (**inferred**).
- MessagePack is larger than JSONL in the point-heavy cases, probably because msgspec writes the float64 arrays as float64 (**inferred**, not tested). This does not hold for text.

**Crash and corruption modes** (functional tests on finished files; unchanged):
- Clean tail cuts (**code** `S/formats_functional.py:98-112`): JSONL, MessagePack, `.skov` and WebVTT each recovered every complete record and returned no corrupt record (**measured** `R/formats_functional.json`, `trunc_recovered_all_complete`, `trunc_errors: []`).
  - This held at 28/28 cuts, in every case and at both sizes.
- At one cut per text format, a cut just before a record's newline still returned that record intact (**measured**, `trunc_cuts_with_extra_record_before_newline: 1`).
- Other crash modes, 300 frames, 720p, "all" (**measured** `R/verify_method_crash_modes.json`):

  | mode | `.skov` | JSONL | MessagePack | WebVTT |
  |---|---|---|---|---|
  | cut + 64 KiB zero tail | 149 returned, 0 wrong | 149, 0 wrong | 149, 0 wrong | 149, 0 wrong |
  | 4 KiB zero hole mid-file | 298, 0 wrong | 299, 0 wrong | **149** (no resync after the hole) | 298, 0 wrong |
  | one byte changed in record 150 | 299, 0 wrong (CRC rejects it) | 300, **1 wrong returned silently** | 300, **1 wrong** | 300, **1 wrong** |

- Only `.skov` detected the corrupted record (**measured**, same file).
- The single SVG per recording fails a strict XML parse at 25/25 cuts. A lenient regex reader recovers 10-288 or 11-288 groups (**measured** `R/formats_functional.json`, `trunc_strict_parse_failures`, `trunc_lenient_groups_recovered_min_max`).
- SVG per frame: all 300/300 files parse independently (**measured**, same file). It was not cut-tested.
- In Chromium (E35 and E45), the full single SVG loads as `<img>`. Cut at 50%, it fires `error`, and `DOMParser` reports a parser error (**measured** `R/electron_*.json` → `trunc`).
- A WebVTT file cut at 50% still loads 150/300 cues in Chromium, but the last cue's JSON fails to parse (`lastCuePayloadParses: False`) (**measured**, same).

### 2.3 Chromium alignment: overlay vs video frame

**Setup and method:**
- Electron 35.7.5 (Chromium 134.0.6998.205) and 45.2.3 (Chromium 156.0.8078.80), scaleFactor 1 (**measured** `env` in `R/electron_*.json` and `B/electron_play_quiet_*.json`).
- Test clips: 300 C930e 720p frames, encoded with PyAV 18 at GOP 30 (**measured** `R/make_test_media.json`; **code** `S/make_test_media.py:88`). These are PyAV 18, GOP 30, background.
  - libx264 at crf 20, libvpx-vp9 at crf 32, libsvtav1 at crf 35.
- The reference frame in every rVFC and rAF check is the barcode read by `drawImage(video)` + `getImageData` inside that callback. It is not the frame on screen (**code** `H:194-205`, `H:218-225`).
- "Captures" are `webContents.capturePage` composites taken on every 10th rVFC callback (**code** `H:208-213`). They show compositor output, not necessarily scan-out.
- **Both runs carry heavy readback instrumentation:**
  - every callback does synchronous readbacks, and a parallel rAF loop reads back on every rAF tick (**code** `H:191-229`);
  - `noRaf` exists in the harness but cannot be set from the command line (**code** `H:229`; `S/electron_harness/main.js:18-25`).
- **Two runs exist**, and each config ran once per run:
  - the functional run of 2026-11-09, on a machine shared with other agents (`R/electron_*.json`, `R/electron_summary.md`);
  - the quiet run, items OV-PLAY-E35/E45, 2026-11-10 04:52-05:01, `load_over_15pct: false`, no Defender scan event, affinity `pcores` requested by the runner (**measured** `LOG` lines 67-68).
- **The two runs differ in more than load** (**measured**):
  - Chromium's GPU list included the Intel UHD 770 only in the quiet run (`env.gpuInfo.gpuDevice`);
  - the rAF loop ran 558-564 ticks per 300-frame 1x clip (279-280 at 2x) in the quiet run, against 597-604 (298-299) in the functional run (`results.play[*].raf`); that is about 56 vs about 60 ticks/s (**arithmetic**, 10.0 s clip);
  - so differences between the runs cannot be attributed to load, to the GPU set or to the rAF rate alone (**inferred**).

#### 2.3.1 Overlay lookup and today's rule during 1x play

- **rVFC lookup.** The overlay was looked up from `metadata.mediaTime` (the nearest entry in the per-frame pts table) and compared with the frame `drawImage` read in the same callback (**measured** `B/electron_play_quiet_*.json` → `results.play`; `R/electron_summary.md`):

  | Electron, run | CFR H.264 | CFR VP9 | CFR AV1 | VFR VP9 | VFR H.264 |
  |---|---|---|---|---|---|
  | 35, functional | 299/299 | 299/299 | 297/297 | 299/299 | 291/295 |
  | 35, quiet | 275/283 | 270/279 | 255/269 | 277/282 | 274/282 |
  | 45, functional | 299/299 | 299/299 | 296/296 | 282/287 | 290/292 |
  | 45, quiet | 280/280 | 279/279 | 278/278 | 253/256 | 258/261 |

- Every lookup mismatch in the quiet run had `drawImage` exactly one frame ahead of the lookup (`code − fi = +1`) (**measured**, same files, `overlayMismatch`).
  - The harness keeps the first 20 mismatches per run (**code** `H:201`). No run had more, so all of them were recorded.
- E35 matched less often in the quiet run than in the functional run, for example CFR AV1 255/269 vs 297/297 (**measured**). The runs differ in load, GPU set and rAF rate (2.3 setup), so the cause is not known. Only the direction (+1) is stable.
- **`round(mediaTime*30)`** equals the lookup on CFR files. On VFR files, in the quiet plain (non-composite) runs, it is right on only 125/256 to 139/282 callbacks; the composite VFR runs gave 145/286 (E35) and 134/269 (E45) (**measured** `naiveMatch`). The functional run showed the same pattern.
- **Today's UI rule, `floor(currentTime*30)` in rAF,** compared against the frame `drawImage` returned in the same rAF (**measured** `rafUiMatch`, `rafUiOffsets`):

  | quiet run | H.264 | VP9 | AV1 |
  |---|---|---|---|
  | E35, CFR | 501/558 | 481/560 | 491/556 |
  | E45, CFR | 293/559 | 280/559 | 296/555 |

  - VFR, both versions: 130/563 to 139/562.
  - Offsets below are `floor(currentTime*30)` minus the `drawImage` frame, so +1 means the rule names a frame one later than `drawImage` returned (**code** `H:224`).
- **This contradicts an earlier finding, which is removed.** The 2026-11-09 version said CFR mismatches were "all offset -1, except one +1". In the quiet run (**measured** `rafUiOffsets`):
  - E35 CFR mismatches were mostly +1 (52 vs 5, 59 vs 20, 53 vs 12);
  - E45 CFR had both -1 (148-156) and +1 (110-123).
- On VFR, the mismatches spread over -1, +1, +2 and +3 in all four quiet runs, for example E35 VFR VP9: -1 135, +1 153, +2 131, +3 4 (**measured**).
- **The rule's match rate varies between modes and between the two runs; repeatability under identical conditions was not measured. The counts cannot rank codecs or versions.** Same file (CFR VP9), same version, plain run vs canvas-composite run:
  - quiet run: E35 481/560 vs 490/560; E45 280/559 vs 393/560 (**measured**);
  - functional run: E35 289/598 vs 522/597; E45 58/599 vs 169/600 (**measured** `R/electron_*.json`).
  - In composite mode the `<video>` is invisible (opacity 0, **code** `H:183`), so the two modes are not identical configs.
- The rule's reference is `drawImage`, which can lead the screen (2.3.4). So the size of its offsets is not what the user sees (**inferred**). The VFR spread still shows that `floor(currentTime*fps)` is wrong for VFR (**inferred**).

#### 2.3.2 Canvas over `<video>` vs video drawn into the canvas

- **Separate overlay canvas over `<video>`, quiet run, 1x:** captures matched 51/275 in total (**measured** `B/electron_play_quiet_*.json` → `captureMatch`; **arithmetic** for the totals):
  - E35: 25/139 (12/28, 3/28, 2/27, 4/28, 4/28);
  - E45: 26/136 (14/28, 0/28, 2/28, 6/26, 4/26).
- **The overlay was 1-3 frames behind in all 224 mismatching captures:** 192 at +1, 28 at +2, 4 at +3 (video − overlay) (**measured** `captureMismatch`; the pairs are `[video, overlay]`, **code** `H:212`).
- **This changes an earlier finding.** The functional run had 3/30 to 19/30 matches, and every mismatch was exactly N-1 (**measured** `R/electron_summary.md` vs `B/electron_play_quiet_*.json`). The direction still holds; "always exactly one behind" does not.
- The readback instrumentation can delay the canvas commit, so how often the lag happens is still confounded (**inferred**). The quiet run used the same instrumented harness.
- **Video drawn into the overlay canvas,** quiet run (**measured** `@canvasComposite` rows):
  - method: `drawImage(video)` in rVFC, with the `<video>` set to opacity 0 (**code** `H:61`, `H:183`);
  - E35: captures matched 29/29 (CFR VP9) and 29/29 (VFR H.264);
  - E45: 27/27 and 26/27;
  - the functional run gave 29/29 to 30/30 (**measured** `R/electron_summary.md`).
- **What this capture check shows** (**code** `H:61`, `H:183`; **inferred**):
  - the captured video barcode and the overlay barcode come from the same canvas commit, so the check reduces to whether the composite's own `drawImage` agreed with the `mediaTime` lookup;
  - it shows that the overlay and the frame stay paired; it does not show that every frame is presented on time: the composite runs had 13-30 barcode skips per 300 frames (**measured** `barcodeSkips`).
- **The one composite mismatch** (E45, VFR H.264) was `[video 250, overlay 249]` (**measured** `B/electron_play_quiet_45.2.3.json` → `play['base_vfr_h264.mp4@canvasComposite'].captureMismatch`).
  - That run's 8 recorded lookup mismatches are at codes 33, 126, 169, 206, 226, 241, 263 and 271, not 250 (**measured**, `overlayMismatch`).
  - The composite canvas gets its own `drawImage(video)` (**code** `H:61`). This is separate from the barcode-reading `drawImage` that the lookup check uses (**code** `H:194`).
  - **Inferred:** the video advanced between the two `drawImage` calls. The composite stays paired only while its own `drawImage` returns the `metadata` frame, and the lookup check does not fully cover that.
- **At 2x (CFR VP9, canvas over `<video>`):**
  - quiet run: lookup matched 224/241 (E35) and 245/247 (E45), all mismatches +1; captures matched 0/24 and 0/25, with the overlay 1-3 behind (**measured** `@2x` rows);
  - functional run: lookup 169/241 and 269/281; captures 0/24 and 0/28 (**measured** `R/electron_summary.md`);
  - the composite path was run only at 1x (**code** `H:523`).
- **The rVFC spec allows a lag** (**source** https://wicg.github.io/video-rvfc/ §1 Introduction, accessed 2026-11-09):
  - "a callback can occasionally be fired one v-sync late, relative to when the new video frame was presented";
  - "drawing operations might occasionally appear on screen one v-sync after the video frame does".
- The spec defines `mediaTime` as "The media presentation timestamp (PTS) in seconds of the frame presented" (**source** https://wicg.github.io/video-rvfc/ §2.2, accessed 2026-11-09).

#### 2.3.3 Frames never seen by rVFC, and the drop counters

- **In every quiet 1x run, some frames never appeared in any rVFC callback** (barcode skips, **code** `H:203`; **measured** `barcodeSkips`):
  - E35: 13-30 of 300;
  - E45: 19-21 on CFR, 38-43 on VFR, and 30 in both composite runs;
  - for AV1, the two unreadable barcodes count as skips.
- **The two built-in counters** (**measured**):
  - `presentedFrames` gaps (**code** `H:206`);
  - `droppedVideoFrames`, read once at the end (**code** `H:236`).

  | run (1x, canvas over `<video>`) | barcode skips | `presentedFrames` gaps | `droppedVideoFrames` |
  |---|---|---|---|
  | E35 CFR H.264 / VP9 / AV1 | 16 / 20 / 30 | 16 / 20 / 28 | 0 / 0 / 0 |
  | E45 CFR H.264 / VP9 / AV1 | 19 / 20 / 21 | 0 / 0 / 0 | 19 / 20 / 19 |
  | E35 VFR VP9 / H.264 | 17 / 17 | 17 / 17 | 0 / 0 |
  | E45 VFR VP9 / H.264 | 43 / 38 | 43 / 38 | 0 / 0 |

- In E35, `presentedFrames` gaps matched the barcode skips in every 1x run (AV1 counting its 2 unreadable barcodes) (**measured**).
- In E45, `presentedFrames` gaps matched on the two VFR files but read 0 on the three CFR files, where `droppedVideoFrames` matched instead (**measured**). So in E45 the counter that moves depends on the file, not only on the version.
- In 13 of the 16 quiet play runs, the barcode skips equal `presentedFrames` gaps + `droppedVideoFrames`, counting AV1's 2 unreadable barcodes (**arithmetic** on the same files). In the other 3 (E45 2x and both E45 composite runs), the barcode count is 1-2 lower.
- Neither counter alone matched the barcode skips in every run (**measured**). Why E45 differs between the CFR and VFR files is NOT VERIFIED.
- The readback load may cause some of the skips (**inferred**). No run without the instrumentation was made.

#### 2.3.4 Paused seeks, dual video, last frame

- **Paused seeks:** how often the requested frame was shown (**measured** `B/electron_play_quiet_*.json` → `results.seek`; identical in `R/electron_summary.md`):

  | file | exact, E35 | exact, E45 | midpoint, E35 | midpoint, E45 |
  |---|---|---|---|---|
  | CFR H.264 | 80/80 | 80/80 | 80/80 | 80/80 |
  | CFR VP9 | 79/80 (f241→240) | 79/80 (f241→240) | 80/80 | 80/80 |
  | CFR AV1 | 78/79 (f241→240) | 78/79 (f241→240) | 79/79 | 79/79 |
  | VFR VP9 | 43/80 | 56/80 | 80/80 | 80/80 |
  | VFR H.264 | 42/80 | 80/80 | 76/80 | 79/80 |

- Every count in this table is the same in both runs (**measured**). Paused-seek behaviour was identical under two different conditions (load, GPU set, rAF rate; 2.3 setup).
- **The f241→240 misses are a timestamp-precision effect, not a GOP effect:**
  - the harness seeks to exactly `pts[f]` from the file's pts table (**code** `H:256`, `t = mode === 'exact' ? pts[f] : …`);
  - the two CFR WebM files have a 1 ms time base, and their table gives `pts[241] = 8.033`; the MP4 table gives 8.033333 (**measured** `<raw>/overlays/media/pts_base_cfr_{vp9,av1}.webm.json`, `pts_base_cfr_h264.mp4.json`);
  - 8.033 as a double truncates to 8,032,999 µs, 1 µs below the frame's 8,033,000 µs pts (**arithmetic**);
  - f241 is the only seek target in either CFR WebM file whose pts truncates below itself (targets from **code** `H:251-255`; other truncating frames 31, 123, 244, 246, 248 are not targets) (**arithmetic**), and it is the only CFR miss, in both files, both versions and both runs (**measured** `results.seek[*].modes.exact.mism`, `t: 8.033`);
  - the H.264 MP4, also GOP 30 with a keyframe at 240, hit f241 in 80/80 seeks (**measured**; keyframe position from the verifier's PyAV 19.0.2 demux, `R/VERIFY_method.md`);
  - **inferred:** Chromium converts the requested time to microseconds by truncation, so a seek 1 µs below a frame's pts shows the previous frame. That Chromium truncates rather than rounds is NOT VERIFIED from source. Midpoint seeks avoid it.
- The midpoint was not better everywhere: E45 VFR H.264 gave 80/80 at the exact pts but 79/80 at the midpoint (**measured**).
- In every paused case, the shown frame equalled the rVFC lookup: 80/80 or 79/79 (**measured** `lookupMatch`).
- Captures 100 ms after the seek matched in every case. Captures right after the seek matched as few as 58/80 (E35 VFR H.264, midpoint) (**measured** `capture100Match`, `captureMatch`).
- **Two `<video>` elements played together** (base + VP9-alpha layer; the CLI-encoded file, GOP 30, background):
  - capturePage composites matched 26/26 (E35) and 27/27 (E45) in the quiet run, and 25/25 and 27/27 in the functional run (**measured**);
  - `drawImage` reads of both, inside the base's rVFC, disagreed far more often (**measured** `results.alpha.dualVideoSync`; the offset is layer minus base, **code** `H:399`):
    - quiet run: layer ahead in 194/256 callbacks (E35: +1 186, +3 8) and 251/273 (E45: +1 240, +2 2, +3 9);
    - functional run: 136/250 and 195/271;
  - paused seeks of both elements: 30/30 on the requested frame in both runs (**measured**);
  - so `drawImage` can disagree with what the compositor shows (**inferred**).
- **Electron 35.7.5 last-frame bug** (functional run only; not re-run) (**measured** `R/electron_summary.md`, last-frame tables):
  - after a seek to the last frame (299), every later seek (150, 0, 299, duration, 75) still showed frame 299;
  - there was no rVFC callback, and `ended` stayed true;
  - this happened in all 5 files.
- **Electron 45.2.3 is not stuck, in 5/5 files** (**measured**, same):
  - the CFR files showed exactly 150, 0, 299, 299, 75;
  - each VFR file had one off-by-one result: VFR VP9 `75→74`, VFR H.264 `duration→298`.
- The AV1 test file has unreadable barcodes at frames 14 and 254 in both versions and both runs (**measured** `decodeFailAt`; `vfcDecodeFail: 2`).

### 2.4 WebVTT and subtitle tracks in Chromium

Method: `track.activeCues` is read inside rVFC and compared with the `drawImage` frame (**code** `H:319-336`). This tests the `activeCues` mechanism. It does not test WebVTT used as data, with cues looked up by rVFC `mediaTime`.

- **Cue == frame during play** (offsets are cue − frame, **code** `H:336`):

  | case | E35 functional | E35 quiet (offsets) | E45 functional | E45 quiet (offsets) |
  |---|---|---|---|---|
  | CFR | 148/299 | 257/281 (-1: 13, +1: 11) | 8/299 | 143/278 (-2: 3, -1: 116, +1: 16) |
  | CFR, cues shifted half a frame earlier | 207/299 | 197/289 (-1: 3, +1: 88) | 18/298 | 143/279 (-1: 57, +1: 78) |
  | VFR, cue times = container pts | 95/285 | 70/285 (-1: 215) | 32/286 | 97/287 (-1: 188, +1: 2) |

  Sources: **measured** `R/electron_summary.md` and `B/electron_play_quiet_*.json` → `results.vtt`.
- **An earlier wording is removed.** The 2026-11-09 version said the CFR mismatches were "all the rest offset -1". The quiet run also shows +1 offsets: 11 of 24 in E35 and 16 of 135 in E45 (**measured**).
- Play-time `activeCues` matching is wrong in both directions and its rate varies between the two runs; the runs differ in load, GPU set and rAF rate, so the cause is not attributable (**inferred**).
- **Paused seeks** (**measured**):
  - CFR: 40/40 in both versions and both runs;
  - half-shift: 39/40 (quiet run);
  - VFR: 30/40 (E35) and 32/40 (E45) in both runs.
- The VFR seek misses are the video missing the requested frame while the cue is right, for example `{"f": 79, "code": 78, "cue": 79}` (**measured** `results.vtt.vfr.seek.mismatch`).
- **In-band tracks:** WebVTT muxed into WebM and ASS muxed into MKV both load, but expose `textTracks.length` 0 in both versions (**measured** `R/electron_summary.md`, functional run).
- `canPlayType('video/x-matroska')` is `''` in E35 and `'maybe'` in E45 (**measured**, same).
- WebVTT timestamps have millisecond resolution: "Three ASCII digits, representing the thousandths of a second seconds-frac as a base ten integer" (**source** https://www.w3.org/TR/webvtt1/ §4.1, accessed 2026-11-09).
- On metadata cues (**source** same URL, accessed 2026-11-09):
  - "WebVTT metadata text cues are only useful for scripted applications" (§4.2.1);
  - "Metadata can be any string and is often provided as a JSON construct" (§1.7).
- **ASS timing is in centiseconds.**
  - FFmpeg's ASS demuxer computes `*start = (hh1*3600LL + mm1*60LL + ss1) * 100LL + ms1;` and calls `avpriv_set_pts_info(st, 64, 1, 100);` (**source** https://raw.githubusercontent.com/FFmpeg/FFmpeg/n8.0/libavformat/assdec.c lines 72 and 118, fetched 2026-11-09; re-fetched by the provenance verifier 2026-11-10).
  - Whether the PyAV 19.0.2 build matches is NOT VERIFIED. The point is moot for PyAV, which has no `ass` filter (2.7).
- ASS muxed into MKV produced 30,898 packets for 300 frames. The 6 packets kept in the record (`first6`) are each 0.03 s long (**measured, ffmpeg CLI, background** `R/make_test_media.json` → `ass_mkv_packets`).

### 2.5 Alpha video overlay layer

**Size (both layers GOP 30, background; no intra-only alpha layer was measured):**
- VP9-alpha WebM: 80,251 B/frame (**measured, ffmpeg CLI, background** `R/make_test_media.json`).
  - Settings: libvpx-vp9, yuva420p, crf 32, realtime, cpu-used 8, g 30, 300 frames, "all" at 720p.
- PNG-in-MOV: 155,859 B/frame. QTRLE-in-MOV: 290,996 B/frame (**measured, ffmpeg CLI, background**, same).
- PyAV 19.0.2 with the same options at 60 frames: 64,006 B/frame (**measured** `R/pyav19_functional_check.json` → `alpha`). The frame counts differ, so this is not like-for-like.
- So the GOP-30 alpha layer is 19.5x (PyAV 19, 60 frames) to 24.4x (CLI, 300 frames) the `.skov` size (900 frames) (**arithmetic**).
  - This holds only for this setting and this synthetic content, which moves every frame (**code** `S/make_test_media.py:186-187`, `S/pyav19_functional_check.py:182`).
  - An intra-only alpha layer, which requirement 8 would need, was not tested and is probably larger (**inferred**).
- The camera's own JPEG for this frame set: median 56,759 B (min 51,085, max 65,760) over 891 frames (**measured** `<raw>/corpus/index.json` → `c930e_720p_flash.bytes_median`, `frames`).

**Rasterisation cost, quiet run** (**measured** `B/bench_overlay_cost_20261110T103707Z.json`, `alpha_render`; µs/frame):

| size | text | skeleton | charuco | all |
|---|---|---|---|---|
| 720p | 34,674.8 (34,638.9-34,866.6) | 35,229.7 | 68,145.7 | 68,229.8 |
| 1080p | 79,194.2 | 80,109.0 | 113,016.3 | 113,110.0 |

- Every case exceeds the 33.3 ms frame period at 30 fps, before any VP9 encode (**arithmetic**).
- This is one implementation: two full-frame cv2 renders (on black and on white) plus a numpy difference matte (**code** `S/overlay_model.py:621-631`). A faster renderer was not tested, so this cost is not a lower bound (**inferred**).
- The VP9 pipeline row (`alpha_vp9_pipeline`) pipes to the ffmpeg CLI and was left out of the queue (**code** `S/bench_overlay_cost.py:5-7,176-191`; `args.only` in the `B/` JSON).

**Chromium:**
- The CLI-encoded VP9-alpha WebM loads in Chromium 134 and 156 (**measured, CLI-encoded file, background** `R/electron_summary.md`; `B/electron_play_quiet_*.json` → `results.alpha`).
  - In frame 0, alpha < 8 on 0.8746 of the pixels and alpha > 247 on 0.1135, in both runs.
- PNG-MOV and QTRLE-MOV fail with `DEMUXER_ERROR_NO_SUPPORTED_STREAMS` in both versions (**measured** `R/electron_summary.md`).
- The PyAV-19-encoded alpha file was not loaded in Chromium.

**Truncation:**
- After a 50% cut, the CLI VP9-alpha file still decoded 160 frames, all with transparency. PNG-MOV and QTRLE-MOV decoded 0 frames (**measured, ffmpeg CLI, background** `R/alpha_truncation.json`).
- The MOV files were written without `movflags` (**code** `S/make_test_media.py`, no `movflags`). So the 0-frame result applies to non-fragmented MOV with the moov atom at the end, not to the codecs (**inferred**).
- PyAV 19.0.2: a 50% cut of the PyAV-19-encoded file, decoded with `libvpx-vp9`, gave 30 frames, all with transparency, and no errors (**measured** `R/pyav19_functional_check.json` → `alpha.trunc50`).
- All cuts were of finished files, not files from a killed writer.

**Decoding alpha in PyAV 19.0.2:**
- **Only the `libvpx-vp9` decoder keeps alpha** (**measured** `R/pyav19_functional_check.json` → `alpha`):
  - the stream reports `yuv420p` with `alpha_mode: 1`;
  - FFmpeg's native `vp9` decoder returns `yuv420p` frames and drops alpha;
  - `av.CodecContext.create("libvpx-vp9", "r")` returns `yuva420p` on 60/60 frames.
- With that decoder (**measured**, same, `libvpx_decoder`):
  - the maximum per-frame mean absolute alpha difference from the source matte is 0.4572 of 255;
  - the overlay barcode reads correctly in 60/60 frames;
  - frame 0 has exact-zero alpha on 0.8463 of its pixels, against 0.873 in the matte.
- The earlier CLI decode gave a frame-0 mean absolute alpha difference of 0.114 (**measured, ffmpeg CLI, background** `R/make_test_media.json` → `vp9alpha_decode_check`).
- The CLI's zero fraction used a `< 8` threshold (**code** `S/make_test_media.py:205`), so it is not comparable with the exact-zero figure.

### 2.6 Burn-in cost at record time

All from **measured** `B/bench_overlay_cost_20261110T103707Z.json`. Single-threaded Python, in a process the runner pinned to the P-cores (actual affinity not recorded; section 5). OpenCV's internal thread count is its default and is not recorded (**code** `S/bench_overlay_cost.py`, which never calls `cv2.setNumThreads`).

- **cv2 burn-in on a decoded frame** (the frame copy is outside the timer, **code** `:151`):

  | size | text | skeleton | charuco | all |
  |---|---|---|---|---|
  | 720p | 89.1 µs (88.5-89.6) | 197.4 µs | 16,514.5 µs (16,500.1-16,603.9) | 16,646.6 µs |
  | 1080p | 90.1 µs | 218.1 µs | 16,539.2 µs | 16,724.6 µs |

- ChArUco/all burn-in takes 49.5-50.2% of a 33.3 ms frame period per stream (**arithmetic**).
- The cost follows the label count, not the resolution: charuco has 100 labelled corners drawn as outlined `LINE_AA` text (**code** `S/overlay_model.py:612-618`; **inferred**).
- **Burn-in into passthrough JPEGs,** timed as imdecode + burn-in + imencode q90 (**code** `:160-163`):

  | size | text | skeleton | charuco | all | decode + re-encode only, no drawing |
  |---|---|---|---|---|---|
  | 720p | 3,426.9 µs | 3,580.4 | 20,294.9 | 20,370.0 (20,360.5-20,475.5) | 3,315.3 |
  | 1080p | 7,683.8 | 7,884.5 | 24,686.8 | 24,932.4 (24,836.2-24,956.8) | 7,527.4 |

- **Corpus caveat:** the input JPEGs are looped to 900 frames: 891 distinct frames at 720p, but only 19 at 1080p (**measured** `<raw>/corpus/index.json` → `c930e_1080p.frames = 19`; **code** `S/bench_overlay_cost.py:160`, `jpeg_bytes[i % len(jpeg_bytes)]`). JPEG decode/encode cost and size depend on content, so the 1080p JPEG numbers rest on 19 images.
- **Once frames pass through as camera JPEGs (G1), even today's text stamp needs that decode + re-encode** (**measured**):
  - 3.43 ms per frame at 720p and 7.68 ms at 1080p;
  - against 89-90 µs on an already decoded frame;
  - **inferred:** with G1 passthrough there is no decoded frame to draw on.
- **Size of the cv2 q90 re-encode vs the camera JPEG** (**measured** `out_jpeg_bytes_per_frame`, `camera_jpeg_bytes_per_frame` = mean over the 900 looped input frames, **code** `:167-168`; **arithmetic**):
  - 720p: text 61,192 B vs the camera's 55,379 B (1.10x); all 167,033 B (3.02x);
  - 1080p: text 138,934 B vs 134,592 B (1.03x); all 299,194 B (2.22x).
  - This is not at matched quality (the camera JPEG quality is unknown; q90 is at neither A nor B). `jpeg_roundtrip_only` records no output size (**code** `:190-200`), so the re-encode's share of the growth and the overlay's share cannot be separated.
- Quality: this is a q90 re-encode of an already decoded camera JPEG, so it is a second lossy generation (**code** `:163`; **inferred**). Its quality against target A or B was not measured.

### 2.7 Export with overlays burned in

- **P1: sidecar → cv2 burn-in → encode, 300 frames** (**measured, PyAV 18, background** `R/export_burnin.json`):
  - libvpx-vp9 WebM: 300/300 aligned (15,215,723 B);
  - libx264 MP4: 300/300 aligned (11,827,653 B);
  - "aligned" means the source-frame barcode equals the overlay-frame barcode in each decoded output frame.
- **PyAV 19.0.2 P1 at 60 frames** (**measured** `R/pyav19_functional_check.json` → `p1`):
  - the `.skov` sidecar read back 60 frames with 0 bad;
  - libvpx-vp9 WebM 60/60 and libx264 MP4 60/60 aligned, with 0 decode failures;
  - the script picks the sidecar record by loop index (**code** `S/pyav19_functional_check.py:122,133`). So this shows no drop or reorder through encode/decode. It does not show sidecar-to-video pairing when the camera drops frames.
- **P2: ffmpeg `overlay` filter, with the alpha layer decoded by `-c:v libvpx-vp9`:** 300/300 aligned (**measured, ffmpeg CLI, background** `R/export_burnin.json`).
- **P2b: the same with the default vp9 decoder:** 1/300. The base barcode read as 0 while the overlay read correctly (**measured**, same). That the layer came out opaque is **inferred** from this.
- **PyAV 19.0.2 P2 inside Python** (**measured** `R/pyav19_functional_check.json` → `p2`):
  - filter graph: `overlay` with `x=0:y=0:eof_action=pass:format=yuv420`;
  - layer decoded by `libvpx-vp9` (`yuva420p`): 60/60 aligned;
  - layer from the default decoder (`yuv420p`): 1/60, with the base barcode read as 0;
  - the base input `base_cfr_vp9.webm` was encoded with PyAV 18 (background). PyAV 19 did the decode, filter and encode;
  - the script sets `fb.pts = fl.pts = i` (**code** `S/pyav19_functional_check.py:249`). So this tests alpha compositing, not timestamp pairing of two demuxed files.
- **P3: libass burn-in with per-frame events at centisecond times:** 200/300 aligned, with every third frame showing the previous event. **P3b**, with events shifted half a frame earlier: 300/300 (**measured, ffmpeg CLI, background** `R/export_burnin.json`).
- **The PyAV 19.0.2 wheel has no `ass`, `subtitles` or `drawtext` filter** (**measured** `R/pyav19_functional_check.json` → `caps`; re-confirmed in `R/VERIFY_provenance.prev.md`). It does have:
  - the filters `overlay`, `alphamerge`, `alphaextract` and `drawbox`;
  - the libvpx-vp9 encoder and decoder, the libx264 and libsvtav1 encoders, and the libdav1d decoder;
  - the png, qtrle, webvtt and ass codecs;
  - the webm, matroska, mp4, mov, webvtt and ass muxers.
- **WebCodecs `isConfigSupported` at 1920x1080,** identical in E35 and E45 (**measured** `R/electron_summary.md`; functional run, with the Intel iGPU absent from Chromium's GPU list):
  - hardware encode: H.264 and HEVC true; VP8, VP9 and AV1 false;
  - software encode: VP8, VP9, AV1 and H.264 true; HEVC false;
  - hardware decode: VP9, AV1, H.264 and HEVC true.
  - This is a capability query, not an encode test. It was not repeated in the quiet run, which ran only `play,seek,vtt,alpha` (`B/electron_play_quiet_*.json` → `tests`).

### 2.8 UI draw cost and label placement

**UI draw cost of the full overlay** (1280x720; 300 frames × 5 reps pooled = 1500 calls; one process per version, single run) (**measured** `B/electron_drawbench_35.7.5.json`, `B/electron_drawbench_45.2.3.json` → `results.drawbench`):

| mode | E35 median / p95 / max (ms) | E45 median / p95 / max (ms) |
|---|---|---|
| canvas, placed labels | 1.1 / 1.3 / 84.5 | 0.9 / 1.1 / 112.9 |
| canvas, naive labels | 1.0 / 1.2 / 1.9 | 0.8 / 0.9 / 1.4 |
| canvas, no labels | 0.9 / 1.0 / 1.3 | 0.6 / 0.7 / 1.0 |
| SVG DOM `innerHTML` + wait for next rAF | 18.0 / 18.2 / not recorded | 18.0 / 18.1 / not recorded |

- Canvas times include `getImageData(0,0,1,1)` to force the draw to complete.
- `performance.now()` values in these files are quantised to 0.1 ms (**measured**, field values such as 1.1000000014901161; `R/BENCH.md` §3).
- The E35 vs E45 differences are 1-3 quanta of 0.1 ms from a single run each; they are not shown to be significant and do not rank the versions (**inferred**).
- The SVG figure includes the wait for the next rAF. The file's own `note` says: "includes waiting for the next rAF (~16.7 ms at 60 Hz floor)" (**measured**, field `note`). So the SVG draw cost alone cannot be separated.
- Canvas draw with placed labels takes at most 1.1 ms median, about 7% of a 16.7 ms frame (**arithmetic**). The 16.7 ms (60 Hz) frame is an assumption: the display refresh rate was not recorded (NOT VERIFIED; section 6).
- The single 84.5 / 112.9 ms max of the placed-label mode is probably a first-call cost (**inferred**):
  - the layout keeps a `measureCache` (**code** `H:58`);
  - the other canvas modes have no such outlier.

**Deterministic label placement** (functional; unchanged):
- The placer is greedy: 8 directions x 3 rings, then side lanes with leader lines, then hide and count.
- It exists in Python (`S/label_layout.py`) and in JS (`S/electron_harness/layout.js`).
- Overlap counts for 60 frames and 5,691 labels (**measured** `R/label_layout.json`):

  | case | skellytracker `Corner#id` (label-label / label-marker) | freemocap-ui id | placed |
  |---|---|---|---|
  | 720p, board 55% of height | 12,272 / 13,397 | 0 / 332 | 0 / 0 |
  | 1080p, board 55% | 9,706 / 10,657 | 116 / 1,450 | 0 / 0 |
  | 720p, board 20% (dense) | 68,733 / 57,092 | 7,223 / 21,957 | 0 / 0 |

- In the dense case (**measured**, same):
  - 1,474 labels went to side lanes and 0 were hidden;
  - two runs were identical (`deterministic: true`);
  - 0 HUD panel pairs overlapped.
- In the browser (12 px Arial, both versions), naive +8/-8 placement gave 11 label-label and 322 label-marker overlaps. `placeLabels` gave 0 and 0, deterministically (**measured** `R/electron_summary.md`, layout table).
- Leader-line crossings are not checked. They are visible in `<raw>/overlays/layout/C_placed_720p_board20.png` (**measured**, image; investigator observation).

## 3. Comparison tables

### 3.1 Overlay storage options (720p, full "all" overlay)

Write cost: median of 3 rep medians (min-max), µs/frame, quiet run. Sizes: quiet run, 900 frames, unless marked otherwise.

| option | write µs/frame | B/frame | MB/h @30 fps | crash / corruption behaviour | Chromium | PyAV 19.0.2 path | evidence |
|---|---|---|---|---|---|---|---|
| `.skov` binary, CRC per record | 29.3 (29.1-29.5) | 3,282.9 | 354.55 | 28/28 clean cuts; resyncs after a zero hole; **rejects a corrupted record** | n/a (UI renders data) | pure Python, no PyAV | `B/bench_overlay_cost_20261110T103707Z.json`, `R/formats_functional.json`, `R/verify_method_crash_modes.json` |
| JSONL (0.01 px) | 125.4 (125.3-125.7) | 5,697.7 (13,795.3 as float32 repr, functional) | 615.35 | 28/28 clean cuts; resyncs; returns a corrupted record silently | n/a | pure Python | same + `R/verify_method_precision.json` |
| MessagePack (float64) | 23.7 (23.2-24.4) | 6,890.3 | 744.15 | 28/28 clean cuts; **stops at a zero hole** (149/300); returns a corrupted record silently | n/a | pure Python + msgspec | same |
| WebVTT metadata cues (0.01 px) | 128.3 (128.2-128.4) | 5,731.5 | 619.00 | as JSONL; Chromium loads 150/300 cues from a 50% cut, last cue torn | as `<track>`; `activeCues` off by ±1 in play (2.4) | pure Python | same + `R/electron_*.json` |
| ASS | 326.8 (325.5-331.8) | 17,053.1 | 1,841.73 | not tested | no text track exposed | no libass filter in the wheel | `B/` JSON, `R/pyav19_functional_check.json` |
| SVG per frame | 934.9 (916.3-939.5) | 35,279.7 | 3,810.21 | not cut-tested; 300/300 files parse independently | not rendered in test | pure Python | `B/` JSON, `R/formats_functional.json` |
| one SVG per recording | 653.4 (651.4-655.8) | 35,156.6 | 3,796.92 | strict parse fails 25/25 cuts | 50% cut fires `img` error | pure Python | same + `R/electron_*.json` |
| VP9-alpha WebM (GOP 30, background) | rasterising alone 68,229.8 (68,171.3-68,274.7); encode not timed | 80,251 (CLI, 300 fr); 64,006 (PyAV 19, 60 fr) | 8,667 (CLI) | one 50% cut: 160 frames (CLI); 30/30 transparent (PyAV 19) | yes, with alpha (CLI file, background) | encode yes; decode only with `libvpx-vp9` | `B/` JSON `alpha_render`, `R/make_test_media.json`, `R/alpha_truncation.json`, `R/pyav19_functional_check.json` |
| PNG-in-MOV / QTRLE-in-MOV | not timed | 155,859 / 290,996 | 16,833 / 31,428 | 0 frames from a 50% cut (non-fragmented MOV) | no (`DEMUXER_ERROR_NO_SUPPORTED_STREAMS`) | not tested | `R/make_test_media.json`, `R/alpha_truncation.json` |

The VP9-alpha and MOV MB/h values are **arithmetic** (B/frame × 108,000 / 1e6). An intra-only alpha layer was not measured.

### 3.2 Record-time cost: separate layer vs burn-in (µs/frame, quiet run, single thread)

| method | 720p text | 720p all | 1080p text | 1080p all | share of 33.3 ms at "all" |
|---|---|---|---|---|---|
| `.skov` sidecar | 0.8 | 29.3 | 0.8 | 29.1 | 0.09% |
| JSONL sidecar | 1.6 | 125.4 | 1.6 | 129.3 | 0.39% |
| cv2 burn-in on a decoded frame | 89.1 | 16,646.6 | 90.1 | 16,724.6 | 50% |
| burn-in into camera JPEG (decode + draw + q90 encode) | 3,426.9 | 20,370.0 | 7,683.8 | 24,932.4 | 61-75% |
| JPEG decode + q90 encode only | 3,315.3 | (same) | 7,527.4 | (same) | 10-23% |
| alpha rasterisation (before encode) | 34,674.8 | 68,229.8 | 79,194.2 | 113,110.0 | 205-339% |

Source: **measured** `B/bench_overlay_cost_20261110T103707Z.json`. Last column: **arithmetic** (median / 33,333 µs). The 1080p JPEG rows use 19 distinct input frames looped to 900 (2.6). All are costs for a thread in a process pinned to the P-cores; an E-core thread was not measured.

### 3.3 Chromium overlay-sync methods (one run per config; both runs instrumented)

| method | 1x: frame named == `drawImage` frame (functional / quiet) | capturePage: overlay == video (functional / quiet) | VFR | evidence |
|---|---|---|---|---|
| today's `floor(currentTime*fps)` in rAF | 13/596-464/595 / 130/563-501/558 | not captured | wrong on CFR and VFR; offsets -1 to +3; varies between modes and runs | `R/electron_*.json`, `B/electron_play_quiet_*.json` |
| rVFC `mediaTime` → pts table, canvas over `<video>` | 282/287-299/299 / 255/269-280/280; misses always `drawImage` +1 | 3/30-19/30 (all N-1) / 0/28-14/28 (overlay 1-3 behind) | works with the pts table | same |
| rVFC + video drawn into the overlay canvas | 287/287-299/299 / 261/269-286/286 | 29/29-30/30 / 26/27-29/29 (one +1); shows pairing, not on-time presentation | works with the pts table | same |
| WebVTT metadata `activeCues` (1x column: CFR, unshifted cues) | 8/299-148/299 / 143/278-257/281 | n/a | 32/286-95/285 / 70/285-97/287 | same |
| second `<video>` with a VP9-alpha layer | `drawImage` layer ahead in 136/250, 195/271 / 194/256, 251/273 | 25/25, 27/27 / 26/26, 27/27 | not tested | same |

The functional and quiet runs differ in load, Chromium's GPU list and rAF rate (2.3 setup).

### 3.4 Electron 35.7.5 vs 45.2.3 (overlay-relevant differences only)

| item | 35.7.5 | 45.2.3 | evidence |
|---|---|---|---|
| seek after reaching the last frame | stuck on the last frame, 5/5 files | not stuck, 5/5; CFR exact; one off-by-one per VFR file | `R/electron_summary.md` |
| VFR H.264 exact-pts paused seek (both runs) | 42/80 | 80/80 | `R/electron_summary.md`, `B/electron_play_quiet_*.json` |
| drop counter that matches the barcode skips at 1x | `presentedFrames` gaps, every file | `droppedVideoFrames` on CFR; `presentedFrames` gaps on VFR | `B/electron_play_quiet_*.json` |
| canvas draw, placed labels (median; single run, difference not shown significant) | 1.1 ms | 0.9 ms | `B/electron_drawbench_*.json` |
| `canPlayType('video/x-matroska')` | `''` | `'maybe'` | `R/electron_summary.md` |
| 2x CFR VP9 rVFC lookup == `drawImage` (functional / quiet) | 169/241 / 224/241 | 269/281 / 245/247 | `R/electron_summary.md`, `B/electron_play_quiet_*.json` |
| in-band WebVTT/ASS text tracks | 0 | 0 | `R/electron_summary.md` |

## 4. Implications for the plan

All bullets are **inferred** from the findings cited.

- **Record overlays as an append-only data sidecar keyed by frame number and timestamp. Never burn them in at record time.**
  - A data sidecar costs at most 131.6 µs per frame for the full overlay and at most 3.3 µs for today's stamp (2.2, 3.2).
  - Burning in ChArUco/all costs about half of a 30 fps frame period per stream (2.6).
  - With G1 passthrough, even today's text stamp forces a JPEG decode + re-encode (2.6):
    - it costs 3.4-7.7 ms per frame;
    - the cv2 q90 re-encode is 1.03-1.10x the camera JPEG size for the text stamp, not at matched quality, and the overlay's share of that growth was not measured;
    - it breaks byte-exact passthrough.
  - A sidecar also removes skellycam's burned stamp, which today cannot be removed after recording (2.1).
- **Prefer a CRC-framed binary sidecar (`.skov`-style) over JSONL.**
  - It is 1.74x smaller than JSONL at 0.01 px precision, and 4.2x smaller than JSON with unrounded float32 values (2.2).
  - It is 4.3x cheaper to write per frame: 29.3 vs 125.4 µs for "all" at 720p (2.2).
  - It is the only format tested that rejected a corrupted record (2.2).
  - JSONL stays readable without a custom reader. A JSONL with a CRC per line was not tested.
- **Do not use length-prefixed MessagePack without a resync marker,** even though it is the fastest to write (23.7 µs). After a 4 KiB zero hole it lost every later record (2.2).
- **Do not use SVG or ASS as the recorded format.**
  - For "all", they are 5-11x the `.skov` size and cost 11-32x as much per frame (2.2, 3.1).
  - A single SVG fails strict parsing at every cut, and Chromium rejects a truncated copy (2.2).
- **Drop the alpha video layer as a record-time option. Keep it only as an export or interchange path.**
  - In this implementation, rasterising the layer alone already exceeds the 30 fps frame period in every case (34.7-113.1 ms), before any encode (2.5).
  - The GOP-30 (background) layer is 19.5-24.4x the `.skov` size; an intra-only layer was not measured and is probably larger (2.5).
  - Python readers must decode it with `libvpx-vp9` (2.5).
- **Drive UI overlays from rVFC `metadata.mediaTime` mapped through the file's per-frame pts table, not from `floor(currentTime*fps)`.**
  - Across both runs, the lookup matched the `drawImage` frame in 255/269 to 299/299 callbacks at 1x. Every miss was `drawImage` one frame ahead (2.3.1).
  - Today's rule misses in both directions on CFR and VFR, and its rate varies between modes and runs (2.3.1).
- **When the overlay must stay paired with the frame, draw the video into the overlay canvas. Do not layer a separate canvas over `<video>`.**
  - Canvas over `<video>` matched only 51/275 quiet-run captures at 1x, with the overlay 1-3 frames behind (2.3.2).
  - The single canvas matched 111/112 quiet-run captures across both versions (2.3.2; **arithmetic** 29+29+27+26 of 29+29+27+27). This check shows the overlay and the frame stay paired in one commit; it does not show on-time presentation (those runs skipped 13-30 of 300 frames).
  - Draw both the frame and the overlay from the same `drawImage` result. The one composite mismatch is consistent with the frame advancing between two `drawImage` calls (2.3.2).
  - Pairing above 1x is unproven, because the composite path ran only at 1x (2.3.2).
  - WebCodecs `VideoFrame` timestamps would remove the `drawImage` question, but were not tested here (section 6).
- **Render UI overlays on canvas, not as SVG DOM.** The full overlay with placed labels draws in 0.9-1.1 ms median per frame. SVG DOM replacement took 18.0 ms including the rAF wait (2.8). The cost for many tiles was not tested (section 6).
- **Do not use `presentedFrames` or `droppedVideoFrames` alone to detect skipped frames in the UI.**
  - Neither matched the barcode skips in every run: in E45 the counter that moved depended on the file (CFR vs VFR) (2.3.3).
  - A version-independent alternative is to count jumps in the pts-table index derived from rVFC `mediaTime` (**inferred**, not tested).
- **Seek to the midpoint between frames, and confirm the shown frame from rVFC `mediaTime`.**
  - Exact-pts seeks missed often on VFR, and missed f241 on the two 1-ms-time-base CFR WebM files, where the requested time truncates 1 µs below the frame's pts. The midpoint was right in 76/80 to 80/80 (2.3.4).
  - The rVFC lookup equalled the shown frame in every paused case, in both runs (2.3.4).
  - skellycam-ui seeks to the exact `frame/fps` today (2.1), which can land just below a frame's pts in the same way.
- **Upgrade Electron 35.7.5 → 45.x, or never seek to a video's last frame.** E35 locks up after a last-frame seek in all 5 files. Workarounds were not tested (2.3.4, 3.4).
- **Do not drive overlays from `track.activeCues` or in-band subtitle streams.**
  - During play, `activeCues` was off by ±1 frame, and how often varied between the two runs (2.4).
  - In-band tracks are not exposed (2.4).
  - WebVTT read as data and looked up by rVFC `mediaTime` is not ruled out, but it was not tested and it has no corruption detection (2.2).
- **Export with burned-in overlays can stay in Python on PyAV 19.0.2.**
  - Two paths work (2.7):
    - sidecar → cv2 burn-in → libvpx-vp9 or libx264;
    - the PyAV `overlay` filter with a VP9-alpha layer decoded by `libvpx-vp9`.
  - Both were shown working for encode and compositing only, with frames paired by index (2.7).
  - libass burn-in needs the ffmpeg CLI, because the wheel lacks `ass` and `subtitles` (2.7).
  - The burn-in dominates export cost: about 16.5 ms per frame on one thread for ChArUco/all (2.6). So export is an offline job.
  - Codec licensing belongs to the licensing topic and is not asserted here.
- **Lay out labels at render time with the deterministic placer, and do not store the layout.** The placer removed every overlap in Python and JS (2.8).
- **Re-check before relying on browser-side export (canvas → WebCodecs).** `isConfigSupported` reported no hardware VP9/AV1 encode, but only as a capability query made with the iGPU absent (2.7).

## 5. Run flags and caveats that apply to this topic

From `results/BENCH_RUN_2300_SUMMARY.md` §3, the run log `LOG`, and `R/BENCH.md` §1 and §6:
- **P-cores requested, actual affinity not recorded.** The runner set affinity `pcores` (8 P-cores, 16 logical CPUs) for every OV item (**measured** `LOG` lines 38-40, 67-68 and 73, `"affinity": "pcores"`; also `bench_queue_2300.json` and `queue_ovcost_rerun.json`).
  - No OV-COST or Electron JSON records the process affinity during the item, including Electron's GPU and renderer processes. Run flag 2 (libx265) shows that a process can widen its own affinity, so P-core-only execution is requested, not measured.
  - The per-call costs are for a P-core-pinned thread. An unpinned recorder thread landing on an E-core was not measured.
  - The OV-COST JSON records `cpu_count: 28`. That is `os.cpu_count()`, which ignores affinity (**code** `S/bench_overlay_cost.py:91`).
- **OV-COST timed out once,** at the 1800 s hard timeout, and wrote no JSON (**measured** `LOG` line 38, flag "hard timeout 1800 s: process tree killed").
  - It had finished 7 of its 8 blocks: the stdout log has 7 "done" lines and no "1920x1080 all" (**measured** `results/bench_runner/logs/20261109T230007/36_OV-COST.out.txt`).
  - The only result is from the re-run: 05:37-06:13, 60-min timeout, status ok (**measured** `LOG` line 73).
  - The OV-COST estimate (12 min) and timeout (30 min) in `make_queue.py` still need raising.
- **No item was load-flagged, and no Defender scan event was logged,** for any OV item: `load_over_15pct: false` and `defender_scan_events_during_item: ""` (**measured** `LOG` lines 38, 39, 40, 67, 68 and 73).
- **Defender real-time scanning was on, and its cost is part of the result.**
  - MsMpEng used 79.36 CPU-s during the OV-COST re-run and 125.08 CPU-s during the attempt that timed out (**measured** `LOG` line 73 and line 38, `msmpeng_cpu_s_during_item`).
  - OV-COST does not split Defender time per method.
  - SVG per frame writes one file per frame (**code** `S/overlay_model.py:451`, `S/bench_overlay_cost.py:132-146`). Its cost is 163.8-950.6 µs per frame across both sizes (**measured** `B/bench_overlay_cost_20261110T103707Z.json`, text 1080p to all 1080p). The folder-of-files Defender cost found in write_throughput probably inflates it (**inferred**).
- **Per-call tails** (**measured** `B/bench_overlay_cost_20261110T103707Z.json`):
  - 11 rep records of methods with a median under 200 µs had a single call over 1 ms, up to 1,877.4 µs (JSONL, charuco, 1080p);
  - `svg_single` "all" had single calls of 16,963.5 and 36,073.8 µs;
  - one VTT `close()` took 2,612.8 µs, against 68.9-71.0 µs in the other reps;
  - file-system or Defender stalls are the likely cause (**inferred**);
  - the medians are stable: every cell above 2 µs has rep medians within 6.1% of each other (`R/BENCH.md` §6).
- **The CPU timer granularity flag (15.625 ms) does not apply here.**
  - OV-COST measures wall time with `perf_counter_ns` (**code** `S/bench_overlay_cost.py:119-121`).
  - The Electron times use `performance.now()`, which is quantised to 0.1 ms in these files.
- **Single runs.** Every Electron play, seek, VTT, alpha and drawbench result is from one run per config. The verifier's 3-repeat play runs were not queued (`R/BENCH.md` §3).
  - Only the patterns are robust: the +1 lookup direction, the overlay lagging behind, the composite staying paired, and the stable paused seeks.
- **The functional and quiet Electron runs differ in load, in Chromium's GPU list and in rAF rate** (about 60 vs about 56 ticks/s) (2.3 setup). Changes between them cannot be attributed to any one of these.
- **The readback instrumentation is still in the harness,** so how often canvas over `<video>` lags is confounded (2.3).
- **The N=8 `<video>` stalls and the WebCodecs scrub errors / GPU-process memory growth** (summary flags 5 and 6) come from intra_playback.
  - Overlays were tested on one video, or two for the alpha layer.
  - The overlay method rides on whichever multi-video playback path G9 picks, and its behaviour there is not tested.
- **Flags that do not apply here:** the libx265 affinity change (no libx265 in this topic; but see the affinity caveat above), the NVENC 12-session limit, nvJPEG quality, the write-latency comparison with the daytime run, and the missing uncompressed_intra lossless check.
- No OV-COST timing existed before tonight, so nothing is replaced as contaminated.

## 6. Not tested / limits / NOT VERIFIED

Data and formats:
- The overlay data is synthetic: a MediaPipe-33 skeleton and a 100-corner ChArUco board, with no NaNs and 0.01 px coordinates.
  - Real RTMPose 133-point output and variable point counts were not sampled.
  - Real-recording sizes and costs are NOT VERIFIED.
- Untested formats: MessagePack with float32 arrays, compressed JSONL/`.skov`, JSONL with a per-line CRC, a MessagePack reader with resync, and an intra-only alpha layer.
- The sidecar write cost excludes flush and fsync per frame. The durability cost of a sidecar is NOT VERIFIED here. crash_resilience measures flush and fsync for video files.
- Write cost was measured on one thread for one stream, in a process pinned (by request) to the P-cores. Sixteen concurrent sidecar writers and E-core threads were not tested.
- The crash tests used cuts and corruptions of finished files. A writer killed mid-record or mid-flush was not tested for any format.
- SVG per frame was not cut-tested, and VP9-alpha got only one 50% cut. Fragmented MOV/MP4 was not tested.
- The SVG and ASS files were not rendered in Chromium. Only `<img>` load/error of the single SVG was tested.
- VP9-alpha encode cost was not timed through PyAV 19, because the CLI row was excluded. No rasteriser faster than the two-render difference matte was tried.
- The quality of the burn-in re-encode against target A or B was not measured. The 1080p JPEG burn-in numbers rest on 19 distinct frames.

Chromium:
- One display (scaleFactor 1) on one machine. The refresh rate was not recorded. rAF ran at about 56 ticks/s in the quiet run and about 60/s in the functional run (**arithmetic** on `raf` counts, 2.3 setup): either the display rate differed or about 7% of rAF ticks were missed in the quiet run. The 16.7 ms frame used in 2.8 is an assumption, NOT VERIFIED.
- Hardware vs software decode per file was not recorded (**code** `S/electron_harness/main.js:98-100`, `getGPUInfo('basic')`).
- The test clips are GOP 30, inter-coded, and so background under requirement 8. This topic did not test overlay alignment on intra-only H.264/HEVC/JPEG playback.
- Each run gives 24-29 capturePage samples, in single runs with readback instrumentation. A run without the rAF loop needs a harness flag first.
- Alignment was tested at 1x and 2x, and composite mode only at 1x. Overlays on several videos at once (the G9 case) were not tested.
- UI draw cost was measured for one 1280x720 overlay canvas. Many tiles (for example 16 × 1.1 ms) were not tested. Whether that fits in a display frame is NOT VERIFIED.
- Untested: WebCodecs decode with `VideoFrame` timestamps paired to the overlay.
- Untested: WebVTT as data looked up by rVFC `mediaTime`.
- The PyAV-19-encoded VP9-alpha file was not tested in Chromium.
- Workarounds for the E35 last-frame lock-up were not tested, and the last-frame test was not re-run in the quiet run.
- The rVFC spec does not state that `drawImage` inside the callback returns the `metadata` frame (**source** https://wicg.github.io/video-rvfc/, checked by the provenance verifier 2026-11-10). The closest text is §1, "synchronized as a best effort with the video playing on screen", and §4.2, where the metadata is built from "video's latest presented frame". The dual-video data show that `drawImage` can disagree with the compositor (2.3.4).
- NOT VERIFIED: why E45 moves `droppedVideoFrames` on the CFR files but `presentedFrames` gaps on the VFR files (2.3.3).
- NOT VERIFIED: that Chromium truncates (rather than rounds) a seek time to microseconds; the f241 explanation (2.3.4) rests on the pts arithmetic and the MP4 control, not on Chromium source.
- NOT VERIFIED: WebCodecs `isConfigSupported` with the UHD 770 present. No real WebCodecs encode was run.
- NOT VERIFIED: that the unreadable barcodes at AV1 frames 14 and 254 are in the bitstream.
  - They are measured in both versions and both runs.
  - The libdav1d cross-check in `R/NOTES.md` §11 has no result file.

FreeMoCap and code citations:
- FreeMoCap schema drift: `charuco-types.ts:20` requires `has_pose: z.boolean()`, which Python does not send. The runtime effect is NOT VERIFIED.
- The skellytracker @6f78af48 citations come from the investigator and were not re-checked.

Labels and export:
- Leader-line crossings are not handled. Placement order is by id, not by importance.
- P3 libass alignment was measured only with the ffmpeg CLI and cannot run through PyAV 19.0.2.
- The PyAV 19.0.2 re-check used 60 frames, and its P1 and P2 pair frames by index, not by timestamp.

## 7. How to reproduce

Run from the repo root (`C:/Users/Dom/GitHub/freemocap/skellycam`) in Git Bash. In PowerShell, use `Remove-Item Env:ELECTRON_RUN_AS_NODE` instead of `env -u`. Timed items need a quiet machine, one item at a time, pinned to the P-cores; the runner does the pinning.

```
# timed (quiet run): the bench runner, from the repo root
uv run --script research/skellycam_recording/recording_upgrade/scripts/bench_runner/run_queue.py --only OV-COST,OV-DRAW-E35,OV-DRAW-E45,OV-PLAY-E35,OV-PLAY-E45 --deadline HH:MM
#   OV-COST needs about 36 min; raise its timeout to 60 min in make_queue.py first.

# the same items run directly (no affinity pinning, no load record):
uv run --script research/skellycam_recording/recording_upgrade/scripts/overlays/bench_overlay_cost.py --only sidecar_jsonl,sidecar_msgpack,sidecar_bin,sidecar_vtt,svg_per_frame,svg_single,ass,burnin_cv2,burnin_cv2_jpeg_roundtrip,jpeg_roundtrip_only,alpha_render --frames 900 --repeats 3
#   -> results/overlays/bench/bench_overlay_cost_<UTC>.json
E35=skellycam-ui/node_modules/electron/dist/electron.exe
E45=C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/shared/electron-latest/node_modules/electron/dist/electron.exe
H=research/skellycam_recording/recording_upgrade/scripts/overlays/electron_harness
O=research/skellycam_recording/recording_upgrade/results/overlays/bench
env -u ELECTRON_RUN_AS_NODE $E35 $H --tests=drawbench --mode=bench --query=reps=5 --out=$O/electron_drawbench_35.7.5.json
env -u ELECTRON_RUN_AS_NODE $E45 $H --tests=drawbench --mode=bench --query=reps=5 --out=$O/electron_drawbench_45.2.3.json
env -u ELECTRON_RUN_AS_NODE $E35 $H --tests=play,seek,vtt,alpha --out=$O/electron_play_quiet_35.7.5.json
env -u ELECTRON_RUN_AS_NODE $E45 $H --tests=play,seek,vtt,alpha --out=$O/electron_play_quiet_45.2.3.json
#   The Electron runs need <raw>/overlays/media/ and a visible, uncovered window.

# functional, no PyAV (pure Python / cv2): results/overlays/formats_functional.{json,md}, label_layout.{json,md}
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/formats_functional.py --frames 300
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/label_layout.py --frames 60

# verifier checks, no PyAV: results/overlays/verify_method_{crash_modes,precision}.json
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/verify_method_crash_modes.py
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/verify_method_precision.py

# test media and export (PyAV 18 + ffmpeg CLI; background)
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/make_test_media.py --frames 300
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/export_burnin.py --frames 300
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/alpha_truncation.py

# PyAV 19.0.2 functional re-check (caps, P1 export, VP9-alpha encode/decode/truncation, overlay filter graph)
uv run --script research/skellycam_recording/recording_upgrade/scripts/overlays/pyav19_functional_check.py --frames 60
#   -> results/overlays/pyav19_functional_check.json ; media -> <raw>/overlays/pyav19_check/

# Chromium functional harness (2026-11-09 run)
env -u ELECTRON_RUN_AS_NODE $E35 $H --out=research/skellycam_recording/recording_upgrade/results/overlays/electron_35.7.5.json --tests=caps,play,seek,lastframe,vtt,inband,alpha,trunc,webcodecs,layout
env -u ELECTRON_RUN_AS_NODE $E45 $H --out=research/skellycam_recording/recording_upgrade/results/overlays/electron_45.2.3.json --tests=caps,play,seek,lastframe,vtt,inband,alpha,trunc,webcodecs,layout
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/summarize_electron.py
```

How this revision recomputed the quiet-run tables from the JSON:
- **OV-COST:** group `results[]` by (`method`, `res`, `kind`), then take the median and min-max of `median_us` over the 3 reps. Sizes are `bytes_per_frame` and `MB_per_hour_30fps`.
- **Play:** for each entry of `results.play`:
  - `overlayMatch` / (`vfc` − `vfcDecodeFail`);
  - `rafUiMatch` / (`raf` − `rafDecodeFail`);
  - `captureMatch` / `captures`, and the differences of the `captureMismatch` pairs;
  - `barcodeSkips` vs `presentedGaps` vs `droppedVideoFrames`;
  - `raf` for the rAF tick rate.
- **Seek:** for each mode, `requestedMatch`, `lookupMatch`, `captureMatch` and `capture100Match`; for the f241 check, `modes.exact.mism[*].t` against `<raw>/overlays/media/pts_<file>.json` and the target list at `H:251-255`.

## Verification

Date: 2026-11-10. Two verifiers checked the quiet-run revision: provenance (`R/VERIFY_provenance.md`) and method (`R/VERIFY_method.md`). The 2026-11-09 reports are kept as `R/VERIFY_provenance.prev.md` and `R/VERIFY_method.prev.md`.

What the verifiers checked:
- Every quiet-run number recomputed from the raw JSON: all OV-COST medians, min-max, sizes and tails (246 records); all play, seek, VTT and alpha counts in both Electron versions; drawbench; and the derived arithmetic (51/275, 192/28/4, 111/112, the 13/16 skip identity, ratios and percentages). All matched except the SVG-per-frame range.
- Functional-run numbers against `R/electron_*.json`; the GPU-list claim; every code file:line checked in the harness, scripts, skellycam, skellycam-ui and freemocap.
- The three primary sources were re-fetched on 2026-11-10 and every quote is exact, including FFmpeg n8.0 `assdec.c` lines 72 and 118.
- The method verifier demuxed the CFR test files with PyAV 19.0.2 (functional, no timing) to locate the keyframes.

What the reviser re-checked before applying the refutations (no timing, reading result files only):
- SVG per frame: 163.8 µs (text, 1080p) to 950.6 µs (all, 1080p) in `B/bench_overlay_cost_20261110T103707Z.json`. Confirmed.
- rAF counts: 558-564 (quiet) vs 597-604 (functional) per 1x clip. Confirmed.
- E45 `presentedGaps` = barcode skips on both VFR files (43, 38) and 0 on CFR. Confirmed.
- f241: WebM pts table 8.033 vs MP4 8.033333; the requested `t` in every f241 miss is 8.033; f241 is the only seek target whose pts truncates below itself in the CFR WebM files; CFR H.264 exact seeks 80/80. Confirmed.
- `LOG` lines 38-40, 67-68 and 73: affinity `pcores`, `load_over_15pct: false`, empty Defender scan events, MsMpEng 125.08 / 79.36 CPU-s. The 7/8 blocks from `36_OV-COST.out.txt`. Confirmed.
- Corpus: 891 frames at 720p, 19 at 1080p; `camera_jpeg_bytes_per_frame` is `statistics.fmean` over 900 looped frames (`S/bench_overlay_cost.py:168`). Confirmed.
- Composite-mode `naiveMatch` VFR: 145/286 (E35) and 134/269 (E45). Composite barcode skips 13, 13, 30, 30 (the verifier's "12-30" is corrected to 13-30).

What was changed:
- Refuted and corrected: (1) the "60 Hz from about 560 rAF ticks" inference (now about 56 vs about 60 ticks/s, refresh rate NOT VERIFIED); (2) the "one counter per version" drop-counter claim (in E45 the counter depends on CFR vs VFR); (3) the GOP-30 keyframe explanation of the f241 misses (now a 1-µs timestamp truncation in the 1-ms-time-base WebM files; GOP and intra-only framing removed); (4) the SVG-per-frame range (now 163.8-950.6 µs).
- Relabelled or tightened: P-core affinity is requested, not measured, with E-core threads not measured; functional-vs-quiet differences are not attributed to load (GPU set and rAF rate also changed); "unstable between runs" now "varies between modes and runs, repeatability not measured"; paused seeks "identical under two different conditions"; the composite 111/112 check shows pairing, not on-time presentation, and the recommendation says "stay paired"; the JPEG size ratio is a cv2 q90 re-encode not at matched quality with the overlay's share unmeasured; alpha sizes labelled GOP 30, background, with intra-only untested; drawbench version difference marked single run, not significant; camera JPEG size labelled median (2.5) vs mean over 900 looped frames (2.6); 1080p 19-frame corpus caveat added; rVFC spec item relabelled as source; WebVTT 1x column labelled "CFR, unshifted cues"; `rafUiOffsets` sign defined; `naiveMatch` VFR range scoped to plain runs; run-log citations made direct; 2026-11-09 verifier citations pointed to the `.prev` files.

What remains NOT VERIFIED:
- The display refresh rate, and so the 16.7 ms frame assumption.
- Why E45 moves different drop counters on CFR and VFR files.
- That Chromium truncates seek times to microseconds (from source).
- Actual per-process CPU affinity during the OV items.
- WebCodecs capability with the UHD 770 present; real-recording overlay sizes and costs; sidecar durability (flush/fsync) cost; the AV1 unreadable barcodes being in the bitstream; the FreeMoCap `has_pose` runtime effect; the skellytracker @6f78af48 citations; PyAV 19.0.2's ASS timing.
