# How skellycam saves recordings today

> **Start with the consolidated report: [docs/skellycam_recording_report.md](docs/skellycam_recording_report.md).** This file is the detailed working review, with every step and correction.

Written 2026-11-09. Code read at `dom/research` @ `55f851e4`, with no uncommitted changes under `skellycam/`. The recorder, camera loop, camera group, timestamp and pubsub code is identical to `23ccbf20`, the commit the frame ring buffer study benchmarked, so that study's measurements apply unchanged. Paths are relative to the repo root.

Labels, as in the other studies: **measured** (a result file supports it), **code** (read from the source), **inferred** (reasoned, not tested).

**Verification.** An independent sub-agent checked every claim in the first draft against the code, the cited result files and OpenCV's `cap_msmf.cpp`. It overturned three conclusions: the R7 symptom, the R8 hang, and the −1 frame-rate fallback. It also corrected a mis-quoted measurement (§3.2) and the pickle size (R9). This version includes those corrections. The R8 and fallback corrections were re-checked by hand.

**Runs.** Two sets of new measurements, both 2026-11-09:
- **A small encode test:** 300 synthetic 720p frames through skellycam's own writer paths, probed with `ffprobe` (`gop_test.py` in this folder; videos not kept). It ran while other timing captures were using the cameras, so no camera was touched.
- **Five real recordings, made later the same day once the cameras were free:** a sub-agent ran the real skellycam server, driven over HTTP, with 3 cameras (C930e, C922, Kiyo Pro), all under `camlock`, and checked every output file. The runs:
  - A: a normal 720p recording, 60 s, with the microphone;
  - B: FreeMoCap's calibration-recording path, 720p, 40 s;
  - C: 1080p, 20 s;
  - D: with `OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS=0`;
  - E: a probe of the encoder DLLs loaded mid-recording.

  Full results: `results/real_recording_20261109/RESULTS.md`, with the per-video table in `per_video_table.md` and the scripts in `scripts/`. The raw videos are outside git in `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/real_recording_20261109/`. Every recording finalized and passed `validate_recording`. One file per run was re-probed by hand, and so was the empty `_stats.json`.

Every other measured figure comes from existing result files. Where the real recordings changed a claim made from code, the text below says so.

## 1. Summary

- **Each camera process encodes its own video, synchronously, inside the capture loop.** The main process writes everything else (timestamp CSVs, stats, info JSON) only after stop, from per-frame metadata that each camera sends in one pickled message. (**code**)
- **If a recording ends any way other than a clean stop, it has no timestamps.** A kill-flag shutdown lets the writers close, so the videos are probably playable, but no CSV or info JSON is written. A hard kill leaves an MSMF `.mp4` with 0 readable frames. (**code**; the hard-kill result is **measured**, `frame_ring_buffer/prototypes/results/p11_crash_container.md`)
- **The videos are constant frame rate, and the header rate is wrong.** Each camera writes its own estimate, measured *before* the recording started. With real cameras running at 30.0 fps, all 15 videos had headers of **32.8–33.25 fps (+9–11%)**, so they **play about 9–10% fast**: 54.7 s of video for 60.1 s of capture. The three cameras of a group also got three different header rates. Pauses, resets and slowdowns are invisible in the file. Real timing exists only in the CSVs. (**measured**, real recordings)
- **On Windows (Gerald) the encoder is NVIDIA's H.264 MFT, through Media Foundation, at a fixed bitrate.** OpenCV sets `bitRate = (UINT32)fps × W × H`; with the truncation that is floor(header fps) × W × H per second. ffprobe reports 29.5 Mbit/s at 720p and 68.4 Mbit/s at 1080p, measured on the files' too-short timeline. That is about **12.1 GB per real camera-hour at 720p and 28 GB at 1080p**. One camera (C930e) came in 11–15% under target at 720p. FFmpeg/OpenH264 is tried first and fails for a missing DLL. (**measured**, real recordings + `nvEncMFTH264x.dll` loaded in every camera process)
- **The video is not I-frame only.** Windows writes Constrained Baseline, I + P frames, no B-frames, with an I-frame every floor(header fps) frames, i.e. about once per second (32 frames at a 32.9 fps header, 33 at 33.2). The Linux PyAV/libx264 path writes High profile with B-frames and an I-frame every 250 frames. (**measured**: real recordings for Windows, `gop_test.py` for Linux)
- **Only one video per camera is written, and it is the annotated one.** The debug overlay (the text `camera.id…idx…fr…` at the top left, where the number is the connection frame number, not the recording index) is drawn into the same buffer that is recorded. No clean copy exists. This was confirmed in real recordings, including the FreeMoCap calibration recording. The only other video file skellycam can create is a `.web.mp4` playback sidecar, transcoded from that same annotated file (§2). (**code** + **measured**)
- **A FreeMoCap calibration recording is an ordinary skellycam recording** in a folder ending `_calibration`, with the microphone forced off: same files, formats, GOP, header bias and overlay (§4a). (**code** + **measured**)
- **Later upstream work (§11).** `upstream/sfn26` (2026-11-07) fixes R6, R7, R8, the empty stats JSON and the `/shutdown` hard-kill. The default Python path still burns in the overlay, writes the same fast CFR headers at a fixed bitrate, and writes timestamps only after a clean stop. A new opt-in Rust backend records clean MJPEG→libx264 video at the true mode rate and streams its timestamps. In code it has a likely ffmpeg stderr deadlock on longer recordings, and one camera's failure destroys every camera's video. (**code**, static check)
- **Several latent bugs** can make every later stop finalize the *previous* recording, write one camera's timestamps under another camera's file name, or hang shutdown after a camera process dies (§7).

## 2. What ends up on disk

Folder names come from `skellycam/system/default_paths.py:6-8`, file names from `skellycam/core/recorders/videos/recording_info.py:37-112` and `parse_video_filename.py:13`.

```
<recording_directory>/<recording_name>/
├── <recording_name>_info.json                  RecordingInfo + every camera config        (after stop)
└── synchronized_videos/
    ├── <recording_name>.id-<cam_id>.idx-<cam_index>.mp4   one per camera (.avi only for the XVID/MJPG fallbacks)  (during)
    ├── <recording_name>.audio.wav                         only if a microphone was chosen  (at stop)
    ├── <recording_name>.audio_timestamps.json             audio sidecar                    (at stop)
    ├── synchronized_videos_README.md                                                       (after stop)
    └── timestamps/
        ├── <recording_name>_timestamps.csv       one row per multiframe: means across cameras + spread stats
        ├── <recording_name>_stats.json / _stats.txt
        └── camera_timestamps/
            └── <recording_name>.camera<cam_id>.timestamps.csv   27 columns per frame, one file per camera
```

