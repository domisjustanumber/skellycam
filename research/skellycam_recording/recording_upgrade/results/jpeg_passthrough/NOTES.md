# jpeg_passthrough - transcode-less storage of camera JPEG bytes (goals G1, G5 compat side)

2026-11-09, machine Gerald (Windows 11, i7-14700K). Functional tests only: no timing, throughput or CPU number from this stage is reported (other agents were running). Timing work is in benchmark scripts listed at the end and in the bench manifest.

Labels: **measured** = result file written in this study (path given) or a prior study's result file; **source** = primary source (spec, library source at a pinned tag, vendor doc), accessed 2026-11-09; **code** = repo source file:line; **inferred** = reasoning, kept short.

## 0. Bottom line (each point is backed in the sections below)

- MKV, MP4, fragmented MP4, MOV, AVI and NUT all store the camera's JPEG bytes as packets with no decode or re-encode from Python (PyAV 18.0.0 `add_mux_stream`), and every reader we used gives back SHA-256-identical bytes. No muxer changed any JPEG header. measured: `mux_matrix.json`, `edge_cases.json`
- WebM cannot hold MJPEG: FFmpeg's WebM muxer accepts only VP8/VP9/AV1 video, and the WebM guidelines say the video codec "SHOULD be VP8 or VP9". measured + source (section 2)
- Chromium (Electron 35.7.5 / Chrome 134 and Electron 45.2.3 / Chrome 156) plays MJPEG in none of the containers: `<video>` fails with `DEMUXER_ERROR_NO_SUPPORTED_STREAMS` (MKV/MP4/MOV) or `DEMUXER_ERROR_COULD_NOT_OPEN` (AVI/NUT/raw). Chromium does decode the same JPEGs one by one through `<img>`, `createImageBitmap` and WebCodecs `ImageDecoder`, including DHT-stripped, extra-bytes and rotated 4:4:0 frames. measured: `electron_check.json`
- Real VFR timestamps survive exactly (0 us error) in MP4, MOV and NUT when the stream time base is set to 1/1,000,000, and within 6 us at the muxers' default 1/90000 (MP4, MOV, fMP4, NUT); MKV is fixed at 1 ms; AVI cannot store VFR (FFmpeg pads with empty frames or refuses). fMP4 was not run with a 1/1e6 time base. measured (section 6)
- OpenCV, and therefore FreeMoCap's readers, can report a wrong frame count and seek to the wrong frame: MKV on the jittery c930e VFR capture (888 of 891, seek 5/10), NUT always (count 1+ short), AVI written with PyAV's default time base (count about 20x). MP4/MOV/fMP4 were frame-exact in every case tested. measured (section 5)
- A file killed mid-recording stays readable as MKV, fMP4, AVI, NUT, raw MJPEG or raw+sidecar; plain MP4/MOV are unreadable (as in prior P11). But FreeMoCap's `VideoHelper` refuses the killed MKV and AVI because OpenCV's frame count is garbage or 0. measured: `truncation.json`
- Lossless rotation in Python with libjpeg-turbo `tj3Transform` (the call the Rust code makes) is bit-exact in the DCT domain on all 228 frame x rotation cases; the Rust code's error handling would silently skip rotation on every generic-camera frame. measured: `rotation.json`
- Newer PyAV 19.0.2 (FFmpeg 9 libs) and opencv-python 5.0.0.93 (FFmpeg 7.1 libs) change none of these results. measured: `version_bump.json`

## 1. Inputs, tools, method

