# SkellyCam camera pipeline: map for adding a GigE Vision backend (TOPIC_KEY=skellycam-arch)

Repo: `C:/Users/Dom/GitHub/freemocap/skellycam`, branch `development`, commit `23ccbf208e43879bfc74fc01049e5af2a623933d` ("update uvlock"), read 2026-10-25.
GitHub permalink base: https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/
All `path:line` references below are relative to the repo root at that commit. The repo was not modified.

Verification artifacts (in this scratchpad):
- `research/venvs/skellycam-arch`: fresh uv venv (Python 3.12, opencv-contrib-python 4.12.0, numpy 2.2.6, plus project deps from `pyproject.toml:53-76`). The repo's own `.venv` cannot import the package because `polars` is missing (`skellycam/core/recorders/video_audio_remuxer.py:8`).
- `research/skellycam-arch-pytest.log`: full existing test suite run.
- `research/scripts/skellycam_arch_verify.py` -> `research/skellycam-arch-verify.log`
- `research/scripts/backend_protocol_prototype.py` -> `research/backend-protocol-prototype.log`

---

## 0. TL;DR

- **OpenCV is hard-wired.** No backend abstraction exists. `CameraWorker.create` always targets `opencv_camera_worker_method` (`skellycam/core/camera/camera_worker.py:7,48-61`). The loop takes a `cv2.VideoCapture` and calls `cv2`-specific helpers (`skellycam/core/camera/opencv/opencv_camera_loop.py:26-34,74-75,150-169`). `determine_backend.py` only chooses *which OpenCV videoio API* to use: DSHOW, V4L2 or AVFoundation (`skellycam/core/camera/determine_backend.py:28-70`). `CameraConfig` has no backend or device-address field; `camera_index` is the only device locator (`skellycam/core/camera/config/camera_config.py:69-71`).
- **How sync works.** It is a software frame-count lock-step gate, not a grab/retrieve barrier. A camera may grab only when its `frame_count` is <= every other camera's (`skellycam/core/camera_group/camera_orchestrator.py:96-109`). Each process then calls `grab()` and `retrieve()` back-to-back (`skellycam/core/camera/opencv/opencv_helpers/opencv_get_frame.py:53-73`). Nothing synchronizes cameras *between* grab and retrieve. The only cross-camera barriers are (a) this gate and (b) the start-up `all_ready` wait (`skellycam/core/camera/opencv/opencv_helpers/setup_opencv_camera_loop.py:63-65`).
- **Frame record.** The frame is a numpy structured dtype `{frame_metadata, image}`. `image` is `uint8[H, W, color_channels]` (`skellycam/core/types/frame_dtype_factories.py:11-26`). Downstream consumers assume 3-channel BGR uint8: JPEG encode, `cv2.VideoWriter`, PyAV `bgr24` and recording validation (details in section 3). Every per-frame timestamp is host `time.perf_counter_ns()` (`skellycam/core/types/numpy_record_dtypes.py:23-33`). **There is no field for a camera or device (PTP) timestamp or a device frame ID** (verified in `backend-protocol-prototype.log`).
- **Recommended integration.** Add a small `@runtime_checkable` `CameraBackend` Protocol. Generalize the existing loop to call it rather than `cv2`. Add `backend` and `device_id` fields to `CameraConfig`, defaulting to OpenCV so the UI is unaffected. Debayer GigE Bayer8 frames into the pre-allocated BGR `image` slot with `cv2.cvtColor(..., dst=)`. Add a separate `device_timing` sub-record (device timestamp ns, device frame/block ID) to `FRAME_METADATA_DTYPE`, with explicit CSV columns. **Do not** add these to `FRAME_LIFECYCLE_TIMESTAMPS_DTYPE`: that dtype's fields are auto-converted to CSV relative to the host clock (`skellycam/core/timestamps/numpy_timestamps/create_camera_csvs.py:85-89`).
- **Gotcha: beartype checks everything.** `skellycam/__init__.py:16-17` runs `beartype_this_package()`, so every annotation is enforced at runtime. A Protocol type hint must be `@runtime_checkable`, or beartype raises `BeartypeDecorHintPep3119Exception` at decoration time (prototype log). `MagicMock` stand-ins fail type checks. That is the root cause of most of the existing suite's failures (section 6).
- **Gotcha: Bayer naming differs between GenICam and OpenCV.** For an RGGB mosaic (red at pixel (0,0)), OpenCV's `COLOR_BayerBG2BGR` gives red; `COLOR_BayerRG2BGR` gives blue (`skellycam-arch-verify.log` [5]).

---

## 1. Camera worker process creation and loop

