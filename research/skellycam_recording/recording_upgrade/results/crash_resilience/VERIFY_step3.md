# crash_resilience: step 3 verification (provenance + method)

Date: 2026-11-10. Scope: only the claims that are new or changed in the step 3 draft (GF01, GF02). Read-only checks; no tests, no timing.

## What was checked

| source | how |
|---|---|
| `gapfill/GF02_container_matrix.json` → `partB[]` (48 rows) | every row dumped: `lost_vs_sidecar`, `last_M_line`, `sidecar_records`, `sidecar_torn_tail_bytes`, `find_unfinished_lists_it`, `recover.matched_prefix`, `killed_pyav.{exact_prefix,first_non_exact}`, `killed_pyav_seek`, `killed_cv2`, `recovered_cv2`, `recovered_pyav` |
| `gapfill/GF02_container_matrix.json` → `partA[]` (36 rows) | `bytes`, `pyav_all_exact`, `ffprobe_packets`, `ffprobe_zero_size_listed`, `ebml`, `cv2_frame_count`, `cv2_seek_exact_input`, `freemocap_ok`, `pyav_seek_exact`, `pyav_seek_miss` |
| `gapfill/GF02_recovered_rates.txt` | all 48 recovered + 6 killed rate lines |
| `gapfill/GF02_container_matrix.md`, `GF02_NOTES.md`, `GF01_NOTES.md`, `GF01_container_decision_table.md` §1 | text and row names |
| code | `scripts/python_integration/recwriter.py:259`; `scripts/crash_resilience/gapfill/GF02/gf02_common.py:41-44`, `:125`, `:188`; `gf02_child.py:42-46`; `gf02_partB_kills.py:49-55`; `scripts/jpeg_passthrough/pyav19_recheck.py:39`, `:163-184` |
| cross-topic lines | `results/write_throughput/FINDINGS.md:86-101`; `results/write_throughput/functional/functional_results_av19.0.2_gapfill.md:26`, `:35-36`; `results/jpeg_passthrough/FINDINGS.md:283-303`, `:565-569`; `results/python_integration/FINDINGS.md:110`, `:405` |

## Confirmed (measured unless noted)

