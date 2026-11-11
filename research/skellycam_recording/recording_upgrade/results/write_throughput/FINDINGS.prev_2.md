# write_throughput: FINDINGS (goal G5)

Topic: which recording wrapper to use (folder of JPEGs, raw append file + index, MKV, fragmented MP4, segmented MKV) and which writer threading model, and whether the throughput difference is big enough to give up compatibility. Machine Gerald, 2026-11-09. This version was revised after two verifier passes (section 8).

Labels: **measured** (result file), **source** (primary source, accessed 2026-11-09), **code** (file:line), **inferred** (kept short, marked). `RES` = `research/skellycam_recording/recording_upgrade/results/write_throughput`, `SCR` = `research/skellycam_recording/recording_upgrade/scripts/write_throughput`, `MEDIA` = `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/write_throughput`.

Version rule: the implementation under test is **PyAV 19.0.2**, with bundled FFmpeg 9.0.2 (measured: `RES/functional/pyav19.0.2_outputcontainer_api.txt`) and libavformat 63.1.102 (measured: `env` block of `RES/functional/functional_results_av19.0.2.md`/`.json`). Results made with PyAV 18.0.0 (skellycam venv) are marked **background**. **Every timing number on disk was made with PyAV 18.0.0 on a loaded machine** (`RES/BENCH.md` section 1 FLAG; every bench JSON has `env.av = 18.0.0`, checked in `VERIFY_provenance.md` section 4). Those numbers are background, contaminated and indicative only. No timing numbers were produced for this FINDINGS.

Reader scope: every "reader" tested here (PyAV, cv2 `CAP_FFMPEG`/`CAP_ANY`, ffprobe) is built on FFmpeg's libavformat. They are not independent. Non-FFmpeg parsers (Media Foundation, MediaInfo, mkvalidator, Chromium's own parsers) are NOT VERIFIED.

## 1. Questions answered

1. Does every wrapper store the camera JPEG (and FFV1) packets unchanged, and can FFmpeg-based readers open them? Yes, with PyAV 19.0.2 (section 2.1).
2. After a hard kill of the writer in steady state (720p60, killed at frames 300-372), how many acknowledged frames does each wrapper lose? Answered functionally with PyAV 19.0.2 (section 2.2).
3. Can the Matroska muxer be made to put every frame on disk at once from PyAV? There is no public flush call. A workaround (an empty packet after each frame) worked in an open-file test and in 3 of 3 hard kills (section 2.3).
4. Can a folder of JPEGs be read with the standard image-sequence APIs? Only if the numbering has no gaps and there are no sub-folders (section 2.4).
5. Can MKV carry finer than millisecond timestamps through PyAV? No (section 2.5).
6. Is the folder layout costlier to write and to handle afterwards? Background data says yes: more MsMpEng CPU, slower first read, copy and delete (section 2.8). That Defender causes the first-read cost is inferred. The timed answer with PyAV 19 on a quiet machine is pending (section 5).

## 2. Findings

### 2.1 Round trip after a clean close (T1)

- measured (PyAV 19.0.2): 300/300 camera JPEG packets and 64/64 FFV1 packets read back byte-exact for files, append, mkv, mkv_flush, fmp4_frame, fmp4_frame_flush, fmp4_1s, fmp4_hybrid and mkvseg10 (`RES/functional/functional_results_av19.0.2.md` T1). The same holds for mkv_flush_cluster1 and fmp4_1s_flush (`RES/functional/functional_results_av19.0.2_gapfill.md` T1).
- measured (PyAV 19.0.2): for every container variant, PyAV decodes all frames, cv2 (FFMPEG backend) reads all frames, ffprobe 9.0.2 counts every packet, and every packet has the keyframe flag (same files, columns `av_decoded`, `cv2_frames`, `ffprobe_packets`, `ffprobe_keyframes`). code: the writer sets the keyframe flag itself (`SCR/wt_common.py:305`).
- measured (PyAV 19.0.2): MKV stores time base 1/1000, with a pts round-trip error of up to 498.916 us (MJPEG) and 493.727 us (FFV1). fMP4 with `video_track_timescale=90000` stores 1/90000, with an error of 6.434 us (same files, `pts_max_abs_err_us`).
- code + inferred: part of the 6.434 us is the writer's own floor from ns to us (`SCR/wt_common.py:304`, `(tick_ns - self.first) // 1000`). The container's share is at most 5.56 us (inferred: half of 1/90000 s).
- measured (PyAV 19.0.2): container overhead in bytes per frame, MJPEG 720p: mkv 45.6, fmp4_frame 133.7, fmp4_1s 14.9, fmp4_hybrid 140.8, mkvseg10 52.2 (same file, `container_overhead_bytes_per_frame`).
- measured (PyAV 19.0.2): FFV1 packets inside MP4 are written and decoded by PyAV, cv2 and ffprobe (FFV1 rows, same file). FFV1-in-MP4 is an FFmpeg-only combination. Other readers are NOT VERIFIED.
- code: the files and append writers use only Python file I/O (`open(..., "wb", buffering=0)`, `os.fsync`), including the `_Idx` sidecar index, and no PyAV (`SCR/wt_common.py:144-220`). Their results therefore do not depend on the PyAV version.
- measured (PyAV 18.0.0, background): files_subdirs, files_fsync, files_subdirs_fsync and append_fsync1s were also 300/300 and 64/64 byte-exact (`RES/functional/functional_results.md` T1). They were not re-run under 19 because their write path has no PyAV (code, above).
- measured (PyAV 19.0.2): `add_stream("ffv1")` with the extradata set by hand stores a configuration that fails to decode (`InvalidDataError ... avcodec_send_packet()`). `add_stream_from_template` stores the 191-byte record, and frame 0 decodes identical to the template (`RES/functional/repro_pyav_add_stream_extradata_av19.0.2.json`). PyAV 18.0.0 behaves the same (background, `RES/functional/repro_pyav_add_stream_extradata.json`). code: the write path raises no error, so the failure is silent until decode (`VERIFY_provenance.md` section 4).
- measured (input provenance): the FFV1 payload cache and its template MKV were encoded with PyAV 18.0.0 (`"av": "18.0.0"` in `MEDIA/payload_cache/ffv1_1080p.json` and `ffv1_720p.json`). The FFV1 T1 rows under 19.0.2 therefore pass PyAV 18-encoded packets through PyAV 19 muxing. inferred: this does not affect a byte-passthrough check.

### 2.2 Hard kill of the writer process (T4)

Scope (code: `SCR/functional_tests.py:310-345`): TerminateProcess, one camera, 720p MJPEG (c930e), 60 fps paced, killed at least 300 acknowledged frames in plus U(0, 1.2) s, so roughly at frames 300-372. This is a steady-state kill. Kills during the header, at close, at a segment rotation (hit only by chance, see below) and with a queued backlog were not targeted.

