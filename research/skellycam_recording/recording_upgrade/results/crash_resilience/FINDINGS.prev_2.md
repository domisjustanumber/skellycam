# crash_resilience (G2): FINDINGS

Goal G2: recording files that can be resumed and that survive a crash, so a crashed session's recording still plays. Machine "Gerald": Windows 11, i7-14700K, RTX 3070 with driver 610.88 (source, `research/skellycam_recording/recording_upgrade/HANDOFF.md:62-63`). Date 2026-11-09. This topic has functional results only. It contains no timing numbers.

**Labels.**
- **measured** = a result file. Paths are relative to `research/skellycam_recording/recording_upgrade/results/crash_resilience/` unless they start with `research/` or `scripts/`.
- **source** = a primary source, accessed 2026-11-09.
- **code** = file:line.
- **inferred** = reasoning, kept to a minimum.

**Versions.**
- The implementation under test is **PyAV 19.0.2**. Its bundled FFmpeg reports libavformat 63.1.102 and libavcodec 63.1.102 (measured, `pyav19_recheck.json` → `env`).
- That matches FFmpeg tag n9.0.2: `LIBAVFORMAT_VERSION_MAJOR 63`, `MINOR 1` (source, `libavformat/version_major.h:32` and `version.h:34` at n9.0.2, https://github.com/FFmpeg/FFmpeg/tree/n9.0.2).
- Results made with PyAV 18.0.0 (the skellycam venv, libavformat 62.12.102) are marked **background (bg)**.
- The OpenCV checks used the skellycam venv's OpenCV 4.12.0, read-only.
- **Deviation from the inspect-only rule (disclosed):** the ffprobe 9.0.2 CLI only inspected files. The **ffmpeg 9.0.2 CLI also wrote files**:
  - the `-c copy` repairs (code, `scripts/crash_resilience/common_cr.py:280-290`);
  - the `*.repaired.mkv` files that OpenCV read in `cv2_on_pyav19_files.json` and `cv2_seek_identity_pyav19_files.json`;
  - every sfn26 stand-in output (`sfn26_pipe*.md`).

  These rows are labelled **"ffmpeg 9.0.2 CLI, reference only"**. They are not the implementation under test. The repair finding is built on the PyAV 19 remux (§2.3).

---

## 1. Questions answered

1. After a hard process kill, and after an emulated power cut, how many frames can be read from each container and option? Payloads tested: MJPEG passthrough, FFV1, SVT-AV1 and NVENC H.264.
2. Why are frames lost? The mechanisms, from FFmpeg source.
3. Can ffprobe, PyAV, OpenCV and Chromium/Electron use an unfinalized file without repair? What does repair fix?
4. How many frames does the encoder hold back (frames that no container can save)? Can settings reduce that?
5. What does "resumable" mean, and does a Python prototype work on PyAV 19?
6. How durable is the timestamp sidecar?
7. How does the sfn26 Rust recorder (a plain MP4 written through an ffmpeg child process) behave when killed? How does today's skellycam behave?

## 2. Findings

### 2.1 Hard kill, PyAV 19.0.2 (implementation under test)

**Method.** `writer_child.py` ran under PyAV 19.0.2.
- `drained` mode: killed with TerminateProcess after all 150 frames were muxed and the encoder was drained, but before `close()`. The kill happens while the writer is blocked in `stdin.readline()` (code, `scripts/crash_resilience/writer_child.py:29-32`, `:184-187`), so the result is deterministic by construction.
- A second run gave the same frame counts and byte sizes in all 25 cases (measured, `pyav19_recheck_repeat.json`; only `nvidia_smi_before` differs). This shows repeatability. It does not show robustness to kill timing.
- Input: corpus `c930e_720p_flash`, 1280x720 MJPEG, **55.4 KB/frame** mean (measured, clean folder 8317014 B / 150, `kill_matrix_a.json`; `NOTES.md:227`).

| container (`+fp` = `flush_packets=1`) | MJPEG: readable / 150 (byte-exact) | H.264 NVENC | AV1 (SVT-AV1 4.2.0) |
|---|---|---|---|
| mkv | 146 (146) | 100 | **0** (0-byte file) |
| mkv+fp | 149 (149) | 120 | 120 |
| mkv_cl0+fp (`cluster_size_limit=0`, `cluster_time_limit=0`) | 149 (149) | 149 | 149 |
| webm_cl0+fp | - | - | 149 |
| fmp4_every (`frag_every_frame`, no fp) | 147 (**146**) | - | - |
| fmp4_every+fp | 149 (149) | 149 | 149 |
| fmp4_kf+fp | 149 (149) | 120 | - |
| mp4 / mp4+fp (plain) | **0 / 0** | - / 0 | - / 0 |
| nut | 147 (**146**) | - | - |
| nut+fp | **150 (150)** | 150 | - |
| avi+fp | **150 (150)** | - | - |
| seg_mkv+fp (segment muxer, 1 s) | 148 (segments 30, 30, 30, 30, 28; ffprobe only) | - | - |

- All of the above: measured, `pyav19_recheck.json` → `kill[]`, using ffprobe `-count_frames`. In every readable non-segment row, PyAV 19 read the same count. PyAV did not read the seg_mkv row.
- measured: **without fp, fmp4_every and nut hand out a torn frame after a plain process kill.** 147 frames are counted but only 146 are byte-exact. The 147th is the JPEG cut at the write-buffer boundary, and ffprobe and PyAV both count it as a frame (`pyav19_recheck.json` → `byte_exact`).
- measured: files written without `flush_packets` are exact multiples of 262144 bytes (`pyav19_recheck.json` → `bytes`, `bytes_mod_262144`):
  - MJPEG mkv: 8126464 B = 31 × 262144
  - MJPEG nut: 8126464 B
  - NVENC mkv: 1310720 B = 5 × 262144
  - MJPEG mp4 and fmp4_every: 8126508 B = 31 × 262144 + 44
- measured: AV1 mkv without fp left a **0-byte file**; the flushed AV1 files are 184533–241301 B (`pyav19_recheck.json`). inferred: the whole 5 s AV1 recording fit inside the 256 KiB write buffer.
- measured: NVENC mkv without fp kept 100/150 on PyAV 19 and 117/150 on PyAV 18 (bg, `kill_matrix_b.json`). Both file sizes are multiples of 262144, so the count depends on where the buffer boundary falls.
- **measured, live kill mid-recording (`rt`, PyAV 19)**: frames fed at 30 fps, TerminateProcess after 75 frames fed, no drain (`verify_method_pyav19_checks.json` → `rt`):

  | variant | muxed | readable / 75 fed |
  |---|---|---|
  | MJPEG mkv+fp | 75 | 74 (74 byte-exact) |
  | NVENC mkv_cl0+fp | 73 | 72 |
  | AV1 mkv_cl0+fp (defaults) | 36 | **35** |

  These are the only PyAV 19 kills made while frames were still arriving. A live kill loses 1 frame plus whatever the encoder still holds (§2.5).
- source (mechanism, FFmpeg n9.0.2; URL https://github.com/FFmpeg/FFmpeg/blob/n9.0.2/libavformat/):
  - `libavformat/file.c:324-332`: for written regular files, `h->max_packet_size = 262144` ("Buffer writes more than the default 32k to improve throughput") and `h->min_packet_size = h->max_packet_size` ("Disable per-packet flushing by default").
  - `libavformat/mux.c:425-433` (`flush_if_needed`): calls `avio_flush` only `if (s->flush_packets == 1 || ...)`; otherwise it writes a FLUSH_POINT marker.
  - `libavformat/options_table.h:84`: `flush_packets` default `{.i64 = -1}`.
  - `libavformat/aviobuf.c:466-469`: a FLUSH_POINT flushes only `if (s->buf_ptr - s->buffer >= s->min_packet_size)`.
- source (what the muxers still hold in memory with fp):
  - `matroskaenc.c:3032-3048`: a Cluster is built in `cluster_bc` and written out in `mkv_end_cluster`.
  - `matroskaenc.c:3231-3236`: a new Cluster starts on the size or time limit, or on a video key frame once the cluster is over 4 KiB.
  - `matroskaenc.c:2744-2748`: the defaults are 5000 ms and 5 MiB.
  - `movenc.c:7449-7455`: a fragment is flushed when the *next* packet meets the condition (duration, key frame, or `FF_MOV_FLAG_FRAG_EVERY_FRAME`).
  - inferred from this code, and consistent with the 120/150 vs 149/150 drained results: the open Cluster or fragment is lost. With GOP 30 that is up to one GOP for inter codecs, unless every frame closes it (cl0 / frag_every_frame).
- **Segment muxer.**
  - measured (P19): seg_mkv and seg_mkv+fp give identical results: 148 frames, segments 30/30/30/30/28, 8238820 B each (`verify_method_pyav19_checks.json` → `segment`).
  - measured (bg): PyAV 18 `rt` seg_mkv and seg_mkv+fp are byte-identical at 796847 B (`kill_matrix_b.json`).
  - source (n9.0.2 `libavformat/segment.c:161-167`): the inner context gets `oc->flags = s->flags`, but `flush_packets` is not copied. Packets are muxed through `ff_write_chained` (`segment.c:996`).
  - inferred, untested: `-fflags flush_packets` (which sets `AVFMT_FLAG_FLUSH_PACKETS` in `flags`) might reach the inner muxer.
  - The 2-frame loss is smaller than the 256 KiB buffer plus an open cluster would predict. The inner muxer's buffering mechanism is **NOT VERIFIED**.

### 2.2 Reading unfinalized files without repair (PyAV 19 files)

- measured: ffprobe and PyAV 19 read the same frame count in every readable non-segment kill image (`pyav19_recheck.json`).
- measured: unfinalized MKV and AVI report **no duration**. fMP4+fp reports 4.966992 s (MJPEG) or 4.966667 s (H.264/AV1), i.e. the complete fragments (`pyav19_recheck.json` → `ffprobe_format_duration`).
- **measured: PyAV 19 seek** (`c.seek(target, backward=True)` on the middle frame, then decode one frame; `pyav19_recheck.json` → `pyav.seek`):

  | file type | result |
  |---|---|
  | MJPEG mkv, mkv+fp, mkv_cl0+fp, fmp4_every, fmp4_every+fp, fmp4_kf+fp | **exact** |
  | MJPEG nut, nut+fp | about **1 frame early**, although every frame is intra (got 151572, target 153600; 2048 ticks/frame) |
  | MJPEG avi+fp | **pts 0, the start of the file** (target 75) |
  | H.264 / AV1 (inter) | the preceding key frame, as `backward=True` should give |

  - code: the check's `ok` flag only means "a frame at or before the target, no exception" (`scripts/crash_resilience/common_cr.py:236-249`), so the AVI fallback still counted as `ok`.
  - ffprobe ran no seek test.
  - Unlike OpenCV, PyAV reports the pts it actually landed on. A reader can detect the miss and decode forward to the target pts.
  - background (`NOTES.md:225`): PyAV 18 also failed to seek in H.264 AVI.
- measured (OpenCV 4.12.0): `CAP_PROP_FRAME_COUNT` (`cv2_on_pyav19_files.json`):

  | file | frame count reported | frames read |
  |---|---|---|
  | MJPEG mkv+fp | **-2.767e17** | 149 |
  | AVI+fp | **0** | 150 |
  | NUT+fp | 149 | 150 |
  | fMP4_every+fp | 149 (correct) | 149 |
  | NVENC mkv_cl0+fp | -2.767e17 | 149 |
  | AV1 mkv_cl0+fp | -2.767e17 | 149 |

- **measured: OpenCV's frame-index seek goes silently to frame 0 on unfinalized MKV and AVI.** This corrects NOTES §4.1 and the bench-queue summary.
  - After `CAP_PROP_POS_FRAMES = 74`, `set()` and `read()` both return True. The returned image is pixel-identical to sequential frame **0** and to no other frame (`pos_after` 1.0).
  - This held for MJPEG mkv+fp, MJPEG avi+fp and NVENC mkv_cl0+fp.
  - On fMP4+fp and NUT+fp it returns frame 74 (`cv2_seek_identity_pyav19_files.json`).
  - measured, bg: every drained MKV, WebM, AVI and raw-MJPEG row in `kill_matrix_a.json` / `kill_matrix_b.json` has `read.cv2.seek.pos_after == 1.0`. fMP4, NUT, IVF and folder rows land on target+1.
  - So "cv2 seek worked" in NOTES (H.264/AVI) and "seeking works" in the bench-queue summary are wrong for OpenCV on unfinalized MKV/AVI. **Unfinalized AVI cannot be seeked by either OpenCV or PyAV.**

### 2.3 Repair (PyAV 19 files)

- **measured (primary): a PyAV 19 remux to `.mkv` with `add_stream_from_template(ist, opaque=True)` kept the frame count in 19/19 repairable kill images** (9 MJPEG, 6 NVENC, 4 AV1; `pyav19_recheck.json` → `pyav_remux_template_opaque`).
  - 20 images are readable. seg_mkv+fp was not repaired.
  - The 4 unreadable images (plain mp4/mp4+fp and the 0-byte AV1 mkv) have nothing to remux.
- **measured: OpenCV on those PyAV 19 remuxes** gives a correct `CAP_PROP_FRAME_COUNT` (149/150) and a **frame-exact** `POS_FRAMES=74` seek (the returned frame equals sequential frame 74) in 5/5 files: MJPEG mkv+fp, avi+fp, nut+fp; NVENC mkv_cl0+fp; AV1 mkv_cl0+fp (`verify_method_cv2_on_pyav_remux.json`).
- measured: PyAV 19 `add_stream_from_template(ist)` with **default** arguments fails for **4/4 readable AV1 files** (mkv+fp, mkv_cl0+fp, webm_cl0+fp, fmp4_every+fp). Each gives `UnknownCodecError: libdav1d` and 0 packets. MJPEG and H.264 remux with either setting (`pyav19_recheck.json` → `pyav_remux_template_default`).
  - measured, bg: PyAV 18 showed the same failure (`kill_matrix_b.json` → `repair.pyav_copy`; `NOTES.md:260-262`).
- Reference only (ffmpeg 9.0.2 CLI, not under test):
  - measured: `ffmpeg -c copy` to `.mkv` kept the frame count in 19/19 and restored a finite duration (e.g. MJPEG mkv+fp gives 149 frames, 4.966 s; `pyav19_recheck.json` → `ffmpeg_copy_mkv`).
  - measured: on the CLI-repaired files, OpenCV reports the correct count. Its seek was pixel-verified on 2 files (MJPEG mkv+fp and H.264 mkv_cl0+fp, `cv2_seek_identity_pyav19_files.json`). On the repaired AVI only position was checked (`pos_after` 76, `cv2_on_pyav19_files.json`).
- measured: a plain MP4 kill image has 0 readable frames and gives `InvalidDataError`, so there is nothing to remux (`pyav19_recheck.json`).

### 2.4 Emulated power loss (prefix cuts), PyAV 19 files

**Method.** 12 seeded cuts per variant. "ideal" = the packets in the image's own ffprobe packet table that end before the cut. Measured, `truncation_pyav19.json`.

| variant | ffprobe = ideal | ffprobe = ideal + 1 | torn last sample handed to the decoder (any codec) | PyAV naive loop < ffprobe |
|---|---|---|---|---|
| MJPEG mkv+fp | 12/12 | 0 | **no, 0/12** | 0 |
| MJPEG fmp4_every+fp | 0 | 12/12 | **yes, 12/12** | 0 |
| MJPEG nut+fp | 2 | 10/12 | **yes, 12/12** (in 2 of them PyAV raised `InvalidDataError` at `avcodec_send_packet()`) | 0 |
| AV1 mkv_cl0+fp | 12/12 | 0 | **no, 0/12** (no decoder error) | 0 |
| AV1 fmp4_every+fp | 12/12 | 0 | **yes, 12/12**: PyAV `InvalidDataError` (11 at `avcodec_send_packet()`, 1 at `avcodec_receive_frame()`) | **12/12, up to 6 frames short** |

- measured: Chromium also fails on the torn AV1 fMP4 sample (`PIPELINE_ERROR_DECODE`, §2.7).
- measured, PyAV 18 (bg, 24 cuts per variant across about 90 variants; `summary.md` truncation table, generated from `truncation_a.json` / `truncation_b.json`):
  - Matroska/WebM: ratio 0.998–1.000, never a torn frame.
  - plain MP4: ratio 0.000, with 0 frames in 20–22 of 24 cuts.
  - seg_mp4: 0.69–0.89.
  - fMP4, NUT, AVI, raw MJPEG and the JPEG folder count the torn frame (ratio up to 1.023).
  - The naive PyAV loop was short of ffprobe for AV1 in fMP4, NUT, AVI and IVF: **up to 6 frames** (`agg.pyav_max_short` = 6 for AV1 fmp4_kf+fp, 5 for the other variants; `truncation_b.json`).
- inferred: a production reader must catch per-packet errors, drain the decoder, and validate the last JPEG (SOI/EOI). The prototype's MJPEG repair does the SOI/EOI check (NOTES §5). There is no H.264/AV1 equivalent.

### 2.5 Frames held by the encoder (no container can save these), PyAV 19

**Method.** 75 decoded camera frames fed at 30 fps; count the packets returned before the drain. Measured, `encoder_hold_check_pyav19.json` and `.log`. The SVT cases ran twice with the same counts.

| encoder settings | packets out / 75 | held by the encoder |
|---|---|---|
| libsvtav1 preset 10, crf 35, defaults (log: "random access", mini-gop 16, **"BRC mode / rate factor : CRF / 35.00"**, "Number of PPCS 161") | 36 | **39** |
| libsvtav1, same + `svtav1-params=pred-struct=1` (log: "low delay", mini-gop 4, **"BRC mode / CQP Assignment : CQP / 35.00"**, "Number of PPCS 1") | 75 | **0** |
| h264_nvenc p4, bf 0, vbr cq 23 | 73 | 2 |
| h264_nvenc, same + `delay=0` | 75 | **0** |

- measured: the default and low-delay SVT runs **used different rate-control modes** (CRF vs CQP) and different picture-level parallelism (PPCS 161 vs 1) (`encoder_hold_check_pyav19.log` lines 9, 18, 33, 42). So "0 held" compares two rate-control modes, not only two prediction structures.
- measured: with pred-struct=1, SVT logs "TPL is disabled in low delay applications." (log line 31).
- measured: the live `rt` kill agrees with the default count. AV1 mkv_cl0+fp muxed 36 of 75 fed frames (`verify_method_pyav19_checks.json` → `rt`).
- inferred: with 0 frames held at a 30 fps feed, `encode()` returns each frame's packet during that same call, so the encode cost moves onto the calling thread. Untested; pending bench.
- The quality, size and speed effects of either low-delay setting were **not tested**. The low-delay packets were counted but not decoded.
- source: SVT-AV1 v4.2.0 `Docs/Parameters.md:261`, `--pred-struct`, default 2, "Set prediction structure [0: all intra, 1: low delay, 2: random access]" (https://gitlab.com/AOMediaCodec/SVT-AV1/-/blob/v4.2.0/Docs/Parameters.md).
- source: FFmpeg n9.0.2 `libavcodec/nvenc_h264.c:100-101`, `"delay"`, "Delay frame output by the given amount of frames", default `INT_MAX`.
- source: FFmpeg n9.0.2 `libavcodec/libsvtav1.c:830`, `svtav1-params`, "Set the SVT-AV1 configuration using a :-separated list of key=value parameters".
- measured, PyAV 18 (bg): in the kill matrix `rt` mode, AV1 muxed 35 of 75 fed frames and NVENC muxed 73 (`summary.md` kill table).

### 2.6 `pict_type` side finding, PyAV 19

- measured: frames decoded from camera JPEGs carry `pict_type` "1" (I). Results (`pyav19_recheck.json` → `pict_type`; PyAV 18 gave the same, bg, `pict_type_check.json`):

  | encoder | key frames, pict_type unchanged | key frames, pict_type = NONE |
  |---|---|---|
  | libsvtav1 | **60/60** | 2/60 |
  | libx264 | **60/60** | 2/60 |
  | h264_nvenc | 2/60 | 2/60 |

  So a transcoding pipeline must set `frame.pict_type = PictureType.NONE`.

### 2.7 Electron / Chromium playback of damaged PyAV 19 files

**Method.** 19 files, hidden window, play from 0 at rate 4.
- Electron 35.7.5 = Chromium 134.0.6998.205; Electron 45.2.3 = Chromium 156.0.8078.80.
- Measured, `electron_pyav19_e35.json`, `electron_pyav19_e45.json`; file list `electron_pyav19_list.json`.
- "ended" means the file reached `ended` with no MediaError. Presentation and pixels during play were **not verified**: `rvfc_callbacks` is 0–1 and `droppedVideoFrames` is large (e.g. 48 of 90 for AV1 mkv_cl0+fp cut at 60 %).
- "end t" = `final_currentTime`. MKV/WebM end at the start time of the last frame (e.g. 4.933 s = frame 148 at 30 fps). fMP4 ends at the duration, the end of the last frame (4.966667 = 149/30; 4.0 = 120/30).

| file | Electron 35.7.5 | Electron 45.2.3 |
|---|---|---|
| MJPEG mkv+fp kill | MediaError 4 `DEMUXER_ERROR_NO_SUPPORTED_STREAMS` | same |
| AV1 / H.264 mkv+fp kill (120 frames) | ended, end t 3.967 s, duration Infinity, `seeked` fired | same |
| AV1 / H.264 mkv_cl0+fp, AV1 webm_cl0+fp kill (149) | ended, end t 4.933 s, duration Infinity | same |
| the same files cut at 60 % / 95 % | ended (AV1 end t 2.8 / 4.4 s; H.264 2.933 / 4.667 s) | same |
| AV1 / H.264 fmp4_every+fp kill (149); H.264 fmp4_kf+fp (120) | ended, finite duration (4.966667 / 4 s) | same |
| AV1 fmp4_every+fp cut 60 % / 95 % | MediaError 3 `PIPELINE_ERROR_DECODE` part-way (end t 2.42 / 4.05 s) | same error |
| H.264 fmp4_every+fp cut 60 % | MediaError 4 `DEMUXER_ERROR_BITSTREAM_CONVERSION_FAILED`, 0 frames decoded | **ended**, end t 3.0 s (ffprobe counts 89 frames) |
| H.264 fmp4_every+fp cut 95 % | same error, 73 of 141 decoded | **ended**, end t 4.733 s |

- **measured, seek frame identity (Electron 35.7.5)**, `verify_method_electron_seek_identity_e35.json`. Method: each unfinalized kill image vs its finalized PyAV 19 opaque remux, by canvas readback; targets 1.5/2.5/3.5/4.5 s; 2 passes each.
  - AV1 mkv_cl0+fp: frame-exact 8/8, read immediately at `seeked`.
  - H.264 mkv_cl0+fp and fmp4_every+fp: frame-exact 16/16 when the canvas was read 250 ms after `seeked`.
  - H.264 read immediately at `seeked`: 9/16 exact. 7/16 returned the previously shown frame (frame 0, or the previous seek target): 3 in MKV, 4 in fMP4. So this is not a container effect. Pass it to chromium_sync_scrub (G9).
  - The `seeked`-only check in `electron_probe/probe.html:30-31` was not a frame check. Seek identity on the 120-frame mkv+fp files: not tested.
- measured, bg: the 218-file PyAV 18 run (`electron_e35.json` / `electron_e45.json`) gives the same behaviour for the file types re-run here.
  - NOTES counts 23 differences by id between E35 and E45 (15 + 6 behavioural + 2 AV1 decode-count, `NOTES.md:295-297`). Recomputed by (ended, error code), 21 ids differ.
  - There, both versions also failed on NUT, AVI, IVF and killed plain MP4 with MediaError 4 `DEMUXER_ERROR_COULD_NOT_OPEN`. Those containers were not re-run with PyAV 19 files.
- measured: in every ended file, `decoded_during_play` = expected − 4. Counts: E35 132/132 and E45 153/153 (PyAV 18 files); E35 14/14 and E45 16/16 (PyAV 19 files).
  - NOTES explains the 4 as frames decoded before `play()`, but `totalVideoFrames_before_play` was 9–38 in those runs. **The cause of the offset is NOT VERIFIED.**
  - Use `final_currentTime` as the evidence that the last frame was reached.

### 2.8 Resumable recorder prototype on PyAV 19

**What it is.** `scripts/crash_resilience/resumable_recorder.py` writes:
- a `manifest.jsonl` journal, fsynced per record;
- per-segment MKV with `flush_packets=1`, 2 s segments;
- a 32-byte `timestamps.bin` record with a CRC.

Child writers ran under PyAV 19.0.2 and were killed with TerminateProcess. Measured, `resumable_demo_pyav19.json` (`env.child_interpreter` is the uv PyAV 19 interpreter).

| scenario | lost frames | video frames == ts records | unique + increasing | gaps listed as lost | pts == capture clock | MJPEG byte-exact | joined MKV |
|---|---|---|---|---|---|---|---|
| kill mid-segment (MJPEG) | 1 [169] | 259 == 259 | yes | yes | yes | 259/259 | 259 |
| double crash | 2 [99, 174] | 233 == 233 | yes | yes | yes | 233/233 | 233 |
| power loss, seed 0 (segment, sidecar and journal torn) | 7 [149–155] | 209 == 209 | yes | yes | yes | 209/209 | 209 |
| power loss, seed 1 | 36 [130–165] | 190 == 190 | yes | yes | yes | 190/190 | 190 |
| FFV1 kill mid-segment | 1 [169] | 259 == 259 | yes | yes | yes | n/a | 259 |

- measured, PyAV 18 (bg, `resumable_demo.md`): 9 scenarios passed, including 5 power-loss seeds and a kill at a segment rollover. A bug in which an orphan segment was overwritten was found and fixed during that work (NOTES §7).
- measured: after a power cut, the resumed run reuses frame numbers whose video record *and* sidecar record were both lost. The outage shows only as a gap in capture time (NOTES §7; `max_capture_gap_ms` in the JSON). The gap values were taken on a loaded machine and are not a benchmark.

### 2.9 Timestamp sidecar (independent of PyAV; Python 3.12.13, pandas 3.0.2)

- measured, process kill after 1 / 37 / 500 rows (`sidecar_durability.md`):

  | writer | rows intact |
  |---|---|
  | CSV + `flush()` per row | 1 / 37 / 500 |
  | binary 72-byte record + CRC + flush | 1 / 37 / 500 |
  | CSV with default buffering | 0 / 0 / 456 (6380 B lost: 72532 vs 66152 B) |
  | binary with default buffering | 0 / 0 / 452 (3456 B lost: 36000 vs 32544 B) |

- measured, 24 cuts × 2 tails (`sidecar_durability.json`, recounted from the raw rows):
  - The strict CSV parser and the CRC binary parser recovered exactly the complete rows in 48/48.
  - pandas `read_csv` returned an extra row in 23/24 cuts (24/24 with a zero-filled tail).
  - Of those extra rows, **6/24 looked complete but had wrong integer values**; the rest were NaN-padded (17, or 18 with the zero tail).
- code: sfn26 `skellycam-rust/src/timestamps/csv_writer.rs:72` flushes each row (`self.writer.flush()`). No `sync_all` or `sync_data` appears in that file (`git show upstream/sfn26`, 765bf82d). Rows are written per frame during recording (`recording/recording_thread.rs:301`, `writer.write_row`).

### 2.10 sfn26 Rust recorder and today's skellycam

- code (sfn26 765bf82d), `skellycam-rust/src/recording/recorder.rs`:
  - `:40-45`: defaults `image2pipe`, `mjpeg`, `libx264`, `ultrafast`, crf 18, `yuv420p`.
  - `:141-156`: spawns ffmpeg with no movflags.
  - `:233`: "Drop stdin so ffmpeg sees EOF and writes the file trailer" (in `finish()`).
  - `:266-275`: `Drop` calls `self.ffmpeg_child.kill()`. This only happens if `finish()` did not run, i.e. on the crash or unwinding path.
  - `camera_group/dispatcher.rs:373` names the output `.mp4`.
- measured (ffmpeg 9.0.2 CLI as a stand-in for sfn26's child process, reference only): the sfn26 arguments were reproduced, with `-r 30` (code, `scripts/crash_resilience/sfn26_pipe_test.py:41`). Feed 300 of 600 frames, wait 1 s, then kill (`sfn26_pipe.md`):

  | output | kill ffmpeg (= `Drop`) | kill the whole tree | kill only the feeder |
  |---|---|---|---|
  | plain MP4 | **0** | **0** | **300/300**, finalized, 10.0 s |
  | MKV x264 | 246 | 246 | - |
  | fMP4 x264 | 246 | 246 | - |
  | MKV MJPEG copy | 293 | 293 | - |

- measured: with 75 frames fed (2.5 s at 30 fps; the feeder-killed MKV MJPEG copy of those frames is 4174837 B) and 1 s of waiting, killing ffmpeg or the whole tree left **no output file** in all 4 outputs. Killing only the feeder still gave 75/75 (`sfn26_pipe_n150.md`).
  - inferred: ffmpeg was still probing its input.
  - Two source limits fit both runs, and they were not separated:
    - `probesize` default `{.i64 = 5000000 }` (source, n9.0.2 `libavformat/options_table.h:39`);
    - `analyzeduration` default 0 (`options_table.h:56`), which becomes `5*AV_TIME_BASE` = 5 s (`demux.c:2638-2641`).
  - The boundary between 75 and 300 frames was not bisected. The bound is **NOT VERIFIED**.
- background (today's skellycam, verified review): a hard kill leaves an MSMF `.mp4` with 0 readable frames, and no timestamps CSV is written unless the stop is clean (`research/skellycam_recording/REPORT.md:27`, `:210-213`, `:226`).

## 3. Comparison tables

**A. Recording container after a crash.** Legend: P19 = PyAV 19 measured; bg = PyAV 18 background.

| container | kill loss, MJPEG +fp (drained; §2.1) | torn sample handed out (§2.1, §2.4) | OpenCV frame count / seek, unfinalized (§2.2) | PyAV seek, unfinalized MJPEG (§2.2) | Chromium, unfinalized AV1/H.264 (§2.7) | Chromium plays MJPEG |
|---|---|---|---|---|---|---|
| MKV/WebM + fp | 1 frame (P19; live `rt` also 1 for MJPEG) | no (P19, bg) | -2.767e17 / **silently frame 0** (P19) | exact (P19) | reaches `ended`, duration Infinity (P19); seek frame-exact on cl0 files (E35) | no |
| MKV/WebM + fp + cl0 | 1 frame after encoder drain (P19). Live: 1 + encoder hold-back (NVENC 72/75, AV1 defaults 35/75, P19) | no (P19) | same as above | exact (P19) | same | no |
| fMP4 frag_every + fp | 1 frame (P19) | **yes**, after a cut (P19); also after a kill without fp | correct / correct (P19) | exact (P19) | reaches `ended`; a torn sample gives MediaError (AV1 both versions, H.264 E35) | no |
| plain MP4 | **all** (P19) | n/a (0 frames) | not readable | not readable | no (bg) | no |
| NUT + fp | 0 (P19) | **yes** (P19); also after a kill without fp | off by 1 / correct (P19) | **about 1 frame early** (P19) | no, cannot open (bg) | no |
| AVI + fp | 0 (P19) | yes (bg) | 0 / **silently frame 0** (P19) | **frame 0** (P19) | no (bg) | no |
| segment muxer (mkv) | 2 frames, with or without fp (P19, bg); mechanism NOT VERIFIED | no (bg) | not tested | not tested | not tested | no |
| raw .mjpeg + CRC index, flush | 0 (bg) | own parser: no; ffprobe: yes (bg) | -1.92e14 / frame 0 (bg) | n/a | no | no |
| folder of JPEGs | 0 (bg) | yes (bg) | n/a | n/a | no | no |

**B. Where frames are lost, and what bounds the loss.**

| loss source | size without mitigation | mitigation | evidence |
|---|---|---|---|
| FFmpeg file-protocol buffer | up to 262144 B (4–5 MJPEG frames; a whole 5 s AV1 file) | `flush_packets=1` | measured §2.1; source file.c/mux.c |
| open MKV Cluster | 1 frame (intra); up to 1 GOP (inter) | `cluster_size_limit=0` + `cluster_time_limit=0` | measured §2.1; source matroskaenc.c |
| open fMP4 fragment | 1 frame (every), 1 GOP (kf), 1 s (1 s fragments, bg) | `frag_every_frame` | measured §2.1; source movenc.c |
| plain MP4 `moov` never written | everything | don't record to plain MP4 | measured §2.1, §2.10 |
| encoder hold-back | SVT-AV1 39 frames, NVENC 2 (at 30 fps) | SVT `pred-struct=1` (also switches CRF to CQP), NVENC `delay=0`: 0 held | measured §2.5; live kill §2.1 |
| ffmpeg-CLI child still probing (sfn26 pattern) | the whole file at 75 frames / 2.5 s; bound not bisected | avoid the CLI child | measured: 0 B output; cause inferred (probesize 5 MB or analyzeduration 5 s), §2.10 |
| unflushed sidecar | 6380 B (CSV) / 3456 B (binary) at the 500-row kill | flush per row; CRC binary record | measured §2.9 |

## 4. Implications for the plan

1. **Recording container for G1 (MJPEG passthrough): Matroska with `flush_packets=1`.**
   - It loses 1 frame on a kill (drained and live) and keeps every frame byte-exact.
   - It never hands out a torn frame after a cut.
   - ffprobe and PyAV read it without repair, and PyAV seeks exactly (§2.1, §2.2, §2.4).
   - NUT and AVI save one more frame on a kill, but they hand out torn frames, seek inexactly or to frame 0, and Chromium can't open them (§2.2, §2.4, §3A).
2. **Set `flush_packets=1` on every libavformat writer.** The default loses up to 256 KiB. With a low-bitrate codec that can be the whole file, and without fp fMP4/NUT also hand out a torn frame (§2.1). The cost is pending (bench `cr_fragment_overhead`).
3. **Inter codecs (G6/G7) need both container and encoder settings.**
   - Container: MKV/WebM with `cluster_size_limit=0` + `cluster_time_limit=0`, or fMP4 with `frag_every_frame`.
   - measured: with container settings alone, a live kill lost 1 frame plus the encoder hold-back (AV1 defaults 35/75, NVENC 72/75, §2.1).
   - Low-delay encoding (SVT-AV1 `pred-struct=1`, NVENC `delay=0`) removes the hold-back (§2.5).
   - inferred, not tested in a kill: with both, the loss is 1 frame.
   - The quality, size and speed cost of low delay is untested, and SVT's low-delay run also switched CRF to CQP (§2.5, §5).
4. **Never record to plain MP4.** Use it at most as a finalize or remux target. This applies to today's MSMF path and to sfn26 (§2.1, §2.10).
5. **Use application-level segments, not the `segment` muxer.**
   - The muxer ignored `flush_packets` on PyAV 19 and PyAV 18, which matches source: `flush_packets` is not copied to the inner muxer (§2.1).
   - It lists a segment only once the segment is closed (NOTES §2 M12).
   - The prototype already uses application-level segments (§2.8).
6. **Finalize before any OpenCV reader, and don't trust PyAV seeks on unfinalized files.**
   - OpenCV on unfinalized MKV/AVI returns a garbage frame count, and frame-index seeks silently return frame 0 (§2.2).
   - The finalize step should be a **PyAV 19 remux to `.mkv` with `opaque=True`**: count kept in 19/19, and OpenCV count and seek correct in 5/5 (§2.3).
   - PyAV readers must catch per-packet errors, drain the decoder (§2.4), check the pts they land on after a seek, and decode forward. Unfinalized AVI seeks to frame 0 in PyAV as well (§2.2).
7. **PyAV-based repair must pass `opaque=True`** to `add_stream_from_template`, or every AV1 file fails (4/4, §2.3).
8. **For the UI during or after a crash, prefer MKV/WebM over fMP4.**
   - Chromium reaches `ended` on unfinalized and prefix-cut MKV/WebM, and its seeks there were frame-exact (§2.7).
   - A torn fMP4 sample is a MediaError in Electron 35. code: the UI declares `"electron": "^35.0.3"` (`skellycam-ui/package.json:52`), and 35.7.5 is installed.
   - H.264 canvas reads taken right at `seeked` can be stale. This goes to G9 (§2.7).
   - MJPEG/FFV1 never play in Chromium, so G1/G4 recordings need a separate preview or proxy path whatever the crash handling (§2.7).
9. **Timestamp sidecar: a fixed-size binary record with a CRC, flushed per frame.** Don't use a CSV parsed by pandas, which returned silently wrong integers (§2.9). The fsync policy is pending (bench `cr_fsync`).
10. **Set `frame.pict_type = NONE` whenever decoded JPEG frames are re-encoded.** Otherwise libsvtav1 and libx264 make every frame a key frame (§2.6).
11. **"Resumable" as defined in NOTES §7 works on PyAV 19** (§2.8): journal + per-segment MKV+fp + CRC sidecar. The segment length depends on repair cost (bench `cr_repair`).
12. **From sfn26, reuse the per-row flush idea, not the ffmpeg-child plain MP4.** `Drop` (on the crash or unwind path) or a tree kill loses the whole file. A short recording can also leave no file while ffmpeg is still probing; that cause is inferred (§2.10).

## 5. Pending tonight's bench

**Run all of these under PyAV 19.0.2 on the quiet machine.**
- The manifest commands call `.venv/Scripts/python.exe`, which is PyAV 18. Use the uv forms in the commands table below instead. `--no-project` is required; without it `uv run` syncs the skellycam `.venv`.
- code: `common_cr.env_versions()` imports `cv2` (`scripts/crash_resilience/common_cr.py:423-426`), hence `--with opencv-python` below. According to VERIFY_method §4, `opencv-python-headless==4.12.0.88` resolves and reports 4.12.0, and `bench_fsync.py` ran functionally under PyAV 19.0.2. The smoke output was not kept, so this is not a result file.
- code: `bench_repair.py:38` starts `writer_child.py` with `cc.VENV_PY` (PyAV 18). Before `cr_repair` can run, it must use the PyAV 19 interpreter, e.g. a wrapper that sets `cc.VENV_PY = Path(sys.executable)`, as `scripts/crash_resilience/pyav19_checks/resumable_pyav19.py` does.
- code, confounder in `cr_fsync`: the `mkv_fp_fsync_K` policy writes Matroska through a **Python file object** (`av.open(f, "w", ...)`, with `f.flush()` + `os.fsync` every K frames; `bench_fsync.py:50-73`). That is not the path-based `av.open(path, options={"flush_packets": "1"})` used by the recorder and every kill test, so its numbers won't transfer. Add a by-path policy. How to fsync a path-opened file on Windows through a second handle: NOT VERIFIED.
- The smoke files in `bench/` (`fsync_smoke.json`, `fragment_overhead_smoke*.json`, `repair_smoke.json`) report PyAV 18.0.0 and were made on a loaded machine. Don't quote them.

| timed question | bench id / command |
|---|---|
| Per-frame latency (p50/p99/max), throughput and CPU of: no flush / flush / fsync every 1, 10, 30, 300 frames / sidecar-only fsync / MKV+fp with fsync | `cr_fsync`: `uv run --no-project --with av==19.0.2 --with numpy --with opencv-python python research/skellycam_recording/recording_upgrade/scripts/crash_resilience/bench_fsync.py --frames 3000 --repeats 3` (see the confounder above) |
| CPU, wall-time and size overhead of mkv vs +fp vs cl0; fMP4 per-frame vs 100–2000 ms fragments; plain mp4, nut, avi; segments 1/10/60 s; raw+index; folder (MJPEG, FFV1, NVENC packets) | `cr_fragment_overhead`: `uv run --no-project --with av==19.0.2 --with numpy --with opencv-python python research/skellycam_recording/recording_upgrade/scripts/crash_resilience/bench_fragment_overhead.py --frames 3000 --repeats 3 --payloads mjpeg,ffv1,h264nv` |
| The same for AV1 packets | `cr_fragment_overhead_av1` (same uv form; needs the AV1 payload option) |
| Repair seconds per GB (ffmpeg -c copy to mkv/mp4, PyAV remux, the prototype's segment repair; cold vs cached cache), which sets the segment length | `cr_repair`, after the `bench_repair.py:38` fix |
| Speed, size and quality (Y-PSNR) cost and per-`encode()` latency of SVT-AV1 `pred-struct=1` and NVENC `delay=0` | new, no manifest id: `uv run --script research/skellycam_recording/recording_upgrade/scripts/crash_resilience/pyav19_checks/bench_lowdelay_pyav19.py --repeats 3` (output `results/crash_resilience/bench/lowdelay_pyav19.json`). Note the CRF/CQP difference and the flash frames in the corpus when reading min PSNR. |
| Time from restart to the first new frame in the resumable recorder (the outage gap) | **no manifest id** |

**Open functional check (no timing).** A PyAV 19 live kill (no drain) of SVT `pred-struct=1` and NVENC `delay=0` into mkv_cl0+fp. This would test implication 3's "1 frame" claim.

## 6. Not tested, limits, NOT VERIFIED

- **Power loss.** Real power loss on NTFS was not tested; only clean prefix cuts (plus a zero tail for the sidecar). Reordered writes, stale blocks and metadata loss: NOT VERIFIED.
- **sfn26 launcher.** Whether the packaged skellycam/freemocap launcher kills an sfn26 ffmpeg grandchild (a kill-on-close job object): NOT VERIFIED. That decides 0 vs 300/300 (§2.10).
- **sfn26 probing bound.** The probing cause and its bound are not separated (probesize vs analyzeduration): NOT VERIFIED (§2.10).
- **FreeMoCap reader.** FreeMoCap's own reader was not run on unfinalized MKV. inferred from §2.2: OpenCV-based readers will miscount and mis-seek.
- **Low-delay encoding.** The settings (§2.5) were counted, not decoded and not combined with a kill. Playability, quality, size and speed: NOT VERIFIED. The SVT run also switched CRF to CQP.
- **Segment muxer.** The buffering mechanism behind its 2-frame loss: NOT VERIFIED (§2.1). Whether `-fflags flush_packets` propagates to the inner muxer: untested.
- **Chromium.** Presentation and pixels during play were not verified (hidden window, §2.7). Seek identity was checked only in Electron 35 and only on the cl0/fmp4_every files.
- **PyAV 19 coverage.** The re-checks were a subset:
  - drained kills for 12 MJPEG, 7 NVENC and 6 AV1 containers;
  - 3 live `rt` kills;
  - the segment muxer with and without fp;
  - 12 cuts × 5 variants (ideal taken from the image itself, not from a clean file);
  - 19 Electron files;
  - 5 of 9 resumable scenarios.

  These remain PyAV 18 background only:
  - the `idle` and `busy` kill modes, and the other `rt` rows;
  - FFV1 kills, `mkv_resv`, `fmp4_1s`, IVF, `seg_mp4`;
  - the 389-file repair check;
  - the Electron NUT/AVI/IVF/plain-MP4 rows.

  The raw+index and folder writers are pure Python, so they don't depend on the PyAV version.
- **Inputs.** One input set (720p MJPEG, 55.4 KB/frame), 150-frame files, GOP 30 only. Matroska's 5 s / 5 MiB cluster defaults and longer GOPs were not exercised. Frames per 256 KiB scale with bitrate (inferred).
- **Kill types.** Only TerminateProcess kills were tested; no OS crash or BSOD.
- **Machine load.** The functional runs shared the machine with other agents.
  - Drained-kill frame counts are deterministic by construction (§2.1).
  - The encoder hold-back count depends on live pacing. It was the same in 2/2 SVT runs and agrees with the live kill (36 muxed), but that is not proven under all loads.
- **Not checked against the ISO registry:** whether FFV1-in-MP4 is a registered mapping (NOTES §3.2). Reference-file MP4 repair tools (untrunc) were not tested.
- **Clock across restarts.** Whether QueryPerformanceCounter / `perf_counter_ns` stays consistent across process restarts was not tested; the prototype uses `time.time_ns()`.
- **Electron offset.** The cause of the constant offset of 4 in Electron's `decoded_during_play`: NOT VERIFIED (§2.7).
- **Quick Sync.** Intel iGPU encoders were not part of this topic.
- **Interrupted PyAV 18 runs.** The first passes of both `kill_matrix_a` and `kill_matrix_b` were ended externally (cause unknown). Both have `resumed_from_partial_run: true` and `replaced_modes: [busy, rt]`, and were completed with `--resume`.
- **ffmpeg CLI.** The ffmpeg 9.0.2 CLI wrote the reference repairs and the sfn26 stand-in files (see Versions). It is not the implementation under test.

## 7. How to reproduce

Run from the repo root `C:/Users/Dom/GitHub/freemocap/skellycam`. Media is written under `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/crash_resilience/pyav19_check/`.

```
C=research/skellycam_recording/recording_upgrade/scripts/crash_resilience/pyav19_checks
R=research/skellycam_recording/recording_upgrade/results/crash_resilience
# PyAV 19.0.2 (PEP 723: av==19.0.2, numpy)
uv run --script $C/pyav19_check.py        $R/pyav19_recheck.json             # §2.1, §2.2, §2.3, §2.6 (run twice -> pyav19_recheck_repeat.json)
uv run --script $C/encoder_hold_check.py  $R/encoder_hold_check_pyav19.json > $R/encoder_hold_check_pyav19.log 2>&1   # §2.5
uv run --script $C/trunc_pyav19.py        $R/truncation_pyav19.json          # §2.4
uv run --script $C/resumable_pyav19.py    $R/resumable_demo_pyav19.json      # §2.8
uv run --script $C/verify_method/verify_method_checks.py $R/verify_method_pyav19_checks.json   # §2.1 segment + rt kills
# OpenCV 4.12.0 readers (skellycam venv, read-only use)
.venv/Scripts/python.exe $C/cv2_on_pyav19.py     $R/cv2_on_pyav19_files.json         # §2.2
.venv/Scripts/python.exe $C/cv2_seek_identity.py $R/cv2_seek_identity_pyav19_files.json
.venv/Scripts/python.exe $C/verify_method/cv2_on_pyav_remux.py $R/verify_method_cv2_on_pyav_remux.json   # §2.3
# Electron (unset ELECTRON_RUN_AS_NODE first); list built from the PyAV 19 kill images
python $C/build_el_list.py $R/electron_pyav19_list.json
P=research/skellycam_recording/recording_upgrade/scripts/crash_resilience/electron_probe
skellycam-ui/node_modules/electron/dist/electron.exe $P $R/electron_pyav19_list.json $R/electron_pyav19_e35.json
C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/shared/electron-latest/node_modules/electron/dist/electron.exe $P $R/electron_pyav19_list.json $R/electron_pyav19_e45.json
# Electron 35 seek frame identity: app in $C/verify_method/seekprobe/ (main.js, pairs_e35.json) -> $R/verify_method_electron_seek_identity_e35.json
```

- PyAV 18 background runs, and the sidecar and sfn26 tests: the commands are in NOTES §3.5.
- FFmpeg n9.0.2 source files were fetched from `https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/libavformat/<file>` and `.../libavcodec/<file>`; SVT-AV1 from `https://gitlab.com/AOMediaCodec/SVT-AV1/-/raw/v4.2.0/Docs/Parameters.md`.
- The sfn26 code is from `git show upstream/sfn26:<path>` (765bf82d).

## 8. Verification

Two verifier reports challenged the draft: `VERIFY_provenance.md` (sources and numbers) and `VERIFY_method.md` (method and confounders). I re-checked each refutation against the raw JSON before changing anything.

**Refuted, now corrected (all four confirmed against the raw JSON):**

| draft claim | evidence | change |
|---|---|---|
| `ffmpeg -c copy` kept the count in 21/21 | `pyav19_recheck.json`: 19 rows have `ffmpeg_copy_mkv`, all match; seg_mkv+fp not repaired | 19/19, demoted to reference only; the PyAV opaque remux (19/19) is now primary |
| default `add_stream_from_template` fails for 5/5 AV1 files | 4 AV1 rows have the libdav1d error; AV1 mkv (0 B) and mp4+fp are `null` | 4/4 readable AV1 files |
| the PyAV seek check passed; "true for ffprobe and PyAV" | avi+fp target 75 → got 0; nut/nut+fp `exact:false`; `ok` = "at or before target" (`common_cr.py:236-249`); ffprobe had no seek test | per-container PyAV seek table (§2.2); AVI unseekable for both readers; ffprobe removed from the seek claim |
| bg naive PyAV loop up to 5 frames short | `truncation_b.json` AV1 fmp4_kf+fp `pyav_max_short` = 6 | up to 6 |

**Weak claims, relabelled or narrowed:**
- the ffmpeg CLI writing files is now disclosed;
- the PyAV 18 template-failure citation is now `kill_matrix_b.json` → `repair.pyav_copy`;
- probing is labelled inferred, with analyzeduration added (I checked `options_table.h:56` and `demux.c:2638-2641` in the fetched n9.0.2 copy);
- the "low delay + cl0 = 1 frame" claim is labelled inferred, and the live `rt` kill results are added;
- 57 KB → 55.4 KB;
- 8 KiB → measured bytes lost;
- the Electron end time is split into MKV/WebM vs fMP4;
- the −4 counts are given per Electron version, and 23 vs 21 differences are explained;
- `^35.0.3` range, 35.7.5 installed;
- segment muxer: P19 with/without fp measured, `segment.c:161-167` (checked), mechanism NOT VERIFIED;
- both kill_matrix files were resumed;
- the post-repair OpenCV seek claim is narrowed (pixel-checked on 2 CLI files, 5/5 PyAV remuxes);
- the machine line now cites HANDOFF.md (it is at lines 62-63 now, not 60-61);
- "seek ok" in Chromium is replaced by the seek frame-identity result;
- "ended" no longer implies presentation;
- torn frames without fp are noted;
- the AV1 torn-sample column is filled in;
- the SVT CRF/CQP confounder is stated (log lines 9, 18, 33, 42 checked);
- the drained-kill determinism is stated;
- the `cr_fsync` file-object confounder is stated.

**Where my re-check differs from the verifiers:**
- NUT landed about **1** frame early (151572 vs 153600 at 2048 ticks/frame), not 2.
- Electron H.264 stale reads at `seeked` were **7/16** (3 MKV, 4 fMP4), not 6/16.
- The AV1 fMP4 PyAV errors were 11 at `avcodec_send_packet()` and 1 at `avcodec_receive_frame()`, not 12 at send_packet.
- New: MJPEG nut+fp raised `InvalidDataError` in 2/12 cuts with no frame shortfall.

**Added bench requests:** `cr_fsync` and `cr_fragment_overhead` in their uv PyAV 19 forms, and the low-delay encoder bench (§5).

**Still NOT VERIFIED:**
- low-delay + cl0 in a kill;
- low-delay cost and quality;
- the segment muxer's buffering mechanism;
- the sfn26 probing bound;
- the Electron −4 offset;
- the packaged launcher's grandchild kill;
- real NTFS power loss;
- Chromium presentation during play;
- a Windows fsync of a path-opened file.
