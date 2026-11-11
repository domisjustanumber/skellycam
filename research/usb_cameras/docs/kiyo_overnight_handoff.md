# Handoff: Kiyo Pro overnight test (age vs use)

2026-11-06 · for Dom, or whichever session runs it. Paths are relative to `research/usb_cameras/`.

## Why

The Razer Kiyo Pro (1532:0E05) wedged in both Windows suite runs on 2026-11-06, at a similar plug-in age:

| Run | Plug-in age at failure | Kiyo work before the failure |
| --- | --- | --- |
| Run 1 | 200.6–224.3 min (window) | 0 suite streams |
| Run 2 | 210.6 min | ~270 stream starts, ~380 control polls |

The signature was the same both times:
1. A stream start hangs: the MF reader release in run 1, a 35 s DirectShow open in run 2.
2. Every call then fails fast with `0x8007001F`.
3. The devnode stays "healthy" (problem code 0, no re-arrival), and only a replug recovers it.

Details are in [windows_results_20261106.md](windows_results_20261106.md) §8.

**The question:** does it fail at a fixed age after plug-in (a firmware or host timer), or because of cumulative use? Two samples can't separate these. This test does: **control polls only, no streaming, past the 3.5 h mark, then one stream start.**

## Expected outcomes

| Result | Reading |
| --- | --- |
| Polls stop answering at ~200–225 min with no streaming at all | age-dependent: a timer in the camera or host, not use |
| Polls answer all night, but the stream start at the end hangs or fails | a latent state that shows only at a stream start |
| Polls and the final stream all work past 4 h | the trigger needs streaming or use count |

## Before starting (attended, ~5 min)

1. **Replug the Kiyo** in its usual port: the Thunderbolt-controller USB-C hub (SS04 → hub port 4). Note the time; the poller also reads it from `LastArrivalDate`.
2. **Keep the PC awake overnight.** Sleep must be "Never" on the current plan, and the display may turn off. Check:

   ```powershell
   powercfg /q SCHEME_CURRENT SUB_SLEEP STANDBYIDLE
   ```

   Pause Windows Update restarts for the night.
3. **Leave everything else as found**, so this run is comparable with runs 1 and 2:
   - USB 3 LPM stays at Moderate and selective suspend stays on;
   - LogiTune and RazerAppEngine stay running (they held the Kiyo in both runs).

   Do **not** change the power plan or quit vendor apps for this run; those are separate arms (below).
4. **No other camera work overnight.** Other Claude sessions (e.g. skellycam-47) must not use the cameras. If anything must run, it has to use `tools/camlock.py`, and even then its lock waits delay polls.

## Run (unattended)

From `research/usb_cameras/`. This polls the Kiyo's controls through MF and DirectShow every 10 s for 5 h. Each poll is a read-only `wincam controls` call with a 3 s timeout under camlock, and nothing streams:

```powershell
uv run --script suite/windows/run_suite.py --only W-KIYO --kiyo-foreground --kiyo-minutes 300 --camera 0e05 --out-dir results/windows/Gerald/kiyo_overnight_<YYYYMMDD>
```

- `--camera 0e05` is the opt-in debugging filter. It is appropriate here, because this run is about the Kiyo alone.
- **Expect ~5 h.** It ends with `run_suite: done` and writes `W-KIYO.json`, `run_suite.json` and `summary.md`.

**After the poll window (attended or scripted):** one MF stream start at the default mode. Run it whatever the polls showed:

```powershell
$wincam = (Resolve-Path suite/windows/native/build/wincam.exe).Path
uv run --script tools/camlock.py --timeout-s 60 -- $wincam capture --api mf --device vid_1532 --width 1280 --height 720 --fps 30 --frames 90 --timeout-ms 10000 --out-dir results/windows/Gerald/kiyo_overnight_<YYYYMMDD>/final_stream
```

- Record its `summary.json`: stage, HRESULT, `first_frame_ms`.
- If it hangs, wincam times out by itself. That is a result, not a reason to retry.

## What to read in the morning

- `W-KIYO.json`, the onset record:
  - `first_failure` per API (utc, plug-in age, codes);
  - `failed_from_first_poll`;
  - `transitions`;
  - `failure_codes`;
  - `activity_changes` (vendor processes attaching or detaching).
- The plug-in age of the last answering poll and the first failing one. In this run there is no lock contention, so poll stamps are accurate to ~10 s.
  - The known harness bug, where stamps are taken before the lock wait (results doc §11), only matters when other camera work holds the lock.
- `final_stream/summary.json`.
- Device state afterwards:

  ```powershell
  Get-PnpDeviceProperty -InstanceId 'USB\VID_1532&PID_0E05&MI_00\*' -KeyName DEVPKEY_Device_ProblemCode,DEVPKEY_Device_LastArrivalDate
  ```

  The current instance on 2026-11-06 was `A&34494D13&0&0000`.

Write the result as a short `README.md` in the result folder, and update §8 of the results doc and REPORT.md's Kiyo line.

## Hazards

- **Never restart the device programmatically** (`pnputil /restart-device` or similar). On this machine LogiTune vetoes restarts and leaves MF locked out until a replug. A wedged Kiyo needs a physical replug.
- If the poller itself stalls (no new polls for minutes), kill only the `run_suite`/`wincam` processes. Do not touch the device.

## Follow-up arms (later nights, one change each)

Run each arm only if the result above leaves the question open. Use the same command each time, with a fresh replug.

| Arm | Change | Tests |
| --- | --- | --- |
| A4a | USB 3 LPM off in the power plan (Advanced settings → USB → USB 3 Link Power Management: Off; revert afterwards) | the LPM hypothesis; Linux 7.0 has a `NO_LPM` quirk for this exact device |
| A4b | Kiyo on a USB 2.0 port (no LPM at high speed) | the same hypothesis by another route |
| V | Quit RazerAppEngine and LogiTune before the replug (services left alone) | vendor control traffic |
| S | Streaming loop: one 10 s stream every minute plus polls, up to 6 h | use count vs age, with the onset timed to a command |

Also still open: the Kiyo's MJPEG modes, including 60 fps, have never been rated. Run `--only W-MJPEG --camera 0e05` within 2 h of a replug.
