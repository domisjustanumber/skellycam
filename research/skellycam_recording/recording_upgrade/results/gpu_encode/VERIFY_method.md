# gpu_encode: VERIFY (method lens), quiet-run revision

- Verifier: adversarial, methodology lens. Run on 2026-11-10, about 08:50-09:20 EST.
- Target: the updated draft gpu_encode FINDINGS, which adds the run `20261109T230007` numbers. The draft was returned as text and is not on disk.
- The previous method report is kept as `VERIFY_method.prev.md`.
- Paths are relative to `research/skellycam_recording/recording_upgrade/` unless they start with `C:/`.
- No timed measurements were run. Every number below comes from the quiet-run JSON or from a functional or static check.
- New checks: PyAV 19.0.2 via `uv run --script` with PEP 723 pins, each well under 1 min CPU, no timing. Other agents were running at the same time.

## New evidence files

| file | what it shows | script |
|---|---|---|
| `results/gpu_encode/verify_method_fmts.json` | static: the pixel formats each encoder advertises in PyAV 19.0.2 (libavcodec 63.1.102). No device is opened | `scripts/gpu_encode/verify_method_fmts.py` |
| `results/gpu_encode/verify_method_lowpower.json` | functional: hevc_qsv with the target-A options (`+qscale`, `global_quality` 1534, `i_qfactor` 1, `i_qoffset` 0), `gop_size` 1, NV12 1080p, 8 synthetic frames; default vs `low_power=1` vs `preset=veryfast` vs both | `scripts/gpu_encode/verify_method_lowpower.py` |

Re-derived from the quiet-run JSON in this session (read-only):
- `runs[]` order and `process_cpu_affinity` in the three `matched_stream_*` files;
- every GPU scaling file's `runs[]`: opened, keep-up, aggregate fps, cores, late %;
- the `matched_settings.json` `yuy2_1080p` entries.

The helper script is `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step2/gpu_conc_summary.py` (scratchpad, not kept).

## Checks that held

| draft claim | check | result |
|---|---|---|
| 5.3: the NV12 GPU cells ran before the first libx265 cell; the YUY2, MJPEG and RGB cells ran after it | measured: in all three `matched_stream_*` files the order is jpeg_turbo, ff_mjpeg, mjpeg_qsv, nvjpeg, h264_nvenc, hevc_nvenc, h264_qsv, hevc_qsv, libx264 ×2, then libx265 (11th, index 10); `system_before` affinity 0-15, `system_after` 0-27 | holds |
| 5.2: the scaling items are P-core-only | measured: `process_cpu_affinity` has 16 entries before and after in all 21 GPU scaling files | holds |
| 2.4 / 5.4: every N=16 NVENC run opened 12 | measured: `opened` = 12 in every N=16 run of all 7 NVENC scaling files (h264/hevc × nv12, mjpeg_cpu, 720p, plus h264 yuy2); the limit probes give 12/32 for h264 and hevc | holds; the N=16 rows are read as 12 |
| 2.8 medians and ranges (h264_nvenc 0.61 (0.60-0.64) cores, 542 (537-542) fps; hevc_nvenc 0.65 (0.59-0.66); h264_qsv 1.25 (1.23-1.28), 679; mjpeg_qsv 1.05, 700; mjpeg_qsv_422 0.92 (0.86-0.97), 934; nvJPEG 2.56 / 4.68 / 9.3 % late; hevc_qsv 66-67 fps, 98.4 % late at N=4) | measured: recomputed from `runs[]` | holds |
| 2.7: mjpeg_qsv output chroma follows the input | measured: all 8 `raw/mjpeg_qsv_*` files: nv12 → {yuvj420p}, yuyv422 → {yuvj422p}; 19 or 23 points each | holds |
| 2.7 / 3.2: quality of the timed rows | measured: QC hits target A on every NVENC/QSV/mjpeg_qsv row in item 1 (the nvJPEG mjpeg_cpu rows MISS, as the draft says) | holds |
| 5.6: input work is inside the timed loop | code: `benchpaths.py:7-19`; `bench_matched_concurrent.py:46-78` | holds |
| I5 is scoped to "the UHD 770 ... at these settings" | text check | holds, but see W5 |

## Refuted

