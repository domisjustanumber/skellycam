# intra_compare: JPEG vs H.264 intra vs HEVC intra at matched quality (PyAV 19.0.2, functional)

Stage: functional quality-matching sweep only. **No timing, throughput or CPU numbers** (other agents were running).
Sizes, PSNR, SSIM, frame counts and bitstream checks are reported.

Labels: **measured** (result file), **source** (primary source, accessed 2026-11-09), **code** (file:line),
**inferred** (kept short and marked). `R` = `research/skellycam_recording/recording_upgrade/results/intra_compare/`,
`S` = `research/skellycam_recording/recording_upgrade/scripts/intra_compare/`. Media (it shows the room) is under
`C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/intra_compare/samples/`.

## 1. Bottom line

Numbers are bytes/frame interpolated to the target (`R/matched_summary.md`, column `bytes@target`; interpolated between two measured points). "x JPEG" is the ratio to libjpeg-turbo 4:2:2 (`jpeg_turbo_422`).

- measured: **994 sweep points over 16 intra-only paths and 4 input classes (73,556 frame encodes). Every point decoded back in PyAV 19.0.2 software decode with the right frame count.** Every H.264/HEVC frame is IDR with `has_b_frames=0`, and there are 0 failed points (`R/verification.md`).
- measured: **target A, camera-equivalent quality (SSIM-Y 0.9961), on the raw YUY2 1080p frames**:

  | path | bytes/frame | x JPEG |
  |---|---|---|
  | libjpeg-turbo 4:2:2 | 297,359 | 1.00 |
  | libjpeg-turbo 4:2:0 | 265,001 | 0.89 |
  | nvJPEG 4:2:0 | 221,461 | 0.74 |
  | mjpeg_qsv 4:2:0 | 296,502 | 1.00 |
  | h264_nvenc | 157,840 | 0.53 |
  | h264_qsv | 175,094 | 0.59 |
  | hevc_nvenc | 129,131 | 0.43 |
  | hevc_qsv 4:2:0 | 116,646 | 0.39 |

  So at camera quality, **H.264 intra is about half the size of JPEG and HEVC intra about 0.4x**.
- measured: **target B, PSNR-Y 45 dB, yuy2_1080p: the gap widens**:

  | path | bytes/frame | x JPEG |
  |---|---|---|
  | libjpeg-turbo 4:2:2 | 77,458 | 1.00 |
  | h264_nvenc | 22,392 | 0.29 |
  | h264_qsv | 27,378 | 0.35 |
  | hevc_nvenc / hevc_qsv | 14,290 / 14,236 | 0.18 |
- measured: **on decoded camera MJPEG, a re-encode at target A is smaller than the camera's own JPEG**. Bytes/frame and the ratio to passthrough:

  | path | mjpeg_720p (passthrough 66,594) | mjpeg_1080p (passthrough 163,478) |
  |---|---|---|
  | libjpeg-turbo 4:2:2 | 60,318 (0.91) | 145,774 (0.89) |
  | libjpeg-turbo 4:2:0 | 55,459 (0.83) | 130,185 (0.80) |
  | h264_nvenc | 46,217 (0.69) | 123,426 (0.76) |
  | hevc_qsv 4:2:0 | 42,502 (0.64) | 110,835 (0.68) |

  - These metrics are generation loss against the decoded camera frame. Passthrough itself adds no loss.
- measured: **the hardware JPEG encoders are in the same size range as CPU libjpeg-turbo**, compared at the same chroma:
  - `mjpeg_qsv` is 0.99-1.12x libjpeg-turbo, at both targets and on every input;
  - nvJPEG is 0.81-1.24x: smaller on the noisy YUY2 frames at target A, larger on decoded camera MJPEG.
  - At target A, nvJPEG's PSNR-Y is 1.4-2.2 dB lower than libjpeg-turbo's at the same SSIM-Y. That is nvJPEG's own colour-conversion bias; it is fed RGB (section 9).
- measured: the CPU H.264/HEVC encoders in the wheel:
  - **libx264 veryfast is close to NVENC/QSV H.264** (0.55x JPEG at A and 0.36x at B on yuy2_1080p);
  - **libx264 ultrafast is not** (0.82x and 0.72x, and 1.42-1.53x passthrough on MJPEG inputs at A) (corrected 2026-11-10, GF05: was 1.41-1.52x; current values from `R/matched_summary.md`, mjpeg_720p 1.42 and mjpeg_1080p 1.53);
  - libx265 ultrafast gives 0.49x and 0.25x.
  - Both libraries are GPL and present in the PyAV 19.0.2 wheel; libopenh264 is absent (section 10).
