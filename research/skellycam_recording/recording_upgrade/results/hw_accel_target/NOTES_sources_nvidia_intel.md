# hw_accel_target: sources for NVIDIA and Intel

Part: primary sources for NVIDIA and Intel hardware encode/decode, checked against Jellyfin's docs. No timing numbers
(other agents running). Two read-only probes and one static PyAV query were run. AMD, Apple, Rockchip and QSV/NVENC
functional tests are other parts of this topic.

Labels: **measured** (a result file), **source** (primary source, accessed 2026-11-09), **code** (file:line at a pinned tag),
**inferred** (kept short). Paths are relative to `research/skellycam_recording/recording_upgrade/` unless they start
with `research/`.

Source copies and extracts, so a verifier can check quotes without re-fetching: `results/hw_accel_target/sources_nv_intel/`.
- `FETCH_MANIFEST.txt`: sha256 of every raw download (curl, 2026-11-09).
- `jellyfin_{main,intel,nvidia,known_issues}.txt`: page text. Line numbers below refer to these files.
- `nvidia_support_matrix_extract.md`: matrix rows parsed from the saved HTML.
- `nvenc_app_note_13.1_tables.md`, `nvdec_app_note_13.1_tables.md`, `nvdec_prog_guide_13.1_tables.md`, `nvenc_13.1_quotes.txt`.
- `intel_media_driver_26.3.5_media_features.md` (full file), `intel_media_driver_26.3.5_README_excerpt.md` (README lines 70-145).
- `intel_com_webfetch_transcripts.md`: intel.com returns HTTP 403 to curl, so oneVPL docs and ark pages were read with
  WebFetch, which transcribes them with a small model. Those cells are marked **source (transcribed)**. They are weaker
  than the saved raw pages.

Main URLs:
- Jellyfin: https://jellyfin.org/docs/general/post-install/transcoding/hardware-acceleration/ plus `/nvidia`, `/intel`, `/known-issues`.
- NVIDIA matrix: https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new
- NVIDIA Video Codec SDK 13.1 (the docs index labels it "Latest Release"): https://docs.nvidia.com/video-technologies/video-codec-sdk/13.1/ (`nvenc-application-note/`, `nvdec-application-note/`, `nvenc-video-encoder-api-prog-guide/`, `nvdec-video-decoder-api-prog-guide/`).
- Intel media-driver at tag `intel-media-26.3.5`: https://github.com/intel/media-driver/blob/intel-media-26.3.5/README.md and `/docs/media_features.md`.
- Intel oneVPL "Media Capabilities Supported by Intel Hardware" v1.1 (doc 772607, dated 3/07/2024): https://www.intel.com/content/www/us/en/docs/onevpl/developer-reference-media-intel-hardware/1-1/overview.html and `details.html`.
- FFmpeg n9.0.2 (the version PyAV 19.0.2 bundles): https://github.com/FFmpeg/FFmpeg/blob/n9.0.2/libavcodec/allcodecs.c, `hwaccels.h`, `nvenc.c`, `qsvenc_jpeg.c`, `qsvdec.c`.

## 1. Bottom line