| draft claim | evidence | correction |
|---|---|---|
| I7: "for YUY2 (4:2:2) cameras, **QSV takes `yuyv422` directly**" | measured, static: `h264_qsv` advertises only `nv12, qsv`. `hevc_qsv` (`yuyv422, y210le, ...`) and `mjpeg_qsv` (`nv12, yuyv422, bgra, qsv`) do list yuyv422 (`verify_method_fmts.json`). measured: the h264_qsv YUY2 row in item 1 paid 8.44 ms CPU/frame against 2.04 from NV12, at the same fps (`matched_stream_A_1080p_20261110T042204Z.json`) | "hevc_qsv and mjpeg_qsv take `yuyv422` directly; h264_qsv takes only NV12, so it needs the same YUY2 → NV12 conversion as NVENC." |
| 6.2: "Whether NVENC accepts packed YUY2 directly in PyAV: NOT TESTED"; I7: "NVENC needs YUY2 → **NV12** first" | measured, static: `h264_nvenc` and `hevc_nvenc` do not list `yuyv422`. They list `nv12`, `yuv420p`, `yuv444p`, `nv16`, `p210le`, `bgr0`, `cuda`, `d3d11` and others (`verify_method_fmts.json`) | Answered: NVENC through PyAV cannot take packed YUY2. It needs a conversion, NV12 being the cheapest option the bench timed. `nv16` (4:2:2) is advertised, but Ampere has no 4:2:2 encode (source, 2.12), so 4:2:2 output was not tried. |

## Weak (needs a fix)

**W1. Table 3.2 header says "P-cores", but some cells may have run on all 28 CPUs.**
- The header reads "(P-cores; single stream and 30 fps scaling)". These single-stream cells ran after libx265 widened the affinity (measured, run order above):
  - mjpeg_qsv_422 YUY2 481;
  - nvjpeg_422 YUY2 343;
  - camera MJPEG → h264_nvenc 228;
  - mjpeg_qsv decode → h264_qsv 554.
- 5.3 says this correctly, but the table and 2.7 / 2.8 don't carry it.
- Fix: mark these single-stream cells "affinity 0-27 possible (5.3)". The scaling columns are P-core-only.

**W2. I7's swscale comparison sets a P-core cell against a possibly all-core cell.**
- "1.40 → 6.67 ms/frame" compares an NV12 cell that ran before libx265 with a YUY2 cell that ran after it.
- A clean P-core-only comparison exists: item 45 (`matched_concurrent_h264_nvenc_420_1080p_yuy2_thread_20261110T084300Z.json`, affinity 0-15) against item 4. The figures (measured, 2 and 3 reps):
  - 12 paced streams: YUY2 2.41-2.64 cores against NV12 0.60-0.64;
  - unpaced N=1: YUY2 1.94-3.36 cores at 511-512 fps against NV12 0.67-0.85 cores at 508-516 fps.
- The direction holds.
- Fix: cite item 45 as the primary evidence and keep the item-1 numbers with the 5.3 caveat.

**W3. The "× jt422" byte ratios compare 4:2:0 outputs with a 4:2:2 reference, and are matched on luma only.**
- The reference row is libjpeg-turbo 4:2:2. Measured, target A, 1080p, item 1, same-chroma comparison:
  - mjpeg_qsv_420 is 276,187 / 255,423 (jpeg_turbo_420 from NV12) = **1.08 × jt420**;
  - mjpeg_qsv_422 is 308,099 / 286,974 = 1.07 × jt422;
  - nvjpeg_420 is 225,514 / 255,423 = 0.88 × jt420;
  - h264_nvenc is 157,924 / 255,423 = 0.62 × jt420 (arithmetic).
- So I9's "0.96 × libjpeg-turbo (4:2:0 from NV12)" reads as if mjpeg_qsv were smaller than libjpeg-turbo. At the same chroma it is about 8 % **larger**.
- The QC metric is luma-only: mjpeg_qsv_420 and _422 have identical QC (52.967 dB / 0.99695). Matching is on SSIM-Y only; chroma fidelity differs. In the sweep, `psnr_yuv_422` is 52.011 for _420 and 52.506 for _422 (`matched_settings.json`).
- Fix: give the same-chroma ratio next to every × jt422 ratio, or say "vs 4:2:2 libjpeg-turbo" each time. Reword I9 to "about 7-8 % larger than libjpeg-turbo at the same chroma".

**W4. nvJPEG's "1.44 dB lower PSNR-Y" comes from a different input than the timed sizes it is paired with.**
- The 50.797 dB matched value comes from the sweep, which fed exact float RGB (`matched_settings.json` → nvjpeg_420 `options.input`).
- The timed NV12/YUY2 rows go through swscale `rgb24`.
- On the item-1 QC (first 4 frames), nvjpeg_420 NV12 scores 52.344 dB against jpeg_turbo_422 52.82 dB, a 0.48 dB gap. The sweep gives 50.797 against 52.24, a 1.44 dB gap.
- Fix: say which input each figure is for. I2's "0.79-0.88 × at 1.44 dB lower PSNR-Y" should be "0.88 × at the same chroma; the PSNR-Y gap is 1.44 dB in the sweep (exact RGB) and 0.48 dB in the 4-frame QC of the timed path".

