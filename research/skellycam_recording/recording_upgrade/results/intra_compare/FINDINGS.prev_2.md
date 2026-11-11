# intra_compare FINDINGS: JPEG vs H.264/HEVC intra at matched quality (PyAV 19.0.2)

Version 2026-11-10 (revised after verification). It replaces the unverified 2026-11-09 draft. It adds the quiet timed run `20261109T230007` (items 1–11, 31–34, 41–45, 49–55). OV-COST (run `20261110T053653`) is not an intra_compare item.

Labels: **measured** = a result file; **source** = primary source (URL, quote, access date); **code** = file:line; **inferred** = reasoning, kept short and marked. Unverifiable = **NOT VERIFIED**.

Paths:
- `R` = `research/skellycam_recording/recording_upgrade/results/intra_compare/`
- `B` = `R/bench/`
- `S` = `research/skellycam_recording/recording_upgrade/scripts/intra_compare/`

Bench JSON aliases (all in `B`):

| alias | file |
|---|---|
| S-A1080 | `matched_stream_A_1080p_20261110T042204Z.json` (item 1) |
| S-A720 | `matched_stream_A_720p_20261110T043459Z.json` (item 2) |
| S-B1080 | `matched_stream_B_1080p_20261110T044204Z.json` (item 3) |
| C-h264nv / C-hevcnv | `matched_concurrent_{h264,hevc}_nvenc_420_1080p_nv12_thread_20261110T044648Z / T045146Z.json` (items 4, 5) |
| C-h264qsv / C-hevcqsv | `matched_concurrent_{h264,hevc}_qsv_420_1080p_nv12_thread_20261110T045738Z / T051629Z.json` (items 6, 7) |
| C-mjqsv | `matched_concurrent_mjpeg_qsv_420_1080p_nv12_thread_20261110T052313Z.json` (item 8) |
| C-nvj | `matched_concurrent_nvjpeg_420_1080p_nv12_thread_20261110T052842Z.json` (item 9) |
| C-jt-proc / C-jt-thr | `matched_concurrent_jpeg_turbo_420_1080p_nv12_{process_20261110T053417Z,thread_20261110T053447Z}.json` (items 10, 11) |
| C-jt422 | `matched_concurrent_jpeg_turbo_422_1080p_yuy2_process_20261110T063244Z.json` (item 31) |
| C-nvj422 | `matched_concurrent_nvjpeg_422_1080p_yuy2_thread_20261110T063635Z.json` (item 32) |
| C-mjqsv422 | `matched_concurrent_mjpeg_qsv_422_1080p_yuy2_thread_20261110T064127Z.json` (item 33) |
| C-hevcqsv422 | `matched_concurrent_hevc_qsv_422_1080p_yuy2_thread_20261110T065430Z.json` (item 34) |
| C-h264nv-mj / C-hevcnv-mj | `matched_concurrent_{h264,hevc}_nvenc_420_1080p_mjpeg_cpu_thread_20261110T081938Z / T082302Z.json` (items 41, 42) |
| C-h264qsv-mjq / C-hevcqsv-mjq | `matched_concurrent_{h264,hevc}_qsv_420_1080p_mjpeg_qsv_thread_20261110T082702Z / T083946Z.json` (items 43, 44) |
| C-h264nv-yuy2 | `matched_concurrent_h264_nvenc_420_1080p_yuy2_thread_20261110T084300Z.json` (item 45) |
| C720-* | `matched_concurrent_<path>_720p_nv12_{thread,process}_…Z.json` (items 49–55): h264_nvenc T085446Z, hevc_nvenc T085747Z, h264_qsv T090121Z, hevc_qsv T090841Z, mjpeg_qsv T091225Z, nvjpeg T091527Z, jpeg_turbo (process) T091904Z |

Verifier reports: `R/VERIFY_provenance.md` and `R/VERIFY_method.md` (both 2026-11-10). The method report holds two functional checks used below: **F1** (libx265 and process affinity, §1.1) and **F2** (encoder output delay, §1.2).

Changes from the 2026-11-09 draft:
- Added timed single-stream and scaling results from the quiet run. The draft's "no timing, no CPU cost" limit is removed.
- The draft's size ratios are sweep interpolations at the exact target. The bench runs the chosen integer setting, so its ratios differ slightly (for example nvJPEG 4:2:0 0.79 vs 0.74, hevc_qsv 0.41 vs 0.39, mjpeg_qsv 4:2:0 0.96 vs 1.00). Both are given and labelled.
- Corrected the draft's list of re-encodes larger than the camera's JPEG (§2.3).
- Corrected the draft's table label "mjpeg_qsv 4:2:0". The mjpeg_qsv rows are 4:2:0 when fed NV12 and 4:2:2 (`yuvj422p`) when fed YUY2 (§2.1).
- `R/NOTES.md` holds stale cells. This text uses `R/matched_summary.md`, which agrees with `R/matched_settings.json`. The stale cells are:
  - §6 line 179: h264_nvenc yuy2_720p 83,921 (now 83,913);
  - §6 line 181 and line 208: hevc_nvenc mjpeg_720p / mjpeg_1080p 55,112 / 144,376 (now 53,975 / 141,655);
  - §1 line 54: libx264 ultrafast "1.41-1.52x passthrough" (now 1.42 / 1.53).

## 1. Questions answered

1. At matched quality, how large are JPEG, H.264 intra and HEVC intra frames for each encoder path and input type? This is G7's cost question (requirement 9).
2. How fast are these paths, and how much CPU and GPU do they use, for one stream at target A and target B?
3. How many 1080p30 and 720p30 streams can each path sustain, including 4:2:2 and the real recorder pipelines from camera MJPEG and YUY2? What session limits apply? (G6, hardware target)
4. Which settings hit the targets, and which pitfalls change the quality silently?

## 2. Findings

### 2.1 Method and verification (functional sweep, no timing)

- measured: the sweep covered 994 points over 16 intra-only paths and 4 input classes, a total of 73,556 frame encodes (counted from `R/raw/*.json`).
  - Every point decoded back in PyAV 19.0.2 software decode with frames out = frames in.
  - Failed points: 0 (`R/verification.md`, last line).
- measured: every H.264/HEVC packet is IDR only (H.264 NAL 5; HEVC 19, or 20 from libx265).
  - Parameter sets repeat in every packet, the decoder reports `has_b_frames` = 0, and every decoded frame is pict_type I.
  - ffprobe of the saved samples agrees (`R/verification.md`).
- measured: the output chroma follows the input.
  - mjpeg_qsv fed `yuyv422` decodes as `yuvj422p`; fed `nv12` it decodes as `yuvj420p`.
  - hevc_qsv fed `yuyv422` gives Rext `yuv422p` (`R/verification.md`, rows mjpeg_qsv_422/420 and hevc_qsv_422).
- measured: profiles.
  - h264_nvenc, h264_qsv and libx264 veryfast: High. libx264 ultrafast: Constrained Baseline.
  - hevc_nvenc and hevc_qsv 4:2:0: Main.
  - **libx265 all-intra 4:2:0: Rext** (`R/verification.md`; `R/NOTES.md` §8).
- code: inputs and conversions are explicit numpy (`S/iclib.py`).
  - JPEG paths are fed full range and H.264/HEVC paths limited range.
  - For the MJPEG classes, metrics are generation loss against the decoded camera frame (`R/matched_settings.json` `_meta.metric_note`; `R/NOTES.md` §2).
- code: the sweep fed nvJPEG exact float BT.601 RGB (`R/matched_settings.json` nvjpeg_420 `options.input`: "host RGB24, exact float BT.601 from the 4:2:2 source"). A recorder would not have that input; the bench's swscale feed is in §2.4 and §2.7.
- code: SSIM-Y uses Wang et al. parameters (Gaussian σ 1.5, K1 0.01, K2 0.03, 5-pixel border excluded). PSNR-Y and SSIM-Y use the same source-Y reference for every path (`S/iclib.py` `metrics`/`ssim`; `R/NOTES.md` §4).
- measured: the bench JSONs record PyAV 19.0.2, libavcodec 63.1.102, simplejpeg 1.9.0, nvimgcodec 0.10.0 and Python 3.12.13 (`system_before` in all 27 files).
- measured: the libjpeg-turbo 3.1.2 build and the nvidia-nvimgcodec-cu12 0.10.0.9 wheel version come from the sweep's `R/raw/*.json` `runs[].versions`. The bench JSONs do not record them.

### 2.2 How targets A and B were derived

- measured: the C930e and C922 camera JPEGs use one fixed DQT set per set. The nearest IJG quality is q94 for luma and chroma in all four sets, but the tables are not exact (summed abs error 124 luma, 60 chroma) (`R/camera_jpeg_quality.md`).
- measured: libjpeg-turbo q94 4:2:2 on the same models' raw YUY2 1080p frames gives (`R/camera_jpeg_quality.md`):
  - C930e: SSIM-Y 0.99694 / PSNR-Y 52.65 dB;
  - C922: SSIM-Y 0.9952 / PSNR-Y 51.831 dB;
  - mean: SSIM-Y 0.9961 / 52.24 dB.
- **Target A = SSIM-Y 0.9961, "camera-equivalent", about 52 dB PSNR-Y. Dom fixed it as the primary point on 2026-11-10** (HANDOFF.md §1.1).
  - inferred: re-encoding YUY2 at A is about as faithful as the camera's own JPEG.
  - On yuy2_1080p, libjpeg-turbo q94 reaches A by construction.