- source: on **every RTX 3000-series GeForce**, NVENC encodes H.264 (8-bit 4:2:0 and 4:4:4) and HEVC (8/10-bit 4:2:0 and 4:4:4). It does **not** encode AV1, VP9 or any 4:2:2 (§2).
- source: **AV1 encode** starts at Ada (RTX 4000). **4:2:2 encode** (H.264 and HEVC) and H.264 10-bit start at Blackwell (RTX 5000) (§2).
- source: on **Intel iGPUs from 2020** (Tiger Lake, Rocket Lake, Alder Lake, Raptor Lake), the media engine encodes H.264, HEVC, **VP9** and **JPEG**, but **not AV1**. AV1 encode starts at Meteor Lake/Arrow Lake, Lunar Lake and Arc. Lunar Lake and Arc B-series (Battlemage) have **no VP9 encode** (§4).
- source: Intel hardware **JPEG encode accepts YUY2 (4:2:2)** and can write 4:2:2 JPEG on every platform since Skylake. Intel JPEG decode handles 4:2:2. That matches the cameras' 4:2:2 MJPEG (§4.2).
- inferred: the only codecs with **fixed-function encode on both RTX 3000+ and every 2020+ Intel iGPU** are **H.264 and HEVC**, both royalty-bearing. No royalty-free fixed-function codec covers both, because AV1 fails on RTX 3000 and Tiger Lake–Raptor Lake, and VP9 fails on all NVIDIA. The closest royalty-free option is JPEG: Intel fixed-function (source), and NVIDIA through CUDA nvJPEG, which is measured but not in FFmpeg/PyAV (`results/gpu_encode/NOTES.md` §6).
- source (transcribed): Intel desktop **F/KF SKUs have no iGPU, so no Quick Sync**. ark examples span 2020–2024: i5-10400F, i9-11900KF, i5-12400F, i7-14700KF, and Core Ultra 7 265KF ("Intel® Quick Sync Video": "No"). **The share of F/KF SKUs is NOT VERIFIED**; no primary source gives one (§5).
- Jellyfin and the vendors **agree on every per-generation claim Jellyfin makes** for NVIDIA and Intel (§3, §4.3), with one exception: Jellyfin's main page says no NVIDIA GPU decodes H.264 10-bit, while NVIDIA documents High10 decode on Blackwell (DISAGREE, §3). Jellyfin says nothing about VP9, JPEG or 4:2:2 for either vendor, so those cells are vendor-only.
- measured (new): on Gerald, the Intel UHD 770 is now present, and its Windows Vulkan driver (101.7088) exposes **Vulkan Video decode only** (AV1, H.264, H.265), with no encode extension. The RTX 3070 exposes encode H.264/H.265 plus decode AV1/H.264/H.265/VP9 (`results/hw_accel_target/vulkaninfo_video_ext.txt`, `display_devices_probe.txt`).
- measured (new): in the PyAV 19.0.2 wheel, `h264_qsv` accepts only `nv12`. `hevc_qsv` accepts `yuyv422`/`y210le`, `mjpeg_qsv` accepts `yuyv422`, and `h264/hevc/av1_nvenc` list `nv16`/`p210le`, so FFmpeg's 4:2:2 NVENC path is compiled in (`results/hw_accel_target/wheel_hw_pixfmts_19.0.2.json`).

## 2. NVIDIA per-generation matrix (GeForce)

Representative rows from the support matrix are RTX 2080 (Turing), RTX 3050/3070 (Ampere), RTX 4060/4070 (Ada) and RTX 5050/5070/5090 (Blackwell) (`sources_nv_intel/nvidia_support_matrix_extract.md`). The SDK 13.1 application notes group the architectures as "Ampere and TU GPUs | Ada GPUs | Blackwell GPUs" for NVENC, and "Turing/GA100/Hopper | GA10x3 and Ada | Blackwell" for NVDEC.

### 2.1 Encode (NVENC)

| codec | Turing (RTX 20, GTX 16) | Ampere (RTX 30) | Ada (RTX 40) | Blackwell (RTX 50) | evidence |
|---|---|---|---|---|---|
| H.264 | Y: 8-bit 4:2:0, 4:4:4, lossless. N: 4:2:2, 10-bit | same as Turing | same as Turing | Y: adds 4:2:2 and High10 | source: matrix cols "H.264 (AVC) YUV 4:2:0/4:2:2/4:4:4/Lossless" = Turing/Ampere/Ada "YES NO YES YES", Blackwell "YES YES YES YES". App note H.264 table: "High10 profile ... N \| N \| Y", "4:2:2 encoding \| N \| N \| Y" |
| HEVC | Y: 8/10-bit 4:2:0, 4:4:4, lossless, 8K, B-frames (7th-gen NVENC). N: 4:2:2 | same as Turing | same as Turing | Y: adds 4:2:2 | source: matrix "H.265 (HEVC) YUV 4:2:2" = NO for RTX 2080/3070/4070, YES for RTX 5070. App note HEVC table "4:2:2 encoding \| N \| N \| Y", "8K encoding: Support for encoding 8192 x 8192 Content. \| Y \| Y \| Y" |
| AV1 | N | **N** | Y: 8/10-bit 4:2:0, up to 8192x8192 | Y | source: matrix "AV1 YUV 4:2:0" NO/NO/YES/YES. App note AV1 table "Main profile: ... 8-bit and 10-bit content up to 8192 x 8192 content. \| N \| Y \| Y". measured: `av1_nvenc` fails on the RTX 3070 (`results/gpu_encode/ff_functional.md`) |
| VP9 | N | N | N | N | source: app note §2 "NVENC can encode H.264 8-bit and H.264 10-bit, HEVC 8-bit, HEVC 10-bit, AV1 8-bit and AV1 10-bit contents." The matrix has no VP9 encode column |
| JPEG | no fixed-function encoder | CUDA nvJPEG only | NOT VERIFIED (inferred: nvJPEG is CUDA, so any CUDA GPU) | NOT VERIFIED | measured: nvJPEG 4:2:2 and 4:2:0 encode on Ampere (`results/gpu_encode/NOTES.md` §6). No JPEG column in the NVENC matrix |
| FFV1 (Vulkan compute) | NOT VERIFIED | Y: byte-exact, CLI only | NOT VERIFIED | NOT VERIFIED | measured: `results/gpu_encode/NOTES.md` §3. Not in PyAV wheels (same file §4) |

