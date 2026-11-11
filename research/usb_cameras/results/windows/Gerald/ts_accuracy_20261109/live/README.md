# Live per-frame timestamp error: skellycam DirectShow vs revised DirectShow vs MF raw MJPEG (Gerald, 2026-11-09)

Labels: **measured** (a file in this folder supports it), **code** (read from source), **inferred**.
All runs: 1280x720 MJPEG, 30 fps requested, fixed manual exposure −7 (2^−7 s = 7.8 ms), 75 s per run, every camera
command wrapped in `tools/camlock.py` and a hard `timeout`. No registry or device changes were made by this task.
Camera time: 13:37–14:07 UTC (about 25 min of streaming including smoke tests).

## What was run

| Run | Path | Cameras | What it emulates |
| --- | --- | --- | --- |
| A1_c930e, A1_c922 | OpenCV 4.12.0 DSHOW, `dshow_capture.py --mode skellycam --record` | one camera | skellycam as-is |
| A2 | same | C930e + Kiyo Pro | skellycam, cameras on different USB links |
| A3 | same | C930e + generic | skellycam, cameras with different real rates |
| A4 | same | C930e + Kiyo + C922 | skellycam, all that could stream together (it worked) |
| B1_c930e, B1_c922, B2, B3 | same capture setup, `--mode free --record` | as A1/A2/A3 | revised DShow: no gate, stored stamp = post-retrieve, encode on its own thread |
| mf_c922, mf_c930e, mf_kiyo, mf_generic | `timing/build/mf_uvc_timing.exe` (MF Source Reader, raw MJPEG, converters off) | one camera | MF tier 0 |
| mf_c930e_kiyo, mf_c930e_generic | same, one thread per camera | two cameras | MF tier 0 |
| mf_smoke6s_c930e_kiyo_meta | same, 6 s | C930e + Kiyo | the only MF run with UVC PTS/SCR besides mf_kiyo (see "Registry value removed") |

skellycam emulation (`timing/ts_accuracy/live/dshow_capture.py`, **code** refs are to `sc_ds/skellycam/core/camera/opencv/...` @ 169caf63):
one spawned process per camera; FOURCC MJPG, width, height, no FPS, BUFFERSIZE=1, `read()`
(`create_cv2_video_capture.py:57-75`); then AUTO_EXPOSURE=1, EXPOSURE, width, height, FOURCC (`opencv_apply_config.py:117-181`);
`read()` + 10 ms sleep until all ready (`setup_opencv_camera_loop.py:348-350`); the lockstep gate polled with `time.sleep(1e-5)`
(`camera_orchestrator.py:381-394`, `opencv_camera_loop.py:67-69`); pre/post `grab()` and `retrieve()` stamps (`opencv_get_frame.py`);
the overlay text; a copy into shared memory; an in-loop `cv2.VideoWriter` write with skellycam's codec probe (`X264` passed the probe);
`frame_count` set last (`opencv_camera_loop.py:123`). Stored stamp = grab midpoint (`create_camera_csvs.py:50-51`).

Deviations from skellycam: (1) every camera's exposure is set again 1.5 s after its first post-configuration frame, and the
gate opens only after every camera has streamed 2.5 s (needed for a constant frame period; see "C930e exposure");
(2) `check_framerate_reset` is evaluated but never resets (it never triggered: `would_framerate_reset` = 0 in every session file);
(3) the recorded videos were written to the session scratchpad and deleted.
The real skellycam (`sc_ds`) was **not** run headless: it needs the HTTP/websocket server and a recording request, which did not
fit the 20-minute budget. The emulation's capture calls and their order were checked against the source line by line.

## Commands

