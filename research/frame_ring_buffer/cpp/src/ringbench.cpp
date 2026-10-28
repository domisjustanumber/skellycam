// ringbench.cpp - C++ equivalent of the Python ring-buffer workloads (NOT SkellyCam code).
//
//   ringbench.exe write <WxH|720p|1080p> <ncams> <head_port|one_copy> <run_s> <out.json>
//       Same workload as baseline/bench_a_write.py: N spawned writer processes, each with its own 1 GiB ring
//       (L = 1 GiB // record), one timed first lap, then all writers start together and write UNTHROTTLED for run_s,
//       timing every put. head_port = a line-by-line port of SkellyCam put_data (ring_buffer_shared_memory.py
//       L118-133): fresh heap temp (copy.copy), copy into the temp, copy the temp into the slot, free it, store the index.
//       one_copy = seqlock publish, one memcpy src -> slot (ring.hpp).
//   ringbench.exe spsc <size> <ncams> <paced_fps|0> <run_s> <proc|thread> <out.json>
//       N writer + N reader processes (or threads), one SPSC ring per camera, lossless gating (block policy), seqlock
//       publish/read, reader copies every frame out into a private buffer and verifies stamps.
//       paced_fps > 0: writer publishes run_s*paced_fps frames at that rate; 0: unthrottled for run_s.
//   ringbench.exe largepages        attempt a 1 GiB SEC_LARGE_PAGES mapping and report the result (hypothesis C4)
#include "ring.hpp"
#include <cstdio>
#include <thread>
#include <intrin.h>

using namespace cr;

struct alignas(64) Result {
    int64_t valid, role, cam, n;          // role 0 = writer, 1 = reader
    double elapsed_s, cpu_s;
    Stats first_lap, op, e2e;
    int64_t blocked_ns, blocked_events, torn, gaps, seq_rejects, verified;
};
struct Control {
    std::atomic<int64_t> ready;
    std::atomic<int64_t> start;
    std::atomic<int64_t> start_ns;
    Result results[32];
};

static void parse_size(const std::string& s, int64_t& h, int64_t& w) {
    if (s == "720p") { h = 720; w = 1280; return; }
    if (s == "1080p") { h = 1080; w = 1920; return; }
    auto x = s.find('x');
    w = std::stoll(s.substr(0, x)); h = std::stoll(s.substr(x + 1));
}

// noinline copy so that the compiler cannot forward memcpy(tmp<-src); memcpy(slot<-tmp) into one copy
__declspec(noinline) static void copy_bytes(uint8_t* dst, const uint8_t* src, size_t n) { std::memcpy(dst, src, n); }

static std::vector<uint8_t> make_record(int64_t rb, int64_t cam) {
    // like baseline make_frame_recarray: image = zeros + camera_index, metadata zeroed except the stamps
    std::vector<uint8_t> r((size_t)rb, (uint8_t)cam);
    std::memset(r.data(), 0, (size_t)META_BYTES);
    return r;
}

