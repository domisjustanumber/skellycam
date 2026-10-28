/*
 * Minimal POSIX-threads shim for building upstream libuvc with MSVC.
 *
 * Why this exists: upstream libuvc (https://github.com/libuvc/libuvc) uses only a tiny
 * subset of pthreads (mutex, condvar incl. timedwait, create/join). Rather than vendoring
 * pthreads4w (what pupil-labs/pyuvc does via the pupil-pthreads-win wheel) or patching every
 * call site, this header maps that subset onto native Win32 primitives (SRWLOCK,
 * CONDITION_VARIABLE, _beginthreadex). It is put on the include path ONLY for WIN32 builds
 * (see research/usb_cameras/libusb/CMakeLists.txt), so libuvc sources compile unmodified.
 *
 * Also provides clock_gettime(CLOCK_MONOTONIC|CLOCK_REALTIME), which libuvc's stream.c calls.
 * CLOCK_MONOTONIC is QueryPerformanceCounter-based, so libuvc's capture_time_finished lands
 * on the same host clock (QPC) the research frame-log schema uses for host_arrival_ns.
 *
 * Only what libuvc needs is implemented; attributes are accepted and ignored.
 */
#ifndef SKELLYCAM_COMPAT_PTHREAD_H
#define SKELLYCAM_COMPAT_PTHREAD_H

#ifndef _WIN32
#error "compat/win32/pthread.h is only for Windows builds"
#endif

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <winsock2.h> /* struct timeval, before windows.h pulls in winsock.h */
#include <windows.h>
#include <process.h>
#include <errno.h>
#include <stdint.h>
#include <stdlib.h>
#include <time.h>

#ifndef ETIMEDOUT
#define ETIMEDOUT 138
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef struct { SRWLOCK lock; } pthread_mutex_t;
typedef struct { CONDITION_VARIABLE cv; } pthread_cond_t;
typedef int pthread_mutexattr_t;
typedef int pthread_condattr_t;
typedef int pthread_attr_t;
typedef struct { HANDLE handle; } pthread_t;

static __inline int pthread_mutex_init(pthread_mutex_t *m, const pthread_mutexattr_t *a) {
  (void)a; InitializeSRWLock(&m->lock); return 0;
}
static __inline int pthread_mutex_destroy(pthread_mutex_t *m) { (void)m; return 0; }
static __inline int pthread_mutex_lock(pthread_mutex_t *m) { AcquireSRWLockExclusive(&m->lock); return 0; }
static __inline int pthread_mutex_unlock(pthread_mutex_t *m) { ReleaseSRWLockExclusive(&m->lock); return 0; }

static __inline int pthread_cond_init(pthread_cond_t *c, const pthread_condattr_t *a) {
  (void)a; InitializeConditionVariable(&c->cv); return 0;
}
static __inline int pthread_cond_destroy(pthread_cond_t *c) { (void)c; return 0; }
static __inline int pthread_cond_signal(pthread_cond_t *c) { WakeConditionVariable(&c->cv); return 0; }
static __inline int pthread_cond_broadcast(pthread_cond_t *c) { WakeAllConditionVariable(&c->cv); return 0; }
static __inline int pthread_cond_wait(pthread_cond_t *c, pthread_mutex_t *m) {
  return SleepConditionVariableSRW(&c->cv, &m->lock, INFINITE, 0) ? 0 : EINVAL;
}

/* ---- clocks ---------------------------------------------------------------------- */
#ifndef CLOCK_REALTIME
#define CLOCK_REALTIME 0
#endif
#ifndef CLOCK_MONOTONIC
#define CLOCK_MONOTONIC 1
#endif
typedef int clockid_t;

static __inline int clock_gettime(clockid_t id, struct timespec *ts) {
  if (id == CLOCK_MONOTONIC) {
    LARGE_INTEGER f, c;
    QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&c);
    ts->tv_sec = (time_t)(c.QuadPart / f.QuadPart);
    ts->tv_nsec = (long)(((c.QuadPart % f.QuadPart) * 1000000000LL) / f.QuadPart);
    return 0;
  } else {
    FILETIME ft;
    uint64_t t;
    GetSystemTimePreciseAsFileTime(&ft);
    t = ((uint64_t)ft.dwHighDateTime << 32) | ft.dwLowDateTime; /* 100ns since 1601 */
    t -= 116444736000000000ULL;                                 /* -> since 1970 */
    ts->tv_sec = (time_t)(t / 10000000ULL);
    ts->tv_nsec = (long)((t % 10000000ULL) * 100);
    return 0;
  }
}

/* abstime is CLOCK_REALTIME (libuvc builds it with clock_gettime(CLOCK_REALTIME)) */
static __inline int pthread_cond_timedwait(pthread_cond_t *c, pthread_mutex_t *m, const struct timespec *abstime) {
  struct timespec now;
  int64_t ms;
  clock_gettime(CLOCK_REALTIME, &now);
  ms = ((int64_t)abstime->tv_sec - (int64_t)now.tv_sec) * 1000 + (abstime->tv_nsec - now.tv_nsec) / 1000000;
  if (ms < 0) ms = 0;
  if (SleepConditionVariableSRW(&c->cv, &m->lock, (DWORD)ms, 0)) return 0;
  return GetLastError() == ERROR_TIMEOUT ? ETIMEDOUT : EINVAL;
}

/* ---- threads --------------------------------------------------------------------- */
typedef struct { void *(*fn)(void *); void *arg; } skc_thread_start_t;

static unsigned __stdcall skc_thread_trampoline(void *p) {
  skc_thread_start_t s = *(skc_thread_start_t *)p;
  free(p);
  s.fn(s.arg);
  return 0;
}

static __inline int pthread_create(pthread_t *t, const pthread_attr_t *a, void *(*fn)(void *), void *arg) {
  skc_thread_start_t *s = (skc_thread_start_t *)malloc(sizeof(*s));
  (void)a;
  if (!s) return ENOMEM;
  s->fn = fn; s->arg = arg;
  t->handle = (HANDLE)_beginthreadex(NULL, 0, skc_thread_trampoline, s, 0, NULL);
  if (!t->handle) { free(s); return EAGAIN; }
  return 0;
}

static __inline int pthread_join(pthread_t t, void **ret) {
  if (ret) *ret = NULL;
  WaitForSingleObject(t.handle, INFINITE);
  CloseHandle(t.handle);
  return 0;
}

#ifdef __cplusplus
}
#endif
#endif /* SKELLYCAM_COMPAT_PTHREAD_H */
