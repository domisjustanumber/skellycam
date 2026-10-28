# skellycam-arch

I read SkellyCam at commit `23ccbf20` (branch `development`) and did not modify the repo. To verify behaviour I ran the existing test suite and two scripts in a fresh scratch venv. The repo's own `.venv` can't import the package because `polars` is missing (`skellycam/core/recorders/video_audio_remuxer.py:8`).

## 1. Worker processes and the capture loop
- **How a camera process is created:** HTTP `/camera/group/apply` → `CameraGroup.create` → `CameraManager.create` makes one `CameraStatus` and one `CameraWorker` per config, all sharing one `CameraOrchestrator` (`skellycam/core/camera/camera_manager.py:27-66`). `CameraWorker.create` **always** uses `opencv_camera_worker_method` as the target (`skellycam/core/camera/camera_worker.py:7,48-61`), so OpenCV is hard-wired here. The device is opened inside the child process (`setup_opencv_camera_loop.py:40`), which suits GigE SDK handles that can't be pickled.
- **Start-up:** each camera opens its device and publishes its *extracted* config. The parent sizes shared memory from those configs. All cameras then wait for each other (`all_ready`) while draining frames (`setup_opencv_camera_loop.py:42-65`; `camera_group.py:104-119`).
- **Each loop iteration:**
  - check for updates and pause;
  - **frame-count gate**: a camera may grab only if its frame count is ≤ every other camera's (`camera_orchestrator.py:96-109`; `opencv_camera_loop.py:67-69`);
  - `grab()` then `retrieve()` straight into the pre-allocated image, back to back in the same process (`opencv_get_frame.py:53-73`);
  - a text overlay is burned into the image, so it ends up in recorded video too (`:80-84`);
  - read recording flags before clearing `grabbing_frame` (`opencv_camera_loop.py:89-93`);
  - write the frame to the shared-memory ring buffer (overwrite allowed) (`:95-97`), record if needed (`:99-105`), then publish `frame_count` (`:116`).
- **No barrier between grab and retrieve.** The docstring says the split lets all cameras grab before any of them retrieves (`opencv_get_frame.py:30-33`), but the code has no cross-camera ordering between the two calls. The only cross-camera coordination is the frame-count gate, the start-up `all_ready` wait, and a wait for all cameras at recording start (`handle_recording_updates.py:45-47`).
- `frame_number` is a host-side count of successful grabs (`opencv_get_frame.py:79`), not a device frame ID.
- `check_framerate_reset` assumes 30 fps and re-creates the `cv2.VideoCapture` when frames run slow (`opencv_camera_loop.py:150-170`).
  > **Correction (2026-10-28):** it acts only once frame_number > 100, and only after more than 30 consecutive slow iterations (> 66.7 ms). It times post-retrieve processing from `previous_tik` (set at :82), not the true inter-frame interval (verifier A5).

## 2. CameraConfig and backend choice
- **Fields:** `camera_id`, `camera_index` (used to open `cv2.VideoCapture` and must be unique), `camera_name`, `use_this_camera`, `resolution`, `color_channels=3`, `pixel_format="RGB"` (marked TODO and unused), `exposure_mode`, `exposure` (OpenCV log2 units), `framerate`, `rotation`, `capture_fourcc="MJPG"`, `writer_fourcc="X264"` (`camera_config.py:63-123,375-390`).
- **There is no backend abstraction.** `determine_backend.py` only picks which OpenCV video API to use: DSHOW, V4L2 or AVFoundation (`determine_backend.py:28-70`). The backend type aliases are OpenCV IDs (`type_overloads.py:12-13`). A grep for GigE, Aravis, Harvester, GenICam, PTP and vendor SDK names in `skellycam/`, `skellycam-ui/src` and `pyproject.toml` found nothing.

## 3. Frame record in shared memory
- A frame is `{frame_metadata, image: uint8[H,W,C]}` (`frame_dtype_factories.py:11-26`). Images are always uint8.
- Metadata holds `camera_info`, `frame_number`, `timebase_mapping`, and nine lifecycle timestamps, all host `time.perf_counter_ns()` (`numpy_record_dtypes.py:10-33,222-228`).
- UTC conversion uses a single `(time_ns, perf_counter_ns)` sample taken when the camera group's IPC object is created (`timebase_mapping.py:16-32`; `camera_group_ipc.py:24`). The docs say it is created at recording start; that is wrong.
- **There is no field for a device or PTP timestamp, or a device frame ID.**
- Downstream code assumes 3-channel BGR uint8:
  - JPEG encode for the UI (`frontend_payload_bytearray.py:142`);
  - `cv2.VideoWriter` with colour on by default, and PyAV with `bgr24` (`video_recorder.py:124-130`; `pyav_video_writer.py:27`);
  - recording validation compares the decoded video shape to `config.image_shape`. For mono that is `(H,W)` while the buffer holds `(H,W,1)` (verified), so mono doesn't work end to end.
    > **Correction (2026-10-28):** the verifier (A9) found that the JPEG/UI path handles (H,W,1) fine, so the first item above is wrong. Mono fails earlier, in the writers: `cv2.VideoWriter` writes 0 frames ('expected 3 channels but got 1') and PyAV `bgr24` raises ValueError. The finalizer's first-frame read therefore fails before the shape comparison is reached.
