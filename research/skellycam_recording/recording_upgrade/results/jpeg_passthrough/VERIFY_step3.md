# jpeg_passthrough: Step 3 verification (provenance + method)

2026-11-10. Scope: only the claims the Step 3 gap-fill (GF01, GF02) adds or changes in the jpeg_passthrough FINDINGS draft. No tests and no timing were run. Every check below is a read of result files, scripts or sidecars (read-only).

Paths are relative to `research/skellycam_recording/recording_upgrade/` unless absolute. GF02 = `results/crash_resilience/gapfill/GF02_container_matrix.json`.

## Verdict

**PASS with minor fixes.** None of the new claims is refuted. Every new number matches its result file. 7 claims are weak (scope, labels or citations); the fixes are listed in §3.

## 1. Checked and confirmed

| Draft claim (section) | Check | Result |
|---|---|---|
| Part A: 36 files byte-exact through PyAV; `grab()` = written in all (§2.4) | GF02 `partA[].pyav_all_exact`, `cv2_grab` vs `n_written` | 36/36 True; grab = written in 36/36 |
| Index PTS, 4 containers × 4 inputs: count exact, 11/11 cv2 seeks, FreeMoCap ok, 16/16 (§2.4, §4.8) | `partA[]` `cv2_frame_count`, `cv2_seek_exact_input`, `cv2_seek_total` (=11 in all), `freemocap` reads | confirmed: 891/831/874/893, 11/11, 4/4 reads `match_cv2_sequential` |
| Index long 54,000: MKV + fp and fMP4 1 s + fp exact, 11/11, ok (§2.4) | `partA[]` long rows; `GF02_partA_long_read.json` `results[].seek` | confirmed |
| Real-PTS fMP4 (per-frame and 1 s): 9/11, 1/11, 8/11, 11/11; FreeMoCap ok 8/8 (§2.4, §4.2) | `partA[]` | confirmed |
| Real-PTS fMP4 c930e full misses k 178 → 179, 267 → 268 (§2.4) | `partA[].cv2_seek[].got_seq_index` | confirmed |
| Real-PTS long MKV: 53,820; 1/11; 5400 → 5418, 10800 → 10836, 16200 → 16254; later targets outside ±70; last read fails; FreeMoCap FAIL (count) (§2.4) | `GF02_partA_long_read.json` `results[0].seek`; `partA[].freemocap` | confirmed (`got_input_index_near` [] for 21600-48600; k 53999 `read_ok` false; FreeMoCap count 53,820, all 4 reads match) |
| Time bases after header: MKV 1/1000; fMP4 1/1e6 real, 1/15360 index (§2.4) | `partA[].time_base` | confirmed |
| 53,820 vs OPEN 53,819; writer rounding differs (§2.4) | `partA[]`; code `recwriter.py:111-115` (half up) vs `jp_common.py:59-69` (floor) | number confirmed; the rounding cause is correctly labelled inferred |
| GF02 writer = RecordingWriter copy + `add_mux_stream` + `flush_packets=1`, half-up rounding (§2.4) | `gf02_common.py:7-8,41-44,57-58,82,94` | confirmed (it also has an optional empty packet) |
| Part B lost per kill: MKV 1 ×12; MKV + empty 0 ×12; fMP4 per-frame 1 ×12; fMP4 1 s real 20,14,24,22,29,26, index 20,17,30,1,11,10 (§2.5) | `partB[].lost_vs_sidecar`, `kill_at` order | confirmed; medians 23 and 14 recomputed |
| Range 1-30 (not 14-30) for fMP4 1 s + fp (§4.2, Step 3 note) | as above | confirmed: index k=451 lost 1. GF02's own "What this changes" text (14–30) is wrong; its Part B table (1 / 14 / 30) is right |
| Index-PTS loss = ((k − 1) mod 30) + 1, 6/6 (§2.5) | arithmetic on kill points 50, 137, 300, 451, 611, 700 | 20, 17, 30, 1, 11, 10: confirmed |
| No torn tail in 48/48; no PyAV demux error 48/48; `recover()` matched prefix = on-disk exact 48/48 (§2.5) | `partB[].killed_pyav.first_non_exact`, `.demux_error`, `recover.matched_prefix` vs `killed_pyav.exact_prefix` | confirmed |
| Killed fMP4: cv2 count = frames on disk 24/24; killed MKV: −2.767e17 and wrong POS_FRAMES seek 24/24 (§2.5) | `partB[].killed_cv2.frame_count_prop`, `.seek[0].match_input` | confirmed |
| Recovered: index MKV count and seek right 12/12; real MKV `r_frame_rate` 125/2, fps 62.5, ~2.1× count 12/12 (§4.8) | `partB[].recovered_cv2`; `GF02_recovered_rates.txt` | confirmed; ratio 2.07-2.08 |
| 48 kills alternate `os._exit(1)` / TerminateProcess (§2.5) | `partB_kill_points`; `partB[].method` | confirmed |
| 600-frame JP kill had no `flush_packets` (§2.5) | `scripts/jpeg_passthrough/pyav19_recheck.py` (no `flush_packets` anywhere) | confirmed |
| 33,030,144 = 1008 × 32,768 = 126 × 262,144 (§2.5) | arithmetic; `pyav19_recheck.json` `C_killed.{mkv,avi_tb_rate,nut,mjpeg_raw_mux}.bytes` | confirmed |
| FFmpeg `file.c:324-332` sets `max_packet_size = 262144`, cited at CR:85, CR §2.1 (§2.5) | `results/crash_resilience/FINDINGS.md:85` (under "### 2.1 Hard kill", line 46) | confirmed; the buffer cause stays inferred, correctly labelled |
| WT 1 s fragments lost 33, 62 (no fp) and 46, 5 (fp) (§4.2) | `results/write_throughput/FINDINGS.md:96`; `functional_results_av19.0.2_gapfill.md:26`; `functional_results_av19.0.2.md:45` | confirmed |
| 22 lost at JP's kill = 600 − 578 (§4.2) | `pyav19_recheck.json` `C_killed` | confirmed (computed) |
| PI: index MKV 7/7; 18,000/18,000 on an ideal-PTS file (§4.8) | PI:110 "MKV index (CFR) \| 7 of 7"; PI:283; `recwriter_quiet1_pyav19.json` `c_open_cost.mkv.cv2_frame_count_prop` 18000.0 | confirmed. PI:274 says the 18,000 file was written in real-PTS mode with ideal timestamps; the draft says "ideal-PTS file", which is accurate |
| recwriter bumps a colliding pts by 1 tick and flags it (§4.8) | `scripts/python_integration/recwriter.py:46` (`FLAG_PTS_ADJUSTED`), `:135-136` | confirmed |
| 1 bump in c930e real MKV; the bumped frame is not a PyAV seek target (§4.8) | `GF02_partA_write.json` `files.A_c930e_full_mkv_fp_real.mkv.pts_adjusted` 1; sidecar read (below) | confirmed. Sidecar `A_c930e_full_mkv_fp_real.frames.bin` flags record 82 (pts 2705); targets are 0, 89, …, 890 |
| `recover()` remux uses `add_stream_from_template` (`recwriter.py:259`) (Step 3 note) | code | confirmed |
| No timing claims from concurrent runs | all new text | none: GF02 recorded no durations, and the draft adds none |

