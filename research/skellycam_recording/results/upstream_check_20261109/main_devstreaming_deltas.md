## Upstream commits not in sfn26: effect on recording behaviour

None of the 5 commits changes any recording behaviour in REPORT.md. That covers folder layout, writer/codec, header frame rate, timestamps, finalize, R1–R11, the kill-flag and hard-kill rows in section 6, `GET /shutdown` and audio. Only two of them touch failure or shutdown code at all, and neither runs while a recording is in progress. sfn26 already has its own version of 169caf63. It has none of the 3 upstream/main commits. Everything below comes from reading the code; nothing was built or run.

### upstream/main, not in sfn26 (3 commits)

- **524e5fc5 – Remove vid/pid check when virtual cameras included (#143)**
  - **Affects recording:** no. It only changes which devices camera detection lists.
  - **Evidence:** the VID/PID filter now applies only when `filter_virtual` is true (`upstream/main:skellycam/core/device_detection/detect_cameras_devices.py:102`). This means virtual cameras without a VID/PID can now be opened and recorded. They go through the same OpenCV recording path, so the findings apply to them unchanged (inferred).
  - **In sfn26:** no. sfn26 still filters on VID/PID regardless of `filter_virtual` (`upstream/sfn26:skellycam/core/device_detection/detect_cameras_devices.py:102-106`).

- **26509b06 – Better process closure for pubsub (#144)**
  - **Affects recording:** no.
  - **What it changes:** `PubSubTopicABC.close()` now calls `sub.cancel_join_thread()` after `sub.close()` (`upstream/main:skellycam/core/ipc/pubsub/pubsub_abcs.py:81`).
  - **Where `close()` is called:** only from `PubSubTopicManager.close()` (`upstream/main:skellycam/core/ipc/pubsub/pubsub_manager.py:61`). That in turn is called only when `create_camera_group_pubsub_manager` replaces an existing manager for the same group_id (`pubsub_manager.py:78-80`). Neither group close nor server shutdown calls it.
  - **R1:** unchanged. The `RECORDING_FINISHED` message on a kill-flag exit is still never finalized.
  - **R7:** unchanged. Stale messages stay queued in the live group's subscription, and this code never closes it.
  - **`GET /shutdown` hard-kill:** unrelated. The commit targets a feeder-thread join that hangs at exit. The finding is a forced exit with code 15, and the shutdown route is not touched.
  - **In sfn26:** no. sfn26's `close()` has no `cancel_join_thread` (`upstream/sfn26:skellycam/core/ipc/pubsub/pubsub_abcs.py:50-59`). Its only `cancel_join_thread` is on the worker's log queue (`upstream/sfn26:skellycam/core/ipc/process_management/managed_worker.py:257`), which is a different queue.

- **06771043 – Aaron/better logging configurations (#145)**
  - **Affects recording:** no. It changes logging only.
  - **What it changes:** `configure_logging` moves out of `skellycam/__init__.py` into `entry_point()` (`upstream/main:skellycam/__main__.py:100`). Worker processes now log with `use_file_handler=False` (`upstream/main:skellycam/core/ipc/process_management/managed_worker.py:183`), so they no longer write their own log files.
  - **Recording files:** none written, closed or finalized by any recording code are touched.
  - **In sfn26:** partly, in a different form. sfn26 also stopped configuring logging on import (`upstream/sfn26:skellycam/__init__.py:24-27`) and does it in `__main__` (`upstream/sfn26:skellycam/__main__.py:99-102`), without `log_file_path`. Its workers still call `configure_logging(LOG_LEVEL, ws_queue=log_queue)` without `use_file_handler=False` (`upstream/sfn26:.../managed_worker.py:226`).

### upstream/development-streaming, not in sfn26 (2 commits)

- **a92cae3e – Fix SkellyCam CI checks**
  - **Affects recording:** no.
  - **Evidence:** the CI matrix (drops Python 3.10, Node 20→22, `uv sync --python`) and a UI barrel export (`skellycam-ui/src/store/index.ts`). The Python changes are only `# noqa: TC00x` comments on imports, including in `recording_finalizer.py`, `video_filename.py`, `sequential_video_reader.py` and `opencv_camera_loop.py`. One trailing blank line is removed from `video_filename.py`. No logic changes.
  - **In sfn26:** no. sfn26's `.github/workflows/test.yml` still has 3.10 (line 30), Node 20 (line 69) and plain `uv sync --group dev` (line 47).

- **169caf63 – Preserve camera startup failures across worker processes**
  - **Affects recording:** no. It only touches camera open and group join, before any recording.
  - **What it changes:**
    - `create_cv2_video_capture` releases the capture before raising (`upstream/development-streaming:skellycam/core/camera/opencv/opencv_helpers/create_cv2_video_capture.py:46,85`).
    - The setup failure handler now goes through `ipc.report_setup_failure(...)` (`setup_opencv_camera_loop.py:72`). This puts a `CameraSetupFailure` on a `SimpleQueue` and sets `shutdown_camera_group_flag` (`camera_group_ipc.py:37-47`). The old code ran `ipc.should_continue = False`, whose setter sets the same flag (`camera_group_ipc.py:82-85`).
    - The handler also releases the capture (`setup_opencv_camera_loop.py:75`).
    - `await_extracted_configs` raises when it finds a recorded failure or any camera without a config (`camera_group.py:319-325`).
  - **Kill flag:** not changed. Before and after, startup failure sets only the group flag, never `global_kill_flag`.
  - **R1, R8, the `VideoRecorder.create` row and the kill-flag rows in section 6:** not touched. The camera-loop exception handler and its `finally`, `finish_recording`, the orchestrator waits and the finalizer are unchanged in development-streaming (`opencv_camera_loop.py:126-135`).
  - **In sfn26:** yes, as a separate and wider implementation.
    - sfn26 stores the first failure in a shared `multiprocessing.Array` through `report_camera_failure` (`upstream/sfn26:skellycam/core/camera_group/camera_group_ipc.py:30-41`).
    - It releases the capture and closes shared memory on setup failure (`upstream/sfn26:.../setup_opencv_camera_loop.py:79-95`).
    - `await_extracted_configs` raises with that message and has a 30 s timeout (`upstream/sfn26:skellycam/core/camera_group/camera_group.py:367-385`).
    - sfn26 also calls `report_camera_failure` on runtime camera-loop and worker exceptions (`upstream/sfn26:.../opencv_camera_loop.py:127`, `opencv_camera_worker_method.py:67`). development-streaming does not, so sfn26 goes further. That runtime part belongs to the sfn26 assessment, not this one.