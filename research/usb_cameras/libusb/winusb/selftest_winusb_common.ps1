# selftest_winusb_common.ps1 - offline test of the rollback post-check (Compare-Family in winusb_common.ps1) on the
# REAL C930e data: results/windows/<host>/winusb_install/{prestate.json, rollback_result.json, install_result.json}.
# No admin, no device access.  pwsh -File research/usb_cameras/libusb/winusb/selftest_winusb_common.ps1
# Writes results/windows/<host>/winusb_multi/selftest_compare_family.json; exit 0 if every case passes.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here "winusb_common.ps1")
$src = [IO.Path]::GetFullPath((Join-Path $here "..\..\results\windows\$env:COMPUTERNAME\winusb_install"))
$pre = Read-JsonFile (Join-Path $src "prestate.json")
$rb = Read-JsonFile (Join-Path $src "rollback_result.json")
$inst = Read-JsonFile (Join-Path $src "install_result.json")
$cases = @()
function Case($name, $expect, $got, $pass) { $script:cases += [ordered]@{ case = $name; expect = $expect; got = $got; pass = [bool]$pass } }

# 1. the real C930e rollback: children re-generated (&0& -> &1&), drivers identical -> no mismatch (the old
#    exact-instance-id check reported 2x 'missing' here: rollback_result.json "mismatches")
$c = Compare-Family $pre.devices $rb.poststate
Case "c930e_real_rollback" "0 mismatches, 2 instance id changes, parent usbccgp; old check reported $(@($rb.mismatches).Count) missing" $c `
  ($c.mismatches.Count -eq 0 -and $c.instance_id_changes.Count -eq 2 -and $c.parent_service -eq "usbccgp")
# 2. install poststate (parent WINUSB, children still listed until replug) -> parent mismatch only
$c = Compare-Family $pre.devices $inst.poststate
Case "c930e_after_install_before_replug" "1 mismatch (parent service WINUSB inf winusb.inf)" $c `
  ($c.mismatches.Count -eq 1 -and $c.mismatches[0] -like "parent: service WINUSB*" -and $c.parent_service -eq "WINUSB")
# 3. after install + replug: only the WinUSB parent is present -> parent mismatch + MI_00 and MI_03 missing
$parentOnly = @($inst.poststate | Where-Object { (Get-FunctionKey $_.instance_id) -eq "parent" })
$c = Compare-Family $pre.devices $parentOnly
Case "c930e_after_install_replugged" "3 mismatches (parent service, MI_00 missing, MI_03 missing)" $c `
  ($c.mismatches.Count -eq 3 -and ($c.mismatches -match "missing function MI_00").Count -eq 1 -and ($c.mismatches -match "missing function MI_03").Count -eq 1)
# 4. a child back on a different INF (e.g. inbox usbvideo.inf instead of Logitech oem11.inf) is a mismatch
$alt = @($rb.poststate | ForEach-Object { $h = [ordered]@{} + $_; if ((Get-FunctionKey $h.instance_id) -eq "MI_00") { $h.inf = "usbvideo.inf" }; $h })
$c = Compare-Family $pre.devices $alt
Case "c930e_child_inf_changed" "1 mismatch on MI_00 inf" $c ($c.mismatches.Count -eq 1 -and $c.mismatches[0] -like "MI_00:*usbvideo.inf*oem11.inf*")
# 5. a child present but non-present flag -> missing
$np = @($rb.poststate | ForEach-Object { $h = [ordered]@{} + $_; if ((Get-FunctionKey $h.instance_id) -eq "MI_03") { $h.present = $false }; $h })
$c = Compare-Family $pre.devices $np
Case "c930e_child_not_present" "1 mismatch: MI_03 missing" $c ($c.mismatches.Count -eq 1 -and $c.mismatches[0] -like "missing function MI_03*")
# 6. empty prestate -> cannot compare
$c = Compare-Family @() $rb.poststate
Case "no_prestate" "1 mismatch 'no prestate'" $c ($c.mismatches.Count -eq 1 -and $c.mismatches[0] -like "no prestate*")
# 7. service comparison is case-insensitive (install reported WINUSB, docs say WinUSB)
Case "service_case" "WINUSB == WinUSB" (Test-ServiceEq "WINUSB" "WinUSB") (Test-ServiceEq "WINUSB" "WinUSB")
# 8. function keys
$k = @("USB\VID_046D&PID_0843&MI_03\8&39DEC205&1&0003", "USB\VID_046D&PID_085C\B76395EF", "USB\VID_4C4A&PID_4A55&MI_00\8&35E81179&0&0000") | ForEach-Object { Get-FunctionKey $_ }
Case "function_keys" "MI_03,parent,MI_00" ($k -join ",") (($k -join ",") -eq "MI_03,parent,MI_00")

$doc = [ordered]@{ test = "winusb_compare_family_selftest"; platform = "windows"; hostname = $env:COMPUTERNAME
  utc_started = (Get-Date).ToUniversalTime().ToString("o"); command = "pwsh -File research/usb_cameras/libusb/winusb/selftest_winusb_common.ps1"
  inputs = @((Join-Path $src "prestate.json"), (Join-Path $src "rollback_result.json"), (Join-Path $src "install_result.json"))
  cases = $cases; passed = @($cases | Where-Object { $_.pass }).Count; total = $cases.Count }
$out = Join-Path (Get-WinUsbResultsDir $here) "selftest_compare_family.json"
$doc | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 $out
$cases | ForEach-Object { "{0,-36} {1}" -f $_.case, $(if ($_.pass) { "PASS" } else { "FAIL  got: $($_.got | ConvertTo-Json -Compress -Depth 4)" }) }
"passed $($doc.passed)/$($doc.total) -> $out"
if ($doc.passed -ne $doc.total) { exit 1 }
