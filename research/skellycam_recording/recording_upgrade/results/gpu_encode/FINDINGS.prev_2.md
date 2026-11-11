# gpu_encode: FINDINGS (G6 GPU-accelerated encode, G7 royalty-free codecs)

Status: functional results and primary sources only. This file has no timing numbers. Timed questions are in section 5.
Paths are relative to `research/skellycam_recording/recording_upgrade/` unless they start with `C:/`.
Labels: **measured** (a result file, cited), **source** (primary source, accessed 2026-11-09; re-fetch status in `results/gpu_encode/VERIFY_provenance.md` §3), **code** (file:line), **inferred** (marked, kept short).
Version rule: the implementation under test is PyAV 19.0.2 with its bundled FFmpeg (libavcodec 63.1.102). Results from PyAV 18.0.0 are labelled "PyAV 18 - background". Results from the gyan ffmpeg 9.0.2 CLI are labelled "CLI reference". The CLI has the same libavcodec 63.1.102 (`results/gpu_encode/cli_version.txt`), but requirement 5 says the CLI is not the implementation under test.
Revision: this version applies two verifier reports (`results/gpu_encode/VERIFY_provenance.md`, `results/gpu_encode/VERIFY_method.md`) and one extra functional check made in the revision pass (`results/gpu_encode/adapter_check_hevc_19.0.2.json`). See section 8.

## 1. Questions answered

1. Which hardware encoders work on Gerald (RTX 3070 Ampere, plus the UHD 770 iGPU of the i7-14700K) through PyAV 19.0.2? Which of them work all-intra and with a short GOP? (G6)
2. Which of them encode a codec other than H.264/HEVC (G7 candidates)? Which royalty-free GPU paths exist outside PyAV?
3. Which hardware encoders ship in the PyPI PyAV wheels on each OS? (G6, cross-platform)
4. Can the GPU decode or encode the cameras' 4:2:2 MJPEG?
5. What is the NVENC concurrent-session limit, and which other APIs share it?

## 2. Findings

### 2.1 Machine state

- measured: during the original investigation (11:36), the Intel UHD 770 was `Unknown / Present False / CM_PROB_PHANTOM` (`results/gpu_encode/system_probe.txt`).
- measured, CLI reference: every QSV row in `ff_functional.md` failed with `Failed to find d3d11va adapter by vendor id 0x8086`. The string occurs 10 times (`results/gpu_encode/ff_functional.md`; count in `VERIFY_provenance.md` §2).
- inferred: the PyAV QSV rows in `pyav_functional_*.md` failed for the same reason. They record only `UnknownError [Errno 1313558101]` (the same AVERROR code), and the same encoders work once the iGPU is present (`qsv_recheck_19.0.2.md`).
- inferred: all `*_amf` encoders fail because the machine has no AMD GPU. The result files do not state the cause.
- measured: at 16:42 the UHD 770 was present: "OK True Intel(R) UHD Graphics 770" (`results/gpu_encode/qsv_recheck_19.0.2.md` header; also `results/hw_accel_target/system_probe_1700.txt`). The iGPU was still present during the revision pass (Get-PnpDevice, 2026-11-09). Every QSV statement below comes from runs with the iGPU present.
- measured: RTX 3070, driver 610.88, compute capability 8.6 (`system_probe.txt`).
- measured: the RTX 3070 Vulkan device enables `VK_KHR_video_encode_h264` and `_encode_h265`. It does not list `VK_KHR_video_encode_av1` (`system_probe.txt`). The list covers the device extensions ffmpeg uses, not a full device enumeration.

### 2.2 PyAV 19.0.2 on Gerald: encoders (implementation under test)

Input for every test: 32 NV12 1080p frames, which are 8 near-static real frames looped 4 times (`scripts/gpu_encode/common.py:4-5`), with `max_b_frames=0`. "intra" means gop_size 0 for NVENC and 1 for the other encoders.

- measured: the 26 working PyAV 19.0.2 outputs (NVENC, D3D12, MF, QSV including vp9_qsv and mjpeg_qsv) each decode to 32 frames. Y PSNR against the NV12 source is ≥ 45.18 dB, and the mean Y offset is ≤ 0.063 (`results/gpu_encode/verify_method_checks.json` → `psnr_y`). Chroma was not checked. The content is near-static, so these PSNRs are a sanity check, not a quality comparison.
- measured: `h264_nvenc` and `hevc_nvenc` work intra (32 I) and gop15 (3 I + 29 P), both with software frames and with `HWAccel('cuda')`. H.264 comes out as High and HEVC as Main (`results/gpu_encode/pyav_functional_19.0.2.md`).
- measured: the software-frame and `HWAccel('cuda')` outputs have identical packet payloads for h264_nvenc intra, h264_nvenc gop15 and hevc_nvenc intra (`results/gpu_encode/revise_nvenc_packet_hashes.txt`). In both modes the frames come from numpy in host memory.
- measured: `av1_nvenc` fails at `avcodec_open2` with software frames (`Generic error in an external library`) and with `HWAccel('cuda')` (`Function not implemented`) (`pyav_functional_19.0.2.md`).
- measured: `h264_d3d12va` and `hevc_d3d12va` fail with software frames (`avcodec_open2(...) returned 22`). With `HWAccel('d3d12va')` they work intra and gop15, written to MP4 (`pyav_functional_19.0.2.md`).
- measured: `h264_d3d12va` with PyAV's default `max_b_frames` (2) logs "Using intra, P- and B-frames" and then fails at `avcodec_send_frame` with "Encode failed: Unknown error occurred" (`results/gpu_encode/verify_method_opts.json`).
- measured: `h264_d3d12va` writing to `.mkv` fails with `InvalidDataError` and leaves a 291-byte file (`results/gpu_encode/verify_method_opts_mkv.json`; file in `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/gpu_encode/verify_method/`).
- measured, once: in the same process, right after the failed B-frame encode, D3D12 device creation failed (`887a0020`). It succeeded in a fresh process (`verify_method_opts.json`, `verify_method_opts_mkv.json`).
- measured: with the iGPU present, the default D3D12 device is the NVIDIA card. Both `h264_d3d12va` and `hevc_d3d12va` log "D3D12VA: Using device 10de:2484 (NVIDIA GeForce RTX 3070)." and give 8/8 I frames (`results/gpu_encode/adapter_check_19.0.2.json`, `results/gpu_encode/adapter_check_hevc_19.0.2.json`).
- measured: `av1_d3d12va` fails at open (`returned 22`) in both modes (`pyav_functional_19.0.2.md`).
- measured: `h264_mf` and `hevc_mf` with `hw_encoding=1` work intra and gop15. H.264 comes out as Constrained Baseline (`pyav_functional_19.0.2.md`, iGPU absent). With the iGPU present, `h264_mf` was re-run (`qsv_recheck_19.0.2.md`) and `hevc_mf` was re-run intra (`adapter_check_hevc_19.0.2.json`, 8/8 I, Main).
- measured: with the iGPU present, the MF enumeration lists both NVIDIA and Intel MFTs, and the encoder logs "activate MFT 0". The MFT used is "NVIDIA H.264 Encoder MFT" for h264_mf (`adapter_check_19.0.2.json`) and "NVIDIA HEVC Encoder MFT" for hevc_mf (`adapter_check_hevc_19.0.2.json`).
- measured, CLI reference: with the iGPU absent, the CLI `av1_mf` picked "Intel® Hardware Accelerated AV1 Encoder MFT" (`system_probe.txt`, last section).
- measured: PyAV `av1_mf` fails in both iGPU states: with `OSError ... -104 ... avcodec_send_frame()` while the iGPU was absent (`pyav_functional_19.0.2.md`), and with `InvalidDataError` once it was present, where it picks the Intel AV1 MFT (`qsv_recheck_19.0.2.md`, MFT column).
- measured (iGPU present): QSV encoders with software frames.

  | encoder | intra | gop15 | profile / pix_fmt |
  |---|---|---|---|
  | `h264_qsv` | 32 I | 3 I + 29 P | High / yuv420p |
  | `hevc_qsv` | 32 I | 3 I + 29 B (low-delay, see below) | Main / yuv420p |
  | `vp9_qsv` | 32 I | 3 I + 29 P | Profile 0 / yuv420p |
  | `mjpeg_qsv` | 32 I | 32 I | Baseline / yuvj420p |

  Source: `results/gpu_encode/qsv_recheck_19.0.2.md`.
