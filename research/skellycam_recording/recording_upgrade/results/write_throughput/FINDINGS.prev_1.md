# write_throughput: FINDINGS (goal G5)

Topic: which recording wrapper (folder of JPEGs, raw append file + index, MKV, fragmented MP4, segmented MKV) and which writer threading model, and whether the throughput difference is big enough to give up compatibility. Machine Gerald, 2026-11-09.

Labels: **measured** (result file), **source** (primary source, accessed 2026-11-09), **code** (file:line), **inferred** (kept short, marked). `RES` = `research/skellycam_recording/recording_upgrade/results/write_throughput`, `SCR` = `research/skellycam_recording/recording_upgrade/scripts/write_throughput`.

Version rule: the implementation under test is **PyAV 19.0.2** (bundled FFmpeg 9.0.2, libavformat 63.1.102; measured: `RES/functional/pyav19.0.2_outputcontainer_api.txt`). Results made with PyAV 18.0.0 (skellycam venv) are marked **background**. **Every timing number on disk was made with PyAV 18.0.0 on a loaded machine** (`RES/BENCH.md` section 1 FLAG). Those numbers are background, contaminated and indicative only. No timing numbers were produced for this FINDINGS.

## 1. Questions answered

1. Does every wrapper store the camera JPEG (and FFV1) packets unchanged, and can standard readers open them? Yes, with PyAV 19.0.2 (section 2.1).
2. After a hard kill of the writer, how many acknowledged frames does each wrapper lose? Answered functionally with PyAV 19.0.2 (section 2.2).
3. Can the Matroska muxer be made to put every frame on disk at once from PyAV? Partly: there is no public flush call, but a workaround works in a functional test (section 2.3).
4. Can a folder of JPEGs be read with the standard image-sequence APIs? Only if the numbering has no gaps and there are no sub-folders (section 2.4).
5. Can MKV carry finer than millisecond timestamps through PyAV? No (section 2.5).
6. Is the folder layout costlier to write and handle afterwards? Background data says yes: Defender CPU, first read, copy and delete (section 2.7). The timed answer with PyAV 19 on a quiet machine is pending (section 5).

## 2. Findings

### 2.1 Round trip after a clean close (T1)

- measured (PyAV 19.0.2): 300/300 camera JPEG packets and 64/64 FFV1 packets read back byte-exact for files, append, mkv, mkv_flush, fmp4_frame, fmp4_frame_flush, fmp4_1s, fmp4_hybrid and mkvseg10 (`RES/functional/functional_results_av19.0.2.md` T1). The same holds for mkv_flush_cluster1 and fmp4_1s_flush (`RES/functional/functional_results_av19.0.2_gapfill.md` T1).
- measured (PyAV 19.0.2): for every container variant, PyAV decodes all frames, cv2 (FFMPEG backend) reads all frames, ffprobe 9.0.2 counts every packet and every packet has the keyframe flag (same files, columns `av_decoded`, `cv2_frames`, `ffprobe_packets`, `ffprobe_keyframes`).
- measured (PyAV 19.0.2): MKV stores time base 1/1000, with a pts round-trip error of up to 498.916 us (MJPEG) and 493.727 us (FFV1). fMP4 with `video_track_timescale=90000` stores 1/90000, with an error of 6.434 us (same files, `pts_max_abs_err_us`).
- measured (PyAV 19.0.2): container overhead in bytes per frame, MJPEG 720p: mkv 45.6, fmp4_frame 133.7, fmp4_1s 14.9, fmp4_hybrid 140.8, mkvseg10 52.2 (same file, `container_overhead_bytes_per_frame`).
- measured (PyAV 19.0.2): FFV1 packets inside MP4 are written and decoded by every reader (FFV1 rows, same file).
- code: the files and append writers use only Python file I/O (`open(..., "wb", buffering=0)`, `os.fsync`), not PyAV (`SCR/wt_common.py:157-219`). Their results therefore do not depend on the PyAV version.
- measured (PyAV 18.0.0, background): files_subdirs, files_fsync, files_subdirs_fsync and append_fsync1s were also 300/300 and 64/64 byte-exact (`RES/functional/functional_results.md` T1). They were not re-run under 19 because their write path has no PyAV (code, above).
- measured (PyAV 19.0.2): `add_stream("ffv1")` with the extradata set by hand stores a configuration that fails to decode (`InvalidDataError ... avcodec_send_packet()`). `add_stream_from_template` stores the 191-byte record, and frame 0 decodes identical to the template (`RES/functional/repro_pyav_add_stream_extradata_av19.0.2.json`). PyAV 18.0.0 behaves the same (background, `..._extradata.json`).

