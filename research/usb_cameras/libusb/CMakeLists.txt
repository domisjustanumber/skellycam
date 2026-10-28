# Wrapper build for upstream libuvc + research test programs (Windows/MSVC, Linux, macOS).
#
#   Windows: run build_windows.ps1 (it builds libusb from the release tarball, clones+patches
#            libuvc, then configures this file). Manual equivalent:
#     cmake -S research/usb_cameras/libusb -B research/usb_cameras/libusb/build/cmake ^
#           -DLIBUVC_SOURCE_DIR=<patched libuvc> -DLIBUSB_INCLUDE_DIR=<dir with libusb.h> ^
#           -DLIBUSB_LIBRARY=<libusb-1.0.lib> -DLIBUSB_DLL=<libusb-1.0.dll>
#   Linux/macOS: libuvc's own FindLibUSB (pkg-config libusb-1.0) is used:
#     cmake -S research/usb_cameras/libusb -B build -DLIBUVC_SOURCE_DIR=<patched libuvc>
#
# Nothing in libuvc's sources is modified for portability: on WIN32 the compat/win32 shim
# headers (pthread.h, sys/time.h, unistd.h) are put first on the include path, and the
# LibUSB::LibUSB imported target that libuvc's FindLibUSB skips for MSVC is defined here.
# The only source patch is patches/0001-frame-timing-and-iso-override.patch (features).
cmake_minimum_required(VERSION 3.18)
project(skellycam_libuvc_research C)

set(LIBUVC_SOURCE_DIR "" CACHE PATH "Patched libuvc source tree")
if(NOT EXISTS "${LIBUVC_SOURCE_DIR}/CMakeLists.txt")
  message(FATAL_ERROR "LIBUVC_SOURCE_DIR must point at a (patched) libuvc checkout")
endif()

if(MSVC)
  set(LIBUSB_INCLUDE_DIR "" CACHE PATH "Directory containing libusb.h")
  set(LIBUSB_LIBRARY "" CACHE FILEPATH "libusb-1.0.lib (import library)")
  set(LIBUSB_DLL "" CACHE FILEPATH "libusb-1.0.dll (copied next to the executables)")
  add_library(LibUSB::LibUSB SHARED IMPORTED GLOBAL)
  set_target_properties(LibUSB::LibUSB PROPERTIES
    INTERFACE_INCLUDE_DIRECTORIES "${LIBUSB_INCLUDE_DIR}"
    IMPORTED_IMPLIB "${LIBUSB_LIBRARY}"
    IMPORTED_LOCATION "${LIBUSB_DLL}")
  # compat shims first, so <pthread.h>, <sys/time.h>, <unistd.h> resolve to them
  include_directories(BEFORE "${CMAKE_CURRENT_SOURCE_DIR}/compat/win32")
  add_compile_definitions(_CRT_SECURE_NO_WARNINGS _CRT_NONSTDC_NO_WARNINGS WIN32_LEAN_AND_MEAN)
  set(CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS ON)
  set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
  set(CMAKE_LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
else()
  # Define LibUSB::LibUSB GLOBAL here so both libuvc (its FindLibUSB skips when the target
  # exists) and uvc_capture_test in this directory can see it.
  find_package(PkgConfig REQUIRED)
  pkg_check_modules(LIBUSB REQUIRED IMPORTED_TARGET GLOBAL libusb-1.0)
  add_library(LibUSB::LibUSB ALIAS PkgConfig::LIBUSB)
  set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
endif()

set(DISABLE_JPEG ON CACHE BOOL "" FORCE)   # we keep MJPEG compressed; no libjpeg needed
set(BUILD_EXAMPLE ON CACHE BOOL "" FORCE)
# Static only: with "Both", MSVC's import lib of uvc.dll and the static uvc.lib share the name
# uvc.lib in one directory and overwrite each other (observed: example.exe failed to link).
set(CMAKE_BUILD_TARGET "Static" CACHE STRING "" FORCE)
set(LibUVC_STATIC ON)
add_subdirectory("${LIBUVC_SOURCE_DIR}" libuvc EXCLUDE_FROM_ALL)
# libuvc's example target is EXCLUDE_FROM_ALL via the subdirectory; pull it in explicitly
set_target_properties(example PROPERTIES EXCLUDE_FROM_ALL OFF)

add_executable(uvc_capture_test uvc_capture_test.c)
target_link_libraries(uvc_capture_test PRIVATE LibUVC::UVCStatic LibUSB::LibUSB)
if(NOT WIN32)
  find_package(Threads REQUIRED)
  target_link_libraries(uvc_capture_test PRIVATE Threads::Threads)
endif()
# hardware-free unit test of the libuvc patch (synthetic payloads)
add_executable(test_payload_timing tests/test_payload_timing.c)
target_link_libraries(test_payload_timing PRIVATE LibUVC::UVCStatic LibUSB::LibUSB)
if(NOT WIN32)
  target_link_libraries(test_payload_timing PRIVATE Threads::Threads)
endif()

if(MSVC)
  target_compile_options(uvc_capture_test PRIVATE /W3)
  target_link_libraries(uvc_capture_test PRIVATE cfgmgr32)
  # all executables and uvc.dll land in bin/<config>; put libusb-1.0.dll next to them
  add_custom_command(TARGET uvc_capture_test POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different "${LIBUSB_DLL}" "$<TARGET_FILE_DIR:uvc_capture_test>")
endif()
