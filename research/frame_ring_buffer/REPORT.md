# Frame Ring Buffer Study — Report

Status as of 2026-10-28: **done** (code mapping, verification and research finished on 2026-10-25; every benchmark stage ran or re-ran in the idle overnight run of 2026-10-27/28 and was then critiqued, partly re-run and revised; nothing in `research/` is committed yet). Raw material: this folder; study state and stage table: [study_state/RESUME.md](study_state/RESUME.md); which numbers are idle vs provisional: [PROVISIONAL.md](PROVISIONAL.md).

## Executive summary

The study asked how SkellyCam moves frames to FreeMoCap through its shared-memory ring buffer (a fixed set of frame-sized slots in shared memory that camera processes write and readers copy out of), whether that path can carry 5 cameras at 60 fps without losing recorded frames, and whether porting it to C++ would help ([RESUME.md](study_state/RESUME.md)). The code paths were mapped and adversarially verified, then benchmarked with the real SkellyCam stack (commit `23ccbf20`) driving 5 synthetic 60 fps cameras, plus 12 Python prototypes, a C++ head-to-head, a reproducibility re-run and a revision round that answered 34 critic issues (30 resolved, 4 partly). At 5x1920x1080 with the MJPEG decode inside the capture loop, current SkellyCam reaches only 53.56 / 53.57 fps per camera; 964 sensor frames (10.7%) are never grabbed, and SkellyCam does not count or report that loss ([e_e2e_summary.md](baseline/results/e_e2e_summary.md), [baseline/README.md](baseline/README.md)). 5x1280x720 holds 60.00 fps. The biggest single fix is small: removing one `copy.copy` from `put_data` lifts the same configuration from 54.14 (HEAD re-measured in the same session) to 58.84 / 58.98 fps ([e2ev_summary.md](baseline/results/e2ev_summary.md)). A prototype with a seqlock ring (a ring whose slots carry a sequence counter so readers can detect a frame being overwritten mid-read) and a recorder decoupled from the capture loop, with SkellyCam's lockstep kept, reached 59.82 / 59.95 fps, but the headroom is thin: 3 ms more CPU per frame drops it to 58.08 fps ([p8v_e2e_summary.md](prototypes/results/p8v_e2e_summary.md)). The default MSMF `.mp4` recording is not crash-safe (0 of 300 frames readable after a kill), while MJPEG-in-MKV keeps 298 ([p11_crash_container.md](prototypes/results/p11_crash_container.md)). C++ is not needed: with the same algorithm it is only 2-7% faster, and with the same one-copy design numpy matches it ([cpp_comparison.md](cpp/results/cpp_comparison.md)). Every 5x60 number comes from synthetic cameras on one Windows 11 / i7-14700K machine; no real camera attached delivered more than 30.1 fps, so the next step for skellycam is to ship the small Python fixes and re-measure with real 60 fps cameras.

## Key findings

Confidence labels: **measured** = read from a result file of an idle run; **provisional** = measured but flagged by the study as loaded or superseded; **inferred** = reasoning or arithmetic from measurements, not a direct test.

1. **HEAD misses 60 fps at 5x1080p with the MJPEG decode in the capture loop, and the loss is silent.** 53.56 / 53.57 fps per camera (2 runs, UI on), 964 / 964 sensor frames never grabbed out of 9009 / 9014 (10.7%); without the UI 55.94 fps (605 never grabbed, 6.7%; a later repeat gave 55.62 fps, 655). The recorded frames were consecutive and every file decoded to exactly the recorded count, so the loss happens *before* the recorder; the finalizer passes and shows only "Mean Framerate 53.93 Hz". With a decode-free retrieve stand-in (memcpy) 1080p holds 59.99 fps, and 720p MJPEG holds 60.00 fps ([e_e2e_summary.md](baseline/results/e_e2e_summary.md), [baseline/README.md](baseline/README.md), [baseline_result.json](study_state/baseline_result.json)). Reproduced at 53.92 / 53.97 fps (911 / 902 never grabbed) ([reproducibility/comparison.md](reproducibility/comparison.md)). **Measured.**

