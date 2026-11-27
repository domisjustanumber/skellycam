# 7DE6 — CI job that runs the portable frame ring tests on an arm64 Linux runner

**Status:** superseded by [S1DJ](S1DJ-decisions-of-the-user-on-the-ci-lane.md), 2026-11-27 (commit to
dom/ci-lane; was accepted, 2026-11-19 (user; commit to dom/native-jpeg)).

## Decision

Add the workflow `.github/workflows/ring-arm64.yml`. It has one job, `ring-portable`, on the runner
`ubuntu-24.04-arm`. The job runs on each push to `dom/native-jpeg` that changes the ring package,
the ring tests, `specs/frame-ring.md`, `pyproject.toml`, `uv.lock` or the workflow file. It also
runs by hand (`workflow_dispatch`). There is no `pull_request` trigger.

The job installs uv 0.13.9, Python 3.13.18 and the `dev` group as `test.yml` does. It then runs
`uv run pytest skellycam/tests/frame_ring -m ring_portable -q` with `SKELLYCAM_RING_FULL=1`. The
timeout is 20 minutes, and the permission is `contents: read`. This applies items 51 and 67 of
[`specs/frame-ring.md`](../../specs/frame-ring.md) to T-RING-35 and T-RING-48 (item 68).

## Reason

The ring has no locks. An x86 processor keeps the order of stores. An ARM processor does not. Only
an ARM run checks that the copy-then-CRC reads do not depend on that order. The user wants step 2b
and phase 3 built on a ring that is checked on ARM at each push.

## Consequences

- The job does not replace the Apple Silicon run (T-RING-34). That run is on hold for the certify
  suite (item 67).
- The job does not solve the open-work item about CI on PRs to `development-streaming`.
- The job has not run yet. It is not verified that the `ubuntu-24.04-arm` runner is free for this
  fork.

## Open work

See [open-work.md](../open-work.md).
