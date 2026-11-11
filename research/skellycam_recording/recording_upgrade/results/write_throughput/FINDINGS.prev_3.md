# write_throughput: FINDINGS (goals G5 and G1 storage layout)

Topic: which recording wrapper to use and which writer threading model. The wrappers are a folder of JPEGs, a raw append file + index, MKV, fragmented MP4 and segmented MKV. The topic also asks whether the throughput difference is big enough to give up compatibility. Machine Gerald. Functional work was done 2026-11-09. Timed numbers come from the quiet overnight run `20261109T230007` (2026-11-09 23:00 to 2026-11-10 05:36). This version replaces every contaminated or "pending tonight" timing entry (section 8 lists the changes). It was revised after two verifier passes (section 9).

Labels: **measured** (result file), **source** (primary source, accessed 2026-11-09), **code** (file:line), **inferred** (kept short, marked). Path prefixes:
- `RES` = `research/skellycam_recording/recording_upgrade/results/write_throughput`
- `SCR` = `research/skellycam_recording/recording_upgrade/scripts/write_throughput`
- `RU` = `research/skellycam_recording/recording_upgrade`
- `MEDIA` = `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/write_throughput`

**Version rule.** The implementation under test is **PyAV 19.0.2**, with bundled FFmpeg 9.0.2 (measured: `RES/functional/pyav19.0.2_outputcontainer_api.txt`) and libavformat/libavcodec 63.1.102.
- measured: the `env` block of every timed JSON cited here says `av` 19.0.2 and libavformat [63, 1, 102]. That covers 77 write cells, `first_read_check_5000.json` and `usability_18000.json`.
- Results made with PyAV 18.0.0 (skellycam venv) or in the contaminated daytime run (`RES/BENCH_20261109_contaminated.md`) are marked **background**.

**Quality target.** Nothing in this topic depends on target A or B.
- code: every write cell stores the corpus camera JPEG bytes unchanged; nothing is encoded (`SCR/bench_write.py:7-11`).
- measured (other topic): the camera JPEGs' quantisation tables are nearest IJG q94 (`RU/results/intra_compare/camera_jpeg_quality.md`).
- inferred (RU/HANDOFF.md section 1.1): the camera JPEGs are about target A. HANDOFF line 182 notes that the cameras' 1080p JPEGs are much smaller than libjpeg-turbo q94 on the same models' YUY2 frames (cause not answered).
- inferred: a re-encoded stream at target B would have smaller frames and lower MB/s. That case was not benched.

**Reader scope.** Every "reader" tested here (PyAV, cv2 `CAP_FFMPEG`/`CAP_ANY`, ffprobe) is built on FFmpeg's libavformat, so they are not independent. Non-FFmpeg parsers are NOT VERIFIED: Media Foundation, MediaInfo, mkvalidator and Chromium's own parsers.

**Machine scope.** Every timed number is from one i7-14700K limited to 16 P-core logical CPUs, with one WD_BLACK SN850X NVMe and Defender on (`RES/BENCH.md` header; section 5). Other CPU and disk classes in the hardware target (RU/HANDOFF.md section 1 item 3, "most CPUs from 2020 on") are NOT VERIFIED.

## 1. Questions answered

1. Does every wrapper store the camera JPEG (and FFV1) packets unchanged, and can FFmpeg-based readers open them?
   - Yes, with PyAV 19.0.2 (2.1).
2. After a hard kill of the writer in steady state (720p60, killed at frames 300-372), how many acknowledged frames does each wrapper lose?
   - Answered functionally with PyAV 19.0.2 (2.2).
3. Can the Matroska muxer be made to put every frame on disk at once from PyAV?
   - There is no public flush call.
   - A workaround, an empty packet after each frame, worked in an open-file test and in 3 of 3 hard kills (2.3).
4. Can a folder of JPEGs be read with the standard image-sequence APIs?
   - Only if the numbering has no gaps and there are no sub-folders (2.4).
5. Can MKV carry finer than millisecond timestamps through PyAV?
   - No (2.5).
6. On a quiet machine with PyAV 19.0.2, does any wrapper fail to keep up?
   - Tested up to 16 cameras x 1080p60 (156.9 MB/s), including 10 minutes sustained.
   - No: 0 frames dropped in 77 of 77 cells (2.8).
7. What does each layout cost per write, in CPU and in Defender real-time scanning?
   - Answered in 2.8 to 2.10.
   - Inside the timed window, the folder of JPEGs is the only layout with a Defender cost above the idle level (2.9).
8. Is one shared writer process for all cameras better than a writer thread per camera?
   - Answered for 16 x 1080p60 (2.11).
9. What does each layout cost after recording: frame table, first read, random reads, copy and delete?
   - Answered for an 18,000-frame recording and a 5000-file first read (2.12).

## 2. Findings

### 2.1 Round trip after a clean close (T1), functional

- measured (PyAV 19.0.2): 300/300 camera JPEG packets and 64/64 FFV1 packets read back byte-exact for files, append, mkv, mkv_flush, fmp4_frame, fmp4_frame_flush, fmp4_1s, fmp4_hybrid and mkvseg10 (`RES/functional/functional_results_av19.0.2.md` T1).
  - The same holds for mkv_flush_cluster1 and fmp4_1s_flush (`RES/functional/functional_results_av19.0.2_gapfill.md` T1).
- measured (PyAV 19.0.2): every container variant passes all four reader checks (same files, columns `av_decoded`, `cv2_frames`, `ffprobe_packets`, `ffprobe_keyframes`):
  - PyAV decodes all frames;
  - cv2 (FFMPEG backend) reads all frames;
  - ffprobe 9.0.2 counts every packet;
  - every packet has the keyframe flag.
- code: the writer sets the keyframe flag itself (`SCR/wt_common.py:305`).
- measured (other topic): the T1 files have 300 frames. On a 54,000-frame MKV, cv2 counted 53,819 frames (`RU/results/jpeg_passthrough/BENCH.md:176-180`). Long-file reader behaviour is covered there, not here.
- measured (PyAV 19.0.2): stored time base and pts round-trip error (same files, `pts_max_abs_err_us`):
  - MKV stores 1/1000, with errors up to 498.916 us (MJPEG) and 493.727 us (FFV1);
  - fMP4 with `video_track_timescale=90000` stores 1/90000, with an error of 6.434 us.
- code + inferred: part of the 6.434 us is the writer's own floor from ns to us (`SCR/wt_common.py:304`). The container's share is at most 5.56 us (inferred: half of 1/90000 s).
- measured (PyAV 19.0.2): container overhead in bytes per frame, MJPEG 720p (same file, `container_overhead_bytes_per_frame`):

  | Wrapper | Bytes per frame |
  |---|---|
  | mkv | 45.6 |
  | fmp4_frame | 133.7 |
  | fmp4_1s | 14.9 |
  | fmp4_hybrid | 140.8 |
  | mkvseg10 | 52.2 |

- measured (PyAV 19.0.2): PyAV writes FFV1 packets inside MP4, and PyAV, cv2 and ffprobe decode them (FFV1 rows, same file). FFV1-in-MP4 is an FFmpeg-only combination; other readers are NOT VERIFIED.
- code: the files and append writers use only Python file I/O, including the `_Idx` sidecar index, and no PyAV (`SCR/wt_common.py:144-220`). The calls are `open(..., "wb", buffering=0)` and `os.fsync`. Their results therefore do not depend on the PyAV version.
- measured (PyAV 18.0.0, background): files_subdirs, files_fsync, files_subdirs_fsync and append_fsync1s were also 300/300 and 64/64 byte-exact (`RES/functional/functional_results.md` T1). They were not re-run under 19 because their write path has no PyAV (code, above).
- measured (PyAV 19.0.2): `add_stream("ffv1")` with the extradata set by hand stores a configuration that fails to decode (`InvalidDataError ... avcodec_send_packet()`).
  - `add_stream_from_template` stores the 191-byte record, and frame 0 decodes identical to the template (`RES/functional/repro_pyav_add_stream_extradata_av19.0.2.json`).
  - PyAV 18.0.0 behaves the same (background, `RES/functional/repro_pyav_add_stream_extradata.json`).
  - code: the write path raises no error, so the failure is silent until decode.
- measured (input provenance): the FFV1 payload cache was encoded with PyAV 18.0.0 (`"av": "18.0.0"` in `MEDIA/payload_cache/ffv1_1080p.json`, `ffv1_720p.json`). inferred: this does not affect a byte-passthrough check.

### 2.2 Hard kill of the writer process (T4), functional

Scope (code: `SCR/functional_tests.py:310-345`):
- TerminateProcess, one camera, 720p MJPEG (c930e), 60 fps paced.
- Killed after at least 300 acknowledged frames plus U(0, 1.2) s, so at about frames 300-372: a steady-state kill.
- Not targeted: kills during the header, at close, at a segment rotation (hit only by chance, see below) and with a queued backlog.

Findings:
- measured (PyAV 19.0.2, 2 kills per variant): acknowledged frames lost per kill (`RES/functional/functional_results_av19.0.2.md` T4; `..._gapfill.md` T4; all variants in table 3.1):
  - files 0, 0; append 0, 0;
  - mkv 3, 4; mkv_flush 1, 1; mkv_flush_cluster1 1, 1;
  - fmp4_frame 5, 5; fmp4_frame_flush 1, 1; fmp4_1s 33, 62; fmp4_1s_flush 46, 5; fmp4_hybrid 1, 4;
  - mkvseg10 4, 5.
- measured (PyAV 19.0.2, verifier run): mkv_flush plus an empty packet with an explicit timestamp after each frame lost 0, 0, 0 acknowledged frames in 3 kills (`RES/functional/verify_method_emptypkt_av19.0.2.json`, `C_kills_mkv_flush_emptypkt_ts`).
  - Acked 332, 340, 367; byte-exact 332, 340, 367; 0 partial units; ffprobe packet counts = acked.