- measured: **4:2:2 costs 7-17% more bytes for JPEG at the same knob** (Y unchanged; PSNR-YUV against the 4:2:2 source +0.33 to +1.78 dB), and 13-33% more for hevc_qsv 4:2:2 (section 7).
- measured: a pitfall for any H.264/HEVC CQP setting through FFmpeg. The default `i_qfactor=-0.8` makes NVENC and QSV code intra frames at 0.8x the requested QP, and x264/x265 apply their own ip factor (QP 25 gives 20 or 22). `matched_settings.json` pins `i_qfactor=1, i_qoffset=0` (section 3 and section 9).
- **Matched settings for tonight's bench: `R/matched_settings.json`** (section 11).

## 2. Inputs and reference frames

| input class | frames | how it is made | source range | reference for metrics |
|---|---|---|---|---|
| yuy2_1080p | 16 | corpus `c930e_1080p_yuy2` + `c922_1080p_yuy2`, 8 real packed YUYV frames each, unpacked to planes in numpy | limited (as delivered) | the camera's own YUY2 samples (exact) |
| yuy2_720p | 16 | **derived**: the same 16 frames scaled 1920x1080 to 1280x720 by PyAV swscale (yuyv422 to yuyv422), as in `scripts/hw_accel_target/benchlib.py:yuy2_frames_bytes` | limited | the scaled YUY2 samples |
| mjpeg_720p | 240 | corpus `c930e_720p_flash` + `c922_720p_flash`, first 120 camera JPEGs each, decoded by PyAV 19.0.2 `mjpeg` (software) to `yuvj422p` | full | the decoded camera frame |
| mjpeg_1080p | 38 | corpus `c930e_1080p` + `c922_1080p`, all 19 + 19 camera JPEGs, decoded the same way | full | the decoded camera frame |

- code: every conversion is explicit numpy in `S/iclib.py` (docstring and `fed_planes`, `map_range`, `down420`):
  - 4:2:0 chroma: rounded vertical average of 4:2:2 row pairs, made once in the source range;
  - range change only where an encoder needs the other range, rounded and clipped: `Y'=(Y-16)*255/219`, `C'=(C-128)*255/224+128` and the inverse;
  - JPEG paths are fed full range (JFIF), H.264/HEVC paths limited range (what the 23:00 bench feeds, `dst_color_range=1`);
  - decoded MJPEG frames are rebuilt as new frames from planes, so no decoder `pict_type=I` reaches an encoder (pitfall in `results/hw_accel_target/NOTES_functional.md` §6).
- measured: decoded camera JPEGs are `yuvj422p` for all four MJPEG sets (`iclib.load_input` asserts it; every sweep run passed).
- For the MJPEG classes the metrics measure **generation loss on top of the camera's JPEG**, not loss against the scene.
- Camera passthrough reference (no re-encode), camera JPEG bytes/frame of exactly the frames used (`R/camera_jpeg_quality.md`):

| set | frames | bytes/frame mean |
|---|---|---|
| c930e_720p_flash | 120 | 55,489 |
| c922_720p_flash | 120 | 77,699 |
| mjpeg_720p class mean | 240 | 66,594 |
| c930e_1080p | 19 | 134,574 |
| c922_1080p | 19 | 192,382 |
| mjpeg_1080p class mean | 38 | 163,478 |

## 3. Encode paths, versions and quality knobs

All paths are intra-only. Versions: PyAV 19.0.2 (libavcodec 63.1.102, FFmpeg 9.0.2), simplejpeg 1.9.0, nvidia-nvimgcodec-cu12 0.10.0.9 (`[nvjpeg]` extra), numpy 2.2.6, scipy 1.16.2, recorded per run in `R/raw/*.json` (`runs[].versions`). Python 3.12, all through `uv run --script` with PEP 723 pins.

