# crash_resilience (G2): FINDINGS

Goal G2: recordings that can be resumed and that survive a crash, so a crashed session's recording still plays.

- **Machine:** "Gerald", Windows 11, i7-14700K (8 P-cores = CPUs 0–15, plus 12 E-cores), RTX 3070 with driver 610.88. Label: study record, not a primary source (`research/skellycam_recording/recording_upgrade/HANDOFF.md:111`, `:113`).
- **Disk:** C:, a WD_BLACK SN850X NVMe, the OS disk. Label: study record (`research/skellycam_recording/recording_upgrade/results/write_throughput/BENCH.md:4`). The CR JSONs record only the drive letter "C:".
- **Dates:** the functional results are from 2026-11-09. The intra NVENC kill and hold checks (§2.5) are from 2026-11-10. The timed results come from the quiet overnight run `20261109T230007` (2026-11-09 23:00 to 2026-11-10 05:36). This revision is dated 2026-11-10.
- **Scope (HANDOFF.md:42, requirement 8):** only intra-only formats are in scope.
  - The main kill matrix used NVENC H.264 at GOP 30 and SVT-AV1. Those rows are **background** for intra-only recording.
  - AV1 has no RTX 3070 encode path (measured, `research/skellycam_recording/recording_upgrade/results/hw_accel_target/functional_pyav19.md:48-52`: every `av1_nvenc` open fails).
  - The in-scope payloads are MJPEG passthrough (G1) and NVENC H.264/HEVC intra. The intra payloads appear in the CR-FRAG-INTRA bench (§2.12) and in one live kill per codec (§2.5).

**Labels.**
- **measured** = a result file. Paths are relative to `research/skellycam_recording/recording_upgrade/results/crash_resilience/` unless they start with `research/` or `scripts/`. `scripts/` is relative to `research/skellycam_recording/recording_upgrade/`.
- **source** = a primary source. FFmpeg and SVT-AV1 were accessed 2026-11-09 and re-fetched by the provenance verifier on 2026-11-10. Python and Microsoft docs were accessed 2026-11-10.
- **code** = file:line.
- **computed** = arithmetic on fields of a result file.
- **inferred** = reasoning, kept to a minimum.
- **bg** = background: PyAV 18, or a GOP/inter codec.

