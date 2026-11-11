# jpeg_passthrough: FINDINGS (goals G1, G5)

2026-11-09, Gerald (Windows 11, i7-14700K). Functional results only. There are no timing numbers here (see section 5).

Paths are relative to `research/skellycam_recording/recording_upgrade/` unless they are absolute.

**Labels**
- **measured**: a result file.
- **measured, PyAV 18 - background**: made with the skellycam venv (PyAV 18.0.0 = FFmpeg 8.1.2 libs). Not the implementation under test.
- **source**: a primary source, accessed 2026-11-09.
- **code**: file:line.
- **inferred**: reasoning, kept to a minimum.

**Implementation under test:** PyAV 19.0.2. Its bundled libs are libavformat 63.1.102 and libavcodec 63.1.102 (measured: `results/jpeg_passthrough/pyav19_recheck.json` meta).

**PyAV 19.0.2 result files**
- `version_bump.json`: c930e_720p_flash, written to files, read by OpenCV 5.0.0.93.
- `pyav19_recheck.json`: new today. All 7 sets in memory, a kill test, setup details and DHT decode.
- `pyav19_fmp4_tb_us_readers.json`: new today. OpenCV 4.12.0 and FreeMoCap read fMP4 written with time base 1/1e6.

**Background files (PyAV 18 writer):** `mux_matrix.json`/`.md`, `keyframe_setup.json`, `truncation.json`, `edge_cases.json` and `electron_check.json` (its media came from the PyAV 18 mux_matrix).

**Not PyAV-dependent:** `rotation.json`. It uses libjpeg-turbo 3.2.1, jpeglib and jpegtran only.

## 1. Questions answered

1. **G1.** Can Python (PyAV 19.0.2) store camera JPEG bytes in a container with no decode or re-encode, and get the same bytes back?
2. Which containers accept MJPEG? Do they change JPEG headers? How well do they keep real variable-frame-rate (VFR) capture timestamps?
3. **G5, compatibility side.** For each wrapper (folder of JPEGs, raw + sidecar, MKV, MP4, fMP4, MOV, AVI, NUT), check:
   - whether OpenCV and FreeMoCap's readers get the right frame count and frame-exact seeks;
   - whether the file still reads after a hard kill;
   - whether Chromium can play it.

   The throughput side is in section 5.
4. Edge cases: frames without DHT, extra bytes after the entropy-coded data, and lossless rotation as the Rust code does it.

## 2. Findings

### 2.1 Writing JPEG bytes as packets (G1)

**The recipe**

- `add_mux_stream("mjpeg", rate, width, height)` + `av.Packet(jpeg_bytes)` + `mux()` writes these 7 sets on PyAV 19.0.2 (measured: `pyav19_recheck.json` `A_matrix`):
  - containers: MKV, MP4, fMP4 (1 s and per-frame fragments), MOV, NUT, AVI and raw `.mjpeg`;
  - sets: c930e_720p_flash 891, c922_720p_flash 893, c922_1080p 19, c930e_1080p 19, c922_1600x896 19, c922_720p60 10 and generic_1080p 11 frames. That is 1,862 frames per container and mode.
- Every written output is byte-exact: 194 of 194 written outputs are SHA-256-identical per packet, in order, through PyAV 19.0.2 demux (measured: `pyav19_recheck.json` `A_matrix`).
  - 210 attempts: 7 sets × 15 container variants × VFR/CFR.
  - The 16 that were not written: 14 WebM, plus AVI VFR on c930e (2 variants).
  - Writes were in memory (BytesIO).
- The same holds for files written by PyAV 19.0.2 for c930e_720p_flash, in every container, VFR and CFR (measured: `version_bump.json`, `pyav19_bytes.byte_exact_all`).
- Background (measured, PyAV 18 - background: `mux_matrix.md` "Across all sets"):
  - 0 mismatches across 3 writers (PyAV VFR, PyAV CFR, ffmpeg CLI `image2pipe -c:v copy`);
  - 2 readers: PyAV demux and `ffmpeg -c:v copy -f image2`;
  - the Python raw+sidecar and folder-of-JPEG writers.
