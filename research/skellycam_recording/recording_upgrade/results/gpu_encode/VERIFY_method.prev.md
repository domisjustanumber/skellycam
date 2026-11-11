# gpu_encode: VERIFY (method lens)

Verifier: adversarial, methodology lens, 2026-11-09 ~16:50-17:00 EST. Target: the draft gpu_encode FINDINGS (returned as text, not on disk).
Paths are relative to `research/skellycam_recording/recording_upgrade/` unless they start with `C:/`.
All new checks are functional only (PyAV 19.0.2 via `uv run --script`, each well under 1 min CPU). No timing numbers. ffmpeg/ffprobe 9.0.2 was used only to inspect existing files (`trace_headers`, packet hashes).
Other agents were running at the same time. nvidia-smi showed 0 NVENC sessions before the pool check (`results/gpu_encode/verify_method_pool.json`).

## New evidence files

| file | what it shows | script |
|---|---|---|
| `results/gpu_encode/verify_method_checks.json` | (a) hevc_qsv `gpb` option, (b) Y PSNR of all existing encoder outputs vs the NV12 source, (c) mjpeg_qsv raw Y plane vs CPU mjpeg | `scripts/gpu_encode/verify_method_checks.py` |
| `results/gpu_encode/verify_method_pool.json` | NVENC pool sharing with a no-sessions control, plus h264_qsv while 12 NVENC sessions are held | `scripts/gpu_encode/verify_method_pool.py` |
| `results/gpu_encode/verify_method_cuvid.json` | NVDEC MJPEG in PyAV: 4:2:0 control vs 4:2:2 | `scripts/gpu_encode/verify_method_cuvid.py` |
| `results/gpu_encode/verify_method_opts.json`, `verify_method_opts_mkv.json` | PyAV re-check of CLI-only settings: nvenc gop 1, d3d12va with default B-frames, d3d12va into MKV | `scripts/gpu_encode/verify_method_opts.py` (the MKV case was re-run on its own) |
| `results/gpu_encode/verify_method_hevc_qsv_trace.txt` | HEVC slice headers of `hevc_qsv_gop15_gpb0.mkv` (ffmpeg `trace_headers`, inspection only) | command in the file header |
| `results/gpu_encode/verify_method_packet_hashes.txt` | packet-payload MD5 of the three hevc_qsv gop15 files; packet sizes of the 1080p input | command in the file header |

Media: `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/gpu_encode/verify_method/`.

## Refuted

| draft claim | evidence | correction |
|---|---|---|
| 2.6 / 6: mjpeg_qsv decode differs from CPU decode by Y max 21 / mean 7.7-8.3; the cause is unexplained ("range suspected") | measured: the raw Y planes (read straight from `frame.planes[0]`, no swscale) match the CPU decode within 1 (mean abs 0.007 at 1080p, 0.009 at 720p; least-squares slope 1.0, intercept 0.002) (`verify_method_checks.json` → `mjpeg_qsv_raw`). The mjpeg_qsv frames are tagged `color_range` 1 (MPEG/limited), but their samples run 0-255 like the CPU's full-range `yuvj422p` (color_range 2). | The 21 / 7.7 came from the measurement method. `to_ndarray(format='gray')` applied a limited-to-full expansion because the frames were mis-tagged. mjpeg_qsv luma is accurate. The real problem is a wrong range tag on its nv12 output, so any conversion that trusts the tag will stretch contrast. Chroma is reduced to 4:2:0 and was still not compared. |
| 2.2 / I7: hevc_qsv B pictures persist "also with `gpb=0`" | measured: the encoder logs `GPB: ON` with `gpb=0` and with `gpb=1` (`verify_method_checks.json` → `gpb`). The packet payloads of the default, gpb0 and gpb1 files are identical (MD5 `3265ef84…` for all three, `verify_method_packet_hashes.txt`). | `gpb=0` had no effect: the option is accepted but not applied on this runtime. Don't present it as a tested way to get P pictures. |
| 2.2 inferred, "NOT VERIFIED at slice level": hevc_qsv B pictures are low-delay with no reordering | measured: `trace_headers` shows 3 slices of type 2 (I) and 29 of type 0 (B). Every explicit RPS has `num_positive_pics = 0`. `slice_pic_order_cnt_lsb` rises 1..14 in decode order in each GOP (`verify_method_hevc_qsv_trace.txt`). | Now measured: generalized P/B (low-delay B). The B slices reference only past pictures, with no reordering. Chromium seek behaviour is still for the chromium topics. |
| I5: "A 16-camera rig cannot use one session per camera on one GeForce GPU, whichever API is used"; "whether QSV has a separate pool is NOT TESTED" | measured, PyAV 19.0.2: with 12 h264_nvenc sessions held (nvidia-smi `12`), `h264_qsv` opened and encoded 3 frames. hevc_nvenc, h264_d3d12va and h264_mf failed. In the no-sessions control all four succeeded (`verify_method_pool.json`). | QSV is not in the NVENC pool. On a machine with an Intel iGPU, streams beyond 12 can go to QSV; the QSV limit itself is untested. MF does not fall back to the Intel MFT when NVENC is full: it still activates the NVIDIA MFT and fails with `MF_E_UNSUPPORTED_D3D_TYPE`. |
| I1: "vp9_qsv is the only working hardware encoder for a lossy codec other than H.264/HEVC" | measured: `mjpeg_qsv` (lossy JPEG) works in the same file (`qsv_recheck_19.0.2.md`), and nvJPEG works outside PyAV (`nvimgcodec_jpeg.json`). | "vp9_qsv is the only working hardware **inter-frame video** encoder other than H.264/HEVC through PyPI PyAV on Gerald. mjpeg_qsv (intra-only JPEG) also works." |

