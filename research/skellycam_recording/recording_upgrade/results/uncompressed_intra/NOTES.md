# uncompressed_intra (G4): uncompressed camera formats stored intra-only

Machine Gerald (i7-14700K, RTX 3070, driver 610.88), 2026-11-09. Functional tests only. **No timing, throughput or CPU numbers are reported here** because other agents shared the machine. The timing benches are written and smoke-tested; the bench manifest is at the end.

Labels: **measured** (a result file from this study, path given), **source** (primary source, quoted, accessed 2026-11-09), **code** (repo file:line), **inferred** (reasoning; kept short).

All paths are relative to `research/skellycam_recording/recording_upgrade/`. Scripts are in `scripts/uncompressed_intra/` and results in `results/uncompressed_intra/`. Media is written only under `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/uncompressed_intra/` and deleted after each test unless noted.

## 1. Inputs

| source key | how it was made | real or derived |
|---|---|---|
| yuyv422 | the camera's own YUY2 bytes, corpus `c930e_1080p_yuy2` (1920x1080) | real |
| uyvy422, yuv422p, nv16 | exact byte re-layout of the YUY2 frame | derived, reversible |
| nv12 / yuv420p | YUY2 chroma averaged over vertical pairs (4:2:2 to 4:2:0) | derived |
| gray | Y plane | derived |
| gray16le | `(Y<<4) OR 4 seeded noise bits`: 12-bit values in 16-bit LE | derived |
| p010le | 10-bit value `(8-bit<<2) OR 2 noise bits`, MSB-aligned | derived |
| rgb24 / bgr24 | BT.601 limited-range YUV to RGB in numpy | derived |
| bayer_rggb8 | RGGB mosaic sampled from rgb24 | derived |
| bayer_rggb16le | `(bayer8<<4) OR 4 noise bits`: 12-bit, low-aligned | derived |
| raw12_packed / raw10_packed | MIPI CSI-2 RAW12 (2 px in 3 B) / RAW10 (4 px in 5 B) packing, stored as a gray8 image W*1.5 / W*1.25 wide | derived |
| bayer8_quad / bayer16_quad | the mosaic split into 4 colour sub-images (R, G1, G2, B), tiled 2x2 | derived, reversible |
| 720p (benches only) | corpus `c930e_720p_flash` JPEGs decoded by PyAV to yuvj422p, then repacked exactly to YUY2 | derived |

- Derivation code: `scripts/uncompressed_intra/uintra_frames.py`. Its self-test checks that RAW10/RAW12 pack/unpack and the quad split/merge round-trip exactly.
- The synthetic noise bits make the >8-bit compressed sizes conservative. Noise-free padded data would flatter the lossless codecs (inferred). `--no-noise` regenerates without them.
- The camera YUY2 is limited range. measured: Y min/max over 8 frames is 18..234 (c930e) and 16..235 (c922). Command and output are in the session log; the one-liner is in section 10.

## 2. Library and encoder capability (PyAV 18.0.0 vs 19.0.2)

- measured `pyav_caps_18.0.0.json` / `pyav_caps_19.0.2.json`: PyAV 18.0.0 bundles FFmpeg 8.1.2 (libavcodec 62.28.102). PyAV 19.0.2 bundles FFmpeg 9.0.2 (libavcodec 63.1.102), the same libraries as the ffmpeg 9.0.2 CLI.
- measured (same files): neither PyAV wheel has **libjxl, libaom-av1, libopenjpeg, librav1e or libsvtjpegxs** encoders, and neither has a JPEG XL decoder. libsvtav1, libvpx-vp9, libdav1d, ffv1, ffvhuff, huffyuv, utvideo, magicyuv, jpegls, jpeg2000 (native), mjpeg, prores_ks, dnxhd, libx264/x265 and NVENC/QSV/AMF/MF are present in both.
- measured (same files): the only encoder pixel-format differences between 18 and 19 are that **ffv1 gains `bayer_rggb16le`**, and h264/hevc/av1_nvenc gain `p012le`, `p212le` and `yuv444p12msble`. Pix_fmt knowledge (nv12, yuyv422, uyvy422, bayer_*, p010le, y210le...) and container availability are identical.
- measured `pyav_mux_acceptance_{18.0.0,19.0.2}.json`: PyAV refuses Matroska for ffvhuff, huffyuv, utvideo, magicyuv, jpegls and png. It refuses MOV/MP4 for several of them, and refuses Matroska for dnxhd. NUT and AVI accept all of these. Both versions behave identically.
- source: PyAV wheel `av/container/output.py` (19.0.2: lines 166-170; 18.0.0: lines 112-116) gates `add_stream` with `avformat_query_codec(self.ptr.oformat, codec.id, lib.FF_COMPLIANCE_NORMAL)` and raises `"... format does not support ... codec"`.
- measured `ffmpeg_cli_reference.json`: the ffmpeg CLI does mux utvideo (tag ULY2), ffvhuff (FFVH), magicyuv (M8Y2) and jpegls (MJLS) into MKV, and decodes them bit-exact. The PyAV refusal is the PyAV gate, not a Matroska limit.

