// mf_multi_open.cpp -- open N UVC cameras at once through Media Foundation (IMFSourceReader) and report,
// per camera, which step succeeded or failed (with the HRESULT), first-sample latency, steady-state fps,
// payload bytes/s and stalls. Goal 3 (USB bandwidth) harness for the skellycam USB camera investigation.
//
// The camera's NATIVE media type is selected with converters disabled, so MJPG samples are the
// compressed payload exactly as delivered by usbvideo.sys (sample size = JPEG size), YUY2 = raw size.
//
// Build: research\usb_cameras\bandwidth\build.bat   (cl /EHsc /O2 /std:c++17, MSVC 14.42, SDK 10.0.22621)
// Usage:
//   mf_multi_open.exe --list
//   mf_multi_open.exe --cam "vid_046d&pid_085c:MJPG:1280x720@30" [--cam ...] [--seconds 8]
//        [--exposure -7] [--wb 4500] [--stagger-ms 0] [--out result.json] [--save-dir DIR [--save-max 300]]
//   mf_multi_open.exe --list [--list-match SUB ...]   (with --list-match only devices whose link contains SUB
//        are activated; the others are listed by name/link only, never opened)
//   --arrivals  (2026-10-27) also write arrivals_ms (host QPC per sample) and sizes_all to the JSON
//   --save-dir  (2026-10-27) write each camera's first --save-max samples, byte-exact as delivered, to
//               DIR/cam<k>/frame_<n>.jpg (MJPG) or .raw (other subtypes); k = --cam order
//   --cam   <symlink-substring>:<MJPG|YUY2|NV12|H264>:<W>x<H>@<fps>
//   --exposure  IAMCameraControl CameraControl_Exposure (log2 seconds), set Manual; previous value restored
//   --wb        IAMVideoProcAmp VideoProcAmp_WhiteBalance (Kelvin), set Manual; previous value restored
// Prints "STREAMING" on stdout once every camera has delivered a first sample or failed (so a wrapper
// can snapshot the hub's open pipes while streams run), then keeps streaming until --seconds elapse.
// Exit code: 0 if all cameras streamed, 2 if any failed, 1 on usage error.

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfreadwrite.h>
#include <mferror.h>
#include <strmif.h>
#include <atomic>
#include <cstdio>
#include <cstdint>
#include <string>
#include <thread>
#include <vector>
#include <algorithm>
#include <sstream>
#include <mutex>
#include <filesystem>

#pragma comment(lib, "mfplat.lib")
#pragma comment(lib, "mf.lib")
#pragma comment(lib, "mfreadwrite.lib")
#pragma comment(lib, "mfuuid.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "strmiids.lib")

template <class T> static void SafeRelease(T** p) { if (*p) { (*p)->Release(); *p = nullptr; } }

