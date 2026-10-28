// ring.hpp - C++ shared-memory frame ring used by the C++ comparison benchmarks (NOT SkellyCam code).
//
// One pagefile-backed named file mapping per camera (CreateFileMappingW(INVALID_HANDLE_VALUE, ...)), which is the
// same Win32 primitive that CPython's multiprocessing.shared_memory uses on Windows.
//
// Layout (all offsets from the start of the mapping):
//   [0, 4096)           header: int64 head (last published k, -1 = none)            @ 0
//                               int64 read_cursor (last k consumed by the SPSC reader) @ 64   (own cache line)
//                               int64 writer_done_count (total frames published, set when the writer exits) @ 128
//                               int64 writer_blocked_events                          @ 192
//   [4096, 4096+S)      per-slot sequence counters: int64 seq[L], S = round4k(L*8)
//   [4096+S, ...)       payload: L slots of `stride` bytes. stride = record_bytes (packed, like SkellyCam's recarray
//                       ring) or round4k(record_bytes) (aligned, like the prototype SeqRing).
//
// Record = SkellyCam frame record: 632 B frame_metadata followed by the HxWx3 BGR image (same itemsize as
// skellycam create_frame_dtype: 2,765,432 B at 720p, 6,221,432 B at 1080p, 12,920 B at 64x64).
// The benchmarks stamp: metadata[0:8] = frame number k, metadata[8:16] = publish time (QPC ns),
// image[0:8] = image[last 8] = k (torn-read detector).
//
// Write protocol for frame k (single writer):  seq[k%L] = 2k+1 ; release fence ; copy record ; seq[k%L] = 2k+2 (release) ;
//                                               head = k (release)
// Read protocol (single lossless reader, SPSC): wait head >= k ; s1 = seq[k%L] (acquire) ; must be 2k+2 ; copy out ;
//                                               acquire fence ; s2 = seq[k%L] ; ok iff s1 == s2 ; read_cursor = k (release)
// Gating (lossless, "block" policy): before writing frame k the writer waits until read_cursor >= k - L.
#pragma once
#define NOMINMAX
#include <windows.h>
#include <atomic>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace cr {

constexpr int64_t HDR = 4096;
constexpr int64_t META_BYTES = 632;  // SkellyCam frame_metadata itemsize (baseline f_copies.md: 6,221,432 - 6,220,800)

inline int64_t round4k(int64_t n) { return (n + 4095) / 4096 * 4096; }

inline int64_t qpc_ns() {
    static int64_t freq = [] { LARGE_INTEGER f; QueryPerformanceFrequency(&f); return (int64_t)f.QuadPart; }();
    LARGE_INTEGER c; QueryPerformanceCounter(&c);
    // same clock as Python time.perf_counter_ns() on Windows (QueryPerformanceCounter)
    return (int64_t)((double)c.QuadPart * 1e9 / (double)freq);
}

struct Mapping {
    HANDLE h = nullptr;
    uint8_t* base = nullptr;
    int64_t size = 0;
    static Mapping create(const std::wstring& name, int64_t size, bool large_pages = false) {
        Mapping m; m.size = size;
        DWORD prot = PAGE_READWRITE | (large_pages ? (SEC_COMMIT | SEC_LARGE_PAGES) : SEC_COMMIT);
        m.h = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, prot, (DWORD)(size >> 32), (DWORD)(size & 0xffffffff),
                                 name.empty() ? nullptr : name.c_str());
        if (!m.h) throw std::runtime_error("CreateFileMappingW failed, GetLastError=" + std::to_string(GetLastError()));
        m.base = (uint8_t*)MapViewOfFile(m.h, FILE_MAP_ALL_ACCESS | (large_pages ? FILE_MAP_LARGE_PAGES : 0), 0, 0, (SIZE_T)size);
        if (!m.base) throw std::runtime_error("MapViewOfFile failed, GetLastError=" + std::to_string(GetLastError()));
        return m;
    }
    static Mapping open(const std::wstring& name, int64_t size) {
        Mapping m; m.size = size;
        m.h = OpenFileMappingW(FILE_MAP_ALL_ACCESS, FALSE, name.c_str());
        if (!m.h) throw std::runtime_error("OpenFileMappingW failed, GetLastError=" + std::to_string(GetLastError()));
        m.base = (uint8_t*)MapViewOfFile(m.h, FILE_MAP_ALL_ACCESS, 0, 0, (SIZE_T)size);
        if (!m.base) throw std::runtime_error("MapViewOfFile failed, GetLastError=" + std::to_string(GetLastError()));
        return m;
    }
    void close() {
        if (base) UnmapViewOfFile(base);
        if (h) CloseHandle(h);
        base = nullptr; h = nullptr;
    }
};

