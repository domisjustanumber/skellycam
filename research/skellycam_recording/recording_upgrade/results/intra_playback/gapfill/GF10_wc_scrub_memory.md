# GF10: WebCodecs scrub with bounded GPU memory (configure-once and decoder-pool patterns)

Gap-fill for intra_playback F22 / P7 / §6 (G9). Run 2026-11-10, 09:48–10:19 local (modification times of the raw JSON, smoke run included), on Gerald while other study agents were running. Functional only.

**No scrub rate, latency, fps or CPU is reported here.** Targets come from a fixed list, not a wall clock. Memory is sampled at fixed target counts. Rate and latency of these patterns still need a later quiet-machine run, one item at a time.

Paths are relative to `research/skellycam_recording/recording_upgrade/` (RU).
- Raw data: `results/intra_playback/gapfill/GF10_wc_scrub_memory.json` (`configs[*]`: every mark with every GPU pid, the 500 ms GPU samples, `child_process_gone`, per-stream errors with message text, decoder names, `gpu_feature_status_end`; also the target list with its seed).
- Scripts: `scripts/intra_playback/gapfill/GF10/`:
  - `harness/` is a copy of `scripts/chromium_sync_scrub/harness/` with a new test `wcscrub`. The original files were not edited.
  - `run_gf10.py` runs the matrix. `run_gf10_orig.py` re-runs the original scrub loop as a control. `summarize_gf10.py` writes the JSON and the tables.
