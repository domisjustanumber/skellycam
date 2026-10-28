# persistence_test.ps1 - USER-RUN, interactive, resumable test: does a WinUSB binding made on one USB
# camera survive (a) replug on the same port, (b) a move to another port, (c) moving back, (d) a reboot,
# and what does restoring it take?  Records the driver bound to EVERY instance of the camera at each step
# (inspect_driver_state.ps1, read-only) and compares it with the documented prediction.
#
# Run from the repo root in a NORMAL (non-elevated) PowerShell 7, camera on the port you want as "port A":
#   pwsh -File research/usb_cameras/driver_swap/persistence_test.ps1 -New
# After the reboot step, log in and run the same command WITHOUT -New; it resumes the latest unfinished run:
#   pwsh -File research/usb_cameras/driver_swap/persistence_test.ps1
#
# UAC prompts: exactly two with the defaults (install at step 02, restore at step 08). Both come from
# research/usb_cameras/libusb/winusb/run_elevated.ps1 (install_winusb_c930e.ps1 / rollback_winusb_c930e.ps1,
# inbox winusb.inf on the composite parent, no certificate). Those scripts are C930e-specific today; for any
# other camera pass -InstallCmd / -RollbackCmd (e.g. the generalized scripts once they exist).
#
# Options:
#   -VidPid 046D:0843        camera model under test (exactly one unit present at the start)
#   -RestoreVia rollback_script | devmgr_rollback | devmgr_uninstall
#                            how step 08 restores: the rollback script (UAC), or YOU do it in Device Manager
#                            ("Roll Back Driver", or "Uninstall device" + tick "Attempt to remove the driver")
#                            and the script records what happened.
#   -FrameCheck              at baseline, after port move and after restore: grab 2 s from Media Foundation
#                            (bandwidth/build/mf_multi_open.exe) and list libusb devices (uvc_capture_test --list),
#                            both through tools/camlock.py. Off by default (no camera opened otherwise).
#   -ColdBoot                adds step 07: shut down with the camera UNPLUGGED, plug into port A after login.
#   -Recheck                 just take one more snapshot in the latest run (e.g. days later, after Windows Update).
#   -StopAfter 01_baseline   stop after the named step (01_baseline is read-only: used to self-test the harness).
# Output: results/windows/<host>/driver_swap/persistence/<stamp>/ (state.json, NN_<step>.json snapshots,
#   install/rollback logs, frame checks, summary.json, summary.txt).
param(
  [string]$VidPid = "046D:0843",
  [switch]$New,
  [string]$RunDir,
  [ValidateSet("rollback_script", "devmgr_rollback", "devmgr_uninstall")][string]$RestoreVia = "rollback_script",
  [string]$InstallCmd,
  [string]$RollbackCmd,
  [switch]$FrameCheck,
  [switch]$ColdBoot,
  [switch]$Recheck,
  [string]$StopAfter,
  [int]$ArrivalTimeoutS = 120
)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = [IO.Path]::GetFullPath((Join-Path $here "..\..\.."))
$uc = [IO.Path]::GetFullPath((Join-Path $here ".."))
$inspect = Join-Path $here "inspect_driver_state.ps1"
$winusbDir = Join-Path $uc "libusb\winusb"
$camlock = Join-Path $uc "tools\camlock.py"
$root = Join-Path $uc "results\windows\$env:COMPUTERNAME\driver_swap\persistence"
New-Item -ItemType Directory -Force $root | Out-Null
$v, $p = $VidPid.ToUpper().Split(":")
$prefix = "USB\VID_$v&PID_$p"
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdmin) { Write-Warning "Run this from a NORMAL shell; only the install/restore steps elevate (via UAC)." }
if (-not $InstallCmd) {
  if ($VidPid -ne "046D:0843") { throw "default install script is C930e-only; pass -InstallCmd/-RollbackCmd for $VidPid" }
  $InstallCmd = "pwsh -NoProfile -File `"$winusbDir\run_elevated.ps1`" -Action install -Target Parent"
}
if (-not $RollbackCmd) { $RollbackCmd = "pwsh -NoProfile -File `"$winusbDir\run_elevated.ps1`" -Action rollback" }

function NowU { (Get-Date).ToUniversalTime() }
function Save-State { $script:state | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 (Join-Path $script:RunDir "state.json") }
function Snap($name) {
  $f = Join-Path $script:RunDir "$name.json"
  & pwsh -NoProfile -File $inspect -VidPid $VidPid -Label $name -SinceUtc $script:state.created_utc -OutFile $f -Quiet | Out-Null
  Get-Content -Raw $f | ConvertFrom-Json
}
function Parents($snap) { @($snap.devices | Where-Object { $_.role -eq "parent" }) }
function PresentParent($snap) { @(Parents $snap | Where-Object { $_.present }) }
function Wait-Arrival([datetime]$afterUtc, [string]$why) {
  Write-Host "  waiting up to $ArrivalTimeoutS s for the camera to (re)enumerate ($why)..."
  $t0 = Get-Date
  while (((Get-Date) - $t0).TotalSeconds -lt $ArrivalTimeoutS) {
    $par = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -like "$prefix\*" })
    foreach ($d in $par) {
      $a = (Get-PnpDeviceProperty -InstanceId $d.InstanceId -KeyName DEVPKEY_Device_LastArrivalDate -ErrorAction SilentlyContinue).Data
      if ($a -and $a.ToUniversalTime() -ge $afterUtc.AddSeconds(-1)) {
        # settle: a NEW instance first gets a driver installed (about 2-3 s in setupapi.dev.log on this rig);
        # wait until the parent reports Status OK and its child count has been stable for 3 s (max 30 s).
        $t1 = Get-Date; $last = -1; $stable = Get-Date
        while (((Get-Date) - $t1).TotalSeconds -lt 30) {
          $st = "$((Get-PnpDevice -InstanceId $d.InstanceId -ErrorAction SilentlyContinue).Status)"
          $n = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -like "$prefix&MI_*" }).Count
          if ($n -ne $last) { $last = $n; $stable = Get-Date }
          if ($st -eq "OK" -and ((Get-Date) - $stable).TotalSeconds -ge 3) { break }
          Start-Sleep -Milliseconds 500
        }
        return [ordered]@{ arrived = $true; instance_id = $d.InstanceId; arrival_utc = $a.ToUniversalTime().ToString("o")
          seconds_after_prompt = [math]::Round(($a.ToUniversalTime() - $afterUtc).TotalSeconds, 1)
          settled_status = $st; present_functions = $last; settle_seconds = [math]::Round(((Get-Date) - $t1).TotalSeconds, 1) }
      }
    }
    Start-Sleep -Milliseconds 500
  }
  [ordered]@{ arrived = $false; note = "no re-enumeration seen within $ArrivalTimeoutS s (replug not done, or device never left?)" }
}
function Ask($msg) { Write-Host ""; Write-Host ">>> $msg" -ForegroundColor Yellow; Read-Host "    press Enter when done (or type a note)" }
function Run-Logged($name, [string]$cmd) {
  $log = Join-Path $script:RunDir "$name.log"
  $t = NowU
  $out = & pwsh -NoProfile -Command $cmd 2>&1 | Out-String
  $code = $LASTEXITCODE
  $out | Set-Content -Encoding utf8 $log
  [ordered]@{ command = $cmd; exit_code = $code; seconds = [math]::Round(((NowU) - $t).TotalSeconds, 1); log = $log }
}
function Frame-Check($name) {
  if (-not $FrameCheck) { return $null }
  $r = [ordered]@{}
  $mf = Join-Path $uc "bandwidth\build\mf_multi_open.exe"
  if (Test-Path $mf) {
    $o = Join-Path $script:RunDir "${name}_mf.txt"
    Push-Location $repo
    $oj = Join-Path $script:RunDir "${name}_mf.json"
    & uv run --script $camlock -- $mf --seconds 2 --cam "vid_$($v.ToLower())&pid_$($p.ToLower()):MJPG:640x480@30" --out $oj *> $o
    $r.mf_exit_code = $LASTEXITCODE; Pop-Location; $r.mf_output = $o; $r.mf_json = $oj
    $r.mf_streamed = ($r.mf_exit_code -eq 0)   # mf_multi_open: 0 = all cameras streamed, 2 = a camera failed
  } else { $r.mf = "not built: $mf" }
  $lu = Join-Path $uc "libusb\build\cmake\bin\Release\uvc_capture_test.exe"
  if (Test-Path $lu) {
    $o = Join-Path $script:RunDir "${name}_libusb_list.txt"
    Push-Location $repo
    & uv run --script $camlock -- $lu --list *> $o
    $r.libusb_list_exit_code = $LASTEXITCODE; Pop-Location; $r.libusb_list_output = $o
    $line = Select-String -Path $o -Pattern "^$($v.ToLower()):$($p.ToLower())\s" | Select-Object -First 1
    $r.libusb_line = if ($line) { $line.Line.Trim() } else { $null }
  } else { $r.libusb = "not built: $lu" }
  $r
}
# one row of the result table for this step
function Row($name, $snap, $expect, $extra) {
  $pp = PresentParent $snap
  $pa = $script:state.port_a_instance_id
  $cur = $pp | Select-Object -First 1
  $kids = if ($cur) { @($snap.devices | Where-Object { $_.present -and $_.parent -and $_.parent.ToUpper() -eq $cur.instance_id.ToUpper() }) } else { @() }
  $camIf = if ($cur) { [bool]($snap.camera_interfaces | Where-Object { $_.category -eq "KSCATEGORY_VIDEO_CAMERA" -and $_.status -eq "Enabled" -and ($kids.instance_id -contains $_.device_instance_id) }) } else { $false }
  $row = [ordered]@{
    step = $name; utc = $snap.utc_started; boot_time_utc = $snap.boot_time_utc
    present_parent = if ($cur) { $cur.instance_id } else { $null }; present_parents = $pp.Count
    same_instance_as_port_a = if ($cur -and $pa) { $cur.instance_id.ToUpper() -eq $pa.ToUpper() } else { $null }
    location = if ($cur) { $cur.location_info } else { $null }
    service = if ($cur) { $cur.service } else { $null }; inf = if ($cur) { $cur.inf } else { $null }
    rank = if ($cur) { $cur.driver_rank_hex } else { $null }; matching_id = if ($cur) { $cur.matching_device_id } else { $null }
    first_install_utc = if ($cur) { $cur.first_install_utc } else { $null }; last_arrival_utc = if ($cur) { $cur.last_arrival_utc } else { $null }
    present_children = @($kids | ForEach-Object { "$($_.role)=$($_.service)" })
    video_camera_interface_enabled = $camIf
    port_a_instance_service = (Parents $snap | Where-Object { $pa -and $_.instance_id.ToUpper() -eq $pa.ToUpper() } | Select-Object -First 1).service
    veto_events_225 = @($snap.pnp_veto_events_225).Count
    vendor_processes = @($snap.vendor_processes | ForEach-Object { $_.name }) -join ","
    expected = $expect
  }
  $ok = $true
  if ($expect.service) { $ok = $ok -and ("$($row.service)" -match "^(?i)$($expect.service)$") }
  if ($null -ne $expect.same_instance) { $ok = $ok -and ($row.same_instance_as_port_a -eq $expect.same_instance) }
  if ($null -ne $expect.camera_interface) { $ok = $ok -and ($row.video_camera_interface_enabled -eq $expect.camera_interface) }
  $row.matches_prediction = $ok
  if ($extra) { foreach ($k in $extra.Keys) { $row[$k] = $extra[$k] } }
  $row
}
function Record($name, $row) {
  $script:state.rows += $row
  $script:state.steps_done += $name
  Save-State
  $c = if ($row.matches_prediction) { "Green" } else { "Red" }
  Write-Host ("  [{0}] service={1} inf={2} instance={3} same_as_A={4} camera_if={5} -> {6}" -f $name, $row.service, $row.inf, $row.present_parent, $row.same_instance_as_port_a, $row.video_camera_interface_enabled, $(if ($row.matches_prediction) { "as predicted" } else { "DIFFERS from prediction" })) -ForegroundColor $c
}

