# The stall watch under load with THREAD workers (2026-11-27)

A diagnosis of the CI triage lane, for a question to the user (open work). No test and no product file changes.

## The failure

CI run 45933928951 (Capture, ubuntu-24.04, commit 3fcec4235):
`skellycam/tests/capture/test_stall_watch.py::test_the_watch_ends_no_healthy_camera_under_load[thread]`,
`assert not facts["ended"]` got `{'17ae': {'ready': 406675801134, 'dead': 413514964556}}` (test_stall_watch.py:232):
a camera went `dead` 6.84 s after `ready`. The only log line: `Camera 17ae failed during streaming: no frame for
2 s` (the in-process rule, `CameraLoop._read`, camera_loop.py 291 to 302). No line of the main-process watch ("no
loop pass for 2.5 s"), no other WARNING. The commits 93b1c57f4..3fcec4235 changed no code on this path.

## The reading

- The test runs on the real clock (`capture_app(..., virtual=False)`): the clock helpers of `capture_session.py`
  (`install_watch_clock`, `hold_clock_*`, the gate probe) act only on a virtual clock.
- With THREAD workers, the camera loops and the frame thread of the fake (`_deliver_loop`) are Python threads of the
  main process. They share one GIL with the four busy threads of the test, the watch thread and the test thread.
  When the frame thread or the loop gets no GIL for 2 s, the read finds no frame and the in-process rule ends the
  camera, as it is built to do. The docstring of the test records loop-pass gaps of 0.78 s to 1.20 s on CI runners.
- The product runs camera loops as processes only (`__main__.py`, certify: `WorkerMode.PROCESS`). THREAD is a test
  mode. Whether freemocap uses THREAD workers is not checked (outside this repository).

## Runs

WSL Ubuntu 24.04, a stand-in `sounddevice`, `taskset -c 0-1` (2 cores), the test `[thread]` alone, rounds
interleaved over three copies (one pytest process at a time):

| Copy | Result |
|---|---|
| e5a5e3c89 | 30 of 30 passed |
| 85e4e939b (8c95e992b^, before the code of ADR-4PPS items 10 and 11) | 30 of 30 passed |
| 43f9fa003 (before the merge of the JPEG lane) | 30 of 30 passed |

The rate is below about 1 in 30 on this host at each commit; no commit moves it.

A forced form (a scratch copy of e5a5e3c89 only): `sys.setswitchinterval(3.0)` during the load, so one busy thread
can hold the GIL for up to 3 s. `[thread]`: 3 of 3 failed (one "no frame for 2 s", two "no loop pass for 2.5 s").
`[process]`: 3 of 3 failed with "lost the server's heartbeat" (decision L: the main process was frozen for many
seconds). The forced form is thus stronger than the load on CI: it shows the THREAD mechanism (starved loops trip
both stall rules), but it does not separate the two worker modes.
