# GF09: lossless intra on Quick Sync, and exactness of the NVENC lossless outputs (2026-11-10)

Functional only. No fps, durations or CPU were recorded (timing rule). Machine Gerald: Intel UHD 770, driver 32.0.101.7088; RTX 3070, driver 610.88 (`GF09_gpu_drivers.json`; `GF09_rows_nvenc_pyav19.0.2.json` `nvidia_smi_before`).

Paths are relative to `research/skellycam_recording/recording_upgrade/`. R = `results/uncompressed_intra/gapfill/`, S = `scripts/uncompressed_intra/gapfill/GF09/`.

**Files**
- Raw rows: `R/GF09_rows_qsv_pyav19.0.2.json`, `R/GF09_rows_nvenc_pyav19.0.2.json`. Merged with versions, options tried and Chromium results: `R/GF09_qsv_lossless.json`.
- Encoder AVOptions (static query of the wheel's own libavcodec): `R/GF09_avoptions_pyav19.0.2.json`.
- Chromium: `R/GF09_chromium_electron35.json`, `R/GF09_chromium_electron45.json`, test media `R/GF09_chromium_media.json`, and a check of the test media themselves, `R/GF09_chromium_media_check.json`.
- Scripts: `S/gf09_lossless_check.py` (`--part qsv|nvenc`), `S/probe_opts.py`, `S/prep_chromium.py`, `S/verify_chromium_media.py`, `S/chromium/{main.js,page.html,page.js}`, `S/summarize_gf09.py`.
- Versions: av 19.0.2 (libavcodec 63.1.102), numpy 2.2.6, Python 3.12.13 (each rows JSON head); Electron 35.7.5 (Chrome 134.0.6998.205), Electron 45.2.3 (Chrome 156.0.8078.80).

**Method (code)**
- Input: the 8 C930e YUY2 1080p corpus frames, looped to 300 frames as in the timed bench (`S/gf09_lossless_check.py`, `NFRAMES`, `fed[i % len(fed)]`). 720p NVENC cases use the bench's 720p source (decoded `c930e_720p_flash`).
- NV12 = `uintra_frames.derive('nv12')`; Bayer8 quad = `derive('bayer8_quad')` (synthetic Bayer, see uncompressed_intra FINDINGS §2.1).
- Exactness: every frame decoded with PyAV and compared per plane against the fed samples (max abs diff). "Data planes" = Y only for gray / Bayer inputs carried as Y + neutral chroma; Y, U, V otherwise.
- QSV: all-intra with `gop_size=1` (as `results/intra_compare/matched_settings.json`); CQP through `flags=+qscale`, `global_quality=QP*118`, `i_qfactor=1`, `i_qoffset=0` (K3 in `results/hw_accel_target/FINDINGS.md` §2.11). The effective encoder parameters were read back from qsvenc's verbose parameter dump (`libav_param_dump` per row).
- NVENC: the bench's own config entries (`scripts/uncompressed_intra/functional_matrix.py:83-84`: `preset p1`, `tune lossless`; `gop=1` is the `cfg()` default at `:53`), the bench's path chooser (`functional_matrix.choose_path`, called as in `scripts/uncompressed_intra/bench_intra.py:108`), `thread_count=1` as in the t1 bench (`bench_intra.py:146`). Cases: the five lossless `gpu` group cases at 1080p and 720p (`scripts/uncompressed_intra/bench_suite.py:57-61`), plus Bayer8 quad on both encoders at 1080p.

## 1. Quick Sync: no exact configuration exists (measured)

All rows: 300 frames, PyAV software decode, `R/GF09_rows_qsv_pyav19.0.2.json`. QPI and VDENC are the values the runtime reported back. PSNR-Y is background only.

| encoder | config | input (fed pix_fmt) | opens | QPI used | VDENC | exact /300 | max abs diff Y,U,V | PSNR-Y min (background) | profile | pix_fmt | KB/frame |
|---|---|---|---|---|---|---|---|---|---|---|---|
| h264_qsv | CQP QP 0 | NV12 (nv12) | yes | 1 | OFF | 0 | 2,1,1 | 64.84 | High | yuv420p | 532.9 |
| h264_qsv | CQP QP 0 | Bayer8 quad (nv12) | yes | 1 | OFF | 0 | 2,0,0 | 64.42 | High | yuv420p | 718.8 |
| h264_qsv | CQP QP 1 | NV12 | yes | 1 | OFF | 0 | 2,1,1 | 64.84 | High | yuv420p | 532.9 |
| h264_qsv | CQP QP 1 | Bayer8 quad (nv12) | yes | 1 | OFF | 0 | 2,0,0 | 64.42 | High | yuv420p | 718.8 |
| h264_qsv | CQP QP 1, low_power 1 | NV12 | yes | 10 | ON | 0 | 4,3,3 | 55.15 | High | yuv420p | 201.7 |
| h264_qsv | CQP QP 1, low_power 1 | Bayer8 quad (nv12) | yes | 10 | ON | 0 | 4,0,0 | 52.75 | High | yuv420p | 352.2 |
| h264_qsv | CQP QP 1, low_power 0 | NV12 | yes | 1 | OFF | 0 | 2,1,1 | 64.84 | High | yuv420p | 532.9 |
| h264_qsv | CQP QP 1, low_power 0 | Bayer8 quad (nv12) | yes | 1 | OFF | 0 | 2,0,0 | 64.42 | High | yuv420p | 718.8 |
| hevc_qsv | CQP QP 0 | NV12 | yes | 1 | OFF | 0 | 2,1,1 | 65.33 | Main | yuv420p | 437.6 |
| hevc_qsv | CQP QP 0 | Bayer8 quad (nv12) | yes | 1 | OFF | 0 | 2,0,0 | 65.42 | Main | yuv420p | 626.2 |
| hevc_qsv | CQP QP 0 | Bayer8 quad (vuyx, 4:4:4) | yes | 10 | ON | 0 | 3,0,0 | 52.61 | Rext | yuv444p | 306.7 |
| hevc_qsv | CQP QP 0 | camera YUY2 (yuyv422) | yes | 1 | OFF | 0 | 2,1,2 | 65.33 | Rext | yuv422p | 562.9 |
| hevc_qsv | CQP QP 1 | NV12 | yes | 1 | OFF | 0 | 2,1,1 | 65.33 | Main | yuv420p | 437.6 |
| hevc_qsv | CQP QP 1 | Bayer8 quad (nv12) | yes | 1 | OFF | 0 | 2,0,0 | 65.42 | Main | yuv420p | 626.2 |
| hevc_qsv | CQP QP 1 | Bayer8 quad (vuyx) | yes | 10 | ON | 0 | 3,0,0 | 52.61 | Rext | yuv444p | 306.7 |
| hevc_qsv | CQP QP 1 | camera YUY2 | yes | 1 | OFF | 0 | 2,1,2 | 65.33 | Rext | yuv422p | 562.9 |
| hevc_qsv | CQP QP 1, low_power 1 | NV12 | yes | 10 | ON | 0 | 4,3,3 | 55.08 | Main | yuv420p | 164.6 |
| hevc_qsv | CQP QP 1, low_power 1 | Bayer8 quad (nv12) | yes | 10 | ON | 0 | 3,0,0 | 52.61 | Main | yuv420p | 306.7 |
| hevc_qsv | CQP QP 1, low_power 1 | Bayer8 quad (vuyx) | yes | 10 | ON | 0 | 3,0,0 | 52.61 | Rext | yuv444p | 306.7 |
| hevc_qsv | CQP QP 1, low_power 1 | camera YUY2 | yes | 10 | ON | 0 | 4, chroma shape differs | - | **Main** | **yuv420p** | 164.6 |
| hevc_qsv | CQP QP 1, low_power 0 | NV12 | yes | 1 | OFF | 0 | 2,1,1 | 65.33 | Main | yuv420p | 437.6 |
| hevc_qsv | CQP QP 1, low_power 0 | Bayer8 quad (nv12) | yes | 1 | OFF | 0 | 2,0,0 | 65.42 | Main | yuv420p | 626.2 |
| hevc_qsv | CQP QP 1, low_power 0 | Bayer8 quad (vuyx) | **no**: "Invalid FrameType:0." / InvalidDataError on `avcodec_send_frame()` | - | - | - | - | - | - | - | - |
| hevc_qsv | CQP QP 1, low_power 0 | camera YUY2 | yes | 1 | OFF | 0 | 2,1,2 | 65.33 | Rext | yuv422p | 562.9 |
| hevc_qsv | CQP QP 1, transform_skip 1 | NV12 | yes | 1 | OFF | 0 | 2,1,1 | 65.33 | Main | yuv420p | 437.6 |
| hevc_qsv | CQP QP 1, transform_skip 1 | Bayer8 quad (nv12) | yes | 1 | OFF | 0 | 2,0,0 | 65.42 | Main | yuv420p | 626.2 |
| hevc_qsv | CQP QP 1, transform_skip 1 | Bayer8 quad (vuyx) | yes | 10 | ON | 0 | 3,0,0 | 52.61 | Rext | yuv444p | 306.7 |
| hevc_qsv | CQP QP 1, transform_skip 1 | camera YUY2 | yes | 1 | OFF | 0 | 2,1,2 | 65.33 | Rext | yuv422p | 562.9 |
| hevc_qsv | CQP QP 4, transform_skip 1 | NV12 | yes | 4 | OFF | 0 | 3,2,2 | 59.99 | Main | yuv420p | 332.7 |
| hevc_qsv | CQP QP 4, transform_skip 1 | Bayer8 quad (nv12) | yes | 4 | OFF | 0 | 3,0,0 | 59.25 | Main | yuv420p | 531.0 |
| hevc_qsv | CQP QP 4, transform_skip 1 | Bayer8 quad (vuyx) | yes | 10 | ON | 0 | 3,0,0 | 52.61 | Rext | yuv444p | 306.7 |
| hevc_qsv | CQP QP 4, transform_skip 1 | camera YUY2 | yes | 4 | OFF | 0 | 3,2,2 | 59.99 | Rext | yuv422p | 427.3 |
| hevc_qsv | CQP QP 1, profile rext | NV12 | yes | 1 | OFF | 0 | 2,1,1 | 65.33 | Rext | yuv420p | 437.6 |

- **measured:** 0 of 300 frames are exact in every one of the 32 QSV rows that opened. The smallest max abs diff is 2 on Y.
- **measured:** a requested QP 0 runs at QPI 1. QP 0 and QP 1 give identical sizes and errors.
- **measured:** with VDENC (`low_power=1`) the runtime raises QPI to 10 and reports `MinQPI: 10` (e.g. row `hevc_qsv__cqp_qp1_lp1__nv12`).
- **measured:** VUYX (4:4:4) input always ran with VDENC ON at QPI 10, even without `low_power=1`. With `low_power=0` it failed with "Invalid FrameType:0.".
- **measured:** `hevc_qsv` with `low_power=1` on camera YUY2 wrote HEVC **Main 4:2:0**, not 4:2:2, with no warning in the libav log. Without low_power the same input gives Rext 4:2:2.
- **measured:** the runtime reported `TransformSkip: ON` for every hevc_qsv row, whether or not `transform_skip=1` was set.
- **measured:** every QSV row is all-intra: 300/300 keyframe packets.
- **measured** (background): the closest QSV gets to lossless is about 65 dB PSNR-Y at QPI 1 (VME path), with max abs diff 2.

## 2. NVENC lossless, exact settings of timed items 35/56/57: exact over 300 frames (measured)

`R/GF09_rows_nvenc_pyav19.0.2.json`. Every case: 300/300 keyframe packets. KB/frame matches the timed bench to 0.1 KB for every timed stem (uncompressed_intra FINDINGS §3.1), so these are the same streams.

| case (timed bench stem) | fed pix_fmt | profile | pix_fmt | PyAV software decode | h264/hevc_cuvid | hwaccel cuda | hwaccel d3d11va | KB/frame |
|---|---|---|---|---|---|---|---|---|
| h264_nvenc lossless, nv12_1080p | nv12 | High 4:4:4 Predictive | yuv420p | 300/300 exact | 300/300 (nv12) | 300/300 (nv12) | fails: "Invalid data found when processing input" | 593.6 |
| h264_nvenc lossless, gray_1080p | yuv420p | High 4:4:4 Predictive | yuv420p | 300/300 | 300/300 | 300/300 | fails (same) | 446.9 |
| hevc_nvenc lossless, nv12_1080p | nv12 | Main | yuv420p | 300/300 | 300/300 | 300/300 | 300/300 (nv12) | 517.7 |
| hevc_nvenc lossless, p010le_1080p | p010le | Main 10 | yuv420p10le | 300/300 | 300/300 (p010le) | 300/300 | 300/300 | 1423.4 |
| hevc_nvenc lossless, bayer8_1080p (mosaic as Y) | yuv420p | Main | yuv420p | 300/300 | 300/300 | 300/300 | 300/300 | 1369.7 |
| h264_nvenc lossless, bayer8_quad_1080p (not timed) | yuv420p | High 4:4:4 Predictive | yuv420p | 300/300 | 300/300 | 300/300 | fails (same) | 772.6 |
| hevc_nvenc lossless, bayer8_quad_1080p (not timed) | yuv420p | Main | yuv420p | 300/300 | 300/300 | 300/300 | 300/300 | 685.1 |
| h264_nvenc lossless, nv12_720p | nv12 | High 4:4:4 Predictive | yuv420p | 300/300 | 300/300 | 300/300 | fails (same) | 202.5 |
| h264_nvenc lossless, gray_720p | yuv420p | High 4:4:4 Predictive | yuv420p | 300/300 | 300/300 | 300/300 | fails (same) | 173.4 |
| hevc_nvenc lossless, nv12_720p | nv12 | Main | yuv420p | 300/300 | 300/300 | 300/300 | 300/300 | 213.1 |
| hevc_nvenc lossless, p010le_720p | p010le | Main 10 | yuv420p10le | 300/300 | 300/300 | 300/300 | 300/300 | 622.3 |
| hevc_nvenc lossless, bayer8_720p | yuv420p | Main | yuv420p | 300/300 | 300/300 | 300/300 | 300/300 | 559.5 |

- **measured:** all 12 NVENC lossless configurations are bit-exact over 300 looped frames with PyAV software decode, and with NVDEC through `h264_cuvid` / `hevc_cuvid` and the `cuda` hwaccel.
- **measured:** the `d3d11va` hwaccel (`allow_software_fallback=False`) rejects every H.264 High 4:4:4 Predictive lossless stream. It decodes every HEVC lossless stream exactly.
- **measured:** PyAV reported `is_hwaccel=True` for the cuda and d3d11va rows, and they returned nv12/p010le frames (the software decoder returns yuv420p). NVDEC use was not checked with nvidia-smi (NOT VERIFIED beyond PyAV's flag).
- **code** (FFmpeg n9.0.2 `libavcodec/nvenc.c:1208-1209`): `if (ctx->flags & NVENC_LOSSLESS) { h264->qpPrimeYZeroTransformBypassFlag = 1;`. This is H.264's lossless (transform bypass) mode.
- **code** (same file, `:920-933`, `set_lossless`): `rc->rateControlMode = NV_ENC_PARAMS_RC_CONSTQP; ... rc->constQP.qpIntra = 0;`. It is called at `:1042-1043`; `tune lossless` sets `NVENC_LOSSLESS` at `:229-230`.
- **code** (same file, `:455-458`): if the GPU's `NV_ENC_CAPS_SUPPORT_LOSSLESS_ENCODE` capability is missing, the encoder warns "Lossless encoding not supported" and returns `AVERROR(ENOSYS)`.

## 3. Code citations (FFmpeg n9.0.2, tag object ce8f11b9, commit 946fcce07b6dcd0331c8cc609192aeff5e1924f8; fetched 2026-11-10 from `https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/<path>`, copies in the step3/GF09/src scratchpad folder)

| claim | file:line | exact text |
|---|---|---|
| No lossless option or code path in any QSV encoder file | `libavcodec/qsvenc.c`, `qsvenc.h`, `qsvenc_h264.c`, `qsvenc_hevc.c`, `qsv.c` | case-insensitive "lossless" occurs 0 times in all five files |
| CQP is selected by the qscale flag | `qsvenc.c:576`, `:592-594` | `int want_qscale = !!(avctx->flags & AV_CODEC_FLAG_QSCALE);` ... `rc_mode = MFX_RATECONTROL_CQP;` |
| QP from global_quality | `qsvenc.c:922-923` | `case MFX_RATECONTROL_CQP: quant = avctx->global_quality / FF_QP2LAMBDA;` |
| H.264/HEVC QP clipped to 0..51; QP 0 can be requested | `qsvenc.c:929-931` | `q->param.mfx.QPI = av_clip(quant * fabs(avctx->i_quant_factor) + avctx->i_quant_offset, 0, 51);` (QPP, QPB alike) |
| AV1 QP is 8-bit (0..255) | `qsvenc.c:925-927` | `q->param.mfx.QPI = av_clip_uintp2(quant * fabs(avctx->i_quant_factor) + avctx->i_quant_offset, 8);` |
| low_power option: tri-state, default auto | `qsvenc.h:65` | `{ "low_power", "enable low power mode(experimental: many limitations by mfx version, BRC modes, etc.)", ..., AV_OPT_TYPE_BOOL, { .i64 = -1}, -1, 1, VE}` |
| low_power mapping | `qsvenc.c:806-811` | `if (q->low_power == 1) { q->param.mfx.LowPower = MFX_CODINGOPTION_ON; } else if (q->low_power == -1) q->param.mfx.LowPower = MFX_CODINGOPTION_UNKNOWN; else ... MFX_CODINGOPTION_OFF;` |
| min/max QP options range | `qsvenc.h:115-120` | `{ "max_qp_i", ..., { .i64 = -1 }, -1, 51, VE}` ... `{ "min_qp_b", ..., -1, 51, VE}` |
| All-intra through gop_size | `qsvenc.c:815`, `:821` | `q->param.mfx.GopPicSize = FFMAX(0, avctx->gop_size);` ... `q->param.mfx.IdrInterval = q->idr_interval;` |
| hevc transform_skip option | `qsvenc_hevc.c:358`; `qsvenc.c:1166-1170` | `{ "transform_skip", "Turn this option ON to enable transformskip", ..., { .i64 = -1}, -1, 1, VE}`; `q->extco3.TransformSkip = q->transform_skip ? MFX_CODINGOPTION_ON : MFX_CODINGOPTION_OFF; else q->extco3.TransformSkip = MFX_CODINGOPTION_UNKNOWN;` |
| h264_qsv profiles: no 4:4:4 profile | `qsvenc_h264.c:152-156` | `unknown`, `baseline`, `main`, `high` |
| h264_qsv inputs: NV12 only | `qsvenc_h264.c:202` | `CODEC_PIXFMTS(AV_PIX_FMT_NV12, AV_PIX_FMT_QSV),` |
| hevc_qsv profiles include rext | `qsvenc_hevc.c:338-345` | `main`, `main10`, `mainsp`, `rext`, `scc` |
| hevc_qsv inputs incl. 4:2:2 and 4:4:4 | `qsvenc_hevc.c:399-402` | `AV_PIX_FMT_NV12, AV_PIX_FMT_P010, AV_PIX_FMT_P012, AV_PIX_FMT_YUYV422, AV_PIX_FMT_Y210, AV_PIX_FMT_QSV, AV_PIX_FMT_BGRA, AV_PIX_FMT_X2RGB10, AV_PIX_FMT_VUYX, AV_PIX_FMT_XV30` |
| hevc_qsv default GOP | `qsvenc_hevc.c:381` | `{ "g", "248" },` |
| NVENC lossless = transform bypass + QP 0 | `nvenc.c:229-230`, `:920-933`, `:1042-1043`, `:1208-1209` | quoted in §2 |
| NVENC lossless capability gate | `nvenc.c:455-458` | quoted in §2 |
| NVENC all-intra | `nvenc.c:1761-1766` | `if (avctx->gop_size > 0) { ... gopLength = avctx->gop_size; } else if (avctx->gop_size == 0) { frameIntervalP = 0; gopLength = 1; }` |

**source** (Intel oneVPL API header `api/vpl/mfxstructures.h`, tag v2.15.0, commit c45b5d786bf7cdabbe49ff1bab78693ad78feb78, lines 913-919, https://raw.githubusercontent.com/intel/libvpl/v2.15.0/api/vpl/mfxstructures.h, accessed 2026-11-10):
> "Quantization Parameter (QP) for I-frames for constant QP mode (CQP). Zero QP is not valid and means that the default value is assigned by the library. Non-zero QPI might be clipped to supported QPI range. ... @note In av1 design, valid range is 0 to 255 inclusive, and if QPI=QPP=QPB=0, the encoder is in lossless mode."

- The same text is on `main` (lines 955-961, commit 412c5cffe3022d5ebb8a955c3b30afe7bd2e3929, 2026-11-04).
- NOT VERIFIED: which libvpl version the PyAV wheel's `libvpl-*.dll` is. The quote is the API's documented contract, not that DLL's source.

**Static AVOptions query** (`R/GF09_avoptions_pyav19.0.2.json`; ctypes on the wheel's `av.libs` avcodec/avutil; no encoder opened)
- **measured:** h264_qsv has 48 private options and hevc_qsv 46. Neither has an option whose name or help text contains "lossless". The only quantiser options are `max_qp_*` / `min_qp_*` (range -1..51), plus hevc `transform_skip` (-1..1). `low_power` defaults to auto.
- **measured:** h264_nvenc / hevc_nvenc list `tune` choices `hq, ll, ull, lossless` (hevc also `uhq`).
- **measured:** the wheel has the decoders `h264_cuvid`, `hevc_cuvid`, `h264_qsv`, `hevc_qsv` (and others), and the hwdevices `cuda, dxva2, qsv, d3d11va, d3d12va, amf`.

## 4. Chromium (Electron 35 and 45): NVENC lossless files (measured)

`R/GF09_chromium_electron{35,45}.json`. Media: the first 60 packets of the two 300-frame NV12 1080p files, stream-copied to MKV and MP4. PyAV decodes frames 0, 1 and 7 of all four cuts exactly against the references (`R/GF09_chromium_media_check.json`). Codec strings come from the files' own avcC/hvcC: `avc1.F40028` and `hvc1.1.6.L120.90`. "Exact readback" = `VideoFrame.copyTo()` of frames 0, 1 and 7 compared byte for byte with the encoder's NV12 input (Y, U and V max abs diff 0). No QSV clip was tested, because none was exact.

| check | H.264 High 4:4:4 Predictive lossless, E35 / E45 | HEVC Main lossless, E35 / E45 |
|---|---|---|
| canPlayType mp4 + codecs | maybe / maybe | probably / probably |
| canPlayType x-matroska + codecs | "" / maybe | "" / probably |
| MSE isTypeSupported (mp4) | true / true | true / true |
| VideoDecoder.isConfigSupported no-preference / prefer-hardware / prefer-software | true / false / true (both) | true / true / false (both) |
| `<video>` MKV: plays to `ended`, error | yes, none (both) | yes, none (both) |
| `<video>` MP4: plays to `ended`, error | yes, none (both) | yes, none (both) |
| `<video>` decoder (media log) | FFmpegVideoDecoder, platform=false (both) | D3D11VideoDecoder, platform=true (both) |
| `<video>` decoded frames / dropped | 60/60, 0 dropped (all four runs) | 60/60; 1 dropped in E35 MKV and in E45 MP4, 0 in the other two |
| `<video>` seek + exact readback, frames 0/1/7 | 3/3 exact, NV12, frame index from timestamp = k (all four runs) | 3/3 exact, NV12 (all four runs) |
| WebCodecs no-preference: outputs, readback | 8/8, 3/3 exact (I420), FFmpegVideoDecoder (both) | 8/8, 3/3 exact (NV12), D3D11VideoDecoder (both) |
| WebCodecs prefer-hardware | configure fails: "OperationError: Unsupported configuration" (DecoderStatus 202) (both) | 8/8, 3/3 exact, D3D11VideoDecoder (both) |
| WebCodecs prefer-software | 8/8, 3/3 exact, FFmpegVideoDecoder (both) | configure fails: "Unsupported configuration" (both) |

- **measured:** both NVENC lossless formats play to the end in `<video>` (MKV and MP4) in E35 and E45, and return bit-exact YUV for 3 seeked frames.
- **measured:** Chromium decodes H.264 High 4:4:4 Predictive lossless **in software only** (FFmpegVideoDecoder; prefer-hardware is refused), and HEVC lossless **in hardware only** (D3D11VideoDecoder; prefer-software is refused) on this RTX 3070.
- **measured:** E35 `canPlayType` returns "" for `video/x-matroska`, yet the MKV files play from `src` in E35.
- **code** (`S/chromium/page.js`, `compareFrame`): readback checks the decoded YUV only. Rendering to a canvas or screen (YUV→RGB) was not compared.
- **measured** (count, not timing): one dropped frame occurred in 2 of 4 HEVC `<video>` runs, during real-time playback.

## 5. What this means for G4 and the hardware target

- **measured + code:** no lossless H.264 or HEVC configuration exists on Quick Sync through FFmpeg 9.0.2 / PyAV 19.0.2.
  - FFmpeg exposes no lossless switch for h264_qsv / hevc_qsv (code, §3).
  - The lowest CQP the runtime accepts is QPI 1 (VME) or 10 (VDENC): measured, §1.
  - The oneVPL API defines QP 0 as "not valid" for these codecs (source, §3).
  - Measured on UHD 770 (Raptor Lake-S), driver 32.0.101.7088.
  - **inferred:** other Intel generations behave the same through FFmpeg 9.0.2, because the missing switch is in FFmpeg's wrapper. Each generation's runtime minimum QP is NOT VERIFIED.
- **inferred** (from the bullet above): the G4 lossless formats (H.264 High 4:4:4 Predictive lossless, HEVC Main / Main 10 lossless) **do not meet the hardware target**. The target needs Quick Sync, and Quick Sync cannot write them.
  - They stay **hardware-encoded on NVIDIA only** (RTX 3070 measured).
  - They are CPU-fallback-class everywhere else.
- **source + code (lead only):** oneVPL documents AV1 CQP with QPI=QPP=QPB=0 as lossless, and FFmpeg passes AV1 QP 0 through (`qsvenc.c:925-927`).
  - av1_qsv does not open on the UHD 770 (`results/uncompressed_intra/qsv_recheck_pyav19.0.2.json`).
  - RTX 3000 has no AV1 encode (cross-reference `results/hw_accel_target/FINDINGS.md` headline / §3.1).
  - So AV1 lossless cannot be in the RTX 3000 + Intel intersection either (inferred). AV1 lossless on Arc / Meteor Lake and later: NOT VERIFIED (no hardware).
- **measured:** QSV's closest approach is hevc_qsv Rext 4:2:2 directly from camera YUY2 at QPI 1: about 65.3 dB PSNR-Y, max abs diff 2, 562.9 KB/frame. It is lossy. As a G4 record it is "near-lossless 4:2:2 in hardware on Intel", not exact.
- **measured:** a recorder must not combine `low_power=1` with YUY2 on hevc_qsv. It silently writes 4:2:0 Main (§1).
- **measured:** the timed NVENC lossless streams are bit-exact over all 300 frames. The HANDOFF §5 flag "uncompressed_intra has no lossless check in the timed bench" is closed for items 35/56/57's lossless rows.
- **measured:** hardware decode of NVENC lossless:
  - NVDEC (cuvid / cuda hwaccel) decodes both formats exactly.
  - D3D11VA rejects H.264 High 4:4:4 Predictive.
  - So on Windows, a D3D11-based player (Chromium) software-decodes H.264 lossless and hardware-decodes HEVC lossless.
- **inferred:** the earlier guess "HEVC lossless may be the one that hardware-decodes" holds for D3D11 / Chromium on this machine. NVDEC through FFmpeg decodes both.
- **NOT VERIFIED (no hardware):** lossless intra on AMD AMF and Apple VideoToolbox; HEVC lossless on RTX 3000 SKUs other than the RTX 3070; other Intel generations.

## 6. Proposed replacement text for `results/uncompressed_intra/FINDINGS.md`

Line numbers are those of the 2026-11-10 file (629 lines).

**Header, line 40.** Old:
> - **NVENC rows: hardware-encoded on NVIDIA** (measured, one RTX 3070). Whether the lossless formats (H.264 High 4:4:4 Predictive lossless, HEVC Main/Main 10 lossless) meet the hardware target is NOT VERIFIED, because lossless on QSV (requirement 3), AMF and VideoToolbox was not tested (§6).

New:
> - **NVENC rows: hardware-encoded on NVIDIA** (measured, one RTX 3070).
> - **The lossless formats (H.264 High 4:4:4 Predictive lossless, HEVC Main/Main 10 lossless) do not meet the hardware target** (inferred from GF09): Quick Sync cannot write them.
>   - measured (`gapfill/GF09_rows_qsv_pyav19.0.2.json`, UHD 770, driver 32.0.101.7088): 0/300 exact frames in all 32 h264_qsv/hevc_qsv rows that opened (CQP QP 0/1/4, low_power auto/on/off, transform_skip, rext, 4:2:0/4:2:2/4:4:4). QP 0 runs at QPI 1, VDENC at QPI 10.
>   - code (FFmpeg n9.0.2 qsvenc*.c): no lossless option.
>   - source (oneVPL `mfxstructures.h` v2.15.0:913): "Zero QP is not valid".
>   - AMF and VideoToolbox lossless: NOT VERIFIED (no hardware).

**§4.1, lines 452-454.** Old:
> - h264_nvenc lossless is coded High 4:4:4 Predictive; hevc_nvenc lossless is Main / Main 10 (§2.5). **inferred:** hardware decoders often stop at H.264 High, so HEVC lossless may be the one that hardware-decodes.
> - Hardware decode of either and threaded software decode were not benched (NOT VERIFIED), so **the H.264 vs HEVC choice is open**.
> - The QSV leg of the hardware target is NOT VERIFIED for lossless.

New:
> - h264_nvenc lossless is coded High 4:4:4 Predictive; hevc_nvenc lossless is Main / Main 10 (§2.5).
> - measured (`gapfill/GF09_rows_nvenc_pyav19.0.2.json`):
>   - NVDEC (h264_cuvid/hevc_cuvid, cuda hwaccel) decodes both exactly;
>   - D3D11VA rejects H.264 High 4:4:4 Predictive and decodes HEVC lossless exactly.
> - measured (`gapfill/GF09_chromium_electron{35,45}.json`): Chromium plays both to the end with exact YUV readback, with H.264 lossless in software (FFmpegVideoDecoder) and HEVC lossless in hardware (D3D11VideoDecoder).
> - Decode speed of either (hardware or threaded) was not timed, so **the H.264 vs HEVC choice is still open** on speed. HEVC is the one Chromium on Windows hardware-decodes.
> - **Not inside the hardware target:** QSV has no lossless H.264/HEVC mode (GF09, header). This path is NVIDIA-only.

**§5, lines 495-498.** Old:
> - **No lossless check in the timed bench.**
>   - Exactness is cited from functional files with 4 frames (matrix; step2 check), 8 frames (`ffv1_recheck` YUY2) or 1 frame (`ffv1_recheck` gray16le).
>   - FFV1 s24 on NV12 and Bayer8 (1080p) and the five 720p NVENC lossless rows are exact over 4 frames (`verify_method/exact_check_step2_pyav19.0.2.json`). The 720p hevc CQ row is lossy and unchecked.
>   - The timed 300-frame streams themselves were not compared against the source.

New:
> - **No lossless check inside the timed bench; the NVENC lossless streams were re-checked afterwards (GF09).**
>   - measured (`gapfill/GF09_rows_nvenc_pyav19.0.2.json`): all ten timed NVENC lossless configs (5 at 1080p, 5 at 720p) were re-encoded with the bench's own config entries, path chooser and t1. They are bit-exact over all 300 frames (software, cuvid and cuda decode), and KB/frame matches the timed JSON to 0.1 KB.
>   - The FFV1 and rawvideo timed streams were not re-checked over 300 frames. Their exactness is cited from functional files with 4 frames (matrix; step2 check), 8 frames (`ffv1_recheck` YUY2) or 1 frame (`ffv1_recheck` gray16le).
>   - The 720p and 1080p hevc CQ rows are lossy and unchecked.

**§6, line 522.** Old:
> - Exactness of the full 300-frame timed streams (functional checks use 1-8 frames).

New:
> - Exactness of the full 300-frame FFV1/rawvideo timed streams (functional checks use 1-8 frames). The NVENC lossless streams are exact over 300 frames (GF09).

**§6, lines 532-535.** Old:
> - Lossless intra on QSV, AMF (no AMD GPU) and VideoToolbox: NOT VERIFIED. So whether the lossless formats meet the hardware target is NOT VERIFIED.
>   - HEVC lossless on RTX 3000 SKUs other than this RTX 3070: NOT VERIFIED.
> - NVDEC / hardware decode or multi-threaded decode of NVENC lossless files (H.264 Hi444PP, HEVC Main lossless): not measured. "dec fps" is single-thread CPU decode.
> - Chromium playback of NVENC lossless files: NOT VERIFIED.

New:
> - Lossless intra on QSV: **answered, not available** (GF09; measured on UHD 770 only, other Intel generations NOT VERIFIED). Lossless on AMF (no AMD GPU) and VideoToolbox: NOT VERIFIED.
>   - HEVC lossless on RTX 3000 SKUs other than this RTX 3070: NOT VERIFIED.
> - Hardware or multi-threaded decode **speed** of NVENC lossless files: not measured. "dec fps" is single-thread CPU decode. Hardware decode **correctness** is measured (GF09: NVDEC exact for both; D3D11VA fails H.264 Hi444PP).
> - Chromium playback of NVENC lossless: answered for NV12 1080p in E35/E45 (GF09: plays, exact YUV for 3 frames). Gray / Bayer / P010 lossless files in Chromium, and canvas (RGB) fidelity: NOT VERIFIED.

**Also affected (suggested):**
- §2.11 lines 387-388, the NOT VERIFIED bullet on Chromium playback of NVENC lossless: replace with the GF09 Chromium result (§4 above).
- §2.7 line 238: add "300-frame exactness of the NVENC lossless configs: GF09".
- §4 item 10, line 487 ("no archive codec here plays in Chromium with verified pixels"): narrow it. NVENC lossless H.264/HEVC NV12 now has verified YUV readback (GF09). FFV1, rawvideo and Bayer still do not play.
- Verification block line 628: remove "lossless on QSV" and "Chromium playback of NVENC lossless" from Still NOT VERIFIED. Add "hardware/threaded decode speed of NVENC lossless".
