# 318R — Decisions of the user on Q942 to Q955

**Status:** accepted, 2026-11-27 (user, Q942 to Q955; commit to dom/answers-q929).

## Decision

The words of the user are in [ADR-6PJ2](6PJ2-decisions-of-the-user-on-q929-to-q941.md): his own answers to Q930,
Q934, Q936 and Q946, and "Otherwise agree to the rest of Q929-955". Each answer here other than Q946 accepts the
recommendation of its question.

1. **Q942.** [ADR-SKZ8](SKZ8-choices-of-the-blocking-half-of-t-prv-17.md) is accepted: the loose limit of 10 s for
   "B continues" in the blocking half of T-PRV-17.
2. **Q943.** [ADR-W3VD](W3VD-choices-of-the-tile-timings-lane.md) is accepted: a camera that leaves keeps its
   timings slot (item 3); the group id is empty (`null`) in skellycam-ui (item 9). The 60 fps benchmark result of
   the tile timings lane is noise: no action.
3. **Q944.** [ADR-FP47](FP47-choices-of-the-triage-of-the-first-ci-run-of-the-4b-component-tests.md) is accepted:
   the test window fits the screen, and the test grid fits the window.
4. **Q945.** [ADR-WP77](WP77-choices-of-the-player-label-and-picked-folders-lane.md) is accepted, except what Q946
   leaves open: item 13 (the list file) and each sentence that says that a pick is never remembered across runs.
   That part moved to [ADR-K907](K907-the-open-part-of-adr-wp77-picks-across-runs.md) (proposed). Items 5 and 7 of
   [ADR-4PPS](4PPS-choices-of-the-answers-lane-of-q842-to-q856.md) stay proposed.
5. **Q946: not decided.** The user wrote: "the player should remember the last folder it played from - what does
   picked-take-folders.json do?" The follow-up questions are open work. No lane builds it.
6. **Q947.** [ADR-CM9S](CM9S-choices-of-the-clean-ups-lane.md) is accepted. The test ID T-UNX-109 is kept.
7. **Q948.** Only `es`, `zh-CN` and `ar` get the tracking note and the size error line now. The other 37 locale
   files fall back to English until there are native-speaker translations. A native speaker reviews the three
   before a release.
8. **Q949.** A camera loop keeps a failure that the stall watch already wrote: no overwrite. Test first, in a later
   small lane.
9. **Q950.** The two tests that raise on purpose inside a thread get a narrow mark
   `filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")`: on the test, or on its parameter.
   Built: `test_restore.py::test_an_end_by_another_base_exception_is_not_a_lost_heartbeat` and
   `test_worker_isolation.py::test_owner_failure_isolation[WorkerMode.THREAD-False]`.
10. **Q951.** A later docs lane fixes the front matter `description` of the streaming page and the feature text of
    `content.config` (`preview-4b.md` 5.9).
11. **Q952.** [ADR-C47T](C47T-choices-of-the-ci-lane.md) is accepted, also: `player-macos` runs only by hand on a
    push to `dom/integration`.
12. **Q953.** One later CI lane: it fixes the type error of `vite.config.ts` and adds its type check, adds the type
    check of the player, and gives the Linux player job a virtual screen of 1920 x 1080.
13. **Q954.** The UI lane of Q925 (a "saving" message after about 10 s) and Q927 ("port in use") starts, spec and
    tests first.
14. **Q955.** The "not to start" list of Q916 stays closed until the user has looked at this batch and tried the
    app by hand (also the tile resize of Q904). He says which item opens first.

## Reason

The words of the user, in ADR-6PJ2.

## Open work

[open-work.md](../open-work.md)
