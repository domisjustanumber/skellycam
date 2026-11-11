# python_integration: adversarial verification, methodology lens (2026-11-10)

2026-11-10, Gerald. Scope: the 2026-11-10 draft FINDINGS for python_integration (not on disk), mainly the new timed findings F11-F15, implications 3, 4, 6, 9, 10 and section 5. F1-F10 were method-verified on 2026-11-09 (`VERIFY_method.prev.md`) and are only re-read here where the new text leans on them. No timed measurement was run. One functional check was run (below).

**Paths:** `R/` = `research/skellycam_recording/recording_upgrade/results/python_integration/`, `B/` = `R/bench/`, `S/` = `.../scripts/python_integration/`, `RES/` = `.../recording_upgrade/results/`, `X/` = `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step2/pi_method/` (verifier scratch, outside the repo).

## Verdict

The timed numbers match their JSON (spot-checked: every phase A/B/C value, the c922 1080p decode row and its threaded rates, every nvJPEG median/p99, the MsMpEng CPU-s for items 24/39/40). The draft handles single runs, P-core pinning and the flag table well. Two claims are wrong and need correcting: the MKV first open labelled "cold", and the general statement that a decode → nvJPEG path misses target A. Several more are overstated or confounded and need narrowing.

## Refuted

### R1. "Cold-open cost appears only as the MKV first rep (77.83 ms)" (section 5); the F13 framing of the 77.83 ms rep
- **code:** phase C reads each file straight after `wr.close()` in the same process, with no cache drop (`S/bench_recwriter.py:169-190`). So all three reps are page-cache warm. The draft says so itself in F13 ("warm cache").
- **code:** phase A and B never call `cv2.VideoCapture`, and MKV is the first file phase C opens (`S/bench_recwriter.py:87-117, 120-158, 165`). The 77.83 ms is therefore the first cv2 CAP_FFMPEG open in the process and the first open of a freshly written 1.4 GB file.
- **measured, cross-topic:** in `RES/jpeg_passthrough/bench/open_long.json` every file's first rep after its write is also elevated (mkv 4.93 vs 0.19 ms, mp4 7.74 vs 2.38, 1 s fMP4 55.1 vs ~42), and that script states "First rep after write is page-cache warm (stated); no cache drop is done" (`scripts/jpeg_passthrough/bench_open_long.py:15`).
- **inferred:** the extra ~74 ms is a first-open effect (one-time cv2/FFmpeg plugin initialisation, a Defender scan on first open of a new file, or both). The files do not separate them. It is not a cold-cache open.
- **Correction:** "No cold-cache open was measured. The MKV first rep (77.83 ms) is the first cv2 open in the process and the first open of a newly written file, page-cache warm; its cause is not separated." Drop "Cold-open cost appears only as…". In F13 keep the arithmetic but call it "first open after write", not cold.

### R2. Implication 10: "A decode → nvJPEG re-encode path is therefore not a target-A path as tested"
- **measured:** in the same file the draft cites, `RES/intra_compare/bench/matched_stream_A_1080p_20261110T042204Z.json` → `summary`, the `nvjpeg_420` row with `source: mjpeg_qsv` has `ssim_y` **0.99788** (`psnr_y` 56.462), above target A (`matched_ssim_y` 0.99617). Only the `source: mjpeg_cpu` rows (`nvjpeg_422`, `nvjpeg_420`) are at `ssim_y` 0.9954.
- **source (run summary):** flag 4 attributes the miss to the swscale-RGB step: "consistent with the swscale-RGB loss noted in the queue" (`RES/BENCH_RUN_2300_SUMMARY.md` §3 item 4).
- **Correction:** "nvJPEG encode fed camera MJPEG decoded on the CPU (`mjpeg_cpu`, via host RGB) misses target A (SSIM-Y 0.9954 < 0.9961). Fed `mjpeg_qsv`-decoded frames, the 4:2:0 row reaches SSIM-Y 0.99788 (same file). Quality checks use 4 frames." Also say this is an encode result for another topic, not a decode result from this one.

## Weak (needs narrowing or a caveat)

### W1. F13 / implication 3 mix two different open metrics
- **code:** PI phase C times `VideoCapture` + `CAP_PROP_FRAME_COUNT` + **first `read()`** (`S/bench_recwriter.py:177-181`). open_long times `VideoCapture` + `CAP_PROP_FRAME_COUNT` only, **no read** (`scripts/jpeg_passthrough/bench_open_long.py:74-77`).
- So implication 3's "against 3.7 ms / 0.19 ms for MKV" makes MKV look faster at 30 minutes than at 10. The 3.7 ms mostly reflects the first-frame decode. The F13 inference "372 ms at 18,000 → 1107 ms at 54,000" also compares different metrics, corpora (c922 vs c930e) and timestamps (ideal vs looped real). The ~3 ms read is small next to ~370 ms, so the trend survives, but say so.
- Also, the "about 100×" headline depends on the metric. With open + count only (open_long) the ratio at 54,000 frames is 1107.28 / 0.19 ≈ 5,800×.
- **Fix:** name the metric in every open number. In implication 3, compare like with like (PI: 372 vs 3.7 ms with first read; open_long: 1107 vs 0.19 ms, open + count). Mark the growth inference as cross-script.

