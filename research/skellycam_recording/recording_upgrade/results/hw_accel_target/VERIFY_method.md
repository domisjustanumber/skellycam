# hw_accel_target: VERIFY_method (methodology lens) of the draft FINDINGS

Verifier: adversarial, methodology lens (confounders, wrong conclusions). Date 2026-11-09, machine Gerald. No timing numbers were taken.
There was no earlier VERIFY_method.md in this folder, so nothing was renamed.

Paths: `R` = `research/skellycam_recording/recording_upgrade/results/`, `S` = `research/skellycam_recording/recording_upgrade/scripts/`.

## 0. New evidence produced by this verification

| file | what |
|---|---|
| `S/hw_accel_target/verify_range_check.py` | functional re-check, PyAV 19.0.2 (`av==19.0.2`, `numpy==2.2.6`), Intel QSV only, < 1 min, no timing |
| `R/hw_accel_target/verify_method_range_check.json` | its output. nvidia-smi `encoder.stats.sessionCount` was 0 before and 0 after |

- measured: a full-range Y ramp (0..255) reformatted the way the bench does it for MJPEG sources (`reformat(format='nv12', dst_color_range=1)`) is fed to `mjpeg_qsv` as Y 16..235. The resulting JPEG decodes as `yuvj420p` with Y 16..235. So the JPEG holds limited-range samples under a full-range (JFIF) interpretation, which compresses the contrast (`verify_method_range_check.json`).
- source: FFmpeg n9.0.2 `libavcodec/qsv_internal.h` lines 26-28, https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/libavcodec/qsv_internal.h, accessed 2026-11-09:
  - "#if CONFIG_VAAPI && !defined(_WIN32) // Do not enable for libva-win32 on Windows"
  - "#define AVCODEC_QSV_LINUX_SESSION_HANDLE"
- source: FFmpeg n8.0 `libavcodec/qsv.c`, accessed 2026-11-09. Only under `#ifdef AVCODEC_QSV_LINUX_SESSION_HANDLE` does `ff_qsv_init_internal_session` call `ff_qsv_set_display_handle`, which runs `av_hwdevice_ctx_create(..., AV_HWDEVICE_TYPE_VAAPI, ...)` and then `MFXVideoCORE_SetHandle`. The n9.0.2 `qsv.c` itself was not checked.
- source: FFmpeg n8.0 `libavutil/hwcontext_qsv.c`, accessed 2026-11-09. The Linux child device is chosen by `} else if (CONFIG_VAAPI) {`. Otherwise it reports "No supported child device type is enabled" and returns `AVERROR(ENOSYS)`.
- source: nvJPEG 13.5 copy (scratchpad `hw_accel_target/findings_src/nvjpeg_index.html`; I re-hashed it as sha256 `5d2f3d74…db5ef`, matching the draft):
  - "NVJPEG_BACKEND_HARDWARE Uses Hardware Acceleration for decode. Supports baseline JPEG images with single scan with 1 or 3 channels. 410 and 411 chroma subsamplings are not supported."

## 1. Refuted

