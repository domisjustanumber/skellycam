# crash_resilience (goal G2) - NOTES

Resumable / crash-tolerant recording files. Machine "Gerald" (Windows 11, i7-14700K, RTX 3070), 2026-11-09.
Functional tests only: **no timing, throughput or CPU numbers are reported from this stage** (other agents ran
concurrently). Timing questions are left to the benchmark scripts in section 9.

Labels: **measured** = a result file of this study (path given) or of a prior study; **source** = primary source
(FFmpeg source at a pinned tag, RFC, Python docs), accessed 2026-11-09; **code** = repo source; **inferred** =
reasoning, kept short. All result paths are relative to `research/skellycam_recording/recording_upgrade/results/crash_resilience/`
unless they start with `research/`.

Versions used (measured, `kill_matrix_a.json` -> `env`): Python 3.12.13, PyAV 18.0.0 (libavformat 62.12.102, libavcodec
62.28.102), OpenCV 4.12.0, ffmpeg/ffprobe CLI 9.0.2 (gyan full build, libavformat 63.1.102), SVT-AV1 v4.1.0 (encoder
banner in the run logs), Electron 35.7.5 = Chromium 134.0.6998.205 and Electron 45.2.3 (see section 5).
PyAV 18's libavformat 62.12 is FFmpeg 8.1: source `libavformat/version.h` at tag n8.1 has `LIBAVFORMAT_VERSION_MINOR 12`
(n8.0 has 3, n9.0.2 has major 63). FFmpeg citations below are to tag **n8.1** (what PyAV runs) unless noted.

---------------------------------------------------------------------------------------------------------------------

## 1. Bottom line

- A plain (non-fragmented) MP4 keeps **0 readable frames** after a hard kill at any point, for every payload tested
  (MJPEG, FFV1, AV1, NVENC H.264), with or without `flush_packets=1`, and `ffmpeg -c copy` cannot repair it (measured,
  `summary.md` kill table rows `mp4`, `mp4+fp`; same as prior p11, `research/frame_ring_buffer/prototypes/results/p11_crash_container.md`).
  Power-loss truncation of a plain MP4 also gave 0 frames in every cut (measured, `summary.md` truncation table).
- The biggest hidden loss is not the container but **write buffering inside the process**: FFmpeg's `file` protocol
  buffers 256 KiB and turns per-packet flushing off for regular files (source, section 2). With MJPEG at ~57 KB/frame
  that is 4-5 frames (262144 / 56759 = 4.6); with AV1 at ~1.5 KB/frame it was the whole 5 s test file (0 of 150 frames survived in every
  unflushed single-file AV1 container; the segment muxer's closed 1 s segments survived) (measured, `summary.md` kill table, av1 rows without `+fp`).
- Setting the AVFormatContext option **`flush_packets=1`** removes that loss in every single-file container tested
  (measured): what remains is only what the muxer itself holds in memory:
  - Matroska/WebM: the open Cluster. For intra-only payloads (MJPEG, FFV1 g=1) that is **1 frame** (149/150, 74/75);
    for a GOP-30 inter codec it is up to one GOP (120/150) unless `cluster_size_limit=0` (149/150).
  - fragmented MP4: the open fragment: 1 frame with `frag_every_frame` (149/150), one GOP with `frag_keyframe` on
    inter codecs (120/150), up to 1 s with `frag_duration=1000000` (120/150).
  - NUT, AVI, IVF, raw `.mjpeg` + index, folder of JPEGs: **nothing** beyond the frame being written (150/150).
- The `segment` muxer did **not** pass `flush_packets` to its per-segment muxers (seg_mkv: 148/150 with or without
  `+fp`), and with `segment_format=mp4` the open segment is lost entirely (120/150) (measured, `summary.md`).
- Encoders hold frames too, and no container can save them: at a live 30 fps feed, SVT-AV1 (preset 10, GOP 30) had
  muxed only 35 of 75 fed frames when killed (40 frames, about 1.3 s, inside the encoder); h264_nvenc held 2
  (measured, `summary.md` kill table `rt` column, av1 and h264nv rows).
- Unfinalized Matroska is readable without repair by ffprobe, PyAV and cv2 (frames, byte-exact MJPEG, mid-file seek)
  but reports no duration; fragmented MP4 reports the duration of the complete fragments (measured, kill table
  `dur` and `PyAV seek` columns). `ffmpeg -c copy` to `.mkv` restored duration and seeking and kept every readable
  frame in every case where any frame was readable (measured, kill table `rep` column, truncation `repaired ratio`).
- Under emulated power loss (24 prefix cuts per format), Matroska never lost more than 1 frame beyond the cut and never
  produced a torn frame; fMP4, NUT, AVI, raw MJPEG and the JPEG folder hand the **torn last JPEG to the decoder**, and
  ffprobe/PyAV/cv2 all count it as a frame (ffprobe = ideal + 1 in 20-23 of 24 cuts) - a reader must validate it
  (measured, `truncation_a.json`; section 4.2).
- sfn26's Rust recorder writes a plain MP4 through an ffmpeg child (code, section 6). Killing ffmpeg (what
  `VideoRecorder::drop` does) or the whole process tree leaves 0 readable frames; killing only the feeding parent lets
  ffmpeg see EOF and finalize the file (300/300) (measured, `sfn26_pipe.md`).