- measured: `av1_qsv` fails at open with "Current codec type is unsupported" and "some encoding parameters are not supported by the QSV runtime" (`qsv_recheck_19.0.2.md`).
- measured: every QSV encoder fails with `HWAccel('qsv')`, with "Error initializing a child frames context / Error creating an internal frame pool" (`qsv_recheck_19.0.2.md`). Only one construction was tried. From PyAV, QSV works only with software frames.
- measured: in the `hevc_qsv` gop15 output the 29 non-IDR pictures are B slices that reference only past pictures. trace_headers shows slice_type I = 3 and B = 29. Every explicit short-term RPS has `num_positive_pics = 0`. The POC rises 1..14 in decode order within each GOP (`results/gpu_encode/verify_method_hevc_qsv_trace.txt`; counts in `VERIFY_provenance.md` §1.2).
- measured: in the same output pts == dts for every packet and `has_b_frames` is 0 (`results/gpu_encode/qsv_recheck2_ffprobe.txt`). There is no reordering.
- not checked: whether list 1 holds the same pictures as list 0 (strict GPB).
- measured: `gpb=0` had no effect. The encoder logs `GPB: ON` for both `gpb=0` and `gpb=1` (`verify_method_checks.json` → `gpb`), and the default, gpb=0 and gpb=1 files have identical packet payloads (`results/gpu_encode/verify_method_packet_hashes.txt`; `VERIFY_provenance.md` §1.1). Whether the option ever reaches the QSV runtime is NOT VERIFIED.
- measured: `h264/hevc/av1/ffv1_vulkan` are "not in av.codecs_available (not built into this wheel)" (`pyav_functional_19.0.2.md`).
- measured: all `*_amf` encoders fail (`pyav_functional_19.0.2.md`).
- measured: `hwdevices_available` = cuda, dxva2, qsv, d3d11va, d3d12va, amf. vulkan is not in the list (`pyav_functional_19.0.2.md`, `qsv_recheck_19.0.2.md`).

### 2.3 PyAV 18 vs 19

- measured (PyAV 18 - background): with the iGPU absent, PyAV 18.0.0 and 19.0.2 give the same pass/fail on every encoder and decoder row. One output differs: with `preset=p4` and these settings, `h264_nvenc` reports profile **Main** under PyAV 18 and **High** under PyAV 19 (`diff` of `pyav_functional_18.0.0.md` and `pyav_functional_19.0.2.md`). NOTES.md §1 said "identical"; this corrects it.
- measured: libavcodec is 62.28.102 in PyAV 18.0.0 and 63.1.102 in PyAV 19.0.2 (headers of `pyav_functional_*.md`).
- measured: in all 6 PyPI wheels inspected, PyAV 19.0.2 contains the same hardware codec names as 18.0.0 (`results/gpu_encode/wheel_hw_codecs.md`; the two version blocks are identical).

### 2.4 NVENC session limit and pool sharing

- measured, PyAV 19.0.2: 12 `h264_nvenc` sessions (1280×720) opened, and the 13th failed at `avcodec_open2`. nvidia-smi showed `12` while they were open and `0` before (`results/gpu_encode/nvenc_sessions_19.0.2.json`). It showed `1` after close, most likely another process.
- measured, PyAV 19.0.2, with a control: with no sessions held, `hevc_nvenc`, `h264_d3d12va`, `h264_mf` and `h264_qsv` each encoded 3 packets. With 12 `h264_nvenc` sessions held (nvidia-smi `12`), three of them failed: `hevc_nvenc` ("OpenEncodeSessionEx failed: incompatible client key (21)"), `h264_d3d12va` ("Failed to create encoder.") and `h264_mf` ("could not set output type (MF_E_UNSUPPORTED_D3D_TYPE)"). `h264_qsv` still encoded 3 packets (`results/gpu_encode/verify_method_pool.json`).
- measured: while the 12 sessions were held, `h264_mf` still activated "NVIDIA H.264 Encoder MFT". It did not fall back to the Intel MFT (`verify_method_pool.json`).
- measured, CLI reference, no control: `h264_vulkan` also failed while the 12 sessions were held (`nvenc_sessions_19.0.2.json`). The error is generic.
- inferred: NVENC, D3D12 and MF (through the NVIDIA MFT) share the GeForce 12-session pool, and Vulkan probably does too (CLI only, no control). QSV is outside that pool.
- measured (PyAV 18 - background): same limit, 12 opened and the 13th failed (`results/gpu_encode/nvenc_sessions.json`). The prior study found "12 (20)" (`research/frame_ring_buffer/prototypes/results/p5_nvenc.md:7`).
- source: NVIDIA support matrix, "Max # of concurrent sessions": 12 in every GeForce row that has NVENC. 82 of 90 GeForce rows say 12; MX570 A, MX150>MX330, MX350 and GT 1030 say 0, and four older mobile rows say n/a (re-fetched 2026-11-09, `VERIFY_provenance.md` §2; https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new).

