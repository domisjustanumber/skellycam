# inspect_driver_state.ps1 - READ-ONLY snapshot of which driver each instance of a USB camera is bound to.
# No admin. No UAC. Does not open cameras, change drivers, write the registry or restart devices.
#
#   pwsh -File research/usb_cameras/driver_swap/inspect_driver_state.ps1 [-VidPid 046D:0843,046D:085C]
#        [-Label baseline] [-SinceUtc 2026-10-25T20:00:00Z] [-OutFile <path.json>]
#
# For every device instance (present AND phantom/non-present) whose instance id starts with
# USB\VID_vvvv&PID_pppp (composite parent and MI_xx children) it records:
#   service, INF, INF section, matching device id, driver rank (hex), provider/version/date,
#   class, status/problem, location (port) info, parent, container id,
#   first-install / install / last-arrival / last-removal dates (an arrival date that moves = a re-enumeration),
#   hardware + compatible ids and the ranked list of matching drivers (pnputil /drivers /format xml),
#   Enum registry values Driver/ConfigFlags and whether Device Parameters has DeviceInterfaceGUIDs.
# Plus, machine-wide:
#   driver-store INFs (C:\Windows\INF\oem*.inf) that name the VID/PID (who could win a re-rank),
#   KSCATEGORY_VIDEO_CAMERA / KSCATEGORY_CAPTURE interfaces of these devices (what Media Foundation / DirectShow can see),
#   HKLM\...\usbflags\vvvvpppprrrr (osvc = MS OS descriptor probe result, IgnoreHWSerNum),
#   setupapi.dev.log sections about these devices since -SinceUtc, Kernel-PnP event 225 (removal vetoes)
#   and vendor processes known to hold camera handles, boot time, Windows Update driver policy.
# Writes JSON (default results/windows/<host>/driver_swap/inspect/<stamp>_<label>.json) and prints a table.
param(
  [string[]]$VidPid = @("046D:0843", "046D:085C", "1532:0E05", "4C4A:4A55"),
  [string]$Label = "snapshot",
  [string]$SinceUtc,
  [string]$OutFile,
  [switch]$Quiet
)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
if (-not $OutFile) {
  $OutFile = [IO.Path]::GetFullPath((Join-Path $here "..\results\windows\$env:COMPUTERNAME\driver_swap\inspect\${stamp}_$Label.json"))
}
New-Item -ItemType Directory -Force (Split-Path -Parent $OutFile) | Out-Null
$since = if ($SinceUtc) { [datetime]::Parse($SinceUtc).ToUniversalTime() } else { (Get-Date).ToUniversalTime().AddHours(-6) }

function U($v) { if ($v -is [datetime]) { $v.ToUniversalTime().ToString("o") } else { $v } }
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$os = Get-CimInstance Win32_OperatingSystem
$res = [ordered]@{
  test = "driver_state_inspect"; label = $Label; platform = "windows"; hostname = $env:COMPUTERNAME
  utc_started = (Get-Date).ToUniversalTime().ToString("o"); command = $MyInvocation.Line
  environment = [ordered]@{ os_caption = $os.Caption; os_build = "$($os.Version) (UBR $((Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').UBR))"
    pwsh = "$($PSVersionTable.PSVersion)"; is_admin = $isAdmin }
  boot_time_utc = U $os.LastBootUpTime
  since_utc = $since.ToString("o"); vidpid = $VidPid
  cameras = @(); devices = @(); driver_store = @(); camera_interfaces = @(); usbflags = @()
  setupapi_sections = @(); pnp_veto_events_225 = @(); vendor_processes = @(); windows_update_policy = [ordered]@{}
}

$keys = @("DEVPKEY_Device_Service", "DEVPKEY_Device_DriverInfPath", "DEVPKEY_Device_DriverInfSection", "DEVPKEY_Device_MatchingDeviceId",
  "DEVPKEY_Device_DriverRank", "DEVPKEY_Device_DriverProvider", "DEVPKEY_Device_DriverVersion", "DEVPKEY_Device_DriverDate",
  "DEVPKEY_Device_LocationInfo", "DEVPKEY_Device_LocationPaths", "DEVPKEY_Device_Parent", "DEVPKEY_Device_ContainerId",
  "DEVPKEY_Device_FirstInstallDate", "DEVPKEY_Device_InstallDate", "DEVPKEY_Device_LastArrivalDate", "DEVPKEY_Device_LastRemovalDate",
  "DEVPKEY_Device_IsPresent", "DEVPKEY_Device_ProblemCode", "DEVPKEY_Device_DevNodeStatus", "DEVPKEY_Device_Driver")

