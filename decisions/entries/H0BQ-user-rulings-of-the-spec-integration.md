# H0BQ — Rulings of the user for the spec integration of 2026-11-20

**Status:** absorbed into
[`specs/certify.md#31-check-names-a`](../../specs/certify.md#31-check-names-a),
[`specs/certify.md#34-the-check-groups-of-a-camera-and-the-summary-item-u-c-37`](../../specs/certify.md#34-the-check-groups-of-a-camera-and-the-summary-item-u-c-37),
[`specs/certify.md#41-the-rules-u`](../../specs/certify.md#41-the-rules-u),
[`specs/certify.md#83-phase-g-re-check-u-a`](../../specs/certify.md#83-phase-g-re-check-u-a),
[`specs/certify.md#96-progress-before-each-step-u-a`](../../specs/certify.md#96-progress-before-each-step-u-a),
[`specs/certify.md#102-the-assumptions-as-checks`](../../specs/certify.md#102-the-assumptions-as-checks),
[`specs/certify.md#107-macos-the-approach-probes-for-exposure-and-for-the-cameras-jpeg-u-a`](../../specs/certify.md#107-macos-the-approach-probes-for-exposure-and-for-the-cameras-jpeg-u-a),
[`specs/certify.md#113-how-the-product-uses-it-u`](../../specs/certify.md#113-how-the-product-uses-it-u),
[`specs/recorder.md#84-the-state-ended-with-an-error-added-on-2026-11-20`](../../specs/recorder.md#84-the-state-ended-with-an-error-added-on-2026-11-20),
[`specs/camera-requests.md#84-the-ui-when-a-take-ends-by-itself-with-an-error`](../../specs/camera-requests.md#84-the-ui-when-a-take-ends-by-itself-with-an-error),
2026-11-25 (commit to dom/log-cleanup; was accepted, 2026-11-20 (user, relayed by the supervisor)).

## Decision

The user ruled these points on 2026-11-20, while the specs
[`specs/camera-requests.md`](../../specs/camera-requests.md),
[`specs/unix-capture.md`](../../specs/unix-capture.md) and [`specs/certify.md`](../../specs/certify.md)
were brought together on one branch.

1. **The summary item of a camera model** in a certify report: `skipped` (busy) when each unit is held
   by another program; `fail` when an open, rate or recording check fails; `pass` when each check
   passes; otherwise `partial`.
2. **Progress.** The progress callback names each check before that check starts, also a computed
   check and a roll-up check.
3. **After a cancelled run,** only the cameras that the run touched are checked again, at most 5 s
   each.
4. **The frame sequence in the gate.** Where the source gives no sequence number (for example macOS,
   if AVFoundation gives none), the sequence check is `not-run` with a reason, and it does not block
   the gate. The gaps are then judged from the timestamps. Where the source gives a sequence number,
   the sequence check stays required.
5. **The macOS approach probes.** Each probe check carries the `module` "macOS probes", so that the
   rows of the probes that did not pass stand apart from the checks of a camera model, which carry
   the model name. The many failed probe rows are accepted.
6. **A take that ends by itself with an error.** The state changes to "ended with an error". The app
   state no longer says that a recording runs, the record button of the UI returns to "Start", and the
   error and the summary of the take show at once, with no click on "Stop".
7. **The quick budget.** The quick level has a hard budget of 30 s for skellycam (skellytracker 75 s,
   freemocap 15 s, 120 s in total). This replaces the provisional 40 s for each package. The quick
   part of skellycam stops at 30 s. A check that does not fit is `not-run` with the common reason
   `over-budget`, never a failure. The freemocap session reported this decision first; the user then
   confirmed it to the supervisor.

## Reason

The user gave these rulings after the second cross-spec review of the three specs and after the
reports of the freemocap session and of the owner of the certify contract.

## Consequences

- The specs apply each point: `specs/certify.md` 3.4 (item 1), 9.6 (item 2), 8.3 and 9.3 (item 3),
  10.2 and 11.3 (item 4), 3.1 and 10.7 (item 5), 4.1 (item 7); `specs/recorder.md` 8.4 and
  `specs/camera-requests.md` 8.4 (item 6).
- The other rulings of the user that the integration applies are already in
  [ADR-BVK7](BVK7-certify-rulings-of-the-user-one-test-one-row.md): the gate at the base mode (item 2),
  A7 and A8 only when A5 and A6 failed (item 7), 29.97 fps counts as 30 (item 8), the OpenCV text
  "Exposure is set by the camera on this system" for now (item 9), and the eight plain steps on a
  macOS route with no time unit (item 10). This entry does not repeat them.
- With the budget of 30 s, the hang self-check of quick usually does not fit when a camera is
  checked. Question 12 of `specs/certify.md` asks the user to accept this.
- The technical choices that the specs need for these points are in
  [ADR-FC1C](FC1C-choices-of-the-spec-integration.md).