- 'Resumable' is defined and prototyped in Python (section 7): journal + per-segment MKV with `flush_packets=1` +
  CRC'd binary timestamp sidecar. In 9 crash scenarios (process kills, a double crash, and 5 emulated power losses
  that also tear the journal and the sidecar) every session reopened, repaired only its last segment, continued with
  unique increasing frame numbers on the same clock, kept video frames == timestamp records, and kept every MJPEG frame
  byte-exact (measured, `resumable_demo.md`).
- Electron 35.7.5 and 45.2.3 both play unfinalized MKV/WebM (AV1, H.264) to the end, including prefix cuts (duration
  Infinity, seek works), and unfinalized fMP4 written with `flush_packets=1` with a finite duration; a torn fMP4 sample
  stops playback with a MediaError (AV1 in both versions, H.264 only in Electron 35). Neither opens MJPEG/FFV1 in any
  container, nor NUT/AVI/IVF files at all (measured, section 5).
- Timestamp sidecar: a per-row `flush()` (the sfn26 `csv_writer.rs` pattern) survives a process kill completely; no
  flush lost rows (measured, `sidecar_durability.md`). pandas `read_csv` accepted a torn last CSV row as data in 23 of
  24 cuts and returned **silently wrong integers** in 6 (measured). A fixed-size binary record with a CRC detected every
  torn or zero-filled record (measured).

### 1b. What this suggests (inferred - design reasoning, not a measurement)
- For G1 (MJPEG passthrough): Matroska, `flush_packets=1`, application-level segments (not the `segment` muxer),
  journal + CRC'd binary timestamp sidecar, as in the prototype. Loss on a process kill = the frame being written;
  every surviving JPEG stays byte-exact; ffprobe/PyAV/cv2 read it without repair; `-c copy` finalizes it.
- NUT/AVI/raw+index lose nothing extra on a kill, but Chromium cannot open NUT/AVI, and NUT/AVI/raw hand torn frames
  to decoders after a power cut; their advantage over MKV+fp is one frame.
- For inter codecs (G6/G7), container settings bound the loss to one frame only with `cluster_size_limit=0` (MKV/WebM)
  or `frag_every_frame` (fMP4); the encoder's own lookahead (SVT-AV1: ~40 frames at preset 10) is lost regardless,
  so the encoder latency settings matter as much as the container.
- Plain MP4 (today's skellycam path and sfn26) should not be the recording container; at most a finalize/remux target.

## 2. Mechanisms (why frames are lost), from source

| # | Fact | Label / citation |
|---|---|---|
| M1 | The `file` protocol sets `max_packet_size = 262144` for written regular files: "Buffer writes more than the default 32k to improve throughput especially with networked file systems" | source: FFmpeg n8.1 `libavformat/file.c:318-321`; same in n9.0.2 `file.c:324-327` |
| M2 | ... and sets `min_packet_size = max_packet_size`: "Disable per-packet flushing by default to improve throughput especially with networked file systems" | source: n8.1 `file.c:323-326`; n9.0.2 `file.c:329-332` |
| M3 | After each packet the muxer only writes a FLUSH_POINT marker unless `flush_packets == 1`; `flush_packets` default is -1 | source: n8.1 `libavformat/mux.c:426-434` (`flush_if_needed`), `options_table.h:83` (`{.i64 = -1}`) |
| M4 | A FLUSH_POINT flushes only `if (s->buf_ptr - s->buffer >= s->min_packet_size)`, i.e. once 256 KiB are buffered | source: n8.1 `libavformat/aviobuf.c:464-470` |
| M5 | Observed on disk: killed unflushed files are exact multiples of 262144 bytes (MP4: plus the few header bytes written before the data, e.g. 3932204 = 15 x 262144 + 44), e.g. mkv drained 8126464 = 31 x 262144 | measured: `kill_matrix_a.json` (`bytes`) |
| M6 | Matroska builds each Cluster in a dynamic buffer (`cluster_bc`) and writes it to the file only in `mkv_end_cluster` | source: n8.1 `libavformat/matroskaenc.c:2961-2977`, cluster start `:3084-3090` |
| M7 | A new Cluster starts when size > `cluster_size_limit` or time > `cluster_time_limit`, or on a video key frame once the cluster is > 4 KiB; defaults 5 MiB / 5000 ms for seekable output | source: n8.1 `matroskaenc.c:2722-2733`, `:3160-3166` |
| M8 | mov/mp4 decides to flush a fragment when the NEXT packet arrives (frag_duration, frag_keyframe on a key packet, or frag_every_frame), so the current fragment is always in memory | source: n8.1 `libavformat/movenc.c:7230-7257` (condition at 7234, `mov_auto_flush_fragment` at 7257) |
| M9 | Matroska/EBML allow unknown-size Segment and Cluster elements ("unknownsizeallowed: True"), which is what an unfinalized writer leaves | source: RFC 9559 §5.1 and §5.1.3; RFC 8794 §6.2 "Unknown Data Size" |
| M10 | `Popen.kill()` on Windows: "kill() is an alias for terminate()"; terminate: "the Win32 API function TerminateProcess() is called" | source: https://docs.python.org/3.12/library/subprocess.html |
| M11 | `os.fsync`: "on Windows, the MS _commit() function"; "first do f.flush(), and then do os.fsync(f.fileno())" | source: https://docs.python.org/3.12/library/os.html#os.fsync |
| M12 | `segment` muxer feeds packets to its inner muxer with `ff_write_chained` and lists a segment only when it is closed | source: n8.1 `libavformat/segment.c:988-990`; measured: `list.csv` had 4 lines for 5 files after a kill (`kill_matrix_a.json` -> `read.segment_list_lines`) |

- inferred: M1-M7 explain p11's `mjpeg_mkv killed_idle` 298/300 (p11 frames were ~240 KB: 72193863 B / 300, so about
  1 frame in the 256 KiB buffer + 1 in the open cluster) and the nvenc_mkv losses (open GOP cluster), now confirmed by the `+fp` variants losing exactly the open
  cluster.