## Weak (survives with a fix)

| claim | problem | fix |
|---|---|---|
| 2.2 "Each output was checked with ffprobe" / 3.1 "works" | The ffprobe check covers structure only (packet and key counts, pict_type). Pixel content was never compared, so a broken encoder giving garbage frames would pass. | Cite the new check. measured: all 26 working PyAV 19.0.2 outputs (NVENC, D3D12, MF, QSV incl. vp9_qsv and mjpeg_qsv) decode to 32 frames with Y PSNR ≥ 45.18 dB vs the NV12 source, and mean Y offset ≤ 0.063 (`verify_method_checks.json` → `psnr_y`). Chroma was not checked. Near-static content makes these PSNRs high, so they are not quality comparisons. |
| 2.4 "So the four APIs share one pool" | The CLI extra encodes had no control run. h264_vulkan and h264_mf showed only generic open errors, so a failure for an unrelated reason could not be ruled out. | Replace with the controlled PyAV 19.0.2 result: hevc_nvenc, h264_d3d12va and h264_mf succeed with 0 sessions held and fail with 12 held (`verify_method_pool.json`). Vulkan stays CLI reference only, with no control. |
| 2.6 NVDEC: "NOT VERIFIED (no saved output)" that 4:2:0 decodes and 4:2:2 fails; I8 attributes the PyAV failure to 4:2:2 | Before this check there was no 4:2:0 control under PyAV, so a PyAV-usage failure could not be ruled out. | measured, PyAV 19.0.2: `diag/j420.mjpeg` (4:2:0) decodes 3/3 to nv12 with both `mjpeg_cuvid` and `mjpeg`+`HWAccel('cuda')`. The 4:2:2 file fails with both (`cuvidDecodePicture ... CUDA_ERROR_INVALID_HANDLE`; `cuvidCreateDecoder ... CUDA_ERROR_NO_DEVICE`, a misleading message) (`verify_method_cuvid.json`). The CLI hang and silent fallback are still NOT VERIFIED. |
| I6 / 2.5: NVENC `gop_size=1` rejected; D3D12 needs `max_b_frames=0`; "D3D12 to MKV through PyAV is untested" | The evidence was CLI only. | measured, PyAV 19.0.2: h264_nvenc gop 1 + max_b_frames 0 fails at open with the same "Gop Length should be greater than number of B frames + 1". h264_d3d12va with PyAV's default max_b_frames (2) fails at `avcodec_send_frame` ("Encode failed"). h264_d3d12va into `.mkv` fails and leaves a 291-byte file (`verify_method_opts.json`, `verify_method_opts_mkv.json`). Observed once: after the failed B-frame encode, the next D3D12 device creation in the same process failed (`887a0020`). On re-run in a fresh process the device was created. D3D12 → MP4 only. |
| I2: on RTX 3000, "GPU JPEG via nvJPEG (CUDA)" is "accelerated"; 2.7 "GPU decode, then GPU encode with no host copy" | `backend:GPU_ONLY` fails for both decode and encode (Code 7). The working decode gives results identical to `backend:HYBRID_CPU_GPU` (`nvimgcodec_jpeg.md`). "No host copy" is the script's intent, not a measured fact. | Say "nvJPEG CUDA (hybrid CPU+GPU) path". Mark "no host copy" as inferred. CPU share is pending B4. Also note that at "q90" nvJPEG gives about 3 dB lower PSNR than OpenCV at about the same bytes (`nvimgcodec_jpeg.json`), so the two are not equal-quality settings. |
| I8: "nvJPEG decodes it at full 4:2:2" | The output is an RGB device buffer, so the chroma was upsampled. The decode is hybrid (see above). | "nvJPEG (hybrid) decodes 4:2:2 JPEG to RGB without first reducing chroma to 4:2:0." |
| 2.8 per-OS encoder lists | The long-name matcher has false negatives. The win_amd64 row lacks long names for h264_qsv, hevc_qsv, mjpeg_qsv, h264_mf and hevc_mf, yet all five work in that wheel (`qsv_recheck_19.0.2.md`, `pyav_functional_19.0.2.md`). Absence in the long-name column is therefore not evidence of absence. | For manylinux x86_64, list QSV h264/hevc/mjpeg short names as well. For aarch64, `hevc_v4l2m2m` / `vp9_v4l2m2m` short names exist, so "H.264 only" should be "H.264 encoder confirmed; hevc/vp9 v4l2m2m encoder status NOT VERIFIED". |
| 3.4 / I1 Intel coverage ("TGL-RPL, 11th-14th gen") vs the target "most CPUs from 2020" | The cited table is the Linux media-driver; NOTES.md:198 says the Windows matrix is NOT VERIFIED, and only RPL-S/Windows was measured. 10th-gen Comet Lake (2020, Gen9.5) and F-SKUs with no iGPU are not covered. | State: measured only on RPL-S/Windows; other generations come from the Linux driver doc; Comet Lake / Ice Lake rows missing; F-SKUs have no QSV. |
| 2.1 "Every QSV row ... failed for that reason"; 2.2 "*_amf fail (no AMD GPU)" | The PyAV rows show only "Unknown error occurred". The vendor-id message is in the CLI log. | Label the cause as inferred, supported by the 16:42 success with the iGPU present. The AMF cause is inferred. |
| I9: "default `h264_nvenc` profile changed from Main to High" | Observed only with `preset=p4`, intra/gop15, nv12 1080p. | "With preset p4 and these settings, PyAV 19 output is High; PyAV 18 was Main (PyAV 18 - background)." |
| 3.1 "HWAccel ctx: yes (cuda)" for NVENC | sw-frame and hwaccel-ctx outputs have identical packet payloads (`h264_nvenc_intra_*`, MD5 `007b99e5…`). Frames still come from numpy on the host either way, so the column says nothing about zero-copy. | Footnote: "opens with a device context; frames are still uploaded from host memory". Upload cost is B3b. |

