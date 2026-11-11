# gpu_encode: FINDINGS (G6 GPU-accelerated encode, G7 royalty-free codecs)

**Status (2026-11-10):**
- This file holds the functional results, the primary sources and the timed numbers from the quiet bench run `20261109T230007`.
- gpu_encode has no bench items of its own in that run: `results/gpu_encode/bench/` is empty and there is no `results/gpu_encode/BENCH.md`.
- The queue replaced or dropped every earlier gpu_encode timing item (`results/BENCH_QUEUE_2300.md` lines 225-230). So the timed numbers here are cited from `results/intra_compare/bench/*.json`, plus pointers into python_integration and uncompressed_intra.
- This file is background to hw_accel_target and intra_compare.
- Verified by two verifiers on 2026-11-10 and revised; see the Verification section at the end.
- Step 3 gap-fill results GF03, GF05, GF06 and GF07 were folded in on 2026-11-10 (sources, static checks and code only; no new timing). GF04 needed no change. See "Step 3 gap-fill" in the Verification section.
- The step 3 fold was verified (`results/gpu_encode/VERIFY_step3.md`: pass with minor fixes) and revised on 2026-11-10: 1 wrong citation path and 7 overstated claims fixed. See "Step 3 verification" at the end.

**Conventions:**
- Paths are relative to `research/skellycam_recording/recording_upgrade/` unless they start with `C:/`.
- Labels:
  - **measured:** a result file, cited.
  - **source:** a primary source. First accessed 2026-11-09. The web sources marked "re-fetched 2026-11-10" were re-fetched by the provenance verifier (`results/gpu_encode/VERIFY_provenance.md` §3). Sources added by the step 3 gap-fill (GF03, GF06, GF07) were accessed 2026-11-10.
  - Gap-fill ids: GF03 = `results/licensing/gapfill/GF03_nvjpeg_licence_arch.md` (quote ids such as R04 are checked verbatim in `GF03_quote_verification.json`); GF05 = `results/chromium_codecs/gapfill/GF05_g8_g9_doc_fixes.md`; GF06 = `results/hw_accel_target/gapfill/GF06_amf_vt_intra.md`; GF07 = `results/hw_accel_target/gapfill/GF07_intel_windows_sources.md`. Pointer notes are in `results/gpu_encode/gapfill/`, plus the header excerpt `results/gpu_encode/gapfill/nvjpeg_h_12.4.0.76_output_formats.txt` (nvjpeg.h lines 143-146, same wheel sha256 as GF03).
  - **code:** file:line.
  - **inferred:** marked and kept short.
- **Version rule:** the implementation under test is PyAV 19.0.2 with its bundled FFmpeg (libavcodec 63.1.102).
  - PyAV 18.0.0 results are labelled "PyAV 18 - background".
  - Results from the gyan ffmpeg 9.0.2 CLI are labelled "CLI reference". The CLI has the same libavcodec (`results/gpu_encode/cli_version.txt`), but requirement 5 says it is not the implementation under test.
- **Quality targets** (HANDOFF §1.1; `results/intra_compare/matched_settings.json` `_meta`):
  - A: SSIM-Y 0.9961, about 52 dB PSNR-Y. A is the fixed primary point.
  - B: PSNR-Y 45 dB, the compact alternative.
  - Every timed number below says which target it is at.
  - The functional checks in 2.2-2.6 are not at either target.
- **Byte ratios:** "× jt422" = bytes ÷ libjpeg-turbo 4:2:2 on the same content (for NV12 rows, the YUY2-source jt422 cell). "× jt (same chroma)" = bytes ÷ libjpeg-turbo at the output's own chroma (jt420 for 4:2:0 outputs). QC compares luma only, so the same-chroma ratio is the fairer one for JPEG vs JPEG.
- **Affinity:** cells marked † ran after libx265 widened the process affinity in items 1-3; P-core-only is not shown for them (§5 flag 3).

## 1. Questions answered

1. Which hardware encoders work on Gerald through PyAV 19.0.2, and which of them work all-intra (G6)? Gerald has an RTX 3070 (Ampere) and the UHD 770 iGPU of the i7-14700K.
2. Which of them encode a codec other than H.264/HEVC (G7 candidates)? Which royalty-free GPU paths exist outside PyAV?
3. Which hardware encoders ship in the PyPI PyAV wheels on each OS (G6, cross-platform)?
4. Can the GPU decode or encode the cameras' 4:2:2 MJPEG? Which chroma does each GPU JPEG encoder write, and from which input?
5. What is the NVENC concurrent-session limit, and which other APIs share it? Does QSV have a limit up to 32?
6. Quiet-run throughput, at target A or B: how many 1080p30 and 720p30 intra streams each GPU encoder sustains, and at what host CPU cost.

## 2. Findings

### 2.1 Machine state

- measured: during the original functional investigation (2026-11-09 11:36), the UHD 770 was `Unknown / Present False / CM_PROB_PHANTOM` (`results/gpu_encode/system_probe.txt`).
- measured, CLI reference: every QSV row in `ff_functional.md` failed with `Failed to find d3d11va adapter by vendor id 0x8086`. The string occurs 10 times (`results/gpu_encode/ff_functional.md`; count re-checked in `VERIFY_provenance.md` §2).
- inferred: the PyAV QSV rows in `pyav_functional_*.md` failed for the same reason. They record `UnknownError [Errno 1313558101]`, the same AVERROR code, and the same encoders work once the iGPU is present (`qsv_recheck_19.0.2.md`).
- inferred: every `*_amf` encoder fails because the machine has no AMD GPU. The result files do not state the cause.
- measured: from 16:42 on 2026-11-09 the UHD 770 was present (`results/gpu_encode/qsv_recheck_19.0.2.md` header; `results/hw_accel_target/system_probe_1700.txt`). Every QSV statement below comes from runs with the iGPU present.
- measured: during the quiet run, `display_devices` lists `OK|True|Intel(R) UHD Graphics 770` and `OK|True|NVIDIA GeForce RTX 3070` in every intra_compare JSON (`system_before`, e.g. `results/intra_compare/bench/matched_stream_A_1080p_20261110T042204Z.json`). No QSV item was skipped (`results/BENCH_RUN_2300_SUMMARY.md` §2).
- measured: RTX 3070, driver 610.88, compute capability 8.6 (`system_probe.txt`).
- measured: during the run the driver was still 610.88. `env.nvidia_smi_before` reads "NVIDIA GeForce RTX 3070, 610.88, 0, 0 %, 0 %, 479 MiB" at item 40, 03:16 (`results/python_integration/bench/nvjpeg_decode_quiet1_2300.json`). The intra_compare JSONs do not record the driver version (`results/intra_compare/BENCH.md` header).
- measured: the RTX 3070 Vulkan device enables `VK_KHR_video_encode_h264` and `_encode_h265`, and does not list `VK_KHR_video_encode_av1` (`system_probe.txt`). This covers the device extensions ffmpeg uses, not a full enumeration.

### 2.2 PyAV 19.0.2 on Gerald: encoders (functional)

**Input for every test:** 32 NV12 1080p frames, made of 8 near-static real frames looped 4 times (`scripts/gpu_encode/common.py:4-5`), with `max_b_frames=0`. "intra" means gop_size 0 for NVENC and 1 for the other encoders.

- measured: each of the 26 working outputs decodes to 32 frames. This covers NVENC, D3D12, MF and QSV, including vp9_qsv and mjpeg_qsv.
  - Y PSNR against the NV12 source is ≥ 45.18 dB, and the mean Y offset is ≤ 0.063 (`results/gpu_encode/verify_method_checks.json` → `psnr_y`).
  - Chroma was not checked.
  - This is a sanity check on near-static content, not a check at target A or B.
- measured: `h264_nvenc` and `hevc_nvenc` work intra (32 I) and gop15 (3 I + 29 P), with software frames and with `HWAccel('cuda')`. H.264 comes out as High and HEVC as Main (`results/gpu_encode/pyav_functional_19.0.2.md`).
- measured: the software-frame and `HWAccel('cuda')` outputs have identical packet payloads for h264_nvenc intra, h264_nvenc gop15 and hevc_nvenc intra (`results/gpu_encode/revise_nvenc_packet_hashes.txt`). In both modes the frames come from numpy in host memory.
- measured, static (advertised pixel formats, no device opened): `h264_nvenc` and `hevc_nvenc` do not list `yuyv422`. They list `nv12`, `yuv420p`, `yuv444p`, `nv16`, `p210le`, `bgr0`, `cuda`, `d3d11` and others. `h264_qsv` lists only `nv12` and `qsv`. `hevc_qsv` and `mjpeg_qsv` list `yuyv422` (`results/gpu_encode/verify_method_fmts.json`).
- measured: `av1_nvenc` fails at `avcodec_open2`: with software frames "Generic error in an external library", with `HWAccel('cuda')` "Function not implemented" (`pyav_functional_19.0.2.md`).
- measured: `h264_d3d12va` and `hevc_d3d12va` fail with software frames (`returned 22`). With `HWAccel('d3d12va')` they work intra and gop15 when written to MP4 (`pyav_functional_19.0.2.md`).
- measured: `h264_d3d12va` with PyAV's default `max_b_frames` (2) fails at `avcodec_send_frame` with "Encode failed: Unknown error occurred" (`results/gpu_encode/verify_method_opts.json`).
- measured: writing `h264_d3d12va` to `.mkv` fails with `InvalidDataError` and leaves a 291-byte file (`results/gpu_encode/verify_method_opts_mkv.json`).
- measured, once: right after the failed B-frame encode, D3D12 device creation failed in the same process (`887a0020`). It succeeded in a fresh process (`verify_method_opts.json`, `verify_method_opts_mkv.json`).
- measured: with the iGPU present, the default D3D12 device is the NVIDIA card for both h264 and hevc ("D3D12VA: Using device 10de:2484", 8/8 I) (`results/gpu_encode/adapter_check_19.0.2.json`, `adapter_check_hevc_19.0.2.json`).
- measured: `av1_d3d12va` fails at open in both modes (`pyav_functional_19.0.2.md`).
- measured: `h264_mf` and `hevc_mf` with `hw_encoding=1` work intra and gop15. H.264 comes out as Constrained Baseline (`pyav_functional_19.0.2.md`).
- measured: with the iGPU present, MF activates "MFT 0", which is the NVIDIA H.264 or HEVC Encoder MFT, not the Intel one (`adapter_check_19.0.2.json`, `adapter_check_hevc_19.0.2.json`).
- measured: PyAV `av1_mf` fails in both iGPU states. With the iGPU present it picks the Intel AV1 MFT and fails with `InvalidDataError` (`pyav_functional_19.0.2.md`, `qsv_recheck_19.0.2.md`).
- measured (iGPU present): the QSV encoders work with software frames:

  | encoder | intra | gop15 | profile / pix_fmt, NV12 input |
  |---|---|---|---|
  | `h264_qsv` | 32 I | 3 I + 29 P | High / yuv420p |
  | `hevc_qsv` | 32 I | 3 I + 29 B (low-delay; see below) | Main / yuv420p |
  | `vp9_qsv` | 32 I | 3 I + 29 P | Profile 0 / yuv420p |
  | `mjpeg_qsv` | 32 I | 32 I | Baseline / yuvj420p (NV12 input; for YUY2 input see 2.7) |

  Source: `results/gpu_encode/qsv_recheck_19.0.2.md`.
- measured: `av1_qsv` fails at open with "Current codec type is unsupported" (`qsv_recheck_19.0.2.md`).
- measured: every QSV encoder fails with `HWAccel('qsv')` ("Error initializing a child frames context / Error creating an internal frame pool"). Only one construction was tried (`qsv_recheck_19.0.2.md`).
- measured, functional: `hevc_qsv` with the target-A options (`global_quality` 1534) opens and encodes 8/8 keyframes with `low_power=1`, with `preset=veryfast` and with both; each gives a different byte count from the default (`results/gpu_encode/verify_method_lowpower.json`). Speed was not measured.
- measured, background (GOP, out of scope by requirement 8): in `hevc_qsv` gop15 the 29 non-IDR pictures are B slices that reference only past pictures (`num_positive_pics = 0`). pts == dts throughout and `has_b_frames` = 0 (`results/gpu_encode/verify_method_hevc_qsv_trace.txt`, `qsv_recheck2_ffprobe.txt`).
- measured, background: `gpb=0` had no effect. The encoder logs `GPB: ON` either way, and the payloads are identical (`verify_method_checks.json` → `gpb`; `verify_method_packet_hashes.txt`).
- measured: `h264/hevc/av1/ffv1_vulkan` are not in `av.codecs_available` (`pyav_functional_19.0.2.md`).
- measured: `hwdevices_available` = cuda, dxva2, qsv, d3d11va, d3d12va, amf; vulkan is not in the list (`pyav_functional_19.0.2.md`).
- measured: in the matched-quality sweeps every NVENC and QSV H.264/HEVC output is all-intra, all VCL IDR, `decoder_has_b_frames` 0 and `max_b_frames` 0 (`results/intra_compare/raw/*_nvenc_*.json`, `*_qsv_*.json`).
  - gop_size is 0 for NVENC and 1 for QSV.
  - Profiles: h264_nvenc High, hevc_nvenc Main, h264_qsv High, hevc_qsv 4:2:0 Main, hevc_qsv 4:2:2 Rext (`decoder_profile`, `yuy2_1080p` files).