**Versions.**
- The implementation under test is **PyAV 19.0.2**. Its bundled FFmpeg reports libavformat 63.1.102 and libavcodec 63.1.102 (measured: `pyav19_recheck.json` → `env`; `env` in every `bench/*_pyav19.json`).
- That matches FFmpeg tag n9.0.2: `LIBAVFORMAT_VERSION_MAJOR 63`, `MINOR 1` (source, `libavformat/version_major.h:32` and `version.h:34` at n9.0.2, https://github.com/FFmpeg/FFmpeg/tree/n9.0.2).
- PyAV 18.0.0 results (the skellycam venv, libavformat 62.12.102) are **bg**.
- OpenCV checks used the skellycam venv's OpenCV 4.12.0, read-only.
- **Deviation from the inspect-only rule (disclosed).** In the 2026-11-09 functional work, the ffmpeg 9.0.2 CLI also wrote files: the `-c copy` repairs (code, `scripts/crash_resilience/common_cr.py:280-290`), the `*.repaired.mkv` files read by OpenCV, and the sfn26 stand-in outputs. These rows are labelled **"ffmpeg 9.0.2 CLI, reference only"**.
  - The timed run used the CLI only as ffprobe, to count frames after the repair timer stopped (code, `scripts/crash_resilience/bench_repair.py:104`, `:114`).

---

## 1. Questions answered

1. After a hard process kill, and after an emulated power cut, how many frames can be read from each container and option?
2. Why are frames lost? The mechanisms, from FFmpeg source.
3. Can ffprobe, PyAV, OpenCV and Chromium/Electron use an unfinalized file without repair? What does repair fix?
4. How many frames does the encoder hold back (frames no container can save)? Now measured for the in-scope intra NVENC settings as well as the GOP codecs (bg).
5. What does "resumable" mean, and does a Python prototype work on PyAV 19?
6. How durable is the timestamp sidecar?
7. How does the sfn26 Rust recorder (a plain MP4 written through an ffmpeg child process) behave when killed? How does today's skellycam behave?
8. **Timed, quiet run:** what do the durability policies cost per frame (flush, fsync every K, sidecar-only fsync)?
9. **Timed:** what do the crash-tolerant container settings cost in wall time and bytes, for MJPEG and for NVENC H.264/HEVC intra packets?
10. **Timed:** how many seconds per GB does repairing a killed 1 GB recording take, and how many frames come back?

## 2. Findings

### 2.1 Hard kill, PyAV 19.0.2 (functional)

**Method.** `writer_child.py` ran under PyAV 19.0.2.
- `drained` mode: the writer is killed with TerminateProcess after all 150 frames are muxed and the encoder is drained, but before `close()`.
- The kill happens while the writer is blocked in `stdin.readline()` (code, `scripts/crash_resilience/writer_child.py:29-32`, `:184-187`), so the result is deterministic by construction.
- A second run gave the same frame counts and byte sizes in all 25 cases (measured, `pyav19_recheck_repeat.json`; only `nvidia_smi_before` differs). This shows repeatability, not robustness to kill timing.
- Input: corpus `c930e_720p_flash`, 1280x720 MJPEG, **55.4 KB/frame** mean (measured: clean folder 8317014 B / 150, `kill_matrix_a.json`).

| container (`+fp` = `flush_packets=1`) | MJPEG: readable / 150 (byte-exact) | H.264 NVENC GOP 30 (bg) | AV1 SVT 4.2.0 (bg) |
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

- measured: every number in the table comes from `pyav19_recheck.json` → `kill[]` (ffprobe `-count_frames`). In every readable non-segment row, PyAV 19 read the same count. PyAV did not read the seg_mkv row.
- measured: **without fp, fmp4_every and nut hand out a torn frame after a plain process kill.** 147 frames are counted but only 146 are byte-exact (`pyav19_recheck.json` → `byte_exact`).
- measured: MKV and NUT files written without fp are exact multiples of 262144 B, e.g. MJPEG mkv and nut 8126464 B = 31 × 262144, and NVENC mkv 1310720 B = 5 × 262144 (`pyav19_recheck.json` → `bytes`, `bytes_mod_262144`).
- measured: the no-fp MJPEG fmp4_every and plain mp4 files are 8126508 B, 44 B over a multiple of 262144 (`bytes_mod_262144` = 44, same file).
- measured (bg): AV1 mkv without fp left a **0-byte file**; NVENC mkv without fp kept 100/150 (`pyav19_recheck.json`).
- **measured, live kill mid-recording (`rt`, PyAV 19):** frames fed at 30 fps, TerminateProcess after 75 frames fed, no drain (`verify_method_pyav19_checks.json` → `rt`; intra rows from `verify_method2_intra_kill.json` → `rt`).

  | variant | muxed | readable / 75 fed |
  |---|---|---|
  | MJPEG mkv+fp | 75 | 74 (74 byte-exact) |
  | **NVENC H.264 intra mkv+fp** (in scope) | 73 | **72** (all key frames, seek exact) |
  | **NVENC HEVC intra mkv+fp** (in scope) | 73 | **72** (all key frames, seek exact) |
  | NVENC GOP 30 mkv_cl0+fp (bg) | 73 | 72 |
  | AV1 mkv_cl0+fp, defaults (bg) | 36 | **35** |

- source (mechanism, FFmpeg n9.0.2, https://github.com/FFmpeg/FFmpeg/blob/n9.0.2/libavformat/):
  - `file.c:324-332`: for written regular files, `h->max_packet_size = 262144` ("Buffer writes more than the default 32k to improve throughput") and `h->min_packet_size = h->max_packet_size` ("Disable per-packet flushing by default").
  - `mux.c:425-433` (`flush_if_needed`): calls `avio_flush` only `if (s->flush_packets == 1 || ...)`.
  - `options_table.h:84`: `flush_packets` default `{.i64 = -1}`.
  - `aviobuf.c:466-469`: a FLUSH_POINT flushes only `if (s->buf_ptr - s->buffer >= s->min_packet_size)`.
- source (what the muxers still hold in memory with fp):
  - `matroskaenc.c:3032-3048`: a Cluster is built in `cluster_bc` and written out in `mkv_end_cluster`.
  - `matroskaenc.c:3231-3236`: a new Cluster starts on the size or time limit, or on a video key frame once the cluster is over 4 KiB.
  - `matroskaenc.c:2744-2748`: the defaults are 5000 ms and 5 MiB.
  - `movenc.c:7449-7455`: a fragment is flushed when the *next* packet meets the condition.
- inferred, consistent with this code and the 120 vs 149 results: the open Cluster or fragment is lost. For an inter codec that is up to one GOP. For an all-key payload whose frames are over 4 KiB, every frame already starts a new Cluster, so 1 frame is lost.
  - measured support: `mkv` and `mkv_cl0+fp` give byte-identical files for all-key payloads (§2.12), and the intra NVENC live kills lost exactly 1 of 73 muxed frames (table above).
- **Segment muxer.**
  - measured (P19): seg_mkv and seg_mkv+fp give identical results, 148 frames and 8238820 B each (`verify_method_pyav19_checks.json` → `segment`).
  - source (n9.0.2 `segment.c:161-167`): the inner context gets `oc->flags = s->flags`, but `flush_packets` is not copied.
  - The 2-frame loss is smaller than the 256 KiB buffer would predict. The buffering mechanism is **NOT VERIFIED**.

### 2.2 Reading unfinalized files without repair (PyAV 19 files)

- measured: ffprobe and PyAV 19 read the same frame count in every readable non-segment kill image (`pyav19_recheck.json`).
- measured: unfinalized MKV and AVI report **no duration**. fMP4+fp reports the complete fragments, e.g. 4.966992 s for MJPEG (`pyav19_recheck.json` → `ffprobe_format_duration`).
- **measured, PyAV 19 seek** (`c.seek(target, backward=True)` on the middle frame, then decode one frame; `pyav19_recheck.json` → `pyav.seek`):

  | file type | result |
  |---|---|
  | MJPEG mkv, mkv+fp, mkv_cl0+fp, fmp4_every, fmp4_every+fp, fmp4_kf+fp | **exact** |
  | NVENC H.264 / HEVC intra mkv+fp, live kill | **exact** (target 1200, got 1200; `verify_method2_intra_kill.json`) |
  | MJPEG nut, nut+fp | about **1 frame early** (got 151572, target 153600; 2048 ticks/frame) |
  | MJPEG avi+fp | **pts 0, the start of the file** (target 75) |
  | H.264 / AV1 GOP (bg) | the preceding key frame, as `backward=True` should give |

  - code: the check's `ok` flag only means "a frame at or before the target, no exception" (`scripts/crash_resilience/common_cr.py:236-249`).
  - PyAV reports the pts it actually landed on, so a reader can detect a miss and decode forward.
- measured (OpenCV 4.12.0): `CAP_PROP_FRAME_COUNT` is **-2.767e17** for MJPEG mkv+fp, NVENC and AV1 mkv_cl0+fp, and **0** for AVI+fp. It is correct (149) for fMP4_every+fp (`cv2_on_pyav19_files.json`).
- **measured: OpenCV's frame-index seek silently returns frame 0 on unfinalized MKV and AVI.**
  - After `CAP_PROP_POS_FRAMES = 74`, `set()` and `read()` both return True, and the image is pixel-identical to sequential frame **0**. This held for MJPEG mkv+fp, MJPEG avi+fp and NVENC mkv_cl0+fp.
  - On fMP4+fp and NUT+fp the seek returns frame 74 (`cv2_seek_identity_pyav19_files.json`).
  - measured, bg: every drained MKV, WebM, AVI and raw-MJPEG row that cv2 could open in `kill_matrix_a.json` / `kill_matrix_b.json` has `read.cv2.seek.pos_after == 1.0`. Six drained AV1 rows in `kill_matrix_b.json` did not open in cv2 and have no seek field (per `VERIFY_provenance.md`).
  - **Neither OpenCV nor PyAV can seek in unfinalized AVI.**

### 2.3 Repair, functional (PyAV 19 files)

- **measured (primary): a PyAV 19 remux to `.mkv` with `add_stream_from_template(ist, opaque=True)` kept the frame count in 19/19 repairable kill images** (9 MJPEG, 6 NVENC, 4 AV1; `pyav19_recheck.json` → `pyav_remux_template_opaque`).
  - measured: of the 25 images, 5 are unreadable and have nothing to remux: MJPEG mp4, MJPEG mp4+fp, H.264 mp4+fp, AV1 mp4+fp and the 0-byte AV1 mkv.
  - measured: the seg_mkv+fp segment directory was not remuxed (`pyav_remux_template_opaque` is null).
- **measured: OpenCV reads those PyAV 19 remuxes correctly.** `CAP_PROP_FRAME_COUNT` is right (149/150) and the `POS_FRAMES=74` seek is frame-exact in 5/5 files (`verify_method_cv2_on_pyav_remux.json`).
- measured: `add_stream_from_template(ist)` with **default** arguments fails on **4/4 readable AV1 files** with `UnknownCodecError: libdav1d`. MJPEG and H.264 remux with either setting (`pyav19_recheck.json` → `pyav_remux_template_default`).
- Reference only (ffmpeg 9.0.2 CLI): `ffmpeg -c copy` to `.mkv` kept the count in 19/19 and restored a finite duration (`pyav19_recheck.json` → `ffmpeg_copy_mkv`).
- measured: a plain MP4 kill image has 0 readable frames and gives `InvalidDataError` (`pyav19_recheck.json`). §2.13 confirms this at 1 GB.

### 2.4 Emulated power loss (prefix cuts), PyAV 19 files

**Method.** 12 seeded cuts per variant. "ideal" = the packets in the image's own ffprobe packet table that end before the cut. Measured, `truncation_pyav19.json`.

| variant | ffprobe = ideal | ffprobe = ideal + 1 | torn last sample handed to the decoder | PyAV naive loop < ffprobe |
|---|---|---|---|---|
| MJPEG mkv+fp | 12/12 | 0 | **no, 0/12** | 0 |
| MJPEG fmp4_every+fp | 0 | 12/12 | **yes, 12/12** | 0 |
| MJPEG nut+fp | 2 | 10/12 | **yes, 12/12** (2 raised `InvalidDataError`) | 0 |
| AV1 mkv_cl0+fp (bg) | 12/12 | 0 | no, 0/12 | 0 |
| AV1 fmp4_every+fp (bg) | 12/12 | 0 | yes, inferred (12/12 PyAV `InvalidDataError`) | 12/12, up to 6 frames short |

- measured: the torn-sample column is the JSON field `mjpeg_torn_last_packet_delivered` for the MJPEG rows. That field is null for AV1. The AV1 fMP4 "yes" is inferred from the 12/12 decoder errors.
- measured, bg (PyAV 18, 24 cuts per variant; `summary.md` truncation table from `truncation_a.json` / `truncation_b.json`):
  - Matroska/WebM ratio 0.998–1.000, never a torn frame;
  - plain MP4 ratio 0.000;
  - fMP4, NUT, AVI, raw MJPEG and the JPEG folder count the torn frame.
- inferred: a production reader must catch per-packet errors, drain the decoder, and validate the last JPEG (SOI/EOI). The prototype's MJPEG repair does the SOI/EOI check (code, `scripts/crash_resilience/resumable_recorder.py:215-218`).
- Not tested: prefix cuts of intra NVENC H.264/HEVC files.

### 2.5 Frames held by the encoder, PyAV 19

**Method.** 75 decoded camera frames fed at 30 fps; count the packets returned before the drain.

**In scope: intra NVENC** (the bench settings `gop_size 0`, `p4`, `tune ll`, `constqp`, QP 14 / 11, `bf 0`, `i_qfactor 1`; code, `scripts/crash_resilience/bench_fragment_overhead.py:45-48`). Measured, `verify_method2_intra_hold.json` (2 runs) and `verify_method2_intra_kill.json`; scripts in `scripts/crash_resilience/pyav19_checks/verify_method/step2/`.

| encoder | packets out before drain / 75 | held | key-frame packets | runs |
|---|---|---|---|---|
| h264_nvenc intra | 73 | **2** | 75/75 | 2/2 + the kill run's hold check |
| h264_nvenc intra + `delay=0` | 75 | **0** | 75/75 | 2/2 |
| hevc_nvenc intra | 73 | **2** | 75/75 | 2/2 + the kill run's hold check |
| hevc_nvenc intra + `delay=0` | 75 | **0** | 75/75 | 2/2 |

- measured: **a live kill of intra NVENC H.264 or HEVC into MKV+fp loses 3 of 75 frames at 30 fps: 2 held by the encoder plus 1 in the open Cluster.** 73 muxed, 72 readable by both ffprobe and PyAV, 72/72 key frames, exact seek (`verify_method2_intra_kill.json` → `rt`). One 75-frame kill per codec.
- measured: with `delay=0` the hold-back is 0 (hold count only).
- **Not measured:** a kill with `delay=0`, and the throughput or latency cost of `delay=0`.

**Background: GOP codecs.** Measured, `encoder_hold_check_pyav19.json` and `.log`.

| encoder settings (bg) | packets out / 75 | held |
|---|---|---|
| libsvtav1 preset 10, crf 35, defaults ("random access", CRF) | 36 | **39** |
| libsvtav1 + `svtav1-params=pred-struct=1` ("low delay"; log shows CQP) | 75 | 0 |
| h264_nvenc p4, bf 0, vbr cq 23, GOP 30 | 73 | 2 |
| h264_nvenc, same + `delay=0` | 75 | 0 |

- measured: the default and low-delay SVT runs used different rate-control modes, CRF vs CQP (`encoder_hold_check_pyav19.log` line 18 "CRF / 35.00", line 42 "CQP / 35.00").
- source: FFmpeg n9.0.2 `libavcodec/nvenc_h264.c:100-101`, `"delay"`, "Delay frame output by the given amount of frames", default `INT_MAX`.

### 2.6 `pict_type` side finding, PyAV 19

- measured: frames decoded from camera JPEGs carry `pict_type` I. When they are re-encoded unchanged, libsvtav1 and libx264 produce a key frame on 60/60 frames; with `pict_type = NONE`, on 2/60. h264_nvenc gives 2/60 either way (`pyav19_recheck.json` → `pict_type`).
- inferred: for intra-only encoders every frame is a key frame anyway, so this matters only for GOP encoders (bg). The intra bench sets `NONE` regardless (code, `scripts/crash_resilience/bench_fragment_overhead.py:71`), and its templates are still all key frames (§2.12).

### 2.7 Electron / Chromium playback of damaged PyAV 19 files (functional)

**Method.**
- 19 files, hidden window, played from 0 at rate 4.
- Electron 35.7.5 = Chromium 134.0.6998.205; Electron 45.2.3 = Chromium 156.0.8078.80.
- Measured, `electron_pyav19_e35.json`, `electron_pyav19_e45.json`.
- "ended" = reached `ended` with no MediaError. Presentation during play was not verified.
- The H.264/AV1 files are GOP 30 (bg). Seeking in intra H.264/HEVC is covered by the intra_playback topic.

| file | Electron 35.7.5 | Electron 45.2.3 |
|---|---|---|
| MJPEG mkv+fp kill | MediaError 4 `DEMUXER_ERROR_NO_SUPPORTED_STREAMS` | same |
| AV1 / H.264 mkv+fp, mkv_cl0+fp, AV1 webm_cl0+fp kill | ended, duration Infinity | same |
| the same files cut at 60 % / 95 % | ended | same |
| AV1 / H.264 fmp4_every+fp kill; H.264 fmp4_kf+fp | ended, finite duration | same |
| AV1 fmp4_every+fp cut 60 % / 95 % | MediaError 3 `PIPELINE_ERROR_DECODE` part-way | same |
| H.264 fmp4_every+fp cut 60 % / 95 % | MediaError 4 `DEMUXER_ERROR_BITSTREAM_CONVERSION_FAILED` | **ended** |

- **measured, seek frame identity (Electron 35.7.5, `verify_method_electron_seek_identity_e35.json`):** each unfinalized image was compared with its finalized PyAV 19 remux by canvas readback.
  - AV1 mkv_cl0+fp: 8/8 frame-exact.
  - H.264 mkv_cl0+fp and fmp4_every+fp: 16/16 frame-exact when read 250 ms after `seeked`.
  - H.264 read at `seeked`: 9/16 exact; 7/16 returned the previously shown frame (3 MKV, 4 fMP4). Not a container effect.
- measured, bg: in the 218-file PyAV 18 run, NUT, AVI, IVF and killed plain MP4 failed with MediaError 4 `DEMUXER_ERROR_COULD_NOT_OPEN` in both versions (`electron_e35.json` / `electron_e45.json`).
- measured: in every ended file, `decoded_during_play` = expected − 4. **The cause is NOT VERIFIED.**
- Not tested: Electron playback of killed intra NVENC files.

### 2.8 Resumable recorder prototype on PyAV 19 (functional)

**What it is** (code, `scripts/crash_resilience/resumable_recorder.py:10-23`, `:99-105`):
- a `manifest.jsonl` journal, fsynced per record (`_journal`, `sync=True`);
- per-segment MKV with `flush_packets=1`;
- a 32-byte `timestamps.bin` record with a CRC, flushed per frame.

Child writers ran under PyAV 19.0.2, 2 s segments, killed with TerminateProcess. Measured, `resumable_demo_pyav19.json`.

| scenario | lost frames | video frames == ts records | MJPEG byte-exact | joined MKV |
|---|---|---|---|---|
| kill mid-segment (MJPEG) | 1 [169] | 259 == 259 | 259/259 | 259 |
| double crash | 2 [99, 174] | 233 == 233 | 233/233 | 233 |
| power loss, seed 0 (segment, sidecar and journal torn) | 7 [149–155] | 209 == 209 | 209/209 | 209 |
| power loss, seed 1 | 36 [130–165] | 190 == 190 | 190/190 | 190 |
| FFV1 kill mid-segment | 1 [169] | 259 == 259 | n/a | 259 |

- measured: in every scenario, frame numbers are unique and increasing, every gap is listed as lost, and pts equals the capture clock (same file).
- measured, bg (`resumable_demo.md`): 9 PyAV 18 scenarios passed, including 5 power-loss seeds and a kill at a segment rollover.

### 2.9 Timestamp sidecar (independent of PyAV)

- measured, process kill after 1 / 37 / 500 rows (`sidecar_durability.md`):

  | writer | rows intact |
  |---|---|
  | CSV + `flush()` per row | 1 / 37 / 500 |
  | binary 72-byte record + CRC + flush | 1 / 37 / 500 |
  | CSV, default buffering | 0 / 0 / 456 |
  | binary, default buffering | 0 / 0 / 452 |

- measured, 24 cuts × 2 tails (`sidecar_durability.json`):
  - the strict CSV parser and the CRC binary parser recovered exactly the complete rows in 48/48;
  - pandas `read_csv` returned an extra row in 23/24 cuts, and **6/24 looked complete but had wrong integer values**.
- code: sfn26 `skellycam-rust/src/timestamps/csv_writer.rs:72` flushes each row. No `sync_all` or `sync_data` appears in that file (`git show upstream/sfn26`, 765bf82d).

### 2.10 sfn26 Rust recorder and today's skellycam

- code (sfn26 765bf82d, `skellycam-rust/src/recording/recorder.rs`):
  - `:40-45`: defaults `image2pipe`, `mjpeg`, `libx264`, `ultrafast`, crf 18;
  - `:141-156`: ffmpeg spawned with no movflags;
  - `:266-275`: `Drop` calls `self.ffmpeg_child.kill()`;
  - `camera_group/dispatcher.rs:373` names the output `.mp4`.
- measured (ffmpeg 9.0.2 CLI as a stand-in for the child process, reference only; `sfn26_pipe.md`): 300 of 600 frames fed, then killed.

  | output | kill ffmpeg (= `Drop`) | kill the tree | kill only the feeder |
  |---|---|---|---|
  | plain MP4 | **0** | **0** | 300/300 |
  | MKV x264 | 246 | 246 | 300/300 |
  | MKV MJPEG copy | 293 | 293 | 300/300 |

- measured: with 75 frames fed, killing ffmpeg or the tree left **no output file** (`sfn26_pipe_n150.md`).
  - inferred: ffmpeg was still probing its input.
  - The bound (probesize vs analyzeduration, `options_table.h:39`, `:56`) is **NOT VERIFIED**.
- background (today's skellycam): a hard kill leaves an MSMF `.mp4` with 0 readable frames, and no timestamps CSV is written unless the stop is clean (`research/skellycam_recording/REPORT.md:27`, `:210-213`, `:226`).

### 2.11 Cost of durability policies (timed: CR-FSYNC-PYAV19)

**Method** (code, `scripts/crash_resilience/bench_fsync.py`):
- Each frame appends one camera JPEG (c930e_720p_flash looped to 3000; 166,023,810 B, i.e. 55,341 B/frame, computed) to a data file, plus a 72-byte record to a sidecar (`:41`, `:86-102`).
- Policies (`:94-101`):
  - `none` = Python buffered writes;
  - `flush` = `flush()` of both files every frame;
  - `fsync_every_K` = flush every frame plus `os.fsync` of **both** files every K frames;
  - `sidecar_fsync_1` = flush data, fsync only the sidecar every frame.
- Latency = `perf_counter_ns` around one frame's write and durability step (`:67`, `:80`, `:90`, `:102`). These latencies are not affected by the 15.625 ms process-time tick.
- 3 repeats, back-to-back in one process, variants in a fixed order. Values are the median (min–max) over repeats; this is within-run noise, not run-to-run variation (§5).
- Drive: one WD_BLACK SN850X NVMe (study record, `research/skellycam_recording/recording_upgrade/results/write_throughput/BENCH.md:4`). **The fsync costs do not transfer to other drives** (SATA SSD, HDD) (inferred).
- File: `bench/fsync_pyav19.json`. Every value was recomputed from the `repeats[]` arrays.

| policy | MB/s | latency p50 µs | p99 µs | max µs | CPU µs/frame (computed; quantized) |
|---|---|---|---|---|---|
| none | 2612 (2587–2680) | 14.4 (14.0–14.9) | 80.3 (77.7–81.5) | 284 (221–324) | 20.8 (20.8–20.8) |
| flush | 2484 (2359–2485) | 16.3 (16.2–17.1) | 81.7 (78.6–85.4) | 251 (241–291) | 26.0 (20.8–26.0) |
| fsync_every_1 | 127 (125–128) | 409.3 (406.8–411.0) | 669.0 (649.7–699.4) | 8736 (8658–8772) | 72.9 (62.5–78.1) |
| fsync_every_10 | 687 (664–694) | 17.5 (17.2–17.9) | 720.6 (698.1–739.9) | 3054 (2098–9318) | 36.5 (15.6–36.5) |
| fsync_every_30 | 1066 (1040–1076) | 16.1 (16.0–16.2) | 883.4 (863.7–890.7) | 4173 (3596–9065) | 26.0 (15.6–41.7) |
| fsync_every_300 | 1454 (1435–1505) | 15.7 (15.6–15.8) | 75.5 (75.4–79.7) | 12361 (6706–12566) | 31.2 (26.0–36.5) |
| sidecar_fsync_1 | 238 (197–243) | 214.5 (208.1–222.4) | 374.4 (365.9–2672.9) | 2916 (604–58903) | 46.9 (41.7–62.5) |
| mkv_fp_fsync_1 (**confounded**) | 121 (118–121) | 439.4 (433.6–446.8) | 699.5 (673.5–706.5) | 8680 (8648–8692) | 119.8 (109.4–130.2) |
| mkv_fp_fsync_30 (**confounded**) | 857 (811–879) | 25.8 (25.7–26.4) | 942.2 (874.2–960.0) | 1306 (1230–9372) | 52.1 (36.5–62.5) |

- measured: **a flush per frame costs +1.9 µs p50 over no flush** (16.3 vs 14.4 µs), and throughput stays at 2484 MB/s.
  - measured: a flush per row survives a process kill (§2.9).
- measured: **an fsync of both files every frame costs p50 409.3 µs, p99 669.0 µs and max 8.7 ms**, and throughput drops to 127 MB/s.
- measured: **fsync every 30 frames keeps p50 at 16.1 µs**, but the fsync frames reach p99 (883.4 µs). The worst frame is 4.2 ms as the median of 3 repeats (3.6–9.1 ms over repeats).
- computed: fsync frames are 1/K of all frames, i.e. 3.3 % at K=30 and 0.33 % at K=300. That is why the fsync stall shows in p99 at K ≤ 30 but not at K=300 (75.5 µs).
- measured: **K=300 has the largest median worst frame, 12.4 ms (6.7–12.6).** computed: each of those fsyncs covers about 16.6 MB (300 × 55,341 B).
- measured: the largest single frame in any repeat was **58.9 ms**, in one `sidecar_fsync_1` repeat. `fsync_every_10` and `mkv_fp_fsync_30` each had one repeat with a 9.3 / 9.4 ms worst frame.
- measured: **a sidecar-only fsync every frame costs p50 214.5 µs.** One repeat had the 58.9 ms worst frame and a 2.67 ms p99.
  - inferred: one fsync costs about 200 µs on this drive (214.5 µs for 1 fsync per frame vs 409.3 µs for 2).
- source: Python `os.fsync`: "on Windows, the MS `_commit()` function" (https://docs.python.org/3.12/library/os.html, accessed 2026-11-10).
- source: Microsoft `_commit`: "forces the operating system to write the file associated with *fd* to disk" (https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/commit, accessed 2026-11-10).
- source: Microsoft FlushFileBuffers: "can be inefficient when used after every write to a disk drive device when many writes are being performed separately... the application should use unbuffered I/O instead" (https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-flushfilebuffers, accessed 2026-11-10).
  - That `_commit` calls FlushFileBuffers is only a code comment (`bench_fsync.py:14`); the `_commit` page does not name it.
- **Confounder (kept):** `mkv_fp_fsync_K` writes Matroska through a **Python file object** (`av.open(f, "w", format="matroska", options={"flush_packets": "1"})`, then `f.flush()` + `os.fsync` every K; code, `bench_fsync.py:60-62`, `:76-79`). It uses `add_stream("mjpeg")` with a 1/1000 packet time base (`:63-71`).
  - The recorder prototypes and every kill test use the path-based `av.open(path, …)`, so these two rows do not transfer to that writer.
  - The kill and torn-frame behaviour of the file-object writer was not tested.
- code: the python_integration RecordingWriter's "fsync every 30" fsyncs only the `.frames.bin` sidecar, not the video file (`scripts/python_integration/recwriter.py:154-155`). So it does not cover a video fsync either.
- computed: one 720p MJPEG camera at 30 fps writes about 1.66 MB/s (55,341 × 30). inferred: every policy, including K=1 at 127 MB/s, has the throughput for one camera. Multi-camera fsync contention was not measured.

### 2.12 Cost of container settings (timed: CR-FRAG-MJPEG-PYAV19, CR-FRAG-INTRA-PYAV19)

**Method** (code, `scripts/crash_resilience/bench_fragment_overhead.py`):
- Packets are prepared in memory. The timer covers muxing and file writing (`:9-10`, `:117-164`). **For the intra rows the timer also covers opening and probing the template file** (`av.open(template)` + `add_stream_from_template`, `:147-148`, inside the window that starts at `:124`); that cost was not measured separately. MJPEG rows use `add_stream("mjpeg")` instead (`:143`).
- 3000 packets, 3 repeats, back-to-back, variants in a fixed order (`:181-190`). Values are the median (min–max) wall time per frame, computed as `wall_s` × 1e6 / 3000.
- Overhead = (file bytes − payload bytes) / frames (`:160-164`). It was constant across repeats.
- MJPEG = the camera's own JPEGs with CFR pts at 1/1000 (`:56-57`); 55,341 B/frame.
- **Intra payloads** = NVENC H.264 (QP 14) and HEVC (QP 11), `gop 0`, `tune ll`, `bf 0`, `i_qfactor 1`, fed **yuv420p** (`:45-48`, `:70`).
  - The QPs are the target A QPs from `research/skellycam_recording/recording_upgrade/results/intra_compare/matched_settings.json` → `h264_nvenc_420` / `hevc_nvenc_420` → `mjpeg_720p`. Those were calibrated on another corpus (66,594.1 B/frame MJPEG, `_meta.camera_passthrough_bytes_per_frame.mjpeg_720p`) and fed nv12 with limited-range input (`_meta.apply`). This corpus is 55,341 B/frame.
  - **This payload's quality was not measured, so these are not target A results.** inferred: container overhead bytes do not depend on payload quality; only payload size does.
  - Only 300 frames were encoded, once and untimed (`:63-77`). The packets were looped to 3000 with rising pts (`:85-88`) and re-muxed via `add_stream_from_template(…, opaque=True)` (`:147-148`).
  - computed: 38,239 B/frame (H.264) and 44,953 B/frame (HEVC), smaller than matched_settings' `mjpeg_720p` sample (46,317.1 / 55,247.4 B).
  - **measured: both templates are all-intra.** ffprobe (inspect only, 2026-11-10) found 300/300 key-flagged packets in `template_h264nv_intra.mkv` and `template_hevcnv_intra.mkv` (`verify_method2_template_keyframes.txt`). The script passes the key flag through to every muxed packet (code, `:84`, `:154`).
- Files: `bench/fragment_overhead_mjpeg_pyav19.json` (19 variants), `bench/fragment_overhead_intra_pyav19.json` (16 variants × 2 payloads). All rows have 3 repeats and `error: null`. Every value was recomputed from `repeats[]`.
- **Wall columns are comparable within a payload only.** Across payloads the stream setup differs (template open inside the timer for intra), the MJPEG item ran at 00:52 and the intra item at 04:35, and H.264 always ran before HEVC (`:181`). The fp deltas within each payload stand.

| variant | MJPEG wall µs/frame | MJPEG B/frame | H.264 intra wall | H.264 B/frame | HEVC intra wall | HEVC B/frame |
|---|---|---|---|---|---|---|
| mkv | 20.0 (19.5–20.5) | 45.75 | 19.7 (19.2–19.9) | 45.73 | 14.9 (14.8–15.1) | 45.78 |
| mkv+fp | 24.9 (24.8–25.0) | 45.75 | 22.4 (22.3–22.9) | 45.73 | 17.9 (17.8–17.9) | 45.78 |
| mkv_cl0+fp | 25.3 (24.9–25.5) | 45.75 | 22.3 (22.0–22.6) | 45.73 | 18.4 (17.9–18.6) | 45.78 |
| fmp4_kf | 20.0 (19.7–20.1) | 131.27 | 19.6 (19.5–20.7) | 131.28 | 15.8 (15.5–15.8) | 131.30 |
| fmp4_kf+fp | 25.1 (24.8–25.3) | 131.27 | 21.3 (21.3–21.6) | 131.28 | 17.6 (17.1–18.5) | 131.30 |
| fmp4_every | 20.4 (19.7–20.5) | 131.27 | 19.7 (19.6–20.0) | 131.28 | 15.8 (15.5–16.1) | 131.30 |
| fmp4_every+fp | 23.5 (23.4–23.7) | 131.27 | 21.5 (21.2–21.8) | 131.28 | 17.0 (17.0–18.5) | 131.30 |
| mp4 (plain) | 17.6 (17.3–17.9) | 10.17 | 18.1 (18.0–19.0) | 9.84 | 14.0 (13.9–14.2) | 9.90 |
| nut+fp | 22.0 (22.0–22.3) | 28.67 | 20.5 (20.2–21.2) | 28.76 | 16.7 (16.0–16.8) | 28.78 |
| avi+fp | 20.4 (20.2–20.6) | 26.40 | skipped (`:186-187`) | - | skipped | - |
| fmp4_frag_100+fp | 19.2 (19.0–19.4) | 50.60 | 19.6 (19.3–19.7) | 50.61 | 14.9 (14.6–15.2) | 50.64 |
| fmp4_frag_500+fp | 19.8 (19.3–20.5) | 16.73 | 19.8 (19.5–20.1) | 16.74 | 15.4 (15.0–15.6) | 16.77 |
| fmp4_frag_1000+fp | 19.7 (19.7–20.2) | 12.50 | 20.4 (20.2–20.6) | 12.51 | 15.8 (15.3–15.9) | 12.54 |
| fmp4_frag_2000+fp | 19.9 (19.7–19.9) | 10.38 | 20.3 (20.3–21.3) | 10.39 | 15.9 (15.6–16.5) | 10.42 |
| seg_mkv_1+fp | 32.0 (31.7–33.5) | 61.42 | 30.6 (30.5–30.9) | 63.82 | 26.8 (26.1–26.8) | 66.42 |
| seg_mkv_10+fp | 21.6 (21.6–22.0) | 46.36 | 22.1 (21.9–22.5) | 46.60 | 17.2 (17.2–17.7) | 46.86 |
| seg_mkv_60+fp | 23.1 (20.5–23.3) | 45.82 | 21.1 (20.9–21.5) | 45.77 | 16.8 (16.7–17.4) | 45.87 |
| rawidx (raw .mjpeg + CRC index, 2 flushes/frame) | 34.9 (34.8–38.3) | 32.0 | skipped (`:184-185`) | - | skipped | - |
| folder (1 file/frame) | 207.3 (206.6–219.9) | 0.0 | skipped | - | skipped | - |

- measured, computed from medians: **`flush_packets=1` on MKV adds 4.9 µs/frame (MJPEG), 2.7 (H.264 intra) and 3.0 (HEVC intra) of wall time.** The min–max ranges with and without fp do not overlap for any payload.
- measured, computed: on fMP4 per-frame, fp adds 3.1 / 1.8 / 1.2 µs/frame.
- measured: **fMP4 per-frame + fp muxes slightly faster than MKV+fp for every payload** (medians 23.5 vs 24.9 MJPEG, 21.5 vs 22.4 H.264, 17.0 vs 17.9 HEVC). The ranges do not overlap for MJPEG and H.264; they overlap for HEVC (17.0–18.5 vs 17.8–17.9).
- measured: **`cluster_size_limit=0` + `cluster_time_limit=0` adds no bytes.** `mkv`, `mkv+fp` and `mkv_cl0+fp` files are byte-identical for each payload (166,161,060 / 114,854,087 / 134,997,090 B), and the wall time is within the fp range.
  - inferred, with `matroskaenc.c:3231-3236`: for all-key payloads over 4 KiB/frame, every frame already opens a new Cluster, so cl0 is redundant for intra-only recording.
- measured: **for MKV, fMP4, NUT and plain MP4, container bytes per frame barely depend on the payload codec.**
  - MKV is 45.7–45.8 B/frame, fMP4 per-frame 131.3, fMP4 1 s fragments 12.5, NUT 28.7–28.8, plain MP4 9.8–10.2.
  - measured: segment-muxer overhead does depend on the codec: seg_mkv_1+fp is 61.42 / 63.82 / 66.42 B/frame for MJPEG / H.264 / HEVC. inferred cause: codec private data in each segment header.
  - computed: fMP4 per-frame is 0.24 % of payload (MJPEG) and 0.34 % (H.264 intra); MKV is 0.08 % (MJPEG). At 30 fps that is about 4.9 MB/h for MKV and 14.2 MB/h for fMP4 per-frame (× 108,000 frames).
- measured: `fmp4_kf` and `fmp4_every` give identical bytes for all three payloads, consistent with the measured all-key templates.
- measured: **1 s segments of the segment muxer cost the most of the container options**: 26.8–32.0 µs/frame and 61.4–66.4 B/frame.
- measured: **one file per frame costs the writer 207.3 µs/frame**, 8.3× MKV+fp (computed). The raw + CRC index costs 34.9 µs/frame. Both are MJPEG only.
  - The 207.3 µs is the writer process's wall time only. It **excludes Defender's CPU** (MsMpEng is another process). computed upper bound: item 19's MsMpEng 5.38 CPU-s over 9000 file creates is about 598 µs/file; attributing all of it to the folder variant is inferred (item 19 also ran 18 other variants).
- The CPU columns are not used: every `cpu_s` is a multiple of 15.625 ms, i.e. steps of 5.21 µs/frame at 3000 frames (measured, `bench/*.json`; the cause, the Windows process-time tick, is inferred).
- No ranking of wall time across payloads is drawn (see the comparability note above).

### 2.13 Repair cost at 1 GB (timed: CR-REPAIR-PYAV19)

**Method** (code, `scripts/crash_resilience/bench_repair.py`):
- Four recordings of about 0.975 GB each, MJPEG passthrough, 17,618 frames requested (`frames`).
- Each was written by `writer_child.py` in `drained:N` mode under the **PyAV 19 uv interpreter** (`:46`; JSON `writer_child_interpreter`) and killed before `close()` (`:43-53`). The input was therefore a quiescent kill: no frame was mid-write.
  - This fixes the earlier `cc.VENV_PY` (PyAV 18) problem.
- `pyav_copy_mkv` = `common_cr.remux_pyav` with `opaque=True` (`scripts/crash_resilience/common_cr.py:293-315`).
- `resumable_repair` = `ResumableRecorder._repair_segment`, which adds the SOI/EOI check (`resumable_recorder.py:198-232`), run on a copy made before the timer (`bench_repair.py:93-103`).
- Frames were counted by ffprobe after the timer. Neither repair path fsyncs its output (code: no fsync in `common_cr.py:293-315` or `resumable_recorder.py:198-232`).
- No cache drop. `free_ram_mb_start` was 49,399.
- File: `bench/repair_pyav19.json`. Median (min–max) of 3 repeats, recomputed from the rows.

| killed recording | input GB | method | seconds | s/GB | frames out / written |
|---|---|---|---|---|---|
| mkv+fp | 0.9755 | pyav_copy_mkv | 0.884 (0.859–0.893) | **0.907 (0.881–0.916)** | 17,617 / 17,618 (3/3) |
| mkv+fp | 0.9755 | resumable_repair | 0.941 (0.934–0.942) | **0.965 (0.957–0.965)** | 17,617 / 17,618 (3/3) |
| fmp4_every+fp | 0.9770 | pyav_copy_mkv | 1.314 (1.306–1.330) | **1.345 (1.337–1.361)** | 17,617 / 17,618 (3/3) |
| mp4 (plain) | 0.9749 | pyav_copy_mkv | failed open | n/a | **0 / 17,618**, `InvalidDataError`, 0 packets |
| rawidx (.mjpeg read with PyAV `format='mjpeg'`) | 0.9751 | pyav_copy_mkv | 1.405 (1.395–1.412) | **1.441 (1.431–1.448)** | 17,618 / 17,618 (3/3) |

- code: the rawidx repair demuxes with PyAV `av.open(format='mjpeg')` (`bench_repair.py:84`, `common_cr.py:299`) and does not use the CRC index.
- measured: **a PyAV remux of a killed 1 GB MKV+fp recording takes 0.907 s/GB**, about 1.10 GB/s (computed). The resumable segment repair takes 0.965 s/GB.
- measured: fMP4 per-frame takes 1.345 s/GB (+48 % vs MKV, computed). The raw .mjpeg takes 1.441 s/GB.
- measured: **MKV+fp and fMP4 every+fp give back 17,617 of 17,618 frames; raw .mjpeg gives back all frames of this quiescent kill; plain MP4 gives back none.** This agrees with the 150-frame kill results in §2.1 (1 frame lost for mkv+fp and fmp4_every+fp; 0 bg for raw).
  - inferred, with bg §2.4: after a mid-write kill or cut, the plain MJPEG demux hands out the torn frame unless the CRC index is used.
- `input_frames_written` is the requested N, not a measured count (code, `bench_repair.py:118`).
- computed: the per-method spread is at most 3.9 % (mkv+fp pyav_copy 0.893 / 0.859). The first repeat was the slowest only for the two mkv+fp methods. inferred: all repeats read from page cache, since the recording had just been written and 49 GB of RAM was free.
- inferred: these in-cache figures cover a process crash without a reboot. After a power loss, repair runs after a reboot, so the cache is cold by definition; **cold-cache repair was not measured.**

## 3. Comparison tables

**A. Recording container after a crash, and its cost.**
- Legend: P19 = PyAV 19 measured; bg = PyAV 18 or GOP codec background.
- Costs are from the quiet run (§2.12, §2.13), single writer, P-cores only. The wall column is comparable down a payload, not across payloads (§2.12).

| container | kill loss, MJPEG (§2.1) | torn sample handed out (§2.1, §2.4) | OpenCV unfinalized count / seek (§2.2) | PyAV seek, unfinalized MJPEG (§2.2) | Chromium (§2.7) | wall µs/frame MJPEG / H.264 / HEVC intra (§2.12) | overhead B/frame (§2.12) | repair s/GB (§2.13) |
|---|---|---|---|---|---|---|---|---|
| MKV + fp | 1 frame (drained and live `rt`, P19); intra NVENC live kill: 3 frames = 2 encoder + 1 Cluster (P19) | no (P19, bg) | -2.767e17 / **silently frame 0** | exact (also intra NVENC) | MJPEG: never plays; GOP H.264/AV1: `ended`, cl0 seek frame-exact (bg) | 24.9 / 22.4 / 17.9 | 45.7–45.8 | **0.907** (remux), 0.965 (prototype) |
| MKV + fp + cl0 | same as MKV+fp for MJPEG; byte-identical file for all-key payloads | no | same | exact | same | 25.3 / 22.3 / 18.4 | 45.7–45.8 | not run separately |
| fMP4 frag_every + fp | 1 frame (P19) | **yes** after a cut; also after a kill without fp | correct / correct | exact | ended; torn sample gives MediaError (AV1 both, H.264 E35; bg) | 23.5 / 21.5 / 17.0 | 131.3 | 1.345 |
| fMP4 1 s fragments + fp | bg only (1 s lost) | yes (bg) | not tested (P19) | not tested | not tested | 19.7 / 20.4 / 15.8 | 12.5 | not run |
| plain MP4 | **all** (P19) | n/a | not readable | not readable | no (bg) | 17.6 / 18.1 / 14.0 | 9.8–10.2 | **unrepairable, 0 frames** |
| NUT + fp | 0 (P19) | **yes** | off by 1 / correct | about 1 frame early | cannot open (bg) | 22.0 / 20.5 / 16.7 | 28.7–28.8 | not run |
| AVI + fp | 0 (P19) | yes (bg) | 0 / **silently frame 0** | **frame 0** | cannot open (bg) | 20.4 / skipped / skipped | 26.4 | not run |
| segment muxer, 1 s (mkv) | 2 frames with or without fp (P19); mechanism NOT VERIFIED | no (bg) | not tested | not tested | not tested | 32.0 / 30.6 / 26.8 | 61.4–66.4 (codec-dependent) | not run |
| raw .mjpeg + CRC index, flush | 0 (bg) | own parser no; ffprobe yes (bg) | -1.92e14 / frame 0 (bg) | n/a | no | 34.9 (MJPEG only) | 32.0 (index) | 1.441 (all frames, quiescent kill) |
| folder of JPEGs | 0 (bg) | yes (bg) | n/a | n/a | no | 207.3 writer only, excludes Defender (MJPEG only) | 0 | n/a |

**B. Where frames are lost, what bounds the loss, and what the fix costs.**

| loss source | size without mitigation | mitigation | measured cost of mitigation | evidence |
|---|---|---|---|---|
| FFmpeg file-protocol buffer | up to 262144 B (4–5 MJPEG frames; a whole 5 s AV1 file, bg) | `flush_packets=1` | +2.7 to +4.9 µs/frame wall on MKV; 0 bytes | §2.1; §2.12 |
| open MKV Cluster | 1 frame (all-key, incl. intra NVENC P19); up to 1 GOP (inter, bg) | cl0 (redundant for all-key payloads) | 0 bytes; within noise | §2.1; §2.5; §2.12 |
| open fMP4 fragment | 1 frame (every), 1 GOP (kf; = every for all-key), 1 s (1 s fragments, bg) | `frag_every_frame` | +85.5 B/frame vs MKV; repair +48 % | §2.1; §2.12; §2.13 |
| plain MP4 `moov` never written | everything | don't record to plain MP4 | n/a | §2.1, §2.10, §2.13 |
| encoder hold-back | **intra NVENC H.264/HEVC: 2 frames (P19)**; GOP NVENC 2, SVT-AV1 39 (bg) | NVENC `delay=0`: hold-back 0 (P19, hold count only) | not measured; a kill with `delay=0` not measured | §2.5 |
| ffmpeg-CLI child still probing (sfn26 pattern) | the whole file at 75 frames | avoid the CLI child | n/a | §2.10 |
| unflushed sidecar | 6380 B (CSV) / 3456 B (binary) at the 500-row kill | flush per row; CRC binary record | flush: +1.9 µs p50 (data + sidecar) | §2.9; §2.11 |
| OS cache at power loss (real NTFS not tested) | unbounded by these tests | fsync every K | K=1: p50 409 µs, max 8.7 ms; K=30: p50 16.1 µs, p99 883 µs, max 4.2 ms median (3.6–9.1); K=300: median max 12.4 ms; sidecar-only K=1: p50 214.5 µs. One SN850X NVMe. | §2.11 (raw files, not a container) |

## 4. Implications for the plan

1. **Recording container for G1 (MJPEG passthrough): Matroska with `flush_packets=1`.**
   - It loses 1 frame on a kill and keeps every frame byte-exact (§2.1).
   - It never hands out a torn frame after a cut (§2.4).
   - PyAV reads it without repair and seeks exactly (§2.2).
   - It repairs fastest, 0.907 s/GB, getting back every readable frame (§2.13).
   - Its overhead is 45.8 B/frame (§2.12). NUT (28.7), AVI (26.4) and raw + index (32.0) are lower, but they are rejected for torn frames, bad seeks and no Chromium support (§3A). All options are ≤ 0.24 % of the payload for MJPEG (computed), so overhead does not decide the choice.
   - NUT and AVI save one more frame on a kill, but they hand out torn frames, seek inexactly or to frame 0, and Chromium can't open them (§3A).
2. **Set `flush_packets=1` on every libavformat writer.** It costs 2.7–4.9 µs/frame of wall time and no bytes (§2.12). Without it, up to 256 KiB is lost, and fMP4/NUT hand out a torn frame (§2.1).
3. **For intra-only H.264/HEVC (G6/G7 hardware path), use MKV+fp with no cluster options.** `cl0` gives byte-identical files for all-key payloads (§2.12).
   - measured: a live kill of intra NVENC H.264/HEVC into MKV+fp loses **3 frames at 30 fps: 2 held by the encoder plus 1 in the open Cluster** (P19, one 75-frame kill per codec; §2.5). The surviving 72 frames are all key frames and seek exactly.
   - measured: `delay=0` removes the 2-frame hold-back (hold count only). A kill with `delay=0`, and the cost of `delay=0`, are not measured (§6).
4. **Never record to plain MP4.** A killed 1 GB plain MP4 gives 0 frames and can't be remuxed (§2.13). This applies to today's MSMF path and to sfn26 (§2.10).
5. **Use application-level segments, not the `segment` muxer.** The muxer ignored `flush_packets` (§2.1), and at 1 s it is the most expensive option (§2.12).
6. **Segment length is not limited by repair time for a process crash.**
   - Measured: 0.907–0.965 s/GB from cache (§2.13).
   - computed: a 60 s, 720p30 MJPEG segment is about 100 MB (1.66 MB/s × 60), which is about 0.1 s of in-cache repair.
   - inferred: choose the segment length by power-loss exposure and file count, not by repair cost. **For power loss, repair runs with a cold cache after a reboot, and that is not measured** (§2.13).
7. **Finalize before any OpenCV reader, and check PyAV seeks on unfinalized files.**
   - Finalize with a PyAV 19 remux to `.mkv` with `opaque=True` (§2.3, §2.13).
   - PyAV readers must catch per-packet errors, drain the decoder, check the pts they land on, and decode forward (§2.2, §2.4).
8. **PyAV-based repair must pass `opaque=True`**, or AV1 templates fail (4/4, bg; §2.3). Both repair paths already do (code, `common_cr.py:301`, `resumable_recorder.py:210`).
9. **Timestamp sidecar: a fixed-size binary record with a CRC, flushed per frame.**
   - The flush is almost free (+1.9 µs p50, §2.11) and survives a process kill (§2.9).
   - Don't use a CSV parsed by pandas: it returned wrong integers (§2.9).
10. **fsync policy (power loss): a trade-off, not a fixed rule. Never on the capture thread.** Measured on one SN850X NVMe, one writer (§2.11):
    - K=1 (both files): p50 409.3 µs, p99 669.0 µs, max 8.7 ms, 127 MB/s, which is ample for one camera at 1.66 MB/s (computed). Smallest loss window (inferred).
    - K=30: p50 16.1 µs, p99 883.4 µs, max 4.2 ms median (3.6–9.1 ms over repeats).
    - K=300: p99 75.5 µs, but the largest median worst frame, 12.4 ms (6.7–12.6), and the widest loss window (inferred).
    - Sidecar-only fsync was benched only at K=1 (p50 214.5 µs).
    - inferred: stalls of up to tens of ms (58.9 ms in one repeat) must sit on the writer thread, not the capture path.
    - **The power-loss benefit of any K is NOT VERIFIED** (no real NTFS power loss, §6). Multi-camera fsync cost is not measured. The fsync costs do not transfer to other drives (inferred).
    - In the current design only the sidecar and the journal can be fsynced. The video file of the path-based PyAV writer cannot.
      - The benched MKV fsync went through a Python file object, a different writer (§2.11).
      - A second-handle FlushFileBuffers is NOT VERIFIED. The source says it flushes "all the buffered information for a specified file", but does not say what happens to data written through another handle.
11. **Prefer MKV over per-frame fMP4 for crash safety.** The reasons are that fMP4 hands out torn samples (§2.4), opens slowly when long (below) and takes 48 % more repair time (§2.13).
    - Not the reason: mux cost or bytes. fMP4 per-frame + fp muxes slightly faster than MKV+fp (e.g. MJPEG 23.5 vs 24.9 µs/frame, §2.12), and its 131.3 B/frame is only 0.24 % of the MJPEG payload (vs 0.08 % for MKV, computed).
    - measured, cross-topic (`research/skellycam_recording/recording_upgrade/results/jpeg_passthrough/bench/open_long.json`): for finalized 54,000-frame files, cv2 open takes 1107.28 ms for `fmp4_perframe_tb_us`, 42.57 ms for `fmp4_1s_tb_us` and 0.19 ms for `mkv`, as medians of 5 back-to-back opens of just-written files (warm, inferred page cache). The first opens were 1111.88 / 55.1 / 4.93 ms. Cold opens were not measured. The same file shows cv2 counting the MKV as 53,819 of 54,000 frames.
12. **Don't record to a folder of JPEGs.** The writer alone costs 207.3 µs/frame vs 24.9 µs for MKV+fp (§2.12), before Defender's CPU (up to about 598 µs/file, computed upper bound, attribution inferred). It can hand out a torn file (bg, §2.4). The write_throughput topic covers the Defender cost of this layout.
13. **"Resumable" as defined in the prototype works on PyAV 19** (journal + per-segment MKV+fp + CRC sidecar, §2.8).
14. **From sfn26, reuse the per-row flush idea, not the ffmpeg-child plain MP4** (§2.10).
15. **Encoder hold-back (bg, GOP only):** if a GOP codec is ever recorded, low-delay settings remove the hold-back (§2.5). Their cost was not benched, because the bench was dropped as out of scope (§6).

## 5. Run flags and caveats that apply to this topic

- **P-cores only.** All four items ran with affinity `pcores` (16 logical CPUs; measured, `research/skellycam_recording/recording_upgrade/results/BENCH_RUN_2300_LOG.jsonl`, lines for orders 18, 19, 28, 61). There was one writer at a time and no multi-camera contention.
  - The libx265 affinity widening (items 1–3) does not apply: no CR item uses libx265. The CR JSONs do not record process affinity.
- **Quiet machine.** No CR item was load-flagged. Background CPU averaged 3.59–5.40 % before the items, and there were no Defender scan events (measured, same log). The "leftover processes" flag lists only the monitoring session's shells (`research/skellycam_recording/recording_upgrade/results/BENCH_RUN_2300_SUMMARY.md` §2).
- **Defender real-time was ON (not changed).** MsMpEng used 1.05 (item 18, fsync), 5.38 (item 19, fragment MJPEG), 10.25 (item 28, repair) and 1.36 (item 61, fragment intra) CPU-s during the items (measured, same log, `msmpeng_cpu_s_during_item`).
  - Item 28 was the highest. inferred: it writes about 1 GB files many times over (code, `bench_repair.py:81-116`).
  - Item 19 was second. inferred: its `folder` variant creates 9000 files.
  - Defender cost per variant was not recorded, and MsMpEng CPU is outside every `wall_s` / `cpu_s` in this topic. It is part of the real cost on a default install.
- **CPU timer granularity 15.625 ms.** CPU-time figures move in 5.21 µs/frame steps at 3000 frames, so the fragment comparisons use wall time. Latencies use `perf_counter_ns` and are not affected.
- **Repeats are within one run.** The 3 repeats ran back-to-back in one process, with variants in a fixed order, not interleaved (`bench_fragment_overhead.py:181-190`; `bench_fsync.py` likewise). The min–max is within-run noise, not run-to-run variation (summary flag 12 applies).
- **No prior timing numbers in this topic.** The smoke files are PyAV 18.0.0 (measured, their `env`). `bench/fsync_smoke.json` and `bench/fragment_overhead_smoke*.json` have 1 repeat and 30–60 frames; `bench/repair_smoke.json` has 352 frames and no repeats field. They started 11:21–11:57 on 2026-11-09, so the machine was probably loaded (inferred from the daytime start times). They are not quoted.
  - So the "tonight's latencies are higher than the daytime run" flag (write_throughput) has no counterpart here.
- **NVENC session limit (12):** does not apply. CR-FRAG-INTRA opens one encoder, untimed; the §2.5 checks open one or two encoders at a time.
- **Intra payloads:** 300 NVENC packets were looped to 3000 (`bench_fragment_overhead.py:63`, `:85-88`).
  - measured: both templates are 300/300 key frames (ffprobe, inspect only, 2026-11-10, `verify_method2_template_keyframes.txt`), and the script passes `is_keyframe` through (code, `:84`, `:154`). The template mtimes (04:35:58, 04:36:02) fall inside item 61 (per `VERIFY_method.md`).
  - Templates: `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/crash_resilience/bench_tmp/template_{h264nv,hevcnv}_intra.mkv`.
  - The QPs are matched_settings' target A QPs, but the bench fed yuv420p and a different corpus, and the quality of these frames was not measured. **They are not target A results.** Only payload size depends on quality, not container overhead (inferred).
  - The template open sits inside the intra timer (§2.12), so intra wall times are not comparable with MJPEG wall times.
- **Short timed windows.** One fragment repeat is 0.04–0.12 s, except the folder variant at 0.62–0.66 s. One fsync repeat is 0.06–1.4 s (measured, `wall_s`). Differences under about 1 µs/frame are within the min–max ranges.
- **Page cache.** Fragment and non-fsync policies only reach the OS cache. Repair inputs were read from cache (inferred), and repair outputs were not fsynced (code). There is no cold-cache number, which matters for the power-loss case (§2.13).
- **One drive.** The fsync and write numbers come from one WD_BLACK SN850X NVMe (study record, `results/write_throughput/BENCH.md:4`).
- **MJPEG pts are CFR at 1/1000** (`bench_fragment_overhead.py:57`), not VFR capture times.
- The flags for nvJPEG, WebCodecs scrub, `<video>` N=8 sync and the uncompressed lossless check do not apply to this topic.

## 6. Not tested, limits, NOT VERIFIED

- **Intra H.264/HEVC under a kill (in scope): partly tested.** One 75-frame live kill per codec into MKV+fp (§2.5). Not tested: other containers, prefix cuts (power loss), Electron playback of the killed files, kill timing variation, and a kill with `delay=0`.
- **Cost of NVENC `delay=0`:** not measured (only the hold count).
- **By-path fsync of the PyAV video file:** not benched; the second-handle approach is NOT VERIFIED (§2.11). The kill behaviour of the file-object writer is not tested.
- **Power loss.** Real power loss on NTFS was not tested, only prefix cuts. Reordered writes, stale blocks and metadata loss: NOT VERIFIED. The power-loss benefit of any fsync interval: NOT VERIFIED.
- **Multi-camera durability cost:** fsync and flush were timed for one writer only. Sidecar-only fsync was timed only at K=1.
- **Other drives:** fsync costs were measured on one SN850X NVMe only.
- **Cold-cache repair; repair of larger or 1080p recordings; cold cv2 opens:** not measured.
- **Intra payload quality in the fragment bench:** not measured; these are not target A results (§2.12).
- **Defender CPU per variant:** not recorded.
- **Dropped from the timed queue** (`research/skellycam_recording/recording_upgrade/results/BENCH_QUEUE_2300.md:250-253`; the queue's footnotes use older requirement numbers, today requirements 3 and 8):
  - the AV1 fragment overhead (AV1 has no RTX 3070 encode);
  - the low-delay encoder bench (GOP only);
  - the FFV1 payload (G4 CPU fallback);
  - the GOP-30 `h264nv` payload (replaced by the intra payloads).
- **Not queued:** the outage gap of the resumable recorder (no script exists).
- **sfn26:** whether the packaged launcher kills an ffmpeg grandchild, and the probing bound: NOT VERIFIED (§2.10).
- **FreeMoCap reader:** not run on unfinalized MKV. inferred from §2.2: OpenCV-based readers will miscount and mis-seek.
- **Segment muxer:** the buffering mechanism behind the 2-frame loss is NOT VERIFIED.
- **Chromium:** presentation during play is not verified, and neither is the −4 `decoded_during_play` offset. Seek identity was checked only in E35, on the cl0/fmp4_every GOP files.
- **PyAV 19 functional coverage is a subset.** These remain PyAV 18 bg only: the `idle`/`busy` kills, FFV1 kills, `mkv_resv`, `fmp4_1s`, IVF, `seg_mp4`, the 389-file repair check, and the Electron NUT/AVI/IVF rows.
- **Inputs:** one 720p MJPEG set, 55.3–55.4 KB/frame. The kill files are 150 frames (75 fed for the `rt` kills); the repair files about 1 GB.
- **Kill types:** TerminateProcess only; no OS crash.
- **Clock across restarts:** not tested (the prototype uses `time.time_ns()`).
- **What changed in the previous revision (timed data added):**
  - §2.11–2.13 were new and measured; "cost pending" implications were replaced by measured numbers.
  - The old statement that `bench_repair.py` starts the writer with PyAV 18 was fixed: `bench_repair.py:46` uses `sys.executable`, and `writer_child_interpreter` is the uv PyAV 19 environment.
  - The old implication 3 (inter codecs need cl0 plus low delay) moved to background: requirement 8 makes GOP codecs out of scope, and the new data show cl0 is redundant for all-key payloads.
  - Nothing in the earlier functional results was contradicted: the 1 GB repair recovered N−1 frames, matching §2.1.

## 7. How to reproduce

Run from the repo root `C:/Users/Dom/GitHub/freemocap/skellycam`. Media goes under `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/crash_resilience/`.

**Timed (quiet machine, one item at a time, P-cores; as run by `scripts/bench_runner/run_queue.py`).** Commands are from `BENCH_RUN_2300_LOG.jsonl`; each script has a PEP 723 header pinning `av==19.0.2`.

```
S=research/skellycam_recording/recording_upgrade/scripts/crash_resilience
uv run --script $S/bench_fsync.py --frames 3000 --repeats 3 --out-name pyav19                                       # bench/fsync_pyav19.json
uv run --script $S/bench_fragment_overhead.py --payloads mjpeg --frames 3000 --repeats 3 --out-name mjpeg_pyav19     # bench/fragment_overhead_mjpeg_pyav19.json
uv run --script $S/bench_repair.py --methods pyav_copy_mkv,resumable_repair --gb 1 --repeats 3 --out-name pyav19     # bench/repair_pyav19.json
uv run --script $S/bench_fragment_overhead.py --payloads h264nv_intra,hevcnv_intra --frames 3000 --repeats 3 --out-name intra_pyav19   # bench/fragment_overhead_intra_pyav19.json
```

- Item logs: `research/skellycam_recording/recording_upgrade/results/bench_runner/logs/20261109T230007/{18_CR-FSYNC-PYAV19,19_CR-FRAG-MJPEG-PYAV19,28_CR-REPAIR-PYAV19,61_CR-FRAG-INTRA-PYAV19}.{out,err}.txt`. All `.err.txt` files are empty.
- Tables and load record: `BENCH.md` in this folder.

**Functional (PyAV 19.0.2).**

```
C=research/skellycam_recording/recording_upgrade/scripts/crash_resilience/pyav19_checks
R=research/skellycam_recording/recording_upgrade/results/crash_resilience
uv run --script $C/pyav19_check.py        $R/pyav19_recheck.json             # §2.1-2.3, §2.6 (run twice -> pyav19_recheck_repeat.json)
uv run --script $C/encoder_hold_check.py  $R/encoder_hold_check_pyav19.json > $R/encoder_hold_check_pyav19.log 2>&1   # §2.5 bg
uv run --script $C/trunc_pyav19.py        $R/truncation_pyav19.json          # §2.4
uv run --script $C/resumable_pyav19.py    $R/resumable_demo_pyav19.json      # §2.8
uv run --script $C/verify_method/verify_method_checks.py $R/verify_method_pyav19_checks.json   # §2.1 segment + rt kills
# §2.5 intra NVENC hold-back, delay=0, live kill, template key frames (2026-11-10)
#   scripts in $C/verify_method/step2/ (intra_check.py, intra_delay0.py, child_wrap.py, template_keyframes.py)
#   -> $R/verify_method2_intra_kill.json, $R/verify_method2_intra_hold.json, $R/verify_method2_template_keyframes.txt
# OpenCV 4.12.0 readers (skellycam venv, read-only use)
.venv/Scripts/python.exe $C/cv2_on_pyav19.py     $R/cv2_on_pyav19_files.json
.venv/Scripts/python.exe $C/cv2_seek_identity.py $R/cv2_seek_identity_pyav19_files.json
.venv/Scripts/python.exe $C/verify_method/cv2_on_pyav_remux.py $R/verify_method_cv2_on_pyav_remux.json
# Electron (unset ELECTRON_RUN_AS_NODE first)
python $C/build_el_list.py $R/electron_pyav19_list.json
P=research/skellycam_recording/recording_upgrade/scripts/crash_resilience/electron_probe
skellycam-ui/node_modules/electron/dist/electron.exe $P $R/electron_pyav19_list.json $R/electron_pyav19_e35.json
C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/shared/electron-latest/node_modules/electron/dist/electron.exe $P $R/electron_pyav19_list.json $R/electron_pyav19_e45.json
# Electron 35 seek identity: $C/verify_method/seekprobe/ -> $R/verify_method_electron_seek_identity_e35.json
```

- The exact command lines for the step2 scripts are in `VERIFY_method.md`; they are not repeated here.
- PyAV 18 background runs, the sidecar test and the sfn26 test: commands in `NOTES.md` §3.5.
- FFmpeg n9.0.2 sources: `https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/libavformat/<file>`. SVT-AV1: `https://gitlab.com/AOMediaCodec/SVT-AV1/-/raw/v4.2.0/Docs/Parameters.md`. sfn26 code: `git show upstream/sfn26:<path>` (765bf82d).

## 8. Verification

**Date:** 2026-11-10. Reports: `VERIFY_provenance.md` and `VERIFY_method.md` in this folder (earlier rounds: `VERIFY_provenance.prev.md`, `VERIFY_method.prev.md`).

**What the verifiers checked.**
- Provenance: recomputed the §2.11 fsync table, both §2.12 fragment tables and the §2.13 repair table from the `repeats[]` arrays of the quiet-run JSON; every cell matched. Checked the §2.1–2.10 functional numbers against their result files. Re-fetched the FFmpeg n9.0.2 sources and the Python and Microsoft pages; quotes and line numbers were exact. Checked the sfn26 citations at 765bf82d and the four CR lines in `BENCH_RUN_2300_LOG.jsonl` (P-cores, load, MsMpEng, no Defender scans).
- Method: checked the timer regions, payload settings, repeat structure and caveats. Ran new PyAV 19 functional checks (counts only, no timing): intra NVENC hold-back with and without `delay=0`, a live kill per codec into MKV+fp, and ffprobe of the intra templates.
- Reviser (this revision): re-checked each refutation against the evidence before applying it: `pyav19_recheck.json` (bytes mod 262144; 25 images, 19 remuxed, 5 unreadable, seg not remuxed), `bench/fragment_overhead_*_pyav19.json` and `bench/fsync_pyav19.json` (`wall_s`, per-repeat `lat_us_max`), `verify_method2_intra_kill.json`, `verify_method2_intra_hold.json`, `verify_method2_template_keyframes.txt`, `encoder_hold_check_pyav19.log` lines 9/18/33/42, `sfn26_pipe.md`, `open_long.json`, the smoke JSONs' `env`/`repeats`/`started`, and `bench_fragment_overhead.py:45-48`, `:70`, `:84`, `:124`, `:143`, `:147`, `:154`, `:181-187`.

**What was changed.**
- Corrected (refuted): no-fp MP4/fMP4 files are 44 B over a multiple of 262144, only MKV/NUT are exact multiples (§2.1); 5 unreadable images, not 4, and seg_mkv+fp was not remuxed (§2.3); fsync K=30 max is 4.2 ms median, 3.6–9.1 ms (§2.11, §3B, §4.10); fragment repeat length (§5).
  - The verifier's range "0.04–0.1 s except folder" was itself slightly short: rawidx repeats are 0.104–0.115 s, so the text now says 0.04–0.12 s, except folder 0.62–0.66 s.
- Corrected (refuted): MKV+fp is no longer called the lowest-overhead crash-safe option; NUT, AVI and raw + index are lower, and overhead does not decide the choice (§4.1).
- Corrected (refuted): intra NVENC hold-back and kill behaviour are now measured (2 held, 72 of 75 readable after a live kill into MKV+fp, 0 held with `delay=0`); §2.5, §2.1, §3A, §3B, §4.3 and §6 updated, and the open functional check removed.
- Relabelled or narrowed (weak): K=300 is the largest median worst frame, and the largest single frame was 58.9 ms (§2.11); Defender item 28 is the highest, item 19 second, both causes inferred (§5); the intra timer includes the template open (§2.12); SVT rate-control cited to log lines 18 and 42 only (§2.5); AV1 fMP4 torn sample marked inferred (§2.4); kill-matrix seek claim limited to rows cv2 could open (§2.2); machine and disk labelled study record (header); cross-topic open times named as finalized variants, warm, with first-open values (§4.11); sfn26 feeder-kill cells filled with 300/300 (§2.10); smoke-file description fixed (§5); all-intra templates upgraded to measured (§2.12, §5); rawidx repair described as PyAV `format='mjpeg'` (§2.13).
- Method fixes: wall times comparable within a payload only, cross-payload ranking dropped (§2.12, §3A); intra payloads stated as not target A results (§2.12, §5); container-bytes claim limited to MKV/fMP4/NUT/plain MP4, segment overhead codec-dependent (§2.12); fsync drive named and non-transferable (§2.11, §5); fsync policy rewritten as a trade-off (§4.10); folder cost stated as writer-only, excluding Defender (§2.12, §4.12); raw repair "all frames" limited to a quiescent kill (§2.13); within-run noise sentence added (§5); cold-cache caveat tied to power loss (§2.13, §4.6); §4.11 now states fMP4's faster mux.
  - The verifier said fMP4-vs-MKV mux ranges do not overlap for any payload; they do overlap for HEVC (17.0–18.5 vs 17.8–17.9), and the text says so.

**What remains NOT VERIFIED** (details in §6): real NTFS power loss and the power-loss benefit of any fsync interval; by-path fsync of the PyAV video file (second-handle FlushFileBuffers); a kill with NVENC `delay=0` and its cost; intra NVENC under cuts, in other containers and in Electron; multi-camera durability cost; other drives; cold-cache repair and cold opens; quality of the intra fragment-bench payload; Defender CPU per variant; the segment-muxer buffering mechanism; the sfn26 probing bound and grandchild kill; the Chromium −4 `decoded_during_play` offset.