```bash
# from research/usb_cameras, Git Bash
uv run --script tools/camlock.py --timeout-s 1800 -- uv run --script timing/ts_accuracy/live/list_dshow.py > results/windows/Gerald/ts_accuracy_20261109/live/dshow_devices.json
VIDEO_DIR=<scratch dir> bash timing/ts_accuracy/live/run_all.sh                 # all 15 runs, log in run_log.txt
uv run --script timing/ts_accuracy/live/analyze.py results/windows/Gerald/ts_accuracy_20261109/live > results/windows/Gerald/ts_accuracy_20261109/live/analysis_tables.md
```
One DShow run, e.g. A2: `uv run --script tools/camlock.py --timeout-s 1800 -- uv run --script timing/ts_accuracy/live/dshow_capture.py --mode skellycam --cams 046D:0843,1532:0E05 --seconds 75 --record --video-dir <dir> --label A2 --out <this folder>`.
One MF run: `uv run --script tools/camlock.py --timeout-s 1800 -- <abs path>\timing\build\mf_uvc_timing.exe --out <dir> --seconds 75 --exposure-schedule -7 --exposure-dwell-s 1000 --exposure-first-s 1.5 --cam "vid_046d&pid_0843,1280,720,30,-7,auto"`.

Files: `<run>_<VIDPID>.frames.csv` (every stamp per frame, QPC ns), `<run>.session.json` (set() returns, readbacks, brightness,
writer), `mf_<run>/` (`*.frames.jsonl`, `*.session.json`, `*.controls.jsonl`), `analysis.json` (all numbers), `analysis_tables.md`, `run_log.txt`.

Cameras (DShow index at run time): generic `4C4A:4A55` (0), C922 `046D:085C` (1), Kiyo Pro `1532:0E05` (2), C930e `046D:0843` (3).
Indices are resolved by VID:PID in every run.

## Scoring (no light ground truth)

- At fixed exposure a camera emits frames on a lattice t_k = t0 + P·k. Measured camera rates (free-running DShow and MF agree to
  ≤ 20 ppm): **C922 30.000, C930e 30.085, Kiyo 30.019, generic 25.757 fps** (the generic camera does not reach 30 fps at 720p in either API). **Measured.**
- Slots: a phase-coherence periodogram (gap thresholds fail: on the 16 ms grid a normal gap can be P+16 = 49.3 ms and a one-drop gap
  2P−16 = 50.7 ms). For skellycam-mode runs, frames whose `retrieve()` did not block were already waiting ("stale"); they are slotted
  with OpenCV DSHOW's rule (the kept sample is the first to arrive after the previous `retrieve()`; `cap_dshow.cpp` 703–716) and the
  per-stream 16 ms delivery grid. The rule reproduces the direct slot of 99.6–100 % of fresh frames in the A1, A2 and B runs and for
  the A3 generic camera, 57 % for the A3 C930e (only 72 fresh frames; its period is fixed to the free-run value) and 26–50 % in A4 (see caveats). The lattice is the lower envelope of fresh post-retrieve stamps (DShow) or of MF sample time.
- Error = stamp − lattice time, median-centred: std / p95(|e|) / max(|e|) in ms. Any constant offset (true latency) is unmeasured.
- MF runs with UVC metadata: the camera's PTS/STC is used **only as an independent reference** (the registry value was set by an
  earlier session, not by this task); it is not part of any tier-0 method.

## Results: per-frame error of each stamp series (ms, std / p95 / max) — **measured**

| Camera | (A) grab midpoint, as stored | (A) post-retrieve | (B) post-retrieve | (C) MF sample time | (C) MF arrival |
| --- | --- | --- | --- | --- | --- |
| C922 alone (A1/B1/mf_c922) | 4.62 / 7.56 / 8.45 | 4.61 / 7.54 / 8.38 | 4.63 / 7.61 / 10.57 | 4.60 / 7.93 / 7.99 | 4.62 / 7.66 / 8.12 |
| C922 in A4 (3 cameras) | 16.13 / 34.91 / 45.77 | 14.79 / 34.18 / 37.48 | — | — | — |
| C930e alone (A1/B1/mf_c930e) | 5.65 / 10.04 / 47.37 | 5.40 / 9.88 / 18.18 | 4.66 / 7.69 / 10.42 | 4.63 / 7.61 / 9.35 | 4.63 / 7.62 / 10.12 |
| C930e with Kiyo (A2/B2/mf_c930e_kiyo) | 16.19 / 29.62 / 35.84 | 7.29 / 15.38 / 25.50 | 4.78 / 7.90 / 13.83 | 4.63 / 7.61 / 9.88 | 4.63 / 7.59 / 8.99 |
| C930e with generic (A3/B3/mf_c930e_generic) | 12.96 / 23.90 / 41.10 | 12.47 / 23.08 / 32.15 | 4.65 / 7.66 / 9.85 | 4.63 / 7.64 / 9.14 | 4.64 / 7.64 / 10.13 |
| C930e in A4 | 20.56 / 39.09 / 59.64 | 15.73 / 26.99 / 44.57 | — | — | — |
| Kiyo with C930e (A2/B2/mf_c930e_kiyo) | 7.59 / 17.63 / 31.01 | 4.71 / 7.86 / 10.19 | 4.71 / 7.91 / 10.23 | 4.73 / 7.94 / 10.49 | 4.73 / 7.93 / 10.55 |
| Kiyo alone (mf_kiyo, before its stall) | — | — | — | 4.72 / 7.89 / 10.52 | 5.30 / 7.93 / 85.31 |
| Kiyo in A4 | 12.24 / 21.29 / 68.14 | 15.06 / 34.38 / 56.83 | — | — | — |
| Generic with C930e (A3/B3/mf_c930e_generic) | 4.70 / 7.73 / 10.86 | 4.69 / 7.69 / 10.67 | 4.63 / 7.59 / 8.75 | 4.62 / 7.60 / 8.03 | 4.62 / 7.61 / 8.09 |