- `add_mux_stream` creates a stream "for muxing pre-encoded data without creating a :class:`.CodecContext`". It raises `'{format}' format does not support '{codec}' codec` when `avformat_query_codec` fails (source: PyAV 19.0.2 `av/container/output.py:265-269,306-310`, installed wheel).

**Settings it needs**

- Width and height are mandatory. Without them every container fails at the first mux with `ArgumentError ... returned 22; last error log: [<fmt>] dimensions not set` (measured: `pyav19_recheck.json` `D_setup` `*|nodims`).
- `is_keyframe` does not need to be set. With `is_keyframe=False`, 30 of 30 packets are still keyframe-flagged in MKV, MP4, MOV, AVI, NUT and raw (measured: `pyav19_recheck.json` `D_setup` `*|mux_stream|kf=False`).
  - FFmpeg sets the flag for intra-only codecs: "`if (sti->is_intra_only)` / `pkt->flags |= AV_PKT_FLAG_KEY;`" (source: FFmpeg n9.0.2 `libavformat/mux.c:820-821`, https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/libavformat/mux.c).
  - On the 891-frame c930e set: measured, PyAV 18 - background (`keyframe_setup.json` `keyframe`).
- Avoid `add_stream_from_template` (measured: `pyav19_recheck.json` `D_setup` `template_vfr_file`):
  - With VFR timestamps in a file, MP4 and MOV hold 29 of 30 packets (ffprobe `nb_read_packets` 29), and AVI fails with EINVAL (`non monotonically increasing dts ... 2 >= 2`).
  - The same happened on PyAV 18 (measured, PyAV 18 - background: `keyframe_setup.json` `setup`).
  - With CFR timestamps in memory, MP4 and MOV kept 30 of 30 (`D_setup` `*|template|kf=True`).
  - Root cause: NOT VERIFIED. `add_mux_stream` has no such loss (above).

**WebM**

