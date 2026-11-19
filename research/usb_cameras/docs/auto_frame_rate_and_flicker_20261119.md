# The "auto" frame rate and mains flicker (2026-11-19)

Question: when the requested frame rate is "auto", should skellycam choose 25 or 30 fps by region, and
does lamp flicker cause problems if it always chooses 30?

A sub-agent (sonnet) made this web and file research. Much of the web evidence is secondhand (patent
summaries, maker support pages). The UVC specification text was not read. "Inferred" marks reasoning
without a source. Nothing here was measured on our cameras.

## Findings

1. **Exposure time is the cause of banding, not frame rate.** Mains at 50 or 60 Hz makes lamps pulse at
   100 or 120 Hz. An exposure of N x 1/100 s (50 Hz) or N x 1/120 s (60 Hz) removes the bands.
   Sources: <https://support.d-imaging.sony.co.jp/support/ilc/flicker/01/en/>,
   <https://red.com/red-101/flicker-free-video-tutorial>,
   <https://onlinemanual.nikonimglib.com/d6/en/16_menu_guide_04_15.html>.
2. **Short exposures always show flicker under a flickering lamp.** The exposures of motion capture
   (1/250 to 1/1000 s) are shorter than one light pulse, so the multiple rule cannot apply.
3. **Frame rate changes only how the bands move (inferred).** When the frame rate divides the pulse rate
   (30 fps at 60 Hz mains, 25 fps at 50 Hz mains), the bands stand still and the brightness does not
   beat. On a mismatch (30 fps at 50 Hz mains) the bands roll and the brightness beats at about 10 Hz.
4. **Lamps.** LED drivers have ripple at twice the mains frequency
   (<https://www.mouser.com/applications/flicker-happens-lighting/>). IEEE 1789-2015 limits it
   (<https://www.energy.gov/eere/ssl/articles/flicker-understanding-new-ieee-recommended-practice>).
   Inferred: magnetic-ballast fluorescent, cheap LED and PWM-dimmed LED flicker strongly;
   high-frequency ballasts, good LED drivers and daylight hardly flicker.
5. **Our four cameras, MJPG modes at 720p and 1080p** (from
   `../results/windows/Gerald/suite_20261119T030441Z/descriptors/descriptors.json`):

   | Camera | Rates (fps) | 25? | 50? |
   |---|---|---|---|
   | Razer Kiyo Pro | 60, 30, 24, 20, 15, 10, 5 | no | no |
   | Logitech C930e | 30, 24, 20, 15, 10, 7.5, 5 | no | no |
   | Logitech C922 | 60 (720p only), 30, 24, 20, 15, 10, 7.5, 5 | no | no |
   | Generic camera | 30, 25 | yes | no |

6. **The UVC Power Line Frequency control** (0 disabled, 1 50 Hz, 2 60 Hz, 3 auto) is advertised by all
   four cameras. The result files hold no current value. Windows:
   `KSPROPERTY_VIDEOPROCAMP_POWERLINE_FREQUENCY`
   (<https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/ksproperty-videoprocamp-powerline-frequency>).
   Linux: `V4L2_CID_POWER_LINE_FREQUENCY`
   (<https://docs.kernel.org/6.5/userspace-api/media/v4l/control.html>). macOS: no public API; Chromium
   sends raw UVC requests. Whether the control changes anything at manual exposure is not known
   (inferred: it only limits the steps of auto exposure).
7. **Knowing the mains frequency without asking** (ratings inferred): the OS region is medium to high
   (wrong for travellers; Japan has both grids); the time zone is weaker; the camera's own value is
   often a vendor default; a measurement of banding in short-exposure frames is reliable where flicker
   exists.
8. **Other software.** OBS uses the device default. No webcam software was found that chooses 25 by
   region. Inferred: 30 is the usual default.
9. **Motion capture.** No source from markerless motion capture was found. Inferred: a stable frame rate
   and a fixed exposure matter more for triangulation than flicker; whether flicker harms pose
   estimation is untested.

## Options for "auto"

| Option | Cost | Benefit |
|---|---|---|
| Always 30 | Rolling bands and beating under 50 Hz lamps at short exposure | Works on all four cameras |
| 25 or 30 from the OS region | 25 is missing on three of four cameras; wrong for travellers | Still bands at 50 Hz mains |
| Follow the camera's Power Line Frequency | The value may be a vendor default | No region lookup |
| Always 30, warn when flicker is measured | Needs a detector | Does not depend on the region |
| Exposure rules by mains frequency | Needs the region or a measurement; long exposures blur motion | Removes the cause |

## Missing evidence

- The current Power Line Frequency value of each camera, and whether it changes manual exposure.
- A measurement of banding at 25 against 30 fps under 50 Hz lamps at short exposure.
- Guidance from a motion capture vendor; the effect of flicker on pose estimation.
