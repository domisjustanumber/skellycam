# GF06: AMF and VideoToolbox, all-intra and constant-QP/quality (code + vendor docs)

Gap-fill for hw_accel_target §3.2/§3.3 (and gpu_encode I6). Date 2026-11-10. Machine Gerald has no AMD or Apple hardware, so **nothing here was run on AMF or VideoToolbox hardware**. No timing.

Labels:
- **[code]** FFmpeg tag `n9.0.2` (commit `946fcce07b6dcd0331c8cc609192aeff5e1924f8`), `libavcodec/<file>:<line>`. Verbatim excerpts: `GF06_sources/ffmpeg_n9.0.2_amf_excerpts.md`, `..._videotoolboxenc_excerpts.md`, `..._generic_opts_excerpts.md`.
- **[source]** vendor text, accessed 2026-11-10, quoted verbatim:
  - AMD: AMF SDK tag `v1.5.3` (commit `57ee0cfb0e1a08d9041f77435653794c1b012be0`), `amf/doc/AMF_Video_Encode_API.md` (H264DOC), `amf/doc/AMF_Video_Encode_HEVC_API.md` (HEVCDOC), headers `VideoEncoderVCE.h` / `VideoEncoderHEVC.h`. Excerpts: `GF06_sources/amf_sdk_v1.5.3_excerpts.md`.
  - Apple: docs JSON endpoint `https://developer.apple.com/tutorials/data/documentation/videotoolbox/<symbol>.json` (APPLEDOC, Apple-hosted). Header-only text comes from `VTCompressionProperties.h`, macOS 15.5 SDK, via the third-party mirror `alexey-lysiuk/macos-sdk@896cd40d` (VTH, **not Apple-hosted**, labelled [source (SDK header via mirror)]). Excerpts: `GF06_sources/apple_videotoolbox_excerpts.md`.
- **[measured]** `GF06_pyav_options.json` (static PyAV 19.0.2 query; script `scripts/hw_accel_target/gf06_pyav_amf_vt_options.py`; no encoder opened).
- **[inferred]** marked; kept minimal.
- Hashes and URLs: `GF06_sources/FETCH_MANIFEST.txt`.

## 1. Version check

- [measured] PyAV 19.0.2 reports `ffmpeg_version_info` "9.0.2", libavcodec 63.1.102, on Windows-11-10.0.26300 (`GF06_pyav_options.json`).
- [source] Tag `n9.0.2` exists: `git ls-remote` gives tag object `ce8f11b9…` → commit `946fcce0…`; its `RELEASE` file reads `9.0.2`. No fallback to `release/9.0` was needed.

## 2. Static PyAV 19.0.2 query on Gerald (win_amd64 wheel)

| encoder | in wheel | relevant private AVOptions (default) | context after alloc (codec defaults) |
|---|---|---|---|
| h264_amf | yes | `rc` (-1 = unknown → auto), `qp_i`/`qp_p`/`qp_b` (-1, range -1..51), `forced_idr` (false), `bf` (-1, B_PIC_PATTERN), `max_b_frames` (-1, consecutive B), `header_spacing` (-1), `usage` (-1), `quality`/`preset` (-1), `qvbr_quality_level` (-1), `pa_adaptive_mini_gop` (auto) | gop_size -1, max_b_frames 0, qmin -1, qmax -1, global_quality 0 |
| hevc_amf | yes | `rc` (-1), `qp_i`/`qp_p` (-1), `min_qp_i`/`max_qp_i` (-1), `gops_per_idr` (1), `forced_idr` (false), `header_insertion_mode` (-1), `usage` (-1), `quality`/`preset` (-1); **no `bf`/`max_b_frames` option** | gop_size -1, max_b_frames 0, qmin -1, qmax -1, global_quality 0 |
| h264_videotoolbox | **no** (UnknownCodecError) | — | — |
| hevc_videotoolbox | **no** (UnknownCodecError) | — | — |