- measured (PyAV 19.0.2): fmp4_frame, fmp4_1s and fmp4_hybrid leave 1 partial (cut) packet per kill, 6 in total (`RES/functional/functional_results_av19.0.2.json` T4).
  - In 5 of the 6, PyAV decoded the cut JPEG with no error and cv2 returned it as a frame.
  - Only fmp4_frame repeat 0 raised `InvalidDataError`.
- measured (PyAV 18.0.0, background): all 15 fMP4 partial packets decoded with no error in PyAV and cv2 (`RES/functional/functional_results.json` T4).
- measured (PyAV 19.0.2): in one mkvseg10 kill (acked 368), PyAV, ffprobe and cv2 could not open the newest segment `cam00_seg0003.mkv`. The 363 frames in the earlier segments were byte-exact (`functional_results_av19.0.2.json`, T4 mkvseg10 repeat 1).
- code + inferred: rotation happens when `tick_ns - seg_start >= segment_ns`, with 2 s segments at 60 fps (`SCR/wt_common.py:295`; `SCR/functional_tests.py:314-316`).
  - New segments therefore start at frames 121, 242 and 363 (arithmetic).
  - The kill at 368 came 5 frames after a rotation.
- inferred: a newest segment is unreadable when the kill lands within the first few frames after a rotation, before its first cluster is written.
  - This was seen in 1 of 2 PyAV 19 kills and in none of 5 PyAV 18 kills.
  - No PyAV 18 kill landed that early: the nearest was 7 frames after a rotation, and that segment was readable (`functional_results.json` T4 mkvseg10 repeat 0).
  - Cause and version dependence are NOT VERIFIED.
- measured (PyAV 18.0.0, background, 5 kills each): files 0 lost (1 of 5 kills left a half-written next file), files_subdirs 0, append 0, append_fsync1s 0, mkv 2-6, mkv_flush 1 every kill, fmp4_frame_flush 1, 1, 1, 1, 0, fmp4_1s 19-59 (`RES/functional/functional_results.md` T4; `functional_results_fmp4_flush.md` T4).
- measured (both versions): in every container kill, the sidecar index held a record for every acknowledged frame (`idx_records` = `acked_at_kill`). So the index can be ahead of the container by the lost tail.
- measured (PyAV 18.0.0, background): for append, an SOI scan of the raw .mjpeg without the index recovered the same frame counts, and cv2 opened the raw .mjpeg (`functional_results.md` T4).
- source: Matroska muxer, FFmpeg n9.0.2. A new cluster starts at the next packet when `cluster_size > mkv->cluster_size_limit || cluster_time > mkv->cluster_time_limit || (codec_type == AVMEDIA_TYPE_VIDEO && keyframe && cluster_size > 4 * 1024)` (matroskaenc.c:3231-3236; excerpt `RES/source/ffmpeg_n9.0.2_mux_flush_excerpts.txt`, from https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/libavformat/matroskaenc.c).
- inferred: with MJPEG every frame is a keyframe over 4 KiB. Each frame's cluster is therefore written only when the next frame arrives, which explains mkv_flush's constant loss of 1 frame.
- inferred: a process kill does not lose data already passed to WriteFile. No Microsoft primary source was fetched. It fits files/append losing 0 frames, because the files and append writers and the sidecar index write unbuffered (code: `SCR/wt_common.py:146,177,195`, `buffering=0`). The container writers go through libavformat's AVIO buffer instead. Power loss is not tested.

### 2.3 Making every MKV frame reach the disk at once, functional

- measured (PyAV 19.0.2): `OutputContainer` exposes `mux`, `mux_one`, `close` and `start_encoding`, with no flush method (`RES/functional/pyav19.0.2_outputcontainer_api.txt`).
  - `mux_one(None)` raises `TypeError` (`RES/functional/mkv_flush_timebase_check_av19.0.2.json`).
- source: two flush paths exist, and only the first ends the cluster (n9.0.2; fetched copy listed in section 7):
  - `av_write_frame(s, NULL)` → `mkv_write_flush_packet` → `mkv_end_cluster` (mux.c:1182-1190; matroskaenc.c:3273-3288);
  - `av_interleaved_write_frame(s, NULL)` drains the interleaving queue and never calls `write_packet(s, NULL)` (mux.c:1075-1092, 1232-1234).
- measured (PyAV 19.0.2): with an MKV writer still open (flush_packets=1, 30 frames muxed), 29 of 30 frames were on disk byte-exact (`mkv_flush_timebase_check_av19.0.2.json`).
  - `live=1` and `cluster_time_limit=0` did not change this.
  - fMP4 per-frame fragments also gave 29/30.
- measured (PyAV 19.0.2): muxing an empty `av.Packet()` after every MJPEG frame put every frame on disk while the writer was open (`RES/functional/mkv_emptypkt_check_av19.0.2.json`).
  - With empty packets: 1/1, 2/2, 10/10 and 30/30. The control gave 0/1, 1/2, 9/10 and 29/30.
  - The closed file showed 30 packets in ffprobe, PyAV and cv2, with 0 decode errors.
- measured (PyAV 19.0.2): an empty packet with no timestamp triggers the FFmpeg "Timestamps are unset" deprecation warning (`RES/functional/mkv_emptypkt_log_av19.0.2.json`).
  - With an explicit pts/dts (frame pts + 1 us), 10/10 frames were on disk after each frame, and ffprobe listed exactly the 10 real packets (`RES/functional/mkv_emptypkt_ts_av19.0.2.json`).
- measured (PyAV 19.0.2, verifier): an EBML scan of the closed explicit-ts file found 11 clusters and 20 SimpleBlocks, 10 of them size 0 (`RES/functional/verify_method_emptypkt_av19.0.2.json`).
  - ffprobe reports 10 packets, so FFmpeg-based readers hide the size-0 blocks.
  - The `extract_extradata` log line appears with and without the workaround.
- source: FFmpeg turns a data-less packet into a 0-size packet (mux.c:823-827) and sets the keyframe flag for intra-only streams (mux.c:820-821). That triggers the cluster end.
- inferred: the workaround relies on undocumented muxer behaviour. Its write cost was not benched (section 6).
- measured: no fMP4 fragment flush is reachable from PyAV either (same API listing). An fMP4 empty-packet trick is NOT TESTED.

### 2.4 Folder of JPEGs as an image sequence (T2/T3), functional

- measured (PyAV 19.0.2 image2; cv2 4.12.0): `cv2.VideoCapture("<dir>/frame_%06d.jpg")` read 30/30 frames with CAP_IMAGES and with CAP_FFMPEG/CAP_ANY (`RES/functional/functional_results_av19.0.2_t2t6.md`).
  - With frame 10 deleted, all three APIs stopped after 10 frames.
  - With sub-folders of 10, none of them opened.
- measured (same file): with the gap, CAP_FFMPEG/CAP_ANY still report `CAP_PROP_FRAME_COUNT` 30.
- measured (same file): PyAV image2 `sequence` stops at the gap. The `glob` pattern type fails on Windows with `NotImplementedError`.
- measured (PyAV 18.0.0, background): 1 of 5 kills left a half-written newest JPEG file (`functional_results.md` T4, files repeat 1). A folder reader must therefore validate files.

### 2.5 Timestamps in MKV, functional

