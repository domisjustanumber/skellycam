# install_winusb.ps1 - put Microsoft's INBOX WinUSB driver (%WINDIR%\INF\winusb.inf "WinUsb Device") on one or
# more UVC cameras so libusb / libuvc / python-libusb1 / pyuvc / uvc_iso can stream them from user space.
# Camera-agnostic successor of install_winusb_c930e.ps1 (which still works and is unchanged). ELEVATED.
# Undo: rollback_winusb.ps1.
#
# Launch from a normal shell (ONE UAC prompt for every device listed):
#   pwsh -File research/usb_cameras/libusb/winusb/run_elevated_winusb.ps1 -Action install -Device 046D:085C,4C4A:4A55
# or in an elevated PowerShell 7:
#   pwsh -File research/usb_cameras/libusb/winusb/install_winusb.ps1 -Device 046D:085C,4C4A:4A55 [-Target Parent|MI_00]
# Dry run (no admin needed, changes nothing; builds the inbox driver list for each target):
#   pwsh -File research/usb_cameras/libusb/winusb/install_winusb.ps1 -Device 046D:085C,4C4A:4A55 -DryRun
#
# Per device (-Device: VID:PID or instance id, repeatable or comma separated):
#   1. records the family state (parent + MI_xx: service, INF, provider, version, class, location) into the
#      per-device prestate store results/windows/<host>/winusb_multi/prestate.json, keyed by the parent instance
#      id. An existing entry is NOT overwritten when the target is already on WinUSB (re-running install must not
#      replace the real pre-state with the WinUSB state);
#   2. builds the inherited class driver list from winusb.inf (WinUsbInbox.cs) and installs "WinUsb Device" on the
#      target (Target=Parent, default: the composite parent; Target=MI_00: the video function + a
#      DeviceInterfaceGUIDs value + restart of that function, as in the C930e script);
#   3. records the post-state, reboot_required, and the per-device outcome.
# Each device is handled in its own try/catch, so one failure does not stop the next.
# Lessons from the C930e (results/windows/<host>/winusb_install): DiInstallDevice reported reboot_required=true and
# the parent showed WINUSB at once, but the MI_xx children stayed until the camera was physically replugged (same
# port). The camera's microphone function disappears while the parent is on WinUSB.
# Writes winusb_multi/install_result.json (or install_dryrun_result.json), install_<stamp>.log, install.done.
param(
  [Parameter(Mandatory)][string[]]$Device,
  [ValidateSet("Parent", "MI_00")][string]$Target = "Parent",
  [switch]$DryRun,
  [string]$OutDir
)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here "winusb_common.ps1")
if (-not $OutDir) { $OutDir = Get-WinUsbResultsDir $here }
New-Item -ItemType Directory -Force $OutDir | Out-Null
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$doneFile = Join-Path $OutDir $(if ($DryRun) { "install_dryrun.done" } else { "install.done" })
Start-Transcript -Path (Join-Path $OutDir "install_$(if ($DryRun) { 'dryrun_' })$stamp.log") | Out-Null
$specs = Split-DeviceSpecs $Device
$result = [ordered]@{ test = "winusb_install"; platform = "windows"; hostname = $env:COMPUTERNAME
  utc_started = (Get-Date).ToUniversalTime().ToString("o"); command = "install_winusb.ps1 -Device $($specs -join ',') -Target $Target$(if ($DryRun) { ' -DryRun' })"
  environment = [ordered]@{ os = [Environment]::OSVersion.VersionString; winusb_inf = "$env:WINDIR\INF\winusb.inf"; pwsh = "$($PSVersionTable.PSVersion)" }
  target = $Target; dry_run = [bool]$DryRun; is_admin = (Test-IsAdmin); devices = @() }
