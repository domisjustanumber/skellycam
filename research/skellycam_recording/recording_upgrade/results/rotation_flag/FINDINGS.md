# Rotation flag in MKV: who honours it

2026-11-12, desk test (Windows 11). This asks whether skellycam can record camera rotation as a container flag (plus a copy in its own sidecar header) instead of rotating pixels with `cv2.rotate`. Scripts: `scripts/rotation_flag/` (`make_media.py`, `probe_all.py`, `vlc_window.py`, `vlc_snap.py`, `vlc_methods_check.py`). Results: `probe_all.json`, `vlc_methods_check.json`, `make_log.json`. The test media are rebuildable and were not kept.

*Written by a sub-agent; saved by the main session. Before saving, the main session checked against `probe_all.json`: the VLC window result for every file at both sizes (only `H90.mp4` rotated: 360×640 / 540×960, red marker bottom-left), `ProjectionPoseRoll` in every rotated MKV (90 / 180 / −90), and `packets_identical` = 30 in every file. The main session also corrected §5 option 1 (see the note there).*

**Labels:** **[M]** measured (result file or command), **[C]** code read, **[I]** inferred, **[NV]** not verified.

**Versions:** PyAV 19.0.2 with libavformat 63.1.102 (FFmpeg 9.0.2), from the `skellycam-phase1` venv. FFmpeg/ffprobe CLI 9.0.2, VLC 3.0.24 (Direct3D11 output), OpenCV 5.0.0.

## 0. Answers
| Question | Answer |
|---|---|
| Is there an MKV rotation flag that VLC honours? | **No** [M]. VLC 3.0.24 showed every rotated MKV unrotated: `Projection`/`ProjectionPoseRoll` from PyAV or the FFmpeg CLI, a `ROTATE` tag, MJPEG or H.264, 90/180/270 degrees, 720p and 1080p. VLC parses the element (log: `mkv debug: ... + Track Video Projection`) but does not rotate. |
| Does VLC honour rotation at all? | **Only H.264 in MP4** (tkhd matrix): its window was 360×640 and the red top-left marker moved to bottom-left [M]. MJPEG in MP4 with the same matrix was **not** rotated [M]. VLC decodes that track with its own `jpeg` decoder, while MKV MJPEG goes through `avcodec`; forcing `--codec=avcodec` failed ("Codec `jpeg' is not supported") [M]. That VLC's `jpeg` decoder drops container orientation is [I]. |
| Can PyAV 19.0.2 write it at header time? | **Yes** [M][C]: `VideoStream.set_display_rotation(degrees, hflip=False, vflip=False)` or `VideoStream.set_display_matrix(seq9)`, called before `start_encoding()`. PyAV injects `AV_PKT_DATA_DISPLAYMATRIX` into `codecpar.coded_side_data` in `_finalize_for_output()` (`av/video/stream.py`). FFmpeg's Matroska muxer turns it into `Projection{ProjectionPoseRoll}`. |
| Which readers read it? | ffprobe, FFmpeg CLI, OpenCV and PyAV all read it [M]. **Only the FFmpeg CLI and OpenCV rotate pixels.** PyAV only reports the rotation (§3). |
| Does the sidecar appender keep it? | **Yes** [M]: element, ffprobe value, OpenCV and PyAV results identical after `append_attachment.py`; VLC still plays the file, still unrotated. |
| Are frame bytes untouched? | **Yes** [M]: 30/30 packets byte-identical to the source JPEGs and contiguous, in every MJPEG file. The first JPEG moves from byte 516 to 530 because of the 14-byte element; offsets recorded live stay correct. |