- measured (PyAV 19.0.2): setting the MKV stream `time_base` to 1/1000000 or 1/90000 has no effect. It is 1/1000 after the header, and pts are stored as 0, 33, 67, 100, 133 for input 0, 33333, 66666, 100000, 133333 us (`RES/functional/mkv_flush_timebase_check_av19.0.2.json`, check B).
- source: FFmpeg n9.0.2 hard-codes `put_ebml_uint(pb, MATROSKA_ID_TIMECODESCALE, 1000000);` (matroskaenc.c:2613) and `avpriv_set_pts_info(st, 64, 1, 1000);` (matroskaenc.c:3602-3603) (`RES/source/ffmpeg_n9.0.2_mux_flush_excerpts.txt`).
- source: RFC 9559 section 5.1.2.9: "A TimestampScale value of 1000000 means scaled timestamps in the Segment are expressed in milliseconds" (https://www.rfc-editor.org/rfc/rfc9559.html, accessed 2026-11-09).
- inferred: ±0.5 ms is far below the 16.7 ms frame interval at 60 fps, so frame-exact seeking is not affected. Sub-millisecond cross-camera timing is lost.

### 2.6 Truncation of a closed file (T5) and the segment muxer (T6), functional

- measured (PyAV 19.0.2): a cleanly closed 300-frame file cut to 50 % keeps (`functional_results_av19.0.2.md` T5):
  - 149 byte-exact frames for append, mkv and mkv_flush;
  - 149 plus 1 cut packet for fmp4_frame, fmp4_frame_flush and fmp4_1s;
  - 0 for fmp4_hybrid, because its moov is at the end.

  This is a damaged-file case, not crash evidence.
- measured (PyAV 19.0.2): FFmpeg's `segment` muxer through PyAV (`segment_format=matroska`, `segment_time=2`) wrote 5 files with 300/300 packets byte-exact after a clean close (`functional_results_av19.0.2_t2t6.md` T6).
- code: T6 used `add_stream("mjpeg", rate=30)` with exact 30 fps timestamps (`SCR/functional_tests.py:384-395`). The segment muxer under a kill is NOT TESTED.
- code: the WT `mkvseg10` writer rotates files itself; it is not FFmpeg's segment muxer (`SCR/wt_common.py:8`, `:61`, `:274`).

### 2.7 Reading back and indexing, functional

- measured (PyAV 19.0.2): MKV (flush_packets=1) and fMP4 (per-frame fragments + flush) both report `stream.frames = 0` with a correct duration (`RES/functional/meta_seek_check_av19.0.2.json`).
  - 100/100 random seek + demux reads returned the same bytes as a sequential demux.
- measured (Windows Search, read-only query): the media folder is in the Windows Search index (`RES/wsearch_scope_check_20261109.json`, `RES/wsearch_itemurl_check_20261109.json`).
  - `System.ItemUrl` gives the real `C:/Users/Dom/Documents/...` path; `System.ItemPathDisplay` shows `C:\Users\Pictures\Documents\...`. That display quirk is NOT VERIFIED.
- code: the write benches record MsMpEng CPU per cell (`SCR/bench_write.py:269-278`, `:338`, `:350`, `:413`) but not SearchIndexer CPU. SearchIndexer is recorded only in the idle baselines (`RU/scripts/bench_runner/idle_baseline.py:20-47`).

### 2.8 Capacity: no wrapper drops frames up to 16 x 1080p60 (quiet run, PyAV 19.0.2, P-cores only)

Method (code):
- Each cell is one `bench_write.py` process. N simulated camera processes replay real corpus JPEGs on an absolute per-camera schedule, and nothing is encoded (`SCR/bench_write.py:7-11`).
- 1080p60 sends the 1080p30 corpus frames at 60 fps (`SCR/wt_common.py:41-42`).
- Thread model: one writer thread per camera behind a bounded queue of `ring_s` = 2.87 s. A full queue drops and counts the frame (`SCR/bench_write.py:19-20`, `:170`, `:233-237`, `:307`). measured: `summary.slots` = 172 frames at 60 fps.
- No writer calls fsync in these cells (code: writer names `files`, `append`, `mkv_flush`, `fmp4_frame_flush` in `SCR/wt_common.py:54`, `:58`; the fsync variants were not in the queue, `RU/results/BENCH_QUEUE_2300.md` line 238).

Findings:
- measured: 77 of 77 write cells had written = produced, 0 dropped and 0 late ticks. Files: `RES/bench/focus16_av19/*.json` (12), `RES/bench/models16_av19_shared_vs_thread/*.json` (18), `RES/bench/core_av19/*.json` (44), `RES/bench/long_av19/*.json` (3), fields `summary.written`, `produced`, `dropped`, `late_ticks`.
- measured: the three 10-minute cells at 16 x 1080p60 each wrote 576,000 frames (94,163,436,720 bytes) at 156.94 MB/s with 0 dropped. This was the thread model with files, append and mkv_flush (`RES/bench/long_av19/{files,append,mkv_flush}__16cam__1080p60__mjpeg__thread__600s.json`).
- measured: the camera loop never stalled. Grab-late max was 1.3-2.0 ms in focus16 (medians per writer; 1.1-2.3 ms over all reps) and 1.3-2.6 ms in the long cells (`grab_lateness_ms_all.max`, same files).
- measured: tick->written max, which includes queue wait, was 26.3 ms (26.1-167.9) for files in focus16 and 329.1 ms in the 10-minute files cell. Both are far below the 2.87 s queue (`tick_to_written_ms_all.max`). Drop-free does not mean stall-free.
- measured: the PhysicalDrive0 write delta during a 30 s 16 x 1080p60 cell was 2.03-2.62 GB (medians per writer), against 4.71 GB of payload (`summary.physical_disk_delta`, focus16_av19). inferred: 30 s cells measure the OS-cache path.
- measured: during the 600 s cells the delta was 106.19 GB (files), 95.64 GB (append) and 91.90 GB (mkv_flush), against 94.16 GB of payload (same long files).
  - inferred: the 600 s cells show the device keeping up at 156.9 MB/s.
  - inferred: files writes about 12.0 GB (12.8 %) more than its payload, plausibly file-system metadata for 576,016 files. This is one rep and the delta is system-wide. Lazy-writer carry-over from WT-USABILITY-18K, which ended 12 s before WT-LONG-AV19 began (`RES/BENCH.md` section 1), is an alternative explanation that was not excluded.
  - inferred: mkv_flush ending below the payload means part of it was still cached at the end.
- measured: one unpaced writer, warm cache, 18,000 frames of 720p (996.8 MB), build time: files 3.77 s, append 0.33 s, mkv_flush 0.83 s, fmp4_frame_flush 0.41 s (`RES/bench/usability/usability_18000.json`, `build_s`, 1 run).
  - inferred (arithmetic): that is about 264, 3,030, 1,200 and 2,440 MB/s into the cache. Even the slowest single writer exceeds 156.9 MB/s.
- measured (other topic, quiet run item CR-FRAG-MJPEG-PYAV19, one unpaced writer, 3000 camera 720p JPEGs, 3 reps, wall µs per frame, median): mkv+fp 24.9, fmp4_every+fp 23.5, seg_mkv_10+fp 21.6, seg_mkv_1+fp 32.0, rawidx 34.9, folder 207.3 (`RU/results/crash_resilience/bench/fragment_overhead_mjpeg_pyav19.json`; table in `RU/results/crash_resilience/BENCH.md` section 3.2). These are that topic's own writer implementations (`seg_mkv` is FFmpeg's segment muxer; WT `mkvseg10` is manual rotation, 2.6), so they cross-check single-writer cost only.

### 2.9 Defender real-time scanning cost per writer (key result)

Windows Defender real-time protection was ON with default settings and was not changed. Its cost is part of what a default Windows install pays.
- code: `msmpeng_cpu_s` is MsMpEng.exe user + system CPU between the start and the end of the timed window. The window starts before `go` and ends right after every child has joined, so writer closes are inside it but any scan that runs after close is not (`SCR/bench_write.py:269-278`, `:333-347`, `:350`, `:413`). It is system-wide, so it includes Defender's background work.

Findings:
- measured (idle baseline, 30 s each): MsMpEng 1.531, 1.469 and 1.234 CPU-s; SearchIndexer 1.344, 1.203 and 1.219 CPU-s (`RES/bench/idle_baseline_av19.jsonl`, tags `before_focus16_av19`, `after_first_read_av19`, `after_core_av19`).
- measured (16 x 1080p60, thread, 30 s, 3 reps, `RES/bench/focus16_av19/*.json`), MsMpEng CPU-s per cell:

  | Writer | MsMpEng CPU-s per cell |
  |---|---|
  | files | 26.8 (25.9-29.3) |
  | append | 1.19 (1.19-1.45) |
  | mkv_flush | 1.52 (1.31-1.55) |
  | fmp4_frame_flush | 1.16 (1.11-1.39) |

- inferred: inside the timed window, append, mkv_flush and fmp4_frame_flush sit at the idle level (1.23-1.53 CPU-s per 30 s). Only the folder of JPEGs adds Defender work there, about 0.89 of a logical CPU (26.8 / 30).
- measured (10-minute cells, `RES/bench/long_av19/`): MsMpEng 558.7 CPU-s (files), 19.9 (append) and 25.7 (mkv_flush) in 600 s.
  - inferred: the idle-equivalent for 600 s is 24.7-30.6 CPU-s (20 x the idle baselines), so append and mkv_flush stay at idle inside the window.
  - inferred: files costs about 0.93 of a logical CPU in Defender, steady over 10 minutes.
- measured (`RES/bench/core_av19/*.json`, 20 s, 1 rep): files MsMpEng scales with the camera count. The one-file layouts stay at 0.4-1.3 CPU-s in every cell.

  | Profile | 1 cam | 4 cams | 8 cams | 16 cams |
  |---|---|---|---|---|
  | 720p30 | 2.14 | 6.03 | 9.62 | 16.64 |
  | 1080p30 | 2.31 | 5.88 | 9.34 | 14.27 |
  | 1080p60 | 3.39 | 8.86 | 11.06 | not run |

- inferred (arithmetic, idle not subtracted): Defender CPU per new file inside the window is a lower bound of about 0.9-1.7 ms in the 8- and 16-camera cells, and it varies with concurrency:
  - about 0.97 ms in the 600 s cell (558.7 s / 576,016 files) and 0.93 ms in focus16 (26.8 s / 28,816 files);
  - 1.15 ms at 8 cams x 1080p60 (11.06 s / 9608 files);
  - 1.48-1.73 ms in the 20 s 16-camera 30 fps cells (14.27 and 16.64 s / 9616 files).
- measured: Defender work also lands outside the timed windows. Runner item totals exceed the cell sums:

  | Item | Item total CPU-s | Cell sum CPU-s | Excess |
  |---|---|---|---|
  | WT-FOCUS16-AV19 | 114.3 | 93.9 | 20.4 |
  | WT-MODELS16-AV19 | 189.3 | 153.7 | 35.6 |
  | WT-CORE-AV19 | 116.2 | 87.6 | 28.6 |
  | WT-CORE60-AV19 | 37.7 | 30.8 | 6.9 |
  | WT-LONG-AV19 | 649.9 | 604.3 | 45.6 |

  Sources: `RU/results/BENCH_RUN_2300_LOG.jsonl` (`msmpeng_cpu_s_during_item`); cell sums recomputed from the cell JSONs (`summary.msmpeng_cpu_s`).
  - inferred: part of the excess is idle Defender activity during setup and teardown between cells. The rest is unattributed; it could include close-time scans of the one-file recordings (NOT VERIFIED).
- measured: no Defender scan event was logged during any WT item (`defender_scan_events_during_item` empty in `RU/results/BENCH_RUN_2300_LOG.jsonl`).
- inferred: the media path is not excluded from Defender, because MsMpEng grows with file creation there. The exclusion list itself was not readable without admin (NOT VERIFIED).