// ------------------------------------------------------------------------------------------------ write-only
static void writer_write_only(Ring ring, Control* ctl, int cam, bool head_port, double run_s) {
    const int64_t rb = ring.spec.record_bytes, L = ring.spec.L;
    auto src = make_record(rb, cam);
    std::vector<int64_t> first, lat; lat.reserve(4000000);
    int64_t k = -1;
    auto put = [&](int64_t kk) {
        if (head_port) {
            // index_to_write = last_written_index.value + 1 ; buffer[i % L] = copy(data) ; last_written_index.value = i
            int64_t i = ring.head()->load(std::memory_order_relaxed) + 1;
            uint8_t* tmp = new uint8_t[(size_t)rb];         // copy.copy: fresh allocation
            copy_bytes(tmp, src.data(), (size_t)rb);       //            + copy 1
            copy_bytes(ring.slot(i % L), tmp, (size_t)rb); // slot assignment: copy 2
            delete[] tmp;                                  // temp freed (refcount drop)
            ring.head()->store(i, std::memory_order_release);
        } else {
            ring.publish(kk, src.data());
        }
    };
    for (int64_t i = 0; i < L; ++i) {
        ++k; stamp(src.data(), rb, k, qpc_ns());
        int64_t t0 = qpc_ns(); put(k); first.push_back(qpc_ns() - t0);
    }
    ctl->ready.fetch_add(1);
    while (!ctl->start.load()) _mm_pause();
    double cpu0 = process_cpu_s();
    int64_t t_start = qpc_ns(), deadline = t_start + (int64_t)(run_s * 1e9), n = 0, t1 = 0;
    for (;;) {
        ++k; stamp(src.data(), rb, k, qpc_ns());
        int64_t t0 = qpc_ns(); put(k); t1 = qpc_ns();
        lat.push_back(t1 - t0); ++n;
        if (t1 >= deadline) break;
    }
    double elapsed = (qpc_ns() - t_start) / 1e9;
    int64_t last = ring.head()->load();
    Result& r = ctl->results[cam];
    r.role = 0; r.cam = cam; r.n = n; r.elapsed_s = elapsed; r.cpu_s = process_cpu_s() - cpu0;
    r.first_lap = stats_ns(first); r.op = stats_ns(lat);
    r.verified = check_stamp(ring.slot(last % L), rb, k) ? 1 : 0;
    r.valid = 1;
}

// ------------------------------------------------------------------------------------------------ SPSC
static void spsc_writer(Ring ring, Control* ctl, int cam, int slot_idx, double paced_fps, double run_s, bool use_thread_cpu) {
    const int64_t rb = ring.spec.record_bytes, L = ring.spec.L;
    auto src = make_record(rb, cam);
    // warm-up lap: touch every slot page in this process without publishing (same in every implementation)
    for (int64_t i = 0; i < L; ++i) std::memcpy(ring.slot(i), src.data(), (size_t)rb);
    std::vector<int64_t> lat; lat.reserve(4000000);
    ctl->ready.fetch_add(1);
    while (!ctl->start.load()) _mm_pause();
    double cpu0 = use_thread_cpu ? thread_cpu_s() : process_cpu_s();
    int64_t t_start = ctl->start_ns.load();
    int64_t period = paced_fps > 0 ? (int64_t)(1e9 / paced_fps) : 0;
    int64_t n_target = paced_fps > 0 ? (int64_t)(run_s * paced_fps) : INT64_MAX;
    int64_t deadline = paced_fps > 0 ? INT64_MAX : t_start + (int64_t)(run_s * 1e9);
    int64_t blocked_ns = 0, blocked_events = 0, k = 0;
    for (; k < n_target; ++k) {
        if (period) sleep_until_ns(t_start + (k + 1) * period);
        if (!ring.can_write(k)) {
            int64_t b0 = qpc_ns(); ++blocked_events;
            while (!ring.can_write(k)) Sleep(0);
            blocked_ns += qpc_ns() - b0;
        }
        int64_t t0 = qpc_ns();
        stamp(src.data(), rb, k, t0);
        ring.publish(k, src.data());
        int64_t t1 = qpc_ns();
        lat.push_back(t1 - t0);
        if (t1 >= deadline) { ++k; break; }
    }
    double elapsed = (qpc_ns() - t_start) / 1e9;
    ring.done()->store(k, std::memory_order_release);
    Result& r = ctl->results[slot_idx];
    r.role = 0; r.cam = cam; r.n = k; r.elapsed_s = elapsed;
    r.cpu_s = (use_thread_cpu ? thread_cpu_s() : process_cpu_s()) - cpu0;
    r.op = stats_ns(lat); r.blocked_ns = blocked_ns; r.blocked_events = blocked_events; r.valid = 1;
}

