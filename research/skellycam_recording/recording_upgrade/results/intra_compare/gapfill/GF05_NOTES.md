# GF05 notes: intra_compare (2026-11-10)

Main record: `results/chromium_codecs/gapfill/GF05_g8_g9_doc_fixes.md` (proposed FINDINGS text per topic and the list of direct edits). No test or timing was run.

- Direct edits: `BENCH.md` line 606 (caveat 3: nvJPEG QC from NV12/YUY2 hits A; values from `bench/matched_stream_A_{1080p,720p}_*.json` `summary[*].quality_check`); `NOTES.md` lines 54, 179, 181, 185, 186, 208 (stale sizes -> `matched_summary.md`).
- Full compare of NOTES §6 target A and B tables against `matched_summary.md` (before editing), stale cells found:

| NOTES line | path | class | NOTES | matched_summary.md |
|---|---|---|---|---|
| 179 | h264_nvenc_420 | yuy2_720p | 83,921 (0.51) | 83,913 (0.51) |
| 181 | hevc_nvenc_420 | mjpeg_720p | 55,112 (0.91; 0.83) | 53,975 (0.89; 0.81) |
| 181 | hevc_nvenc_420 | mjpeg_1080p | 144,376 (0.99; 0.88) | 141,655 (0.97; 0.87) |
| 185 | libx264_ultrafast_420 | mjpeg_720p | 93,764 (1.55; 1.41) | 94,459 (1.57; 1.42) |
| 185 | libx264_ultrafast_420 | mjpeg_1080p | 248,857 (1.71; 1.52) | 249,785 (1.71; 1.53) |
| 186 | libx265_ultrafast_420 | mjpeg_720p | 67,557 (1.12; 1.01) | 67,662 (1.12; 1.02) |
| 186 | libx265_ultrafast_420 | mjpeg_1080p | 160,931 (1.10; 0.98) | 161,155 (1.11; 0.99) |

- The target B table matched in every cell. Lines 185 and 186 were not in the FINDINGS stale list (FINDINGS lines 40-43).
- Proposed FINDINGS: line 525 and 476 and 620 (libx265 Electron playback -> intra_playback F16); lines 40-43 stale list.
