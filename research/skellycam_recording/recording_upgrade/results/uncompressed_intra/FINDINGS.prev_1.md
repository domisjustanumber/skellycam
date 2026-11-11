# uncompressed_intra (G4) - FINDINGS

Machine Gerald (i7-14700K, 28 logical CPUs; RTX 3070, driver 610.88), 2026-11-09. This file merges `NOTES.md` (functional tests), `bench/BENCH.md` and the raw bench JSON (`bench/*.json`, 147 case files). Every number was read from the raw result file named next to it.

Labels: **measured** (result file; path relative to `research/skellycam_recording/recording_upgrade/results/uncompressed_intra/` unless it starts with `research/`), **source** (primary source, quoted, accessed 2026-11-09), **code** (repo file:line), **inferred** (reasoning; kept short).

Units: KB = 1000 bytes of encoded payload per frame (packet bytes / packets, container overhead excluded). "cores/stream" = process CPU seconds per second of 30 fps video. t1 = `thread_count=1`; t0 = libav auto threads.

**Benchmark caveat.** The machine was busy: total CPU 50.4% before the run, 24.3-52.3% in 5-min re-checks, 13-99% during individual reps (measured: `bench/precheck_typeperf.csv`, `bench/precheck_typeperf_recheck_avgs.txt`, `system_cpu_percent_during_encode` per JSON). NVENC session count was 3 around two 720p GPU cases. All fps are lower bounds; t1 rows and rankings are more reliable than t0. Re-run idle before quoting capacity.

## 1. Questions answered
1. Which codecs store each uncompressed camera format (YUY2, NV12, GRAY8/16, P010, RGB, Bayer 8/12, packed RAW10/12) bit-exact and intra-only, natively or after an exact re-layout?
2. Which containers keep the pixel format and survive truncation?
3. How fast and how large is each option at 1080p/720p, per CPU core and on NVENC?
4. Bayer: raw mosaic, plane-split mosaic, or debayered RGB?
5. What can Chromium (Electron 35/45) play natively?
6. Do PyAV 19.0.2, OpenCV 5.0.0.93, Electron 45.2.3 add useful format support?

## 2. Findings

### 2.1 Inputs
- measured (`NOTES.md` §1; code `scripts/uncompressed_intra/uintra_frames.py`): YUY2 = the camera's own bytes (corpus `c930e_1080p_yuy2`, 8 frames). NV12, gray, gray16, P010, RGB, Bayer 8/12, quad split, RAW10/12-packed are derived from it; 720p YUY2 is derived from `c930e_720p_flash` JPEGs.
- code (`uintra_frames.py` docstring): >8-bit sources carry seeded low-bit noise, so compressed sizes are pessimistic (inferred).
- measured (`loose_ends_check.json`): camera YUY2 is limited range: c930e Y 18..234, C 115..151; c922 Y 16..235, C 95..181; 0 samples outside 16..235.
- measured (each bench JSON: `looped: true`, `unique_frames: 8`): 8 frames looped to 90 (24 slow codecs, 300 GPU) per rep.

### 2.2 Library capability and versions
- measured (`pyav_caps_18.0.0.json`, `pyav_caps_19.0.2.json`): PyAV 18.0.0 = libavcodec 62.28.102 (FFmpeg 8.1.2); PyAV 19.0.2 = libavcodec 63.1.102 (FFmpeg 9.0.2).
- measured (same): both lack libopenjpeg, libjxl, libaom-av1, librav1e, libsvtjpegxs encoders and JPEG XL / JPEG XS decoders.
- measured (same): only encoder pix_fmt differences 18->19: ffv1 gains `bayer_rggb16le`; h264/hevc/av1_nvenc gain `p012le`, `p212le`, `yuv444p12msble`.
- measured (`pyav_mux_acceptance_{18.0.0,19.0.2}.json`): PyAV refuses Matroska for ffvhuff, huffyuv, utvideo, magicyuv, jpegls, png, dnxhd; NUT and AVI accept them; same in both versions.
- source (PyAV 18.0.0 `av/container/output.py:112-116`, installed wheel): `if not lib.avformat_query_codec(self.ptr.oformat, codec.id, lib.FF_COMPLIANCE_NORMAL): raise ValueError(... "format does not support" ...)`.
- measured (`ffmpeg_cli_reference.json`): ffmpeg 9.0.2 CLI muxes utvideo (`ULY2`), ffvhuff (`FFVH`), magicyuv (`M8Y2`), jpegls (`MJLS`) into MKV, bit-exact. The refusal is PyAV's gate.

