# overlays (G3): provenance verification of the 2026-11-10 FINDINGS draft

Verifier: provenance lens. Date 2026-11-10. No timed measurement was run. The previous report (verification of the 2026-11-09 text) is kept as `VERIFY_provenance.prev.md`.

Paths as in the draft: `R/` = `results/overlays/`, `B/` = `R/bench/`, `S/` = `scripts/overlays/`, `H` = `S/electron_harness/harness.js`.

## Verdict

**PASS with minor corrections.** Every quiet-run number I checked matches the raw JSON. One number is wrong (a range in section 5). Six citations or labels need tightening. Nothing is from memory, no PyAV 18 result is presented as primary, and no contaminated daytime timing is presented as current. The draft states correctly that no number is at target A or B.

## How I checked

I recomputed everything from the raw files with scripts in the step2 scratchpad (`ov_prov/check.py`, `check2.py`, `check3.py`). I did not rely on BENCH.md.

| area | file(s) | what I recomputed | result |
|---|---|---|---|
| OV-COST timing and sizes | `B/bench_overlay_cost_20261110T103707Z.json` | 246 records grouped by (method, res, kind): median and min-max of `median_us` over 3 reps; `bytes_per_frame`, `MB_per_hour_30fps`, `out_jpeg_bytes_per_frame`, `camera_jpeg_bytes_per_frame`; `max_us` and `close_us` tails | every cell in 2.2, 2.5, 2.6, 3.1 and 3.2 matches; 11 tail records confirmed; 6.1% maximum rep spread above 2 µs confirmed (VTT text 720p) |
| arithmetic | same | 4.3x, 1.74x, 0.4%, 49.5-50.2%, 1.10/3.02/1.03/2.22x, 0.09%/0.39%/61-75%/10-23%/205-339%, 19.5x/24.4x, 5-11x size and 11-32x cost, MB/h for alpha and MOV, 111/112, 51/275, 192/28/4 | all correct |
| quiet play | `B/electron_play_quiet_{35.7.5,45.2.3}.json` → `results.play` | lookup, naive, rAF rule and offsets, captures and capture-mismatch differences, barcode skips vs `presentedGaps` vs `droppedVideoFrames`, `overlayMismatch` code − fi, `overlayMismatchCount` | all match; every quiet mismatch is +1, and none was truncated by the 20-entry cap (`H:201`); 13/16 runs satisfy skips = gaps + dropped (+2 for AV1); the other 3 are 1-2 lower, as stated |
| quiet seek, VTT, alpha | same → `seek`, `vtt`, `alpha` | requested/lookup/capture/capture100 per mode; VTT play offsets and seek counts; dual-video sync and seek | all match; the example `{"f": 79, "code": 78, "cue": 79}` is from E45 |
| functional run | `R/electron_35.7.5.json`, `R/electron_45.2.3.json`, `R/electron_summary.md` | the same fields, plus last-frame, trunc, inband, caps, webcodecs | all functional numbers quoted match; all functional 1x lookup misses are also +1 |
| GPU list | `env.gpuInfo.gpuDevice` in all four Electron result files plus the drawbench files | vendor and device IDs, driverVersion | functional: 4318/9348 and 5140 only; quiet and drawbench: also 32902/42880 (Intel) |
| drawbench | `B/electron_drawbench_*.json` | median/p95/max; `note` text | match; the note is quoted verbatim |
| functional formats | `R/formats_functional.json`, `R/verify_method_crash_modes.json`, `R/verify_method_precision.json`, `R/label_layout.json` | sizes, truncation fields, crash modes, precision ratio, layout counts | all match; the crash and precision scripts are 300 frames, 1280x720, "all" (`S/verify_method_crash_modes.py:12-14`, `S/verify_method_precision.py:13-14`) |
| media, export, PyAV 19 | `R/make_test_media.json`, `R/alpha_truncation.json`, `R/export_burnin.json`, `R/pyav19_functional_check.json`, `<raw>/corpus/index.json` | every figure quoted | all match; `make_test_media.json` and `export_burnin.json` record `pyav: 18.0.0` and are labelled background |
| run log | `results/BENCH_RUN_2300_LOG.jsonl` | lines 38-40, 67-68, 72-73 | OV-COST timeout at line 38 (status timeout, MsMpEng 125.08); re-run ok at line 73 (79.36); every OV item has `affinity: pcores`, `load_over_15pct: false`, and no Defender scan event |
| code citations | `H`, `S/electron_harness/main.js`, `S/*.py`, skellycam, skellycam-ui, freemocap | every file:line in the draft | all say what the draft claims (details below) |
| primary sources | rVFC spec, WebVTT TR, FFmpeg n8.0 `assdec.c` | re-fetched 2026-11-10 | every quote is exact; `assdec.c` lines 72 and 118 are exact (raw GitHub, tag n8.0) |

