# write_throughput (goal G5): recording wrapper, file layout and writer threading

Stage 1 notes, 2026-11-09, machine Gerald. Other agents were running at the same time, so this stage reports
**no timing, throughput or CPU numbers of its own**. Everything timing-related is a benchmark script listed in
the bench manifest (section 8), to be run later on a quiet machine. All results below are functional (does it
write, read back byte-exact, open, survive a kill) or come from cited sources and earlier studies.

Labels: **measured** (result file), **source** (primary document / library source, accessed 2026-11-09),
**code** (repo file:line), **inferred** (reasoning, kept short). Paths are relative to the repo root unless
absolute. `RES` = `research/skellycam_recording/recording_upgrade/results/write_throughput`,
`SCR` = `research/skellycam_recording/recording_upgrade/scripts/write_throughput`.

## 1. Question and answer so far

G5 asks: is a folder of JPEGs, a raw append file, or one (fragmented / segmented) container best for recording
throughput, and is the difference big enough to beat the compatibility costs?

What this stage can already say (functional evidence only):

- Every candidate wrapper stores the camera's JPEG bytes unchanged: 300 of 300 frames read back byte-exact for
  files, append+index, MKV, fragmented MP4 (per-frame fragments, 1 s fragments, hybrid; with and without
  `flush_packets`) and segmented MKV (2 s segments in the test). Measured: `RES/functional/functional_results.md` T1.
- After a hard kill of the writer process, only the formats that hand each frame to the OS with no muxer-side
  buffering kept **every acknowledged frame**: one file per frame and raw append + index. MKV and fragmented MP4
  lost a small tail of acknowledged frames. Measured: T4 (section 4.3).
- A folder of JPEGs breaks the standard image-sequence readers at the first missing frame number (one dropped frame
  ends playback at that frame). Measured: T2/T3 (section 4.2).
- Which wrapper is fastest, and whether it matters at 16 cameras x 1080p60, is **NOT VERIFIED** in this stage:
  see the benches in section 8.

## 2. Machine and storage (read-only checks)

| Item | Value | Label / evidence |
|---|---|---|
| Recording disk | WD_BLACK SN850X 4000GB, MediaType SSD, BusType NVMe, firmware 624331WD, Healthy | measured: `RES/sysinfo_stage1_20261109.json` (Get-PhysicalDisk) |
| Volume C: | NTFS, AllocationUnitSize 4096, 829.4 GB free at the snapshot (only data drive) | measured: same file (Get-Volume) |
| Media folder | `C:/Users/Dom/Documents/skellycam-raw/...` is on C: (same disk) | measured: same file (`media_dir`) |
| Defender | AntivirusEnabled, RealTimeProtectionEnabled, OnAccessProtectionEnabled, IoavProtectionEnabled, BehaviorMonitorEnabled all `true`; AMRunningMode Normal; product 4.18.26100.4; signatures 1.463.210.0 | measured: same file (Get-MpComputerStatus, not changed) |
| Defender exclusions | not readable: "N/A: Must be an administrator to view exclusions" (paths and processes) | measured: sysinfo file (Get-MpPreference, not changed) |
| Windows Search service | WSearch Status 4 (Running), StartType 2 (Automatic). Whether the media folder is indexed: NOT VERIFIED | measured: sysinfo file |
| NTFS last-access updates | "DisableLastAccess = 2 (System Managed, Last Access Time Updates ENABLED)" | measured: sysinfo file (fsutil, read-only) |
| 8.3 short names, NTFS MFT info | NOT VERIFIED: `fsutil 8dot3name query C:` returned "Error 5: Access is denied" (sysinfo file); `fsutil fsinfo ntfsinfo C:` likewise in this session | measured |
| Power plan | Balanced (381b4222-...) | measured: sysinfo file |
| Background load at snapshot | five python.exe processes at 87-141 % of one CPU over 2 s (other agents); an earlier snapshot in this session (overwritten) showed MsMpEng.exe at about 133 % | measured: sysinfo file `top_cpu_processes_2s` |
| Prior state of the same disk | 94.38 % used, 224.9 GB free on 2026-10-27; write-through stalls up to 138 ms at 70-162 MB/s | measured: `research/frame_ring_buffer/prototypes/results/p12_disk_sustained.md` |

