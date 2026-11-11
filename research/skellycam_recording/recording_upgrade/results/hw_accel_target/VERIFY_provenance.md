# hw_accel_target: provenance check of the draft FINDINGS.md

Verifier: adversarial, provenance lens. Date 2026-11-09. No timing was run. No earlier `VERIFY_provenance.md` existed, so nothing was renamed.

Method:
- Opened every cited result file and compared the numbers.
- Opened the saved source copies and checked the quotes:
  - `sources_nv_intel/*`;
  - scratchpad `hw_accel_target/src_nv_intel/`, `src_amd_apple/` and `findings_src/`.
- Re-fetched https://docs.nvidia.com/cuda/nvjpeg/index.html with WebFetch (2026-11-09).
- Opened the code at the cited file:line: `n902_nvenc.c`, `hwaccels_n9.0.2.h`, `allcodecs_n9.0.2.c`, `bench_encode_stream.py`, `pyav19_functional.py`.

`R` = `research/skellycam_recording/recording_upgrade/results/`.

## Verdict

The draft is mostly well sourced. 6 claims need correcting before it is final, and 10 are weak (wrong line numbers, mixed chroma bases, labels).

## 1. Refuted (needs correcting)

| # | draft claim | what the evidence says | correction |
|---|---|---|---|
| X1 | §3.4: hevc_nvenc is 55,112 (mjpeg_720p) and 144,376 (mjpeg_1080p), "from `matched_summary.md`" | `R/intra_compare/matched_summary.md:56` has 53,975 (0.89; 0.81), and `:80` has 141,655 (0.97; 0.87). The draft's values come from `R/intra_compare/NOTES.md:181`, which is out of date against matched_summary.md. Other NOTES §6 cells drift too: h264_nvenc yuy2_720p 83,921 vs 83,913, and the libx264_ultrafast / libx265 MJPEG cells | Use 53,975 and 141,655. Tell the intra_compare owner that NOTES §6 is out of sync |
| X2 | F9: QSV and NVDEC decode H.264, HEVC, VP9 and AV1 "bit-identically to software" | `R/hw_accel_target/functional_pyav19.md:359-360,366-367,380-381,387-388`: `h264_qsv`/`h264_cuvid`/`hevc_qsv`/`hevc_cuvid` have PSNR-Y 99 but **PSNR all (min) 63.3–63.7 dB**. Only VP9 and AV1 (`*_qsv`/`*_cuvid`) and native+hwaccel (d3d11va/d3d12va/cuda/dxva2) are 99/99. FN §4 has the same overstatement | "Y plane identical. All planes are identical for VP9/AV1 and for native+hwaccel. H.264/HEVC through `*_qsv`/`*_cuvid` give 63.3–63.7 dB on all planes; the cause is NOT VERIFIED (it could be the planes444 comparison)" |
| X3 | N10 [measured]: the 13th session fails "across nvenc/vulkan/d3d12va/mf" (`R/gpu_encode/nvenc_sessions.json`) | That file has `"pyav": "18.0.0"`, which is background only. The PyAV 19.0.2 files are `nvenc_sessions_19.0.2.json` (12 opened, the 13th failed) and `verify_method_pool.json`, which has a control: hevc_nvenc, h264_d3d12va and h264_mf fail, and h264_qsv still encodes. Vulkan is CLI-only with no control (`R/gpu_encode/FINDINGS.md:75-80`) | Cite the 19.0.2 files. Label Vulkan "CLI, no control (inferred to share the pool)" |
| X4 | A6 [code+measured]: no AMD path for 4:2:2 MJPEG decode is reachable from PyAV 19.0.2 | The parts (no `mjpeg_amf`, `hwaccels.h:54-55` has mjpeg only for nvdec/vaapi, no vaapi in the wheel) check out. AAC §2.4 (line 122) still marks the conclusion "**inferred** ... needs a functional test on AMD hardware ... NOT VERIFIED". The draft drops that marker | Label it [inferred from code+measured wheel contents]; NOT VERIFIED on AMD hardware |
| X5 | A1 and the §3.1 legend: "every AMD hardware codec is 4:2:0 only"; "'4:2:0 only' applies to every AMD cell" | AAC §2.2 says otherwise. Mesa `ac_video.c:540-545`: the VCN JPEG decoder outputs `y8u8y8v8_422` (YUYV). AMF-DOC v1.5.3 line 106: MJPEG "supports the `AMF_SURFACE_YUY2` format". A6 in the draft also says so | Limit "4:2:0 only" to the AVC/HEVC/VP9/AV1 encode/decode cells. AMD JPEG decode outputs 4:2:2 (Linux) |
| X6 | V4: "Camera JPEGs decode exactly through createImageBitmap / ImageDecoder: 800/800 seeks per path per browser" | The 800/800 seeks are on the **mjpeg_qsv 4:2:2 re-encoded** JPEG path (`R/intra_playback/NOTES.md` §2, "JPEG path: `mjpeg_qsv` from YUYV"). Camera JPEGs were tested as 88/88 still images per browser (`R/chromium_codecs/NOTES.md:150`) and as 450/450 byte-range fetches from MKV per browser (IP §1) | Split it: re-encoded JPEG path 800/800 seeks; camera JPEGs 88/88 decode and 450/450 byte-identical fetch+decode |

