# crash_resilience: provenance check of the 2026-11-10 draft FINDINGS

Verifier: adversarial provenance pass, 2026-11-10. No timed runs. The previous report (2026-11-09) is `VERIFY_provenance.prev.md`.

Paths are relative to `research/skellycam_recording/recording_upgrade/results/crash_resilience/` unless stated otherwise.

## What was checked

| area | how | result |
|---|---|---|
| §2.11 fsync table (9 policies x 6 columns) | recomputed median (min-max) from `bench/fsync_pyav19.json` → `results[].repeats[]` | every cell matches |
| §2.12 fragment tables (19 MJPEG + 16x2 intra variants) | recomputed wall µs/frame (`wall_s`x1e6/3000), bytes and overhead from both `bench/fragment_overhead_*_pyav19.json` | every cell matches; every row has 3 repeats and `error: null`; overhead constant across repeats |
| §2.12 derived numbers | fp deltas 4.9/2.7/3.0 and 3.1/1.8/1.2; 0.24 %/0.34 %/0.08 %; 4.9 and 14.2 MB/h; 8.3x; 38,239 and 44,953 B/frame; byte-identical mkv/mkv+fp/cl0 (166,161,060 / 114,854,087 / 134,997,090) | all match |
| §2.13 repair table | recomputed from `bench/repair_pyav19.json` (15 rows) | all match, incl. 3.9 % spread, +48 %, 1.10 GB/s, first-repeat-slowest pattern, `free_ram_mb_start` 49399, `writer_child_interpreter` = uv env |
| §2.1-2.3, 2.6 kill/seek/remux/pict_type | `pyav19_recheck.json`, `pyav19_recheck_repeat.json` (only `nvidia_smi_before` differs), `verify_method_pyav19_checks.json` | all table cells match; two side statements are wrong (R1, R2) |
| §2.2 OpenCV | `cv2_on_pyav19_files.json`, `cv2_seek_identity_pyav19_files.json`, `verify_method_cv2_on_pyav_remux.json` | match |
| §2.4 truncation | `truncation_pyav19.json` | match (AV1 "torn" cell is inferred, W5) |
| §2.5 encoder hold | `encoder_hold_check_pyav19.json`, `.log`, `encoder_hold_check.py:40` (gop 30) | numbers match; log line citation partly off (W4) |
| §2.7 Electron | `electron_pyav19_e35/e45.json`, `verify_method_electron_seek_identity_e35.json` | all match (9/16, 7/16 = 3 MKV + 4 fMP4, 16/16 at 250 ms, 8/8 AV1, expected−4) |
| §2.8 resumable | `resumable_demo_pyav19.json` → `verify` | match |
| §2.9 sidecar | `sidecar_durability.md` | match (6380 B = 72532−66152; 3456 B = 36000−32544; 23/24 and 6/24) |
| §2.10 sfn26 | `git show 765bf82d:` recorder.rs:40-45, :141-156, :266-275; dispatcher.rs:373; csv_writer.rs:72 (no `sync_all`/`sync_data`); `sfn26_pipe.md`, `sfn26_pipe_n150.md` | match |
| §5 run record | `BENCH_RUN_2300_LOG.jsonl` lines 19, 20, 29, 63: affinity `pcores`, status ok, load means 5.40/3.59/3.59/3.89 %, MsMpEng 1.05/5.38/10.25/1.36 CPU-s, no Defender scan events; `.err.txt` files all 0 B; no `affinity` field in any CR bench JSON | match (one inference W2) |
| §5 intra keyframes | ffprobe (inspect only) of `.../crash_resilience/bench_tmp/template_{h264nv,hevcnv}_intra.mkv` | **300/300 packets flagged K in both**, 1280x720, tb 1/1000. The all-intra claim can now be labelled measured. |
| §2.12 target A settings | `results/intra_compare/matched_settings.json` → `h264_nvenc_420/hevc_nvenc_420` → `mjpeg_720p`: qp 14 / 11, ssim_y 0.99611 / 0.99619, 46,317.1 / 55,247.4 B | match |
| §4.11 cross-topic | `results/jpeg_passthrough/bench/open_long.json` | 1107.28 / 42.57 / 0.19 ms medians and 53,819 match (W8) |
| Sources | re-fetched 2026-11-10: FFmpeg n9.0.2 raw files (version_major.h:32, version.h:34, file.c:324-332, mux.c:425-433, options_table.h:39/:56/:84, aviobuf.c:466-469, matroskaenc.c:3032-3048/3231-3236/2744-2748, movenc.c:7449-7455, segment.c:161-167 with no `flush_packets` anywhere in segment.c, nvenc_h264.c:100-101); Python 3.12 `os.fsync`; Microsoft `_commit` and `FlushFileBuffers` | every line number and quote matches; the `_commit` page does not mention FlushFileBuffers, as the draft says |
| code citations | bench_fsync.py, bench_fragment_overhead.py, bench_repair.py, writer_child.py:29-32/:184-187, common_cr.py:236-249/:280-290/:293-315/:301, resumable_recorder.py:10-23/:99-105/:198-232/:210/:215-218, recwriter.py:154-155 | match (one scope issue, W3) |

