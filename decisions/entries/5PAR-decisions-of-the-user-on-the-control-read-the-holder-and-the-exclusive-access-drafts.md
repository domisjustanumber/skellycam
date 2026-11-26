# 5PAR — Decisions of the user on the control read during a take, the holder of a certify check, and the exclusive access drafts

**Status:** absorbed into [`specs/windows-capture.md#21-exclusive-access-of-a-camera`](../../specs/windows-capture.md#21-exclusive-access-of-a-camera),
[`specs/certify.md#20-exclusive-access-the-public-calls-for-freemocap-and-the-light-data`](../../specs/certify.md#20-exclusive-access-the-public-calls-for-freemocap-and-the-light-data),
2026-11-25 (commit to dom/exclusive-access-spec; was accepted, 2026-11-25 (user; the supervisor relayed the answers
to Q811 to Q813)).

## Decision

1. **Q811 (QX-1), answer (b).** The read of `windows-capture.md` 11.4 (exposure, gain and focus, one time each second)
   stays during a take. On a build with no control monitor it finds a change of those controls by another program;
   only controls in manual are compared by value, because auto values drift. A certify check measures the frame gaps
   around each control read, for each camera model. When the check shows that the read harms a model, the read pauses
   during a take for that model. This supersedes the words "no poll during a take" of Q784 (item 8 of
   [ADR-AA4X](AA4X-decisions-of-the-user-on-exclusive-access-of-a-camera.md)) for the read of 11.4.
2. **Q812 (QX-2), answer (a).** The holder child of `<label>:in-use:other-program` opens the camera with OpenCV
   (`CAP_DSHOW`, `CAP_V4L2`, `CAP_AVFOUNDATION`). Certify never judges OpenCV.
3. **Q813.** The drafts of commit 6159ec494 (`windows-capture.md` 21, `unix-capture.md` 4.13 and 6.9, `certify.md` 20
   and 12) are accepted, with the choices of
   [ADR-FR2J](FR2J-choices-of-the-exclusive-access-and-overlap-specs.md), among them: HTTP 409 at a record start while
   another program streams; the macOS lock from the open to the close; warn and mark, no set-back; no program names in
   reports; `system:kernel` drops only `kernel_major` and `kernel_minor`; the Linux 1 s rule for dependent controls.
   ADR-AA4X, ADR-13BB and ADR-CQ2X are absorbed in the commit that records this.

## Reason

1. "Our four wedges all began at a stream start or stop, never mid-stream and never during control polling alone"
   (`research/usb_cameras/docs/kiyo_pro_wedge_research.md` §1, branch `dom/research`). One read each second is not a
   burst. The certify check gives the evidence for each model.
2. The rule "no OpenCV checks" is about what certify judges; here OpenCV is only the other program.