- WebM refuses MJPEG in PyAV 19.0.2 on all 7 sets with `ValueError: 'webm' format does not support 'mjpeg' codec` (measured: `pyav19_recheck.json`).
- The ffmpeg CLI also refuses it (measured, PyAV 18 - background: `mux_matrix.md`).
- source: FFmpeg n9.0.2 `libavformat/matroskaenc.c:3744-3747`. `webm_query_codec` accepts only `ff_webm_codec_tags`, which are V_VP8, V_VP9, V_AV1, A_VORBIS, A_OPUS and D_WEBVTT/* (`libavformat/matroska.c:110-124`).
- source: https://www.webmproject.org/docs/container/ says "Video codec SHOULD be VP8 *or* VP9".

**What the containers register and write**

- MKV registers MJPEG as `V_MJPEG`: "Motion JPEG is a video compression format in which each video frame or interlaced field is compressed separately as a [@!JPEG] image." with "Initialization: none" (source: https://www.matroska.org/technical/codec_specs.html; FFmpeg n9.0.2 `libavformat/matroska.c:86`).
- MP4 stores MJPEG as an `mp4v` sample entry with object type 0x6C, "Visual ISO/IEC 10918-1" (source: https://mp4ra.org/registered-types/object-types; FFmpeg n9.0.2 `libavformat/isom.c:55`).
- ffprobe shows `codec_tag_string` `mp4v` for fMP4 written by PyAV 19.0.2 (measured: `pyav19_recheck.json` `B_fmp4_tb_us_ffprobe`).

**Container overhead**

PyAV 19.0.2, c930e_720p_flash VFR, 891 frames, 49,314,521 payload bytes, in-memory sizes (measured: `pyav19_recheck.json` `A_matrix` `size_bytes`):

| Container | Overhead |
|---|---|
| MKV | 40,253 B |
| MP4 (1/90000) | 11,232 B |
| MP4 (1/1e6) | 11,936 B |
| fMP4 1 s | 11,738 B |
| fMP4 per frame | 117,521 B |
| MOV | 11,139 B |
| NUT | 25,376 B |
| raw | 0 B |

- These are 1-3 B smaller than the PyAV 18 file writes (e.g. MKV VFR 49,354,777 B in `mux_matrix.md`). Cause NOT VERIFIED. The payload bytes are identical either way.

**Rust reference**

- The Rust reference does not pass JPEGs through. It pipes them to ffmpeg with libx264 (code: `git show upstream/sfn26:skellycam-rust/src/recording/recorder.rs:1-6,38-46,141-155`, cited from NOTES.md §2, not re-read).

### 2.2 JPEG headers and edge cases

**Headers**

- No muxer changed any JPEG header. Extraction is SHA-256-identical to the input, so no APP0/AVI1 was added and no DHT was inserted (measured: `pyav19_recheck.json`; measured, PyAV 18 - background: `mux_matrix.json`).
- Marker layouts (measured: `edge_cases.json` `mjpeg2jpeg.*.in_markers`):
  - Logitech C922 and C930e: `DQT SOF0 DHT DHT DHT DHT COM APP0 DRI SOS`;
  - generic camera: `APP0(JFIF) DQT DQT SOF0 DHT DHT DHT DHT SOS`.
- All 3 cameras carry 4 DHTs equal to the standard tables (measured: `edge_cases.json` `dht_vs_standard`, all True; `dht_tables_count` 4).

**DHT-stripped frames**

- They stay byte-exact in MKV, MP4, fMP4 1 s, MOV, AVI (1/fps), NUT and raw on PyAV 19.0.2 (30/30 each; measured: `pyav19_recheck.json` `D_setup` `*|dht_stripped`).
- PyAV 19.0.2's mjpeg decoder decodes them to pixels identical to the originals (measured: `pyav19_recheck.json` `E_decode_dht_stripped`):
  - c930e 30/30;
  - c922 30/30;
  - generic 11/11.
- FFmpeg installs default Huffman tables at decoder init (source: FFmpeg n9.0.2 `libavcodec/mjpegdec.c:62,148`, `init_default_huffman_tables`).
- cv2.imdecode, Pillow and djpeg 3.2.1 behave the same (measured: `edge_cases.json` `decoders`; cv2/Pillow/djpeg are not PyAV-dependent).
  - djpeg exits non-zero on the generic camera's original and stripped frames alike: "535 extraneous bytes before marker 0xd9".
  - Its stripped and original outputs are still equal (11/11).

**Bitstream filters**

- `mjpeg2jpeg` adds 438 B (Logitech) or 419 B (generic) per frame and leaves Logitech frames with two sets of tables. It is not byte-exact and is opt-in only (measured, PyAV 18-era CLI run: `edge_cases.json` `mjpeg2jpeg`).
- `mjpegadump` adds 44 B. That is measured only in NOTES.md §3 as a one-off whose output files were deleted. Treat it as NOT VERIFIED by a result file.

### 2.3 Timestamps (real VFR capture times)

**Accuracy by container**

- MP4, MOV, NUT, fMP4 1 s and fMP4 per-frame with stream `time_base = 1/1,000,000` keep the real timestamps exactly: max error 0 µs on all 7 sets, strictly increasing (measured: `pyav19_recheck.json` `A_matrix`, `*_tb_us|vfr`).
- **This closes the open fMP4 1/1e6 question:**
  - ffprobe reads the PyAV 19.0.2 fMP4 1/1e6 files with 0 µs error (measured: `pyav19_recheck.json` `B_fmp4_tb_us_ffprobe`);
  - OpenCV 4.12.0 `CAP_PROP_POS_MSEC` also gives 0 µs on c930e_720p_flash (measured: `pyav19_fmp4_tb_us_readers.json`).
- At the muxers' default 1/90000 the max error is 5.556 µs (MP4, MOV, fMP4, NUT; measured: `pyav19_recheck.json`).
- MKV is fixed at 1 ms. The max error is 470 µs (VFR), and c930e frames 81/82, which are 11 µs apart, get the same timestamp (`strictly_increasing` False) (measured: `pyav19_recheck.json` `c930e_720p_flash|mkv|vfr`).
  - source: FFmpeg n9.0.2 `libavformat/matroskaenc.c:3602-3603`, "ms precision is the de-facto standard timescale for mkv files" / `avpriv_set_pts_info(st, 64, 1, 1000);`.

**AVI cannot store VFR**

- With time base 1/fps the max error is 14,671.667 µs.
- On c930e it fails with `non monotonically increasing dts ... 81 >= 81` (1/30) or `1622 >= 1622` (muxer default 1/600) (measured: `pyav19_recheck.json`).
- The AVI muxer writes empty packets to fill gaps (source: FFmpeg n9.0.2 `libavformat/avienc.c:745-762`).
- PyAV's default AVI stream time base is 1/600 even for CFR (measured: `pyav19_recheck.json` `avi|cfr` `stream_tb` 1/600). Read back, OpenCV reports 17,820 frames for 891 (measured: `version_bump.json`, OpenCV 5.0.0.93). Setting `st.time_base = 1/fps` fixes this (`avi_tb_rate|cfr`: 891).

**Formats without stored timestamps**

- Raw `.mjpeg` stores no timestamps. Readers assume 25 fps, and the error reaches 6,031,976 µs on c930e VFR (measured: `pyav19_recheck.json`).
- The sidecar index returned the exact int64 ns timestamps (7/7; measured, PyAV 18 - background: `mux_matrix.json` `sidecar_reader_ts_exact_ns`; this is a Python writer, not PyAV-dependent).

**Readers agree**

- PyAV pts, ffprobe `pts_time` and OpenCV `CAP_PROP_POS_MSEC` give the same per-frame error in every container (measured: `version_bump.json`, `pyav19_ts` = `cv5_ffmpeg_ts`; measured, PyAV 18 - background: `mux_matrix.md`).

### 2.4 Frame count and seek in OpenCV and FreeMoCap (G5 compatibility)

**How FreeMoCap reads**

- `VideoHelper.from_video_path` opens `cv2.VideoCapture(str(video_path))` and stores `CAP_PROP_FRAME_COUNT` (code: freemocap 5632778a, `freemocap/core/pipeline/posthoc/video_group_helper.py:151,159`).
- A `VideoGroup` raises unless every camera reports the same count (code: `video_group_helper.py:381-385`).
- File discovery accepts only `{".mp4", ".avi", ".mov", ".mkv", ".webm"}` (code: skellycam `skellycam/core/recorders/videos/parse_video_filename.py:18`).
- OpenCV's frame count is `nb_frames`, or `floor(duration × fps + 0.5)` when `nb_frames` is 0 (source: OpenCV 4.12.0 `modules/videoio/src/cap_ffmpeg_impl.hpp:1980-1989`). Seek converts a frame index through fps (`:1991-1995`).

**Results on files written by PyAV 19.0.2 (c930e_720p_flash)**

- **fMP4 1/1e6, 1 s and per-frame fragments, read by OpenCV 4.12.0** (measured: `pyav19_fmp4_tb_us_readers.json`):
  - `CAP_FFMPEG` count 891, frames read 891, seek 10/10;
  - `CAP_ANY` picks FFMPEG with count 891;
  - FreeMoCap `VideoHelper` `frame_count` 891, with 4/4 reads ok.
- **All containers, read by OpenCV 5.0.0.93** (measured: `version_bump.json`):

  | Container | Count | Seek |
  |---|---|---|
  | MP4, MOV, fMP4 (1/90000 and 1/1e6) | exact | 10/10 |
  | MKV VFR | 888 for 891 | 5/10 |
  | NUT VFR | 887 | 6/10 |
  | NUT CFR | 890 | 10/10 |
  | raw `.mjpeg` | -192153584101141 | 0/10 |

- `CAP_MSMF` reads 0 frames of MJPEG from MP4 or fMP4 but reads MKV, MOV and AVI (1/fps) (measured: `version_bump.json` `cv5_MSMF`; `pyav19_fmp4_tb_us_readers.json` `cv2_msmf.frames_read` 0).

**Background (measured, PyAV 18 - background: `mux_matrix.md` "Across all sets"), all 7 sets, OpenCV 4.12.0**

- MP4, MOV and fMP4 (VFR and CFR): count exact 7/7 and seek 70/70.
- MKV VFR: count exact 6/7 and seek 65/70.
- NUT: count exact 0/7 in every mode.
- AVI with PyAV's default time base: count exact 0/7.
- Raw `.mjpeg` and raw+sidecar: seek 0/70.
- Folder via the `frame_%06d.jpg` pattern: count exact 7/7 and seek 70/70.
- FreeMoCap `VideoHelper` refuses:
  - the folder (count matched 0/7);
  - raw `.mjpeg` (ValidationError).

### 2.5 Hard kill (adjunct to G2)

**Setup.** A child process muxes 600 c930e_720p_flash frames with PyAV 19.0.2 and calls `os._exit(1)` without closing. PyAV 19.0.2 demux results (measured: `pyav19_recheck.json` `C_killed`):

| Container | Complete byte-exact frames of 600 | Packets read |
|---|---|---|
| MKV | 597 | 597 |
| MP4 | not readable ("moov atom not found") | - |
| MOV | not readable ("moov atom not found") | - |
| fMP4 1 s, 1/90000 | 578 | 579 |
| fMP4 1 s, 1/1e6 | 578 | 579 |
| fMP4 per frame | 596 | 597 |
| AVI (1/fps) | 597 | 598 |
| NUT | 597 | 598 |
| raw `.mjpeg` | 597 | 598 |

- The counts are identical to PyAV 18 (measured, PyAV 18 - background: `truncation.json` `killed`).
- The last packet is a cut JPEG ("+1 partial"). On PyAV 18 it decoded without error in most containers and raised `InvalidDataError` in fMP4 per-frame (measured, PyAV 18 - background: `truncation.json` `decode_errors`). PyAV 19.0.2 decode of the partial frame was not run.

**OpenCV and FreeMoCap on the killed files** (measured, PyAV 18 - background: `truncation.json`):

| Container | OpenCV count | FreeMoCap |
|---|---|---|
| MKV | -276701161105643264 | ValidationError |
| AVI | 0 | ValidationError |
| raw | garbage | ValidationError |
| fMP4 1 s | 582 (579 readable) | 3/4 reads ok |
| NUT | 595 | 4/4 reads ok |

**Other crash results (background)**
- The Python raw+sidecar writer kept 409 of 600 frames, all exact (measured, Python writer: `truncation.json` `raw_sidecar`).
- Byte truncation at 50%/90% keeps 445/801-802 exact frames in every container except plain MP4/MOV, which are unreadable (measured, PyAV 18 - background: `truncation.json` `truncated`).
- A 1,154,485,550 B OpenDML AVI (6000 frames, 1 `AVIX` RIFF) reads 6000/6000 byte-exact in PyAV, with OpenCV seek 10/10, MSMF 6000 and FreeMoCap 6000 (measured, PyAV 18 - background: `truncation.json` `large_avi`).

### 2.6 Chromium / Electron (G8 cross-check)

Measured, PyAV 18-written files - background: `electron_check.json`.

- **`<video>`.** Electron 35.7.5 (Chrome 134.0.6998.205) and 45.2.3 (Chrome 156.0.8078.80) play MJPEG from no container:
  - MKV, MP4, fMP4 1 s and MOV fail with error 4 `DEMUXER_ERROR_NO_SUPPORTED_STREAMS`;
  - AVI, NUT and raw fail with `DEMUXER_ERROR_COULD_NOT_OPEN`;
  - the VP9 WebM control plays and seeks.
- **MIME checks.** `canPlayType` is "" for every MJPEG MIME tested, and MSE `isTypeSupported` is false. `video/x-matroska` alone gives "maybe" in 45.2.3 only.
- **Single frames.** `<img>`, `createImageBitmap` and `ImageDecoder` decode every test JPEG in both versions: original, DHT-stripped, generic with extra bytes, and rotated 4:4:0 (ImageDecoder format I422, or BGRX for 4:4:0).
- inferred: the failure is the codec, not the muxer version, so it is expected on PyAV 19 files too. The re-run was not done.

### 2.7 Lossless rotation (Rust parity)

Measured: `rotation.json`, libjpeg-turbo 3.2.1, not PyAV-dependent.

- libjpeg-turbo 3.2.1 `tj3Transform` through ctypes (options 0, the Rust call) is DCT-exact in 228 of 228 frame × rotation cases.
- jpegtran gives the same bytes in 228/228.
- The control (block-grid rotation without coefficient permutation) matches 0/228, so the test can fail.
- The RGB max abs diff is ≤ 5. rot90/270 output is 4:4:0 (TJSAMP 4).
- The Rust-equivalent legacy `tjTransform` returns 0 (rotated) on 195 of 228 cases. All 33 generic_1080p cases return -1 (`tj3_warnings` 33).
- The Rust code keeps the output only when `ret == 0` (code: `git show upstream/sfn26:skellycam-rust/src/camera_group/jpeg_transform.rs`, the `tjTransform(...)` call followed by `if ret == 0 && !dst_buf.is_null()`).
- inferred: with that logic a rotated generic camera would record unrotated frames without any error.

### 2.8 Version bump

- PyAV 19.0.2 changes no passthrough result relative to PyAV 18 (measured: `version_bump.json`, `pyav19_recheck.json`). That covers write success, byte-exactness, timestamp errors, WebM refusal, AVI VFR EINVAL, kill survivors and template loss.
- opencv-python 5.0.0.93 gives the same counts and seeks as 4.12.0 on the c930e set (measured: `version_bump.json`).

## 3. Comparison tables

### 3.1 Container properties for camera-JPEG passthrough

PyAV 19.0.2 writer unless marked [18].

| Property | Folder .jpg + CSV | raw .mjpeg + sidecar | MKV | MP4 (1/1e6) | fMP4 1 s (1/1e6) | MOV (1/1e6) | AVI (1/fps) | NUT (1/1e6) |
|---|---|---|---|---|---|---|---|---|
| Bytes exact (7 sets) | yes [18] | yes [18] | yes | yes | yes | yes | yes (CFR) | yes |
| VFR timestamp error | exact in CSV (ns) [18] | exact in index (ns) [18] | ≤470 µs, merges frames 11 µs apart | 0 µs | 0 µs | 0 µs | VFR impossible | 0 µs |
| OpenCV count exact, c930e VFR | yes [18] | no [18] | no (888/891) | yes | yes | yes | n/a (VFR refused); CFR yes | no (887) |
| OpenCV seek exact, c930e | 10/10 [18] | 0/10 [18] | 5/10 | 10/10 | 10/10 | 10/10 | CFR 10/10 | 6/10 |
| FreeMoCap VideoHelper opens | no [18] | no [18] | yes, wrong count on c930e VFR [18] | yes [18] | yes (891, 4/4) | yes [18] | yes [18] | yes, count short [18] |
| CAP_MSMF reads | yes, CAP_IMAGES [18] | no [18] | yes | no | no | yes | yes | no [18] |
| Readable after hard kill | not tested | 409/600 (Python buffered) [18] | 597/600 | no | 578/600 | no | 597/600 | 597/600 |
| OpenCV count on killed file | - | - | negative [18] | - | 582 vs 579 [18] | - | 0 [18] | 595 [18] |
| Chromium `<video>` | n/a | no [18] | no [18] | no [18] | no [18] | no [18] | no [18] | no [18] |
| Overhead per 891 c930e frames | +CSV | 20 B/frame index [18] | 40,253 B | 11,936 B | 11,738 B | 11,843 B | 27,515 B (CFR) | 26,908 B |
| Files per camera-minute at 30 fps (arithmetic) | 1,801 | 2 | 1 | 1 | 1 | 1 | 1 | 1 |

**Sources for the table**
- `pyav19_recheck.json`, `pyav19_fmp4_tb_us_readers.json`, `version_bump.json`.
- [18] = `mux_matrix.json`, `truncation.json`, `electron_check.json`, measured, PyAV 18 - background.
- The AVI and MOV-1/1e6 overheads are from `pyav19_recheck.json` c930e rows (AVI CFR, MOV `mov_tb_us|vfr`).
- The c930e OpenCV rows for MKV, NUT, MP4, fMP4 1/90000, MOV and AVI are from `version_bump.json` (OpenCV 5.0.0.93); the fMP4 1/1e6 row is OpenCV 4.12.0.

### 3.2 fMP4 fragment choice (c930e_720p_flash, PyAV 19.0.2)

| | fMP4 1 s fragments | fMP4 per-frame fragments |
|---|---|---|
| Overhead (891 frames) | 11,738 B | 117,521 B |
| Complete frames after kill at 600 | 578 | 596 |
| Timestamp error (1/1e6) | 0 µs | 0 µs |
| OpenCV 4.12 count / seek / FreeMoCap (1/1e6) | 891 / 10/10 / 891 | 891 / 10/10 / 891 |

Measured: `pyav19_recheck.json`, `pyav19_fmp4_tb_us_readers.json`.

## 4. Implications for the plan

1. **G1 is met by PyAV 19.0.2 alone.** Use `add_mux_stream("mjpeg", rate, width=w, height=h)` + `av.Packet(bytes)`. Always pass width/height, skip `is_keyframe`, and do not use `add_stream_from_template` (§2.1).
2. **Leading container candidate: fMP4 with `st.time_base = Fraction(1, 1_000_000)`.** It is the only tested option that is byte-exact, keeps exact µs VFR timestamps, gives OpenCV/FreeMoCap exact counts and seeks on a clean file, and stays readable after a kill (§2.3, §2.4, §2.5, table 3.2). The fragment length trades overhead against frames lost on a kill (table 3.2). The mux cost per container is still pending (§5).
3. **Avoid plain MP4/MOV as the recording format.** A killed file is unreadable (§2.5). They remain fine as a finalize/remux target (inferred).
4. **Rule out these containers for FreeMoCap-compatible recordings:**
   - MKV: 1 ms grid; wrong OpenCV count and seek on jittery VFR (§2.3, §2.4);
   - NUT: count always short (§2.4);
   - AVI: no VFR, and the 1/600 default time base trap (§2.3);
   - raw `.mjpeg`: no timestamps, garbage count (§2.3, §2.4);
   - WebM: refused (§2.1).
5. **Keep a per-frame timestamp sidecar regardless of container.** OpenCV's count on recovered files is wrong (killed fMP4 582 vs 579 readable; §2.5), and FreeMoCap trusts `CAP_PROP_FRAME_COUNT` (§2.4). The plan should have FreeMoCap count frames from the sidecar or a PyAV packet count rather than OpenCV's property (inferred from §2.4/§2.5).
6. **A folder of JPEGs costs FreeMoCap compatibility.** VideoHelper cannot open it and it means 1,801 files per camera-minute (table 3.1). Its throughput and Defender cost decide G5's "is the wrapper significant" and are pending (§5; write_throughput topic).
7. **G8/G9 cannot be decided by the container choice.** Chromium plays MJPEG from no container (§2.6). Playback needs per-frame JPEG decode in the renderer or a proxy encode (chromium_codecs / chromium_sync_scrub topics).
8. **Rotation, if kept.** Port `tj3Transform` with ctypes and accept `TJERR_WARNING` outputs. Do not copy Rust's `ret == 0` check (§2.7). For 4:2:0 or odd-size cameras, add `TJXOPT_PERFECT` or `TRIM` (inferred; NOTES.md §8 cites `turbojpeg.h:1130-1142`).
9. **PyAV upgrade.** No passthrough gain or loss from PyAV 18 → 19 (§2.8). The decision rests on other topics.

## 5. Pending tonight's bench

None of these has run. `results/jpeg_passthrough/bench/` and `BENCH.md` do not exist yet.

| Timed question | bench_manifest id | Notes for the queue |
|---|---|---|
| Mux CPU and wall µs/frame per container, and close/trailer ms, vs `pkt_only`, `raw_sidecar` and `jpg_folder` baselines, at 720p and 1080p, 1 camera per process, page cache | `jp_mux_cost` (priority 1) | See the switch and the fMP4 entry below |
| The same with `FlushFileBuffers` after close (cost of getting data to disk) | `jp_mux_cost_fsync` (priority 2) | Same changes as `jp_mux_cost` |
| Lossless rotation cost per frame (tj3Transform rot90/180/270), 720p and 1080p | `jp_rotate_cost` (priority 2) | PyAV-independent; DLL at the old scratchpad `.../106dc0c8-.../scratchpad/jpeg_passthrough/ljt321/bin/turbojpeg.dll` (present at 16:4x; fallback download in NOTES.md §14). The Rust comment "~1-2ms per frame" (code: `jpeg_transform.rs:3-4`) is NOT VERIFIED until then |
| Multi-camera disk throughput, and the Defender cost of a JPEG folder vs one container | write_throughput topic items | Its earlier BENCH.md is contaminated; do not reuse its numbers here |

**Changes needed for the mux benches**
- **Switch to PyAV 19.0.2.** The manifest commands use `.venv/Scripts/python.exe` (PyAV 18). `bench_mux.py` has no PEP 723 header, and its workers run under `sys.executable` (code: `scripts/jpeg_passthrough/bench_mux.py:141`).
  - A candidate command is `uv run --no-project --python 3.12 --with av==19.0.2 --with numpy --with psutil python research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/bench_mux.py --tag default_pyav19`.
  - It has not been smoke-tested yet.
- **Add `fmp4_1s_tb_us`.** The leading candidate is not in its container list: `jp_io.CONTAINERS` has no fMP4 1/1e6 entry (code: `scripts/jpeg_passthrough/jp_io.py:31-49`). A one-line addition is needed.

## 6. Not tested / limits / NOT VERIFIED

**Not re-run on PyAV 19.0.2 (background only)**
- OpenCV 4.12 and FreeMoCap reads of every container except fMP4 1/1e6.
- `ffmpeg -c:v copy` extraction.
- Truncated-file reads and the >1 GiB AVI.
- The Electron `<video>` check.
- PyAV 19 decode of the partial last frame after a kill.

**Coverage gaps**
- The PyAV 19 matrix in `pyav19_recheck.json` was written in memory (BytesIO), not to files. Its file sizes differ from file writes by 1-3 B (cause NOT VERIFIED).
- OpenCV checks on PyAV 19 files cover c930e_720p_flash only (the most jittery set). The other 6 sets were read by OpenCV only for PyAV 18 files.
- Kill tests used `os._exit` (user-space buffers lost). Power loss, OS crash and per-packet flush policies were not tested; flushing belongs to the crash_resilience topic.

**NOT VERIFIED**
- MP4/MKV/NUT files over 4 GiB were not written. The `co64` switch is cited only from source (FFmpeg n9.0.2 `libavformat/movenc.c:177-179,204-208`).
- The `mjpegadump` +44 B result (no result file).
- The root cause of the template frame loss.

**Not in scope or not covered**
- Linux/macOS readers, and AVFoundation/QuickTime playback of MJPEG MOV/MP4.
- Chrome browser (only Electron).
- MSE/WebCodecs VideoDecoder for MJPEG.
- Audio.
- Whether any camera used with skellycam omits DHT: none of the 3 corpus cameras does (§2.2).

## 7. How to reproduce

Run from the repo root `C:/Users/Dom/GitHub/freemocap/skellycam`. Run `unset ELECTRON_RUN_AS_NODE` first for the Electron step.

```
# PyAV 19.0.2 (implementation under test)
uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/pyav19_recheck.py          # -> results/jpeg_passthrough/pyav19_recheck.json
uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/pyav19_recheck.py --write-fmp4-us C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/jpeg_passthrough/fmp4_tb_us
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/fmp4_tb_us_cv2_check.py C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/jpeg_passthrough/fmp4_tb_us   # reader only (OpenCV 4.12, FreeMoCap) -> pyav19_fmp4_tb_us_readers.json
uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/version_bump_check.py      # PyAV 19.0.2 + opencv-python 5.0.0.93 -> version_bump.json

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
- Media is written under `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/jpeg_passthrough/` and deleted by the new scripts.
- The FFmpeg n9.0.2 and OpenCV 4.12.0 source files cited above were fetched from raw.githubusercontent.com into `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/jpeg_passthrough/src/`.