Fetched sources: `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step2/cr_prov_src/`.

## Refuted

| # | draft claim | evidence | correction |
|---|---|---|---|
| R1 | §2.1 "files written without fp are exact multiples of 262144 bytes" | `pyav19_recheck.json`: MJPEG `fmp4_every` (no fp) 8126508 B and plain `mp4` 8126508 B, `bytes_mod_262144` = **44**. Only mkv, nut, H.264 mkv (and the 0-byte AV1 mkv) are exact multiples. | "MKV and NUT files written without fp are exact multiples of 262144 B (e.g. 8126464 = 31 x 262144); the no-fp MP4/fMP4 files are 44 B over a multiple." |
| R2 | §2.3 "The **4** unreadable images (plain mp4/mp4+fp and the 0-byte AV1 mkv)" | `pyav19_recheck.json` → `kill[]`: 25 images = 19 remuxed + **5** unreadable (MJPEG mp4, MJPEG mp4+fp, H.264 mp4+fp, AV1 mp4+fp, AV1 mkv) + 1 segment directory (seg_mkv+fp, not remuxed). | Say 5 unreadable, and note seg_mkv+fp was not remuxed. |
| R3 | §5 "One fragment repeat is 0.04–0.1 s" | `bench/fragment_overhead_mjpeg_pyav19.json` → `folder` `wall_s` 0.620–0.660 s (206.6–219.9 µs x 3000). All other variants are 0.042–0.100 s. | "0.04–0.1 s (folder: 0.62–0.66 s)". |
| R4 | §4.10 "Every 30 keeps p50 at 16.1 µs, with p99 883 µs and max **4.2–9.1 ms**" | `bench/fsync_pyav19.json` → `fsync_every_30` per-repeat `lat_us_max` = 3596.4 / 4173.1 / 9065.2: median 4.2 ms, range **3.6–9.1 ms**. | "max 4.2 ms median (3.6–9.1 ms over repeats)". |

## Weak (true or close, but labelled, scoped or cited badly)

