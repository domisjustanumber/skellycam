// memcpybench.cpp - raw copy bandwidth, the ceiling Python and C++ share (NOT SkellyCam code).
// Python twin: ../py_memcpy.py (same sizes, scenarios, thread counts, timing rules).
//
//   memcpybench.exe <out.json> [rep_s=2] [reps=5]
//
// Sizes: 64x64x3 (12,288 B), 1280x720x3 (2,764,800 B), 1920x1080x3 (6,220,800 B) - image bytes only.
// Scenarios (single thread):
//   hot_hot      same private src -> same private dst every time (cache-resident at 720p; the L3 is 33 MB)
//   hot_to_ring  same private src -> dst cycles through a 512 MiB pagefile-backed mapping (prefaulted), like a writer
//                filling ring slots (= baseline a_write single_copy_reference shape)
//   cold_to_ring src cycles through a 512 MiB private buffer -> dst cycles through a 512 MiB mapping (both cold)
// Variants: memcpy (MSVC CRT), nt = AVX2 non-temporal (streaming) stores + sfence (a C++-only option: numpy has none).
// Threads: hot_to_ring with T = 1, 2, 4, 5, 8 threads, each with its own src and its own 512 MiB mapping; aggregate GB/s.
// Pixel ops (hypothesis C2, openpnp prior art shape): per-pixel BGR->RGB swap + vertical flip loop vs row-memcpy flip.
// Timing: 0.5 s warm-up, then `reps` throughput repetitions of `rep_s` seconds with no per-copy timer call (deadline
// checked every 64 copies); GB/s per rep = bytes copied / rep wall time, reported as median (min-max) over reps.
// Then a 1 s latency pass with every copy timed (QPC), at most 2M samples: median / p99 per copy.
#include "ring.hpp"
#include <immintrin.h>
#include <thread>
#include <barrier>
#include <cstdio>

using namespace cr;

static void nt_copy(uint8_t* dst, const uint8_t* src, size_t n) {
    // dst must be 32-byte aligned for streaming stores; slots are 4 KiB-strided here
    size_t i = 0;
    for (; i + 128 <= n; i += 128) {
        __m256i a = _mm256_loadu_si256((const __m256i*)(src + i));
        __m256i b = _mm256_loadu_si256((const __m256i*)(src + i + 32));
        __m256i c = _mm256_loadu_si256((const __m256i*)(src + i + 64));
        __m256i d = _mm256_loadu_si256((const __m256i*)(src + i + 96));
        _mm256_stream_si256((__m256i*)(dst + i), a);
        _mm256_stream_si256((__m256i*)(dst + i + 32), b);
        _mm256_stream_si256((__m256i*)(dst + i + 64), c);
        _mm256_stream_si256((__m256i*)(dst + i + 96), d);
    }
    if (i < n) std::memcpy(dst + i, src + i, n - i);
    _mm_sfence();
}

__declspec(noinline) static void do_copy(int variant, uint8_t* d, const uint8_t* s, size_t n) {
    if (variant == 0) std::memcpy(d, s, n); else nt_copy(d, s, n);
}

struct Row { std::string json; };
static std::vector<std::string> rows;

