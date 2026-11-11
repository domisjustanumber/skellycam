# gpu_encode: GPU-accelerated encode (G6) and royalty-free codecs (G7)

Stage: functional tests and primary sources only. No timing, throughput or CPU numbers from this stage (other
agents were running). Timing scripts were written, smoke-tested on tiny runs (outputs deleted), and are listed in
the benchmark manifest at the end.

Labels: **measured** (result file from this study or a prior study), **source** (primary source, accessed
2026-11-09), **code** (repo file:line), **inferred** (reasoning, kept short). Paths are relative to the repo root.
Media outputs are in `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/gpu_encode/`,
outside the repo.

## 1. Bottom line

- measured: on Gerald, no hardware **AV1 or VP9** encoder opens, through any API (NVENC, D3D12, Vulkan Video, MediaFoundation, QSV, AMF). See `ff_functional.md` and `pyav_functional_*.md`.
- source: the RTX 3070 (Ampere) has no AV1 encode. In the NVIDIA support matrix row, the last column (AV1 YUV 4:2:0) is "NO", while Ada and Blackwell rows show "YES" (§7.1).
- measured: the only **royalty-free codecs that run on the GPU on Gerald** are:
  - `ffv1_vulkan` (lossless FFV1 on Vulkan compute; byte-exact round trip for 4:2:0, RGB and 16-bit Bayer);
  - JPEG encode and decode via nvJPEG (CUDA) in nvImageCodec.
- measured: `prores_ks_vulkan` also works on the GPU. ProRes's licence status belongs to the licensing topic.
- measured: hardware H.264 and HEVC encode works, all-intra and with a short GOP, via 4 APIs: `*_nvenc`, `*_vulkan`, `*_d3d12va` and `*_mf` (the NVIDIA MFT).
- measured: all of those APIs share one pool of **12 NVENC sessions** on driver 610.88. While 12 PyAV `h264_nvenc` sessions were held open, a 13th failed, and so did one extra `hevc_nvenc`, `h264_vulkan`, `h264_d3d12va` and `h264_mf` encode (`nvenc_sessions.json`).
- measured: the cameras' **4:2:2 MJPEG cannot be decoded by NVDEC**:
  - `mjpeg_cuvid` and `-hwaccel cuda` both fail on the corpus JPEGs;
  - `-hwaccel cuda` silently falls back to the CPU;
  - the same frames re-encoded as 4:2:0 decode fine.
  - nvJPEG (CUDA) does decode the 4:2:2 camera JPEGs.
- measured: **PyAV 19.0.2 and PyAV 18.0.0 behave identically** for every hardware encoder and decoder tested on Gerald. Neither PyPI wheel contains any Vulkan encoder, so `ffv1_vulkan` and `av1_vulkan` are not usable from PyAV. Bumping PyAV gives no new GPU-encode capability (§4).
- inferred: for MJPEG cameras (G1), passthrough needs no encoder at all. GPU encode matters for G4 inputs: raw YUY2, NV12 or Bayer.
  - On Gerald today, the royalty-free GPU option is `ffv1_vulkan`, run via the ffmpeg CLI or a custom FFmpeg build.
  - Lossy royalty-free hardware encode (AV1) needs NVIDIA Ada/Blackwell, Intel Arc/MTL or newer, or AMD RDNA3 hardware (§7).

## 2. Machine facts (read-only probes)

Raw output: `results/gpu_encode/system_probe.txt`.

- measured: `Get-PnpDevice -Class Display` lists `Intel(R) UHD Graphics 770` (PCI\VEN_8086&DEV_A780) with:
  - Status `Unknown`, Present `False`, Problem `CM_PROB_PHANTOM`;
  - driver 32.0.101.7088 installed, LastArrivalDate 2026-11-07.
  - So the iGPU is known to Windows but not currently present, which is why `Win32_VideoController` omits it. Nothing was changed.