### 2.10 Per-write latency and CPU (quiet run)

- measured (16 x 1080p60, thread, 30 s, 3 interleaved reps, `RES/bench/focus16_av19/*.json`), `write_ms_all`:

  | Writer | p50 ms | p99.9 ms | max ms |
  |---|---|---|---|
  | files | 2.111 (1.978-2.206) | 20.3 (12.8-29.5) | 25.6 (25.5-167.4) |
  | append | 0.553 (0.539-0.586) | 1.72 (1.62-1.77) | 15.7 (11.5-37.7) |
  | mkv_flush | 0.808 (0.804-0.884) | 2.85 (2.12-2.92) | 8.0 (6.2-9.2) |
  | fmp4_frame_flush | 0.853 (0.767-0.879) | 3.18 (2.32-5.40) | 7.2 (5.7-11.3) |

- measured: bench CPU, meaning camera processes including their writer threads (`our_cpu_s / 30`; code `SCR/bench_write.py:386-389`): files 1.09 (0.75-1.13) logical CPUs, append 0.63 (0.56-0.71), mkv_flush 0.90 (0.86-0.93), fmp4_frame_flush 0.88 (0.86-1.06) (same files).
- measured: system busy (share of all 28 logical CPUs): files 14.6 %, append 7.6 %, mkv_flush 8.1 %, fmp4_frame_flush 8.1 % (`system_busy_pct_all_cpus`, same files).
- inferred (arithmetic from `our_cpu_s`, `msmpeng_cpu_s` and `system_busy_pct_all_cpus` x 28, medians, thread model at 16 x 1080p60 in focus16_av19, models16_av19 and long_av19):

  | Measure (logical CPUs) | files | one-file layouts (append, mkv_flush, fmp4_frame_flush) |
  |---|---|---|
  | bench + MsMpEng | 1.6-2.0 | 0.67-1.24 |
  | whole system busy | 3.5-4.1 | 2.1-2.5 |
  | residual (system - bench - MsMpEng) | 1.95-2.06 | 1.23-1.61 |

  - files' whole-system busy is 1.2-2.0 logical CPUs above append in the same item.
  - The residual for files is about 0.4-0.7 logical CPU above the one-file layouts. It is kernel, file-system or other system work (possibly SearchIndexer, which indexes this folder, 2.7). It is not recorded per process.
  - The 1-camera core cells show a residual of about 0.92-1.12, the idle floor of the machine.
- measured (10 minutes, 16 x 1080p60, 1 rep, `RES/bench/long_av19/`):

  | Writer | p50 ms | p99.9 ms | max ms | tick->written p99.9 ms | bench CPU (logical CPUs) |
  |---|---|---|---|---|---|
  | files | 1.977 | 37.7 | 328.8 | 96.0 | 0.70 |
  | append | 0.479 | 1.73 | 26.6 | 2.66 | 0.81 |
  | mkv_flush | 1.003 | 6.75 | 31.8 | 7.74 | 1.19 |

  - measured: the 10-minute mkv_flush tail (p99.9 6.75 ms) is above its 30 s value (2.85 ms). Single sample; fmp4_frame_flush has no 10-minute cell.
- measured (`RES/bench/core_av19/*.json`, 1 rep, `write_ms_all.p50`, 1080p30):

  | Writer | 1 cam | 4 cams | 8 cams | 16 cams |
  |---|---|---|---|---|
  | files | 1.324 | 1.623 | 2.411 | 3.368 |
  | append | 0.195 | 0.211 | 0.272 | 0.679 |
  | mkv_flush | 0.324 | 0.331 | 0.408 | 0.818 |
  | fmp4_frame_flush | 0.311 | 0.324 | 0.413 | 0.958 |

  - measured: files p50 rises most in absolute terms, by about 2.0 ms from 1 to 16 cams (2.5x).
  - measured: the one-file layouts are nearly flat up to 8 cams, then rise 2.5-3.5x at 16 cams (+0.48 to +0.65 ms from 1 cam). In relative terms they grow as much as files or more.
  - measured: at 720p30 the one-file layouts stay nearly flat (append 0.105 to 0.170, mkv_flush 0.180 to 0.266, fmp4_frame_flush 0.184 to 0.258 ms from 1 to 16 cams), while files goes from 1.260 to 3.255 ms.
  - inferred: the 8 to 16 step at 1080p coincides with 16 camera processes on 16 pinned logical CPUs. Not tested.
- measured: medians of the same config differ between items. files thread at 16 x 1080p60:

  | Measure | focus16_av19 | models16_av19 |
  |---|---|---|
  | files p50 ms | 2.111 (1.978-2.206) | 2.098 (2.027-2.323) |
  | files p99.9 ms | 20.3 (12.8-29.5) | 8.4 (7.0-19.3) |
  | files bench CPU (logical CPUs) | 1.09 (0.75-1.13) | 0.69 (0.67-0.78) |
  | append p50 ms | 0.553 (0.539-0.586) | 0.365 (0.355-0.520) |

  - The files p99.9 and bench CPU rep ranges overlap; only append p50 has disjoint ranges. Files: `RES/bench/focus16_av19/`, `RES/bench/models16_av19_shared_vs_thread/*thread*`. The cause is not attributed.
- measured: **per-write latencies are higher tonight than in the contaminated daytime run.** p50 at 16 x 1080p60, thread:

  | Writer | daytime (`RES/bench/focus16/`, PyAV 18 env) ms | tonight focus16_av19 ms | tonight models16_av19 ms | factor |
  |---|---|---|---|---|
  | files | 1.299 | 2.111 | 2.098 | 1.6x |
  | append | 0.179 | 0.553 | 0.365 | 2.0-3.1x |
  | mkv_flush | 0.260 | 0.808 | 0.846 | 3.1-3.3x |
  | fmp4_frame_flush | 0.266 | 0.853 | not run | 3.2x |

  - measured: the daytime per-rep bench CPU was erratic (append 0.35, 0.62 and 0.03 logical CPUs), so it is not compared here.
  - measured: daytime system busy was 11.0-25.8 % per cell, against 7.4-14.8 % tonight (same files). The more loaded run was faster per call.
  - inferred (not tested): P-core pinning is a possible cause. 16 camera processes plus writer threads ran on 16 logical CPUs (8 P-cores with HT) instead of 28. The system-busy observation is consistent with oversubscription of the pinned CPUs but does not test it.
  - inferred: PyAV is an unlikely cause, because append uses no PyAV (code `SCR/wt_common.py:144-220`) and also rose.
  - The daytime numbers are therefore not lower bounds in every column.

### 2.11 One shared writer process vs a writer thread per camera

- code: process_shared sends frames through a shared-memory ring to ONE writer process serving all cameras round-robin (`SCR/bench_write.py:22`). Per-call write time is the wrong metric for it; tick->written includes the wait for its turn.
- code: the writer-process CPU is split per camera and added once to `our_cpu_s`, so it is not double-counted (`SCR/bench_write.py:141-146`, `:387-389`).
- measured (16 x 1080p60, 30 s, 3 interleaved reps, `RES/bench/models16_av19_shared_vs_thread/*.json`):

  | Writer | Model | write p50 ms | tick->written p99 ms | tick->written max ms | bench CPU (logical CPUs) | MsMpEng CPU-s |
  |---|---|---|---|---|---|---|
  | files | process_shared | 0.270 (0.270-0.275) | 7.49 (7.20-7.49) | 26.5 (24.9-41.9) | 0.34 (0.31-0.50) | 19.5 (18.6-20.2) |
  | files | thread | 2.098 (2.027-2.323) | 5.98 (5.96-6.20) | 34.6 (22.2-38.4) | 0.69 (0.67-0.78) | 26.6 (26.0-28.4) |
  | append | process_shared | 0.118 (0.117-0.119) | 4.49 (4.40-4.55) | 10.4 (10.1-22.1) | 0.29 (0.23-0.33) | 1.06 (0.95-1.08) |
  | append | thread | 0.365 (0.355-0.520) | 2.10 (2.03-2.51) | 4.9 (4.3-10.8) | 0.70 (0.67-0.73) | 1.14 (1.13-1.36) |
  | mkv_flush | process_shared | 0.170 (0.167-0.176) | 5.44 (5.44-5.57) | 19.3 (9.7-55.1) | 0.26 (0.25-0.36) | 1.16 (1.08-1.19) |
  | mkv_flush | thread | 0.846 (0.648-1.011) | 2.62 (2.34-2.81) | 6.7 (4.3-9.0) | 0.93 (0.80-0.99) | 1.45 (1.38-1.48) |

- measured: both models had 0 dropped and 0 late ticks in all 18 cells (same files).
- inferred (arithmetic, ratio of medians): process_shared used 28-49 % of the thread model's bench CPU (files 0.49, append 0.42, mkv_flush 0.28).
- inferred (arithmetic): process_shared raised tick->written p99 by 1.25x for files (7.49 vs 5.98 ms) and 2.1x for append and mkv_flush. Every p99 stays under one 60 fps frame interval (16.7 ms). Some maxima exceed it (up to 55.1 ms) and are absorbed by the queue.
- inferred: the lower files MsMpEng with process_shared (19.5 vs 26.6 CPU-s) is not explained here.

### 2.12 After-recording cost (quiet run)

- measured (first read, `RES/bench/usability/first_read_check_5000.json`): 5000 freshly written 720p corpus JPEGs, 276,716,591 bytes per pass:

  | Layout | 1st pass wall s | 1st pass MsMpEng CPU-s | 2nd pass wall s | 2nd pass MsMpEng CPU-s |
  |---|---|---|---|---|
  | files (.jpg) | 20.594 | 20.594 | 0.186 | 0.156 |
  | one append file | 0.088 | 0.031 | 0.084 | 0.000 |

  - code: the wall time and MsMpEng CPU are separate readings that happen to agree (`SCR/first_read_check.py:46-59`).
