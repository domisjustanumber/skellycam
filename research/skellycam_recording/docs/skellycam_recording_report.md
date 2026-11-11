# How skellycam saves recordings: consolidated report

Written 2026-11-09. This is the clean summary of the `skellycam_recording` study. The detailed working review, with every step and correction, is `research/skellycam_recording/REPORT.md`. Labels in parentheses, like (R2), point to its sections and findings.

**Code bases.**
- **Today's default path:** `dom/research` @ `55f851e4`. Its recorder, camera loop, camera group, timestamp and pubsub code is identical to upstream `development` @ `23ccbf20`, which the frame ring buffer study also benchmarked.
- **Later upstream:** `upstream/sfn26` @ `765bf82d` (2026-11-07), `upstream/main` @ `06771043`, and `upstream/development-streaming` @ `169caf63`.
- **FreeMoCap:** `development` @ `5632778a`.

**Labels:** **measured** (a result file supports it), **code** (read from the source), **inferred** (reasoned, not tested).

**Paths.** Result paths are relative to `research/skellycam_recording/`. Code files are named by file name; they sit under `skellycam/core/…` or `skellycam/api/…` (full paths in REPORT.md). Upstream evidence is in `results/upstream_check_20261109/`.

**Measurements.** All on Gerald (Windows 11, RTX 3070) on 2026-11-09, with 3 cameras: Logitech C930e, Logitech C922 and Razer Kiyo Pro.

## 1. Summary

| | Today (`23ccbf20`, default Python/OpenCV path) | `sfn26`, Python path (still the default) | `sfn26`, Rust path (opt-in) | Evidence |
| --- | --- | --- | --- | --- |
| **Timestamps survive an unclean ending** | No. CSVs and the info JSON are written only after a clean stop | No | Partly. A native CSV is flushed every frame | code; §5.1 |
| **Clean video (no overlay)** | No. The debug text is burned into every recorded frame | No | Yes | measured (today); code (sfn26) |
| **Correct header frame rate** | No. Videos play 9–11% fast, and each camera gets its own rate | No | Uses the negotiated mode rate (e.g. 30). Still CFR, so drops stay hidden | measured (today); code (sfn26) |
| **Encoder** | Media Foundation → NVIDIA NVENC MFT on Gerald. Fixed bitrate, about 1 s GOP | Same | ffmpeg libx264, CRF 18, ultrafast | measured (today); code (sfn26) |
| **Survives a hard kill** | No. A killed MSMF `.mp4` keeps 0 of 300 frames | No | No (plain MP4). Outcome depends on whether ffmpeg outlives its parent | measured (today); inferred (sfn26) |
| **Latent finalize bugs** (wrong camera names, previous recording finalized, hang on close) | Present | Fixed, with one new hang case | Different set; see §6.3 | code |

- **Where the work happens.** Each camera process encodes its own video inside the capture loop. The main process writes the CSVs, stats and info JSON only after a clean stop, from one big metadata message per camera. (**code**; confirmed in the log)
- **Unclean ending = no timestamps.** A kill-flag shutdown, crash or `GET /shutdown` mid-recording leaves no CSVs and no info JSON. A hard kill also leaves an unreadable `.mp4`. (**code**; hard kill **measured**)
- **Overlay.** The debug text `camera.id…idx…fr…` is in every recorded frame, calibration recordings included. (**measured**)
- **Fast headers.** Real 30.0 fps cameras got headers of 32.79–33.25 fps, a different value per camera, so 60.1 s of capture became about 54.7 s of video. (**measured**)
- **Encoder.** Windows uses whatever Media Foundation encoder the machine has (NVENC on Gerald), at floor(header fps) × W × H bit/s. That is about 12 GB per camera-hour at 720p30 and 28 GB at 1080p30. (**measured**)
- **Calibration recordings** are normal recordings with the microphone off, in a folder ending `_calibration`. (**code** + **measured**)
- **Upstream.** `sfn26` fixes the latent bugs, the stats JSON and `/shutdown`, but not the default path's data problems. The opt-in Rust backend fixes most of those. In code, though, it has a likely ffmpeg stderr deadlock after a few tens of seconds, and one camera's failure destroys every camera's video. (**code**, static only)

## 2. How a recording is saved today

### 2.1 Flow

All file references are at `55f851e4`.

| Step | What happens | Code |
| --- | --- | --- |
| **Start** (`POST …/group/all/record/start`) | Pause all cameras. Set the first recording frame to `max(frame_count) + 3`. Publish `RecordingInfoMessage`. Start `AudioRecorder` in the API process if a mic is chosen. Unpause. Each camera then **probes the codec by writing a one-frame temp video**, opens its writer at its own frame-rate estimate, and waits until all cameras are recording. Takes 0.84–1.05 s with 3 cameras (**measured**, `run*_drive.json`) | `camera_group.py:183-213`; `handle_recording_updates.py:15-48`; `fourcc_codec_helpers.py:95-196` |
| **Every frame** | `grab()`, `retrieve()`, then draw the overlay into the same array. Copy it to shared memory (UI, FreeMoCap). `record_frame`: check frame number and shape, rotate, `cv2.VideoWriter.write()`, and append the 632-byte metadata to a list. Lockstep means a slow write delays every camera. `record_frame` median 0.99 ms at 720p, 2.17 ms at 1080p (**measured**, ring buffer `c_record.md`) | `opencv_camera_loop.py:89-105`; `opencv_get_frame.py:79-83`; `video_recorder.py:87-109` |
| **Stop** (`GET …/group/all/record/stop`) | Pause. Stop audio (writes WAV and sidecar). Set the last frame to `max(frame_count) + 3`. Unpause. At that frame each camera releases its writer and publishes one `RecordingFinishedMessage` with **the whole metadata list**. The main process polls every 100 ms until all have reported | `camera_group.py:215-238`; `handle_recording_updates.py:50-59` |
| **Finalize** (main process) | Write the info JSON. Check frame numbers agree, then write per-camera CSVs, multiframe CSV and stats. Write the README. `validate_recording`: videos open, frame counts equal, CSV rows = video frames. The audio/VFR remux is **commented out**. Runs synchronously on the FastAPI event loop. Stop call: 0.78–0.89 s (20 s takes), 1.17 s (40 s), 1.47 s (60 s) (**measured**) | `recording_finalizer.py:53-67` (remux line 63) |

