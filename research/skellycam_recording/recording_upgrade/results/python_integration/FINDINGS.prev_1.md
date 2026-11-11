# python_integration: FINDINGS (G1-G9 in skellycam's Python implementation)

2026-11-09, Gerald (Windows 11, i7-14700K, RTX 3070, driver 610.88). This covers functional results only. Timing questions are listed in section 5.

**Labels**
- **measured**: a result file.
- **source**: a primary source, accessed 2026-11-09.
- **code**: file:line.
- **inferred**: reasoning, kept short and marked.
- "PyAV 18 - background" marks results made with the skellycam venv (PyAV 18.0.0 / FFmpeg 8.1.2). They are context only and are not results for the implementation under test.

**Paths**
- `R/` = `research/skellycam_recording/recording_upgrade/results/python_integration/`
- `S/` = `research/skellycam_recording/recording_upgrade/scripts/python_integration/`
- `fmc:` = `C:/Users/Dom/GitHub/freemocap/freemocap` (development branch)
- `sfn26:` = `git show upstream/sfn26:<path>` (765bf82d)
- Media is in `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/python_integration/`.

**PyAV 19.0.2 re-checks made for this report** (functional, under 1 min CPU, no timing):
- `R/pyav19_recheck_roundtrip_crash.json` (log `R/pyav19_recheck_run.log`, script `S/pyav19_recheck.py`): the round-trip and crash tests re-run with PyAV 19.0.2 + opencv-python 4.12.0.88. To stay under 1 min CPU, the full-frame decode loops were cut. PyAV decodes only the last packet, and cv2 counts frames with `grab()`.
- `R/compat_recheck_pyav19.json` (script `S/compat_recheck_pyav19.py`): MJPEG, FFV1 and SVT-AV1 compat clips re-encoded with PyAV 19.0.2, then the FreeMoCap-style cv2 4.12 CAP_FFMPEG probe.
- `R/decode_strict_check_pyav19.json` (script `S/decode_strict_check_pyav19.py`): decoder acceptance and agreement on the corpus JPEGs.
- `R/recorder_thread_check_pyav19.json` (script `S/recorder_thread_check_pyav19.py`): RecorderThread under PyAV 19.0.2.
- `R/av1_vfr_ffprobe_pyav19.txt`: ffprobe 9.0.2 inspection of the VFR clips (inspection only).

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
- **code:** capture decodes straight into the shared array: `cap.retrieve(image=frame_rec_array.image[0])` (`skellycam/core/camera/opencv/opencv_helpers/opencv_get_frame.py:71`).
- **code:** the recorder encodes that array synchronously inside the camera loop: `self.video_writer.write(image)` (`skellycam/core/recorders/videos/video_recorder.py:101`). It is called from `skellycam/core/camera/opencv/opencv_camera_loop.py:99-105`.
- **measured (prior study):** OpenCV 4.12 never returns the JPEG bytes. Source: `research/usb_cameras/docs/mjpeg_passthrough_summary.md`, "Results matrix".
- **code:** sfn26's Rust backend already passes JPEG bytes to a recording thread, but it re-encodes them with libx264, so it does not avoid transcoding:
  - unbounded channel: `sfn26:skellycam-rust/src/camera_group/recording_thread.rs:1-6`;
  - libx264 re-encode: `sfn26:skellycam-rust/src/.../recorder.rs:137-155`.
  - These citations come from NOTES.md §1 and were not re-checked in this pass.

### F2. Byte-exact round trip on PyAV 19.0.2 (G1, G9)
- **measured** (`R/pyav19_recheck_roundtrip_crash.json` → `roundtrip.rows`): 7 MJPEG corpus sets (1,862 real camera frames) × 5 variants (MKV real/index PTS, fMP4 real, AVI real/index). All 35 files passed all four checks:
  - `bytes_exact`
  - `sidecar_ts_exact` (ns timestamps returned exactly)
  - `sidecar_fn_exact`
  - `container_pts_eq_sidecar`
- **measured** (same file): the container time base depends on the container.

| Container | Time base | Note |
|---|---|---|
| MKV | 1/1000 | forced by the muxer |
| fMP4 | 1/1000000 | kept as requested |
| AVI, real PTS | 1/600 | |
| AVI, index PTS | 1/fps | |

- **measured** (same file, real-PTS rows): largest |PTS − (t − t0)| on frames that were not adjusted:

| Container | Largest error | Half a tick |
|---|---|---|
| MKV | 0.0004975 s (c930e_720p_flash) | 0.0005 s |
| fMP4 | 5.0e-07 s | |
| AVI | 0.0008318 s | 1/1200 s |

- **measured:** `pts_adjusted_frames` = 1 for c930e_720p_flash in MKV real and in AVI real (two arrivals closer together than one tick), and 0 everywhere else.
- **measured:** container overhead per frame for c930e 720p: MKV 45.2 B, fMP4 131.9 B, AVI real-PTS 485.3 B, AVI index-PTS 30.9 B. For 1080p MKV it is 69.6 B.
- **source:** FFmpeg n9.0.2 `libavformat/matroskaenc.c`, https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/libavformat/matroskaenc.c:
  - :3602-3603: "`// ms precision is the de-facto standard timescale for mkv files`" / "`avpriv_set_pts_info(st, 64, 1, 1000);`"
  - :2613: "`put_ebml_uint(pb, MATROSKA_ID_TIMECODESCALE, 1000000);`"
- **measured, PyAV 18 - background** (`R/roundtrip.md`): the same 35 rows, all exact. A deliberate frame-number gap was flagged at index [10] as expected. This gap test was not repeated on PyAV 19.

### F3. FreeMoCap reads correctly only from CFR files (G9 / compatibility)
- **code:** FreeMoCap opens files with `cv2.VideoCapture(str(video_path))` and reads `frame_count = int(video_reader.get(cv2.CAP_PROP_FRAME_COUNT))` (`fmc:freemocap/core/pipeline/posthoc/video_group_helper.py:151,159`). It raises `ValueError` when the counts differ between cameras (`:381-392`).
- **code:** sfn26 skellycam's `VideoFileMetadata.from_path` raises "Invalid reported video frame count" when the count is not finite, below 1 or not an integer (`sfn26:skellycam/core/recorders/videos/video_file_metadata.py:30-36`).
- **source:** OpenCV 4.12.0 `modules/videoio/src/cap_ffmpeg_impl.hpp`, https://raw.githubusercontent.com/opencv/opencv/4.12.0/modules/videoio/src/cap_ffmpeg_impl.hpp:
  - :1982: "`int64_t nbf = ic->streams[video_stream]->nb_frames;`"
  - :1984-1986: "`if (nbf == 0)` … `nbf = (int64_t)floor(get_duration_sec() * get_fps() + 0.5);`"
  - :1960: FPS = `avg_frame_rate`.
- **measured, PyAV 19.0.2 camera-byte files** (`R/pyav19_recheck_roundtrip_crash.json`), cv2 4.12 on c930e_720p_flash (891 frames):

| File | FRAME_COUNT | FPS | `grab()` count |
|---|---|---|---|
| MKV index (CFR) | 891.0 | 30.0 | 891 |
| MKV real (VFR) | **888.0** | 30.0 | 891 |
| fMP4 real | 891.0 | 30.0999 | 891 |
| AVI index | 891.0 | 30.0 | 891 |
| AVI real | **17761.0** | **600.0** | 891 |

  On c922_720p_flash, AVI real reports 17857.0.
- **measured, PyAV 19.0.2-encoded barcode clips** (`R/compat_recheck_pyav19.json`), cv2 4.12 CAP_FFMPEG, 120 frames, 11 `POS_FRAMES` seek targets:
  - **CFR, all exact** (count 120, 120 read, order exact, every seek exact): `mjpeg_mkv`, `mjpeg_avi`, `ffv1_mkv`, `ffv1_avi`, `av1svt_mp4`.
  - **`mjpeg_mkv_vfr`:** count 122.0, 120 read, order exact, seek 119 → 117.
  - **`mjpeg_mp4frag_vfr`:** count 120.0, fps 29.5035, seeks 59 → 60, 61 → 62, 62 → 63, 77 → 78.
- **measured, PyAV 18 clips - background** (`R/cv2_read_probe_cv2_4.12_venv.json`, `R/cv2_read_probe_cv2_5.0.0.93_uv.json`, `R/cv2_compat_table.md`):
  - The same pattern holds for VP9 (WebM/MKV/MP4, GOP 30 and intra-only) and H.264 MP4. All CFR clips are exact.
  - opencv-python 5.0.0.93 gives results identical to 4.12 in every field ("Differences 4.12 -> 5.0.0.93: none").

