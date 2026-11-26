# YQN1 — Choices of the size floor and the tracking note (Q887 to Q889)

**Status:** proposed, 2026-11-26 (agent).

## Decision

The user decided the size floor and the note
([ADR-25VS](25VS-decisions-of-the-user-on-the-later-opens-and-the-size-floor.md)). An agent chose the
items below. Section 22.2 of [`specs/windows-capture.md`](../../specs/windows-capture.md) marks each one
[YQN1 n]. T-CAP-162 to T-CAP-165 test them.

1. **One predicate.** `modes.size_at_floor(width, height)` on the server: width 640 or more and height
   360 or more. The UI has the same two numbers in `resolution-floor.ts` (another language, so a second
   copy); each has its test.
2. **The reason in `capture_modes`.** "below 640x360". The size comes before the rate: a mode below both
   floors has the size reason. "never opened" comes first.
3. **The refusal.** The text is "no mode of 640x360 or more", the code `below-floor`, as for the rate
   floor. The whole-request check refuses a requested size below the floor (HTTP 422); the mode choice
   refuses it at `set mode` before any other rule. The 422 text names each reason once.
4. **After the open.** The shared loop fails a camera whose open reports a size below the floor (the
   OpenCV source), stage `set mode`, as for a rate below the floor.
5. **The UI control.** `CameraConfigResolution` keeps its presets (640x480, 1280x720, 1920x1080). A
   custom size below the floor is not applied, as an invalid number is not, and the fields show the
   applied size again; the inputs have the minimums 640 and 360.
6. **The note.** Under each resolution control (the camera list and the settings of a grid tile), in the
   gray small text of the rate notes, linked with `aria-describedby`, while the chosen size is below
   1280x720. It does not block the choice. The English text is "Hand and face
   tracking will be limited at this resolution. 1280 × 720 or more gives the best tracking." (key
   `trackingLimitedByResolution`, English only, as the other keys of step 4).
7. **Test fixtures.** The tests that used a size below the floor for a mode now use one above it: the
   lane tests use 640x480 in place of 320x240 (W, H); T-CAP-154 has its extra MJPG mode at 1280x720;
   `NATIVE_61` uses 1600x900 for the size with YUY2 only at 10 fps; `NATIVE_25` uses 960x960 for the
   size of equal area with a smaller width and 1024x576 for the size with only low rates.

8. **Q886 by camera.** The manager keeps the cameras that fell back by `camera_id`, for the app run.
9. **The texts of a refusal.** A requested size below the floor: "camera `<id>`: the requested size
   `<w>x<h>` is below the smallest size 640x360". A camera whose every mode is below a floor, with a mode
   below the size floor: "camera `<id>` has no mode of 640x360 or more at 30 fps", with no mode list. A
   camera that the check refuses gets no other reason from the mode choice.
10. **The mechanism of Q886.** Each status has the flag `encoder_failed`; the camera loop sets it at a
    fallback. At each write of the switch, the manager reads the flag of the status of the newest group
    of each camera (its shared value stays readable after the close of the group) and writes it only as
    True, so that a fallback that lands meanwhile is never reset. The loop also keeps its own count.
11. **The rule of the note.** The note shows when the width is below 1280 or the height is below 720:
    960x960 shows it.
12. **The Quick Sync test frame.** 1280x720 NV12. The user asked for at least 640x480, ideally 720p
    (Q887). At 1280x720 the check took 0.51 to 0.57 s in fresh processes on the development machine,
    as at 320x240 (0.51 to 0.55 s).

## Reason

- Items 1 to 4: the size floor follows each rule of the rate floor, with the same code.
- Items 5 and 6: the smallest change of the control, with the pattern of the existing notes.
- Item 7: each test still checks what its spec row says.