| path id | encoder | chroma | fed as | knob (sweep values) | other options |
|---|---|---|---|---|---|
| jpeg_turbo_422 / _420 | libjpeg-turbo 3.1.2 via `simplejpeg.encode_jpeg_yuv_planes` (CPU) | 4:2:2 / 4:2:0 | Y, U, V planes, full range | quality 20-98 | fastdct=False |
| ff_mjpeg_422 / _420 | FFmpeg `mjpeg` (CPU) | 4:2:2 / 4:2:0 | yuvj422p / yuvj420p | qscale via `qmin=qmax` 1-16 | defaults |
| mjpeg_qsv_422 / _420 | `mjpeg_qsv` (Intel UHD 770) | 4:2:2 / 4:2:0 | yuyv422 / nv12, full-range samples | `global_quality` 20-98 | defaults |
| nvjpeg_422 / _420 | nvJPEG `nvjpeg_cuda_encoder` via nvImageCodec (CUDA, RTX 3070) | CSS_422 / CSS_420 | host RGB24, exact float BT.601 from the 4:2:2 source (`iclib.rgb_from_src`) | quality 20-98 | QualityType.QUALITY |
| h264_nvenc_420, hevc_nvenc_420 | NVENC | 4:2:0 | nv12, limited | `qp` 8-40, `rc=constqp` | preset p4, tune ll, gop_size 0, max_b_frames 0, i_qfactor 1, i_qoffset 0 |
| h264_qsv_420, hevc_qsv_420 | QSV | 4:2:0 | nv12, limited | QP 8-40 as `flags=+qscale`, `global_quality=QP*118` (CQP) | gop_size 1, max_b_frames 0, i_qfactor 1, i_qoffset 0 |
| hevc_qsv_422 | QSV, HEVC Rext 4:2:2 | 4:2:2 | yuyv422, limited | as hevc_qsv | as hevc_qsv |
| libx264_ultrafast_420, libx264_veryfast_420 | libx264 in the PyAV wheel (CPU) | 4:2:0 | yuv420p, limited | `qp` 8-40 | preset ultrafast / veryfast, gop_size 1, i_qfactor 1, i_qoffset 0 |
| libx265_ultrafast_420 | libx265 in the PyAV wheel (CPU) | 4:2:0 | yuv420p, limited | `qp` 8-40 | preset ultrafast, gop_size 1, i_qfactor 1, i_qoffset 0 |

Coarse grid: JPEG quality 50/70/80/85/90/95/98; QP 12/16/20/24/28/32/36; mjpeg qscale 1/2/3/4/6/8/12. Then `S/analyze.py` writes `R/refine_plan.json`: integer values between the two points that bracket each target (at most 4), plus grid extensions where a target lay outside the grid. `S/run_refine.py` runs that plan (labels `extend` / `refine` in the raw JSON). Every point is listed in `R/curves.md`.

Knob evidence:
- code: FFmpeg's default `i_qfactor` is -0.8 (`libavcodec/options_table.h:151`, n9.0.2). NVENC constqp sets `qpIntra = cqp * fabs(i_quant_factor) + i_quant_offset + 0.5` (`nvenc.c:835-836`). QSV CQP sets `QPI = quant * fabs(i_quant_factor) + i_quant_offset` with `quant = global_quality / FF_QP2LAMBDA` (`qsvenc.c:922-929`). libx264 sets `f_ip_factor = 1 / fabs(i_quant_factor)` only when it is > 0 (`libx264.c:1143-1144`). libx265 passes `ipratio` only when it is >= 0 (`libx265.c:473-474`). Excerpts with line numbers are in `R/ffmpeg_n9.0.2_knob_excerpts.txt`.
- measured: requesting QP 25 with the default `i_qfactor` gives intra QP 20 on h264_nvenc and h264_qsv, and 22 on libx264 and libx265 (encoder quality-stats side data). With `i_qfactor=1, i_qoffset=0` all four report 25. Packet sizes change for hevc_nvenc and hevc_qsv too (hevc_qsv attaches no stats) (`R/knob_check.json`).
- measured: in the sweep, the stats side data equals the requested QP for every point of h264_qsv, libx264 and libx265. h264/hevc_nvenc report QP-1, which matches `(frameAvgQP - 1) * FF_QP2LAMBDA` at `nvenc.c:2646-2647`, so frameAvgQP = QP (`R/verification.md`, last two columns).
- code: `mjpeg_qsv` uses `Quality = av_clip(global_quality, 1, 100)` (`qsvenc.c:762`, in `init_video_param_jpeg`).
- measured: FFmpeg `mjpeg` ignores `flags=+qscale` + `global_quality` given as codec options. Values 236 and 1416 give the same 125,998 bytes, the size of `qmin=qmax=2`. `qmin=qmax=12` gives 67,031 (`R/knob_check.json`). inferred: the fixed-qscale path reads the per-frame `quality` field, which the ffmpeg CLI sets and PyAV does not expose, so the sweep clamps with `qmin=qmax`.
- code: NVENC `gop_size == 0` sets `frameIntervalP = 0; gopLength = 1` (`nvenc.c:1764-1766`).

## 4. Metrics

code (`S/iclib.py`, `metrics`, `ssim`, `up422`):
- **PSNR-Y and SSIM-Y**:
  - decoded Y mapped in float (no rounding) to the source range, compared with the source Y;
  - the same reference for every path, so these two are comparable across paths;
  - mean of per-frame values, and the minimum is also kept.