## 3. Which codecs take which pixel formats

Full matrix: `functional_tables.md`, generated from `functional_matrix_pyav{18.0.0,19.0.2}.json`. It covers 15 sources x 37 configs, with 4 real 1080p frames each.

Codes: **N** = native pix_fmt, bit-exact. **R** = exact numpy re-layout or re-tag, source recovered bit-exact. **L** = lossy. **!** = lossless config that was not exact. **-** = no exact path. **mux/enc/dec** = failure at that stage. The cells below are copied from `functional_tables.md`, PyAV 19.0.2.

| config | yuyv422 | nv12 | gray | gray16le | p010le | rgb24 | bayer8 | bayer12 (16le) | raw12 packed |
|---|---|---|---|---|---|---|---|---|---|
| rawvideo.nut | N | N | N | N | ! | N | N | N | N |
| rawvideo.mkv | N | N | N | enc | enc | enc | enc | enc | N |
| rawvideo.avi | N | N | N | ! | ! | ! | dec | dec | N |
| rawvideo.mov | N | dec | ! | ! | dec | N | dec | dec | ! |
| ffv1 v1 / v3 (g=1) | R | R | N | N | R | R | R | R (re-tag gray16le*) | N |
| ffv1 v4 experimental | R | R | N | N | R | R | R | N (bayer_rggb16le) | N |
| ffvhuff (nut) | R | R | N | N | R | enc | R | R | N |
| huffyuv (avi) | R | - | - | - | - | N | - | - | - |
| utvideo / magicyuv (avi) | R | R | R / N | - | - | R | R | - | R / N |
| jpegls (nut) | - | - | N | N | - | N | R | R | N |
| jpeg2000 dwt53 | R | R | N | N | R | N | R | R | N |
| png (nut) | - | - | N | - | - | N | R | - | N |
| libsvtav1 lossless | - | R | R | - | R | - | R | - | R |
| libvpx-vp9 lossless | R | R | R | - | - | R | R | - | R |
| libx264 qp0 | R | N | N | - | R | - | R | - | N |
| libx265 lossless | R | R | N | R | R | R | R | R | N |
| h264_nvenc lossless | enc | N | R | enc | enc | R | R | enc | R |
| hevc_nvenc lossless | enc | N | R | ! | N | R | R | ! | R |
| mjpeg / svtav1 crf / vp9 crf / x264 crf / prores / dnxhr | L | L | L | L | L | L | L/- | - | L/- |
| av1_nvenc, hevc/av1_qsv, av1_amf, av1_mf | enc | enc | enc | enc | enc | enc | enc | enc | enc |

\* FFV1 v1/v3 cannot take bayer_rggb16le natively. The mosaic is re-tagged as gray16le, which is exact in both PyAV versions (measured: matrix; `ffmpeg_cli_reference.json` `ffv1_l3_bayer16_as_gray16.mkv`).

Native vs conversion, per format:

- **YUY2/UYVY (packed 4:2:2)**: no compressing encoder accepts packed 4:2:2 directly. Every one needs a de-interleave to yuv422p (or nv16), which is an exact numpy shuffle. measured: matrix, path "numpy deinterleave", source recovered bit-exact. Only rawvideo stores YUY2 as is.
- **NV12**: native in libx264, h264/hevc_nvenc and QSV. Every other codec needs NV12 de-interleaved to yuv420p, which is exact (measured: matrix).
- **GRAY8**: native in ffv1, ffvhuff, magicyuv, jpegls, jpeg2000, png, x264 and x265. svtav1, vp9, utvideo and NVENC need Y plus neutral chroma, which is exact once the chroma is dropped (measured).
- **GRAY16 / Y16 (12-bit)**: native in ffv1, ffvhuff, jpegls and jpeg2000. libx265 takes it as gray12le, exact (measured). NVENC lossless is not exact (section 5).
- **P010**: native only in NVENC/QSV (hevc_nvenc lossless is exact). Other codecs need the shift and de-interleave to yuv420p10le, which is exact (measured).
- **RGB24/BGR24**: native in jpegls, png, jpeg2000 (rgb24) and huffyuv. FFV1 needs bgr0. utvideo, magicyuv, vp9 and NVENC need gbrp. All of these re-layouts are exact (measured).
- **Bayer**: see section 6.

