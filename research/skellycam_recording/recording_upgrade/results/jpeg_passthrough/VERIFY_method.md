# jpeg_passthrough: VERIFY_method (methodology review, timed-results revision)

2026-11-10, Gerald. Adversarial methodology review of the 2026-11-10 draft FINDINGS (the revision that adds run `20261109T230007`). The draft was given as text and is not on disk. The previous review is now `VERIFY_method.prev.md`.

Paths are relative to `research/skellycam_recording/recording_upgrade/` (RU). No timing was measured. One functional check was run (PyAV 19.0.2 + OpenCV 4.12.0.88, under 1 min CPU, no timing). Its media went to the study media folder and was deleted.

| Script | Result file | What it tests |
|---|---|---|
| `scripts/jpeg_passthrough/verify_method2_mkv_count.py` (uv, av==19.0.2, opencv-python==4.12.0.88) | `results/jpeg_passthrough/verify_method2_mkv_count.json` | OpenCV `CAP_FFMPEG` frame count and fps for MKV and fMP4 1 s (1/1e6) written by PyAV 19.0.2 from the **two real** timestamp series (c930e_720p_flash, c922_720p_flash) |

Every timed number below was recomputed from the `runs` arrays of the four bench JSONs. Everything else in the draft that I checked matched: medians and min-max, run times, MsMpEng CPU-s, affinity "pcores", the 130/130 runs.

## Refuted

### R1. "Container differences of a few µs/frame at 720p are within run-to-run variation" (§2.9.1, §4.3, §5)
- measured (MUX-D vs MUX-F; the in-loop code is identical, and fsync happens only after `close()`, `bench_mux.py:98-113`): for every libav container the two runs' medians differ by −0.3% to +2.8% at 720p and −0.2% to +2.3% at 1080p.
  - mkv 19.04 / 19.05, mp4 17.87 / 17.91, mov 17.97 / 17.96, avi_tb_rate 16.15 / 15.99, nut 17.55 / 17.25, fmp4_1s_tb_us 20.78 / 20.86 µs/frame (720p).
- measured: only the two Python-file baselines move a lot between runs: raw_sidecar +22.4% (19.97 vs 16.32) and jpg_folder +14.4% at 720p (217.93 vs 190.42).
- computed: the 720p order avi < mjpeg_raw < nut < mp4 ≈ mov < mkv < fMP4 repeats in both runs. AVI vs fMP4 1 s 1/1e6 is a 29% difference (16.15 vs 20.78), about 10× the libav run-to-run spread.
- **Correction:** the differences between libav containers are reproducible across the two runs, not noise. The spread between the two runs is large only for the raw_sidecar and jpg_folder Python loops, and its cause is unknown. G5's conclusion still holds, but for a different reason: every container costs a few tens of µs/frame, so the absolute cost is small. Remove "treat as noise" from §2.9.1, §4.3 and §5.

### R2. "MKV counts are wrong whenever the timing is not regular" (§2.4; §4.8 "wrong whenever timing is irregular"; §2.9.5)
- measured (PyAV 19.0.2 writer, OpenCV 4.12.0 reader): MKV from c922_720p_flash's **real VFR** timestamps counts **893 of 893**. The c930e MKV counts 888 of 891 (`verify_method2_mkv_count.json`). Background (PyAV 18): c922 MKV VFR 893 (893), seek 10/10 (`mux_matrix.md` line 98).
- measured: OpenCV reports MKV fps as 30.0 for both cameras, but fMP4 gives 30.10 (c930e) and 29.99 (c922) (same file, `cv2_fps`).
- inferred: OpenCV's MKV count is round(duration × 30). That is exact when the real mean rate is about 30 fps and no frames are missing, and wrong otherwise.
  - Consistent with this: 54,000 × 30 / 30.10 ≈ 53,821, against the measured 53,819 (OPEN).
  - Every wrong MKV count in the draft (888/891, gap60, drop50, 299/300, 53,819/54,000) uses c930e intervals.
- **Correction:** "the OpenCV MKV count is wrong on every gap/drop file and whenever the mean frame rate differs from the nominal rate (c930e, 30.10 fps). It is exact on c922's real VFR (29.99 fps, no drops)." The rule-out in §4.8 still stands on the gap/drop evidence, because real recordings drop frames.

