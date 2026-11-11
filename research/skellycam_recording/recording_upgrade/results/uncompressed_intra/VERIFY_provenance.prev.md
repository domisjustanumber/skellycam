# uncompressed_intra - provenance verification of FINDINGS.md

Verifier: adversarial provenance pass, 2026-11-09, machine Gerald. No timed benchmarks were run. Every result file cited by `FINDINGS.md` was opened and its numbers compared with the text. Primary sources were downloaded again and checked line by line. All paths are relative to `research/skellycam_recording/recording_upgrade/results/uncompressed_intra/` unless they start with `research/`.

Sources downloaded again on 2026-11-09 (scratchpad `verify_uintra_prov/`):
- `https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/` and `/n8.1.2/`: `libavformat/matroskaenc.c`, `libavcodec/nvenc.c`, `libavcodec/nvenc.h` (n9.0.2 only), `libavcodec/ffv1enc.c`, `libavcodec/mjpegenc_common.c`.
- `https://www.rfc-editor.org/rfc/rfc9043.txt`.
- `https://www.w3.org/Graphics/JPEG/jfif3.pdf`, text extracted with pypdf 6.1.1.
- The PyAV 18.0.0 wheel in the skellycam venv: `av/container/output.py`.

## Summary

- About 150 numeric claims were checked against the raw JSON. Nearly all match after rounding. This covers every bench median, size, core count, decode fps and prep time in §2.7, §3.1, §3.2 and §3.3, plus every functional-matrix size in §2.6.
- 5 claims are **refuted**: the result files say something different (table below).
- 10 claims are **weak**: the evidence exists but is thinner than the wording, or a label or citation is wrong (table below).
- Every source quote matches its primary source, including the RFC 9043 and JFIF quotes that FINDINGS marks "not re-fetched".

## Refuted

| # | FINDINGS claim | what the evidence says | correction |
|---|---|---|---|
| R1 | §2.4: under 50% truncation, "MKV/NUT/AVI decode 1-2 frames, all exact for lossless configs" | `functional_tables.md` (truncation table, PyAV 19.0.2): `ffvhuff_median.nut` and `jpegls.nut` on `bayer_rggb16le` each decode 2 frames, but only 1 is bit-exact. The partly written frame is returned with no error. `rawvideo.avi` on bayer_rggb16le decodes 0. `ffmpeg_cli_reference.json` `rawvideo_gray16_allow_raw_vfw.mkv`: 1 frame decoded, 0 exact. | "MKV/NUT/AVI kept 1-2 frames. Every complete frame was exact. ffvhuff and jpegls in NUT also returned the truncated last frame, silently corrupted." This matters for G2: the reader must validate the last frame. |
| R2 | §2.7 / §3.4: PyAV 19 vs 18 "fps within spread (... mjpeg 168 vs 149)"; "same sizes/speed" | mjpeg_q2 YUY2 1080p t1: PyAV 18 rep range is 132.62-158.05, PyAV 19 is 161.74-169.33. The ranges do not overlap. FFV1 s24 YUY2 t0 (not mentioned): 18 = 258.61-270.62, 19 = 217.98-234.65, also no overlap. Source: `bench/mjpeg_q2.mkv__yuyv422_1080p__t1__pyav{18.0.0,19.0.2}.json` and `bench/ffv1_l3_s24_crc_g1.mkv__yuyv422_1080p__t0__pyav*.json`, `stats.encode_fps`. Machine load also differed: sys CPU during mjpeg PyAV 18 reps was 49-72%, PyAV 19 27-38%. | "Sizes are identical. Some fps differences exceed the 3-rep spread (mjpeg t1 +13% on PyAV 19; FFV1 s24 t0 -15%). Load differed between runs, so no speed conclusion can be drawn." |
| R3 | §2.2: "PyAV refuses Matroska for ffvhuff, huffyuv, utvideo, magicyuv, jpegls, png, dnxhd; NUT and AVI accept them" | `pyav_mux_acceptance_{18.0.0,19.0.2}.json`: dnxhd is `refused` for nut and avi too (it is accepted only by mov). NOTES §2 repeats the same error. | "...NUT and AVI accept all of them except dnxhd, which PyAV accepts only in MOV." |
| R4 | §2.3: "no compressing encoder takes packed 4:2:2" | `pyav_caps_19.0.2.json`: the `hevc_qsv` encoder lists `yuyv422` among its formats. It could not be opened here ("MFX session -9"). libx264 and the NVENC encoders list `nv16`. | "No compressing encoder that opens on this machine takes packed 4:2:2. hevc_qsv lists yuyv422 but QSV is unavailable here (NOT VERIFIED)." |
| R5 | §5: "BENCH.md says 141 cases" | No "141 cases" text exists in `bench/BENCH.md`. Its run table adds up to 12+46+10+48+1+16+14 = 147 cases (441 reps), which matches the 147 JSONs. | Drop the bullet, or say "BENCH.md's run table totals 147 cases". |

