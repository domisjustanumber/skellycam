# Frame timestamp accuracy: DirectShow today vs revised DirectShow vs Media Foundation

2026-11-09, Gerald (Windows 11). Code read: skellycam `development-streaming` @ `169caf63` (the version freemocap pins), freemocap `development-streaming` @ `c27fc299` (including `freemocap-ui/`), skellytracker `development-streaming` @ `03b9c1dc`, skellyforge `development-streaming` @ `f5404db`, OpenCV 4.12.0 `modules/videoio` (the version skellycam pins). Labels: **measured** = a result file supports it; **code** = read from source; **inferred** = reasoned, not tested.

**Verification.** Three independent verifiers checked the draft: one for code citations, one for numbers against the result files, and one skeptic. Each finding was re-checked against the source or data before it was applied. The corrections that matter most:
- The improvement factors measure **per-frame precision**. Cross-camera accuracy is limited by an unmeasured bias that may vary between sessions, so its gain is unknown.
- The faster-camera figure for today is 13.0–16.2 ms (A2/A3), and the group gain is ~23–29×, not 25–40×. The A4 figures are indicative only.
- The tier-0 flash bound is ≤ 0.56 ms, and it holds only for robust arrival or two-stage fits. A robust fit on sample time gives 2.0 ms on the C930e.
- The 6 s C930e camera-clock figure (0.10 ms) is a self-consistency check, not an accuracy figure.
- Arrival-only slotting on the Kiyo failed (3 false drops, 29.7 ms from the camera clock).
- The fit worked for at most two cameras on separate links. It failed in the one three-camera run on a shared link.
- Filtered 3D trajectories and MediaPipe VIDEO-mode landmarks **do** depend on group time. Only raw triangulation does not.
- The "today" runs re-set exposure and delayed the gate, so they describe skellycam with the C930e exposure loss fixed.
- Under the gate, setting the writer fps from a camera's own period would make the faster camera's video play fast.
- The slot-aligned design now names which column holds which time.
- Freemocap also reads `connection_frame_number` and the multiframe CSV, and skellycam's live displays use the grab midpoint.
- `CAP_PROP_FPS` is set at open when a manual framerate is configured.

Path conventions:
- skellycam code: `skellycam/...`, relative to the skellycam repo root, at `169caf63`.
- freemocap code: `freemocap/...` or `freemocap-ui/...`, relative to the freemocap repo root.
- Research: `research/usb_cameras/...`, relative to the skellycam repo.
- `LIVE/` = `research/usb_cameras/results/windows/Gerald/ts_accuracy_20261109/live/`.
- `REANALYSIS/` = `research/usb_cameras/results/windows/Gerald/ts_accuracy_20261109/existing_reanalysis/`.
- `OCV/` = `research/usb_cameras/results/windows/Gerald/ts_accuracy_20261109/opencv_internals/` (scripts in `research/usb_cameras/timing/ts_accuracy/opencv/`).
- `NOTES/` = `research/usb_cameras/results/windows/Gerald/ts_accuracy_20261109/reader_notes/` (the code-reading notes behind §2, §3 and §5.3).