2. **The limit is the loop body plus the lockstep gate.** Lockstep is SkellyCam's rule that no camera grabs frame k+1 until every camera has finished frame k. The finalizer shows a 15.77 ms median per-frame processing time (retrieve 10.04, `put_frame` 3.56, record 1.14 ms plus small idles) and 2.49 ms median idle waiting at the gate, giving an 18.69 ms group interval against a 16.67 ms budget ([recommend_result.json](study_state/recommend_result.json) `current_state_verdict`, from `e_e2e_1080p_mjpeg_ui.json` `finalizer_stats`; [baseline/README.md](baseline/README.md) L169). The isolated `put_frame` rate (353 fps per camera at 5x1080p, [a_write.md](baseline/results/a_write.md)) does not reflect its in-loop cost of 3.64-3.73 ms ([e_e2e_summary.md](baseline/results/e_e2e_summary.md)). **Measured** (the attribution to the gate is **inferred** from the timing breakdown).

3. **Removing `copy.copy` from `SharedMemoryRingBuffer.put_data` is the largest single measured gain.** Alone, in the real stack: 58.84 / 58.98 fps with 170 / 150 never grabbed, against 54.14 fps and 878 for HEAD in the same session; `put_frame` median 3.61 → 1.29-1.38 ms; 2.50-3.19 ms of gate idle remains ([e2ev_summary.md](baseline/results/e2ev_summary.md), [revision/README.md](revision/README.md)). It removes 6,221,432 B of copy per 1080p frame ([recommend_result.json](study_state/recommend_result.json) rank 9). **Measured** (2 runs).

4. **The recommended design reaches about 60 fps on synthetic cameras, with little headroom.** Seqlock ring + recorder decoupled from the capture loop, lockstep and per-frame metadata writes kept: 59.82 / 59.95 fps, 20 / 0 never grabbed; recorder as a thread in the camera process: 59.93 fps, 1 never grabbed. With 3 ms extra CPU per frame on the capture thread (decode 14.5 ms, near the top of the 11.0-14.7 ms CPU per 1080p frame measured on real cameras at 30 fps) it drops to 58.08 fps, 276 never grabbed ([p8v_e2e_summary.md](prototypes/results/p8v_e2e_summary.md), [p9_real_camera.md](prototypes/results/p9_real_camera.md)). The prototype copies the decoded frame into the slot and polls the gate with `time.sleep(1e-5)`, so ranks 11 and 13 are *not* in this number ([RESUME.md](study_state/RESUME.md) audit notes). Not modelled: pubsub polling, the deepcopy in `should_grab_by_id`, the start/stop handshake and the finalizer. **Measured on a prototype**, not on SkellyCam.

