# Rust recording path on upstream/sfn26 (765bf82d): overview

All of this comes from reading the code. Nothing was built or run, and anything marked **inferred** is a prediction. The Rust backend exists only on sfn26: `upstream/main` and `upstream/development-streaming` have no `skellycam-rust/` directory, and none of their extra commits touch this path. The Rust recording code arrived in `6cb170f2` ("Add selectable Rust camera capture with native audio and bundled runtimes"). Two later commits also touched the Rust recording files: `43e2b968` and `f1aefa95`.

## 1. Default backend, how it is chosen, and whether it ships

- **Python/OpenCV is the default on every OS.** No code picks a backend by OS.
  - `upstream/sfn26:skellycam/core/camera_group/camera_backend_manager.py:26` sets `self.backend = "python"`, and `:30` defaults the parameter to `backend="python"`.
  - `:39` swaps in `RustCameraGroupManager` only when the request asks for `"rust"`.
- **It is chosen per request, through the API body.** `CameraGroupCreateRequest.backend: CameraBackend = "python"` is at `upstream/sfn26:skellycam/api/http/cameras/camera_router.py:25`, and it is passed on at `:127`.
- **The UI has a dropdown.** "Python / OpenCV" or "Rust / OpenPNP" (`skellycam-ui/src/components/camera-config-tree-view/CameraConfigSidebarPanel.tsx:58-70`). It defaults to `'python'` (`skellycam-ui/src/store/slices/cameras/cameras-slice.ts:31`) and is locked while cameras are connected (`:42-45`; `camera_backend_manager.py:35-37`).
- **There is no environment variable or config field.** The `USE_RUST_BACKEND: bool = True` flag described at `upstream/sfn26:skellycam-rust/README.md:134-139` is stale: `git grep USE_RUST_BACKEND` finds it only in that README. The developer notes agree that Python is the default: `RUST-BACKEND-DEVELOPMENT.md:3-6`.
- **It ships, and it is a required dependency.**
  - `pyproject.toml:76` lists `"skellycam-rust", # Required native backend`, built from source with `skellycam-rust = { path = "skellycam-rust" }` (`:82`).
  - `imageio-ffmpeg` (`:77`) supplies the encoder.
  - Every `uv sync` compiles the crate, even when the Python backend is used (`RUST-BACKEND-DEVELOPMENT.md:10-11`).
  - The PyInstaller spec bundles `_skellycam_rust`, `imageio_ffmpeg` and PortAudio (`skellycam.spec:9-18`).
  - The installer workflow builds Rust on all 5 platform/arch targets (`.github/workflows/build-installers-pyinstaller.yml:180-187`).
- **Only Windows x64 has been checked, and only that it builds and imports.**
  - `RUST-BACKEND-DEVELOPMENT.md:34-38` and `:96-98` record that local validation covers Windows x64.
  - On macOS ARM64 and Linux x64 it built and imported with no cameras attached (`:100-114`).
  - `skellycam-rust/README.md:189-191` says "Mac and Linux are not currently tested".

## 2. Capture API per OS

- **Library:** openpnp-capture, called through FFI from one thread per camera. Prebuilt static libraries come from the `jonmatthis/openpnp-capture` fork (`skellycam-rust/build.rs:1-14`, `:55-63`).
- **Windows:** DirectShow (`skellycam-rust/src/camera/camera_thread.rs:1`; `README.md:38`).
- **macOS:** AVFoundation, according to the README (`README.md:194`). Untested.
- **Linux:** V4L2, according to the README (`README.md:194`). Untested.
- **Only MJPEG formats are accepted.** Format selection filters on `info.fourcc == FOURCC_MJPG` (`camera_thread.rs:519`, `:538`, `:567`, `:595`, `:623`).
- **The only OS-specific code** in the crate is one `#[cfg(target_os = "windows")]` at `skellycam-rust/src/camera_group/jpeg_transform.rs:50`.

## 3. Files a Rust-backend recording writes

**The Rust side writes these** (`skellycam-rust/src/camera_group/dispatcher.rs:354-374`):

```
<recording_directory>/<recording_name>/
├── native_recording_summary.json                       finalizer.rs:119 (at stop)
└── synchronized_videos/
    ├── <name>.id-<cam_id>.idx-<cam_index>.mp4          dispatcher.rs:373 (during)
    └── timestamps/camera_timestamps/
        └── <name>.camera<cam_id>.native_timestamps.csv dispatcher.rs:374 (during)
```

Python passes `recording_name` as the label, so the session folder matches Python's `full_recording_path` (`rust_camera_group.py:126-129`; `recording_info.py:42`).

**Python then adds everything the review listed in §2.** `RustCameraGroup.stop_recording` calls `finalize_native_recording` (`skellycam/core/camera_group/rust_recording.py:12-55`), which runs the same `RecordingFinalizer` as the Python path:

- the info JSON (`recording_finalizer.py:55`);
- the Python per-camera CSV `<name>.camera<id>.timestamps.csv`, the multiframe CSV and the stats (`:57-61`; path at `recording_timing_reader.py:15`);
- the README (`:64`);
- `validate_recording` (`:65`).

The VFR/audio remux is **still commented out** (`:63`).

**Video encoding** (`skellycam-rust/src/recording/recorder.rs`):

- **The camera's MJPEG is decoded and re-encoded.** Each camera has an ffmpeg subprocess fed raw JPEG bytes on stdin (`recorder.rs:1-6`, `:197-209`). The ffmpeg binary is the imageio-ffmpeg executable (`rust_camera_group.py:285`).
- **Command** (`:141-153`): `-y -f image2pipe -c:v mjpeg -s WxH -r <fps> -i pipe:0 -c:v libx264 -preset ultrafast -crf 18 -pix_fmt yuv420p -an <out>.mp4`.
- **Settings** (defaults at `:37-47`; always `VideoRecorderConfig::default()`, `dispatcher.rs:403`): libx264, preset ultrafast, CRF 18, yuv420p, MP4 container.
- **Not set:** bitrate, GOP, B-frames or `movflags`.
  - **Inferred:** x264 defaults plus ultrafast give keyint 250 with scenecut off, so an I-frame every 250 frames, no B-frames, CAVLC, probably signalled Constrained Baseline.
  - **Inferred:** CRF rate control means file size depends on content and quality, not on the header rate. That replaces the review's R4 (fixed 1 bit/pixel MSMF/NVENC bitrate) for this path.
- **Frame rate is constant, at the camera mode's nominal rate.**
  - `-r target_fps` on the input gives a CFR file with no per-frame timestamps.
  - `target_fps` is the negotiated openpnp format rate (`dispatcher.rs:380-390`), written by the camera thread as `guard.framerate = format_info.fps` (`camera_thread.rs:167`, `:219`). `fps` is a `u32` (`camera/ffi.rs:20`). The fallback when it is missing is 30.0.
  - **Inferred effect on R3:** the pre-recording median estimate that caused the +9–11% header bias is gone. The header will read, for example, exactly 30 for a 30 fps mode, and all cameras in one mode get the same value. Durations will be correct only if the camera really delivers its nominal rate. Dropped or slow frames are still hidden by the CFR file.
- **Rotation is applied before recording, without re-encoding the JPEG.** The dispatcher rotates in the DCT domain (`dispatcher.rs:197-214`; `jpeg_transform.rs:1-5`).
- **The Rust side does no shape check of its own,** but Python's `validate_recording` still checks shape and frame count (`recording_finalizer.py:126-208`).

## 4. When timestamps and CSVs are written, and their format

- **The native CSV is written incrementally, flushed after every row.** It is created with its header at recorder setup, and each frame appends a row and calls `flush()` (`skellycam-rust/src/timestamps/csv_writer.rs:22-41`, `:53-72`). The call site is `recording_thread.rs:301-306`.
  - **Inferred:** `flush()` hands the data to the OS but does not fsync, so rows survive a process crash but not a power loss.
- **Native CSV columns (8):** `frame_number`, `timestamps.loop_start_ns`, `.frame_available_ns`, `.post_jpeg_extract_ns`, `.pre_send_ns`, `.gatherer_received_ns`, `.pre_frame_record_ns`, `.post_frame_record_ns` (`csv_writer.rs:28-37`).
- **Clock:** the Rust monotonic clock shifted once to Python's `perf_counter_ns` when the module is imported (`timestamps/performance.rs:31-33`, `:66`; `pyo3_bridge/mod.rs:29-35`, which also exposes the uncertainty as `clock_alignment_uncertainty_ns`).
  - `frame_available_ns` is stamped when `Cap_hasNewFrame` turns true (`camera_thread.rs:351`, `:367-370`).
  - `loop_start_ns` is stamped just after the barrier, at the start of the wait (`:474-479`).
- **The Python 27-column CSV, the multiframe CSV and the stats are written only at stop**, from the native CSV. `rust_recording.py:32-44` maps the columns:
  - `pre_frame_grab_ns` ← `loop_start_ns`
  - `post_frame_grab_ns` ← `frame_available_ns`
  - retrieve ← `post_jpeg_extract_ns`
  - shm copy ← `pre_send_ns` / `gatherer_received_ns`
- **Inferred:** the Python CSV's main timestamp is still the grab midpoint (`create_camera_csvs.py:49-51`). For Rust that is the midpoint of loop start and frame-available, so it sits up to half the wait time before the frame actually arrived. `frame_available_ns`, available only in the native CSV, is the more meaningful stamp.
- **Rust also computes recording stats** and returns them as `stats_json` (`py_camera_group_manager.rs:542-545`), but `RustCameraGroup.stop_recording` never reads them (`rust_camera_group.py:143-155`).

## 5. Overlay