| # | draft claim | why it is wrong | correction |
|---|---|---|---|
| X1 | §3.4: hevc_nvenc at target A is 55,112 (mjpeg_720p) and 144,376 (mjpeg_1080p), "from `matched_summary.md`" | `R/intra_compare/matched_summary.md` gives `bytes@target` 53,975 (mjpeg_720p) and 141,655 (mjpeg_1080p). The draft's values come from `R/intra_compare/NOTES.md` §6, which disagrees with the generated summary. It also differs on h264_nvenc yuy2_720p (83,921 vs 83,913) and on libx264/libx265 ultrafast MJPEG cells | Use the generated file: 53,975 and 141,655. Flag the NOTES-vs-summary mismatch to the intra_compare owner. The Q4 range (0.70-1.02x) does not change |
| X2 | Q7: "At 45 dB it takes about 2.9-5.6x" | The draft inverted the rounded ratios (1/0.35, 1/0.18). The bytes in matched_summary.md give 77,458/27,378 = 2.83 and 77,458/14,236 = 5.44 | about 2.8-5.4x (libjpeg-turbo 4:2:2 against hardware H.264/HEVC 4:2:0) |
| X3 | §3.3, JPEG passthrough row: "(Q4: re-encodes at A are 0.64-1.02x)" of camera bytes | 1.02 is h264_qsv against libjpeg-turbo on mjpeg_1080p, not against passthrough. Against camera bytes the H.264/HEVC re-encodes are 0.64-0.91x (matched_summary.md, column "x passthrough") | "0.64-0.91x camera bytes (0.70-1.02x libjpeg-turbo 4:2:2)" |
| X4 | §2.11/§4.7, by omission: the range rule is "`dst_color_range=1` for H.264/HEVC from JPEG sources". §5 treats the existing bench as fine apart from rate control | `S/hw_accel_target/bench_encode_stream.py:120-124` also applies `dst_color_range=1` when the target is `mjpeg_qsv` (fmt `nv12`). At `:112` it feeds limited-range NV12 from YUY2 to `mjpeg_qsv` unchanged. measured: the JPEG then decodes with Y 16..235 (`verify_method_range_check.json`; also `NOTES_functional.md` §6.2, "`mjpeg_qsv` fed limited-range NV12 (from YUY2) writes JPEGs tagged `pc`") | The JPEG paths in that bench produce wrongly-ranged output, so their bytes/frame are not comparable. Run JPEG paths with `S/intra_compare/bench_matched_stream.py`, which feeds full range to JPEG paths (`benchpaths.py:16-18,195`), or fix `bench_encode_stream.py` |

## 2. Weak (needs relabelling, narrowing or a caveat)

### 2.1 Matched-quality confounders

| # | claim | why weak | fix |
|---|---|---|---|
| W1 | Q7 / §4.2: "JPEG costs 1.7-2.6x the bytes of hardware H.264/HEVC intra" | **Chroma mismatch.** The baseline is libjpeg-turbo **4:2:2**, but every H.264/HEVC row is **4:2:0**. Matching is on Y only (SSIM-Y), so the 4:2:2 JPEG pays for chroma that the 4:2:0 video drops. Recomputed from matched_summary.md yuy2_1080p, target A: <br>- libjpeg-turbo 4:2:0 vs H.264/HEVC 4:2:0 is 1.51-2.27x; <br>- mjpeg_qsv 4:2:0 is 1.69-2.54x; <br>- nvJPEG 4:2:0 is 1.26-1.90x; <br>- like for like at 4:2:2, libjpeg-turbo 4:2:2 vs hevc_qsv 4:2:2 is 1.92x | State the ratio at matched chroma (about 1.3-2.5x at 4:2:0 across the JPEG encoders, 1.9x at 4:2:2 against hevc_qsv Rext), and say that matching is on luma only |
| W2 | Q2 / §3.4 / §4.4: nvJPEG 4:2:0 at 0.74x (the smallest JPEG) | The advantage is specific to the metric. At target A, nvJPEG's PSNR-Y is 50.80 dB against libjpeg-turbo's 52.24 (matched_summary.md yuy2_1080p). At target B (PSNR-matched), nvjpeg_420 is 0.92x, larger than jpeg_turbo_420 (0.89x) and mjpeg_qsv_420 (0.88x) | Don't present nvJPEG as the smallest JPEG. Say that at matched PSNR it is no smaller than CPU or QSV JPEG |
| W3 | Q4 / §4.3: "re-encoding to H.264/HEVC saves only 0-36% at A" | It mixes two baselines (passthrough 0.64-0.91x; libjpeg-turbo 0.70-1.02x). Passthrough is also not at matched quality: it adds no loss, while every re-encode adds SSIM-Y 0.9961 of generation loss on top of the camera JPEG (IC §2: "generation loss on top of the camera's JPEG"). So 9-36% is a saving bought with extra loss, not a like-for-like saving | "9-36% smaller than the camera's own JPEG, at the cost of one more generation of loss". Keep the libjpeg-turbo comparison separate |
| W4 | Q2-Q7 ratios as general codec facts | They depend on presets and settings (NVENC p4/ll constqp, QSV default CQP, libjpeg-turbo non-fastdct; `R/intra_compare/matched_settings.json`) and on 16 YUY2 frames from one room. IC §12 says "Other generations can produce different bytes at the same QP" | Label them "Gerald, these presets, this content". Add preset dependence to §6 |

