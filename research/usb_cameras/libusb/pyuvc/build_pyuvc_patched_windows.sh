#!/bin/bash
# Build pupil-labs-uvc 1.0.8 (pyuvc v1.0.8 = 45506641, libuvc-source 949cb473) on Windows with
# patches/0001-winusb-null-product-guard-and-vs2022.patch, then a run venv with the runtime DLLs next to the pyd.
# Exactly what was run on GERALD (Git Bash, VS 2022 Community, uv, 7-Zip) on 2026-10-25.
#
# Why: the PyPI wheel crashes (access violation, ucrtbase!strlen(NULL)) at the first get_frame() on a WinUSB-bound
# camera: libuvc's uvc_stream_start() calls uvc_get_device_descriptor(), which libusb_open()s the device a second
# time to read iProduct; WinUSB is exclusive so the 2nd open returns LIBUSB_ERROR_ACCESS, desc->product stays NULL
# and is passed to strlen (results/windows/Gerald/phase2_pyuvc/debug_cdb, no_stream_double_open).
#
# usage: build_pyuvc_patched_windows.sh <pyuvc source checkout with submodules> <work dir>
# The work dir is subst'ed to P: because MSBuild FileTracker fails on the long scratchpad path (FTK1011).
set -euo pipefail
SRC=$1; W=$2
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$W/deps"
cp -r "$SRC" "$W/src"
rm -rf "$W/src/.git" "$W/src/libuvc-source/.git" "$W/src/libusb-source/.git"   # setuptools_scm relpath C:/P: clash
(cd "$W/src" && patch -p1 --binary < "$HERE/patches/0001-winusb-null-product-guard-and-vs2022.patch")
cd "$W/deps"
curl -sSL -o libjpeg-turbo.exe https://github.com/pupil-labs/pyndsi/wiki/libjpeg-turbo-2.1.0-vc64.exe   # same URLs as
curl -sSL -o libusb-bin.7z https://github.com/libusb/libusb/releases/download/v1.0.26/libusb-1.0.26-binaries.7z  # scripts/download-deps-win.ps1
"/c/Program Files/7-Zip/7z.exe" x -aoa libjpeg-turbo.exe -oltj > /dev/null     # extracted, never executed
"/c/Program Files/7-Zip/7z.exe" x -aoa libusb-bin.7z -olusb > /dev/null
cmd //c "subst P: $(cygpath -w "$W")"
cat > /p/deps/dep_paths_p.json <<'EOF'
{
 "LIBUSB_WIN_IMPORT_LIB_PATH": "P:/deps/lusb/libusb-1.0.26-binaries/VS2015-x64/dll/libusb-1.0.lib",
 "LIBUSB_WIN_DLL_SEARCH_PATH": "P:/deps/lusb/libusb-1.0.26-binaries/VS2015-x64/dll",
 "LIBUSB_WIN_INCLUDE_DIR": "P:/deps/lusb/libusb-1.0.26-binaries/libusb-MinGW-x64/include/libusb-1.0",
 "TURBOJPEG_WIN_IMPORT_LIB_PATH": "P:/deps/ltj/lib/turbojpeg.lib",
 "TURBOJPEG_WIN_DLL_SEARCH_PATH": "P:/deps/ltj/bin",
 "TURBOJPEG_WIN_INCLUDE_DIR": "P:/deps/ltj/include"
}
EOF
cd /p
uv venv venv --python 3.12 -q
uv pip install -q --python venv/Scripts/python.exe pip setuptools "setuptools_scm[toml]" wheel Cython numpy scikit-build cmake pupil_pthreads_win
(cd /p/src && PATH="/p/venv/Scripts:$PATH" DEPS_PATHS_LOC="P:/deps/dep_paths_p.json" SETUPTOOLS_SCM_PRETEND_VERSION=1.0.8.post0+winusbfix \
   /p/venv/Scripts/python.exe -m pip wheel --no-build-isolation --no-deps -w P:/wheel . > /p/build.log 2>&1)
uv venv runenv --python 3.12 -q
uv pip install -q --python runenv/Scripts/python.exe wheel/pupil_labs_uvc-1.0.8.post0+winusbfix-cp312-cp312-win_amd64.whl numpy pillow
S=runenv/Lib/site-packages/uvc   # no delvewheel repair: copy the runtime DLLs next to the pyd instead
cp $S/bin/uvc.dll deps/ltj/bin/turbojpeg.dll deps/lusb/libusb-1.0.26-binaries/VS2015-x64/dll/libusb-1.0.dll \
   venv/Lib/site-packages/pupil_pthreads_win/data/lib/x64/pthreadVC2.dll $S/
runenv/Scripts/python.exe -c "import uvc; print(uvc.__version__)"
echo "run: P:/runenv/Scripts/python.exe research/usb_cameras/libusb/pyuvc/pyuvc_winusb_stream.py ...   (undo the drive: subst P: /d)"