- [measured] AMF pixel formats in this wheel: nv12, yuv420p, d3d11, dxva2_vld, p010le, amf and RGB variants; no 4:2:2 input (`GF06_pyav_options.json`).
- [measured, earlier] The VideoToolbox encoders exist only in the macOS wheels (`R/gpu_encode/wheel_hw_codecs.md` lines 7-8: macosx_11_0_x86_64 and macosx_14_0_arm64 list h264/hevc/prores_videotoolbox). Their options can't be listed from Windows; section 4 takes them from code.
- [measured] The generic options `i_qfactor` (-0.8) and `i_qoffset` (0.0) are listed for every encoder. That only means they are AVCodecContext fields. Whether a wrapper reads them is answered by the code (sections 3.4 and 4.4).

## 3. AMF (h264_amf, hevc_amf)

### 3.1 gop_size → IDR period

| | h264_amf | hevc_amf |
|---|---|---|
| FFmpeg mapping [code] | `amfenc_h264.c:574-576`: `if (avctx->gop_size != -1)` → `AMF_VIDEO_ENCODER_IDR_PERIOD = gop_size` | `amfenc_hevc.c:298-301`: `NUM_GOPS_PER_IDR = gops_per_idr` (always set; default 1, `:97`), then `if (avctx->gop_size != -1)` → `AMF_VIDEO_ENCODER_HEVC_GOP_SIZE = gop_size` |
| default if unset [code + source] | codec default `"g", "-1"` (`amfenc_h264.c:638`), so FFmpeg does not set it. AMF default by usage: H264DOC:1408-1414 "Transcoding: `240`" … "Webcam: `0`" … "HQLL: `120`" | `"g", "-1"` (`amfenc_hevc.c:564`). HEVCDOC:1258-1263: "Transcoding: `240`" … "Webcam: `0`" … "HQLL: `240`" |
| meaning of 0 [source] | H264DOC:1417: "Sets IDR period. IDRPeriod = `0` turns IDR off." | HEVCDOC:1266: "The period to insert IDR/CRA in fixed size mode. `0` means only insert the first IDR/CRA (infinite GOP size)." |
| meaning of 1 | [source] header `VideoEncoderVCE.h:266`: "IDR Period in frames". [inferred] gop_size=1 → an IDR every frame | [source] HEVCDOC:1280: "Determines the frequency to insert IDR as start of a GOP." [inferred] gop_size=1 with gops_per_idr=1 → every 1-frame GOP starts with an IDR |

- **[code+source] AMF gop_size=0 is NOT all-intra, unlike NVENC.**
  - NVENC maps `gop_size == 0` to intra-only (`nvenc.c:1764-1766`, K4).
  - AMF passes 0 straight through, and AMD documents 0 as "turns IDR off" (H.264) or "only insert the first IDR/CRA" (HEVC).
  - inferred: reusing the NVENC entry of `matched_settings.json` (gop_size 0) on AMF would give long-GOP output. The QSV value (gop_size 1) is the one to reuse.

### 3.2 Per-frame forcing (second route to all-intra)

- [code] `amfenc.c:480-488` (H.264) and `:501-508` (HEVC): a frame with `pict_type == AV_PICTURE_TYPE_I` gets `FORCE_PICTURE_TYPE` = IDR when `forced_idr` is set, otherwise = I.
- [source] H264DOC:1953: "Forces the picture type (to use this feature, set `AMF_VIDEO_ENCODER_IDR_PERIOD` to `0`) determined by the picture management with the following precedence `IDR`, `I`, `P` and `B`."
- [source] HEVCDOC:1719 gives the same precedence and does not state the IDR_PERIOD=0 condition.
- [code] Only IDR output gets the packet key flag: `amfenc.c:211` (H.264) and `:224` (HEVC) set `AV_PKT_FLAG_KEY` only when the output type is IDR. Plain I output is typed `AV_PICTURE_TYPE_I` but is not flagged key (`:212-213`, `:225-226`).
  - inferred: forcing `I` without `forced_idr=1` would give all-intra bitstreams whose packets are not marked as keyframes in the container. The "every frame a keyframe" scope needs IDR.
- Route summary (inferred from the code and docs above):
  - H.264: (a) `gop_size=1`; or (b) `gop_size=0` + `forced_idr=1` + every frame `pict_type=I`.
  - HEVC: (a) `gop_size=1` (gops_per_idr stays 1); or (b) `forced_idr=1` + every frame `pict_type=I`.
  - K1 notes that decoded MJPEG frames already carry `pict_type=I`. Route (b) needs that for every frame; route (a) does not depend on it.

