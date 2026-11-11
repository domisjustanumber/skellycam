# write_throughput: step 3 verification (GF01, GF02), 2026-11-10

Adversarial check of the new or changed claims only, covering provenance and method. Read-only: I read the cited files, JSON fields and code lines. No timed measurement and no new tests.

Paths: `GAP` = `research/skellycam_recording/recording_upgrade/results/crash_resilience/gapfill`, `RES` = `.../results/write_throughput`.

## Confirmed

| Draft claim | Evidence checked |
|---|---|
| Impl. 8: 1 s fragments lost 33, 62 without fp; 46, 5 with fp | `RES/functional/functional_results_av19.0.2.md:45` (`fmp4_1s` [33, 62]); `..._gapfill.md:26` (`fmp4_1s_flush` [46, 5]) |
| Impl. 8: conflicts with JP §4 item 2 | `RU/results/jpeg_passthrough/FINDINGS.md:531` still says "leading container candidate is fMP4 ... 1 s fragments" |
| Impl. 4 lead + GF01 pointer | `GAP/GF01_container_decision_table.md` §3 holds the same proposed text; the table has fMP4 1 s rows (R4a/R4b) and a PTS policy item (§2.3) |
| GF01 change 3, no numeric changes | GF01 §4 quotes for WT:480/484/496 match the draft's unchanged values |
| GF02 writer env | `GF02_container_matrix.json` `env_writer`: pyav 19.0.2, ffmpeg 9.0.2, libavformat 63.1.102 |
| Clean close 8/8 byte-exact, ffprobe only real packets | 8 `mkv_fp_empty` rows: `pyav_all_exact` true, `ffprobe_packets` = n, `ffprobe_zero_size_listed` 0 |
| EBML n size-0 SimpleBlocks, n+1 Clusters | e.g. c930e 891: clusters 892, simpleblocks 1782, size0 891; all 8 rows follow the same pattern |
| Last-frame seek returns no packet, 8/8 | `pyav_seek_exact` 10, `pyav_seek_miss` = [{k: n-1}] with no `got_pts`, 8/8 |
| +6.0 B/frame | 49,360,153 − 49,354,793 = 5,360 B / 891 = 6.02 (computed) |
| 12 empty-packet kills lost 0; 6 `os._exit`, 6 TerminateProcess | `partB[]` `lost_vs_sidecar` 0 ×12; methods exit/term alternate, 3+3 per PTS mode |
| Killed empty-packet file: PyAV seek 1 frame late 12/12; plain MKV exact 12/12 | `killed_pyav_seek` `got_pts` = next frame's pts (e.g. 4976 → 5008) in 12/12; `mkv_fp` target = got 12/12 |
| MKV + fp 1 lost 12/12; fMP4 `frag_keyframe` + fp 1 lost 12/12 | `lost_vs_sidecar` = 1 in all 24; WT `fmp4_frame` uses the same `frag_keyframe+empty_moov+default_base_moof` (`SCR/wt_common.py:262`) |
| fMP4 1 s + fp lost 1-30 (real 14-29, index 1-30) | real 20, 14, 24, 22, 29, 26; index 20, 17, 30, 1, 11, 10 |
| No torn tail in 48 kills | `killed_pyav.first_non_exact` null ×48 |
| Index PTS: 4 clean files byte-exact, 6 kills 0 lost | `partA` index empty rows exact; `partB` index empty rows 0 |
| `recover()` byte-exact 12/12 | `recover.matched_prefix` = `recovered_pyav.exact_prefix` = acked, 12/12 empty-packet kills |
| Code `gf02_common.py:124-129`, `:46-48`; `recwriter.py:252-269` | Lines match: empty packet with `time_base` 1/1e6, pts = frame time µs + 1; in-process `rw.CONTAINERS` registration; `recover()` skips `p.size == 0` and remuxes with the container's options |
| Inferred: the empty packet lands in the frame's own 1 ms tick | code: `self.tb` is read after `start_encoding()` (`gf02_common.py:84-85`), so for MKV it is 1/1000. The empty pts is therefore an exact ms value + 1 µs and always rounds to the same tick. This holds for both PTS modes |
| Real-PTS recovered MKV 125/2, 0/0; cv2 about 2.1x | `GF02_recovered_rates.txt`: 12/12 real MKV recovered files 125/2,0/0. `recovered_cv2.frame_count_prop` / packets = 2.07-2.08 (12/12). Index: 1.00 (12/12) |
| No timing claims from concurrent runs | None of the GF02 numbers is a duration or rate (GF02 report header) |

## Refuted

- **Section 6, empty-packet NOT VERIFIED list: "kills at 60 fps ... (GF02's 12 kills were at 30 fps ...)".**
  - code: the WT verifier's 3 empty-packet kills were 60 fps paced (`C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/write_throughput/verify_emptypkt_av19.py:9`, `:112` `fps=60, pace=True`).
  - So 60 fps kills were tested (3, all 0 lost). What is missing is more than 3 kills at 60 fps, and any kill that cuts a write in progress.
  - measured: none of the 15 kills cut a packet. The 3 verifier kills had units = acked (`verify_method_emptypkt_av19.0.2.json`), and GF02 found no torn tail.

## Weak

- **Impl. 4: "three of the four adoption checks", counting the EBML scan as the "non-FFmpeg parser check".**
  - The scan is the study's own structural counter. It shows the size-0 blocks exist, which is the risk. It does not show that any non-FFmpeg demuxer tolerates them.
  - The WT verifier had already run the same scan (2.3).
  - Fix: say two of four (clean close, more kills) are done. The parser check is partial: structure confirmed by the in-house scanner, and no third-party parser was run.
- **Impl. 4 and 2.3: "on an unfinalized file a PyAV pts seek lands 1 frame late (12/12)".**
  - Each killed file had one seek target, k = exact//2 (code `gf02_partB_kills.py:103`). That makes it 12/12 files with one target each, not all targets.
  - Fix: add "(one target per file, k = exact//2)".
- **Impl. 8 citation.** The 33 and 62 values come from `functional_results_av19.0.2.md:45`, but the item cites only `..._gapfill.md:26`, which holds 46 and 5. Fix: cite both lines (section 9 already does).
- **Impl. 4: "15/15 with WT's 3".**
  - This pools 3 kills of a WT verifier writer at 60 fps (frames 332-367) with 12 kills of a recwriter-derived writer at 30 fps (frames 50-700).
  - The section 9 scope note covers this, but the bullet itself does not.
  - Fix: write "15/15 (3 at 60 fps WT, 12 at 30 fps GF02)".

## Verdict

GF01 and GF02 are folded in accurately. Every number, file and code line checked matches. One refutation needs a fix: section 6 wrongly lists 60 fps kills as untested. Four claims are weak and need rewording: the parser check is overstated, the seek defect needs its scope, implication 8 needs a second citation, and implication 4 pools the kill counts without saying so.
