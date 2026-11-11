# How skellycam timestamps frames today, measured against the USB camera research

Written 2026-11-08. Code read at `dom/research` @ `55f851e4` (no uncommitted changes under `skellycam/`). Paths are relative to the repo root.
Labels as elsewhere in this study: **measured** (a result file supports it), **code** (read from the source), **inferred** (reasoned, not tested).

**Verification.** An independent sub-agent checked every claim in the first draft against the code, the cited research files, OpenCV upstream source (4.x HEAD; skellycam pins `opencv` 4.12.*) and the raw captures, which it re-analysed itself. The first draft got the central mechanism wrong (it assumed DirectShow `grab()` waits for or delivers a frame). This version includes its corrections. The two most consequential ones (DirectShow `grabFrame` and `SampleCB`, and the local ISO 8601 bug) were re-checked by hand. The OpenCV sources it read were kept in the session scratchpad.

## 1. Summary

- **skellycam stamps each frame with the host clock when its loop calls `cap.grab()`.** On Windows it uses OpenCV DirectShow, where `grab()` is a no-op: it only checks that the device is still connected. The frame is actually obtained in `retrieve()`, which waits for the oldest unread frame. So the stored timestamp is **not tied to when the frame arrived**. (**code**: OpenCV `cap_dshow.cpp`)
- **The error goes both ways and is up to about one frame period**, on top of the 16 ms delivery grid: early when `retrieve()` then has to wait for the frame, late when the frame sat waiting while the lockstep gate held the camera. (**inferred** from the code; never measured)
- **No camera or driver timestamp is read anywhere.** OpenCV DirectShow exposes none (no `CAP_PROP_POS_MSEC` support), and skellycam reads none on any backend. (**code**)
- **freemocap ignores even these stamps.** Recorded videos are constant frame rate, skellytracker uses `frame_number / fps`, and triangulation pairs frames by index (`research/rolling_shutter/README.md`; §2.8).

## 2. What the code does

### 2.1 Backend
`skellycam/core/camera/determine_backend.py`:
- Windows: `cv2.CAP_DSHOW` (line 42). The comment (lines 34–39) says DirectShow honours `CAP_PROP_BUFFERSIZE` and MSMF does not. **The comment is wrong**: OpenCV's DirectShow `setProperty` has no `CAP_PROP_BUFFERSIZE` case, so `set()` returns False and the value is ignored (`cap_dshow.cpp` 3462–3632).
- Linux: `cv2.CAP_V4L2` (line 57).
- macOS and other: `CAP_AVFOUNDATION` if `cv2_enumerate_cameras` lists it, otherwise the first listed backend, otherwise `cv2.CAP_ANY` (lines 59–67).

### 2.2 Capture setup
`skellycam/core/camera/opencv/opencv_helpers/create_cv2_video_capture.py`:
- Sets `CAP_PROP_FOURCC` (line 54), then width and height (55–56), then FPS only if `config.framerate > 0` (58). The default framerate is −1.0 (`camera_config.py:26`), so FPS is normally **never set**. Then `CAP_PROP_BUFFERSIZE = 1` (62), which DirectShow ignores. Default capture FOURCC: `MJPG` (`camera_config.py:28`).
- After the first `read()`, `apply_camera_configuration` (`opencv_apply_config.py:62-85`) sets exposure, then width and height, then **FOURCC again**, with `should_apply_framerate = False`. So the final order is size, then FOURCC.

### 2.3 Grab and retrieve
`skellycam/core/camera/opencv/opencv_helpers/opencv_get_frame.py`:
- Lines 53–55: `pre_frame_grab_ns`, `cap.grab()`, `post_frame_grab_ns`, all from `time.perf_counter_ns()`.
- Lines 71–73: the same around `cap.retrieve()`.
- **What these calls do on OpenCV DirectShow** (**code**, `cap_dshow.cpp`):
  - `grabFrame()` is `return !g_VI.isDeviceDisconnected(m_index);` (line 3639). It neither waits nor touches a frame.
  - `retrieve()` → `getPixels` waits up to 1 s on the frame-ready event, copies the frame, then resets the event (lines 1551–1590).
  - The capture callback `SampleCB` **discards each new sample while a frame is still unread** (lines 703–716). So `retrieve()` returns the oldest unread frame, the first to arrive after the previous `retrieve()`, not the newest.
  - With MJPG, the sample grabber's type is forced to RGB24 (line 2904), so DirectShow decodes the MJPEG in its graph on its own streaming thread. `retrieve()` only waits and copies or flips.