### 2.3 PyAV 18 vs 19

- measured (PyAV 18 - background): with the iGPU absent, PyAV 18.0.0 and 19.0.2 give the same pass/fail on every row. One output differs: with `preset=p4`, `h264_nvenc` reports Main under 18 and High under 19 (`pyav_functional_18.0.0.md` vs `pyav_functional_19.0.2.md`).
- measured: libavcodec is 62.28.102 in PyAV 18.0.0 and 63.1.102 in PyAV 19.0.2 (headers of `pyav_functional_*.md`).
- measured: in all 6 PyPI wheels inspected, PyAV 19.0.2 has the same hardware codec names as 18.0.0 (`results/gpu_encode/wheel_hw_codecs.md`).

### 2.4 Session limits and pool sharing

**Quiet run (PyAV 19.0.2, 1080p, matched settings at target A).** Limit probe = open up to 32 encoders one by one, 2 frames each, all kept open, in one process (`scripts/intra_compare/bench_matched_concurrent.py:217-234`).

- measured: `h264_nvenc` opened 12 of 32. The 13th `avcodec_open2` failed with `ExternalError: [Errno 542398533] Generic error in an external library`. nvidia-smi read "0, 0 %, 0 %, 0 %" before and "12, 5 %, 0 %, 0 %" at the peak (`results/intra_compare/bench/matched_concurrent_h264_nvenc_420_1080p_nv12_thread_20261110T044648Z.json` → `limit_probe`).
- measured: `hevc_nvenc` behaves the same: 12 of 32 opened, same error, nvidia-smi 12 at the peak (`results/intra_compare/bench/matched_concurrent_hevc_nvenc_420_1080p_nv12_thread_20261110T045146Z.json` → `limit_probe`).
- measured: every N=16 NVENC scaling run opened 12 streams, and `open_error` is the same ExternalError. This held in all 7 NVENC scaling items, both modes and every rep (`results/intra_compare/BENCH.md` §2; `runs[].opened` = 12 in the h264_nvenc file above).
- measured: QSV opened 32 of 32 with no error for `h264_qsv` 4:2:0 from NV12, `mjpeg_qsv` 4:2:0 from NV12 and `mjpeg_qsv` 4:2:2 from YUY2. nvidia-smi stayed at 0 sessions (`limit_probe` in `matched_concurrent_h264_qsv_420_1080p_nv12_thread_20261110T045738Z.json`, `matched_concurrent_mjpeg_qsv_420_1080p_nv12_thread_20261110T052313Z.json`, `matched_concurrent_mjpeg_qsv_422_1080p_yuy2_thread_20261110T064127Z.json`).
- measured: `hevc_qsv` had no limit probe, but every N=16 run opened 16 of 16 (`matched_concurrent_hevc_qsv_420_1080p_nv12_thread_20261110T051629Z.json`).
- Scope: every quiet-run probe ran in one process. A cross-process cap was not measured in the quiet run (`VERIFY_provenance.md` §2.4). The probe counts encoders that open, not encoders that sustain throughput (see 3.2).

**Earlier functional checks (PyAV 19.0.2, busier machine):**
- measured: 12 `h264_nvenc` sessions (1280×720) opened, and the 13th failed. nvidia-smi showed 12 while they were open (`results/gpu_encode/nvenc_sessions_19.0.2.json`).
- measured, with a control: with 12 `h264_nvenc` sessions held, these failed while each had encoded 3 packets with no sessions held (`results/gpu_encode/verify_method_pool.json`):
  - `hevc_nvenc` ("incompatible client key (21)");
  - `h264_d3d12va` ("Failed to create encoder.");
  - `h264_mf` (`MF_E_UNSUPPORTED_D3D_TYPE`).
  - `h264_qsv` still encoded. `h264_mf` did not fall back to the Intel MFT.
- measured, CLI reference, no control: `h264_vulkan` also failed with 12 sessions held (`nvenc_sessions_19.0.2.json`).
- inferred: NVENC, D3D12 and MF (through the NVIDIA MFT) share the GeForce 12-session pool, and Vulkan probably does too (CLI only, no control). QSV is outside that pool.
- measured (PyAV 18 - background): the same limit, 12 (`results/gpu_encode/nvenc_sessions.json`).
- source: NVIDIA support matrix, "Max # of concurrent sessions": 12 in 82 of 90 GeForce rows; rows without NVENC give 0 or n/a. Counted on 2026-11-09; re-fetched 2026-11-10, consistent, not recounted (`VERIFY_provenance.md` §3; https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new). The cap in general (other GPUs, other processes, other drivers) rests on this source; on Gerald it is measured with driver 610.88.

### 2.5 ffmpeg 9.0.2 CLI hardware encoders (CLI reference; iGPU absent)

Source for every bullet unless stated: `results/gpu_encode/ff_functional.md` / `.json`.

- measured, CLI: `h264_nvenc -g 1 -bf 0` fails with "Gop Length should be greater than number of B frames + 1"; `-g 0` gives 32 I.
- measured, PyAV 19.0.2: gop_size 1 fails at open with the same message (`verify_method_opts.json`).
- code: `libavcodec/nvenc.c:1761-1767` @ n9.0.2: `gop_size == 0` takes the intra-only path (NOTES.md §3; saved copy, not re-fetched).
- measured: `h264_vulkan` (High) and `hevc_vulkan` (Main) work intra and gop15. `av1_vulkan` fails with "Device does not support encoding av1!".
- measured: `ffv1_vulkan` round-trips byte-exact (8/8 frames, framemd5 against a CPU decode) on yuv420p (`-level 4`), bgr0 and `bayer_rggb16le` (`ff_functional.json` → `roundtrip`). At level 3, yuv420p and gop15 fail.
- measured: `ffv1_vulkan` gop15 gives 3 key packets out of 32. inferred, thin, from `ffv1enc_vulkan.c:279,289`: the non-key packets are probably not independently decodable, so use gop 1.
- measured: `prores_ks_vulkan` works: 32 I, HQ, yuv422p10le.
- measured: 8 synthetic 16-bit Bayer frames: ffv1_vulkan writes 8,087,879 B and CPU ffv1 with defaults 17,047,238 B (`ls -l` of `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/gpu_encode/diag/`). The settings differ and the content is synthetic, so this is not a codec comparison.

### 2.6 MJPEG (camera 4:2:2) decode on the GPU