## 3. Method

### 3.1 Inputs
- Real camera JPEG bytes from corpus set `c930e_720p_flash` (1280x720 MJPEG 4:2:2, median 56759 B/frame, 891 frames;
  `corpus/index.json`). N = 150 frames per recording (5 s at 30 fps). `busy` runs loop frames 0-149 past 150.
- MJPEG payload = the camera's JPEG bytes as packets (passthrough, no decode). FFV1 / AV1 / H.264 payloads: JPEG decoded
  by PyAV's mjpeg decoder, converted with `reformat()` (FFV1 `yuv422p`, level 3, g=1, slices 4, slicecrc 1; AV1
  `libsvtav1` preset 10 crf 35 g=30 `yuv420p`; `h264_nvenc` p4 vbr cq 23 g=30 bf=0 `yuv420p`).
- nvidia-smi `encoder.stats.sessionCount, utilization.gpu`: before the av1/h264 matrix `0, 8 %`, after `0, 28 %`;
  each h264nv run records its own before/after pair (`kill_matrix_b.json` -> `nvidia_smi_before_after`).

### 3.2 Writers and kill modes (`scripts/crash_resilience/writer_child.py`, `run_kill_matrix.py`)
- Each recording is written by a child process; after every `mux()` the child prints `M <packets_muxed> <frames_fed>`
  through a pipe that survives its death, so "what libavformat had accepted" is known exactly.
- Modes: `clean` (close normally); `idle:1`, `idle:75` (killed while blocked after K frames fed, encoder not drained);
  `drained:150` (all frames fed, encoder drained, killed before close = the image a crash at the very end leaves);
  `busy` (killed while muxing flat out after 75 packets); `rt` (fed at 30 fps, killed after 75 frames fed).
- Kill = TerminateProcess on the writer interpreter (`os.kill(pid, SIGTERM)` on the PID the child prints), then on the
  venv launcher. The venv `python.exe` is a launcher that starts a second interpreter (measured,
  `launcher_kill_check.json`: launcher 43180 != inner 51564); killing the launcher alone also ended the inner process
  (heartbeat stopped, `inner_still_running: false`), but a first `busy` pass that killed only the launcher overshot by
  up to ~930 frames in one run, so `busy`/`rt` were re-run with the direct PID kill (measured; the rows in
  `kill_matrix_*.json` are the re-run).
- Containers (`common_cr.py` `CONTAINERS`; `+fp` = same plus `flush_packets=1`): `mkv` (PyAV defaults), `mkv_cl0`
  (`cluster_size_limit=0`, `cluster_time_limit=0`), `mkv_resv` (`reserve_index_space=262144`), `webm`, `webm_cl0`,
  `fmp4_kf` (`movflags=frag_keyframe+empty_moov+default_base_moof`), `fmp4_every` (`frag_every_frame+empty_moov+default_base_moof`),
  `fmp4_1s` (`empty_moov+default_base_moof`, `frag_duration=1000000`), `mp4` (plain), `seg_mkv` / `seg_mp4`
  (`segment`, `segment_time=1`, `reset_timestamps=0`, `segment_list_type=csv`), `nut`, `avi`, `ivf` (AV1 only),
  `rawidx` (own format: JPEGs appended to `frames.mjpeg`, then a 32-byte `<qQIIq>` record frame/offset/size/crc32/ts
  appended to `frames.idx`, both flushed per frame), `folder` (one `frame_%06d.jpg` per frame).
- 98 payload x container combos x 6 modes. Refused combos are recorded (MJPEG in WebM: `ValueError: 'webm' format does
  not support 'mjpeg' codec`). FFV1 in MP4 and AV1 in AVI were accepted by the muxers (measured; FFV1-in-MP4 is not a
  registered mapping - inferred, NOT VERIFIED against the ISO registry).

### 3.3 Readers (all on the file as left on disk, no repair) - `common_cr.py`
- `ffprobe -v error -count_frames -select_streams v:0` (nb_read_frames, stream/format duration).
- PyAV: demux + decode until EOF or the **first exception** (deliberately naive), count frames; MJPEG packets compared
  by SHA-1 to the camera JPEG at the same index; seek to the middle decoded pts (`backward=True`) and decode one frame.
- cv2: `VideoCapture(path, CAP_FFMPEG)` read loop; then `CAP_PROP_POS_FRAMES` = half and one `read()`.
- Repair: `ffmpeg -v error -i <in> -map 0:v:0 -c copy <out>.mkv` (and a PyAV `-c copy` remux), then re-read.

### 3.4 Power-loss emulation (`run_truncation.py`)
- Source image = the `drained:150` file (no trailer). 24 cuts per variant: 20 seeded-random offsets + byte 64, middle of
  the first packet, middle of the median packet, size-1. Multi-file kinds are cut in write order; for `rawidx` the
  index keeps only records whose data were fully written (the writer writes data before index).