- **One video per camera, overlay included.** `retrieve()` decodes into `frame_rec_array.image[0]` (`opencv_get_frame.py:71`). The overlay is drawn into that same array (lines 79-83). The array then goes, unchanged, to shared memory and to `record_frame` (`opencv_camera_loop.py:96-105`). The repo has no other `putText` call on the capture path and no second recorder, so there is no clean file and no separate annotated file.
- **A possible `.web.mp4` sidecar.** When the playback view opens a video whose codec isn't browser-playable (in practice the `mp4v`, XVID or MJPG fallbacks), `_ensure_web_compatible` writes `<stem>.web.mp4` next to it in `synchronized_videos/`. It uses PyAV/libx264 at CRF 18 and is cached for later views (`api/http/playback/playback_router.py:114-139`, `utilities/transcode_to_h264.py`). It is a re-encode of the annotated file. skellycam's own playback listing skips `.web` stems, but another reader of the folder (FreeMoCap) might count it as an extra camera (**inferred**, not checked).
- **Per-camera CSV** (`create_camera_csvs.py:45-103`): recording and connection frame numbers; the main timestamp (`timestamp.perf_counter_ns.ns`, the midpoint of the pre- and post-`grab()` stamps); seconds from recording start; UTC; local ISO 8601; interval and rate from the previous frame; every lifecycle stamp (grab, retrieve, shm copy, record) relative to recording start; and the derived durations.
- **Multiframe CSV** (`create_multi_frame_csvs.py`): the mean of each timestamp across cameras, the per-frame grab spread between cameras, and mean, median, std, range and CV for every lifecycle column.
- **Info JSON** (`recording_info.py:77-86`): name, directory, UUID, mic index, start timestamp, and the full `CameraConfig` of each camera, with rotation written as a name.
- **Stats JSON** (`_stats.json`): every statistic block is written as `{}`. The stats are `np.recarray`, and `to_json`'s fallback `default=lambda o: o.__dict__` (`recording_timestamp_stats.py:143`) serializes them as empty objects. The `_stats.txt` file has the numbers (**measured**: 13 empty blocks in a real recording).
- **Real recordings matched this layout exactly**, with no extra or missing files and no `.web.mp4`. The multiframe CSV has 103 columns (**measured**).
- **README**: a fixed text saying each frame index "represent[s] the same moment in time" in every camera (`recording_finalizer.py:27-31`). The timestamps review (P3) shows frame *k* of two cameras can be up to about one period apart.

## 3. How a recording runs

### 3.1 Start: `POST …/group/all/record/start`
`camera_router.py:136-153` → `CameraGroup.start_recording` (`camera_group.py:183-213`):
1. Pause all cameras and wait until every one reports paused.
2. Set `first_recording_frame_number = max(frame_count) + 3` and `last = -1` (line 192).
3. Publish `RecordingInfoMessage`.
4. If a microphone is selected, start `AudioRecorder` in the API process (lines 197-205).
5. Wait 10 ms, then unpause and wait until no camera is paused.

Each camera handles the message in its loop's update checks, which run even while paused (`handle_recording_updates.py:15-48`):
- `VideoRecorder.create` **probes the codec by writing a one-frame temp file**, for every camera at every recording start (`fourcc_codec_helpers.py:95-196`). It then opens the writer and sets `recording_in_progress`.
- The camera then busy-waits until every camera is recording (lines 45-47).

**Measured:** the start call takes 0.93–1.09 s with 5 synthetic cameras (`frame_ring_buffer/baseline/results/e_e2e_*.json`, `start_recording_call_s`), and 0.84–1.05 s with the 3 real cameras (`results/real_recording_20261109/run*_drive.json`).

### 3.2 Every frame
`opencv_camera_loop.py:89-105`:
1. Decide `should_record_frame` from the frame number (`camera_orchestrator.py:80-94`).
2. Copy the frame into shared memory for the UI and FreeMoCap.
3. `record_frame` (`video_recorder.py:87-109`):
   - checks the frame number is consecutive and the shape matches;
   - rotates the image if a rotation is set;
   - calls `video_writer.write()`, stamped before and after;
   - appends a copy of the 632-byte frame metadata to a Python list.

The image written is the one `opencv_get_frame.py:79-83` has already drawn the overlay text onto.

Because of lockstep, a slow write delays every camera, not just its own. **Measured** cost (ring buffer report, `c_record.md`), 5 processes at 60 fps on MSMF H.264: `record_frame` median 0.99 ms at 720p, 2.17 ms at 1080p.

### 3.3 Stop: `GET …/group/all/record/stop`
`camera_group.py:215-238`:
1. Pause all cameras.
2. Stop audio, which writes the WAV and its sidecar.
3. Set `last_recording_frame_number = max(frame_count) + 3` and `first = -1`.
4. Unpause.
5. `finalize_recording` (lines 317-379) polls the `RECORDING_FINISHED` topic every 100 ms until every camera has reported.

On the camera side, at `frame_number == last` the camera releases the writer and publishes one `RecordingFinishedMessage` carrying **the whole per-frame metadata list** (`handle_recording_updates.py:50-59`; `handle_video_recording_loop.py:27-36`).

### 3.4 Finalize (main process, after all cameras report)
`RecordingFinalizer.finalize_recording` (`recording_finalizer.py:53-67`):
1. Write the info JSON.
2. `process_and_save_recording_timestamps`: check that every camera has the same frame numbers and one timebase mapping, then write the per-camera CSVs, the multiframe CSV and the stats.
3. Write the README.
4. `validate_recording` (lines 126-208):
   - each video opens and its first frame has the expected shape;
   - `CAP_PROP_FRAME_COUNT` is equal across cameras;
   - each CSV has as many rows as its video has frames.
5. The VFR/audio remux is **commented out** (line 63).

**Measured:** the whole stop call took 1.97–2.19 s for 5 cameras × 30 s (`e_e2e_*.json`, `stop_recording_call_s`). How that scales with recording length was not measured. The finalize code is synchronous Python, with per-frame loops at `process_and_save_recording_timestamps.py:43-65`, `process_recording_timestamps.py:22-24` and `create_camera_csvs.py:66-68`. It runs on the FastAPI event loop without yielding, so the UI stream presumably stalls for the whole finalize (**inferred**).

## 4. Codec and container

`DEFAULT_WRITER_FOURCC = "X264"` (`camera_config.py:29`). `resolve_writer_fourcc` (`fourcc_codec_helpers.py:155-196`) tries the requested fourcc first, then `X264, H264, avc1, X264_PYAV`, then `mp4v, XVID, MJPG`, and keeps the first that passes its probe. For OpenCV codecs the probe writes one frame and needs a file of at least 100 bytes. For `X264_PYAV` it only checks that PyAV has a libx264 encoder (lines 84-104).