- measured (PyAV 19.0.2, 2 kills per variant): acknowledged frames lost per kill (see table 3.1 for all variants): files 0, 0; append 0, 0; mkv 3, 4; mkv_flush 1, 1; mkv_flush_cluster1 1, 1; fmp4_frame 5, 5; fmp4_frame_flush 1, 1; fmp4_1s 33, 62; fmp4_1s_flush 46, 5; fmp4_hybrid 1, 4; mkvseg10 4, 5 (`RES/functional/functional_results_av19.0.2.md` T4; `..._gapfill.md` T4).
- measured (PyAV 19.0.2, verifier run): mkv_flush plus an empty packet with an explicit timestamp after each frame lost 0, 0, 0 acknowledged frames in 3 kills (acked 332, 340, 367; byte-exact 332, 340, 367; 0 partial units; ffprobe packet counts = acked) (`RES/functional/verify_method_emptypkt_av19.0.2.json`, `C_kills_mkv_flush_emptypkt_ts`). Script: `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/write_throughput/verify_emptypkt_av19.py` (same kill timing as T4, acked counter set after both packets are muxed).
- measured (PyAV 19.0.2): fmp4_frame, fmp4_1s and fmp4_hybrid leave 1 partial (cut) packet per kill, 6 in total. In 5 of the 6, PyAV decoded the cut JPEG with no error and cv2 returned it as a frame (`av_decoded` = `units`, `cv2_frames` = `units`). Only fmp4_frame repeat 0 raised `InvalidDataError ... avcodec_send_packet()` (298 decoded from 299 units) (`RES/functional/functional_results_av19.0.2.json` T4).
- measured (PyAV 18.0.0, background): all 15 fMP4 partial packets (fmp4_frame, fmp4_1s, fmp4_hybrid, 5 kills each) decoded with no error in PyAV and cv2 (`RES/functional/functional_results.json` T4).
- measured (PyAV 19.0.2): in one mkvseg10 kill (acked 368), the newest segment `cam00_seg0003.mkv` could not be opened by PyAV, ffprobe ("Invalid data found when processing input") or cv2 (backend None). The 363 frames in the earlier segments were byte-exact (`functional_results_av19.0.2.json`, T4 mkvseg10 repeat 1).
- code + inferred: in T4, rotation happens when `tick_ns - seg_start >= segment_ns` (`SCR/wt_common.py:295`), with `segment_ns = int(2e9)` and ticks every `int(1e9/60)` ns (`SCR/functional_tests.py:314-316`). New segments therefore start at frames 121, 242 and 363 (inferred, arithmetic). The kill at 368 came 5 frames after a rotation, and 363 is exactly the frame count of seg0000-0002.
- measured (PyAV 18.0.0, background): the nearest PyAV 18 kill came at 370, 7 frames after the rotation. That newest segment was readable, with 4 of its frames (367 byte-exact, 4 files) (`functional_results.json` T4 mkvseg10 repeat 0). Default MKV holds 2-6 frames in the muxer (mkv rows, both versions).
- inferred: a newest segment is unreadable when the kill lands within the first few frames after a rotation, before its first cluster is written. This was seen in 1 of 2 PyAV 19 kills and in none of 5 PyAV 18 kills. No PyAV 18 kill landed that early, so there is no evidence of a version difference. Cause and version dependence are NOT VERIFIED. For comparison, `RES/NOTES.md` section 4.3 (PyAV 18) says: "no killed file was unreadable; every container opened in PyAV, cv2 and ffprobe".
- measured (PyAV 18.0.0, background, 5 kills each): files 0 lost (1 of 5 kills left a half-written next file), files_subdirs 0, append 0, append_fsync1s 0, mkv 2-6, mkv_flush 1 every kill, mkv_flush_cluster1 1 every kill, fmp4_frame 2-5, fmp4_frame_flush 0-1, fmp4_1s 19-59, fmp4_1s_flush 2-36, fmp4_hybrid 3-6, mkvseg10 3-5 (`RES/functional/functional_results.md` T4; `functional_results_fmp4_flush.md` T4).
- measured (both versions): in every container kill the sidecar index held a record for every acknowledged frame (`idx_records` = `acked_at_kill`). The index can therefore be ahead of the container by the lost tail (same files).
- measured (PyAV 18.0.0, background): for append, an SOI scan of the raw .mjpeg without the index recovered the same frame counts, and cv2 opened the raw .mjpeg (`functional_results.md` T4, `byte_exact_without_index_soi_scan`, `cv2_frames`).
- source: Matroska muxer, FFmpeg n9.0.2 (the version PyAV 19.0.2 bundles). A new cluster starts at the next packet when `cluster_size > mkv->cluster_size_limit || cluster_time > mkv->cluster_time_limit || (codec_type == AVMEDIA_TYPE_VIDEO && keyframe && cluster_size > 4 * 1024)` (matroskaenc.c:3231-3236). Excerpt: `RES/source/ffmpeg_n9.0.2_mux_flush_excerpts.txt`, from https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/libavformat/matroskaenc.c.
- inferred: with MJPEG every frame is a keyframe of more than 4 KiB. Each frame's cluster is therefore written only when the next frame arrives, which explains why mkv_flush always loses exactly 1 frame. `cluster_size_limit=1` cannot help because the check runs on the next packet. This matches the measured 1, 1 loss for mkv_flush_cluster1.
- inferred: a process kill does not lose data already passed to WriteFile (it stays in the OS cache). No Microsoft primary source was fetched. It fits files/append losing 0 frames. T4 therefore tests muxer-side buffering only. This holds only because every writer here writes unbuffered (code: `SCR/wt_common.py:146,177,195`, `buffering=0`). Power loss is not tested (section 6).

### 2.3 Making every MKV frame reach the disk at once