- After `retrieve()`, a text overlay (camera id, index, frame number) is drawn into the image itself (line 81). It ends up in every frame passed downstream and recorded.

### 2.4 The frame timestamp
- **The midpoint of the two grab stamps**: `skellycam/core/timestamps/numpy_timestamps/create_camera_csvs.py:50-51`, written to `timestamp.perf_counter_ns.ns` at line 58.
- On Windows `perf_counter_ns` is QPC, so the stored value is **the QPC time at which the loop called a no-op `grab()`**.
- Other uses of the grab stamps:
  - live performance view: midpoint (`skellycam/api/websocket/performance_data.py:67`);
  - frontend payload: mean of pre and post grab (`frontend_payload_bytearray.py:99-104`);
  - multiframe CSV: the mean of the per-camera stamps across cameras (`create_multi_frame_csvs.py:44-45`);
  - **recording start time**: the minimum `pre_frame_grab_ns` (`process_and_save_recording_timestamps.py:82-84`).
- `calculate_frame_grab_timestamps` (`calculate_timestamps_numpy.py:30`) also computes the midpoint but has no callers.

### 2.5 Wall-clock conversion
`skellycam/core/timestamps/timebase_mapping.py`:
- One (`time.time_ns()`, `time.perf_counter_ns()`) pair (lines 22–23), created once per `CameraGroupIPC` (`camera_group_ipc.py:24`), converts every stamp to UTC or local ISO 8601.
- On Python 3.12, `time.time_ns()` comes from `GetSystemTimeAsFileTime`, so the UTC anchor can be off by up to one system-timer tick (`docs/windows_timer_resolution.md`, "Effect of moving the test scripts to Python 3.13").
- **Bug: the local ISO 8601 string applies the UTC offset twice.** `convert_perf_counter_ns_to_local_iso8601` gets a unix time with the local offset already added (`local_time=True`, line 31), then calls `datetime.fromtimestamp(..., tz=LOCAL_TIMEZONE)` (line 42), which converts to local time again. At UTC−5 a true 06:06 prints as 01:06 (sub-agent demo). It's invisible at UTC+0, and the test (`tests/test_timestamps_and_framerate.py:118-125`) doesn't catch it. The multiframe CSV computes local time correctly (`create_multi_frame_csvs.py:50-52`), so the per-camera and multiframe CSVs disagree.

### 2.6 Lockstep
- `skellycam/core/camera_group/camera_orchestrator.py:96-109`: a camera may grab only when all cameras are ready and its frame count is ≤ every other camera's.
- `opencv_camera_loop.py` polls this gate with `wait_10us` (per the sub-agent, it really sleeps about 0.5 ms). A camera updates its `frame_count` only after retrieve, shared-memory copy and recording (line 116), so the gate waits for every peer's full iteration.
- Frame *k* is therefore taken from every camera before any camera takes *k+1*. Frames are grouped by index into multiframes, and `validate_frame_metadatas` requires equal frame numbers.
- Retries after a failed grab or retrieve (loop lines 72–85) overwrite the stamps. A `retrieve()` timeout (1 s) shows up as a failed frame.

### 2.7 Frame-rate reset
`check_framerate_reset` (`opencv_camera_loop.py:150-170`) hard-codes a 30 fps target. It can release and recreate one camera mid-stream while the frame numbers carry on.

### 2.8 Recorded videos
Video writers are constant frame rate:
- PyAV sets `pts = frame_count` at `rate=round(fps)` (`pyav_video_writer.py:14, 28`);
- the cv2 writer uses the loop's median measured rate or the config value.

The variable-frame-rate remux from grab stamps is commented out (`recording_finalizer.py:63`).

## 3. Problems, measured against the research

