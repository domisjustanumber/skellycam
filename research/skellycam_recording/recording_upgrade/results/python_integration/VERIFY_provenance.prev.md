# python_integration: provenance verification of the draft FINDINGS

2026-11-09, Gerald. Adversarial check (provenance lens) of the draft FINDINGS passed in by the workflow. No timed runs were made. One functional check took under 1 min of CPU (PyAV 19.0.2 audio `rate` type, see V3).

Paths: `R/` = `results/python_integration/`, `S/` = `scripts/python_integration/`, `V/` = `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/python_integration_verify/`.

## Method

- I opened every cited result file and compared each number with the JSON (`R/pyav19_recheck_roundtrip_crash.json`, `R/compat_recheck_pyav19.json`, `R/decode_strict_check_pyav19.json`, `R/recorder_thread_check_pyav19.json`, both `R/pyav_version_probe_*.json`, `R/av1_vfr_ffprobe_pyav19.txt`, `R/crash.md`, `R/roundtrip.md`, `R/cv2_compat_table.md`, `R/bench/*.json`, `R/pyav19_recheck_run.log`).
- I downloaded the primary sources again into `V/src/` with curl (accessed 2026-11-09):
  - FFmpeg n9.0.2 `matroskaenc.c`: the sha256 `087df6ac…3e1c` matches the draft.
  - OpenCV 4.12.0 `cap_ffmpeg_impl.hpp`.
  - PyAV v19.0.2 `CHANGELOG.rst`.
- I opened the code at each cited line in skellycam at HEAD 55f851e4 (no working-tree changes under `skellycam/`), FreeMoCap `development` 5632778a, and `upstream/sfn26` 765bf82d.
- I opened `av/container/output.py` of the installed PyAV 19.0.2 wheel in the uv cache.

## Refuted (the cited evidence says something else)

| # | Draft claim | Evidence | Correction |
|---|---|---|---|
| X1 | F2: largest MKV unadjusted error is 0.0004975 s (c930e_720p_flash) | `roundtrip.rows`: c922_1080p, c930e_1080p, c922_1600x896 and generic_1080p MKV real all give 0.000498333 s | The largest is 0.000498333 s (1080p / 1600x896 sets). It is still under half a tick (0.0005 s). |
| X2 | F2: largest AVI unadjusted error is 0.0008318 s | Same file: c922_720p_flash AVI real = 0.00083287 s | The largest is 0.00083287 s (c922_720p_flash). It is still under 1/1200 s (0.00083333 s). |
| X3 | F8: availability is identical for "all 45 names probed" | Both `R/pyav_version_probe_*.json` → `codecs` hold 44 keys | 44 names. Availability is identical for all 44. |
| X4 | F10: `av1svt_mp4_vfr` has "every seek off by 1 (77 → 79)" | `R/compat_recheck_pyav19.json` → `seek_results`: 9 of 11 targets are +1, 77 → 79 is +2, and 119 → 119 is exact | "9 of 11 seeks land 1 frame late, 77 lands 2 late, and 119 is exact." |
| X5 | F1: `opencv_get_frame.py:71` (retrieve) and `video_recorder.py:101` (write) | `cap.retrieve(image=frame_rec_array.image[0])` is on line 72. `self.video_writer.write(image)` is on line 102 (NOTES.md:40 also says :102) | Cite :72 and :102. |
| X6 | F1: `sfn26:skellycam-rust/src/camera_group/recording_thread.rs:1-6` | `git show upstream/sfn26:` → that path does not exist | The file is `skellycam-rust/src/recording/recording_thread.rs:1-6` ("Receives per-camera frame data via an unbounded `mpsc::channel()`, so the dispatcher never blocks on ffmpeg pipe writes or CSV fsyncs"). The libx264 re-encode is verified: `recording/recorder.rs:42` `output_codec: "libx264".into()`, `:137-155` ffmpeg spawn with `.codec_video(&config.output_codec)`, and `camera_group/dispatcher.rs:403` `VideoRecorderConfig::default()`. Move this out of NOT VERIFIED. |
| X7 | F4 (inferred): the −2.77e17 count "fails FreeMoCap's checks … FreeMoCap development does `int()` on it" | `int()` raises nothing. The value comes from AV_NOPTS_VALUE, so it is the same for every killed MKV, and the cross-camera equality check (`fmc:…/video_group_helper.py:381-392`) **passes** when every camera is a killed MKV | inferred from code: in FreeMoCap development the count passes the equality check. The failure comes later: `frame_count > 0` at `:131` makes the reader return no frames, and the bounds check at `:211` raises on any frame index. The sfn26 rejection (`video_file_metadata.py:35-36`, `frame_count < 1`) is correct. |

## Weak (true as far as it goes, but over-stated, unlabelled or under-cited)