## Weak

| # | claim | why weak | fix |
|---|---|---|---|
| W1 | §2.5: source nvenc.c:446-451 "YUV422P not supported", labelled "inferred: GPU capability, not FFmpeg limit" | The quoted check sits inside `#ifdef NVENC_HAVE_422_SUPPORT ... #else ret = 0; #endif` (n9.0.2 nvenc.c:445-453). Without that macro the message is printed with no GPU query. The macro is defined only for SDK >= 13.0 (nvenc.h:66-69). The inference does hold, but only via a step FINDINGS leaves out: both PyAV builds list `nv16` for h264/hevc_nvenc (`pyav_caps_*.json`), and nv16 is in the encoder's format list only when the macro is defined (nvenc.c:60-61). | Cite nvenc.h:66-69 and nvenc.c:60-61, and add the measured nv16-in-pix_fmts evidence. |
| W2 | §2.5: "hevc_nvenc 12-bit request produces yuv444p10le" | The matrix fed `yuv444p16le` (12-bit values in 16-bit words), not a 12-bit pix_fmt (`functional_matrix_pyav19.0.2.json`: target_pix_fmt yuv444p16le, decoded yuv444p10le). The `yuv444p12msble` request comes only from an unsaved CLI check (NOTES §10). | "hevc_nvenc fed 16-bit (12-bit-valued) 4:4:4 outputs yuv444p10le, not exact." |
| W3 | §3.1 Chromium column: x265 lossless "E45 only"; x264 qp0 ".mkv" row "4:2:0 lossless plays"; §3.3 hevc_nvenc lossless "E45 only", h264_nvenc lossless "plays" | `chromium_check_*.json` tested only HEVC intra 4:2:0 lossy (`hvc1.1.6.L120.90`), H.264 lossless 4:2:0 from libx264 in MP4, and H.264 intra 4:2:2 lossy. The table rows are 4:2:2 lossless x265 (Rext), 4:2:2 lossless x264 in MKV, and NVENC lossless output. None of these was played. | Mark these cells "not tested". Keep "plays" only where the exact profile and container were tested. |
| W4 | §2.6: "v4/v3 gray16 decode exact" | `ffv1_v4_cross_version_pyav18.0.0.json` records `frame0_bit_exact` only: 1 of 5 frames, a 320x240 random clip. | "frame 0 of 5 exact (320x240 random)". |
| W5 | §2.3: RFC 9043 §3.8.1.3 quote used for the gop=1 rule, while the recommendation is the rice (VLC) coder | The quote matches rfc9043.txt:977-978, but it covers the range coder only. The VLC equivalent is §3.8.2.5 (lines 1307-1308): "When "keyframe" ... value is 1, all VLC coder state variables are set to their initial state." §4.2.17 "intra" (lines 1747-1757), "keyframe MUST be 1 (keyframes only)", is also relevant. | Add the §3.8.2.5 quote. Drop "not re-fetched": both RFC quotes and the JFIF quote (printed p.3 = PDF page 4) were re-checked here and match. |
| W6 | §4 Implications 1-10 | These are recommendations with no `inferred` label. Examples: "Range coder only if CPU is spare", "No version bump required for G4". | Label each item `inferred (from §x)`. |
| W7 | §4.4: "481 MB/s minimum per-GiB sustained write ... inferred ~3 streams" | p12 phase A is "unbuffered+write-through, 4 MiB sequential" on C: at 94% full (`research/frame_ring_buffer/prototypes/results/p12_disk_sustained.md:3,7`). A PyAV muxer makes buffered writes of a different size, and C: now has 826 GB free (`bench/precheck_disk.txt`). Also 481/124.4 = 3.9, not ~3. | State the write mode and the fill difference. Keep it labelled inferred. Give the plain ratio. |
| W8 | §6 How to reproduce | The commands do not match what produced the results. `bench_py_still.py --frames 120 --workers 1,4,8` actually ran as 16 frames at 1 and 8 workers. `bench_debayer.py --frames 120` actually ran as 30 frames. `bench_suite.py --group ...` was run with `--sources/--configs/--skip-configs` filters (BENCH.md "What was run"). | Give the exact commands that were run. |
| W9 | §2.7: JXL e1 Bayer12 mosaic "2767 KB" attributed to `bench/py_still__uv.json` | That file has 2765943 B = 2766 KB. 2767 is the 1-frame value from `python_jpeg_libs_uv.json`. | Use 2766 for the bench figure. |
| W10 | NOTES.md (merged into FINDINGS) §5: "nvidia-smi ... was 0 sessions, 3-10 % around these tests" | `functional_matrix_pyav{18.0.0,19.0.2}.json` `nvidia_smi_before/after`: sessions 0-2 (1 session in 55/204 and 60/204 samples), utilisation 0-30% and 0-93%. NOTES §8 also quotes JPEG XL/XS mux errors ("codec jpegxl is not supported by this format") that differ from the saved `loose_ends_check.json` ("No bmp codec tag found for codec jpegxl"). FINDINGS correctly uses the saved text. | Correct NOTES, or mark it superseded by FINDINGS. Add to FINDINGS §5 that NVENC was also shared during the functional matrix. |

