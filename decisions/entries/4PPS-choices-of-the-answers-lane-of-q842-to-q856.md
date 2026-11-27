# 4PPS — Choices of the agent that applies the answers Q842 to Q856

**Status:** proposed, 2026-11-26 (agent; applies Q850 to Q852 of
[ADR-88HQ](88HQ-decisions-of-the-user-on-q842-to-q856.md) and Q863 of
[ADR-3RJJ](3RJJ-decision-of-the-user-on-the-order-of-the-two-stall-rules.md); commit to dom/answers-q842).

## Decision

The user did not decide these details.

1. Accepted by Q919 and moved to [ADR-70J6](70J6-decisions-of-the-user-on-the-remaining-items-of-4pps.md) item 1.
2. Accepted by Q919 and moved to [ADR-70J6](70J6-decisions-of-the-user-on-the-remaining-items-of-4pps.md) item 2.
3. Accepted by Q874 and moved to [ADR-EQ3K](EQ3K-decisions-of-the-user-on-the-head-start-of-the-stall-watch.md) item 3.
4. Accepted by Q874 and moved to [ADR-EQ3K](EQ3K-decisions-of-the-user-on-the-head-start-of-the-stall-watch.md) item 4.
5. **The sentences of Q852.** `windows-capture.md` 15 says that the workflow does not raise the open-file limit
   of its runner (N14T item 2). `windows-capture.md` 16.1 says that T-CAP-91 stays a blocking test with no change (R394 item 3,
   N14T item 3), that the clock rule replaces the words of item 8 of ADR-B7YV (2SX2 item 1), and that the blocking
   half of the test under load keeps both cameras `ready` (2AQT). `unix-capture.md` 7 says that each new dependency
   must be justified (item 11 of ADR-22EJ).
6. Accepted by Q919 and moved to [ADR-70J6](70J6-decisions-of-the-user-on-the-remaining-items-of-4pps.md) item 3.
7. **The time of the control-read check.** `certify.md` 16 says that its sums and run times leave out the 60 s for
   each model of `<label>:control-read:gaps`; the sums are not recomputed.
8. Accepted by Q919 and moved to [ADR-70J6](70J6-decisions-of-the-user-on-the-remaining-items-of-4pps.md) item 4.
9. Accepted by Q874 and moved to [ADR-EQ3K](EQ3K-decisions-of-the-user-on-the-head-start-of-the-stall-watch.md) item 5.
10. Accepted by Q891 and moved to [ADR-N2VE](N2VE-decisions-of-the-user-on-the-ci-triage-and-the-stall-watch-code.md) item 5.
11. Accepted by Q891 and moved to [ADR-N2VE](N2VE-decisions-of-the-user-on-the-ci-triage-and-the-stall-watch-code.md) item 5.
12. Accepted by Q891 and moved to [ADR-N2VE](N2VE-decisions-of-the-user-on-the-ci-triage-and-the-stall-watch-code.md) item 5.

## Reason

1. See [ADR-70J6](70J6-decisions-of-the-user-on-the-remaining-items-of-4pps.md).
2. See [ADR-70J6](70J6-decisions-of-the-user-on-the-remaining-items-of-4pps.md).
3. See [ADR-EQ3K](EQ3K-decisions-of-the-user-on-the-head-start-of-the-stall-watch.md).
4. See [ADR-EQ3K](EQ3K-decisions-of-the-user-on-the-head-start-of-the-stall-watch.md).
5. Each sentence states a rule of an accepted entry that no spec stated, so that the entry can be absorbed.
6. See [ADR-70J6](70J6-decisions-of-the-user-on-the-remaining-items-of-4pps.md).
7. The new sums would change the run times that the user accepted; that is a question for the user.
8. See [ADR-70J6](70J6-decisions-of-the-user-on-the-remaining-items-of-4pps.md).
9. See [ADR-EQ3K](EQ3K-decisions-of-the-user-on-the-head-start-of-the-stall-watch.md).
10. See [ADR-N2VE](N2VE-decisions-of-the-user-on-the-ci-triage-and-the-stall-watch-code.md).
11. See [ADR-N2VE](N2VE-decisions-of-the-user-on-the-ci-triage-and-the-stall-watch-code.md).
12. See [ADR-N2VE](N2VE-decisions-of-the-user-on-the-ci-triage-and-the-stall-watch-code.md).

## Open work

[open-work.md](../open-work.md)
