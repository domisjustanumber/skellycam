# intra_playback: step 3 verification (provenance + method), 2026-11-10

Scope: only the new or changed claims from gap-fills GF05, GF08 and GF10 in the step 3 FINDINGS draft. No test and no timed measurement was run. Every value below was re-read from the cited file by script or by direct reading.
Paths are relative to `research/skellycam_recording/recording_upgrade/` (RU). `R` = `results/intra_playback/`.

## 1. Confirmed

### GF05 (doc fixes)

| claim in draft | check | result |
|---|---|---|
| §6 HEVC 4:2:2: E35 `DEMUXER_ERROR_NO_SUPPORTED_STREAMS`, E45 opens then `PIPELINE_ERROR_DECODE`, 4:2:0 control plays | `results/chromium_codecs/raw/verify_method_rechecks.json` `hevc422_probe_and_play.play_file_url` | confirmed: E35 error 4, E45 error 3; control `loadeddata` true in both (rVFC 10 / 11). The file is the 720p `hevc_qsv ... native422_yuyv422.mkv`, ffprobe Rext |
| C17a: E45/C156 probes say "probably"/supported | `results/chromium_codecs/FINDINGS.md:123-127`; `probe` block in the same JSON | confirmed (E45 in the JSON; C156 via `*_main.json` as cited by C17a) |
| Supporting only `hw_accel_target/NOTES_functional.md:126` | read line 126 | confirmed: `hevc_cuvid`, `hevc`+cuda, d3d11va, d3d12va (NVIDIA adapter) and dxva2 fail |
| F16 pointer `uncompressed_intra/VERIFY_method.prev.md:28` (row R1) says "Main"; current `VERIFY_method.md:28` is NVENC lossless | read both lines | confirmed; line 28 of `.prev` carries the GF05 annotation |
| BENCH.md 48 raw cells; E45 H.264 NVENC WebCodecs N = 8 37.9 -> 39,695,312 | `R/gapfill/GF05_private_kb_cells.json` (50 edits: 2 headers + 48 cells); 48 raw `private_kb` cells counted in `R/BENCH.md` lines 235-258, 264-287 | confirmed |
| BENCH.md line 355 60 Hz remark corrected | read line 355 | confirmed |

### GF08 (timestamp sync)

| claim in draft | check (`results/chromium_sync_scrub/gapfill/GF08_ts_sync.json`) | result |
|---|---|---|
| 0 identity mismatches over 456 ticks per camera, JPEG + ImageDecoder and h264_nvenc + WebCodecs flush, E35 and E45 | `mismatch_table`: 48 cells, all `ticks` 456, identity + selection + decode failures sum = 0 | confirmed |
| 3,157 decodes per Electron for path `h264` | `electron.<ver>.rows` with `chosen_k` >= 0: 3,157 per path per Electron | confirmed |
| 174/174 rows choosing frame 81 or 82 correct | rows with cam 0, `chosen_k` in {81, 82}: 87 per Electron (29 per path), all `decode_ok`, `read_id` = `chosen_k` | confirmed (174 is the sum over both Electrons) |
| target A settings: h264_nvenc constqp qp 14, i_qfactor 1 | `GF08_generation.json` `settings_source` "... h264_nvenc_420 / mjpeg_720p (target A)"; `results/intra_compare/matched_settings.json` `h264_nvenc_420.mjpeg_720p` value 14, SSIM-Y 0.99611 | confirmed (settings) |
| frame-index sync and MKV ms pts do not reproduce PREV (§2.4) | `offline.frame_index_sync_vs_timestamp` (58/414, 0/328, 27/338); `offline.container_pts_instead_of_sidecar` | confirmed |
| No timing | GF08_ts_sync.md header: "no timing numbers" | confirmed |

### GF10 (WebCodecs scrub memory)

Recomputed from `R/gapfill/GF10_wc_scrub_memory.json` `configs[*]` (100 configs: main 48, diag 40, orig 12).