### 2.2 Hard kill of the writer process (T4: TerminateProcess, 60 fps, killed after at least 300 acknowledged frames)

- measured (PyAV 19.0.2, 2 kills per variant): acknowledged frames lost per kill (see table 3.1 for all variants): files 0, 0; append 0, 0; mkv 3, 4; mkv_flush 1, 1; mkv_flush_cluster1 1, 1; fmp4_frame 5, 5; fmp4_frame_flush 1, 1; fmp4_1s 33, 62; fmp4_1s_flush 46, 5; fmp4_hybrid 1, 4; mkvseg10 4, 5 (`RES/functional/functional_results_av19.0.2.md` T4; `..._gapfill.md` T4).
- measured (PyAV 19.0.2): fmp4_frame, fmp4_1s and fmp4_hybrid leave 1 partial packet per kill. In one fmp4_frame kill, PyAV raised `InvalidDataError ... avcodec_send_packet()` on that partial packet (298 decoded from 299 units) (`functional_results_av19.0.2.json`, T4 fmp4_frame repeat 0).
- measured (PyAV 19.0.2): in one mkvseg10 kill, the newest segment `cam00_seg0003.mkv` could not be opened by PyAV, ffprobe ("Invalid data found when processing input") or cv2 (backend None). The 363 frames in the earlier segments were byte-exact (`functional_results_av19.0.2.json`, T4 mkvseg10 repeat 1). The PyAV 18 statement "every killed file was still readable" therefore does not hold for segmented MKV under PyAV 19.
- measured (PyAV 18.0.0, background, 5 kills each): files 0 lost (1 of 5 kills left a half-written next file), files_subdirs 0, append 0, append_fsync1s 0, mkv 2-6, mkv_flush 1 every kill, mkv_flush_cluster1 1 every kill, fmp4_frame 2-5, fmp4_frame_flush 0-1, fmp4_1s 19-59, fmp4_1s_flush 2-36, fmp4_hybrid 3-6, mkvseg10 3-5 (`RES/functional/functional_results.md` T4; `functional_results_fmp4_flush.md` T4).
- measured (both versions): in every container kill the sidecar index held a record for every acknowledged frame (`idx_records` = `acked_at_kill`). The index can therefore be ahead of the container by the lost tail (same files).
- measured (PyAV 18.0.0, background): for append, an SOI scan of the raw .mjpeg without the index recovered the same frame counts, and cv2 opened the raw .mjpeg (`functional_results.md` T4, `byte_exact_without_index_soi_scan`, `cv2_frames`).
- source: Matroska muxer, FFmpeg n9.0.2 (the version PyAV 19.0.2 bundles). A new cluster starts at the next packet when `cluster_size > mkv->cluster_size_limit || cluster_time > mkv->cluster_time_limit || (codec_type == AVMEDIA_TYPE_VIDEO && keyframe && cluster_size > 4 * 1024)` (matroskaenc.c:3231-3236). Excerpt: `RES/source/ffmpeg_n9.0.2_mux_flush_excerpts.txt`, from https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/libavformat/matroskaenc.c.
- inferred: with MJPEG every frame is a keyframe of more than 4 KiB. Each frame's cluster is therefore written only when the next frame arrives, which explains why mkv_flush always loses exactly 1 frame. `cluster_size_limit=1` cannot help because the check runs on the next packet. This matches the measured 1/1 loss for mkv_flush_cluster1.
- inferred: a process kill does not lose data already passed to WriteFile (it is in the OS cache). T4 therefore tests muxer-side buffering only. Power loss is not tested (section 6).

### 2.3 Making every MKV frame reach the disk at once (open question from the investigation)