| Platform | What is chosen | Settings | Status |
| --- | --- | --- | --- |
| Windows | `X264` passes the probe. OpenCV's bundled FFmpeg has no libx264, so the MSMF writer takes it. MSMF maps any fourcc it doesn't know to H.264. | Bitrate `(UINT32)fps × width × height`, i.e. 1 bit/pixel (fps is truncated first, so 29.97 → 29); frame rate `fps×1000/1000`; sample time `+= 1/fps` per frame (`cap_msmf.cpp`, `CvVideoWriter_MSMF::open` and `write`) | **code**; MSMF as the backend is **measured** (`bench_c_record.py` logs `getBackendName()`, and `c_record.md` shows `X264/MSMF` on every row) |
| Linux (pip OpenCV) | `X264`, `H264` and `avc1` usually fail, so `X264_PYAV` → `PyavVideoWriter` | libx264, CRF 18, preset fast, yuv420p, `rate = int(round(fps))`, `pts = frame index` (`pyav_video_writer.py:14-28`) | **code**; the platform outcome is **inferred** |
| macOS | `avc1` (VideoToolbox) is the likely pick | OpenCV AVFoundation writer | **inferred** |
| Any, last resort | `MJPG` in `.avi` | Large files. Chromium can't play them, so the playback view transcodes a `.web.mp4` sidecar on first view (§2) | **code** |

**Real recordings (measured, `results/real_recording_20261109/per_video_table.md`).** Three cameras, five runs, 15 videos, all on Gerald:

| Mode | Profile | Frame types | GOP | Header fps (real 30.0) | Bitrate | Bits per pixel per frame |
| --- | --- | --- | --- | --- | --- | --- |
| 1280×720 (runs A, B, D, E) | Constrained Baseline L4.1, `has_b_frames=0` | I + P only | 32 | 32.79–32.97 | C922 and Kiyo 29.4–29.6 Mbit/s; C930e 25.1–26.2 | 0.97–0.98; C930e 0.83–0.86 |
| 1920×1080 (run C) | Constrained Baseline L5.0 | I + P only | 33 | 33.23–33.25 | 67.8–68.7 Mbit/s | 0.98–1.00 |

- **The GOP is floor(header fps) frames**, about one second of the file's own timeline.
- **The bitrate target is `(UINT32)fps × W × H`**, so 32 × W × H at a 32.9 fps header. Two of the three cameras hit it within 1–3%. The C930e's scene came in 11–15% under it, so MF does not pad every scene to the target. That corrects the "whatever the content" reading taken from the synthetic tests.
- **The encoder is the NVIDIA H.264 Encoder MFT.** Run E listed the modules loaded in each camera process mid-recording: `nvEncMFTH264x.dll` and `nvEncodeAPI64.dll` (NVENC, RTX 3070) were loaded, and Microsoft's `mfh264enc.dll` was not. Run D could not have switched it off: in OpenCV 4.12 the `OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS` variable only reaches the capture reader (`cap_msmf.cpp:959`), and the writer hard-codes hardware transforms on (`cap_msmf.cpp:2620`). The GOP, profile and rate control above are NVENC MFT defaults. A machine without an NVIDIA GPU gets a different MFT, possibly with different defaults (**inferred**). The synthetic `gop_test.py` run almost certainly used NVENC too.
- **Capture is DirectShow, not MSMF:** `grab()` took 0.05 ms and `retrieve()` 16–27 ms. That matches the timestamps review's account of what the CSV grab-midpoint stamp means.

**GOP structure, synthetic test (measured, `gop_test.py`, 2026-11-09).** 300 frames of a moving gradient and disc at 1280×720, written through `resolve_writer_fourcc("X264")` and `PyavVideoWriter`, probed with `ffprobe` frame types:

