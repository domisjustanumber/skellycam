@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
cd /d "%~1"
uv run --script compile_checks\run_compile_checks.py
echo exit_compile_checks=%ERRORLEVEL%