- **Target B = PSNR-Y 45 dB, the compact alternative.**
  - measured: libjpeg-turbo q50 on yuy2_1080p gives PSNR-Y 45.6 dB / SSIM-Y 0.988 (`R/curves.md`; `R/NOTES.md` §5), so B is about q50 here. The chosen jt422 point at B is q44 (45.09 dB) (`R/matched_summary.md`).
- measured: SSIM-Y saturates near A. jpeg_turbo_422 on yuy2_1080p goes from q90 (SSIM-Y 0.9953, 204,402 B) to q95 (0.9962, 327,395 B), which is +60% bytes for +0.0009 SSIM-Y (`R/curves.md`).
- measured: at equal SSIM-Y (A, yuy2_1080p), the H.264/HEVC points have higher PSNR-Y than the JPEG points (`R/matched_summary.md`):
  - H.264/HEVC, all 8 paths: 53.12–53.36 dB;
  - libjpeg-turbo, mjpeg_qsv and FFmpeg mjpeg: 52.24–52.56 dB;
  - nvJPEG (exact-RGB input): 50.80 dB.
  - inferred: matching on PSNR-Y instead would favour H.264/HEVC slightly more.
- No machine-vision quality test will be run (Dom, HANDOFF.md §1.1).

### 2.3 Sizes at matched quality (sweep, interpolated to the exact target)

Full tables are in §3.1 and §3.2. Ratios are against libjpeg-turbo 4:2:2 (jt422) unless stated.
- measured: **at target A on raw YUY2 1080p**, H.264 intra is 0.53 (h264_nvenc) to 0.59 (h264_qsv) of jt422, and HEVC intra is 0.39 (hevc_qsv) to 0.43 (hevc_nvenc) (`R/matched_summary.md`).
- measured: **at target A against libjpeg-turbo 4:2:0** (jt420, 265,001 B, same chroma subsampling), H.264 is 0.60–0.66 and HEVC 0.44–0.49 (bytes from `R/matched_summary.md`).
- measured: **at target B on YUY2 1080p** the gap widens: H.264 0.29–0.35 and HEVC 0.18 of jt422; against jt420, H.264 0.33–0.40 and HEVC 0.21 (`R/matched_summary.md`).
- measured: matching is on luma only, so the chroma basis matters. At A the hardware 4:2:0 H.264/HEVC points score `psnr_yuv_422` 53.06–53.25 dB, against 52.41 for jt422 and 51.96 for jt420 (`R/matched_settings.json`, yuy2_1080p). So jt422 is not ahead on a chroma-inclusive PSNR either.
- measured: on YUY2 720p (derived by swscale) the ratios are similar: at A, H.264 0.51–0.56 and HEVC 0.36–0.40 of jt422 (`R/matched_summary.md`).
- measured: **on decoded camera MJPEG at A, the codecs are closer together**.
  - NVENC/QSV H.264/HEVC are 0.70–1.02x jt422 and 0.64–0.91x the camera passthrough bytes.
  - Passthrough is 66,594 B/frame at 720p and 163,478 at 1080p (`R/matched_summary.md`; `R/camera_jpeg_quality.md`).
  - code: for MJPEG classes, A is measured against the decoded camera frame (`R/matched_settings.json` `_meta.metric_note`). inferred: a re-encode "at A" carries the camera's loss plus its own, so ratios to passthrough compare bytes at **lower fidelity to the scene than passthrough**, not at equal fidelity.
- measured: re-encodes at A that are **larger** than the camera's JPEG (`R/matched_summary.md`):
  - at 720p: libx264 ultrafast (1.42x) and libx265 ultrafast (1.02x);
  - at 1080p: libx264 ultrafast (1.53x) and nvJPEG 4:2:2 (1.07x).
  - Just under passthrough: libx265 at 1080p (0.99x), nvJPEG 4:2:0 at 1080p (0.99x) and nvJPEG 4:2:2 at 720p (0.98x). This corrects the draft's list.
- measured: hardware JPEG against libjpeg-turbo at the same chroma (`R/matched_summary.md`):
  - mjpeg_qsv: 0.99–1.12x at A and B;
  - nvJPEG (exact-RGB input) at A: 0.81–0.84x on YUY2 and 1.08–1.24x on decoded MJPEG; at B: 1.04–1.14x on every class.
  - At A, nvJPEG's PSNR-Y is 1.4–2.2 dB under libjpeg-turbo's at equal SSIM-Y.
- measured: 4:2:2 against 4:2:0 at the same knob, at target A (`R/matched_summary.md` chosen points; `R/NOTES.md` §7):
  - JPEG: 1.07–1.17x bytes;
  - hevc_qsv Rext: 1.13–1.33x;
  - PSNR-Y is identical in every pair at A.
  - At B, hevc_qsv_422 differs from hevc_qsv_420 by 0.01–0.02 dB (for example 45.07 vs 45.08 on yuy2_1080p); the B byte ratios fall inside the A ranges (VERIFY_provenance R2).
  - measured: the timed bench does not keep luma equal for hevc_qsv fed decoded MJPEG. QC PSNR-Y is 49.97 (4:2:2) vs 52.53 (4:2:0) at 1080p A, and 49.53 vs 52.00 at 720p A. From YUY2 they are equal (54.069 vs 54.071) (S-A1080, S-A720; §2.7).
- measured: hevc_nvenc is larger than h264_nvenc at A on MJPEG inputs (53,975 vs 46,217 at 720p; 141,655 vs 123,426 at 1080p). It is smaller at B and on YUY2 (`R/matched_summary.md`).
- measured: FFmpeg `mjpeg` 4:2:0 is 0.78–0.84x libjpeg-turbo 4:2:0 at A on YUY2, but 0.92–0.97x at B and 0.97–1.03x on MJPEG inputs at A (`R/matched_summary.md`).
  - The cause is NOT VERIFIED. It is not Huffman optimisation (`R/dht_check.json`).
- measured: at A, the decoded camera JPEGs need about half the bytes of the YUY2 frames: jt422 needs 145,774 B on mjpeg_1080p against 297,359 B on yuy2_1080p (`R/matched_summary.md`). See §6 for the open loose end.

### 2.4 Single-stream speed, CPU and GPU (items 1–3; one thread, unpaced, packets discarded)

- code: method.
  - Each rep is at least 300 frames and at least 3 s (`S/bench_matched_stream.py:58`).
  - CPU is process user + system CPU over all threads, driver threads included.
  - Packets are discarded, so there is no file I/O (`S/bench_matched_stream.py:12, 69-71`).
  - Values are the median (min–max) of 5 (A 1080p), 4 (A 720p) or 3 (B 1080p) timed reps after 1 warm-up.
- measured: **CPU affinity in items 1–3.** The process started pinned to CPUs 0–15 (8 P-cores with HT). In run order, the first 10 cells (the NV12 rows before libx265) ran on that mask. Every later cell ran after libx265 widened the mask to 0–27 (§5 flag 1). Rows below marked "(0–27 mask)" are not P-core-only figures.
- measured, A 1080p from NV12, CPUs 0–15 (S-A1080):
  - h264_nvenc: 540 (540–540) fps, 1.40 ms CPU/frame;
  - h264_qsv: 585 (585–585) fps, 2.04 ms;
  - hevc_nvenc: 390 (389–390) fps, 1.47 ms;
  - hevc_qsv: 65 (65–66) fps, 2.81 ms;
  - mjpeg_qsv 4:2:0: 602 (601–606) fps, 1.81 ms;
  - libjpeg-turbo 4:2:0: 360 (358–360) fps, 2.77 ms.
- measured, A 1080p from native YUY2, 4:2:2 paths, (0–27 mask) (S-A1080):
  - mjpeg_qsv_422: 481 (481–482) fps, 1.58 ms;
  - jt422: 225 (225–226) fps, 4.38 ms;
  - hevc_qsv_422: 64 (64–64) fps, 3.18 ms.
- measured: feeding 4:2:0 hardware paths from YUY2 adds the swscale yuyv422 → nv12 step to CPU, (0–27 mask) (S-A1080):
  - h264_nvenc: 6.67 ms/frame from YUY2 vs 1.40 from NV12;
  - h264_qsv: 8.44 vs 2.04;
  - mjpeg_qsv_420: 7.56 vs 1.81.
- measured: decoding camera MJPEG on the CPU first (decode + swscale range change, timed), (0–27 mask) (S-A1080, `mjpeg_cpu` rows):
  - 9 of the 13 hardware/JPEG paths run at 152–243 fps, at 6.4–14.4 ms CPU/frame;
  - exceptions: nvJPEG 140–145 fps, and hevc_qsv / hevc_qsv_422 66–68 fps;
  - libx264 runs at 156–198 fps at 17.8–32.0 ms, and libx265 at 108 fps.
- measured: decoding camera MJPEG with mjpeg_qsv first, (0–27 mask) (S-A1080, `mjpeg_qsv` rows):
  - h264_nvenc: 594 fps, 7.62 ms;
  - mjpeg_qsv_420: 609 (432–611) fps, 1.17 ms;
  - h264_qsv: 554 (361–554) fps.