| # | Draft claim | Problem | Fix |
|---|---|---|---|
| W1 | F4 (inferred): the newest frames wait in the MKV cluster buffer, which "fits the 297-of-300 result" | Every camera frame is a keyframe larger than 4 KB, so each packet closes the previous cluster (`matroskaenc.c:3231-3241`). The buffer (`cluster_bc`, :3156-3168) therefore holds only the newest frame, which explains at most 1 of the 3 missing frames. Every killed file except fMP4 is exactly 23,068,672 B = 704 × 32 KiB (`killed_bytes`), which points at I/O-buffer boundaries. The demuxer logged "File ended prematurely" (`R/pyav19_recheck_run.log`). | Say that the cluster rule explains at most 1 frame, and that the cause of the other missing frames is NOT VERIFIED. Keep the measured fact: MKV returned only whole packets. |
| W2 | F3 title "reads correctly only from CFR files"; Impl. 2 "VFR PTS give wrong counts in MKV" | MKV real gives a wrong count in **1 of 7** camera sets (c930e_720p_flash, 888 vs 891, the set with a PTS-adjusted frame). The other 6 sets are exact. fMP4 real gives a correct count in 7 of 7 (only the fps is off). The barcode MKV VFR count of 122 comes from a deliberate 67 ms gap (`S/make_compat_clips.py:56`), which the draft does not mention. | Give the per-set scope. Say that AVI real is wrong in 7 of 7. Mention the deliberate gap. The CFR recommendation still holds, because VFR is not reliable. |
| W3 | F3 PyAV 18 background: "the same pattern holds for VP9 … and H.264" | No VFR VP9 or H.264 clip exists (`S/make_compat_clips.py` VARIANTS, all `"cfr"`) | "The VP9 and H.264 CFR clips are exact. No VFR VP9 or H.264 clip was made." |
| W4 | F4/F5/Impl. 4: the torn frame "is not flagged"; "neither PyAV nor cv2 flags" it | `is_corrupt` is False (measured). The run log does show FFmpeg `[mjpeg] overread 2/7/8` warnings (`R/pyav19_recheck_run.log`), but they are not tied to particular files. | Say "not flagged by `is_corrupt` or by cv2's return value". FFmpeg prints log-level warnings, but they are not exposed per frame. |
| W5 | F6: "always more [sidecar] records than the container had packets" | This holds for the 4 PyAV 19 kills only. In the PyAV 18 AVI kill the sidecar and the container both held 301 (`R/crash.md`). `mux()` runs before the sidecar write (`recwriter.py:144-149`), so the container could in principle hold one packet more than the sidecar (inferred). | Change "always more" to "≥ in these runs". Note that `recover()` must also handle a container longer than the sidecar (inferred, not tested). |
| W6 | F7: "block" policy, 0 dropped | maxsize=256 is larger than the 120 frames submitted (`S/recorder_thread_check_pyav19.py:62`), so back-pressure never engaged. The timestamps are synthetic (`:67`). In the drop case `frame_gap_flags` = 0, although the docstring expects gap flags (`:12`). So the 2 written frames were consecutive, and gap-flag-on-drop was not exercised. | Say that the block path never blocked and that the gap flag on drops is untested on PyAV 19. |
| W7 | F1: "OpenCV 4.12 never returns the JPEG bytes" | The summary matrix covers specific configurations: CAP_MSMF FORMAT=-1/CONVERT_RGB=0, and CAP_DSHOW MJPG decode or CONVERT_RGB=0 (`research/usb_cameras/docs/mjpeg_passthrough_summary.md:41-44`) | "No OpenCV 4.12 configuration tested returned them." |
| W8 | F9: "PyTurboJPEG 2.6.1 (libjpeg-turbo 3.2.0 DLL)" | The result JSON records only the DLL path. The versions come from the PEP 723 pin (`S/decode_strict_check_pyav19.py:3`) and from NOTES.md:285. I re-hashed the installer next to that DLL: sha256 `662761d8…a42`, which matches NOTES.md:285. | Cite the pin and NOTES.md:285. |
| W9 | Impl. 6: "Bump to PyAV 19.0.2 for the GIL release on open and close" | The CHANGELOG motivates this fix with network outputs: "Writing to a network URL no longer blocks every other Python thread" (CHANGELOG.rst:90). Nothing has measured a benefit for local-file recording. | Mark as inferred and list it under "pending bench". |
| W10 | F10 (inferred): a negative first PTS (−3 ms) explains the dropped frame | The first packet in ffprobe is −560/16000 s = −35 ms, not −3 ms. The MJPEG VFR clips have the same −3 ms first PTS but start at 0 with no edit list (`R/av1_vfr_ffprobe_pyav19.txt`). | The mechanism is NOT VERIFIED. Keep the measured symptom and "test-clip artefact, not real recordings". |
| W11 | F1: "called from `opencv_camera_loop.py:99-105`" | That line calls `handle_video_recording`. The `record_frame` call is at `handle_video_recording_loop.py:24` | Cite both. |
| W12 | §5: "No timed python_integration bench has run" | The orchestrator background says an earlier python_integration bench was killed. No result file from it exists. | Mention the killed attempt, which left no data. See the bench requests for PyAV 19 commands that need no script edits. |
| W13 | F8: PyAV 19 break audit for skellycam (average_rate, stream_options) | The audit leaves out `a_in_stream.rate` (`skellycam/core/recorders/video_audio_remuxer.py:93,100`), and `rate` is in the CHANGELOG's list of rational attributes. I checked it: on PyAV 19.0.2 an audio stream's `.rate` is `48000 int`, and `int(0.5*rate)` works (measured, `V/audio_rate_check.out`, script `V/audio_rate_check.py`). | Add this. No break. |
| W14 | §3 table: PyAV 18 supports "Python 3.11+" | The CHANGELOG says only that 19 drops 3.11. 18's lower bound is not sourced. | Write "3.11 supported (dropped in 19)". |
| W15 | F9: "simplejpeg (both strict settings) … identical to cv2 on frame 0 of every set" | On generic_1080p the default strict setting produced no output (rejected) | Add "except generic_1080p with strict=True (rejected)". |

