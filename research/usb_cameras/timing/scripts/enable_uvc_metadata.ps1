# enable_uvc_metadata.ps1 -- ELEVATED. Enables the usbvideo.sys UVC metadata pin for the listed cameras.
#
# What it does (per Microsoft "UVC extensions 1.5" s.2.2.3 and the librealsense realsense_metadata_win10.ps1 recipe):
#   sets REG_DWORD MetadataBufferSizeInKB0 = 5 under
#   HKLM\SYSTEM\CurrentControlSet\Control\DeviceClasses\{GUID}\##?#USB#<VID_PID_MI_00>#<instance>#{GUID}\#GLOBAL\Device Parameters
#   for GUID in {e5323777-f976-4f5b-9b55-b94699c46e44} (KSCATEGORY_VIDEO_CAMERA) and {65E8773D-8F56-11D0-A3B9-00A0C9223196}
#   (KSCATEGORY_CAPTURE), then restarts the camera function with pnputil /restart-device.
# Revert: revert_uvc_metadata.ps1 (removes exactly these values, restarts the devices).
# Run:   Start-Process powershell -Verb RunAs -ArgumentList '-ExecutionPolicy Bypass -File <this> -Log <logfile>'
# NOTE: registry paths contain '?' so every cmdlet uses -LiteralPath (with -Path, '?' is a wildcard and a
#       non-matching path is silently ignored -- that bug made the first run of this script a no-op).
param(
  [string]$Log = "$env:TEMP\enable_uvc_metadata.log",
  [string[]]$Instances = @('USB\VID_1532&PID_0E05&MI_00\A&34494D13&0&0000',
                           'USB\VID_046D&PID_085C&MI_00\8&268DA596&0&0000',
                           'USB\VID_046D&PID_0843&MI_00\8&39DEC205&0&0000'),
  [int]$SizeKB = 5,
  [switch]$Remove,
  [switch]$NoRestart
)
$ErrorActionPreference = 'Continue'
function W([string]$s) { Add-Content -LiteralPath $Log -Value $s -Encoding UTF8 }
Set-Content -LiteralPath $Log -Encoding UTF8 -Value "=== $(Get-Date -Format o) $(if($Remove){'REMOVE'}else{'ENABLE'}) MetadataBufferSizeInKB0 (admin=$(([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)))"
$base = 'HKLM:\SYSTEM\CurrentControlSet\Control\DeviceClasses'
foreach ($inst in $Instances) {
  $sym = ('##?#' + $inst.Replace([string][char]92, '#')).ToUpperInvariant()
  foreach ($g in '{e5323777-f976-4f5b-9b55-b94699c46e44}', '{65E8773D-8F56-11D0-A3B9-00A0C9223196}') {
    $k = Get-ChildItem -LiteralPath "$base\$g" -ErrorAction SilentlyContinue |
         Where-Object { $_.PSChildName.ToUpperInvariant().StartsWith($sym + '#') } | Select-Object -First 1
    if (-not $k) { W "MISSING interface key for $inst under $g"; continue }
    $p = $k.PSPath + '\#GLOBAL\Device Parameters'
    if (-not (Test-Path -LiteralPath $p)) { W "MISSING $p"; continue }
    $before = (Get-ItemProperty -LiteralPath $p -Name MetadataBufferSizeInKB0 -ErrorAction SilentlyContinue).MetadataBufferSizeInKB0
    try {
      if ($Remove) { if ($null -ne $before) { Remove-ItemProperty -LiteralPath $p -Name MetadataBufferSizeInKB0 -ErrorAction Stop } }
      else { New-ItemProperty -LiteralPath $p -Name MetadataBufferSizeInKB0 -PropertyType DWord -Value $SizeKB -Force -ErrorAction Stop | Out-Null }
      $after = (Get-ItemProperty -LiteralPath $p -Name MetadataBufferSizeInKB0 -ErrorAction SilentlyContinue).MetadataBufferSizeInKB0
      W "OK  $g\$($k.PSChildName)\#GLOBAL\Device Parameters  before=$before after=$after"
    } catch { W "ERR $($k.PSChildName): $_  (before=$before)" }
  }
}
if (-not $NoRestart) {
  foreach ($inst in $Instances) {
    $o = & pnputil.exe /restart-device "$inst" 2>&1 | Out-String
    W "pnputil /restart-device $inst :: exit=$LASTEXITCODE :: $($o.Trim() -replace '\r?\n',' | ')"
  }
}
W "DONE $(Get-Date -Format o)"