### 2.5 ffmpeg 9.0.2 CLI hardware encoders (CLI reference; run while the iGPU was absent)

Source for every bullet unless stated: `results/gpu_encode/ff_functional.md` / `.json`.

- measured, CLI: `h264_nvenc -g 1 -bf 0` fails with "InitializeEncoder failed: invalid param (8): Gop Length should be greater than number of B frames + 1". `-g 0` gives 32 I.
- measured, PyAV 19.0.2: `h264_nvenc` with gop_size 1 and max_b_frames 0 fails at open with the same message (`verify_method_opts.json`).
- code: `libavcodec/nvenc.c:1761-1767` @ n9.0.2: `gop_size == 0` takes the intra-only path (NOTES.md §3; checked against the investigator's saved copy, not re-fetched).
- measured: `h264_vulkan` (High) and `hevc_vulkan` (Main) work intra and gop15.
- measured: `av1_vulkan` fails with "Device does not support encoding av1!".
- measured: `h264_d3d12va` works with `-bf 0`. With default B-frames, gop15 fails with "Encode failed: Unknown error occurred". Writing `.mkv` fails with "Could not write header (incorrect codec parameters ?)". PyAV 19.0.2 behaves the same (2.2).
- measured: `ffv1_vulkan` works on yuv420p 1080p with `-level 4 -strict -2`, on bgr0 intra, and on bayer_rggb16le with `-level 4 -strict -2`.
- measured: the lossless round trip is byte-exact for all three (8/8 frames; framemd5 against the CPU ffv1 decode; bgr0 compared as gbrp) (`ff_functional.json` → `roundtrip`).
- measured: at level 3, `ffv1_vulkan` yuv420p fails with "Encoding frames with subsampling and unaligned dimensions is only supported in version 4 (-level 4)", and bgr0 gop15 fails with "Using inter frames requires version 4 (-level 4)".
- measured: `ffv1_vulkan` gop15 gives 3 key packets out of 32, while ffprobe reports all 32 as pict_type I.
- inferred, thin: from `ffv1enc_vulkan.c:279,289` (`has_inter = gop_size > 1` and the key-frame decision; NOTES.md §3). Non-key packets are probably not independently decodable. The cited lines do not show the state carry-over itself. Use gop 1 for crash tolerance and scrubbing.
- measured: `prores_ks_vulkan` works: 32 I, HQ, yuv422p10le.
- measured: file sizes for 8 synthetic 16-bit Bayer frames: `diag/bayer_vk.mkv` (ffv1_vulkan) is 8,087,879 bytes and `diag/bayer_cpu.mkv` (CPU ffv1 defaults) is 17,047,238 bytes (`ls -l` of `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/gpu_encode/diag/`). The coder settings differ, and the synthetic Bayer has a zero low byte, so this is not a codec comparison. Whether the CPU file is byte-exact is NOT VERIFIED (no result file).

### 2.6 MJPEG (camera 4:2:2) decode on the GPU

- measured, PyAV 19.0.2: on 5 real 4:2:2 camera JPEGs per set (c930e_1080p, c930e_720p_flash), `mjpeg_cuvid` fails with "Generic error in an external library: 'avcodec_send_packet()'", and `mjpeg` + `HWAccel('cuda')` fails with "'avcodec_send_packet()' returned 22" (`pyav_functional_19.0.2.md`).
- measured, PyAV 19.0.2, with a control: `diag/j420.mjpeg` (yuvj420p) decodes 3/3 to nv12 with both `mjpeg_cuvid` and `mjpeg` + `HWAccel('cuda')`. `inputs/mjpeg_1080p.mjpeg` (yuvj422p; c922_1080p frames per `common.py:95`) fails with both. The errors are `cuvidDecodePicture ... CUDA_ERROR_INVALID_HANDLE`, and `cuvidCreateDecoder ... CUDA_ERROR_NO_DEVICE`, which is a misleading message (`results/gpu_encode/verify_method_cuvid.json`). NVDEC MJPEG through PyAV therefore works for 4:2:0 and fails for the cameras' 4:2:2.
- NOT VERIFIED (no saved output): the CLI `mjpeg_cuvid` hang on 4:2:2 and the silent CPU fallback of `-hwaccel cuda` (NOTES.md §5 only).
- source: the NVDEC guide (SDK 13.0) lists "Hybrid (CUDA + CPU) JPEG" (re-fetched 2026-11-09; https://docs.nvidia.com/video-technologies/video-codec-sdk/13.0/nvdec-video-decoder-api-prog-guide/index.html). The guide says nothing about 4:2:2 JPEG.
- measured: the `mjpeg_qsv` decoder decodes the camera 4:2:2 JPEGs, 5/5 frames per set (c930e_1080p, c930e_720p_flash). Its output format is **nv12**, so chroma is reduced to 4:2:0 (`qsv_recheck_19.0.2.md`).
- measured: mjpeg_qsv luma matches the CPU `mjpeg` decode. On the raw Y planes (`frame.planes[0]`, no swscale) the max |diff| is 1, the mean |diff| is 0.007 (1080p) and 0.009 (720p), and the least-squares slope is 1.0 (`verify_method_checks.json` → `mjpeg_qsv_raw`).
- measured: mjpeg_qsv tags its nv12 frames `color_range` 1 (limited), but the samples span the same full range as the CPU's yuvj422p (0-255 at 1080p) (`verify_method_checks.json`). The earlier "Y max 21, mean 7.7-8.3" (`qsv_recheck2_19.0.2.json`) came from `to_ndarray(format='gray')`, which applied a limited-to-full expansion because of that tag.
- inferred: any conversion that trusts the tag will stretch contrast. A recorder using mjpeg_qsv decode must override the range to full.
- not compared: mjpeg_qsv chroma.
- measured: `mjpeg` + `HWAccel('qsv', allow_software_fallback=False)` returned `yuvj422p` software frames (`qsv_recheck_19.0.2.md`).
- inferred: that was a CPU decode (the native mjpeg decoder has no QSV hwaccel). NOT VERIFIED.
- measured (nvImageCodec 0.10.0.9, not PyAV): `nvjpeg_cuda_decoder` decodes the 4:2:2 camera JPEGs (c930e_1080p, c922_720p_flash) to an RGB device buffer. Against ffmpeg's CPU decode, max/mean |diff| is 8/0.245 at PSNR 53.14 dB (1080p) and 25/0.179 at 54.18 dB (720p) (`results/gpu_encode/nvimgcodec_jpeg.json`, `.md`).
- measured: `backend:HYBRID_CPU_GPU` gives numbers identical to `nvjpeg_cuda_decoder`. `backend:GPU_ONLY` and `HW_GPU_ONLY` fail with "Could not create decoder. Code: 7" (`nvimgcodec_jpeg.md`).
- measured: the CPU `libjpeg_turbo_decoder` also reports `STRIDED_DEVICE` (`nvimgcodec_jpeg.json`), so the buffer kind does not show where decoding ran.
- inferred: the working nvJPEG decode is the hybrid CPU+CUDA path. Its CPU share is pending (B4).

### 2.7 GPU JPEG encode

- measured: on QSV (PyAV 19.0.2), `mjpeg_qsv` encodes NV12 input to Baseline yuvj420p (`qsv_recheck_19.0.2.md`). 4:2:2 output (e.g. from YUY2 input) was not tested.
- source: the Intel media-driver doc lists JPEG encode "input format NV12/YUY2/UYVY/ABGR/Y8 and output format YUV400/YUV420/YUV422H_2Y/YUV444/RGB24" (`docs/media_features.md` line 79 @ intel-media-26.3.5, re-fetched 2026-11-09). This is the Linux driver; the Windows runtime was not checked.
- measured (nvImageCodec 0.10.0.9, nvJPEG CUDA, not PyAV): q90 encode of a 1920×1080 RGB image. The RGB is ffmpeg's CPU decode of a c930e_1080p JPEG (`scripts/gpu_encode/nvimgcodec_jpeg.py:94`). PSNR is against that RGB:

  | encoder | chroma | bytes | ffprobe pix_fmt | PSNR |
  |---|---|---|---|---|
  | nvjpeg_cuda_encoder | 4:2:2 | 144,880 | yuvj422p | 44.42 dB |
  | opencv_jpeg_encoder | 4:2:2 | 145,207 | yuvj422p | 47.25 dB |
  | nvjpeg_cuda_encoder | 4:2:0 | 133,516 | yuvj420p | 43.74 dB |
  | opencv_jpeg_encoder | 4:2:0 | 133,742 | yuvj420p | 46.16 dB |

  Source: `nvimgcodec_jpeg.json`. At about the same size, nvJPEG q90 scores 2.4-2.8 dB below OpenCV q90, so "q90" does not mean the same quality in the two encoders.
- measured: `backend:GPU_ONLY` encode fails with "Could not create encoder. Code: 7" (`nvimgcodec_jpeg.md`).
- measured: chaining nvjpeg_cuda_decoder into nvjpeg_cuda_encoder works: 144,363 bytes, yuvj422p, 43.5 dB against the ffmpeg decode (`nvimgcodec_jpeg.json` → `gpu_resident`).
- inferred: the script meant this as a decode-to-encode path with no host copy. That was not measured.
- measured: nvImageCodec rejects YUV input (`P_YUV` / `I_YUV`: "encode returned None"). It accepts gray input (`P_Y` / `I_Y`) and outputs `gray` (`nvimgcodec_jpeg.md`).
- measured: releasing GPU-decoded images without synchronisation printed 392 `CUDA error #700` lines in runs d1, d8 and dl1+d8, and 0 in dl1, eh1, ed1, ec1 and ed1+d8. Every run exited with code 0 (`results/gpu_encode/nvimgcodec_lifetime.json`).

### 2.8 Hardware encoders in the PyPI PyAV wheels

Method: static string search of the bundled libavcodec in each wheel, with sha256 checks (`wheel_hw_codecs.md`; `scripts/gpu_encode/wheel_hw_codecs.py:59-60`). Short names (column 3) are shared with decoders. Encoder long names (column 4) prove an encoder, but the long-name matcher misses some: on win_amd64 it finds no long name for h264_qsv, hevc_qsv, mjpeg_qsv, h264_mf or hevc_mf, yet all five work (`qsv_recheck_19.0.2.md`, `pyav_functional_19.0.2.md`). So a missing long name is not proof that the encoder is absent.

| wheel | encoder proven (long name or functional) | short name only (encoder NOT VERIFIED) |
|---|---|---|
| win_amd64 | NVENC h264/hevc/av1; QSV av1/vp9; AMF av1; D3D12VA h264/hevc/av1; MF av1; plus functional h264/hevc/mjpeg_qsv and h264/hevc_mf | vp9_d3d12va, h264/hevc/vp9_amf |
| win_arm64 | D3D12VA h264/hevc/av1; MF av1 | h264/hevc_mf, vp9_d3d12va |
| manylinux_2_28_x86_64 | NVENC h264/hevc/av1; QSV av1/vp9; AMF av1; V4L2 m2m h264 | h264/hevc/mjpeg/vp8_qsv, h264/hevc/vp9_amf, hevc/vp8/vp9_v4l2m2m |
| manylinux_2_28_aarch64 | V4L2 m2m h264 | hevc/vp8/vp9_v4l2m2m |
| macOS arm64 / x86_64 | VideoToolbox H.264, H.265, ProRes | av1/vp9_videotoolbox (decoders, see code below) |

- measured: none of the wheels contains VAAPI or Vulkan names (`wheel_hw_codecs.md`).
- source: pyav-ffmpeg `scripts/build-ffmpeg.py` @ 9.0.2-1, lines 188-203, has `--enable-nvenc --enable-nvdec`, `--enable-amf`, `--enable-libvpl` and `--enable-videotoolbox`. It has no `--enable-vulkan` and no VAAPI flag (re-fetched 2026-11-09; https://github.com/PyAV-Org/pyav-ffmpeg/blob/9.0.2-1/scripts/build-ffmpeg.py).
- code: ffmpeg n9.0.2 `libavcodec/allcodecs.c:875,890,907` declares only the h264, hevc and prores VideoToolbox encoders. No AV1 or VP9 VideoToolbox encoder exists (NOTES.md §7.4; checked against the investigator's saved copy, not re-fetched).

### 2.9 Vendor support, from primary sources

- source (re-fetched 2026-11-09): NVIDIA support matrix (URL above):
  - RTX 2080 / Turing: AV1 encode "NO".
  - RTX 3070 / Ampere: AV1 4:2:0 encode "NO"; H.264 4:2:2 and HEVC 4:2:2 encode "NO".
  - RTX 4070 / Ada: AV1 "YES".
  - RTX 5070 / Blackwell: AV1 "YES" and 4:2:2 "YES".
  - The matrix has no VP9 encode column.
- source (re-fetched 2026-11-09): Intel media-driver `intel-media-26.3.5` README groups the platforms. "TGLx (TGL: Tiger Lake, RKL: Rocket Lake, ADL-S/P/N: Alder Lake, RPL-S/P: Raptor Lake)", "ICL (Ice Lake)", and "KBLx (KBL: Kaby Lake, CFL: Coffee Lake, WHL: Whiskey Lake, CML: Comet Lake, AML: Amber Lake)" (README.md lines 79-82; https://github.com/intel/media-driver/blob/intel-media-26.3.5/README.md).
- source (re-fetched 2026-11-09): `docs/media_features.md` lines 59-76 (VDEnc table) (https://github.com/intel/media-driver/blob/intel-media-26.3.5/docs/media_features.md):
  - TGLx and ICL: AVC, JPEG, HEVC and VP9 8-bit encode; the AV1 cell is blank.
  - KBLx: AVC and JPEG only; the VP9 and HEVC cells are blank.
  - DG2, MTLx, LNL, BMG, PTL and NVL: AV1 8-bit encode.
  - BMG and LNL: the VP9 cell is blank.
  - In the PAK+shader table (lines 83-95), KBLx has HEVC 8-bit and VP8 encode, and no VP9.
- source caveat: this is the Linux driver documentation. Whether the Windows driver exposes the same matrix was measured only for RPL-S (next bullet).
- measured, RPL-S on Windows, consistent with the TGLx column: vp9_qsv, mjpeg_qsv, h264_qsv and hevc_qsv encode, and av1_qsv is "unsupported" (`qsv_recheck_19.0.2.md`).
- inferred from the source: 10th-gen Comet Lake desktops (KBLx group, 2020) have no VP9 hardware encode. F-SKU CPUs have no iGPU and so no QSV.
- source (checked against the investigator's saved HTML, not re-fetched): AMD RX 7600 (RDNA 3) spec page says "AV1 Encode Yes". The RX 6600 page has only "AV1 Decode Yes" (NOTES.md §7.3).
- source (saved HTML, not re-fetched): the Apple M5 and M2 MacBook spec pages list hardware-accelerated "H.264, HEVC, ProRes, and ProRes RAW". The M5 pages also list "AV1 decode" (NOTES.md §7.4).

## 3. Comparison tables

### 3.1 Hardware encode on Gerald through PyAV 19.0.2 (functional only)

Source: `pyav_functional_19.0.2.md`, `qsv_recheck_19.0.2.md`, `adapter_check_19.0.2.json`, `adapter_check_hevc_19.0.2.json`, `verify_method_checks.json` (Y PSNR), `verify_method_pool.json`.

| encoder | device | sw frames | HWAccel ctx | intra | gop15 | in NVENC 12-session pool | codec class |
|---|---|---|---|---|---|---|---|
| h264_nvenc / hevc_nvenc | RTX 3070 | yes | yes (cuda)¹ | yes (`gop_size=0` only) | yes | yes | H.264/HEVC (G7: avoid) |
| h264_d3d12va / hevc_d3d12va | RTX 3070 (default device) | no (err 22) | yes (d3d12va), MP4 only, `max_b_frames=0` | yes | yes | yes (h264 tested) | H.264/HEVC |
| h264_mf / hevc_mf | NVIDIA MFT (MFT 0) | yes | n/a | yes | yes | yes (h264 tested) | H.264/HEVC |
| h264_qsv / hevc_qsv | UHD 770 | yes | no (frame pool) | yes | yes (HEVC: low-delay B, no reorder) | no (h264 tested) | H.264/HEVC |
| **vp9_qsv** | UHD 770 | yes | no | yes | yes | not tested | VP9 (G7 candidate; licence per licensing topic) |
| **mjpeg_qsv** | UHD 770 | yes (4:2:0 out) | no | yes | n/a | not tested | JPEG (licence per licensing topic) |
| av1_nvenc / av1_d3d12va / av1_mf / av1_qsv | - | no | no | - | - | - | AV1: no hardware on Gerald |
| *_vulkan, ffv1_vulkan, prores_ks_vulkan | - | not in wheel | not in wheel | - | - | - | - |

¹ The encoder opens with a device context, but the frames are still uploaded from host memory. The packets are identical to the software-frame mode (`revise_nvenc_packet_hashes.txt`). Upload cost is pending (B3b).

### 3.2 GPU / royalty-free paths outside PyPI PyAV (measured on Gerald)

| path | how reached | measured result |
|---|---|---|
| ffv1_vulkan (lossless) | ffmpeg CLI 9.0.2 (no PyAV binding) | byte-exact for yuv420p (L4), bgr0 and synthetic Bayer RGGB16 (`ff_functional.json`) |
| prores_ks_vulkan | ffmpeg CLI | works, HQ 4:2:2 10-bit (`ff_functional.md`) |
| nvJPEG encode/decode | nvImageCodec 0.10.0.9 (CUDA, NVIDIA only; hybrid CPU+GPU, inferred) | 4:2:2 / 4:2:0 / gray encode; decode of 4:2:2 to an RGB device buffer (`nvimgcodec_jpeg.json`) |

### 3.3 Decode of camera 4:2:2 MJPEG

| decoder | result | output | evidence |
|---|---|---|---|
| mjpeg (CPU) | ok | yuvj422p | `qsv_recheck_19.0.2.md` |
| mjpeg_cuvid (PyAV 19) | fails on 4:2:2; 4:2:0 control ok | nv12 (4:2:0 control) | `pyav_functional_19.0.2.md`, `verify_method_cuvid.json` |
| mjpeg + HWAccel cuda (PyAV 19) | fails on 4:2:2; 4:2:0 control ok | nv12 (4:2:0 control) | same |
| mjpeg_qsv (PyAV 19) | ok, 5/5; luma within ±1 of CPU | nv12 (chroma reduced to 4:2:0), mis-tagged limited range | `qsv_recheck_19.0.2.md`, `verify_method_checks.json` |
| nvImageCodec nvjpeg_cuda_decoder | ok (hybrid CPU+GPU, inferred) | RGB device buffer | `nvimgcodec_jpeg.json` |

### 3.4 Hardware encode of codecs other than H.264/HEVC, by platform

Rows come from the sources in 2.9 unless marked measured.

| platform | AV1 HW enc | VP9 HW enc | JPEG HW enc | in PyPI PyAV wheel |
|---|---|---|---|---|
| NVIDIA Turing/Ampere (RTX 2000/3000) | no (source) | inferred no (no VP9 column in the matrix) | CUDA nvJPEG (measured on Ampere; not PyAV) | only NVENC h264/hevc usable |
| NVIDIA Ada/Blackwell | yes (source) | inferred no (no VP9 column) | NOT VERIFIED | av1_nvenc compiled in (Win, Linux x64) |
| Intel TGLx (TGL, RKL, ADL, RPL; 11th-14th gen) and ICL | no (source; measured on RPL-S) | yes (source; **measured on RPL-S via PyAV 19**) | yes (source; **measured mjpeg_qsv on RPL-S**) | vp9_qsv: Win and Linux x64 (long name); mjpeg_qsv encoder: Win (measured), Linux x64 NOT VERIFIED (short name only) |
| Intel KBLx (incl. CML, 10th gen) | no (source) | no (source) | yes (source) | - |
| Intel Arc / MTL / ARL / LNL / BMG | yes (source) | yes, except LNL/BMG (source) | yes (source) | av1_qsv compiled in |
| AMD RDNA3 | yes (source, RX 7600) | NOT VERIFIED | NOT VERIFIED | av1_amf compiled in |
| AMD RDNA2 / Zen APUs | no AV1 encode row on the RX 6600 page | NOT VERIFIED | NOT VERIFIED | - |
| Apple silicon | no (source; no ffmpeg encoder, code) | no (no ffmpeg encoder, code) | NOT VERIFIED | VideoToolbox h264/hevc/prores only |
| CPU with no iGPU / no supported GPU | software only | software only | software only | libsvtav1 (encoder-only name); libvpx-vp9 encoder NOT VERIFIED (name shared with the decoder) |

## 4. Implications for the plan

- I1 (from 2.2, 3.4): through PyPI PyAV on Gerald, **vp9_qsv is the only working hardware inter-frame video encoder for a codec other than H.264/HEVC**. `mjpeg_qsv` also gives hardware JPEG (intra-only, 4:2:0 output from NV12). Both run only on the Intel iGPU. Per the Intel Linux driver docs, VP9 encode covers ICL, TGL-RPL, MTL/ARL and Arc. It does not cover KBLx (incl. 10th-gen Comet Lake), LNL/BMG, F-SKU CPUs, NVIDIA or Apple. Only RPL-S on Windows was measured.
- I2 (from 2.6, 2.7, 2.9): Ampere has no fixed-function (NVENC) encoder for any codec other than H.264/HEVC (source: matrix). On RTX 3000, the only GPU path for another lossy codec is CUDA JPEG through nvImageCodec (measured, outside PyAV, hybrid CPU+GPU inferred). So "hardware-accelerated on RTX 3000 and newer" plus G7 cannot be met by a video codec. The plan must state this trade-off openly.
- I3 (from 2.2): from PyAV, QSV works only with software frames (`HWAccel('qsv')` fails). Every QSV design pays a host-to-iGPU upload inside the encoder. The cost is pending (B-QSV in section 5).
- I4 (from 2.2, 2.7): `mjpeg_qsv` gives hardware JPEG encode for G4 raw inputs. From NV12 its output is 4:2:0. The Linux driver doc lists YUY2 input and 4:2:2 output (source), but neither was tested on Windows.
- I5 (from 2.4): on a GeForce card, NVENC, D3D12 and MF (through the NVIDIA MFT) share one 12-session pool (measured with a control; Vulkan CLI only, no control). So one GeForce GPU cannot give each camera of a 16-camera rig its own NVIDIA-backed session. QSV is outside the pool (measured: h264_qsv encoded with 12 NVENC sessions held), so an Intel iGPU can take extra streams. The QSV limit is untested. MF does not fall back to the Intel MFT when the pool is full.
- I6 (from 2.2, 2.5): intra settings must be explicit per encoder:
  - NVENC: `gop_size=0`; 1 is rejected (measured under PyAV 19.0.2 and the CLI).
  - QSV: `gop_size=1` works.
  - D3D12: needs `HWAccel('d3d12va')` and `max_b_frames=0`, and MP4 only. PyAV's default B-frames fail and MKV fails (measured, PyAV 19.0.2).
- I7 (from 2.2): `hevc_qsv` gop15 emits low-delay B slices even with `max_b_frames=0`. They reference only past pictures and there is no reordering (measured at slice level). `gpb=0` had no effect, so it is not a way to get P pictures. Frame-accurate seek of these files in Chromium (G9) is for the chromium topics. Intra-only avoids the question.
- I8 (from 2.6): the GPU cannot decode the cameras' 4:2:2 MJPEG through NVDEC from PyAV, while 4:2:0 MJPEG does decode (measured with a control). `mjpeg_qsv` decodes 4:2:2 accurately in luma, reduces chroma to 4:2:0, and mis-tags the range as limited. The recorder must override the range. nvJPEG (hybrid CPU+GPU, inferred) decodes 4:2:2 to RGB without first reducing chroma to 4:2:0. For G1 this matters only for previews and overlays, since archival is passthrough.
- I9 (from 2.3): PyAV 19.0.2 brings no new hardware encoder over 18.0.0, so the choice of version rests on other reasons. With preset p4 and these settings, `h264_nvenc` output changed from Main (PyAV 18 - background) to High.
- I10 (from 2.2, 2.5): PyPI PyAV cannot reach `ffv1_vulkan` (royalty-free lossless on the GPU, byte-exact including synthetic Bayer) or `prores_ks_vulkan`. They need a CLI subprocess or a custom FFmpeg/PyAV build with `--enable-vulkan`. This belongs in the standard-FFmpeg vs custom-build trade-off.
- I11 (from 2.2), inferred: on Gerald, D3D12 and MF chose the NVIDIA device for both h264 and hevc, but the default adapter is machine-dependent. The recorder should allow explicit device selection.

## 5. Pending tonight's bench

Timed questions. `bench_manifest` ids come from `results/bench_queue_from_wf_2e122ed0.json` → `gpu_encode`. The verifiers made no bench requests.

| timed question | manifest id | needs fixing before the run |
|---|---|---|
| Single-stream fps and CPU cost per GPU encoder, 720p/1080p, intra/gop15, from NV12 and from MJPEG | B1a | Runs through the **ffmpeg CLI** (`bench_ffmpeg_encode.py` docstring), so under requirement 5 the results are CLI reference only. Port to PyAV 19.0.2 or label them so |
| CPU reference encoders (libsvtav1, libvpx-vp9, mjpeg, ffv1), same matrix | B1b | same CLI caveat |
| Concurrent scaling 1-16 streams, h264_nvenc 1080p, unpaced and paced 30 fps (late frames, p99) | B2a | The manifest command uses `.venv` (PyAV 18). Use `uv run --script` (the script header pins av 19.0.2) |
| Same, hevc_nvenc 1080p | B2b | same |
| Same, h264_d3d12va 1080p | B2c | same |
| Same, h264_nvenc 720p | B2d | same |
| numpy-to-frame / swscale / upload / encode-call cost | B3b (keep); B3a (drop: PyAV 18) | - |
| GPU JPEG decode/encode throughput and CPU share vs CPU (nvImageCodec; hybrid decode) | B4 | Compare at matched quality or matched size, since nvJPEG q90 ≠ OpenCV q90 (2.7) |
| Session limit on a quiet machine | B5 | The manifest command uses `.venv` (PyAV 18). Run `nvenc_sessions_versioned.py` under `uv` with av==19.0.2 (section 7). Already answered functionally under PyAV 19.0.2 (12), so optional |
| B2a under PyAV 19 | B2e | redundant once B2a runs on 19 |
| **QSV** per-stream fps and CPU (h264/hevc/vp9/mjpeg_qsv, software frames), 720p/1080p, NV12/YUY2 and MJPEG input; stream scaling; QSV alongside 12 NVENC sessions | none (B-QSV, to be added by hw_accel_target) | code: `bench_pyav_concurrent.py:48-63` `make_ctx` handles `*_qsv` generically (software frames, gop 1 for intra). inferred: no code change needed; argument parsing not checked. `bench_ffmpeg_encode.py` has no qsv entries |
| mjpeg_qsv vs nvJPEG vs CPU JPEG encode cost for G4 raw input | none (add) | - |

Bench confounder (all rows):
- measured: the 1080p NV12 input is 8 near-static frames looped 4 times. In h264_qsv gop15, 24 of the 29 P packets are under 6 kB (`verify_method_packet_hashes.txt`).
- inferred: 1080p speed and size will look better than with real motion.
- Use `--size 720p` (60 consecutive real frames, `common.py:6-7`) as the primary input, or label 1080p results "static content".

## 6. Not tested / limits / NOT VERIFIED

- Only NVIDIA Ampere and the Intel RPL-S iGPU were tested physically. Every Turing, Ada, Blackwell, other-Intel, AMD and Apple row comes from documents. The Intel rows come from Linux driver docs.
- AV1 hardware encode through PyAV (av1_nvenc / av1_qsv / av1_amf / av1_d3d12va) on capable GPUs: NOT TESTED (no hardware).
- QSV session or concurrency limit: NOT TESTED. vp9_qsv / mjpeg_qsv alongside 12 NVENC sessions: NOT TESTED (only h264_qsv was).
- Vulkan Video in the NVENC pool: CLI only, no control.
- `hevc_qsv` strict GPB (L1 = L0): not checked. Whether `gpb` reaches the QSV runtime: NOT VERIFIED.
- QSV with YUY2 input, 4:2:2 or 10-bit output, and PyAV QSV files played in Chromium: NOT TESTED.
- Root cause of the `HWAccel('qsv')` frame-pool failure in PyAV: unknown (one construction tried).
- `mjpeg_qsv` decode chroma accuracy: not compared.
- CLI `mjpeg_cuvid` hang and silent `-hwaccel cuda` fallback: NOT VERIFIED (no saved output).
- D3D12 MKV failure and default-B-frame failure: whether they are FFmpeg bugs or driver limits is NOT VERIFIED. The D3D12 device-creation failure after a failed encode (887a0020) was seen once.
- `ffv1_vulkan` on AMD, Intel or MoltenVK: NOT VERIFIED.
- nvJPEG: where decode and encode actually run (hybrid share) and whether the decode-to-encode chain avoids a host copy: inferred only. A GPU-resident nvJPEG-to-NVENC path in Python: NOT TESTED. Whether PyAV can wrap external CUDA pointers: inferred unsupported, NOT TESTED.
- `torchvision.io.encode_jpeg` on CUDA: NOT TESTED.
- Root cause of nvImageCodec CUDA error 700: unknown.
- The FFmpeg source lines, AMD and Apple quotes were checked only against the investigator's saved copies in an old session's scratchpad (`C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/gpu_encode/src/`), which may be deleted. The Intel README and media_features.md re-fetched in this revision are saved in `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/gpu_encode/src/`. Jellyfin per-generation claims belong to `hw_accel_target`.
- Royalty and licence status of VP9, AV1, JPEG, FFV1 and ProRes: not asserted here (licensing topic).
- Functional encodes use 32 frames (8 near-static real 1080p frames looped). The Bayer input is synthetic.
- Other agents and Parsec/Sunshine processes were running during these checks. nvidia-smi showed 1 foreign NVENC session before the original PyAV 19 run (`pyav_functional_19.0.2.md`), 0 before the session-limit and pool checks, and 1 after them.

## 7. How to reproduce (repo root `C:/Users/Dom/GitHub/freemocap/skellycam`)

```
# PyAV 19.0.2 functional matrix (NVENC/D3D12/MF/QSV/AMF/Vulkan + MJPEG GPU decode)
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/pyav_functional.py
# QSV / MF re-check with the iGPU present -> results/gpu_encode/qsv_recheck_19.0.2.{json,md}
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/qsv_recheck.py
# hevc_qsv gpb + mjpeg_qsv gray-conversion diff -> results/gpu_encode/qsv_recheck2_19.0.2.json
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/qsv_recheck2.py
# default D3D12 device / selected MFT, h264 and hevc -> adapter_check_19.0.2.json, adapter_check_hevc_19.0.2.json
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/adapter_check.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/adapter_check_hevc.py
# verifier checks: gpb log, Y PSNR of all outputs, mjpeg_qsv raw Y; pool with control; NVDEC 4:2:0 control; CLI-only options in PyAV
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/verify_method_checks.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/verify_method_pool.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/verify_method_cuvid.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/verify_method_opts.py
# NVENC session limit under PyAV 19.0.2 -> results/gpu_encode/nvenc_sessions_19.0.2.json
# (the script docstring is stale: it still names nvenc_sessions.py and the PyAV 18 .venv; use this command)
uv run --no-project --with av==19.0.2 --with numpy==2.2.6 python research/skellycam_recording/recording_upgrade/scripts/gpu_encode/nvenc_sessions_versioned.py --max 16
# inspection only (ffprobe/ffmpeg), in the media dir .../gpu_encode/:
ffprobe -v error -select_streams v:0 -show_entries packet=pts,dts,flags -of csv=p=0 qsv_recheck_19.0.2/hevc_qsv_gop15_gpb0.mkv
ffprobe -v error -select_streams v:0 -show_entries stream=has_b_frames -of csv=p=0 qsv_recheck_19.0.2/hevc_qsv_gop15_gpb0.mkv
ffmpeg -hide_banner -v trace -i qsv_recheck_19.0.2/hevc_qsv_gop15_gpb0.mkv -c copy -bsf:v trace_headers -f null - 2>&1 | grep trace_headers | grep -E ' slice_type | num_positive_pics |slice_pic_order_cnt_lsb'
ffprobe -v error -select_streams v:0 -show_data_hash MD5 -show_entries packet=data_hash -of csv=p=0 pyav_19.0.2/h264_nvenc_intra_sw.mkv | md5sum
# wheel inspection (static, downloads wheels to scratchpad)
.venv/Scripts/python.exe -I research/skellycam_recording/recording_upgrade/scripts/gpu_encode/wheel_hw_codecs.py 19.0.2 18.0.0
# GPU JPEG (nvImageCodec 0.10.0.9) and buffer lifetime
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/nvimgcodec_jpeg.py
python research/skellycam_recording/recording_upgrade/scripts/gpu_encode/nvimgcodec_lifetime_run.py
# CLI reference matrix (ffmpeg 9.0.2 on PATH; reference only)
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/gpu_encode/ff_functional.py
# NVDEC 4:2:2 CLI checks from NOTES.md section 5 (media dir .../gpu_encode/; reported not to exit, so bound them; save the output)
timeout 60 ffmpeg -v verbose -c:v mjpeg_cuvid -i inputs/mjpeg_1080p.mjpeg -f null - > cli_mjpeg_cuvid.log 2>&1
timeout 60 ffmpeg -v verbose -hwaccel cuda -hwaccel_output_format cuda -i inputs/mjpeg_1080p.mjpeg -f null - > cli_hwaccel_cuda.log 2>&1
# iGPU presence (read-only)
powershell -NoProfile -Command "Get-PnpDevice -Class Display | ft Status,Present,FriendlyName"
```

Media from these runs goes to `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/gpu_encode/` (subfolders `qsv_recheck_19.0.2/`, `pyav_19.0.2/`, `ff_functional/`, `diag/`, `nvimgcodec/`, `verify_method/`).

## 8. Verification

Challenged by two verifiers (`results/gpu_encode/VERIFY_provenance.md`, `results/gpu_encode/VERIFY_method.md`). I re-checked each refutation against the cited result files before applying it. All of them held.

What changed:

| item | before | after | evidence |
|---|---|---|---|
| I1 | vp9_qsv the "only" lossy non-H.264/HEVC HW encoder | refuted: mjpeg_qsv also works; vp9_qsv is the only inter-frame one | `qsv_recheck_19.0.2.md` |
| hevc_qsv B pictures | inferred low-delay, NOT VERIFIED | measured: 29 B slices, past refs only, no reordering | `verify_method_hevc_qsv_trace.txt`, `VERIFY_provenance.md` §1.2 |
| `gpb=0` | "B also with gpb=0" | option had no effect (identical payloads, `GPB: ON` logged) | `verify_method_packet_hashes.txt`, `verify_method_checks.json` |
| mjpeg_qsv decode accuracy | Y diff 21 / 7.7, cause unexplained | refuted: luma within ±1; the defect is a wrong limited-range tag | `verify_method_checks.json` → `mjpeg_qsv_raw` |
| NVENC pool (I5) | four APIs share the pool (no control); QSV untested | controlled: NVENC/D3D12/MF share it, QSV outside; Vulkan CLI only | `verify_method_pool.json` |
| PyAV NVDEC MJPEG | 4:2:2 attribution without a control | 4:2:0 control decodes; 4:2:2 fails | `verify_method_cuvid.json` |
| NVENC gop 1, D3D12 B-frames, D3D12 MKV | CLI only | also measured in PyAV 19.0.2 | `verify_method_opts.json`, `verify_method_opts_mkv.json` |
| hevc_mf / hevc_d3d12va device | extrapolated from h264 | measured in this revision: NVIDIA device / NVIDIA HEVC MFT | `adapter_check_hevc_19.0.2.json` |
| "works" | ffprobe structure only | plus Y PSNR ≥ 45.18 dB on all 26 outputs | `verify_method_checks.json` → `psnr_y` |
| NVENC HWAccel ctx | implied GPU path | identical packets to sw frames; host upload either way | `revise_nvenc_packet_hashes.txt` |
| nvJPEG | "GPU decode at full 4:2:2" | hybrid CPU+GPU (inferred), RGB output; "no host copy" inferred; 720p set is c922 | `nvimgcodec_jpeg.md` |
| PyAV QSV/AMF failure cause; av1_mf pre-iGPU MFT | cited as measured from pyav files | inferred (QSV, AMF); CLI reference (av1_mf MFT) | `ff_functional.md`, `system_probe.txt` |
| NVIDIA matrix "every GeForce row" | 12 | 82 of 90 rows; non-NVENC rows give 0 / n/a | `VERIFY_provenance.md` §2 |
| Wheel table | mjpeg_qsv Linux; libvpx-vp9 encoder; aarch64 "H.264 only" | short name only → NOT VERIFIED; long-name false negatives noted | `wheel_hw_codecs.md` |
| Intel coverage | "TGL-RPL" | adds ICL (VP9 yes) and KBLx incl. Comet Lake (VP9 no), from the re-fetched README and media_features.md; Linux-doc caveat | section 2.9 |
| I2 | self-contradictory | no NVENC non-H.264/HEVC codec on Ampere; CUDA nvJPEG is the only GPU path | section 4 |
| B5, reproduce commands | B5 "optional"; no timeout; stale docstring | B5 flagged for PyAV 19; `timeout 60`; docstring noted | sections 5, 7 |
| Source status | "not re-fetched" | NVIDIA matrix, pyav-ffmpeg script, Intel docs, NVDEC guide re-fetched; FFmpeg/AMD/Apple saved copies only | `VERIFY_provenance.md` §3 |

One verifier claim was corrected rather than applied. VERIFY_method.md said the Intel table has no Ice Lake row. The re-fetched `media_features.md` has an ICL column that lists VP9 8-bit encode. It is Comet Lake that has no column of its own: the README puts it in the KBLx group.

Still NOT VERIFIED or not tested: see section 6. The main gaps are the QSV session limit, Vulkan pool membership with a control, mjpeg_qsv chroma, strict GPB, the Windows Intel matrix beyond RPL-S, every non-Gerald GPU, and every timing question (section 5).