### 2.2 Functional pass taken as compatibility

| # | claim | why weak | fix |
|---|---|---|---|
| W5 | §3.2: Intel / Linux x86_64 "reachable: qsv" | The wheel contains `*_qsv` names but no VA-API (`R/gpu_encode/wheel_hw_codecs.md`; AAC §2.4). In FFmpeg n9.0.2 the Linux QSV session display handle is compiled only `#if CONFIG_VAAPI` (qsv_internal.h:26-28), and the Linux QSV hw device needs `CONFIG_VAAPI` (hwcontext_qsv.c, n8.0). inferred: `*_qsv` in the manylinux wheel probably cannot open a hardware session. Being present in the wheel is not the same as working | Mark Intel/Linux QSV via the PyPI wheel as NOT VERIFIED and likely unusable (inferred from code). Then Linux Intel has no verified hardware path in the wheel |
| W6 | F2 / §4.4: "`mjpeg_qsv` on Intel, fed `yuyv422` for 4:2:2" | The functional pass (FP:33) does not check range. YUY2 is limited range. `NOTES_functional.md` §6.2: "`mjpeg_qsv` fed limited-range NV12 (from YUY2) writes JPEGs tagged `pc`". The re-check confirms that limited-range input gives a JPEG decoding to Y 16..235. A correct JPEG needs full-range yuyv422 first, which is an extra conversion the "native" path was meant to avoid | Add "after expanding YUY2 to full range (as `S/intra_compare/benchpaths.py` does)" to F2 and §4.4 |
| W7 | N8 / §3.1 Ampere JPEG cell: "dec nvJPEG CUDA Y" | `R/gpu_encode/nvimgcodec_jpeg.md`: on the camera 4:2:2 JPEGs, backends `GPU_ONLY` and `HW_GPU_ONLY` fail ("Could not create decoder. Code: 7"). Only `HYBRID_CPU_GPU` / `id:nvjpeg_cuda_decoder` worked | "dec: hybrid CPU+CUDA (measured); GPU-only backends fail on 4:2:2 camera JPEGs" |
| W8 | V4: "Camera JPEGs decode exactly through `createImageBitmap` / `ImageDecoder`: 800/800 seeks" | The 800/800 seeks used **`mjpeg_qsv` re-encoded JPEGs with a burned-in index pattern** (IP §2, "JPEG path: `mjpeg_qsv` from YUYV"), not camera bytes. The camera-bytes test (450 fetches) checked byte identity and that decoding succeeded, with no decoded-pixel comparison (IP §1) | Split it: "re-encoded JPEGs: 800/800 frame-exact by index pattern; camera JPEGs: 450/450 byte-identical by Range fetch and decode without error (pixels not compared)" |
| W9 | §5 "Gaps": "No nvJPEG and no libjpeg-turbo per-stream or scaling bench exists"; "the bench uses default rate control, not matched_settings.json" | True only of `S/hw_accel_target/`. `S/intra_compare/bench_matched_stream.py` (18:59) and `bench_matched_concurrent.py` (19:00) bench jpeg_turbo, ff_mjpeg, mjpeg_qsv, nvJPEG, NVENC and QSV at matched settings with range rules (`benchpaths.py:49-50`, docstring) | Cite those scripts as the req-11 / 17:35 bench. Keep `bench_encode_stream.py` only for non-JPEG pipeline-cost items (or fix X4) |

### 2.3 Generalising from one SKU or one OS

