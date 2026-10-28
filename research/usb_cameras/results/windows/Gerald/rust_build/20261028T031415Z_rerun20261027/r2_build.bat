@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
cd /d "%~1"
"%USERPROFILE%\.cargo\bin\cargo.exe" build --release -p nokhwa_probe
echo exit_nokhwa_probe=%ERRORLEVEL%