### Creation chain
1. HTTP `POST /skellycam/camera/group/apply` -> `CameraGroupManager.create_or_update_camera_group` (`skellycam/api/http/cameras/camera_router.py:113-129`; `skellycam/core/camera_group/camera_group_manager.py:73-83`).
2. `CameraGroup.create` validates configs, creates `CameraGroupIPC`, then `CameraManager.create` (`skellycam/core/camera_group/camera_group.py:72-102`).
3. `CameraManager.create` builds one `CameraStatus` per camera, a shared `CameraOrchestrator`, and one `CameraWorker` per config. Each worker gets three pubsub subscriptions: settings, shm and recording info (`skellycam/core/camera/camera_manager.py:27-66`).
4. `CameraWorker.create` -> `worker_registry.create_worker(target=opencv_camera_worker_method, kwargs=...)` (`skellycam/core/camera/camera_worker.py:35-67`). **The target is hard-coded and is the single dispatch point to change.**
5. `WorkerRegistry.create_worker` makes a `ManagedProcess` (a `multiprocessing.Process`) or a `ManagedThread`, depending on `WorkerMode` (`skellycam/core/ipc/process_management/worker_registry.py:128-159`; `skellycam/core/ipc/process_management/managed_worker.py:39-41,221-250`).
6. `CameraManager.start` starts workers, staggered 0.25 s apart on Windows (`skellycam/core/camera/camera_manager.py:68-81`).
7. `CameraGroup.start` waits for each worker to publish its *extracted* config (`await_extracted_configs`, `skellycam/core/camera_group/camera_group.py:290-314`). It then sizes and creates the shared memory from those configs and publishes the SHM DTO (`camera_group.py:104-119`).

Implication for GigE: device handles (Aravis `ArvCamera`, Harvester `ImageAcquirer`, and so on) are opened *inside the child process*. Only the pydantic `CameraConfig` crosses the process boundary, which already matches how `cv2.VideoCapture` is created in the child (`setup_opencv_camera_loop.py:40`).

### Worker entry point and setup (`skellycam/core/camera/opencv/opencv_camera_worker_method.py:18-83`)
- `setup_opencv_camera_loop` (`skellycam/core/camera/opencv/opencv_helpers/setup_opencv_camera_loop.py:31-77`):
  - Opens the device with `create_cv2_video_capture(config)`, which applies config and returns the *extracted* config (`:40`; `create_cv2_video_capture.py:31-88`).
  - Publishes `DeviceExtractedConfigMessage` (`:42`). The parent sizes SHM from this, so **the extracted resolution and channels define the frame dtype**.
  - Waits for `SetShmMessage` and attaches to its camera ring buffer (`:44-58`).
  - Sets `connected=True` (`:61`).
  - **Start barrier:** loops `cv2_video_capture.read()` to drain the buffer until `orchestrator.all_ready` (`:63-65`).
  - Builds the initial frame recarray with `frame_number=-1` (`:66-67`; `create_initial_frame_recarray.py:8-19`).
- Failure raises `CameraSetupFailedException`, which stops only this group (`:69-76`; `opencv_camera_worker_method.py:59-65`).
- `finally` calls `cv2_video_capture.release()` and closes SHM (not unlink) (`opencv_camera_worker_method.py:73-83`).

### Hot loop (`skellycam/core/camera/opencv/opencv_camera_loop.py:26-130`)
Each iteration:
1. `camera_loop_update_checks`: new recording info -> create `VideoRecorder`, then **barrier until all cameras are recording** (`opencv_helpers/handle_recording_updates.py:24-47`). Config update -> `apply_camera_configuration(cv2_video_capture, ...)`, which is cv2-specific (`opencv_helpers/check_for_new_config.py:21-41`). Pause flag check (`camera_loop_update_checks.py:52-63`).
2. Exit on `should_close`, and spin 1 ms while paused (`opencv_camera_loop.py:60-65`).
3. **Sync gate:** `orchestrator.should_grab_by_id(camera_id)`, otherwise wait 10 µs (`:67-69`). The gate (`camera_orchestrator.py:96-109`) requires `all_ready`, and this camera's `frame_count` must be <= all others.
4. `grabbing_frame=True`, then call `opencv_get_frame` with up to `MAX_FAIL_COUNT=30` retries (`:70-85`). `opencv_get_frame` (`opencv_helpers/opencv_get_frame.py:53-86`) does:
   - `pre_frame_grab_ns`, `cap.grab()`, `post_frame_grab_ns` (`:53-55`)
   - `pre_frame_retrieve_ns`, `cap.retrieve(image=frame_rec_array.image[0])` into the pre-allocated array, `post_frame_retrieve_ns` (`:71-73`)
   - `frame_number += 1` (`:79`)
   - **burns a text overlay into the image** (`camera.id… .fr…`, `:80-84`). This overlay goes into shared memory *and into the recorded video*, because recording uses the same `image` (`opencv_camera_loop.py:99-105`).
