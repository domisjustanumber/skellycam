# hw_accel_target FINDINGS: hardware-acceleration target (G6, G7), intra-only recording format

Topic: Jellyfin-guided hardware-acceleration target (HANDOFF §1 requirements 3 (hardware target, including the 17:20 recording-format and 17:35 nvJPEG sub-bullets), 8 (intra-only) and 9 (H.264/HEVC intra vs JPEG at matched quality)).

- Machine: Gerald (i7-14700K with UHD 770, RTX 3070, driver 610.88).
- Implementation under test: PyAV 19.0.2 (FFmpeg 9.0.2, libavcodec 63.1.102).
- **Timing:** this topic ran no timed test. The capacity column in §3.3 and the table in §3.3.1 come from the quiet bench run `20261109T230007` (23:00:07–05:36:29; 67 of 68 items ok, the only timeout was OV-COST, not an encode item; no item flagged `load_over_15pct`) [measured: `R/BENCH_RUN_2300_SUMMARY.md` §1–§2]. Full tables: `R/intra_compare/FINDINGS.md` §2.4–§2.6 and §3.5. Size, PSNR/SSIM, correctness and seek exactness are from the functional runs, as before.

Labels:
- **[measured]**: a result file.
- **[source]**: a primary source, accessed 2026-11-09. Sources added in the step 3 gap-fill (GF03, GF06, GF07, and R6 from GF04) were accessed 2026-11-10.
- **[source (Win)]**: a primary source that is Windows-specific (Windows OS scope, Windows exposure APIs, or a "(Windows Only)" cell). Intel Windows sources: GF07.
- **[source (SDK header via mirror)]**: Apple SDK header text read from a third-party mirror (GF06). Weaker than [source].
- The earlier **[source (transcribed)]** label (intel.com read through WebFetch's small model) is retired: GF07 re-read the pages raw and checked each quote against the raw file.
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
- Verification: `R/hw_accel_target/VERIFY_provenance.md` (VP), `R/hw_accel_target/VERIFY_method.md` (VM), `R/hw_accel_target/verify_method_range_check.json`, `R/hw_accel_target/VERIFY_step3.md` (VS3).
- Step 3 gap-fill inputs (2026-11-10):
  - GF03 = `R/licensing/gapfill/GF03_nvjpeg_licence_arch.md` (quotes checked 72/72 in `GF03_quote_verification.json`; fatbinary lists in `GF03_wheel_arch_facts.json`);
  - GF04 = `R/hw_accel_target/gapfill/GF04_doc_fixes.md` and `GF04_capacity.json` (parsed from `R/intra_compare/bench/*.json`); licence copies in `R/hw_accel_target/gapfill/GF04_src/` (sha256 in `SHA256SUMS.txt`);
  - GF06 = `R/hw_accel_target/gapfill/GF06_amf_vt_intra.md` (FFmpeg n9.0.2 commit `946fcce0`, AMF SDK v1.5.3 commit `57ee0cfb`, Apple docs JSON; excerpts in `GF06_sources/`);
  - GF07 = `R/hw_accel_target/gapfill/GF07_intel_windows_sources.md` (Intel pages read raw; excerpts and sha256 in `GF07_sources/`).

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
  - [source] `nvidia-nvjpeg-cu12==12.4.0.76` (the measured stack; GE §6, `R/gpu_encode/NOTES.md:148`) is the libnvjpeg of CUDA 12.9 Update 1. `redistrib_12.9.1.json` gives libnvjpeg `"version": "12.4.0.76"`; CUDA 12.4.0 ships 12.3.1.89 (GF03 R04, R05).
  - [code] The wheel's `nvjpeg.h:70-73` gives 12.4.0.76 (GF03 R22).
  - [source] The CUDA 12.9.1 nvJPEG docs match the measured library: "NVJPEG_ENC_BACKEND_GPU Always use CUDA encoder." and "Hardware accelerated JPEG encode is available on Jetson Thor (Blackwell), running Linux ARM64." (GF03 R06, R07).
  - [source] CUDA 12.9.1 release notes: "Added hardware-accelerated JPEG encoding support for NVIDIA Jetson Thor hardware (Blackwell SM 10.1 architecture)." (GF03 R09).
  - The version gap noted in the 2026-11-09 revision is closed.
- **N7 [source]** Same page: "Hardware accelerated JPEG decode is available on the following GPUs architectures - Ampere (A100, A30) Hopper Ada Blackwell Jetson Thor", on "Windows Linux (x86_64, ARM64)".
  - Consumer Ampere (GA10x) is not listed.
  - The list names architectures. Whether "Ada" and "Blackwell" include GeForce RTX 40/50 is NOT VERIFIED.
  - [source] The hardware backend "Supports baseline JPEG images with single scan with 1 or 3 channels. 410 and 411 chroma subsamplings are not supported." So 4:2:2 is not excluded on paper. Whether it works is NOT VERIFIED (VM §0).
  - [source] The CUDA 12.9.1 docs (the measured library's version, N6) give the same decode list without Thor: "Ampere (A100, A30) Hopper Ada Blackwell" (GF03 R06).
  - [source] CUDA 12.8 nvJPEG notes: "Added hardware-accelerated JPEG decoding support in nvJPEG for NVIDIA Blackwell architecture GPUs." (GF03 R10).
  - [source] The CUDA 12.4.0 docs listed "A100, A30, H100" only (GF03 R01).
  - GeForce applicability of "Ada" and "Blackwell": still NOT VERIFIED.
- **N8 [measured]** nvJPEG via nvImageCodec 0.10.0.9 on the RTX 3070 (GE §5, §6; `R/gpu_encode/nvimgcodec_jpeg.md`):
  - `nvjpeg_cuda_encoder` encodes 4:2:2 and 4:2:0 JPEG from host RGB and from GPU-resident images. The generic `backend:GPU_ONLY` encoder selection fails ("Could not create encoder. Code: 7").
  - Camera 4:2:2 JPEG decode works only through `HYBRID_CPU_GPU` / `nvjpeg_cuda_decoder`. `GPU_ONLY` and `HW_GPU_ONLY` fail ("Could not create decoder. Code: 7").
  - Planar and interleaved YUV input are rejected (`encode returned None`).
- **N9 [source]** The nvJPEG 13.5 C API has:
  - `nvjpegEncodeYUV` ("Input for this function is an image in YUV colorspace");
  - an NV12 input (`NVJPEG_INPUT_NV12`). For NV12, the subsampling "must both be NVJPEG_CSS_420", so **NV12 input gives 4:2:0 output only**.
  - [inferred] The RGB-only limit comes from the nvImageCodec 0.10.0.9 binding, not from nvJPEG.
  - [code] The measured library's header has `NVJPEG_INPUT_YUV`, `NVJPEG_INPUT_NV12`, `nvjpegEncodeYUV` and `nvjpegEncode` (wheel `nvjpeg.h:154, 159, 540, 560`; `R/licensing/gapfill/GF03_sources/nvjpeg_h_12.4.0.76_lines.txt`).
  - A Python binding that reaches them: NOT TESTED.
  - [source] nvImageCodec 0.10 release notes: "Planar YUV (P_YUV) is not converted, and CPU-only encoders are unaffected." and "Encoding a chroma-subsampled Image is not supported yet and raises ValueError." (GF03 R19, R20). The notes page is labelled "v0.10.0-beta.11"; whether it applies to wheel 0.10.0.9 is NOT VERIFIED (GF03 R17, R18).
- **N10 [source+measured]** GeForce NVENC is limited to 12 concurrent sessions per system.
  - [source] App note 13.1: "limited to 12 per system".
  - [measured, PyAV 19.0.2] 12 `h264_nvenc` sessions open and the 13th fails (`R/gpu_encode/nvenc_sessions_19.0.2.json`).
  - [measured, PyAV 19.0.2, with a control] With no sessions held, these all encode: `hevc_nvenc`, `h264_d3d12va`, `h264_mf` and `h264_qsv`. With 12 held, `hevc_nvenc`, `h264_d3d12va` and `h264_mf` fail, and `h264_qsv` still encodes (`R/gpu_encode/verify_method_pool.json`; GEF §2.4).
  - Vulkan: `h264_vulkan` also failed while the sessions were held. That was a CLI run with no control. [inferred] Vulkan shares the pool (GEF §2.4).
  - [measured, quiet run] The limit probes opened 12 of 32 requested `h264_nvenc` and `hevc_nvenc` sessions, and every N=16 NVENC scaling cell opened 12 (§3.3.1; GF04).
- **N11 [source]** "Ampere" or "Turing" alone does not guarantee NVENC.
  - MX450, MX570 A and GT 1030 have 0 NVENC.
  - Every RTX-branded desktop row lists NVENC (NI §2.1).
- **N12 [measured]** FFV1 on Vulkan compute (`ffv1_vulkan`) works on the RTX 3070 and is byte-exact, but **only through the ffmpeg CLI**. No PyAV wheel contains a Vulkan encoder (GE §1, §3, §4).
- **N13 [measured, static fatbinary parse, not cross-checked with cuobjdump]** The nvJPEG wheels used (nvidia-nvimgcodec-cu12 0.10.0.9 pinned; nvidia-nvjpeg-cu12 12.4.0.76 as resolved, unpinned; GF03 §1, G04; `R/gpu_encode/NOTES.md:148`) carry GPU code for RTX 20 to RTX 50 (GF03 §4; `R/licensing/gapfill/GF03_wheel_arch_facts.json` → `fatbin`).
  - `nvjpeg64_12.dll` (nvidia-nvjpeg-cu12 12.4.0.76) contains SASS for sm_50, 52, 60, 61, 70, 75, 80, 86, 89, 90, 100, 101, 103, 120 and 121, plus PTX 121.
  - The nvImageCodec 0.10.0.9 DLLs (`nvjpeg_ext_0.dll`, `nvimgcodec_0.dll`, `nvimgcodec_impl.cp312-win_amd64.pyd`) contain SASS for sm_50, 60, 70, 80, 90, 100 and 120, plus PTX 120.
  - [source] "a cubin object generated for compute capability X.y will only execute on devices of compute capability X.z where z≥y" (CUDA 12.9.1 programming guide; GF03 R14).
  - [source] GeForce RTX 20/30/40/50 = compute capability 7.5/8.6/8.9/12.0 (https://developer.nvidia.com/cuda-gpus). GF03 K01-K04 quote one representative desktop SKU per generation (2080, 3070, 4090, 5090). The saved page lists the other GeForce RTX 20/30/40/50 SKUs under the same headings (scratchpad `step3/GF03/work/txt/cuda_gpus.txt:26-32, 57-63, 78-87, 106-109`; not copied under `R/`). Laptop variants were not checked.
  - [inferred] RTX 20/40/50 are "code present, not run". Functional encode on 7.5, 8.9 and 12.0 is NOT VERIFIED.

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
- **I5 [source + measured]** Intel desktop F/KF SKUs have no processor graphics, so they have no Quick Sync media engine (GF07 §2).
  - [source] Intel oneVPL media-capabilities doc (ID 772607 v1.1): "Intel® Core™ Processors without processor graphics do not have media support."
  - [source] Intel processor-numbers page, desktop suffix table: "F | Requires discrete graphics".
  - [source] ark Core Ultra 7 265KF (Q4'24, Arrow Lake): "Intel® Quick Sync Video | No", "Xe-cores | 0", "Graphics Output | n/a".
  - [measured] Downloaded ark pages (2026-11-10): i5-10400F (Q2'20), i9-11900KF (Q1'21), i5-12400F (Q1'22) and i7-14700KF (Q4'23) have no "GPU Specifications" section and 0 "Quick Sync" matches; i7-14700K has "Intel® Quick Sync Video | Yes".
  - **NOT VERIFIED:** what share of 2020+ SKUs or shipments they are.
- **I6 [source (Win)]** Intel Windows encode sources per generation (GF07 §2). The media-driver tables are Linux VA-API background only.
  - RPL, MTL, ARL-S/HX: the datasheet encode sections name the Windows exposure APIs ("Direct3D12 Video API", "Intel®one VPL", "MFT (Media Foundation Transform) filters [Only for AVC/HEVC/JPEG/AV1 Encoder]"; RPL: "Intel® Media SDK", "MFT …"). They list JPEG (RPL "JPEG | Baseline | — | 16Kx16K"; MTL/ARL "16Kx16K"), AVC and HEVC encode.
  - Arc A, Core Ultra Series 1, Arc B: Intel KB 000098345 ("Operating System Windows® 10*, Windows 11*") lists H.264 "8-bit 4:2:0" and HEVC encode including "8-bit 4:2:2". It has no JPEG row.
  - Arc A JPEG: oneVPL doc "MJPEG 8-bit, 4:2:2 | ✔ | ✔" (OS-agnostic; Windows inferred).
  - LNL: only a datasheet whose page is labelled "Confidential" ("Xe2 supports full HW accelerated video encoding for AVC/HEVC/JPEG/AV1."). Whether PLAN.md may cite it is Dom's call.
  - **NOT VERIFIED on Windows:** Arc B JPEG encode; the ARL-H/ARL-U codec list; LNL HEVC 4:2:2. No `*_qsv` encode was tested outside RPL-S.
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
- **A8 [code+source] AMF all-intra and constant QP (GF06). Not run on AMD hardware.**
  - [measured] `h264_amf` and `hevc_amf` are in the PyAV 19.0.2 win_amd64 wheel, with nv12/yuv420p/p010le input and no 4:2:2 (`R/hw_accel_target/gapfill/GF06_pyav_options.json`, static query).
  - [code] h264_amf maps `gop_size` to `AMF_VIDEO_ENCODER_IDR_PERIOD` (`amfenc_h264.c:574-576`). hevc_amf maps it to `AMF_VIDEO_ENCODER_HEVC_GOP_SIZE` and always sets `NUM_GOPS_PER_IDR` (default 1) (`amfenc_hevc.c:97, 298-301`).
  - [source] AMF H.264 doc v1.5.3:1417: "Sets IDR period. IDRPeriod = `0` turns IDR off." HEVC doc:1266: "`0` means only insert the first IDR/CRA (infinite GOP size)." `VideoEncoderVCE.h:266`: "IDR Period in frames".
  - [inferred] `gop_size=1` gives an IDR every frame.
  - [code+source] Second route: `forced_idr=1` plus `pict_type=I` on every frame forces IDR (`amfenc.c:480-486, 501-506`). The H.264 doc:1953 requires IDR_PERIOD 0 for this route.
  - [code] Only IDR output gets `AV_PKT_FLAG_KEY` (`amfenc.c:211, 224`).
  - [code+source] Constant QP: `rc=cqp` with `qp_i` → `QP_I` (`amfenc_h264.c:86, 377-378`; `amfenc_hevc.c:79, 523-524`). H.264 doc:1139 and HEVC doc:1050: "Sets the constant QP for I-pictures."
  - [code+source] B-frames are off by default: `B_PIC_PATTERN` default 0 (H.264 doc:1498: "BPicturesPattern = `0` indicates that B-pictures are not used."). hevc_amf has no B-frame option.
  - On-hardware behaviour: NOT VERIFIED.

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
- **P5 [code+source] VideoToolbox all-intra and quality (GF06). Not run on Apple hardware.**
  - [code] `gop_size>0` → `kVTCompressionPropertyKey_MaxKeyFrameInterval` (`videotoolboxenc.c:1379-1395`). [source] Apple: "A key frame interval of 1 indicates that every frame must be a keyframe".
  - [code] The generic default gop_size is 12 (`options_table.h:96`), and the VT codec defaults (`videotoolboxenc.c:2837-2842`) do not override it. So all-intra needs an explicit `gop_size=1`.
  - [code] `max_b_frames=0` (generic default) → `AllowFrameReordering=false` (`:1528-1537, 1666, 1683`).
  - [code] Quality: `global_quality` (or `+qscale`, arm64 only, `:1132-1135, 1245-1248`) → `kVTCompressionPropertyKey_Quality` = global_quality/100, capped at 1.0 (`:1250-1261`). [source] Apple: "range of 0.0 to 1.0 … 1.0 implies lossless compression for encoders that support it".
  - [code + source (SDK header via mirror)] No constant QP: `kVTEncodeFrameOptionKey_BaseFrameQP` exists (macOS 12+; header: "turns off standard rate control"), but FFmpeg n9.0.2 never sets it (0 matches).
  - [code] `qmin`/`qmax` map to Min/MaxAllowedFrameQP (`:1570-1590`). On `kVTPropertyNotSupportedErr` they are only logged at INFO and ignored (`:1144-1149`). [source (SDK header via mirror)] VTH:1142: the encoder "may drop frames to maintain bitrate and QP goals".
  - [code] Hardware is required by default (`allow_sw=0`, `:1702-1705`).
  - On-hardware behaviour: NOT VERIFIED.

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
- **J5 [source] Vendor vs vendor (Intel), HEVC 4:2:2 encode, Windows vs Linux (GF07 §3).**
  - Arc A: oneVPL details "8-bit, 4:2:2 (YUY2) |  | ✔16k (Windows Only)", and KB 000098345 (Windows) lists "8-bit 4:2:2". Media-driver README L118 gives DG2 "D/E" on Linux. Windows Y; the Linux statement disagrees with "Windows Only".
  - MTL and ARL-S/HX: datasheets "HEVC/H265 | Main10 422 - 8b/10b | L5.2 | 4K@60", and the KB lists "8-bit 4:2:2" for Core Ultra Series 1. Media-driver L118 gives MTLx "D" (no encode). Windows Y, Linux N.
  - LNL: the datasheet HEVC row lists only "Main Main10 420, 444 - 8b/10b SCC 420 444 - 8b/10b"; media-driver L118 gives LNL "D/E". NOT VERIFIED.
  - None tested. This matters only for keeping 4:2:2 in HEVC.
- **J6 [source] Jellyfin-only claims (NOT VERIFIED, kept out of the plan):**
  - "no concurrent encoding sessions limit" on Intel, AMD and Rockchip;
  - the Apple "soft limit";
  - the VCN quality ranking (NI §4.3; AAC §2.3, §3.2).
  - [source] Update (GF07 §3): Intel, "Encode and Decode Capabilities for 7th Generation Intel® Core™ Processors and Newer" (Updated 6/8/2021): "For all processor graphics listed here, there is no limitation on the number of concurrent sessions to transcode." It lists Iris Xe MAX and 7th–11th Gen only. So the Intel "no limit" claim has an Intel source for TGL/RKL and older, and stays Jellyfin-only for ADL and later and Arc.
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
- **R5 [source]** nvImageCodec (wheel SLA) and nvJPEG (CUDA EULA) may be redistributed only inside an application with material additional functionality. Downstream terms must be consistent with NVIDIA's, and neither may be made subject to an open-source licence (LIC Q51, Q52; GF03 W03-W07, C02, C03, C06, C11, C13).
  - [source] The nvImageCodec SLA also bars publishing benchmark results without NVIDIA's permission (GF03 W10).
  - [source] nvImageCodec's own channels disagree: the wheel carries the NVIDIA SLA, while PyPI and GitHub v0.10.0 say Apache-2.0 (GF03 W01, G01, H01).
  - [source] The live CUDA EULA permits developing and testing applications released under OSI-approved licences (GF03 C04). The 2018 EULA inside the nvjpeg wheel lacks that sentence and lists nvJPEG as distributable on Linux only (GF03 E01, E04). Which text governs: NOT VERIFIED.
  - [inferred, not legal advice] An optional pip extra with a pinned nvjpeg version is the low-risk route for AGPL skellycam. Bundling the wheels in an installer needs legal review (GF03 §3).
- **R6 [source]** libjpeg-turbo: "libjpeg-turbo is covered by two compatible BSD-style open source licenses" (the IJG License and the Modified (3-clause) BSD License). https://raw.githubusercontent.com/libjpeg-turbo/libjpeg-turbo/main/LICENSE.md, accessed 2026-11-10, sha256 `ba6bceeb…d4433579`; copy at `R/hw_accel_target/gapfill/GF04_src/libjpeg-turbo_LICENSE_main.md` (line 4).
  - [source] The binding used, simplejpeg, is under the "MIT License" (https://raw.githubusercontent.com/jfolz/simplejpeg/master/LICENSE, accessed 2026-11-10, sha256 `dcb18a8a…cd7fe6d4`); copy at `R/hw_accel_target/gapfill/GF04_src/simplejpeg_LICENSE` (line 1). Both sha256 values re-checked against the copies (`GF04_src/SHA256SUMS.txt`).
  - Both were read from the default branch, not from the version bundled in simplejpeg 1.9.0. Neither text is a patent grant.

### 2.11 Pipeline pitfalls (affect any implementation)

- **K1 [measured]** Decoded MJPEG frames carry `pict_type=I`, which forces key frames in GOP encoders. Reset it to `NONE` (FN §6.1). This does not matter for intra-only output, but it matters for any decode→encode pipeline.
- **K2 [measured]** `reformat(format='nv12')` keeps full-range samples from a range-tagged decoded JPEG frame. Pass `dst_color_range=1` for **H.264/HEVC** targets (FN §6.2).
  - PyAV 19 converts range only when the source is an untagged `yuvj*` frame (FN §6.3).
  - Always pass `src_color_range` and `dst_color_range` explicitly, as `S/intra_compare/benchpaths.py:195` does.
- **K3 [measured+code]** FFmpeg's default `i_qfactor=-0.8` makes NVENC constqp and QSV CQP code intra frames at 0.8x the requested QP. Pin `i_qfactor=1, i_qoffset=0` (IC §3, §9.1; `R/intra_compare/knob_check.json`).
  - [code] Applies to NVENC (`nvenc.c:835-836`) and QSV (`qsvenc.c:925, 929`) only. AMF and VideoToolbox never read `i_qfactor`/`i_qoffset` (0 grep matches in `amfenc*.c/h` and `videotoolboxenc.c` at n9.0.2; GF06).
- **K4 [code+measured]** NVENC all-intra needs `gop_size=0` (`nvenc.c:1764-1766`; GE §3).
- **K5 [measured+code]** **JPEG targets must be fed full range.**
  - `S/hw_accel_target/bench_encode_stream.py` gets this wrong:
    - `:54` sets `mjpeg_qsv`'s input format to `nv12`;
    - `:112` feeds limited-range NV12 (from YUY2) to `mjpeg_qsv`;
    - `:119-124` applies `dst_color_range=1` to MJPEG sources for every non-`yuvj` format, `mjpeg_qsv`'s nv12 included (GF04 re-read the lines; the branch starts at `:119`).
  - Measured with PyAV 19.0.2: the resulting JPEG decodes as `yuvj420p` with Y 16..235 (`verify_method_range_check.json`).
  - `S/intra_compare/benchpaths.py:16-18` feeds JPEG paths full range and H.264/HEVC limited range.
  - [measured] No reported result uses `bench_encode_stream.py`: it was not queued in the quiet run, and `R/hw_accel_target/bench/` is empty (§5; GF04).
- **K6 [code+source]** **`gop_size=0` means all-intra on NVENC but NOT on AMF** (IDR off for H.264, first IDR only for HEVC; A8). Use `gop_size=1` for AMF. VideoToolbox ignores 0 and falls back to gop_size 12 (P5), so use `gop_size=1` there too. AMF's option names differ from NVENC's: AMF has `rc=cqp, qp_i` and no `qp` (GF06).
- **K7 [code]** On VideoToolbox, a `qmin=qmax` QP clamp can be ignored silently (INFO log only, `videotoolboxenc.c:1144-1149`). Do not rely on it for matched quality; use `global_quality` and check the output (P5; GF06).

## 3. Comparison tables

### 3.1 Per-generation hardware matrix (cell = encode / decode)

Legend:
- Y = yes; N = no; NV = NOT VERIFIED; P = partial.
- "CUDA" = the nvJPEG compute backend. Per Dom (17:35; HANDOFF §1 requirement 3), it counts as hardware-accelerated.
- Hardware JPEG encode exists only on Jetson Thor (GF03 R06, R09), so every GeForce JPEG encode cell is the CUDA backend; the docs separate `NVJPEG_ENC_BACKEND_GPU` from `NVJPEG_ENC_BACKEND_HARDWARE` (GF03 R07).
- "Win source" = a Windows-specific Intel source (GF07, I6). Intel decode cells are unchanged.
- "4:2:0 only" applies to the AMD H.264/HEVC/AV1/VP9 cells. AMD JPEG decode outputs 4:2:2 YUYV on Linux (A1).
- "measured" cells are measured on the RTX 3070 or the UHD 770 (RPL-S) only. The rest of each row is from sources.
- Jellyfin column: verdict on Jellyfin's per-generation claims (§2.6). Every VP9/JPEG/FFV1 cell is vendor-only (J7).

| generation | H.264 | HEVC | AV1 | VP9 | JPEG | FFV1 (Vulkan compute) | Jellyfin vs vendor | evidence |
|---|---|---|---|---|---|---|---|---|
| NVIDIA Turing (RTX 20, GTX 16) | Y / Y (8-bit; no 4:2:2) | Y / Y (no 4:2:2) | N / N | N / Y | enc CUDA: NV (not run; sm_75 SASS present, GF03) / dec hybrid CUDA+CPU; no hardware engine (not listed, GF03 R06) | NV | AGREE | N1-N5, N7, N11, N13 |
| NVIDIA Ampere (RTX 30) | Y / Y | Y / Y | **N** / Y | N / Y | **enc CUDA: Y (measured, RTX 3070)** / dec: hybrid CPU+CUDA Y (measured); GPU-only nvImageCodec backends and NVDEC/FFmpeg **fail** on 4:2:2 (measured) | Y (measured, CLI only) | AGREE | N1, N5, N8, N12 |
| NVIDIA Ada (RTX 40) | Y / Y | Y / Y | **Y** / Y | N / Y | enc CUDA: NV (not run; sm_89 SASS present, GF03) / dec: Ada in the hardware-decode list (N7); GeForce applicability and 4:2:2 NV (doc excludes only 4:1:0/4:1:1) | NV | AGREE | N2, N6, N7, N13 |
| NVIDIA Blackwell (RTX 50) | Y / Y (adds 4:2:2, High10) | Y / Y (adds 4:2:2) | Y / Y | N / Y | enc CUDA: NV (not run; sm_120 SASS in nvjpeg and nvImageCodec, GF03) / dec: Blackwell listed (N7, GF03 R10); GeForce NV. Hardware JPEG encode is Jetson Thor SM 10.1 only, not RTX 50 (GF03 R09) | NV | AGREE (except main-page H.264 10-bit, J2) | N2, N7, N13, J2 |
| Intel TGL / RKL / ADL / RPL iGPU | Y (measured RPL-S; Win source RPL) / Y | Y / Y (4:2:2 enc fixed-function + shader only, ≤4k; Win source RPL "Main 4:2:2 10"; **measured Rext 4:2:2 on RPL-S**) | **N** / Y (measured on RPL-S; other TGLx source) | **Y (measured on RPL-S)** / Y | **Y fixed-function (measured on RPL-S, 4:2:2 from yuyv422; needs full-range input, K5); Win source RPL "JPEG Baseline"; TGL/RKL/ADL OS-agnostic source** / Y (measured, output nv12) | NV (Vulkan 1.4 device, not run) | AGREE; scope DISAGREE on "QSV only on Windows" (J10) | I1, I3, I4, I6, F1-F5, F9 |
| Intel MTL / ARL-S/HX | Y / Y (Win source) | Y / Y (Win source); 4:2:2 enc: Win Y, Linux N (J5) | Y / Y | Y / Y | **Y (Win source, datasheets; not tested)** / Y | NV | AGREE | I2, I4, I6, J5 |
| Intel ARL-H / ARL-U | NV (Windows codec list not sourced) | NV | NV | NV | NV | NV | n/a | I6 |
| Intel LNL | Y / Y (datasheet labelled "Confidential", I6) | Y / Y; 4:2:2 enc NV (J5) | Y / Y | **N** / Y | Y on Windows only per the "Confidential" datasheet; else Windows NV (Linux source) / Y | NV | AGREE | I2, I6, J5 |
| Intel Arc A (DG2) | Y / Y (Win source, KB) | Y / Y (Win source); 4:2:2 enc Win Y ("Windows Only"), Linux vendor vs vendor (J5) | Y / Y | Y / Y | Y (oneVPL doc, OS-agnostic; Windows inferred) / Y | NV | AGREE | I2, I6, J5 |
| Intel Arc B (BMG) | Y / Y (Win source, KB + ark B580) | Y / Y incl. 4:2:2 enc (Win source, KB) | Y / Y | **N** / Y (KB "Not Supported") | **Windows NV** (no Intel Windows source; Linux media-driver "D/E") / Y | NV | AGREE | I2, I6 |
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
| AMD / Windows | `h264/hevc/av1_amf` in the wheel (measured, GF06_pyav_options.json). All-intra via `gop_size=1` (not 0) or `forced_idr=1` + `pict_type=I` [code amfenc_h264.c:574-576, amfenc_hevc.c:298-301, amfenc.c:480-508]. Constant QP via `rc=cqp, qp_i` [code amfenc_h264.c:377-378, amfenc_hevc.c:523-524]. On-hardware NOT VERIFIED (no AMD here) | JPEG, VP9 (no hardware) | AAC §2.4; A8 |
| AMD / Linux | `*_amf` (needs AMD's closed runtime); same intra/CQP options as Windows (GF06) [code]; on-hardware NOT VERIFIED | vaapi, vulkan | AAC §2.4; A8 |
| Apple / macOS | `h264/hevc_videotoolbox` (+ prores), macOS wheels only (R/gpu_encode/wheel_hw_codecs.md:7-8). All-intra via `gop_size=1` → MaxKeyFrameInterval 1 [code videotoolboxenc.c:1379-1395; source Apple docs: 'A key frame interval of 1 indicates that every frame must be a keyframe']. Default gop_size is 12 [code options_table.h:96; vt_defaults videotoolboxenc.c:2837-2842 do not override g]. Quality via `global_quality` → kVTCompressionPropertyKey_Quality 0-1 [code :1250-1261]. Constant QP not reachable (BaseFrameQP unused by FFmpeg n9.0.2) [code]. Hardware required by default (allow_sw=0) [code :1702-1705]. On-hardware NOT VERIFIED | JPEG (only via jellyfin-ffmpeg 0047), AV1, VP9 | P2, P3, P5 |
| Windows on ARM64 (e.g. Snapdragon) | `h264/hevc/av1_d3d12va`, `*_mf` names only. NOT VERIFIED (no device; not covered by this study) | qsv, nvenc, amf | `R/gpu_encode/wheel_hw_codecs.md` |

### 3.3 Intra-only candidates vs the target (recording format)

Bytes column: target A, yuy2_1080p, against libjpeg-turbo 4:2:2. These are Gerald, these presets, this content (§2.8 scope). Capacity column: largest tested N (1/4/8/16) that kept up, with the encoder settings chosen for A; the scaling runs had no quality check (§3.3.1).

| candidate (intra only) | RTX 3000+ hw encode | Intel 2020+ iGPU hw encode | AMD 2020+ APU / RDNA hw encode | Apple M1-M4 hw encode | verified through PyAV 19.0.2 on Gerald | no-iGPU CPU | G7 | Electron playback / exact seek | bytes at target A | measured 1080p30 capacity on Gerald, target-A settings (largest tested N kept up, cores) | meets target? |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **H.264 intra 4:2:0** | Y (NVENC; measured on RTX 3070, other generations source) | Y (QSV; measured on UHD 770, other generations source) | codec Y (source; not Navi24). Intra-only via `gop_size=1` [code+source]. Matched-quality knob `rc=cqp, qp_i` [code+source]. `i_qfactor` not read, so K3 does not apply [code]. On-hardware NOT VERIFIED (GF06) | codec Y (P on base M1; source). Intra-only via `gop_size=1` [code+source]. Matched-quality knob `global_quality` → VT Quality (no constant QP) [code+source]. On-hardware NOT VERIFIED (GF06) | `h264_nvenc`, `h264_qsv`, `h264_d3d12va`, `h264_mf` (Windows x64) | libx264 (GPL) | royalty-bearing (R2) | `<video>` + WebCodecs, sw fallback; exact (V1, V2) | 0.53 (nvenc) / 0.59 (qsv) | h264_nvenc 12 (session cap) at 0.611 cores; h264_qsv 16 (largest tested N) at 1.246 cores (NV12 best case); libx264 not scaled (§3.3.1) | **yes**, on both readings below |
| **HEVC intra 4:2:0** | Y (NVENC; measured on RTX 3070) | Y (QSV; measured on UHD 770) | codec Y (source; not Navi24). Intra-only via `gop_size=1` with `gops_per_idr=1` [code+source]. Matched-quality knob `rc=cqp, qp_i` [code+source]. On-hardware NOT VERIFIED (GF06) | codec Y (P on base M1; source). Intra-only via `gop_size=1` [code+source]; IDR vs CRA NOT VERIFIED. Matched-quality knob `global_quality` → VT Quality (no constant QP) [code+source]. On-hardware NOT VERIFIED (GF06) | `hevc_nvenc`, `hevc_qsv`, `hevc_d3d12va`, `hevc_mf` | libx265 (GPL) | royalty-bearing (R2) | **hardware decode only** (V2); exact (V1) | 0.43 / 0.39 | hevc_nvenc 12 (session cap) at 0.652 cores; **hevc_qsv 1** of the tested N (1/4/8/16; N=4 fails; N=2–3 not tested) at 0.155 cores (default mode; low_power NOT VERIFIED); libx265 not scaled (§3.3.1) | **yes**; playback needs HEVC decode hardware. hevc_qsv: capability yes; in default mode only N=1 of the tested N kept up at 1080p30 (measured); N=2–3 and low_power NOT VERIFIED |
| **JPEG re-encode** (4:2:2 or 4:2:0) | Y via **nvJPEG CUDA** (measured on Ampere, outside FFmpeg/PyAV; RTX 20/40/50: binaries present for sm_75/89/120, not run, GF03) | Y (`mjpeg_qsv`, in the wheel; measured on RPL-S; Windows source for MTL and ARL-S/HX, not tested; LNL only per a "Confidential" datasheet; Arc B Windows NV; needs full-range input, K5) | **N** (no AMD JPEG encode) → CPU | **N** in FFmpeg/PyAV → CPU | `mjpeg_qsv`; nvJPEG via nvImageCodec 0.10.0.9 (separate wheel, RGB input only) | libjpeg-turbo / FFmpeg mjpeg | no patents listed for baseline (R1) | no `<video>`; ImageDecoder / createImageBitmap frame-exact (V4) | 4:2:0: libjpeg-turbo 0.89, mjpeg_qsv 1.00, nvJPEG 0.74 (nvJPEG not smaller at matched PSNR, Q2a) | mjpeg_qsv 4:2:2 from YUY2: 16 at 0.915; mjpeg_qsv 4:2:0 from NV12: 16 at 1.050; nvJPEG from NV12: 8 of the tested N (N=9–15 not tested) at 2.558; nvJPEG 4:2:2 from YUY2: 16 at 4.684 (with late frames); nvJPEG fed CPU-decoded camera MJPEG through swscale rgb24 **misses A**, after mjpeg_qsv decode it hits A (single-stream QC, not scaled); libjpeg-turbo 4:2:0: 16 at ≥1.685, 4:2:2: 16 at ≥2.809 (process workers, lower bound) (§3.3.1) | **partly**: Ampere and Intel TGL–RPL measured or source; Intel MTL/ARL-S/HX Windows source (not tested); RTX 20/40/50 code present, not run; Arc B Windows NV; AMD and Apple software only |
| JPEG passthrough (MJPEG cameras) | no encode needed | no encode needed | no encode needed | no encode needed | n/a | no encode needed | as JPEG (R1) | camera JPEGs: 88/88 still decode, 450/450 byte-identical fetch + decode (V4) | camera bytes. H.264/HEVC re-encodes at A are 0.64–0.91x camera bytes, with one more generation of loss (0.70–1.02x libjpeg-turbo 4:2:2) (Q4) | n/a: no encoder (write cost: `R/write_throughput/BENCH.md`, `R/jpeg_passthrough/BENCH.md`) | n/a: no encoder involved (C3) |
| AV1 intra | **N** | **N** (TGL–RPL) | VCN 4+ only | **N** | none (F4) | libsvtav1 (4:2:0) | RF licence, Sisvel claims (R3) | plays (CC §2, all-intra rows) | not swept | not benched: no RTX 3000 encode in the wheel (`R/BENCH_QUEUE_2300.md:217`) | **no** |
| VP9 intra | **N** (all NVIDIA) | Y except LNL/BMG | **N** | **N** | `vp9_qsv` | libvpx-vp9 | RF licence, Sisvel claims (R3) | plays (CC §2, all-intra rows) | not swept | not benched: no NVIDIA encoder (`R/BENCH_QUEUE_2300.md:220`) | **no** |
| FFV1 (Vulkan) | CLI only (measured) | NV | NV | NV | none (no Vulkan encoder in any wheel) | CPU `ffv1` | 0 IETF disclosures (LIC §2.1) | **does not play** (CC §2) | lossless | not benched here (CPU `ffv1` is a G4 fallback in uncompressed_intra; `R/BENCH_QUEUE_2300.md:217`) | **no** (not in PyAV, not playable) |

Two readings of "supported on most 2020+ CPUs" (req 3). The share of Intel, AMD, Apple and no-iGPU CPUs is NOT VERIFIED (I5).
- **Hardware encode on the CPU's own iGPU or APU (capability, from sources):**
  - H.264 and HEVC cover Intel, AMD and Apple 2020+ parts that have graphics.
  - JPEG covers Intel only.
  - Reachability through the PyAV wheel is narrower:
    - AMD AMF is untested on hardware. Its all-intra (`gop_size=1`) and CQP (`rc=cqp, qp_i`) options exist in code (GF06);
    - Linux AMD needs the closed AMF runtime;
    - Linux Intel QSV is likely unusable (§3.2);
    - Windows-on-ARM is NOT VERIFIED.
- **Encodable at all on the CPU:**
  - every candidate has a software encoder;
  - patents and licences are separate questions:
    - JPEG baseline: T.81 Annex L lists patents only for the arithmetic-coding and hierarchical-lossless processes, none for baseline (R1) [source];
    - libjpeg-turbo's code licence is BSD-style (R6) [source];
    - the wheel's libx264/libx265 are GPL and cannot be removed (R4) [measured].

### 3.3.1 Measured capacity with the target-A settings on Gerald (quiet run 20261109T230007)

Every value below is [measured], from `R/intra_compare/bench/*.json` (keys `runs[mode=paced].streams_keeping_up` / `opened` / `cpu_cores` and `runs[mode=unpaced].aggregate_fps`), extracted to `R/hw_accel_target/gapfill/GF04_capacity.json` by `S/hw_accel_target/gf04_capacity_extract.py` (parse only). VS3 recomputed every cell from the 24 raw `matched_concurrent_*.json` files.

- [measured] Every scaling item ran pinned to CPUs 0–15 (8 P-cores with HT) of the i7-14700K (`GF04_capacity.json` keys `affinity_before`, `affinity_after`).
- [code] "Keeps up" = per-stream fps ≥ 0.98 × 30 and end lag < 1/30 s. Paced = 450 frames per stream at 30 fps; unpaced = 300 frames per stream (script defaults). One thread or process and one encoder per stream (`S/intra_compare/bench_matched_concurrent.py:10-16, 127-131, 245-246`).
- [code] Packets are discarded, so these are encode-only numbers with no writer (`S/intra_compare/bench_matched_concurrent.py:60-62, 73-75`).
- [code] Tested N = 1, 4, 8 and 16 only (`bench_matched_concurrent.py:243`, `--streams` default "1,4,8,16"). "Streams kept up" = the largest **tested** N whose every paced rep has `streams_keeping_up` == `opened`. It is not a measured maximum: an untested N between two tested values may also keep up. Cores = paced `cpu_cores` at that N, median (min–max) over reps. Unpaced = `aggregate_fps` at the same N.
- Scope: "target A" here means the encoder setting chosen for A in the sweep. The scaling items run no quality check (`R/intra_compare/FINDINGS.md` §5, flag 5).
- [measured] **NVENC opens at most 12 sessions.** Every requested N=16 NVENC cell has `opened` = 12, and the limit probes read 12 of `max_tried` = 32. Read every N=16 NVENC row as 12 streams (N10).

| candidate · feed (queue item) | streams kept up, 1080p30 (largest tested N) | CPU cores at that N | unpaced aggregate fps at that N | 720p30 streams kept up (item) |
|---|---|---|---|---|
| h264_nvenc · NV12 (4) | **12** (N=16 requested, 12 opened; probe 12/32) | 0.611 (0.601–0.635), 3 reps | 541.79 | 12 (49) |
| h264_nvenc · YUY2 → swscale NV12 (45) | 12 | 2.526 (2.409–2.644), 2 reps | 540.44 | – |
| h264_nvenc · MJPEG CPU decode (41) | 12 | 4.057 (4.013–4.101) | 596.21 | – |
| hevc_nvenc · NV12 (5) | **12** (N=16 requested, 12 opened; probe 12/32) | 0.652 (0.586–0.656), 3 reps | 390.01 | 12 (50) |
| hevc_nvenc · MJPEG CPU decode (42) | 12 | 3.901 (3.769–4.033) | 377.97 | – |
| h264_qsv · NV12 (6) | **16** (probe 32/32 opened) | 1.246 (1.233–1.276), 3 reps | 679.40 | 16 (51) |
| h264_qsv · mjpeg_qsv decode (43) | 16 | 4.326 (4.303–4.350) | 485.54 | – |
| hevc_qsv · NV12, default mode (7) | **1** (N=4: 0 keep up in all 3 reps; N=2–3 not tested) | 0.155 (0.154–0.183) | 66.40 (about 2.2 × 30) | 4 (52) |
| hevc_qsv · mjpeg_qsv decode (44) | 1 (late 6, 7; N=2–3 not tested) | 0.431 (0.407–0.455) | 63.58 | – |
| hevc_qsv 4:2:2 · YUY2 (34) | 1 (N=2–3 not tested) | 0.153 (0.146–0.160) | 64.07 | – |
| mjpeg_qsv 4:2:2 · native YUY2 (33) | **16** (probe 32/32) | 0.915 (0.857–0.974) | 933.92 | – |
| mjpeg_qsv 4:2:0 · NV12 (8) | **16** (probe 32/32) | 1.050 (1.029–1.055), 3 reps | 700.43 | 16 (53) |
| nvJPEG 4:2:0 · NV12 via swscale RGB (9) | **8** (late 0, 73, 66; N=9–15 not tested). At N=16 only 1, 2 and 3 of 16 keep up; aggregate reaches 98.2% of the needed rate (`R/intra_compare/FINDINGS.md` §3.5) | 2.558 (2.466–2.566), 3 reps | 455.51 at N=8; 475.37 at N=16 | 16 (54; late 136, 0) |
| nvJPEG 4:2:2 · YUY2 via swscale RGB (32) | 16, with 383 and 955 of 7,200 frames late | 4.684 (4.630–4.739) | 567.47 | – |
| nvJPEG · decoded camera MJPEG | **not scaled**; CPU decode → swscale rgb24 misses A, mjpeg_qsv decode hits A (single-stream QC, below) | – | – | – |
| libjpeg-turbo 4:2:0 · NV12, process (10) | 16 | ≥1.685 (1.594–1.778), lower bound | 3,571.86 | 16 (55) |
| libjpeg-turbo 4:2:2 · YUY2, process (31) | 16 | ≥2.809 (2.482–3.137), lower bound | 1,742.22 | – |
| libx264 / libx265 | **not scaled** (no `matched_concurrent_libx26*` file) | single stream only, below | – | – |

- [measured] **nvJPEG fed CPU-decoded camera MJPEG through swscale rgb24 misses target A.** In single-stream item 1, the `nvjpeg_420` and `nvjpeg_422` rows with source `mjpeg_cpu` read `quality_check.ssim_y` 0.9954 (< 0.9961) and `psnr_y` 45.211 dB against `matched_psnr_y` 49.995 (`R/intra_compare/bench/matched_stream_A_1080p_20261110T042204Z.json`, `summary[]`; `R/intra_compare/FINDINGS.md:276-283`).
- [measured] **After `mjpeg_qsv` decode, nvJPEG hits target A.** The `nvjpeg_420` row with source `mjpeg_qsv` reads `ssim_y` 0.99788 and `psnr_y` 56.462 dB against `matched_psnr_y` 49.995 (same file, `summary[]`). There is no `nvjpeg_422` row for that source (`mjpeg_qsv` decodes to nv12, F5).
- [code] The QC uses the first 4 frames, all from the C930e; the C922 is never QC'd (`R/intra_compare/FINDINGS.md:270`, §5 flag 5). The cause of the spread between feeds is NOT VERIFIED. No scaling item fed nvJPEG decoded MJPEG.
- [measured] Single-stream CPU encoders at A, 1080p from NV12 (same file, `fps_median`, `cpu_cores_median`): libx264 ultrafast 372.47 fps at 5.476 cores; libx264 veryfast 229.19 fps at 7.116 cores; libx265 ultrafast 106.22 fps at 26.935 cores. libx265 widened the process affinity to CPUs 0–27, so its row is not a P-core figure (`R/intra_compare/FINDINGS.md` §5).
- [measured] Process-worker CPU is a lower bound: three unpaced N=8 process runs recorded negative CPU (`R/intra_compare/FINDINGS.md` §5).
- [measured, functional, no timing] `hevc_qsv` with the target-A options opens and writes 8/8 keyframes with `low_power=1`, with `preset=veryfast` and with both (`R/gpu_encode/verify_method_lowpower.json`, `cases[]`). Its speed in those modes is NOT VERIFIED.
- [inferred] On this machine, the hardware paths that kept up at the largest tested N (16 × 1080p30) with the target-A settings are h264_qsv, mjpeg_qsv (4:2:0 and 4:2:2) and, at its limit, nvJPEG from YUY2. NVENC carries 12 (session cap). nvJPEG from NV12 kept up at 8 (N=9–15 not tested). hevc_qsv in default mode kept up at 1 of the tested N (N=2–3 not tested).
- Scope: one run, one machine (RTX 3070 driver 610.88, UHD 770 driver 32.0.101.7088, CPUs 0–15). Lower-end CPUs, other GPUs, NVENC + QSV together, target B and file writing were not timed (`R/intra_compare/FINDINGS.md` §6).

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
- `R/intra_compare/NOTES.md` §6 was out of sync with MS (hevc_nvenc 55,112 / 144,376 vs MS 53,975 / 141,655; h264_nvenc yuy2_720p 83,921 vs 83,913; libx264_ultrafast / libx265 MJPEG cells).
  - [measured] Corrected on 2026-11-10 by gap-fill GF05: `R/intra_compare/NOTES.md:179, 181, 185, 186, 208` now carry the MS values, each marked "corrected 2026-11-10, GF05" (file read 2026-11-10; `R/intra_compare/gapfill/GF05_NOTES.md`).
- MS is the generated file and is used here.

## 4. Implications for the plan

1. **The target and G7 conflict for re-encoded formats, and the plan must say so** (§3.3).
   - Only H.264 and HEVC intra are hardware-encoded on both RTX 3000+ and the iGPU/APU of Intel, AMD and Apple 2020+ parts (N1, I1, A1, P1). Both are royalty-bearing (R2).
   - No royalty-free video codec meets the target:
     - AV1 fails on RTX 3000 and TGL–RPL (N2, I1, F4);
     - VP9 fails on NVIDIA, AMD and Apple (N3, A1, P2).
2. **JPEG baseline is the only format with no listed patents (R1) that is accelerated on both RTX 3000 and Intel TGL–RPL iGPUs.**
   - NVIDIA support is CUDA nvJPEG, which Dom counts as hardware (N6, N8). It is measured on Ampere; RTX 40/50 have SASS in the wheels used (nvimgcodec 0.10.0.9 pinned; nvjpeg 12.4.0.76 as resolved, unpinned) but were not run (N13; GF03).
   - Intel support is fixed-function `mjpeg_qsv` (F2). It is measured on RPL-S. Intel datasheets list JPEG hardware encode exposed through oneVPL/MFT on MTL and ARL-S/HX (Windows source, not tested through FFmpeg). LNL rests on a datasheet labelled "Confidential", and Arc B on Windows is NOT VERIFIED (I6).
   - It falls back to CPU on AMD and Apple (A1, P3).
   - Cost at camera-equivalent quality on raw YUY2, at matched chroma (luma-matched only; Gerald presets):
     - 4:2:0 JPEG is about 1.3–2.5x the bytes of hardware H.264/HEVC 4:2:0 intra;
     - 4:2:2 libjpeg-turbo is 1.9x hevc_qsv Rext 4:2:2 (Q7).
   - At PSNR-Y 45 dB the gap is 2.5–5.0x at 4:2:0 (Q7).
   - Capacity with the target-A settings on Gerald [measured, §3.3.1; no QC in the scaling runs]: mjpeg_qsv 16 × 1080p30 (the largest tested N) at 4:2:0 and 4:2:2; nvJPEG 8 from NV12 (N=9–15 not tested), 16 from YUY2 with late frames.
3. **For MJPEG cameras the target barely applies.**
   - Passthrough stores the camera's JPEG with no encoder (C3).
   - Camera JPEGs decode in the UI through ImageDecoder/createImageBitmap: 88/88 stills, and 450/450 byte-identical fetches from MKV (V4).
   - The hardware target decides only the G4 inputs (YUY2/NV12/Bayer).
   - On decoded MJPEG, re-encoding to H.264/HEVC gives files 9–36% smaller than the camera's bytes, at the cost of one more generation of loss (Q4).
4. **If JPEG is the recording format for G4 inputs**, the encoder choice is per vendor:
   - **nvJPEG on NVIDIA.**
     - It needs two proprietary NVIDIA wheels; ship them as an optional pip extra with a pinned nvjpeg version, not inside an installer (R5; GF03 §3).
     - nvImageCodec 0.10.0.9 accepts only RGB (N8).
     - The C API's NV12 input gives 4:2:0 only. The planar-YUV encode API exists in the measured library, but no Python binding for it was tested (N9).
     - Its size lead disappears at matched PSNR (Q2a).
     - Fed CPU-decoded camera MJPEG through swscale rgb24, it misses target A (SSIM-Y 0.9954, PSNR-Y 45.21 dB). After mjpeg_qsv decode it hits A (SSIM-Y 0.99788, PSNR-Y 56.46 dB). The QC uses the first 4 C930e frames only (intra_compare §5 flag 5) (§3.3.1, measured). This applies only if decoded MJPEG is ever re-encoded; passthrough avoids it (implication 3).
     - The Q2 ratios also hold only with an exact RGB conversion: PyAV swscale RGB costs about 6 dB PSNR-Y (IC §9.3).
   - **`mjpeg_qsv` on Intel**, fed `yuyv422` for 4:2:2, after expanding YUY2 to full range (F2, K5).
   - **libjpeg-turbo** everywhere else (C2).
5. **If H.264/HEVC intra is chosen** (accepting royalties):
   - **Prefer H.264 over HEVC for playback robustness.** HEVC decodes only in hardware in Electron (V2), and NVIDIA cannot decode HEVC 4:2:2 (F8).
   - **Record 4:2:0.**
     - 4:2:2 encode exists only on Intel QSV (HEVC Rext) and Blackwell (N2, F2).
     - Chromium does not decode it in hardware on Ampere (V5).
   - The CPU fallback in the wheel is GPL libx264/libx265 (R4).
   - Capacity with the target-A settings on Gerald [measured, §3.3.1; no QC in the scaling runs]: h264_qsv 16 × 1080p30 (the largest tested N); NVENC 12 (session cap); hevc_qsv in default mode 1 of the tested N (1/4/8/16; N=4 fails; N=2–3 not tested).
6. **The NVENC 12-session cap is a hard per-system limit, shared by `*_nvenc`, `*_d3d12va` and `*_mf` on NVIDIA** (N10, measured PyAV 19.0.2).
   - The quiet run re-confirmed it: the limit probes opened 12 of 32 (§3.3.1).
   - More than 12 cameras need a second engine (QSV, measured outside the pool), nvJPEG, or CPU.
   - Remote-desktop tools can hold sessions. nvidia-smi showed 1 foreign session during clip generation, with Parsec/Sunshine running (IP §2; FN §2).
   - The Intel "no limit" claim has an Intel source only up to 11th Gen (TGL/RKL); for ADL and later and Arc it is Jellyfin-only (J6).
7. **Implementation constraints (measured on Gerald):**
   - feed QSV encoders software frames, because hwctx mode fails (F3);
   - set NVENC `gop_size=0` (K4);
   - on AMF and VideoToolbox use `gop_size=1`, not 0, and AMF's own option names `rc=cqp, qp_i` (K6; code only, not run on hardware);
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

## 5. What happened to the old bench items (quiet run 20261109T230007)

- [measured] None of the 68 queued items is a `B-*` item, and no queued command runs a script under `S/hw_accel_target/`. `R/bench_queue_2300.json` has 68 `id` fields and 0 matches for `scripts/hw_accel_target`; `R/BENCH_RUN_2300_LOG.jsonl` has 0 matches for `"B-`.
- [measured] The queue replaced the old items with the matched-quality intra_compare benches (`S/intra_compare/bench_matched_stream.py`, `S/intra_compare/bench_matched_concurrent.py`) and listed the rest as dropped (`R/BENCH_QUEUE_2300.md:216-222`). `R/gpu_encode/FINDINGS.md` §6.1 records the same outcome for the gpu_encode items.
- [code] The replacement benches feed JPEG paths full range and H.264/HEVC limited range (`S/intra_compare/benchpaths.py:16-19`), so they do not have the K5 bug.
- Bracket reasons in `BENCH_QUEUE_2300.md` use the old numbering: `[9]` is now HANDOFF §1 requirement 3 (recording-format sub-bullet) and `[10]` is now requirement 8.

| old item (`R/hw_accel_target/NOTES_functional.md` line) | what it asked | answered by (queue item) | result files (`R/intra_compare/bench/` unless noted) |
|---|---|---|---|
| B-QSV-1 (:195) | per-stream fps and CPU per frame, QSV, 720p/1080p; sources nv12/yuy2/yuy2native/mjpeg_cpu/mjpeg_qsv | items 1–3 ("replaced by items 1-3", `BENCH_QUEUE_2300.md:216`) | `matched_stream_A_1080p_20261110T042204Z.json`, `matched_stream_A_720p_20261110T043459Z.json`, `matched_stream_B_1080p_20261110T044204Z.json` |
| B-NV-1 (:196) | same, NVENC | items 1–3 | same three files |
| B-DEC-1 (:198) | source pipeline cost | mjpeg_cpu / mjpeg_qsv rows minus nv12 rows of items 1–3, plus pipeline items 41–44 (`BENCH_QUEUE_2300.md:218`) | items 1–3 files; `matched_concurrent_{h264,hevc}_nvenc_420_1080p_mjpeg_cpu_thread_*`, `matched_concurrent_{h264,hevc}_qsv_420_1080p_mjpeg_qsv_thread_*` |
| B-CPU-1 (:197) | CPU baselines: libsvtav1, libvpx-vp9, mjpeg, ffv1 | FFmpeg mjpeg kept as the `ff_mjpeg_*` rows of items 1–3. libsvtav1 and libvpx-vp9 **dropped**: no RTX 3000 encode path. ffv1 covered for G4 by items 57 and 56 (`BENCH_QUEUE_2300.md:217`) | items 1–3 files; `R/uncompressed_intra/BENCH.md` |
| B-QSV-C1 (:199) | h264_qsv 1/4/8/16 + limit probe, 1080p | item 6 (+ 51 at 720p) (`BENCH_QUEUE_2300.md:219`) | `matched_concurrent_h264_qsv_420_1080p_nv12_thread_20261110T045738Z.json`; `…720p_nv12_thread_20261110T090121Z.json` |
| B-QSV-C2 (:200) | same, hevc_qsv | item 7 (+ 52 at 720p; also 34 and 44) | `…hevc_qsv_420_1080p_nv12_thread_20261110T051629Z.json`; `…hevc_qsv_420_720p_nv12_thread_20261110T090841Z.json` |
| B-QSV-C3 (:201) | same, vp9_qsv | **dropped**: "VP9 has no NVENC encoder" (`BENCH_QUEUE_2300.md:220`) | – |
| B-QSV-C4 (:202) | same, mjpeg_qsv | item 8 (+ 53 at 720p); 4:2:2 from YUY2 in item 33 | `…mjpeg_qsv_420_1080p_nv12_thread_20261110T052313Z.json`; `…mjpeg_qsv_420_720p_nv12_thread_20261110T091225Z.json`; `…mjpeg_qsv_422_1080p_yuy2_thread_20261110T064127Z.json` |
| B-QSV-C5 (:206) | h264_qsv 720p | item 51 (`BENCH_QUEUE_2300.md:222`) | `…h264_qsv_420_720p_nv12_thread_20261110T090121Z.json` |
| B-QSV-C6 (:208) | MJPEG CPU decode + hevc_qsv **gop30** | gop30 part **dropped** (intra only); intra pipelines added as items 41–45 (`BENCH_QUEUE_2300.md:222`). [inferred] The nearest hevc_qsv pipeline is item 44 (mjpeg_qsv decode, not CPU decode) | `…hevc_qsv_420_1080p_mjpeg_qsv_thread_20261110T083946Z.json` |
| B-QSV-C7 (:209) | mjpeg_qsv decode + vp9_qsv gop30 | **dropped** (VP9, gop30; `BENCH_QUEUE_2300.md:220`) | – |
| B-NV-C1 (:203) | h264_nvenc 1/4/8/16 + limit probe | item 4 (+ 49 at 720p) (`BENCH_QUEUE_2300.md:219`) | `…h264_nvenc_420_1080p_nv12_thread_20261110T044648Z.json`; `…h264_nvenc_420_720p_nv12_thread_20261110T085446Z.json` |
| B-NV-C2 (:204) | same, hevc_nvenc | item 5 (+ 50 at 720p) | `…hevc_nvenc_420_1080p_nv12_thread_20261110T045146Z.json`; `…hevc_nvenc_420_720p_nv12_thread_20261110T085747Z.json` |
| B-NV-C3 (:207) | h264_nvenc 720p | item 49 | `…h264_nvenc_420_720p_nv12_thread_20261110T085446Z.json` |
| B-NV-C4 (:210) | MJPEG CPU decode + h264_nvenc gop30 | intra part = item 41; gop30 dropped (`BENCH_QUEUE_2300.md:222`) | `…h264_nvenc_420_1080p_mjpeg_cpu_thread_20261110T081938Z.json` |
| B-MF-1 (:205) | per-stream MF + D3D12VA | **dropped**: MF and d3d12va land on the same RTX 3070 NVENC; d3d12va does not mux to MKV (`BENCH_QUEUE_2300.md:221`) | – |
| IP-SYNC/SEEK/SCRUB-E35/E45 | Electron decode cost, H.264/HEVC intra vs JPEG path | items 12–15, 25–26, 46–47 (intra_playback) | `R/intra_playback/BENCH.md` |

- [code] **The K5 range bug is still in `S/hw_accel_target/bench_encode_stream.py`.** `mjpeg_qsv` defaults to `nv12` (`:54`). YUY2 sources are reformatted to `nv12` with no range argument (`:112`). Decoded MJPEG sources are reformatted with `dst_color_range=1` for every non-`yuvj` format (`:119-124`).
- [measured] **No reported result uses that script.** It was not queued (first bullet), and `R/hw_accel_target/bench/` is empty (listing 2026-11-10).
- [code] The script also uses default rate control: its `ENC` table has empty QSV options and no `i_qfactor` (`:49-66`). Any future use needs both fixes; otherwise retire it in favour of the intra_compare benches.

## 6. Not tested / limits / NOT VERIFIED

- Hardware physically tested: only NVIDIA Ampere (RTX 3070) and Intel Xe-LP (RPL-S UHD 770). Every Turing, Ada, Blackwell, other TGLx, MTL/ARL/LNL, Arc, AMD and Apple cell is from primary sources only. Intel Windows-specific sources per cell: GF07.
- NVIDIA NOT VERIFIED:
  - nvJPEG encode on Turing/Ada/Blackwell (binaries present, not run; GF03);
  - whether nvJPEG's hardware-decode list covers GeForce Ada/Blackwell, and whether it decodes 4:2:2 there (N7);
  - nvImageCodec on Linux;
  - a Python binding for nvJPEG planar-YUV encode (the API exists in the measured library, GF03; N9);
  - whether the nvImageCodec 0.10 release notes (labelled beta) apply to wheel 0.10.0.9 (N9; GF03 R17, R18);
  - compute capability of laptop RTX SKUs (N13);
  - which licence governs the nvImageCodec wheel and which CUDA EULA governs the nvjpeg wheel (R5).
- Intel NOT VERIFIED:
  - Windows JPEG encode on Arc B (BMG); the Windows codec list for ARL-H/ARL-U. No Intel Windows source found (I6).
  - LNL on Windows, if the "Confidential"-labelled datasheet is not cited (I6).
  - HEVC 4:2:2 encode on LNL; Linux HEVC 4:2:2 on MTL/ARL/Arc A (J5).
  - Any `*_qsv` encode through FFmpeg/PyAV on MTL, ARL, LNL, Arc A or Arc B: sources only, no hardware tested (I6).
  - Intel/Linux QSV through the PyPI wheel; likely unusable per code (§3.2).
  - Windows-on-ARM64 `*_d3d12va`/`*_mf` (§3.2).
- Market NOT VERIFIED:
  - the share of 2020+ CPUs that are F/KF or otherwise have no iGPU (I5, A5);
  - the market shares of Intel, AMD and Apple, so "most CPUs" cannot be quantified.
- Other NOT VERIFIED:
  - Intel session limits for ADL and later and Arc (TGL/RKL and older have an Intel source), and AMD and Apple session limits (J6);
  - AMD `*_d3d12va`/`*_mf`/`*_amf` encode (A7);
  - the AMD 4:2:2 MJPEG decode conclusion (A6);
  - AMD vendor-vs-vendor cells (J9);
  - Apple hardware JPEG encode and HEVC 4:2:2 (P3, P4);
  - the base-M1 codec list (P1).
- AMF / VideoToolbox NOT VERIFIED (GF06; no AMD or Apple hardware):
  - AMF/VT honouring an every-frame IDR/keyframe on real hardware;
  - the `qp_i` (AMF) or `global_quality` (VT) value that reaches target A, and the bytes there;
  - whether VT Min/MaxAllowedFrameQP are accepted on M1-M4;
  - whether hevc_videotoolbox keyframes are IDR or CRA;
  - the AMF runtime version in each driver (the docs are SDK v1.5.3).
- Unexplained: why the H.264/HEVC `*_qsv`/`*_cuvid` decodes differ from software in the chroma planes (63.3–63.7 dB), while Y is identical (F9).
- Unexplained: why nvJPEG misses A after CPU MJPEG decode + swscale rgb24 but hits A after mjpeg_qsv decode (§3.3.1).
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
- Timing limits: the capacity numbers (§3.3.1) are from one quiet run on Gerald only, encode only (packets discarded), with the target-A settings and no QC in the scaling runs, on CPUs 0–15 [measured: `R/BENCH_RUN_2300_SUMMARY.md` §2; `R/intra_compare/FINDINGS.md` §2.5]. Only N = 1/4/8/16 were run, so each capacity value is the largest tested N that kept up, not a maximum (for example hevc_qsv N=2–3 and nvJPEG NV12 N=9–15 were not run). Not timed: scaling at target B; NVENC and QSV together; hevc_qsv `low_power` or other presets; libx264/libx265 with more than one stream; nvJPEG with process workers; any file writer in the loop [`R/intra_compare/FINDINGS.md` §6; `R/gpu_encode/FINDINGS.md` §6.2].
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
# licence texts for R6 (2026-11-10), copies in results/hw_accel_target/gapfill/GF04_src/ (SHA256SUMS.txt)
curl -sL -o libjpeg-turbo_LICENSE_main.md https://raw.githubusercontent.com/libjpeg-turbo/libjpeg-turbo/main/LICENSE.md   # sha256 ba6bceebcba0fdd35488477c2cca8c4632ce82c74dbfbc87d886ce6fc4433579
curl -sL -o simplejpeg_LICENSE https://raw.githubusercontent.com/jfolz/simplejpeg/master/LICENSE   # sha256 dcb18a8aa6b52844c238b5266ccca7964793c74759092f6c004c34a90d7fe6d4
```

Primary-source copies:
- NVIDIA/Intel: `R/hw_accel_target/sources_nv_intel/`. FETCH_MANIFEST.txt has the sha256 values.
- AMD/Apple: the scratchpad `hw_accel_target/src_amd_apple/`, pinned to the commits and tags in AAC §0.
- libjpeg-turbo and simplejpeg licences: `R/hw_accel_target/gapfill/GF04_src/`.

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
- §5 cites `S/intra_compare/bench_matched_stream.py` / `bench_matched_concurrent.py` as the requirement-9 bench (then numbered 11).
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

- intra_compare: `R/intra_compare/NOTES.md` §6 vs `matched_summary.md`: **closed.** GF05 corrected lines 179, 181, 185, 186 and 208 on 2026-11-10 (checked 2026-11-10; `R/intra_compare/gapfill/GF05_NOTES.md`). GF04 had found them still stale before that edit.
- hw_accel_target bench: the K5 range bug was **bypassed, not fixed**. No `S/hw_accel_target/` script was queued, so no result uses it (§5). The bug is still at `bench_encode_stream.py:112` and `:119-124`; fix it or retire the script before any future use. **Open.**
- FN §4: the "bit-identical" wording still needs the F9 correction (checked 2026-11-10: `NOTES_functional.md:118, 120`). **Open.**
- capacity: hevc_qsv at N=2–3 and nvJPEG NV12 at N=9–15 were never run; a quiet-machine run at those N would turn "largest tested N" into a maximum. **Open.**

### 8.5 Step 3 gap-fill (2026-11-10)

Inputs GF03, GF04, GF06 and GF07 (listed in the header). I opened each evidence file and re-checked the claims I applied:
- GF03: quote verification (72/72 `found_verbatim`), the fatbinary lists in `GF03_wheel_arch_facts.json`, and the header lines in `GF03_sources/nvjpeg_h_12.4.0.76_lines.txt`.
- GF04: every §3.3.1 number against `GF04_capacity.json`; the code lines in `bench_encode_stream.py` and `bench_matched_concurrent.py`; `BENCH_QUEUE_2300.md:216-222`; the queue and log grep counts; the empty `R/hw_accel_target/bench/`; the R6 licence text and sha256.
- GF06: the FFmpeg n9.0.2, AMF SDK v1.5.3 and Apple excerpts in `GF06_sources/`, plus the raw AMF doc for lines 1417 and 1498.
- GF07: the Intel quotes in `GF07_sources/`.

| id | section(s) | what changed | why (evidence) |
|---|---|---|---|
| GF03 | N6 | version-gap bullet replaced; gap closed | measured wheel 12.4.0.76 = CUDA 12.9.1 libnvjpeg (R04, R05, R22); 12.9.1 docs carry the same encode statements (R06, R07, R09) |
| GF03 | N7 | added the 12.9.1 decode list, the CUDA 12.8 Blackwell note and the 12.4.0 list | R06, R10, R01; GeForce applicability still NOT VERIFIED |
| GF03 | N9; §4.4; §6 | "planar-YUV encode in 12.4 NOT VERIFIED" → the API exists in the header [code]; a binding is NOT TESTED | wheel `nvjpeg.h:154, 159, 540, 560`; R19, R20 |
| GF03 | new N13; §3.1 NVIDIA JPEG cells and legend; §3.3 JPEG row; §4.2; §6 | RTX 20/40/50 nvJPEG: "inferred" → "code present, not run"; hardware JPEG encode is Jetson Thor only | static fatbinary parse (not cross-checked with cuobjdump); R14; K01-K04; R06, R07, R09 |
| GF03 | R5; §4.4; §6 | R5 widened to nvJPEG, the benchmark clause, the licence-channel conflict and the OSI "develop and test" permission; optional pip extra recommended (inferred, not legal advice) | W01, W03-W07, W10, G01, H01, C02, C03, C04, C06, C11, C13, E01, E04; GF03 §3 |
| GF04 | header; §6 | "no timing" replaced; timing-limits bullet replaces "no timing yet" | `R/BENCH_RUN_2300_SUMMARY.md` §1-§2 |
| GF04 | §3.3 column; new §3.3.1; N10; §4.2, §4.4, §4.5, §4.6 | measured capacity with the target-A settings added (hevc_qsv 1 of the tested N in default mode; NVENC 12; nvJPEG misses A on CPU-decoded MJPEG, hits A after mjpeg_qsv decode) | `GF04_capacity.json` from `R/intra_compare/bench/*.json`; step 3 verification (§8.6) |
| GF04 | §5 | "Pending tonight's bench" replaced with the mapping of old B-* items to queue items | `R/BENCH_QUEUE_2300.md:216-222`; `R/bench_queue_2300.json`; `R/BENCH_RUN_2300_LOG.jsonl` |
| GF04 | K5; §5; §8.4 | K5 line range :120-124 → :119-124 and `:54` added; bug bypassed, not fixed; no result uses the script | `bench_encode_stream.py:54, 112, 119-124`; empty `R/hw_accel_target/bench/` |
| GF04 | §3.3 readings; R6 (new); §4.2 heading | "JPEG is royalty-free" split into patents (R1) vs code licence (R6, new) vs GPL (R4); "royalty-free" → "no listed patents (R1)" | R1 covers patents only; R4 is [measured] and silent on libjpeg-turbo; libjpeg-turbo and simplejpeg licence texts (sha256 checked) |
| GF04 | header line 3; §3.1 legend; §8.2 | requirement numbers remapped to HANDOFF §1 (3, 8, 9) | current HANDOFF §1 numbering |
| GF06 | new A8, P5, K6, K7; K3; §3.2 AMD/Apple rows; §3.3 AMD/Apple cells; §3.3 readings; §4.7; §6 | AMF and VideoToolbox all-intra and matched-quality knobs from code and vendor docs; `gop_size=0` is not intra on AMF; VT has no constant QP in FFmpeg; K3 limited to NVENC/QSV; on-hardware NOT VERIFIED | FFmpeg n9.0.2 code, AMF SDK v1.5.3 docs, Apple docs JSON (`GF06_sources/`); `GF06_pyav_options.json` |
| GF07 | labels; I5; I6; J5; J6; §3.1 Intel rows and legend; §3.3 JPEG row; §4.2; §4.6; §6 | [source (transcribed)] retired; Intel Windows encode re-sourced from raw Intel pages; new ARL-H/U row (NV); MTL/ARL-S HEVC 4:2:2 is Win Y / Linux N; Arc B Windows JPEG NV; Intel "no session limit" sourced for TGL/RKL and older only | `GF07_sources/` excerpts (oneVPL doc, datasheets, KB 000098345, ark, S3 article) |

Deviations from the proposed text:
- GF04 item 5 said the intra_compare NOTES §6 follow-up was still open. GF05 has since corrected those lines (read 2026-11-10), so §3.4 and §8.4 mark it closed.
- GF07 S7 (Lunar Lake datasheet) is labelled "Confidential" on the page. The LNL cells keep the caveat, and §6 lists the fallback (NOT VERIFIED) in case Dom does not allow citing it.
- Added for consistency with the changes above: §4.4 planar-YUV bullet (follows N9), the §4.4 decoded-MJPEG bullet and the §4.2/§4.5/§4.6 capacity bullets (follow §3.3.1), the §4.7 AMF/VT `gop_size=1` bullet (follows K6), and the R5 C04/E04 bullet (GF03 §3.1).
- Nothing else changed. §8.1-§8.3 are kept as the 2026-11-09 revision history.

### 8.6 Step 3 verification (VS3, 2026-11-10)

VS3 verdict: PASS WITH FIXES. It recomputed every §3.3.1 cell from the 24 raw `matched_concurrent_*.json` files and confirmed the GF03/GF04 numbers and quotes. I re-checked each point below before applying it.

| # | VS3 point | my re-check | change |
|---|---|---|---|
| X1 (refuted) | "nvJPEG fed decoded camera MJPEG misses A" | `matched_stream_A_1080p_20261110T042204Z.json` `summary[]`: `mjpeg_cpu` source nvjpeg_420/422 ssim_y 0.9954, psnr_y 45.211; `mjpeg_qsv` source nvjpeg_420 ssim_y 0.99788, psnr_y 56.462, matched 49.995. `R/intra_compare/FINDINGS.md:270, 276-283` agree (QC = 4 C930e frames) | narrowed to CPU decode → swscale rgb24; mjpeg_qsv-decode hit added; QC scope added (§3.3, §3.3.1, §4.4, §6) |
| W1 | hevc_qsv "1", nvJPEG NV12 "8" read as maxima | `bench_matched_concurrent.py:243` `--streams` default "1,4,8,16" | "largest tested N" wording; N=2–3 / N=9–15 not tested (§3.3, §3.3.1, §4.2, §4.5, §6, §8.4) |
| W2 | "pinned nvJPEG wheels" | `R/gpu_encode/NOTES.md:148`: nvimgcodec 0.10.0.9 pinned, it "pulled" nvjpeg 12.4.0.76 | N13, §4.2: "wheels used (nvimgcodec 0.10.0.9 pinned; nvjpeg 12.4.0.76 as resolved, unpinned)"; R5/§4.4 now recommend a pinned nvjpeg version |
| W3 | R5 cites C04, C05 for restrictions | GF03 lines 49-55: C04 is a permission, C05 the component-licence conflict rule; C11 is a condition | R5 cites C02, C03, C06, C11, C13 |
| W4 | K01-K04 cover only one SKU each | saved page `cuda_gpus.txt:26-32, 57-63, 78-87, 106-109` list the other RTX SKUs under the same headings | N13 cites those lines (scratchpad), "representative desktop SKU"; laptops not checked (§6) |
| W5 | R19/R20 from beta-labelled notes | GF03 line 97 (R17, R18): "v0.10.0-beta.11", applicability NOT VERIFIED | caveat added to N9 and §6 |
| W6 | wrong lines for frame counts and workers | `bench_matched_concurrent.py:10-16` (workers, keeps-up), `:127-131`, `:245-246` (450 / 300 defaults) | citation fixed in §3.3.1 |
| W7 | "capacity at target A" implies a QC | `R/intra_compare/FINDINGS.md` §5 flag 5 | scope bullet added; headings and column say "target-A settings" |
| W8 | R6 copies only in the scratchpad | sha256 of both scratchpad copies matches; quotes present (line 4, line 1) | copied to `R/hw_accel_target/gapfill/GF04_src/` with `SHA256SUMS.txt` (sha256 unchanged after copy); R6 and §7 cite the copies |
