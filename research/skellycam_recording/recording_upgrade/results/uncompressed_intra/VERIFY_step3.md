# uncompressed_intra: step 3 verification (provenance + method), 2026-11-10

Scope: only the claims added or changed by gap-fills GF05 and GF09 in the new FINDINGS draft. No timed measurement was run. Paths are relative to `research/skellycam_recording/recording_upgrade/results/uncompressed_intra/` unless they start with `results/` or `scripts/`.

## What was checked

| claim area | evidence opened | result |
|---|---|---|
| QSV: 33 configs, 32 encoded 300 frames, 0/300 exact in all | `gapfill/GF09_rows_qsv_pyav19.0.2.json` (all 33 rows parsed) | matches; the 33rd row (`hevc_qsv__cqp_qp1_lp0__bayer8_quad_as_vuyx`) opened and failed on `avcodec_send_frame()` with "Invalid FrameType:0." |
| QSV: smallest max abs diff 2; PSNR-Y min 65.42 (Bayer8 quad), 65.33 (NV12, YUY2) | same | matches |
| QSV table in §2.5 (QPI, VDENC, KB/frame, max abs Y) | same, `libav_param_dump` | all four rows match (437.6/562.9, 532.9, 332.7/427.3, 164.6/164.6, 201.7, 306.7; QPI 1/4/10/10; diffs 2/3/4/3) |
| QP 0 runs at QPI 1; QP 0 = QP 1 in size and error | same | matches |
| low_power=1: QPI 10 for both; MinQPI 10 only on hevc_qsv | same | matches (h264_qsv reports MinQPI 0) |
| VUYX always VDENC ON at QPI 10; fails with low_power=0 | same | matches |
| hevc_qsv lp1 on YUY2 writes Main 4:2:0, `libav_warnings` empty | same (ffprobe `profile` Main, `yuv420p`) | matches |
| closest approach: hevc Rext 4:2:2 from YUY2, 65.33 dB, diff 2,1,2, 562.9 KB | same | numbers match; wording issue, see W1 |
| all QSV rows 300/300 keyframes | same | true for the 32 rows that encoded; see W2 |
| UHD 770 driver 32.0.101.7088 | `gapfill/GF09_gpu_drivers.json` | matches |
| "lossless" count 0 in qsvenc.c/.h, qsvenc_h264.c, qsvenc_hevc.c, qsv.c | re-fetched from `https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/libavcodec/` 2026-11-10 | 0 in all five; re-fetched qsvenc.c SHA-256 4feac182... equals the step3 copy |
| qsvenc.c:929-931 (H.264/HEVC clip 0..51), :925-927 (AV1 `av_clip_uintp2(...,8)`) | re-fetched qsvenc.c | text matches at those lines |
| qsvenc_h264.c:152-156 profiles; :202 `CODEC_PIXFMTS(AV_PIX_FMT_NV12, AV_PIX_FMT_QSV),` | step3 copy | matches (152 is the `profile` option, 153-156 the four constants) |
| oneVPL mfxstructures.h v2.15.0:913 "Zero QP is not valid ..." and :918 AV1 lossless | re-fetched from the cited URL 2026-11-10 | SHA-256 d0d31b20... equals the step3 copy; both quotes exact at 913 and 918 |
| AVOptions: no "lossless" option on h264_qsv (48) / hevc_qsv (46) | `gapfill/GF09_avoptions_pyav19.0.2.json` | matches |
| NVENC lossless: 12 rows, 300/300 exact for sw/cuvid/cuda; d3d11va fails on all 5 H.264 rows, exact on 7 HEVC rows | `gapfill/GF09_rows_nvenc_pyav19.0.2.json` | matches |
| KB/frame equals timed JSON to 0.1 KB | the 10 `bench/*nvenc_intra_lossless*_q2300.json` `stats.bytes_per_frame` | equal to the byte (e.g. 593,569.7 / 593.5697 KB) for all 10 |
| Bayer8 quad 772.6 / 685.1 KB, exact | same GF09 file | matches |
| bench config and method citations | `scripts/uncompressed_intra/functional_matrix.py:53, 83-84`, `bench_intra.py:108`, `bench_suite.py:57-61`, `gapfill/GF09/gf09_lossless_check.py:159` (`thread_count = 1`), `:200` (`allow_software_fallback=False`) | match |
| Chromium: E35 (Chrome 134.0.6998.205) and E45 (156.0.8078.80); both clips play to `ended` from MKV and MP4; no error; 60/60; readback 0/1/7 exact; WebCodecs exact | `gapfill/GF09_chromium_electron{35,45}.json` | matches |
| decoders: H.264 FFmpegVideoDecoder (platform false), prefer-hardware "Unsupported configuration"; HEVC D3D11VideoDecoder (platform true), prefer-software fails | same | matches |
| HEVC dropped 1 frame in E35 MKV and E45 MP4 | same | matches; see W3 |
| E35 `canPlayType('video/x-matroska...')` = "" yet MKV plays from `src` | same; `page.js:77` `v.src = ...` | matches |
| media = first 60 packets, stream copy; codec strings from avcC/hvcC | `scripts/.../GF09/prep_chromium.py:8, 40, 67-78`; manifest `extradata_hex_head` 01f40028..., 0101600000009... | matches |
| media self-check | `gapfill/GF09_chromium_media_check.json` | 4 cuts x frames 0/1/7 exact |
| readback compares YUV only | `page.js:13-42` `compareFrame` (NV12/I420 only, copyTo) | matches |
| av1_qsv does not open | `qsv_recheck_pyav19.0.2.json` row av1_qsv: "NotImplementedError ... Function not implemented: 'avcodec_open2(\"av1_qsv\", {})'" | matches |
| cross-reference "AV1 fails on RTX 3000" | `results/hw_accel_target/FINDINGS.md:44` (N2) and `:417` | present |
| GF05: hevc_intra_420.mp4 is `profile=Rext`, hvc1, yuv420p, 8 frames all I | `results/chromium_codecs/gapfill/GF05_ffprobe_hevc_intra_420.txt` | matches (ffprobe used to inspect only) |
| GF05: generator declares `hvc1.1.6.L120.90` | `scripts/uncompressed_intra/make_chromium_samples.py:46` | matches |
| GF05: fails E35, plays E45 | `chromium_check_electron35.json` (DEMUXER_ERROR_NO_SUPPORTED_STREAMS), `chromium_check_electron45.json` (seeked, 1920x1080); `results/intra_playback/FINDINGS.md:80` (F16) | matches |
| GF05: "Main" came from VERIFY_method.prev.md:28 (R1), now annotated; VERIFY_method.md:28 lacks it; NOTES.md:209 no profile | those lines | matches |
| timing rule | all new claims | no fps, duration or CPU figures introduced |

