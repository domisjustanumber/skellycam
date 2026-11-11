# Kiyo Pro overnight control run (run 3), 2026-11-06/07

Plan: [docs/kiyo_overnight_handoff.md](../../../../docs/kiyo_overnight_handoff.md). Context: [docs/windows_results_20261106.md](../../../../docs/windows_results_20261106.md) §8.

**Result: the third expected outcome.** The polls and the final stream start all worked past 5 h of plug-in age. The Kiyo did not wedge with read-only control traffic alone, and one MF stream start at 304.8 min was normal. Runs 1 and 2 failed at 200–225 min, so age alone does not trip the fault. It needs streaming or use, or an idle period that this run never allowed (see Caveats).

## Setup

| | |
| --- | --- |
| Device | Razer Kiyo Pro 1532:0E05, SuperSpeed, Thunderbolt-controller hub port 4 (`.../USBROOT(0)/4.4`), instance `A&34494D13&0&0000` |
| Plug-in | 2026-11-07 00:50:01Z (19:50:01 local), fresh replug |
| Poll window | 00:54:45Z – 05:54:46Z (300.0 min), plug-in age 4.7 → 304.7 min |
| Final stream | 05:54:46.7Z, plug-in age 304.8 min |
| Power | Balanced; USB 3 LPM Moderate (AC/DC); USB selective suspend Enabled; sleep Never (AC). Same as runs 1 and 2 |
| Vendor apps | LogiTune and RazerAppEngine running. LogiTuneAgent and RazerAppEngine held the camera (`activity_changes`, `in_use: true`) from the start, with no changes all night |
| Other camera work | none: no lock wait on any poll |
| Driver | [run_overnight.ps1](run_overnight.ps1), log [driver.log](driver.log) |

## Polls ([W-KIYO.json](W-KIYO.json))

| API | Polls | Answered | Timeouts | Controls answered per poll | Elapsed p50 / p99 / max |
| --- | --- | --- | --- | --- | --- |
| MF | 1801 | 1801 | 0 | 16/16 every time | 0.265 / 0.282 / 0.500 s |
| DS | 1801 | 1801 | 0 | 16/16 every time | 0.250 / 0.266 / 0.296 s |

- `first_failure`: none. `transitions`: none. `failure_codes`: none. `poller_errors`: none.
- The largest gap between poll pairs was 10.25 s, so the poller never stalled.
- `arrivals_seen` has one entry (the 00:50:01Z arrival, problem code 0): no re-arrival.
- Exposure read back −7 on every poll.
- Latency did not change across the 200–225 min window where runs 1 and 2 failed.

## Final stream ([final_stream/summary.json](final_stream/summary.json))

MF, MJPG 1280x720@30, 90 frames:

| Stage | Result |
| --- | --- |
| Every step (enumerate → activate_shutdown_object) | S_OK, none timed out |
| `open_to_first_frame_ms` | 598.5 (`first_frame_ms` 567.2) |
| Frames | 90/90 ok; 90 valid SOI/EOI; 90 with SOF0 size matching; 90 with UVC metadata |
| Measured fps | 29.59 over 3.01 s |
| `reader_release_ms` | 902.5 (released; `unreleasable: false`) |
| Exit | 0, `ok: true` |

Each of the 1 null sample, 1 stream tick and 1 discontinuity is the usual stream-start marker, not a drop.

## Device state afterwards

Problem code 0, LastArrivalDate still 00:50:01Z ([device_state_after.txt](device_state_after.txt), read by hand because the driver's dump had a formatting bug).

## Reading

- **Hypothesis 1 in its pure form (a timer at about 200–225 min after plug-in) is not supported.** With no streaming, the camera answered every query to 304.7 min, and a stream started cleanly at 304.8 min.
- **"A latent age state exposed by the next stream start" is not supported either:** the first stream start after 5 h worked.
- Both earlier failures came after streaming: R1 had a self-test streaming at 171–200 min, and R2 had about 270 stream starts. This fits a use or stream-dependent trigger (hypothesis 2), possibly combined with age, or with the conditions in the caveats.

## Caveats

- **One sample**, and only one stream start at the end.
- **No idle periods.** Polling every 10 s may have kept the device out of the selective suspend and USB 3 LPM states it would enter when idle. R1's onset followed 23.7 min with nothing touching the Kiyo. So an idle → suspend/LPM → stream-start trigger is still open. This run does not test hypothesis 3 (LPM).
- Vendor control traffic was present, as in runs 1 and 2, but it is not observed.

## Next

Per the handoff doc's follow-up arms:
- **S (streaming loop)** is now the most informative: one 10 s stream every minute plus polls, up to 6 h, after a fresh replug. It times the onset to a command.
- **A4a (LPM off)** after that.
- An idle arm (replug, leave untouched for about 3.5 h, then one stream start) would test the idle/suspend variant directly.
