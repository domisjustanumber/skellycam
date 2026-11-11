# GF05 notes: intra_playback (2026-11-10)

Main record: `results/chromium_codecs/gapfill/GF05_g8_g9_doc_fixes.md` (proposed FINDINGS text per topic and the list of direct edits). No test or timing was run.

- Direct edits to `BENCH.md`: line 355 (60 Hz remark, aligned with F18); lines 40, 233, 262, 293, 295, 334 and 48 table cells (GPU memory now raw `private_kb`, unit NOT VERIFIED per F22). Cell-by-cell record: `GF05_private_kb_cells.json` (from `scripts/intra_playback/gf05_bench_private_kb_edit.py`, which asserts every old cell = round(private_kb / 2^20, 1)).
- Proposed FINDINGS: §6 lines 258-260 (HEVC 4:2:2 now measured, chromium_codecs C17/C17a); line 85 pointer -> uncompressed_intra `VERIFY_method.prev.md:28`; lines 12, 124, 320, 339 wording.