- inferred (arithmetic): about 4.1 ms of wall time and 4.1 ms of Defender CPU per new file on the first open, 111x the second pass.
  - Defender CPU equal to the wall time is consistent with Defender causing the delay, but does not prove it. A Defender exclusion test was not allowed.
  - The daytime 3000-file check gave about the same per-file cost, 3.8 ms (11.35 s; `RES/bench/usability/first_read_check_3000.json`, background).
- measured (usability, `RES/bench/usability/usability_18000.json`): an 18,000-frame single-camera 720p30 recording (10 min, about 1.0 GB per format), warm cache, 1 run, same volume (C:). 1000 random reads gave 0 wrong reads in every format.
- code: per format the order is frame table, sequential read, random reads, first image (`SCR/bench_usability.py:90-108`). For the folder layouts the random reads and first image therefore come after the sequential pass has already paid the per-file first-open cost.

  | Format | Files | sequential read s (first read) | frame table s | 1000 random reads s (after a full read) | first image s (after a full read) | robocopy /MT:8 s | delete s |
  |---|---|---|---|---|---|---|---|
  | files | 18001 | 78.36 | 0.038 | 0.048 | 0.0023 | 3.48 | 1.21 |
  | files_subdirs | 18001 | 64.63 | 0.039 | 0.047 | 0.0022 | 2.31 | 1.15 |
  | append | 2 | 0.18 | 0.016 | 0.017 | 0.0024 | 0.22 | 0.06 |
  | mkv_flush | 2 | 0.20 | 0.233 | 0.027 | 0.0037 | 0.22 | 0.06 |
  | fmp4_frame_flush | 2 | 0.64 | 0.638 | 0.425 | 0.400 | 0.22 | 0.06 |

- inferred: the first access to a frame in a fresh folder recording costs about 4 ms per file (first-read check above), not the 0.0023 s / 1000 random-read figures shown here.
- inferred (arithmetic): the folder sequential reads are 4.35 ms (files) and 3.59 ms (files_subdirs) per file, close to the 4.1 ms first-read cost per file. This bench records no MsMpEng per format; the whole item used 193.36 CPU-s (`RU/results/BENCH_RUN_2300_LOG.jsonl`).
- measured: fmp4_frame_flush open + metadata took 0.412 s, against 0.006 s for mkv_flush (`open_meta_s`).
  - inferred: fMP4's first image and random-read times are dominated by that open.
- measured: mkv_flush and fmp4_frame_flush report `stream_frames` = 0 in metadata (`meta` field). A frame table therefore needs a demux pass (0.233 s / 0.638 s) or the sidecar index (append: 0.016 s).
- measured: the folder layouts allocate 1.022 GB for 0.997 GB of data with 4 KiB clusters (`alloc_bytes_4k_clusters`). inferred: about 2.5 % slack.
- measured: deleting the 10-minute 16 x 1080p60 recording took 53.0 s for files (576,016 files), against 4.4 s for append and mkv_flush (`delete_s`, `RES/bench/long_av19/`).

### 2.13 Durability policy cost (cross-reference, quiet run)

- measured (other topic, PyAV 19.0.2 env, one unpaced writer, 3000 frames of 720p, 3 reps): per-frame latency, medians (`RU/results/crash_resilience/bench/fsync_pyav19.json`):

  | Policy | p50 us | p99 us | max | throughput |
  |---|---|---|---|---|
  | flush only | 16.3 | not cited | not cited | 2484 MB/s |
  | fsync every frame | 409.3 | 669.0 | 8.74 ms | 127 MB/s |
  | fsync every 30 frames | 16.1 | 883.4 | 4.17 ms | 1066 MB/s |

- measured (PyAV 18 env, contaminated, background): files_fsync at 16 x 1080p60 had a write max of 1278.5 ms; append_fsync1s had 235.0 ms (1 rep each, `RES/bench/core16_extra/`). Multi-camera fsync was not re-run on the quiet machine.

### 2.14 Earlier studies and Chromium (background / other topics)

- measured (earlier study, background): a hard-killed MSMF .mp4 had 0 of 300 frames readable, against 298-359 for MJPEG-in-MKV (`research/frame_ring_buffer/prototypes/results/p11_crash_container.md`).
- measured (earlier study, background): under lockstep, a stalled recorder stalls every camera. The overwrite policy lost 195 frames silently during a 3.5 s stall (`research/frame_ring_buffer/prototypes/results/p3v_asymmetric_stall.md`, `p3_lossless_record.md`).
- code: the Rust prototype pipes MJPEG into an ffmpeg child that re-encodes to H.264 (libx264 ultrafast) through an unbounded channel (`git show upstream/sfn26:skellycam-rust/src/recording/recorder.rs` lines 1-6, 41-43). It is not a passthrough reference.
- measured (other topic): Electron 35 and 45 (and the `C156` browser rows in the same table) do not play MJPEG in any of the five containers tested (`RU/results/chromium_codecs/tables.md` lines 105-119 for mjpeg_422 and 165-176 for mjpeg_camera):
  - `DEMUXER_ERROR_NO_SUPPORTED_STREAMS` for mp4, fmp4, mkv and mov;
  - `DEMUXER_ERROR_COULD_NOT_OPEN` for avi.
- inferred: no wrapper gives native Chromium playback for MJPEG. The compatibility that G5 trades away is compatibility with FFmpeg/OpenCV-based tools.

## 3. Comparison tables

### 3.1 Functional properties per wrapper (PyAV 19.0.2 unless marked)

| Wrapper | Byte-exact T1 | Acked frames lost per kill | Cut packet after kill | 50 % truncation of closed file keeps | Stored time base | Files per camera | FFmpeg-based readers (300-frame files) |
|---|---|---|---|---|---|---|---|
| files | 300/300 | 0, 0 | 1 of 5 kills (PyAV 18, background) | n/a | sidecar int64 ns | 1 per frame + .idx | image-seq breaks at a gap or sub-folder |
| files_subdirs | 300/300 (background) | 0 x5 (background) | 0 (background) | n/a | sidecar | 1 per frame + .idx | not opened by image-seq APIs |
| append + .idx | 300/300 | 0, 0 | 0 | 149 | sidecar int64 ns | 2 | cv2 opens raw .mjpeg (background) |
| mkv (defaults) | 300/300 | 3, 4 | 0 | 149 | 1/1000 | 1 | PyAV, cv2, ffprobe |
| mkv_flush | 300/300 | 1, 1 | 0 | 149 | 1/1000 | 1 | PyAV, cv2, ffprobe |
| mkv_flush + explicit-ts empty packet | NOT TESTED (clean close); 30/30 on disk while open | 0, 0, 0 (3 verifier kills) | 0 | NOT TESTED | 1/1000 | 1 | PyAV, cv2, ffprobe (size-0 blocks hidden) |
| fmp4_frame_flush | 300/300 | 1, 1 | 0 | 149 + 1 cut | 1/90000 | 1 | PyAV, cv2, ffprobe |
| fmp4_1s | 300/300 | 33, 62 | 1 each, decoded silently | 149 + 1 cut | 1/90000 | 1 | PyAV, cv2, ffprobe |
| fmp4_hybrid | 300/300 | 1, 4 | 1 each, decoded silently | 0 (moov at end) | 1/90000 | 1 | PyAV, cv2, ffprobe |
| mkvseg10 (2 s in tests) | 300/300 in 5 files | 4, 5 | 0; newest segment unreadable once | NOT TESTED | 1/1000 | N | per segment |

Sources: `RES/functional/functional_results_av19.0.2.md`, `..._gapfill.md`, `..._t2t6.md`, `mkv_emptypkt_check_av19.0.2.json`, `verify_method_emptypkt_av19.0.2.json`. Background rows: `functional_results.md`. Long-file caveat (other topic): cv2 counts a 54,000-frame MKV as 53,819 frames (`RU/results/jpeg_passthrough/BENCH.md:176-180`).

### 3.2 Timed cost at 16 cameras x 1080p60, thread model (quiet run, PyAV 19.0.2, 16 P-core logical CPUs, 3 reps, median (min-max))

| Writer | write p50 ms | write p99.9 ms | write max ms | bench CPU (logical CPUs) | MsMpEng CPU-s / 30 s (timed window) | sys busy % of 28 | delete 30 s media s |
|---|---|---|---|---|---|---|---|
| files | 2.111 (1.978-2.206) | 20.3 (12.8-29.5) | 25.6 (25.5-167.4) | 1.09 (0.75-1.13) | 26.8 (25.9-29.3) | 14.6 (12.7-14.8) | 2.32 (2.28-2.43) |
| append | 0.553 (0.539-0.586) | 1.72 (1.62-1.77) | 15.7 (11.5-37.7) | 0.63 (0.56-0.71) | 1.19 (1.19-1.45) | 7.6 (7.4-7.8) | 0.34 |
| mkv_flush | 0.808 (0.804-0.884) | 2.85 (2.12-2.92) | 8.0 (6.2-9.2) | 0.90 (0.86-0.93) | 1.52 (1.31-1.55) | 8.1 (8.0-8.5) | 0.33 |
| fmp4_frame_flush | 0.853 (0.767-0.879) | 3.18 (2.32-5.40) | 7.2 (5.7-11.3) | 0.88 (0.86-1.06) | 1.16 (1.11-1.39) | 8.1 (8.0-9.0) | 0.33 |
| idle baseline | - | - | - | - | 1.23-1.53 | - | - |