## Confounders for tonight's bench (no numbers asserted)

- measured: the 1080p NV12 input is 8 near-static frames looped 4×. In `h264_qsv` gop15, I packets are 56-72 kB; P packets range from 356 to 21,814 bytes, and 24 of the 29 are under 6 kB. The packet at the loop restart (index 8) is 16,521 bytes (`verify_method_packet_hashes.txt`).
  - inferred: encode speed and size on this input will be optimistic compared with real motion.
  - Use `--size 720p` (60 consecutive real frames, `common.py` docstring) as the primary B2/B-QSV input, or label 1080p results "static content".
- B1a/B1b run through the ffmpeg CLI, so they are CLI reference only (the draft already says this).
- B2a-d manifest commands use `.venv` (PyAV 18). Swap to `uv run --script` (the draft already says this).
- `bench_pyav_concurrent.py` `make_ctx` handles `*_qsv` generically: sw frames, gop 1 for intra. A QSV run needs no code change: `--codec h264_qsv` was confirmed to open via `CodecContext.create` with the same settings (`verify_method_pool.json`).

## Survives as written

2.1 machine state; NVENC 12-session count; av1_* failures; QSV `HWAccel('qsv')` frame-pool failure (one construction tried, so keep "root cause unknown"); D3D12 default device = NVIDIA; MF picks the NVIDIA MFT; PyAV 18 vs 19 diff (one profile line only); the ffv1_vulkan round trip (framemd5 vs CPU ffv1 decode, a cross-implementation check; Bayer synthetic with zero low byte, so compressibility is not representative, as the draft says); nvImageCodec CUDA error 700 counts.
