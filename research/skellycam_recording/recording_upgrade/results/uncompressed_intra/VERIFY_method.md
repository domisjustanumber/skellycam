# uncompressed_intra: adversarial verification, methodology lens (2026-11-10)

Target: the draft FINDINGS.md revised after the quiet bench (run `20261109T230007`, items 35 / 56 / 57). The draft was not on disk. The previous report is now `VERIFY_method.prev.md`.

Verifier: Gerald, 2026-11-10, with other agents running. **No timed measurement was run.** Two functional checks were run (PyAV 19.0.2 via `uv run --script`, under 1 min CPU each, no timing). Their JSON is in `verify_method/`. Their scripts are in the scratchpad (`.../scratchpad/step2/ui_vm/`), and the media went to `C:/Users/Dom/Documents/skellycam-raw/.../uncompressed_intra/verify_method_step2/` and was deleted afterwards.

Paths are relative to `results/uncompressed_intra/` unless they start with `results/` (= `research/skellycam_recording/recording_upgrade/results/`).

## 1. What I re-derived from the JSON (all confirmed)
- **measured:** all 36 `bench/*_q2300.json` files have 3 reps with `packets` 300 and `decode_frames` 300, `av_version` 19.0.2, `threads` as named, `unique_frames` 8 and `looped` true.
- **measured:** every fps, cores/stream, KB/f, p99 and decode number in draft §2.7, §3.1 and §3.2 matches `stats` (median, min, max) to the stated rounding. `prep_ms_per_frame` is 1.415-1.490 ms for YUY2→yuv422p and 0.338-0.358 ms for NV12→yuv420p.
- **measured:** all 108 `encode_cpu_s` values are whole multiples of 15.625 ms. NVENC reps register 6-60 ticks.
- **measured:** `latency_max / encode_wall_s` per rep is 3.6-22.7 % for the NVENC cases (720p NV12 h264 21.0-22.7 %, hevc 13.2-13.4 %) and at most 1.7 % for the CPU cases.
- **measured:** `nvidia_smi_before` and `nvidia_smi_after` read `0, 0 %` in all 12 NVENC files.
- **measured** (`results/BENCH_RUN_2300_LOG.jsonl`): the three items ran 02:30:22-02:35:07, 04:19:15-04:28:08 and 04:28:19-04:31:46. Load before: 3.87 / 4.27 / 5.33 %. MsMpEng used 13.14 / 17.92 / 9.22 CPU-s. No Defender scan events. `affinity: pcores`.
- **code** (`scripts/uncompressed_intra/bench_intra.py`):
  - each rep opens a new container and encoder inside `run_once` (lines 137-164); the warm-up is a separate `run_once` (line 191), so the open falls inside every timed rep;
  - the timed window is lines 150-164;
  - decode uses the encode's `thread_count` (line 179);
  - the file is deleted per rep (line 188);
  - `cpu_logical` is `psutil.cpu_count()` and ignores affinity.
- **arithmetic:** every ratio in draft §3.3 checks out.
- **measured:** the "faster than its PyAV 18 row" claim holds for every config re-run except FFV1 s24 Bayer8/NV12 t0, which the draft already lists.

