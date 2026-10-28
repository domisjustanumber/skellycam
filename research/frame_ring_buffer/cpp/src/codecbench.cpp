// codecbench.cpp - decode / encode / record in C++ with OpenCV 4.8.0 (official Windows build, opencv_world480)
// (NOT SkellyCam code). Python twin: ../py_codec.py (same inputs, frame counts, thread settings, process topology).
//
//   codecbench.exe buildinfo <out.txt>
//   codecbench.exe decode <720p|1080p> <nprocs> <run_s> <inputs_dir> <inplace 0|1> <out.json>
//       nprocs spawned processes, cv::setNumThreads(1) each, 30 q90 JPEGs per camera (seed = camera index, the same
//       files Python decodes), 2 s warm-up, then run_s unthrottled. Each decoded frame lands in a slot of a private
//       1 GiB pagefile-backed ring (4 KiB-aligned slots, prefaulted):
//         inplace 0: Mat m = imdecode(buf) then memcpy into the slot   (= Python cv2.imdecode + np.copyto into a slot,
//                    prototypes P1 row p_imdecode_copyslot)
//         inplace 1: imdecode(buf, IMREAD_COLOR, &dst) with dst a Mat header over the slot memory - C++-only API:
//                    OpenCV 4.12's Python binding has no dst for imdecode (prototypes README P1)
//   codecbench.exe imencode <720p|1080p> <run_s> <inputs_dir> <out.json>
//       1 process, setNumThreads(1): full-frame imencode q90, and the SkellyCam UI step
//       (resize 0.5 INTER_LINEAR + imencode q60, frontend_payload_bytearray.py L136-147, L34)
//   codecbench.exe videowriter <720p|1080p> <nprocs> <paced_fps|0> <nframes> <threads|-1> <inputs_dir> <tmp_dir> <out.json>
//       nprocs spawned processes, each cv::VideoWriter(path.mp4, fourcc 'X264', 60, (w, h)) with the default backend,
//       exactly the call in video_recorder.py L125-130; 60 distinct raw frames per camera (seed = camera index);
//       paced at paced_fps or unthrottled; times every write() and release(); counts frames in the file afterwards.
#include "ring.hpp"
#include <opencv2/core.hpp>
#include <opencv2/core/utility.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/videoio.hpp>
#include <cstdio>
#include <fstream>
#include <intrin.h>

using namespace cr;

struct Control { std::atomic<int64_t> ready, start, start_ns; char json[16][4096]; };

