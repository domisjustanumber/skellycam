# intra_playback: provenance check of the 2026-11-10 draft FINDINGS

Verifier: provenance lens. Date 2026-11-10. No timed runs; only JSON reads, code reads and one source fetch.
Paths are relative to `research/skellycam_recording/recording_upgrade/` (RU). `R` = `results/intra_playback/`.

**Verdict: mostly sound.** Every number below was re-computed from the raw JSON, and almost all of them match. There are 2 refuted claims (a GPU-memory unit conversion and a vsync arithmetic error) and 11 weak points to fix.

## 1. What was checked and matched (re-computed from raw files)

| claim | check | result |
|---|---|---|
| F1–F3, F5 functional totals | re-summed `R/functional/<e35,e45,c156>/seek_*.json`, `step_*.json` per encoder, path and mode | `mid` 1200/family; WC `wcflush=1` 1200/family, `decoded_hist {"1": n}`; steps 1464/family; `cfrmid` CFR 600/600, VFR 57/600 per family; same in all three browsers |
| F5 histogram | `seek_vfr720p.json` `off_by_hist` | `{1:39,2:33,3:21}` on all 36 vfr720p clip×browser rows; vfr1080p `{1:55,2:33}` |
| F4 JPEG | same files | seeks 800/decode path, steps 976/decode path, play 600 draws / 0 mismatches CFR and VFR |
| F7 | `play_vfr*.json` | 25/3549 (E35), 62/3426 (E45), 55/3294 (C156); all 142 examples have pattern = mt_idx+1 |
| F9 | Media log `kVideoDecoderName`; `gpu_info.gpuDevice` | D3D11VideoDecoder for every `<video>`/WC/WC-hw H.264+HEVC row; active GPU 0x10DE:0x2484, driver 32.0.16.1088 in all 140 bench JSON |
| F10, F11 | `seek_*.json` summary `flushes`, errors | HEVC `prefer-software` "config not supported"; H.264 sw FFmpegVideoDecoder 360/360; `flushes` 360/360 only for `h264_nvenc` (no-pref and hw) |
| F12 | `R/sps_vui_trace.txt` | matches |
| F13, F15 | `seek_*.json`, `caps.json` | matches (MKV canPlayType "" / unsupported in E35 only) |
| F14 | `jpegmkv_seq.json`, `jpegmkv_random.json`, `clips_summary.json` | 300+150 identical/SOI-EOI/bitmap/ImageDecoder in all three; `pos_delta_hist {"4": n}` on every MKV |
| F16 | `results/uncompressed_intra/chromium_check_electron{35,45}.json`, `make_chromium_samples.py:46`, `intra_compare/verification.md` rows 51–54, `uncompressed_intra/VERIFY_method.md:28` | matches |
| F17, F18 | `bench/*/bench_intra_seek/*.json` | 200/200 ×24; all p50/max/`seeked` ranges match; max is the first seek in 7 of 8 WC configs (E45 h264_qsv at index 32) |
| F19–F21, 3.1, 3.2 sync | `bench/*/bench_intra_sync/*.json` | 28 master configs 100% spread 0; CPU, WS, rVFC/s, slowest/median 42.5–59.7% (+ one 78%), max spread 100–245, N=4 max 2–4, exact0 21.0–90.3% all match |
| F22 errors / pids | `bench/*/bench_intra_scrub/*__webcodecs__*.json` | 300+4+80+523+7 = 914 (E35), 0 (E45); 3 E35 N=8 configs with 2 GPU pids; non-WC GPU peak ≤ 0.86 GiB |
| F23 table | scrub JSON | every cell matches |
| §3.3 | `clips_summary.json` (`bytes`/`frames`, `decode_check(_mp4)`) | matches; range 54.49–55.72 dB across all clips |
| code refs | `harness.mjs:70,71,74,129,137-160,238-313,501`; `run_suite.py:246-275,358(-361)`; `summarize.py:181-186`; `main.cjs:66-68,93-101`; `skellycam-ui/.../SyncedVideoPlayer.tsx:334` | all say what is claimed (`index.append` itself is at `run_suite.py:361`; 358 is the `result.error` extraction) |
| HANDOFF correction | `HANDOFF.md:170` | does say "The UI's current seek rule `(k+0.5)/fps`" |
| background refs | `chromium_sync_scrub/FINDINGS.md` F7 (line 50), F14 (line 108, `ui` 0/122 vfr720p), F16a; `chromium_codecs/NOTES.md:122`; `hw_accel_target/NOTES_functional.md:126` | match |
| §5 load record | `results/BENCH_RUN_2300_LOG.jsonl` | 11 IP items, none `load_over_15pct`, mean ≤ 4.11%, max 10.25%, MsMpEng 0.19–29.19 CPU-s, no Defender events; times 00:34:58–01:13:36 and 03:43:11–03:51:50 |

## 2. Refuted

