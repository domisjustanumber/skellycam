# gpu_encode: step 3 verification (provenance + method)

**Date:** 2026-11-10.
**Scope:** only the claims that are new or changed in the step 3 draft (GF03, GF05, GF06, GF07; GF04 = no change).
**How:** read-only checks of the cited result files, the GF03/GF06/GF07 excerpt files, and the raw scratchpad downloads under `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step3/` (sha256 matched against `GF06_sources/FETCH_MANIFEST.txt` for the FFmpeg and AMF files). No tests, no timing, no network.

## 1. Verdict

**Pass with minor fixes.** Every quote, number, line number and file in the step 3 fold exists and says what the draft says. No timing claims were added. There is 1 wrong citation path. There are 7 places where the wording goes further than the source or leaves out context; each is fixed by rewording.

## 2. Confirmed

| claim (draft section) | check | result |
|---|---|---|
| 12.4.0.76 = CUDA 12.9.1 libnvjpeg; CUDA 12.4 = 12.3.1.89 (2.7) | raw `dl/redistrib_12.9.1.json` / `12.4.0.json` → `libnvjpeg.version`; `GF03_wheel_arch_facts.json` → `redistrib_libnvjpeg` | 12.4.0.76 / 12.3.1.89. Confirmed (the bare R04/R05 quotes do not show the key, but the raw JSON does) |
| `[nvjpeg]` extra unpinned, G04 (2.7) | `GF03_quote_verification.json` G04 `found_verbatim: true`; `GF03_sources/nvimgcodec_METADATA.txt.excerpt.txt` | confirmed |
| NOTES.md:148 resolved 12.4.0.76 (2.7) | `results/gpu_encode/NOTES.md:148` | confirmed |
| `nvjpeg.h:154, 159, 540, 560` (2.7) | `GF03_sources/nvjpeg_h_12.4.0.76_lines.txt` | `NVJPEG_INPUT_YUV`, `NVJPEG_INPUT_NV12`, `nvjpegEncodeYUV`, `nvjpegEncode`. Confirmed |
| R19 quote (2.7, 6.2) | quote verification + raw `nvimgcodec_release_notes_v0.10.0.txt:75` | verbatim. Context problem, see W1 |
| R21 quote (2.6) | raw `cuda_12.9.1_relnotes.txt:1152` | verbatim. It is in section "nvJPEG: Release 12.9" (line 1149), not "12.9 Update 1". See W2 |
| R06, R09 quotes (2.12, 3.4) | quote verification | verbatim |
| SASS sm_75/86/89/120 in `nvjpeg64_12.dll` (2.12, 3.4) | `GF03_wheel_arch_facts.json` → `fatbin` | 11 fatbins; SASS 50…121 including 75, 86, 89, 120. Confirmed. The "own parser, not cross-checked with cuobjdump" caveat is kept in 2.12 |
| W10 quote and "§2.11", "(v. November 28, 2023)" (6.2) | raw `work/lic/nvimgcodec_LICENSE.txt:55`, `:113` | verbatim; numbered 2.11. Confirmed |
| hevc_qsv 4:2:2 fails in E35/E45, 4:2:0 control plays (6.2) | `chromium_codecs/FINDINGS.md:116-122` (C17); `chromium_codecs/raw/verify_method_rechecks.json` | E35 error 4 `DEMUXER_ERROR_NO_SUPPORTED_STREAMS`; E45 error 3 `PIPELINE_ERROR_DECODE`; control `loadeddata` true in both. Confirmed. Key path wrong, see R1 |
| old pointer "intra_playback FINDINGS line 64" is stale (6.2) | `intra_playback/FINDINGS.md:60-66` | line 64 is now about F11; HEVC 4:2:2 is at line 258. Confirmed stale |
| h264/hevc_amf resolve, long names, `rc`/`qp_i`/`qp_p`/`forced_idr` (3.5) | `GF06_pyav_options.json` | confirmed ("AMD AMF H.264 Encoder", "AMD AMF HEVC encoder"; av 19.0.2, libavcodec 63.1.102, "static query only") |
| old 3.5 short-name column had h264/hevc/vp9_amf | current `FINDINGS.md:382` | confirmed; new column `vp9_d3d12va, vp9_amf` is consistent |
| AMF `amfenc_h264.c:574-576`, `:377-378`; `amfenc_hevc.c:298-301`, `:523-524` (I6) | raw `GF06/ff/*.c` (sha256 = manifest) | gop_size → `IDR_PERIOD` / `HEVC_GOP_SIZE`; `qp_i` → `QP_I`. Confirmed |
| AMF SDK v1.5.3 H264 doc:1417, HEVC doc:1266 (I6) | raw `GF06/amf/*.md` (sha256 = manifest) | 1417 under `AMF_VIDEO_ENCODER_IDR_PERIOD` (heading line 1403): "IDRPeriod = `0` turns IDR off". 1266 under `AMF_VIDEO_ENCODER_HEVC_GOP_SIZE` (line 1252): "`0` means only insert the first IDR/CRA". Confirmed |
| VT `videotoolboxenc.c:1379-1395`, `:1250-1261`; `options_table.h:96` default 12 (I6) | raw `GF06/ff/` | confirmed (`gop_size > 0` → MaxKeyFrameInterval; `global_quality` → Quality capped at 1.0; `{.i64 = 12 }`) |
| "BaseFrameQP unused"; AMF/VT never read `i_quant_factor` (I6) | grep raw `videotoolboxenc.c`, `amfenc*.c`, `amfenc.h` | 0 matches each. `nvenc.c:835-836` and `qsvenc.c:925,929` do read it. Confirmed |
| RPL/MTL/ARL-S JPEG rows and API lines (2.12) | `GF07_sources/04-06_*.md` | verbatim |
| LNL "low-power low-latency … AVC, HEVC, and AV1." (2.12) | raw `step3/GF07/dl/lnl_ds_encode.txt:969` | verbatim. The "Confidential" label is disclosed |
| KB 000098345 OS line; Arc B VP9 "Not Supported"; no JPEG row (2.12) | `GF07_sources/08_*.md` | present. Context problem, see W4 |
| Arc A JPEG from oneVPL doc (3.4) | `GF07_sources/01_*.md:26-28`, `02_*.md:17` | MJPEG encode ticks for Arc A. Confirmed |
| GF04: no change needed | `GF04_capacity.json` (12 NVENC streams at N=16 for MJPEG→h264_nvenc, 4.06 cores, 596 fps) | matches §2.8 / §3.2 |
| no new timing | whole fold | no new timed numbers; all new labels are source/code/static/inferred |

