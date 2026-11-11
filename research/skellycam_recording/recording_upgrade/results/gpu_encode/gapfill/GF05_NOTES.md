# GF05 notes: gpu_encode (2026-11-10)

Main record: `results/chromium_codecs/gapfill/GF05_g8_g9_doc_fixes.md` (proposed FINDINGS text per topic and the list of direct edits). No test or timing was run.

- Proposed FINDINGS: §6.2 line 481 (hevc_qsv 4:2:2 in Chromium) -> measured fail per chromium_codecs C17 (E35 no open, E45 PIPELINE_ERROR_DECODE; C156 NOT VERIFIED); the old pointer "intra_playback FINDINGS line 64" is stale.