- **SSIM** (Wang et al. 2004 parameters):
  - Gaussian window sigma 1.5, radius 5, K1 0.01, K2 0.03, L 255;
  - population covariance;
  - mean over the image with a 5-pixel border excluded;
  - the same parameters as scikit-image `structural_similarity(gaussian_weights=True, sigma=1.5, use_sample_covariance=False, data_range=255)`.
  - Implemented with `scipy.ndimage.gaussian_filter` (scipy 1.16.2). scikit-image itself was not used.
- **PSNR-YUV 4:2:2**:
  - Y, U and V against the 4:2:2 source, with MSE weighted by sample count;
  - 4:2:0 output chroma is upsampled vertically by linear interpolation (0.75/0.25) for this metric only;
  - this is the total loss including chroma subsampling.
- **PSNR-YUV fed**: codec-only loss against the frame actually fed, at its own chroma resolution and range. It is not defined for nvJPEG, which is fed RGB.
- **bytes/frame**:
  - JPEG: the whole JPEG file, headers included;
  - H.264/HEVC: the encoder's Annex B packet with SPS/PPS(/VPS) repeated in-band in every packet.
  - inferred: in MP4/MKV the parameter sets go to extradata, so container payloads would be slightly smaller; not measured.

## 5. Choice of the matched-quality targets

- measured: the cameras' JPEGs use one fixed DQT set across all frames of each set:
  - the nearest IJG quality is **q94** for luma and chroma in all four sets (`c930e_720p_flash`, `c922_720p_flash`, `c930e_1080p`, `c922_1080p`);
  - it is not an exact IJG table (summed absolute error over 64 entries: 124 luma, 60 chroma) (`R/camera_jpeg_quality.md`).
- measured: libjpeg-turbo q94 (4:2:2, full range) on the **same camera models' raw YUY2 1080p frames** reaches:

  | camera | SSIM-Y | PSNR-Y |
  |---|---|---|
  | C930e | 0.99694 | 52.65 dB |
  | C922 | 0.99520 | 51.83 dB |
  | mean | **0.9961** | 52.24 dB |

  (`R/camera_jpeg_quality.md`).
- **Target A = SSIM-Y 0.9961 ("camera-equivalent")**.
  - inferred: this approximates the quality the cameras' own JPEGs reach against a fair (uncompressed) reference. A recorder that re-encodes at A is about as faithful as storing the camera's JPEG.
  - Caveats:
    - the camera's encoder is not libjpeg-turbo and its tables are not exact IJG tables;
    - the YUY2 and MJPEG frames are different captures;
    - the cameras' 1080p JPEGs are much smaller (134,574 / 192,382 B) than libjpeg-turbo q94 on the YUY2 frames (260,827 / 312,812 B). inferred: the scenes differ, or the camera processes MJPEG differently (for example, noise reduction); NOT VERIFIED.