static std::string W2U(const wchar_t* w) {
    if (!w) return "";
    int n = WideCharToMultiByte(CP_UTF8, 0, w, -1, nullptr, 0, nullptr, nullptr);
    std::string s(n > 0 ? n - 1 : 0, '\0');
    if (n > 1) WideCharToMultiByte(CP_UTF8, 0, w, -1, &s[0], n, nullptr, nullptr);
    return s;
}
static std::string lower(std::string s) { for (auto& c : s) c = (char)tolower((unsigned char)c); return s; }
static std::string jesc(const std::string& s) {
    std::string o;
    for (char c : s) {
        if (c == '"' || c == '\\') { o += '\\'; o += c; }
        else if ((unsigned char)c < 0x20) { char b[8]; snprintf(b, sizeof b, "\\u%04x", c); o += b; }
        else o += c;
    }
    return o;
}
static std::string hrs(HRESULT hr) { char b[16]; snprintf(b, sizeof b, "0x%08lX", (unsigned long)hr); return b; }
static std::string hrmsg(HRESULT hr) {
    wchar_t* buf = nullptr;
    FormatMessageW(FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS, nullptr, hr, 0, (LPWSTR)&buf, 0, nullptr);
    if (!buf) {  // MF errors live in mferror.dll
        HMODULE m = LoadLibraryExW(L"mferror.dll", nullptr, LOAD_LIBRARY_AS_DATAFILE);
        if (m) {
            FormatMessageW(FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_HMODULE | FORMAT_MESSAGE_IGNORE_INSERTS, m, hr, 0, (LPWSTR)&buf, 0, nullptr);
            FreeLibrary(m);
        }
    }
    std::string s = buf ? W2U(buf) : "";
    if (buf) LocalFree(buf);
    while (!s.empty() && (s.back() == '\n' || s.back() == '\r' || s.back() == ' ')) s.pop_back();
    return s;
}
static double qpc_ms() {
    static LARGE_INTEGER f = [] { LARGE_INTEGER x; QueryPerformanceFrequency(&x); return x; }();
    LARGE_INTEGER t; QueryPerformanceCounter(&t);
    return (double)t.QuadPart * 1000.0 / (double)f.QuadPart;
}
static std::string subtype_name(const GUID& g) {
    if (g == MFVideoFormat_MJPG) return "MJPG";
    if (g == MFVideoFormat_YUY2) return "YUY2";
    if (g == MFVideoFormat_NV12) return "NV12";
    if (g == MFVideoFormat_H264) return "H264";
    if (g == MFVideoFormat_RGB24) return "RGB24";
    char b[8] = {0}; memcpy(b, &g.Data1, 4);
    for (int i = 0; i < 4; i++) if (b[i] < 32 || b[i] > 126) b[i] = '?';
    return b;
}
static bool subtype_from(const std::string& s, GUID* g) {
    if (s == "MJPG") { *g = MFVideoFormat_MJPG; return true; }
    if (s == "YUY2") { *g = MFVideoFormat_YUY2; return true; }
    if (s == "NV12") { *g = MFVideoFormat_NV12; return true; }
    if (s == "H264") { *g = MFVideoFormat_H264; return true; }
    return false;
}

struct Dev { std::string name, link; IMFActivate* act = nullptr; };

static std::vector<Dev> enum_devices() {
    std::vector<Dev> out;
    IMFAttributes* a = nullptr;
    MFCreateAttributes(&a, 1);
    a->SetGUID(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE, MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID);
    IMFActivate** devs = nullptr; UINT32 n = 0;
    if (SUCCEEDED(MFEnumDeviceSources(a, &devs, &n))) {
        for (UINT32 i = 0; i < n; i++) {
            Dev d;
            WCHAR* w = nullptr; UINT32 l = 0;
            if (SUCCEEDED(devs[i]->GetAllocatedString(MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME, &w, &l))) { d.name = W2U(w); CoTaskMemFree(w); }
            if (SUCCEEDED(devs[i]->GetAllocatedString(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK, &w, &l))) { d.link = W2U(w); CoTaskMemFree(w); }
            d.act = devs[i];
            out.push_back(d);
        }
        CoTaskMemFree(devs);
    }
    SafeRelease(&a);
    return out;
}

struct Spec { std::string match, subtype_s; GUID subtype{}; UINT32 w = 0, h = 0; double fps = 0; std::string raw; };

struct Result {
    Spec spec;
    std::string name, link, failed_stage, error_hr, error_msg;
    std::string chosen_type;
    double t_create_ms = 0, t_first_sample_ms = -1, t_end_ms = 0;
    std::vector<double> arrivals;
    std::vector<uint32_t> sizes;
    std::vector<std::string> read_errors;
    uint32_t stream_ticks = 0, read_err_count = 0;
    long exp_prev = 0, exp_prev_flags = 0, wb_prev = 0, wb_prev_flags = 0;
    bool exp_set = false, wb_set = false;
    std::string exp_hr, wb_hr;
    bool streamed = false;
    int index = 0;
    uint32_t saved = 0;
};
static std::string g_save_dir; static uint32_t g_save_max = 300; static bool g_arrivals = false;

static std::atomic<int> g_ready{0};

