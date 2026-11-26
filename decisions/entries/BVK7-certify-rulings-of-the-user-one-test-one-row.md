# BVK7 — Rulings of the user after the cross-spec review: one test one row, the gate, macOS routes

**Status:** absorbed into
[`specs/certify.md#33-one-test-one-row-u`](../../specs/certify.md#33-one-test-one-row-u),
[`specs/certify.md#25-checked-camera-models-and-the-local-record-u-a`](../../specs/certify.md#25-checked-camera-models-and-the-local-record-u-a),
[`specs/certify.md#51-selection-rule-a`](../../specs/certify.md#51-selection-rule-a),
[`specs/certify.md#53-skellycam-auto-u-a-13`](../../specs/certify.md#53-skellycam-auto-u-a-13),
[`specs/certify.md#104-probes-u-a`](../../specs/certify.md#104-probes-u-a),
[`specs/certify.md#107-macos-the-approach-probes-for-exposure-and-for-the-cameras-jpeg-u-a`](../../specs/certify.md#107-macos-the-approach-probes-for-exposure-and-for-the-cameras-jpeg-u-a),
[`specs/certify.md#113-how-the-product-uses-it-u`](../../specs/certify.md#113-how-the-product-uses-it-u),
[`specs/certify.md#115-from-a-report-to-a-release-u-a`](../../specs/certify.md#115-from-a-report-to-a-release-u-a),
[`specs/certify.md#116-what-the-contract-lacks-for-this`](../../specs/certify.md#116-what-the-contract-lacks-for-this),
2026-11-25 (commit to dom/log-cleanup; was accepted, 2026-11-20 (user, relayed by the supervisor)).

## Decision

The user ruled on 2026-11-20. [`specs/certify.md`](../../specs/certify.md) marks these points [U].

1. **One test, one row.** The words of the user: "each test must have it's own row, so a test either
   passes or fails so it's clear what exactly failed." No check folds two or more tests. A test that
   could not run is `not-run` with a reason (for example `too-dark`), not `record-only`. The row
   check `<label>` and the reason code `partial` go. The contract states the same rule in format
   1.4.0 (`skellycertify` commit `1c9c191`, skellycertify ADR-V1TR).
2. **The gate for native capture** on Linux and macOS, and the `verified` rule of the shipped file:
   named checks of a `full` run at the base mode only (720p at 30): the camera opens, its mode is
   granted, its frame rate, native JPEG delivery, timestamps and frame sequence (these stay
   required), a short recording through the native source, and no check of that model ended as hung
   or crashed. The summary item plays no part. Failed exposure, gain or focus checks do not block:
   the control is then absent in the UI. A roll-up check may state the gate. The local row stores the
   result of each gate check and the route and result of each control.
3. **macOS camera control.** The words of the user: "I want to use the widest/best supported route
   for camera control and prefer that over the measurement units for exposure. So if the method that
   uses EV is better than the one that uses seconds, I'd take that."
4. **Answers to the first form of draft 3.** A new OS version makes each model unchecked again. The
   macOS full run of about 10, 16 and 27 minutes for 1, 2 and 4 models is accepted for now. The
   requests for notices and for the risk to a device were sent to the owner of the contract (format
   1.4.0 holds `notices` and `risks`).
5. **Pause.** The public pause route is removed. Nothing in certify may call it.
6. **Probes.** Each macOS approach probe is its own pass or fail check for each control. Probes do not
   count toward the summary item of the camera. This changes "probes are record-only" of
   [ADR-GVC0](GVC0-certify-decisions-of-the-user.md) item 8.
7. **Exclusive opens.** The probes A7 and A8 run only when A5 and A6 failed. This is the one accepted
   exception to "every approach is tried" of [ADR-C5BR](C5BR-macos-approach-probes-in-certify.md).
8. **29.97 fps counts as 30.** The words of the user: "for the purposes of '30fps and above are the
   only modes I want to know about' - yes 29.97 counts". Nothing below that class is listed or
   tested.
9. **OpenCV and exposure.** On Linux and macOS the OpenCV source leaves the exposure to the camera.
   This is accepted for now as a known limit of the temporary OpenCV path. The UI says "Exposure is
   set by the camera on this system".
10. **Manual on a unitless macOS route.** Manual shows eight plain steps from darkest to brightest,
    with no time label, for now, until certify runs show the real scales.

## Reason

The cross-spec review of 2026-11-20 found checks that fold several tests, a turn-on rule stated as a
summary word, and open product questions. The user ruled on each.

## Consequences

Points 2, 6 and 7 replace the gate, the probe and the A7/A8 questions of the earlier forms of
draft 3. Point 6 changes item 8 of ADR-GVC0 for probes only.

## Open work

See [open-work.md](../open-work.md).
