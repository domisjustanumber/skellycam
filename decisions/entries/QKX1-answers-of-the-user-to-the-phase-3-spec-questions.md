# QKX1 — Answers of the user to the eight questions of the phase 3 spec draft; two interim rules

**Status:** accepted, 2026-11-19 (user; commit to dom/native-jpeg).

## Decision

The user answered the eight questions of the first draft of
[`specs/windows-capture.md`](../../specs/windows-capture.md) on 2026-11-19
([ADR-4CQC](4CQC-phase-3-windows-capture-spec-and-test-list.md)). The spec marks each answer [Un].
They add to the decisions of [ADR-EN7A](EN7A-phase-3-windows-capture-decisions.md).

1. **U1.** While OpenCV is the default source on Windows during the build of phase 3, the OpenCV source
   finds its camera by the device part of the Media Foundation link: the part before the interface
   class GUID.
2. **U2.** The shared loop has no burned-in frame stamp and no "reopen after 30 slow frames", on any
   OS, from step 3a.
3. **U3.** The pass limits of the comparison run (D48 item 3) apply to the native run. The OpenCV run
   is the reference.
4. **U4.** When a camera dies during a recording: the timing file of each camera ends at its own last
   frame; the multi-frame rows continue with the cameras that are still alive; the recording info names
   the dead camera and its last frame. This is an interim rule of phase 3 only. It must change back
   when the recorder of phase 5 comes.
5. **U5.** A frame with an error flag gives the old recorder the last good image again, and the camera
   process logs the count at stop. This is an interim rule of phase 3 only. It must change back in
   phase 5.
6. **U6.** A camera that dies while no recording runs is treated as a failed camera.
7. **U7.** A request for a group with different mode rates is refused as a whole, and no camera is
   opened. How this applies to a running group is still a question of the spec.
8. **U8.** The full mode list of step 3c holds H.264 and RAW modes with `selectable: false`, as in
   section 9 of [`specs/frame-ring.md`](../../specs/frame-ring.md). They are never opened.
   `supported_modes` of step 3a stays MJPG only. This corrects the wording of D4 ("not listed as
   selectable").
9. **U9.** The first failure is kept for each camera.

## Reason

- The user, 2026-11-19: answers to the questions of the first draft of the spec.
- U4 and U5 keep the old recorder usable in phase 3. The user: they "must change back once we have the
  new recorder".

## Consequences

- Phase 5 removes U4 and U5 (open work).
- The finaliser and the timing files must accept unequal frame counts in phase 3 (U4).

## Open work

See [open-work.md](../open-work.md).