| # | claim | problem | fix |
|---|---|---|---|
| W1 | §2.11 "K=300 gives the **largest single stall**, 12.4 ms (median max)" | `sidecar_fsync_1` had a 58.9 ms worst frame in one repeat, and `fsync_every_10` 9.3 ms, `mkv_fp_fsync_30` 9.4 ms. 12.4 ms is the largest *median* max only. | "the largest median worst frame (12.4 ms); the largest single frame in any repeat was 58.9 ms (sidecar_fsync_1)". |
| W2 | §5 "the higher value for item 19 fits its `folder` variant (9000 file creates)" | The highest MsMpEng value is item **28** (repair, 10.25 CPU-s), not 19 (5.38). Item 28 writes four ~1 GB recordings, nine ~1 GB PyAV remux outputs, and three 1 GB copies each repaired into a new ~1 GB file (`bench_repair.py:81-116`, `resumable_recorder.py:204-233`). | Mention item 28 as highest, with the inferred cause (bulk writes), and keep item 19 as second (inferred). |
| W3 | §2.12 "only muxing and file writing are timed (`:9-10`, `:117-164`)" | For the intra payloads the timer also covers opening and probing the template file (`bench_fragment_overhead.py:147`, inside `t0w` at `:124` and `:158`). | Add "for the intra rows, plus opening the template file (`:147`)"; the size of that cost is not measured. |
| W4 | §2.5 CRF vs CQP "(log lines 9, 18, 33, 42)" | Lines 9 and 33 are `Number of PPCS 161` / `1`, not the rate-control mode. Lines 18 (`CRF / 35.00`) and 42 (`CQP / 35.00`) carry the claim. | Cite lines 18 and 42 for CRF/CQP; lines 9/33 only as the lookahead (PPCS) difference. |
| W5 | §2.4 AV1 fmp4_every+fp "torn last sample handed to the decoder: yes, 12/12" | `truncation_pyav19.json` has `mjpeg_torn_last_packet_delivered: null` for AV1; what is measured is 12/12 PyAV `InvalidDataError` and `ffprobe_eq_ideal` 12/12. | Label the AV1 "yes" as inferred from the 12 decoder errors. |
| W6 | §2.2 bg "every drained MKV, WebM, AVI and raw-MJPEG row ... has `pos_after == 1.0`" | 6 drained AV1 rows in `kill_matrix_b.json` (mkv, mkv_cl0, mkv_resv, webm, webm_cl0, avi) did not open in cv2 and have no seek. | "every drained row that cv2 could open". |
| W7 | Header: machine/GPU/driver labelled **source** (`HANDOFF.md:111`, `:113`) | HANDOFF is a study file, not a primary source. | Label it as the study record (or measured via `nvidia_smi` in the JSONs). |
| W8 | §4.11 "a 54,000-frame per-frame fMP4 takes 1107.28 ms to open in cv2" | The file is `fmp4_perframe_tb_us` (µs time base), a finalized file; the 1 s row is `fmp4_1s_tb_us`. | Name the variants and say they are finalized files. |
| W9 | §2.10 table: "kill only the feeder" shown as "-" for MKV x264 and MKV MJPEG copy | `sfn26_pipe.md` has 300/300 for both. | Fill in 300/300. |
| W10 | §5 smoke files are "30–352 frames, 1 repeat, loaded machine (measured, their `env` and `frames`)" | `repair_smoke.json` has no `repeats` field; "loaded machine" is not in any of those files (they ran 11:21–11:57 on 2026-11-09). | Drop "1 repeat" for repair_smoke and label "loaded machine" as inferred from the daytime start times. |
| W11 | §5 all-intra "rests on the queue's smoke check ... and on byte equality (inferred)" | Now directly measurable: ffprobe shows 300/300 K-flagged packets in both templates, and the script passes `is_keyframe` through (`bench_fragment_overhead.py:84`, `:154`). | Upgrade to measured (ffprobe of the templates, 2026-11-10, by this verifier) and cite the code lines. |
| W12 | §2.13 rawidx row "(.mjpeg read with `-f mjpeg`)" | The PyAV path uses `av.open(..., format="mjpeg")` (`bench_repair.py:84`, `common_cr.py:299`); `-f` is CLI syntax and the CLI was not used for repair. | "read with PyAV `format="mjpeg"`". |

## Things that hold up

- No number in the draft comes from BENCH.md without matching the JSON; no contaminated daytime number is quoted; PyAV 18 rows are marked bg throughout.
- The only quality-dependent numbers (intra payload sizes) say target A and that their quality was not measured. Nothing else in the topic depends on target A or B.
- The section 5 run flags are applied correctly: P-cores for all four CR items, libx265 and NVENC-12 flags correctly marked not applicable, CPU columns dropped for the 15.625 ms tick, Defender ON stated.

## Verdict

Mostly sound. All timed tables recompute exactly from the quiet-run JSON, and every re-fetched source quote and line matches. There are four small factual errors (R1–R4) and twelve labelling or scope issues (W1–W12). None of them changes an implication in §4. Fix them before saving.