- 16/√12 = 4.62 ms is uniform quantization on a 16 ms grid. **DirectShow delivery is on the same per-stream 16.000 ms grid as MF**
  (grid coherence of fresh post-retrieve stamps 0.996–0.999 in the A1/A2/B runs). So a revised DShow loop and MF tier-0 stamps have the same floor. **Measured.**
- The lockstep gate is what makes skellycam's stored stamp bad: the slowest camera is unaffected (Kiyo in A2, generic in A3), every
  faster camera gets 13–21 ms std and 36–68 ms max. In A3, 96 % of C930e frames were stale (retrieve returned in < 2 ms). **Measured.**
- The grab midpoint also sits a near-constant ~31 ms before arrival in single-camera runs (retrieve blocks a median 31.2 ms), which is excluded above as a constant. **Measured.**

## Tier-0 lattice-fitted stamps

| Check | Result | Label |
| --- | --- | --- |
| MF C930e fitted stamps vs camera PTS (6 s run, PTS lattice residual 1.35 µs std) | 0.10 / 0.16 / 0.17 ms | measured (short run) |
| MF Kiyo fitted stamps vs camera PTS (75 s run) | 1.01 / 2.22 / 3.29 ms — the Kiyo's own PTS/STC deviates ~1.0 ms std from a lattice (1 kHz counter plus jitter), so this is the reference's noise, not the fit's | measured |
| Tier-0 slots vs camera-clock slots (mf_kiyo, smoke) | 0 mismatches (no drops occurred) | measured |
| Lower-envelope line vs least-squares line, free runs | 0.01–0.30 ms std | measured |
| Split-half extrapolation (fit first half, compare at end of second half), free DShow and MF runs | 0.01–2.5 ms; MF 0.02–0.56 ms; C930e is the worst | measured |
| Earlier flash ground truth: "frame index fitted to arrival envelope" on the C922 | same as UVC PTS, ≈ 0.5 ms = method floor (REPORT.md finding 9, timestamp-sources table) | measured (10-27/28) |

## Multi-camera pairing: how far apart in real time is "frame k" — **measured** (lattice times)

| Run | Pair | Stored-stamp difference for frame k (what skellycam writes) | Lattice-time difference for frame k (median [p5, p95], min..max) |
| --- | --- | --- | --- |
| A2 | C930e − Kiyo | 0.21 ms median, 0.23 std | −27.1 [−48.6, 17.9], −52.4..25.9 ms |
| A3 | generic − C930e | −0.24 ms median, 0.16 std | 56.4 [38.4, 74.0], 17.9..80.7 ms |
| A4 | C922 − C930e / C922 − Kiyo / C930e − Kiyo | −0.18 / −0.18 / 0.00 ms median, 1.5–1.7 std | 26.4 [−7.2, 64.0] / 10.8 [−4.0, 30.8] / −16.8 [−37.7, 15.4] ms (low confidence, see caveats) |
| B2 (free) | C930e − Kiyo | drifts: −72 ms median, 48 std | drifts from +6.8 to −156 ms over 74 s (2.2 ms/s rate difference) |
| B3 / mf_c930e_generic | | drifts by seconds (different rates) | index pairing meaningless |
| B2, B3, MF pairs | nearest neighbour in lattice time instead of by index | — | median |Δ| 7.8–9.7 ms, bounded by P/2 ≈ 16.7 ms |