### F4. Hard kill: MKV returns only whole frames, but its reported count is garbage until recovery (G2)
- **measured, PyAV 19.0.2** (`R/pyav19_recheck_roundtrip_crash.json` → `crash.part_a_kill`). The writer child was killed with TerminateProcess once the sidecar held at least 300 records, one kill per variant.

| Variant | Sidecar records (torn bytes) | Packets in killed file | Last packet | cv2 FRAME_COUNT, killed | `grab()` count, killed | `recover()` matched prefix | cv2 FRAME_COUNT, recovered |
|---|---|---|---|---|---|---|---|
| MKV real | 300 (0) | 297 | whole (80,637 B) | **−2.7670116110564326e+17** | 297 | 297 | 297.0 |
| MKV index | 300 (0) | 297 | whole | **−2.7670116110564326e+17** | 297 | 297 | 297.0 |
| fMP4 real | 300 (0) | 298 | **torn**: 22,583 B of 82,954 B, CRC mismatch | 298.0 | 298 | 297 | 297.0 |
| AVI index | 300 (0) | 298 | **torn**: 48,476 B of 82,954 B, CRC mismatch | **0.0** | 298 | 297 | 297.0 |

- **measured:** PyAV 19 decodes each torn last packet to 1 frame with `is_corrupt` False (`killed_last_packet_is_corrupt: [false]`). The torn frame is not flagged.
- **measured:** `find_unfinished()` listed every killed stem, and every manifest was still in state `recording`.
- **inferred:** the MKV count matches OpenCV's duration × fps formula when the duration is AV_NOPTS_VALUE at the 1/1000 time base: (−9223372036854775808 / 1000) × 30 = −2.7670116110564326e+17.
  - Either count fails FreeMoCap's checks: the sfn26 check rejects counts below 1 (F3 code), and FreeMoCap development does `int()` on it.
- **source:** n9.0.2 `matroskaenc.c:3231-3236` starts a new cluster when "`codec_type == AVMEDIA_TYPE_VIDEO && keyframe && cluster_size > 4 * 1024`".
  - **inferred:** every camera JPEG is a keyframe larger than 4 KB, so the newest frames wait in the cluster buffer. That fits the 297-of-300 result.
- **measured, PyAV 18 - background** (`R/crash.md`): MKV 300 → 297, fMP4 300 → 298 with a torn packet 297, AVI 301 → 301 with a torn packet 300. Counts move by a frame or two between runs (kill timing), but the pattern is the same.

### F5. Truncated copies: MKV prefixes are exact; fMP4 and AVI end on an unflagged partial JPEG (G2)
- **measured, PyAV 19.0.2** (`crash.part_b_truncate`, a 300-frame file cut at 50 / 90 / 99.9 % and at −1 byte):
  - **MKV:** every returned packet is exact (149 / 270 / 299 / 300). cv2 FRAME_COUNT stays at 300.0 from the header, while 149 / 270 / 299 / 300 frames are read.
  - **fMP4:** after the exact prefix, packet 149 is 47,179 of 73,984 B, packet 270 is 17,355 of 80,320 B, and packet 299 is 63,595 of 81,142 B. cv2 FRAME_COUNT equals the packet count (150 / 271 / 300), torn frame included.
  - **AVI:** the torn packets are 44,240 / 16,117 / 62,682 B. cv2 FRAME_COUNT stays at 300.0 while 150 / 271 / 300 frames are read.
  - **All three:** the last packet decodes in PyAV 19 with `is_corrupt` False. At −1 byte, all three containers return 300 exact packets.

### F6. The sidecar + manifest + `recover()` design works on PyAV 19 (G2, G9)
- **code:** sidecar format (`S/recwriter.py`):
  - 64-byte header, then a 48-byte record per frame: frame_number, timestamp_ns, pts, size, CRC32 of the JPEG, flags, write_index, CRC32 of the record;
  - flushed after every mux (`recwriter.py:144` mux, followed by the sidecar write and `flush()`);
  - manifest written atomically with `os.replace`.
- **measured:** after the kills, every sidecar held 300 valid records with 0 torn bytes, always more records than the container had packets (F4 table). `recover()` compares size, CRC and PTS by index, remuxes the matched prefix, and restores a correct count (297.0 in every variant). Source: `R/pyav19_recheck_roundtrip_crash.json`.
- **code:** the first PTS is always 0, because `t0` is the first timestamp (`recwriter.py:111-115,125`).