5. Reads recording flags *before* clearing `grabbing_frame` (`:89-93`).
6. Copies the frame into the camera's SHM ring buffer with overwrite, bracketed by `pre/post_copy_to_camera_shm_ns` (`:95-97`).
7. `handle_video_recording` writes the frame to the `VideoRecorder` and finishes recording at the stop boundary (`:99-105`; `handle_video_recording_loop.py:13-37`).
8. `check_framerate_reset` assumes **30 fps** (`#TODO`). After 30 consecutive frames longer than 2× 33 ms it **re-creates the `cv2.VideoCapture`** (`:150-170`). This is OpenCV-specific and would misfire for any camera configured below about 15 fps.
9. Zeroes the lifecycle timestamps and sets `initialized_ns` (`:113`, `:133-147`).
10. Publishes `self_status.frame_count = frame_number`, which "ungates" the other cameras (`:115-116`).

**Answer to "grab/retrieve split for sync / orchestrator barrier?"** The docstring motivates the split as letting "all cameras grab() in tight succession before any camera spends time on the heavier retrieve()" (`opencv_get_frame.py:30-33`). The code, however, runs grab then retrieve consecutively in one process with no inter-camera barrier between them (`:53-73`). Each process's grab starts whenever it independently passes the frame-count gate. The only cross-camera coordination is:
- the frame-count gate (`camera_orchestrator.py:96-109`), which is unit-tested in `skellycam/tests/test_camera_orchestrator.py:84-117`
- the start-up `all_ready` barrier (`setup_opencv_camera_loop.py:63-65`)
- the recording-start barrier (`handle_recording_updates.py:45-47`)

