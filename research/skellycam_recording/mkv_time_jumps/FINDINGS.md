# MKV time jumps: OpenCV and Blender with missing MJPEG blocks

Date: 2026-11-19. Synthetic images only. No camera was used. A sub-agent (opus) ran the test; the main
session saved this text from its report.

## Question

The new recorder writes one Matroska file per camera, codec V_MJPEG, with the JPEG frames stored
unchanged. A missing frame has no block. Option B: the block time counts rows (row r at r/30 s), so the
file has a time jump at each missing frame. Option A: the block time counts stored blocks, so there is no
jump.

## Method

- `make_files.py`: 300 synthetic 640x480 JPEG frames (quality 90). Each shows its row number in large
  digits, and the background colour changes per frame. The JPEG bytes are muxed with PyAV
  `add_mux_stream("mjpeg", rate=30, width=640, height=480)`, with no re-encode. Packet time_base 1/30,
  pts=dts=row (B) or block index (A), duration 1. The demuxed bytes of frames 0 and 150 equal the source
  JPEGs.
- `probe_opencv.py`: ffprobe, PyAV, OpenCV. `summarize_opencv.py`: reads and seeks near the holes.
- `probe_blender.py` (headless): renders every movie frame index n=0..299 through three paths.
  `identify_pngs.py` identifies the drawn number.
- Identification: the nearest reference frame (64x48 grey, mean absolute difference). The worst distance
  was 0.98 (OpenCV) and 1.41 (Blender); the smallest gap to the second best was 2.9 and 4.2.
- Media went to a temp folder outside the repository.

## Versions

Python 3.13.18; PyAV 19.0.2 (libavformat 63.1.102); numpy 2.5.5; opencv-contrib-python 5.1.0.95, backend
`FFMPEG`; ffprobe 9.0.2; Blender 5.2.3 LTS (avformat 62.12.100).

## Files

| file | rows missing | stored | timestamps |
|---|---|---|---|
| full | none | 300 | row |
| B-one | 100 | 299 | row |
| B-run | 100-189 | 210 | row |
| B-tail | 200-299 | 200 | row |
| B-tail-dur10 | 200-299 | 200 | row, Segment Duration byte-patched to 10 s |
| B-head | 0-9 (first block 333 ms) | 290 | row |
| B-head30 | 0-29 (first block 1000 ms) | 270 | row |
| A-one | 100 | 299 | block |
| A-run | 100-189 | 210 | block |

## Muxer facts

- Block times are in whole ms (TimestampScale 1 ms): row 1 = 33 ms, row 10 = 333 ms.
- DefaultDuration follows `rate`: 30 gives 33333333 ns; no rate gives no element.
- `width`/`height` only work as kwargs of `add_mux_stream`. Without them the mux fails (error 22).
- The container duration is not settable in PyAV. The muxer writes the last block time + 1 frame
  (B-tail 6.666 s). B-tail-dur10 was byte-patched; the PyAV writer cannot make it.

## ffprobe / PyAV

| file | packets | format dur s | first/last pts ms |
|---|---|---|---|
| full | 300 | 10.000 | 0 / 9967 |
| B-one | 299 | 10.000 | 0 / 9967 |
| B-run | 210 | 10.000 | 0 / 9967 |
| B-tail | 200 | 6.666 | 0 / 6633 |
| B-tail-dur10 | 200 | 10.000 | 0 / 6633 |
| B-head | 290 | 10.000 | 333 / 9967 |
| B-head30 | 270 | 10.000 | 1000 / 9967 |
| A-one | 299 | 9.966 | 0 / 9933 |
| A-run | 210 | 7.000 | 0 / 6967 |

avg_frame_rate and r_frame_rate are 30/1 in every file. nb_frames is empty (Matroska has no frame count).

## OpenCV

| file | FRAME_COUNT | frames read | drawn returned | duplicates |
|---|---|---|---|---|
| full | 300 | 300 | 0..299 | 0 |
| B-one | 300 | 299 | stored only (99 then 101) | 0 |
| B-run | 300 | 210 | stored only (99 then 190) | 0 |
| B-tail | 200 | 200 | 0..199 | 0 |
| B-tail-dur10 | 300 | 200 | 0..199 | 0 |
| B-head | 300 | 290 | 10..299 | 0 |
| B-head30 | 300 | 270 | 30..299 | 0 |
| A-one | 299 | 299 | stored only | 0 |
| A-run | 210 | 210 | stored only | 0 |

