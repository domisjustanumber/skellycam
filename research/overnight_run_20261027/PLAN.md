# Overnight plan, 2026-10-27 (set up at Dom's request ~18:30)

Dom's request: "When the computer is idle after 23:00 tonight, start a sub-agent to run all of the unattended camera
driver tests again. When that has completed, start another sub-agent to run all of the ring buffer tests again and
complete the work started in an earlier session."
Dom's setup notes: the Kiyo Pro is excluded (known flaky, not pointed at the screen). The C922, C930e and generic
camera face the monitor. Nothing touches the cameras between setup and 23:00.

S = C:\Users\Dom\AppData\Local\Temp\claude\c--Users-Dom-GitHub-freemocap-skellycam\7c9d3345-0e7f-4af6-bb14-20fd851edd1a\scratchpad\overnight
REPO = C:\Users\Dom\GitHub\freemocap\skellycam
Log every step (time + outcome) by appending to S\OVERNIGHT_LOG.md.

## Step 1: 23:02 (cron) arm the idle watcher
- Bash, run_in_background: `powershell -NoProfile -File "<S>/idle_watch.ps1"`
  (idle = no input for 15 min AND CPU < 25%; gives up at 06:00 and prints TIMEOUT). Do NOT pass -ExecutionPolicy Bypass
  (blocked; RemoteSigned already allows local scripts).
- End the turn and wait for its completion notification.

## Step 2: watcher exits
- TIMEOUT: don't start anything. Log it and stop.
- IDLE:
  1. Pre-flight (read-only): Get-PnpDevice -Class Camera,Image + DEVPKEY_Device_DevNodeStatus for the C922 (046D:085C),
     the C930e (046D:0843, instance ...8&39DEC205&1&0000) and the generic camera (4C4A:4A55). Log the status; DN_NEED_RESTART = 0x100.
     Never restart devices. If a camera is broken, still run (agents record it).
  2. Stop-Process LogiTuneAgent, LogiTune, RazerAppEngine if running (Dom approved closing processes; NOT services).
  3. Bash, run_in_background: `powershell -NoProfile -File "<S>/keep_display_awake.ps1"` (display stays on for the flash tests).
  4. Workflow({ scriptPath: "<REPO>\research\usb_cameras\overnight_rerun_workflow.js",
               args: { stamp: "20261027", scratch: "C:\Users\Dom\AppData\Local\Temp\claude\c--Users-Dom-GitHub-freemocap-skellycam\7c9d3345-0e7f-4af6-bb14-20fd851edd1a\scratchpad" } })
  5. Log the run id. End the turn and wait.

## Step 3: camera workflow completes (whatever its outcome)
1. Release the display: create the file S\stop_display_hold.
2. Check that no camera-test processes are left (camlock, python/uv/cargo started from research\usb_cameras). Stop leftovers.
3. Log the workflow's summary.
4. Workflow({ scriptPath: "<REPO>\benchmarks\frame_pipeline\study_state\overnight_workflow.js", args: { stamp: "20261027" } })
   (baseline re-run -> continue_workflow.js -> revise -> fill and audit the Claude Doc).
5. Log the run id. End the turn and wait.

## Step 4: ring buffer workflow completes
1. Log the summary.
2. Update the memories usb-camera-investigation and frame-ring-buffer-study (status, where the new results are).
3. Final chat message for Dom: both summaries, links (camera RERUN_20261027.md, ring buffer doc
   https://claude.ai/artifact/Cz1otkZxAjLTHfP1WeE9it), what failed, and what needs a human.

## Rules for the whole night
- Never SendMessage an agent running inside a workflow (it spawns a duplicate). To stop one, use TaskStop on the workflow.
- No UAC prompts, no driver changes, no device restarts, no git commits.
- If a workflow dies, resume it once with Workflow({scriptPath, resumeFromRunId}); if it fails again, log it and move on to the next step.
