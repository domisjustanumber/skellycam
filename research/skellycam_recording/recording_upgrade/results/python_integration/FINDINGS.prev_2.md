# python_integration: FINDINGS (G1-G9 in skellycam's Python implementation)

2026-11-09, Gerald (Windows 11, i7-14700K, RTX 3070, driver 610.88). This covers functional results only. Timing questions are in section 5. Revised after two verifier passes (section 8).

**Labels**
- **measured**: a result file.
- **source**: a primary source, accessed 2026-11-09.
- **code**: file:line.
- **inferred**: reasoning, kept short and marked.
- "PyAV 18 - background" marks results made with the skellycam venv (PyAV 18.0.0 / FFmpeg 8.1.2). They are context only and are not results for the implementation under test.

**Paths**
- `R/` = `research/skellycam_recording/recording_upgrade/results/python_integration/`
- `S/` = `research/skellycam_recording/recording_upgrade/scripts/python_integration/`
- `V/` = `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/python_integration_verify/` (verifier scratch, outside the repo)
- `fmc:` = `C:/Users/Dom/GitHub/freemocap/freemocap` (development, 5632778a)
- `sfn26:` = `git show upstream/sfn26:<path>` (765bf82d)
- skellycam code citations are at HEAD 55f851e4.
- Media is in `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/python_integration/`.

**PyAV 19.0.2 re-checks behind this report** (functional, under 1 min CPU, no timing):
- `R/pyav19_recheck_roundtrip_crash.json` (log `R/pyav19_recheck_run.log`, script `S/pyav19_recheck.py`): round-trip and crash tests with PyAV 19.0.2 + opencv-python 4.12.0.88. To stay under 1 min CPU, PyAV decodes only the last packet (re-wrapped as a bare `av.Packet`, which drops demuxer flags), and cv2 counts frames with `grab()`.
- `R/verify_method_checks_pyav19.json` (script `S/verify_method_checks_pyav19.py`, verifier pass): container-level demux + decode of the killed and truncated files with packet flags kept; killed-file sizes mod 32 KiB; VFR clips re-made as original / jitter-only / first-PTS-shifted controls.
- `R/compat_recheck_pyav19.json` (script `S/compat_recheck_pyav19.py`): MJPEG, FFV1 and SVT-AV1 compat clips re-encoded with PyAV 19.0.2, then the FreeMoCap-style cv2 4.12 CAP_FFMPEG probe.
- `R/decode_strict_check_pyav19.json` (script `S/decode_strict_check_pyav19.py`): decoder acceptance and agreement on the corpus JPEGs.
- `R/recorder_thread_check_pyav19.json` (script `S/recorder_thread_check_pyav19.py`): RecorderThread under PyAV 19.0.2.
- `R/av1_vfr_ffprobe_pyav19.txt`: ffprobe 9.0.2 inspection of the VFR clips (inspection only).
- `V/audio_rate_check.out` (script `V/audio_rate_check.py`, verifier pass): type of an audio stream's `.rate` on PyAV 19.0.2.

## 1. Questions answered

1. Where can raw camera JPEG bytes enter today's Python recorder, and what has to change? (G1, G5)
2. Does a transcode-free PyAV writer `write(jpeg_bytes, frame_number, timestamp_ns)` keep the bytes and timestamps exact in MKV, fragmented MP4 and AVI on PyAV 19.0.2? (G1, G9)
3. What does FreeMoCap (OpenCV 4.12 CAP_FFMPEG) read from those files, CFR vs VFR? (G9, compatibility)
4. What survives a hard kill or a truncation, and can a startup recovery fix the file? (G2)
5. What do the PyAV 18 → 19 and OpenCV 4.12 → 5.0 bumps change for this recorder?
6. Which Python JPEG decoders accept every corpus camera, and do they agree? (live UI / decode-at-source)
7. Does the threaded recorder (writes moved out of the lockstep loop) work on PyAV 19?

## 2. Findings

### F1. Today's path has no entry point for JPEG bytes (G1)
- **code:** capture decodes straight into the shared array: `cap.retrieve(image=frame_rec_array.image[0])` (`skellycam/core/camera/opencv/opencv_helpers/opencv_get_frame.py:72`).
- **code:** the recorder encodes that array synchronously inside the camera loop: `self.video_writer.write(image)` (`skellycam/core/recorders/videos/video_recorder.py:102`).
  - The camera loop calls `handle_video_recording(...)` (`skellycam/core/camera/opencv/opencv_camera_loop.py:99-105`), which calls `video_recorder.record_frame(frame=frame_rec_array)` (`skellycam/core/camera/opencv/opencv_helpers/handle_video_recording_loop.py:24`).
- **measured (prior study):** no OpenCV 4.12 configuration tested returned the JPEG bytes (CAP_MSMF FORMAT=-1/CONVERT_RGB=0 and decode; CAP_DSHOW MJPG decode and CONVERT_RGB=0). Source: `research/usb_cameras/docs/mjpeg_passthrough_summary.md:41-46`.
- **code:** sfn26's Rust backend already passes JPEG bytes to a recording thread, but re-encodes them with libx264, so it does not avoid transcoding:
  - "Receives per-camera frame data via an unbounded `mpsc::channel()`, so the dispatcher never blocks on ffmpeg pipe writes or CSV fsyncs" (`sfn26:skellycam-rust/src/recording/recording_thread.rs:1-6`);
  - default `output_codec: "libx264".into()` (`sfn26:skellycam-rust/src/recording/recorder.rs:42`), passed to the ffmpeg spawn with `.codec_video(&config.output_codec)` (`:137-155`);
  - the dispatcher uses `config: VideoRecorderConfig::default()` (`sfn26:skellycam-rust/src/camera_group/dispatcher.rs:403`).

### F2. Byte-exact round trip on PyAV 19.0.2 (G1, G9)
- **measured** (`R/pyav19_recheck_roundtrip_crash.json` → `roundtrip.rows`): 7 MJPEG corpus sets (1,862 real camera JPEGs) × 5 variants (MKV real/index PTS, fMP4 real, AVI real/index). All 35 files passed all four checks: `bytes_exact`, `sidecar_ts_exact`, `sidecar_fn_exact`, `container_pts_eq_sidecar`.
  - Timestamps are real camera arrival times on 2 sets (c930e_720p_flash 891 + c922_720p_flash 893 = 1,784 frames) and synthetic ("30/60 fps lattice +-2 ms deterministic jitter") on the 5 short sets (10-19 frames).
  - `sidecar_ts_exact` and `sidecar_fn_exact` are close to tautological: the writer stores the input integers. The informative checks are `bytes_exact` and `container_pts_eq_sidecar`.
