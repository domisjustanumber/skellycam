# T-S4 runner: one Electron process per (run, version, fps, arm), interleaved; raw JSON per run into $OutDir.
# Usage: pwsh -File run.ps1 -DataDir <scratch>\sidecar_load -OutDir <scratch>\sidecar_load\runs [-Runs 5] [-Arms ...] [-Fps 30,60] [-Versions e35,e45]
param(
  [Parameter(Mandatory)] [string]$DataDir,
  [Parameter(Mandatory)] [string]$OutDir,
  [int]$Runs = 5,
  [string[]]$Arms = @('A_dv', 'A_dvl', 'A_zc', 'B', 'C', 'D', 'E_a', 'E_cin', 'E_catt'),
  [int[]]$Fps = @(30, 60),
  [string[]]$Versions = @('e35', 'e45'),
  [int]$TimeoutSec = 180,
  [string]$SetSuffix = ''
)
$ErrorActionPreference = 'Stop'
$exe = @{
  e35 = 'C:\Users\Dom\GitHub\freemocap\skellycam\skellycam-ui\node_modules\electron\dist\electron.exe'
  e45 = 'C:\Users\Dom\AppData\Local\Temp\claude\ca7e9b09df19a3f5\106dc0c8-f977-4082-9d8d-367e9a9f721d\scratchpad\shared\electron-latest\node_modules\electron\dist\electron.exe'
}
$appDir = Join-Path $PSScriptRoot 'electron'
New-Item -ItemType Directory -Force $OutDir | Out-Null
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
$log = Join-Path $OutDir 'runlog.jsonl'
for ($r = 1; $r -le $Runs; $r++) {
  foreach ($v in $Versions) {
    foreach ($f in $Fps) {
      foreach ($a in $Arms) {
        $tag = "r${r}_${v}_fps${f}${SetSuffix}_${a}"
        $out = Join-Path $OutDir "$tag.json"
        if (Test-Path $out) { continue }
        $base = 'file:///' + ((Join-Path $DataDir "fps$f$SetSuffix") -replace '\\', '/')
        $cfg = @{ arm = $a; fps = $f; cams = 16; base = $base; positions = 10; draws = 3600; seeks = 5000; lazySeeks = 300; maxBlocks = 32; seed = 7 }
        $cfgPath = Join-Path $OutDir "$tag.cfg.json"
        $cfg | ConvertTo-Json -Compress | Set-Content -Encoding utf8NoBOM $cfgPath
        $load = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
        $others = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match '^(electron|python|ffmpeg|chrome)$' }).Count
        $env:SL_CFG = $cfgPath; $env:SL_OUT = $out
        $t0 = Get-Date
        $p = Start-Process -FilePath $exe[$v] -ArgumentList "`"$appDir`"" -PassThru -WindowStyle Hidden
        $ok = $p.WaitForExit($TimeoutSec * 1000)
        if (-not $ok) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
        $sec = ((Get-Date) - $t0).TotalSeconds
        @{ tag = $tag; ok = $ok; exists = (Test-Path $out); sec = [math]::Round($sec, 1); cpu_load_pct_before = $load; other_procs = $others; when = (Get-Date).ToString('o') } | ConvertTo-Json -Compress | Add-Content $log
        Remove-Item $cfgPath -ErrorAction SilentlyContinue
      }
    }
  }
}
