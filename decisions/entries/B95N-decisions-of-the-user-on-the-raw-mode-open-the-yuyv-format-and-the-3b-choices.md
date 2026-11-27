# B95N — Decisions of the user on the raw-mode open, the YUYV format and the 3b choices

**Status:** absorbed into
[`specs/windows-capture.md#222-rules-of-step-3b`](../../specs/windows-capture.md#222-rules-of-step-3b),
[`specs/windows-capture.md#226-python-api-and-rules-of-the-port`](../../specs/windows-capture.md#226-python-api-and-rules-of-the-port),
2026-11-25 (commit to dom/jpeg-encode-tests; was accepted, 2026-11-25 (user, relayed by the
supervisor; questions Q807 to Q810)).

## Decision

The words of the user on 2026-11-25:

1. **Q807.** "yes. A camera with no MJPG mode at 30 fps or more at the requested size, but a YUY2 or
   NV12 mode at that size, opens the raw mode, logs one line, and the frames are JPEG-encoded. Spec
   item and test first, then code."
2. **Q808.** "a YUY2 take records capture_format `YUYV`; `NV12` is added to SFF-800 on a skellyspecs
   branch."
3. **Q809.** "port the 3c tests of dom/3bc-tests in a later lane, then retire the branch; never merge
   it."
4. **Q810.** "ADR-3WCA, ADR-0Z2F (items 1 to 12) and the five absorbs (TC9B, 53VB, JWZ1, 2AQT, 8ACV)
   accepted."

Section 22.2 of the spec states Q807 and Q808, and 22.6 states the accepted items of Q810. The
choices of the agent that build Q807 and Q808 are in
[ADR-N72V](N72V-choices-of-the-raw-mode-open-and-the-yuyv-format.md) (proposed).

## Reason

- Q807: each camera must record, and each take is JPEG-MKV (Q689).
- Q808: SFF-800 lists `MJPG` and `YUYV` today.

## Open work

See [open-work.md](../open-work.md).