- **measured** (same file): the container time base depends on the container.

| Container | Time base | Note |
|---|---|---|
| MKV | 1/1000 | forced by the muxer |
| fMP4 | 1/1000000 | kept as requested |
| AVI, real PTS | 1/600 | |
| AVI, index PTS | 1/fps | |

- **measured** (same file, real-PTS rows): largest |PTS − (t − t0)| on frames that were not adjusted, over all 7 sets:

| Container | Largest error | Set(s) | Half a tick |
|---|---|---|---|
| MKV | 0.000498333 s | c922_1080p, c930e_1080p, c922_1600x896, generic_1080p (synthetic ts) | 0.0005 s |
| fMP4 | 5.0e-07 s | 720p flash sets | |
| AVI | 0.00083287 s | c922_720p_flash | 1/1200 s (0.00083333 s) |

- **measured:** `pts_adjusted_frames` = 1 for c930e_720p_flash in MKV real and AVI real (two arrivals closer together than one tick), 0 everywhere else.
- **measured:** container overhead per frame on the 891-frame c930e 720p set: MKV 45.2 B, fMP4 131.9 B, AVI real-PTS 485.3 B, AVI index-PTS 30.9 B. On the 10-19-frame sets the fixed header dominates (for example MKV 1080p 69.6 B, AVI index 323.6-593.1 B), so those figures are not per-frame costs.
- **source:** FFmpeg n9.0.2 `libavformat/matroskaenc.c`, https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/libavformat/matroskaenc.c:
  - :3602-3603: "`// ms precision is the de-facto standard timescale for mkv files`" / "`avpriv_set_pts_info(st, 64, 1, 1000);`"
  - :2613: "`put_ebml_uint(pb, MATROSKA_ID_TIMECODESCALE, 1000000);`"
- **measured, PyAV 18 - background** (`R/roundtrip.md`): the same 35 rows, all exact. A deliberate frame-number gap was flagged at index [10] as expected. This gap test was not repeated on PyAV 19.

### F3. FreeMoCap's count and seek go wrong when the PTS timeline has gaps or drifts from nominal; CFR (index) PTS avoid it (G9 / compatibility)
- **code:** FreeMoCap opens files with `cv2.VideoCapture(str(video_path))` and reads `frame_count = int(video_reader.get(cv2.CAP_PROP_FRAME_COUNT))` (`fmc:freemocap/core/pipeline/posthoc/video_group_helper.py:151,159`). It raises `ValueError` when the counts differ between cameras (`:381-392`).
- **code:** sfn26 skellycam's `VideoFileMetadata.from_path` raises "Invalid reported video frame count" when the count is not finite, below 1 or not an integer (`sfn26:skellycam/core/recorders/videos/video_file_metadata.py:30-36`).
- **source:** OpenCV 4.12.0 `modules/videoio/src/cap_ffmpeg_impl.hpp`, https://raw.githubusercontent.com/opencv/opencv/4.12.0/modules/videoio/src/cap_ffmpeg_impl.hpp:
  - :1982: "`int64_t nbf = ic->streams[video_stream]->nb_frames;`"
  - :1984-1986: "`if (nbf == 0)` … `nbf = (int64_t)floor(get_duration_sec() * get_fps() + 0.5);`"
  - :1960: FPS = `avg_frame_rate`.
- **measured, PyAV 19.0.2 camera-byte files** (`R/pyav19_recheck_roundtrip_crash.json`), cv2 4.12 FRAME_COUNT vs frames in, all 7 sets:

| Variant | Correct count | Wrong count |
|---|---|---|
| MKV index (CFR) | 7 of 7 | - |
| AVI index (CFR) | 7 of 7 | - |
| fMP4 real (VFR) | 7 of 7 (fps reported off nominal, e.g. 30.0999) | - |
| MKV real (VFR) | 6 of 7 (c922_720p_flash 893 = 893) | 1 of 7: c930e_720p_flash **888.0** vs 891 |
| AVI real (VFR, tb 1/600) | 0 of 7 | 7 of 7: fps **600.0**, e.g. c930e **17761.0**, c922 17857.0, 19-frame sets 382.0 |

  - `grab()` count was taken only on c930e_720p_flash: 891 in every variant.
  - **inferred:** the c930e MKV miscount follows its rate drift from nominal (fMP4 `cv2_fps_prop` 30.0999 vs c922 30.0055), because cv2 multiplies duration by the nominal 30 fps. The error would grow with recording length and dropped frames.
- **measured, PyAV 19.0.2-encoded barcode clips** (`R/compat_recheck_pyav19.json`), cv2 4.12 CAP_FFMPEG, 120 frames, 11 `POS_FRAMES` seek targets:
  - **CFR, all exact** (count 120, 120 read, order exact, every seek exact): `mjpeg_mkv`, `mjpeg_avi`, `ffv1_mkv`, `ffv1_avi`, `av1svt_mp4`.
  - **`mjpeg_mkv_vfr`:** count 122.0, 120 read, order exact, seek 119 → 117.
  - **`mjpeg_mp4frag_vfr`:** count 120.0, fps 29.5035, seeks 59 → 60, 61 → 62, 62 → 63, 77 → 78.
  - **code:** the VFR pattern is ±3 ms jitter plus a deliberate 67 ms gap after frame 60 ("a drop"): `round(i * 1000 / 30) + ((i * 37) % 7 - 3) + (67 if i > 60 else 0)` (`S/make_compat_clips.py:54-56`).
  - **measured** (`R/verify_method_checks_pyav19.json` → `vfr`): with jitter only (no gap), `mjpeg_mkv` and `mjpeg_mp4frag` both give count 120.0 and all 11 seeks exact. The VFR errors above come from the gap, not from the jitter.
