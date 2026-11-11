# GF04: jellyfin_ffmpeg doc fixes (proposed text; FINDINGS.md not edited)

Date 2026-11-10. Gap-fill GF04 (doc_fix). Sources and result files only. No test, no timing, and no timing number in this topic (HANDOFF §1 requirement 4). Line numbers refer to `R/jellyfin_ffmpeg/FINDINGS.md` as of 2026-11-10 (463 lines).

Paths: `R` = `research/skellycam_recording/recording_upgrade/results/`, `IB` = `R/intra_compare/bench/`.

## Item 8a. Replace §5

Old (lines 335–344):

> ```
> ## 5. Pending tonight's bench (23:00)
>
> - No jellyfin-ffmpeg item is queued. Testing it is out of scope by rule (HANDOFF §1 requirement 4).
> - These queued PyAV 19.0.2 items decide whether the wheel alone covers the target, and so whether any jellyfin-only option is ever needed:
>   - CPU JPEG vs nvJPEG vs `mjpeg_qsv` for YUY2/NV12 at 720p/1080p (HANDOFF §1 req. 11);
>   - `B-QSV-1` and `B-QSV-C4` (mjpeg_qsv), `B-NV-1` and `B-NV-C1/C2` (NVENC), and `B-QSV-C1/C2` (QSV H.264/HEVC) (`R/hw_accel_target/NOTES_functional.md:195-204`).
>   - Those commands also run `gop30` legs. Only the **intra** legs bear on this topic; GOP results are background (requirement 10).
> - The results will not change §3.1. They can only confirm or weaken the Windows row's "Tie for the target codecs on Gerald" verdict.
> - No timing numbers from the bench belong in this topic.
> ```

New:

> ```
> ## 5. Bench status (quiet run 20261109T230007)
>
> No jellyfin-ffmpeg item was queued, by rule (source: HANDOFF §1 requirement 4). The `B-QSV-*` and `B-NV-*` items this section used to list were not queued either: none of the 68 ids in `R/bench_queue_2300.json` is a `B-*` id, and the queue replaced them with matched-quality intra_compare items (measured: `R/bench_queue_2300.json`; `R/BENCH_QUEUE_2300.md:216-222`). The intra_compare items that did run, all with status ok, use the PyAV 19.0.2 wheel's own encoders at target A on Gerald (measured: `R/BENCH_RUN_2300_LOG.jsonl` `status`; files in `IB`, aliases in the `R/intra_compare/FINDINGS.md` header). They are items 1–3 (single stream, all paths: `matched_stream_{A_1080p,A_720p,B_1080p}_*.json`), 4–5 and 49–50 (h264/hevc_nvenc), 6–7 and 51–52 (h264/hevc_qsv), 8, 33 and 53 (mjpeg_qsv 4:2:0 and 4:2:2), 34 (hevc_qsv 4:2:2), and 41–45 (pipelines from camera MJPEG and YUY2) (`matched_concurrent_*.json`). They bear on the Windows row's "Tie for the target codecs on Gerald" verdict (§3.1) only from the standard-FFmpeg side. They show that the wheel's NVENC and QSV H.264/HEVC and `mjpeg_qsv` encoders open and run at matched quality on Gerald with no jellyfin patch (measured). The jellyfin side stays source-only, so the verdict remains "Tie (inferred)". One caveat for the Tie: in its default mode, hevc_qsv was not a multi-camera path in those items (measured: `R/intra_compare/FINDINGS.md` §2.5). Its `low_power` speed is NOT VERIFIED (`R/gpu_encode/FINDINGS.md` I5), and no jellyfin patch in §3.2 is shown to change it (inferred, F31). Timing numbers stay in `R/intra_compare/FINDINGS.md` §3.3–§3.5 and are not repeated here.
> ```

Every claim in that paragraph was checked:
- `R/bench_queue_2300.json`: 68 `id` fields; 0 matches for `scripts/hw_accel_target`; no id starts with `B-` (grep, 2026-11-10).
- `R/BENCH_RUN_2300_LOG.jsonl`: items 1–8, 33, 34, 41–45 and 49–53 have `"status": "ok"`, `exit_code` 0 (read 2026-11-10). The summary reports 67 of 68 items ok, with OV-COST the only timeout (`R/BENCH_RUN_2300_SUMMARY.md` §1).
- Items 1–3: in each `matched_stream_*.json`, every NVENC/QSV `summary[]` row has `reps_ok` ≥ 3, and `skipped` is empty.
- F31 (§3.2 row "QSV low-power retry (0071)"): "Could help H.264/HEVC/JPEG QSV open on parts without low-power support (inferred)". That is about opening, not speed.

## Item 8b. Requirement numbers remapped to the current HANDOFF §1

Current numbering: HANDOFF.md §1 (4 = jellyfin-ffmpeg sources only; 8 = intra-only; 9 = H.264/HEVC intra vs JPEG at matched quality; 10 = timed tests from 23:00). Old numbering: `HANDOFF_20261109_1300.md:30-48`. There, item 9 includes the 17:35 head-to-head text, which lists the inputs "decoded camera MJPEG at 720p/1080p" and "YUY2/NV12" (line 46); 10 = intra-only (line 47); 11 = the queue (line 48).

| line | old | new |
|---|---|---|
| 1 | `requirement 4` | unchanged |
| 3 | `HANDOFF §1 requirement 4` | unchanged |
| 61 | `It covers H.264/HEVC intra from decoded camera MJPEG, and YUY2 to NV12 (requirement 9).` | `It covers H.264/HEVC intra from decoded camera MJPEG, and YUY2 to NV12 (HANDOFF §1 requirement 9; the inputs are listed in the 17:35 text, \`HANDOFF_20261109_1300.md:46\`).` |
| 292 | `HANDOFF §1 req. 4` | unchanged |
| 333 | `requirement-4 table` | unchanged |
| 337 | `HANDOFF §1 requirement 4` | unchanged (inside the new §5) |
| 339 | `(HANDOFF §1 req. 11)` | requirement 10 (timed tests). The line is removed by item 8a |
| 341 | `(requirement 10)` | requirement 8 (intra-only). The line is removed by item 8a |
| 448 | `Requirement 9 includes a decode + convert leg` | `Requirement 9 (17:35 text, \`HANDOFF_20261109_1300.md:46\`) includes a decode + convert leg` |

§8 (verification log) line 453, row `§5 bench items`, is revision history. Keep it.
