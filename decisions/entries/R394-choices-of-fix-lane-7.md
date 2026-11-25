# R394 — Choices of fix lane 7: the macOS jobs by hand, the leak of open files, and the start of a group on the test clock

**Status:** accepted, 2026-11-25 (user: [ADR-2SX2](2SX2-acceptance-of-the-choices-of-fix-lane-7-and-its-follow-ups.md),
"yes to all"; commit to dom/fix-lane-7; was proposed, 2026-11-25 (agent; builds items 1 to 3 of
[ADR-N14T](N14T-decisions-of-the-user-on-the-ci-review-of-2026-11-25.md))).

## Decision

1. **The macOS jobs by hand** (item 1 of ADR-N14T). The condition is on the job, after `name`:
   `if: github.event_name == 'workflow_dispatch'`, in `capture-macos` of `capture.yml` and in `recorder-macos` of
   `recorder.yml`. The triggers of the workflows, the job-level concurrency group of `capture-macos`, the steps and
   the pace steps (Q619) do not change. A comment over each job and the header comment of each workflow say it.
   [`windows-capture.md`](../../specs/windows-capture.md) section 15 and [`recorder.md`](../../specs/recorder.md)
   12.1 (the workflow item and the macOS column of the table: "(by hand)") state it.
2. **"Too many open files" is a leak of the product** (item 2 of ADR-N14T). On Linux, the count of open files of the
   pytest process grows by about 19 pipe ends for each camera group that a test makes, and never goes down: from 12 to
   3,962 in the selection of the first macOS step. The holder is the global registry `CAMERA_GROUP_PUB_SUB_MANAGERS`
   of `skellycam/core/ipc/pubsub/pubsub_manager.py`: `CameraGroup.close` does not close the `PubSubTopicManager`
   of its group or remove it, so its `multiprocessing.Queue` subscriptions (2 pipe ends each, and a feeder thread
   after the first `put`) stay. It is product code, so this lane changes no code and does not raise the limit. The
   cause on macOS is [NV].
3. **The start of a group on the test clock** (item 3 of ADR-N14T). Two rules in the test helpers:
   - `capture_session.install_loop_clock` also wraps `CameraManager.start`: it calls `VirtualClock.expect` for each
     camera loop thread (THREAD workers) of the group before the first start, and calls `forget` for each thread
     that did not start when the start of the group returns or raises. `VirtualClock.expect` of a thread that is
     already expected does nothing.
   - `VirtualClock._advance` takes no forced step while an expected thread is not started (`ident is None`). The
     forced steps for a thread that runs, and at the gate (item 1 of
     [ADR-7GC1](7GC1-choices-of-the-gate-on-the-test-clock-and-the-end-of-t-cap-05.md)), do not change. This rule
     changes item 8 of [ADR-B7YV](B7YV-choices-of-fix-lane-6.md) ("until then only forced steps move the time").

   Three self-tests in `test_helpers.py`. [`windows-capture.md`](../../specs/windows-capture.md) 16.1 states the
   rule. No product code changes, and T-CAP-91 does not change and stays blocking.
4. **Proposal for the leak (the work is approved by item 2 of ADR-2SX2; not built).** The close of a camera group, after its cameras end,
   closes the `PubSubTopicManager` of the group and removes it from `CAMERA_GROUP_PUB_SUB_MANAGERS`. The close of a
   topic ends each subscription so that its pipe closes also when it never had a `put`: `cancel_join_thread`, then
   `close`, then the drop of the reference. A spec item and a test come first (a test that opens and closes a group
   a number of times and counts the open files of the process); then the code.

## Reason

1. Item 1: the reasons of ADR-N14T. A job-level `if` keeps the job for a run by hand.
2. Item 2: evidence items 2 to 4. With the registry cleared after each test (a diagnostic plugin, not a fix), the
   largest count was 121 open files, and the run passed also with the limit 256. Without it, the limit 256 fails
   at about 9 % of the run.
3. Item 3, the cause of the CI failure of T-CAP-91 (evidence items 7 to 10): `CameraManager.start` starts the
   workers one at a time. Before this change, a loop thread was expected only at its own start. When the main
   thread lost the CPU for about 2 ms or more after the start of the first worker, the first loop was the only
   participant: it ran the time through its open and its warm-up of 90 frames, and the second camera opened 3 s of
   virtual time later. Then the frames of the 30 fps camera start about 30 ms after the frames of the 29.97 fps
   camera with the same number, the first replaced frame comes after about 97 s, and the test counts 1. The forced
   steps are a second path: with only the first rule, a gap of 0.2 s gave three forced steps while the second
   thread was expected and not started, and the second camera opened 30 ms later (count 1 again).
4. Item 3, why the forced steps stay for a running thread: 7GC1 keeps them so that a loop that does not come back
   cannot stop the clock. A thread that is not started does no work, and only its starter can start it. Each path
   of a start (the start of the group, and the start of one worker) starts the thread or calls `forget`, so the
   rule cannot stop the clock for good.
5. Item 4: a server that applies and closes groups for a long time leaks the same pipes and threads. A change of product code needs the user, and its spec
   and tests come first.

## Evidence

[evidence/R394-fix-lane-7-evidence.md](../evidence/R394-fix-lane-7-evidence.md).

## Alternatives rejected

1. Item 1: delete the macOS jobs. The jobs stay for a run by hand.
2. Item 2: a higher open-file limit in the workflow (ADR-N14T item 2), or a close of the registry in the test
   harness. Each one hides the leak of the product.
3. Item 3: no forced step while any thread is expected. A thread that started and does work before its first wait
   must not stop the clock (7GC1).
4. Item 3: a wider band for T-CAP-91 (1 to 4), a later start of its 100 s window, or a move to `pace`. They change
   the test, not the cause; a move to `pace` needs the user.

## Not repeated

1. Without a delay injection, T-CAP-91 passed in each run in WSL on 2 cores before this change (alone, under CPU
   load and in the whole selection): the race needs a main thread that loses the CPU between two starts.
2. T-CAP-91 counts 2 in each passing run, not 3 (evidence item 7).

## Open work

[open-work.md](../open-work.md)