**W5. The hevc_qsv ceiling may be a mode artefact.**
- I5 and 3.2 present 66-67 fps as the UHD 770's hevc_qsv capacity.
- measured: the item-1 GPU Engine counters put hevc_qsv on the iGPU **3D** engine (89-91 %, VideoDecode 8-13 %). h264_qsv and mjpeg_qsv load the video engine (VideoDecode 47-87 %).
- measured, functional: hevc_qsv accepts `low_power=1`, `preset=veryfast` and both, with the target-A options. Each gives 8/8 keyframes, and the byte counts differ from the default (22,881,310 / 23,230,445 / 22,792,419 / 23,030,886 B on synthetic noise), so the options change the encode (`verify_method_lowpower.json`).
- inferred: the default probably ran the EU (non-VDENC) path. A low-power run might be much faster. Speed and quality in these modes are NOT TESTED.
- Fix:
  - I5: say "at the default (non-low-power) mode; `low_power=1` opens but is untimed".
  - 6.2: name `low_power` explicitly.
  - Don't drop hevc_qsv as a class until that is timed.

**W6. Table 3.2's "limit" column mixes the session-open limit with the throughput limit.**
- "none to 32" for h264_qsv and mjpeg_qsv is the open probe: 2 frames per encoder.
- The unpaced aggregates bound 1080p30 streams at about 679/30 ≈ 22 (h264_qsv), 700/30 ≈ 23 (mjpeg_qsv_420) and 934/30 ≈ 31 (mjpeg_qsv_422) (arithmetic, thread workers, P-cores).
- Fix: split the column into "sessions opened" and "throughput ceiling (inferred, aggregate ÷ 30)".

**W7. nvJPEG's scaling limit is for threads in one process.**
- I2, 2.8 and 3.2 say nvJPEG from NV12 keeps up with only 8, and give "host conversion (inferred)" as the limit.
- Every nvJPEG scaling item used `--workers thread` (file names). The script docstring says GIL-holding work "shows up as flat scaling" (`bench_matched_concurrent.py:10-11`). No process-worker nvJPEG run exists.
- Fix: say "thread workers, one process". The GIL is a possible confounder alongside swscale; process-mode nvJPEG is NOT TESTED.

**W8. Single-stream fps and the scaling items' N=1 unpaced fps disagree by up to 40 %. The draft mixes them in one table.**
- measured, median over reps:

  | path · source | item 1 (≥ 3 s per rep) | scaling N=1 unpaced (300 frames, ≤ 1.6 s) |
  |---|---|---|
  | nvjpeg_420 NV12 | 323 | 192 |
  | mjpeg_qsv_422 YUY2 | 481 | 317-324 |
  | mjpeg_qsv_420 NV12 | 602 | 405-407 |
  | h264_qsv | 585 | 542 |
  | h264_nvenc | 540 | 512 |

- The short scaling runs time 300 frames after a 5-frame warm-up and include the encoder flush in the timed span (`bench_matched_concurrent.py:46-78`). Why the gap is this large is not established (inferred candidates: QSV pipeline depth and start-up inside a ≤ 1.6 s run).
- Fix: state in 3.2 that the two methods are not interchangeable. Don't derive scaling efficiency by dividing the N=16 aggregate by the item-1 single-stream fps.

**W9. CPU per frame differs by method, and I7 quotes the lowest value.**
- I7 says "mjpeg_qsv writes 4:2:2 JPEG at 0.66-1.58 ms CPU/frame" (single-stream, items 1-2, post-libx265 cells).
- measured, P-core-only item 33:
  - 16 paced streams: 0.86-0.97 cores / 480 fps = 1.8-2.0 ms/frame;
  - unpaced N=16: 2.03-2.21 cores / 932-936 fps = 2.2-2.4 ms/frame (arithmetic).
- Fix: quote the scaling figure for recorder sizing, or give both.

**W10. Defender: the caveat cites the wrong cost.**
- 5.11 cites MsMpEng 9.16 / 48.86 CPU-s during items 4 and 7. Those items write no files: packets are discarded (`bench_matched_stream.py:12`; `stream_loop` only counts bytes, `bench_matched_concurrent.py:62,75`). So that MsMpEng CPU is background, not caused by the encode.
- The cost that matters for recording is not in any gpu_encode number: Defender scanning the written output.
  - write_throughput measured that cost: folder-of-files 26.8 CPU-s per 30 s cell, against 1.2-1.5 s for container writers (`BENCH_RUN_2300_SUMMARY.md` §4).
- Fix: say every GPU number here excludes muxing, disk writes and Defender's write-path cost. Point to write_throughput for it. A single container file per camera (the normal output of these encoders) is in the low-Defender group there.

