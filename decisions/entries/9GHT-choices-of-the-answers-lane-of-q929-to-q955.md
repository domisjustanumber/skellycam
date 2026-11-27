# 9GHT — Choices of the answers lane of Q929 to Q955

**Status:** proposed, 2026-11-27 (agent, answers lane on `dom/answers-q929`; waits for the user).

## Decision

The user decided Q929 to Q955 ([ADR-6PJ2](6PJ2-decisions-of-the-user-on-q929-to-q941.md),
[ADR-318R](318R-decisions-of-the-user-on-q942-to-q955.md)). These details his answers did not settle.

1. **Q931: may more move with "no camera ended"?** The `[thread]` case checks three things: no camera ended, both
   cameras `ready` at the end, and more than 30 loop passes in the 12 s. As built, only "no camera ended" is the
   `pace` test `test_no_camera_ends_under_load_with_thread_workers` (the words of Q931). The blocking `[thread]` case
   keeps `ready` and more than 30 passes for each camera that did not end, and that each loop passed under the load
   (at least one pass). Both run on one run (`one_run`). But a camera that ends from a starved GIL also is not
   `ready` and makes fewer passes, and a starved loop that does not end can still make 30 passes or fewer: those two
   checks can fail from the same cause. Question: may `ready` and the pass count of `[thread]` move to the `pace`
   test too, with the blocking check of at least one pass? Yes accepts it.
2. **Q932: the form of `_same`.** The same pid and a create time within 1.5 s. On Linux `create_time()` is the
   start time since boot plus the boot time of `/proc/stat` in whole seconds, read again at each call, so a tick of
   it moves the value by exactly 1 s. psutil 7.2.2 (the lock file) has no public monotonic create time: only the
   private `Process._proc.create_time(monotonic=True)`, which psutil itself uses for `Process.__eq__`. The test does
   not use a private API. A clock step of more than 1.5 s between the two reads still hides a live process (a
   `shortcut:` comment says so). A new unit test checks the helper. Question: is a tolerance of 1.5 s, with no
   private psutil API, enough? Yes accepts it.
3. **Q945: the split of ADR-WP77.** The sentences that say that a pick is never remembered across runs are: the
   end of a pick with the main process (item 8), the old `picked-take-folders.json` that is not read and not deleted
   (item 8), the form of the "no list file" check of T-PLAY-62 and the picked-folders file that the harness lost
   (item 12), and item 13. They moved to [ADR-K907](K907-the-open-part-of-adr-wp77-picks-across-runs.md). The rest
   of item 8 (a reload or a closed window does not end a pick) and of item 12 (the user data folder of the harness)
   stay in ADR-WP77. Question: is this the part that waits for Q946? Yes accepts it.
4. **Facts that are not rules.** Item 16 of [ADR-VTW3](VTW3-choices-of-the-quick-sync-check-in-a-child-process.md)
   (no second entry for Q879) and item 5 of [ADR-KXQ9](KXQ9-choices-of-the-quick-run-without-the-six-full-checks.md)
   (8CP7 not absorbed, now decided by Q940) are facts of the log, with no rule that stays. The lane absorbed both
   entries with them. Question: may such log facts stay out of the specs? Yes accepts it.

## Reason

1. Q931 moves the check that fails from the test mode, not from the product. A check that fails from the same cause
   can keep a CI failure; the user decides whether it moves. A loop that makes no pass at all in 12 s is a real fault,
   and its check does not depend on the pace.
2. A tolerance is one line; a private API can change in any psutil release.
3. Q945 names item 13 and "any item that says picks are never remembered across runs"; the lane took each sentence
   that holds a pick or the list file to one run.
4. The specs state rules of the product and of its tests, not the history of the log.

## Open work

[open-work.md](../open-work.md)
