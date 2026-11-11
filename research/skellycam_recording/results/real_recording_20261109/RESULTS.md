# Real skellycam recordings on Gerald, 2026-11-09

Checks of `research/skellycam_recording/REPORT.md` against real recordings made with the physical cameras, by driving the real servers over HTTP as a UI would. skellycam code: `dom/research` @ `55f851e4`.

Labels: **measured** (a file in this folder supports it), **code** (read from source), **inferred** (reasoned, not tested).

Raw media (videos, extracted frames, crops) are in `C:\Users\Dom\Documents\skellycam-raw\skellycam_recording\real_recording_20261109\` and are not in the repo. Text results are here: `run*_drive.json` (every request, response and timing), `run*_server.log`, and `run*/` (inventory, CSV heads, ffprobe JSON, analysis JSON). `per_video_table.md` has the full per-video table.

## 1. Runs and commands

All camera access went through `camlock` (no waiting: tickets 34–41, lock acquired after 0.0 s each time). No driver, registry or device changes were made. All five runs used three cameras.

| Run | Server | Path | Mode | Length | Mic | Recording folder (under skellycam-raw) |
| --- | --- | --- | --- | --- | --- | --- |
| A | skellycam | `POST /skellycam/camera/group/all/record/start` | 1280x720 | 60 s | 6 (C930e mic, MME) | `runA_skellycam_720p/runA_720p_3cam/` |
| B | **FreeMoCap** | `POST /freemocap/calibration/recording/start` (calibration recording) | 1280x720 | 40 s | forced -1 by FreeMoCap | `runB_freemocap_calibration/2026-11-09_09-46-44_calibration/` |
| C | skellycam | as A | 1920x1080 | 20 s | none | `runC_skellycam_1080p/runC_1080p_3cam/` |
| D | skellycam | as A, with `OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS=0` | 1280x720 | 20 s | none | `runD_skellycam_720p_hwoff/runD_720p_hwoff/` |
| E | skellycam | as A, plus a loaded-DLL probe 5 s into the recording | 1280x720 | 15 s | none | `runE_skellycam_720p_moduleprobe/runE_720p_moduleprobe/` |

Driver: `scripts/drive_recording.py`. It starts the server (`python -m skellycam` or `python -m freemocap`), polls `/health`, then calls `POST /skellycam/camera/detect`, `GET …/microphone/detect` and `POST …/group/apply`. The apply request sends only `camera_id`, `camera_index`, `camera_name` and `resolution`; everything else is left at its default (writer `X264`, capture `MJPG`, framerate -1, exposure MANUAL -7). It then waits 15 s, as a user watching the preview would, starts the recording, sleeps, stops with `GET /skellycam/camera/group/all/record/stop`, calls `DELETE …/group/close/all`, and finally `GET /shutdown`. Exact commands, from the repo root in Git Bash:

```
# preflight (enumerate + open the 3 cameras together at 720p MJPG for 4 s)
uv run --script research/usb_cameras/tools/camlock.py --timeout-s 1800 -- 'C:\…\skellycam\.venv\Scripts\python.exe' research/skellycam_recording/results/real_recording_20261109/scripts/preflight.py 046D:0843 1532:0E05 046D:085C

# A
uv run --script research/usb_cameras/tools/camlock.py --timeout-s 1800 -- 'C:\…\skellycam\.venv\Scripts\python.exe' "$R\scripts\drive_recording.py" --server skellycam --mic 6 --root '<raw>\runA_skellycam_720p' --name runA_720p_3cam --out-json "$R\runA_drive.json" --server-log "$R\runA_server.log"
# B (see §5 for the PYTHONPATH overlay)
PYTHONIOENCODING=utf-8 PYTHONPATH="$SP\skellytracker_6f78af48;$SP\pydeps" uv run --script …camlock.py --timeout-s 1800 -- '…\skellycam\.venv\Scripts\python.exe' "$R\scripts\drive_recording.py" --server freemocap --duration-s 40 --root '<raw>\runB_freemocap_calibration' --out-json "$R\runB_drive.json" --server-log "$R\runB_server.log"
# C
PYTHONIOENCODING=utf-8 uv run --script …camlock.py --timeout-s 1800 -- … drive_recording.py --server skellycam --width 1920 --height 1080 --duration-s 20 --root '<raw>\runC_skellycam_1080p' --name runC_1080p_3cam …
# D
PYTHONIOENCODING=utf-8 uv run --script …camlock.py --timeout-s 1800 -- … drive_recording.py --server skellycam --hw-transforms-off --duration-s 20 --root '<raw>\runD_skellycam_720p_hwoff' --name runD_720p_hwoff …
# E
PYTHONIOENCODING=utf-8 uv run --script …camlock.py --timeout-s 1800 -- … drive_recording.py --server skellycam --module-probe --duration-s 15 --root '<raw>\runE_skellycam_720p_moduleprobe' --name runE_720p_moduleprobe …