- measured (PyAV 19.0.2): `OutputContainer` exposes `mux`, `mux_one`, `close` and `start_encoding`, with no flush method (`RES/functional/pyav19.0.2_outputcontainer_api.txt`). `mux_one(None)` raises `TypeError: Argument 'packet' has incorrect type (expected av.packet.Packet, got NoneType)` (`RES/functional/mkv_flush_timebase_check_av19.0.2.json`).
- source: the cluster-flush path is `av_write_frame(s, NULL)` → `write_packet(s, NULL)` → `mkv_write_flush_packet` → `mkv_end_cluster` (mux.c:1182-1190; matroskaenc.c:3273-3288). `av_interleaved_write_frame(s, NULL)` only drains the interleaving queue (mux.c:1232-1234). Both excerpts are in `RES/source/ffmpeg_n9.0.2_mux_flush_excerpts.txt`.
- measured (PyAV 19.0.2): with an MKV writer still open (flush_packets=1, 30 frames muxed), 29 of 30 frames were on disk byte-exact. The `live=1` and `cluster_time_limit=0` options did not change this (29/30). fMP4 per-frame fragments with flush_packets=1 also gave 29/30 (`mkv_flush_timebase_check_av19.0.2.json`).
- measured (PyAV 19.0.2): muxing an empty `av.Packet()` after every MJPEG frame put every frame on disk while the writer was open: 1/1, 2/2, 10/10 and 30/30. The control without empty packets gave 0/1, 1/2, 9/10 and 29/30. In the closed file, ffprobe, PyAV demux and cv2 each saw 30 packets or frames, with 0 zero-size packets and 0 decode errors (`RES/functional/mkv_emptypkt_check_av19.0.2.json`).
- measured (PyAV 19.0.2): an empty packet with no timestamp triggers the FFmpeg warning "Timestamps are unset in a packet for stream 0. This is deprecated and will stop working in the future". The muxer then writes a size-0 block with a made-up pts (previous + 1 ms) in a new cluster (`RES/functional/mkv_emptypkt_log_av19.0.2.json`).
- measured (PyAV 19.0.2): an empty packet with an explicit pts/dts (frame pts + 1 us, time base 1/1000000) raised no exception and logged no warning. All 10/10 frames were on disk after each frame, and ffprobe listed exactly the 10 real packets (`RES/functional/mkv_emptypkt_ts_av19.0.2.json`). The only log line was an error-level `extract_extradata: Codec 'mjpeg' (7) is not supported` during the first mux. It is not attributed.
- source: FFmpeg turns a data-less packet into a 0-size refcounted packet ("Such empty packets signal EOS for the BSF API; so sanitize the packet by allocating data of size 0", mux.c:823-827). For an intra-only stream the muxer sets the keyframe flag (mux.c:820-821). That keyframe on a cluster of more than 4 KiB triggers the cluster end in matroskaenc.c:3234-3235.
- inferred: this workaround relies on how the muxer happens to behave, not on a documented API. Its kill behaviour (T4) has not been tested yet, and neither has playback of such files in Chromium.

### 2.4 Folder of JPEGs as an image sequence (T2/T3)

- measured (PyAV 19.0.2 for PyAV image2; cv2 4.12.0): `cv2.VideoCapture("<dir>/frame_%06d.jpg")` read 30/30 frames with CAP_IMAGES and with CAP_FFMPEG/CAP_ANY. With frame 10 deleted, all three APIs stopped after 10 frames. With sub-folders of 10, none of them opened (`RES/functional/functional_results_av19.0.2_t2t6.md`).
- measured (same file): CAP_IMAGES frame 0 matched `cv2.imdecode` (max abs diff 0). CAP_FFMPEG/CAP_ANY differed by up to 6 levels.
- measured (same file): PyAV image2 `sequence` read 30 packets (contiguous) and 10 packets followed by `FileNotFoundError` (gap). The `glob` pattern type fails with `NotImplementedError: [Errno 40] Function not implemented` in PyAV 19.0.2's FFmpeg on Windows. PyAV 18.0.0 gave the same results (background, `functional_results.md` T2/T3).
- measured (PyAV 18.0.0, background): 1 of 5 kills left a half-written newest JPEG file (`functional_results.md` T4, files repeat 1), so a folder reader must validate files (index record or EOI marker).

### 2.5 Timestamps in MKV

