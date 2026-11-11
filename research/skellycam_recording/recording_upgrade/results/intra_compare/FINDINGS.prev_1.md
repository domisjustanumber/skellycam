> **Draft, not yet verified** (returned by the workflow agent on 2026-11-09 as its summary; saved by the main session). Provenance/method verification runs after tonight's bench.

The intra_compare sweep is finished, and `matched_settings.json` is written for tonight's bench. Every output decoded back in PyAV 19.0.2 software decode with the right frame count; there were 0 failed points. No timing numbers were recorded. NOTES.md is written; this text is the FINDINGS for the main session to save (the write guard blocks me from creating FINDINGS.md).

# intra_compare FINDINGS (PyAV 19.0.2, functional, no timing)

`R` = research/skellycam_recording/recording_upgrade/results/intra_compare/, `S` = research/skellycam_recording/recording_upgrade/scripts/intra_compare/

## What was run
- measured: 994 points (73,556 frame encodes) over 16 intra-only paths and 4 input classes, all decoded back in PyAV 19.0.2 software decode with frames out = frames in (`R/verification.md`).
- measured: every H.264/HEVC packet's VCL NAL units are IDR, SPS/PPS(/VPS) repeat in every packet, decoder `has_b_frames=0`, and every decoded frame is a key frame with pict_type I. ffprobe of the saved samples agrees (`R/verification.md`).
- Paths:
  - CPU JPEG: libjpeg-turbo 3.1.2 via simplejpeg 1.9.0, from YUV planes, 4:2:2 and 4:2:0; FFmpeg `mjpeg` 4:2:2 and 4:2:0.
  - Hardware JPEG: `mjpeg_qsv` (yuyv422 4:2:2 / nv12 4:2:0); nvJPEG via nvidia-nvimgcodec-cu12 0.10.0.9 (CSS_422 / CSS_420).
  - Hardware H.264/HEVC: `h264_nvenc`, `hevc_nvenc`, `h264_qsv`, `hevc_qsv` 4:2:0, and `hevc_qsv` yuyv422 (Rext 4:2:2).
  - CPU H.264/HEVC: libx264 ultrafast and veryfast, libx265 ultrafast.
  - PyTurboJPEG 2.6.1 was not used: it needs a system turbojpeg DLL, which is not installed.
- Inputs: real YUY2 1080p (16 frames), YUY2 720p (derived by swscale, as in the bench), decoded camera MJPEG 720p (c930e + c922, 120 frames each) and 1080p (19 + 19).
  - JPEG paths are fed full range; H.264/HEVC paths are fed limited range. All conversions are explicit numpy (`S/iclib.py`).
  - For the MJPEG classes the metrics are generation loss against the decoded camera frame.

## Targets
- **Target A, camera-equivalent: SSIM-Y 0.9961.**
  - measured: the camera DQT tables are nearest IJG q94 in all four sets (not exact).
  - measured: libjpeg-turbo q94 on the same camera models' raw YUY2 reaches SSIM-Y 0.99694 / 0.99520 and PSNR-Y 52.65 / 51.83 dB (`R/camera_jpeg_quality.md`).
- **Target B: PSNR-Y 45 dB.** measured: on this content B is lower quality than A.
- The task's other example, SSIM-Y 0.98 / PSNR-Y 40 dB, lies below even libjpeg-turbo q50 here (45.6 dB, SSIM-Y 0.988), so it was not used.

## Results (bytes/frame interpolated to the target; ratio to libjpeg-turbo 4:2:2; `R/matched_summary.md`)

| path | A, YUY2 1080p | B, YUY2 1080p |
|---|---|---|
| libjpeg-turbo 4:2:2 | 297,359 (1.00) | 77,458 (1.00) |
| libjpeg-turbo 4:2:0 | 265,001 (0.89) | 68,773 (0.89) |
| mjpeg_qsv 4:2:0 | 296,502 (1.00) | 68,415 (0.88) |
| nvJPEG 4:2:0 | 221,461 (0.74) | 71,551 (0.92) |
| h264_nvenc | 157,840 (0.53) | 22,392 (0.29) |
| h264_qsv | 175,094 (0.59) | 27,378 (0.35) |
| hevc_nvenc | 129,131 (0.43) | 14,290 (0.18) |
| hevc_qsv 4:2:0 | 116,646 (0.39) | 14,236 (0.18) |
| libx264 veryfast | 164,862 (0.55) | 27,722 (0.36) |
| libx264 ultrafast | 244,910 (0.82) | 55,449 (0.72) |
| libx265 ultrafast | 146,521 (0.49) | 19,518 (0.25) |