## Checks that passed (spot list)

- measured, all match: §2.7 YUY2 t1 fps (366/203/149/99/97/83/75/42-43/43), FFV1 range 27/29 fps, 1.10/1.00 cores, 370/373 KB (21%), t0 138/266/266, decode 417-443. Smallest-size ranking, slow-codec rows, NV12 rows, Bayer12/8 rows, NVENC rows (428/472/292/155/431 fps; 594/447/518/1423/59 KB; 720p 327-876). 720p rows, py_still rows, debayer ms.
- measured: prep_ms. Median over the 42 yuyv422 1080p de-interleave cases is 1.729 ms (1.455-3.692). 720p is 0.685, NV12 0.37.
- measured: `bench/precheck_typeperf.csv` mean 50.36%. Re-checks 24.3-52.3%. Per-rep sys CPU 13.0-99.0%. NVENC sessions = 3 before `h264_nvenc gray_720p` and after `hevc_nvenc_cq nv12_720p`. Case count 147 (56/49/16/14/12).
- measured: `pyav_caps_*.json`. libavcodec 62.28.102 / 63.1.102. libjxl, libaom-av1, libopenjpeg, librav1e and libsvtjpegxs are unavailable, and so are the jpegxl/jpegxs decoders. The only pix_fmt diffs are ffv1 +bayer_rggb16le and *_nvenc +p012le/p212le/yuv444p12msble. FFmpeg 8.1.2 / 9.0.2 come from `ffmpeg_version` in the bench JSON. `ffmpeg -version` 9.0.2 reports libavcodec 63.1.102.
- measured: `functional_tables.md` sizes in §2.6 (4147, 3110, 2467, 2413, 1839, 1620, 1601, 1625, 2819). The PyAV 18 v4 grayf16le note. The keyframe list (only ffv1_l1_gdefault). Container pix_fmt losses. The NVENC/QSV/AMF/MF error strings.
- measured: `ffmpeg_cli_reference.json` tags ULY2/FFVH/M8Y2/MJLS/[186]RG[8]/[186]RG[16], all exact. libaom gray12le 2136 KB exact, all-keyframe. libjxl, svtav1, rav1e, openjpeg results. allow_raw_vfw gives rgb555le.
- measured: `loose_ends_check.json`. YUY2 ranges (18..234 / 115..151; 16..235 / 95..181). PnP "Unknown Intel(R) UHD Graphics 770". Win32_VideoController lists Parsec + NVIDIA. The QSV d3d11va vendor 0x8086 error. CLI NVENC "No capable devices found". The hevc control returned rc 0. JPEG XL/XS mux errors.
- measured: `bayer_debayer_check.json`. 365/43.52 dB, 24/43.23 dB, BG 43.6-44.25, RG 20.33-20.35, only BG VNG 8-bit exact, VNG 12-bit assertion. 3736 / 940-1151 vs 2415/1079/1596/492 KB.
- measured: `python_jpeg_libs_{uv,venv}.json` and the `chromium_check_electron{35,45}.json` versions, results and checksums (1968455, 1968484, 1999082, 2011651) all match §2.8-§2.10.
- source, all match the re-fetched files: matroskaenc.c n9.0.2:2042-2043; ffv1enc.c n9.0.2:921-927, 652-653, 1693-1696; n8.1.2 ffv1enc.c has 0 "bayer" matches; mjpegenc_common.c n9.0.2:499-500; RFC 9043 line 162 "This document defines versions 0, 1, and 3 of FFV1."; JFIF printed p.3 "normalized so as to occupy the full 256 levels of a 8-bit binary encoding"; PyAV 18.0.0 `output.py:112-116`.
- code: `bench_intra.py:111-121` (prep timed outside the encode loop) and `:150-159` (encode loop); `uintra_frames.py` docstring (noise bits, 720p derivation).

## Verdict

FINDINGS.md is mostly well sourced. The numbers trace to raw files with very few rounding slips, and the source quotes are accurate. Five statements must be corrected before reuse:
- R1, the truncation exactness claim. It matters for G2.
- R2, PyAV 19 vs 18 speed.
- R3, dnxhd mux acceptance.
- R4, "no encoder takes packed 4:2:2".
- R5, the phantom "141 cases".

The Chromium cells for untested profiles (W3) and the unlabelled §4 implications (W6) need relabelling. None of these changes the main recommendations: FFV1 v3 g=1 in MKV for YUY2/NV12, quad-split FFV1 v3 for Bayer, no FFV1 v4.