- measured: nvJPEG encode alone, from exact RGB prepared untimed, runs at 1,126 (1,117–1,132) fps at 0.87 ms CPU/frame (0–27 mask). From host NV12 through swscale `rgb24` it drops to 323 (283–341) fps at 7.57 ms (CPUs 0–15) (S-A1080).
  - code: nvJPEG gets RGB through swscale `rgb24` for the nv12, yuy2 and MJPEG sources (`S/benchpaths.py:215, 228, 240`).
- measured, CPU encoders, A 1080p from NV12 (S-A1080):
  - libx264 ultrafast: 372 fps, 14.70 ms (5.5 cores, CPUs 0–15);
  - libx264 veryfast: 229 fps, 31.05 ms (7.1 cores, CPUs 0–15);
  - libx265 ultrafast: 106 fps, 252.95 ms at 26.9 cores, on the mask it widened itself (§5 flag 1).
- measured, A 720p from NV12, CPUs 0–15 except libx265 (S-A720):
  - h264_nvenc: 1,115 fps, 0.56 ms;
  - h264_qsv: 1,151 fps, 0.97 ms;
  - hevc_nvenc: 842 fps, 0.60 ms;
  - hevc_qsv: 128 fps, 1.57 ms;
  - mjpeg_qsv_420: 1,155 fps, 0.75 ms;
  - libjpeg-turbo 4:2:0: 744 (728–764) fps, 1.34 ms;
  - nvJPEG 4:2:0: 617 (579–646) fps, 4.59 ms.
- measured, B 1080p from NV12, CPUs 0–15 except libx265 (S-B1080):
  - h264_nvenc: 635 fps, 1.39 ms;
  - h264_qsv: 691 fps, 1.93 ms;
  - hevc_nvenc: 425 fps, 1.43 ms;
  - hevc_qsv: 87 fps, 2.81 ms;
  - mjpeg_qsv_420: 618 fps, 1.76 ms;
  - libjpeg-turbo 4:2:0: 507 fps, 1.96 ms;
  - nvJPEG: 330 fps, 8.05 ms.
- measured: NVENC paths run the NVIDIA VideoEncode engine at about 97%, with nvidia-smi encoder at 100% for one unpaced 1080p stream from NV12 (S-A1080). Engine counters are per process and summed per engine type (`S/benchpaths.py:429-435`).
- measured: QSV H.264 shows "iGPU VideoDecode" 87% / "3D" 44%. hevc_qsv shows "iGPU 3D" 89–91% (medians of the nv12/yuy2 rows; per-rep 81.0–91.3%) / "VideoDecode" 8% (S-A1080, Windows engine names).
  - inferred: hevc_qsv 4:2:0 runs on a shader-heavy path on this UHD 770. Whether `low_power`/VDEnc would speed it up is NOT VERIFIED (not tested).
- measured: **bench bytes/frame at the chosen settings against the sweep's chosen point** (S-A1080 `bytes_per_frame_median` ÷ `quality_check.matched_bytes_per_frame`):

  | rows | bench vs sweep |
  |---|---|
  | JPEG fed NV12, native YUY2 or exact RGB (libjpeg-turbo, FFmpeg mjpeg, mjpeg_qsv, nvJPEG exact RGB) | within 0.06% |
  | nvJPEG through swscale RGB from NV12 / YUY2 | −0.2 to −0.5% |
  | FFmpeg mjpeg / mjpeg_qsv 4:2:0 from YUY2 | −0.2 to −0.3% |
  | JPEG after MJPEG decode | −0.04 to −2.7% (largest: nvJPEG after mjpeg_qsv, −2.69%) |
  | H.264/HEVC 4:2:0 from NV12 | within 0.13% |
  | NVENC/QSV H.264/HEVC 4:2:0 from YUY2 (swscale) | −1.4 to −1.6% |
  | NVENC/QSV H.264/HEVC 4:2:0 after MJPEG CPU decode | −1.8 to −3.5% (for example h264_nvenc 115,527 vs 119,147) |
  | hevc_qsv_422 after MJPEG CPU decode | −0.5% |
  | NVENC/QSV H.264/HEVC after mjpeg_qsv decode | −1.4 to −2.0% |
  | libx264 / libx265 from MJPEG | −1.1 to −2.8% |

  - measured: S-A720 shows the same pattern; hevc_qsv / hevc_qsv_422 after MJPEG CPU decode are 4.8% / 4.4% smaller.
  - inferred: every feed with a swscale or decoder step differs from the sweep's numpy feed. NOT VERIFIED.

### 2.5 Stream scaling, 1/4/8/16 streams, paced 30 fps and unpaced, all at target A

- code: definitions (`S/bench_matched_concurrent.py:14-16, 127-131`).
  - Paced = 450 frames per stream at 30 fps; unpaced = 300 frames per stream.
  - "Keeps up" = per-stream fps ≥ 0.98 × 30 and end lag < 1/30 s.
  - One thread (or one spawned process) and one encoder per stream.
  - Scaling items have no in-pipeline QC; they use the same `matched_settings.json` entries (`entry` block in each JSON).
- measured: **every scaling item ran pinned to CPUs 0–15 (8 P-cores with HT) of an i7-14700K.** All 24 files record `process_cpu_affinity` 0–15 before and after (`R/BENCH.md` line 4; `results/BENCH_RUN_2300_SUMMARY.md` §2). CPU-bound ceilings below are 16-CPU ceilings, not machine ceilings.
- code: NV12 is made untimed in numpy from the YUY2 frames (`S/benchpaths.py:8-9, 96-97`). measured: the study cameras deliver YUY2 or 4:2:2 JPEG, not NV12 (`R/NOTES.md` §7, line 226). inferred: the NV12 rows are the **best case** for 4:2:0 hardware paths.
- measured: **h264_nvenc 1080p from NV12:**
  - 12 streams (the most that open; §2.6) keep up in all 3 reps with 0 late frames, at 0.61 (0.60–0.64) cores (C-h264nv).
  - Unpaced aggregate medians per N are 512–542 fps for N = 1–12 (single reps 507.5–541.9); nvidia-smi encoder is at 80% at N=12 (C-h264nv).
- measured: **hevc_nvenc 1080p from NV12:** 12 keep up at 0.65 (0.59–0.66) cores. Unpaced aggregate medians per N are 389–391 fps (single reps 380.0–392.2) (C-hevcnv).
  - inferred: on this RTX 3070 at p4/ll and target A, about 390 fps would cap hevc_nvenc at 13 × 1080p30 even without the session limit.
- measured: **h264_qsv 1080p from NV12:** 16 keep up at 1.25 (1.23–1.28) cores. Unpaced aggregate is 679 (678–682) fps at N=16 (C-h264qsv).
- measured: **hevc_qsv 1080p from NV12 tops out at 66–67 fps aggregate at every N.** Only 1 stream keeps up. At N=4 paced, 0/4 keep up in each rep, with 98.4% late and 1,394–1,397 dropped-equivalent frames (C-hevcqsv).
- measured: hevc_qsv_422 from YUY2 behaves the same: 64–65 fps aggregate, 1 stream (C-hevcqsv422). hevc_qsv after mjpeg_qsv decode: 66 fps, 1 stream (C-hevcqsv-mjq).
- measured: **mjpeg_qsv 4:2:0 1080p from NV12:** 16 keep up at 1.05 (1.03–1.05) cores. Unpaced aggregate is 700 (695–705) fps (C-mjqsv).
  - Paced N=1 had 13, 13 and 26 late frames while keeping up; N=4–16 had 0.
- measured: **mjpeg_qsv 4:2:2 1080p from native YUY2:** 16 keep up at 0.92 (0.86–0.97) cores. Unpaced aggregate is 934 (932–936) fps (C-mjqsv422).
- measured: **nvJPEG 4:2:0 1080p from host NV12 (swscale RGB):**
  - N=8: all 8 keep up at 2.56 (2.47–2.57) cores, with 0, 73 and 66 late frames in the three reps (N=4: 3, 0, 4).
  - N=16: 471.0–473.2 fps aggregate of the 480 needed (98.2%); 1, 2 and 3 of 16 streams keep up; 83.6% (72.8–87.2) late; 56–79 of 7,200 frames dropped-equivalent.
  - Unpaced aggregate is 475 (472–477) fps at N=16 (C-nvj).
- measured: **nvJPEG 4:2:2 1080p from YUY2:** at N=16 all 16 keep up at 4.68 (4.63–4.74) cores, but with 5.3% and 13.3% late frames (383 and 955 of 7,200) and paced encode p99 of 39.2–43.7 ms. Aggregate 479.9 fps. Unpaced aggregate is 567 (567–568) fps (C-nvj422).
  - inferred: **nvJPEG is at its limit near 16 × 1080p30 from either feed.** The heavier YUY2 feed "passes" and NV12 "fails" over 2 and 3 reps, so 8 is not a firm ceiling for NV12. Item 32 had the run's highest pre-item load sample (14.7%, §5 flag 11).
- measured: **libjpeg-turbo 4:2:0 1080p, 16 streams, on 16 CPUs:**
  - Unpaced: 3,511 fps as threads at 14.55 cores (1 rep), against 3,572 (3,512–3,579) fps as processes at about 15.3 cores (C-jt-thr, C-jt-proc). Both saturate the 16-CPU pin.
  - inferred: threads scale like processes, so simplejpeg does not serialise on the GIL (1 thread rep).
  - Paced 16 × 1080p30 keeps up at 1.69 (1.59–1.78) cores, a process-mode lower bound (C-jt-proc).
