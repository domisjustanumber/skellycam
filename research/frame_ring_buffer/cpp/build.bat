@echo off
rem Build every C++ benchmark of the cpp\ stage with MSVC (Visual Studio 2022 Community, x64).
rem   cpp\build\ringbench.exe     shared-memory ring, write-only and SPSC (processes or threads), large-page probe
rem   cpp\build\memcpybench.exe   copy bandwidth (single / multi-thread, memcpy and AVX2 streaming stores), pixel ops
rem   cpp\build\microbench.exe    control-plane ops, cross-process ping-pong, sleep granularity
rem   cpp\build\codecbench.exe    OpenCV 4.8.0 C++ decode / imencode / VideoWriter (needs OPENCV_DIR, see below)
rem   cpp\build\cppring.cp312-win_amd64.pyd   pybind11 + C-export module over the same ring (hybrid option)
rem Usage (any shell):  cmd /c research\frame_ring_buffer\cpp\build.bat    from C:\Users\Dom\GitHub\freemocap\skellycam
setlocal
set HERE=%~dp0
set SRC=%HERE%src
set OUT=%HERE%build
if not exist "%OUT%" mkdir "%OUT%"
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
if "%OPENCV_DIR%"=="" set OPENCV_DIR=C:\Users\Dom\Downloads\opencv\build
set PYBASE=C:\Users\Dom\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none
rem pybind11 3.1.0 headers, installed into .venv-bench with: uv pip install --python .venv-bench\Scripts\python.exe pybind11
set PYBIND_INC=%HERE%..\.venv-bench\Lib\site-packages\pybind11\include

set CFLAGS=/nologo /O2 /std:c++20 /EHsc /W3 /arch:AVX2 /DNDEBUG /MD /D_CRT_SECURE_NO_WARNINGS
pushd "%OUT%"
cl %CFLAGS% "%SRC%\ringbench.cpp" /Fe:ringbench.exe /link advapi32.lib || goto :fail
cl %CFLAGS% "%SRC%\memcpybench.cpp" /Fe:memcpybench.exe || goto :fail
cl %CFLAGS% "%SRC%\microbench.cpp" /Fe:microbench.exe || goto :fail
cl %CFLAGS% /I"%OPENCV_DIR%\include" "%SRC%\codecbench.cpp" /Fe:codecbench.exe /link /LIBPATH:"%OPENCV_DIR%\x64\vc16\lib" opencv_world480.lib || goto :fail
cl %CFLAGS% /LD /I"%PYBASE%\Include" /I"%PYBIND_INC%" "%SRC%\cppring_py.cpp" /Fe:cppring.cp312-win_amd64.pyd /link /LIBPATH:"%PYBASE%\libs" || goto :fail
del /q *.obj *.exp 2>nul
popd
echo BUILD OK
cl 2>&1 | findstr /i "Version"
exit /b 0
:fail
popd
echo BUILD FAILED
exit /b 1