| claim in draft | recomputed | result |
|---|---|---|
| 64 readback configs, 58 every target (240/240), 6 every 20th (12/12) | `readevery` 1: 58, 20: 6; `checked_per_stream` = `exact_per_stream` in all 64 | confirmed |
| 0 errors, 0 GPU replacements, every checked frame exact | errors 0, `gpu_replacements` 0, `child_process_gone` 0, wrong 0, unreadable 0 | confirmed |
| mark peaks 324,224-967,496; sampler 1,002,132 | min/max `gpu_private_kb_peak_marks` 324,224 / 967,496; max `gpu_private_kb_peak_bg500ms` 1,002,132 | confirmed |
| no readback: 21 of 24 configs crashed, 35 crashes, 2,949 errors, exitCode 34 | 24 configs, 21 with crashes, 35 crashes, 2,949 errors; all 47 `child_process_gone` events (incl. orig) are GPU / crashed / 34 | confirmed |
| original loop 12/12 crashed, 1,479-8,378 errors | orig 12 configs, all crashed, errors 1,479-8,378 | confirmed |
| 6 configs end `video_decode: disabled_software` | 6 | confirmed |
| max 2,280,968 in any sample | max over marks and 500 ms samples: 2,280,968 (`reuse_re0` hevc_nvenc N = 8 E35) | confirmed |
| code: bench scrub loop draws and closes with no readback, `harness.mjs:501` | read `scripts/chromium_sync_scrub/harness/harness.mjs:501` | confirmed |
| code: `wc-master` caps decode-ahead at 8, draws on rAF (`:326`, `:426-443`) | read lines | confirmed (code content) |
| No rate, latency, fps or CPU | GF10 header; draft states it | confirmed |

## 2. Refuted

| claim | why | correction |
|---|---|---|
| §8 GF05: "`R/BENCH.md` lines 40, 233, 262, 293, 295, 334 and 355 carry GF05 marks" | Line 295 was edited (series label now `private_kb` / 1,048,576, unit NOT VERIFIED) but has no "GF05" mark; `grep GF05 R/BENCH.md` hits 40, 233, 262, 293, 334, 355 only. GF05's own edit list gives 295 without "+ mark". | "lines 40, 233, 262, 293, 334 and 355 carry GF05 marks; line 295 was edited without a mark" |

## 3. Weak (fix wording)

1. **"at target A" (§6, P9, §8 for GF08 h264).** GF08 used intra_compare's target-A settings (qp 14, from `mjpeg_720p`) on barcode-burned frames; quality on those frames was not measured. Say "at target-A settings (quality of the barcoded frames not measured), 720p only".
2. **F19 addition and P1 (GF08 scope).** GF08 used synthetic drops on real timestamps, camera clocks aligned by construction (cross-camera alignment NOT VERIFIED, GF08 §3), a fixed shuffled tick list (not rAF playback), 720p, N = 4, no HEVC and no `<video>`. The `jpeg` path cannot detect a cam0/cam2 mix-up (same bytes). Add a one-line scope; "master clock" here means fixed ticks, not a running clock.
3. **P2.** Both PREV and NEAREST were exact (GF08 §2.1); choosing PREV is inferred (GF08 §3). The hold limit was run only at P, which flags normal capture jitter (GF08 §2.2; 1.5·P is inferred, not run). "MKV ms pts" omits that MP4 1/90000 pts also differed on 5-28 ticks per cam × rule.
4. **F22 GF10 (a) mode list.** It reads as if `baseline` covered all codecs at N = 1/4/8. Baseline lockstep was N = 1/4 (3 codecs); N = 8 baseline was only free-drive h264_nvenc (and N = 4).
5. **F22 "code:" bullet.** "So the 23:00 run's WebCodecs scrub rates measure an unsynchronised loop, not decode capacity" is an inference under a code label. Split: code (line 501) + inferred (conclusion).
6. **F22 inferred note on `wc-master`.** "draws on rAF, which is a natural back-pressure point" is an untested mechanism, and §6 lists rAF pacing as not measured. Mark it "untested (§6)" or drop the rAF clause.
7. **F24 and §3.2 now stale against GF10.** The GF10 control re-run of the bench's own scrub loop crashed the GPU process in all 6 E45 configs (and 6 E35). §3.2 "GPU process replaced: E35 3 configs / E45 0" and F24 should point to GF10 so E45 is not read as more stable.
8. **§6 HEVC 4:2:2 "does not play on this RTX 3070".** E35's failure is a demuxer rejection (it never reaches the GPU); only E45's `PIPELINE_ERROR_DECODE` concerns decode. Say "does not play in E35 (demuxer) or E45 (decode, RTX 3070)".
9. **P7.** "every few targets" goes beyond the tested every-20th; "rebuild decoders after a GPU-process crash" is inferred and did not help HEVC after 3 crashes (`disabled_software`). State "tested: every target or every 20th" and the HEVC limit.
10. **174/174.** It is the total over both Electrons (87 each). Say so.

## 4. Verdict

GF05, GF08 and GF10 numbers and pointers in the draft match the files. One factual slip (BENCH.md line 295 has no GF05 mark). The rest is scope wording: GF08 "target A" means settings only and its sync test is synthetic and tick-based; GF10's baseline coverage and two inference labels need tightening; F24/§3.2 should cite GF10's E45 crashes. No timing claims from concurrent runs were added.
