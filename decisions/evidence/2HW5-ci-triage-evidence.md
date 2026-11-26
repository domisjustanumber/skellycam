# 2HW5 — Evidence of the CI triage of the first test run on dom/integration

The evidence of [ADR-2HW5](../entries/2HW5-choices-of-the-ci-triage-of-the-first-test-run-on-dom-integration.md).

Set-up: a copy of 32eb69e20 ("before") and a copy with the test changes of ADR-2HW5 ("after") under WSL Ubuntu
24.04 (uv 0.13.9, Python 3.13.18, pytest 9.2.0, a stand-in `sounddevice` with no PortAudio), `taskset -c 0-1`
(2 cores) or `taskset -c 0` (1 core), one pytest process at a time. Windows: the development machine, Windows 11,
Python 3.13.18, the full machine or a process affinity of 2 cores. A Linux result is a fact about Linux only. Other
work ran on the same host at the same time.

## The CI run

CI run 45872128301 (workflow Tests, commit 32eb69e20): `uv run pytest skellycam/tests/ -m "not pace and not
capture_local"`. ubuntu-24.04: 7 failed, 1323 passed. windows-2025: 1 failed, 1356 passed.

1. **Four certify tests (ubuntu-24.04).** `test_t_cert_08_and_17_...`, `test_t_cert_10_a_camera_in_use`,
   `test_t_cert_92_17_...` and `test_review_4_...`. The item of the good camera is `partial`, not `pass`. Its one
   row that is not `pass` is `<label>:native-jpeg:source-equals-ring` `not-run` `ring-lapped` (the row
   `sequence` `not-run` `no-sequence` is on each Linux run and does not make an item `partial`).
2. **T-RING-40 (ubuntu-24.04).** `(1603, <ReadResult.LAPPED: 3>)`: the test reader got `LAPPED` on the JPEG ring.
3. **T-RING-38 (ubuntu-24.04).** `timed out: camera e605 in ('ready',)`, with the log line "Camera e605 failed
   during streaming: no frame for 2 s": the planned end of the test (no frame after frame 200) came before the
   test saw `ready`.
4. **T-REC-41 `[BGR ring]` (ubuntu-24.04).** `(46, 46)`, `assert 46 >= 60`: 46 decodes and 46 BGR writes with
   an image. Each write had one decode; the decode stage skipped frames.
5. **`test_t_cert_92_a_hang_at_the_open` (windows-2025).** The good camera (`17ae`) has a `not-reached` row. Its
   log: it published its config 0.02 s after its start, then nothing for 4.7 s; 0.05 s after the hang of
   camera `e605` ended its open ("open did not return in 5 s"), its loop stopped with no failure line ("replaced 0
   frames since its first frame in the gate"): the close of the group at the end of a run with no take. The test
   took 7.7 s. A passing run on this machine takes 17 s. The cause is the race of item 5 of ADR-2HW5.
6. **`test_a_slow_stop_has_a_gap_only_on_the_last_row[0.2-60]` (windows-2025, the pace step, not blocking).**
   One `camera_gap`, `row=17 from=115 to=117`, that is not on the last row: one lost frame at 60 fps in the middle
   of the take, the busy-machine case of Q619.

## The race of item 5

The steps, in the code of 32eb69e20:

- `CameraGroup.start` opens the rings only after each camera published its config or failed (`camera_group.py`
  236 to 241). The camera that hangs at its open fails after 5 s. Until then the good camera waits in `waiting`.
- `waiting` is a settled state (`camera_status.py` 15), so `_await_settled` returns at once (`camera_group.py`
  352 to 362). The good camera has its config; with its ring it is `ready` within about 1 ms.
- `Session.wait_states` sees the final states on its first look and returns with no await (`session.py` 276 to
  280). `open_step` then cancels `watch_rings` (`session.py` 348 to 350). That task looks for new rings each 5 ms
  (`session.py` 366), and no look came after the ring open. So no `RingWatch` exists.
- `judge_open` writes `opens` `pass`, but it adds the camera to `live` only when it has a watch (`session.py` 403
  to 406), and it gives no reason. `_fill` and `_not_reached` (`run.py` 940 to 985) then give its later checks one
  `not-reached` row with `prior-check-failed`.

An independent review found it. Its probe (`Session.watch_rings` with a look each 0.25 s, and a spy on
`judge_open`) ran here on Windows, PROCESS workers, in a scratch folder outside the repository: 1 failed in 9.1 s,
the CI failure. The spy gave `feed-0000` `failed` with no watch and `feed-0001` `ready` with no watch at the judge
of the open. The rows of `feed-0001` ended in `not-reached` `not-run` `prior-check-failed`.

## Runs on this machine

| Test | Copy | Cores | Runs | Failed |
|---|---|---|---|---|
| The four certify tests of item 1, together | before | 2 | 3 | 4 test failures in 3 runs (12 test runs) |
| The same | after, first form (no hold from the ring open) | 2 | 5 | 3 test failures |
| The same | after | 2 | 5 | 0 (20 test runs) |
| T-RING-40 | before | 2 | 3 | 1 (`(726, LAPPED)`) |
| T-RING-40 | after | 2 | 6 | 0 |
| T-RING-38 | before | 2, then 1 | 3 + 5 | 1, on 1 core (`timed out: camera e605 in ('ready',)`) |
| T-RING-38 | after | 1 | 10 | 0 |
| T-REC-41 `[BGR ring]` | before | 1 and 2, also 1 core with a busy loop | 14 | 0 (not reproduced) |
| T-REC-41 `[BGR ring]` | after | 1 | 10 | 0 |
| `test_t_cert_92_a_hang_at_the_open` (PROCESS workers: no change of ADR-2HW5 acts) | after, Windows | all, then 2 | 3 + 1, then 4 | 0 (not reproduced) |
| The reviewer's probe (look of `watch_rings` each 0.25 s, a spy on `judge_open`) | after, Windows | all | 1 | 1 (the CI failure) |
| T-CERT-151 (no look after the first) | after, Windows | all | 3, and 1 with `--runxfail` | 3 `xfailed`; the run with `--runxfail` fails on `native-jpeg:format` of the good camera, whose rows end in `not-reached` |
| T-CERT-151 and `test_t_cert_92_a_hang_at_the_open`, Linux | after | 2 | 2 | 0: T-CERT-151 `xfailed`, the hang test passed |
| The four certify tests and T-RING-38, with the hold that ignores a closed ring | after | 2 | 5 | 0 (25 test runs) |

Diagnostics of the before copy (print lines in a scratch copy only, not in the repository):

- In a failing certify run, the ring watch of the good camera started at frame 1290 of a ring whose newest frame
  was 1354 at its attach, or it attached at an empty ring and its first read was already `LAPPED`. The hashed
  frames of D-11 (source frames 110 to 139) were not in its hashes, so `frames_compared` was 0.
- With the first form of the change (the watch thread holds the clock only after its start), the watch still
  attached late in each failing run: the newest frame at its attach was 73 to 1354, and its ring holds 30 frames.
  The session looks for new rings each 5 ms of real time (`Session.watch_rings`). The hold from the ring open
  (item 1) removed these failures.
- The changed tests passed on Windows (the four certify tests and both cases of T-REC-41: 6 passed). The
  changed files with `-m "not pace and not capture_local"` (`skellycam/tests/certify`, `test_bgr_camera.py`,
  `test_connection.py`): 155 passed, 2 xfailed (T-CERT-09 and T-CERT-151).