**W11. Intra is inferred, not measured, in the timed runs.**
- The timed benches record packet counts but no keyframe flags (`bench_matched_stream.py`, `bench_matched_concurrent.py`: no `is_keyframe`). All-intra is shown only by the untimed sweeps with the same options (2.2, `raw/*.json` `all_intra`) and by `gop_size` from `matched_settings.json` (`benchpaths.py:147`).
- Fix: label the timed rows' intra status "inferred from identical settings", as BENCH_RUN_2300_SUMMARY flag 8 does for CR-FRAG-INTRA.

**W12. Section 2.9 (intra_playback pointer) is a functional pass presented without the run's flags.**
- "seek frame-exactly" is the functional result on about 55 dB clips.
- The quiet run flagged 914 hidden WebCodecs scrub errors in E35, GPU-process memory growth to 9-38 GB, and stalled tiles in N=8 `<video>` sync (`BENCH_RUN_2300_SUMMARY.md` §3, flags 5-6). Those are what matter for G9 use.
- Fix: add "functional seek only; scrub reliability and multi-stream sync have open flags (summary §3.5-3.6); the intra_playback draft is unverified".

**W13. Section 2.9 (uncompressed_intra pointer) omits flag 9.**
- The timed uncompressed_intra bench has no lossless check. Exactness comes from functional files, and the 720p NVENC rows have no PyAV 19 exactness file (`uncompressed_intra/BENCH.md` lines 89-94: "1080p only checked").
- Encoder open falls inside the timed window, at 3.6-22.7 % of NVENC wall time.
- Fix: add both points to the h264/hevc_nvenc lossless bullet.

**W14. Hardware results from one SKU are generalised.**
- I9 says "hardware encode on Intel iGPUs from TGL/ICL on (source) **at about libjpeg-turbo size**". The size and speed come from one UHD 770 (RPL-S) with one Windows driver (Intel 32.0.101.7088 per the summary §2). The generation list comes from Linux driver docs.
- KBLx also lists JPEG encode (source, 2.12), so "from TGL/ICL on" understates the source.
- I3's "one GeForce GPU cannot ..." rests on one driver (610.88) plus the current support matrix. The session cap is a driver-side limit (inferred).
- Fix:
  - I9: say "size and speed measured on UHD 770 only; other generations NOT VERIFIED".
  - I3: say "with driver 610.88 and the matrix as fetched 2026-11-09".

**W15. I8 calls nvJPEG "not a re-encode route for MJPEG cameras", which is stronger than the evidence.**
- The miss is measured for the tested pipeline only: CPU decode, then swscale rgb24, then nvJPEG. The cause is inferred to be the swscale RGB step (2.7).
- Fix: say "misses A and B in the tested pipeline (swscale RGB); an exact-RGB or YUV-input route is NOT TESTED".

**W16. "Keeps up" allows late frames, and the bullets drop them.**
- I2 gives "16 × 1080p30 at 4.68 cores" for nvJPEG 4:2:2 without its 5.3-13.3 % late frames over 2 reps.
- h264_qsv from mjpeg_qsv decode has 1.1-4.2 % late at N=1-8 but 0 at N=16 (measured, 2 reps). That non-monotonic pattern says late % is noisy at 2 reps.
- mjpeg_qsv_420 has 2.9-5.8 % late at N=1.
- Fix: carry the late % wherever "keeps up" is used for these paths.

**W17. Minor.**
- Status bullet 4 is missing a verb ("This file background to ...").
- 3.2 marks "16 (16 tested)" for h264_qsv but plain "16" for mjpeg_qsv and nvJPEG 4:2:2, although every path was tested only to 16.
- I3's "hevc_nvenc 390 fps < 480" holds at preset p4 only (target A, QP 12), and at target B (425 fps). Faster presets were not tried.
- Fix: correct the wording, use the same "(16 tested)" label everywhere, and add "at p4" to I3.

## Verdict

**Mostly sound; revise before saving.**
- The quiet-run numbers, the 12-session reading, the libx265 run-order analysis and the mjpeg_qsv chroma correction all check out against the JSON.
- Two statements are wrong and must change:
  - I7's "QSV takes yuyv422 directly" (h264_qsv does not);
  - 6.2's "NVENC + packed YUY2 NOT TESTED" (static check: not advertised).
- The main methodology gaps:
  - × jt422 ratios compare 4:2:0 outputs with a 4:2:2 reference and are luma-matched; mjpeg_qsv is 1.08 × at the same chroma, not 0.96 ×;
  - the P-core label sits on cells that may have run after the affinity widened;
  - the hevc_qsv ceiling was measured only in the default mode, which appears to be the EU path;
  - nvJPEG scaling was run with thread workers only;
  - the Defender caveat cites background CPU instead of the write-path cost these numbers exclude.