- measured: every QSV encoder fails at device creation: `Failed to find d3d11va adapter by vendor id 0x8086` (`ff_functional.md`).
- measured: `av1_mf -hw_encoding 1` picks `Intel(R) Hardware Accelerated AV1 Encoder MFT`, which the Intel driver registered, then fails with `could not start streaming (80004005)`.
- source: Intel media-driver `intel-media-26.3.5` README, "Supported Platforms": "TGLx (TGL: Tiger Lake, RKL: Rocket Lake, ADL-S/P/N: Alder Lake, RPL-S/P: Raptor Lake)". https://github.com/intel/media-driver/blob/intel-media-26.3.5/README.md
- source: in `docs/media_features.md` at the same tag (lines 59-76), the TGLx column has AVC, JPEG, HEVC and VP9 encode, and its AV1 8bit cell is empty.
- inferred: the i7-14700K iGPU (RPL-S) would give VP9, JPEG, H.264 and HEVC hardware encode if it were present, but not AV1. NOT VERIFIED on this machine, because making the iGPU present needs a BIOS or display change, which is out of scope.
- measured: `nvidia-smi`: RTX 3070, driver 610.88, compute capability 8.6. The session count was 0 before most tests. It was 1 before the PyAV 19 run, from another process.
- measured: Vulkan device 0 is the RTX 3070. The video extensions ffmpeg enabled were:
  - `VK_KHR_video_encode_queue`, `_encode_h264`, `_encode_h265`;
  - decode h264/h265/vp9/av1.
  - No `VK_KHR_video_encode_av1`.

## 3. ffmpeg 9.0.2 CLI: every hardware encoder

Script: `scripts/gpu_encode/ff_functional.py`. Results: `ff_functional.{md,json}`.

Input: 8 real 1080p frames (c930e YUY2 converted to NV12, 4:2:0, 4:2:2 10-bit, BGR0 or synthetic RGGB16 by swscale), looped to 32 frames. Each output was checked with ffprobe: packets, key packets, decoded frames, and pict_type counts.

| encoder | all-intra | gop15 (no B) | outcome on Gerald (measured) |
|---|---|---|---|
| h264_nvenc / hevc_nvenc | yes, 32 I | yes, 3 I + 29 P | works. Intra needs `-g 0`; `-g 1` fails, see below |
| av1_nvenc | no | no | `Codec not supported` / `No capable devices found` |
| h264_vulkan / hevc_vulkan | yes, 32 I | yes, 3 I + 29 P | works (Vulkan Video on NVIDIA). H.264 High, HEVC Main |
| av1_vulkan | no | no | `Device does not support encoding av1!` |
| h264_d3d12va / hevc_d3d12va | yes (MP4) | yes (MP4, `-bf 0`) | works with `-bf 0`. Default B-frames fail mid-stream (`Encode failed`). MKV header write fails (see below) |
| av1_d3d12va | no | no | `Driver does not support requested features ... Codec configuration not supported` |
| h264_mf / hevc_mf (`-hw_encoding 1`) | yes, 32 I | yes, 3 I + 29 P | works via `NVIDIA H.264 Encoder MFT`. H.264 comes out as Constrained Baseline |
| av1_mf | no | no | picks the Intel AV1 MFT (iGPU not present): `could not start streaming (80004005)` |
| *_qsv (h264, hevc, av1, vp9, mjpeg) | no | no | `Failed to find d3d11va adapter by vendor id 0x8086` |
| *_amf (h264, hevc, av1) | no | no | `DLL amfrt64.dll failed to open` (no AMD GPU) |
| ffv1_vulkan (yuv420p, `-level 4 -strict -2`) | yes | yes (see note) | works. Byte-exact round trip on 8 frames |
| ffv1_vulkan (bgr0, level 3) | yes | no | works intra. Byte-exact (compared as gbrp). gop>1 needs level 4 |
| ffv1_vulkan (bayer_rggb16le, `-level 4 -strict -2`) | yes | yes | works. Byte-exact round trip (synthetic Bayer, see `common.py`) |
| ffv1_vulkan (yuv420p, level 3) | no | no | `Encoding frames with subsampling and unaligned dimensions is only supported in version 4 (-level 4)` |
| prores_ks_vulkan (yuv422p10le) | yes, 32 I | n/a (intra codec) | works. Profile HQ |
| av1_vaapi / h264_vaapi | no | no | `Failed to initialise VAAPI connection` (Linux-only API) |

Configuration findings:

- measured: `h264_nvenc -g 1 -bf 0` fails with `InitializeEncoder failed: invalid param (8): Gop Length should be greater than number of B frames + 1`. `-g 0` gives 32/32 I frames, and so does `-force_key_frames expr:1 -forced-idr 1`.
- code: in ffmpeg n9.0.2 `libavcodec/nvenc.c:1761-1767`, `gop_size == 0` sets `frameIntervalP = 0; gopLength = 1`, which is the intra-only path. `gop_size > 0` copies the value into `gopLength`. https://github.com/FFmpeg/FFmpeg/blob/n9.0.2/libavcodec/nvenc.c
- measured: `h264_d3d12va` to `.mkv` fails with `Could not write header (incorrect codec parameters ?): Invalid data found when processing input`. MP4 and raw Annex-B work.
- measured: adding `-bsf:v dump_extra -flags -global_header` made ffmpeg segfault (exit 139).
- measured: `h264_d3d12va` with default settings logs `Using intra, P- and B-frames` and then `Encode failed: Unknown error occurred` after 12 input frames. With `-bf 0` it works.
- code: `libavcodec/ffv1enc_vulkan.c` @ n9.0.2:
  - lines 1297-1300 contain "Using inter frames requires version 4 (-level 4)";
  - lines 1302-1305 contain "Version 4 is experimental and requires -strict -2";
  - lines 1343-1350: subsampled input needs width and height divisible by 64<<shift at version 3. 1080 is not divisible by 128.