| Path | Profile | Frame types (300 frames) | Keyframes | B-frames | Bitrate |
| --- | --- | --- | --- | --- | --- |
| Windows: cv2 → MSMF (FFmpeg first tried `libopenh264`, failed, and fell through) | Constrained Baseline | 10 I, 290 P at 30 fps | Every 30 frames at 30 fps, every 60 at 60 fps: **one per second** | None | 27.7 Mbit/s at 30 fps, 55.8 Mbit/s at 60 fps (targets 27.6 and 55.3) |
| Linux: `PyavVideoWriter` (libx264, CRF 18, preset fast) | High | 2 I, 76 P, 222 B | Frames 0 and 250 (libx264's default `keyint=250`) | Yes (`has_b_frames=2`) | 1.29 Mbit/s |

On Windows, OpenCV's FFmpeg writer is tried first. It remaps `X264` to `avc1` and tries `libopenh264`, which fails only because `openh264-1.8.0-win64.dll` is not installed ("Failed to load OpenH264 library"). On a machine that has that DLL, FFmpeg/OpenH264 would probably take the recording instead of MSMF, with a different bitrate and GOP (**inferred**).

Neither path is I-frame only. Neither writer sets a GOP: OpenCV's MSMF writer sets no codec-API properties, and it enables hardware transforms (`cap_msmf.cpp:2620`). The structure above is therefore that encoder's default (NVENC on Gerald, identified in the real recordings). Consequences:
- Sequential reading (how FreeMoCap reads) is unaffected.
- Random access to frame *k* means decoding from the previous I-frame: up to 1 s of frames on Windows, up to 249 frames on Linux. With the Linux file's B-frames, decode order also differs from display order.
- Seeking by `CAP_PROP_POS_FRAMES` depends on the demuxer's accuracy, which was not tested here.
- On Linux the same content is about 21× smaller, because CRF is quality-targeted while MSMF pads to its fixed bitrate.

**Size on Windows.** The ring buffer e2e runs wrote 258,648 B per frame at 1080p (0.998 bit/pixel) and 115,734 B per frame at 720p (1.005 bit/pixel) (`e_e2e_1080p_memcpy_ui.json`, `e_e2e_720p_memcpy_ui.json`, total bytes ÷ 5 cameras ÷ recorded frames), on synthetic frames with noise. The real recordings sit at the target for two cameras and below it for the C930e (above).

ffprobe's bitrate is per second of the file's own timeline, which is about 9% shorter than real time (§5). Disk use per **real** hour therefore comes from bytes per frame × 108,000 frames (30 fps × 3600 s), or equivalently file size ÷ capture span. The target per frame is floor(header fps)/header fps × W × H ≈ 0.97 bit/pixel, so real files come out slightly *smaller* than a 1 bit/pixel × 30 fps estimate. (Corrected 2026-11-09; this table first gave per-file-hour figures of 13.3 GB and 31 GB. The overall report's author caught it.)

| Mode | Bitrate on the file timeline (ffprobe) | Real-time bitrate | Per real camera-hour |
| --- | --- | --- | --- |
| 720p30 | ~29.5 Mbit/s (C930e ~26) | ~26.9 Mbit/s (C930e ~23.9) | **~12.1 GB** (C930e ~10.7); e.g. run A C922 201,815,143 B ÷ 60.08 s |
| 1080p30 | ~68.4 Mbit/s | ~62 Mbit/s | **~27.9 GB**; run C 155.5 MB ÷ 20.03 s |
| 1080p60 | not recorded | — | ~56 GB (**inferred**: about W × H bits per frame × 216,000 frames) |

The ring buffer report already found that the free disk fills in 54 min at 5×1080p (`p12_disk_sustained.md`).

## 4a. FreeMoCap calibration recordings

How FreeMoCap makes one (**code**, read in `C:\Users\Dom\GitHub\freemocap\freemocap`; see RESULTS.md for file references):
- The UI sends `POST /freemocap/calibration/recording/start` with `calibrationRecordingDirectory = <root>/<YYYY-MM-DD_HH-MM-SS_GMT-5>_calibration`.
- FreeMoCap forces the microphone to −1, refuses a folder that already holds videos, and calls skellycam's own `start_recording_all_groups`. It sends no camera settings of its own.
- `POST /freemocap/calibration/recording/stop` stops through skellycam and then immediately starts a posthoc calibration solve. If a realtime pipeline is running, the stop also writes `output_data/charuco_observations_realtime.pkl`.

What it produces (**measured**, run B). The test started recording through FreeMoCap's start endpoint and stopped through skellycam's `…/group/all/record/stop`, the same `stop_recording_all_groups` call minus the solve. On request, no calibration was solved. The result:
- **An ordinary skellycam recording.** The tree is identical to §2, minus the WAV and audio sidecar; the info JSON says `mic_device_index: -1`.
- **The same formats**: Constrained Baseline, GOP 32, header about 32.9 fps for a real 30.0 fps, bitrate as in §4.
- **The overlay is burned into every frame**, which matters for ChArUco detection near the top-left corner (R2).
- **Not exercised:** no realtime pipeline was running, so `charuco_observations_realtime.pkl` was not produced. The test's folder name lacked the UI's `_GMT-5` suffix (name only).
- **FreeMoCap's own venv is stale.** Its server fails at import (`skellytracker…keypoint_bbox` missing). The test ran it by putting current skellytracker, `filelock` and `skelly-synchronize` on `PYTHONPATH`, without changing either environment. The skellycam installed in FreeMoCap's environment is byte-identical to `55f851e4`.

## 5. Time inside the files

- **The rate in the header** is `1 / median(last ≤1000 intervals)`, measured by each camera process before the recording (`opencv_camera_loop.py:80-84`, passed in at `handle_recording_updates.py:39-43`, used at `video_recorder.py:80`).
  - **Measured on real cameras:** the header was 2.79–3.25 fps (9.3–10.8%) above the achieved 30.0 fps in all 15 videos. The video duration was 91% of the capture span (for example, 54.82 s against 60.08 s). Two causes stack:
    - **Stamp placement (code).** `current_tik` is taken right after grab and retrieve (line 80), but `previous_tik` is reset at the end of the loop (line 117), after `put_frame`, recording and `check_framerate_reset`. Each sample is therefore the period minus the post-grab work.
    - **DirectShow delivery pattern (measured).** The intervals are mostly 32 ms with a 48 ms step every 12–13 frames, so the *median* is 32 ms (31.25 fps) even though the mean is 33.3 ms. On its own that adds about +1.1 fps. How the bias splits between the two causes is **inferred**.
  - Each camera computes its own value, so the cameras of one lockstep group get different header rates: 32.890 / 32.971 / 32.933 in run A (**measured**).
  - The value is measured *before* recording adds the write to every loop iteration. If the loop slows during the recording, the header overstates the rate further and the video plays fast. At 5×1080p MJPEG the loop achieved 53.6 fps during recording (ring buffer report). The header rate was not logged.
  - With fewer than 30 intervals measured (a recording started within about a second of connecting), the rate falls back to `config.framerate`. In the camera process that is the *extracted* config, whose `framerate` is the backend's `CAP_PROP_FPS` (`opencv_extract_config.py:24`; `create_cv2_video_capture.py:84-88`). Under DirectShow that value is **0.0 for every camera** (**measured**, the extracted configs in the real recordings' info JSON), so the fallback rate on Windows is 0. The fallback was not triggered in the tests. With fps 0, MSMF would compute a zero bitrate and a zero frame rate. What the writer then does was not tested.
  - Because of the same stamp placement, `check_framerate_reset` fires only when the shm copy plus the write exceed 66.7 ms for more than 30 frames in a row: a slow-writer trigger, not a slow-camera one.
  - The 1 bit/pixel file sizes can't reveal a wrong header rate: MF targets about W×H bits per frame whatever the rate.
- **Gaps the file can't show:** a pause during a recording (the UI asks the user to stop first; the API doesn't), and `check_framerate_reset` releasing and reopening a camera mid-recording (`opencv_camera_loop.py:150-170`). Frame numbers stay consecutive in both cases, so the CFR file closes up the gap.
- **The CSV timestamp** is the grab midpoint. For what that does and doesn't mean, see `usb_cameras/docs/skellycam_timestamps_review.md` P1–P3. FreeMoCap ignores it anyway and pairs frames by index.
- **The dormant remux** (`video_audio_remuxer.py`) would put real gaps into the file. It sets a 1/90000 time base and gives each frame a PTS from the CSV's grab midpoint (lines 67-82, 105-108); `rate=30` (line 69) is only the nominal stream rate. But it has costs:
  - it decodes and re-encodes every video with libx264, a second lossy pass that is slow;
  - its PTS come from the grab midpoint, with the limits in the timestamps review;
  - it writes MP4 content back under the original name, even when that name is `.avi` (lines 28, 39).

### Audio
`audio_recorder.py`; started and stopped at `camera_group.py:197-205` and `220-224`.
- **Capture:** a PortAudio callback stream in the API process: 44.1 kHz, up to 2 channels, int16, 1024-sample blocks. All of it stays in RAM until stop (about 635 MB per hour in stereo).
- **Timing:** the start stamp is `perf_counter_ns()` taken before the `InputStream` is even constructed (line 68; `start()` is at line 78), so it includes the device-open time. Each chunk is stamped with the host time when its callback runs (line 113), which is at least one block (23 ms) after its first sample. PortAudio's `time_info.inputBufferAdcTime` is ignored. Overflow flags are only logged (lines 108-109), so the sample count is not a verified clock.
- **Alignment:** audio starts while the cameras are paused, before the first recorded frame, and stops before the last ~2 frames. **Measured** in run A: audio started 1.02 s before the first frame and ended 86 ms (about 2.6 frames) before the last, and the chunk stamps arrive in bursts. Nothing aligns the WAV to the videos (the remux that would is off), so a consumer has to line up the sidecar's `start_perf_counter_ns` with the camera CSVs itself.

## 6. What survives a failure