- inferred: Defender's on-access scanning and NTFS metadata work scale with the number of files created, so the
  folder-of-JPEGs layout is where they can show up. The benches record MsMpEng.exe CPU seconds and physical-disk
  write bytes per run so this can be measured instead of assumed.

## 3. Earlier evidence reused (not re-measured)

| Claim | Label / evidence |
|---|---|
| MJPEG packet passthrough into MKV (PyAV) at 5 x 1080p60: 0 frames never grabbed, recorder 28 % CPU summed, 162.1 MB/s, versus decode + MSMF H.264 at 939 % recorder CPU | measured: `research/frame_ring_buffer/prototypes/results/p4_mjpeg_passthrough.md` |
| Unthrottled passthrough muxing reached 9,740 fps summed over 5 cameras at 1080p (one PyAV MKV writer per camera process) | measured: p4 same file, `passthrough_unthrottled` row |
| A decoupled recorder (reads the ring, own process) with passthrough: tick->written 0.8 / 1.5 / 2.9 ms median / p99 / max at 5 x 1080p60 | measured: `p8_e2e_summary.md`, row `p8_e2e_1080p_imdecode_off_passthrough.json` |
| With SkellyCam's lockstep gate kept, the decoupled prototype still held 59.82-59.95 fps with 20 / 0 frames never grabbed; a recorder thread inside the camera process (`recthread`) held 59.93 fps | measured: `p8v_e2e_summary.md` |
| Under lockstep, a stalled recorder that blocks its camera stalls every camera (block policy kept all 5 on the same 445 frames during a 3.5 s stall); overwrite policy lost 195 frames silently | measured: `p3v_asymmetric_stall.md` via `research/frame_ring_buffer/docs/frame_ring_buffer_report.md` lines 253 and 267; `p3_lossless_record.md` |
| Today the encoder runs inside the capture loop | code (cited by the ring study): `video_recorder.py` L87-109 and `opencv_camera_loop.py` L95-105 at commit 23ccbf2, `frame_ring_buffer_report.md` line 198 |
| Hard-killed writers: MSMF .mp4 0 of 300 frames readable; MJPEG-in-MKV 298 of 300 (killed idle) and 359 (killed mid-stream); NVENC fMP4 233-297 with a decode error | measured: `p11_crash_container.md` |
| Same disk, buffered writes at 162 MB/s: write() max 3.4 ms, flush at stop 0.48 s; write-through: max 134.8-137.8 ms | measured: `p12_disk_sustained.md` |

## 4. Functional results (this study)

All from `SCR/functional_tests.py` with the skellycam venv (Python 3.12.13, PyAV 18.0.0 / libavformat 62.12.102,
OpenCV 4.12.0). Full tables: `RES/functional/functional_results.md` and `.json`. Payloads: camera JPEGs from
corpus set `c930e_720p_flash` (1280x720, baseline 4:2:2, unmodified camera bytes); FFV1 version 3 intra-only
yuv422p packets made from the 16 real YUY2 1080p corpus frames (lossless repack yuyv422 -> yuv422p, verified
16 / 16 planes identical after decode; 720p by libswscale scaling), see `wt_common.build_ffv1_payload`.

### 4.1 T1 round trip (clean close)

300 MJPEG frames at 30 fps with +-2 ms tick jitter; 64 FFV1 1080p frames. Readers: own parser (files, append),
PyAV 18 demux + decode, cv2.VideoCapture (FFMPEG backend), ffprobe 9.0.2.