- measured: on decoded camera MJPEG at target A, every re-encode path except libx264 ultrafast, libx265 ultrafast and nvJPEG 4:2:2 at 1080p is smaller than the camera's own JPEG (passthrough 66,594 B/frame at 720p, 163,478 at 1080p):

  | path | 720p (x passthrough) | 1080p (x passthrough) |
  |---|---|---|
  | libjpeg-turbo 4:2:2 | 60,318 (0.91) | 145,774 (0.89) |
  | h264_nvenc | 46,217 (0.69) | 123,426 (0.76) |
  | hevc_qsv 4:2:0 | 42,502 (0.64) | 110,835 (0.68) |

  At target B the H.264/HEVC paths are 0.07-0.17x passthrough.
- measured: hardware JPEG size against libjpeg-turbo at the same chroma:
  - mjpeg_qsv is 0.99-1.12x;
  - nvJPEG is 0.81-1.24x, with PSNR-Y 1.4-2.2 dB lower at equal SSIM-Y (a colour-conversion bias; `R/nvjpeg_rgb_diag.json`).
- measured: 4:2:2 costs 7-17% more bytes for JPEG at the same knob, with identical Y and PSNR-YUV against the 4:2:2 source up by 0.33-1.78 dB. hevc_qsv 4:2:2 costs 13-33% more.
- measured: hevc_nvenc is worse than h264_nvenc at target A on MJPEG inputs, but better at target B and on YUY2.
- measured: libx264 and libx265 are in the PyAV 19.0.2 wheel and libopenh264 is absent. Their GPL status is per `results/licensing/FINDINGS.md` §2.5.

## Pitfalls
- measured/code: FFmpeg's default `i_qfactor=-0.8` makes NVENC constqp and QSV CQP code intra frames at 0.8x the requested QP; x264/x265 apply ipratio 1.4 instead. QP 25 becomes intra QP 20 or 22 (`R/knob_check.json`; nvenc.c:835-836, qsvenc.c:922-929, options_table.h:151, n9.0.2, excerpts in `R/ffmpeg_n9.0.2_knob_excerpts.txt`). The fix is `i_qfactor=1, i_qoffset=0`, and every H.264/HEVC entry in `matched_settings.json` includes it.
- measured: FFmpeg `mjpeg` ignores `+qscale`/`global_quality` passed as codec options; `qmin=qmax` is the working knob.
- measured: feeding nvJPEG RGB made by PyAV swscale caps PSNR-Y at 46.7 dB (mean Y error -1.13). An exact float BT.601 conversion gives 63.1 dB, so the sweep uses the exact conversion.
- measured: libx265 all-intra 4:2:0 streams are Rext profile, not Main.
- measured: FFmpeg `mjpeg` defaults to `huffman=optimal` in source (mjpegenc.c:650), yet every sample from every JPEG encoder, and the camera JPEGs, uses the standard Annex K Huffman tables (`R/dht_check.json`).

## Matched settings
- `R/matched_settings.json` has the form `{path: {input_class: {knob, value, bytes_per_frame, psnr_y, ssim_y, psnr_yuv_422, encoder, chroma, pix_fmt_fed, gop_size, options, target, delta, bytes_at_target_interp, psnr45: {...}}}}`.
- The top-level entry per input class is target A; the nested `psnr45` object is target B; the `_meta` key holds the targets and the passthrough bytes.
- Input classes: yuy2_1080p, yuy2_720p, mjpeg_720p, mjpeg_1080p.

## Limits
- Two camera models in one room; the YUY2 sets are 8 frames per camera and noisy.
- Matching uses the nearest integer knob value; the remaining single-step gaps are in `R/refine_plan.json`.
- nvJPEG was fed host RGB, not a GPU-resident path.
- Not in the sweep: MF and d3d12va encoders; libx264/libx265 4:2:2; other presets.
- No timing, CPU cost or playback tests. `R/raw` (about 15 MB) is rebuildable.

## Files
- Scripts in `S`: iclib.py, sweep.py, run_refine.py, analyze.py, camera_jpeg_quality.py, knob_check.py, nvjpeg_rgb_diag.py, dht_check.py.
- Results in `R`: NOTES.md, matched_settings.json, matched_summary.md, curves.md/.json, verification.md, camera_jpeg_quality.md/.json, knob_check.json, nvjpeg_rgb_diag.json, dht_check.json, ffmpeg_n9.0.2_knob_excerpts.txt, refine_plan.json, raw/.
- Sample media: C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/intra_compare/samples/ (56 MB).