static void run_cam(Result* r, IMFActivate* act, double t0, double t_stop, long exposure, bool set_exp, long wb, bool set_wb, double start_at) {
    HRESULT hr;
    IMFMediaSource* src = nullptr;
    IMFSourceReader* rd = nullptr;
    IMFAttributes* ra = nullptr;
    IAMCameraControl* cc = nullptr;
    IAMVideoProcAmp* pa = nullptr;
    double tc = qpc_ms();
    auto fail = [&](const char* stage, HRESULT h) { r->failed_stage = stage; r->error_hr = hrs(h); r->error_msg = hrmsg(h); };
    hr = act->ActivateObject(IID_PPV_ARGS(&src));
    if (FAILED(hr)) { fail("ActivateObject", hr); g_ready++; return; }
    if (set_exp && SUCCEEDED(src->QueryInterface(IID_PPV_ARGS(&cc)))) {
        cc->Get(CameraControl_Exposure, &r->exp_prev, &r->exp_prev_flags);
        HRESULT h2 = cc->Set(CameraControl_Exposure, exposure, CameraControl_Flags_Manual);
        r->exp_set = SUCCEEDED(h2); r->exp_hr = hrs(h2);
    }
    if (set_wb && SUCCEEDED(src->QueryInterface(IID_PPV_ARGS(&pa)))) {
        pa->Get(VideoProcAmp_WhiteBalance, &r->wb_prev, &r->wb_prev_flags);
        HRESULT h2 = pa->Set(VideoProcAmp_WhiteBalance, wb, VideoProcAmp_Flags_Manual);
        r->wb_set = SUCCEEDED(h2); r->wb_hr = hrs(h2);
    }
    MFCreateAttributes(&ra, 2);
    ra->SetUINT32(MF_READWRITE_DISABLE_CONVERTERS, TRUE);
    hr = MFCreateSourceReaderFromMediaSource(src, ra, &rd);
    if (FAILED(hr)) { fail("MFCreateSourceReaderFromMediaSource", hr); g_ready++; goto done; }
    {
        IMFMediaType* best = nullptr;
        for (DWORD i = 0;; i++) {
            IMFMediaType* mt = nullptr;
            if (FAILED(rd->GetNativeMediaType((DWORD)MF_SOURCE_READER_FIRST_VIDEO_STREAM, i, &mt))) break;
            GUID st{}; UINT32 w = 0, h = 0, fn = 0, fd = 1;
            mt->GetGUID(MF_MT_SUBTYPE, &st);
            MFGetAttributeSize(mt, MF_MT_FRAME_SIZE, &w, &h);
            MFGetAttributeRatio(mt, MF_MT_FRAME_RATE, &fn, &fd);
            double f = fd ? (double)fn / fd : 0;
            if (st == r->spec.subtype && w == r->spec.w && h == r->spec.h && fabs(f - r->spec.fps) < 0.6 && !best) {
                best = mt; mt = nullptr;
                char b[96]; snprintf(b, sizeof b, "%s %ux%u %u/%u", subtype_name(st).c_str(), w, h, fn, fd); r->chosen_type = b;
            }
            SafeRelease(&mt);
        }
        if (!best) { fail("NoMatchingNativeType", MF_E_INVALIDMEDIATYPE); g_ready++; goto done; }
        hr = rd->SetCurrentMediaType((DWORD)MF_SOURCE_READER_FIRST_VIDEO_STREAM, nullptr, best);
        SafeRelease(&best);
        if (FAILED(hr)) { fail("SetCurrentMediaType", hr); g_ready++; goto done; }
    }
    r->t_create_ms = qpc_ms() - tc;
    while (qpc_ms() < start_at) Sleep(1);
    {
        bool first = true;
        for (;;) {
            double now = qpc_ms();
            if (now >= t_stop) break;
            DWORD si = 0, flags = 0; LONGLONG ts = 0; IMFSample* s = nullptr;
            hr = rd->ReadSample((DWORD)MF_SOURCE_READER_FIRST_VIDEO_STREAM, 0, &si, &flags, &ts, &s);
            double ta = qpc_ms();
            if (FAILED(hr) || (flags & MF_SOURCE_READERF_ERROR)) {
                r->read_err_count++;
                if (r->read_errors.size() < 5) r->read_errors.push_back(hrs(hr) + " " + hrmsg(hr));
                if (first) { fail("ReadSample(first)", hr); g_ready++; first = false; }
                else if (r->failed_stage.empty()) { fail("ReadSample(during)", hr); }
                SafeRelease(&s);
                break;
            }
            if (flags & MF_SOURCE_READERF_STREAMTICK) r->stream_ticks++;
            if (s) {
                DWORD len = 0; s->GetTotalLength(&len);
                if (!g_save_dir.empty() && r->saved < g_save_max) {
                    IMFMediaBuffer* mb = nullptr;
                    if (SUCCEEDED(s->ConvertToContiguousBuffer(&mb))) {
                        BYTE* p = nullptr; DWORD cur = 0;
                        if (SUCCEEDED(mb->Lock(&p, nullptr, &cur))) {
                            char fn[600];
                            snprintf(fn, sizeof fn, "%s/cam%d/frame_%05u.%s", g_save_dir.c_str(), r->index, (unsigned)r->sizes.size(),
                                     r->spec.subtype_s == "MJPG" ? "jpg" : "raw");
                            FILE* f = nullptr; fopen_s(&f, fn, "wb");
                            if (f) { fwrite(p, 1, cur, f); fclose(f); r->saved++; }
                            mb->Unlock();
                        }
                        mb->Release();
                    }
                }
                r->arrivals.push_back(ta - t0);
                r->sizes.push_back(len);
                if (first) { r->t_first_sample_ms = ta - start_at; first = false; r->streamed = true; g_ready++; }
                s->Release();
            }
        }
        if (first) { fail("NoSampleBeforeDeadline", E_FAIL); g_ready++; }
    }
done:
    r->t_end_ms = qpc_ms() - t0;
    if (cc) { if (r->exp_set) cc->Set(CameraControl_Exposure, r->exp_prev, r->exp_prev_flags); cc->Release(); }
    if (pa) { if (r->wb_set) pa->Set(VideoProcAmp_WhiteBalance, r->wb_prev, r->wb_prev_flags); pa->Release(); }
    SafeRelease(&rd);
    SafeRelease(&ra);
    if (src) { src->Shutdown(); src->Release(); }
}