| # | Issue | Effect | Status |
| --- | --- | --- | --- |
| P1 | **The stamp brackets no delivery event** | On OpenCV DirectShow the stamp is the time the loop asked, not when the frame arrived. The research measured **MF** arrival on the C922 at 4.6–5.0 ms std, and MF sample time at 4.4–4.5 ms, against the flash ground truth (REPORT.md finding 7 and the timestamp-sources table). No DirectShow arrival was scored, and skellycam's stamp doesn't follow arrival anyway. | code (mechanism); MF figures measured |
| P2 | **Lockstep error in both directions** | Early when `retrieve()` then blocks for a frame that hasn't arrived; late when the frame waited through the gate. Lateness is bounded by the slower peer's period (~39 ms at 25.7 fps) plus that peer's loop time. Newer frames that arrive while one is unread are **dropped**, and `CAP_PROP_BUFFERSIZE = 1` has no effect on DirectShow. | code (mechanism); size inferred, never measured |
| P3 | **Index pairing assumes simultaneous capture** | Cameras run freely, and each camera's frame *k* is "the first frame after its previous retrieve", so frame *k* of two cameras can differ by up to about one period. Half a period is only the best case, for nearest-neighbour pairing. | inferred |
| P4 | **The docstring's assumptions are off** | `opencv_get_frame.py` says driver jitter is "~0.1-1ms" (line 26), readout "~10-20ms" (line 28), that DSHOW `grab()` "calls IMediaSample delivery", and that buffer_size=1 gives the newest frame (36–39). Measured instead: a 16 ms delivery grid on MF, WinRT, GStreamer `mfvideosrc`/`ksvideosrc`, SDL3 and nokhwa (`docs/windows_timer_resolution.md` §"Other Windows timestamp sources"; not measured on OpenCV DSHOW), and a fitted ~31 ms row term per frame height with a 35 ms spread across image blocks for both the C922 and the C930e at 720p30. Readout and display scan-out cannot be separated in that figure (`timing/VERIFY_method.md` §1). The DSHOW claims are contradicted by `cap_dshow.cpp` (§2.3). | measured / code |
| P5 | **Better sources are ignored** | OpenCV DirectShow gives no sample time at all (`SampleCB` ignores the sample time; `getProperty` has no `CAP_PROP_POS_MSEC` case, so it returns −1). UVC PTS/SCR need Media Foundation plus the metadata registry value (REPORT.md timestamp table), or libusb on WinUSB, which is out of scope. On Linux, OpenCV V4L2 returns the driver's buffer timestamp as `CAP_PROP_POS_MSEC` (`cap_v4l.cpp:997`, 1849–1853), and skellycam doesn't read it. | code |

## 4. Smaller code issues

- **The local ISO 8601 bug** (§2.5): a double UTC offset in `timebase_mapping.py:31` and `:42`.
- **False comments about the buffer size**: `determine_backend.py:34-39` and `create_cv2_video_capture.py:21-27` say DirectShow honours `CAP_PROP_BUFFERSIZE`. It doesn't.
- **Two dead functions**:
  - `create_camera_frame_csv_row_recarray` (`create_camera_csvs.py:110`) computes `(pre_frame_grab_ns + pre_frame_grab_ns) // 2` at lines 127–128 (pre-grab, not the midpoint its comment promises);
  - `calculate_frame_grab_timestamps` (`calculate_timestamps_numpy.py:30`).
  
  Neither has callers. Fix or delete.
- **Format negotiation order.** The research found that FOURCC-first on OpenCV DirectShow can end in YUY2 at ~10 fps (`mjpeg/RESULTS.md` lines 125–127, a `CONVERT_RGB=0` run on 10-25). The 11-06 suite reproduced YUY2 at ~9.97 fps with FOURCC-first on the C922 and C930e (`results/windows/Gerald/suite_20261106T224912Z/W-CYC/*/opencv_inproc_cycles.json`). skellycam creates FOURCC-first but re-applies size-then-FOURCC after the first read (§2.2). `cap_dshow.cpp` 3567–3570 then restarts the graph with `setIdealFramerate(getFPS())`, which carries over the YUY2 rate, so **MJPG at ~10 fps is a plausible outcome** (inferred). skellycam's full sequence is untested; `cyc_kiyo.md` B4 already flags it.
- **The overlay in the image** (§2.3), and the **hard-coded 30 fps reset** (§2.7).

## 5. Open points

- **How big P1–P3 are in practice.** Run skellycam with two cameras of different rates (C922 plus the generic camera) next to an MF reference that has UVC PTS on the C922, and compare the stored stamps with the reference.
- **The Linux `CAP_PROP_POS_MSEC` clock.** It is CLOCK_MONOTONIC unless uvcvideo has `clock=realtime`. It's stamped when the first payload of a frame is processed, on a ~4 ms URB grid, unless `hwtimestamps=1` replaces it with the camera-clock-derived time. Kernel version (6.8 / 6.11 / 7.2) affects hardware-timestamp quality (`results/agent_reports/plan_20261106/linux.md` lines 122–145).
- **The format negotiation sequence** (§4), on the actual skellycam code path.