## 1. Method
- **Frames** (`make_media.py`): 30 frames at 1280×720 and 1920×1080; grey background, a solid block in each corner (top-left red, top-right green, bottom-left blue, bottom-right yellow), a white up-arrow and the frame number; each frame encoded once with `cv2.imencode` as baseline JPEG (SOF0, no SOF2), then muxed unchanged as MJPEG packets.
- **Files** (per size): `A.mkv` (PyAV, recording-style: index PTS, `flush_packets=1`, no rotation); `B90/B180/B270.mkv` (same writer plus `s.set_display_rotation(deg)`); `Bm90.mkv` (`s.set_display_matrix([0,-65536,0,65536,0,0,0,0,1<<30])`); `C<deg>.mkv` / `D<deg>.mp4` (`ffmpeg -display_rotation <deg> -i A.mkv -map 0 -c copy`); `T90.mkv` (`-metadata:s:v:0 rotate=90`); controls `H.mkv`, `H90.mkv`, `H90.mp4` (libx264, `-display_rotation 90 -c copy`); `B90_att.mkv` (`B90.mkv` plus a 1,400 B dummy attachment via `scripts/sidecar_embedding/append_attachment.py`).
- **Orientation from pixels, not by eye** (`probe_all.py` `orient()`): where the red and green blocks land gives the label (red TL + green TR = none; red BL + green TL = 90° ccw; red TR + green BR = 90° cw; red BR + green BL = 180°).
- **Container check:** EBML walk of Tracks and Tags (`probe_all.py` `ebml_scan`) plus `ffprobe -show_entries stream_side_data`.
- **VLC** (`vlc_window.py`): rc interface (TCP), `--vout=direct3d11`, start paused, step one frame, read the window's client size and grab its pixels with PIL `ImageGrab`. This briefly opens small VLC windows on the desktop.
  - **The scene filter and rc `snapshot` cannot see VLC's orientation:** on `H90.mp4`, which VLC rotates on screen, the scene filter, rc `snapshot` with `--vout=dummy` and rc `snapshot` with `--vout=direct3d11` all gave unrotated 1280×720 pictures (`vlc_methods_check.json`) [M]. VLC 3 applies orientation in the display, after both [I]. Earlier scene-filter VLC checks therefore say nothing about rotation.
- **OpenCV:** `cv2.VideoCapture(path, cv2.CAP_FFMPEG)` with defaults, and again with `CAP_PROP_ORIENTATION_AUTO=0`; `CAP_PROP_ORIENTATION_META` read in both.
- **PyAV:** `stream.codec_context.coded_side_data`, `frame.rotation`, `frame.side_data`, pixels from `to_ndarray()`.

## 2. What is in the container
| File | Matroska element (EBML walk) | Tag | ffprobe `rotation` |
|---|---|---|---|
| A.mkv | none | none | none |
| B90 / Bm90 / C90.mkv | `Projection` (0x7670) with only `ProjectionPoseRoll` (0x7675) = 90.0 | none | 90 |
| B180 / C180.mkv | `ProjectionPoseRoll` = 180.0 | none | −180 |
| B270 / C270.mkv | `ProjectionPoseRoll` = −90.0 | none | −90 |
| T90.mkv | none | `ROTATE`=90 | none (tag only) |
| D90 / D180 / D270.mp4 | (tkhd matrix) | none | 90 / −180 / −90 |
| B90_att.mkv | `ProjectionPoseRoll` = 90.0, plus Attachments | none | 90 |

- [M] IDs confirmed from the bytes FFmpeg wrote: `76 70 8B 76 75 88 40 56 80 00 00 00 00 00` = Projection (size 11) holding ProjectionPoseRoll (size 8, IEEE double 90.0). No `ProjectionType` (default 0 = rectangular), no Yaw/Pitch. 14 bytes in Tracks, before the first Cluster.
- [M] PyAV-written and CLI-written elements are identical; `set_display_rotation(90)` and the raw matrix give the same matrix as `-display_rotation 90`; 270 is stored as −90.
- [M] Sign convention: ffprobe `rotation` and `PoseRoll` are counter-clockwise degrees, like PyAV's `set_display_rotation` argument and `frame.rotation`. OpenCV's `CAP_PROP_ORIENTATION_META` uses the opposite sense (90 → 270, 270/−90 → 90, 180 → 180).
- [M] A `ROTATE` tag is ignored by every reader tested, ffprobe's display matrix included.
- [M] A file truncated to 300 kB (no trailer) still reports rotation 90: the element is in the header, so crashed files keep it.

## 3. Results per file and reader (identical at 1280×720 and 1920×1080)
| File | FFmpeg CLI decode | VLC 3.0.24 (window; 1280×720 shown at zoom 0.5) | OpenCV 5.0.0 default | OpenCV `ORIENTATION_AUTO=0` | PyAV 19.0.2 |
|---|---|---|---|---|---|
| A.mkv | none | none, 640×360 | none | none | rotation 0, no side data |
| B90.mkv (PyAV) | 90° ccw | **none**, 640×360, red TL | **90° ccw**, 720×1280, META=270 | none | `frame.rotation`=90, `DISPLAYMATRIX` in frame and stream side data; pixels **not** rotated |
| Bm90.mkv (PyAV matrix) | 90° ccw | **none** | 90° ccw | none | as B90 |
| B180.mkv | 180° | **none** | 180°, META=180 | none | rotation −180; pixels not rotated |
| B270.mkv | 90° cw | **none** | 90° cw, META=90 | none | rotation −90; pixels not rotated |
| C90/C180/C270.mkv (CLI) | as B | **none** | as B | none | as B |
| T90.mkv (tag) | none | none | none, META=0 | none | rotation 0 |
| D90/D180/D270.mp4 (MJPEG) | as B | **none** (VLC `jpeg` decoder) | as B | none | as B |
| H90.mkv (H.264) | 90° ccw | **none**, 640×360 | 90° ccw | none | rotation 90; pixels not rotated |
| H90.mp4 (H.264) | 90° ccw | **90° ccw**, 360×640, red BL | 90° ccw | none | rotation 90; pixels not rotated |
| B90_att.mkv (appended) | 90° ccw | **none**, plays | 90° ccw | none | as B90 |

