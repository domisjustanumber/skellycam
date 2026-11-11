# uncompressed_intra (G4): findings (revised)

Machine Gerald: i7-14700K (20 cores / 28 logical), RTX 3070 (driver 610.88), Intel UHD 770 iGPU (present since 16:36). Written 2026-11-09. This revision applies `VERIFY_provenance.md` and `VERIFY_method.md`. I checked each of their refutations again before applying it (see §7). It also adds four quick functional re-checks made with PyAV 19.0.2, none of them timed.

Paths are relative to `research/skellycam_recording/recording_upgrade/results/uncompressed_intra/` unless they start with `research/`.

**Labels**
- **measured**: a PyAV 19.0.2 result file, cited by path.
- **background (PyAV 18.0.0)**: a result from the skellycam venv (PyAV 18.0.0 / FFmpeg 8.1.2). Kept only as context, never as the basis for a functional claim.
- **CLI reference**: a result made with the ffmpeg 9.0.2 CLI (gyan full build, libavcodec 63.1.102, the same FFmpeg release that PyAV 19.0.2 bundles). This is not the implementation under test.
- **source**: a primary source, quoted, accessed 2026-11-09.
- **code**: repo file:line.
- **inferred**: my reasoning, marked as such.
- **NOT VERIFIED**: no evidence either way.

**Rules for this revision**
1. Functional claims rest on PyAV 19.0.2 files: `functional_matrix_pyav19.0.2.json` and `functional_tables.md` (the PyAV 19 sections), `pyav_caps_19.0.2.json`, `pyav_mux_acceptance_19.0.2.json`, `ffv1_v4_cross_version_pyav19.0.2.json`, `qsv_recheck_pyav19.0.2.json`, `ffv1_recheck_pyav19.0.2.json` and `bayer_debayer_check_pyav19.0.2.json`.
2. **Bench numbers are contaminated.** The machine was about 50% busy with other agents during the bench (§2.7). Every fps, cores/stream and ms figure in §2.7 and §3 is a lower bound on speed, or an upper bound on cost. Most of them are also PyAV 18 (background). All of them will be replaced by tonight's quiet PyAV 19.0.2 re-run from 23:00 (`HANDOFF.md` §6B and §7). Sizes (KB/frame) do not depend on load, but they do depend on content (§2.1).

Units: KB = 1000 bytes of encoded payload per frame (packet bytes / packets; container overhead excluded). "cores/stream" = process CPU seconds per second of 30 fps video. t1 = `thread_count=1`; t0 = libav auto threads.

## 1. Questions
1. Which codecs store each uncompressed camera format bit-exact and intra-only, either natively or after an exact re-layout? Formats: YUY2, NV12, GRAY8/16, P010, RGB, Bayer 8/12, packed RAW10/12.
2. Which containers keep the pixel format, and what survives truncation?
3. How large is each option, and roughly how expensive (lower bounds only until tonight)?
4. Bayer: raw mosaic, plane-split mosaic, or debayered RGB?
5. What can Chromium (Electron 35/45) play natively?
6. Do PyAV 19.0.2, OpenCV 5.0.0.93 or Electron 45.2.3 add useful support?

## 2. Findings

### 2.1 Inputs
- measured (code `scripts/uncompressed_intra/uintra_frames.py` docstring; corpus `index.json`): the YUY2 frames are the camera's own bytes (`c930e_1080p_yuy2`, 8 frames; `c922_1080p_yuy2`, 8 frames).
- Every other format is derived from C930e YUY2: NV12, gray, gray16, P010, RGB, Bayer 8/12, quad split and RAW10/12-packed. The 720p "YUY2" comes from decoded `c930e_720p_flash` JPEGs.
- measured (`loose_ends_check.json`; the script reads frames with numpy only, no PyAV): camera YUY2 is limited range.
  - c930e: Y 18..234, C 115..151.
  - c922: Y 16..235, C 95..181.
  - 0 samples fall outside 16..235.
- **Content dependence.** measured (`ffv1_recheck_pyav19.0.2.json`): the same FFV1 v3 s24 rice g1 config gives 470.3 KB/f on real C930e YUY2 and 740.7 KB/f on real C922 YUY2 (+58%). Both are bit-exact over 8 frames. Every size in this file comes from the C930e scene unless stated otherwise.
- **720p rows are JPEG-derived.** CLI reference (`verify_method/ffv1_size_by_camera.txt`): decoded C930e 1080p JPEGs give 325.1 KB/f, against 470.3 for real C930e YUY2. inferred: JPEG quantisation smooths the image, so the 720p sizes are probably flattered.
- **12-bit sizes are dominated by synthetic noise.** The >8-bit sources carry 4 seeded random low bits (code `uintra_frames.py` docstring). measured (`ffv1_recheck_pyav19.0.2.json`, FFV1 v3 s24, 1 frame, all bit-exact):

| 12-bit layout | noise=True | noise=False | share from noise |
|---|---|---|---|
| quad split (gray16le) | 1,617,493 B | 504,260 B | 69% |
| mosaic (gray16le) | 2,347,875 B | 1,219,858 B | 48% |

  - Share from noise is arithmetic. 4 uniform bits x 1920x1080 = 1,036,800 B of entropy (arithmetic).
  - The quad/mosaic ratio is 1.45x with noise and 2.42x without.
  - inferred: the high bits come from an ISP-processed image with 4:2:2 chroma, so the direction of the error against real raw data is unknown. The earlier word "pessimistic" is withdrawn.
- inferred (path name `pyav_ds_1920x1080_5` in corpus `index.json`): both YUY2 sets look like 5 fps captures. NOT VERIFIED that either camera delivers 1080p30 YUY2. "Per 30 fps stream" is only a normalisation.

### 2.2 Library capability and versions
- measured (`pyav_caps_19.0.2.json`): PyAV 19.0.2 bundles libavcodec 63.1.102 (FFmpeg 9.0.2). background (`pyav_caps_18.0.0.json`): PyAV 18.0.0 bundles 62.28.102 (FFmpeg 8.1.2).
- measured (`pyav_caps_19.0.2.json`): no encoder for libopenjpeg, libjxl, libaom-av1, librav1e or libsvtjpegxs; no JPEG XL or JPEG XS decoder.
- measured (`pyav_caps_{18.0.0,19.0.2}.json`): the only encoder pix_fmt changes from 18 to 19:
  - ffv1 gains `bayer_rggb16le`;
  - h264/hevc/av1_nvenc gain `p012le`, `p212le` and `yuv444p12msble`.