- Loss per kill, partB order 50/137/300/451/611/700: MKV+fp 1×12; MKV+fp+empty 0×12; fMP4 `frag_keyframe`+fp 1×12; fMP4 1 s+fp real 20, 14, 24, 22, 29, 26 and index 20, 17, 30, 1, 11, 10. Exact match.
- Real 14–29, median 23; index 1–30, median 14 (computed). The draft's correction of the proposed "14–30" to "1–30" is right (index kill 451 lost 1).
- Index formula ((k − 1) mod 30) + 1 reproduces all 6 index values (computed). Label inferred is fine.
- 3 `os._exit` + 3 TerminateProcess per combination (`method` field; `partB_kill_points`).
- 48/48: `last_M_line` = `sidecar_records` = kill point, torn bytes 0; `find_unfinished_lists_it` true; `matched_prefix` = `exact_prefix`; `first_non_exact` null.
- Unfinalized MKV+empty PyAV seek lands on frame k+1 in 12/12 (e.g. 4976 → 5008, real k300; index 833 → 867 = frame 26). Plain MKV+fp exact 12/12.
- Killed MKV (24): cv2 count −2.767e17 24/24; POS_FRAMES seek wrong 24/24; `got_input_index_near` [0] at kill points 50 and 137, [] otherwise.
- Killed fMP4 (24): cv2 count = packets 24/24; cv2 seek 23/24, miss = 1 s real k137, k 61 → 60; PyAV seek 24/24.
- Recovered: real-PTS MKV (both variants) `r_frame_rate` 125/2, `avg_frame_rate` 0/0 (12/12); cv2 fps 62.5; counts 102, 281, 620, 934, 1266, 1451 / 104 … 1453 (≈2.08×, "about 2.1×" fine). Index MKV and all fMP4 recovered counts right; recovered 1 s real cv2 seek 11/12. Recovered files byte-exact for all recovered packets (`exact_prefix` = `recovered_packets`; `all_exact` is false only because it compares with the acked list, code `gf02_common.py:188`).
- `recwriter.py:259` is `s_out = dst.add_stream_from_template(s_in)`.
- partA: 8 MKV+empty files byte-exact; `ffprobe_zero_size_listed` 0 and `ffprobe_packets` = n; EBML c930e 892 clusters, 1782 SimpleBlocks, 891 size-0 (n+1 / 2n / n on all 4 inputs); last-frame `pyav_seek_miss` 8/8 with 10/11 exact.
- +6.0 B/frame: 49,360,153 − 49,354,793 = 5,360 B / 891 = 6.02 (computed); other inputs 6.02 too.
- Condition 1: index MKV+fp count exact, 11/11 seeks, FreeMoCap ok on c930e, gap60, drop50, c922 and 54,000. Real MKV 888 for 891/831/874 and 53,820 for 54,000.
- WT:96 (`fmp4_1s 33, 62; fmp4_1s_flush 46, 5`), gapfill.md:26 (`[46, 5]`, partial `[0, 0]`), WT:98-99 (empty packet 0, 0, 0; 0 partial units), WT:100-101 (1 cut packet per kill, 5 of 6 decoded silently), WT:88-89 (720p, 60 fps, steady-state kills): all as quoted.
- JP:292 (fMP4 1 s 1/1e6: 578 complete of 600) and JP:565-569 (MKV ruled out for FreeMoCap); PI:110 (MKV index 7 of 7) and PI:405 (write CFR index PTS) as quoted.
- GF01 table holds rows R1 MKV+fp, R2 MKV+fp+empty, R3 fMP4 per-frame, R4a/R4b fMP4 1 s, R5 append + CRC index, R6 plain MP4, matching the §4.11 pointer.
- No new timing claim. Write cost of the empty packet is stated as not measured.

## Weak (fix wording; numbers stand)

1. **JP 578/600 "without fp".** JP FINDINGS:292 does not say fp was off. Code does: `scripts/jpeg_passthrough/pyav19_recheck.py:39` (FRAG1S has no `flush_packets`). The kill was also drained (`os._exit` after 600 mux calls, `pyav19_recheck.py:163-184`), not live. Fix: add the code cite and "drained kill".
2. **§2.1 "inferred (GF02 notes): the kills landed between frames, while the child slept".** GF02 infers this only for the TerminateProcess kills. The `os._exit` kills are between frames by construction (code, `gf02_child.py:44-46`: exit right after "M k"). Fix: split into code (`os._exit`) and inferred (TerminateProcess, after a 0–33 ms delay, `gf02_partB_kills.py:49-55`).
3. **§6 "These remain PyAV 18 bg only: … `fmp4_1s` without fp".** The same draft (§3A) cites PyAV 19 no-fp 1 s kills from write_throughput (33, 62) and jpeg_passthrough (578/600). Fix: "not in this topic's own PyAV 19 matrix; cross-topic P19: WT and JP (§3A)".
4. **§4.1 lead "jpeg_passthrough rules MKV out for FreeMoCap under real VFR PTS".** JP:565-569 states no PTS qualifier. That the reasons apply to real PTS only comes from GF02 partA and PI:110. Fix: "JP rules MKV out (JP:565-569); its evidence used real VFR PTS, and GF02/PI show index PTS give exact counts".
5. **§6 "GF02's paced kills never interrupted a write".** Measured: no torn tail (`first_non_exact` null 48/48) and ack = sidecar 48/48. "Never interrupted a write" goes further. Fix: label it inferred.

## Refuted

None.

## Verdict

Pass with minor wording fixes. Every new GF01/GF02 number matches its result file, the labels are right apart from the five items above, and no timing is used.