- Each camera gets a 1 GiB ring buffer (`ring_buffer_shared_memory.py:35-45`). Measured depth: 388 frames at 1280×720, 71 at 2448×2048.

## 4. Device detection
- `detect_available_cameras` uses `cv2_enumerate_cameras` (`detect_cameras_devices.py:86-109`) and returns `CameraDeviceInfo` rows (index, name, VID, PID, path, backend). `camera_id` is a hash of path or VID/PID (`:35-55`).
- These are served at `POST /camera/detect` (`camera_router.py:89-100`).
- The UI builds each camera's config from `(camera_id, index, name)` only (`skellycam-ui/src/store/slices/cameras/cameras-thunks.ts:63-97`).
- GigE devices would be added as extra `CameraDeviceInfo` rows carrying backend, serial, MAC and IP. The UI must then carry backend and serial through to the config.

## 5. Recording and timestamp CSVs
- During recording, each recorder keeps a copy of every frame's metadata (`video_recorder.py:108`) and sends the list to the parent when recording stops. The parent then runs the finalizer.
- Per-camera CSVs auto-map **every** lifecycle-timestamp field to a column, subtracting the host-clock recording start (`create_camera_csvs.py:85-89`).
- The multi-camera CSV computes `inter_camera.frame_grab_range.ms` from host grab midpoints (`create_multi_frame_csvs.py:54-58`).
- **Where PTP timestamps should go:** a new `device_timing` sub-record in the frame metadata, not the lifecycle-timestamp dtype (otherwise a device-clock value gets a host-clock offset subtracted). It needs explicit `device.*` CSV columns plus `inter_camera.device_timestamp_range.ms`.
- Dead, buggy code: `create_camera_frame_csv_row_recarray` (`create_camera_csvs.py:110-178`) has no callers and adds `pre_grab` to itself instead of `post_grab`.

## 6. Tests and mocks
Full suite: 171 passed, 15 failed, 4 errors in 8.7s. The interpreter then hangs on exit.
- **Most failures are beartype type checks.** `beartype_this_package()` (`skellycam/__init__.py:16-17`) rejects `MagicMock` objects and int-vs-float mismatches.
- `MockVideoCapture` has no `grab`/`retrieve`, so it can't drive the capture loop (`tests/mocks/camera_mock.py:8-118`).
- Patterns worth reusing:
  - real frame recarrays built from configs (`test_frontend_payload_and_recording.py:28-49`);
  - orchestrator tested without processes (`test_camera_orchestrator.py:10-12`);
  - a small shared-memory ring buffer (`test_shared_memory.py:140-151`);
  - thread-mode workers (`test_worker_lifecycle.py`);
  - patching the detect function in router tests (`test_camera_router.py:10-31`).

## 7. Proposed design
- **Backend interface:** add `skellycam/core/camera/backends/` with a `@runtime_checkable` `CameraBackend` Protocol: `open`, `apply_config`, `start`, `drain`, `grab`, `retrieve(out)`, `device_timing`, `is_open`, `close`.
  - Generalize the loop and worker entry point to call it, keeping the gate, flag ordering and shared-memory code unchanged.
  - Wrap the existing OpenCV helpers as `OpenCVBackend`, and put the GigE implementation under an optional install extra.
- **Prototype check:**
  - Beartype accepts a fake backend checked against a `@runtime_checkable` Protocol and rejects a non-conforming object.
  - A plain Protocol (without `@runtime_checkable`) used as a type hint fails as soon as the function is decorated.
- **CameraConfig:** add `backend="opencv"` (default), `device_id` (serial), `device_address`, `source_pixel_format`, `ptp_enabled`. Give GigE cameras synthetic, non-colliding `camera_index` values.
- **Debayer:** `cv2.cvtColor(raw, code, dst=frame.image[0])` writes in place into the shared-memory slot (verified). It took about 0.18 ms at 2448×2048 on this machine.
  - **OpenCV's Bayer names don't match the layout names.** For an RGGB mosaic, `COLOR_BayerBG2BGR` gives red; `COLOR_BayerRG2BGR` gives blue.
  - Use `Mono8` → `GRAY2BGR`, and prefer 8-bit pixel formats.