function Get-MatchingDrivers($id) {
  try {
    [xml]$x = (pnputil /enum-devices /instanceid "$id" /drivers /ids /format xml 2>$null) -join "`n"
    $d = $x.PnpUtil.Device
    if (-not $d) { return $null }
    [ordered]@{
      hardware_ids = @($d.HardwareIds.HardwareId); compatible_ids = @($d.CompatibleIds.CompatibleId); pnputil_status = $d.Status
      matching_drivers = @($d.MatchingDrivers.DriverName | Where-Object { $_ } | ForEach-Object {
          [ordered]@{ inf = $_.DriverName; original = $_.OriginalName; provider = $_.ProviderName; class = $_.ClassName
            version = $_.DriverVersion; signer = $_.SignerName; matching_id = $_.MatchingDeviceId; rank = $_.Rank; status = $_.Status } })
    }
  } catch { [ordered]@{ error = "$_" } }
}

foreach ($vp in $VidPid) {
  $v, $p = $vp.ToUpper().Split(":")
  $prefix = "USB\VID_$v&PID_$p"
  $inst = @(Get-PnpDevice -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -like "$prefix\*" -or $_.InstanceId -like "$prefix&MI_*" })
  foreach ($d in $inst) {
    $id = $d.InstanceId
    $props = @{}
    Get-PnpDeviceProperty -InstanceId $id -KeyName $keys -ErrorAction SilentlyContinue | ForEach-Object { $props[$_.KeyName] = $_.Data }
    $reg = [ordered]@{}
    try {
      $rk = Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Enum\$id" -ErrorAction Stop
      $reg.driver_key = $rk.Driver; $reg.config_flags = $rk.ConfigFlags; $reg.service = $rk.Service
      $dp = Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Enum\$id\Device Parameters" -ErrorAction SilentlyContinue
      $reg.device_interface_guids = if ($dp) { @($dp.DeviceInterfaceGUIDs) + @($dp.DeviceInterfaceGUID) | Where-Object { $_ } } else { @() }
    } catch { $reg.error = "$($_.Exception.Message)" }
    $rank = $props["DEVPKEY_Device_DriverRank"]
    $entry = [ordered]@{
      vidpid = "$v`:$p"; instance_id = $id; role = if ($id -like "*&MI_*") { "function " + ($id -replace '^.*&(MI_[0-9A-F]{2}).*$', '$1') } else { "parent" }
      present = [bool]$props["DEVPKEY_Device_IsPresent"]; status = "$($d.Status)"; problem = $props["DEVPKEY_Device_ProblemCode"]
      devnode_status_hex = if ($null -ne $props["DEVPKEY_Device_DevNodeStatus"]) { "0x{0:X8}" -f [uint32]$props["DEVPKEY_Device_DevNodeStatus"] } else { $null }
      friendly = $d.FriendlyName; class = $d.Class; class_guid = "$($d.ClassGuid)"
      service = $props["DEVPKEY_Device_Service"]; inf = $props["DEVPKEY_Device_DriverInfPath"]; inf_section = $props["DEVPKEY_Device_DriverInfSection"]
      matching_device_id = $props["DEVPKEY_Device_MatchingDeviceId"]
      driver_rank_hex = if ($null -ne $rank) { "{0:X8}" -f [uint32]$rank } else { $null }
      driver_provider = $props["DEVPKEY_Device_DriverProvider"]; driver_version = $props["DEVPKEY_Device_DriverVersion"]; driver_date = U $props["DEVPKEY_Device_DriverDate"]
      location_info = $props["DEVPKEY_Device_LocationInfo"]; location_paths = @($props["DEVPKEY_Device_LocationPaths"]); parent = $props["DEVPKEY_Device_Parent"]
      container_id = "$($props["DEVPKEY_Device_ContainerId"])"
      first_install_utc = U $props["DEVPKEY_Device_FirstInstallDate"]; install_utc = U $props["DEVPKEY_Device_InstallDate"]
      last_arrival_utc = U $props["DEVPKEY_Device_LastArrivalDate"]; last_removal_utc = U $props["DEVPKEY_Device_LastRemovalDate"]
      registry = $reg
    }
    if ($entry.role -eq "parent" -or $entry.present) { $entry.pnputil = Get-MatchingDrivers $id }
    $res.devices += $entry
  }
  # driver-store packages that name this VID/PID (any of them could win a later re-rank)
  Get-ChildItem "$env:WINDIR\INF\oem*.inf" -ErrorAction SilentlyContinue | ForEach-Object {
    $hit = Select-String -Path $_.FullName -Pattern "VID_$v&PID_$p" -SimpleMatch -List -ErrorAction SilentlyContinue
    if ($hit) {
      $txt = Get-Content -Raw $_.FullName -ErrorAction SilentlyContinue
      $res.driver_store += [ordered]@{ vidpid = "$v`:$p"; published = $_.Name
        provider = ([regex]::Match($txt, '(?im)^\s*Provider\s*=\s*([^\r\n]+)').Groups[1].Value.Trim())
        driver_ver = ([regex]::Match($txt, '(?im)^\s*DriverVer\s*=\s*([^\r\n]+)').Groups[1].Value.Trim())
        class = ([regex]::Match($txt, '(?im)^\s*Class\s*=\s*([^\r\n]+)').Groups[1].Value.Trim())
        includes_winusb = [bool]($txt -match '(?i)Include\s*=\s*winusb\.inf')
        model_lines = @([regex]::Matches($txt, "(?im)^[^;\r\n]*VID_$v&PID_$p[^\r\n]*") | ForEach-Object { $_.Value.Trim() } | Select-Object -First 8) }
    }
  }
  Get-ChildItem "HKLM:\SYSTEM\CurrentControlSet\Control\usbflags" -ErrorAction SilentlyContinue | Where-Object { $_.PSChildName -like "$v$p*" } | ForEach-Object {
    $ip = Get-ItemProperty $_.PSPath
    $res.usbflags += [ordered]@{ key = $_.PSChildName; osvc = if ($ip.osvc) { ($ip.osvc | ForEach-Object { "{0:X2}" -f $_ }) -join "" } else { $null }
      ignore_hw_sernum = $ip.IgnoreHWSerNum }
  }
}
$usbflagsRoot = Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\usbflags" -ErrorAction SilentlyContinue
if ($usbflagsRoot) {
  $res.usbflags_ignore_hw_sernum_values = @($usbflagsRoot.PSObject.Properties | Where-Object { $_.Name -like "IgnoreHWSerNum*" } | ForEach-Object { $_.Name })
}

