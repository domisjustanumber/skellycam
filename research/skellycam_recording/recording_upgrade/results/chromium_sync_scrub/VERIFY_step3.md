# chromium_sync_scrub: VERIFY_step3 (provenance + method, step 3 changes GF05 / GF08 / GF10)

Date 2026-11-10. Verifier checked only new or changed claims in the step 3 FINDINGS draft. No test or timing was run; all checks are file reads and recounts (Python over the JSON, grep over code). Paths relative to `research/skellycam_recording/recording_upgrade/` unless written out.

## Verdict

Mostly verified. 2 claims refuted (one misquote, one over-tidy summary of a histogram), 6 weak. Every number in F26–F28, the GF10 bullets, §5 and the F25 additions matched its source. No timing from concurrent runs is quoted: the timings in §5 / I3 come from intra_playback's quiet run 20261109T230007 (F18, F19, F21); GF08 and GF10 recorded none.

## Refuted

| Claim | Evidence | Correction |
|---|---|---|
| Scope note: HANDOFF §1 requirement 8 says "Only intra-only formats are in scope ... Existing GOP results are background only." | `HANDOFF.md:42`: "**Only intra-only formats are in scope** (every frame a keyframe). GOP/inter results are background only." The words "Existing GOP results" are not in the current text. The number was changed (10 → 8) but the quote was not. | Quote verbatim: "Only intra-only formats are in scope (every frame a keyframe). GOP/inter results are background only." |
| F28(b): "The differences are ±1 frame or a status flip at an edge." | `gapfill/GF08_ts_sync.json` → `offline.container_pts_instead_of_sidecar.*.k_container_minus_k_sidecar_hist`: `jpeg\|PREV\|cam0` and `jpeg\|PREV\|cam2` each contain `"-2": 1`; several cells contain `"0"` (same k, different status, e.g. `jpeg\|PREV\|cam2` `"0": 4`). | "The differences are ±1 frame, −2 frames on one tick each in MKV PREV cam0 and cam2, or a status change (stale flag, before start, after end)." (Same wording sits in `gapfill/GF08_ts_sync.md` §2.4.) |

## Weak

| Claim | Why | Fix |
|---|---|---|
| Version note and §6: "No Electron run in sections 2.1-2.6 used a PyAV 19 file" | §2.6 F25 now has two bullets on PyAV 19.0.2 files played in Electron (intra_playback F1–F3, and F26). Inconsistent inside the file. | "No Electron run in this topic's functional suites (F10–F24) used a PyAV 19 file." |
| I3: N = 8 `<video>` "stalled in 19 of 20 configs, max spread 100–245 frames" | intra_playback F21: in 19 of 20 configs the slowest stream got 42–60% of the median's rVFC callbacks; the 20th got 78%. "Stalled in 19 of 20" restates a threshold F21 does not use; the 100–245 range is over all 20. | "the slowest of 8 tiles got 42–60% of the median tile's rVFC callbacks in 19 of 20 configs (78% in the 20th); max spread 100–245 frames (intra_playback F21)." |
| F26 "Active GPU: NVIDIA"; §6 "Chromium listed no Intel device during these runs (F22)" | `gapfill/GF08_ts_sync.json` → `electron.{35,45}.gpu_device` lists vendor 32902 device 42880 ("Intel(R) UHD Graphics 770" in E45), `active: false`. F22 is still true for `functional/e*/caps.json` (no Intel hit), but §6 now reads as if Chromium never saw the iGPU. | Add: "GF08 and GF10 runs (2026-11-10) list the UHD 770 as an inactive device; decode ran on NVIDIA." |
| F27 inferred "the bench never hit these cases ... (`harness.mjs:426-430`)" | `:426-430` covers only `floorIdx` in the sync loop. The after-end part also needs bench `dur` (default 10 s, `harness.mjs:361`) < clip length (600 frames, 20 s). `nearestIdx` is used at `:266`, `:375`, `:474` on rVFC `mediaTime` (a frame pts, so no midpoint ties). | Cite `:361` and the `nearestIdx` call sites with that reason. |
| I3 sentence describing the PREV rule with "holds inside gaps with a stale flag, and shows nothing after a hold limit" | Written as fact, no label. It is a design recommendation; the threshold was run only at P, and the draft itself says P flags normal jitter (F28c). | Label "inferred (recommendation; tested at limit P only, F26, F28)". |
| I3 inferred: "NEAREST keeps the shown frame within P/2 of T (vs P)" | `offline.chosen_frame_distance` bounds only `ok` rows; `hold_stale` rows are further away for both rules. | Add "for `ok` frames". |

## Verified (new or changed claims)