struct RingSpec {
    int64_t L = 0;            // slots
    int64_t record_bytes = 0; // 632 + H*W*3
    int64_t stride = 0;       // slot stride in bytes
    int64_t total_bytes() const { return HDR + round4k(L * 8) + L * stride; }
};

inline RingSpec make_spec(int64_t h, int64_t w, bool aligned, int64_t mem_alloc = (1LL << 30)) {
    RingSpec s;
    s.record_bytes = META_BYTES + h * w * 3;
    s.L = mem_alloc / s.record_bytes;  // SkellyCam default: ONE_GIGABYTE // itemsize (ring_buffer_shared_memory.py L41-42)
    s.stride = aligned ? round4k(s.record_bytes) : s.record_bytes;
    return s;
}

struct Ring {
    RingSpec spec;
    uint8_t* base = nullptr;
    std::atomic<int64_t>* head() const { return reinterpret_cast<std::atomic<int64_t>*>(base + 0); }
    std::atomic<int64_t>* cursor() const { return reinterpret_cast<std::atomic<int64_t>*>(base + 64); }
    std::atomic<int64_t>* done() const { return reinterpret_cast<std::atomic<int64_t>*>(base + 128); }
    std::atomic<int64_t>* blocked() const { return reinterpret_cast<std::atomic<int64_t>*>(base + 192); }
    std::atomic<int64_t>* seq(int64_t slot) const { return reinterpret_cast<std::atomic<int64_t>*>(base + HDR) + slot; }
    uint8_t* slot(int64_t s) const { return base + HDR + round4k(spec.L * 8) + s * spec.stride; }

    void init() {
        head()->store(-1); cursor()->store(-1); done()->store(-1); blocked()->store(0);
        for (int64_t i = 0; i < spec.L; ++i) seq(i)->store(0, std::memory_order_relaxed);
    }

    // lossless gating: true if frame k may be written (slot k%L holds nothing unconsumed)
    bool can_write(int64_t k) const { return cursor()->load(std::memory_order_acquire) >= k - spec.L; }

    // seqlock publish of one record (one copy: src -> slot)
    void publish(int64_t k, const uint8_t* src) {
        int64_t s = k % spec.L;
        seq(s)->store(2 * k + 1, std::memory_order_relaxed);
        std::atomic_thread_fence(std::memory_order_release);
        std::memcpy(slot(s), src, (size_t)spec.record_bytes);
        seq(s)->store(2 * k + 2, std::memory_order_release);
        head()->store(k, std::memory_order_release);
    }

    // seqlock read of frame k into dst; returns 0 ok, 1 not yet stable / overwritten (seq mismatch)
    int read(int64_t k, uint8_t* dst) const {
        int64_t s = k % spec.L;
        int64_t s1 = seq(s)->load(std::memory_order_acquire);
        if (s1 != 2 * k + 2) return 1;
        std::memcpy(dst, slot(s), (size_t)spec.record_bytes);
        std::atomic_thread_fence(std::memory_order_acquire);
        int64_t s2 = seq(s)->load(std::memory_order_relaxed);
        return s2 == s1 ? 0 : 1;
    }
};