### 2.2 Files, writers and timing

```
<recording_directory>/<recording_name>/
├── <recording_name>_info.json
└── synchronized_videos/
    ├── <recording_name>.id-<cam_id>.idx-<cam_index>.mp4      (.avi only for XVID/MJPG fallbacks)
    ├── <recording_name>.audio.wav                            (only with a microphone)
    ├── <recording_name>.audio_timestamps.json                (only with a microphone)
    ├── synchronized_videos_README.md
    └── timestamps/
        ├── <recording_name>_timestamps.csv
        ├── <recording_name>_stats.json  /  _stats.txt
        └── camera_timestamps/
            └── <recording_name>.camera<cam_id>.timestamps.csv
```

| File | Written by | When | Contents |
| --- | --- | --- | --- |
| Video, one per camera | That camera's process | During the recording | The overlaid frames (§3.4). `idx` is the DirectShow index |
| WAV and audio sidecar | API process | At stop | 44.1 kHz, up to 2 channels, int16. The sidecar has the start stamp and per-chunk host stamps (§3.6) |
| Info JSON | Main process | After stop | Name, directory, UUID, mic index, start timestamp, and each camera's full `CameraConfig`, **as read back from the capture**: `framerate: 0.0` under DirectShow, and C930e exposure −5 when −7 was requested (**measured**) |
| Per-camera CSV | Main process | After stop | 27 columns per frame: frame numbers, the main timestamp (midpoint of the pre- and post-`grab()` stamps), UTC and local time, and every lifecycle stamp and duration (`create_camera_csvs.py:45-103`) |
| Multiframe CSV | Main process | After stop | 103 columns: the means across cameras, the per-frame grab spread, and stats per lifecycle column (**measured**) |
| `_stats.json` / `_stats.txt` | Main process | After stop | The JSON's 13 statistic blocks are all `{}` (§5, smaller issues). The `.txt` has the numbers (**measured**) |
| README | Main process | After stop | Fixed text claiming frame *k* is "the same moment in time" in every camera. The timestamps review shows frames can be up to about one period apart |

The real recordings matched this tree exactly, with nothing extra or missing (**measured**, `results/real_recording_20261109/RESULTS.md` §3). One more video file can appear later: when the playback view opens a video that isn't browser-playable (the `mp4v`, XVID or MJPG fallbacks), it writes a `<stem>.web.mp4` re-encode of the overlaid file into `synchronized_videos/` (`playback_router.py:114-139`). FreeMoCap filters by suffix only, so it might count that file as an extra camera (**code**; effect not tested). sfn26 removes this sidecar (§6.2).

## 3. What the files actually contain (measured)

Five real recordings with 3 cameras, driven over HTTP like the UI, all on Gerald. All cameras ran MJPEG at 30 fps under DirectShow. Every recording finalized and passed `validate_recording`, and the frame count of every video equalled its CSV row count.

| Run | Path | Mode | Length | Mic |
| --- | --- | --- | --- | --- |
| A | skellycam | 1280×720 | 60 s | yes |
| B | FreeMoCap calibration start | 1280×720 | 40 s | forced off |
| C | skellycam | 1920×1080 | 20 s | no |
| D | skellycam, `OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS=0` | 1280×720 | 20 s | no |
| E | skellycam, loaded-DLL probe | 1280×720 | 15 s | no |

### 3.1 Per-mode results

Source: `results/real_recording_20261109/per_video_table.md` (15 videos) and the `run*/…_ffprobe_*.json` files.

| | 720p (runs A, B, D, E; 12 videos) | 1080p (run C; 3 videos) |
| --- | --- | --- |
| Codec, profile | H.264 Constrained Baseline L4.1, yuv420p | H.264 Constrained Baseline L5.0 |
| Frame types | I + P only, `has_b_frames=0` | I + P only |
| GOP | 32 frames | 33 frames |
| Header fps (real 30.0) | 32.79–32.97 | 33.23–33.25 |
| Header duration / real span | 54.68–54.82 s / 60.08 s (run A) | 18.11 s / 20.03 s |
| Bitrate over the file's timeline | C922, Kiyo: 29.4–29.6 Mbit/s. C930e: 25.1–26.2 | 67.8–68.7 Mbit/s |
| Bytes per frame | C922, Kiyo: ~112 kB. C930e: ~99 kB (run A) | ~255–258 kB |
| Size per camera per hour of real recording at 30 fps | **~12.1 GB** (C930e ~10.7) | **~27.9 GB** |