# what MF / DirectShow can enumerate: camera + capture category interfaces of these devices
foreach ($cat in @(@{n = "KSCATEGORY_VIDEO_CAMERA"; g = "{E5323777-F976-4F5B-9B55-B94699C46E44}" }, @{n = "KSCATEGORY_CAPTURE"; g = "{65E8773D-8F56-11D0-A3B9-00A0C9223196}" })) {
  try {
    [xml]$x = (pnputil /enum-interfaces /class $cat.g /format xml 2>$null) -join "`n"
    foreach ($i in @($x.PnpUtil.Interface)) {
      if (-not $i) { continue }
      $did = "$($i.DeviceInstanceId)"
      if ($VidPid | Where-Object { $a, $b = $_.ToUpper().Split(":"); $did.ToUpper() -like "USB\VID_$a&PID_$b*" }) {
        $res.camera_interfaces += [ordered]@{ category = $cat.n; device_instance_id = $did; status = "$($i.Status)"; path = "$($i.Path)" }
      }
    }
  } catch { $res.camera_interfaces += [ordered]@{ category = $cat.n; error = "$_" } }
}

# setupapi.dev.log sections mentioning these devices since $since (local timestamps in the log)
try {
  $log = Get-Content "$env:WINDIR\INF\setupapi.dev.log" -ErrorAction Stop
  $pat = ($VidPid | ForEach-Object { $a, $b = $_.ToUpper().Split(":"); [regex]::Escape("VID_$a&PID_$b") }) -join "|"
  $cur = $null
  for ($n = 0; $n -lt $log.Count; $n++) {
    $line = $log[$n]
    if ($line.StartsWith(">>>  [")) { $cur = [ordered]@{ title = $line.Substring(5).Trim(); line = $n + 1; start_local = $null; key_lines = @() }; continue }
    if ($cur -and $line.StartsWith(">>>  Section start ")) {
      $t = [datetime]::ParseExact($line.Substring(19).Trim(), "yyyy/MM/dd HH:mm:ss.fff", $null)
      $cur.start_local = $t.ToString("s"); $cur.start_utc = $t.ToUniversalTime().ToString("o"); continue
    }
    if ($cur -and $line -match '(?i)Strong Name=|vetoed|required reboot|force-install|Selected driver|Driver INF  |Install needed|Removing device|problem code|Exit status|cmd:') {
      if ($cur.key_lines.Count -lt 25) { $cur.key_lines += $line.Trim() }
    }
    if ($cur -and $line.StartsWith("<<<  [Exit status")) {
      if ($cur.title -match $pat -and $cur.start_utc -and ([datetime]$cur.start_utc).ToUniversalTime() -ge $since) { $res.setupapi_sections += $cur }
      $cur = $null
    }
  }
} catch { $res.setupapi_error = "$($_.Exception.Message)" }

