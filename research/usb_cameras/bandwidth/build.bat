@echo off
rem Builds bandwidth\build\mf_multi_open.exe with MSVC (VS 2022, SDK 10.0.22621).
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
cd /d "%~dp0"
if not exist build mkdir build
cl /nologo /EHsc /O2 /std:c++17 /W3 mf_multi_open.cpp /Fo:build\ /Fe:build\mf_multi_open.exe || exit /b 1