### F7. The threaded recorder works on PyAV 19 (writes leave the lockstep loop)
- **measured** (`R/recorder_thread_check_pyav19.json`), "block" policy: 5 RecorderThreads (MKV real ×2, MKV index, fMP4 real, AVI index), 120 frames each, submitted at once from 5 producer threads. Result: 0 dropped, `thread_error` None, 120 packets = 120 sidecar records, CRC and size match, packets byte-equal to the source frames, manifest `closed`.
- **measured** (same file), "drop" policy with `maxsize=2` and an unpaced burst of 120: 118 dropped, 2 written. The file stays consistent: packets = submitted − dropped, and the sidecar matches the container.
  - **inferred:** an unpaced burst larger than the queue is dropped almost entirely. Queue size and policy need the paced bench (section 5).
- **source:** in the installed PyAV 19.0.2 wheel, `av/container/output.py` releases the GIL (`with cython.nogil:`) around:
  - `av_interleaved_write_frame` (:784-785);
  - `avformat_write_header` (:656-657);
  - `av_write_trailer` (:84-85);
  - `avio_closep` (:95-96).
- **measured, PyAV 18 - background** (`R/bench/recwriter_smoke.json`, `--quick`): 5 cameras paced at 30 and 60 fps, `dropped` 0 per camera, `all_bytes_exact` True. Its timing fields are not used.

### F8. PyAV 18.0.0 → 19.0.2: nothing changes for this recorder except the type of rational attributes
- **measured** (`R/pyav_version_probe_pyav_19.0.2_uv.json` vs `..._18.0.0_venv.json`):
  - The bundled FFmpeg goes from 8.1.2 to 9.0.2 (libavcodec 62.28.102 → 63.1.102).
  - Encoder/decoder availability is identical for all 45 names probed. Only library versions and the type names differ.
  - Absent from both wheels: libaom-av1, librav1e, libopenh264, libjxl, libopenjpeg.
- **measured:** in PyAV 19, `time_base` is of type `AVRational` (in PyAV 18 it is `Fraction`), and `recwriter.py` runs unchanged (F2, F4, F7).
- **source:** PyAV CHANGELOG v19.0.0, https://raw.githubusercontent.com/PyAV-Org/PyAV/v19.0.2/CHANGELOG.rst:
  - "Rational attributes (``time_base``, ``average_rate``, …) now return :class:`av.AVRational` rather than ``fractions.Fraction``, and are never ``None``: an unset value is the falsy ``AVRational(0, 1)``."
  - "``avio_open()``, ``avformat_write_header()``, ``av_write_trailer()``, and ``avio_closep()`` held the GIL" (fixed in 19.0.0).
  - "Remove the ``stream_options`` argument to :func:`av.open`."
  - "Drop support for Python 3.11."
- **code:** skellycam's only `average_rate` use is `fps = v_in.average_rate or 30` (`skellycam/utilities/transcode_to_h264.py:23`). It still works with a falsy `AVRational(0, 1)`. No `stream_options` use was found under `skellycam/` (Grep).
- **measured / cross-topic:** codec presence does not mean the codec opens.
  - `av1_nvenc` is listed as an encoder, but cannot open on the RTX 3070 (`results/gpu_encode/NOTES.md:60,102`, which reports the same failure on PyAV 18 and 19).
  - PyAV 18 - background: the compat clip `av1nvenc_mp4` failed with `avcodec_open2("av1_nvenc") -> Generic error in an external library` (raw `compat/manifest.json`).

### F9. JPEG decoders for the live UI and decode-at-source
- **measured** (`R/decode_strict_check_pyav19.json`; the first 60 frames of each flash set and all frames of the short sets):
  - simplejpeg 1.9.0's `strict` defaults to `True`.
  - With the default, it rejects **11 of 11** generic_1080p frames: `ValueError('Corrupt JPEG data: 534 extraneous bytes before marker 0xd9')`.
  - With `strict=False` it accepts all 11.
  - cv2 4.12 `imdecode` accepts all 11.
  - PyTurboJPEG 2.6.1 (libjpeg-turbo 3.2.0 DLL) accepts all 11, with a "Corrupt JPEG data" warning on each.
  - Every other set is accepted by every method.