## Refuted

None. Every new number and quote matched its file.

## Weak (fix before saving)

- **W1 "closest approach" (§2.5).** The draft names hevc_qsv Rext 4:2:2 from YUY2 (65.33 dB, 562.9 KB) as QSV's closest approach, while the header says the highest PSNR-Y min is 65.42 dB (Bayer8 quad). Every hevc QPI-1 row has max abs diff 2 on Y; hevc NV12 has the same 65.33 dB at 437.6 KB with diffs 2,1,1. Fix: "At QPI 1 every hevc_qsv row has max abs diff 2 (PSNR-Y min 65.33-65.42 dB). On camera YUY2 the best is Rext 4:2:2 at 65.33 dB, diffs 2,1,2, 562.9 KB/frame."
- **W2 "every QSV row is all-intra, 300/300".** True for the 32 rows that encoded; the failed row wrote no packets. Fix: "every QSV row that encoded (32/33)".
- **W3 dropped-frame count (§2.11).** `droppedVideoFrames` during real-time playback depends on machine load, and other agents ran concurrently. It is a count, but it carries timing. Also `decodedFrames` is `totalVideoFrames` (`page.js:87`), which counts dropped frames too. Fix: keep it only as "(load-sensitive, concurrent run; not a performance result)", or drop it. Say "60 frames reported (`totalVideoFrames`)" instead of "60/60 decoded".
- **W4 NVDEC caveat dropped (§4.1, §6).** GF09 itself says NVDEC use was not checked with nvidia-smi, "NOT VERIFIED beyond PyAV's flag" (`gapfill/GF09_qsv_lossless.md` §2). For cuvid the decoder name is enough. For the `cuda` and `d3d11va` hwaccel rows, the draft should keep "PyAV `is_hwaccel=True`, frames returned as nv12/p010le".
- **W5 "flag closed" (§5) is an inference.** The timed streams were deleted. GF09 checked re-encodes made with the same settings, and only the byte-equal KB/frame links them. Fix: label it "**inferred** (same config and path code, KB/frame equal to the byte): the HANDOFF §5 flag is closed for the NVENC lossless rows".
- **W6 scope of the hardware decode results (§4.1).** The d3d11va rejection of H.264 Hi444PP and Chromium's software-only H.264 / hardware-only HEVC choice are measured on one RTX 3070 (driver 610.88) only. Add "on this RTX 3070". Other GPUs, including Intel D3D11VA, are NOT VERIFIED.
- **W7 §4.10 wording.** "verified YUV readback" rests on 3 seeked frames (0, 1, 7) of 60-frame cuts. Add "(3 frames per file)" so it does not read as full-stream verification.
- **W8 stale §3.4 row (flagged by the reviser, unchanged).** "Electron 35.7.5 -> 45.2.3: HEVC 4:2:0 playback" is now contradicted by the evidence. GF09 shows HEVC Main lossless 4:2:0 playing in E35, and GF05 shows that the E45-only sample is libx265 Rext. Fix: "libx265 Rext 4:2:0 playback (HEVC Main already plays in E35)".

## Verdict

PASS WITH FIXES. Provenance is clean: every new file exists, every number matches, and the re-fetched FFmpeg n9.0.2 and oneVPL v2.15.0 sources are byte-identical to the copies quoted. The quotes are exact at the cited lines. The labels are right except W4 and W5. No timing claim was introduced, apart from the load-sensitive dropped-frame count (W3). Apply W1-W8. W8 is outside the requested changes but now contradicts them.
