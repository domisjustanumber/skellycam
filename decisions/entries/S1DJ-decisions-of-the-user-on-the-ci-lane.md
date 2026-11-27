# S1DJ — Decisions of the user on the CI lane: Q854, Q897 and Q915 item 4

**Status:** absorbed into [`specs/frame-ring.md#14-accepted-decisions`](../../specs/frame-ring.md#14-accepted-decisions),
[`specs/player.md#126-ci-agent-35`](../../specs/player.md#126-ci-agent-35),
[`tools/tests/test_workflows.py`](../../tools/tests/test_workflows.py), 2026-11-27 (commit to dom/ci-lane; was
accepted, 2026-11-27 (user, Q854, Q897 and Q915; the supervisor relayed the answers)).

## Decision

The user answered "agree to Q842-855" on 2026-11-26 (Q854), "agree to all Q893-Q902" on 2026-11-26 (Q897) and
"agree to all" on 2026-11-27 (Q910 to Q921). Supersedes
[ADR-7DE6](7DE6-arm64-ci-job-for-the-portable-frame-ring-tests.md).

1. **Q854** ([ADR-88HQ](88HQ-decisions-of-the-user-on-q842-to-q856.md) item 13). The uv version is the version of
   the workflows: `0.13.7`. ADR-7DE6 said `0.13.9`, so this entry supersedes it. Each `astral-sh/setup-uv` step of
   each workflow pins one version, and the specs and the Active entries name no other.
2. **Q897** ([ADR-BPP8](BPP8-answers-of-the-user-q864-to-q873-on-the-step-4b-code.md) item 16). CI gets a second
   type check that covers the test code of the UI.
3. **Q915 item 4.** The CI lane makes `player.yml` and `ring-arm64.yml` run on the pushes to `dom/integration`, and
   removes `.github/workflows/debug-azure.yml`.
4. **The kept rules of ADR-7DE6.** Item 68 of
   [`specs/frame-ring.md` section 14](../../specs/frame-ring.md#14-accepted-decisions) states the job
   `ring-portable`: its runner, its triggers, its set-up, its test steps, its time limit and its permission. The
   changed rules: uv `0.13.7` (item 1), and the push to `dom/integration` (item 3).

The form of each item (file names, steps, the one source of the uv version) is in
[ADR-C47T](C47T-choices-of-the-ci-lane.md) (proposed).

## Reason

The words of the user, above. Before this entry, `tsc --noEmit` in `skellycam-ui` left out the four test folders
that the root `tsconfig.json` excludes, so no CI job checked the types of the UI tests. The pushes to
`dom/integration` ran `test.yml`, `capture.yml` and `recorder.yml`, but not the player and arm64 ring tests.
`debug-azure.yml` was a by-hand debug run that echoed the signing secrets, and no file referred to it.

## Open work

[open-work.md](../open-work.md)
