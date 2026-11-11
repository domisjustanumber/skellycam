# Handoff: start the full Windows camera run at 23:00

**For:** a fresh Claude Code session on Gerald, opened in `C:\Users\Dom\GitHub\freemocap\skellycam`.
**Task:** start the full unattended camera test run at **23:00 local on 2026-11-09**. Let it run, about 7 h, and then
report the results to Dom.
**Written:** 2026-11-09 around 12:40 local, by the session that built and smoke-tested the suite.

## 1. When to start

- **Before 23:00:** launch the wait-then-run command in section 3 straight away, as a background command. It waits
  until 23:00 and then starts the run. Do not start the run before 23:00.
- **Between 23:00 and 01:00 that night:** start it straight away with the same command. Its wait is zero after 23:00.
- **Later than that, for example the next morning:** do not start. Ask Dom first, because the run needs about 7 h
  with nobody using the cameras.

## 2. What is already settled (do not redo)

- **Suite:** `research/usb_cameras/suite/windows/`. The runbook is [RUNBOOK_20261109.md](RUNBOOK_20261109.md); read
  its sections 1–3 and the known risks before you start.
- **Status:** the suite was reviewed adversarially over 3 rounds and its offline tests pass (402). Two hardware smoke
  runs were done; the second passed 14 of 14 checks with no device faults. Their folders are marked
  `SMOKE_RUN_NOT_RESULTS.txt`.
- **wincam 1.2:** already built at `research/usb_cameras/suite/windows/native/build/wincam.exe`. Do not rebuild it.
  The Windows SDK headers are missing on Gerald, and a rebuild is not needed.
- **Aborted start:** a start at 12:33 was stopped after about a minute at Dom's request. Its folder,
  `results/windows/Gerald/suite_20261109T173335Z`, is marked `ABORTED_RUN_NOT_RESULTS.txt`. Ignore it.
- **The Kiyo (Razer Kiyo Pro, `1532:0e05`) is on USB 3:** SuperSpeed, bcdUSB 0320, Thunderbolt xHCI / Genesys hub
  port `.../USBROOT(0)/4.4`.
- **Camera state at 12:40:** all four cameras present with PnP status OK: Kiyo, Logitech C930e, Logitech C922, and a
  generic `4c4a:4a55`.

## 3. Start command

Run this with the **PowerShell tool, `run_in_background: true`**. A background wait is allowed; a foreground sleep
is blocked.

```powershell
$target = [datetime]::Today.AddHours(23)
if ((Get-Date).Hour -lt 12) { $target = $target.AddDays(-1) }   # just after midnight: the 23:00 has passed
$wait = ($target - (Get-Date)).TotalSeconds
if ($wait -gt 0) { Start-Sleep -Seconds ([int][Math]::Ceiling($wait)) }
Set-Location C:\Users\Dom\GitHub\freemocap\skellycam
"=== preflight $(Get-Date -Format o)" | Out-File $env:TEMP\full_run_20261109_console.txt -Encoding utf8
uv run --python 3.12 --script research/usb_cameras/suite/windows/run_suite.py --plan *>> $env:TEMP\full_run_20261109_console.txt
"=== run $(Get-Date -Format o)" | Out-File $env:TEMP\full_run_20261109_console.txt -Append -Encoding utf8
uv run --python 3.12 --script research/usb_cameras/suite/windows/run_suite.py --cyc-profile reliability --reliability-cycles 400 --min-fps 30 --min-height 720 --max-height 720 *>> $env:TEMP\full_run_20261109_console.txt
"=== exit $LASTEXITCODE $(Get-Date -Format o)" | Out-File $env:TEMP\full_run_20261109_console.txt -Append -Encoding utf8
```

- **The `--plan` pre-flight** only lists cameras and opens none. It may print Kiyo age warnings or exit 3 (an
  age-based order check). **Ignore both:** the run starts regardless (see section 4).
- **Do not wrap `run_suite.py` in `tools/camlock.py`.** The runner already takes camlock for every camera command;
  an outer lock would make each inner one time out.