- measured (PyAV 19.0.2): setting the MKV stream `time_base` to 1/1000000 or 1/90000 before writing has no effect. After the header, and when read back, it is 1/1000, and the pts are stored as 0, 33, 67, 100, 133 for input 0, 33333, 66666, 100000, 133333 us (`RES/functional/mkv_flush_timebase_check_av19.0.2.json`, check B).
- source: FFmpeg n9.0.2 hard-codes `put_ebml_uint(pb, MATROSKA_ID_TIMECODESCALE, 1000000);` (matroskaenc.c:2613) and `// ms precision is the de-facto standard timescale for mkv files` / `avpriv_set_pts_info(st, 64, 1, 1000);` (matroskaenc.c:3602-3603) (`RES/source/ffmpeg_n9.0.2_mux_flush_excerpts.txt`).
- source: RFC 9559 section 5.1.2.9: "A TimestampScale value of 1000000 means scaled timestamps in the Segment are expressed in milliseconds" (https://www.rfc-editor.org/rfc/rfc9559.html, cited in `RES/NOTES.md` section 5).

### 2.6 Truncation (T5) and the segment muxer (T6)

- measured (PyAV 19.0.2): a cleanly closed 300-frame file cut to 50 % keeps 149 byte-exact frames for append, mkv and mkv_flush. fmp4_frame, fmp4_frame_flush and fmp4_1s keep 149 plus 1 cut packet. fmp4_hybrid keeps 0, with `InvalidDataError` because the moov is at the end after close (`functional_results_av19.0.2.md` T5).
- measured (PyAV 19.0.2): FFmpeg's `segment` muxer used through PyAV (`segment_format=matroska`, `segment_time=2`, `reset_timestamps=1`) wrote 5 files, with 300/300 packets byte-exact and time base 1/1000 (`functional_results_av19.0.2_t2t6.md` T6).

### 2.7 Reading back and file count

- measured (PyAV 19.0.2): MKV (flush_packets=1) and fMP4 (per-frame fragments + flush) both report `stream.frames = 0`. The container duration is 10.0 s for 300 frames at 30 fps, and 100/100 random `seek(pts, backward=True)` + demux reads returned the exact bytes (`RES/functional/meta_seek_check_av19.0.2.json`).
- measured (PyAV 18.0.0, background; warm cache, 27,000 frames, 1 run): random reads were 0 wrong out of 1000 for every format. The frame table took 0.009 s from the append index, against 0.442 s (mkv_flush) and 1.008 s (fmp4_frame_flush) by demux (`RES/bench/usability/usability_27000.json`).
- measured (Windows Search, read-only OLE DB query): the media folder is in the Windows Search index. Items under `.../recording_upgrade_20261109/write_throughput/payload_cache` and `.../corpus/c930e_720p_flash/frame_*.jpg` are returned, while the repo results folder returns 0 rows (`RES/wsearch_scope_check_20261109.json`). This closes the NOTES open question.
- code: the benches record MsMpEng.exe CPU (`SCR/bench_write.py:263-272`) but not SearchIndexer CPU. SearchIndexer is not referenced anywhere in `SCR/*.py` apart from the WSearch service status in `SCR/sysinfo.py:26`.

### 2.8 Background timing (PyAV 18.0.0 env, contaminated machine; indicative only)

All of the following are from `RES/BENCH.md` and were re-checked against the raw JSON in `RES/bench/*/`. During cells, system busy was 11-44 %. Other agents (camera suite, Electron harness) were running (`RES/BENCH.md` section 1). The files and append write paths do not use PyAV (code: `SCR/wt_common.py:157-219`), but the machine load still applies.

- measured (background): written = produced, 0 dropped, in all 45 timed cells (`RES/bench/*/*.json`, `summary.written`, `summary.dropped`).
- measured (background): at 16 cameras x 1080p60 (157 MB/s, thread model, 3 interleaved reps), the median write call was files 1.299 ms, append 0.179, mkv_flush 0.260 and fmp4_frame_flush 0.266 (`RES/bench/focus16/`).
- measured (background): in the same cells, MsMpEng.exe CPU per 30 s cell was files 31.7 s (26.6-33.7), append 7.1, mkv_flush 6.1 and fmp4_frame_flush 5.4 (`RES/bench/focus16/`).
- measured (background): files_fsync at 16 x 1080p60 had a write max of 1278.5 ms and p99.9 of 113.0 ms. append_fsync1s had a max of 235.0 ms (1 rep each, `RES/bench/core16_extra/`).
- measured (background): one writer process for all 16 cameras (process_shared) wrote files at a p50 of 0.262-0.279 ms, against 0.920-1.380 ms with 16 concurrent writers (`RES/bench/models16/`, `RES/bench/models16_files_rerun/`).
- measured (background): the first read of 27,000 fresh files took 116.42 s (files) and 129.79 s (files_subdirs), against 0.29-1.00 s for the one-file formats (`RES/bench/usability/usability_27000.json`). 3,000 fresh .jpg files took 11.35 s and 12.02 s of MsMpEng CPU on the first pass, and 0.117 s on the second (`RES/bench/usability/first_read_check_3000.json`).
- measured (background): copy and delete of 27,000 files took 9.96 s (shutil), 6.73 s (robocopy /MT:8) and 2.26 s (delete). The one-file formats took 0.34-0.46 s to copy and 0.12 s to delete (`usability_27000.json`).
- measured (background): the PhysicalDrive0 write-byte delta per 30 s cell (2.39-3.28 GB in the non-fsync 16-camera cells) was below the 4.71 GB written. The fsync cells were above it (5.32 and 5.73 GB) (`summary.physical_disk_delta` in each JSON). inferred: part of each non-fsync cell was still in the OS cache at the end of the cell, so 30 s cells do not show sustained device throughput.

### 2.9 Earlier studies (background, not re-measured)

- measured (earlier study, background): a hard-killed MSMF .mp4 had 0 of 300 frames readable, against 298-359 for MJPEG-in-MKV (`research/frame_ring_buffer/prototypes/results/p11_crash_container.md`).
- measured (earlier study, background): under lockstep, a stalled recorder that blocks its camera stalls every camera. The overwrite policy lost 195 frames silently during a 3.5 s stall (`research/frame_ring_buffer/prototypes/results/p3v_asymmetric_stall.md`, `p3_lossless_record.md`).
- code: the Rust prototype pipes MJPEG into an ffmpeg child that re-encodes to H.264 (libx264 ultrafast), fed through an unbounded channel (`git show upstream/sfn26:skellycam-rust/src/recording/recorder.rs` lines 1-6 and 41-43; `recording_thread.rs` lines 1-6, per `RES/NOTES.md` section 6). It is not a passthrough reference.

## 3. Comparison tables

### 3.1 Functional properties per wrapper (PyAV 19.0.2 unless marked)

| Wrapper | Byte-exact T1 | Acked frames lost per kill (19.0.2, 2 kills) | Partial unit after kill | 50 % truncation keeps | Stored time base | Files per camera | Std image-seq / container readers |
|---|---|---|---|---|---|---|---|
| files | 300/300 | 0, 0 | 1 of 5 kills (PyAV 18 run, background) | n/a | sidecar int64 ns | 1 per frame + .idx | image-seq breaks at a gap or sub-folder (2.4) |
| files_subdirs | 300/300 (background) | 0 x5 (background) | 0 (background) | n/a | sidecar | 1 per frame + .idx | not opened by image-seq APIs |
| append + .idx | 300/300 | 0, 0 | 0 | 149 | sidecar int64 ns | 2 | cv2 opens raw .mjpeg (background) |
| mkv (defaults) | 300/300 | 3, 4 | 0 | 149 | 1/1000 | 1 | PyAV, cv2, ffprobe |
| mkv_flush | 300/300 | 1, 1 | 0 | 149 | 1/1000 | 1 | PyAV, cv2, ffprobe |
| mkv_flush + empty packet per frame | 30/30 | NOT TESTED by kill; 30/30 on disk while open | NOT TESTED | NOT TESTED | 1/1000 | 1 | PyAV, cv2, ffprobe (30 packets) |
| mkv_flush_cluster1 | 300/300 | 1, 1 | 0 | 149 (background) | 1/1000 | 1 | PyAV, cv2, ffprobe |
| fmp4_frame | 300/300 | 5, 5 | 1 each (decode error once) | 149 + 1 cut | 1/90000 | 1 | PyAV, cv2, ffprobe |
| fmp4_frame_flush | 300/300 | 1, 1 | 0 | 149 + 1 cut | 1/90000 | 1 | PyAV, cv2, ffprobe |
| fmp4_1s | 300/300 | 33, 62 | 1 each | 149 + 1 cut | 1/90000 | 1 | PyAV, cv2, ffprobe |
| fmp4_1s_flush | 300/300 | 46, 5 | 0 | NOT TESTED | 1/90000 | 1 | PyAV, cv2, ffprobe |
| fmp4_hybrid | 300/300 | 1, 4 | 1 each | 0 (moov at end) | 1/90000 | 1 | PyAV, cv2, ffprobe |
| mkvseg10 (2 s in tests) | 300/300 in 5 files | 4, 5 | 0; newest segment unreadable once | NOT TESTED | 1/1000 | N | PyAV, cv2, ffprobe per segment |

Sources: `RES/functional/functional_results_av19.0.2.md`, `..._gapfill.md`, `..._t2t6.md`, `mkv_emptypkt_check_av19.0.2.json`. Background rows: `functional_results.md`.

### 3.2 Background timing at 16 cameras x 1080p60, thread model (PyAV 18.0.0 env, contaminated, 3 reps, median (min-max))

| Writer | write ms p50 | write ms p99.9 | write ms max | MsMpEng CPU s / 30 s | sys busy % |
|---|---|---|---|---|---|
| files | 1.299 (1.256-1.358) | 9.8 (7.4-39.0) | 24.1 (13.3-183.3) | 31.7 (26.6-33.7) | 25.0 (18.7-25.8) |
| append | 0.179 (0.169-0.201) | 1.1 (0.9-1.2) | 17.8 (9.8-59.6) | 7.1 (3.3-15.2) | 15.5 (14.8-19.1) |
| mkv_flush | 0.260 (0.254-0.261) | 2.4 (2.1-2.5) | 9.9 (9.0-13.1) | 6.1 (5.5-13.1) | 13.6 (12.2-17.4) |
| fmp4_frame_flush | 0.266 (0.266-0.275) | 1.5 (1.4-1.8) | 3.1 (2.8-4.7) | 5.4 (4.0-10.8) | 13.1 (11.0-13.3) |

Source: `RES/bench/focus16/*.json` via `RES/BENCH.md` section 3 (values match the raw JSON). Indicative only; must be re-measured tonight with PyAV 19.0.2.

### 3.3 Background after-recording cost, 27,000 frames, 720p30, warm cache, 1 run (PyAV 18.0.0 env, contaminated)

| Format | Files | First sequential read s | Frame table s | Copy shutil s | Delete s |
|---|---|---|---|---|---|
| files | 27001 | 116.42 | 0.060 | 9.96 | 2.26 |
| files_subdirs | 27001 | 129.79 | 0.061 | 9.83 | 2.12 |
| append | 2 | 0.29 | 0.009 | 0.34 | 0.12 |
| mkv_flush | 2 | 0.33 | 0.442 | 0.34 | 0.12 |
| fmp4_frame_flush | 2 | 1.00 | 1.008 | 0.41 | 0.12 |

Source: `RES/bench/usability/usability_27000.json`.

## 4. Implications for the plan

1. **Do not make a folder of JPEGs the default layout.** It has no crash advantage over append + index (both lost 0 frames, 2.2). Standard image-sequence readers stop at the first dropped frame (2.4), and it is the only layout with large Defender and file-count costs (2.8, background). The timed size of the cost is pending (section 5).
2. **The append + sidecar index layout is the reference for crash tolerance (G2).** It lost 0 acknowledged frames under both PyAV versions, keeps 149/150 after truncation, and has the cheapest frame table (2.2, 2.6, 2.7). It is not a standard container, so playback (G8) needs a remux or a custom reader. That is for the chromium_codecs and python_integration topics, not this one.
3. **If a standard single file is wanted, MKV with `flush_packets=1` is the best measured container.** It loses exactly 1 frame per kill, has no partial packets and keeps 149/150 after truncation (2.2, 2.6). Muxing an empty packet with an explicit timestamp after each frame removed the 1-frame lag in an open-file test (2.3). Adopt it only after a kill test and a Chromium playback test (section 5 and the chromium_codecs topic). It relies on how the muxer happens to behave (inferred, 2.3).
4. **Keep exact capture timestamps in a sidecar index, not in MKV pts.** MKV through PyAV 19.0.2 is fixed at 1 ms (2.5), with a measured error of up to 498.9 us (2.1). This matters for G9 frame-accurate sync. The sidecar index survived every kill (2.2). Readers must reconcile the index with the container, using the shorter of the two, because the index can be ahead by the lost tail (2.2).
5. **Avoid `hybrid_fragmented` and 1 s fragments for recording.** hybrid_fragmented gives 0 frames after truncation once closed (2.6). 1 s fragments lost up to 62 frames per kill (2.2). Per-frame fMP4 fragments with flush_packets=1 lose 1 frame and keep a 90 kHz time base (2.1, 2.2). In PyAV 18 they were the slowest container to index and seek (background, 2.7 / 3.3).
6. **If segment rotation is used, a reader must tolerate an unreadable newest segment.** Seen once under PyAV 19.0.2 (2.2). FFmpeg's segment muxer works through PyAV, so manual rotation is not needed (2.6).
7. **A process crash does not need fsync.** Every non-container layout lost 0 frames without it (2.2), and per-frame or periodic fsync produced the largest write stalls (2.8, background). Whether power loss needs it is untested (section 6).
8. **Build passthrough streams with `add_mux_stream` (MJPEG) or `add_stream_from_template` (FFV1 and hardware-encoded codecs), never `add_stream(codec)` + extradata.** This fails silently under PyAV 19.0.2 too (2.1).
9. **Keep the writer off the capture loop, with a bounded and counted queue.** Earlier evidence shows silent loss or stall propagation otherwise (2.9, background). Whether one writer process can serve all cameras (process_shared looked cheaper in background data, 2.8) is a tonight question.
10. **Record SearchIndexer CPU in the benches, or note it as a known confound.** The media folder is indexed (2.7), and only MsMpEng is recorded (code, 2.7). inferred: a product default under Documents would also be indexed.

## 5. Pending tonight's bench (PyAV 19.0.2 only, quiet machine)

All manifest commands in `results/bench_queue_from_wf_2e122ed0.json` call `.venv/Scripts/python.exe` (PyAV 18). They must be switched to the PyAV 19.0.2 environment, for example `uv run --no-project --python 3.12 --with av==19.0.2 --with numpy==2.2.6 --with psutil==7.2.2 --with opencv-python==4.12.0.88 python <script> ...`. That environment ran `functional_tests.py`, including its multiprocessing spawn, in this session (`..._gapfill.md`). `bench_write.py` and `run_matrix.py` have not been smoke-tested under it (NOT VERIFIED). `run_matrix.py` launches cells with `sys.executable` (code: `SCR/run_matrix.py:103`), so the environment carries through. inferred: `summarize_bench.py` globs all bench JSONs, so tonight's summary must separate rows by `env.av`, or today's PyAV 18 JSONs must be moved aside first.

| Timed question | Manifest id(s) |
|---|---|
| Machine quiet and state recorded before and after (add SearchIndexer CPU) | `sysinfo_before`, `sysinfo_after` |
| Write latency p50/p99/p99.9/max, CPU, MsMpEng CPU per wrapper at 1/4/8/16 cameras x 720p30/1080p30/1080p60 | `core` |
| Run-to-run spread at 16 x 1080p60 (files vs mkv_flush; add append and fmp4_frame_flush to match focus16) | `repeat` |
| In-loop vs thread vs process vs one shared writer process, at 4 and 16 cameras | `models` |
| Other container settings (mkv defaults, mkv_flush_cluster1, fmp4_1s, hybrid, files_subdirs_fsync) | `variants` |
| Wrapper cost for FFV1 intra packets (about 350 KB per frame) | `intra_ffv1` |
| Sustained 10-minute 16 x 1080p60: SSD cache, lazy writer, Defender steady state (30 s cells did not reach the disk, 2.8) | `long` |
| After-recording cost of a 108k-frame (1 h) recording: frame table, first read, random reads, copy, delete | `usability_1h` |
| Defender first-read cost per new file (not in the manifest; the bench runner added it) | `SCR/first_read_check.py --frames 3000` |
| Kill-loss pattern stable on a quiet machine (functional, no timing). Proposal: add an mkv_flush + empty-packet variant to `wt_common.WRITER_VARIANTS` first | `functional_rerun_quiet` |
| Write cost of the empty-packet MKV variant vs mkv_flush | not in the manifest. Needs the new variant, then `run_matrix.py --writers ...` |

## 6. Not tested / limits / NOT VERIFIED

- All timing on disk is PyAV 18.0.0 on a loaded machine (2.8). No PyAV 19.0.2 timing exists. Every throughput, latency, CPU and Defender conclusion is NOT VERIFIED for the implementation under test.
- T4 under PyAV 19.0.2 used 2 kills per variant. The PyAV 18 runs used 5. Kill ranges under 19 are therefore narrow samples.
- The empty-packet MKV flush (2.3) was tested only with an open file of up to 30 frames and a single stream. Kill test, multi-hour files, Cues growth, other readers (Chromium/Electron, FreeMoCap) and future FFmpeg behaviour are NOT VERIFIED. Why readers do not show the size-0 blocks (the demuxer is presumably skipping them) is NOT VERIFIED.
- Power-loss / OS-crash durability is not tested (it cannot be done safely here). Whether fsync is needed for that case is NOT VERIFIED.
- Simulated cameras: real camera JPEG bytes are used, but USB, driver queue and capture-API timing are not modelled. The in-loop drop rule is an assumption (`RES/NOTES.md` section 7).
- Reads are warm cache only. A cold-cache read of 108k files needs admin or a reboot.
- Defender exclusions cannot be read without admin. If the media path were excluded, the measured MsMpEng cost would understate a default install. NOT VERIFIED.
- Windows only, NTFS on one NVMe SSD. macOS/Linux file systems are NOT VERIFIED.
- files_subdirs, *_fsync and append_fsync1s functional results are PyAV 18 runs (background). Their write path does not use PyAV (code, 2.1).
- fmp4_1s_flush and mkv_flush_cluster1 truncation (T5), and mkvseg10 truncation, were not run under 19.0.2.
- Chromium/Electron playback of any wrapper is out of scope here (see chromium_codecs, G8).

## 7. How to reproduce (repo root `C:/Users/Dom/GitHub/freemocap/skellycam`)

Set `UV_CACHE_DIR` to a scratchpad folder first. Media goes to `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/write_throughput/` and is deleted by each script.

```sh
# PyAV 19.0.2 functional T1/T4/T5 (the earlier run; 2 kills per variant)
uv run --no-project --python 3.12 --with av==19.0.2 --with numpy==2.2.6 --with psutil==7.2.2 --with opencv-python==4.12.0.88 \
  python research/skellycam_recording/recording_upgrade/scripts/write_throughput/functional_tests.py --only T1,T4,T5 --repeats 2 --tag _av19.0.2
# gap fill: mkv_flush_cluster1 and fmp4_1s_flush under 19.0.2
uv run --no-project --python 3.12 --with av==19.0.2 --with numpy==2.2.6 --with psutil==7.2.2 --with opencv-python==4.12.0.88 \
  python research/skellycam_recording/recording_upgrade/scripts/write_throughput/functional_tests.py --only T1,T4 \
  --variants mkv_flush_cluster1,fmp4_1s_flush --repeats 2 --tag _av19.0.2_gapfill
# T2/T3 and T6 under 19.0.2 (PEP 723 wrapper)
uv run --script research/skellycam_recording/recording_upgrade/scripts/write_throughput/av19_checks/run_functional_av19.py --only T2,T6 --tag _av19.0.2_t2t6
# MKV cluster flush, empty packet, time base, metadata/seek (PEP 723, PyAV 19.0.2)
uv run --script research/skellycam_recording/recording_upgrade/scripts/write_throughput/av19_checks/probe_api.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/write_throughput/av19_checks/mkv_checks_av19.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/write_throughput/av19_checks/mkv_emptypkt_av19.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/write_throughput/av19_checks/mkv_emptypkt_log_av19.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/write_throughput/av19_checks/mkv_emptypkt_ts_av19.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/write_throughput/av19_checks/meta_seek_av19.py
# PyAV extradata repro under 19.0.2
uv run --no-project --python 3.12 --with av==19.0.2 --with numpy==2.2.6 --with psutil==7.2.2 \
  python research/skellycam_recording/recording_upgrade/scripts/write_throughput/repro_pyav_add_stream_extradata.py
```

- The Windows Search scope check (read-only, PowerShell) is an OLE DB `Provider=Search.CollatorDSO` query, `SELECT TOP 5 System.ItemPathDisplay FROM SYSTEMINDEX WHERE SCOPE='file:<folder>'`. The output is in `RES/wsearch_scope_check_20261109.json`.
- FFmpeg source excerpts: `RES/source/ffmpeg_n9.0.2_mux_flush_excerpts.txt`, fetched from `https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/libavformat/{matroskaenc.c,mux.c}`.
- Timed benches: the manifest commands in section 5, run with the PyAV 19.0.2 `uv run --no-project ... python` prefix instead of `.venv/Scripts/python.exe`.
