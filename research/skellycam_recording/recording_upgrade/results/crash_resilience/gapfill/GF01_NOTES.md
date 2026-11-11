# GF01 notes (doc fix: cross-topic container decision table)

2026-11-10. Output: `GF01_container_decision_table.md` (same folder).

## What was done

- Read HANDOFF.md §1, §1.1, §4, §5, §6, then the FINDINGS of jpeg_passthrough, crash_resilience, write_throughput, python_integration, licensing, intra_playback and chromium_codecs, plus `results/crash_resilience/summary.md` (PyAV 18 kill tables) and `results/write_throughput/functional/functional_results_av19.0.2_gapfill.md`.
- Checked three values against their result files (read only, no timing):
  - `results/python_integration/bench/recwriter_quiet1_pyav19.json` → `c_open_cost.{mkv,mp4f}.cv2_frame_count_prop` = 18000.0 for both;
  - `results/write_throughput/functional/verify_method_emptypkt_av19.0.2.json` → `C_kills_mkv_flush_emptypkt_ts`: acked 332 / 340 / 367, `acked_lost` 0 in each;
  - `scripts/intra_playback/gen_intra_clips.py:17`, `:74`: the intra fMP4 clips use `frag_keyframe+empty_moov+default_base_moof` with no `min_frag_duration`, i.e. one fragment per intra frame, 1/90000. So Chromium playback of 1 s-fragment fMP4 is untested.
- No tests, no timed measurements, no media written. No FINDINGS.md or HANDOFF.md edited.

## Caveats

- **GF02 scope.** GF01 did not see GF02's task text. At 09:49 GF02 had written `GF02_partA_write.json`. Its scripts (`scripts/crash_resilience/gapfill/GF02/`) show Part A covers clean-closed `mkv_fp`, `mkv_fp_empty`, `fmp4pf_fp` and `fmp4_1s_fp` with real and index PTS on c930e, c922, gap60 and drop50, read by cv2 4.12 and FreeMoCap. In the table those cells say `gap: GF02`. Kill, prefix-cut and Chromium cells say `gap: GF02?` (scope not confirmed).
- **Kill tests are not comparable across topics.** They differ in frame count, rate, kill timing and whether fp was set (table §0).
- **Line numbers** are as of 2026-11-10 about 10:00. They move when the FINDINGS are revised.
- **Stale line references found in python_integration FINDINGS** (reported in the structured output, not fixed):
  - PI:146 cites `crash_resilience/FINDINGS.md:310` for the 262144 B buffer loss; that text is now at CR:421.
  - PI:295 cites `:312` for the open-fragment loss; now CR:423.
  - PI:415 cites `:325` for the `flush_packets=1` recommendation; now CR:439.
- **jpeg_passthrough §2.5 buffer inference.** JP:300-301 infers a 32 KiB user-space buffer from killed files of 33,030,144 B = 1008 × 32,768. That size is also exactly 126 × 262,144 (computed). CR:85 cites FFmpeg `file.c:324-332` setting `max_packet_size = 262144`. So the 32 KiB inference is not supported over 256 KiB.
