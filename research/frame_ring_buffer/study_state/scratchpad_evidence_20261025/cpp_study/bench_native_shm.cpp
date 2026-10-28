// Native baseline for the "would C++ help?" study.
// Build (from a vcvars64 shell):  cl /O2 /EHsc /std:c++20 bench_native_shm.cpp
// Run:                            bench_native_shm.exe > bench_native_shm.out.txt
// Measures:
//   1. memcpy of 720p/1080p BGR frames into a CreateFileMapping (pagefile-backed) ring, cold slots
//   2. aggregate memcpy bandwidth with 1/2/5/8 threads, each writing its own "camera" ring
//   3. std::atomic<int64_t> store/load cost on a shared-memory index (vs Python SharedMemoryNumber)
//   4. per-pixel BGR->RGB + vertical flip loop as in openpnp-capture win/platformstream.cpp submitBuffer
#include <windows.h>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <thread>
#include <vector>
#include <algorithm>
#include <cstdint>

using clk = std::chrono::steady_clock;

static double median(std::vector<double> v) { std::sort(v.begin(), v.end()); return v[v.size() / 2]; }

struct Mapping {
    HANDLE h = nullptr; uint8_t* p = nullptr; size_t sz = 0;
    explicit Mapping(size_t bytes) : sz(bytes) {
        h = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE,
                               (DWORD)(bytes >> 32), (DWORD)(bytes & 0xffffffff), nullptr);
        p = (uint8_t*)MapViewOfFile(h, FILE_MAP_ALL_ACCESS, 0, 0, bytes);
        // touch every page once (first-touch page faults are a separate, one-time cost)
        for (size_t i = 0; i < bytes; i += 4096) p[i] = 0;
    }
    ~Mapping() { UnmapViewOfFile(p); CloseHandle(h); }
};

int main() {
    struct Sz { const char* name; size_t w, h; } sizes[] = {{"720p", 1280, 720}, {"1080p", 1920, 1080}};
    const size_t RING_BYTES = 1ull << 30;  // 1 GiB, same as SkellyCam default allocation

    std::printf("=== 1. single-thread memcpy into CreateFileMapping ring (cold slots) ===\n");
    for (auto& s : sizes) {
        size_t fb = s.w * s.h * 3;
        Mapping m(RING_BYTES);
        size_t slots = RING_BYTES / fb;
        std::vector<uint8_t> src(fb, 7);
        std::vector<double> us;
        for (int i = 0; i < 400; ++i) {
            auto t0 = clk::now();
            std::memcpy(m.p + (i % slots) * fb, src.data(), fb);
            us.push_back(std::chrono::duration<double, std::micro>(clk::now() - t0).count());
        }
        double med = median(us);
        std::printf("%-6s %zu B: median %8.1f us  ~%6.2f GB/s\n", s.name, fb, med, fb / (med * 1e-6) / 1e9);
    }

    std::printf("\n=== 2. aggregate memcpy bandwidth, N threads each with own 1080p camera ring ===\n");
    for (int nthreads : {1, 2, 5, 8}) {
        size_t fb = 1920 * 1080 * 3;
        std::vector<Mapping*> maps;
        size_t per = 256ull << 20;  // 256 MiB per camera
        for (int t = 0; t < nthreads; ++t) maps.push_back(new Mapping(per));
        std::atomic<bool> go{false}, stop{false};
        std::vector<uint64_t> counts(nthreads, 0);
        std::vector<std::thread> th;
        for (int t = 0; t < nthreads; ++t) th.emplace_back([&, t] {
            std::vector<uint8_t> src(fb, (uint8_t)t);
            size_t slots = per / fb; uint64_t i = 0;
            while (!go.load()) {}
            while (!stop.load(std::memory_order_relaxed)) {
                std::memcpy(maps[t]->p + (i % slots) * fb, src.data(), fb); ++i;
            }
            counts[t] = i;
        });
        go = true;
        std::this_thread::sleep_for(std::chrono::milliseconds(1500));
        stop = true;
        for (auto& x : th) x.join();
        uint64_t tot = 0; for (auto c : counts) tot += c;
        double fps = tot / 1.5;
        std::printf("%d threads: %9.0f frames/s total  %6.2f GB/s written  (%7.0f fps per thread)\n",
                    nthreads, fps, fps * fb / 1e9, fps / nthreads);
        for (auto* m : maps) delete m;
    }

    std::printf("\n=== 3. std::atomic<int64_t> on shared mapping ===\n");
    {
        Mapping m(4096);
        auto* a = reinterpret_cast<std::atomic<int64_t>*>(m.p);
        const int N = 10000000;
        auto t0 = clk::now();
        for (int i = 0; i < N; ++i) a->store(i, std::memory_order_release);
        double st_ns = std::chrono::duration<double, std::nano>(clk::now() - t0).count() / N;
        int64_t acc = 0;
        t0 = clk::now();
        for (int i = 0; i < N; ++i) acc += a->load(std::memory_order_acquire);
        double ld_ns = std::chrono::duration<double, std::nano>(clk::now() - t0).count() / N;
        std::printf("store(release): %.2f ns   load(acquire): %.2f ns   (acc=%lld)\n", st_ns, ld_ns, (long long)acc);
    }

    std::printf("\n=== 4. openpnp-capture-style per-pixel BGR->RGB + vflip loop (win/platformstream.cpp submitBuffer) ===\n");
    for (auto& s : sizes) {
        size_t fb = s.w * s.h * 3;
        std::vector<uint8_t> src(fb, 3), dst(fb);
        std::vector<double> us;
        for (int it = 0; it < 200; ++it) {
            auto t0 = clk::now();
            for (size_t y = 0; y < s.h; y++) {
                uint8_t* d = &dst[(y * s.w) * 3];
                const uint8_t* p = src.data() + (s.w * 3) * (s.h - y - 1);
                for (size_t x = 0; x < s.w; x++) { uint8_t b = *p++, g = *p++, r = *p++; *d++ = r; *d++ = g; *d++ = b; }
            }
            us.push_back(std::chrono::duration<double, std::micro>(clk::now() - t0).count());
        }
        std::vector<double> us2;
        for (int it = 0; it < 200; ++it) {
            auto t0 = clk::now();
            for (size_t y = 0; y < s.h; y++)
                std::memcpy(&dst[(y * s.w) * 3], src.data() + (s.w * 3) * (s.h - y - 1), s.w * 3);
            us2.push_back(std::chrono::duration<double, std::micro>(clk::now() - t0).count());
        }
        std::printf("%-6s swap+flip loop: median %8.1f us | flip-only row memcpy: median %8.1f us (dst[0]=%d)\n",
                    s.name, median(us), median(us2), dst[0]);
    }
    return 0;
}
