# uncompressed_intra (G4): findings (revised after the quiet bench and two verifiers, 2026-11-10)

Machine: Gerald. i7-14700K (20 cores / 28 logical; `results/BENCH_RUN_2300_SUMMARY.md` row "Machine"), RTX 3070, driver 610.88 (`bench/precheck_nvsmi.txt`), Intel UHD 770 iGPU present, Windows 11, Defender real-time protection ON.

**What this revision changes**
- The timed numbers now come from the quiet run `20261109T230007`, items UI-GPU-AV19 (35), UI-BAYER-AV19 (56) and UI-CORE-AV19 (57). These are PyAV 19.0.2 (FFmpeg 9.0.2) runs, pinned to the 8 P-cores (16 logical CPUs).
- They replace the contaminated PyAV 18 rows for the same configs.
- Configs that were not re-run keep their contaminated numbers. Those numbers are marked as background (§2.8).
- Earlier statements that the new data correct or supersede (§2.7):
  - the rule "every contaminated number is a lower bound on speed" is withdrawn for cross-version comparisons;
  - the "PyAV 19 vs 18" bullet had the versions reversed and is removed;
  - the earlier NVENC decode (12-24 fps) and 720p (327-876 fps) figures were correct for the loaded PyAV 18 files and are **superseded by quiet numbers**.
- After verification: the truncation result is broader than first stated (§2.4); the 12-bit NVENC question is answered by source (§2.5); FFV1 s24 on NV12/Bayer8 and the five 720p NVENC lossless rows are now verified exact (§2.3); the NVENC lossless coded profiles are recorded (§2.5).
- Step 3 (gap-fills GF05, GF09, then `VERIFY_step3.md`): QSV lossless tested and not available; NVENC lossless timed configs re-checked over 300 frames; Chromium playback of NVENC lossless NV12 tested; the libx265 4:2:0 Chromium sample relabelled Rext.

Paths are relative to `research/skellycam_recording/recording_upgrade/results/uncompressed_intra/` unless they start with `research/` or `results/` (`results/` = `research/skellycam_recording/recording_upgrade/results/`). Tonight's files are `bench/<config>__<source>_<res>__t<threads>__pyav19.0.2_q2300.json`. Tables below give the `<config>__<source>_<res>` stem.

**Labels**
- **measured**: a PyAV 19.0.2 result file, cited by path.
- **background (PyAV 18.0.0)**: a result from the skellycam venv (PyAV 18.0.0 / FFmpeg 8.1.2), or an older loaded PyAV 19 run. Context only.
- **CLI reference**: the ffmpeg 9.0.2 CLI (gyan build, libavcodec 63.1.102). This is not the implementation under test.
- **source**: a primary source, quoted, with its access date.
- **code**: repo or library file:line.
- **cross-reference**: a claim taken from another topic's FINDINGS; its primary evidence is there, not re-checked here.
- **arithmetic**: computed from cited numbers.
- **inferred**: my reasoning, marked as such.
- **NOT VERIFIED**: no evidence either way.

**Units**
- KB = 1000 bytes of encoded packet payload per frame. Container overhead is excluded.
- cores/stream = process CPU seconds per second of 30 fps video. 1.0 means one core fully busy.
- t1 = `thread_count=1`; t0 = libav auto threads.
- Tonight's bench values are **median (min-max) over 3 reps of 300 frames**. The 3 reps ran back to back in one process on one night, so min-max is within-run spread only; run-to-run variation is not measured.

**Quality targets**
- Every lossless row is exact, so no quality target applies to it.
- The few lossy rows (hevc_nvenc CQ qp 24, mjpeg q2, dnxhr, prores, svtav1 crf30, QSV defaults and QSV QPI 1-10) are **at neither target A nor target B**.
- Matched-quality H.264/HEVC/JPEG numbers at A and B are in `results/intra_compare/`.