- **PTP timestamps:** fill `device_timing` after `grab()`. It then flows through shared memory, the recorder, the recording-finished message and the finalizer into new CSV columns. Compare device frame IDs against `frame_number` to detect dropped frames.

Full notes, including docs-vs-code discrepancies: `C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/f77e9c4e-e1ea-4406-8a36-bef826a63a0e/scratchpad/research/skellycam-arch.md`

## Open questions

- How does the UI/backend handle a resolution change on a running camera group, given the SHM frame dtype is fixed at group creation (camera_group.py:104-119) and check_for_new_config does not reallocate? Not traced.
- Why does the pytest process hang after printing the test summary (likely WorkerRegistry heartbeat/monitor threads)? Not investigated.
- Confirm from the GenICam PFNC spec that BayerRG8 means R at pixel (0,0) (RGGB); the OpenCV code mapping (RGGB -> COLOR_BayerBG2BGR) was verified empirically, but the PFNC side is assumed.
- Whether the burned-in frame overlay text (opencv_get_frame.py:80-84) should be applied to GigE frames / recorded video.
- Best uniqueness key for GigE cameras: synthetic camera_index vs changing validate_camera_configs to (backend, device_id); camera_index is also used in filenames (parse_video_filename.py:83-90) and the frontend header.
- Exact GenICam API for reading buffer device timestamp, block ID and PTP status (Aravis vs Harvester) — out of scope here, belongs to library topics.

## Verification: Counter({'supported': 16, 'partially-supported': 4})

- [partially-supported] A5: check_framerate_reset hard-codes a 30 fps target and recreates the cv2.VideoCapture after 30 consecutive slow frames.
  REASON: The 30 fps target is hard-coded (:156) and the capture is re-created (:167-168). The details are off. The reset needs more than 30 slow frames in a row (`> 30`, so 31). It only runs after frame_number > 100. 'Slow' means longer than 2x 33.3 ms (66.7 ms). Most importantly, previous_tik is set at :82, just after grab/retrieve, so the check times the post-retrieve work (SHM copy plus recording). It does not measure the gap between frames.
  CORRECTED: check_framerate_reset assumes a 30 fps target. Once frame_number > 100, it re-creates the cv2.VideoCapture after more than 30 consecutive iterations (31 or more) whose post-retrieve processing time, measured from the previous_tik set at :82, exceeds 66.7 ms. It does not measure the true inter-frame interval.
  BETTER: ['https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/skellycam/core/camera/opencv/opencv_camera_loop.py#L80-L117', 'https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/skellycam/core/camera/opencv/opencv_camera_loop.py#L150-L170']

- [partially-supported] A8: Host timestamps map to UTC via one TimebaseMapping sample created with CameraGroupIPC (camera-group creation), not at recording start as the docs state.
  REASON: The code part is correct. TimebaseMapping is a field default_factory on CameraGroupIPC (camera_group_ipc.py:24), so it is sampled once when the IPC object is created. That sample is copied into each frame (create_initial_frame_recarray.py:15). The doc citations are wrong: precise-timestamps.mdx has only 108 lines. The 'created once at recording start' sentence is at line 56, not 159. The broken link to skellycam/core/camera/config/timebase_mapping.py is at line 45; that file does not exist, and the real one is in core/timestamps/.
  CORRECTED: TimebaseMapping is sampled once when CameraGroupIPC is created (camera_group_ipc.py:24). precise-timestamps.mdx:56 wrongly says it is created at recording start, and :45 links to a path that does not exist.
  BETTER: ['https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/skellycam/core/camera_group/camera_group_ipc.py#L16-L45', 'https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/skellycam-docs/docs/core/precise-timestamps.mdx#L45-L56']

- [partially-supported] A9: Downstream consumers assume 3-channel BGR uint8 (JPEG encode, cv2.VideoWriter default isColor, PyAV bgr24); mono (color_channels=1) is inconsistent: frame dtype holds (H,W,1) but CameraConfig.image_shape is (H,W), which recording validation compares against decoded video frames.
  REASON: Mono is indeed broken end to end, but the claimed mechanism is partly wrong. I ran a test (research/src/verify-skellycam-arch/mono_paths.py, OpenCV 4.12.0): cv2.imencode('.jpg') accepts a (H,W,1) image fine, so the JPEG/UI path does not assume 3 channels. The failure comes earlier. cv2.VideoWriter (isColor defaults to true) logs 'writeFrame write frame skipped - expected 3 channels but got 1' and writes 0 frames. PyAV VideoFrame.from_ndarray(format='bgr24') raises ValueError. As a result, the finalizer's first-frame read at recording_finalizer.py:156-158 fails before the shape comparison at :161 is reached. Even when frames are written, cv2.VideoCapture decodes to 3-channel BGR, which never equals the (H,W) image_shape.
  CORRECTED: Recording assumes 3-channel BGR uint8. cv2.VideoWriter silently drops 1-channel frames (0 frames written) and PyAV bgr24 raises ValueError, so mono recordings fail. JPEG encoding for the UI handles mono fine. CameraConfig.image_shape for mono is (H,W) while the SHM image is (H,W,1).
  BETTER: ['https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/skellycam/core/recorders/videos/video_recorder.py#L116-L130', 'https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/skellycam/core/recorders/videos/pyav_video_writer.py#L25-L31', 'https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/skellycam/core/recorders/recording_finalizer.py#L147-L164']