- code: `libavcodec/ffv1enc.c:921-928` @ n9.0.2: FFV1 Bayer is only `AV_PIX_FMT_BAYER_RGGB16`, and it forces version 4.
- inferred, from `ffv1enc_vulkan.c:279,289`: ffv1_vulkan "gop15" keeps the coder state across frames between key frames (3 key packets out of 32), so non-key frames are not independently decodable. For crash tolerance and scrubbing, use `-g 1`.
- measured: the 16-bit Bayer test file was 8,087,879 bytes from ffv1_vulkan and 17,047,238 bytes from CPU `ffv1` defaults, for the same 8 frames. Both were byte-exact. This is a size observation, not a recommendation; the coder settings differ. Files: `skellycam-raw/.../gpu_encode/diag/bayer_{vk,cpu}.mkv`.

## 4. PyAV 18.0.0 (skellycam venv) and PyAV 19.0.2 (isolated uv env)

Script: `scripts/gpu_encode/pyav_functional.py`, using the same file for both versions. Results: `pyav_functional_18.0.0.{md,json}` and `pyav_functional_19.0.2.{md,json}`.

The script encodes 32 frames from numpy NV12 with `VideoFrame.from_ndarray`, in two ways: plain software frames, and `add_stream(..., hwaccel=HWAccel(type))`, where PyAV builds the hw frames context and uploads.

| encoder | sw frames | HWAccel ctx | PyAV 18 = PyAV 19? |
|---|---|---|---|
| h264_nvenc, hevc_nvenc | intra and gop15 OK (`gop_size=0` for intra) | intra and gop15 OK (cuda) | identical |
| h264_mf, hevc_mf (`hw_encoding=1`) | OK | n/a | identical |
| h264_d3d12va, hevc_d3d12va | fail: `avcodec_open2(...) returned 22` | intra and gop15 OK (d3d12va) | identical |
| av1_nvenc / av1_d3d12va / av1_mf | fail (as in the CLI) | fail | identical |
| *_qsv, *_amf | fail (no device) | fail | identical |
| h264/hevc/av1/ffv1 `_vulkan` | not in wheel | not in wheel | identical |
| decode: mjpeg_cuvid, mjpeg + HWAccel(cuda) on camera JPEGs | fail (`avcodec_send_packet()`) | fail | identical |

- measured: PyAV 18.0.0 uses libavcodec 62.28.102. PyAV 19.0.2 uses libavcodec 63.1.102, the same as the ffmpeg 9.0.2 CLI.
- measured: both report `hwdevices_available` = cuda, dxva2, qsv, d3d11va, d3d12va, amf. There is no vulkan.
- source: PyAV `scripts/ffmpeg-latest.json` points to the pinned pyav-ffmpeg build:
  - at tag v18.0.0: `.../pyav-ffmpeg/releases/download/8.1.2-1/ffmpeg-{platform}.tar.gz`;
  - at tag v19.0.2: `.../9.0.2-1/...`.
  - https://github.com/PyAV-Org/PyAV/blob/v19.0.2/scripts/ffmpeg-latest.json
- source: pyav-ffmpeg `scripts/build-ffmpeg.py` @ 9.0.2-1:
  - lines 97-104 contain "use_cuda = plat in {"Linux", "Windows"} and not is_arm", plus the same rules for AMF and libvpl;
  - lines 165-167 contain `--enable-mediafoundation` (Windows only);
  - lines 188-203: `--enable-nvenc --enable-nvdec`, `--enable-amf`, `--enable-libvpl`, and `--enable-videotoolbox` (Darwin);
  - no `--enable-vulkan` and no vaapi flag.
  - https://github.com/PyAV-Org/pyav-ffmpeg/blob/9.0.2-1/scripts/build-ffmpeg.py
  - The build script at the 8.1.2-1 tag could not be fetched (NOT VERIFIED for 18). The wheel inspection below covers it.