### 3.3 B-frames

- [code] h264_amf reads its **private** `bf` (→ `B_PIC_PATTERN`) and `max_b_frames` (→ `MAX_CONSECUTIVE_BPICTURES`), only when one of them is set or adaptive mini-GOP is on (`amfenc_h264.c:477-513`). It never reads the generic `avctx->max_b_frames`.
- [code] An options-dict key `bf` reaches the private option first: `avcodec.c:226` calls `av_opt_set_dict2(avctx, options, AV_OPT_SEARCH_CHILDREN)`, and `opt.c:2004-2017` searches child objects (priv_data) before the context's own options.
- [source] H264DOC:1498: "BPicturesPattern = `0` indicates that B-pictures are not used." `VideoEncoderVCE.h:263`: "default = 0".
- [code] hevc_amf has no B-frame option (§2 table). Its output types are IDR/I/P only (`amfenc.c:225-227`).
- [source] HEVCDOC v1.5.3 defines no B-picture property (a grep for B-picture wording returns nothing).
- inferred: B-frames are off by default on both. Passing `bf=0` to h264_amf is harmless and explicit.

### 3.4 Rate control for matched quality

| | h264_amf | hevc_amf |
|---|---|---|
| CQP option [code] | `rc=cqp` (`amfenc_h264.c:86`); auto-selected if any `qp_i/qp_p/qp_b` is set (`:299-302`) | `rc=cqp` (`amfenc_hevc.c:79`); auto-selected if any `qp_i/qp_p/min_qp_*/max_qp_*` is set (`:313-318`) |
| I-frame QP [code] | `qp_i` → `AMF_VIDEO_ENCODER_QP_I` (`amfenc_h264.c:377-378`) | `qp_i` → `AMF_VIDEO_ENCODER_HEVC_QP_I` (`amfenc_hevc.c:523-524`) |
| vendor text [source] | H264DOC:1136-1140: default "`22`", "Sets the constant QP for I-pictures. Remarks: Only available for CQP rate control method." | HEVCDOC:1047-1050: default "`26`", "Sets the constant QP for I-pictures.Remarks: Only available for CQP rate control method." |
| side effects of CQP [code] | MIN_QP 0 / MAX_QP 51 forced (`:363-365`); pre-encode disabled (`:312-319`); VBAQ disabled (`:539-542`) | VBAQ disabled (`:382-385`); pre-encode disabled (`:345-350`) |
| quality-VBR alternative [code] | `rc=qvbr` + `qvbr_quality_level` 0-51 (`:90`, `:94`, `:326-330`) | same (`:83`, `:87`, `:359-362`) |
| reads `i_qfactor`/`i_qoffset`? [code] | **no**: 0 matches in `amfenc.c`, `amfenc.h`, `amfenc_h264.c`, `amfenc_hevc.c` | **no** (same grep) |

- **[code] K3 does not apply to AMF.** The I-frame QP is set directly by `qp_i`. FFmpeg's `i_qfactor=-0.8` default is never read. Contrast: NVENC applies `i_quant_factor` to constQP (`nvenc.c:835-836`), and so does QSV CQP (`qsvenc.c:925,929`).
- [inferred] Matched-quality recipe for AMF: `rc=cqp`, `qp_i=N` (and `qp_p=N`), with `gop_size=1`. N for target A must come from an SSIM sweep on AMD hardware. On Gerald, NVENC/QSV reached A at QP 12-13 on yuy2_1080p (`R/intra_compare/matched_settings.json`). AMF's encoder is different hardware, so that value does not carry over (NOT VERIFIED).
- [inferred] AMF option names differ from NVENC's: AMF has `rc=cqp` and no `qp`, while NVENC uses `rc=constqp` and `qp`. So the NVENC options dict can't be reused as-is.

## 4. VideoToolbox (h264_videotoolbox, hevc_videotoolbox)

### 4.1 gop_size → MaxKeyFrameInterval