5. **The default recording does not survive a crash.** After `TerminateProcess` with 300 frames written: cv2 'X264' → MSMF `.mp4` (SkellyCam's default) 0 of 300 frames readable at 720p and 1080p (no index is written until `release()`); PyAV MJPEG passthrough `.mkv` 298 (killed idle) / 359 of about 360 (killed mid-write); h264_nvenc fragmented MP4 or MKV 233-237 (idle) / 291-297 (mid-write), losing the frames inside the encoder pipeline. Clean release gives 300 in every case ([p11_crash_container.md](prototypes/results/p11_crash_container.md)). **Measured.**

6. **One stalled recorder: lockstep keeps cameras in sync; without it they silently drift.** 1080p, ring of 172 slots (2.87 s), camera 0's recorder stalls at t = 3 s. A 1000 ms stall is lossless under every policy. A 3500 ms stall: blocking without lockstep records 445 vs 481 frames on camera 0, and camera 0's frame k was captured up to 606 ms later than the others' (92 frames out of sync by at least one period); dropping without lockstep gives 443 vs 481 and up to 639 ms. Both pass every frame-count check. Block + lockstep records 445 frames on all 5 cameras, all skipping the same 36 sensor ticks, with the capture-time spread staying at 6.3 ms ([p3v_asymmetric_stall.md](prototypes/results/p3v_asymmetric_stall.md)). With the current overwrite policy, a ring-reading recorder loses frames silently once a stall exceeds the ring (195 lost, non-consecutive output, at L=172 and 3500 ms; [p3_lossless_record.md](prototypes/results/p3_lossless_record.md)). **Measured** (synthetic 2 ms recorders).

7. **`cv2.setNumThreads(1)` roughly halves recorder CPU at the same encode rate.** SkellyCam's real `VideoRecorder`, 5x1080p, unthrottled: 115.8 fps at 1826% CPU (default, 28 threads) vs 116.1 fps at 896% (1 thread); paced 60 fps under a concurrent decode load: 1185% vs 481%, all 60.0 fps with 0 late writes, `record_frame` median 1.88 vs 2.67 ms (100% = one logical CPU) ([p10v_msmf_threads.md](prototypes/results/p10v_msmf_threads.md)). In the real stack with the encode still inline it cut children CPU from 1338% to 713% (54.14 → 54.74 fps), but combined with rank 9 it gave 58.29 fps vs 58.84 / 58.98 for rank 9 alone ([e2ev_summary.md](baseline/results/e2ev_summary.md)). **Measured** (the earlier `p10_msmf_threads` run is **provisional**: Defender scanned during its last row, [PROVISIONAL.md](PROVISIONAL.md)).

8. **The UI relay is limited by its 10 ms sleep plus the build, not by the ring.** The real HEAD relay path gives 46.0 payloads/s at 1080p (9.39 ms per payload for shm copy plus build, isolated benchmark) and 36.6-36.9/s inside the full capture run ([d_ui.md](baseline/results/d_ui.md), [e_e2e_summary.md](baseline/results/e_e2e_summary.md)). Building from views in a thread pool with 2 ms polling gave 60.0-60.1/s over 4 runs, with the event loop blocked 0.04 ms per payload instead of 8.28 ms ([p6_ui_path.md](prototypes/results/p6_ui_path.md), [revision/README.md](revision/README.md)). No browser was attached. **Measured.**

9. **The disk keeps up, even with its write cache exhausted.** C: (WD_BLACK SN850X 4 TB, 224.9 GB free = 94.38% used): 64 GiB unbuffered write-through ran about 5 GB/s for the first 48 GiB, then 481-1508 MB/s; 5 paced write-through streams at 162 MB/s (MJPEG passthrough rate) for 300 s achieved 162 MB/s with a worst `write()` of 134.8 ms; at 69 MB/s (HEAD MSMF rate) for 600 s, worst 137.8 ms. The worst stall (138 ms) is about 5% of the 2.87 s 1080p ring. The free space fills in 54.3 min at 69 MB/s and 23.1 min at 162 MB/s ([p12_disk_sustained.md](prototypes/results/p12_disk_sustained.md)). Raw writes only, no encoder, Defender in its default state. **Measured.**

10. **C++ is not needed.** A line-by-line port of `put_frame` is 2-7% faster (1080p, 5 writers: 2.694 / 2.662 vs 2.765 / 2.780 ms), because the cost is the algorithm (fresh allocation plus 2 copies). With the same one-copy seqlock write, numpy and C++ match: 1080p, 1 writer 0.1466 ms (numpy) vs 0.1456 ms (C++); 5 writers 0.613-0.654 ms across numpy, pybind11, ctypes and C++. Lossless writer→reader rate at 5x1080p: numpy 527 / 537 fps, C++ 535-545, HEAD ring 243 / 250 ([cpp_comparison.md](cpp/results/cpp_comparison.md) sections 1a, 1b). The OpenCV build matters more than the language: Python cv2 4.12 decodes 1080p JPEG 1.57x faster (7.22 vs 11.32 ms) and encodes q90 4.9x faster (4.11 vs 20.00 ms) than the C++ OpenCV 4.8 SDK; at the same OpenCV 4.8.0, C++ decodes 11-19% faster (10.36-11.32 vs 12.78 ms) (section 4). **Measured**; C++ in-place decode with a current libjpeg-turbo, a native capture callback and large pages were not tested ([recommend_result.json](study_state/recommend_result.json) `cpp_verdict`).

11. **HEAD makes avoidable full-frame copies.** 2 per captured frame (`copy.copy` + slot assignment, after the decode output), 5 per UI multiframe (31.1 MB at 1080p) and 2N per FreeMoCap multiframe ([recommend_result.json](study_state/recommend_result.json), [f_copies.md](baseline/results/f_copies.md), [verified_digest.json](study_state/verified_digest.json)). Retrieving straight into the ring slot cut publish from 2.618 to 0.060 ms at 1080p in isolation ([p1_write.md](prototypes/results/p1_write.md)). **Measured** in isolation; not yet measured end to end.

12. **The study's recommendation is a Python-only redesign in 15 ranked changes.** Build order: ranks 9 (`copy.copy`), 3, 4, 5 and 2 (small effort) first, then rank 1 (contain failures), then ranks 6 + 11 + 7 together with 13 and 10, then 12, 14 and 15; rank 8 (MJPEG passthrough) is a separate project ([recommend_result.json](study_state/recommend_result.json) `headline`). The P1 exposure in the control code (a UI, websocket or FreeMoCap-node exception, 30 failed grabs, or a config change during recording can stall or end a recording) is from code review, not a fault test. **Inferred** (ranking), with per-rank evidence of mixed strength.

## Techniques compared

### End-to-end capture pipelines (5 x 1920x1080 MJPEG, synthetic 60 fps cameras, UI on, 30 s)

| Pipeline | Min-camera fps | Sensor frames never grabbed (5 cams) | Key timing | CPU | Verdict |
|---|---|---|---|---|---|
| HEAD `23ccbf20` ([e_e2e_summary.md](baseline/results/e_e2e_summary.md); same-session control in [e2ev_summary.md](baseline/results/e2ev_summary.md)) | 53.56 / 53.57 (control 54.14) | 964 / 964 (878) | `put_frame` 3.64-3.73 ms; group interval 18.69 ms | children 1345-1361% | Misses 60 fps, loss uncounted |
| HEAD, no UI | 55.94 / 55.62 | 605 / 655 | `put_frame` 3.41-3.49 ms | children 1392-1399% | UI costs about 1.5-2.4 fps |
| HEAD − `copy.copy` (rank 9) | 58.84 / 58.98 | 170 / 150 | `put_frame` 1.29-1.38 ms; gate idle 2.50-3.19 ms | children 1351-1392% | Best single change; still short of 60 |
| HEAD + `setNumThreads(1)` | 54.74 | 788 | record 2.73 ms | children 713% | Halves CPU, small fps change |
| HEAD − `copy.copy` + `setNumThreads(1)` | 58.29 | 254 | `put_frame` 1.13 ms, record 2.72 ms | children 686% | Cheapest CPU; slightly below rank 9 alone while encode is inline |
| HEAD + 3 ms retrieve CPU (sensitivity) | 48.46 | 1732 | retrieve 12.88 ms | children 1230% | Shows how close HEAD is to the edge |
| Prototype: seqlock ring + decoupled recorder + lockstep ([p8v_e2e_summary.md](prototypes/results/p8v_e2e_summary.md)) | 59.82 / 59.95 | 20 / 0 | tick→written p99 30.5 / 27.3 ms | cams 330-338%, recorders 979-1017% | Reaches 60 on synthetic cameras |
| Same, recorder as thread in camera process | 59.93 | 1 | tick→written p99 29.7 ms | 1323% in camera processes | Equivalent |
| Same + 3 ms extra CPU per frame | 58.08 | 276 | decode 14.5 ms | cams 408% | Thin headroom |
| Prototype: MJPEG passthrough recorder, decode off-loop ([p8_e2e_summary.md](prototypes/results/p8_e2e_summary.md)) | 59.97 / 59.97 | 0 / 0 | tick→written p99 1.5 ms | recorders 19-20% (vs 924-954% for decode + MSMF) | Lowest cost, but XL effort and no real camera delivered 60 fps passthrough |

### Ring write implementations (1080p, unthrottled, [cpp_comparison.md](cpp/results/cpp_comparison.md) 1a/1b)

| Implementation | Write median, 1 writer (ms) | Write median, 5 writers (ms) | Lossless SPSC fps, 5x1080p (slowest camera) | Verdict |
|---|---|---|---|---|
| SkellyCam HEAD ring (`sk_head`) | 1.3263 | 2.7652 / 2.7802 | 243 / 250 | Baseline: fresh allocation + 2 copies |
| C++ port of the same algorithm (`cpp_head_port`) | 1.2759 | 2.6941 / 2.6624 | – | Only 2-7% faster than HEAD |
| numpy seqlock, 1 copy (`py_seq`) | 0.1466 | 0.6353 / 0.6347 | 527 / 537 | Recommended (rank 6) |
| C++ ring via pybind11 (`hybrid`) | 0.1465 | 0.6210 / 0.6130 | 530 / 526 | Same as numpy; fallback if non-x86 ordering is needed |
| Same C function via ctypes | 0.1466 | 0.6537 / 0.6207 | – | Same as numpy |
| Pure C++, 1 copy (processes / threads) | 0.1456 | 0.6369 / 0.6295 | 543 / 535 (proc), 545 / 545 (thread) | Same as numpy; no reason to port |

### Recorders (5x1080p, decoupled recorder, 60 fps paced unless noted)

| Recorder / container | Holds 60 fps? | Recorder CPU | Bitrate per camera | Frames readable after a kill (of 300) | Verdict |
|---|---|---|---|---|---|
| cv2 'X264' → MSMF `.mp4` (HEAD default) | Yes (60.0) | 283% in P5 harness; 1207% for the real `VideoRecorder` ([c_record.md](baseline/results/c_record.md)) | 124.9 Mbit/s | 0 | Keeps up but not crash-safe; set threads=1 |
| Same with `setNumThreads(1)` ([p10v_msmf_threads.md](prototypes/results/p10v_msmf_threads.md)) | Yes (60.0 under load) | 481% vs 1185% default | 124.9 Mbit/s | (same container) | Do it (rank 10) |
| PyAV h264_nvenc ([p5_nvenc.md](prototypes/results/p5_nvenc.md)) | Yes (60.0) | 105% | 29.7 Mbit/s | 237 (fMP4 or MKV) | Option if H.264 needed; tick→written p99 189 ms; 12-session limit on the RTX 3070 |
| PyAV hevc_nvenc | Slowest recorder 57 fps, 693 ms backlog | 80% | 16.2 Mbit/s | – | Not recommended |
| PyAV libx264 | No (56.4, 319 frames lost) | 2442% | 8.4 Mbit/s | – | Not recommended |
| MJPEG passthrough → `.mkv` ([p4_mjpeg_passthrough.md](prototypes/results/p4_mjpeg_passthrough.md), [p11](prototypes/results/p11_crash_container.md)) | Yes (60.01) | 28% | 162.1 MB/s for 5 cams (synthetic q90 JPEGs) | 298 | Best on CPU and crash safety; larger files |

P5 cameras published with a memcpy stand-in, so its recorder CPU is not directly comparable with `c_record`'s 1207%.

### Full-ring policies for a ring-reading recorder (1080p, L=172 = 2.87 s, [p3_lossless_record.md](prototypes/results/p3_lossless_record.md), [p3v_asymmetric_stall.md](prototypes/results/p3v_asymmetric_stall.md))

| Policy | 3500 ms stall on all 5 recorders | 3500 ms stall on 1 recorder | Verdict |
|---|---|---|---|
| Overwrite (today's ring rule) | 195 frames lost silently, output not consecutive | – | Not acceptable for recording |
| Block (writer waits) | 0 lost after ring; 180 sensor ticks skipped (countable) | Camera 0 drifts up to 606 ms, invisible to counts | Only with lockstep |
| Drop (writer skips, counted) | 190 explicit drops | Up to 639 ms drift | Not recommended for recording |
| Block + lockstep | – | All 5 record 445, same 36 ticks skipped, spread 6.3 ms | Recommended (ranks 6/7) |

### UI tap variants (1080p, 5 cameras, no browser, [p6_ui_path.md](prototypes/results/p6_ui_path.md))

| Variant | Payloads/s | Build median (ms) | Event loop blocked per payload (ms) | Verdict |
|---|---|---|---|---|
| HEAD relay (real ring + `create_frontend_payload`, [d_ui.md](baseline/results/d_ui.md)) | 46.0 | 9.39 (total) | whole build | Baseline |
| `cur_copy_real` (HEAD-shaped copies, P6 harness) | 51.8 (51.6-51.8 over 4 runs) | 8.28 | 8.28 | Baseline in P6 harness |
| Build from views (`view_proto`) | 53.0 | 4.84 | 4.84 | Fewer copies |
| Views + thread pool | 46.4 (46.4-47.5) | 2.20 | 0.05 | Frees the event loop |
| Views + thread pool + 2 ms poll | 60.1 (60.0-60.1) | 1.96 | 0.04 | Recommended (rank 12) |
| Forward camera JPEGs | 51.0 | 0.25 | 0.25 | Payload 2.7 MB (synthetic JPEGs); bandwidth-heavy |

**Winner and caveats.** The winning approach is a Python-only redesign: remove `copy.copy` (rank 9) first, then the seqlock ring with per-reader cursors (rank 6) and a decoupled recorder (rank 7) with block + lockstep, `setNumThreads(1)` in recorders, a crash-tolerant container, and a threaded UI build. C++ adds nothing at frame sizes. Caveats: the 60 fps results come from synthetic cameras whose timing differs from real DSHOW cameras; the recommended design was measured as a prototype, not inside SkellyCam; and the end-to-end headroom is only about 2-3 ms per frame.

## Areas of interest

- **Lockstep aligns grab calls, not exposures.** The finalizer's "Mean Inter-Camera Sync" (0.47-1.28 ms) uses grab-call stamps, while the sensor capture times of the same frame number differed by 7.0-13.3 ms median and up to 20.2 ms (more than one 16.7 ms frame period) across free-running synthetic cameras ([revision/README.md](revision/README.md), [e2ev_gap_detector.md](baseline/results/e2ev_gap_detector.md)). Real sub-frame sync needs hardware sync, not software.
- **Real DSHOW timing differs from the synthetic model.** On real cameras `grab()` returns in 0.00-0.01 ms and `retrieve()` waits about 32 ms ([p9_real_camera.md](prototypes/results/p9_real_camera.md)), so grab timestamps do not mark frame arrival. A stand-in with that timing gave the same throughput as HEAD (54.17 fps, 874 never grabbed) but a 12.9 ms median capture-time spread ([revision/README.md](revision/README.md)).
- **The obvious drop detector does not work.** A per-interval `round(dt/T) - 1` count found 16 of 878 missed frames at HEAD; an accumulated-clock count (`round((t_last - t_first)/T) + 1 - n`) found 880 of 878, and matched within -2 to +5 in every run ([e2ev_gap_detector.md](baseline/results/e2ev_gap_detector.md)).
- **HEAD's read check accepts torn frames in an adversarial test.** The copy-then-check-`frame_number` reader accepted 15 silent tears in 44,276 reads at L=2, and 39,854-41,834 when reading the slot the writer overwrites next; seqlock readers accepted 0 torn frames in all 12 rows ([p2_seqlock_read.md](prototypes/results/p2_seqlock_read.md), [prototypes/README.md](prototypes/README.md)). At the realistic ring length reading the latest frame, no tears were seen.
- **MSMF encode CPU depends 2-3x on OpenCV's thread pool**, with no change in throughput; the cause (busy-waiting) is inferred, not profiled ([recommend_result.json](study_state/recommend_result.json) `open_questions`).
- **The stop/start pause in `camera_group.py` costs at most about one frame per camera** in these runs ([revision/README.md](revision/README.md)).
- **NVENC allows 12 concurrent sessions** on this RTX 3070 / driver 610.88; session 13 fails ([p5_nvenc.md](prototypes/results/p5_nvenc.md)).
- **Websocket permessage-deflate costs 6.22 ms per 1080p payload** on the event loop, using the websockets library's own compressor on a real SkellyCam payload ([h_deflate.md](baseline/results/h_deflate.md)).
- **Threads do not scale for Python per-frame work**: x1.03 with 5 threads vs x4.97 with 5 processes; GIL-releasing decode scales either way (x4.60 / x4.90) ([p7_topology.md](prototypes/results/p7_topology.md)).
- **RAM runs at 4000 MT/s** although the part number (CMK64GX5M2B6400C32) suggests a 6400 MT/s kit ([environment_system.json](cpp/results/environment_system.json)); whether faster RAM raises copy bandwidth is untested ([research.json](study_state/research.json)).

## Limitations and caveats

- **One machine.** Intel i7-14700K (20 cores / 28 threads, 8 P-cores + 12 E-cores, placement not pinned), 64 GB DDR5 at 4000 MT/s, NVIDIA RTX 3070, WD_BLACK SN850X 4 TB (94.4% full), Windows 11 Home 10.0.26300, Balanced power plan ([environment_system.json](cpp/results/environment_system.json)); Python 3.12.13, numpy 2.2.6, opencv-contrib-python 4.12.0.88 ([environment_python.json](baseline/results/environment_python.json)).
- **Synthetic cameras.** Every 5x60 number uses FakeCapture-style synthetic cameras with q90 JPEGs of about 540 KB at 1080p, far larger than the 57-116 KB the real cameras produced at 1080p30 ([g_decode_ref.md](baseline/results/g_decode_ref.md), [p9b_pyav_dshow_probe.md](prototypes/results/p9b_pyav_dshow_probe.md)). None of the 4 attached UVC cameras delivered more than 30.1 fps.
- **Small samples.** End-to-end runs are 30 s, with 1-2 runs per configuration (1 run for several variants).
- **Idle-machine runs, with exceptions.** Baseline 2026-10-28 00:59-01:27, prototypes 01:44-03:20, C++ about 03:44-04:44, reproducibility 05:13-06:02, revision 06:10-07:06, all meeting the study's idle rule. Exceptions: `p10_msmf_threads` is provisional (Defender scan); a stuck smoke-test process ran through the `e2ev_*` revision runs (still idle by the rule); the 2026-10-25 loaded results are kept for comparison only ([PROVISIONAL.md](PROVISIONAL.md), [revision/README.md](revision/README.md)).
- **Reproducibility.** 130 of 136 throughput rows were within ±15% and all 18 pass/fail rows held. The 6 outliers: five 720p UI rows in P6 (−24% to −26%; 720p `view_proto` is bimodal, 43.5-60.0/s) and one C++ write row (−18.8%) ([comparison.md](reproducibility/comparison.md)).
- **Disk.** The e2e recordings sat in the OS page cache (no fsync), so they show the writer kept up, not the disk; P12 covers raw disk writes only ([recommend_result.json](study_state/recommend_result.json)).
- **Not tested:** fault behaviour (the benchmark UI stand-in catches every exception), event-wake latency for the lockstep gate, browser-side UI throughput, non-x86 seqlock ordering, NVENC failure handling, and FreeMoCap reading MKV / fragmented MP4.
- **Known errata in earlier write-ups.**
  - The Claude Doc report was audited on 2026-10-28 and six content corrections plus a byline-date fix were made, among them the rank 7 prototype label and the rank 13 gate-wait range ([RESUME.md](study_state/RESUME.md)).
  - RESUME.md still says `recommend_result.json` rank 13 carries the wrong "0.03-0.18 ms" gate-wait range. That note is stale: the current JSON gives the corrected 0.03-6.4 ms per-camera medians, which match the `lockstep_gate_wait` values in `p8v_e2e_1080p_imdecode_msmf_lockstep_meta*.json`.
  - The [Claude Docs summary](https://claude.ai/artifact/H1dJaFNr9cbuQD3XNU78fq) says the 4000 MT/s RAM speed "lowers the memory-copy numbers". The local [research.json](study_state/research.json) says this is untested, so treat it as unverified.
  - The first `dshowlike` run had a tick-log index bug. It is superseded by `_v2` and kept in `baseline/results/superseded_revision/`.
- **Recorded paths.** Raw logs and results record the old location `benchmarks/frame_pipeline/`, which is now `research/frame_ring_buffer/` ([RESUME.md](study_state/RESUME.md)).

## Proposed further investigation

1. **Real 5x60 fps cameras.** This would decide whether a real camera behaves like the 53.6 fps decode stand-in or the 59.99 fps memcpy stand-in. It needs to measure:
   - capture-thread CPU per frame at 60 fps;
   - USB host-controller bandwidth with 5 cameras;
   - whether DSHOW decodes MJPEG on the calling thread;
   - whether the accumulated-clock drop counter (rank 5) is accurate on real hardware.

   Every headline fps number depends on this.
2. **Ship ranks 9, 3, 4, 5 and 2 and re-measure the real stack.** These are small changes with measured or code-cited effects. The re-run confirms how much of the prototype gain SkellyCam gets. For rank 2, first check that FreeMoCap's posthoc reader accepts MKV and fragmented MP4, including a truncated last fragment.
3. **Build the rank-1 fault-injection test.** The P1 risks (a UI, websocket or FreeMoCap error ending a recording) come from code review only. This test would show whether containment works.
4. **Record for 10+ minutes through the real encoders**, with Defender real-time scanning on and off and a nearly full disk. This sizes the ring and the overflow tier, and decides whether spill-to-disk is needed. P12 measured raw writes only.
5. **Implement and measure the event-driven lockstep wake (rank 13).** It targets the 2.5-3.2 ms per-frame gate idle that remains after rank 9, the largest remaining gap to 60 fps.
6. **Repeat key runs pinned to P-cores.** This would show how much of the run-to-run variance comes from P/E-core placement.
7. **Only if H.264 output is required:** build NVENC session-exhaustion and driver-reset handling (rank 14).
8. **Lower priority:**
   - a browser-attached UI test;
   - seqlock ordering on non-x86 CPUs;
   - C++ in-place decode against libjpeg-turbo 3.x and a native capture callback (the only open C++ questions);
   - RAM at its rated speed;
   - whether the target cameras support a hardware sync input.

## Where to look

| Path | What it holds |
|---|---|
| [study_state/RESUME.md](study_state/RESUME.md) | Stage status, the original task, pinned commits, audit corrections, open items |
| [PROVISIONAL.md](PROVISIONAL.md) | Which results are idle and which are provisional; the idle rule |
| [study_state/recommend_result.json](study_state/recommend_result.json) | Final 15 ranked recommendations, C++ verdict, not-recommended ideas, open questions (post-revision) |
| [study_state/verified_maps.json](study_state/verified_maps.json), [verified_digest.json](study_state/verified_digest.json) | Code map of the write, read, control, UI and FreeMoCap paths; 172 claims verified (123 confirmed, 43 corrected, 1 refuted, 5 unverifiable) |
| [study_state/research.json](study_state/research.json) | Best-practice and Python-vs-C++ research |
| [study_state/revision_result.json](study_state/revision_result.json), [revision/README.md](revision/README.md) | The 34 critic issues and the benchmarks added to answer them |
| `study_state/critic_*_result.json` | The three critiques (evidence, priorities, reproducibility) |
| [baseline/README.md](baseline/README.md), `baseline/results/` | Real SkellyCam benchmarks: write (a), read (b), record (c), UI (d), end-to-end (e, e2ev), copies (f), decode reference (g), deflate (h). `results_provisional_20261025/` holds the loaded first run |
| [prototypes/README.md](prototypes/README.md), `prototypes/results/` | P1-P12: write variants, seqlock reads, lossless recording, passthrough, NVENC, UI, threads vs processes, end-to-end prototype, real cameras, OpenCV threads, crash containers, disk |
| [cpp/README.md](cpp/README.md), [cpp/results/cpp_comparison.md](cpp/results/cpp_comparison.md) | C++ vs Python ring, memcpy, micro-ops and codec comparison; sources in `cpp/src/` |
| [reproducibility/README.md](reproducibility/README.md), [comparison.md](reproducibility/comparison.md) | Re-run of the headline benchmarks and the ±15% comparison |
| `study_state/*_workflow.js`, `workflows/` | Workflow scripts that drove the study |
| [Claude Doc report](https://claude.ai/artifact/Cz1otkZxAjLTHfP1WeE9it) · [summary](https://claude.ai/artifact/H1dJaFNr9cbuQD3XNU78fq) | Full report with code references and charts; one-page summary |