## 3. Refuted

- **R1 (6.2, GF05 bullet).** The draft cites `results/chromium_codecs/raw/verify_method_rechecks.json` → `play_file_url`. The file has no top-level `play_file_url`; its top-level keys are `when, machine, note, filefetch_range, hevc422_probe_and_play`. The data is at `hevc422_probe_and_play.play_file_url`. The same wrong path is in the Verification "Step 3 gap-fill" GF05 line.
  - Correction: cite `verify_method_rechecks.json` → `hevc422_probe_and_play.play_file_url`.

## 4. Weak (wording goes further than the evidence)

- **W1 (2.7 YUV bullet; 6.2 nvJPEG sub-bullet). R19 is quoted out of context.**
  - The sentence is about a new 0.10 feature: planar RGB/BGR is interleaved on the GPU for encoders that accept only interleaved samples (nvTIFF). "Planar YUV (P_YUV) is not converted" means this feature leaves P_YUV out (raw `nvimgcodec_release_notes_v0.10.0.txt:75`). It does not say that nvImageCodec rejects YUV input to nvJPEG.
  - The measured rejection also covers `I_YUV` (`nvimgcodec_jpeg.md:41-42`), which R19 does not cover.
  - 6.2's paraphrase "nvImageCodec 0.10 does not convert P_YUV" drops the context.
  - The more relevant 0.10 line is R20: "Encoding a chroma-subsampled Image is not supported yet and raises ValueError."
  - Fix: either quote R19 with its context ("in the new planar→interleaved fallback for interleaved-only GPU encoders, P_YUV is not converted"), add R20, and say why I_YUV is rejected is NOT VERIFIED; or drop R19.
