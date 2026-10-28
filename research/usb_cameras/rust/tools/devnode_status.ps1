# Records PnP devnode status for every present USB camera-related devnode (VID_1532/VID_046D or class Camera/Image/MEDIA),
# decoding DN_NEED_RESTART (= DN_LIAR = 0x00000100 per Windows SDK shared/cfg.h; 0x01000000 is DN_NT_DRIVER) — the state that makes Media Foundation return MF_E_REBOOT_REQUIRED (0xC00D7167).
# Also captures recent Kernel-PnP 225 (removal vetoed) events. Read-only; no elevation needed.
#   pwsh -File research/usb_cameras/rust/tools/devnode_status.ps1 [-Out <dir>]
param([string]$Out = "")
$hostName = (hostname)
if (-not $Out) { $Out = Join-Path $PSScriptRoot "..\..\results\windows\$hostName\rust_devnode_status\$((Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ'))" }
New-Item -ItemType Directory -Force $Out | Out-Null
$devs = Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match '^USB\\' -and ($_.Class -in @('Camera','Image','MEDIA','USB') ) -and ($_.InstanceId -match 'VID_1532|VID_046D') }
$rows = foreach ($d in $devs) {
  $st = (Get-PnpDeviceProperty -InstanceId $d.InstanceId -KeyName DEVPKEY_Device_DevNodeStatus -ErrorAction SilentlyContinue).Data
  [pscustomobject]@{ instance_id = $d.InstanceId; class = $d.Class; name = $d.FriendlyName; status = $d.Status;
    devnode_status_hex = ('0x{0:X8}' -f [uint32]$st); dn_need_restart = ((([uint32]$st) -band 0x00000100) -ne 0);
    problem = (Get-PnpDeviceProperty -InstanceId $d.InstanceId -KeyName DEVPKEY_Device_ProblemCode -ErrorAction SilentlyContinue).Data }
}
$ev = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-Kernel-PnP'; Id=225; StartTime=(Get-Date).AddHours(-6)} -ErrorAction SilentlyContinue |
  Select-Object -First 40 @{n='time';e={$_.TimeCreated.ToUniversalTime().ToString('o')}}, @{n='message';e={$_.Message}}
$res = [pscustomobject]@{ test = 'rust_devnode_status'; platform = 'windows'; hostname = $hostName;
  utc_started = (Get-Date).ToUniversalTime().ToString('o'); command = $MyInvocation.Line;
  environment = @{ os_build = [System.Environment]::OSVersion.VersionString };
  devnodes = @($rows); pnp_225_removal_vetoed_last6h = @($ev) }
$res | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $Out 'summary.json')
Write-Output (Join-Path $Out 'summary.json')