Code lines confirmed: `H:58` (`measureCache`), `H:61` (composite `drawImage`), `H:183` (opacity 0), `H:194-205`, `H:201` (20-entry cap), `H:203` (barcode skips), `H:206` (presentedFrames gaps), `H:208-213` and `H:212` (`[c.video, c.overlay]`), `H:221` (floor), `H:229` (`noRaf`), `H:236` (`droppedVideoFrames`), `H:336` (cue − frame), `H:399` (layer − base), `H:523` (composite only at rate 1); `main.js:18-25` (no `noRaf` argument), `main.js:98-100` (`getGPUInfo('basic')`); `bench_overlay_cost.py:1-7, 11-16, 50-55, 91, 118-127, 132-146, 151, 160-163, 168, 176-191`; `overlay_model.py:62, 269, 304, 451, 612-618, 621-631`; `formats_functional.py:15-25, 98-112`; `label_layout.py:186`; `make_test_media.py:88, 186-187, 205`; `pyav19_functional_check.py:122, 133, 182, 249`; skellycam `opencv_get_frame.py:79-90`; skellycam-ui `SyncedVideoPlayer.tsx:281-308, 334-335, 377-403, 506-507, 658-700`; freemocap `charuco-overlay-renderer.ts:165`, `offscreen-renderer.worker.ts:17,26-29,62-63,83`, `video_node.py:211-219`, `binary_keypoints_protocol.py:15,58-64` (`frame_number` is at lines 8, 27 and 85), `charuco-types.ts:20`.

## Refuted

| claim | evidence | correction |
|---|---|---|
| §5: SVG per frame takes "165-951 µs per frame" | `B/bench_overlay_cost_20261110T103707Z.json`: the lowest cell is `svg_per_frame` text 1080p at 163.8 µs (720p text is 165.0); the highest is "all" 1080p at 950.6 µs. The draft takes the 720p minimum and the 1080p maximum | "163.8-950.6 µs per frame (both sizes)" |

## Weak (correct, but the citation or label needs fixing)

1. **§5, "timed out once ... after 7 of its 8 blocks" is cited to log line 38.** Line 38 records the timeout and the kill, but not the block count. The 7/8 comes from `results/bench_runner/logs/20261109T230007/36_OV-COST.out.txt`, which prints 7 "done" lines and has no `1920x1080 all`. **Fix:** cite the stdout log for 7/8.
2. **§5, "P-cores only" for every item.** Every OV line in the log has `"affinity": "pcores"` (lines 38-40, 67-68, 73), but no OV result JSON records the process affinity during the item. Flag 2 shows that a child process can widen its affinity. **Fix:** cite the log lines and add "per-process affinity during OV items was not recorded".
3. **§5, "No item was load-flagged ... no Defender scan event" is cited only to `R/BENCH.md` §1,** which is a convenience file. **Fix:** cite `BENCH_RUN_2300_LOG.jsonl` lines 38-40, 67-68 and 73 (`load_over_15pct: false`, `defender_scan_events_during_item: ""`). I checked these.
4. **Two different statistics are both called "the camera's own JPEG".** §2.5 gives the corpus median, 56,759 B (`corpus/index.json`, 891 frames). §2.6 and §3 use 55,379 B, which is `statistics.fmean` over 900 looped frames (`S/bench_overlay_cost.py:168`). **Fix:** say "median" in §2.5 and "mean over the 900 looped frames" in §2.6.
5. **The 1080p corpus is only 19 frames, looped** (`<raw>/corpus/index.json` → `c930e_1080p.frames: 19`; `R/BENCH.md` §6). The draft does not say this. It applies to the 1080p burn-in, the JPEG round trip and the re-encoded JPEG sizes in 2.6 and 3.2. **Fix:** add one caveat line in 2.6 or §6.
6. **§6, "NOT VERIFIED: whether the spec requires `drawImage` inside rVFC to return the `metadata` frame (investigator reading, not re-checked)".** I re-checked the spec on 2026-11-10 (https://wicg.github.io/video-rvfc/). It does not say so. The closest text is §1, "synchronized as a best effort with the video playing on screen", and §4.2 builds the metadata from "video's latest presented frame". **Fix:** relabel as **source**: "the spec does not state this (checked 2026-11-10)".
7. **§3.3, WebVTT row, "1x" column.** The functional range "8/299-148/299" is the unshifted CFR case only; the half-shift case gave 207/299. The quiet range "143/278-257/281" happens to contain the half-shift values. **Fix:** label the column "CFR, unshifted cues", or widen the functional range to 8/299-207/299.

## Checked and OK (notable)

- **Quality targets.** The draft says no number is at target A or B. This is correct: the only lossy re-encode is cv2 q90 (`S/bench_overlay_cost.py:163`), with no quality measured. The test clips use fixed CRF (`R/make_test_media.json`).
- **PyAV versions.** PyAV 18 results (`make_test_media.json`, `export_burnin.json`) and ffmpeg CLI results are all labelled background. The PyAV 19.0.2 results come from `R/pyav19_functional_check.json` (`pyav: 19.0.2`, libavformat 63.1.102). OV-COST imports no PyAV (`S/bench_overlay_cost.py:1-7`; `overlay_model.py` imports only stdlib and numpy).
- **No daytime OV-COST timing exists to replace.** The 2026-11-09 Electron play counts are presented as a separate functional run, never as current timing.
- **Contradictions with the 2026-11-09 text are stated openly** (2.3.1 rAF offsets, 2.3.2 lag of 1-3 frames, 2.4 VTT +1 offsets). The data support each one.
- **The libdav1d bitstream claim** for the AV1 barcodes is correctly NOT VERIFIED. `R/NOTES.md:250` asserts it as measured, but no result file exists.
- **The ASS centisecond source** is FFmpeg n8.0. PyAV 19.0.2 bundles libavformat 63.1.102, and the draft correctly marks the match as NOT VERIFIED.
- **Reproduce paths exist:** the E35 and E45 `electron.exe` files and `<raw>/overlays/layout/C_placed_720p_board20.png`.
