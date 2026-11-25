# 4CAF — Choices of fix lane 8: the close of the queues of a camera group

**Status:** accepted, 2026-11-25 (user: [ADR-ZT5F](ZT5F-acceptance-of-the-choices-of-fix-lane-8.md), "yes to all"; commit to dom/fix-lane-8; was proposed,
2026-11-25 (agent; builds item 2 of
[ADR-2SX2](2SX2-acceptance-of-the-choices-of-fix-lane-7-and-its-follow-ups.md) and item 4 of
[ADR-R394](R394-choices-of-fix-lane-7.md))).

## Decision

1. **The spec.** The rule is in [`windows-capture.md`](../../specs/windows-capture.md) 5.9, a new section of "The
   shared loop". That spec owns the camera group of the capture path (the gate, the states, the start-up) and its
   fake-source tests; no spec had a section for the close of a group. The test is T-CAP-114 (16.2), step 3a, on each
   system (16.6, 16.7).
2. **The test.** `test_t_cap_114_a_closed_group_leaves_no_pubsub_manager_and_no_open_queue` in
   `skellycam/tests/capture/test_states.py`: blocking, no `pace`, THREAD workers on the test clock. It asserts on
   portable signals: the registry has no entry for the group; a `put` to each subscription queue raises
   `ValueError`; a read of each subscription queue and of `setup_failures` raises `OSError` (its read end is closed).
   It waits for the read ends with the loose wait of the harness (60 s), because a feeder thread closes its ends
   after the close.
3. **The code**, in three files, with no change of a public name or signature:
   - `PubSubTopicABC.close` (`ipc/pubsub/pubsub_abcs.py`): for each subscription, `cancel_join_thread`, a read of
     the unread messages (at most 10,000), `close`, and for a queue with no feeder thread a close of its two pipe
     ends (`_reader`, `_writer`; private names of `multiprocessing.Queue`, marked as a shortcut). The real wait of
     100 ms after each topic is removed.
   - `close_camera_group_pubsub_manager(group_id)` (`ipc/pubsub/pubsub_manager.py`), a new function beside
     `create_camera_group_pubsub_manager`: it removes the manager from the registry and closes it. A second call
     does nothing.
   - `CameraGroup.close` keeps its watch thread in `_watch_thread`. As its last step, it waits at most 2 s for the
     end of the watch thread, then closes the manager of the group and `ipc.setup_failures`. If the watch thread
     does not end, or if an earlier step raises, the queues stay open (an error line for the watch).

## Reason

1. Item 3: the root cause is that no code closed or removed the manager of a closed group (ADR-R394 item 2). The
   close of `multiprocessing.Queue` of Python 3.13.18 does not close the pipe of a queue that never had a `put`,
   and the `WorkerRegistry` of the app keeps each worker with its queue arguments, so these queues never go. A
   feeder thread that waits on a full pipe never takes its end marker; the read of the unread messages lets it end.
2. Item 3, the wait: a real wait of 100 ms for each of the 8 topics adds 0.8 s to each close of a group, and no
   step needs it: the feeder thread closes its ends after its last message.
3. No lost message (the risk of the task). The close of the queues comes after the stop of the take, after the end
   of each camera process or thread (`_close_cameras`), after the end of the watch thread and after the last read
   of the diagnostics. After that point no code reads or writes a queue of the group, so the messages that the close
   reads are messages that nobody reads. The shared log queue (`LogsTopic.publication`) is not a subscription and
   stays open. A camera that cannot be killed makes `_close_cameras` raise, so its queues stay open for a later
   close. The take files are written by the camera processes, not through these queues. Evidence items 4 and 5.
4. FreeMoCap uses `create_camera_group_pubsub_manager` and `PubSubTopicManager.close` in one test
   (`freemocap/tests/test_dev_reload.py`): their names and signatures do not change. At run time it reads only
   `ipc.global_kill_flag` of a group.

## Evidence

[evidence/4CAF-fix-lane-8-evidence.md](../evidence/4CAF-fix-lane-8-evidence.md).

## Alternatives rejected

1. A close of the queues in the test harness: it hides the leak of the product (ADR-N14T item 2).
2. A close of the two pipe ends of each queue, also of a queue with a feeder thread: the feeder thread can still
   write, and a closed number can go to another file.
3. A drop of the references only (no close): the `WorkerRegistry` of the app keeps them.
4. A put of a marker into a queue with no feeder thread, so that a feeder thread closes it: a reader that lives
   could get the marker.

## Open work

[open-work.md](../open-work.md)