- [code] `videotoolboxenc.c:1379-1395`: `if (avctx->gop_size > 0 && avctx->codec_id != AV_CODEC_ID_PRORES)` → `kVTCompressionPropertyKey_MaxKeyFrameInterval = gop_size`. A failure returns an error (`:1390-1393`).
- [source] APPLEDOC `kvtcompressionpropertykey_maxkeyframeinterval`: "The default key frame interval is 0, which indicates that the video encoder should choose where to place all key frames. A key frame interval of 1 indicates that every frame must be a keyframe, 2 indicates that at least every other frame must be a keyframe, and so on."
- [code] gop_size 0 or -1 sets nothing, so the encoder chooses.
- [code] The VT codec defaults (`videotoolboxenc.c:2837-2842`) do not override `g`, so the generic default applies: `options_table.h:96` `"g" … {.i64 = 12 }`.
  - inferred: a PyAV context that leaves gop_size alone sends MaxKeyFrameInterval 12. All-intra needs an explicit `gop_size=1`.
- [code] Per-frame route: `create_encoder_dict_h264` (`:2458-2470`, used for both codecs at `:2492`) sets `kVTEncodeFrameOptionKey_ForceKeyFrame` when `pict_type == I`.
  - [source] APPLEDOC `kvtencodeframeoptionkey_forcekeyframe`: "Note that it may not be possible for the encoder to accommodate all requests."
- [code] `kVTCompressionPropertyKey_AllowTemporalCompression` is never set by FFmpeg (0 matches).
  - [source] APPLEDOC: "Set this `value` to false to require key-frame-only compression."
  - So FFmpeg's only routes to all-intra are MaxKeyFrameInterval=1 and per-frame ForceKeyFrame.
- [code] The packet key flag follows the sample's `kCMSampleAttachmentKey_NotSync` attachment (`:1809-1832`).
- NOT VERIFIED: whether hevc_videotoolbox keyframes at interval 1 are IDR or CRA. `flags=+cgop` sets `AllowOpenGOP=false` (`:1563-1568`).

### 4.2 B-frames

- [code] `has_b_frames = avctx->max_b_frames > 0` (H.264, `:1666`) or `? 2 : 0` (HEVC, `:1683`). When it is 0, FFmpeg sets `kVTCompressionPropertyKey_AllowFrameReordering = false` (`:1528-1537`).
- [code] The generic `bf` default is 0 (`options_table.h:109`, `DEFAULT`), so B-frames are off unless they are requested. After init, FFmpeg reads the property back (`:1789-1804`).
- [source] APPLEDOC `kvtcompressionpropertykey_allowframereordering`: "The default value is `true`. Set this value to `false` to prevent frame reordering."

### 4.3 Rate control: quality, QP clamps and the missing constant-QP knob

- [code] Quality knob, `:1250-1261`: if `AV_CODEC_FLAG_QSCALE` is set or `global_quality > 0`, FFmpeg sets `kVTCompressionPropertyKey_Quality` = `fminf(global_quality / factor, 1.0)`.
  - `factor` = `FF_QP2LAMBDA * 100` with `+qscale` (FF_QP2LAMBDA = 118, `libavutil/avutil.h:226`), otherwise 100.
  - In PyAV terms: `global_quality=75` gives Quality 0.75; `flags=+qscale, global_quality=q*118` gives q/100.
- [code] `+qscale` is allowed only where `!TARGET_OS_IPHONE && TARGET_CPU_ARM64` (`:1132-1135`). Elsewhere open fails with "-q:v qscale not available for encoder" (`:1245-1248`).
  - inferred: on the macosx_11_0_x86_64 wheel, set `global_quality` without `+qscale`.
- [source] APPLEDOC `kvtcompressionpropertykey_quality`: "This value should be specified as a number in the range of 0.0 to 1.0, where low = 0.25, normal = 0.50, high = 0.75, and 1.0 implies lossless compression for encoders that support it."
  - Apple gives no mapping from Quality to QP or PSNR. inferred: Quality is a quality-target knob, not constant QP, and target A needs a sweep on Apple hardware.
