//! Host monotonic clock in nanoseconds, matching the README frame-log schema:
//! Windows = QueryPerformanceCounter, Linux = CLOCK_MONOTONIC, macOS = mach_absolute_time.

#[cfg(windows)]
pub fn host_ns() -> i64 {
    use windows::Win32::System::Performance::{QueryPerformanceCounter, QueryPerformanceFrequency};
    let mut c = 0i64;
    let mut f = 0i64;
    unsafe {
        let _ = QueryPerformanceCounter(&mut c);
        let _ = QueryPerformanceFrequency(&mut f);
    }
    ((c as i128) * 1_000_000_000i128 / (f as i128)) as i64
}

#[cfg(windows)]
pub fn host_clock_name() -> &'static str {
    "QueryPerformanceCounter"
}

#[cfg(windows)]
pub fn qpc_freq() -> i64 {
    use windows::Win32::System::Performance::QueryPerformanceFrequency;
    let mut f = 0i64;
    unsafe {
        let _ = QueryPerformanceFrequency(&mut f);
    }
    f
}

#[cfg(target_os = "linux")]
pub fn host_ns() -> i64 {
    let mut ts = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut ts) };
    ts.tv_sec as i64 * 1_000_000_000 + ts.tv_nsec as i64
}
#[cfg(target_os = "linux")]
pub fn host_clock_name() -> &'static str {
    "CLOCK_MONOTONIC"
}

#[cfg(target_os = "macos")]
pub fn host_ns() -> i64 {
    #[allow(deprecated)]
    unsafe {
        let mut tb = libc::mach_timebase_info { numer: 0, denom: 0 };
        libc::mach_timebase_info(&mut tb);
        let t = libc::mach_absolute_time() as i128;
        (t * tb.numer as i128 / tb.denom as i128) as i64
    }
}
#[cfg(target_os = "macos")]
pub fn host_clock_name() -> &'static str {
    "mach_absolute_time"
}

#[cfg(not(windows))]
pub fn qpc_freq() -> i64 {
    0
}

/// Wall clock (UNIX epoch) in ns, as Rust's SystemTime reports it
/// (GetSystemTimePreciseAsFileTime on Windows, CLOCK_REALTIME on unix).
pub fn wall_ns() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos() as i64)
        .unwrap_or(0)
}
