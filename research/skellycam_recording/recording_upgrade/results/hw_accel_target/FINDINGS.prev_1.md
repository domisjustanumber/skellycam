# hw_accel_target FINDINGS: hardware-acceleration target (G6, G7), intra-only recording format

Topic: Jellyfin-guided hardware-acceleration target (HANDOFF §1 req 3, 9 and 10, plus the 17:20 and 17:35 decisions).

- Machine: Gerald (i7-14700K with UHD 770, RTX 3070, driver 610.88).
- Implementation under test: PyAV 19.0.2 (FFmpeg 9.0.2, libavcodec 63.1.102).
- **No timing numbers**, because other agents were running. Only size, PSNR/SSIM, correctness and seek exactness are reported.

Labels:
- **[measured]**: a result file.
- **[source]**: a primary source, accessed 2026-11-09.
- **[source (transcribed)]**: intel.com returned 403, so the page was read through WebFetch's small model (NI header). Weaker than [source].
- **[code]**: file:line.
- **[inferred]**: kept to a minimum and marked.

Paths: `R` = `research/skellycam_recording/recording_upgrade/results/`, `S` = `research/skellycam_recording/recording_upgrade/scripts/`.

Merged inputs:
- `R/hw_accel_target/NOTES_sources_nvidia_intel.md` (NI)
- `R/hw_accel_target/NOTES_sources_amd_apple_cpu.md` (AAC)
- `R/hw_accel_target/NOTES_functional.md` (FN)
- `R/hw_accel_target/functional_pyav19.md` (FP)
- `R/intra_compare/NOTES.md` (IC) and `R/intra_compare/matched_summary.md` (MS)
- Also cited: `R/intra_playback/NOTES.md` (IP), `R/gpu_encode/NOTES.md` (GE), `R/gpu_encode/FINDINGS.md` (GEF), `R/licensing/FINDINGS.md` (LIC), `R/jellyfin_ffmpeg/NOTES.md` (JFF), `R/chromium_codecs/NOTES.md` (CC).
- Verification: `R/hw_accel_target/VERIFY_provenance.md` (VP), `R/hw_accel_target/VERIFY_method.md` (VM), `R/hw_accel_target/verify_method_range_check.json`.

## 1. Questions answered

1. Per hardware generation, which of these can be encoded and decoded in hardware: H.264, HEVC, AV1, VP9, JPEG (including nvJPEG on CUDA) and FFV1 on Vulkan? Do Jellyfin's claims agree with the vendors' primary sources?
2. Which **intra-only recording formats** meet the target? The target is hardware encode on RTX 3000+ and support on most 2020+ CPUs (Intel, AMD, Apple, and CPUs with no iGPU).
3. How do those candidates compare under G7 (royalty-free)? What does the royalty-free choice cost at matched quality?
4. What works on Gerald through PyAV 19.0.2, and which pitfalls must an implementation handle?

## 2. Findings

### 2.1 NVIDIA (GeForce)

- **N1 [source, representative rows]** NVENC on RTX 3000 (Ampere) encodes:
  - H.264: 8-bit 4:2:0 and 4:4:4;
  - HEVC: 8/10-bit 4:2:0 and 4:4:4;
  - not AV1, VP9 or any 4:2:2.
  - Basis: 2 Ampere matrix rows (RTX 3050, 3070) plus the app note's per-architecture grouping, not every SKU.
  - Evidence: support matrix row "H.264 (AVC) YUV 4:2:0/4:2:2/4:4:4/Lossless" = "YES NO YES YES" for Turing/Ampere/Ada; Video Codec SDK 13.1 NVENC application note (NI §2.1).
- **N2 [source]** AV1 encode starts at Ada (RTX 40). 4:2:2 H.264/HEVC encode and H.264 High10 start at Blackwell (RTX 50).
  - Matrix: "AV1 YUV 4:2:0" = NO/NO/YES/YES.
  - App note: "4:2:2 encoding | N | N | Y" (NI §2.1).
- **N3 [source]** No NVIDIA generation encodes VP9. App note §2: "NVENC can encode H.264 8-bit and H.264 10-bit, HEVC 8-bit, HEVC 10-bit, AV1 8-bit and AV1 10-bit contents." (NI §2.1)
- **N4 [source]** NVDEC decodes:
  - VP9 on Turing and later;
  - AV1 from GA10x (consumer Ampere) on: "AV1 Main Profile decoding | N | Y | Y" (NI §2.2).
- **N5 [source]** The NVDEC programming guide lists JPEG as "Hybrid (CUDA + CPU) JPEG", not as a fixed-function decoder (NI §2.2).
  - **[measured]** Through PyAV 19.0.2, `mjpeg_cuvid` and `mjpeg`+cuda both fail on the cameras' 4:2:2 JPEGs. Errors: `cuvid decode callback error` and `Failed setup for format cuda` (FP:312-313, 321-322, 330-331).
