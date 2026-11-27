# 4TBY — Decisions of the user on the review of the 3b code (Q876 to Q881)

**Status:** absorbed into
[`specs/windows-capture.md#133-range-rule`](../../specs/windows-capture.md#133-range-rule),
[`specs/windows-capture.md#222-rules-of-step-3b`](../../specs/windows-capture.md#222-rules-of-step-3b),
[`specs/recorder.md#67-the-capture-info-json`](../../specs/recorder.md#67-the-capture-info-json),
[`specs/recorder.md#152-open-points`](../../specs/recorder.md#152-open-points),
[`specs/capture-timings.md#54-steps-that-apply`](../../specs/capture-timings.md#54-steps-that-apply),
[`specs/capture-timings.md#85-the-step-ids`](../../specs/capture-timings.md#85-the-step-ids),
[`skellycam/tests/capture/test_detection_and_modes.py`](../../skellycam/tests/capture/test_detection_and_modes.py),
2026-11-26 (commit to dom/jpeg-encode-tests; was accepted, 2026-11-26 (user, relayed by the supervisor)).

## Decision

The words of the user on 2026-11-26: "agree to all" (Q876 to Q881).

1. **Q876.** The NV12 type of the fixture `NATIVE_26` of T-CAP-26 is at 15 fps.
2. **Q877.** A take of a camera in NV12 records `capture_format` `NV12`.
3. **Q878.** When Quick Sync holds more frames than its normal depth (2) and gives none back, the
   camera falls back to OpenCV for the rest of that open, as after a Quick Sync error.
4. **Q879.** Yes to both, spec and tests first, in a follow-up lane after the merge of this branch:
   (a) a record-only certify check that reports whether Quick Sync works and how long the check
   takes; (b) the check of the product runs in a child process with a time limit (5 s suggested, as
   for camera detection); a hang or a crash means "no Quick Sync, use OpenCV". Until then the check is
   [NV] on other machines.
5. **Q880.** A raw Media Foundation camera reports the step `jpeg_encode`.
6. **Q881.** These choices of
   [ADR-ZEK6](ZEK6-choices-of-the-jpeg-encode-at-capture-code.md) are accepted: a raw mode opens only
   with a mode at 30 fps or more; the input range is decided one time for each camera loop; frames that
   Quick Sync still holds at a close are dropped; a Quick Sync encoder that does not open at the start
   is not counted as a fallback; the mode label of the ring shows the requested format.

## Reason

- The user decided each item.

## Open work

See [open-work.md](../open-work.md).
