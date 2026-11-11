# gpu_encode: FINDINGS (G6 GPU-accelerated encode, G7 royalty-free codecs)

Status: functional results and primary sources only. There are no timing numbers in this file; timed questions are listed in section 5.
Paths are relative to `research/skellycam_recording/recording_upgrade/` unless they start with `C:/`.
Labels: **measured** (a result file, cited), **source** (primary source; URL and quote as recorded in `results/gpu_encode/NOTES.md`, accessed 2026-11-09, not re-fetched for this write-up), **code** (file:line), **inferred** (marked, kept short).
Version rule: the implementation under test is PyAV 19.0.2, with its bundled FFmpeg (libavcodec 63.1.102). Results from PyAV 18.0.0 are labelled "PyAV 18 - background". Results from the gyan ffmpeg 9.0.2 CLI are labelled "CLI reference". The CLI has the same libavcodec 63.1.102 (`results/gpu_encode/cli_version.txt`), but requirement 5 says it is not the implementation under test.

## 1. Questions answered

1. Which hardware encoders work on Gerald (RTX 3070 Ampere plus i7-14700K UHD 770) through PyAV 19.0.2? Which work with all-intra and short-GOP settings? (G6)
2. Which of them are codecs other than H.264/HEVC, i.e. G7 candidates? Which royalty-free GPU paths exist outside PyAV?
3. Which hardware encoders ship in the PyPI PyAV wheels on each OS? (G6 cross-platform)
4. Can the cameras' 4:2:2 MJPEG be decoded or encoded on the GPU?
5. What is the NVENC concurrent-session limit, and do other APIs share it?

## 2. Findings

### 2.1 Machine state

- measured: during the original investigation (11:36), the Intel UHD 770 was `Unknown / Present False / CM_PROB_PHANTOM` (`results/gpu_encode/system_probe.txt`). Every QSV row in `ff_functional.md` and `pyav_functional_*.md` failed for that reason: `Failed to find d3d11va adapter by vendor id 0x8086`.
- measured: at 16:42 the UHD 770 was present: "OK True Intel(R) UHD Graphics 770" (`results/gpu_encode/qsv_recheck_19.0.2.md`, header line; also `results/hw_accel_target/system_probe_1700.txt`). All QSV statements below come from the 16:42 re-check.
- measured: RTX 3070, driver 610.88, compute capability 8.6 (`system_probe.txt`).
- measured: the RTX 3070's Vulkan device enables `VK_KHR_video_encode_h264` and `_encode_h265`. It does not list `VK_KHR_video_encode_av1` (`system_probe.txt`).

### 2.2 PyAV 19.0.2 on Gerald: encoders (implementation under test)

Input for every test: 32 NV12 1080p frames (8 real frames looped 4 times), `max_b_frames=0`. "intra" means gop_size 0 for NVENC and 1 for the others. Each output was checked with ffprobe.

- measured: `h264_nvenc` and `hevc_nvenc` work, both intra (32 I) and gop15 (3 I + 29 P), with software frames and with `HWAccel('cuda')`. H.264 comes out as High, HEVC as Main (`results/gpu_encode/pyav_functional_19.0.2.md`).
- measured: `av1_nvenc` fails at `avcodec_open2` with software frames (`Generic error in an external library`) and with `HWAccel('cuda')` (`Function not implemented`) (`pyav_functional_19.0.2.md`).
- measured: `h264_d3d12va` and `hevc_d3d12va` fail with software frames (`avcodec_open2(...) returned 22`). They work with `HWAccel('d3d12va')`, intra and gop15, written to MP4 (`pyav_functional_19.0.2.md`).
- measured: with the iGPU present, the default D3D12 device is still the NVIDIA card. Log line: "D3D12VA: Using device 10de:2484 (NVIDIA GeForce RTX 3070)." Output: 8/8 I frames, H.264 Main (`results/gpu_encode/adapter_check_19.0.2.json`).
- measured: `av1_d3d12va` fails at open (`returned 22`) in both modes (`pyav_functional_19.0.2.md`).
- measured: `h264_mf` and `hevc_mf` with `hw_encoding=1` work, intra and gop15. The H.264 profile is Constrained Baseline (`pyav_functional_19.0.2.md`; `qsv_recheck_19.0.2.md`).
- measured: with the iGPU present, `h264_mf` lists both the NVIDIA and Intel QSV H.264 MFTs and logs "activate MFT 0" and "MFT name: 'NVIDIA H.264 Encoder MFT'" (`adapter_check_19.0.2.json`).
- measured: `av1_mf` picks "Intel® Hardware Accelerated AV1 Encoder MFT" and fails, both before the iGPU was present (`OSError ... -104 ... avcodec_send_frame()`, `pyav_functional_19.0.2.md`) and after (`InvalidDataError`, `qsv_recheck_19.0.2.md`).
- measured (new; iGPU present) - QSV encoders with software frames:

  | encoder | intra | gop15 | profile / pix_fmt |
  |---|---|---|---|
  | `h264_qsv` | 32 I | 3 I + 29 P | High / yuv420p |
  | `hevc_qsv` | 32 I | 3 I + 29 B | Main / yuv420p |
  | `vp9_qsv` | 32 I | 3 I + 29 P | Profile 0 / yuv420p |
  | `mjpeg_qsv` | 32 I | 32 I | Baseline / yuvj420p |

  Source: `results/gpu_encode/qsv_recheck_19.0.2.md`.
