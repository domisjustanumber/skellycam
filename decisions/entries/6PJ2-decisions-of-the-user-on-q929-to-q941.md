# 6PJ2 — Decisions of the user on Q929 to Q941

**Status:** accepted, 2026-11-27 (user, Q929 to Q941; commit to dom/answers-q929).

## Decision

The user wrote on 2026-11-27: "Q930 explain this further, why is the move needed and what is the exception to the
rule for? / Q934 a second manual keyboard Ctrl C is generally an "abort now, something has gone wrong" case so the
primary goal is to get all processes to stop and release any holds and locks. Cleaning up the recording would be
nice, but is not expected. / Q936 - give me a full summary of any changes you've made to skellylogs, then I can open
the PR manually / Q946 - the player should remember the last folder it played from - what does
picked-take-folders.json do? / Otherwise agree to the rest of Q929-955 / This continues to be unattended until I say
otherwise. I'll do periodic check-ins". Each other answer accepts the recommendation of its question.
[ADR-318R](318R-decisions-of-the-user-on-q942-to-q955.md) holds Q942 to Q955.

1. **Q929, a standing rule** (also while the user is away, until he says otherwise). The supervisor merges a lane
   after a "safe to merge" review whose findings are fixed, with the full checks green on the merged branch. Then it
   pushes `dom/integration` to the fork (no PR, never a force-push), with no question each time.
2. **Q930: not decided.** The user asked why the move of T-PRV-25 is needed and what the exception to the rule is
   for (open work). Doc checks stays red until he decides.
3. **Q931.** The check "no camera ended" of the `[thread]` case of
   `test_the_watch_ends_no_healthy_camera_under_load` moves to a `pace` test; `[process]` stays blocking. Built:
   `test_no_camera_ends_under_load_with_thread_workers` (`windows-capture.md` 16.1). Whether `ready` and the pass
   count of `[thread]` move too is a question of [ADR-9GHT](9GHT-choices-of-the-answers-lane-of-q929-to-q955.md)
   (proposed).
4. **Q932.** A small lane makes `_same` of `test_certify_review.py` robust to the boot time that Linux reads again in
   whole seconds, low priority. Built here; the form is in ADR-9GHT (proposed).
5. **Q933.** [ADR-4W3H](4W3H-choices-of-the-q928-build.md) is accepted, also its rule that a disk call that hangs
   inside a take start or stop holds the exit with no time limit.
6. **Q934, his words above.** A second Ctrl-C means "abort now". The goal is that every process ends and every hold
   and lock is released. The end of the take is welcome, not required. So no lane builds "a second Ctrl-C stops the
   take"; the shutdown lane proves the goal with a test (open work).
7. **Q935.** One later lane, test first: tests of the requests other than a take start or stop that the 5 s limit
   cuts (an apply, a search); a record start during the background close of `/shutdown` gets 409, not 500.
8. **Q936.** The user opens the skellylogs PR himself, from the summary of the changes that the supervisor gives
   him. The supervisor pushes nothing to skellylogs.
9. **Q937.** [ADR-VTW3](VTW3-choices-of-the-quick-sync-check-in-a-child-process.md) is accepted.
10. **Q938.** A Quick Sync check child that answers "works" and then does not end counts as "does not work", with
    one WARNING line. Not built (open work); T-CAP-175 changes with it.
11. **Q939.** [ADR-KXQ9](KXQ9-choices-of-the-quick-run-without-the-six-full-checks.md) is accepted: no row at all
    for the six in quick; a fault inside one shows on the next visible check of the camera.
12. **Q940.** On the three conflicts of [ADR-8CP7](8CP7-certify-spec-draft-3-choices-of-the-agent.md) the later spec
    text wins: no Auto checks at 60 fps (Q617, `certify.md` 3.6.11), the raw device name in `nousb:` (`certify.md`
    2.5, Q627), a progress message before each check (`certify.md` 9.6). Then ADR-8CP7 is absorbed.
13. **Q941.** A later lane removes the wait of a quick run for the hash set of the first `ready` (`certify.md`
    3.6.1), after it measures that wait. Low priority.

## Reason

The words of the user, above.

## Open work

[open-work.md](../open-work.md)