| Wrapper (variant) | MJPEG byte-exact | FFV1 byte-exact | Frame 0 decode == reference | cv2 / ffprobe frames | Keyframe flag on every packet | Stored time base | pts round-trip max error | Container bytes per frame | File layout |
|---|---|---|---|---|---|---|---|---|---|
| files, files_subdirs, *_fsync | 300 / 300 | 64 / 64 | n/a (bytes identical) | n/a | n/a | sidecar int64 ns | not tested (code: stored as int64 ns, `wt_common.IDX_REC`) | 0 (+ 4 KiB cluster slack per file) | 1 file per frame + .idx |
| append, append_fsync1s | 300 / 300 | 64 / 64 | n/a | MJPEG: cv2 300, ffprobe 300 (raw .mjpeg opens as an MJPEG elementary stream) | MJPEG: 300 K | sidecar int64 ns | not tested (same) | 0 | .mjpeg + .idx |
| mkv, mkv_flush, mkv_flush_cluster1 | 300 / 300 | 64 / 64 | True | 300 / 300; FFV1 64 / 64 | 300 / 300 | 1/1000 | 498.9 us (MJPEG), 493.7 us (FFV1) | 45.6 (MJPEG), 54.9 (FFV1) | one .mkv |
| fmp4_frame (and _flush) | 300 / 300 | 64 / 64 | True | 300 / 300 | 300 / 300 | 1/90000 | 6.4 us | 133.7 / 145.9 | ftyp, moov, 300 x (moof, mdat), mfra |
| fmp4_1s (and _flush) | 300 / 300 | 64 / 64 | True | 300 / 300 | 300 / 300 | 1/90000 | 6.4 us | 14.9 / 28.9 | ftyp, moov, 10 x (moof, mdat), mfra |
| fmp4_hybrid | 300 / 300 | 64 / 64 | True | 300 / 300 | 300 / 300 | 1/90000 | 6.4 us | 140.8 / 163.6 | after close: ftyp, free, mdat, moov (moov at the end) |
| mkvseg10 (2 s segments in T1) | 300 / 300 in 5 files | 64 / 64 in 2 files | True | 300 / 300 | 300 / 300 | 1/1000 | not computed | 52.2 / 65.6 | N .mkv files |

- measured: all of the above in `RES/functional/functional_results.md` T1 and `functional_results_fmp4_flush.md` T1.
- measured: FFmpeg's MP4 muxer accepted FFV1 packets in MP4 and every reader decoded them (FFV1 64 / 64 rows).
- measured: PyAV packets need `is_keyframe = True` set by the writer; with it every packet carries the K flag
  in ffprobe (column 6). Without it was not tested.
- inferred: the 0.5 ms MKV quantization is far below a 16.7 ms frame period, but it means MKV pts cannot carry
  the capture timestamps exactly; the sidecar (int64 ns) or a finer `TimestampScale` would. A non-default
  TimestampScale through PyAV was not tested (NOT VERIFIED).

### 4.2 T2/T3 a folder of JPEGs as an image sequence

30 camera JPEGs named `frame_%06d.jpg` from 0; variants: contiguous, frame 10 deleted (a dropped frame), and
10 per sub-folder.

| Layout | cv2 CAP_IMAGES | cv2 CAP_FFMPEG / CAP_ANY (backend FFMPEG) | PyAV image2 `sequence` | PyAV image2 `glob` |
|---|---|---|---|---|
| contiguous 0..29 | opens, 30 frames, frame 0 identical to cv2.imdecode (max abs diff 0) | opens, 30 frames, frame 0 max abs diff 6 vs cv2.imdecode | 30 packets | `NotImplementedError: [Errno 40] Function not implemented` |
| frame 10 missing (29 files) | 10 frames, CAP_PROP_FRAME_COUNT 10 | 10 frames, CAP_PROP_FRAME_COUNT 30 | 10 packets then `FileNotFoundError` | same NotImplementedError |
| sub-folders of 10 | does not open | does not open | `FileNotFoundError` | same NotImplementedError (also `*/frame_*.jpg`) |

- measured: `RES/functional/functional_results.md` T2/T3.
- answer to the task question: yes, `cv2.VideoCapture("<dir>/frame_%06d.jpg")` reads a JPEG folder as an image
  sequence (CAP_IMAGES or FFMPEG backend), but only for contiguous numbering in one folder; a single missing
  number ends the sequence, and sub-folders are not read. A folder recording that can drop frames needs its own
  reader (sidecar index or directory listing), not the image-sequence API.
- measured: the CAP_FFMPEG / CAP_ANY decode differs from cv2.imdecode by up to 6 levels on frame 0 (different
  JPEG decoder and colour conversion path); CAP_IMAGES matches cv2.imdecode exactly.
