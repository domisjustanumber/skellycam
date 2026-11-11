# Windows UVC suite run, Gerald, 20261107T005445Z

Mode: full (cycles 50, process cycles 15, frames 30, MJPEG 3.0 s per mode; streaming mode scope >= 30 fps and >= 720 lines). Elapsed 5h00m. Results folder: `C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\results\windows\Gerald\kiyo_overnight_20261106`. Raw frames: `C:\Users\Dom\Documents\skellycam-raw\results\windows\Gerald\kiyo_overnight_20261106`.

Ratings use the plan section 3 thresholds (common/rating.py). Tier 1 = needs the one-time admin configuration (MetadataBufferSizeInKB0); everything else is tier 0. Each cell links to the JSON with the criteria and evidence. A camera x API aggregate cell (e.g. G-TS without a route suffix) shows the best available route, and 'untested' ranks above 'no' there by design (an unscored route may still work); the per-route cells hold the measured ratings. '(gated)' = skipped by the device-fault gate.

## Cameras

| Key | Name | VID:PID | Speed | Tier-1 metadata | Last arrival (discovery) | Last arrival (latest check) |
| --- | --- | --- | --- | --- | --- | --- |
| `1532:0e05:port=PCIROOT(0)#PCI(1C04)#PCI(0000)#PCI(0200)#PCI(0000)#USBROOT(0)/4.4` | USB Video Device (Kiyo) | 1532:0e05 | SS | True | 2026-11-07T00:50:01.798169+00:00 | 2026-11-07T00:50:01.798169+00:00 |

## Ratings per goal, camera and API

### kiyo

| Camera | all |
| --- | --- |
| USB Video Device (1532:0e05) Kiyo | [yes](W-KIYO.json) |

## Device faults, first failures and the Kiyo onset

Faults (0x8007001F / unreleasable reader / killed streaming command) gate a camera's streaming work from the next test on; each later test re-probes it once with a 1-frame MF capture. "(gated)" in a rating cell = the camera was faulted when that test started.

Kiyo onset, USB Video Device (1532:0e05) Kiyo (W-KIYO foreground poller from 2026-11-07T00:54:45.228218+00:00, plug-in age at start 4.7 min):

- answered every control poll so far (3602 polls)

## Tests

| Test | Status | Elapsed | ETA was | Errors | Gated (faulted at start) | JSON |
| --- | --- | --- | --- | --- | --- | --- |
| W-KIYO | ok | 5h00m | 5h00m | 0 | - | [W-KIYO.json](W-KIYO.json) |