# ---------------- run directory / state ----------------
if (-not $RunDir) {
  if (-not $New) {
    $RunDir = Get-ChildItem $root -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending |
      Where-Object { -not (Test-Path (Join-Path $_.FullName "summary.json")) -or $Recheck } | Select-Object -First 1 -ExpandProperty FullName
  }
  if (-not $RunDir) { $RunDir = Join-Path $root ((Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")); $New = $true }
}
New-Item -ItemType Directory -Force $RunDir | Out-Null
$sf = Join-Path $RunDir "state.json"
if (Test-Path $sf) { $state = Get-Content -Raw $sf | ConvertFrom-Json -AsHashtable }
else {
  $state = [ordered]@{ test = "winusb_persistence"; platform = "windows"; hostname = $env:COMPUTERNAME; vidpid = $VidPid
    created_utc = (NowU).ToString("o"); command = $MyInvocation.Line; restore_via = $RestoreVia; install_cmd = $InstallCmd
    rollback_cmd = $RollbackCmd; frame_check = [bool]$FrameCheck; cold_boot = [bool]$ColdBoot; steps_done = @(); rows = @(); notes = [ordered]@{} }
  Save-State
}
$state.steps_done = @($state.steps_done); $state.rows = @($state.rows)
function Done($n) {
  if ($StopAfter -and ($script:state.steps_done -contains $StopAfter)) { Write-Host "stopping after $StopAfter (-StopAfter)"; exit 0 }
  $script:state.steps_done -contains $n
}
Write-Host "run dir: $RunDir"

if ($Recheck) {
  $t = NowU; $s = Snap ("recheck_" + $t.ToString("yyyyMMddTHHmmssZ"))
  Record ("recheck_" + $t.ToString("yyyyMMddTHHmmssZ")) (Row "recheck" $s ([ordered]@{ note = "compare with the last row" }) $null)
  exit 0
}

# 01 baseline
if (-not (Done "01_baseline")) {
  $s = Snap "01_baseline"
  $pp = PresentParent $s
  if ($pp.Count -ne 1) { throw "need exactly one $VidPid plugged in at the start (found $($pp.Count))" }
  if ($pp[0].service -match '^(?i)winusb$') { throw "camera is already on WinUSB; restore it first (rollback_winusb_c930e.ps1)" }
  $state.port_a_instance_id = $pp[0].instance_id; $state.port_a_location = $pp[0].location_info
  $state.port_a_location_paths = $pp[0].location_paths
  $state.known_ports_before = @(Parents $s | ForEach-Object { [ordered]@{ instance_id = $_.instance_id; location = $_.location_info; present = $_.present; service = $_.service } })
  $fc = Frame-Check "01_baseline"
  Record "01_baseline" (Row "01_baseline" $s ([ordered]@{ service = "usbccgp"; same_instance = $true; camera_interface = $true }) ([ordered]@{ frame_check = $fc }))
  Write-Host "  port A = $($state.port_a_location)  ($($state.port_a_instance_id))"
  Write-Host "  instances of this model Windows already knows (each = one port it was plugged into):"
  $state.known_ports_before | ForEach-Object { Write-Host ("     {0,-28} {1,-10} present={2}  {3}" -f $_.location, $_.service, $_.present, $_.instance_id) }
  Save-State
}

# 02 install (UAC #1)
if (-not (Done "02_install")) {
  $vp = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match '^(LogiTune|LogiTuneAgent|RazerAppEngine|CameraHub|WindowsCamera|obs64|Zoom|ms-teams)$' } | ForEach-Object { $_.ProcessName })
  $vendorNote = $null
  if ($vp) {
    Write-Host "  processes that have held camera handles on this rig are running: $($vp -join ', ')"
    $vendorNote = Read-Host "    keep them running (tests the vetoed path: reboot_required, replug needed) or quit them now from their tray icons (tests the clean path)? type 'keep' or 'quit' and press Enter after doing it"
  }
  Write-Host ""; Write-Host ">>> step 02: installing WinUSB on port A's instance. Accept the UAC prompt." -ForegroundColor Yellow
  $r = Run-Logged "02_install" $InstallCmd
  $r.vendor_processes_before = $vp; $r.vendor_apps_choice = $vendorNote
  $ir = Join-Path $uc "results\windows\$env:COMPUTERNAME\winusb_install\install_result.json"
  if (Test-Path $ir) { Copy-Item $ir (Join-Path $RunDir "02_install_result.json") -Force; $j = Get-Content -Raw $ir | ConvertFrom-Json; $r.reboot_required = $j.reboot_required; $r.outcome = $j.outcome }
  Start-Sleep -Seconds 3
  $s = Snap "02_install"
  # prediction: registry/devnode now says WINUSB (Service is written immediately); whether the camera interface
  # is already gone depends on whether a handle-holder vetoed the stack restart (reboot_required).
  Record "02_install" (Row "02_install" $s ([ordered]@{ service = "winusb"; same_instance = $true }) ([ordered]@{ install = $r }))
}

# 03 replug, same port
if (-not (Done "03_replug_same_port")) {
  $t = NowU
  $note = Ask "step 03: UNPLUG the camera, wait 5 s, plug it back into the SAME port A ($($state.port_a_location))."
  $w = Wait-Arrival $t "replug same port"
  $s = Snap "03_replug_same_port"
  $rb = Read-Host "    optional: in Device Manager open the camera (now under 'Universal Serial Bus devices') > Properties > Driver. Is 'Roll Back Driver' clickable? [y/n/Enter=skip] (do NOT click it)"
  Record "03_replug_same_port" (Row "03_replug_same_port" $s ([ordered]@{ service = "winusb"; same_instance = $true; camera_interface = $false }) ([ordered]@{ wait = $w; user_note = $note; devmgr_roll_back_enabled = $rb }))
}

# 04 move to another port
if (-not (Done "04_move_port_b")) {
  $t = NowU
  Write-Host "  ports already known for this model (a port in this list re-uses its OLD instance and its old driver):"
  $state.known_ports_before | ForEach-Object { Write-Host ("     {0,-28} {1}" -f $_.location, $_.service) }
  $note = Ask "step 04: unplug and plug the camera into a DIFFERENT port B (preferably one NOT in the list above). Type the port you used (e.g. 'front-left USB-A, never used')."
  $w = Wait-Arrival $t "move to port B"
  $s = Snap "04_move_port_b"
  $fc = Frame-Check "04_move_port_b"
  $row = Row "04_move_port_b" $s ([ordered]@{ service = "usbccgp"; same_instance = $false; camera_interface = $true }) ([ordered]@{ wait = $w; user_note = $note; frame_check = $fc })
  $row.new_instance_created = [bool]($row.first_install_utc -and ([datetime]$row.first_install_utc).ToUniversalTime() -ge $t.AddSeconds(-1))
  Record "04_move_port_b" $row
}

# 05 back to port A
if (-not (Done "05_back_to_port_a")) {
  $t = NowU
  $note = Ask "step 05: move the camera BACK to port A ($($state.port_a_location))."
  $w = Wait-Arrival $t "back to port A"
  $s = Snap "05_back_to_port_a"
  Record "05_back_to_port_a" (Row "05_back_to_port_a" $s ([ordered]@{ service = "winusb"; same_instance = $true; camera_interface = $false }) ([ordered]@{ wait = $w; user_note = $note }))
}

# 06 warm reboot with the camera attached to port A
if (-not (Done "06_reboot")) {
  if (-not $state.notes.reboot_requested_utc) {
    $state.notes.reboot_requested_utc = (NowU).ToString("o"); Save-State
    Write-Host ""; Write-Host ">>> step 06: leave the camera on port A and RESTART Windows now. After logging in, run:" -ForegroundColor Yellow
    Write-Host "      pwsh -File research/usb_cameras/driver_swap/persistence_test.ps1"
    exit 0
  }
  $s = Snap "06_reboot"
  $rebooted = ([datetime]$s.boot_time_utc).ToUniversalTime() -gt ([datetime]$state.notes.reboot_requested_utc).ToUniversalTime()
  if (-not $rebooted) { Write-Warning "boot time $($s.boot_time_utc) is before the reboot request: Windows was NOT restarted. Restart, then rerun."; exit 1 }
  Record "06_reboot" (Row "06_reboot" $s ([ordered]@{ service = "winusb"; same_instance = $true; camera_interface = $false }) ([ordered]@{ rebooted = $rebooted }))
}

# 07 optional cold boot with the camera unplugged
if ($ColdBoot -and -not (Done "07_coldboot_unplugged")) {
  if (-not $state.notes.coldboot_requested_utc) {
    $state.notes.coldboot_requested_utc = (NowU).ToString("o"); Save-State
    Write-Host ">>> step 07: UNPLUG the camera, SHUT DOWN (not restart), power on, log in, plug the camera into port A, then rerun this script." -ForegroundColor Yellow
    exit 0
  }
  $t = NowU
  $w = Wait-Arrival ([datetime]$state.notes.coldboot_requested_utc).ToUniversalTime() "plug after cold boot"
  $s = Snap "07_coldboot_unplugged"
  Record "07_coldboot_unplugged" (Row "07_coldboot_unplugged" $s ([ordered]@{ service = "winusb"; same_instance = $true; camera_interface = $false }) ([ordered]@{ wait = $w }))
}

# 08 restore
if (-not (Done "08_restore")) {
  $extra = [ordered]@{ restore_via = $RestoreVia }
  switch ($RestoreVia) {
    "rollback_script" {
      Write-Host ">>> step 08: restoring with the rollback script. Accept the UAC prompt." -ForegroundColor Yellow
      $extra.rollback = Run-Logged "08_restore" $RollbackCmd
      $rr = Join-Path $uc "results\windows\$env:COMPUTERNAME\winusb_install\rollback_result.json"
      if (Test-Path $rr) { Copy-Item $rr (Join-Path $RunDir "08_rollback_result.json") -Force }
    }
    "devmgr_rollback" { $extra.user_note = Ask "step 08: Device Manager > Universal Serial Bus devices > the camera > Properties > Driver > 'Roll Back Driver'. Do it (admin prompt), then describe what happened." }
    "devmgr_uninstall" { $extra.user_note = Ask "step 08: Device Manager > the camera > Uninstall device, tick 'Attempt to remove the driver for this device' if offered, then Action > Scan for hardware changes. Describe what happened." }
  }
  Start-Sleep -Seconds 3
  $s = Snap "08_restore"
  Record "08_restore" (Row "08_restore" $s ([ordered]@{ service = "usbccgp" }) $extra)
}

# 09 replug after restore
if (-not (Done "09_post_restore_replug")) {
  $t = NowU
  $note = Ask "step 09: unplug and replug the camera on port A (checks that the restored driver persists and that MF gets frames)."
  $w = Wait-Arrival $t "replug after restore"
  $s = Snap "09_post_restore_replug"
  $fc = Frame-Check "09_post_restore_replug"
  Record "09_post_restore_replug" (Row "09_post_restore_replug" $s ([ordered]@{ service = "usbccgp"; same_instance = $true; camera_interface = $true }) ([ordered]@{ wait = $w; user_note = $note; frame_check = $fc }))
}

# summary
$sum = [ordered]@{ test = "winusb_persistence"; platform = "windows"; hostname = $env:COMPUTERNAME; vidpid = $VidPid
  utc_started = $state.created_utc; utc_finished = (NowU).ToString("o"); command = $state.command; restore_via = $state.restore_via
  port_a = $state.port_a_location; port_a_instance_id = $state.port_a_instance_id
  all_as_predicted = -not ($state.rows | Where-Object { -not $_.matches_prediction }); rows = $state.rows }
$sum | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 (Join-Path $RunDir "summary.json")
$txt = $state.rows | ForEach-Object { [pscustomobject]@{ step = $_.step; service = $_.service; inf = $_.inf; rank = $_.rank; same_as_A = $_.same_instance_as_port_a
    location = $_.location; cam_if = $_.video_camera_interface_enabled; vetoes = $_.veto_events_225; predicted = $_.matches_prediction } } | Format-Table -AutoSize | Out-String -Width 220
$txt | Set-Content -Encoding utf8 (Join-Path $RunDir "summary.txt")
Write-Host $txt
Write-Host "summary: $(Join-Path $RunDir 'summary.json')"