- ideal = packets of the clean file entirely before the cut (ffprobe `pos + size`), approximate to +-1 frame.
- 20-24 of the 24 cuts fell inside a packet for most variants (column "mid-packet" in `summary.md`).

### 3.5 Commands (from the repo root, skellycam venv)
```
P=.venv/Scripts/python.exe; S=research/skellycam_recording/recording_upgrade/scripts/crash_resilience
$P $S/run_kill_matrix.py --payloads mjpeg,ffv1 --tag kill_matrix_a
$P $S/run_kill_matrix.py --payloads av1,h264nv --tag kill_matrix_b
$P $S/run_kill_matrix.py --payloads mjpeg,ffv1 --modes busy,rt --resume --replace-modes --tag kill_matrix_a
$P $S/run_kill_matrix.py --payloads av1,h264nv --modes busy,rt --resume --replace-modes --tag kill_matrix_b
$P $S/run_truncation.py --payloads mjpeg,ffv1 --workers 3 --tag truncation_a
$P $S/run_truncation.py --payloads av1,h264nv --workers 3 --tag truncation_b
$P $S/run_electron.py --label e35            # Electron 35.7.5 (skellycam-ui pin)
$P $S/run_electron.py --label e45 --electron C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/shared/electron-latest/node_modules/electron/dist/electron.exe --list C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/crash_resilience/electron_list.json
$P $S/sfn26_pipe_test.py --n 600
$P $S/sfn26_pipe_test.py --n 150 --tag sfn26_pipe_n150
$P $S/run_resumable_demo.py
$P $S/sidecar_durability.py
$P $S/launcher_kill_check.py
$P $S/pict_type_check.py
$P $S/summarize.py                           # -> summary.md
```
`pyav_remux_opaque_check.json` and `cv2_framecount_after_repair.json` come from short inline checks that call
`common_cr.remux_pyav` / `common_cr.cv2_read` on the media files named inside each JSON.
(The first kill_matrix_a pass was terminated externally at 11:12 after 176 runs, no traceback; it was completed with
`--resume`, which skips rows already in the JSON.)

## 4. Results

Full per-run tables: `kill_matrix_a.md`, `kill_matrix_b.md`, `truncation_a.md`, `truncation_b.md`; condensed:
`summary.md`. The tables below are extracts of `summary.md` (ffprobe counts; PyAV and cv2 gave the same count in
every kill row).

### 4.1 Hard kill - frames readable without repair / packets muxed before the kill (measured)

MJPEG passthrough (camera bytes):

| container | drained (150 fed) | idle (75 fed) | rt (75 fed @30 fps) | idle:1 | byte-exact (drained) | duration w/o repair | repair -> mkv |
|---|---|---|---|---|---|---|---|
| mkv | 146/150 | 70/75 | 70/75 | 0 | 146 | none | 146 |
| mkv+fp | **149/150** | 74/75 | 74/75 | 0 | 149 | none | 149 |
| mkv_cl0+fp / mkv_resv+fp | 149/150 | 74/75 | 74/75 | 0 | 149 | none | 149 |
| fmp4_kf / fmp4_every | 147/150 | 71/75 | 71/75 | 0 | 146 | 4.90 s | 147 |
| fmp4_every+fp | 149/150 | 74/75 | 74/75 | 0 | 149 | 4.97 s | 149 |
| fmp4_1s+fp | 120/150 | 60/75 | 60/75 | 0 | 120 | 4.00 s | 120 |
| mp4 / mp4+fp | **0/150** | 0/75 | 0/75 | 0 | - | none | **0** |
| seg_mkv (= +fp) | 148/150 | 69/75 | 69/75 | 0 | 148 | none | 148 |
| seg_mp4 (= +fp) | 120/150 | 60/75 | 60/75 | 0 | 120 | none | 120 |
| nut | 147/150 | 71/75 | 71/75 | 0 | 146 | 4.87 s | 147 |
| nut+fp / avi+fp | **150/150** | 75/75 | 75/75 | 1 | 150 | nut 4.97 s, avi none | 150 |
| rawidx (flush per frame) | **150/150** | 75/75 | 75/75 | 1 | 150 | n/a | 150 |
| folder | **150/150** | 75/75 | 75/75 | 1 | 150 | 6.0 s (image2 default 25 fps) | n/a |

FFV1 (g=1) behaved the same way: mkv 148, mkv+fp 149, fmp4_every+fp 149, fmp4_1s+fp 120, nut+fp/avi+fp 150, mp4 0,
seg_mp4 120 (measured, `summary.md`).

Inter codecs (GOP 30):

| container | AV1 drained | AV1 rt (fed 75) | H.264 NVENC drained | NVENC rt (fed 75) |
|---|---|---|---|---|
| mkv / webm (no fp) | 0/150 | 0/35 | 117/150 | 59/73 |
| mkv+fp / webm+fp | 120/150 | 30/35 | 120/150 | 60/73 |
| mkv_cl0+fp / webm_cl0+fp | **149/150** | 34/35 | **149/150** | 72/73 |
| fmp4_kf+fp | 120/150 | 30/35 | 120/150 | 60/73 |
| fmp4_every+fp | **149/150** | 34/35 | **149/150** | 72/73 |
| mp4 (any) | 0/150 | 0/35 | 0/150 | 0/73 |
| nut+fp / avi+fp | **150/150** | 35/35 | **150/150** | 73/73 |
| ivf+fp (AV1) | 150/150 | 35/35 | - | - |
| any single-file container without fp (AV1) | 0/150 | 0 | - | - |