FRAME_COUNT = duration x FPS. POS_FRAMES counts reads. POS_MSEC is the block time measured from the first
block: `round(POS_MSEC*30/1000) + first row` = the drawn number for all 1,269 reads of the B files. It is
wrong after the hole for A.

Seek POS_FRAMES=n, then read (drawn number; fail = read False):

| n | full | B-one | B-run | B-tail | B-head | A-one | A-run |
|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 | 10 | 0 | 0 |
| 99 | 99 | 99 | 99 | 99 | 109 | 99 | 99 |
| 100 | 100 | 101 | 190 | 100 | 110 | 101 | 190 |
| 102 | 102 | 103 | 192 | 102 | 112 | 103 | 192 |
| 120 | 120 | 120 | 210 | 120 | 130 | 121 | 210 |
| 150 | 150 | 150 | 240 | 150 | 160 | 151 | 240 |
| 190 | 190 | 190 | 280 | 190 | 200 | 191 | 280 |
| 201 | 201 | 201 | 291 | fail | 211 | 202 | 291 |
| 209 | 209 | 209 | 209 | fail | 219 | 210 | 299 |
| 250 | 250 | 250 | 250 | fail | 260 | 251 | fail |
| 290 | 290 | 290 | 290 | fail | fail | 291 | fail |
| 299 | 299 | 299 | 299 | fail | fail | fail | fail |

A POS_MSEC seek to n*1000/30 gives the same numbers. Cause: OpenCV seeks by time to about n-16, then
counts blocks forward. With B, n inside a hole or up to about 16 rows after it lands on a later row.

## Blender

Paths: VSE movie strip, VSE clip strip from `movieclips.load`, and `images.load` (source MOVIE) in a
compositor Image node. n = scene frame - 1. All paths agree within the length.

Length (frame_duration): full 300, B-one 300, B-run 300, B-tail 200, B-tail-dur10 300, B-head 290,
B-head30 270, A-one 299, A-run 210. fps is 30.0.

| file | frames where n = row n | repeats | where n is not row n |
|---|---|---|---|
| full | 300 | 0 | none |
| B-one | 299 | 1 | 100 shows 99 |
| B-run | 210 | 90 | 100-189 show 99 |
| B-tail | 200 | 0 | 200-299 blank (VSE) or 199 (Image node) |
| B-tail-dur10 | 200 | 100 | 200-299 show 199 |
| B-head | 0 | 97 | n+10 or n+9 |
| B-head30 | 0 | 0 | n+30 |
| A-one | 100 | 0 | n>=100 shows n+1 |
| A-run | 100 | 0 | n>=100 shows n+90 |

Blender shows the last block at or before n/30 s after the first block. B-head's first block at 333 ms
(rounded) makes about 1 in 3 frames repeat; B-head30 (1000 ms) is clean. No crash or hang.

## Answers

- **OpenCV, B:** (a) the count is the row span (duration x fps), not the stored count; after a dead tail
  it is the last stored row + 1. (b) Reads return stored blocks only, with no inserted frames. POS_MSEC
  gives the row. A seek gives row n except in a hole and up to about 16 rows after it (a later row).
  (c) No crash or hang. FRAME_COUNT is larger than the frames that can be read. Missing leading rows
  shift index 0.
- **OpenCV, A:** (a) stored count; (b) stored block n; (c) no fault.
- **Blender, B:** (a) the time span, not the stored count; (b) row n, holding the frame before the hole
  inside it; (c) no crash; repeated frames when the first block is not on a whole ms; the length is cut
  after a dead tail.
- **Blender, A:** (a) stored count; (b) stored block n; (c) no fault.

## Not tested

Other OpenCV backends; Linux and macOS; Blender UI playback, proxies, timecode indexes and tracking;
damaged frames stored as blocks; other frame rates and lengths; players; leading offsets other than 10
and 30 rows.
