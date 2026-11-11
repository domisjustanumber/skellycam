# Completeness critique: REPORT.md findings vs upstream/sfn26 (765bf82d), main and development-streaming

Everything here comes from static reading with `git show` and `git grep`; nothing was built or run. "Inferred" marks a prediction. Python is still the default backend on sfn26 (`upstream/sfn26:skellycam/core/camera_group/camera_backend_manager.py:26,30`), so every "python" verdict describes what users get by default.

## (a) Findings that were not checked, now checked on sfn26

**A1. §1 bullet 1: each camera process encodes synchronously inside the capture loop**
- **python: UNCHANGED.** `handle_video_recording` is still called inline in the loop (`upstream/sfn26:skellycam/core/camera/opencv/opencv_camera_loop.py:106-112`), so a slow write still holds up every camera in lockstep.
- **rust: CHANGED.** Encoding runs in a recording thread and one ffmpeg child process per camera. The dispatcher only queues frames:
  - `upstream/sfn26:skellycam-rust/src/camera_group/dispatcher.rs:298-321`
  - `upstream/sfn26:skellycam-rust/src/recording/recording_thread.rs:96-101,280-314`
- Capture is no longer blocked by encoding, but see C1 in (c): a blocked ffmpeg can now hang the whole recording.

**A2. §4, codec choice per platform** (Linux falls back to `X264_PYAV`, macOS probably gets `avc1`, Windows tries FFmpeg/OpenH264 before MSMF)
- **python: UNCHANGED.** No diff to `fourcc_codec_helpers.py` (`git diff --stat 23ccbf20 upstream/sfn26 -- skellycam/core/recorders/videos/fourcc_codec_helpers.py` is empty). OpenCV is still pinned to 4.12.0.88, so whether OpenH264 is used still depends only on whether its DLL is present.
- **rust: NOT_APPLICABLE.** libx264 is used on every OS. macOS and Linux capture and recording are untested (`upstream/sfn26:skellycam-rust/README.md:189-197`).

**A3. §4a, FreeMoCap calibration recordings.** Checked against the local FreeMoCap checkout (development @ 5632778a, 2026-10-08).
- **Start and stop: still work (code).**
  - FreeMoCap calls `get_or_create_camera_group_manager(...).start_recording_all_groups(recording_info=...)` and `stop_recording_all_groups()`, then reads `[0][0]` (`freemocap/app/freemocap_application.py:63,74-87`).
  - On sfn26 that accessor returns a `CameraBackendManager` (`upstream/sfn26:skellycam/core/camera_group/camera_group_manager.py:274-285`). It accepts the same keyword arguments and still returns a list of `(RecordingInfo, stats)` (`camera_backend_manager.py:75-92`).
  - FreeMoCap stops through internal calls, not HTTP, so the GET→POST change does not affect it.
- **python output: same as §4a.** Same files and encoder, header bias and overlay (L2, C2, F1 unchanged), with the microphone forced to −1 (`freemocap/api/http/calibration/calibration_router.py:52-60`).
- **Calibration solve: broken on sfn26 with this FreeMoCap (inferred).** The solve that `/freemocap/calibration/recording/stop` starts runs FreeMoCap nodes, which call `WorkerRegistry.create_worker` without the arguments it now requires (S3 evidence: `upstream/sfn26:skellycam/core/ipc/process_management/worker_registry.py:133-143`). The recording would be written, but the solve would fail with a TypeError.
- **rust: recording works; realtime pipeline does not.**
  - The recording is clean (no overlay) and has an extra `*.native_timestamps.csv` in `camera_timestamps/`.
  - FreeMoCap's own fps helper globs `synchronized_videos/timestamps/**/*timestamps.csv` and takes the first match after sorting (`freemocap/core/tasks/mocap/mocap_helpers/recording_framerate.py:29-32,44-49`). It looks for the stats JSON first, though, and that is no longer empty (L3).
  - The `charuco_observations_realtime.pkl` path cannot run on Rust. `RustCameraGroup` has no `shm` or `ipc` (`upstream/sfn26:skellycam/core/camera_group/rust_camera_group.py:34-268`), which FreeMoCap's realtime nodes need. FreeMoCap's `create_or_update_camera_group(camera_configs=...)` also sends no backend, so it defaults to "python", and with a Rust group open it gets `CameraBackendInUseError` (`camera_backend_manager.py:35-37`).