### R3. "16 × 1080p60 would be about 58 ms/s (fMP4 1 s) vs 223 ms/s (folder)" (§2.9.1)
- measured (write_throughput, 16 × 1080p60, threads, same quiet run): the p50 write call is files 2.111 ms, append 0.553 ms and fmp4_frame_flush 0.853 ms (`results/write_throughput/BENCH.md` line 220; `bench/focus16_av19/`).
- computed: that is 9× (files vs jpg_folder 0.233 ms), 13× (append vs raw_sidecar 0.043 ms) and 15× (fmp4_frame_flush vs fmp4_perframe 0.056 ms) this topic's single-stream cost. The ratio between folder and container falls from 4.2× to 2.5×.
- **Correction:** delete the 16× linear extrapolation, or replace it with write_throughput's measured 16-camera numbers. Multiplying a single-stream cost by camera count understates the 16-camera cost by about an order of magnitude on this machine.

### R4. "about 3.9-4.1 GB/s" flush throughput at close (§2.9.2)
- computed (MUX-F `bytes_on_disk` / median `wall_ms_close`): 720p 2.03 GB/s (mjpeg_raw_mux) to 3.87 GB/s (fmp4_1s_tb_us); 1080p 3.68-4.15 GB/s.
- **Correction:** "2.0-4.2 GB/s across writers (3.9-4.1 GB/s for fMP4 1 s at 1/1e6)". This is still inferred to be a whole-file flush.

### R5. "the Rust '~1-2ms per frame' line is now cited at `jpeg_transform.rs:3`" (§2.9.4, §8)
- code: `git show upstream/sfn26:skellycam-rust/src/camera_group/jpeg_transform.rs`. Line 3 reads "Operates entirely in the DCT (compressed) domain — no decode to pixels,". Line 4 reads "no quality loss, ~1-2ms per frame."
- **Correction:** cite `:4`, which is what the previous revision had, and drop the §8 note.

### R6. "5/10 and 7/10 with gaps in all 4 containers tested" (§4.5)
- measured: `verify_method_reader.json` `drop50_mkv.mkv.cv2.seek_exact` is 5, so MKV is 5/10 on both gap files. Only fMP4 1 s, fMP4 per-frame and MP4 give 5/10 (gap60) and 7/10 (drop50). Table 3.1 already has this right.
- **Correction:** state "fMP4/MP4 5/10 and 7/10; MKV 5/10 and 5/10".

## Weak (true or plausible, but the support or wording needs fixing)

