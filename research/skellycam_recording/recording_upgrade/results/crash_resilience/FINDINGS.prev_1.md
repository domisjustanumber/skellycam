# crash_resilience (G2): FINDINGS

Goal G2: resumable, crash-tolerant recording files, so that a crashed session's recording still plays. Machine "Gerald" (Windows 11, i7-14700K, RTX 3070 driver 610.88), 2026-11-09. This topic has functional results only. It contains no timing numbers.

**Labels.** **measured** = a result file (paths are relative to `research/skellycam_recording/recording_upgrade/results/crash_resilience/` unless they start with `research/`). **source** = a primary source, accessed 2026-11-09. **code** = file:line. **inferred** = reasoning, kept to a minimum.

**Versions.** The implementation under test is **PyAV 19.0.2**. Its bundled FFmpeg reports libavformat 63.1.102 and libavcodec 63.1.102 (measured, `pyav19_recheck.json` → `env`). That matches FFmpeg tag n9.0.2: `LIBAVFORMAT_VERSION_MAJOR 63`, `MINOR 1` (source, `libavformat/version_major.h:32` and `version.h:34` at n9.0.2, https://github.com/FFmpeg/FFmpeg/tree/n9.0.2). Results made with PyAV 18.0.0 (the skellycam venv, libavformat 62.12.102) are marked **background**. The ffprobe 9.0.2 CLI was used only to read and inspect files. The OpenCV checks used the skellycam venv's OpenCV 4.12.0, read-only.

---

## 1. Questions answered

1. After a hard process kill, and after an emulated power cut, how many frames can be read from each container and option? Payloads: MJPEG passthrough, FFV1, SVT-AV1, NVENC H.264.
2. Why are frames lost? The mechanisms, from FFmpeg source.
3. Can ffprobe, PyAV, OpenCV and Chromium/Electron use an unfinalized file without repair? What does repair fix?
4. How many frames does the encoder hold back, frames no container can save? Can settings reduce that?
5. What does "resumable" mean, and does a Python prototype work on PyAV 19?
6. How durable is the timestamp sidecar?
7. How does the sfn26 Rust recorder (a plain MP4 written through an ffmpeg child) behave when killed? And today's skellycam?

## 2. Findings

### 2.1 Hard kill, PyAV 19.0.2 (implementation under test)

How the test was run: `writer_child.py` ran under PyAV 19.0.2. It was killed with TerminateProcess after all 150 frames were muxed (and the encoder drained), but before `close()`. Input: corpus `c930e_720p_flash`, 1280x720 MJPEG, about 57 KB/frame. A second identical run gave the same frame counts and byte sizes in all 25 cases (measured, `pyav19_recheck_repeat.json`).

| container (`+fp` = `flush_packets=1`) | MJPEG: readable / 150 (byte-exact) | H.264 NVENC | AV1 (SVT-AV1 4.2.0) |
|---|---|---|---|
| mkv | 146 (146) | 100 | **0** (0-byte file) |
| mkv+fp | 149 (149) | 120 | 120 |
| mkv_cl0+fp (`cluster_size_limit=0`, `cluster_time_limit=0`) | 149 (149) | 149 | 149 |
| webm_cl0+fp | - | - | 149 |
| fmp4_every (`frag_every_frame`, no fp) | 147 (146) | - | - |
| fmp4_every+fp | 149 (149) | 149 | 149 |
| fmp4_kf+fp | 149 (149) | 120 | - |
| mp4 / mp4+fp (plain) | **0 / 0** | - / 0 | - / 0 |
| nut | 147 (146) | - | - |
| nut+fp | **150 (150)** | 150 | - |
| avi+fp | **150 (150)** | - | - |
| seg_mkv+fp (segment muxer, 1 s) | 148 (segments 30, 30, 30, 30, 28) | - | - |

All of the above: measured, `pyav19_recheck.json` → `kill[]`, ffprobe `-count_frames`. In every readable case, PyAV 19 read the same count.

- measured: files written without `flush_packets` are exact multiples of 262144 bytes:
  - MJPEG mkv: 8126464 B = 31 × 262144
  - MJPEG nut: 8126464 B
  - NVENC mkv: 1310720 B = 5 × 262144
  - MJPEG mp4 and fmp4_every: 8126508 B = 31 × 262144 + 44

  Source: `pyav19_recheck.json` → `bytes`, `bytes_mod_262144`.
- measured: AV1 mkv without fp left a **0-byte file**, while the flushed AV1 files are 184533–241301 B (`pyav19_recheck.json`). inferred: the whole 5 s AV1 recording fit inside the 256 KiB write buffer.
- measured: on PyAV 19, NVENC mkv without fp kept 100/150. On PyAV 18 it kept 117/150 (background, `kill_matrix_b.json`). Both file sizes are multiples of 262144, so the count depends on where the buffer boundary falls.
- source (mechanism, FFmpeg n9.0.2):
  - `libavformat/file.c:324-332`: for written regular files `h->max_packet_size = 262144` ("Buffer writes more than the default 32k to improve throughput") and `h->min_packet_size = h->max_packet_size` ("Disable per-packet flushing by default").
  - `libavformat/mux.c:425-433` (`flush_if_needed`): `avio_flush` only `if (s->flush_packets == 1 || ...)`; otherwise it writes a FLUSH_POINT marker.
  - `libavformat/options_table.h:84`: `flush_packets` default `{.i64 = -1}`.
  - `libavformat/aviobuf.c:466-469`: a FLUSH_POINT flushes only `if (s->buf_ptr - s->buffer >= s->min_packet_size)`.

  URL: https://github.com/FFmpeg/FFmpeg/blob/n9.0.2/libavformat/
- source (what the muxers still hold in memory with fp):
  - `matroskaenc.c:3032-3048`: a Cluster is built in `cluster_bc` and written in `mkv_end_cluster`.
  - `matroskaenc.c:3231-3236`: a new Cluster starts on size or time limit, or on a video key frame once the cluster is over 4 KiB.
  - `matroskaenc.c:2744-2748`: the defaults are 5000 ms and 5 MiB.
  - `movenc.c:7449-7455`: a fragment is flushed when the *next* packet meets the condition (duration, key frame, or `FF_MOV_FLAG_FRAG_EVERY_FRAME`).
  - inferred from the code and matching the 120/150 vs 149/150 results: the open Cluster or fragment is lost. With GOP 30 that is up to one GOP for inter codecs, unless every frame closes it (cl0 / frag_every_frame).

### 2.2 Reading unfinalized files without repair (PyAV 19 files)

- measured: ffprobe and PyAV 19 read every readable kill image, and the PyAV mid-file seek check passed. Unfinalized MKV reports **no duration**. fMP4+fp reports 4.966992 s, the complete fragments (`pyav19_recheck.json` → `ffprobe_format_duration`, `pyav.seek`).
- measured (OpenCV 4.12.0): `CAP_PROP_FRAME_COUNT` values (`cv2_on_pyav19_files.json`):

  | file | frame count reported | frames read |
  |---|---|---|
  | MJPEG mkv+fp | **-2.767e17** | 149 |
  | AVI+fp | **0** | 150 |
  | NUT+fp | 149 | 150 |
  | fMP4_every+fp | 149 (correct) | 149 |
  | NVENC mkv_cl0+fp | -2.767e17 | 149 |
  | AV1 mkv_cl0+fp | -2.767e17 | 149 |

- **measured (new; corrects NOTES §4.1 and the bench-queue summary).** OpenCV's frame-index seek goes **silently** to frame 0 on unfinalized MKV and AVI. After `CAP_PROP_POS_FRAMES = 74`, `set()` and `read()` both return True, but the image returned is pixel-identical to sequential frame **0** (`pos_after` 1.0). This held for MJPEG mkv+fp, MJPEG avi+fp and NVENC mkv_cl0+fp. On fMP4+fp, NUT+fp and the `-c copy` repaired MKVs it returns frame 74 (`cv2_seek_identity_pyav19_files.json`).
  - measured, PyAV 18 (background): every drained MKV, WebM, AVI and raw-MJPEG row in `kill_matrix_a.json` / `kill_matrix_b.json` has `read.cv2.seek.pos_after == 1.0`. fMP4, NUT, IVF and folder rows land on target+1. So "cv2 seek worked" in NOTES (H.264/AVI) and "seeking works" in the bench-queue summary are true only for ffprobe and PyAV.

### 2.3 Repair (PyAV 19 files)

- measured: `ffmpeg -c copy` to `.mkv` kept the frame count of every readable kill image (21/21) and restored a finite duration (e.g. MJPEG mkv+fp gives 149 frames, 4.966 s) (`pyav19_recheck.json` → `ffmpeg_copy_mkv`).
- measured: after repair, OpenCV reports the correct frame count (149 and 150) and seeks to the right frame (`cv2_on_pyav19_files.json`, `cv2_seek_identity_pyav19_files.json`).
- measured: PyAV 19 `add_stream_from_template(ist)` with default arguments **fails for every AV1 file** (5/5: `UnknownCodecError: libdav1d`, 0 packets). With `opaque=True` all AV1 files remux with the full count (120/149). MJPEG and H.264 remux with either setting (`pyav19_recheck.json` → `pyav_remux_template_default` / `_opaque`). PyAV 18 showed the same failure (background, `pyav_remux_opaque_check.json`).
- measured: a plain MP4 kill image has 0 readable frames and gives `InvalidDataError`, so there is nothing to remux (`pyav19_recheck.json`).

### 2.4 Emulated power loss (prefix cuts), PyAV 19 files

Method: 12 seeded cuts per variant. "ideal" = the packets in the image's own ffprobe packet table that end before the cut. Measured, `truncation_pyav19.json`.

| variant | ffprobe = ideal | ffprobe = ideal + 1 | torn last JPEG handed to the decoder | PyAV naive loop < ffprobe |
|---|---|---|---|---|
| MJPEG mkv+fp | 12/12 | 0 | **0/12** | 0 |
| MJPEG fmp4_every+fp | 0 | 12/12 | **12/12** | 0 |
| MJPEG nut+fp | 2 | 10/12 | **12/12** | 0 |
| AV1 mkv_cl0+fp | 12/12 | 0 | n/a | 0 |
| AV1 fmp4_every+fp | 12/12 | 0 | n/a | **12/12, up to 6 frames short** |

- measured, PyAV 18 (background, 24 cuts per variant across about 90 variants, `summary.md` truncation table generated from `truncation_a.json` / `truncation_b.json`):
  - Matroska/WebM: ratio 0.998–1.000, never a torn frame.
  - plain MP4: ratio 0.000, 0 frames in 20–22 of 24 cuts.
  - seg_mp4: 0.69–0.89.
  - fMP4, NUT, AVI, raw MJPEG and the JPEG folder count the torn frame (ratio up to 1.023).
  - naive PyAV loop up to 5 frames short for AV1 in fMP4, NUT, AVI and IVF.
- inferred: a production reader must catch per-packet errors, drain the decoder, and validate the last JPEG (SOI/EOI). The prototype's MJPEG repair does the SOI/EOI check (NOTES §5). There is no H.264/AV1 equivalent.

### 2.5 Frames held by the encoder (no container can save these), PyAV 19

Method: 75 decoded camera frames fed at 30 fps; count the packets returned before the drain. Measured, `encoder_hold_check_pyav19.json` and `.log`; SVT cases ran twice with the same counts.

| encoder settings | packets out / 75 | held by the encoder |
|---|---|---|
| libsvtav1 preset 10, crf 35, defaults (log: "pred struct: random access", mini-gop 16) | 36 | **39** |
| libsvtav1 same + `svtav1-params=pred-struct=1` (log: "low delay", mini-gop 4) | 75 | **0** |
| h264_nvenc p4, bf 0, vbr cq 23 | 73 | 2 |
| h264_nvenc same + `delay=0` | 75 | **0** |

- source: SVT-AV1 v4.2.0 `Docs/Parameters.md:261`, `--pred-struct`, default 2, "Set prediction structure [0: all intra, 1: low delay, 2: random access]" (https://gitlab.com/AOMediaCodec/SVT-AV1/-/blob/v4.2.0/Docs/Parameters.md).
- source: FFmpeg n9.0.2 `libavcodec/nvenc_h264.c:100-101`, `"delay"`, "Delay frame output by the given amount of frames", default `INT_MAX`.
- source: FFmpeg n9.0.2 `libavcodec/libsvtav1.c:830`, `svtav1-params`, "Set the SVT-AV1 configuration using a :-separated list of key=value parameters".
- measured: with pred-struct=1, SVT logs "TPL is disabled in low delay applications." (`encoder_hold_check_pyav19.log`). The quality, size and speed effects of either low-delay setting were **not tested**. The low-delay packets were counted but not decoded.
- measured, PyAV 18 (background): in the kill matrix `rt` mode, AV1 muxed 35 of 75 fed frames and NVENC muxed 73 (`summary.md` kill table).

### 2.6 `pict_type` side finding, PyAV 19

- measured: frames decoded from camera JPEGs carry `pict_type` "1" (I). Results (`pyav19_recheck.json` → `pict_type`; PyAV 18 gave the same, background, `pict_type_check.json`):

  | encoder | key frames, pict_type unchanged | key frames, pict_type = NONE |
  |---|---|---|
  | libsvtav1 | **60/60** | 2/60 |
  | libx264 | **60/60** | 2/60 |
  | h264_nvenc | 2/60 | 2/60 |

  So a transcoding pipeline must set `frame.pict_type = PictureType.NONE`.

### 2.7 Electron / Chromium playback of damaged PyAV 19 files

19 files, hidden window, play from 0 at rate 4. Electron 35.7.5 = Chromium 134.0.6998.205; Electron 45.2.3 = Chromium 156.0.8078.80. Measured, `electron_pyav19_e35.json`, `electron_pyav19_e45.json`, list `electron_pyav19_list.json`. "end t" = `final_currentTime`; in every ended file it equals the last frame's time (e.g. 4.933 s = frame 148 at 30 fps).

| file | Electron 35.7.5 | Electron 45.2.3 |
|---|---|---|
| MJPEG mkv+fp kill | MediaError 4 `DEMUXER_ERROR_NO_SUPPORTED_STREAMS` | same |
| AV1 / H.264 mkv+fp kill (120 frames) | ended, end t 3.967 s, duration Infinity, seek ok | same |
| AV1 / H.264 mkv_cl0+fp, AV1 webm_cl0+fp kill (149) | ended, end t 4.933 s, duration Infinity | same |
| the same cut at 60 % / 95 % | ended (AV1 end t 2.8 / 4.4 s; H.264 2.933 / 4.667 s) | same |
| AV1 / H.264 fmp4_every+fp kill (149); H.264 fmp4_kf+fp (120) | ended, finite duration (4.966667 / 4 s) | same |
| AV1 fmp4_every+fp cut 60 % / 95 % | MediaError 3 `PIPELINE_ERROR_DECODE` part-way (end t 2.42 / 4.05 s) | same error |
| H.264 fmp4_every+fp cut 60 % | MediaError 4 `DEMUXER_ERROR_BITSTREAM_CONVERSION_FAILED`, 0 frames decoded | **ended**, end t 3 s |
| H.264 fmp4_every+fp cut 95 % | same error, 73 of 141 decoded | **ended**, end t 4.733 s |

- measured: these match the 218-file PyAV 18 run (background, `electron_e35.json` / `electron_e45.json`, 23 differences by id). There, both versions also failed on NUT, AVI, IVF and killed plain MP4 with MediaError 4 `DEMUXER_ERROR_COULD_NOT_OPEN`. Those containers were not re-run with PyAV 19 files.
- measured: in every ended file, `decoded_during_play` = expected − 4 (132/132 PyAV-18 files, 14/14 PyAV-19 files). NOTES explains the 4 as frames decoded before `play()`, but `totalVideoFrames_before_play` was 9–38 in those runs. **The cause of the offset is NOT VERIFIED.** Use `final_currentTime` as the evidence that the last frame was reached.

### 2.8 Resumable recorder prototype on PyAV 19

What it is: `scripts/crash_resilience/resumable_recorder.py`. It writes a `manifest.jsonl` journal (fsync per record), per-segment MKV with `flush_packets=1` (2 s segments), and a 32-byte CRC'd `timestamps.bin`. Child writers ran under PyAV 19.0.2, killed with TerminateProcess. Measured, `resumable_demo_pyav19.json`.

| scenario | lost frames | video frames == ts records | unique + increasing | gaps listed as lost | pts == capture clock | MJPEG byte-exact | joined MKV |
|---|---|---|---|---|---|---|---|
| kill mid-segment (MJPEG) | 1 [169] | 259 == 259 | yes | yes | yes | 259/259 | 259 |
| double crash | 2 [99, 174] | 233 == 233 | yes | yes | yes | 233/233 | 233 |
| power loss, seed 0 (segment, sidecar and journal torn) | 7 [149–155] | 209 == 209 | yes | yes | yes | 209/209 | 209 |
| power loss, seed 1 | 36 [130–165] | 190 == 190 | yes | yes | yes | 190/190 | 190 |
| FFV1 kill mid-segment | 1 [169] | 259 == 259 | yes | yes | yes | n/a | 259 |

- measured, PyAV 18 (background, `resumable_demo.md`): 9 scenarios passed, including 5 power-loss seeds and a kill at a segment rollover. A bug where an orphan segment was overwritten was found and fixed during that work (NOTES §7).
- measured: after a power cut, frame numbers whose video *and* sidecar record were both lost are reused by the resumed run. The outage shows only as a capture-time gap (NOTES §7; `max_capture_gap_ms` in the JSON). The gap values were taken on a loaded machine and are not a benchmark.

### 2.9 Timestamp sidecar (does not depend on PyAV; Python 3.12.13, pandas 3.0.2)

- measured, process kill after 1 / 37 / 500 rows (`sidecar_durability.md`):

  | writer | rows intact |
  |---|---|
  | CSV + `flush()` per row | 1 / 37 / 500 |
  | binary 72-byte record + CRC + flush | 1 / 37 / 500 |
  | CSV with default buffering | 0 / 0 / 456 |
  | binary with default buffering | 0 / 0 / 452 |

- measured, 24 cuts × 2 tails (`sidecar_durability.json`, recounted from the raw rows):
  - The strict CSV parser and the CRC binary parser recovered exactly the complete rows in 48/48.
  - pandas `read_csv` returned an extra row in 23/24 cuts (24/24 with a zero-filled tail).
  - Of those, **6/24 were complete-looking rows with wrong integer values**; the rest were NaN-padded (17, or 18 with zeros).
- code: sfn26 `skellycam-rust/src/timestamps/csv_writer.rs:72` flushes each row (`self.writer.flush()`). No `sync_all`/`sync_data` appears in the file (git show upstream/sfn26 765bf82d).

### 2.10 sfn26 Rust recorder and today's skellycam

- code (sfn26 765bf82d), `skellycam-rust/src/recording/recorder.rs`:
  - `:40-45`: defaults `image2pipe`, `mjpeg`, `libx264`, `ultrafast`, crf 18, `yuv420p`.
  - `:141-156`: spawns ffmpeg with no movflags.
  - `:233`: "Drop stdin so ffmpeg sees EOF and writes the file trailer".
  - `:266-275`: `Drop` calls `self.ffmpeg_child.kill()`.
  - `camera_group/dispatcher.rs:373` names the output `.mp4`.
- measured: the sfn26 arguments were reproduced with the ffmpeg 9.0.2 CLI as a stand-in for sfn26's child process, not as the implementation under test. Feed 300 of 600 frames, wait 1 s, then kill (`sfn26_pipe.md`):

  | output | kill ffmpeg (= `Drop`) | kill the whole tree | kill only the feeder |
  |---|---|---|---|
  | plain MP4 | **0** | **0** | **300/300**, finalized, 10.0 s |
  | MKV x264 | 246 | 246 | - |
  | fMP4 x264 | 246 | 246 | - |
  | MKV MJPEG copy | 293 | 293 | - |

- measured: with 75 frames (4.3 MB) fed and 1 s of waiting, killing ffmpeg left **no output file** in all 4 outputs, while killing the feeder still gave 75/75 (`sfn26_pipe_n150.md`). source: the default `probesize` is `{.i64 = 5000000 }` (FFmpeg n9.0.2 `libavformat/options_table.h:39`). inferred: ffmpeg was still probing its input.
- background (today's skellycam, verified review): a hard kill leaves an MSMF `.mp4` with 0 readable frames, and no timestamps CSV is written unless the stop is clean (`research/skellycam_recording/REPORT.md:27`, `:210-213`, `:226`).

## 3. Comparison tables

**A. Recording container after a crash.** Columns: kill loss (MJPEG, fp, §2.1) / torn frame after a power cut (§2.4) / OpenCV on the unfinalized file (§2.2) / Chromium (§2.7). Legend: P19 = PyAV 19 measured; bg = PyAV 18 background.

| container | kill loss, MJPEG (+fp) | torn JPEG handed out after a cut | OpenCV frame count / seek, unfinalized | Chromium plays unfinalized AV1/H.264 | Chromium plays MJPEG |
|---|---|---|---|---|---|
| MKV/WebM + fp | 1 frame (P19) | no (P19, bg) | -2.767e17 / **silently frame 0** (P19) | yes, duration Infinity (P19) | no |
| MKV/WebM + fp + cl0 | 1 frame (P19), and 1 frame for inter codecs | no | same as above | yes | no |
| fMP4 frag_every + fp | 1 frame (P19) | **yes** (P19) | correct / correct (P19) | yes; a torn sample gives MediaError (AV1 both versions, H.264 E35) | no |
| plain MP4 | **all** (P19) | n/a (0 frames) | not readable | no (bg) | no |
| NUT + fp | 0 (P19) | **yes** (P19) | off by 1 / correct (P19) | no, cannot open (bg) | no |
| AVI + fp | 0 (P19) | yes (bg) | 0 / **silently frame 0** (P19) | no (bg) | no |
| segment muxer (mkv) | 2 frames; ignores fp (P19, bg) | no (bg) | not tested | not tested | no |
| raw .mjpeg + CRC index, flush | 0 (bg) | own parser: no; ffprobe: yes (bg) | -1.92e14 / frame 0 (bg) | no | no |
| folder of JPEGs | 0 (bg) | yes (bg) | n/a | no | no |

**B. Where frames are lost, and what bounds the loss.**

| loss source | size without mitigation | mitigation | evidence |
|---|---|---|---|
| FFmpeg file-protocol buffer | up to 262144 B (4–5 MJPEG frames; a whole 5 s AV1 file) | `flush_packets=1` | measured §2.1; source file.c/mux.c |
| open MKV Cluster | 1 frame (intra); up to 1 GOP (inter) | `cluster_size_limit=0` + `cluster_time_limit=0` | measured §2.1; source matroskaenc.c |
| open fMP4 fragment | 1 frame (every), 1 GOP (kf), 1 s (1 s fragments, bg) | `frag_every_frame` | measured §2.1; source movenc.c |
| plain MP4 `moov` never written | everything | don't record to plain MP4 | measured §2.1, §2.10 |
| encoder hold-back | SVT-AV1 39 frames, NVENC 2 (at 30 fps) | SVT `pred-struct=1`, NVENC `delay=0`: 0 held | measured §2.5 |
| ffmpeg-CLI probing (sfn26 pattern) | first ~5 MB | n/a (avoid the CLI child) | measured §2.10; source probesize |
| unflushed CSV sidecar | everything since the last 8 KiB-ish block | flush per row; CRC binary record | measured §2.9 |

## 4. Implications for the plan

1. **Recording container for G1 (MJPEG passthrough): Matroska with `flush_packets=1`.** It loses 1 frame on a kill and keeps every frame byte-exact. It never hands out a torn frame after a cut, and ffprobe/PyAV read it without repair (§2.1, §2.2, §2.4). NUT/AVI save one more frame on a kill, but they hand out torn frames and Chromium can't open them (§2.4, §3A).
2. **Set `flush_packets=1` on every libavformat writer.** The default loses up to 256 KiB, and with a low-bitrate codec that can be the whole file (§2.1). The cost is pending, bench `cr_fragment_overhead`.
3. **For inter codecs (G6/G7) you need both container and encoder settings.** Use MKV/WebM `cluster_size_limit=0` + `cluster_time_limit=0`, or fMP4 `frag_every_frame`, *plus* low-delay encoding: SVT-AV1 `pred-struct=1`, NVENC `delay=0`. Only with both is the loss 1 frame, not up to a GOP plus 39 frames (§2.1, §2.5). The quality and speed cost of low delay is untested (§6).
4. **Never record to plain MP4.** Use it at most as a finalize/remux target. This applies to today's MSMF path and to sfn26 (§2.1, §2.10).
5. **Use application-level segments, not the `segment` muxer.** The muxer ignores `flush_packets` and lists a segment only once it is closed (§2.1; NOTES §2 M12). The prototype already works this way (§2.8).
6. **OpenCV must not read unfinalized MKV/AVI.** Its frame count is garbage and frame-index seeks silently return frame 0 (§2.2). Before handing a crashed session to FreeMoCap or any `cv2.VideoCapture` reader, the plan needs a finalize step (`ffmpeg -c copy` or a PyAV remux to `.mkv`; both fix count and seek, §2.3). PyAV readers must catch per-packet errors and drain the decoder (§2.4).
7. **PyAV-based repair must pass `opaque=True`** to `add_stream_from_template`, or AV1 fails (§2.3).
8. **For the UI during or after a crash, prefer MKV/WebM over fMP4.** Chromium plays unfinalized and prefix-cut MKV/WebM to the end. A torn fMP4 sample is a MediaError in Electron 35, the version the UI pins (§2.7). MJPEG/FFV1 never play in Chromium, so G1/G4 recordings need a separate preview or proxy path whatever the crash handling (§2.7).
9. **Timestamp sidecar: a fixed-size binary record with a CRC, flushed per frame.** Don't use a CSV parsed by pandas, which returned silently wrong integers (§2.9). The fsync policy is pending, bench `cr_fsync`.
10. **Set `frame.pict_type = NONE` whenever decoded JPEG frames are re-encoded.** Otherwise libsvtav1 and libx264 make every frame a key frame (§2.6).
11. **"Resumable" as defined in NOTES §7 works on PyAV 19** (§2.8): journal + per-segment MKV+fp + CRC sidecar. The segment length depends on repair cost, bench `cr_repair`.
12. **From sfn26, reuse the per-row flush idea, not the ffmpeg-child plain MP4.** `Drop` or a tree kill loses the whole file, and probing holds the first ~5 MB (§2.10).

## 5. Pending tonight's bench

Before running: every manifest command calls `.venv/Scripts/python.exe`, which is PyAV 18. Under the PyAV-19-only rule they need these changes first:

- code: `common_cr.env_versions()` imports `cv2` (`scripts/crash_resilience/common_cr.py:423-426`). A `uv run --script` environment with only `av==19.0.2` and `numpy` will fail there. Either add OpenCV to the PEP 723 deps or make `cv2` optional. The exact opencv-python pin is NOT VERIFIED.
- code: `bench_repair.py:38` starts `writer_child.py` with `cc.VENV_PY` (PyAV 18). It must use the PyAV 19 interpreter, e.g. a wrapper that sets `cc.VENV_PY = Path(sys.executable)`, as `scripts/crash_resilience/pyav19_checks/resumable_pyav19.py` does.
- The smoke files in `bench/` (`fsync_smoke.json`, `fragment_overhead_smoke*.json`, `repair_smoke.json`) were made with PyAV 18 on a loaded machine. Don't quote them.

| timed question | bench_manifest id |
|---|---|
| Per-frame latency (p50/p99/max), throughput and CPU of no flush / flush / fsync every 1, 10, 30, 300 frames / sidecar-only fsync / MKV+fp with fsync | `cr_fsync` |
| CPU, wall and size overhead of mkv vs +fp vs cl0, fMP4 per-frame vs 100–2000 ms fragments, plain mp4, nut, avi, segments 1/10/60 s, raw+index, folder (MJPEG, FFV1, NVENC packets) | `cr_fragment_overhead` |
| The same for AV1 packets | `cr_fragment_overhead_av1` |
| Repair seconds per GB (ffmpeg -c copy to mkv/mp4, PyAV remux, the prototype's segment repair; cold vs cached), which sets the segment length | `cr_repair` |
| Speed, size and quality cost of SVT-AV1 `pred-struct=1` and NVENC `delay=0` | **no manifest id**. Add one to the gpu_encode benches or here |
| Time from restart to the first new frame in the resumable recorder (the outage gap) | **no manifest id** |

## 6. Not tested, limits, NOT VERIFIED

- Real power loss on NTFS was not tested; only clean prefix cuts (plus a zero tail for the sidecar). Reordered writes, stale blocks and metadata loss: NOT VERIFIED.
- Whether the packaged skellycam/freemocap launcher kills an sfn26 ffmpeg grandchild (a kill-on-close job object): NOT VERIFIED. That decides 0 vs 300/300 (§2.10).
- FreeMoCap's own reader was not run on unfinalized MKV. inferred from §2.2: OpenCV-based readers will miscount and mis-seek.
- Low-delay settings (§2.5) were counted, not decoded. Playability, quality, size and speed: NOT VERIFIED.
- PyAV 19 re-checks were a subset:
  - drained kills for 12 MJPEG, 7 NVENC and 6 AV1 containers;
  - 12 cuts × 5 variants (ideal taken from the image itself, not from a clean file);
  - 19 Electron files;
  - 5 of 9 resumable scenarios.

  The following remain PyAV 18 background only: `idle`, `busy` and `rt` kill modes, FFV1 kills, `mkv_resv`, `fmp4_1s`, IVF, `seg_mp4`, the 389-file repair check and the Electron NUT/AVI/IVF/plain-MP4 rows. The raw+index and folder writers are pure Python, so they don't depend on the PyAV version.
- One input set (720p MJPEG, about 57 KB/frame), 150-frame files, GOP 30 only. Matroska's 5 s / 5 MiB cluster defaults and longer GOPs were not exercised. Frames per 256 KiB scale with bitrate (inferred).
- Only TerminateProcess kills were tested; no OS crash or BSOD.
- The functional runs shared the machine with other agents. Frame counts are deterministic: a repeat run was identical (`pyav19_recheck_repeat.json`). The encoder hold-back count depends on live pacing; it was the same in 2/2 SVT runs, but that is not proven under all loads.
- Not checked against the ISO registry: whether FFV1-in-MP4 is a registered mapping (NOTES §3.2). Reference-file MP4 repair tools (untrunc) were not tested.
- Whether QueryPerformanceCounter / `perf_counter_ns` stays consistent across process restarts was not tested; the prototype uses `time.time_ns()`.
- The cause of the constant offset of 4 in Electron's `decoded_during_play`: NOT VERIFIED (§2.7).
- Quick Sync (Intel iGPU) encoders were not part of this topic.
- The first PyAV 18 `kill_matrix_a` pass was ended externally (cause unknown) and completed with `--resume`.

## 7. How to reproduce

Run from the repo root `C:/Users/Dom/GitHub/freemocap/skellycam`. Media is written under `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/crash_resilience/pyav19_check/`.

```
C=research/skellycam_recording/recording_upgrade/scripts/crash_resilience/pyav19_checks
R=research/skellycam_recording/recording_upgrade/results/crash_resilience
# PyAV 19.0.2 (PEP 723: av==19.0.2, numpy)
uv run --script $C/pyav19_check.py        $R/pyav19_recheck.json             # §2.1, §2.3, §2.6 (run twice -> pyav19_recheck_repeat.json)
uv run --script $C/encoder_hold_check.py  $R/encoder_hold_check_pyav19.json > $R/encoder_hold_check_pyav19.log 2>&1   # §2.5
uv run --script $C/trunc_pyav19.py        $R/truncation_pyav19.json          # §2.4
uv run --script $C/resumable_pyav19.py    $R/resumable_demo_pyav19.json      # §2.8
# OpenCV 4.12.0 readers (skellycam venv, read-only use)
.venv/Scripts/python.exe $C/cv2_on_pyav19.py     $R/cv2_on_pyav19_files.json         # §2.2
.venv/Scripts/python.exe $C/cv2_seek_identity.py $R/cv2_seek_identity_pyav19_files.json
# Electron (unset ELECTRON_RUN_AS_NODE first); list built from the PyAV 19 kill images
python $C/build_el_list.py $R/electron_pyav19_list.json
P=research/skellycam_recording/recording_upgrade/scripts/crash_resilience/electron_probe
skellycam-ui/node_modules/electron/dist/electron.exe $P $R/electron_pyav19_list.json $R/electron_pyav19_e35.json
C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/shared/electron-latest/node_modules/electron/dist/electron.exe $P $R/electron_pyav19_list.json $R/electron_pyav19_e45.json
```

- The PyAV 18 background runs and the sidecar and sfn26 tests: the commands are in NOTES §3.5.
- FFmpeg n9.0.2 source files were fetched from `https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/libavformat/<file>` and `.../libavcodec/<file>`; SVT-AV1 from `https://gitlab.com/AOMediaCodec/SVT-AV1/-/raw/v4.2.0/Docs/Parameters.md`.
- The sfn26 code is from `git show upstream/sfn26:<path>` (765bf82d).