- **Side effect of the L3 fix (inferred).** FreeMoCap reads `stats["framerate_stats"]["median"]` (`recording_framerate.py:63-74`). The fixed serializer writes exactly that key, because it strips `_value` from the field names (`upstream/sfn26:skellycam/core/timestamps/recording_timestamp_stats.py:135-142`). So FreeMoCap will now take its filter rate from the stats JSON rather than its CSV fallback.

**A4. §5, pausing mid-recording through the API is not refused**
- **python: UNCHANGED.**
  - `PUT /group/all/pause` has no recording check (`upstream/sfn26:skellycam/api/http/cameras/camera_router.py:214-221`).
  - Neither does `CameraGroup.set_paused` (`upstream/sfn26:skellycam/core/camera_group/camera_group.py:228-232`).
  - The loop still skips frames while paused (`opencv_camera_loop.py:63-65`), so the CFR file closes up the gap.
- **rust: UNCHANGED** in effect (F3 rust): `pause_group` has no guard (`rust_camera_group.py:169-173`).

**A5. §5, dormant remux details** (it writes MP4 under an `.avi` name, `rate=30`)
- **UNCHANGED.** `skellycam/core/recorders/video_audio_remuxer.py` has no diff, and the call is still commented out (`upstream/sfn26:skellycam/core/recorders/recording_finalizer.py:63`). This applies to both paths.

**A6. §2, multiframe CSV has 103 columns; per-camera dtype unchanged**
- **UNCHANGED.** `numpy_record_dtypes.py`, `create_multi_frame_csvs.py` and `create_camera_csvs.py` have no diff.
- The only change under `numpy_timestamps/` is in `process_and_save_recording_timestamps.py` (the ID check and reorder).

**A7. §6 row: `validate_recording` fails → "Kept / Written; HTTP 500"**
- **python and rust: CHANGED for a missing video.**
  - `save_to_file` now runs `VideoAssociations.resolve_paths`, which calls `resolve(strict=True)` and raises on a missing file (`upstream/sfn26:skellycam/core/recorders/videos/recording_info.py:86-90`; `video_associations.py:36-48`; commit c3e752e6).
  - That is step 1 of finalize (`recording_finalizer.py:55`), so a missing video now leaves **no** info JSON, CSVs or stats.
- **python and rust: UNCHANGED for other failures** (frame-count or shape mismatch): those are still caught by `validate_recording` after the files are written.

**A8. §6 row: rotation changed to 90/270 mid-recording**
- **python: CHANGED in containment.**
  - In-place updates are still allowed while recording; only membership, resolution, channel or pixel-format changes are refused (`upstream/sfn26:skellycam/core/camera_group/camera_group_manager.py:101-114`).
  - `_validate_image_shape` still raises (`upstream/sfn26:skellycam/core/recorders/videos/video_recorder.py:145-151`).
  - The handler now calls `report_camera_failure` and sets `should_continue=False` (`opencv_camera_loop.py:126-131`, d65707a1), which stops the group, not the whole app. The recording still ends without finalize (R1).
- **rust: NEW BEHAVIOUR (inferred, low confidence).**
  - Nothing refuses `apply_configs` while recording (`rust_camera_group.py:90-110`).
  - The dispatcher rotates each frame with the current rotation (`dispatcher.rs:201-214`), but the recorder size is fixed from the first multiframe and passed to ffmpeg as `-s` (`dispatcher.rs:392-404`; `recorder.rs:145`).
  - ffmpeg then rebuilds its filter graph and scales the rotated frames to the original size, so the video comes out stretched.
  - At stop, `validate_recording` compares the first frame's shape with the configs as they are at stop time, so it would probably fail.

