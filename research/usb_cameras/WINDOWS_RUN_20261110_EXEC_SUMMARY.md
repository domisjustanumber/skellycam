# Executive summary: full Windows camera run, Gerald, 2026-11-10/11

> **Correction (2026-11-11):** the full write-up, [docs/windows_results_20261110.md](docs/windows_results_20261110.md), re-read every number from the raw data. Its §12 lists where this summary is wrong. The main points:
> - The 17:04 wedge was a Media Foundation open of the Kiyo Pro **alone**, not during multi-camera use. A multi-camera DirectShow trigger fits only 2 of the 4 recorded wedge onsets.
> - In W-PYMF the generic camera dropped off the bus. **Both** the C++ and the Python MF probes failed about a third of their cycles there (39/60 and 40/60).
> - The generic camera's gain and white balance also had no visible effect.
>
> Use the write-up, not this summary.

**Run:** `suite/windows` full profile, started 23:00:03 on 2026-11-10 and finished 04:24:24 on 2026-11-11 (5 h 24 min; the estimate was 7 h).
**Results:** [results/windows/Gerald/suite_20261111T040003Z/](results/windows/Gerald/suite_20261111T040003Z/) ([summary.md](results/windows/Gerald/suite_20261111T040003Z/summary.md) has every rating with links to its evidence).
**Scope:** tier 0 only (cameras as found, no registry or driver changes); streaming tests at exactly 720 lines and at least 30 fps; plan: [docs/capture_stack_options_plan.md](docs/capture_stack_options_plan.md) section 6.
**Cameras:** Razer Kiyo Pro (SuperSpeed, Thunderbolt xHCI), Logitech C930e, Logitech C922 and a generic 4c4a:4a55, all high-speed on the Intel xHCI.

## Bottom line

- **The run is valid.** Exit code 0. All 18 tests and the background Kiyo poller (W-KIYO) finished `ok` with 0 errors. Every control restore check passed.
- **Media Foundation (MF) native capture stays the best Windows path.** On all four cameras it delivered the camera's own MJPEG and passed 400/400 in-process open/close cycles with no hangs. It also passed 100/100 cycles with a new process each time.
- **The pure-Python MF probe (pymf) matches wincam** on the Kiyo, C930e and C922. That supports building the product in Python over MF. Its cycle test on the generic camera was not scored after a device fault.
- **DirectShow is a fallback only through the ffmpeg CLI** (400/400 cycles on all four). On the Kiyo, PyAV over DirectShow streams the wrong format below the requested rate.
- **OpenCV is not a candidate** on any camera: in every OpenCV variant, no camera delivered a first frame within 2 s.
- **The Kiyo wedged again,** at 01:52:46 local (plug-in age 8 h 46 min), during W-MULTI's simultaneous DirectShow opens. It did not recover. This is the second wedge to start during multi-camera DirectShow opens, and the plug-in-age theory (about 210 min) does not fit it.

## Headline ratings