## 6. Steps before and toward a backend change

1. **Stop using the grab midpoint on DirectShow.** `post_frame_retrieve_ns` is closer to arrival when `retrieve()` actually blocked (that is, when `post_frame_retrieve_ns − pre_frame_retrieve_ns` is long), although it includes DirectShow's MJPEG decode. A frame-slot fit (`t_k = a + P·k`, lower envelope, drop detection) should use those post-retrieve stamps, not the grab stamps.
2. **On Linux, store `CAP_PROP_POS_MSEC`** next to the grab stamp.
3. **Fix the local ISO 8601 bug and the false buffer-size comments.**
4. **Move Windows capture to Media Foundation.** It gives real delivery times (sample time, arrival) and the UVC metadata needed for tier 1 and tier 2. This is the change the research already recommends.

## Appendix: metadata check on Gerald, 2026-11-08

Context for P5. `MetadataBufferSizeInKB0 = 5` was set (with `-NoRestart`, then a replug by Dom) on the current instances and every stale C930e, Kiyo and generic instance. A read-only registry query by the sub-agent found the value on all 13 MI_00 instances of the four cameras, under both interface classes. Short `timing/build/mf_uvc_timing.exe` runs at 1280x720@30 MJPEG. Raw output was kept in the session scratchpad only, not in `results/`.

| | C922 | C930e | Kiyo Pro | Generic |
| --- | --- | --- | --- | --- |
| Frames with the UVC item | 142/142 | 288/288, 288/288, 137/137 (three runs) | 134/134 | 0/102: the capture-metadata store is present but empty |
| Metadata items | only id 2 (`MetadataId_UsbVideoHeader`), 40 bytes | same | same | none |
| PTS | 300 MHz, steps 9,952,800–10,047,200 ticks | regular steps plus ±1 ms jumps (below) | 1 kHz counter, steps 28–43 | — |
| STC | 300 MHz, steps 9,995,000–10,003,400 | 30 MHz, steps 997,518–999,024 | all steps multiples of 30,000 (1 ms) | — |
| SOF | 885.5/s (broken) | 999.9/s (999.5 in the 137-frame run) (real) | always 0 | — |
| Last-payload SCR differs from first | yes, 142/142 | no, identical in every frame | no | — |

- **C930e PTS.** In the 288-frame run at fixed exposure −7, 273 of 287 steps are within ±50 ticks (±1.7 µs) of 997,222. Ten steps are ±30,000 ticks (±1 ms) in cancelling pairs, and two are about +2,100. The step size varies between sessions: the 137-frame run with auto exposure (flags = 1) has a median step of 999,304. The second 288-frame run, labelled "auto", actually ran at exposure −5 in manual mode (flags = 2), so auto was not engaged. The pattern of regular steps plus ±1 ms corrections holds in all three runs. Its PTS is not a capture time. Use the STC.
- **The 40-byte item** is an 8-byte item header plus `KSSTREAM_UVC_METADATA`: two 16-byte records, PTS (4), SCR STC (4), SCR token (2; 11-bit SOF counter), Reserved0 (2), Reserved1 (4), taken from the frame's first and last payloads (Microsoft "UVC extensions 1.5" §2.2.3.4.5). It is not the raw payload header: the flags byte (FID, EOF, error) is missing.
- **Generic camera.** The 0/102 result came from a **two-camera** run with the C922, in which the C922 got 0 frames (`errors: 21`; the console showed `ReadSample hr=0x800718cf`, which isn't kept in the session files). A separate solo `wincam` run on the generic camera (60 frames: store present, no UVC item) agrees. In the 11-06 run, metadata-off cameras had no capture-metadata store at all (`W-FMT-NOGRAB.json`: C930e and generic 0 frames, C922 and Kiyo all frames). So the empty store shows the registry value took effect, and the camera's headers most likely carry no PTS/SCR (**inferred**).
- **Topology after the replugs.** The Kiyo is behind a Genesys 05E3:0610 hub at Intel root port 12 (`USB(12)#USB(4)`), probably at USB 2.0 speed. The C930e is on root port 8. The C922 and generic camera are on a hub **behind the Kiyo's hub** (`USB(12)#USB(1)#USB(4/2)`), so all three share one upstream USB 2.0 link at root port 12. That explains why the C922 and generic camera can't stream together.