- measured (PyAV 19.0.2): `OutputContainer` exposes `mux`, `mux_one`, `close` and `start_encoding`, with no flush method (`RES/functional/pyav19.0.2_outputcontainer_api.txt`). `mux_one(None)` raises `TypeError: Argument 'packet' has incorrect type (expected av.packet.Packet, got NoneType)` (`RES/functional/mkv_flush_timebase_check_av19.0.2.json`).
- source: the cluster-flush path is `av_write_frame(s, NULL)` → `write_packet(s, NULL)` → `mkv_write_flush_packet` → `mkv_end_cluster` (mux.c:1182-1190; matroskaenc.c:3273-3288). `av_interleaved_write_frame(s, NULL)` calls `interleaved_write_packet(s, ..., 1/*flush*/, 0)` (mux.c:1232-1234), which loops `interleave_packet` → `write_packet(s, pkt)` and never calls `write_packet(s, NULL)` (mux.c:1075-1092, n9.0.2, fetched copy in `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/write_throughput/verify_src/mux.c`). So it drains the interleaving queue without the cluster flush. mux.c:1075-1092 is not yet in `RES/source/ffmpeg_n9.0.2_mux_flush_excerpts.txt`.
- measured (PyAV 19.0.2): with an MKV writer still open (flush_packets=1, 30 frames muxed), 29 of 30 frames were on disk byte-exact. The `live=1` and `cluster_time_limit=0` options did not change this (29/30). fMP4 per-frame fragments with flush_packets=1 also gave 29/30 (`mkv_flush_timebase_check_av19.0.2.json`).
- measured (PyAV 19.0.2): muxing an empty `av.Packet()` after every MJPEG frame put every frame on disk while the writer was open: 1/1, 2/2, 10/10 and 30/30. The control without empty packets gave 0/1, 1/2, 9/10 and 29/30. In the closed file, ffprobe, PyAV demux and cv2 each saw 30 packets or frames, with 0 zero-size packets and 0 decode errors (`RES/functional/mkv_emptypkt_check_av19.0.2.json`). code: that closed-file check counts packets and frames but does not compare bytes (`SCR/av19_checks/mkv_emptypkt_av19.py`, `readers()`).
- measured (PyAV 19.0.2): an empty packet with no timestamp triggers the FFmpeg warning "Timestamps are unset in a packet for stream 0. This is deprecated and will stop working in the future". The muxer then writes a size-0 block with a made-up pts (previous + 1 ms) in a new cluster (`RES/functional/mkv_emptypkt_log_av19.0.2.json`).
- measured (PyAV 19.0.2): an empty packet with an explicit pts/dts (frame pts + 1 us, time base 1/1000000) raised no exception. All 10/10 frames were on disk after each frame, and ffprobe listed exactly the 10 real packets (`RES/functional/mkv_emptypkt_ts_av19.0.2.json`). That script kept at most 6 log lines per step (code: `SCR/av19_checks/mkv_emptypkt_ts_av19.py:41`, `[:6]`), and step 0 was filled by one error-level `extract_extradata: Codec 'mjpeg' (7) is not supported` message.
- measured (PyAV 19.0.2, verifier run, no line cap): at WARNING level, 10 frames, the control (no empty packets) and the explicit-ts empty-packet run each logged 14 lines, all `extract_extradata`, and no other lines (`RES/functional/verify_method_emptypkt_av19.0.2.json`, `A_logs_*`). The `extract_extradata` message therefore comes from MJPEG muxing under PyAV 19.0.2 / FFmpeg 9.0.2 in general, not from the workaround.
- measured (PyAV 19.0.2, verifier run): an EBML scan of the closed explicit-ts file found 11 clusters and 20 SimpleBlocks, 10 of them size 0. Each size-0 block opens a new cluster (relative timecode 0), and the next real frame follows in that cluster (relative timecode 33/34). The control had 10 clusters, 10 SimpleBlocks, 0 of size 0. ffprobe reports 10 packets, 0 of size 0, for both files (same JSON, `B_*`). So the size-0 blocks are on disk, and FFmpeg-based readers hide them.
- source: FFmpeg turns a data-less packet into a 0-size refcounted packet ("Such empty packets signal EOS for the BSF API; so sanitize the packet by allocating data of size 0", mux.c:823-827). For an intra-only stream the muxer sets the keyframe flag (mux.c:820-821). That keyframe on a cluster of more than 4 KiB triggers the cluster end in matroskaenc.c:3234-3235.
- inferred: this workaround relies on how the muxer happens to behave, not on a documented API. Non-FFmpeg parsers, Chromium/MSE handling of size-0 blocks, the extra per-frame overhead, multi-hour files and future FFmpeg versions are NOT VERIFIED.
- measured (PyAV 19.0.2): no fMP4 fragment flush (`av_write_frame(NULL)`) is reachable from PyAV either (same API listing). An equivalent empty-packet trick for fMP4 is NOT TESTED.

### 2.4 Folder of JPEGs as an image sequence (T2/T3)

- measured (PyAV 19.0.2 for PyAV image2; cv2 4.12.0): `cv2.VideoCapture("<dir>/frame_%06d.jpg")` read 30/30 frames with CAP_IMAGES and with CAP_FFMPEG/CAP_ANY. With frame 10 deleted, all three APIs stopped after 10 frames. With sub-folders of 10, none of them opened (`RES/functional/functional_results_av19.0.2_t2t6.md`).
- measured (same file): with the gap, CAP_FFMPEG and CAP_ANY still report `CAP_PROP_FRAME_COUNT` 30 while reading only 10 frames. CAP_IMAGES reports 10. The frame count is misleading as well.
- measured (same file): CAP_IMAGES frame 0 matched `cv2.imdecode` (max abs diff 0). CAP_FFMPEG/CAP_ANY differed by up to 6 levels.
- measured (same file): PyAV image2 `sequence` read 30 packets (contiguous) and 10 packets followed by `FileNotFoundError` (gap). The `glob` pattern type fails with `NotImplementedError: [Errno 40] Function not implemented` in PyAV 19.0.2's FFmpeg on Windows. PyAV 18.0.0 gave the same results (background, `functional_results.md` T2/T3).
- measured (PyAV 18.0.0, background): 1 of 5 kills left a half-written newest JPEG file (`functional_results.md` T4, files repeat 1), so a folder reader must validate files (index record or EOI marker).

### 2.5 Timestamps in MKV