1. **F22: "9.1–37.9 GiB ... that is 9.6–39.7 GB decimal".** The two figures use different units for `private_kb`.
   - measured: the raw peaks are 9,586,248–39,695,312 `private_kb`.
   - /1024² gives 9.14–37.86, which is GiB only if the unit is 1024 bytes. Then the decimal value is ×1024/1e9 = **9.82–40.65 GB**.
   - The draft's 9.6–39.7 is ×1000/1e9, which assumes 1000-byte kB. That would make the GiB figure 8.93–36.97.
   - source: Electron MemoryInfo, https://www.electronjs.org/docs/latest/api/structures/memory-info, "Note that all statistics are reported in Kilobytes." (accessed 2026-11-10). This does not say whether a kilobyte is 1000 or 1024 bytes.
   - Fix: quote the raw `private_kb` range and give one conversion with its assumption. For example: "9.14–37.86 GiB if the unit is KiB (NOT VERIFIED whether Electron's Kilobytes are 1024 bytes)". P7 and §5 should use the same wording.
2. **F18: "inferred: about 14 ms is one 60 Hz vsync".** One 60 Hz frame is 16.7 ms, not 14 ms. The display refresh rate was also not recorded.
   - Fix: drop the vsync claim, or say "the p50 is under one 60 Hz frame (16.7 ms), if the display ran at 60 Hz (refresh rate NOT VERIFIED)".

## 3. Weak (fix the wording or the label)

1. **F24: "This matches the functional VFR rVFC counts (F7)."** This picks the one subset that agrees.
   - The functional CFR counts go the other way: E35 3535 vs E45 3600 (`play_c*.json`).
   - The functional runs were also run in parallel on a non-quiet machine.
   - Fix: delete the sentence, or quote both subsets and say the functional runs carry no rate claims.
2. **§3.1 JPEG `ImageDecoder` N = 8 scrub "58.0–58.6", in a table labelled E45.** E45 is 58.0–58.5. The 58.625 comes from E35 (`e35/.../jpeg_seq__jpeg-range-imagedecoder__n8.json`).
   - Fix: write 58.0–58.5 (E45).
3. **P7: "crashed E35's GPU process 3 times".** The evidence is a second GPU pid in `metrics_samples` and private bytes falling to about 0.1 GB. A crash is inferred, not logged.
   - Fix: write "the GPU process was replaced (new pid) in 3 configs", or label "crashed" as inferred.
4. **F11: "no frame came out after one decode()".** The code waits `flushAfterMs \|\| 200` ms and then forces a flush (code: `harness.mjs:153-158`).
   - Fix: write "no frame came out within 200 ms of `decode()`".
5. **P3: "the JPEG passthrough path (G1, G7) meets G9".** The benched JPEG clips are not camera bytes. They are `mjpeg_qsv` 4:2:2 q90 re-encodes at about 207 KB/frame (`clips_summary.json` `c1080p30/jpeg_seq`, `codec`).
   - Camera-byte MKV access (F14) was only tested functionally, on `c720p30/camera_bytes_mkv`, untimed.
   - Fix: label P3 inferred and say the timed JPEG numbers are for re-encoded JPEGs of similar size, not the cameras' own files.
6. **F14 does not name the content.** It was 720p only (`c720p30/camera_bytes_mkv`, 300 frames).
   - Fix: add "720p, 300 frames".
7. **F4 playback pattern check.** Only `jpeg-master-range-bitmap` was played (`run_suite.py:224`). `ImageDecoder` was not part of the play check.
   - Fix: say "playback check: `createImageBitmap` path only".
8. **F21: "N = 8 spread p95 was 86–217 frames".** That range holds only for the leader and rVFC-steered configs. The free configs reach p95 244–245 (e.g. `e35/.../h264_qsv_intra.mp4__video-free__n8.json`, p95 244).
   - Fix: say "leader / rVFC configs: p95 86–217; free: 195–244".
9. **§5 and the `B` definition: "pinned to 16 P-core logical CPUs".** The runner sets its own affinity and relies on children inheriting it (code: `scripts/bench_runner/run_queue.py:21-22,441-446`; log `affinity: "pcores"`).
   - No IP JSON records the affinity of the Electron, GPU or renderer processes.
   - The libx265 items show a child can widen its affinity (BENCH_RUN_2300_SUMMARY §3 flag 2).
   - Fix: write "launched with P-core affinity (inherited); the Electron processes' actual affinity is NOT VERIFIED".
10. **§5: the 15.625 ms timer flag "does not apply".** `cumulativeCPUUsage` on Windows may have the same coarse granularity. That is not checked here (NOT VERIFIED).
    - inferred: the effect is at most about 0.002 cores per process over an 8–15 s window, so it is negligible.
    - Fix: write "negligible (inferred)", not "does not apply".
11. **F23: "input every ~16 ms".** The code calls `sleep(16)` per tick (code: `harness.mjs:507`). The recorded `input_events` are 365–479 per 8 s, a mean interval of 16.7–21.9 ms.
    - Fix: cite the code and the measured event counts.

## 4. Labels, targets and PyAV versions

- Target labelling is correct.
  - The draft says throughout that these clips are at about 55 dB, not target A or B (§1, §3.1, §3.3, P9).
  - It uses no intra_compare A/B numbers.
- PyAV 19.0.2 is the clip generator (`clips_summary.json` `generator`; NOTES §2). No PyAV 18 result is presented as primary.
- No daytime or contaminated timing is used. All timed numbers are from run `20261109T230007`.
- Unlabelled claims: P1, P2, P4 and P6 cite findings but have no label. P1, P5, P8 and P9 are labelled inferred. Mark P2, P4 and P6 as "inferred from F…", or label each one measured / code where that fits.