Sources: `RES/bench/focus16_av19/*.json`; `RES/bench/idle_baseline_av19.jsonl`. Each of the 12 cells wrote 28,800/28,800 frames with 0 dropped (86,400 per writer over 3 reps).

### 3.3 Sustained 10 minutes, 16 x 1080p60, thread model (1 rep each)

| Writer | written / dropped | write p99.9 ms | write max ms | tick->written max ms | MsMpEng CPU-s / 600 s (timed window) | disk write GB (payload 94.16) | delete s |
|---|---|---|---|---|---|---|---|
| files | 576,000 / 0 | 37.7 | 328.8 | 329.1 | 558.7 | 106.19 | 53.0 |
| append | 576,000 / 0 | 1.73 | 26.6 | 27.4 | 19.9 | 95.64 | 4.4 |
| mkv_flush | 576,000 / 0 | 6.75 | 31.8 | 32.9 | 25.7 | 91.90 | 4.4 |

Source: `RES/bench/long_av19/*.json`. fmp4_frame_flush was not run for 10 minutes.

### 3.4 After-recording cost, 18,000 frames (10 min, 1 camera 720p30), warm cache, 1 run

| Format | Files | First sequential read s | Frame table s | 1000 random reads s (after a full read) | Copy shutil s | Copy robocopy s | Delete s |
|---|---|---|---|---|---|---|---|
| files | 18001 | 78.36 | 0.038 | 0.048 | 5.99 | 3.48 | 1.21 |
| files_subdirs | 18001 | 64.63 | 0.039 | 0.047 | 5.23 | 2.31 | 1.15 |
| append | 2 | 0.18 | 0.016 | 0.017 | 0.20 | 0.22 | 0.06 |
| mkv_flush | 2 | 0.20 | 0.233 | 0.027 | 0.21 | 0.22 | 0.06 |
| fmp4_frame_flush | 2 | 0.64 | 0.638 | 0.425 | 0.20 | 0.22 | 0.06 |

Source: `RES/bench/usability/usability_18000.json`. Order of operations: `SCR/bench_usability.py:90-108`.

### 3.5 Single-file container trade-off (no ranking)

| Property | mkv_flush | mkv_flush + empty packet | fmp4_frame_flush |
|---|---|---|---|
| Acked lost per kill, PyAV 19 | 1, 1 | 0, 0, 0 (verifier) | 1, 1 |
| Cut packet after kill | 0 | 0 | 0 |
| Stored time base | 1/1000 | 1/1000 | 1/90000 |
| Overhead B/frame (MJPEG 720p) | 45.6 | NOT MEASURED | 133.7 (fmp4_frame) |
| Write p50 / p99.9 at 16 x 1080p60, 30 s (quiet) | 0.808 / 2.85 ms | NOT MEASURED | 0.853 / 3.18 ms |
| Write p50 / p99.9 at 16 x 1080p60, 10 min (quiet, 1 rep) | 1.003 / 6.75 ms | NOT MEASURED | NOT MEASURED |
| One unpaced writer, wall µs/frame (CR-FRAG, nearest variant) | 24.9 (mkv+fp) | NOT MEASURED | 23.5 (fmp4_every+fp) |
| Open + metadata, 18k frames | 0.006 s | not run | 0.412 s |
| Frame table, 18k frames (demux) | 0.233 s | not run | 0.638 s |
| 1000 random reads, 18k frames | 0.027 s | not run | 0.425 s |
| Relies on undocumented muxer behaviour | no | yes (inferred, 2.3) | no |

Sources: as in 3.1-3.4; CR-FRAG row from `RU/results/crash_resilience/bench/fragment_overhead_mjpeg_pyav19.json`.

## 4. Implications for the plan

Implications 1-2 and 13 are scoped to this machine (16 P-core logical CPUs, one NVMe, Defender on). Smaller CPUs and slower disks in the hardware target are NOT VERIFIED; there the files layout's extra CPU would weigh more (inferred).

1. **Do not make a folder of JPEGs the default layout (G1, G5).**
   - Inside the timed window it is the only layout with a Defender cost above idle: about 0.9 of a logical CPU at 16 x 1080p60, steady over 10 minutes (2.9).
   - inferred: bench + Defender is 1.6-2.0 logical CPUs, against 0.67-1.24 for the one-file layouts; whole-system busy is 1.2-2.0 logical CPUs above append (2.10).
   - Its write tail is the worst: p99.9 20.3 ms and a 328.8 ms max in 10 minutes (2.10).
   - Its first read costs about 4 ms per file, and deleting a 10-minute 16-camera recording takes 53 s against 4.4 s (2.12).
   - It has no crash advantage over append + index: both lost 0 frames (2.2).
   - Standard image-sequence readers stop at the first dropped frame (2.4).
2. **Throughput does not decide between append, MKV and fMP4 on this machine (G5).**
   - All three kept 16 x 1080p60 with 0 drops (2.8) and stay at the idle Defender level inside the timed window (2.9).
   - Write p99.9 at 16 x 1080p60 was 1.72-3.18 ms in the 30 s cells; the 10-minute mkv_flush cell reached 6.75 ms (2.10).
   - inferred: giving up standard-container compatibility buys 0.25-0.52 ms per write at p50 and 0.23-0.39 logical CPUs at 16 x 1080p60 (append vs mkv_flush, across focus16_av19, models16_av19 and long_av19, 2.10). That is not enough on its own to justify a non-standard format.
3. **The append + sidecar index layout remains the reference for crash tolerance (G2) and indexing.**
   - It lost 0 acknowledged frames (2.2) and has the cheapest frame table, 0.016 s for 18k frames (2.12).
   - It is not a standard container, so FFmpeg/OpenCV tools need the raw-MJPEG path or a remux. For Chromium (G8), MJPEG needs a remux, transcode or JS path whatever the wrapper (2.14).
4. **For a standard single file, prefer mkv_flush over fmp4_frame_flush on after-recording cost; they tie on crash loss.**
   - Both lost 1, 1 frames per kill with 0 cut packets (2.2). Their 30 s write costs overlap within the rep range (3.2). The 10-minute fMP4 write cost is NOT MEASURED.
   - MKV opened in 0.006 s against 0.412 s, and did 1000 random reads in 0.027 s against 0.425 s (2.12).
   - fMP4 keeps a 90 kHz time base (2.1).
   - MKV plus an explicit-ts empty packet per frame was the only variant with 0 loss in every kill (3 kills, against 2 per variant elsewhere under PyAV 19, 2.2). It relies on undocumented muxer behaviour (2.3), and its write cost is unmeasured. Adopt it only after a clean-close byte-exact check, more kills, a timed cell and a non-FFmpeg parser check.
5. **Keep exact capture timestamps in a sidecar index, not in MKV pts.**
   - MKV through PyAV 19.0.2 is fixed at 1 ms (2.5), with a measured error up to 498.9 us (2.1).
   - The sidecar index survived every kill (2.2). Readers must reconcile index and container using the shorter of the two.
6. **One writer thread per camera is adequate. A single shared writer process is a valid CPU-saving alternative.**
   - Both models had 0 drops at 16 x 1080p60 (2.11).
   - process_shared used 28-49 % of the thread model's bench CPU and raised tick->written p99 1.25-2.1x, still under one 60 fps frame interval (inferred, 2.11).
   - Neither choice is forced by the data. The 4-camera and in-loop models were not re-run (section 6).
7. **Keep the writer off the capture loop, with a bounded and counted queue.**
   - Writer stalls up to 329 ms occurred without any camera-loop delay (grab-late max ≤ 2.6 ms) because the 2.87 s queue absorbed them (2.8).
   - Earlier evidence shows silent loss or stall propagation otherwise (2.14, background).
   - Use the tested depth (2.87 s). Smaller queues are NOT VERIFIED: the worst tick->written in 10 minutes was 329.1 ms (files) and 32.9 ms (mkv_flush), one sample per writer, Defender on, NVMe.
8. **Avoid `hybrid_fragmented` and 1 s fragments for recording.** hybrid gives 0 frames after truncating a closed file (2.6), and 1 s fragments lost up to 62 frames per kill (2.2).
9. **Readers must not rely on decode errors to find a cut tail frame.** A cut tail JPEG decoded silently in 5 of 6 PyAV 19 cases (2.2). Check packet size against the index, or look for EOI.
10. **If segment rotation is used, a reader must tolerate an unreadable newest segment** (2.2). FFmpeg's segment muxer is untested under a kill (2.6).
11. **inferred: a process crash does not need fsync, provided each frame and index record is written unbuffered before it is acknowledged** (2.2).
    - It rests on the unsourced WriteFile premise and on 2 (PyAV 19) plus 5 (PyAV 18) steady-state kills per variant.
    - Tonight's 77 cells used no fsync and dropped nothing (2.8).
    - fsync per frame costs about 0.4 ms p50 and up to 8.7 ms per frame for one writer (2.13).
    - Power-loss durability is untested.
12. **Build passthrough streams with `add_mux_stream` (MJPEG) or `add_stream_from_template` (FFV1), never `add_stream(codec)` + extradata** (2.1).
13. **Quote capacity numbers as "16 logical CPUs, Defender on".**
    - They come from a P-core-pinned run, with per-call p50 1.6-3.3x the 28-CPU daytime run (2.10).
    - Medians of the same config differ between items (files p99.9 20.3 vs 8.4 ms; append p50 0.553 vs 0.365 ms) (2.10).

## 5. Run flags and caveats that apply to this topic