- measured: with AV1 at ~1.5 KB/frame (clean mkv 229768 bytes for 150 frames, `kill_matrix_b.md`) the whole file stays
  inside the 256 KiB buffer, so every unflushed single-file AV1 variant lost everything.
- measured: AV1 `idle:75` muxed 0 packets (SVT-AV1 had produced nothing yet when frames were fed faster than real
  time); `rt` muxed 35 of 75 fed. NVENC muxed 73 of 75 in both.
- measured: cv2 `CAP_PROP_FRAME_COUNT` on the killed (`drained:150`) MJPEG files: mkv+fp **-2.767e17** (149 frames
  readable), avi+fp **0** (150 readable), nut+fp 149 (150 readable; also 149 for the clean NUT), fmp4_every+fp 149
  (correct), raw .mjpeg -1.92e14 (`kill_matrix_a.json` -> `read.cv2.prop_frame_count`). Code that sizes arrays from
  this property (FreeMoCap-style readers - inferred, not checked here) must not be given unfinalized files; after the
  `-c copy` .mkv repair the property equals the frames read (149, 150, 150, 149) (measured,
  `cv2_framecount_after_repair.json`).
- measured: unfinalized IVF reports a bogus duration (ffprobe 143165576.5 s) but all frames decode.
- measured: H.264 in AVI: PyAV seek failed on the killed `rt` file and in 20/22 and 14/21 truncation cuts
  (`summary.md` truncation `seek ok` 2/22 avi, 7/21 avi+fp); cv2 seek worked.
- measured: container overhead from the clean MJPEG files (payload = folder total 8317014 B for 150 frames):
  mkv 8324104 (+47 B/frame), mkv_resv 8583395 (reserved 256 KiB), fmp4_kf/every 8337465 (+136 B/frame), fmp4_1s
  8319650 (+18), mp4 8319315 (+15), nut 8321448 (+30), avi 8326382 (+62), rawidx data+index 8321814 (+32)
  (`kill_matrix_a.json` -> `bytes`). These are sizes, not timings.

### 4.2 Emulated power loss (24 prefix cuts per variant) (measured, `summary.md` truncation table)

| family | recovered / ideal (ffprobe) | cuts with 0 frames though ideal > 0 | worst shortfall | torn last frame handed to decoders |
|---|---|---|---|---|
| Matroska / WebM (all options, all payloads) | 0.998-1.000 | 0 | 1 frame | no (demuxer drops the torn block: "File ended prematurely") |
| fragmented MP4 (kf, every, 1 s) | 1.000-1.023 | 0 | 0 | yes for MJPEG (ffprobe = ideal+1 in 21-23 cuts) |
| plain MP4 | 0.000 | 20-22 of 24 | 136-149 | - |
| seg_mkv | 0.999-1.000 | 0 | 1 | no |
| seg_mp4 | 0.69-0.89 | 2-9 | 23-29 (the open segment) | - |
| NUT, AVI | 1.000-1.018 | 0 | 0 | yes for MJPEG / H.264 |
| IVF+fp (AV1) | 0.998 | 0 | 1 | - |
| raw .mjpeg + index | 1.013 by ffprobe; own idx+scan parser 1776/1776 exact | 0 | 0 | ffprobe yes; own parser no |
| folder of JPEGs | 1.013 by readers; files ending in EOI 1656/1656 | 0 | 0 | readers yes (`cv2.imdecode` decodes a truncated JPEG) |

- measured: ratios above 1.0 are the torn last frame counted as a frame (`truncation_a.json` rows with
  `ffprobe == ideal + 1`: fmp4 21-23, nut 22-23, avi 20-22, rawidx 23, folder 22 of 24 cuts).
- measured: the naive PyAV loop (stop at first exception) got fewer frames than ffprobe for AV1 in fMP4/NUT/AVI/IVF in
  19-21 of 24 cuts, up to 5 frames short (`truncation_b.md` `max short` PyAV column) - the frames still inside the
  decoder when the torn packet raises are dropped. ffprobe and cv2 did not show this. A production reader must catch
  per-packet errors and drain the decoder (inferred).
- measured: `ffmpeg -c copy` to `.mkv` kept exactly the frames ffprobe could read (repaired ratio = ffprobe ratio in
  every variant).

### 4.3 Repair (measured)
- `ffmpeg -c copy -> .mkv` of every killed file with >= 1 readable frame (389 files) produced a finalized file with the
  same ffprobe frame count (389/389); duration present and PyAV mid-file seek ok in 303/303 single-file repairs where
  seek was tested (files with >= 4 frames; segment and raw-MJPEG repairs were only frame-counted) (`summary.md` section "Repair check", computed by `summarize.py` from `kill_matrix_*.json`).