- **N6 [source]** nvJPEG **13.5** docs (https://docs.nvidia.com/cuda/nvjpeg/index.html, sha256 `5d2f3d74…db5ef`, copy in the scratchpad `hw_accel_target/findings_src/`):
  - "The encoding functions of the nvJPEG library perform GPU-accelerated compression of user's image data to the JPEG bitstream."
  - "NVJPEG_ENC_BACKEND_GPU Always use CUDA encoder."
  - "Hardware accelerated JPEG encode is available on Jetson Thor, running Linux ARM64."
  - So on every GeForce, nvJPEG encode uses the **CUDA (compute) backend**, not a fixed-function engine.
  - Version gap: the measured stack is `nvidia-nvjpeg-cu12==12.4.0.76` (GE §6, `R/gpu_encode/NOTES.md:148`). The 13.5 docs are used for capability statements only.
- **N7 [source]** Same page: "Hardware accelerated JPEG decode is available on the following GPUs architectures - Ampere (A100, A30) Hopper Ada Blackwell Jetson Thor", on "Windows Linux (x86_64, ARM64)".
  - Consumer Ampere (GA10x) is not listed.
  - The list names architectures. Whether "Ada" and "Blackwell" include GeForce RTX 40/50 is NOT VERIFIED.
  - [source] The hardware backend "Supports baseline JPEG images with single scan with 1 or 3 channels. 410 and 411 chroma subsamplings are not supported." So 4:2:2 is not excluded on paper. Whether it works is NOT VERIFIED (VM §0).
- **N8 [measured]** nvJPEG via nvImageCodec 0.10.0.9 on the RTX 3070 (GE §5, §6; `R/gpu_encode/nvimgcodec_jpeg.md`):
  - `nvjpeg_cuda_encoder` encodes 4:2:2 and 4:2:0 JPEG from host RGB and from GPU-resident images. The generic `backend:GPU_ONLY` encoder selection fails ("Could not create encoder. Code: 7").
  - Camera 4:2:2 JPEG decode works only through `HYBRID_CPU_GPU` / `nvjpeg_cuda_decoder`. `GPU_ONLY` and `HW_GPU_ONLY` fail ("Could not create decoder. Code: 7").
  - Planar and interleaved YUV input are rejected (`encode returned None`).
- **N9 [source]** The nvJPEG 13.5 C API has:
  - `nvjpegEncodeYUV` ("Input for this function is an image in YUV colorspace");
  - an NV12 input (`NVJPEG_INPUT_NV12`). For NV12, the subsampling "must both be NVJPEG_CSS_420", so **NV12 input gives 4:2:0 output only**.
  - [inferred] The RGB-only limit comes from the nvImageCodec 0.10.0.9 binding, not from nvJPEG.
  - NOT VERIFIED: planar-YUV encode in nvJPEG 12.4, and any YUV path through another binding.
- **N10 [source+measured]** GeForce NVENC is limited to 12 concurrent sessions per system.
  - [source] App note 13.1: "limited to 12 per system".
  - [measured, PyAV 19.0.2] 12 `h264_nvenc` sessions open and the 13th fails (`R/gpu_encode/nvenc_sessions_19.0.2.json`).
  - [measured, PyAV 19.0.2, with a control] With no sessions held, these all encode: `hevc_nvenc`, `h264_d3d12va`, `h264_mf` and `h264_qsv`. With 12 held, `hevc_nvenc`, `h264_d3d12va` and `h264_mf` fail, and `h264_qsv` still encodes (`R/gpu_encode/verify_method_pool.json`; GEF §2.4).
  - Vulkan: `h264_vulkan` also failed while the sessions were held. That was a CLI run with no control. [inferred] Vulkan shares the pool (GEF §2.4).
- **N11 [source]** "Ampere" or "Turing" alone does not guarantee NVENC.
  - MX450, MX570 A and GT 1030 have 0 NVENC.
  - Every RTX-branded desktop row lists NVENC (NI §2.1).
- **N12 [measured]** FFV1 on Vulkan compute (`ffv1_vulkan`) works on the RTX 3070 and is byte-exact, but **only through the ffmpeg CLI**. No PyAV wheel contains a Vulkan encoder (GE §1, §3, §4).

### 2.2 Intel

- **I1 [source]** Tiger Lake, Rocket Lake, Alder Lake and Raptor Lake iGPUs ("TGLx") encode H.264, HEVC, **VP9 and JPEG** in hardware, but **not AV1**.
  - media-driver `intel-media-26.3.5` README L112-133: AV1 TGLx "D" only (NI §4.1).
- **I2 [source]** AV1 encode exists on Meteor Lake/Arrow Lake, Lunar Lake, Arc A (DG2) and Arc B (BMG).
  - VP9 encode is absent on Lunar Lake and Arc B: README L126-129, "BMG 'D', LNL 'D'" (NI §4.1).
- **I3 [source]** JPEG encode is "D/E" on every platform from Skylake on.
  - media_features.md L79: "JPEG encoding supports input format NV12/YUY2/UYVY/ABGR/Y8 and output format YUV400/YUV420/YUV422H_2Y/YUV444/RGB24."
  - JPEG 4:2:2 decode is listed "BDW+" (NI §4.1, §4.2).
- **I4 [source]** HEVC 8-bit 4:2:2 encode is:
  - "Es" (PAK + shader) on TGLx;
  - absent on MTL/ARL;
  - "E" on LNL, DG2 and BMG (README L118; NI §4.1).
- **I5 [source (transcribed)]** Intel desktop F/KF SKUs have no iGPU, so they have no Quick Sync.
  - ark examples span 2020–2024: i5-10400F, i9-11900KF, i5-12400F, i7-14700KF, Core Ultra 7 265KF.
  - Only the 265KF page says "Intel® Quick Sync Video": "No". The other pages have no GPU section (NI §5).
  - **NOT VERIFIED:** what share of 2020+ SKUs or shipments they are.
- **I6 [source (transcribed)]** The media-driver tables are for Linux VA-API. The Windows oneVPL capability doc covers only 11th–13th Gen and Arc A. Windows support for MTL/ARL/LNL/BMG is therefore read from the Linux tables (NI §4).
- **I7 [measured]** The UHD 770's Windows Vulkan driver (101.7088) exposes Vulkan Video **decode only** (AV1, H.264, H.265), with no encode extension (`R/hw_accel_target/vulkaninfo_video_ext.txt`).

### 2.3 AMD

- **A1 [source+code]** No AMD GPU or APU encodes VP9 or JPEG. Every AMD H.264, HEVC, VP9 and AV1 hardware path is 4:2:0 only.
  - AMF wiki: "All codecs are 4:2:0". Its encode columns are AVC/HEVC/AV1 only.
  - Mesa `ac_video.h:29`: the encode slots end at AV1.
  - `ac_video.c:424,468-469,516-517`: encode input is `nv12`/`p010` (AAC §1).
  - **Exception: JPEG decode is 4:2:2-capable.**
    - Mesa `ac_video.c:540-545`: the VCN JPEG decoder outputs `y8u8y8v8_422` (YUYV).
    - AMF docs v1.5.3 line 106: "The Motion JPEG codec supports the `AMF_SURFACE_YUY2` format in addition to `AMF_SURFACE_NV12`." (AAC §2.2)
- **A2 [source+code]** AV1 encode needs VCN 4.0 or newer: RDNA3, RDNA4, Phoenix/Hawk Point/8000G and Strix Point.
  - Mesa `ac_video.c:478`: `info->vcn_ip_version >= VCN_4_0_0`.
  - AMF wiki: AV1 encode "N/A" for VCN 2.0/3.x (AAC §1, §2.2).
- **A3 [source]** These parts have no AV1 encode:
  - the desktop Ryzen 7000/9000 iGPU (Raphael/Granite Ridge). The kernel `apu-asic-info-table.csv` gives VCN 3.1.2; the AMF wiki gives 3.1 and 3.0 (J9).
  - Zen 2/3 APUs (VCN 2.2 per kernel; the AMF wiki gives Cezanne 2.0);
  - Rembrandt/Mendocino (VCN 3.1.1) (AAC §2.1, §5).
- **A4 [source+code]** RX 6400/6500 (Navi24, VCN 3.0.33) have no encoder: kernel `nv.c:192-195` `.codec_count = 0`; AMF wiki "Decode only" (AAC §2.2).
- **A5 [source]** Some Zen 4 parts have no iGPU: Ryzen 7 8700F and Ryzen 5 8400F say "Graphics Model Discrete Graphics Card Required". So do Ryzen 3000/5000 non-G parts (AAC §6.1).
- **A6 [inferred from code + measured wheel contents; NOT VERIFIED on AMD hardware]** No AMD path for decoding the cameras' 4:2:2 MJPEG is reachable from PyAV 19.0.2.
  - FFmpeg n9.0.2 has no `mjpeg_amf`. Its only MJPEG hwaccels are nvdec and vaapi (`hwaccels.h:54-55`).
  - The Linux wheel has no VA-API (`R/gpu_encode/wheel_hw_codecs.md`).
  - AAC §2.4 says this needs a functional test on AMD hardware.
- **A7 NOT VERIFIED:** whether `*_d3d12va` / `*_mf` encoders work on AMD Windows drivers. There is no AMD hardware here (AAC §7).

### 2.4 Apple

- **P1 [source]** These chips list "Hardware-accelerated H.264, HEVC, ProRes, and ProRes RAW" and a video encode engine: M1 Pro/Max/Ultra, M2, M3 and M4.
  - Base-M1 spec pages do not name the codecs they encode (partial) (AAC §3.1).
- **P2 [source+code]** No M1–M4 chip encodes AV1 or VP9.
  - M3/M4 add "AV1 decode" only.
  - FFmpeg's only VideoToolbox encoders are h264, hevc and prores (`allcodecs.c:875,890,907`) (AAC §3.1).
- **P3 [code]** Upstream FFmpeg n9.0.2 and the PyAV 19.0.2 macOS wheels have **no VideoToolbox JPEG encoder** (AAC §3.1; `R/gpu_encode/wheel_hw_codecs.md`).
  - **[source]** jellyfin-ffmpeg patch 0047 adds `mjpeg_videotoolbox` ("VideoToolbox MJPEG Encoder", with an `allow_sw` option). Its input formats are videotoolbox/nv12/yuv420p, so it takes 4:2:0 input (JFF §3).
  - NOT VERIFIED: whether Apple silicon encodes JPEG in fixed-function hardware.
- **P4 [code]** FFmpeg can request HEVC Main 4:2:2 10 from VideoToolbox (`videotoolboxenc.c:987-989,2874`). NOT VERIFIED: hardware support per chip (AAC §3.1).

### 2.5 CPUs with no iGPU (and no usable dGPU encoder)

- **C1 [measured]** The only path is CPU software. Software encoders in the PyAV 19.0.2 wheel (`R/hw_accel_target/sw_encoders_pyav19_win_amd64.json`, AAC §6.2):

  | encoder | 4:2:2 | licence / note |
  |---|---|---|
  | FFmpeg `mjpeg` | yes | |
  | `ffv1` | yes | lossless |
  | `libvpx-vp9` | yes, profile 1 | |
  | `libsvtav1` | **no**, 4:2:0 only | |
  | `libx264` / `libx265` | yes (`yuv422p` listed) | GPL |

  - `libopenh264` and `libaom-av1` are absent.
- **C2 [measured]** libjpeg-turbo (via simplejpeg 1.9.0) comes in a separate wheel, not in PyAV. It encodes 4:2:2 from YUV planes (IC §3; `R/uncompressed_intra/python_jpeg_libs_uv.json`).
- **C3 [measured]** MJPEG passthrough needs no encoder on any CPU (`research/frame_ring_buffer/prototypes/results/p4_mjpeg_passthrough.md`; AAC §1).

### 2.6 Jellyfin vs vendors

- **J1 [source]** On per-generation encode/decode claims, Jellyfin agrees with the vendors on every NVIDIA and Intel claim it makes, except J2 (NI §3, §4.3). J10 is a separate scope disagreement.
- **J2 [source] DISAGREE (NVIDIA).** Jellyfin's main page says H.264 10-bit decode "is not supported by any Intel, NVIDIA and AMD GPU".
  - The NVDEC guide lists Blackwell "High 10 and High 422".
  - Jellyfin's own NVIDIA page (L26) agrees with NVIDIA (NI §3).
- **J3 [source] DISAGREE (AMD).** Jellyfin says "Zen 4 based processors have integrated graphics". The 8700F/8400F pages say "Discrete Graphics Card Required" (AAC §2.3).
- **J4 [source] DISAGREE / overbroad (AMD AV1).**
  - Jellyfin's AV1 encode wording, "Ryzen 7000/8000 … and newer", takes in VCN 3.x parts with no AV1 encode: 7x20, 7x35, 7x45 and Granite Ridge.
  - Its AV1 decode wording, "Ryzen 6000 mobile … and newer", takes in Ryzen 7x30 (VCN 2.2, no AV1 decode) (AAC §2.3).
- **J5 [source (transcribed)] Vendor vs vendor (Intel).** oneVPL marks Arc A HEVC 4:2:2 encode "✔16k (Windows Only)". Media-driver README L118 gives DG2 "D/E" on Linux (NI §4.3).
- **J6 [source] Jellyfin-only claims (NOT VERIFIED, kept out of the plan):**
  - "no concurrent encoding sessions limit" on Intel, AMD and Rockchip;
  - the Apple "soft limit";
  - the VCN quality ranking (NI §4.3; AAC §2.3, §3.2).
- **J7 [measured]** The saved Jellyfin NVIDIA, Intel, main and known-issues page texts have 0 matches for `vp9|jpeg|4:2:2|422` (grep of `R/hw_accel_target/sources_nv_intel/jellyfin_*.txt`, re-run in VP).
  - The AMD page mentions VP9 only in a mapping from settings to VA-API profiles (scratchpad `src_amd_apple/jf_amd.md:250-261`).
  - So **every VP9, JPEG, 4:2:2 and FFV1 cell in §3.1 is vendor-only**.
- **J8 [source]** Jellyfin known issues, "590 and newer | Up to 12 encoding sessions", agrees with NVIDIA and with the measured 12 (NI §3; N10).
- **J9 [source+code] Vendor vs vendor (AMD), not resolved:**
  - Navi24 AV1 decode: the AMF wiki gives VCN 3.0 AV1 decode "8,10b", but the kernel `nv.c:182-184` bg decode table has no AV1. The §3.1 cell follows the kernel.
  - VCN versions: Cezanne is 2.0 (AMF wiki) vs 2.2 (kernel); Granite Ridge is 3.0 (AMF wiki) vs 3.1.2 (kernel). Both values in each pair fall in the same capability band (AAC §2.1 line 70).
- **J10 [code+measured] Scope disagreement (Intel).** Jellyfin intel L5 says "On Windows QSV is the only available method".
  - FFmpeg also has d3d11va/d3d12va/dxva2 decode and `*_d3d12va`/`*_mf` encoders (NI §4.3).
  - `h264_d3d12va` and `hevc_d3d12va` encode on the UHD 770 (device 1; FP:293, 297).

### 2.7 Functional results on Gerald through PyAV 19.0.2

- **F1 [measured]** `h264_qsv`, `hevc_qsv`, `vp9_qsv` and `mjpeg_qsv` encode from software frames.
  - All-intra gives 60/60 key frames and decodes back 60/60, in MKV and MP4 (FP:124-166; FN §3).
  - `vp9_qsv` also writes WebM (FP:155).
- **F2 [measured]** `mjpeg_qsv` and `hevc_qsv` accept `yuyv422` natively.
  - `mjpeg_qsv` writes 4:2:2 Baseline JPEG (`yuvj422p`) (FP:33, 164-165).
  - `hevc_qsv` writes HEVC Rext 4:2:2 (FP:18, 141-142).
  - `h264_qsv` accepts `nv12` only (FP:13-17).
  - **Range caveat:** the functional pass did not check range. Camera YUY2 is limited range. Fed limited-range input, `mjpeg_qsv` writes JPEGs that decode with Y 16..235 under a full-range (JFIF) interpretation, so contrast is compressed (`verify_method_range_check.json`; FN §6.2). A correct JPEG needs YUY2 expanded to full range first, as `S/intra_compare/benchpaths.py:16-18` does. That is an extra conversion step.
- **F3 [measured]** QSV `HWAccel` frames-context mode fails for every QSV encoder with `Error creating an internal frame pool` (FP:125, 134, 157; also 127, 136, 145, 147, 149, 159; FN §3).
- **F4 [measured]** No AV1 hardware encode works on Gerald through any API.
  - `av1_qsv`: "Current codec type is unsupported" (FP:144, 447).
  - `av1_nvenc`: "Codec not supported".
  - `av1_d3d12va` fails on every adapter (FP:201, 300-303).
  - `av1_mf` picks the Intel AV1 MFT (FP:563), and the header write fails (FN §1).
- **F5 [measured]** `mjpeg_qsv` decodes the cameras' 4:2:2 MJPEG: 10/10 frames on each of three sets.
  - Output is `nv12`, so chroma drops to 4:2:0.
  - PSNR-Y vs CPU decode, min: 66.9–69.5 dB (FP:310, 319, 328).
  - NVDEC fails on the same frames (N5).
- **F6 [measured]** The `mjpeg` decoder has no D3D11VA/D3D12VA/DXVA2/QSV hw config. Requests for those decode in software without raising (FP:314-317; FN §4).
- **F7 [measured]** Media Foundation picks the NVIDIA MFT: `MFT name: 'NVIDIA H.264 Encoder MFT'` (FP:540); HEVC likewise (FP:553).
  - `h264_d3d12va` and `hevc_d3d12va` work on both adapters; device 1 is the UHD 770 (FP:292-298).
  - D3D12VA to MKV fails with "Invalid data found when processing input" (FP:193, 200). MP4 works.
- **F8 [measured]** The HEVC 4:2:2 file from `hevc_qsv` decodes on QSV and in software, but **not on NVIDIA**:
  - `hevc_cuvid` error (FP:374);
  - `hevc`+cuda: "Hardware is lacking required capabilities" (FN §4).
- **F9 [measured]** Hardware decode against the default software decoder:
  - Y plane identical (PSNR-Y 99) for every working hardware decoder of H.264, HEVC, VP9 and AV1 streams.
  - All planes identical for VP9 and AV1 through `*_qsv`/`*_cuvid` (FP:345-346, 352-353, 394-395, 401-402).
  - All planes identical for native h264/hevc/vp9 with d3d11va/d3d12va/cuda/dxva2 hwaccel (FP:361-372, 382-393, 396-400).
  - **Not all planes:** H.264 and HEVC through `h264_qsv`/`h264_cuvid`/`hevc_qsv`/`hevc_cuvid` give "PSNR all (min)" 63.3–63.7 dB (FP:359-360, 366-367, 380-381, 387-388). Cause NOT VERIFIED; it could be the comparison method.
  - FN §4 makes the same "bit-identical" overstatement.
  - The UHD 770 decodes AV1 (`av1_qsv`, FP:345, 352) although it cannot encode it.

### 2.8 Matched-quality head to head (intra only; IC, MS)

Scope of every ratio in this section [measured]:
- Gerald only, with the presets and settings in `R/intra_compare/matched_settings.json`: NVENC p4/ll constqp, QSV default CQP, libjpeg-turbo non-fastdct.
- One room's content: 16 YUY2 frames plus two camera models' MJPEG.
- Matching is on luma only (SSIM-Y at target A, PSNR-Y at target B).
- IC §12: "Other generations can produce different bytes at the same QP."

Findings:
- **Q1 [measured]** 994 sweep points over 16 intra-only paths and 4 input classes. Every point decoded back with the right frame count. Every H.264/HEVC frame is IDR with `has_b_frames=0` (`R/intra_compare/verification.md`).
- **Q2 [measured]** Target A is camera-equivalent quality (SSIM-Y 0.9961), on raw YUY2 1080p. Ratios of interpolated bytes to libjpeg-turbo 4:2:2 (MS:11-25):
  - JPEG 4:2:0: libjpeg-turbo 0.89, mjpeg_qsv 1.00, nvJPEG 0.74;
  - H.264 4:2:0: h264_nvenc 0.53, h264_qsv 0.59;
  - HEVC 4:2:0: hevc_nvenc 0.43, hevc_qsv 0.39;
  - HEVC 4:2:2: hevc_qsv Rext 0.52.
- **Q2a [measured] nvJPEG's size lead depends on the metric.**
  - At target A, nvJPEG's PSNR-Y is 50.80 dB against libjpeg-turbo's 52.24 dB (MS:18, 23).
  - At target B (PSNR-matched), nvjpeg_420 is 0.92x. That is larger than jpeg_turbo_420 (0.89x) and mjpeg_qsv_420 (0.88x) (MS:106-108).
  - So at matched PSNR, nvJPEG is no smaller than CPU or QSV JPEG.
- **Q3 [measured]** Target B (PSNR-Y 45 dB, yuy2_1080p) widens the gap, against libjpeg-turbo 4:2:2 (MS:97-111):
  - H.264 4:2:0 is 0.29–0.35x;
  - HEVC 4:2:0 is 0.18x.
- **Q4 [measured]** On decoded camera MJPEG at target A, H.264/HEVC re-encodes (NVENC/QSV) are (MS:53-89):
  - 0.64–0.91x the camera's own JPEG bytes (passthrough), i.e. 9–36% smaller. Each re-encode adds one more generation of loss (SSIM-Y 0.9961 against the decoded camera frame), while passthrough adds none (IC §2). So this saving is not at matched quality.
  - 0.70–1.02x libjpeg-turbo 4:2:2 re-encodes of the same frames (a separate comparison).
- **Q5 [measured]** At the same chroma, the hardware JPEG encoders are in libjpeg-turbo's size range:
  - `mjpeg_qsv`: 0.99–1.12x;
  - nvJPEG: 0.81–1.24x.
  - nvJPEG's PSNR-Y is 1.4–2.2 dB lower at the same SSIM-Y; it is fed RGB (IC §1, §9.3).
- **Q6 [measured]** Keeping 4:2:2 costs 7–17% more bytes for JPEG and 13–33% for `hevc_qsv` Rext, with luma unchanged (IC §7).
- **Q7 [inferred, arithmetic on MS]** JPEG's byte cost relative to hardware H.264/HEVC intra (h264/hevc × nvenc/qsv), raw YUY2 1080p.

  Target A (SSIM-Y 0.9961):

  | JPEG path | vs H.264/HEVC 4:2:0 |
  |---|---|
  | libjpeg-turbo 4:2:0 | 1.51–2.27x |
  | mjpeg_qsv 4:2:0 | 1.69–2.54x |
  | nvJPEG 4:2:0 | 1.26–1.90x |

  - At 4:2:2 on both sides, libjpeg-turbo 4:2:2 vs hevc_qsv Rext 4:2:2 is 1.92x.
  - The draft's "1.7–2.6x" compared 4:2:2 JPEG with 4:2:0 video, so chroma was not matched.

  Target B (PSNR-Y 45 dB):

  | comparison | ratio |
  |---|---|
  | libjpeg-turbo 4:2:2 vs H.264/HEVC 4:2:0 (77,458 / 27,378 to 77,458 / 14,236) | 2.8–5.4x |
  | 4:2:0 JPEG (libjpeg-turbo, mjpeg_qsv, nvJPEG) vs H.264/HEVC 4:2:0 | 2.5–5.0x |

### 2.9 Playback side (G8/G9) for the candidates

- **V1 [measured]** All 48 H.264/HEVC intra clips (h264/hevc × nvenc/qsv, in MP4/fMP4/MKV) play and seek exactly in Electron 35.7.5, Electron 45.2.3 and Chrome 156.
  - `<video>` seek to the `mid` target from the file's real pts: 4800/4800 per browser.
  - WebCodecs: 4800/4800 per browser.
  - Each frame decodes on its own (IP §1).
  - "Exact" here means frame identity, checked with a burned-in index. It is not pixel fidelity (VM §3).
- **V2 [measured]** HEVC decodes only in hardware in all three browsers. WebCodecs `prefer-software` gives "config not supported". H.264 falls back to `FFmpegVideoDecoder` (IP §1, §4.5).
- **V3 [measured]** `h264_nvenc` frames need `flush()` after each WebCodecs chunk (360/360).
  - Cause: `bitstream_restriction_flag = 0` in the SPS.
  - QSV and HEVC streams did not need it (IP §1; `R/intra_playback/sps_vui_trace.txt`).
- **V4 [measured]** MJPEG does not play in `<video>` in any container (`DEMUXER_ERROR_NO_SUPPORTED_STREAMS`). The JPEG path splits into two cases:
  - **Re-encoded JPEGs** (`mjpeg_qsv` 4:2:2 from full-range YUYV, burned-in index): frame-exact through Range fetch + `createImageBitmap` / `ImageDecoder`, 800/800 seeks per path per browser (IP §1-§2, IP:18-19, 66).
  - **Camera JPEG stills:** 88/88 decode with ImageDecoder, createImageBitmap and `<img>` in all three browsers. Max grid MAD vs OpenCV decode is 0.04 (CC:150).
  - **Camera JPEG bytes inside an MKV, fetched by sidecar offset:** 450/450 came back byte-identical, and 450/450 decoded without error with both APIs. Pixels were not compared in this test (IP:32-33).
- **V5 [measured]** On the RTX 3070:
  - Chromium does not decode H.264 4:2:2 in hardware (FFmpegVideoDecoder).
  - E35 reports HEVC Rext 4:2:2 as unsupported. No 4:2:2 HEVC clip was played (CC §3; IP §6).

### 2.10 Royalty status (G7; LIC §2.1, §3.1)

- **R1 [source]** Baseline JPEG: T.81 Annex L lists patents only for the arithmetic-coding and hierarchical-lossless processes. "No other patents required for implementation of any of the other processes … had been identified at the time of publication" (LIC Q17, Q18).
- **R2 [source]** H.264 and HEVC are royalty-bearing.
  - Via LA AVC rates (Q29); Access Advance / Via LA HEVC (Q31–Q34).
  - NVIDIA's SDK licence leaves codec patent licensing to the developer (Q49, N1).
- **R3 [source]** AV1 and VP9 have developer royalty-free licences (AOM Q01, Google Q12). Sisvel offers royalty-bearing pool licences for both (Q04, Q07).
- **R4 [measured]** The wheel's only CPU H.264/HEVC encoders are libx264/libx265, which are GPL. Removing their DLLs breaks `import av` (LIC §2.5).
- **R5 [source]** nvImageCodec may be redistributed only "as incorporated into a software application", and not under an open-source licence (LIC Q51, Q52).

### 2.11 Pipeline pitfalls (affect any implementation)

- **K1 [measured]** Decoded MJPEG frames carry `pict_type=I`, which forces key frames in GOP encoders. Reset it to `NONE` (FN §6.1). This does not matter for intra-only output, but it matters for any decode→encode pipeline.
- **K2 [measured]** `reformat(format='nv12')` keeps full-range samples from a range-tagged decoded JPEG frame. Pass `dst_color_range=1` for **H.264/HEVC** targets (FN §6.2).
  - PyAV 19 converts range only when the source is an untagged `yuvj*` frame (FN §6.3).
  - Always pass `src_color_range` and `dst_color_range` explicitly, as `S/intra_compare/benchpaths.py:195` does.
- **K3 [measured+code]** FFmpeg's default `i_qfactor=-0.8` makes NVENC constqp and QSV CQP code intra frames at 0.8x the requested QP. Pin `i_qfactor=1, i_qoffset=0` (IC §3, §9.1; `R/intra_compare/knob_check.json`).
- **K4 [code+measured]** NVENC all-intra needs `gop_size=0` (`nvenc.c:1764-1766`; GE §3).
- **K5 [measured+code]** **JPEG targets must be fed full range.**
  - `S/hw_accel_target/bench_encode_stream.py` gets this wrong:
    - `:112` feeds limited-range NV12 (from YUY2) to `mjpeg_qsv`;
    - `:120-124` applies `dst_color_range=1` to MJPEG sources for every non-`yuvj` format, `mjpeg_qsv`'s nv12 included.
  - Measured with PyAV 19.0.2: the resulting JPEG decodes as `yuvj420p` with Y 16..235 (`verify_method_range_check.json`).
  - `S/intra_compare/benchpaths.py:16-18` feeds JPEG paths full range and H.264/HEVC limited range.

## 3. Comparison tables

### 3.1 Per-generation hardware matrix (cell = encode / decode)

Legend:
- Y = yes; N = no; NV = NOT VERIFIED; P = partial.
- "CUDA" = the nvJPEG compute backend. Per Dom (17:35), it counts as hardware-accelerated.
- "4:2:0 only" applies to the AMD H.264/HEVC/AV1/VP9 cells. AMD JPEG decode outputs 4:2:2 YUYV on Linux (A1).
- "measured" cells are measured on the RTX 3070 or the UHD 770 (RPL-S) only. The rest of each row is from sources.
- Jellyfin column: verdict on Jellyfin's per-generation claims (§2.6). Every VP9/JPEG/FFV1 cell is vendor-only (J7).

| generation | H.264 | HEVC | AV1 | VP9 | JPEG | FFV1 (Vulkan compute) | Jellyfin vs vendor | evidence |
|---|---|---|---|---|---|---|---|---|
| NVIDIA Turing (RTX 20, GTX 16) | Y / Y (8-bit; no 4:2:2) | Y / Y (no 4:2:2) | N / N | N / Y | enc CUDA: NV (not tested) / dec hybrid CUDA+CPU | NV | AGREE | N1-N5, N7, N11 |
| NVIDIA Ampere (RTX 30) | Y / Y | Y / Y | **N** / Y | N / Y | **enc CUDA: Y (measured, RTX 3070)** / dec: hybrid CPU+CUDA Y (measured); GPU-only nvImageCodec backends and NVDEC/FFmpeg **fail** on 4:2:2 (measured) | Y (measured, CLI only) | AGREE | N1, N5, N8, N12 |
| NVIDIA Ada (RTX 40) | Y / Y | Y / Y | **Y** / Y | N / Y | enc CUDA: NV (inferred from N6) / dec: architecture listed (N7); GeForce applicability and 4:2:2 NV (doc excludes only 4:1:0/4:1:1) | NV | AGREE | N2, N6, N7 |
| NVIDIA Blackwell (RTX 50) | Y / Y (adds 4:2:2, High10) | Y / Y (adds 4:2:2) | Y / Y | N / Y | as Ada | NV | AGREE (except main-page H.264 10-bit, J2) | N2, N7, J2 |
| Intel TGL / RKL / ADL / RPL iGPU | Y / Y | Y / Y (4:2:2 enc shader-assisted; **measured Rext 4:2:2 on RPL-S**) | **N** / Y (measured on RPL-S; other TGLx source) | **Y (measured on RPL-S)** / Y | **Y fixed-function (measured on RPL-S, 4:2:2 from yuyv422; needs full-range input, K5)** / Y (measured, output nv12) | NV (Vulkan 1.4 device, not run) | AGREE; scope DISAGREE on "QSV only on Windows" (J10) | I1, I3, I4, F1-F5, F9 |
| Intel MTL / ARL | Y / Y | Y / Y (4:2:2 enc N) | Y / Y | Y / Y | Y / Y (Windows read from Linux tables, I6) | NV | AGREE | I2, I4, I6 |
| Intel LNL | Y / Y | Y / Y | Y / Y | **N** / Y | Y / Y (Windows inferred, I6) | NV | AGREE | I2, I6 |
| Intel Arc A (DG2) | Y / Y | Y / Y (4:2:2: vendor vs vendor, J5) | Y / Y | Y / Y | Y / Y | NV | AGREE | I2, J5 |
| Intel Arc B (BMG) | Y / Y | Y / Y | Y / Y | **N** / Y | Y / Y (Windows inferred, I6) | NV | AGREE | I2, I6 |
| Intel F/KF desktop (no iGPU) | none | none | none | none | none | none | AGREE ("ending with F") | I5 |
| AMD Zen 2/3 APU (Renoir, Lucienne*, Cezanne, Barcelo; VCN 2.2 per kernel, Cezanne 2.0 per AMF wiki) | Y / Y | Y / Y | N / N | N / Y | **N** / Y (4:2:2 YUYV out; Linux VA-API only; not reachable from PyAV, A6) | NV | AGREE; "Ryzen 6000 … and newer" AV1 decode overbroad for 7x30 (J4); VCN version vendor vs vendor (J9) | A1, A3, A6, J9 |
| AMD Rembrandt, Mendocino (VCN 3.1.1) | Y / Y | Y / Y | N / Y | N / Y | N / Y | NV | AGREE; 7x20/7x35 fall inside Jellyfin's AV1-encode wording (J4) | A3 |
| AMD Raphael / Granite Ridge desktop iGPU (VCN 3.1.2 per kernel; AMF wiki 3.1 / 3.0) | Y / Y | Y / Y | **N** / Y | N / Y | N / Y | NV | DISAGREE (J4); VCN version vendor vs vendor (J9) | A3, J9 |
| AMD Phoenix / Hawk Point / 8000G, Strix Point (VCN 4.x) | Y / Y | Y / Y | **Y** (1 instance; 64w/16h alignment) / Y | N / Y | N / Y | NV | AGREE | A2 |
| AMD RDNA1 RX 5000 (VCN 2.0) | Y / Y | Y / Y | N / N | N / Y | N / Y | NV | AGREE | AAC §5 |
| AMD RDNA2 RX 6600-6900 (VCN 3.0) | Y / Y | Y / Y | N / Y | N / Y | N / Y | NV | AGREE | AAC §5 |
| AMD RDNA2 RX 6400/6500 (Navi24) | **N** / Y | **N** / Y | N / N (kernel; AMF wiki says Y: J9) | N / Y | N / N | NV | AGREE | A4, J9 |
| AMD RDNA3 RX 7000 (VCN 4.0) | Y / Y | Y / Y | Y / Y | N / Y | N / Y | NV | AGREE | A2 |
| AMD RDNA4 RX 9000 (VCN 5.0) | Y / Y | Y / Y | Y / Y | N / Y | N / Y | NV | AGREE | A2 |
| AMD no iGPU (Ryzen 3000/5000 non-G, 8400F/8700F) | none | none | none | none | none | none | DISAGREE (J3) | A5 |
| Apple M1 (base) | P / Y | P / Y | N / N | N / NV | N in FFmpeg/PyAV (jellyfin-ffmpeg `mjpeg_videotoolbox`, 4:2:0 input; hardware NV) / N via FFmpeg | NV | AGREE (partial) | P1-P3 |
| Apple M1 Pro/Max/Ultra, M2 | Y / Y | Y / Y (4:2:2 10-bit NV) | N / N | N / NV | as M1 | NV | AGREE | P1-P4 |
| Apple M3, M4 | Y / Y | Y / Y | N / **Y** | N / NV | as M1 | NV | AGREE | P1-P3 |
| CPU with no iGPU and no GPU encoder | software (libx264, GPL) | software (libx265, GPL) | software (libsvtav1, 4:2:0) | software (libvpx-vp9) | software (libjpeg-turbo, FFmpeg mjpeg) | software `ffv1` (CPU) | n/a | C1, C2 |

\* The Lucienne VCN version is inferred (AAC §2.1).

### 3.2 What PyAV 19.0.2 can reach per vendor and OS (encode)

| vendor / OS | reachable in the PyPI wheel | not reachable | evidence |
|---|---|---|---|
| NVIDIA / Windows | `h264/hevc(/av1)_nvenc`, `*_d3d12va`, `*_mf` (all share the 12 sessions, measured PyAV 19.0.2) | `*_vulkan`, `ffv1_vulkan`; nvJPEG (needs nvImageCodec, a separate wheel) | NI §6; GE §1, §4; N8, N10 |
| NVIDIA / Linux | nvenc (names in wheel; not tested) | vulkan | NI §6 |
| Intel / Windows | `h264/hevc/vp9/mjpeg_qsv` (measured); `*_d3d12va` on adapter 1 (measured) | vulkan encode (the driver exposes none) | F1, F7, I7 |
| Intel / Linux x86_64 | **NOT VERIFIED, likely unusable** [inferred from code]: the `*_qsv` names are in the wheel, but it has no VA-API. FFmpeg n9.0.2 compiles the Linux QSV session handle only `#if CONFIG_VAAPI && !defined(_WIN32)` (`qsv_internal.h:26-28`). Without VA-API, the QSV child device falls through to "No supported child device type is enabled" (`hwcontext_qsv.c:2548-2551`). So Linux Intel has no verified hardware path in the wheel | vaapi (incl. `mjpeg_vaapi`) | VM §0, W5; files fetched 2026-11-09 to scratchpad `hw_accel_target/findings_src/ffqsv/` (sha256 `c75d4fbb…9325f`, `b719cf0c…8e4b`); `R/gpu_encode/wheel_hw_codecs.md` |
| AMD / Windows | `h264/hevc/av1_amf` (not tested; no AMD here) | JPEG, VP9 (no hardware) | AAC §2.4 |
| AMD / Linux | `*_amf` (needs AMD's closed runtime) | vaapi, vulkan | AAC §2.4 |
| Apple / macOS | `h264/hevc_videotoolbox` (+ prores) | JPEG (only via jellyfin-ffmpeg 0047), AV1, VP9 | P2, P3 |
| Windows on ARM64 (e.g. Snapdragon) | `h264/hevc/av1_d3d12va`, `*_mf` names only. NOT VERIFIED (no device; not covered by this study) | qsv, nvenc, amf | `R/gpu_encode/wheel_hw_codecs.md` |

### 3.3 Intra-only candidates vs the target (recording format)

Bytes column: target A, yuy2_1080p, against libjpeg-turbo 4:2:2. These are Gerald, these presets, this content (§2.8 scope).

| candidate (intra only) | RTX 3000+ hw encode | Intel 2020+ iGPU hw encode | AMD 2020+ APU / RDNA hw encode | Apple M1-M4 hw encode | verified through PyAV 19.0.2 on Gerald | no-iGPU CPU | G7 | Electron playback / exact seek | bytes at target A | meets target? |
|---|---|---|---|---|---|---|---|---|---|---|
| **H.264 intra 4:2:0** | Y (NVENC; measured on RTX 3070, other generations source) | Y (QSV; measured on UHD 770, other generations source) | Y (source; all parts with an encoder, not Navi24; AMF untested) | Y (P on base M1; source) | `h264_nvenc`, `h264_qsv`, `h264_d3d12va`, `h264_mf` (Windows x64) | libx264 (GPL) | royalty-bearing (R2) | `<video>` + WebCodecs, sw fallback; exact (V1, V2) | 0.53 (nvenc) / 0.59 (qsv) | **yes**, on both readings below |
| **HEVC intra 4:2:0** | Y (NVENC; measured on RTX 3070) | Y (QSV; measured on UHD 770) | Y (source; not Navi24) | Y (P on base M1; source) | `hevc_nvenc`, `hevc_qsv`, `hevc_d3d12va`, `hevc_mf` | libx265 (GPL) | royalty-bearing (R2) | **hardware decode only** (V2); exact (V1) | 0.43 / 0.39 | **yes**; playback needs HEVC decode hardware |
| **JPEG re-encode** (4:2:2 or 4:2:0) | Y via **nvJPEG CUDA** (measured on Ampere, outside FFmpeg/PyAV; RTX 40/50 inferred, N6) | Y (`mjpeg_qsv`, in the wheel; measured on RPL-S; MTL+ on Windows inferred, I6; needs full-range input, K5) | **N** (no AMD JPEG encode) → CPU | **N** in FFmpeg/PyAV → CPU | `mjpeg_qsv`; nvJPEG via nvImageCodec 0.10.0.9 (separate wheel, RGB input only) | libjpeg-turbo / FFmpeg mjpeg | no patents listed for baseline (R1) | no `<video>`; ImageDecoder / createImageBitmap frame-exact (V4) | 4:2:0: libjpeg-turbo 0.89, mjpeg_qsv 1.00, nvJPEG 0.74 (nvJPEG not smaller at matched PSNR, Q2a) | **partly**: Ampere and Intel TGL–RPL measured or source; RTX 40/50 and Windows MTL+ inferred; AMD and Apple software only |
| JPEG passthrough (MJPEG cameras) | no encode needed | no encode needed | no encode needed | no encode needed | n/a | no encode needed | as JPEG (R1) | camera JPEGs: 88/88 still decode, 450/450 byte-identical fetch + decode (V4) | camera bytes. H.264/HEVC re-encodes at A are 0.64–0.91x camera bytes, with one more generation of loss (0.70–1.02x libjpeg-turbo 4:2:2) (Q4) | n/a: no encoder involved (C3) |
| AV1 intra | **N** | **N** (TGL–RPL) | VCN 4+ only | **N** | none (F4) | libsvtav1 (4:2:0) | RF licence, Sisvel claims (R3) | plays (CC §2, all-intra rows) | not swept | **no** |
| VP9 intra | **N** (all NVIDIA) | Y except LNL/BMG | **N** | **N** | `vp9_qsv` | libvpx-vp9 | RF licence, Sisvel claims (R3) | plays (CC §2, all-intra rows) | not swept | **no** |
| FFV1 (Vulkan) | CLI only (measured) | NV | NV | NV | none (no Vulkan encoder in any wheel) | CPU `ffv1` | 0 IETF disclosures (LIC §2.1) | **does not play** (CC §2) | lossless | **no** (not in PyAV, not playable) |

Two readings of "supported on most 2020+ CPUs" (req 3). The share of Intel, AMD, Apple and no-iGPU CPUs is NOT VERIFIED (I5).
- **Hardware encode on the CPU's own iGPU or APU (capability, from sources):**
  - H.264 and HEVC cover Intel, AMD and Apple 2020+ parts that have graphics.
  - JPEG covers Intel only.
  - Reachability through the PyAV wheel is narrower:
    - AMD AMF is untested;
    - Linux AMD needs the closed AMF runtime;
    - Linux Intel QSV is likely unusable (§3.2);
    - Windows-on-ARM is NOT VERIFIED.
- **Encodable at all on the CPU:**
  - every candidate has a software encoder;
  - JPEG's is royalty-free (libjpeg-turbo), while the wheel's H.264/HEVC encoders are GPL (R4).

### 3.4 Matched-quality bytes/frame (target A, SSIM-Y 0.9961; `bytes@target`, interpolated, from MS)

| path | chroma | yuy2_1080p | mjpeg_720p (passthrough 66,594) | mjpeg_1080p (passthrough 163,478) |
|---|---|---|---|---|
| libjpeg-turbo (CPU) | 4:2:2 | 297,359 | 60,318 | 145,774 |
| libjpeg-turbo (CPU) | 4:2:0 | 265,001 | 55,459 | 130,185 |
| mjpeg_qsv | 4:2:2 | 331,349 | 59,802 | 145,128 |
| mjpeg_qsv | 4:2:0 | 296,502 | 54,796 | 129,364 |
| nvJPEG (CUDA) | 4:2:2 | 248,629 | 65,280 | 175,469 |
| nvJPEG (CUDA) | 4:2:0 | 221,461 | 60,527 | 161,033 |
| h264_nvenc | 4:2:0 | 157,840 | 46,217 | 123,426 |
| h264_qsv | 4:2:0 | 175,094 | 55,667 | 148,327 |
| hevc_nvenc | 4:2:0 | 129,131 | 53,975 | 141,655 |
| hevc_qsv | 4:2:0 | 116,646 | 42,502 | 110,835 |
| hevc_qsv Rext | 4:2:2 | 155,171 | 47,993 | 136,529 |

- Source lines: MS:11-25, 53-67, 74-88.
- `R/intra_compare/NOTES.md` §6 (around line 181) is out of sync with MS. It gives:
  - hevc_nvenc 55,112 / 144,376 (MS: 53,975 / 141,655);
  - h264_nvenc yuy2_720p 83,921 (MS: 83,913);
  - different libx264_ultrafast / libx265 MJPEG cells.
- MS is the generated file and is used here. The intra_compare owner should regenerate NOTES §6.

## 4. Implications for the plan

1. **The target and G7 conflict for re-encoded formats, and the plan must say so** (§3.3).
   - Only H.264 and HEVC intra are hardware-encoded on both RTX 3000+ and the iGPU/APU of Intel, AMD and Apple 2020+ parts (N1, I1, A1, P1). Both are royalty-bearing (R2).
   - No royalty-free video codec meets the target:
     - AV1 fails on RTX 3000 and TGL–RPL (N2, I1, F4);
     - VP9 fails on NVIDIA, AMD and Apple (N3, A1, P2).
2. **JPEG is the only royalty-free format accelerated on both RTX 3000 and Intel TGL–RPL iGPUs.**
   - NVIDIA support is CUDA nvJPEG, which Dom counts as hardware (N6, N8). It is measured on Ampere; RTX 40/50 is inferred.
   - Intel support is fixed-function `mjpeg_qsv` (F2). It is measured on RPL-S; Windows MTL+ is inferred from the Linux tables (I6).
   - It falls back to CPU on AMD and Apple (A1, P3).
   - Cost at camera-equivalent quality on raw YUY2, at matched chroma (luma-matched only; Gerald presets):
     - 4:2:0 JPEG is about 1.3–2.5x the bytes of hardware H.264/HEVC 4:2:0 intra;
     - 4:2:2 libjpeg-turbo is 1.9x hevc_qsv Rext 4:2:2 (Q7).
   - At PSNR-Y 45 dB the gap is 2.5–5.0x at 4:2:0 (Q7).
3. **For MJPEG cameras the target barely applies.**
   - Passthrough stores the camera's JPEG with no encoder (C3).
   - Camera JPEGs decode in the UI through ImageDecoder/createImageBitmap: 88/88 stills, and 450/450 byte-identical fetches from MKV (V4).
   - The hardware target decides only the G4 inputs (YUY2/NV12/Bayer).
   - On decoded MJPEG, re-encoding to H.264/HEVC gives files 9–36% smaller than the camera's bytes, at the cost of one more generation of loss (Q4).
4. **If JPEG is the recording format for G4 inputs**, the encoder choice is per vendor:
   - **nvJPEG on NVIDIA.**
     - It is a separate dependency with licence limits (R5).
     - nvImageCodec 0.10.0.9 accepts only RGB (N8).
     - The C API's NV12 input gives 4:2:0 only. Planar YUV in nvJPEG 12.4, and any binding for it, are NOT VERIFIED (N9).
     - Its size lead disappears at matched PSNR (Q2a).
     - The Q2 ratios also hold only with an exact RGB conversion: PyAV swscale RGB costs about 6 dB PSNR-Y (IC §9.3).
   - **`mjpeg_qsv` on Intel**, fed `yuyv422` for 4:2:2, after expanding YUY2 to full range (F2, K5).
   - **libjpeg-turbo** everywhere else (C2).
5. **If H.264/HEVC intra is chosen** (accepting royalties):
   - **Prefer H.264 over HEVC for playback robustness.** HEVC decodes only in hardware in Electron (V2), and NVIDIA cannot decode HEVC 4:2:2 (F8).
   - **Record 4:2:0.**
     - 4:2:2 encode exists only on Intel QSV (HEVC Rext) and Blackwell (N2, F2).
     - Chromium does not decode it in hardware on Ampere (V5).
   - The CPU fallback in the wheel is GPL libx264/libx265 (R4).
6. **The NVENC 12-session cap is a hard per-system limit, shared by `*_nvenc`, `*_d3d12va` and `*_mf` on NVIDIA** (N10, measured PyAV 19.0.2).
   - More than 12 cameras need a second engine (QSV, measured outside the pool), nvJPEG, or CPU.
   - Remote-desktop tools can hold sessions. nvidia-smi showed 1 foreign session during clip generation, with Parsec/Sunshine running (IP §2; FN §2).
   - The Intel "no limit" claim is Jellyfin-only (J6).
7. **Implementation constraints (measured on Gerald):**
   - feed QSV encoders software frames, because hwctx mode fails (F3);
   - set NVENC `gop_size=0` (K4);
   - pin `i_qfactor=1, i_qoffset=0` (K3);
   - set `dst_color_range=1` for H.264/HEVC targets from JPEG sources (K2);
   - feed **JPEG targets full range** (K5);
   - pass both range arguments to every `reformat` (K2);
   - write D3D12VA output to MP4, not MKV (F7);
   - expect MF to pick the NVIDIA MFT (F7);
   - in the UI, seek `<video>` to `mid` from the real pts, and call WebCodecs `flush()` after each `h264_nvenc` chunk (V1, V3).
8. **jellyfin-ffmpeg adds no royalty-free hardware video codec.**
   - Its only target-relevant addition is `mjpeg_videotoolbox` (P3, 4:2:0 input), behind a subprocess pipe (JFF §3, summary).
   - A self-built PyAV against upstream FFmpeg plus patch 0047 would keep the in-process API (JFF summary; inferred there).

## 5. Pending tonight's bench (23:00, timed, one item at a time)

**Req 11 / 17:35 JPEG-vs-H.264/HEVC bench at matched quality** [code]:
- `S/intra_compare/bench_matched_stream.py` (single stream) and `S/intra_compare/bench_matched_concurrent.py` (N streams).
- Paths: jpeg_turbo, ff_mjpeg, mjpeg_qsv, nvJPEG, NVENC, QSV and libx264/libx265.
- Settings come from `matched_settings.json`.
- Range rules: JPEG full range, H.264/HEVC limited (`benchpaths.py:16-18`, `ALL_PATHS` at :47-49).
- Use these for every JPEG item.

Items in `S/hw_accel_target/` (FN §9; IP §8):

| id | what | scope note |
|---|---|---|
| B-QSV-1, B-NV-1 | per-stream fps and CPU per frame, QSV / NVENC, 720p/1080p; sources nv12/yuy2/yuy2native/mjpeg_cpu/mjpeg_qsv | `--gops intra` only (req 10). **Do not use its `mjpeg_qsv` rows** (K5 range bug) unless the bug is fixed first |
| B-DEC-1 | source pipeline cost (YUY2 convert; MJPEG CPU vs QSV decode) | keep |
| B-QSV-C1, C2, C4; B-NV-C1, C2 | stream scaling 1/4/8/16 + limit probe (h264/hevc/mjpeg_qsv, h264/hevc_nvenc), 1080p | `--gop intra` only. Run the mjpeg_qsv scaling with `bench_matched_concurrent.py` instead |
| B-CPU-1 | CPU baselines (mjpeg, ffv1, libsvtav1, libvpx-vp9) | keep mjpeg and ffv1 intra. AV1/VP9 are not target candidates (§3.3) |
| IP-SYNC/SEEK/SCRUB-E35/E45 | Electron decode cost: H.264/HEVC intra vs JPEG path, N = 4/8 | keep (req 9 playback side) |

Gaps to close before 23:00 [code; inferred from the scripts]:
- **`bench_encode_stream.py` JPEG range bug (K5):** limited-range input reaches `mjpeg_qsv` at `:112` and `:120-124`. Either fix it (feed full range to JPEG targets), or keep the script for non-JPEG pipeline-cost items only.
- **`bench_encode_stream.py` uses default rate control, not `matched_settings.json`.**
  - Its `ENC` table (`:49-66`) has empty QSV options and no `i_qfactor`.
  - So its bytes/frame are not at matched quality.
  - The matched comparison belongs to the intra_compare scripts above.
- Drop or deprioritise:
  - every `gop30` item (B-QSV-C6, B-QSV-C7, B-NV-C4 and the gop30 halves above);
  - `vp9_qsv` scaling (B-QSV-C3): Intel-only, not a target candidate;
  - B-MF-1: MF uses the same NVENC as `*_nvenc` (F7, N10).
- The NVENC limit under PyAV 19.0.2 is already measured (N10). The limit probe only needs to re-confirm it under load.

## 6. Not tested / limits / NOT VERIFIED

- Hardware physically tested: only NVIDIA Ampere (RTX 3070) and Intel Xe-LP (RPL-S UHD 770). Every Turing, Ada, Blackwell, other TGLx, MTL/ARL/LNL, Arc, AMD and Apple cell is from primary sources only.
- NVIDIA NOT VERIFIED:
  - nvJPEG encode on Turing/Ada/Blackwell;
  - whether nvJPEG's hardware-decode list covers GeForce Ada/Blackwell, and whether it decodes 4:2:2 there (N7);
  - nvImageCodec on Linux;
  - planar YUV input in nvJPEG 12.4, and YUV through another binding (N9).
  - nvJPEG capability text is from the 13.5 docs; the measured stack is 12.4.0.76 (N6).
- Intel NOT VERIFIED:
  - Windows codec support for MTL/ARL/LNL/BMG. It is read from the Linux media-driver tables (I6).
  - Intel/Linux QSV through the PyPI wheel; likely unusable per code (§3.2).
  - Windows-on-ARM64 `*_d3d12va`/`*_mf` (§3.2).
- Market NOT VERIFIED:
  - the share of 2020+ CPUs that are F/KF or otherwise have no iGPU (I5, A5);
  - the market shares of Intel, AMD and Apple, so "most CPUs" cannot be quantified.
- Other NOT VERIFIED:
  - Intel, AMD and Apple session limits (J6);
  - AMD `*_d3d12va`/`*_mf`/`*_amf` encode (A7);
  - the AMD 4:2:2 MJPEG decode conclusion (A6);
  - AMD vendor-vs-vendor cells (J9);
  - Apple hardware JPEG encode and HEVC 4:2:2 (P3, P4);
  - the base-M1 codec list (P1).
- Unexplained: why the H.264/HEVC `*_qsv`/`*_cuvid` decodes differ from software in the chroma planes (63.3–63.7 dB), while Y is identical (F9).
- FFV1 on Vulkan ran only on Ampere, CLI only (N12). Intel (a Vulkan 1.4 device), AMD and Apple (MoltenVK) were not tested.
- Not tested:
  - QSV hwctx with a manually sized frames pool (F3);
  - forcing `*_mf` onto the Intel MFT (F7);
  - the `hevc_qsv` 4:2:2 shader path on other TGLx parts;
  - `av1_qsv` decode via native `av1`+hwaccel in PyAV (harness limit, FN §4).
- Playback was tested with NVIDIA decode only. Not tested:
  - Intel/AMD/Apple Chromium decode;
  - machines without HEVC hardware;
  - HEVC 4:2:2 playback (IP §6);
  - decoded-pixel fidelity of camera JPEGs fetched from MKV (V4).
- Matched quality:
  - two camera models in one room;
  - the YUY2 sets are only 8 frames per camera, and the 720p YUY2 class is derived;
  - SSIM is on Y only, and there is no VMAF;
  - results depend on presets (NVENC p4/ll, QSV default CQP, libjpeg-turbo non-fastdct) and on this machine's drivers (IC §12).
- No timing, CPU-cost or stream-scaling numbers yet (§5).
- The NVIDIA matrix rows used are representative GeForce rows, not the full table (N1). GTX 1650 (6th-gen NVENC) has no HEVC B-frames, which does not matter for intra-only.

## 7. How to reproduce (repo root `C:/Users/Dom/GitHub/freemocap/skellycam`)

```
# static wheel queries (no device opened)
uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/wheel_hw_pixfmts.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/sw_encoders_pyav19.py
# functional encode/decode matrix (PyAV 19.0.2), then the d3d12/pictreset/decode stages and PSNR v2
uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/pyav19_functional.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/pyav19_functional.py --only h264_d3d12va,hevc_d3d12va,av1_d3d12va --skip-decode --tag d3d12
uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/merge_functional.py d3d12
uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/pyav19_functional.py --stage decode --tag decode
uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/merge_functional.py decode --append
uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/recompute_psnr.py
# range re-check for JPEG targets (VERIFY_method; Intel QSV only, no timing)
uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/verify_range_check.py
# matched-quality sweep (intra_compare)
uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_compare/camera_jpeg_quality.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_compare/sweep.py --paths <ids> --keep-media
uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_compare/analyze.py
# playback of intra H.264/HEVC vs JPEG (intra_playback)
uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_playback/gen_intra_clips.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron <35|45|chrome> --suite intra_functional
# read-only probes: Get-PnpDevice -Class Display; vulkaninfo; nvidia-smi -q -d ENCODER_STATS
# sources saved under the scratchpad hw_accel_target/findings_src/ (2026-11-09):
curl -sL -o nvjpeg_index.html https://docs.nvidia.com/cuda/nvjpeg/index.html   # sha256 5d2f3d74c05b136a32fc89a00b3a4a2dc9bcea9535b3c5f8691a2bf2399db5ef
curl -sL -o ffqsv/qsv_internal.h https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/libavcodec/qsv_internal.h   # sha256 c75d4fbbc5b3b63b22d134d4a6acc32d197f33f58fbbaa3d671fdaacc1c9325f
curl -sL -o ffqsv/hwcontext_qsv.c https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/libavutil/hwcontext_qsv.c   # sha256 b719cf0c814eeea1e7a5b3906f68057f330f0198b928d1656fa061f6d8a92e4b
```

Primary-source copies:
- NVIDIA/Intel: `R/hw_accel_target/sources_nv_intel/`. FETCH_MANIFEST.txt has the sha256 values.
- AMD/Apple: the scratchpad `hw_accel_target/src_amd_apple/`, pinned to the commits and tags in AAC §0.

## 8. Verification

Two adversarial verifiers reviewed the draft:
- provenance: `R/hw_accel_target/VERIFY_provenance.md`;
- methodology: `R/hw_accel_target/VERIFY_method.md`, which added the new measurement `R/hw_accel_target/verify_method_range_check.json`.

I re-checked each refutation against the cited files before applying it. I also fetched FFmpeg n9.0.2 `qsv_internal.h` and `hwcontext_qsv.c` myself to confirm the Linux QSV code path.

### 8.1 Refuted claims and what changed

| # | draft claim | checked against | change |
|---|---|---|---|
| X1 | §3.4 hevc_nvenc 55,112 / 144,376 "from matched_summary.md" | MS:56 = 53,975; MS:80 = 141,655. The draft values are from IC NOTES §6, which is stale | fixed in §3.4; NOTES-vs-MS mismatch flagged |
| X2 | F9: QSV/NVDEC decode "bit-identically" | FP:359-360, 366-367, 380-381, 387-388: PSNR-Y 99, all planes 63.3–63.7 | F9 rewritten: Y plane identical; all planes identical only for VP9/AV1 and native+hwaccel |
| X3 | N10 cites `nvenc_sessions.json`; Vulkan as measured | that file has `"pyav": "18.0.0"`. `nvenc_sessions_19.0.2.json` and `verify_method_pool.json` (with control) are PyAV 19.0.2. Vulkan was CLI only (GEF §2.4) | N10 re-cited; Vulkan labelled CLI, no control, inferred |
| X4 | A6 labelled [code+measured] | AAC line 122 says "inferred … NOT VERIFIED" | relabelled [inferred]; NOT VERIFIED on AMD hardware |
| X5 | A1 / §3.1 legend: every AMD codec is 4:2:0 | AAC §2.2: Mesa `ac_video.c:540-545` YUYV JPEG decode; AMF docs line 106 YUY2 | "4:2:0 only" limited to AVC/HEVC/VP9/AV1; JPEG decode exception added |
| X6 | V4: camera JPEGs 800/800 seeks | IP:18-19, 66: the 800/800 used `mjpeg_qsv` re-encoded JPEGs. Camera JPEGs: CC:150 88/88 stills; IP:32-33 450/450 byte-identical fetch + decode | V4 split into three cases |
| X7 | Q7: at 45 dB "2.9–5.6x" | MS:97-111: 77,458/27,378 = 2.83 and 77,458/14,236 = 5.44 | 2.8–5.4x (4:2:2 JPEG vs 4:2:0 video); 2.5–5.0x at matched 4:2:0 |
| X8 | §3.3 passthrough row "0.64–1.02x" camera bytes | MS "x passthrough" column: 0.64–0.91. The 1.02 is h264_qsv against libjpeg-turbo | fixed in §3.3 and Q4 |
| X9 | K2 / §4.7 / §5: the only range rule is `dst_color_range=1` for H.264/HEVC, and the bench is fine apart from rate control | `bench_encode_stream.py:112, 120-124` feed limited range to `mjpeg_qsv`; `verify_method_range_check.json` decodes Y 16..235 | K5 added; F2, §4.4, §4.7 and §5 updated. K2 itself holds for tagged decoded frames (FN §6.2-6.3) |

### 8.2 Weak claims and what changed

- Line citations fixed (re-read in FP):
  - N5 → FP:312-313 (+321-322, 330-331);
  - F3 → FP:125, 134, 157;
  - F4 → FP:300-303 (+201);
  - F6 → FP:314-317;
  - F1 → FP:124-166;
  - F7 → FP:292-298.
- Q7 / implication 2 restated at matched chroma, with "luma-matched only".
  - Recomputed from MS:11-25: 4:2:0 JPEG vs H.264/HEVC 4:2:0 is 1.26–2.54x (libjpeg-turbo 1.51–2.27, mjpeg_qsv 1.69–2.54, nvJPEG 1.26–1.90).
  - At 4:2:2: 1.92x.
- Implication 3 / Q4 restated as 9–36% vs camera bytes, with the generation-loss caveat (IC §2). The libjpeg-turbo comparison is kept separate.
- nvJPEG presented as the smallest JPEG: Q2a added (target A PSNR-Y 50.80 vs 52.24; target B 0.92x vs 0.89x/0.88x; MS:18, 23, 106-108).
- nvJPEG version gap noted, and NV12 input = 4:2:0 only. The "must both be NVJPEG_CSS_420" text was confirmed in the saved 13.5 copy (N6, N9).
- N8 / §3.1 Ampere decode: hybrid CPU+CUDA only; GPU_ONLY / HW_GPU_ONLY fail (`R/gpu_encode/nvimgcodec_jpeg.md`).
- N7 / Ada and Blackwell cells: "architecture listed; GeForce applicability NOT VERIFIED; doc excludes only 410/411".
- I6 and J5 relabelled [source (transcribed)]. I5's "Quick Sync Video: No" quote attributed to the 265KF only (NI:149-153).
- AMD vendor-vs-vendor added as J9 (Navi24 AV1 decode; Cezanne and Granite Ridge VCN versions). C1 libx264/libx265 4:2:2 cell filled ("yes"; `yuv422p` is in the JSON).
- N1 now says "representative rows".
- §3.1 Intel TGLx AV1 cells say "measured on RPL-S".
- §3.2 Intel/Linux marked NOT VERIFIED and likely unusable [inferred from code]. Confirmed in n9.0.2: `qsv_internal.h:26-28`, `hwcontext_qsv.c:2548-2551`. Windows-on-ARM64 row added (`wheel_hw_codecs.md`).
- §3.3:
  - "measured" scoped to the RTX 3070 / UHD 770;
  - JPEG row marks RTX 40/50 and Windows MTL+ as inferred;
  - a "verified through PyAV 19.0.2" column added.
- §2.8 scoped to "Gerald, these presets, this content", and preset dependence added to §6 (IC §12:309).
- §5 cites `S/intra_compare/bench_matched_stream.py` / `bench_matched_concurrent.py` as the req-11 bench.
- J10 added: Jellyfin's "QSV only on Windows" vs the measured `*_d3d12va` on the UHD 770 (FP:293, 297).
- P3 notes that `mjpeg_videotoolbox` takes 4:2:0 input (JFF:70).

### 8.3 Checked and unchanged (per VP §3, VM §3)

- nvJPEG quotes, against the saved copy (sha256 matches) and a live re-fetch.
- NVIDIA and Intel source tables, and the Jellyfin grep returning 0 matches.
- The other matched-quality numbers.
- K3 and K4 code.
- The licensing quote IDs.
- Intra-only status of every compared H.264/HEVC stream.
- The §4.1 conclusion: no royalty-free video codec meets the target.

### 8.4 Follow-ups for other owners

- intra_compare: `R/intra_compare/NOTES.md` §6 is out of sync with `matched_summary.md`.
- hw_accel_target bench: fix or bypass the K5 range bug before 23:00.
- FN §4: the "bit-identical" wording needs the F9 correction.
