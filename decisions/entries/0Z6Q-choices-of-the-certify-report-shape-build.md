# 0Z6Q — Choices of the build of the certify report shape

**Status:** proposed, 2026-11-23 (agent; the build steps of [`certify.md`](../../specs/certify.md) 3.6.7).

## Decision

The code builds the steps of 3.6.7 in their order. The agent made these choices. "Not:" gives the rejected
alternative.

1. B1 (3.6.1) applies only to a live camera (its open passed). A code that is not a wedge code needs the state
   `failed` or `dead`. Not: each camera (a failed open would get two rows).
2. The checks of the open are never a B1 row: the open judged them.
3. A live camera that is gone before the record start gets its B1 row on its first check with no result, for
   example `native-jpeg:valid`. Not: `records:rows-complete`.
4. After a B1 row, the later checks are `prior-failure` for a wedge code (2.3), else `prior-check-failed`.
5. A B1 row has the failure facts that the run has: `stage`, `call`, `native_code` with `native_domain`,
   `first_fail_code`, and `exit_code` from the status failure (`exit code <n>`), so before P4. Not: wait for P4.
6. P7: `tools/build_info.py` gives the `build_py` and `sdist` commands of setuptools (`pyproject.toml`). `build_py`
   writes the file into the wheel from git, else it copies a valid file of the source tree (an sdist). `sdist` writes
   it into the sdist. `python tools/build_info.py --require` writes it into the source tree for the installer build
   of CI and fails with no commit. An editable install writes none. Not: a `setup.py`.
7. The fake source gets `on_arm` and `FakeLog.arm()`: the event comes at the next frame after a progress message.
   Not: a frame number (the real clock of a session child moves it).
8. T-CERT-93 puts the stream error and the removal in the take; no progress message comes before it.
9. `details.not_built.run` holds `group:open` and `self:hang-100ms:*` only with a camera to check; `camera` is the
   union of the units. Not: the lists of the level only.
10. `total` counts `session:exit` only with a camera to check. The progress counts the end of the session at the
    end of each run, so the last `done` equals `total`. Not: one more check in each plan.
11. `<label>:not-reached` stands for each filled row of the camera (the caller wrote it; no step gave it) with a
    reason of 3.6.1 that no progress message named, wherever it stands, at the place of its first check. A row of
    the session (`no-manual-exposure`, `holds` after a failed `readback`) stays. A camera with no MJPG mode gets no
    `opens` row from the session: its checks are filled with `no-mjpg-mode`. Not: only the rows at the end (a B1 row
    in the take then left three filled rows before it).
12. A `not-reached` row makes the item `partial` when no `fail` rule applies, and a gate step whose check it holds
    `not-run`. The local record reads a settings check in it as `not-run`. Not: ignore it.
13. A check counts as named when the run announced it, also with no progress callable or after it raised. Not:
    only a message that the callable got (the report would depend on the callable).
14. A B1 row of a code that is not a wedge code also marks the camera as failed. A `stalled` camera then gets the
    cleanup row and the notice `camera-not-restored`, also after a stall in the take (the product does not restore
    after a wedge code, Z7F3). Not: no cleanup row for a stall in the take.
15. Q646 ([ADR-056Z](056Z-decisions-of-the-user-on-a-late-camera-failure-the-release-build-file-and-the-open-rows.md)):
    the fail row of a camera that leaves after its take checks is `<label>:live-at-close`, a planned check, the last
    of the camera: `pass` with no product failure code from the end of its take checks to the end of the close,
    else `fail` with the code and its facts. It is in the Open group of the item and in the gate step `records`.
    Not: a second result of a written row (one test, one check, contract 3.4); not: a cleanup row (contract 3.1:
    a failed cleanup step); not: a row that the plan does not count (`done` above `total`).
16. The build file has a commit only when `git rev-parse --show-toplevel` is the source root. An error of git, also
    a text that does not decode, gives no commit and never fails the build. Not: the commit of a parent repository.

## Reason

The spec does not give these details. Each choice keeps the rules of 3.6.1 and of the contract, and each one has
a test in `skellycam/tests/certify/` or `tools/tests/`. Items 11 and 15 follow the review of 2026-11-23 (a B1 row
in the take left filled rows; a camera that died after its take checks gave no row). Item 16 follows a build of
an sdist inside another repository, which gave the commit of that repository.

## Alternatives rejected

The "Not:" parts of the items.