## 4. Container findings (rawvideo)

- measured (matrix + `ffmpeg_cli_reference.json`): **NUT** stores bayer_rggb8 and bayer_rggb16le rawvideo with the pix_fmt preserved (tags `[186]RG[8]`, `[186]RG[16]`) and decodes bit-exact. NUT also preserves gray16le, rgb24 and nv12. It does **not** preserve p010le, which reads back as rgb555le.
- measured: **Matroska** rawvideo works only for formats with a native FourCC: yuyv422 (`YUY2`), nv12 (`NV12`), yuv420p and gray. gray16le, p010le, rgb24/bgr24 and Bayer are rejected.
- source `libavformat/matroskaenc.c` n9.0.2:2042-2043: "Raw RGB is not supported Natively in Matroska, you can use AVI or NUT or ... enable allow_raw_vfw".
- measured: with `-allow_raw_vfw 1`, Bayer16 and gray16 read back as rgb555le, so the pix_fmt is lost and the result is not exact.
- measured: **AVI** loses the pix_fmt for gray16le and p010le (both read back as rgb555le), returns rgb24 as bgr24, and cannot decode Bayer (error -129).
- measured: **MOV** returns gray as pal8 and gray16 as rgb555be, cannot decode nv12/yuv420p/p010/Bayer, and loses all frames when truncated ("moov atom not found").
- measured, truncation at 50 % of file size (4 frames; `functional_tables.md`): MKV, NUT and AVI keep every complete frame before the cut, and all those frames are bit-exact. MOV/MP4 (rawvideo, prores, dnxhd, x264 mp4, hevc_nvenc mp4) keep 0 frames.
  - This agrees with prior result `research/frame_ring_buffer/prototypes/results/p11_crash_container.md`. Crash tolerance is studied in depth by the G2 topic.
- measured: **FFV1 with the default GOP is not intra-only**. `ffv1_l1_gdefault.mkv` has packets that are not flagged keyframe, while every `-g 1` FFV1 config is all-keyframe.
- source RFC 9043 §3.8.1.3: "When the "keyframe" value ... is 1, all range coder state variables are set to their initial state." In other words, non-keyframes carry context state over, so FFV1 must be run with `gop_size=1` for independent frames (inferred from the quote plus the measurement).

## 5. GPU encoders on this machine (intra-only)

nvidia-smi `encoder.stats.sessionCount,utilization.gpu` was 0 sessions, 3-10 % around these tests. Per-run values are in `nvidia_smi_before/after` in the matrix JSON.

| encoder | result | evidence |
|---|---|---|
| h264_nvenc lossless, gop 1 | nv12/yuv420p bit-exact; gray via Y+neutral chroma exact; rgb via gbrp exact | measured: matrix |
| h264_nvenc 4:2:2 / 10-bit | open fails: "YUV422P not supported" / "10 bit encode not supported" | measured: matrix `libav_log` |
| hevc_nvenc lossless, gop 1 | nv12, p010le, gbrp exact | measured: matrix |
| hevc_nvenc 4:2:2 | open fails: "YUV422P not supported" | measured |
| hevc_nvenc 12-bit | yuv444p12msble requested, stream comes out yuv444p10le (Rext) and is not exact; 16-bit input loses its low bits | measured: matrix `!` cells (decoded yuv444p10le); CLI check (section 10) |
| av1_nvenc | open fails: "Codec not supported" | measured |
| hevc_qsv / av1_qsv | "Error creating a MFX session: -9" | measured: matrix |
| QSV device | "Failed to find d3d11va adapter by vendor id 0x8086" | measured (CLI, section 10) |
| av1_amf | "DLL amfrt64.dll failed to open" (no AMD GPU) | measured |
| av1_mf | "could not find any MFT for the given media type" | measured |