- [code] QP clamps, `:1570-1590`: `qmin >= 0` → `kVTCompressionPropertyKey_MinAllowedFrameQP`; `qmax >= 0` → `kVTCompressionPropertyKey_MaxAllowedFrameQP`. VT codec defaults set both to -1 (`:2839-2840`).
  - [source] APPLEDOC platforms: MinAllowedFrameQP macOS 13.0, MaxAllowedFrameQP macOS 12.0.
  - [source (SDK header via mirror)] VTH:1142-1143 (Max): "To satisfy this requirement, the encoder may drop frames to maintain bitrate and QP goals. This is not supported in all encoders or in all encoder operating modes."
  - [code] On `kVTPropertyNotSupportedErr`, FFmpeg logs at INFO level "This device does not support the %s option. Value ignored." and carries on (`:1144-1149`).
  - inferred: `qmin=qmax=N` is the nearest thing to CQP that FFmpeg exposes. It can be ignored without an error, and the Max clamp may drop frames. Neither is acceptable without a check on hardware.
- [source (SDK header via mirror)] VT has a true constant-QP control, `kVTEncodeFrameOptionKey_BaseFrameQP`. VTH:820: "Setting BaseFrameQP turns off standard rate control and will cause the following properties to be ignored". It is supported only when `kVTCompressionPropertyKey_SupportsBaseFrameQP` returns true (VTH:784-793, 832-834). APPLEDOC lists both symbols with macOS 12.0.
  - [code] FFmpeg n9.0.2 never sets it (0 matches for `BaseFrameQP`). So **constant QP is not reachable through PyAV 19.0.2 on VideoToolbox**.
- [code] `constant_bit_rate` (`:2831`, "macOS 13 or newer") selects CBR (`:1269-1275`). It is irrelevant to matched quality.
- [code] **VT never reads `i_qfactor`/`i_qoffset`** (0 matches), so K3 does not apply. There is no separate I/P QP to skew.

### 4.4 Hardware vs software

- [code] `allow_sw` defaults to 0 (`:2776-2777`). FFmpeg then sets `kVTVideoEncoderSpecification_RequireHardwareAcceleratedVideoEncoder = true` (`:1702-1705`).
- [source] APPLEDOC: "If hardware acceleration is not possible, the [VTCompressionSessionCreate(...)] call fails."
- inferred: with default options, a VT encoder that opens is a hardware encoder. A software fallback needs `allow_sw=1`.

## 5. Verdicts

| encoder | all-intra reachable (every frame a keyframe) | matched-quality knob | i_qfactor equivalent | on-hardware behaviour |
|---|---|---|---|---|
| h264_amf | **yes [code+source]**: `gop_size=1` → IDR_PERIOD 1 (`amfenc_h264.c:574-576`; VCE.h:266 "IDR Period in frames"; every-frame IDR inferred). Alt.: `gop_size=0` + `forced_idr=1` + `pict_type=I` (`amfenc.c:480-486`; H264DOC:1953). **gop_size=0 alone = IDR off** (H264DOC:1417) | **yes, constant QP [code+source]**: `rc=cqp`, `qp_i` (`amfenc_h264.c:86,377-378`; H264DOC:1139) | none needed: `qp_i` sets the I QP directly; `i_qfactor` not read [code] | NOT VERIFIED (no AMD hardware) |
| hevc_amf | **yes [code+source]**: `gop_size=1` with `gops_per_idr=1` default (`amfenc_hevc.c:97,298-301`; HEVCDOC:1266,1280; inferred). Alt.: `forced_idr=1` + `pict_type=I` (`amfenc.c:501-506`). **gop_size=0 = first IDR only** (HEVCDOC:1266) | **yes, constant QP [code+source]**: `rc=cqp`, `qp_i` (`amfenc_hevc.c:79,523-524`; HEVCDOC:1050) | none needed; `i_qfactor` not read [code] | NOT VERIFIED |
| h264_videotoolbox | **yes [code+source]**: `gop_size=1` → MaxKeyFrameInterval 1 (`videotoolboxenc.c:1379-1395`; APPLEDOC "every frame must be a keyframe"). The default gop_size 12 must be overridden | **quality knob only [code+source]**: `global_quality` → `kVTCompressionPropertyKey_Quality` 0-1 (`:1250-1261`). Constant QP **not reachable** in FFmpeg n9.0.2 (BaseFrameQP unused). `qmin=qmax` QP clamp is best-effort (may be ignored or drop frames; VTH:1142-1143; `:1144-1149`) | none: no I/P QP split; `i_qfactor` not read [code] | NOT VERIFIED (no Apple hardware) |
| hevc_videotoolbox | **yes [code+source]**: as h264 (same code path). IDR vs CRA NOT VERIFIED | as h264 | as h264 | NOT VERIFIED |

