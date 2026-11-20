# BM73 — Fixes of the first CI run of the capture workflow

**Status:** proposed, 2026-11-20 (agent; waits for the user).

## Decision

The first run of `.github/workflows/capture.yml` (commit d8989972d) failed 15 tests on Windows, 17
on Linux and 29 on macOS. The development machine passed the same suite. These are the causes and
the fixes. An agent made the choices below. The user decides them.

1. **F1, product.** `_build_processing_table` in
   `skellycam/core/timestamps/recording_timestamp_stats.py` gave the int `0` to
   `_format_stats_row(percentage: float)` when the stage times add up to no positive time. Beartype
   refused it, and each record stop returned HTTP 500. The value is now `0.0`; the hint stays. The
   stage total is not positive with a source that does not stamp the retrieve (Media Foundation and
   the fake source): two stage times are then minus a clock value and a clock value. The virtual
   clock of the tests starts at 1000 s, so the total was positive only on a machine with a
   `perf_counter` of more than about 1000 s. The development machine had run for days; a CI runner
   starts fresh. `test_recording_timestamp_stats.py` sets the medians, so it fails without the fix
   on each machine. No other int `0` goes to a float hint there.
2. **F2, product.** `_probe_codec` in `skellycam/core/recorders/videos/fourcc_codec_helpers.py`
   sets its `SIGALRM` limit only on the main thread. With `WorkerMode.THREAD` the camera loop is a
   thread, and CPython refuses `signal.signal` there. With `WorkerMode.PROCESS` the loop is on the
   main thread of the camera process, and the alarm works as before. The test uses a stand-in
   `signal` module with the rule of CPython, so it fails without the fix on each system.
3. **F3, test.** The product makes each process and each shared object with the default context
   (`ManagedProcess` uses `multiprocessing.Process`), so it does not mix contexts. The self-test of
   the factory now starts its process with the default context too.
4. **F4, test.** A camera sets `ready` before its first ring write. T-CAP-13 read the ring writes
   when it saw `ready`, so the list could be empty. The test now waits for the first ring write of
   each camera, then checks it with the same criterion. The case "late first write" stops each loop
   for 0.5 s after `ready`.
5. **F5, test.** T-CAP-46 runs its steps in a fresh process. The pytest main thread is in a
   single-threaded apartment after the import of `sounddevice`, and comtypes joins the MTA at
   import. The product imports comtypes only in a fresh process (the camera process and the
   detection child), and neither imports `sounddevice`.
6. **F6, tests.** The OpenCV fake tests run on a `VirtualClock`. The OpenCV source stamps the
   arrival itself, so `OpenCVFakeFactory` replaces the module name `time` of
   `skellycam.core.camera.capture.opencv_source` with the clock (an existing seam; no new seam and
   no product change). T-CAP-86 joins the clock while it collects relay messages. The self-test of
   the real-time fake checks the schedule of the frames that it reads, not that the reader saw each
   frame. No product limit changed.
7. **F6, CI.** T-CAP-40, T-CAP-82 and T-CAP-85 measure real gaps of 100 ms (U16). They get the
   marker `capture_timing`. The macOS job runs them in a separate step. Section 15 of
   [`specs/windows-capture.md`](../../specs/windows-capture.md) says that the three jobs run the same
   selection. If the user accepts this item, that line of section 15 must change.
8. **F8, product.** The watch thread of `CameraGroup` logs (ERROR, with the camera ID) an error of
   one step and continues. It no longer closes a ring reader: it hands the close to the event loop
   of `start` with `call_soon_threadsafe`. The callback closes the rings only if the camera still
   has the ring of the ended process. `_ring_lock` stays, and the interim relay keeps it. The
   hand-off keeps the 4a preview relay, which reads `ring_readers` on the loop with no lock, and its
   accepted spec unchanged.

## Reason

- Items 1, 2 and 8 are product faults: they show in the product, not only in a test.
- Items 3 to 6: the test was the faulty side. Each criterion stays.
- Item 6: a test of logic must not measure the speed of the machine.
- Item 7: the 100 ms limit is a rule of the user (U16), so it stays. The separate step shows a
  slow runner apart from a fault of logic.
- Item 8: the hand-off is smaller than a lock in each loop-side reader, and the camera group has the
  loop of `start`. Each other close of a ring (`apply`, `close`) already runs on the loop.

## Evidence

- F1: a virtual clock start of 10^18 ns gives the HTTP 500 on the development machine
  (T-CAP-08).
- F4: a copy of T-CAP-13 with diagnostics failed in 4 of 15 runs under load (30 busy processes).
  Each failed run had no ring write for either camera and correct states. A 0.5 s stop after
  `ready` made the old test fail each time.
- F5: `import sounddevice`, then an import of
  `skellycam.core.camera.capture.media_foundation.com`, gives `RPC_E_CHANGED_MODE` on the
  development machine. No device was used.
- F6: with each loop frame 80 ms slower (an injected sleep), the OpenCV tests pass. With each relay
  payload 0.5 s slower, the old T-CAP-86 fails with "not ready in 15 s", as on macOS, and the new
  test passes.

## Alternatives rejected

- F1: a hint of `float | int`. It hides the fault of the caller.
- F2: a thread with a join limit in place of the alarm. The alarm never stopped a hung C call.
- F3: an explicit spawn context in the product on Linux. The product does not mix contexts. A change
  of the start method is a separate decision (see [open-work.md](../open-work.md)).
- F6: smaller limits for CI, or fewer frames in the fake. They change criteria, not the cause.
- F8: a lock in each loop-side reader of `ring_readers`. It changes the accepted spec of the 4a
  relay.

## Open work

See [open-work.md](../open-work.md).