| Event | Videos | CSVs and info JSON | Status |
| --- | --- | --- | --- |
| Clean stop | Closed and validated | Written | code |
| Kill flag (any exception in a camera loop, the UI relay or a FreeMoCap node sets it; ring buffer report P1) | Each loop exits and `finally` releases the writer (`opencv_camera_loop.py:124-127`). The process gets 3 s before `terminate()` (`worker_registry.py:161-207`), so the files are probably playable. | **Not written.** The metadata goes out on `RECORDING_FINISHED`, but nothing finalizes it | code; playability **inferred** |
| One camera's `VideoRecorder.create` fails at start (probe or writer open) | It raises and sets the kill flag. That releases every peer waiting at `handle_recording_updates.py:45-47` while it holds a recorder with 0 frames | Each such peer's `finally` raises from `RecordingFinishedMessage.__post_init__` (`pubsub_topics.py:45-46`) and sends no message: a second traceback. The worker's own `finally` still sets `closed` (`opencv_camera_worker_method.py:73-82`) | code |
| A camera process dies without running its `finally` (segfault, external kill) | — | `CameraManager.close()` calls `orchestrator.close()` (`camera_manager.py:98`) *before* any join/terminate step, and that wait has no timeout (`camera_orchestrator.py:111-117`), so close hangs. If the dead camera still shows `recording_in_progress`, `CameraGroup.close()` first calls `stop_recording()`, and its `pause(await_paused=True)` hangs too | code; trigger **inferred** |
| Hard kill of a camera process, crash, or power loss | MSMF `.mp4`: 0 of 300 frames readable. MJPEG-in-MKV kept 298–359 | Not written | **measured** (`p11_crash_container.md`) |
| `validate_recording` fails | Kept | Written; the HTTP call returns 500 | code |
| Rotation set to 90° or 270° through the API during a recording | `_validate_image_shape` raises → kill-flag row above | — | code (the UI asks the user to stop first) |
| 30 failed grabs in a row | The frame number repeats, `_validate_frame_number` raises → kill-flag row | — | code (ring buffer report) |

## 7. Problems

| # | Issue | Effect | Status |
| --- | --- | --- | --- |
| R1 | **Timestamps exist only after a clean stop** | Every unclean ending loses all timing, the info JSON, and the frame count that validation would check against | code |
| R2 | **Overlay burned into the recording** | Every frame carries text over roughly a 40 px strip at the top left (`opencv_get_frame.py:79-83`). Anything detected there (ChArUco corners, a hand, a marker) is corrupted, and no clean copy exists | code |
| R3 | **The CFR header rate is a pre-recording estimate, per camera, biased high** | Videos play about 9–10% fast (header ~32.9 fps for 30.0 real), and the cameras in one group disagree. The fallback is 0 fps under DirectShow | measured |
| R4 | **Fixed-bitrate H.264 on Windows, ~1 s GOP, encoder defaults** | Large files (~12 GB per real camera-hour at 720p, ~28 GB at 1080p) and no quality setting; the bitrate is tied to the wrong header rate in R3. GOP, profile and rate control are the defaults of whichever MFT is picked (NVENC on Gerald), so they differ between machines | measured |
| R5 | **A non-crash-tolerant container** | A hard kill loses the whole MSMF MP4 | measured |
| R6 | **Camera order is assumed to match by position** | Timestamps are packed in orchestrator order (`camera_group.py:322-325`, `process_recording_timestamps.py:14-24`) but written by `enumerate(camera_configs.keys())` (`create_camera_csvs.py:45-47`). After `update_camera_settings`, `self.configs` is rebuilt from the request (`camera_group.py:171-181`, `290-314`), and the request can be a **subset**: `_get_configs_by_group` keeps only the requested cameras (`camera_group_manager.py:91-100`), and the UI sends only the selected ones (`skellycam-ui/src/store/slices/cameras/cameras-thunks.ts:109-115`). Deselect camera 0 of [0, 1, 2] and re-apply, and the next recording writes camera 0's timestamps under camera 1's name, camera 1's under camera 2's, and none for camera 0. The info JSON and validation then cover 2 cameras | code; UI flow **inferred** |
| R7 | **A stale `RecordingFinishedMessage` shifts every later stop by one recording** | Starting while already recording (nothing guards against it) closes the old recorder and publishes its messages (`handle_recording_updates.py:32-35`), which nobody reads. At the next stop, `finalize_recording` reads one message per camera and exits once every slot is filled (`camera_group.py:328-362`). The stale messages come first, so it **silently finalizes the previous recording**: its CSVs and info JSON, written with the current configs, and its name in the HTTP response. The new messages stay queued, so every later stop is one recording behind until the group is recreated | code |
| R8 | **A dead camera process hangs close** (§6) | `orchestrator.close()` and `pause()` wait on status flags with no timeout, before any terminate step | code; trigger **inferred** |
| R9 | **All metadata in one message at stop** | About 694 B per frame when the list is pickled (632 B of data; checked by the verifier with `pickle.dumps` of a 2,000-item list), so ~75 MB per camera for an hour at 30 fps. The ring buffer study measured a ~387 ms + 127 ms camera-loop stall for 36,000 frames (PROVISIONAL), and lockstep stalls every camera with it | measured (per frame) / inferred (per hour) |
| R10 | **Finalize blocks the event loop** | The UI and websocket freeze while timestamps are processed; the time grows with recording length | inferred |
| R11 | **Audio is unaligned and loosely stamped** (§5) | A/V sync is left to the consumer; the ADC time and overflow counts are thrown away | code |

## 8. Smaller code issues

- **Codec probe every time.** Each camera writes and deletes a temp video at every recording start. There is no timeout on Windows (`fourcc_codec_helpers.py:116-118`). This is part of the ~1 s start.
- **A reused name overwrites silently.** `video_file_path_from_camera_config` returns any existing file with the same stem, whatever its extension (`recording_info.py:95-100`). Reusing a recording name overwrites the old video. If the old extension differs, the new stream goes into a container that doesn't match its codec.
- **Path properties create folders.** `full_recording_path`, `videos_folder`, `timestamps_folder` and `camera_timestamps_folder` all call `mkdir` when read (`recording_info.py:37-63`).
- **The API defaults nest.** `StartRecordingRequest` defaults `recording_directory` to `…/recordings/<timestamp>` and `recording_name` to `<timestamp>` (`camera_router.py:37-49`), so a client that sends neither gets `<ts>/<ts>/`. The UI sends both.
- **The two CSVs disagree on local time.** The per-camera CSV uses `convert_perf_counter_ns_to_local_iso8601`, which has the double-offset bug (timestamps review §4). The multiframe CSV builds local time from UTC seconds with `datetime.astimezone()` (`create_multi_frame_csvs.py:48-52`), which is correct.
- **`validate_recording` check 1 doesn't fail on a missing file.** It stores the path whether or not the file exists (`recording_finalizer.py:140-145`). A missing video only shows up afterwards as "Failed to open".
- **`_stats.json` statistics are empty** (§2): `default=lambda o: o.__dict__` can't serialize `np.recarray` (`recording_timestamp_stats.py:143`).
- **`GET /shutdown` hard-kills the server on Windows** (exit code 15, no HTTP reply, the cleanup block never runs). This was seen in the real-recording runs, on both the skellycam and FreeMoCap servers. The camera groups had already been closed there, so no recording was affected (**measured**).
- **`video_frame_metadata` is never cleared.** It is fine only because each recording gets a new `VideoRecorder`.
- **`finish_recording` returns `None`, and one caller ignores it** (`handle_recording_updates.py:35`). It is harmless only because the variable is overwritten on the next line.