static void spsc_reader(Ring ring, Control* ctl, int cam, int slot_idx, bool use_thread_cpu) {
    const int64_t rb = ring.spec.record_bytes, L = ring.spec.L;
    std::vector<uint8_t> dst((size_t)rb, 0);
    for (int64_t i = 0; i < L; ++i) std::memcpy(dst.data(), ring.slot(i), (size_t)rb);  // warm-up lap (page faults)
    std::vector<int64_t> lat, e2e; lat.reserve(4000000); e2e.reserve(4000000);
    ctl->ready.fetch_add(1);
    while (!ctl->start.load()) _mm_pause();
    double cpu0 = use_thread_cpu ? thread_cpu_s() : process_cpu_s();
    int64_t t_start = ctl->start_ns.load();
    int64_t k = 0, torn = 0, rejects = 0;
    for (;;) {
        int64_t h = ring.head()->load(std::memory_order_acquire);
        if (h >= k) {
            int64_t t0 = qpc_ns();
            int rc = ring.read(k, dst.data());
            int64_t t1 = qpc_ns();
            if (rc != 0) { ++rejects; continue; }
            if (!check_stamp(dst.data(), rb, k)) ++torn;
            lat.push_back(t1 - t0);
            e2e.push_back(t1 - stamp_pub_ns(dst.data()));
            ring.cursor()->store(k, std::memory_order_release);
            ++k;
        } else {
            int64_t d = ring.done()->load(std::memory_order_acquire);
            if (d >= 0 && k >= d) break;
            Sleep(0);
        }
    }
    double elapsed = (qpc_ns() - t_start) / 1e9;
    Result& r = ctl->results[slot_idx];
    r.role = 1; r.cam = cam; r.n = k; r.elapsed_s = elapsed;
    r.cpu_s = (use_thread_cpu ? thread_cpu_s() : process_cpu_s()) - cpu0;
    r.op = stats_ns(lat); r.e2e = stats_ns(e2e); r.torn = torn; r.seq_rejects = rejects; r.gaps = 0; r.valid = 1;
}

// ------------------------------------------------------------------------------------------------ orchestration
static std::wstring wname(const std::string& prefix, DWORD pid, int i) {
    return std::wstring(L"Local\\crbench_") + std::wstring(prefix.begin(), prefix.end()) + L"_" + std::to_wstring(pid) + L"_" + std::to_wstring(i);
}

static HANDLE spawn(const std::wstring& args) {
    wchar_t exe[MAX_PATH]; GetModuleFileNameW(nullptr, exe, MAX_PATH);
    std::wstring cmd = L"\"" + std::wstring(exe) + L"\" " + args;
    STARTUPINFOW si{}; si.cb = sizeof si; PROCESS_INFORMATION pi{};
    std::vector<wchar_t> buf(cmd.begin(), cmd.end()); buf.push_back(0);
    if (!CreateProcessW(nullptr, buf.data(), nullptr, nullptr, FALSE, 0, nullptr, nullptr, &si, &pi))
        throw std::runtime_error("CreateProcessW failed " + std::to_string(GetLastError()));
    CloseHandle(pi.hThread);
    return pi.hProcess;
}

static std::string result_json(const Result& r) {
    char b[512];
    snprintf(b, sizeof b, "{\"role\":\"%s\",\"cam\":%lld,\"n\":%lld,\"elapsed_s\":%.6f,\"fps\":%.3f,\"cpu_s\":%.6f,\"cpu_ms_per_frame\":%.6f,"
             "\"blocked_ns\":%lld,\"blocked_events\":%lld,\"torn\":%lld,\"gaps\":%lld,\"seq_rejects\":%lld,\"verified\":%lld,",
             r.role == 0 ? "writer" : "reader", (long long)r.cam, (long long)r.n, r.elapsed_s, r.n / std::max(1e-9, r.elapsed_s), r.cpu_s,
             r.n ? 1e3 * r.cpu_s / r.n : 0.0, (long long)r.blocked_ns, (long long)r.blocked_events, (long long)r.torn, (long long)r.gaps,
             (long long)r.seq_rejects, (long long)r.verified);
    return std::string(b) + "\"first_lap\":" + stats_json(r.first_lap) + ",\"op\":" + stats_json(r.op) + ",\"e2e\":" + stats_json(r.e2e) + "}";
}