Caveat rows (source, matrix):
- "GeForce GTX 1650 GDDR6 | Turing | 6th Gen" and GTX 1630 / MX550 have 6th-gen NVENC with "HEVC B Frame support" = NO.
- "GeForce MX450 | Turing | N/A ... 0" NVENC, "GeForce MX570 A | Ampere | N/A | M | 1 | 0 | 0" and "GeForce GT 1030 | Pascal | N/A | D | 1 | 0 | 0" have **no NVENC**. So "Ampere" alone does not guarantee NVENC. Every RTX-branded desktop row from 2000 onwards lists NVENC.

### 2.2 Decode (NVDEC)

| codec | Turing | Ampere (GA10x) | Ada | Blackwell | evidence |
|---|---|---|---|---|---|
| H.264 | Y: 8-bit 4:2:0, max 4096x4096. N: 10-bit, 4:2:2 | same as Turing | same as Turing | Y: adds High10 and High422, max 8192x8192 | source: NVDEC app note "H264 High10/High422 profiles \| N \| N \| Y". Prog guide capability table "Blackwell ... High 10 and High 422 (exclude MBAFF) up to Level 6.2", GA10x/AD10x "Max: 4096x4096" |
| HEVC | Y: 8/10/12-bit 4:2:0 and 4:4:4. N: 4:2:2 | same as Turing | same as Turing | Y: adds 4:2:2 10/12-bit | source: app note "HEVC main 422 10/12 profiles \| N \| N \| Y". Matrix HEVC 4:2:2 columns NO except Blackwell |
| AV1 | **N** | Y: 8/10-bit | Y | Y | source: app note "AV1 Main Profile decoding \| N \| Y \| Y" (Turing/GA100/Hopper, GA10x and Ada, Blackwell). Prog guide "Turing/GA100 ... Unsupported", "GA10x/AD10x ... Max: 8192x8192" |
| VP9 | Y: 8/10/12-bit, max 8192x8192 | Y | Y | Y | source: app note "VP9 Profile 0 \| Y \| Y \| Y"; matrix VP9 8/10/12 YES |
| MJPEG/JPEG | hybrid CUDA+CPU, not fixed-function | **4:2:2 fails via FFmpeg** | NOT VERIFIED | NOT VERIFIED | source: NVDEC prog guide 13.1 codec list "Hybrid (CUDA + CPU) JPEG". measured: `mjpeg_cuvid` / `-hwaccel cuda` fail on the camera 4:2:2 JPEGs, while nvJPEG decodes them (`results/gpu_encode/NOTES.md` §1, §5) |

### 2.3 NVIDIA sessions, resolution, 4:2:2 in FFmpeg

- source: NVENC app note 13.1: "On non-qualified GPUs, the number of concurrent encode sessions is limited to 12 per system. This limit of 12 concurrent sessions per system applies to the combined number of encoding sessions executed on all non-qualified cards present in the system." The matrix lists "Max # of concurrent sessions" = 12 for every GeForce row in the extract.
- measured: the limit is 12 on driver 610.88, and the 13th session fails across nvenc/vulkan/d3d12va/mf (`results/gpu_encode/nvenc_sessions.json`, NOTES §1).
- source: NVENC app note: "unless Split Frame Encoding is enabled, performance with single encoding session cannot exceed performance per NVENC". The matrix lists 1 NVENC for RTX 3070/4070/5070, 2 for RTX 4070 Ti / 5070 Ti, and 3 for RTX 5090.
- NOT VERIFIED: the NVENC H.264 maximum encode resolution. It is not stated in the 13.1 app note or programming guide text; it is only queryable at runtime via `NvEncGetEncodeCaps`.
- code: FFmpeg n9.0.2 `libavcodec/nvenc.c:60-65` adds `NV16, P210, P212, P216` under `#ifdef NVENC_HAVE_422_SUPPORT`. `nvenc.c:445-451` checks `NV_ENC_CAPS_SUPPORT_YUV422_ENCODE` and logs "YUV422P not supported". `nvenc.c:1263-1266` forces H.264 High 4:2:2 for 4:2:2 input.
- measured: the PyAV 19.0.2 wheel's `h264_nvenc`/`hevc_nvenc` list `nv16` and `p210le` (`wheel_hw_pixfmts_19.0.2.json`), so 4:2:2 NVENC would work from PyAV on Blackwell.
- inferred: on Ampere and Ada, the cameras' 4:2:2 has to be downsampled to 4:2:0 or upsampled to 4:4:4 (`yuv444p` is in the same list, and 4:4:4 encode is Y in the app note). NOT TESTED here.

