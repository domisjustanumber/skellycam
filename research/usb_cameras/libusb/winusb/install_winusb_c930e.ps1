# install_winusb_c930e.ps1 - PHASE 2 ONLY. Puts Microsoft's INBOX WinUSB driver on the Logitech C930e
# so libusb/libuvc/py-libusb1 can stream it from user space. ELEVATED. Undo: rollback_winusb_c930e.ps1.
#
# Launch (from a normal shell; the user clicks the UAC prompt; this script logs to a file):
#   pwsh -File research/usb_cameras/libusb/winusb/run_elevated.ps1 -Action install [-Target Parent|MI_00]
# or directly in an elevated PowerShell 7:
#   pwsh -File research/usb_cameras/libusb/winusb/install_winusb_c930e.ps1 [-Target Parent] [-DryRun]
#
# What it does (Target=Parent, the default):
#   1. records the pre-state of USB\VID_046D&PID_0843 (parent + MI_xx children: service, INF, class)
#      to results/windows/<host>/winusb_install/prestate.json (rollback reads it);
#   2. builds a driver list from %WINDIR%\INF\winusb.inf (inbox, Microsoft-signed) using the
#      SetupAPI "inherit class driver list" route (WinUsbInbox.cs; verified read-only by
#      dryrun_winusb_driverlist.ps1), selects "WinUsb Device" and calls DiInstallDevice on the
#      composite PARENT. No custom INF, no catalog, NO certificate is installed.
#   3. verifies DEVPKEY_Device_Service == WinUSB and writes install_result.json.
# Why the parent (see research notes in the phase-1 result): libusb's Windows backend enumerates a
# non-composite WinUSB device through GUID_DEVINTERFACE_USB_DEVICE (no DeviceInterfaceGUIDs needed),
# whereas a WinUSB *function* under usbccgp (MI_00) is only found through a DeviceInterfaceGUIDs
# registry value, which the generic inbox "WinUsb Device" install does not write. Side effect: the
# C930e microphone (MI_03, usbaudio) disappears until rollback.
# Target=MI_00 is provided for comparison: installs on the video function only and writes a
# DeviceInterfaceGUIDs value so libusb can find it (keeps the microphone).
param(
  [ValidateSet("Parent", "MI_00")][string]$Target = "Parent",
  [string]$InstanceId,
  [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$outDir = [IO.Path]::GetFullPath((Join-Path $here "..\..\results\windows\$env:COMPUTERNAME\winusb_install"))
New-Item -ItemType Directory -Force $outDir | Out-Null
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
Start-Transcript -Path (Join-Path $outDir "install_$stamp.log") | Out-Null
$result = [ordered]@{ test = "winusb_install_c930e"; platform = "windows"; hostname = $env:COMPUTERNAME
  utc_started = (Get-Date).ToUniversalTime().ToString("o"); command = $MyInvocation.Line; target = $Target; dry_run = [bool]$DryRun }
try {
  $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
  $result.is_admin = $isAdmin
  if (-not $isAdmin -and -not $DryRun) { throw "must run elevated (use run_elevated.ps1)" }
  Add-Type -TypeDefinition (Get-Content -Raw (Join-Path $here "WinUsbInbox.cs")) -Language CSharp

  function Get-State($id) {
    $d = Get-PnpDevice -InstanceId $id -ErrorAction SilentlyContinue
    if (-not $d) { return $null }
    [ordered]@{ instance_id = $id; friendly = $d.FriendlyName; class = $d.Class; class_guid = "$($d.ClassGuid)"; status = "$($d.Status)"
      problem = "$($d.Problem)"
      service = (Get-PnpDeviceProperty -InstanceId $id -KeyName DEVPKEY_Device_Service -ErrorAction SilentlyContinue).Data
      inf = (Get-PnpDeviceProperty -InstanceId $id -KeyName DEVPKEY_Device_DriverInfPath -ErrorAction SilentlyContinue).Data
      driver_provider = (Get-PnpDeviceProperty -InstanceId $id -KeyName DEVPKEY_Device_DriverProvider -ErrorAction SilentlyContinue).Data
      driver_version = (Get-PnpDeviceProperty -InstanceId $id -KeyName DEVPKEY_Device_DriverVersion -ErrorAction SilentlyContinue).Data }
  }
  $all = @(Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'USB\VID_046D&PID_0843*' })
  if (-not $all) { throw "C930e (USB\VID_046D&PID_0843) not present" }
  $parent = ($all | Where-Object { $_.InstanceId -notlike '*&MI_*' } | Select-Object -First 1).InstanceId
  $mi00 = ($all | Where-Object { $_.InstanceId -like '*&MI_00\*' } | Select-Object -First 1).InstanceId
  if (-not $InstanceId) { $InstanceId = if ($Target -eq "Parent") { $parent } else { $mi00 } }
  $result.instance_id = $InstanceId
  $pre = [ordered]@{ utc = (Get-Date).ToUniversalTime().ToString("o"); target = $Target; target_instance_id = $InstanceId
    parent_instance_id = $parent; devices = @($all | ForEach-Object { Get-State $_.InstanceId }) }
  $result.prestate = $pre
  if (-not $DryRun) { $pre | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $outDir "prestate.json") }

  $result.driver_list = @([WinUsbInbox]::ListDrivers($InstanceId))
  if (-not ($result.driver_list -match '^inherit/class\|WinUsb Device\|')) { throw "inbox 'WinUsb Device' not offered for $InstanceId" }
  if ($DryRun) { $result.outcome = "dry-run: WinUsb Device selectable; nothing changed" }
  else {
    $reboot = $false
    $result.install_message = [WinUsbInbox]::Install($InstanceId, [ref]$reboot)
    $result.reboot_required = $reboot
    if ($Target -eq "MI_00") {
      # libusb finds WinUSB functions under usbccgp only via DeviceInterfaceGUIDs (libusb windows_winusb.c get_guid)
      $guid = "{" + [guid]::NewGuid().ToString() + "}"
      $key = "HKLM:\SYSTEM\CurrentControlSet\Enum\$InstanceId\Device Parameters"
      New-ItemProperty -Path $key -Name DeviceInterfaceGUIDs -PropertyType MultiString -Value @($guid) -Force | Out-Null
      $result.device_interface_guid = $guid
      pnputil /restart-device "$InstanceId" | Out-String | ForEach-Object { $result.restart = $_ }
    }
    Start-Sleep -Seconds 3
    $result.poststate = @(@(Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'USB\VID_046D&PID_0843*' }) | ForEach-Object { Get-State $_.InstanceId })
    $svc = (Get-PnpDeviceProperty -InstanceId $InstanceId -KeyName DEVPKEY_Device_Service).Data
    $result.target_service_after = $svc
    $result.outcome = if ($svc -eq "WinUSB") { "OK: $InstanceId now on WinUSB" } else { "FAILED: service is '$svc'" }
  }
} catch {
  $result.outcome = "ERROR: $($_.Exception.Message)"
  $result.error_detail = "$_"
} finally {
  $result.utc_finished = (Get-Date).ToUniversalTime().ToString("o")
  $name = if ($DryRun) { "install_dryrun_result.json" } else { "install_result.json" }
  $result | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 (Join-Path $outDir $name)
  Write-Host $result.outcome
  Stop-Transcript | Out-Null
  "DONE" | Set-Content (Join-Path $outDir "install.done")
}
