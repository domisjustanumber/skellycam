# jpeg_passthrough: FINDINGS (goals G1, G5)

2026-11-09, Gerald (Windows 11, i7-14700K). This file has functional results only and no timing numbers (see section 5). It was revised after two verifier reports; section 8 lists what changed.

Paths are relative to `research/skellycam_recording/recording_upgrade/` unless they are absolute.

**Labels**
- **measured**: a result file.
- **measured, PyAV 18 - background**: made with the skellycam venv (PyAV 18.0.0, libavformat 62.12.102, libavcodec 62.28.102; `mux_matrix.json` meta). It is not the implementation under test.
- **source**: a primary source, accessed 2026-11-09.
- **code**: file:line.
- **inferred**: reasoning, kept to a minimum.

**Implementation under test:** PyAV 19.0.2, with libavformat and libavcodec 63.1.102 (measured: `results/jpeg_passthrough/pyav19_recheck.json` meta). `av.ffmpeg_version_info` is "9.0.2" (measured: `pyav19_seek_ts_check.json` meta).

**PyAV 19.0.2 result files** (all in `results/jpeg_passthrough/`)

| File | What it holds |
|---|---|
| `version_bump.json` | c930e_720p_flash written to files, read by OpenCV 5.0.0.93. That OpenCV bundles its own avformat 61.7.100 (meta). |
| `pyav19_recheck.json` | All 7 sets written in memory, kill test, setup details, DHT decode |
| `pyav19_fmp4_tb_us_readers.json` | OpenCV 4.12.0 and FreeMoCap reads of fMP4 written with time base 1/1e6 |
| `verify_method_writer.json` | Verbatim payload check, plus files with dropped frames: gap60 (frames 300-359 removed, 831 frames) and drop50 (every 50th frame removed, 874 frames). Also a 54,000-frame file. |
| `verify_method_reader.json` | OpenCV 4.12 and FreeMoCap reads of those files |
| `verify_method_killed_readers.json` | OpenCV 4.12 and FreeMoCap reads of files killed while PyAV 19 was writing |
| `verify_method_size_check.json`, `verify_method_open_dry.json` | Size in memory vs file; dry run of the open bench (counts only) |
| `pyav19_seek_ts_check.json` | New in this revision: PyAV timestamp seek, checked by frame identity |
| `pyav19_lavf_tag.json` | New in this revision: writer tag per muxer |

**Background files (PyAV 18 writer):** `mux_matrix.json`/`.md`, `keyframe_setup.json`, `truncation.json`, `edge_cases.json` and `electron_check.json`. The Electron check used media from the PyAV 18 mux_matrix.

**Not PyAV-dependent:** `rotation.json` (libjpeg-turbo 3.2.1, jpeglib, jpegtran).

**Timestamp corpus.** Only c930e_720p_flash (891 frames) and c922_720p_flash (893) have real capture times (MF sample time, 100 ns units). The other 5 sets (10-19 frames each) reuse c930e's first intervals, and 720p60 halves them. Every timestamp is floored to whole µs before muxing (code: `scripts/jpeg_passthrough/jp_common.py:22-29,59-69`; `pyav19_recheck.py:152-160`).

## 1. Questions answered

1. **G1.** Can Python (PyAV 19.0.2) store camera JPEG bytes in a container with no decode or re-encode, and get the same bytes back?
2. Which containers accept MJPEG? Do they change JPEG headers? How well do they keep real variable-frame-rate (VFR) capture timestamps?
3. **G5, compatibility side.** For each wrapper (folder of JPEGs, raw + sidecar, MKV, MP4, fMP4, MOV, AVI, NUT):
   - frame count and seeking in OpenCV, FreeMoCap and PyAV;
   - reading after a hard kill;
   - Chromium playback.

   The throughput side is pending (section 5).
4. Edge cases: frames without DHT, extra bytes after the entropy-coded data, and lossless rotation as the Rust code does it.

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
- **Checked without FFmpeg.** All 891 c930e input JPEGs appear verbatim and in order in the raw file bytes of fMP4 1 s, fMP4 per-frame, MP4, MOV and NUT (all at 1/1e6) and of MKV (measured: `verify_method_writer.json` `V1_verbatim`). This removes the worry that one library both writes and reads the files.
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
  - source: https://www.matroska.org/technical/codec_specs.html. The served HTML contains the bracket text literally (fetched with curl 2026-11-09; copy in the scratchpad `.../93366190-.../scratchpad/jpeg_passthrough/mkvspec/codec_specs.html`).
  - source: FFmpeg n9.0.2 `libavformat/matroska.c:86`.
