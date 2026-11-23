# 0Z6Q — Choices of the build of the certify report shape

**Status:** proposed, 2026-11-23 (agent; the build steps of [`certify.md`](../../specs/certify.md) 3.6.7).

## Decision

The code builds the steps of 3.6.7 of [`certify.md`](../../specs/certify.md) in their order. The spec does not
make these choices. The agent made them. "Not:" gives the rejected alternative.

1. B1 (3.6.1) applies only to a live camera: a camera whose open passed and that was `ready`. A failure in the
   open stays on `<label>:opens`. A code that is not a wedge code needs the state `failed` or `dead`. Not: each
   product code of each camera (a failed open would then get two rows).
2. The checks of the open (`opens`, `rate`, `modes:granted:<base>`) are never a B1 row: the open judged them.
3. A live camera that is gone at the scan before the record start gets its B1 row on its first check with no
   result in the order of the plan, for example `native-jpeg:valid`. Only a camera that leaves in the take or after
   it gets `records:rows-complete`. Not: `records:rows-complete` also before the record start.
4. After a B1 row, the later checks of the camera are `prior-failure` for a wedge code (2.3) and
   `prior-check-failed` for another code (`stalled`, `stream-error`), as before. Not: `prior-failure` for each code.
5. A B1 row has the failure facts of 3.5.3 that the run has today: `stage`, `call`, `native_code` with
   `native_domain`, `first_fail_code` when a source gives it, and `exit_code` from the failure of the status
   (`exit code <n>`). Thus `exit_code` 3 of T-CERT-93 is in the row now, before P4. Not: `exit_code` only after P4.
6. P7: `tools/build_info.py` is the `build_py` command of setuptools (`[tool.setuptools.cmdclass]` of
   `pyproject.toml`). It writes the build file into the build folder of the wheel. An editable install, and a build
   with no git answer (for example a wheel built from an sdist), write no file. Not: a `setup.py`; not: a file in the
   source tree.
7. The fake source gets `on_arm` and `FakeLog.arm()`: a stall, an exit or a removal comes at the next frame after a
   progress message. Not: a frame number (the real clock of a session child moves the step of a frame).
8. T-CERT-93 puts the stream error and the removal in the take, not "before the take": no progress message comes
   between the settings change and the take.
9. `details.not_built.run` holds `group:open` and the two `self:hang-100ms` checks only when the run checks a
   camera, as the plan did before. `details.not_built.camera` is the union of the names of the units; a unit with
   no `<base>` adds no name with `base`. A refused run also has `details.not_built`. Not: the lists of the level
   with no regard to the cameras.
10. `total` counts `session:exit` only when the run has a camera to check, because only then a session child runs.
    With no camera, `total` of `full` is 1 (`detect`) and of `quick` 0, as before. The progress counts the end of
    the session child at the end of the run, also after a refused run or a stop before the session, so the last
    `done` equals `total`. Not: one more check in each plan.
11. `<label>:not-reached` stands for the checks at the end of the camera, in the order of the plan, that are
    `not-run` with a reason of a camera that cannot go on (the list of 3.6.1) and that no progress message named. A
    `not-run` row before a check with a result (for example `no-manual-exposure`, or `holds` after a failed
    `readback`) keeps its own row. Not: each such row of the camera wherever it stands.
12. A unit with a `not-reached` row makes its item `partial` when no `fail` rule applies. A gate step whose required
    check is in the `not-reached` row requires that row, so the gate is `not-run`. The local record (2.5) reads a
    settings check in the `not-reached` row as `not-run` with the reason of that row, so the row has no `controls`.
    Not: no part in the item and the gate (an item would then pass with checks that did not run).

## Reason

1. A camera that fails in the open has its cause on `opens` already.
2. The rate row of a live camera comes after the open only because it adds the light and the JPEG size.
3. The text of 3.6.1 says "in the take and after it"; a camera that is gone before the record start is not in the
   take.
4. The wedge rule of 2.3 names only a hang, a crash and a removal.
5. The status failure of a camera process that ended holds its exit code.
6. A `build_py` command runs in each wheel build and has the build folder.
7. A progress message is the only point that a test can name in a session child.
9. The plan has planned these checks only with a camera to check.
10. The rule "with no camera to check, the run also reports `detect`" of 9.1 stays.
11. Only the end of the checks of a camera shows that it could not go on; a check in the middle can be `not-run`
    for its own reason.
12. Before, these checks were `not-run` rows of the groups, and the item and the gate read them.

## Alternatives rejected

The "Not:" parts of the items.
