# ELEVATED. Removes every MetadataBufferSizeInKB0 value under the two camera device-interface classes for the four
# study cameras (Logitech 046D, Razer 1532, generic 4C4A), current and stale instances alike.
# No device restart (LogiTune vetoes them on this machine); the user replugs each camera afterwards.
param([Parameter(Mandatory)][string]$Log, [Parameter(Mandatory)][string]$Json)
$ErrorActionPreference = 'Continue'
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
  [Security.Principal.WindowsBuiltInRole]::Administrator)
Set-Content -LiteralPath $Log -Encoding UTF8 -Value "=== $(Get-Date -Format o) REMOVE MetadataBufferSizeInKB0 (admin=$isAdmin)"
$base = 'HKLM:\SYSTEM\CurrentControlSet\Control\DeviceClasses'
$vids = 'VID_046D&', 'VID_1532&', 'VID_4C4A&'
$rows = @()
foreach ($g in '{e5323777-f976-4f5b-9b55-b94699c46e44}', '{65E8773D-8F56-11D0-A3B9-00A0C9223196}') {
  foreach ($k in Get-ChildItem -LiteralPath "$base\$g" -ErrorAction SilentlyContinue) {
    $name = $k.PSChildName.ToUpperInvariant()
    if (-not ($vids | Where-Object { $name.Contains($_) })) { continue }
    $p = $k.PSPath + '\#GLOBAL\Device Parameters'
    if (-not (Test-Path -LiteralPath $p)) { continue }
    $before = (Get-ItemProperty -LiteralPath $p -Name MetadataBufferSizeInKB0 -ErrorAction SilentlyContinue).MetadataBufferSizeInKB0
    if ($null -eq $before) { continue }
    $err = $null
    try { Remove-ItemProperty -LiteralPath $p -Name MetadataBufferSizeInKB0 -ErrorAction Stop } catch { $err = "$_" }
    $after = (Get-ItemProperty -LiteralPath $p -Name MetadataBufferSizeInKB0 -ErrorAction SilentlyContinue).MetadataBufferSizeInKB0
    $rows += [pscustomobject]@{ class = $g; key = $k.PSChildName; before = $before; after = $after; error = $err }
    Add-Content -LiteralPath $Log -Encoding UTF8 -Value ("{0} {1}\{2} before={3} after={4} {5}" -f $(if ($err) {'ERR'} else {'OK '}), $g, $k.PSChildName, $before, $after, $err)
  }
}
$doc = [pscustomobject]@{
  test = 'metadata_revert'; utc = (Get-Date).ToUniversalTime().ToString('o'); hostname = $env:COMPUTERNAME; admin = $isAdmin
  note = 'Dom 2026-11-09: tier-0-only testing; removed MetadataBufferSizeInKB0 everywhere it was set; no device restart, cameras replugged by hand afterwards'
  removed = @($rows | Where-Object { $null -eq $_.after }).Count; failed = @($rows | Where-Object { $null -ne $_.after }).Count; values = $rows
}
$doc | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $Json -Encoding UTF8
Add-Content -LiteralPath $Log -Encoding UTF8 -Value "DONE $(Get-Date -Format o) removed=$($doc.removed) failed=$($doc.failed)"