**Raw JPEG** (the camera's MJPEG bytes delivered unchanged):

| Camera | MF | DirectShow | PyAV over DirectShow |
| --- | --- | --- | --- |
| Kiyo | yes | yes | **no** |
| C930e | yes | yes | yes |
| Generic | yes | yes | yes |
| C922 | yes | yes | yes |

On the Kiyo and the generic camera, one mode did not hold its requested frame rate.

**Listing devices and formats without opening a camera:**
- Device listing rates `partial`, because whether the keys survive a replug or reboot was not measured. The key source itself is stable.
- MF, DirectShow and the USB hub descriptors list formats without opening, on all four cameras.
- The ffmpeg format list is incomplete on the Kiyo, C930e and C922.
- OpenCV and WinRT cannot list formats without opening the camera.
- PyAV and ffmpeg device listing "touches but harmless" on all four cameras, including the wedged Kiyo.

**Exposure, focus and auto modes:**

| Camera | Controls change the image (MF / DirectShow) | Auto-exposure back on | Autofocus back on |
| --- | --- | --- | --- |
| Kiyo | yes | partial | inconclusive (its focus kept hunting) |
| C930e | partial: effect seen; fails "works before and after stream start" and 3/3 runs | yes | yes |
| Generic | partial: no focus control (fixed focus); same two misses as the C930e | yes | n/a |
| C922 | yes | partial | yes (OpenCV DirectShow: **no**, only sets the flag) |

Through OpenCV, the control ratings are mostly `partial` on every camera.

**Open/close reliability (400 cycles in-process, 100 with a new process each time):**

| Route | Kiyo | C930e | Generic | C922 |
| --- | --- | --- | --- | --- |
| MF in-process | 400/400 | 400/400 | 400/400 | 400/400 |
| DirectShow via ffmpeg | 400/400 | 400/400 | 400/400 | 400/400 |
| MF, new process each time | 100/100 | 100/100 | 100/100 | 100/100 |
| DirectShow via PyAV | partial (wrong format, slow) | yes | yes | yes |
| OpenCV (3 variants) | **no** (latency) | **no** | **no** | **no** |

- The 100-cycle new-process runs rate `partial` only because 100 cycles cannot support a ≥99 % claim.
- The generic camera ran at about 25.7 fps throughout because its auto-exposure lengthened exposure in room light.

**Timestamps:** this run has no ground truth (the A5 strobe rig is not built).
- The MF sample time sits on a 16 ms host grid, so it rates `no`.
- PyAV's pts is synthesized, so it also rates `no`.
- The frame-index fits are recorded but stay `untested` until the rig measures them.

## The Kiyo wedge

- **When and where:**
  - The first symptom came at 01:52:46 local, in W-MULTI "ds all-at-once" round 7.
  - That round opens all four cameras at once through DirectShow, one process per camera.
  - The Kiyo's open timed out and the watchdog killed it after 30 s.
  - The background poller stopped getting answers at 01:53:17.
- **No second process was touching the Kiyo.** The runner held the camera lock for the whole round, so the only process on the Kiyo was that round's own.
  - LogiTune and Signal were closed. Of the vendor software, only `razer_elevation_service` was running.
  - Earlier rounds passed with the Kiyo: six rounds of the same DirectShow pattern, plus 15 rounds of MF multi-camera opens.
  - 25 s before the wedge, in round 4, the generic camera failed and re-enumerated. It is on a different USB controller from the Kiyo.
- **It did not recover.** Re-probes at 01:56, 02:01 and 02:08 failed, and the poller kept failing until the end. A replug is still the only known recovery.
- **Little was lost.** The Kiyo's own tests, including its 400-cycle reliability runs, had all finished before the wedge.
- **A second wedge on the same day.** In a camera check at 17:04 on 2026-11-10, the Kiyo wedged about 4 minutes after a replug. At the time, Signal held the C930e and LogiTuneAgent was attached to all four cameras. ([results/windows/Gerald/scene_check_20261110/](results/windows/Gerald/scene_check_20261110/))
- **What this says (inferred, not proven):**
  - Neither wedge fits the 210-minute plug-in-age theory.
  - Both happened while several cameras were being opened or used at once.
  - Together with the 11-06 R2 onset, also in W-MULTI's DirectShow opens, the evidence now points at concurrent multi-camera use, especially DirectShow opens, as the trigger.
- **Windows' camera-usage record is not useful for this.** Its snapshots before and after the run are identical; the newest entry is from 2026-10-13. It records neither the suite's tools nor Signal, so it does not cover desktop apps.

## Camera state after the run

- All four cameras are present with PnP status OK.
- The Kiyo remains wedged until it is replugged.
- All control restores were confirmed. Image brightness after the restores was 0.93–1.06 times the as-found level.

## Suggested next steps

1. **Replug the Kiyo** and confirm it streams.
2. **Test the trigger directly:** run W-MULTI on its own, several times. Compare DirectShow all-at-once with MF all-at-once, with and without the other cameras. If DirectShow all-at-once reproduces the wedge and MF does not, that settles the multi-camera theory and supports MF-only capture.
3. **Build the A5 strobe rig** for timestamp ground truth. It is the only way to rate the frame-index-fit routes.
4. **Rerun the generic camera's pymf cycles** (`--only W-PYMF`) to close the one untested pymf cell.

Nothing from this run is committed.
