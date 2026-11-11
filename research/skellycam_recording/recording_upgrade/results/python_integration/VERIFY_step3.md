# python_integration: step 3 verification (provenance + method)

2026-11-10. Scope: only the claims added or changed by GF01, GF02 and GF05 in the new FINDINGS draft. No tests run, no timing. All checks are reads of result files, scripts and FINDINGS lines.

Paths: `RU/` = `research/skellycam_recording/recording_upgrade/`; `GF02/` = `RU/results/crash_resilience/gapfill/`.

## Verdict

No refuted claims. Every new number matches the files. Six weak points (citation range, scope, one inference), none of which changes a conclusion.

## Checked and confirmed

| Draft claim | Evidence read | Result |
|---|---|---|
| F3 / §4.2: index PTS give exact cv2 count, 11/11 POS_FRAMES seeks and FreeMoCap ok in 18/18 files (4 containers × 4 inputs + 2 long) | `GF02/GF02_container_matrix.json` `partA[]` (36 rows): `cv2_frame_count`, `cv2_seek_exact_input`, `freemocap_ok` | confirmed, 18/18 |
| F3: real-PTS MKV counts 888 for 891 / 831 / 874 and 53,820 for 54,000 | same, both MKV variants | confirmed |
| F3: real-PTS MKV seeks 2, 2, 1 / 11 and 1/11 on the long file | same | confirmed |
| F3: real-PTS fMP4 (both fragment modes) count exact, seeks 9 / 1 / 8 of 11 | same | confirmed |
| F3: c922 real PTS exact (count, 11/11, FreeMoCap ok) in every container | same, 4 rows | confirmed |
| F3: seeks checked by identity vs cv2 decode of the corpus; FreeMoCap ok = count + 4 reads | `GF02/GF02_container_matrix.md` Method; `gf02_cv2_reader.py:1-5` | confirmed |
| §3 index-PTS row text | matches GF02 proposed text and `partA[]` | confirmed |
| §3 hard-kill FRAME_COUNT: fMP4 = complete frames 24/24; MKV −2.767e17 24/24 | `partB[].killed_cv2.frame_count_prop` vs `killed_pyav.exact_prefix` (48 rows) | confirmed |
| §4.3: fMP4 1 s + fp lost real 20, 14, 24, 22, 29, 26; index 20, 17, 30, 1, 11, 10 | `partB[].lost_vs_sidecar` | confirmed |
| §4.3: range 1-30 (correction of GF02's "14–30") | index kill at 451 lost 1; GF02 md table "1 / 14 / 30" | correction is right; GF02's "14–30" text is wrong |
| §4.3: MKV + fp and fMP4 per-frame + fp lost 1 every kill; MKV + fp + empty lost 0 | `partB[].lost_vs_sidecar` | confirmed, 6/6 each per PTS mode |
| §4.3 inferred: index-PTS 1 s loss = frames since last 1 s boundary | ((k−1) mod 30)+1 for k = 50/137/300/451/611/700 gives 20/17/30/1/11/10 | arithmetic matches; label inferred is right |
| §4.3: no torn tail in 48 kills | `partB[].killed_pyav.first_non_exact` null ×48 | confirmed |
| F6: recovered real-PTS MKV `r_frame_rate` 125/2, `avg_frame_rate` 0/0 | `GF02/GF02_recovered_rates.txt` (12 files) | confirmed |
| F6: cv2 fps 62.5, count ≈2.1×, e.g. 102 for 49, 1451 for 699, 12/12 | `partB[].recovered_cv2` (mkv_fp real k50 → 102, k700 → 1451; ratio 2.08) | confirmed |
| F6: index MKV + all fMP4 recover with correct count, 36/36 | `recovered_cv2.frame_count_prop` = `recovered_pyav.packets` | confirmed |
| F6 code: `add_stream_from_template(s_in)` at `recwriter.py:259` | `scripts/python_integration/recwriter.py:259` | confirmed |
| F6 code: earlier PI kills used `perf_counter_ns` (`test_crash.py:44-50`, reused by `pyav19_recheck.py:35`) | `test_crash.py:44-50`; `pyav19_recheck.py:35,152-155` | confirmed |
| Evidence: GF02Writer = recwriter copy + `add_mux_stream`, `flush_packets=1`, optional empty packet; `recover()` unchanged | `gf02_common.py:1-13,40-46` | confirmed (citation range slightly off, W1) |
| Evidence: readers OpenCV 4.12 + FreeMoCap `VideoHelper`, read-only skellycam venv | `gf02_cv2_reader.py:1-2`; matrix md | confirmed |
| §4.2: JP's MKV-count reason measured with real VFR PTS | `RU/results/jpeg_passthrough/FINDINGS.md:568` | confirmed |
| §4.3: HANDOFF.md:173 names fMP4 1/1e6 leading; GF01 §2.2, §4 list the disagreement | `RU/HANDOFF.md:173`; GF01 headings at lines 95, 151 | confirmed |
| §4.3 cross-topic: write_throughput 33/62 (no fp), 46/5 (fp), 720p60, 2 kills | `RU/results/write_throughput/FINDINGS.md:88-96` | confirmed |
| Line fixes: CR `:421` (262144 B, 4–5 frames), `:423` (open fragment), `:439` (`flush_packets=1`) | `RU/results/crash_resilience/FINDINGS.md` | confirmed |
| GF05: `R/BENCH.md` §2 now has 20,021 bare + 11 UserWarning lines | `R/BENCH.md:41` (§2 heading), `:46` | confirmed |
| No timing claims from concurrent runs | GF02 records no durations (matrix md, first line) | confirmed |

## Weak points

- **W1.** `gf02_common.py:1-11,41-44` stops before the 1 s fragment entry (`:45`) and the in-process `rw.CONTAINERS` registration (`:46-48`) that backs "recover() unchanged". Fix: cite `gf02_common.py:1-13,40-48`.
- **W2.** F6 "(the killed source has 30/1, 30/1)" is stated for both real-PTS MKV variants, but `GF02_recovered_rates.txt` lists killed-file rates only for the 6 `mkv_fp_real` files. Fix: "the 6 killed MKV + fp real files have 30/1, 30/1".
- **W3.** F6 says "byte-exact (`recover` matched prefix = byte-exact frames on disk in 48/48)". That column checks the matched prefix against the killed file, not the recovered file. The recovered file check is `recovered_pyav.exact_prefix == packets == matched_prefix`, also 48/48 (`gf02_report.py:103-104`). Fix: cite that check.
- **W4.** §4.2 "Real PTS break seeks with drops even in fMP4" understates: real-PTS fMP4 also missed on c930e full with no drops (9/11, rate drift). Fix: "with drops or rate drift (c930e full 9/11, gap60 1/11, drop50 8/11)".
- **W5.** F3 "closes the seek-accuracy gap ... for these inputs": the files came from GF02Writer (`add_mux_stream`, `flush_packets=1`), not recwriter. Fix: "for these inputs and the GF02 writer".
- **W6.** F6 inference (NOT VERIFIED): the same `add_stream_from_template` remux gave 30/1 for index-PTS MKV and a correct 297.0 for the perf_counter real-PTS MKV kill. So "the template does not carry the rate" alone does not explain 125/2; the trigger is the timestamp pattern. Fix: "inferred, NOT VERIFIED: with no rate in the template, FFmpeg guesses from the timestamps; real c930e intervals at 1 ms give 62.5, evenly spaced ones give 30".