## 9. Checks still to run

Done 2026-11-09 (real recordings): real-scene file size and GOP, the encoder identity, and the header rate against the real rate. Still open:

1. **A long recording** (10–60 min) to check the bitrate and GOP over time and the finalize scaling (check 5).
2. **A machine without NVENC**, to see which MFT and defaults it gets.
3. **Kill-flag ending:** raise inside a camera loop mid-recording; check the videos play and the CSVs are missing.
4. **R7 and R8:** start twice and then stop (check which recording gets finalized); kill one camera process externally, then close the group (check for the hang).
5. **Finalize scaling:** stop-call time and event-loop stall at 1, 10 and 60 min.
6. **Linux and macOS:** which codec `resolve_writer_fourcc` actually picks.
7. **sfn26 Rust backend (§11):** in a worktree of `upstream/sfn26`, run a Rust-backend recording of at least 2 minutes on Windows, to see whether it stalls at stop (stderr deadlock). Also kill one camera mid-recording and check whether the other cameras' videos survive; and `ffprobe` the files (GOP, profile, header rate, size).

## 10. Suggested changes, in order

1. **Stop drawing the overlay on recorded frames** (R2). Draw it on the UI copy only. Small.
2. **Write timestamps during the recording** (R1, R9, R10): append each frame's row (or a fixed-size binary record) to a per-camera file as it is written, and finalize from disk off the event loop (`asyncio.to_thread`). This removes the big message and the stale-message failure (R7) along with it.
3. **Use a crash-tolerant container** (R5): MKV, fragmented MP4, or segments. This is ring buffer recommendation 2, backed by p11. FreeMoCap's reader still needs testing on it.
4. **Choose the rate and quality on purpose** (R3, R4): one rate per group, from the negotiated camera mode; an explicit quality-based encoder (PyAV/libx264 CRF, or a hardware encoder). Or skip encoding entirely and store the camera's own MJPEG, which the MJPEG passthrough study showed costs 1–2% of a core per camera on Windows (`usb_cameras/docs/mjpeg_passthrough_summary.md`). If time in the file matters, write per-frame PTS at encode time from a better stamp (timestamps review §6), not as a re-encode afterwards.
5. **Fix the latent bugs:** match cameras by ID, not position, and finalize every camera that recorded (R6); refuse a start while recording, and match finished messages by recording UUID (R7); give `orchestrator.close()` and `pause()` timeouts that also check whether the process is alive (R8); skip the finished message when there are 0 frames.
6. **Audio** (R11): store `inputBufferAdcTime` and overflow counts, and either mux the audio with an explicit offset or document the alignment rule for consumers.

## 11. Status on later upstream branches (checked 2026-11-09)

Every finding above was re-checked against the upstream branches that move past this review's base (`23ccbf20` = `upstream/development`).
- **How:** workflow `wf_2558fc98-76a`, 100 agents. Six finding groups were checked, plus an overview of the Rust path and a check of the extra commits on `main` and `development-streaming`. Every verdict was adversarially verified (2 refuters for anything claimed changed or fixed, 1 for unchanged), and a completeness critic followed. The R6/R7/R8/L3/S2 fixes and the Rust stderr mechanism were then re-read by hand: the code with `git show`, and the `ffmpeg-sidecar` 2.5.1 source on docs.rs.
- **Static only:** nothing was built or run on those branches, so effects on files are **inferred** unless the code is identical to what was measured.
- **Full output** is in `results/upstream_check_20261109/`: `verdict_table.md` (every verdict with evidence and votes), `rust_recording_overview.md`, `completeness_critique.md`, `main_devstreaming_deltas.md` and `workflow_result.json`.

**Branches**

| Branch | Tip | Relevant? |
| --- | --- | --- |
| `upstream/sfn26` | 765bf82d, 2026-11-07 | **Yes.** The newest branch. It contains all of `cleanup-camera-api` and nearly all of `development-streaming`. It changes the Python recording path and adds an **opt-in Rust backend** (`skellycam-rust/`: openpnp-capture → one ffmpeg/libx264 process per camera). |
| `upstream/main` | 06771043 | 3 commits not in sfn26 (logging, PubSub closure, a VID/PID check). **None of them affects recording.** |
| `upstream/development-streaming` | 169caf63 | 2 commits not in sfn26 (startup-failure reporting, CI). **No effect on recording**; sfn26 has a wider version of the first. |
| All other upstream branches | — | Their tips are older than this review's base. Not checked. |

**Python/OpenCV is still the default backend on every OS.** It is `"python"` in `CameraBackendManager`, in the API request and in the UI store. Rust is chosen per camera group from a UI dropdown or the API `backend` field (`upstream/sfn26:skellycam/core/camera_group/camera_backend_manager.py:26,30`). The Rust crate is a required dependency and is bundled in the installers, but only Windows x64 has been exercised.