- **None.** The recorder receives the camera's own JPEG bytes, rotated only (`dispatcher.rs:216-221`, `:306-319`).
- `git grep -iE "overlay|annotat|putText|draw_text"` over `skellycam-rust/src` finds nothing.
- **R2 (overlay burned into the recording) does not apply to this path.** The Python/OpenCV path is reviewed separately.

## 6. Audio

- **Capture:** PortAudio, called from Rust through the PortAudio library sounddevice already loaded (`skellycam-rust/src/recording/audio.rs:1-3`, `:50-63`; `rust_camera_group.py:119-125`).
  - Format: 44.1 kHz, 1024-frame blocks, int16, up to 2 channels (`audio.rs:16-17`, `:159-162`).
  - Data passes through a lock-free ring buffer and is written to the WAV as it arrives through hound/BufWriter (`:152`, `:166-169`, `:190-191`), so audio no longer piles up in RAM.
- **Timing:**
  - `start_perf_counter_ns` is now taken after `Pa_OpenStream` and just before `Pa_StartStream` (`:170-174`), so device-open time is no longer included.
  - Each chunk carries both the callback host time and an ADC time, computed as host time + (`inputBufferAdcTime` − `currentTime`) (`:89-92`).
  - The sidecar records dropped chunks and status flags (`:210-219`).
  - The sidecar `<name>.audio_timestamps.json` is written only at stop (`:220-222`).
- **Alignment and muxing: none.**
  - Audio starts before the video recorder is asked to start (`rust_camera_group.py:118-129`).
  - It stops after the video stops (`:142-147`, the `finally`).
  - The remux that would join them is commented out (`recording_finalizer.py:63`).
  - The WAV stays separate. A consumer must line up the sidecar stamps with the CSVs, as in R11, but with better stamps to work from.

## 7. Crash and kill behaviour

| Event | What survives |
| --- | --- |
| Clean stop, graceful `/shutdown`, or app lifespan exit | Everything. `close_native_camera_groups()` stops and fully finalizes Rust recordings before the kill flag is set (`api/http/app/shutdown.py:37`; `app.py:64`; `camera_group_manager.py:268-271`). This is better than the Python path, where a kill-flag shutdown writes no CSVs. |
| Server process hard-killed | The native CSVs, up to the last flushed row. ffmpeg is a separate child process: **inferred**, if it outlives the parent, stdin EOF lets it write a playable MP4; if the process tree is killed, the MP4 has no moov atom and is unreadable. Missing: the WAV header sizes (hound writes them only at `finalize`, `audio.rs:207`), the audio sidecar, `native_recording_summary.json`, and all the Python finalize outputs. |
| Recorder dropped without `finish()` (setup failure, recording thread exits on channel disconnect) | `Drop` kills ffmpeg, leaving a partial MP4 (`recorder.rs:86-87`, `:265-276`; `recording_thread.rs:335-340`). **Inferred:** if the gatherer disconnects mid-recording (`dispatcher.rs:327-329`), the handle is dropped this way. |
| Dispatcher `Shutdown` while recording | `handle.shutdown()` runs `finalize_all`, so the videos and native files are finalized (`dispatcher.rs:144-151`; `recording_thread.rs:326-332`). The Python finalize does not run on this path. |
| Microphone reports any dropped chunk or nonzero status flag | `AudioRecorder` raises at stop (`audio.rs:223-224`). That exception comes out of the `finally` at `rust_camera_group.py:145-147`, so `finalize_native_recording` (`:150-154`) never runs: no info JSON and no Python CSVs. **Inferred:** `CameraBackendManager._recording_requested` then stays `True` (`camera_backend_manager.py:86-92`), so later starts are refused until the cameras are closed. |

## 8. Unfinished, TODO or disabled

- **Encoder settings are hard-coded.** "In the future these will be user-configurable" (`recorder.rs:17-20`). There is no GOP, bitrate or `movflags` setting.
- **The remux is still disabled** (`recording_finalizer.py:63`), so there is no VFR file and no audio in the video.
- **The README's selection flag `USE_RUST_BACKEND` is stale** (`skellycam-rust/README.md:134-139`).
- **macOS and Linux capture and recording are untested** (`README.md:189-197`; `RUST-BACKEND-DEVELOPMENT.md:96-114`). The code comments assume DirectShow throughout (`camera_thread.rs:1`, `:372-374`; `ffi.rs:3`).
- **Known lifecycle race conditions** around hot-plugging and fast start/stop (`README.md:187`).
- **Polars is commented out of the build**, labelled "Phase 3 — recording" (`Cargo.toml:85-86`).
- **The Rust stats summary is computed but not used** (§4).
- **The recording thread's queue is unbounded** (`recording_thread.rs:5`, `:96-101`). **Inferred:** if ffmpeg falls behind, memory grows and the stop waits until the queue drains.
- **The Python finalize still runs synchronously on the event loop** (`rust_camera_group.py:150-154` → `RecordingFinalizer`), so R10 (finalize freezes the UI) applies to this path too (**inferred**).