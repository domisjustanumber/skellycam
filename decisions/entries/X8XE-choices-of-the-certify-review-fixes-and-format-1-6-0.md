# X8XE — Choices of the certify review fixes and format 1.6.0

**Status:** proposed, 2026-11-21 (agent; the user approved the review fixes and the move to format 1.6.0).

## Decision

The code of [ADR-VG5F](VG5F-choices-of-the-first-certify-code.md) gets the fixes of an independent review and
format 1.6.0 of the contract (skellycertify ADR-9FHP). [`certify.md`](../../specs/certify.md) states them in 0, 1,
4.1, 4.5, 8.3, 9.3 and 9.5. The agent made these choices:

1. The record row of a model comes from the summary item of that model, never from its name.
2. A wedge code (`hung`, `process-ended`, `device-removed`) after any step makes the running check `fail` (`hung`,
   `crashed` or `device-removed`), each later check of that camera `prior-failure`, and `camera-wedged`.
   `gate:no-hang` counts only `fail` rows.
3. The session sends the "before" values as soon as the diagnostics hold them. Phase G never opens a wedged
   camera or a camera with no `opens` result; the second one is `camera-not-restored`. A camera with no known
   "before" values gets no open.
4. A camera whose loop failed after its controls were set is `camera-not-restored`, because the product does not
   restore it (`camera_loop.py`, `close(restore=not self.failed ...)`).
5. The session child keeps its parent handle before it clears the mark. A thread waits on the caller; at its death
   it sets the kill flag, closes the group within 15 s and ends. The wait for an answer has a limit of 1 s in a loop.
   The caller stops the child in a `finally`, also after a `BaseException` from the progress callable.
6. A time-out ends the main process of the child, waits up to 12 s, then kills the rest. A cancel, an abandon and
   the end of the budget kill the tree. After a crash, the caller waits up to 12 s for the camera processes that it
   saw.
7. At a stop, the events already in the queue keep their results.
8. After a crash or a time-out, a running check is `fail` only when the checks that ran belong to one camera; else
   each is `not-run` with the cause. A refused apply gives `opens` `not-run` with the class name. A crash, a
   time-out or an abandon writes no record row.
9. `certify.lock` beside the record holds one run at a time. A second run is refused with `cameras-busy` and makes
   no work folder. A failed record write gives the cleanup row `write-record`.
10. The budget of quick starts at the call and holds the detection. The bound is in 9.3.
11. `gaps-explained` passes when the gaps are not more than the replaced frames of a window from before the record
    start to after the stop. Only the mode check of `<base>` counts for the item and `gate:mode`.
12. Format 1.6.0: the schema id `skellycertify.report/1.6.0`; `abandon` stops as a cancel (`cancelled`) and writes
    no record row; no `test_media` and no `gpus`; `session:exit` has no `module`. The local contract clone is at
    1.7.0, which changes only the `name` of a `test_media` item; skellycam writes 1.6.0 as the user decided.
13. Second review: the live change skips a wedged or not-ready camera. After the session starts its close, the
    caller kills nothing before 5 s + 8 s for each camera. A clean close means no reopen in phase G. A crash never
    blames a camera. A late abandon stops the record write. Camera logs go to `logs` of the work folder.
14. Proposal (the coordinator chose it, the user has not): a camera with a step running at a stop is not opened
    again and gets `camera-not-restored`, because the product needs 5 s to declare a hang. Cost: no restore after a
    cancel during the take.

## Open work

Not built: a check for a camera group that another process holds (review finding 11). A sound way is that the
app takes `certify.lock` while it has a camera group open; that is a change of `camera_group_manager.py`, which
another job changes now.

## Questions for the user

Each "yes" accepts the recommendation.

1. Spec 9.1 says that a model in the record gives a quick `total` of 0; 2.4 and C 2.7 say that a quick run with no
   `cameras` option checks it again. Keep 2.4: the app uses `details.unchecked` for the pop-up. Yes?
2. With no camera to check, the quick plan has `total` 0, but the run still reports `detect` (T-CERT-06 against
   T-CERT-01 and 66). Accept that difference of one in this case. Yes?
3. A quick run of three cameras sends 63 progress messages; the gap of 100 ms costs about 6 s of the 30 s.
   Let the checks that only compute from data that the run has (JPEG, records, clock) share one message. Yes?
4. In quick, phase G opens a camera whose loop failed (not wedged) and sets its "before" values back, in place of
   only the notice. Yes?
5. Product change, not built: `managed_worker` sets an explicit role flag in each camera process, the
   `parent_process()` guards read it, and certify drops its workaround of item 5. Yes?
6. Accept item 14. Yes?

## Reason

Each fix follows a decision of the user or a rule of the spec or the contract, with the smallest change and no
change of product code.

## Alternatives rejected

- `gaps` equal to the replaced count: the window of the count cannot match the rows, so a good camera can fail.
- A missing `restore_ok` as proof of no restore: the close dict of a good camera can come after the close returns.