The docs describe the same model (`skellycam-docs/docs/technical/frame-synchronization.mdx:58-80`) and acknowledge that USB sensor exposure is unsynchronized, about ±½ frame (`skellycam-docs/docs/core/frame-perfect-sync.mdx:25-27`, which references issue #91).

Implications for hardware or PTP-synced GigE:
- `frame_number` is a host-side counter of successful grabs (`opencv_get_frame.py:79`), not a device frame ID. If a GigE camera drops a frame (a missing block ID), lock-step still advances by count, so cameras can silently pair different exposure instants. A GigE backend should record the device block ID and timestamp so drops can be detected, and ideally should match frames across cameras by device timestamp.
- With PTP-scheduled or triggered acquisition, the frame-count gate still provides the "no camera more than one frame ahead" property. However, the camera exposes on its own schedule, so `grab()` must return the *next buffer in order*, not "latest". The OpenCV path relies on `CAP_PROP_BUFFERSIZE=1` to get the latest frame (`create_cv2_video_capture.py:21-28,60-69`). For GigE, the stream buffer pool and discard policy need equivalent configuration.

---

## 2. CameraConfig fields and backend selection

`CameraConfig` (pydantic) is at `skellycam/core/camera/config/camera_config.py:63-123`:

| field | default | note |
|---|---|---|
| `camera_id: str` | `"000"` | unique key (`:65-67`) |
| `camera_index: int` | 0 | "used to create the `cv2.VideoCapture`" (`:69-71`); **must be unique across configs** (`validate_camera_configs`, `:386-390`) |
| `camera_name` | "Default Camera" -> `Camera-{id}` | (`:73-76`, `:125-129`) |
| `use_this_camera` | True | (`:77-80`) |
| `resolution: ImageResolution(height,width)` | 720×1280 | (`:81-84`; `image_resolution.py:6-8`) |
| `color_channels: int` | 3 | (`:85-88`) |
| `pixel_format: str` | `"RGB"` | `# TODO - Handle options other than RGB` (`:90-92`). Nothing reads it in the capture path, and the data is actually BGR (cv2 retrieve, PyAV `bgr24`). |
| `exposure_mode` | `MANUAL` | (`:94-99`) |
| `exposure: int` | -7 | OpenCV log2 convention (`:100-106`) |
| `framerate: float` | -1 | (`:108-109`); not applied on update (`opencv_apply_config.py:62`) |
| `rotation: RotationTypes` | NO_ROTATION | (`:111-114`) |
| `capture_fourcc` | `"MJPG"` | (`:115-118`); OpenCV-only concept |
| `writer_fourcc` | `"X264"` | (`:120-123`) |

Settable parameters (UI): exposure_mode, exposure, resolution, framerate, rotation (`:55-60`, `:189-218`).

- **Backend selection:** `determine_opencv_camera_backend()` returns an `OpenCVBackend(id, name)`. It picks DSHOW on Windows, V4L2 on Linux, and AVFoundation (or the first supported) on macOS (`skellycam/core/camera/determine_backend.py:13-70`). Only `create_cv2_video_capture` (`create_cv2_video_capture.py:32,37`) and device detection (`detect_cameras_devices.py:91-95`) call it.
- **Abstraction:** none. The type aliases `CameraBackendInt = int  # OpenCV backend ID` and `CameraBackendNameString` are OpenCV-specific (`skellycam/core/types/type_overloads.py:12-13`). A grep for `gige|aravis|harvester|genicam|ptp|1588|spinnaker|pypylon|vimba` across `skellycam/`, `skellycam-ui/src` and `pyproject.toml` returned no hits.
- **OpenCV-coupled code a backend would need to bypass or generalize:**
  - `opencv_camera_worker_method.py`, `setup_opencv_camera_loop.py`, `opencv_camera_loop.py` (`cv2.VideoCapture` parameters, `check_framerate_reset`)
  - `camera_loop_update_checks.py:18-27` and `check_for_new_config.py:15-35`, which type the `cv2_video_capture` parameter
  - `opencv_apply_config.py`, `opencv_extract_config.py`, and `recommend_camera_exposure_setting.py`. `camera_config.py:13` imports `ExposureModes` from that last file, so `CameraConfig` itself imports from the opencv helper package.

---

## 3. Frame record dtype in shared memory

- `create_frame_dtype(config)` = `[("frame_metadata", FRAME_METADATA_DTYPE), ("image", np.uint8, (H, W, color_channels))]` with `align=True` (`skellycam/core/types/frame_dtype_factories.py:11-26`). **The image is always uint8**, so there is no 10/12/16-bit path; `IMAGE_DATA_DTYPE = np.uint8` (`type_overloads.py:30-31`).
- `FRAME_METADATA_DTYPE` = `camera_info` (camera_id U128, camera_index i4, rotation i4, color_channels i4), `frame_number` int64, `timebase_mapping` (utc_time_ns, perf_counter_ns, local_time_utc_offset), and `timestamps` (`numpy_record_dtypes.py:10-15,17-21,222-228`).
- `FRAME_LIFECYCLE_TIMESTAMPS_DTYPE` has int64 fields `initialized, pre/post_frame_grab, pre/post_frame_retrieve, pre/post_copy_to_camera_shm, pre/post_frame_record` (`numpy_record_dtypes.py:23-33`). Every write site uses `time.perf_counter_ns()`:
  - `opencv_get_frame.py:53,55,71,73`
  - `opencv_camera_loop.py:95,97,145`
  - `video_recorder.py:101,103`
- **Clock:** host monotonic `perf_counter_ns`. Mapping to UTC uses one `TimebaseMapping` sample of `(time.time_ns(), time.perf_counter_ns(), utc offset)` (`skellycam/core/timestamps/timebase_mapping.py:16-32`). It is created when `CameraGroupIPC` is constructed (`camera_group_ipc.py:24`) and copied into every frame (`create_initial_frame_recarray.py:15`) and the SHM template (`camera_shared_memory_ring_buffer.py:33`). The "main" frame timestamp downstream is the grab midpoint `(pre_grab + post_grab) // 2` (`create_camera_csvs.py:49-51`; `calculate_timestamps_numpy.py:15-32`; `frontend_payload_bytearray.py:100-105`).
- **SHM ring:** one `CameraSharedMemoryRingBuffer` per camera, built from the config-derived dtype (`camera_shared_memory_ring_buffer.py:21-42`). Default allocation is `ONE_GIGABYTE // itemsize` slots per camera (`ring_buffer_shared_memory.py:35-45`). Measured depth for BGR frames (verify log [3]): 1280×720 = 388 slots; 1920×1200 = 155; 2448×2048 = 71; 4096×3000 = 29. Memory is 1 GiB per camera regardless of camera count.
- **Shape and colour assumptions downstream:**
  - The frontend payload rotates, resizes and `cv2.imencode('.jpg')` each image (quality 60, `frontend_payload_bytearray.py:34,107-147`). It works for 1 or 3 channels, but colour order is interpreted as BGR.
  - `VideoRecorder` uses `cv2.VideoWriter(path, fourcc, fps, (w,h))` with no `isColor` argument, so the colour default applies (`video_recorder.py:124-130`). `PyavVideoWriter.write` uses `av.VideoFrame.from_ndarray(frame, format='bgr24')` (`pyav_video_writer.py:25-27`). **Both expect 3-channel BGR.**
  - Recording validation compares a decoded video frame's shape to `config.image_shape` (`recording_finalizer.py:161-163`). For `color_channels=1`, `image_shape` is `(H, W)` (`camera_config.py:155-168`) but the frame dtype holds `(H, W, 1)` (verify log [1]), and decoded video comes back 3-channel. **Mono is therefore not supported end to end today, so a GigE backend should hand the pipeline 3-channel BGR uint8.** (A mono sensor can be `cvtColor(GRAY2BGR)`'d.)
  - The SHM dtype is fixed when the group is created (`camera_group.py:112-117`). `check_for_new_config` re-applies settings but does not resize `frame_rec_array` or SHM (`check_for_new_config.py:30-41`). So a resolution change on a live group (for example after GigE ROI or binning) would mismatch the dtype. I did not trace how the UI handles resolution changes (it may close and recreate the group); this is listed as an open question.

---

## 4. Device detection

