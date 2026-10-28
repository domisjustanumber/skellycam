// microbench.cpp - per-operation fixed costs in C++ (NOT SkellyCam code). Python twin: ../py_micro.py
//
//   microbench.exe <out.json>
//
// 1. control-plane ops on a pagefile-backed mapping: atomic int64 store(release) / load(acquire), timer read (QPC).
//    Measured as throughput over 10M ops x 5 reps (ns/op), the same way py_micro.py measures its ops.
// 2. cross-process ping-pong latency: two processes bounce an int64 counter through a shared mapping (pure spin);
//    200,000 round trips after 10,000 warm-up; per-round-trip latency median / p99.
// 3. sleep granularity: Sleep(0), Sleep(1), std::this_thread::sleep_for(10us), high-resolution waitable timer for
//    10 us / 100 us / 1 ms (CPython 3.11+ time.sleep uses that timer on Windows); 500 samples each.
#include "ring.hpp"
#include <thread>
#include <chrono>
#include <cstdio>
#include <intrin.h>

using namespace cr;
static std::vector<std::string> rows;
static void add(const std::string& s) { rows.push_back(s); printf("%s\n", s.c_str()); fflush(stdout); }

static int pong_child(const wchar_t* name, int64_t n) {
    Mapping m = Mapping::open(name, 4096);
    auto* a = reinterpret_cast<std::atomic<int64_t>*>(m.base);        // ping (parent writes)
    auto* b = reinterpret_cast<std::atomic<int64_t>*>(m.base + 64);   // pong (child writes)
    for (int64_t i = 1; i <= n; ++i) {
        while (a->load(std::memory_order_acquire) != i) _mm_pause();
        b->store(i, std::memory_order_release);
    }
    m.close();
    return 0;
}

int main(int argc, char** argv) {
    if (argc > 1 && std::string(argv[1]) == "pong") {
        std::wstring nm(argv[2], argv[2] + strlen(argv[2]));
        return pong_child(nm.c_str(), std::stoll(argv[3]));
    }
    std::string out = argc > 1 ? argv[1] : "-";
    // ---- 1. control-plane ops
    {
        Mapping m = Mapping::create(L"", 4096);
        auto* x = reinterpret_cast<std::atomic<int64_t>*>(m.base);
        const int64_t N = 10000000;
        auto bench = [&](const char* name, auto fn) {
            std::vector<double> ns;
            for (int r = 0; r < 6; ++r) {
                int64_t t0 = qpc_ns();
                for (int64_t i = 0; i < N; ++i) fn(i);
                double v = (double)(qpc_ns() - t0) / N;
                if (r > 0) ns.push_back(v);  // rep 0 = warm-up
            }
            std::sort(ns.begin(), ns.end());
            char b[256]; snprintf(b, sizeof b, "{\"lang\":\"cpp\",\"group\":\"control_op\",\"op\":\"%s\",\"ns_per_op_median\":%.3f,\"ns_min\":%.3f,\"ns_max\":%.3f}",
                                  name, ns[ns.size() / 2], ns.front(), ns.back());
            add(b);
        };
        volatile int64_t sink = 0;
        bench("atomic_int64_store_release_shm", [&](int64_t i) { x->store(i, std::memory_order_release); });
        bench("atomic_int64_load_acquire_shm", [&](int64_t) { sink = x->load(std::memory_order_acquire); });
        bench("qpc_timer_read", [&](int64_t) { sink = qpc_ns(); });
        m.close();
    }
    // ---- 2. cross-process ping-pong
    {
        const int64_t N = 210000, WARM = 10000;
        std::wstring nm = L"Local\\crbench_pingpong_" + std::to_wstring(GetCurrentProcessId());
        Mapping m = Mapping::create(nm, 4096);
        auto* a = reinterpret_cast<std::atomic<int64_t>*>(m.base);
        auto* b = reinterpret_cast<std::atomic<int64_t>*>(m.base + 64);
        a->store(0); b->store(0);
        wchar_t exe[MAX_PATH]; GetModuleFileNameW(nullptr, exe, MAX_PATH);
        std::wstring cmd = L"\"" + std::wstring(exe) + L"\" pong " + nm + L" " + std::to_wstring(N);
        STARTUPINFOW si{}; si.cb = sizeof si; PROCESS_INFORMATION pi{};
        std::vector<wchar_t> buf(cmd.begin(), cmd.end()); buf.push_back(0);
        CreateProcessW(nullptr, buf.data(), nullptr, nullptr, FALSE, 0, nullptr, nullptr, &si, &pi);
        std::vector<int64_t> lat; lat.reserve(N);
        for (int64_t i = 1; i <= N; ++i) {
            int64_t t0 = qpc_ns();
            a->store(i, std::memory_order_release);
            while (b->load(std::memory_order_acquire) != i) _mm_pause();
            if (i > WARM) lat.push_back(qpc_ns() - t0);
        }
        WaitForSingleObject(pi.hProcess, 10000); CloseHandle(pi.hProcess); CloseHandle(pi.hThread);
        Stats s = stats_ns(lat);
        add(std::string("{\"lang\":\"cpp\",\"group\":\"pingpong\",\"op\":\"atomic_int64_spin_cross_process_round_trip\",\"lat\":") + stats_json(s) + "}");
        m.close();
    }
    // ---- 3. sleep granularity
    {
        auto bench = [&](const char* name, auto fn) {
            std::vector<int64_t> lat;
            for (int i = 0; i < 520; ++i) { int64_t t0 = qpc_ns(); fn(); if (i >= 20) lat.push_back(qpc_ns() - t0); }
            add(std::string("{\"lang\":\"cpp\",\"group\":\"sleep\",\"op\":\"") + name + "\",\"lat\":" + stats_json(stats_ns(lat)) + "}");
        };
        bench("Sleep(0)", [] { Sleep(0); });
        bench("Sleep(1)", [] { Sleep(1); });
        bench("this_thread::sleep_for(10us)", [] { std::this_thread::sleep_for(std::chrono::microseconds(10)); });
        bench("hr_waitable_timer(10us)", [] { hr_sleep_ns(10000); });
        bench("hr_waitable_timer(100us)", [] { hr_sleep_ns(100000); });
        bench("hr_waitable_timer(1ms)", [] { hr_sleep_ns(1000000); });
    }
    std::string js = "{\"tool\":\"microbench\",\"rows\":[";
    for (size_t i = 0; i < rows.size(); ++i) { if (i) js += ","; js += rows[i]; }
    js += "]}";
    if (out != "-") { FILE* f = fopen(out.c_str(), "wb"); fputs(js.c_str(), f); fclose(f); }
    return 0;
}
