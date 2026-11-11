# chromium_codecs: step 3 verification (GF05), provenance + method

Date 2026-11-10. Scope: only the claims GF05 adds or changes in the draft: header line, C27 last bullet, P2, P3, P4, §5, the §8 queue row and the §8 step 3 table. Everything else is out of scope.

Paths are relative to `research/skellycam_recording/recording_upgrade/`. My helper script: `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step3/cc_verify/v.py`. I ran no tests and took no timings.

## 1. Provenance checks

| check | result |
|---|---|
| `scripts/chromium_codecs/gf05_extract_intra_playback.py` re-run into scratch | output identical to `results/chromium_codecs/gapfill/GF05_intra_playback_extract.json` (24 seek, 68 sync, 48 scrub rows) |
| Bench files come from the quiet run | mtimes: seek 00:35–00:36, sync 00:36–00:51 and 03:43–03:51, scrub 01:04–01:13 (2026-11-10). These fall inside the IP-SEEK/SYNC/SCRUB/SYNC-QSV `start`/`end` windows in `results/BENCH_RUN_2300_LOG.jsonl`. Smoke folders are excluded by the glob |
| Queue | `results/bench_queue_2300.json`: 68 items. IP-SEEK/SYNC order 12–15, IP-SUM 16, IP-SCRUB 25–26, IP-SUM-2 27, IP-SYNC-QSV 46–47, IP-SUM-3 48. Topics do not include `chromium_codecs` |
| Log lines | 13–16, 26–27 and 48–49 are the timed IP items; 17, 28 and 50 are IP-SUM. All 11 lines have `status` ok. The draft's narrowed citation is correct |
| Seek | 24/24 configs 200/200. p50 ImageDecoder E35 4.4/4.4, E45 4.6/4.6. Bitmap 7.1/7.0 and 6.1/6.0. WebCodecs E35 3.1–3.4, E45 2.7–2.9. `<video>` rVFC E35 11.8–14.1, E45 8.5–14.1. All match |
| Sync spread | 28 master-clock configs (16 `wc-master`, 8 JPEG bitmap, 4 JPEG ImageDecoder), all spread 0/0/0 with 100% of ticks at 0. Matches |
| Sync CPU, N = 8 | ImageDecoder 1.4516 / 1.4401; bitmap 2.548–2.563 / 2.1375–2.1385; `wc-master` 0.575–0.630 / 0.508–0.575; `<video>` 0.452–0.563 / 0.436–0.553. All round to the drafted ranges |
| `<video>` N = 8 | 20 configs, max spread 100–245. min/median rVFC is 0.416–0.585 in 19 configs; the exception is E35 `hevc_qsv` `video-rvfc` at 0.778 with max spread 100 |
| Scrub N = 8 | ImageDecoder 58.0–58.625; bitmap 41.75–50.75; gated `<video>` 17.25–45.5. E35 WebCodecs errors 300+523+4+80+7 = 914 in 5 configs. WebCodecs GPU `private_kb` peak 9,586,248–39,695,312 over 16 configs. All match |
| Clips | `IP/clips_summary.json` `c1080p30/*`: 600 frames, `distinct_source_frames` 19, `vfr` false. H.264/HEVC are `.mp4`; JPEG is `jpeg_seq` (`clip.mjpeg`) and `jpeg_in_mkv` (`mjpeg_qsv422.mkv`), `mjpeg_qsv 4:2:2` |
| ~55 dB, not A/B | `IP/FINDINGS.md:20-22` |
| IP references | F17 `:93`, F19 `:102`, F20 `:103-107`, F21 `:108-114`, F22 `:115-126`, F23 `:129-140` (ceiling), P1 `:206`, P3 `:211-215`, §5 pixel note `:243`. All say what the draft attributes to them |
| Code | `scripts/chromium_sync_scrub/harness/main.cjs:93-101`: CPU is the sum of Electron `cumulativeCPUUsage` per pid. `run_suite.py:246-275`: sync configs set no `readpattern` |
| HANDOFF numbering | `HANDOFF.md:35` is requirement 3 (hardware target); `:43` is requirement 9 (matched quality). The P4 fix is correct |
| Timing rule | every timing number comes from the quiet-run files. No timing comes from concurrent or functional runs |

## 2. Refuted

None.

## 3. Weak

| claim | why | fix |
|---|---|---|
| P2: "at N ≤ 8 … the JPEG path stays frame-exact (200/200 seeks)" | The seek bench is N = 1: the queue purpose says "N=1 1080p, 200 random seeks", and `run_suite.py:248-254` sets `n` = 200 seeks with no stream count. At N = 8, exactness is only index-based sync spread with no pixel readback (`run_suite.py:255-262`; `IP/FINDINGS.md:243`) | Write: "frame-exact seeks at N = 1 (200/200); N = 8 sync spread 0 (index-based, no pixel readback)" |
| §5 bullet F21: "in 19 of 20 … 42–60% … giving max spread 100–245 frames" | The max spread of 100 belongs to the exception config (E35 `hevc_qsv` `video-rvfc`, 78%). The 19 stalled configs have max spread 147–245 | Write: "max spread 100–245 across all 20 configs (147–245 in the 19 stalled ones)", or drop "giving" |
| §5 table row "WebCodecs H.264/HEVC intra (`wcflush`), master clock" | `wcflush=1` is set only for seek and scrub (`run_suite.py:252,269`). The sync `wc-master` config has no `wcflush` (`run_suite.py:258-259`), and its CPU and spread cells come from sync | Label: "WebCodecs H.264/HEVC intra (seek/scrub `wcflush=1`; sync `wc-master`)" |
| §5 table row and P2 for JPEG `ImageDecoder`: N = 8 sync spread 0 and 1.44/1.45 cores | Only `jpeg_seq` (`.mjpeg`) has an ImageDecoder sync config. JPEG-in-MKV ran bitmap only (`run_suite.py:260-261`) | Add "(`.mjpeg` only)" to the sync spread and CPU cells and to the P2 sync clause |
| P2 bullet labelled "inferred (IP P3)" that also carries 2.14–2.56 cores and 41.75–50.75 shown/s | The numbers are measured (extract, both Electrons). IP P3 quotes only the E45 figures (2.14; 49–51). Measured and inferred are mixed in one bullet | Split it: measured numbers (§5) in one bullet, "inferred (IP P3): prefer `ImageDecoder`" in the other |

## 4. Verdict

PASS with minor fixes. Every new number re-derives exactly from the quiet-run bench JSON, and every citation says what is attributed to it. There are no timing claims from concurrent runs. Five wording and scope points are weak: one scope over-reach in P2 (N = 1 seeks presented as N ≤ 8), one misattributed range in the F21 bullet, two label or scope gaps in the §5 table, and one bullet in P2 that mixes labels.
