# jpeg_passthrough: FINDINGS (goals G1, G5)

2026-11-10, Gerald (Windows 11, i7-14700K, RTX 3070). This revision adds the timed results from the quiet overnight run `20261109T230007` and applies the 2026-11-10 verifier pass (§9). The timed results replace every "pending tonight's bench" entry. The functional results from 2026-11-09 still stand, with one refinement from the verifier recheck: OpenCV's MKV count is exact on c922's real VFR (§2.4). §2.9 lists what the timed data confirms. The Step 3 gap-fill (2026-11-10) folds in the crash_resilience gap-fills GF01 (cross-topic container table) and GF02 (PTS mode, and paced kills with `flush_packets=1`), and applies the Step 3 verification (`results/jpeg_passthrough/VERIFY_step3.md`); see §9.

Paths are relative to `research/skellycam_recording/recording_upgrade/` (RU) unless they are absolute.

**Labels**
- **measured**: a result file.
- **computed**: arithmetic on fields of the cited result file.
- **measured, PyAV 18 - background**: made with the skellycam venv (PyAV 18.0.0, libavformat 62.12.102, libavcodec 62.28.102; `mux_matrix.json` meta). It is not the implementation under test.
- **source**: a primary source, accessed 2026-11-09 (re-checked by the verifier on 2026-11-10).
- **code**: file:line.
- **inferred**: reasoning, kept to a minimum.

**Implementation under test:** PyAV 19.0.2, with libavformat and libavcodec 63.1.102 (measured: `results/jpeg_passthrough/pyav19_recheck.json` meta; also `meta.pyav_ffmpeg_libs` in both mux bench JSONs). `av.ffmpeg_version_info` is "9.0.2" (measured: `pyav19_seek_ts_check.json` meta). The bench JSONs record library versions only, not this string.

**Quality target.** Passthrough stores the camera's own JPEG bytes unchanged (§2.1). Every size and cost here is at the camera's own quality. That quality is **not a measured point on the target A/B scale**.
- measured: the C930e and C922 JPEG sets each use one quantisation table. The nearest IJG quality is 94 for luma and chroma in all four sets, but not as an exact match (`results/intra_compare/camera_jpeg_quality.md` lines 7-10).
- source: HANDOFF.md §1.1 defines target A from libjpeg-turbo q94 on the same camera models' YUY2 frames.
- measured: the cameras' 1080p JPEGs are about half the size of libjpeg-turbo q94 on the YUY2 frames: 134,574 vs 260,827 B (c930e) and 192,382 vs 312,812 B (c922) (`results/intra_compare/camera_jpeg_quality.md` lines 9-10, 16-17). The cause (different scenes, or in-camera processing such as noise reduction) is NOT VERIFIED (`results/intra_compare/NOTES.md:156`).
- inferred: passthrough is near target A in quantisation, but the same table does not mean the same fidelity, so this is uncertain. The camera JPEG's own SSIM-Y against a raw frame of the same instant was never measured (NOT VERIFIED).

**Result files**

Functional, PyAV 19.0.2 (all in `results/jpeg_passthrough/`):

| File | What it holds |
|---|---|
| `version_bump.json` | c930e_720p_flash written to files and read by OpenCV 5.0.0.93, which bundles its own avformat 61.7.100 (meta) |
| `pyav19_recheck.json` | All 7 sets written in memory, kill test, setup details, DHT decode |
| `pyav19_fmp4_tb_us_readers.json` | OpenCV 4.12.0 and FreeMoCap reads of fMP4 written at time base 1/1e6 |
| `verify_method_writer.json` | Verbatim payload check, plus files with dropped frames: gap60 (frames 300-359 removed, 831 frames) and drop50 (every 50th frame removed, 874 frames). Also a 54,000-frame file. |
| `verify_method_reader.json` | OpenCV 4.12 and FreeMoCap reads of those files |
| `verify_method_killed_readers.json` | OpenCV 4.12 and FreeMoCap reads of files killed while PyAV 19 was writing |
| `verify_method2_mkv_count.json` | OpenCV 4.12 count and fps for MKV and fMP4 1 s at 1/1e6, on c930e and c922 real VFR (verifier recheck, 2026-11-10) |
| `verify_method_size_check.json`, `verify_method_open_dry.json` | Size in memory vs on file; dry run of the open bench (counts only) |
| `pyav19_seek_ts_check.json` | PyAV timestamp seek, checked by frame identity |
| `pyav19_lavf_tag.json` | Writer tag per muxer |
| `step3_gf02_sidecar_flags.json` | Read-only scan of the GF02 Part A sidecars for `FLAG_PTS_ADJUSTED`, and whether any GF02 seek target hit a flagged frame (Step 3 revise, 2026-11-10; script `scripts/jpeg_passthrough/step3_gf02_sidecar_flags.py`) |

Cross-topic, used for §2.4, §2.5 and §4: GF02 = `results/crash_resilience/gapfill/GF02_container_matrix.json` (merged from `GF02_partA_*.json` in the same folder), and `GF01_container_decision_table.md`.

Timed, quiet run `20261109T230007` (all in `results/jpeg_passthrough/bench/`). The short names are used below.

| Short name | Queue item (order) | File |
|---|---|---|
| MUX-D | JP-MUX-PYAV19 (17) | `bench_mux_default_pyav19_20261110T055215Z.json` |
| MUX-F | JP-MUX-FSYNC-PYAV19 (59) | `bench_mux_fsync_pyav19_20261110T093308Z.json` |
| ROT | JP-ROTATE (60) | `bench_rotate_20261110T093546Z.json` |
| OPEN | JP-OPEN-LONG-PYAV19 (29) | `open_long.json` |

- `results/jpeg_passthrough/BENCH.md` summarises these files. Every timed number below was recomputed from the raw `runs` arrays (medians and min-max over 5 reps) and matches BENCH.md.
- None of this topic's items was in the OV-COST re-run `20261110T053653`.

**Background files (PyAV 18 writer):** `mux_matrix.json`/`.md`, `keyframe_setup.json`, `truncation.json`, `edge_cases.json` and `electron_check.json`. The Electron check used media from the PyAV 18 mux_matrix.

**Not PyAV-dependent:** `rotation.json` and ROT (libjpeg-turbo 3.2.1, jpeglib, jpegtran).

**Timestamp corpus.** Only c930e_720p_flash (891 frames) and c922_720p_flash (893) have real capture times (MF sample time, 100 ns units). The other 5 sets (10-19 frames each) reuse c930e's first intervals, and 720p60 halves them. Every timestamp is floored to whole µs before muxing (code: `scripts/jpeg_passthrough/jp_common.py:22-29,59-69`; `pyav19_recheck.py:152-160`).

**PTS modes.** "Real PTS" (real VFR PTS) = container pts from the capture time. "Index PTS" = container pts = frame index at the nominal rate, with capture times only in a sidecar (code: `scripts/python_integration/recwriter.py:87-89`, time base 1/nominal_fps in index mode). This topic's own files all use real PTS; index PTS appears only in GF02 and python_integration results.

## 1. Questions answered

1. **G1.** Can Python (PyAV 19.0.2) store camera JPEG bytes in a container with no decode or re-encode, and get the same bytes back?
2. Which containers accept MJPEG? Do they change JPEG headers? How well do they keep real variable-frame-rate (VFR) capture timestamps?
3. **G5, compatibility side.** For each wrapper (folder of JPEGs, raw + sidecar, MKV, MP4, fMP4, MOV, AVI, NUT):
   - frame count and seeking in OpenCV, FreeMoCap and PyAV;
   - reading after a hard kill;
   - Chromium playback.
4. **G5, throughput side (quiet run).** Per-frame mux cost per wrapper, close cost with and without a flush to disk, and the cost of opening and counting a 30-minute recording. One camera per process.
5. Edge cases: frames without DHT, extra bytes after the entropy-coded data, and lossless rotation as the Rust code does it, now with its per-frame cost.

## 2. Findings

### 2.1 Writing JPEG bytes as packets (G1)

**The recipe and what it was tested on**

- The recipe is `add_mux_stream("mjpeg", rate, width, height)`, then `av.Packet(jpeg_bytes)`, then `mux()` (measured: `pyav19_recheck.json` `A_matrix`).
- It writes all 7 sets on PyAV 19.0.2:
  - containers: MKV, MP4, fMP4 (1 s and per-frame fragments), MOV, NUT, AVI and raw `.mjpeg`;
  - sets: c930e_720p_flash 891, c922_720p_flash 893, c922_1080p 19, c930e_1080p 19, c922_1600x896 19, c922_720p60 10 and generic_1080p 11 frames, so 1,862 frames per container and mode.

**Byte-exactness**

- 194 of 194 written outputs are SHA-256-identical per packet, in order, through PyAV 19.0.2 demux (measured: `pyav19_recheck.json` `A_matrix`).
  - There were 210 attempts: 7 sets × 15 container variants × VFR/CFR.
  - 16 were not written: 14 WebM, plus AVI VFR on c930e (2 variants; see §2.3).
  - The writes were in memory (BytesIO). This does not change the output: on PyAV 19.0.2, in-memory and file writes have identical sizes for MKV, MP4 and NUT (measured: `verify_method_size_check.json`).
- **Checked without FFmpeg.** All 891 c930e input JPEGs appear verbatim and in order in the raw file bytes of MKV and of fMP4 1 s, fMP4 per-frame, MP4, MOV and NUT at 1/1e6 (measured: `verify_method_writer.json` `V1_verbatim`).
- Files written by PyAV 19.0.2 for c930e_720p_flash are byte-exact in every container, VFR and CFR (measured: `version_bump.json` `pyav19_bytes.byte_exact_all`).
- Background (measured, PyAV 18 - background: `mux_matrix.md` "Across all sets"):
  - 0 mismatches across 3 writers: PyAV VFR, PyAV CFR and the ffmpeg CLI with `image2pipe -c:v copy`;
  - 2 readers: PyAV demux and `ffmpeg -c:v copy -f image2`;
  - the Python raw+sidecar and folder-of-JPEG writers.
- PyAV's own description: `add_mux_stream` creates a stream "for muxing pre-encoded data without creating a :class:`.CodecContext`". It raises `'{format}' format does not support '{codec}' codec` when `avformat_query_codec` fails (source: PyAV 19.0.2 `av/container/output.py:265-269,306-310`, installed wheel).

**Settings it needs**

- **Width and height are mandatory.** Without them every container fails at the first mux with `ArgumentError ... returned 22; last error log: [<fmt>] dimensions not set` (measured: `pyav19_recheck.json` `D_setup` `*|nodims`).
- **`is_keyframe` does not need to be set.** With `is_keyframe=False`, 30 of 30 packets are still flagged as keyframes in MKV, MP4, MOV, AVI, NUT and raw (measured: `pyav19_recheck.json` `D_setup` `*|mux_stream|kf=False`).
  - Reason: "`if (sti->is_intra_only)` / `pkt->flags |= AV_PKT_FLAG_KEY;`" (source: FFmpeg n9.0.2 `libavformat/mux.c:820-821`, https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/libavformat/mux.c).
  - The 891-frame c930e set was checked only on PyAV 18 (measured, PyAV 18 - background: `keyframe_setup.json` `keyframe`).
- **Avoid `add_stream_from_template`** (measured: `pyav19_recheck.json` `D_setup` `template_vfr_file`).
  - With VFR timestamps written to a file, MP4 and MOV hold 29 of 30 packets (ffprobe `nb_read_packets` 29). AVI fails with EINVAL (`non monotonically increasing dts ... 2 >= 2`).
  - PyAV 18 behaved the same (measured, PyAV 18 - background: `keyframe_setup.json` `setup`).
  - With CFR timestamps in memory, MP4 and MOV kept 30 of 30 (`D_setup` `*|template|kf=True`).
  - Root cause: NOT VERIFIED.

**WebM**