## 2. Weak (fix the wording or the citation)

| # | claim | why | fix |
|---|---|---|---|
| W1 | N5 `FP:313-314` | The cuvid and cuda error rows are FP:312-313. Line 314 is the native+qsv success row | FP:312-313 (also 321-322, 330) |
| W2 | F3 `FP:131, 157` | FP:131 is h264_qsv gop30 **sw, ok**. The hwctx failures are FP:125, 127, 134, 136, 145, 147, 149, 157, 159 | FP:125, 134, 157 |
| W3 | F4 av1_d3d12va `FP:297-300` | FP:297-299 are hevc_d3d12va successes. av1_d3d12va is FP:300-303 (and FP:201) | FP:300-303 |
| W4 | F6 `FP:315-318`; F1 `FP:130-166` | The native+qsv/d3d11va/d3d12va/dxva2 rows are FP:314-317 (line 318 is a 1080p CPU row). The h264_qsv encode rows start at FP:124 | FP:314-317; FP:124-166 |
| W5 | Q7 and implication 2: JPEG costs "1.7–2.6x" the bytes of H.264/HEVC | This compares 4:2:2 libjpeg-turbo with 4:2:0 H.264/HEVC, so chroma is not matched. From matched_summary.md:11-25: at 4:2:0, jpeg_turbo_420 (0.89) is 1.5–2.3x. The hardware JPEG paths named in implication 2 (nvJPEG 4:2:0 0.74, mjpeg_qsv 4:2:0 1.00) are 1.25–2.6x. At 4:2:2, jpeg_turbo_422 vs hevc_qsv_422 (0.52) is 1.9x | State the chroma basis, or give the 4:2:0-matched range |
| W6 | Implication 3: re-encoding saves "0–36%" at A (Q4) | Against passthrough, Q4's ratios are 0.64–0.91, which is 9–36%. The "0" comes from the libjpeg-turbo ratio (1.02) | "9–36% vs the camera's bytes" |
| W7 | N6, N7, N9 cite the nvJPEG **13.5** docs | The measured stack is `nvidia-nvjpeg-cu12==12.4.0.76` (`R/gpu_encode/NOTES.md` §6). The saved 13.5 copy also says that for `NVJPEG_INPUT_NV12` the subsampling "must both be NVJPEG_CSS_420", so NV12 input cannot give 4:2:2. Planar `nvjpegEncodeYUV` exists in 13.5; it is NOT VERIFIED in 12.4 | Note the version gap. In N9 and implication 4, say that NV12 input means 4:2:0 output |
| W8 | J5 and I6 are labelled [source] | NI marks the oneVPL statements "source (transcribed)" (intel.com returned 403, so they were read through WebFetch's small model) | Label them [source (transcribed)] |
| W9 | I5 attaches the quote "Intel® Quick Sync Video": "No" to i5-10400F through Core Ultra 7 265KF | Per NI §5, that quote is on the 265KF page only. The others show "no GPU section" | Attribute the quote to the 265KF only |
| W10 | §2.6 and the §3.1 AMD rows | Vendor-vs-vendor disagreements in AAC are not flagged. AMFW gives Navi24 (VCN 3.0) AV1 decode "8,10b", but the kernel `nv.c:182-184` bg table has no AV1; the draft's cell follows the kernel without saying so. Cezanne and Granite Ridge VCN versions also differ (AAC §2.1). In C1, the libx264/libx265 4:2:2 cell is blank, but `sw_encoders_pyav19_win_amd64.json` lists yuv422p | Add a J row (vendor vs vendor, AMD). Fill in the 4:2:2 cell |

Minor wording issues:
- N1 says "every RTX 3000". It rests on 2 matrix rows (3050, 3070) plus the app note's per-architecture grouping, so "representative rows" (§6) should be stated next to it.
- §3.1 marks the Intel TGLx AV1 cells "(measured)", but only RPL-S was measured.

## 3. Checked and correct

- N2, N3, N4, N5 (source), N11: they match `sources_nv_intel/nvidia_support_matrix_extract.md`, `nvenc_app_note_13.1_tables.md` and the scratchpad `nvsdk131_*` text. The text has "NVENC can encode H.264 8-bit ... AV1 10-bit contents" at line 21, "limited to 12 per system" at line 396, and "Hybrid (CUDA + CPU) JPEG" in the NVDEC programming guide at line 43.
- N6, N7, N9 quotes:
  - present verbatim in `findings_src/nvjpeg_index.txt`;
  - the HTML's sha256 is `5d2f3d74…db5ef`, which matches the draft;
  - the live re-fetch confirms the decode list (Ampere A100/A30, Hopper, Ada, Blackwell, Jetson Thor), "encode is available on Jetson Thor, running Linux ARM64" and v13.5;
  - "NVJPEG_ENC_BACKEND_GPU Always use CUDA encoder." is in the saved copy.
- N8: `R/gpu_encode/nvimgcodec_jpeg.md`: nvjpeg_cuda_encoder CSS_422/420 ok, GPU-resident ok, P_YUV/I_YUV "encode returned None", and nvjpeg_cuda_decoder decodes the camera 4:2:2 JPEGs.
- I1–I4: the README excerpt lines (file line + 69 = README line) give JPEG L115, HEVC 8bit 422 L118, VP9 L126-129 and AV1 L132-133, as the draft says. media_features.md L79 matches verbatim.
- I7 matches `vulkaninfo_video_ext.txt`: the UHD 770 lists decode extensions only.
- J7: the grep `vp9|jpeg|4:2:2|422` over `sources_nv_intel/jellyfin_*.txt` returns 0 matches in all 4 files (re-run here). J2, J3, J4 and J8 match NI §3 and AAC §2.3.
- F1, F2, F5 (PSNR-Y 66.94/67.15/69.48), F7 (FP:193, 200, 292-298, 540, 553) and F8 (FP:374) match.
- Q1–Q6 match `matched_summary.md` and IC NOTES §1, §7, §9.3. Recomputed here:
  - nvJPEG 0.81–1.24x and its PSNR-Y deficit of 1.4–2.2 dB;
  - mjpeg_qsv 0.99–1.12x;
  - 4:2:2 costs 7–17% for JPEG and 13–33% for hevc_qsv.
- The other §3.4 cells match `matched_summary.md`.
- K3 and K4: `n902_nvenc.c:1764-1766` (`gop_size == 0` gives `gopLength = 1`). K1 and K2 match FN §6.
- R1–R5 match `R/licensing/FINDINGS.md` Q17/18/29/31-34/49/51/52/01/04/07/12 and §2.5. R4's DLL-strip result is PyAV 19.0.2 with a control run.
- V1–V3 and V5 match IP §1 and CC §3 (line 117 FFmpegVideoDecoder for H.264 4:2:2; line 122: E35 reports HEVC Rext unsupported, and no clip was played).
- P3: JFF §3 line 70 lists patch 0047 `mjpeg_videotoolbox` with `allow_sw`. Its input formats are videotoolbox/nv12/yuv420p, so it is 4:2:0 only; worth one word in P3.
- §5 gaps: `bench_encode_stream.py:49-66` has no nvjpeg or turbo entry, empty QSV options and no `i_qfactor` anywhere in the bench scripts (grep).
- No PyAV 18 result is presented as primary except X3.