What stays NOT VERIFIED (no AMD or Apple hardware, no test possible here):
- whether each driver honours IDR_PERIOD 1 / GOP_SIZE 1 / MaxKeyFrameInterval 1 on every frame;
- which `qp_i` (AMF) or `global_quality` (VT) reaches target A, and the resulting bytes;
- whether VT Min/MaxAllowedFrameQP are accepted on M1-M4 for H.264/HEVC;
- the AMF runtime version shipped in each driver. The docs here are SDK v1.5.3.

## 6. Proposed replacement text for hw_accel_target FINDINGS

Old text is quoted from `R/hw_accel_target/FINDINGS.md` (read 2026-11-10).

**§3.2 line 357, AMD / Windows, "reachable" cell.** Old: "`h264/hevc/av1_amf` (not tested; no AMD here)".
New: "`h264/hevc/av1_amf` in the wheel (measured, GF06 static query). All-intra via `gop_size=1` (not 0) or `forced_idr=1` + `pict_type=I` [code `amfenc_h264.c:574-576`, `amfenc_hevc.c:298-301`, `amfenc.c:480-508`]. Constant QP via `rc=cqp, qp_i` [code `amfenc_h264.c:377-378`, `amfenc_hevc.c:523-524`]. On-hardware NOT VERIFIED (no AMD here)".

**§3.2 line 358, AMD / Linux.** Old: "`*_amf` (needs AMD's closed runtime)".
New: "`*_amf` (needs AMD's closed runtime); same intra/CQP options as Windows (GF06) [code]; on-hardware NOT VERIFIED".

**§3.2 line 359, Apple / macOS.** Old: "`h264/hevc_videotoolbox` (+ prores)".
New: "`h264/hevc_videotoolbox` (+ prores), macOS wheels only (`R/gpu_encode/wheel_hw_codecs.md`). All-intra via `gop_size=1` → MaxKeyFrameInterval 1 [code `videotoolboxenc.c:1379-1395`; source APPLEDOC]. Default gop_size is 12 [code `options_table.h:96`]. Quality via `global_quality` → `kVTCompressionPropertyKey_Quality` (0-1) [code `:1250-1261`]. **Constant QP not reachable** (BaseFrameQP unused by FFmpeg n9.0.2) [code]. Hardware required by default (`allow_sw=0`) [code `:1702-1705`]. On-hardware NOT VERIFIED".

**§3.3 line 368, H.264 intra, AMD cell.** Old: "Y (source; all parts with an encoder, not Navi24; AMF untested)".
New: "codec Y (source; not Navi24). Intra-only via `gop_size=1` [code]. Matched-quality knob `rc=cqp, qp_i` [code+source]. `i_qfactor` not read, so K3 does not apply [code]. On-hardware NOT VERIFIED (GF06)".

**§3.3 line 368, H.264 intra, Apple cell.** Old: "Y (P on base M1; source)".
New: "codec Y (P on base M1; source). Intra-only via `gop_size=1` [code+source]. Matched-quality knob `global_quality` → VT Quality (no constant QP) [code+source]. On-hardware NOT VERIFIED (GF06)".

**§3.3 line 369, HEVC intra, AMD cell.** Old: "Y (source; not Navi24)".
New: "codec Y (source; not Navi24). Intra-only via `gop_size=1` with `gops_per_idr=1` [code+source]. Matched-quality knob `rc=cqp, qp_i` [code+source]. On-hardware NOT VERIFIED (GF06)".

**§3.3 line 369, HEVC intra, Apple cell.** Old: "Y (P on base M1; source)".
New: "codec Y (P on base M1; source). Intra-only via `gop_size=1` [code+source]; IDR vs CRA NOT VERIFIED. Matched-quality knob `global_quality` → VT Quality (no constant QP) [code+source]. On-hardware NOT VERIFIED (GF06)".

**§3.3 line 381.** Old: "    - AMD AMF is untested;".
New: "    - AMD AMF is untested on hardware. Its all-intra (`gop_size=1`) and CQP (`rc=cqp, qp_i`) options exist in code (GF06);".