- measured (`pyav_mux_acceptance_19.0.2.json`):
  - PyAV refuses Matroska for ffvhuff, huffyuv, utvideo, magicyuv, jpegls, png and dnxhd.
  - NUT and AVI accept all of these except dnxhd, which PyAV accepts only in MOV.
  - background: PyAV 18.0.0 behaves the same.
- source (PyAV 19.0.2 wheel, `av/container/output.py:166-171`, read from the uv environment):
  `if not lib.avformat_query_codec(self.ptr.oformat, codec.id, lib.FF_COMPLIANCE_NORMAL): raise ValueError(f"{self.format.name!r} format does not support {codec_obj.name!r} codec")`.
  The same check is at lines 306, 381 and 539. background: PyAV 18.0.0 has it at `output.py:112-116`.
- CLI reference (`ffmpeg_cli_reference.json`): the ffmpeg 9.0.2 CLI muxes utvideo (`ULY2`), ffvhuff (`FFVH`), magicyuv (`M8Y2`) and jpegls (`MJLS`) into MKV, bit-exact. So the refusal is PyAV's compliance gate, not a Matroska limit.

### 2.3 Pixel format -> codec (bit-exact)
The full matrix is in `functional_tables.md`: 15 sources x 37 configs, 4 real 1080p frames, from `functional_matrix_pyav19.0.2.json`. All bullets below are measured from it unless labelled otherwise.
- No lossless encoder that opens here takes packed 4:2:2. Every exact path de-interleaves to yuv422p, which is exact. Only rawvideo stores YUY2 as-is.
- Exception to the above: `hevc_qsv` (lossy) lists `yuyv422` and `y210le` (`pyav_caps_19.0.2.json`). Since the iGPU appeared it opens and encodes camera YUY2 directly (§2.5). libx264 and NVENC list `nv16`, which is semi-planar, not packed.
- NV12 is native in libx264, h264_nvenc and hevc_nvenc. Every other encoder needs NV12 -> yuv420p, which is exact.
- GRAY16 is native in ffv1, ffvhuff, jpegls and jpeg2000. libx265 is exact via gray12le. hevc_nvenc lossless is not exact: fed yuv444p16le, it decodes as yuv444p10le.
- P010 is exact natively only in hevc_nvenc lossless. Every other encoder needs shift + de-interleave to yuv420p10le, which is exact.
- FFV1 with the default GOP produces non-keyframe packets (`ffv1_l1_gdefault.mkv`). Every `-g 1` FFV1 config is all-keyframe.
- source (RFC 9043, https://www.rfc-editor.org/rfc/rfc9043.txt):
  - §3.8.1.3: "When the "keyframe" value (see Section 4.4) is 1, all range coder state variables are set to their initial state."
  - §3.8.2.5 (the rice/VLC coder recommended below): "When "keyframe" (see Section 4.4) value is 1, all VLC coder state variables are set to their initial state."
  - §4.2.17 "intra": value 1 means ""keyframe" MUST be 1 (keyframes only)".
  - All three were re-read from the downloaded RFC; see §7.

### 2.4 Containers
- measured (`functional_tables.md`, PyAV 19):
  - NUT keeps bayer_rggb8/16le, gray16le, rgb24 and nv12 bit-exact.
  - p010le in NUT reads back as rgb555le.
  - MKV rawvideo works only for yuyv422, nv12, yuv420p, gray and 8-bit quad/packed-as-gray.
- CLI reference (`ffmpeg_cli_reference.json`): NUT tags are `[186]RG[8]` and `[186]RG[16]`. `-allow_raw_vfw 1` returns Bayer16/gray16 in MKV as rgb555le, not exact.
- source (FFmpeg n9.0.2 `libavformat/matroskaenc.c:2042-2043`): "Raw RGB is not supported Natively in Matroska, you can use AVI or NUT or".
- measured (`functional_tables.md`, "Lossless configs that decoded but were not bit-exact"):
  - AVI loses gray16le and p010le, returns rgb24 as bgr24, and cannot decode Bayer.
  - MOV returns gray as pal8 and gray16 as rgb555be, and cannot decode nv12, yuv420p, p010 or Bayer.
- **Truncation at 50% of a finalized 4-frame file.** measured (`functional_tables.md` truncation table, PyAV 19):
  - MKV, NUT and AVI kept 1-2 frames for nearly all configs. `rawvideo.avi` with bayer_rggb16le kept 0 (OSError).
  - Every complete frame was bit-exact.
  - `ffvhuff_median.nut` and `jpegls.nut` on bayer_rggb16le each returned 2 frames, of which only 1 was exact. The cut last frame came back silently corrupted, with no error.
  - NUT and AVI readers raised InvalidDataError or ArgumentError at the tail. MKV readers did not.
  - Every MOV/MP4 config decoded 0 frames.
- Limits of the truncation test:
  - code (`scripts/uncompressed_intra/functional_matrix.py:403-410`): this is a cut of an already-finalized file, not a writer crash.
  - `research/frame_ring_buffer/prototypes/results/p11_crash_container.md` killed writers for MKV and MP4 only, so it agrees for MKV only.
  - CLI reference (`verify_method/cli_checks.txt` §2): a hard-killed ffmpeg 9.0.2 writer (about 3 s at 30 fps) left 100-104 readable frames in utvideo.avi, ffvhuff.nut, ffv1.mkv, utvideo.nut and ffv1.avi. The partial last packet reached the decoder in AVI/NUT ("Incorrect slice size"; "slice count 0 is invalid").
  - Kill tests with the PyAV writer belong to `results/crash_resilience/`.

### 2.5 GPU encoders
- **NVENC.** measured (`functional_matrix_pyav19.0.2.json`; `functional_tables.md`):
  - h264_nvenc lossless gop 1 is exact for nv12/yuv420p (native), gray (re-layout) and rgb (via gbrp).
  - hevc_nvenc lossless is exact for nv12, p010le (native) and rgb.
- measured (`functional_tables.md`, encoder/muxer errors, PyAV 19):
  - h264/hevc_nvenc on 4:2:2: "YUV422P not supported; ... No capable devices found".
  - h264_nvenc on gray16/Bayer16: "10 bit encode not supported".
  - av1_nvenc: "Codec not supported".
  - av1_amf: "DLL amfrt64.dll failed to open".
  - av1_mf: "could not find any MFT for the given media type".
- source (FFmpeg n9.0.2 `libavcodec/nvenc.c:445-453`): `#ifdef NVENC_HAVE_422_SUPPORT ret = nvenc_check_cap(avctx, NV_ENC_CAPS_SUPPORT_YUV422_ENCODE); #else ret = 0; #endif if (IS_YUV422(ctx->data_pix_fmt) && ret <= 0) { av_log(avctx, AV_LOG_WARNING, "YUV422P not supported\n");`.
- source (n9.0.2 `nvenc.h:66-68`): `#if NVENCAPI_CHECK_VERSION(13, 0)` ... `#define NVENC_HAVE_422_SUPPORT`.
- source (n9.0.2 `nvenc.c:60-61`): `AV_PIX_FMT_NV16` is listed only `#ifdef NVENC_HAVE_422_SUPPORT`.
- measured (`pyav_caps_19.0.2.json`): h264/hevc_nvenc list `nv16`, so the macro is defined in this build.
- inferred: the 4:2:2 refusal comes from the GPU capability query, i.e. this RTX 3070 (Ampere) has no 4:2:2 NVENC, not from an FFmpeg build limit.
- measured (`functional_matrix_pyav19.0.2.json`): hevc_nvenc fed 12-bit values in yuv444p16le outputs yuv444p10le, not exact. A request in `yuv444p12msble` was not tested with PyAV 19 (NOT VERIFIED).
- measured (`functional_matrix_pyav{18.0.0,19.0.2}.json` `nvidia_smi_before/after`): NVENC was shared during the matrix. PyAV 19 samples showed 0-2 sessions and 0-93% GPU utilisation. inferred: this does not change functional pass/fail, because the errors name capabilities.
- **QSV, now that the iGPU is present.** measured (`qsv_recheck_pyav19.0.2.json`: 4 real C930e YUY2 1080p frames, gop_size=1, nvidia-smi 0 sessions before and after):

| encoder | input | result | decoded | profile | keyframes | Y PSNR min |
|---|---|---|---|---|---|---|
| hevc_qsv | yuyv422 (camera bytes, no conversion) | ok | yuv422p | Rext | 4/4 | 50.64 dB (lossy, defaults) |
| hevc_qsv | nv12 | ok | yuv420p | Main | 4/4 | 50.65 dB |
| h264_qsv | nv12 | ok | yuv420p | High | 4/4 | 50.12 dB |
| av1_qsv | nv12 | open fails: "Function not implemented" | - | - | - | - |

- The 11:19 matrix failures ("Error creating a MFX session: -9") and the `loose_ends_check.json` failure ("Failed to find d3d11va adapter by vendor id 0x8086") were made while the iGPU was phantom. They are superseded.
- NOT VERIFIED:
  - QSV lossless or near-lossless intra;
  - Chromium playback of hevc_qsv 4:2:2 Rext;
  - whether av1_qsv fails because UHD 770 has no AV1 encode (the vendor-source check belongs to `results/hw_accel_target/`).

### 2.6 Bayer storage
- measured (`functional_tables.md`, PyAV 19, 1080p 12-bit RGGB with seeded noise, bit-exact, KB/f):
  - rawvideo 4147;
  - RAW12-packed rawvideo 3110;
  - RAW12-packed FFV1 range 2467;
  - mosaic gray16le FFV1 v3 2413;
  - mosaic jpeg2000 1839;
  - quad FFV1 v3 1620;
  - quad jpegls 1601;
  - FFV1 v4 native 1625;
  - mosaic x265 gray12le 2819.
  - These rankings depend on the noise model (§2.1).
- **FFV1 v3 forces the range coder above 8 bits.** measured (`ffv1_recheck_pyav19.0.2.json`): gray16le at level 3 gives identical bytes for coder=rice and coder=range_tab:
  - quad 1,617,493 / 1,617,493;
  - mosaic 2,347,875 / 2,347,875.
- CLI reference (`verify_method/cli_checks.txt` §1): the encoder logs "high bits_per_raw_sample, forcing range coder".
- measured (same PyAV 19 file): native bayer_rggb16le at level 4 is not forced. rice gives 1,629,144 B and range gives 1,612,245 B, both exact.
- So the "rice" and "range" 12-bit FFV1 v3 rows in the bench are the same encoder mode, and the v4 bench row (default coder = rice) is not like-for-like with v3. source (`verify_method/ffv1_encoder_help_ffmpeg9.0.2.txt`, `ffmpeg -h encoder=ffv1`): "-coder ... (default rice)".
- source (FFmpeg n9.0.2 `libavcodec/ffv1enc.c`):
  - lines 921-927: `case AV_PIX_FMT_BAYER_RGGB16: ... s->version = FFMAX(s->version, 4); s->bayer = 1;`;
  - lines 652-653: "Version 2 or 4 needed for requested features but version 2 or 4 is experimental and not enabled";
  - lines 1694-1696: "Bayer 2x2 RCT, based on: "Reversible color transform for Bayer color filter array images", S. Poomrittigul et al".
- source (n8.1.2 `ffv1enc.c`): no `bayer` string.
- source (RFC 9043 §1, line 162): "This document defines versions 0, 1, and 3 of FFV1."
- measured (`ffv1_v4_cross_version_pyav19.0.2.json`): PyAV 19 decodes CLI-written FFV1 v4 bayer_rggb16le and gray16le, and v3 gray16le. The check covers frame 0 of 5 only (`frame0_bit_exact`), on a 320x240 random 12-bit clip.
- background (PyAV 18.0.0 used as the old reader under test; `ffv1_v4_cross_version_pyav18.0.0.json`): FFmpeg 8.1.2 cannot open FFV1 v4 Bayer ("Invalid data found ... avcodec_open2"). Its own v4 gray16/Bayer round trip decodes as grayf16le, not exact (`functional_tables.md`, PyAV 18 -> 19 differences).
- **Debayering.** measured (`bayer_debayer_check_pyav19.0.2.json`, PyAV 19.0.2 + OpenCV 5.0.0; results identical to the PyAV 18 / OpenCV 4.12 file):
  - swscale demosaic keeps the CFA samples exactly.
  - After conversion to 8-bit yuv420p, the max error is 365/4095 at 12-bit (43.52 dB) and 24/255 at 8-bit (43.23 dB).
  - OpenCV `BayerBG2BGR*` matches RGGB (43.6-44.25 dB). `BayerRG2BGR*` gives 20.33-20.35 dB.
  - Only 8-bit BG VNG is exact. VNG fails on 12-bit ("Assertion failed) depth == CV_8U").
- measured (same file, 1 frame): debayered RGB in FFV1 takes 3,735,615 B (12-bit) and 940,014-1,151,126 B (8-bit). The raw layouts take: mosaic 2,414,539 / 1,078,696 B and quad 1,596,055 / 492,160 B (12-bit / 8-bit).

### 2.7 Bench results: CONTAMINATED, lower bounds, mostly PyAV 18 background
Files: `bench/<config>__<source>_<res>__t<threads>__pyav<ver>.json` (147 cases: 133 on PyAV 18.0.0, 14 on PyAV 19.0.2); median of 3 reps after a discarded warm-up. **Every number in this section will be replaced by tonight's quiet PyAV 19.0.2 re-run (23:00).**

**Contamination.** measured:
- whole-machine CPU was 50.4% before the run (`bench/precheck_typeperf.csv`);
- 24.3-52.3% in 5-minute re-checks (`bench/precheck_typeperf_recheck_avgs.txt`);
- 13-99% during individual reps (`system_cpu_percent_during_encode` in each JSON; this includes the bench's own load);
- NVENC had 3 sessions around two 720p GPU cases (`bench/precheck_nvsmi.txt`, case JSON).

**Method caveats** (for tonight's re-run):
- **Encoder open is inside the timed region.**
  - code: `scripts/uncompressed_intra/bench_intra.py:149-160` starts the clock before the first `encode()`.
  - source: PyAV opens the codec on the first encode.
  - measured (bench JSON `latency_max`/`encode_wall_s`): the slowest call is 75% of wall time for dnxhd t0, 54-56% for svtav1 p10, 16% for h264_nvenc and 6% for FFV1.
  - This distorts short reps: 24 frames for slow codecs, under 1 s for NVENC.
- **Hybrid CPU without affinity.** CLI reference (`verify_method/cpu_topology.txt`): 20 cores, 28 logical. inferred: P and E cores, so a t1 thread can land on either, which fits the wide t1 ranges (ffvhuff 147-209 fps).
- **Warm caches.** The 8 unique frames total about 33 MB, against a 33.8 MB L3 (`cpu_topology.txt`), and decode reads the file just written. inferred: rawvideo encode and all decode figures measure memory and page cache, not disk.
- Single-camera content, JPEG-derived 720p and noise-dominated 12-bit sizes (§2.1).
- Forced range coder on 12-bit FFV1 v3 (§2.6).

YUY2 1080p, background (PyAV 18), lower bounds:
- t1 fps:
  - rawvideo 366;
  - ffvhuff 203;
  - mjpeg q2 (lossy) 149;
  - utvideo 99;
  - magicyuv 97;
  - dnxhr (lossy) 83;
  - x264 qp0 75;
  - FFV1 v3 rice 42-43 (0.69-0.70 cores/stream);
  - FFV1 level 1: 43.
- FFV1 range at t1: 27 fps (s24) and 29 fps (s4), 1.10 / 1.00 cores/stream, 370 / 373 KB (21% smaller than 469-470).
  - The s24 rep range is 26.6-32.5 fps at 30-43% system CPU, so "range misses 30 fps at t1" is not established (VERIFY_method W4).
- FFV1 at t0: 138 fps (s4), 266 (s16, s24). Level 1 stays at 43. Decode is about 39-40 fps at t1 and 417-443 at t0.
- Smallest lossless YUY2 1080p (sizes; load-independent; C930e only): FFV1 range 370, rice 469-470, x264 qp0 581, jpeg2000 633, vp9 668, x265 702, utvideo 786, magicyuv 795, ffvhuff 1162, raw 4147 KB.
- Slow at t1: jpeg2000 7 fps (4.14 cores/stream), prores 7, vp9 lossless 11 (48 at t0), x265 lossless 21 at 11.99 cores/stream. inferred: x265 and svtav1 ignore thread_count=1 (about 8.5 and 10.9 busy cores).
- De-interleave runs outside the timed loop (code `bench_intra.py:111-121`). From `prep_ms_per_frame`: YUY2 -> yuv422p median 1.73 ms (1.46-3.69) at 1080p, 0.69 ms at 720p; NV12 -> yuv420p 0.37 ms. These are upper bounds under load. Quad split was not timed.

NV12 1080p, background (PyAV 18), t1 / t0:
- FFV1 s24 rice 54 / 326 fps, 383 KB;
- range 45 / 296 fps, 306 KB;
- utvideo 159 / 896 fps, 627 KB;
- svtav1 lossless 41 / 41 fps at 7.27 cores/stream, 545 KB.

Bayer, background (PyAV 18) except where marked:
- Bayer12 FFV1 v3, forced range coder: mosaic 2349-2413 KB at 8-10 fps t1; quad 1625-1647 KB at 14-15 fps t1; quad s24 t0 107 fps (2.46 cores/stream).
- measured (lower bound, PyAV 19): FFV1 v4 native Bayer with the rice coder takes 1633 KB at 30 fps t1 (1.00 cores/stream), 94 fps t0, decode 29 / 330 fps. v3 s4 quad (range forced) on the same PyAV takes 1625 KB at 16 / 53 fps. The speed gap mixes coder and Bayer transform (§2.6), so it is not attributable.
- Bayer8: FFV1 s24 rice 50 fps t1, 990 KB; jpegls 31 fps, 1095 KB; ffvhuff 269 fps but 2238 KB, larger than raw (2074).
- Bayer12 quad ffvhuff: 171 fps t1, 0.18 cores/stream, 1829 KB (+11% over quad FFV1 v3; this gap is set by the noise model).

NVENC 1080p, background (PyAV 18):
- h264 lossless NV12: 428 fps, 0.07 cores/stream, 594 KB;
- h264 lossless gray: 472 fps, 447 KB;
- hevc lossless NV12: 292 fps, 518 KB;
- hevc lossless P010: 155 fps, 1423 KB;
- hevc CQ: 431 fps, 59 KB;
- software decode of hevc lossless: 12-24 fps;
- 720p: 327-876 fps.

720p t1, background (PyAV 18; JPEG-derived input): FFV1 s24 117 fps, 0.24 cores/stream, 130 KB; utvideo 252 fps; mjpeg 407 fps, 46 KB.

PyAV 19 vs 18:
- measured: sizes are identical.
- Timings differ beyond the 3-rep ranges in opposite directions:
  - mjpeg t1: 149 (133-158) vs 168 (162-169);
  - FFV1 s24 t0: 266 (259-271) vs 226 (218-235).
- These differences follow the background load (system CPU 49-72% vs 28-38% for mjpeg). No version speed effect can be read from this run.

Python stills (`bench/py_still__uv.json`, uv env, no PyAV; 16 frames x 3, thread pool, contaminated), fps at 1 / 8 workers:
- simplejpeg 4:2:2: 204 / 991;
- simplejpeg 4:2:0: 423 / 1921;
- cv2 YUY2 -> BGR -> JPEG: 196 / 758;
- JXL e1 Bayer12 mosaic: 84 / 430 (2766 KB);
- JXL e1 quad: 90 / 493 (1777 KB);
- at 1 worker only: SOF3 14, ljpeg 42, JPEG-LS 25, J2K 6, cv2 PNG 20 fps.
- inferred: all release the GIL (3.5-7.6x scaling).

Debayer (`bench/debayer__pyav18.0.0_cv4.12.0.json`, background, 30 frames), ms at 8 / 12-bit: OpenCV bilinear 0.96 / 1.31; EA 0.99 / 1.31; VNG 8.40 / error; swscale 5.05 / 7.87.

### 2.8 JPEG from camera YUV (`python_jpeg_libs_uv.json`: uv env with simplejpeg 1.9.0, PyTurboJPEG 2.6.1, imagecodecs 2026.10.10, opencv-python 5.0.0; no PyAV)
- measured: simplejpeg `encode_jpeg_yuv_planes` takes 4:2:2 planes, I420 and Y-only. It rejects interleaved NV12 UV.
- measured: PyTurboJPEG 2.6.1 is unusable from pip alone (needs libjpeg-turbo >= 3.0).
- measured: cv2.imencode needs BGR first. Neither OpenCV 5.0.0 nor 4.12.0 has a .jxl/.avif writer (background: `python_jpeg_libs_venv.json` for 4.12.0).
- measured: simplejpeg q90 Y PSNR 52.92 dB. Decoded as full-range RGB, it scores 27.74 dB against a limited-range BT.601 reference.
- measured: 12-bit Bayer, 1 frame, all exact, sizes in KB: JPEG-LS 2505, J2K reversible 1748, JXL e3 2397 / e1 2767, SOF3 12-bit 2705, PNG 2938.
- source (FFmpeg n9.0.2 `libavcodec/mjpegenc_common.c:499`): "Non full-range YUV is non-standard, set strict_std_compliance to at most unofficial to use it."
- source (JFIF 1.02, printed p.3, https://www.w3.org/Graphics/JPEG/jfif3.pdf): "normalized so as to occupy the full 256 levels of a 8-bit binary encoding". inferred: limited-range YUV stored in JFIF without conversion shows raised blacks.

### 2.9 Codecs PyAV 19 lacks (CLI reference only)
- CLI reference (`ffmpeg_cli_reference.json`):
  - libjxl lossless is exact for gray8 and for Bayer-as-gray16; YUY2 via rgb24 is not exact;
  - libaom allintra lossless is exact for yuv422p and gray12le (Bayer mosaic 2136 KB, all-keyframe);
  - svtav1 lossless yuv420p is exact;
  - rav1e qp0 is not lossless;
  - libopenjpeg gray16/Bayer16 is exact.
- CLI reference (`loose_ends_check.json`): JPEG XL / JPEG XS refuse every container tried:
  - MKV: "No bmp codec tag found";
  - NUT: "No codec tag defined";
  - MOV: "Could not find tag ... not currently supported in container".
- None of these is usable from PyAV 19.0.2 (§2.2).

### 2.10 Chromium playback (shallow; samples encoded with the ffmpeg 9.0.2 CLI, code `make_chromium_samples.py:2,71`)
- measured (`chromium_check_electron35.json`: E35.7.5 / Chrome 134.0.6998.205; `chromium_check_electron45.json`: E45.2.3 / Chrome 156.0.8078.80):
  - Load, draw and seek in both versions: VP9 lossless 4:4:4 / 4:2:2; AV1 lossless 4:2:0 / 4:2:2 / 4:4:4 / gray12; H.264 intra and lossless 4:2:0, intra 4:2:2.
  - HEVC intra 4:2:0 (Main): fails in E35, plays in E45.
  - Fail in both: MJPEG (AVI/MKV), FFV1, rawvideo YUY2 (MKV), ProRes.
  - JPEG XL still: E45 only. JPEG 2000: neither.
- measured (`verify_method/chromium_benched_configs_electron{35,45}.json`, the configs the bench actually used):
  - x264 qp0 4:2:2 (High 4:4:4 Intra) plays in MKV and MP4 in both versions.
  - x265 lossless 4:2:2 (Rext) fails in both: E35 `DEMUXER_ERROR_NO_SUPPORTED_STREAMS`, E45 `PIPELINE_ERROR_DECODE`.
  - x265 lossless 4:2:0 (Rext) plays in E45 only.
  - svtav1 lossless 4:2:0 in MKV plays in both.
  - H.264, AV1 and VP9 in `.mkv` play in E35 even though `canPlayType('video/x-matroska')` returns "". inferred: the codec is the blocker, not MKV.
- NOT VERIFIED: NVENC and QSV output in Chromium (never loaded).
- **"Plays" does not mean correct pixels.** code (`scripts/uncompressed_intra/chromium_check/page.html`): the harness keeps only a weighted sum of a 64x36 drawImage copy.
  - measured: the same 4:2:2 lossless YUV gives sum 1,968,455 for VP9/AV1 but 1,990,009 for H.264 qp0 4:2:2.
  - CLI reference (`verify_method/canvas_sum_hypotheses.txt`): the 4:2:2 sums match no standard matrix (predicted range 1,994,305-2,013,740).
- **Colour matrix changes between Electron versions.** The predicted frame-0 4:2:0 sums are 1,999,356 (BT.601 limited) and 2,011,860 (BT.709 limited) (`verify_method/canvas_sum_hypotheses.txt`).
  - The observed 2,011,651 (E45 for every codec; H.264 in E35) is within 0.01% of BT.709.
  - E35 AV1 lossless 4:2:0 (1,999,082) is within 0.02% of BT.601.
  - inferred: E35 renders untagged VP9/AV1 4:2:0 as BT.601, and E45 and H.264 render it as BT.709. Every E35 VP9/AV1 4:2:0 sum changed in E45; H.264 did not (study JSON).
  - Colour fidelity is NOT VERIFIED.
- inferred: Bayer streams display as a grey mosaic. Colour needs a WebGL demosaic.

## 3. Comparison tables
Speed columns are **contaminated lower bounds** from PyAV 18 (background) unless marked "19". They are to be replaced at 23:00. Sizes are C930e content only.

### 3.1 YUY2 1080p
| config | exact (PyAV 19 matrix) | KB/f | MB/s @30 | t1 fps | t1 cores | t0 fps | trunc 50% (PyAV 19) | Chromium (exact file tested) |
|---|---|---|---|---|---|---|---|---|
| rawvideo .nut | yes | 4147 | 124 | 366 | 0.08 | 409 | 1 frame, tail error | not tested (rawvideo YUY2 .mkv fails both) |
| ffvhuff .nut | yes | 1162 | 35 | 203 | 0.15 | 515 | 2/2, tail error | not tested |
| utvideo .avi | yes | 786 | 24 | 99 | 0.30 | 456 | 2/2, tail error | not tested |
| magicyuv .avi | yes | 795 | 24 | 97 | 0.31 | 441 | 2/2, tail error | not tested |
| x264 qp0 .mkv (4:2:2) | yes | 581 | 17 | 75 | 0.38 | 385 | 2/2 | plays E35+E45 (pixels NOT VERIFIED) |
| FFV1 v3 s4 rice .mkv | yes | 469 | 14 | 43 | 0.69 | 138 | 2/2 | fails both |
| FFV1 v3 s24 rice .mkv | yes | 470 | 14 | 42 | 0.70 | 266 | 2/2 (s4 config tested) | fails both |
| FFV1 v3 s24 range .mkv | yes | 370 | 11 | 27 | 1.10 | 207 | 2/2 (s16 config tested) | fails both |
| vp9 lossless .webm (4:2:2) | yes | 668 | 20 | 11 | 2.71 | 48 | 2/2 | plays both |
| x265 lossless .mkv (4:2:2) | yes | 702 | 21 | 21 | 11.99 | 32 | 2/2 | fails both |
| jpeg2000 .mkv | yes | 633 | 19 | 7 | 4.14 | 19 | 2/2 | not tested (JPEG 2000 still fails both) |
| mjpeg q2 .mkv | lossy | 121 | 3.6 | 149 | 0.20 | 158 | 2 (lossy) | fails both |
| dnxhr hq .mov | lossy | 918 | 28 | 83 | 0.36 | 159 | 0 frames | not tested |
| prores hq .mov | lossy | 944 | 28 | 7 | 4.28 | 104 | 0 frames | fails both |
| svtav1 crf30 p12 (4:2:0) | lossy | 25 | 0.75 | 266 | 1.23 | 259 | 2 (lossy; p10 config tested) | SVT-AV1 intra 4:2:0 sample plays both |
| hevc_qsv (4:2:2 Rext, defaults; 19) | lossy | 55 (4 frames, file bytes) | - | not run | - | - | not tested | NOT VERIFIED |

MB/s @30 is arithmetic. The hevc_qsv size is file bytes / 4 from `qsv_recheck_pyav19.0.2.json` (218,045 B), not packet bytes.

### 3.2 Bayer 12-bit 1080p, bit-exact (sizes noise-dominated, §2.1)
| storage | KB/f (noise=True) | 1-frame bytes noise=False (19) | t1 fps | t1 cores | t0 fps | FFmpeg 8.1.2 reads |
|---|---|---|---|---|---|---|
| rawvideo bayer16 .nut | 4147 | - | 287 | 0.10 | 317 | yes |
| RAW12 packed rawvideo .nut | 3110 | - | 452 | 0.07 | not run | yes |
| mosaic gray16le FFV1 v3 s24 (range forced) | 2349 | 1,219,858 | 10 | 3.03 | 76 | yes |
| quad FFV1 v3 s24 (range forced) | 1647 | 504,260 | 15 | 2.00 | 107 | yes |
| quad FFV1 v3 s4 (range forced) | 1625 | - | 14 | 2.07 | 48 | yes |
| quad jpegls .nut | 1605 | - | 20 | 1.50 | 242 | yes |
| quad ffvhuff .nut | 1829 | - | 171 | 0.18 | 447 | yes |
| FFV1 v4 native, rice (19, experimental) | 1633 | - | 30 (19) | 1.00 | 94 | **no** |
| mosaic x265 gray12le | 2822 | - | 14 | 22.07 | 24 | yes |
| debayered RGB FFV1 (1 frame, 19) | 3736 | - | not run | - | - | yes |

The FFV1 v3 "range" Bayer bench rows are byte-identical to the rice rows (forced range, §2.6) and are merged here.

### 3.3 NV12 1080p, one stream
| config | KB/f | enc fps (lower bound) | cores/stream | Chromium |
|---|---|---|---|---|
| h264_nvenc lossless | 594 | 428 | 0.07 | NOT VERIFIED (libx264 lossless 4:2:0 MP4 plays both) |
| hevc_nvenc lossless | 518 | 292 | 0.07 | NOT VERIFIED (x265 lossless 4:2:0 plays E45 only) |
| hevc_qsv / h264_qsv (lossy, 19) | 45 / 67 (file bytes / 4) | not run | - | NOT VERIFIED |
| FFV1 s24 rice | 383 | 54 t1 / 326 t0 | 0.56 / 0.73 | fails |
| utvideo | 627 | 159 t1 / 896 t0 | 0.19 / 0.26 | not tested |
| svtav1 lossless p12 | 545 | 41 | 7.27 | plays E35+E45 (MKV) |
| av1_nvenc | - | fails to open (19) | - | - |

### 3.4 Version bumps
| bump | adds for G4 |
|---|---|
| PyAV 18.0.0 -> 19.0.2 | Experimental FFV1 v4 Bayer (unreadable by FFmpeg 8.1.2). NVENC 12-bit formats (untested here). No libjxl / libaom / openjpeg. Same sizes; speed not comparable (load) |
| OpenCV 4.12.0 -> 5.0.0.93 | Nothing: same debayer results (§2.6), no JXL/AVIF writer |
| Electron 35.7.5 -> 45.2.3 | HEVC 4:2:0 playback, JPEG XL stills. Untagged VP9/AV1 4:2:0 colour changes (inferred BT.601 -> BT.709). Still no FFV1, MJPEG, rawvideo or ProRes |
| + imagecodecs 2026.10.10 | JXL, SOF3 12-bit, JPEG-LS and J2K from pip on Windows |

## 4. Implications for the plan (all inferred from the sections cited)
1. **YUY2/NV12 archive.** FFV1 v3 in MKV, gop_size=1, slicecrc=1, 16-24 slices, rice coder, threads on (§2.3, §2.4, §3.1).
   - Size per stream varies with content by at least 1.6x (470-741 KB/f, §2.1).
   - The range coder (-21% size) waits for tonight's quiet t1/t0 re-run (VERIFY_method repro 1).
2. Budget the YUY2 de-interleave separately from the encoder. Its cost is re-measured tonight (§2.7).
3. **CPU-light fallback.** utvideo or ffvhuff in AVI/NUT, because PyAV's gate rules out MKV (§2.2). Readers must catch the tail exception (§2.4).
4. **Rawvideo** is about 124.4 MB/s per 1080p30 YUY2 stream (arithmetic: 4,147,200 B x 30).
   - p12's 481 MB/s minimum per-GiB figure was unbuffered write-through with 4 MiB sequential writes on a 94%-full C: (`research/frame_ring_buffer/prototypes/results/p12_disk_sustained.md:3,7`).
   - C: now has 826 GB free (`bench/precheck_disk.txt`).
   - The plain ratio 481 / 124.4 = 3.9 is not a stream-count guarantee for PyAV's buffered writes.
   - Use MKV for YUY2/NV12 and NUT for Bayer/gray16. Never MOV/MP4 (§2.4).
5. **NVENC lossless** is not the G4 answer for 4:2:2 cameras on Ampere (§2.5). It is H.264/HEVC (G7 conflict). It is valid for NV12 (§3.3).
6. **QSV** can encode camera YUY2 directly to 4:2:2 HEVC intra (lossy) and NV12 to H.264/HEVC (§2.5). That is a G6 lead with a G7 conflict. Lossless, playback and throughput are open (`results/hw_accel_target/`).
7. **Bayer.** Store the mosaic undebayered (§2.6) and record the CFA phase.
   - Choose between quad FFV1 v3 (about 2 cores/stream, lower bound) and quad ffvhuff (about 0.18 cores/stream, +11% size) by CPU budget, and only after testing real raw frames. Today's 12-bit sizes are 48-69% synthetic noise (§2.1, §3.2).
   - Not FFV1 v4: experimental, unreadable by FFmpeg 8.1.2 (§2.6).
   - For an RGGB preview use OpenCV `COLOR_BayerBG2BGR` (§2.6).
8. Packed RAW10/12: unpack to 16-bit before compressing. RAW12-packed FFV1 is 2467 KB vs mosaic gray16le FFV1 2413 KB (§2.6).
9. **G8 cannot be met by the archive codec** (§2.10). The H.264/VP9/AV1 lossless files that play have pixel fidelity NOT VERIFIED. A proxy or backend-decoded frames is needed (G8/G9 topics).
10. **G2.** MKV/NUT/AVI keep the complete frames. The reader must validate the last frame, because ffvhuff/jpegls in NUT returned a corrupt tail frame silently (§2.4). Writer-kill tests belong to crash_resilience.
11. Lossy JPEG of YUV frames: use simplejpeg from YUV planes, and convert or flag the range (§2.8).
12. No version bump is required for G4. PyAV 19 adds only experimental FFV1 v4 (§3.4).

## 5. Not tested / limits / NOT VERIFIED
- Every speed number is a contaminated lower bound, mostly PyAV 18. To be re-run quiet with PyAV 19.0.2 at 23:00. Fixes for that run:
  - open the codec before starting the clock;
  - at least 10 s per rep;
  - pin t1 runs to a P core;
  - both cameras' YUY2.
- VERIFY_method repro 2 (v4 rice/range vs v3 quad, null output) is still open. It needs timing.
- Not benchmarked:
  - NV12 1080p for 18 of 23 configs;
  - bayer8_quad;
  - RAW12-packed beyond rawvideo t1;
  - 6 of 10 720p configs;
  - Python stills at 4 workers or 120 frames;
  - debayer at 120 frames;
  - quad-split cost;
  - QSV throughput.
- bench/BENCH.md's run table totals 147 cases, which matches the 147 JSONs.
- One scene per camera, 4-8 real frames. All non-YUY2 formats are derived. 12-bit sizes depend on the noise model. Real Bayer statistics are NOT VERIFIED.
- No multi-stream concurrency, 60 fps, long recordings or AVI size-limit tests.
- AMF untestable (no AMD GPU). AV1 NVENC on newer GPUs NOT VERIFIED. QSV lossless NOT VERIFIED.
- The Chromium check is shallow: no pixel comparison, no frame-accurate seek or sync. Its samples were encoded by the ffmpeg 9.0.2 CLI, not PyAV.
- The CLI-reference evidence (`ffmpeg_cli_reference.json`, `loose_ends_check.json` NVENC/JXL parts, `verify_method/cli_checks.txt`) is supporting only. The CLI is not the implementation under test.
- NOTES.md is superseded where it conflicts with this file:
  - its NVENC session figure "0 sessions, 3-10 %" is wrong: sessions were 0-2 and utilisation 0-93% (§2.5);
  - its JPEG XL/XS error strings differ from the saved `loose_ends_check.json`;
  - its dnxhd NUT/AVI claim is wrong (§2.2).
- Licensing (G7) is out of scope (`results/licensing/`).

## 6. How to reproduce
From the repo root; `S=research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra`.

PyAV 19.0.2 (evidence):
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
Background (PyAV 18.0.0 venv) and CLI reference:
```
.venv/Scripts/python.exe $S/probe_pyav_caps.py ; .venv/Scripts/python.exe $S/pyav_mux_acceptance.py
.venv/Scripts/python.exe $S/functional_matrix.py ; .venv/Scripts/python.exe $S/ffv1_v4_cross_version.py
.venv/Scripts/python.exe $S/bayer_debayer_check.py ; .venv/Scripts/python.exe $S/python_jpeg_libs.py
.venv/Scripts/python.exe $S/ffmpeg_cli_reference.py ; .venv/Scripts/python.exe -I $S/loose_ends_check.py
bash $S/verify_method/cli_checks.sh
```
Chromium:
```
.venv/Scripts/python.exe $S/make_chromium_samples.py
env -u ELECTRON_RUN_AS_NODE skellycam-ui/node_modules/electron/dist/electron.exe $S/chromium_check/main.js <media>/chromium_samples/manifest.json <results>/chromium_check_electron35.json   (repeat with Electron 45.2.3)
bash $S/verify_method/make_chromium_benched_samples.sh
```
Contaminated bench, exactly as run:
- The per-case `bench_intra.py` command lines are in `bench/run_{core1080_yuyv,core1080_nv12,bayer,core720,gpu}.log`: venv PyAV 18, `--frames 90` or 24, `--reps 3`.
- PyAV 19 cases are in `bench/run_pyav19.log` (`uv run --script`).
- Python stills ran as 16 frames at 1 and 8 workers: `uv run --script $S/bench_py_still.py --frames 16 --workers 1,8`.
- Debayer: `.venv/Scripts/python.exe $S/bench_debayer.py --frames 30`.
- Summaries: `bench_summary.py` and `bench_tables.py`.

Versions:
- uv / PyPI: av 19.0.2, numpy 2.2.6, simplejpeg 1.9.0, PyTurboJPEG 2.6.1, imagecodecs 2026.10.10, opencv-python 5.0.0.93.
- venv (background): PyAV 18.0.0 (FFmpeg 8.1.2), OpenCV 4.12.0.
- ffmpeg 9.0.2 gyan full build.
- Electron 35.7.5 / 45.2.3.
- FFmpeg sources: https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/<path> and /n8.1.2/.

## 7. Verification
This revision step ran 2026-11-09 after 16:36, with functional checks only and no timing.

**Refutations, re-checked before applying**

| item | my check | outcome |
|---|---|---|
| Prov R1: truncation "all exact" | `functional_tables.md` truncation table (PyAV 19): ffvhuff.nut and jpegls.nut on bayer_rggb16le decode 2 frames, 1 exact; rawvideo.avi on bayer_rggb16le decodes 0 | confirmed; §2.4 and §4.10 rewritten |
| Prov R2 / Method R2: PyAV 19 vs 18 "within spread" | bench JSON `stats.encode_fps`: mjpeg t1 149.41 (132.62-158.05) vs 168.21 (161.74-169.33); FFV1 s24 t0 266.39 (258.61-270.62) vs 226.42 (217.98-234.65) | confirmed; §2.7 and §3.4 corrected |
| Prov R3: dnxhd in NUT/AVI | `pyav_mux_acceptance_19.0.2.json`: dnxhd refused for matroska, webm, nut, avi and mp4; accepted only for mov | confirmed; §2.2 corrected |
| Prov R4 / Method R3: "no compressing encoder takes packed 4:2:2" | `pyav_caps_19.0.2.json`: hevc_qsv lists yuyv422 and y210le. New `qsv_recheck_pyav19.0.2.json`: hevc_qsv now opens and encodes yuyv422 to 4:2:2 Rext (lossy) | confirmed and extended; §2.3 and §2.5 |
| Prov R5: "BENCH.md says 141 cases" | grep finds no "141" in `bench/BENCH.md` | confirmed; bullet replaced |
| Method R1: x265 lossless "E45 only" | `verify_method/chromium_benched_configs_electron{35,45}.json`: x265_lossless_422 errors in both; x265_lossless_420 plays in E45 only | confirmed; §2.10, §3.1 |

**Weak items applied**
- Prov W1: n9.0.2 `nvenc.c` and `nvenc.h` downloaded again into scratchpad `uncompressed_intra_revise/dl/`. Lines 445-453, 60-61 and h:66-68 match.
- Prov W2: the matrix fed yuv444p16le (JSON `target_pix_fmt`).
- Prov W3 / Method W12: Chromium cells now name the file tested.
- Prov W4: frame0-only scope stated.
- Prov W5: RFC §3.8.2.5 and §4.2.17 checked against the downloaded `rfc9043.txt` (lines 975-978, 1305-1308, 1745-1757).
- Prov W6: §4 labelled inferred.
- Prov W7: p12 write mode and ratio 3.9 checked against `p12_disk_sustained.md:3,7` and `bench/precheck_disk.txt`.
- Prov W8: §6 commands checked against `bench/run_*.log` and `BENCH.md:51-62`.
- Prov W9: `py_still__uv.json` `bytes_per_frame` 2765943.
- Prov W10: matrix nvidia-smi samples. PyAV 19: sessions 0 (139), 1 (60), 2 (5); utilisation 0-93%.
- Method W1: `bench_intra.py:149-160`, clock before the first encode.
- Method W2, W3, W4, W6, W9, W10, W11 and W13: applied as caveats.
- Method W5, W7 and W8: reproduced with PyAV 19.0.2 (below) instead of relying on the CLI.

**New PyAV 19.0.2 functional checks (each under 1 min CPU, no timing)**
- `scripts/uncompressed_intra/qsv_recheck.py` -> `qsv_recheck_pyav19.0.2.json`:
  - hevc_qsv yuyv422 / nv12 and h264_qsv nv12 encode, all keyframes, 50.1-50.7 dB;
  - av1_qsv fails to open;
  - nvidia-smi "0, 24 %" before and "0, 17 %" after.
- `scripts/uncompressed_intra/ffv1_pyav19_recheck.py` -> `ffv1_recheck_pyav19.0.2.json`:
  - forced range coder on v3 12-bit (identical bytes);
  - v4 Bayer rice 1,629,144 vs range 1,612,245 B;
  - noise=True / noise=False sizes;
  - C930e 470.3 vs C922 740.7 KB/f;
  - all exact.
  - These match the verifier's CLI numbers byte-for-byte where the settings match.
- `scripts/uncompressed_intra/bayer_debayer_check_pyav19.py` -> `bayer_debayer_check_pyav19.0.2.json`: results identical to the PyAV 18 / OpenCV 4.12 file except the OpenCV version string.
- The PyAV 19.0.2 `av/container/output.py` was read from the uv environment. The Matroska gate is at lines 166-171.

**Not re-checked here**
- FFmpeg `ffv1enc.c`, `matroskaenc.c`, `mjpegenc_common.c` and JFIF quotes: VERIFY_provenance re-checked them against downloads on 2026-11-09 and found matches.
- About 150 bench numbers: VERIFY_provenance matched them to the JSON. They stay contaminated lower bounds.
