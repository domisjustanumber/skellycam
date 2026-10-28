/* Minimal <unistd.h> for libuvc's example.c under MSVC (WIN32 builds only). */
#ifndef SKELLYCAM_COMPAT_UNISTD_H
#define SKELLYCAM_COMPAT_UNISTD_H
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#define sleep(s) (Sleep((DWORD)(s) * 1000u), 0)
#define usleep(us) (Sleep((DWORD)((us) / 1000u)), 0)
#endif
