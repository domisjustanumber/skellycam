# Windows camera-identity stability workflow (USER-RUN; unverified until you run it).
#
# What it tests: which identifiers survive (a) a reboot, (b) unplug + replug into the SAME port,
# (c) moving each camera to a DIFFERENT port (or hub). No admin needed. Nothing is streamed; the hub is asked for
# the device/config/string descriptors (EP0 control requests).
#
# Run from the repo root in PowerShell, one step at a time, doing the physical action between steps:
#   powershell -ExecutionPolicy Bypass -File research\usb_cameras\naming\win_stability_workflow.ps1 -Step baseline
#   (reboot)                 ... -Step after_reboot
#   (unplug/replug same port)... -Step after_replug_same_port
#   (move to other ports)    ... -Step after_move_port
#   ... -Step diff           # writes results\windows\<host>\naming\stability_<labels>.json and prints the table
# Optional: -Step snapshot -Label <any_name> for extra states (e.g. after_driver_update, two_identical_cameras).
# Needs: uv on PATH. Writes: results\windows\<hostname>\naming\snapshots\<label>.json (+ identity_dump.json, descriptors.json)
# Tip: for (c), note which camera went where; serial-less cameras of the same model cannot be matched automatically
# (that is the point of the test) - identity_diff.py then lists them as separate rows.
param(
    [Parameter(Mandatory = $true)][ValidateSet('baseline', 'after_reboot', 'after_replug_same_port', 'after_move_port', 'snapshot', 'diff')][string]$Step,
    [string]$Label
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $here '..\..\..')
$snapDir = Join-Path $here "..\results\windows\$env:COMPUTERNAME\naming\snapshots"
$camlock = Join-Path $here '..\tools\camlock.py'
Push-Location $root
try {
    if ($Step -eq 'diff') {
        $order = 'baseline', 'after_reboot', 'after_replug_same_port', 'after_move_port'
        $files = @($order | ForEach-Object { Join-Path $snapDir "$_.json" } | Where-Object { Test-Path $_ })
        $files += @(Get-ChildItem $snapDir -Filter *.json | Where-Object { $order -notcontains $_.BaseName -and $_.BaseName -notlike 'restart_*' -and $_.BaseName -ne 'baseline_initial' } | ForEach-Object { $_.FullName })
        if ($files.Count -lt 2) { throw "need >= 2 snapshots in $snapDir" }
        uv run --script (Join-Path $here 'identity_diff.py') @files
        # pairwise too, so each physical action is isolated
        for ($i = 1; $i -lt $files.Count; $i++) {
            uv run --script (Join-Path $here 'identity_diff.py') $files[0] $files[$i]
        }
    }
    else {
        $lbl = if ($Step -eq 'snapshot') { if (-not $Label) { throw '-Label required' }; $Label } else { $Step }
        $cmd = @('run', '--script', $camlock, '--', 'uv', 'run', '--script', (Join-Path $here 'win_identity_dump.py'), '--label', $lbl)
        & uv @cmd
        if ($LASTEXITCODE -ne 0) { throw "snapshot failed ($LASTEXITCODE)" }
        Write-Host "saved snapshot '$lbl' in $snapDir"
    }
}
finally { Pop-Location }