- source `libavcodec/nvenc.c` n9.0.2:428-452: these messages come from capability queries made to the GPU (`nvenc_check_cap(... NV_ENC_CAPS_SUPPORT_YUV422_ENCODE)` and similar). They describe this RTX 3070 and driver, not an FFmpeg limit.
- measured (read-only `Get-PnpDevice -Class Display`): "Intel(R) UHD Graphics 770" is listed with Status **Unknown**, next to the NVIDIA (OK) and Parsec adapters. `Win32_VideoController` lists only NVIDIA and Parsec.
  - inferred: the iGPU exists in the PnP database but is not active, so QSV cannot run as configured. This was not changed (BIOS and driver changes are out of scope).
- PyAV `gop_size=1` with NVENC opens fine (measured: matrix). The CLI `-g 1` on a 1-frame clip fails with "Gop Length should be greater than number of B frames + 1" even with `-bf 0`. measured: CLI, section 10. NOT VERIFIED for multi-frame CLI runs.

## 6. Bayer: raw vs packed vs debayered

| storage (1080p, 12-bit RGGB, noisy low bits) | bit-exact | KB/frame | raw/compressed | evidence |
|---|---|---|---|---|
| rawvideo bayer_rggb16le in NUT | yes | 4147 | 1.00 | measured: matrix |
| RAW12 packed bytes, rawvideo gray | yes | 3110 | 1.33 | measured |
| RAW12 packed bytes, FFV1 v3 range coder | yes | 2467 | 1.68 (vs 16-bit) | measured: `functional_tables.md` |
| mosaic as gray16le, FFV1 v3 | yes | 2413 | 1.72 | measured |
| mosaic as gray16le, jpeg2000 dwt53 (PyAV) | yes | 1839 | 2.25 | measured |
| **quad split as gray16le, FFV1 v3** | yes | 1620 | 2.56 | measured |
| quad split as gray16le, jpegls (PyAV) | yes | 1601 | 2.59 | measured |
| **bayer_rggb16le native, FFV1 v4 experimental (PyAV 19 / ffmpeg 9 only)** | yes | 1625 | 2.55 | measured |
| mosaic as gray12le, libaom AV1 lossless (CLI) | yes | 2136 | 1.94 | measured: `ffmpeg_cli_reference.json` |
| mosaic as gray12le, libx265 lossless | yes | 2819 | 1.47 | measured |
| mosaic, imagecodecs JPEG-LS / J2K reversible / JXL e3 / JPEG SOF3 12-bit | yes | 2505 / 1748 / 2397 / 2705 | | measured: `python_jpeg_libs_uv.json` (1 frame) |
| debayered RGB (swscale) as gbrp12le, FFV1 v3 | CFA samples kept | 3736 | 1.11 | measured: `bayer_debayer_check.json` |

8-bit Bayer:

- measured: the mosaic as gray in FFV1 v3 (rice coder) takes 1085 KB.
- measured: the **quad split in FFV1 v3 with the range coder takes 457 KB**. jpeg2000 on the mosaic takes 739 KB.
- measured `bayer_debayer_check.json`: debayered RGB (bgr0) in FFV1 takes 1151 KB. Raw-mosaic sizes in that file: bayer8 1079 KB, bayer8 quad 492 KB with the default coder.

Bayer notes:

- **Storing the raw mosaic losslessly and de-interleaving the four CFA planes first is the size winner among exact options.** FFV1 v3 on the quad layout matches FFV1 v4's native Bayer mode: 1620 vs 1625 KB (measured).
- source `libavcodec/ffv1enc.c` n9.0.2:921-927: native `AV_PIX_FMT_BAYER_RGGB16` forces `s->version = FFMAX(s->version, 4)`.
- source n9.0.2:652-653: "Version 2 or 4 needed for requested features but version 2 or 4 is experimental and not enabled", unless `strict=experimental`.
- source n9.0.2:1694-1696: the v4 Bayer path uses a reversible 2x2 colour transform ("Reversible color transform for Bayer color filter array images", Poomrittigul et al.).
- source RFC 9043 §1: "This document defines versions 0, 1, and 3 of FFV1." Version 4 is not in the RFC.
- measured `ffv1_v4_cross_version_pyav{18.0.0,19.0.2}.json`:
  - an FFV1 v4 Bayer file written by ffmpeg 9.0.2 **cannot be opened by PyAV 18 / FFmpeg 8.1.2** ("Invalid data found ... avcodec_open2(ffv1)");
  - v4 gray16 written by 9.0.2 does decode exact in 8.1.2;
  - PyAV 18's own v4 gray16 round trip came back as `grayf16le` and was not exact (matrix, PyAV 18.0.0 `!` cells).
  - inferred: v4 is not stable across FFmpeg versions, so use v3 with the quad split for archives.