| Claim | Check |
|---|---|
| Header: no timed bench of own; smoke only | `bench/e{35,45}/` holds only `bench_{seek,step,sync,scrub}_smoke/`; `_index.json` run counts 6/4/10/10 per Electron, `smoke: true`, `error: null` on every run |
| §5: queue has no chromium_sync_scrub item; IP items ran with this topic's runner, all ok | `results/bench_queue_2300.json`: 68 items, topics = 8 others; `BENCH_RUN_2300_LOG.jsonl` lines 13–16, 26–27, 48–49 = IP-SEEK/SYNC/SCRUB/SYNC-QSV E35+E45, `status` ok, cmd `run_suite.py --suite bench_intra_*` |
| §5: seed 11, 200/200 × 24, p50 2.7–3.4 / 4.4–4.6 / 8.5–14.1 ms, spread 0, N = 8 stall, scrub notes | intra_playback FINDINGS F17, F18, F19, F21–F23; `results/intra_playback/BENCH.md:86` (seed 11) |
| §5 code note: scrub loop `:497-504`, `:501` draw + close, `:502` count + sleep | `scripts/chromium_sync_scrub/harness/harness.mjs` lines read |
| GF10 bullets | `results/intra_playback/gapfill/GF10_wc_scrub_memory.json`: 64 readback configs, 0 errors / wrong / unreadable, all exact, peak 324,224–967,496, N 1/4/8, E35+E45, modes include `baseline`; 21 of 24 `readevery=0` with `child_process_gone` exit 34; 6 configs with 3 crashes = the 6 `disabled_software`; `origscrub` errors 1,479–8,378 |
| F25 additions | intra_playback F1–F3 (4800/4800, 5856/5856, `wcflush=1` 4800/4800); `results/intra_playback/clips_summary.json`: 48 clips with `nal_check`, all `frames_with_idr = frames`, `has_b_frames = 0`, `decode_order_equals_pts_order` true; codecs h264/hevc × nvenc/qsv |
| §6 NVENC/QSV playback bullet | intra_playback F9 (`D3D11VideoDecoder`, NVIDIA active); about 55 dB = `clips_summary.json` `calibration` target 55.0, clip `y_psnr_db_mean` 55.42 |
| F26 streams, offsets, frame counts, gaps | `gapfill/GF08_generation.json` `cameras`, `offset_ns`; raw start difference 164,995,500 |
| F26 result | 48 `mismatch_table` cells, ticks 456 each, identity + selection + decode = 0; recount of `electron.*.rows`: 3,157 decoded / 491 none per path per Electron, 0 bad; cam0 k 81/82 rows 29 per path per Electron (174) all correct; `wc_decoder_errors` and `wc_recreated` all 0 |
| F26 encode settings | `GF08_generation.json` `files.h264`: h264_nvenc, qp 14, i_qfactor 1, i_qoffset 0, gop_size 0, max_b_frames 0, `all_key`, decode = pts order; `matched_settings.json` `h264_nvenc_420.mjpeg_720p` qp 14 (SSIM-Y 0.99611) and `ff_mjpeg_422.mjpeg_720p` qmin = qmax = 2 (SSIM-Y 0.99619) = target A |
| P = 33,333,333 ns from `nominal_fps` 30 | `recording_upgrade_20261109/corpus/index.json`: both sets `nominal_fps` 30; `gen_gf08.py:47` |
| F26 versions, GPU | `electron.<ver>.versions` 35.7.5 / 134.0.6998.205, 45.2.3 / 156.0.8078.80; NVIDIA `active: true` |
| §2.7 "shared harness not edited" | original `harness.mjs` mtime 2026-11-09 18:28; GF08 copy differs only by the added block and the `TESTS` line |
| F27 | `harness_helpers` both Electrons: PREV differs 4 (cam2) + 1 (cam3) = 5, all `gap_edge`; NEAREST 4+2+9+3 = 18, all `mid`/gap ties; cam2 example `t_ns` 2,700,984,500 between ts 2,700,979,000 and 2,700,990,000 (the 0.011 ms pair); code `harness.mjs:57-67`, `r = 0` at `:64`, `1e-9` at `:65` |
| F28 (a), (c) and (b) magnitudes | `offline.frame_index_sync_vs_timestamp` 58/414, 0/328, 27/338; 321, 328, 296 vs 0, 27 (27), 9 (6); `intervals` medians 32,002,000 / 32,002,400, over P 71/75/59/58, over 1.5·P 0; MKV 14–31, max 386,479–1,010,000; MP4 5–28, max 5,534–5,545; boundary distance ≤ 327,433 / ≤ 1 |
| §3.1 JPEG pair cell, §3.2 row, I8 additions | GF08 row recount; intra_playback F24 |
| §3.3 heading | `clips_summary.json` settings crf 35/33/23, q90 (not matched to target A or B) |