- measured, PyAV 19.0.2: on real 4:2:2 camera JPEGs, `mjpeg_cuvid` and `mjpeg` + `HWAccel('cuda')` both fail (`pyav_functional_19.0.2.md`).
- measured, with a control: a 4:2:0 JPEG (`diag/j420.mjpeg`) decodes 3/3 to nv12 by both routes, and the cameras' 4:2:2 fails (`results/gpu_encode/verify_method_cuvid.json`).
- source: the NVDEC guide (SDK 13.0) lists "Hybrid (CUDA + CPU) JPEG" and says nothing about 4:2:2 (re-fetched 2026-11-10; https://docs.nvidia.com/video-technologies/video-codec-sdk/13.0/nvdec-video-decoder-api-prog-guide/index.html).
- measured: the `mjpeg_qsv` decoder decodes the camera 4:2:2 JPEGs 5/5 per set, and its output is **nv12**, so it reduces chroma to 4:2:0 (`qsv_recheck_19.0.2.md`). This is the decoder. For the encoder's output chroma see 2.7.
- measured: mjpeg_qsv luma matches the CPU decode: max |diff| 1, mean 0.007-0.009, slope 1.0 (`verify_method_checks.json` → `mjpeg_qsv_raw`).
- measured: mjpeg_qsv tags its frames limited range, while the samples span full range (`verify_method_checks.json`).
  - inferred: a conversion that trusts the tag stretches contrast.
- measured: `mjpeg` + `HWAccel('qsv', allow_software_fallback=False)` returned `yuvj422p` software frames (`qsv_recheck_19.0.2.md`). inferred, NOT VERIFIED: this was a CPU decode.
- measured, nvImageCodec 0.10.0.9 (not PyAV): `nvjpeg_cuda_decoder` decodes the 4:2:2 camera JPEGs to an RGB device buffer at 53.14 dB (1080p) and 54.18 dB (720p) against ffmpeg's CPU decode (`results/gpu_encode/nvimgcodec_jpeg.json`). `GPU_ONLY` / `HW_GPU_ONLY` backends fail with "Code: 7" (`nvimgcodec_jpeg.md`).
- measured, quiet run, nvImageCodec 0.9.0.20 (`results/python_integration/bench/nvjpeg_decode_quiet1_2300.json`; table in `results/python_integration/BENCH.md` lines 198-202). Medians per frame, camera sets only:

  | set | decode left on GPU | decode + copy to host |
  |---|---|---|
  | c930e 720p | 0.72 ms | 1.44 ms |
  | c922 720p | 0.93 ms | 1.68 ms |
  | c930e 1080p | 2.08 ms | 3.45 ms |
  | c922 1080p | 2.27 ms | 3.64 ms |

  - The non-camera `generic_1080p` set (11 frames; `scripts/python_integration/bench_nvjpeg_decode.py:36`) gives 1.92 / 3.37 ms; it is not a camera figure.
  - These are host wall times from one run; the JSON has no CPU-time fields.
- inferred: the working nvJPEG decode is the hybrid CPU+CUDA path. Its host CPU share is not measured (see 6).
- source, lead (NOT TESTED): the CUDA 12.9 Update 1 release notes, section "nvJPEG: Release 12.9" (not the "12.9 Update 1" section): "Added JPEG decoding support for two new formats: NV12 and YUY2, for both hardware engine and CUDA. For NV12, the chroma subsampling must be 420, and for YUY2, it must be 422." (https://docs.nvidia.com/cuda/archive/12.9.1/cuda-toolkit-release-notes/index.html, accessed 2026-11-10; GF03 R21).
  - code: the measured nvidia-nvjpeg-cu12 12.4.0.76 wheel header declares `NVJPEG_OUTPUT_NV12 = 8` (`nvjpeg.h:144`) and `NVJPEG_OUTPUT_YUY2 = 9` (`nvjpeg.h:146`), with the comment "U and V are at half horizontal resolution - 422" (`:145`) (excerpt `results/gpu_encode/gapfill/nvjpeg_h_12.4.0.76_output_formats.txt`).
  - A GPU decode of the camera 4:2:2 MJPEG to YUY2 through this route: NOT TESTED. Whether nvImageCodec exposes it: NOT VERIFIED.

### 2.7 GPU JPEG encode: chroma by input, and quiet-run cost

**mjpeg_qsv output chroma follows the pix_fmt it is fed** (corrects the earlier "4:2:0 output" wording; HANDOFF §4):
- measured: fed `nv12`, mjpeg_qsv writes 4:2:0. Every point in `results/intra_compare/raw/mjpeg_qsv_420__{yuy2_1080p,yuy2_720p,mjpeg_1080p,mjpeg_720p}.json` has `pix_fmt_fed` nv12 and `decoded_pix_fmts` [yuvj420p] (19-23 points per file, all intra).
- measured: fed `yuyv422` (YUY2), mjpeg_qsv writes 4:2:2. Every point in `results/intra_compare/raw/mjpeg_qsv_422__{yuy2_1080p,yuy2_720p,mjpeg_1080p,mjpeg_720p}.json` has `pix_fmt_fed` yuyv422 and `decoded_pix_fmts` [yuvj422p] (19-23 points per file, all intra, `sof` 0xc0 = baseline).
- measured: `matched_settings.json` records the same pairing: mjpeg_qsv_420 has `pix_fmt_fed` nv12 and chroma 4:2:0, and mjpeg_qsv_422 has yuyv422 and 4:2:2. `global_quality` is 94 at target A and 44 at target B for `yuy2_1080p`; across classes it is 83-95 at A and 43-59 at B.
- measured, earlier check: from NV12 the encoder output is Baseline yuvj420p (`qsv_recheck_19.0.2.md`).
- source: the Intel media-driver doc lists JPEG encode "input format NV12/YUY2/UYVY/ABGR/Y8 and output format YUV400/YUV420/YUV422H_2Y/YUV444/RGB24" (`docs/media_features.md` line 79 @ intel-media-26.3.5, re-fetched 2026-11-10). This is the Linux driver. On Windows, YUY2 → 4:2:2 is measured on RPL-S (UHD 770) only.
- measured: the "mjpeg_cpu" rows feed mjpeg_qsv_422 decoded camera frames as yuyv422 and get yuvj422p, so a 4:2:2 camera JPEG re-encodes to 4:2:2 (`mjpeg_qsv_422__mjpeg_1080p.json`).
- measured: the `mjpeg_qsv` decoder (2.6) is a different case. It outputs nv12, so a decode → mjpeg_qsv chain gives 4:2:0. The `mjpeg_qsv` source rows in item 1 feed nv12 to mjpeg_qsv_420 (`matched_stream_A_1080p_20261110T042204Z.json`, `pix_fmt_fed` nv12).

**Quiet run, single stream (one thread, unpaced, packets discarded; median (min-max) over the timed reps)**

Sources: `results/intra_compare/bench/matched_stream_A_1080p_20261110T042204Z.json` (5 reps), `..._A_720p_20261110T043459Z.json` (4 reps) and `..._B_1080p_20261110T044204Z.json` (3 reps). † = ran after the libx265 affinity widening (§5 flag 3).

- measured, target A, 1080p:
  - mjpeg_qsv_420 from NV12: 602 (601-606) fps, 1.81 ms CPU/frame, 276,187 B/frame: 1.08 × jt420 (same chroma), 0.96 × jt422.
  - mjpeg_qsv_422 from YUY2 †: 481 (481-482) fps, 1.58 ms CPU/frame, 308,099 B: 1.07 × jt422 (same chroma).
  - QC for both: SSIM-Y 0.99695 (target A hit).
- measured, target A, 720p:
  - mjpeg_qsv_420 from NV12: 1,155 (1,140-1,161) fps, 1.09 × jt420.
  - mjpeg_qsv_422 from YUY2 †: 894 (891-896) fps, 0.66 ms CPU/frame, 182,530 B: 1.09 × jt422 (same chroma).
- measured, target B, 1080p: mjpeg_qsv_420 from NV12: 618 (617-621) fps, 68,768 B/frame (1.00 × jt420), QC PSNR-Y 45.17 dB.
- measured, CPU per frame under load (scaling items, P-core-only, target A 1080p): mjpeg_qsv_422 from YUY2 uses 1.79-2.03 ms/frame at 16 paced streams and 2.17-2.37 unpaced; mjpeg_qsv_420 from NV12 uses 2.14-2.20 ms/frame at 16 paced (`matched_concurrent_mjpeg_qsv_422_1080p_yuy2_thread_20261110T064127Z.json`, `matched_concurrent_mjpeg_qsv_420_1080p_nv12_thread_20261110T052313Z.json`). These are the figures to use for recorder sizing.
- measured, nvJPEG (nvImageCodec 0.10.0.9) at target A, 1080p:
  - from exact RGB † (encode call only): 1,126 (1,117-1,132) fps at 0.87 ms CPU/frame (4:2:0);
  - from host NV12 through swscale `rgb24`: 323 (283-341) fps at 7.57 ms CPU/frame, 225,514 B: 0.88 × jt420 (same chroma), 0.79 × jt422;
  - from YUY2 via swscale `rgb24`, 4:2:2 output †: 343 (340-368) fps, 8.14 ms CPU/frame, 253,793 B: 0.88 × jt422 (same chroma).
- measured: the nvJPEG quality gap depends on the input pipeline:
  - sweep (exact float RGB input, `matched_settings.json` → nvjpeg_420 `options.input`): target A reached at quality 93 with PSNR-Y 50.797 dB, against libjpeg-turbo 4:2:2 at 52.24 dB, so 1.44 dB lower PSNR-Y at the same SSIM-Y (arithmetic).
  - timed path (swscale rgb24 from NV12/YUY2), 4-frame QC: 52.344-52.365 dB against libjpeg-turbo's 52.82, a 0.46-0.48 dB gap (arithmetic; item 1 `summary[].quality_check`).
- measured: **nvJPEG fed CPU-decoded camera MJPEG misses the target.**
  - target A, 1080p: SSIM-Y 0.9954 < 0.9961, PSNR-Y 45.21 dB against 49.995 matched;
  - target A, 720p: PSNR-Y 45.51 dB, 3.8 dB under matched (49.30); SSIM passes;
  - target B, 1080p: PSNR-Y 43.14 dB < 45.
  - Files: items 1-3 JSON, `summary[].quality_check` (`source` mjpeg_cpu).
  - inferred: the cause is the swscale RGB path (`results/intra_compare/BENCH.md` caveat 3; `results/intra_compare/nvjpeg_rgb_diag.json`).
  - measured: the item-1 nvjpeg_420 row fed `mjpeg_qsv`-decoded frames † passes its QC (PSNR-Y 56.46 dB, SSIM-Y 0.99788) at 160,252 B (1.23 × jt420 on the same source). Why it differs from the mjpeg_cpu row was not examined (NOT VERIFIED).
- measured, earlier and superseded for sizing: nvJPEG q90 scored 2.4-2.8 dB below OpenCV q90 at about the same size (`nvimgcodec_jpeg.json`). The matched-quality numbers above replace this for any size comparison.
- measured: nvImageCodec 0.10.0.9 rejects full-resolution YUV input, both planar (`P_YUV`) and interleaved (`I_YUV`), with "RuntimeError: encode returned None", and accepts gray (`P_Y`, `I_Y`) (`results/gpu_encode/nvimgcodec_jpeg.md` lines 41-44).
  - code: the test YUV was 4:4:4, not chroma-subsampled (`scripts/gpu_encode/nvimgcodec_jpeg.py:129-131`).
  - source, context only: the nvImageCodec 0.10 release notes sentence "Planar YUV (P_YUV) is not converted, and CPU-only encoders are unaffected." ends a paragraph about the new fallback that interleaves planar RGB/BGR on the GPU for encoders that only accept interleaved samples ("nvTIFF being the case that prompted this") (https://docs.nvidia.com/cuda/nvimagecodec/release_notes_v0.10.0.html, accessed 2026-11-10; GF03 R19). It does not say that YUV input to the nvJPEG encoder is rejected.
  - source: the same notes say "Encoding a chroma-subsampled Image is not supported yet and raises ValueError." (GF03 R20). inferred: this does not describe the test case either: the input was 4:4:4 and the error was not ValueError.
  - The cause of the P_YUV and I_YUV rejection: NOT VERIFIED.
  - code: nvJPEG itself exposes YUV and NV12 encode input: `NVJPEG_INPUT_YUV` (`nvjpeg.h:154`), `NVJPEG_INPUT_NV12` (`:159`), `nvjpegEncodeYUV` (`:540`) and `nvjpegEncode` (`:560`) in the nvidia-nvjpeg-cu12 12.4.0.76 wheel header (excerpt `results/licensing/gapfill/GF03_sources/nvjpeg_h_12.4.0.76_lines.txt`).
  - A YUV-input binding: NOT TESTED. This supports the existing "exact-RGB or YUV-input nvJPEG route: NOT TESTED" item (I8, 6.2).
- measured: releasing GPU-decoded images without synchronisation printed 392 `CUDA error #700` lines in some runs, all with exit code 0 (`results/gpu_encode/nvimgcodec_lifetime.json`).

**nvJPEG library provenance (GF03):**
- measured: `nvidia-nvimgcodec-cu12[nvjpeg]==0.10.0.9` pulled `nvidia-nvjpeg-cu12==12.4.0.76` (`results/gpu_encode/NOTES.md:148`).
- source: the measured nvidia-nvjpeg-cu12 12.4.0.76 is CUDA 12.9 Update 1's libnvjpeg: `redistrib_12.9.1.json` gives libnvjpeg `"version": "12.4.0.76"` (https://developer.download.nvidia.com/compute/cuda/redist/redistrib_12.9.1.json, accessed 2026-11-10; GF03 R04). It is not CUDA 12.4's: `redistrib_12.4.0.json` gives `"version": "12.3.1.89"` (GF03 R05).
- source: the nvimgcodec `[nvjpeg]` extra does not pin it: `Requires-Dist: nvidia-nvjpeg-cu12; extra == "nvjpeg"` (nvidia_nvimgcodec_cu12-0.10.0.9 win_amd64 wheel METADATA, accessed 2026-11-10; GF03 G04).
- inferred: pin nvidia-nvjpeg-cu12 explicitly in any shipped dependency.

### 2.8 Quiet-run throughput of the H.264/HEVC GPU encoders (intra_compare items)

All numbers are at the matched settings in `results/intra_compare/matched_settings.json`, which differ per input class:
- NVENC: `preset p4, tune ll, rc constqp, i_qfactor 1, i_qoffset 0`. For `yuy2_1080p`: qp 12 at target A and 31 at target B (both h264 and hevc). Across classes: qp 11-14 at A, 28-31 at B.
- QSV: `+qscale` with `global_quality` = 118 × QP. For `yuy2_1080p`: h264_qsv QP 12 / hevc_qsv QP 13 at A, QP 30 / 31 at B. Across classes: QP 12-14 at A, 28-31 at B.
- All encoders: `max_b_frames=0`, intra gop (`gop_size` set at `scripts/intra_compare/benchpaths.py:147`).
- inferred: the timed rows are intra. The timed benches record no keyframe flags; intra is shown by the untimed sweeps with identical settings (2.2).

**Single stream** (same files as 2.7; † as in 2.7):
- measured, target A, 1080p from NV12 (all P-core-only), median (min-max) fps / CPU ms per frame / bytes / × jt420 (same chroma) / × jt422:
  - h264_nvenc 540 (540-540) / 1.40 / 157,924 / 0.62 / 0.55;
  - hevc_nvenc 390 (389-390) / 1.47 / 135,292 / 0.53 / 0.47;
  - h264_qsv 585 (585-585) / 2.04 / 170,101 / 0.67 / 0.59;
  - hevc_qsv 65 (65-66) / 2.81 / 117,180 / 0.46 / 0.41.
  - QC SSIM-Y 0.99705-0.9973, all hit target A.
- measured: nvidia-smi encoder utilisation is 100 % for both NVENC rows in that item (`results/intra_compare/BENCH.md` §3.1, from the same JSON).
- measured: in the item-1 GPU Engine counters, hevc_qsv loads the iGPU **3D** engine (mean 81-91 % per timed rep; VideoDecode 7.5-8.5 %), while h264_qsv (VideoDecode 52-91 %, 3D 26-45 %) and mjpeg_qsv_420 (VideoDecode 29-51 %) load the engine Windows labels VideoDecode (`runs[].gpu.gpu_engine_util_pct`, NV12 rows). inferred: the default hevc_qsv mode runs largely on the EUs rather than the fixed-function encoder; `low_power=1` opens (2.2) but was not timed.
- measured, target A, 720p from NV12: h264_nvenc 1,115, hevc_nvenc 842, h264_qsv 1,151 and hevc_qsv 128 fps (`matched_stream_A_720p_20261110T043459Z.json`).
- measured, target B, 1080p from NV12 (P-core-only):
  - h264_nvenc 635 fps, 21,825 B; QC 44.61 dB, a knob-step shortfall also present in the sweep;
  - hevc_nvenc 425 fps, 14,506 B;
  - h264_qsv 691 fps, 27,081 B; QC 44.74 dB, knob-step;
  - hevc_qsv 87 fps, 14,449 B.
  - File: `matched_stream_B_1080p_20261110T044204Z.json`.
- measured, YUY2 input cost:
  - Primary (P-core-only, scaling items, target A 1080p, 12 paced streams): h264_nvenc from YUY2 uses 2.41-2.64 cores (6.69-7.34 ms CPU/frame) against 0.60-0.64 cores (1.67-1.76 ms) from NV12 (`matched_concurrent_h264_nvenc_420_1080p_yuy2_thread_20261110T084300Z.json` vs `..._nv12_thread_20261110T044648Z.json`; affinity 0-15 before and after in both).
  - Single stream †: CPU rises to 6.67 ms/frame (h264_nvenc) and 8.44 (h264_qsv), against 1.40 and 2.04 from NV12, at the same fps (item 1 JSON).
  - The 4:2:0 NVENC/QSV paths get YUY2 → NV12 by swscale inside the timed loop (code: `scripts/intra_compare/benchpaths.py:229`; rgb24 for nvJPEG at 214-215, 227-228, 239-240; `Feed.next` is 199-244).
  - hevc_qsv_422, fed yuyv422 natively †: 3.18 ms/frame at 64 fps, 155,864 B (0.54 × jt422).
- measured: hevc_qsv_422 from YUY2 outputs `yuv422p`, profile Rext, all IDR (`results/intra_compare/raw/hevc_qsv_422__yuy2_1080p.json`).

**Concurrent streams, 1080p30 paced (450 frames per stream) and unpaced (300 frames per stream), one thread per stream, P-core-only** (affinity 0-15 before and after in every scaling file). "keeps up" = every stream ≥ 0.98 × 30 fps with end lag < 1/30 s in every rep (`bench_matched_concurrent.py:130-131`); it allows late frames, so the late-frame share is given where it is non-zero. Values are median (min-max) over 3 reps for items 4-10 and 2 reps for the rest.

- measured: h264_nvenc, target A, NV12. N=1, 4 and 8 keep up. N=16 opens 12, and the 12 keep up with 0 late frames at 0.61 (0.60-0.64) CPU cores. Unpaced aggregate: 512 (N=1), 534, 539, then 542 (537-542) fps at 12 streams (`matched_concurrent_h264_nvenc_420_1080p_nv12_thread_20261110T044648Z.json`).
- measured: hevc_nvenc, target A, NV12. 12 streams keep up at 0.65 (0.59-0.66) cores. Unpaced aggregate medians 389-391 fps at every N (range 380-392) (`matched_concurrent_hevc_nvenc_420_1080p_nv12_thread_20261110T045146Z.json`).
- measured: h264_qsv, target A, NV12. 16 of 16 keep up with 0 late frames at 1.25 (1.23-1.28) cores. Unpaced aggregate 679 (678-682) fps at N=16 and 542 at N=1 (`matched_concurrent_h264_qsv_420_1080p_nv12_thread_20261110T045738Z.json`).
- measured: **hevc_qsv (default mode), target A, NV12, tops out at 66-67 fps aggregate at every N.**
  - N=1 keeps up; N=4 keeps up 0/4 in every rep, with 98.4-98.6 % of frames late.
  - Per-stream fps at N=16: 4.
  - File: `matched_concurrent_hevc_qsv_420_1080p_nv12_thread_20261110T051629Z.json`.
- measured: hevc_qsv 4:2:2 from YUY2 behaves the same, 64.0-64.8 fps aggregate (`matched_concurrent_hevc_qsv_422_1080p_yuy2_thread_20261110T065430Z.json`).
- measured: hevc_qsv from mjpeg_qsv decode: 63.5-66.8 fps aggregate (66.3-66.6 at N ≥ 8); N=1 paced keeps up with 6-7 late frames, N ≥ 4 does not (`matched_concurrent_hevc_qsv_420_1080p_mjpeg_qsv_thread_20261110T083946Z.json`).
- measured: hevc_qsv at 720p, target A: 4 streams keep up and 8 do not. The aggregate is 133.5-134.6 fps at N ≥ 4 (122-124 at N=1) (`matched_concurrent_hevc_qsv_420_720p_nv12_thread_20261110T090841Z.json`).
- measured: mjpeg_qsv 4:2:0, target A, NV12. 16 of 16 keep up at 1.05 (1.03-1.06) cores, 0 late frames at N=16. At N=1 every rep kept up but had 13-26 late frames (2.9-5.8 %). Unpaced aggregate 700 (695-705) fps at N=16 (`matched_concurrent_mjpeg_qsv_420_1080p_nv12_thread_20261110T052313Z.json`).
- measured: mjpeg_qsv 4:2:2, target A, YUY2. 16 of 16 keep up with 0 late frames at 0.92 (0.86-0.97) cores. Unpaced aggregate 934 (932-936) fps (`matched_concurrent_mjpeg_qsv_422_1080p_yuy2_thread_20261110T064127Z.json`).
- measured: nvJPEG 4:2:0, target A, NV12 via swscale RGB, thread workers. 8 keep up at 2.56 cores (0, 73 and 66 late frames, ≤ 2.0 %). At N=16 only 1, 2 and 3 of 16 keep up in the three reps, with 73-87 % of frames late (median 83.6 %). Unpaced aggregate 475 (472-477) fps at 4.87 cores at N=16 (`matched_concurrent_nvjpeg_420_1080p_nv12_thread_20261110T052842Z.json`).
- measured: nvJPEG 4:2:2, target A, YUY2, thread workers. 16 of 16 keep up at 4.68 (4.63-4.74) cores, with 5.3 % and 13.3 % of frames late in the two reps (383 and 955 of 7,200) (`matched_concurrent_nvjpeg_422_1080p_yuy2_thread_20261110T063635Z.json`).
- Method note: all nvJPEG scaling runs used thread workers in one process. The script notes that GIL-holding work shows up as flat scaling (`bench_matched_concurrent.py:10-11`). inferred: the limit is host conversion and/or the GIL; process-mode nvJPEG was NOT TESTED.
- measured, recorder pipelines from camera MJPEG, target A, 1080p30:
  - CPU decode → h264_nvenc: 12 keep up (N=16 opens 12) with 0 late frames at 4.06 (4.01-4.10) cores (`matched_concurrent_h264_nvenc_420_1080p_mjpeg_cpu_thread_20261110T081938Z.json`);
  - CPU decode → hevc_nvenc: 12 at 3.90 (3.77-4.03) cores, 0 late (`..._hevc_nvenc_420_1080p_mjpeg_cpu_thread_20261110T082302Z.json`);
  - mjpeg_qsv decode → h264_qsv: 16 of 16 at 4.33 (4.30-4.35) cores, 0 late frames at N=16. At smaller N every rep kept up but had late frames: 5/5 at N=1 (1.1 %), 43/45 at N=4 (2.4-2.5 %), 153/113 at N=8 (3.1-4.3 %) (`..._h264_qsv_420_1080p_mjpeg_qsv_thread_20261110T082702Z.json`).
- measured, 720p30 at target A, all from NV12 (items 49-54; `results/intra_compare/BENCH.md` §4.4; files `matched_concurrent_*_720p_nv12_thread_*.json`):
  - h264_nvenc and hevc_nvenc keep up with 12 (N=16 opens 12), 0 late;
  - h264_qsv keeps up with 16, aggregate 1,572-1,578 fps;
  - mjpeg_qsv keeps up with 16 (one N=1 rep had 25 late frames);
  - nvJPEG keeps up with 16 (one N=16 rep had 136 of 7,200 late, 1.9 %).
- measured: the scaling items' unpaced N=1 fps is up to 40 % below the single-stream fps for the same path: nvjpeg_420 192 vs 323, mjpeg_qsv_422 317-324 vs 481 †, mjpeg_qsv_420 405-407 vs 602 (scaling files above vs item 1). The two methods are not interchangeable, so no scaling efficiency is computed across them.

### 2.9 Other quiet-run GPU results (pointers; owned by other topics)

- measured, G4: h264_nvenc lossless NV12 1080p runs at 516 (515-521) fps and 0.045 cores per 30 fps stream, 593.6 KB/frame. hevc_nvenc lossless runs at 302 fps, with software decode at only 29 fps (`results/uncompressed_intra/bench/{h264,hevc}_nvenc_intra_lossless.mkv__nv12_1080p__t1__pyav19.0.2_q2300.json`; `results/uncompressed_intra/BENCH.md` §4.1). Lossless, so not at target A or B.
  - Run flag 9 (`BENCH_RUN_2300_SUMMARY.md` §3): the timed bench has no lossless check. "Lossless" rests on the PyAV 19 functional matrix (`results/uncompressed_intra/functional_matrix_pyav19.0.2.json`; "yes (matrix)" in `uncompressed_intra/BENCH.md` §4.1), which covers 1080p only; the 720p rows say "1080p only checked".
  - Encoder open is inside the timed window: 3.6-22.7 % of NVENC wall time (same flag).
- measured, functional only, draft unverified: the intra_playback FINDINGS reports that 48 PyAV 19.0.2 NVENC/QSV H.264/HEVC intra clips play and scrub frame-exactly in E35, E45 and Chrome 156. The clips are at about 55 dB Y-PSNR, not target A or B (`results/intra_playback/FINDINGS.md` lines 5, 20).
  - The quiet run flagged open issues for that topic: 914 per-stream WebCodecs scrub errors hidden in 5 E35 configs, GPU-process memory growth to 9-38 GB in all 16 WebCodecs scrub configs, and stalled tiles in 19 of 20 N=8 `<video>` sync configs (`BENCH_RUN_2300_SUMMARY.md` §3 flags 5-6).

### 2.10 Encoder settings needed for matched intra quality

- measured: with FFmpeg's default `i_qfactor`, h264_nvenc `constqp qp=25` coded intra frames at `stats_q_over_118` 19 and 50,990 B. With `i_qfactor=1, i_qoffset=0` it coded them at 24 and 33,081 B (`results/intra_compare/knob_check.json` → `iqfactor`).
  - hevc_nvenc and h264_qsv shift the same way (19/20 → 24/25).
- code: the mechanism is in `nvenc.c:835-836`, `qsvenc.c:922-929` and `options_table.h:151` @ n9.0.2 (excerpts in `results/intra_compare/ffmpeg_n9.0.2_knob_excerpts.txt`; cited by `results/intra_compare/FINDINGS.md` line 62).
- measured: every H.264/HEVC entry in `matched_settings.json` sets `i_qfactor=1, i_qoffset=0` (entries listed in 2.8).

### 2.11 What the post-bench revision changed (before verification)

| item | before | after | evidence |
|---|---|---|---|
| mjpeg_qsv encoder chroma | "yes (4:2:0 out)"; "4:2:2 output (e.g. from YUY2) not tested" | refuted: NV12 in → yuvj420p, YUY2 in → yuvj422p (Windows, RPL-S). The 4:2:0 claim held only for NV12 input | `intra_compare/raw/mjpeg_qsv_42{0,2}__*.json` |
| QSV session limit | "NOT TESTED" | h264_qsv and mjpeg_qsv (4:2:0 and 4:2:2) open 32/32; hevc_qsv opens 16/16 (no probe) | limit probes in 2.4 |
| NVENC limit | functional, busy machine, h264 only | quiet machine, h264 and hevc: 12 (one process); N=16 rows are 12 streams | 2.4 |
| QSV YUY2 / 4:2:2 output | "NOT TESTED" | mjpeg_qsv 4:2:2 and hevc_qsv 4:2:2 (Rext, yuv422p) from yuyv422 measured; 10-bit still untested | 2.7, 2.8 |
| PyAV QSV files in Chromium | "NOT TESTED" | pointer to the intra_playback draft (about 55 dB, functional only) | 2.9 |
| §5 "Pending tonight's bench" | 13 pending rows | answered by intra_compare / python_integration items, or dropped by the queue with a reason | 6.1 |
| nvJPEG q90 vs OpenCV q90 | used as the quality caveat | kept as background; matched-quality rows (2.7) supersede it | 2.7 |
| I3 QSV upload cost | "pending" | total host CPU per frame measured (upload not separated) | 2.8 |

The verifier-driven changes are listed in the Verification section.

### 2.12 Vendor support, from primary sources (cited by 3.4)

- source (re-fetched 2026-11-10): NVIDIA support matrix (URL in 2.4):
  - RTX 3070 / Ampere: AV1 4:2:0 encode "NO"; H.264 4:2:2 and HEVC 4:2:2 encode "NO".
  - RTX 2080 / Turing: AV1 "NO".
  - RTX 4070 / Ada: AV1 "YES".
  - RTX 5070 / Blackwell: AV1 "YES" and 4:2:2 "YES".
  - The matrix has no VP9 encode column.
- source (re-fetched 2026-11-10): Intel media-driver README @ intel-media-26.3.5, lines 79-82, groups KBLx (KBL, CFL, WHL, CML, AML), ICL, JSL/EHL and TGLx (TGL, RKL, ADL-S/P/N, RPL-S/P) (https://github.com/intel/media-driver/blob/intel-media-26.3.5/README.md).
- source (re-fetched 2026-11-10): `docs/media_features.md` lines 59-76 (https://github.com/intel/media-driver/blob/intel-media-26.3.5/docs/media_features.md):
  - TGLx and ICL: AVC, JPEG, HEVC and VP9 8-bit encode; no AV1.
  - KBLx: AVC and JPEG only.
  - DG2, MTLx, LNL, BMG, PTL and NVL: AV1 8-bit.
  - BMG and LNL: the VP9 cell is blank.
  - These are Linux docs. On Windows only RPL-S was measured.
- source (Win, accessed 2026-11-10; GF07 §1, excerpts in `results/hw_accel_target/gapfill/GF07_sources/04-07_*.md`): the Intel RPL, MTL and ARL-S/HX datasheets (edc.intel.com IDs 743844, 792044, 832586; URLs in GF07 §1) list JPEG encode: "JPEG | Baseline | — | 16Kx16K" (RPL); "JPEG |  |  | 16Kx16K" (MTL, ARL-S).
  - Their exposure APIs: "Direct3D12 Video API", "Intel®one VPL", "MFT (Media Foundation Transform) filters [Only for AVC/HEVC/JPEG/AV1 Encoder]" (MTL, ARL-S); "Intel® Media SDK" and "MFT (Media Foundation Transform) filters" (RPL).
  - The Lunar Lake datasheet (ID 829568) has the same JPEG row, but the page is labelled "Confidential" (GF07 S7). It also says "Xe2 implements a low-power low-latency fixed function encoder which supports AVC, HEVC, and AV1." (no VP9).
- source (Win, accessed 2026-11-10; GF07 S8, excerpt `GF07_sources/08_intel_kb_000098345_arc_video_codecs_windows.md`): Intel KB 000098345 (https://www.intel.com/content/www/us/en/support/articles/000098345/graphics.html; "Operating System Windows® 10*, Windows 11*").
  - Its "Encode - supported codecs" row lists "AVC (H.264) HEVC (H.265) VP9 AV1" for all five columns: Arc A-Series, Core Ultra Series 1, Arc B-Series, Core Ultra Series 2 and Core Ultra Series 3.
  - Its "Encode - supported formats" VP9 row gives formats for four columns and "Not Supported" for Arc B-Series.
  - So the KB is internally inconsistent for Arc B VP9 encode: NOT VERIFIED. GF07 recorded only the "Not Supported" cell.
  - Its Series 2 column lists VP9 encode formats, while the LNL datasheet names an AVC/HEVC/AV1 fixed-function encoder. Which Series 2 parts the KB column covers is not stated (GF07 lines 101-102).
  - It has no JPEG row.
- source (accessed 2026-11-10; GF03 R06, R09): nvJPEG documents hardware (fixed-function) JPEG encode only for Jetson Thor.
  - CUDA 12.9.1 nvJPEG docs: "Hardware accelerated JPEG encode is available on Jetson Thor (Blackwell), running Linux ARM64." (https://docs.nvidia.com/cuda/archive/12.9.1/nvjpeg/index.html).
  - CUDA 12.9.1 release notes: "Added hardware-accelerated JPEG encoding support for NVIDIA Jetson Thor hardware (Blackwell SM 10.1 architecture)." (https://docs.nvidia.com/cuda/archive/12.9.1/cuda-toolkit-release-notes/index.html).
  - Neither source says anything about GeForce silicon. inferred: on GeForce, nvJPEG encode is the CUDA backend.
- measured (static, GF03 §4; `results/licensing/gapfill/GF03_wheel_arch_facts.json` → `fatbin`, parser `scripts/licensing/gapfill/GF03_fatbin_archs.py`, not cross-checked with cuobjdump): `nvjpeg64_12.dll` in the 12.4.0.76 wheel carries SASS for sm_75, 86, 89 and 120, among others. Functional nvJPEG encode was run only on sm_86 (RTX 3070).
- source (saved HTML, not re-fetched): the AMD RX 7600 page says "AV1 Encode Yes"; the RX 6600 page has only "AV1 Decode Yes". The Apple M5/M2 pages list hardware-accelerated "H.264, HEVC, ProRes, and ProRes RAW" (NOTES.md §7.3-7.4).

## 3. Comparison tables

### 3.1 Hardware encode on Gerald through PyAV 19.0.2 (functional)

Sources: `pyav_functional_19.0.2.md`, `qsv_recheck_19.0.2.md`, `adapter_check*.json`, `verify_method_pool.json`, `verify_method_fmts.json`, quiet-run limit probes (2.4) and the `intra_compare/raw` sweeps (2.7).

| encoder | device | sw frames | HWAccel ctx | intra | in NVENC 12-session pool | sessions opened (quiet run, one process) | accepts yuyv422 (advertised) | output chroma by input | codec class |
|---|---|---|---|---|---|---|---|---|---|
| h264_nvenc / hevc_nvenc | RTX 3070 | yes | yes (cuda)¹ | yes (`gop_size=0` only) | yes | 12 of 32 | no | NV12 → 4:2:0 | H.264/HEVC (G7: avoid) |
| h264_d3d12va / hevc_d3d12va | RTX 3070 (default device) | no | yes (d3d12va), MP4 only, `max_b_frames=0` | yes | yes (h264 tested) | not probed | not checked | - | H.264/HEVC |
| h264_mf / hevc_mf | NVIDIA MFT | yes | n/a | yes | yes (h264 tested) | not probed | not checked | - | H.264/HEVC |
| h264_qsv | UHD 770 | yes | no (frame pool) | yes (`gop_size=1`) | no | 32 of 32 | no (nv12 only) | NV12 → 4:2:0 | H.264 |
| hevc_qsv | UHD 770 | yes | no | yes | not tested | 16 of 16 (no probe) | yes | NV12 → 4:2:0 Main; YUY2 → 4:2:2 Rext | HEVC |
| **mjpeg_qsv** | UHD 770 | yes | no | yes | not tested | 32 of 32 (4:2:0 and 4:2:2) | yes | **NV12 → yuvj420p; YUY2 → yuvj422p** | JPEG (licence: licensing topic) |
| **vp9_qsv** | UHD 770 | yes | no | yes | not tested | not tested | not checked | NV12 → 4:2:0 | VP9 (outside the hardware target; no NVENC VP9) |
| av1_nvenc / av1_d3d12va / av1_mf / av1_qsv | - | fail | fail | - | - | - | - | - | AV1: no hardware on Gerald |
| *_vulkan, ffv1_vulkan, prores_ks_vulkan | - | not in wheel | not in wheel | - | - | - | - | - | - |

¹ The encoder opens with a device context, but the frames are still uploaded from host memory. The packets are identical to the software-frame mode (`revise_nvenc_packet_hashes.txt`).

### 3.2 Quiet-run intra throughput, 1080p, target A

Sources: 2.7 and 2.8. Single-stream fps is from item 1 (one thread, unpaced); † = ran after the libx265 affinity widening, P-core-only not shown. All scaling columns are P-core-only (affinity 0-15 before and after). Single-stream fps and scaling aggregates come from different methods (2.8, last bullet) and should not be combined into an efficiency figure. "max N" = largest tested N at which every stream kept up in every rep. "Ceiling" = unpaced aggregate at the largest N ÷ 30 (inferred, arithmetic; not tested as a paced run).

| path · source | single-stream fps | × jt (same chroma) | × jt422 | max N at 1080p30 | late frames at max N | CPU cores at max N, paced | unpaced aggregate fps at max N | sessions opened (probe) | ceiling, 1080p30 streams (inferred) |
|---|---|---|---|---|---|---|---|---|---|
| h264_nvenc · NV12 | 540 | 0.62 | 0.55 | 12 | 0 | 0.61 | 542 | 12 of 32 | 18 by throughput; 12 by sessions |
| hevc_nvenc · NV12 | 390 | 0.53 | 0.47 | 12 | 0 | 0.65 | 390 | 12 of 32 | 13 by throughput; 12 by sessions |
| h264_qsv · NV12 | 585 | 0.67 | 0.59 | 16 (max tested) | 0 | 1.25 | 679 | 32 of 32 | about 22 |
| hevc_qsv · NV12 (default mode) | 65 | 0.46 | 0.41 | 1 | 0 | 0.15 | 66 | 16 of 16 (no probe) | about 2 (N=4 fails) |
| hevc_qsv_422 · YUY2 | 64 † | 0.54 | 0.54 | 1 | 0 | 0.15 | 64 | 16 of 16 (no probe) | about 2 (N=4 fails) |
| mjpeg_qsv_420 · NV12 | 602 | 1.08 | 0.96 | 16 (max tested) | 0 | 1.05 | 700 | 32 of 32 | about 23 |
| mjpeg_qsv_422 · YUY2 | 481 † | 1.07 | 1.07 | 16 (max tested) | 0 | 0.92 | 934 | 32 of 32 | about 31 |
| nvjpeg_420 · NV12 (swscale RGB, threads) | 323 | 0.88 | 0.79 | 8 | ≤ 2.0 % | 2.56 | 456 | n/a | about 15 (N=16 fails) |
| nvjpeg_422 · YUY2 (swscale RGB, threads) | 343 † | 0.88 | 0.88 | 16 (max tested) | 5.3-13.3 % | 4.68 | 567 | n/a | about 18 |
| camera MJPEG CPU decode → h264_nvenc | 228 † | 0.89² | 0.79² | 12 | 0 | 4.06 | 596 | 12 | 19 by throughput; 12 by sessions |
| camera MJPEG QSV decode → h264_qsv | 554 † | 1.14³ | 1.02² | 16 (max tested) | 0 (1.1-4.3 % at N=1-8) | 4.33 | 486 | 16 of 16 | about 16 |

² Ratio against libjpeg-turbo re-encoding the same CPU-decoded camera frames (`mjpeg_cpu` source), not against passthrough (`results/intra_compare/BENCH.md` §3 column definition).
³ Against libjpeg-turbo 4:2:0 on the `mjpeg_qsv` source (item 1 has no jt422 cell for that source).

Target B, 1080p from NV12, single stream (all P-core-only): h264_nvenc 635, hevc_nvenc 425, h264_qsv 691, hevc_qsv 87 and mjpeg_qsv 618 fps (2.8, 2.7).

### 3.3 Decode of camera 4:2:2 MJPEG

| decoder | result | output | evidence |
|---|---|---|---|
| mjpeg (CPU) | ok | yuvj422p | `qsv_recheck_19.0.2.md` |
| mjpeg_cuvid (PyAV 19) | fails on 4:2:2; 4:2:0 control ok | nv12 (4:2:0 control) | `verify_method_cuvid.json` |
| mjpeg + HWAccel cuda (PyAV 19) | fails on 4:2:2; 4:2:0 control ok | nv12 (4:2:0 control) | same |
| mjpeg_qsv decoder (PyAV 19) | ok, 5/5; luma within ±1 of CPU | nv12 (chroma reduced to 4:2:0), mis-tagged limited range | `qsv_recheck_19.0.2.md`, `verify_method_checks.json` |
| nvImageCodec nvjpeg_cuda_decoder | ok (hybrid CPU+GPU, inferred); camera sets at 1080p: 2.08-2.27 ms/frame on GPU, 3.45-3.64 ms to host (generic set 1.92 / 3.37) | RGB device buffer | `nvimgcodec_jpeg.json`, `python_integration/bench/nvjpeg_decode_quiet1_2300.json` |

### 3.4 Hardware encode of codecs other than H.264/HEVC, by platform

Rows come from the sources in section 2.12 unless marked measured. Every measured cell is from one UHD 770 (RPL-S) or one RTX 3070 on Windows, except "measured static" cells (wheel binary inspection, no device).

| platform | AV1 HW enc | VP9 HW enc | JPEG HW enc | in PyPI PyAV wheel |
|---|---|---|---|---|
| NVIDIA Turing/Ampere (RTX 2000/3000) | no (source) | inferred no (no VP9 column in the matrix) | CUDA nvJPEG: measured on Ampere (not PyAV). Turing: sm_75 SASS present in `nvjpeg64_12.dll` (measured static, GF03), not run | only NVENC h264/hevc usable |
| NVIDIA Ada/Blackwell | yes (source) | inferred no | CUDA nvJPEG: binaries present (sm_89/sm_120 SASS in `nvjpeg64_12.dll`, measured static, GF03), not run. nvJPEG documents hardware JPEG encode only for Jetson Thor SM 10.1 (source, GF03 R06, R09); on GeForce nvJPEG encode is the CUDA backend (inferred) | av1_nvenc compiled in (Win, Linux x64) |
| Intel TGLx (TGL, RKL, ADL, RPL) and ICL | no (source; measured on RPL-S) | yes (source; measured on RPL-S) | yes (source; measured mjpeg_qsv 4:2:0 and 4:2:2 on RPL-S only) | vp9_qsv: Win and Linux x64; mjpeg_qsv encoder: Win (measured), Linux x64 NOT VERIFIED |
| Intel KBLx (incl. CML, 10th gen) | no (source) | no (source) | yes (source; NOT VERIFIED on hardware) | - |
| Intel Arc / MTL / ARL / LNL / BMG | yes (source) | Linux: yes, except LNL/BMG (source, media-driver). Windows: Arc B NOT VERIFIED (KB 000098345 is internally inconsistent: codecs row lists VP9, formats row "Not Supported"); LNL datasheet names an AVC/HEVC/AV1 fixed-function encoder, while the KB Series 2 column lists VP9 and does not state which Series 2 parts it covers (2.12, GF07) | Linux: yes (media-driver). Windows: MTL and ARL-S/HX yes (source, datasheets); LNL only per a datasheet labelled "Confidential"; Arc B NOT VERIFIED. Arc A: yes per the oneVPL doc (source, OS-agnostic; Windows inferred). None tested | av1_qsv compiled in |
| AMD RDNA3 | yes (source, RX 7600) | NOT VERIFIED | NOT VERIFIED | av1_amf compiled in |
| AMD RDNA2 / Zen APUs | no AV1 encode row on the RX 6600 page | NOT VERIFIED | NOT VERIFIED | - |
| Apple silicon | no (source; no ffmpeg encoder, code) | no (no ffmpeg encoder, code) | NOT VERIFIED | VideoToolbox h264/hevc/prores only |
| CPU with no iGPU / no supported GPU | software only | software only | software only | libsvtav1 (encoder-only name); libvpx-vp9 encoder NOT VERIFIED |

### 3.5 Hardware encoders in the PyPI PyAV wheels

Method: static string search of the bundled libavcodec, with sha256 checks (`wheel_hw_codecs.md`; `scripts/gpu_encode/wheel_hw_codecs.py:59-60`). The long-name matcher misses some encoders: on win_amd64, h264/hevc/mjpeg_qsv and h264/hevc_mf have no long name, yet all five work. So a missing long name does not prove the encoder is absent.

| wheel | encoder proven (long name or functional) | short name only (encoder NOT VERIFIED) |
|---|---|---|
| win_amd64 | NVENC h264/hevc/av1; QSV av1/vp9; AMF av1; D3D12VA h264/hevc/av1; MF av1; plus functional h264/hevc/mjpeg_qsv and h264/hevc_mf; h264/hevc_amf present (static PyAV query, GF06; function NOT VERIFIED) | vp9_d3d12va, vp9_amf |
| win_arm64 | D3D12VA h264/hevc/av1; MF av1 | h264/hevc_mf, vp9_d3d12va |
| manylinux_2_28_x86_64 | NVENC h264/hevc/av1; QSV av1/vp9; AMF av1; V4L2 m2m h264 | h264/hevc/mjpeg/vp8_qsv, h264/hevc/vp9_amf, hevc/vp8/vp9_v4l2m2m |
| manylinux_2_28_aarch64 | V4L2 m2m h264 | hevc/vp8/vp9_v4l2m2m |
| macOS arm64 / x86_64 | VideoToolbox H.264, H.265, ProRes | av1/vp9_videotoolbox (decoders) |

- measured (static, PyAV 19.0.2 on Gerald): `av.codec.Codec("h264_amf"/"hevc_amf", "w")` resolves, with long names "AMD AMF H.264 Encoder" / "AMD AMF HEVC encoder", and the private options `rc`, `qp_i`, `qp_p` and `forced_idr` are listed (`results/hw_accel_target/gapfill/GF06_pyav_options.json`). The encoders are present in the wheel; functional encode NOT VERIFIED (no AMD hardware).
  - inferred: h264/hevc_amf move from "short name only (encoder NOT VERIFIED)" to "present (static), function NOT VERIFIED" (table updated).
- measured: no wheel contains VAAPI or Vulkan names (`wheel_hw_codecs.md`).
- source: pyav-ffmpeg `scripts/build-ffmpeg.py` @ 9.0.2-1 has `--enable-nvenc --enable-nvdec` (line 189), `--enable-amf` (192), `--enable-libvpl` (195) and `--enable-videotoolbox` (200), and no `--enable-vulkan` or VAAPI flag (re-fetched 2026-11-10; https://github.com/PyAV-Org/pyav-ffmpeg/blob/9.0.2-1/scripts/build-ffmpeg.py).
- code: ffmpeg n9.0.2 `libavcodec/allcodecs.c:875,890,907` declares only the h264, hevc and prores VideoToolbox encoders (NOTES.md §7.4; saved copy, not re-fetched).

## 4. Implications for the plan

- I1 (from 2.2, 2.7, 3.4): through PyPI PyAV on Gerald, **vp9_qsv is the only working hardware inter-frame encoder for a codec other than H.264/HEVC, and mjpeg_qsv is the only intra-only one** (measured). Both run only on the Intel iGPU.
  - mjpeg_qsv's output chroma follows its input: NV12 → 4:2:0, YUY2 → 4:2:2 (measured).
  - VP9 is outside the hardware target (no RTX 3000 encode, source) and was not timed.
- I2 (from 2.7, 2.8, 2.12): Ampere has no NVENC encoder for any codec other than H.264/HEVC (source). On RTX 3000 the only GPU path for JPEG is CUDA nvJPEG through nvImageCodec, outside PyAV (measured).
  - measured, target A, thread workers: nvJPEG from YUY2 keeps up with 16 × 1080p30 at 4.68 cores, with 5.3-13.3 % of frames late; from NV12 it keeps up with 8 (≤ 2.0 % late), not 16.
  - measured, timed swscale-RGB path: files are 0.88 × libjpeg-turbo at the same chroma, with a 0.46-0.48 dB PSNR-Y gap in the 4-frame QC.
  - measured, sweep with exact RGB input: target A is reached with 1.44 dB less PSNR-Y than libjpeg-turbo 4:2:2.
  - inferred: "JPEG, hardware-accelerated on RTX 3000" is achievable for raw (YUY2/NV12) inputs, but at several host cores, not near-zero CPU as with NVENC (measured 0.61 cores for 12 streams). Process-mode nvJPEG, which might scale better, is NOT TESTED.
- I3 (from 2.4, 2.8): **one GeForce GPU cannot give each camera of a 16-camera rig its own NVENC session.** The cap is 12 (measured on Gerald, driver 610.88, quiet machine, one process, H.264 and HEVC; matrix value 12 for most GeForce rows, re-fetched 2026-11-10), and D3D12/MF share the pool (measured with a control).
  - Within the cap, h264_nvenc and hevc_nvenc sustain 12 × 1080p30 at target A with 0 late frames (measured).
  - inferred, arithmetic: hevc_nvenc's 390 fps total at preset p4 is below the 480 fps that 16 × 1080p30 needs, even without the cap.
- I4 (from 2.4, 2.8): **QSV is outside the NVENC pool and opened 32 sessions of h264_qsv and mjpeg_qsv** (measured, open probe). h264_qsv and mjpeg_qsv each sustain 16 × 1080p30 at target A at 0.92-1.25 cores with 0 late frames (measured).
  - inferred, arithmetic: unpaced aggregates suggest throughput ceilings of about 22 (h264_qsv), 23 (mjpeg_qsv 4:2:0) and 31 (mjpeg_qsv 4:2:2) × 1080p30; not tested as paced runs.
  - inferred: an Intel iGPU can carry the streams beyond NVENC's 12. Running 12 NVENC plus 4 QSV streams at the same time was not tested.
- I5 (from 2.2, 2.8): **hevc_qsv in its default mode on the UHD 770 is not viable for multi-camera intra recording at these settings** (measured): 66-67 fps in total at 1080p (one 1080p30 stream) and about 134 fps at 720p (four streams), at target A.
  - measured: in that mode it loads the iGPU 3D engine (81-91 %), not the video engine. `low_power=1` and `preset=veryfast` open and produce intra output (functional), but their speed is NOT TESTED. Do not rule hevc_qsv out until low-power mode is timed.
- I6 (from 2.2, 2.5, 2.10): intra settings must be explicit per encoder (measured):
  - NVENC: `gop_size=0` (1 is rejected).
  - QSV: `gop_size=1`.
  - AMF (not tested; no AMD hardware): `gop_size=1`, not 0. AMF maps 0 to "IDR off" (H.264) or "first IDR only" (HEVC) [code `amfenc_h264.c:574-576`, `amfenc_hevc.c:298-301`; source AMF SDK v1.5.3 H264 doc:1417, HEVC doc:1266, GF06]. Constant QP via `rc=cqp, qp_i=N` [code `amfenc_h264.c:377-378`, `amfenc_hevc.c:523-524`].
  - VideoToolbox (not tested; no Apple hardware): `gop_size=1` → MaxKeyFrameInterval 1 [code `videotoolboxenc.c:1379-1395`]; the default gop_size is 12 [code `options_table.h:96`]. Quality only via `global_quality` → VT Quality 0-1 [code `videotoolboxenc.c:1250-1261`]. No constant QP in FFmpeg n9.0.2 [code: BaseFrameQP unused, GF06].
  - D3D12: `HWAccel('d3d12va')`, `max_b_frames=0`, MP4 only.
  - NVENC and QSV H.264/HEVC: `i_qfactor=1, i_qoffset=0` (AMF and VideoToolbox never read these fields [code, GF06], so the setting is harmless there but has no effect). Otherwise intra frames are coded at a lower QP than requested and are much larger (measured: 50,990 vs 33,081 B at qp 25, h264_nvenc).
- I7 (from 2.2, 2.7, 2.8): for YUY2 (4:2:2) cameras:
  - measured, static: hevc_qsv and mjpeg_qsv take `yuyv422` directly. h264_qsv takes only NV12, and NVENC (h264/hevc) does not take packed YUY2, so both need a conversion. NV12 is the only conversion the bench timed; it drops chroma to 4:2:0.
  - measured, P-core-only: the YUY2 → NV12 swscale step raised h264_nvenc from 0.60-0.64 to 2.41-2.64 cores at 12 × 1080p30 (2.8). Single-stream † values: 1.40 → 6.67 ms/frame (h264_nvenc), 2.04 → 8.44 (h264_qsv).
  - measured: mjpeg_qsv writes 4:2:2 JPEG from YUY2 at target A at 1.8-2.0 ms CPU/frame at 16 paced streams (P-core-only); single-stream † values are 0.66 (720p) and 1.58 (1080p) ms/frame.
  - source: Ampere has no H.264/HEVC 4:2:2 encode (2.12). NVENC lists `nv16` but 4:2:2 output was not tried.
- I8 (from 2.6, 2.7, 2.8): re-encoding camera MJPEG costs about 4 host cores for 12-16 × 1080p30, whichever route the decode takes (measured: CPU decode → h264_nvenc 4.06 cores for 12; mjpeg_qsv decode → h264_qsv 4.33 cores for 16).
  - G1 passthrough avoids this.
  - measured: nvJPEG fed CPU-decoded camera MJPEG through swscale rgb24 misses target A and target B. That tested pipeline is not a re-encode route; an exact-RGB or YUV-input route is NOT TESTED (and the mjpeg_qsv-decode row passed its QC, cause not examined).
  - measured with a control: NVDEC cannot decode the cameras' 4:2:2 MJPEG from PyAV.
- I9 (from 2.7, 3.2): mjpeg_qsv at target A, 1080p, writes files about 7-8 % larger than libjpeg-turbo at the same chroma (measured: 1.08 × jt420 from NV12, 1.07 × jt422 from YUY2). It gives G7-preferred JPEG with hardware encode; measured on the UHD 770 (RPL-S) with one Windows driver only. Other Intel generations (TGL/ICL on, and KBLx, per the Linux docs, source) are NOT VERIFIED on hardware.
- I10 (from 2.2, 2.5): PyPI PyAV cannot reach `ffv1_vulkan` (byte-exact lossless) or `prores_ks_vulkan` (measured). Using them needs a CLI subprocess or a custom build with `--enable-vulkan` (standard FFmpeg vs custom-build trade-off).
- I11 (from 2.2), inferred: on Gerald D3D12 and MF chose the NVIDIA device. The default adapter is machine-dependent, so the recorder should allow explicit device selection.
- I12 (from 2.3): PyAV 19.0.2 brings no new hardware encoder over 18.0.0 (measured).

## 5. Run flags and caveats that apply to this topic

1. **No gpu_encode-owned bench.** The timed numbers come from intra_compare items 1-11, 31-34, 41-45 and 49-55, python_integration item 40 and uncompressed_intra item 35 of run `20261109T230007` (`results/BENCH_RUN_2300_SUMMARY.md`). The queue's mapping is in `results/BENCH_QUEUE_2300.md` lines 225-230.
2. **P-cores.** Items were pinned to CPUs 0-15; every intra_compare JSON records `system_before.process_cpu_affinity` 0-15 (measured).
3. **libx265 widened affinity in items 1-3.**
   - `system_after.process_cpu_affinity` is 0-27 in all three `matched_stream_*` files (measured).
   - In the `runs` order, all NV12 cells (including the GPU ones) ran before the first libx265 cell, so they are P-core-only (measured). This includes every target B GPU cell cited here.
   - Every YUY2, MJPEG (`mjpeg_cpu`, `mjpeg_qsv`) and RGB cell ran after it and may have had all 28 CPUs; that cannot be told from the files. These are marked † in 2.7, 2.8 and 3.2: mjpeg_qsv_422 481 / 894 fps, nvjpeg_422 343, nvJPEG RGB 1,126, hevc_qsv_422 64, MJPEG → h264_nvenc 228, mjpeg_qsv decode → h264_qsv 554, and the YUY2 CPU-per-frame values.
   - That libx265 set the affinity is inferred, not tested.
   - The scaling items kept 0-15 before and after (measured, every `matched_concurrent_*` file; `results/intra_compare/BENCH.md` caveat 1).
4. **NVENC N=16 rows are 12 streams** (2.4).
5. **nvJPEG fed CPU-decoded camera MJPEG misses target A** (SSIM-Y 0.9954) and target B (43.14 dB) (2.7).
6. **Input work is inside the timed loop.** That includes swscale for YUY2 → NV12 and → RGB, and the MJPEG decode (code: `scripts/intra_compare/benchpaths.py:199-244`, `Feed.next`; the docstring at lines 7-19 states the decode is in the loop and range mapping for nv12/yuy2 is untimed). The fps and CPU are pipeline numbers, not encoder-only, except the `rgb` nvJPEG rows.
7. **Short cycled inputs** (`results/intra_compare/BENCH.md` caveat 6): YUY2 is 16 frames (8 per camera); MJPEG is 38 frames at 1080p and 240 at 720p. Encoder speed on long real motion is not measured.
8. **QC covers the first 4 frames only**, from a separate untimed encoder. The scaling items have no QC; they reuse the matched settings. The timed benches record no keyframe flags; intra is inferred from identical settings (2.8).
9. **Repeats:** single-stream items have 5, 4 and 3 timed reps. The scaling items have 3 (items 4-10) or 2. Min-max over 2 reps is just the two values. The python_integration nvJPEG decode is one run with per-call percentiles.
10. **CPU metrics:** thread workers report process CPU, driver threads included. Unpaced N=1 GPU utilisation is unreliable, because those runs last ≤ 1 s, which is at or below the counter period (`results/intra_compare/BENCH.md` caveat 8). Single-stream fps and scaling N=1 fps differ by up to 40 % (2.8).
11. **"keeps up" allows late frames.** Late shares are given in 2.8 and 3.2 wherever non-zero; they vary between reps (e.g. nvjpeg_422 N=16: 5.3 % vs 13.3 %).
12. **nvJPEG scaling used threads only.** GIL effects cannot be separated from host-conversion cost (`bench_matched_concurrent.py:10-11`); process mode NOT TESTED.
13. **Write-path cost is excluded.** Every gpu_encode timing discards packets and writes no files (`bench_matched_stream.py:12`; `bench_matched_concurrent.py:62,75`). Muxing, disk writes and Defender's scanning of written output are not in these numbers. Defender real-time scanning was on and not changed; write_throughput measured its cost: 26.8 Defender CPU-s per 30 s cell for folder-of-files against 1.2-1.5 s for container writers (`BENCH_RUN_2300_SUMMARY.md` line 102; `write_throughput/bench/focus16_av19/`). One container file per camera, the normal output of these encoders, is in the low group. The MsMpEng CPU during items 4 and 7 (9.16 and 48.86 CPU-s, `results/intra_compare/BENCH.md` §1) is background CPU, not write-path cost.
14. **Per-write latencies** in the quiet run are higher than in the contaminated daytime run (`BENCH_RUN_2300_SUMMARY.md` §3), so earlier daytime numbers are not lower bounds everywhere. This topic cites no per-write latency.
15. The GOP-only functional results (hevc_qsv low-delay B, gpb, the gop15 rows) are background (requirement 8).

## 6. Not tested / limits / NOT VERIFIED

### 6.1 Status of the earlier "pending bench" items

| earlier id | question | status | where |
|---|---|---|---|
| B1a, B1b | CLI single-stream fps; CPU reference encoders | dropped: ffmpeg CLI (req. 5), GOP legs (req. 8); replaced by intra_compare items 1-3 | `BENCH_QUEUE_2300.md` line 225; 2.7, 2.8 |
| B2a, B2b, B2d, B2e | NVENC 1-16 stream scaling, 1080p and 720p | answered (PyAV 19.0.2, target A) | items 4, 5, 49, 50; 2.8 |
| B2c | d3d12va scaling | dropped: same RTX 3070 silicon, no MKV | `BENCH_QUEUE_2300.md` lines 221, 227 |
| B3a, B3b | numpy-to-frame / upload / encode-call micro-costs | dropped (B3a PyAV 18; B3b covered by in-loop input work). The upload share is not separated | line 228 |
| B4 | nvJPEG encode/decode throughput and CPU share | encode answered at matched quality (2.7, 2.8; threads only). Decode wall time answered (2.6). **Decode host-CPU share NOT MEASURED** (no CPU fields) | items 1-3, 9, 32, 54, 40 |
| B5 | NVENC session limit, quiet machine | answered: 12, h264 and hevc, one process | 2.4 |
| B-QSV | QSV per-stream fps, scaling, alongside NVENC | answered for h264/hevc/mjpeg_qsv (2.8). **vp9_qsv timing dropped** (outside the hardware target). **QSV alongside 12 held NVENC sessions under load: NOT TESTED** | items 6-8, 33-34, 43-44, 51-53 |
| mjpeg_qsv vs nvJPEG vs CPU JPEG for raw input | cost at matched quality | answered at target A and B | 2.7, 3.2 |

### 6.2 Still not tested or NOT VERIFIED

- Only NVIDIA Ampere (RTX 3070, driver 610.88) and the Intel RPL-S iGPU (UHD 770) were tested physically. Every Turing, Ada, Blackwell, other-Intel, AMD and Apple row comes from documents (plus static wheel inspection for nvJPEG binaries, GF03). The Intel rows come from Linux driver docs, plus Intel Windows datasheets and KB 000098345 for some cells (2.12, GF07).
- AV1 hardware encode through PyAV on capable GPUs: NOT TESTED (no hardware).
- NVENC and QSV encoding at the same time (for example 12 + 4 streams): NOT TESTED. Total throughput and CPU in that mix are unknown.
- The NVENC cap across several processes: not measured in the quiet run (all probes in one process); the general cap rests on the NVIDIA matrix (source).
- Any way around the 12-session cap, such as several cameras through one session or one encoder per tile: NOT TESTED.
- hevc_qsv speed with `low_power=1` and/or a faster `preset`: NOT TESTED (functional open only, 2.2). The 66 fps ceiling is for the default mode with no preset set (`matched_settings.json`).
- QSV throughput ceilings beyond 16 paced streams (the "about 22 / 23 / 31" figures in 3.2): inferred from unpaced aggregates, NOT TESTED.
- nvJPEG with process workers: NOT TESTED.
- The hevc_qsv session limit above 16, and the vp9_qsv / mjpeg_qsv behaviour while 12 NVENC sessions are held: NOT TESTED.
- Vulkan Video in the NVENC pool: CLI only, no control.
- 10-bit QSV output: NOT TESTED.
- NVENC with packed YUY2: answered statically (not advertised; 2.2). NVENC `nv16` (4:2:2) input: advertised, not tried (Ampere has no 4:2:2 encode, source).
- Chromium playback of hevc_qsv 4:2:2 (Rext): measured to fail on this RTX 3070 (chromium_codecs C17; `results/chromium_codecs/raw/verify_method_rechecks.json` → `hevc422_probe_and_play.play_file_url`): E35 does not open the one 720p MKV tested (`DEMUXER_ERROR_NO_SUPPORTED_STREAMS`); E45 gives `PIPELINE_ERROR_DECODE`; a 4:2:0 control plays. Chrome 156 playback: NOT VERIFIED. (The earlier pointer "intra_playback FINDINGS line 64" was stale; GF05.)
- Root cause of the `HWAccel('qsv')` frame-pool failure: unknown (one construction tried). The cost of a GPU-resident (no host upload) NVENC or QSV path: NOT TESTED.
- `mjpeg_qsv` decoder chroma accuracy: not compared. mjpeg_qsv encoder chroma accuracy beyond the sweep's `psnr_yuv_422`: not separately reviewed here.
- Why the nvjpeg_420 row fed `mjpeg_qsv`-decoded frames passes its QC while the `mjpeg_cpu` row misses: NOT VERIFIED.
- CLI `mjpeg_cuvid` hang and silent `-hwaccel cuda` fallback: NOT VERIFIED (no saved output).
- D3D12 MKV failure and default-B-frame failure: FFmpeg bug vs driver limit NOT VERIFIED. The D3D12 device-creation failure after a failed encode was seen once.
- `ffv1_vulkan` on AMD, Intel or MoltenVK: NOT VERIFIED.
- nvJPEG:
  - where decode and encode actually run (the hybrid share) is inferred only;
  - host CPU per decode is not measured;
  - a GPU-resident nvJPEG → NVENC path in Python: NOT TESTED;
  - an exact-RGB or YUV-input nvJPEG route for camera MJPEG: NOT TESTED (the YUV/NV12 encode inputs exist in the nvJPEG API, code, 2.7);
  - why nvImageCodec 0.10.0.9 rejects P_YUV and I_YUV input: NOT VERIFIED (neither R19 nor R20 describes the 4:4:4 test case; 2.7);
  - nvJPEG decode to YUY2/NV12 (declared in the measured header, code, `nvjpeg.h:144-146`; nvJPEG 12.9 release note, GF03 R21; 2.6): NOT TESTED;
  - nvJPEG encode on Turing, Ada or Blackwell: binaries present (static), not run (GF03);
  - PyAV wrapping external CUDA pointers: inferred unsupported, NOT TESTED.
- `torchvision.io.encode_jpeg` on CUDA: NOT TESTED. Root cause of nvImageCodec CUDA error 700: unknown.
- `hevc_qsv` strict GPB and whether `gpb` reaches the runtime: NOT VERIFIED (GOP background only).
- The FFmpeg source lines and the AMD and Apple quotes were checked only against saved copies in an old session scratchpad (`C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/gpu_encode/src/`), which may be deleted. The NVIDIA, Intel and pyav-ffmpeg sources re-fetched on 2026-11-10 are in `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step2/ge_src/`.
- Royalty and licence status of VP9, AV1, JPEG, FFV1 and ProRes: not asserted here (licensing topic). Jellyfin per-generation claims belong to hw_accel_target.
- Licence and benchmark-disclosure terms for nvImageCodec/nvJPEG are in licensing GF03 (`results/licensing/gapfill/GF03_nvjpeg_licence_arch.md`).
  - source: the nvImageCodec SLA §2.11 (the nvimgcodec 0.10.0.9 wheel's `LICENSE.txt`, "(v. November 28, 2023)", accessed 2026-11-10; GF03 W10) says: "You may not distribute or disclose to third parties the output of the Software where the output reveals functionality or performance data pertinent to NVIDIA hardware or software products, results of benchmarking, competitive analysis, or regression or performance data relating to the Software or NVIDIA GPUs without the prior written permission from NVIDIA."
  - source: the licence is inconsistent across NVIDIA's channels: the wheel and docs carry the SLA, while PyPI metadata and GitHub v0.10.0 say Apache-2.0 (GF03 §3.1; G01, H01, W01). Which governs the PyPI wheel: NOT VERIFIED.
  - inferred: if the SLA governs, it bears on publishing the nvJPEG encode timings measured with nvImageCodec 0.10.0.9 (2.7, 2.8, 3.2). Not legal advice; Dom to decide.
  - The nvJPEG decode timings (2.6 table, 3.3) used nvImageCodec 0.9.0.20, whose licence GF03 did not inspect (GF03 §7): NOT VERIFIED.
- Intel Windows JPEG encode on Arc B: NOT VERIFIED (no Intel Windows text; GF07). LNL Windows cells rest on a datasheet labelled "Confidential"; whether PLAN.md may cite it is Dom's call (GF07 §3).
- Intel Windows VP9 encode on Arc B: NOT VERIFIED (KB 000098345 contradicts itself; 2.12). Which parts the KB "Core Ultra Series 2" column covers: not stated.
- The functional checks in 2.2-2.6 ran while other agents and Parsec/Sunshine were active (nvidia-smi showed 1 foreign NVENC session at times; `pyav_functional_19.0.2.md`). They have no timing.

## 7. How to reproduce (repo root `C:/Users/Dom/GitHub/freemocap/skellycam`)

Timed items, one at a time on a quiet machine (queue and runner: `results/BENCH_QUEUE_2300.md`, `scripts/bench_runner/run_queue.py --only <ids>`):

```
# single-stream matched quality, target A 1080p (items 2-3: --sizes 720p / --target B, see queue)
uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_compare/bench_matched_stream.py --paths all --sizes 1080p --sources nv12,yuy2,mjpeg_cpu,mjpeg_qsv,rgb --target A --frames 300 --min-seconds 3 --reps 5 --label A_1080p
# scaling + limit probe (same form for hevc_nvenc_420, mjpeg_qsv_420; mjpeg_qsv_422 with --source yuy2 --reps 2)
uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_compare/bench_matched_concurrent.py --path h264_nvenc_420 --size 1080p --source nv12 --workers thread --modes paced,unpaced --streams 1,4,8,16 --reps 3 --limit-probe 32
uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_compare/bench_matched_concurrent.py --path h264_qsv_420 --size 1080p --source nv12 --workers thread --modes paced,unpaced --streams 1,4,8,16 --reps 3 --limit-probe 32
# nvJPEG decode (nvImageCodec 0.9.0.20)
uv run --script research/skellycam_recording/recording_upgrade/scripts/python_integration/bench_nvjpeg_decode.py --tag quiet1_2300
```

Read-only checks of the mjpeg_qsv chroma claim (no timing):

```
python -I -c "import json,glob;[print(f,{p['pix_fmt_fed'] for p in json.load(open(f))['points']},{x for p in json.load(open(f))['points'] for x in p['decoded_pix_fmts']}) for f in sorted(glob.glob('research/skellycam_recording/recording_upgrade/results/intra_compare/raw/mjpeg_qsv_*.json'))]"
```

Functional (PyAV 19.0.2):

```
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/pyav_functional.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/qsv_recheck.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/qsv_recheck2.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/adapter_check.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/adapter_check_hevc.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/verify_method_checks.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/verify_method_pool.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/verify_method_cuvid.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/verify_method_opts.py
# advertised pixel formats (static) and hevc_qsv low_power/preset open check (functional, untimed)
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/verify_method_fmts.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/verify_method_lowpower.py
# NVENC session limit (script docstring is stale; use this command)
uv run --no-project --with av==19.0.2 --with numpy==2.2.6 python research/skellycam_recording/recording_upgrade/scripts/gpu_encode/nvenc_sessions_versioned.py --max 16
# wheel inspection (static)
.venv/Scripts/python.exe -I research/skellycam_recording/recording_upgrade/scripts/gpu_encode/wheel_hw_codecs.py 19.0.2 18.0.0
# GPU JPEG (nvImageCodec 0.10.0.9) and buffer lifetime
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/nvimgcodec_jpeg.py
python research/skellycam_recording/recording_upgrade/scripts/gpu_encode/nvimgcodec_lifetime_run.py
# CLI reference matrix (reference only)
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/gpu_encode/ff_functional.py
# iGPU presence (read-only)
powershell -NoProfile -Command "Get-PnpDevice -Class Display | ft Status,Present,FriendlyName"
```

- Functional media: `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/gpu_encode/`.
- Timed results: `results/intra_compare/bench/`, `results/python_integration/bench/` and `results/uncompressed_intra/bench/` (files cited above).

## Verification

**Date:** 2026-11-10. Reports: `results/gpu_encode/VERIFY_provenance.md` and `results/gpu_encode/VERIFY_method.md` (the previous reports are `VERIFY_provenance.prev.md` and `VERIFY_method.prev.md`).

**What the verifiers checked:**
- Provenance: about 150 quiet-run numbers recomputed from the JSON (`matched_stream` `summary[]`, `matched_concurrent` `runs[]` and `limit_probe`, the raw sweep points, `matched_settings.json`, the nvJPEG decode JSON, uncompressed_intra). Almost all matched. The mjpeg_qsv chroma correction holds in all 8 raw files. NVENC 12/32 and QSV 32/32 match the probes. Primary sources re-fetched on 2026-11-10 (NVIDIA matrix, NVDEC guide, Intel README and media_features, pyav-ffmpeg build script).
- Method: advertised pixel formats (`verify_method_fmts.json`, static), hevc_qsv `low_power`/`preset` open check (`verify_method_lowpower.json`, functional, untimed), run order vs libx265 affinity, same-chroma byte ratios, GPU Engine counters, late-frame shares, single-stream vs scaling N=1 fps, nvJPEG worker mode, and the Defender caveat.
- The reviser re-checked each refutation against the evidence before applying it: the hevc_qsv-from-mjpeg_qsv `runs[]` aggregates, the per-class QP values in `matched_settings.json`, `verify_method_fmts.json`, the item-1 `summary[]` and `runs[]` order and engine counters, every `matched_concurrent_*` file, the nvJPEG decode table, and `benchpaths.py` line numbers. No timed runs.

**What was changed:**

| item | before | after |
|---|---|---|
| hevc_qsv from mjpeg_qsv decode (2.8) | "66-67 fps" | refuted; now 63.5-66.8 fps aggregate (66.3-66.6 at N ≥ 8) |
| NVENC/QSV QP summary (2.8 header) | qp 12 / 31 and QP 12-13 / 30-31 for every row | refuted as general; scoped to `yuy2_1080p`, plus per-class ranges (NVENC A 11-14, B 28-31; QSV A 12-14, B 28-31) |
| I7 "QSV takes yuyv422 directly" | all QSV | refuted; only hevc_qsv and mjpeg_qsv; h264_qsv needs NV12 |
| NVENC with packed YUY2 (6.2) | NOT TESTED | answered statically: not advertised; needs a conversion |
| Table 3.2 and 2.7/2.8 single-stream cells | headed "P-cores" | † marks on cells after the libx265 widening; header no longer says P-cores |
| I7 swscale cost | single-stream † cells only | primary evidence is now the P-core-only scaling pair (2.41-2.64 vs 0.60-0.64 cores) |
| JPEG byte ratios (I9, 2.7, 3.2) | × jt422 only (mjpeg_qsv_420 0.96) | same-chroma ratio added; I9 now "about 7-8 % larger than libjpeg-turbo" |
| nvJPEG 1.44 dB gap (I2, 2.7) | applied to the timed path | split: 1.44 dB in the exact-RGB sweep; 0.46-0.48 dB on the timed swscale path |
| "keeps up" claims | no late-frame caveat | late shares added (nvjpeg_422 5.3-13.3 %, mjpeg_qsv→h264_qsv 1.1-4.3 % at N=1-8, mjpeg_qsv_420 N=1, 720p reps) |
| mjpeg_qsv_420 N=16 cores | 1.05 (1.03-1.05) | 1.05 (1.03-1.06) |
| nvJPEG decode (2.6, 3.3) | 1.92-2.27 ms / 3.37-3.64 ms | camera sets 2.08-2.27 / 3.45-3.64; generic set noted separately |
| hevc_qsv "not viable" (I5) | general | scoped to default mode; 3D-engine load and untimed `low_power=1` added |
| 3.2 limit column | "none to 32" | split into sessions opened (probe) and inferred throughput ceiling |
| nvJPEG scaling | unqualified | thread workers; GIL possible confounder; process mode NOT TESTED |
| single-stream vs scaling | set side by side | note that they differ by up to 40 % |
| CPU per frame for mjpeg_qsv (I7) | single-stream † only | scaling figures (1.8-2.0 ms) added for sizing |
| Defender caveat (§5) | background MsMpEng CPU | write-path cost excluded; pointer to write_throughput (26.8 vs 1.2-1.5 CPU-s per 30 s cell) |
| timed rows intra | implied | "inferred from identical settings" |
| uncompressed_intra pointer (2.9) | "Lossless" | flag 9 added; functional matrix cited; 720p unchecked |
| intra_playback pointer (2.9) | frame-exact seek | "functional only; draft unverified"; scrub and sync flags added |
| I3, I9 scope | general | driver 610.88, one process, preset p4, UHD 770 only |
| I8 nvJPEG | "not a re-encode route" | scoped to the tested swscale-RGB pipeline; mjpeg_qsv-decode row QC pass noted |
| benchpaths citation | `benchpaths.py:7-19` | `benchpaths.py:199-244` (229 for YUY2; 214-215, 227-228, 239-240 for rgb24) |
| source access dates | 2026-11-09 | re-fetched 2026-11-10 where the provenance verifier re-fetched |
| style | missing verb in Status; 2.12 after 3.5; "16 (16 tested)" | fixed; 2.12 moved into section 2; "16 (max tested)" throughout |

**What remains NOT VERIFIED or NOT TESTED** (details in 6.2):
- hevc_qsv speed in low-power mode or with a faster preset.
- NVENC + QSV together under load; the NVENC cap across processes.
- QSV paced throughput beyond 16 streams (the ceilings in 3.2 are inferred).
- nvJPEG with process workers; nvJPEG host CPU share for decode; an exact-RGB or YUV nvJPEG route for camera MJPEG; why the mjpeg_qsv-decode nvJPEG row passes QC.
- Whether the † cells were affected by the affinity change (cannot be told from the files).
- Every non-Ampere, non-RPL-S hardware row (documents only).
- FFmpeg source lines and the AMD and Apple quotes (saved copies only, not re-fetched); the NVIDIA "82 of 90" row count was not recounted on 2026-11-10.

### Step 3 gap-fill (2026-11-10)

No tests or timing were run for this fold. Each change was checked against the gap-fill evidence files, not their summaries:
- GF03: quote ids G04, R04, R05, R06, R09, R19, R20, R21 and W10 are `found_verbatim: true` in `results/licensing/gapfill/GF03_quote_verification.json`; the header lines are in `GF03_sources/nvjpeg_h_12.4.0.76_lines.txt` (plus lines 143-146 in `results/gpu_encode/gapfill/nvjpeg_h_12.4.0.76_output_formats.txt`); the sm list is in `GF03_wheel_arch_facts.json` → `fatbin`; `results/gpu_encode/NOTES.md:148` gives the resolved nvjpeg wheel.
- GF05: chromium_codecs C17 and `results/chromium_codecs/raw/verify_method_rechecks.json` → `hevc422_probe_and_play.play_file_url` (E35 error 4, E45 error 3, 4:2:0 control `loadeddata` true).
- GF06: `GF06_pyav_options.json` (long names and options); FFmpeg n9.0.2 and AMF SDK v1.5.3 lines in `GF06_sources/`; AMF doc line 1417, which is not in the excerpt file, was checked in the scratchpad raw copy, whose sha256 matches `GF06_sources/FETCH_MANIFEST.txt`; 0 `i_quant_factor`/`i_quant_offset` matches in the AMF and VideoToolbox sources.
- GF07: datasheet rows and API lines in `GF07_sources/04-07_*.md`; KB OS line, the "Encode - supported codecs" row and the Arc B VP9 formats cell in `08_*.md`; the LNL "low-power low-latency" sentence was found in the scratchpad raw download (`step3/GF07/dl/lnl_ds_encode.txt`).

| id | where | before | after | why |
|---|---|---|---|---|
| GF03 | 2.7 (new "nvJPEG library provenance") | the nvjpeg wheel version only in NOTES.md | 12.4.0.76 = CUDA 12.9.1's libnvjpeg, not CUDA 12.4's (12.3.1.89); the `[nvjpeg]` extra is unpinned; pin it (inferred) | GF03 R04, R05, G04 |
| GF03 | 2.7, YUV rejection bullet | measured rejection only | nvImageCodec 0.10 release notes (R19 with its context, R20); nvJPEG API has YUV/NV12 encode input (code); cause of the rejection and the binding NOT VERIFIED / NOT TESTED | GF03 R19, R20; wheel `nvjpeg.h:154, 159, 540, 560` |
| GF03 | 2.6 | - | lead: nvJPEG 12.9 decode to NV12/YUY2; declared in the measured header (code); NOT TESTED | GF03 R21; wheel `nvjpeg.h:144-146` |
| GF03 | 2.12, 3.4 NVIDIA rows | Ada/Blackwell JPEG "NOT VERIFIED"; Turing not separated | binaries present (sm_75/89/120, static), not run; nvJPEG documents hardware JPEG encode only for Jetson Thor SM 10.1 (source); GeForce = CUDA backend (inferred); Ampere measured | GF03 §4, R06, R09 |
| GF03 | 6.2 | - | pointer to licensing GF03; nvImageCodec SLA §2.11 benchmark clause; licence channel conflict; bearing on publishing nvJPEG encode timings (inferred); 0.9.0.20 not inspected | GF03 W10, §3.1, §7 |
| GF04 | - | - | no change: 6.1 and I3-I5 agree with GF04's mapping and capacity values | `results/hw_accel_target/gapfill/GF04_capacity.json`, `GF04_NOTES.md` |
| GF05 | 6.2 | hevc_qsv 4:2:2 "not played" (pointer to intra_playback FINDINGS line 64) | measured to fail in E35/E45 on the RTX 3070; Chrome 156 NOT VERIFIED; old pointer marked stale | chromium_codecs C17 |
| GF06 | I6 | NVENC/QSV/D3D12 only; `i_qfactor` for "all" H.264/HEVC encoders | AMF and VideoToolbox intra and quality settings added (not tested); `i_qfactor` scoped to NVENC and QSV | GF06 code and AMF SDK lines |
| GF06 | 3.5 | h264/hevc_amf "short name only (encoder NOT VERIFIED)" | present (static PyAV query), function NOT VERIFIED | `GF06_pyav_options.json` |
| GF07 | 2.12, 3.4 Intel Arc/MTL/ARL/LNL/BMG row | JPEG "yes (source)" from the Linux media-driver | Linux yes; Windows MTL and ARL-S/HX yes (datasheets); LNL only per a "Confidential" datasheet; Arc B NOT VERIFIED; Arc A OS-agnostic, Windows inferred; none tested. VP9 cell: KB self-contradiction for Arc B; LNL datasheet vs KB Series 2 column | GF07 S4-S8 |
| GF03, GF07 | 6.2 first bullet; 3.4 lead-in | "The Intel rows come from Linux driver docs" | adds Intel Windows datasheets/KB and static nvJPEG binary inspection | consistency with the rows above |

Still NOT VERIFIED after the gap-fill: AMF and VideoToolbox intra/CQP behaviour on hardware; nvJPEG encode on Turing, Ada or Blackwell; a YUV/NV12-input nvJPEG binding and why nvImageCodec rejects YUV; nvJPEG decode to YUY2; Intel Windows JPEG encode on Arc B (and on LNL without the "Confidential" datasheet); Intel Windows VP9 encode on Arc B; Chrome 156 playback of HEVC 4:2:2; which licence governs the nvImageCodec wheel.

### Step 3 verification (2026-11-10)

Report: `results/gpu_encode/VERIFY_step3.md` (pass with minor fixes). The reviser checked each item against the evidence before applying it. No tests or timing were run.
- R1: `verify_method_rechecks.json` top-level keys are `when, machine, note, filefetch_range, hevc422_probe_and_play`; the E35/E45/control data is under `hevc422_probe_and_play.play_file_url`.
- W1: raw `nvimgcodec_release_notes_v0.10.0.txt:75` (scratchpad `step3/GF03/work/txt/`) puts R19 in the planar-RGB/BGR interleave-fallback paragraph; R20 is at line 76. `nvimgcodec_jpeg.md:41-42` records both P_YUV and I_YUV rejected; `nvimgcodec_jpeg.py:129-131` builds 4:4:4 YUV.
- W2: raw `cuda_12.9.1_relnotes.txt` has R21 at line 1152 under "nvJPEG: Release 12.9" (line 1149), not "12.9 Update 1" (line 1146). Lines 143-146 were read from the 12.4.0.76 wheel itself (sha256 `21923726…40abc`, same as GF03) and saved to `results/gpu_encode/gapfill/nvjpeg_h_12.4.0.76_output_formats.txt`. The licensing topic's excerpt file was not modified.
- W3: R06/R09 name only Jetson Thor (GF03 lines with R06, R09).
- W4, W5: `GF07_sources/08_*.md` codecs row lists VP9 for all five columns; formats row says "Not Supported" for Arc B only; GF07 lines 101-102 record the Series 2 vs LNL conflict.
- W6: GF07 line 69 labels Arc A JPEG "source (OS-agnostic); Windows inferred".
- W7: GF03 line 109 (§3.1, licence inconsistent, NOT VERIFIED) and line 282 (§7, nvImageCodec 0.9.0.20 not inspected); `bench_nvjpeg_decode.py:5` pins 0.9.0.20.

| id | where | before | after |
|---|---|---|---|
| R1 | 6.2; Step 3 gap-fill GF05 line | `verify_method_rechecks.json` → `play_file_url` | → `hevc422_probe_and_play.play_file_url` |
| W1 | 2.7 YUV bullet; 6.2 nvJPEG | R19 read as support for the measured rejection; "nvImageCodec 0.10 does not convert P_YUV" | R19 quoted with its context (RGB/BGR interleave fallback); R20 added; test input was 4:4:4 (code); I_YUV also rejected; cause NOT VERIFIED |
| W2 | 2.6 R21 bullet; 6.2 | "this release is the measured library" (inferred) | note is in the "nvJPEG: Release 12.9" section; the measured header declares `NVJPEG_OUTPUT_NV12` / `NVJPEG_OUTPUT_YUY2` (code, `nvjpeg.h:144, 146`) |
| W3 | 3.4 Ada/Blackwell JPEG; 2.12 | "No fixed-function JPEG encoder on GeForce" labelled source | nvJPEG documents hardware JPEG encode only for Jetson Thor SM 10.1 (source); GeForce = CUDA backend (inferred) |
| W4 | 2.12 KB bullet; 3.4 VP9 cell | KB gives Arc B VP9 "Not Supported"; codec list without VP9 | KB internally inconsistent for Arc B VP9 (codecs row lists VP9, formats row "Not Supported"); NOT VERIFIED; VP9 listed in every codecs cell |
| W5 | 3.4 VP9 cell; 2.12 | LNL datasheet "AVC, HEVC and AV1 only" as a Windows confirmation | KB Series 2 column lists VP9; which Series 2 parts it covers is not stated (GF07) |
| W6 | 3.4 Intel JPEG cell | "Windows: … Arc A yes (oneVPL doc, OS-agnostic)" | Arc A moved out of the Windows list; "source, OS-agnostic; Windows inferred" |
| W7 | 6.2 SLA bullet | SLA bears on 2.6-2.8, 3.2 | SLA is the wheel's licence file; PyPI/GitHub say Apache-2.0; which governs NOT VERIFIED; scope narrowed to 2.7, 2.8, 3.2; 0.9.0.20 decode timings (2.6, 3.3) flagged separately |