- **Packed RAW10/RAW12** has no FFmpeg pix_fmt. The `ffmpeg -pix_fmts` listing (9.0.2) shows only `bayer_*8` and `bayer_*16le/be`, input-only ("I....").
  - measured: storing the packed bytes as gray8 is exact but compresses poorly (1.68x for RAW12 in FFV1).
  - inferred: unpacking to 16-bit before compression is better.
- **Debayering first**:
  - measured `bayer_debayer_check.json`: libswscale's interpolating demosaic keeps the original CFA samples exactly, so the mosaic is recoverable while the RGB stays lossless.
  - measured: once that RGB is converted to 8-bit yuv420p (what typical video encoders take), the re-sampled mosaic is off by up to 365/4095 (12-bit) or 24/255 (8-bit), with CFA PSNR about 43.5 dB. Sensor precision is lost.
  - measured: OpenCV's `COLOR_BayerBG2BGR*` is the code that matches this RGGB layout (CFA PSNR about 44 dB after yuv420p). `COLOR_BayerRG2BGR*` gives about 20 dB, the wrong phase. Only the 8-bit VNG output kept the CFA samples exactly; bilinear and EA did not (max error 37/255, 601/4095). VNG does not support 16-bit (error recorded).
  - Debayered RGB is 3 samples per pixel, so lossless storage takes 1.1-2.3x more bytes than the mosaic (table above).
- source `libswscale/bayer_template.c` n9.0.2: Bayer to RGB uses `BAYER_TO_RGB24_INTERPOLATE` / `BAYER_TO_RGB48_INTERPOLATE` (lines 71-203).

## 7. JPEG and other per-frame image encoders from Python

Results are in `python_jpeg_libs_uv.json` (isolated: simplejpeg 1.9.0, PyTurboJPEG 2.6.1, imagecodecs 2026.10.10, opencv-python 5.0.0.93) and `python_jpeg_libs_venv.json` (OpenCV 4.12.0).

| path | takes camera YUV without RGB? | output | evidence |
|---|---|---|---|
| simplejpeg.encode_jpeg_yuv_planes(Y,U,V) | yes: YUY2 de-interleaved to 4:2:2 planes; I420 planes; Y only | SOF0, sampling 2x1/1x1/1x1 (4:2:2) or 2x2 (4:2:0); interleaved NV12 UV rejected ("both U and V planes must be given") | measured |
| PyTurboJPEG encode_from_yuv | API yes, but needs an external libturbojpeg ≥ 3.0 | not usable from pip alone: "Unable to locate turbojpeg library automatically"; with Audacity's turbojpeg.dll (libjpeg-turbo 2.1.5): "PyTurboJPEG 2.0 requires libjpeg-turbo 3.0 or later" | measured |
| cv2.imencode .jpg | no: needs `cvtColor(YUV2BGR_YUY2)`; a 2-channel YUYV array fails "channels == 1 or 3 or 4" | `IMWRITE_JPEG_SAMPLING_FACTOR_422` gives 4:2:2 | measured (4.12.0 and 5.0.0) |
| cv2 .jxl / .avif writers | no writer in either wheel (`haveImageWriter` false; encode error) | | measured |
| imagecodecs.jpeg8_encode lossless=True bitspersample=12 | n/a (Bayer/gray) | **SOF3 lossless JPEG, 12-bit, bit-exact** (libjpeg-turbo 3.2.0) | measured |
| imagecodecs.jpeg8_encode colorspace=YCbCr | interleaved 4:4:4 YCbCr only (chroma must be upsampled) | 4:2:2 SOF0 | measured |
| imagecodecs jpegls / jpeg2k reversible / jpegxl lossless / png / ljpeg | Bayer12 and gray8 | all bit-exact | measured |
| ffmpeg mjpeg (PyAV) from yuv422p | yes (after de-interleave) | needs `strict=unofficial` for non-full-range yuv422p | measured + source below |

