@echo off
rem Build the small Windows-only probes in this folder with MSVC (no admin).
rem   research\usb_cameras\libusb\tests\build_win_tests.bat
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
set OUT=%~dp0..\build\tests
if not exist "%OUT%" mkdir "%OUT%"
cl /nologo /W4 /O2 /Fe"%OUT%\win_usb_frame_qpc.exe" /Fo"%OUT%\\" "%~dp0win_usb_frame_qpc.c" setupapi.lib || exit /b 1
echo OK