## Verified (evidence says exactly what the draft says)

- **F2:** 35 rows, 1,862 frames, and all four exactness checks True. The time bases are MKV 1/1000, fMP4 1/1000000, AVI real 1/600 and AVI index 1/fps. `pts_adjusted_frames` is 1 only for c930e MKV/AVI real. The overheads are 45.2 / 131.9 / 485.3 / 30.9 B, and 69.6 B for 1080p MKV.
- **F2 / F3 sources:** `matroskaenc.c:3602-3603` and `:2613` match. `cap_ffmpeg_impl.hpp:1982`, `:1984-1986` and `:1960` match. The inferred −2.7670116110564326e+17 is consistent with `get_duration_sec()` (`:1940-1950`) falling back to the stream duration × 1/1000.
- **F3:** the camera-byte cv2 table is correct (888 / 891 / 17761@600, and 17857 for c922). The barcode CFR and VFR results are correct (122 / seek 119→117; 59→60, 61→62, 62→63, 77→78). The FreeMoCap lines `:151, :159, :381-392` and sfn26 `video_file_metadata.py:30-36` are correct.
- **F4 / F5:** every number in the kill and truncation tables matches `crash.part_a_kill` and `part_b_truncate`, including the torn sizes 22,583 / 48,476 of 82,954 B and 47,179 / 17,355 / 63,595 and 44,240 / 16,117 / 62,682 B. The PyAV 18 background matches `R/crash.md`.
- **F6:** the code citations for `recwriter.py` are correct: 64 B header, 48 B record (there is also a `reserved` field), atomic `os.replace` at :58-61, mux at :144 before the sidecar flush at :148-149, and t0 at :124-125.
- **F7:** the GIL-release lines in the installed PyAV 19.0.2 `av/container/output.py` (:84-85, :95-96, :656-657, :784-785) are correct. `R/bench/recwriter_smoke.json` (PyAV 18): dropped 0 and `all_bytes_exact` True at 30 and 60 fps.
- **F8:** FFmpeg 8.1.2 → 9.0.2, libavcodec 62.28.102 → 63.1.102. The listed absences are correct (av1_vaapi, av1_videotoolbox and vp9_vaapi are also absent, which is expected on Windows). The `time_base` type changes from Fraction to AVRational. The CHANGELOG v19.0.0 quotes match. `transcode_to_h264.py:23` and `pyproject.toml:68` are correct. The av1_nvenc failure matches `results/gpu_encode/NOTES.md:60,102` and the raw `compat/manifest.json`.
- **F9:** all decoder numbers match `R/decode_strict_check_pyav19.json`, and the simplejpeg fast max of 26 matches `R/bench/jpeg_decode_smoke.json`. nvImageCodec 0.9.0.20 decoded 5 sets with the right shapes, and the driver is 610.88 (nvidia-smi in `R/bench/nvjpeg_decode_smoke.json`).
- **sfn26 `sequential_video_reader` raising on `is_corrupt`:** verified at `sfn26:skellycam/core/recorders/videos/sequential_video_reader.py:47-48`. Move it out of NOT VERIFIED.
- **Impl. 9:** `results/chromium_codecs/tables.md:127-130` is correct.
- **§5:** the ids, priorities and estimates match `results/bench_queue_from_wf_2e122ed0.json`. `S/bench_jpeg_decode.py` pins `av==18.0.0`, and the `pi_recwriter_cost` command uses `.venv` (PyAV 18).
- **PyAV 18 labelling:** every PyAV 18 result in the draft is labelled "background".

## Notes

- To get a short path, the functional check used `UV_CACHE_DIR=C:/Users/Dom/AppData/Local/Temp/pi_uv` (the bench's own short cache). It only added cached wheels there. No media was written outside `V/`.
- A `FINDINGS.md` appeared in `R/` during this check. Two of its lines turned up in a grep. Apart from that I did not read it, I did not edit it, and I did not use it as evidence.
