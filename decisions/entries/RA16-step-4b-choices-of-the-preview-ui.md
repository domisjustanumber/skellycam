# RA16 — Step 4b choices of the preview UI: the three spec revisions, Q14 and the Displayed rate

**Status:** absorbed into
[`specs/camera-requests.md#81-the-rule`](../../specs/camera-requests.md#81-the-rule),
[`specs/preview-4b.md#2-the-base-branch-q2-s`](../../specs/preview-4b.md#2-the-base-branch-q2-s),
[`specs/preview-4b.md#43-the-ring-reader-close-on-the-event-loop-q4`](../../specs/preview-4b.md#43-the-ring-reader-close-on-the-event-loop-q4),
[`specs/preview-4b.md#56-the-grid-and-the-camera-list`](../../specs/preview-4b.md#56-the-grid-and-the-camera-list),
[`specs/preview-4b.md#63-targets-q6-q9-agent-10-agent-26`](../../specs/preview-4b.md#63-targets-q6-q9-agent-10-agent-26),
[`specs/preview-4b.md#77-what-t-prv-30-searches`](../../specs/preview-4b.md#77-what-t-prv-30-searches),
[`specs/preview-4b.md#11-choices-of-the-agent`](../../specs/preview-4b.md#11-choices-of-the-agent),
[`specs/preview-4b.md#121-the-answers-of-the-user`](../../specs/preview-4b.md#121-the-answers-of-the-user),
2026-11-25 (commit to dom/log-cleanup; was accepted, 2026-11-20 (user: two rulings on review sheet 2 of 2026-11-20; the other items
accepted through the review sheets of 2026-11-20; commit to dom/integration)).

## Decision

This entry supersedes [ADR-EE0E](EE0E-step-4b-preview-spec-and-agent-choices.md),
[ADR-R1TD](R1TD-revision-2-of-the-step-4b-preview-spec.md) and
[ADR-W674](W674-choices-of-revision-3-of-the-step-4b-spec-and-its-test-list.md). Each of their items
is below. P is [`preview-4b.md`](../../specs/preview-4b.md), and "item n" is an item of its section
[11](../../specs/preview-4b.md#11-choices-of-the-agent).

Ruled by the user:

- W674 Q14 (P [12.3](../../specs/preview-4b.md#123-new-question)): yes. The take uses the camera
  list number of the apply request, for the order only.
  [`camera-requests.md` 8.1](../../specs/camera-requests.md#81-the-rule) states it.
- W674 3: yes. The Displayed rate is the time between drawn frames, and a time longer than 1 s is not
  added to the statistics (item 22).

Accepted through the review sheets, by a link to the heading that states it:

- EE0E 1, 3, 4, 5, 7, 9, 12, 13, 14, 15, 16: items 1, 3, 4, 5, 7, 9, 12, 13, 14, 15, 16.
- EE0E 6: item 6 (`frameDigits` 6). EE0E 18, R1TD 10 (English only, Q8), R1TD 6 (Q9), R1TD 9 (Q2):
  the answers in P [12.1](../../specs/preview-4b.md#121-the-answers-of-the-user), with P
  [2](../../specs/preview-4b.md#2-the-base-branch-q2-s) and
  [6.3](../../specs/preview-4b.md#63-targets-q6-q9-agent-10-agent-26).
- R1TD 1 (Q7), R1TD 8: item 8 and P
  [5.6](../../specs/preview-4b.md#56-the-grid-and-the-camera-list).
- R1TD 2: P [7.7](../../specs/preview-4b.md#77-what-t-prv-30-searches). R1TD 4: item 19. R1TD 5:
  item 29 and P [4.3](../../specs/preview-4b.md#43-the-ring-reader-close-on-the-event-loop-q4) (part
  1 of T-PRV-29 only). R1TD 7: item 3 (`preview/server-messages.ts`).
- W674 1, 2, 4 to 12: items 20, 21 and 23 to 31 (W674 n is item 19 + n).

Overturned: the label text of EE0E 6 (the frame number with no time part as the label). Q5 of
[ADR-VYS7](VYS7-answers-of-the-user-to-the-step-4b-spec-and-go-ahead-for-its-tests.md) makes the
label `Camera <n> · <name>` (item 20).

Dropped as stale:

- EE0E 2 and R1TD 3: the public `ring_lock` and its fallback. Fix F8 settled Q4 (P 4.3), so no lock
  is in the sender.
- EE0E 8: `connectedCameraIds` for the grid. R1TD 1 and Q7 replace it.
- EE0E 10, 11, 17: the targets B-1 to B-4, the old fixture and test plan, and one table row for each
  camera. Revision 3 replaces them (items 24, 26 to 28).

## Reason

The rulings of the user on the review sheets. Each old entry keeps the reasons of its items. The
Rules allow no partial supersession, so this entry places each old item.

## Open work

See [open-work.md](../open-work.md).