- code: PyAV 18 encodes with hw frames by calling `av_hwframe_get_buffer` and `av_hwframe_transfer_data` on a frame context it builds before open (`.venv/Lib/site-packages/av/codec/context.py:386-436`, `av/video/codeccontext.py:115-117`).

### Hardware encoders shipped in the PyPI wheels, per OS

Script: `scripts/gpu_encode/wheel_hw_codecs.py`. Results: `wheel_hw_codecs.{md,json}`. Each wheel was downloaded from PyPI, checked against its sha256, and its bundled libavcodec searched for encoder `CODEC_LONG_NAME` strings. Short names were not enough, because they are shared with hwaccel decoders. On win_amd64 the method agrees with `av.codecs_available`.

| wheel (av 19.0.2 and 18.0.0 identical) | hardware ENCODERS compiled in (measured) |
|---|---|
| win_amd64 | NVENC h264/hevc/av1; QSV av1/vp9 (+h264/hevc/mjpeg short names); AMF av1 (+h264/hevc); D3D12VA h264/hevc/av1; MF av1 (+h264/hevc) |
| win_arm64 | D3D12VA h264/hevc/av1; MF av1 (+h264/hevc). No NVENC, QSV or AMF |
| manylinux_2_28_x86_64 | NVENC h264/hevc/av1; QSV av1/vp9; AMF av1; V4L2 m2m h264. **No VAAPI, no Vulkan** |
| manylinux_2_28_aarch64 | V4L2 m2m h264 only |
| macosx arm64 / x86_64 | VideoToolbox H.264, H.265, ProRes. No AV1/VP9 encoder (none exists, §7.4) |

## 5. MJPEG input: decode on the GPU

- measured: `ffmpeg -c:v mjpeg_cuvid` on the corpus 1080p JPEGs (4:2:2) negotiates `nv16` and then fails with `cuvidCreateDecoder ... failed -> CUDA_ERROR_NO_DEVICE`, followed by `CUDA_ERROR_INVALID_HANDLE` per frame. The process **did not exit within 120 s** and was stopped.
- measured: `-hwaccel cuda` with the native mjpeg decoder reports `NVDEC capabilities: format supported: yes`, then `Failed setup for format cuda: hwaccel initialisation returned error`, then decodes all 19 frames **on the CPU** with exit code 0.
- measured: the same frames re-encoded as 4:2:0 JPEG decode fine with both `mjpeg_cuvid` and `-hwaccel cuda`. The diag output is in skellycam-raw `gpu_encode/diag/j420.mjpeg`. Commands, run in the media dir `gpu_encode/`:
  - `ffmpeg -v verbose -c:v mjpeg_cuvid -i inputs/mjpeg_1080p.mjpeg -f null -` (4:2:2: fails and hangs);
  - `ffmpeg -v verbose -hwaccel cuda -hwaccel_output_format cuda -i inputs/mjpeg_1080p.mjpeg -f null -` (4:2:2: falls back to CPU);
  - `ffmpeg -i inputs/mjpeg_1080p.mjpeg -frames:v 3 -pix_fmt yuvj420p -c:v mjpeg -q:v 3 diag/j420.mjpeg`, then the two decode commands above on `diag/j420.mjpeg`: both exit 0.
- source: NVDEC Video Decoder API Programming Guide (Video Codec SDK 13.0) lists, among supported codecs, "Hybrid (CUDA + CPU) JPEG". So JPEG on NVDEC is not a fixed-function decoder. https://docs.nvidia.com/video-technologies/video-codec-sdk/13.0/nvdec-video-decoder-api-prog-guide/index.html
- source: the NVIDIA support matrix NVDEC table has no JPEG column (§7.1).
- measured: nvImageCodec `nvjpeg_cuda_decoder` decodes the camera 4:2:2 JPEGs into GPU memory (`STRIDED_DEVICE`). Against ffmpeg's CPU decode, max |diff| was 8 (1080p) and 25 (720p), with PSNR 53.1 / 54.2 dB. The differences come from different upsampling and IDCT (`nvimgcodec_jpeg.md`).

## 6. GPU JPEG encode from Python: nvImageCodec

Env: `nvidia-nvimgcodec-cu12[nvjpeg]==0.10.0.9`, which pulled `nvidia-nvjpeg-cu12==12.4.0.76`, plus `numpy==2.2.6`, via `uv run --script`. Script: `scripts/gpu_encode/nvimgcodec_jpeg.py`. Results: `nvimgcodec_jpeg.{md,json}`.