- The PyAV `-c copy` remux (`common_cr.remux_pyav`, stops at first demux error) gave the same ffprobe frame counts for
  MJPEG, FFV1 and H.264, but **failed for every AV1 file** with `UnknownCodecError: libdav1d`: PyAV 18's
  `add_stream_from_template()` defaults to `opaque=False` for video and builds an encoder named after the template's
  decoder (`libdav1d`) (measured, `kill_matrix_b.json` -> `repair.pyav_copy`; source: `av/container/output.py:268-290`
  in the installed PyAV 18.0.0). With `opaque=True` the AV1, H.264, MJPEG and FFV1 kill images all remuxed with the
  same frame count (measured, `pyav_remux_opaque_check.json`); the scripts now pass `opaque=True`.
- Plain MP4 without `moov` is not repairable by remuxing (0 frames, rc != 0: "moov atom not found") (measured). A
  reference-file tool such as `untrunc` was not tested (NOT VERIFIED).
- Repair time per GB: not measured here; `bench_repair.py` (section 9).

## 5. Electron / Chromium playback of damaged files

See `electron_e35.md` (Electron 35.7.5 / Chromium 134.0.6998.205) and `electron_e45.md` (Electron 45.2.3), condensed in
`summary.md`.

218 files per version: clean, `drained:150` and `rt` kills, their `ffmpeg -c copy` .mkv repairs, and 30/60/95 %
prefix cuts of the drained image for 8 Chromium-relevant containers (`run_electron.py`; hidden BrowserWindow; play from
0 at playbackRate 4).

How to read the numbers: in every file that played to `ended`, `decoded_during_play` = ffprobe frames - 4 (e.g.
clean 146/150, killed mkv+fp 116/120 with `final_currentTime` 3.967 s = frame 119 at 30 fps); the 4 frames are decoded
before `play()` (after the seek back to 0) and are not counted (measured, `electron_e35.json` field
`totalVideoFrames_before_play`). So "ended + expected-4" means every frame was shown.

| file state | Electron 35.7.5 (Chromium 134) | Electron 45.2.3 (Chromium 156) |
|---|---|---|
| MJPEG or FFV1 in mkv / mp4 / fMP4 (clean) | MediaError 4 `DEMUXER_ERROR_NO_SUPPORTED_STREAMS` | same (4, `PipelineStatus::DEMUXER_ERROR_...`) |
| NUT, AVI, IVF, any payload, even clean | MediaError 4 `DEMUXER_ERROR_COULD_NOT_OPEN` | same |
| plain MP4 killed or truncated | MediaError 4 `DEMUXER_ERROR_COULD_NOT_OPEN` | same |
| AV1 / H.264 in **unfinalized MKV/WebM** (kill or prefix cut) | plays to `ended`, all frames; `duration` = Infinity, `seekable` [0, Infinity]; seek to 1 s fires `seeked`; `duration` becomes the last frame time after playing | same |
| AV1 / H.264 in **unfinalized fMP4 written with flush_packets=1** (kill) | plays to `ended`, all frames; finite `duration` (complete fragments); mid seek ok | same |
| AV1 in **prefix-cut fMP4** (torn last sample) | plays the frames before the cut, then MediaError 3 `PIPELINE_ERROR_DECODE`; at a 30 % cut of kf/1s fragments nothing plays (`play()` pending) | same |
| H.264 in prefix-cut fMP4, or killed fMP4 **without** flush_packets (torn tail) | MediaError 4 `DEMUXER_ERROR_BITSTREAM_CONVERSION_FAILED` or "no supported sources"; 0-74 frames shown | **plays to `ended`**, all frames |
| `ffmpeg -c copy` .mkv of that torn H.264 fMP4 | still fails (the torn last packet is copied) | plays to `ended` |
| `ffmpeg -c copy` .mkv repair of any other killed file (incl. NUT/AVI/IVF sources) | plays to `ended`, finite duration, seek ok | same |

- measured: the only behavioural differences between the two versions are the torn-H.264-in-fMP4 files (15: the
  no-flush `drained`/`rt` kills of fmp4_kf/every/1s and the 9 prefix cuts) and their 6 MKV remuxes; the other
  differences in the diff are the error-message prefix and two AV1 cut files that decoded 1 frame more/less before the
  same decode error (`electron_e35.json` vs `electron_e45.json`, compared by id).
- inferred: for Chromium playback during or after a crash, Matroska/WebM is the safer container: its demuxer drops a
  torn block and ends cleanly, whereas a torn fMP4 sample puts the media element into an error state. A repair step
  for the UI should drop a torn last packet rather than `-c copy` it (the prototype's MJPEG repair does this by
  checking SOI/EOI; an H.264/AV1 equivalent is NOT implemented).
- measured: Chromium cannot play MJPEG or FFV1 from any of these containers in either version, so the G1/G4 payloads
  need a separate preview path in the UI regardless of crash handling.

## 6. sfn26 Rust recorder (plain MP4 through an ffmpeg child)

- code: `upstream/sfn26` (765bf82d) `skellycam-rust/src/recording/recorder.rs:40-45` defaults `image2pipe`, `mjpeg`,
  `libx264`, `ultrafast`, CRF 18, `yuv420p`; `:141-155` builds `ffmpeg -y -f image2pipe -c:v mjpeg -s WxH -r fps -i
  pipe:0 -c:v libx264 -preset ultrafast -crf 18 -pix_fmt yuv420p -an <out>` with no `-movflags`;
  `camera_group/dispatcher.rs:373` names the output `....mp4`; `recorder.rs:233-234` "Drop stdin so ffmpeg sees EOF and
  writes the file trailer"; `recorder.rs:265-276` `Drop` calls `self.ffmpeg_child.kill()`.
