@echo off
rem Build the Windows timing tools (MSVC 2022 x64). Run from any directory.
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
set HERE=%~dp0
if not exist "%HERE%build" mkdir "%HERE%build"
cl /nologo /std:c++17 /O2 /EHsc /W3 /Fo"%HERE%build\\" /Fe"%HERE%build\mf_uvc_timing.exe" "%HERE%src\mf_uvc_timing.cpp" || exit /b 1
if exist "%HERE%src\flash_timecode.cpp" cl /nologo /std:c++17 /O2 /EHsc /W3 /Fo"%HERE%build\\" /Fe"%HERE%build\flash_timecode.exe" "%HERE%src\flash_timecode.cpp" || exit /b 1
cl /nologo /O2 /EHsc /DUNICODE /D_UNICODE /Fo"%HERE%build\\" /Fe"%HERE%build\devrestart.exe" "%HERE%src\devrestart.cpp" setupapi.lib cfgmgr32.lib || exit /b 1