- measured: the FFmpeg image2 `glob` pattern type is not available in this Windows build (PyAV 18's FFmpeg).

### 4.3 T4 hard kill of the writer process

A child process writes camera JPEGs (c930e_720p_flash, looped) paced at 60 fps and publishes the number of
returned `write()` calls ("acknowledged") in shared memory; the parent waits for >= 300, waits a random 0-1.2 s,
then `Process.terminate()` (TerminateProcess: no close, no flush, no atexit). 5 kills per variant. "Lost" =
acknowledged frames not readable byte-exact; "partial" = an extra unit that exists but is not byte-exact.

| Variant | Acked frames lost per kill | Max lost | Partial units per kill | Readers agree (PyAV demux / decode / cv2 / ffprobe) |
|---|---|---|---|---|
| files | 0, 0, 0, 0, 0 | 0 | 0, 1, 0, 0, 0 (a half-written next file) | n/a |
| files_subdirs | 0, 0, 0, 0, 0 | 0 | 0 | n/a |
| append (+ index) | 0, 0, 0, 0, 0 | 0 | 0 | cv2 reads the raw .mjpeg: same counts; SOI scan without the index: same counts |
| append_fsync1s | 0, 0, 0, 0, 0 | 0 | 0 | same |
| mkv (defaults) | 6, 5, 3, 4, 2 | 6 | 0 | yes |
| mkv_flush (`flush_packets=1`) | 1, 1, 1, 1, 1 | 1 | 0 | yes |
| mkv_flush_cluster1 (+ `cluster_size_limit=1`) | 1, 1, 1, 1, 1 | 1 | 0 | yes |
| fmp4_frame (fragment per frame) | 3, 4, 5, 2, 2 | 5 | 1 each kill | yes (the partial packet is returned by PyAV demux) |
| fmp4_frame_flush (+ `flush_packets=1`) | 1, 1, 1, 1, 0 | 1 | 0 | yes |
| fmp4_1s (1 s fragments) | 35, 23, 59, 52, 19 | 59 | 1 each kill | yes |
| fmp4_1s_flush | 26, 4, 36, 2, 31 | 36 | 0 | yes |
| fmp4_hybrid (`hybrid_fragmented`) | 6, 3, 4, 3, 5 | 6 | 1 each kill | yes |
| mkvseg10 (2 s segments, defaults) | 3, 5, 3, 4, 3 | 5 | 0 | yes, summed over 3-4 segment files |

- measured: `RES/functional/functional_results.md` T4 (all variants except the two `_flush` fMP4 rows) and
  `RES/functional/functional_results_fmp4_flush.md` (fmp4_frame_flush, fmp4_1s_flush).
- measured: in every container kill the sidecar index had a record for every acknowledged frame (idx_records ==
  acked), i.e. the index can be ahead of the container by the lost tail.
- measured: no killed file was unreadable; every container opened in PyAV, cv2 and ffprobe (contrast: MSMF .mp4 0
  of 300 in p11).
- inferred: the MKV 1-frame loss with `flush_packets=1` matches the source (section 5): the cluster holding the
  newest frame is written only when the next frame arrives; `cluster_size_limit=1` cannot help because the check
  runs on the next packet. Without `flush_packets`, the AVIO buffer adds a few more frames.
- inferred: with fragmented MP4 the loss is bounded by the fragment length (1 frame per fragment for
  `frag_keyframe` with MJPEG, up to about 60 frames = 1 s for `frag_duration=1000000`), plus the AVIO buffer
  unless `flush_packets=1`.
- inferred: the earlier p11 result "MJPEG-in-MKV killed_idle 298 of 300" is the same buffering effect with PyAV
  defaults.
- measured: a kill can leave a partially written JPEG file as the newest file in the folder layout (1 of 5 kills),
  so a folder reader must validate (index record or EOI marker) rather than trust every file.

### 4.4 T5 truncation and T6 segment muxer

T5: a cleanly closed 300-frame file truncated to 50 % (stand-in for a file whose tail never reached the disk).

| Variant | Frames byte-exact after truncation | Notes |
|---|---|---|
| append (+ index) | 149 | cv2 decoded 150 (the cut last JPEG decodes with corruption, no error) |
| mkv, mkv_flush, mkv_flush_cluster1 | 149 | all readers 149, no error |
| fmp4_frame, fmp4_1s | 149 + 1 partial | readers return 150 packets/frames; the last is cut |
| fmp4_hybrid (after clean close) | 0 | `InvalidDataError`; ffprobe "moov atom not found": after close it is a normal MP4 with moov at the end |

- measured: `RES/functional/functional_results.md` T5.
- inferred: `hybrid_fragmented` protects only while recording; after a clean close the file is as fragile as a
  plain MP4 to later truncation (copy interrupted, disk full during finalisation NOT VERIFIED).

T6: FFmpeg's `segment` muxer used through PyAV (`format="segment"`, `segment_format=matroska`, `segment_time=2`,
`reset_timestamps=1`) with MJPEG packet passthrough wrote 5 files, 300 / 300 packets byte-exact. Measured: T6.
So segmenting does not need manual rotation in Python; the benches use manual rotation (`mkvseg10`) to time the
close/open cost inside the writer.

