# Read-only: DevNodeStatus / problem code / LastArrivalDate for the camera devnodes (Kiyo included: PnP property
# read only, nothing is sent to the device). DN_NEED_RESTART = 0x100. Also machine CPU load and vendor agents.
# Run (PowerShell, from repo root):
#   $Out = 'research/usb_cameras/results/windows/Gerald/naming_rerun_20261027/devnode_status_<when>.json'
#   . research/usb_cameras/results/windows/Gerald/naming_rerun_20261027/devnode_status.ps1
$rx = 'VID_(046D&PID_085C|046D&PID_0843|4C4A&PID_4A55|1532&PID_0E05)'
$rows = Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match $rx } | ForEach-Object {
  $id = $_.InstanceId
  $st = (Get-PnpDeviceProperty -InstanceId $id -KeyName DEVPKEY_Device_DevNodeStatus).Data
  $pc = (Get-PnpDeviceProperty -InstanceId $id -KeyName DEVPKEY_Device_ProblemCode).Data
  $la = (Get-PnpDeviceProperty -InstanceId $id -KeyName DEVPKEY_Device_LastArrivalDate).Data
  [pscustomobject]@{ instance_id=$id; friendly=$_.FriendlyName; status="$($_.Status)"; service=$_.Service
    devnode_status=('0x{0:x8}' -f $st); need_restart=[bool]($st -band 0x100); problem_code=$pc
    last_arrival_utc= if ($la) { $la.ToUniversalTime().ToString('o') } else { $null } }
}
$cpu = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
$res = [pscustomobject]@{ utc=(Get-Date).ToUniversalTime().ToString('o'); machine_cpu_load_percent=$cpu
  vendor_processes=@(Get-Process LogiTune*,Razer*,razer* -ErrorAction SilentlyContinue | Select-Object Name,Id); devnodes=$rows }
$res | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 $Out
$res.devnodes | Format-Table instance_id,devnode_status,need_restart,problem_code,last_arrival_utc -AutoSize | Out-String -Width 220
"cpu=$cpu"