**A9. §6 row: 30 failed grabs → repeated frame number → `_validate_frame_number` raises**
- **python: CHANGED.** After `MAX_FAIL_COUNT` failures the loop now raises `RuntimeError("…failed to capture a frame after N attempts")` (`upstream/sfn26:skellycam/core/camera/opencv/opencv_camera_loop.py:86-92`; 87eddca2). Before, it went on with a stale frame (`23ccbf20:…/opencv_camera_loop.py:72-86`). The group stops, `finish_recording` runs in `finally` (`:132-140`), and nothing is finalized (R1). It also fires when not recording.
- **rust: CHANGED, and worse for the video files (inferred).** Any capture error on one camera destroys every camera's video for the take:
  1. The camera thread exits on any of: a frame wait longer than 5 s (`upstream/sfn26:skellycam-rust/src/camera/camera_thread.rs:355-364`), a `getFrameSize` or `captureFrameRaw` failure (`:377-418`), or a frame-number mismatch, which makes the gatherer panic (`upstream/sfn26:skellycam-rust/src/camera_group/gatherer.rs:324-330`).
  2. The gatherer sees the disconnect and breaks the barrier (`gatherer.rs:301-322`).
  3. The dispatcher sees `Disconnected` and exits without Stop (`dispatcher.rs:327-330`).
  4. The recording thread exits on the dropped channel (`recording_thread.rs:335-340`).
  5. `VideoRecorder::drop` kills ffmpeg (`recorder.rs:265-276`), which leaves MP4s with no moov atom. Only the native CSVs survive.
  6. The Python stop then fails with "Dispatcher disconnected" (`upstream/sfn26:skellycam-rust/src/camera_group/camera_group.rs:600-611`). `_recording_requested` stays True.

**A10. §8: `video_frame_metadata` is never cleared**
- **python: UNCHANGED** (`upstream/sfn26:skellycam/core/recorders/videos/video_recorder.py:33,115-118`). Still harmless, because each recording gets a new recorder.
- **rust: NOT_APPLICABLE.** The Rust recorder `mem::take`s its timestamps (`recorder.rs:253`).

**A11. §8: `finish_recording` returns `None` and one caller ignores it**
- **python: UNCHANGED** (`upstream/sfn26:skellycam/core/camera/opencv/opencv_helpers/handle_recording_updates.py:35,59-68`). Still harmless: line 40 now sets `video_recorder = None` explicitly.
- **rust: NOT_APPLICABLE.**

