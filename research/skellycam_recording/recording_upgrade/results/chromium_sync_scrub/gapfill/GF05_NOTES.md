# GF05 notes: chromium_sync_scrub (2026-11-10)

Main record: `results/chromium_codecs/gapfill/GF05_g8_g9_doc_fixes.md` (proposed FINDINGS text per topic and the list of direct edits). No test or timing was run.

- measured: `bench/` holds only `bench_{seek,step,sync,scrub}_smoke/` for e35 and e45 (6 / 4 / 10 / 10 runs, `smoke: true`, 0 errors). This topic's own bench suites never ran timed.
- measured: `results/bench_queue_2300.json` has no chromium_sync_scrub item; the timed G9 items are intra_playback's IP-* (all ok).
- measured: no `functional/e*/exhaustive/` exists; the exhaustive sweep was not run (stays NOT VERIFIED).
- Proposed: header line 6, requirement numbers (10 -> 8), §3.3 label, I3 (master clock + canvas for N >= 8), I8, §5, F25, §6 lines 265/273/284, §7 '# tonight', §8 lines 360/362.