| # | Claim | Why weak | Fix |
|---|---|---|---|
| W1 | "inferred: passthrough is therefore at about target A" (header, §4.1) | measured: the cameras' 1080p JPEGs are about half the bytes of libjpeg-turbo q94 on the same models' YUY2 frames (134,574 vs 260,827 B; 192,382 vs 312,812 B; `results/intra_compare/camera_jpeg_quality.md` lines 9-10, 16-17). intra_compare/NOTES.md:156 marks the cause (scene, or in-camera noise reduction) NOT VERIFIED. The same quantisation table does not mean the same fidelity to the sensor. The q94 match was measured on 120 frames per 720p set (lines 7-8). | Keep "about target A" as inferred and add this size gap as the reason it is uncertain. Passthrough is by definition the camera's quality, not a measured point on the A/B scale. |
| W2 | "open cost scales linearly with fragment count (inferred from two points only)"; support cited from the bench's own docstring (§2.9.3, §6) | The docstring states the hypothesis; it is not evidence. A third measured point exists: python_integration's per-frame fMP4 (`recwriter.py:52`, no `min_frag_duration`) with 18,000 frames opens in 370.83-378.58 ms in cv2 (`results/python_integration/bench/recwriter_quiet1_pyav19.json` `c_open_cost.mp4f`). computed: about 20.6 µs per fragment, against 20.5 µs here (1107.28 / 54,000). That writer is different, and its time includes the first read. | Cite it as a third point and drop the docstring as support. |
| W3 | §4.6 "inferred: the sidecar count is cheaper" than a PyAV demux | It is measured elsewhere: reading the append index of an 18,000-frame file takes 0.016 s, against a demux pass of 0.233 s (mkv_flush) or 0.638 s (fmp4_frame_flush) (`results/write_throughput/BENCH.md` line 213). | Cite it as measured. |
| W4 | "That estimate was exact in every 1/1e6 MP4 and fMP4 case" (§2.4) | Plain MP4 stores the frame count: PyAV `stream.frames` is 54,000 for mp4_tb_us (OPEN). OpenCV does not estimate it. | Say "fMP4 (estimated) and MP4 (stored)". |
| W5 | "about 0.2% of one CPU per 1080p30 camera" (§4.3); "about 27% of one logical CPU" for rot270 (§4.11, §2.9.4) | The 0.2% comes from wall time, not CPU, and is single-stream (see R3). Both numbers are for one hyper-threaded P-core logical CPU of an i7-14700K, pinned. E-cores and older 2020+ CPUs (the hardware target) are not covered. | Label both "single stream, Gerald P-core". Say the 0.2% is wall time. |
| W6 | §2.9.1 "inferred: part of [jpg_folder's] cost is Defender real-time scanning" | It is better supported than "inferred". write_throughput measured MsMpEng at 26.8 CPU-s per 30 s cell for a folder of files, against 1.2-1.5 s (idle level) for append, mkv_flush and fmp4_frame_flush (`results/write_throughput/BENCH.md` line 221). In this topic, Defender CPU is logged per item, not per writer. | Cite write_throughput as the measured attribution. Keep this topic's 32.44 CPU-s as item-level only. |
| W7 | ROT run conditions "not load-flagged" (§2.9) | True, but the ROT item had the busiest pre-item window of the four: SearchIndexer.exe 9.36 CPU-s in 10 s, mean 6.03% (`BENCH_RUN_2300_LOG.jsonl` order 60). The 1080p input is 19 distinct frames (about 3.6 MB, likely cache-resident); 720p is 891 frames (about 49 MB). Both are confounders for a real camera stream (inferred). | Add both to §5. The spreads (for example 7179-7262 µs) suggest a small effect, which is inferred. |
| W8 | §4.2 fMP4 1 s is "the only one that is all of the following" | fMP4 per-frame meets every listed bullet except the warm open time. The open-time advantage is warm only, and no cold open was measured. | Say the 1 s vs per-frame choice rests on warm open cost and overhead (131.3 vs 12.4 B/frame), against more frames lost at a kill (578 vs 596, one sample). |

## Checked and accepted (methodology)

- **P-cores:** all four items ran with `affinity` "pcores", and the draft says so. The libx265 widening flag (summary flag 2) concerns intra_compare items 1-3, not these items; the draft says that correctly.
- **NVENC 12 sessions, nvJPEG target miss, WebCodecs errors, N=8 stalls, uncompressed_intra lossless check:** none of these paths is used in passthrough. Listing them as not applicable is correct.
- **Quality targets:** no number in the draft is presented as target A or B, and intra_playback's ~55 dB clips are not used. The draft states that sizes are at the camera's own quality (but see W1).
- **Page cache:** OPEN is clearly labelled warm, with "no cold-open number". The mux runs are labelled page-cache.
- **CPU timer:** the 5.21 µs/frame steps are correctly handled by comparing wall time only.
- **Single runs:** OPEN's demux count (1 run) is labelled. The 5 reps are within one item, and the draft uses MUX-F as a second run.
- **Intra vs GOP:** MJPEG passthrough is intra by construction, and the keyframe flag is shown forced by `mux.c:820-821`.
- **Functional vs compatibility:** Chromium is "inferred, not re-run" for PyAV 19 files. OpenCV "exact seek" is defined against the reader's own decode.
- **One machine:** §6 says "any machine other than Gerald" is not tested. But see W5 for §4.

## Verdict

The timed numbers are transcribed correctly and the run conditions are reported accurately. Six claims need correction:
- R1: libav container differences are reproducible, not noise.
- R2: the MKV count is exact on c922's real VFR; it fails with drops and off-nominal mean rates.
- R3: the 16× linear extrapolation is contradicted by write_throughput.
- R4: the GB/s range.
- R5: the Rust line number is 4.
- R6: MKV drop50 seek is 5/10.

Recommendations §4.2 (fMP4 1 s, 1/1e6), §4.3 (the wrapper doesn't matter for throughput), §4.4 and §4.8 survive with reworded reasons.
