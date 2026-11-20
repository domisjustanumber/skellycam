# MKV black placeholder blocks: FFmpeg, PyAV, OpenCV, Blender and skellycam's reader

Date: 2026-11-19. Synthetic images only. No camera was used. A sub-agent (opus) ran the test; the main
session saved this text from its report. See also `../mkv_time_jumps/FINDINGS.md` (missing blocks with
and without time jumps).

## Question

A missing frame is stored as a black placeholder JPEG block on its row. Every file then has exactly one
block per row, with constant timestamps (row r at r/30 s, no time jumps). Do the tools read such files
exactly? Does it matter whether the placeholder has the same size and chroma layout as the camera frames?

## Method

- `make_files.py`: 300 synthetic camera JPEGs (quality 90) per config, each with its row number drawn
  large. Configs: 640x480 and 1920x1080, each as 4:2:2, 4:2:0 and 4:4:4
  (`cv2.IMWRITE_JPEG_SAMPLING_FACTOR`; layout checked by parsing SOF0). Muxed by packet with PyAV
  `add_mux_stream("mjpeg", rate=30, width, height)`, no re-encode, pts = dts = row. Every block of every
  file was demuxed again: the bytes equal the source bytes.
- Placeholders (cv2.imencode of a zero image): P-same (the camera's size and layout, q90), P-samemin (the
  same, q1 with optimised Huffman tables), P-420 (the camera's size, always 4:2:0), P-gray (one
  component), P-small (16x16).
- Patterns: one (row 100), run (rows 100 to 189), tail (rows 200 to 299), head (rows 0 to 9), full (the
  control). 70 files in total.
- `probe.py`: ffprobe; `ffmpeg -f null`; PyAV full decode; OpenCV (FFMPEG backend) count, sequential
  reads and seeks at 30 points before, inside and after each run; skellycam `SequentialVideoReader`.
  Reference: the full file decoded by the same tool (hash compare). A placeholder row must be black.
- `probe_blender.py`, `compare_blender.py` (headless): frame_duration of the movie clip, the image and
  the VSE strip; every n from 0 to 299 rendered through a VSE movie strip at 25 %, selected n at 100 %.
- `check_head_height.py`: placeholders of other sizes as the first blocks of a 640x480 file.
- Media and JSON results (1.1 GB) are in a temp folder outside the repository.

## Versions

PyAV 19.0.2, opencv 5.1.0 (FFMPEG backend), numpy 2.5.5, ffprobe/ffmpeg 9.0.2, Blender 5.2.3 LTS,
Windows 11.

## Placeholder byte sizes (bytes)

| size, layout | q90 | q90 optimised |
|---|---|---|
| 640x480 4:2:2 | 6,627 | 2,684 |
| 640x480 4:2:0 | 5,427 | 2,084 |
| 640x480 4:4:4 | 9,027 | 3,884 |
| 640x480 gray | 3,932 | 1,361 |
| 1920x1080 4:2:2 | 41,127 | 16,484 |
| 1920x1080 4:2:0 | 33,267 | 12,524 |
| 1920x1080 4:4:4 | 57,327 | 24,584 |
| 1920x1080 gray | 24,632 | 8,261 |

- The quality setting does not change the size of a black JPEG (q1 is 1 byte smaller than q90).
  Optimised Huffman tables cut it by about 60 %. The optimised placeholder decodes to exactly 0.
- One hour of 1080p placeholders at 30 fps (108,000 blocks): 4:2:2 optimised 1.785 GB (measured;
  Matroska overhead 47 B per block); 4:2:2 q90 4.45 GB; 4:2:0 optimised 1.36 GB; 4:4:4 optimised 2.66 GB.
- For comparison, the synthetic 1080p camera frames average 60 to 88 kB.

## Results

### Same size and layout (P-same, P-samemin): exact in every tool

All 6 camera configs, all 4 patterns:

- ffprobe and PyAV: 300 packets, 10.000 s, one pix_fmt for the whole file, no warning.
- OpenCV: FRAME_COUNT 300, 300 reads, every camera row pixel-equal to the full file, placeholders decode
  to max 0, all 30 seek points exact.
- Blender: 300 frames on all three paths, also with a dead tail. Every camera frame equals the control,
  placeholders are black, the first frame after a run is pixel-equal at 100 %.
- SequentialVideoReader: 300 frames, no exception.

### Same size, different layout (P-420, P-gray)

- FFmpeg, PyAV, OpenCV, SequentialVideoReader: exact. Frames come back black, frames after them are
  pixel-exact, no frame fails. frame.format changes mid-stream and back. swscaler prints "deprecated
  pixel format used" at each change. No slowdown measured.
- **Blender breaks.** A placeholder in the middle or at the tail is not black: P-420 shows striped
  garbage (max 225), P-gray shows a stale, shifted image of an earlier frame (max 255). Camera frames
  after it are exact.
- **Blender, placeholder as the first block:** all 290 camera frames of the file have wrong colour and a
  ghost image (max diff 83 to 165). ffprobe reports the first block's format as the stream pix_fmt.

### Different size (P-small, 16x16)

- In the middle or at the tail: no error. PyAV and SequentialVideoReader return 16x16 arrays. OpenCV
  returns black at the camera size. Blender draws a 16x16 patch that is not always black.
- **As the first block, every tool fails.** FFmpeg's MJPEG decoder treats pairs of blocks as interlaced
  fields when the first block is shorter than 3/4 of the container height (640x352 triggers it at
  height 480, 640x368 does not). Half of the head packets give "No JPEG data found". PyAV and
  SequentialVideoReader raise InvalidDataError at frame 0. OpenCV reads 0 frames. Blender shows wrong
  frames for all camera rows.

### Decode time (one run each, 1080p 4:2:2, seconds for 300 frames)

| file | PyAV | OpenCV |
|---|---|---|
| full | 3.57 | 3.68 |
| same-one | 3.29 | 4.05 |
| same-run | 2.66 | 3.13 |
| 420-run | 2.46 | 3.03 |
| gray-run | 2.39 | 2.94 |

No slowdown from placeholders. Files with a run decode faster because they hold fewer bytes. Noise is
about 10 %.

## Answers

1. A placeholder with the camera's size and chroma layout is exact in every tool: count 300, frame i =
   row i, seeks exact, placeholders black, frames after a placeholder unchanged, no warning.
2. A placeholder with a different chroma layout breaks Blender (garbage on the placeholder; wrong colour
   for the whole file when it is the first block). The other tools are exact.
3. A placeholder with a different size must never be used; as the first block it breaks every tool.
4. Use optimised Huffman tables: about 16.5 kB per 1080p 4:2:2 placeholder, 1.8 GB per hour.

## Not tested

- Real camera JPEGs (their own tables, restart markers, AVI1 or APP0 variants).
- P-gray and P-small with 4:2:0 and 4:4:4 cameras.
- Other OpenCV backends; Linux and macOS; players; frame rates other than 30.
- Blender: UI playback, proxies, timecode indexes; pixel checks only through the VSE movie strip.
- Whether the Blender garbage is the same on each run.