The per-hour figures are bytes per frame × 108,000 frames: measured per frame, extrapolated per hour (**inferred**). The ring buffer study's synthetic frames gave 115,734 B per frame at 720p and 258,648 B at 1080p, which agrees. At 5 × 1080p the disk filled in 54 min (ring buffer study, `p12_disk_sustained.md`). REPORT.md first quoted 13.3 GB and 31 GB per camera-hour. Those were per hour of the file's shorter, fast timeline, and REPORT.md has since been corrected to these real-time figures (Notes on sources, 1).

Rules that fit every file (**measured**):
- **GOP = floor(header fps)**: one I-frame per header-second.
- **Bitrate target = floor(header fps) × W × H** bits per second. That is 29.49 Mbit/s at 720p and 68.43 Mbit/s at 1080p. The C922 and Kiyo hit it within 1%. The C930e came in 11–15% under it at 720p, so the encoder does not pad every scene to the target; that it depends on content is **inferred**. Because the target follows the header rate, file size can't reveal a wrong header rate.

### 3.2 Encoder

- **Windows: Media Foundation → NVENC.** The default fourcc is `X264` (`camera_config.py:29`). OpenCV's FFmpeg writer is tried first and fails because `openh264-1.8.0-win64.dll` is missing (**measured**, `runA_server.log`). The MSMF writer takes over and maps the fourcc to H.264 (**code**, `cap_msmf.cpp`). Run E found NVIDIA's `nvEncMFTH264x.dll` loaded in all three camera processes and Microsoft's `mfh264enc.dll` not loaded (**measured**, `runE_drive.json`).
- **The env var can't switch it off.** In OpenCV 4.12, `OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS` reaches only the capture reader (`cap_msmf.cpp:959`); the writer hard-codes hardware transforms on (`:2620`). So run D changed nothing.
- **The format is the encoder's default.** OpenCV sets only the bitrate (`(UINT32)fps × W × H`) and frame rate. A machine without an NVIDIA GPU gets another MFT, possibly with other defaults; one with the OpenH264 DLL would probably record through FFmpeg instead (both **inferred**).
- **Other platforms:**

| Platform | Expected writer | Settings | Status |
| --- | --- | --- | --- |
| Linux (pip OpenCV) | `X264_PYAV` → PyAV libx264 | CRF 18, preset fast. The synthetic test gave High profile, B-frames and an I-frame every 250 frames, at 1.29 Mbit/s against 27.7 for Windows on the same content | code; GOP **measured** (`gop_test.py`); platform outcome inferred |
| macOS | `avc1` (VideoToolbox) | OpenCV AVFoundation writer | inferred |
| Last resort | `MJPG` in `.avi` | Large files that Chromium can't play | code |

- **Random access.** Sequential reading, which is how FreeMoCap reads, is unaffected by the GOP. Seeking to frame *k* means decoding from the previous I-frame: up to about 1 s on Windows, up to 249 frames on Linux.

### 3.3 Header rate versus real rate

- **Source.** `1 / median(last ≤1000 frame intervals)`, measured by each camera before the recording (`opencv_camera_loop.py:80-84`, used at `video_recorder.py:80`).
- **Bias.** 2.79–3.25 fps (9.3–10.8%) above the achieved 29.99–30.01 fps in all 15 videos. Each video lasts 90–91% of the real span (**measured**). Two causes stack:
  1. **Stamp placement (code):** `previous_tik` is reset at the end of the loop (line 117), so each sample misses the shm copy and the write.
  2. **DirectShow delivery (measured):** intervals are mostly ~32 ms with a ~48 ms step every 12–13 frames (median 32.1 ms, mean 33.3 ms), so the median alone gives 31.1–31.2 fps.

  Rebuilding the loop's sample from the CSV stamps brackets the header rates. The split between the causes is **inferred**.