- measured (PyAV 19.0.2): setting the MKV stream `time_base` to 1/1000000 or 1/90000 before writing has no effect. After the header, and when read back, it is 1/1000, and the pts are stored as 0, 33, 67, 100, 133 for input 0, 33333, 66666, 100000, 133333 us (`RES/functional/mkv_flush_timebase_check_av19.0.2.json`, check B).
- source: FFmpeg n9.0.2 hard-codes `put_ebml_uint(pb, MATROSKA_ID_TIMECODESCALE, 1000000);` (matroskaenc.c:2613) and `// ms precision is the de-facto standard timescale for mkv files` / `avpriv_set_pts_info(st, 64, 1, 1000);` (matroskaenc.c:3602-3603) (`RES/source/ffmpeg_n9.0.2_mux_flush_excerpts.txt`).
- source: RFC 9559 section 5.1.2.9: "A TimestampScale value of 1000000 means scaled timestamps in the Segment are expressed in milliseconds" (https://www.rfc-editor.org/rfc/rfc9559.html, cited in `RES/NOTES.md` section 5; quote re-checked in `VERIFY_provenance.md`).
- inferred: rounding to ±0.5 ms is far below the 16.7 ms frame interval at 60 fps, so frame identity and frame-exact seeking are not affected at 30/60 fps. What is lost is sub-millisecond cross-camera timing.

### 2.6 Truncation of a closed file (T5) and the segment muxer (T6)

T5 cuts a **cleanly closed** file once at 50 %. That is a damaged-file case, not crash evidence (a closed file has Cues and known element sizes; a killed one does not).

- measured (PyAV 19.0.2): a cleanly closed 300-frame file cut to 50 % keeps 149 byte-exact frames for append, mkv and mkv_flush. fmp4_frame, fmp4_frame_flush and fmp4_1s keep 149 plus 1 cut packet. fmp4_hybrid keeps 0, with `InvalidDataError` because the moov is at the end after close (`functional_results_av19.0.2.md` T5).
- measured (PyAV 19.0.2): FFmpeg's `segment` muxer used through PyAV (`segment_format=matroska`, `segment_time=2`, `reset_timestamps=1`) wrote 5 files, with 300/300 packets byte-exact and time base 1/1000, after a clean close (`functional_results_av19.0.2_t2t6.md` T6).
- code: T6 used `add_stream("mjpeg", rate=30)` with exact 30 fps timestamps (`SCR/functional_tests.py:384-395`), not `add_mux_stream` with jittered ticks. The segment muxer under a kill, whether `flush_packets` reaches its inner muxer, and its rotation window are NOT TESTED.

### 2.7 Reading back and file count

- measured (PyAV 19.0.2): MKV (flush_packets=1) and fMP4 (per-frame fragments + flush) both report `stream.frames = 0`. The container duration is 10.0 s for 300 frames at 30 fps, and 100/100 random `seek(pts, backward=True)` + demux reads returned the same bytes as a sequential demux at that pts (`RES/functional/meta_seek_check_av19.0.2.json`; code: `SCR/av19_checks/meta_seek_av19.py`). Equality with the source JPEGs is covered by T1.
- measured (PyAV 18.0.0, background; warm cache, 27,000 frames, 1 run): random reads were 0 wrong out of 1000 for every format. The frame table took 0.009 s from the append index, against 0.442 s (mkv_flush) and 1.008 s (fmp4_frame_flush) by demux (`RES/bench/usability/usability_27000.json`).
- measured (Windows Search, read-only OLE DB query): `SCOPE='file:C:/Users/Dom/Documents/skellycam-raw/...'` queries return rows for the media folder, for example `C:\Users\Pictures\Documents\skellycam-raw\skellycam_recording\recording_upgrade_20261109\write_throughput\payload_cache\ffv1_1080p.bin` and `...\corpus\c930e_720p_flash\frame_000000.jpg`, while the repo results folder returns 0 rows (`RES/wsearch_scope_check_20261109.json`). The displayed paths start `C:\Users\Pictures\`, not `C:\Users\Dom\`.
- measured (re-query, 2026-11-09T17:00:30): `System.ItemUrl` for the same rows is `file:C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/write_throughput/payload_cache/...`, while `System.ItemPathDisplay` shows `C:\Users\Pictures\Documents\...` (`RES/wsearch_itemurl_check_20261109.json`). So the media folder is in the Windows Search index. The display-path quirk is unexplained (NOT VERIFIED). The query shows that items exist in the index. It does not show whether files written during a bench cell are indexed while the cell runs.
- code: the benches record MsMpEng.exe CPU (`SCR/bench_write.py:263-272`) but not SearchIndexer CPU. SearchIndexer is not referenced anywhere in `SCR/*.py` apart from the WSearch service status in `SCR/sysinfo.py:26`.

### 2.8 Background timing (PyAV 18.0.0 env, contaminated machine; indicative only)

All of the following are from `RES/BENCH.md` and were re-checked against the raw JSON in `RES/bench/*/` (`VERIFY_provenance.md` section 4). During cells, system busy was 11-44 %. Other agents (camera suite, Electron harness) were running (`RES/BENCH.md` section 1). The files and append write paths do not use PyAV (code: `SCR/wt_common.py:144-220`), but the machine load still applies. There was no idle-baseline cell, and MsMpEng was already a top process before the start (`RES/BENCH.md` section 1).

- measured (background): written = produced, 0 dropped, in all 45 timed cells (`RES/bench/*/*.json`, `summary.written`, `summary.dropped`). code: the thread/process queue holds 2.87 s of frames (`SCR/bench_write.py:423`, `--ring-s` default 2.87), so even the largest stall below fitted in the queue. Drop-free does not mean stall-free.
- measured (background): at 16 cameras x 1080p60 (157 MB/s, thread model, 3 interleaved reps), the median write call was files 1.299 ms, append 0.179, mkv_flush 0.260 and fmp4_frame_flush 0.266 (`RES/bench/focus16/`).
- measured (background): in the same cells, MsMpEng.exe CPU per 30 s cell was files 31.7 s (26.6-33.7), append 7.1 (3.3-15.2), mkv_flush 6.1 and fmp4_frame_flush 5.4 (`RES/bench/focus16/`). inferred: the wide append range points to a variable background (for example other agents' file activity). SearchIndexer CPU was not recorded.
- measured (background): files_fsync at 16 x 1080p60 had a write max of 1278.5 ms and p99.9 of 113.0 ms. append_fsync1s had a max of 235.0 ms (1 rep each, `RES/bench/core16_extra/`).
- measured (background): one writer process for all 16 cameras (process_shared) wrote files at a per-call p50 of 0.262-0.279 ms, against 0.920-1.380 ms with 16 concurrent writers (`RES/bench/models16/`, `RES/bench/models16_files_rerun/`). Per-call p50 is the wrong metric for a writer that serializes 16 streams. tick->written max for files was mixed: process_shared 269.9 ms (first run) and 26.1 (18.8-33.4) ms (2 reruns); thread 274.6 ms (first run) and 75.3 (32.6-118.0) ms (2 reruns) (`RES/BENCH.md` models16 tables, lines 72, 75, 83, 84).
- measured (background): the first read of 27,000 fresh files took 116.42 s (files) and 129.79 s (files_subdirs), against 0.29-1.00 s for the one-file formats (`RES/bench/usability/usability_27000.json`). That file does not record MsMpEng CPU.
- measured (background): for 3,000 fresh .jpg files, the first pass took 11.35 s wall and 12.02 s of MsMpEng CPU; the second pass took 0.117 s wall and 0.14 s of MsMpEng CPU. The append file took 0.053 s and 0.049 s with 0.0 s MsMpEng (`RES/bench/usability/first_read_check_3000.json`, env av 18.0.0). inferred from this file: Defender scanning on first access causes most of the 116.42 s first read of 27,000 files.
- measured (background): copy and delete of 27,000 files took 9.96 s (shutil), 6.73 s (robocopy /MT:8) and 2.26 s (delete). The one-file formats took 0.34-0.46 s to copy and 0.12 s to delete (`usability_27000.json`).
- measured (background): the PhysicalDrive0 write-byte delta per 30 s cell (2.39-3.28 GB in the non-fsync 16-camera cells) was below the 4.71 GB written. The fsync cells were above it (5.32 and 5.73 GB) (`summary.physical_disk_delta` in each JSON). inferred: part of each non-fsync cell was still in the OS cache at the end of the cell, so 30 s cells do not show sustained device throughput.

### 2.9 Earlier studies (background, not re-measured)

- measured (earlier study, background): a hard-killed MSMF .mp4 had 0 of 300 frames readable, against 298-359 for MJPEG-in-MKV (`research/frame_ring_buffer/prototypes/results/p11_crash_container.md`).
- measured (earlier study, background): under lockstep, a stalled recorder that blocks its camera stalls every camera. The overwrite policy lost 195 frames silently during a 3.5 s stall (`research/frame_ring_buffer/prototypes/results/p3v_asymmetric_stall.md`, `p3_lossless_record.md`).
- code: the Rust prototype pipes MJPEG into an ffmpeg child that re-encodes to H.264 (libx264 ultrafast), fed through an unbounded channel (`git show upstream/sfn26:skellycam-rust/src/recording/recorder.rs` lines 1-6 and 41-43; `recording_thread.rs` lines 1-6; re-checked in code by `VERIFY_provenance.md`). It is not a passthrough reference.

### 2.10 Chromium playback is not a differentiator for MJPEG

- measured (other topic): Electron 35 and 45 return `DEMUXER_ERROR_NO_SUPPORTED_STREAMS` for MJPEG in mp4, fmp4, mkv and mov, and `DEMUXER_ERROR_COULD_NOT_OPEN` for avi, for both synthetic 4:2:2 MJPEG and camera MJPEG bytes (`research/skellycam_recording/recording_upgrade/results/chromium_codecs/tables.md` lines 87-96 and 127-131 onward). FFV1 in mp4/fmp4 also fails there (lines 97-100).
- inferred: for MJPEG, no wrapper gives native Chromium playback. Every layout needs a remux, a transcode or a JavaScript JPEG path for G8. The compatibility that G5 trades away is compatibility with FFmpeg/OpenCV-based tools.

## 3. Comparison tables

### 3.1 Functional properties per wrapper (PyAV 19.0.2 unless marked)

| Wrapper | Byte-exact T1 | Acked frames lost per kill (19.0.2) | Cut packet after kill | 50 % truncation of closed file keeps | Stored time base | Files per camera | FFmpeg-based readers |
|---|---|---|---|---|---|---|---|
| files | 300/300 | 0, 0 | 1 of 5 kills (PyAV 18, background) | n/a | sidecar int64 ns | 1 per frame + .idx | image-seq breaks at a gap or sub-folder (2.4) |
| files_subdirs | 300/300 (background) | 0 x5 (background) | 0 (background) | n/a | sidecar | 1 per frame + .idx | not opened by image-seq APIs |
| append + .idx | 300/300 | 0, 0 | 0 | 149 | sidecar int64 ns | 2 | cv2 opens raw .mjpeg (background) |
| mkv (defaults) | 300/300 | 3, 4 | 0 | 149 | 1/1000 | 1 | PyAV, cv2, ffprobe |
| mkv_flush | 300/300 | 1, 1 | 0 | 149 | 1/1000 | 1 | PyAV, cv2, ffprobe |
| mkv_flush + explicit-ts empty packet per frame | NOT TESTED (clean close); 30/30 on disk while open (not T1) | 0, 0, 0 (3 verifier kills, byte-exact) | 0 | NOT TESTED | 1/1000 | 1 | PyAV, cv2, ffprobe (size-0 blocks hidden) |
| mkv_flush_cluster1 | 300/300 | 1, 1 | 0 | 149 (background) | 1/1000 | 1 | PyAV, cv2, ffprobe |
| fmp4_frame | 300/300 | 5, 5 | 1 each; decoded silently 1 of 2 | 149 + 1 cut | 1/90000 | 1 | PyAV, cv2, ffprobe |
| fmp4_frame_flush | 300/300 | 1, 1 | 0 | 149 + 1 cut | 1/90000 | 1 | PyAV, cv2, ffprobe |
| fmp4_1s | 300/300 | 33, 62 | 1 each; decoded silently 2 of 2 | 149 + 1 cut | 1/90000 | 1 | PyAV, cv2, ffprobe |
| fmp4_1s_flush | 300/300 | 46, 5 | 0 | NOT TESTED (either version) | 1/90000 | 1 | PyAV, cv2, ffprobe |
| fmp4_hybrid | 300/300 | 1, 4 | 1 each; decoded silently 2 of 2 | 0 (moov at end) | 1/90000 | 1 | PyAV, cv2, ffprobe |
| mkvseg10 (2 s in tests) | 300/300 in 5 files | 4, 5 | 0; newest segment unreadable once (kill 5 frames after rotation) | NOT TESTED (either version) | 1/1000 | N | PyAV, cv2, ffprobe per segment |

Sources: `RES/functional/functional_results_av19.0.2.md`, `..._gapfill.md`, `..._t2t6.md`, `mkv_emptypkt_check_av19.0.2.json`, `verify_method_emptypkt_av19.0.2.json`. Background rows: `functional_results.md`.

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

### 3.4 Single-file container trade-off (no ranking)

| Property | mkv_flush | mkv_flush + empty packet | fmp4_frame_flush |
|---|---|---|---|
| Acked lost per kill, PyAV 19 | 1, 1 | 0, 0, 0 (verifier) | 1, 1 |
| Acked lost per kill, PyAV 18 (background) | 1 x5 | not run | 0-1 |
| Cut packet after kill | 0 | 0 | 0 |
| Stored time base | 1/1000 | 1/1000 | 1/90000 |
| Overhead B/frame (MJPEG 720p) | 45.6 | NOT MEASURED (one extra cluster + size-0 block per frame) | 133.7 (fmp4_frame) |
| Frame table, 27k frames (background) | 0.442 s | not run | 1.008 s |
| Relies on undocumented muxer behaviour | no | yes (inferred, 2.3) | no |

Sources: as in 3.1 and 3.3.

## 4. Implications for the plan

1. **Do not make a folder of JPEGs the default layout.** It has no crash advantage over append + index (both lost 0 frames, 2.2). Standard image-sequence readers stop at the first dropped frame and misreport the frame count (2.4). In background data it had about 4x the MsMpEng CPU of the one-file layouts and the slowest first read, copy and delete (2.8). That Defender causes the first-read cost is inferred (2.8). The timed size of the cost is pending (section 5).
2. **The append + sidecar index layout is the reference for crash tolerance (G2).** It lost 0 acknowledged frames under both PyAV versions and has the cheapest frame table (2.2, 2.7). It keeps 149/150 after truncating a closed file (2.6, damaged-file case). It is not a standard container, so FFmpeg/OpenCV tools need the raw-MJPEG path or a remux. For Chromium (G8), MJPEG needs a remux, transcode or JS path whatever the wrapper (2.10).
3. **For a standard single file, choose between MKV and per-frame fMP4 on the trade-off in table 3.4, not on crash loss alone.** mkv_flush and fmp4_frame_flush tie on the measured crash metrics: 1, 1 lost under PyAV 19 and 0 cut packets (2.2). fMP4 keeps a 90 kHz time base. MKV has less overhead and, in background data, a faster frame table. MKV plus an explicit-ts empty packet per frame was the only container variant with 0 lost frames (3 of 3 kills, verifier run, 2.2). It relies on undocumented muxer behaviour and writes a size-0 block and a new cluster per frame (2.3). Adopt it only after a clean-close byte-exact check, more kills and a check with non-FFmpeg parsers (section 5). Any ranking between these three is inferred.
4. **Keep exact capture timestamps in a sidecar index, not in MKV pts.** MKV through PyAV 19.0.2 is fixed at 1 ms (2.5), with a measured error of up to 498.9 us (2.1). This limits timestamp precision to ±0.5 ms. Frame-exact seeking is not affected at 30/60 fps (inferred, 2.5). The sidecar index survived every kill (2.2). Readers must reconcile the index with the container, using the shorter of the two, because the index can be ahead by the lost tail (2.2).
5. **Avoid `hybrid_fragmented` and 1 s fragments for recording.** hybrid_fragmented gives 0 frames after truncating a closed file (2.6). 1 s fragments lost up to 62 frames per kill (2.2). Per-frame fMP4 fragments with flush_packets=1 lose 1 frame and keep a 90 kHz time base (2.1, 2.2). In PyAV 18 they were the slowest container to index and seek (background, 2.7 / 3.3).
6. **Readers must not rely on decode errors to find a cut tail frame.** A cut tail JPEG was returned as a valid image in 5 of 6 PyAV 19 cases and 15 of 15 PyAV 18 cases (2.2). Check each packet's size against the sidecar index, or look for the EOI marker.
7. **If segment rotation is used, a reader must tolerate an unreadable newest segment.** It happened once, when the kill landed 5 frames after a manual rotation (2.2). There is no evidence that this is a PyAV 19 effect (inferred, 2.2). FFmpeg's segment muxer round-trips through PyAV after a clean close (2.6), but its crash behaviour is NOT VERIFIED, so it cannot yet replace manual rotation on crash-tolerance grounds.
8. **A process crash does not need fsync, provided each frame and index record is written unbuffered (or flushed) before it is acknowledged.** Every non-container layout lost 0 frames without fsync, with `buffering=0` writes (2.2). Per-frame or periodic fsync produced the largest write stalls (2.8, background). Whether power loss needs fsync is untested (section 6).
9. **Build passthrough streams with `add_mux_stream` (MJPEG) or `add_stream_from_template` (FFV1), never `add_stream(codec)` + extradata.** The latter fails silently under PyAV 19.0.2 too (2.1). That the same applies to hardware-encoded codecs is inferred and NOT VERIFIED (only FFV1 was tested).
10. **Keep the writer off the capture loop, with a bounded and counted queue.** Earlier evidence shows silent loss or stall propagation otherwise (2.9, background). No drops occurred with a 2.87 s queue, but stalls of over 1 s did (2.8, background). Whether one writer process can serve all cameras is open: per-call p50 favoured process_shared, but tick->written max was mixed (2.8, background). This is a tonight question.
11. **Record SearchIndexer CPU and an idle baseline in the benches, or note them as known confounds.** The media folder is in the Windows Search index (2.7), and only MsMpEng is recorded (code, 2.7). inferred: a product default under Documents would also be indexed.

## 5. Pending tonight's bench (PyAV 19.0.2 only, quiet machine)

All manifest commands in `research/skellycam_recording/recording_upgrade/results/bench_queue_from_wf_2e122ed0.json` call `.venv/Scripts/python.exe` (PyAV 18). They must be switched to the PyAV 19.0.2 environment, for example `uv run --no-project --python 3.12 --with av==19.0.2 --with numpy==2.2.6 --with psutil==7.2.2 --with opencv-python==4.12.0.88 python <script> ...`. That environment ran `functional_tests.py`, including its multiprocessing spawn, in this session (`..._gapfill.md`). `bench_write.py` and `run_matrix.py` have not been smoke-tested under it (NOT VERIFIED). `run_matrix.py` launches cells with `sys.executable` (code: `SCR/run_matrix.py:103`), so the environment carries through. code: `SCR/summarize_bench.py:56` and `SCR/aggregate_bench.py:32` glob every `*.json` in a set folder, so tonight's runs should go to new folders (`run_matrix.py --outdir-name ..._av19`) and the summary must separate rows by `env.av`.

Before `intra_ffv1`: move `MEDIA/payload_cache/ffv1_*` aside so the cache is rebuilt under PyAV 19.0.2. code: the cache is rebuilt only when a file is missing (`SCR/wt_common.py:99`). The current FFV1 1080p payload is 16 packets of 346-630 KB, mean about 500 KB (8,006,562 bytes / 16), and 720p is 16 packets of 168-266 KB, both encoded with PyAV 18.0.0 (measured: `MEDIA/payload_cache/ffv1_1080p.json`, `ffv1_720p.json`).

| Timed question | Manifest id(s) or command |
|---|---|
| Machine quiet and state recorded before and after (add SearchIndexer CPU) | `sysinfo_before`, `sysinfo_after` |
| Idle 30 s baseline of MsMpEng / SearchIndexer / SearchProtocolHost / SearchFilterHost CPU, before and after the focus/repeat cells | `VERIFY_method.md` section 5 request 1 (psutil one-liner appending to `RES/bench/idle_baseline_av19.jsonl`) |
| Write latency p50/p99/p99.9/max, CPU, MsMpEng CPU per wrapper at 1/4/8/16 cameras x 720p30/1080p30/1080p60 | `core` |
| 16 x 1080p60 focus cells, 4 writers, 3 reps, under PyAV 19 (replaces background `focus16`) | `uv run --no-project --python 3.12 --with av==19.0.2 --with numpy==2.2.6 --with psutil==7.2.2 --with opencv-python==4.12.0.88 python research/skellycam_recording/recording_upgrade/scripts/write_throughput/run_matrix.py --set core --cams 16 --profiles 1080p60 --writers files,append,mkv_flush,fmp4_frame_flush --reps 3 --outdir-name focus16_av19` |
| Run-to-run spread at 16 x 1080p60 (files vs mkv_flush; add append and fmp4_frame_flush to match focus16) | `repeat` |
| In-loop vs thread vs process vs one shared writer process, at 4 and 16 cameras | `models` |
| process_shared vs thread on tick->written p99/max and queue occupancy (not per-call p50), 3 reps | `uv run --no-project --python 3.12 --with av==19.0.2 --with numpy==2.2.6 --with psutil==7.2.2 --with opencv-python==4.12.0.88 python research/skellycam_recording/recording_upgrade/scripts/write_throughput/run_matrix.py --set models --writers files,append,mkv_flush --cams 16 --profiles 1080p60 --models thread,process_shared --duration 30 --reps 3 --outdir-name models16_av19_shared_vs_thread` |
| Other container settings (mkv defaults, mkv_flush_cluster1, fmp4_1s, hybrid, files_subdirs_fsync) | `variants` |
| Wrapper cost for FFV1 intra packets (1080p: 16 packets of 346-630 KB, mean about 500 KB; rebuild cache under 19.0.2 first) | `intra_ffv1` |
| Sustained 10-minute 16 x 1080p60: SSD cache, lazy writer, Defender steady state (30 s cells did not reach the disk, 2.8) | `long` |
| After-recording cost of a 108k-frame (1 h) recording: frame table, first read, random reads, copy, delete | `usability_1h` |
| Defender first-read cost per new file, 3,000 and 5,000 frames | `SCR/first_read_check.py --frames 3000`; `uv run --no-project --python 3.12 --with av==19.0.2 --with numpy==2.2.6 --with psutil==7.2.2 --with opencv-python==4.12.0.88 python research/skellycam_recording/recording_upgrade/scripts/write_throughput/first_read_check.py --frames 5000` |
| Kill-loss pattern on a quiet machine (functional, no timing), 5 kills per variant. Add an mkv_flush + explicit-ts empty-packet variant to `wt_common.WRITER_VARIANTS` first, and add kill-at-start, kill-at-rotation and kill-at-close cases | `functional_rerun_quiet` |
| Write cost of the empty-packet MKV variant vs mkv_flush | not in the manifest. Needs the new variant, then `run_matrix.py --writers ...` |

## 6. Not tested / limits / NOT VERIFIED

- All timing on disk is PyAV 18.0.0 on a loaded machine (2.8). No PyAV 19.0.2 timing exists. Every throughput, latency, CPU and Defender conclusion is NOT VERIFIED for the implementation under test.
- T4 under PyAV 19.0.2 used 2 kills per variant (3 for the empty-packet variant, verifier run). The PyAV 18 runs used 5. Kill ranges under 19 are narrow samples. All kills were steady-state at 720p60, one camera, frames about 300-372 (code, 2.2). For buffered variants, loss depends on frame size and fps; other sizes and rates are NOT TESTED.
- The empty-packet MKV flush (2.3): clean-close byte-exactness, more than 3 kills, multi-hour files, Cues growth, per-frame overhead, non-FFmpeg parsers (Chromium/Electron, Media Foundation, mkvalidator, FreeMoCap tooling) and future FFmpeg behaviour are NOT VERIFIED.
- The FFmpeg segment muxer under a kill, and whether `flush_packets` reaches its inner muxer, are NOT TESTED (2.6).
- Cause and version dependence of the unreadable newest mkvseg segment are NOT VERIFIED (inferred kill-timing window, 2.2).
- Power-loss / OS-crash durability is not tested (it cannot be done safely here). Whether fsync is needed for that case is NOT VERIFIED.
- That data passed to WriteFile survives a process kill is inferred, with no Microsoft primary source fetched (2.2).
- Simulated cameras: real camera JPEG bytes are used, but USB, driver queue and capture-API timing are not modelled. The in-loop drop rule is an assumption (`RES/NOTES.md` section 7). Bench payloads are looped (for example 19-frame 1080p sets). How Defender treats repeated content is NOT VERIFIED.
- Reads are warm cache only. A cold-cache read of 108k files needs admin or a reboot.
- Defender exclusions cannot be read without admin. If the media path were excluded, the measured MsMpEng cost would understate a default install. NOT VERIFIED.
- Why Windows Search displays the media paths as `C:\Users\Pictures\...` is NOT VERIFIED (2.7).
- Windows only, NTFS on one NVMe SSD. macOS/Linux file systems are NOT VERIFIED.
- files_subdirs, *_fsync and append_fsync1s functional results are PyAV 18 runs (background). Their write path does not use PyAV (code, 2.1).
- T5 truncation: fmp4_1s_flush and mkvseg10 were never run under either version. mkv_flush_cluster1 T5 exists only under PyAV 18 (background). The empty-packet variant has no T5.
- The FFV1 payload cache used by the PyAV 19 runs was encoded with PyAV 18.0.0 (2.1).

## 7. How to reproduce (repo root `C:/Users/Dom/GitHub/freemocap/skellycam`)

Set `UV_CACHE_DIR` to a scratchpad folder first. Media goes to `MEDIA` and is deleted by each script.

```sh
# PyAV 19.0.2 functional T1/T4/T5, 2 kills per variant.
# The command actually used for functional_results_av19.0.2.* was not recorded (NOT VERIFIED).
# The result holds these 9 variants; without --variants the script runs all 15 (functional_tests.py:470).
uv run --no-project --python 3.12 --with av==19.0.2 --with numpy==2.2.6 --with psutil==7.2.2 --with opencv-python==4.12.0.88 \
  python research/skellycam_recording/recording_upgrade/scripts/write_throughput/functional_tests.py --only T1,T4,T5 \
  --variants files,append,mkv,mkv_flush,fmp4_frame,fmp4_frame_flush,fmp4_1s,fmp4_hybrid,mkvseg10 --repeats 2 --tag _av19.0.2
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
# Verifier re-check: uncapped logs, EBML scan, 3 kills of the empty-packet variant (PEP 723, PyAV 19.0.2)
uv run --script C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/write_throughput/verify_emptypkt_av19.py
# PyAV extradata repro under 19.0.2.
# The script always writes functional/repro_pyav_add_stream_extradata.json (code: repro_pyav_add_stream_extradata.py:62),
# which is the PyAV 18 background file. Back it up first, then rename the new output by hand
# (that is how repro_pyav_add_stream_extradata_av19.0.2.json was named).
cp research/skellycam_recording/recording_upgrade/results/write_throughput/functional/repro_pyav_add_stream_extradata.json /tmp-or-scratchpad/repro_av18_backup.json
uv run --no-project --python 3.12 --with av==19.0.2 --with numpy==2.2.6 --with psutil==7.2.2 \
  python research/skellycam_recording/recording_upgrade/scripts/write_throughput/repro_pyav_add_stream_extradata.py
# then: rename the output to ..._av19.0.2.json and restore the PyAV 18 backup
```

- The Windows Search scope check (read-only, PowerShell) is an OLE DB `Provider=Search.CollatorDSO` query, `SELECT TOP 5 System.ItemPathDisplay FROM SYSTEMINDEX WHERE SCOPE='file:<folder>'` (output `RES/wsearch_scope_check_20261109.json`). The re-query adds `System.ItemUrl` and `System.ItemFolderPathDisplay` (output `RES/wsearch_itemurl_check_20261109.json`).
- FFmpeg source excerpts: `RES/source/ffmpeg_n9.0.2_mux_flush_excerpts.txt`, fetched from `https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/libavformat/{matroskaenc.c,mux.c}`. Full fetched copies (including mux.c:1075-1092): `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/write_throughput/verify_src/`.
- Timed benches: the manifest commands in section 5, run with the PyAV 19.0.2 `uv run --no-project ... python` prefix instead of `.venv/Scripts/python.exe`, writing to new `..._av19` folders.

## 8. Verification

Two verifier passes challenged the draft: `RES/VERIFY_provenance.md` (citations, numbers, sources) and `RES/VERIFY_method.md` (methodology, plus a new PyAV 19.0.2 functional run). Each refutation was re-checked against the evidence before it was applied.

### 8.1 Refuted and corrected (each re-checked)

| Draft claim | Re-check | Change |
|---|---|---|
| FFV1 intra packets "about 350 KB per frame" | measured: `MEDIA/payload_cache/ffv1_1080p.json` lists 16 packets of 345,823-629,661 bytes; `.bin` is 8,006,562 bytes (mean about 500 KB); `"av": "18.0.0"` | Corrected in section 5; PyAV 18 provenance disclosed (2.1, 6) |
| Extradata repro command reproduces the `_av19.0.2` JSON | code: output path hard-coded at `repro_pyav_add_stream_extradata.py:62`, no tag option | Section 7 now says to back up and rename by hand |
| T1/T4/T5 "earlier run" command | code: `functional_tests.py:470` runs all 15 variants without `--variants`; the result JSON (started 11:27:25) has 9 variants; `wt_common.py` modified 11:25:15 | `--variants` list added; original command marked NOT VERIFIED |
| Unreadable newest mkvseg segment is a PyAV 19 effect | code `wt_common.py:295`, `functional_tests.py:314-316`: rotations at frames 121/242/363; PyAV 19 kill at 368 (5 frames in), PyAV 18 kill at 370 (7 frames in, readable) | Restated as a kill-timing window (inferred); version effect not supported |
| Segment muxer makes manual rotation unnecessary | code `functional_tests.py:384-395`: T6 is a clean close only | Crash behaviour marked NOT VERIFIED (2.6, implication 7) |
| A standard container helps G8 playback | measured: `chromium_codecs/tables.md` lines 87-96, 127-131: MJPEG fails in every container in Electron 35 and 45 | New 2.10; implication 2 rewritten |

### 8.2 Weak claims relabelled or reworded

- libavformat version now cited to the `env` block of `functional_results_av19.0.2.*` (checked in the JSON).
- Empty-packet row: "30/30 on disk while open (not T1)"; clean-close byte-exactness NOT TESTED.
- Windows Search: displayed `C:\Users\Pictures\...` paths quoted as they are. A new `System.ItemUrl` re-query confirmed the real `C:/Users/Dom/Documents/...` path (`RES/wsearch_itemurl_check_20261109.json`).
- NOTES 4.3 now quoted exactly.
- "Best container" replaced by the trade-off table 3.4.
- "Hardware-encoded codecs" in implication 9 marked inferred / NOT VERIFIED.
- Defender as the cause of the 116.42 s first read is now labelled inferred from `first_read_check_3000.json`. Second pass corrected to 0.117 s wall / 0.14 s MsMpEng (checked in the JSON).
- Seek check reworded to "same bytes as sequential demux".
- Code range widened to `wt_common.py:144-220` (`_Idx`, `buffering=0` at lines 146, 177, 195, checked).
- mux.c:1075-1092 added for the "never calls `write_packet(s, NULL)`" claim (checked in the fetched n9.0.2 copy).
- The `extract_extradata` log is now described as capped at 6 lines (code `mkv_emptypkt_ts_av19.py:41`). The verifier's uncapped run shows it also appears without empty packets.
- T5 gaps corrected: fmp4_1s_flush and mkvseg10 were never run; mkv_flush_cluster1 only under PyAV 18.
- FFmpeg-only reader scope stated.
- Cut tail JPEGs: 5 of 6 silent under PyAV 19 and 15 of 15 under PyAV 18 (checked in both JSONs). New implication 6.
- T4 scope stated as a steady-state kill; T5 labelled as a damaged closed file, not crash evidence.
- fsync implication now conditional on unbuffered writes.
- G9 wording: ±0.5 ms precision; frame-exact seeking not affected (inferred).
- fMP4 6.434 us error: writer floor noted (code `wt_common.py:304`).
- T2 misleading `CAP_PROP_FRAME_COUNT` added (checked in `_t2t6.md`).
- 2.87 s queue noted (code `bench_write.py:423`).
- process_shared tick->written max shown as mixed (checked in `BENCH.md` lines 72, 75, 83, 84).
- Bench JSON glob relabelled as code (`summarize_bench.py:56`, `aggregate_bench.py:32`).

### 8.3 New evidence added

- measured (PyAV 19.0.2, verifier): MKV + explicit-ts empty packet lost 0 acknowledged frames in 3 of 3 kills, byte-exact. It writes one size-0 SimpleBlock and one new cluster per frame, and FFmpeg-based readers hide them (`RES/functional/verify_method_emptypkt_av19.0.2.json`; kill logic re-read in the verifier script).
- measured: Windows Search `System.ItemUrl` re-query (`RES/wsearch_itemurl_check_20261109.json`).

### 8.4 Still NOT VERIFIED

All PyAV 19.0.2 timing (section 5); the empty-packet workaround beyond 3 kills and FFmpeg readers; segment-muxer crash behaviour; cause of the unreadable segment; power-loss durability; the WriteFile-survives-kill premise (no primary source); non-FFmpeg readers; Defender exclusions; the Windows Search display-path quirk; `bench_write.py`/`run_matrix.py` under the PyAV 19 environment; macOS/Linux.
