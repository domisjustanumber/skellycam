@echo off
rem Builds mf_mjpeg_capture.exe into ..\build\ . Run from any cmd prompt; sets up MSVC x64 itself.
setlocal
set VCVARS="C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
if not exist %VCVARS% (echo error: vcvars64.bat not found at %VCVARS% & exit /b 1)
call %VCVARS% >nul || exit /b 1
set HERE=%~dp0
if not exist "%HERE%..\build" mkdir "%HERE%..\build"
cl /nologo /EHsc /O2 /std:c++17 /W3 /utf-8 "%HERE%mf_mjpeg_capture.cpp" /Fo"%HERE%..\build\\" /Fe"%HERE%..\build\mf_mjpeg_capture.exe" mfplat.lib mf.lib mfreadwrite.lib mfuuid.lib ole32.lib strmiids.lib || exit /b 1
echo built %HERE%..\build\mf_mjpeg_capture.exe