- measured: libjpeg-turbo 4:2:2 from YUY2: 16 keep up at 2.81 (2.48–3.14) cores (process, lower bound). Unpaced aggregate is 1,742 (1,719–1,766) fps (C-jt422).
- measured: **recorder pipelines from camera data, 1080p:**
  - MJPEG CPU decode → h264_nvenc: 12 keep up at 4.06 (4.01–4.10) cores, against 0.61 from NV12. Unpaced aggregate 596 (595–597) fps (C-h264nv-mj).
  - MJPEG CPU decode → hevc_nvenc: 12 keep up at 3.90 (3.77–4.03) cores. Unpaced aggregate 378 (376–379) fps (C-hevcnv-mj).
  - mjpeg_qsv decode → h264_qsv: 16 keep up at 4.33 (4.30–4.35) cores. Unpaced aggregate 486 (476–495) fps, just above the 480 fps needed (C-h264qsv-mjq). Every stream kept up at every N, but late frames were 5, 5 (N=1), 43, 45 (N=4) and 153, 113 (N=8); N=16 had 0.
  - YUY2 → swscale NV12 → h264_nvenc: 12 keep up at 2.53 (2.41–2.64) cores (C-h264nv-yuy2).
- measured: **720p30 from NV12** (C720-*):
  - h264_nvenc and hevc_nvenc: 12 (all that open) at 0.39 / 0.42 cores;
  - h264_qsv: 16 at 0.79 (0.75–0.82) cores;
  - mjpeg_qsv: 16 at 0.57 cores;
  - nvJPEG: 16 at 3.07 (3.02–3.12) cores, 0.9% late;
  - libjpeg-turbo (process): 16 at 2.05 (1.29–2.80) cores, lower bound;
  - hevc_qsv: 4 keep up, but 8 do not (0/8; 134 fps aggregate).
- measured: **paced encode-call p99** at the largest N that keeps up (`encode_ms_p99`, per-run JSON fields):
  - h264_nvenc NV12: 12.4–16.0 ms;
  - h264_qsv NV12: 18.6–23.1 ms;
  - mjpeg_qsv 4:2:0 NV12: 16.0–21.4 ms;
  - libjpeg-turbo process: 5.6–6.7 ms;
  - nvJPEG NV12 at N=8: 17.9–40.3 ms.
  - This is the time of one `encode()` call, **not frame-to-packet latency**. Do not rank latency between JPEG and NVENC/QSV from it.
  - measured (F2, functional, no timing): NVENC (H.264 and HEVC) returns each packet 2 `encode()` calls after its frame; h264_qsv and hevc_qsv 4 calls later; mjpeg_qsv 3 calls later (`R/VERIFY_method.md` §1.2).
  - code: simplejpeg and nvJPEG return the JPEG from the same call (`S/benchpaths.py` `Encoder.encode`).
  - inferred: at 30 fps a frame's packet appears about 67 ms later on NVENC and about 100–133 ms later on QSV. Those 2–4 frames are still inside the encoder if the process dies (relevant to G2).

### 2.6 Session limits

- measured: **NVENC opens at most 12 concurrent sessions in one process, for both H.264 and HEVC.**
  - The limit probe opened 12 of 32. The 13th `avcodec_open2` fails with `ExternalError [Errno 542398533] Generic error in an external library`, and nvidia-smi shows 12 sessions at the peak (C-h264nv, C-hevcnv `limit_probe`).
  - Every N=16 NVENC cell opened 12 encoders, in items 4, 5, 41, 42, 45, 49 and 50.
- source: NVIDIA Video Encode and Decode GPU Support Matrix, https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new, accessed 2026-11-10 (re-fetched by the provenance verifier, `R/VERIFY_provenance.md` §3). Column header: "Max # of concurrent sessions". The GeForce RTX 3070 row shows 12 (all RTX 30 rows show 12).
- measured: **QSV opened 32 of 32** with no error for h264_qsv, mjpeg_qsv 4:2:0 and mjpeg_qsv 4:2:2 (C-h264qsv, C-mjqsv, C-mjqsv422 `limit_probe`).
  - hevc_qsv, simplejpeg and nvJPEG were not probed: their files have `args.limit_probe` = 0.
  - code: the probe would also skip simplejpeg and nvJPEG if requested (`S/bench_matched_concurrent.py:268`).
- measured (other topic): h264_qsv still encodes while 12 NVENC sessions are held (`results/gpu_encode/FINDINGS.md` §2.4).

### 2.7 Quality-check results and misses

- code: the in-pipeline QC is an untimed re-encode of the first 4 source frames through the same pipeline, decoded by PyAV and compared with the source Y (`S/benchpaths.py:266-288` `quality_check`; `S/bench_matched_stream.py:87, 128`).
- code: the sources load C930e first (`S/iclib.py:44-47` `INPUTS`; sorted per set at `:133, :143`), so **all 4 QC frames are C930e frames**. The C922 is never QC'd.
- measured: at A the NV12 QC reads 0.6–0.9 dB PSNR-Y above the two-camera sweep value on every NV12 row except nvJPEG (for example jt420 52.82 vs 52.24, h264_nvenc 54.07 vs 53.22) (S-A1080). nvJPEG reads +1.5 dB, because the sweep fed it exact RGB.
  - This fits the C930e scoring higher than the C922 (52.65 vs 51.83 dB, `R/camera_jpeg_quality.md`).
  - At B the NV12 QC differs from the sweep by −0.28 to +0.40 dB (S-B1080).
- measured: every NV12, YUY2 and exact-RGB row hits its target at A, at 1080p and 720p (S-A1080, S-A720).
  - inferred: a hit shows the setting is not grossly off. The byte match with the sweep (§2.4) is the stronger evidence that the settings transfer to the NV12/YUY2 feeds.
- measured: **nvJPEG fed decoded camera MJPEG (`mjpeg_cpu` → swscale `rgb24`) misses**:
  - A 1080p: SSIM-Y 0.9954 < 0.9961 and PSNR-Y 45.21 dB, against 49.995 in the sweep;
  - A 720p: SSIM-Y hits (0.99737), but PSNR-Y is 45.51 dB against 49.30 matched;
  - B 1080p: PSNR-Y 43.14 dB < 45 (S-A1080, S-A720, S-B1080).
  - inferred: the miss is robust, because the C930e-only QC bias runs the other way.
- measured: nvJPEG in other feeds:
  - the same encoder hits A from NV12/YUY2 through swscale (52.34–52.37 dB) and from exact RGB (51.36 dB);
  - after mjpeg_qsv decode it reaches 56.46 dB (S-A1080).
  - The cause of the spread is NOT VERIFIED. inferred: the swscale conversion from `yuvj422p` is involved.
- measured: **hevc_qsv_422 from decoded MJPEG sits just under A**:
  - SSIM-Y 0.99608 (1080p) and 0.9960 (720p);
  - PSNR-Y is 2.1 dB (1080p) and 2.7 dB (720p) under the sweep value, and 2.5 dB under hevc_qsv_420 on the same feed (S-A1080, S-A720).
  - The sweep's own value at that knob step was also under A (0.99575 / 0.99582) (`R/matched_summary.md`).
- measured: at B 1080p, five rows are under 45 dB by a knob step, and the sweep value was also under 45 dB for each: QC 44.61–44.85 dB (S-B1080).
  - The rows are ff_mjpeg_420, h264_nvenc, h264_qsv and libx264 ultrafast (all from NV12) and hevc_qsv_422 (from MJPEG).

### 2.8 Pitfalls (they change what an implementation records)

- code/measured: **FFmpeg's default `i_qfactor` = -0.8 silently lowers the intra QP.**
  - code: `libavcodec/options_table.h:151`, `nvenc.c:835-836`, `qsvenc.c:922-929` (FFmpeg n9.0.2; excerpts in `R/ffmpeg_n9.0.2_knob_excerpts.txt`; re-fetched from https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/ on 2026-11-10 and matching line for line, `R/VERIFY_provenance.md` §3).
  - measured: requesting QP 25 gives intra QP 20 on h264_nvenc and h264_qsv, and 22 on libx264/libx265 (their own ip factor) (`R/knob_check.json`; `R/NOTES.md` §3).
  - measured: the packet for that frame shrinks when the fix is applied. h264_nvenc: 50,990 → 33,081 B. hevc_nvenc: 36,511 → 22,404 B. h264_qsv: 56,202 → 37,634 B. hevc_qsv: 37,257 → 22,783 B (`R/knob_check.json`).
  - **Fix: `i_qfactor=1, i_qoffset=0`.** Every H.264/HEVC entry in `R/matched_settings.json` carries it, and the bench passed it (`entry.options` in each JSON).
- measured: FFmpeg `mjpeg` ignores `flags=+qscale` + `global_quality` passed as PyAV codec options (`global_quality` 236 and 1416 both give 125,998 B). `qmin=qmax` is the working knob (`R/knob_check.json`).
- code: `mjpeg_qsv` quality is `av_clip(global_quality, 1, 100)` (`qsvenc.c:762`).
- measured: an nvJPEG RGB input made by swscale cost PSNR-Y in the earlier diagnostic: 46.7 dB for the RGB step alone, against 63.1 dB with exact float BT.601 (`R/nvjpeg_rgb_diag.json`).
  - The timed bench reproduces a loss only for the decoded-MJPEG feed (§2.7). The conflict with the NV12/YUY2 swscale-RGB feeds, which hit A, is unexplained (NOT VERIFIED).
