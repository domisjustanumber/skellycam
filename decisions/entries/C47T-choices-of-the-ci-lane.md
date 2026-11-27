# C47T — Choices of the CI lane

**Status:** accepted, 2026-11-27 (user, Q952 of [ADR-318R](318R-decisions-of-the-user-on-q942-to-q955.md); commit to dom/answers-q929; was proposed, 2026-11-27 (agent, CI lane; waits for the user)).

## Decision

The choices of the lane that builds [ADR-S1DJ](S1DJ-decisions-of-the-user-on-the-ci-lane.md) and the D: drive try
of Q922 ([ADR-D2YZ](D2YZ-decisions-of-the-user-on-t-rec-36-t-prv-17-and-the-slow-holder-reading.md) item 1). The
user did not decide them.

1. **One source of the uv version.** The source is the `version:` of the setup-uv step of `doc-checks.yml`. That
   file is kit text, and its comment says "The same uv in each repo". `tools/tests/test_workflows.py` checks that
   each setup-uv step of each workflow has a `version:` equal to it, and that the specs and the Active entries
   name no other `uv X.Y.Z`. A change of the uv version thus starts in the kit.
2. **The test file.** `tools/tests/test_workflows.py` is local, not kit text. It also checks the push trigger of
   `dom/integration` in the five workflows, and the type check of the UI test code (item 3).
3. **The type check of the UI test code.** A new file `skellycam-ui/tsconfig.tests.json` extends the root
   `tsconfig.json`, includes `src`, `e2e`, `playwright*.config.ts` and `vite.player-harness.config.ts`, and excludes
   nothing. The job `frontend-typecheck` of `test.yml` gets a second step, "Typecheck the test code",
   `npx tsc -p tsconfig.tests.json --noEmit`. The step runs also when the first type check fails, when
   `npm ci` passed. The root `tsconfig.json` and its excludes do not change. `vite.config.ts` stays out: it is the
   file of `tsconfig.node.json`, not test code, and it has a type error of its own today.
4. **The one type error that the new check found.** `server-messages.test.ts` line 69: `o.label` "is possibly
   'null'". The fix is a non-null assertion, `o.label!.includes(other)`. It changes only the type: a null label
   still throws, and the test still fails.
5. **`player.yml`.** Its push branches get `dom/integration`. Its push and pull-request paths both get four paths of
   `preview-4b.md` 7.8; the fifth, `skellycam-ui/src/store/slices/cameras/**`, is already in
   `skellycam-ui/src/store/slices/**`. Each of its three jobs gets the steps of `capture.yml` before `npm ci`: setup-uv
   (the same SHA and uv), `uv python install 3.13.18`, PortAudio on Linux, and `uv sync --group dev --python
   3.13.18`. The preview component tests start `uv run python -m skellycam.tests.preview.ui_server`. On a push to
   `dom/integration`, the job `player-macos` runs only by hand:
   `if: github.event_name == 'workflow_dispatch' || github.ref != 'refs/heads/dom/integration'`. On each other
   branch and event, it runs as before. Q952 of [ADR-318R](318R-decisions-of-the-user-on-q942-to-q955.md) accepts it.
6. **`ring-arm64.yml`.** Its push branches are `[dom/native-jpeg, dom/integration]`, as `capture.yml`. Its paths do
   not change. It gets no `pull_request` trigger.
7. **The D: drive in `recorder-windows`.** A step "Put the temp folder on the D drive" runs before the test
   steps. When `D:\` exists, it makes `D:\tmp` and writes `TEMP` and `TMP` to `GITHUB_ENV`. When `D:\` is missing,
   or the folder cannot be made, it prints a line and the default stays. The Linux and macOS jobs do not change.
   It has not run on a runner.

## Reason

1. One source in the kit keeps the uv of each repo the same, and a test makes a second version fail at once.
2. A file of its own needs no kit proposal.
3. A second config leaves the product check as it is, and checks every TypeScript file of the UI tests.
4. A non-null assertion is a change of the type only. `?? ''` would let a null label pass.
5. Without uv, the preview component tests in `player.yml` cannot start their server. On `dom/integration`, the
   hosted `macos-15` runner often did not take a job ("The job was not acquired by Runner of type hosted",
   [ADR-N14T](N14T-decisions-of-the-user-on-the-ci-review-of-2026-11-25.md)), so `capture-macos` and
   `recorder-macos` run only by hand there. `player-macos` would make Player red with no real fault.
7. Python and pytest take the temp folder from `TEMP` on Windows. A guard keeps the job as it was on a runner with
   no D: drive.

## Alternatives rejected

- A separate job for the second type check: it would run `npm ci` a second time.
- Removing the excludes of the root `tsconfig.json`: the product build (`npm run build` runs `tsc`) would then
  depend on the test code.
- `player-macos` on every push, also to `dom/integration`: the runner faults of N14T would make Player red with no
  real fault. N14T kept `player.yml` as it is for its old branches, and they keep it.

## Open work

[open-work.md](../open-work.md)