- `detect_available_cameras(backend_id=None, filter_virtual=True)` calls `cv2_enumerate_cameras.enumerate_cameras(apiPreference=backend.id)` (`skellycam/core/device_detection/detect_cameras_devices.py:86-109`). It drops "virtual" names, and drops devices without VID/PID except on macOS (`:100-107`).
- `CameraDeviceInfo` (pydantic) has: `index` (required), `name`, `vendor_id`, `product_id`, `path`, `backend_id`, `backend_name`. `camera_id` is a computed 4-hex-character hash of `path`, or of `vid_pid_index`, or the index itself (`:35-55`).
- Endpoint `POST /skellycam/camera/detect?filter_virtual&backend_id` returns `DetectedCamerasResponse{cameras: list[CameraDeviceInfo]}` (`skellycam/api/http/cameras/camera_router.py:60-61,89-100`).
- UI: `skellycam-ui/src/store/slices/cameras/cameras-thunks.ts` maps each detected camera to `createDefaultCameraConfig(camera_id, index, name)` and stores only `vendor_id`/`product_id` as device info (`cameras-thunks.ts:63-97`, file lines). The UI's `CameraConfigSchema` uses `capture_fourcc: z.enum(['MJPG','X264','YUYV','H264'])` and `pixel_format: z.enum(['RGB','BGR','GRAY'])` (`skellycam-ui/src/store/slices/cameras/cameras-types.ts:5,18,35-61`).
- **Where GigE devices would be listed:** add a GigE enumerator (for example `detect_gige_cameras()`) whose `CameraDeviceInfo` rows carry new optional fields: `backend: Literal["opencv","gige"]`, `serial`, `mac`, `ip`, `vendor`, `model`. `camera_id` should hash the serial. `detect_available_cameras` (or the router at `camera_router.py:96`) concatenates both lists.
  - The UI must carry the backend and serial through to `CameraConfig`, because today it builds configs from `index` alone.
  - `camera_router.py:93` types `backend_id: CameraBackendInt` as an OpenCV ID; add a separate `include_gige: bool` query parameter rather than overloading it.
  - GigE discovery relies on broadcast discovery over the NIC (a property of GigE Vision, not of SkellyCam). Expect it to be slower than `cv2_enumerate_cameras`, so it should be optional or cached.

---

## 5. Recording and timestamp CSVs

Flow:
1. `CameraGroup.start_recording` pauses, sets `first_recording_frame_number = max(frame_count)+3`, publishes `RecordingInfoMessage`, and unpauses (`camera_group.py:183-213`).
2. Each worker creates a `VideoRecorder` (`handle_recording_updates.py:24-47`). For each recorded frame, `VideoRecorder.record_frame` rotates the image, writes it, and appends `copy(frame.frame_metadata)` to an in-memory list (`video_recorder.py:87-109`).
3. At stop, each worker publishes `RecordingFinishedMessage(frame_metadatas=list[recarray])` (`handle_recording_updates.py:50-59`).
4. The parent collects these (`camera_group.py:317-379`) and runs `RecordingFinalizer.finalize_recording` (`recording_finalizer.py:53-67`), which calls `process_and_save_recording_timestamps` (`process_and_save_recording_timestamps.py:72-115`):
   - `validate_frame_metadatas` checks equal counts, equal frame numbers across cameras, and a consistent `timebase_mapping` (`:21-69`).
   - `recording_start_time_ns = min(first pre_frame_grab_ns)` (`:81-84`).
   - `process_recording_timestamps` stacks `FRAME_LIFECYCLE_TIMESTAMPS_DTYPE` into `(cams, frames)` and computes durations (`process_recording_timestamps.py:8-33`; `calculate_timestamps_numpy.py:35-80`).
   - `create_and_save_camera_csvs` writes `<rec>/<camera timestamps folder>/<rec>.camera{id}.timestamps.csv` (`create_camera_csvs.py:15-107`; path at `recording_info.py:103-104`). Columns come from `CAMERA_TIMESTAMPS_CSV_ROW_DTYPE` (`numpy_record_dtypes.py:49-79`). It **auto-maps every `FRAME_LIFECYCLE_TIMESTAMPS_DTYPE` field to `frame.<name>.ns` minus `recording_start_time_ns`** (`create_camera_csvs.py:85-89`).
   - `create_and_save_multiframe_csv` writes `<rec>_timestamps.csv`, including `inter_camera.frame_grab_range.ms` = max−min of per-camera grab-midpoint `perf_counter_ns` (`create_multi_frame_csvs.py:13-121`, esp. `:54-58`).
   - Stats summary (`save_timestamps_statistics_summary.py`). `recording_info.save_to_file` dumps every `CameraConfig` to `<rec>_info.json` (`recording_info.py:77-86`).
   - `validate_recording` (`recording_finalizer.py:126-208`).
- Dead or buggy code worth knowing: `create_camera_frame_csv_row_recarray` (`create_camera_csvs.py:110-178`) has no callers (grep). It uses `pre+pre` instead of `pre+post` (`:127-128`) and column names absent from the dtype (`:151-163`).

