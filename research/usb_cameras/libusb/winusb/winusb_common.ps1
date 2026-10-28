# winusb_common.ps1 - helpers dot-sourced by install_winusb.ps1 / rollback_winusb.ps1 / verify_winusb.ps1 /
# run_elevated_winusb.ps1 (camera-agnostic successors of the *_c930e.ps1 scripts). Read-only functions only;
# nothing here changes a driver.
#
# Device specs (parameter -Device, repeatable and/or comma separated):
#   VID:PID          e.g. 046D:085C   -> the present composite PARENT with that VID/PID (error if several are present)
#   <instance id>    e.g. USB\VID_4C4A&PID_4A55\7&7DCC7CE&0&3  (parent or MI_xx function instance id)
# A "family" is a parent plus its MI_xx functions (DEVPKEY_Device_Children of the parent, so stale non-present
# children of an older devnode are not mixed in). Functions are compared by their key ("parent" or "MI_xx"),
# never by exact child instance id: after pnputil /remove-device /subtree + /scan-devices the child ids are
# re-generated (C930e: 8&39DEC205&0&0000 -> 8&39DEC205&1&0000).

function Get-WinUsbResultsDir([string]$here, [string]$sub = "winusb_multi") {
  $d = [IO.Path]::GetFullPath((Join-Path $here "..\..\results\windows\$env:COMPUTERNAME\$sub"))
  New-Item -ItemType Directory -Force $d | Out-Null
  return $d
}

function Test-IsAdmin {
  ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Split-DeviceSpecs([string[]]$Device) {
  @($Device | ForEach-Object { "$_" -split "," } | ForEach-Object { $_.Trim().Trim('"').Trim("'") } | Where-Object { $_ })
}

function Get-FunctionKey([string]$id) {
  if ($id -match '&MI_([0-9A-Fa-f]{2})\\') { return "MI_$($Matches[1].ToUpper())" }
  return "parent"
}

function Get-VidPidOf([string]$id) {
  if ($id -match 'VID_([0-9A-Fa-f]{4})&PID_([0-9A-Fa-f]{4})') { return "$($Matches[1].ToUpper()):$($Matches[2].ToUpper())" }
  return $null
}

function Get-DevProp([string]$id, [string]$key) {
  (Get-PnpDeviceProperty -InstanceId $id -KeyName $key -ErrorAction SilentlyContinue).Data
}

function Get-DevState([string]$id) {
  $d = Get-PnpDevice -InstanceId $id -ErrorAction SilentlyContinue
  if (-not $d) { return $null }
  [ordered]@{ instance_id = $d.InstanceId; function = (Get-FunctionKey $d.InstanceId); present = [bool]$d.Present
    friendly = $d.FriendlyName; class = $d.Class; class_guid = "$($d.ClassGuid)"; status = "$($d.Status)"; problem = "$($d.Problem)"
    service = (Get-DevProp $id DEVPKEY_Device_Service); inf = (Get-DevProp $id DEVPKEY_Device_DriverInfPath)
    driver_provider = (Get-DevProp $id DEVPKEY_Device_DriverProvider); driver_version = (Get-DevProp $id DEVPKEY_Device_DriverVersion)
    location_paths = @(Get-DevProp $id DEVPKEY_Device_LocationPaths); parent = (Get-DevProp $id DEVPKEY_Device_Parent) }
}

# Parent instance id for a spec (VID:PID -> present parent; MI_xx id -> its parent; parent id -> itself).
function Resolve-ParentInstance([string]$spec) {
  if ($spec -match '^([0-9A-Fa-f]{4}):([0-9A-Fa-f]{4})$') {
    $pre = "USB\VID_$($Matches[1].ToUpper())&PID_$($Matches[2].ToUpper())\"
    $p = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId.ToUpper().StartsWith($pre) })
    if ($p.Count -eq 0) { throw "no present device $spec (expected a parent like $pre...)" }
    if ($p.Count -gt 1) { throw "several present devices match $spec ($(($p.InstanceId) -join ', ')); pass the instance id" }
    return $p[0].InstanceId
  }
  $d = Get-PnpDevice -InstanceId $spec -ErrorAction SilentlyContinue
  if (-not $d) { throw "instance id not found: $spec" }
  if ((Get-FunctionKey $d.InstanceId) -ne "parent") {
    $par = Get-DevProp $d.InstanceId DEVPKEY_Device_Parent
    if (-not $par) { throw "no parent for $spec" }
    return $par
  }
  return $d.InstanceId
}