# analysis (no cameras), per recording
.venv/Scripts/python.exe research/skellycam_recording/results/real_recording_20261109/scripts/analyze_recording.py <recording folder> <results subfolder> <raw>\frames
.venv/Scripts/python.exe scripts/per_video_table.py   # from the results folder
```

`$R` is this folder, `<raw>` the skellycam-raw folder above, and `$SP` the session scratchpad. `analyze_recording.py` runs `ffprobe -show_streams -show_format -count_packets`, then `ffprobe -show_frames -show_entries frame=pict_type,key_frame,pkt_size`, reads the CSVs, extracts frame 100 with `ffmpeg -vf select=eq(n\,100)`, and reads the WAV with `wave`.

## 2. Cameras and modes (measured)

| Camera | VID:PID | skellycam id / DSHOW index | Mode used | Notes |
| --- | --- | --- | --- | --- |
| Logitech C930e | 046D:0843 | `0100` / 3 | MJPG 1280x720 and 1920x1080, 30 fps | Exposure reads back as -5 when the default -7 is requested (info JSON) |
| Logitech C922 | 046D:085C | `1c81` / 1 | same | Behind the Kiyo's hub (shared USB 2.0 link) |
| Razer Kiyo Pro | 1532:0E05 | `fbf5` / 2 | same | **Worked in all six sessions** (preflight plus A–E, 09:38–09:52). No hang and no replug needed |
| Generic 4C4A:4A55 | — | `b395` / 0 | not used | Detected. Left out because it shares the C922's hub |

- **The capture backend is DSHOW, not MSMF.** skellycam's `determine_opencv_camera_backend()` picks `CAP_DSHOW` on Windows (log: "Determined OpenCV backend: DSHOW (ID: 700)"). DSHOW indices differ from MSMF's (the preflight's MSMF enumeration listed 4 NDI virtual cameras as well). (**measured**)
- The Kiyo and the C922 streamed 1080p MJPEG together over the shared link without errors: 602/602 frames each in run C. (**measured**)
- `group/apply` took 10.0–12.9 s (camera open). In the preflight, a raw MSMF open took 23 s (C930e), 31 s (C922) and 6 s (Kiyo). (**measured**)

## 3. Output tree (measured; runs A and B, from `run*/…_inventory.txt`)

| Path, relative to `<recording_name>/` | A (normal, mic) | B (FreeMoCap calibration) | REPORT §2 |
| --- | --- | --- | --- |
| `<name>_info.json` | 2,689 B | 2,714 B | matches |
| `synchronized_videos/<name>.id-<cam_id>.idx-<cam_index>.mp4` ×3 | 179–202 MB each | 119–135 MB each | matches; `idx` is the DSHOW index |
| `synchronized_videos/<name>.audio.wav` | 10.7 MB | **absent** (mic forced to -1) | matches |
| `synchronized_videos/<name>.audio_timestamps.json` | 53 KB | **absent** | matches |
| `synchronized_videos/synchronized_videos_README.md` | 378 B | 378 B | matches; text is as quoted ("…the same moment in time…") |
| `…/timestamps/<name>_timestamps.csv` | 1803 rows × **103 columns** | 1203 × 103 | matches |
| `…/timestamps/<name>_stats.json` | 1,613 B | 1,637 B | present, but **every statistic is `{}`** (below) |
| `…/timestamps/<name>_stats.txt` | 3,024 B | 3,041 B | present, full tables |
| `…/timestamps/camera_timestamps/<name>.camera<cam_id>.timestamps.csv` ×3 | 1803 rows × **27 columns** | 1203 × 27 | matches |
| `*.web.mp4` | none | none | none created by recording |
| anything else | nothing | nothing (no `output_data/`) | — |

- **Info JSON**: name, directory, UUID, mic index, the full start timestamp block (UTC/local/ISO/perf_counter_ns, and so on), and each camera's full `CameraConfig` with rotation as a name (`"NO_ROTATION"`). The configs are the values **read back from the capture**, not the request: `framerate: 0.0` for every camera (requested -1) and C930e `exposure: -5` (requested -7). (**measured**)
- **`_stats.json` is broken**: `framerate_stats`, `frame_duration_stats`, `inter_camera_grab_range_ms` and all 12 stage stats are `{}`. Cause: the stats are `np.recarray` and `RecordingTimestampStats.to_json` falls back to `default=lambda o: o.__dict__`, which is empty for a recarray (`recording_timestamp_stats.py:123-143`). The `.txt` and the HTTP stop response have the numbers. (**measured** + **code**)
- **Per-camera CSV local time is 5 h off**: the first row reads `2026-11-09T04:40:05.524223-05:00` for a frame taken at 09:40:05 local. The multiframe CSV reads `2026-11-09T09:40:05.524532-05:00` (correct). (**measured**)
- **Audio** (run A): WAV is 2 ch, 16-bit, 44,100 Hz, 2,686,976 samples = 60.929 s. Sidecar keys: `audio_file, mic_device_index, sample_rate, channels, chunk_size (1024), total_chunks (2624), total_samples, start_perf_counter_ns, end_perf_counter_ns, duration_seconds (61.019), mean/std_chunk_duration_seconds, timebase_mapping, chunk_timestamps_perf_ns`. Alignment, from perf_counter: the audio start stamp is 40.8 ms after the info JSON's start stamp, the first chunk callback is 139 ms after the audio start stamp, the audio starts **1.022 s before the first recorded frame**, and it ends **85.9 ms (about 2.6 frames) before the last frame**. Chunk callbacks come in bursts (median gap 0.16 ms, max 51 ms). The sample count (60.929 s) and the stamp span (61.019 s) differ by 90 ms. (**measured**)

## 4. Per-video format (measured; full table in `per_video_table.md`)

| Run | Camera | Size | Profile | B-frames | Frame types | GOP | Header fps | Achieved fps (CSV) | Frames (video = CSV) | Header duration / real span | Mbit/s | Bits/pixel |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | C930e | 720p | Constrained Baseline L4.1 | 0 | 57 I / 1746 P | 32 | 32.890 | 29.991 | 1803 | 54.82 / 60.08 s | 26.18 | 0.864 |
| A | C922 | 720p | CB L4.1 | 0 | 57 I / 1746 P | 32 | 32.971 | 29.992 | 1803 | 54.68 / 60.08 s | 29.52 | 0.972 |
| A | Kiyo | 720p | CB L4.1 | 0 | 57 I / 1746 P | 32 | 32.933 | 29.992 | 1803 | 54.75 / 60.08 s | 29.41 | 0.969 |
| B (calib) | C930e | 720p | CB L4.1 | 0 | 38 I / 1165 P | 32 | 32.881 | 30.014 | 1203 | 36.59 / 40.05 s | 26.04 | 0.859 |
| B (calib) | C922 | 720p | CB L4.1 | 0 | 38 I / 1165 P | 32 | 32.839 | 30.014 | 1203 | 36.63 / 40.05 s | 29.53 | 0.976 |
| B (calib) | Kiyo | 720p | CB L4.1 | 0 | 38 I / 1165 P | 32 | 32.927 | 30.014 | 1203 | 36.54 / 40.05 s | 29.51 | 0.972 |
| C | C930e | 1080p | CB L5.0 | 0 | 19 I / 583 P | 33 | 33.241 | 30.000 | 602 | 18.11 / 20.03 s | 68.55 | 0.995 |
| C | C922 | 1080p | CB L5.0 | 0 | 19 I / 583 P | 33 | 33.230 | 30.001 | 602 | 18.12 / 20.03 s | 68.67 | 0.997 |
| C | Kiyo | 1080p | CB L5.0 | 0 | 19 I / 583 P | 33 | 33.249 | 30.000 | 602 | 18.11 / 20.03 s | 67.84 | 0.984 |
| D (HW env off) | C930e / C922 / Kiyo | 720p | CB L4.1 | 0 | 19 I / 583 P | 32 | 32.79 / 32.84 / 32.89 | 30.001 | 602 | 18.3 / 20.03 s | 26.09 / 29.54 / 29.58 | 0.864 / 0.976 / 0.976 |
| E | C930e / C922 / Kiyo | 720p | CB L4.1 | 0 | 15 I / 454 P | 32 | 32.91 | 30.000 | 469 | 14.25 / 15.60 s | 25.06 / 29.63 / 29.50 | 0.826 / 0.977 / 0.973 |

All files: `h264`, `yuv420p`, `has_b_frames=0`, constant frame rate (`r_frame_rate == avg_frame_rate`), `time_base = 1/(fps×1000)`, encoder tag "AVC Coding". ffprobe `nb_frames` equals the CSV row count in every file, and `validate_recording` passed in every run.

- **GOP = floor(header fps)**: 32 at a header rate of 32.8–33.0 fps, 33 at 33.2. That is one I-frame per header-second, no B-frames, and every frame in between is P. (**measured**)
- **Bitrate target = floor(header fps) × W × H**: 32×1280×720 = 29.49 Mbit/s and 33×1920×1080 = 68.43 Mbit/s. The C922 and Kiyo hit it within 0.3% at 720p and 1% at 1080p. The **C930e undershoots by 11–15% at 720p** (25.1–26.2 Mbit/s, 0.83–0.86 bit/pixel) on this real scene, and hits it at 1080p. Bits per pixel per frame on target is floor(fps)/fps ≈ 0.97–0.99, not 1.0, because the header fps isn't an integer. (**measured**; the undershoot being content-driven is **inferred**)
- **Header rate vs real time**: the header rates are **2.8–3.25 fps (9.4–10.8%) above** the achieved rate, so **each video plays about 9–10% fast** (54.7–54.8 s of video for 60.08 s of capture). The three cameras' header rates differ by up to 0.08 fps (A: 32.890 / 32.933 / 32.971), so after 60 s their header durations differ by 0.135 s (about 4 frames). (**measured**)
- **Why the header rate is high.** Two effects stack:
  1. The real frame intervals are skewed. Under DSHOW lockstep they run about 32 ms most of the time, with a regular ~48 ms step every 12–13 frames (histogram in the analysis below), so 1/median(interval) = 31.1–31.2 fps while 1/mean = 30.0 fps.
  2. The stamp placement that REPORT §5 describes: `previous_tik` is reset at line 117, so samples miss the post-retrieve work. Rebuilding the loop's sample from the CSV stamps (`post_retrieve[k] − post_shm[k−1]` or `post_record[k−1]`) gives 1/median = 32.3–33.0 fps at 720p and 33.1–34.2 fps at 1080p, which brackets the measured header rates (32.84–32.97 and 33.23–33.25).

  (**measured** stamps; the split between the two effects is **inferred**)
- **Interval pattern** (run A, all three cameras): 1,803 frames, median 32.1 ms, mean 33.3 ms, about 120 intervals of 43–50 ms, one of about 102 ms and one of about 3 ms per camera (a late frame followed by a catch-up). (**measured**)

## 5. Calibration recording (FreeMoCap path)

**How FreeMoCap makes a calibration recording** (**code**, `freemocap` repo `development` @ `5632778a`):
- The UI (`freemocap-ui/src/store/slices/calibration/calibration-thunks.ts`, `startCalibrationRecording`) sends `POST /freemocap/calibration/recording/start` with `{calibrationRecordingDirectory: "<recordingsRoot>/<getTimestampString()>_calibration", calibrationTaskConfig}`. `getTimestampString()` gives, for example, `2026-11-09_09-46-44_GMT-5`.
- `calibration_router.py:start_calibration_recording`:
  - `to_recording_info()` builds `RecordingInfo(recording_directory=<parent>, recording_name=Path(dir).stem, mic_device_index=-1)`. **The microphone is always off.** `.stem` would cut a name at its first dot.
  - `_reject_if_recording_directory_not_empty` returns 409 if `synchronized_videos/` already holds a file with a suffix in `VIDEO_EXTENSIONS`.
  - Then `FreemocapApplication.start_recording_all`, which is **skellycam's own `CameraGroupManager.start_recording_all_groups`**.
  - For each live realtime pipeline it publishes `CalibrationRecordingState(is_active=True)` and switches the pipeline to Charuco-only mode.
- There are no other camera settings: the cameras keep whatever the group was applied with. Writer, codec, overlay and timestamps are skellycam's, unchanged.
- `POST /freemocap/calibration/recording/stop` calls `stop_recording_all_groups()` (skellycam), publishes `is_active=False`, then **immediately launches the posthoc calibration pipeline**. If a realtime pipeline is running, its `CharucoRecorderNode` writes `<recording>/output_data/charuco_observations_realtime.pkl` on that signal (`charuco_recorder_node.py`), an extra folder that normal recordings don't have.
- FreeMoCap's server also mounts skellycam's camera router at `/skellycam/camera/…`, and its package code is byte-identical to `55f851e4`: I diffed every `.py` in `freemocap/.venv/Lib/site-packages/skellycam` (installed from 777b058c) against `git show 55f851e4`, with 0 differences. (**measured**)

**What I ran** (run B):
- I started FreeMoCap's own server (`freemocap\.venv\Scripts\python.exe -m freemocap`) and applied the group through `/skellycam/camera/group/apply`.
- I started the recording through **`POST /freemocap/calibration/recording/start`** with `{"calibrationRecordingDirectory": "<raw>\runB_freemocap_calibration/2026-11-09_09-46-44_calibration"}` and the default task config. The response was `{"success": true, "message": "Recording started"}`, and the log line was "Starting calibration recording: RecordingInfo(name=2026-11-09_09-46-44_calibration …".
- After 40 s I **stopped through `GET /skellycam/camera/group/all/record/stop`, not `/freemocap/calibration/recording/stop`**, because the latter starts a calibration solve, which was out of scope. Both end in the same `CameraGroupManager.stop_recording_all_groups()`, so the files on disk are the same (**code**).
- No realtime pipeline was created, so no `CalibrationRecordingState` messages went out and no `charuco_observations_realtime.pkl` could be written; that path was not exercised.
- Deviation from the UI: my folder name has no `_GMT-5` suffix. It is a name-only difference.

**Blocker worked around: FreeMoCap's venv is stale against its source.**
- `freemocap -m freemocap` first exited with `ModuleNotFoundError: skellytracker.core.detectors.object_detectors.keypoint_bbox`. The venv has skellytracker from the fork branch `dom/pipeline-metrics-rebased` @ 5081c3a5 (synced Aug 12), while the source expects freemocap/skellytracker `main`.
- Without touching either venv or any source, I overlaid via `PYTHONPATH`:
  - `git archive 6f78af48` (upstream/main, the branch `uv.lock` names) of skellytracker into the scratchpad;
  - `filelock` (`uv pip install --target <scratchpad>\pydeps --no-deps`);
  - `skelly-synchronize` at the locked commit `0231c41a` (same way).
- With that overlay the app imported and served. One benign side error remains: `LogRecordModel has no attribute 'from_dict'` in the log-queue consumer (skellylogs skew). The local `../skellytracker` and `skellytracker-hw-and-ep-work` checkouts did not work: they lack `RTMPoseBodyDetector.canonical_mapping_path`.

**Files produced** (**measured**, `runB/2026-11-09_09-46-44_calibration_inventory.txt`): the same tree as a normal skellycam recording (§3), with these differences:
- no `audio.wav` and no `audio_timestamps.json` (mic forced to -1);
- `mic_device_index: -1` in the info JSON;
- the folder name ends `_calibration`.

Videos (§4 row B): H.264 Constrained Baseline, GOP 32, no B-frames, header 32.84–32.93 fps against 30.01 achieved, and 0.86–0.98 bit/pixel. Those are the same as normal recordings. **The overlay is burned into the calibration videos too** (`camera.id0100.idx3.fr540` at top left), so any ChArUco corner in that strip is covered. Calibration was not solved, by instruction.

## 6. Overlay (measured; images in `<raw>\frames\`, not committed)

- Frame 100 of every video in A–E has `camera.id<cam_id>.idx<cam_index>.fr<N>` burned in at the top left, for example `camera.id0100.idx3.fr550`.
- It is light lavender text, BGR (255,210,210), with a thick black outline: `cv2.putText` at (10, 40), FONT_HERSHEY_SIMPLEX scale 0.8, outline thickness 8 (`opencv_get_frame.py:79-89`). It spans about x 5–340 and y 15–50 px, the **same pixel size at 720p and 1080p**.
- **`N` is the connection frame number, not the recording frame index**: 550 = 450 (the first recorded frame's `connection_frame_number`) + 100.
- Only the overlaid video exists. No clean copy is written.

## 7. Encoder identity (measured)

- **Run D** (`OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS=0` on the server, inherited by the camera processes) gave the same profile, GOP and bitrate as A and E. **That test can't decide anything**: in OpenCV 4.12.0 `cap_msmf.cpp` the env var is read only by the capture reader (line 956-959). The writer hard-codes `MF_READWRITE_ENABLE_HARDWARE_TRANSFORMS, true` (line 2620). I read the file from `raw.githubusercontent.com/opencv/opencv/4.12.0`; it is in the scratchpad, not kept. The bitrate line (2593) and the `fps*1000/1000` frame-rate lines (2607, 2616) are confirmed in the same file. (**code**)
- **Run E** listed the DLLs loaded by every `python.exe` 5 s into the recording. All three camera processes (parent = server) had **`nvEncMFTH264x.dll` and `nvEncodeAPI64.dll`** loaded from the NVIDIA driver store. Microsoft's software encoder `mfh264enc.dll` was not loaded. **So on Gerald the MSMF sink writer uses the NVIDIA H.264 Encoder MFT (NVENC, RTX 3070).** (**measured**, `runE_drive.json` → `module_probe`)
- `ffmpeg -c:v h264_mf -v verbose` on the same machine lists 'NVIDIA H.264 Encoder MFT' as the hardware MFT and 'H264 Encoder MFT' (Microsoft) as the software one. (**measured**, console only)
- The GOP-32 / Constrained Baseline / CBR-to-target behaviour above is NVENC MFT's default. A machine without an NVIDIA GPU would get another MFT, with possibly different defaults (**inferred**). REPORT's `gop_test.py` almost certainly ran on NVENC too, since the writer always enables hardware MFTs (**inferred**).
- The log shows OpenCV's FFmpeg writer tried first for every camera. The codec probe failed with "Failed to load OpenH264 library: openh264-1.8.0-win64.dll", and the real writer's attempt about 0.7 s later failed with "Incorrect library version loaded". Each then fell through to MSMF. (**measured**, `runA_server.log`)

## 8. Other observations

- **The grab stamp is not the frame-arrival time under DSHOW**: `during_frame_grab` has a median of 0.046 ms, while `during_frame_retrieve` has a median of 26.5 ms (run A `_stats.txt`) out of a 33 ms period. The waiting happens inside `retrieve()`, so the CSV's main timestamp (the grab midpoint) marks when the loop started waiting, not when the frame arrived. The 0.27 ms "inter-camera grab sync" then measures loop lockstep, not capture sync. (**measured** durations; interpretation **inferred**)
- **Start/stop call times with 3 cameras**: start 0.84–1.05 s. Stop 0.78–0.89 s (20 s recordings), 1.17 s (40 s) and 1.47 s (60 s), so the stop call grows with recording length. (**measured**)
- **`GET /shutdown` is a hard kill on Windows**: `os.kill(getpid(), SIGTERM)` ends the process with exit code 15 before it replies (client sees WinError 10054). `main()`'s `finally` (`worker_registry.shutdown_all()`, "Done!") never runs. This happens on both the skellycam and FreeMoCap servers. The camera groups had already been closed, and no stray `python.exe` remained. (**measured**)
- Run A's `runA_server.log` is full of `UnicodeEncodeError` logging errors because stdout went to a file under cp1252. Runs B–E set `PYTHONIOENCODING=utf-8`. Harmless to the recording.

## 9. REPORT.md claims

| REPORT claim | Verdict | Evidence |
| --- | --- | --- |
| §1/§3: each camera process encodes its own video during capture; CSVs, stats and info JSON written by the main process after stop | CONFIRMED | Log: "Camera xxxx creating recorder…" in camera processes; info JSON, CSVs and stats saved in the 09:41:06 finalize after the stop (`runA_skellycam_logfile.log`) (**measured**) |
| §1/§4: Windows encoder is Media Foundation H.264 | CONFIRMED, and now identified | FFmpeg/OpenH264 fails, MSMF takes over; the MFT is **NVIDIA H.264 Encoder MFT** (`nvEncMFTH264x.dll` loaded in all camera processes) (**measured**) |
| §1/§4: fixed 1 bit/pixel (bitrate = (UINT32)fps×W×H) | CONFIRMED with refinements | The target is floor(**header** fps)×W×H, so ≈0.97–0.99 bit/pixel per frame; C922/Kiyo on target within 0.3–1%; **C930e 11–15% below target at 720p** on a real scene (0.83–0.86 bit/pixel) (**measured**) |
| §4: "MF holds the bitrate whatever the content" | PARTLY REFUTED | C930e at 720p undershoots by 11–15% in 4 runs; the other cameras and 1080p hold (**measured**) |
| §4 size table (720p30 27.6 Mbit/s ≈ 12.4 GB/h; 1080p30 62.2 Mbit/s ≈ 28 GB/h) | REFUTED as an estimate (too low) | The bitrate follows the inflated header rate: 29.5 Mbit/s at 720p (≈13.3 GB/camera-hour) and 68.4 Mbit/s at 1080p (≈30.8 GB/camera-hour) with real 30 fps cameras (**measured** bitrate; per-hour **inferred**) |
| §1/§4: not I-frame only; Constrained Baseline, I+P, one I-frame per second, no B-frames | CONFIRMED | 57 I / 1746 P (A); GOP 32 at header 32.9 fps, 33 at 33.2; `has_b_frames=0`; CB L4.1 (720p) and L5.0 (1080p) (**measured**) |
| §4: GOP 30 at 30 fps / 60 at 60 fps | CONSISTENT (rule = floor(header fps)) | 32 and 33 observed for header rates 32.x and 33.2; 60 fps not tested |
| §4: OpenCV FFmpeg tries libopenh264 first and fails for lack of `openh264-1.8.0-win64.dll` | CONFIRMED | Log messages quoted in §7 (**measured**) |
| §4: which MFT ran was not identified; HW transforms enabled | RESOLVED | NVENC MFT (§7). The env var can't disable it for the writer (hard-coded, line 2620) (**measured** + **code**) |
| §1/§2/R2: one video per camera, overlay `camera.id…idx…fr…` burned in, no clean copy | CONFIRMED | §6; 3 videos per recording, overlay in every run including the calibration recording (**measured**) |
| §2: `.web.mp4` only from playback, not from recording | CONFIRMED (recording side) | No `.web.mp4` in any run (**measured**). Playback-triggered creation, and whether FreeMoCap would count one as a camera: NOT TESTED (FreeMoCap filters by suffix only, so `.web.mp4` passes its `VIDEO_EXTENSIONS` check; **code**) |
| §2: folder and file layout | CONFIRMED | §3 inventory matches exactly; nothing extra (**measured**) |
| §2: per-camera CSV has 27 columns | CONFIRMED | 27 columns in all 15 per-camera CSVs; multiframe CSV has 103 (**measured**) |
| §2: info JSON contents (name, dir, UUID, mic, start timestamp, full configs, rotation as a name) | CONFIRMED | §3. Note: configs are read back from the capture (framerate 0.0, C930e exposure -5) (**measured**) |
| §2: README text claims frame k is the same moment in every camera | CONFIRMED (text present) | `synchronized_videos_README.md` (**measured**) |
| §2: stats files `_stats.json` / `_stats.txt` | CONFIRMED present; NEW BUG | `_stats.json` has `{}` for every statistic (recarray → `o.__dict__`) (**measured** + **code**) |
| §3.1: start call ≈ 1 s | CONFIRMED | 0.84–1.05 s with 3 cameras (**measured**) |
| §3.3: stop time grows with length (not measured before) | PARTLY TESTED | 0.78–0.89 s (20 s), 1.17 s (40 s), 1.47 s (60 s), 3 cameras (**measured**); 10/60 min not tested |
| §1/§5/R3: CFR header rate is a pre-recording estimate, biased high | CONFIRMED, quantified | +2.8 to +3.25 fps (9.4–10.8%) above achieved, in all 15 videos; videos play about 9–10% fast (**measured**) |
| §5: the bias comes from the stamp placement (`previous_tik` reset at line 117) | CONFIRMED, plus a second cause | Line 117 overwrites line 82's reset (**code**). A rebuilt sample brackets the header rate. The median of a skewed interval distribution (32 ms with periodic 48 ms) adds about +1.1 fps on its own (**measured** stamps; split **inferred**) |
| §5: cameras in one group can get different header rates | CONFIRMED | A: 32.890 / 32.933 / 32.971; header durations differ by 0.135 s after 60 s (**measured**) |
| §5: if the loop slows during recording the header overstates further | NOT TESTED | No slowdown occurred: achieved 29.99–30.01 fps in every run |
| §5: fallback `config.framerate` is "normally the mode rate (30 or 60)" | REFUTED for DSHOW on Gerald | The extracted `framerate` is **0.0** for all three cameras under DSHOW (info JSON, apply response) (**measured**). The fallback itself (start < 1 s after connect) was not triggered; what MSMF does with fps 0 is NOT TESTED |
| §5: header durations can't be checked from file size | CONSISTENT | Bitrate tracks floor(header fps)×W×H, so the per-frame size hides the rate error (**measured**) |
| §5 audio: 44.1 kHz, ≤2 ch, int16, 1024-sample blocks, all in RAM | CONFIRMED (format) | WAV 2 ch / 16-bit / 44,100 Hz; sidecar chunk_size 1024 (**measured**) |
| §5 audio: start stamp before the stream exists; chunk stamps are callback times; overflow flags only logged | CONFIRMED (stamps) | First callback 139 ms after the start stamp; chunks delivered in bursts (median gap 0.16 ms, max 51 ms); sample count and stamp span differ by 90 ms (**measured**). Overflow handling NOT TESTED |
| §5 audio: starts before the first recorded frame, stops before the last ~2 frames | CONFIRMED | Starts 1.022 s before frame 0; ends 85.9 ms (≈2.6 frames) before the last frame (**measured**) |
| §5: CSV timestamp is the grab midpoint | CONFIRMED, with a caveat | Under DSHOW, grab takes 0.05 ms and retrieve 16–27 ms, so the midpoint is when waiting started, not frame arrival (§8) |
| §8: per-camera CSV local time has the double-offset bug; multiframe CSV is correct | CONFIRMED | 04:40:05 vs 09:40:05 local (**measured**) |
| §8: codec probe at every recording start | CONFIRMED | Two FFmpeg attempts per camera per start in the log (probe, then writer) (**measured**) |
| §8: API defaults nest `<ts>/<ts>/` | NOT TESTED | Both fields were always sent |
| §1/§6/R1: unclean ending loses timestamps; hard kill → 0-frame MP4 | NOT TESTED | Only clean stops were made |
| §7 R5–R9, R11 (other than the audio items above) | NOT TESTED | — |
| §7 R10: finalize blocks the event loop | NOT TESTED | (Stop-call times only, above) |
| §9.1 real-scene size, GOP and MFT | DONE | §4, §7 (1080p for 20 s rather than 10 min) |
| §9.2 header rate against real rate, 3 cameras | DONE | §4 |
| §9.3–9.6 | NOT TESTED | — |

## 10. Device state

- The Kiyo Pro answered in all six sessions (09:38–09:52), and no replug is needed. The generic 4C4A:4A55 was detected but not used.
- No camera needed a replug, and nothing was changed on the devices.
