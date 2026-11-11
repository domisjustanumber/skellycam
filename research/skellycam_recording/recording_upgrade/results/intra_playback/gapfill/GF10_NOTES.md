# GF10 notes: WebCodecs scrub with bounded GPU memory (functional)

Date 2026-11-10, Gerald, on a shared machine (other study agents running). **No rate, latency, fps or CPU was recorded.** Full write-up: `GF10_wc_scrub_memory.md`. Raw data: `GF10_wc_scrub_memory.json`.

## Answer
- measured: a configure-once WebCodecs scrub is error-free and keeps GPU-process memory bounded, if each target (or at least every 20th) ends with a GPU→CPU readback. The pattern is: one decoder per stream, decode the target's key chunk, `flush()`, draw, close. Tested on H.264 NVENC, HEVC NVENC and H.264 QSV intra, N = 1/4/8, E35 and E45: 64 configs, 0 errors, 0 GPU crashes, peak `private_kb` 324,224–967,496.
- measured: the per-target `reset()` pattern behaves the same when synced. So F22's "reset causes the growth" inference does not hold.
- measured: without a sync point the GPU process crashes (exit code 34) in 21/24 configs of every mode. The unchanged bench scrub loop crashed in 12/12. After 3 crashes `video_decode` becomes `disabled_software`, and HEVC fails from then on.
- measured: F22's 9.6–39.7 million `private_kb` growth was not reproduced (max 2,280,968).
- measured: a decoder pool (3 per stream) brings no memory or error benefit.

## Files
- Scripts: `scripts/intra_playback/gapfill/GF10/`:
  - `harness/` is a copy of `scripts/chromium_sync_scrub/harness/`, adding test `wcscrub`, on-demand memory marks, `child-process-gone` capture, and its own userData in the step3 temp folder. The original harness was not edited.
  - `run_gf10.py` (options `--drive lockstep|free`, `--readevery M`, `--cap`), `run_gf10_orig.py` (control) and `summarize_gf10.py`.
- Raw per-config JSON and Electron logs are in the temp folder `.../scratchpad/step3/GF10/raw/{smoke,main,diag,orig}/`. They are merged into `GF10_wc_scrub_memory.json`.
- Run order (sequential, one Electron at a time):
  - `main`: the 48-config matrix; baseline cut to N = 1/4, which the task allows;
  - `diag`: free drive, `readevery` 0 and 20, `pool_free_re0`;
  - `orig`: 12 control configs.

## Reproduce (repo root)
```
uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_playback/gapfill/GF10/run_gf10.py --tag main
uv run --script .../GF10/run_gf10.py --tag diag --cap 16000000 --modes baseline --baseline-ns 4,8 --codecs h264_nvenc --drive free --readevery 0
uv run --script .../GF10/run_gf10.py --tag diag --cap 16000000 --modes baseline --baseline-ns 4,8 --codecs h264_nvenc --drive free --readevery 1
uv run --script .../GF10/run_gf10.py --tag diag --cap 16000000 --modes reuse --ns 4,8 --drive free --readevery 0
uv run --script .../GF10/run_gf10.py --tag diag --cap 16000000 --modes reuse --ns 8 --drive free --readevery 1
uv run --script .../GF10/run_gf10.py --tag diag --cap 16000000 --modes pool --ns 8 --codecs h264_nvenc --drive free --readevery 0
uv run --script .../GF10/run_gf10.py --tag diag --cap 16000000 --modes reuse --ns 8 --drive free --readevery 20
uv run --script .../GF10/run_gf10.py --tag diag --cap 16000000 --modes reuse --ns 8 --drive lockstep --readevery 0
(cd .../GF10 && uv run --script run_gf10_orig.py --codecs h264_nvenc,hevc_nvenc,h264_qsv)
uv run --script .../GF10/summarize_gf10.py --tags main,diag,orig
```

## Still open
- A quiet-machine run of the bounded pattern for scrub rate and latency, plus a back-pressure method other than `getImageData` (e.g. rAF pacing).
- Why the 23:00 run grew memory instead of crashing.
- The meaning of exit code 34.
- `hevc_qsv`, Intel/AMD/Apple decode.