### W2. F11 Defender attribution
- **measured:** MsMpEng used 16.62 CPU-s during PI-JPEG-DECODE (9.21 min), which writes no files, against 12.31 CPU-s during PI-RECWRITER (2.24 min) (`RES/BENCH_RUN_2300_LOG.jsonl`). PI-RECWRITER also writes 2 × ~1.4 GB new container files in phase C and 10 MKV files in phase B (`B/recwriter_quiet1_pyav19.json` → `c_open_cost.*.bytes`; `S/bench_recwriter.py:128`).
- So the item total cannot be pinned on the folder cases. The section 5 wording "(folder baseline: 3000 new files per case)" reads as an attribution.
- **Fix:** give the decode item as a no-write comparison (1.8 vs 5.5 CPU-s per minute; arithmetic). Say the 12.31 CPU-s covers all three phases. For the folder-specific cost cite write_throughput (`RES/BENCH_RUN_2300_SUMMARY.md` §2/§4: files 26.8 s vs 1.2-1.5 s per 30 s cell). Implication 4's "draws Defender scanning" should cite write_throughput, not F11.

### W3. F11 title "a folder of JPEGs costs 2.5-6.8× more" than "any container"
- **arithmetic** on `B/recwriter_quiet1_pyav19.json`: the range holds against MKV only. Against AVI (index) it is 7.75× at 720p (0.2233 / 0.0288) and 2.69× at 1080p. Against fMP4 it is 7.0× at 720p.
- **Fix:** "2.5-6.8× the MKV median (2.5-7.8× across the three containers)".

### W4. F11 / implication 6: phase A is an unpaced burst; its worst call is not the study's worst stall
- **code:** phase A calls `write()` back to back with no pacing (`S/bench_recwriter.py:106-109`), so 3000 calls run in well under a second at about 30,000 calls/s (arithmetic: 3000 × 0.033 ms). Its p99.9 rests on 3 samples and its max on 1 sample, in one run.
- **measured, cross-topic:** under paced 16 × 1080p60 load, write_throughput reports p99.9 of 1.7 / 2.9 / 3.2 ms (append / mkv_flush / fmp4_frame_flush) and 20.3 ms for files (`RES/BENCH_RUN_2300_SUMMARY.md` §4, `write_throughput/bench/focus16_av19/`). These are above phase A's 0.68 ms "at most" for MKV/fMP4.
- **Fix:** in implication 6, size the queue from the concurrent paced tails (cross-topic), not from phase A's 0.68 ms. The conclusion (a few frames of headroom at 33 ms per frame is plenty) still holds. Say phase A is a burst, single-writer measure.

### W5. F12 title generalises beyond the test
- **code:** phase B is 720p only, MKV only, 5 cameras, 60 s per rate, single run, producer only sleeps (`S/bench_recwriter.py:120-145`).
- **Fix:** title "…keeps up with 5 paced 720p MKV cameras at 30 and 60 fps (one 60 s run each)". 1080p, fMP4, 16 cameras and a GIL-busy producer are untested (the GIL limit is already disclosed).

### W6. F14 / implication 9: "simplejpeg into a preallocated buffer" is a best case
- **code:** `sj_into` reuses one thread-local buffer for every call (`S/bench_jpeg_decode.py:64-71`), so the destination stays allocated and probably cache-resident. The other methods allocate a new output array per call. A real shared-memory ring writes to a different slot each frame.
- **inferred:** part of the gain (no new allocation) carries over to a preallocated ring. The cache-hot part may not. Not separated.
- **Fix:** state that the into-buffer number reuses one buffer, and call the ring-slot cost not measured.

### W7. F14 / implication 9 / F15: single SKU and P-cores only, applied to a cross-platform choice
- **measured:** all decode numbers are from one i7-14700K, pinned to its P-cores, and one RTX 3070 (`RES/BENCH_RUN_2300_LOG.jsonl`, `affinity: pcores`; `B/nvjpeg_decode_quiet1_2300.json` → `env.nvidia_smi_before`).
- The 16-camera extrapolation (32% / 59% of the 5-thread rate) and "nvJPEG with copy is no faster than simplejpeg" are relative to this fast CPU. The hardware target includes 2020+ CPUs without this headroom (HANDOFF §1 req. 3).
- **Fix:** add "on this i7-14700K (P-cores) / RTX 3070" to implications 9 and 10 and to the 16-camera arithmetic. Don't apply the ratios to other CPUs or GPUs.
- Minor: the threaded ratios include 5.03× on 5 threads (c930e_720p PyAV native YUV), which is above linear and shows single 5-s-run noise. Say so next to "3.92-5.03×".

