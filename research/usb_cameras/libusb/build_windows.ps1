# build_windows.ps1 - reproducible Windows/MSVC build of libusb + patched libuvc + test programs.
#
# Run (PowerShell 7, no admin needed, VS 2022 with C++ workload installed):
#   pwsh -File research/usb_cameras/libusb/build_windows.ps1
# Outputs:
#   research/usb_cameras/libusb/build/deps/        downloaded/cloned sources (git-ignored)
#   research/usb_cameras/libusb/build/cmake/bin/Release/{uvc_capture_test.exe,example.exe,uvc.dll,libusb-1.0.dll}
#   research/usb_cameras/libusb/build/libusb-msvc/  libusb-1.0.dll/.lib built from the release tarball
#   research/usb_cameras/libusb/build/build_info.json  exact versions, hashes, commands
#
# Pinned inputs (change deliberately, then re-run):
#   libusb  v1.0.30 source tarball  https://github.com/libusb/libusb/releases/download/v1.0.30/libusb-1.0.30.tar.bz2
#           sha256 fea36f34f9156400209595e300840767ab1a385ede1dc7ee893015aea9c6dbaf
#   libuvc  https://github.com/libuvc/libuvc.git  master @ d07de4fa23905ee8cac06f5d24b2a03d42a3b363 (2026-10-01)
#           + patches/0001-frame-timing-and-iso-override.patch
# Windows portability needs NO libuvc source patch: compat/win32/{pthread.h,sys/time.h,unistd.h}
# are injected via the include path by ../CMakeLists.txt.
param(
  [string]$Root = (Split-Path -Parent $MyInvocation.MyCommand.Path),
  [string]$Config = "Release"
)
$ErrorActionPreference = "Stop"
$LibusbVer = "1.0.30"
$LibusbUrl = "https://github.com/libusb/libusb/releases/download/v$LibusbVer/libusb-$LibusbVer.tar.bz2"
$LibusbSha = "fea36f34f9156400209595e300840767ab1a385ede1dc7ee893015aea9c6dbaf"
$LibuvcUrl = "https://github.com/libuvc/libuvc.git"
$LibuvcCommit = "d07de4fa23905ee8cac06f5d24b2a03d42a3b363"

$Build = Join-Path $Root "build"
$Deps = Join-Path $Build "deps"
New-Item -ItemType Directory -Force $Deps | Out-Null

$VsRoot = "C:\Program Files\Microsoft Visual Studio\2022\Community"
$MSBuild = Join-Path $VsRoot "MSBuild\Current\Bin\amd64\MSBuild.exe"
$CMake = Join-Path $VsRoot "Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
foreach ($t in @($MSBuild, $CMake)) { if (-not (Test-Path $t)) { throw "missing tool: $t" } }

# ---- 1. libusb from the release tarball -------------------------------------------------
$Tarball = Join-Path $Deps "libusb-$LibusbVer.tar.bz2"
if (-not (Test-Path $Tarball)) {
  Write-Host "downloading $LibusbUrl"
  Invoke-WebRequest -Uri $LibusbUrl -OutFile $Tarball
}
$h = (Get-FileHash -Algorithm SHA256 $Tarball).Hash.ToLower()
if ($h -ne $LibusbSha) { throw "libusb tarball sha256 mismatch: $h" }
$LibusbSrc = Join-Path $Deps "libusb-$LibusbVer"
if (-not (Test-Path $LibusbSrc)) { tar -xjf $Tarball -C $Deps; if ($LASTEXITCODE) { throw "tar failed" } }

Write-Host "building libusb (msvc/libusb_dll.vcxproj, x64 $Config)"
& $MSBuild (Join-Path $LibusbSrc "msvc\libusb_dll.vcxproj") -m -v:m -nologo "-p:Configuration=$Config" "-p:Platform=x64"
if ($LASTEXITCODE) { throw "libusb build failed" }
$dll = Get-ChildItem -Recurse (Join-Path $LibusbSrc "build") -Filter "libusb-1.0.dll" | Where-Object { $_.FullName -match "x64\\$Config" } | Select-Object -First 1
if (-not $dll) { throw "libusb-1.0.dll not found after build" }
$LibusbOut = Join-Path $Build "libusb-msvc"
New-Item -ItemType Directory -Force $LibusbOut | Out-Null
Copy-Item $dll.FullName $LibusbOut -Force
Copy-Item (Join-Path $dll.DirectoryName "libusb-1.0.lib") $LibusbOut -Force
Copy-Item (Join-Path $LibusbSrc "libusb\libusb.h") $LibusbOut -Force

# ---- 2. libuvc at the pinned commit + patch ----------------------------------------------
$Uvc = Join-Path $Deps "libuvc"
if (-not (Test-Path (Join-Path $Uvc ".git"))) {
  git -c core.autocrlf=false clone -q $LibuvcUrl $Uvc
  if ($LASTEXITCODE) { throw "git clone libuvc failed" }
}
git -C $Uvc -c core.autocrlf=false checkout -q --force $LibuvcCommit
git -C $Uvc reset -q --hard $LibuvcCommit
git -C $Uvc clean -qfdx
foreach ($p in Get-ChildItem (Join-Path $Root "patches") -Filter "*.patch" | Sort-Object Name) {
  Write-Host "applying $($p.Name)"
  git -C $Uvc apply --whitespace=nowarn $p.FullName
  if ($LASTEXITCODE) { throw "patch failed: $($p.Name)" }
}

# ---- 3. CMake (Visual Studio generator; no vcvars needed) ---------------------------------
$CmakeBuild = Join-Path $Build "cmake"
& $CMake -S $Root -B $CmakeBuild -G "Visual Studio 17 2022" -A x64 `
  "-DLIBUVC_SOURCE_DIR=$Uvc" "-DLIBUSB_INCLUDE_DIR=$LibusbOut" `
  "-DLIBUSB_LIBRARY=$(Join-Path $LibusbOut 'libusb-1.0.lib')" "-DLIBUSB_DLL=$(Join-Path $LibusbOut 'libusb-1.0.dll')" `
  "-DCMAKE_C_FLAGS=/DLIBUVC_GIT_COMMIT=\`"$LibuvcCommit\`""
if ($LASTEXITCODE) { throw "cmake configure failed" }
& $CMake --build $CmakeBuild --config $Config -- "/m" "/nologo" "/verbosity:minimal"
if ($LASTEXITCODE) { throw "cmake build failed" }

$Bin = Join-Path $CmakeBuild "bin\$Config"
$info = [ordered]@{
  utc = (Get-Date).ToUniversalTime().ToString("o")
  host = $env:COMPUTERNAME
  libusb = @{ version = $LibusbVer; url = $LibusbUrl; sha256 = $LibusbSha; built_with = "msvc/libusb_dll.vcxproj x64 $Config" }
  libuvc = @{ url = $LibuvcUrl; commit = $LibuvcCommit; patches = @(Get-ChildItem (Join-Path $Root "patches") -Filter "*.patch" | ForEach-Object { @{ name = $_.Name; sha256 = (Get-FileHash -Algorithm SHA256 $_.FullName).Hash.ToLower() } }) }
  msbuild = $MSBuild; cmake = $CMake; cmake_version = (& $CMake --version | Select-Object -First 1)
  outputs = @(Get-ChildItem $Bin | ForEach-Object { @{ name = $_.Name; bytes = $_.Length; sha256 = (Get-FileHash -Algorithm SHA256 $_.FullName).Hash.ToLower() } })
}
$info | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 (Join-Path $Build "build_info.json")
Write-Host "OK: binaries in $Bin"
