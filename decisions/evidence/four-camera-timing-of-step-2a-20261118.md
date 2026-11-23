# Four-camera comparison of the timing, step 2a of the frame ring (2026-11-18)

This fact was in the item "Phase 2 of the frame ring" of [open-work.md](../open-work.md). It moved
here on 2026-11-23 with no change of its text, because the Rules put long evidence in `evidence/`.

Fact, 2026-11-18: the four-camera comparison of the timing. Before is commit 0a66994c3, after
is commit 8a1f9b517. Each had two runs of 60 s, with a 720p30 MJPG request, lockstep and
four cameras (Logitech C922, Logitech C930e, Razer Kiyo Pro and a generic camera), lights on.
The values below are before (run 1 and 2), then after (run 1 and 2).

- Frames per camera: 1548 and 1547, then 1548 and 1548.
- Group frame rate: 25.76 and 25.76, then 25.76 and 25.77.
- Median spread of the grab times between cameras: 0.205 and 0.189 ms, then 0.183 and 0.194 ms.
- The step that copied a frame to the old ring now holds the JPEG encode and the capture check.
  Median: 1.02 and 1.24 ms, then 1.87 and 1.81 ms. 95th percentile: 1.58 and 1.92 ms, then
  3.39 and 3.41 ms.
- Whole processing of a frame, median: 2.86 and 3.24 ms, then 3.97 and 3.91 ms.
- No traceback. Four JPEG rings of 27,779,072 bytes each, 111,116,288 bytes in total. The
  largest frame is 0.10 to 0.22 of its slot. There was no oversize frame, no cut-off frame, no
  capture-error frame and no failed ring write.
- An earlier pair of runs the same day in a dim room gave 8.00 frames per second before and
  after. The cause is not verified.
- The result files are in the research branch `dom/research` of this repository. They are not
  committed there yet.