- **Cameras disagree.** Run A: 32.890 / 32.933 / 32.971 fps; after 60 s their header durations differ by 0.135 s, about 4 frames (**measured**).
- **Fallback is 0 fps on Windows.** With fewer than 30 intervals (a start within ~1 s of connecting), the rate falls back to the extracted `framerate`, which is **0.0 under DirectShow** (**measured**, info JSON). What MSMF does with fps 0 was not tested.
- **It can get worse.** A loop that slows during recording makes the header overstate further (**inferred**; no slowdown occurred).
- **Gaps are invisible.** A pause mid-recording (the API doesn't refuse it) or a `check_framerate_reset` reopen keeps frame numbers consecutive, so the CFR file closes up the gap (**code**). Real timing exists only in the CSVs, which FreeMoCap ignores: it pairs frames by index.

### 3.4 Overlay

- **What it is.** Every frame of every video in runs A–E carries `camera.id<cam_id>.idx<cam_index>.fr<N>` at the top left (**measured**, frame 100 extracted from each video). It is light lavender text with a thick black outline (`cv2.putText` at (10, 40), scale 0.8; `opencv_get_frame.py:79-89`). It covers about x 5–340, y 15–50 px, the same pixel size at 720p and 1080p.
- **The number is not the recording index.** `N` is the connection frame number. For example, 550 = 450 (first recorded frame) + 100.

### 3.5 Timestamps in the CSVs

- **The main timestamp marks the start of the wait, not frame arrival.** Under DirectShow, `grab()` is a no-op (median 0.046 ms) and the wait happens in `retrieve()` (median 26.5 ms of a 33 ms period). The grab midpoint therefore marks when the loop started waiting. The 0.27 ms "inter-camera grab sync" measures loop lockstep, not capture sync (**measured** durations; meaning **inferred**; see `usb_cameras/docs/skellycam_timestamps_review.md`).
- **The per-camera CSV's local time is 5 h off** (it applies the UTC offset twice). The multiframe CSV's local time is correct (**measured**).

### 3.6 Audio (run A)

- **Format.** 2 channels, 16-bit, 44,100 Hz. All samples stay in RAM until stop, about 635 MB per hour in stereo (**code**).
- **Alignment.** Audio started **1.022 s before the first recorded frame** and ended **85.9 ms (about 2.6 frames) before the last**. Nothing aligns or muxes it; a consumer must line up `start_perf_counter_ns` with the CSVs (**measured**).
- **Stamps.** The start stamp is taken before the stream is constructed (`audio_recorder.py:68`); the first callback came 139 ms later. Chunk stamps are callback host times, in bursts (median gap 0.16 ms, max 51 ms). Sample count and stamp span differ by 90 ms (**measured**). PortAudio's ADC time is ignored and overflows are only logged (**code**).

## 4. FreeMoCap calibration recordings

**How they are triggered** (**code**, FreeMoCap `5632778a`):
- The UI sends `POST /freemocap/calibration/recording/start` with `calibrationRecordingDirectory = <root>/<YYYY-MM-DD_HH-MM-SS_GMT-5>_calibration`.
- `calibration_router.py` forces `mic_device_index = -1`, returns 409 if `synchronized_videos/` already holds a video, and calls skellycam's own `CameraGroupManager.start_recording_all_groups`. It sends no camera settings of its own.
- `POST /freemocap/calibration/recording/stop` calls skellycam's `stop_recording_all_groups()`, then immediately starts the posthoc calibration solve.
- If a realtime pipeline is running, the stop also writes `output_data/charuco_observations_realtime.pkl`.

**How they differ** (**measured**, run B; started through FreeMoCap's endpoint, stopped through skellycam's stop, which is the same call minus the solve):
- There is no WAV or audio sidecar, the info JSON has `mic_device_index: -1`, and the folder name ends `_calibration`.
- Everything else is identical: the same tree, Constrained Baseline, GOP 32, a header of 32.84–32.93 fps against 30.01 achieved, the same bitrate, and **the overlay burned in** (`camera.id0100.idx3.fr540`).

**Not exercised.** No realtime pipeline ran, so the `.pkl` was not produced, and no calibration was solved. FreeMoCap's own venv is stale (skellytracker import error); the run worked around that with a `PYTHONPATH` overlay without changing either environment. The skellycam installed in FreeMoCap's venv is byte-identical to `55f851e4` (**measured**).

## 5. Problems, ranked by impact

The "sfn26" columns are from static reading of `765bf82d`. On sfn26 the default is still the Python path.

| Rank | Problem | Effect today | Evidence | sfn26 Python (default) | sfn26 Rust (opt-in) |
| --- | --- | --- | --- | --- | --- |
| 1 | **Timestamps only after a clean stop** (R1) | Any unclean ending loses all timing, the info JSON and the frame counts that validation needs | code; `camera_group.py:317-379` is the only reader of `RECORDING_FINISHED` | Unchanged. `/shutdown` and Electron quit now take this unfinalized path | Partly fixed: native CSV flushed per frame; the standard CSVs and info JSON are still built only at stop |
| 2 | **Overlay burned into the recording** (R2) | Text over about 335 × 35 px at the top left of every frame. ChArUco corners, hands or markers there are corrupted. No clean copy exists | measured, all runs | Unchanged (`opencv_get_frame.py` byte-identical) | Not applicable: records the camera's JPEGs |
| 3 | **Header rate is a per-camera pre-recording estimate, biased high** (R3) | Videos play 9–11% fast, cameras disagree, the fallback is 0 fps, and gaps are invisible | measured | Unchanged | Mode rate (e.g. 30), the same for all cameras in a mode. Still CFR. A 60 fps-capable camera grouped with 30 fps cameras would get a 60 header while lockstep holds it near 30 (inferred) |
| 4 | **Container not crash-tolerant** (R5) | A hard kill, crash or power loss loses the whole MSMF MP4: 0 of 300 frames readable, where MJPEG-in-MKV kept 298–359 | measured (`frame_ring_buffer/prototypes/results/p11_crash_container.md`) | Unchanged | Unchanged (plain MP4, no `movflags`) |
| 5 | **Camera order assumed by position** (R6) | After deselecting a camera and re-applying, the next recording writes each camera's timestamps under the next camera's name, and drops one | code; UI flow inferred | **Fixed** (`dc578551`, `43e2b968`) | The reported case can't happen. But frames are routed to files by position, and `apply()` isn't refused mid-recording (inferred risk, non-UI clients) |
| 6 | **Stale finished message** (R7) | Starting while already recording leaves stale messages. Every later stop then silently finalizes the *previous* recording, until the group is recreated | code | **Fixed** at the API: a second start returns 409. The underlying mechanism is still there, unreachable through the API | Fixed in the shipped build |
| 7 | **Fixed-bitrate H.264, encoder defaults** (R4) | About 12 GB per camera-hour at 720p30. No quality setting. The bitrate is tied to the wrong header rate, and GOP and profile vary by machine | measured | Unchanged (OpenCV still 4.12.0.88) | libx264 CRF 18 ultrafast. Size depends on content; I-frame every 250 frames (inferred) |
| 8 | **A dead camera process hangs close** (R8) | `orchestrator.close()` and `pause()` wait with no timeout, before any terminate step | code; trigger inferred | **Fixed** for a dead process. **New:** a live but hung camera that is still recording blocks close and app exit forever (`managed_worker.py:66-74`) | No camera processes. Some waits have no timeout |
| 9 | **Finalize blocks the event loop** (R10) | The UI and websocket freeze during finalize; the time grows with length | inferred; stop call measured growing 0.8 → 1.5 s over 20 → 60 s | Unchanged | Unchanged, plus a row-by-row CSV parse on the loop |
| 10 | **All metadata in one message at stop** (R9) | ~694 B per frame pickled, about 75 MB per camera per hour. The ring buffer study saw a ~387 + 127 ms loop stall for 36,000 frames (PROVISIONAL) | measured per frame; inferred per hour | Unchanged | Fixed: streamed per frame |
| 11 | **Audio unaligned and loosely stamped** (R11) | A/V sync is left to the consumer; ADC time and overflows are discarded | measured (run A) + code | Unchanged | Partly fixed (§6.3). Still not muxed |

### 5.1 What survives which ending (default Python path)

| Ending | Videos | CSVs, stats, info JSON | Change on sfn26 Python |
| --- | --- | --- | --- |
| Clean stop | Closed and validated | Written | A missing video now aborts finalize at step 1, so **nothing** is written. A stop that fails leaves later starts refused (409) until the cameras are closed |
| Kill flag (any exception in a camera loop, the UI relay or a FreeMoCap node) | `finally` releases each writer; the process gets 3 s before `terminate()`. Probably playable (**inferred**) | **Not written** | Camera errors stop only their own group, and a worker with an open writer gets unlimited time to save. A websocket-relay exception still ends every group. Still not finalized |
| `GET /shutdown` | On Windows it hard-kills the server: exit code 15, no reply, no cleanup (**measured**; the groups were already closed, so no recording was affected) | Not written | **Fixed**: replies 200 and waits for video saves. A Python recording in progress still ends unfinalized |
| One camera's writer fails to open at start | Peers are released holding 0-frame recorders | Each peer raises a second traceback and sends no message | Same symptom, but only the failing group stops |
| A camera process dies without its `finally` | — | Close hangs (rank 8) | Fixed (bounded join, terminate, kill) |
| Hard kill, crash or power loss | MSMF `.mp4`: 0 of 300 frames readable (**measured**) | Not written | Unchanged (**inferred**) |
| 30 failed grabs in a row | The frame number repeats, `_validate_frame_number` raises → kill-flag row | — | Now raises `RuntimeError`; the group stops, still not finalized |
| Rotation set to 90°/270° mid-recording through the API | Shape check raises → kill-flag row | — | Only the group stops |
| `validate_recording` fails | Kept | Written; HTTP 500 | Same, except a missing video (above) |

### 5.2 Smaller issues (default path; all **code** unless marked)

- **`_stats.json` is empty:** all 13 statistic blocks are `{}`, because `default=lambda o: o.__dict__` can't serialize `np.recarray` (`recording_timestamp_stats.py:143`; **measured**). Fixed on sfn26 (#141). Side effect on sfn26: FreeMoCap will now read its filter rate from `framerate_stats.median` (inferred).
- **A codec probe runs at every recording start**, per camera, with no timeout on Windows. It is part of the ~1 s start. Unchanged on sfn26.
- **A reused recording name silently overwrites** the old video, even into a container with a different extension (`recording_info.py:95-100`). Partly fixed on sfn26: it now raises on a different extension, but still overwrites a same-extension file.
- **The two CSVs disagree on local time** (§3.5). Unchanged on sfn26.
- **`validate_recording` check 1 doesn't fail on a missing file** (`recording_finalizer.py:140-145`). On sfn26 a missing file aborts earlier, at `save_to_file`.
- **Path properties call `mkdir` when read** (`recording_info.py:37-63`). **The API defaults nest as `<ts>/<ts>/`** when a client sends neither directory nor name (the UI sends both). Both unchanged on sfn26.
- **The dormant remux** (`video_audio_remuxer.py`) would put real gaps into the file (1/90000 time base, PTS from the CSV). But it re-encodes every video with libx264, uses the grab-midpoint stamp, and writes MP4 content under an `.avi` name. Unchanged on sfn26.

## 6. Status on later upstream branches

Checked 2026-11-09 by static reading only; nothing was built or run on these branches (§9).

| Branch | Tip | Relevant to recording? |
| --- | --- | --- |
| `upstream/sfn26` | `765bf82d`, 2026-11-07 | **Yes.** It changes the Python path and adds the opt-in Rust backend. It contains `cleanup-camera-api` and nearly all of `development-streaming` |
| `upstream/main` | `06771043` | No. Its 3 extra commits change logging, PubSub closure and a VID/PID check. It also lacks the R6 fixes |
| `upstream/development-streaming` | `169caf63` | No. Its 2 extra commits change startup-failure reporting and CI. sfn26 has a wider version of the first |

Evidence: `results/upstream_check_20261109/verdict_table.md`, `main_devstreaming_deltas.md`.

### 6.1 Which backend users get

- **Python/OpenCV is still the default on every OS:** `"python"` in `CameraBackendManager`, in the API request and in the UI store (`upstream/sfn26:skellycam/core/camera_group/camera_backend_manager.py:26,30`).
- **Rust is opt-in per camera group,** through a UI dropdown or the API `backend` field. Switching backends requires closing the cameras first.
- **The Rust crate ships everywhere but is tested only on Windows.** It is a required dependency, built on every `uv sync` and bundled in the installers for all 5 targets. Only Windows x64 has been exercised; macOS and Linux only build and import (`rust_recording_overview.md` §1).

### 6.2 sfn26, Python path (default)

**Fixed** (**code**):
- R6 camera order (`dc578551` adds an ID check and reorders by ID; `43e2b968` recreates the group when membership changes).
- R7 (a second start returns 409).
- R8 for a dead process.
- The empty stats JSON (#141; a NaN statistic is now written as a bare `NaN`, which strict JSON parsers reject, inferred).
- The `/shutdown` hard kill (`d65707a1`).

**Unchanged:**
- The overlay, header-rate estimator, 0 fps fallback, CFR video with the remux off, and codec probe.
- MSMF/NVENC at a fixed bitrate (OpenCV still 4.12.0.88), the PyAV settings and the plain MP4 container.
- Timestamps only after a clean stop, one big message at stop, and finalize on the event loop.
- Audio, the local-time bug and the grab-midpoint stamp.

**New behaviour to know about** (**code**, effects **inferred**):
- **Stop is now `POST`;** `GET` returns 405. FreeMoCap calls skellycam internally, so it isn't affected.
- **A missing video aborts the whole finalize:** no info JSON, CSVs or stats.
- **The `.web.mp4` transcoder is deleted,** so `mp4v`, XVID and MJPG fallback recordings no longer play in the playback view (regression). `browser_stream.py` could replace it but has no production caller.
- **The info JSON gains `videos`, `camera_timing` and `multiframe_timing`.** Playback uses them to prefer CSV timing; older recordings fall back to the biased header fps.
- **A FreeMoCap calibration solve would fail:** FreeMoCap nodes call `WorkerRegistry.create_worker` without its new required `shutdown_flag` and `worker_mode`. The recording itself is still written.
- **An exposure sweep can land in a recording** if a non-UI client applies a RECOMMEND config mid-recording, putting 80+ frames of changing brightness into the take.
- **Camera order in the CSVs and info JSON can vary between runs** (worker arrival order). Alignment is safe because finalize reorders by ID.

### 6.3 sfn26, Rust path (opt-in)

**How it records** (**code**, `skellycam-rust/`; `rust_recording_overview.md`):
- openpnp-capture (DirectShow on Windows) runs one thread per camera, MJPEG only.
- Each camera's JPEG bytes are piped to its own ffmpeg process (imageio-ffmpeg):
  `ffmpeg -f image2pipe -c:v mjpeg -s WxH -r <fps> -i pipe:0 -c:v libx264 -preset ultrafast -crf 18 -pix_fmt yuv420p -an <out>.mp4`
  (`recorder.rs:137-155`).
- Python then runs the same `RecordingFinalizer`, so the standard tree is produced, plus `native_recording_summary.json` and a per-camera `…native_timestamps.csv`.

**Improvements over the measured Python path** (**code**; effects **inferred**):

| Improvement | Detail | Caveats |
| --- | --- | --- |
| **No overlay** | The camera's JPEGs are never drawn on; `skellycam-rust/src` has no drawing code. Rotation is lossless in the DCT domain (`dispatcher.rs:197-214`) | Still one decode and re-encode, not MJPEG passthrough |
| **Header = negotiated mode rate** | The format's integer fps (`camera_thread.rs:167,219`), fallback 30 (`dispatcher.rs:376-390`). No estimate, so no +9–11% bias; every camera in a mode gets the same value | Still CFR: drops or slow delivery are hidden. The rate is recorded only in the video header (the info JSON keeps the requested −1), and the dispatcher's measured fps is thrown away |
| **Quality-based encode** | CRF 18: size follows content, not `fps × W × H`. ultrafast keeps CPU low and turns off B-frames, CABAC and scene-cut, so an I-frame every 250 frames. No longer depends on the GPU encoder | Hard-coded (`recorder.rs:17-20`); software libx264 in N processes; still a plain MP4 |
| **Timestamps streamed** | One row per frame, flushed (`csv_writer.rs:53-72`): `frame_number`, `loop_start_ns`, `frame_available_ns`, `post_jpeg_extract_ns`, `pre_send_ns`, `gatherer_received_ns`, `pre/post_frame_record_ns`. A Rust monotonic clock aligned once to `perf_counter_ns`. Flushed rows survive a process crash. `frame_available_ns` is a better stamp than Python's no-op-`grab()` midpoint | No fsync, so a power loss can lose rows. The standard 27-column CSV maps `loop_start`/`frame_available` onto the grab columns, so its main timestamp is not comparable with Python-backend CSVs |
| **Better audio** | Start stamp after the stream opens; host stamp plus ADC estimate per chunk (`audio.rs:89-92`); dropped chunks and status flags recorded; streamed to disk; audio brackets the video | Still not muxed or aligned |
| **Graceful endings finalize** | `/shutdown`, app exit and group close stop and fully finalize a Rust recording | — |

**Risks** (**code**; consequences **inferred**, untested):
1. **ffmpeg stderr deadlock (highest priority).** `ffmpeg-sidecar` 2.5.1 pipes ffmpeg's stderr and adds `-loglevel level+info`, but drains stderr only inside `wait()`. skellycam-rust calls `wait()` only at stop (`recorder.rs:233-240`; crate source `command.rs`/`child.rs`, re-read by hand). ffmpeg writes a progress line about every 0.5 s. Once the pipe fills (about 4 KB on Windows, roughly 10–30 s; 64 KB on Linux and macOS, a few minutes), this chain follows:
   1. ffmpeg blocks and stops reading stdin.
   2. `feed_frame`'s `write_all` blocks.
   3. The recording thread never processes Stop.
   4. Python's stop never returns, and `close()` hangs behind it.
   5. The unbounded frame queue keeps growing.

   The only Rust recording test is 150 frames, about 5 s (`recording_tests.rs:20-22`; `completeness_critique.md` B4).
2. **One camera's error destroys every camera's video.** A 5 s frame timeout or capture failure ends that camera's thread and breaks the gatherer barrier. The dispatcher and recording thread exit, and `VideoRecorder::drop` kills ffmpeg, leaving MP4s with no moov atom. Only the native CSVs survive. Python keeps playable videos in the same case.
3. **Mid-recording changes corrupt the take.** `apply()` and the exposure sweep aren't refused while recording (the UI blocks them; API clients aren't blocked). Removing a camera shifts frames into other cameras' files; a rotation change makes ffmpeg scale rotated frames into the original size.
4. **Start succeeds before any recorder exists.** Spawn, CSV or overwrite failures surface only at stop ("Rust recorder did not produce video frames"). If the Rust finalizer rejects a frame-count mismatch, Python crashes on `Path('').read_text()`.
5. **Strict audio check costs the finalize.** Any dropped chunk or status flag makes stop raise **before** the Python finalize: no info JSON, no standard CSVs, and later starts refused until the cameras are closed.
6. **No FreeMoCap realtime ChArUco on Rust** (`RustCameraGroup` has no `shm`/`ipc`). FreeMoCap sends no backend, so it gets `CameraBackendInUseError` while a Rust group is open.

## 7. Recommendations, in order

Updated for what sfn26 already fixes. Items 1–5 apply to the default Python path on both `development` and `sfn26`.

1. **Stop drawing the overlay on recorded frames** (R2). Draw it on the UI copy only. Small, and still needed on sfn26's default path.
2. **Write timestamps during the recording, and finalize off the event loop** (R1, R9, R10). Append each frame's row, or a fixed-size record, to a per-camera file as it is written, and finalize from disk in `asyncio.to_thread`. This also removes the big stop message and the R7 mechanism, which sfn26 only blocks at the API. The Rust native CSV shows the pattern.
3. **Use a crash-tolerant container** (R5): MKV, fragmented MP4 or segments, on both paths (ring buffer recommendation 2, backed by p11). Test FreeMoCap's reader on it.
4. **Choose the rate and quality on purpose** (R3, R4). Use one rate per group from the negotiated mode, and record it in the info JSON. Use an explicit quality-based encoder (PyAV/libx264 CRF, or a configured hardware encoder), or store the camera's own MJPEG (1–2% of a core per camera on Windows, `usb_cameras/docs/mjpeg_passthrough_summary.md`). If time in the file matters, write per-frame PTS at encode time from a better stamp, not by re-encoding afterwards.
5. **Fix the remaining latent bugs.** Match finished messages by recording UUID. Bound `wait_for_recording_save` for a live but hung process. Skip the finished message for a 0-frame recorder. Let `_recording_requested` recover after a failed stop (the last two on sfn26).
6. **Before recommending the Rust backend,** run open check 7. If the deadlock is confirmed, drain (or quiet) stderr during the recording. Also: end the recording cleanly when one camera fails instead of killing every ffmpeg; refuse `apply()` and exposure sweeps while recording; route frames by camera ID; record the negotiated rate.
7. **Restore playback of fallback-codec files on sfn26**, for example by wiring up `browser_stream.py`.
8. **Audio** (R11, Python path): store `inputBufferAdcTime` and overflow counts. Then either mux with an explicit offset, or document the alignment rule for consumers.
9. **FreeMoCap compatibility before moving to sfn26:** update its `create_worker` calls, and any HTTP client that stops with `GET`.

## 8. Open checks

Done on 2026-11-09: real-scene size and GOP, encoder identity, and header rate against the real rate. Still open:

1. **A long recording** (10–60 min): bitrate and GOP over time, the stop-call time and the event-loop stall at 1, 10 and 60 min.
2. **A machine without NVENC**: which MFT it gets, and with what defaults.
3. **Kill-flag ending**: raise inside a camera loop mid-recording; check that the videos play and the CSVs are missing.
4. **R7 and R8 on `development`**: start twice, then stop (which recording gets finalized?). Kill one camera process externally, then close the group (does it hang?).
5. **Linux and macOS**: which codec `resolve_writer_fourcc` actually picks.
6. **The 0 fps fallback**: start a recording within 1 s of connecting under DirectShow.
7. **sfn26 Rust backend, in a worktree of `upstream/sfn26` on Windows:**
   - Record for at least 2 minutes and check whether stop stalls (stderr deadlock).
   - Kill one camera mid-recording and check whether the other cameras' videos survive.
   - `ffprobe` the files for GOP, profile, header rate and size.
8. **Calibration paths not exercised**: a realtime pipeline during a calibration recording (`charuco_observations_realtime.pkl`), and whether FreeMoCap picks up a `.web.mp4` or a Rust `native_timestamps.csv` as an extra camera or CSV.

## 9. Method and evidence

| Part | What was done | Where |
| --- | --- | --- |
| Code review | Recorder, camera loop, camera group, timestamps, pubsub, worker registry and API at `55f851e4`, plus OpenCV `cap_msmf.cpp` (4.12.0) | REPORT.md §2–§8, Sources |
| Verification pass | An independent sub-agent checked every first-draft claim against code, result files and OpenCV. It overturned three conclusions (the R7 symptom, the R8 hang, and the −1 frame-rate fallback) and corrected a quote and the pickle size. The R8 and fallback corrections were re-checked by hand | REPORT.md header |
| Synthetic encode test | 300 synthetic 720p frames through skellycam's writer paths, probed with `ffprobe`; no camera used | `gop_test.py`; REPORT.md §4 |
| Real recordings | Five 3-camera recordings (A–E) through the real skellycam and FreeMoCap servers over HTTP, all under `camlock`. Every output file was inventoried and probed, frame 100 was extracted, and one file per run was re-probed by hand | `results/real_recording_20261109/` (RESULTS.md, `per_video_table.md`, `run*/`, `scripts/`); raw media in `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/real_recording_20261109/` |
| Upstream check | Workflow `wf_2558fc98-76a`: 6 finding groups, a Rust overview and a main/development-streaming delta, each verdict adversarially verified, then a completeness critic. The R6, R7, R8, stats and `/shutdown` fixes and the Rust stderr mechanism were re-read by hand | `results/upstream_check_20261109/` |
| Earlier studies reused | Ring buffer study (record cost, crash container, disk fill, e2e sizes); timestamps review (meaning of the grab stamp, local-time bug) | `research/frame_ring_buffer/docs/frame_ring_buffer_report.md`; `research/usb_cameras/docs/skellycam_timestamps_review.md` |

**Limits.**
- **Windows only.** One machine (Gerald, NVENC). Linux and macOS outcomes are from code.
- **Short recordings.** 15–60 s takes; nothing longer than a minute.
- **Clean stops only.** No failure ending was triggered in the real runs; the hard-kill result comes from the ring buffer study's p11.
- **Synthetic versus real frames.** The GOP test and the ring buffer sizes used synthetic frames. Real scenes showed the encoder can undershoot its target (C930e).
- **Static-only upstream check.** Nothing was built or run on `sfn26`, `main` or `development-streaming`. Every effect on files there is **inferred** unless the code is identical to what was measured.

## Notes on sources

Where the sources disagree, this report uses the later or better-supported statement:

1. **Size per camera-hour** (REPORT.md §1, §4, §5 and R4 corrected to match on 2026-11-09; RESULTS.md, a dated run record, still has the old figures). REPORT.md and RESULTS.md §9 gave ~13.3 GB at 720p and ~31 GB (30.8) at 1080p per camera-hour. Those divide the file size by the header duration, which is ~9% shorter than real time. Per hour of real recording at 30 fps the measured files give **~12.1 GB at 720p** (C930e ~10.7) and **~27.9 GB at 1080p**: ffprobe `format.size` ÷ `nb_frames` × 108,000. For example, run A C922 is 201,815,143 B ÷ 1,803 = 111,933 B per frame, and run C C922 is 258,317 B per frame (`run*/…_ffprobe_*.json`). The earlier code-based estimate that RESULTS.md marked "refuted, too low" (12.4 / 28 GB) is in fact close on a real-time basis.
2. **Header bias range.** REPORT.md and RESULTS.md say 9.4–10.8%. `per_video_table.md` gives 9.3% at the low end: run D C930e, 32.787 fps against 30.001 fps (+2.79 fps).
3. **Stats JSON block count.** RESULTS.md §3 says "all 12 stage stats" are empty. Run A's `_stats.json` (raw folder) has 13 empty blocks: `framerate_stats`, `frame_duration_stats`, `inter_camera_grab_range_ms` and 10 stage blocks. REPORT.md's "13" is right.
4. **Median interval.** REPORT.md §5 says a 32 ms median (31.25 fps). RESULTS.md measured a 32.1 ms median and 1/median = 31.1–31.2 fps. This report uses RESULTS.md.
5. **Superseded REPORT.md statements, resolved by its later sections:** the §5 fallback "normally the mode rate" → 0.0 under DirectShow; §4 "1 bit/pixel whatever the content" → refined by the C930e undershoot; §4 "GOP 30 at 30 fps" → floor(header fps).
6. **Rust GOP.** The `verdict_table.md` codec rows say "keyint 250 plus scenecut". `completeness_critique.md` B2 resolves scenecut as **off** under ultrafast. This report uses B2.
7. **R7 on the Rust path.** The votes split. This report uses critique B1: fixed in the shipped build; the unguarded dispatcher is reachable only from the unshipped standalone binary.
8. **Stderr deadlock timing.** REPORT.md says "plausibly within a minute". Critique B4 estimates 10–30 s on Windows (4 KB pipe) and a few minutes on Linux/macOS (64 KB). Both are inferred. This report quotes B4.
9. **`browser_stream.py`.** One `verdict_table.md` codec observation says playback "now streams … through browser_stream.py". The L5 row and critique C4 say it has no production caller. `git grep browser_stream upstream/sfn26 -- 'skellycam/*.py'` finds no use outside `tests/`, so this report follows L5 and C4.