- measured: nvImageCodec 0.10.0.9 does not accept YUV input (`results/gpu_encode/nvimgcodec_jpeg.md`, cited in `R/NOTES.md` §9).
- measured: libx265 all-intra 4:2:0 is Rext, not Main (`R/verification.md`).
- measured: every sampled JPEG file uses the standard Annex K Huffman tables: 29 encoder samples and 4 camera sets (`R/dht_check.json`). mjpeg_qsv and nvjpeg_420 have no mjpeg_1080p sample.
  - code: FFmpeg `mjpeg`'s option defaults to `huffman=optimal` (`mjpegenc.c:650`), yet its written tables equal Annex K.
- measured (F1, functional): opening libx265 in PyAV 19.0.2 widens the process CPU affinity and does not restore it (§5 flag 1). An implementation that pins capture threads would lose that pinning.

## 3. Comparison tables

### 3.1 Target A (SSIM-Y 0.9961): bytes/frame at target (interpolated), (× jt422; × camera passthrough)

measured, `R/matched_summary.md`. Passthrough is 66,594 B (720p) and 163,478 B (1080p).
- MJPEG columns: quality is relative to the decoded camera JPEG, so ratios to passthrough are **not at equal fidelity to the scene** (§2.3).
- The YUY2 and MJPEG columns are different captures (`R/NOTES.md` §2). Do not compare bytes across them.
- nvJPEG rows: exact-RGB input (sweep). For the swscale feed see §2.4 and §3.3.

| path | yuy2_1080p | yuy2_720p | mjpeg_720p | mjpeg_1080p |
|---|---|---|---|---|
| jpeg_turbo_422 | 297,359 (1.00) | 163,913 (1.00) | 60,318 (1.00; 0.91) | 145,774 (1.00; 0.89) |
| jpeg_turbo_420 | 265,001 (0.89) | 147,259 (0.90) | 55,459 (0.92; 0.83) | 130,185 (0.89; 0.80) |
| ff_mjpeg_422 | 258,748 (0.87) | 131,824 (0.80) | 58,143 (0.96; 0.87) | 146,720 (1.01; 0.90) |
| ff_mjpeg_420 | 221,837 (0.75) | 114,849 (0.70) | 54,073 (0.90; 0.81) | 133,872 (0.92; 0.82) |
| mjpeg_qsv_422 | 331,349 (1.11) | 170,009 (1.04) | 59,802 (0.99; 0.90) | 145,128 (1.00; 0.89) |
| mjpeg_qsv_420 | 296,502 (1.00) | 152,596 (0.93) | 54,796 (0.91; 0.82) | 129,364 (0.89; 0.79) |
| nvjpeg_422 (exact RGB) | 248,629 (0.84) | 133,459 (0.81) | 65,280 (1.08; 0.98) | 175,469 (1.20; 1.07) |
| nvjpeg_420 (exact RGB) | 221,461 (0.74) | 119,385 (0.73) | 60,527 (1.00; 0.91) | 161,033 (1.10; 0.99) |
| h264_nvenc_420 | 157,840 (0.53) | 83,913 (0.51) | 46,217 (0.77; 0.69) | 123,426 (0.85; 0.76) |
| h264_qsv_420 | 175,094 (0.59) | 92,438 (0.56) | 55,667 (0.92; 0.84) | 148,327 (1.02; 0.91) |
| hevc_nvenc_420 | 129,131 (0.43) | 66,037 (0.40) | 53,975 (0.89; 0.81) | 141,655 (0.97; 0.87) |
| hevc_qsv_420 | 116,646 (0.39) | 59,282 (0.36) | 42,502 (0.70; 0.64) | 110,835 (0.76; 0.68) |
| hevc_qsv_422 (Rext) | 155,171 (0.52) | 77,251 (0.47) | 47,993 (0.80; 0.72) | 136,529 (0.94; 0.84) |
| libx264_veryfast_420 | 164,862 (0.55) | 87,991 (0.54) | 55,236 (0.92; 0.83) | 149,851 (1.03; 0.92) |
| libx264_ultrafast_420 | 244,910 (0.82) | 133,065 (0.81) | 94,459 (1.57; 1.42) | 249,785 (1.71; 1.53) |
| libx265_ultrafast_420 | 146,521 (0.49) | 79,734 (0.49) | 67,662 (1.12; 1.02) | 161,155 (1.11; 0.99) |

### 3.2 Target B (PSNR-Y 45 dB): bytes/frame at target (interpolated), (× jt422; × passthrough)

measured, `R/matched_summary.md`. The same notes as §3.1 apply. The draft omitted three rows (ff_mjpeg_422, nvjpeg_422, libx264_ultrafast); they are added here.

| path | yuy2_1080p | yuy2_720p | mjpeg_720p | mjpeg_1080p |
|---|---|---|---|---|
| jpeg_turbo_422 | 77,458 (1.00) | 47,077 (1.00) | 32,096 (1.00; 0.48) | 69,748 (1.00; 0.43) |
| jpeg_turbo_420 | 68,773 (0.89) | 42,593 (0.90) | 28,228 (0.88; 0.42) | 61,406 (0.88; 0.38) |
| ff_mjpeg_422 | 76,857 (0.99) | 43,978 (0.93) | 30,737 (0.96; 0.46) | 69,552 (1.00; 0.43) |
| ff_mjpeg_420 | 66,622 (0.86) | 39,007 (0.83) | 26,631 (0.83; 0.40) | 59,270 (0.85; 0.36) |
| mjpeg_qsv_422 | 76,949 (0.99) | 46,804 (0.99) | 32,015 (1.00; 0.48) | 69,004 (0.99; 0.42) |
| mjpeg_qsv_420 | 68,415 (0.88) | 42,349 (0.90) | 28,133 (0.88; 0.42) | 61,085 (0.88; 0.37) |
| nvjpeg_422 (exact RGB) | 80,220 (1.04) | 49,810 (1.06) | 36,447 (1.14; 0.55) | 77,255 (1.11; 0.47) |
| nvjpeg_420 (exact RGB) | 71,551 (0.92) | 45,104 (0.96) | 32,263 (1.01; 0.48) | 68,468 (0.98; 0.42) |
| h264_nvenc_420 | 22,392 (0.29) | 16,047 (0.34) | 8,611 (0.27; 0.13) | 18,026 (0.26; 0.11) |
| h264_qsv_420 | 27,378 (0.35) | 18,593 (0.39) | 10,722 (0.33; 0.16) | 22,639 (0.32; 0.14) |
| hevc_nvenc_420 | 14,290 (0.18) | 10,960 (0.23) | 6,417 (0.20; 0.10) | 12,428 (0.18; 0.08) |
| hevc_qsv_420 | 14,236 (0.18) | 10,431 (0.22) | 5,959 (0.19; 0.09) | 11,965 (0.17; 0.07) |
| hevc_qsv_422 (Rext) | 17,337 (0.22) | 12,530 (0.27) | 6,916 (0.22; 0.10) | 15,444 (0.22; 0.09) |
| libx264_veryfast_420 | 27,722 (0.36) | 19,231 (0.41) | 11,217 (0.35; 0.17) | 23,474 (0.34; 0.14) |
| libx264_ultrafast_420 | 55,449 (0.72) | 38,125 (0.81) | 19,391 (0.60; 0.29) | 47,793 (0.69; 0.29) |
| libx265_ultrafast_420 | 19,518 (0.25) | 16,196 (0.34) | 9,805 (0.31; 0.15) | 15,985 (0.23; 0.10) |

### 3.3 Single stream at target A, 1080p: fps median (min–max) / CPU ms per frame

measured, S-A1080. Bytes and the ratio are at the chosen setting from NV12 (or native YUY2 for 4:2:2 paths); the ratio is against the bench's YUY2 jt422 row.
- CPU mask (§5 flag 1): the NV12 cells of the 4:2:0 rows ran on CPUs 0–15. **Every other cell ran with the mask widened to 0–27**: the "from YUY2", "after MJPEG CPU decode" and "after mjpeg_qsv decode" columns, the native-YUY2 4:2:2 rows (marked †) and the exact-RGB row (†). libx265 widened the mask itself.