**Where camera-side hardware (PTP) timestamps could go:**
- *Hot path:* add `('device_timing', DEVICE_TIMING_DTYPE)` to `FRAME_METADATA_DTYPE` (`numpy_record_dtypes.py:222-228`), with fields like:
  - `device_timestamp_ns` int64: GenICam buffer timestamp (PTP clock when PTP is enabled)
  - `device_frame_id` int64: GVSP block ID
  - `device_clock_ptp_status` int8 (or similar)
  - optionally `host_receive_ns` int64 (perf_counter at buffer pop)

  The backend fills these after `grab()`. It should be its own sub-record so that `create_camera_csvs.py:85-89` does not subtract the host `recording_start_time_ns` from a device-clock value.
- *Recording:* metadata already flows through `video_frame_metadata` -> `RecordingFinishedMessage` -> finalizer (`video_recorder.py:108`), so nothing new is needed in IPC.
- *CSV:* add explicit columns to `CAMERA_TIMESTAMPS_CSV_ROW_DTYPE`: `device.timestamp.ns`, `device.timestamp.from_recording_start.sec` (relative to the min first device ts across cameras), and `device.frame_id`. Fill them in `create_and_save_camera_csvs`. Add `inter_camera.device_timestamp_range.ms` to `MULTI_FRAME_TIMESTAMP_CSV_ROW` (`numpy_record_dtypes.py:81-208`) and `create_multi_frame_csvs.py:54-58`. With PTP-locked cameras that column is the true exposure skew; `frame_grab_range` stays the host-side measure.
- *Mapping device clock to host clock:* PTP time is TAI/UTC-based (to be confirmed by the PTP topic). A per-recording linear fit of `device_timestamp_ns` against `host_receive_ns` (or against `utc_time_ns` via `TimebaseMapping`) could be stored next to `timebase_mapping`, or in `<rec>_info.json`, for correlation with other data.
- *UI or websocket:* `frontend_payload_bytearray.py` computes a mean grab timestamp per payload (`:100-105`). It could prefer the device timestamp when present, but that is optional.

---

## 6. Existing tests and mocks to reuse

Full suite run (`research/skellycam-arch-pytest.log`, with `timeout 90 python -m pytest -p no:cacheprovider -q -rfE --tb=line skellycam/tests`): **171 passed, 15 failed, 4 errors in about 8.7 s**. The interpreter then **hangs on exit**: the first run without `timeout` did not exit within 600 s after printing its summary, likely because of lingering worker or monitor threads (not investigated).

Failures are pre-existing and mostly beartype-related:
- `MagicMock` passed where `WorkerRegistry` or `CameraGroupManager` is annotated (`test_camera_group_manager.py`, `test_websocket.py`)
- `MockVideoCapture.set(value: float)` called with an `int` (`skellycam/tests/mocks/test_camera_mock.py:67-68`)
- int/float annotation mismatches in `FramerateTracker.update` and `ms_to_ns`
- one filename assertion: `idx0` vs `idx-0` (`test_frontend_payload_and_recording.py:161`)

Implication: **GigE tests must use real typed objects, or `@runtime_checkable` Protocol types, rather than `MagicMock`, wherever an annotated skellycam function receives them.**

Reusable patterns:
- `skellycam/tests/mocks/camera_mock.py:8-118`: `MockVideoCapture` with `isOpened/read/set/get/release`, rate-limited to FPS. **It has no `grab()`/`retrieve()`**, so it cannot drive `opencv_get_frame` as is. A `FakeGigEBackend` implementing the proposed Protocol is a better fit (prototype in `research/scripts/backend_protocol_prototype.py`).
- `test_frontend_payload_and_recording.py:28-49`: builds real frame recarrays from `CameraConfig` + `create_frame_dtype`, which is a template for testing debayer and device-timestamp fill without hardware. `:105-129` covers the dtype tests.
- `test_camera_orchestrator.py:10-12,73-130`: `CameraOrchestrator.from_statuses({id: CameraStatus()})` exercises the gate without processes.
- `test_shared_memory.py:140-245`: real SHM ring buffer with small `ring_buffer_length`, for a GigE frame dtype round-trip.
- `test_worker_lifecycle.py:45-306`: `WorkerRegistry` in THREAD and PROCESS mode with simple target functions. A fake-backend worker could run in THREAD mode for an integration test.
- `conftest.py:24-127`: FastAPI app with patched `get_or_create_camera_group_manager`. `test_camera_router.py:10-52` shows how to patch `detect_available_cameras` to return `CameraDeviceInfo` rows, so a GigE detect test can do the same with GigE fields.
- For an end-to-end GigE test without hardware, Aravis's `arv-fake-gv-camera` (covered by other topics) can run in Docker. The SkellyCam side only needs the backend's `open()` to accept a fake device ID.

---

## 7. Proposed minimal integration design