Sidecar check (read-only, media folder `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/crash_resilience/gapfill/GF02/partA/`, 48-byte records after the 64-byte header, `flags & 1`): each of the 6 real-PTS MKV files on c930e-derived inputs (c930e full, gap60, drop50; MKV + fp and MKV + fp + empty) has exactly 1 flagged record: frame_number 82, pts 2705 (record index 81 in drop50). The c922 files, the fMP4 files and the index files have 0.

## 2. Refuted

None.

## 3. Weak (fix before final)

1. **§4.2 "lose everything since the last 1 s boundary" is stated for both PTS modes.** The formula is computed on index PTS only; for real PTS the boundary is in time, and the draft's own Step 3 note says so. Fix: "index PTS: everything since the last 1 s boundary (computed, 6/6); real PTS: 14-29 frames, consistent with it (inferred)".
2. **§4.2 "per-frame fragments lose 1 frame per kill" has no `flush_packets` scope in that clause.** Without fp, JP lost 4 (596/600) and WT lost 5, 5 (WT:96). Fix: "with `flush_packets=1`, per-frame fragments lost 1 frame per paced kill (12/12)".
3. **§4.2 mixes time bases and PTS modes under the 1/1e6 heading.** The bullet "exact OpenCV frame count … re-measured … in both PTS modes" sits under "fMP4 with `st.time_base = 1/1e6`", but GF02's index-PTS fMP4 files have time base 1/15360, and index PTS do not "keep VFR timestamps exact at 1 µs". Fix: "(re-measured with `flush_packets=1`: real PTS at 1/1e6 and index PTS at 1/15360; GF02)".
4. **§4.2 lead: the WT vs JP loss comparison has no conditions attached.** WT is 720p60 paced with TerminateProcess; JP is one unpaced `os._exit` after 600 frames at 30 fps (GF01 §0 says they are not comparable). Also, the 33/62 figures cite a FINDINGS line, not the result file. Fix: add "(WT: 720p60 paced, TerminateProcess; not directly comparable)" and cite `results/write_throughput/functional/functional_results_av19.0.2.md:45` for 33, 62.
5. **§4.8 bump citation and count.** `GF02_partA_write.json` `pyav_seek` does not record which frame was bumped. The evidence is the sidecar flag (record 82). Also, 1 bump occurred in each of 6 real-PTS MKV files on c930e-derived inputs, not only the c930e one. Fix: "measured: 1 bump per real-PTS MKV on c930e-derived inputs (6 files; sidecar `FLAG_PTS_ADJUSTED` on frame 82); no PyAV or cv2 seek target hit frame 82".
6. **§4.8 "Index PTS with dropped frames is therefore tested, and exact."** "Exact" here means count = frames written and seek by index. By construction the container timeline no longer shows the gap, so any reader that takes time from the container is wrong across a drop. Fix: append "(the container timeline hides the drop; capture times come only from the sidecar, inferred)".
7. **Unchanged text now contradicts the new evidence, and the "Left unchanged" note misstates the conflict.** §4 item 5 ("POS_FRAMES seeks are exact only when the capture has no gaps") and the §3.1 MKV count/FreeMoCap cells hold for real PTS only: GF02 index-PTS gap60/drop50 gave 11/11 seeks and exact counts. The note frames the conflict only as real-PTS 9/11 on a gap-free file. Fix: scope §4 item 5 and the §3.1 gap rows to "real VFR PTS", and add the index-PTS result. Minor: in §2.5, "i.e. every frame since the last 1 s fragment boundary" is interpretation (inferred), not computed.

## 4. Files read

- `results/crash_resilience/gapfill/GF01_container_decision_table.md`, `GF01_NOTES.md`
- `results/crash_resilience/gapfill/GF02_container_matrix.md`, `.json`, `GF02_NOTES.md`, `GF02_partA_write.json`, `GF02_partA_long_read.json`, `GF02_recovered_rates.txt`
- `scripts/crash_resilience/gapfill/GF02/gf02_common.py`; `scripts/python_integration/recwriter.py:33-50,105-140,255-262`; `scripts/jpeg_passthrough/pyav19_recheck.py` (grep)
- `results/jpeg_passthrough/pyav19_recheck.json` `C_killed`
- `results/write_throughput/FINDINGS.md:86-97`; `functional/functional_results_av19.0.2.md:45`; `functional/functional_results_av19.0.2_gapfill.md:18-27`
- `results/python_integration/FINDINGS.md:110,274,283,405`; `bench/recwriter_quiet1_pyav19.json` `c_open_cost`
- `results/crash_resilience/FINDINGS.md:46,85`
- GF02 partA sidecars (`*.frames.bin`) in the media folder, read-only
