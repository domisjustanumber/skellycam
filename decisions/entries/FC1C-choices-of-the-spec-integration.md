# FC1C — Choices of the spec integration of 2026-11-20

**Status:** proposed, 2026-11-20 (supervisor and agent).
Accepted in part by [ADR-6YGH](6YGH-acceptance-of-the-as-built-choices-of-fix-lanes-4-and-5-and-of-certify.md) on 2026-11-25: items 1 to 3, 5 to 12 and 14 to 19 (Q759 to Q762).

## Decision

The specs [`camera-requests.md`](../../specs/camera-requests.md) (A),
[`unix-capture.md`](../../specs/unix-capture.md) (B) and [`certify.md`](../../specs/certify.md) (C)
are merged on one branch. A second cross-spec review found contradictions between them and
[`windows-capture.md`](../../specs/windows-capture.md) (W). These choices fix them, with the rulings
of [ADR-H0BQ](H0BQ-user-rulings-of-the-spec-integration.md) and
[ADR-BVK7](BVK7-certify-rulings-of-the-user-one-test-one-row.md). A owns the exposure search, its
states, names and limits, the 60 fps fall back and the USB link lookup; B the diagnostics keys and the
failure codes; C the check names and `camera_checks.json`. The other specs point to the owner and cite
sections, not commit ids.

Choices of the supervisor (the review items):

1. N1: the frame hashes arm at the first `ready` of an open and at each record start, not after a live
   change. C reads the set of the first `ready` before the live change to -8, and compares the set of
   the record start with the MKV blocks.
2. N2: the local row stores, for exposure, gain and focus, the result of each route tried, keyed by
   its `control_path` value. The product chooses a `works` route; with several, the one that works on
   the most models of the shipped file.
3. N3: certify never applies the record to itself. `works`: read-back, hold and image check pass.
   `unproven`: the image check is `not-run`; the control is offered. `no`: a check failed; only `no`
   removes a control.
4. N5: native capture turns on for a camera model (model, backend, OS key, ABI), never for an OS key.
   This follows item 2 of ADR-BVK7; C6 of
   [ADR-KG00](KG00-certify-decisions-of-the-user-on-draft-2.md) named a verified OS. Decided by the
   user: item 1 of [ADR-F2KY](F2KY-rulings-of-the-user-after-the-third-consistency-check.md).
5. N6: the bullet "never `skipped` with `reviewed`" goes. N7: no manual exposure is `not-run` with
   `no-manual-exposure`, never `fail`.
6. N8: a client waits 25 s from the apply response at 30 and 60 fps, and 45 s more after a fall back
   starts. N9: `exposure_search.count` is kept by the main process for each camera ID for the life of
   the group.
7. N10 to N14: the product values of `usb_link` everywhere; `no-manual-exposure` is no failure code of
   `CaptureFailure`; one list of T-CAP edits, owned by A; a route proven in 100 µs reports `100us`;
   after a fall back from 60, both Auto checks at 60 are `not-run` with `prior-check-failed`.
8. N15: `<model>:gate:no-hang` is an ordinary check. A roll-up that is not `pass` has the reason
   `gate-check-failed` or `gate-check-not-run`.
9. Contract: a cancel kills the child of the running check with its process tree, no check starts
   after it, and the re-check gives only cleanup rows; `section` is `null`; the keyword options of
   `certify_plan` are declared.
10. The change texts of A and B are applied in W and `recorder.md`. W and the code hold the facts:
    the USB link is ported as `usb_connection.py`, the event-log check is ported; step 5 builds the UI
    label of the link (L1). A's T-CAP list wins; case 1 of T-CAP-104 changes; T-CAP-96 is retired.

Choices of the agent:

11. On a route with no time unit, `exposure` holds the step index 0 to 7 (0 the darkest); a value
    below 0 sets the step `v + 12`, clamped. The search tries the steps 0 to 7. The UI texts are item 4 of
    [ADR-F2KY](F2KY-rulings-of-the-user-after-the-third-consistency-check.md). Certify sets the steps 5 and 4 in place of -7 and -8.
12. With no `works` route, the product uses an `unproven` route by the same rule.
13. Where no sequence number exists, `<label>:time-gaps` (`long_intervals` 0 over the quick take,
    else `frame-gaps`, not calibrated) takes the place of `<label>:sequence` in the gate and the item.
14. A model counts as checked when its item is `pass` or `fail`, or `partial` with one unit whose
    `opens` judged; so a run that judged no unit writes no row.
15. Quick order: detection, the apply, the retries, the settings change, the take, the close, then
    `self:hang-100ms` (only with 10 s left; a retry only with 14 s left). A check that runs at the end
    of the budget is stopped and is `not-run` with `over-budget`. Estimate: min(30, ⌈20 + N/4⌉ + 10).
16. The group state gets `take_state` (`none`, `recording`, `ended_with_error`) and `ended_take_summary`; the
    UI reads them through `endedTakeNotice`.
17. Contract commit `9e6d575` (skellycertify ADR-T191): a `full` camera item has `gate`; a reviewed
    row of a `partial` item keeps `not_passed`; the cleaned camera name holds no markup, link or IPv4
    address.
18. W marks T-CAP-92 to T-CAP-98 retired (item 10 of
    [ADR-22EJ](22EJ-decisions-of-the-user-for-linux-and-macos-native-capture.md)); the pause tests
    check the 404.
19. New tests: T-REC-50, T-REC-51, T-REQ-73 to T-REQ-76, T-CERT-68 to T-CERT-71.

## Reason

One owner for each rule and one repository state remove the contradictions. The choices of the agent
are the smallest rules that make the rulings testable.

## Consequences

- Question 12 of `specs/certify.md`: with 30 s, the quick hang self-check usually gives
  `over-budget` when a camera is checked.