Source: `probe_all.json` (keys `ffmpeg_cli_autorotate`, `vlc`, `opencv`, `pyav`, `ebml`, `frame_bytes`) and `vlc_methods_check.json`.

## 4. Writing it from the skellycam writer (PyAV 19.0.2)
```python
s = container.add_stream("mjpeg", rate=fps)
s.width, s.height, s.pix_fmt = w, h, "yuvj420p"
s.set_display_rotation(90)        # counter-clockwise degrees; hflip=/vflip= also available
container.start_encoding()        # header (Tracks with Projection{PoseRoll}) is written here
```
- [C] Set the display matrix before `start_encoding()`. It is applied in `VideoStream._finalize_for_output()`, after `avcodec_parameters_from_context()`, which would otherwise overwrite it.
- [C] It is applied only when the stream has a codec context; `add_stream("mjpeg", ...)` (the recording writer's pattern) has one.
- [M] Muxing pre-encoded JPEG packets is unaffected: 30/30 identical and contiguous, nothing re-encoded, no remux, Segment UID and offsets undisturbed.
- [I] The skellycam sidecar header copy should store the same counter-clockwise integer (90/180/270), so skellycam's own readers don't depend on container side data.

## 5. Consequences for the plan [I]
- A container flag does not give "upright in VLC" for skellycam's MJPEG MKVs: VLC 3 ignores it in MKV, and for MJPEG even in MP4.
- **Readers disagree on what a frame is:** OpenCV (`cv2.VideoCapture`, auto-rotate on by default) returns rotated frames with width and height swapped; PyAV `to_ndarray()` returns sensor-orientation frames and only reports `frame.rotation`; VLC shows sensor orientation. Any freemocap or skellysync code reading recordings with OpenCV would see a different frame shape from code reading them with PyAV. If the flag is used, every skellycam/freemocap reader must choose one policy explicitly, e.g. set `CAP_PROP_ORIENTATION_AUTO=0` and apply the rotation from the sidecar header.
- The options this leaves:
  1. Bake the rotation into the pixels, so every reader sees the same thing. *Main-session correction: the sub-agent wrote that this means decoding and re-encoding the camera JPEG. It need not: a lossless JPEG transform (jpegtran-style) rotates without re-encoding, measured at 2.0–2.2 ms per frame at 720p and 6.8–8.9 ms at 1080p (`results/EVIDENCE_INDEX.md` line 59 [M]); TJERR_WARNING outputs must be accepted, or a generic camera is left unrotated (line 71 [I]); 1080 is not a multiple of 16, so the transform has partial MCUs at an edge [I]. The frame bytes still change, so the stored JPEG is no longer the camera's own bytes.*
  2. Store the rotation only in the skellycam header and rotate in skellycam's own viewer and readers: passthrough kept, external players show sensor orientation.
  3. Option 2 plus the container flag: cheap, honoured by FFmpeg-based tools, but adds the OpenCV auto-rotate inconsistency.

  The choice is Dom's.

## 6. Limits
- [NV] Other players: mpv, MPC-HC/LAV, VLC 4.x. mpv uses FFmpeg's demuxer and display matrix, so it probably honours the MKV flag [I].
- [NV] Rotation via JPEG EXIF orientation: changes frame bytes (outside the passthrough rule); not tested.
- [NV] Flips (`hflip`/`vflip`).
- Synthetic frames only; the container-level result does not depend on JPEG content [I].
- VLC checked through one stepped frame in a paused Direct3D11 window, one run per file; fullscreen and other outputs (OpenGL, Direct3D9) not tested [NV].
- Matroska IDs verified only against FFmpeg 9.0.2's output, not an independent writer such as mkvmerge [NV].
