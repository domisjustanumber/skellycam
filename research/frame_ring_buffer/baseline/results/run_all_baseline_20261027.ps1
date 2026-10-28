$ErrorActionPreference = 'Continue'
Set-Location C:\Users\Dom\GitHub\freemocap\skellycam
$env:PYTHONIOENCODING = 'utf-8'
$PY = '.venv\Scripts\python.exe'
$BL = 'benchmarks\frame_pipeline\baseline'
$W = "$BL\run_with_load.py"
$progress = 'C:\Users\Dom\AppData\Local\Temp\claude\c--Users-Dom-GitHub-freemocap-skellycam\7c9d3345-0e7f-4af6-bb14-20fd851edd1a\scratchpad\run_all_progress.txt'
"start $(Get-Date -Format s)" | Out-File $progress

function Step($name, $log, $timeout, [string[]]$cmd) {
    Start-Sleep -Seconds 15
    "$(Get-Date -Format s) START $name" | Out-File $progress -Append
    $out = & $PY $W $name $log $timeout -- @cmd
    "$(Get-Date -Format s) END $name $out" | Out-File $progress -Append
}

Step 'a_write' 'a_write_stdout.log' 1200 @($PY, "$BL\bench_a_write.py")
Step 'b_read' 'b_read_stdout.log' 1200 @($PY, "$BL\bench_b_read.py")
Step 'c_record' 'c_record_stdout.log' 1200 @($PY, "$BL\bench_c_record.py")
Step 'd_ui' 'd_ui_stdout.log' 900 @($PY, "$BL\bench_d_ui.py")
Step 'f_copies' 'f_copies_stdout.log' 900 @($PY, "$BL\bench_f_copies.py")
Step 'g_decode_ref' 'g_decode_ref_stdout.log' 600 @($PY, "$BL\bench_g_decode_ref.py")

$e2e = @(
  @('720p','memcpy','ui',''), @('720p','memcpy','ui','_rep2'), @('720p','mjpeg','ui',''),
  @('1080p','memcpy','ui',''), @('1080p','memcpy','ui','_rep2'),
  @('1080p','mjpeg','ui',''), @('1080p','mjpeg','ui','_rep2'), @('1080p','mjpeg','noui','')
)
foreach ($c in $e2e) {
    $env:BENCH_E2E_REP = $c[3]
    $tag = "e_e2e_$($c[0])_$($c[1])_$($c[2])$($c[3])"
    Step $tag "${tag}_stdout.log" 600 @($PY, "$BL\bench_e_e2e.py", $c[0], $c[1], $c[2], '30')
}
Remove-Item Env:\BENCH_E2E_REP -ErrorAction SilentlyContinue

Step 'summarize_e2e' 'summarize_e2e_stdout.log' 120 @($PY, "$BL\summarize_e2e.py")
Step 'repro_type_overloads_spawn' 'repro_type_overloads_spawn.txt' 300 @($PY, "$BL\repro_type_overloads_spawn.py")
Step 'diag_check_shm_speed' 'diag_check_shm_speed.txt' 300 @($PY, 'skellycam/system/diagnostics/check_shm_speed.py')
Step 'diag_pytest_shared_memory' 'diag_pytest_shared_memory.txt' 300 @($PY, '-m', 'pytest', 'skellycam/tests/test_shared_memory.py', '-q', '-p', 'no:cacheprovider')
Step 'diag_pytest_three_files' 'diag_pytest_three_files.txt' 300 @($PY, '-m', 'pytest', 'skellycam/tests/test_shared_memory.py', 'skellycam/tests/test_camera_orchestrator.py', 'skellycam/tests/test_frontend_payload_and_recording.py', '-q', '-p', 'no:cacheprovider')
"done $(Get-Date -Format s)" | Out-File $progress -Append