- **measured** (same file): on frame 0 of every set, simplejpeg (both strict settings) and PyTurboJPEG give BGR identical to cv2 (max abs diff 0). PyAV 19.0.2's libavcodec mjpeg → bgr24 differs from cv2 by:

| Set | Max abs diff vs cv2 |
|---|---|
| c930e_720p_flash | 6 |
| c922_720p_flash | 24 |
| c922_1080p | 11 |
| c930e_1080p | 8 |
| c922_1600x896 | 11 |
| c922_720p60 | 12 |
| generic_1080p | 11 |

- **measured, PyAV 18 - background** (`R/bench/jpeg_decode_smoke.json`, functional fields only): simplejpeg `fastdct+fastupsample` differs from cv2 by up to 26 (c922_720p_flash).
- **measured, not PyAV** (`R/bench/nvjpeg_decode_smoke.json`): nvImageCodec 0.9.0.20 (nvJPEG) decodes all 5 sets on the RTX 3070, to shape 720×1280×3 or 1080×1920×3 on the device.
  - NOTES.md §3 says the env failed to import from a long uv-cache path ("filename or extension is too long"). That error is not in a result file: NOT VERIFIED beyond the note. The bench manifest sets a short `UV_CACHE_DIR` accordingly.

### F10. Loose end settled: why SVT-AV1 in VFR MP4 decodes 119 of 120 frames
- **measured:** this is reproduced with PyAV 19.0.2 encoding. `av1svt_mp4_vfr` gives `pyav_decoded` 119, cv2 read 119 starting at barcode 1, and every seek off by 1 (77 → 79). The CFR `av1svt_mp4` clip is exact. Source: `R/compat_recheck_pyav19.json`.
- **measured** (`R/av1_vfr_ffprobe_pyav19.txt`, both the PyAV 18 and the PyAV 19 clip):
  - The first packet has pts −560 at time base 1/16000, flags `KD_` (keyframe + discard).
  - The file has an edit list (`elst`, "media time: 48").
  - ffprobe counts 120 packets and 119 frames.
  - The MJPEG VFR MP4 and MKV clips start at pts 0, with no edit list.
- **code:** the clip generator's first VFR PTS is negative: `vfr_pts_ms(0)` = round(0) + ((0·37) % 7 − 3) = −3 ms (`S/make_compat_clips.py:54-56`).
- **inferred:** the dropped frame is a test-clip artefact: a negative first PTS through the SVT-AV1 + MP4 path, discarded by the edit list. recwriter always starts at PTS 0 (F6). This does not test real AV1 recordings.

## 3. Comparison tables

**Containers for transcode-free camera JPEG (all PyAV 19.0.2, measured in `R/pyav19_recheck_roundtrip_crash.json`)**

| | MKV | fMP4 (`frag_keyframe+empty_moov+default_base_moof`) | AVI |
|---|---|---|---|
| Byte-exact round trip, 7 sets | yes | yes | yes |
| Time base (real PTS) | 1/1000 (forced) | 1/1000000 | 1/600 |
| cv2 count with real (VFR) PTS, 891 frames | 888.0 (wrong) | 891.0 | 17761.0 at fps 600 (wrong) |
| cv2 count with index (CFR) PTS | 891.0 | not tested (index PTS mode was not run for fMP4) | 891.0 |
| Overhead per frame, 720p | 45.2 B | 131.9 B | 30.9 B (index) / 485.3 B (real) |
| After a hard kill: torn last frame returned? | no | yes, unflagged | yes, unflagged |
| After a hard kill: cv2 FRAME_COUNT | −2.77e17 | equals the packets, torn frame included | 0.0 |
| Truncated copy: count vs frames read | header count (300) > frames read | equal, torn frame included | header count (300) > frames read |
| `recover()` gives a correct count | yes | yes | yes |

**PyAV 18.0.0 vs 19.0.2 for this recorder**

| Item | 18.0.0 (background) | 19.0.2 | Evidence |
|---|---|---|---|
| FFmpeg | 8.1.2 | 9.0.2 | measured, version probes |
| Codecs in the probed list | same | same | measured |
| recwriter output | byte-exact | byte-exact, code unchanged | measured, F2 |
| `time_base` type | Fraction | AVRational, never None | measured + source |
| GIL during header/trailer/close | held | released | source, F7/F8 |
| Python | 3.11+ | 3.12+ | source, CHANGELOG |