- **measured, PyAV 18 clips - background** (`R/cv2_read_probe_cv2_4.12_venv.json`, `R/cv2_read_probe_cv2_5.0.0.93_uv.json`, `R/cv2_compat_table.md`):
  - The VP9 (WebM/MKV/MP4, GOP 30 and intra-only) and H.264 MP4 CFR clips are exact. No VFR VP9 or H.264 clip was made (`S/make_compat_clips.py` VARIANTS, all `"cfr"`).
  - opencv-python 5.0.0.93 gives results identical to 4.12 in every field ("Differences 4.12 -> 5.0.0.93: none").
- **Not tested:** seek accuracy on the camera-byte files (CFR or VFR). Seeks were tested only on the 120-frame barcode clips.

### F4. Hard kill: MKV returns only whole frames, but its reported count is invalid until recovery (G2)
- **measured, PyAV 19.0.2** (`R/pyav19_recheck_roundtrip_crash.json` → `crash.part_a_kill`; packet flags from `R/verify_method_checks_pyav19.json` → `killed_container_decode`). The writer child was killed with TerminateProcess once the sidecar held at least 300 records, one kill per variant.

| Variant | Sidecar records (torn bytes) | Packets in killed file | Last packet | `packet.is_corrupt` on last | cv2 FRAME_COUNT, killed | `grab()` count, killed | `recover()` matched prefix | cv2 FRAME_COUNT, recovered |
|---|---|---|---|---|---|---|---|---|
| MKV real | 300 (0) | 297 | whole (80,637 B) | False (no packet flagged) | **−2.7670116110564326e+17** | 297 | 297 | 297.0 |
| MKV index | 300 (0) | 297 | whole | not run | **−2.7670116110564326e+17** | 297 | 297 | 297.0 |
| fMP4 real | 300 (0) | 298 | **torn**: 22,583 of 82,954 B, CRC mismatch | **True** | 298.0 | 298 | 297 | 297.0 |
| AVI index | 300 (0) | 298 | **torn**: 48,476 of 82,954 B, CRC mismatch | **True** | **0.0** | 298 | 297 | 297.0 |

- **measured:** frame-level `is_corrupt` stays False on every decoded frame, including the torn ones (`frames_flagged_corrupt: []`). cv2 returns the torn frame with no failure. FFmpeg logs `[mjpeg] overread 2/8` warnings, which are not tied to particular files (`R/pyav19_recheck_run.log:59-60`).
- **measured:** `find_unfinished()` listed every killed stem, and every manifest was still in state `recording`.
- **measured** (`R/verify_method_checks_pyav19.json`, `bytes_mod_32KiB`): the killed MKV and AVI files are both exactly 23,068,672 B = 704 × 32 KiB; fMP4 is that + 28 B. Each killed MKV/AVI file holds about 43 KB beyond the recovered 297-frame file (MKV 43,044 B, AVI 43,724 B; killed minus recovered bytes in `R/pyav19_recheck_roundtrip_crash.json`).
- **measured:** the MKV demuxer logs "File ended prematurely" (`R/pyav19_recheck_run.log:57-67`) and returns no partial packet.
- **source:** n9.0.2 `matroskaenc.c:3231-3241` starts a new cluster on "`codec_type == AVMEDIA_TYPE_VIDEO && keyframe && cluster_size > 4 * 1024`".
  - **inferred:** every camera JPEG is a keyframe larger than 4 KB, so each packet closes the previous cluster and the cluster buffer holds at most the newest frame. That explains at most 1 of the 3 missing MKV frames.
  - **inferred:** the identical 32 KiB-aligned sizes point at FFmpeg's I/O buffer setting the cut point, so all three containers lose about the same data; MKV hides its partial block while fMP4/AVI return it. The cause of the other missing frames is NOT VERIFIED.