- **W2 (2.6 R21 lead). The version link is inferred, but code could show it.**
  - R21 is in the "nvJPEG: Release 12.9" section (libnvjpeg 12.4.0.16 per `redistrib_12.9.0`). The measured 12.4.0.76 is 12.9 Update 1, so "this release is the measured library" is slightly off.
  - The measured wheel header declares `NVJPEG_OUTPUT_NV12` (`nvjpeg.h:144`) and `NVJPEG_OUTPUT_YUY2` (`nvjpeg.h:146`) (raw `step3/GF03/work/lic/nvjpeg.h`; not in the repo excerpt).
  - Fix: "the feature was added in nvJPEG 12.9; the measured 12.4.0.76 (12.9.1) header declares `NVJPEG_OUTPUT_YUY2` (code, nvjpeg.h:146)". Add those lines to `nvjpeg_h_12.4.0.76_lines.txt` if the repo citation must be self-contained.
- **W3 (3.4 Ada/Blackwell JPEG cell). "No fixed-function JPEG encoder on GeForce" is labelled source, but it goes beyond the source.**
  - R06/R09 say nvJPEG hardware JPEG encode is available on Jetson Thor (SM 10.1). They are silent on GeForce silicon.
  - 2.12 already states it correctly: "inferred: on GeForce, nvJPEG encode is the CUDA backend".
  - Fix: "nvJPEG documents hardware JPEG encode only for Jetson Thor SM 10.1 (source, GF03 R06, R09); on GeForce nvJPEG encode is the CUDA backend (inferred)".
- **W4 (2.12 KB bullet; 3.4 Intel Arc VP9 cell). The KB contradicts itself on Arc B VP9.**
  - Its "Encode - supported codecs" row lists "AVC (H.264) HEVC (H.265) VP9 AV1" for Arc B-Series.
  - Its "Encode - supported formats" VP9 row says "Not Supported" for Arc B (`GF07_sources/08_*.md`).
  - The draft cites only "Not Supported", and also says the KB lists "H.264/HEVC/AV1 encode" for Arc A, Series 1 and Arc B, leaving VP9 out of that list.
  - GF07 itself missed the conflict.
  - Fix: "KB 000098345 is inconsistent for Arc B VP9: codecs row lists VP9, formats row says 'Not Supported'" (vendor vs vendor, NOT VERIFIED).
- **W5 (3.4 VP9 cell, LNL). A second Windows Intel source points the other way.**
  - The cell cites the LNL datasheet (AVC, HEVC, AV1 only).
  - The KB "Core Ultra Series 2 with Intel Arc GPU" column lists VP9 encode. GF07 §101-102 records this conflict and says Series 2 does not map to LNL alone.
  - Fix: add "KB Series 2 column lists VP9; which Series 2 parts it covers is not stated (GF07)".
- **W6 (3.4 Intel Arc JPEG cell).** "Arc A yes (oneVPL doc, OS-agnostic)" sits under "Windows:". GF07 labels it "source (OS-agnostic); Windows inferred", and the Windows KB is silent on JPEG.
  - Fix: move Arc A out of the "Windows:" list, or append "Windows inferred".
- **W7 (6.2 SLA §2.11 bullet). Two caveats from GF03 are missing.**
  - (a) GF03 found nvImageCodec's licence inconsistent across NVIDIA channels. The wheel and docs give the SLA; PyPI and GitHub v0.10.0 give Apache-2.0. Which governs is NOT VERIFIED (GF03 §3.1).
  - (b) The 2.6 decode timings used nvImageCodec 0.9.0.20, whose licence GF03 did not inspect (GF03 §7). So "bears on … (2.6-2.8, 3.2)" over-reaches for 2.6.
  - Fix: add "(the SLA is the wheel's licence file; PyPI/GitHub say Apache-2.0, which governs NOT VERIFIED; 0.9.0.20 used in 2.6 not inspected)".

## 5. Not checked

- The GF07 claims carried over unchanged from earlier revisions (media-driver rows).
- The rest of the draft outside the step 3 fold (verified earlier in `VERIFY_provenance.md`, `VERIFY_method.md`).
- GF03 R06's "(Blackwell)" vs R09's "SM 10.1": consistent, not cross-checked against a Thor spec sheet.