### 7.1 New and changed modules
```
skellycam/core/camera/backends/
    __init__.py
    camera_backend.py          # CameraBackend Protocol (+ BackendType enum), DeviceTiming dataclass
    opencv_backend.py          # wraps existing create_cv2_video_capture/apply/extract/grab/retrieve
    gige/
        gige_backend.py        # GenICam/GigE implementation (Aravis or Harvester; chosen by other topics)
        gige_pixel_formats.py  # PFNC name -> cv2 conversion code table
        detect_gige_cameras.py # enumerate -> CameraDeviceInfo rows
skellycam/core/camera/camera_loop.py      # generalized run loop (from opencv_camera_loop.py), takes CameraBackend
skellycam/core/camera/camera_worker_method.py  # generalized entry (from opencv_camera_worker_method.py)
```
Changed files:
- `camera_worker.py:48-49` (target -> generic method)
- `camera_config.py` (new fields)
- `numpy_record_dtypes.py` (device_timing and CSV columns)
- `create_camera_csvs.py` and `create_multi_frame_csvs.py`
- `detect_cameras_devices.py` and `camera_router.py` (GigE listing)
- the UI types and thunks

GigE dependencies should be optional extras (`pip install skellycam[gige]`) so the default install is unchanged.

### 7.2 Interface (prototype-verified with beartype)
```python
@runtime_checkable                      # REQUIRED: beartype rejects plain Protocol hints
class CameraBackend(Protocol):
    def open(self, config: CameraConfig) -> CameraConfig: ...   # returns *extracted* config (real W/H/fps/exposure)
    def apply_config(self, prior: CameraConfig, new: CameraConfig) -> CameraConfig: ...
    def start(self) -> None: ...         # begin acquisition (GigE: AcquisitionStart after all_ready)
    def drain(self) -> None: ...         # replaces the read()-until-all_ready loop
    def grab(self) -> bool: ...          # dequeue next buffer (blocking w/ timeout); record device timing
    def retrieve(self, out: np.ndarray) -> bool: ...  # convert into pre-allocated HxWx3 uint8 BGR view
    def device_timing(self) -> DeviceTiming: ...      # ts_ns, frame_id, ptp_status for the last grab
    def is_open(self) -> bool: ...
    def close(self) -> None: ...
```
Mapping to current code:
- `open` corresponds to `create_cv2_video_capture` (`create_cv2_video_capture.py:31-88`)
- `apply_config` corresponds to `apply_camera_configuration` (`opencv_apply_config.py:50-103`)
- `grab`/`retrieve` correspond to `opencv_get_frame.py:53-73`
- `is_open`/`close` correspond to `isOpened()`/`release()` (`opencv_camera_loop.py:78`, `opencv_camera_worker_method.py:77-78`)

The generic loop keeps the gate, recording-flag ordering, SHM put, and recorder code unchanged (`opencv_camera_loop.py:60-116`). It writes `device_timing` into `frame_rec_array.frame_metadata.device_timing[0]` after a successful grab. `check_framerate_reset` becomes backend-specific and opt-in, because it hard-codes 30 fps.

Prototype result (`backend-protocol-prototype.log`):
- `isinstance(FakeGigEBackend(), CameraBackend)` returns True, and a `@beartype` function annotated with it accepts the fake.
- It rejects a non-conforming object with `BeartypeCallHintParamViolation`.
- A plain (non-runtime-checkable) Protocol hint raises `BeartypeDecorHintPep3119Exception` at decoration.
- The fake filled the real `create_frame_dtype` recarray; its RGGB red frame came out as BGR `(0,0,200)`.

### 7.3 Representing a GigE camera in CameraConfig
Add fields with backward-compatible defaults, so existing UI payloads (which omit them) still validate:
```python
backend: Literal["opencv", "gige"] = "opencv"
device_id: str | None = None        # GigE: serial number (stable); fallback MAC "00:11:22:..."; or IP
device_address: str | None = None   # optional IP/interface hint for unicast open on multi-NIC hosts
source_pixel_format: str | None = None  # e.g. "BayerRG8", "Mono8" (reported by device, informational)
ptp_enabled: bool = False           # request GevIEEE1588/PtpEnable (feature name per SFNC; other topics)
```
- `camera_index` stays required and unique (`camera_config.py:386-390`). It is used in worker names (`camera_worker.py:50`), video filenames (`parse_video_filename.py:83-90`), the frame `camera_info`, and the frontend header. So the GigE detector should assign stable synthetic indices that do not collide with OpenCV indices (for example 1000+ in enumeration order). Alternatively, change the uniqueness check to `(backend, device_id or camera_index)`; that requires checking the filename parser and UI too.
- `capture_fourcc` is meaningless for GigE. Leave the default so UI zod validation passes (`cameras-types.ts:59`).
- `camera_id` for GigE = hash of serial, mirroring `CameraDeviceInfo.camera_id` (`detect_cameras_devices.py:44-54`).
- The UI needs to round-trip `backend` and `device_id`. Today `createDefaultCameraConfig` only takes `(id, index, name)` (`cameras-thunks.ts:68-72`), so without a UI change GigE configs would arrive as `backend="opencv"`.