try {
  $ev = Get-WinEvent -FilterHashtable @{ LogName = "System"; ProviderName = "Microsoft-Windows-Kernel-PnP"; Id = 225; StartTime = $since.ToLocalTime() } -ErrorAction Stop
  $res.pnp_veto_events_225 = @($ev | ForEach-Object { [ordered]@{ utc = U $_.TimeCreated; message = ($_.Message -replace '\s+', ' ') } })
} catch { $res.pnp_veto_events_225 = @() }

$res.vendor_processes = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match '^(LogiTune|LogiTuneAgent|logioptionsplus_agent|LogiCapture|LogiOverlay|RazerAppEngine|Razer.*|Synapse.*|CameraHub|WindowsCamera|obs64|Zoom|ms-teams|Teams)$' } |
  ForEach-Object { [ordered]@{ name = $_.ProcessName; pid = $_.Id; path = $_.Path } })
$fs = Get-Service FrameServer -ErrorAction SilentlyContinue
$res.frame_server = if ($fs) { "$($fs.Status)" } else { $null }
foreach ($k in @(@{p = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate"; v = "ExcludeWUDriversInQualityUpdate" },
    @{p = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\DriverSearching"; v = "SearchOrderConfig" })) {
  $val = (Get-ItemProperty $k.p -ErrorAction SilentlyContinue).($k.v)
  $res.windows_update_policy[$k.v] = $val
}

# cameras summary: one row per physical camera = per parent instance
$res.cameras = @($res.devices | Where-Object { $_.role -eq "parent" } | ForEach-Object {
    $par = $_
    $kids = @($res.devices | Where-Object { $_.parent -and $_.parent.ToUpper() -eq $par.instance_id.ToUpper() })
    [ordered]@{ vidpid = $par.vidpid; parent_instance_id = $par.instance_id; present = $par.present; location_info = $par.location_info
      parent_service = $par.service; parent_inf = $par.inf; parent_rank = $par.driver_rank_hex
      children = @($kids | ForEach-Object { "$($_.role)=$($_.service)/$($_.inf)$(if (-not $_.present) {' (not present)'})" })
      camera_interface_enabled = [bool]($res.camera_interfaces | Where-Object { $_.status -eq "Enabled" -and ($kids.instance_id -contains $_.device_instance_id -or $_.device_instance_id -eq $par.instance_id) })
      binding = if ($par.service -match '^(?i)winusb$') { "WINUSB" } elseif ($par.service -match '^(?i)usbccgp$') { "COMPOSITE(usbccgp->usbvideo)" } else { "$($par.service)" } }
  })
$res.utc_finished = (Get-Date).ToUniversalTime().ToString("o")
$res | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 $OutFile
if (-not $Quiet) {
  $res.cameras | ForEach-Object { [pscustomobject]$_ } | Format-Table vidpid, present, location_info, binding, parent_inf, parent_rank, camera_interface_enabled, parent_instance_id -AutoSize | Out-String -Width 250 | Write-Host
  Write-Host "wrote $OutFile"
}
$OutFile