- measured: `nvjpeg_cuda_encoder` works for these inputs:
  - host numpy RGB with CSS_422, giving a `yuvj422p` JPEG per ffprobe;
  - host numpy RGB with CSS_420, giving `yuvj420p`;
  - GPU-resident images straight from the GPU decoder, with no host round trip;
  - single-channel gray (P_Y / I_Y gives `gray`), which is usable for Bayer-as-gray or mono cameras.
- measured: YUV input (P_YUV / I_YUV) is rejected. `encode` returns None.
- measured: selecting `backends=[Backend(GPU_ONLY)]` or `HW_GPU_ONLY` alone fails with `Could not create encoder/decoder. Code: 7`.
  - Selecting the implementation id works: `encoder_ids=["nvjpeg_cuda_encoder"]` / `decoder_ids=["nvjpeg_cuda_decoder"]`.
  - `get_decoder_ids()` lists no hardware JPEG decoder id on this GeForce.
- measured: dropping GPU-decoded images without synchronising (no `.cpu()` and no later GPU consumer) produced 392 `CUDA error #700` log lines per run. The process still exited with code 0 (`nvimgcodec_lifetime.json`, scripts `nvimg_life.py` and `nvimgcodec_lifetime_run.py`). Code that uses the GPU decoder must keep results alive until it synchronises; the benchmark does.
- measured: a uv env named after a long script file name failed with `DLL load failed ... The filename or extension is too long`, so the probe script is named `nvimg_life.py`.
- NOT TESTED: `torchvision.io.encode_jpeg` on CUDA. On Windows, PyPI torch 2.15.0 has no CUDA dependency (source: PyPI JSON `requires_dist` lists CUDA packages only for `platform_system == "Linux"`), and the CUDA build is a multi-GB download from the PyTorch index. inferred: it would also use nvJPEG.

## 7. Cross-platform hardware encode support (primary sources only)

### 7.1 NVIDIA

Source: NVIDIA "Video Encode and Decode GPU Support Matrix", https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new (saved HTML parsed in the scratchpad).

The NVENC table columns are: BOARD | FAMILY | NVENC Generation | Desktop/Mobile | # OF CHIPS | Total # of NVENC | Max # of concurrent sessions | H.264 4:2:0 | H.264 4:2:2 | H.264 4:4:4 | H.264 Lossless | HEVC 4K 4:2:0 | HEVC 4:2:2 | HEVC 4K 4:4:4 | HEVC 4K Lossless | HEVC 8K | HEVC 10-bit | HEVC B-frame | AV1 4:2:0.

| row (verbatim values) | AV1 enc | 4:2:2 enc | max concurrent sessions |
|---|---|---|---|
| GeForce GTX 1080 / Pascal / 6th Gen / D/M / 1 / 2 / 12 / YES NO YES YES YES NO YES YES YES YES NO NO | NO | NO | 12 |
| GeForce RTX 2080 / Turing / 7th Gen / D/M / 1 / 1 / 12 / YES NO YES YES YES NO YES YES YES YES YES NO | NO | NO | 12 |
| GeForce RTX 3070 / Ampere / 7th Gen / D / 1 / 1 / 12 / YES NO YES YES YES NO YES YES YES YES YES NO | NO | NO | 12 |
| GeForce RTX 4070 / Ada Lovelace / 8th Gen / D / 1 / 1 / 12 / YES NO YES YES YES NO YES YES YES YES YES YES | YES | NO | 12 |
| GeForce RTX 5070 / Blackwell / 9th Gen / D / 1 / 1 / 12 / YES YES YES YES YES YES YES YES YES YES YES YES | YES | YES | 12 |