### 7.4 Bayer and mono to BGR uint8
- `retrieve(out)` converts the raw GVSP payload (an `np.frombuffer` view of the GenICam buffer, H×W uint8 for 8-bit formats) straight into the SHM-bound recarray slot with `cv2.cvtColor(raw, code, dst=out)`.
- Measured in `skellycam-arch-verify.log` [4]: the output *is* the recarray view (`np.shares_memory` True), so there is no extra copy. Measured cost on this machine: 640×480 about 40 µs; 2448×2048 about 0.18 ms (random data, OpenCV 4.12; real-world cost depends on CPU and threading).
- **Code mapping** (empirically verified [5]: pure-red mosaic with R at pixel (0,0)): `COLOR_BayerBG2BGR` gives red `(0,0,255)`; `COLOR_BayerRG2BGR` gives blue. The table therefore maps by layout, *not* by name:
  - RGGB -> `COLOR_BayerBG2BGR`
  - BGGR -> `COLOR_BayerRG2BGR`
  - GRBG -> `COLOR_BayerGB2BGR`
  - GBRG -> `COLOR_BayerGR2BGR`

  The last two follow the same OpenCV convention; I only tested RGGB directly. PFNC's `BayerRG8` = RGGB with R at (0,0) is an assumption to confirm against the PFNC spec (genicam topic).
- `Mono8` -> `cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR, dst=out)`, since mono is not supported end to end (section 3).
- `>8-bit` (`Mono12/BayerRG12`, packed or unpacked) needs unpack and shift to uint8 first, because the dtype is uint8-only (`frame_dtype_factories.py:21`). Prefer configuring the camera to an 8-bit `PixelFormat` (`BayerXX8`/`Mono8`) for v1.
- Do the colour conversion in `retrieve()` so the existing `pre/post_frame_retrieve_ns` brackets time it (`opencv_get_frame.py:71-73`).
- Decide whether GigE frames should get the burned-in text overlay (`opencv_get_frame.py:80-84`). It alters recorded pixels; probably make it backend-agnostic and optional.

### 7.5 Threading PTP timestamps through
1. `gige_backend.grab()` pops a buffer, records `host_receive_ns = perf_counter_ns()`, and reads the buffer's device timestamp and frame/block ID (API per library: other topics).
2. The generic loop copies them into `frame_metadata.device_timing[0]` (new sub-dtype, section 5), next to `pre/post_frame_grab_ns`.
3. They flow automatically into SHM (`opencv_camera_loop.py:95-97`), the recorder's `video_frame_metadata` (`video_recorder.py:108`), `RecordingFinishedMessage`, and the finalizer.
4. CSV: new explicit `device.*` columns per camera, plus `inter_camera.device_timestamp_range.ms` per multiframe.
5. Optional: a per-camera `ptp_status` sample at recording start (e.g. PTP state "Slave/Master", offset from master), stored in `<rec>_info.json` via `CameraConfig` fields (`recording_info.py:77-86`).
6. Drop detection: if `device_frame_id` is non-consecutive while `frame_number` is consecutive (`video_recorder.py:149-156`), log or flag it. Optionally match by nearest device timestamp in the finalizer instead of by host frame count.

---

## 8. Doc vs code discrepancies noticed (for the report's credibility)
- `precise-timestamps.mdx:159` says the TimebaseMapping is "created once at recording start". Code creates it with `CameraGroupIPC` (`camera_group_ipc.py:24`), i.e. at camera-group creation.
- `precise-timestamps.mdx:148` links `core/camera/config/timebase_mapping.py`; the actual path is `skellycam/core/timestamps/timebase_mapping.py`.
- `architecture.mdx:164` describes a second multi-frame shared memory buffer. Code assembles multiframes by reading the per-camera rings directly (`camera_group_shared_memory.py:129-141`).
- `architecture.mdx:165` says JPEG quality 80; code uses 60 (`frontend_payload_bytearray.py:34`).
- `frame-synchronization.mdx:46-56` line references (e.g. `opencv_camera_loop.py:66-68`) are slightly stale (pause is now `:63-65`, gate `:67-69`).
- `opencv_get_frame.py:30-33` claims all cameras grab before any retrieves; the code has no such cross-camera ordering (section 1).

## Open questions
- How does the UI handle a resolution change on a running group? Does it recreate the group, since the SHM dtype is fixed at creation, or does it break?
- Why does the pytest process hang after the test summary? (Possibly WorkerRegistry heartbeat or monitor threads; not investigated.)
- PFNC `BayerRG8` pixel order (R at (0,0)) needs confirming from the PFNC spec or genicam topic before relying on the code table.
- Should the burned-in overlay text stay in recorded GigE video?