# Parent + its current children (present or not, as recorded by PnP for this devnode).
function Get-Family([string]$parentId) {
  $rows = @()
  $p = Get-DevState $parentId
  if ($p) { $rows += $p }
  foreach ($c in @(Get-DevProp $parentId DEVPKEY_Device_Children)) { if ($c) { $s = Get-DevState $c; if ($s) { $rows += $s } } }
  # fall back to present MI_xx with the same VID/PID whose parent is this devnode (Children can be empty while
  # the devnode is being re-enumerated)
  if ($rows.Count -le 1) {
    $vp = Get-VidPidOf $parentId
    if ($vp) {
      $pre = "USB\VID_$($vp.Split(':')[0])&PID_$($vp.Split(':')[1])&MI_"
      foreach ($dev in @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId.ToUpper().StartsWith($pre) })) {
        $cid = $dev.InstanceId
        if ((Get-DevProp $cid DEVPKEY_Device_Parent) -eq $parentId -and -not ($rows | Where-Object { $_.instance_id -eq $cid })) {
          $rows += (Get-DevState $cid)
        }
      }
    }
  }
  return ,@($rows)
}

function Read-JsonFile([string]$path) {
  if (Test-Path $path) { return (Get-Content -Raw $path | ConvertFrom-Json -AsHashtable) }
  return $null
}

# Per-device prestate store: { "schema": 1, "devices": { "<parent instance id>": {...} } }
function Read-Prestates([string]$file) {
  $p = Read-JsonFile $file
  if (-not $p) { $p = [ordered]@{ schema = 1; devices = [ordered]@{} } }
  if (-not $p.devices) { $p.devices = [ordered]@{} }
  return $p
}

# Legacy C930e prestate (install_winusb_c930e.ps1) converted to one store entry, or $null.
function Read-LegacyPrestate([string]$here, [string]$parentId) {
  $f = [IO.Path]::GetFullPath((Join-Path $here "..\..\results\windows\$env:COMPUTERNAME\winusb_install\prestate.json"))
  $l = Read-JsonFile $f
  if (-not $l -or $l.parent_instance_id -ne $parentId) { return $null }
  [ordered]@{ utc = $l.utc; source = $f; target = $l.target; target_instance_id = $l.target_instance_id; parent_instance_id = $l.parent_instance_id
    vid_pid = (Get-VidPidOf $parentId)
    functions = @($l.devices | ForEach-Object { $_.function = (Get-FunctionKey $_.instance_id); $_ }) }
}

function Test-ServiceEq($a, $b) { return ("$a".ToLowerInvariant() -eq "$b".ToLowerInvariant()) }

# Compare a prestate function list with the current family by function key (parent / MI_xx), service and INF.
# Rows may lack "function"/"present" (legacy C930e prestate / rollback poststate): derived from instance_id, and
# rows without "present" count as present. Returns @{ mismatches; instance_id_changes; parent_service }.
function Compare-Family($preFunctions, $nowFamily) {
  $mm = @(); $idc = @()
  $now = @($nowFamily | ForEach-Object {
    $k = if ($_.function) { $_.function } else { Get-FunctionKey $_.instance_id }
    $pr = if ($null -ne $_.present) { [bool]$_.present } else { $true }
    [pscustomobject]@{ function = $k; present = $pr; instance_id = $_.instance_id; service = $_.service; inf = $_.inf } })
  foreach ($f in @($preFunctions)) {
    $key = if ($f.function) { $f.function } else { Get-FunctionKey $f.instance_id }
    $n = @($now | Where-Object { $_.function -eq $key -and $_.present }) | Select-Object -First 1
    if (-not $n) { $mm += "missing function ${key} (was $($f.instance_id), $($f.service) $($f.inf))"; continue }
    if ($n.instance_id -ne $f.instance_id) { $idc += "${key}: $($f.instance_id) -> $($n.instance_id)" }
    if (-not (Test-ServiceEq $n.service $f.service) -or -not (Test-ServiceEq $n.inf $f.inf)) {
      $mm += "${key}: service $($n.service) inf $($n.inf) (was $($f.service) $($f.inf))" }
  }
  if (-not @($preFunctions)) { $mm += "no prestate: cannot compare" }
  $ps = ($now | Where-Object { $_.function -eq "parent" -and $_.present } | Select-Object -First 1).service
  return [ordered]@{ mismatches = $mm; instance_id_changes = $idc; parent_service = $ps }
}
