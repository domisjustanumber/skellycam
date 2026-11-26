# QF7V — Choices of the test workflow on dom/integration

**Status:** proposed, 2026-11-26 (agent; builds [ADR-PA3A](PA3A-decision-of-the-user-on-the-test-workflow-on-dom-integration.md); waits for the user).

## Decision

These are the choices of the agent in `.github/workflows/test.yml`.

1. **Skipped pushes.** A push that changes only files under `decisions/`, `specs/` or `skellycam-docs/` does not
   run the workflow (`paths-ignore`). The workflow also runs by hand (`workflow_dispatch`).
2. **No macOS job on a push.** On a push, the matrix holds `ubuntu-24.04` and `windows-2025`. A pull request
   and a run by hand also hold `macos-15`. This follows item 1 of
   [ADR-N14T](N14T-decisions-of-the-user-on-the-ci-review-of-2026-11-25.md).
3. **Runner labels.** `ubuntu-24.04`, `windows-2025` and `macos-15` replace the `-latest` labels, as in
   `capture.yml` and `recorder.yml`. The apt pin of PortAudio is for Ubuntu 24.04.
4. **PortAudio.** The Linux job installs `libportaudio2=19.6.0-1.2build3`, as `capture.yml` does. The conftest
   of the tests imports `sounddevice`, and its Linux wheel does not hold PortAudio.
5. **No `capture_local` tests.** Both pytest steps leave out the marker `capture_local`, as section 15 of
   [`windows-capture.md`](../../specs/windows-capture.md) states for the hosted runners. The conftest does
   not skip these tests.
6. **`fail-fast: false`.** A failure on one system does not cancel the job of the other system.
7. **A time limit of 60 minutes** for the job of the tests. The default limit is 6 hours, and a test that
   does not end (for example T-UNX-98 before fix lane 8) held the job until its limit.

## Reason

1. Item 1: most pushes of `dom/integration` change only the decision log and the specs.
2. Item 2: in 9 of 13 Capture runs, no hosted `macos-15` runner took the job.
3. Items 3 to 5: without them, the Linux job fails at the collection, and the `capture_local` tests fail on a
   hosted runner. The cause is the runner, not a fault of the product.
4. Items 6 and 7: a failed run shows the result of each system, and a hang ends in 60 minutes.

## Evidence

On `dom/fix-lane-9` (from e13105855), Windows: `uv run ruff check skellycam/` passed, and `npx tsc --noEmit` in
`skellycam-ui/` passed. On ea25cd717, Windows: the tests outside `skellycam/tests/capture`,
`skellycam/tests/preview` and `skellycam/tests/take_recorder` with `-m "not pace"`: 557 passed, 1 skipped.
Linux: not verified until the first run.

## Alternatives rejected

1. A push trigger only for the test folders that no other workflow runs: the steps of a pull request and of a
   push then differ.
2. A macOS job on each push: see item 2.

## Open work

[open-work.md](../open-work.md)