$preFile = Join-Path $OutDir "prestate.json"
try {
  if (-not $result.is_admin -and -not $DryRun) { throw "must run elevated (use run_elevated_winusb.ps1)" }
  Add-Type -TypeDefinition (Get-Content -Raw (Join-Path $here "WinUsbInbox.cs")) -Language CSharp
  $store = Read-Prestates $preFile
  foreach ($spec in $specs) {
    $r = [ordered]@{ spec = $spec }
    try {
      $parent = Resolve-ParentInstance $spec
      $r.parent_instance_id = $parent
      $r.vid_pid = Get-VidPidOf $parent
      $fam = Get-Family $parent
      $tgt = if ($Target -eq "Parent") { $parent } else {
        ($fam | Where-Object { $_.function -eq "MI_00" -and $_.present } | Select-Object -First 1).instance_id }
      if (-not $tgt) { throw "no present $Target function under $parent" }
      $r.target_instance_id = $tgt
      $r.prestate_functions = $fam
      $tgtSvc = Get-DevProp $tgt DEVPKEY_Device_Service
      $r.target_service_before = $tgtSvc
      $already = Test-ServiceEq $tgtSvc "WinUSB"
      $r.already_winusb = $already
      if ($already) {
        $r.prestate_entry = if ($store.devices.Contains($parent)) { "kept existing entry (target already on WinUSB)" } else { "MISSING: target already on WinUSB and no stored prestate" }
      } elseif (-not $DryRun) {
        $store.devices[$parent] = [ordered]@{ utc = (Get-Date).ToUniversalTime().ToString("o"); target = $Target; target_instance_id = $tgt
          parent_instance_id = $parent; vid_pid = $r.vid_pid; functions = $fam }
        $store | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 $preFile   # saved before any change
        $r.prestate_entry = "written"
      }
      $r.driver_list = @([WinUsbInbox]::ListDrivers($tgt))
      $offered = [bool]($r.driver_list -match '^inherit/class\|WinUsb Device\|')
      $r.winusb_device_offered = $offered
      if (-not $offered) { throw "inbox 'WinUsb Device' not offered for $tgt" }
      if ($DryRun) { $r.outcome = "dry-run: WinUsb Device selectable for $tgt; nothing changed" }
      elseif ($already) { $r.outcome = "OK: $tgt already on WinUSB (nothing installed)" }
      else {
        $reboot = $false
        $r.install_message = [WinUsbInbox]::Install($tgt, [ref]$reboot)
        $r.reboot_required = $reboot
        if ($Target -eq "MI_00") {
          # libusb finds WinUSB functions under usbccgp only via DeviceInterfaceGUIDs (libusb windows_winusb.c)
          $guid = "{" + [guid]::NewGuid().ToString() + "}"
          $key = "HKLM:\SYSTEM\CurrentControlSet\Enum\$tgt\Device Parameters"
          New-ItemProperty -Path $key -Name DeviceInterfaceGUIDs -PropertyType MultiString -Value @($guid) -Force | Out-Null
          $r.device_interface_guid = $guid
          $r.restart = (pnputil /restart-device "$tgt" | Out-String)
        }
        Start-Sleep -Seconds 3
        $r.poststate_functions = Get-Family $parent
        $svc = Get-DevProp $tgt DEVPKEY_Device_Service
        $r.target_service_after = $svc
        $r.target_inf_after = Get-DevProp $tgt DEVPKEY_Device_DriverInfPath
        $r.outcome = if (Test-ServiceEq $svc "WinUSB") { "OK: $tgt now on WinUSB" } else { "FAILED: service is '$svc'" }
      }
    } catch {
      $r.outcome = "ERROR: $($_.Exception.Message)"
      $r.error_detail = "$_"
    }
    Write-Host "$spec -> $($r.outcome)"
    $result.devices += $r
  }
  $outs = @($result.devices | ForEach-Object { "$($_.outcome)" })
  $result.outcome = if ($DryRun -and -not ($outs | Where-Object { $_ -notlike "dry-run*" })) { "dry-run: all $($outs.Count) device(s) OK" }
    elseif (-not ($outs | Where-Object { $_ -notlike "OK*" })) { "OK: $($outs.Count) device(s) on WinUSB" }
    else { "PARTIAL/FAILED: $($outs -join ' | ')" }
  if (-not $DryRun) {
    $result.next_step = "physically unplug and replug each camera INTO THE SAME PORT (a camera without a serial number, e.g. 4C4A:4A55, " +
      "gets a new devnode with its default driver on a different port), then run verify_winusb.ps1"
  }
} catch {
  $result.outcome = "ERROR: $($_.Exception.Message)"
  $result.error_detail = "$_"
} finally {
  $result.utc_finished = (Get-Date).ToUniversalTime().ToString("o")
  $name = if ($DryRun) { "install_dryrun_result.json" } else { "install_result.json" }
  $result | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 (Join-Path $OutDir $name)
  Write-Host $result.outcome
  Stop-Transcript | Out-Null
  "DONE" | Set-Content $doneFile
}
