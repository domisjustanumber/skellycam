# Windows timer resolution and capture timing

2026-10-28 · Dom

Question: "There used to be a Windows bug where the system timer did not update at regular intervals, and you had to run some C# code to make it update reliably. Is there evidence of this, and is it still the case on Windows 11?" Also: would moving the test scripts to Python 3.13 change any results?

Confidence labels follow [REPORT.md](../REPORT.md): **measured** (a result file supports it), **inferred**, **web** (external source, re-checked by a verifier). Web evidence was gathered by the interrupted workflow `wf_31366494-74f` (see [capture_backends_review.md](capture_backends_review.md) section 3): gatherers `web-mf-flaky` and `web-app-choices` produced 31 timer claims, 24 confirmed and 7 weakened ([results/agent_reports/mf_vs_dshow_reports_and_verifications.json](../results/agent_reports/mf_vs_dshow_reports_and_verifications.json)).

## Answer

No source describes that exact story. It matches a real, documented behaviour that changed in 2020 and again in Windows 11, and that still applies, per process, today.

- **The system timer.** Windows wakes sleeping threads on a global timer interrupt, by default 15.625 ms (64 Hz). The coarse wall clock (`GetSystemTimeAsFileTime`, `DateTime.UtcNow` in old .NET Framework) only advances on that interrupt. A 2012 Microsoft blog measured `DateTime.UtcNow` changing 3 times in 50 ms on one machine and 50 on another ([Osenkov](https://learn.microsoft.com/en-us/archive/blogs/kirillosenkov/high-accuracy-datetime-utcnow)). **Web.**
- **The old workaround.** Before Windows 10 2004, `timeBeginPeriod` was global: the lowest request from any process applied to every process. Keeping a small helper running (often a C# tray app, or tools like TimerResolution or Process Lasso) held the whole system at 1 ms or 0.5 ms. This is very likely the "C# code". **Web.**
- **Windows 10 2004 (2020).** "This function no longer affects global timer resolution… For processes which have not called this function, Windows does not guarantee a higher resolution than the default system resolution" ([timeBeginPeriod](https://learn.microsoft.com/en-us/windows/win32/api/timeapi/nf-timeapi-timebeginperiod)). The change was unannounced; Bruce Dawson documented it first ([The Great Rule Change](https://randomascii.wordpress.com/2020/10/04/windows-timer-resolution-the-great-rule-change/)). He reports the interrupt rate itself is still global; only the scheduler's treatment of non-requesting processes changed. **Web.**
- **Windows 11.** "If a window-owning process becomes fully occluded, minimized, or otherwise invisible or inaudible to the end user, Windows does not guarantee a higher resolution." A process can opt out with `SetProcessInformation(PROCESS_POWER_THROTTLING_IGNORE_TIMER_RESOLUTION)` ([SetProcessInformation](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-setprocessinformation)). The rule names window-owning processes, so windowless camera worker processes are not clearly covered. **Web.**
- **`GlobalTimerResolutionRequests`** (DWORD 1 under `HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\kernel`, reboot) reportedly restores the old global behaviour on Windows 11 / Server 2022+.
  - It is undocumented by Microsoft; the only evidence it works is one blog commenter, and the [valleyofdoom/TimerResolution](https://github.com/valleyofdoom/TimerResolution) README cites that same comment.
  - Dawson: software "definitely shouldn't set it on user machines".
  - It is a registry value, so it may be the "register" in the story. **Web**, weak.
- **Other candidates for the story:**
  - Windows 8+ "dynamic tick": the timer interrupt pauses when idle; BCDEdit has `disabledynamictick`.
  - The XP-era "performance counter may leap forward" chipset bug (KB274323), which Microsoft's timestamp doc says is handled since Vista/7 by checking the TSC at boot.

  Not verified further.
- **No current bug found.** Searches for Windows 11 22H2–24H2 timer or `GetSystemTimeAsFileTime` regressions found nothing specific.

## Measured on Gerald

[tools/timer_probe.py](../tools/timer_probe.py) opens no camera. Result: [results/windows/Gerald/timer_resolution_20261028/result.json](../results/windows/Gerald/timer_resolution_20261028/result.json). Windows 10.0.26300, Python 3.12.13.

| | Without `timeBeginPeriod` | After `timeBeginPeriod(1)` |
| --- | --- | --- |
| Global timer (`NtQueryTimerResolution`) current / coarsest / finest | 0.5 / 15.625 / 0.5 ms | same |
| `GetSystemTimeAsFileTime` update step, p50 | 0.5 ms (some 0.7, 1.0) | same |
| `GetSystemTimePreciseAsFileTime` step, p50 | 0.4 µs | same |
| `Sleep(1)` actual, p50 / max | 1.50 / 2.04 ms | 1.50 / 2.02 ms |
| `GlobalTimerResolutionRequests` | not set | — |

- **Some other process already holds the timer at 0.5 ms** (not identified; `powercfg /energy` needs admin). So this run cannot show the 15.625 ms default or the Windows 11 occlusion rule, and the "after" column cannot differ.
- **A process that never called `timeBeginPeriod` still got 0.5 ms clock steps and ~1.5 ms `Sleep(1)`.** Dawson's Windows 10 2004 measurements suggest the opposite (~64 wakeups/s). A verifier reproduced this result.
- **Build 26300 may be an Insider build** (24H2 = 26100, 25H2 = 26200), so it may not represent shipping Windows 11. **Measured** (one machine, one build).

## What this means for camera timing

- **The ~16 ms grid on Windows frame timestamps is not the system timer.** It persists with `timeBeginPeriod(1)` and with the global timer already at 0.5–1 ms, and it also appears on the KS path (REPORT finding 7, [prior_art/SURVEY.md](../prior_art/SURVEY.md)). The unverified hypothesis is isochronous transfer-completion boundaries. No timer setting removes it; only the camera's UVC PTS/SCR does. **Measured.**
- **What `timeBeginPeriod(1)` did change was wake-up jitter.** Arrival-phase jitter fell from 0.3–0.5 to 0.05–0.08 ms ([RERUN_20261027.md](../results/windows/Gerald/RERUN_20261027.md)). That matters for sleep-polling capture loops. **Measured.**
- **QPC is unaffected.** `perf_counter_ns` uses QPC (10 MHz here). Microsoft: a higher timer resolution "does not improve the accuracy of the high-resolution performance counter."

## Effect of moving the test scripts to Python 3.13

Python 3.13 changes two clocks on Windows ([What's New 3.13](https://docs.python.org/3/whatsnew/3.13.html)):
- `time.monotonic()`: from `GetTickCount64`, which stepped every 16.0 ms even with the timer at 0.5 ms (verifier measurement), to QPC;
- `time.time()`: from `GetSystemTimeAsFileTime` to `GetSystemTimePreciseAsFileTime`.

`perf_counter` stays QPC and becomes the same clock as `monotonic`.

**It would not change any measured result in this study.**

- **Per-frame times in every Python probe already use `time.perf_counter_ns()`** (QPC): `mjpeg/pyav/pyav_capture.py`, `prior_art/pyav_dshow_probe.py`, `prior_art/gst_probe.py`, `prior_art/sdl3_camera_probe.py`. The C++ tools (`mf_mjpeg_capture`, `mf_uvc_timing`, `flash_timecode`) read QPC directly. Nothing timing-critical depends on the Python version.
- **`time.monotonic()` on Windows is used only for loop deadlines and timeouts:**
  - the capture windows of `gst_probe.py`, `pyav_dshow_probe.py` and `sdl3_camera_probe.py`;
  - the budget check in `bandwidth/run_concurrency.py`;
  - `tools/camlock.py`.

  A window end that is off by up to 16 ms out of 6–10 s does not change any reported rate. The fps figures divide by the span of QPC arrival times, not by the window length.
- **One reported field uses it:** `pipes_while_streaming_t_s` in `run_concurrency.py`, a seconds-scale "when was the pipe snapshot taken" value with 16 ms granularity. Informational only.
- **`time.time()` measures only seconds-scale durations** (`run_one.py` `capture_s`, `run_matrix.py`, `naming/win_restart_test.py` timelines, ETW scripts). 3.13 would make these finer, and nothing depends on them.
- **On Linux and macOS** `monotonic` is already `CLOCK_MONOTONIC` / `mach_absolute_time`, so the drafts there are unaffected.
- **Pins.** Most scripts allow `>=3.10`, and `uv` picked 3.12.13 here. Two scripts pin `<3.13` because of `gstreamer-bundle`.

**Where 3.13 would matter is skellycam itself** (`requires-python >=3.11`, `.python-version` 3.12):
- `skellycam/api/websocket/websocket_server.py:242` uses `time.monotonic()`, which steps every ~16 ms on 3.12.
- `skellycam/core/timestamps/timebase_mapping.py:22-23` anchors UTC with `time.time_ns()`. On 3.12 that lags true UTC by up to one timer interval (0.5 ms here, up to 15.625 ms on an idle machine): a constant bias per recording, the same for all cameras.
- `skellycam/utilities/wait_functions.py`: `wait_100us`, `wait_10us` and `wait_1us` each sleep ~0.5 ms median, and `wait_1ms` ~1.5 ms (verifier measurement, 3.12 with the global timer at 0.5 ms). That is an OS floor, which 3.13 does not change.

## Practical guidance for skellycam

- **Call `timeBeginPeriod(1)` in each camera worker process,** since requests are per-process now. Better, block on the capture API instead of sleep-polling.
- **If a window-owning process may be minimized,** consider the `PROCESS_POWER_THROTTLING_IGNORE_TIMER_RESOLUTION` opt-out.
- **Never set `GlobalTimerResolutionRequests` on users' machines.**
- **Move skellycam to Python 3.13+,** or switch the UTC anchor to a precise clock, so `monotonic` and `time` stop stepping at 16 ms.
- **Remember QPC-to-UTC drift on long recordings.** It doesn't matter between cameras on one PC, which share QPC. Microsoft cites ±30–50 ppm crystals, partly compensated at boot.