- measured: `av1_qsv` fails at open with "Current codec type is unsupported" and "some encoding parameters are not supported by the QSV runtime" (`qsv_recheck_19.0.2.md`).
- measured: every QSV encoder fails when given `HWAccel('qsv')`, with "Error initializing a child frames context / Error creating an internal frame pool" (`qsv_recheck_19.0.2.md`). From PyAV, QSV works only with software frames.
- measured: `hevc_qsv` gop15 output has ffprobe pict_type `B` for all 29 non-key frames. This happens with `max_b_frames=0`, and also with `gpb=0` (`results/gpu_encode/qsv_recheck2_19.0.2.json`). In every case ffprobe shows pts == dts for all packets, and `has_b_frames` is 0 (`results/gpu_encode/qsv_recheck2_ffprobe.txt`).
- inferred: these are low-delay B pictures that reference only past frames, with no reordering. NOT VERIFIED at slice level.
- measured: `h264/hevc/av1/ffv1_vulkan` are "not in av.codecs_available (not built into this wheel)" (`pyav_functional_19.0.2.md`).
- measured: all `*_amf` encoders fail (no AMD GPU) (`pyav_functional_19.0.2.md`).
- measured: `hwdevices_available` = cuda, dxva2, qsv, d3d11va, d3d12va, amf; there is no vulkan (`pyav_functional_19.0.2.md`, `qsv_recheck_19.0.2.md`).

### 2.3 PyAV 18 vs 19

- measured (PyAV 18 - background): with the iGPU absent, PyAV 18.0.0 and 19.0.2 give the same pass/fail result on every encoder and decoder row. There is one difference: `h264_nvenc` reports profile **Main** under PyAV 18 and **High** under PyAV 19, with the same script and options (`diff` of `pyav_functional_18.0.0.md` and `pyav_functional_19.0.2.md`). NOTES.md §1 said "identical"; that claim is corrected here.
- measured: libavcodec is 62.28.102 in PyAV 18.0.0 and 63.1.102 in PyAV 19.0.2 (headers of `pyav_functional_*.md`).
- measured: PyAV 19.0.2 adds no hardware encoder over 18.0.0 in any of the 6 PyPI wheels inspected (`results/gpu_encode/wheel_hw_codecs.md`; the two version blocks are identical).

### 2.4 NVENC session limit

- measured, PyAV 19.0.2: 12 `h264_nvenc` sessions opened, and the 13th failed at `avcodec_open2`. nvidia-smi showed `12` sessions while they were open and `0` before (`results/gpu_encode/nvenc_sessions_19.0.2.json`).
- measured, CLI reference: while those 12 sessions were held, one extra encode failed on each of `hevc_nvenc` ("OpenEncodeSessionEx failed: incompatible client key (21)"), `h264_vulkan`, `h264_d3d12va` and `h264_mf` (`nvenc_sessions_19.0.2.json`). So the four APIs share one pool.
- measured (PyAV 18 - background): same result, 12 opened and the 13th failed (`results/gpu_encode/nvenc_sessions.json`). The prior study also found "12 (20)" (`research/frame_ring_buffer/prototypes/results/p5_nvenc.md:7`).
- source: NVIDIA support matrix, every GeForce row: "Max # of concurrent sessions 12" (NOTES.md §7.1; https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new).

