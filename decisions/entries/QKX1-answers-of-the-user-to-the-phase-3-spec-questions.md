# QKX1 — Thirteen answers of the user to the phase 3 spec drafts; three interim rules

**Status:** accepted, 2026-11-19 (user; commit to dom/native-jpeg).

## Decision

The user gave thirteen answers on 2026-11-19 to the drafts of
[`specs/windows-capture.md`](../../specs/windows-capture.md): to the eight questions of the first
draft (U1 to U4, U6 to U9), to one agent choice of it (U5), and to the four questions of the second
draft (U10 to U13)
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
   opened. U10 gives the rule for a running group.
8. **U8.** The full mode list of step 3c holds H.264 and RAW modes with `selectable: false`, as in
   section 9 of [`specs/frame-ring.md`](../../specs/frame-ring.md). They are never opened.
   `supported_modes` of step 3a stays MJPG only. This corrects the wording of D4 ("not listed as
   selectable").
9. **U9.** The first failure is kept for each camera.
10. **U10.** A request is checked as a whole first. A refused request (HTTP 409 or 422) changes
    nothing, also on a running group. Then the change of each camera is applied on its own. A camera
    whose change fails becomes `failed`, and the other cameras are not touched. Example: three cameras
    run at 30 fps, and a request asks one of them for 60. The one-rate rule refuses the request, and
    all three keep running at 30.
11. **U11.** skellycam does not offer modes below 30 fps (the user: "we will not be doing anything
    lower than 30fps"). They are left out of `supported_modes` and are not selectable in the 3c list.
    A request for one is refused. A mode at 29.97 fps counts as 30: the floor is 29.97. A camera with
    no mode at 30 fps or more at the requested size fails with the reason "no mode at 30 fps or
    more". The D49 test of each declared MJPG rate at 720p shrinks to 30 on each camera and 60 on the
    C922 and the Kiyo Pro. The warm-up stays 90 frames and the ready limit 15 s (D21). D16 does not
    change.
12. **U12.** On a hang during a recording, the camera process tries to finish the files of that
    camera for at most 5 s, then ends hard. This is an interim rule. It goes with the recorder of
    phase 5, whose files survive a hard stop.
13. **U13.** The interim preview relay sends the newest frame of each camera on its own, without a
    wait for equal frame numbers. The preview frames of different cameras can then be one gate round
    apart. Phase 4 replaces this relay.

## Reason

- The user, 2026-11-19: answers to the questions of the first draft of the spec.
- U4, U5 and U12 keep the old recorder usable in phase 3. The user: they "must change back once we have the
  new recorder".

## Consequences

- Phase 5 removes U4, U5 and U12 (open work).
- The finaliser and the timing files must accept unequal frame counts in phase 3 (U4).

## Open work

See [open-work.md](../open-work.md).
