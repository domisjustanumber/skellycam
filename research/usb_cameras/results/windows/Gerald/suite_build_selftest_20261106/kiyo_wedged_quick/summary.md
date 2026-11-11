# Windows UVC suite run, Gerald, 20261106T212100Z

Mode: quick (cycles 4, process cycles 2, frames 10, MJPEG 1.5 s per mode). Elapsed 1m29s. Results folder: `C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\results\windows\Gerald\suite_build_selftest_20261106\kiyo_wedged_quick`. Raw frames: `C:\Users\Dom\Documents\skellycam-raw\results\windows\Gerald\suite_build_selftest_20261106\kiyo_wedged_quick`.

Ratings use the plan section 3 thresholds (common/rating.py). Tier 1 = needs the one-time admin configuration (MetadataBufferSizeInKB0); everything else is tier 0. Each cell links to the JSON with the criteria and evidence. A camera x API aggregate cell (e.g. G-TS without a route suffix) shows the best available route, and 'untested' ranks above 'no' there by design (an unscored route may still work); the per-route cells hold the measured ratings. '(gated)' = skipped by the device-fault gate.

## Cameras

| Key | Name | VID:PID | Speed | Tier-1 metadata | Last arrival (discovery) | Last arrival (latest check) |
| --- | --- | --- | --- | --- | --- | --- |
| `1532:0e05:port=PCIROOT(0)#PCI(1C04)#PCI(0000)#PCI(0200)#PCI(0000)#USBROOT(0)/4.4` | USB Video Device (Kiyo) | 1532:0e05 | SS | True | 2026-11-06T20:32:29.065252+00:00 | 2026-11-06T20:32:29.065252+00:00 |

## Ratings per goal, camera and API

### reliability

| Camera | ds_inproc | ds_modeswitch | ds_newproc | mf_inproc | mf_modeswitch | mf_newproc | opencv_inproc | opencv_skellycam |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | [partial (format mismatch)](W-CYC.json) | [partial (format mismatch)](W-CYC.json) | [partial (format mismatch)](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) |

### ctrl_list_equivalence

| Camera | all |
| --- | --- |
| all | [yes](W-CTRL-LIST.json) |

## Device faults, first failures and the Kiyo onset

Faults (0x8007001F / unreleasable reader / killed streaming command) gate a camera's streaming work from the next test on; each later test re-probes it once with a 1-frame MF capture. "(gated)" in a rating cell = the camera was faulted when that test started.

First failed camera command per camera (any class):

- USB Video Device (1532:0e05) Kiyo: 2026-11-06T21:21:31.665896+00:00 in W-CYC, ds MJPG 1280x720@30 at format: 4 (other), plug-in age 49.0 min

## Tests

| Test | Status | Elapsed | ETA was | Errors | Gated (faulted at start) | JSON |
| --- | --- | --- | --- | --- | --- | --- |
| W-ENV | ok | 0m00s | 0m20s | 0 | - | [W-ENV.json](W-ENV.json) |
| W-CTRL-LIST | ok | 0m00s | 0m16s | 0 | - | [W-CTRL-LIST.json](W-CTRL-LIST.json) |
| W-CYC | ok | 1m28s | 1m59s | 0 | - | [W-CYC.json](W-CYC.json) |
