# First hardware run of step 3a (native capture through Media Foundation), 2026-11-20

A sub-agent (opus) ran this from 05:41 to 06:30 UTC on the four test cameras, unattended, in a quiet
window agreed with the other sessions. The main session saved this text from its report. Code under test:
`dom/native-jpeg` at 6d496aa24, plus the local commit ee9b6f08b made during the run. Raw results,
recordings and logs are in a temp folder outside the repositories (they hold device paths; they stay
local). No unplug test and no dark-room test was run.

## Lights

The C922 delivered 29.97 fps at 720p30 with default auto exposure. The room was bright.

## Detection (T-CAP-46 passes)

Detection took 0.83 s and found 8 devices, all with `virtual: false`.

| Device | Modes found |
|---|---|
| Logitech C930e | 17 MJPG sizes, all at 30 |
| Logitech C922 | 17 MJPG sizes; 1280x720 at 30 and 60 |
| Razer Kiyo Pro (Media Foundation names it "USB Video Device") | 4 sizes, each at 30 and 60 |
| Generic camera ("USB Camera") | 5 sizes, all at 30 |
| 4 NDI software cameras | no USB IDs, no modes; links under `root#media` |

The links of the four real cameras are lower case as the OS gives them.

## Hardware tests

| Test | Result |
|---|---|
| T-CAP-46 | Pass |
| T-CAP-51 | Fail on `len == 4` only: 8 devices are present (the NDI cameras). The rest passes: arrival gaps 48 ms, full mode lists while two cameras stream. |
| T-CAP-52 | Pass on the three good cameras: 30.00, 30.35, 29.66 fps. MJPG passthrough is byte-equal. |
| T-CAP-53 | Pass: the generic camera measures 25.86 fps and is failed. |
| T-CAP-54 | 30 fps: C922 30.00, C930e 30.00, Kiyo Pro 29.66, generic 25.73 (failed). 60 fps: C922 and Kiyo Pro both deliver 29.66, so both fail at 60. |
| T-CAP-55 | Not run (needs a dark room) |
| T-CAP-56 | Pass: "in use by another program" at the first frame |
| T-CAP-57 | Pass on all three, as table 10.5 predicts |
| T-CAP-58 | Not run (needs an unplug) |
| T-CAP-59 | Pass. Every frame keeps its sample time (same base as perf_counter). Arrival minus sample: C922 and C930e median 0.33 ms, Kiyo Pro 32 ms. |
| T-CAP-60 | Fail on `mean_framerate` 30.6 > 30.3. Counts are equal (1802), replaced = gaps for each camera, and the rate by elapsed time is 29.98 fps. |
| T-CAP-88 | Pass on all three after the fix below |
| 1080p30 | C922 30.17, C930e 30.00, Kiyo Pro 30.17 are ready; generic 25.74 failed |
| T-CAP-92 to 98 | Not run (Linux and macOS) |

## Faults

- Fixed (product): the OpenCV source reported the detection index as its device path, not the DirectShow
  path of spec 4.1. A fake-source test now fails without the fix.
- Fixed (test harness): cameras were labelled by name, so the Kiyo Pro was labelled "generic". Labels now
  come from the USB IDs.
- Open (product): the multi-frame timing file and `take_stats` hold retrieve values of about +/-3.2e8 ms
  with Media Foundation. The per-camera timing files and the stop response are sensible.
- Open (product): after a live change ends in `too_slow`, `measured_fps` keeps the old passing value.
- Open (test, for the user): T-CAP-60 checks `mean_framerate`, the mean of 1/interval per frame; the
  32 ms / 48 ms arrival grid biases it high. T-CAP-51 assumes that no other camera device is installed.
- Open: the NDI software cameras are not marked virtual (their names do not hold "virtual").
- Open: the OpenCV open of the Kiyo Pro takes 11.1 s; under the OpenCV source it missed the 15 s ready
  limit in 2 of 3 runs. The Media Foundation source is not affected.

## Comparison: before (OpenCV, phase 2 code at 699e65139) against native (Media Foundation)

Three cameras (C922, C930e, Kiyo Pro), 720p30 MJPG, 60 s, two runs each.

| | Before, run 1 / 2 | Native, run 1 / 2 |
|---|---|---|
| Frames per camera (equal) | 1802 / 1802 | 1804 / 1802 |
| Camera rate (fps) | 30.00 | 29.99 to 30.03 |
| Interval median / p99 (ms) | 32.0 / 48.2 | 32.0 / 48.1 |
| Interval max (ms) | 75 / 50 | 64 / 96 |
| Replaced frames | not counted | 25 to 32 per camera (= gaps) |
| CPU of the server process tree (cores) | 1.34 / 1.29 | 0.80 / 0.77 |
| Start-up (apply) | 12.9 / 12.7 s | 5.8 / 5.8 s |
| Spread between cameras in one group frame, median / p95 (ms) | 0.17 / 0.43 | 35.8 / 55.4 and 35.0 / 51.1 |

Four-camera native run: the generic camera was `failed` at the rate check (25.74 fps); after it was
unselected, the other three recorded 1803 frames each. No camera log holds "--- Logging error ---".

## The spread between cameras

The two spread figures do not measure the same thing. The "before" figure is the spread of the times of
the grab calls, which the old loop issues together; it says nothing about when each image was made. The
native figure is the spread of real arrival times of the frames that one gate round takes. At the median,
the frames of one group frame arrive about 36 ms apart, and 60 to 77 % of the rounds exceed one frame
period. This follows the gate rule of spec 5.2 (D26). It needs a decision of the user; an offline analysis
of the recorded arrival times (best possible pairing against the actual pairing) is planned.

## Other observations

- Open to first frame: 0.09 to 0.92 s. Close: 0.27 to 1.18 s. Both far under the 5 s limit; the Kiyo Pro
  is the slowest.
- Exposure, gain and focus each set and read back in about 2 ms.
- C930e at stream start: it read manual exposure -5 although -7 was set last, and its gain fell 4, 3, 2
  over three opens. The product sets the controls after the first frame (spec 9.1), so the configured
  values hold.
- Discontinuity flag: set on the first frame of each open, plus one Kiyo Pro frame.
- Unplug path (not tested): a failing `OnReadSample` makes the camera dead at once; `OnEvent` is ignored,
  so a removal that came only as an event would show as "no frame for 2 s".
- All four cameras were alive at the end. The Kiyo Pro did not wedge.

## Helper changes (research checkout, not committed)

`research/usb_cameras/suite/windows/helpers/skellycam_record.py`: a `--unselect-failed` flag; the apply
response's `camera_failures` and `warnings` are saved in the run summary; the CPU of the server tree is
measured with the job object's accounting.