static int do_list(const std::vector<std::string>& match) {
    auto devs = enum_devices();
    printf("[\n");
    for (size_t i = 0; i < devs.size(); i++) {
        printf(" {\"index\": %zu, \"name\": \"%s\", \"symbolic_link\": \"%s\", \"native_types\": [", i, jesc(devs[i].name).c_str(), jesc(devs[i].link).c_str());
        IMFMediaSource* src = nullptr; IMFSourceReader* rd = nullptr; IMFAttributes* ra = nullptr;
        bool firstt = true;
        bool want = match.empty();
        for (auto& m : match) if (lower(devs[i].link).find(m) != std::string::npos) want = true;
        if (want && SUCCEEDED(devs[i].act->ActivateObject(IID_PPV_ARGS(&src)))) {
            MFCreateAttributes(&ra, 1); ra->SetUINT32(MF_READWRITE_DISABLE_CONVERTERS, TRUE);
            if (SUCCEEDED(MFCreateSourceReaderFromMediaSource(src, ra, &rd))) {
                for (DWORD k = 0;; k++) {
                    IMFMediaType* mt = nullptr;
                    if (FAILED(rd->GetNativeMediaType((DWORD)MF_SOURCE_READER_FIRST_VIDEO_STREAM, k, &mt))) break;
                    GUID st{}; UINT32 w = 0, h = 0, fn = 0, fd = 1;
                    mt->GetGUID(MF_MT_SUBTYPE, &st); MFGetAttributeSize(mt, MF_MT_FRAME_SIZE, &w, &h); MFGetAttributeRatio(mt, MF_MT_FRAME_RATE, &fn, &fd);
                    printf("%s\"%s:%ux%u@%.3f\"", firstt ? "" : ", ", subtype_name(st).c_str(), w, h, fd ? (double)fn / fd : 0.0);
                    firstt = false;
                    mt->Release();
                }
            }
            SafeRelease(&rd); SafeRelease(&ra); src->Shutdown(); src->Release();
        }
        printf("]}%s\n", i + 1 < devs.size() ? "," : "");
        devs[i].act->Release();
    }
    printf("]\n");
    return 0;
}