- **Once the run has started** (after 23:00), read the head of the console file once. Check the four cameras are
  listed, the Kiyo shows `speed=SS`, and a results folder `results/windows/Gerald/suite_2026111(0)T...Z` is named.
- **Do not poll after that.** You are notified when the background command exits.

## 4. Dom's rules for this run

- **No fresh Kiyo replug.** The "~210 min after plug-in" Kiyo wedge is only a theory. Run 3 on 11-06/07 polled the
  Kiyo for 305 min with no wedge. Dom suspects the wedge is a collision: several processes reaching the Kiyo at once.
- **If the Kiyo wedges, log it and carry on.** The runner already does this:
  - it records the fault (`0x8007001F`, a hung or unreleasable reader, or a command killed at its timeout);
  - it skips the Kiyo's streaming work while the Kiyo is faulted;
  - it re-probes the Kiyo with a 1-frame capture at the start of every later test, and un-gates it if it answers.

  Do not stop the run, replug, restart devices or retry by hand. Only a replug has ever recovered a wedged Kiyo, and
  that is Dom's call later.
- **Leave the machine as found:**
  - do not kill LogiTune, Logi Options+ or Razer processes; W-ENV records what is running;
  - no registry writes (tier 0 only), no device restarts (`pnputil`), no driver changes;
  - no other camera work on Gerald while the run is going, including other agents and the Windows Camera app;
  - every camera command goes through camlock (the runner does this).
- **Power:** Gerald never sleeps on mains power (checked 12:40). On battery it sleeps after 10 min. Before launching,
  check it is on mains (`(Get-CimInstance Win32_Battery).BatteryStatus`: 2 means AC; no battery is also fine). If it
  is on battery, tell Dom; do not change power settings.
- **Results:** results stay local. Do not commit, and do not put results in Claude Docs.

## 5. Evidence for the collision theory (read-only)

- **Before the run starts,** take a read-only snapshot of Windows' camera-usage record (`LastUsedTimeStart` /
  `LastUsedTimeStop` per app under `...\CapabilityAccessManager\ConsentStore\webcam`, HKCU and HKLM). Take it once
  more after the run. Save both to `results/windows/Gerald/camera_consent_20261109/` next to `consent_1233.json`
  (taken at 12:33 the same day). The 12:33 snapshot showed no app use since 2026-10-13, and none of the suite's own
  tools, so this record may not cover desktop apps. Note that rather than lean on it.
- **Do this in a separate tool call** before launching section 3, or put it at the top of the background script
  before the wait. Reading the registry is allowed; writing it is not.

## 6. When the run finishes

Report to Dom:

1. **Outcome:** exit code, results folder, total time, and the test count with any `error` or `untested` tests.
   Use `summary.md` and `run_suite.json`.
2. **The Kiyo:** did it wedge?
   - If so, give the first symptom time to the second (wincam `utc_started`, not the request time), which test and
     command were running, and the plug-in age then. Use `run_suite.json` faults and `first_failure`, `W-KIYO.json`
     polls, and `suite_log.txt`.
   - Say what else was reaching the Kiyo then. Look for camlock waits, and W-MULTI, W-FMT-NOGRAB "while streaming"
     or W-PYAV-LIST "while streaming" sessions; those deliberately reach a camera from a second process. Add the
     vendor processes and the consent snapshots.
   - Say whether later re-probes recovered it.
3. **Headline ratings:** per camera and API, give the ratings for raw JPEG, listing without opening, formats without
   opening, exposure/AE and focus/AF controls, and open/close reliability (W-CYC 400 cycles).
4. **Camera state afterwards:** PnP status and controls. If the run's restore checks flagged anything, say so; do not
   re-set controls without asking.

Plan and context: `research/usb_cameras/docs/capture_stack_options_plan.md` (section 6 is the test plan, section 8
Dom's decisions) and `research/usb_cameras/docs/windows_results_20261106.md` (the previous run, with the Kiyo
onsets in section 8).