| path | from NV12 (4:2:2 paths: native YUY2) | from YUY2 (swscale for 4:2:0), 0–27 mask | after MJPEG CPU decode, 0–27 mask | after mjpeg_qsv decode, 0–27 mask | bytes (× jt422) |
|---|---|---|---|---|---|
| jpeg_turbo_422 † | 225 (225–226) / 4.38 | – | 152 / 6.43 | – | 286,974 (1.00) |
| jpeg_turbo_420 | 360 (358–360) / 2.77 | 231 / 8.30 | 156 / 8.96 | 291 / 7.02 | 255,423 (0.89) |
| ff_mjpeg_420 | 415 (410–418) / 11.08 | 480 / 11.70 | 209 / 14.44 | 591 / 10.46 | 227,158 (0.79) |
| mjpeg_qsv_422 † | 481 (481–482) / 1.58 | – | 206 / 7.06 | – | 308,099 (1.07) |
| mjpeg_qsv_420 | 602 (601–606) / 1.81 | 553 / 7.56 | 206 / 9.23 | 609 (432–611) / 1.17 | 276,187 (0.96) |
| nvjpeg_420 (swscale RGB) | 323 (283–341) / 7.57 | 361 / 7.74 | 145 / 8.94 **QC miss** | 446 / 8.72 | 225,514 (0.79) |
| nvjpeg_420 (exact RGB, encode only) † | 1,126 (1,117–1,132) / 0.87 | – | – | – | 226,566 (0.79) |
| h264_nvenc_420 | 540 (540–540) / 1.40 | 544 / 6.67 | 228 / 9.84 | 594 / 7.62 | 157,924 (0.55) |
| hevc_nvenc_420 | 390 (389–390) / 1.47 | 390 / 6.38 | 230 / 8.84 | 380 / 6.84 | 135,292 (0.47) |
| h264_qsv_420 | 585 (585–585) / 2.04 | 580 / 8.44 | 236 / 10.26 | 554 (361–554) / 8.44 | 170,101 (0.59) |
| hevc_qsv_420 | 65 (65–66) / 2.81 | 66 / 10.10 | 68 / 9.22 | 66 / 15.88 | 117,180 (0.41) |
| hevc_qsv_422 † | 64 (64–64) / 3.18 | – | 66 / 8.75 (just under A) | – | 155,864 (0.54) |
| libx264_ultrafast_420 | 372 (371–375) / 14.70 | 434 / 15.32 | 198 / 17.81 | 505 / 15.08 | 250,639 (0.87) |
| libx264_veryfast_420 | 229 (229–232) / 31.05 | 256 / 28.50 | 156 / 31.95 | 286 / 31.34 | 163,303 (0.57) |
| libx265_ultrafast_420 (26–27 cores, widened mask) | 106 (105–107) / 252.95 | 107 / 250.73 | 108 / 250.73 | 108 / 248.34 | 147,170 (0.51) |

### 3.4 Single stream at 720p A and at 1080p B, from NV12: fps / CPU ms per frame / bytes

measured, S-A720 and S-B1080. Every row except libx265 ran before the first libx265 cell, so on CPUs 0–15 (run order in `runs[]`).

| path | 720p, target A | 1080p, target B |
|---|---|---|
| jpeg_turbo_420 | 744 / 1.34 / 150,618 | 507 / 1.96 / 69,092 |
| mjpeg_qsv_420 | 1,155 / 0.75 / 163,558 | 618 / 1.76 / 68,768 |
| nvjpeg_420 (swscale RGB) | 617 / 4.59 / 117,252 | 330 / 8.05 / 71,782 |
| h264_nvenc_420 | 1,115 / 0.56 / 83,596 | 635 / 1.39 / 21,825 (QC 44.61 dB, step-short) |
| hevc_nvenc_420 | 842 / 0.60 / 64,007 | 425 / 1.43 / 14,506 |
| h264_qsv_420 | 1,151 / 0.97 / 89,279 | 691 / 1.93 / 27,081 (QC 44.74 dB, step-short) |
| hevc_qsv_420 | 128 / 1.57 / 61,274 | 87 / 2.81 / 14,449 |
| libx264_veryfast_420 | 433 / 14.14 / 86,591 | 310 / 17.98 / 28,041 |
| libx265_ultrafast_420 (widened mask) | 232 / 113.82 / 80,414 (26.3 cores) | 152 / 177.78 / 19,925 (27.0 cores) |

### 3.5 Scaling at target A: largest N that keeps up at 30 fps (paced), CPU there, and unpaced aggregate at the largest N

measured; files as listed. All on CPUs 0–15 (8 P-cores) of an i7-14700K. CPU for process workers is a lower bound (§5). Rows "· NV12" are the best case for 4:2:0 hardware paths (§2.5).

| path · source | 1080p: max N keeping up | CPU cores at that N, median (min–max) | unpaced aggregate fps at N=16 (12 for NVENC) | 720p: max N |
|---|---|---|---|---|
| h264_nvenc · NV12 | 12 (session limit) | 0.61 (0.60–0.64) | 542 (537–542) | 12 (limit) |
| hevc_nvenc · NV12 | 12 (session limit) | 0.65 (0.59–0.66) | 390 (390–392) | 12 (limit) |
| h264_qsv · NV12 | 16 | 1.25 (1.23–1.28) | 679 (678–682) | 16 |
| hevc_qsv · NV12 | 1 (0/4 at N=4) | 0.15 (0.15–0.18) at N=1 | 67 (67–67) | 4 (0/8 at N=8) |
| mjpeg_qsv_420 · NV12 | 16 | 1.05 (1.03–1.05) | 700 (695–705) | 16 |
| nvjpeg_420 · NV12 | 8 (at N=16: 98.2% of needed rate, 1–3 of 16 keep up) | 2.56 (2.47–2.57) | 475 (472–477) | 16 |
| jpeg_turbo_420 · NV12 · process | 16 | ≥1.69 (1.59–1.78) | 3,572 (3,512–3,579); threads 3,511 (1 rep); 16-CPU ceiling | 16 |
| jpeg_turbo_422 · YUY2 · process | 16 | ≥2.81 (2.48–3.14) | 1,742 (1,719–1,766) | – |
| nvjpeg_422 · YUY2 | 16 (5.3 / 13.3% late) | 4.68 (4.63–4.74) | 567 (567–568) | – |
| mjpeg_qsv_422 · YUY2 | 16 | 0.92 (0.86–0.97) | 934 (932–936) | – |
| hevc_qsv_422 · YUY2 | 1 | 0.15 (0.15–0.16) at N=1 | 65 (65–65) | – |
| MJPEG CPU decode → h264_nvenc | 12 (limit) | 4.06 (4.01–4.10) | 596 (595–597) | – |
| MJPEG CPU decode → hevc_nvenc | 12 (limit) | 3.90 (3.77–4.03) | 378 (376–379) | – |
| mjpeg_qsv decode → h264_qsv | 16 | 4.33 (4.30–4.35) | 486 (476–495) | – |
| mjpeg_qsv decode → hevc_qsv | 1 | 0.43 (0.41–0.46) at N=1 | 66 (66–67) | – |
| YUY2 → swscale → h264_nvenc | 12 (limit) | 2.53 (2.41–2.64) | 540 (540–541) | – |

## 4. Implications for the plan

All throughput and CPU numbers here are **encode only** (packets discarded) on this machine. The recording cost also depends on the writer: per `results/write_throughput/BENCH.md` and `results/BENCH_RUN_2300_SUMMARY.md` §2, folder-of-files writing triggers large Defender real-time scanning cost (Defender ON, part of the real cost).