- In lockstep, the gate lets a camera take frame k as soon as the slower peer finishes k−1, and DSHOW `retrieve()` then returns the
  frame buffered since its last read. So the faster camera's frame k is typically from about one frame earlier than the slower
  camera's frame k, while the stored stamps say the two were taken within 0.2 ms. **Measured** (A2, A3); mechanism **code**.
- Lockstep forces drops on the faster camera equal to the rate difference: A2 C930e 3, A3 C930e 320 (14 %), A4 C930e 6, Kiyo 2, C922 1.
  Expected from the free-run rates over 74 s: 4.8, 320, 6.9 / 2.4 / 0. **Measured.**
- The lattice differences include each camera's constant latency, which differs by model (MF sample time on the generic camera is
  32 ms before arrival; 0.2 ms on the others). Cross-camera offsets therefore need a one-time per-model latency calibration. **Measured** (the 32 ms); calibration need **inferred**.

## Other findings from these runs — **measured**

- **C930e exposure under skellycam's sequence is lost.** `apply_camera_configuration` sets exposure and then FOURCC, which restarts
  the DShow graph; the C930e then runs at its default (readback −4, image mean 84–103) until the exposure is set again (mean 14–19).
  Seen in all 7 C930e DShow runs (`brightness_before_after_exposure_reset` in each session file). Kiyo, C922 and generic keep −7.
- OpenCV DSHOW: `set(CAP_PROP_BUFFERSIZE, 1)` returns False; `get(CAP_PROP_FPS)` = 0; `get(CAP_PROP_POS_MSEC)` = −1 (all session files).
- In-loop `cv2.VideoWriter` (`X264`) write: median 0.4–0.5 ms per frame, so encoding was not the loop bottleneck here.
- No drops in any free-running DShow or MF run.

## Failures and anomalies

- **Registry value removed mid-session (not by this task).** `MetadataBufferSizeInKB0` was removed from all 26 camera interface keys at
  2026-11-09T08:49:11−05:00 by an elevated process (`results/windows/Gerald/metadata_revert_20261109/revert.log`). MF runs after
  13:49 UTC have no capture metadata (`attr_counts` in their session files); only `mf_kiyo` (13:44 UTC) and the 6 s smoke run
  (13:40 UTC) carry PTS/SCR. All later MF runs are genuinely tier 0. A read-only registry query after the runs found the value absent.
- **Kiyo stalls in mf_kiyo:** no frames for 8.1 s at 60 s and 7.8 s at 68.7 s, then recovered; scored on the 57 s before the stall.
  The Kiyo streamed normally in the four later runs (A2, B2, mf_c930e_kiyo, A4). Not a wedge.
- **A4 slotting is unreliable:** with three cameras (C922 and Kiyo share one USB 2.0 upstream link) the fresh frames' delay above
  the envelope spreads to 27–48 ms and the grid coherence drops to 0.86–0.89, so the window rule matches only 26–50 % of fresh
  frames and the split-half fit disagrees by ~1000 ppm. A4's error sizes are indicative; its drop counts match the rate prediction.
- A1_c930e had four 52–60 ms delivery gaps (frames 278, 317, 549, 1298), which give its larger max.

## Caveats

- No light ground truth today: constant latency and per-model latency differences are unmeasured; errors are relative to each camera's own lattice.
- DShow decodes MJPEG to RGB24 in its graph thread before `retrieve()` returns (`cap_dshow.cpp` 2904, **code**), so post-retrieve includes decode; the mean delay of fresh frames above the envelope was 7.6–8.1 ms in single-camera and free runs, the same as MF sample time (7.5–8.1 ms); a constant decode time is absorbed into the envelope, and no extra decode jitter is visible (**inferred** from these numbers).
- The 16 ms grid caps any host stamp at ~4.6 ms std; only lattice fitting (tier 0) or camera clocks (tier 1) go below it.
- The camera-clock reference covers only the Kiyo (75 s, ~1 ms reference noise) and the C930e (6 s) because of the registry removal.
