# N14T — Decisions of the user on the CI review of 2026-11-25

**Status:** absorbed into [`specs/windows-capture.md#15-ci-d47`](../../specs/windows-capture.md#15-ci-d47),
[`specs/windows-capture.md#161-kinds`](../../specs/windows-capture.md#161-kinds),
[`specs/recorder.md#121-kinds-markers-workflow-and-parity`](../../specs/recorder.md#121-kinds-markers-workflow-and-parity),
2026-11-26 (commit to dom/answers-q842; was accepted, 2026-11-25 (user; the coordinator gave the three recommendations and relayed the answer)).

## Decision

The user reviewed CI on 2026-11-25 and accepted three recommendations. The words of the user: "ok, make the
relevant changes".

1. **The macOS jobs run only by hand.** The job `capture-macos` of `.github/workflows/capture.yml` and the job
   `recorder-macos` of `.github/workflows/recorder.yml` run only on `workflow_dispatch`, with the job-level
   condition `if: github.event_name == 'workflow_dispatch'`. `player.yml` does not change.
   [`windows-capture.md`](../../specs/windows-capture.md) section 15 and [`recorder.md`](../../specs/recorder.md)
   12.1 state it.
2. **"Too many open files" on macOS.** An agent finds if the error comes from a leak of open files. The workflow
   does not raise the limit of open files.
3. **T-CAP-91 on Linux CI.** An agent finds the cause of the failure of
   `test_t_cap_91_rate_class_30` on `ubuntu-24.04` and proposes the smallest fix at the cause. A change of product
   code, or a move of the test to `pace`, needs the user.

The choices and the findings of the agent that build these items are in
[ADR-R394](R394-choices-of-fix-lane-7.md) (proposed).

## Reason

1. Item 1: in 9 of 13 Capture runs and in both Recorder runs on `dom/integration`, no hosted `macos-15` runner
   took the job ("The job was not acquired by Runner of type hosted"). The one run that got a runner (run
   45523455772, job 138900837438) had 29 errors `OSError: [Errno 24] Too many open files` from about minute 5,
   and then the job did not end before its limit of 40 minutes.
2. Item 2: a higher limit can hide a leak.
3. Item 3: the test failed with "AssertionError: 1 frames replaced in 100 s" at commit dfc6c6e2a (run
   45523455772); the test wants 2 to 4.

## Open work

[open-work.md](../open-work.md)
