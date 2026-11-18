# Range of the test cameras' uncompressed modes (2026-11-18)

Question: when a camera streams YUY2 or NV12, are the values limited range (Y 16 to 235) or full range (0 to
255)? A JPEG is always full range, so the conversion must know.

Run by a sub-agent on the four test cameras through the pymf capture code; the main session saved this text
and did not rerun it. Script: `probe.py`. Numbers: `results/<camera>.json` (statistics only; each file also lists
the camera's native media types).

**Result: the two Logitech cameras send limited range. The Kiyo Pro and the generic camera send full range,
although Media Foundation reports "16 to 235" for their YUY2 modes. The operating system's range flag cannot
be trusted.**

## Method

- One camera at a time. Each capture: 30 frames discarded, 60 kept, frames in memory only.
- Controls were not set. For each camera a YUY2 capture and an MJPG capture of the same scene ran back to
  back. Exposure and gain read the same in both, except the C930e at 640x480 (gain 0 in YUY2, 9 in MJPG).
- Test A: the share of Y samples below 16 or above 235. Limited-range output cannot have a large share there.
- Test B: the Y percentile profile (1, 5, 25, 50, 75, 95, 99) of the YUY2 frames against the same camera's
  decoded MJPG frames (full range, BT.601), under two hypotheses: (a) the YUY2 is already full range; (b) it
  is limited range and is expanded first. The fit is the mean absolute error in Y levels.
- All four cameras opened and streamed with no error. The Kiyo Pro did not wedge.

## What Media Foundation reports

- `MF_MT_VIDEO_NOMINAL_RANGE` is 2 (16 to 235) on every uncompressed type of every camera, except the generic
  camera's NV12 type, which reports 1 (0 to 255). Every MJPG type reports 1.
- `MF_MT_YUV_MATRIX` is 2 (BT.601) and `MF_MT_VIDEO_PRIMARIES` is 2 (BT.709) on every type.
- `MF_MT_TRANSFER_FUNCTION` is not set on any type.
- `MF_MT_VIDEO_CHROMA_SITING` is 6 on YUY2 and 1 on MJPG and NV12.

## Measured

| Camera | Mode | Y min / max | Y below 16 / above 235 | Fit (a) full | Fit (b) limited | Verdict |
|---|---|---|---|---|---|---|
| C930e | YUY2 640x480 at 30 | 20 / 231 | 0 / 0 | 10.09 | 0.60 | limited |
| C930e | YUY2 1280x720 at 10 | 19 / 232 | 0 / 0 | 10.89 | 0.43 | limited |
| C922 | YUY2 640x480 at 30 | 77 / 235 | 0 / 0 | 14.43 | 0.73 | limited |
| C922 | YUY2 1280x720 at 10 | 56 / 235 | 0 / 0 | 14.44 | 0.14 | limited |
| Generic (4c4a:4a55) | YUY2 640x480 at 30 | 0 / 170 | 12.9 % / 0 | 0.61 | 14.79 | full |
| Generic | NV12 1280x720 at 30 | 0 / 178 | 18.7 % / 0 | 0.59 | 14.65 | full |
| Kiyo Pro (1532:0e05) | YUY2 640x480 at 30 | 13 / 240 | 0.0007 % / 3.8 % | 0.21 | 12.15 | full |
| Kiyo Pro | YUY2 1280x720 at 30 | 13 / 244 | 0.0008 % / 6.1 % | 0.12 | 12.26 | full |

- The better hypothesis fits 20 to 100 times better than the other for every camera.
- Chroma was never outside 16 to 240 on any camera.
- The C922 scene was saturated at Y 234 to 235, the ceiling of the limited range.
- The generic camera's scene was dark (median Y about 20).

## Other facts from the run

- The C930e and C922 offer YUY2 at 1280x720 only up to 10 frames/s. The generic camera offers NV12, not YUY2,
  at 1280x720.
- MJPG headers: no Adobe marker on any camera. C930e and C922: no JFIF marker, 4:2:2. Generic: JFIF, 4:2:2.
  Kiyo Pro: JFIF, 4:2:0.
- Auto exposure was on for the C930e and C922 (exposure -6 and -7); the generic camera and the Kiyo Pro were
  on manual exposure (-7; gain 4 and 0).

## Not verified

- Whether the range depends on the scene or on the exposure mode. Each camera saw one scene.
- The NV12 range of the Logitech cameras and the Kiyo Pro.
- The colour matrix from pixel content. Only the reported flag is known, and test B assumes BT.601.