- measured (`sfn26_pipe.md`, ffmpeg 9.0.2, the same arguments, 600 frames, kill after 300 fed + 1 s):

| output | ffmpeg killed (= Drop) | parent (feeder) killed, ffmpeg left alone | whole tree killed (taskkill /F /T) | clean |
|---|---|---|---|---|
| plain MP4 (sfn26) | **0** | **300/300**, finalized, duration 10.0 s | **0** | 600 |
| MKV x264 | 246 | 300 | 246 | 600 |
| fMP4 x264 (frag_keyframe) | 246 | 300 | 246 | 600 |
| MKV MJPEG `-c copy` | 293 | 300 | 293 | 600 |

- measured: the ffmpeg CLI also buffers 256 KiB (killed MKV = 4194304 B = 16 x 262144), i.e. the CLI does not set
  `flush_packets` by default for these outputs.
- measured (`sfn26_pipe_n150.md`): with 75 frames fed (4.3 MB) and 1 s of waiting, killing ffmpeg left **no output
  file at all** in all four outputs ("missing"), while closing its stdin (feeder killed) still produced 75/75.
  inferred: ffmpeg was still probing the image2pipe input; source: the default `probesize` is 5000000 bytes
  (FFmpeg n9.0.2 `libavformat/options_table.h:39`, `{.i64 = 5000000 }`). So the first ~88 MJPEG frames (at ~57 KB) of an
  sfn26 recording exist only in ffmpeg's memory until probing ends (inferred).
- measured (`pict_type_check.json`, side finding): the ffmpeg CLI resets the decoder's picture type (3 key frames in 600
  x264 frames), but a PyAV pipeline that feeds decoded JPEG frames straight into `libsvtav1` or `libx264` gets **every
  frame as a key frame** (60/60) unless `frame.pict_type = NONE` is set first; `h264_nvenc` ignored it (2/60).
- implications (inferred): a crash of the Rust recording thread (Drop runs) or of the process tree loses every
  in-progress sfn26 video; a hard kill of only the host process may still give a complete file, but only if the OS
  leaves ffmpeg running. Whether skellycam's launcher puts ffmpeg in a kill-on-close job object is NOT VERIFIED (our
  venv launcher killed its own child but not the grandchild ffmpeg - measured, the `feeder_killed` row).

## 7. 'Resumable' recording - definition and prototype

Definition used here:
1. Everything written before a crash stays playable **without repair** by common readers, losing at most the frame
   being written.
2. On restart the recorder detects the unfinished session, repairs only the last open segment (`-c copy` of its
   readable packets, atomically swapped in), reconciles the timestamp sidecar with the frames really in the video, and
   records lost frame numbers.
3. Recording continues in a **new segment of the same session**: frame numbers continue (never reused while any
   evidence of them exists) and pts stay on one session clock (`pts_ms = (capture_ns - t0_ns) // 1e6`), so the outage
   shows as a time gap.

Prototype: `scripts/crash_resilience/resumable_recorder.py` (PyAV only):
- `manifest.jsonl` append-only journal (session, segment_open, segment_closed, resume, session_closed), flushed and
  fsynced per record; a torn last line is truncated on resume.
- `seg_NNNNN.mkv`: Matroska, `flush_packets=1`, MJPEG passthrough (or FFV1), new segment every `segment_seconds`.
- `timestamps.bin`: 32-byte records `<q frame, q capture_ns, i seg, I crc32, q reserved>`, flushed per frame (fsync
  policy is a parameter).