### 2.3 Pixel format -> codec (bit-exact)
Full matrix `functional_tables.md` (15 sources x 37 configs, 4 real 1080p frames; raw `functional_matrix_pyav{18.0.0,19.0.2}.json`).
- measured: no compressing encoder takes packed 4:2:2; all exact paths de-interleave to yuv422p (exact). Only rawvideo stores YUY2 as-is.
- measured: NV12 native in libx264, h264/hevc_nvenc; others need NV12->yuv420p (exact).
- measured: GRAY16 native in ffv1, ffvhuff, jpegls, jpeg2000; libx265 exact as gray12le; hevc_nvenc lossless not exact (yuv444p10le).
- measured: P010 exact natively only in hevc_nvenc lossless; others need shift + de-interleave to yuv420p10le (exact).
- measured: FFV1 with default GOP has non-keyframe packets (`ffv1_l1_gdefault.mkv`); every `-g 1` FFV1 config is all-keyframe.
- source (RFC 9043 §3.8.1.3, https://www.rfc-editor.org/rfc/rfc9043.txt, quote from `NOTES.md` §4, not re-fetched): "When the "keyframe" value ... is 1, all range coder state variables are set to their initial state."

### 2.4 Containers
- measured (`functional_tables.md`, `ffmpeg_cli_reference.json`): NUT keeps bayer_rggb8/16le (`[186]RG[8]`, `[186]RG[16]`), gray16le, rgb24, nv12 bit-exact; p010le reads back as rgb555le.
- measured: MKV rawvideo works only for yuyv422 (`YUY2`), nv12 (`NV12`), yuv420p, gray.
- source (FFmpeg n9.0.2 `libavformat/matroskaenc.c:2042-2043`): "Raw RGB is not supported Natively in Matroska, you can use AVI or NUT or".
- measured: `-allow_raw_vfw 1` returns Bayer16/gray16 as rgb555le (not exact).
- measured: AVI loses gray16le/p010le, returns rgb24 as bgr24, cannot decode Bayer; MOV returns gray as pal8, gray16 as rgb555be, cannot decode nv12/yuv420p/p010/Bayer.
- measured (50% truncation, 4-frame files): MKV/NUT/AVI decode 1-2 frames, all exact for lossless configs; all MOV/MP4 configs decode 0. Agrees with `research/frame_ring_buffer/prototypes/results/p11_crash_container.md`.

### 2.5 GPU encoders
- measured (matrix): h264_nvenc lossless gop 1 exact for nv12/yuv420p, gray (Y+neutral chroma), gbrp; hevc_nvenc lossless exact for nv12, p010le, gbrp.
- measured (matrix `libav_log`): h264/hevc_nvenc 4:2:2 "YUV422P not supported"; h264_nvenc "10 bit encode not supported"; av1_nvenc "Codec not supported"; hevc/av1_qsv "Error creating a MFX session: -9"; av1_amf "DLL amfrt64.dll failed to open"; av1_mf "could not find any MFT for the given media type".
- measured (`loose_ends_check.json`, CLI, 1 frame): nv16->h264/hevc_nvenc and nv12->av1_nvenc fail ("No capable devices found"); nv12->hevc_nvenc control rc 0; nvidia-smi 0 sessions before/after.
- source (FFmpeg n9.0.2 `libavcodec/nvenc.c:446-451`): `nvenc_check_cap(avctx, NV_ENC_CAPS_SUPPORT_YUV422_ENCODE)` ... "YUV422P not supported" (inferred: GPU capability, not FFmpeg limit).
- measured (`loose_ends_check.json`, read-only): Get-PnpDevice lists "Intel(R) UHD Graphics 770" Status Unknown; Win32_VideoController lists only Parsec and NVIDIA; `-init_hw_device qsv=q` fails "Failed to find d3d11va adapter by vendor id 0x8086". inferred: iGPU present but inactive.
- measured (matrix): hevc_nvenc 12-bit request produces yuv444p10le, not exact.

### 2.6 Bayer storage
- measured (`functional_tables.md`, PyAV 19, 1080p 12-bit RGGB, bit-exact): rawvideo 4147 KB; RAW12-packed rawvideo 3110; RAW12-packed FFV1 range 2467; mosaic gray16le FFV1 v3 2413; mosaic jpeg2000 1839; quad FFV1 v3 1620; quad jpegls 1601; FFV1 v4 native 1625; mosaic x265 gray12le 2819.
- measured (`ffmpeg_cli_reference.json`): libaom AV1 lossless mosaic gray12le 2136 KB, exact, all-keyframe.
- measured (`python_jpeg_libs_uv.json`, 1 frame, imagecodecs 2026.10.10): JPEG-LS 2505, J2K reversible 1748, JXL e3 2397 / e1 2767, SOF3 12-bit 2705, PNG 2938 KB, all exact.
- source (n9.0.2 `ffv1enc.c:921-927`): `case AV_PIX_FMT_BAYER_RGGB16: ... s->version = FFMAX(s->version, 4); s->bayer = 1;`.
- source (n9.0.2 `ffv1enc.c:652-653`): "Version 2 or 4 needed for requested features but version 2 or 4 is experimental and not enabled".
- source (n9.0.2 `ffv1enc.c:1694-1696`): "Bayer 2x2 RCT, based on: "Reversible color transform for Bayer color filter array images", S. Poomrittigul et al".
- source (n8.1.2 `ffv1enc.c`, cached): no `bayer`/`BAYER` string.
- source (RFC 9043 §1, from `NOTES.md` §6, not re-fetched): "This document defines versions 0, 1, and 3 of FFV1."
- measured (`ffv1_v4_cross_version_pyav18.0.0.json`): v4 Bayer written by ffmpeg 9.0.2 fails to open in FFmpeg 8.1.2 ("Invalid data found ... avcodec_open2"); v4/v3 gray16 decode exact.
- measured (`functional_tables.md`): PyAV 18's own v4 gray16/Bayer round trip decoded as grayf16le, not exact.
- measured (`bayer_debayer_check.json`): swscale demosaic keeps CFA samples exactly; after 8-bit yuv420p max error 365/4095 (43.52 dB) and 24/255 (43.23 dB). OpenCV `BayerBG2BGR*` matches RGGB (43.6-44.25 dB); `BayerRG2BGR*` 20.33-20.35 dB. Only 8-bit BG VNG exact; VNG fails on 12-bit (`depth == CV_8U`).
- measured (same): debayered RGB FFV1 3736 KB (12-bit), 940-1151 KB (8-bit) vs mosaic 2415/1079 and quad 1596/492 -> 0.87-1.55x mosaic, 1.9-2.3x quad (arithmetic).

### 2.7 Bench results (loaded machine; lower bounds)
From `bench/<config>__<source>_<res>__t<threads>__pyav<ver>.json`; median of 3 reps after a discarded warm-up.
- measured: YUY2 1080p >=30 fps on one core: rawvideo 366; ffvhuff 203; mjpeg q2 (lossy) 149; utvideo 99; magicyuv 97; dnxhr (lossy) 83; x264 qp0 75; FFV1 v3 rice 42-43 (0.69-0.70 cores/stream); FFV1 l1 43.
- measured: FFV1 range YUY2 1080p 27 (s24) / 29 (s4) fps t1, 1.10/1.00 cores/stream, 370/373 KB (21% smaller than 469-470).
- measured: FFV1 t0 138 fps (s4), 266 (s16, s24); level 1 stays 43; decode ~39-40 -> 417-443 fps.
- measured: smallest lossless YUY2 1080p: FFV1 range 370, rice 469-470, x264 qp0 581, jpeg2000 633, vp9 668, x265 702, utvideo 786, magicyuv 795, ffvhuff 1162, raw 4147 KB.
- measured: slow t1: jpeg2000 7 fps (4.14 cores/stream), prores 7, vp9 lossless 11 (48 t0), x265 lossless 21 at 11.99 cores/stream.
- inferred: x265 and svtav1 ignore thread_count=1 (~8.5 and ~10.9 busy cores).
- code (`scripts/uncompressed_intra/bench_intra.py:111-121,150-159`) + measured `prep_ms_per_frame`: de-interleave runs outside the timed loop; YUY2->yuv422p median 1.73 ms (1.46-3.69) at 1080p, 0.69 ms at 720p; NV12->yuv420p 0.37 ms. Quad split not timed.
- measured: NV12 1080p t1/t0: FFV1 s24 rice 54/326 fps, 383 KB; range 45/296, 306 KB; utvideo 159/896, 627 KB; svtav1 lossless 41/41 at 7.27 cores/stream, 545 KB.
- measured: Bayer12 FFV1 v3: mosaic 2349-2413 KB at 8-10 fps t1; quad 1625-1647 KB at 14-15 fps t1; quad s24 t0 107 fps (2.46 cores/stream).
- measured: PyAV 19 FFV1 v4 native Bayer: 1633 KB, 30 fps t1 (1.00 cores/stream), 94 t0, decode 29/330; v3 s4 quad same PyAV 16/53 fps, 1625 KB.
- measured: Bayer8: FFV1 s24 rice 50 fps t1, 990 KB; jpegls 31 fps, 1095 KB; ffvhuff 269 fps but 2238 KB > raw 2074.
- measured: NVENC 1080p: h264 lossless NV12 428 fps, 0.07 cores/stream, 594 KB; gray 472 fps, 447 KB; hevc lossless NV12 292, 518 KB; P010 155, 1423 KB; hevc CQ 431, 59 KB; sw decode hevc lossless 12-24 fps. 720p 327-876 fps.
- measured: 720p t1: FFV1 s24 117 fps, 0.24 cores/stream, 130 KB; utvideo 252; mjpeg 407, 46 KB.
- measured: PyAV 19 vs 18: identical sizes; fps within spread (FFV1 s4 43.1 vs 43.4; mjpeg 168 vs 149).
- measured (`bench/py_still__uv.json`, 16 frames x 3, thread pool): 1/8 workers: simplejpeg 4:2:2 204/991, 4:2:0 423/1921; cv2 YUY2->BGR->JPEG 196/758; JXL e1 Bayer12 mosaic 84/430 (2767 KB), quad 90/493 (1777 KB); 1 worker: SOF3 14, ljpeg 42, JPEG-LS 25, J2K 6, cv2 PNG 20 fps. inferred: all release the GIL (3.5-7.6x scaling).
- measured (`bench/debayer__pyav18.0.0_cv4.12.0.json`), 8/12-bit ms: OpenCV bilinear 0.96/1.31; EA 0.99/1.31; VNG 8.40/error; swscale 5.05/7.87.

### 2.8 JPEG from camera YUV
- measured (`python_jpeg_libs_uv.json`): simplejpeg 1.9.0 `encode_jpeg_yuv_planes` takes 4:2:2 planes, I420, Y-only; rejects interleaved NV12 UV.
- measured: PyTurboJPEG 2.6.1 unusable from pip alone (needs libjpeg-turbo >= 3.0).
- measured (`python_jpeg_libs_{uv,venv}.json`): cv2.imencode needs BGR first; no .jxl/.avif writer in 4.12.0 or 5.0.0.
- measured: simplejpeg q90 Y PSNR 52.92 dB; decoded as full-range RGB 27.74 dB vs limited-range BT.601 reference.
- source (n9.0.2 `mjpegenc_common.c:499`): "Non full-range YUV is non-standard, set strict_std_compliance to at most unofficial to use it."
- source (JFIF 1.02 p.3, https://www.w3.org/Graphics/JPEG/jfif3.pdf, from `NOTES.md` §7): "normalized so as to occupy the full 256 levels of a 8-bit binary encoding". inferred: limited-range YUV in JFIF without conversion shows raised blacks.

### 2.9 Codecs PyAV lacks (CLI)
- measured (`ffmpeg_cli_reference.json`): libjxl lossless exact for gray8 and Bayer-as-gray16; YUY2 via rgb24 not exact.
- measured (`loose_ends_check.json`): JPEG XL / JPEG XS refuse MKV ("No bmp codec tag found"), NUT ("No codec tag defined"), MOV ("Could not find tag ... not currently supported in container").
- measured (`ffmpeg_cli_reference.json`): libaom allintra lossless exact for yuv422p and gray12le; svtav1 lossless yuv420p exact; rav1e qp0 not lossless; libopenjpeg gray16/Bayer16 exact.

### 2.10 Chromium playback (shallow)
- measured (`chromium_check_electron35.json` E35.7.5/Chrome 134.0.6998.205; `chromium_check_electron45.json` E45.2.3/Chrome 156.0.8078.80): VP9 lossless 4:4:4/4:2:2, AV1 lossless 4:2:0/4:2:2/4:4:4/gray12, H.264 intra/lossless 4:2:0 and 4:2:2: load, draw, seek in both. HEVC: fails E35, plays E45. MJPEG (AVI/MKV), FFV1, rawvideo, ProRes: fail in both. JPEG XL still: E45 only; JPEG 2000: neither.
- measured: identical checksums VP9/AV1 lossless 4:2:2 (1968455) and 4:4:4 (1968484). E35 AV1 lossless 4:2:0 (1999082) differs from H.264 lossless 4:2:0 (2011651); E45 both 2011651 - cause NOT VERIFIED.
- inferred: Bayer streams display as grey mosaic; colour needs a WebGL demosaic.

## 3. Comparison tables

### 3.1 YUY2 1080p, PyAV 18.0.0
| config | exact | KB/f | MB/s @30 | t1 fps | t1 cores | t0 fps | dec t1/t0 | trunc ok | Chromium |
|---|---|---|---|---|---|---|---|---|---|
| rawvideo.nut | yes | 4147 | 124 | 366 | 0.08 | 409 | 795/733 | yes | fails (MKV) |
| ffvhuff .nut | yes | 1162 | 35 | 203 | 0.15 | 515 | 66/757 | yes | - |
| utvideo .avi | yes | 786 | 24 | 99 | 0.30 | 456 | 115/1009 | yes | - |
| magicyuv .avi | yes | 795 | 24 | 97 | 0.31 | 441 | 103/851 | yes | - |
| x264 qp0 .mkv | yes | 581 | 17 | 75 | 0.38 | 385 | 71/475 | yes | 4:2:0 lossless plays |
| FFV1 v3 s4 rice | yes | 469 | 14 | 43 | 0.69 | 138 | 40/430 | yes | fails |
| FFV1 v3 s24 rice | yes | 470 | 14 | 42 | 0.70 | 266 | 39/428 | yes | fails |
| FFV1 v3 s24 range | yes | 370 | 11 | 27 | 1.10 | 207 | 24/306 | yes | fails |
| vp9 lossless .webm | yes | 668 | 20 | 11 | 2.71 | 48 | 19/148 | yes | plays |
| x265 lossless | yes | 702 | 21 | 21 | 11.99 | 32 | 19/172 | yes | E45 only |
| jpeg2000 | yes | 633 | 19 | 7 | 4.14 | 19 | 7/32 | yes | - |
| mjpeg q2 | lossy | 121 | 3.6 | 149 | 0.20 | 158 | 274/306 | n/a | fails |
| dnxhr hq .mov | lossy | 918 | 28 | 83 | 0.36 | 159 | 177/1375 | 0 frames | - |
| prores hq .mov | lossy | 944 | 28 | 7 | 4.28 | 104 | 58/425 | 0 frames | fails |
| svtav1 crf30 p12 (4:2:0) | lossy | 25 | 0.75 | 266 | 1.23 | 259 | 189/1287 | n/a | plays |

### 3.2 Bayer 12-bit 1080p, bit-exact
| storage | KB/f | t1 fps | t1 cores | t0 fps | FFmpeg 8.1.2 reads |
|---|---|---|---|---|---|
| rawvideo bayer16 .nut | 4147 | 287 | 0.10 | 317 | yes |
| RAW12 packed rawvideo .nut | 3110 | 452 | 0.07 | not run | yes |
| mosaic gray16le FFV1 v3 s24 | 2349 | 10 | 3.03 | 76 | yes |
| quad FFV1 v3 s24 | 1647 | 15 | 2.00 | 107 | yes |
| quad FFV1 v3 s4 | 1625 | 14 | 2.07 | 48 | yes |
| quad jpegls .nut | 1605 | 20 | 1.50 | 242 | yes |
| quad ffvhuff .nut | 1829 | 171 | 0.18 | 447 | yes |
| FFV1 v4 native (PyAV 19, experimental) | 1633 | 30 | 1.00 | 94 | **no** |
| mosaic x265 gray12le | 2822 | 14 | 22.07 | 24 | yes |
| debayered RGB FFV1 (1 frame) | 3736 | not run | - | - | yes |

### 3.3 NV12 1080p, one stream
| config | KB/f | enc fps | cores/stream | Chromium |
|---|---|---|---|---|
| h264_nvenc lossless | 594 | 428 | 0.07 | plays |
| hevc_nvenc lossless | 518 | 292 | 0.07 | E45 only |
| FFV1 s24 rice | 383 | 54 t1 / 326 t0 | 0.56 / 0.73 | fails |
| utvideo | 627 | 159 t1 / 896 t0 | 0.19 / 0.26 | - |
| svtav1 lossless p12 | 545 | 41 | 7.27 | plays |
| av1_nvenc | - | fails to open | - | - |

### 3.4 Version bumps
| bump | adds for G4 |
|---|---|
| PyAV 18.0.0 -> 19.0.2 | experimental FFV1 v4 Bayer (unreadable by 8.1.2); NVENC 12-bit formats (unusable here); no libjxl/libaom/openjpeg; same sizes/speed |
| OpenCV 4.12.0 -> 5.0.0.93 | nothing |
| Electron 35.7.5 -> 45.2.3 | HEVC playback, JPEG XL stills; still no FFV1/MJPEG/rawvideo/ProRes |
| + imagecodecs 2026.10.10 | JXL, SOF3 12-bit, JPEG-LS, J2K from pip on Windows |

## 4. Implications for the plan
1. YUY2/NV12 archive: FFV1 v3, MKV, gop_size=1, slicecrc=1, 16-24 slices, rice, threads on (§2.3, §2.4, §2.7, §3.1). Range coder only if CPU is spare (+21% saving for ~1.1 cores/stream).
2. Budget the 1.73 ms/frame YUY2 de-interleave separately (§2.7).
3. CPU-light fallback: utvideo/ffvhuff in AVI/NUT (PyAV gate, §2.2; truncation-tolerant, §2.4).
4. Rawvideo only if disk allows: 124 MB/s per 1080p30 stream vs 481 MB/s minimum per-GiB sustained write in `research/frame_ring_buffer/prototypes/results/p12_disk_sustained.md` (inferred ~3 streams). MKV for YUY2/NV12, NUT for Bayer/gray16; never MOV/MP4 (§2.4).
5. NVENC lossless is not the G4 answer for 4:2:2 cameras (§2.5) and is H.264/HEVC (G7 conflict); valid for NV12 (§3.3).
6. Bayer: raw mosaic, 4-plane split, FFV1 v3, MKV, threads on (§3.2); not FFV1 v4 (§2.6); do not debayer before storage (§2.6); store CFA phase; OpenCV `COLOR_BayerBG2BGR` for RGGB preview, ~1-1.3 ms (§2.7).
7. Packed RAW10/12: unpack to 16-bit before compressing (§2.6).
8. G8 cannot be met by the archive codec (§2.10); a separate proxy or backend-decoded frames is needed (inferred; G8/G9 topics).
9. Lossy JPEG of YUV frames: simplejpeg from YUV planes, convert/flag range (§2.7, §2.8).
10. No version bump required for G4 (§3.4).

## 5. Not tested / limits / NOT VERIFIED
- Loaded machine; no idle re-run; NVENC shared around two 720p cases.
- Not benchmarked: NV12 1080p for 18/23 configs; bayer8_quad; RAW12-packed beyond rawvideo t1; 6/10 720p configs; Python stills at 4 workers/120 frames; debayer at 120 frames.
- BENCH.md says 141 cases; 147 case JSONs exist (12 GPU + 56 core 1080p + 49 Bayer + 16 720p + 14 PyAV 19).
- Quad-split cost NOT VERIFIED (not timed).
- Python-still CPU figures coarse (16 frames; repeated 0.146 suggests Windows CPU-time granularity, inferred); thread-pool start inside timed region (code `bench_py_still.py:112-118`).
- One camera, one scene, 4-8 real frames; all non-YUY2 formats derived; real Bayer statistics may differ.
- No multi-stream concurrency, 60 fps, long recordings, or AVI size-limit tests.
- QSV/AMF untestable; AV1 NVENC on newer GPUs NOT VERIFIED.
- Chromium check shallow (no frame-accurate seek/sync); E35 AV1-4:2:0 checksum difference unexplained.
- RFC 9043 and JFIF quotes taken from `NOTES.md`, not re-fetched; FFmpeg/PyAV quotes re-checked against cached n9.0.2/n8.1.2 sources and the PyAV 18.0.0 wheel.
- Unsaved NOTES CLI checks kept only where matrix JSON or `loose_ends_check.json` backs them; NVENC CLI `-g 1` failure dropped.
- Licensing (G7) out of scope (`results/licensing/`).

## 6. How to reproduce
From repo root; `S=research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra`.
```
.venv/Scripts/python.exe $S/probe_pyav_caps.py ; uv run --script $S/probe_pyav_caps.py
.venv/Scripts/python.exe $S/pyav_mux_acceptance.py ; uv run --script $S/pyav_mux_acceptance.py
.venv/Scripts/python.exe $S/functional_matrix.py ; uv run --script $S/functional_matrix.py
.venv/Scripts/python.exe $S/summarize_functional.py
.venv/Scripts/python.exe $S/ffmpeg_cli_reference.py
uv run --script $S/python_jpeg_libs.py --turbojpeg-dll "C:/Program Files/Audacity/turbojpeg.dll"
.venv/Scripts/python.exe $S/python_jpeg_libs.py
.venv/Scripts/python.exe $S/bayer_debayer_check.py
.venv/Scripts/python.exe $S/ffv1_v4_cross_version.py ; uv run --script $S/ffv1_v4_cross_version.py
.venv/Scripts/python.exe -I $S/loose_ends_check.py
.venv/Scripts/python.exe $S/make_chromium_samples.py
env -u ELECTRON_RUN_AS_NODE skellycam-ui/node_modules/electron/dist/electron.exe $S/chromium_check/main.js <media>/chromium_samples/manifest.json <results>/chromium_check_electron35.json   (repeat with Electron 45.2.3)
.venv/Scripts/python.exe $S/bench_suite.py --group core_1080p --reps 3   (also: bayer, gpu, core_720p, pyav19)
uv run --script $S/bench_py_still.py --frames 120 --workers 1,4,8
.venv/Scripts/python.exe $S/bench_debayer.py --frames 120
.venv/Scripts/python.exe $S/bench_summary.py ; .venv/Scripts/python.exe $S/bench_tables.py
.venv/Scripts/python.exe $S/bench_intra.py --config ffv1_l3_s24_crc_g1.mkv --source bayer12_quad --res 1080p --threads 0 --frames 90 --reps 3 --warmup-frames 10
```
Versions: PyAV 18.0.0 (FFmpeg 8.1.2) venv; uv/PyPI av 19.0.2, numpy 2.2.6, psutil 7.2.2, simplejpeg 1.9.0, PyTurboJPEG 2.6.1, imagecodecs 2026.10.10, opencv-python 5.0.0.93; ffmpeg 9.0.2 gyan full; Electron 35.7.5 / 45.2.3. FFmpeg sources: https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/<path> and /n8.1.2/.
----- END FINDINGS.md -----