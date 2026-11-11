# python_integration: FINDINGS (G1-G9 in skellycam's Python implementation)

2026-11-10, Gerald (Windows 11, i7-14700K, RTX 3070, driver 610.88). This revision adds the timed results from the quiet bench run `20261109T230007` (items 24, 39, 40) and replaces the old "pending tonight's bench" section. The functional findings F1-F10 were verified on 2026-11-09 (appendix). The timed findings F11-F15 are new. They were checked by two verifiers on 2026-11-10 and corrected (see **Verification** at the end).

**Labels**
- **measured**: a result file.
- **source**: a primary source, accessed 2026-11-09 unless stated.
- **code**: file:line.
- **inferred**: reasoning, kept short and marked. **arithmetic**: plain arithmetic on values from the files.
- "PyAV 18 - background" marks results made with the skellycam venv (PyAV 18.0.0 / FFmpeg 8.1.2). They are context only, not results for the implementation under test (PyAV 19.0.2 / FFmpeg 9.0.2).

**Quality targets.** Nothing in this topic encodes. The writer stores the cameras' own JPEG bytes, and the decoders read those same bytes. So no number here is at target A or B.
- **measured (HANDOFF.md:55-56):** the C930e and C922 JPEGs use fixed quantisation tables whose nearest IJG quality is q94, and libjpeg-turbo q94 (4:2:2) on those models' raw YUY2 1080p frames gives target A on average (SSIM-Y 0.9961 / 52.24 dB).
- **inferred (HANDOFF.md:57):** so the C930e and C922 JPEGs are about as faithful as a target-A re-encode. The cameras' own fidelity to the scene was not measured, and generic_1080p is not covered.
- Where a cross-topic number depends on quality, the target is named.

**Paths**
- `R/` = `research/skellycam_recording/recording_upgrade/results/python_integration/`
- `B/` = `R/bench/` (timed JSON from the quiet run)
- `S/` = `research/skellycam_recording/recording_upgrade/scripts/python_integration/`
- `RES/` = `research/skellycam_recording/recording_upgrade/results/`
- `V/` = `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/python_integration_verify/` (verifier scratch from 2026-11-09, outside the repo)
- `fmc:` = `C:/Users/Dom/GitHub/freemocap/freemocap` (development, 5632778a)
- `sfn26:` = `git show upstream/sfn26:<path>` (765bf82d)
- skellycam code citations are at HEAD 55f851e4.
- Media: `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/python_integration/`.

**Evidence files**

Functional, PyAV 19.0.2, under 1 min CPU each, no timing:
- `R/pyav19_recheck_roundtrip_crash.json` (log `R/pyav19_recheck_run.log`, script `S/pyav19_recheck.py`): round-trip and crash tests, PyAV 19.0.2 + opencv-python 4.12.0.88. To keep under 1 min CPU, PyAV decodes only the last packet, re-wrapped as a bare `av.Packet`, which drops the demuxer flags. cv2 counts frames with `grab()`.
- `R/verify_method_checks_pyav19.json` (script `S/verify_method_checks_pyav19.py`): container demux with packet flags; killed-file sizes; VFR control clips.
- `R/compat_recheck_pyav19.json` (script `S/compat_recheck_pyav19.py`): MJPEG, FFV1 and SVT-AV1 clips, then a cv2 4.12 CAP_FFMPEG probe.
- `R/decode_strict_check_pyav19.json` (script `S/decode_strict_check_pyav19.py`): which decoders accept the corpus, and whether they agree.
- `R/recorder_thread_check_pyav19.json` (script `S/recorder_thread_check_pyav19.py`): RecorderThread.
- `R/av1_vfr_ffprobe_pyav19.txt`: ffprobe 9.0.2 inspection.
- `V/audio_rate_check.out`: type of an audio stream's `.rate`.
- `R/VERIFY_method.md` W11 (2026-11-10): verifier's functional fMP4 box count (`moof_check.py`, PyAV 19.0.2, no timing).
- Step 3 gap-fill GF02 (2026-11-10, functional, no timing), `GF02/` = `RES/crash_resilience/gapfill/`: `GF02/GF02_container_matrix.md` and `.json` (merged rows), `GF02/GF02_partA_*.json`, `GF02/GF02_partB_*.json`, `GF02/GF02_recovered_rates.txt`; scripts `scripts/crash_resilience/gapfill/GF02/`. Writer: `GF02Writer`, a copy of recwriter's `RecordingWriter` with `add_mux_stream`, `flush_packets=1` and an optional empty packet, same sidecar and manifest; `recwriter.recover()` unchanged (`gf02_common.py:1-13,40-48`). PyAV 19.0.2 / FFmpeg 9.0.2 writer; readers OpenCV 4.12.0 and FreeMoCap's `VideoHelper`, read-only from the skellycam venv (`gf02_cv2_reader.py:1-2`).
- Step 3 gap-fill GF01 (2026-11-10, no tests): `RES/crash_resilience/gapfill/GF01_container_decision_table.md` (cross-topic container evidence, no choice made).

Timed, from the quiet run `20261109T230007` (2026-11-10). Each was a **single run**, started with P-core affinity (8 P-cores = 16 logical CPUs; runner log `affinity: pcores`; affinity during the run not recorded), Defender real-time ON, no item load-flagged:
- **PI-RECWRITER-AV19** (item 24, 01:01-01:03): `B/recwriter_quiet1_pyav19.json`. Python 3.12.13, av 19.0.2, opencv 4.12.0.
- **PI-JPEG-DECODE-PYAV19** (item 39, 03:06-03:16): `B/jpeg_decode_quiet1_pyav19.json`. numpy 2.2.6, opencv 4.12.0 (`cv2_num_threads` 1), simplejpeg 1.9.0, PyTurboJPEG 2.6.1 on **libjpeg-turbo 3.2.1** (version: see section 5), av 19.0.2.
- **PI-NVJPEG-DECODE** (item 40, 03:16): `B/nvjpeg_decode_quiet1_2300.json`. **nvImageCodec 0.9.0.20**; nvidia-smi before `0, 0 %, 0 %, 479 MiB`, after `0, 41 %, 0 %, 967 MiB`.
- Runner log: `RES/BENCH_RUN_2300_LOG.jsonl`; stdout/stderr in `RES/bench_runner/logs/20261109T230007/{24,39,40}_*`.
- Convenience tables: `R/BENCH.md`. All 50 decode rows, the phase A/B/C values and the nvJPEG values were checked against the JSON by the provenance verifier, and they match. (`R/BENCH.md` §2 now gives the corrected stderr counts, see F14; corrected by GF05, 2026-11-10.)

## 1. Questions answered

1. Where can raw camera JPEG bytes enter today's Python recorder, and what has to change? (G1, G5)
2. Does a transcode-free PyAV writer `write(jpeg_bytes, frame_number, timestamp_ns)` keep bytes and timestamps exact in MKV, fragmented MP4 and AVI on PyAV 19.0.2? (G1, G9)
3. What does FreeMoCap (OpenCV 4.12 CAP_FFMPEG) read from those files, CFR vs VFR? (G9, compatibility)
4. What survives a hard kill or a truncation, and can a startup recovery fix the file? (G2)
5. What do the PyAV 18 → 19 and OpenCV 4.12 → 5.0 bumps change for this recorder?
6. Which Python JPEG decoders accept every corpus camera, and do they agree? (live UI / decode at source)
7. Does the threaded recorder (writes moved out of the lockstep loop) work on PyAV 19?
8. **New:** What does `write()` cost per frame for each container vs a folder of JPEGs? Does a writer thread keep up with 5 paced cameras? How long do a 10-minute MKV and fMP4 take to open, count and seek? (G1, G2, G5)
9. **New:** What does decoding a camera JPEG cost in Python, on the CPU (cv2, simplejpeg, PyTurboJPEG, PyAV) and on the GPU (nvJPEG)? (live UI, decode at source)

## 2. Findings

### F1. Today's path has no entry point for JPEG bytes (G1)
- **code:** capture decodes straight into the shared array with `cap.retrieve(image=frame_rec_array.image[0])` (`skellycam/core/camera/opencv/opencv_helpers/opencv_get_frame.py:72`).
- **code:** the recorder encodes that array synchronously, inside the camera loop, with `self.video_writer.write(image)` (`skellycam/core/recorders/videos/video_recorder.py:102`).
  - The caller chain is `handle_video_recording(...)` (`skellycam/core/camera/opencv/opencv_camera_loop.py:99-105`) → `video_recorder.record_frame(frame=frame_rec_array)` (`skellycam/core/camera/opencv/opencv_helpers/handle_video_recording_loop.py:24`).
- **measured (prior study):** none of the OpenCV 4.12 configurations tested returned the JPEG bytes. Tested: CAP_MSMF with FORMAT=-1 / CONVERT_RGB=0 and decode; CAP_DSHOW MJPG with decode and with CONVERT_RGB=0 (`research/usb_cameras/docs/mjpeg_passthrough_summary.md:41-46`).
- **code:** sfn26's Rust backend already passes JPEG bytes to a recording thread. It then re-encodes them with libx264, so it does not avoid transcoding:
  - "Receives per-camera frame data via an unbounded `mpsc::channel()`, so the dispatcher never blocks on ffmpeg pipe writes or CSV fsyncs" (`sfn26:skellycam-rust/src/recording/recording_thread.rs:1-6`);
  - `output_codec: "libx264".into()` (`sfn26:skellycam-rust/src/recording/recorder.rs:42`), used as `.codec_video(&config.output_codec)` (`:137-155`);
  - the dispatcher uses `VideoRecorderConfig::default()` (`sfn26:skellycam-rust/src/camera_group/dispatcher.rs:403`).

### F2. Byte-exact round trip on PyAV 19.0.2 (G1, G9)
- **measured** (`R/pyav19_recheck_roundtrip_crash.json` → `roundtrip.rows`): 7 MJPEG corpus sets (1,862 real camera JPEGs) × 5 variants (MKV real/index PTS, fMP4 real, AVI real/index) = 35 files. Every file passed all four checks: `bytes_exact`, `sidecar_ts_exact`, `sidecar_fn_exact`, `container_pts_eq_sidecar`.
  - Two sets carry real camera arrival times: c930e_720p_flash (891 frames) and c922_720p_flash (893). The 5 short sets (10-19 frames) carry synthetic times: a 30/60 fps lattice with ±2 ms deterministic jitter.
  - `sidecar_ts_exact` and `sidecar_fn_exact` are close to tautological, because the writer stores the integers it is given. The informative checks are `bytes_exact` and `container_pts_eq_sidecar`.
- **measured** (same file): the time base depends on the container.

| Container | Time base | Note |
|---|---|---|
| MKV | 1/1000 | forced by the muxer |
| fMP4 | 1/1000000 | kept as requested |
| AVI, real PTS | 1/600 | |
| AVI, index PTS | 1/fps | |

- **measured** (same file, real-PTS rows, frames that were not adjusted, all 7 sets): largest |PTS − (t − t0)|.

| Container | Largest error | Set(s) | Half a tick |
|---|---|---|---|
| MKV | 0.000498333 s | c922_1080p, c930e_1080p, c922_1600x896, generic_1080p (synthetic ts) | 0.0005 s |
| fMP4 | 5.0e-07 s | 720p flash sets | |
| AVI | 0.00083287 s | c922_720p_flash | 1/1200 s (0.00083333 s) |

- **measured:** `pts_adjusted_frames` is 1 for c930e_720p_flash in MKV real and in AVI real, where two arrivals fell closer together than one tick. It is 0 everywhere else.
- **measured:** container overhead per frame on the 891-frame c930e 720p set: MKV 45.2 B, fMP4 131.9 B, AVI real-PTS 485.3 B, AVI index-PTS 30.9 B. On the 10-19-frame sets the fixed header dominates, so their figures are not per-frame costs.
- **source:** FFmpeg n9.0.2 `libavformat/matroskaenc.c` (https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/libavformat/matroskaenc.c):
  - :3602-3603: "`// ms precision is the de-facto standard timescale for mkv files`" / "`avpriv_set_pts_info(st, 64, 1, 1000);`"
  - :2613: "`put_ebml_uint(pb, MATROSKA_ID_TIMECODESCALE, 1000000);`"
