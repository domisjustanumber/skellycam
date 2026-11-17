# Ring slot size from resolution alone (2026-11-17)

Status: the sample frames are not in git. Dom ruled on 2026-11-17 that camera frames and recordings are
never committed unless they are golden reference files. `frames/` (84 camera frames: the largest and the
median per camera and mode) stays on the local disk only and is ignored. `scan_files.jsonl` (8.6 MB, rebuilt
by `scan.py` from `skellycam-raw`) is not committed either.

## Rule (accepted by Dom, 2026-11-17)

- estimate = 2,048 + 0.5 x width x height bytes
- slot = 2 x estimate, rounded up to 4 KiB (about 1 byte per pixel + 4 KiB)
- A frame that does not fit is not copied: the slot is flagged oversize and
  counted. The recorder is separate and writes every frame.
- The product logs each camera's largest frame as a fraction of its slot,
  warns above 50 %, and shows the oversize count.

| mode | estimate | slot | largest frame seen | slot / largest |
|---|---|---|---|---|
| 640x480 | 155,648 | 311,296 | 79,130 (C930e) | 3.9 |
| 1280x720 | 462,848 | 925,696 | 276,269 (Kiyo Pro) | 3.4 |
| 1920x1080 | 1,038,848 | 2,080,768 | 607,032 (Kiyo Pro) | 3.4 |
| 3840x2160 | 4,149,248 | 8,298,496 | no data | |

## Evidence

- Measured: 850,817 camera frames (C922, C930e, generic 4c4a:4a55, Kiyo Pro)
  rescanned from `skellycam-raw` and the repo results. Largest content was
  0.30 bytes per pixel at 640x480 and above, 0.36 at the tiny modes. No frame
  exceeded the estimate. Tables: `agg.txt`, `rules.txt`.
- Encoders, parsed from real frames (`headers.json`, `dqt_census.json`):
  C922 and C930e are 4:2:2 at about IJG quality 94; the Kiyo Pro is 4:2:0 at
  quality 90 and lowers quality under load; the generic camera is 4:2:2 at
  quality 70 and switches between 17 table sets down to quality 20.
- Simulated (`sim.py`, `sim.txt`): each camera's own tables on a content
  ladder. The simulation matched real frame sizes to within 0.965-1.007x.
  The cameras' largest frames match a pixel-noise target behind about
  1.5 px of blur. 0.5 bytes per pixel corresponds to about 1 px of blur at
  the strictest tables seen. The slot (1 byte per pixel) is exceeded only by
  unblurred per-pixel noise.
- Frame rate and USB speed do not bound frame size: on a narrow alt setting
  the C930e sent the same size frames at a lower frame rate.
- The camera-advertised maximum (width x height x 2) is the uncompressed
  size copied into the MJPEG descriptors. libjpeg-turbo's guaranteed bound
  is 4 bytes per pixel for 4:2:2. Neither is used.

## Not verified

- Nothing above 1080p; the 4K row is extrapolated.
- The sharpness control, a 4:4:4 camera, and tables above quality 94.
- About 100k frames with unknown resolution were left out (all under 235 kB).
- The scan and simulation were run once by a sub-agent and not rerun.

## Files

`scan.py` (-> `scan_files.jsonl`), `agg.py`, `rules.py` (-> `envelope.json`),
`headers.py`, `jpeg_inspect.py`, `dqt_census.py`, `sim.py`, `gain.py`,
`table.py`, `keys.py`, `miss.py`. The scripts read from
`C:\Users\Dom\Documents\skellycam-raw\`, which is outside the repo.
