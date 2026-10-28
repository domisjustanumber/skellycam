@echo off
rem Build timing\build\kiyo_ks_mf_probe.exe (MSVC 2022 x64). Run from any directory.
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
set HERE=%~dp0
if not exist "%HERE%build" mkdir "%HERE%build"
cl /nologo /std:c++17 /O2 /EHsc /W3 /Fo"%HERE%build\\" /Fe"%HERE%build\kiyo_ks_mf_probe.exe" "%HERE%src\kiyo_ks_mf_probe.cpp" || exit /b 1
cl /nologo /std:c++17 /O2 /EHsc /W3 /Fo"%HERE%build\\" /Fe"%HERE%build\dshow_open_probe.exe" "%HERE%src\dshow_open_probe.cpp" || exit /b 1
cl /nologo /std:c++17 /O2 /EHsc /W3 /Fo"%HERE%build\\" /Fe"%HERE%build\usb_ep0_probe.exe" "%HERE%src\usb_ep0_probe.cpp" || exit /b 1