- **G7 cost at target A, for cameras that deliver YUY2/raw frames** (inferred: byte ratios from §3.1, yuy2_1080p):
  - Against jt422 (keeps the cameras' 4:2:2 chroma): JPEG needs about 1.7–1.9x the bytes of hardware H.264 intra and about 2.3–2.5x those of hardware HEVC intra.
  - Against jt420 (same 4:2:0 subsampling): about 1.5–1.7x and 2.1–2.3x.
  - Matching is on luma (SSIM-Y). The hardware 4:2:0 codecs also score higher `psnr_yuv_422` than jt422 at A (§2.3), so the jt422 comparison is not unfair to JPEG on chroma.
  - At target B: about 2.8–3.5x for H.264 and 5.4x for HEVC against jt422; 2.5–3.1x and 4.8x against jt420 (inferred: from §3.2 bytes). The draft's 5.6x came from the rounded 0.18 ratio.
  - That is the price of the royalty-free choice (§2.3).
- **For MJPEG cameras, passthrough (G1) stays the baseline at target A.**
  - The best re-encode that also scales (h264_nvenc) is 0.69–0.76x passthrough at A, a 24–31% byte saving **at lower fidelity than passthrough** (generation loss on top of the camera's JPEG; §2.3, §3.1). hevc_qsv is smaller (0.64–0.68x) but sustains only 1 stream (§2.5).
  - It costs 4.06 cores for 12 × 1080p30 (MJPEG CPU decode + h264_nvenc, on 16 CPUs; §2.5), and it hits the 12-session NVENC limit (§2.6).
  - inferred: passthrough is cheaper and more faithful.
- **Storage at A, 1080p30 per camera** (inferred: bytes/frame from §3.1 × 30 fps; decimal MB). Input classes are kept apart because they are different captures:

  | camera type | format | MB/s | GB/h | 16 cameras, MB/s |
  |---|---|---|---|---|
  | YUY2 camera (yuy2_1080p) | jt422 | 8.9 | 32 | 143 |
  | YUY2 camera | mjpeg_qsv_422 | 9.9 | 36 | 159 |
  | YUY2 camera | h264_nvenc | 4.7 | 17.0 | 76 |
  | YUY2 camera | hevc_qsv | 3.5 | 12.6 | 56 |
  | MJPEG camera (mjpeg_1080p) | passthrough | 4.9 | 17.7 | 78 |
  | MJPEG camera | jt422 re-encode | 4.4 | 15.7 | 70 |
  | MJPEG camera | h264_nvenc re-encode | 3.7 | 13.3 | 59 |

- **Hardware JPEG on this machine** (G6 and hardware target for the recording format):
  - mjpeg_qsv sustains 16 × 1080p30 from NV12 (best case; these cameras do not deliver NV12) at 1.05 cores, and from native YUY2 at 4:2:2 at 0.92 cores (§2.5). The native-YUY2 4:2:2 result is the one that matches the cameras.
  - nvJPEG is at its limit near 16 × 1080p30 from either feed: from NV12 it reaches 98.2% of the needed rate (1–3 of 16 streams keep up); from YUY2 all 16 keep up with 5–13% late frames (§2.5).
  - nvJPEG's CPU cost is dominated by the swscale RGB step: 7.57 ms vs 0.87 ms per frame for the encode alone (§2.4).
  - inferred: nvJPEG needs a cheaper YUV→RGB step (exact RGB or a GPU kernel, untested) before it is a reliable 16-camera path.
  - Platform coverage beyond Gerald (AMD has no JPEG encode, and so on) is in `results/hw_accel_target/FINDINGS.md`, not re-checked here.
- **Hardware H.264/HEVC intra on this machine:**
  - One GeForce gives at most 12 NVENC streams (§2.6), so 16 cameras need a second encoder.
  - h264_qsv sustains 16 × 1080p30 from NV12 (best case) and after mjpeg_qsv decode (§2.5). 16 streams from YUY2 through swscale were not tested; one stream costs 8.44 ms CPU/frame for that step (§2.4).
  - hevc_qsv at default settings sustains only 1 × 1080p30 (4 × 720p30), so it is not a multi-camera path as configured (§2.5).
  - NVENC + QSV split across cameras was not tested (§6).
  - inferred: NVENC/QSV hold 2–4 frames inside the encoder (F2, §2.5). A crash loses those frames; JPEG paths hold none (G2).
- **CPU fallback (no iGPU, no NVIDIA), measured on 16 logical CPUs (8 P-cores) of an i7-14700K only:**
  - libjpeg-turbo 4:2:0 runs 16 × 1080p30 paced at ≥1.69 cores (measured, process lower bound, C-jt-proc). An unpaced-saturation estimate gives about 2 cores (inferred: 4.14 ms/frame at N=16 threads × 480 fps).
  - Unpaced per-frame CPU is lower than paced: paced N=1 costs 7.05 ms vs 2.81 ms unpaced for libjpeg-turbo (C-jt-proc), and 3.82 vs 1.46 ms for h264_nvenc (C-h264nv).
  - libx264 veryfast needs about 0.93 cores per 1080p30 stream (inferred: 31.05 ms × 30, unpaced, at 7.1 cores threaded in one stream). libx265 ultrafast needs about 7.6 (inferred: 252.95 ms × 30), read on the widened 0–27 mask with x265's thread pool; it is not a P-core figure.
  - inferred: JPEG is the only practical CPU fallback for many cameras on this CPU. Capacity on lower-end or no-iGPU CPUs is not tested (§6).
  - The wheel bundles libx264/libx265, which are GPL-licensed upstream, and their DLLs cannot be removed, while the FFmpeg build reports "LGPL version 3 or later" (`results/licensing/FINDINGS.md` §2.5).
- **Settings to carry into the implementation:**
  - Use `R/matched_settings.json` (target A top level, B under `psnr45`).
  - Always set `i_qfactor=1, i_qoffset=0` for NVENC/QSV CQP.
  - Use `qmin=qmax` for FFmpeg `mjpeg`.
  - Pass the colour range explicitly (§2.8).
  - Do not open libx265 in the capture process if threads are pinned: it widens the process affinity permanently (F1).
- **4:2:2:** keeping the cameras' 4:2:2 chroma costs 7–17% more bytes for JPEG and 13–33% for HEVC Rext at target A (§2.3).
  - Luma is unchanged in the sweep and from YUY2. From decoded MJPEG, hevc_qsv_422 came out 2.5 dB lower than hevc_qsv_420 in the bench (§2.7).
  - Playback limits from another topic: HEVC Rext 4:2:2 fails to decode in E45 and E35 rejects it (`results/chromium_codecs/FINDINGS.md` C17, C17a).
  - inferred: HEVC 4:2:2 is not a safe recording format for the Electron UI.
- **Avoid libx265 output for the UI.** It is Rext even at 4:2:0 (§2.1), and its Electron playback is NOT VERIFIED.
- **Feed nvJPEG correctly.** Do not feed it RGB converted by swscale from decoded `yuvj422p`: that feed misses targets A and B (§2.7).

## 5. Run flags and caveats that apply to this topic

1. **libx265 widened the process affinity in items 1–3, and the wider mask stayed.**
   - measured: `system_before.process_cpu_affinity` is 0–15 and `system_after` is 0–27 in all three `matched_stream_*` files.
   - measured: every libx265 run used 23.25–27.31 cores (26.0–27.3 at A 1080p), which is impossible on 16 CPUs.
   - measured (F1, functional, PyAV 19.0.2, no timing): after pinning to CPUs 0–15, opening libx264 leaves 16 CPUs; opening libx265 widens the mask to 28 CPUs, and it stays at 28 after the encoder is deleted (`R/VERIFY_method.md` §1.1).
   - measured: the libx265 NV12 cell is the 11th cell in items 1–3 (`runs[]` order), followed by 45, 32 and 16 cells.
   - inferred (F1 + `system_after`): every cell after it ran with the 0–27 mask. Only the first 10 NV12 cells of each item are P-core-only (§3.3, §3.4).
   - measured: non-x265 cells after the first libx265 cell used at most 9.97 (S-A1080), 6.61 (S-A720) and 3.90 (S-B1080) cores.
   - NOT VERIFIED: whether the scheduler still kept those single-threaded cells on P-cores.
   - measured: the 24 scaling files keep 0–15 before and after.
2. **NVENC N=16 rows are 12-stream rows** (§2.6).
3. **nvJPEG fed decoded camera MJPEG misses target A and target B** (§2.7). Its MJPEG-source fps/CPU rows are not at matched quality.
4. **hevc_qsv_422 rows are slightly under A**, by a knob step present in the sweep, with 2.1–2.7 dB lower PSNR-Y from decoded MJPEG (§2.7).
5. **The QC covers the first 4 frames, all C930e, from a separate untimed encoder.** It reads 0.6–0.9 dB above the two-camera sweep at A. The scaling items have no QC (code: `S/bench_matched_stream.py:87`; `S/benchpaths.py:266-288`; `S/iclib.py:44-47`; BENCH.md caveat 5).
6. **Process-worker CPU is a lower bound.**
   - code: a child that exits before the second read is lost (`S/bench_matched_concurrent.py:210`).
   - measured: three unpaced N=8 process runs recorded negative CPU: item 10 (−2.22, −2.44 cores) and item 55 (−1.15) (C-jt-proc, C720-jt).
7. **The input work is inside the timed loop for the MJPEG and swscale sources.** The NV12/YUY2 range mapping is done untimed (`S/benchpaths.py` docstring, lines 7-19).
8. **GPU utilisation in unpaced N=1 scaling runs is unreliable.** Those runs last 0.29–1.6 s (hevc_qsv 2.4–4.7 s), at or under the 1 s counter period (BENCH.md caveat 8). Use items 1–3 for single-stream GPU load.
9. **Reps.**
   - Scaling: 3 reps (items 4–10), 1 (item 11) or 2 (items 31–55). Min–max over 2 reps is just the two values.
   - Single stream: 5 / 4 / 3 timed reps.
   - All are repeats within one run, not across runs (summary flag 12).
10. **Short source sets, cycled.** YUY2 16 frames (8 per camera), MJPEG 1080p 38 JPEGs (19 per camera), MJPEG 720p 240 (120 per camera) (code: set sizes `S/iclib.py:44-48` `INPUTS`; cycling `S/benchpaths.py:190, 206, 218`). The 720p YUY2 frames are swscale-derived.
11. **Load record** (`results/BENCH_RUN_2300_LOG.jsonl` via BENCH.md §1):
    - no intra_compare item was flagged `load_over_15pct`; the highest pre-item max was 14.7% (item 32);
    - no Defender scan events during any intra_compare item;
    - MsMpEng used 1.55–50.89 CPU-s per item.
    - code: these items wrote no media files (`S/bench_matched_stream.py:12`; `S/bench_matched_concurrent.py:60-62, 73-75`). So the MsMpEng CPU here is not a write cost; its cause is NOT VERIFIED.
12. **CPU timer granularity.**
    - measured: Windows process CPU readings in these files are whole multiples of 15.625 ms (for example single-stream hevc_qsv_420·nv12 reps read 0.7656, 0.7344, 0.8438, 1.5312 and 1.1719 CPU-s = 49, 47, 54, 98 and 75 quanta; S-A1080 `runs[]`). The same granularity is summary flag 11 for the mux/fragment benches.
    - inferred: one quantum is 15.625 ms ÷ the run's CPU-seconds. That is under 0.5% for CPU-bound reps of 3 CPU-s or more, about 2% for single-stream hevc_qsv (about 0.8 CPU-s), and 8–10% for the unpaced N=1 NVENC 720p runs (0.156–0.203 CPU-s over 0.29–0.30 s, C720-h264_nvenc).
13. **Drivers are not recorded in the JSONs.** NVIDIA 610.88 and Intel 32.0.101.7088 were read after the run (`results/BENCH_RUN_2300_SUMMARY.md` §2).
14. **Run flags that do not apply here:** the WebCodecs errors, `<video>` stalls, write-latency comparison and uncompressed_intra lossless gap are other topics.

## 6. Not tested, limits, NOT VERIFIED

- **NOT VERIFIED: why the cameras' 1080p JPEGs are much smaller than libjpeg-turbo q94 on the same models' YUY2 frames.**
  - measured: camera JPEGs average 134,574 B (C930e) and 192,382 B (C922), against 260,827 and 312,812 B for libjpeg-turbo q94 on the YUY2 frames (`R/camera_jpeg_quality.md`).
  - measured: at equal SSIM-Y the decoded camera frames need about half the bytes (§2.3).
  - inferred hypotheses:
    - the YUY2 and MJPEG sets are different captures (`R/NOTES.md` §2);
    - or the cameras denoise or process MJPEG differently.
  - Settling it needs back-to-back YUY2 and MJPEG captures of one static scene, which needs Dom (no camera access, requirement 11).
- NOT VERIFIED: whether "no loss at A" holds for pose keypoints. Dom decided not to run that test (HANDOFF.md §1.1).
- NOT VERIFIED: Electron/Chromium playback of libx265's Rext all-intra 4:2:0 (chromium_codecs tested only HEVC Rext 4:2:2).
- NOT VERIFIED: the causes behind several measured differences:
  - nvJPEG's QC spread across feeds, and its conflict with `R/nvjpeg_rgb_diag.json` (§2.7, §2.8);
  - FFmpeg `mjpeg`'s smaller files on YUY2 (§2.3);
  - the PSNR-Y drop of hevc_qsv_422 fed decoded MJPEG (§2.7);
  - the bench-vs-sweep byte differences for swscale/decoder feeds (§2.4).
- NOT VERIFIED: whether the post-libx265 single-stream cells in items 1–3 ran on P-cores (§5 flag 1).
- Not tested:
  - scaling at target B (all scaling items ran at A);
  - h264_qsv and mjpeg_qsv 4:2:0 × 16 from YUY2 (the tested YUY2 pipelines are YUY2 → h264_nvenc and native mjpeg_qsv 4:2:2);
  - NVENC and QSV running together on one machine;
  - one encoder session shared by several cameras;
  - hevc_qsv `low_power`/VDEnc or other QSV presets;
  - NVENC presets other than p4/ll;
  - `*_mf` and `*_d3d12va` encoders;
  - libx264/libx265 4:2:2;
  - a GPU-resident nvJPEG path or a CUDA YUV→RGB kernel;
  - perceptual metrics (VMAF);
  - file writing (packets were discarded), and so the Defender cost of each format's writer.
- Not tested on other hardware: AMD, Apple, other NVIDIA or Intel generations, lower-end CPUs, or CPUs with no iGPU. Bytes per QP and speeds are for the RTX 3070, UHD 770 and 16 logical CPUs of the i7-14700K only. The hardware target covers "most CPUs from 2020 on" (HANDOFF §1, requirement 3), so the CPU-fallback capacity is a high-end data point.
- Content limits: two camera models in one room; 16 YUY2 frames (noisy); the matched settings are integer knob steps (remaining single-step gaps in `R/refine_plan.json`); SSIM on Y only; the bench QC covers C930e frames only.
- The intra_playback clips are at 54.5–55.0 dB Y-PSNR, which is neither target A nor target B. Do not mix their sizes with these (`results/BENCH_RUN_2300_SUMMARY.md` §4).

## 7. How to reproduce (from the repo root; PyAV 19.0.2 via PEP 723 pins)

Functional sweep (no timing):
```
uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_compare/camera_jpeg_quality.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_compare/sweep.py --paths <ids> --keep-media
uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_compare/analyze.py
python research/skellycam_recording/recording_upgrade/scripts/intra_compare/run_refine.py --per-path
uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_compare/analyze.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_compare/knob_check.py
```

Timed items. Run them on a quiet machine, one item at a time, through the runner: `scripts/bench_runner/run_queue.py --only <ids>`. Exact commands are in `results/BENCH_QUEUE_2300.md`, items 1–11, 31–34, 41–45 and 49–55. For example:
```
uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_compare/bench_matched_stream.py --paths all --sizes 1080p --sources nv12,yuy2,mjpeg_cpu,mjpeg_qsv,rgb --target A --frames 300 --min-seconds 3 --reps 5 --label A_1080p
uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_compare/bench_matched_concurrent.py --path h264_nvenc_420 --size 1080p --source nv12 --workers thread --modes paced,unpaced --streams 1,4,8,16 --reps 3 --limit-probe 32
```
- inferred: to keep single-stream results P-core-only, run libx265 cells in their own process, or last (§5 flag 1).

Numbers in this file were read from the JSON fields `summary[]` (single stream) and `runs[]` / `limit_probe` (scaling), with medians and min–max computed over reps. `R/BENCH.md` holds the full per-cell tables built from the same files.

## 8. Verification (2026-11-10)

**What the verifiers checked**
- Provenance (`R/VERIFY_provenance.md`):
  - every single-stream and scaling number against the 27 bench JSONs;
  - the sweep tables against `R/matched_summary.md`, `R/raw/`, `R/verification.md`, `R/knob_check.json`, `R/dht_check.json` and `R/nvjpeg_rgb_diag.json`;
  - the run log and summary, and the cited code lines;
  - re-fetched the FFmpeg n9.0.2 sources and the NVIDIA support matrix.
  - Verdict: mostly sound, 4 refuted side claims, 13 weak.
- Method (`R/VERIFY_method.md`):
  - recomputed every timed number;
  - read the source preparation, QC and paced loop;
  - ran two functional checks (F1 libx265 affinity, F2 encoder output delay; PyAV 19.0.2, no timing).
  - Verdict: revise, 3 refuted, 15 weak; main conclusions unchanged.
- The reviser re-checked each refutation against the JSON and summary files before applying it. Checked: bench/sweep byte ratios, target B PSNR-Y pairs, `system_before` versions, the 53.36 dB point, run order, QC bias, nvJPEG late/drop counts, `cpu_s` quantisation, paced vs unpaced CPU, `psnr_yuv_422`, DHT sample count and NOTES stale lines. All were confirmed.

**What was changed**
- Refuted claims corrected:
  - §2.4 bytes vs sweep: replaced "within 0.1% for JPEG" with a per-feed table;
  - §2.3 "PSNR-Y identical in every pair": now at target A only; B differs by 0.01–0.02 dB for hevc_qsv;
  - §2.1 versions: only what the bench JSONs record; the full versions come from `R/raw`;
  - §2.2 H.264/HEVC PSNR-Y range: now 53.12–53.36 dB;
  - §5 flag 1: now gives the F1 result; post-x265 cells are marked as on the 0–27 mask in §2.4, §3.3 and §3.4;
  - §5 flag 12: the timer bound is now against CPU-seconds (about 2% for hevc_qsv, 8–10% for N=1 NVENC 720p) and is measured from these files.
- Weak claims relabelled or qualified:
  - NVIDIA source: now has URL, quote and access date;
  - GPL wording;
  - storage table split by input class;
  - nvJPEG late counts, and "at its limit near 16" instead of a firm 8;
  - "medians per N" on the unpaced ranges;
  - set-size code lines; hevc_qsv/simplejpeg/nvJPEG "not probed";
  - all mjpeg_cpu fps exceptions named; libx265 26–27 cores in §3.3;
  - nvjpeg_420 1080p 0.99x added to the passthrough list;
  - G7 factors from bytes (H.264 2.8–3.5x and HEVC 5.4x at B; HEVC 2.3–2.5x at A), plus the jt420 basis and `psnr_yuv_422`;
  - DHT "every sampled file"; NOTES stale lines cited (line 179 added by the reviser);
  - QC is C930e-only with an upward bias at A;
  - encode-call p99 is not latency (F2 delays added);
  - "at lower fidelity than passthrough" on the MJPEG ratios and the 24–31% saving;
  - NV12 is the best case; 16-CPU pin stated on every CPU-fallback number;
  - paced vs unpaced CPU kept apart;
  - hevc_qsv_422 luma drop from MJPEG in the bench;
  - RTX 3070/p4/ll scope on the 13-stream inference; "1 thread rep" on the GIL inference;
  - nvJPEG sweep rows marked "exact RGB";
  - encode-only/Defender note in §4, and MsMpEng CPU not called a write cost.
- Also: added the three target-B rows the draft omitted (§3.2); corrected nvJPEG's "smaller on YUY2" to A only (§2.3).

**What remains NOT VERIFIED**
- Causes of the bench-vs-sweep byte gaps, nvJPEG's feed-dependent quality, FFmpeg mjpeg's small YUY2 files and the hevc_qsv_422 drop from MJPEG.
- Whether the post-libx265 cells in items 1–3 stayed on P-cores.
- Why the camera JPEGs are about half the bytes of YUY2 at A (needs captures by Dom).
- Pose-keypoint loss at A (not to be tested).
- Electron playback of libx265 Rext 4:2:0.
- MsMpEng CPU cause during no-write items.
- Every hardware other than the RTX 3070, UHD 770 and 16 CPUs of the i7-14700K.
