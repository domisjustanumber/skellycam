# run_elevated_wait.ps1 -- launches <Script> elevated (UAC prompt) with -Log <Log> and waits until the log says DONE.
# Intended to be run under camlock so no other agent opens cameras while devices restart.
param([Parameter(Mandatory)][string]$Script, [Parameter(Mandatory)][string]$Log, [int]$TimeoutS = 300)
if (Test-Path $Log) { Remove-Item $Log }
Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$Script`" -Log `"$Log`""
$t0 = Get-Date
while (((Get-Date) - $t0).TotalSeconds -lt $TimeoutS) {
  if ((Test-Path $Log) -and (Select-String -Path $Log -Pattern '^DONE' -Quiet)) { Start-Sleep 5; Get-Content $Log; exit 0 }
  Start-Sleep 2
}
"TIMEOUT waiting for $Log"; if (Test-Path $Log) { Get-Content $Log }; exit 1
