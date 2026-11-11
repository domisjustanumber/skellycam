# overlays (G3): method verification of the 2026-11-10 draft FINDINGS

Verifier: adversarial, methodology lens. Date 2026-11-10. Draft: the post-bench revision (quiet run `20261109T230007`, OV-COST re-run `20261110T053653`), passed in by the workflow, not on disk.
The 2026-11-09 method report is kept as `VERIFY_method.prev.md`.

Paths are relative to `research/skellycam_recording/recording_upgrade/`. `R/` = `results/overlays/`, `B/` = `R/bench/`, `H` = `scripts/overlays/electron_harness/harness.js`.

## What I did

- I recomputed every quiet-run number the draft cites from the raw JSON, with a short script that reads only the files (no timing):
  - `B/bench_overlay_cost_20261110T103707Z.json`: medians and min-max of the 3 per-rep medians, sizes, `max_us` tails, `close_us`;
  - `B/electron_play_quiet_{35.7.5,45.2.3}.json` and `R/electron_{35.7.5,45.2.3}.json`: play, seek, VTT and alpha counts, the `captureMismatch` differences, skips vs gaps vs `droppedVideoFrames`, `raf` counts and `env.gpuInfo`;
  - `B/electron_drawbench_*.json`;
  - `results/BENCH_RUN_2300_LOG.jsonl` lines 38-40, 67-68, 72-73.
- I read the harness code that produced each number (`H:180-288`, `H:50-66`, `H:135-141`, `S/electron_harness/main.js:18-25,119`) and `scripts/overlays/bench_overlay_cost.py:85-200`.
- One quick functional check (PyAV 19.0.2 via `uv run --script`, demux only, no timing): `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step2/ov_method/kf.py`. Output:
  - `base_cfr_vp9.webm` and `base_cfr_av1.webm`: time base 1/1000, pts of frames 239-242 = 7967, 8000, 8033, 8067; keyframes 0, 30, ..., 270.
  - `base_cfr_h264.mp4`: time base 1/15360, pts 122368, 122880, 123392, 123904; keyframes 0, 30, ..., 270.

## Numbers that check out (measured, recomputed)

- Every OV-COST cell the draft cites (sidecars, SVG, ASS, burn-in, JPEG round trip, alpha rasterisation, sizes, MB/h, JPEG sizes) matches the JSON. So do the 0.4-3.3 µs text range, 4.3x and 1.74x, 0-5.0 % growth at 1080p (ASS skeleton 2,757.1 vs 2,627.0 B), the 11 tail records over 1 ms, the 16,963.5 / 36,073.8 µs `svg_single` maxima and the 2,612.8 µs VTT close.
- Every play count in 2.3.1-2.3.3 and 3.3 matches: the lookup table, the +1-only lookup offsets (no run went past the 20-entry cap; maximum count 17), `naiveMatch`, `rafUiMatch` and its offsets, captures 51/275, mismatch differences +1 192 / +2 28 / +3 4, composite 111/112, the `[250, 249]` pair, 2x rows, skips/gaps/drops and "13 of 16".
- The seek table, VTT table, dual-video counts and drawbench values match.
- Log citations match: OV-COST timeout at line 38; re-run at lines 72-73 (60-min timeout, no flags); MsMpEng 125.08 and 79.36 CPU-s; `make_queue.py:251` still has `12, 30` for OV-COST.

## Refuted

### R1. "about 60 Hz, inferred from about 560 rAF ticks per 10-s clip" (section 6; also `R/BENCH.md:266`)

- measured: the quiet run's `raf` counts are 558-564 for the 300-frame (10.0 s) 1x clips and 279-280 for the 5-s 2x clips, in both versions (`B/electron_play_quiet_*.json` → `results.play[*].raf`).
- arithmetic: 558-564 per 10 s is 55.8-56.4 ticks/s, not 60.
- measured: the functional run had 597-604 (1x) and 298-299 (2x) ticks, which is about 60/s (`R/electron_*.json`).
- Correction: "rAF ran at about 56 ticks/s in the quiet run and about 60/s in the functional run (arithmetic on `raf` counts). The refresh rate was not recorded. Either the display ran at a different rate or about 7 % of rAF ticks were missed in the quiet run. The 16.7 ms frame used in 2.8 is an assumption, NOT VERIFIED."

### R2. The drop-counter reading (2.3.3, 3.4 and section 4)