- **P-cores only.** Every WT item ran with its affinity set to logical CPUs 0-15 before the child was created (`RU/results/BENCH_RUN_2300_LOG.jsonl` `"affinity": "pcores"`; code `RU/scripts/bench_runner/run_queue.py:21-22`, `:441-446`).
  - The write-cell JSONs do not record per-process affinity.
  - measured (verifier functional check, no timing): a parent python pinned to 0-15, then a `uv run --script` child, then a multiprocessing `spawn` grandchild, all reported 16 CPUs (0-15). This is the same chain as runner → uv → bench_write.py → camera processes (scripts `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step2/wt_vm/aff_parent.py` and `aff_child.py`; code `SCR/bench_write.py:315`).
  - MsMpEng and SearchIndexer are system processes and were not pinned.
  - `sys busy %` is a share of all 28 logical CPUs (code `SCR/bench_write.py:384-386`).
- **The libx265 affinity widening (items 1-3) does not apply here.** It was seen in intra_compare single-stream items (`RU/results/BENCH_RUN_2300_SUMMARY.md` section 3, flag 2). The runner sets the affinity again before each item (code `run_queue.py:441-446`), and the WT benches encode nothing (code `SCR/bench_write.py:7-11`).
- **Per-write latencies are higher than the contaminated daytime run** for every writer (2.10). The old numbers are not lower bounds everywhere. P-core pinning is a possible cause (inferred).
- **Defender real-time protection ON, unchanged.** Its cost is part of every timing and is reported separately (2.9). The per-cell MsMpEng figures cover the timed window only, which ends at writer close; item totals show more Defender work outside it. No scan event during any WT item. The exclusion list is NOT VERIFIED.
- **CPU timer granularity 15.625 ms.** psutil CPU readings come in multiples of 1/64 s.
  - measured: MsMpEng readings 0.03125 and 0.15625 s (`first_read_check_5000.json`).
  - inferred: MsMpEng and bench CPU differences under about 0.05 s per cell are not resolved. This does not affect the 1-27 s per-cell Defender comparisons.
- **Single runs.** Every core_av19 cell, every long cell, the first-read check and the usability bench ran once. Their tail values are single samples. Only focus16_av19 and models16_av19 have 3 reps.
- **Between-item spread.** Medians of the same files/thread config differ between focus16_av19 and models16_av19 (p99.9 20.3 vs 8.4 ms, bench CPU 1.09 vs 0.69), with overlapping rep ranges; append p50 differs with disjoint ranges (2.10). Treat tail differences under about 1.5x as unresolved.
- **Background load.** CPU before each WT item was 3.3-6.8 % mean; no item had `load_over_15pct`. SearchIndexer was the top process before WT-IDLE-BEFORE (8.48 CPU-s) and WT-LONG-AV19 (9.83 CPU-s) in the 10 s pre-item window (`RU/results/BENCH_RUN_2300_LOG.jsonl`, `load_before.top10_cpu_s_in_window`). SearchIndexer CPU during cells was not recorded.
- **Leftover processes.** The runner flagged "leftover processes after item (listed, not killed)" on 9 of 10 WT items (all but WT-LONG-AV19). The list holds the monitoring Claude session's bash, uv and python watcher processes, one of them under the skellycam `.venv`; claude.exe and Code.exe also appear in the pre-item top-10 (`RU/results/BENCH_RUN_2300_LOG.jsonl`, `flags`, `leftover_processes`). No bench process was left behind (`RES/BENCH.md` line 30).
- **Disk C: is the OS disk** (WD_BLACK SN850X NVMe, the only disk; `RES/BENCH.md` header).
- **Flags that do not apply to this topic:**
  - NVENC session limit, nvJPEG quality miss, WebCodecs scrub errors and N=8 `<video>` stalls: no encode or playback here.
  - uncompressed_intra lossless check: this topic's byte-exactness is from the functional T1 files (2.1).

## 6. Not tested / limits / NOT VERIFIED

- **Not run as paced multi-camera cells:** `variants` (mkv defaults, mkv_flush_cluster1, fmp4_1s, hybrid), `intra_ffv1`, `repeat`, the 4-camera and in-loop `models` cells, every fsync writer, files_subdirs and mkvseg10 write cells, the 108k-frame `usability_1h`, and 16 x 1080p60 in the core matrix.
  - Sources: `RES/BENCH.md` section 2; `RU/results/BENCH_QUEUE_2300.md` lines 238, 240, 243.
  - The queue dropped the variants and mkvseg10 because their single-writer mux cost is covered by CR-FRAG-MJPEG-PYAV19 (2.8, measured under PyAV 19.0.2 on the quiet machine). Their multi-camera paced write cost is NOT VERIFIED.
- **FFV1 wrapper cost** is NOT MEASURED (no `intra_ffv1` cells).
- **fmp4_frame_flush over 10 minutes** is NOT MEASURED.
- **The empty-packet MKV flush:** NOT VERIFIED:
  - write cost;
  - clean-close byte-exactness;
  - more than 3 kills;
  - multi-hour files and Cues growth;
  - non-FFmpeg parsers (Chromium, Media Foundation, mkvalidator);
  - future FFmpeg behaviour.
- **Kill loss on a quiet machine with 5 kills per variant** (the planned `functional_rerun_quiet`, with kill-at-start, -rotation and -close cases) was not run. Kill results here are 2 kills per variant under PyAV 19, steady-state, at 720p60.
- **Multi-camera fsync cost** on the quiet machine is NOT MEASURED. The only quiet fsync data is one unpaced writer (2.13).
- **Power-loss / OS-crash durability** is not tested. The premise that data passed to WriteFile survives a process kill is inferred, with no Microsoft primary source.
- **The FFmpeg segment muxer under a kill** is NOT TESTED. The cause of the unreadable newest mkvseg segment is NOT VERIFIED.
- **Defender work outside the timed window** (2.9 item excess) is unattributed; close-time scans of one-file recordings are NOT VERIFIED.
- **Defender exclusions** cannot be read without admin. That Defender causes the folder first-read delay is inferred, because an exclusion test was not allowed (2.12).
- **Defender's handling of repeated content** is NOT VERIFIED: the payloads are looped 19-frame 1080p and 891-frame 720p sets.
- **The files layout's extra system residual** (about 0.4-0.7 logical CPU, 2.10) is not attributed to a process.
- **The 12.8 % extra disk writes for files** (2.8) are not separated from lazy-writer carry-over.
- **Queues shorter than 2.87 s** are NOT VERIFIED (implication 7).
- **1080p60 reuses 1080p30 frames**; real 1080p60 camera frames are NOT TESTED.
- **Simulated cameras:** USB, driver queue and capture-API timing are not modelled.
- **Warm cache only.** Cold-cache reads need admin or a reboot.
- **Scaling to 1 h recordings** (108k frames per camera) is NOT VERIFIED; usability used 18,000 frames. Long-file cv2 frame counts for MKV are wrong at 54k frames (other topic, 3.1).
- **The cause of the higher latency tonight** (P-core pinning vs other factors) is NOT VERIFIED (2.10).
- **SearchIndexer CPU during write cells** is not recorded (code, 2.7). The Windows Search display-path quirk is NOT VERIFIED.
- **Platform and hardware target:** Windows only, NTFS on one NVMe SSD, one i7-14700K with 16 logical CPUs used. macOS/Linux file systems, other disks and the 2020-era CPUs of the hardware target are NOT VERIFIED.
- **No timing at target B or with re-encoded payloads**; every payload is camera JPEG bytes (inferred to be about target A, see the header).

## 7. How to reproduce (repo root `C:/Users/Dom/GitHub/freemocap/skellycam`)

Set `UV_CACHE_DIR` to a scratchpad folder first. Media goes to `MEDIA` and is deleted by each script. Timed items need a quiet machine: one item at a time, P-core affinity, nothing else running except monitoring shells (section 5, leftover processes).

```sh
# Timed items exactly as run in 20261109T230007 (runner sets P-core affinity, logs load + MsMpEng per item)
uv run --script research/skellycam_recording/recording_upgrade/scripts/bench_runner/run_queue.py \
  --only WT-IDLE-BEFORE,WT-FOCUS16-AV19,WT-FIRST-READ,WT-IDLE-AFTER,WT-MODELS16-AV19,WT-CORE-AV19,WT-CORE60-AV19,WT-IDLE-AFTER2,WT-USABILITY-18K,WT-LONG-AV19 \
  --deadline HH:MM
# The item commands (from results/bench_queue_2300.json; each script has a PEP 723 header pinning av==19.0.2):
S=research/skellycam_recording/recording_upgrade/scripts
uv run --script $S/bench_runner/idle_baseline.py --tag before_focus16_av19
uv run --script $S/write_throughput/run_matrix.py --set core --profiles 1080p60 --writers files,append,mkv_flush,fmp4_frame_flush --cams 16 --reps 3 --outdir-name focus16_av19
uv run --script $S/write_throughput/first_read_check.py --frames 5000
uv run --script $S/write_throughput/run_matrix.py --set models --profiles 1080p60 --models thread,process_shared --writers files,append,mkv_flush --cams 16 --duration 30 --reps 3 --outdir-name models16_av19_shared_vs_thread
uv run --script $S/write_throughput/run_matrix.py --set core --writers files,append,mkv_flush,fmp4_frame_flush --cams 1,4,8,16 --profiles 720p30,1080p30 --duration 20 --outdir-name core_av19
uv run --script $S/write_throughput/run_matrix.py --set core --writers files,append,mkv_flush,fmp4_frame_flush --cams 1,4,8 --profiles 1080p60 --duration 20 --outdir-name core_av19
uv run --script $S/write_throughput/bench_usability.py --formats files,files_subdirs,append,mkv_flush,fmp4_frame_flush --frames 18000 --robocopy
uv run --script $S/write_throughput/run_matrix.py --set long --outdir-name long_av19

# Functional (PyAV 19.0.2), unchanged from the previous version
uv run --no-project --python 3.12 --with av==19.0.2 --with numpy==2.2.6 --with psutil==7.2.2 --with opencv-python==4.12.0.88 \
  python $S/write_throughput/functional_tests.py --only T1,T4,T5 \
  --variants files,append,mkv,mkv_flush,fmp4_frame,fmp4_frame_flush,fmp4_1s,fmp4_hybrid,mkvseg10 --repeats 2 --tag _av19.0.2
uv run --no-project --python 3.12 --with av==19.0.2 --with numpy==2.2.6 --with psutil==7.2.2 --with opencv-python==4.12.0.88 \
  python $S/write_throughput/functional_tests.py --only T1,T4 --variants mkv_flush_cluster1,fmp4_1s_flush --repeats 2 --tag _av19.0.2_gapfill
uv run --script $S/write_throughput/av19_checks/run_functional_av19.py --only T2,T6 --tag _av19.0.2_t2t6
uv run --script $S/write_throughput/av19_checks/probe_api.py
uv run --script $S/write_throughput/av19_checks/mkv_checks_av19.py
uv run --script $S/write_throughput/av19_checks/mkv_emptypkt_av19.py
uv run --script $S/write_throughput/av19_checks/mkv_emptypkt_log_av19.py
uv run --script $S/write_throughput/av19_checks/mkv_emptypkt_ts_av19.py
uv run --script $S/write_throughput/av19_checks/meta_seek_av19.py
uv run --script C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/write_throughput/verify_emptypkt_av19.py
```