### 4.5 PyAV passthrough API finding (affects G4 too)

- measured: with PyAV 18.0.0, `add_stream("ffv1")` + setting `codec_context.extradata` stored a different
  configuration record than the source encoder's, and decoding the passthrough packets failed with
  `InvalidDataError ... avcodec_send_packet()`; `add_stream_from_template(<template stream>)` stored the 191-byte
  record and frame 0 decoded identical to the template. Same result with PyAV 19.0.2 (libavformat 63.1.102).
  `RES/functional/repro_pyav_add_stream_extradata.json`, `..._av19.0.2.json`; script `SCR/repro_pyav_add_stream_extradata.py`.
- measured: the first T1 attempt with `add_stream` produced FFV1 MKV/MP4 files that every reader opened but that
  decoded with "quant_table_index out of range" errors from FFmpeg (the stored extradata was 43 bytes instead of
  191), i.e. the failure is silent unless the decode is compared. Seen in this session's first T1 log; the scripts
  now use `add_mux_stream` (MJPEG, no tables needed outside the JPEG) and `add_stream_from_template` (FFV1).
- inferred: any passthrough recorder for codecs with out-of-band configuration (FFV1 v3, H.264/HEVC/AV1 from a
  hardware encoder) must build the output stream from the encoder's parameters, not from `add_stream(codec)`.
- PyAV 19.0.2 did not change this behaviour, so it is not a reason to bump for wrappers (measured, same files).
  The repro under 19.0.2 ran via `uv run --no-project --python 3.12 --with av==19.0.2 --with numpy==2.2.6 --with psutil==7.2.2`
  with UV_CACHE_DIR in the scratchpad; its env record also shows cv2 4.12.0 importable from outside the ephemeral
  env (not used by the repro).

### 4.6 Version bump check: PyAV 19.0.2 (newest on PyPI)

- measured: T1, T4 (2 kills per variant) and T5 re-run in an isolated env (`uv run --no-project --python 3.12
  --with av==19.0.2 --with numpy==2.2.6 --with psutil==7.2.2 --with opencv-python==4.12.0.88`, libavformat
  63.1.102): same byte-exact round trips for all 9 tested variants and both payloads, same time bases and pts
  errors (498.9 us MKV, 6.4 us MP4), same kill pattern (files / append 0 lost; mkv 3-4; mkv_flush 1;
  fmp4_frame 5 + 1 partial; fmp4_frame_flush 1; fmp4_1s 33-62; hybrid 1-4; mkvseg10 4-5), same T5 results.
  `RES/functional/functional_results_av19.0.2.md`.
- inferred: for wrapper choice and crash behaviour, PyAV 19.0.2 gives no functional gain over the pinned 18.0.0;
  write throughput under 19.0.2 is not benchmarked (can be added with the same uv command around
  `bench_write.py` if another topic wants the bump).

### 4.7 Usability smoke (functional parts only)

From a 2,000-frame smoke run of `SCR/bench_usability.py` (timing columns discarded; JSON kept only in the scratchpad):

- measured: frame-accurate random access by index worked for every format: 0 wrong frames out of 200 random
  reads each for files, files_subdirs, append+index, MKV, fMP4 (1 s and per-frame fragments) and MKV with
  `cluster_size_limit=1` (PyAV `seek(pts, backward=True)` then demux to the exact pts).
- measured: `stream.frames` is 0 for both MKV and fragmented MP4 in PyAV, so the frame count of a container needs
  a full demux pass (or a sidecar index); the container `duration` is present (66.666 s for 2,000 frames at 30 fps).
- measured: on-disk allocation with 4 KiB clusters was 113.58 MB for 2,000 JPEG files vs 110.75-111.01 MB for
  single-file formats holding the same 110.75 MB of payload (about 2.5 % slack for the folder, computed as file
  sizes rounded up to 4096; NTFS MFT records not counted).
- measured: robocopy returned exit code 1 for every copy, which Microsoft documents as "All files were copied
  successfully." (source: https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/robocopy, exit codes table).
- code: Python 3.12's `shutil.copy2` uses `_winapi.CopyFile2` on Windows
  (`C:/Users/Dom/AppData/Roaming/uv/python/cpython-3.12-windows-x86_64-none/Lib/shutil.py:453-460`), so
  `copytree` of 108k files makes 108k CopyFile2 calls (inferred from the code path).