- Orphan segment files whose `segment_open` line was lost are adopted (first frame from the sidecar's segment field);
  a segment index present on disk is never reused. This was added after the first power-loss runs overwrote an orphan
  segment (measured in the first run of `run_resumable_demo.py`, then fixed and re-run).
- `join_session()` -c copies all segments into one MKV keeping the session-clock pts.

Results (measured, `resumable_demo.md`, final run after the `opaque=True` change below; segment 2 s, 30 fps pacing;
exact kill points vary by a frame between runs because pacing and kills are live):

| scenario | lost frames | video frames == ts records | unique, increasing | gaps all listed as lost | pts == capture clock | MJPEG byte-exact | joined MKV frames |
|---|---|---|---|---|---|---|---|
| kill mid-segment | 1 (the open cluster) | 259 == 259 | yes | yes | yes | 259/259 | 259 |
| kill at frame 120, near the 2nd (time-based) segment boundary | 1 | 181 == 181 | yes | yes | yes | 181/181 | 181 |
| double crash | 2 | 233 == 233 | yes | yes | yes | 233/233 | 233 |
| power loss x5 (segment, sidecar and journal cut) | 6-36 | equal in all 5 | yes | yes | yes | all | all |
| FFV1 kill mid-segment | 1 | 259 == 259 | yes | yes | yes | n/a | 259 |

- measured: after a power-loss cut, frame numbers whose video AND sidecar record were both lost are reused by the
  resumed run (they never existed on disk); the time gap (up to 1817.5 ms in these runs) shows the outage.
- inferred: the clock must survive a process restart; the demo uses `time.time_ns()`. QPC/`perf_counter_ns` across
  processes is NOT VERIFIED here (Python documents its reference point as undefined).

## 8. Timestamp sidecar durability (measured, `sidecar_durability.md`)

| writer | kill after 1 / 37 / 500 rows: rows intact | notes |
|---|---|---|
| CSV + flush per row (sfn26 `csv_writer.rs:50-72` pattern) | 1 / 37 / 500 | |
| CSV, default buffering | 0 / 0 / 456 | header only on disk after 37 rows |
| CSV + flush + fsync per row | 1 / 37 / 500 | same as flush for a process kill |
| binary 72-byte record + CRC + flush | 1 / 37 / 500 | |
| binary, default buffering | 0 / 0 / 452 | |

- measured: truncation at 24 offsets, with and without 4096 appended zero bytes: the strict CSV parser (all 8 fields,
  integers, expected values) and the CRC'd binary parser both recovered exactly the complete rows in 48/48 cases.
- measured: pandas 3.0.2 `read_csv` returned more rows than complete in 23/24 cuts (24/24 with zeros): the torn last
  row came back NaN-padded in 17 (18) and with **wrong integer values and no NaN** in 6 (6).
- inferred: flush vs fsync only differs for power loss / OS crash, which cannot be produced here; fsync cost is left to
  `bench_fsync.py`. sfn26's CSV flushes but never fsyncs (code: `csv_writer.rs:72`).

## 9. Benchmarks to run later (quiet machine) - see bench_manifest in the structured output

| script | question |
|---|---|
| `bench_fragment_overhead.py` | CPU/wall/size cost of mkv vs +fp vs cl0, fMP4 per-frame vs 100/500/1000/2000 ms fragments, plain mp4, nut, avi, segments 1/10/60 s, rawidx, folder; MJPEG, FFV1 and NVENC packets re-muxed from memory |
| `bench_fsync.py` | per-frame latency and throughput of none / flush / fsync every 1, 10, 30, 300 frames / sidecar-only fsync / PyAV MKV + fsync |
| `bench_repair.py` | seconds per GB for ffmpeg -c copy (mkv, mp4), PyAV remux and the prototype's segment repair, on ~1 GB unfinalized mkv+fp, fmp4_every+fp, plain mp4 and rawidx |

Commands (from the repo root, one at a time, nothing else running; each writes JSON to `results/crash_resilience/bench/`):
```
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/crash_resilience/bench_fsync.py --frames 3000 --repeats 3
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/crash_resilience/bench_fragment_overhead.py --frames 3000 --repeats 3 --payloads mjpeg,ffv1,h264nv
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/crash_resilience/bench_repair.py --gb 1 --repeats 3
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/crash_resilience/bench_fragment_overhead.py --frames 3000 --repeats 3 --payloads av1 --out-name av1
```
- Outputs: `bench/fsync.json`, `bench/fragment_overhead.json`, `bench/repair.json`, `bench/fragment_overhead_av1.json`.
- Temp data go to `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/crash_resilience/bench_tmp/`
  and are deleted by the scripts (repair needs ~4 GB free while it runs).
- `h264nv` uses NVENC once to prepare packets; the JSON records `nvidia-smi` before/after (Parsec/Sunshine may hold
  sessions).
- All were smoke-tested (`bench/*_smoke.json`, tiny sizes, loaded machine): those numbers must not be quoted.

## 10. Limits and open points

- Power loss is emulated as a clean prefix cut (plus a zero-filled tail for the sidecar). Real power loss can reorder
  writes, leave stale blocks, or lose metadata; NTFS behaviour was not tested (NOT VERIFIED).
- One source set (720p MJPEG, ~57 KB/frame). Frames per 256 KiB scale with bitrate; 1080p MJPEG (~133-192 KB/frame in
  the corpus) would lose fewer frames to the buffer, low-bitrate codecs more (inferred).
- 150-frame files: Matroska's 5 s default cluster limit and long GOPs were not exercised beyond GOP 30.
- AV1 encoder lag was measured at one preset (10) and default SVT-AV1 settings; low-delay settings were not tried.
- Chromium's handling of MJPEG/FFV1 is "not supported" (section 5), so crash behaviour of those payloads in the UI
  needs a proxy/transcode path (other topics).
- The kill_matrix_a first pass was terminated externally (unknown cause); completed with `--resume`.
- No timing claims: fragment, fsync and repair costs are in the bench manifest only.

## 11. Files

- Scripts: `research/skellycam_recording/recording_upgrade/scripts/crash_resilience/` - `common_cr.py`, `writer_child.py`,
  `run_kill_matrix.py`, `run_truncation.py`, `run_electron.py`, `electron_probe/{main.js,probe.html,package.json}`,
  `sfn26_pipe_test.py`, `resumable_recorder.py`, `run_resumable_demo.py`, `sidecar_durability.py`,
  `launcher_kill_check.py`, `pict_type_check.py`, `summarize.py`, `bench_fragment_overhead.py`, `bench_fsync.py`,
  `bench_repair.py`.
- Results: this folder (`*.json` raw, `*.md` tables, `summary.md`), `bench/` (smoke only).
- Media (room images, outside the repo): `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/crash_resilience/`
  (`kill/`, `kill/repaired/`, `electron_trunc/`, `sfn26_pipe/`, `sfn26_pipe_n150/`, `resumable/`).
- FFmpeg sources used for citations were downloaded from `https://raw.githubusercontent.com/FFmpeg/FFmpeg/<tag>/libavformat/<file>`
  (tags n8.0, n8.1, n9.0.2) into the scratchpad; RFC 8794 / 9559 from rfc-editor.org.