- [partially-supported] A19: Docs/code discrepancies: architecture.mdx claims a second multiframe SHM buffer and JPEG quality 80; code reads per-camera rings directly and uses quality 60; precise-timestamps.mdx links a non-existent timebase_mapping path.
  REASON: architecture.mdx:164-165 does describe a second multiframe SHM buffer and quality 80. The code reads the per-camera rings directly (camera_group_shared_memory.py:129-141) and uses JPEG quality 60 (frontend_payload_bytearray.py:34). The precise-timestamps.mdx citation is wrong: the broken link is at line 45, not 148, and the file has only 108 lines.
  CORRECTED: architecture.mdx:164-165 (second multiframe SHM buffer, JPEG quality 80) disagrees with the code (direct per-camera reads, quality 60). precise-timestamps.mdx:45 links a non-existent core/camera/config/timebase_mapping.py.
  BETTER: ['https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/skellycam-docs/docs/technical/architecture.mdx#L164-L165', 'https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/skellycam-docs/docs/core/precise-timestamps.mdx#L45']

## Missed points

- Recording start is aligned by frame number, not by time. CameraGroup.start_recording pauses all cameras, sets first_recording_frame_number = max(frame_count)+3, publishes RecordingInfo and unpauses. should_record_frame_number then gates each frame. https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/skellycam/core/camera_group/camera_group.py#L183-L208 and https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/skellycam/core/camera_group/camera_orchestrator.py#L80-L94
- Frames from different cameras are paired purely by equal host frame_number. latest_multiframe_number is the min over cameras and get_latest_multiframe raises on mismatch (https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/skellycam/core/ipc/shared_memory/camera_group_shared_memory.py#L34-L35, #L129-L141). validate_frame_metadatas requires identical frame numbers across cameras (https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/skellycam/core/timestamps/numpy_timestamps/process_and_save_recording_timestamps.py#L41-L48). VideoRecorder raises on non-consecutive numbers (https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/skellycam/core/recorders/videos/video_recorder.py#L149-L156). So a GigE backend must keep frame_number as the host lockstep counter and store the device block ID or PTP timestamp separately. Without that, frames dropped on the device are silently paired with the wrong frames.
- CameraStatus.grabbing_frame is set at opencv_camera_loop.py:70 and :93 but never read anywhere, so the 'race-condition' comment at :87-88 protects nothing. https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/skellycam/core/camera/opencv/opencv_camera_loop.py#L67-L93
- There is prior art in the user's own fork (domisjustanumber/skellycam). Branch origin/dom/openpnp-capture (3be07237, 2026-05-13) replaced OpenCV by swapping camera_worker.py's import to openpnp_camera_worker_method, again with no abstraction. The local-only branch dom/openpnp-capture-mf, commit 4a086a74 (2026-05-19), added hardware_timestamp_ns to FRAME_LIFECYCLE_TIMESTAMPS_DTYPE plus a 'frame.hardware_timestamp.ns' CSV column. That is exactly the anti-pattern A12 warns about: a device-clock value gets the host recording start subtracted. Verified with git show; the pushed branch is at https://github.com/domisjustanumber/skellycam/tree/dom/openpnp-capture
- detect_available_cameras skips any device without VID/PID on Windows and Linux. camera_id is a 16-bit SHA-256 prefix (4 hex chars), so collisions are possible as camera counts grow. GigE device rows need their own enumeration path and ID scheme. https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/skellycam/core/device_detection/detect_cameras_devices.py#L44-L106
- The real mono failure is in the video writers: cv2.VideoWriter logs 'expected 3 channels but got 1' and writes 0 frames, and PyAV bgr24 raises ValueError. JPEG encoding is fine. Script: C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/f77e9c4e-e1ea-4406-8a36-bef826a63a0e/scratchpad/research/src/verify-skellycam-arch/mono_paths.py. Code: https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/skellycam/core/recorders/videos/pyav_video_writer.py#L25-L31
- Verifier notes: C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/f77e9c4e-e1ea-4406-8a36-bef826a63a0e/scratchpad/research/verify-skellycam-arch.md