static int child_main(int argc, char** argv) {
    // child <write|spsc_w|spsc_r> <parent_pid> <cam> <slot_idx> <h> <w> <aligned> <head_port> <paced_fps> <run_s>
    std::string role = argv[2];
    DWORD ppid = (DWORD)std::stoul(argv[3]);
    int cam = std::stoi(argv[4]), slot_idx = std::stoi(argv[5]);
    int64_t h = std::stoll(argv[6]), w = std::stoll(argv[7]);
    bool aligned = std::stoi(argv[8]) != 0, head_port = std::stoi(argv[9]) != 0;
    double paced = std::stod(argv[10]), run_s = std::stod(argv[11]);
    Mapping ctlm = Mapping::open(wname("ctl", ppid, 0), sizeof(Control));
    Control* ctl = (Control*)ctlm.base;
    Ring ring; ring.spec = make_spec(h, w, aligned);
    Mapping m = Mapping::open(wname("ring", ppid, cam), ring.spec.total_bytes());
    ring.base = m.base;
    if (role == "write") writer_write_only(ring, ctl, cam, head_port, run_s);
    else if (role == "spsc_w") spsc_writer(ring, ctl, cam, slot_idx, paced, run_s, false);
    else spsc_reader(ring, ctl, cam, slot_idx, false);
    m.close(); ctlm.close();
    return 0;
}

static int run_parent(const std::string& mode, int64_t h, int64_t w, int ncams, bool head_port, double paced, double run_s,
                      bool threads, const std::string& out_path) {
    bool aligned = !head_port;  // head_port keeps SkellyCam's packed recarray stride; one_copy uses 4 KiB-aligned slots
    DWORD pid = GetCurrentProcessId();
    Mapping ctlm = Mapping::create(wname("ctl", pid, 0), sizeof(Control));
    Control* ctl = (Control*)ctlm.base;
    std::memset((void*)ctl, 0, sizeof(Control));
    std::vector<Mapping> maps; std::vector<Ring> rings;
    RingSpec spec = make_spec(h, w, aligned);
    for (int c = 0; c < ncams; ++c) {
        maps.push_back(Mapping::create(wname("ring", pid, c), spec.total_bytes()));
        Ring r; r.spec = spec; r.base = maps.back().base; r.init(); rings.push_back(r);
    }
    int n_roles = mode == "write" ? ncams : 2 * ncams;
    std::vector<HANDLE> procs; std::vector<std::thread> ths;
    for (int c = 0; c < ncams; ++c) {
        if (mode == "write") {
            wchar_t a[512];
            swprintf(a, 512, L"child write %lu %d %d %lld %lld %d %d 0 %f", pid, c, c, (long long)h, (long long)w, aligned ? 1 : 0, head_port ? 1 : 0, run_s);
            procs.push_back(spawn(a));
        } else if (!threads) {
            wchar_t a[512];
            swprintf(a, 512, L"child spsc_w %lu %d %d %lld %lld %d 0 %f %f", pid, c, 2 * c, (long long)h, (long long)w, aligned ? 1 : 0, paced, run_s);
            procs.push_back(spawn(a));
            swprintf(a, 512, L"child spsc_r %lu %d %d %lld %lld %d 0 %f %f", pid, c, 2 * c + 1, (long long)h, (long long)w, aligned ? 1 : 0, paced, run_s);
            procs.push_back(spawn(a));
        } else {
            ths.emplace_back(spsc_writer, rings[c], ctl, c, 2 * c, paced, run_s, true);
            ths.emplace_back(spsc_reader, rings[c], ctl, c, 2 * c + 1, true);
        }
    }
    int64_t t_wait = qpc_ns();
    while (ctl->ready.load() < n_roles) {
        Sleep(1);
        if (qpc_ns() - t_wait > 300e9) { fprintf(stderr, "timeout waiting for ready\n"); return 2; }
    }
    ctl->start_ns.store(qpc_ns() + 1000000);  // common start, 1 ms ahead
    ctl->start.store(1);
    double cpu0 = process_cpu_s();
    for (auto& t : ths) t.join();
    for (auto hp : procs) { WaitForSingleObject(hp, 600000); CloseHandle(hp); }
    double parent_cpu = process_cpu_s() - cpu0;
    // JSON
    std::string js = "{\"tool\":\"ringbench\",\"mode\":\"" + mode + "\",\"impl\":\"" + (head_port ? "cpp_head_port" : "cpp_one_copy") +
                     "\",\"topology\":\"" + (threads ? "thread" : "process") + "\",\"h\":" + std::to_string(h) + ",\"w\":" + std::to_string(w) +
                     ",\"ncams\":" + std::to_string(ncams) + ",\"paced_fps\":" + std::to_string(paced) + ",\"run_s\":" + std::to_string(run_s) +
                     ",\"ring_len\":" + std::to_string(spec.L) + ",\"record_bytes\":" + std::to_string(spec.record_bytes) +
                     ",\"slot_stride\":" + std::to_string(spec.stride) + ",\"parent_cpu_s\":" + std::to_string(parent_cpu) + ",\"roles\":[";
    for (int i = 0; i < n_roles; ++i) { if (i) js += ","; js += result_json(ctl->results[i]); }
    js += "]}";
    printf("%s\n", js.c_str());
    if (!out_path.empty() && out_path != "-") { FILE* f = fopen(out_path.c_str(), "wb"); if (f) { fputs(js.c_str(), f); fclose(f); } }
    for (auto& m : maps) m.close();
    ctlm.close();
    return 0;
}

