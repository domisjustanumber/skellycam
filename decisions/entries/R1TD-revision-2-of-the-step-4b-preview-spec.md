# R1TD — Revision 2 of the step 4b preview spec: the review faults, and the choices it replaces

**Status:** superseded by [RA16](RA16-step-4b-choices-of-the-preview-ui.md), 2026-11-20 (commit to dom/integration; was accepted, 2026-11-20 (user, through the review sheets of 2026-11-20); was proposed, 2026-11-20 (agent)).

## Decision

Revision 2 of [`specs/preview-4b.md`](../../specs/preview-4b.md) applies the faults of an
independent review. An agent checked each fault against the code and accepted each one. This entry
replaces items 2, 8, 10, 11 and 18 of
[ADR-EE0E](EE0E-step-4b-preview-spec-and-agent-choices.md). Its other items stay.

Changes:

1. The grid gets its own list, `gridCameraIds`, from `cameras` of each group in `app_state`, with
   no filter on `alive`. On `dom/native-jpeg` one camera in `starting`, `failed` or `dead` makes the
   group not alive. `connectedCameraIds` keeps "the cameras that stream": the states with a preview.
   This replaces item 8 and is question Q7. New item 8: the automatic columns use `gridCameraIds`.
2. T-PRV-30 does not search the UI for `frameNumber`, because the parser field has that name. It
   searches the translated docs too.
3. The ring lock: the fault stays (the watch thread closes readers). The planned fix is on the
   capture branch (each close on the event loop), so section 5.1 of the 4a spec stays. The lock,
   with no rename, is only the fallback, and it now also covers `skipped_count` and the final loop
   over `ring_readers`. This replaces item 2. Q4 is rewritten.
4. A session fixture configures `skellylogs` (new item 19), and `ui_server.py` does too. The
   websocket tests fail today on `logger.success`.
5. T-PRV-29 part 1 checks that each reader close runs on the event-loop thread; part 2 (fallback
   only) uses a reader that yields inside `read` and records a close during a read.
6. B-1 splits into B-1a (outside captures, about 30 each second) and B-1b (ready messages and the
   draw count of the product, stated as a claim). This replaces item 10. Question Q9.
7. New pure module `preview/server-messages.ts`, so that T-PRV-40 runs under Node.
8. Section 5.6 lists each user of `connectedCameraIds`.
9. The merge order: `dom/native-jpeg` now (one conflict), `dom/player` before the first UI test
   (Q2). T-PRV-49 runs on Windows only. T-PRV-45 and T-PRV-46 are cut, with their two commands.
   T-PRV-44 uses the real group state through a second mode of `ui_server.py`. This replaces
   item 11.
10. Item 18 (English-only labels, English prose in the docs copies) is now question Q8.

The user answered the nine questions on 2026-11-20
([ADR-VYS7](VYS7-answers-of-the-user-to-the-step-4b-spec-and-go-ahead-for-its-tests.md)). Q4 is
settled by fix F8 of the capture branch, so the lock fallback of change 3 and part 2 of T-PRV-29
are removed. [ADR-W674](W674-choices-of-revision-3-of-the-step-4b-spec-and-its-test-list.md)
replaces changes 6 and 9 where they touch items 10 and 11.

## Reason

- Each fault was confirmed in the code of `dom/preview` and `dom/native-jpeg`.
- Items 8 and 18 change what the user sees, so they are questions, not choices.

## Open work

See [open-work.md](../open-work.md).