- **Target B = PSNR-Y 45 dB** (the task's example "high quality" point). measured: **on this content B is lower quality than A**:
  - camera-equivalent PSNR-Y is about 52 dB;
  - libjpeg-turbo q50 on yuy2_1080p already gives PSNR-Y 45.6 dB and SSIM-Y 0.988 (`R/curves.md`).
  - So B serves as the compact point. The task's other examples, SSIM-Y 0.98 / PSNR-Y 40 dB, lie below even libjpeg-turbo q50 here and were not used.
- measured: **SSIM-Y saturates near A**. Small SSIM steps are large byte steps: jpeg_turbo_422 on yuy2_1080p goes from q90 (SSIM-Y 0.9953, 204,402 B) to q95 (0.9962, 327,395 B) (`R/curves.md`). The refine pass therefore swept every integer between the bracketing points.
- measured: at equal SSIM-Y the H.264/HEVC points have about 1 dB higher PSNR-Y than the JPEG points (target A, yuy2_1080p: H.264/HEVC 53.1-53.4 dB vs CPU/QSV JPEG 52.2-52.6 dB; nvJPEG 50.8 dB). Matching on PSNR-Y instead would favour H.264/HEVC slightly more.

## 6. Results at matched quality

Full tables: `R/matched_summary.md` (all paths, both targets, all four input classes). All curves: `R/curves.md` / `R/curves.json`. Below, `bytes@target` (interpolated), with the ratio to jpeg_turbo_422 in parentheses (and the ratio to camera passthrough for the MJPEG classes).

Target A (SSIM-Y 0.9961):

| path | yuy2_1080p | yuy2_720p | mjpeg_720p (passthrough 66,594) | mjpeg_1080p (passthrough 163,478) |
|---|---|---|---|---|
| jpeg_turbo_422 | 297,359 (1.00) | 163,913 (1.00) | 60,318 (1.00; 0.91) | 145,774 (1.00; 0.89) |
| jpeg_turbo_420 | 265,001 (0.89) | 147,259 (0.90) | 55,459 (0.92; 0.83) | 130,185 (0.89; 0.80) |
| ff_mjpeg_420 | 221,837 (0.75) | 114,849 (0.70) | 54,073 (0.90; 0.81) | 133,872 (0.92; 0.82) |
| mjpeg_qsv_422 | 331,349 (1.11) | 170,009 (1.04) | 59,802 (0.99; 0.90) | 145,128 (1.00; 0.89) |
| mjpeg_qsv_420 | 296,502 (1.00) | 152,596 (0.93) | 54,796 (0.91; 0.82) | 129,364 (0.89; 0.79) |
| nvjpeg_422 | 248,629 (0.84) | 133,459 (0.81) | 65,280 (1.08; 0.98) | 175,469 (1.20; 1.07) |
| nvjpeg_420 | 221,461 (0.74) | 119,385 (0.73) | 60,527 (1.00; 0.91) | 161,033 (1.10; 0.99) |
| h264_nvenc_420 | 157,840 (0.53) | 83,913 (0.51) (corrected 2026-11-10, GF05: was 83,921; current value from `R/matched_summary.md`) | 46,217 (0.77; 0.69) | 123,426 (0.85; 0.76) |
| h264_qsv_420 | 175,094 (0.59) | 92,438 (0.56) | 55,667 (0.92; 0.84) | 148,327 (1.02; 0.91) |
| hevc_nvenc_420 | 129,131 (0.43) | 66,037 (0.40) | 53,975 (0.89; 0.81) (corrected 2026-11-10, GF05: was 55,112 (0.91; 0.83); `R/matched_summary.md`) | 141,655 (0.97; 0.87) (corrected 2026-11-10, GF05: was 144,376 (0.99; 0.88); `R/matched_summary.md`) |
| hevc_qsv_420 | 116,646 (0.39) | 59,282 (0.36) | 42,502 (0.70; 0.64) | 110,835 (0.76; 0.68) |
| hevc_qsv_422 | 155,171 (0.52) | 77,251 (0.47) | 47,993 (0.80; 0.72) | 136,529 (0.94; 0.84) |
| libx264_veryfast_420 | 164,862 (0.55) | 87,991 (0.54) | 55,236 (0.92; 0.83) | 149,851 (1.03; 0.92) |
| libx264_ultrafast_420 | 244,910 (0.82) | 133,065 (0.81) | 94,459 (1.57; 1.42) (corrected 2026-11-10, GF05: was 93,764 (1.55; 1.41); `R/matched_summary.md`) | 249,785 (1.71; 1.53) (corrected 2026-11-10, GF05: was 248,857 (1.71; 1.52); `R/matched_summary.md`) |
| libx265_ultrafast_420 | 146,521 (0.49) | 79,734 (0.49) | 67,662 (1.12; 1.02) (corrected 2026-11-10, GF05: was 67,557 (1.12; 1.01); `R/matched_summary.md`) | 161,155 (1.11; 0.99) (corrected 2026-11-10, GF05: was 160,931 (1.10; 0.98); `R/matched_summary.md`) |

Target B (PSNR-Y 45 dB):

| path | yuy2_1080p | yuy2_720p | mjpeg_720p | mjpeg_1080p |
|---|---|---|---|---|
| jpeg_turbo_422 | 77,458 (1.00) | 47,077 (1.00) | 32,096 (1.00; 0.48) | 69,748 (1.00; 0.43) |
| jpeg_turbo_420 | 68,773 (0.89) | 42,593 (0.90) | 28,228 (0.88; 0.42) | 61,406 (0.88; 0.38) |
| mjpeg_qsv_420 | 68,415 (0.88) | 42,349 (0.90) | 28,133 (0.88; 0.42) | 61,085 (0.88; 0.37) |
| nvjpeg_420 | 71,551 (0.92) | 45,104 (0.96) | 32,263 (1.01; 0.48) | 68,468 (0.98; 0.42) |
| h264_nvenc_420 | 22,392 (0.29) | 16,047 (0.34) | 8,611 (0.27; 0.13) | 18,026 (0.26; 0.11) |
| h264_qsv_420 | 27,378 (0.35) | 18,593 (0.39) | 10,722 (0.33; 0.16) | 22,639 (0.32; 0.14) |
| hevc_nvenc_420 | 14,290 (0.18) | 10,960 (0.23) | 6,417 (0.20; 0.10) | 12,428 (0.18; 0.08) |
| hevc_qsv_420 | 14,236 (0.18) | 10,431 (0.22) | 5,959 (0.19; 0.09) | 11,965 (0.17; 0.07) |
| libx264_veryfast_420 | 27,722 (0.36) | 19,231 (0.41) | 11,217 (0.35; 0.17) | 23,474 (0.34; 0.14) |
| libx265_ultrafast_420 | 19,518 (0.25) | 16,196 (0.34) | 9,805 (0.31; 0.15) | 15,985 (0.23; 0.10) |

Observations (all measured, from the two tables and `R/curves.md`):
- H.264/HEVC intra's size advantage over JPEG grows as quality drops:
  - about 0.4-0.6x at camera quality on raw frames;
  - about 0.2-0.35x at 45 dB.
- On decoded camera MJPEG at target A the codecs are closer together (0.70-1.02x jpeg_turbo_422, 0.64-0.91x passthrough, for the NVENC/QSV H.264/HEVC paths), because the camera's JPEG already removed detail and noise.
- hevc_nvenc is worse than h264_nvenc at target A on MJPEG inputs (53,975 vs 46,217 at 720p; 141,655 vs 123,426 at 1080p), but better at target B and on YUY2 (corrected 2026-11-10, GF05: hevc_nvenc was 55,112 / 144,376; current values from `R/matched_summary.md`).
- FFmpeg `mjpeg` 4:2:0 is 0.78-0.84x libjpeg-turbo 4:2:0 at target A on YUY2, but 0.92-0.97x at B, and 0.97-1.03x on MJPEG inputs at A.
  - The cause is NOT VERIFIED. It is not Huffman optimisation (section 8). FFmpeg writes a single DQT table and uses a qscale-scaled matrix rather than IJG quality scaling (inferred from the DQT count only).
- `mjpeg_qsv` and libjpeg-turbo give the same Y quality at the same quality value (for example yuy2_1080p q50: PSNR-Y 45.64 dB for both, SSIM-Y 0.9883 vs 0.9882; `R/curves.md`), with bytes within 0.99-1.12x.

## 7. 4:2:2 vs 4:2:0

measured (`R/raw/*.json`, same knob value as the target-A setting of the 4:2:2 path):

| path pair | bytes 4:2:2 / 4:2:0 | PSNR-Y change | PSNR-YUV (vs 4:2:2 source) change |
|---|---|---|---|
| jpeg_turbo | 1.08-1.12 | 0.00 | +0.45 (yuy2_1080p) to +1.67 (mjpeg_1080p) |
| ff_mjpeg | 1.07-1.17 | 0.00 | +0.43 to +1.37 |
| mjpeg_qsv | 1.09-1.12 | 0.00 | +0.49 to +1.78 |
| nvjpeg | 1.08-1.12 | 0.00 | +0.33 to +0.82 |
| hevc_qsv (Rext 4:2:2 vs Main) | 1.13-1.33 | 0.00 | +0.14 to +0.47 |

- measured: the chroma choice does not change luma in any of these encoders (identical PSNR-Y and SSIM-Y at the same knob).
- measured: the cameras deliver 4:2:2 (YUY2, and 4:2:2 JPEG).
  - Keeping 4:2:2 costs 7-17% more bytes for JPEG.
  - inferred: that is the price of not discarding half the chroma the camera sent. Whether it matters for markerless tracking is outside this test.

## 8. Decode-back and intra-only verification

Table: `R/verification.md`, one row per (path, input class).
- measured: **every point of every path decoded back in PyAV 19.0.2 software decode with frames out = frames in** (`frames_ok`). JPEG: each JPEG is decoded on its own with `mjpeg`. H.264/HEVC: the encoder's Annex B packets are written to a raw elementary-stream file and read back with `av.open(format="h264"|"hevc")`.
- measured: for every H.264/HEVC point:
  - every VCL NAL unit in every packet is IDR (H.264 type 5; HEVC type 19 IDR_W_RADL from NVENC/QSV, type 20 IDR_N_LP from libx265);
  - SPS/PPS (and VPS for HEVC) are repeated in every packet;
  - the decoder reports `has_b_frames = 0`;
  - every decoded frame has `key_frame = 1` and `pict_type = I` (PyAV 19 returns the AVPictureType int, 1 = I).
- measured: ffprobe (inspection only) of the saved mid-grid sample of each path and input agrees: `has_b_frames=0`, key frames = frames, `pict_types {'I': n}` (`R/verification.md`, last column).
- measured: profiles. h264_nvenc, h264_qsv and libx264 veryfast give High; libx264 ultrafast gives Constrained Baseline; hevc_nvenc and hevc_qsv 4:2:0 give Main; hevc_qsv yuyv422 gives Rext 4:2:2; **libx265 all-intra 4:2:0 gives Rext** (ffprobe and decoder agree).
  - inferred: x265 signals a RExt-family intra profile for all-intra streams. Whether Electron/Chromium decodes it is NOT VERIFIED here (chromium_codecs topic).
- measured: JPEG outputs are baseline (SOF0) and decode as `yuvj422p` / `yuvj420p` as requested (`decoded_pix_fmts` per point).
- measured: every saved JPEG sample from all four JPEG encoders, and the camera JPEGs, uses the four standard Annex K Huffman tables (`R/dht_check.json`).
  - code: FFmpeg `mjpeg`'s `huffman` option defaults to `optimal` (`mjpegenc.c:650`), yet the written DHT code-length counts equal Annex K. So optimised Huffman tables do not explain any size difference here.
  - measured: FFmpeg `mjpeg` writes one DQT table, libjpeg-turbo and nvJPEG two, and mjpeg_qsv and the cameras three.

## 9. Pitfalls found (they affect the bench and any implementation)

1. measured/code: **FFmpeg's default `i_qfactor=-0.8` silently lowers the intra QP** for NVENC constqp and QSV CQP (x0.8). For x264/x265 the encoder's own ip factor (1.4) applies instead. An "all-intra QP 25" stream is then really QP 20-22 (section 3). Every H.264/HEVC entry in `matched_settings.json` carries `i_qfactor=1, i_qoffset=0`; the bench must pass the options exactly.
2. measured: FFmpeg `mjpeg` quality cannot be set through `global_quality` codec options from PyAV; use `qmin=qmax` (section 3).
3. measured: **feeding nvJPEG RGB made by PyAV swscale costs about 6 dB of PSNR-Y**:
   - the RGB step alone gives PSNR-Y 46.7 dB against the YUY2 source, with a mean Y error of -1.13 levels;
   - an exact float BT.601 conversion gives 63.1 dB and +0.001;
   - nvJPEG q95 on the YUY2 frames reaches 43.9 dB from swscale RGB and 51.4 dB from exact RGB (`R/nvjpeg_rgb_diag.json`, `sws_*` vs `np_*`).
   - The sweep uses the exact conversion. nvJPEG still trails libjpeg-turbo from the same exact RGB (q95: 51.4 vs 52.1 dB on YUY2; 50.7 vs 55.2 dB on decoded camera JPEG), which points to nvJPEG's own RGB-to-YCbCr step.
   - measured: nvImageCodec 0.10.0.9 does not accept planar or interleaved YUV input (`results/gpu_encode/nvimgcodec_jpeg.md`, "YUV/gray input acceptance": `encode returned None`).
4. measured: libx265 all-intra streams are Rext profile, not Main (section 8).
5. code/measured: range. JPEG wants full-range samples and H.264/HEVC are tagged limited, so the range conversion must be explicit. `results/hw_accel_target/NOTES_functional.md` §6.2 shows that PyAV `reformat()` keeps full range when going to nv12 unless `dst_color_range=1` is passed. The rounding of the range change itself costs something. inferred from the arithmetic (uniform +-0.5 rounding, then rescaling):
   - limited to full (JPEG paths on YUY2): about 0.25 levels RMS in the source domain, a PSNR ceiling near 60 dB;
   - full to limited (H.264/HEVC on decoded MJPEG): about 0.34 levels RMS, a ceiling near 57.6 dB.
   - That is negligible at target B (45 dB). At target A (about 52-53 dB) it slightly penalises JPEG on YUY2 inputs and H.264/HEVC on MJPEG inputs.

## 10. CPU H.264/HEVC encoders in the PyAV 19.0.2 wheel and their licence

- measured: `libx264` and `libx265` are in `av.codecs_available`, and `libopenh264` is not (this sweep's environment probe; agrees with `results/licensing/FINDINGS.md` §2.5 and `results/hw_accel_target/sw_encoders_pyav19_win_amd64.json`).
- measured: both encode all-intra and decode back correctly (section 8).
- source/code (from `results/licensing/FINDINGS.md` §2.5, not re-checked):
  - the wheel ships `libx264-165-*.dll` and `libx265-*.dll`;
  - upstream FFmpeg lists libx264/libx265 as GPL-2.0 libraries that require `--enable-gpl`;
  - pyav-ffmpeg patches them into the version-3 list instead;
  - the DLLs cannot be removed without breaking `import av`.
  - So they are present but GPL, and H.264/HEVC also carry patent-pool licensing (same file, table at line 150). They are reference points for the CPU fallback cost, not a recommended path (G7).

## 11. `matched_settings.json` for the 23:00 bench

- Form: `{path: {input_class: {knob, value, bytes_per_frame, psnr_y, ssim_y, ..., options, pix_fmt_fed, gop_size, psnr45: {...}}}}`.
  - The top-level entry per input class is target A; the nested `psnr45` object is target B.
  - The key `_meta` (skip keys starting with `_`) holds the targets, the rules, and the camera passthrough bytes/frame.
- `options` is exactly what was passed:
  - PyAV `CodecContext.options` for FFmpeg encoders;
  - simplejpeg keyword arguments;
  - nvImageCodec `EncodeParams` fields.
- Feed full range to JPEG paths and limited range to H.264/HEVC paths, with `max_b_frames=0` and the given `gop_size`.
- Input classes map to the bench sources:
  - `yuy2_*` to the bench's `nv12` / `yuy2` sources;
  - `mjpeg_*` to `mjpeg_cpu` / `mjpeg_qsv` (decode first).
  - inferred: matched values transfer across these sources because the encoder sees the same samples.
- Per-camera curves are in `R/curves.json` (`per_camera`).

## 12. Limits and what is NOT VERIFIED

- Content:
  - two camera models (C930e, C922), one room;
  - the YUY2 sets are only 8 frames per camera, and the frames are noisy (high bitrate even at moderate quality);
  - the MJPEG sets are different captures from the YUY2 sets;
  - the 720p YUY2 class is derived by scaling.
- Matching is the nearest **swept integer** knob value. After two refine rounds the remaining gaps are single steps, listed in `R/refine_plan.json`, for example jpeg yuy2_720p q60 and nvjpeg mjpeg_1080p q54. The ratios use interpolated bytes at the exact target.
- No perceptual metric (VMAF is in the wheel's configure line per `results/licensing/FINDINGS.md`, not used). SSIM is on Y only.
- nvJPEG was fed host RGB (exact float BT.601). These were not tested:
  - a GPU-resident path (nvJPEG decode to device, then encode), which earlier gave 144,363 B at q90 4:2:2 for one 1080p frame (`results/gpu_encode/nvimgcodec_jpeg.md`);
  - a CUDA YUY2-to-RGB kernel;
  - newer nvImageCodec builds that might accept YUV.
- Not in this sweep:
  - `h264_mf` / `hevc_mf` (MF picks the NVIDIA MFT; `results/hw_accel_target/NOTES_functional.md`);
  - `*_d3d12va`;
  - libx264/libx265 4:2:2;
  - other x264/x265 presets;
  - QSV/NVENC presets other than the defaults and p4/ll.
- Encoder settings are tied to this machine (RTX 3070 driver 610.88; Intel UHD 770 driver 32.0.101.7088 per `results/hw_accel_target/NOTES_functional.md` §2). Other generations can produce different bytes at the same QP.
- nvidia-smi encoder sessions were 0-2 before and after each run (`R/raw/*.json`, `runs[].nvidia_smi_*`). Several sweep processes ran in parallel, so their NVENC sessions overlapped; the 12-session limit was never approached.
- No timing, no CPU cost, no playback test (Electron/Chromium). In particular, Chromium decoding of libx265's Rext all-intra streams and of HEVC Rext 4:2:2 is NOT VERIFIED here.
- `R/raw/` (about 15 MB, per-frame values) is rebuildable from the scripts and is not meant for commit.

## 13. Scripts and commands (repo root)

| script | does | writes |
|---|---|---|
| `S/iclib.py` | inputs, encode paths, decode-back, NAL/side-data checks, metrics | (library) |
| `S/sweep.py` | one or more paths x input classes x knob values; resumable | `R/raw/<path>__<input>.json`, samples |
| `S/run_refine.py` | runs `R/refine_plan.json` (`--only=`, `--per-path`) | (via sweep.py) |
| `S/analyze.py` | curves, matched settings, refine plan, verification | `R/curves.{json,md}`, `R/matched_settings.json`, `R/matched_summary.md`, `R/refine_plan.json`, `R/verification.md` |
| `S/camera_jpeg_quality.py` | camera bytes/frame, DQT to IJG q, camera-equivalent quality on YUY2 | `R/camera_jpeg_quality.{json,md}` |
| `S/knob_check.py` | i_qfactor effect, mjpeg knob, mjpeg_qsv knob | `R/knob_check.json` |
| `S/nvjpeg_rgb_diag.py` | nvJPEG RGB-route diagnostic | `R/nvjpeg_rgb_diag.json` |
| `S/dht_check.py` | Huffman/DQT tables of saved JPEG samples and camera JPEGs | `R/dht_check.json` |

```
uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_compare/camera_jpeg_quality.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_compare/sweep.py --paths <ids> --keep-media
uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_compare/analyze.py
python research/skellycam_recording/recording_upgrade/scripts/intra_compare/run_refine.py --per-path
uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_compare/analyze.py
```