## 5. Source facts that drive the design

| Fact | Label / evidence |
|---|---|
| FFmpeg's Matroska muxer writes blocks into an in-memory cluster buffer (`cluster_bc`) and writes the cluster to the file in `mkv_end_cluster`; a new cluster starts, at the next packet, when `cluster_size > cluster_size_limit`, `cluster_time > cluster_time_limit`, or a video keyframe arrives with `cluster_size > 4 * 1024` | source: FFmpeg `libavformat/matroskaenc.c` at tag n8.0, functions `mkv_write_packet`, `mkv_write_packet_internal`, `mkv_end_cluster` (https://raw.githubusercontent.com/FFmpeg/FFmpeg/n8.0/libavformat/matroskaenc.c). PyAV 18's libavformat 62.12.102 is newer than n8.0: identical logic NOT VERIFIED |
| Default cluster limits: "start a new cluster every 5 MB or 5 sec" (seekable output: 5000 ms / 5 MiB) | source: same file, end of `mkv_write_header` |
| Only audio packets are held back one packet in the Matroska muxer ("buffer an audio packet to ensure the packet containing the video keyframe's timecode is contained in the same cluster for WebM") | source: same file, `mkv_write_packet` |
| inferred from the two rows above: with MJPEG (every frame a keyframe, > 4 KiB) each cluster holds one frame and is written when the next frame arrives, so the newest acknowledged frame is always only in memory; this matches T4 (MKV with `flush_packets=1` lost 1 acked frame) | inferred |
| Matroska `TimestampScale` default 1000000: "A TimestampScale value of 1000000 means scaled timestamps in the Segment are expressed in milliseconds" | source: RFC 9559 section 5.1.2.9 (https://www.rfc-editor.org/rfc/rfc9559.html) |
| measured consequence: MKV pts round trip error up to 498.9 us (ms quantization) vs 6.4 us for MP4 with `video_track_timescale=90000` | measured: T1 `pts_max_abs_err_us` |
| Seeking without Cues: "It is possible to seek without this element, but it is much more difficult" | source: RFC 9559 (Cues) |
| FFmpeg mp4 muxer options: `frag_keyframe`, `frag_every_frame`, `empty_moov`, `default_base_moof`, `frag_duration`, and `hybrid_fragmented` = "For recoverability, write a fragmented file that is converted to non-fragmented at the end." | source: `ffmpeg -h muxer=mp4` from ffmpeg 9.0.2, saved as `RES/source/ffmpeg9.0.2_h_muxer_mp4.txt` lines 12-45 |
| Matroska muxer options `cluster_size_limit`, `cluster_time_limit` (default -1 = muxer default), `live`, `reserve_index_space`, `cues_to_front` | source: `RES/source/ffmpeg9.0.2_h_muxer_matroska.txt` lines 8-17 |
| `flush_packets`: "enable flushing of the I/O context after each packet (from -1 to 1) (default -1)" | source: `RES/source/ffmpeg9.0.2_h_full_format_flush.txt` |
| Segment muxer: `segment_time` default 2, `segment_format`, `reset_timestamps`, `segment_list` | source: `RES/source/ffmpeg9.0.2_h_muxer_segment.txt` |
| image2 demuxer options (pattern types) | source: `RES/source/ffmpeg9.0.2_h_demuxer_image2.txt` |
| `os.fsync`: "on Windows, the MS `_commit()` function" | source: https://docs.python.org/3.12/library/os.html (os.fsync) |
| FlushFileBuffers "can be inefficient when used after every write to a disk drive device when many writes are being performed separately"; Microsoft recommends unbuffered I/O (FILE_FLAG_NO_BUFFERING + FILE_FLAG_WRITE_THROUGH) instead | source: https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-flushfilebuffers (Remarks) |
| `time.sleep` on Windows: "On Windows 8.1 and newer the implementation uses a high-resolution timer which provides resolution of 100 nanoseconds"; `perf_counter` "is system-wide" (the benches compare perf_counter_ns ticks across processes) | source: https://docs.python.org/3.12/library/time.html |
| robocopy `/mt:<n>` "Creates multi-threaded copies with n threads ... The default value for n is 8." | source: robocopy page above |

- inferred: a process crash does not lose data already passed to WriteFile (it sits in the OS cache); only power
  loss / OS crash needs fsync. T4 is a process kill, so it tests the first case only. Power-loss behaviour is
  NOT VERIFIED and cannot be tested here.

## 6. Rust reference (upstream/sfn26 skellycam-rust)

- code: each camera is recorded by an ffmpeg child process "fed MJPEG frames via stdin" that "decodes them, and
  re-encodes to H.264" (`git show upstream/sfn26:skellycam-rust/src/recording/recorder.rs` lines 1-6), default
  output codec libx264 preset ultrafast (same file lines 41-43).
- code: a recording thread owns the recorders and receives frames "via an unbounded `mpsc::channel()`, so the
  dispatcher never blocks on ffmpeg pipe writes or CSV fsyncs" (`recording_thread.rs` lines 1-6).
- inferred: the Rust design is the "writer off the capture path" model (thread + queue), with an unbounded queue;
  the Python plan should keep the decoupling but use a bounded, counted queue (p3 shows why: silent loss or
  unbounded growth otherwise). It re-encodes, so it is not a passthrough reference for G1/G5.

## 7. Benchmark design (scripts written, smoke-tested, not reported)

| Script | Purpose |
|---|---|
| `SCR/wt_common.py` | corpus payloads, writers (files, append, mkv, fmp4, mkvseg), sidecar index, readers |
| `SCR/functional_tests.py` | T1-T6 above (functional) |
| `SCR/repro_pyav_add_stream_extradata.py` | section 4.5 repro |
| `SCR/bench_write.py` | one bench cell: writer x cameras x profile x threading model x payload |
| `SCR/run_matrix.py` | runs named sets of cells one by one (resumable), then `summarize_bench.py` |
| `SCR/summarize_bench.py` | builds `RES/bench/bench_summary.md` from all JSONs |
| `SCR/bench_usability.py` | enumerate / open / read / random access / copy / delete of a 108k-frame recording |
| `SCR/sysinfo.py` | read-only machine snapshot (disk, Defender, search service, power plan, top CPU, nvidia-smi) |

Writer variants (`wt_common.WRITER_VARIANTS`): `files` (open/write/close per frame, unbuffered), `files_subdirs`
(1,000 files per sub-folder), `files_fsync` / `files_subdirs_fsync` (os.fsync before close), `append` (one
unbuffered WriteFile per frame + 32-byte index record per frame), `append_fsync1s` (fsync of data + index every
1 s), `mkv`, `mkv_flush` (`flush_packets=1`), `mkv_flush_cluster1` (+ `cluster_size_limit=1`), `fmp4_frame`
(`frag_keyframe+empty_moov+default_base_moof`, one fragment per frame), `fmp4_1s` (`frag_duration=1000000`),
`fmp4_frame_flush` / `fmp4_1s_flush` (+ `flush_packets=1`), `fmp4_hybrid` (`movflags=hybrid_fragmented`), `mkvseg10` (new MKV every 10 s, manual rotation). Every writer
also writes the 32-byte per-frame sidecar index (frame, tick ns, offset, size) with one unbuffered write, so all
variants pay the same timestamp cost.

Load profiles: 720p30 (cameras alternate c930e_720p_flash 891 frames / c922_720p_flash 893 frames, looped),
1080p30 (c922_1080p / c930e_1080p, 19 frames each, looped), 1080p60 (the same 1080p frames sent at 60 fps:
no 1080p60 capture exists in the corpus), 720p60 (c922_720p60, 10 frames). FFV1 payload: 16 packets looped.

Threading models (`bench_write.py --model`): `inloop` (write inside the camera loop; a tick is dropped when more
than `--inloop-buffer` = 1 ticks elapsed while busy: a modelling assumption, not a measured driver behaviour),
`inloop_lockstep` (+ a two-phase multiprocessing.Barrier per frame across all cameras, a stand-in for SkellyCam's
gate; the barrier itself costs time, so compare with `inloop`), `thread` (one writer thread per camera process,
bounded queue of 2.87 s, explicit counted drops), `process` (shared-memory ring per camera, one writer process per
camera), `process_shared` (one writer process for all cameras). Each camera is its own process (spawn), like
SkellyCam.

Metrics per cell (JSON): per-frame write-call latency p50/p99/p99.9/max (pooled and worst camera), tick->written
latency, grab lateness (shows in-loop stalls), produced / written / dropped / late ticks, close time, bench CPU
(process_time, thread_time), system busy %, MsMpEng.exe CPU seconds (readable without admin: smoke run returned
a float), PhysicalDrive write bytes, files created, sustained MB/s vs nominal MB/s.

Smoke tests run (2-3 s cells, outputs deleted, numbers not used): the first 12 writer variants x thread model x
1 camera 1080p30; fmp4_frame_flush and fmp4_1s_flush x inloop_lockstep x 2 cameras 1080p60; MKV x all 5 models x 2 cameras 720p30; FFV1 MKV x process model x 2 cameras; files x process
x 16 cameras 1080p60; `run_matrix.py --set smoke`; `bench_usability.py --frames 2000`. All completed with
produced == written and 0 drops; their JSONs were deleted from `RES/bench/` to keep stage-1 timing out of the repo.

## 8. Bench manifest (run on a quiet machine, one at a time, from the repo root)

| id | priority | est. min | command (repo root) |
|---|---|---|---|
| sysinfo_before | 1 | 1 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/write_throughput/sysinfo.py` |
| usability_1h | 1 | 30 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/write_throughput/bench_usability.py --frames 108000 --robocopy` |
| models | 1 | 40 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/write_throughput/run_matrix.py --set models` |
| core | 1 | 75 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/write_throughput/run_matrix.py --set core` |
| variants | 2 | 10 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/write_throughput/run_matrix.py --set variants` |
| intra_ffv1 | 2 | 12 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/write_throughput/run_matrix.py --set intra` |
| repeat | 2 | 8 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/write_throughput/run_matrix.py --set repeat` |
| long | 2 | 35 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/write_throughput/run_matrix.py --set long` |
| sysinfo_after | 1 | 1 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/write_throughput/sysinfo.py` |
| functional_rerun | 3 | 45 | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/write_throughput/functional_tests.py --tag _quiet` (functional only; checks T4 is stable) |

Same commands as the structured manifest. Order: sysinfo -> usability -> models ->
core -> variants -> intra -> repeat -> long -> sysinfo. Each command writes JSON under `RES/bench/` and
`run_matrix.py` regenerates `RES/bench/bench_summary.md`. Media goes to
`C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/write_throughput/` and is
deleted after each cell (`bench_runs/current`, `usability/`). Disk guard: a cell refuses to start unless free space
> 2 x its estimate + 50 GB (a long cell writes about 94 GB before deletion: 16 cameras x 60 fps x 600 s x the
133 / 192 KB median 1080p frame sizes of corpus/index.json, arithmetic).

What each set decides (inferred, to be confirmed by the numbers):

- `models`: whether writing inside the capture loop shows grab lateness / drops at 4 and 16 cameras x 1080p60
  for each wrapper, and whether one writer process can serve 16 cameras.
- `core` uses the crash-tolerant container settings from T4 (`mkv_flush`, `fmp4_frame_flush`); `variants`
  times the other container settings. `core` decides whether files vs append vs MKV vs fMP4 vs segments differ in p99.9/max write latency, CPU or MsMpEng CPU
  at the target loads; `files_fsync` shows the cost of per-frame durability.
- `long`: 10-minute sustained 16 x 1080p60 (past the SSD cache and Defender steady state; p12 saw stalls only
  in write-through mode).
- `usability`: the after-recording cost of 108k files vs one file (copy, delete, frame table).

## 9. Limits and open questions

- No timing numbers from this stage (concurrent agents). All performance conclusions wait for the bench run.
- Warm cache only for reads in `bench_usability.py` (the OS standby list cannot be flushed without admin).
- Simulated cameras: payload bytes are real camera JPEGs, but the capture API, USB timing and driver queues are
  not modelled; `inloop` drop rule is an assumption.
- Process kill only; power-loss durability NOT VERIFIED.
- T4 covers PyAV 18 / libavformat 62.12.102 on Windows; other platforms NOT VERIFIED.
- Whether the media folder under Documents is indexed by Windows Search (WSearch is running) NOT VERIFIED; it may
  add load during the folder-of-JPEGs benches.
- Defender exclusions are unknown (admin needed); the bench does not change them.
- PyAV has no call here to force the Matroska muxer to end a cluster after each packet (libavformat's
  `mkv_write_flush_packet` exists in the source); whether PyAV exposes a NULL-packet flush is NOT VERIFIED.
