@echo off
rem Builds wincam.exe into build\ next to this file. Run from any cmd prompt; sets up MSVC x64 itself.
rem Needs VS 2022 (Community or any other edition, or the Build Tools) with the C++ x64 tools.
rem Windows SDK: an installed SDK is used when vcvars64 finds one (windows.h on INCLUDE). Otherwise the
rem Windows SDK 10.0.22621 NuGet packages (Microsoft.Windows.SDK.CPP and .CPP.x64, 10.0.22621.3233) are
rem downloaded once from nuget.org into build\sdk\ (git-ignored), checked against pinned SHA-256 hashes,
rem unpacked and re-used on later builds. Nothing is installed system-wide.
rem   WINCAM_SDK_DIR=<folder>     use another folder for the NuGet SDK (default build\sdk)
rem   WINCAM_FORCE_NUGET_SDK=1    use the NuGet SDK even when an installed SDK is found
setlocal EnableDelayedExpansion
set "HERE=%~dp0"
set "VCVARS=C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "!VCVARS!" if exist "!VSWHERE!" (
  for /f "usebackq tokens=*" %%i in (`"!VSWHERE!" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VCVARS=%%i\VC\Auxiliary\Build\vcvars64.bat"
)
if not exist "!VCVARS!" (echo error: vcvars64.bat not found & exit /b 1)
call "!VCVARS!" >nul || exit /b 1

set "WINH="
for %%I in (windows.h) do set "WINH=%%~$INCLUDE:I"
if defined WINCAM_FORCE_NUGET_SDK set "WINH="
if defined WINH (
  echo Windows SDK: installed, !WINH!
) else (
  call :nuget_sdk || exit /b 1
)

if not exist "%HERE%build" mkdir "%HERE%build"
cl /nologo /EHsc /O2 /std:c++17 /W4 /permissive- /utf-8 /DUNICODE /D_UNICODE ^
   "%HERE%wincam.cpp" /Fo"%HERE%build\\" /Fd"%HERE%build\\" /Fe"%HERE%build\wincam.exe" ^
   /link mfplat.lib mf.lib mfreadwrite.lib mfuuid.lib ole32.lib oleaut32.lib strmiids.lib advapi32.lib || exit /b 1
echo built %HERE%build\wincam.exe
exit /b 0

rem ---- NuGet Windows SDK fallback --------------------------------------------------------------
:nuget_sdk
set "SDKVER=10.0.22621.3233"
set "SDKINC=10.0.22621.0"
if not defined WINCAM_SDK_DIR set "WINCAM_SDK_DIR=%HERE%build\sdk"
set "SDK=!WINCAM_SDK_DIR!\microsoft.windows.sdk.cpp\c"
set "SDKX=!WINCAM_SDK_DIR!\microsoft.windows.sdk.cpp.x64\c"
call :nuget_pkg Microsoft.Windows.SDK.CPP microsoft.windows.sdk.cpp E4EFE1768EA61F4F999DBEF61B09895320629F975F9CEED8290A9633E0C31623 "!SDK!\Include\!SDKINC!\um\windows.h" || exit /b 1
call :nuget_pkg Microsoft.Windows.SDK.CPP.x64 microsoft.windows.sdk.cpp.x64 F8475CF8654763DD5D5DB050B99788EF3CEAE4436A2FBA8FE4EA3B022C656E19 "!SDKX!\um\x64\kernel32.lib" || exit /b 1
set "INCLUDE=!INCLUDE!;!SDK!\Include\!SDKINC!\ucrt;!SDK!\Include\!SDKINC!\um;!SDK!\Include\!SDKINC!\shared;!SDK!\Include\!SDKINC!\winrt;!SDK!\Include\!SDKINC!\cppwinrt"
set "LIB=!LIB!;!SDKX!\ucrt\x64;!SDKX!\um\x64"
echo Windows SDK: NuGet !SDKVER!, !WINCAM_SDK_DIR!
exit /b 0

rem usage: call :nuget_pkg <package id> <folder name> <sha256 of the .nupkg> <file that proves it is unpacked>
:nuget_pkg
if exist "%~4" exit /b 0
set "PKGDIR=!WINCAM_SDK_DIR!\%~2"
set "ZIP=!WINCAM_SDK_DIR!\%~2.!SDKVER!.zip"
if not exist "!WINCAM_SDK_DIR!" mkdir "!WINCAM_SDK_DIR!" || exit /b 1
echo downloading %~1 !SDKVER! from nuget.org into !WINCAM_SDK_DIR! ...
curl.exe -fsSL --retry 3 -o "!ZIP!" "https://www.nuget.org/api/v2/package/%~1/!SDKVER!" || (echo error: download of %~1 failed & exit /b 1)
set "GOT="
for /f "skip=1 delims=" %%h in ('certutil -hashfile "!ZIP!" SHA256') do if not defined GOT set "GOT=%%h"
set "GOT=!GOT: =!"
if /i not "!GOT!"=="%~3" (echo error: %~1 SHA-256 is !GOT!, expected %~3 & del "!ZIP!" & exit /b 1)
if exist "!PKGDIR!" rmdir /s /q "!PKGDIR!"
mkdir "!PKGDIR!" || exit /b 1
tar.exe -xf "!ZIP!" -C "!PKGDIR!" || (echo error: could not unpack !ZIP! & exit /b 1)
if not exist "%~4" (echo error: %~4 missing after unpacking %~1 & exit /b 1)
del "!ZIP!"
exit /b 0