static int largepages() {
    // Hypothesis C4: SEC_LARGE_PAGES needs SeLockMemoryPrivilege enabled in the token.
    HANDLE tok; TOKEN_PRIVILEGES tp{}; LUID luid;
    BOOL ok_tok = OpenProcessToken(GetCurrentProcess(), TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY, &tok);
    BOOL ok_luid = LookupPrivilegeValueW(nullptr, L"SeLockMemoryPrivilege", &luid);
    tp.PrivilegeCount = 1; tp.Privileges[0].Luid = luid; tp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED;
    BOOL ok_adj = ok_tok && ok_luid ? AdjustTokenPrivileges(tok, FALSE, &tp, 0, nullptr, nullptr) : FALSE;
    DWORD adj_err = GetLastError();  // ERROR_NOT_ALL_ASSIGNED (1300) = privilege not held
    SIZE_T lp = GetLargePageMinimum();
    std::string result;
    try { Mapping m = Mapping::create(L"", 1LL << 30, true); result = "ok"; m.close(); }
    catch (std::exception& e) { result = e.what(); }
    printf("{\"tool\":\"ringbench\",\"mode\":\"largepages\",\"large_page_minimum\":%zu,\"adjust_token_ok\":%d,\"adjust_last_error\":%lu,"
           "\"create_1GiB_sec_large_pages\":\"%s\"}\n", lp, (int)ok_adj, adj_err, result.c_str());
    return 0;
}

int main(int argc, char** argv) {
    try {
        if (argc < 2) { fprintf(stderr, "usage: see header\n"); return 1; }
        std::string mode = argv[1];
        if (mode == "child") return child_main(argc, argv);
        if (mode == "largepages") return largepages();
        int64_t h, w; parse_size(argv[2], h, w);
        int ncams = std::stoi(argv[3]);
        if (mode == "write") return run_parent("write", h, w, ncams, std::string(argv[4]) == "head_port", 0, std::stod(argv[5]), false, argc > 6 ? argv[6] : "");
        if (mode == "spsc") return run_parent("spsc", h, w, ncams, false, std::stod(argv[4]), std::stod(argv[5]), std::string(argv[6]) == "thread", argc > 7 ? argv[7] : "");
        fprintf(stderr, "unknown mode\n"); return 1;
    } catch (std::exception& e) { fprintf(stderr, "ERROR %s\n", e.what()); return 3; }
}