**A12. §4, GOP consequences for random access** (how skellycam's own playback seeks)
- **python: UNCHANGED.** The encoder is unchanged. Playback now serves the file as-is to the browser (`upstream/sfn26:skellycam/api/http/playback/playback_router.py:237-277`), and `sequential_video_reader.py` is used by no production code (only tests).
- **rust: CHANGED (inferred).** With keyint 250 and scenecut off, random access means decoding up to 249 frames.

## (b) Disagreements and inconsistencies, resolved

**B1. R7 [sfn26/rust]: votes CONFIRMED (FIXED) vs REFUTED→PARTLY_FIXED. Resolution: FIXED for skellycam as shipped; a separate hazard remains only in the standalone Rust binary.**
- Through Python, a second start is refused twice:
  - `CameraBackendManager.start_recording_all_groups` returns 409 (`upstream/sfn26:skellycam/core/camera_group/camera_backend_manager.py:75-84`).
  - `RustCameraGroup.start_recording` raises if already recording (`rust_camera_group.py:115-116`).
- Stop is a synchronous request/response (`camera_group.rs:600-611`), so there is no queue of stale finished-messages. The R7 symptom (finalizing the previous recording) cannot happen.
- The dispatcher itself has no guard. A second `StartRecording` overwrites `pending_recording` (`dispatcher.rs:96-102`), and the next multiframe replaces `recording_handle` (`:177-182`). The old thread then sees the disconnect and ffmpeg is killed: the old take is destroyed, not mis-finalized.
- That path is reachable only from the standalone `skellycam-rust` binary's start route (`upstream/sfn26:skellycam-rust/Cargo.toml` `[[bin]]`; `skellycam-rust/src/api/camera_routes.rs:305`). The PyInstaller build bundles only `_skellycam_rust`.
- So the dispatcher hazard is a different failure in an unshipped binary. It does not mean R7 is only partly fixed.

**B2. C3/F-new [rust] "GOP = keyint 250 plus scenecut" vs Rust overview "scenecut off". Resolution: the overview is right.**
- `recorder.rs:43-44` (preset `ultrafast`) and `:141-153` set no `-g` and no x264 parameters.
- x264's ultrafast preset sets scenecut 0, bframes 0, no CABAC, no 8x8dct, weightp 0 and no deblocking (x264 source `common/base.c`, preset apply, which is outside the repo).
- So the GOP is a fixed I-frame every 250 frames with no scene-cut I-frames, signalled Constrained Baseline (inferred, not probed).

**B3. S1 [python] "validate check-1 weakness carries over" vs files-layout new observation "missing video aborts finalize at save_to_file". Resolution: both readings are accurate, and the second one decides the outcome.**
- The check-1 code is byte-for-byte the same (`upstream/sfn26:skellycam/core/recorders/recording_finalizer.py:138-145`).
- It can no longer see a missing file, though: `save_to_file`'s strict `resolve_paths` raises first (`recording_info.py:86-90`; `video_associations.py:41`). See A7.
- Verdict for the §8 item: PARTLY_FIXED. A missing video is now a loud error, but it costs every finalize output.

**B4. Rust ffmpeg stderr "possible stall, not verified" (codec group). Resolution: likely real, and worse than a stall: a deadlock at stop (inferred, now supported by the library source).**
- ffmpeg-sidecar 2.5.1 (`upstream/sfn26:skellycam-rust/Cargo.lock:762-763`):
  - `new_with_path` pipes stdin, stdout and stderr, and adds `-loglevel level+info`.
  - `FfmpegChild::wait()` copies stderr to a sink only when it is called, with the comment "we need to run it to completion to avoid a deadlock".
  - Source: docs.rs `ffmpeg-sidecar/2.5.1/src/command.rs` and `child.rs`, fetched read-only.
- skellycam-rust reads stderr nowhere except `finish()` → `wait()` (`recorder.rs:233-240`; `git grep stderr` finds only that comment).
- At info level, ffmpeg prints a progress line about every 0.5 s. Once the stderr pipe fills, ffmpeg blocks; that is roughly 4 KB on Windows anonymous pipes (about 10–30 s) and 64 KB on Linux and macOS (a few minutes). Then this chain follows:
  1. ffmpeg stops reading stdin.
  2. `feed_frame`'s `write_all` blocks (`recorder.rs:206-209`).
  3. The recording thread is stuck inside `FeedFrames`, so the queued `Stop` is never processed (`recording_thread.rs:280-324`).
  4. `HandleRecording::stop` waits on `rx.recv()` with no timeout (`:108-127`).
  5. Python's `to_thread(stop_group_recording)` never returns.
  6. `close()` hangs too, because it calls `stop_recording` first (`rust_camera_group.py:81-85`).
  7. Meanwhile the unbounded channel takes on every JPEG.
- The only Rust recording test records 150 frames, about 5 s (`upstream/sfn26:skellycam-rust/src/tests/recording_tests.rs:20-22`), which is too short to show this.
- Severity is high if true. It needs one Rust recording longer than 60 s on Windows to confirm.

**B5. L7 [rust] "info JSON framerate is the requested value, e.g. −1" vs F1 [rust] "the header uses the negotiated fps from `shared_config`". Not a conflict.**
- `shared_config` is Rust-internal (`camera_thread.rs:167,219`; `dispatcher.rs:380-390`).
- The Python `self._configs` is the requested set (`rust_camera_group.py:108`).
- Both claims hold: the negotiated rate is recorded nowhere except the ffmpeg `-r`.

**B6. R8 [python] FIXED vs lifecycle new observation "a hung camera blocks close forever". Resolution: FIXED for the reported trigger (a dead process), with a new caveat.**
- `wait_for_recording_save` has no timeout for a process that is alive but hung (`upstream/sfn26:skellycam/core/ipc/process_management/managed_worker.py:66-74`).
- Keep FIXED, and list the hung-process case as a new item.

No other votes disagreed. The C4 rust and R1 rust predictions about a hard kill agree; they are inferred and assume ffmpeg ignores SIGPIPE on POSIX.

## (c) Recording-relevant sfn26 changes nobody reported

**C1. The Rust stderr deadlock** in B4 was listed only as "possible". It should be promoted to a headline Rust risk.

**C2. On Rust, a capture error on any single camera destroys every camera's video for the take** (A9). This is a new failure mode with no Python equivalent; Python keeps playable videos.

**C3. Recorder creation moved after config application in each loop iteration.**
- **What changed:** in `camera_loop_update_checks`, `check_for_new_recording_info` now runs after `check_for_new_config` (`upstream/sfn26:skellycam/core/camera/opencv/opencv_helpers/camera_loop_update_checks.py:30-48`; d65707a1).
- **Effect (inferred):** if a config update and a recording start land in the same iteration, the writer now opens with the new config.
- Recorder creation is also wrapped so a failure closes the writer and clears `recording_in_progress` (`handle_recording_updates.py:39-56`).

**C4. Regression: fallback-codec videos are no longer playable in skellycam's playback view (inferred).**
- `transcode_to_h264.py` was deleted (59a3e7b1), and `stream_video` now returns the raw file for `.avi` (`video/x-msvideo`) too (`upstream/sfn26:skellycam/api/http/playback/playback_router.py:260-277`).
- `browser_stream.py` would solve this but has no production caller.
- Recordings made with the `mp4v`, XVID or MJPG fallbacks (§4's last-resort row) will not play in Chromium.
- L5 marked the sidecar FIXED without noting that the problem it handled is now unhandled.

**C5. An exposure sweep can land inside a recording (inferred).**
- `CameraBackendManager._create_or_update` runs `recommend_exposure` whenever a RECOMMEND config is applied (`upstream/sfn26:skellycam/core/camera_group/camera_backend_manager.py:42-56`).
- It does not check `_recording_requested`, and in-place updates are allowed while recording on both backends (`camera_group_manager.py:101-114`; `rust_camera_group.py:90-110`).
- The sweep steps through exposures −12…−5 for at least 10 frames each (`upstream/sfn26:skellycam/core/camera_group/tasks/recommend_exposure.py:19-75`). If it runs during a recording, those roughly 80+ frames of changing brightness go into the take.
- The UI blocks apply while recording; non-UI clients are not blocked.

**C6. Rust frame-rate stats are computed but thrown away.**
- The dispatcher measures `camera_fps` from `frame_available_ns` (`dispatcher.rs:242-262`) and the finalizer gets a `RecordingStatsSummary`.
- `native_recording_summary.json` has no stats field, and Python never reads `stats_json` (`rust_camera_group.py:143-155`). The measured rate never reaches disk except through the Python CSV pipeline.
- This partly overlaps L3 rust, but nobody noted that the fps measurement exists.

**C7. Dead code next to the recorder.** `video_copy_plan.py`, `video_derivation.py`, `sequential_video_reader.py`, `browser_stream.py` and `PyavVideoWriter.set_container_metadata` have no production caller (`git grep` finds only tests). They change no behaviour, but readers should not take them as active recording features.

**C8. `ms_to_ns` now returns rounded int64 and rejects NaN and overflow** (`upstream/sfn26:skellycam/utilities/time_unit_conversion.py:11-38`; f1aefa95). No production caller was found, so recordings are unaffected.

**C9. The sfn26 Rust path has no recording guard on `apply()` and routes frames to files by position** (R6 rust). This was reported, but it adds to C2 and A8: a non-UI client changing cameras, rotation or exposure mid-recording on Rust has three separate ways to corrupt the take.

**main and development-streaming deltas:** nothing further. Their 5 extra commits touch none of the items above.