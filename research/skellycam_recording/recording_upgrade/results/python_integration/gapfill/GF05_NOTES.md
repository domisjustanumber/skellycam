# GF05 notes: python_integration (2026-11-10)

Main record: `results/chromium_codecs/gapfill/GF05_g8_g9_doc_fixes.md` (proposed FINDINGS text per topic and the list of direct edits). No test or timing was run.

- measured (`results/bench_runner/logs/20261109T230007/39_PI-JPEG-DECODE-PYAV19.err.txt`): 20,043 lines; `grep -c "^Corrupt JPEG data"` = 20,021; `grep -c UserWarning` = 11 (each followed by a `warnings.warn(error_message)` line). Matches FINDINGS F14.
- Direct edit: `BENCH.md` line 46 now gives these counts (was "about 18,000 ... UserWarning ... PyTurboJPEG").
- Proposed FINDINGS: lines 328 and 614 (BENCH.md is now corrected).