## 3. NVIDIA: Jellyfin claims vs vendor

| Jellyfin claim (jellyfin_nvidia.txt line, quote) | vendor primary source | verdict |
|---|---|---|
| L24 "Decoding & Encoding H.264 8-bit - Any NVIDIA GPU supporting NVENC/NVDEC" | matrix: H.264 4:2:0 YES on every row with NVENC | AGREE |
| L26 "Decoding & Encoding H.264 10-bit - Blackwell and newer (WIP, it's not currently enabled in Jellyfin)" | prog guide (text line 579; `sources_nv_intel/nvenc_13.1_quotes.txt` L4) "Starting from Blackwell generation, NVIDIA GPUs support high-bit-depth H264 encoding (H264 high-10 profile...)"; NVDEC app note High10 N/N/Y | AGREE |
| jellyfin_main.txt L84 "The hardware decoding of H.264 / AVC 10-bit (High 10 profile) video is not supported by any Intel, NVIDIA and AMD GPU." | NVDEC prog guide: Blackwell "High 10 and High 422 ... up to Level 6.2" | **DISAGREE** (Jellyfin's main page is out of date for Blackwell; its own NVIDIA page L26 agrees with NVIDIA) |
| L35 "Encoding HEVC 10-bit - Pascal and newer" | prog guide (text line 579; `sources_nv_intel/nvenc_13.1_quotes.txt` L4) "Starting from Pascal generation, NVIDIA GPUs support high-bit-depth HEVC encoding" | AGREE |
| L42 "Decoding AV1 8/10-bit - Ampere and newer" | NVDEC app note "AV1 Main Profile decoding \| N \| Y \| Y"; GA100 (data-centre Ampere) excluded | AGREE (GA10x consumer Ampere) |
| L44 "Encoding AV1 8/10-bit - Ada Lovelace and newer" | prog guide (text line 579; `sources_nv_intel/nvenc_13.1_quotes.txt` L4) "Starting from Ada generation, NVIDIA GPUs support high-bit-depth AV1 encoding"; matrix AV1 NO for Ampere | AGREE |
| L19 "some low-end and mobile models (e.g. GT1030 and MX450) are exceptions" | matrix: GT 1030 has 0 NVENC but 1 NVDEC; MX450 has 0 NVENC and 0 NVDEC | AGREE (GT 1030 still decodes) |
| jellyfin_known_issues.txt L70-75 "artificial limit ... 590 and newer \| Up to 12 encoding sessions" (8 for 550-58x, 5 for 530-546, 3 pre-530) | app note: "limited to 12 per system"; measured 12 on 610.88 | AGREE on 12. Per-driver history is Jellyfin-only |
| (nothing on VP9, JPEG, 4:2:2 or FFV1) | §2 | vendor-only |

## 4. Intel per-generation matrix

media-driver README groups the platforms (L82-87): "TGLx (TGL: Tiger Lake, RKL: Rocket Lake, ADL-S/P/N: Alder Lake, RPL-S/P: Raptor Lake)", "Alchemist(DG2)/ATSM", "MTLx (MTL: Meteor Lake, ARL-S/H: Arrow Lake)", "LNL (Lunar Lake)", "BMG (Battlemage)".

README legend (L140-141): "E - Hardware Encoding, Low Power Encoding(VDEnc/Huc)", "Es - Hardware(PAK) + Shader(media kernel+VME) Encoding".

The media-driver is the **Linux VA-API** driver. For Windows, the oneVPL capability doc covers 11th–13th Gen and Arc A only; it is older than MTL/LNL/ARL/BMG.

### 4.1 Encode

| codec | TGL / RKL / ADL / RPL (TGLx) | MTL / ARL (MTLx) | LNL | Arc A (DG2) | Arc B (BMG) | evidence |
|---|---|---|---|---|---|---|
| H.264 | Y: 8-bit, max 4k | Y, 4k | Y, 4k | Y, 4k | Y, 4k | source: README L112 AVC "D/E" (TGLx "D/E/Es"); media_features.md L61-62 AVC max "4k". source (transcribed): oneVPL "AVC 8-bit, 4:2:0" Y for 11th, 12th/13th Gen and Arc A; ark B580 "H.264 Hardware Encode/Decode": "Yes" |
| HEVC 4:2:0 / 4:4:4 | Y: 8/10-bit, max 8k | Y, 16k | Y, 16k | Y, 16k | Y, 16k | source: README L117, L119-120, L122 "D/E"; media_features.md L65-68 (8k TGLx, "16k***" = 16384x12288 for MTL+, DG2, LNL, BMG) |
| HEVC 4:2:2 | **Es only** (PAK+shader; Full-Feature build). Windows: "fixed-function + shader-based ... ✔4k" | **N** (D only) | Y (E) | Y (E). Windows: "✔16k (Windows Only)" | Y (E) | source: README L118 "HEVC 8bit 422" row = NVL D/E, PTL D/E, BMG D/E, LNL D/E, MTLx **D**, DG2 D/E, DG1 D/Es, TGLx **D/Es** (Free-Kernel build: D). source (transcribed): oneVPL ENCODE-11-12 / ENCODE-DISCRETE rows |
| AV1 | **N** | Y: 8/10-bit 4:2:0, 8k | Y | Y | Y | source: README L132-133 AV1 TGLx "D" (no E), MTLx/LNL/DG2/BMG "D/E"; media_features.md L73-76 input NV12/P010, max 8k. source (transcribed): oneVPL AV1 encode only Arc A among the platforms it covers; ark B580 "AV1 Encode/Decode": "Yes" |
| VP9 | Y: 8/10-bit, 4:2:0 and 4:4:4, 8k | Y | **N** | Y | **N** | source: README L126-129 VP9 BMG "D", LNL "D", others "D/E"; media_features.md L69-72 (BMG and LNL cells blank). source (transcribed): oneVPL VP9 8/10-bit encode Y for 11th–13th Gen and Arc A |
| JPEG / MJPEG | Y | Y | Y | Y | Y | source: README L115 JPEG "D/E" for every column from SKL; media_features.md L63-64 max 16k, L79 "JPEG encoding supports input format NV12/YUY2/UYVY/ABGR/Y8 and output format YUV400/YUV420/YUV422H_2Y/YUV444/RGB24." source (transcribed): oneVPL ENCODE-11-12 MJPEG "4:2:2 (YUY2) \| ✔16k" |
| FFV1 (Vulkan compute) | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | measured: the UHD 770 is a Vulkan device (apiVersion 1.4.323, driver 101.7088; `vulkaninfo_video_ext.txt`). ffv1_vulkan was never run on it, and is CLI-only (not in PyAV) |

### 4.2 Decode

| codec | TGLx | MTLx | LNL | DG2 | BMG | evidence |
|---|---|---|---|---|---|---|
| H.264 | Y: 8-bit 4:2:0, 4k | Y | Y | Y | Y | source: media_features.md L8-9 AVC output NV12, max 4k |
| HEVC | Y: 8/10/12-bit, 4:2:0, 4:2:2, 4:4:4, 8k | Y, 16k | Y, 16k | Y, 16k | Y, 16k | source: README L117-125 "D" for TGLx and later; media_features.md L16-21 (outputs NV12/YUY2/AYUV, P010/Y210/Y410, P016/Y216/Y416) |
| AV1 | Y: 8/10-bit, 8k | Y, 16k | Y | Y | Y | source: README L132-133 "D"; media_features.md L28-31. source (transcribed): oneVPL AV1 decode Y for 11th–13th Gen |
| VP9 | Y: 8/10/12-bit, 4:2:0 and 4:4:4 | Y | Y | Y | Y | source: README L126-131; media_features.md L22-27 |
| MJPEG 4:2:2 | Y, 16k | Y | Y | Y | Y | source: media_features.md L44-45 "4:2:2, 8-bit \| 422H \| 16K \| BDW+" and "422V". source (transcribed): oneVPL DECODE-11-12 "4:2:2, 8-bit → 4:2:2H \| ✔16k". NOT TESTED on Gerald here |
| VVC | N | N | Y | N | N | source: README L134-135 (also PTL and NVL) |

### 4.3 Intel: Jellyfin claims vs vendor

| Jellyfin claim (jellyfin_intel.txt line, quote) | vendor primary source | verdict |
|---|---|---|
| L48 "Decoding & Encoding H.264 8-bit - Any Intel GPU that supports Quick Sync Video (QSV)" | README L112 AVC D/E for every listed platform | AGREE |
| L53 HEVC 8-bit "Gen 9 Skylake ... and newer"; L55 HEVC 10-bit "Gen 9.5 Kaby Lake ... and newer" | README L117, L120: TGLx and later D/E | AGREE (for 2020+ parts) |
| L62 "Decoding AV1 8/10-bit - Gen 12 Tiger Lake (11th Gen Core) and newer" | README L132-133 TGLx "D"; oneVPL AV1 decode on 11th Gen | AGREE |
| L64 "Encoding AV1 8/10-bit - Gen 12.5 DG2 / ARC A-series, Gen 12.7 Meteor Lake ... and newer" | README L132-133 E for DG2, MTLx, LNL, BMG, none for TGLx; ark B580 "AV1 Encode/Decode: Yes" | AGREE |
| L21 "Unlike NVIDIA NVENC, there is no concurrent encoding sessions limit on Intel iGPU and ARC dGPU." | none found. The oneVPL details page has no session statement (transcribed); the media-driver docs read here have none | **Jellyfin-only** (NOT VERIFIED) |
| L44 "Do not use models of Intel processors ending with "F" - those do not have an integrated GPU." | ark (§5) | AGREE. KF SKUs too; Core Ultra 265KF shows "Quick Sync Video: No" |
| L89 "Models like the UHD 770 and Iris Xe feature a second MFX video engine" | ark i7-14700K "Multi-Format Codec Engines": "2" (transcribed) | AGREE |
| L96 "Intel supports OneVPL on Gen 12+ graphics (11th Gen Core and newer processor, namely Tiger Lake & Rocket Lake)." | not checked against an Intel VPL source in this part | Jellyfin-only (NOT VERIFIED) |
| L5 "On Windows QSV is the only available method." | code: FFmpeg also has d3d11va/dxva2/d3d12va decode hwaccels (`hwaccels.h:36-39,45-48,84-87,23-26`) and `*_d3d12va` / `*_mf` encoders (`allcodecs.c:851,859,867-868,880,883`) | Jellyfin scope statement. FFmpeg exposes more paths; their Intel behaviour is NOT VERIFIED |
| jellyfin_known_issues.txt L21: Windows driver bug "from 31.0.101.5186 / 31.0.101.5234 to 31.0.101.5534" (HDR tone-mapping) | measured: Gerald's Intel driver is 32.0.101.7088 (`results/gpu_encode/system_probe.txt`) | outside the range (not affected; inferred from version order) |
| (nothing on VP9, JPEG or 4:2:2) | §4.1, §4.2 | vendor-only |

Intel-internal disagreement: oneVPL marks Arc A HEVC 4:2:2 encode "✔16k (Windows Only)" (transcribed), but the media-driver README L118 gives DG2 "D/E" for HEVC 8bit 422 in both Linux builds. **DISAGREE (vendor vs vendor)**. Linux behaviour is NOT VERIFIED.

## 5. Intel desktop CPUs with no iGPU (F / KF)

source (transcribed), Intel ark (URLs in `sources_nv_intel/intel_com_webfetch_transcripts.md`):

| SKU | launch | code name | GPU on ark |
|---|---|---|---|
| Core i5-10400F | Q2'20 | Comet Lake | no GPU section |
| Core i9-11900KF | Q1'21 | Rocket Lake | no GPU section |
| Core i5-12400F | Q1'22 | Alder Lake | no GPU section |
| Core i7-14700KF | Q4'23 | (Raptor Lake refresh; not asked) | no Processor Graphics / Quick Sync field |
| Core Ultra 7 265KF | Q4'24 | Arrow Lake | "Intel® Quick Sync Video": "No", Xe-cores "0" |
| (contrast) Core i7-14700K | Q4'23 | — | "Intel® UHD Graphics 770", Quick Sync "Yes", Device ID "0xA780" |

- source (transcribed): none of these F/KF pages says a discrete GPU is required.
- NOT VERIFIED: what share of 2020+ Intel desktop SKUs or shipments are F/KF. No primary source was found.
- inferred: an F/KF CPU with no NVIDIA/AMD/Intel GPU has only CPU software encode. The CPU cost then decides (bench topic).

## 6. FFmpeg API per path and OS (FFmpeg n9.0.2; PyAV 19.0.2 wheel column)

code: `allcodecs.c` and `hwaccels.h` @ n9.0.2 (line numbers below). measured: wheel contents from `results/gpu_encode/wheel_hw_codecs.md` and `results/hw_accel_target/wheel_hw_pixfmts_19.0.2.json`.

| vendor / OS | encode APIs (codecs) | decode APIs | in PyAV 19.0.2 wheel |
|---|---|---|---|
| NVIDIA / Windows | nvenc: h264/hevc/av1 (`allcodecs.c:869,884,854`); d3d12va: h264/hevc/av1 (`:867,880,851`); mediafoundation: h264/hevc/av1 via the NVIDIA MFT (`:868,883,859`); vulkan: h264/hevc/av1 (`:876,891,861`) and ffv1 (`:119`) | cuvid: h264/hevc/av1/vp9/mjpeg (`:866,879,850,916,893`); hwaccels nvdec/d3d11va/dxva2/d3d12va/vulkan for h264/hevc/vp9/av1; mjpeg only via nvdec (`hwaccels.h:54`) | nvenc, d3d12va, mf, cuvid. **No vulkan** (`results/gpu_encode/NOTES.md` §4) |
| NVIDIA / Linux | nvenc; vulkan | cuvid; nvdec, vdpau and vulkan hwaccels | nvenc only (manylinux x86_64). No vulkan |
| Intel / Windows | qsv: h264/hevc/av1/vp9/mjpeg (`:872,887,856,921,894`), via oneVPL on D3D11; d3d12va and mf: NOT VERIFIED on Intel; vulkan encode: none (measured: driver 101.7088 exposes no `VK_KHR_video_encode_*`) | qsv: h264/hevc/av1/vp9/mjpeg (`:155,161,855,919,895`); d3d11va/dxva2/d3d12va hwaccels h264/hevc/vp9/av1. **No d3d11va/d3d12va MJPEG hwaccel exists** (`hwaccels.h:23-92`), so Windows Intel MJPEG decode is `mjpeg_qsv` only | qsv, d3d12va, mf; decode hwdevices dxva2/d3d11va/d3d12va/qsv |
| Intel / Linux | qsv (oneVPL on VA-API); vaapi: h264/hevc/av1/vp9/mjpeg (`:874,889,860,920,896`); vulkan (Mesa ANV) encode is debug-gated (`results/gpu_encode/NOTES.md` §7.5) | qsv; vaapi hwaccels incl. mjpeg (`hwaccels.h:55`) | qsv only (manylinux x86_64). **No vaapi** |

FFmpeg pixel formats that matter for 4:2:2 (measured, PyAV 19.0.2 wheel):

| encoder | accepts 4:2:2 input? | formats |
|---|---|---|
| h264_qsv | no | nv12, qsv |
| hevc_qsv | yes | nv12, p010le, p012le, **yuyv422, y210le**, qsv, bgra, x2rgb10le, vuyx, xv30le |
| mjpeg_qsv | yes | nv12, **yuyv422**, bgra, qsv (code: `qsvenc_jpeg.c:91-92`) |
| av1_qsv | no | nv12, p010le, qsv |
| vp9_qsv | no (4:4:4 via vuyx) | nv12, p010le, vuyx, qsv, xv30le |
| h264/hevc/av1_nvenc | listed (nv16, p210le); hardware-gated, Blackwell only | full list in the JSON |

## 7. What this means for the hardware target (inferred, minimal)

| candidate | RTX 3000 | RTX 4000 | RTX 5000 | Intel TGL–RPL iGPU | Intel MTL/ARL | Intel LNL | Arc A | Arc B | royalty-free? |
|---|---|---|---|---|---|---|---|---|---|
| H.264 (4:2:0) | Y | Y | Y | Y | Y | Y | Y | Y | no (licensing topic) |
| HEVC (4:2:0) | Y | Y | Y | Y | Y | Y | Y | Y | no (licensing topic) |
| AV1 | N | Y | Y | N | Y | Y | Y | Y | yes (licensing topic) |
| VP9 | N | N | N | Y | Y | N | Y | N | yes (licensing topic) |
| JPEG 4:2:2 | CUDA nvJPEG (measured), not FFmpeg | NOT VERIFIED | NOT VERIFIED | fixed-function | fixed-function | fixed-function | fixed-function | fixed-function | licensing topic |
| any 4:2:2 video codec | N | N | Y (H.264/HEVC) | HEVC via shader-assisted path, ≤4k | N | HEVC | HEVC | HEVC | — |

- inferred: the target "hardware encode on RTX 3000+ and most 2020+ CPUs" is met only by H.264 and HEVC. Every royalty-free option fails at least one of RTX 3000 or Tiger Lake–Raptor Lake.
- inferred: JPEG is the only royalty-free-candidate format accelerated on both vendors' 2020+ parts. On NVIDIA it needs nvImageCodec (CUDA), not PyAV/FFmpeg. For MJPEG cameras, passthrough needs no encoder at all (`results/gpu_encode/NOTES.md` §1).
- inferred: F/KF CPUs with no discrete GPU get no hardware path from either vendor.

## 8. Open items for the functional / bench parts

- Now possible because the iGPU is present (`display_devices_probe.txt`: "OK True Intel(R) UHD Graphics 770"):
  - `h264/hevc/vp9/mjpeg_qsv` encode through PyAV 19.0.2, including `hevc_qsv` with `yuyv422` and `mjpeg_qsv` with `yuyv422`;
  - `mjpeg_qsv` decode of the camera 4:2:2 JPEGs;
  - `av1_qsv`, expected to fail per source.
- Is Intel HEVC 4:2:2 encode on Raptor Lake (the "Es" / shader-assisted path) reachable through oneVPL on Windows from FFmpeg? NOT VERIFIED.
- `h264_d3d12va` / `h264_mf` on the Intel adapter (adapter selection), and `ffv1_vulkan` on the UHD 770 (CLI only). NOT VERIFIED.
- Intel session limit: Jellyfin-only claim. A session-count probe on the UHD 770 would settle it.
- NVENC 4:4:4 (`yuv444p`) all-intra on Ampere as a 4:2:2-preserving alternative to 4:2:0. NOT TESTED.
- Windows codec support for MTL, ARL, LNL and BMG iGPUs: only Linux media-driver tables plus ark B580 were found.

## 9. Files from this part

| file | kind |
|---|---|
| `scripts/hw_accel_target/wheel_hw_pixfmts.py` | static query (no device opened): `uv run --script scripts/hw_accel_target/wheel_hw_pixfmts.py` |
| `results/hw_accel_target/wheel_hw_pixfmts_19.0.2.json` | measured, output of the above |
| `results/hw_accel_target/vulkaninfo_video_ext.txt` | measured, read-only `vulkaninfo` excerpt (full dump in scratchpad `hw_accel_target/vulkaninfo_full.txt`) |
| `results/hw_accel_target/display_devices_probe.txt` | measured, `Get-PnpDevice -Class Display` |
| `results/hw_accel_target/sources_nv_intel/*` | source copies and extracts (see top) |

## 10. Correction note (2026-11-10, GF07)

The "source (transcribed)" cells above were re-checked against raw downloads of intel.com / edc.intel.com pages fetched on 2026-11-10 (curl with browser headers; quotes checked against the raw files). Details, verbatim quotes and sha256 values: `results/hw_accel_target/gapfill/GF07_intel_windows_sources.md` and `gapfill/GF07_sources/`.
- §1 F/KF bullet, §4.3 L44 row, §5 table: now **source**. oneVPL doc: "Intel® Core™ Processors without processor graphics do not have media support."; processor-numbers suffix table: "F | Requires discrete graphics"; ark 265KF: "Intel® Quick Sync Video | No". The 14700KF code name is "Products formerly Raptor Lake" (§5 said "not asked").
- §5 "none of these F/KF pages says a discrete GPU is required": still true for the SKU pages (0 "discrete" matches), but the suffix table now says it for "F".
- §4 intro ("For Windows, the oneVPL capability doc covers 11th–13th Gen and Arc A only"): still true of that doc, but it is no longer the only Windows source. The RPL, MTL and ARL-S datasheets name Windows exposure APIs (Direct3D12 Video, MFT) and list JPEG/AVC/HEVC encode. Intel KB 000098345 (Windows 10/11) covers Arc A, Core Ultra Series 1/2/3 and Arc B, without JPEG.
- §4.1 H.264, HEVC 4:2:2, AV1, VP9 and JPEG rows: the transcribed oneVPL values checked here match the raw pages. **Error:** the transcript's encode summary showed only "MJPEG 8-bit, 4:2:0". The raw tables also have "MJPEG 8-bit, 4:2:2 | ✔ | ✔" and "MJPEG 8-bit, 4:4:4 | ✔ | ✔" (Xe MAX/Arc A; 11th, 12th/13th Gen), and the "(fixed-function hardware + shader-based)" rows incl. HEVC 4:2:2 for 11th–13th Gen.
- §4.1 HEVC 4:2:2 "MTL / ARL **N** (D only)": that is the Linux media-driver. Intel Windows sources say Y. The MTL and ARL-S datasheets give "HEVC/H265 | Main10 422 - 8b/10b | L5.2 | 4K@60", and KB 000098345 gives Core Ultra Series 1 "8-bit 4:2:2". This is a vendor-vs-vendor / OS split, not tested.
- §4.3 L21 (no session limit): Intel's "Encode and Decode Capabilities for 7th Generation … and Newer" (Updated 6/8/2021) says "For all processor graphics listed here, there is no limitation on the number of concurrent sessions to transcode." It covers Iris Xe MAX and 7th–11th Gen only.
- §4.3 L89: the ark i7-14700K field "Multi-Format Codec Engines | 2" is now verified on the raw page.
- §8 last bullet ("only Linux media-driver tables plus ark B580 were found"): superseded by GF07. Still NOT VERIFIED on Windows: Arc B JPEG encode and the ARL-H/U codec list. LNL rests on a datasheet whose page is labelled "Confidential".
