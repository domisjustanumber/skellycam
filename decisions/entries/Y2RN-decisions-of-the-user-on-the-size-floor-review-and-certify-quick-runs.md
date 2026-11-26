# Y2RN — Decisions of the user on the size floor review and on quick certify runs (Q898 to Q902)

**Status:** absorbed into
[`specs/windows-capture.md#222-rules-of-step-3b`](../../specs/windows-capture.md#222-rules-of-step-3b),
[`decisions/open-work.md#open-work`](../open-work.md#open-work),
2026-11-26 (commit to dom/jpeg-encode-tests; was accepted, 2026-11-26 (user, relayed by the supervisor)).

## Decision

The words of the user on 2026-11-26: "agree to all" (Q898 to Q902).

1. **Q898.** The size floor is two bounds: a mode passes when its width is 640 or more and its height is
   360 or more.
2. **Q899.** A custom size below the floor shows a short error line: "The smallest size is 640 × 360".
3. **Q900.** These choices of [ADR-YQN1](YQN1-choices-of-the-size-floor.md) are accepted: the texts
   "below 640x360" and "no mode of 640x360 or more" with the code `below-floor`; a mode below both floors
   shows the size reason; a camera whose open reports a size below the floor fails at the mode step; the
   text, place and gray style of the note; one copy of the rule in Python and one in the UI, each with
   its test. The next UI lane adds the note to the other three language files.
4. **Q901.** Push `dom/integration` (292529fa9) to the fork, with no PR. The supervisor did it.
5. **Q902.** A quick certify run leaves out the six full-only checks of Q593 (image-effect,
   not-reencoded, size, ring-equals-mkv, source-equals-ring, gaps-explained). The spec text and the test
   come first, in the next certify lane.

## Reason

- The user decided each item.