- source `libavcodec/mjpegenc_common.c` n9.0.2:499: "Non full-range YUV is non-standard, set strict_std_compliance to at most unofficial to use it."
- source JFIF 1.02 (https://www.w3.org/Graphics/JPEG/jfif3.pdf, p.3): Y, Cb and Cr "are normalized so as to occupy the full 256 levels of a 8-bit binary encoding".
- measured: simplejpeg q90 keeps the Y samples (Y-plane PSNR 52.9 dB vs input). Decoded to RGB as full range, it is 27.7 dB from a limited-range BT.601 reference.
  - inferred: putting the camera's limited-range YUV planes into a JFIF JPEG without a range conversion or flag makes standard decoders show raised blacks and lowered contrast. The recorder must either scale to full range or record the range in metadata.
- simplejpeg exposes no decode-to-YUV-planes function, so the Y comparison above used imagecodecs `jpeg8_decode(outcolorspace="YCbCr")`.

## 8. ffmpeg CLI reference (codecs PyAV lacks)

Results are in `ffmpeg_cli_reference.json` (ffmpeg 9.0.2; 4 real 1080p frames).

- libjxl lossless (effort 1):
  - gray8 and Bayer12-as-gray16le are bit-exact; yuyv to rgb24 is not exact.
  - libjxl takes rgb24, rgba, rgb48, gray and gray16 only (`ffmpeg -h encoder=libjxl`). YUV camera frames need an RGB conversion first.
  - **JPEG XL cannot be muxed into MKV, NUT or MOV in ffmpeg 9.0.2.** MKV: "codec jpegxl is not supported by this format". NUT: "No codec tag defined". MOV: "Could not find tag for codec jpegxl". Only a per-frame `.jxl` sequence (image2) works. measured (commands in section 10).
- libaom AV1 `-usage allintra -crf 0 -aom-params lossless=1`:
  - yuv422p (profile "Professional") and gray12le (Bayer) are bit-exact and all-keyframe.
  - `-g 1` together with `-usage allintra` makes the encoder fail to open, and `-cpu-used 9` is out of range [0-8]. measured: earlier runs, errors recorded in the session.
- libsvtav1 lossless (`lossless=1:keyint=1`), yuv420p: bit-exact. libsvtav1 accepts only yuv420p and yuv420p10le (`-h encoder`), so it has no 4:2:2 and no gray.
- librav1e qp 0 is not lossless (measured: not bit-exact).
- libopenjpeg (default settings) on gray16 / Bayer16 is bit-exact. PyAV's native jpeg2000 with `pred=dwt53` is also bit-exact.
- libx264 qp 0 on yuv422p (profile "High 4:4:4 Intra") and libx265 lossless on gray12le are bit-exact.
- libsvtjpegxs: there is no `-bpp` option (bit rate is set with `-b:v`). JPEG XS cannot be muxed into MKV/NUT/MOV in 9.0.2 ("codec jpegxs is not supported by this format", "No codec tag defined", "Could not find tag for codec jpegxs"). measured (section 10).

## 9. Chromium native playback (cheap check; another topic goes deep)

Results are in `chromium_check_electron35.json` (Electron 35.7.5 / Chrome 134.0.6998.205) and `chromium_check_electron45.json` (Electron 45.2.3 / Chrome 156.0.8078.80).

Method: 8-frame 1080p samples from `make_chromium_samples.py`. Each `<video>` must reach `loadeddata`, draw a non-black first frame to a canvas, then seek to frame 5 and draw a different picture. Each `<img>` must decode.

| sample | E35 (Chrome 134) | E45 (Chrome 156) |
|---|---|---|
| VP9 lossless 4:4:4 / 4:2:2 (WebM), VP9 intra 4:2:0 | plays, seeks | plays, seeks |
| AV1 intra 4:2:0 (svt, MP4/WebM), AV1 lossless 4:2:0 / 4:2:2 / 4:4:4 / **gray 12-bit Bayer** (libaom, MP4) | plays, seeks | plays, seeks |
| H.264 intra 4:2:0, H.264 lossless 4:2:0, H.264 intra 4:2:2 | plays (canPlayType "maybe" for lossless/4:2:2) | same |
| HEVC intra 4:2:0 | **fails** (DEMUXER_ERROR_NO_SUPPORTED_STREAMS) | plays |
| MJPEG (AVI/MKV), FFV1, rawvideo, ProRes | fail (demuxer: no supported streams / could not open) | fail |
| JPEG XL still (lossless gray16, lossy RGB) | not decoded | **decoded** |
| JPEG 2000 still | not decoded | not decoded |
| PNG 16-bit gray, JPEG 4:2:2, AVIF, WebP lossless | decoded | decoded |

- measured: identical canvas checksums for VP9-lossless-4:2:2 and AV1-lossless-4:2:2 (1968455), and for 4:4:4 (1968484), in both Electrons.
  - inferred: Chromium decodes these lossless streams to the same pixels.
- inferred: a Bayer stream that "plays" shows the grey mosaic, not a colour image. The UI would need a WebGL demosaic to show colour.

## 10. Commands used

```
# capability probes
.venv/Scripts/python.exe scripts/uncompressed_intra/probe_pyav_caps.py ; uv run --script scripts/uncompressed_intra/probe_pyav_caps.py
.venv/Scripts/python.exe scripts/uncompressed_intra/pyav_mux_acceptance.py ; uv run --script scripts/uncompressed_intra/pyav_mux_acceptance.py
# functional matrix (4 frames, all sources x configs) and tables
.venv/Scripts/python.exe scripts/uncompressed_intra/functional_matrix.py ; uv run --script scripts/uncompressed_intra/functional_matrix.py
.venv/Scripts/python.exe scripts/uncompressed_intra/summarize_functional.py
# CLI reference, Python image libs, Bayer, cross-version, Chromium
.venv/Scripts/python.exe scripts/uncompressed_intra/ffmpeg_cli_reference.py
uv run --script scripts/uncompressed_intra/python_jpeg_libs.py --turbojpeg-dll "C:/Program Files/Audacity/turbojpeg.dll"
.venv/Scripts/python.exe scripts/uncompressed_intra/python_jpeg_libs.py
.venv/Scripts/python.exe scripts/uncompressed_intra/bayer_debayer_check.py
.venv/Scripts/python.exe scripts/uncompressed_intra/ffv1_v4_cross_version.py ; uv run --script scripts/uncompressed_intra/ffv1_v4_cross_version.py
.venv/Scripts/python.exe scripts/uncompressed_intra/make_chromium_samples.py
env -u ELECTRON_RUN_AS_NODE skellycam-ui/node_modules/electron/dist/electron.exe scripts/uncompressed_intra/chromium_check/main.js <media>/chromium_samples/manifest.json <repo>/results/uncompressed_intra/chromium_check_electron35.json
(same with the shared Electron 45.2.3 electron.exe -> chromium_check_electron45.json)
```

All commands are run from the repo root, with the `research/skellycam_recording/recording_upgrade/` prefix on the script and result paths.

Manual one-off checks:

- Run in the scratchpad on a 320x240 random 12-bit clip; outputs were read in the session and are quoted above, not saved as result files.
- `ffmpeg ... -pix_fmt nv16 -c:v h264_nvenc/hevc_nvenc` gave "YUV422P not supported". `-c:v av1_nvenc` gave "Codec not supported".
- `ffmpeg -init_hw_device qsv=q` gave "Failed to find d3d11va adapter by vendor id 0x8086".
- `-c:v hevc_nvenc -tune lossless -pix_fmt yuv444p12msble` gave a yuv444p10le Rext stream that was not exact.
- libjxl and libsvtjpegxs to .mkv/.nut/.mov gave the mux errors quoted in section 8.
- FFV1 Bayer `-level 1/3/4` without `-strict experimental` gave the experimental error. `-level 4 -strict experimental` decoded bit-exact.
- YUY2 range: a numpy min/max over the corpus Y samples (code inline in the session).

Third-party downloads (uv cache, PyPI; exact pins): av 19.0.2, numpy 2.2.6, psutil 7.2.2, simplejpeg 1.9.0, PyTurboJPEG 2.6.1, imagecodecs 2026.10.10, opencv-python 5.0.0.93, pypdf 6.1.1 (used only to read the JFIF PDF). FFmpeg sources for citation: `https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/<path>` and `/n8.1.2/` (scratchpad `uncompressed_intra/src/`). JFIF: https://www.w3.org/Graphics/JPEG/jfif3.pdf. RFC 9043: https://www.rfc-editor.org/rfc/rfc9043.txt.

## 11. Version bumps (user allows them for better format support)

- PyAV 18.0.0 to 19.0.2 adds:
  - native FFV1 Bayer (but v4 is experimental and not readable by FFmpeg 8.1.2);
  - NVENC 12-bit formats (unusable on the RTX 3070, section 5).
  - It adds no libjxl, libaom or openjpeg. measured: section 2. Not needed for G4 if FFV1 v3 with the quad split is used (inferred).
- opencv-python 4.12.0 to 5.0.0.93 adds nothing for this topic: no YUV-input JPEG and no JXL/AVIF writer (measured).
- Electron 35.7.5 to 45.2.3 adds JPEG XL still decode and HEVC playback on this machine (measured). Neither version plays FFV1, MJPEG or rawvideo.
- imagecodecs 2026.10.10 (not currently a dependency) is the only pip route found that gives JPEG XL, lossless JPEG (SOF3 12-bit), JPEG-LS and J2K from Python on Windows without extra DLLs (measured).

## 12. Limits

- Only 4 real 1080p frames go through the matrix, and 8 into the samples. Sizes come from these frames: one camera (C930e), one scene. Sizes for >8-bit derived sources depend on the synthetic noise bits.
- Bayer, NV12, P010, gray16 and RGB inputs are derived, not captured, so a real sensor's CFA statistics may differ. inferred: real Bayer has stronger inter-channel differences than a mosaic resampled from 4:2:2 JPEG-era YUV.
- The Chromium check is shallow: hidden window, no presentation timing, no frame-accurate seek test. That belongs to another topic.
- QSV/AMF could not be tested (no active Intel iGPU, no AMD GPU). AV1 NVENC needs a newer NVIDIA generation, NOT VERIFIED here.
- Licensing and royalty status of each codec (G7) is out of scope here. See `results/licensing/`.
- No timing numbers. All of them are deferred to the benches below.

## 13. Benchmarks to run later (quiet machine, one at a time)

Run from the repo root. Each case writes JSON to `results/uncompressed_intra/bench/`. When all runs are done, run `bench_summary.py`, which writes `bench/bench_summary.md`.

Before each GPU run, make sure Parsec and Sunshine are idle; nvidia-smi is recorded per case.

Frames are the 8 real frames, looped to 300 (90 for the slow codecs). Each case records threads 1 and threads 0 (libav auto). FFV1 threading is slice-based, so compare the s4, s16 and s24 configs.

| id | priority | command (from repo root) | est. min | purpose |
|---|---|---|---|---|
| core_1080p | 1 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/bench_suite.py --group core_1080p` | 50 | encode fps (1 thread / all threads), CPU per stream, bytes/frame, decode fps: 23 configs x {real YUY2, NV12} 1080p |
| bayer_1080p | 1 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/bench_suite.py --group bayer` | 35 | the same metrics for Bayer 12-bit (mosaic, quad split), Bayer 8-bit (mosaic, quad) and RAW12-packed, 1080p |
| gpu_nvenc | 1 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/bench_suite.py --group gpu` | 6 | NVENC lossless/CQ intra (NV12, P010, gray, Bayer8) at 1080p and 720p; nvidia-smi recorded per case |
| core_720p | 2 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/bench_suite.py --group core_720p` | 15 | 10 configs x {YUY2, NV12} 720p (from real JPEGs) |
| pyav19 | 2 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/bench_suite.py --group pyav19` | 8 | the same key configs under PyAV 19.0.2 (uv), including FFV1 v4 native Bayer vs v3 quad split |
| py_still | 2 | `uv run --script research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/bench_py_still.py --frames 120 --workers 1,4,8` | 12 | simplejpeg YUV planes, cv2 via BGR, imagecodecs lossless JPEG/JPEG-LS/J2K/JXL/PNG on Bayer12; GIL scaling across workers |
| debayer | 3 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/bench_debayer.py --frames 120` | 2 | ms/frame for swscale vs OpenCV bilinear/EA/VNG demosaic, 8- and 12-bit |
| summary | 1 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/bench_summary.py` | 1 | aggregate every bench JSON into bench/bench_summary.md |

Single cases can be run directly, for example `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/bench_intra.py --config ffv1_l3_s24_crc_g1.mkv --source bayer12_quad --res 1080p --threads 0`. Use `--list` to see config ids. Use `bench_suite.py --dry-run` to print every command.

Bench rules:

- Each case JSON records `system_cpu_percent_1s_before/after`. Discard cases where the before value shows load.
- Smoke tests: each bench script was run with 2-10 frames and its output deleted. The scripts work; the numbers were not kept.
- Kept media, for the Chromium deep-dive topic: `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/uncompressed_intra/chromium_samples/`, which has 25 samples plus `manifest.json`, including the full ffmpeg command for each sample.