### W8. F15: the interleaved timing loop makes gpu_single vs gpu_to_host depend on the unverified sync
- **code:** each frame's `gpu_single` (decode + `__cuda_array_interface__`) is followed at once by a separate `gpu_to_host` (decode + `.cpu()`) in the same loop (`S/bench_nvjpeg_decode.py:79-86`). If the interface access does not synchronise (NOT VERIFIED, as the draft says), `gpu_single` under-reads and the next `gpu_to_host` absorbs the leftover GPU work. Then "faster only if the pixels stay on the GPU" is not established.
- `gpu_batch5` also never forces a host sync between reps (`:89-95`), so its median may reflect pipelined throughput rather than latency.
- Not recorded: which nvJPEG backend nvImageCodec picked (GPU vs hybrid with CPU Huffman). The JSON has only `ImageBufferKind.STRIDED_DEVICE`, and host CPU time is not recorded.
- **Fix:** make the F15 title and implication 10 conditional: "if `__cuda_array_interface__` access synchronises (NOT VERIFIED)". Add the backend as NOT VERIFIED.

### W9. "Quality targets" paragraph and implication 9: "camera JPEGs sit at about target A" is an inference
- **source (HANDOFF §1.1):** the measured facts are that the camera quant tables are nearest IJG q94, and that libjpeg-turbo q94 on raw YUY2 frames from the same models gives target A. HANDOFF labels the equivalence "inferred". HANDOFF §4 leaves open why the camera 1080p JPEGs are much smaller than libjpeg-turbo q94 on the same models' YUY2.
- **Fix:** "camera JPEGs use q94-equivalent tables, which HANDOFF 1.1 infers to be about target A; their fidelity to the scene is not measured". Label it inferred in implication 9 too.

### W10. Implication 3: "MKV is now favoured on open cost" is argued only against per-frame-fragment fMP4
- **measured, cross-topic:** fMP4 with 1 s fragments opens in 42.57 ms (cv2 open + count) at 54,000 frames (`RES/jpeg_passthrough/bench/open_long.json`). 16 files serially is about 0.7 s (arithmetic), which is acceptable. The HANDOFF headline still calls fMP4 (1/1e6) the leading container (HANDOFF §4).
- **Fix:** "MKV beats per-frame-fragment fMP4 on open cost. Against 1 s-fragment fMP4 the open cost is small either way, and the choice rests on crash behaviour (fragment loss vs MKV's invalid count until recover())." The "16 × 372 ms ≈ 6 s" arithmetic assumes serial opens; say so.

### W11. F13 "one fragment per frame" was inferred; now measured
- **measured (verifier, functional, PyAV 19.0.2, no timing):** `X/moof_check.py` wrote 30 c922 720p corpus JPEGs with `RecordingWriter(container="mp4f")` and counted top-level boxes: `{"ftyp": 1, "moov": 1, "moof": 30, "mdat": 30, "mfra": 1}`.
- **Fix:** relabel as measured, citing this report. Note also that `close()` writes an `mfra` box, which a killed file will not have.

### W12. Implication 9: "37% faster than cv2"
- **arithmetic:** 1 − 3.3434 / 5.2931 = 0.368, which is 37% **less time** per call. As a rate it is 5.2931 / 3.3434 = 1.58×, i.e. 58% faster.
- **Fix:** "37% less time per call (1.58× the rate)".

## Checked and sound
- Single runs are disclosed per finding and in section 5; phase C reps and per-call spreads are not presented as run-to-run spread.
- P-core pinning is disclosed. The libx265 affinity flag and the NVENC 12-session flag do not apply here (no encoder in items 24/39/40; `affinity: pcores` in the log for all three).
- CPU timer flag: correctly not applicable (wall-clock `perf_counter_ns` only).
- F12 `max_queue_depth` is a valid maximum: it is sampled after each put, the only point where depth grows (`S/recwriter.py:307-320`).
- F13 counts are correctly limited to ideal timestamps, with F3 cited for real timing.
- No quality-dependent number from this topic is confused with the ~55 dB intra_playback clips.
- Intra vs GOP: not applicable (passthrough of all-keyframe JPEG; decode only).

## Functional check run
- `uv run --script X/moof_check.py X/out` (PyAV 19.0.2, numpy 2.2.6; under 10 s CPU; no timing; media deleted after the count). Output above (W11).