int main(int argc, char** argv) {
    std::vector<Spec> specs;
    double seconds = 8; long exposure = 0; bool set_exp = false; long wb = 0; bool set_wb = false;
    double stagger = 0; std::string outp; bool list = false; std::vector<std::string> list_match;
    for (int i = 1; i < argc; i++) {
        std::string a = argv[i];
        auto nx = [&]() -> std::string { if (i + 1 >= argc) { fprintf(stderr, "missing value for %s\n", a.c_str()); exit(1); } return argv[++i]; };
        if (a == "--list") list = true;
        else if (a == "--seconds") seconds = atof(nx().c_str());
        else if (a == "--exposure") { exposure = atol(nx().c_str()); set_exp = true; }
        else if (a == "--wb") { wb = atol(nx().c_str()); set_wb = true; }
        else if (a == "--stagger-ms") stagger = atof(nx().c_str());
        else if (a == "--out") outp = nx();
        else if (a == "--save-dir") g_save_dir = nx();
        else if (a == "--save-max") g_save_max = (uint32_t)atol(nx().c_str());
        else if (a == "--arrivals") g_arrivals = true;
        else if (a == "--list-match") list_match.push_back(lower(nx()));
        else if (a == "--cam") {
            Spec s; s.raw = nx();
            // match:SUB:WxH@fps  (match may itself contain ':'? no -- symlink substrings don't)
            size_t p1 = s.raw.find(':'), p2 = s.raw.find(':', p1 + 1);
            if (p1 == std::string::npos || p2 == std::string::npos) { fprintf(stderr, "bad --cam %s\n", s.raw.c_str()); return 1; }
            s.match = lower(s.raw.substr(0, p1)); s.subtype_s = s.raw.substr(p1 + 1, p2 - p1 - 1);
            if (!subtype_from(s.subtype_s, &s.subtype)) { fprintf(stderr, "bad subtype %s\n", s.subtype_s.c_str()); return 1; }
            if (sscanf_s(s.raw.c_str() + p2 + 1, "%ux%u@%lf", &s.w, &s.h, &s.fps) != 3) { fprintf(stderr, "bad mode in %s\n", s.raw.c_str()); return 1; }
            specs.push_back(s);
        } else { fprintf(stderr, "unknown arg %s\n", a.c_str()); return 1; }
    }
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    MFStartup(MF_VERSION);
    if (list) { int rc = do_list(list_match); MFShutdown(); return rc; }
    if (specs.empty()) { fprintf(stderr, "no --cam given\n"); return 1; }

    auto devs = enum_devices();
    std::vector<Result> res(specs.size());
    std::vector<IMFActivate*> acts(specs.size(), nullptr);
    for (size_t k = 0; k < specs.size(); k++) {
        res[k].spec = specs[k]; res[k].index = (int)k;
        if (!g_save_dir.empty()) { std::error_code ec; std::filesystem::create_directories(g_save_dir + "/cam" + std::to_string(k), ec); }
        for (auto& d : devs) if (lower(d.link).find(specs[k].match) != std::string::npos) { acts[k] = d.act; res[k].name = d.name; res[k].link = d.link; break; }
        if (!acts[k]) { res[k].failed_stage = "DeviceNotFound"; }
    }
    double t0 = qpc_ms();
    // Readers are created first (up to 4 s budget), then every camera starts streaming at the same instant (+stagger).
    double start_at = t0 + 4000;
    double t_stop = start_at + seconds * 1000 + stagger * specs.size();
    std::vector<std::thread> th;
    int expected = 0;
    for (size_t k = 0; k < specs.size(); k++) {
        if (!acts[k]) { g_ready++; continue; }
        expected++;
        th.emplace_back(run_cam, &res[k], acts[k], t0, t_stop, exposure, set_exp, wb, set_wb, start_at + stagger * k);
    }
    bool announced = false;
    while (!announced) {
        if (g_ready.load() >= (int)specs.size() || qpc_ms() > start_at + 6000) { printf("STREAMING\n"); fflush(stdout); announced = true; }
        else Sleep(20);
    }
    for (auto& t : th) t.join();
    for (auto& d : devs) d.act->Release();

    // ------------------------------------------------------------------ summarize + JSON
    std::ostringstream js;
    int failed = 0;
    js << "{\n \"tool\": \"mf_multi_open\", \"seconds\": " << seconds << ", \"stagger_ms\": " << stagger
       << ", \"exposure_requested\": " << (set_exp ? std::to_string(exposure) : "null")
       << ", \"wb_requested\": " << (set_wb ? std::to_string(wb) : "null") << ",\n \"cameras\": [\n";
    for (size_t k = 0; k < res.size(); k++) {
        auto& r = res[k];
        if (!r.streamed) failed++;
        // steady window: from first sample + 1 s to the end
        double fps = 0, bps = 0, mean_sz = 0, max_gap = 0; uint32_t max_sz = 0, n_win = 0, late = 0;
        if (r.arrivals.size() > 2) {
            double ws = r.arrivals.front() + 1000.0;
            size_t i0 = 0; while (i0 < r.arrivals.size() && r.arrivals[i0] < ws) i0++;
            if (r.arrivals.size() - i0 > 2) {
                size_t i1 = r.arrivals.size() - 1;
                double dt = (r.arrivals[i1] - r.arrivals[i0]) / 1000.0;
                n_win = (uint32_t)(i1 - i0);
                fps = n_win / dt;
                uint64_t b = 0; for (size_t i = i0 + 1; i <= i1; i++) b += r.sizes[i];
                bps = b / dt; mean_sz = (double)b / n_win;
                for (size_t i = i0 + 1; i <= i1; i++) { double g = r.arrivals[i] - r.arrivals[i - 1]; max_gap = std::max(max_gap, g); if (g > 1.5 * 1000.0 / r.spec.fps) late++; }
            }
            for (auto s : r.sizes) max_sz = std::max(max_sz, s);
        }
        js << "  {\"spec\": \"" << jesc(r.spec.raw) << "\", \"name\": \"" << jesc(r.name) << "\", \"symbolic_link\": \"" << jesc(r.link)
           << "\", \"chosen_native_type\": \"" << jesc(r.chosen_type) << "\", \"streamed\": " << (r.streamed ? "true" : "false")
           << ", \"failed_stage\": " << (r.failed_stage.empty() ? "null" : "\"" + r.failed_stage + "\"")
           << ", \"error_hr\": " << (r.error_hr.empty() ? "null" : "\"" + r.error_hr + "\"")
           << ", \"error_msg\": \"" << jesc(r.error_msg) << "\""
           << ", \"setup_ms\": " << r.t_create_ms << ", \"first_sample_ms\": " << r.t_first_sample_ms
           << ", \"samples\": " << r.sizes.size() << ", \"steady_fps\": " << fps << ", \"steady_bytes_per_s\": " << bps
           << ", \"steady_mean_sample_bytes\": " << mean_sz << ", \"max_sample_bytes\": " << max_sz
           << ", \"steady_intervals\": " << n_win << ", \"late_intervals_gt_1p5x\": " << late << ", \"max_gap_ms\": " << max_gap
           << ", \"stream_ticks\": " << r.stream_ticks << ", \"saved_samples\": " << r.saved << ", \"read_errors\": [";
        for (size_t e = 0; e < r.read_errors.size(); e++) js << (e ? ", " : "") << "\"" << jesc(r.read_errors[e]) << "\"";
        js << "], \"exposure\": {\"set_ok\": " << (r.exp_set ? "true" : "false") << ", \"hr\": \"" << r.exp_hr << "\", \"prev\": " << r.exp_prev << ", \"prev_flags\": " << r.exp_prev_flags << "}"
           << ", \"white_balance\": {\"set_ok\": " << (r.wb_set ? "true" : "false") << ", \"hr\": \"" << r.wb_hr << "\", \"prev\": " << r.wb_prev << ", \"prev_flags\": " << r.wb_prev_flags << "}"
           << ", \"sizes_first_60\": [";
        for (size_t i = 0; i < r.sizes.size() && i < 60; i++) js << (i ? "," : "") << r.sizes[i];
        js << "]";
        if (g_arrivals) {  // host QPC arrival of every sample, ms since program start, with its size
            js << ", \"arrivals_ms\": [";
            for (size_t i = 0; i < r.arrivals.size(); i++) { char b[32]; snprintf(b, sizeof b, "%.2f", r.arrivals[i]); js << (i ? "," : "") << b; }
            js << "], \"sizes_all\": [";
            for (size_t i = 0; i < r.sizes.size(); i++) js << (i ? "," : "") << r.sizes[i];
            js << "]";
        }
        js << "}" << (k + 1 < res.size() ? "," : "") << "\n";
    }
    js << " ]\n}\n";
    std::string s = js.str();
    if (!outp.empty()) { FILE* f = nullptr; fopen_s(&f, outp.c_str(), "wb"); if (f) { fwrite(s.data(), 1, s.size(), f); fclose(f); } }
    fprintf(stderr, "%s", s.c_str());
    MFShutdown();
    CoUninitialize();
    return failed ? 2 : 0;
}