| Finding | sfn26, Python path (default) | sfn26, Rust path (opt-in) |
| --- | --- | --- |
| §2 layout | Same tree and names. The info JSON gains `videos`, `camera_timing` and `multiframe_timing`, which playback now reads | Same Python tree (finalized by the same `RecordingFinalizer`), **plus** `native_recording_summary.json` and `camera_timestamps/<name>.camera<id>.native_timestamps.csv` |
| R2 overlay burned in | **Unchanged** (`opencv_get_frame.py` byte-identical) | **Not applicable:** no overlay; records the camera's JPEGs, rotated losslessly |
| `_stats.json` all `{}` | **Fixed** (#141: structured arrays serialized) | Fixed (shared code) |
| Local ISO double offset | **Unchanged** | Unchanged (shared code) |
| `.web.mp4` sidecar | **Removed**: the transcoder is deleted, and playback serves files as-is. So **mp4v, XVID and MJPG fallback files no longer play in the playback view** (regression, inferred) | Same |
| Reused name overwrites | **Partly fixed:** raises on several matches or a different extension; still overwrites a same-extension file | Partly fixed: refuses an existing file, but only at the first frame, after start has already returned OK |
| C1 codec probe every start | **Unchanged** | No probe; libx264 is fixed |
| C2/R4 Windows encoder | **Unchanged:** cv2 → MSMF (NVENC here), fixed bitrate `(UINT32)fps×W×H`, ~1 s GOP, OpenCV still 4.12.0.88 | **Changed:** ffmpeg libx264, `-preset ultrafast -crf 18`, yuv420p. Inferred: I-frame every 250 frames, no B-frames, size depends on content |
| C3 Linux PyAV settings | **Unchanged** (release now closes in `finally`) | libx264 ultrafast on every OS; macOS and Linux untested |
| R5 / C4 not crash-tolerant | **Unchanged** (plain MP4) | **Unchanged** (plain MP4, no `movflags`). ffmpeg is a child process, so the outcome depends on whether it outlives the parent (inferred) |
| R3/F1 header rate biased high | **Unchanged** (same estimator) | **Changed:** the header is the negotiated integer mode rate (e.g. 30), the same for all cameras in a mode. Still CFR, so drops stay hidden |
| F2 fallback 0 fps under DSHOW | **Unchanged** | No such fallback (30 if the mode rate is ≤0) |
| F3 CFR, remux commented out | **Unchanged** | **Unchanged** |
| F4 `check_framerate_reset` | **Unchanged** | No equivalent; a 5 s frame timeout ends the camera thread (see the new risks below) |
| F5 grab-midpoint timestamp | **Unchanged** | **Changed meaning:** the CSV midpoint is (loop start + frame available)/2. The better stamp, `frame_available_ns`, is only in the native CSV |
| R1 timestamps only after a clean stop | **Unchanged** | **Partly fixed:** the native CSV is written and flushed every frame; the Python CSVs and info JSON still come only from finalize. `/shutdown` and app exit now stop and finalize Rust recordings first |
| R6 camera order by position | **Fixed** (dc578551 checks that the key sets match and reorders by camera ID; 43e2b968 recreates the group when membership changes) | Not reproducible as reported. But frames are routed to files by position, and `apply()` is not refused while recording (risk) |
| R7 stale message → previous recording | **Fixed:** a second start returns 409 (`CameraBackendManager._recording_requested`) | Fixed in the shipped build (409, plus a guard in `RustCameraGroup`). The standalone Rust binary's dispatcher has no guard |
| R8 dead camera hangs close | **Fixed:** `orchestrator.close()` only signals; bounded join, terminate and kill; pause times out after 10 s. **New caveat:** `wait_for_recording_save` has no timeout for a process that is alive but hung | No camera processes; some waits have no timeout (see the new risks below) |
| R8b zero-frame traceback | **Unchanged** symptom, better contained (only the failing group stops) | Not applicable |
| R9 one big message at stop | **Unchanged** | **Fixed:** per-frame channel and per-frame CSV rows |
| R10 finalize blocks the event loop | **Unchanged** | **Unchanged** (the Python finalize still runs on the loop) |
| R11 audio | **Unchanged** (`audio_recorder.py` untouched) | **Partly fixed:** streamed to the WAV, start stamp taken after open, per-chunk ADC time, and dropped chunks and status flags recorded. Still not muxed or aligned. Any dropped chunk makes stop raise **before** finalize |
| S1 start/stop sequence | Same core sequence, plus 409 guards and 10 s pause timeouts. **Stop is now `POST`** (GET → 405). A missing video now aborts finalize at `save_to_file`, so no files are written at all | Different mechanism: start is queued and the recorders are built at the first frame, so start reports success before anything exists |
| S2 `/shutdown` hard-kill | **Fixed:** sets the kill flag, replies 200, and waits for active video saves before SIGTERM | Fixed, and Rust recordings are stopped and finalized first |
| S3 kill flag ends recordings | **Partly fixed:** a worker with an open writer gets unlimited time to save; a camera failure stops only its own group. A websocket-relay exception still ends everything | Native threads ignore the kill flag; shutdown goes through the lifespan close |
| §4a calibration recording | Same files and formats. FreeMoCap calls skellycam internally, so the GET→POST change doesn't affect it. **Inferred:** a FreeMoCap calibration *solve* on sfn26 would fail, because FreeMoCap nodes call `WorkerRegistry.create_worker` without the arguments it now requires | Clean recording with an extra native CSV. FreeMoCap's realtime ChArUco path can't run (no `shm`/`ipc` on `RustCameraGroup`) |

**New risks on the sfn26 Rust path** (code; consequences **inferred**, untested):
1. **ffmpeg stderr deadlock.** `ffmpeg-sidecar` 2.5.1 pipes stderr and adds `-loglevel level+info`, but drains stderr only inside `wait()` (crate source, `command.rs`/`child.rs`). skellycam-rust calls `wait()` only at stop (`recorder.rs:226-239`).
   - At info level ffmpeg writes a progress line about every 0.5 s. Once the pipe buffer fills, ffmpeg stops reading stdin, and the following chain runs:
     1. `feed_frame`'s `write_all` blocks.
     2. The recording thread never sees Stop.
     3. Python's stop never returns, and `close()` hangs behind it.
     4. The unbounded frame queue grows.
   - How soon the pipe fills depends on the OS pipe buffer (small on Windows), so plausibly within a minute.
   - The only Rust recording test records about 5 s. **Highest-priority check.**
2. **One camera's capture error destroys every camera's video.** A 5 s frame timeout or a capture failure ends that camera's thread, which breaks the gatherer barrier. The dispatcher and recording thread then exit, and `VideoRecorder::drop` kills ffmpeg, leaving MP4s without a moov atom. Only the native CSVs survive. Python keeps playable videos in the same situation.
3. **Changing settings mid-recording corrupts the take.** `apply()` and the exposure-recommendation sweep are not refused while recording (UI clients are blocked, API clients aren't). A rotation change would make ffmpeg scale rotated frames into the original size.
4. **Start succeeds before any recorder exists**, so ffmpeg spawn, CSV or overwrite failures surface only at stop. If the Rust finalizer rejects a frame-count mismatch, Python then crashes on `Path('').read_text()`.

### 11.1 The Rust path's improvements in detail

Read from `upstream/sfn26` @ 765bf82d. Nothing was built or run. "Better" compares the code with what was measured on the Python path.

**No overlay.**
- **What happens instead:** capture asks openpnp-capture for MJPEG only (it filters on `FOURCC_MJPG`, `camera_thread.rs:519` ff.). The camera's compressed JPEG bytes are passed through and never decoded to pixels for recording. `skellycam-rust/src` has no drawing code.
- **Rotation is lossless:** `rotate_jpeg_lossless` rearranges the JPEG's DCT blocks and swaps width and height for 90°/270° (`dispatcher.rs:197-214`).
- **Result:** ffmpeg receives the camera's own image and decodes and re-encodes it once. The Python path has decode → overlay text → encode.
- **Caveat:** this is still a re-encode, not an MJPEG passthrough. Stored quality depends on the H.264 settings below.

**Header rate = the camera's negotiated mode rate.**
- **Source:** when the stream opens, the camera thread stores the negotiated format's integer rate, `guard.framerate = format_info.fps` (`camera_thread.rs:167, 219`). The dispatcher reads it at recorder setup, falling back to 30 if it is missing (`dispatcher.rs:376-390`), and passes it to ffmpeg as the input `-r`. Frame *n* therefore gets time *n*/fps.
- **Effect (inferred):** no pre-recording estimate, so no +9–11% bias. A 30 fps mode gets a 30 fps header, the same for every camera in that mode.
- **Caveats:**
  - Still CFR, with no real per-frame timestamps in the file. A camera that drops frames or really runs at 29.97 or 25.7 fps still gets a header of 30.
  - The negotiated rate is recorded nowhere except the video header: the info JSON keeps the requested config, e.g. −1.
  - The dispatcher measures each camera's actual fps, but that measurement is discarded.

**Quality-based encode.**
- **Command:** `recorder.rs:137-155` spawns
  `ffmpeg -f image2pipe -c:v mjpeg -s WxH -r <fps> -i pipe:0 -c:v libx264 -preset ultrafast -crf 18 -pix_fmt yuv420p -an <out>.mp4`.
- **CRF instead of a fixed bitrate:** CRF sets a quality level, so bits go where the image needs them. A static scene is cheap; motion, noise and texture cost more. CRF 18 is close to visually lossless. The file size depends on content, not on the fixed `fps × W × H` target and the wrong header rate that the Windows MSMF/NVENC path uses.
- **Preset ultrafast:** low CPU per camera (software encode on every OS), but larger files at the same CRF. In x264 it turns off B-frames, CABAC, scene-cut detection and most analysis.
- **GOP (inferred):** no `-g` is set, so x264's default applies: an I-frame every 250 frames, none at scene cuts, and no B-frames. Seeking can decode up to 249 frames.
- **Same everywhere:** the file properties no longer depend on the machine's GPU encoder.
- **Caveats:** not configurable yet (`recorder.rs:17-20`). Still a plain MP4, so not crash-tolerant.

**Timestamps streamed to a CSV every frame.**
- **The file:** `csv_writer.rs` creates `camera_timestamps/<name>.camera<id>.native_timestamps.csv` at recorder setup. It appends one row per frame and calls `flush()` each time ("Flushing on every write ensures crash-resilience", `csv_writer.rs:53-72`).
- **Columns:**
  - `frame_number`;
  - `loop_start_ns`: the wait for the next frame starts;
  - `frame_available_ns`: `Cap_hasNewFrame` first reports a frame (`camera_thread.rs:367-370`);
  - `post_jpeg_extract_ns`;
  - `pre_send_ns` and `gatherer_received_ns`: the handoff to the gatherer thread;
  - `pre_frame_record_ns` and `post_frame_record_ns`: around the write to ffmpeg's stdin.
- **Clock:** a Rust monotonic clock, shifted once to Python's `perf_counter_ns`. The alignment uncertainty is exposed as `clock_alignment_uncertainty_ns`.
- **Better than Python:**
  - Rows already flushed survive a process crash. There is no fsync, so a power loss can still lose the OS buffer.
  - There's no single large message at stop.
  - `frame_available_ns` is a more meaningful stamp than Python's midpoint around a no-op DirectShow `grab()`.
- **Caveats:**
  - The standard 27-column CSV, the multiframe CSV, the stats and the info JSON are still built only at stop (`rust_recording.py`).
  - The mapping (`pre_frame_grab ← loop_start`, `post_frame_grab ← frame_available`, `rust_recording.py:32-44`) gives the standard CSV's "main timestamp" a different meaning: it sits up to half a wait before the frame arrived, so it can't be compared directly with Python-backend CSVs. Use `frame_available_ns`.
  - `frame_available_ns` is when openpnp *reported* the frame, not when the sensor exposed it. The DirectShow delivery grid still applies.

**Better audio timestamps** (`skellycam-rust/src/recording/audio.rs`).
- **Start stamp:** taken after the stream opens and just before it starts (`audio.rs:170-174`), so it no longer includes device-open time.
- **Two stamps per chunk:** host time, plus an ADC estimate
  `adc_timestamp = host_time + (inputBufferAdcTime − currentTime) × 1e9` (`audio.rs:89-92`). The ADC estimate removes the callback delay that the Python stamps include.
- **Loss is recorded and enforced:** dropped chunks (ring buffer full or a bad callback), per-chunk PortAudio status flags, per-chunk sample counts and stream errors all go into the sidecar. Any loss makes stop fail instead of silently leaving a gap.
- **Streamed to disk:** a lock-free ring buffer feeds a writer thread, so RAM doesn't grow with recording length.
- **Caveats:**
  - Still not aligned or muxed. Audio starts before the video and stops after it, and the remux is commented out, so consumers align it themselves (now with better stamps).
  - The loss check raises inside stop's `finally`, before Python's finalize. One dropped chunk therefore means no info JSON or standard CSVs, and further starts are refused until the cameras are closed (inferred).
  - The WAV header sizes are written only at finalize, so a crash leaves a WAV that needs repair.

These improvements come with the Rust risks listed above. The worst is the possible ffmpeg stderr deadlock.

**What this means for the recommendations (§10):**
- Fixed on sfn26: R6 (§10.5), R7 and R8 (dead process), and the stats JSON.
- Not addressed on the default path: the overlay (§10.1), incremental timestamps (§10.2), crash-tolerant containers (§10.3), and the header rate and quality (§10.4).
- The opt-in Rust path addresses §10.1 (no overlay), §10.4 partly (true mode rate, CRF instead of fixed bitrate), §10.2 partly (native CSV) and §10.6 partly (audio stamps). It brings the risks above, starting with the stderr deadlock.

## Sources

- skellycam code at `55f851e4`: `skellycam/core/recorders/**`, `skellycam/core/camera/opencv/opencv_camera_loop.py` and `opencv_helpers/handle_*.py`, `skellycam/core/camera_group/camera_group.py` and `camera_orchestrator.py`, `skellycam/core/timestamps/numpy_timestamps/*.py`, `skellycam/core/ipc/pubsub/pubsub_topics.py`, `skellycam/core/ipc/process_management/worker_registry.py`, `skellycam/api/http/cameras/camera_router.py`.
- OpenCV 4.x `modules/videoio/src/cap_msmf.cpp`, `CvVideoWriter_MSMF`: bitrate line `bitRate = (UINT32)fps*videoWidth*videoHeight; // 1-bit per pixel`; `FourCC2GUID` defaults to `MFVideoFormat_H264`; `rtStart += rtDuration` per sample. Read from a copy an earlier session downloaded (not kept in the repo).
- GOP test: `research/skellycam_recording/gop_test.py`; results in §4.
- Upstream check: `research/skellycam_recording/results/upstream_check_20261109/`; `ffmpeg-sidecar` 2.5.1 source on docs.rs (`src/command.rs`, `src/child.rs`).
- Real recordings: `research/skellycam_recording/results/real_recording_20261109/` (`RESULTS.md`, `per_video_table.md`, `run*/`, `scripts/`). Raw media in `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/real_recording_20261109/`.
- Ring buffer study: `research/frame_ring_buffer/docs/frame_ring_buffer_report.md`, `baseline/results/e_e2e_*.json`, `prototypes/results/p11_crash_container.md`.
- Timestamps review: `research/usb_cameras/docs/skellycam_timestamps_review.md`.
