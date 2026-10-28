/*
 * Minimal <sys/time.h> for building upstream libuvc with MSVC (WIN32 builds only).
 * libuvc.h includes <sys/time.h> for struct timeval; upstream stream.c already defines
 * gettimeofday() under _MSC_VER but relies on this header for struct timezone + prototype.
 */
#ifndef SKELLYCAM_COMPAT_SYS_TIME_H
#define SKELLYCAM_COMPAT_SYS_TIME_H
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <winsock2.h> /* struct timeval */
#include <time.h>     /* struct timespec (MSVC >= 2015) */
#include "../pthread.h" /* clock_gettime() lives here so a single shim defines it */
#ifdef __cplusplus
extern "C" {
#endif
struct timezone { int tz_minuteswest; int tz_dsttime; };
int gettimeofday(struct timeval *tv, struct timezone *tz);
#ifdef __cplusplus
}
#endif
#endif