**Decoders on the corpus (measured, `R/decode_strict_check_pyav19.json`)**

| Decoder | Accepts generic_1080p | Same BGR as cv2 |
|---|---|---|
| cv2.imdecode (4.12) | 11/11 | reference |
| simplejpeg 1.9.0, default (`strict=True`) | **0/11** | n/a |
| simplejpeg 1.9.0, `strict=False` | 11/11 | yes (0) |
| PyTurboJPEG 2.6.1 | 11/11 (with warnings) | yes (0) |
| PyAV 19.0.2 mjpeg → bgr24 | 11/11 | no (6-24) |

## 4. Implications for the plan

1. **A new capture backend is needed for G1.** It must return `(jpeg_bytes, timestamps)`, because OpenCV cannot (F1). The recorder call site moves from `video_writer.write(image)` to an enqueue of bytes (F1, F7).
2. **Write CFR (index) PTS to the file and keep the exact ns timestamps in the per-frame sidecar.**
   - FreeMoCap counts with `CAP_PROP_FRAME_COUNT` and raises when cameras differ.
   - VFR PTS give wrong counts in MKV and AVI and wrong seeks in MKV and MP4.
   - CFR files are exact in every reader tested.
   - The sidecar, not the container, carries timing (MKV keeps only 1 ms).
   - (F2, F3)
3. **MKV is the preferred container for G2.**
   - It never returns a partial JPEG after a kill or truncation, while fMP4 and AVI return an unflagged torn frame (F4, F5).
   - Its killed-file count is invalid for FreeMoCap, so **recovery is mandatory before any FreeMoCap/OpenCV read**: `find_unfinished()` + `recover()` at skellycam startup, plus a load-time check in FreeMoCap (F3, F4, F6).
   - Where recovery runs is still a plan decision (section 6).
4. **The sidecar CRC is the only torn-frame detector for fMP4/AVI.** Neither PyAV nor cv2 flags the torn frame (F4, F5). A reader that trusts `is_corrupt`, as sfn26's `sequential_video_reader` does per NOTES.md §1, would pass it.
5. **Use a writer thread per camera inside the camera process, with an explicit drop counter.**
   - It works functionally on PyAV 19, and PyAV 19 releases the GIL around mux, header, trailer and close (F7).
   - Queue size and policy must come from the paced bench, not from guesses (F7 drop result; section 5).
6. **Bump to PyAV 19.0.2 for the GIL release on open and close.** Codec support gives no reason to bump (F8). Code that tests `time_base is None` must change to `not time_base` (F8 source). The repo pin `av>=12.0.0` (`pyproject.toml:68`) would need raising (code).
7. **No format reason to bump OpenCV:** 5.0.0.93 behaves identically (F3 background).
8. **Decode at source must use a lenient decoder:** cv2, PyTurboJPEG, or simplejpeg with `strict=False`. The default simplejpeg rejects one real camera (F9). PyAV's mjpeg output is not bit-identical to cv2, so keep one decoder per pipeline (F9). Which decoder to use depends on tonight's numbers (section 5).
9. **Chromium cannot play MJPEG directly**, so G8/G9 need a proxy or a JS decode path for the UI. Source: cross-topic, measured, `results/chromium_codecs/tables.md:127-130`, `DEMUXER_ERROR_NO_SUPPORTED_STREAMS` / `DEMUXER_ERROR_COULD_NOT_OPEN` on E35 and E45. This is not decided here.

## 5. Pending tonight's bench

No timed python_integration bench has run: there is no `BENCH.md`, and `R/bench/` holds only `--quick` smoke files, whose numbers must not be used. The ids come from `results/bench_queue_from_wf_2e122ed0.json` → `python_integration.bench_manifest`.