// stamps used for torn-read detection (same positions as the Python benchmarks)
inline void stamp(uint8_t* rec, int64_t record_bytes, int64_t k, int64_t pub_ns) {
    std::memcpy(rec + 0, &k, 8);
    std::memcpy(rec + 8, &pub_ns, 8);
    std::memcpy(rec + META_BYTES, &k, 8);
    std::memcpy(rec + record_bytes - 8, &k, 8);
}
inline bool check_stamp(const uint8_t* rec, int64_t record_bytes, int64_t k) {
    int64_t a, b, c;
    std::memcpy(&a, rec + 0, 8); std::memcpy(&b, rec + META_BYTES, 8); std::memcpy(&c, rec + record_bytes - 8, 8);
    return a == k && b == k && c == k;
}
inline int64_t stamp_pub_ns(const uint8_t* rec) { int64_t t; std::memcpy(&t, rec + 8, 8); return t; }

// high-resolution waitable timer sleep: the same primitive CPython 3.11+ uses for time.sleep on Windows
inline void hr_sleep_ns(int64_t ns) {
    thread_local HANDLE t = CreateWaitableTimerExW(nullptr, nullptr, CREATE_WAITABLE_TIMER_HIGH_RESOLUTION, TIMER_ALL_ACCESS);
    LARGE_INTEGER due; due.QuadPart = -(ns / 100);
    if (due.QuadPart == 0) due.QuadPart = -1;
    SetWaitableTimerEx(t, &due, 0, nullptr, nullptr, nullptr, 0);
    WaitForSingleObject(t, INFINITE);
}
// same pacing primitive as the Python benchmarks (proto_common.sleep_until): coarse sleep, then spin
inline void sleep_until_ns(int64_t t_ns) {
    for (;;) {
        int64_t rem = t_ns - qpc_ns();
        if (rem <= 0) return;
        if (rem > 2000000) hr_sleep_ns(rem - 1500000);
    }
}

struct Stats { int64_t n = 0; double median_ms = NAN, mean_ms = NAN, p99_ms = NAN, min_ms = NAN, max_ms = NAN; };
inline Stats stats_ns(std::vector<int64_t> v) {
    Stats s; s.n = (int64_t)v.size();
    if (v.empty()) return s;
    std::sort(v.begin(), v.end());
    auto q = [&](double p) {  // numpy.percentile default (linear interpolation)
        double pos = p / 100.0 * (double)(v.size() - 1);
        size_t lo = (size_t)std::floor(pos), hi = (size_t)std::ceil(pos);
        return ((double)v[lo] + ((double)v[hi] - (double)v[lo]) * (pos - (double)lo)) / 1e6;
    };
    double sum = 0; for (auto x : v) sum += (double)x;
    s.median_ms = q(50); s.p99_ms = q(99); s.min_ms = v.front() / 1e6; s.max_ms = v.back() / 1e6; s.mean_ms = sum / v.size() / 1e6;
    return s;
}
inline std::string stats_json(const Stats& s) {
    char b[256];
    snprintf(b, sizeof b, "{\"n\":%lld,\"median_ms\":%.6f,\"mean_ms\":%.6f,\"p99_ms\":%.6f,\"min_ms\":%.6f,\"max_ms\":%.6f}",
             (long long)s.n, s.median_ms, s.mean_ms, s.p99_ms, s.min_ms, s.max_ms);
    return b;
}

inline double process_cpu_s() {
    FILETIME c, e, k, u; GetProcessTimes(GetCurrentProcess(), &c, &e, &k, &u);
    auto f = [](FILETIME t) { return ((double)(((uint64_t)t.dwHighDateTime << 32) | t.dwLowDateTime)) / 1e7; };
    return f(k) + f(u);
}
inline double thread_cpu_s() {
    FILETIME c, e, k, u; GetThreadTimes(GetCurrentThread(), &c, &e, &k, &u);
    auto f = [](FILETIME t) { return ((double)(((uint64_t)t.dwHighDateTime << 32) | t.dwLowDateTime)) / 1e7; };
    return f(k) + f(u);
}

}  // namespace cr
