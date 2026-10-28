# dryrun_winusb_driverlist.ps1 - READ-ONLY check that the inbox winusb.inf "WinUsb Device" driver
# can be selected for a given device instance (no admin, changes nothing, does not open the camera).
#
#   pwsh -File research/usb_cameras/libusb/winusb/dryrun_winusb_driverlist.ps1 [-InstanceId <id>]
# Default: every present USB\VID_046D&PID_0843* instance (C930e parent + MI_xx functions).
# Writes research/usb_cameras/results/windows/<host>/winusb_dryrun/result.json
param([string[]]$InstanceId)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Add-Type -TypeDefinition (Get-Content -Raw (Join-Path $here "WinUsbInbox.cs")) -Language CSharp
if (-not $InstanceId) {
  $InstanceId = @(Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'USB\VID_046D&PID_0843*' } | ForEach-Object InstanceId)
}
$rows = foreach ($id in $InstanceId) {
  $d = Get-PnpDevice -InstanceId $id
  $svc = (Get-PnpDeviceProperty -InstanceId $id -KeyName DEVPKEY_Device_Service -ErrorAction SilentlyContinue).Data
  $inf = (Get-PnpDeviceProperty -InstanceId $id -KeyName DEVPKEY_Device_DriverInfPath -ErrorAction SilentlyContinue).Data
  [ordered]@{
    instance_id = $id; friendly = $d.FriendlyName; class = $d.Class; status = "$($d.Status)"
    current_service = $svc; current_inf = $inf
    winusb_inf_driver_list = @([WinUsbInbox]::ListDrivers($id))
  }
}
$res = [ordered]@{
  test = "winusb_dryrun_driverlist"; platform = "windows"; hostname = $env:COMPUTERNAME
  utc_started = (Get-Date).ToUniversalTime().ToString("o")
  command = "pwsh -File research/usb_cameras/libusb/winusb/dryrun_winusb_driverlist.ps1"
  environment = @{ os = [Environment]::OSVersion.VersionString; winusb_inf = "$env:WINDIR\INF\winusb.inf"; is_admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) }
  set_level_winusb_inf_class_drivers = @([WinUsbInbox]::ListSetDrivers())
  cameras = @($rows)
}
$out = Join-Path $here "..\..\results\windows\$env:COMPUTERNAME\winusb_dryrun"
New-Item -ItemType Directory -Force $out | Out-Null
$res | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 (Join-Path $out "result.json")
$res | ConvertTo-Json -Depth 6