- Frames: real camera JPEG bytes from `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus/` (index.json). All MJPEG sets were used: c930e_720p_flash (891), c922_720p_flash (893), c922_1080p (19), c930e_1080p (19), c922_1600x896 (19), c922_720p60 (10), generic_1080p (11). No frame was looped in the functional matrix; the large-AVI test loops c922_1080p to 6000 frames (stated there).
- Real per-frame timestamps: the two flash sets have MF sample times per frame (`os_timestamp_ns`, QPC-based) in `research/usb_cameras/results/windows/Gerald/timing/flash_run1_repositioned/capture/*.frames.jsonl`, the same capture the corpus was split from; `jp_common.real_timestamps_ns` checks `payload_bytes` == corpus frame size for every frame (all matched). code: `scripts/jpeg_passthrough/jp_common.py`
- These timestamps contain real jitter: c930e_720p_flash intervals run 0.011 ms to 48.10 ms (median 32.0 ms); frames 81 -> 82 are 11 us apart. measured (computed from the jsonl above; printed during this study, reproduced by `real_timestamps_ns`)
- Sets without recorded timestamps (1080p, 1600x896, generic) reuse the c930e_720p_flash intervals ("borrowed" jitter); c922_720p60 uses them halved. code: `jp_common.jitter_timestamps_ns`, `mux_matrix.DATASETS`
- DHT-stripped frames are made by removing every DHT segment before SOS (`jp_common.strip_dht`). code
- Versions (measured, in each result file's meta): skellycam .venv Python 3.12.13, PyAV 18.0.0 (bundled FFmpeg libs libavformat 62.12.102 / libavcodec 62.28.102 = FFmpeg 8.1.2, `av.ffmpeg_version_info` prints `8.1.2`), OpenCV 4.12.0 (its FFmpeg backend reports avformat 58.76.100 / avcodec 58.134.100 in `cv2.getBuildInformation()`), Pillow 12.3.0, ffmpeg/ffprobe CLI 9.0.2 gyan full build (libavformat 63.1.102). Isolated uv envs: PyAV 19.0.2 (libavformat 63.1.102), opencv-python 5.0.0.93 (avformat 61.7.100), jpeglib 1.0.2, PyTurboJPEG 2.6.1, numpy 2.2.6.
- Third-party download: libjpeg-turbo 3.2.1 Windows x64 build `https://github.com/libjpeg-turbo/libjpeg-turbo/releases/download/3.2.1/libjpeg-turbo-3.2.1-vc-x64.exe` (sha256 1f05bc3ed1585e6b12a8b0c24c8c5f07b1f6d90d01b4b709b331bedc9d6e5838), extracted with 7-Zip into the scratchpad (`.../scratchpad/jpeg_passthrough/ljt321/`; provides turbojpeg.dll, jpegtran.exe, djpeg.exe). Library sources read at pinned tags: FFmpeg n8.1.2 and n9.0.2 (raw.githubusercontent.com/FFmpeg/FFmpeg/<tag>/...), OpenCV 4.12.0 `modules/videoio/src/cap_ffmpeg_impl.hpp`, turbojpeg.h from the 3.2.1 package.
- Readers applied to every output: ffprobe (`-count_packets -show_streams -show_entries packet=...`), PyAV demux (SHA-256 per packet, pts, full decode), `ffmpeg -i X -c:v copy -f image2 %06d.jpg` (SHA-256 per file), `cv2.VideoCapture(path, CAP_FFMPEG)` (props, sequential read, POS_MSEC, seek), `cv2.VideoCapture(path)` (= FreeMoCap VideoHelper's call), `CAP_MSMF`, and FreeMoCap's real `VideoHelper` class imported from the read-only freemocap repo. code: `scripts/jpeg_passthrough/jp_io.py`
- cv2 seek test: `set(CAP_PROP_POS_FRAMES, k)` then `read()`, pass if the frame's SHA-1 equals the k-th frame of a fresh sequential read, targets k = 0, 1, 2, n/3, n/2, n-2, n-1, 5, n/2, 3 (backward seeks included). Sequential frame k is tied to input JPEG k by the byte-exact packet test plus a mean-abs-diff check against `cv2.imdecode(input k)` vs `input k+-1` (`mad_vs_imdecode_input_offsets` in mux_matrix.json).
- How FreeMoCap opens files: `VideoNode` uses `cv2.VideoCapture(str(video_path), cv2.CAP_FFMPEG)` and `CAP_PROP_FRAME_COUNT` for progress (code: freemocap `freemocap/core/pipeline/posthoc/video_node.py:297,301`); `VideoHelper.from_video_path` uses `cv2.VideoCapture(str(video_path))` and stores `CAP_PROP_FRAME_COUNT` as the frame count (`video_group_helper.py:151,159`), reads by sequential `grab()` (`video_group_helper.py:235-247`), and a `VideoGroup` raises unless all cameras report the same frame count (`video_group_helper.py:381-385,531`). File discovery accepts only `.mp4 .avi .mov .mkv .webm` (skellycam `skellycam/core/recorders/videos/parse_video_filename.py:18`, imported at `video_group_helper.py:15`; freemocap `api/http/playback/playback_router.py:47`). freemocap repo at commit 5632778a.

## 2. (a) Writing camera JPEGs as packets from Python

| container (PyAV format) | PyAV `add_mux_stream` write | ffmpeg `-f image2pipe -c:v copy` | codec tag written | stream time_base chosen by muxer (VFR input) |
|---|---|---|---|---|
| MKV (`matroska`) | ok | ok | V_MJPEG (ffprobe tag 0) | 1/1000 |
| WebM (`webm`) | ValueError: 'webm' format does not support 'mjpeg' codec | `Could not write header (incorrect codec parameters ?): Invalid argument` | - | - |
| MP4 (`mp4`) | ok | ok | `mp4v` (OTI 0x6C) | 1/90000 |
| fMP4 1 s fragments | ok | ok | `mp4v` | 1/90000 |
| fMP4 one fragment per frame | ok | ok | `mp4v` | 1/90000 |
| MOV (`mov`) | ok | ok | `jpeg` | 1/90000 |
| AVI (`avi`) | ok only if timestamps strictly increase after rounding; default time base 1/600 pads (see 6) | ok (CFR) | `MJPG` | 1/600 |
| NUT (`nut`) | ok | ok | `MJPG` | 1/90000 |
| raw `.mjpeg` (`mjpeg` muxer) | ok | ok | - | 1/90000 (no timestamps stored) |
| raw `.mjpeg` + binary index sidecar (Python file writes) | ok | n/a | - | index holds int64 ns |
| folder of `.jpg` + timestamps.csv (Python) | ok | n/a | - | CSV holds int64 ns |

measured: `mux_matrix.json` (rows `write`), `keyframe_setup.json`.

Minimal working PyAV recipe (measured working for every non-WebM container; code `jp_io.pyav_write`):

```python
c = av.open(path, "w", format=fmt, options=muxer_opts)            # e.g. {"movflags": "frag_keyframe+empty_moov+default_base_moof", "min_frag_duration": "1000000"}
st = c.add_mux_stream("mjpeg", rate=30, width=w, height=h)        # no codec context, nothing is encoded
st.time_base = Fraction(1, 1_000_000)                              # mp4/mov/nut: keep us timestamps exactly; AVI: Fraction(1, fps)
pkt = av.Packet(jpeg_bytes); pkt.stream = st
pkt.time_base = Fraction(1, 1_000_000); pkt.pts = pkt.dts = t_us   # PyAV rescales to st.time_base inside mux
c.mux(pkt)
```

- `add_mux_stream` creates a stream "for muxing pre-encoded data without creating a CodecContext" and checks `avformat_query_codec(..., FF_COMPLIANCE_NORMAL)`, raising `'{format}' format does not support '{codec}' codec`. source: PyAV 18.0.0 `av/container/output.py:191-266` (installed package in .venv), quote from docstring lines 194-196 and 229-235.
- PyAV rescales every packet from `packet.time_base` to the stream time base before `av_interleaved_write_frame`. source: PyAV 18.0.0 `av/container/output.py:621` (`packet._rebase_time(stream.time_base)`).
- Width and height are required: `add_mux_stream("mjpeg")` without them fails every container with `ArgumentError ... returned 22` (EINVAL) at the first mux. measured: `keyframe_setup.json` (`*|mux_stream_nodims`).
- `add_stream("mjpeg")` with width/height/pix_fmt also works (it opens an MJPEG encoder context that is never fed frames; inferred from PyAV API) and the stream pix_fmt set (yuvj420p vs yuvj422p) does not change the bytes stored; ffprobe reports yuvj422p for both. measured: `keyframe_setup.json` (`encoder_ctx`, `encoder_ctx_420`).
- `add_stream_from_template(av.open(first.jpg).streams.video[0])` lost the last frame from the MP4 and MOV index (29 of 30 packets reported by ffprobe and PyAV although the bytes are in the file) and failed for AVI (EINVAL). measured: `keyframe_setup.json` (`mp4|template`, `mov|template`, `avi|template`). Not investigated further; use `add_mux_stream`.
- Setting `pkt.is_keyframe` is not needed: with the flag False, all 891 packets are still keyframe-flagged in MKV, MP4, MOV, NUT and AVI, and seek results are identical. measured: `keyframe_setup.json` (`keyframe`). source: FFmpeg n8.1.2 `libavformat/mux.c:820-821` "`if (sti->is_intra_only) pkt->flags |= AV_PKT_FLAG_KEY;`".
- WebM is refused by FFmpeg's muxer because `webm_query_codec` only accepts `ff_webm_codec_tags` = V_VP8, V_VP9, V_AV1, A_VORBIS, A_OPUS, D_WEBVTT/*. source: FFmpeg n8.1.2 `libavformat/matroskaenc.c:3675-3682`, `libavformat/matroska.c:110-124`.
- The WebM container guidelines say "Video codec SHOULD be VP8 or VP9" and "The Codec ID SHOULD be "V_VP8" or "V_VP9"". source: https://www.webmproject.org/docs/container/ (accessed 2026-11-09). WebM-with-MJPEG is therefore outside the WebM spec (a SHOULD, not a MUST) and unsupported by FFmpeg; MKV is the Matroska container that allows it.
- Matroska registers `V_MJPEG` ("Motion JPEG ... each video frame or interlaced field is compressed separately ... as a JPEG image", initialization: none). source: https://www.matroska.org/technical/codec_specs.html; FFmpeg maps it at `libavformat/matroska.c:86` (n8.1.2).
- MP4 stores JPEG as an `mp4v` sample entry with ESDS object type indication 0x6C, registered as "Visual ISO/IEC 10918-1". source: https://mp4ra.org/registered-types/object-types (row 6C); FFmpeg n8.1.2 `libavformat/isom.c:55` `{ AV_CODEC_ID_MJPEG , 0x6C }, /* 10918-1 */`, `libavformat/movenc.c:8898` (`mp4v` tag). measured: ffprobe `codec_tag_string` = mp4v (MP4) and jpeg (MOV), `mux_matrix.json`.
- MKV time base is fixed at 1 ms by FFmpeg: `// ms precision is the de-facto standard timescale for mkv files` / `avpriv_set_pts_info(st, 64, 1, 1000);`. source: FFmpeg n8.1.2 `libavformat/matroskaenc.c:3533-3534`.
- The Rust reference implementation does not do passthrough: it spawns ffmpeg reading `image2pipe` MJPEG from stdin and re-encodes with libx264 (`ultrafast`, CRF 18, yuv420p). code: `git show upstream/sfn26:skellycam-rust/src/recording/recorder.rs:1-6,38-46,141-155` (upstream/sfn26 = 765bf82d).

## 3. (b) Byte-exactness and (c) header changes

Byte-exactness, all 7 MJPEG sets (1,862 camera frames per writer mode), SHA-256 per frame in order. measured: `mux_matrix.json`, table "Across all sets" in `mux_matrix.md`.

| container | PyAV VFR | PyAV CFR | ffmpeg CLI CFR | PyAV demux packets == input | `ffmpeg -c:v copy -f image2` files == input | container overhead, c930e_720p_flash (891 frames, 49,314,521 payload bytes) |
|---|---|---|---|---|---|---|
| MKV | 7/7 sets | 7/7 | 7/7 | 21/21 outputs | 21/21 | 40,256 B |
| MP4 (1/90000) | 7/7 | 7/7 | 7/7 | 21/21 | 21/21 | 11,233 B |
| MP4 (1/1e6) | 7/7 | 7/7 | - | 14/14 | 14/14 | 11,937 B |
| fMP4 1 s | 7/7 | 7/7 | 7/7 | 21/21 | 21/21 | 11,739 B |
| fMP4 per frame | 7/7 | 7/7 | 7/7 | 21/21 | 21/21 | 117,522 B |
| MOV | 7/7 | 7/7 | 7/7 | 21/21 | 21/21 | 11,140 B |
| AVI (muxer default 1/600) | 6/7 (c930e: EINVAL) | 7/7 | - | 13/13 | 13/13 | - |
| AVI (1/fps) | 6/7 (c930e: EINVAL) | 7/7 | 7/7 (CLI) | 13/13 (+7 CLI) | 13/13 (+7 CLI) | - |
| NUT | 7/7 | 7/7 | 7/7 | 21/21 (+14 with 1/1e6) | 21/21 (+14) | 25,377 B |
| raw .mjpeg (muxer) | 7/7 | 7/7 | 7/7 | 21/21 | 21/21 | 0 B |
| raw .mjpeg + sidecar (Python) | 7/7 | - | - | 7/7 (own reader; also ffmpeg/PyAV as raw MJPEG) | 7/7 | 0 B + 20 B/frame index |
| folder of .jpg (Python) | 7/7 | - | - | 7/7 (PyAV image2) | 7/7 | 0 B + CSV |

- Every output that was written is byte-exact in every reader: 0 mismatches in the whole matrix, including the generic camera's extra-bytes frames. measured: `mux_matrix.json`.
- The sidecar reader also returns the exact int64 ns timestamps (7/7). measured: `mux_matrix.json` (`sidecar_reader_ts_exact_ns`).
- Sequential cv2 frame k is the decode of input JPEG k: in all 708 checked (frame, offset) rows the mean abs diff to `cv2.imdecode(input k)` (0.66 for c930e_720p frame 0) is smaller than to input k-1 or k+1. measured: `mux_matrix.json` (`mad_vs_imdecode_input_offsets`).
- PyAV decoded every packet of every output with 0 decode errors. measured.

- No container changed any JPEG header (APP0/COM/DQT/DHT/DRI kept as delivered; no AVI1 marker added; no DHT inserted) - extraction is SHA-256-identical, which rules out any byte change. measured: `mux_matrix.json` (no `header_change_frame0` entries), `edge_cases.json`.
- The Logitech C922/C930e frames carry `DQT SOF0 DHT DHT DHT DHT COM APP0 DRI SOS`; the generic 4C4A:4A55 camera carries `APP0(JFIF) DQT DQT SOF0 DHT DHT DHT DHT SOS`. measured: `edge_cases.json` (`markers`).
- All three cameras' four Huffman tables are identical to the standard tables FFmpeg inserts for MJPEG (ITU-T T.81 Annex K tables, `ff_mjpeg_bits_*`/`ff_mjpeg_val_*`). measured: `edge_cases.json` (`dht_vs_standard`: all True).
- `mjpeg2jpeg` bsf (opt-in, `-bsf:v mjpeg2jpeg`) always prepends a JFIF APP0 plus one 420-byte standard DHT and drops a leading APP0: Logitech frames grew by 438 bytes (`APP0(JFIF) DHT DQT SOF0 DHT DHT DHT DHT COM APP0 DRI SOS`, so they then carry two sets of tables), generic frames by 419 bytes; it is not byte-exact, and is only useful for DHT-less input. measured: `edge_cases.json` (`mjpeg2jpeg`); source: FFmpeg n8.1.2 `libavcodec/bsf/mjpeg2jpeg.c:101-121`.
- `mjpegadump` bsf (MJPEG-A for MOV, opt-in; there is no bsf named `mjpega_dump_header` in ffmpeg 9.0.2, `ffmpeg -bsfs` lists `mjpegadump`) inserts a 44-byte APP1 `mjpg` segment: 3 c930e frames grew from 65760/65723/65483 to 65804/65767/65527 bytes, markers `APP1 DQT SOF0 ...`. measured (command in section 13; one-off check, output files inspected then deleted); source: FFmpeg n8.1.2 `libavcodec/bsf/mjpega_dump_header.c:45-62,105`.
- Neither bsf is inserted automatically by any muxer we used (all extractions byte-exact). measured.

## 4. (h) Camera JPEG edge cases

| set (frames) | decoder | original decodes | DHT-stripped decodes | stripped pixels == original pixels |
|---|---|---|---|---|
| c930e_720p_flash (30) | cv2.imdecode / Pillow / PyAV mjpeg / djpeg 3.2.1 | 30/30 each | 30/30 each | 30/30 each |
| c922_720p_flash (30) | same four | 30/30 each | 30/30 each | 30/30 each |
| generic_1080p (11) | cv2.imdecode / Pillow / PyAV mjpeg | 11/11 each | 11/11 each | 11/11 each |
| generic_1080p (11) | djpeg 3.2.1 | output written, exit code non-zero, `Corrupt JPEG data: 535 extraneous bytes before marker 0xd9` (frame 0) | same | 11/11 |

measured: `edge_cases.json` (`decoders`).

- generic_1080p frames have 534-1393 extraneous bytes between the entropy-coded data and EOI (libjpeg-turbo's own wording); every frame still ends in EOI. measured: `edge_cases.json`, `rotation.json` (`tj3_message`).
- DHT-stripped c930e frames stored in MKV, MP4, fMP4, MOV, AVI (1/fps), NUT and raw MJPEG come back byte-exact (PyAV and ffmpeg extraction), decode with 0 PyAV errors, and OpenCV CAP_FFMPEG decodes every frame to pixels identical to the same container built from the original frames (30/30 in each). measured: `edge_cases.json` (`containers_stripped_c930e_720p`).
- FFmpeg's MJPEG decoder installs default Huffman tables at init, which explains why DHT-less frames decode. source: FFmpeg n8.1.2 `libavcodec/mjpegdec.c:61,147` (`init_default_huffman_tables`).
- Media Foundation (`CAP_MSMF`) also read all 30 stripped frames from MKV, MOV and AVI (0 from MP4/fMP4, same as with DHT). measured: `edge_cases.json`.
- Chromium decodes the DHT-stripped frame and the generic extra-bytes frame through `<img>`, `createImageBitmap` and `ImageDecoder` (Electron 35.7.5 and 45.2.3); the stripped frame's 32x32 thumbnail mean equals the original's (128.163). measured: `electron_check.json`.

## 5. (d) Readability, frame counts and frame-accurate seek

All 7 sets; "VFR" uses real (flash sets) or borrowed capture intervals. measured: `mux_matrix.json` / `mux_matrix.md`, plus `keyframe_setup.json` and `version_bump.json` for c930e_720p_flash.

| container (writer) | cv2 CAP_FFMPEG frames read == n | cv2 FRAME_COUNT == n | cv2 seek (POS_FRAMES) exact | PyAV seek exact | FreeMoCap VideoHelper frame_count == n | CAP_MSMF reads all |
|---|---|---|---|---|---|---|
| MKV CFR (PyAV, CLI) | 14/14 | 14/14 | 140/140 | 70/70 | 14/14 | 14/14 |
| MKV VFR (PyAV) | 7/7 | 6/7 (c930e: 888 of 891) | 65/70 (c930e: 297->298, 445->447, 889/890 read fails) | 35/35 | 6/7 (888) | 6/7 (888) |
| MP4 / MP4 1e6 / MOV / MOV 1e6 / fMP4 1 s / fMP4 per frame, VFR and CFR | all | all | all (70/70 per row) | all | all | MOV yes; MP4 and fMP4 0 frames read |
| AVI 1/fps CFR (PyAV), AVI CLI CFR | all | all | all | all | all | all |
| AVI 1/fps VFR (PyAV, 6/7 written) | 6/6 | 6/6 | 60/60 | 30/30 | 6/6 | 6/6 |
| AVI default 1/600 (PyAV) | 13/13 | 0/13 (e.g. 17866 for 893; 385 for 19) | 115/130 (c922_720p VFR: 297->41, 446->45) | 65/65 | 0/13 | 0/13 |
| NUT any (PyAV, CLI) | all | 0/35 (n-1 CFR; n-1 to n-4 VFR) | 66/70 VFR (c930e 4 misses), 70/70 CFR | 28/35 (last-frame seek lands on n-2) | 0/35 | not opened ("can't be used to capture by name") |
| raw .mjpeg (muxer or sidecar) | all | 0 (-192153584101141) | 0/70 per writer | 7-10/35 | ValidationError | not opened |
| folder of .jpg (cv2 pattern `frame_%06d.jpg`) | 7/7 | 7/7 | 70/70 | n/a | FileNotFoundError (path is a pattern) | CAP_IMAGES reads all 7/7 |

- ffprobe opened every written file (folder with `-f image2`); it reports no `nb_frames` for MKV, NUT, fMP4 and raw MJPEG. measured: `mux_matrix.json` (`ffprobe`).
- `cv2.VideoCapture(path)` (FreeMoCap VideoHelper's call) chose the FFMPEG backend for every file. measured: `mux_matrix.json` (`cv2_any.backend`).
- OpenCV's frame count is `nb_frames`, or `floor(duration x fps + 0.5)` when the container has no `nb_frames`, with fps from `avg_frame_rate`. source: OpenCV 4.12.0 `modules/videoio/src/cap_ffmpeg_impl.hpp:1957-1989`. So MKV, NUT and fMP4 counts are estimates; fMP4 happened to be exact on clean files, NUT is always 1+ short, MKV VFR is short on the jittery c930e capture. measured + source.
- OpenCV seeks by converting the frame number to a timestamp with that fps, then counting frames from the pts of the frame it lands on (`dts_to_frame_number` = pts x fps). source: `cap_ffmpeg_impl.hpp:1991-1995,2022-2075`. inferred: any container read through OpenCV can seek wrongly on VFR content when pts x avg_fps drifts from the frame index; MP4/MOV/fMP4 passed on all VFR sets here, which is a measured outcome on these captures, not a guarantee.
- FreeMoCap would reject a recording set if one camera's count differs (`VideoGroup` requires identical counts, code `video_group_helper.py:381-385`); with NUT every camera's count misses its last frame(s), and `VideoHelper.read_frame_number` raises on frames past the real end (`reads ok 3/4` in truncation tests). measured + code.
- Media Foundation (CAP_MSMF) cannot decode MJPEG from MP4/fMP4 (`MFVideoFormat_RGB32(codec not found)` warning, 0 frames) but reads MKV, MOV and AVI. measured: run log + `mux_matrix.json`.

## 6. (e) Real per-frame timestamps (VFR)

Max |reported - input| per frame, first frame aligned, microseconds. measured: `mux_matrix.json` (`pyav_ts`, `ffprobe_ts`, `cv2_ffmpeg_ts`), `version_bump.json`.

| container / stream time base | VFR: PyAV = ffprobe = cv2 POS_MSEC | CFR (k/fps) | notes |
|---|---|---|---|
| MKV 1/1000 (fixed) | 470 (c930e), 430 (c922) | 333 | c930e frames 81 and 82 (11 us apart) get the same timestamp: reported times not strictly increasing |
| MP4 / MOV / fMP4 / NUT, muxer default 1/90000 | <= 6 | 0 | 1/90000 grid |
| MP4 / MOV / NUT with `st.time_base = 1/1000000` | 0 | 0 (0.333 us for CFR values) | exact to the microsecond input |
| AVI 1/fps | 14,672 (c922 720p) | 0 | VFR forced onto the CFR grid; c930e refused (EINVAL) |
| AVI muxer default 1/600 | 830 | 0 | gaps filled with empty frames (frame count about 20x) |
| raw .mjpeg / sidecar read via FFmpeg | about 6,000,000 over 30 s | about 5,950,000 | demuxer assumes 25 fps; the sidecar index itself is exact (ns) |
| folder via image2 | about 6,000,000 | - | 25 fps default; the CSV itself is exact (ns) |

- PyAV pts, ffprobe pts_time and cv2 CAP_PROP_POS_MSEC report the same per-frame time in every container (identical max errors), so OpenCV does expose real VFR timestamps (it returns the decoded frame's pts). measured; source: `cap_ffmpeg_impl.hpp:1852-1857`.
- MKV accepts equal timestamps because its muxer has `AVFMT_TS_NONSTRICT`; MP4 at 1/90000 kept frames 81/82 distinct (11 us is about one 11.1 us tick); AVI rejects equal DTS: `Application provided invalid, non monotonically increasing dts to muxer in stream 0: 81 >= 81` at frame 82 (1/30) and `1622 >= 1622` (1/600). measured (PyAV log captured in this study; reproduce with `jp_io.pyav_write` on c930e_720p_flash, containers avi / avi_tb_rate); source: FFmpeg n8.1.2 `libavformat/mux.c:558-565,803-808`, `matroskaenc.c:3661`.
- AVI cannot carry VFR: the muxer writes empty packets to fill timestamp gaps and errors above 60000 skipped frames. source: FFmpeg n8.1.2 `libavformat/avienc.c:742-762`. measured: c930e CFR AVI written with PyAV's default time base reports 17,820 frames in OpenCV for 891 stored (`version_bump.json`); c922 VFR 17,866 for 893 (`mux_matrix.json`).
- With PyAV's default `add_mux_stream` time base, AVI gets 1/600 even for CFR input (c922_720p60 CFR: 100 frames reported for 10); `st.time_base = Fraction(1, fps)` fixes it. measured: `mux_matrix.json` (`avi` vs `avi_tb_rate`). The ffmpeg CLI writer gets it right by itself (count == n in 7/7).
- inferred: per-frame capture timestamps belong in a sidecar regardless of container; the container's own timestamps were exact only for MP4/MOV/NUT with a 1/1e6 time base (fMP4 uses the same mov muxer but was only tested at 1/90000).

## 7. Crash side: killed writer and truncated files (adjunct to G2; crash_resilience topic goes deeper)

Child process muxes 600 c930e_720p frames (real VFR timestamps) with PyAV and calls `os._exit(1)` without closing (no trailer, user-space buffers lost). Truncated = cleanly closed 891-frame file cut at 50% / 90% of its bytes. measured: `truncation.json`.

| container | killed: file readable? | killed: exact frames (PyAV) / cv2 frames read / cv2 FRAME_COUNT | killed: FreeMoCap VideoHelper | trunc 50%: exact / cv2 read / cv2 count | trunc 90%: exact / cv2 read / cv2 count |
|---|---|---|---|---|---|
| MKV | yes | 597 / 597 / -276701161105643264 | ValidationError (end_frame negative) | 445 / 445 / 888 | 802 / 802 / 888 |
| MP4 | no (InvalidDataError; cv2 not opened) | 0 / - / - | RuntimeError: Failed to open | not readable | not readable |
| fMP4 1 s | yes | 578 (+1 partial) / 579 / 582 | count 582, 3/4 reads ok | 445 (+1 partial) / 446 / 459 | 801 (+1 partial) / 802 / 828 |
| fMP4 per frame | yes | 596 (+1 partial, 1 decode error) / 596 / 597 | count 597, 3/4 reads ok | 445 (+1) / 446 / 446 | 802 (+1) / 802 / 803 |
| MOV | no | 0 | RuntimeError: Failed to open | not readable | not readable |
| AVI (1/fps) | yes | 597 (+1 partial) / 598 / 0 | ValidationError (end_frame 0) | 445 (+1) / 446 / 891 | 801 (+1) / 802 / 891 |
| NUT | yes | 597 (+1 partial) / 598 / 595 | count 595, 4/4 reads ok | 445 (+1) / 446 / 443 | 801 (+1) / 802 / 798 |
| raw .mjpeg (muxer) | yes | 597 (+1 partial) / 598 / -192153584101141 | ValidationError | 445 (+1) / 446 / garbage | 801 (+1) / 802 / garbage |
| raw .mjpeg + sidecar (Python buffered writes) | yes (custom reader) | 409 complete frames (index entries 409) | n/a | 445 | 801 |

- "+1 partial": the last packet is a cut JPEG; PyAV/FFmpeg decode it without an error in most cases (a silently damaged last frame), once with `InvalidDataError`. measured: `truncation.json` (`exact_prefix` vs `packets`, `decode_errors`).
- Of 600 frames muxed before the kill, 597-598 reached the file for the FFmpeg muxers; fMP4 with 1 s fragments lost the unflushed fragment (578 complete); the Python sidecar writer lost 191 frames to its user-space buffers. measured: `truncation.json`. inferred: flush policy (avio flush per packet, or `flush_packets`), not the container, decides how many frames a kill loses; the crash_resilience topic should measure that.
- OpenCV's frame count on damaged files is wrong in both directions (MKV truncated at 50%: 888 reported, 445 readable; killed MKV: a negative number; killed AVI: 0), so FreeMoCap either crashes on open or reports frames it cannot read (`reads ok 3/4`). measured: `truncation.json`. code: OpenCV 4.12.0 falls back to duration x fps when `nb_frames` is 0 (`cap_ffmpeg_impl.hpp:1980-1989`); FreeMoCap trusts the property (`video_group_helper.py:159`).
- Matches prior P11 (cv2-encoded JPEGs): MKV MJPEG readable after kill, plain MP4 not. measured: `research/frame_ring_buffer/prototypes/results/p11_crash_container.md`.
- AVI above 1 GiB: 6000 looped c922_1080p frames (1,154,485,550 bytes) written by PyAV with time base 1/30 got one `AVIX` RIFF and an OpenDML `indx`; ffprobe nb_frames 6000, PyAV 6000 packets byte-exact, cv2 CAP_FFMPEG count 6000 / read 6000 / seek 10/10, CAP_MSMF read 6000, FreeMoCap frame_count 6000 and all 4 reads ok. measured: `truncation.json` (`large_avi`). source: FFmpeg n8.1.2 `libavformat/avienc.c:878-886` (new `AVIX` RIFF once `AVI_MAX_RIFF_SIZE` is exceeded).
- MP4 above 4 GiB was not written (avoided a 4 GB disk write on a shared machine); FFmpeg switches to `co64` chunk offsets when an offset exceeds UINT32_MAX. source: FFmpeg n8.1.2 `libavformat/movenc.c:176-178,203-207`. NOT VERIFIED by test.

## 8. (f) Lossless rotation in Python (as Rust jpeg_transform.rs)

Method: libjpeg-turbo 3.2.1 `tj3Transform` via ctypes with `options = 0` (the Rust call), plus `TJXOPT_PERFECT`, plus `jpegtran -rotate N -perfect -copy all`; losslessness proven on dequantized DCT coefficients (jpeglib 1.0.2), with native-resolution planes and RGB as secondary checks. All 7 MJPEG sets, 11 frames each (c922_720p60: 10), rotations 90/180/270 = 228 cases. measured: `rotation.json`; code: `scripts/jpeg_passthrough/rotate_check.py`.

| check | result (of 228) |
|---|---|
| tj3Transform output produced | 228 (33 generic frames with a warning, output kept) |
| TJXOPT_PERFECT accepted (no partial-iMCU edge) | 228 |
| dequantized DCT coefficients == exact permutation + sign flips of the original, all 3 components | 228 |
| control: block-grid rotation without coefficient permutation matches | 0 (the test can fail) |
| jpegtran.exe output bytes == tj3Transform output bytes | 228 |
| YUV planes (native resolution) max abs diff | <= 1 |
| RGB max abs diff vs np.rot90(decode(original)) | <= 5 (up to 15.1% of pixels differ) |
| output subsampling | rot90/270: TJSAMP 4 = 4:4:0 (720x1280 etc.); rot180: 4:2:2 |
| Rust-equivalent legacy `tjTransform` returns 0 (Rust keeps the rotation) | 195; all 33 generic_1080p frames return -1 |

- The rotation is lossless: the coefficients are identical after the exact transpose/flip mapping. measured: `rotation.json`. The <=1 plane / <=5 RGB differences come from decoding (inferred: integer IDCT rounding on transposed blocks, and 4:4:0 vs 4:2:2 chroma upsampling); they are not changes to the stored data.
- The cameras' luma quantisation table is not symmetric (e.g. row 1 col 5 = 9 vs row 5 col 1 = 5 for c930e frame 0), so a transpose must also transpose the table; libjpeg-turbo does. measured: printed `qt[0]` by jpeglib in this study (probe in scratchpad); the DCT comparison is done on dequantized values so it covers this.
- `TJXOPT_PERFECT` "causes tj3Transform() to return an error if the transform is not perfect ... any partial iMCUs that cannot be transformed will be left in place". source: libjpeg-turbo 3.2.1 `include/turbojpeg.h:1130-1142`. All corpus sizes are multiples of the 16x8 4:2:2 iMCU, so options 0 is safe for them; a 4:2:0 or odd-size camera would need PERFECT or TRIM (inferred).
- The generic camera's frames make libjpeg-turbo report `TJERR_WARNING` ("The error was non-fatal and recoverable, but the destination image may still be corrupt", source: `turbojpeg.h:1065-1070`); tj3Transform still returns a complete output whose DCT data is exact (33/33). The legacy `tjTransform` returns -1 for these frames, and the Rust code keeps the output only `if ret == 0` and otherwise falls back to the unrotated frame without changing width/height. measured: `rotation.json` (`rust_equivalent_legacy_rc`); code: `git show upstream/sfn26:skellycam-rust/src/camera_group/jpeg_transform.rs:89,108`, `dispatcher.rs:201-213`. Consequence (inferred): with Rust's logic a rotated generic camera would record unrotated frames silently; a Python port should accept TJERR_WARNING outputs.
- Python options: PyTurboJPEG 2.6.1 has no public rotate method (it uses `tj3Transform` only for crop/optimize; `TJXOP_ROT90` etc. are defined) and needs a separately installed libjpeg-turbo >= 3.0 DLL (default Windows path `C:/libjpeg-turbo64/bin/turbojpeg.dll`). source: PyTurboJPEG 2.6.1 wheel `turbojpeg.py:55-78,154-172,459-468,1585-1820`. A ~60-line ctypes wrapper (as in `rotate_check.py`) or jpegtran.exe works.
- Chromium decodes the rotated 4:4:0 JPEG (720x1280) via `<img>`, `createImageBitmap` and `ImageDecoder` in both Electron versions (ImageDecoder reports format BGRX for it vs I422 for 4:2:2). measured: `electron_check.json`.
- Rotation cost per frame is not measured here; see `bench_rotate.py` in the manifest (the Rust comment claims "~1-2ms per frame", code: `jpeg_transform.rs:4`, NOT VERIFIED).

## 9. (g) Chromium / Electron cheap check

Files: c930e_720p_flash written by mux_matrix (PyAV, VFR except AVI) plus a VP9 WebM control encoded from the same JPEGs with libvpx-vp9; pages load `file://` URLs in a hidden BrowserWindow. measured: `electron_check.json`; code: `scripts/jpeg_passthrough/electron_check/` and `electron_check.py`.

| file | Electron 35.7.5 (Chrome 134.0.6998.205) | Electron 45.2.3 (Chrome 156.0.8078.80) |
|---|---|---|
| MKV MJPEG | error 4 `DEMUXER_ERROR_NO_SUPPORTED_STREAMS` | same |
| MP4 MJPEG (mp4v/0x6C) | error 4 `DEMUXER_ERROR_NO_SUPPORTED_STREAMS` | same |
| fMP4 MJPEG | error 4 `DEMUXER_ERROR_NO_SUPPORTED_STREAMS` | same |
| MOV MJPEG | error 4 `DEMUXER_ERROR_NO_SUPPORTED_STREAMS` | same |
| AVI MJPEG | error 4 `DEMUXER_ERROR_COULD_NOT_OPEN` | same |
| NUT MJPEG | error 4 `DEMUXER_ERROR_COULD_NOT_OPEN` | same |
| raw .mjpeg | error 4 `DEMUXER_ERROR_COULD_NOT_OPEN` | same |
| control VP9 WebM | loadeddata, seeked, 1280x720, frame drawn | same |
| single JPEGs (orig, no-DHT, generic, rot90 4:4:0) via img / createImageBitmap / ImageDecoder | all decode | all decode |

- `canPlayType` returns "" for `video/mp4; codecs="mp4v.6C"`, `video/x-matroska; codecs="mjpeg"`, `video/webm; codecs="mjpeg"`, `video/quicktime`, `video/x-msvideo`, `video/x-motion-jpeg` in both; `video/x-matroska` alone is "" in 35.7.5 and "maybe" in 45.2.3; MSE `isTypeSupported` is false for all MJPEG types. measured: `electron_check.json` (`mime`).
- Bumping Electron to 45.2.3 does not add MJPEG playback. measured.
- inferred: G8/G9 for passthrough recordings need either per-frame JPEG decode in the page (img/createImageBitmap/ImageDecoder on bytes served by the backend, e.g. from the sidecar index or a container demuxed server-side), or a separate playback proxy encode; the chromium_codecs / chromium_sync_scrub topics own that comparison.

## 10. Version bumps (PyAV 19.0.2, opencv-python 5.0.0.93)

measured: `version_bump.json` (c930e_720p_flash, 891 frames).

- PyAV 19.0.2 bundles FFmpeg libs libavformat 63.1.102 / libavcodec 63.1.102 (same major as ffmpeg CLI 9.0.2). Every container's write result, byte-exactness, timestamp error and seek result equals PyAV 18.0.0's; WebM still refused; VFR AVI still EINVAL at frame 82. measured.
- opencv-python 5.0.0.93 bundles FFmpeg avformat 61.7.100 / avcodec 61.19.100. Its frame counts and seek results equal OpenCV 4.12.0's: VFR MKV count 888 for 891 frames and seek 5/10; NUT 887 (VFR) / 890 (CFR); default-time-base PyAV AVI 17820; MP4/MOV/AVI(1/fps) exact with seek 10/10. measured.
- Conclusion for this topic: no format-support gain from bumping PyAV or OpenCV for MJPEG passthrough (inferred from the identical results; other topics may still want PyAV 19 for codecs).

## 11. G5 (compat side): folder of JPEGs vs one container

Throughput is not measured here (bench_mux.py in the manifest measures PyAV mux cost per container vs raw+sidecar vs folder, 1 camera per process; the write_throughput topic covers multi-camera disk throughput). Compatibility facts from the tests:

| property | folder of .jpg + CSV | raw .mjpeg + binary sidecar | MKV | MP4 (1/1e6) | fMP4 1 s | AVI (1/fps) |
|---|---|---|---|---|---|---|
| camera bytes byte-exact | yes | yes | yes | yes | yes | yes |
| real VFR timestamps kept | in CSV (ns) | in index (ns) | 1 ms grid | exact (us) | <= 6 us at 1/90000 (1/1e6 not tested) | no (CFR only) |
| ffprobe / PyAV open | yes via image2 pattern (25 fps default timestamps) | yes as raw MJPEG (no timestamps) | yes | yes | yes | yes |
| cv2 CAP_FFMPEG frame count exact | yes (pattern) | no (garbage) | CFR yes; VFR 6/7 sets | yes | yes (clean) / no (killed) | yes |
| cv2 seek frame-exact | yes (pattern) | no (0/70) | CFR yes; VFR 65/70 | yes | yes | yes |
| FreeMoCap VideoHelper opens | no (path is not a file; extension not in VIDEO_EXTENSIONS) | no (`.mjpeg` not in VIDEO_EXTENSIONS; ValidationError if forced) | yes (count wrong on c930e VFR) | yes | yes | yes |
| readable after kill | each finished file (inferred; not killed-tested) | yes with custom reader | yes | no | yes | yes (count 0) |
| Chromium `<video>` | n/a | no | no | no | no | no |
| Chromium per-frame decode (img/ImageDecoder) | yes, file = frame | yes after slicing by index (inferred) | needs demux outside Chromium (inferred) | same | same | same |
| files per camera-minute at 30 fps | 1800 (+1 CSV) (arithmetic) | 2 | 1 | 1 | 1 | 1 |

measured unless marked: `mux_matrix.json`, `truncation.json`, `electron_check.json`; FreeMoCap code citations in section 1.

- inferred: no container gives Chromium playback of MJPEG, so G8/G9 cannot be the tie-breaker between folder/sidecar and containers; the deciding factors are FreeMoCap/OpenCV compatibility (favours MP4 or fMP4 with an exact time base), crash tolerance (favours fMP4/MKV/NUT/raw over plain MP4) and the measured mux cost (pending bench).

## 12. Limits and what was not done

- No timing/throughput/CPU numbers (by instruction); see bench manifest.
- One machine, Windows only; Linux/macOS readers untested.
- Partial-file behaviour tested with os._exit and byte truncation, not power loss or OS crash.
- MP4 > 4 GiB (co64) and MKV/NUT > 4 GiB not written. NOT VERIFIED.
- Chromium: only `<video>` and image decoders checked; no MSE/WebCodecs VideoDecoder path for MJPEG (no MJPEG codec string exists for them, inferred) and no Chrome-browser run.
- macOS AVFoundation / QuickTime readability of MJPEG MOV/MP4 not tested.
- Audio was out of scope for this topic.

## 13. Commands (repo root `C:/Users/Dom/GitHub/freemocap/skellycam`)

```
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/mux_matrix.py          # -> mux_matrix.json (media in skellycam-raw/.../jpeg_passthrough/mux_matrix/)
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/summarize_matrix.py     # -> mux_matrix.md
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/keyframe_check.py       # -> keyframe_setup.json
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/edge_cases.py --djpeg <scratchpad>/jpeg_passthrough/ljt321/bin/djpeg.exe   # -> edge_cases.json
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/truncation_check.py     # -> truncation.json
uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/rotate_check.py --lib <scratchpad>/jpeg_passthrough/ljt321/bin/turbojpeg.dll --jpegtran <scratchpad>/jpeg_passthrough/ljt321/bin/jpegtran.exe --n 11   # -> rotation.json
.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/electron_check.py --jpegtran <scratchpad>/jpeg_passthrough/ljt321/bin/jpegtran.exe   # -> electron_check.json (run mux_matrix first)
uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/version_bump_check.py           # -> version_bump.json
ffmpeg -i <mux_matrix>/c930e_720p_flash/pyav_vfr_mov.mov -frames:v 3 -c:v copy -bsf:v mjpegadump -f image2 <scratchpad>/jpeg_passthrough/mjpega/%03d.jpg
```
`<scratchpad>` = `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad`. electron_check.py strips `ELECTRON_RUN_AS_NODE` from the child environment (VS Code terminals set it, which makes electron.exe run as plain Node).

## 14. Benchmarks to run later (quiet machine, one at a time)

Scripts write JSON to `research/skellycam_recording/recording_upgrade/results/jpeg_passthrough/bench/`. Each was smoke-tested here with a tiny run (`--frames 60 --reps 1`, `--frames 20 --reps 1`); those outputs were discarded and no number is reported. Run from the repo root with nothing else running (CPU-only benchmarks, no GPU involved); bench_mux records `psutil.cpu_percent` over 1 s before starting in its meta.

| id | what it measures | command | est. min |
|---|---|---|---|
| jp_mux_cost | PyAV passthrough mux CPU and wall us/frame + close cost, per container (pkt_only baseline, mkv, mp4, fmp4_1s, fmp4_perframe, mov, avi_tb_rate, nut, mjpeg_raw_mux, raw_sidecar, jpg_folder), 720p (c930e) and 1080p (c922), 3000 frames, 5 reps, 1 camera per worker process, page cache (no fsync) | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/bench_mux.py --tag default` | 8 |
| jp_mux_cost_fsync | same with FlushFileBuffers at close (close cost includes getting the data to disk) | `.venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/bench_mux.py --fsync --tag fsync` | 10 |
| jp_rotate_cost | tj3Transform rot90/180/270 per frame, 720p and 1080p, 1000 frames x 5 reps, single thread | `uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/bench_rotate.py --lib C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/jpeg_passthrough/ljt321/bin/turbojpeg.dll` | 3 |

If the scratchpad DLL is gone: download `https://github.com/libjpeg-turbo/libjpeg-turbo/releases/download/3.2.1/libjpeg-turbo-3.2.1-vc-x64.exe` into an empty folder and run `"C:/Program Files/7-Zip/7z.exe" x -o<dir> libjpeg-turbo-3.2.1-vc-x64.exe`; the DLL is `<dir>/bin/turbojpeg.dll`.

What to read from them: `summary["720p|mkv"]["cpu_us_per_frame_mux"]["median"]` etc. Compare each container with `pkt_only` (PyAV packet overhead alone) and with `raw_sidecar` / `jpg_folder` (no container) to answer G5's "is the wrapper significant".

## 15. Open questions

- Which single format to recommend: fMP4 (1 s fragments) is the only tested option that is byte-exact, keeps VFR timestamps within 6 us (1/90000; 1/1e6 untested for fMP4), gives OpenCV/FreeMoCap an exact frame count and frame-exact seek on clean files, and stays readable after a kill; but on a killed fMP4 OpenCV's count is wrong (582 vs 579 readable) and FreeMoCap loses reads. Should FreeMoCap stop trusting `CAP_PROP_FRAME_COUNT` (use a timestamps sidecar or PyAV packet count) regardless of container?
- How many frames does each container lose on a kill with a per-packet avio flush (`flush_packets=1` / `fflags=flush_packets`) vs default buffering? (crash_resilience topic)
- MKV's 1 ms time base collapses frames 81/82 of the real c930e capture (11 us apart) to the same timestamp; is a 1 ms grid acceptable for the timestamp accuracy goals (see docs/timestamp_accuracy_options.md), or must timestamps live in a sidecar anyway?
- Chromium playback/scrub of MJPEG recordings: per-frame JPEG decode in the renderer vs a proxy encode - which is fast enough for N synchronized cameras? (chromium_codecs, chromium_sync_scrub topics)
- Does any camera actually used with skellycam omit DHT? None of the three cameras in the corpus does (all carry standard tables).
- Why does `add_stream_from_template` drop the last frame from the MP4/MOV index (PyAV 18.0.0)? Not needed if `add_mux_stream` is used.
- MP4/MKV > 4 GiB passthrough files and macOS/Linux readers are untested.
- Mux CPU per frame per container and rotation cost: pending bench_mux.py / bench_rotate.py.