- measured (`B/electron_play_quiet_45.2.3.json`): in E45, `presentedFrames` gaps equal the barcode skips on both VFR files (43/43, 38/38, with `droppedVideoFrames` 0). They are 0 only on the three CFR files, where `droppedVideoFrames` is 19/20/19.
- measured: in E35, `presentedFrames` gaps equal the skips on every 1x run (the 2 unreadable AV1 barcodes aside).
- So these statements are wrong:
  - section 4, "Each matched the barcode skips in only one Electron version": `presentedFrames` gaps matched in E35 and in E45 VFR;
  - 2.3.3, "The two Chromium versions appear to file the same missing frames under different counters": inside E45 the counter depends on the file (CFR vs VFR).
- 3.4 is correct only because it says "on CFR 1x".
- Correction: "In E35, `presentedFrames` gaps matched the skips in every 1x run. In E45 they matched on the VFR files but read 0 on the CFR files, where `droppedVideoFrames` matched instead (measured). Neither counter matched in every run. Why E45 differs between CFR and VFR is NOT VERIFIED." The recommendation (don't rely on either counter alone) still holds.

### R3. "The f241→240 misses land on frame 240, which is a keyframe at GOP 30" (2.3.4) and the link to intra-only in section 4

- measured (quick check above): `base_cfr_h264.mp4` also has a keyframe at 240 (GOP 30), and its exact-pts seek to 241 hit in both versions and both runs (80/80).
  - Frame 151 follows keyframe 150, is in the seek target list (`H:252-255`), and hit in the WebM files too.
  - So "frame after a keyframe" does not predict the miss.
- measured: the pts table gives `pts[241] = 8.033` for both WebM files (ms time base) and `8.033333` for the MP4 (`<raw>/overlays/media/pts_*.json`). The harness seeks to exactly `pts[f]` (`H:261`).
- arithmetic (Python `int(t*1e6)` over all 80 targets of each file): 8.033 as a double is 8.03299999999999947..., which truncates to 8,032,999 µs, below the 8,033,000 µs pts. Frame 241 is the **only** target in either CFR WebM file whose value truncates below its pts. It is the only CFR miss in both files and both runs. No target in the MP4 truncates below.
- inferred: the miss is better explained by double-to-microsecond truncation of a millisecond-exact seek time than by the GOP. That Chromium truncates rather than rounds is NOT VERIFIED from Chromium source.
- Correction: "The f241→240 misses happen only in the two WebM files (1 ms time base). There the requested time 8.033 s truncates to 1 µs below the frame's pts. The H.264 MP4, also GOP 30 with a keyframe at 240, hit f241. inferred: this is a timestamp-precision effect, not a GOP effect. Seeking to the midpoint avoids it." The midpoint recommendation stands. Delete the implied link "missed f241 on the GOP-30 CFR WebM files", and the framing that intra-only would answer this.

## Weak (correct numbers, conclusion over-reaches or is under-qualified)

### W1. The functional-vs-quiet comparisons are not a load-only contrast

- measured: Chromium's GPU list has the Intel UHD 770 (32902/42880) only in the quiet run (`env.gpuInfo.gpuDevice`). rAF rate went from about 60/s to about 56/s (R1).
- So differences between the two runs cannot be attributed to load. That covers:
  - "E35 matched less often in the quiet run than in the loaded run ... rates do not simply improve on a quiet machine";
  - "Play-time `activeCues` matching is load-sensitive";
  - "paused-seek behaviour is ... not sensitive to load".
- Fix: "the two runs differ in load, in the GPU adapters Chromium saw and in the rAF rate. Changes between them are not attributable to any one of these." Paused seeks are "identical under two different conditions".

### W2. "The rule's match rate is unstable between runs"

- The pairs used are plain vs canvas-composite (a different mode: the `<video>` is opacity 0, `H:183`) and functional vs quiet (W1). No identical config was repeated under the same conditions.
- Fix: "varies between modes and between the two runs; repeatability under identical conditions is not measured." The conclusion "cannot rank codecs or versions" still holds.

### W3. "P-cores only" for the OV items is requested, not measured

- measured: the log records `"affinity": "pcores"` for lines 38-40, 67-68 and 73. That is the runner's setting.
- The OV-COST and Electron JSONs record no `process_cpu_affinity`. The `BENCH_QUEUE_2300.md:38` evidence is smoke snapshots of other bench processes.
- The libx265 case shows that a library can widen affinity (`results/BENCH_RUN_2300_SUMMARY.md:44-47`).
- Fix: "pinned by the runner (requested); actual affinity inside the OV processes, including Electron's GPU and renderer processes, was not recorded." Also say that per-call costs are for a P-core thread. An unpinned recorder thread on an E-core was not measured.

### W4. The composite capture check is close to tautological

- code: in composite mode the video is invisible (`H:183`). The captured "video" barcode and the overlay barcode both come from one canvas commit (`H:61`).
- So 111/112 shows that the composite's own `drawImage` agreed with the `mediaTime` lookup. It does not show that the canvas presents every frame on time: the composite runs had 12-30 barcode skips per 300 frames.
- Fix: say this next to the 111/112. The recommendation stands as "keeps overlay and frame paired". It is not "frame-exact on screen".

### W5. JPEG growth under burn-in (2.6, section 4: "grows the file 1.03-1.10x at q90")

- This compares a cv2 q90 re-encode with the camera's own JPEG, at unmatched and unmeasured quality (neither at A nor B).
- `jpeg_roundtrip_only` records no output size (`bench_overlay_cost.py:190-200`). So the growth from the re-encode cannot be separated from the growth from the drawn overlay.
- Fix: "size of a cv2 q90 re-encode vs the camera JPEG, not at matched quality; the overlay's share of the growth was not measured."

### W6. Alpha-layer size ratio (2.5, 3.1, section 4: "19.5-24.4x the `.skov` size")

- Both VP9-alpha files are GOP 30, inter-coded (`-g 30`, `S/make_test_media.py:187`; `S/pyav19_functional_check.py:182`). Under requirement 8 that is background. An intra-only alpha layer was not measured.
- inferred: an intra-only alpha layer would probably be larger, so the ratio is not an upper bound.
- The two sizes also come from 300 and 60 frames, against `.skov` at 900.
- Fix: label the alpha sizes "GOP 30, background" in 2.5 and 3.1. The recommendation to drop the alpha layer only gets stronger.

### W7. Electron draw-cost comparison (3.4: 1.1 vs 0.9 ms)

- Each is one process (1,500 pooled calls), with `performance.now()` quantised to 0.1 ms. The difference is 2 quanta, with no repeat.
- Fix: don't rank the versions on this row, or mark it "single run, not shown significant".

### W8. Small items

- `rafUiOffsets` sign is not defined in the draft. It is `floor(currentTime*30) − drawImage frame` (`H:224`). Add it, because the +1/-1 discussion depends on it.
- Section 5 gives "165-951 µs per frame" for SVG per frame. The JSON medians run 163.8 (1080p text) to 950.6 (1080p all).
- The draft cites `R/VERIFY_method.md` and `R/VERIFY_provenance.md` for the 2026-11-09 pass. Those reports are now `R/VERIFY_method.prev.md` and `R/VERIFY_provenance.prev.md`; update the citations.
- The `naiveMatch` VFR range "125/256 to 139/282" covers plain runs only. The composite VFR runs gave 145/286 and 134/269. Say "plain runs".

## Lens items checked and found handled

- Quality: no number is claimed at target A or B, and the draft says so. The ~55 dB clip quality is not mixed with A or B.
- NVENC 12-session limit, libx265, nvJPEG and the write-latency comparison are correctly marked not applicable. No OV item uses NVENC or libx265.
- Defender: it is kept as part of the cost, and not split per method. The SVG-per-frame inflation is labelled inferred. Fine.
- Page-cache vs cold opens: not applicable. OV-COST reads the corpus into memory before timing (`bench_overlay_cost.py:101-103`), and no open time is claimed.
- Functional pass vs compatibility: the PyAV 19 P1/P2 limits (60 frames, index pairing) and the CLI-encoded alpha file in Chromium are stated.
- Intra vs GOP: the test clips are labelled background, except R3 and W6.
- Single runs: section 5 says so. W1 and W2 tighten the wording.
- One SKU: WebCodecs `isConfigSupported` is limited to this machine, with the iGPU absent.

## Verdict

Every number in the draft matches the raw JSON. The structure and the main recommendations hold: a CRC-framed sidecar, no record-time burn-in, rVFC `mediaTime` lookup, a composite canvas, midpoint seeks, and the Electron 45 upgrade.

Three statements are refuted and need rewording:
- R1: the "about 60 Hz from 560 ticks" inference;
- R2: the drop-counter characterisation and its section 4 bullet;
- R3: the GOP/keyframe explanation of the f241 misses.

The weak items mostly qualify confounders:
- W1-W2: run-to-run changes attributed to load;
- W3: requested vs measured P-core affinity;
- W4: the tautological composite capture;
- W5-W6: size ratios not at matched quality or not intra-only.

None of these changes a section 4 recommendation's direction.