- PyAV 19.0.2 refuses MJPEG in WebM on all 7 sets with `ValueError: 'webm' format does not support 'mjpeg' codec` (measured: `pyav19_recheck.json`). The ffmpeg CLI refuses it too (measured, PyAV 18 - background: `mux_matrix.md`).
- source: FFmpeg n9.0.2 `libavformat/matroskaenc.c:3744-3747`. `webm_query_codec` accepts only `ff_webm_codec_tags`: V_VP8, V_VP9, V_AV1, A_VORBIS, A_OPUS and D_WEBVTT/* (`libavformat/matroska.c:110-124`).
- source: https://www.webmproject.org/docs/container/ says "Video codec SHOULD be VP8 *or* VP9".

**How the containers register MJPEG**

- **MKV** registers MJPEG as `V_MJPEG`: "Motion JPEG is a video compression format in which each video frame or interlaced field is compressed separately as a [@!JPEG] image.", with "Initialization: none".
  - source: https://www.matroska.org/technical/codec_specs.html. The served HTML contains the bracket text literally (fetched with curl 2026-11-09; copy in `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/jpeg_passthrough/mkvspec/codec_specs.html`).
  - source: FFmpeg n9.0.2 `libavformat/matroska.c:86`.
- **MP4** stores MJPEG as an `mp4v` sample entry with object type 0x6C, "Visual ISO/IEC 10918-1" (source: https://mp4ra.org/registered-types/object-types; FFmpeg n9.0.2 `libavformat/isom.c:55`).
- ffprobe shows `codec_tag_string` `mp4v` for fMP4 written by PyAV 19.0.2 (measured: `pyav19_recheck.json` `B_fmp4_tb_us_ffprobe`).

**Container overhead, 891 frames** (PyAV 19.0.2, c930e_720p_flash VFR, 49,314,521 payload bytes; AVI is CFR; measured: `pyav19_recheck.json` `A_matrix` `size_bytes`). Per-frame overhead on 3000-frame files is in §2.9.

| Container (stream time base) | Overhead |
|---|---|
| MKV (1/1000, fixed) | 40,253 B |
| MP4 (1/90000) / (1/1e6) | 11,232 / 11,936 B |
| fMP4 1 s (1/90000) / (1/1e6) | 11,738 / 11,738 B |
| fMP4 per frame (1/90000) / (1/1e6) | 117,521 / 117,521 B |
| MOV (1/90000) / (1/1e6) | 11,139 / 11,843 B |
| NUT (1/90000) / (1/1e6) | 25,376 / 26,908 B |
| AVI (1/fps), CFR | 27,515 B |
| raw `.mjpeg` | 0 B |

**PyAV 18 vs PyAV 19 file sizes**

- Over 166 matched rows, PyAV 18 writes are 0-3 B larger than PyAV 19 writes: 0 B for AVI and raw, 1 B for MP4/MOV/NUT/fMP4, 3 B for MKV. The payload bytes are identical (measured: `mux_matrix.json` vs `pyav19_recheck.json`).
- PyAV 19 writes the tag `Lavf63.1.102` 3 times in MKV and once in MP4, MOV, NUT and AVI (measured: `pyav19_lavf_tag.json`). PyAV 18's tag `Lavf62.12.102` is 1 character longer.
- inferred: the tag length explains MKV (3 B) and MP4/MOV/NUT (1 B). AVI's 0 B is probably RIFF even-byte padding. The exact cause is NOT VERIFIED.

**Rust reference**

- The Rust reference does not pass JPEGs through. It pipes them to ffmpeg with libx264 (code: `git show upstream/sfn26:skellycam-rust/src/recording/recorder.rs:1-6,38-46,141-155`; re-read in VERIFY_provenance.md).

### 2.2 JPEG headers and edge cases

**Headers**

- No muxer changed any JPEG header. Extraction is SHA-256-identical to the input, so no APP0/AVI1 was added and no DHT was inserted (measured: `pyav19_recheck.json`, `verify_method_writer.json` `V1_verbatim`).
- Marker layouts (measured: `edge_cases.json` `mjpeg2jpeg.*.in_markers`):
  - Logitech C922 and C930e: `DQT SOF0 DHT DHT DHT DHT COM APP0 DRI SOS`;
  - generic camera: `APP0(JFIF) DQT DQT SOF0 DHT DHT DHT DHT SOS`.
- All 3 cameras carry 4 DHTs equal to the standard tables (measured: `edge_cases.json` `dht_vs_standard` all True; `dht_tables_count` 4).

**DHT-stripped frames**

- Muxing: the first 30 c930e_720p_flash frames, CFR, in memory, stay byte-exact in MKV, MP4, fMP4 1 s, MOV, AVI (1/fps), NUT and raw on PyAV 19.0.2 (30/30 each; measured: `pyav19_recheck.json` `D_setup` `*|dht_stripped`; scope from code: `pyav19_recheck.py:320-331`).
- Decoding: PyAV 19.0.2's mjpeg decoder turns stripped frames into the same pixels as the originals: c930e 30/30, c922 30/30, generic 11/11 (measured: `pyav19_recheck.json` `E_decode_dht_stripped`).
- Why it works: FFmpeg installs default Huffman tables when the decoder starts (source: FFmpeg n9.0.2 `libavcodec/mjpegdec.c:62,148`, `init_default_huffman_tables`).
- cv2.imdecode, Pillow and djpeg 3.2.1 also give stripped == original (measured: `edge_cases.json` `decoders`; not PyAV-dependent).
  - djpeg exits non-zero on the generic camera's original and stripped frames alike ("535 extraneous bytes before marker 0xd9"). Its two outputs are still equal (11/11).

**Bitstream filters**

- `mjpeg2jpeg` adds 438 B (Logitech) or 419 B (generic) per frame. Every camera that carries DHT ends up with two table sets (5 DHT markers). The output is not byte-exact, so use it only on request (measured, ffmpeg CLI 9.0.2 bsf on PyAV 18 MKV - background: `edge_cases.json` `mjpeg2jpeg`, `out_markers`).
- `mjpegadump` +44 B: NOT VERIFIED. It was a one-off in NOTES.md §3 and its output was deleted.

### 2.3 Timestamps (real VFR capture times)

**Accuracy by container** (corpus caveat in the header: 2 real timestamp series, 5 borrowed)

- **1/1e6 time base.** MP4, MOV, NUT, fMP4 1 s and fMP4 per-frame keep the timestamps exactly at 1 µs resolution on all 7 sets: max error 0 µs against the µs values the writer was given, and strictly increasing (measured: `pyav19_recheck.json` `A_matrix` `*_tb_us|vfr`). The sub-µs part of the 100 ns source is never stored, so ns precision needs the sidecar (code: `pyav19_recheck.py:156`).
- **fMP4 1/1e6 readers:**
  - ffprobe reads the PyAV 19.0.2 files with 0 µs error (measured: `pyav19_recheck.json` `B_fmp4_tb_us_ffprobe`);
  - OpenCV 4.12.0 `CAP_PROP_POS_MSEC` also gives 0 µs on c930e_720p_flash (measured: `pyav19_fmp4_tb_us_readers.json`).
- **Default 1/90000 time base.** Max error is 5.556 µs in MP4, MOV, fMP4 and NUT (measured: `pyav19_recheck.json`).
- **MKV** is fixed at 1 ms. Max error is 470 µs on VFR (measured: `pyav19_recheck.json` `c930e_720p_flash|mkv|vfr`).
  - Frames that arrive less than 1 ms apart get the same timestamp, so the pts is not strictly increasing.
  - On c930e, frames 81 and 82 both get pts 2704. A timestamp seek to frame 82 returns frame 81 (measured, PyAV 19.0.2: `pyav19_seek_ts_check.json` `full|mkv` misses).
  - Their capture times are 11 µs apart (11,000 ns from the capture jsonl via `jp_common.real_timestamps_ns`, recomputed in VERIFY_provenance.md).
  - c922_720p_flash has no pair of frames sharing a ms (measured: `verify_method2_mkv_count.json` `same_ms_pairs` 0; c930e 1).
  - source: FFmpeg n9.0.2 `libavformat/matroskaenc.c:3602-3603`, "ms precision is the de-facto standard timescale for mkv files" / `avpriv_set_pts_info(st, 64, 1, 1000);`.
  - measured: python_integration's recwriter (as copied by GF02) resolves this collision by bumping frame 82 to pts 2705 and setting `FLAG_PTS_ADJUSTED` in the sidecar (`step3_gf02_sidecar_flags.json`; code: `scripts/python_integration/recwriter.py:46`, `:135-136`). See §4 item 8.

**AVI rounds VFR timestamps and refuses frames that land on the same tick**

- AVI rounds every timestamp to its stream time base and fills gaps with empty packets (source: FFmpeg n9.0.2 `libavformat/avienc.c:745-762`). Measured on PyAV 19.0.2 (`pyav19_recheck.json` `A_matrix`):
  - At the default 1/600, VFR writes 6 of 7 sets with max error 830 µs.
  - At 1/fps, VFR writes 6 of 7 sets with max error 14,671.667 µs.
  - c930e_720p_flash fails at both: `non monotonically increasing dts ... 1622 >= 1622` (1/600) and `81 >= 81` (1/30).
  - PyAV 18 gives the same 6/7 pattern (measured, PyAV 18 - background: `mux_matrix.md` lines 32, 41).
- PyAV's default AVI stream time base is 1/600 even for CFR (measured: `pyav19_recheck.json` `avi|cfr` `stream_tb`).
  - Read back, OpenCV 5.0.0.93 reports 17,820 frames for 891 (measured: `version_bump.json`).
  - Setting `st.time_base = 1/fps` fixes this: `avi_tb_rate|cfr` reports 891.

**Formats without stored timestamps**

- Raw `.mjpeg` stores no timestamps. Readers assume 25 fps, and the error reaches 6,031,976 µs on c930e VFR (measured: `pyav19_recheck.json`).
- The raw+sidecar index returned the exact int64 ns timestamps, 7/7 (measured, Python writer, PyAV 18 run - background: `mux_matrix.json` `sidecar_reader_ts_exact_ns`).
- The folder-of-JPEGs writer writes `timestamps.csv` (code: `scripts/jpeg_passthrough/jp_io.py:157-166`, opened at `:161`), but nothing reads it back. Not tested.

**Do the readers agree?**

- **PyAV 19 files.** On c930e, the maximum timestamp error from PyAV 19 pts agrees with the one from OpenCV 5.0.0.93 `CAP_PROP_POS_MSEC` in every written container (measured: `version_bump.json` `pyav19_ts` vs `cv5_ffmpeg_ts`). Only maxima are stored, and ffprobe is not in that file.
- **PyAV 18 files.** PyAV, ffprobe and OpenCV 4.12 agree on the maximum everywhere except raw `.mjpeg` and raw+sidecar, where OpenCV differs by up to 586 µs: 6,031,976 vs 6,032,562 µs on VFR (measured, PyAV 18 - background: `mux_matrix.md` lines 38-39 and 49; in the jpg_folder row, line 50, all three agree).

### 2.4 Frame count and seeking (G5 compatibility)

**How the readers work**

- FreeMoCap's `VideoHelper.from_video_path` opens `cv2.VideoCapture(str(video_path))` and stores `CAP_PROP_FRAME_COUNT` (code: freemocap 5632778a, `freemocap/core/pipeline/posthoc/video_group_helper.py:151,159`).
- A `VideoGroup` raises unless every camera reports the same count (code: `video_group_helper.py:381-385`).
- FreeMoCap reads forward with `grab()` and then `read()`. It never sets `CAP_PROP_POS_FRAMES` (code: `video_group_helper.py:235-250`; there is no `POS_FRAMES` in the file).
- skellycam's file discovery accepts only `{".mp4", ".avi", ".mov", ".mkv", ".webm"}` (code: `skellycam/core/recorders/videos/parse_video_filename.py:18`).
- OpenCV's frame count is `nb_frames`, or `floor(duration × fps + 0.5)` when `nb_frames` is 0 (source: OpenCV 4.12.0 `modules/videoio/src/cap_ffmpeg_impl.hpp:1980-1989`).
- OpenCV turns a time into a frame index through the average fps: `(int64_t)(get_fps() * sec + 0.5)` (source: same file, `:1992-1996`).
  - inferred: with real VFR PTS, a capture with gaps therefore breaks `CAP_PROP_POS_FRAMES` seeks. With index PTS, time = index / fps, so the conversion is exact; GF02 measured 11/11 on gap60 and drop50 with index PTS (rows below).
- **Seek test method.** OpenCV seek targets are `[0,1,2,n//3,n//2,n-2,n-1,5,n//2,3]`. "Exact" means the frame matches the same reader's sequential decode, not the input frame (code: `jp_io.py:335-343`). About 4 of the 10 targets are informative.

**OpenCV 4.12.0 on PyAV 19.0.2 files** (this topic's rows: real PTS, time base 1/1e6 except MKV; GF02 rows as marked)

| File | Count (actual) | Frames read | OpenCV seek | FreeMoCap count / reads matching OpenCV's sequential decode | Source (measured) |
|---|---|---|---|---|---|
| c930e full (no gaps), fMP4 1 s and per-frame | 891 (891) | 891 | 10/10 | 891 / 4 reads, identity not checked | `pyav19_fmp4_tb_us_readers.json` |
| gap60, fMP4 1 s / per-frame / MP4 | 831 (831) | 831 | **5/10** | 831 / 4 of 4 | `verify_method_reader.json` |
| drop50, fMP4 1 s / per-frame / MP4 | 874 (874) | 874 | **7/10** | 874 / 4 of 4 | `verify_method_reader.json` |
| gap60 / drop50, MKV (1/1000) | 888 for 831 / 888 for 874 | 831 / 874 | 5/10 / 5/10 | 888 / 3 of 4 (frame 887: "Failed to grab frame") | `verify_method_reader.json` |
| 54,000 frames, 1,796 s, one 2 s gap, fMP4 1 s / per-frame / MP4 | 54,000 (54,000) | 54,000 grabbed | not run | 54,000 / 4 reads without error, identity not checked | `verify_method_reader.json` `long_*` |
| c930e / c922 real VFR, MKV | 888 for 891 / 893 for 893 | not recorded | not run | not run | `verify_method2_mkv_count.json` |
| c930e / c922 real VFR, fMP4 1 s | 891 / 893 (exact) | not recorded | not run | not run | `verify_method2_mkv_count.json` |
| GF02, **index PTS**, MKV + fp, MKV + fp + empty pkt, fMP4 per-frame + fp, fMP4 1 s + fp; c930e full / gap60 / drop50 / c922 full | 891 / 831 / 874 / 893 (exact in 16/16 files) | = written (`grab()`) | 11/11 in 16/16 files | ok in 16/16 (count = written, 4/4 reads match) | GF02 `partA[]` |
| GF02, **index PTS**, 54,000 frames, MKV + fp / fMP4 1 s + fp | 54,000 / 54,000 (exact) | 54,000 grabbed | 11/11 / 11/11 | ok / ok | GF02 `partA[]`; `GF02_partA_long_read.json` |
| GF02, real PTS, MKV + fp and MKV + fp + empty pkt; c930e full / gap60 / drop50 / c922 full | 888 / 888 / 888 / 893 (exact on c922 only) | = written | 2/11, 2/11, 1/11, 11/11 (same for both) | FAIL (count) in 6/6 c930e-derived files; ok in 2/2 c922 | GF02 `partA[]` |
| GF02, real PTS, fMP4 per-frame + fp and fMP4 1 s + fp; c930e full / gap60 / drop50 / c922 full | 891 / 831 / 874 / 893 (exact) | = written | 9/11, 1/11, 8/11, 11/11 (same for both) | ok in 8/8 | GF02 `partA[]` |
| GF02, real PTS, 54,000 frames, fMP4 1 s + fp | 54,000 (exact) | 54,000 grabbed | 11/11 | ok (4/4 reads match) | GF02 `partA[]` |
| GF02, real PTS, 54,000 frames, MKV + fp | 53,820 for 54,000 | 54,000 grabbed | **1/11**: 5400 → 5418, 10800 → 10836, 16200 → 16254; later targets more than 70 frames off; last target read fails | FAIL (count) | `GF02_partA_long_read.json` `seek[]` |

- **GF02 rows** (crash_resilience gap-fill, PyAV 19.0.2 writer, OpenCV 4.12 and FreeMoCap readers).
  - code: the writer is a copy of python_integration's `RecordingWriter` with `add_mux_stream`, `flush_packets=1` and pts rounded half up, not floored (`GF02_container_matrix.md` Method; `scripts/crash_resilience/gapfill/GF02/gf02_common.py`).
  - code: GF02 seeks use 11 targets (k = 0, ⌊n·p/10⌋ for p = 1..9, n − 1) checked by identity against the input frame, not this topic's 10 targets checked against sequential decode (`GF02_container_matrix.md` Method). The two seek scores are not directly comparable.
  - measured: all 36 GF02 Part A files are byte-exact through PyAV, and `grab()` returned the frames written in every file (GF02 `partA[].pyav_all_exact`, `cv2_grab`).
  - measured: stream time bases after the header: MKV 1/1000 in both modes; fMP4 1/1e6 with real PTS and 1/15360 with index PTS (GF02 `partA[].time_base`).
  - measured: the real-PTS fMP4 misses on c930e full (a file with no gaps) are k 178 → 179 and 267 → 268 (`GF02_partA_read.json` `seek[].got_seq_index`). So with real PTS, POS_FRAMES seeks can miss even without gaps; this topic's 10 sequential-decode targets did not catch it (10/10).
  - measured: GF02's real-PTS 54,000-frame MKV counts 53,820, one more than OPEN's 53,819. inferred: the writers round pts differently (half up vs floor).
  - inferred: index PTS hide dropped frames from the container timeline by construction; the capture times then come only from the sidecar.

- `CAP_ANY` picks FFMPEG on the fMP4 1/1e6 files (measured: `pyav19_fmp4_tb_us_readers.json`).
- **fMP4 count is estimated, MP4 count is stored.**
  - fMP4 stores no `nb_frames` (measured: `pyav19_recheck.json` `B_fmp4_tb_us_ffprobe` `nb_frames` null), so OpenCV estimates its count. The estimate was exact in every fMP4 case above (both PTS modes), and on the real-content 54,000-frame files of the quiet run (§2.9.3).
  - Plain MP4 stores its count (measured: OPEN `files.mp4_tb_us.pyav_stream_frames` 54,000), so OpenCV does not estimate it.
- **With real VFR PTS, OpenCV's MKV count is wrong when frames are missing or when the mean rate differs from the nominal rate. It is exact on c922's real VFR, and exact in every index-PTS MKV file (GF02).**
  - Wrong (measured: `verify_method_reader.json`, `verify_method_open_dry.json`, `verify_method2_mkv_count.json`, OPEN; GF02 real-PTS rows agree): gap60 888 for 831; drop50 888 for 874; c930e real VFR 888 for 891; looped c930e frames and intervals 299 for 300; the 30-minute looped c930e file 53,819 for 54,000 (OPEN `files.mkv.cv2_frame_count`).
  - Exact: c922_720p_flash real VFR, 893 for 893 (measured: `verify_method2_mkv_count.json`; GF02 real-PTS c922 rows). PyAV 18 agrees: c922 MKV VFR count 893, seek 10/10 (measured, PyAV 18 - background: `mux_matrix.md` line 98).
  - Exact with index PTS: 891 / 831 / 874 / 893 and 54,000 (measured: GF02 index-PTS rows).
  - OpenCV reports MKV fps 30.0 on both cameras. The same captures in fMP4 report 30.10 (c930e) and 29.99 (c922) (measured: `verify_method2_mkv_count.json` `cv2_fps`).
  - Every wrong MKV count without dropped frames above uses c930e intervals.
  - inferred: the mechanism is `round(duration × nominal 30 fps)` from the source rule above. computed: 54,000 × 30 / 30.10 ≈ 53,821, against 53,819 measured.

**OpenCV 5.0.0.93 on PyAV 19.0.2 files, c930e_720p_flash (no gaps)** (measured: `version_bump.json` `cv5_FFMPEG`)

| Container | Count | OpenCV seek |
|---|---|---|
| MP4 and MOV (1/90000 and 1/1e6), fMP4 1 s and per-frame (1/90000) | 891, exact | 10/10 |
| MKV VFR | 888 for 891 | 5/10 |
| NUT VFR (1/90000 and 1/1e6) | 887 | 6/10 |
| NUT CFR | 890 | 10/10 |
| AVI 1/600 CFR / AVI 1/fps CFR | 17,820 / 891 | 5/10 / 10/10 |
| raw `.mjpeg` | -192153584101141 | 0/10 |

- OpenCV 5 never read fMP4 at 1/1e6. Only OpenCV 4.12.0 did (see the table above).

**PyAV seeking**

- **Timestamp seek checked by frame identity** (measured, PyAV 19.0.2: `pyav19_seek_ts_check.json`). Method: seek to frame k's own pts as a sidecar would give it (`seek(backward=True, any_frame=False)`), then check that the next packet's SHA-256 equals input frame k.

  | Container | full (891) | gap60 (831) | drop50 (874) |
  |---|---|---|---|
  | fMP4 1 s, fMP4 per-frame, MP4 (all 1/1e6) | 36/36 | 34/34 | 35/35 |
  | MKV (1/1000) | 35/36 | 33/34 | 34/35 |

  The only MKV miss in each column is the frame pair that shares pts 2704 (§2.3).

- **Keyframe seek by pts** (measured: `version_bump.json` `pyav19_seek_exact`). Method: 5 targets `[0,1,445,890,2]`, comparing only the pts (code: `version_bump_check.py:58`; `jp_io.py:239-253`, with the pts-only test at `:253`).
  - 5/5 for MKV, MP4, MOV, fMP4, AVI CFR and the 1/1e6 variants.
  - 4/5 for NUT.
  - 1/5 for raw `.mjpeg`.
- `CAP_MSMF` (measured: `version_bump.json` `cv5_MSMF`; `pyav19_fmp4_tb_us_readers.json` `cv2_msmf.frames_read` 0):
  - reads 0 frames of MJPEG from MP4 or fMP4;
  - reads MKV partly (888 of 891 on VFR, 891 on CFR);
  - reads MOV and AVI (1/fps) fully.

**Background** (measured, PyAV 18 - background: `mux_matrix.md` "Across all sets"; all 7 sets, OpenCV 4.12.0, no gaps)

- MP4, MOV and fMP4, VFR and CFR: count exact 7/7, seek 70/70.
- MKV VFR: count exact 6/7, seek 65/70.
- NUT: count exact 0/7 in every mode.
- AVI with PyAV's default time base: count exact 0/7.
- Raw `.mjpeg` and raw+sidecar: seek 0/70.
- Folder read through the `frame_%06d.jpg` pattern: count exact 7/7, seek 70/70.
- FreeMoCap `VideoHelper` refuses the folder (count matched 0/7) and raw `.mjpeg` (ValidationError).

### 2.5 Hard kill (adjunct to G2)

**Setup.** A child process muxes 600 c930e_720p_flash frames with PyAV 19.0.2, unpaced and without `flush_packets`, and calls `os._exit(1)` without closing the file (code: `scripts/jpeg_passthrough/pyav19_recheck.py:13`, `:184`; no `sleep` or `flush_packets` in the file). PyAV 19.0.2 then demuxes the result (measured: `pyav19_recheck.json` `C_killed`; readers measured: `verify_method_killed_readers.json`, OpenCV 4.12).

| Container | Complete byte-exact frames of 600 | Packets read | OpenCV count / frames read | FreeMoCap |
|---|---|---|---|---|
| MKV | 597 | 597 | -276701161105643264 / 597 | ValidationError |
| MP4 | not readable ("moov atom not found") | - | - | - |
| MOV | not readable ("moov atom not found") | - | - | - |
| fMP4 1 s, 1/90000 | 578 | 579 | not run on PyAV 19 | - |
| fMP4 1 s, 1/1e6 | 578 | 579 | 582 / 579 | count 582; reads 0, 1, 291 match; frame 581 fails |
| fMP4 per frame | 596 | 597 | 597 / 596 | count 597; frame 596 fails ("Failed to retrieve frame 596") |
| AVI (1/fps) | 597 | 598 | 0 / - [PyAV 18] | ValidationError [PyAV 18] |
| NUT | 597 | 598 | 595 / 598 | count 595; 4/4 reads match |
| raw `.mjpeg` | 597 | 598 | garbage [PyAV 18] | ValidationError [PyAV 18] |

- [PyAV 18] = measured, PyAV 18 - background: `truncation.json`. The demux counts and file sizes match PyAV 18 exactly.
- **OpenCV miscounts every killed file it opened:** fMP4 +1 to +3 (582 for 579, 597 for 596), NUT -3 (595 for 598), MKV negative (measured: `verify_method_killed_readers.json`).
- **This is one kill point, so read it as a bound, not a ranking.** The killed MKV, AVI, NUT and raw files are all 33,030,144 B = 1008 × 32,768 (measured: `pyav19_recheck.json` `C_killed.*.bytes`).
  - computed: 33,030,144 B is also exactly 126 × 262,144.
  - source: FFmpeg n9.0.2 `libavformat/file.c:324-332` sets `max_packet_size = 262144` for written regular files (cited at `results/crash_resilience/FINDINGS.md:85`).
  - inferred: the loss is the unflushed libavformat file buffer (262,144 B per crash_resilience §2.1; the file sizes fit both 32 KiB and 256 KiB multiples). For fMP4 the open fragment is lost as well (up to about 1 s with 1 s fragments).
  - The 597/598 survivors in MKV, AVI, NUT and raw show where the buffer stopped. They are not a container property.
- **A cut last frame can enter analysis without any error.** OpenCV returns 579 frames from the killed fMP4 1 s file, but only 578 packets are complete (measured: `verify_method_killed_readers.json`, `pyav19_recheck.json`).
  - On PyAV 18, the cut frame decoded without error in most containers and raised `InvalidDataError` in fMP4 per-frame (measured, PyAV 18 - background: `truncation.json` `decode_errors`).
  - PyAV 19 decode of the cut frame was not run.

**Paced kills with `flush_packets=1` (crash_resilience gap-fill GF02)**

Setup (`GF02_container_matrix.md` Part B): the GF02 writer (§2.4) fed c930e frames looped at 30 fps. 4 containers × {real, index} PTS × 6 kill points (50, 137, 300, 451, 611, 700 acknowledged frames) = 48 kills, alternating `os._exit(1)` and TerminateProcess. Acknowledged = `write()` returned (mux, plus the empty packet where used, plus the sidecar record flushed). Lost = acknowledged − complete byte-exact frames on disk.

| Container (all with `flush_packets=1`) | Lost per kill, real PTS (kill points in the order above) | Lost per kill, index PTS |
|---|---|---|
| MKV | 1 in 6/6 | 1 in 6/6 |
| MKV + empty timestamped packet per frame | 0 in 6/6 | 0 in 6/6 |
| fMP4 per-frame fragments | 1 in 6/6 | 1 in 6/6 |
| fMP4 1 s fragments | 20, 14, 24, 22, 29, 26 (median 23) | 20, 17, 30, 1, 11, 10 (median 14) |

measured: GF02 `partB[].lost_vs_sidecar`.

- measured: none of the 48 kills produced a torn tail packet (GF02 `partB[].killed_pyav.first_non_exact` null in 48/48).
  - inferred (GF02 report): the kills landed between frames, during the pacing wait, so torn-tail handling was not exercised. The silent cut-frame risk above still stands.
- computed: with index PTS, the fMP4 1 s loss equals ((kill point − 1) mod 30) + 1 in 6/6 kills.
  - inferred: that is every frame since the last 1 s fragment boundary. With real PTS the boundary is in time, not frames, and the real-PTS losses (14-29) are consistent with it.
  - inferred: the 1 s loss depends on where the kill falls in the fragment, so the single 600-frame kill above is one sample.
- measured: in 48/48 kills PyAV raised no demux error on the killed file, and `recover()`'s matched prefix equals the byte-exact frames on disk (GF02 `partB[].killed_pyav.demux_error`, `recover.matched_prefix`).
- measured: killed fMP4 files (both fragment sizes) give a cv2 count equal to the frames on disk in 24/24. Killed MKV files (both variants, both PTS modes) give −2.767e17 and a wrong cv2 POS_FRAMES seek in 24/24 (GF02 `partB[].killed_cv2`).
- These kills used `flush_packets=1` and were paced; the 600-frame kill above was neither. The two are not directly comparable.

**Other crash results (background)**

- The Python raw+sidecar writer kept 409 of 600 frames, all exact (measured, Python writer: `truncation.json` `raw_sidecar`).
- Truncating files to 50% and 90% of their bytes keeps 445 and 801-802 exact frames in every container except plain MP4/MOV, which become unreadable (measured, PyAV 18 - background: `truncation.json` `truncated`).
- A 1,154,485,550 B OpenDML AVI (6000 frames, 1 `AVIX` RIFF) reads 6000/6000 byte-exact in PyAV. OpenCV seeks 10/10, MSMF reads 6000 and FreeMoCap counts 6000 (measured, PyAV 18 - background: `truncation.json` `large_avi`).
- The crash_resilience topic measures per-frame flush and fsync policies and repair of killed files (see its FINDINGS).

### 2.6 Chromium / Electron (G8 cross-check)

Measured on PyAV 18-written files - background: `electron_check.json`.

- **`<video>`.** Neither Electron 35.7.5 (Chrome 134.0.6998.205) nor Electron 45.2.3 (Chrome 156.0.8078.80) plays MJPEG from any container:
  - MKV, MP4, fMP4 1 s and MOV fail with error 4 `DEMUXER_ERROR_NO_SUPPORTED_STREAMS`;
  - AVI, NUT and raw fail with `DEMUXER_ERROR_COULD_NOT_OPEN`;
  - the VP9 WebM control plays and seeks.
- **MIME checks.** `canPlayType` returns "" for every MJPEG MIME tested, and MSE `isTypeSupported` returns false. `video/x-matroska` alone gives "maybe", in 45.2.3 only.
- **Single frames.** `<img>`, `createImageBitmap` and `ImageDecoder` decode every test JPEG in both versions: original, DHT-stripped, generic with extra bytes, and rotated 4:4:0 (ImageDecoder reports I422, or BGRX for 4:4:0).
  - The evidence is correct dimensions and a mean pixel value. Stripped and original give the same mean (128.16276).
  - Pixels were not compared against a reference decoder.
- inferred: the failure comes from the codec, not the muxer version, so PyAV 19 files should fail the same way. Not re-run.

### 2.7 Lossless rotation (Rust parity, functional)

Measured: `rotation.json`, libjpeg-turbo 3.2.1, not PyAV-dependent. The cost is in §2.9.4.

- libjpeg-turbo 3.2.1 `tj3Transform` through ctypes (options 0, the call Rust makes) is DCT-exact in 228 of 228 frame × rotation cases.
- jpegtran gives the same bytes in 228/228.
- The control (rotating the block grid without permuting coefficients) matches 0/228, so the test can fail.
- RGB max abs diff is ≤ 5. rot90/270 output is 4:4:0 (TJSAMP 4).
- The Rust-equivalent legacy `tjTransform` returns 0 (rotated) on 195 of 228 cases. All 33 generic_1080p cases return -1 (`tj3_warnings` 33). Every c930e and c922 set has `tj3_warnings` 0.
- The Rust code keeps the output only when `ret == 0` (code: `git show upstream/sfn26:skellycam-rust/src/camera_group/jpeg_transform.rs:108`, `if ret == 0 && !dst_buf.is_null()`).
- inferred, conditional: with libjpeg-turbo 3.2.1, that check would record a rotated generic camera unrotated, with no error.
  - The Rust build downloads turbojpeg "from the latest GitHub Release on the `jonmatthis/openpnp-capture` fork" (code: `git show upstream/sfn26:skellycam-rust/build.rs:1-6`).
  - That library version is not pinned, so the Rust behaviour is NOT VERIFIED.

### 2.8 Version bump

- Going from PyAV 18 to PyAV 19.0.2 changes no passthrough result: write success, byte-exactness, timestamp errors, WebM refusal, AVI VFR EINVAL, kill survivors and template loss are all the same (measured: `version_bump.json`, `pyav19_recheck.json`, `verify_method_killed_readers.json`).
- Output sizes differ by 0-3 B (§2.1).
- OpenCV: PyAV 18 + OpenCV 4.12 and PyAV 19 + OpenCV 5.0.0.93 gave the same counts and seeks on all 26 c930e rows (measured: `version_bump.json` vs `mux_matrix.json`). The writer changed too, so this does not isolate OpenCV.

### 2.9 Timed results from the quiet run (G5 throughput, open cost, rotation cost)

**Run conditions** (measured: `results/BENCH_RUN_2300_LOG.jsonl`, the lines for orders 17, 29, 59 and 60; `results/jpeg_passthrough/BENCH.md` §1)
- All four items finished with status ok and exit 0. Each had `affinity` "pcores" (pinned to the 8 P-cores = 16 logical CPUs), no Defender scan event during the item, and `load_over_15pct` false in the 10 s before it.
- Local times on 2026-11-10: MUX-D 00:51:28-00:52:15, OPEN 01:18:31-01:18:57, MUX-F 04:32:09-04:33:08, ROT 04:33:19-04:35:46.
- Every item carries the flag "leftover processes after item (listed, not killed)". The summary explains that the list held only the session's own monitoring shells and no bench process (source: `results/BENCH_RUN_2300_SUMMARY.md` line 38).
- Before ROT, SearchIndexer.exe used 9.36 CPU-s in the 10 s window, with mean total CPU 6.03%. This was the busiest pre-item window of the four, but below the 15% load flag (measured: log, order 60 `load_before`).
- MsMpEng (Defender real-time) CPU-s during each item: 32.44 for MUX-D (47 s item), 34.78 for MUX-F (59 s), 1.23 for OPEN and 4.75 for ROT (measured: same log, `msmpeng_cpu_s_during_item`). These totals cover the whole item (all 13 writers × 2 sizes for the mux items), not single writers.

#### 2.9.1 Mux cost per frame (MUX-D, MUX-F)

Method (code: `scripts/jpeg_passthrough/bench_mux.py`):
- Each (container, size, rep) runs in a fresh worker process, one after another. 3000 frames are held in RAM. VFR timestamps come from real c930e intervals, looped and floored to µs (`:47-51`, `:150`; `jp_common.py:59-69`).
- `wall_us_per_frame_mux` = `perf_counter` across the mux loop / 3000 (`:98-107`, `:114`). Close is timed separately. With `--fsync`, the close includes a reopen and `os.fsync` (`:108-113`). The in-loop code is the same in both runs (`:98-113`).
- 720p = c930e_720p_flash (891 frames looped, 55,341 B/frame). 1080p = c922_1080p (19 frames looped, 192,382 B/frame) (computed: `payload_bytes` / 3000 in MUX-D).
- Baselines (`:54-80`):
  - `pkt_only`: packet creation only;
  - `raw_sidecar`: a Python file write plus a 20-byte index entry, with close timed separately;
  - `jpg_folder`: one open/write/close per frame inside the timed loop.
- `fmp4_*_tb_us` set the stream time base to 1/1e6 (`bench_mux.py:94-95`; `jp_io.py:47-48`). `mp4`, `mov` and `nut` keep the muxer default stream time base, so MP4/MOV/NUT at 1/1e6 were **not** benched (`jp_io.py:31-49`; `--containers` list in MUX-D `meta.args`).
- Completeness: each file has 130 runs (13 containers × 2 sizes × 5 reps), none with an `error` key, and `frames` is 3000 in every run (measured: MUX-D, MUX-F `runs`).

Findings (wall µs/frame, median (min-max) of 5 reps; MUX-D unless stated; single stream, Gerald P-core):
- measured: every libav container costs 16.1-20.8 µs/frame at 720p and 46.4-60.2 µs/frame at 1080p (MUX-D; full table in §3.3).
- measured: **libav container medians reproduce across the two runs within 3%**: -2.7% to +0.3% at 720p and -2.3% to +0.2% at 1080p, MUX-F vs MUX-D. Examples: MKV 19.04 / 19.05, MP4 17.87 / 17.91, fMP4 1 s at 1/1e6 20.78 / 20.86 (720p). The order of the containers is the same in both runs. So the container differences are real, but small in absolute terms.
  - computed: the largest libav spread is 4.63 µs/frame at 720p (AVI 16.15 to fMP4 1 s at 1/1e6 20.78), about 0.14 ms/s at 30 fps. At 1080p it is 13.88 µs/frame (AVI 46.36 to fMP4 1 s at 1/1e6 60.24), about 0.42 ms/s at 30 fps.
- measured: **the large swings between runs are confined to the two Python writers.** `raw_sidecar` at 720p: 19.97 (19.35-20.60) in MUX-D and 16.32 (16.17-17.11) in MUX-F, 18% lower. `jpg_folder` at 720p: 13% lower in MUX-F. At 1080p both moved by less than 4%. The cause is unknown (NOT VERIFIED).
- measured: fMP4 at 1/1e6 costs the same as fMP4 at the default time base (MUX-D, 720p):
  - 1 s fragments: 20.78 (20.56-20.94) vs 20.69 (20.47-21.36);
  - per-frame fragments: 20.41 (20.04-20.56) vs 20.09 (19.60-20.73).
- measured: at 1080p, fMP4 1 s fragments are the most expensive libav container: 60.24 (59.03-62.29) µs/frame at 1/1e6, against 51.22 (50.95-53.26) for plain MP4 and 55.20 (54.25-56.67) for MKV (MUX-D).
- measured: at 1080p, `raw_sidecar` is the cheapest writer: 42.98 (42.09-43.54) in MUX-D and 41.84 (41.71-42.30) in MUX-F.
- measured: a folder of JPEGs costs 217.93 (190.72-298.44) µs/frame at 720p and 232.53 (224.89-250.99) at 1080p (MUX-D). In MUX-F, where it is not fsynced either (`bench_mux.py:72-79`), it costs 190.42 (187.49-215.52) and 223.43 (219.02-244.54).
  - computed: that is 11.4× MKV at 720p and 4.2× at 1080p, or 10.5× and 3.9× fMP4 1 s at 1/1e6.
  - measured elsewhere: write_throughput measured Defender per writer at 16 × 1080p60. MsMpEng used 26.8 s (25.9-29.3) per 30 s cell for the folder writer, against 1.2-1.5 s for the container writers, which is the idle level (`results/write_throughput/BENCH.md` line 221). This bench only has item-level MsMpEng totals (see Run conditions above). Defender stays ON, so this is part of the real cost on a default Windows machine.
- computed (single stream, wall time): at 30 fps, fMP4 1 s at 1/1e6 uses 0.62 ms/s per camera at 720p and 1.81 ms/s at 1080p. A folder of JPEGs uses 6.5 and 7.0 ms/s.
  - CPU agrees here: the MUX-D `cpu_us_per_frame_mux` median for 1080p fMP4 1 s at 1/1e6 is 62.5 µs/frame, about 1.9 ms/s at 30 fps.
- **Multi-camera cost is higher than single-stream arithmetic predicts.** write_throughput measured the p50 per write call at 16 × 1080p60 (thread per camera) in the same quiet run: files 2.111 ms, append 0.553 ms, mkv_flush 0.808 ms, fmp4_frame_flush 0.853 ms (measured: `results/write_throughput/BENCH.md` line 220).
  - computed: that is 9× (folder) to 15× (fMP4 per-frame) the single-stream µs/frame here, and the folder/container ratio falls to about 2.5×.
  - inferred: those writers differ from this bench (for example, fmp4_frame_flush flushes every frame), so the ratio is not a pure contention factor. Do not scale this topic's numbers linearly with camera count.
- measured: CPU µs/frame values are multiples of 5.21 µs (15.625 ms / 3000 frames) in all 260 runs, so CPU differences under about 5 µs/frame are not resolved. This file compares wall time (MUX-D, MUX-F `cpu_us_per_frame_mux`).

#### 2.9.2 Close cost, with and without a flush to disk (MUX-D, MUX-F)

- measured: close without fsync takes under 1 ms for every container except fMP4 1 s fragments at 1080p: 1.54 ms (1.41-1.71) at the default time base and 1.54 (1.41-1.67) at 1/1e6 (MUX-D `wall_ms_close`).
- measured: close plus a whole-file FlushFileBuffers takes 42.9-81.9 ms (medians) for the 166 MB 720p files and 139.2-156.9 ms for the 577 MB 1080p files (MUX-F `wall_ms_close`).
  - Single reps reach 255.3 ms (720p `mjpeg_raw_mux`), 389.1 ms (1080p `fmp4_perframe`), 507.8 ms (1080p `raw_sidecar`) and 521.1 ms (1080p `nut`) (MUX-F).
  - fMP4 1 s at 1/1e6: 42.91 (41.02-46.64) ms at 720p and 140.50 (140.22-146.86) ms at 1080p (MUX-F).
- computed: bytes on disk / median close time gives 2.0-4.2 GB/s across writers (2.03 GB/s for 720p `mjpeg_raw_mux` up to 4.15 GB/s for 1080p `mov` and `fmp4_perframe_tb_us`). For fMP4 1 s at 1/1e6 it is 3.87 GB/s (720p) and 4.11 GB/s (1080p) (MUX-F).
- inferred: this is a one-off flush of the whole file at close, not a per-frame durability cost. crash_resilience measures per-frame flush and fsync costs.

#### 2.9.3 Opening and counting a 30-minute file (OPEN)

Method (code: `scripts/jpeg_passthrough/bench_open_long.py`):
- c930e_720p_flash looped to 54,000 frames (30 min at 30 fps), with real intervals looped, written fresh by PyAV 19.0.2 `add_mux_stream`. MP4 variants use stream time base 1/1e6; MKV uses its fixed 1/1000 (`:37-38`, `:59-71`).
- `cv2_open_ms` = `cv2.VideoCapture(path, CAP_FFMPEG)` plus `CAP_PROP_FRAME_COUNT`, with `release()` excluded (`:74-77`). `pyav_open_ms` = `av.open` plus `streams.video[0].frames` (`:79-82`). There is one full demux packet count per file, with no decode (`:89-92`).
- inferred: every open was warm (from the page cache), because each file was read straight after it was written and the script drops no cache (docstring `:15`). Cache residency was not measured. **There is no cold-open number.**
- meta: PyAV 19.0.2, OpenCV 4.12.0, `frames` 54000, `reps` 5, `dry` false (OPEN `meta`).

Findings (median (min-max) of 5 reps, warm):
- measured: fMP4 with per-frame fragments takes 1107.28 ms (1104.80-1111.88) to open and count in OpenCV and 1224.24 ms (1217.30-1228.59) in PyAV (OPEN `files.fmp4_perframe_tb_us`).
- measured: fMP4 with 1 s fragments takes 42.57 ms (41.42-55.10) in OpenCV and 45.69 ms (45.05-47.81) in PyAV (OPEN `files.fmp4_1s_tb_us`).
  - computed: per-frame fragments cost 26× (OpenCV) and 27× (PyAV) as much per open as 1 s fragments.
- measured: a finalized MP4 opens in 2.38 ms (2.33-7.74) in OpenCV and 2.95 ms (2.83-3.56) in PyAV. MKV opens in 0.19 ms (0.19-4.93) and 0.17 ms (0.15-0.32) (OPEN).
- measured: the OpenCV count is exact (54,000) for all three MP4 variants. For MKV it is 53,819, 181 frames short (OPEN `cv2_frame_count`, `count_exact`).
- measured: PyAV `stream.frames` is 0 for both fMP4 variants and MKV. Only the finalized MP4 gives 54,000 (OPEN `pyav_stream_frames`).
- measured: a full PyAV demux finds 54,000 packets in every container. One run each took 486.34 ms (MP4), 547.41 ms (fMP4 1 s), 580.72 ms (MKV) and 2220.53 ms (fMP4 per frame) (OPEN `pyav_demux_packets`, `pyav_demux_count_ms`).
- measured: the first OpenCV rep is the slowest (fMP4 1 s 55.10, MP4 7.74, MKV 4.93 ms), then the times settle (OPEN `cv2_open_ms[0]`).
- **Open cost grows with the number of fragments.**
  - computed: 1107.28 ms / 54,000 fragments is 20.5 µs per fragment (OPEN).
  - A third point comes from python_integration: its per-frame fMP4 with 18,000 frames takes 370.83-378.58 ms to open in cv2, median 371.96 ms, about 20.7 µs per fragment (measured: `results/python_integration/bench/recwriter_quiet1_pyav19.json` `c_open_cost.mp4f.cv2_open_count_first_read_ms`). That writer is different (code: `scripts/python_integration/recwriter.py:52`, `movflags` without `min_frag_duration`), and its timing includes the first read.
  - inferred: the cost per fragment is roughly constant across these points. The mechanism inside the mov demuxer was not checked against FFmpeg source (NOT VERIFIED).
- Related: python_integration's RecordingWriter bench also measures open, count and mid-file seek on a 10-minute file for MKV and fMP4 (`results/python_integration/BENCH.md` §3.3). Read that topic for its numbers.

#### 2.9.4 Lossless rotation cost (ROT)

Method (code: `scripts/jpeg_passthrough/bench_rotate.py:45-61`):
- `tj3Transform` with options 0, called through the ctypes wrapper in `rotate_check.py`, which copies the input and output buffers on each call (BENCH.md §3.2, citing `rotate_check.py:74-92`).
- 1000 frames per (size, op), 5 reps, one thread. 720p = c930e_720p_flash (891 distinct frames, about 49 MB); 1080p = c922_1080p (19 distinct frames, about 3.6 MB, looped).
- libjpeg-turbo 3.2.1 `turbojpeg.dll`, sha256 `3dd7a8a99dd744b4f53d8c8108cca703abe25c99cc526fc6bfc49ce681f975fd` (ROT `meta.lib_sha256`).
- The script raises on hard errors (`bench_rotate.py:53-55`). The wrapper keeps results that come with `TJERR_WARNING` (`rotate_check.py:82-89`). None are expected on these inputs: `rotation.json` `tj3_warnings` is 0 for every c930e and c922 set. The item exited 0.

Findings (wall µs/frame, median (min-max) of 5 reps; ROT `runs`; single stream, Gerald P-core):
- measured: 720p rot90 2138 (2124-2345), rot180 2019 (2008-2023), rot270 2238 (2235-2299).
- measured: 1080p rot90 7211 (7179-7262), rot180 6753 (6668-6829), rot270 8873 (8743-9052).
- The Rust comment says "no quality loss, ~1-2ms per frame" (code: `git show upstream/sfn26:skellycam-rust/src/camera_group/jpeg_transform.rs:3-4`; the figure is on line 4). In this harness that is close to the 720p result (2.0-2.2 ms) but does not hold at 1080p (6.8-8.9 ms).
  - This harness is Python ctypes calling `tj3Transform` 3.2.1. Rust calls the legacy `tjTransform` from an unpinned library (§2.7), so the Rust figure itself is still NOT VERIFIED.
- computed: 1080p rot270 at 30 fps takes 266 ms/s of one logical CPU per camera (about 27% of one pinned, hyper-threaded P-core logical CPU of the i7-14700K), and 532 ms/s at 60 fps. 720p rot270 at 30 fps takes 67 ms/s.

#### 2.9.5 What the timed results confirm or change

- Confirms (no change needed):
  - exact OpenCV counts on fMP4/MP4 at 1/1e6 with real content at 54,000 frames;
  - a wrong MKV count on the looped c930e file (53,819);
  - PyAV `stream.frames` = 0 for fMP4 and MKV (§2.4).
- Resolves these "pending" items from the previous revision's §5: the open cost of 30-minute files, the cost of a PyAV demux count, the mux cost of fMP4 at 1/1e6, and the rotation cost.
- Changes: the fMP4 fragment choice now has a measured open-cost side. A warm open of a 30-minute file takes about 1.1-1.2 s with per-frame fragments, against about 43-46 ms with 1 s fragments (§2.9.3). This weighs against per-frame fragments for long recordings (§4.2).
- The timed data contradicts none of the earlier functional findings. The verifier's functional recheck (not the timed run) narrowed the MKV count finding: the count is exact on c922's real VFR (§2.4).

## 3. Comparison tables

### 3.1 Container properties for camera-JPEG passthrough

PyAV 19.0.2 writer unless marked [18] (measured, PyAV 18 - background). Real VFR PTS unless a row says index PTS.

| Property | Folder .jpg + CSV | raw .mjpeg + sidecar | MKV | MP4 (1/1e6) | fMP4 1 s (1/1e6) | MOV (1/1e6) | AVI (1/fps) | NUT (1/1e6) |
|---|---|---|---|---|---|---|---|---|
| Bytes exact (7 sets) | yes [18] | yes [18] | yes | yes | yes | yes | yes (CFR; VFR 6/7) | yes |
| VFR timestamp error | CSV written, not read back (not tested) | exact in index (ns) [18] | ≤470 µs; frames <1 ms apart share a pts | 0 µs (µs inputs) | 0 µs (µs inputs) | 0 µs (µs inputs) | 14.67 ms; fails if 2 frames land on one tick | 0 µs (µs inputs) |
| OpenCV count exact, c930e VFR | yes [18] | no [18] | no (888 for 891) | yes (stored) | yes (estimated; OpenCV 4.12) | yes | CFR only, yes | no (887) |
| OpenCV count exact, c922 VFR (OpenCV 4.12) | not tested | not tested | yes (893) | not tested | yes (893) | not tested | not tested | not tested |
| OpenCV count exact with gaps (gap60/drop50), real VFR PTS | not tested | not tested | no (888 for 831 / 888 for 874; GF02 + fp the same) | yes | yes (GF02 + fp too) | not tested | not tested | not tested |
| OpenCV count, 54,000-frame real-content file, real VFR PTS | not tested | not tested | no (53,819; GF02 + fp 53,820) | yes | yes (GF02 + fp too) | not tested | not tested | not tested |
| Index PTS + fp (GF02): count / cv2 seek on c930e, gap60, drop50, c922, 54,000 frames | not tested | not tested | exact / 11/11 in all | not tested | exact / 11/11 in all (time base 1/15360) | not tested | not tested | not tested |
| OpenCV seek, c930e (no gaps) | 10/10 [18] | 0/10 [18] | 5/10 (GF02 + fp 2/11) | 10/10 | 10/10 (OpenCV 4.12; GF02 + fp 9/11) | 10/10 | CFR 10/10 | 6/10 |
| OpenCV seek with gaps (gap60 / drop50), real VFR PTS | not tested | not tested | 5/10 / 5/10 (GF02 + fp 2/11 / 1/11) | 5/10 / 7/10 | 5/10 / 7/10 (GF02 + fp 1/11 / 8/11) | not tested | not tested | not tested |
| PyAV timestamp seek, frame identity (full / gap60 / drop50) | n/a | not tested | 35/36, 33/34, 34/35 | 36/36, 34/34, 35/35 | 36/36, 34/34, 35/35 | not tested | not tested | not tested |
| FreeMoCap VideoHelper opens | no [18] | no [18] | yes; real VFR PTS: wrong count with drops or an off-nominal mean rate; index PTS + fp: count and 4/4 reads ok (GF02) | yes [18] | yes; reads match on gap files (4/4), both PTS modes | yes [18] | yes [18] | yes, count short [18] |
| CAP_MSMF reads | yes, CAP_IMAGES [18] | no [18] | partly (888/891 VFR) | no | no | yes | yes | no [18] |
| Complete frames after hard kill at 600, no fp (one sample) | not tested | 409/600 (Python buffered) [18] | 597 | unreadable | 578 | unreadable | 597 | 597 |
| Frames lost per paced kill with fp (GF02, 12 kills, both PTS modes) | not tested | not tested | 1 (0 with an empty packet per frame) | not tested | 1-30 (real 14-29, index 1-30) | not tested | not tested | not tested |
| OpenCV count / read on killed file | - | - | negative / 597 (GF02 + fp: negative in 24/24) | - | 582 / 579 (GF02 + fp: count = frames on disk, 24/24 incl. per-frame) | - | 0 [18] | 595 / 598 |
| Chromium `<video>` | n/a | no [18] | no [18] | no [18] | no [18] | no [18] | no [18] | no [18] |
| Overhead for 891 c930e frames | +CSV | 20 B/frame index [18] | 40,253 B | 11,936 B | 11,738 B | 11,843 B | 27,515 B (CFR) | 26,908 B |
| Mux wall µs/frame 720p / 1080p (MUX-D) | 217.93 / 232.53 | 19.97 / 42.98 | 19.04 / 55.20 | 17.87 / 51.22 (default tb) | 20.78 / 60.24 | 17.97 / 51.30 (default tb) | 16.15 / 46.36 | 17.55 / 47.93 (default tb) |
| Warm open + count, 30-min 720p file, cv2 / PyAV ms (OPEN) | not tested | not tested | 0.19 / 0.17 (count wrong) | 2.38 / 2.95 | 42.57 / 45.69 | not tested | not tested | not tested |
| Files per camera-minute at 30 fps (arithmetic) | 1,801 | 2 | 1 | 1 | 1 | 1 | 1 | 1 |

**Sources:** `pyav19_recheck.json`, `pyav19_fmp4_tb_us_readers.json`, `version_bump.json` (OpenCV 5.0.0.93, c930e rows except fMP4 1/1e6), `verify_method_reader.json`, `verify_method2_mkv_count.json`, `verify_method_killed_readers.json`, `pyav19_seek_ts_check.json`, MUX-D and OPEN. GF02 entries from GF02 `partA[]`, `partB[]` and `GF02_partA_long_read.json` (11 identity targets; not directly comparable with this topic's 10 sequential-decode targets, §2.4). [18] rows come from `mux_matrix.json`, `truncation.json` and `electron_check.json`. "default tb" = the mux bench used the muxer default stream time base for that container, not 1/1e6 (§2.9.1). Mux medians: libav containers reproduce within 3% across runs; the Python writers do not (§2.9.1).

### 3.2 fMP4 fragment choice (c930e_720p_flash, PyAV 19.0.2, time base 1/1e6, real PTS unless stated)

| | fMP4 1 s fragments | fMP4 per-frame fragments | Source |
|---|---|---|---|
| Overhead (891 frames) | 11,738 B | 117,521 B | `pyav19_recheck.json` |
| Overhead per frame, 3000 frames, 720p (computed) | 12.4 B (0.02% of payload) | 131.3 B (0.24%) | MUX-D `bytes_on_disk` − `payload_bytes` |
| Mux wall µs/frame, 720p / 1080p | 20.78 / 60.24 | 20.41 / 56.26 | MUX-D |
| Close ms without / with fsync, 1080p | 1.54 / 140.50 | 0.29 / 139.31 | MUX-D, MUX-F |
| Complete frames after one kill at 600, no fp | 578 (loses the open fragment, inferred) | 596 | `pyav19_recheck.json` |
| Frames lost per paced kill with fp (12 kills, both PTS modes) | 1-30 (real 14-29, index 1-30) | 1 in 12/12 | GF02 `partB[].lost_vs_sidecar` |
| OpenCV count / frames read on the killed file, no fp | 582 / 579 | 597 / 596 | `verify_method_killed_readers.json` |
| FreeMoCap read of the last counted frame, killed file, no fp | fails (581) | fails (596) | `verify_method_killed_readers.json` |
| Timestamp error | 0 µs | 0 µs | `pyav19_recheck.json` |
| OpenCV 4.12 count / seek, no gaps | 891 / 10/10 | 891 / 10/10 | `pyav19_fmp4_tb_us_readers.json` |
| OpenCV 4.12 count / seek, gap60 | 831 / 5/10 | 831 / 5/10 | `verify_method_reader.json` |
| GF02 + fp, OpenCV seek (11 identity targets), c930e full / gap60 / drop50 | real 9/11, 1/11, 8/11; index (1/15360) 11/11 | real 9/11, 1/11, 8/11; index (1/15360) 11/11 | GF02 `partA[]` |
| PyAV timestamp seek, frame identity (full, gap60, drop50) | 36/36, 34/34, 35/35 | 36/36, 34/34, 35/35 | `pyav19_seek_ts_check.json` |
| Warm open + count, 30-min file: cv2 / PyAV | 42.57 / 45.69 ms | **1107.28 / 1224.24 ms** | OPEN |
| Full PyAV demux count, 30-min file (1 run) | 547.41 ms | 2220.53 ms | OPEN |
| cv2 count, 30-min file | 54,000 (exact) | 54,000 (exact) | OPEN |

### 3.3 Mux cost per container, wall µs/frame and close ms (median (min-max), 5 reps)

| container | 720p wall, default (MUX-D) | 720p close ms, fsync (MUX-F) | 1080p wall, default (MUX-D) | 1080p close ms, fsync (MUX-F) | container B/frame 720p / 1080p (computed) |
|---|---|---|---|---|---|
| pkt_only (no file) | 0.68 (0.68-0.70) | - | 0.66 (0.66-0.66) | - | - |
| mkv | 19.04 (18.58-19.31) | 45.40 (41.78-57.90) | 55.20 (54.25-56.67) | 145.58 (141.41-147.50) | 45.7 / 45.8 |
| mp4 (default tb) | 17.87 (17.43-18.31) | 45.02 (39.63-54.60) | 51.22 (50.95-53.26) | 144.59 (137.18-146.63) | 11.8 / 12.1 |
| fmp4_1s (default tb) | 20.69 (20.47-21.36) | 45.08 (40.72-54.65) | 59.92 (59.44-60.60) | 141.87 (139.67-149.63) | 12.4 / 12.4 |
| fmp4_perframe (default tb) | 20.09 (19.60-20.73) | 45.48 (42.60-49.00) | 55.68 (55.40-57.48) | 145.92 (138.33-389.10) | 131.3 / 131.3 |
| fmp4_1s_tb_us | 20.78 (20.56-20.94) | 42.91 (41.02-46.64) | 60.24 (59.03-62.29) | 140.50 (140.22-146.86) | 12.4 / 12.4 |
| fmp4_perframe_tb_us | 20.41 (20.04-20.56) | 44.36 (40.43-59.96) | 56.26 (55.50-61.03) | 139.31 (137.87-146.57) | 131.3 / 131.3 |
| mov (default tb) | 17.97 (17.78-18.44) | 48.63 (39.67-51.46) | 51.30 (50.68-52.15) | 139.20 (138.49-335.97) | 11.8 / 12.0 |
| avi_tb_rate (1/30, CFR) | 16.15 (16.04-16.88) | 60.46 (51.68-151.14) | 46.36 (45.58-47.94) | 154.90 (139.63-165.42) | 26.4 / 26.6 |
| nut (default tb) | 17.55 (17.23-17.65) | 52.36 (51.75-54.56) | 47.93 (47.28-48.16) | 155.41 (152.91-521.06) | 28.9 / 33.8 |
| mjpeg_raw_mux | 16.51 (16.25-17.09) | 81.92 (53.18-255.29) | 46.40 (45.96-49.12) | 156.92 (152.70-162.84) | 0 / 0 |
| raw_sidecar | 19.97 (19.35-20.60) | 66.31 (56.86-68.90) | 42.98 (42.09-43.54) | 145.38 (143.18-507.77) | 20.0 / 20.0 (index) |
| jpg_folder (never fsynced) | 217.93 (190.72-298.44) | 0.00 (no fsync) | 232.53 (224.89-250.99) | 0.00 (no fsync) | 0 / 0 |

Files: MUX-D = `results/jpeg_passthrough/bench/bench_mux_default_pyav19_20261110T055215Z.json`; MUX-F = `results/jpeg_passthrough/bench/bench_mux_fsync_pyav19_20261110T093308Z.json`. Single stream, P-cores, Defender ON, page cache. The MUX-F in-loop wall values are in BENCH.md §3.1. They are within 3% of MUX-D for every libav container.

### 3.4 Lossless rotation cost (ROT, wall µs/frame, median (min-max))

| size | rot90 | rot180 | rot270 |
|---|---|---|---|
| 720p (c930e) | 2138 (2124-2345) | 2019 (2008-2023) | 2238 (2235-2299) |
| 1080p (c922) | 7211 (7179-7262) | 6753 (6668-6829) | 8873 (8743-9052) |

File: `results/jpeg_passthrough/bench/bench_rotate_20261110T093546Z.json`. Single stream, Gerald P-core.

## 4. Implications for the plan

1. **PyAV 19.0.2 alone meets G1** (§2.1).
   - Use `add_mux_stream("mjpeg", rate, width=w, height=h)` and `av.Packet(bytes)`.
   - Always pass width and height. Leave `is_keyframe` unset. Do not use `add_stream_from_template`.
   - The payload was checked verbatim without FFmpeg.
   - Quality: passthrough keeps the camera's own JPEG. Its quantisation is near the q94 that defines target A, but it is not a measured point on the A/B scale, and the camera files are about half the size of q94 on YUY2 (header; HANDOFF §1.1).
2. **fMP4 with 1 s fragments is a container candidate** (`movflags frag_keyframe+empty_moov+default_base_moof`, `min_frag_duration 1000000`; with real PTS, `st.time_base = Fraction(1, 1_000_000)`).
   - Other topics disagree. write_throughput lost 33 and 62 acked frames per kill with 1 s fragments (measured: `results/write_throughput/functional/functional_results_av19.0.2.md:45`), and 46 and 5 with `flush_packets=1` (measured: `results/write_throughput/functional/functional_results_av19.0.2_gapfill.md:26`). This topic lost 22 at its one kill (§2.5; computed 600 − 578).
   - These kill tests are not directly comparable: WT is 720p60 paced, TerminateProcess; JP is one unpaced `os._exit(1)` after 600 frames, no fp (source: `results/crash_resilience/gapfill/GF01_container_decision_table.md:33-36`). Cross-topic evidence: `GF01_container_decision_table.md`.

   In the tests it is all of the following (§2.3-§2.5, §2.9, table 3.2):
   - byte-exact;
   - with real PTS at 1/1e6, keeps VFR timestamps exact at 1 µs;
   - gives an exact OpenCV frame count, with dropped frames and on a real-content 54,000-frame file (re-measured with `flush_packets=1`: real PTS at 1/1e6 and index PTS at 1/15360; GF02; §2.4);
   - returns the right frames to FreeMoCap's forward reads;
   - lands on the right frame with a PyAV timestamp seek;
   - stays readable by PyAV/ffprobe after a kill;
   - opens a 30-minute file in about 43-46 ms warm (§2.9.3).

   Qualifications from GF02 (crash_resilience gap-fill):
   - measured: with `flush_packets=1`, 1 s fragments lost 1-30 acknowledged frames per live paced kill (real PTS 14-29, median 23; index PTS 1-30, median 14; 12 kills). fMP4 per-frame + fp and MKV + fp each lost 1 frame in 12/12 kills (§2.5).
   - measured: with real PTS, OpenCV POS_FRAMES seeks still miss on fMP4: gap60 1/11, drop50 8/11, c930e full 9/11. With index PTS they are 11/11 (§2.4).

   **fMP4 with per-frame fragments meets every point except warm open time.** The choice between the two rests on:
   - warm open cost of a 30-minute file: 1.1-1.2 s for per-frame fragments, 26-27× the 1 s fragments (cold opens not measured);
   - container overhead: 131.3 vs 12.4 B/frame;
   - against these, frames lost at a kill (GF02, §2.5):
     - measured: with `flush_packets=1`, per-frame fragments lost 1 frame per paced kill (12/12, GF02);
     - 1 s fragments with index PTS lost everything since the last 1 s boundary (computed, 6/6); with real PTS they lost 14-29 frames, consistent with it (inferred);
     - without fp, at this topic's one unpaced kill, per-frame fragments lost 4 of 600 and 1 s fragments 22 (computed: 600 − 596, 600 − 578; `pyav19_recheck.json` `C_killed`).

   inferred: the sidecar (point 6) recovers timing for frames lost in the open fragment only if those frames reached the disk. So the crash trade-off belongs with the crash_resilience topic's flush policy.
3. **The wrapper hardly matters for single-stream write throughput; compatibility decides (G5).**
   - measured: libav container medians reproduce across runs within 3%, so their differences are real (§2.9.1).
   - computed: the differences are small. The largest libav spread is 4.6 µs/frame at 720p (about 0.14 ms/s at 30 fps) and 13.9 µs/frame at 1080p (about 0.42 ms/s).
   - measured: fMP4 at 1/1e6 costs no more than at the default time base.
   - computed: fMP4 1 s at 1/1e6 takes about 1.8 ms/s of wall time per 1080p30 camera (about 0.2% of one CPU). This is single stream on a Gerald P-core. The CPU median agrees (62.5 µs/frame, §2.9.1). It does not cover E-cores or the older CPUs in the hardware target.
   - inferred: this data does not justify giving up compatibility for throughput. Multi-camera cost is 9-15× higher per write in write_throughput (§2.9.1), so read that topic for the multi-camera budget.
4. **A folder of JPEGs is the expensive and incompatible option** (§2.4, §2.9.1).
   - It costs 217.93 / 232.53 µs/frame (720p / 1080p), 4-11× a container.
   - FreeMoCap cannot open it, and it means 1,801 files per camera-minute.
   - Defender real-time scanning is part of that cost. write_throughput measured 26.8 CPU-s per 30 s cell for the folder writer vs 1.2-1.5 for the container writers (measured: `results/write_throughput/BENCH.md` line 221). This topic has only item-level Defender totals.
5. **Random access must seek by timestamp from the per-frame sidecar, with PyAV.**
   - measured: with real VFR PTS, OpenCV `CAP_PROP_POS_FRAMES` seeks are not reliable. With gaps, this topic's 10 targets gave 5/10 (gap60) and 7/10 (drop50) for fMP4 1 s, fMP4 per-frame and MP4, and 5/10 and 5/10 for MKV. GF02's 11 identity targets (fp) gave fMP4 1/11 and 8/11, and 9/11 on gap-free c930e, where this topic's targets gave 10/10 (§2.4).
   - measured: with index PTS, GF02 POS_FRAMES seeks were 11/11 in MKV and fMP4 on every input, including gap60, drop50 and 54,000 frames (§2.4).
   - inferred: with index PTS, a sidecar still maps capture time to frame index, because the container timeline hides drops.
   - inferred: this matters for UI scrubbing and for any analysis that seeks (G9).
6. **Keep a per-frame timestamp sidecar whatever the container.**
   - OpenCV miscounts killed files: fMP4 +1 to +3, NUT -3, MKV negative. FreeMoCap fails on the last counted frame of killed fMP4 (§2.5). FreeMoCap trusts `CAP_PROP_FRAME_COUNT` (§2.4).
   - Counting by a full PyAV demux takes 0.49-0.58 s per 30-minute file for MP4, fMP4 1 s and MKV, and 2.22 s for fMP4 per-frame, warm (§2.9.3).
   - measured elsewhere: a sidecar index read is much cheaper. For 18,000 frames, write_throughput measured 0.016 s for the append index read against demux passes of 0.233 s (mkv_flush) and 0.638 s (fmp4_frame_flush) (`results/write_throughput/BENCH.md` line 213). inferred: the sidecar also covers killed files.
   - On recovery, trust only frames that the sidecar records as complete, or check that each packet ends with EOI (inferred). Otherwise the cut last frame is returned silently (§2.5).
7. **Avoid plain MP4/MOV as the recording format.** A killed file is unreadable (§2.5).
   - inferred: a finalized MP4 remains a good finalize/remux target. It opens in 2.38 ms and is the only container with PyAV `stream.frames` filled (§2.9.3).
8. **Rule out these containers for FreeMoCap-compatible recordings written with real VFR PTS:**
   - MKV, for three reasons, all under real VFR PTS (§2.3, §2.4, §2.9.3):
     - its 1 ms grid merges frames less than 1 ms apart;
     - its OpenCV count is wrong whenever frames are dropped (gap60, drop50) or the mean rate is off nominal (c930e at 30.10 fps, including 53,819 for 54,000 on a 30-minute file). It was exact on c922's real VFR, but real recordings drop frames;
     - it opens fastest, but the count it gives FreeMoCap cannot be trusted.

     With index (CFR) PTS these reasons do not apply (see GF01 §2.2):
     - measured (GF02, §2.4): index-PTS MKV + fp gives count = written, 11/11 POS_FRAMES seeks and FreeMoCap ok on c930e full (891), gap60 (831), drop50 (874), c922 (893) and 54,000 frames. Index PTS with dropped frames is therefore tested, and exact (the container timeline hides the drop; capture times come only from the sidecar, inferred).
     - measured (other topic): python_integration counted index-PTS MKV correctly on 7/7 sets without drops, and 18,000/18,000 on an ideal-PTS file (`results/python_integration/FINDINGS.md:110`, `:283`; `results/python_integration/bench/recwriter_quiet1_pyav19.json` `c_open_cost.mkv.cv2_frame_count_prop`).
     - code: with real PTS, recwriter bumps a colliding pts by 1 tick and flags it, keeping the exact ns time in the sidecar (`scripts/python_integration/recwriter.py:46`, `:136`).
     - measured: 1 bump per real-PTS MKV on c930e-derived inputs (6 files: c930e full, gap60, drop50, each MKV + fp and MKV + fp + empty; sidecar `FLAG_PTS_ADJUSTED` on frame 82, pts 2705); no PyAV or cv2 seek target hit frame 82 (`step3_gf02_sidecar_flags.json`; targets 0, 89, …, 890 in GF02 `partA[].cv2_seek`, `GF02_partA_write.json` `pyav_seek`). A seek to a bumped frame is therefore not tested.
     - measured: the real-PTS 54,000-frame MKV has 61 bumped frames (every 890th frame of the c930e loop, from frame 82), and none of its 11 seek targets is a bumped frame (`step3_gf02_sidecar_flags.json` `L_long_mkv_fp_real`). `GF02_partA_long_write.json` does not record `pts_adjusted`.
     - inferred: with exact times in a sidecar (`results/python_integration/FINDINGS.md:405`), the 1 ms grid no longer carries timing.
     - measured (GF02, §2.5): a killed MKV still reports a cv2 count of −2.767e17 in both PTS modes until `recover()`. After `recover()`, index-PTS MKV counts and seeks correctly (12/12), but real-PTS MKV comes back with `r_frame_rate` 125/2, cv2 fps 62.5 and about 2.1× the frame count (12/12; `GF02_recovered_rates.txt`, GF02 `partB[].recovered_cv2`).
     - In short: MKV with real-timestamp PTS is ruled out for FreeMoCap (count wrong with drops or rate drift); MKV with index PTS plus a sidecar gave exact counts and seeks (GF02).

     crash_resilience evaluates MKV for crash safety; that is a separate trade-off.
   - NUT: the count is always short (§2.4).
   - AVI: VFR is rounded to the time base and refused when two frames land on one tick, and the default time base is 1/600 (§2.3).
   - raw `.mjpeg`: no timestamps and a garbage count (§2.3, §2.4).
   - WebM: refuses MJPEG (§2.1).
9. **Flush cost at stop is bounded.** A whole-file fsync at close of a 100 s single-camera fMP4 1 s file takes about 43 ms (720p, 166 MB) to 141 ms (1080p, 577 MB). Single outliers on other writers reach about 0.5 s (§2.9.2). inferred: if the plan fsyncs at stop, budget for it per camera file. Per-frame durability is a crash_resilience decision.
10. **The container choice cannot settle G8/G9.** Chromium plays MJPEG from no container (§2.6). Playback needs per-frame JPEG decode in the renderer or a proxy encode (chromium_codecs, chromium_sync_scrub and intra_playback topics).
11. **Rotation, if kept, is expensive at 1080p.**
    - Cost (single stream, Gerald P-core): 2.0-2.2 ms/frame at 720p and 6.8-8.9 ms/frame at 1080p through ctypes `tj3Transform`. For rot270 that is about 27% of one logical CPU per 1080p30 camera (§2.9.4). Older CPUs in the hardware target were not measured.
    - Port `tj3Transform` with ctypes and accept outputs that come with `TJERR_WARNING`. Do not copy Rust's `ret == 0` check (§2.7).
    - For 4:2:0 or odd-size cameras, add `TJXOPT_PERFECT` or `TRIM` (inferred; NOTES.md §8 cites `turbojpeg.h:1130-1142`).
    - inferred, untested: storing frames unrotated, recording the rotation in the sidecar and rotating at read or display time would take this cost off the record path and keep G1 byte-exactness.
12. **PyAV upgrade.** Going from PyAV 18 to 19 brings no passthrough gain or loss (§2.8). The decision rests on other topics.

## 5. Run flags and caveats that apply to this topic

From `results/BENCH_RUN_2300_SUMMARY.md` §3 and this topic's JSONs:

- **P-cores only.** All four items were pinned to the 8 P-cores = 16 logical CPUs (measured: `BENCH_RUN_2300_LOG.jsonl` `affinity` "pcores").
  - The JSONs record `cpu_count` 28 because `os.cpu_count()` ignores affinity.
  - The JP JSONs record no per-process affinity, so there is no record of whether it stayed at 16 CPUs.
  - The libx265 affinity widening (summary flag 2) concerns intra_compare items 1-3, not these items.
- **Single stream, one camera per process, workers one after another.** These numbers contain no multi-camera contention (code: `bench_mux.py:146-150`). write_throughput measured 9-15× higher per-write latency at 16 × 1080p60 (§2.9.1).
- **CPU timer granularity 15.625 ms** (summary flag 11). Mux CPU µs/frame moves in steps of 5.21 µs, and close CPU ms in steps of 15.6 ms (measured: all 260 runs in MUX-D and MUX-F). Compare wall times only. ROT CPU steps are 15.6 µs/frame, small next to 2-9 ms.
- **Defender real-time ON, not changed.** MsMpEng used 32.44 and 34.78 CPU-s during the two mux items (measured: run log). These are item-level totals.
  - The per-writer attribution, folder 26.8 vs containers 1.2-1.5 CPU-s per 30 s cell, comes from write_throughput (§2.9.1).
  - inferred: Defender likely also affects the fsync close.
  - It is part of the real cost on a default Windows install. No Defender scan event fell inside any item.
- **Page cache throughout.** The default mux runs never wait for the disk inside the timed loop, and the fsync run flushes once at close. OPEN read every file straight after writing it, so the opens were warm (inferred, not measured; code: `bench_open_long.py:15`, `:72-85`). **No cold-open number exists.**
- **Run-to-run variation.**
  - measured: libav container medians reproduce within 3% between MUX-D and MUX-F, so their differences are real but small (§2.9.1).
  - The large swings are in the Python writers only: raw_sidecar 720p 19.97 vs 16.32 µs/frame, jpg_folder 720p 217.93 vs 190.42 (measured: MUX-D vs MUX-F). Their cause is unknown.
- **ROT confounders.**
  - Before ROT, SearchIndexer.exe used 9.36 CPU-s in 10 s, the busiest pre-item window of the four, though not load-flagged (measured: log order 60).
  - The 1080p input is 19 distinct frames (about 3.6 MB, likely cache-resident); the 720p input is 891 frames (about 49 MB). Neither matches a live camera stream.
  - inferred: the narrow min-max spreads suggest the effect is small.
- **Leftover-process flag** on all four items: harmless per the summary (only the session's own monitoring shells; `BENCH_RUN_2300_SUMMARY.md` line 38).
- **Write-latency flag (summary flag 7)** concerns write_throughput: tonight's per-write latencies there are higher than in the contaminated daytime run. This topic had no earlier timed numbers, so nothing here replaces an older figure.
- **Looped payloads.** The 1080p mux and rotate benches use 19 distinct c922 frames; OPEN loops 891 c930e frames to 54,000. Whether rotation cost depends on content was not tested.
- **MP4, MOV and NUT were benched at the muxer default stream time base**, not 1/1e6 (code: `bench_mux.py:87-95`; `jp_io.py:31-49`). Only the fMP4 mux rows and the OPEN MP4 rows are at 1/1e6.
- **`jpg_folder` is never fsynced** (code: `bench_mux.py:72-79`), so its MUX-F row is a second default run.
- **Rotation is timed through Python ctypes**, with two buffer copies per call, on libjpeg-turbo 3.2.1. It is not Rust's `tjTransform` on its unpinned library.
- **Flags that do not apply here:** the NVENC 12-session limit, nvJPEG missing target A, the WebCodecs hidden errors and GPU memory growth, the N=8 `<video>` stalls, and the missing lossless check in uncompressed_intra. Passthrough uses none of those code paths.
- **GF02 results** (cross-topic, functional, no timing) were made by crash_resilience; this topic only re-read them and scanned the GF02 sidecars read-only.

## 6. Not tested / limits / NOT VERIFIED

**Timed questions not covered**

- Cold-open time of long files (all OPEN reads were warm).
- Open cost at 1080p, and for 60-minute or longer files.
- Mux cost of MP4, MOV and NUT at stream time base 1/1e6 (`mp4_tb_us`, `mov_tb_us` and `nut_tb_us` were not in the mux list).
- Multi-camera mux contention in the passthrough bench (write_throughput covers multi-camera writing with its own writers).
- Per-frame durability cost (crash_resilience covers it).
- Rotation through the Rust call, multi-threaded rotation, and rotation on 4:2:0 or odd-size cameras.
- Any machine other than Gerald (no E-core-only or older 2020+ CPU), and any OS other than Windows 11.

**Not re-run on PyAV 19.0.2 (background only)**

- OpenCV 4.12 and FreeMoCap reads of all 7 sets in MP4/MOV/AVI/NUT. The c930e set, its gap/drop variants and the c922 MKV/fMP4 counts were re-run (§2.4).
- `ffmpeg -c:v copy` extraction.
- Reads of byte-truncated files, and the >1 GiB AVI.
- OpenCV/FreeMoCap on killed AVI and raw files.
- PyAV 19 decode of the cut last frame after a kill.
- The Electron `<video>` check.

**Coverage gaps**

- **Timestamp corpus.** There are 2 real timestamp series; the other 5 sets borrow c930e intervals. The corpus has no real dropped frames: gap60 and drop50 are synthetic deletions from c930e.
- **OpenCV on PyAV 19 files** covers c930e_720p_flash, its gap/drop variants, the looped 54,000-frame files, and c922_720p_flash counts for MKV and fMP4 1 s only (plus the GF02 MKV and fMP4 files in both PTS modes).
- **Seek coverage.** Seek tests with gaps cover fMP4, MP4 and MKV only. MOV, NUT and AVI were not tested with gaps. Index PTS was tested only in MKV and fMP4 (GF02).
- **FreeMoCap frame identity** was not checked on the clean c930e fMP4 1/1e6 files or on this topic's 54,000-frame files ("reads without error" only). It was checked on the gap60/drop50 files, the killed files and the GF02 files.
- **Kill tests:** this topic made one unpaced kill point per container, after complete `mux()` calls, using only `os._exit`, which loses user-space buffers. GF02 adds 6 paced kill points per container with `flush_packets=1` (MKV and fMP4 only, `os._exit` and TerminateProcess). Torn-tail handling under fp was not exercised (no torn tail in 48 paced kills). Power loss and OS crash were not tested.
- **PyAV timestamp seek** used only `backward=True, any_frame=False` with exact stored pts. Seeking to a time between two frames was not tested.

**NOT VERIFIED**

- The camera JPEG's own SSIM-Y/PSNR-Y against a raw frame of the same instant, and why camera JPEGs are about half the bytes of q94 on YUY2. Passthrough's position on the A/B scale is unknown (header).
- MP4/MKV/NUT files over 4 GiB were not written. The `co64` switch is cited only from source (FFmpeg n9.0.2 `libavformat/movenc.c:177-179,204-208`). The OPEN files were about 2.99 GB.
- The `mjpegadump` +44 B result (no result file).
- The root cause of the template frame loss.
- The exact cause of the 0-3 B size difference (the Lavf tag explanation is inferred).
- PyAV 18's FFmpeg release string ("8.1.2" was seen on the console only, VERIFY_provenance.md).
- The turbojpeg version in the Rust build, and therefore Rust's rotation behaviour and its "~1-2ms per frame" figure (§2.7, §2.9.4).
- Why fMP4 1 s fragments cost more per frame than per-frame fragments at 1080p (60.24 vs 56.26 µs/frame) and take 1.54 ms to close. Not investigated.
- The cause of the 13-18% run-to-run swing in the Python raw_sidecar and jpg_folder loops at 720p.
- The mechanism of the wrong MKV count (`round(duration × nominal fps)` is inferred).
- That open cost is linear in fragment count. Three points (two writers, one including the first read) give about 20.5-20.7 µs per fragment; the mov demuxer mechanism was not checked in source.
- Torn-tail handling with `flush_packets=1`; a PyAV or cv2 seek to a pts-bumped MKV frame; the trigger of the 62.5 fps rate on recovered real-PTS MKV (§9).

**Not in scope or not covered**

- Linux/macOS readers, and AVFoundation/QuickTime playback of MJPEG MOV/MP4.
- Chrome browser (only Electron was tested).
- MSE or WebCodecs VideoDecoder for MJPEG.
- Audio.
- Whether any camera used with skellycam omits DHT. None of the 3 corpus cameras does (§2.2).

## 7. How to reproduce

Run from the repo root `C:/Users/Dom/GitHub/freemocap/skellycam`. Run `unset ELECTRON_RUN_AS_NODE` first for the Electron step. **Run timed benches only on a quiet machine** (HANDOFF §5).

```
# Timed benches (quiet machine; the queue pinned them to the P-cores), commands as in results/bench_queue_2300.json
uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/bench_mux.py --containers pkt_only,mkv,mp4,fmp4_1s,fmp4_perframe,fmp4_1s_tb_us,fmp4_perframe_tb_us,mov,avi_tb_rate,nut,mjpeg_raw_mux,raw_sidecar,jpg_folder --tag default_pyav19            # -> bench/bench_mux_default_pyav19_<UTC>.json
uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/bench_mux.py --containers <same list> --fsync --tag fsync_pyav19   # -> bench/bench_mux_fsync_pyav19_<UTC>.json
uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/bench_open_long.py --frames 54000 --reps 5   # -> bench/open_long.json (about 12 GB written, then deleted)
uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/bench_rotate.py --lib C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/jpeg_passthrough/ljt321/bin/turbojpeg.dll   # -> bench/bench_rotate_<UTC>.json
# Queue runner used tonight: scripts/bench_runner/run_queue.py --only JP-MUX-PYAV19,JP-OPEN-LONG-PYAV19,JP-MUX-FSYNC-PYAV19,JP-ROTATE

# PyAV 19.0.2 functional (implementation under test)
uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/pyav19_recheck.py          # -> pyav19_recheck.json
uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/pyav19_recheck.py --write-fmp4-us C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/jpeg_passthrough/fmp4_tb_us
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/fmp4_tb_us_cv2_check.py C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/jpeg_passthrough/fmp4_tb_us   # reader only (OpenCV 4.12, FreeMoCap) -> pyav19_fmp4_tb_us_readers.json
uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/version_bump_check.py      # PyAV 19.0.2 + opencv-python 5.0.0.93 -> version_bump.json
uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/pyav19_seek_ts_check.py    # -> pyav19_seek_ts_check.json
uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/lavf_tag_check.py          # -> pyav19_lavf_tag.json
# verifier scripts (writer: uv/av==19.0.2; readers: skellycam .venv read-only), see VERIFY_method.md:
#   verify_method_writer.py, verify_method_reader.py, verify_method_size_check.py, verify_method_killed_readers.py, bench_open_long.py --dry --frames 300,
#   and the 2026-11-10 MKV count recheck -> verify_method2_mkv_count.json

# Step 3: read-only scan of GF02 sidecars (needs the GF02 Part A media to still exist)
uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/step3_gf02_sidecar_flags.py   # -> step3_gf02_sidecar_flags.json

# Not PyAV-dependent
uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/rotate_check.py --lib <scratchpad>/jpeg_passthrough/ljt321/bin/turbojpeg.dll --jpegtran <scratchpad>/jpeg_passthrough/ljt321/bin/jpegtran.exe --n 11   # -> rotation.json

# Background (PyAV 18 writer, skellycam .venv, read-only use)
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/mux_matrix.py         # -> mux_matrix.json
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/summarize_matrix.py   # -> mux_matrix.md
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/keyframe_check.py     # -> keyframe_setup.json
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/edge_cases.py --djpeg <scratchpad>/jpeg_passthrough/ljt321/bin/djpeg.exe   # -> edge_cases.json
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/truncation_check.py   # -> truncation.json
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/electron_check.py --jpegtran <scratchpad>/jpeg_passthrough/ljt321/bin/jpegtran.exe   # -> electron_check.json (needs mux_matrix media)
```

- `<scratchpad>` = `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad` for the functional rotation check. The timed ROT used the copy under `.../93366190-c2b0-4501-a85e-83654db13698/scratchpad/` (ROT `meta.lib`, sha256 above). NOTES.md §1 and §14 describe the libjpeg-turbo 3.2.1 download and extraction.
- `bench_mux.py` and `bench_open_long.py` carry PEP 723 pins (`av==19.0.2`; code: `bench_mux.py:1-4`, `bench_open_long.py:1-4`).
- Media is written under `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/jpeg_passthrough/` and deleted by the scripts.
- The FFmpeg n9.0.2 and OpenCV 4.12.0 source files cited above were fetched from raw.githubusercontent.com into `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/jpeg_passthrough/src/`. The verifier's re-downloads are byte-identical (VERIFY_provenance.md).

## 8. Revision history

**2026-11-10: Step 3 gap-fill and its verification** (see §9).

**2026-11-10: timed results added.**
- §2.9, the timed rows of §3.2, §3.3, §3.4 and §5 are new. The previous §5 "Pending tonight's bench" is removed: all four items ran in `20261109T230007`, and every number was recomputed from the raw `runs` arrays.
- The "changes needed before the mux benches" from the previous §5 were made before the run:
  - PyAV 19.0.2 via PEP 723 (`bench_mux.py:1-4`);
  - `fmp4_1s_tb_us` / `fmp4_perframe_tb_us` in `jp_io.py:47-48`;
  - the `"us"` branch in `bench_mux.py:94-95`;
  - the names in the queue's `--containers` list.

  MP4/MOV/NUT at 1/1e6 were still not added (§6).
- §4 updated: the fragment choice now uses open cost (§4.2). §4.3 (G5 throughput), §4.4 (folder cost) and §4.9 (fsync at stop) are new, and §4.11 adds the rotation cost.
- The 2026-11-10 verifier corrections are listed in §9.

**2026-11-09: verifier pass** (`VERIFY_provenance.prev.md`, `VERIFY_method.prev.md`).
- Accepted refutations:
  - fMP4 1/1e6 benching needed 3 changes;
  - the readers agree only on maxima;
  - AVI rounds VFR and refuses same-tick frames, rather than "cannot store VFR";
  - OpenCV seeks fail with gaps;
  - in-memory and file sizes are equal on PyAV 19;
  - OpenCV 5 never read fMP4 at 1/1e6.
- Rejected:
  - the Matroska `[@!JPEG]` quote objection (the served HTML contains it);
  - "PyAV seek 5/10" (the test has 5 targets; the frame-identity check was added as `pyav19_seek_ts_check.json`).

## 9. Verification

**Date:** 2026-11-10. Reports: `results/jpeg_passthrough/VERIFY_provenance.md` and `results/jpeg_passthrough/VERIFY_method.md` (the previous reports are `VERIFY_*.prev.md`); Step 3: `results/jpeg_passthrough/VERIFY_step3.md`.

**What the verifiers checked**
- Provenance:
  - every timed number in §2.9 and §3.2-§3.4 against the four quiet-run JSONs: medians and min-max recomputed from `runs`, OPEN, ROT, the run-log fields and the arithmetic;
  - spot checks of functional numbers against their PyAV 19.0.2 result files;
  - re-downloads of the FFmpeg/OpenCV sources (byte-identical to the author's copies);
  - the PyAV and web quotes (still present on 2026-11-10);
  - PyAV 18 labelling and target A/B handling.
- Method:
  - MUX-D vs MUX-F reproducibility with identical in-loop code (`bench_mux.py:98-113`);
  - a PyAV 19.0.2 + OpenCV 4.12 recheck of MKV counts on c922 real VFR (`verify_method2_mkv_count.json`);
  - a cross-check against write_throughput's 16-camera, Defender and index-read figures;
  - the python_integration open-cost point;
  - the reader and kill results per container.
- Reviser re-check (2026-11-10, no timed runs):
  - `jpeg_transform.rs` lines 1-5 (the figure is on line 4);
  - `jp_io.py` line numbers (:157-166, :161, :239, :253, :335-343);
  - MUX-D/MUX-F medians, CPU medians and close GB/s recomputed from `runs`;
  - `verify_method2_mkv_count.json`, `verify_method_reader.json` (MKV drop50 seek 5), `verify_method_killed_readers.json` (NUT 595/598);
  - `recwriter_quiet1_pyav19.json` `c_open_cost.mp4f`;
  - the run-log times, flags and SearchIndexer.exe 9.36 CPU-s;
  - `mux_matrix.md` lines 38-39, 49-50;
  - `rotate_check.py:82-89` and `rotation.json` `tj3_warnings`;
  - `write_throughput/BENCH.md` lines 213, 220 and 221;
  - `camera_jpeg_quality.md` lines 9-10, 16-17;
  - `intra_compare/NOTES.md:156`.

  Every refutation was confirmed.

**What changed in this revision**
- Refuted, corrected:
  - "720p container differences are noise" is replaced by "libav medians reproduce within 3%; the differences are real but small (≤4.6 µs/frame at 720p ≈ 0.14 ms/s at 30 fps); the large swing is only in the Python loops" (§2.9.1, §4.3, §5).
  - "MKV counts are wrong whenever timing is irregular" is replaced by "wrong with dropped frames or an off-nominal mean rate, exact on c922 real VFR". The mechanism is inferred (§2.4, §3.1, §4.8, §2.9.5).
  - The 16-camera linear extrapolation is deleted and replaced by write_throughput's measured 16 × 1080p60 latencies (§2.9.1).
  - The flush rate is now 2.0-4.2 GB/s across writers, with 3.87-4.11 for fMP4 1 s at 1/1e6 (§2.9.2).
  - The Rust comment is cited at `jpeg_transform.rs:3-4` (the figure is on line 4). The earlier note that called `:4` wrong is removed.
  - OpenCV seeks with gaps: MKV is 5/10 and 5/10, not 5/10 and 7/10 (§4.5).
  - Stale `jp_io.py` lines updated to :335-343, :157-166 and :239-253.
- Weak, relabelled or rescoped:
  - passthrough quality: the size gap is added, and passthrough is not a point on the A/B scale (header, §4.1);
  - open-cost scaling: the docstring is dropped as support and the python_integration point added (§2.9.3);
  - warm cache is labelled inferred (§2.9.3, §5);
  - the sidecar count is now cited as measured in write_throughput (§4.6);
  - fMP4 count is estimated, MP4 count is stored (§2.4);
  - the 0.2% and 27% CPU figures are labelled single stream, Gerald P-core, with 0.2% as wall time and the CPU median agreeing (§4.3, §4.11);
  - Defender CPU is item-level here, with the per-writer attribution from write_throughput (§2.9, §2.9.1, §4.4, §5);
  - run times are exact, and the leftover-process flag and SearchIndexer activity before ROT are given (§2.9, §5);
  - the ROT input confounders are added (§5);
  - the §4.2 fragment choice is restated as a trade-off;
  - killed-file miscounts: fMP4 +1 to +3, NUT -3, MKV negative (§2.5, §4.6);
  - the §3.1 MKV gap cell reads "888 for 831 / 888 for 874";
  - the `mux_matrix.md` citation is lines 38-39 and 49;
  - the rotate script raises on hard errors and accepts warnings (§2.9.4).
- At that pass no §4 recommendation changed. The Step 3 fold below supersedes this for §4 items 2, 5 and 8.

**Step 3 gap-fill (2026-11-10)**

Evidence read: `results/crash_resilience/gapfill/GF01_container_decision_table.md`, `GF01_NOTES.md`, `GF02_container_matrix.md`/`.json`, `GF02_NOTES.md`, `GF02_partA_write.json`, `GF02_partA_read.json`, `GF02_partA_long_read.json`, `GF02_partA_long_write.json`, `GF02_recovered_rates.txt`. Values were re-read from the JSONs, not from the reports. Cross-topic lines re-read: `write_throughput/FINDINGS.md:87-96`, `functional/functional_results_av19.0.2.md:45`, `functional_results_av19.0.2_gapfill.md:26`, `python_integration/FINDINGS.md:110`, `:274`, `:283`, `:405`, `crash_resilience/FINDINGS.md:85`, and `recwriter_quiet1_pyav19.json` `c_open_cost.*.cv2_frame_count_prop` (18000.0 for mkv and mp4f). No timing was run for this fold. One read-only functional scan was added (`step3_gf02_sidecar_flags.json`).

| Change | Section | Why |
|---|---|---|
| "Leading container candidate" → "a container candidate", with write_throughput's 33/62 (no fp) and 46/5 (fp) losses, their kill conditions and a pointer to GF01 | §4 item 2 lead | GF01 §2.2 item 1: the topics disagree on 1 s fragments; GF01:33-36: kill tests not comparable |
| Added GF02 kill losses (1 s fragments 1-30 frames per kill; per-frame fMP4 + fp and MKV + fp 1 in 12/12) and real-PTS fMP4 seek misses | §4 item 2 | GF02 Part A and B |
| "Per-frame fragments kept 18 more (596 vs 578) at the one kill point" → GF02 paced-kill losses scoped by fp and PTS mode, plus the no-fp single-kill losses (4 and 22) | §4 item 2 | 12 paced kills per container replace one kill point |
| MKV rule-out scoped to real VFR PTS; index-PTS evidence, the recwriter bump, and the killed/recovered MKV results added | §4 item 8 | GF02 Part A/B; python_integration F3/F13 |
| POS_FRAMES seek rule scoped to real VFR PTS; index-PTS 11/11 added | §4 item 5, §2.4 reader notes | GF02 Part A |
| GF02 rows (index PTS, real-PTS MKV and fMP4, long real-PTS fMP4 and MKV) and method notes | §2.4 | GF02 Part A |
| GF02 rows in the comparison tables (index PTS, paced kills, GF02 seek scores); gap rows scoped to real VFR PTS | §3.1, §3.2 | GF02 Part A/B |
| GF02 paced-kill table, no torn tail in 48 kills, kill-point formula, killed-file reader results | §2.5 | GF02 Part B |
| Buffer inference 32 KiB → libavformat 262,144 B buffer | §2.5 | Sizes are also 126 × 262,144; FFmpeg `file.c:324-332` (GF01 notes) |
| PTS-mode definitions, GF02 and GF01 in the result-file list | header | |

**Proposed text corrected against the evidence**
- The proposed range "14-30 frames" for fMP4 1 s + fp is wrong. Index PTS lost 1 frame at kill point 451, so the range is 1-30 (real 14-29, index 1-30) (GF02 `partB[].lost_vs_sidecar`).
- The proposed "the 1 ms grid collision is absorbed by recwriter's +1 tick bump (PyAV seeks 11/11)" is rescoped. The bump is in code and happened, but no seek target hit a bumped frame (`step3_gf02_sidecar_flags.json`).
- GF01's proposed "Index PTS with dropped frames: not yet tested (GF02)" is superseded: GF02 tested gap60 and drop50 with index PTS (exact).
- The kill-point formula ((k − 1) mod 30) + 1 is labelled computed, on index PTS only. With real PTS the 1 s boundary is in time, not frames.

**Step 3 verification (`VERIFY_step3.md`): PASS with minor fixes, 0 refuted, 7 weak.** Each weak item was re-checked by the reviser before it was applied.

| Weak claim | Reviser check | Applied |
|---|---|---|
| §4.2 "everything since the last 1 s boundary" for both PTS modes | Formula holds on index PTS only (20, 17, 30, 1, 11, 10 for kill points 50…700) | Split: index PTS computed 6/6; real PTS 14-29, consistent (inferred) |
| §4.2 "per-frame fragments lose 1 frame per kill" with no fp scope | `pyav19_recheck.json` per-frame kill 596/600 without fp; WT `fmp4_frame` 5, 5 (WT FINDINGS:96) | Scoped to fp, 12/12; no-fp losses 4 and 22 added |
| §4.2 "both PTS modes" under the 1/1e6 heading | GF02 `partA[].time_base`: index fMP4 1/15360, real 1/1e6 | Time base per mode stated; 1 µs timestamp bullet scoped to real PTS; heading no longer implies 1/1e6 for index PTS |
| §4.2 WT 33/62 vs JP 22 without conditions | `functional_results_av19.0.2.md:45` `[33, 62]`; WT FINDINGS:87-89 (720p60 paced, TerminateProcess); `pyav19_recheck.py` has no sleep or `flush_packets`, `os._exit` at :184; GF01:33-36 | Conditions and result-file citation added |
| §4.8 bump citation and count | Sidecar scan: 1 flagged record (frame 82, pts 2705) in each of the 6 c930e-derived real-PTS MKV files; none in c922, fMP4 or index files; GF02 targets 0, 89, …, 890 | Applied. Also found: the real-PTS 54,000-frame MKV has 61 bumps (every 890 frames from 82), none on its 11 targets (not in the verifier's report; `step3_gf02_sidecar_flags.json`) |
| §4.8 "tested, and exact" for index PTS with drops | Index PTS = frame index by construction (`recwriter.py:87-89`) | Appended "(the container timeline hides the drop; capture times come only from the sidecar, inferred)" |
| Unchanged §4 item 5 and §3.1 gap rows contradict GF02 index-PTS results; §2.5 "i.e." clause unlabelled | GF02 index-PTS gap60/drop50: counts exact, 11/11 (16/16 files) | §4 item 5, §2.4 reader notes and §3.1 rows scoped to real VFR PTS with index-PTS results; §2.5 clause labelled inferred |

**Still open**
- HANDOFF §4 still headlines "fMP4 with a 1/1e6 time base is the leading container". GF01 §4 calls it contested; HANDOFF was not edited.

**New NOT VERIFIED from this fold:** torn-tail handling with `flush_packets=1` (no torn tail occurred in 48 paced kills); a PyAV or cv2 seek to a pts-bumped MKV frame (no target hit one); the trigger of the 62.5 fps rate on recovered real-PTS MKV (inferred by GF02 as the template remux, `scripts/python_integration/recwriter.py:259`).

**Still NOT VERIFIED:** passthrough's SSIM-Y/PSNR-Y against raw frames and the cause of the camera-vs-q94 size gap; the cause of the Python-loop run-to-run swing; the MKV count mechanism; the linear fragment-count open cost and its demuxer mechanism; cold-open times; the Rust turbojpeg version and its rotation figure; the template frame-loss root cause; the 0-3 B size-difference cause; >4 GiB files; the `mjpegadump` +44 B result; PyAV 18's FFmpeg release string (full list in §6).
