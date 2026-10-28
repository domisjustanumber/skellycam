# Fact-check: skellycam-arch (verifier notes, 2026-10-25)

Repo: SkellyCam `development` @ 23ccbf208e43879bfc74fc01049e5af2a623933d (committed 2026-07-21; present on upstream freemocap/skellycam development+main).
Permalink base: https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/

Scripts I wrote and ran (scratch venv `research/venvs/skellycam-arch`, python -I; cv2 4.12.0, numpy 2.2.6, beartype 0.23.1):
- research/src/verify-skellycam-arch/bayer_and_dst.py  -> RGGB: BayerRG2BGR=(255,0,0) [blue], BayerBG2BGR=(0,0,255) [red]; SHM slots 388/155/71/29; cvtColor dst shares memory with recarray; 0.14 ms median at 2448x2048; mono dtype (720,1280,1) vs image_shape (720,1280)
- research/src/verify-skellycam-arch/beartype_protocol.py -> runtime_checkable ok/BeartypeCallHintParamViolation; plain Protocol -> BeartypeDecorHintPep3119Exception
- research/src/verify-skellycam-arch/mono_paths.py -> cv2.imencode works on (H,W,1); cv2.VideoWriter(mp4v, isColor default) logs "writeFrame write frame skipped - expected 3 channels but got 1" and writes 0 frames; PyAV from_ndarray(bgr24) raises ValueError on (H,W,1)
- pytest: 15 failed, 171 passed, 4 errors (reproduced). A subset run hung after finishing and was killed by `timeout 100` (rc=124). Log: research/verify-arch-pytest.log

## Verdicts
A1 supported. A2 supported. A3 supported (+ missed recording-start alignment). A4 supported.
A5 partially: threshold is >30 (31) consecutive, only after frame_number>100, "slow" = >66.7 ms (2x 1/30 s), and the duration is measured from previous_tik set at opencv_camera_loop.py:82 (after grab/retrieve) so it measures post-retrieve processing (SHM write + recording), not the inter-frame interval.
A6 supported. A7 supported.
A8 partially: code claim correct; doc citation wrong. precise-timestamps.mdx is 108 lines; "created once at recording start" is line 56, broken TimebaseMapping link (skellycam/core/camera/config/timebase_mapping.py) is line 45.
A9 partially: JPEG path works for mono. The real mono failure is earlier: cv2.VideoWriter drops 1-channel frames (0 frames written) and PyAV raises; the decoded video is always 3-channel anyway.
A10 supported (independently computed itemsizes 2765432/6912632/15041144/36864632).
A11 supported. A12 supported. A13 supported. A14 supported (tested with beartype 0.23.1; uv.lock pins 0.22.9).
A15 supported (17 of 19 failures/errors are beartype violations; the other two are test_stop_recording 500!=200 and an 'idx0' filename assertion).
A16 supported (0.14 ms here). A17 supported. A18 supported.
A19 partially: architecture.mdx:164-165 and quality 60 are correct; precise-timestamps line is 45, not 148.
A20 supported.

## Missed points
1. Recording start: CameraGroup.start_recording pauses all cameras, sets first_recording_frame_number = max(frame_count)+3, publishes info, then unpauses (camera_group.py:183-208); should_record_frame_number gates frames (camera_orchestrator.py:80-94).
2. Cross-camera pairing is by equal host frame_number: latest_multiframe_number = min over cameras (camera_group_shared_memory.py:34-35); get_latest_multiframe raises on mismatch (:129-141); validate_frame_metadatas requires identical numbers (process_and_save_recording_timestamps.py:41-48); VideoRecorder requires consecutive numbers (video_recorder.py:149-156). Device-side drops would be silently mispaired; a GigE backend must keep frame_number as the host lockstep counter and store the device block ID separately.
3. CameraStatus.grabbing_frame is written (opencv_camera_loop.py:70,93) but never read anywhere.
4. Prior art in the user's fork: origin/dom/openpnp-capture (3be07237, 2026-05-13) swaps camera_worker.py's import to openpnp_camera_worker_method (no abstraction); local-only branch dom/openpnp-capture-mf commit 4a086a74 (2026-05-19) put hardware_timestamp_ns into FRAME_LIFECYCLE_TIMESTAMPS_DTYPE + CSV column 'frame.hardware_timestamp.ns', i.e. exactly the pattern A12 warns would get the host recording start subtracted.
5. detect_available_cameras drops devices with no VID/PID on Windows/Linux (detect_cameras_devices.py:102-106) and camera_id is a 16-bit hash (4 hex chars, :44-54), so collisions are possible; GigE rows need a different path.