| # | claim | why weak | fix |
|---|---|---|---|
| W10 | §3.3: "RTX 3000+ hw encode Y (NVENC, measured)"; "Intel 2020+ iGPU Y (QSV, measured)" | measured only on an RTX 3070 and a UHD 770 (RPL-S). The rest is source | "measured on RTX 3070 / UHD 770; other generations source" |
| W11 | §3.3 JPEG row and §4.2: "RTX 3000+ ... yes", "JPEG is the only royalty-free format accelerated on both RTX 3000+ and Intel 2020+ iGPUs" | §3.1 itself marks nvJPEG encode on Ada/Blackwell NV (inferred from N6). Intel MTL/ARL/LNL/BMG JPEG encode on Windows is read from the Linux media-driver tables (I6) | Mark the RTX 40/50 and Windows MTL+ parts as inferred |
| W12 | N7 / §3.1 Ada and Blackwell rows: "dec: hardware listed" | The nvJPEG list names architectures, and for Ampere only A100/A30 (data-centre). Whether "Ada" and "Blackwell" include GeForce RTX 40/50 is not stated. The same page says the hardware backend excludes only 4:1:0 and 4:1:1 subsampling, so 4:2:2 is not excluded on paper | "architecture listed; GeForce applicability NOT VERIFIED; doc excludes only 410/411" |
| W13 | N10: "[measured] the 13th session fails on driver 610.88, across nvenc/vulkan/d3d12va/mf" | `R/gpu_encode/nvenc_sessions.json` has `"pyav": "18.0.0"` (skellycam venv), and the extra-API probes are ffmpeg CLI. Under the version rule this is background only | Label it as background (PyAV 18 + CLI). The source claim (12 per system) stands. Add a PyAV 19.0.2 re-check to the bench (B-NV-C limit probe) |
| W14 | §3.3 "two readings" / "H.264 and HEVC cover Intel, AMD and Apple 2020+ parts that have graphics" | This mixes hardware capability with reachability through the PyAV wheel: <br>- AMD AMF is untested; <br>- Linux AMD needs the closed AMF runtime; <br>- Linux Intel QSV is doubtful (W5); <br>- the win_arm64 wheel (Snapdragon) has only `*_d3d12va`/`*_mf` (`wheel_hw_codecs.md`), and the draft does not cover it at all | Add a "reachable through PyAV 19.0.2 and verified" column to §3.3. Add Windows-on-ARM as NOT VERIFIED |

### 2.4 Jellyfin

| # | claim | why weak | fix |
|---|---|---|---|
| W15 | J1: Jellyfin agrees with the vendors on every NVIDIA/Intel claim except J2 | Correct for per-generation codec claims. But Jellyfin intel L5 "On Windows QSV is the only available method" is contradicted for FFmpeg by code (NI §4.3) and by measurement: `h264/hevc_d3d12va` work on the UHD 770 (FP:290-297, device 1) | Add as a scope disagreement (measured), as the draft already does for AMD L14 |

## 3. Checked and holding up

- Intra vs GOP: there is no confusion.
  - Every intra_compare H.264/HEVC point is all-IDR with `has_b_frames=0` (IC §8).
  - All 48 IP clips are all-IDR (IP §2).
  - The AV1/VP9 "plays" cells in §3.3 rest on the **all-intra** CC rows ("AV1 Main 8-bit all-intra", "VP9 profile 0 all-intra": OK in every container except avi; CC §2, §9).
  - K1 is correctly called irrelevant to intra-only output.
- Chromium exactness for H.264/HEVC is a decoded-pixel check of frame identity (burned-in 16-bit index read back; IP §2, §4). It is not a pixel-fidelity check, and nothing in the draft claims fidelity.
- Cited FP lines spot-checked: 13-18, 33, 130-166, 193-200, 290-300, 308-330, 345-353, 372-375, 447, 540, 553. They match the draft's F1-F9 statements.
- The Q2, Q3, Q4, Q5 and Q6 numbers match matched_summary.md, apart from X1 and the rounding in X2.
- The nvJPEG quotes in N6/N7 match the saved copy (sha256 re-checked).
- §4.1 (no royalty-free video codec meets the target) holds on the cited sources and measurements.

## 4. Verdict

The main conclusions hold:
- only H.264/HEVC intra meet the hardware target;
- JPEG is the royalty-free option, accelerated on NVIDIA (CUDA) and Intel;
- passthrough avoids encoding for MJPEG cameras.

Fix before the plan relies on this draft:
- the size penalty for JPEG is overstated by comparing 4:2:2 JPEG with 4:2:0 video on a luma-only metric (W1);
- the nvJPEG size advantage does not hold at matched PSNR (W2);
- the savings against passthrough are not at matched quality (W3);
- the JPEG range bug in `bench_encode_stream.py` must not reach the 23:00 run (X4/W6/W9);
- "reachable on Linux Intel" is likely false (W5);
- three numbers are wrong (X1-X3).
