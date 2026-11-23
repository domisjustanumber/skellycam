# BW5M — Decisions of the user on the two verdicts, the gate not complete and the certify test set

**Status:** absorbed into
[`specs/certify.md#364-the-full-report-is-not-a-production-sign-off-yet-u-q599-q610`](../../specs/certify.md#364-the-full-report-is-not-a-production-sign-off-yet-u-q599-q610),
[`specs/certify.md#366-fixes-of-the-code-that-the-reviews-found`](../../specs/certify.md#366-fixes-of-the-code-that-the-reviews-found),
[`specs/certify.md#3610-two-verdicts-the-pipeline-and-each-camera-model-u-q611`](../../specs/certify.md#3610-two-verdicts-the-pipeline-and-each-camera-model-u-q611),
[`specs/certify.md#3611-changes-to-the-test-set-u-q612-to-q618`](../../specs/certify.md#3611-changes-to-the-test-set-u-q612-to-q618),
[`specs/certify.md#63-the-disk-benchmark-u`](../../specs/certify.md#63-the-disk-benchmark-u),
2026-11-23 (commit to dom/certify-4; was accepted, 2026-11-23 (user; questions Q610 to Q618 after the second
pass and the gap review of the certify report; the supervisor relayed the answers and Q608, Q609)).

## Decision

The user decided these items on 2026-11-23. They are not built. [`certify.md`](../../specs/certify.md) section
3.6 states them, beside the decisions of
[ADR-H2A0](H2A0-decisions-of-the-user-on-the-certify-report-shape.md). The choices of the agent are in
[ADR-MEE1](MEE1-choices-of-the-certify-report-shape.md) (proposed).

The words of the user: "Q610-Q611 agree"; "Q612-Q618 agree, Q616 record only for now, but do more tests on this
machine to get a better read on it".

1. **Q610.** Until `cycles`, `group:take-30` and `group:contention` with `group:open` exist, a full run writes no
   pass into the local record; it writes "gate not complete", for the pipeline and for each model. The full plan
   states what the run does today (about 30 s, no risk text about many opens). Quick does not change: a quick
   pass stays a smoke-test pass. The full pass of the pipeline needs the take of 30 s and the check of all
   cameras together; the full pass of a model needs the cycles.
2. **Q611.** Two verdicts. In the words of the user: "there are two things that can pass - the pipeline itself,
   and specific camera models ... if a pipeline works for say 3 models of camera connected, but 1 camera model
   fails ... I would deem that as the pipeline works and is good for use with 3 cameras, and the 4th camera may
   need special attention, or just isn't up to the task". The summary gets one line for the pipeline on this
   system beside the lines of the models. (a) A failed camera check counts against that model only. (b) A
   pipeline check that fails on one model and passes on at least one other model counts against that model.
   (c) A pipeline check that fails on each tested camera counts against the pipeline. (d) A system check counts
   against the pipeline. (e) With one model only, a failed pipeline check cannot be assigned: the pipeline line
   says "not decided" and the model fails. The local record gets a pipeline row beside the model rows.
3. **Q612.** One disk check: `system:disk-benchmark` merges into `system:disk`: the real recorder with synthetic
   frames, 20 s at the real load and 10 s at twice the load, judged on the write and hand-over delays. No
   separate file of 1 GiB. The camera counts come from the measured JPEG size.
4. **Q613.** Quick reads the kind of the volume of the recording folder (fixed, removable, network) and the free
   space as minutes of recording, and fails under 5 minutes free.
5. **Q614.** `cycles` runs 30 opens for each model and 10 opens of the whole group (about one minute for each
   model).
6. **Q615.** The restore of the camera settings after a kill of the server becomes a pipeline gate check, when
   the product keeps the "before" values on disk (Q608).
7. **Q616.** A check of the cameras in step (the spread) is record only for now, with its limit shown. More runs
   on the test system calibrate it.
8. **Q617.** The exposure sweep at 60 fps and the two Auto checks at 60 fps go; `rate:<w>x<h>@60` stays.
9. **Q618.** The take of 5 minutes is an option of full, not the default; the default full keeps the take of
   30 s.
10. **Q608 and Q609, relayed.** The product keeps the restore record of the camera settings on disk, so a restore
    survives a kill of the server (a later fix round). The headline frame rate of a take is the frame count
    divided by the elapsed time; the median is only for the figures of each frame interval. Certify uses the same
    rule for its take rate.

**What this entry replaces.** C8 of [ADR-KG00](KG00-certify-decisions-of-the-user-on-draft-2.md) (the disk
benchmark of 1 GiB), by Q612. The text of KG00 does not change.

## Reason

The second pass on the real reports found that a full run of 28 s wrote a full pass into the local record, and
that its plan announced 565 s and many opens. The gap review found that the sign-off checks, the disk check and
the cycles did not test what a sign-off needs, and that a pipeline fault and a camera fault had one verdict.

## Open work

[open-work.md](../open-work.md)