- **measured, PyAV 18 - background** (`R/roundtrip.md`): the same 35 rows, all exact. A deliberate frame-number gap was flagged at index [10]. This gap test was not repeated on PyAV 19.

### F3. FreeMoCap's frame count and seek go wrong when the PTS timeline has gaps or drifts from nominal; CFR (index) PTS avoid it (G9 / compatibility)
- **code:** FreeMoCap opens files with `cv2.VideoCapture(str(video_path))` and reads `frame_count = int(video_reader.get(cv2.CAP_PROP_FRAME_COUNT))` (`fmc:freemocap/core/pipeline/posthoc/video_group_helper.py:151,159`). It raises `ValueError` when the counts differ between cameras (`:381-392`).
- **code:** sfn26 skellycam's `VideoFileMetadata.from_path` raises "Invalid reported video frame count" when the count is not finite, below 1 or not an integer (`sfn26:skellycam/core/recorders/videos/video_file_metadata.py:30-36`).
- **source:** OpenCV 4.12.0 `modules/videoio/src/cap_ffmpeg_impl.hpp` (https://raw.githubusercontent.com/opencv/opencv/4.12.0/modules/videoio/src/cap_ffmpeg_impl.hpp):
  - :1982: "`int64_t nbf = ic->streams[video_stream]->nb_frames;`"
  - :1984-1986: "`if (nbf == 0)` … `nbf = (int64_t)floor(get_duration_sec() * get_fps() + 0.5);`"
  - :1960: FPS comes from `avg_frame_rate`.
- **measured, PyAV 19.0.2 camera-byte files** (`R/pyav19_recheck_roundtrip_crash.json`): cv2 4.12 FRAME_COUNT against frames written, all 7 sets.

| Variant | Correct count | Wrong count |
|---|---|---|
| MKV index (CFR) | 7 of 7 | - |
| AVI index (CFR) | 7 of 7 | - |
| fMP4 real (VFR) | 7 of 7 (fps reported off nominal, e.g. 30.0999) | - |
| MKV real (VFR) | 6 of 7 | 1 of 7: c930e_720p_flash **888.0** vs 891 |
| AVI real (VFR, tb 1/600) | 0 of 7 | 7 of 7: fps **600.0**, e.g. c930e **17761.0**, c922 17857.0, 19-frame sets 382.0 |

  - The `grab()` count was taken only on c930e_720p_flash: 891 in every variant.
  - **inferred:** the c930e MKV miscount follows that camera's rate drift from nominal (fMP4 `cv2_fps_prop` 30.0999, against 30.0055 for the c922), because cv2 multiplies the duration by the nominal 30 fps.
- **measured, cross-topic, long file** (`RES/jpeg_passthrough/bench/open_long.json`, quiet run): with real c930e inter-frame intervals looped to 54,000 frames, cv2 counts the MKV as **53,819** (`count_exact` false). It counts all three MP4/fMP4 variants (time base 1/1e6) as 54,000. This supports the inference that the MKV error grows with recording length.
- **measured, PyAV 19.0.2-encoded barcode clips** (`R/compat_recheck_pyav19.json`): cv2 4.12 CAP_FFMPEG, 120 frames, 11 `POS_FRAMES` seek targets.
  - **CFR, all exact** (count 120, 120 read, order exact, every seek exact): `mjpeg_mkv`, `mjpeg_avi`, `ffv1_mkv`, `ffv1_avi`, `av1svt_mp4`.
  - **`mjpeg_mkv_vfr`:** count 122.0, 120 read, order exact, seek 119 → 117.
  - **`mjpeg_mp4frag_vfr`:** count 120.0, fps 29.5035, seeks 59 → 60, 61 → 62, 62 → 63, 77 → 78.
  - **code:** the VFR pattern is ±3 ms jitter plus a deliberate 67 ms gap after frame 60 (a drop): `round(i * 1000 / 30) + ((i * 37) % 7 - 3) + (67 if i > 60 else 0)` (`S/make_compat_clips.py:54-56`).
  - **measured** (`R/verify_method_checks_pyav19.json` → `vfr`): with jitter only (no gap), `mjpeg_mkv` and `mjpeg_mp4frag` both count 120.0 and land all 11 seeks exactly. So the errors come from the gap, not from the jitter.
- **measured, PyAV 18 clips - background** (`R/cv2_read_probe_cv2_4.12_venv.json`, `R/cv2_read_probe_cv2_5.0.0.93_uv.json`, `R/cv2_compat_table.md`):
  - The VP9 (WebM/MKV/MP4, GOP 30 and intra-only) and H.264 MP4 CFR clips are exact. No VFR VP9 or H.264 clip was made.
  - opencv-python 5.0.0.93 matches 4.12 in every field ("Differences 4.12 -> 5.0.0.93: none").
- **Not tested:** seek *accuracy* on the camera-byte files written by recwriter. F13 times a mid-file seek on a 10-minute camera-byte file, but the script does not check which frame came back (`S/bench_recwriter.py:182-185`). GF02 (below) now covers seek accuracy on its inputs with its own writer; the F13 timed seek itself is still unchecked.
- **measured, Step 3 gap-fill GF02** (`GF02/GF02_container_matrix.json` → `partA[]`: `cv2_frame_count`, `cv2_seek_exact_input`, `freemocap_ok`). PyAV 19.0.2 `GF02Writer` (`add_mux_stream`, `flush_packets=1`) with recwriter's real and index PTS modes; OpenCV 4.12; 11 `POS_FRAMES` seeks per file, checked by frame identity against cv2's own decode of the corpus; FreeMoCap ok = `VideoHelper` count = frames written and 4 reads match. Inputs: c930e full (891, real timestamps), gap60 (831), drop50 (874), c922 full (893), and c930e looped to 54,000 frames.
  - Index PTS give the exact count, 11/11 `POS_FRAMES` seeks and FreeMoCap ok in 18/18 files: MKV + fp, MKV + fp + empty packet, fMP4 per-frame + fp and fMP4 1 s + fp on c930e full, gap60, drop50 and c922 full, plus the 54,000-frame MKV + fp and fMP4 1 s + fp files.
  - Real PTS: MKV counts 888 for 891 / 831 / 874 and 53,820 for 54,000. MKV seeks are 1-2/11 on c930e inputs (2, 2, 1 and 1/11 on the long file).
  - Real PTS on fMP4 (both fragment modes) count exactly but seek 9/11 (c930e full), 1/11 (gap60) and 8/11 (drop50).
  - c922 real PTS is exact (count, 11/11 seeks, FreeMoCap ok) in every container.
  - This closes the "seek accuracy on camera-byte files" gap above for these inputs and the GF02 writer. recwriter itself uses an encoder stream (`S/recwriter.py:96`), not `add_mux_stream` (`gf02_common.py:82`).

### F4. Hard kill: MKV returns only whole frames, but its reported count is invalid until recovery (G2)
- **measured, PyAV 19.0.2** (`R/pyav19_recheck_roundtrip_crash.json` → `crash.part_a_kill`; packet flags from `R/verify_method_checks_pyav19.json` → `killed_container_decode`). The writer child was killed with TerminateProcess once the sidecar held at least 300 records, once per variant.

| Variant | Sidecar records (torn bytes) | Packets in killed file | Last packet | `packet.is_corrupt` on last | cv2 FRAME_COUNT, killed | `grab()` count, killed | `recover()` matched prefix | cv2 FRAME_COUNT, recovered |
|---|---|---|---|---|---|---|---|---|
| MKV real | 300 (0) | 297 | whole (80,637 B) | False | **−2.7670116110564326e+17** | 297 | 297 | 297.0 |
| MKV index | 300 (0) | 297 | whole | not run | **−2.7670116110564326e+17** | 297 | 297 | 297.0 |
| fMP4 real | 300 (0) | 298 | **torn**: 22,583 of 82,954 B, CRC mismatch | **True** | 298.0 | 298 | 297 | 297.0 |
| AVI index | 300 (0) | 298 | **torn**: 48,476 of 82,954 B, CRC mismatch | **True** | **0.0** | 298 | 297 | 297.0 |

- **measured:** frame-level `is_corrupt` stays False on every decoded frame, torn ones included. cv2 returns the torn frame without failing. FFmpeg logs `[mjpeg] overread 2/8` warnings that the log does not tie to particular files (`R/pyav19_recheck_run.log:59-60`).
- **measured:** `find_unfinished()` listed every killed stem, and every manifest was still in state `recording`.
- **measured** (`R/verify_method_checks_pyav19.json` → `bytes_mod_32KiB`): the killed MKV and AVI files are both exactly 23,068,672 B = 704 × 32 KiB = 88 × 262,144 B (arithmetic); the fMP4 is that plus 28 B. Each killed MKV/AVI file holds about 43 KB more than the recovered 297-frame file (MKV 43,044 B, AVI 43,724 B).
- **measured:** the MKV demuxer logs "File ended prematurely" (`R/pyav19_recheck_run.log:57-67`) and returns no partial packet.
- **source:** n9.0.2 `matroskaenc.c:3231-3241` starts a new cluster on "`codec_type == AVMEDIA_TYPE_VIDEO && keyframe && cluster_size > 4 * 1024`".
  - **inferred:** every camera JPEG is a keyframe larger than 4 KB, so the cluster rule explains at most 1 of the 3 missing MKV frames.
  - **code / cross-topic:** `recwriter.py` sets no `flush_packets` (muxer options at `S/recwriter.py:49-54`). crash_resilience finds the FFmpeg file buffer loses "up to 262144 B (4–5 MJPEG frames)" without `flush_packets=1` (`RES/crash_resilience/FINDINGS.md:421`, §3B).
  - **inferred:** the killed file size being an exact multiple of that 262,144 B buffer supports an unflushed buffer as the cause of the other missing frames. It was not tested with recwriter, so the cause stays NOT VERIFIED.
- **inferred:** the MKV count matches OpenCV's duration × fps formula when the duration is AV_NOPTS_VALUE at a 1/1000 time base: (−9223372036854775808 / 1000) × 30 = −2.7670116110564326e+17.
- **inferred from code, effect on readers:**
  - sfn26 rejects both the MKV value and AVI's 0.0 (`frame_count < 1`, `sfn26:skellycam/core/recorders/videos/video_file_metadata.py:35-36`).
  - FreeMoCap: `int()` does not raise, and every killed MKV gives the same value, so the cross-camera check (`video_group_helper.py:381-392`) passes when every camera is a killed MKV. The failure comes later: `has_frames` is `frame_count > 0` (`:131`), and the bounds check `0 <= frame_number < frame_count` (`:211`) raises on any frame index.
- **measured, PyAV 18 - background** (`R/crash.md`): the same pattern, with counts 1-2 frames different (kill timing).

### F5. Truncated copies of a finalised file: MKV returns an exact prefix; fMP4 and AVI end on a partial JPEG flagged at packet level (G2)
- **code:** part B truncates a file that was already closed (`S/test_crash.py:143-160`), so the header duration is final. A crash does not produce that state (F4).
- **measured, PyAV 19.0.2** (`crash.part_b_truncate`, a 300-frame file cut at 50 / 90 / 99.9 % and at −1 byte):
  - **MKV:** every returned packet is exact (149 / 270 / 299 / 300).
  - **fMP4:** after the exact prefix there is a torn packet: packet 149 is 47,179 of 73,984 B, packet 270 is 17,355 of 80,320 B, packet 299 is 63,595 of 81,142 B.
  - **AVI:** torn packets of 44,240 / 16,117 / 62,682 B.
  - **−1 byte:** all three return 300 exact packets. That cut only removes trailer/index bytes.
- **measured** (`R/verify_method_checks_pyav19.json` → `truncated_container_decode`): `packet.is_corrupt` is True on the torn tail of `cut_50pct.mp4f.real.mp4` and `cut_90pct.avi.index.avi`, and on no packet of `cut_50pct.mkv.real.mkv`. Frame-level `is_corrupt` stays False. Only these three files were demuxed at container level.
- **measured, an artefact of truncating a finalised file:** cv2 FRAME_COUNT stays at 300.0 for MKV and AVI at every cut. For fMP4 it equals the packet count, torn frame included.

### F6. The sidecar + manifest + `recover()` design works on PyAV 19 (G2, G9)
- **code:** the sidecar (`S/recwriter.py`) is a 64-byte header, then one 48-byte record per frame: frame_number, timestamp_ns, pts, size, CRC32 of the JPEG, flags, write_index, a reserved field, CRC32 of the record.
  - The write order is `mux()` first (`recwriter.py:144`), then the sidecar record write and `flush()`, plus a CSV line and `flush()` (`:145-152`).
  - The manifest is written atomically with `os.replace` (`:58-61`).
  - `fsync_every` fsyncs only the binary sidecar, not the video file (`:154-155`).
- **measured:** after the 4 PyAV 19 kills, every sidecar held 300 valid records with 0 torn bytes, at least as many as the container's packets in these runs (F4 table). `recover()` compares size, CRC and PTS by index, remuxes the matched prefix, and restores a correct count (297.0 in every variant). Source: `R/pyav19_recheck_roundtrip_crash.json`.
  - **code:** those kills used `time.perf_counter_ns()` timestamps at the writer's pacing (`S/test_crash.py:44-50`, reused by `S/pyav19_recheck.py:35`), not real camera intervals.
- **measured, Step 3 gap-fill GF02** (`GF02/GF02_container_matrix.json` → `partB[]`: `recover`, `recovered_cv2`; `GF02/GF02_recovered_rates.txt`; 48 live paced kills, real c930e intervals looped): `recover()` of a **real-PTS MKV** (MKV + fp and MKV + fp + empty packet) writes `r_frame_rate` 125/2 and `avg_frame_rate` 0/0 (the 6 killed MKV + fp real files have 30/1, 30/1). cv2 then reports fps 62.5 and a count about 2.1× the frames, e.g. 102 for 49 and 1451 for 699, in 12/12.
  - measured: index-PTS MKV and every fMP4 (both fragment modes, both PTS modes) recover with the correct cv2 count (24 + 12 = 36/36).
  - measured: every recovered file is byte-exact: `recovered_pyav.exact_prefix` = `recovered_pyav.packets` = `recover.matched_prefix` in 48/48 (the check at `gf02_report.py:103-104`).
  - code: `recover()` remuxes with `dst.add_stream_from_template(s_in)` (`S/recwriter.py:259`).
  - inferred, NOT VERIFIED: with no rate in the template, FFmpeg guesses the rate from the timestamps. Real c930e intervals on a 1 ms grid give 62.5; evenly spaced ones give 30 (index-PTS MKV recovered at 30/1, and the earlier `perf_counter` real-PTS MKV kill recovered to the correct 297.0, F4). The missing template rate alone does not explain 125/2; the timestamp pattern triggers it.
  - This qualifies "restores a correct count" above, which was measured on `perf_counter`-paced timestamps.
- **inferred, not tested:** mux runs before the sidecar write, so a container can hold one packet more than the sidecar. The PyAV 18 AVI kill had 301 / 301 (`R/crash.md`). `recover()` must handle that case.
- **code:** the first PTS is always 0. `t0` is set from the first timestamp (`recwriter.py:124-125`), and `_pts` subtracts it (`:111-115`).

### F7. The threaded recorder works on PyAV 19 (writes leave the lockstep loop)
- **measured** (`R/recorder_thread_check_pyav19.json`), "block" policy: 5 RecorderThreads (MKV real ×2, MKV index, fMP4 real, AVI index), 120 frames each, submitted at once from 5 producer threads.
  - Result: 0 dropped, `thread_error` None, 120 packets = 120 sidecar records, CRC and size match, packets byte-equal to the source, manifest `closed`.
  - Limits: `maxsize=256` is larger than the 120 frames (`S/recorder_thread_check_pyav19.py:62`), so back-pressure never engaged; the timestamps are synthetic (`:67`).
- **measured** (same file), "drop" policy with `maxsize=2` and an unpaced burst of 120: 118 dropped, 2 written, sidecar matches container. The gap flag on dropped frames was not exercised (`frame_gap_flags` = 0).
- **measured, paced:** see F12. 5 cameras (720p MKV) at 30 and 60 fps for 60 s each: 0 drops, maximum queue depth 1.
- **source:** in the installed PyAV 19.0.2 wheel, `av/container/output.py` releases the GIL (`with cython.nogil:`) around `av_interleaved_write_frame` (:784-785), `avformat_write_header` (:656-657), `av_write_trailer` (:84-85) and `avio_closep` (:95-96).
- **code (PyAV 18 - background):** PyAV 18.0.0 already releases the GIL around `av_interleaved_write_frame` (`.venv/Lib/site-packages/av/container/output.py:627-628`). The change in 19 adds header, trailer and close.

### F8. PyAV 18.0.0 → 19.0.2: nothing changes for this recorder except rational attribute types and the Python floor
- **measured** (`R/pyav_version_probe_pyav_19.0.2_uv.json` vs `R/pyav_version_probe_pyav_18.0.0_venv.json`):
  - The bundled FFmpeg goes from 8.1.2 to 9.0.2 (libavcodec 62.28.102 → 63.1.102).
  - Encoder/decoder availability is identical for all 44 names probed.
  - Absent from both wheels: libaom-av1, librav1e, libopenh264, libjxl, libopenjpeg.
- **measured:** in PyAV 19, `time_base` is an `AVRational` (PyAV 18: `Fraction`), and `recwriter.py` runs unchanged (F2, F4, F7, F11-F13).
- **source:** PyAV CHANGELOG v19.0.0 (https://raw.githubusercontent.com/PyAV-Org/PyAV/v19.0.2/CHANGELOG.rst):
  - "Rational attributes (``time_base``, ``average_rate``, …, ``rate``, …) now return :class:`av.AVRational` rather than ``fractions.Fraction``, and are never ``None``: an unset value is the falsy ``AVRational(0, 1)``."
  - "Writing to a network URL no longer blocks every other Python thread … ``avio_open()``, ``avformat_write_header()``, ``av_write_trailer()``, and ``avio_closep()`` held the GIL" (CHANGELOG.rst:90).
  - "Remove the ``stream_options`` argument to :func:`av.open`."
  - "Drop support for Python 3.11. Binary wheels are now built for Python 3.12 and later."
- **code, break audit of skellycam:**
  - `fps = v_in.average_rate or 30` (`skellycam/utilities/transcode_to_h264.py:23`) still works with a falsy `AVRational(0, 1)`.
  - `a_in_stream.rate` (`skellycam/core/recorders/video_audio_remuxer.py:93,100`): **measured** on 19.0.2, an audio `.rate` is `48000 int`, and `int(0.5 * rate)` = 24000 (`V/audio_rate_check.out`). No break.
  - No `stream_options` use under `skellycam/` (Grep).
  - `requires-python = ">=3.11"` (`pyproject.toml:5`) and `av>=12.0.0` (`pyproject.toml:68`) would both need raising for a PyAV 19 pin.
- **measured, cross-topic:** a codec being listed does not mean it opens. `av1_nvenc` is listed but fails to open on the RTX 3070 under both PyAV 18 and 19 (`RES/gpu_encode/NOTES.md:60,102`).

### F9. JPEG decoders: acceptance and agreement (live UI, decode at source)
- **measured** (`R/decode_strict_check_pyav19.json`; the first 60 frames of each flash set and all frames of the short sets):
  - simplejpeg 1.9.0's `strict` defaults to `True`. With the default it rejects **11 of 11** generic_1080p frames (`ValueError('Corrupt JPEG data: 534 extraneous bytes before marker 0xd9')`). With `strict=False` it accepts all 11.
  - cv2 4.12 `imdecode` accepts all 11. PyTurboJPEG 2.6.1 accepts all 11, with a "Corrupt JPEG data" warning on each.
  - Every other set is accepted by every method.
- **measured** (same file, frame 0 of each set): simplejpeg and PyTurboJPEG give BGR identical to cv2 (max abs diff 0). PyAV 19.0.2 mjpeg → bgr24 differs from cv2 by up to 6 (c930e_720p_flash), 24 (c922_720p_flash), 11 (c922_1080p), 8 (c930e_1080p), 11 (c922_1600x896), 12 (c922_720p60) and 11 (generic_1080p).
- **measured, quiet run** (`B/jpeg_decode_quiet1_pyav19.json`, frame 0): the same PyAV differences reappear on the 5 sets it covers (6 / 24 / 8 / 11 / 11). simplejpeg `fastdct+fastupsample` differs from cv2 by 8 / 26 / 11 / 13 / 12 (c930e_720p, c922_720p, c930e_1080p, c922_1080p, generic_1080p). PyTurboJPEG on libjpeg-turbo 3.2.1, simplejpeg (default DCT, `strict=False`) and simplejpeg into-buffer all differ by 0.
  - This replaces the PyAV 18 smoke value cited before (fast max 26), which the quiet run confirms.
- **inferred, not isolated:** the PyAV difference may come from swscale's yuvj422p → bgr24 conversion rather than from the mjpeg decoder.
- **measured** (`B/nvjpeg_decode_quiet1_2300.json`): nvImageCodec 0.9.0.20 (nvJPEG) decoded all 5 sets on the RTX 3070 without error, to `ImageBufferKind.STRIDED_DEVICE` arrays of 720×1280×3 or 1080×1920×3.
  - **code:** the script checks only for no exception, the shape and the buffer kind (`S/bench_nvjpeg_decode.py:71-74`). The pixels were not validated, and the nvJPEG backend used was not recorded.
  - The earlier note of an import failure from a long uv-cache path did not recur. The queue command is a plain `uv run --script` (`RES/bench_queue_2300.json`, PI-NVJPEG-DECODE), and `scripts/bench_runner/run_queue.py` sets no `UV_CACHE_DIR` (Grep).
  - The original error was never captured in a result file, so it stays NOT VERIFIED.
  - Whether nvJPEG's pixels agree with cv2's, including channel order, was not measured.

### F10. Loose end: SVT-AV1 in VFR MP4 decodes 119 of 120 frames because the first PTS is negative (test-clip artefact)
- **measured** (`R/compat_recheck_pyav19.json`): `av1svt_mp4_vfr` gives `pyav_decoded` 119, and cv2 reads 119 frames starting at barcode 1. Of 11 seeks, 9 land 1 frame late, 77 lands 2 late (→ 79), and 119 is exact. The CFR `av1svt_mp4` clip is exact.
- **code:** the generator's first VFR PTS is −3 ms (`S/make_compat_clips.py:54-56`).
- **measured** (`R/verify_method_checks_pyav19.json` → `vfr`): with the pattern shifted so the first PTS is 0, PyAV decodes 120 and cv2 reads 120 in exact order. The shifted clip still has seeks 77 → 78 and 119 → 118, the same kind of error as the MJPEG VFR clips with the 67 ms gap (F3).
- **measured** (`R/av1_vfr_ffprobe_pyav19.txt`): the first stored packet has pts −560 at 1/16000 (−35 ms) with flags `KD_`, there is an edit list ("media time: 48"), and ffprobe counts 120 packets and 119 frames.
- NOT VERIFIED: the internal mechanism (why SVT-AV1 + mp4 turns −3 ms into −35 ms with a discard flag).
- **inferred:** recwriter always starts at PTS 0 (F6), so its recordings are not affected.

### F11. `RecordingWriter.write()` costs about 0.03 ms per 720p frame and 0.10-0.11 ms per 1080p frame in any container; a folder of JPEGs costs 2.5-6.8× the MKV median (2.5-7.8× across the three containers) (G1, G5)
- **code, method** (`S/bench_recwriter.py:87-117`):
  - 3000 calls per case, one unthreaded writer, called back to back with no pacing (an unpaced burst, `:106-109`).
  - The frames are real c922 JPEGs, looped: `c922_720p_flash` and `c922_1080p` (19 frames).
  - Synthetic timestamps every 33.333 ms. MKV and fMP4 use real-PTS mode, AVI uses index mode.
  - Each call is mux + binary sidecar record + flush + CSV line + flush (`S/recwriter.py:139-152`).
  - The folder baseline writes one `.jpg` per frame plus the binary sidecar record, with **no CSV** (`S/bench_recwriter.py:68-76`).
  - "fsync 30" fsyncs **only the sidecar** every 30 frames, not the video or JPEG files (`recwriter.py:154-155`; `bench_recwriter.py:75-76`).
- **measured** (`B/recwriter_quiet1_pyav19.json` → `a_write_cost`; single run, spread is across calls). All values in ms.

| Size | Writer | fsync | median | p99 | p99.9 | max | close() |
|---|---|---|---|---|---|---|---|
| 720p | MKV | off / 30 | 0.0330 / 0.0329 | 0.1364 / 0.2850 | 0.2601 / 0.3530 | 0.6333 / 0.6070 | 1.255 / 1.053 |
| 720p | fMP4 | off / 30 | 0.0319 / 0.0323 | 0.1151 / 0.2796 | 0.1816 / 0.3578 | 0.5776 / 0.5772 | 0.979 / 0.923 |
| 720p | AVI (index) | off / 30 | 0.0288 / 0.0291 | 0.1115 / 0.2913 | 0.1916 / 0.5300 | 0.5967 / **2.8203** | 0.920 / 0.872 |
| 720p | folder of JPEGs | off / 30 | 0.2233 / 0.2233 | 0.3265 / 0.5461 | 0.4164 / 0.6194 | 0.5615 / 0.6687 | 0.037 / 0.047 |
| 1080p | MKV | off / 30 | 0.1117 / 0.1103 | 0.1813 / 0.3607 | 0.3015 / 0.4137 | 0.5746 / 0.6646 | 1.043 / 1.065 |
| 1080p | fMP4 | off / 30 | 0.1112 / 0.1139 | 0.1833 / 0.3374 | 0.2504 / 0.4164 | 0.6799 / 0.6441 | 0.909 / 1.018 |
| 1080p | AVI (index) | off / 30 | 0.1019 / 0.1048 | 0.1964 / 0.3644 | 0.3753 / 0.4908 | **7.1538** / 1.9316 | 0.904 / 0.799 |
| 1080p | folder of JPEGs | off / 30 | 0.2737 / 0.2794 | 0.4049 / 0.5996 | 0.5416 / 0.6918 | 2.2599 / **10.4082** | 0.033 / 0.039 |

- **arithmetic:** the folder median (fsync off) is 6.8× the MKV median at 720p (0.2233 / 0.0330) and 2.5× at 1080p (0.2737 / 0.1117). Against fMP4 it is 7.0× / 2.5×, against AVI 7.8× / 2.7×.
- **measured:** in this burst every MKV and fMP4 call stayed at or below 0.68 ms. The worst single calls were the folder (10.41 ms, 1080p, fsync 30) and AVI (7.15 ms, 1080p, fsync off; 2.82 ms at 720p, fsync 30). Each p99.9 rests on 3 calls and each max on 1 call, in one run.
- **measured, cross-topic:** under paced 16 × 1080p60 load, write_throughput reports p99.9 of 1.7 / 2.9 / 3.2 ms (append / mkv_flush / fmp4_frame_flush) and 20.3 ms for files (`RES/BENCH_RUN_2300_SUMMARY.md:101`, `RES/write_throughput/bench/focus16_av19/`). These tails are larger than phase A's.
- **measured:** sidecar fsync every 30 frames leaves the median unchanged and roughly doubles p99 (e.g. MKV 720p 0.1364 → 0.2850 ms).
- **arithmetic:** at 30 fps, 1080p MKV spends 30 × 0.1117 = 3.4 ms per second inside `write()`, about 0.3% of one core per camera (wall time in the call, this machine).
- **measured** (`RES/BENCH_RUN_2300_LOG.jsonl`): MsMpEng (Defender) used 12.31 CPU-s during item 24 (2.24 min, 5.50 CPU-s/min). The idle items around it ran at 2.60-3.40 CPU-s/min (WT-IDLE-BEFORE 1.70, WT-IDLE-AFTER 1.56, WT-IDLE-AFTER2 1.30 CPU-s over 0.5 min each). The no-write decode item 39 ran at 1.80 CPU-s/min (16.62 over 9.21 min).
  - **arithmetic:** above the idle rate, item 24 accounts for about 5-6 CPU-s (12.31 − 2.24 × 2.60-3.40 = 4.7-6.5).
  - **code:** the 12.31 CPU-s covers all phases of item 24: phase A (including 3000 new `.jpg` files per folder case), phase B (10 MKVs) and phase C (two files of about 1.4 GB each) (`S/bench_recwriter.py:87-195`). Which part belongs to the folder cases was not separated.
  - **inferred:** the folder numbers may include some Defender real-time scanning, as on a default Windows install. write_throughput measures the folder-specific Defender cost (`RES/BENCH_RUN_2300_SUMMARY.md:35`).

### F12. A writer thread per camera keeps up with 5 paced 720p MKV cameras at 30 and 60 fps (one 60 s run each); `submit()` costs 0.014 ms (G5)
- **code, method** (`S/bench_recwriter.py:120-158`):
  - 5 `RecorderThread(RecordingWriter(..., container="mkv"), maxsize=256, policy="drop")`, 720p c922 JPEGs, MKV real PTS.
  - One paced loop sleeps to the next 1/fps tick, then submits frame i to all 5 cameras (`:137-145`), for 60 s.
  - Afterwards every file is read back and compared byte by byte.
- **measured** (`B/recwriter_quiet1_pyav19.json` → `b_threaded`; single run):

| Case | Multiframes | submit() calls | submit median / p99 / p99.9 / max (ms) | Dropped per camera | Max queue depth | Frames written per camera | All bytes exact | Thread errors |
|---|---|---|---|---|---|---|---|---|
| 5 cam × 30 fps | 1801 | 9005 | 0.0142 / 0.0586 / 0.1154 / 0.5400 | 0 ×5 | 1 ×5 | 1801 | True | None ×5 |
| 5 cam × 60 fps | 3601 | 18005 | 0.0143 / 0.0642 / 0.2000 / 0.4122 | 0 ×5 | 1 ×5 | 3601 | True | None ×5 |

- **measured:** producer lateness (how late the sleep loop woke) had a median of 0.53 / 0.54 ms and a max of 1.44 / 1.49 ms. It measures the sleep loop, not the recorder (`bench_recwriter.py:136-140`).
- **code + inferred:** `max_depth` is `qsize()` read right after `put` (`S/recwriter.py:317-319`). A maximum of 1 means each writer thread had taken the previous frame off the queue (`:324`) before the next arrived. It does not show that `write()` had returned (`:328`). The queue never filled, so the drop path and back-pressure were not exercised under load.
- **Limits:**
  - The producer only sleeps between submits. It does not hold the GIL the way a real camera loop does (decode, numpy, IPC), so contention for the GIL is not tested.
  - Not tested: 1080p, fMP4, more than 5 cameras (e.g. 16), repeat runs.

### F13. On a 10-minute 720p file, fMP4 with per-frame fragments takes about 100× longer than MKV for cv2 open + count + first read; mid-file seek is similar (G2, G9)
- **code, method** (`S/bench_recwriter.py:161-195`):
  - 18,000 c922 720p JPEGs (10 min at 30 fps), written by `RecordingWriter` with ideal 33.333 ms timestamps (real-PTS mode, effectively CFR).
  - fMP4 uses `frag_keyframe+empty_moov+default_base_moof` (`recwriter.py:52`).
  - **measured** (`R/VERIFY_method.md` W11, verifier functional check, PyAV 19.0.2, no timing): 30 JPEGs written with recwriter `mp4f` give 30 `moof` + 30 `mdat` + 1 `mfra` boxes, so one fragment per frame.
  - Three reps of: cv2 open + `CAP_PROP_FRAME_COUNT` + first read (`:177-181`); cv2 seek to frame 9000 + read; PyAV open + first packet (`:186-189`).
  - Each file is read straight after it is written, in the same process, with no cache drop (page-cache warm). MKV is the first `cv2.VideoCapture` in the process; phases A and B never call cv2.
- **measured** (`B/recwriter_quiet1_pyav19.json` → `c_open_cost`; median (min-max) over 3 reps, ms):

| Container | File bytes | cv2 open + count + first read | cv2 seek to 9000 + read | PyAV open + first packet | cv2 count |
|---|---|---|---|---|---|
| MKV | 1,398,584,150 | 3.68 (3.66-77.83) | 29.29 (29.02-29.42) | 0.39 (0.34-0.40) | 18000.0 |
| fMP4 (per-frame fragments) | 1,400,100,613 | 371.96 (370.83-378.58) | 25.67 (25.57-25.71) | 407.89 (407.89-409.05) | 18000.0 |

- **measured:** the MKV 77.83 ms is the first rep (reps: 77.83, 3.66, 3.68). It is the first cv2 open in the process and the first open of a newly written, page-cache-warm file. **inferred:** start-up (FFmpeg backend init, a Defender scan on first open, or both; not separated). It is not a cold-cache open. The fMP4 first rep (378.58) is close to its later reps.
- **arithmetic:** cv2 open + count + first read, fMP4 / MKV = 371.96 / 3.68 = 101×. PyAV open + first packet = 407.89 / 0.39 ≈ 1,046×. MKV's 3.68 ms includes a first-frame decode.
- **measured, cross-topic** (`RES/jpeg_passthrough/bench/open_long.json`, quiet run, 54,000 frames, c930e intervals looped, 5 reps). Metric: cv2 open + count only, no read (`scripts/jpeg_passthrough/bench_open_long.py:74-77`); PyAV open + `streams.video[0].frames`:
  - per-frame-fragment fMP4: cv2 median 1107.28 ms, PyAV 1224.24 ms;
  - fMP4 with 1 s fragments (`min_frag_duration` 1000000): cv2 42.57 ms;
  - finalised MP4: cv2 2.38 ms;
  - MKV: cv2 0.19 ms (reps 4.93, 0.28, 0.19, 0.19, 0.19; the elevated first rep after write appears there too).
  - **inferred, cross-script:** fMP4 open time grows with the fragment count (about 372 ms at 18,000 fragments in phase C, about 1107 ms at 54,000 in open_long). The two scripts time different things (phase C adds a first read) and use different corpora and writers, so this is a trend, not a fit.
  - **arithmetic, like with like:** open_long (open + count): MKV 0.19 vs per-frame fMP4 1107.28 ms (about 5,800×); phase C (open + count + first read): MKV 3.68 vs fMP4 371.96 ms (101×).
- **cross-topic:** an open fMP4 fragment is lost on a crash. That is 1 frame with per-frame fragments and up to 1 s with 1 s fragments (background), per `RES/crash_resilience/FINDINGS.md:423` (§3B).
- **Limit:** both counts are right here because the timestamps are ideal. With real camera timing MKV miscounts (F3).

### F14. CPU JPEG decode: simplejpeg into a preallocated buffer is the fastest full-size BGR decode; every library releases the GIL; cv2 is slowest (live UI, decode at source)
- **code, method** (`S/bench_jpeg_decode.py:51-140`):
  - One call per frame over 5 passes after 20 warm-up calls. `threaded` is aggregate decodes/s with 1 and 5 Python threads over 5 s.
  - cv2 runs with `setNumThreads(1)` (`:155`). simplejpeg runs with `strict=False` (`:58-63`).
  - "into preallocated buffer" reuses **one thread-local buffer** on every call (`:64-71`), so it is cache-hot and already allocated. A real ring writes to a different slot each frame; that cost was not measured.
  - PyAV uses one mjpeg `CodecContext` per thread with `thread_count = 1` (`:80-86`). "native YUV" is decode with no colour conversion.
  - Inputs are the cameras' own JPEGs. Median JPEG sizes: c930e 720p 56,715 B; c922 720p 77,265 B; c930e 1080p 133,365 B; c922 1080p 192,435 B; generic 1080p 65,502 B.
- **measured** (`B/jpeg_decode_quiet1_pyav19.json`; single run; median ms per call, n = 1500 / 1500 / 95 / 95 / 55):

| Method | Output | c930e 720p | c922 720p | c930e 1080p | c922 1080p (min-max across calls) | generic 1080p |
|---|---|---|---|---|---|---|
| cv2 imdecode | full BGR | 2.0959 | 2.3106 | 4.6498 | 5.2931 (5.2227-6.1716) | 4.1413 (includes a stderr write per call) |
| cv2 IMREAD_REDUCED_COLOR_2 | 1/2 | 0.8068 | 1.0335 | 2.3699 | 2.9316 (2.8721-3.6761) | 1.8370 (includes a stderr write per call) |
| simplejpeg | full BGR | 1.4754 | 1.7454 | 3.3879 | 4.0701 (4.0212-4.6263) | 2.8843 |
| simplejpeg fastdct+fastupsample | full BGR (not identical) | 1.2824 | 1.5305 | 2.9195 | 3.4824 (3.4438-3.6613) | 2.3343 |
| simplejpeg min_height=360 | reduced | 0.7616 | 0.9845 | 1.6920 | 2.1802 (2.1458-2.4030) | 1.2793 |
| **simplejpeg into preallocated buffer (one reused buffer)** | full BGR | **1.1577** | **1.4027** | **2.7215** | **3.3434** (3.3042-4.0412) | **2.1380** |
| PyTurboJPEG (libjpeg-turbo 3.2.1) | full BGR | 1.4439 | 1.6887 | 3.3295 | 3.9840 (3.9164-4.3225) | 2.7631 |
| PyTurboJPEG scale 1/2 | 1/2 | 0.7725 | 0.9998 | 1.9974 | 2.6075 (2.5628-2.7423) | 1.4864 |
| PyAV mjpeg → bgr24 | full BGR (not identical) | 1.6528 | 1.9152 | 3.4025 | 4.0480 (3.9030-4.9904) | 2.8773 |
| PyAV mjpeg native YUV | planes | 1.1747 | 1.3823 | 2.7347 | 3.3099 (3.2278-4.0885) | 2.1808 |

- **measured:** PyAV native YUV (planes, no BGR) is slightly faster than simplejpeg into-buffer on c922 720p (1.3823 vs 1.4027) and c922 1080p (3.3099 vs 3.3434). simplejpeg into-buffer is the fastest full-size **BGR** decode on every set.
- **measured** (same file, `threaded`): the 5-thread aggregate is 3.92-5.03× the 1-thread rate for every method and set (arithmetic on the file values). A ratio above 5 on 5 threads shows single-run noise. On c922 1080p, for example: simplejpeg into-buffer 297.3 → 1486.1 decodes/s, cv2 186.9 → 807.5, PyTurboJPEG 244.4 → 1161.2, PyAV bgr24 249.4 → 1056.8.
  - **inferred:** all four libraries release the GIL during decode. The run started with 16 logical CPUs (P-cores), so 5 threads did not oversubscribe them.
- **arithmetic, per camera at 30 fps, c922 1080p (the largest JPEGs), this machine's P-cores:** cv2 30 × 5.2931 = 159 ms/s (0.16 core); simplejpeg into-buffer 30 × 3.3434 = 100 ms/s (0.10 core).
  - For 16 cameras at 30 fps (480 decodes/s): 32% of simplejpeg into-buffer's measured 5-thread rate (1486.1/s) and 59% of cv2's (807.5/s).
  - **inferred:** this is an extrapolation from 5 threads on one i7-14700K. 16 concurrent decoders, and the 2020+ CPUs in the hardware target, were not measured.
- **measured** (`RES/bench_runner/logs/20261109T230007/39_PI-JPEG-DECODE-PYAV19.err.txt`, counted 2026-11-10): the stderr holds 20,021 bare libjpeg `Corrupt JPEG data: N extraneous bytes before marker 0xd9` lines plus 11 PyTurboJPEG `UserWarning` lines (Python prints each distinct warning once).
  - **inferred (exact count match):** the 20,021 bare lines come from `cv2.imdecode`, one per call on generic_1080p: 5,998 `cv2_imdecode_bgr` + 14,022 reduced-2 calls (warm-up + timed + threaded, from the JSON) + 1 reference decode (`S/bench_jpeg_decode.py:171`). So the cv2 generic_1080p timings include one stderr write per call.
  - These are the same warnings as F9, not errors. (`R/BENCH.md` §2 was corrected to these counts by GF05, 2026-11-10.)

### F15. nvJPEG decode (nvImageCodec 0.9.0.20, RTX 3070): faster than the CPU only if the pixels stay on the GPU, assuming the timing synchronises
- **code, method** (`S/bench_nvjpeg_decode.py:65-96`):
  - `gpu_single` = `Decoder.decode(bytes)` plus `__cuda_array_interface__` access. The script comment says the access "forces the decode to be complete" (`:82`); that is not independently checked.
  - `gpu_to_host` = a **second, separate** decode plus `.cpu()` to numpy, so it is a full decode + copy (`:84-86`). It is interleaved per frame with `gpu_single` (`:79-86`). If the access in `gpu_single` does not synchronise, `gpu_single` under-reads and `gpu_to_host` absorbs leftover GPU work (inferred).
  - `gpu_batch5` = one `decode([5 frames])` call on the set's first 5 frames, repeated 100 times, with no host sync between reps (`:89-95`).
  - Only median / mean / p90 / p99 are recorded; no min or max (`:48-51`). The values are host wall time. Host CPU time and the nvJPEG backend (GPU vs hybrid CPU Huffman) are not recorded.
- **measured** (`B/nvjpeg_decode_quiet1_2300.json`; single run; ms):

| Set | gpu_single median (p99) | gpu_to_host median (p99) | batch of 5 median (p99) | batch / 5 (arithmetic) |
|---|---|---|---|---|
| c930e 720p | 0.7233 (0.834) | 1.4400 (1.6293) | 1.2017 (4.0703) | 0.240 |
| c922 720p | 0.9343 (1.0601) | 1.6835 (2.5246) | 1.2320 (1.7647) | 0.246 |
| c930e 1080p | 2.0797 (2.3719) | 3.4495 (3.7825) | 3.1150 (6.3432) | 0.623 |
| c922 1080p | 2.2676 (2.5306) | 3.6440 (4.0335) | 3.1970 (5.6243) | 0.639 |
| generic 1080p | 1.9188 (2.5173) | 3.3670 (3.7484) | 2.6539 (3.4394) | 0.531 |

- **arithmetic (this machine):** with the copy to host, nvJPEG at 1080p (3.37-3.64 ms) is not faster than simplejpeg into-buffer (2.14-3.34 ms, F14) per call. Left on the GPU it is 1.92-2.27 ms single, or 0.53-0.64 ms per frame in a batch of 5, if the timing synchronises (NOT VERIFIED).
- **measured:** the item finished in 10.28 s (`env.finished_unix − env.started_unix`; arithmetic). The stderr holds 5 `cuDevicePrimaryCtxRelease failed: 4` lines printed after `wrote ...json` (`RES/bench_runner/logs/20261109T230007/40_PI-NVJPEG-DECODE.{out,err}.txt`).
- **Version note:** intra_compare uses nvImageCodec 0.10.0.9. The bench pins 0.9.0.20 because 0.10.0.9 "was published 2026-11-03 (<2 weeks old)" (`S/bench_nvjpeg_decode.py:15`).

## 3. Comparison tables

**Containers for transcode-free camera JPEG** (all PyAV 19.0.2; cv2 4.12 CAP_FFMPEG)

| | MKV | fMP4 (`frag_keyframe+empty_moov+default_base_moof`) | AVI | Folder of JPEGs | Evidence |
|---|---|---|---|---|---|
| Byte-exact round trip, 7 sets | yes | yes | yes | not tested here | F2 |
| Time base (real PTS) | 1/1000 (forced) | 1/1000000 | 1/600 | n/a (sidecar) | F2 |
| cv2 count, real (VFR) PTS | wrong on 1 of 7 sets; 53,819 of 54,000 on a 30-min file | right on 7 of 7 and at 54,000 | wrong on 7 of 7 (fps 600) | n/a | F3 |
| cv2 count, index (CFR) PTS | right on 7 of 7; also gap60, drop50 and 54,000 (GF02) | right on c930e, gap60, drop50, c922 (per-frame and 1 s fragments) and at 54,000 (1 s); POS_FRAMES seeks 11/11 (GF02) | right on 7 of 7 | n/a | F3; GF02 |
| Overhead per frame, 891-frame 720p set | 45.2 B | 131.9 B | 30.9 B (index) / 485.3 B (real) | n/a | F2 |
| `write()` median, 720p / 1080p (ms) | 0.0330 / 0.1117 | 0.0319 / 0.1112 | 0.0288 / 0.1019 | 0.2233 / 0.2737 | F11 |
| Worst single `write()`, unpaced burst, 1 call (ms) | 0.66 | 0.68 | 7.15 | 10.41 | F11 |
| p99.9 `write()`, paced 16 × 1080p60 (cross-topic, ms) | 2.9 (mkv_flush) | 3.2 (fmp4_frame_flush) | not tested | 20.3 | F11 |
| cv2 open + count + first read, 10-min 720p, warm (ms) | 3.68 (3.66-77.83; 77.83 = first cv2 open in process) | 371.96 (370.83-378.58), per-frame fragments | not in bench | not in bench | F13 |
| cv2 open + count, 30-min, warm (cross-topic, ms) | 0.19 | 1107.28 per-frame / 42.57 with 1 s fragments | not in bench | not in bench | F13 |
| PyAV open + first packet, 10-min 720p (ms) | 0.39 | 407.89 | not in bench | not in bench | F13 |
| cv2 seek to mid-file + read (ms) | 29.29 | 25.67 | not in bench | n/a | F13 |
| After a hard kill: torn last frame returned? | no (partial block dropped silently) | yes, `packet.is_corrupt` True | yes, `packet.is_corrupt` True | not tested | F4 |
| After a hard kill: cv2 FRAME_COUNT | −2.77e17 (invalid); with fp, paced kills: −2.767e17 in 24/24 (GF02) | 298.0 = frames read (torn one included); with fp, paced kills, both fragment modes: = complete frames in 24/24 (GF02) | 0.0 (invalid) | n/a | F4; GF02 |
| Usable by cv2 without `recover()` | no | yes, except one torn last frame | no | n/a | F4 |
| `recover()` restores a correct count | yes (perf_counter timestamps; index PTS 12/12, GF02); **no** for real-PTS MKV with real camera intervals: fps 62.5, about 2.1× count in 12/12 (GF02) | yes (GF02: 24/24, both PTS modes) | yes | n/a | F6 |

**Python JPEG decode, c922 1080p (192 KB camera JPEG), single run, i7-14700K P-cores / RTX 3070** (F14, F15)

| Decoder | Median ms/call | 5-thread decodes/s | Accepts generic_1080p | Same BGR as cv2 (frame 0) |
|---|---|---|---|---|
| cv2.imdecode 4.12 | 5.2931 | 807.5 | 11/11 (stderr warning per call) | reference |
| simplejpeg 1.9.0, `strict=False` | 4.0701 | 1150.0 | 11/11 | yes (0) |
| simplejpeg into preallocated buffer (one reused buffer) | 3.3434 | 1486.1 | 11/11 | yes (0) |
| simplejpeg `strict=True` (library default) | not timed | not timed | **0/11** | yes on the other sets |
| PyTurboJPEG 2.6.1 + libjpeg-turbo 3.2.1 | 3.9840 | 1161.2 | 11/11 (warnings) | yes (0) |
| PyAV 19.0.2 mjpeg → bgr24 | 4.0480 | 1056.8 | 11/11 | no (11 on this set) |
| PyAV 19.0.2 mjpeg, native YUV (no conversion) | 3.3099 | 1504.2 | yes | n/a (planes) |
| nvJPEG, result on GPU (sync not verified) | 2.2676 | not measured | decoded without error (output not validated) | not measured |
| nvJPEG, copied to host | 3.6440 | not measured | decoded without error (output not validated) | not measured |
| nvJPEG, batch of 5, per frame | 0.639 (arithmetic) | not measured | decoded without error (output not validated) | not measured |
| Reduced preview: simplejpeg min_height=360 / PyTurboJPEG 1/2 / cv2 reduced 2 | 2.1802 / 2.6075 / 2.9316 | 2262.1 / 1845.9 / 1587.7 | yes | n/a |

**PyAV 18.0.0 vs 19.0.2 for this recorder**

| Item | 18.0.0 (background) | 19.0.2 | Evidence |
|---|---|---|---|
| FFmpeg | 8.1.2 | 9.0.2 | measured, version probes |
| Codecs in the probed list (44) | same | same | measured |
| recwriter output | byte-exact | byte-exact, code unchanged | measured, F2 |
| `time_base` type | Fraction | AVRational, never None | measured + source |
| GIL during mux | released | released | code (18 venv) / source (19 wheel), F7 |
| GIL during header / trailer / close | held | released | source, F7/F8 |
| Benefit for local files | - | not measured (no timed PyAV 18 vs 19 comparison) | - |
| Python | 3.11 supported (dropped in 19) | 3.12+ | source, CHANGELOG |

## 4. Implications for the plan

1. **A new capture backend is needed for G1.** It must return `(jpeg_bytes, timestamps)`, because no OpenCV configuration tested can (F1). The recorder call changes from `video_writer.write(image)` to enqueueing bytes (F1, F7, F12).
2. **Write CFR (index) PTS to the file and keep the exact ns timestamps in the sidecar.** This policy removes jpeg_passthrough's MKV-count reason for ruling out MKV (`results/jpeg_passthrough/FINDINGS.md:568`), which was measured with real VFR PTS. Index PTS with dropped frames and fMP4 1 s fragments with index PTS were the untested cases; GF02 Part A has now tested both (next bullet). See `results/crash_resilience/gapfill/GF01_container_decision_table.md`.
   - **measured (GF02 Part A, F3):** index PTS are exact for cv2 count, `POS_FRAMES` seek (11/11) and FreeMoCap in every container tested (MKV + fp, MKV + fp + empty packet, fMP4 per-frame + fp, fMP4 1 s + fp), with drops (gap60, drop50) and at 54,000 frames (18/18 files). Real PTS break seeks even in fMP4 when there are drops or rate drift (c930e full 9/11, gap60 1/11, drop50 8/11).
   - FreeMoCap counts with `CAP_PROP_FRAME_COUNT` and raises when cameras differ (F3, code).
   - With real-time PTS, cv2's count and seek go wrong on drops or rate drift: MKV miscounted 1 of 7 camera sets and 181 of 54,000 frames on a long file, AVI miscounted 7 of 7, and a 67 ms gap broke MKV count and MKV/MP4 seeks. Jitter of ±3 ms alone did no harm (F3).
   - The sidecar, not the container, carries timing: MKV keeps only 1 ms (F2).
3. **Container for G2: against per-frame-fragment fMP4, MKV wins on open cost; against 1 s-fragment fMP4 the choice rests on crash behaviour.**
   - Like with like (F13): cv2 open + count + first read on a 10-minute file is 3.68 ms (MKV) vs 371.96 ms (per-frame fMP4); cv2 open + count on a 30-minute file is 0.19 ms vs 1107.28 ms.
   - **inferred, arithmetic (serial, warm-cache opens):** 16 cameras × 372 ms ≈ 6 s for 10-minute per-frame-fragment fMP4 files. Parallel opens were not measured.
   - fMP4 with 1 s fragments opens in 42.57 ms at 30 minutes (about 0.7 s for 16 files, serial; arithmetic), but an open fragment can lose up to 1 s on a crash (F13, cross-topic). HANDOFF.md:173 still names fMP4 (1/1e6 time base) the leading container; GF01 lists the cross-topic disagreement (`RES/crash_resilience/gapfill/GF01_container_decision_table.md` §2.2, §4).
   - **measured (GF02 Part B, recwriter-format sidecar, live paced kills at 30 fps, 6 kills per container and PTS mode; `GF02/GF02_container_matrix.json` → `partB[].lost_vs_sidecar`):** fMP4 1 s + fp lost 1-30 acknowledged frames per kill (real 20, 14, 24, 22, 29, 26; index 20, 17, 30, 1, 11, 10). MKV + fp and fMP4 per-frame + fp lost 1 in every kill, and MKV + fp + empty packet lost 0.
   - **inferred (GF02 report):** with index PTS the 1 s loss equals the frames since the last 1 s fragment boundary.
   - **measured, cross-topic:** write_throughput (720p60, 2 kills each) lost 33 and 62 with 1 s fragments without fp, and 46 and 5 with fp (`RES/write_throughput/FINDINGS.md:96`).
   - **measured (GF02):** no torn tail packet occurred in the 48 paced kills, so torn-tail flagging was not exercised by them (F4/F5 remain the evidence).
   - MKV never returns a partial JPEG, but a killed MKV reports an invalid count (−2.77e17), so `recover()` must run before any cv2 read (F4, F6).
   - **measured (GF02, F6):** `recover()` of a real-PTS MKV gives `r_frame_rate` 125/2 and `avg_frame_rate` 0/0, so cv2 reads fps 62.5 and about 2.1× the frames (12/12). Index-PTS MKV and every fMP4 recover with the correct count, byte-exact (48/48). With real PTS, `recover()` (`S/recwriter.py:259`) needs a fix before MKV can rely on it (inferred).
   - Whatever the container: run `find_unfinished()` + `recover()` at skellycam startup and add a load-time check in FreeMoCap (F3, F4, F6). Where recovery runs is a plan decision.
   - Add `flush_packets=1` to recwriter's muxer options. recwriter sets none today (F4, code), and crash_resilience recommends it (`RES/crash_resilience/FINDINGS.md:439`, §4 item 2).
4. **Write cost does not decide the container; folder-of-files is the slow outlier.**
   - Any container `write()` (mux + sidecar + flush) is 0.03 ms at 720p and 0.10-0.11 ms at 1080p, about 0.3% of a core per 1080p30 camera on this machine (F11).
   - A folder of JPEGs is 2.5-7.8× slower at the median than the containers, has the worst single burst call (10.4 ms) and the worst paced p99.9 (20.3 ms, cross-topic) (F11). The folder-specific Defender cost is measured in write_throughput, not here (F11). This supports a container over folder-of-files for G5.
   - AVI had a 7.2 ms outlier and the worst cv2 behaviour (F3, F4, F11), so it is not a candidate.
5. **Torn-frame detection must work at packet level or through the sidecar.** PyAV 19 flags the torn tail packet in fMP4/AVI with `packet.is_corrupt`, but the frame-level flag and cv2 give nothing (F4, F5).
   - sfn26's `sequential_video_reader` raises only on frame-level `self.frame.is_corrupt` (`sfn26:skellycam/core/recorders/videos/sequential_video_reader.py:47-48`), so it would pass a torn frame (inferred from code + measured).
   - The sidecar CRC also catches same-length corruption and a missing tail (inferred).
6. **Use one writer thread per camera inside the camera process, with an explicit drop counter.**
   - 5 paced 720p MKV cameras at 30 and 60 fps: 0 drops, queue depth 1, all files byte-exact, `submit()` 0.014 ms (F12).
   - The GIL is released around mux (already in 18) and around header, trailer and close (new in 19) (F7).
   - The queue size cannot be derived from these runs, because the queue never filled. Size it from the paced concurrent write tails: p99.9 2.9-3.2 ms for mkv_flush / fmp4_frame_flush and 20.3 ms for files under 16 × 1080p60 (cross-topic, F11). Phase A's unpaced-burst maxima (0.68 ms MKV/fMP4) understate this. **inferred:** at 30-60 fps (16.7-33.3 ms per frame), a few frames of headroom covers what was measured.
7. **Adopting PyAV 19.0.2 is safe; its benefit is unmeasured.** Codec support gives no reason to bump (F8). The extra GIL release motivated upstream by network outputs was not measured for local files (F7, F8).
   - A bump needs `requires-python` raised to 3.12 (`pyproject.toml:5`) and the `av>=12.0.0` pin raised (`pyproject.toml:68`).
   - Code that tests `time_base is None` must change; skellycam's current uses survive (F8).
8. **No format reason to bump OpenCV:** 5.0.0.93 behaves identically on the PyAV 18 clips (F3, background).
9. **Live-view / decode-at-source decoder: simplejpeg with `strict=False`, decoding into a preallocated (shared-memory) buffer.**
   - On this machine's P-cores it is the fastest full-size BGR decode on every set (1.16-3.34 ms). On c922 1080p it takes 37% less time per call than cv2 (1.58× the rate; arithmetic: 3.3434 vs 5.2931). It is bit-identical to cv2 on frame 0 (F9, F14).
   - The bench reused one cache-hot buffer; the cost of writing into a different ring slot each frame was not measured (F14).
   - The default `strict=True` rejects a real camera, so `strict=False` is required (F9).
   - All CPU decoders release the GIL, so one decode thread per camera scales to 5 threads here (3.92-5.03×, single run) (F14). Other CPUs in the hardware target were not measured.
   - For previews, reduced decodes cost 0.76-2.18 ms with simplejpeg `min_height=360` (F14).
   - PyAV and simplejpeg fast are not bit-identical to cv2, so keep one decoder per pipeline (F9).
   - Inputs are the C930e and C922 cameras' own JPEGs, inferred to be about target A from their q94-equivalent tables (HANDOFF.md:55-57). Re-encoded files at target B would decode faster (smaller files; inferred, not measured).
10. **nvJPEG decode is worth it only for GPU consumers** (e.g. pose inference on CUDA). With the copy to host it is no faster than simplejpeg at 1080p on this machine (F15).
    - Its host CPU cost, backend, pixel agreement and whether the GPU-side timing synchronises are unmeasured (F15).
    - **Cross-topic (encode, not decode):** in `RES/intra_compare/bench/matched_stream_A_1080p_20261110T042204Z.json` (`summary`, 4-frame quality check), nvJPEG encode fed camera MJPEG decoded on the CPU (`mjpeg_cpu`, via host RGB; `nvjpeg_422` and `nvjpeg_420`) gives SSIM-Y 0.9954, below target A (matched SSIM-Y 0.99617). Fed `mjpeg_qsv`-decoded frames, `nvjpeg_420` reaches SSIM-Y 0.99788 / PSNR-Y 56.462 dB, above target A. So the miss is specific to the CPU-decode source, not to every decode → nvJPEG path.
11. **Chromium cannot play MJPEG in `<video>`**, so G8/G9 need a proxy or a JS decode path. MJPEG in mp4, fMP4, mkv and mov gives `DEMUXER_ERROR_NO_SUPPORTED_STREAMS`, and in AVI `DEMUXER_ERROR_COULD_NOT_OPEN`, on E35, E45 and C156 (cross-topic, measured, `RES/chromium_codecs/tables.md:37,42-45,105-119`). That decision is not made in this topic.

## 5. Run flags and caveats that apply to this topic

| Flag (`RES/BENCH_RUN_2300_SUMMARY.md` §3) | Applies here? | Effect |
|---|---|---|
| Single runs (flag 12) | **yes** | The recwriter A/B phases, JPEG decode and nvJPEG decode each ran once. Spreads are per-call percentiles or min-max within one run, not across repeats. Only recwriter phase C has 3 reps. Each threaded decode rate is one 5-s run (one ratio above 5× on 5 threads shows the noise). |
| Defender real-time ON (§2) | **yes** | MsMpEng CPU-s during items (`RES/BENCH_RUN_2300_LOG.jsonl`): PI-RECWRITER 12.31 over 2.24 min (5.50/min, about 5-6 CPU-s above the 2.60-3.40/min idle rate, all phases together); PI-JPEG-DECODE 16.62 over 9.21 min (1.80/min, no file writes); PI-NVJPEG 0.78. This is part of the real cost on a default install. No Defender scan event fell inside these items. |
| P-core pinning | **yes** | The runner set P-core affinity on itself before starting each child (`scripts/bench_runner/run_queue.py:21-22,441-443`), and the log has `affinity: pcores` for items 24, 39 and 40. Affinity during the run was not recorded; flag 2 shows a library can widen it. The PI JSONs' `cpu_count: 28` is `os.cpu_count()`. Thread scaling may differ on all 28 CPUs. |
| Per-write latencies higher tonight than in the daytime run (flag 7) | indirectly | No earlier timed PI result exists (the earlier attempt was killed with no file), so there is nothing to compare. The P-core pinning that may explain flag 7 also applies here (inferred). |
| CPU timer granularity 15.625 ms (flag 11) | **no** | The PI benches time wall clock with `perf_counter_ns` and record no CPU time (`bench_recwriter.py:104-109`, `bench_jpeg_decode.py:103-111`, `bench_nvjpeg_decode.py:66`). |
| libx265 widened affinity, items 1-3 (flag 2) | no | Not these items. |
| NVENC 12-session limit (flag 3) | no | No encoder here. |
| nvJPEG fed decoded MJPEG misses target A (flag 4) | cross-topic | An encode result, cited in implication 10. Only the CPU-decoded (`mjpeg_cpu`) source misses (SSIM-Y 0.9954); the `mjpeg_qsv` source reaches 0.99788. The decode bench here measures time only. |
| WebCodecs scrub errors, `<video>` N=8 stalls (flags 5, 6) | no | They concern the UI path (implication 11), not Python. |
| uncompressed_intra has no lossless check (flag 9) | no | Here, byte exactness of the passthrough is checked in phase B (`all_bytes_exact` True) and in F2. |
| Load | clean | CPU before each item averaged 3.2-3.8% (max 9.4%). No item was load-flagged. The leftover-process notes list only the monitoring session's shells (`R/BENCH.md` §1). |

Other caveats:
- **Phase A input is small and looped:** the 1080p case cycles 19 frames. **inferred:** this has little effect on a passthrough write, which copies bytes without encoding.
- **Phase A is an unpaced burst:** its p99.9 rests on 3 calls and its max on 1. Paced concurrent tails are larger (F11, cross-topic).
- **The folder baseline does slightly less work than the container writers:** it writes no CSV line (F11, code). So its median gap is, if anything, understated.
- **"fsync 30" covers only the sidecar.** It says nothing about the cost of making the video durable. crash_resilience measures fsync of the media file.
- **Phase C is 720p only, page-cache warm, ideal timestamps.** No cold-cache open was measured for any container. The MKV first rep (77.83 ms) is the first cv2 open in the process and the first open after write; its cause is not separated (F13).
- **Phase C and open_long time different things** (open + count + first read vs open + count), on different corpora and writers (F13).
- **cv2 generic_1080p decode timings include one stderr write per call** (inferred from the warning count, F14).
- **Decode inputs at 1080p are short** (19, 19 and 11 frames looped 5 times). Pixel agreement is checked on frame 0 only.
- **libjpeg-turbo 3.2.1:** **measured** 2026-11-10 from the DLL at `env.turbojpeg_dll` (`.../jpeg_passthrough/ljt321/bin/turbojpeg.dll`): sha256 `3dd7a8a9…f975fd`, Windows ProductVersion 3.2.1, with `uninstall_3.2.1.exe.nsis` in the install folder. The version is not in the JSON itself, only the path; `RES/BENCH_QUEUE_2300.md:174,200` records the same sha256. The functional check F9 used 3.2.0, and the script docstring still names 3.2.0 (`S/bench_jpeg_decode.py:22-24`).
- **nvJPEG:** `gpu_batch5` repeats the same 5 frames with no host sync between reps; `gpu_to_host` includes a second decode; there is no CPU-time field; the backend is not recorded; nvImageCodec 0.9.0.20 differs from intra_compare's 0.10.0.9.
- **One machine:** all timed numbers are from one i7-14700K (P-cores) and one RTX 3070. The hardware target spans 2020+ CPUs/GPUs.
- **Corpus scenes are dim** (the flash sets show a monitor). JPEG sizes, and with them decode and write cost, may differ for bright, textured scenes (open question).

## 6. Not tested / limits / NOT VERIFIED

- **Writer thread under realistic load:** GIL contention from a busy producer, back-pressure in block mode, and the drop path under load (queue depth never exceeded 1, F12). 1080p, fMP4 and 16-camera paced runs. The gap flag on dropped frames was not exercised on PyAV 19 (F7).
- **Benefit of PyAV 19's extra GIL release for local files:** there was no PyAV 18 vs 19 timed comparison (F7, F8).
- **16 concurrent Python decoders, and other CPUs:** only 1 and 5 threads on this machine's P-cores were measured. The 16-camera figure in F14 is extrapolated.
- **Decoding into a different shared-memory slot each frame:** the bench reused one buffer (F14).
- **Host CPU cost of nvJPEG calls, the nvJPEG backend, and nvJPEG pixel agreement / channel order** (F15).
- **Seek accuracy on camera-byte files written by recwriter:** F13 times seeks but does not check which frame came back (F3). GF02 checked seek identity on 36 clean-closed files written by `GF02Writer` (`add_mux_stream`, `flush_packets=1`; F3), but not on recwriter's encoder-stream files or the F13 timed files.
- **Long-file open for AVI and folder-of-files; fMP4 with 1 s fragments written by recwriter; 1080p long files; cold-cache opens; parallel opens** (F13).
- **Lean functional re-checks:** the PyAV 19 round trip did not fully decode every frame. cv2 `grab()` counts exist only for c930e_720p_flash. The crash re-check decoded only the last packet per file; container demux with flags covered 3 killed and 3 truncated files (F4, F5). The full decode-all results are PyAV 18 background.
- **Kill test:** one kill per variant, writer paced at about 30 fps, parent kills child.
  - GF02 added 48 paced kills with fp (4 containers × 2 PTS modes × 6), but none produced a torn tail, and FreeMoCap was not run on killed or recovered files (`GF02/GF02_container_matrix.md`, "Combinations not run").
  - Not a power-loss test.
  - Killing the whole skellycam process tree was not tested here (see crash_resilience).
  - A kill with a full writer queue was not tested.
  - `recover()` with a container one packet longer than the sidecar was not tested (F6).
- **Truncation test** used finalised files, so its cv2 counts are artefacts (F5).
- **The frame-gap flag test and the VP9 / H.264 / intra-VP9 compat clips** exist only on PyAV 18 (background), CFR only.
- **cv2 version:** the PyAV 19 re-checks and benches used `opencv-python` 4.12.0.88, not the venv's `opencv-contrib-python` 4.12.0.88.
- **Hardware-encoded AV1/VP9/HEVC/H.264-intra bitstreams** were not probed with cv2. Reader behaviour on them is NOT VERIFIED here.
- **Not tested:**
  - FreeMoCap's own code end to end (its venv is stale, `R/NOTES.md` §11). The F4 FreeMoCap failure path is inferred from code.
  - Linux and macOS wheels.
  - A Python lossless 90/270 rotation (see jpeg_passthrough).
  - Audio recording.
  - A recorder in a separate process.
- **NOT VERIFIED:**
  - The cause of the 2 MKV frames lost at a kill beyond the 1 the cluster rule explains. An unflushed 262,144 B FFmpeg buffer is the likely cause (inferred; the killed size is exactly 88 × 262,144 B, F4).
  - The SVT-AV1 + MP4 internal mechanism (F10).
  - Which files produced the FFmpeg `[mjpeg] overread` warnings (F4).
  - Why `recover()` of a real-PTS MKV writes `r_frame_rate` 125/2. Inferred: with no rate in the template, FFmpeg guesses from the timestamps, and real c930e intervals on a 1 ms grid give 62.5 (F6).
  - The original nvImageCodec long-path import error. It did not recur with the default uv cache in tonight's run (F9).
  - That `__cuda_array_interface__` access synchronises the decode (F15).
  - That the PyAV vs cv2 pixel difference comes from swscale (F9).
  - The cause of the MKV first-open 77.83 ms (backend start-up vs a Defender scan) (F13).
  - That the 20,021 bare stderr lines are all from cv2 (inferred from an exact count match, F14).
  - That the C930e/C922 JPEGs are as faithful to the scene as a target-A re-encode (inferred, HANDOFF.md:57).
- **Not re-checked against n9.0.2:** FFmpeg's `movenc.c` / `matroskadec.c` (crash_resilience cites movenc.c).
- **`recwriter.py` is a research prototype:** one stream per file, no audio.

## 7. How to reproduce (repo root, Bash; `uv` 0.11.8)

```
P=research/skellycam_recording/recording_upgrade
# PyAV 19.0.2 functional re-checks (F2-F10)
uv run --script $P/scripts/python_integration/pyav19_recheck.py $P/results/python_integration/pyav19_recheck_roundtrip_crash.json
uv run --script $P/scripts/python_integration/verify_method_checks_pyav19.py $P/results/python_integration/verify_method_checks_pyav19.json
uv run --script $P/scripts/python_integration/compat_recheck_pyav19.py $P/results/python_integration/compat_recheck_pyav19.json
uv run --script $P/scripts/python_integration/decode_strict_check_pyav19.py $P/results/python_integration/decode_strict_check_pyav19.json <dir>/bin/turbojpeg.dll
uv run --script $P/scripts/python_integration/recorder_thread_check_pyav19.py $P/results/python_integration/recorder_thread_check_pyav19.json
uv run --script $P/scripts/python_integration/pyav_version_probe.py --tag pyav_19.0.2_uv
# ffprobe inspection behind F10 (inspection only)
ffprobe -v error -select_streams v:0 -show_entries packet=pts,dts,flags -of csv=p=0 <raw>/python_integration/compat_pyav19/av1svt_mp4_vfr.mp4 | head -3
ffprobe -v trace <raw>/python_integration/compat_pyav19/av1svt_mp4_vfr.mp4 2>&1 | grep -i "elst\|edit list"

# Timed benches (F11-F15): quiet machine only, one at a time, through the runner (P-core affinity at start, load record)
uv run --script $P/scripts/bench_runner/run_queue.py --only PI-RECWRITER-AV19,PI-JPEG-DECODE-PYAV19,PI-NVJPEG-DECODE --deadline HH:MM
# the queue commands it runs (from results/bench_queue_2300.json):
uv run --script $P/scripts/python_integration/bench_recwriter.py --tag quiet1_pyav19            # -> results/python_integration/bench/recwriter_quiet1_pyav19.json
uv run --script $P/scripts/python_integration/bench_jpeg_decode.py --turbojpeg-dll <ljt 3.2.1>/bin/turbojpeg.dll --tag quiet1_pyav19   # -> jpeg_decode_quiet1_pyav19.json
uv run --script $P/scripts/python_integration/bench_nvjpeg_decode.py --tag quiet1_2300         # -> nvjpeg_decode_quiet1_2300.json (nvImageCodec 0.9.0.20)
# DLL used tonight: C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/jpeg_passthrough/ljt321/bin/turbojpeg.dll (sha256 3dd7a8a9…f975fd, ProductVersion 3.2.1; BENCH_QUEUE_2300.md:174)

# Stderr warning count behind F14 (no timing)
grep -c 'Corrupt JPEG data' $P/results/bench_runner/logs/20261109T230007/39_PI-JPEG-DECODE-PYAV19.err.txt   # 20032 = 20021 bare + 11 UserWarning

# Recovered-file rates behind F6 (inspection only; listed in GF02_recovered_rates.txt)
ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate,avg_frame_rate,time_base:format=duration -of csv=p=0 <recovered file>

# PyAV 18 background runs (skellycam venv, read-only use)
.venv/Scripts/python.exe $P/scripts/python_integration/test_roundtrip.py
.venv/Scripts/python.exe $P/scripts/python_integration/test_crash.py
.venv/Scripts/python.exe $P/scripts/python_integration/make_compat_clips.py
.venv/Scripts/python.exe $P/scripts/python_integration/cv2_read_probe.py --tag cv2_4.12_venv
uv run --script $P/scripts/python_integration/cv2_read_probe.py --tag cv2_5.0.0.93_uv
```

Sources fetched (accessed 2026-11-09; re-fetched by the verifier into `V/src/`):
- FFmpeg n9.0.2 `libavformat/matroskaenc.c` (sha256 `087df6ac8ffaa6bbceb61c6d61aa7f0ee0f1a19cc71f73df5bd0fde6a76f3e1c`);
- OpenCV 4.12.0 `cap_ffmpeg_impl.hpp`;
- PyAV v19.0.2 `CHANGELOG.rst`.

## Appendix: revision log

**2026-11-10 (this revision)**
- The old section 5 ("Pending tonight's bench") is removed. Its three items now have results: PI-RECWRITER-AV19 → F11, F12, F13; PI-JPEG-DECODE-PYAV19 → F14; PI-NVJPEG-DECODE → F15.
- Contradicted or superseded:
  - "Defer the MKV vs fMP4 choice until the long-file cost is in". It is in: per-frame-fragment fMP4 opens about 100× slower on the same metric (implication 3); against 1 s fragments the choice rests on crash behaviour.
  - "Which decoder depends on tonight's numbers". Now simplejpeg into-buffer with `strict=False` (implication 9).
  - PyAV 18 smoke values (`R/bench/*_smoke.json`) are no longer cited. The quiet run replaces them.
  - The old reference `results/chromium_codecs/tables.md:127-130` now points at FFV1 rows. Corrected to `:37,42-45,105-119`.
- Added: the cross-topic `open_long.json` MKV miscount (F3); `flush_packets` missing from recwriter (F4, implication 3); sidecar-only fsync (F6, F11); the nvImageCodec long-path error not recurring (F9).
- Verifier corrections applied: see **Verification** below.

**2026-11-09 verification** (`R/VERIFY_provenance.prev.md`, `R/VERIFY_method.prev.md`). Corrections that were applied:
- Torn frames: a packet-level flag exists in fMP4/AVI; frame-level and cv2 flags do not (F4, F5).
- PTS error maxima corrected to 0.000498333 s (MKV) and 0.00083287 s (AVI) (F2).
- 44 codec names, not 45 (F8).
- `av1svt_mp4_vfr` seek errors corrected (F10).
- Code line numbers corrected: `opencv_get_frame.py:72`, `video_recorder.py:102`, `handle_video_recording_loop.py:24`; sfn26 Rust paths verified (F1).
- FreeMoCap killed-MKV failure moved from `int()` to `:131` / `:211` (F4).
- Narrowed:
  - MKV cluster explanation narrowed to 1 frame (F4).
  - VFR count failure narrowed per set, with the 67 ms gap disclosed (F3).
  - The G2 container left as a trade-off (implication 3).
  - Truncation counts labelled as artefacts (F5).
  - Threaded-recorder limits disclosed (F7).
  - PyAV 19 GIL benefit marked unmeasured (F7, F8).

## Verification

**Date:** 2026-11-10. **Reports:** `R/VERIFY_provenance.md` (provenance lens) and `R/VERIFY_method.md` (methodology lens); the 2026-11-09 reports are kept as `R/VERIFY_provenance.prev.md` and `R/VERIFY_method.prev.md`. Step 3 review: `R/VERIFY_step3.md`.

**What the verifiers checked**
- Provenance: every timed number in F11-F15 against the quiet-run JSON (16 recwriter phase-A rows, phases B and C, 50 decode rows, 15 nvJPEG cells, `open_long.json`), the runner-log load and Defender values, cross-topic citations and code line numbers. All timed numbers matched.
- Method: single-run handling, P-core pinning, run flags, metric scopes, buffer reuse, timing synchronisation, and the generality of each claim. One functional check (no timing): recwriter `mp4f` writes one `moof` per frame (`R/VERIFY_method.md` W11).
- The reviser re-checked each refutation before applying it (2026-11-10): the stderr file has 20,021 bare `Corrupt JPEG data` lines plus 11 `UserWarning` lines (grep); 370.83 / 77.83 = 4.76; the intra_compare `summary` has `nvjpeg_420` / `mjpeg_qsv` at SSIM-Y 0.99788 and only the `mjpeg_cpu` rows at 0.9954; `open_long.json` MKV reps are 4.93, 0.28, 0.19, 0.19, 0.19; the DLL's ProductVersion is 3.2.1; idle Defender rates are 2.60-3.40 CPU-s/min.

**Refuted and corrected**
- F14: the about 18,000 stderr warnings are not from PyTurboJPEG. There are 20,021 bare lines, inferred to come from `cv2.imdecode` (one per generic_1080p call), plus 11 PyTurboJPEG UserWarnings. The cv2 generic_1080p timings include a stderr write per call.
- F13: the MKV first-rep comparison ("4.9×") was wrong arithmetic (4.76×) and compared a start-up rep. The comparison is dropped. The 77.83 ms is relabelled as the first cv2 open in the process and the first open after write (page-cache warm), not a cold open.
- Implication 10 and flag 4: the nvJPEG target-A miss is specific to the CPU-decoded (`mjpeg_cpu`) source (SSIM-Y 0.9954). The `mjpeg_qsv`-sourced `nvjpeg_420` row reaches SSIM-Y 0.99788.

**Weak points relabelled or rescoped**
- Open metrics: phase C (open + count + first read) and open_long (open + count) are now compared like with like; the growth inference is marked cross-script; the 16-camera 6 s figure is marked serial and warm-cache (F13, implication 3).
- Implication 3 is restricted to per-frame fragments; 1 s fragments (42.57 ms) and HANDOFF.md:173 (fMP4 leading) are stated.
- F11: the ratio is given against the MKV median (2.5-6.8×) and across containers (2.5-7.8×); Defender CPU is given with the idle rate, the about 5-6 CPU-s excess, the no-write decode item, and as covering all phases.
- F11 / implication 6: phase A is an unpaced burst; the queue is now sized from the paced 16 × 1080p60 write_throughput tails.
- F12: the title is scoped to 5 paced 720p MKV cameras, one 60 s run each; the loop order is corrected (sleep, then submit); queue depth 1 means "taken off the queue", not "written".
- F14: "fastest full-size BGR decode" (PyAV native YUV is faster on two sets); the single reused buffer is disclosed; the claims are scoped to one i7-14700K on P-cores; the run noise is noted (ratio above 5× on 5 threads).
- F15: the GPU-side claim is conditional on the unverified synchronisation; the backend and host CPU time are listed as not recorded.
- F9 and tables: nvJPEG "decoded without error (output not validated; backend not recorded)"; "simplejpeg (default DCT, `strict=False`)".
- Quality paragraph and implication 9: limited to the C930e and C922 JPEGs, labelled inferred (HANDOFF.md:55-57).
- Pinning: "started with P-core affinity; affinity during the run not recorded".
- F13 per-frame fragments: relabelled measured (W11).
- Implication 9: "37% less time per call (1.58× the rate)".
- Line numbers: `recwriter.py:49-54`, `chromium_codecs/tables.md:105-119`. F4 adds 23,068,672 B = 88 × 262,144 B. libjpeg-turbo 3.2.1 now measured from the DLL version resource. The intro now names F11-F15 as new.

**Still NOT VERIFIED or not measured** (details in section 6)
- The cause of the extra lost MKV frames at a kill (unflushed buffer, inferred).
- Whether nvImageCodec's `__cuda_array_interface__` access synchronises; nvJPEG backend, host CPU cost and pixel agreement.
- The cause of the MKV 77.83 ms first open.
- That all 20,021 bare stderr lines come from cv2 (count match only).
- Camera JPEG fidelity relative to target A (inferred).
- Cold-cache and parallel opens; 16 concurrent decoders; other CPUs in the hardware target; writer threads under GIL load.
- The cause of the real-PTS MKV `recover()` rate 125/2 (inferred from timestamps, F6).
- `R/BENCH.md` §2 was corrected by GF05 (2026-11-10).

**Step 3 gap-fill (2026-11-10)**

Folded from GF01 (doc fix), GF02 (functional container matrix, no timing) and GF05 (doc fix). Each value was re-read from the evidence files before it was applied.
- §4 item 2: added GF01's cross-reference (index PTS remove jpeg_passthrough's MKV-count reason, `results/jpeg_passthrough/FINDINGS.md:568`, checked) and GF02's measured result: index PTS exact for count, 11/11 seeks and FreeMoCap in 18/18 files, including drops and 54,000 frames; real PTS break seeks even in fMP4 with drops or rate drift. GF01's "not yet tested" wording was rephrased because GF02 has since tested both cases.
- F3: added the GF02 Part A results (all 36 rows re-read from `GF02_container_matrix.json`) and noted that seek accuracy on camera-byte files is now tested for those inputs and the GF02 writer (also §6).
- §3: "cv2 count, index (CFR) PTS" row filled for fMP4 and extended for MKV; "After a hard kill: cv2 FRAME_COUNT" row extended (fMP4 = complete frames 24/24, MKV −2.767e17 24/24, re-read from `partB[].killed_cv2`); "`recover()` restores a correct count" row qualified for real-PTS MKV (consequence of the F6 addition).
- F6 and §4 item 3: added the GF02 `recover()` defect (real-PTS MKV → 125/2, 0/0, fps 62.5, about 2.1× count, 12/12; checked in `GF02_recovered_rates.txt` and `partB[].recovered_cv2`), the `recwriter.py:259` code citation (checked), and the cause as NOT VERIFIED (also §6). Added the code note that the earlier PI kills used `perf_counter_ns` timestamps (`S/test_crash.py:44-50`).
- §4 item 3: "Kill behaviour with recwriter and 1 s fragments was not tested here" replaced by the GF02 Part B kill losses and the write_throughput cross-reference (GF01 optional text; `RES/write_throughput/FINDINGS.md:96` checked). **Correction to the proposed text:** GF02's proposal and its notes say fMP4 1 s + fp lost "14–30" per kill, but the index-PTS kill at 451 lost 1 (`partB[].lost_vs_sidecar`; the report's own table gives index min 1). The range is given as 1-30.
- Stale cross-topic line numbers fixed (checked against the current `RES/crash_resilience/FINDINGS.md`): F4 `:310` → `:421` (§3B buffer row), F13 `:312` → `:423` (§3B open-fragment row), §4 item 3 `:325` → `:439` (§4 item 2).
- F14, this section and the Evidence files note: `R/BENCH.md` §2 was corrected by GF05 (line 46 re-read: 20,021 bare lines + 11 UserWarning lines). The Evidence files note (`R/BENCH.md` §2 "still attributes … to PyTurboJPEG") was stale for the same reason and was updated with it.
- Not changed: F4's NOT VERIFIED buffer cause. GF02's 1-frame MKV + fp loss used a different writer stream (`add_mux_stream`), so it was not used to settle the recwriter cause.

