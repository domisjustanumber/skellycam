# PA3A — Decision of the user on the test workflow on dom/integration

**Status:** accepted, 2026-11-26 (user; the coordinator asked the question and relayed the answer).

## Decision

The user decided this item on 2026-11-26. The coordinator asked: "Do you want me to add a push trigger for
`dom/integration` to `test.yml`, so the full suite and ruff run there?" The words of the user: "yes".

1. `.github/workflows/test.yml` runs on each push to `dom/integration`: ruff, the test suite of the package and
   the typecheck of the UI.

The choices of the agent that build this item are in [ADR-QF7V](QF7V-choices-of-the-test-workflow-on-dom-integration.md)
(proposed).

## Reason

1. `test.yml` ran only on a pull request to `main` or `development`. The fork has no such pull request, so no
   CI job ran ruff, the typecheck of the UI or the tests outside `skellycam/tests/capture`,
   `skellycam/tests/preview` and `skellycam/tests/take_recorder` on `dom/integration`.
2. Fix lane 8 broke `test_the_close_of_the_camera_processes_runs_off_the_event_loop` of
   `skellycam/tests/test_camera_startup_responsiveness.py`, and the Capture workflow of that push passed (run
   45711032368). Another session found the failure by hand.

## Open work

[open-work.md](../open-work.md)