"Option 1" = revised OpenCV DirectShow (post-retrieve stamps, stale-frame flag, frame-slot fit, drop detection). "Option 2" = custom Media Foundation capture with raw MJPEG and the same fit, tier 0 (no registry value). "Tier 1" = UVC PTS/SCR via the `MetadataBufferSizeInKB0` registry value. Tier 1 appears here **only as a measuring reference** (the camera's own clock), never as part of a tier-0 method.

Error terms used throughout:
- **Per-frame random error**: frame-to-frame scatter of a stamp around the camera's true frame times. A fit removes most of it.
- **Constant per-camera bias**: fixed delay from light on the sensor to the stamp. No tier-0 method removes it, and it differs between camera models.
- **Gross pairing error**: frame *k* of camera A and frame *k* of camera B were not captured at the same time, but the data says they were. This comes from the lockstep gate and index pairing, not from the stamps.

## 1. Answer in brief

**(a) What skellycam writes today.**
- One stamp per frame: the midpoint of `perf_counter_ns()` taken just before and just after `cap.grab()` (`skellycam/core/timestamps/numpy_timestamps/create_camera_csvs.py:50-51`). **code**
- On OpenCV DirectShow `grab()` does nothing. It returns in 2–6 µs (**measured**, `OCV/dshow_c930e_aep0/summary.json`; **code**, `cap_dshow.cpp:3633-3636`). So the stamp is the moment the loop got past the lockstep gate, not when the frame arrived.
- The multiframe CSV time is the **mean across cameras** of those stamps (`create_multi_frame_csvs.py:44-45`). **code**
- No camera, driver or OS frame time is captured anywhere. **code**
- Known bugs:
  - The local ISO 8601 column applies the UTC offset twice (**measured**).
  - The video writer's fps is biased high (**code**; size inferred).
  - The C930e loses its manual exposure under skellycam's setup order (**measured**).

**(b) How freemocap uses it.**
- freemocap reads `timestamp.from_recording_start.sec`, `recording_frame_number`/`multiframe_number` and `connection_frame_number`. It uses `connection_frame_number` to map the realtime ChArUco cache onto recorded frames (`freemocap/core/pipeline/posthoc/video_node.py:368-381, 491-509`). Through skellycam's `recording_statistics.py:13-22`, it also takes the recording fps and duration shown in the UI from the multiframe CSV. **code**
- The **group** time (the multiframe mean) drives gap filling, Butterworth filtering, alignment, the MediaPipe timestamps and the time label of every 3D sample in Parquet, the exports and Blender. **code**
- Per-camera times label the 2D rows and the playback timelines. **code**
- Triangulation, calibration and the whole realtime pipeline pair cameras **by frame index only**. No capture time reaches any realtime computation. The realtime 1€ filters (2D in the camera node, 3D in the aggregator) use `perf_counter()` at processing time. **code**

**(c) Would MF + raw JPEG + tier 0 + the proposed stamping be more accurate per camera frame? For per-frame precision (random error), yes: about 9× for a camera alone and about 23–29× for a faster camera grouped with a slower one. Option 1 probably gets 3–9× for a camera alone (against option 2's 9×), but it has not been scored. Cross-camera accuracy is a separate question, and its gain is unknown (see below).**

Today's stored stamp, scored against each camera's own frame lattice (constant offset removed), from `LIVE/analysis_tables.md`, **measured**:
- One camera alone: 4.6–5.7 ms std.
- In a group:
  - Faster cameras: 13.0–16.2 ms std, max 35.8–41.1 ms (A2, A3). A3's slots were validated on only 57 % of 72 fresh frames.
  - The slowest camera: 4.7–7.6 ms. The A2 Kiyo stores 7.59 ms because it sometimes waits at the gate (p95 wait 12.7 ms).
  - A4 (three cameras, two of them behind the same hub): 12.2–20.6 ms, indicative only.
- Frame *k* across cameras: the stamps say 0.2 ms apart. The lattice times are −52 to +26 ms apart (C930e − Kiyo) and +18 to +81 ms apart (generic − C930e). The spread is reliable. The medians include each model's unmeasured latency.
- **Caveat:** these "today" figures come from an emulation that set exposure again 1.5 s after configuration and opened the gate only after 2.5 s of streaming (§5.1). They therefore describe skellycam **with the C930e exposure loss corrected**. Shipped skellycam on the C930e, at its default exposure, is unmeasured.

Option 2 with the fit:
- **≤ 0.56 ms** (0.52–0.56 ms) std against flash ground truth on the C922 and C930e. This holds for a robust arrival-envelope fit or a two-stage fit (one 30 s run, n = 85/95 ground-truth frames, offline whole-run fit). It equals the method floor, so it is an upper bound (**measured**, `REANALYSIS/flash_gt_perframe.json`). On the C930e, naive least squares gives 2.7 ms and the robust whole-run fit on sample time gives 2.0 ms, because of the start-up latency step.
- Typically 0.02–0.15 ms against the camera's own clock (**measured**, `REANALYSIS/camera_clock_scores.json`).
- Kiyo: 1.0–1.9 ms against its own clock, but that clock itself deviates ~1 ms from a lattice. Whether this is noise in the reference or real exposure jitter is open (§7.3). These figures use slots taken from MF sample time. Arrival-only slotting on the Kiyo produced 3 false drops and a lattice 29.7 ms std from the camera clock (`mf_kiyo`, §5.1). **measured**
- **Scope:** the fit has been shown for at most two cameras on separate USB links. In the one three-camera run on a shared link (A4, DirectShow under the gate), it failed: 4.2–7.3 ms from its own least-squares line, split-half end errors of 57–65 ms. No free-running (B) or MF run with three cameras exists. **measured**
- The fit assumes one fixed period. Auto exposure, stalls and period-mode switches are untested (§7.2 step 2).

What does **not** improve:
- The constant per-camera latency from light to stamp. It is unmeasured. The flash data suggest it differs between models by several ms up to ~30 ms (C930e − C922: 4.4–30.7 ms over 6 runs, sd 10 ms), so it is **not stable across runs** (**measured**, `REANALYSIS/README.md` §5).
- So **cross-camera accuracy** at tier 0 is limited by a bias that may vary per session. Until the A5 rig measures it, the gain in inter-camera accuracy is unknown, and for a lone or slowest camera it could be close to 1×. For example, with a 10 ms bias the total is sqrt(10² + 4.6²) = 11.0 ms today against sqrt(10² + 0.56²) = 10.0 ms fitted (**inferred**).
- Rolling shutter adds ~30 ms from the top row to the bottom row (C922 upper bound).
- Neither the latency bias nor rolling shutter is a frame-stamp problem that tier 0 can fix.

**(d) Downstream effects.**
- **Better values in the existing column flow into freemocap with no freemocap change**, as long as the contract holds: one row per video frame, indices 0..N−1, strictly increasing times, same column names (**code**). That improves filtering, gap filling, alignment and the time labels.
- **Raw triangulated points do not change**, because triangulation pairs by index (**code**).
- **The filtered and gap-filled 3D trajectories do change** (**code**; size unmeasured):
  - The Butterworth filter resamples each trajectory onto a uniform grid built from group time, then back (`freemocap/core/reconstruction/posthoc_filtering.py:91-118`).
  - Gap filling uses the same times (`posthoc_filtering.py:44-47`).
  - MediaPipe VIDEO-mode landmarks can change, because their `timestamp_ms` changes (`freemocap/core/pipeline/dataflow/tracker_adapter.py:37-49`; skellytracker `mediapipe_pose_detector.py:105-111, 159`).
- A gain in raw 3D pairing needs one of two things (**code** + **inferred**):
  - skellycam builds multiframes by time, or
  - freemocap interpolates each camera's 2D track to a common time before triangulating.
- skellycam's own live displays use the grab midpoint and need switching to the new stamp: the frontend frame timestamp, the "Server" fps readout and the performance panel (§6.1). **code**
- Removing the lockstep gate, which option 1 needs in order to work, touches every equal-count check: 12+ sites in skellycam, ~11 in freemocap (§6).

**(e) Different frame rates and dropped frames.**
- **At the capture level: yes for option 2; yes for option 1 only without the gate.**
- **Downstream today: no.** Every stage from the skellycam finaliser to freemocap triangulation, calibration, playback and the realtime nodes requires equal per-camera frame counts with the same indices. Unequal counts fail loudly (**code**).
- **Today the gate hides both.** It silently drops frames from the faster camera: 320 of the C930e's frames (14 %) when paired with the 25.76 fps generic camera (**measured**, `LIVE/analysis_tables.md` run A3). None are flagged.
- **Cheapest route:** skellycam assembles group slots by time and writes equal-length, slot-aligned outputs (§6.4). **inferred**
  - The existing time column holds the slot (group-clock) time, which stays strictly increasing.
  - A new column holds the camera's own fitted time.
  - A per-camera `frame_status` column marks each frame fresh, repeated or missing.
  - Changes needed: skellycam's `recording_timing_reader`, freemocap's `RecordingGroupTiming.resolve`, and carrying `frame_status` through `FRAME_METADATA_DTYPE` to the realtime camera node, inference node and aggregator.
- **Outside what has been tested:** auto exposure, camera stalls and period changes. Every method here assumes one fixed period per segment (§7.2 step 2).

**(f) How much improvement each option gives.**

| | Option 1: revised OpenCV DShow | Option 2: custom MF raw MJPEG, tier 0 |
| --- | --- | --- |
| Raw stamp, per-frame std (no fit) | 4.6–4.8 ms for every camera once the gate is removed, in the 1–2-camera combinations tested (**measured**, runs B1–B3). With the gate kept, faster cameras stay at 7–16 ms (post-retrieve, A2–A4). | 4.54–4.73 ms (**measured**, MF runs), except Kiyo arrival in `mf_kiyo` at 5.30 ms std, 85 ms max (arrival bursts). This is the same 16 ms grid floor, so it is **no more precise** per fresh frame than option 1. |
| Fitted stamp, per-frame std | ~0.5–2 ms (**inferred**; the low end is optimistic). The envelope and least-squares lines agree to 0.01–0.30 ms (B runs; internal consistency only). Split-half slopes on free DShow runs differ by up to 49 ppm (2.5 ms extrapolated), against ≤ 16 ppm on MF (**measured**). Never scored against ground truth on DShow. Adds an unknown constant per-camera decode delay. | **≤ 0.56 ms** (0.52–0.56 ms) with a robust arrival or two-stage whole-run fit (**measured**, flash, C922 and C930e, one 30 s run, offline). The robust whole-run fit on sample time gives 2.0 ms on the C930e. Causal (trailing-window) fits, flash re-analysis [M-re]: C922 0.56–0.75 ms; C930e 1.5–3.9 ms depending on variant (2.4–3.4 ms for the q = 0.02 fixed-period variants). Kiyo 1.0–1.9 ms against its own clock, with sample-time slotting (cause open). |
| Improvement over today (per-camera random error) | Camera alone: raw ~1×, fitted probably 3–9× (inferred, unscored). Faster camera in a group: raw 2.8–3.4× (measured, A2/A3 vs B2/B3), fitted ~7–29× (inferred). | Camera alone: ~9× (measured vs flash). Faster camera in a group: ~23–29× (inferred from measured components: A2/A3 against the flash floor). Both are precision only; the cross-camera accuracy gain is unknown (§1(c)). |
| Gain of option 2 over option 1 | — | Unknown. The split-half indicator puts the DShow fit 0.5–2 ms behind MF (a measured indicator, not ground truth). The clearer gains are robustness: the stamp stays correct when the app reads late, drops are seen, there is no decode delay ahead of the stamp, and the tier-1 route stays open. Capture CPU also drops from ~25 % to 1–2 % of a core per camera, plus ~5–10 % per camera if the JPEG is decoded at source (§5.3). The CPU figures are for the capture process only; Frame Server CPU is not included. (**measured** for CPU and late-read behaviour, in a dark scene; **inferred** for the combination.) |
| Constant per-camera bias | Unchanged and unmeasured, plus DShow's in-graph decode (inferred: a few ms, varies by camera) | Unchanged and unmeasured. MF sample time on the generic camera sits one frame (32 ms) earlier than on the others (**measured**). Use arrival-based fits. Calibrate per model if the A5 rig shows the bias is stable across sessions and stream restarts; otherwise calibrate per session. |
| 3D accuracy | Raw triangulation unchanged unless pairing changes (§6). Filtered and gap-filled trajectories and MediaPipe VIDEO-mode landmarks change with group time (size unmeasured). | Same |

## 2. What skellycam development-streaming writes

### 2.1 How a frame gets its stamp (Windows)

**Setup** (**code**):
- Backend: `cv2.CAP_DSHOW` on Windows (`skellycam/core/camera/determine_backend.py:29-42`).
- Setup order is FOURCC → width/height → FPS (only if `config.framerate > 0`) → `BUFFERSIZE=1` → `read()` (`skellycam/core/camera/opencv/opencv_helpers/create_cv2_video_capture.py:57-75`), then exposure → width/height → FOURCC again (`opencv_apply_config.py:71-85`).
- By default the FPS is not set, because the default is −1 (`camera_config.py:26`). The UI offers a manual framerate (`freemocap-ui/src/components/control-panels/camera-config-panel/CameraConfigFramerate.tsx:16-23, 95`). `apply_camera_configuration` never sets the FPS (`opencv_apply_config.py:62`). After open, `extract_config` stores `cap.get(CAP_PROP_FPS)` as `config.framerate` (`opencv_extract_config.py:24, 45`). On DShow that value is 0 (**measured**), so later re-opens (`opencv_camera_loop.py:177-178`) never set the FPS. **code**
- **measured** results of that order:
  - `set(CAP_PROP_BUFFERSIZE)` returns False and `get(CAP_PROP_FPS)` returns 0 (`LIVE/*.session.json`).
  - The second FOURCC set rebuilds the DirectShow graph, and the C930e falls back to its default exposure: readback −4, image mean 84–103 instead of 14–19, in all 7 C930e DShow runs (`LIVE/README.md`, "Other findings").

**Per-frame loop** (`skellycam/core/camera/opencv/opencv_camera_loop.py`, `opencv_helpers/opencv_get_frame.py`; **code**):
1. Wait at the lockstep gate. It polls `sleep(1e-5)` until this camera's `frame_count` is ≤ every peer's (`skellycam/core/camera_group/camera_orchestrator.py:118-131`; loop 67–69).
2. Take `pre_frame_grab_ns`, call `grab()`, take `post_frame_grab_ns` (get_frame 53–55). `grab()` returns at once on DShow.
3. Bracket `retrieve()` with pre/post stamps (71–73). It waits up to 1 s for **the first frame that arrived after the previous `retrieve()`**. OpenCV discards newer frames while one is unread, and counts nothing (`cap_dshow.cpp:703-723, 1543-1594`). DShow has already decoded the MJPEG to RGB24 on its own thread before the frame is handed over.
4. Burn a text overlay into the image (80–84). Copy into shared memory, write the video, then publish `frame_count` (loop 102–123). Publishing `frame_count` is what releases the peers.

**What the stored stamp ends up meaning:**
- **One camera alone:** about one frame period (~31 ms median) **before** arrival, but with steady scatter (**measured**, `LIVE/README.md`). The constant cancels in relative timing.
- **A camera held back by a slower peer:** the frame it gets was already waiting, so the stamp is **late by the frame's unknown age**. In A3, 96 % of the C930e's frames were already waiting (**measured**).

### 2.2 Files and fields

| File | Time content | Source |
| --- | --- | --- |
| `synchronized_videos/timestamps/camera_timestamps/<rec>.camera<id>.timestamps.csv` | `timestamp.perf_counter_ns.ns` = grab midpoint.<br>`timestamp.from_recording_start.sec` = midpoint − recording start.<br>`timestamp.utc.seconds`.<br>`timestamp.local.iso8601` (buggy).<br>`from_previous.*` diffs.<br>Every lifecycle stamp minus start (`frame.post_frame_retrieve.ns` is kept).<br>`recording_frame_number` = 0..N−1, `connection_frame_number` = loop count. | `create_camera_csvs.py:49-99` |
| `synchronized_videos/timestamps/<rec>_timestamps.csv` | Per multiframe: mean across cameras of the times, `inter_camera.frame_grab_range.ms` (max − min of midpoints), and cross-camera stats of every stage | `create_multi_frame_csvs.py:44-111` |
| `<rec>_stats.json/.txt` | Summary statistics of the multiframe CSV | `recording_timestamp_stats.py:64-121` |
| `<rec>_info.json` | Paths to the CSVs (`camera_timing`, `multiframe_timing`), configs, and `recording_start_timestamp`, taken at the HTTP start request rather than the first frame | `recording_info.py:27, 80-104`; `camera_router.py:147-148` |
| Videos | CFR. The cv2 writer is given the loop-measured median rate. If fewer than 30 loop intervals exist when recording starts, it gets `config.framerate` instead, which on DShow is `get(CAP_PROP_FPS)` = 0 (**code**; value 0 **measured**). PyAV uses `round(fps)` with pts = frame count. The VFR remux is commented out. | `video_recorder.py:80, 129-134`; `opencv_camera_loop.py:41, 83-84`; `opencv_extract_config.py:24`; `pyav_video_writer.py:14, 33`; `recording_finalizer.py:63` |

- **Recording start** = the minimum `pre_frame_grab_ns` over the cameras' first recorded frames (`process_and_save_recording_timestamps.py:81-84`).
- **Time base:** one `(time_ns, perf_counter_ns)` pair per camera group, used to map to UTC (`timebase_mapping.py:22-24`). **code**

### 2.3 Bugs and defects in the timing path

| Defect | Evidence | Effect |
| --- | --- | --- |
| Local ISO 8601 applies the UTC offset twice | `timebase_mapping.py:31, 42`. **measured** at UTC−5: a true 06:06 is written as 01:06 in the per-camera CSV, and correctly as 06:06 in the multiframe CSV (`NOTES/iso8601_double_offset.out.txt`) | Wrong local times; the test only checks for a `"T"` (`tests/test_timestamps_and_framerate.py:118-125`) |
| Writer fps measured over part of the loop only | Each duration runs from the end of the previous iteration (loop 124) to after `get_frame` (80–82). It leaves out the shm copy and video write, but includes the gate wait (67–69), so under the gate it roughly tracks the delivered rate. **code** | Rate biased high, CFR video duration short. A freemocap code comment reports container rates of 34.28–34.74 fps for one take with equal counts (`freemocap/core/tasks/mocap/mocap_helpers/recording_framerate.py:9-13`). That is consistent in direction; the size is unmeasured. |
| Frame-rate reset times post-processing, not the frame interval | `opencv_camera_loop.py:160-180` (hard-coded 30 fps). **code** | Fires only on a slow encoder. It never fired in the live runs (`would_framerate_reset` = 0, **measured**) |
| Exposure lost on the C930e | FOURCC set after exposure (`opencv_apply_config.py:74-85`). **measured** | Wrong exposure on the C930e; and under auto exposure the frame rate is not constant |
| Overlay burned into the image | `opencv_get_frame.py:80-84`. **code** | Text in recorded videos and in the images freemocap's realtime trackers see |
| Dead or wrong helpers | `create_camera_frame_csv_row_recarray` uses `(pre+pre)//2` and would raise (`create_camera_csvs.py:110-178`); `FullTimestamp.from_timebase_mapping` adds raw perf seconds to UTC (`full_timestamp.py:81-83`). **code** | None today (not called from recordings) |
| False `CAP_PROP_BUFFERSIZE` comments | `determine_backend.py:34-35, 39`; `create_cv2_video_capture.py:21-27`. **code**; set returns False (**measured**) | Misleading |
| Camera death mid-recording | Peers may be one frame ahead; `validate_frame_metadatas` raises after `_info.json` is written (`process_and_save_recording_timestamps.py:34-48`; `recording_finalizer.py:55-61`) | Recording without timestamp CSVs (**inferred**, not tested) |

### 2.4 What changed since the earlier review

`docs/skellycam_timestamps_review.md` read the older `dom/research` code (`55f851e4`). On development-streaming (**code**, from an old-vs-new diff of the 72 differing files):
- **Timing model: unchanged.** Grab midpoint, lockstep gate, index pairing, no device time, the ISO bug, dead helpers and the false comments are all still there. Its P1–P5 findings still hold. One citation needs correcting: its quotes from the `opencv_get_frame.py` docstring are swapped (readout is line 26, jitter is line 28).
- **New and important:** `skellycam/core/timestamps/recording_timing_reader.py`.
  - `read_recording_timing` returns `{frame_index: timestamp.from_recording_start.sec}` and requires strictly increasing values (80–117).
  - `resolve_camera_timing` requires the CSV to cover exactly `range(video frame count)` (65–68). It falls back to `k/fps` when there is no CSV.
  - freemocap now calls it, so **the grab-midpoint stamp now reaches freemocap's outputs**. The earlier review said freemocap ignored skellycam's timestamps; that is no longer true.
- **Changed:** after 30 failed grabs or retrieves the loop raises and stops the whole camera group (`opencv_camera_loop.py:86-92, 126-130`). The frame-rate reset measures from `previous_tik` as set at loop line 82 (just after `get_frame`) to the reset check (169). So it times the shm copy and video write, not the frame interval (§2.3).

## 3. How freemocap, skellytracker and skellyforge use it

| Consumer | Code | Uses | Assumes equal counts? | Assumes frame *k* is simultaneous? |
| --- | --- | --- | --- | --- |
| Timing resolver | `freemocap/core/reconstruction/recording_timing.py:20-47` | Per-camera CSV, else `k/fps`. Group time = multiframe CSV, else the mean of the cameras. | yes (raises) | yes (group time = mean per index) |
| Video group, dataflow sources, camera join | `freemocap/core/pipeline/posthoc/video_group_helper.py:321-334`; `freemocap/core/pipeline/dataflow/video_sources.py:45-56`; `camera_join.py:37-38, 58-74` | Frame ordinal; each frame carries its camera's time | **raises** | one ordinal key for all cameras |
| Triangulation (posthoc and realtime) | `freemocap/core/reconstruction/posthoc_reconstruction.py:85-91`; realtime `realtime_aggregator_node.py:906-955` | Ordinal only, no time | **raises** | **yes, implicitly** |
| Calibration (ChArUco → Anipose) | `freemocap/core/pipeline/posthoc/posthoc_aggregation_node.py:135-171`; `freemocap_anipose.py:437-452`; `bundle_adjust.py:570-591` | Ordinal; one board pose per merged frame | raises | yes; no check that the board is still |
| Tracker timestamps (dataflow) | `freemocap/core/pipeline/dataflow/tracker_adapter.py:37-49, 120` | **Group** time as integer ms; must strictly increase | yes | yes |
| Legacy detection | `freemocap/core/pipeline/posthoc/mocap_detection.py:73-137` | Ordinal; no `timestamp_ms` passed (115) | raises | yes |
| Butterworth filter | `freemocap/core/reconstruction/posthoc_filtering.py:50-119` | Group time. Rate = 1/median; runs split at > 1.5 × median; resampled to a uniform grid and back | – | no (time-aware) |
| Gap filling | skellyforge `core/trajectories/gap_filling.py:7, 49-103` via `freemocap/core/reconstruction/trajectory_gap_filling.py:35-39` | Group time; fills only gaps ≤ 100 ms | – | no |
| Alignment and centre-of-mass derivatives | skellyforge `core/biomechanics/{body_alignment,ground_alignment,derived_kinematics}.py`; `freemocap/core/reconstruction/mocap_alignment.py:32, 76-80` | Group time, real Δt | – | no |
| Persistence and exports | `freemocap/core/recording/result_processing/observation_publication.py:75-233`; `exports/arrays.py:156-177`; `exports/wide_csv.py:256` | 2D rows: per-camera time. All 3D rows: group time. | checks frame number = group ordinal | – |
| Saved reload | `saved_observations.py:61-110` | Rebuilds timing from Parquet | raises | – |
| Blender | `freemocap/core/blender/helpers/validate_saved_scene.py:36-41` | Uniform scene rate 1/median(Δt); true times kept only as metadata | – | – |
| Playback server and UI | `freemocap/api/http/playback/playback_router.py:69-87, 784-806`; `freemocap-ui/src/components/playback/usePlaybackController.ts:38-141` | Leader video's fps; **every** video seeked to `frame / leader_fps` | yes | yes |
| Realtime 1€ filter, velocity gate, XCoM | `realtime_aggregator_node.py:248-258, 897, 970, 992` | `time.perf_counter()` when the **aggregator** runs, not capture time | – | – |
| Realtime 2D 1€ filter | `freemocap/core/pipeline/realtime/camera_node.py:329-336` | `t = time.perf_counter()` when the camera node runs | – | – |
| Realtime MediaPipe (skellytracker) | skellytracker `mediapipe_pose_detector.py:105-110`; freemocap `camera_node.py:316-318` | `time.monotonic()` at detect time | – | – |
| Realtime camera node | `freemocap/core/pipeline/realtime/camera_node.py:287-311, 377-379` | Each camera node reads slot *k* from its own ring buffer. On a mismatch it warns, then publishes the frame under its actual number | warns, does not skip | yes |
| Realtime batched skeleton inference | `freemocap/core/pipeline/realtime/realtime_skeleton_inference_node.py:201-216, 321-325` | Reads slot *k* from every camera's ring buffer | skips a mismatched camera | yes |
| Posthoc ChArUco cache alignment | `freemocap/core/pipeline/posthoc/video_node.py:368-381, 491-509`; cache keyed by connection frame in `realtime/charuco_recorder_node.py:96-104` | `connection_frame_number` per camera CSV, used to map realtime ChArUco observations onto recorded frames | per-camera map; raises on duplicate recording frames | – |
| Recording statistics in the UI | skellycam `core/recorders/videos/recording_statistics.py:13-22` via `freemocap/api/http/playback/playback_router.py:403, 850`; `RecordingBrowser.tsx:296, 669-674`, `PlaybackContext.tsx:126` | fps = (N − 1) / span of the multiframe times; duration = span | – | – |
| skellytracker 1€ keypoint smoothing | skellytracker `core/tracker/detection_stage.py:810-818` | Δt = 1 frame | – | off in freemocap (`keypoint_smoothing=None`) |
| `/recording/check_sync`, skellysync | `freemocap/api/http/mocap/mocap_router.py:153-178, 234-282` | "Synchronized" = equal frame counts; skellysync trims videos (source not read) | yes | yes |

All entries above are **code**.

**Assumption in force:** "same ordinal = same instant". freemocap's own plans write this down: "select the same ordinal in every source. Do not infer a different per-camera frame from capture timestamps" (`current-work-plans/.../client-playback-design.md:195-197`). The same plans also point the other way for the future: "Different rates belong on timestamp timelines" (`media-identity-and-camera-matching.md:86`). **code (docs)**

**Defects found on the freemocap side** (independent of capture):
- **D1.** The playback UI seeks every video to `frame / leader_fps`, but skellycam writes a different container fps per camera. With 34.28 vs 34.74 fps, a follower is 13 frames off at frame 1000 (**code**; size **inferred**, not seen in the app).
- **D2.** 3D playback looks up group time ≤ the leader camera's time, so it is sometimes one frame behind (**inferred**).
- **D4.** The legacy path passes no `timestamp_ms` to the tracker. **code**
- **D5.** A truncated JPEG decodes without any error (**measured**, synthetic; §5.4).

## 4. Error budget per option

Errors are per camera, 1280x720 MJPEG at 30 fps, fixed exposure, unless stated. "Today" means the stored grab midpoint. Source tags:
- **M-live**: measured today, `LIVE/analysis_tables.md`.
- **M-re**: measured today by re-analysing older raw data, `REANALYSIS/`.
- **M-old**: measured in earlier runs; the file is given.
- **I**: inferred.

| Component | Today (OpenCV DShow, grab midpoint, lockstep) | Option 1 (revised DShow, no gate, post-retrieve + fit) | Option 2 (custom MF raw MJPEG, tier 0, fit) | Reference: tier 1 PTS/SCR |
| --- | --- | --- | --- | --- |
| **Per-frame random error, raw** | Camera alone: C922 4.62, C930e 5.65 ms std (max 47 ms) [M-live A1] | 4.63–4.78 ms std, max 8.8–13.8 ms [M-live B1–B3] | 4.54–4.73 ms std, max 8.0–10.6 ms [M-live MF runs], except Kiyo arrival in `mf_kiyo`: 5.30 ms std, max 85 ms; 4.7–5.2 ms vs flash [M-re] | not applicable |
| **16 ms delivery grid** (part of the line above) | present: uniform 0–16 ms, 16/√12 = 4.62 ms [M-live; M-old `docs/windows_timer_resolution.md`] | present (same grid; coherence 0.94–0.999, ≥ 0.98 except A1_c930e at 0.94) [M-live] | present [M-live]. `timeBeginPeriod` does not remove it [M-old `RERUN_20261027.md:220`] | absent (camera clock) |
| **Per-frame random error after the frame-slot fit** | no fit | ~0.5–2 ms [I]. Envelope and least-squares lines agree to 0.01–0.30 ms (B runs; internal consistency only) [M-live]. Split-half slopes differ by up to 49 ppm (2.5 ms extrapolated) on free DShow runs [M-live]. Never scored vs ground truth | **≤ 0.56 ms** vs flash, C922 and C930e, offline whole-run, robust arrival or two-stage fit; robust sample-time fit 2.0 ms on the C930e [M-re `flash_gt_perframe.json`]. 0.02–0.15 ms typical vs camera clock [M-re `camera_clock_scores.json`]. Kiyo 1.0–1.9 ms with sample-time slotting; arrival-only slotting 29.7 ms (3 false drops) [M-live, M-re]. Causal: C922 0.56–0.75, C930e 1.5–3.9 ms by variant [M-re] | ≤ 0.56 ms vs flash (method floor) [M-re]; C922 STC cadence 2 µs [M-old `suite_20261106T224912Z/analysis/ts.md`] |
| **Stale-frame and lockstep error** (faster camera in a group) | 13.0–16.2 ms std, max 35.8–41.1 ms; 54–96 % of frames already waiting [M-live A2, A3]. A4 (two cameras behind one hub): 12.2–20.6 ms, indicative | Gone without the gate [M-live B]. With the gate kept, stale frames need a flag, and their slot is ambiguous (the DShow slot rule matched 57 % of fresh frames for the A3 C930e) [M-live] | Sample time stays correct when the app reads late [M-old/today: OpenCV MSMF NV12 run, `OCV/msmf_c930e_rawfirst/`]; would also hold for custom MF [I] | same as option 2 |
| **Gross pairing error** (frame *k* across cameras) | Stamps say 0.2 ms apart. Error in the stored difference: 19.9 ms std (A2), 11.3 ms std (A3). Lattice difference −52..+26 and +18..+81 ms [M-live] | Same if frames stay index-paired. With pairing by fitted time: median 7.8–9.7 ms; within P_slower/2 (≤ 19.4 ms) inside the overlap, edge frames excluded (the analysis did not restrict pairing to the overlap, so its abs max reaches 44–321 ms at the run edges) [M-live B2, B3]. With 2D interpolation: stamp error + interpolation error (a few mm at 5 m/s) [I] | same as option 1 [M-live MF pairs] | same |
| **Drop handling** | Invisible. Forced drops on the faster camera: A2 3, A3 320, A4 6/2/1 [M-live] | Inferred from slot gaps between fresh frames. No counter (`POS_FRAMES` = −1) [code, M-live]. True-positive detection untested. At 30 fps drops must be found by lattice or phase slotting, not a gap threshold; at 60 fps per-frame slotting becomes ambiguous [M-live, `timing/ts_accuracy/live/analyze.py` slotting] | On an OpenCV MSMF run, `POS_MSEC` slot gaps (99) match the deficit expected from duration × camera rate; there is no independent drop counter [today, `OCV/fit_stamps.json`]. False drops at start-up on the generic camera and the Kiyo [M-re]. True-positive detection on custom MF untested. Same 60 fps limit. | PTS gaps are exact (C922, C930e, Kiyo; the generic camera has no PTS) |
| **Constant per-camera bias** (light → stamp) | Unmeasured. One period early when alone; under the gate it varies, so it is not constant | **Unmeasured.** Includes DShow's in-graph decode, ~8–9 ms CPU per frame, of which the constant part depends on JPEG size and so on the camera [I]; no extra jitter visible [M-live] | **Unmeasured.** MF sample time on the generic camera is 32.2–32.5 ms earlier relative to arrival than on the others (0.2–0.8 ms) [M-re]. Envelope quantile choice shifts the offset 1.3–6.1 ms [M-re] | Unmeasured absolute. C922 PTS sits near the end of exposure (provisional) [M-old REPORT finding 12] |
| **Cross-camera bias** | Unmeasured; hidden under the pairing error | Unmeasured. Flash hints: C930e − C922 = 4.4–30.7 ms across 6 runs, +12.8 ms at a fixed row; confounded with scan-out, image row and exposure [M-re `existing_gt_aggregates.json`] | same | Best figure: C930e (libusb SCR) − C922 (PTS) spread 0.54–0.79 ms over 5 runs; driver swap, out of scope [M-old REPORT.md:40] |
| **Drift** (camera clock vs QPC) | Host stamps follow QPC; no model | The fit's period absorbs it | C922 −1.6 ppm, C930e +39.9 ppm; one run's own estimate scatters ±50 ppm [M-re]. Over a 10-min take, 40 ppm is 24 ms if a nominal period were used [I]; a whole-run fit removes it | camera clock is the reference |
| **Exposure (E/2) and rolling shutter** | E/2 = 3.9 ms at −7, up to ~16 ms under auto exposure; readout ~30–31 ms per frame height (C922 upper bound) [M-old REPORT.md, `VERIFY_method.md`] | same | same | same |

How to read this table:
- **What a tier-0 fit removes:** the grid quantisation and other zero-mean delivery jitter (4.6 → ≤ 0.56 ms).
- **Grid phase limits the offset (inferred).** How well the lower envelope pins a camera's offset depends on how the period beats against the 16.000 ms grid. If P/grid = p/q in lowest terms, the offset resolution is about grid/q. At exactly 30.000 fps, P/grid = 25/12, so only 12 phases occur and the offset is quantised in steps of up to ~1.3 ms. Near 25 fps (2 phases) or 31.25 fps (1 phase) the offset uncertainty grows to 8–16 ms. This error is constant, so it never shows in a std, but it goes straight into the cross-camera bias and depends on the phase at stream start. The measured rates (30.000 / 30.085 / 30.019 / 25.757 fps) happen to avoid the worst cases. The timestamp module should check P/grid phase coverage per camera.
- **What removing the gate removes:** the stale/lockstep term, and the false "simultaneous" labels.
- **What neither removes:** the per-camera constant bias and the cross-camera bias, or exposure and rolling-shutter timing. Only a light-based measurement (the A5 strobe rig) can size the bias.

## 5. Measurements made for this report

### 5.1 Live run, 2026-11-09 (`LIVE/`, harness `research/usb_cameras/timing/ts_accuracy/live/`)

**What ran:**
- 15 runs of 75 s: 1280x720 MJPEG, 30 fps requested, exposure −7. Every command was wrapped in `tools/camlock.py` with a timeout.
- **A runs**: an emulation of skellycam's capture loop (same calls, same order, gate, overlay, shm copy, in-loop writer).
- **B runs**: the same capture with no gate and post-retrieve stamps.
- **C runs**: `timing/build/mf_uvc_timing.exe`, MF raw MJPEG.
- The real skellycam server was **not** run.
- **Deviations from skellycam** (`LIVE/README.md`): (1) every camera's exposure was set again 1.5 s after its first post-configuration frame; (2) the gate opened only after every camera had streamed 2.5 s. Real skellycam does neither. As a result, in real skellycam the C930e stays at its default exposure for the whole recording (image mean 84–103 before the re-set against 14–19 after, `LIVE/A*.session.json`). No frame intervals were logged before the re-set, so shipped skellycam's C930e frame rate and period stability are unmeasured.
- **Conditions:** dark scene with low-detail JPEGs (brightness medians 4.5–32; writer 0.4–0.5 ms per frame). Decode, writer and USB transfer costs in a bright, textured scene are unmeasured.
- Commands are in `LIVE/README.md`.

**Scoring:** each stamp is compared with the camera's own frame lattice t_k = t0 + P·k. The lattice is fitted on the lower envelope of fresh post-retrieve or MF stamps, and slots come from a periodogram. The camera's rate is fixed by its exposure, so the lattice stands in for capture time up to a constant.

Per-frame error, std / p95 / max in ms (**measured**, `LIVE/analysis_tables.md`):

| Camera | (A) grab midpoint, as stored | (A) post-retrieve | (B) post-retrieve, no gate | (C) MF sample time | (C) MF arrival |
| --- | --- | --- | --- | --- | --- |
| C922 alone | 4.62 / 7.56 / 8.45 | 4.61 / 7.54 / 8.38 | 4.63 / 7.61 / 10.57 | 4.60 / 7.93 / 7.99 | 4.62 / 7.66 / 8.12 |
| C930e alone | 5.65 / 10.04 / 47.37 | 5.40 / 9.88 / 18.18 | 4.66 / 7.69 / 10.42 | 4.63 / 7.61 / 9.35 | 4.63 / 7.62 / 10.12 |
| C930e with Kiyo | 16.19 / 29.62 / 35.84 | 7.29 / 15.38 / 25.50 | 4.78 / 7.90 / 13.83 | 4.63 / 7.61 / 9.88 | 4.63 / 7.59 / 8.99 |
| C930e with generic | 12.96 / 23.90 / 41.10 | 12.47 / 23.08 / 32.15 | 4.65 / 7.66 / 9.85 | 4.63 / 7.64 / 9.14 | 4.64 / 7.64 / 10.13 |
| Kiyo with C930e | 7.59 / 17.63 / 31.01 | 4.71 / 7.86 / 10.19 | 4.71 / 7.91 / 10.23 | 4.73 / 7.94 / 10.49 | 4.73 / 7.93 / 10.55 |
| Generic with C930e | 4.70 / 7.73 / 10.86 | 4.69 / 7.69 / 10.67 | 4.63 / 7.59 / 8.75 | 4.62 / 7.60 / 8.03 | 4.62 / 7.61 / 8.09 |
| All three (A4: C922, C930e, Kiyo) | 12.2–20.6 std, max 46–68 | 14.8–15.7 std | – | – | – |

Pairing of frame *k* across cameras under the gate (**measured**):

| Run | Stored-stamp difference | Lattice-time difference, median [p5, p95] (min..max) | Error in the stored difference, std |
| --- | --- | --- | --- |
| A2 C930e − Kiyo | 0.21 ms | −27.1 [−48.6, 17.9] (−52.4..25.9) ms | 19.9 ms |
| A3 generic − C930e | −0.24 ms | 56.4 [38.4, 74.0] (17.9..80.7) ms | 11.3 ms |
| B2, B3, MF pairs: nearest neighbour by fitted time | – | median abs 7.8–9.7 ms; within P_slower/2 (≤ 19.4 ms) inside the overlap; edge frames excluded (pairing was not restricted to the overlap, so abs max is 44 ms for `mf_c930e_generic` and 321 ms for `mf_c930e_kiyo`) | – |

**What the runs show:**
- **Measured camera rates:** C922 30.000, C930e 30.085, Kiyo 30.019, generic 25.757 fps. The generic camera never reaches 30 fps at 720p.
- **Forced drops under the gate match the rate differences:** A3 C930e 320 frames vs 320 expected; A2 3 vs 4.8. **measured**
- **The lattice differences above contain each model's unmeasured constant latency and, under the gate, the age of the faster camera's stale frame.** (The 32 ms MF sample-time shift on the generic camera does not apply to these DirectShow stamps.) So the medians are not true capture offsets. The spreads (p5–p95, std) are reliable.
- **Tier-0 fits checked against the camera's clock (tier 1 used only as a reference):**
  - C930e, 65 frames (2.2 s scored from the 6 s smoke run): the tier-0 envelope line agrees to 0.10 ms with the clock mapped through a slope fitted to the same host stamps. This is a **self-consistency check, not an accuracy measurement**: the score equals the envelope-vs-least-squares gap of the same stamps (0.1006 ms), the fitted rate (30.061 fps) is ~800 ppm off the 30.085 fps of every 75 s run, and the split-half slopes differ by 2869 ppm. The flash re-analysis (≤ 0.56 ms) is the only tier-0 accuracy figure for the C930e.
  - Kiyo (`mf_kiyo`, slots from MF sample time): 1.01 / 2.22 / 3.29 ms. The Kiyo's own PTS/STC deviates ~1.0 ms from a lattice; whether that is reference noise or real exposure jitter is open (§7.3).
  - **Arrival-only slotting failed on the Kiyo.** In `mf_kiyo` it produced 3 false drops (30 ambiguous slots), and the resulting arrival lattice was 29.7 ms std (max 52.7 ms) from the camera clock. The 1.0 ms figure and the 0 slot mismatches apply to sample-time slotting only.
  - Split-half extrapolation: MF 0.03–0.56 ms (slopes ≤ 16 ppm apart); DShow free runs up to 2.5 ms (30–49 ppm apart; C930e worst). **measured**
- **The fit failed in the only three-camera run.** In A4 (C922 and Kiyo behind the same hub), the fitted lines sit 4.2–7.3 ms from their own least-squares lines (0.002–0.75 ms in every other run), and the split-half end errors are 57–65 ms (1018–1401 ppm). There is no B or MF run with three cameras. **measured**
- **Where the delay comes from:** the mean delay of fresh DShow frames above the envelope is 7.6–8.1 ms, the same as MF sample time (7.5–8.1 ms). DShow's decode therefore adds no visible jitter, at least with the dark scene's small JPEGs. Any constant part is absorbed into the envelope and stays unmeasured. **measured / inferred**

**Failures** (**measured**, `LIVE/README.md`):
- **Registry value removed mid-session, by Dom's decision.** In a separate session Dom ruled that testing is tier 0 only, and `MetadataBufferSizeInKB0` was removed from all 26 camera keys at 08:49:11 local (13:49 UTC, during run B2; `research/usb_cameras/results/windows/Gerald/metadata_revert_20261109/README.md`, `revert.log`). Only `mf_kiyo` and the 6 s smoke run carry PTS/SCR; all later MF runs are true tier 0. The value took effect at the next stream open, without a replug. Dom's replugs (09:25–09:31 local) came after the last live run (09:07 local), so no run was interrupted. **It is not set now**, and no further registry changes or PTS/SCR tests are planned.
- **Kiyo stalls.** In `mf_kiyo` it stalled for 8.1 s and 7.8 s near the end, then recovered. It was scored on the 60 s before the first stall (3 s to ~63 s; `LIVE/README.md` says 57 s, which is wrong). It streamed normally in four later runs.
- **A4 is approximate.** Grid coherence fell to 0.86–0.89, so A4's error sizes are indicative only. The C922 and Kiyo sit behind the same Genesys hub. This report's runs assumed a shared USB 2.0 upstream link, but the 2026-11-09 replug check records the Kiyo at SuperSpeed on the hub's USB 3 half (`metadata_revert_20261109/README.md`), so whether the two actually share bandwidth is unverified. Throughout this report, "shared link" means "behind the same hub". A4 is also evidence that the fit does not yet generalise to groups on a shared link (see above).
- **Wrong line numbers in `LIVE/README.md`.** Its line references for the emulated skellycam calls (e.g. `camera_orchestrator.py:381-394`) are wrong; that file has 137 lines. The correct locations are the ones in §2.1 of this report. The emulated call sequence itself matches the source.

### 5.2 Re-analysis of existing data (`REANALYSIS/`, scripts `research/usb_cameras/timing/ts_accuracy/`)

**Per-frame flash ground truth:**
- Ground truth exists for one run only: `timing/flash_run1_repositioned` (2026-10-25, C922 + C930e, MF, 30 s, n = 85 / 95 ground-truth frames).
- Its raw MJPEG survives in `C:/Users/Dom/Documents/skellycam-raw/research/usb_cameras/results/windows/Gerald/timing/flash_run1_repositioned/capture/`, checked today.
- This corrects the earlier statement that no flash MJPEG was kept. That statement is true only for the 10-27/28 re-run.

| Method (tier 0 unless marked) | C922 std / p95 / max µs | C930e std / p95 / max µs |
| --- | --- | --- |
| MF sample time, raw | 4784 / 8186 / 8567 | 5155 / 7949 / 23387 |
| MF arrival, raw | 4713 / 7684 / 9095 | 5089 / 7915 / 21451 |
| Fit on sample time, robust whole run | 564 / 1327 / 1626 | **2007** / 3528 / 4262 |
| Fit on arrival, robust whole run | 564 / 1297 / 1610 | 536 / 1085 / 1310 |
| Fit on arrival, period from whole run, offset from a 10 s window | 561 / 1298 / 1589 | 519 / 1107 / 1361 |
| Fit on arrival, causal (10 s trailing window) | 565 / 1258 / 1557 | 3322 / 6247 / 9561 |
| Tier 1 reference: PTS mapped to the arrival envelope | 564 / 1249 / 1658 | 536 / 1081 / 1309 |

All **measured**, `REANALYSIS/flash_gt_perframe.json`. The method floor is ~0.5 ms.

**What the re-analysis shows:**
- **The C930e is fragile.** Its latency is +22.8 ms higher for the first ~2 s, which pulls least-squares and causal fits off. A two-stage fit (period from the whole run, offset from a window of 10 s or more) or the robust arrival fit reaches the floor.
- **Against the camera clock** (`camera_clock_scores.json`, 12 C922 / 8 C930e / 1 Kiyo runs; random error only): whole-run tier-0 fits typically land at 0.02–0.15 ms, with worst runs at 0.35–0.5 ms. The Kiyo has one run only, so its "fixed slope" is that run's own envelope slope and its robust whole-run arrival figure (1648 µs) is degenerate by construction: it shows only the reference's noise. The usable figures are the sample-time fit (1652 µs) and the live sample-time fit (1.0 ms). Its PTS lattice residual is 1.64 ms; the cause is open (§7.3).
- **Drops:** 0 false drops in 20 C922/C930e runs. There were false drops at start-up on the generic camera (frame 0, sample time) and on the Kiyo (arrival bursts). No run contained a real drop, so true-positive detection is untested.

### 5.3 OpenCV 4.12 internals and single-camera DShow/MSMF runs (`NOTES/opencv.md`, results `OCV/`)

C930e only, one run per variant, no ground truth. **measured** unless marked:

**DShow:**
- With 0 or 20 ms of work per iteration, `retrieve()` blocks on every frame. Post-retrieve stamps fit to a lattice leave a 4.64–4.68 ms residual (the grid).
- With 50 ms of work, `retrieve()` never blocks (0.24 ms p50). The camera loses ~1 frame in 3 **silently**, and the fit returns a clean-looking 19.90 fps with `fit_unreliable: false`. **A fit on stale stamps fits the loop, not the camera**, so stale frames must be removed first.
- `CAP_PROP_POS_MSEC` and `POS_FRAMES` read −1. `CONVERT_RGB=0` still returns BGR. **OpenCV DShow cannot return JPEG bytes** (**code** `cap_dshow.cpp:2885-2899`, **measured**).

**OpenCV MSMF:**
- `POS_MSEC` is a real MF sample time **only** with native NV12 output and `CONVERT_RGB=0` set before the first read. Otherwise it is synthesized at exactly 33.333 ms steps.
- Open time falls from 32–41 s to 0.9 s with `OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS=0`.
- In a slow loop, the `POS_MSEC` slot gaps (99) matched the deficit expected from duration × camera rate, and frame age was visible. There is no independent drop counter, so this shows consistency, not verified detection.
- OpenCV cannot select the MJPG native type and cannot read UVC metadata (**code**).
- It is a possible stopgap, but custom MF dominates it.

**Decode cost** (`decode_bench/decode_bench.json`): 1.5–2.5 ms per 720p frame with `simplejpeg`, 2.2–3.1 ms with `cv2.imdecode`. Four cameras at 30 fps need 0.2–0.4 of a core, against ~25–28 % of a core **per camera** for DShow's in-graph decode (REPORT finding 3).

### 5.4 Container probe (`research/usb_cameras/timing/ts_accuracy/harness/mjpeg_container_probe.py`, output `research/usb_cameras/results/windows/Gerald/ts_accuracy_20261109/container_probe/probe_results.json`)

90 synthetic 720p JPEGs, muxed without re-encoding and read back the way skellycam and freemocap read videos. **measured**, synthetic:
- **CFR AVI works.** cv2 and PyAV both report 90 frames at 30 fps, and PyAV decodes all 90.
- **CFR MKV works only for cv2.** cv2 reports 90, but PyAV's `stream.frames` is 0 (it still decodes 90). skellycam (`core/recorders/videos/video_file_metadata.py:30`) and freemocap (`freemocap/core/pipeline/posthoc/video_node.py:181`) take the count from cv2 `CAP_PROP_FRAME_COUNT`. Only freemocap's dataset tool `tools/datasets/inspection.py:48` reads PyAV `stream.frames`. **code**
- **VFR MKV fails.** It reports 92 frames, which breaks `resolve_camera_timing` and the equal-count checks.
- **VFR MP4 gives a misleading fps.** It reports the average, 29.35 fps.
- **VFR AVI cannot be written.**
- **Corrupt frames pass silently.** A truncated JPEG decodes with no error and no corrupt flag.

### 5.5 ISO 8601 harness

`research/usb_cameras/timing/ts_accuracy/harness/iso8601_double_offset.py`, output `.out.txt`. It calls skellycam's two conversion paths for a fixed instant in America/New_York (§2.3). **measured**

## 6. Downstream effects

### 6.1 Option 1 in skellycam (revised DShow)

**Stamps only, gate kept** (cheap):
- Store `post_frame_retrieve_ns` and a `retrieve_blocked` flag (blocked if `retrieve` took more than ~1 ms). Fit `t_k = a + P·k` per camera at finalisation, on fresh frames only, and write the fitted time into `timestamp.from_recording_start.sec`.
- Touches `create_camera_csvs.py:50-58`, the CSV dtypes (`numpy_record_dtypes.py:49-208`) and `process_and_save_recording_timestamps.py:81-84`. **code**
- Limit: under the gate the faster cameras are mostly stale (28–96 %), so their slots are ambiguous and their stamps no better than today's (**measured** A2–A4). **This variant helps only the slowest camera and cameras that run alone.**

**Gate removed** (what option 1 needs):
- Each camera free-runs, blocks in `retrieve()` on every frame, and records post-retrieve stamps (B runs: 4.6–4.8 ms raw).
- Multiframes are then assembled **by time**, not by loop index.
- That touches every equal-count site listed below (**code**, skellycam reader §4.2):
  - the gate (`camera_orchestrator.py:118-131`);
  - the shared recording window (`camera_orchestrator.py:102-116`, `camera_group.py:196-240`);
  - `VideoRecorder._validate_frame_number` (`video_recorder.py:153-160`);
  - `validate_frame_metadatas`;
  - the multiframe CSV;
  - `validate_recording`;
  - `latest_multiframe_number`, `get_latest_multiframe` and `get_images_by_frame_number` (`camera_group_shared_memory.py:32-33, 127-168`);
  - `ImagePayloadRequest` (`frontend_payload_bytearray.py:94-95`);
  - `resolve_camera_timing`.

**Other effects:**
- **Writer fps** = (frames written − 1) / (time of the last written frame − time of the first), using the fitted times of the frames actually written. Once slot-aligned output exists, use the group slot rate. A camera's own fitted period is the right container rate only when the camera runs free with no gate. Under the gate, a faster camera writes at the slowest camera's rate: in A3 the C930e fits at 30.085 fps but wrote frames at the generic camera's 25.76 fps, so its own P would make the video play 17 % fast. (**code** + **measured**)
- **Live displays:** the live frontend payload timestamp (`skellycam/core/types/frontend_payload_bytearray.py:154-155`), the "Server" capture-framerate readout (`skellycam/api/websocket/websocket_server.py:216-227`, calculator at 38-61) and the performance panel (`skellycam/api/websocket/performance_data.py:58-68`) all use the grab midpoint. They should switch to the new per-frame stamp (post-retrieve, or MF sample time/arrival). **code**
- If outputs stay slot-aligned (§6.4), the frontend and shared memory keep their single-index contract.
- DShow still decodes every frame on its own thread (~25 % of a core per camera), and frames lost inside OpenCV remain uncounted except through slot gaps.

### 6.2 Option 2 in skellycam (custom MF raw MJPEG)

**Capture and config** (~12–15 modules, **code**/**inferred**):
- `camera_worker.py:7, 51` is hard-wired to OpenCV. The loop must be split into a backend-agnostic part and a capture interface (`open`, `read() → (jpeg bytes, sample time, arrival QPC, flags)`, `set_controls`, `close`).
- Device detection (`detect_cameras_devices.py:86-110`) and exposure control need MF/KS equivalents. `research/usb_cameras/suite/windows/pymf` has `read_ctl`/`set_ctl` and the MF reader (~3,100 lines including probe code; a production subset is perhaps 1,000–1,500, **inferred**).
- `camera_id` is the first 16 bits (4 hex characters) of SHA-256(device path from `cv2_enumerate_cameras`). It falls back to `VID_PID_index`, or to the index, when there is no path (`detect_cameras_devices.py:44-54`). A collision raises at detection (107-108). If MF's symbolic link differs, every saved config and recording key changes. **Unchecked.**

**Design A, decode at source** (recommended first):
- JPEG → BGR into the existing shared-memory slot, using `simplejpeg` or `cv2.imdecode` (1.5–3 ms, **measured**). The raw JPEG can optionally be written to a CFR MJPEG AVI as a lossless copy (passes freemocap's probes, §5.4).
- Shared memory, recording, frontend and freemocap realtime stay unchanged.
- New fields in `FRAME_METADATA_DTYPE` and the hand-written CSV row dtypes: MF sample time, arrival, MF flags or discontinuity, JPEG size, decode time.
- The overlay must stop being burned in, or go on a copy.

**Design B, JPEG end to end:** about 8 more skellycam modules (shm dtype and ring sizing, recorder, finaliser shape check, frontend) and 3–4 freemocap realtime modules must decode. **inferred**

**MF behind the gate:**
- MF's reader queues frames instead of latching one, so a gated faster camera would build up latency unless the backend drains to the newest frame. The drain drops frames deliberately.
- The MF sample time stays correct for late-read frames (**measured** on OpenCV MSMF; **inferred** for custom MF).
- So **option 2 can deliver correct per-camera stamps even before the gate is removed**. Frame *k* would still not be simultaneous, but its label would be true.

**Stamp choice:**
- Fit the lattice on **arrival**, so the generic camera's 32 ms sample-time shift does not become a cross-camera bias. A fit on sample time is acceptable only in the two-stage form (0.67 ms on the C930e); the robust whole-run fit on sample time scored 2.0 ms (**measured**, `REANALYSIS/README.md` §2).
- Take the **slots** from a burst-robust source, for example MF sample time, before fitting on arrival. Arrival-only slotting on the Kiyo produced 3 false drops and a lattice 29.7 ms from the camera clock (§5.1).
- Use a two-stage or robust fit with the start-up seconds excluded, because of the C930e's start-up step.
- Keep raw sample time and arrival in the CSV as provenance.
- Arrival is `perf_counter_ns` (QPC) by construction (**code**, `research/usb_cameras/suite/windows/pymf/mf.py:44`). MF sample time is the raw `ReadSample` timestamp, not rebased (**code**, `cap_msmf.cpp:1792-1804`). That it shares the QPC timebase is **measured**: arrival − sample time is bimodal at ~0.3–1 ms or ~16 ms (`docs/capture_stack_options_plan.md:94`; `docs/windows_results_20261106.md` §4).

### 6.3 freemocap, skellytracker and skellyforge

**Better values in the existing columns, same frame model (either option):**
- **No change needed to read them** (**code**).
- **Better:** the group timeline (mean of fitted per-camera times), filter resampling, gap-fill decisions, alignment, MediaPipe timestamps and every output time label (**inferred**).
- **Changed, size unmeasured:** filtered and gap-filled 3D trajectories, because the filter resamples on group time (`posthoc_filtering.py:91-118`); MediaPipe VIDEO-mode landmarks, because their `timestamp_ms` changes (§1(d)). **code**
- **Not changed:** raw triangulated points, calibration and realtime.
- **New fields need a code change to be used.** freemocap reads only `timestamp.from_recording_start.sec`, so any new column (flag, method) is ignored until code reads it. A new `TimingMethod` value (e.g. `fitted_arrival`) is needed for provenance; only `recorded`, `inferred_from_fps` and `mean_camera_times` exist (`recording_timing_reader.py:34-37`).

**To turn better stamps into better 3D** (**inferred** from code):
- Interpolate each camera's 2D keypoints from its own times onto the group times before `observation_buffers(...)` (`freemocap/core/pipeline/dataflow/scientific_recording.py:94-99`, callers 129-130 and 304; `posthoc_mocap_task.py:144-150`). All the inputs are already in `RecordingGroupTiming.cameras`.
- Each ms of inter-camera offset is worth 2 / 5 / 10 mm at 2 / 5 / 10 m/s. Today's pairing errors of 10–50 ms are 50–250 mm for a wrist at 5 m/s, more than enough to trip the realtime 60 px reprojection rejection (`realtime_filter_config.py:94`).
- Linear interpolation over 33 ms adds ≤ 3 mm at 20 m/s² and ~14 mm at 100 m/s².
- This needs a plan change: the current plans forbid choosing a different frame per camera from timestamps (`client-playback-design.md:195-197`).

**Realtime, no skellycam change:** pass the multiframe's capture time to the 1€ filter, the velocity gate and XCoM instead of `perf_counter()` at aggregation (`realtime_aggregator_node.py:897`). Also pass it to MediaPipe as `timestamp_ms`. Today Δt follows processing cadence, so velocity can be off by up to ~2× when the aggregator skips frames. **inferred**

**Calibration:** pairing by index on a moving board costs 7–17 mm at 0.2–0.5 m/s with a 33 ms offset (**inferred**). The still-board approach (`research/rolling_shutter/still_charuco_issue/`) removes both timing and rolling-shutter error, and is cheaper than timing-aware calibration.

### 6.4 Supporting dropped frames and different rates

**What breaks if nothing downstream changes** (**code**):

| skellycam delivers | Result |
| --- | --- |
| Unequal per-camera frame counts | **Hard failure**: skellycam's own finaliser (`validate_frame_metadatas`, `process_and_save_recording_timestamps.py:34-47`; `validate_recording`, `recording_finalizer.py:168-170`); freemocap `video_group_helper.py:328-334`, `video_sources.py:46-48`, playback validity, calibration, `/check_sync` |
| Gaps in `recording_frame_number` | **Hard failure** in `resolve_camera_timing` (65–68) |
| A duplicate image in the missing slot, no flag | Runs, but **silently wrong**: a stale view is triangulated as simultaneous, and the filter treats it as a fresh sample. In realtime, the camera node would also process the repeated image as fresh |
| A repeated timestamp | **Hard failure**, first in skellycam's `read_recording_timing` (`recording_timing_reader.py:105-112`), then in `tracker_adapter.py:47-48`, `posthoc_filtering.py:53-55` and 72-74, and skellyforge `gap_filling.py:64` |
| VFR containers | VFR MKV breaks the frame-count probe; VFR MP4 breaks fps-based playback (§5.4) |
| A whole-group slot missing | Runs. The filter splits there; Blender compresses the gap without warning |

**Two ways forward** (**inferred**):

**Slot-aligned output (cheapest).**
- skellycam free-runs each camera, fits its lattice, and builds group slots on a group clock (e.g. the fastest or a nominal 30 fps camera).
- For each slot it picks each camera's nearest frame within P/2, or repeats the last one.
- Columns:
  - `timestamp.from_recording_start.sec` = slot (group-clock) time. It stays strictly increasing, so `read_recording_timing` (`recording_timing_reader.py:80-117`) does not reject repeated slots.
  - A new column = the camera's own fitted time of the frame actually used.
  - `frame_status` = fresh / repeated / missing.
  - `connection_frame_number` must still name the frame actually used, so the ChArUco cache map (`video_node.py:491-509`) stays correct; it raises on duplicate recording frames, not duplicate connection frames.
- Videos stay CFR with ordinal = slot.
- Changes needed:
  - skellycam: the `recording_timing_reader` (to expose the new columns) and the finaliser.
  - freemocap: `RecordingGroupTiming.resolve` reads the flag and turns repeated or missing views into all-missing observations. Triangulation already masks NaN cameras per point (`observation_buffer.py:33-48`, `triangulator.py:226-230`).
  - Realtime: `frame_status` carried through `FRAME_METADATA_DTYPE` to the camera node, the inference node and the aggregator. Otherwise realtime triangulates repeated images as fresh, silently.
- Cost: the faster camera's extra frames are discarded, and repeats waste slots. A 25.76 fps camera grouped at 30 fps repeats about 1 slot in 7.
- Pairing error drops to ≤ P/2 of the slower camera. Per-camera times plus 2D interpolation can take it below that.

**Time-native model (full).**
- Each camera keeps its own ordinal-to-time map, and freemocap associates by time throughout.
- About 11 freemocap sites hard-code one shared ordinal: video group, timing resolve, camera join, `ObservationCollection`, legacy loop, publication check, saved reload, triangulation, calibration aggregation, UI playback (freemocap reader A §8c) and the realtime batched inference node (`realtime_skeleton_inference_node.py:201-216, 321-325`).
- The storage model (time-first Parquet, separate `capture` and `synchronized` channels) and the filters already handle irregular times.

**Rate limits for drop detection from host stamps** (**measured**, `LIVE/README.md` "Scoring" and `timing/ts_accuracy/live/analyze.py` slotting; start-up false drops in `REANALYSIS/`):
- At 30 fps, drops must be found by lattice or phase slotting: a fresh frame's delay above the envelope stays below P (0 to ~22 ms, from the residual ranges in `LIVE/analysis_tables.md`). A gap threshold fails even at 30 fps, because on the 16 ms grid a normal gap can be P + 16 = 49.3 ms and a one-drop gap 2P − 16 = 50.7 ms.
- At 60 fps the delay spread exceeds P = 16.7 ms, so per-frame slotting becomes ambiguous (**inferred**).
- Slotting must be burst-robust: arrival-only slotting on the Kiyo invented 3 drops (§5.1).
- Start-up seconds need excluding.

## 7. Recommendation and order of work

### 7.1 Recommendation

**Go to option 2 (custom MF, raw MJPEG, tier 0), Design A, and pair cameras by time.**

What option 2 gives (**measured** and **inferred** as in §1(f)):
- the same per-frame floor as option 1;
- stamps that stay correct under any read timing;
- drops that are visible;
- roughly a quarter to a half of the CPU, even with decoding at source (DShow ~25 % of a core per camera vs MF 1–2 % plus ~5–10 % decode; capture process only, Frame Server excluded; dark scene);
- JPEG bytes for lossless recording;
- a later tier-1 path.

Option 1 is worth doing only if the switch to MF is far off. Its benefit depends on removing the gate, which is the expensive part of either option.

**Raw 3D pairing accuracy stays the same until pairing changes.** Without slot-aligned assembly or 2D time interpolation, the improvement shows up in time labels, playback, and the filtered and gap-filled trajectories (which resample on group time). MediaPipe VIDEO-mode landmarks may also shift. Cross-camera accuracy stays limited by the unmeasured latency bias until the A5 rig sizes it.

### 7.2 Order of work

1. **Fixes needed whatever else happens** (small; **code**):
   - the ISO 8601 bug;
   - the C930e exposure loss: set the format once, before exposure, or open with `[W, H, FOURCC]` params (`cap_dshow.cpp:3363-3383`);
   - store a `retrieve_blocked` flag;
   - writer fps = (frames written − 1) / (time of the last written frame − time of the first), from the fitted times of the frames actually written; once slot-aligned output exists, the group slot rate. Not the camera's own period while the gate is in place (§6.1);
   - stop burning the overlay into the image;
   - freemocap playback D1/D2;
   - the realtime filter's `t` = capture time.
2. **Timestamp module** (stdlib, as `capture_stack_options_plan.md` C1 asks):
   - slotting, robust two-stage lattice fit, start-up exclusion, drop and repeat flags;
   - burst-robust slotting (slots from MF sample time where available) before an arrival fit;
   - change-point detection (residual steps, gaps over N·P, exposure-control changes), with a separate lattice per segment and the offset re-estimated after every stall;
   - a per-frame `fit_unreliable` flag that falls back to the raw post-retrieve or arrival time, and no drop flags across a period change;
   - a per-camera validity check on P/grid phase coverage (§4);
   - one envelope quantile for all cameras;
   - run at finalisation (offline, whole recording);
   - write fitted times into the existing column plus provenance columns.

   Usable on DShow post-retrieve stamps now, and on existing recordings for cameras that were not stale.
3. **MF capture backend** behind a capture interface, Design A (decode at source), drain-to-newest under the gate, raw JPEG optionally archived in CFR AVI. Check `camera_id` stability first.
4. **Gate removal with slot-aligned assembly** (§6.4) plus the freemocap flag reader. This is what allows different rates and honest drop handling.
5. **freemocap 2D time interpolation before triangulation**, including the rolling-shutter row term. It needs a plan change. This is the step that turns timing accuracy into 3D accuracy.
6. **Tier 1 (optional)**, where the admin step is accepted: PTS/STC with per-camera validation.

### 7.3 What remains unmeasured, and the tests that would settle it

| Open point | Why it matters | Test |
| --- | --- | --- |
| **Absolute and cross-camera light-to-stamp bias** (K, K_rel) per model and per stamp type (MF arrival, MF sample time, DShow post-retrieve) | Not removed by any tier-0 method. Flash hints at several ms to ~30 ms between models, confounded with scan-out and image row | **A5 strobe rig** (`research/usb_cameras/sync_rig/atoms3_sync_rig/`, `timing/rig/`; firmware compiles, never flashed): all four cameras viewing one LED, K_rel per camera, repeated across sessions and exposures |
| Causal / live fit accuracy vs ground truth, and the DShow post-retrieve fit vs ground truth | Option 1's ~0.5–2 ms is inferred; causal C930e fits are 1.5–3.9 ms | The same rig, scoring the `ts_accuracy` fits on DShow (B mode) and MF runs |
| True-positive drop detection | No scored run contained a real drop | Induce drops (C922 + generic behind their shared hub, or a deliberately slow reader) with a PTS camera as reference; count detected vs PTS gaps |
| Long recordings | All scored runs are 30–75 s. C930e period-mode switches (two modes ~0.12 % apart) and drift over minutes are untested | 10–30 min MF runs per camera, fit on windows vs whole run, with a camera-clock reference where available (registry value now removed, see §5.1) |
| Auto exposure and stalls | AE changes the frame period. With exposure auto priority on, low light can lower the frame rate (`docs/chromium_comparison.md:188`), and a halved rate would look like every other frame dropped (**inferred**, not seen in this study) and moves exposure start by up to E/2. The Kiyo stalled for 8.1 s and 7.8 s and recovered at an unknown phase. A single whole-run fit across such changes gives large errors | Repeat the live A/B/C set under AE in normal light and dimming light; test the change-point segmentation of §7.2 step 2 on the `mf_kiyo` stalls |
| Kiyo cadence (1.0–1.6 ms) | Whether it is exposure jitter (real) or delivery jitter (fit-removable) | Strobe rig on the Kiyo |
| Real skellycam on this branch, including the C930e at its default exposure | The live A runs are an emulation that re-set exposure and delayed the gate, so shipped skellycam's C930e period, drops and stamp error are unknown | A short headless recording (C930e alone, then C930e + C922), or the emulation with no exposure re-set. Log frame intervals at default exposure. Compare writer fps with 1/median frame interval, and the stored stamp with `frame.post_frame_retrieve.ns` |
| Three or more cameras behind one hub | The fit failed in A4, the only three-camera run; no B or MF run has three cameras | B-mode and MF runs of C930e + Kiyo + C922 (C922 and Kiyo behind the same hub), scoring the fit's residual, split-half error and slot agreement |
| Bright, textured scene | All live runs were in a near-dark scene (low-detail JPEGs); decode, writer, transfer time and CPU may grow | Repeat A1/B1/C in normal light with a textured scene |
| MF symbolic link vs DShow device path | Decides whether `camera_id` survives the backend swap | `wincam list` vs `cv2_enumerate_cameras` on Gerald (no streaming needed) |
| DShow decode bias per camera | Part of option 1's constant bias | Strobe rig, DShow and MF on the same camera |

### 7.4 Reproducibility notes

- **Durable:** the live and re-analysis harnesses and results are in the repo tree (`research/usb_cameras/timing/ts_accuracy/`, `LIVE/`, `REANALYSIS/`).
- **Also in the repo tree:** the OpenCV internals scripts (`timing/ts_accuracy/opencv/`) and results (`OCV/`), the ISO 8601 harness, container probe and grid script (`timing/ts_accuracy/harness/`), the container probe's `probe_results.json` (`ts_accuracy_20261109/container_probe/`) and the code-reading notes (`NOTES/`).
- **Not kept (rebuildable):** the OpenCV 4.12.0 `videoio` sources (upstream tag `4.12.0`), the synthetic probe videos (re-run `mjpeg_container_probe.py`), and the development-streaming code snapshots (`git archive` at the commits in the header; skellyforge `f5404db`).