**Step 3 review (`R/VERIFY_step3.md`, 2026-11-10): PASS, 0 refuted, 6 weak points; all 6 re-checked by the reviser and applied**
- Evidence files: `GF02Writer` citation widened to `gf02_common.py:1-13,40-48`. Checked: the docstring runs to :13, the `CONTAINERS` dict ends at :45 (`fmp4_1s_fp`), and the in-process `rw.CONTAINERS` registration is at :46-48.
- F6: "the killed source has 30/1, 30/1" narrowed to "the 6 killed MKV + fp real files". Checked: `GF02_recovered_rates.txt` lists killed-file rates only for `mkv_fp_real`.
- F6 / §4 item 3: byte-exactness now cites the recovered-file check (`recovered_pyav.exact_prefix` = `packets` = `recover.matched_prefix`, `gf02_report.py:103-104`), recomputed from `partB[]`: 48/48. The previous parenthetical cited the matched-prefix-vs-killed-file check (also 48/48), which does not test the recovered file.
- §4 item 2: "real PTS break seeks with drops even in fMP4" widened to "with drops or rate drift (c930e full 9/11, gap60 1/11, drop50 8/11)". Checked: `partA[]` real-PTS `fmp4pf_fp` and `fmp4_1s_fp` on `c930e_full` both have `cv2_seek_exact_input` 9.
- F3 (and §6): the gap closure is scoped to "these inputs and the GF02 writer". Checked: GF02 uses `add_mux_stream` (`gf02_common.py:82`), recwriter uses an encoder stream (`S/recwriter.py:96`).
- F6 inference (and §6) reworded: the missing template rate alone does not explain 125/2, because the same `add_stream_from_template` remux gave 30/1 for index-PTS MKV (`GF02_recovered_rates.txt`) and a correct 297.0 count for the `perf_counter` real-PTS MKV kill (F4). Now: FFmpeg guesses from the timestamps; real c930e intervals on a 1 ms grid give 62.5, evenly spaced ones give 30 (inferred, NOT VERIFIED).