## 2. New functional evidence (closes two NOT VERIFIED items)
- **measured** (`verify_method/exact_check_step2_pyav19.0.2.json`; PyAV 19.0.2; 4 frames each; the bench's own config and path code, `functional_matrix.run_one`):
  - `ffv1_l3_s24_crc_g1.mkv` is bit-exact and all-keyframe at 1080p on NV12 (via yuv420p) and on the Bayer8 mosaic (as gray).
  - At 720p (JPEG-derived), these are bit-exact and all-keyframe: h264_nvenc lossless on NV12 and gray; hevc_nvenc lossless on NV12, P010 and the Bayer8 mosaic.
  - **So "FFV1 s24 on NV12/Bayer8 exactness NOT VERIFIED" and "720p NVENC rows NOT VERIFIED at 720p" should become "exact (4 frames)".** The 720p hevc CQ row is lossy and was not checked.
- **measured** (`verify_method/nvenc_lossless_profile_step2_pyav19.0.2.json`; 2 frames at 1080p):

  | encoder (preset p1, tune lossless) | input | coded profile |
  |---|---|---|
  | h264_nvenc | nv12 | **High 4:4:4 Predictive** |
  | hevc_nvenc | nv12 | Main |
  | hevc_nvenc | p010le | Main 10 |

  - **inferred:** hardware decoders commonly support H.264 only up to High profile, so H.264 lossless output may decode only in software. HEVC Main / Main 10 lossless may be hardware-decodable. Neither is tested here (NOT VERIFIED). This affects §4.1 (see §3).

## 3. Methodology findings

| # | Draft claim | Problem | Severity |
|---|---|---|---|
| M1 | §2.7 Corrections: "the contaminated all-threads FFV1 s24 rows were not lower bounds" and §5 "the P-core affinity probably explains it" | The comparison mixes four changes: PyAV 18 vs 19 (FFmpeg 8.1.2 vs 9.0.2), 28 vs 16 CPUs, 3x90 vs 3x300 frames, and load. The same-version evidence points the other way. The loaded PyAV 19 run of the same config gave 226.42 fps (3x90, `system_cpu_percent_before` 19.8; `bench/ffv1_l3_s24_crc_g1.mkv__yuyv422_1080p__t0__pyav19.0.2.json`), slower than tonight's 241.4. So for PyAV 19 the loaded row *was* a lower bound. The loaded PyAV 18 row (266.39, before-load 11.8) beats the loaded PyAV 19 row, so a version effect fits as well as affinity. | refuted as worded |
| M2 | §4.5 "Use 24 slices with threads (241-323 fps at t0)" | This picks by single-stream peak fps. For a multi-camera recorder the cost per stream matters, and s24 at t0 costs more CPU than s4 at t0: YUY2 0.880 vs 0.672, NV12 0.709 vs 0.519, Bayer8 0.719 vs 0.539, Bayer12 3.358 vs 2.638 cores/stream (+27-37 %; q2300 JSONs). s4 t0 already runs 150-195 fps, 5-6.5x real time. | weak (wrong basis) |
| M3 | §4.1 "Prefer H.264 [over HEVC lossless] unless playback uses NVDEC or threads" | The basis is only single-thread software decode. h264_nvenc lossless is coded High 4:4:4 Predictive and hevc_nvenc lossless is Main (§2 above). If HEVC Main lossless decodes in hardware and Hi444PP does not, the preference could flip. Both are NOT VERIFIED. The t0 (threaded) decode of NVENC files was never benched. | weak |
| M4 | Header "IN target: the NVENC rows" | Requirement 3 asks to cover both Quick Sync and NVIDIA. Lossless intra encode is measured only on NVENC (one RTX 3070); QSV, AMF and VideoToolbox lossless are NOT VERIFIED (draft §6). The *format* (H.264 Hi444PP / HEVC lossless) is therefore not shown to be in target. Only its NVIDIA leg is shown. | weak (label overstates) |
| M5 | §5 "each NVENC cores/stream figure carries ±1 tick: about ±1.7 % to ±17 %" | Process CPU time sums all threads, each quantised, and NVENC runs driver threads. The observed rep-to-rep spread is far wider than ±1 tick: hevc CQ 1080p is 16 / 28 / 22 ticks (0.025-0.044); hevc CQ 720p is 11 / 6 / 14 ticks (0.009-0.022); h264 NV12 1080p is 29 / 35 / 29. | weak (understated) |
| M6 | §4.2 "split the 8-bit mosaic into four quarter planes before NVENC lossless" (681,534 vs 1,368,828 B) | The Bayer8 source is sampled from an rgb24 conversion of ISP-processed 4:2:2 YUY2 (code `uintra_frames.py:21`, `bayer8_from_rgb` line 155). Its R/B samples come from upsampled chroma, so the colour planes are unnaturally smooth. The 2x quad gain is a synthetic-content result. The draft caveats this for 12-bit (§2.1) but not in §4.2. | weak (missing caveat) |
| M7 | §2.5 / §3.1 / §4.4 P010 sizes and speed (1,423.4 KB, 158 fps; 2.75x NV12) | P010 carries 2 seeded noise bits per sample (`uintra_frames.py:19`: "10-bit value = (8-bit << 2) \| 2 noise bits"). RAW10-packed has the same (line 25), and gray16le has 4 (lines 17-18). The draft's noise caveat covers only 12-bit. Both size and lossless encode speed depend on that synthetic entropy. | weak (missing caveat) |
| M8 | §4.5 "One thread already runs 44-45 fps with p99 under 33 ms" | Measured on one i7-14700K P-core (affinity 0-15). The hardware target covers most CPUs from 2020 on. E-cores, laptop parts and older CPUs are untested, and the margin over 30 fps is only 1.47-1.49x (arithmetic). | weak (one SKU generalised) |
| M9 | §5 Defender: "does not apply" | **inferred**, not measured. Each rep closes a new MKV in `Documents` and reopens it at once to decode (code `bench_intra.py:164-176`). Any on-close or on-open real-time scan lands in the untimed close or in the **timed decode** window. MsMpEng used 9.2-17.9 CPU-s per item. Defender's share of the encode and decode numbers is not separated, which the draft also says. | weak (label) |
| M10 | §5 "The libx265 affinity widening does not apply ... the per-item affinity record reads pcores" | `affinity: pcores` is the runner's *requested* mask (code `run_queue.py:441-443`). The uncompressed_intra JSONs have no `process_cpu_affinity` after-check, unlike the intra_compare JSONs in which the widening was found. "Does not apply" holds by inference (no libx265 in items 35/56/57), not by record. | weak (label) |
| M11 | §2.7 "nvidia-smi read 0, 0 % before and after every GPU case, so no other NVENC session ran" | nvidia-smi was sampled only before and after each case, not during it. "No other session ran" is inferred. | weak (label) |
| M12 | "median (min-max) over 3 reps" | The 3 reps are back to back in one process on one night, so min-max is within-run spread only. Run-to-run variation is not measured. | weak (minor) |

Checked and found sound: the open is inside the window; trailer and close are outside; dec fps is single-thread software decode; there is no lossless check in the timed bench; 720p input is JPEG-derived; page-cache decode is labelled inferred; NVENC N=16→12 is correctly kept out of the single-stream numbers; lossy rows are stated at neither A nor B; the GOP note (FFV1 default GOP non-intra) is kept as functional background; the CQ row's i_qfactor note is present.
- One source gap: the i_qfactor note cites `results/intra_compare/FINDINGS.md` line 62. The primary evidence it relies on is FFmpeg n9.0.2 `nvenc.c:835-836` and `options_table.h:151` (excerpts in `results/intra_compare/R/ffmpeg_n9.0.2_knob_excerpts.txt`). Cite those directly.

## 4. Suggested wording changes
- **M1:** replace with: "measured: tonight's FFV1 s24 t0 rows are slower than or equal to the loaded PyAV 18 rows (241 vs 266 YUY2, 323 vs 326 NV12, 308 vs 310 Bayer8). Cross-version loaded rows are therefore not lower bounds for PyAV 19 on 16 P-core CPUs. measured: the loaded PyAV 19 s24 YUY2 t0 row (226 fps, 3x90) is below tonight's 241, consistent with a same-version lower bound. inferred: the difference is FFmpeg version, CPU count, or both. Not separated."
- **M2:** "With threads, s4 is the cheaper choice per stream (0.52-0.67 cores at 8-bit, 2.64 at 12-bit). Use s24 only where single-stream speed matters, at +27-37 % CPU."
- **M3:** add "h264_nvenc lossless is High 4:4:4 Predictive; hevc_nvenc lossless is Main / Main 10 (verify_method/nvenc_lossless_profile_step2_pyav19.0.2.json). Hardware decode of either, and threaded software decode, are NOT VERIFIED, so the H.264 vs HEVC choice is open."
- **M4:** "NVENC rows: hardware-encoded on NVIDIA (measured, RTX 3070). Whether the lossless formats meet the hardware target (QSV leg) is NOT VERIFIED."
- **M5:** "observed rep spread up to 2.3x in ticks (hevc CQ 720p 6-14); treat NVENC cores/stream as order-of-magnitude (about 0.02-0.09)."
- **M6 / M7:** add to §4.2 and §4.4: "sizes and speeds are from synthetic Bayer (from ISP 4:2:2) and synthetic low-bit noise (P010 2 bits, 12-bit 4 bits); real-sensor results NOT VERIFIED."
- **M8:** "on one i7-14700K P-core".
- **M9 / M10 / M11:** relabel as inferred.
- §5 and §6: move FFV1 s24 NV12/Bayer8 and the five 720p NVENC lossless rows from NOT VERIFIED to "exact, 4 frames (verify_method/exact_check_step2_pyav19.0.2.json)".

## 5. Verdict
The numbers are faithful to the quiet-run JSON and the method description is accurate. One conclusion is refuted as worded (M1: the "not lower bounds" correction is confounded by version, and same-version data contradicts its explanation). Several conclusions need caveats or relabelling (M2-M12). Two NOT VERIFIED items are now closed by functional checks. Fix M1-M4 before the FINDINGS is used for PLAN.md.