- Clips: the PyAV 19.0.2 bench clips `c1080p30/{h264_nvenc,hevc_nvenc,h264_qsv}_intra.mp4` under `C:/Users/Dom/Documents/skellycam-raw/.../intra_playback/clips/`. No new clips were made. Each is 600 frames, all IDR, about 55 dB, so NOT at target A or B (`R/clips_summary.json`; intra_playback §1 quality note).
- Versions (in every config's `electron`/`chrome` fields):
  - E35 = Electron 35.7.5 / Chromium 134.0.6998.205;
  - E45 = Electron 45.2.3 / Chromium 156.0.8078.80.
  - Active GPU: NVIDIA 0x10DE:0x2484 (`gpu_device`).

## 1. Method

| item | what was done | evidence |
|---|---|---|
| Target list | 240 targets, seed 20261110, frames 0–599. Runs of 5–20 +1 steps (96 steps), runs of 5–20 −1 steps (138 steps), single random jumps (5). The same list is used for every stream, mode, codec, N and Electron. | code `run_gf10.py:46-71`; JSON `target_list` |
| Drive | `lockstep` (matrix): target j is decoded on all N streams, then j+1. `free` (diagnostics): each stream walks the list on its own, like the original scrub loop. A mark is taken each time the total finished targets reach a multiple of 20·N. | code `harness/harness.mjs:713-742` |
| `reuse` | One `VideoDecoder` per stream, `configure()` once. Per target: Range-fetch that chunk (type `key`), `decode()`, `flush()`. Never `reset()`. | code `harness.mjs:614-634,658-668` |
| `pool` | 3 decoders per stream, each configured once, used round-robin (target j on decoder j mod 3). Flush per target, no reset. Used one at a time, so there is no parallel decode within a stream. | code `harness.mjs:651,663` |
| `baseline` | The unchanged `WcSource` with `flushEach`. It calls `reset()` + `configure()` before every target after the first (`resets_total` = 239 per stream). | code original `harness.mjs:137-152` (`:141` reset, `:147` needKey); JSON `resets_total` |
| Frame handling | Each `VideoFrame` is drawn to the stream's 1920×1080 canvas. Its burned-in 16-bit index is read with `readIndex` (a 64×1 `getImageData`, i.e. a GPU→CPU readback), then the frame is closed in a `finally`. `readevery=M` reads only every M-th target; `0` means never. | code `harness.mjs:676-683`; original `readIndex` `:42-56` |
| Exactness | Read index == target. Counted per stream over the checked targets. | JSON `exact_per_stream`, `checked_per_stream` |
| Errors | Every failed target is counted, with its message text (digits normalised). Recovery in all modes: if the decoder is closed or a flush hangs for 5 s, the decoder (or the `WcSource`) is rebuilt and configured again, and `rebuilds` counts it. The original bench loop had no recovery. | code `harness.mjs:664-675`; original `:502` |
| Memory | Electron main samples `app.getAppMetrics()` on request (`GET /metrics/mark-<label>`) and keeps `memory.privateBytes` as `private_kb`. Raw unit, the harness's own field. Marks are taken before decoders exist (`baseline_before_decoders`), after configure, at targets 20, 40, …, 240, after close, and 3 s after close. A 500 ms sampler runs as well, for a supplementary peak only. | code `harness/main.cjs:71,75-86` |
| GPU replacements | Distinct GPU pids over all samples, minus 1. Electron `child-process-gone` events are also kept, with reason and exit code. | code `main.cjs:157`; JSON `gpu_pids`, `child_process_gone` |
| Isolation | One Electron launch per config, run one after another, with switches `--noocclusion=1 --medialog=1`. The control used `--medialog=0`, as the original bench did. CPU fields are dropped from the saved JSON. | code `run_gf10.py:74-97` |
| Safety cap | A config would stop if a mark showed GPU `private_kb` above 25,000,000 (16,000,000 in the diagnostics). No config hit the cap. | JSON `aborted_at_count` = null everywhere |

Unit: source, Electron MemoryInfo: "Note that all statistics are reported in Kilobytes." (https://www.electronjs.org/docs/latest/api/structures/memory-info, accessed 2026-11-10, as quoted in intra_playback FINDINGS line 124). Whether that means 1000 or 1024 bytes is NOT VERIFIED. Values below are raw `private_kb`.

## 2. Matrix (lockstep, index read on every target): mode × codec × N × Electron

All 240 targets were checked on every stream. "exact" = frames whose read index equals the target. Peak and final are taken from the fixed-count marks, final = the mark at target 240. "baseline" = before any decoder existed. Decoder names come from the DevTools Media log. "None" means that player reported no decoder name; the log is rate-limited ("Log rate exceeds 512 messages per second", in `media_players_at_end`), so names are incomplete.

| mode | codec | N | Electron | errors | rebuilds | exact | peak private_kb (marks) | final run mark | after close +3 s | baseline | GPU repl. | decoders (media log) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| reuse | h264_nvenc | 1 | 35 | 0 | 0 | 240/240 checked | 326,892 | 300,764 | 280,856 | 76,960 | 0 (gone 0) | D3D11VideoDecoder ×1 |
| reuse | h264_nvenc | 1 | 45 | 0 | 0 | 240/240 checked | 324,224 | 282,364 | 282,244 | 76,520 | 0 (gone 0) | D3D11VideoDecoder ×1 |
| reuse | h264_nvenc | 4 | 35 | 0 | 0 | 960/960 checked | 492,936 | 492,936 | 451,076 | 77,692 | 0 (gone 0) | D3D11VideoDecoder ×3, None ×1 |
| reuse | h264_nvenc | 4 | 45 | 0 | 0 | 960/960 checked | 472,360 | 459,408 | 386,820 | 75,948 | 0 (gone 0) | D3D11VideoDecoder ×2, None ×2 |
| reuse | h264_nvenc | 8 | 35 | 0 | 0 | 1920/1920 checked | 872,556 | 799,704 | 517,992 | 78,000 | 0 (gone 0) | D3D11VideoDecoder ×7, None ×1 |
| reuse | h264_nvenc | 8 | 45 | 0 | 0 | 1920/1920 checked | 686,920 | 660,268 | 516,472 | 76,208 | 0 (gone 0) | D3D11VideoDecoder ×7, None ×1 |
| reuse | hevc_nvenc | 1 | 35 | 0 | 0 | 240/240 checked | 331,204 | 302,404 | 290,092 | 76,036 | 0 (gone 0) | D3D11VideoDecoder ×1 |
| reuse | hevc_nvenc | 1 | 45 | 0 | 0 | 240/240 checked | 326,940 | 290,064 | 274,340 | 74,880 | 0 (gone 0) | D3D11VideoDecoder ×1 |
| reuse | hevc_nvenc | 4 | 35 | 0 | 0 | 960/960 checked | 511,788 | 465,728 | 375,304 | 77,528 | 0 (gone 0) | D3D11VideoDecoder ×3, None ×1 |
| reuse | hevc_nvenc | 4 | 45 | 0 | 0 | 960/960 checked | 560,312 | 560,312 | 392,188 | 75,460 | 0 (gone 0) | D3D11VideoDecoder ×2, None ×2 |
| reuse | hevc_nvenc | 8 | 35 | 0 | 0 | 1920/1920 checked | 813,968 | 702,164 | 540,952 | 77,560 | 0 (gone 0) | D3D11VideoDecoder ×5, None ×3 |
| reuse | hevc_nvenc | 8 | 45 | 0 | 0 | 1920/1920 checked | 792,100 | 780,900 | 519,412 | 75,940 | 0 (gone 0) | D3D11VideoDecoder ×6, None ×2 |
| reuse | h264_qsv | 1 | 35 | 0 | 0 | 240/240 checked | 325,024 | 302,828 | 282,996 | 77,544 | 0 (gone 0) | D3D11VideoDecoder ×1 |
| reuse | h264_qsv | 1 | 45 | 0 | 0 | 240/240 checked | 326,236 | 299,920 | 279,980 | 75,000 | 0 (gone 0) | D3D11VideoDecoder ×1 |
| reuse | h264_qsv | 4 | 35 | 0 | 0 | 960/960 checked | 481,272 | 474,184 | 398,804 | 76,752 | 0 (gone 0) | D3D11VideoDecoder ×2, None ×2 |
| reuse | h264_qsv | 4 | 45 | 0 | 0 | 960/960 checked | 486,424 | 455,248 | 377,916 | 75,880 | 0 (gone 0) | D3D11VideoDecoder ×3, None ×1 |
| reuse | h264_qsv | 8 | 35 | 0 | 0 | 1920/1920 checked | 832,612 | 624,884 | 495,744 | 76,316 | 0 (gone 0) | D3D11VideoDecoder ×7, None ×1 |
| reuse | h264_qsv | 8 | 45 | 0 | 0 | 1920/1920 checked | 671,480 | 657,920 | 514,340 | 76,452 | 0 (gone 0) | D3D11VideoDecoder ×7, None ×1 |
| pool | h264_nvenc | 1 | 35 | 0 | 0 | 240/240 checked | 332,324 | 312,008 | 286,408 | 77,000 | 0 (gone 0) | D3D11VideoDecoder ×3 |
| pool | h264_nvenc | 1 | 45 | 0 | 0 | 240/240 checked | 329,184 | 303,656 | 277,952 | 74,988 | 0 (gone 0) | D3D11VideoDecoder ×2, None ×1 |
| pool | h264_nvenc | 4 | 35 | 0 | 0 | 960/960 checked | 506,240 | 484,644 | 424,148 | 77,724 | 0 (gone 0) | D3D11VideoDecoder ×7, None ×5 |
| pool | h264_nvenc | 4 | 45 | 0 | 0 | 960/960 checked | 518,604 | 487,788 | 392,888 | 75,976 | 0 (gone 0) | D3D11VideoDecoder ×10, None ×2 |
| pool | h264_nvenc | 8 | 35 | 0 | 0 | 1920/1920 checked | 795,992 | 607,708 | 501,376 | 76,680 | 0 (gone 0) | D3D11VideoDecoder ×18, None ×6 |
| pool | h264_nvenc | 8 | 45 | 0 | 0 | 1920/1920 checked | 739,416 | 739,416 | 517,332 | 74,700 | 0 (gone 0) | D3D11VideoDecoder ×16, None ×8 |
| pool | hevc_nvenc | 1 | 35 | 0 | 0 | 240/240 checked | 333,124 | 306,120 | 290,612 | 77,844 | 0 (gone 0) | D3D11VideoDecoder ×3 |
| pool | hevc_nvenc | 1 | 45 | 0 | 0 | 240/240 checked | 332,760 | 299,312 | 277,484 | 75,424 | 0 (gone 0) | D3D11VideoDecoder ×2, None ×1 |
| pool | hevc_nvenc | 4 | 35 | 0 | 0 | 960/960 checked | 541,496 | 535,560 | 374,336 | 76,484 | 0 (gone 0) | D3D11VideoDecoder ×8, None ×4 |
| pool | hevc_nvenc | 4 | 45 | 0 | 0 | 960/960 checked | 565,420 | 503,120 | 493,104 | 76,252 | 0 (gone 0) | D3D11VideoDecoder ×9, None ×3 |
| pool | hevc_nvenc | 8 | 35 | 0 | 0 | 1920/1920 checked | 877,772 | 858,716 | 526,572 | 75,900 | 0 (gone 0) | D3D11VideoDecoder ×20, None ×4 |
| pool | hevc_nvenc | 8 | 45 | 0 | 0 | 1920/1920 checked | 895,968 | 895,968 | 516,664 | 75,244 | 0 (gone 0) | D3D11VideoDecoder ×16, None ×8 |
| pool | h264_qsv | 1 | 35 | 0 | 0 | 240/240 checked | 342,924 | 317,364 | 294,576 | 77,760 | 0 (gone 0) | D3D11VideoDecoder ×2, None ×1 |
| pool | h264_qsv | 1 | 45 | 0 | 0 | 240/240 checked | 325,996 | 303,460 | 280,672 | 74,132 | 0 (gone 0) | D3D11VideoDecoder ×3 |
| pool | h264_qsv | 4 | 35 | 0 | 0 | 960/960 checked | 510,896 | 510,896 | 431,632 | 76,776 | 0 (gone 0) | D3D11VideoDecoder ×6, None ×6 |
| pool | h264_qsv | 4 | 45 | 0 | 0 | 960/960 checked | 503,776 | 493,752 | 375,380 | 75,172 | 0 (gone 0) | D3D11VideoDecoder ×8, None ×4 |
| pool | h264_qsv | 8 | 35 | 0 | 0 | 1920/1920 checked | 870,436 | 778,932 | 568,692 | 77,036 | 0 (gone 0) | D3D11VideoDecoder ×18, None ×6 |
| pool | h264_qsv | 8 | 45 | 0 | 0 | 1920/1920 checked | 733,204 | 733,204 | 517,988 | 75,080 | 0 (gone 0) | D3D11VideoDecoder ×16, None ×8 |
| baseline | h264_nvenc | 1 | 35 | 0 | 0 | 240/240 checked | 325,900 | 303,916 | 284,268 | 77,148 | 0 (gone 0) | D3D11VideoDecoder ×1 |
| baseline | h264_nvenc | 1 | 45 | 0 | 0 | 240/240 checked | 329,644 | 296,352 | 276,224 | 74,952 | 0 (gone 0) | D3D11VideoDecoder ×1 |
| baseline | h264_nvenc | 4 | 35 | 0 | 0 | 960/960 checked | 490,400 | 456,344 | 375,840 | 76,804 | 0 (gone 0) | D3D11VideoDecoder ×2, None ×2 |
| baseline | h264_nvenc | 4 | 45 | 0 | 0 | 960/960 checked | 487,272 | 485,172 | 395,604 | 75,676 | 0 (gone 0) | D3D11VideoDecoder ×3, None ×1 |
| baseline | hevc_nvenc | 1 | 35 | 0 | 0 | 240/240 checked | 325,604 | 301,824 | 287,736 | 77,188 | 0 (gone 0) | D3D11VideoDecoder ×1 |
| baseline | hevc_nvenc | 1 | 45 | 0 | 0 | 240/240 checked | 337,600 | 300,692 | 284,912 | 76,132 | 0 (gone 0) | D3D11VideoDecoder ×1 |
| baseline | hevc_nvenc | 4 | 35 | 0 | 0 | 960/960 checked | 529,404 | 529,404 | 386,224 | 77,664 | 0 (gone 0) | D3D11VideoDecoder ×3, None ×1 |
| baseline | hevc_nvenc | 4 | 45 | 0 | 0 | 960/960 checked | 525,288 | 474,964 | 382,816 | 76,024 | 0 (gone 0) | D3D11VideoDecoder ×4 |
| baseline | h264_qsv | 1 | 35 | 0 | 0 | 240/240 checked | 325,080 | 301,776 | 293,044 | 76,456 | 0 (gone 0) | D3D11VideoDecoder ×1 |
| baseline | h264_qsv | 1 | 45 | 0 | 0 | 240/240 checked | 332,920 | 295,520 | 279,924 | 76,348 | 0 (gone 0) | D3D11VideoDecoder ×1 |
| baseline | h264_qsv | 4 | 35 | 0 | 0 | 960/960 checked | 502,256 | 474,292 | 405,212 | 76,772 | 0 (gone 0) | D3D11VideoDecoder ×4 |
| baseline | h264_qsv | 4 | 45 | 0 | 0 | 960/960 checked | 483,372 | 478,040 | 382,048 | 75,216 | 0 (gone 0) | D3D11VideoDecoder ×3, None ×1 |

## 3. Diagnostics: free-running drive, readback frequency, and the original scrub loop as a control

Rows without a suffix in §2 are `lockstep` with `readevery=1`. Suffixes: `_free` = free drive, `_re0` = never read the index, `_re20` = read on every 20th target only. `origscrub` = the original bench page logic (`harness.mjs:461-515`, path `webcodecs`, `wcflush=1`, 8 s triangle drag at 90 frames/s, run without `bench=1`). It has no fixed target list, no recovery and no readback, and only its 500 ms sampler. Its rate fields were dropped. "gone" = Electron `child-process-gone` events. All of them were `type GPU, reason crashed, exitCode 34` (JSON `child_process_gone`).

| mode | codec | N | Electron | errors | rebuilds | exact | peak private_kb (marks) | final run mark | after close +3 s | baseline | GPU repl. | decoders (media log) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| origscrub (control) | h264_nvenc | 4 | 35 | 1479 | none (no recovery) | not read | 500,872 (500 ms sampler) | | | | 1 (gone 1) | |
| origscrub (control) | h264_nvenc | 4 | 45 | 3388 | none (no recovery) | not read | 507,472 (500 ms sampler) | | | | 1 (gone 1) | |
| origscrub (control) | h264_nvenc | 8 | 35 | 6555 | none (no recovery) | not read | 699,696 (500 ms sampler) | | | | 1 (gone 1) | |
| origscrub (control) | h264_nvenc | 8 | 45 | 5190 | none (no recovery) | not read | 728,788 (500 ms sampler) | | | | 1 (gone 1) | |
| origscrub (control) | hevc_nvenc | 4 | 35 | 4280 | none (no recovery) | not read | 562,992 (500 ms sampler) | | | | 1 (gone 1) | |
| origscrub (control) | hevc_nvenc | 4 | 45 | 4484 | none (no recovery) | not read | 544,240 (500 ms sampler) | | | | 1 (gone 1) | |
| origscrub (control) | hevc_nvenc | 8 | 35 | 7962 | none (no recovery) | not read | 902,728 (500 ms sampler) | | | | 1 (gone 1) | |
| origscrub (control) | hevc_nvenc | 8 | 45 | 8378 | none (no recovery) | not read | 801,404 (500 ms sampler) | | | | 1 (gone 1) | |
| origscrub (control) | h264_qsv | 4 | 35 | 3408 | none (no recovery) | not read | 499,448 (500 ms sampler) | | | | 1 (gone 1) | |
| origscrub (control) | h264_qsv | 4 | 45 | 3198 | none (no recovery) | not read | 518,588 (500 ms sampler) | | | | 1 (gone 1) | |
| origscrub (control) | h264_qsv | 8 | 35 | 3261 | none (no recovery) | not read | 688,404 (500 ms sampler) | | | | 1 (gone 1) | |
| origscrub (control) | h264_qsv | 8 | 45 | 5103 | none (no recovery) | not read | 789,232 (500 ms sampler) | | | | 1 (gone 1) | |
| reuse_free | h264_nvenc | 8 | 35 | 0 | 0 | 1920/1920 checked | 834,536 | 773,060 | 520,344 | 77,244 | 0 (gone 0) | D3D11VideoDecoder ×7, None ×1 |
| reuse_free | h264_nvenc | 8 | 45 | 0 | 0 | 1920/1920 checked | 684,064 | 620,328 | 516,580 | 74,536 | 0 (gone 0) | D3D11VideoDecoder ×5, None ×3 |
| reuse_free | hevc_nvenc | 8 | 35 | 0 | 0 | 1920/1920 checked | 811,676 | 734,920 | 518,348 | 77,308 | 0 (gone 0) | D3D11VideoDecoder ×6, None ×2 |
| reuse_free | hevc_nvenc | 8 | 45 | 0 | 0 | 1920/1920 checked | 837,420 | 661,200 | 513,508 | 75,616 | 0 (gone 0) | D3D11VideoDecoder ×5, None ×3 |
| reuse_free | h264_qsv | 8 | 35 | 0 | 0 | 1920/1920 checked | 808,756 | 779,896 | 515,004 | 76,064 | 0 (gone 0) | D3D11VideoDecoder ×6, None ×2 |
| reuse_free | h264_qsv | 8 | 45 | 0 | 0 | 1920/1920 checked | 672,868 | 603,620 | 509,996 | 74,308 | 0 (gone 0) | D3D11VideoDecoder ×6, None ×2 |
| reuse_free_re0 | h264_nvenc | 4 | 35 | 8 | 8 | not read (readevery=0) | 1,056,884 | 570,436 | 414,888 | 77,520 | 2 (gone 2) | D3D11VideoDecoder ×7, None ×5 |
| reuse_free_re0 | h264_nvenc | 4 | 45 | 1 | 1 | not read (readevery=0) | 505,944 | 505,944 | 466,312 | 75,148 | 1 (gone 1) | D3D11VideoDecoder ×4, None ×1 |
| reuse_free_re0 | h264_nvenc | 8 | 35 | 5 | 5 | not read (readevery=0) | 981,448 | 970,560 | 840,764 | 77,444 | 1 (gone 1) | D3D11VideoDecoder ×3, None ×10 |
| reuse_free_re0 | h264_nvenc | 8 | 45 | 6 | 6 | not read (readevery=0) | 1,131,040 | 1,025,452 | 910,400 | 74,864 | 1 (gone 1) | D3D11VideoDecoder ×7, None ×7 |
| reuse_free_re0 | hevc_nvenc | 4 | 35 | 4 | 4 | not read (readevery=0) | 592,276 | 528,456 | 517,400 | 77,788 | 1 (gone 1) | D3D11VideoDecoder ×6, None ×2 |
| reuse_free_re0 | hevc_nvenc | 4 | 45 | 199 | 199 | not read (readevery=0) | 613,684 | 18,312 | 18,320 | 75,056 | 3 (gone 3, video_decode disabled_software) | D3D11VideoDecoder ×8, None ×195 |
| reuse_free_re0 | hevc_nvenc | 8 | 35 | 1180 | 1180 | not read (readevery=0) | 806,672 | 22,960 | 22,960 | 76,584 | 3 (gone 3, video_decode disabled_software) | D3D11VideoDecoder ×8, None ×1180 |
| reuse_free_re0 | hevc_nvenc | 8 | 45 | 1378 | 1378 | not read (readevery=0) | 755,044 | 18,728 | 18,728 | 74,528 | 3 (gone 3, video_decode disabled_software) | D3D11VideoDecoder ×9, None ×1377 |
| reuse_free_re0 | h264_qsv | 4 | 35 | 4 | 4 | not read (readevery=0) | 623,840 | 623,840 | 447,528 | 76,808 | 1 (gone 1) | D3D11VideoDecoder ×3, None ×5 |
| reuse_free_re0 | h264_qsv | 4 | 45 | 0 | 0 | not read (readevery=0) | 483,072 | 455,848 | 424,012 | 75,208 | 0 (gone 0) | D3D11VideoDecoder ×3, None ×1 |
| reuse_free_re0 | h264_qsv | 8 | 35 | 6 | 6 | not read (readevery=0) | 987,488 | 979,928 | 834,120 | 76,480 | 1 (gone 1) | D3D11VideoDecoder ×7, None ×6, FFmpegVideoDecoder ×1 |
| reuse_free_re0 | h264_qsv | 8 | 45 | 0 | 0 | not read (readevery=0) | 802,764 | 639,436 | 639,436 | 74,756 | 1 (gone 1) | D3D11VideoDecoder ×5, None ×3 |
| reuse_free_re20 | h264_nvenc | 8 | 35 | 0 | 0 | 96/96 checked (of 1920 targets) | 827,436 | 769,252 | 599,372 | 76,460 | 0 (gone 0) | D3D11VideoDecoder ×5, None ×3 |
| reuse_free_re20 | h264_nvenc | 8 | 45 | 0 | 0 | 96/96 checked (of 1920 targets) | 745,536 | 701,860 | 598,880 | 75,124 | 0 (gone 0) | D3D11VideoDecoder ×2, None ×6 |
| reuse_free_re20 | hevc_nvenc | 8 | 35 | 0 | 0 | 96/96 checked (of 1920 targets) | 967,496 | 964,672 | 578,504 | 77,484 | 0 (gone 0) | D3D11VideoDecoder ×3, None ×5 |
| reuse_free_re20 | hevc_nvenc | 8 | 45 | 0 | 0 | 96/96 checked (of 1920 targets) | 849,564 | 774,020 | 496,236 | 74,968 | 0 (gone 0) | D3D11VideoDecoder ×5, None ×3 |
| reuse_free_re20 | h264_qsv | 8 | 35 | 0 | 0 | 96/96 checked (of 1920 targets) | 780,808 | 739,424 | 611,172 | 76,544 | 0 (gone 0) | D3D11VideoDecoder ×3, None ×5 |
| reuse_free_re20 | h264_qsv | 8 | 45 | 0 | 0 | 96/96 checked (of 1920 targets) | 776,628 | 700,208 | 598,724 | 74,776 | 0 (gone 0) | D3D11VideoDecoder ×2, None ×6 |
| reuse_re0 | h264_nvenc | 8 | 35 | 0 | 0 | not read (readevery=0) | 1,218,340 | 734,120 | 546,480 | 76,568 | 0 (gone 0) | D3D11VideoDecoder ×5, None ×3 |
| reuse_re0 | h264_nvenc | 8 | 45 | 24 | 24 | not read (readevery=0) | 888,868 | 18,888 | 18,888 | 75,348 | 3 (gone 3, video_decode disabled_software) | D3D11VideoDecoder ×9, None ×16, FFmpegVideoDecoder ×7 |
| reuse_re0 | hevc_nvenc | 8 | 35 | 8 | 8 | not read (readevery=0) | 2,240,188 | 975,700 | 577,428 | 77,264 | 1 (gone 1) | D3D11VideoDecoder ×7, None ×9 |
| reuse_re0 | hevc_nvenc | 8 | 45 | 0 | 0 | not read (readevery=0) | 1,502,624 | 1,116,804 | 531,760 | 75,532 | 0 (gone 0) | D3D11VideoDecoder ×3, None ×5 |
| reuse_re0 | h264_qsv | 8 | 35 | 24 | 24 | not read (readevery=0) | 926,404 | 21,884 | 22,116 | 75,848 | 3 (gone 3, video_decode disabled_software) | D3D11VideoDecoder ×10, None ×21, FFmpegVideoDecoder ×1 |
| reuse_re0 | h264_qsv | 8 | 45 | 24 | 24 | not read (readevery=0) | 770,232 | 18,968 | 18,968 | 76,156 | 3 (gone 3, video_decode disabled_software) | D3D11VideoDecoder ×11, None ×17, FFmpegVideoDecoder ×4 |
| pool_free_re0 | h264_nvenc | 8 | 35 | 46 | 46 | not read (readevery=0) | 1,366,256 | 1,322,872 | 957,156 | 76,884 | 2 (gone 2) | D3D11VideoDecoder ×14, None ×56 |
| pool_free_re0 | h264_nvenc | 8 | 45 | 17 | 17 | not read (readevery=0) | 1,110,744 | 1,042,044 | 898,136 | 75,664 | 1 (gone 1) | D3D11VideoDecoder ×18, None ×22, FFmpegVideoDecoder ×1 |
| baseline_free | h264_nvenc | 4 | 35 | 0 | 0 | 960/960 checked | 475,720 | 475,720 | 453,980 | 76,400 | 0 (gone 0) | D3D11VideoDecoder ×3, None ×1 |
| baseline_free | h264_nvenc | 4 | 45 | 0 | 0 | 960/960 checked | 507,292 | 493,012 | 412,024 | 76,556 | 0 (gone 0) | D3D11VideoDecoder ×3, None ×1 |
| baseline_free | h264_nvenc | 8 | 35 | 0 | 0 | 1920/1920 checked | 843,292 | 807,560 | 505,548 | 76,840 | 0 (gone 0) | D3D11VideoDecoder ×4, None ×4 |
| baseline_free | h264_nvenc | 8 | 45 | 0 | 0 | 1920/1920 checked | 697,512 | 567,000 | 519,056 | 74,920 | 0 (gone 0) | D3D11VideoDecoder ×2, None ×6 |
| baseline_free_re0 | h264_nvenc | 4 | 35 | 3 | 3 | not read (readevery=0) | 824,456 | 824,456 | 723,056 | 76,748 | 1 (gone 1) | D3D11VideoDecoder ×5, None ×2 |
| baseline_free_re0 | h264_nvenc | 4 | 45 | 2 | 2 | not read (readevery=0) | 752,036 | 752,036 | 735,768 | 75,400 | 1 (gone 1) | D3D11VideoDecoder ×2, None ×3, FFmpegVideoDecoder ×1 |
| baseline_free_re0 | h264_nvenc | 8 | 35 | 3 | 3 | not read (readevery=0) | 854,148 | 833,960 | 778,944 | 77,544 | 1 (gone 1) | D3D11VideoDecoder ×7, FFmpegVideoDecoder ×1, None ×3 |
| baseline_free_re0 | h264_nvenc | 8 | 45 | 7 | 7 | not read (readevery=0) | 1,120,864 | 1,101,120 | 1,013,484 | 75,016 | 1 (gone 1) | D3D11VideoDecoder ×5, None ×10 |

## 4. Results (labelled)

Source for every "measured" bullet: `results/intra_playback/gapfill/GF10_wc_scrub_memory.json`, `configs[*]` (keys named in each bullet).

**Configure-once and pool patterns, read on every target (the requested matrix)**
- measured: **`reuse` and `pool` were error-free and frame-exact in all 36 configs** (3 codecs × N = 1/4/8 × E35/E45). That is 0 errors, 0 rebuilds, 0 wrong and 0 unreadable frames, and 240/240 exact on every stream (`errors_total`, `rebuilds_total`, `exact_per_stream`).
- measured: **their GPU-process memory stayed bounded.** Peak `private_kb` over the fixed-count marks (`gpu_private_kb_peak_marks`):
  - N = 1: 324,224–342,924;
  - N = 4: 472,360–565,420;
  - N = 8: 671,480–895,968.
  - The value at target 240 was at or below the peak in every config. 3 s after close it fell to 274,340–568,692 (`gpu_private_kb_after_close_settle3s`).
  - Before any decoder existed it was 74,132–78,000 in every config (`gpu_private_kb_baseline`).
  - The 500 ms sampler's highest value in any config that read frames back was 1,002,132 (`gpu_private_kb_peak_bg500ms`).
- measured: **no rising trend.** From the first marks (targets 20–60) to the last marks (200–240), reuse and pool at N = 8 moved within one band (e.g. E35 `reuse` `h264_nvenc` N = 8: 641,424–872,556 over all 12 run marks; the highest was at target 20) (`marks`).
- measured: **0 GPU-process replacements and 0 `child-process-gone` events** in these 36 configs (`gpu_replacements`, `child_process_gone`).
- measured: **`pool` gave no memory or error advantage over `reuse`.** Peak ranges overlap at every N (above). `pool` creates 3× the decoders: up to 24 players at N = 8 in the media log (`decoder_names_media_log`).
- measured: every player that reported a decoder name reported `D3D11VideoDecoder` (hardware) in the readback configs. The names are incomplete (see §2 note).

**Per-target reset (`baseline`), read on every target**
- measured: **with the index read on every target, the per-target `reset()` + `configure()` + `flush()` pattern was also error-free, exact and bounded.**
  - Lockstep, 12 configs (3 codecs × N = 1/4 × 2 Electrons): 0 errors, 240/240 exact per stream, peak 325,080–529,404, 0 replacements.
  - Free drive, h264_nvenc N = 4/8, 4 configs: 0 errors, exact, peak 475,720–843,292, 0 replacements.
  - `resets_total` is 239 per stream.
- inferred: **so `reset()` per target is not, on its own, what caused F22.** On these runs the protective factor was the readback (next block), not the reset.

**What breaks it: no GPU→CPU sync per target**
- measured: **with `readevery=0` (frames drawn to canvas and closed, never read back), the GPU process crashed in 21 of 24 configs**, for every mode tested (`reuse`, `pool`, `baseline`), both drives and both Electrons. That was 35 crashes in total, all `exitCode 34` (`child_process_gone`).
  - Errors in those configs: 0–1,378 per config, 2,949 in total (`errors_total`).
  - Messages (summed): "InvalidStateError: … Cannot call 'decode' on a closed codec." 2,698; "EncodingError: Decoding error." 214; "OperationError: Error during initialize after flush." 23; "no output … after flush (decoder state closed, err EncodingError: …)" 14 (`errors_by_message`).
- measured: **after 3 GPU crashes in one launch (6 configs), Chromium ended with `video_decode: disabled_software` and `gpu_compositing: disabled_software`**, and GPU `private_kb` dropped to 18,312–22,960 (`gpu_feature_status_end`, `gpu_private_kb_final_run`).
  - HEVC then failed on every remaining target: 1,180 (E35) and 1,378 (E45) errors at N = 8, and 199 at N = 4 (E45).
  - H.264 partly continued on `FFmpegVideoDecoder` (software), which appears in `decoder_names_media_log` only in crash configs.
  - This matches intra_playback F10 (no HEVC software decode).
- measured: **reading the index on only every 20th target was enough in these runs.** `reuse_free_re20`, N = 8, 3 codecs × 2 Electrons: 0 errors, 0 crashes, 96/96 checked frames exact, peak 745,536–967,496.
- measured: **lockstep alone did not protect.** `reuse` lockstep with `readevery=0`, N = 8: 4 of 6 configs crashed (1–3 crashes each), and the peak reached 2,240,188 (E35 hevc_nvenc).
- measured: **the unchanged original scrub loop crashed the GPU process in 12 of 12 configs today** (h264_nvenc, hevc_nvenc, h264_qsv × N = 4/8 × E35/E45; one crash each).
  - Without recovery, each stream that lost its decoder failed every later target: 1,479–8,378 errors per config (`errors_total`).
  - Its peak `private_kb` was only 499,448–902,728 (500 ms sampler).
- measured: **the 9.6–39.7 million `private_kb` growth of the 23:00 bench (F22) was NOT reproduced** in any of the 100 configs today. The highest value in any sample, marks or 500 ms sampler, was 2,280,968.
  - inferred: today's early GPU crashes may cut growth short before it builds up. Why the 23:00 run grew instead of crashing (E45 had 0 errors then) is not determined. The machine was quiet then and shared now.
- inferred (minimal): the 64×1 `getImageData` readback makes the renderer wait for the GPU to finish the draw of that frame. That bounds how much decode and draw work can queue in the GPU process. The mechanism is NOT VERIFIED (no Chromium source checked). The readback also slows the loop, and that effect was not measured (timing rule).
- code: the original scrub loop draws and closes each frame with no readback (`scripts/chromium_sync_scrub/harness/harness.mjs:501`). The original sync path (`wc-master`) has no readback either (`:434-436` with `readpattern` unset). But it decodes at most about 8 frames ahead and draws on rAF (`:326`, `:426-443`). inferred: that is why `wc-master` stayed near 1 million `private_kb` in F22.

**Does a bounded-memory, error-free WebCodecs scrub pattern exist?**
- measured (functional, this machine, NVIDIA D3D11 decode): **yes.** It is: one `VideoDecoder` per stream, configured once, then decode the target's key chunk, `flush()`, draw, and close every frame. Add a GPU→CPU sync point every target, or at least every 20th. With that, 0 errors, 0 GPU crashes and bounded memory held for H.264 NVENC, HEVC NVENC and H.264 QSV intra at N = 1, 4 and 8 in E35 and E45.
- measured: a decoder pool is not needed for memory or errors.
- inferred: the scrub design needs **back-pressure**. Without it, the same decoders crash the GPU process. After 3 crashes HEVC has no decode path left in that launch.
  - Candidate sync points other than `getImageData` (e.g. pacing decodes to `requestAnimationFrame`, or capping in-flight targets per stream) are NOT tested.
- inferred: the player must also recover. A GPU crash closes every decoder in the page, so rebuild and reconfigure on `closed`. Without recovery the original loop turned 1 crash into thousands of errors.

## 5. Limits and NOT VERIFIED

- **No scrub rate, latency, fps or CPU is reported.** Whether the bounded pattern keeps up with a slider drag needs a later quiet-machine run, one item at a time. The readback costs time, and the pool might help throughput; neither was measured.
- Single run per config on a shared machine. Other agents may have used the GPU. The crash counts are not repeat-tested, and their rate on a quiet machine is NOT VERIFIED.
- `h264_nvenc` / `hevc_nvenc` / `h264_qsv` only. `hevc_qsv`, JPEG and other clips were not in this matrix. 1080p30 CFR MP4 only.
- The target list has only 5 random jumps among 239 moves. inferred: this does not matter for these modes, because every chunk is an IDR and every target is decoded on its own (one chunk per target; `harness.mjs:663`, and baseline resets every target).
- NVIDIA D3D11 decode only. Intel/AMD/Apple decode, other OSes and machines without HEVC hardware: NOT VERIFIED.
- What exit code 34 means: NOT VERIFIED.
- Unit of `private_kb` (1000 vs 1024): NOT VERIFIED.
- The media-log decoder names are incomplete (rate-limited).
- Not tested: a sync point other than `getImageData`; rAF-paced scrub; GPU memory reported by nvidia-smi.

## 6. Proposed replacement text for intra_playback FINDINGS

Old text is quoted from `results/intra_playback/FINDINGS.md` as of 2026-11-10 09:28.

**F22, lines 115 and 128.**
- Old line 115: "- **F22** measured: **WebCodecs scrub has hidden errors, and GPU-process memory grows.**"
- Old line 128: "- inferred: the harness's per-target `reset()` + `configure()` + `flush()` cycle triggers the growth (code: `harness.mjs:137-152`), because the no-reset `wc-master` path stays near 1 GiB. Frames are closed after drawing (code: `harness.mjs:501`). So these scrub rates measure this harness pattern, not WebCodecs decode capacity."
- Proposed line 115: "- **F22** measured: **the bench's WebCodecs scrub loop has hidden errors and GPU-process failures; a configure-once scrub with a per-target GPU sync is error-free and bounded (GF10).**"
- Proposed replacement for line 128:
  - "- measured (GF10, functional, 2026-11-10): the per-target reset is not the cause. With the frame index read back (`getImageData`) on every target, `baseline` (this reset pattern), `reuse` (configure once, flush per target, no reset) and `pool` (3 decoders round-robin) were all error-free, with every checked frame exact and 0 GPU replacements. This held in 64 configs (H.264 NVENC, HEVC NVENC, H.264 QSV; N = 1/4/8; E35/E45). 58 of them read every target (240/240 per stream) and 6 read every 20th (12/12 per stream). GPU `private_kb` peaked at 324,224–967,496 at the fixed-count marks (1,002,132 in the 500 ms sampler) (`results/intra_playback/gapfill/GF10_wc_scrub_memory.json`)."
  - "- measured (GF10): without any GPU→CPU readback, the GPU process crashed (exit code 34) in 21 of 24 configs of every mode, and in 12 of 12 re-runs of this bench's own scrub loop. After 3 crashes in one launch, `video_decode` became `disabled_software` and HEVC failed on every later target. The 9.6–39.7 million `private_kb` growth was not reproduced today (max 2,280,968 in any sample)."
  - "- code: the bench scrub loop draws and closes each frame with no readback (`harness.mjs:501`). So these scrub rates measure an unsynchronised loop, not WebCodecs decode capacity."
- Keep lines 116–127 as the record of the 23:00 run.

**P7, lines 221–222.**
- Old line 221: "- **P7 (F22) inferred: a WebCodecs scrub design must be benchmarked before it is chosen.** The tested per-target `reset/configure/flush` pattern grew GPU-process `private_kb` to 9,586,248–39,695,312 (9.14–37.86 GiB if KiB) in 8 s, and in 3 E35 configs the GPU process was replaced (new pid)."
- Old line 222: "  - So no WebCodecs scrub capacity figure is available yet. The seek and sync numbers (F18–F20) stand."
- Proposed:
  - "- **P7 (F22, GF10) inferred: a WebCodecs scrub for H.264/HEVC intra should configure one `VideoDecoder` per stream once, decode only the target's key chunk, `flush()`, close every frame, and keep a GPU sync point (back-pressure) every target or every few targets. It must also rebuild decoders after a GPU-process crash.** measured basis: this pattern was error-free with bounded GPU memory at N = 1/4/8 in E35 and E45 (functional, GF10). Without a sync point the GPU process crashed, and after 3 crashes HEVC had no decode path. A decoder pool brought no benefit."
  - "  - No WebCodecs scrub rate or latency is available yet. It needs a quiet-machine run of this pattern. The seek and sync numbers (F18–F20) stand."

**§6, lines 272–275.**
- Old: "- Not measured:" / "  - a sequential WebCodecs scrub without a per-target reset;" / "  - a WebCodecs scrub that bounds GPU memory;" / "  - CPU cost of software H.264 decode in the sync or scrub pattern."
- Proposed:
  - "- Not measured:"
  - "  - scrub rate, latency and CPU of the bounded configure-once pattern (GF10 was functional only, on a shared machine);"
  - "  - a back-pressure method other than a per-target or every-20th `getImageData` readback (e.g. rAF pacing);"
  - "  - why the 23:00 bench grew GPU memory to 9.6–39.7 million `private_kb` while today's runs crashed early instead (GF10, not reproduced);"
  - "  - CPU cost of software H.264 decode in the sync or scrub pattern."
- Also add to §6: "- NOT VERIFIED: the meaning of Chromium GPU exit code 34, and the GPU-crash rate of unsynchronised scrub on a quiet machine (GF10, single runs on a shared machine)."