- **inferred:** the MKV count matches OpenCV's duration × fps formula when the duration is AV_NOPTS_VALUE at the 1/1000 time base: (−9223372036854775808 / 1000) × 30 = −2.7670116110564326e+17.
- **inferred from code, effect on readers:**
  - sfn26 rejects it (and AVI's 0.0): `frame_count < 1` (`sfn26:skellycam/core/recorders/videos/video_file_metadata.py:35-36`).
  - FreeMoCap development: `int()` does not raise, and the value is the same for every killed MKV, so the cross-camera equality check (`video_group_helper.py:381-392`) passes when every camera is a killed MKV (it raises if killed and good files are mixed). The failure comes later: `has_frames` is `frame_count > 0` (`:131`), so the reader returns no frames, and the bounds check `0 <= frame_number < frame_count` (`:211`) raises on any frame index.
- **measured, PyAV 18 - background** (`R/crash.md`): MKV 300 → 297, fMP4 300 → 298 with a torn packet 297, AVI sidecar 301 / container 301 with a torn packet 300. Counts move by a frame or two between runs (kill timing), but the pattern is the same.

### F5. Truncated copies of a finalised file: MKV returns an exact prefix; fMP4 and AVI end on a partial JPEG flagged at packet level (G2)
- **code:** part B truncates a file that was already closed (`S/test_crash.py:143-160`), so the duration in the header is final. This is not what a crash produces (F4).
- **measured, PyAV 19.0.2** (`crash.part_b_truncate`, a 300-frame file cut at 50 / 90 / 99.9 % and at −1 byte):
  - **MKV:** every returned packet is exact (149 / 270 / 299 / 300).
  - **fMP4:** after the exact prefix, packet 149 is 47,179 of 73,984 B, packet 270 is 17,355 of 80,320 B, packet 299 is 63,595 of 81,142 B.
  - **AVI:** the torn packets are 44,240 / 16,117 / 62,682 B.
  - **−1 byte:** all three return 300 exact packets. The cut only removes trailer/index bytes, so it never lands inside a frame.
- **measured** (`R/verify_method_checks_pyav19.json` → `truncated_container_decode`): `packet.is_corrupt` is True on the torn tail of `cut_50pct.mp4f.real.mp4` (packet 149) and `cut_90pct.avi.index.avi` (packet 270), and on no packet of `cut_50pct.mkv.real.mkv`. Frame-level `is_corrupt` stays False. Only these three cut files were demuxed at container level.
- **measured, artefact of truncating a finalised file:** cv2 FRAME_COUNT stays at 300.0 for MKV and AVI at every cut (header value), while fewer frames are read; fMP4 FRAME_COUNT equals the packet count (150 / 271 / 300), torn frame included. These counts are not a crash property.

### F6. The sidecar + manifest + `recover()` design works on PyAV 19 (G2, G9)
- **code:** sidecar format (`S/recwriter.py`):
  - 64-byte header, then a 48-byte record per frame: frame_number, timestamp_ns, pts, size, CRC32 of the JPEG, flags, write_index, a reserved field, CRC32 of the record;
  - `mux()` first (`recwriter.py:144`), then the sidecar record write and `flush()` (`:145-149`);
  - manifest written atomically with `os.replace` (`:58-61`).
- **measured:** after the 4 PyAV 19 kills, every sidecar held 300 valid records with 0 torn bytes, ≥ the container's packets in these runs (F4 table). `recover()` compares size, CRC and PTS by index, remuxes the matched prefix, and restores a correct count (297.0 in every variant). Source: `R/pyav19_recheck_roundtrip_crash.json`.
- **measured, PyAV 18 - background** (`R/crash.md`): in the AVI kill the sidecar and container both held 301.
  - **inferred, not tested:** because mux runs before the sidecar write, a container can hold one packet more than the sidecar; `recover()` must handle that case.
- **code:** the first PTS is always 0, because `t0` is set from the first timestamp (`recwriter.py:124-125`) and `_pts` subtracts it (`:111-115`).

### F7. The threaded recorder works functionally on PyAV 19 (writes leave the lockstep loop)
- **measured** (`R/recorder_thread_check_pyav19.json`), "block" policy: 5 RecorderThreads (MKV real ×2, MKV index, fMP4 real, AVI index), 120 frames each, submitted at once from 5 producer threads. Result: 0 dropped, `thread_error` None, 120 packets = 120 sidecar records, CRC and size match, packets byte-equal to the source frames, manifest `closed`.
  - **Limits:** `maxsize=256` is larger than the 120 frames submitted (`S/recorder_thread_check_pyav19.py:62`), so back-pressure never engaged; the timestamps are synthetic (`:67`).
- **measured** (same file), "drop" policy with `maxsize=2` and an unpaced burst of 120: 118 dropped, 2 written, packets = submitted − dropped, sidecar matches the container. This shows only that the drop path keeps the files consistent.
  - **Limit:** `frame_gap_flags` = 0, so the gap flag on dropped frames (expected by the script docstring, `:10-13`) was not exercised on PyAV 19.
- **source:** in the installed PyAV 19.0.2 wheel, `av/container/output.py` releases the GIL (`with cython.nogil:`) around `av_interleaved_write_frame` (:784-785), `avformat_write_header` (:656-657), `av_write_trailer` (:84-85) and `avio_closep` (:95-96).
- **code (PyAV 18 - background):** PyAV 18.0.0 already releases the GIL around `av_interleaved_write_frame` (`.venv/Lib/site-packages/av/container/output.py:627-628`, read-only). The 19 change adds header, trailer and close.
- **measured, PyAV 18 - background** (`R/bench/recwriter_smoke.json`, `--quick`): 5 cameras paced at 30 and 60 fps, `dropped` 0 per camera, `all_bytes_exact` True. Its timing fields are not used.

### F8. PyAV 18.0.0 → 19.0.2: nothing changes for this recorder except rational attribute types and the Python floor
- **measured** (`R/pyav_version_probe_pyav_19.0.2_uv.json` vs `..._18.0.0_venv.json`):
  - The bundled FFmpeg goes from 8.1.2 to 9.0.2 (libavcodec 62.28.102 → 63.1.102).
  - Encoder/decoder availability is identical for all 44 names probed (`codecs` entries equal).
  - Absent from both wheels: libaom-av1, librav1e, libopenh264, libjxl, libopenjpeg.
- **measured:** in PyAV 19, `time_base` is of type `AVRational` (PyAV 18: `Fraction`), and `recwriter.py` runs unchanged (F2, F4, F7).
- **source:** PyAV CHANGELOG v19.0.0, https://raw.githubusercontent.com/PyAV-Org/PyAV/v19.0.2/CHANGELOG.rst:
  - "Rational attributes (``time_base``, ``average_rate``, …, ``rate``, …) now return :class:`av.AVRational` rather than ``fractions.Fraction``, and are never ``None``: an unset value is the falsy ``AVRational(0, 1)``."
  - "Writing to a network URL no longer blocks every other Python thread … ``avio_open()``, ``avformat_write_header()``, ``av_write_trailer()``, and ``avio_closep()`` held the GIL" (CHANGELOG.rst:90).
  - "Remove the ``stream_options`` argument to :func:`av.open`."
  - "Drop support for Python 3.11. Binary wheels are now built for Python 3.12 and later."
- **code, break audit of skellycam:**
  - `fps = v_in.average_rate or 30` (`skellycam/utilities/transcode_to_h264.py:23`) still works with a falsy `AVRational(0, 1)`.
  - `a_in_stream.rate` (`skellycam/core/recorders/video_audio_remuxer.py:93,100`): **measured** on PyAV 19.0.2, an audio stream's `.rate` is `48000 int` and `int(0.5 * rate)` = 24000 (`V/audio_rate_check.out`). No break.
  - No `stream_options` use was found under `skellycam/` (Grep).
  - `requires-python = ">=3.11"` (`pyproject.toml:5`) and `av>=12.0.0` (`pyproject.toml:68`) would both need raising for a PyAV 19 pin.
- **measured / cross-topic:** codec presence does not mean the codec opens.
  - `av1_nvenc` is listed as an encoder but cannot open on the RTX 3070 (`results/gpu_encode/NOTES.md:60,102`, same failure on PyAV 18 and 19).
  - PyAV 18 - background: the compat clip `av1nvenc_mp4` failed with `avcodec_open2("av1_nvenc") -> Generic error in an external library` (raw `compat/manifest.json`).

### F9. JPEG decoders for the live UI and decode-at-source
- **measured** (`R/decode_strict_check_pyav19.json`; the first 60 frames of each flash set and all frames of the short sets). Versions from the PEP 723 pin (`S/decode_strict_check_pyav19.py:3`); the libjpeg-turbo 3.2.0 DLL from the installer whose sha256 `662761d8…a42` is recorded in `R/NOTES.md:285` and was re-hashed by the verifier.
  - simplejpeg 1.9.0's `strict` defaults to `True`.
  - With the default, it rejects **11 of 11** generic_1080p frames: `ValueError('Corrupt JPEG data: 534 extraneous bytes before marker 0xd9')`. With `strict=False` it accepts all 11.
  - cv2 4.12 `imdecode` accepts all 11.
  - PyTurboJPEG 2.6.1 accepts all 11, with a "Corrupt JPEG data" warning on each.
  - Every other set is accepted by every method.
- **measured** (same file), frame 0 of each set only: simplejpeg (`strict=False` on every set; default strict on every set except generic_1080p, where it rejected the frame) and PyTurboJPEG give BGR identical to cv2 (max abs diff 0). PyAV 19.0.2 libavcodec mjpeg → bgr24 differs from cv2 by:

| Set | Max abs diff vs cv2 |
|---|---|
| c930e_720p_flash | 6 |
| c922_720p_flash | 24 |
| c922_1080p | 11 |
| c930e_1080p | 8 |
| c922_1600x896 | 11 |
| c922_720p60 | 12 |
| generic_1080p | 11 |

  - **inferred, not isolated:** the PyAV difference may come from the swscale yuvj422p → bgr24 conversion rather than the mjpeg decoder.
- **measured, PyAV 18 - background** (`R/bench/jpeg_decode_smoke.json`, functional fields only): simplejpeg `fastdct+fastupsample` differs from cv2 by up to 26 (c922_720p_flash).
- **measured, not PyAV** (`R/bench/nvjpeg_decode_smoke.json`): nvImageCodec 0.9.0.20 (nvJPEG) decodes all 5 sets on the RTX 3070, to shape 720×1280×3 or 1080×1920×3 on the device.
  - NOTES.md §3 says the env failed to import from a long uv-cache path ("filename or extension is too long"). That error is not in a result file: NOT VERIFIED beyond the note. The bench manifest sets a short `UV_CACHE_DIR` accordingly.

### F10. Loose end: SVT-AV1 in VFR MP4 decodes 119 of 120 frames because the first PTS is negative (test-clip artefact)
- **measured** (`R/compat_recheck_pyav19.json`): with PyAV 19.0.2 encoding, `av1svt_mp4_vfr` gives `pyav_decoded` 119 and cv2 reads 119 starting at barcode 1. Of 11 seeks, 9 land 1 frame late, 77 lands 2 late (→ 79), and 119 is exact. The CFR `av1svt_mp4` clip is exact.
- **code:** the generator's first VFR PTS is −3 ms: `vfr_pts_ms(0)` = 0 + ((0·37) % 7 − 3) = −3 (`S/make_compat_clips.py:54-56`).
- **measured** (`R/verify_method_checks_pyav19.json` → `vfr`): the encoder emits a first packet of pts −3 at 1/1000. With the same pattern shifted so the first PTS is 0 (`av1svt_mp4_orig_nonneg`), PyAV decodes 120 and cv2 reads 120 in exact order. The jitter-only variant (still −3 ms first) also decodes 119. So the negative first PTS causes the dropped frame.
  - The shifted clip still has seeks 77 → 78 and 119 → 118, the same kind of error as the MJPEG VFR clips with the 67 ms gap (F3).
- **measured** (`R/av1_vfr_ffprobe_pyav19.txt`): in the stored MP4 the first packet has pts −560 at 1/16000 (−35 ms), flags `KD_` (keyframe + discard), there is an edit list ("media time: 48"), and ffprobe counts 120 packets and 119 frames. The MJPEG VFR MP4 and MKV clips have the same −3 ms first PTS but start at pts 0 with no edit list.
- NOT VERIFIED: the internal mechanism (why SVT-AV1 + mp4 turns −3 ms into −35 ms with a discard flag and edit list).
- **inferred:** recwriter always starts at PTS 0 (F6), so this does not affect recordings made with it. Real AV1 recordings were not tested.

## 3. Comparison tables

**Containers for transcode-free camera JPEG (all PyAV 19.0.2; measured in `R/pyav19_recheck_roundtrip_crash.json` and `R/verify_method_checks_pyav19.json`)**

| | MKV | fMP4 (`frag_keyframe+empty_moov+default_base_moof`) | AVI |
|---|---|---|---|
| Byte-exact round trip, 7 sets | yes | yes | yes |
| Time base (real PTS) | 1/1000 (forced) | 1/1000000 | 1/600 |
| cv2 count with real (VFR) PTS | wrong on 1 of 7 sets (c930e 888 vs 891) | right on 7 of 7 | wrong on 7 of 7 (fps 600) |
| cv2 count with index (CFR) PTS | right on 7 of 7 | not tested (index mode not run for fMP4) | right on 7 of 7 |
| Overhead per frame, 891-frame 720p set | 45.2 B | 131.9 B | 30.9 B (index) / 485.3 B (real) |
| After a hard kill: torn last frame returned? | no (partial block dropped silently) | yes, `packet.is_corrupt` True | yes, `packet.is_corrupt` True |
| After a hard kill: frame-level `is_corrupt` / cv2 flag | n/a | False / none | False / none |
| After a hard kill: cv2 FRAME_COUNT | −2.77e17 (invalid) | 298.0 = frames read (torn one included) | 0.0 (invalid) |
| Usable by cv2 without `recover()` | no | yes, except one torn last frame | no |
| `recover()` gives a correct count | yes | yes | yes |
| Long-file open / count / seek cost | pending (section 5) | pending (section 5) | not in bench |

**PyAV 18.0.0 vs 19.0.2 for this recorder**

| Item | 18.0.0 (background) | 19.0.2 | Evidence |
|---|---|---|---|
| FFmpeg | 8.1.2 | 9.0.2 | measured, version probes |
| Codecs in the probed list (44) | same | same | measured |
| recwriter output | byte-exact | byte-exact, code unchanged | measured, F2 |
| `time_base` type | Fraction | AVRational, never None | measured + source |
| GIL during mux | released | released | code (18 venv) / source (19 wheel), F7 |
| GIL during header / trailer / close | held | released | source, F7/F8 |
| Benefit of that for local files | - | not measured | pending (section 5) |
| Python | 3.11 supported (dropped in 19) | 3.12+ | source, CHANGELOG |

**Decoders on the corpus (measured, `R/decode_strict_check_pyav19.json`)**

| Decoder | Accepts generic_1080p | Same BGR as cv2 (frame 0) |
|---|---|---|
| cv2.imdecode (4.12) | 11/11 | reference |
| simplejpeg 1.9.0, default (`strict=True`) | **0/11** | yes on the other 6 sets; n/a on generic_1080p |
| simplejpeg 1.9.0, `strict=False` | 11/11 | yes (0) |
| PyTurboJPEG 2.6.1 | 11/11 (with warnings) | yes (0) |
| PyAV 19.0.2 mjpeg → bgr24 | 11/11 | no (6-24) |

## 4. Implications for the plan

1. **A new capture backend is needed for G1.** It must return `(jpeg_bytes, timestamps)`, because no OpenCV configuration tested can (F1). The recorder call site moves from `video_writer.write(image)` to an enqueue of bytes (F1, F7).
2. **Write CFR (index) PTS to the file and keep the exact ns timestamps in the per-frame sidecar.**
   - FreeMoCap counts with `CAP_PROP_FRAME_COUNT` and raises when cameras differ (F3 code).
   - cv2 count and seek go wrong when the PTS timeline has gaps (drops) or drifts from the nominal rate: MKV real PTS miscounted 1 of 7 camera sets, AVI real PTS 7 of 7, and the 67 ms gap broke MKV count and MKV/MP4 seeks. Jitter of ±3 ms alone was harmless (F3, measured).
   - CFR files were exact in count, order and seek in cv2 4.12 / 5.0 CAP_FFMPEG on the barcode clips, and exact in count on the camera-byte files (F3). Seek accuracy on camera-byte files is untested.
   - The sidecar, not the container, carries timing (MKV keeps only 1 ms; F2).
3. **Container choice for G2 is a trade-off, not settled.**
   - MKV never returns a partial JPEG, but its killed-file count is invalid (−2.77e17), so it needs `recover()` before any cv2 read (F4).
   - fMP4 keeps a consistent cv2 count after a kill without recovery, but returns a torn last frame that `packet.is_corrupt` and the sidecar CRC detect (F4, F5).
   - AVI gives an invalid count (0.0) and a torn frame after a kill (F4).
   - Whatever the container, run `find_unfinished()` + `recover()` at skellycam startup and add a load-time check in FreeMoCap (F3, F4, F6). Where recovery runs is a plan decision.
   - Defer the MKV vs fMP4 choice until the long-file open/count/seek cost (`pi_recwriter_cost`) is in (section 5).
4. **Torn-frame detection must work at packet level or via the sidecar.** PyAV 19 flags the torn tail packet in fMP4/AVI (`packet.is_corrupt`), but frame-level `is_corrupt` and cv2 give nothing (F4, F5). sfn26's `sequential_video_reader` raises only on frame-level `self.frame.is_corrupt` (`sfn26:skellycam/core/recorders/videos/sequential_video_reader.py:47-48`), so it would pass the torn frame (inferred from code + measured). The sidecar CRC is the stronger check: it also catches same-length corruption and a missing tail (inferred).
5. **Use a writer thread per camera inside the camera process, with an explicit drop counter.**
   - It works functionally on PyAV 19, and the GIL is released around mux (already in 18) and around header/trailer/close (new in 19) (F7).
   - Back-pressure and the gap flag on drops were not exercised; queue size and policy must come from the paced bench (F7, section 5).
6. **PyAV 19.0.2 is safe to adopt; the benefit is unmeasured.** Codec support gives no reason to bump (F8). The GIL release on header/trailer/close is motivated upstream by network outputs; any gain for local-file recording is inferred, not measured (F7, F8; section 5). A bump needs `requires-python` raised to 3.12 (`pyproject.toml:5`) and the `av>=12.0.0` pin raised (`pyproject.toml:68`). Code that tests `time_base is None` must change to `not time_base` (F8 source); skellycam's current uses survive (F8 audit).
7. **No format reason to bump OpenCV:** 5.0.0.93 behaves identically on the PyAV 18 clips (F3 background).
8. **Decode at source must use a lenient decoder:** cv2, PyTurboJPEG, or simplejpeg with `strict=False`. The default simplejpeg rejects one real camera (F9). PyAV's mjpeg → bgr24 output is not bit-identical to cv2, so keep one decoder per pipeline (F9). Which decoder to use depends on tonight's numbers (section 5).
9. **Chromium cannot play MJPEG directly**, so G8/G9 need a proxy or a JS decode path for the UI. Source: cross-topic, measured, `results/chromium_codecs/tables.md:127-130`, `DEMUXER_ERROR_NO_SUPPORTED_STREAMS` / `DEMUXER_ERROR_COULD_NOT_OPEN` on E35 and E45. This is not decided here.

## 5. Pending tonight's bench

No timed python_integration result exists. An earlier timed attempt was killed and left no result file. `R/bench/` holds only `--quick` smoke files, whose numbers must not be used. The ids come from `results/bench_queue_from_wf_2e122ed0.json` → `python_integration.bench_manifest`; the commands below replace the manifest commands so that the run uses PyAV 19.0.2 without editing scripts or touching the skellycam venv.

| Timed question | bench_manifest id | Priority / estimate | Command (repo root, Bash) |
|---|---|---|---|
| `RecordingWriter.write()` per-call median/p99/p99.9/max for MKV / fMP4 / AVI vs a folder of JPEGs, fsync off vs every 30, at 720p and 1080p; `RecorderThread.submit()` cost, queue depth and drops at 5 × 30 and 60 fps; open / count / mid-seek time on a 10-min MKV vs fMP4 (decides implication 3) | `pi_recwriter_cost` (replaced: manifest used `.venv` = PyAV 18) | 1 / 12 min, about 3 GB temp disk | `cd /c/Users/Dom/GitHub/freemocap/skellycam && UV_CACHE_DIR=C:/Users/Dom/AppData/Local/Temp/pi_uv uv run --no-project --python 3.12 --with av==19.0.2 --with numpy==2.2.6 --with opencv-python==4.12.0.88 python research/skellycam_recording/recording_upgrade/scripts/python_integration/bench_recwriter.py --tag quiet1_pyav19` → `R/bench/recwriter_quiet1_pyav19.json` |
| CPU decode cost per library on real camera JPEGs (720p ×2, 1080p ×3): cv2 full and reduced/2, simplejpeg (`strict=False`) default, fast, min_h360 and into-buffer, PyTurboJPEG full and 1/2, PyAV bgr24 and native YUV; aggregate rate with 1 vs 5 threads | `pi_jpeg_decode_cpu` (replaced: script header pins `av==18.0.0`; `--no-project --with` bypasses it) | 1 / 15 min | `cd /c/Users/Dom/GitHub/freemocap/skellycam && D=/c/Users/Dom/AppData/Local/Temp/pi_ljt && mkdir -p $D && ( [ -f $D/bin/turbojpeg.dll ] \|\| ( curl -sSfL -o $D/ljt.exe https://github.com/libjpeg-turbo/libjpeg-turbo/releases/download/3.2.0/libjpeg-turbo-3.2.0-vc-x64.exe && echo "662761d8ba8dae04aec74023ebaeceb856c2b56b9b59cfd180759d26300dda42 *$D/ljt.exe" \| sha256sum -c && "/c/Program Files/7-Zip/7z.exe" x -y -o$D $D/ljt.exe > /dev/null ) ) && UV_CACHE_DIR=C:/Users/Dom/AppData/Local/Temp/pi_uv uv run --no-project --python 3.12 --with numpy==2.2.6 --with opencv-python==4.12.0.88 --with simplejpeg==1.9.0 --with PyTurboJPEG==2.6.1 --with av==19.0.2 python research/skellycam_recording/recording_upgrade/scripts/python_integration/bench_jpeg_decode.py --tag quiet1_pyav19 --turbojpeg-dll "$D/bin/turbojpeg.dll"` → `R/bench/jpeg_decode_quiet1_pyav19.json` |
| nvJPEG decode: single frame to GPU, to host, batch of 5 | `pi_nvjpeg_decode` | 2 / 5 min | manifest command unchanged (no PyAV). Keep the short `UV_CACHE_DIR`. Record nvidia-smi before and after (Parsec/Sunshine) |

Also pending, not in this manifest:
- whether PyAV 19's GIL release on header/trailer/close gives any measurable benefit for local-file recording (no bench item measures it yet);
- whether the writer thread keeps up when the producer holds the GIL, and real back-pressure behaviour (F7 never engaged it);
- the Defender cost of folder-of-files, measured in `results/write_throughput/BENCH.md`, which is contaminated: treat its numbers as lower bounds.

## 6. Not tested / limits / NOT VERIFIED

- **No timing** of any kind in this topic so far (section 5).
- **Lean re-checks:**
  - The PyAV 19 round trip did not fully decode every frame. cv2 frames were counted (`grab()`) only for c930e_720p_flash.
  - The crash re-check decoded only the last packet per file; container-level demux with flags covered 3 killed and 3 truncated files (F4, F5).
  - The full PyAV/cv2 decode-all results are PyAV 18 - background (`R/roundtrip.md`, `R/crash.md`).
- **Kill test:**
  - One kill per variant, writer paced at about 30 fps, parent kills child. Counts differ by 1-3 frames between runs (F4 vs the PyAV 18 background).
  - Not a power-loss test: no fsync.
  - Killing the whole skellycam process tree was not tested here (crash_resilience topic).
  - A kill with a full writer queue (queued frames lost) was not tested.
  - `recover()` with a container one packet longer than the sidecar was not tested (F6).
- **Truncation test** runs on finalised files; its cv2 counts are artefacts (F5).
- **Seek accuracy on camera-byte files** (CFR and VFR) was not tested (F3).
- **Threaded recorder:** back-pressure in block mode and the gap flag on drops were not exercised on PyAV 19 (F7).
- **Frame-gap flag** test and **VP9 / H.264 / intra-VP9 compat clips** exist only on PyAV 18 (background), CFR only.
- **The cv2 PyAV 19 re-check used `opencv-python` 4.12.0.88**, not the venv's `opencv-contrib-python` 4.12.0.88.
- **Decoder agreement** was checked on frame 0 of each set only; the source of the PyAV vs cv2 pixel difference is not isolated (F9).
- **Hardware-encoded AV1/VP9/HEVC bitstreams** were not probed with cv2. Reader behaviour on them is NOT VERIFIED.
- **Not tested:**
  - FreeMoCap's own code end to end (its venv is stale per NOTES.md §11). The tests reproduce its OpenCV calls; the F4 FreeMoCap failure path is inferred from code.
  - Linux and macOS wheels: NOT VERIFIED.
  - A Python lossless 90/270 rotation (jpeg_passthrough topic).
  - Audio recording (only the `.rate` type was checked, F8).
  - A recorder in a separate process (only the thread variant exists).
- **NOT VERIFIED:**
  - The cause of the 2 MKV frames missing after a kill beyond the 1 the cluster rule can explain (F4).
  - The internal SVT-AV1 + MP4 mechanism behind the −35 ms discarded first packet (F10).
  - Which files produced the FFmpeg `[mjpeg] overread` warnings (F4).
  - The nvImageCodec long-path import error (F9).
- **Not re-checked against n9.0.2:** FFmpeg's `movenc.c` / `matroskadec.c`.
- **Corpus scenes are dim.** The flash sets show a monitor. JPEG sizes, and so decode and write costs, may differ for bright, textured scenes (open question).
- **`recwriter.py` is a research prototype:** one stream, no audio, no multi-stream.

## 7. How to reproduce (repo root, Bash; `uv` 0.11.8)

```
P=research/skellycam_recording/recording_upgrade
# PyAV 19.0.2 functional re-checks (this report)
uv run --script $P/scripts/python_integration/pyav19_recheck.py $P/results/python_integration/pyav19_recheck_roundtrip_crash.json
uv run --script $P/scripts/python_integration/verify_method_checks_pyav19.py $P/results/python_integration/verify_method_checks_pyav19.json
uv run --script $P/scripts/python_integration/compat_recheck_pyav19.py $P/results/python_integration/compat_recheck_pyav19.json
uv run --script $P/scripts/python_integration/decode_strict_check_pyav19.py $P/results/python_integration/decode_strict_check_pyav19.json <dir>/bin/turbojpeg.dll
uv run --script $P/scripts/python_integration/recorder_thread_check_pyav19.py $P/results/python_integration/recorder_thread_check_pyav19.json
uv run --script $P/scripts/python_integration/pyav_version_probe.py --tag pyav_19.0.2_uv
# ffprobe inspection behind F10 (inspection only)
ffprobe -v error -select_streams v:0 -show_entries packet=pts,dts,flags -of csv=p=0 <raw>/python_integration/compat_pyav19/av1svt_mp4_vfr.mp4 | head -3
ffprobe -v trace <raw>/python_integration/compat_pyav19/av1svt_mp4_vfr.mp4 2>&1 | grep -i "elst\|edit list"
# PyAV 18 background runs (skellycam venv, read-only use)
.venv/Scripts/python.exe $P/scripts/python_integration/test_roundtrip.py
.venv/Scripts/python.exe $P/scripts/python_integration/test_crash.py
.venv/Scripts/python.exe $P/scripts/python_integration/make_compat_clips.py
.venv/Scripts/python.exe $P/scripts/python_integration/cv2_read_probe.py --tag cv2_4.12_venv
uv run --script $P/scripts/python_integration/cv2_read_probe.py --tag cv2_5.0.0.93_uv
```

Sources fetched for this report (into the scratchpad, not the repo; accessed 2026-11-09; re-fetched by the verifier into `V/src/`):
- FFmpeg n9.0.2 `libavformat/matroskaenc.c` (sha256 `087df6ac8ffaa6bbceb61c6d61aa7f0ee0f1a19cc71f73df5bd0fde6a76f3e1c`);
- OpenCV 4.12.0 `cap_ffmpeg_impl.hpp`;
- PyAV v19.0.2 `CHANGELOG.rst`.

## 8. Verification

Two adversarial passes challenged the draft: `R/VERIFY_provenance.md` (every number traced to its result file, sources re-fetched, code lines re-opened) and `R/VERIFY_method.md` (confounders and test artefacts, with new functional checks in `R/verify_method_checks_pyav19.json`). Each refutation below was re-checked against the evidence in this revision before being applied.

**Refuted and corrected**

| Draft claim | Re-check | Change |
|---|---|---|
| Torn frame is flagged by neither PyAV nor cv2; sidecar CRC is the only detector | Confirmed refuted: the lean re-check re-wrapped bytes in `av.Packet`, dropping demuxer flags; container demux gives `packet.is_corrupt` True on fMP4/AVI torn tails (`R/verify_method_checks_pyav19.json`) | F4, F5, implication 4, table rewritten: packet-level flag exists; frame-level and cv2 flags do not |
| Largest MKV PTS error 0.0004975 s; largest AVI 0.0008318 s | Confirmed in `roundtrip.rows`: 0.000498333 s (four short sets), 0.00083287 s (c922_720p_flash) | F2 table corrected; both still within half a tick |
| 45 codec names probed | Both probes hold 44 `codecs` keys, equal | F8 and table: 44 |
| `av1svt_mp4_vfr` every seek off by 1 | `seek_results`: 9 of 11 +1, 77 → 79, 119 exact | F10 corrected |
| `opencv_get_frame.py:71`, `video_recorder.py:101`; caller `opencv_camera_loop.py:99-105` | Lines are :72 and :102; `record_frame` is at `handle_video_recording_loop.py:24` | F1 corrected, both callers cited |
| sfn26 Rust path `camera_group/recording_thread.rs` (NOT VERIFIED) | Path is `recording/recording_thread.rs:1-6`; libx264 default at `recorder.rs:42`, spawn :137-155, `dispatcher.rs:403` | F1 corrected and moved to verified |
| FreeMoCap rejects the killed-MKV count via `int()` | `int()` does not raise; equal counts pass `:381-392`; failure at `:131` / `:211` | F4 rewritten (inferred from code) |

**Weakened or relabelled**
- MKV cluster buffer "fits 297 of 300" → explains at most 1 frame; 32 KiB-aligned sizes added; rest NOT VERIFIED (F4).
- "FreeMoCap reads correctly only from CFR" → per-set scope (MKV real 1 of 7 wrong, fMP4 7 of 7 right, AVI real 7 of 7 wrong); the 67 ms gap disclosed; jitter-only control shows jitter is harmless (F3, implication 2).
- "MKV preferred for G2" → trade-off, deferred to the long-file bench (implication 3).
- Truncation counts → labelled artefacts of finalised files; −1 byte never cuts a frame (F5).
- F2 sample scope (real ts on 2 sets, synthetic on 5) and header-dominated overhead figures stated.
- F6 "always more records" → "≥ in these runs"; container-longer-than-sidecar case noted.
- F7 block policy never back-pressured; gap flag on drops not exercised; drop result reduced to "files stay consistent"; the burst inference removed.
- F7/F8: PyAV 18 already released the GIL around mux (`.venv` output.py:627-628); the 19 benefit is source-only, unmeasured, and moved to pending (implication 6). `requires-python` change added.
- F8 audit extended with `a_in_stream.rate` (int 48000 on 19.0.2, no break). Python row: "3.11 supported (dropped in 19)".
- F9: simplejpeg strict exception on generic_1080p; decoder versions cited from the pin and NOTES.md:285; swscale alternative noted.
- F10: the negative first PTS is now measured as the cause (shifted clip decodes 120); the internal mechanism stays NOT VERIFIED. The provenance pass (mechanism unverified) and the method pass (cause confirmed) are reconciled this way.
- Section 5: killed earlier bench attempt noted; script-edit advice replaced with the verifiers' no-edit PyAV 19.0.2 commands.

**Moved out of NOT VERIFIED:** sfn26 Rust recording thread and libx264 re-encode (F1); sfn26 `sequential_video_reader` raising on frame-level `is_corrupt` (`:47-48`).

**Still NOT VERIFIED:** cause of the 2 extra MKV frames lost at a kill; SVT-AV1 + MP4 internal mechanism; per-file origin of `[mjpeg] overread` warnings; nvImageCodec long-path error; Linux/macOS wheels; hardware-encoded bitstreams in cv2. All timing questions remain in section 5.
