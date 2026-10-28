@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
cd /d "%~1"
set CARGO=%USERPROFILE%\.cargo\bin\cargo.exe
"%USERPROFILE%\.cargo\bin\rustc.exe" --version
"%CARGO%" --version
echo === cargo build --release -p nokhwa_probe
"%CARGO%" build --release -p nokhwa_probe
echo exit_nokhwa_probe=%ERRORLEVEL%
echo === cargo build --release -p uvc_iso --features libusb
"%CARGO%" build --release -p uvc_iso --features libusb
echo exit_uvc_iso_libusb=%ERRORLEVEL%
echo === cargo test --release -p uvc_iso --features libusb
"%CARGO%" test --release -p uvc_iso --features libusb
echo exit_uvc_iso_test=%ERRORLEVEL%