Notes:
- The original command for `functional_results_av19.0.2.*` was not recorded (NOT VERIFIED). Without `--variants` the script runs all 15 variants (code `functional_tests.py:470`).
- The extradata repro always writes `functional/repro_pyav_add_stream_extradata.json` (code `repro_pyav_add_stream_extradata.py:62`). Back up the PyAV 18 file first, then rename the new output to `..._av19.0.2.json`.
- Medians (min-max) in this file were recomputed from the raw cell JSONs (`summary.*`) with throwaway scripts at `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step2/wt/wt_stats.py` and, for the revision (ratios, residual, MsMpEng sums), `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step2/wt_rev/chk.py`. Temporary files; they match `RES/BENCH.md` except that BENCH.md truncates the core MsMpEng cell sum to 87.5 (JSON sum 87.58).
- `RES/bench/bench_summary.md` mixes PyAV 18 and PyAV 19 sets with no env column. Use the set folder names ending `_av19` and `usability_18000.json` for this run.
- Windows Search checks: OLE DB `Provider=Search.CollatorDSO` query (outputs `RES/wsearch_scope_check_20261109.json`, `RES/wsearch_itemurl_check_20261109.json`).
- FFmpeg source excerpts: `RES/source/ffmpeg_n9.0.2_mux_flush_excerpts.txt`. Full fetched copies, including mux.c:1075-1092, are in `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/write_throughput/verify_src/`.

## 8. Changes from the previous version

Replaced with quiet-run data (PyAV 19.0.2, run `20261109T230007`):

| Old entry (contaminated / PyAV 18 env) | New entry | Effect |
|---|---|---|
| focus16 table, files p50 1.299 ms, append 0.179 | focus16_av19: files 2.111, append 0.553 (3.2) | Tonight is higher; the old "lower bound" framing is removed (2.10) |
| MsMpEng files 31.7 s vs append 7.1 s per 30 s, "about 4x the one-file layouts" | files 26.8 s vs 1.16-1.52 s, at the idle level of 1.23-1.53 (2.9) | **Contradicted inside the timed window:** one-file layouts add no measurable Defender work before writer close. Work after close is not covered (2.9). inferred: the old append range reflected background activity |
| models16: process_shared per-call p50 0.262-0.279 vs 0.920-1.380 ms; tick->written mixed | models16_av19 table (2.11) | Open question answered: both models drop nothing; process_shared saves CPU and costs tick->written p99 |
| usability_27000: first read 116.42 s, frame table 0.009/0.442/1.008 s | usability_18000: 78.36 s, 0.016/0.233/0.638 s (2.12) | Same conclusion, new numbers |
| first_read_check_3000 (11.35 s) | first_read_check_5000 (20.594 s, all Defender CPU) (2.12) | Per-file cost about the same (3.8 vs 4.1 ms); the 3000-file result is kept as background agreement |
| "30 s cells did not reach the disk; sustained unknown" | long_av19: 10 min at 156.9 MB/s, 0 drops, disk delta ≥ payload for files and append (2.8) | Answered |
| "No idle baseline" | `idle_baseline_av19.jsonl`, 3 baselines (2.9) | Answered |
| "bench_write.py / run_matrix.py not smoke-tested under PyAV 19" | `env.av` = 19.0.2 in all 77 cells (header) | Resolved |
| Section 5 "Pending tonight's bench" | Removed; what did not run is listed in section 6 | - |
| files_fsync / append_fsync1s stalls (core16_extra) | Kept as background (2.13), with the quiet one-writer fsync data from crash_resilience | Not re-run |

The functional findings (2.1-2.7) are unchanged in substance. They were verified in the previous `RES/VERIFY_provenance.md` and `RES/VERIFY_method.md` passes (now `*.prev.md`), and the corrections from those passes are kept. Section 9 lists this revision's changes.

## 9. Verification (2026-11-10)

**What the verifiers checked.**
- Provenance (`RES/VERIFY_provenance.md`): recomputed every cited `summary.*` field from all 77 cell JSONs, plus `usability_18000.json`, `first_read_check_{5000,3000}.json`, `idle_baseline_av19.jsonl`, the WT lines of `RU/results/BENCH_RUN_2300_LOG.jsonl`, `fsync_pyav19.json` and the daytime `bench/focus16/`. Re-checked FFmpeg n9.0.2 and RFC 9559 lines and every code citation. Result: all cells PyAV 19.0.2 with 0 drops; nearly every number matches.
- Method (`RES/VERIFY_method.md`): spot-checked the same JSON sets, the MsMpEng window code, process_shared CPU accounting and the first-read readings. Ran one functional check (affinity inheritance through uv and spawn; no timing).
- Reviser (this pass): re-checked each refutation against the JSON before applying it (script `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step2/wt_rev/chk.py`), and read the cited lines of `chromium_codecs/tables.md`, `jpeg_passthrough/BENCH.md`, `crash_resilience/BENCH.md`, `BENCH_QUEUE_2300.md`, `functional_results_fmp4_flush.md`, `bench_usability.py` and HANDOFF.md. No timed measurement was run.

**Refuted and corrected.**
- 3.2 footer: each cell wrote 28,800/28,800 frames (86,400 per writer over 3 reps), not 86,400 per cell.
- 2.10 core table: "the containers barely grow" removed. files grows most in absolute ms; the one-file layouts rise 2.5-3.5x from 8 to 16 cams at 1080p30 and stay nearly flat at 720p30.
- 2.11 and implication 6: process_shared uses 28-49 % of the thread model's bench CPU (not "a third to a half") and raises tick->written p99 1.25-2.1x (not "doubles").
- 2.10 between-item spread: medians differ, but the files rep ranges overlap; only append p50 has disjoint ranges. Section 5 and implication 13 changed to match.
- 2.14: Chromium citation corrected to `tables.md` lines 105-119 and 165-176.
- 2.8: grab-late max corrected to 1.3-2.0 ms (medians per writer; 1.1-2.3 over all reps).
- Implication 4: the empty-packet variant is "the only variant with 0 loss in every kill (3 kills)"; PyAV 18 fmp4_frame_flush also had a 0-loss kill (1, 1, 1, 1, 0).

**Weak claims relabelled or rescoped.**
- Header: camera JPEGs nearest IJG q94 is measured; "about target A" is inferred (HANDOFF 1.1), with the HANDOFF line 182 size caveat.
- 2.2: the unbuffered premise applies to the files and append writers and the sidecar index only.
- 2.9: Defender findings scoped to the timed window, which ends at writer close; item-total excess table added (core sum 87.6, core60 added); per-file cost given as a 0.9-1.7 ms lower bound that depends on concurrency.
- 2.10: files cost given as ranges (bench + Defender 1.6-2.0 logical CPUs; whole system 1.2-2.0 above append) with the unattributed residual named; long-cell mkv_flush tail added; daytime factor given as 1.6-3.3x (append 2.0-3.1x), the CPU %/cam comparison dropped and the system-busy observation added as inferred support.
- 2.12 / 3.4: random-read and first-image columns labelled "after a full read".
- 2.8: CR-FRAG-MJPEG-PYAV19 single-writer cost cross-referenced; the 12.8 % extra disk writes now name lazy-writer carry-over as an alternative.
- Implications 1-2 scoped to this machine; implication 2 ranges widened to 0.25-0.52 ms and 0.23-0.39 logical CPUs; implication 7 recommends the tested 2.87 s queue only; implication 11 labelled inferred.
- Section 5: affinity inheritance relabelled measured (verifier check); libx265 non-applicability relabelled code; leftover-process flag added.
- 3.1: long-file cv2 MKV frame-count caveat added.

**Still NOT VERIFIED** (details in section 6): paced multi-camera cost of the variants, mkvseg10, fsync writers and FFV1; 10-minute fMP4 cost; the empty-packet MKV flush beyond 3 kills and an open-file check; kill loss with 5 kills per variant and kills at start, rotation or close; power-loss durability and the WriteFile premise; Defender work after writer close and Defender as the cause of the first-read delay; the files residual system CPU; the cause of the higher latency tonight; queues shorter than 2.87 s; cold cache, 1 h recordings, real 1080p60 frames; other CPUs, disks and operating systems in the hardware target; target B or re-encoded payloads.