static void size_of(const std::string& s, int& h, int& w) { if (s == "720p") { h = 720; w = 1280; } else { h = 1080; w = 1920; } }
static std::vector<uint8_t> read_file(const std::string& p) {
    std::ifstream f(p, std::ios::binary); return std::vector<uint8_t>((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
}
static std::wstring ctl_name(DWORD pid) { return L"Local\\crcodec_ctl_" + std::to_wstring(pid); }

static HANDLE spawn(const std::wstring& args) {
    wchar_t exe[MAX_PATH]; GetModuleFileNameW(nullptr, exe, MAX_PATH);
    std::wstring cmd = L"\"" + std::wstring(exe) + L"\" " + args;
    STARTUPINFOW si{}; si.cb = sizeof si; PROCESS_INFORMATION pi{};
    std::vector<wchar_t> buf(cmd.begin(), cmd.end()); buf.push_back(0);
    if (!CreateProcessW(nullptr, buf.data(), nullptr, nullptr, FALSE, 0, nullptr, nullptr, &si, &pi))
        throw std::runtime_error("CreateProcessW failed");
    CloseHandle(pi.hThread);
    return pi.hProcess;
}
static std::wstring W(const std::string& s) { return std::wstring(s.begin(), s.end()); }

// ------------------------------------------------------------------------------------------------ decode child
static void decode_child(Control* ctl, int cam, const std::string& size, double run_s, const std::string& dir, bool inplace) {
    cv::setNumThreads(1);
    int h, w; size_of(size, h, w);
    std::vector<std::vector<uint8_t>> jpegs;
    for (int i = 0; i < 30; ++i) jpegs.push_back(read_file(dir + "\\" + size + "_seed" + std::to_string(cam) + "_" + std::to_string(i) + ".jpg"));
    int64_t n = (int64_t)h * w * 3, stride = round4k(n + META_BYTES), L = (1LL << 30) / stride;
    Mapping ring = Mapping::create(L"", L * stride);
    std::memset(ring.base, 0, (size_t)(L * stride));
    int64_t k = 0; bool inplace_ok = true;
    auto one = [&]() {
        uint8_t* img = ring.base + (k % L) * stride + META_BYTES;
        const auto& j = jpegs[k % 30];
        cv::Mat buf(1, (int)j.size(), CV_8UC1, (void*)j.data());
        if (inplace) {
            cv::Mat dst(h, w, CV_8UC3, img);
            cv::imdecode(buf, cv::IMREAD_COLOR, &dst);
            if (dst.data != img) inplace_ok = false;
        } else {
            cv::Mat m = cv::imdecode(buf, cv::IMREAD_COLOR);
            std::memcpy(img, m.data, (size_t)n);
        }
        ++k;
    };
    int64_t t_end = qpc_ns() + 2000000000LL; while (qpc_ns() < t_end) one();
    ctl->ready.fetch_add(1);
    while (!ctl->start.load()) _mm_pause();
    std::vector<int64_t> lat;
    double cpu0 = process_cpu_s();
    int64_t t0 = qpc_ns(), dl = t0 + (int64_t)(run_s * 1e9), cnt = 0;
    while (qpc_ns() < dl) { int64_t a = qpc_ns(); one(); lat.push_back(qpc_ns() - a); ++cnt; }
    double el = (qpc_ns() - t0) / 1e9, cpu = process_cpu_s() - cpu0;
    // content check: last decoded slot equals a fresh decode of the same JPEG
    cv::Mat ref = cv::imdecode(cv::Mat(1, (int)jpegs[(k - 1) % 30].size(), CV_8UC1, (void*)jpegs[(k - 1) % 30].data()), cv::IMREAD_COLOR);
    bool content_ok = std::memcmp(ref.data, ring.base + ((k - 1) % L) * stride + META_BYTES, (size_t)n) == 0;
    snprintf(ctl->json[cam], 4096, "{\"cam\":%d,\"n\":%lld,\"elapsed_s\":%.4f,\"fps\":%.2f,\"cpu_ms_per_frame\":%.4f,\"inplace_ok\":%d,\"content_ok\":%d,"
             "\"mean_jpeg_kb\":%.1f,\"lat\":%s}", cam, (long long)cnt, el, cnt / el, 1e3 * cpu / cnt, inplace_ok ? 1 : 0, content_ok ? 1 : 0,
             [&] { double s = 0; for (auto& j : jpegs) s += j.size(); return s / jpegs.size() / 1024; }(), stats_json(stats_ns(lat)).c_str());
    ring.close();
}

// ------------------------------------------------------------------------------------------------ videowriter child
static void vw_child(Control* ctl, int cam, const std::string& size, double paced, int64_t nframes, int threads,
                     const std::string& dir, const std::string& tmp) {
    if (threads >= 0) cv::setNumThreads(threads);
    int h, w; size_of(size, h, w);
    auto raw = read_file(dir + "\\" + size + "_seed" + std::to_string(cam) + ".raw");
    size_t fb = (size_t)h * w * 3; int nf = (int)(raw.size() / fb);
    std::string path = tmp + "\\cpp_vw_" + size + "_cam" + std::to_string(cam) + "_" + std::to_string(GetCurrentProcessId()) + ".mp4";
    int64_t c0 = qpc_ns();
    cv::VideoWriter vw(path, cv::VideoWriter::fourcc('X', '2', '6', '4'), 60.0, cv::Size(w, h));
    double create_s = (qpc_ns() - c0) / 1e9;
    std::string backend = vw.isOpened() ? vw.getBackendName() : "NOT_OPENED";
    ctl->ready.fetch_add(1);
    while (!ctl->start.load()) _mm_pause();
    int64_t t_start = ctl->start_ns.load();
    int64_t period = paced > 0 ? (int64_t)(1e9 / paced) : 0;
    std::vector<int64_t> lat; int64_t late = 0;
    double cpu0 = process_cpu_s();
    int64_t t0 = qpc_ns();
    for (int64_t i = 0; i < nframes; ++i) {
        if (period) sleep_until_ns(t_start + (i + 1) * period);
        cv::Mat f(h, w, CV_8UC3, raw.data() + (i % nf) * fb);
        int64_t a = qpc_ns(); vw.write(f); int64_t d = qpc_ns() - a;
        lat.push_back(d); if (d > 16667000) ++late;
    }
    int64_t loop_end = qpc_ns();
    vw.release();
    int64_t rel_end = qpc_ns();
    double cpu = process_cpu_s() - cpu0;
    double loop_s = (loop_end - t0) / 1e9, release_s = (rel_end - loop_end) / 1e9;
    // count frames in the file
    int64_t counted = 0;
    { cv::VideoCapture cap(path); cv::Mat m; while (cap.grab()) ++counted; }
    WIN32_FILE_ATTRIBUTE_DATA fa{}; GetFileAttributesExA(path.c_str(), GetFileExInfoStandard, &fa);
    int64_t fsize = ((int64_t)fa.nFileSizeHigh << 32) | fa.nFileSizeLow;
    snprintf(ctl->json[cam], 4096, "{\"cam\":%d,\"backend\":\"%s\",\"create_s\":%.4f,\"n\":%lld,\"loop_s\":%.4f,\"release_s\":%.4f,"
             "\"write_return_fps\":%.2f,\"encode_fps_incl_release\":%.2f,\"cpu_s\":%.4f,\"cpu_pct\":%.1f,\"late_writes\":%lld,\"frames_in_file\":%lld,"
             "\"file_bytes\":%lld,\"path\":\"%s\",\"lat\":%s}",
             cam, backend.c_str(), create_s, (long long)nframes, loop_s, release_s, nframes / loop_s, nframes / (loop_s + release_s), cpu,
             100.0 * cpu / (loop_s + release_s), (long long)late, (long long)counted, (long long)fsize, [&] { std::string p = path; for (auto& ch : p) if (ch == '\\') ch = '/'; return p; }().c_str(),
             stats_json(stats_ns(lat)).c_str());
}

// ------------------------------------------------------------------------------------------------ parent
static int run_multi(const std::wstring& child_args_fmt_prefix, int nprocs, const std::string& header, const std::string& out) {
    DWORD pid = GetCurrentProcessId();
    Mapping ctlm = Mapping::create(ctl_name(pid), sizeof(Control));
    Control* ctl = (Control*)ctlm.base; std::memset((void*)ctl, 0, sizeof(Control));
    std::vector<HANDLE> ps;
    for (int c = 0; c < nprocs; ++c) ps.push_back(spawn(L"child " + std::to_wstring(pid) + L" " + std::to_wstring(c) + L" " + child_args_fmt_prefix));
    int64_t tw = qpc_ns();
    while (ctl->ready.load() < nprocs) { Sleep(1); if (qpc_ns() - tw > 300e9) { fprintf(stderr, "timeout\n"); return 2; } }
    ctl->start_ns.store(qpc_ns() + 1000000); ctl->start.store(1);
    for (auto hp : ps) { WaitForSingleObject(hp, 900000); CloseHandle(hp); }
    std::string js = header + ",\"procs\":[";
    for (int c = 0; c < nprocs; ++c) { if (c) js += ","; js += ctl->json[c][0] ? ctl->json[c] : "null"; }
    js += "]}";
    printf("%s\n", js.c_str());
    FILE* f = fopen(out.c_str(), "wb"); if (f) { fputs(js.c_str(), f); fclose(f); }
    ctlm.close();
    return 0;
}

static int imencode_main(const std::string& size, double run_s, const std::string& dir, const std::string& out) {
    cv::setNumThreads(1);
    int h, w; size_of(size, h, w);
    auto raw = read_file(dir + "\\" + size + "_seed0.raw");
    size_t fb = (size_t)h * w * 3; int nf = std::min(30, (int)(raw.size() / fb));
    std::string js = "{\"tool\":\"codecbench\",\"mode\":\"imencode\",\"opencv\":\"" + std::string(CV_VERSION) + "\",\"size\":\"" + size + "\",\"rows\":[";
    for (int variant = 0; variant < 2; ++variant) {
        std::vector<uchar> enc; int64_t k = 0; double bytes = 0;
        cv::Mat small;
        auto one = [&]() {
            cv::Mat f(h, w, CV_8UC3, raw.data() + (k % nf) * fb);
            if (variant == 0) cv::imencode(".jpg", f, enc, {cv::IMWRITE_JPEG_QUALITY, 90});
            else { cv::resize(f, small, cv::Size(w / 2, h / 2), 0, 0, cv::INTER_LINEAR); cv::imencode(".jpg", small, enc, {cv::IMWRITE_JPEG_QUALITY, 60}); }
            bytes += enc.size(); ++k;
        };
        int64_t te = qpc_ns() + 2000000000LL; while (qpc_ns() < te) one();
        std::vector<int64_t> lat; bytes = 0; int64_t k0 = k;
        double cpu0 = process_cpu_s();
        int64_t t0 = qpc_ns(), dl = t0 + (int64_t)(run_s * 1e9);
        while (qpc_ns() < dl) { int64_t a = qpc_ns(); one(); lat.push_back(qpc_ns() - a); }
        double el = (qpc_ns() - t0) / 1e9, cpu = process_cpu_s() - cpu0; int64_t cnt = k - k0;
        char b[1024];
        snprintf(b, sizeof b, "%s{\"variant\":\"%s\",\"n\":%lld,\"fps\":%.2f,\"cpu_ms_per_frame\":%.4f,\"mean_kb\":%.1f,\"lat\":%s}", variant ? "," : "",
                 variant == 0 ? "imencode_q90_full" : "ui_resize05_linear_imencode_q60", (long long)cnt, cnt / el, 1e3 * cpu / cnt, bytes / cnt / 1024,
                 stats_json(stats_ns(lat)).c_str());
        js += b;
    }
    js += "]}";
    printf("%s\n", js.c_str());
    FILE* f = fopen(out.c_str(), "wb"); fputs(js.c_str(), f); fclose(f);
    return 0;
}

int main(int argc, char** argv) {
    try {
        std::string mode = argv[1];
        if (mode == "buildinfo") { FILE* f = fopen(argv[2], "wb"); fputs(cv::getBuildInformation().c_str(), f); fclose(f); return 0; }
        if (mode == "child") {
            DWORD ppid = (DWORD)std::stoul(argv[2]); int cam = std::stoi(argv[3]); std::string sub = argv[4];
            Mapping m = Mapping::open(ctl_name(ppid), sizeof(Control)); Control* ctl = (Control*)m.base;
            if (sub == "decode") decode_child(ctl, cam, argv[5], std::stod(argv[6]), argv[7], std::stoi(argv[8]) != 0);
            else vw_child(ctl, cam, argv[5], std::stod(argv[6]), std::stoll(argv[7]), std::stoi(argv[8]), argv[9], argv[10]);
            m.close(); return 0;
        }
        if (mode == "decode") {
            std::string size = argv[2]; int np = std::stoi(argv[3]); std::string run_s = argv[4], dir = argv[5], inplace = argv[6], out = argv[7];
            std::string hdr = "{\"tool\":\"codecbench\",\"mode\":\"decode\",\"lang\":\"cpp\",\"opencv\":\"" + std::string(CV_VERSION) + "\",\"size\":\"" + size +
                              "\",\"nprocs\":" + std::to_string(np) + ",\"run_s\":" + run_s + ",\"inplace\":" + inplace;
            return run_multi(L"decode " + W(size) + L" " + W(run_s) + L" \"" + W(dir) + L"\" " + W(inplace), np, hdr, out);
        }
        if (mode == "imencode") return imencode_main(argv[2], std::stod(argv[3]), argv[4], argv[5]);
        if (mode == "videowriter") {
            std::string size = argv[2]; int np = std::stoi(argv[3]); std::string paced = argv[4], nfr = argv[5], th = argv[6], dir = argv[7], tmp = argv[8], out = argv[9];
            std::string hdr = "{\"tool\":\"codecbench\",\"mode\":\"videowriter\",\"lang\":\"cpp\",\"opencv\":\"" + std::string(CV_VERSION) + "\",\"size\":\"" + size +
                              "\",\"nprocs\":" + std::to_string(np) + ",\"paced_fps\":" + paced + ",\"nframes\":" + nfr + ",\"threads\":" + th;
            return run_multi(L"vw " + W(size) + L" " + W(paced) + L" " + W(nfr) + L" " + W(th) + L" \"" + W(dir) + L"\" \"" + W(tmp) + L"\"", np, hdr, out);
        }
        fprintf(stderr, "unknown mode\n"); return 1;
    } catch (std::exception& e) { fprintf(stderr, "ERROR %s\n", e.what()); return 3; }
}