- measured: the 12-session limit holds on driver 610.88 (`nvenc_sessions.json`). It matches the prior study (`research/frame_ring_buffer/prototypes/results/p5_nvenc.md`: "12 (20)" sessions, first error at session 13).
- measured: the limit error is `OpenEncodeSessionEx failed: incompatible client key (21)`.
- source: the NVENC programming guide (SDK 13.0, §8.6): "Starting from Ada generation, NVIDIA GPUs support high-bit-depth AV1 encoding."
- source: the NVIDIA Vulkan driver page (https://developer.nvidia.com/vulkan-driver): "November 21st, 2024 - Windows 553.40, Linux 550.40.80 New: VK_KHR_video_encode_av1". The extension still needs AV1 hardware; on the Ampere card it is absent (measured, §2).

### 7.2 Intel (media-driver intel-media-26.3.5, `docs/media_features.md` lines 59-76, VDEnc table)

Source: https://github.com/intel/media-driver/blob/intel-media-26.3.5/docs/media_features.md

| platform column | AVC | HEVC 8/10 | VP9 8/10 | AV1 8/10 | JPEG |
|---|---|---|---|---|---|
| NVL, PTL | yes | yes | yes | yes | yes |
| BMG, LNL | yes | yes | (blank) | yes | yes |
| MTLx (MTL, ARL) | yes | yes | yes | yes | yes |
| DG2/ATSM (Arc Alchemist) | yes | yes | yes | yes | yes |
| DG1/SG1, TGLx (TGL, RKL, ADL, RPL) | yes | yes | yes | (blank) | yes |
| ICL | yes | yes | yes | (blank) | yes |

- source: the same file, line 79: "JPEG encoding supports input format NV12/YUY2/UYVY/ABGR/Y8 and output format YUV400/YUV420/YUV422H_2Y/YUV444/RGB24."
- NOT VERIFIED: that the Windows Intel driver exposes the same matrix. The table is for the Linux VA-API media-driver.

### 7.3 AMD

- source: amd.com RX 7600 spec page (RDNA 3): "H264 Encode Yes ... H265/HEVC Encode Yes AV1 Decode Yes AV1 Encode Yes". https://www.amd.com/en/products/graphics/desktops/radeon/7000-series/amd-radeon-rx-7600.html
- source: amd.com RX 6600 spec page: "H264 Encode Yes H265/HEVC Decode Yes H265/HEVC Encode Yes AV1 Decode Yes", with no AV1 Encode row. The page did not state RDNA 2 in its spec text (NOT VERIFIED from that page).
- source: the AMF README @ v1.5.3: "Version 1.4.28 ... Added AV1 encoding support". It does not name a GPU generation. https://github.com/GPUOpen-LibrariesAndSDKs/AMF/blob/v1.5.3/README.md
- NOT VERIFIED: RDNA 4 (RX 9070 XT). Its spec page is rendered by JavaScript and had no codec rows.
- NOT VERIFIED: any AMD VP9 encode. No AMD spec page lists VP9 encode.

### 7.4 Apple (VideoToolbox)

- source: Apple tech specs, MacBook Air (M5) and MacBook Pro (M5 family): "Media Engine Hardware-accelerated H.264, HEVC, ProRes, and ProRes RAW / Video decode engine / Video encode engine / ProRes encode and decode engine / AV1 decode". https://www.apple.com/macbook-air/specs/, https://www.apple.com/macbook-pro/specs/
- source: MacBook Air (M2, 2022) specs: "Hardware-accelerated H.264, HEVC, ProRes, and ProRes RAW ... Video encode engine". https://support.apple.com/en-us/111867
- code: ffmpeg n9.0.2 `libavcodec/allcodecs.c:875,890,907` declares exactly three VideoToolbox encoders: `ff_h264_videotoolbox_encoder`, `ff_hevc_videotoolbox_encoder` and `ff_prores_videotoolbox_encoder`.
  - `videotoolboxenc.c:2852,2893,2934` names them "h264_videotoolbox", "hevc_videotoolbox" and "prores_videotoolbox".
  - **No av1/vp9 VideoToolbox encoder exists in ffmpeg.**
- inferred: on macOS there is no royalty-free hardware encode path. Royalty-free means software (libsvtav1, libvpx, mjpeg, ffv1), or `ffv1_vulkan`/`prores_ks_vulkan` via MoltenVK, which is NOT VERIFIED.

### 7.5 Linux Vulkan Video and VA-API

- code: Mesa `mesa-26.2.6`, `src/amd/vulkan/radv_physical_device.c:831-832`: `.KHR_video_encode_av1 = VIDEO_CODEC_AV1ENC && pdev->video_encode_enabled && pdev->info.video_caps.enc[AC_VIDEO_CODEC_AV1].supported`.
- code: Mesa `src/intel/vulkan/anv_physical_device.c:186-188`: `hw_video_encode_supported = device->info.verx10 <= 125; video_encode_enabled = hw_video_encode_supported && ANV_DEBUG(VIDEO_ENCODE)`. Lines 311-313 have encode h264/h265 only, with no `KHR_video_encode_av1` entry. So ANV Vulkan encode is debug-gated and has no AV1.
- code: ffmpeg n9.0.2 `allcodecs.c:860,874,889,896,914,920` declares VA-API encoders for av1, h264, hevc, mjpeg, vp8 and vp9.
  - `allcodecs.c:861,876,891` declares av1/h264/hevc `_vulkan` encoders.
  - The CLI on Gerald was built with `--enable-vaapi --enable-vulkan`, but VA-API cannot initialise on Windows (measured).

### 7.6 Summary: royalty-free hardware encode by platform (from 7.1-7.5)

| platform | AV1 HW enc | VP9 HW enc | JPEG HW/GPU enc | lossless GPU (ffv1_vulkan) | in PyPI PyAV wheel? |
|---|---|---|---|---|---|
| NVIDIA Pascal-Ampere (incl. Gerald) | no (source 7.1) | no (no VP9 column in the NVENC matrix) | nvJPEG on CUDA (measured on Ampere) | yes (measured on Ampere) | NVENC yes; Vulkan encoders no |
| NVIDIA Ada / Blackwell | yes (source 7.1) | no | nvJPEG (NOT VERIFIED here) | NOT VERIFIED | av1_nvenc yes |
| Intel TGL-RPL iGPU | no | yes (source 7.2) | yes (source 7.2) | NOT VERIFIED | av1_qsv/vp9_qsv yes (Win, Linux x86_64) |
| Intel Arc / MTL+ | yes | yes (not LNL/BMG) | yes | NOT VERIFIED | yes |
| AMD RDNA3 | yes (source 7.3) | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | av1_amf yes (Win, Linux x86_64) |
| Apple silicon | no (source 7.4) | no | NOT VERIFIED | NOT VERIFIED | no |
| Windows ARM64 | via D3D12/MF if the driver offers it (NOT VERIFIED) | no encoder in ffmpeg | n/a | n/a | av1_d3d12va / av1_mf yes |

## 8. What this means for G6/G7 (inferred, minimal)

- inferred: there is no single royalty-free hardware encoder that covers Windows, Linux and macOS.
  - AV1 hardware covers recent NVIDIA, Intel and AMD GPUs, but not Gerald's Ampere card and not Apple.
  - For a portable design, record G1 MJPEG cameras by passthrough. Treat AV1-HW (`av1_nvenc`/`av1_qsv`/`av1_amf`/`av1_d3d12va` via PyAV) as an optional accelerator, with H.264/HEVC hardware or CPU libsvtav1 as the fallback. The CPU cost goes in the bench manifest.
- inferred: for G4 lossless or raw recording on the GPU, `ffv1_vulkan` is the only royalty-free GPU codec measured here. It is not in PyAV wheels, so it needs either a subprocess ffmpeg CLI (frames piped or shared) or a self-built FFmpeg/PyAV with `--enable-vulkan`.
- inferred: the GPU input format is a constraint. NVENC on Ampere has no 4:2:2 encode (source 7.1), so the cameras' YUY2/MJPEG 4:2:2 must be converted to NV12 (4:2:0), or recorded via ffv1_vulkan or JPEG, which keep 4:2:2.

## 9. Limits of this stage

- No timing, throughput or CPU numbers (stage rule). Prior-study numbers are in `p5_nvenc.md` and `p4_mjpeg_passthrough.md`.
- Only one GPU vendor was physically testable: the NVIDIA Ampere card. Every Intel, AMD and Apple row comes from documents only.
- Functional encodes used 32 frames (8 real frames looped 4x). The Bayer input is synthetic (an RGGB mosaic sampled from real RGB).
- NVENC session counts are system-wide. Parsec and Sunshine were installed but idle in these runs (sessionCount 0 before).
- Not tested here: truncation and crash survival of GPU-encoded files (crash_resilience topic) and Chromium playback of these codecs (chromium topics).

## 10. Scripts, commands, downloads

All under `research/skellycam_recording/recording_upgrade/scripts/gpu_encode/`. Run from the repo root.

| script | kind | command |
|---|---|---|
| common.py | input prep (NV12/yuv420p/yuv422p10/bgr0/Bayer16 from the corpus; MJPEG concatenations) | imported |
| ff_functional.py | functional, ffmpeg CLI | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/gpu_encode/ff_functional.py` |
| pyav_functional.py | functional, PyAV | `.venv/Scripts/python.exe .../pyav_functional.py` (18.0.0); `uv run --script .../pyav_functional.py` (19.0.2) |
| wheel_hw_codecs.py | static wheel inspection | `.venv/Scripts/python.exe -I .../wheel_hw_codecs.py 19.0.2 18.0.0` |
| nvimgcodec_jpeg.py | functional, GPU JPEG | `uv run --script .../nvimgcodec_jpeg.py` |
| nvimg_life.py + nvimgcodec_lifetime_run.py | functional, buffer lifetime | `python .../nvimgcodec_lifetime_run.py` |
| nvenc_sessions.py | functional, session limit (also a bench) | `.venv/Scripts/python.exe .../nvenc_sessions.py --max 24` |
| benchlib.py | nvidia-smi sampler + JSON writer | imported |
| bench_*.py | timing (manifest) | see below |

Third-party downloads (temp, `scratchpad/gpu_encode/`):
- PyPI `av==19.0.2` (cp312 abi3 wheels for win_amd64, win_arm64, manylinux_2_28 x86_64/aarch64, macosx_14_0_arm64, macosx_11_0_x86_64) and `av==18.0.0` (same platforms). URLs and sha256 are in `wheel_hw_codecs.json`.
- `nvidia-nvimgcodec-cu12==0.10.0.9`, `nvidia-nvjpeg-cu12==12.4.0.76`, `numpy==2.2.6`, `opencv-python==4.12.0.88`, `psutil==7.2.2` (uv envs).
- Sources fetched at pinned tags into `scratchpad/gpu_encode/src/`:
  - FFmpeg n9.0.2: nvenc.c, ffv1enc_vulkan.c, ffv1enc.c, allcodecs.c, videotoolboxenc.c, vulkan_encode_*.c, d3d12va_encode.c;
  - pyav-ffmpeg 9.0.2-1 build-ffmpeg.py;
  - intel media-driver intel-media-26.3.5;
  - AMF v1.5.3;
  - Mesa mesa-26.2.6;
  - NVIDIA matrix, Vulkan driver page and NVDEC guide; AMD and Apple spec pages (HTML).

## 11. Benchmark manifest (run later, one at a time, quiet machine)

Before each run, check that `nvidia-smi --query-gpu=encoder.stats.sessionCount,utilization.gpu --format=csv` shows 0 sessions, and that Parsec and Sunshine are not streaming. Each script records nvidia-smi before, during and after. All JSON goes to `research/skellycam_recording/recording_upgrade/results/gpu_encode/bench/`.

| id | what | command (repo root) |
|---|---|---|
| B1a | single-stream unpaced fps + CPU, GPU encoders, 720p/1080p, intra/gop15, NV12 input and MJPEG (CPU decode) input | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/gpu_encode/bench_ffmpeg_encode.py --frames 900 --reps 3 --only h264_nvenc,hevc_nvenc,h264_vulkan,hevc_vulkan,h264_d3d12va,hevc_d3d12va,h264_mf,hevc_mf,ffv1_vulkan,prores_ks_vulkan,none_rawvideo` |
| B1b | same, CPU royalty-free references | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/gpu_encode/bench_ffmpeg_encode.py --frames 300 --reps 3 --only libsvtav1,libvpx-vp9,mjpeg,ffv1,none_rawvideo` |
| B2a | concurrent streams 1-16, h264_nvenc 1080p, unpaced + paced 30 fps | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/gpu_encode/bench_pyav_concurrent.py --codec h264_nvenc --size 1080p --streams 1,2,4,8,12,16 --frames 600 --mode unpaced,paced` |
| B2b | same, hevc_nvenc 1080p | `... bench_pyav_concurrent.py --codec hevc_nvenc --size 1080p --streams 1,2,4,8,12,16 --frames 600 --mode unpaced,paced` |
| B2c | same, h264_d3d12va 1080p (D3D12 path) | `... bench_pyav_concurrent.py --codec h264_d3d12va --size 1080p --streams 1,2,4,8,12,16 --frames 600 --mode unpaced,paced` |
| B2d | same, h264_nvenc 720p | `... bench_pyav_concurrent.py --codec h264_nvenc --size 720p --streams 1,2,4,8,12,16 --frames 600 --mode unpaced,paced` |
| B3a | numpy to frame / colour conversion / upload / encode-call cost, PyAV 18 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/gpu_encode/bench_pyav_upload.py --iters 600` |
| B3b | same, PyAV 19.0.2 | `uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/bench_pyav_upload.py --iters 600` |
| B4 | GPU JPEG decode (camera 4:2:2) and encode (q90 4:2:2) vs CPU | `uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/bench_nvimgcodec.py --n 300 --reps 3` |
| B5 | session limit on a quiet machine | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/gpu_encode/nvenc_sessions.py --max 24 --bench` |
| B2e (optional) | B2a under PyAV 19.0.2 | `uv run --script research/skellycam_recording/recording_upgrade/scripts/gpu_encode/bench_pyav_concurrent.py --codec h264_nvenc --size 1080p --streams 1,4,8,12 --frames 600 --mode unpaced,paced` |

Interpretation notes for the runner:
- B1 `fps` = frames / ffmpeg rtime, and `cpu_cores` = (utime + stime) / rtime, for the whole ffmpeg process. That includes the rawvideo read or MJPEG decode, so subtract the `none_rawvideo` row for encode-only cost.
- B2 `late_frames` (paced) counts encode calls that returned after the next frame was due.