### 2.5 ffmpeg 9.0.2 CLI hardware encoders (CLI reference; run while the iGPU was absent)

Source for every bullet: `results/gpu_encode/ff_functional.md` / `.json`.

- measured: `h264_nvenc -g 1 -bf 0` fails with "InitializeEncoder failed: invalid param (8): Gop Length should be greater than number of B frames + 1". `-g 0` gives 32 I.
- code: `libavcodec/nvenc.c:1761-1767` @ n9.0.2: `gop_size == 0` gives the intra-only path (NOTES.md §3).
- measured: `h264_vulkan` (High) and `hevc_vulkan` (Main) work, intra and gop15.
- measured: `av1_vulkan` fails with "Device does not support encoding av1!".
- measured: `h264_d3d12va` works with `-bf 0`. With default B-frames, gop15 fails with "Encode failed: Unknown error occurred". Writing to `.mkv` fails with "Could not write header (incorrect codec parameters ?)".
- measured: `ffv1_vulkan` works on these inputs:
  - yuv420p 1080p with `-level 4 -strict -2`;
  - bgr0, intra;
  - bayer_rggb16le with `-level 4 -strict -2`.
- measured: the lossless round trip is byte-exact for all three (8/8 frames; bgr0 compared as gbrp) (`ff_functional.json` → `roundtrip`).
- measured: at level 3, `ffv1_vulkan` yuv420p fails with "Encoding frames with subsampling and unaligned dimensions is only supported in version 4 (-level 4)". bgr0 gop15 fails with "Using inter frames requires version 4 (-level 4)".
- measured: `ffv1_vulkan` gop15 gives 3 key packets out of 32, while ffprobe reports all 32 as pict_type I.
- inferred, from `ffv1enc_vulkan.c:279,289` (NOTES.md §3): the coder state carries over between key frames, so non-key packets are not independently decodable. Use gop 1 for crash tolerance and scrubbing.
- measured: `prores_ks_vulkan` works: 32 I, HQ, yuv422p10le.
- measured: file sizes on disk for 8 synthetic 16-bit Bayer frames: `diag/bayer_vk.mkv` (ffv1_vulkan) is 8,087,879 bytes and `diag/bayer_cpu.mkv` (CPU ffv1 defaults) is 17,047,238 bytes (`ls -l` of `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/gpu_encode/diag/`). The coder settings differ, so this is not a codec comparison. The CPU file's byte-exactness is NOT VERIFIED (no result file).

### 2.6 MJPEG (camera 4:2:2) decode on the GPU