static uint8_t* alloc_private(size_t n) {
    uint8_t* p = (uint8_t*)VirtualAlloc(nullptr, n, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    for (size_t i = 0; i < n; i += 4096) p[i] = (uint8_t)i;  // prefault
    return p;
}

constexpr int64_t REGION = 512LL << 20;

// single-thread scenario run
static void run_single(const char* size_name, size_t n, const char* scen, int variant, double rep_s, int reps) {
    int64_t stride = round4k((int64_t)n);
    int64_t nslots = REGION / stride;
    uint8_t* src_hot = alloc_private(n);
    uint8_t* dst_hot = alloc_private(n);
    Mapping ring = Mapping::create(L"", REGION);
    std::memset(ring.base, 1, (size_t)REGION);   // prefault
    uint8_t* src_ring = nullptr;
    if (std::string(scen) == "cold_to_ring") { src_ring = alloc_private((size_t)REGION); std::memset(src_ring, 2, (size_t)REGION); }
    int64_t i = 0;
    auto one = [&]() {
        uint8_t* d; const uint8_t* s;
        if (std::string(scen) == "hot_hot") { d = dst_hot; s = src_hot; }
        else { d = ring.base + (i % nslots) * stride; s = src_ring ? src_ring + (i % nslots) * stride : src_hot; }
        do_copy(variant, d, s, n); ++i;
    };
    std::string sc = scen;
    int64_t t_end = qpc_ns() + 500000000LL;
    while (qpc_ns() < t_end) one();
    std::vector<int64_t> lat; std::vector<double> gbps;
    for (int r = 0; r < reps; ++r) {
        // throughput pass: no per-copy timer call; deadline checked every 64 copies
        int64_t t0 = qpc_ns(), dl = t0 + (int64_t)(rep_s * 1e9), cnt = 0, t = t0;
        while (t < dl) { for (int j = 0; j < 64; ++j) one(); cnt += 64; t = qpc_ns(); }
        gbps.push_back((double)cnt * n / ((t - t0) / 1e9) / 1e9);
    }
    {   // latency pass: 1 s, every copy timed, at most 2M samples
        int64_t dl = qpc_ns() + 1000000000LL;
        while (qpc_ns() < dl && lat.size() < 2000000) { int64_t a = qpc_ns(); one(); lat.push_back(qpc_ns() - a); }
    }
    std::sort(gbps.begin(), gbps.end());
    Stats s = stats_ns(lat);
    char b[1024];
    snprintf(b, sizeof b, "{\"lang\":\"cpp\",\"size\":\"%s\",\"bytes\":%zu,\"scenario\":\"%s\",\"variant\":\"%s\",\"threads\":1,"
             "\"gbps_median\":%.3f,\"gbps_min\":%.3f,\"gbps_max\":%.3f,\"lat\":%s}",
             size_name, n, scen, variant == 0 ? "memcpy" : "nt_avx2", gbps[gbps.size() / 2], gbps.front(), gbps.back(), stats_json(s).c_str());
    rows.push_back(b); printf("%s\n", b); fflush(stdout);
    VirtualFree(src_hot, 0, MEM_RELEASE); VirtualFree(dst_hot, 0, MEM_RELEASE);
    if (src_ring) VirtualFree(src_ring, 0, MEM_RELEASE);
    ring.close();
}

static void run_threads(const char* size_name, size_t n, int T, int variant, double rep_s, int reps) {
    int64_t stride = round4k((int64_t)n), nslots = REGION / stride;
    std::vector<Mapping> rings; std::vector<uint8_t*> srcs;
    for (int t = 0; t < T; ++t) {
        rings.push_back(Mapping::create(L"", REGION)); std::memset(rings.back().base, 1, (size_t)REGION);
        srcs.push_back(alloc_private(n));
    }
    std::vector<double> gbps;
    for (int r = -1; r < reps; ++r) {  // r = -1 is the warm-up rep (0.5 s)
        double dur = r < 0 ? 0.5 : rep_s;
        std::atomic<int64_t> total{0};
        std::atomic<int> go{0};
        std::atomic<int> readyc{0};
        int64_t t0 = 0;
        std::vector<std::thread> th;
        std::atomic<int64_t> t_start{0};
        for (int t = 0; t < T; ++t) th.emplace_back([&, t]() {
            readyc.fetch_add(1);
            while (!go.load()) _mm_pause();
            int64_t dl = t_start.load() + (int64_t)(dur * 1e9), cnt = 0, i = 0;
            while (qpc_ns() < dl) { do_copy(variant, rings[t].base + (i % nslots) * stride, srcs[t], n); ++i; ++cnt; }
            total.fetch_add(cnt);
        });
        while (readyc.load() < T) _mm_pause();
        t0 = qpc_ns(); t_start.store(t0); go.store(1);
        for (auto& x : th) x.join();
        double wall = (qpc_ns() - t0) / 1e9;
        if (r >= 0) gbps.push_back((double)total.load() * n / wall / 1e9);
    }
    std::sort(gbps.begin(), gbps.end());
    char b[512];
    snprintf(b, sizeof b, "{\"lang\":\"cpp\",\"size\":\"%s\",\"bytes\":%zu,\"scenario\":\"hot_to_ring_threads\",\"variant\":\"%s\",\"threads\":%d,"
             "\"gbps_median\":%.3f,\"gbps_min\":%.3f,\"gbps_max\":%.3f}",
             size_name, n, variant == 0 ? "memcpy" : "nt_avx2", T, gbps[gbps.size() / 2], gbps.front(), gbps.back());
    rows.push_back(b); printf("%s\n", b); fflush(stdout);
    for (auto& m : rings) m.close();
    for (auto p : srcs) VirtualFree(p, 0, MEM_RELEASE);
}

// C2: per-pixel swap+flip (openpnp-capture win/platformstream.cpp submitBuffer shape) vs row-memcpy flip
__declspec(noinline) static void swap_flip(uint8_t* dst, const uint8_t* src, int w, int h) {
    for (int y = 0; y < h; ++y) {
        const uint8_t* s = src + (size_t)(h - 1 - y) * w * 3; uint8_t* d = dst + (size_t)y * w * 3;
        for (int x = 0; x < w; ++x) { d[3 * x] = s[3 * x + 2]; d[3 * x + 1] = s[3 * x + 1]; d[3 * x + 2] = s[3 * x]; }
    }
}
__declspec(noinline) static void flip_rows(uint8_t* dst, const uint8_t* src, int w, int h) {
    for (int y = 0; y < h; ++y) std::memcpy(dst + (size_t)y * w * 3, src + (size_t)(h - 1 - y) * w * 3, (size_t)w * 3);
}
static void run_pixel(const char* size_name, int w, int h, int op, double rep_s, int reps) {
    size_t n = (size_t)w * h * 3;
    uint8_t* s = alloc_private(n); uint8_t* d = alloc_private(n);
    for (size_t i = 0; i < n; ++i) s[i] = (uint8_t)(i * 7);
    auto one = [&]() { if (op == 0) swap_flip(d, s, w, h); else flip_rows(d, s, w, h); };
    int64_t t_end = qpc_ns() + 500000000LL; while (qpc_ns() < t_end) one();
    std::vector<int64_t> lat;
    for (int r = 0; r < reps; ++r) { int64_t dl = qpc_ns() + (int64_t)(rep_s * 1e9); while (qpc_ns() < dl) { int64_t a = qpc_ns(); one(); lat.push_back(qpc_ns() - a); } }
    // correctness spot check
    bool ok = op == 0 ? (d[0] == s[(size_t)(h - 1) * w * 3 + 2]) : (d[0] == s[(size_t)(h - 1) * w * 3]);
    Stats st = stats_ns(lat);
    char b[512];
    snprintf(b, sizeof b, "{\"lang\":\"cpp\",\"size\":\"%s\",\"bytes\":%zu,\"scenario\":\"pixel_op\",\"variant\":\"%s\",\"threads\":1,\"check\":%d,\"lat\":%s}",
             size_name, n, op == 0 ? "swap_bgr_rgb_and_flip_loop" : "flip_rows_memcpy", ok ? 1 : 0, stats_json(st).c_str());
    rows.push_back(b); printf("%s\n", b); fflush(stdout);
    VirtualFree(s, 0, MEM_RELEASE); VirtualFree(d, 0, MEM_RELEASE);
}

int main(int argc, char** argv) {
    std::string out = argc > 1 ? argv[1] : "-";
    double rep_s = argc > 2 ? atof(argv[2]) : 2.0;
    int reps = argc > 3 ? atoi(argv[3]) : 5;
    struct S { const char* name; int w, h; } sizes[] = {{"64x64", 64, 64}, {"720p", 1280, 720}, {"1080p", 1920, 1080}};
    for (auto& z : sizes) {
        size_t n = (size_t)z.w * z.h * 3;
        run_single(z.name, n, "hot_hot", 0, rep_s, reps);
        run_single(z.name, n, "hot_to_ring", 0, rep_s, reps);
        run_single(z.name, n, "hot_to_ring", 1, rep_s, reps);
        run_single(z.name, n, "cold_to_ring", 0, rep_s, reps);
        run_single(z.name, n, "cold_to_ring", 1, rep_s, reps);
    }
    for (auto& z : sizes) {
        if (z.w == 64) continue;
        size_t n = (size_t)z.w * z.h * 3;
        for (int T : {1, 2, 4, 5, 8}) { run_threads(z.name, n, T, 0, rep_s, reps); run_threads(z.name, n, T, 1, rep_s, reps); }
        run_pixel(z.name, z.w, z.h, 0, rep_s, reps);
        run_pixel(z.name, z.w, z.h, 1, rep_s, reps);
    }
    std::string js = "{\"tool\":\"memcpybench\",\"rep_s\":" + std::to_string(rep_s) + ",\"reps\":" + std::to_string(reps) + ",\"rows\":[";
    for (size_t i = 0; i < rows.size(); ++i) { if (i) js += ","; js += rows[i]; }
    js += "]}";
    if (out != "-") { FILE* f = fopen(out.c_str(), "wb"); fputs(js.c_str(), f); fclose(f); }
    return 0;
}