- **MP4** stores MJPEG as an `mp4v` sample entry with object type 0x6C, "Visual ISO/IEC 10918-1" (source: https://mp4ra.org/registered-types/object-types; FFmpeg n9.0.2 `libavformat/isom.c:55`).
- ffprobe shows `codec_tag_string` `mp4v` for fMP4 written by PyAV 19.0.2 (measured: `pyav19_recheck.json` `B_fmp4_tb_us_ffprobe`).

**Container overhead**

PyAV 19.0.2, c930e_720p_flash VFR, 891 frames with 49,314,521 payload bytes (measured: `pyav19_recheck.json` `A_matrix` `size_bytes`; AVI is CFR):

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

- PyAV 18 writes are 0-3 B larger than PyAV 19 writes over 166 matched rows: 0 B for AVI and raw, 1 B for MP4/MOV/NUT/fMP4, 3 B for MKV. The payload bytes are identical (measured: `mux_matrix.json` vs `pyav19_recheck.json`, recomputed in this revision).
- PyAV 19 writes the tag `Lavf63.1.102` 3 times in MKV and once in MP4, MOV, NUT and AVI (measured: `pyav19_lavf_tag.json`). PyAV 18's libavformat is 62.12.102, so its tag `Lavf62.12.102` is 1 character longer.
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
- Decoding: PyAV 19.0.2's mjpeg decoder turns stripped frames into the same pixels as the originals (measured: `pyav19_recheck.json` `E_decode_dht_stripped`):
  - c930e 30/30;
  - c922 30/30;
  - generic 11/11.
- Why it works: FFmpeg installs default Huffman tables when the decoder starts (source: FFmpeg n9.0.2 `libavcodec/mjpegdec.c:62,148`, `init_default_huffman_tables`).
- cv2.imdecode, Pillow and djpeg 3.2.1 also give stripped == original (measured: `edge_cases.json` `decoders`; not PyAV-dependent).
  - djpeg exits non-zero on the generic camera's original and stripped frames alike ("535 extraneous bytes before marker 0xd9"). Its two outputs are still equal (11/11).

**Bitstream filters**

- `mjpeg2jpeg` adds 438 B (Logitech) or 419 B (generic) per frame. Every camera that carries DHT ends up with two table sets (5 DHT markers). It is not byte-exact, so use it only on request (measured, ffmpeg CLI 9.0.2 bsf on PyAV 18 MKV - background: `edge_cases.json` `mjpeg2jpeg`, `out_markers`).
- `mjpegadump` +44 B: NOT VERIFIED. It was a one-off in NOTES.md §3 and its output was deleted.

### 2.3 Timestamps (real VFR capture times)

**Accuracy by container** (corpus caveat in the header: 2 real timestamp series, 5 borrowed)

- **1/1e6 time base.** MP4, MOV, NUT, fMP4 1 s and fMP4 per-frame keep the timestamps exactly at 1 µs resolution. Max error is 0 µs against the µs values the writer was given, strictly increasing, on the 2 real series (891 and 893 frames) and the 5 borrowed-interval sets (measured: `pyav19_recheck.json` `A_matrix` `*_tb_us|vfr`). The sub-µs part of the 100 ns source is never stored, so ns precision needs the sidecar (code: `pyav19_recheck.py:156`).
- **fMP4 1/1e6 readers:**
  - ffprobe reads the PyAV 19.0.2 files with 0 µs error (measured: `pyav19_recheck.json` `B_fmp4_tb_us_ffprobe`);
  - OpenCV 4.12.0 `CAP_PROP_POS_MSEC` also gives 0 µs on c930e_720p_flash (measured: `pyav19_fmp4_tb_us_readers.json`).
- **Default 1/90000 time base.** Max error is 5.556 µs in MP4, MOV, fMP4 and NUT (measured: `pyav19_recheck.json`).
- **MKV** is fixed at 1 ms. Max error is 470 µs on VFR (measured: `pyav19_recheck.json` `c930e_720p_flash|mkv|vfr`).
  - Frames that arrive less than 1 ms apart get the same timestamp, so the pts is not strictly increasing.
  - On c930e, frames 81 and 82 both get pts 2704. A timestamp seek to frame 82 returns frame 81 (measured, PyAV 19.0.2: `pyav19_seek_ts_check.json` `full|mkv` misses).
  - Their capture times are 11 µs apart: 11,000 ns from the capture jsonl read through `jp_common.real_timestamps_ns`, recomputed on the console in VERIFY_provenance.md.
  - source: FFmpeg n9.0.2 `libavformat/matroskaenc.c:3602-3603`, "ms precision is the de-facto standard timescale for mkv files" / `avpriv_set_pts_info(st, 64, 1, 1000);`.

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
- The folder-of-JPEGs `timestamps.csv` is written (code: `scripts/jpeg_passthrough/jp_io.py:154-160`) but nothing reads it back. Not tested.

**Do the readers agree?**

- **PyAV 19 files.** The maximum timestamp error from PyAV 19 pts and from OpenCV 5.0.0.93 `CAP_PROP_POS_MSEC` agrees in every written container on c930e (measured: `version_bump.json` `pyav19_ts` vs `cv5_ffmpeg_ts`). Only maxima are stored, not per-frame errors, and ffprobe is not in that file.
- **PyAV 18 files.** PyAV, ffprobe and OpenCV 4.12 agree on the maximum everywhere except raw `.mjpeg` and raw+sidecar, where OpenCV differs by up to 586 µs: 6,031,976 vs 6,032,562 µs on VFR (measured, PyAV 18 - background: `mux_matrix.md` lines 38-39, 49-50).

### 2.4 Frame count and seeking (G5 compatibility)

**How the readers work**

- FreeMoCap's `VideoHelper.from_video_path` opens `cv2.VideoCapture(str(video_path))` and stores `CAP_PROP_FRAME_COUNT` (code: freemocap 5632778a, `freemocap/core/pipeline/posthoc/video_group_helper.py:151,159`).
- A `VideoGroup` raises unless every camera reports the same count (code: `video_group_helper.py:381-385`).
- FreeMoCap reads forward with `grab()` and then `read()`. It never sets `CAP_PROP_POS_FRAMES` (code: `video_group_helper.py:235-250`; grep finds no `POS_FRAMES` in the file).
- skellycam's file discovery accepts only `{".mp4", ".avi", ".mov", ".mkv", ".webm"}` (code: `skellycam/core/recorders/videos/parse_video_filename.py:18`).
- OpenCV's frame count is `nb_frames`, or `floor(duration × fps + 0.5)` when `nb_frames` is 0 (source: OpenCV 4.12.0 `modules/videoio/src/cap_ffmpeg_impl.hpp:1980-1989`).
- OpenCV turns a time into a frame index through the average fps: `(int64_t)(get_fps() * sec + 0.5)` (source: same file, `:1992-1996`). A capture with gaps therefore breaks `CAP_PROP_POS_FRAMES` seeks.
- **Seek test method.** OpenCV seek targets are `[0,1,2,n//3,n//2,n-2,n-1,5,n//2,3]`. "Exact" means the frame matches the same reader's sequential decode, not the input frame (code: `jp_io.py:332`). About 4 of the 10 targets are informative.

**OpenCV 4.12.0 on PyAV 19.0.2 files with time base 1/1e6**

| File | Count (actual) | Frames read | OpenCV seek | FreeMoCap count / reads matching OpenCV's sequential decode | Source (measured) |
|---|---|---|---|---|---|
| c930e full (no gaps), fMP4 1 s and per-frame | 891 (891) | 891 | 10/10 | 891 / 4 reads, identity not checked | `pyav19_fmp4_tb_us_readers.json` |
| gap60, fMP4 1 s / per-frame / MP4 | 831 (831) | 831 | **5/10** | 831 / 4 of 4 | `verify_method_reader.json` |
| drop50, fMP4 1 s / per-frame / MP4 | 874 (874) | 874 | **7/10** | 874 / 4 of 4 | `verify_method_reader.json` |
| gap60 / drop50, MKV (1/1000) | 888 (831 / 874) | 831 / 874 | 5/10 | 888 / 3 of 4 (frame 887: "Failed to grab frame") | `verify_method_reader.json` |
| 54,000 frames, 1,796 s, one 2 s gap, fMP4 1 s / per-frame / MP4 | 54,000 (54,000) | 54,000 grabbed | not run | 54,000 / 4 reads without error, identity not checked | `verify_method_reader.json` `long_*` |

- `CAP_ANY` picks FFMPEG on the fMP4 1/1e6 files (measured: `pyav19_fmp4_tb_us_readers.json`).
- fMP4 stores no `nb_frames` (measured: `pyav19_recheck.json` `B_fmp4_tb_us_ffprobe` `nb_frames` null), so OpenCV estimates the count. That estimate was still exact in every 1/1e6 MP4 and fMP4 case above.
- **MKV counts are wrong whenever the timing is not regular** (measured: `verify_method_reader.json`, `verify_method_open_dry.json`):
  - gap60 888 for 831;
  - drop50 888 for 874;
  - 299 for 300 on looped c930e frames and intervals.

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

- **Keyframe seek by pts** (measured: `version_bump.json` `pyav19_seek_exact`). Method: 5 targets `[0,1,445,890,2]`, comparing only the pts, not the frame (code: `version_bump_check.py:58`, `jp_io.py:236-250`).
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

**Setup.** A child process muxes 600 c930e_720p_flash frames with PyAV 19.0.2 and calls `os._exit(1)` without closing the file. PyAV 19.0.2 then demuxes the result (measured: `pyav19_recheck.json` `C_killed`; readers measured: `verify_method_killed_readers.json`, OpenCV 4.12).

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
- **This is one kill point, so read it as a bound, not a ranking.** The killed MKV, AVI, NUT and raw files are all 33,030,144 B = 1008 × 32,768 (measured: `pyav19_recheck.json` `C_killed.*.bytes`).
  - inferred: the loss is the unflushed user-space write buffer (32 KiB here). For fMP4 the open fragment is lost as well (up to about 1 s with 1 s fragments).
  - The 597/598 survivors in MKV, AVI, NUT and raw show where the buffer stopped. They are not a container property.
- **A cut last frame can enter analysis without any error.** OpenCV returns 579 frames from the killed fMP4 1 s file, but only 578 packets are complete (measured: `verify_method_killed_readers.json`, `pyav19_recheck.json`).
  - On PyAV 18, the cut frame decoded without error in most containers and raised `InvalidDataError` in fMP4 per-frame (measured, PyAV 18 - background: `truncation.json` `decode_errors`).
  - PyAV 19 decode of the cut frame was not run.

**Other crash results (background)**

- The Python raw+sidecar writer kept 409 of 600 frames, all exact (measured, Python writer: `truncation.json` `raw_sidecar`).
- Truncating files to 50% and 90% of their bytes keeps 445 and 801-802 exact frames in every container except plain MP4/MOV, which become unreadable (measured, PyAV 18 - background: `truncation.json` `truncated`).
- A 1,154,485,550 B OpenDML AVI (6000 frames, 1 `AVIX` RIFF) reads 6000/6000 byte-exact in PyAV. OpenCV seeks 10/10, MSMF reads 6000 and FreeMoCap counts 6000 (measured, PyAV 18 - background: `truncation.json` `large_avi`).

### 2.6 Chromium / Electron (G8 cross-check)

Measured, PyAV 18-written files - background: `electron_check.json`.

- **`<video>`.** Electron 35.7.5 (Chrome 134.0.6998.205) and Electron 45.2.3 (Chrome 156.0.8078.80) play MJPEG from no container:
  - MKV, MP4, fMP4 1 s and MOV fail with error 4 `DEMUXER_ERROR_NO_SUPPORTED_STREAMS`;
  - AVI, NUT and raw fail with `DEMUXER_ERROR_COULD_NOT_OPEN`;
  - the VP9 WebM control plays and seeks.
- **MIME checks.** `canPlayType` returns "" for every MJPEG MIME tested, and MSE `isTypeSupported` returns false. `video/x-matroska` alone gives "maybe", in 45.2.3 only.
- **Single frames.** `<img>`, `createImageBitmap` and `ImageDecoder` decode every test JPEG in both versions: original, DHT-stripped, generic with extra bytes, and rotated 4:4:0 (ImageDecoder reports I422, or BGRX for 4:4:0).
  - The evidence is correct dimensions and a mean pixel value. Stripped and original give the same mean (128.16276).
  - Pixels were not compared against a reference decoder.
- inferred: the failure comes from the codec, not the muxer version, so PyAV 19 files should fail the same way. Not re-run.

### 2.7 Lossless rotation (Rust parity)

Measured: `rotation.json`, libjpeg-turbo 3.2.1, not PyAV-dependent.

- libjpeg-turbo 3.2.1 `tj3Transform` through ctypes (options 0, the call Rust makes) is DCT-exact in 228 of 228 frame × rotation cases.
- jpegtran gives the same bytes in 228/228.
- The control (rotating the block grid without permuting coefficients) matches 0/228, so the test can fail.
- RGB max abs diff is ≤ 5. rot90/270 output is 4:4:0 (TJSAMP 4).
- The Rust-equivalent legacy `tjTransform` returns 0 (rotated) on 195 of 228 cases. All 33 generic_1080p cases return -1 (`tj3_warnings` 33).
- The Rust code keeps the output only when `ret == 0` (code: `git show upstream/sfn26:skellycam-rust/src/camera_group/jpeg_transform.rs:108`, `if ret == 0 && !dst_buf.is_null()`).
- inferred, conditional: with libjpeg-turbo 3.2.1, that check would record a rotated generic camera unrotated, with no error.
  - The Rust build downloads turbojpeg "from the latest GitHub Release on the `jonmatthis/openpnp-capture` fork" (code: `git show upstream/sfn26:skellycam-rust/build.rs:1-6`).
  - That library version is not pinned, so the Rust behaviour is NOT VERIFIED.

### 2.8 Version bump

- PyAV 19.0.2 changes no passthrough result relative to PyAV 18. That covers write success, byte-exactness, timestamp errors, WebM refusal, AVI VFR EINVAL, kill survivors and template loss (measured: `version_bump.json`, `pyav19_recheck.json`, `verify_method_killed_readers.json`).
- Output sizes differ by 0-3 B (§2.1).
- OpenCV: the pairs PyAV 18 + OpenCV 4.12 and PyAV 19 + OpenCV 5.0.0.93 gave the same counts and seeks on all 26 c930e rows (measured: `version_bump.json` vs `mux_matrix.json`). This is not an isolated OpenCV comparison, because the writer changed too.

## 3. Comparison tables

### 3.1 Container properties for camera-JPEG passthrough

PyAV 19.0.2 writer unless marked [18] (measured, PyAV 18 - background).

| Property | Folder .jpg + CSV | raw .mjpeg + sidecar | MKV | MP4 (1/1e6) | fMP4 1 s (1/1e6) | MOV (1/1e6) | AVI (1/fps) | NUT (1/1e6) |
|---|---|---|---|---|---|---|---|---|
| Bytes exact (7 sets) | yes [18] | yes [18] | yes | yes | yes | yes | yes (CFR; VFR 6/7) | yes |
| VFR timestamp error | CSV written, not read back (not tested) | exact in index (ns) [18] | ≤470 µs; frames <1 ms apart share a pts | 0 µs (µs inputs) | 0 µs (µs inputs) | 0 µs (µs inputs) | 14.67 ms; fails if 2 frames land on one tick | 0 µs (µs inputs) |
| OpenCV count exact, c930e VFR | yes [18] | no [18] | no (888/891) | yes | yes (OpenCV 4.12) | yes | CFR only, yes | no (887) |
| OpenCV count exact with gaps (gap60/drop50) | not tested | not tested | no (888/888) | yes | yes | not tested | not tested | not tested |
| OpenCV seek, c930e (no gaps) | 10/10 [18] | 0/10 [18] | 5/10 | 10/10 | 10/10 (OpenCV 4.12) | 10/10 | CFR 10/10 | 6/10 |
| OpenCV seek with gaps (gap60 / drop50) | not tested | not tested | 5/10 / 5/10 | 5/10 / 7/10 | 5/10 / 7/10 | not tested | not tested | not tested |
| PyAV timestamp seek, frame identity (full / gap60 / drop50) | n/a | not tested | 35/36, 33/34, 34/35 | 36/36, 34/34, 35/35 | 36/36, 34/34, 35/35 | not tested | not tested | not tested |
| FreeMoCap VideoHelper opens | no [18] | no [18] | yes; wrong count on irregular timing | yes [18] | yes; reads match on gap files (4/4) | yes [18] | yes [18] | yes, count short [18] |
| CAP_MSMF reads | yes, CAP_IMAGES [18] | no [18] | partly (888/891 VFR) | no | no | yes | yes | no [18] |
| Complete frames after hard kill at 600 (one sample) | not tested | 409/600 (Python buffered) [18] | 597 | unreadable | 578 | unreadable | 597 | 597 |
| OpenCV count / read on killed file | - | - | negative / 597 | - | 582 / 579 | - | 0 [18] | 595 / 598 |
| Chromium `<video>` | n/a | no [18] | no [18] | no [18] | no [18] | no [18] | no [18] | no [18] |
| Overhead for 891 c930e frames | +CSV | 20 B/frame index [18] | 40,253 B | 11,936 B | 11,738 B | 11,843 B | 27,515 B (CFR) | 26,908 B |
| Files per camera-minute at 30 fps (arithmetic) | 1,801 | 2 | 1 | 1 | 1 | 1 | 1 | 1 |

**Sources for the table:** `pyav19_recheck.json`, `pyav19_fmp4_tb_us_readers.json`, `version_bump.json` (OpenCV 5.0.0.93, c930e rows except fMP4 1/1e6), `verify_method_reader.json`, `verify_method_killed_readers.json` and `pyav19_seek_ts_check.json`. [18] rows come from `mux_matrix.json`, `truncation.json` and `electron_check.json`.

### 3.2 fMP4 fragment choice (c930e_720p_flash, PyAV 19.0.2, time base 1/1e6)

| | fMP4 1 s fragments | fMP4 per-frame fragments |
|---|---|---|
| Overhead (891 frames) | 11,738 B | 117,521 B |
| Complete frames after one kill at 600 | 578 (loses the open fragment, inferred) | 596 |
| OpenCV count / frames read on the killed file | 582 / 579 | 597 / 596 |
| FreeMoCap read of the last counted frame, killed file | fails (581) | fails (596) |
| Timestamp error | 0 µs | 0 µs |
| OpenCV 4.12 count / seek, no gaps | 891 / 10/10 | 891 / 10/10 |
| OpenCV 4.12 count / seek, gap60 | 831 / 5/10 | 831 / 5/10 |
| PyAV timestamp seek, frame identity (full, gap60, drop50) | 36/36, 34/34, 35/35 | 36/36, 34/34, 35/35 |
| Open cost on a 30-minute file | pending (`bench_open_long.py`) | pending; 54,000 fragments |

Measured: `pyav19_recheck.json`, `pyav19_fmp4_tb_us_readers.json`, `verify_method_reader.json`, `verify_method_killed_readers.json`, `pyav19_seek_ts_check.json`.

## 4. Implications for the plan

1. **PyAV 19.0.2 alone meets G1.**
   - Use `add_mux_stream("mjpeg", rate, width=w, height=h)` and `av.Packet(bytes)`.
   - Always pass width and height. Leave `is_keyframe` unset. Do not use `add_stream_from_template` (§2.1).
   - The payload was checked verbatim without FFmpeg (§2.1).
2. **The leading container candidate is fMP4 with `st.time_base = Fraction(1, 1_000_000)`.** Among the tested options it is the only one that is all of the following (§2.3-§2.5, table 3.2):
   - byte-exact;
   - keeps VFR timestamps exact at 1 µs;
   - gives an exact OpenCV frame count, including with dropped frames and on a 54,000-frame file;
   - returns the right frames to FreeMoCap's forward reads;
   - lands on the right frame with a PyAV timestamp seek;
   - stays readable by PyAV/ffprobe after a kill.

   Caveats:
   - The fragment length trades overhead against frames lost on a kill.
   - Open cost on long files and mux cost are pending (§5).
3. **Random access must seek by timestamp from the per-frame sidecar, with PyAV.** OpenCV `CAP_PROP_POS_FRAMES` seeks are exact only when the capture has no gaps: 5/10 and 7/10 with gaps in all 4 containers tested (§2.4).
   - inferred: this matters for UI scrubbing and for any analysis that seeks (G9).
4. **Avoid plain MP4/MOV as the recording format.** A killed file is unreadable (§2.5).
   - inferred: they remain fine as a finalize/remux target.
5. **Rule out these containers for FreeMoCap-compatible recordings:**
   - MKV: 1 ms grid that merges frames less than 1 ms apart, and an OpenCV count that is wrong whenever timing is irregular (§2.3, §2.4);
   - NUT: the count is always short (§2.4);
   - AVI: VFR is rounded to the time base and refused when two frames land on one tick, and the default time base is 1/600 (§2.3);
   - raw `.mjpeg`: no timestamps and a garbage count (§2.3, §2.4);
   - WebM: refuses MJPEG (§2.1).
6. **Keep a per-frame timestamp sidecar whatever the container.**
   - After a kill, OpenCV over-counts by 1-3 frames (582 vs 579, 597 vs 596), and FreeMoCap fails on the last counted frame (§2.5). FreeMoCap trusts `CAP_PROP_FRAME_COUNT` (§2.4).
   - FreeMoCap should take its count from the sidecar, or from a full PyAV demux pass. PyAV's `stream.frames` is 0 for fMP4 and MKV (measured: `verify_method_open_dry.json`), and the cost of a demux pass is pending.
   - On recovery, trust only frames that the sidecar records as complete, or check that each packet ends with EOI (inferred). The cut last frame is otherwise returned silently (§2.5).
7. **A folder of JPEGs costs FreeMoCap compatibility.** VideoHelper cannot open it, and it means 1,801 files per camera-minute (table 3.1). Its throughput and Defender cost decide G5's "is the wrapper significant" and are pending (§5; write_throughput topic).
8. **The container choice cannot settle G8/G9.** Chromium plays MJPEG from no container (§2.6). Playback needs per-frame JPEG decode in the renderer or a proxy encode (chromium_codecs and chromium_sync_scrub topics).
9. **Rotation, if kept.**
   - Port `tj3Transform` with ctypes and accept outputs that come with `TJERR_WARNING`. Do not copy Rust's `ret == 0` check (§2.7).
   - For 4:2:0 or odd-size cameras, add `TJXOPT_PERFECT` or `TRIM` (inferred; NOTES.md §8 cites `turbojpeg.h:1130-1142`).
10. **PyAV upgrade.** Going from PyAV 18 to 19 brings no passthrough gain or loss (§2.8). The decision rests on other topics.

## 5. Pending tonight's bench

None of these has run. `results/jpeg_passthrough/bench/` and `BENCH.md` do not exist yet. The write_throughput topic's earlier BENCH.md is contaminated, so do not reuse its numbers here.

| Timed question | bench_manifest id / source | Command / notes for the queue |
|---|---|---|
| Mux CPU and wall µs/frame per container, and close/trailer ms, against the `pkt_only`, `raw_sidecar` and `jpg_folder` baselines; 720p and 1080p; 1 camera per process; page cache | `jp_mux_cost` (priority 1) | `uv run --no-project --python 3.12 --with av==19.0.2 --with numpy --with psutil python research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/bench_mux.py --tag default_pyav19`. Not smoke-tested. As written it does not cover fMP4 1/1e6 (see below). |
| The same with `FlushFileBuffers` after close (cost of getting data to disk) | `jp_mux_cost_fsync` (priority 2) | Same changes as `jp_mux_cost` |
| Open time and frame count for long recordings (30 min, 54,000 frames) in fMP4 1 s / per-frame / MP4 at 1/1e6 and in MKV, for cv2 `CAP_FRAME_COUNT` and PyAV open, plus a full PyAV demux packet count | VERIFY_method request | `uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/bench_open_long.py --frames 54000 --reps 5`. Dry run passed with counts only (`verify_method_open_dry.json`). |
| Lossless rotation cost per frame (tj3Transform rot90/180/270), 720p and 1080p | `jp_rotate_cost` (priority 2) | `uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/bench_rotate.py --lib C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/jpeg_passthrough/ljt321/bin/turbojpeg.dll`. PyAV-independent; fallback download in NOTES.md §14. The Rust comment "~1-2ms per frame" (code: `jpeg_transform.rs:4`) is NOT VERIFIED until then. |
| Multi-camera disk throughput, and the Defender cost of a JPEG folder vs one container | write_throughput topic | - |

**Changes needed before the mux benches**

1. **Switch to PyAV 19.0.2.** The manifest commands use `.venv/Scripts/python.exe` (PyAV 18). `bench_mux.py` has no PEP 723 header, and its workers run under `sys.executable` (code: `scripts/jpeg_passthrough/bench_mux.py:141`). The `uv run --with av==19.0.2` command above handles this.
2. **Add fMP4 1/1e6. This takes three changes, not one** (code: `bench_mux.py:36,82-87`; `jp_io.py:31-49`). Without the second change, a new entry would silently bench at the muxer default of 1/90000.
   1. Add a `jp_io.CONTAINERS` entry: `"fmp4_1s_tb_us": ("mp4", ".mp4", {movflags frag_keyframe+empty_moov+default_base_moof, min_frag_duration 1000000}, "us")`.
   2. In `bench_mux.py`, add `elif stb == "us": st.time_base = Fraction(1, 1_000_000)` after line 86. Today the worker handles only `"rate"`.
   3. Add the name to `DEFAULT_CONTAINERS` (`bench_mux.py:36`), or pass `--containers`.

   The same gap affects `mp4_tb_us`, `mov_tb_us` and `nut_tb_us`. Until these changes are made, the mux cost at 1/1e6 has not been benched.

## 6. Not tested / limits / NOT VERIFIED

**Not re-run on PyAV 19.0.2 (background only)**

- OpenCV 4.12 and FreeMoCap reads of all 7 sets in MP4/MOV/AVI/NUT. The c930e set and the gap/drop variants were re-run; see §2.4.
- `ffmpeg -c:v copy` extraction.
- Reads of byte-truncated files, and the >1 GiB AVI.
- OpenCV/FreeMoCap on killed AVI and raw files.
- PyAV 19 decode of the cut last frame after a kill.
- The Electron `<video>` check.

**Coverage gaps**

- **Timestamp corpus.** 2 real timestamp series; the other 5 sets borrow c930e intervals. The corpus has no real dropped frames: gap60 and drop50 are synthetic deletions from c930e.
- **OpenCV on PyAV 19 files** covers c930e_720p_flash and its gap/drop variants only.
- **Seek coverage.** Seek tests with gaps cover fMP4, MP4 and MKV only. MOV, NUT and AVI were not tested with gaps.
- **FreeMoCap frame identity** was not checked on the clean c930e fMP4 1/1e6 files or on the 54,000-frame files ("reads without error" only). It was checked on the gap60/drop50 files and on the killed files.
- **Kill tests:**
  - one kill point per container, after complete `mux()` calls;
  - `os._exit` only, which loses user-space buffers;
  - power loss, OS crash and per-packet flush policies were not tested (flushing belongs to the crash_resilience topic).
- **PyAV timestamp seek** used only `backward=True, any_frame=False` with exact stored pts. Seeking to a time between two frames was not tested.

**NOT VERIFIED**

- MP4/MKV/NUT files over 4 GiB were not written. The `co64` switch is cited only from source (FFmpeg n9.0.2 `libavformat/movenc.c:177-179,204-208`).
- The `mjpegadump` +44 B result (no result file).
- The root cause of the template frame loss.
- The exact cause of the 0-3 B size difference (the Lavf tag explanation is inferred).
- PyAV 18's FFmpeg release string. `av.ffmpeg_version_info` "8.1.2" was seen on the console only (VERIFY_provenance.md); only the lib versions are in a result file.
- The turbojpeg version in the Rust build, and therefore Rust's rotation behaviour (§2.7).

**Not in scope or not covered**

- Linux/macOS readers, and AVFoundation/QuickTime playback of MJPEG MOV/MP4.
- Chrome browser (only Electron).
- MSE or WebCodecs VideoDecoder for MJPEG.
- Audio.
- Whether any camera used with skellycam omits DHT. None of the 3 corpus cameras does (§2.2).

## 7. How to reproduce

Run from the repo root `C:/Users/Dom/GitHub/freemocap/skellycam`. Run `unset ELECTRON_RUN_AS_NODE` first for the Electron step.

```
# PyAV 19.0.2 (implementation under test)
uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/pyav19_recheck.py          # -> pyav19_recheck.json
uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/pyav19_recheck.py --write-fmp4-us C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/jpeg_passthrough/fmp4_tb_us
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/fmp4_tb_us_cv2_check.py C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/jpeg_passthrough/fmp4_tb_us   # reader only (OpenCV 4.12, FreeMoCap) -> pyav19_fmp4_tb_us_readers.json
uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/version_bump_check.py      # PyAV 19.0.2 + opencv-python 5.0.0.93 -> version_bump.json
uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/pyav19_seek_ts_check.py    # -> pyav19_seek_ts_check.json
uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/lavf_tag_check.py          # -> pyav19_lavf_tag.json
# verifier scripts (writer: uv/av==19.0.2; readers: skellycam .venv read-only), see VERIFY_method.md:
#   verify_method_writer.py, verify_method_reader.py, verify_method_size_check.py, verify_method_killed_readers.py, bench_open_long.py --dry --frames 300

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

- `<scratchpad>` = `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad`. The libjpeg-turbo 3.2.1 download and extraction are in NOTES.md §1 and §14.
- Media is written under `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/jpeg_passthrough/`. The new scripts delete it.
- The FFmpeg n9.0.2 and OpenCV 4.12.0 source files cited above were fetched from raw.githubusercontent.com into `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/jpeg_passthrough/src/`. The verifier's re-downloads are byte-identical (VERIFY_provenance.md).

## 8. Verification

The draft was challenged by `results/jpeg_passthrough/VERIFY_provenance.md` (provenance: every number recomputed, every source re-read) and `VERIFY_method.md` (method: new PyAV 19.0.2 checks on files with dropped frames, on killed files and on size). I re-checked each refutation against the result files and code before applying it. I also ran two new functional checks (no timing, under 1 min CPU): `pyav19_seek_ts_check.json` and `pyav19_lavf_tag.json`.

**Refutations accepted (confirmed by my own check)**

| Draft claim | Check | Change |
|---|---|---|
| Benching fMP4 1/1e6 is "a one-line addition" | `bench_mux.py:82-87` handles only `"rate"`; `DEFAULT_CONTAINERS` at :36 | §5 now lists 3 changes |
| PyAV, ffprobe and OpenCV give "the same per-frame error in every container" | `mux_matrix.md` lines 38-39: raw cv2 6,032,562 vs 6,031,976 µs; `version_bump.json` stores maxima only and has no ffprobe | §2.3 reworded |
| "AVI cannot store VFR" | `pyav19_recheck.json`: `avi\|vfr` 6/7 written (max 830 µs), `avi_tb_rate\|vfr` 6/7 (14,671.667 µs) | §2.3, table 3.1 and §4.5 reworded: rounding, plus EINVAL when two frames land on one tick |
| fMP4/MP4 give OpenCV frame-exact seeks | `verify_method_reader.json`: gap60 5/10, drop50 7/10, while counts stay exact | §2.4 tables split by gaps; new §4.3; §4.2 no longer claims OpenCV seeks |
| In-memory sizes differ from file writes by 1-3 B | `verify_method_size_check.json`: mem == file on PyAV 19; my recount gives 0 B (40 rows), 1 B (112), 3 B (14), PyAV 18 vs 19 | §2.1 and §6 corrected; tag explanation added (inferred) |
| OpenCV 5 read fMP4 at 1/1e6 | `version_bump.json` has no such row | OpenCV 5 table relabelled; fMP4 1/1e6 is OpenCV 4.12 only |

**Weak items applied**

- Corpus scope: 2 real timestamp series, 5 borrowed; timestamps floored to µs.
- MKV frame pair: now measured on PyAV 19 (`pyav19_seek_ts_check.json`, both at pts 2704). The 11 µs gap is cited to the capture jsonl via VERIFY_provenance.md.
- FreeMoCap "reads ok" now says "without error, identity not checked" where that applies. Identity matches are cited only from the gap and killed files.
- DHT-stripped scope named; MSMF MKV 888/891; mjpeg2jpeg relabelled and extended to all DHT cameras.
- Folder CSV marked not tested; PyAV 18 FFmpeg string removed from the labels.
- Kill table: PyAV 19 reader rows added (including fMP4 per-frame), the result framed as one sample bounded by the write buffer, and the silent cut-frame risk added (§4.6).
- Overhead rows labelled by time base; the OpenCV 4 vs 5 comparison noted as confounded; Electron decode evidence scoped; the Rust rotation inference made conditional on the unpinned library; PyAV `stream.frames` = 0 noted.

**Verifier claims I rejected or corrected**

- **"Matroska quote contains `[@!JPEG]`, not on the page": rejected.** A curl of https://www.matroska.org/technical/codec_specs.html on 2026-11-09 returns the literal text "compressed separately as a [@!JPEG] image." The quote stays, with a note.
- **"PyAV seek 5/10 (NUT 4/10)": corrected.** `version_bump_check.py:58` uses 5 targets, so the result is 5/5 (NUT 4/5, raw 1/5), and it compares pts only. A frame-identity check was added (`pyav19_seek_ts_check.json`).

**Still NOT VERIFIED or open:** see §6. That covers:

- the cause of the template loss and of the size difference;
- files over 4 GiB;
- mjpegadump;
- PyAV 19 decode of the cut frame;
- the Rust turbojpeg version;
- FreeMoCap frame identity on clean and long fMP4 1/1e6 files;
- all timing questions (§5).