- measured, PyAV 19.0.2: on 5 real 4:2:2 camera JPEGs (c930e 1080p and 720p), `mjpeg_cuvid` fails with "Generic error in an external library: 'avcodec_send_packet()'", and `mjpeg` + `HWAccel('cuda')` fails with "'avcodec_send_packet()' returned 22" (`pyav_functional_19.0.2.md`).
- NOT VERIFIED (no saved output): NOTES.md §5 says the CLI `mjpeg_cuvid` hangs on 4:2:2 input, that `-hwaccel cuda` silently falls back to the CPU, and that the same frames re-encoded as 4:2:0 decode on NVDEC. Commands are in section 7. The file `diag/j420.mjpeg` exists, but the console output was not saved.
- source: the NVDEC guide (SDK 13.0) lists "Hybrid (CUDA + CPU) JPEG" (NOTES.md §5; https://docs.nvidia.com/video-technologies/video-codec-sdk/13.0/nvdec-video-decoder-api-prog-guide/index.html).
- measured (new): the `mjpeg_qsv` decoder decodes the same 4:2:2 camera JPEGs, 5/5 frames per set. Its output format is **nv12**, i.e. 4:2:0 (`qsv_recheck_19.0.2.md`).
- measured: against the CPU `mjpeg` decoder, the Y-plane max |diff| is 21 for both sets, and the mean is 7.705 (1080p) and 8.297 (720p) (`qsv_recheck2_19.0.2.json`).
- inferred: a mean offset this large suggests a full-range vs limited-range difference (yuvj422p vs nv12), not decode error. NOT VERIFIED.
- measured: `mjpeg` + `HWAccel('qsv', allow_software_fallback=False)` returned `yuvj422p` software frames (`qsv_recheck_19.0.2.md`).
- inferred: this was CPU decode (no QSV hwaccel for the native mjpeg decoder). NOT VERIFIED.
- measured (nvImageCodec 0.10.0.9, not PyAV): `nvjpeg_cuda_decoder` decodes the 4:2:2 camera JPEGs into `STRIDED_DEVICE` buffers. Against ffmpeg's CPU decode, max/mean |diff| is 8/0.245 with PSNR 53.14 dB (1080p), and 25/0.179 with 54.18 dB (720p) (`results/gpu_encode/nvimgcodec_jpeg.json`).
- measured: in nvImageCodec, `backend:GPU_ONLY` and `HW_GPU_ONLY` fail with "Could not create decoder. Code: 7". Selecting `decoder_ids=["nvjpeg_cuda_decoder"]` works (`nvimgcodec_jpeg.json`).

### 2.7 GPU JPEG encode

- measured: on QSV (PyAV 19.0.2), `mjpeg_qsv` encodes NV12 input to Baseline yuvj420p (`qsv_recheck_19.0.2.md`). Encoding 4:2:2 output (from YUY2 input) was not tested.
- measured (nvImageCodec 0.10.0.9 / nvJPEG CUDA): q90 encode results from host RGB (1920×1080), with PSNR measured against the source RGB:

  | encoder | chroma | bytes | ffprobe pix_fmt | PSNR |
  |---|---|---|---|---|
  | nvjpeg_cuda_encoder | 4:2:2 | 144,880 | yuvj422p | 44.42 dB |
  | opencv_jpeg_encoder | 4:2:2 | 145,207 | yuvj422p | 47.25 dB |
  | nvjpeg_cuda_encoder | 4:2:0 | 133,516 | yuvj420p | 43.74 dB |
  | opencv_jpeg_encoder | 4:2:0 | 133,742 | yuvj420p | 46.16 dB |

  Source: `nvimgcodec_jpeg.json`.
- measured: a GPU-resident path works: GPU decode, then GPU encode with no host copy, giving 144,363 bytes, yuvj422p, 43.5 dB (`nvimgcodec_jpeg.json`).
- measured: nvImageCodec rejects YUV input (`P_YUV` / `I_YUV`: "encode returned None"). Gray input `P_Y` / `I_Y` is accepted and gives 109,135 bytes, `gray` (`nvimgcodec_jpeg.json`).
- measured: dropping unsynchronised GPU-decoded images printed 392 `CUDA error #700` lines in runs d1, d8 and dl1+d8, and 0 in dl1, eh1, ed1, ec1 and ed1+d8. All runs exited with code 0 (`results/gpu_encode/nvimgcodec_lifetime.json`).

### 2.8 Hardware encoders in the PyPI PyAV wheels

- measured, by static string search of the bundled libavcodec in each wheel, with sha256 checks; 19.0.2 and 18.0.0 are identical (`wheel_hw_codecs.md`):
  - win_amd64: NVENC h264/hevc/av1; QSV av1/vp9 (and h264/hevc/mjpeg short names); AMF av1; D3D12VA h264/hevc/av1; MF av1 (and h264/hevc).
  - win_arm64: D3D12VA h264/hevc/av1; MF av1 (and h264/hevc).
  - manylinux_2_28_x86_64: NVENC h264/hevc/av1; QSV av1/vp9; AMF av1; V4L2 m2m h264. No VAAPI and no Vulkan names.
  - manylinux_2_28_aarch64: V4L2 m2m H.264 only.
  - macOS arm64 / x86_64: VideoToolbox H.264, H.265 and ProRes encoders.
- source: pyav-ffmpeg `scripts/build-ffmpeg.py` @ 9.0.2-1, lines 188-203: `--enable-nvenc --enable-nvdec`, `--enable-amf`, `--enable-libvpl`, `--enable-videotoolbox`. There is no `--enable-vulkan` and no VAAPI flag (NOTES.md §4; https://github.com/PyAV-Org/pyav-ffmpeg/blob/9.0.2-1/scripts/build-ffmpeg.py).
- code: ffmpeg n9.0.2 `libavcodec/allcodecs.c:875,890,907` declares only h264, hevc and prores VideoToolbox encoders. No AV1 or VP9 VideoToolbox encoder exists (NOTES.md §7.4).

### 2.9 Vendor support, from primary sources (recorded in NOTES.md §7; not re-fetched here)

- source: NVIDIA support matrix (URL above). RTX 3070 / Ampere: AV1 4:2:0 encode "NO", H.264 4:2:2 and HEVC 4:2:2 encode "NO". RTX 4070 / Ada: AV1 "YES". RTX 5070 / Blackwell: AV1 "YES" and 4:2:2 "YES".
- source: Intel media-driver `intel-media-26.3.5`, `docs/media_features.md` lines 59-76. TGLx (TGL, RKL, ADL, RPL): AVC, HEVC, VP9 and JPEG encode, with the AV1 cell blank. DG2, MTL/ARL, LNL/BMG and PTL/NVL have AV1 encode. BMG and LNL have VP9 blank (https://github.com/intel/media-driver/blob/intel-media-26.3.5/docs/media_features.md).
- measured, consistent with that table for RPL-S on Windows: vp9_qsv, mjpeg_qsv, h264_qsv and hevc_qsv encode, while av1_qsv is "unsupported" (`qsv_recheck_19.0.2.md`). This partly settles NOTES' "NOT VERIFIED that the Windows driver exposes the same matrix", for RPL-S and these 5 codecs.
- source: AMD RX 7600 (RDNA 3) spec page: "AV1 Encode Yes". The RX 6600 page has no AV1 Encode row (NOTES.md §7.3).
- source: Apple M5 and M2 MacBook specs: hardware-accelerated "H.264, HEVC, ProRes, and ProRes RAW" encode, plus "AV1 decode" on M5 (NOTES.md §7.4).

## 3. Comparison tables

### 3.1 Hardware encode on Gerald through PyAV 19.0.2 (functional only)

Source: `pyav_functional_19.0.2.md`, `qsv_recheck_19.0.2.md`, `adapter_check_19.0.2.json`.

| encoder | device | sw frames | HWAccel ctx | intra | gop15 | codec class |
|---|---|---|---|---|---|---|
| h264_nvenc / hevc_nvenc | RTX 3070 | yes | yes (cuda) | yes (`gop_size=0`) | yes | H.264/HEVC (G7: avoid) |
| h264_d3d12va / hevc_d3d12va | RTX 3070 (default device) | no (err 22) | yes (d3d12va) | yes | yes | H.264/HEVC |
| h264_mf / hevc_mf | NVIDIA MFT (MFT 0) | yes | n/a | yes | yes | H.264/HEVC |
| h264_qsv / hevc_qsv | UHD 770 | yes | no (frame pool) | yes | yes (HEVC: low-delay B) | H.264/HEVC |
| **vp9_qsv** | UHD 770 | yes | no | yes | yes | VP9 (G7 candidate; licence per licensing topic) |
| **mjpeg_qsv** | UHD 770 | yes (4:2:0 out) | no | yes | n/a | JPEG (licence per licensing topic) |
| av1_nvenc / av1_d3d12va / av1_mf / av1_qsv | - | no | no | - | - | AV1: no hardware on Gerald |
| *_vulkan, ffv1_vulkan, prores_ks_vulkan | - | not in wheel | not in wheel | - | - | - |

### 3.2 GPU/royalty-free paths outside PyPI PyAV (measured on Gerald)

| path | how reached | measured result |
|---|---|---|
| ffv1_vulkan (lossless) | ffmpeg CLI 9.0.2 (no PyAV binding) | byte-exact for yuv420p (L4), bgr0, Bayer RGGB16 (`ff_functional.json`) |
| prores_ks_vulkan | ffmpeg CLI | works, HQ 4:2:2 10-bit (`ff_functional.md`) |
| nvJPEG encode/decode | nvImageCodec 0.10.0.9 (CUDA, NVIDIA only) | 4:2:2/4:2:0/gray encode; 4:2:2 decode to device (`nvimgcodec_jpeg.json`) |

### 3.3 Decode of camera 4:2:2 MJPEG

| decoder | result | output | evidence |
|---|---|---|---|
| mjpeg (CPU) | ok | yuvj422p | `qsv_recheck_19.0.2.md` |
| mjpeg_cuvid (PyAV 19) | fails | - | `pyav_functional_19.0.2.md` |
| mjpeg + HWAccel cuda (PyAV 19) | fails | - | `pyav_functional_19.0.2.md` |
| mjpeg_qsv (PyAV 19) | ok, 5/5 | nv12 (chroma reduced to 4:2:0) | `qsv_recheck_19.0.2.md` |
| nvImageCodec nvjpeg_cuda_decoder | ok | RGB device buffer | `nvimgcodec_jpeg.json` |

### 3.4 Hardware encode of codecs other than H.264/HEVC, by platform

Rows come from sources in 2.9 unless marked measured.

| platform | AV1 HW enc | VP9 HW enc | JPEG HW enc | in PyPI PyAV wheel |
|---|---|---|---|---|
| NVIDIA Turing/Ampere (RTX 2000/3000) | no (source) | no VP9 column in the NVENC matrix | nvJPEG via CUDA (measured, Ampere; not PyAV) | NVENC h264/hevc only usable |
| NVIDIA Ada/Blackwell | yes (source) | no | NOT VERIFIED | av1_nvenc compiled in (Win, Linux x64) |
| Intel TGL-RPL iGPU (11th-14th gen) | no (source; measured on RPL-S) | yes (source; **measured on RPL-S via PyAV 19**) | yes (source; **measured mjpeg_qsv**) | vp9_qsv / mjpeg_qsv (Win, Linux x64) |
| Intel Arc / MTL / ARL / LNL / BMG | yes (source) | yes, except LNL/BMG (source) | yes (source) | av1_qsv compiled in |
| AMD RDNA3 | yes (source, RX 7600) | NOT VERIFIED | NOT VERIFIED | av1_amf compiled in |
| AMD RDNA2 / Zen APUs | no AV1 row on the RX 6600 page | NOT VERIFIED | NOT VERIFIED | - |
| Apple silicon | no (source; no ffmpeg encoder, code) | no | NOT VERIFIED | VideoToolbox h264/hevc/prores only |
| CPU with no iGPU / no supported GPU | software only | software only | software only | libsvtav1, libvpx-vp9 names present (`wheel_hw_codecs.md`) |

## 4. Implications for the plan

- I1 (from 2.2, 3.4): through PyPI PyAV on Gerald, **vp9_qsv is the only working hardware encoder for a lossy codec other than H.264/HEVC**. According to the Intel media-driver source, it covers Intel iGPUs from TGL to RPL plus MTL/ARL/Arc. It does not cover NVIDIA, Apple, or Intel LNL/BMG.
- I2 (from 2.9, 3.4): the target "hardware-accelerated on RTX 3000 and newer" cannot be met by any lossy codec other than H.264/HEVC. Ampere NVENC has no AV1 or VP9 encode (source). On RTX 3000, only H.264/HEVC (NVENC) or GPU JPEG via nvJPEG (CUDA, a separate library from PyAV) are accelerated. The plan must state this trade-off against G7 openly.
- I3 (from 2.2): QSV from PyAV works only with software frames (`HWAccel('qsv')` fails). Any QSV design pays a host-to-iGPU upload inside the encoder. Its cost is pending (B-QSV in section 5).
- I4 (from 2.2, 2.7): `mjpeg_qsv` gives hardware JPEG encode for G4 raw inputs (NV12, and YUY2 after conversion). Its output from NV12 is 4:2:0; 4:2:2 output is untested.
- I5 (from 2.4): NVENC, Vulkan Video, D3D12 and MF all draw from one 12-session pool on a GeForce card. A 16-camera rig cannot use one session per camera on one GeForce GPU, whichever API is used. Whether QSV has a separate pool is NOT TESTED.
- I6 (from 2.2, 2.5): per-encoder intra settings must be explicit:
  - NVENC: `gop_size=0`; 1 is rejected.
  - QSV: `gop_size=1` works.
  - D3D12: needs `HWAccel('d3d12va')` and `max_b_frames=0`. Its MKV header write failed in the CLI; D3D12 to MKV through PyAV is untested.
- I7 (from 2.2): `hevc_qsv` gop15 emits B pictures even with `max_b_frames=0` and `gpb=0`, though without reordering. Frame-accurate seek of these files in Chromium (G9) has to be checked by the chromium topics. Intra-only avoids the question.
- I8 (from 2.6): GPU decode of the cameras' 4:2:2 MJPEG cannot use NVDEC through PyAV. `mjpeg_qsv` decodes it but reduces chroma to 4:2:0, and nvJPEG decodes it at full 4:2:2. For G1 this matters only for previews or overlays, since archival is passthrough.
- I9 (from 2.3): PyAV 19.0.2 brings no new hardware encoder over 18.0.0. Choose it for other reasons. Note that the default `h264_nvenc` profile changed from Main to High.
- I10 (from 2.2, 2.5): `ffv1_vulkan` (royalty-free lossless on the GPU, byte-exact incl. Bayer) and `prores_ks_vulkan` cannot be reached from PyPI PyAV. They need a CLI subprocess or a custom FFmpeg/PyAV build with `--enable-vulkan`. This belongs in the standard FFmpeg vs custom-build trade-off.
- I11 (from 2.2), inferred: on a dual-GPU machine, D3D12 and MF chose the NVIDIA device on Gerald, but default adapter choice is machine-dependent. The recorder should allow explicit device selection.

## 5. Pending tonight's bench

Timed questions; `bench_manifest` ids come from `results/bench_queue_from_wf_2e122ed0.json` → `gpu_encode`.

| timed question | manifest id | needs fixing before the run |
|---|---|---|
| Single-stream fps and CPU cost per GPU encoder, 720p/1080p, intra/gop15, from NV12 and from MJPEG | B1a | Runs through the **ffmpeg CLI** (`bench_ffmpeg_encode.py` docstring). Under requirement 5 the results are CLI reference only. Port to PyAV 19.0.2, or label them so |
| CPU reference encoders (libsvtav1, libvpx-vp9, mjpeg, ffv1), same matrix | B1b | same CLI caveat |
| Concurrent scaling 1-16 streams, h264_nvenc 1080p, unpaced and paced 30 fps (late frames, p99) | B2a | Manifest command uses `.venv` (PyAV 18). Use `uv run --script` (script header pins av 19.0.2) |
| Same, hevc_nvenc 1080p | B2b | same |
| Same, h264_d3d12va 1080p | B2c | same |
| Same, h264_nvenc 720p | B2d | same |
| numpy to frame / swscale / upload / encode-call cost | B3b (keep); B3a (drop: PyAV 18) | - |
| GPU JPEG decode/encode throughput vs CPU (nvImageCodec) | B4 | - |
| Session limit on a quiet machine | B5 | Already answered functionally under PyAV 19.0.2 (`nvenc_sessions_19.0.2.json`: 12). Optional |
| B2a under PyAV 19 | B2e | redundant once B2a runs on 19 |
| **QSV** per-stream fps and CPU (h264/hevc/vp9/mjpeg_qsv, software frames), 720p/1080p, NV12/YUY2 and MJPEG input; stream scaling | none (B-QSV, to be added by hw_accel_target) | `bench_pyav_concurrent.py` / `bench_ffmpeg_encode.py` contain no `qsv` entries. Must use software frames (I3) |
| mjpeg_qsv vs nvJPEG vs CPU JPEG encode cost for G4 raw input | none (add) | - |

## 6. Not tested / limits / NOT VERIFIED

- Only NVIDIA Ampere and the Intel RPL-S iGPU were tested physically. Every Ada/Blackwell, Arc, AMD and Apple row comes from documents.
- AV1 hardware encode through PyAV (av1_nvenc / av1_qsv / av1_amf / av1_d3d12va) on capable GPUs: NOT TESTED (no hardware).
- QSV session or concurrency limit; whether QSV runs alongside 12 NVENC sessions: NOT TESTED.
- QSV with YUY2 input, 4:2:2 or 10-bit output, and PyAV QSV to MKV/MP4 playback in Chromium: NOT TESTED.
- Why `HWAccel('qsv')` frame-pool creation fails in PyAV: root cause unknown.
- `mjpeg_qsv` decode accuracy: the Y offset is unexplained (range is suspected, NOT VERIFIED). Chroma was not compared.
- CLI `mjpeg_cuvid` hang and `-hwaccel cuda` silent fallback: NOT VERIFIED (no saved output; NOTES.md §5 only).
- D3D12 MKV header failure and default-B-frame failure: whether these are FFmpeg bugs or driver limits is NOT VERIFIED. D3D12 to MKV through PyAV is NOT TESTED.
- `ffv1_vulkan` on AMD, Intel or MoltenVK: NOT VERIFIED.
- A GPU-resident path from nvJPEG output to NVENC in Python: NOT TESTED. PyAV wrapping external CUDA pointers is inferred to be unsupported, also NOT TESTED.
- `torchvision.io.encode_jpeg` on CUDA: NOT TESTED.
- Root cause of nvImageCodec CUDA error 700: unknown.
- Vendor sources were quoted by the investigator (NOTES.md §7) and not re-fetched for this write-up. Jellyfin per-generation claims belong to `hw_accel_target`.
- Royalty and licence status of VP9, AV1, JPEG, FFV1 and ProRes: not asserted here (licensing topic).
- Functional encodes are 32 frames (8 real 1080p frames looped). The Bayer input is synthetic.
- Other agents and Parsec/Sunshine processes were running during these checks. nvidia-smi showed 1 foreign NVENC session before the original PyAV 19 run (`pyav_functional_19.0.2.md`) and 0 before the session-limit re-check.

## 7. How to reproduce (repo root `C:/Users/Dom/GitHub/freemocap/skellycam`)

```
# PyAV 19.0.2 functional matrix (NVENC/D3D12/MF/QSV/AMF/Vulkan + MJPEG GPU decode)
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/pyav_functional.py
# QSV / MF re-check with the iGPU present -> results/gpu_encode/qsv_recheck_19.0.2.{json,md}
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/qsv_recheck.py
# hevc_qsv gpb + mjpeg_qsv decode accuracy -> results/gpu_encode/qsv_recheck2_19.0.2.json
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/qsv_recheck2.py
# default D3D12 device / selected MFT -> results/gpu_encode/adapter_check_19.0.2.json
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/adapter_check.py
# NVENC session limit under PyAV 19.0.2 -> results/gpu_encode/nvenc_sessions_19.0.2.json
uv run --no-project --with av==19.0.2 --with numpy==2.2.6 python research/skellycam_recording/recording_upgrade/scripts/gpu_encode/nvenc_sessions_versioned.py --max 16
# packet order inspection (ffprobe, inspection only), in the media dir .../gpu_encode/qsv_recheck_19.0.2/
ffprobe -v error -select_streams v:0 -show_entries packet=pts,dts,flags -of csv=p=0 hevc_qsv_gop15_gpb0.mkv
ffprobe -v error -select_streams v:0 -show_entries stream=has_b_frames -of csv=p=0 hevc_qsv_gop15_gpb0.mkv
# wheel inspection (static, downloads wheels to scratchpad)
.venv/Scripts/python.exe -I research/skellycam_recording/recording_upgrade/scripts/gpu_encode/wheel_hw_codecs.py 19.0.2 18.0.0
# GPU JPEG (nvImageCodec 0.10.0.9) and buffer lifetime
uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/nvimgcodec_jpeg.py
python research/skellycam_recording/recording_upgrade/scripts/gpu_encode/nvimgcodec_lifetime_run.py
# CLI reference matrix (ffmpeg 9.0.2 on PATH; reference only)
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/gpu_encode/ff_functional.py
# NVDEC 4:2:2 checks from NOTES.md section 5 (run in the media dir .../gpu_encode/; output not saved previously)
ffmpeg -v verbose -c:v mjpeg_cuvid -i inputs/mjpeg_1080p.mjpeg -f null -
ffmpeg -v verbose -hwaccel cuda -hwaccel_output_format cuda -i inputs/mjpeg_1080p.mjpeg -f null -
# iGPU presence (read-only)
powershell -NoProfile -Command "Get-PnpDevice -Class Display | ft Status,Present,FriendlyName"
```

Media from these runs goes to `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/gpu_encode/` (subfolders `qsv_recheck_19.0.2/`, `pyav_19.0.2/`, `ff_functional/`, `diag/`, `nvimgcodec/`).