**Hardware target**
- **NVENC rows: hardware-encoded on NVIDIA** (measured, one RTX 3070).
- **inferred** (from the three bullets below): **the lossless formats (H.264 High 4:4:4 Predictive lossless, HEVC Main/Main 10 lossless) do NOT meet the hardware target.** Quick Sync cannot write them, so they are NVIDIA-only.
  - **measured** (`gapfill/GF09_rows_qsv_pyav19.0.2.json`; UHD 770, driver 32.0.101.7088 per `gapfill/GF09_gpu_drivers.json`): h264_qsv/hevc_qsv all-intra (gop 1), CQP QP 0/1/4, low_power auto/on/off, transform_skip 1, profile rext; inputs NV12, Bayer8 quad as NV12, Bayer8 quad as VUYX (4:4:4), camera YUY2. 33 configurations tried, 32 encoded 300 frames, **0/300 frames exact in every one**. Smallest max abs diff 2; highest PSNR-Y min 65.42 dB (Bayer8 quad, Y only), 65.33 dB on NV12 and YUY2 (background).
  - **code** (FFmpeg n9.0.2, commit 946fcce0): "lossless" occurs 0 times (case-insensitive) in `qsvenc.c`, `qsvenc.h`, `qsvenc_h264.c`, `qsvenc_hevc.c` and `qsv.c`.
  - **source** (Intel oneVPL `api/vpl/mfxstructures.h`, tag v2.15.0, line 913, https://raw.githubusercontent.com/intel/libvpl/v2.15.0/api/vpl/mfxstructures.h, accessed 2026-11-10): "Zero QP is not valid and means that the default value is assigned by the library."
  - Details in §2.5.
- Other Intel generations: NOT VERIFIED. AMF and VideoToolbox lossless: NOT VERIFIED (no hardware).
- **OUTSIDE target:** FFV1, rawvideo and every other CPU codec. They count only as the **G4 CPU fallback**.

## 1. Questions answered
1. Which codecs store each uncompressed camera format bit-exact and intra-only, natively or after an exact re-layout? Formats: YUY2, NV12, GRAY8/16, P010, RGB, Bayer 8/12, packed RAW10/12.
2. Which of these paths are hardware-encoded (NVENC/QSV), and which are CPU fallback only?
3. What does each option cost on a quiet machine: encode fps, host CPU per 30 fps stream, bytes per frame, decode speed?
4. Which containers keep the pixel format, and what survives truncation?
5. Bayer: raw mosaic, plane-split (quad) mosaic, or debayered RGB?
6. What can Chromium (Electron 35/45) play natively?
7. Do PyAV 19.0.2, OpenCV 5.0.0.93 or Electron 45.2.3 add useful support?

## 2. Findings

### 2.1 Inputs
- **measured** (code `scripts/uncompressed_intra/uintra_frames.py` docstring; corpus `index.json`): the YUY2 frames are the cameras' own bytes, `c930e_1080p_yuy2` and `c922_1080p_yuy2`, 8 frames each.
- **measured** (same): every other source is derived from C930e YUY2: NV12, gray, gray16, P010, RGB, Bayer 8/12, quad split and RAW10/12-packed. The 720p "YUY2" is decoded `c930e_720p_flash` JPEGs (code `bench_intra.py:99`).
- **measured** (every tonight JSON: `unique_frames` 8, `looped` true, `frames` 300): the timed bench loops the 8 C930e frames to 300.
- **measured** (`loose_ends_check.json`, numpy only): camera YUY2 is limited range.
  - c930e: Y 18..234, C 115..151.
  - c922: Y 16..235, C 95..181.
  - 0 samples fall outside 16..235.
- **measured** (`ffv1_recheck_pyav19.0.2.json`): sizes depend on content.
  - The same FFV1 v3 s24 rice g1 config gives 470.3 KB/f on C930e YUY2 and 740.7 KB/f on C922 YUY2 (+58%).
  - Both are bit-exact over 8 frames.
  - Every size here comes from the C930e scene unless stated otherwise.
- **CLI reference** (`verify_method/ffv1_size_by_camera.txt`): decoded C930e 1080p JPEGs give 325.1 KB/f, against 470.3 for real C930e YUY2.
- **inferred:** the 720p (JPEG-derived) sizes are probably flattered.
- **code** (`uintra_frames.py:17-19, 23, 25`): every source above 8 bits carries seeded synthetic noise in its low bits: gray16le and 12-bit Bayer 4 bits; P010 and RAW10-packed 2 bits.
- **measured** (`ffv1_recheck_pyav19.0.2.json`, FFV1 v3 s24, 1 frame, all exact): 12-bit sizes are dominated by that noise.

| 12-bit layout | noise=True | noise=False | share from noise (arithmetic) |
|---|---|---|---|
| quad split (gray16le) | 1,617,493 B | 504,260 B | 69% |
| mosaic (gray16le) | 2,347,875 B | 1,219,858 B | 48% |

- **inferred:** P010 and RAW10 sizes and lossless encode speeds are probably noise-inflated too (hevc_nvenc P010 is 2.75x the NV12 size, §3.1). No noise=False run exists for them.
- **code** (`uintra_frames.py:21`, `bayer8_from_rgb` at line 155): the 8-bit Bayer mosaic is sampled from an rgb24 conversion of ISP-processed 4:2:2 YUY2.
- **inferred:** its R and B samples come from upsampled chroma and are unnaturally smooth, so Bayer sizes (especially the quad-split gain) are synthetic-content results. The direction of the error against real raw data is unknown.
- **inferred** (path name `pyav_ds_1920x1080_5` in corpus `index.json`): both YUY2 sets look like 5 fps captures.
  - NOT VERIFIED that either camera delivers 1080p30 YUY2.
  - "Per 30 fps stream" is only a normalisation.

### 2.2 Library capability and versions
- **measured** (`pyav_caps_19.0.2.json`): PyAV 19.0.2 bundles libavcodec 63.1.102 (FFmpeg 9.0.2).
- **background** (`pyav_caps_18.0.0.json`): PyAV 18.0.0 bundles libavcodec 62.28.102 (FFmpeg 8.1.2).
- **measured** (`pyav_caps_19.0.2.json`): PyAV 19.0.2 has no encoder for libopenjpeg, libjxl, libaom-av1, librav1e or libsvtjpegxs, and no JPEG XL or JPEG XS decoder.
- **measured** (`pyav_caps_{18.0.0,19.0.2}.json`): the only encoder pix_fmt changes from 18 to 19:
  - ffv1 gains `bayer_rggb16le`;
  - h264/hevc/av1_nvenc gain `p012le`, `p212le` and `yuv444p12msble` (truncated to 10 bits, §2.5).
- **measured** (`pyav_mux_acceptance_19.0.2.json`): PyAV refuses Matroska for ffvhuff, huffyuv, utvideo, magicyuv, jpegls, png and dnxhd.
  - NUT and AVI accept all of these except dnxhd.
  - dnxhd is accepted only in MOV.
- **source** (PyAV 19.0.2 wheel, `av/container/output.py:166-171`, read from the uv environment 2026-11-09, re-checked 2026-11-10): `if not lib.avformat_query_codec(self.ptr.oformat, codec.id, lib.FF_COMPLIANCE_NORMAL): raise ValueError(f"{self.format.name!r} format does not support {codec_obj.name!r} codec")`.
- **CLI reference** (`ffmpeg_cli_reference.json`): the ffmpeg 9.0.2 CLI muxes utvideo, ffvhuff, magicyuv and jpegls into MKV, bit-exact. So the refusal is PyAV's compliance gate, not a Matroska limit.

### 2.3 Pixel format -> codec (bit-exact)
All bullets in this section are measured from `functional_matrix_pyav19.0.2.json` / `functional_tables.md` (4 real 1080p frames, 15 sources x 37 configs) unless labelled otherwise.
- No lossless encoder that opens here takes packed 4:2:2.
  - Every exact path de-interleaves YUY2 to yuv422p, which is exact.
  - Only rawvideo stores YUY2 as-is.
- hevc_qsv (lossy) lists `yuyv422` (`pyav_caps_19.0.2.json`) and encodes camera YUY2 directly (§2.5).
- NV12 is native in libx264, h264_nvenc and hevc_nvenc. Every other encoder needs NV12 -> yuv420p, which is exact.
- GRAY16 is native in ffv1, ffvhuff, jpegls and jpeg2000. libx265 is exact via gray12le.
- hevc_nvenc fed yuv444p16le decodes as yuv444p10le, so it is not exact (cause in §2.5).
- P010 is exact natively only in hevc_nvenc lossless. Every other encoder needs shift + de-interleave to yuv420p10le, which is exact.
- FFV1 with the default GOP produces non-keyframe packets (`ffv1_l1_gdefault.mkv`). Every `-g 1` FFV1 config is all-keyframe.
- **measured** (`verify_method/exact_check_step2_pyav19.0.2.json`; PyAV 19.0.2, 4 frames, the bench's own configs and path code):
  - `ffv1_l3_s24_crc_g1.mkv` is bit-exact and all-keyframe at 1080p on NV12 (via yuv420p) and on the Bayer8 mosaic (as gray);
  - at 720p (JPEG-derived input), h264_nvenc lossless on NV12 and gray, and hevc_nvenc lossless on NV12, P010 and the Bayer8 mosaic, are bit-exact and all-keyframe.
- **source** (RFC 9043, https://www.rfc-editor.org/rfc/rfc9043.txt, accessed 2026-11-09, re-fetched 2026-11-10): §4.2.17 "intra": value 1 means ""keyframe" MUST be 1 (keyframes only)".
- **source** (same, §3.8.2.5): "When "keyframe" (see Section 4.4) value is 1, all VLC coder state variables are set to their initial state."

### 2.4 Containers and truncation
- **measured** (`functional_tables.md`, PyAV 19):
  - NUT keeps bayer_rggb8/16le, gray16le, rgb24 and nv12 bit-exact.
  - p010le in NUT reads back as rgb555le.
  - MKV rawvideo works only for yuyv422, nv12, yuv420p, gray and 8-bit quad/packed-as-gray.
- **source** (FFmpeg n9.0.2 `libavformat/matroskaenc.c:2042-2043`, re-checked 2026-11-10): "Raw RGB is not supported Natively in Matroska, you can use AVI or NUT or".
- **measured** (`functional_tables.md`, "Lossless configs that decoded but were not bit-exact"):
  - AVI loses gray16le and p010le, returns rgb24 as bgr24, and cannot decode Bayer.
  - MOV returns gray as pal8 and gray16 as rgb555be, and cannot decode nv12, yuv420p, p010 or Bayer.
- **measured** (`functional_matrix_pyav19.0.2.json`, `trunc50_*`, all 15 sources; a 50% cut of a finalized 4-frame file; 275 exact lossless MKV/NUT/AVI cases):
  - MKV, NUT and AVI returned 1-3 frames (1 frame: 51 cases, 2: 217, 3: 7).
  - **In 18 of the 275 cases the cut frame came back silently corrupted** (frames decoded > frames exact). All 18 are in NUT or AVI:
    - `jpegls.nut` (10 sources: gray, gray16le, rgb24, bgr24, bayer_rggb8, bayer_rggb16le, raw12_packed, raw10_packed, bayer8_quad, bayer16_quad);
    - `ffvhuff_median.nut` (bayer_rggb8, bayer_rggb16le, raw12_packed, raw10_packed);
    - `magicyuv_median.avi` (bayer_rggb8, raw12_packed, raw10_packed);
    - **`ffv1_l3_s4_crc_g1.avi` on raw12_packed** (FFV1 in AVI).
  - **No MKV case returned a corrupted frame.** NVENC lossless in MKV kept 1-2 exact frames.
  - `rawvideo.avi` kept 0 frames on both Bayer sources (bayer_rggb8 and bayer_rggb16le).
  - Every MOV/MP4 config decoded 0 frames. This includes `hevc_nvenc_intra_cq.mp4` ("moov atom not found").
- **code** (`scripts/uncompressed_intra/functional_matrix.py:403-410`): this is a cut of a finalized file, not a writer crash. Writer-kill tests belong to `results/crash_resilience/`.
- **inferred:** the FFV1-in-AVI corruption suggests the slice CRC is not checked by the default decode path in that case; not tested further.

### 2.5 GPU encoders (functional)
- **measured** (`functional_matrix_pyav19.0.2.json`): h264_nvenc lossless (preset p1, tune lossless, gop 1) is exact for:
  - nv12 / yuv420p (native);
  - gray (Y + neutral chroma);
  - rgb (via gbrp);
  - bayer_rggb8 mosaic as Y;
  - bayer8_quad;
  - raw10/raw12 packed bytes as Y.
- **measured** (same file): hevc_nvenc lossless is exact for all of those inputs plus p010le (native).
  - Every one of these cases is all-keyframe over 4 frames.
- **measured** (`verify_method/nvenc_lossless_profile_step2_pyav19.0.2.json`, 2 frames, 1080p): coded profiles.

| encoder (p1, tune lossless) | input | coded profile |
|---|---|---|
| h264_nvenc | nv12 | High 4:4:4 Predictive |
| hevc_nvenc | nv12 | Main |
| hevc_nvenc | p010le | Main 10 |

- **measured** (`functional_matrix_pyav19.0.2.json`, `packet_bytes_mean`, 4 frames): Bayer8 through NVENC lossless (synthetic Bayer, §2.1).

| Bayer8 layout | h264_nvenc lossless | hevc_nvenc lossless | rawvideo |
|---|---|---|---|
| mosaic as Y | 1,803,645 B | 1,368,828 B | 2,073,600 B |
| quad split as Y | 767,200 B | 681,534 B | (same bytes) |

- **measured** (same file): raw12/raw10 packed bytes through hevc_nvenc are exact but 3,141,306 / 2,326,082 B per frame.
- **measured** (`bayer_debayer_check_pyav19.0.2.json`, `raw_bytes.bayer12_packed_raw12`): the raw12-packed frame is 3,110,400 B, so NVENC gives no saving on packed 12-bit. These sources carry synthetic noise (§2.1).
- **measured** (`functional_matrix_pyav19.0.2.json`): 12-bit sources through hevc_nvenc are not exact. Fed as yuv444p16le (gray16le, bayer_rggb16le, bayer16_quad), they decode as yuv444p10le.
- **source** (FFmpeg n9.0.2 `libavcodec/nvenc.c`, fetched 2026-11-10, copy in `.../scratchpad/step2/uintra_prov/nvenc.c`), the NVENC input list `ff_nvenc_pix_fmts`:
  - line 58: `AV_PIX_FMT_P012,      // Truncated to 10bits`;
  - line 63: `AV_PIX_FMT_P212,      // Truncated to 10bits`;
  - line 67: `AV_PIX_FMT_YUV444P12MSB, // Truncated to 10bits`;
  - line 68: `AV_PIX_FMT_YUV444P16, // Truncated to 10bits`.
- **source** (same): FFmpeg truncates every 12-bit and 16-bit NVENC input to 10 bits, so no exact 12-bit NVENC path exists in this build. Line 68 explains the measured yuv444p16le -> yuv444p10le result. A `yuv444p12msble` request was not run; the source answers it.
- **measured** (`functional_tables.md`, encoder errors, PyAV 19):
  - h264/hevc_nvenc on 4:2:2: "YUV422P not supported; ... No capable devices found";
  - h264_nvenc on gray16/Bayer16: "10 bit encode not supported";
  - av1_nvenc: "Codec not supported".
- **source** (FFmpeg n9.0.2 `libavcodec/nvenc.c:445-453`, re-checked 2026-11-10): `if (IS_YUV422(ctx->data_pix_fmt) && ret <= 0) { av_log(avctx, AV_LOG_WARNING, "YUV422P not supported\n");`.
- **code** (FFmpeg n9.0.2, fetched 2026-11-10): `nv16` is in `ff_nvenc_pix_fmts` only under `#ifdef NVENC_HAVE_422_SUPPORT` (nvenc.c:60-61). The macro is defined for SDK 13.0+ (nvenc.h:67-69). Under it, `ret` comes from the GPU capability query `nvenc_check_cap(avctx, NV_ENC_CAPS_SUPPORT_YUV422_ENCODE)` (nvenc.c:445-446).
- **measured** (`pyav_caps_19.0.2.json`): `nv16` is listed for NVENC, so this build has 4:2:2 support compiled in.
- **inferred** (from the three bullets above): the 4:2:2 refusal comes from the RTX 3070's capability report, not from the FFmpeg build.
- **cross-reference** (`results/hw_accel_target/FINDINGS.md` N2, NVIDIA NVENC application note): "4:2:2 encoding | N | N | Y"; 4:2:2 NVENC starts at Blackwell (RTX 50). Primary URL and access date are in that topic, not re-checked here.
- **cross-reference** (`results/hw_accel_target/FINDINGS.md` N1, NVIDIA support matrix): row "H.264 (AVC) YUV 4:2:0/4:2:2/4:4:4/Lossless" = "YES NO YES YES" for Turing/Ampere/Ada.
  - So H.264 lossless is hardware-listed on RTX 2000-4000 (per that topic).
  - HEVC lossless on other RTX 3000+ SKUs is measured only on this RTX 3070.
- **measured** (`qsv_recheck_pyav19.0.2.json`; 4 C930e YUY2 1080p frames, gop 1, encoder defaults, lossy, at neither A nor B):

| encoder | input | result | decoded | profile | keyframes | Y PSNR min |
|---|---|---|---|---|---|---|
| hevc_qsv | yuyv422 (camera bytes) | ok | yuv422p | Rext | 4/4 | 50.64 dB |
| hevc_qsv | nv12 | ok | yuv420p | Main | 4/4 | 50.65 dB |
| h264_qsv | nv12 | ok | yuv420p | High | 4/4 | 50.12 dB |
| av1_qsv | nv12 | open fails: "Function not implemented" | - | - | - | - |

**Lossless on Quick Sync (gap-fill GF09, functional, 300 looped frames, UHD 770)**
- **measured** (`gapfill/GF09_rows_qsv_pyav19.0.2.json`, `libav_param_dump` per row): no QSV configuration is exact (header, "Hardware target"). The effective parameters the runtime reported back:

| request | QPI used | VDENC | KB/frame (NV12 / YUY2) | max abs diff Y |
|---|---|---|---|---|
| CQP QP 0 or 1, default low_power | 1 | OFF | hevc 437.6 / 562.9; h264 532.9 / - | 2 |
| CQP QP 4, transform_skip 1 (hevc) | 4 | OFF | 332.7 / 427.3 | 3 |
| CQP QP 1, low_power 1 | 10 | ON | hevc 164.6 / 164.6 (4:2:0, see below); h264 201.7 / - | 4 |
| any QP, Bayer8 quad as VUYX (4:4:4), hevc | 10 | ON | 306.7 (Rext 4:4:4) | 3 |

- **measured** (same file): a requested QP 0 runs at QPI 1; QP 0 and QP 1 give identical sizes and errors.
- **measured** (same file): with `low_power=1` both encoders run at QPI 10; hevc_qsv reports `MinQPI: 10`.
- **measured** (same file): VUYX (4:4:4) input always ran with VDENC ON at QPI 10, even without `low_power=1`; with `low_power=0` it failed with "Invalid FrameType:0." (InvalidDataError on send).
- **measured** (same file): **hevc_qsv with `low_power=1` on camera YUY2 silently writes HEVC Main 4:2:0** (`libav_warnings` empty). Without low_power the same input gives Rext 4:2:2.
- **measured** (same file): every QPI-1 row has max abs diff 2 on Y; PSNR-Y min is 65.33-65.42 dB for hevc_qsv and 64.42-64.84 dB for h264_qsv.
- **measured** (same file): on camera YUY2 the best result is hevc_qsv Rext 4:2:2 at QPI 1: PSNR-Y min 65.33 dB, max abs diff 2,1,2 (Y,U,V), 562.9 KB/frame. It is lossy and at neither target A nor target B.
- **measured** (same file): every QSV row that encoded (32/33) is all-intra, with 300/300 keyframe packets. The 33rd row (`hevc_qsv__cqp_qp1_lp0__bayer8_quad_as_vuyx`) failed on send and wrote no packets.
- **code** (FFmpeg n9.0.2 `libavcodec/qsvenc.c:929-931`): `q->param.mfx.QPI = av_clip(quant * fabs(avctx->i_quant_factor) + avctx->i_quant_offset, 0, 51);` (H.264/HEVC; QPP and QPB alike).
- **code** (FFmpeg n9.0.2 `libavcodec/qsvenc_h264.c:152-156`): h264_qsv profiles are `unknown`, `baseline`, `main`, `high`; no 4:4:4 profile.
- **code** (same file, line 202): `CODEC_PIXFMTS(AV_PIX_FMT_NV12, AV_PIX_FMT_QSV),`, so h264_qsv takes NV12 only.
- **measured** (`gapfill/GF09_avoptions_pyav19.0.2.json`, static AVOptions query of the wheel's libavcodec): neither h264_qsv nor hevc_qsv has an option whose name or help contains "lossless".
- Full table and code citations: `gapfill/GF09_qsv_lossless.md` §1, §3.

### 2.6 Bayer storage (functional)
- **measured** (`functional_tables.md`, PyAV 19, 1080p 12-bit RGGB with seeded noise, all bit-exact, KB/f):

| storage | KB/f |
|---|---|
| rawvideo | 4147 |
| RAW12-packed rawvideo | 3110 |
| RAW12-packed FFV1 range | 2467 |
| mosaic gray16le FFV1 v3 | 2413 |
| mosaic x265 gray12le | 2819 |
| mosaic jpeg2000 | 1839 |
| FFV1 v4 native | 1625 |
| quad FFV1 v3 | 1620 |
| quad jpegls | 1601 |

  The ranking depends on the noise model and the synthetic mosaic (§2.1).
- **measured** (`ffv1_recheck_pyav19.0.2.json`): FFV1 v3 forces the range coder above 8 bits.
  - gray16le at level 3 gives identical bytes for coder=rice and coder=range_tab: quad 1,617,493 / 1,617,493 B; mosaic 2,347,875 / 2,347,875 B.
  - Native bayer_rggb16le at level 4 is not forced: rice 1,629,144 B, range 1,612,245 B, both exact.
- **source** (FFmpeg n9.0.2 `libavcodec/ffv1enc.c:921-927`, re-checked 2026-11-10): `case AV_PIX_FMT_BAYER_RGGB16: ... s->version = FFMAX(s->version, 4); s->bayer = 1;`.
- **source** (same file, lines 652-653): "Version 2 or 4 needed for requested features but version 2 or 4 is experimental and not enabled".
- **source** (RFC 9043 §1): "This document defines versions 0, 1, and 3 of FFV1."
- **background** (`ffv1_v4_cross_version_pyav18.0.0.json`): FFmpeg 8.1.2 cannot open FFV1 v4 Bayer.
- **measured** (`ffv1_v4_cross_version_pyav19.0.2.json`; frame 0 of a 320x240 clip): PyAV 19 decodes CLI-written v4 Bayer.
- **measured** (`bayer_debayer_check_pyav19.0.2.json`, PyAV 19.0.2 + OpenCV 5.0.0):
  - swscale demosaic keeps the CFA samples exactly.
  - OpenCV `BayerBG2BGR*` matches RGGB (43.6-44.25 dB); `BayerRG2BGR*` gives 20.33-20.35 dB.
  - VNG fails on 12-bit.
- **measured** (same file, 1 frame): debayered RGB in FFV1 takes 3,735,615 B at 12-bit. The raw layouts take 2,414,539 B (mosaic) and 1,596,055 B (quad).

### 2.7 Quiet timed bench (run 20261109T230007, PyAV 19.0.2, P-cores only)
**Run record**
- **measured** (`results/BENCH_RUN_2300_LOG.jsonl`): the three items ran 02:30-02:35 (35), 04:19-04:28 (56) and 04:28-04:31 (57). All exited 0.
  - Mean CPU over 10 s before each item: 3.87 / 4.27 / 5.33%.
  - No load flag and no Defender scan event.
  - MsMpEng CPU during the items: 13.14 / 17.92 / 9.22 s.
- **measured** (36 `*_q2300.json`): 36/36 cases are present. Every rep has `packets` 300 and `decode_frames` 300.
- **measured** (12 NVENC files, `nvidia_smi_before/after`): nvidia-smi read `0, 0 %` at the start and end of every GPU case.
  - **inferred:** no other NVENC session was open during the cases; nvidia-smi was not sampled during a case.
- **measured** (each JSON `env`): `av_version` 19.0.2, `ffmpeg_version` 9.0.2, libavcodec 63.1.102, numpy 2.2.6, python 3.12.13.

**Method**
- **code** (`scripts/uncompressed_intra/bench_intra.py:150-164`): the timed window covers frame construction from numpy (`make_frame`, line 153), encode (first `encode()` at line 155), mux to a file on C:, and flush. Each rep opens a new container and encoder (lines 137-164).
- **code** (PyAV 19.0.2 `av/codec/context.py:686`, `self.open(strict=False)` in the encode path): the codec opens lazily on the first `encode()`, so the open is inside the timed window.
- **code** (PyAV 19.0.2 `av/container/output.py:592-612`, `start_encoding`, "Write the file header! Called automatically."): the header write on the first mux is also inside the window.
- **code** (`bench_intra.py:164-166`): the trailer and close are outside the window.
- **code** (`bench_intra.py:173-187`): decode re-reads the file just written with libav's default (software) decoder, using the same `thread_count` as the encode (line 179). So the NVENC rows' "dec fps" is **single-thread CPU decode**, not NVDEC.
- **code** (`bench_intra.py:111-121`): prep is untimed and reported separately. It times `make_frame` + `reformat` + `read_planes` (lines 116-120), so it is the re-layout cost only on paths that have a re-layout function; the native NV12 paths also report about 0.55 ms (h264_nvenc and rawvideo NV12 JSON).
- **measured** (rep JSON): the lossless check is **not** in the timed bench. Exactness comes from §2.3/§2.5 files. NVENC lossless exactness over 300 frames: gap-fill GF09 (§5).

**Hardware-encoded on NVIDIA: NVENC intra (single stream, t1)**
- **measured** (`bench/h264_nvenc_intra_lossless.mkv__nv12_1080p__t1__pyav19.0.2_q2300.json`): h264_nvenc lossless NV12 1080p.
  - Encode: 516 (515-521) fps at 0.045 (0.045-0.055) cores/stream.
  - Size: 593.6 KB/f.
  - Single-thread software decode: 103 (103-103) fps.
- **measured** (`bench/h264_nvenc_intra_lossless.mkv__gray_1080p__...`): h264_nvenc lossless gray 1080p.
  - Encode: 549 (542-551) fps at 0.050 (0.042-0.050) cores/stream.
  - Size: 446.9 KB/f.
  - Decode: 146 fps.
- **measured** (`bench/hevc_nvenc_intra_lossless.mkv__nv12_1080p__...`): hevc_nvenc lossless NV12 1080p.
  - Encode: 302 (298-303) fps at 0.048 (0.045-0.048) cores/stream.
  - Size: 517.7 KB/f.
  - **Decode: 29 (29-29) fps**, single-thread.
- **measured** (`bench/hevc_nvenc_intra_lossless.mkv__p010le_1080p__...`): hevc_nvenc lossless P010 1080p.
  - Encode: 158 (158-159) fps at 0.084 (0.081-0.094) cores/stream.
  - Size: 1,423.4 KB/f (synthetic 2 noise bits, §2.1).
  - Decode: 14 fps.
- **measured** (`bench/hevc_nvenc_intra_lossless.mkv__bayer8_1080p__...`): hevc_nvenc lossless on the Bayer8 mosaic as Y, 1080p.
  - Encode: 186 (185-187) fps at 0.070 (0.066-0.072) cores/stream.
  - Size: 1,369.7 KB/f.
  - Decode: 19 fps.
- **measured** (`bench/hevc_nvenc_intra_cq.mp4__nv12_1080p__...`): hevc_nvenc CQ qp 24, NV12 1080p, lossy.
  - Encode: 459 (459-463) fps at 0.034 cores/stream.
  - Size: 59.2 KB/f.
  - Decode: 111 fps.
  - Functional PSNR plane 0 min: 51.02 dB (`functional_matrix_pyav19.0.2.json`).
  - **This row is at neither target A nor target B.**
  - **source** (FFmpeg n9.0.2, fetched 2026-11-10): `nvenc.c:835-836` `if (avctx->i_quant_factor != 0.0) rc->constQP.qpIntra = av_clip(ctx->cqp * fabs(avctx->i_quant_factor) + avctx->i_quant_offset + 0.5, 0, qmax);`; `options_table.h:151` `i_qfactor` default `-0.8`; `options_table.h:152` `i_qoffset` default `0.0`; `nvenc_hevc.c` defaults contain no `i_qfactor` override. Excerpts also in `results/intra_compare/R/ffmpeg_n9.0.2_knob_excerpts.txt`.
  - **code** (`scripts/uncompressed_intra/functional_matrix.py:85`): this config does not override `i_qfactor`.
  - **arithmetic:** 24 x 0.8 + 0 + 0.5 = 19.7, so the intra frames are coded at QP 19, not 24.
- **measured** (the 6 `..._720p__t1__pyav19.0.2_q2300.json` NVENC files): at 720p (JPEG-derived input), NVENC encodes 332-1,027 fps at 0.017-0.047 cores/stream.
- **measured** (12 NVENC files): per-frame p99 latency is 0.96-7.06 ms.
  - The slowest call per case (`latency_max`; inferred to be the encoder open) has medians of 60.6-83.7 ms.
  - Per rep, that call is 3.6-22.7% of encode wall time (arithmetic over `rep_results`).
  - Its share is largest for 720p NV12 (h264 21.0-22.7%, hevc 13.2-13.4%), so those fps understate steady-state speed the most. The 720p P010 and Bayer8 shares (6.9-8.8%) are smaller than the 1080p h264 shares (10.7-13.1%).
- **measured**: KB/f was identical in all 3 reps for every NVENC case (`stats.bytes_per_frame` min = max). It matches the PyAV 18 files to the KB.

**Outside target, G4 CPU fallback: FFV1 v3 and rawvideo, 1080p**
- **measured** (`bench/ffv1_l3_s{4,24}_crc_g1.mkv__yuyv422_1080p__t{1,0}__...`): FFV1 on camera YUY2.
  - t1: 45 (45-45) fps (s4) and 44 (44-44) fps (s24), at 0.664 and 0.673 cores/stream.
  - t0: 150 (149-151) fps (s4) at 0.672 cores and 241 (234-244) fps (s24) at 0.880 cores.
  - Size: 468.8 / 470.3 KB/f.
  - Decode: 41 fps at t1, 467-475 fps at t0.
- **measured** (same files): the t1 per-frame p99 is 23.77-24.05 ms, under the 33.3 ms frame interval at 30 fps (arithmetic). Measured on one i7-14700K P-core only.
- **measured** (`bench/ffv1_l3_s{4,24}_crc_g1.mkv__nv12_1080p__...`): FFV1 on NV12.
  - t1: 59 / 57 fps at 0.506 / 0.523 cores/stream.
  - t0: 195 (194-196) / 323 (304-326) fps at 0.519 / 0.709 cores/stream.
  - Size: 381.3 / 382.8 KB/f.
- **measured** (`bench/ffv1_l3_s{4,24}_crc_g1.mkv__bayer8_1080p__...`): FFV1 on the Bayer8 mosaic.
  - t1: 55 / 56 fps at 0.539 / 0.533 cores/stream.
  - t0: 176 / 308 fps at 0.539 / 0.719 cores/stream.
  - Size: 1,087.3 / 990.4 KB/f.
- **measured** (`bench/ffv1_l3_s{4,24}_crc_g1.mkv__bayer12_1080p__...`): FFV1 on the Bayer12 mosaic as gray16le, range coder forced (§2.6).
  - **t1: 11 (11-11) / 12 (11-12) fps at 2.633 / 2.587 cores/stream, so one thread cannot hold 30 fps.**
  - p99: 88-91 ms.
  - t0: 41 (s4) / 83 (s24) fps at 2.638 / 3.358 cores/stream.
  - Size: 2,413.3 / 2,349.0 KB/f.
  - Decode: 9 fps at t1, 106 fps at t0.
- **arithmetic** (rows above): at t0, s24 costs 27-37% more CPU per stream than s4 (YUY2 0.880 vs 0.672; NV12 0.709 vs 0.519; Bayer8 0.719 vs 0.539; Bayer12 3.358 vs 2.638). At t1, s4 and s24 are within 4% in fps and within 0.017 cores; s24 is 9% smaller on Bayer8 and within 0.4% on YUY2/NV12.
- **measured** (`bench/rawvideo.nut__{yuyv422,nv12,bayer8,bayer12}_1080p__t{1,0}__...`): rawvideo in NUT encodes 385-974 fps at 0.037-0.086 cores/stream.
  - YUY2: 385 / 500 fps.
  - NV12: 510 / 642 fps.
  - Bayer8: 779 / 974 fps.
  - Bayer12: 391 / 492 fps.
- **measured** (`prep_ms_per_frame`, FFV1 files):
  - YUY2 -> yuv422p de-interleave: 1.415-1.490 ms per 1080p frame.
  - NV12 -> yuv420p: 0.338-0.358 ms.
  - **arithmetic:** 1.49 ms x 30 = 0.045 cores per YUY2 stream, on top of the encoder.

**Corrections the new data force**
- **measured** (tonight vs `bench/ffv1_l3_s24_crc_g1.mkv__{yuyv422,nv12,bayer8}_1080p__t0__pyav18.0.0.json`): tonight's FFV1 s24 t0 rows are slower than or equal to the loaded **PyAV 18** rows:
  - YUY2: 241 (234-244) vs 266 (259-271) fps;
  - NV12: 323 (304-326) vs 326 (321-329);
  - Bayer8: 308 vs 310, at 0.719 vs 0.505 cores/stream.
- **measured** (`bench/ffv1_l3_s24_crc_g1.mkv__yuyv422_1080p__t0__pyav19.0.2.json`, 3x90, `system_cpu_percent_before` 19.8): the loaded **PyAV 19** row for the same config is 226.42 (217.98-234.65) fps, below tonight's 241. For that one config, the same-version loaded row was a lower bound.
- **inferred:** the cross-version comparison changes four things at once: FFmpeg 8.1.2 vs 9.0.2, 28 vs 16 CPUs, 3x90 vs 3x300 frames, and load. The loaded PyAV 18 row (266, 11.8% load before) is also faster than the loaded PyAV 19 row (226), so a version effect fits as well as the CPU count. The causes are not separated.
- Consequence: the rule "every contaminated number is a lower bound on speed" is withdrawn. Contaminated rows are **not reliably lower bounds**, especially across PyAV versions.
- **measured**: every other config re-run tonight that has a PyAV 18 row is faster than it. Two configs (`rawvideo.nut__nv12_1080p` and `ffv1_l3_s4_crc_g1.mkv__nv12_1080p`, 4 of the 36 files) have no PyAV 18 1080p file. Examples:
  - h264_nvenc NV12: 428 -> 516 fps;
  - FFV1 s4 Bayer12 t0: 27 -> 41;
  - rawvideo Bayer12 t1: 287 -> 391.
- **measured** (old PyAV 18 files): earlier hevc_nvenc software decode was 12-24 fps at 1080p (12.45 / 17.11 / 23.87). Tonight it is 29 (NV12), 19 (Bayer8) and 14 (P010) fps. Superseded, not wrong.
- **measured** (old PyAV 18 files): the earlier NVENC 720p range was 327-876 fps. Tonight it is 332-1,027. Superseded, not wrong.
- **measured** (`bench/mjpeg_q2.mkv__yuyv422_1080p__t1__pyav{18.0.0,19.0.2}.json`, `bench/ffv1_l3_s24_crc_g1.mkv__yuyv422_1080p__t0__pyav{18.0.0,19.0.2}.json`): the previous "PyAV 19 vs 18" bullet had the versions reversed.
  - The files give PyAV 18 149 vs PyAV 19 168 fps (mjpeg t1), and PyAV 18 266 vs PyAV 19 226 fps (FFV1 s24 t0).
  - Both runs were loaded, so the bullet is removed. No version speed effect is established.

### 2.8 Background rows not re-run tonight (contaminated, about 50% machine load)
- **measured** (`bench/precheck_typeperf.csv`, `bench/precheck_typeperf_recheck_avgs.txt`): whole-machine CPU was 50.4% before that run and 24.3-52.3% in 5-minute re-checks.
- These speeds are neither clean nor reliably lower bounds (§2.7). Sizes do not depend on load.
- **background** (PyAV 18, 3 reps of 90 frames, except vp9, x265 and jpeg2000 at 3 x 24 (`frames` field); YUY2 1080p, t1 fps / t0 fps / cores at t1 / KB):

| config | t1 fps | t0 fps | t1 cores | KB |
|---|---|---|---|---|
| ffvhuff .nut | 203 | 515 | 0.146 | 1,162.3 |
| utvideo .avi | 99 | 456 | 0.302 | 785.9 |
| magicyuv .avi | 97 | 441 | 0.307 | 794.9 |
| x264 qp0 .mkv | 75 | 385 | 0.380 | 581.2 |
| FFV1 s24 range | 27 | 207 | 1.099 | 370.1 |
| vp9 lossless (3x24) | 11 | 48 | 2.715 | 668.3 |
| x265 lossless (3x24) | 21 | 32 | 11.992 | 702.5 |
| jpeg2000 (3x24) | 7 | 19 | 4.141 | 633.0 |

  Files: `bench/<config>__yuyv422_1080p__t{1,0}__pyav18.0.0.json`.
- **background** (PyAV 18; Bayer12 quad, t1 fps / cores / KB):
  - ffvhuff (3x90): 171 / 0.177 / 1,828.5;
  - FFV1 s24 (3x90): 15 / 2.000 / 1,646.6;
  - jpegls (3x24): 20 / 1.504 / 1,605.5.
  - Files: `bench/{ffvhuff_median.nut,ffv1_l3_s24_crc_g1.mkv,jpegls.nut}__bayer12_quad_1080p__t1__pyav18.0.0.json`.
- **background** (PyAV 19, loaded, 3x90): FFV1 s4 Bayer12 quad gives 16 fps t1 / 53 fps t0 at 1,625.1 KB (`bench/ffv1_l3_s4_crc_g1.mkv__bayer12_quad_1080p__t{1,0}__pyav19.0.2.json`).
- **background** (PyAV 19, loaded, 3x90): FFV1 v4 native Bayer12 (rice) gives 30 fps t1 / 94 fps t0 at 1,632.8 KB (`bench/ffv1_l4_experimental_s4_crc_g1.mkv__bayer12_1080p__t{1,0}__pyav19.0.2.json`).
  - It is not comparable with v3, because the coder differs (§2.6).
- **background** (PyAV 18, 3x90): Bayer8 ffvhuff takes 2,237.9 KB, larger than rawvideo's 2,073.6 KB (`bench/ffvhuff_median.nut__bayer8_1080p__t1__pyav18.0.0.json`).
- **background** (PyAV 18, 3x24): svtav1 lossless NV12 runs at 41 fps and 7.27 cores/stream, 544.7 KB (`bench/libsvtav1_intra_lossless_p12.mkv__nv12_1080p__t1__pyav18.0.0.json`).
- **background:** the Python stills (`bench/py_still__uv.json`) and debayer timings (`bench/debayer__pyav18.0.0_cv4.12.0.json`) are contaminated too and are not quoted here.

### 2.9 JPEG from camera YUV (`python_jpeg_libs_uv.json`; uv env, no PyAV)
- **measured:** simplejpeg 1.9.0 `encode_jpeg_yuv_planes` takes 4:2:2 planes, I420 and Y-only. It rejects interleaved NV12 UV.
- **measured:** PyTurboJPEG 2.6.1 needs libjpeg-turbo >= 3.0, so it is unusable from pip alone.
- **measured:** neither OpenCV 5.0.0 nor 4.12.0 has a .jxl/.avif writer (`python_jpeg_libs_venv.json` for 4.12.0).
- **source** (FFmpeg n9.0.2 `libavcodec/mjpegenc_common.c:499-500`, re-checked 2026-11-10): "Non full-range YUV is non-standard, set strict_std_compliance to at most unofficial to use it."
- **measured** (12-bit Bayer, 1 frame, all exact, synthetic noise; KB):
  - JPEG-LS 2505;
  - J2K reversible 1748;
  - JXL e3 2397;
  - SOF3 2705;
  - PNG 2938.

### 2.10 Codecs PyAV 19 lacks (CLI reference only)
- **CLI reference** (`ffmpeg_cli_reference.json`): these work with the CLI but not with PyAV 19.0.2 (§2.2):
  - libjxl lossless, exact for gray8 and Bayer-as-gray16;
  - libaom allintra lossless, exact (Bayer mosaic 2136 KB);
  - libopenjpeg gray16, exact.
- **CLI reference** (`loose_ends_check.json`): JPEG XL / XS refuse MKV, NUT and MOV.

### 2.11 Chromium playback (shallow; samples from the ffmpeg 9.0.2 CLI)
- **measured** (`chromium_check_electron35.json`, `chromium_check_electron45.json`):
  - Load, draw and seek work in both versions for: VP9 lossless 4:4:4 / 4:2:2; AV1 lossless 4:2:0 / 4:2:2 / 4:4:4 / gray12; H.264 intra and lossless 4:2:0, intra 4:2:2.
  - libx265 all-intra 4:2:0 (Rext; the generator declares `hvc1.1.6.L120.90`, a Main string, `scripts/uncompressed_intra/make_chromium_samples.py:46`) fails in E35 and plays in E45 (intra_playback F16; ffprobe `profile=Rext`, 8/8 frames I, `results/chromium_codecs/gapfill/GF05_ffprobe_hevc_intra_420.txt`).
  - MJPEG, FFV1, rawvideo YUY2 and ProRes fail in both.
  - JPEG XL stills decode in E45 only.
- **measured** (`verify_method/chromium_benched_configs_electron{35,45}.json`):
  - x264 qp0 4:2:2 plays in both.
  - x265 lossless 4:2:2 (Rext) fails in both.
  - x265 lossless 4:2:0 plays in E45 only.
  - svtav1 lossless 4:2:0 MKV plays in both.
- **code** (`scripts/uncompressed_intra/chromium_check/page.html`): the harness keeps only a weighted sum of a 64x36 copy. "Plays" does not mean correct pixels; colour fidelity is NOT VERIFIED.
- **NVENC lossless in Chromium (gap-fill GF09).** Media: the first 60 packets of the 300-frame h264_nvenc and hevc_nvenc lossless NV12 1080p files (PyAV 19.0.2), stream-copied to MKV and MP4; codec strings from the files' avcC/hvcC.
  - **measured** (`gapfill/GF09_chromium_electron{35,45}.json`): in E35 (Chrome 134) and E45 (Chrome 156), h264_nvenc lossless (`avc1.F40028`, High 4:4:4 Predictive) and hevc_nvenc lossless (`hvc1.1.6.L120.90`, Main) play to `ended` in `<video>` from MKV and from MP4, with no media error. Each run reports 60 frames (`totalVideoFrames`, which includes dropped frames; code `page.js:87`).
  - **measured** (same files; load-sensitive, concurrent run; not a performance result): `droppedVideoFrames` was 1 in 2 of 4 HEVC runs (E35 MKV, E45 MP4) and 0 in all H.264 runs.
  - **measured** (same files): seeked frames 0, 1 and 7, read back with `VideoFrame.copyTo`, are bit-exact YUV (Y, U, V max abs diff 0) in both versions. WebCodecs frames 0, 1 and 7 are also exact.
  - **measured** (same files; this RTX 3070, driver 610.88): H.264 lossless decodes in software (FFmpegVideoDecoder, `kIsPlatformVideoDecoder` false); WebCodecs `prefer-hardware` fails with "OperationError: Unsupported configuration".
  - **measured** (same files; this RTX 3070, driver 610.88): HEVC lossless decodes in hardware (D3D11VideoDecoder, `kIsPlatformVideoDecoder` true); WebCodecs `prefer-software` fails with "Unsupported configuration".
  - Chromium decoder choice on other GPUs (including Intel): NOT VERIFIED.
  - **measured** (same files): in E35, `canPlayType('video/x-matroska...')` returns "" but the MKV files play from `src`.
  - **measured** (`gapfill/GF09_chromium_media_check.json`): PyAV decodes frames 0, 1 and 7 of all four cuts exactly, so the test media themselves are exact.
  - **code** (`scripts/uncompressed_intra/gapfill/GF09/chromium/page.js`, `compareFrame`): readback compares decoded YUV only; canvas (RGB) output was not checked.
  - Gray, Bayer and P010 lossless files in Chromium: NOT VERIFIED (only NV12 1080p was played).
- **inferred:** Bayer streams display as a grey mosaic; colour needs a WebGL demosaic.

## 3. Comparison tables

### 3.1 Hardware-encoded on NVIDIA: NVENC intra, single stream, t1 (measured, run 20261109T230007)
File = `bench/<stem>__t1__pyav19.0.2_q2300.json`. "dec" = single-thread libav software decode. MB/s @30 is arithmetic. "exact (matrix)" = `functional_matrix_pyav19.0.2.json`, 4 frames at 1080p; "exact (step2)" = `verify_method/exact_check_step2_pyav19.0.2.json`, 4 frames. The 10 lossless rows were also re-encoded with the same config and found exact over 300 frames (GF09, §5). P010 sizes and speeds include 2 synthetic noise bits; Bayer8 is synthetic (§2.1). cores/stream for NVENC is approximate (§5).

| stem | exact? (PyAV 19 functional) | KB/f | MB/s @30 | enc fps | cores/stream | p99 ms | dec fps |
|---|---|---|---|---|---|---|---|
| h264_nvenc_intra_lossless.mkv__nv12_1080p | yes (matrix) | 593.6 | 17.8 | 516 (515-521) | 0.045 (0.045-0.055) | 1.98 | 103 |
| h264_nvenc_intra_lossless.mkv__gray_1080p | yes (matrix) | 446.9 | 13.4 | 549 (542-551) | 0.050 (0.042-0.050) | 1.88 | 146 |
| hevc_nvenc_intra_lossless.mkv__nv12_1080p | yes (matrix) | 517.7 | 15.5 | 302 (298-303) | 0.048 (0.045-0.048) | 3.48 | 29 |
| hevc_nvenc_intra_lossless.mkv__p010le_1080p | yes (matrix) | 1,423.4 | 42.7 | 158 (158-159) | 0.084 (0.081-0.094) | 7.06 | 14 |
| hevc_nvenc_intra_lossless.mkv__bayer8_1080p | yes (matrix; mosaic as Y) | 1,369.7 | 41.1 | 186 (185-187) | 0.070 (0.066-0.072) | 5.95 | 19 |
| hevc_nvenc_intra_cq.mp4__nv12_1080p | lossy (51.02 dB min; neither A nor B) | 59.2 | 1.8 | 459 (459-463) | 0.034 (0.025-0.044) | 2.26 | 111 |
| h264_nvenc_intra_lossless.mkv__nv12_720p | yes (step2) | 202.5 | 6.1 | 985 (983-1,061) | 0.023 | 0.99 | 296 |
| h264_nvenc_intra_lossless.mkv__gray_720p | yes (step2) | 173.4 | 5.2 | 1,027 (1,019-1,030) | 0.027 | 0.96 | 353 |
| hevc_nvenc_intra_lossless.mkv__nv12_720p | yes (step2) | 213.1 | 6.4 | 660 (654-663) | 0.028 | 1.62 | 73 |
| hevc_nvenc_intra_lossless.mkv__p010le_720p | yes (step2) | 622.3 | 18.7 | 332 (332-334) | 0.047 | 3.24 | 33 |
| hevc_nvenc_intra_lossless.mkv__bayer8_720p | yes (step2) | 559.5 | 16.8 | 381 (381-383) | 0.036 | 3.21 | 53 |
| hevc_nvenc_intra_cq.mp4__nv12_720p | lossy, not checked | 20.9 | 0.6 | 878 (861-935) | 0.017 (0.009-0.022) | 1.13 | 281 |

### 3.2 Outside target (G4 CPU fallback): FFV1 v3 and rawvideo, 1080p (measured, run 20261109T230007)
File = `bench/<stem>__t{1,0}__pyav19.0.2_q2300.json`. Bayer rows are synthetic; Bayer12 sizes are noise-dominated (§2.1).

| stem | exact? | KB/f | MB/s @30 | t1 fps | t1 cores | t0 fps | t0 cores | dec t1 / t0 |
|---|---|---|---|---|---|---|---|---|
| rawvideo.nut__yuyv422_1080p | yes (matrix) | 4,147.2 | 124.4 | 385 (382-388) | 0.077 | 500 (500-503) | 0.084 | 806 / 825 |
| ffv1_l3_s4_crc_g1.mkv__yuyv422_1080p | yes (matrix) | 468.8 | 14.1 | 45 (45-45) | 0.664 | 150 (149-151) | 0.672 | 41 / 475 |
| ffv1_l3_s24_crc_g1.mkv__yuyv422_1080p | yes (`ffv1_recheck`, 8 frames) | 470.3 | 14.1 | 44 (44-44) | 0.673 | 241 (234-244) | 0.880 | 41 / 467 |
| rawvideo.nut__nv12_1080p | yes (matrix) | 3,110.4 | 93.3 | 510 (506-514) | 0.059 | 642 (640-653) | 0.058 | 1,069 / 1,068 |
| ffv1_l3_s4_crc_g1.mkv__nv12_1080p | yes (matrix) | 381.3 | 11.4 | 59 (58-59) | 0.506 | 195 (194-196) | 0.519 | 52 / 593 |
| ffv1_l3_s24_crc_g1.mkv__nv12_1080p | yes (step2, 4 frames) | 382.8 | 11.5 | 57 (56-57) | 0.523 | 323 (304-326) | 0.709 | 52 / 582 |
| rawvideo.nut__bayer8_1080p | yes (matrix) | 2,073.6 | 62.2 | 779 (767-784) | 0.037 | 974 (964-985) | 0.042 | 1,578 / 1,572 |
| ffv1_l3_s4_crc_g1.mkv__bayer8_1080p | yes (matrix) | 1,087.3 | 32.6 | 55 (55-55) | 0.539 | 176 (176-177) | 0.539 | 42 / 491 |
| ffv1_l3_s24_crc_g1.mkv__bayer8_1080p | yes (step2, 4 frames) | 990.4 | 29.7 | 56 (56-56) | 0.533 | 308 (301-310) | 0.719 | 42 / 489 |
| rawvideo.nut__bayer12_1080p | yes (matrix) | 4,147.2 | 124.4 | 391 (387-391) | 0.075 | 492 (482-498) | 0.086 | 819 / 788 |
| ffv1_l3_s4_crc_g1.mkv__bayer12_1080p | yes (matrix) | 2,413.3 | 72.4 | 11 (11-11) | 2.633 | 41 (41-41) | 2.638 | 9 / 106 |
| ffv1_l3_s24_crc_g1.mkv__bayer12_1080p | yes (`ffv1_recheck`, 1 frame) | 2,349.0 | 70.5 | 12 (11-12) | 2.587 | 83 (83-83) | 3.358 | 9 / 106 |

### 3.3 Size ratio against rawvideo, 1080p (arithmetic from §3.1, §3.2 and §2.5)

| source | hardware-encoded on NVIDIA (NVENC lossless) | outside target (FFV1 v3) |
|---|---|---|
| NV12 (raw 3,110.4 KB) | h264 5.2x, hevc 6.0x | s4 8.2x, s24 8.1x |
| Bayer8 mosaic (raw 2,073.6 KB; synthetic) | hevc 1.51x | s24 2.09x, s4 1.91x |
| Bayer8 quad (functional, 4 frames; synthetic) | hevc 3.0x (681,534 B), h264 2.7x (767,200 B) | not timed |
| YUY2 4:2:2 | **no exact NVENC path on Ampere** | 8.8x |
| Bayer12 | **no exact compressing NVENC path** (12-bit truncated to 10 bits by source; packed bytes larger than raw) | 1.7-1.8x (mosaic, noise-dominated) |

### 3.4 Version bumps

| bump | adds for G4 |
|---|---|
| PyAV 18.0.0 -> 19.0.2 | Experimental FFV1 v4 Bayer, which FFmpeg 8.1.2 cannot read. NVENC 12-bit pix_fmts listed, but truncated to 10 bits (source, nvenc.c:58,63,67). No libjxl, libaom or openjpeg. Sizes are identical; no version speed effect is established (§2.7) |
| OpenCV 4.12.0 -> 5.0.0.93 | Nothing: same debayer results, no JXL/AVIF writer |
| Electron 35.7.5 -> 45.2.3 | libx265 Rext 4:2:0 playback (HEVC Main, including NVENC HEVC lossless, already plays in E35; §2.11) and JPEG XL stills. Still no FFV1, MJPEG, rawvideo or ProRes |
| + imagecodecs 2026.10.10 | JXL, SOF3 12-bit, JPEG-LS and J2K from pip on Windows |

## 4. Implications for the plan (inferred, tied to the findings)
1. **NV12 and 8-bit gray cameras, hardware-encoded on NVIDIA: NVENC lossless intra in MKV** (§2.5, §2.7, §3.1).
   - h264_nvenc lossless is exact, needs 0.045-0.050 host cores per 1080p30 stream and 13.4-17.8 MB/s, and decodes in software at 103-146 fps on one thread.
   - hevc_nvenc lossless is about 13% smaller, but its single-thread software decode is 29 fps at 1080p, below a 30 fps camera.
   - h264_nvenc lossless is coded High 4:4:4 Predictive; hevc_nvenc lossless is Main / Main 10 (§2.5).
   - **measured** (`gapfill/GF09_rows_nvenc_pyav19.0.2.json`): NVDEC via `h264_cuvid` / `hevc_cuvid` and the `cuda` hwaccel decode both NVENC lossless formats exactly (300/300 frames, every case).
   - **measured** (same file): the cuda and d3d11va rows have PyAV `is_hwaccel=True` and return nv12/p010le frames; GPU use was not checked with nvidia-smi (`gapfill/GF09_qsv_lossless.md` §2).
   - **measured** (same file; this RTX 3070, driver 610.88): the `d3d11va` hwaccel rejects H.264 High 4:4:4 Predictive ("Invalid data found when processing input") and decodes HEVC lossless exactly. Other GPUs, including Intel D3D11VA: NOT VERIFIED.
   - **measured** (`gapfill/GF09_chromium_electron{35,45}.json`; this RTX 3070, driver 610.88): Chromium plays both with exact YUV readback on 3 seeked frames, H.264 lossless in software and HEVC lossless in hardware (§2.11).
   - Decode **speed** (hardware or threaded) is still not measured, so **the H.264 vs HEVC choice is still open on speed**.
   - **inferred:** this path is outside the hardware target, because QSV has no lossless mode (header, §2.5). It is NVIDIA-only.
2. **8-bit Bayer, hardware-encoded on NVIDIA: split the mosaic into four quarter planes before NVENC lossless** (§2.5, §3.3).
   - Measured functionally at 681,534 B (hevc) vs 1,368,828 B for the mosaic.
   - The source is synthetic Bayer from ISP 4:2:2 (§2.1); the real-sensor quad gain is NOT VERIFIED.
   - Its speed was not timed (§6). The mosaic path is timed: 186 fps, 0.070 cores/stream.
3. **YUY2 (4:2:2) cameras: no exact hardware-encoded recorder on RTX 3000** (§2.5).
   - The refusal comes from the GPU capability query (inferred from code, §2.5); NVENC 4:2:2 starts at Blackwell (cross-reference hw_accel_target N2).
   - YUY2 -> NV12 discards chroma, so it is lossy.
   - Options:
     - matched-quality lossy intra at target A from `results/intra_compare/`;
     - QSV hevc 4:2:2 Rext (lossy, §2.5);
     - the CPU fallback (item 5).
   - Storing 4:2:2 exactly through NVENC 4:4:4 lossless with duplicated chroma is an untested idea (NOT VERIFIED).
4. **12-bit Bayer, P010 and gray16: only P010 has an exact hardware-encoded path** (hevc_nvenc lossless, 1,423.4 KB, 158 fps; §3.1).
   - Those P010 numbers include 2 synthetic noise bits per sample (§2.1); real-sensor size and speed are NOT VERIFIED.
   - Bayer12 and gray16 have no exact NVENC path: FFmpeg truncates 12-bit NVENC input to 10 bits (source, §2.5), and packed 12-bit bytes do not compress. They need the CPU fallback.
5. **CPU fallback (outside target): FFV1 v3, level 3, gop 1, slicecrc 1, in MKV** for YUY2/NV12/Bayer8, with threads on (§3.2).
   - YUY2 1080p needs about 0.67 cores per stream plus 0.045 for the de-interleave.
   - One thread runs 44-45 fps with p99 under 33 ms **on one i7-14700K P-core**; other CPUs (E-cores, laptops, older parts) are NOT VERIFIED, and the margin over 30 fps is only 1.47-1.49x (arithmetic).
   - With threads, **4 slices is the cheaper choice per stream** (0.52-0.67 cores at 8-bit, 2.64 at 12-bit; 150-195 fps at 8-bit). 24 slices is faster per stream (241-323 fps at 8-bit) but costs 27-37% more CPU; use it where single-stream speed matters.
   - At t1, s4 and s24 are within 4%; s24 is 9% smaller on Bayer8.
   - Size varies at least 1.6x with the scene (§2.1).
6. **Bayer12 on CPU is expensive.**
   - FFV1 v3 needs 2.6-3.4 cores per 1080p30 stream and cannot hold 30 fps on one thread (§2.7).
   - Before choosing, compare quad ffvhuff (background 0.18 cores, +11% size) and FFV1 v4 (experimental, unreadable by FFmpeg 8.1.2) on real raw frames (§2.6, §2.8).
7. **Rawvideo** in NUT costs 0.04-0.09 cores but 62-124 MB/s per 1080p30 stream (§3.2).
   - Disk bandwidth, not CPU, sets the camera count. Multi-stream write was not tested here; see `results/write_throughput/`.
8. **Containers** (§2.4):
   - use MKV for YUY2/NV12/gray8 and NVENC output; it is the only container with no silently corrupted cut frame in 275 cases;
   - NUT is needed for Bayer/gray16 rawvideo, but NUT and AVI returned a silently corrupted last frame in 18 of 275 cut cases (jpegls, ffvhuff, magicyuv, FFV1-in-AVI);
   - never use MOV/MP4 for crash-tolerant recording (0 frames after truncation, including NVENC CQ MP4);
   - readers must validate the last frame, especially for NUT/AVI.
9. **Multi-camera NVENC lossless is capped at 12 sessions** (measured with lossy settings in `results/intra_compare/BENCH.md`, BENCH_RUN_2300_SUMMARY §3; NOT VERIFIED for lossless). A 16-camera NVENC-only plan does not fit on one RTX 3070.
10. **G8:** NVENC lossless H.264/HEVC NV12 1080p now has verified YUV readback in Chromium E35/E45 (§2.11, GF09; 3 frames per file, YUV only). FFV1, rawvideo and Bayer still do not play, and gray/P010 lossless and canvas RGB fidelity are NOT VERIFIED. For those, keep a playback proxy or backend-decoded frames for the UI.
11. **No version bump is needed for G4** (§3.4).

## 5. Run flags and caveats that apply to this topic
- **P-cores only.** The runner requested a 16-logical-CPU P-core mask for every item (`results/BENCH_RUN_2300_LOG.jsonl` `affinity: pcores`; code `run_queue.py:441-443`). This topic's JSON records no actual process affinity. The JSON field `cpu_logical: 28` is `psutil.cpu_count()` and ignores affinity.
  - t0 rows depend on the thread count libav auto-selected, which is not recorded.
  - Why the FFV1 s24 t0 rows did not beat the loaded PyAV 18 rows is not known: FFmpeg version, CPU count, frame count and load are confounded (inferred, §2.7).
- **The libx265 affinity widening (flag 2) does not apply (inferred).** No libx265 case ran in items 35, 56 or 57, and each case runs as its own process. Affinity was not measured per case.
- **No lossless check inside the timed bench; the NVENC lossless configs were re-checked afterwards (gap-fill GF09).**
  - **measured** (`gapfill/GF09_rows_nvenc_pyav19.0.2.json`): all ten timed NVENC lossless configs of item 35 (5 at 1080p, 5 at 720p) were re-encoded with the bench's own config entries (`functional_matrix.py:83-84`; gop 1 is the `cfg()` default at `:53`), the bench's path chooser (called as in `bench_intra.py:108`) and t1. The re-encodes are bit-exact over all 300 frames (software, cuvid and cuda decode), and their KB/frame equals the timed JSON's to the byte.
  - **measured** (same file): Bayer8 quad (not timed) is also exact over 300 frames: h264_nvenc 772.6 KB/frame, hevc_nvenc 685.1 KB/frame.
  - **inferred** (same config entries, path chooser and t1; KB/frame equal to the byte; the timed streams themselves were deleted): the HANDOFF §5 flag "uncompressed_intra has no lossless check in the timed bench" is closed for the NVENC lossless rows.
  - The FFV1 and rawvideo timed streams were not re-checked over 300 frames. Their exactness is cited from functional files with 4 frames (matrix; step2 check), 8 frames (`ffv1_recheck` YUY2) or 1 frame (`ffv1_recheck` gray16le). FFV1 s24 on NV12 and Bayer8 (1080p) is exact over 4 frames (`verify_method/exact_check_step2_pyav19.0.2.json`).
  - The 720p and 1080p hevc CQ rows are lossy and unchecked.
- **The encoder open and header write are inside the timed window** (code PyAV 19.0.2 `context.py:686`, `output.py:592-612`; bench window `bench_intra.py:150-164`). The slowest call is 3.6-22.7% of NVENC rep wall time (arithmetic) and at most 1.7% for the CPU rows. NVENC fps, especially 720p NV12, understate steady state.
- **CPU timer granularity and NVENC CPU spread.**
  - **measured:** all 108 rep `encode_cpu_s` readings are whole multiples of 15.625 ms.
  - **measured:** NVENC reps register 6-60 ticks, and the rep-to-rep spread is far wider than ±1 tick: up to 2.3x in ticks (hevc CQ 720p 11 / 6 / 14; hevc CQ 1080p 16 / 28 / 22; h264 NV12 1080p 29 / 35 / 29).
  - **inferred:** process CPU time sums several quantised threads, including driver threads. Treat NVENC cores/stream as approximate: medians 0.017-0.084, reps 0.009-0.094.
  - The CPU codec rows are resolved far better.
- **NVENC session cap** (BENCH_RUN_2300_SUMMARY §3 item 3): a 13th NVENC session fails to open. This bench is single-stream, so the cap does not affect its numbers, but it limits the plan (§4.9).
- **Defender ON.** MsMpEng used 9.22-17.92 CPU-seconds per item (log).
  - **inferred:** the large folder-of-files cost seen in `results/write_throughput/` is unlikely to be the same here, because the bench writes one file per rep and deletes it (code `bench_intra.py:188`). Rawvideo reps still write and delete about 1.24 GB each (arithmetic, 300 x 4.15 MB).
  - Each rep closes the MKV and reopens it at once to decode (code `bench_intra.py:164-176`), so any scan on close falls in the untimed close and any scan on open falls in the **timed decode** window.
  - Defender's share of encode and decode times is not separated.
- **Warm caches.** There are 8 unique frames, and decode reads the file just written.
  - **inferred:** rawvideo encode and all decode figures measure memory and page cache, not disk.
- **Single camera content** (C930e). Every non-YUY2 source is derived, 720p is JPEG-derived, Bayer is synthetic, and every >8-bit source carries synthetic low-bit noise (P010/RAW10 2 bits, 12-bit/gray16 4 bits; §2.1).
- **One CPU, one NVIDIA GPU.** All CPU numbers are from one i7-14700K P-core cluster; all NVENC/NVDEC/D3D11VA/Chromium decoder results are from one RTX 3070 (driver 610.88). Other CPUs and GPUs in the hardware target are NOT VERIFIED.
- **Chromium dropped-frame counts (§2.11)** come from real-time playback while other agents ran; they are load-sensitive and are not a performance result.
- **Not all of the earlier method fixes were applied.** The open is still timed; reps are under 10 s for every case except Bayer12 t1; t1 is not pinned to one core; only one camera's YUY2 is used.
- **Flags that do not apply here:**
  - nvJPEG target-A miss (no JPEG in this topic);
  - WebCodecs scrub errors and `<video>` N=8 stalls (playback topics);
  - higher per-write latencies (write_throughput).
- **`bench/bench_summary.md` mixes 183 rows.** Tonight's rows are the PyAV 19.0.2 rows with 3x300. Do not quote the 3x90/3x24 or PyAV 18 rows as quiet numbers (`BENCH.md` §2).

## 6. Not tested / limits / NOT VERIFIED
- Exactness of the full 300-frame FFV1/rawvideo timed streams (functional checks use 1-8 frames). The NVENC lossless configs are exact over 300 frames in same-config re-encodes (GF09; link to the deleted timed streams inferred, §5).
- Timing not measured for:
  - NVENC lossless on Bayer8 quad, raw10/12-packed and RGB;
  - h264_nvenc on Bayer8;
  - FFV1 quad Bayer (quiet run).
- These configs have only contaminated background numbers (§2.8): ffvhuff, utvideo, magicyuv, x264 qp0, FFV1 range coder, FFV1 v4, jpegls, jpeg2000, vp9, x265, svtav1, dnxhr, prores, every 720p CPU row, the Python stills and debayer.
- VERIFY_method repro 1 (earlier pass) is half answered.
  - Rice t1 now meets its expectation: 44-45 fps, 0.66-0.67 cores.
  - The range coder (8-bit, -21% size) was not re-run, so whether range holds 30 fps at t1 is NOT VERIFIED.
- VERIFY_method repro 2 (FFV1 v4 vs v3: coder or Bayer transform) is still open.
- Lossless intra on QSV: **answered, not available** (GF09; measured on the UHD 770 only, other Intel generations NOT VERIFIED). Lossless on AMF (no AMD GPU) and VideoToolbox: NOT VERIFIED.
  - HEVC lossless on RTX 3000 SKUs other than this RTX 3070: NOT VERIFIED.
- Hardware or multi-threaded decode **speed** of NVENC lossless files: not measured. "dec fps" is single-thread CPU decode.
- Hardware decode **correctness** is measured on this RTX 3070 (driver 610.88) only: cuvid exact for both; cuda/d3d11va rows have PyAV `is_hwaccel=True` and return nv12/p010le frames, GPU use not checked with nvidia-smi; D3D11VA rejects H.264 Hi444PP and is exact for HEVC. Other GPUs, including Intel D3D11VA: NOT VERIFIED.
- Chromium NVENC lossless: answered for NV12 1080p in E35/E45 on this RTX 3070 (GF09: plays, exact YUV for 3 seeked frames per file). Gray, Bayer and P010 lossless in Chromium, canvas RGB fidelity, and decoder choice on other GPUs: NOT VERIFIED.
- AV1 lossless on Quick Sync (lead only, NOT VERIFIED):
  - **source** (oneVPL `mfxstructures.h` v2.15.0:918, URL in the header, accessed 2026-11-10): "In av1 design, valid range is 0 to 255 inclusive, and if QPI=QPP=QPB=0, the encoder is in lossless mode."
  - **code** (FFmpeg n9.0.2 `qsvenc.c:925-927`): AV1 QP is clipped to 8 bits (`av_clip_uintp2(..., 8)`), so QP 0 passes through.
  - **measured** (`qsv_recheck_pyav19.0.2.json`): av1_qsv does not open on the UHD 770 ("Function not implemented").
  - **cross-reference** (`results/hw_accel_target/FINDINGS.md` N2; summary line "AV1 fails on RTX 3000"): RTX 3000 has no AV1 encode.
  - **inferred:** AV1 lossless is outside the RTX 3000 + Intel intersection anyway. Arc / Meteor Lake AV1 lossless: NOT VERIFIED (no hardware).
- 4:2:2 via NVENC 4:4:4 with duplicated chroma: NOT VERIFIED.
- Real Bayer sensor statistics and real 10/12-bit noise: NOT VERIFIED (12-bit sizes are 48-69% synthetic noise; P010/RAW10 noise share not measured; Bayer8 from ISP 4:2:2).
- CPU results on other CPUs (E-cores, laptops, pre-2023 parts): NOT VERIFIED.
- Run-to-run variation of the timed numbers: not measured (one run).
- No multi-stream, 60 fps, long-recording or writer-kill test in this topic.
- Steady-state throughput without the encoder open was not measured.
- Defender's share of encode/decode times: not separated.
- **Answered by source (no longer open):** `yuv444p12msble` (and every 12-bit input) into NVENC is truncated to 10 bits in FFmpeg n9.0.2 (nvenc.c:58,63,67,68).
- The CLI-reference evidence is supporting only.
- Licensing (G7) is in `results/licensing/`.
- `NOTES.md` is superseded where it conflicts with this file.

## 7. How to reproduce
From the repo root, with `S=research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra`.

Quiet timed bench, exactly as run (only on an idle machine; the runner pins to the P-cores):
```
uv run --script research/skellycam_recording/recording_upgrade/scripts/bench_runner/run_queue.py --only UI-GPU-AV19,UI-BAYER-AV19,UI-CORE-AV19,UI-SUM --deadline HH:MM
```
The underlying commands (from `results/bench_queue_2300.json`; defaults 300 frames, 3 reps, 20 warm-up frames):
```
uv run --script $S/bench_suite.py --interp uv --tag _q2300 --group gpu
uv run --script $S/bench_suite.py --interp uv --tag _q2300 --group bayer --sources bayer12,bayer8 --configs rawvideo.nut,ffv1_l3_s4_crc_g1.mkv,ffv1_l3_s24_crc_g1.mkv
uv run --script $S/bench_suite.py --interp uv --tag _q2300 --group core_1080p --sources yuyv422,nv12 --configs rawvideo.nut,ffv1_l3_s4_crc_g1.mkv,ffv1_l3_s24_crc_g1.mkv
uv run --script $S/bench_summary.py
```
- Logs: `results/bench_runner/logs/20261109T230007/{35,56,57,58}_*.{out,err}.txt`.
- Load record: `results/BENCH_RUN_2300_LOG.jsonl`.
- Tables: `BENCH.md`.

PyAV 19.0.2 functional evidence (no timing):
```
uv run --script $S/probe_pyav_caps.py
uv run --script $S/pyav_mux_acceptance.py
uv run --script $S/functional_matrix.py ; .venv/Scripts/python.exe $S/summarize_functional.py
uv run --script $S/ffv1_v4_cross_version.py
uv run --script $S/qsv_recheck.py
uv run --script $S/ffv1_pyav19_recheck.py
uv run --script $S/bayer_debayer_check_pyav19.py
uv run --script $S/python_jpeg_libs.py --turbojpeg-dll "C:/Program Files/Audacity/turbojpeg.dll"
```
- Gap-fill GF09 (QSV lossless rows, NVENC 300-frame exactness, Chromium NVENC lossless): scripts under `$S/gapfill/GF09/` (e.g. `gf09_lossless_check.py`, `chromium/prep_chromium.py`, `chromium/page.js`); outputs in `gapfill/GF09_*`; write-up `gapfill/GF09_qsv_lossless.md`.
- Step-2 verifier checks (exactness of s24 NV12/Bayer8 and 720p NVENC; NVENC lossless profiles): outputs `verify_method/exact_check_step2_pyav19.0.2.json` and `verify_method/nvenc_lossless_profile_step2_pyav19.0.2.json`; scripts in the session scratchpad (`.../scratchpad/step2/ui_vm/`, not in the repo).
- FFmpeg n9.0.2 sources used above: `https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/<path>`, fetched 2026-11-10 (copies in `.../scratchpad/step2/uintra_prov/` and, for qsvenc*, the step3 scratchpad).

Background (PyAV 18.0.0 venv), CLI reference and Chromium:
```
.venv/Scripts/python.exe $S/functional_matrix.py ; .venv/Scripts/python.exe $S/ffmpeg_cli_reference.py
bash $S/verify_method/cli_checks.sh
.venv/Scripts/python.exe $S/make_chromium_samples.py
env -u ELECTRON_RUN_AS_NODE skellycam-ui/node_modules/electron/dist/electron.exe $S/chromium_check/main.js <media>/chromium_samples/manifest.json <results>/chromium_check_electron35.json   (repeat with Electron 45.2.3)
```
- The contaminated bench command lines are in `bench/run_{core1080_yuyv,core1080_nv12,bayer,core720,gpu,pyav19}.log`.

Versions:
- av 19.0.2 (FFmpeg 9.0.2, libavcodec 63.1.102), numpy 2.2.6, Python 3.12.13, uv 0.11.8;
- simplejpeg 1.9.0, imagecodecs 2026.10.10, opencv-python 5.0.0.93;
- background: PyAV 18.0.0 / OpenCV 4.12.0;
- ffmpeg 9.0.2 gyan build;
- Electron 35.7.5 / 45.2.3;
- NVIDIA driver 610.88; Intel UHD 770 driver 32.0.101.7088.

## Verification (2026-11-10)
**What the verifiers checked** (`VERIFY_provenance.md`, `VERIFY_method.md`; previous passes renamed `*.prev.md`):
- All 36 quiet-run JSON files: about 260 numeric claims, every row of §3.1-§3.3, the run record, tick counts and open shares. All matched after rounding.
- The old PyAV 18 and loaded PyAV 19 rows behind every §2.7 correction.
- All 555 rows of `functional_matrix_pyav19.0.2.json` (including `trunc50_*` for all 15 sources) and the other functional files.
- FFmpeg n9.0.2 sources (matroskaenc.c, nvenc.c, nvenc.h, nvenc_hevc.c, ffv1enc.c, mjpegenc_common.c, options_table.h), RFC 9043 and PyAV 19.0.2 `output.py` / `context.py`, re-fetched; every quote matched.
- Two new functional checks (PyAV 19.0.2, no timing): exactness of FFV1 s24 NV12/Bayer8 and the 720p NVENC lossless rows; NVENC lossless coded profiles.

**Checked again by the reviser before applying:**
- Recounted the truncation cases from the JSON: 275 exact lossless MKV/NUT/AVI cases, 18 with frames decoded > frames exact, none in MKV; `rawvideo.avi` 0 frames on both Bayer sources.
- Re-read nvenc.c: the "Truncated to 10bits" entries are at lines 58 (P012), 59 (P016), 63 (P212), 67 (YUV444P12MSB) and 68 (YUV444P16). The provenance report gave 57/62/66/67, one line low; this file uses the re-counted numbers. nv16 under `NVENC_HAVE_422_SUPPORT` at 60-61, macro at nvenc.h:69, capability query at 445-446, i_qfactor at 835-836, defaults at options_table.h:151-152.
- Re-read `bench_intra.py` (make_frame 153, encode 155, window end 164, decode thread_count 179, unlink 188), PyAV 19.0.2 `context.py:686` and `output.py:592`, and the `uintra_frames.py` docstring (gray16 17-18, P010 19, Bayer8 21, RAW10 25).
- Confirmed the loaded PyAV 19 s24 row (226.42, 217.98-234.65, 19.8% before), the PyAV 18 row (266.39, 11.8%), the NVENC tick counts, the missing PyAV 18 NV12 1080p files, `raw_bytes.bayer12_packed_raw12` = 3,110,400, and the 3x24 frame counts of the background rows.
- Opened both new `verify_method/*_step2_*.json` files; contents match the verifiers' description.

**What was changed:**
- R1: truncation bullet rewritten (18 of 275 NUT/AVI cases silently corrupted, including FFV1 in AVI; none in MKV; rawvideo.avi 0 frames on both Bayer sources); §4.8 updated.
- R2: the 12-bit NVENC question is answered by source (truncated to 10 bits); removed from NOT VERIFIED; §3.3 and §3.4 updated.
- M1/W1: the "not lower bounds" correction now gives both comparisons (slower than loaded PyAV 18, faster than loaded PyAV 19) and states the confounds; "affinity probably explains it" removed.
- W2, W3, W6/M11, W7, W8, W10/M10, W11/M9: scope, wording, labels and citations fixed (configs with a PyAV 18 row; "superseded"; nvidia-smi as start/end snapshots; PyAV lazy open and header write; raw12 size from a PyAV 19 file; affinity and Defender relabelled inferred, with the decode-window caveat).
- W4, W5: hw_accel_target quotes marked cross-reference; code chain for the 4:2:2 refusal cited and the conclusion labelled inferred; i_qfactor cited to FFmpeg code (intra QP 19 by arithmetic).
- W9/M7, M6: noise caveat extended to P010, RAW10 and gray16; synthetic-Bayer caveat added to §4.2.
- M2/W12: §4.5 now recommends s4 with threads as cheaper per stream, s24 for single-stream speed (+27-37% CPU).
- M3: NVENC lossless profiles added; H.264 vs HEVC choice left open.
- M4: hardware-target label narrowed to "hardware-encoded on NVIDIA"; QSV leg NOT VERIFIED.
- M5: NVENC CPU spread reported as observed (up to 2.3x in ticks); figures called approximate.
- M8: single-thread FFV1 claim qualified to one i7-14700K P-core.
- M12: within-run spread note added to Units.
- Exactness of FFV1 s24 NV12/Bayer8 and the five 720p NVENC lossless rows moved from NOT VERIFIED to exact (4 frames).
- Minor: machine line cited; background frame counts stated; mjpegenc lines 499-500; prep caveat; 720p open-share qualifier; JPEG XL stills in E45.

**Step 3 gap-fill (2026-11-10)**

Evidence opened by the reviser before applying: `gapfill/GF09_qsv_lossless.md`, `GF09_rows_qsv_pyav19.0.2.json` (33 rows: 32 ok, 1 send failure, 0 exact; QPI/VDENC/MinQPI from `libav_param_dump`), `GF09_rows_nvenc_pyav19.0.2.json` (12 rows, all 300/300 exact for sw/cuvid/cuda; d3d11va fails on all 5 H.264 rows; KB/frame equal to §3.1), `GF09_chromium_electron{35,45}.json`, `GF09_chromium_media_check.json`, `GF09_avoptions_pyav19.0.2.json`, `GF09_gpu_drivers.json`, `scripts/uncompressed_intra/gapfill/GF09/chromium/page.js` (`compareFrame`), the FFmpeg n9.0.2 and oneVPL v2.15.0 copies in the step3 scratchpad (`qsvenc.c:925-931`, `qsvenc_h264.c:152-156, 202`, "lossless" count 0, `mfxstructures.h:913, 918`), `functional_matrix.py:53, 83-84`, `bench_intra.py:108`; for GF05, `results/chromium_codecs/gapfill/GF05_ffprobe_hevc_intra_420.txt`, `GF05_g8_g9_doc_fixes.md` §5, `make_chromium_samples.py:46` and `VERIFY_method.prev.md:28`.

What changed and why:
- GF05, §2.11: "HEVC intra 4:2:0 (Main)" replaced by libx265 all-intra 4:2:0 (Rext). ffprobe gives `profile=Rext`, 8/8 frames I; only the generator's declared codec string says Main. The "Main" claim came from `VERIFY_method.prev.md:28` (row R1), which was annotated in place; `VERIFY_method.md:28` does not carry it. `NOTES.md:209` (no profile given) was not edited.
- GF09, header "Hardware target": the lossless formats now **do not meet the hardware target** (inferred from measured, code and source): Quick Sync has no exact configuration on the UHD 770, FFmpeg has no QSV lossless switch, and oneVPL calls QP 0 invalid for these codecs.
- GF09, §2.5: new QSV lossless subsection (QPI 1 floor, QPI 10 with VDENC/4:4:4, the silent 4:2:0 Main with `low_power=1` on YUY2, h264_qsv NV12-only and no 4:4:4 profile).
- GF09, §2.7: pointer to the 300-frame NVENC exactness check.
- GF09, §2.11: the "Chromium playback of NVENC lossless: NOT VERIFIED" bullet replaced by the E35/E45 result (plays, exact YUV readback, H.264 software / HEVC hardware decoder).
- GF09, §4.1: the inferred hardware-decode guess replaced by measured NVDEC/D3D11VA results; H.264 vs HEVC still open on speed; path marked outside the hardware target.
- GF09, §4.10: narrowed; NVENC lossless NV12 has verified YUV readback in Chromium.
- GF09, §5: the "no lossless check" caveat now records the 300-frame exactness of re-encodes of all ten timed NVENC lossless configs (and Bayer8 quad); FFV1/rawvideo still checked on 1-8 frames only.
- GF09, §6: 300-frame gap limited to FFV1/rawvideo; QSV lossless answered (not available); decode correctness measured, speed not; Chromium NVENC lossless answered for NV12; AV1-on-QSV lossless lead added as NOT VERIFIED.
- Wording narrowed against the proposal where the files differ: the 33rd QSV configuration opened but failed on send (so "32 encoded", not "32 opened"); `MinQPI: 10` is reported by hevc_qsv only (h264_qsv reports QPI 10 with MinQPI 0); the highest QSV PSNR-Y min is 65.42 dB (Bayer8 quad, Y only), 65.33 dB on NV12/YUY2.

**Step 3 verification (`VERIFY_step3.md`, PASS WITH FIXES, nothing refuted)**

Re-checked by the reviser before applying: all 33 rows of `gapfill/GF09_rows_qsv_pyav19.0.2.json` (QPI from `libav_param_dump`, `decode.sw.max_abs_per_plane`, `psnr_y_min`, `keyframe_packets`; the failed row has `packets_written` None); the `droppedFrames` / `decodedFrames` fields in both `GF09_chromium_electron{35,45}.json`; `page.js:87` (`res.decodedFrames = v.getVideoPlaybackQuality().totalVideoFrames`); the `cuda` decoder field `h264 is_hwaccel=True` in `GF09_rows_nvenc_pyav19.0.2.json`; `GF09_qsv_lossless.md:91` ("NVDEC use was not checked with nvidia-smi (NOT VERIFIED beyond PyAV's flag)").

What changed:
- W1, §2.5: "closest approach" replaced. Every QPI-1 row (h264 and hevc) has max abs diff 2 on Y (hevc 65.33-65.42 dB, h264 64.42-64.84 dB); the YUY2 best (Rext 4:2:2, 65.33 dB, 562.9 KB/frame) is stated separately. Widened beyond the verdict's wording because the h264_qsv QPI-1 rows also have Y diff 2.
- W2, §2.5: keyframe claim scoped to the 32/33 rows that encoded.
- W3, §2.11: "60/60 decoded frames" replaced by "60 frames (`totalVideoFrames`, includes dropped)"; the dropped-frame count kept only as load-sensitive, not a performance result; caveat added to §5.
- W4, §4.1/§6: cuda/d3d11va rows labelled PyAV `is_hwaccel=True`, nv12/p010le frames, GPU use not checked with nvidia-smi.
- W5, §5: "flag closed" relabelled inferred (re-encodes with the same config; timed streams deleted; KB/frame equal to the byte). §6 and the §3.1 note were updated to match.
- W6, §2.11/§4.1/§6/§5: d3d11va and Chromium decoder results scoped to this RTX 3070 (driver 610.88); other GPUs, including Intel D3D11VA, NOT VERIFIED.
- W7, §4.10: "(3 frames per file, YUV only)" added.
- W8, §3.4: Electron row now reads "libx265 Rext 4:2:0 playback (HEVC Main already plays in E35)".
- Minor: GF09 scripts added to §7; Intel driver added to versions.

**Still NOT VERIFIED:** lossless on AMF/VideoToolbox and on Intel generations other than the UHD 770; hardware/threaded decode speed of NVENC lossless; actual NVDEC use in the cuda/d3d11va rows beyond PyAV's flag; hardware decode and Chromium decoder choice on other GPUs; Chromium playback of gray/Bayer/P010 lossless and canvas RGB fidelity; real-sensor Bayer and real 10/12-bit noise; other CPUs; run-to-run variation; the FFV1 range coder at t1; FFV1 v4 coder vs Bayer transform; 4:2:2 via NVENC 4:4:4; multi-stream, 60 fps, long-recording and writer-kill behaviour; Defender's share; the cause of the FFV1 s24 t0 cross-version difference.