| Timed question | bench_manifest id | Priority / estimate | Change needed before 23:00 |
|---|---|---|---|
| CPU decode cost per library on real camera JPEGs (720p ×2, 1080p ×3): cv2 full and reduced/2, simplejpeg (`strict=False`) default, fast, min_h360 and into-buffer, PyTurboJPEG full and 1/2, PyAV bgr24 and native YUV; aggregate rate with 1 vs 5 threads | `pi_jpeg_decode_cpu` | 1 / 15 min | `S/bench_jpeg_decode.py` pins `av==18.0.0` in its PEP 723 header. Switch to `av==19.0.2`. Needs the libjpeg-turbo 3.2.0 DLL; the command downloads and checksums it |
| `RecordingWriter.write()` per-call median/p99/p99.9/max for MKV / fMP4 / AVI vs a folder of JPEGs, fsync off vs every 30, at 720p and 1080p; `RecorderThread.submit()` cost, queue depth and drops at 5 × 30 and 60 fps; open / count / mid-seek time on a 10-min MKV vs fMP4 | `pi_recwriter_cost` | 1 / 12 min | The manifest command runs in the skellycam venv (PyAV 18). It must run under PyAV 19.0.2 in isolation, for example by adding a PEP 723 header (`av==19.0.2`, `numpy==2.2.6`, `opencv-python==4.12.0.88`) and using `uv run --script`. Plain `uv run` in the repo root could sync the project venv, which is forbidden (inferred). Needs about 3 GB of temporary disk |
| nvJPEG decode: single frame to GPU, to host, batch of 5 | `pi_nvjpeg_decode` | 2 / 5 min | No PyAV involved. Keep the short `UV_CACHE_DIR`. Record nvidia-smi before and after (Parsec/Sunshine) |

Also pending, not in this manifest:
- whether the writer thread keeps up when the producer holds the GIL (the F7 drop result only hints at this);
- the Defender cost of folder-of-files, measured in `results/write_throughput/BENCH.md`, which is contaminated: treat its numbers as lower bounds.

## 6. Not tested / limits / NOT VERIFIED

- **No timing** of any kind in this topic so far (section 5).
- **Lean re-checks:**
  - The PyAV 19 round trip did not fully decode every frame. cv2 frames were counted (`grab()`) only for c930e_720p_flash.
  - The crash re-check decoded only the last packet per file.
  - The full PyAV/cv2 decode-all results are PyAV 18 - background (`R/roundtrip.md`, `R/crash.md`).
- **Kill test:**
  - One kill per variant, writer paced at about 30 fps, parent kills child. Counts differ by 1-3 frames between runs (F4 vs the PyAV 18 background).
  - Not a power-loss test: no fsync.
  - Killing the whole skellycam process tree was not tested here (crash_resilience topic).
- **Frame-gap flag** test and **VP9 / H.264 / intra-VP9 compat clips** exist only on PyAV 18 (background).
- **The cv2 PyAV 19 re-check used `opencv-python` 4.12.0.88**, not the venv's `opencv-contrib-python` 4.12.0.88.
- **Hardware-encoded AV1/VP9/HEVC bitstreams** were not probed with cv2. Reader behaviour on them is NOT VERIFIED.
- **Not tested:**
  - FreeMoCap's own code end to end (its venv is stale per NOTES.md §11). The tests reproduce its OpenCV calls.
  - Linux and macOS wheels: NOT VERIFIED.
  - A Python lossless 90/270 rotation (jpeg_passthrough topic).
  - Audio.
  - A recorder in a separate process (only the thread variant exists).
- **NOT VERIFIED in this pass:**
  - sfn26 Rust file:line citations (F1, from NOTES.md §1).
  - sfn26 `sequential_video_reader` raising on `is_corrupt` (NOTES.md §1).
  - The nvImageCodec long-path import error (F9).
- **Not re-checked against n9.0.2:** FFmpeg's `movenc.c` / `matroskadec.c`.
- **Corpus scenes are dim.** The flash sets show a monitor. JPEG sizes, and so decode and write costs, may differ for bright, textured scenes (open question).
- **`recwriter.py` is a research prototype:** one stream, no audio, no multi-stream.

## 7. How to reproduce (repo root, Bash; `uv` 0.11.8)

```
P=research/skellycam_recording/recording_upgrade
# PyAV 19.0.2 functional re-checks (this report)
uv run --script $P/scripts/python_integration/pyav19_recheck.py $P/results/python_integration/pyav19_recheck_roundtrip_crash.json
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

Sources fetched for this report (into the scratchpad, not the repo; accessed 2026-11-09):
- FFmpeg n9.0.2 `libavformat/matroskaenc.c` (sha256 `087df6ac8ffaa6bbceb61c6d61aa7f0ee0f1a19cc71f73df5bd0fde6a76f3e1c`);
- OpenCV 4.12.0 `cap_ffmpeg_impl.hpp`;
- PyAV v19.0.2 `CHANGELOG.rst`.
