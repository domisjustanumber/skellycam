// wincam.cpp -- Windows UVC camera probe for the skellycam cross-platform capture suite (W-FMT, W-CTRL-LIST,
// W-CTRL-EFFECT, W-MJPEG, W-TS, W-CYC). Media Foundation + DirectShow, Windows SDK only, no third-party code.
//
// Build: suite\windows\native\build.bat  ->  suite\windows\native\build\wincam.exe
//
// Subcommands (full reference in README.md next to this file):
//   wincam list                                         MF + DirectShow device lists; activates/binds nothing
//   wincam formats  --api mf|ds --device X [--hold-ms H] every native MF type on every stream / every DS caps entry
//                                                       (--hold-ms: keep the source/filter open H ms before release)
//   wincam activity [--wait-ms W] [--device X]          which processes use each camera (IMFSensorActivityMonitor +
//                                                       the privacy ConsentStore); opens no camera
//   wincam controls --api mf|ds --device X [--set id=v,...] [--set-flags auto|manual] [--restore] [--read-only]
//   wincam capture  --api mf --device X --width W --height H --fps F [--subtype MJPG|YUY2|NV12|<FOURCC>]
//                   (--frames N | --seconds S) --timeout-ms T --out-dir D [--save none|all|every:K]
//                   [--schedule "ms:id=v;..."] [--controls-before id=v,...] [--stop-file F] [--allow-synthesized]
//   wincam cycle    --api mf --device X --width W --height H --fps F [--subtype S] --cycles K --frames N --timeout-ms T
//                   --out D [--alt-width W2 --alt-height H2 --alt-fps F2] [--gap-ms G] [--allow-synthesized]
//   Raw (uncompressed) subtypes: each frame is checked by buffer length (stride x height; 4:2:0 planar x 1.5), not
//   by JPEG markers. An NV12 type listed right before a same-mode MJPG type (MF's synthesized decode) is refused
//   unless --allow-synthesized.
//
// Output: one JSON object on stdout (or in the --out file for list/formats/controls); per-frame / per-cycle data as
// JSON Lines files. Exit codes: 0 ok, 2 usage, 3 device not found, 4 camera failure (details in JSON), 5 timeout.
//
// Safety rules this tool follows (plan section 6.1): it never restarts, disables or removes a device, never writes
// the registry, never changes a driver. Every blocking camera call runs on a helper thread and is bounded by
// --timeout-ms; a call that does not return is recorded as a timeout. A process-wide watchdog (--watchdog-ms) is
// the last resort: it prints what it has and terminates the process with exit code 5.
//
// Code borrowed from (same study folder): mjpeg/msmf/mf_mjpeg_capture.cpp (native MJPG selection, DS caps listing,
// controls via MF source / DS filter), timing/src/mf_uvc_timing.cpp (KSCAMERA_METADATA_ITEMHEADER /
// KSSTREAM_UVC_METADATA parsing), bandwidth/mf_multi_open.cpp (per-step HRESULTs, FormatMessage via mferror.dll),
// timing/src/dshow_open_probe.cpp (DS enumeration).

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define _CRT_SECURE_NO_WARNINGS
#include <windows.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfreadwrite.h>
#include <mferror.h>
#include <strmif.h>
#include <ks.h>
#include <ksmedia.h>
#include <ksproxy.h>
#include <dshow.h>
#include <dvdmedia.h>
#include <wrl/client.h>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdarg>
#include <cstdint>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <thread>
#include <vector>

#pragma comment(lib, "mfplat.lib")
#pragma comment(lib, "mf.lib")
#pragma comment(lib, "mfreadwrite.lib")
#pragma comment(lib, "mfuuid.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "oleaut32.lib")
#pragma comment(lib, "strmiids.lib")
#pragma comment(lib, "advapi32.lib")

using Microsoft::WRL::ComPtr;

static const char* kVersion = "wincam 1.2 (2026-11-08)";

// ============================================================================================ small utilities

static std::string w2u(const wchar_t* w) {
    if (!w) return {};
    int n = WideCharToMultiByte(CP_UTF8, 0, w, -1, nullptr, 0, nullptr, nullptr);
    std::string s(n > 0 ? n - 1 : 0, '\0');
    if (n > 1) WideCharToMultiByte(CP_UTF8, 0, w, -1, s.data(), n, nullptr, nullptr);
    return s;
}
static std::wstring u2w(const std::string& s) {
    int n = MultiByteToWideChar(CP_UTF8, 0, s.c_str(), -1, nullptr, 0);
    std::wstring w(n > 0 ? n - 1 : 0, L'\0');
    if (n > 1) MultiByteToWideChar(CP_UTF8, 0, s.c_str(), -1, w.data(), n);
    return w;
}
static std::string lower(std::string s) { for (auto& c : s) c = (char)tolower((unsigned char)c); return s; }
static bool contains(const std::string& hay, const std::string& needle) { return hay.find(needle) != std::string::npos; }

static int64_t qpc_freq() { static int64_t f = [] { LARGE_INTEGER x; QueryPerformanceFrequency(&x); return (int64_t)x.QuadPart; }(); return f; }
static int64_t qpc_to_ns(int64_t q) { int64_t f = qpc_freq(); return (q / f) * 1000000000LL + ((q % f) * 1000000000LL) / f; }
static int64_t qpc_ns() { LARGE_INTEGER t; QueryPerformanceCounter(&t); return qpc_to_ns(t.QuadPart); }
static double now_ms() { return (double)qpc_ns() / 1e6; }

static std::string utc_now() {
    FILETIME ft; GetSystemTimePreciseAsFileTime(&ft);
    SYSTEMTIME st; FileTimeToSystemTime(&ft, &st);
    ULARGE_INTEGER u; u.LowPart = ft.dwLowDateTime; u.HighPart = ft.dwHighDateTime;
    char b[64];
    snprintf(b, sizeof b, "%04u-%02u-%02uT%02u:%02u:%02u.%06lluZ", st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond,
             (unsigned long long)((u.QuadPart / 10ULL) % 1000000ULL));
    return b;
}

static std::string hrs(HRESULT hr) { char b[16]; snprintf(b, sizeof b, "0x%08lX", (unsigned long)hr); return b; }
// "Call not made" sentinel for per-call HRESULT fields (FAILED() is true, customer bit set, so it can never collide
// with a code a driver or COM returns). JSON emits it as null; it used to default to E_NOINTERFACE, which hid the
// real code of the call that was made (e.g. the Kiyo's KS GET failure; analysis ctrl_id_env B2, 2026-11-06).
static const HRESULT HR_NOT_CALLED = (HRESULT)0xA0DE0001L;
// KSDATAFORMAT_SPECIFIER_H264_VIDEO (ksmedia.h), the format block of a UVC 1.5 H.264 pin (KS_H264VIDEOINFO)
static const GUID kFormatUvcH264 = {0x2017be05, 0x6629, 0x4248, {0xaa, 0xed, 0x7e, 0x1a, 0x47, 0xbc, 0x9b, 0x9c}};
static std::string guid_str(const GUID& g) {
    char b[64];
    snprintf(b, sizeof b, "%08lX-%04X-%04X-%02X%02X-%02X%02X%02X%02X%02X%02X", g.Data1, g.Data2, g.Data3, g.Data4[0], g.Data4[1], g.Data4[2],
             g.Data4[3], g.Data4[4], g.Data4[5], g.Data4[6], g.Data4[7]);
    return b;
}
static std::string fourcc_of(DWORD d) {
    char c[5] = {(char)(d & 0xff), (char)((d >> 8) & 0xff), (char)((d >> 16) & 0xff), (char)((d >> 24) & 0xff), 0};
    for (int i = 0; i < 4; i++) if (c[i] < 32 || c[i] > 126) { char b[24]; snprintf(b, sizeof b, "D3DFMT_%lu", d); return b; }
    return c;
}
static std::string guid_name(const GUID& g);
// FOURCC-based subtypes ({XXXXXXXX-0000-0010-8000-00AA00389B71}) print as the FOURCC; others by name or GUID.
static std::string subtype_fourcc(const GUID& g) {
    static const BYTE base4[8] = {0x80, 0x00, 0x00, 0xAA, 0x00, 0x38, 0x9B, 0x71};
    if (g.Data2 == 0x0000 && g.Data3 == 0x0010 && memcmp(g.Data4, base4, 8) == 0) return fourcc_of(g.Data1);
    return guid_name(g);
}

static void wlog(const char* fmt, ...) {
    va_list ap; va_start(ap, fmt);
    fprintf(stderr, "[wincam] ");
    vfprintf(stderr, fmt, ap);
    fprintf(stderr, "\n");
    fflush(stderr);
    va_end(ap);
}

// ============================================================================================ JSON value

struct JV {
    enum T { Null, Bool, Int, UInt, Dbl, Str, Arr, Obj } t = Null;
    bool b = false; long long i = 0; unsigned long long u = 0; double d = 0; std::string s;
    std::vector<JV> a; std::vector<std::pair<std::string, JV>> o;
    JV() {}
    JV(std::nullptr_t) {}
    JV(bool v) : t(Bool), b(v) {}
    JV(int v) : t(Int), i(v) {}
    JV(long v) : t(Int), i(v) {}
    JV(long long v) : t(Int), i(v) {}
    JV(unsigned v) : t(UInt), u(v) {}
    JV(unsigned long v) : t(UInt), u(v) {}
    JV(unsigned long long v) : t(UInt), u(v) {}
    JV(double v) : t(Dbl), d(v) {}
    JV(float v) : t(Dbl), d(v) {}
    JV(const char* v) : t(Str), s(v ? v : "") {}
    JV(const std::string& v) : t(Str), s(v) {}
    static JV arr() { JV j; j.t = Arr; return j; }
    static JV obj() { JV j; j.t = Obj; return j; }
    JV& operator[](const std::string& k) {
        if (t != Obj) { t = Obj; o.clear(); }
        for (auto& p : o) if (p.first == k) return p.second;
        o.emplace_back(k, JV());
        return o.back().second;
    }
    const JV* get(const std::string& k) const { for (auto& p : o) if (p.first == k) return &p.second; return nullptr; }
    void push(JV v) { if (t != Arr) { t = Arr; a.clear(); } a.push_back(std::move(v)); }
    size_t size() const { return t == Arr ? a.size() : (t == Obj ? o.size() : 0); }
    static void esc(std::string& out, const std::string& s) {
        out += '"';
        for (unsigned char c : s) {
            switch (c) {
                case '"': out += "\\\""; break;
                case '\\': out += "\\\\"; break;
                case '\n': out += "\\n"; break;
                case '\r': out += "\\r"; break;
                case '\t': out += "\\t"; break;
                default:
                    if (c < 0x20) { char b[8]; snprintf(b, sizeof b, "\\u%04x", c); out += b; }
                    else out += (char)c;
            }
        }
        out += '"';
    }
    void dump_to(std::string& out, int indent, int level) const {
        auto nl = [&](int lv) { if (indent > 0) { out += '\n'; out.append((size_t)(lv * indent), ' '); } };
        char nb[64];
        switch (t) {
            case Null: out += "null"; break;
            case Bool: out += b ? "true" : "false"; break;
            case Int: snprintf(nb, sizeof nb, "%lld", i); out += nb; break;
            case UInt: snprintf(nb, sizeof nb, "%llu", u); out += nb; break;
            case Dbl:
                if (!std::isfinite(d)) out += "null";
                else { snprintf(nb, sizeof nb, "%.10g", d); out += nb; }
                break;
            case Str: esc(out, s); break;
            case Arr:
                out += '[';
                for (size_t k = 0; k < a.size(); k++) { if (k) out += ','; nl(level + 1); a[k].dump_to(out, indent, level + 1); }
                if (!a.empty()) nl(level);
                out += ']';
                break;
            case Obj:
                out += '{';
                for (size_t k = 0; k < o.size(); k++) {
                    if (k) out += ',';
                    nl(level + 1); esc(out, o[k].first); out += indent > 0 ? ": " : ":";
                    o[k].second.dump_to(out, indent, level + 1);
                }
                if (!o.empty()) nl(level);
                out += '}';
                break;
        }
    }
    std::string dump(int indent = 0) const { std::string s2; dump_to(s2, indent, 0); return s2; }
};

// ============================================================================================ HRESULT names + classes

struct HrName { HRESULT hr; const char* name; };
#define HRN(x) {(HRESULT)(x), #x}
static const HrName kHrNames[] = {
    HRN(S_OK), HRN(S_FALSE), HRN(E_FAIL), HRN(E_INVALIDARG), HRN(E_NOINTERFACE), HRN(E_NOTIMPL), HRN(E_POINTER), HRN(E_OUTOFMEMORY),
    HRN(E_UNEXPECTED), HRN(E_ABORT), HRN(E_PENDING),
    {(HRESULT)0x80070005L, "E_ACCESSDENIED"},
    {(HRESULT)0x800718CFL, "HRESULT_FROM_WIN32(6351) USB_INSUFFICIENT_BANDWIDTH"},
    {(HRESULT)0x8007001FL, "HRESULT_FROM_WIN32(ERROR_GEN_FAILURE)"},
    {(HRESULT)0x80070015L, "HRESULT_FROM_WIN32(ERROR_NOT_READY)"},
    {(HRESULT)0x8007048FL, "HRESULT_FROM_WIN32(ERROR_DEVICE_NOT_CONNECTED)"},
    {(HRESULT)0x80070651L, "HRESULT_FROM_WIN32(ERROR_DEVICE_REMOVED)"},
    {(HRESULT)0x800701B1L, "HRESULT_FROM_WIN32(ERROR_NO_SUCH_DEVICE)"},
    {(HRESULT)0x8007045DL, "HRESULT_FROM_WIN32(ERROR_IO_DEVICE)"},
    {(HRESULT)0x800700AAL, "HRESULT_FROM_WIN32(ERROR_BUSY)"},
    {(HRESULT)0x80070964L, "HRESULT_FROM_WIN32(ERROR_DEVICE_IN_USE)"},
    {(HRESULT)0x80070079L, "HRESULT_FROM_WIN32(ERROR_SEM_TIMEOUT)"},
    {(HRESULT)0x800705B4L, "HRESULT_FROM_WIN32(ERROR_TIMEOUT)"},
    {(HRESULT)0x800705AAL, "HRESULT_FROM_WIN32(ERROR_NO_SYSTEM_RESOURCES)"},
    {(HRESULT)0x80070490L, "HRESULT_FROM_WIN32(ERROR_NOT_FOUND) E_PROP_ID_UNSUPPORTED"},
    {(HRESULT)0x80070492L, "HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND) E_PROP_SET_UNSUPPORTED"},
    {(HRESULT)0x80070002L, "HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND)"},
    {(HRESULT)0x8007007AL, "HRESULT_FROM_WIN32(ERROR_INSUFFICIENT_BUFFER)"},
    {(HRESULT)0x800700EAL, "HRESULT_FROM_WIN32(ERROR_MORE_DATA)"},
    {(HRESULT)0x80070032L, "HRESULT_FROM_WIN32(ERROR_NOT_SUPPORTED)"},
    {(HRESULT)0x80070057L, "E_INVALIDARG"},
    {(HRESULT)0xA00F4271L, "CAMERA_APP_0xA00F4271_MEDIA_CAPTURE_FAILED"},
    {(HRESULT)0xA00F4244L, "CAMERA_APP_0xA00F4244_NO_CAMERA"},
    {(HRESULT)0xA00F4243L, "CAMERA_APP_0xA00F4243_CAMERA_IN_USE"},
    HRN(MF_E_HW_MFT_FAILED_START_STREAMING), HRN(MF_E_VIDEO_RECORDING_DEVICE_INVALIDATED), HRN(MF_E_VIDEO_RECORDING_DEVICE_PREEMPTED),
    HRN(MF_E_REBOOT_REQUIRED), HRN(MF_E_INVALIDMEDIATYPE), HRN(MF_E_INVALIDREQUEST), HRN(MF_E_SHUTDOWN), HRN(MF_E_NO_MORE_TYPES),
    HRN(MF_E_INVALIDSTREAMNUMBER), HRN(MF_E_NOTACCEPTING), HRN(MF_E_UNEXPECTED), HRN(MF_E_ATTRIBUTENOTFOUND), HRN(MF_E_NOT_FOUND),
    HRN(MF_E_NOT_AVAILABLE), HRN(MF_E_INVALID_STATE_TRANSITION), HRN(MF_E_HW_STREAM_NOT_CONNECTED), HRN(MF_E_VIDEO_DEVICE_LOCKED),
    HRN(MF_E_CAPTURE_ENGINE_INVALID_OP), HRN(MF_E_TOPO_CODEC_NOT_FOUND), HRN(MF_E_TRANSFORM_TYPE_NOT_SET), HRN(MF_E_SAMPLEALLOCATOR_EMPTY),
    HRN(MF_E_MEDIA_SOURCE_WRONGSTATE), HRN(MF_E_NO_SAMPLE_TIMESTAMP), HRN(MF_E_NOT_INITIALIZED), HRN(MF_E_INVALIDTYPE),
    HRN(MF_E_CAPTURE_SOURCE_NO_VIDEO_STREAM_PRESENT), HRN(MF_E_UNSUPPORTED_CAPTURE_DEVICE_PRESENT), HRN(MF_E_MULTIPLE_SUBSCRIBERS),
    HRN(MF_E_HARDWARE_DRM_UNSUPPORTED), HRN(MF_E_PLATFORM_NOT_INITIALIZED), HRN(MF_E_BUFFERTOOSMALL),
    HRN(VFW_E_NOT_CONNECTED), HRN(VFW_E_INVALIDMEDIATYPE), HRN(VFW_E_NO_ACCEPTABLE_TYPES), HRN(VFW_E_CANNOT_CONNECT), HRN(VFW_E_NOT_STOPPED),
    HRN(VFW_E_WRONG_STATE), HRN(VFW_E_NO_CAPTURE_HARDWARE), HRN(VFW_E_TYPE_NOT_ACCEPTED),
};
#undef HRN

static std::string hr_name(HRESULT hr) {
    for (auto& n : kHrNames) if (n.hr == hr) return n.name;
    return hrs(hr);
}
// JSON for a per-call HRESULT: null when the call was not made (HR_NOT_CALLED), else hex / name.
static JV hrj(HRESULT hr) { return hr == HR_NOT_CALLED ? JV() : JV(hrs(hr)); }
static JV hrnj(HRESULT hr) { return hr == HR_NOT_CALLED ? JV() : JV(hr_name(hr)); }
static std::string hr_message(HRESULT hr) {
    wchar_t* buf = nullptr;
    FormatMessageW(FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS, nullptr, (DWORD)hr, 0, (LPWSTR)&buf, 0, nullptr);
    if (!buf) {
        static HMODULE m = LoadLibraryExW(L"mferror.dll", nullptr, LOAD_LIBRARY_AS_DATAFILE);
        if (m) FormatMessageW(FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_HMODULE | FORMAT_MESSAGE_IGNORE_INSERTS, m, (DWORD)hr, 0, (LPWSTR)&buf, 0, nullptr);
    }
    std::string s = buf ? w2u(buf) : "";
    if (buf) LocalFree(buf);
    while (!s.empty() && (s.back() == '\n' || s.back() == '\r' || s.back() == ' ')) s.pop_back();
    return s;
}

// Error classes match suite/common/topology_model.classify_failure ("bandwidth_probable" needs domain context, so the
// runner decides that one; this tool reports what the code alone says).
static const char* error_class(HRESULT hr, bool timed_out, const char** reason) {
    const char* r = "";
    const char* c = "other";
    if (timed_out) { c = "timeout"; r = "call did not return within --timeout-ms"; }
    else if (hr == (HRESULT)0x800718CFL) { c = "bandwidth_certain"; r = "usbvideo refused the isochronous bandwidth (Win32 6351)"; }
    else if (hr == MF_E_HW_MFT_FAILED_START_STREAMING) { c = "in_use"; r = "MF could not start streaming; usually another app holds the camera"; }
    else if (hr == MF_E_VIDEO_RECORDING_DEVICE_PREEMPTED) { c = "in_use"; r = "preempted by another application"; }
    else if (hr == (HRESULT)0x80070964L || hr == (HRESULT)0x800700AAL) { c = "in_use"; r = "device busy / in use"; }
    else if (hr == (HRESULT)0x80070005L) { c = "permission"; r = "access denied (privacy setting, or for DirectShow possibly bandwidth)"; }
    else if (hr == (HRESULT)0x8007001FL) { c = "device_error"; r = "ERROR_GEN_FAILURE: device stopped answering (Kiyo signature)"; }
    else if (hr == MF_E_REBOOT_REQUIRED) { c = "device_error"; r = "devnode needs restart (DN_NEED_RESTART); ask for a replug"; }
    else if (hr == MF_E_VIDEO_RECORDING_DEVICE_INVALIDATED || hr == (HRESULT)0x8007048FL || hr == (HRESULT)0x80070651L || hr == (HRESULT)0x800701B1L) {
        c = "device_error"; r = "device disappeared or re-enumerated";
    }
    else if (hr == (HRESULT)0x8007045DL || hr == (HRESULT)0x80070015L) { c = "device_error"; r = "I/O error / device not ready"; }
    else if (hr == MF_E_SHUTDOWN) { c = "other"; r = "object used after Shutdown (stale IMFActivate?)"; }
    else if (hr == MF_E_INVALIDREQUEST) { c = "other"; r = "MF_E_INVALIDREQUEST (Chromium treats as transient and retries)"; }
    if (reason) *reason = r;
    return c;
}

// ============================================================================================ bounded calls

// Runs f on a detached MTA thread and waits up to timeout_ms. On timeout the thread is abandoned (it keeps its own
// references alive); f may poll ctl.abandoned after a slow call to clean up after itself.
struct CallCtl { std::atomic<bool> abandoned{false}; };
template <class R> struct Timed { bool timed_out = false; double ms = 0; R value{}; };

static std::atomic<int> g_abandoned_threads{0};

template <class R, class F>
static Timed<R> timed(DWORD timeout_ms, F f) {
    struct St {
        HANDLE ev = nullptr; std::mutex mu; R value{}; CallCtl ctl;
        St() { ev = CreateEventW(nullptr, TRUE, FALSE, nullptr); }
        ~St() { if (ev) CloseHandle(ev); }
    };
    auto st = std::make_shared<St>();
    auto fn = std::make_shared<std::optional<F>>(std::move(f));
    double t0 = now_ms();
    std::thread([st, fn]() {
        HRESULT ci = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
        R v = (**fn)(st->ctl);
        fn->reset();  // drop captured COM references while this thread is still in the MTA
        {
            std::lock_guard<std::mutex> lk(st->mu);
            if (st->ctl.abandoned) v = R(); else st->value = std::move(v);
        }
        SetEvent(st->ev);
        if (SUCCEEDED(ci)) CoUninitialize();
    }).detach();
    Timed<R> out;
    DWORD w = WaitForSingleObject(st->ev, timeout_ms);
    out.ms = now_ms() - t0;
    std::lock_guard<std::mutex> lk(st->mu);
    if (w != WAIT_OBJECT_0) {
        st->ctl.abandoned = true; out.timed_out = true; g_abandoned_threads++;
        return out;
    }
    out.value = std::move(st->value);
    return out;
}

// ============================================================================================ global run context

struct Ctx {
    std::string subcommand, api, device, out_file;
    std::vector<std::string> argv;
    std::string utc_started;
    DWORD timeout_ms = 5000;
    DWORD watchdog_ms = 0;
    DWORD hold_ms = 0;        // formats: keep the activated source (+ reader) / bound filter open this long
    DWORD wait_ms = 1500;     // activity: how long to wait for the first sensor-activity report
    bool allow_synth = false; // capture/cycle: accept an NV12 type flagged as likely MF-synthesized (--allow-synthesized)
};
static Ctx G;

// --hold-ms bookkeeping (formats): the HOLD_BEGIN / HOLD_END stderr lines let a caller sample the USB pipes and try
// a concurrent open while the listing method still holds the device.
struct HoldRec { bool done = false; int64_t begin_ns = 0, end_ns = 0; std::string begin_utc, end_utc, holding; };
static HoldRec g_hold;
// Sleep for G.hold_ms with the device still open, announcing begin/end on stderr (machine-readable lines).
static void do_hold(const char* holding) {
    if (!G.hold_ms) return;
    g_hold.holding = holding; g_hold.begin_utc = utc_now(); g_hold.begin_ns = qpc_ns();
    fprintf(stderr, "[wincam] HOLD_BEGIN qpc_ns=%lld hold_ms=%lu holding=%s\n", (long long)g_hold.begin_ns, (unsigned long)G.hold_ms, holding);
    fflush(stderr);
    Sleep(G.hold_ms);
    g_hold.end_ns = qpc_ns(); g_hold.end_utc = utc_now(); g_hold.done = true;
    fprintf(stderr, "[wincam] HOLD_END qpc_ns=%lld\n", (long long)g_hold.end_ns);
    fflush(stderr);
}
static JV hold_json() {
    JV h = JV::obj();
    h["requested_ms"] = (unsigned long)G.hold_ms; h["done"] = g_hold.done; h["holding"] = g_hold.holding.empty() ? JV() : JV(g_hold.holding);
    h["begin_qpc_ns"] = g_hold.begin_ns ? JV((long long)g_hold.begin_ns) : JV(); h["end_qpc_ns"] = g_hold.end_ns ? JV((long long)g_hold.end_ns) : JV();
    h["begin_utc"] = g_hold.begin_utc.empty() ? JV() : JV(g_hold.begin_utc); h["end_utc"] = g_hold.end_utc.empty() ? JV() : JV(g_hold.end_utc);
    return h;
}

static std::mutex g_partial_mu;
static JV g_partial;               // updated at checkpoints; dumped by the watchdog
static std::string g_partial_file; // summary path for capture/cycle
static std::atomic<const char*> g_stage{"start"};

static JV header(const char* sub) {
    JV j = JV::obj();
    j["tool"] = "wincam"; j["version"] = kVersion; j["subcommand"] = sub;
    j["utc_started"] = G.utc_started; j["pid"] = (unsigned long)GetCurrentProcessId();
    JV av = JV::arr(); for (auto& a : G.argv) av.push(a); j["argv"] = av;
    j["timeout_ms"] = (unsigned long)G.timeout_ms;
    return j;
}

static bool write_text_file(const std::string& path, const std::string& text) {
    FILE* f = _wfopen(u2w(path).c_str(), L"wb");
    if (!f) return false;
    fwrite(text.data(), 1, text.size(), f);
    fclose(f);
    return true;
}
static void ensure_dir(const std::string& dir) {
    std::error_code ec; std::filesystem::create_directories(std::filesystem::path(u2w(dir)), ec);
}

// Emit the final JSON: to --out if given, else stdout. Returns rc for convenience.
static int emit(JV& j, int rc) {
    j["utc_finished"] = utc_now();
    j["exit_code"] = rc;
    j["abandoned_threads"] = g_abandoned_threads.load();
    std::string s = j.dump(1);
    s += "\n";
    if (!G.out_file.empty()) {
        std::filesystem::path p(u2w(G.out_file));
        if (p.has_parent_path()) { std::error_code ec; std::filesystem::create_directories(p.parent_path(), ec); }
        if (!write_text_file(G.out_file, s)) { wlog("cannot write %s; printing to stdout", G.out_file.c_str()); fwrite(s.data(), 1, s.size(), stdout); }
        else wlog("wrote %s", G.out_file.c_str());
    } else {
        fwrite(s.data(), 1, s.size(), stdout);
    }
    fflush(stdout);
    return rc;
}

static void watchdog_thread(DWORD ms) {
    Sleep(ms);
    JV j = header(G.subcommand.c_str());
    j["watchdog_fired"] = true; j["watchdog_ms"] = (unsigned long)ms; j["stage"] = g_stage.load();
    j["error"] = JV::obj();
    j["error"]["class"] = "timeout"; j["error"]["reason"] = "process watchdog expired; a camera call hung beyond every per-call timeout";
    j["error"]["stage"] = g_stage.load();
    std::string part;
    if (g_partial_mu.try_lock()) { part = g_partial.dump(1); g_partial_mu.unlock(); }
    j["utc_finished"] = utc_now(); j["exit_code"] = 5;
    std::string s = j.dump(1);
    if (!part.empty()) { s.pop_back(); s += ",\"partial\":" + part + "}"; }
    s += "\n";
    if (!g_partial_file.empty()) write_text_file(g_partial_file, s);
    else if (!G.out_file.empty()) write_text_file(G.out_file, s);
    HANDLE h = GetStdHandle(STD_OUTPUT_HANDLE); DWORD wr = 0;
    WriteFile(h, s.data(), (DWORD)s.size(), &wr, nullptr);
    wlog("watchdog fired after %lu ms in stage %s; terminating with exit 5", ms, g_stage.load());
    TerminateProcess(GetCurrentProcess(), 5);
}

// ============================================================================================ device enumeration

struct MfDev { int index = 0; std::string name, symlink; ComPtr<IMFActivate> act; };
struct DsDev { int index = 0; std::string name, path, clsid; ComPtr<IMoniker> mk; };

static JV parse_usb_ids(const std::string& link) {
    JV j = JV::obj();
    std::string l = lower(link);
    auto grab = [&](const char* key, int len) -> JV {
        size_t p = l.find(key);
        if (p == std::string::npos || p + strlen(key) + len > l.size()) return JV();
        return JV(l.substr(p + strlen(key), (size_t)len));
    };
    j["vid"] = grab("vid_", 4); j["pid"] = grab("pid_", 4); j["mi"] = grab("mi_", 2);
    // instance part: \\?\usb#vid_..&pid_..&mi_00#<instance>#{guid}\global
    size_t a = l.find('#'); size_t b = a == std::string::npos ? a : l.find('#', a + 1); size_t c = b == std::string::npos ? b : l.find('#', b + 1);
    if (b != std::string::npos && c != std::string::npos) j["instance"] = l.substr(b + 1, c - b - 1); else j["instance"] = nullptr;
    return j;
}
// Normalized key shared by the MF symlink and the DS DevicePath of one camera interface: lower case, without the
// "\\?\" prefix and without the "#{interface class guid}" segment (MF uses KSCATEGORY_VIDEO_CAMERA, DS
// KSCATEGORY_CAPTURE), keeping any reference string after it ("\global", "\vidsource0").
static std::string norm_link(const std::string& s) {
    std::string l = lower(s);
    if (l.rfind("\\\\?\\", 0) == 0) l = l.substr(4);
    size_t p = l.find("#{");
    if (p != std::string::npos) { size_t e = l.find('}', p); l = l.substr(0, p) + (e == std::string::npos ? std::string() : l.substr(e + 1)); }
    return l;
}

static HRESULT enum_mf(std::vector<MfDev>& out) {
    ComPtr<IMFAttributes> a; IMFActivate** acts = nullptr; UINT32 n = 0;
    HRESULT hr = MFCreateAttributes(&a, 1);
    if (SUCCEEDED(hr)) hr = a->SetGUID(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE, MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID);
    if (SUCCEEDED(hr)) hr = MFEnumDeviceSources(a.Get(), &acts, &n);
    if (FAILED(hr)) return hr;
    for (UINT32 i = 0; i < n; i++) {
        MfDev d; d.index = (int)i; d.act.Attach(acts[i]);
        WCHAR* s = nullptr; UINT32 len = 0;
        if (SUCCEEDED(acts[i]->GetAllocatedString(MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME, &s, &len))) { d.name = w2u(s); CoTaskMemFree(s); }
        if (SUCCEEDED(acts[i]->GetAllocatedString(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK, &s, &len))) { d.symlink = w2u(s); CoTaskMemFree(s); }
        out.push_back(std::move(d));
    }
    CoTaskMemFree(acts);
    return S_OK;
}

static HRESULT enum_ds(std::vector<DsDev>& out) {
    ComPtr<ICreateDevEnum> de; ComPtr<IEnumMoniker> em;
    HRESULT hr = CoCreateInstance(CLSID_SystemDeviceEnum, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&de));
    if (FAILED(hr)) return hr;
    hr = de->CreateClassEnumerator(CLSID_VideoInputDeviceCategory, &em, 0);
    if (hr != S_OK) return SUCCEEDED(hr) ? S_OK : hr;  // S_FALSE = category empty
    int i = 0;
    for (;;) {
        ComPtr<IMoniker> mk;
        if (em->Next(1, &mk, nullptr) != S_OK) break;
        DsDev d; d.index = i++; d.mk = mk;
        ComPtr<IPropertyBag> pb;
        if (SUCCEEDED(mk->BindToStorage(nullptr, nullptr, IID_PPV_ARGS(&pb)))) {
            VARIANT v; VariantInit(&v);
            if (SUCCEEDED(pb->Read(L"FriendlyName", &v, nullptr)) && v.vt == VT_BSTR) d.name = w2u(v.bstrVal);
            VariantClear(&v);
            if (SUCCEEDED(pb->Read(L"DevicePath", &v, nullptr)) && v.vt == VT_BSTR) d.path = w2u(v.bstrVal);
            VariantClear(&v);
            if (SUCCEEDED(pb->Read(L"CLSID", &v, nullptr)) && v.vt == VT_BSTR) d.clsid = w2u(v.bstrVal);
            VariantClear(&v);
        }
        out.push_back(std::move(d));
    }
    return S_OK;
}

// Match --device against candidates: exact (case-insensitive) link, else substring of link or of the normalized
// link (so an MF symlink also finds the DS DevicePath of the same interface), else substring of the friendly name.
// Returns index into cands, -1 not found, -2 ambiguous (matches listed in *amb).
static int match_device(const std::string& want, const std::vector<std::pair<std::string, std::string>>& cands, JV* amb) {
    std::string w = lower(want), wn = norm_link(want);
    std::vector<int> hits;
    for (size_t i = 0; i < cands.size(); i++) if (lower(cands[i].first) == w) return (int)i;
    for (size_t i = 0; i < cands.size(); i++) {
        if (cands[i].first.empty()) continue;
        std::string l = lower(cands[i].first), ln = norm_link(cands[i].first);
        if (contains(l, w) || (!wn.empty() && contains(ln, wn))) hits.push_back((int)i);
    }
    if (hits.empty()) for (size_t i = 0; i < cands.size(); i++) if (contains(lower(cands[i].second), w)) hits.push_back((int)i);
    if (hits.size() == 1) return hits[0];
    if (hits.empty()) return -1;
    if (amb) { *amb = JV::arr(); for (int h : hits) { JV m = JV::obj(); m["name"] = cands[(size_t)h].second; m["link"] = cands[(size_t)h].first; amb->push(m); } }
    return -2;
}

// ============================================================================================ list

static int cmd_list() {
    JV j = header("list");
    j["note"] = "enumeration only: no IMFActivate::ActivateObject, no IMoniker::BindToObject";
    double t0 = now_ms();
    std::vector<MfDev> mf; HRESULT hr = enum_mf(mf);
    double t1 = now_ms();
    JV mfj = JV::obj(); mfj["hr"] = hrs(hr); mfj["hr_name"] = hr_name(hr); mfj["elapsed_ms"] = t1 - t0;
    JV mfl = JV::arr();
    for (auto& d : mf) {
        JV e = JV::obj(); e["index"] = d.index; e["friendly_name"] = d.name; e["symlink"] = d.symlink; e["usb"] = parse_usb_ids(d.symlink);
        e["match_key"] = norm_link(d.symlink);
        mfl.push(e);
    }
    mfj["devices"] = mfl; j["mf"] = mfj;
    double t2 = now_ms();
    std::vector<DsDev> ds; hr = enum_ds(ds);
    double t3 = now_ms();
    JV dsj = JV::obj(); dsj["hr"] = hrs(hr); dsj["hr_name"] = hr_name(hr); dsj["elapsed_ms"] = t3 - t2;
    JV dsl = JV::arr();
    for (auto& d : ds) {
        JV e = JV::obj(); e["index"] = d.index; e["friendly_name"] = d.name; e["device_path"] = d.path; e["usb"] = parse_usb_ids(d.path);
        e["match_key"] = d.path.empty() ? JV() : JV(norm_link(d.path));
        e["clsid"] = d.clsid;
        e["clsid_is_ksproxy"] = lower(d.clsid) == "{17cca71b-ecd7-11d0-b908-00a0c9223196}";
        dsl.push(e);
    }
    dsj["devices"] = dsl; j["ds"] = dsj;
    j["elapsed_ms"] = now_ms() - t0;
    return emit(j, 0);
}

// ============================================================================================ attribute dumps

struct NamedGuid { GUID g; const char* name; };
static const GUID kMFSampleExtension_DeviceTimestamp = {0x8f3e35e7, 0x2dcd, 0x4887, {0x86, 0x22, 0x2a, 0x58, 0xba, 0xa6, 0x52, 0xb0}};
static const NamedGuid kAttrNames[] = {
    {MF_DEVICESTREAM_STREAM_CATEGORY, "MF_DEVICESTREAM_STREAM_CATEGORY"},
    {MF_DEVICESTREAM_STREAM_ID, "MF_DEVICESTREAM_STREAM_ID"},
    {MF_DEVICESTREAM_FRAMESERVER_SHARED, "MF_DEVICESTREAM_FRAMESERVER_SHARED"},
    {MF_DEVICESTREAM_ATTRIBUTE_FRAMESOURCE_TYPES, "MF_DEVICESTREAM_ATTRIBUTE_FRAMESOURCE_TYPES"},
    {MF_DEVICESTREAM_EXTENSION_PLUGIN_CLSID, "MF_DEVICESTREAM_EXTENSION_PLUGIN_CLSID"},
    {MF_DEVICESTREAM_MAX_FRAME_BUFFERS, "MF_DEVICESTREAM_MAX_FRAME_BUFFERS"},
    {MF_DEVICESTREAM_IMAGE_STREAM, "MF_DEVICESTREAM_IMAGE_STREAM"},
    {MF_DEVICESTREAM_INDEPENDENT_IMAGE_STREAM, "MF_DEVICESTREAM_INDEPENDENT_IMAGE_STREAM"},
    {MF_DEVICESTREAM_TAKEPHOTO_TRIGGER, "MF_DEVICESTREAM_TAKEPHOTO_TRIGGER"},
    {MF_DEVICESTREAM_REQUIRED_CAPABILITIES, "MF_DEVICESTREAM_REQUIRED_CAPABILITIES"},
    {MF_DEVICESTREAM_REQUIRED_SDDL, "MF_DEVICESTREAM_REQUIRED_SDDL"},
    {MF_SD_STREAM_NAME, "MF_SD_STREAM_NAME"},
    {MF_SD_LANGUAGE, "MF_SD_LANGUAGE"},
    {MF_MT_MAJOR_TYPE, "MF_MT_MAJOR_TYPE"},
    {MF_MT_SUBTYPE, "MF_MT_SUBTYPE"},
    {MF_MT_FRAME_SIZE, "MF_MT_FRAME_SIZE"},
    {MF_MT_FRAME_RATE, "MF_MT_FRAME_RATE"},
    {MF_MT_FRAME_RATE_RANGE_MIN, "MF_MT_FRAME_RATE_RANGE_MIN"},
    {MF_MT_FRAME_RATE_RANGE_MAX, "MF_MT_FRAME_RATE_RANGE_MAX"},
    {MF_MT_PIXEL_ASPECT_RATIO, "MF_MT_PIXEL_ASPECT_RATIO"},
    {MF_MT_INTERLACE_MODE, "MF_MT_INTERLACE_MODE"},
    {MF_MT_ALL_SAMPLES_INDEPENDENT, "MF_MT_ALL_SAMPLES_INDEPENDENT"},
    {MF_MT_SAMPLE_SIZE, "MF_MT_SAMPLE_SIZE"},
    {MF_MT_FIXED_SIZE_SAMPLES, "MF_MT_FIXED_SIZE_SAMPLES"},
    {MF_MT_DEFAULT_STRIDE, "MF_MT_DEFAULT_STRIDE"},
    {MF_MT_AVG_BITRATE, "MF_MT_AVG_BITRATE"},
    {MF_MT_COMPRESSED, "MF_MT_COMPRESSED"},
    {MF_MT_YUV_MATRIX, "MF_MT_YUV_MATRIX"},
    {MF_MT_VIDEO_NOMINAL_RANGE, "MF_MT_VIDEO_NOMINAL_RANGE"},
    {MF_MT_VIDEO_PRIMARIES, "MF_MT_VIDEO_PRIMARIES"},
    {MF_MT_TRANSFER_FUNCTION, "MF_MT_TRANSFER_FUNCTION"},
    {MF_MT_VIDEO_CHROMA_SITING, "MF_MT_VIDEO_CHROMA_SITING"},
    {MF_MT_AM_FORMAT_TYPE, "MF_MT_AM_FORMAT_TYPE"},
    {MF_MT_VIDEO_ROTATION, "MF_MT_VIDEO_ROTATION"},
    {MFVideoFormat_MJPG, "MFVideoFormat_MJPG"},
    {MFVideoFormat_NV12, "MFVideoFormat_NV12"},
    {MFVideoFormat_YUY2, "MFVideoFormat_YUY2"},
    {MFVideoFormat_H264, "MFVideoFormat_H264"},
    {MFVideoFormat_H264_ES, "MFVideoFormat_H264_ES"},
    {MFVideoFormat_HEVC, "MFVideoFormat_HEVC"},
    {MFMediaType_Video, "MFMediaType_Video"},
    {FORMAT_VideoInfo, "FORMAT_VideoInfo"},
    {FORMAT_VideoInfo2, "FORMAT_VideoInfo2"},
    {PIN_CATEGORY_CAPTURE, "PIN_CATEGORY_CAPTURE (PINNAME_VIDEO_CAPTURE)"},
    {PIN_CATEGORY_PREVIEW, "PIN_CATEGORY_PREVIEW (PINNAME_VIDEO_PREVIEW)"},
    {PIN_CATEGORY_STILL, "PIN_CATEGORY_STILL (PINNAME_VIDEO_STILL)"},
    {PIN_CATEGORY_CC, "PIN_CATEGORY_CC"},
    {PIN_CATEGORY_VBI, "PIN_CATEGORY_VBI"},
    {PIN_CATEGORY_TIMECODE, "PIN_CATEGORY_TIMECODE"},
    {PIN_CATEGORY_ANALOGVIDEOIN, "PIN_CATEGORY_ANALOGVIDEOIN"},
    {PIN_CATEGORY_VIDEOPORT, "PIN_CATEGORY_VIDEOPORT"},
    {PIN_CATEGORY_VIDEOPORT_VBI, "PIN_CATEGORY_VIDEOPORT_VBI"},
    {PIN_CATEGORY_EDS, "PIN_CATEGORY_EDS"},
    {PIN_CATEGORY_TELETEXT, "PIN_CATEGORY_TELETEXT"},
    {PIN_CATEGORY_NABTS, "PIN_CATEGORY_NABTS"},
    {PINNAME_IMAGE, "PINNAME_IMAGE"},
    {PINNAME_VIDEO_CC_CAPTURE, "PINNAME_VIDEO_CC_CAPTURE"},
    {PINNAME_VIDEO_NABTS_CAPTURE, "PINNAME_VIDEO_NABTS_CAPTURE"},
    {MEDIATYPE_Video, "MEDIATYPE_Video"},
    {MEDIATYPE_Interleaved, "MEDIATYPE_Interleaved"},
    {MEDIATYPE_Stream, "MEDIATYPE_Stream"},
    {MEDIATYPE_VBI, "MEDIATYPE_VBI"},
    {MFSampleExtension_CaptureMetadata, "MFSampleExtension_CaptureMetadata"},
    {MF_CAPTURE_METADATA_FRAME_RAWSTREAM, "MF_CAPTURE_METADATA_FRAME_RAWSTREAM"},
    {kMFSampleExtension_DeviceTimestamp, "MFSampleExtension_DeviceTimestamp"},
};
static std::string guid_name(const GUID& g) {
    for (auto& k : kAttrNames) if (IsEqualGUID(k.g, g)) return k.name;
    return guid_str(g);
}

static JV attrs_json(IMFAttributes* a) {
    JV o = JV::obj();
    if (!a) return o;
    UINT32 n = 0; a->GetCount(&n);
    for (UINT32 i = 0; i < n; i++) {
        GUID key; PROPVARIANT v; PropVariantInit(&v);
        if (FAILED(a->GetItemByIndex(i, &key, &v))) continue;
        std::string k = guid_name(key);
        switch (v.vt) {
            case VT_UI4: o[k] = (unsigned long)v.ulVal; break;
            case VT_UI8:
                if (IsEqualGUID(key, MF_MT_FRAME_SIZE) || IsEqualGUID(key, MF_MT_FRAME_RATE) || IsEqualGUID(key, MF_MT_FRAME_RATE_RANGE_MIN) ||
                    IsEqualGUID(key, MF_MT_FRAME_RATE_RANGE_MAX) || IsEqualGUID(key, MF_MT_PIXEL_ASPECT_RATIO)) {
                    JV p = JV::arr(); p.push((unsigned long)(v.uhVal.QuadPart >> 32)); p.push((unsigned long)(v.uhVal.QuadPart & 0xffffffffULL)); o[k] = p;
                } else o[k] = (unsigned long long)v.uhVal.QuadPart;
                break;
            case VT_I8: o[k] = (long long)v.hVal.QuadPart; break;
            case VT_R8: o[k] = v.dblVal; break;
            case VT_CLSID: o[k] = guid_name(*v.puuid); break;
            case VT_LPWSTR: o[k] = w2u(v.pwszVal); break;
            case VT_VECTOR | VT_UI1: {
                JV b = JV::obj(); b["blob_bytes"] = (unsigned long)v.caub.cElems;
                std::string hx; char h[3];
                for (ULONG x = 0; x < std::min<ULONG>(v.caub.cElems, 48); x++) { snprintf(h, sizeof h, "%02x", v.caub.pElems[x]); hx += h; }
                b["hex_head"] = hx; o[k] = b;
                break;
            }
            case VT_UNKNOWN: o[k] = "<IUnknown>"; break;
            default: { char b[32]; snprintf(b, sizeof b, "<vt %u>", (unsigned)v.vt); o[k] = b; }
        }
        PropVariantClear(&v);
    }
    return o;
}

// ============================================================================================ device resolution helpers

static int resolve_mf(const std::string& want, MfDev* out, JV& j) {
    std::vector<MfDev> all;
    double t0 = now_ms();
    auto r = timed<std::pair<HRESULT, std::vector<MfDev>>>(G.timeout_ms, [](CallCtl&) {
        std::pair<HRESULT, std::vector<MfDev>> p; p.first = enum_mf(p.second); return p;
    });
    j["enumerate_ms"] = now_ms() - t0;
    if (r.timed_out) { j["error"] = JV::obj(); j["error"]["stage"] = "enumerate"; j["error"]["class"] = "timeout"; return 5; }
    if (FAILED(r.value.first)) {
        j["error"] = JV::obj(); j["error"]["stage"] = "enumerate"; j["error"]["hr"] = hrs(r.value.first); j["error"]["hr_name"] = hr_name(r.value.first);
        j["error"]["class"] = "other"; return 4;
    }
    all = std::move(r.value.second);
    std::vector<std::pair<std::string, std::string>> c;
    for (auto& d : all) c.push_back({d.symlink, d.name});
    JV amb;
    int idx = match_device(want, c, &amb);
    if (idx == -2) { j["error"] = JV::obj(); j["error"]["stage"] = "match"; j["error"]["reason"] = "ambiguous --device"; j["error"]["matches"] = amb; return 2; }
    if (idx < 0) {
        j["error"] = JV::obj(); j["error"]["stage"] = "match"; j["error"]["class"] = "device_error"; j["error"]["reason"] = "no MF device matches --device";
        JV avail = JV::arr(); for (auto& d : all) avail.push(d.symlink); j["error"]["available"] = avail; return 3;
    }
    *out = all[(size_t)idx];
    JV dj = JV::obj(); dj["index"] = out->index; dj["friendly_name"] = out->name; dj["symlink"] = out->symlink; dj["usb"] = parse_usb_ids(out->symlink);
    j["device"] = dj;
    return 0;
}

static int resolve_ds(const std::string& want, DsDev* out, JV& j) {
    double t0 = now_ms();
    auto r = timed<std::pair<HRESULT, std::vector<DsDev>>>(G.timeout_ms, [](CallCtl&) {
        std::pair<HRESULT, std::vector<DsDev>> p; p.first = enum_ds(p.second); return p;
    });
    j["enumerate_ms"] = now_ms() - t0;
    if (r.timed_out) { j["error"] = JV::obj(); j["error"]["stage"] = "enumerate"; j["error"]["class"] = "timeout"; return 5; }
    if (FAILED(r.value.first)) {
        j["error"] = JV::obj(); j["error"]["stage"] = "enumerate"; j["error"]["hr"] = hrs(r.value.first); j["error"]["hr_name"] = hr_name(r.value.first);
        j["error"]["class"] = "other"; return 4;
    }
    auto& all = r.value.second;
    std::vector<std::pair<std::string, std::string>> c;
    for (auto& d : all) c.push_back({d.path, d.name});
    JV amb;
    int idx = match_device(want, c, &amb);
    if (idx == -2) { j["error"] = JV::obj(); j["error"]["stage"] = "match"; j["error"]["reason"] = "ambiguous --device"; j["error"]["matches"] = amb; return 2; }
    if (idx < 0) {
        j["error"] = JV::obj(); j["error"]["stage"] = "match"; j["error"]["class"] = "device_error"; j["error"]["reason"] = "no DirectShow device matches --device";
        JV avail = JV::arr(); for (auto& d : all) avail.push(d.path); j["error"]["available"] = avail; return 3;
    }
    *out = all[(size_t)idx];
    JV dj = JV::obj(); dj["index"] = out->index; dj["friendly_name"] = out->name; dj["device_path"] = out->path; dj["usb"] = parse_usb_ids(out->path);
    j["device"] = dj;
    return 0;
}

static void set_error(JV& j, const char* stage, HRESULT hr, bool timed_out) {
    const char* reason = "";
    JV e = JV::obj();
    e["stage"] = stage;
    e["hr"] = timed_out ? JV() : JV(hrs(hr));
    e["hr_name"] = timed_out ? JV("timeout") : JV(hr_name(hr));
    e["message"] = timed_out ? std::string("no return within --timeout-ms") : hr_message(hr);
    e["class"] = error_class(hr, timed_out, &reason);
    e["reason"] = reason;
    j["error"] = e;
}
static JV step_rec(const char* name, HRESULT hr, double ms, bool timed_out) {
    JV s = JV::obj();
    s["step"] = name; s["hr"] = timed_out ? JV() : JV(hrs(hr)); s["hr_name"] = timed_out ? JV("timeout") : JV(hr_name(hr));
    s["ms"] = ms; s["timed_out"] = timed_out;
    return s;
}

struct Activated { HRESULT hr = E_FAIL; ComPtr<IMFMediaSource> src; };
static Timed<Activated> activate_mf(ComPtr<IMFActivate> act) {
    return timed<Activated>(G.timeout_ms, [act](CallCtl& ctl) {
        Activated a; a.hr = act->ActivateObject(IID_PPV_ARGS(&a.src));
        if (ctl.abandoned && a.src) { a.src->Shutdown(); act->ShutdownObject(); a.src.Reset(); }
        return a;
    });
}
// Release order used everywhere: reader (by caller) -> IMFMediaSource::Shutdown -> IMFActivate::ShutdownObject.
static JV shutdown_mf(ComPtr<IMFMediaSource>& src, ComPtr<IMFActivate>& act, bool* hung) {
    JV steps = JV::arr();
    if (src) {
        ComPtr<IMFMediaSource> s = std::move(src);
        auto r = timed<HRESULT>(G.timeout_ms, [s = std::move(s)](CallCtl&) mutable { HRESULT h = s->Shutdown(); s.Reset(); return h; });
        steps.push(step_rec("source_shutdown", r.value, r.ms, r.timed_out));
        if (r.timed_out && hung) *hung = true;
    }
    if (act) {
        ComPtr<IMFActivate> a = std::move(act);
        auto r = timed<HRESULT>(G.timeout_ms, [a = std::move(a)](CallCtl&) mutable { HRESULT h = a->ShutdownObject(); a.Reset(); return h; });
        steps.push(step_rec("activate_shutdown_object", r.value, r.ms, r.timed_out));
        if (r.timed_out && hung) *hung = true;
    }
    return steps;
}

// ============================================================================================ formats

static int formats_mf() {
    JV j = header("formats"); j["api"] = "mf";
    MfDev dev;
    int rc = resolve_mf(G.device, &dev, j);
    if (rc) return emit(j, rc);
    JV steps = JV::arr();
    g_stage = "activate";
    auto a = activate_mf(dev.act);
    steps.push(step_rec("activate", a.value.hr, a.ms, a.timed_out));
    if (a.timed_out || FAILED(a.value.hr)) { set_error(j, "activate", a.value.hr, a.timed_out); j["steps"] = steps; return emit(j, a.timed_out ? 5 : 4); }
    ComPtr<IMFMediaSource> src = a.value.src;

    // Presentation descriptor: per-stream attributes (category, stream id) and the source's own type count.
    g_stage = "presentation_descriptor";
    auto pd = timed<std::pair<HRESULT, JV>>(G.timeout_ms, [src](CallCtl&) {
        std::pair<HRESULT, JV> out; out.second = JV::arr();
        ComPtr<IMFPresentationDescriptor> p;
        out.first = src->CreatePresentationDescriptor(&p);
        if (FAILED(out.first)) return out;
        DWORD n = 0; p->GetStreamDescriptorCount(&n);
        for (DWORD i = 0; i < n; i++) {
            BOOL sel = FALSE; ComPtr<IMFStreamDescriptor> sd;
            if (FAILED(p->GetStreamDescriptorByIndex(i, &sel, &sd))) continue;
            JV s = JV::obj(); s["stream_index"] = (unsigned long)i; s["selected_by_default"] = sel != FALSE;
            DWORD sid = 0; sd->GetStreamIdentifier(&sid); s["stream_identifier"] = (unsigned long)sid;
            s["attributes"] = attrs_json(sd.Get());
            ComPtr<IMFMediaTypeHandler> th; DWORD tc = 0;
            if (SUCCEEDED(sd->GetMediaTypeHandler(&th))) {
                th->GetMediaTypeCount(&tc);
                GUID major{}; if (SUCCEEDED(th->GetMajorType(&major))) s["major_type"] = guid_name(major);
            }
            s["handler_type_count"] = (unsigned long)tc;
            out.second.push(s);
        }
        return out;
    });
    steps.push(step_rec("create_presentation_descriptor", pd.value.first, pd.ms, pd.timed_out));
    if (pd.timed_out) { set_error(j, "create_presentation_descriptor", E_FAIL, true); j["steps"] = steps; return emit(j, 5); }
    j["streams"] = pd.value.second;

    // Source reader (sync, converters disabled) native types on every stream: the indices capture code uses.
    g_stage = "native_types";
    auto nt = timed<std::pair<HRESULT, JV>>(G.timeout_ms + G.hold_ms, [src](CallCtl&) {
        std::pair<HRESULT, JV> out; out.second = JV::arr();
        ComPtr<IMFAttributes> ra; MFCreateAttributes(&ra, 2);
        ra->SetUINT32(MF_READWRITE_DISABLE_CONVERTERS, TRUE);
        ra->SetUINT32(MF_SOURCE_READER_DISCONNECT_MEDIASOURCE_ON_SHUTDOWN, TRUE);
        ComPtr<IMFSourceReader> rd;
        out.first = MFCreateSourceReaderFromMediaSource(src.Get(), ra.Get(), &rd);
        if (FAILED(out.first)) return out;
        for (DWORD si = 0; si < 64; si++) {
            ComPtr<IMFMediaType> probe;
            HRESULT h = rd->GetNativeMediaType(si, 0, &probe);
            if (h == MF_E_INVALIDSTREAMNUMBER) break;
            struct T { DWORD idx; std::string sub; GUID g; UINT32 w, h, fn, fd; JV extra; };
            std::vector<T> ts;
            for (DWORD ti = 0;; ti++) {
                ComPtr<IMFMediaType> t;
                if (FAILED(rd->GetNativeMediaType(si, ti, &t))) break;
                T x{}; x.idx = ti; t->GetGUID(MF_MT_SUBTYPE, &x.g); x.sub = subtype_fourcc(x.g);
                MFGetAttributeSize(t.Get(), MF_MT_FRAME_SIZE, &x.w, &x.h);
                x.fd = 1; MFGetAttributeRatio(t.Get(), MF_MT_FRAME_RATE, &x.fn, &x.fd);
                x.extra = JV::obj();
                UINT32 a1 = 0, a2 = 0;
                if (SUCCEEDED(MFGetAttributeRatio(t.Get(), MF_MT_FRAME_RATE_RANGE_MIN, &a1, &a2))) { JV p = JV::arr(); p.push(a1); p.push(a2); x.extra["frame_rate_range_min"] = p; }
                if (SUCCEEDED(MFGetAttributeRatio(t.Get(), MF_MT_FRAME_RATE_RANGE_MAX, &a1, &a2))) { JV p = JV::arr(); p.push(a1); p.push(a2); x.extra["frame_rate_range_max"] = p; }
                UINT32 ss = 0; if (SUCCEEDED(t->GetUINT32(MF_MT_SAMPLE_SIZE, &ss))) x.extra["sample_size"] = ss;
                GUID major{}; if (SUCCEEDED(t->GetGUID(MF_MT_MAJOR_TYPE, &major))) x.extra["major_type"] = guid_name(major);
                ts.push_back(x);
            }
            JV s = JV::obj(); s["stream_index"] = (unsigned long)si; s["type_count"] = (unsigned long long)ts.size();
            JV tl = JV::arr();
            std::map<std::string, int> counts;
            for (size_t k = 0; k < ts.size(); k++) {
                auto& x = ts[k];
                counts[x.sub]++;
                JV e = JV::obj();
                e["stream_index"] = (unsigned long)si; e["type_index"] = (unsigned long)x.idx; e["subtype"] = x.sub; e["subtype_guid"] = guid_str(x.g);
                e["width"] = x.w; e["height"] = x.h; e["fps_num"] = x.fn; e["fps_den"] = x.fd; e["fps"] = x.fd ? (double)x.fn / x.fd : 0.0;
                JV flags = JV::arr();
                // MF (Frame Server) inserts a decoded NV12 type right before each MJPG type on cameras without native NV12.
                if (x.g == MFVideoFormat_NV12 && k + 1 < ts.size() && ts[k + 1].g == MFVideoFormat_MJPG && ts[k + 1].w == x.w && ts[k + 1].h == x.h &&
                    ts[k + 1].fn == x.fn && ts[k + 1].fd == x.fd)
                    flags.push("nv12_immediately_before_same_mode_mjpg:likely_mf_synthesized_decode");
                e["flags"] = flags;
                for (auto& kv : x.extra.o) e[kv.first] = kv.second;
                tl.push(e);
            }
            JV cj = JV::obj(); for (auto& kv : counts) cj[kv.first] = kv.second;
            s["subtype_counts"] = cj;
            // de-duplicated MJPG modes: size -> list of frame rates
            JV mj = JV::arr();
            std::vector<std::pair<std::pair<UINT32, UINT32>, std::vector<double>>> modes;
            for (auto& x : ts) {
                if (x.g != MFVideoFormat_MJPG) continue;
                auto key = std::make_pair(x.w, x.h);
                auto it = std::find_if(modes.begin(), modes.end(), [&](auto& m) { return m.first == key; });
                double f = x.fd ? (double)x.fn / x.fd : 0.0;
                if (it == modes.end()) modes.push_back({key, {f}}); else it->second.push_back(f);
            }
            for (auto& m : modes) { JV e = JV::obj(); e["width"] = m.first.first; e["height"] = m.first.second; JV fl = JV::arr(); for (double f : m.second) fl.push(f); e["fps"] = fl; mj.push(e); }
            s["mjpg_sizes"] = mj;
            s["types"] = tl;
            out.second.push(s);
        }
        // --hold-ms: keep the activated source AND the (converters-off) source reader open; no stream is started
        do_hold("mf_source_and_reader");
        rd.Reset();
        return out;
    });
    steps.push(step_rec("reader_native_types", nt.value.first, nt.ms, nt.timed_out));
    if (nt.timed_out) { set_error(j, "reader_native_types", E_FAIL, true); j["steps"] = steps; return emit(j, 5); }
    j["reader_streams"] = nt.value.second;
    if (G.hold_ms) j["hold"] = hold_json();
    j["stream_started"] = false;  // formats never calls ReadSample / IMFMediaSource::Start
    bool hung = false;
    JV sh = shutdown_mf(src, dev.act, &hung);
    for (auto& s : sh.a) steps.push(s);
    j["steps"] = steps;
    if (FAILED(nt.value.first)) { set_error(j, "reader_native_types", nt.value.first, false); return emit(j, 4); }
    if (hung) { set_error(j, "shutdown", E_FAIL, true); return emit(j, 5); }
    j["error"] = nullptr;
    return emit(j, 0);
}

struct BoundFilter { HRESULT hr = E_FAIL; ComPtr<IBaseFilter> f; };
static Timed<BoundFilter> bind_ds(ComPtr<IMoniker> mk) {
    return timed<BoundFilter>(G.timeout_ms, [mk](CallCtl&) {
        BoundFilter b; b.hr = mk->BindToObject(nullptr, nullptr, IID_PPV_ARGS(&b.f)); return b;
    });
}

static void free_mt(AM_MEDIA_TYPE* mt) {
    if (!mt) return;
    if (mt->cbFormat && mt->pbFormat) CoTaskMemFree(mt->pbFormat);
    if (mt->pUnk) mt->pUnk->Release();
    CoTaskMemFree(mt);
}

static int formats_ds() {
    JV j = header("formats"); j["api"] = "ds";
    DsDev dev;
    int rc = resolve_ds(G.device, &dev, j);
    if (rc) return emit(j, rc);
    JV steps = JV::arr();
    g_stage = "bind";
    auto b = bind_ds(dev.mk);
    steps.push(step_rec("bind_filter", b.value.hr, b.ms, b.timed_out));
    if (b.timed_out || FAILED(b.value.hr)) { set_error(j, "bind_filter", b.value.hr, b.timed_out); j["steps"] = steps; return emit(j, b.timed_out ? 5 : 4); }
    ComPtr<IBaseFilter> filt = b.value.f;
    g_stage = "pins";
    auto r = timed<JV>(G.timeout_ms * 4, [filt](CallCtl&) {
        JV out = JV::obj();
        JV pins = JV::arr();
        ComPtr<IAMVideoControl> vc; filt->QueryInterface(IID_PPV_ARGS(&vc));
        out["has_IAMVideoControl"] = (bool)vc;
        ComPtr<IEnumPins> ep;
        HRESULT hr = filt->EnumPins(&ep);
        out["enum_pins_hr"] = hrs(hr);
        int pi = 0;
        bool metadata_like = false;
        while (ep) {
            ComPtr<IPin> pin;
            if (ep->Next(1, &pin, nullptr) != S_OK) break;
            JV pj = JV::obj(); pj["pin_index"] = pi++;
            PIN_INFO info{}; info.dir = PINDIR_INPUT;
            if (SUCCEEDED(pin->QueryPinInfo(&info))) { pj["name"] = w2u(info.achName); pj["direction"] = info.dir == PINDIR_OUTPUT ? "output" : "input"; if (info.pFilter) info.pFilter->Release(); }
            ComPtr<IKsPropertySet> ps; GUID cat{}; DWORD ret = 0;
            if (SUCCEEDED(pin.As(&ps))) {
                HRESULT ch = ps->Get(AMPROPSETID_Pin, AMPROPERTY_PIN_CATEGORY, nullptr, 0, &cat, sizeof(cat), &ret);
                pj["category_hr"] = hrs(ch);
                if (SUCCEEDED(ch)) {
                    pj["category"] = guid_str(cat); pj["category_name"] = guid_name(cat);
                    std::string nm = guid_name(cat);
                    if (nm == guid_str(cat) && info.dir == PINDIR_OUTPUT) metadata_like = true;  // unknown output-pin category: flag for inspection
                }
            }
            if (vc) { long caps = 0; HRESULT hc = vc->GetCaps(pin.Get(), &caps); pj["videocontrol_caps_hr"] = hrs(hc); if (SUCCEEDED(hc)) pj["videocontrol_caps"] = caps; }
            ComPtr<IAMStreamConfig> sc;
            if (SUCCEEDED(pin.As(&sc))) {
                int n = 0, sz = 0; sc->GetNumberOfCapabilities(&n, &sz);
                pj["caps_count"] = n;
                std::vector<BYTE> scc((size_t)std::max(sz, (int)sizeof(VIDEO_STREAM_CONFIG_CAPS)));
                JV caps = JV::arr();
                struct DsMode { std::string sub; long w, h; std::vector<std::string> kinds; std::vector<int> idx; LONGLONG mn, mx; std::vector<LONGLONG> rates; HRESULT rhr; bool rset; };
                std::vector<DsMode> modes;
                for (int i = 0; i < n; i++) {
                    AM_MEDIA_TYPE* mt = nullptr;
                    HRESULT gh = sc->GetStreamCaps(i, &mt, scc.data());
                    JV c = JV::obj(); c["caps_index"] = i; c["hr"] = hrs(gh);
                    if (FAILED(gh) || !mt) { caps.push(c); continue; }
                    long w = 0, h = 0; REFERENCE_TIME atpf = 0; DWORD bic = 0; const char* kind = "other";
                    if (mt->formattype == FORMAT_VideoInfo && mt->pbFormat && mt->cbFormat >= sizeof(VIDEOINFOHEADER)) {
                        auto* vi = (VIDEOINFOHEADER*)mt->pbFormat; w = vi->bmiHeader.biWidth; h = vi->bmiHeader.biHeight; atpf = vi->AvgTimePerFrame; bic = vi->bmiHeader.biCompression; kind = "VIH";
                    } else if (mt->formattype == FORMAT_VideoInfo2 && mt->pbFormat && mt->cbFormat >= sizeof(VIDEOINFOHEADER2)) {
                        auto* vi = (VIDEOINFOHEADER2*)mt->pbFormat; w = vi->bmiHeader.biWidth; h = vi->bmiHeader.biHeight; atpf = vi->AvgTimePerFrame; bic = vi->bmiHeader.biCompression; kind = "VIH2";
                    } else if (mt->formattype == FORMAT_MPEG2Video && mt->pbFormat && mt->cbFormat >= sizeof(MPEG2VIDEOINFO) - sizeof(DWORD)) {
                        auto* vi = (MPEG2VIDEOINFO*)mt->pbFormat; w = vi->hdr.bmiHeader.biWidth; h = vi->hdr.bmiHeader.biHeight; atpf = vi->hdr.AvgTimePerFrame;
                        bic = vi->hdr.bmiHeader.biCompression; kind = "MPEG2VI";
                    } else if (mt->formattype == kFormatUvcH264 && mt->pbFormat && mt->cbFormat >= offsetof(KS_H264VIDEOINFO, bMaxCodecConfigDelay)) {
                        // UVC 1.5 H.264 pin (C930e): KS_H264VIDEOINFO carries the frame size and interval
                        auto* vi = (KS_H264VIDEOINFO*)mt->pbFormat; w = vi->wWidth; h = vi->wHeight; atpf = (REFERENCE_TIME)vi->dwFrameInterval; kind = "H264VI";
                    }
                    h = std::labs(h);
                    auto* v = (VIDEO_STREAM_CONFIG_CAPS*)scc.data();
                    // Unrecognised format block (e.g. the C930e's UVC H.264 pin): take the size from
                    // VIDEO_STREAM_CONFIG_CAPS (InputSize, else MaxOutputSize) instead of reporting 0x0, and log the
                    // formattype GUID (analysis mjpeg_fmt H7, verifier's fallback).
                    if (std::string(kind) == "other") {
                        const char* size_src = nullptr;
                        if (v->InputSize.cx > 0 && v->InputSize.cy > 0) { w = v->InputSize.cx; h = std::labs(v->InputSize.cy); size_src = "VIDEO_STREAM_CONFIG_CAPS.InputSize"; }
                        else if (v->MaxOutputSize.cx > 0 && v->MaxOutputSize.cy > 0) { w = v->MaxOutputSize.cx; h = std::labs(v->MaxOutputSize.cy); size_src = "VIDEO_STREAM_CONFIG_CAPS.MaxOutputSize"; }
                        if (!atpf && v->MinFrameInterval > 0) atpf = v->MinFrameInterval;
                        c["format_type_guid"] = guid_str(mt->formattype); c["format_type"] = guid_name(mt->formattype);
                        c["format_block_bytes"] = (unsigned long)mt->cbFormat;
                        c["size_source"] = size_src ? JV(size_src) : JV();
                        wlog("DS caps %d: unrecognised formattype %s (%s), %lu-byte block; size %ldx%ld from %s", i, guid_str(mt->formattype).c_str(),
                             guid_name(mt->formattype).c_str(), (unsigned long)mt->cbFormat, w, h, size_src ? size_src : "nowhere (0x0)");
                    }
                    std::string sub = subtype_fourcc(mt->subtype);
                    c["header_kind"] = kind; c["subtype"] = sub; c["subtype_guid"] = guid_str(mt->subtype); c["biCompression"] = fourcc_of(bic);
                    c["major_type"] = guid_name(mt->majortype);
                    c["width"] = w; c["height"] = h; c["avg_time_per_frame_100ns"] = (long long)atpf;
                    // caps without intervals (the H.264 pin reports 0): fall back to the format block's interval
                    LONGLONG imn = v->MinFrameInterval > 0 ? v->MinFrameInterval : (LONGLONG)atpf;
                    LONGLONG imx = v->MaxFrameInterval > 0 ? v->MaxFrameInterval : (LONGLONG)atpf;
                    if (imn != v->MinFrameInterval) c["interval_source"] = "format block (caps intervals are 0)";
                    c["min_interval_100ns"] = (long long)imn; c["max_interval_100ns"] = (long long)imx;
                    c["max_fps"] = imn ? 1e7 / (double)imn : 0.0;
                    c["min_fps"] = imx ? 1e7 / (double)imx : 0.0;
                    // discrete rates: IAMVideoControl::GetFrameRateList(pin, caps index, size)
                    JV rl = JV::arr(); HRESULT rhr = HR_NOT_CALLED;
                    std::vector<LONGLONG> rates;
                    if (vc) {
                        long cnt = 0; LONGLONG* list = nullptr; SIZE dim{w, h};
                        rhr = vc->GetFrameRateList(pin.Get(), i, dim, &cnt, &list);
                        if (SUCCEEDED(rhr) && list) { for (long k = 0; k < cnt; k++) { rates.push_back(list[k]); rl.push((long long)list[k]); } CoTaskMemFree(list); }
                    }
                    c["frame_rate_list_hr"] = hrj(rhr); c["frame_rate_list_100ns"] = rl;
                    caps.push(c);
                    auto it = std::find_if(modes.begin(), modes.end(), [&](const DsMode& m) { return m.sub == sub && m.w == w && m.h == h; });
                    if (it == modes.end()) { modes.push_back(DsMode{sub, w, h, {kind}, {i}, imn, imx, rates, rhr, !rates.empty()}); }
                    else {
                        if (std::find(it->kinds.begin(), it->kinds.end(), kind) == it->kinds.end()) it->kinds.push_back(kind);
                        it->idx.push_back(i); it->mn = std::min(it->mn, imn); it->mx = std::max(it->mx, imx);
                        for (auto rr : rates) if (std::find(it->rates.begin(), it->rates.end(), rr) == it->rates.end()) it->rates.push_back(rr);
                        if (!rates.empty()) it->rset = true;
                    }
                    free_mt(mt);
                }
                pj["caps"] = caps;
                JV mj = JV::arr();
                for (auto& m : modes) {
                    JV e = JV::obj(); e["subtype"] = m.sub; e["width"] = m.w; e["height"] = m.h;
                    JV k = JV::arr(); for (auto& s : m.kinds) k.push(s); e["header_kinds"] = k;
                    JV ix = JV::arr(); for (int x : m.idx) ix.push(x); e["caps_indices"] = ix;
                    e["min_interval_100ns"] = (long long)m.mn; e["max_interval_100ns"] = (long long)m.mx;
                    e["max_fps"] = m.mn ? 1e7 / (double)m.mn : 0.0; e["min_fps"] = m.mx ? 1e7 / (double)m.mx : 0.0;
                    std::sort(m.rates.begin(), m.rates.end());
                    JV rl = JV::arr(), fl = JV::arr();
                    for (auto rr : m.rates) { rl.push((long long)rr); fl.push(rr ? 1e7 / (double)rr : 0.0); }
                    e["frame_rate_list_100ns"] = rl; e["fps_list"] = fl; e["rate_list_available"] = m.rset;
                    mj.push(e);
                }
                pj["modes"] = mj;
                pj["mode_count"] = (unsigned long long)modes.size();
            } else {
                // pins without IAMStreamConfig: list media types as offered
                ComPtr<IEnumMediaTypes> emt; JV mts = JV::arr();
                if (SUCCEEDED(pin->EnumMediaTypes(&emt)) && emt) {
                    AM_MEDIA_TYPE* mt = nullptr;
                    while (emt->Next(1, &mt, nullptr) == S_OK) {
                        JV m = JV::obj(); m["major_type"] = guid_name(mt->majortype); m["subtype"] = subtype_fourcc(mt->subtype); m["subtype_guid"] = guid_str(mt->subtype);
                        m["format_type"] = guid_name(mt->formattype); mts.push(m); free_mt(mt); mt = nullptr;
                    }
                }
                pj["media_types"] = mts;
            }
            pins.push(pj);
        }
        out["pins"] = pins;
        out["any_unknown_pin_category"] = metadata_like;
        return out;
    });
    steps.push(step_rec("enumerate_pins_and_caps", S_OK, r.ms, r.timed_out));
    j["steps"] = steps;
    if (r.timed_out) { set_error(j, "enumerate_pins_and_caps", E_FAIL, true); return emit(j, 5); }
    for (auto& kv : r.value.o) j[kv.first] = kv.second;
    // --hold-ms: keep the capture filter bound (no filter graph, no IMediaControl::Run)
    do_hold("ds_bound_filter");
    if (G.hold_ms) j["hold"] = hold_json();
    j["stream_started"] = false;
    j["error"] = nullptr;
    filt.Reset();
    return emit(j, 0);
}

// ============================================================================================ controls

struct CtlDef { int set; long id; const char* name; };  // set 0 = CAMERACONTROL, 1 = VIDEOPROCAMP
static const CtlDef kCtls[] = {
    {0, 0, "pan"}, {0, 1, "tilt"}, {0, 2, "roll"}, {0, 3, "zoom"}, {0, 4, "exposure"}, {0, 5, "iris"}, {0, 6, "focus"}, {0, 7, "scanmode"},
    {0, 8, "privacy"}, {0, 9, "pantilt"}, {0, 10, "pan_relative"}, {0, 11, "tilt_relative"}, {0, 12, "roll_relative"}, {0, 13, "zoom_relative"},
    {0, 14, "exposure_relative"}, {0, 15, "iris_relative"}, {0, 16, "focus_relative"}, {0, 17, "pantilt_relative"}, {0, 18, "focal_length"},
    {0, 19, "auto_exposure_priority"}, {0, 20, "cc_id20"}, {0, 21, "cc_id21"}, {0, 22, "cc_id22"}, {0, 23, "cc_id23"},
    {1, 0, "brightness"}, {1, 1, "contrast"}, {1, 2, "hue"}, {1, 3, "saturation"}, {1, 4, "sharpness"}, {1, 5, "gamma"}, {1, 6, "color_enable"},
    {1, 7, "white_balance"}, {1, 8, "backlight_compensation"}, {1, 9, "gain"}, {1, 10, "digital_multiplier"}, {1, 11, "digital_multiplier_limit"},
    {1, 12, "white_balance_component"}, {1, 13, "powerline_frequency"}, {1, 14, "pa_id14"}, {1, 15, "pa_id15"},
};

static const CtlDef* find_ctl(const std::string& s0) {
    std::string s = lower(s0);
    int set = -1; std::string rest = s;
    if (s.rfind("cc.", 0) == 0 || s.rfind("pa.", 0) == 0) { set = s[0] == 'c' ? 0 : 1; rest = s.substr(3); }
    else if ((s.rfind("cc", 0) == 0 || s.rfind("pa", 0) == 0) && s.size() > 2 && isdigit((unsigned char)s[2])) { set = s[0] == 'c' ? 0 : 1; rest = s.substr(2); }
    bool numeric = !rest.empty() && std::all_of(rest.begin(), rest.end(), [](char c) { return isdigit((unsigned char)c) != 0; });
    for (auto& c : kCtls) {
        if (set >= 0 && c.set != set) continue;
        if (numeric ? (set >= 0 && c.id == atol(rest.c_str())) : rest == c.name) return &c;
    }
    if (!numeric && set < 0) {  // aliases
        if (s == "wb" || s == "white_balance_temperature") return find_ctl("pa.white_balance");
        if (s == "ae_priority") return find_ctl("cc.auto_exposure_priority");
    }
    return nullptr;
}

static JV flags_names(long f) {
    JV a = JV::arr();
    if (f & 0x1) a.push("auto");
    if (f & 0x2) a.push("manual");
    if (f & 0x4) a.push("asynchronous");
    if (f & 0x10) a.push("relative");
    return a;
}

struct CtlIfaces { ComPtr<IAMCameraControl> cc; ComPtr<IAMVideoProcAmp> pa; ComPtr<IKsControl> ks; };
static CtlIfaces get_ifaces(IUnknown* u) {
    CtlIfaces c;
    if (u) { u->QueryInterface(IID_PPV_ARGS(&c.cc)); u->QueryInterface(IID_PPV_ARGS(&c.pa)); u->QueryInterface(IID_PPV_ARGS(&c.ks)); }
    return c;
}

static ULONG ks_struct_size(const CtlDef& d) {
    if (d.set == 0) {
        if (d.id == KSPROPERTY_CAMERACONTROL_PANTILT || d.id == KSPROPERTY_CAMERACONTROL_PANTILT_RELATIVE) return sizeof(KSPROPERTY_CAMERACONTROL_S2);
        if (d.id == KSPROPERTY_CAMERACONTROL_FOCAL_LENGTH) return sizeof(KSPROPERTY_CAMERACONTROL_FOCAL_LENGTH_S);
        return sizeof(KSPROPERTY_CAMERACONTROL_S);
    }
    if (d.id == KSPROPERTY_VIDEOPROCAMP_WHITEBALANCE_COMPONENT) return sizeof(KSPROPERTY_VIDEOPROCAMP_S2);
    return sizeof(KSPROPERTY_VIDEOPROCAMP_S);
}
static GUID ks_set_guid(const CtlDef& d) { return d.set == 0 ? PROPSETID_VIDCAP_CAMERACONTROL : PROPSETID_VIDCAP_VIDEOPROCAMP; }

struct CtlRead {
    bool supported = false; std::string via;
    bool has_range = false, has_default = false, has_value = false, has_value2 = false;
    long mn = 0, mx = 0, step = 0, def = 0, caps = 0, val = 0, flags = 0, val2 = 0;
    HRESULT hr_iam_range = HR_NOT_CALLED, hr_iam_get = HR_NOT_CALLED, hr_ks_basic = HR_NOT_CALLED, hr_ks_default = HR_NOT_CALLED, hr_ks_get = HR_NOT_CALLED;
    JV ks_ranges;
    bool ks_has_range = false, ks_has_default = false, iam_range_degenerate = false;
    long ks_mn = 0, ks_mx = 0, ks_step = 0, ks_def = 0;
    std::string ks_basic_hex; unsigned long ks_basic_len = 0, ks_members_lists = 0;
};

// KSPROPERTY_TYPE_BASICSUPPORT / DEFAULTVALUES parsing (KSPROPERTY_DESCRIPTION + KSPROPERTY_MEMBERSHEADER list)
static HRESULT ks_describe(IKsControl* ks, const CtlDef& d, ULONG type, std::vector<BYTE>& out) {
    std::vector<BYTE> in(ks_struct_size(d), 0);
    auto* p = (KSPROPERTY*)in.data(); p->Set = ks_set_guid(d); p->Id = (ULONG)d.id; p->Flags = type;
    out.assign(512, 0); ULONG ret = 0;
    HRESULT hr = ks->KsProperty(p, (ULONG)in.size(), out.data(), (ULONG)out.size(), &ret);
    if (SUCCEEDED(hr) && ret >= sizeof(KSPROPERTY_DESCRIPTION)) {
        auto* desc = (KSPROPERTY_DESCRIPTION*)out.data();
        if (desc->DescriptionSize > out.size() && desc->DescriptionSize < 65536) {
            out.assign(desc->DescriptionSize, 0);
            hr = ks->KsProperty(p, (ULONG)in.size(), out.data(), (ULONG)out.size(), &ret);
        }
    }
    if (SUCCEEDED(hr)) out.resize(std::min<size_t>(ret, out.size()));
    return hr;
}
static void ks_parse_members(const std::vector<BYTE>& buf, CtlRead& r, bool defaults) {
    if (buf.size() < sizeof(KSPROPERTY_DESCRIPTION)) return;
    auto* desc = (const KSPROPERTY_DESCRIPTION*)buf.data();
    const BYTE* p = buf.data() + sizeof(KSPROPERTY_DESCRIPTION);
    const BYTE* end = buf.data() + std::min<size_t>(buf.size(), desc->DescriptionSize ? desc->DescriptionSize : buf.size());
    for (ULONG k = 0; k < desc->MembersListCount && p + sizeof(KSPROPERTY_MEMBERSHEADER) <= end; k++) {
        auto* mh = (const KSPROPERTY_MEMBERSHEADER*)p; p += sizeof(KSPROPERTY_MEMBERSHEADER);
        size_t body = (size_t)mh->MembersSize * mh->MembersCount;
        if (p + body > end) break;
        if ((mh->MembersFlags == KSPROPERTY_MEMBER_RANGES || mh->MembersFlags == KSPROPERTY_MEMBER_STEPPEDRANGES) && mh->MembersSize >= sizeof(KSPROPERTY_STEPPING_LONG) && mh->MembersCount) {
            auto* s = (const KSPROPERTY_STEPPING_LONG*)p;
            JV rj = JV::obj(); rj["min"] = (long)s->Bounds.SignedMinimum; rj["max"] = (long)s->Bounds.SignedMaximum; rj["step"] = (unsigned long)s->SteppingDelta;
            r.ks_ranges.push(rj);
            if (!r.has_range && !defaults) { r.has_range = true; r.mn = s->Bounds.SignedMinimum; r.mx = s->Bounds.SignedMaximum; r.step = (long)s->SteppingDelta; }
        } else if (mh->MembersFlags == KSPROPERTY_MEMBER_VALUES && mh->MembersSize >= sizeof(LONG) && mh->MembersCount) {
            if ((mh->Flags & KSPROPERTY_MEMBER_FLAG_DEFAULT) && !r.has_default) { r.has_default = true; r.def = *(const LONG*)p; }
        }
        p += body;
    }
}

// KS path: BASICSUPPORT (range), DEFAULTVALUES (default) and GET (value, flags, capabilities) on the property set.
static void read_ctl_ks(const CtlIfaces& c, const CtlDef& d, CtlRead& r, bool want_value) {
    std::vector<BYTE> buf;
    CtlRead k; k.ks_ranges = JV::arr();
    r.hr_ks_basic = ks_describe(c.ks.Get(), d, KSPROPERTY_TYPE_BASICSUPPORT, buf);
    if (SUCCEEDED(r.hr_ks_basic)) {
        ks_parse_members(buf, k, false);
        r.ks_basic_len = (unsigned long)buf.size();
        if (buf.size() >= sizeof(KSPROPERTY_DESCRIPTION)) r.ks_members_lists = ((const KSPROPERTY_DESCRIPTION*)buf.data())->MembersListCount;
        if (!k.has_range) { char h[3]; for (size_t x = 0; x < std::min<size_t>(buf.size(), 96); x++) { snprintf(h, sizeof h, "%02x", buf[x]); r.ks_basic_hex += h; } }
    }
    r.hr_ks_default = ks_describe(c.ks.Get(), d, KSPROPERTY_TYPE_DEFAULTVALUES, buf);
    if (SUCCEEDED(r.hr_ks_default)) ks_parse_members(buf, k, true);
    r.ks_ranges = k.ks_ranges;
    r.ks_has_range = k.has_range; r.ks_mn = k.mn; r.ks_mx = k.mx; r.ks_step = k.step; r.ks_has_default = k.has_default; r.ks_def = k.def;
    if (!want_value) return;
    std::vector<BYTE> st(std::max<ULONG>(ks_struct_size(d), sizeof(KSPROPERTY_CAMERACONTROL_S2)), 0);
    auto* p = (KSPROPERTY*)st.data(); p->Set = ks_set_guid(d); p->Id = (ULONG)d.id; p->Flags = KSPROPERTY_TYPE_GET;
    ULONG ret = 0;
    r.hr_ks_get = c.ks->KsProperty(p, ks_struct_size(d), st.data(), ks_struct_size(d), &ret);
    if (SUCCEEDED(r.hr_ks_get)) {
        r.has_value = true;
        if (d.set == 0 && d.id == KSPROPERTY_CAMERACONTROL_FOCAL_LENGTH) {
            auto* f = (KSPROPERTY_CAMERACONTROL_FOCAL_LENGTH_S*)st.data();
            r.val = f->lOcularFocalLength; r.has_value2 = true; r.val2 = f->lObjectiveFocalLengthMax;
        } else if (ks_struct_size(d) == sizeof(KSPROPERTY_CAMERACONTROL_S2)) {
            auto* s2 = (KSPROPERTY_CAMERACONTROL_S2*)st.data();  // VIDEOPROCAMP_S2 has the same layout
            r.val = s2->Value1; r.flags = (long)s2->Flags; r.caps = (long)s2->Capabilities; r.val2 = s2->Value2; r.has_value2 = true;
        } else {
            auto* s = (KSPROPERTY_CAMERACONTROL_S*)st.data();  // VIDEOPROCAMP_S has the same layout
            r.val = s->Value; r.flags = (long)s->Flags; r.caps = (long)s->Capabilities;
        }
    }
}

// full=true (listing): IAM interface first, then always the KS cross-check. If the IAM range is degenerate
// (0..0 step 0, seen for AE priority) and KS has a range, the KS range is reported as primary.
// full=false (set/readback): only the calls needed for the value.
static CtlRead read_ctl(const CtlIfaces& c, const CtlDef& d, bool full = true) {
    CtlRead r; r.ks_ranges = JV::arr();
    if (d.set == 0 && c.cc) {
        r.hr_iam_range = c.cc->GetRange(d.id, &r.mn, &r.mx, &r.step, &r.def, &r.caps);
        if (SUCCEEDED(r.hr_iam_range)) {
            r.supported = true; r.via = "IAMCameraControl"; r.has_range = r.has_default = true;
            r.hr_iam_get = c.cc->Get(d.id, &r.val, &r.flags); r.has_value = SUCCEEDED(r.hr_iam_get);
        }
    }
    if (d.set == 1 && c.pa) {
        r.hr_iam_range = c.pa->GetRange(d.id, &r.mn, &r.mx, &r.step, &r.def, &r.caps);
        if (SUCCEEDED(r.hr_iam_range)) {
            r.supported = true; r.via = "IAMVideoProcAmp"; r.has_range = r.has_default = true;
            r.hr_iam_get = c.pa->Get(d.id, &r.val, &r.flags); r.has_value = SUCCEEDED(r.hr_iam_get);
        }
    }
    if (r.supported) {
        if (full && c.ks) {
            CtlRead tmp;
            read_ctl_ks(c, d, tmp, false);
            r.hr_ks_basic = tmp.hr_ks_basic; r.hr_ks_default = tmp.hr_ks_default; r.ks_ranges = tmp.ks_ranges;
            r.ks_basic_hex = tmp.ks_basic_hex; r.ks_basic_len = tmp.ks_basic_len; r.ks_members_lists = tmp.ks_members_lists;
            r.ks_has_range = tmp.ks_has_range; r.ks_mn = tmp.ks_mn; r.ks_mx = tmp.ks_mx; r.ks_step = tmp.ks_step;
            r.ks_has_default = tmp.ks_has_default; r.ks_def = tmp.ks_def;
            if (r.mn == 0 && r.mx == 0 && r.step == 0 && r.ks_has_range && !(r.ks_mn == 0 && r.ks_mx == 0)) {
                r.iam_range_degenerate = true; r.mn = r.ks_mn; r.mx = r.ks_mx; r.step = r.ks_step;
                if (r.ks_has_default) r.def = r.ks_def;
            }
        }
        return r;
    }
    if (!c.ks) return r;
    r.mn = r.mx = r.step = r.def = r.caps = 0;
    read_ctl_ks(c, d, r, true);
    r.has_range = r.ks_has_range; r.mn = r.ks_mn; r.mx = r.ks_mx; r.step = r.ks_step; r.has_default = r.ks_has_default; r.def = r.ks_def;
    if (SUCCEEDED(r.hr_ks_get) || SUCCEEDED(r.hr_ks_basic)) { r.supported = true; r.via = "IKsControl"; }
    return r;
}

static HRESULT set_ctl(const CtlIfaces& c, const CtlDef& d, const std::string& via, long value, long flags) {
    if (via == "IAMCameraControl" && c.cc) return c.cc->Set(d.id, value, flags);
    if (via == "IAMVideoProcAmp" && c.pa) return c.pa->Set(d.id, value, flags);
    if (!c.ks) return E_NOINTERFACE;
    ULONG sz = ks_struct_size(d);
    if (sz != sizeof(KSPROPERTY_CAMERACONTROL_S)) return E_NOTIMPL;  // multi-value controls are listed, not set
    KSPROPERTY_CAMERACONTROL_S s{};
    s.Property.Set = ks_set_guid(d); s.Property.Id = (ULONG)d.id; s.Property.Flags = KSPROPERTY_TYPE_SET;
    s.Value = value; s.Flags = (ULONG)flags; s.Capabilities = 0;
    ULONG ret = 0;
    return c.ks->KsProperty((PKSPROPERTY)&s, sizeof(s), &s, sizeof(s), &ret);
}

static JV ctl_json(const CtlDef& d, const CtlRead& r, double ms) {
    JV e = JV::obj();
    e["set"] = d.set == 0 ? "camera_control" : "video_proc_amp"; e["id"] = d.id; e["name"] = d.name;
    e["key"] = std::string(d.set == 0 ? "cc." : "pa.") + d.name;
    e["supported"] = r.supported; e["via"] = r.via.empty() ? JV() : JV(r.via);
    e["min"] = r.has_range ? JV(r.mn) : JV(); e["max"] = r.has_range ? JV(r.mx) : JV(); e["step"] = r.has_range ? JV(r.step) : JV();
    e["default"] = r.has_default ? JV(r.def) : JV();
    e["caps_flags"] = r.supported ? JV(r.caps) : JV(); e["caps_flags_names"] = r.supported ? flags_names(r.caps) : JV();
    e["value"] = r.has_value ? JV(r.val) : JV(); e["flags"] = r.has_value ? JV(r.flags) : JV(); e["flags_names"] = r.has_value ? flags_names(r.flags) : JV();
    if (r.has_value2) e["value2"] = r.val2;
    if (r.ks_ranges.size()) e["ks_ranges"] = r.ks_ranges;
    JV kx = JV::obj();
    kx["hr"] = hrj(r.hr_ks_basic);
    kx["min"] = r.ks_has_range ? JV(r.ks_mn) : JV(); kx["max"] = r.ks_has_range ? JV(r.ks_mx) : JV(); kx["step"] = r.ks_has_range ? JV(r.ks_step) : JV();
    kx["default"] = r.ks_has_default ? JV(r.ks_def) : JV();
    if (SUCCEEDED(r.hr_ks_basic)) { kx["bytes"] = r.ks_basic_len; kx["members_lists"] = r.ks_members_lists; }
    if (!r.ks_basic_hex.empty()) kx["raw_hex_head"] = r.ks_basic_hex;
    e["ks_basicsupport"] = kx;
    if (r.via != "IKsControl" && r.supported)
        e["iam_ks_range_agree"] = r.ks_has_range ? JV(r.iam_range_degenerate || (r.ks_mn == r.mn && r.ks_mx == r.mx && r.ks_step == r.step)) : JV();
    if (r.iam_range_degenerate) e["note"] = "IAM GetRange returned 0..0 step 0; range and default taken from KSPROPERTY_TYPE_BASICSUPPORT/DEFAULTVALUES";
    JV h = JV::obj();
    h["iam_get_range"] = hrj(r.hr_iam_range); h["iam_get"] = hrj(r.hr_iam_get);
    h["ks_basicsupport"] = hrj(r.hr_ks_basic); h["ks_defaultvalues"] = hrj(r.hr_ks_default); h["ks_get"] = hrj(r.hr_ks_get);
    JV hn = JV::obj();
    hn["iam_get_range"] = hrnj(r.hr_iam_range); hn["iam_get"] = hrnj(r.hr_iam_get);
    hn["ks_basicsupport"] = hrnj(r.hr_ks_basic); hn["ks_defaultvalues"] = hrnj(r.hr_ks_default); hn["ks_get"] = hrnj(r.hr_ks_get);
    e["hr"] = h; e["hr_names"] = hn; e["call_ms"] = ms;
    // value GET outcome of a supported control: get_ok false = the device did not answer the GET that was made;
    // get_hr = the HRESULT of that GET (KS GET on the IKsControl path, else IAM Get, else IAM GetRange)
    if (r.supported) {
        e["get_ok"] = r.has_value;
        HRESULT gh = r.via == "IKsControl" ? r.hr_ks_get : (r.hr_iam_get != HR_NOT_CALLED ? r.hr_iam_get : r.hr_iam_range);
        e["get_hr"] = hrj(gh); e["get_hr_name"] = hrnj(gh);
    }
    return e;
}

struct SetReq { const CtlDef* def; std::string raw_value; bool is_auto = false, is_manual_keep = false; long value = 0; long flags = 2; };

// "id=value,id=value"; value = integer | auto | manual. default_flags applies to integers.
static bool parse_sets(const std::string& spec, long default_flags, std::vector<SetReq>& out, std::string& err) {
    size_t p0 = 0;
    while (p0 <= spec.size()) {
        size_t p = spec.find(',', p0);
        std::string item = spec.substr(p0, p == std::string::npos ? std::string::npos : p - p0);
        p0 = p == std::string::npos ? spec.size() + 1 : p + 1;
        if (item.empty()) continue;
        size_t eq = item.find('=');
        if (eq == std::string::npos) { err = "bad set item (need id=value): " + item; return false; }
        SetReq r; r.def = find_ctl(item.substr(0, eq)); r.raw_value = lower(item.substr(eq + 1));
        if (!r.def) { err = "unknown control id: " + item.substr(0, eq); return false; }
        if (r.raw_value == "auto") { r.is_auto = true; r.flags = 1; }
        else if (r.raw_value == "manual") { r.is_manual_keep = true; r.flags = 2; }
        else {
            char* e = nullptr; r.value = strtol(r.raw_value.c_str(), &e, 10);
            if (!e || *e) { err = "bad value: " + item; return false; }
            r.flags = default_flags;
        }
        out.push_back(r);
    }
    return true;
}

// Apply one set request: read current (for auto/manual keep and for restore), set, read back. Bounded by timeout.
struct SetOutcome { JV rec; bool timed_out = false; long prev_val = 0, prev_flags = 0; bool have_prev = false; std::string via; };
static SetOutcome apply_set(const CtlIfaces& c, const SetReq& rq) {
    SetOutcome so;
    auto r = timed<std::pair<JV, std::pair<CtlRead, std::string>>>(G.timeout_ms, [c, rq](CallCtl&) {
        std::pair<JV, std::pair<CtlRead, std::string>> o; JV& j = o.first; j = JV::obj();
        double t0 = now_ms();
        CtlRead before = read_ctl(c, *rq.def, false);
        o.second.first = before;
        j["control"] = std::string(rq.def->set == 0 ? "cc." : "pa.") + rq.def->name; j["requested"] = rq.raw_value;
        j["supported"] = before.supported; j["via"] = before.via.empty() ? JV() : JV(before.via);
        j["before_value"] = before.has_value ? JV(before.val) : JV(); j["before_flags"] = before.has_value ? JV(before.flags) : JV();
        if (!before.supported) { j["hr_set"] = hrs(E_PROP_ID_UNSUPPORTED); j["hr_set_name"] = hr_name(E_PROP_ID_UNSUPPORTED); j["matches"] = false; return o; }
        long v = (rq.is_auto || rq.is_manual_keep) ? before.val : rq.value;
        HRESULT hs = set_ctl(c, *rq.def, before.via, v, rq.flags);
        j["set_value"] = v; j["set_flags"] = rq.flags; j["set_flags_names"] = flags_names(rq.flags);
        j["hr_set"] = hrs(hs); j["hr_set_name"] = hr_name(hs);
        CtlRead after = read_ctl(c, *rq.def, false);
        j["readback_value"] = after.has_value ? JV(after.val) : JV(); j["readback_flags"] = after.has_value ? JV(after.flags) : JV();
        j["readback_flags_names"] = after.has_value ? flags_names(after.flags) : JV();
        bool m = SUCCEEDED(hs) && after.has_value && ((rq.flags & 1) ? (after.flags & 1) != 0 : (after.val == v && (after.flags & 2) != 0));
        j["matches"] = m;
        j["call_ms"] = now_ms() - t0;
        o.second.second = before.via;
        return o;
    });
    so.timed_out = r.timed_out;
    if (r.timed_out) {
        so.rec = JV::obj(); so.rec["control"] = std::string(rq.def->set == 0 ? "cc." : "pa.") + rq.def->name; so.rec["requested"] = rq.raw_value;
        so.rec["timed_out"] = true; so.rec["call_ms"] = r.ms;
        return so;
    }
    so.rec = r.value.first; so.rec["timed_out"] = false;
    so.have_prev = r.value.second.first.has_value; so.prev_val = r.value.second.first.val; so.prev_flags = r.value.second.first.flags;
    so.via = r.value.second.second;
    return so;
}

static JV restore_one(const CtlIfaces& c, const CtlDef& d, const std::string& via, long val, long flags, bool* timed_out) {
    auto r = timed<JV>(G.timeout_ms, [c, d, via, val, flags](CallCtl&) {
        JV j = JV::obj(); j["control"] = std::string(d.set == 0 ? "cc." : "pa.") + d.name; j["restore_value"] = val; j["restore_flags"] = flags;
        HRESULT h = set_ctl(c, d, via, val, flags);
        j["hr_set"] = hrs(h); j["hr_set_name"] = hr_name(h);
        CtlRead a = read_ctl(c, d, false);
        j["readback_value"] = a.has_value ? JV(a.val) : JV(); j["readback_flags"] = a.has_value ? JV(a.flags) : JV();
        return j;
    });
    if (r.timed_out) { *timed_out = true; JV j = JV::obj(); j["control"] = std::string(d.set == 0 ? "cc." : "pa.") + d.name; j["timed_out"] = true; return j; }
    r.value["timed_out"] = false;
    return r.value;
}

struct ControlsOpts { bool read_only = true; std::string sets; long set_flags = 2; bool restore = false; };

// Lists every control, then applies sets, then (optionally) restores. Returns rc (0 / 5 on a timed-out call).
static int run_controls(IUnknown* obj, JV& j, const ControlsOpts& o) {
    CtlIfaces c = get_ifaces(obj);
    JV ifs = JV::obj(); ifs["IAMCameraControl"] = (bool)c.cc; ifs["IAMVideoProcAmp"] = (bool)c.pa; ifs["IKsControl"] = (bool)c.ks;
    j["interfaces"] = ifs;
    JV list = JV::arr();
    bool to = false;
    for (auto& d : kCtls) {
        if (to) { JV e = JV::obj(); e["set"] = d.set == 0 ? "camera_control" : "video_proc_amp"; e["id"] = d.id; e["name"] = d.name; e["skipped"] = "earlier control call timed out"; list.push(e); continue; }
        CtlDef dd = d;
        auto r = timed<CtlRead>(G.timeout_ms, [c, dd](CallCtl&) { return read_ctl(c, dd); });
        if (r.timed_out) {
            to = true;
            JV e = JV::obj(); e["set"] = d.set == 0 ? "camera_control" : "video_proc_amp"; e["id"] = d.id; e["name"] = d.name; e["timed_out"] = true; e["call_ms"] = r.ms;
            list.push(e); continue;
        }
        list.push(ctl_json(d, r.value, r.ms));
    }
    j["controls"] = list;
    int supported = 0; for (auto& e : list.a) { auto* s = e.get("supported"); if (s && s->t == JV::Bool && s->b) supported++; }
    j["supported_count"] = supported;
    if (to) { set_error(j, "control_query", E_FAIL, true); return 5; }
    // Device-backed GET health. focal_length is descriptor data the driver answers without the device (it still
    // answered on the faulted Kiyo), so it does not count. Every device-backed GET failing = the device is not
    // answering: rc 4 with error stage control_get and the first failing GET's HRESULT, and no set is attempted
    // (a read-only run used to return rc 0 here, so callers could not see the failure; ctrl_id_env B1).
    int get_ok = 0, get_failed = 0; HRESULT first_fail = S_OK; JV failed = JV::arr();
    for (auto& e : list.a) {
        auto* s = e.get("supported"); if (!(s && s->t == JV::Bool && s->b)) continue;
        auto* nm = e.get("name"); if (nm && nm->t == JV::Str && nm->s == "focal_length") continue;
        auto* g = e.get("get_ok"); bool ok = g && g->t == JV::Bool && g->b;
        if (ok) { get_ok++; continue; }
        get_failed++;
        auto* k = e.get("key"); if (k && k->t == JV::Str) failed.push(k->s);
        if (first_fail == S_OK) { auto* gh = e.get("get_hr"); first_fail = (gh && gh->t == JV::Str) ? (HRESULT)strtoul(gh->s.c_str(), nullptr, 16) : E_FAIL; }
    }
    j["get_ok_count"] = get_ok; j["get_failed_count"] = get_failed; j["get_failed_controls"] = failed;
    bool not_answering = get_failed > 0 && get_ok == 0;
    j["device_not_answering"] = not_answering;
    if (not_answering) { set_error(j, "control_get", first_fail, false); j["sets"] = JV::arr(); return 4; }
    if (o.read_only || o.sets.empty()) { j["sets"] = JV::arr(); return 0; }
    std::vector<SetReq> reqs; std::string err;
    parse_sets(o.sets, o.set_flags, reqs, err);  // validated in main
    JV sets = JV::arr();
    struct Prev { const CtlDef* d; std::string via; long v, f; };
    std::vector<Prev> prevs;
    for (auto& rq : reqs) {
        auto so = apply_set(c, rq);
        sets.push(so.rec);
        if (so.timed_out) { to = true; break; }
        if (so.have_prev && !so.via.empty()) prevs.push_back({rq.def, so.via, so.prev_val, so.prev_flags});
    }
    j["sets"] = sets;
    if (o.restore && !to) {
        JV rs = JV::arr();
        for (auto it = prevs.rbegin(); it != prevs.rend(); ++it) {
            // restore manual value first, then the original flags (auto) so the camera ends in its prior mode
            rs.push(restore_one(c, *it->d, it->via, it->v, it->f, &to));
            if (to) break;
        }
        j["restore"] = rs;
    }
    if (to) { set_error(j, "control_set", E_FAIL, true); return 5; }
    return 0;
}

static int controls_cmd(const ControlsOpts& o) {
    JV j = header("controls"); j["api"] = G.api; j["read_only"] = o.read_only || o.sets.empty();
    JV steps = JV::arr();
    double t0 = now_ms();
    int rc = 0;
    if (G.api == "mf") {
        MfDev dev;
        rc = resolve_mf(G.device, &dev, j);
        if (rc) return emit(j, rc);
        g_stage = "activate";
        auto a = activate_mf(dev.act);
        steps.push(step_rec("activate", a.value.hr, a.ms, a.timed_out));
        j["activate_ms"] = a.ms;
        if (a.timed_out || FAILED(a.value.hr)) { set_error(j, "activate", a.value.hr, a.timed_out); j["steps"] = steps; return emit(j, a.timed_out ? 5 : 4); }
        ComPtr<IMFMediaSource> src = a.value.src;
        g_stage = "controls";
        rc = run_controls(src.Get(), j, o);
        bool hung = false;
        if (rc == 5) { j["steps"] = steps; j["elapsed_ms"] = now_ms() - t0; return emit(j, 5); }  // do not touch a hung source again
        JV sh = shutdown_mf(src, dev.act, &hung);
        for (auto& s : sh.a) steps.push(s);
        if (hung) { set_error(j, "shutdown", E_FAIL, true); rc = 5; }
    } else {
        DsDev dev;
        rc = resolve_ds(G.device, &dev, j);
        if (rc) return emit(j, rc);
        g_stage = "bind";
        auto b = bind_ds(dev.mk);
        steps.push(step_rec("bind_filter", b.value.hr, b.ms, b.timed_out));
        j["bind_ms"] = b.ms;
        if (b.timed_out || FAILED(b.value.hr)) { set_error(j, "bind_filter", b.value.hr, b.timed_out); j["steps"] = steps; return emit(j, b.timed_out ? 5 : 4); }
        g_stage = "controls";
        rc = run_controls(b.value.f.Get(), j, o);
    }
    j["steps"] = steps;
    j["elapsed_ms"] = now_ms() - t0;
    if (!j.get("error")) j["error"] = nullptr;
    return emit(j, rc);
}

// ============================================================================================ JPEG + UVC metadata parsing

struct JpegInfo { bool soi = false, eoi = false; long eoi_trailing = -1; int sof_w = -1, sof_h = -1; int sof_marker = -1; };
static JpegInfo jpeg_info(const BYTE* p, size_t n) {
    JpegInfo j;
    j.soi = n >= 2 && p[0] == 0xFF && p[1] == 0xD8;
    if (n >= 2 && p[n - 2] == 0xFF && p[n - 1] == 0xD9) { j.eoi = true; j.eoi_trailing = 0; }
    else {
        size_t lim = n > 4096 ? n - 4096 : 0;
        for (size_t i = n >= 2 ? n - 2 : 0; i > lim; i--) if (p[i] == 0xFF && p[i + 1] == 0xD9) { j.eoi_trailing = (long)(n - (i + 2)); break; }
    }
    if (!j.soi) return j;
    size_t i = 2;
    while (i + 4 <= n) {
        if (p[i] != 0xFF) { i++; continue; }
        BYTE m = p[i + 1];
        if (m == 0xFF) { i++; continue; }
        if (m == 0xD8 || m == 0x01 || (m >= 0xD0 && m <= 0xD7)) { i += 2; continue; }
        size_t len = ((size_t)p[i + 2] << 8) | p[i + 3];
        if (m >= 0xC0 && m <= 0xCF && m != 0xC4 && m != 0xC8 && m != 0xCC) {
            if (i + 9 <= n) { j.sof_h = (p[i + 5] << 8) | p[i + 6]; j.sof_w = (p[i + 7] << 8) | p[i + 8]; j.sof_marker = m; }
            break;
        }
        if (m == 0xDA || m == 0xD9) break;
        i += 2 + len;
    }
    return j;
}

struct UvcMeta { bool present = false; ULONG pts = 0, stc = 0, eof_pts = 0, eof_stc = 0; unsigned sof = 0, eof_sof = 0; DWORD raw_len = 0; int items = 0; };
// Same walk as timing/src/mf_uvc_timing.cpp parse_uvc_metadata(): KSCAMERA_METADATA_ITEMHEADER items,
// MetadataId_UsbVideoHeader carries KSSTREAM_UVC_METADATA (first and last payload header of the frame).
static UvcMeta parse_uvc_meta(const BYTE* p, DWORD n) {
    UvcMeta u; u.raw_len = n; DWORD off = 0;
    while (off + sizeof(KSCAMERA_METADATA_ITEMHEADER) <= n) {
        auto* h = (const KSCAMERA_METADATA_ITEMHEADER*)(p + off);
        if (h->Size < sizeof(KSCAMERA_METADATA_ITEMHEADER) || off + h->Size > n) break;
        u.items++;
        if (h->MetadataId == MetadataId_UsbVideoHeader && h->Size >= sizeof(KSCAMERA_METADATA_ITEMHEADER) + sizeof(KSSTREAM_UVC_METADATA)) {
            auto* m = (const KSSTREAM_UVC_METADATA*)(p + off + sizeof(KSCAMERA_METADATA_ITEMHEADER));
            u.present = true;
            u.pts = m->StartOfFrameTimestamp.PresentationTimeStamp; u.stc = m->StartOfFrameTimestamp.SourceClockReference;
            u.sof = (unsigned)(m->StartOfFrameTimestamp.SCRToken & 0x7FF);
            u.eof_pts = m->EndOfFrameTimestamp.PresentationTimeStamp; u.eof_stc = m->EndOfFrameTimestamp.SourceClockReference;
            u.eof_sof = (unsigned)(m->EndOfFrameTimestamp.SCRToken & 0x7FF);
        }
        off += h->Size;
    }
    return u;
}

// ============================================================================================ raw (uncompressed) frames

static constexpr DWORD fcc(char a, char b, char c, char d) {
    return (DWORD)(unsigned char)a | ((DWORD)(unsigned char)b << 8) | ((DWORD)(unsigned char)c << 16) | ((DWORD)(unsigned char)d << 24);
}
static bool is_fourcc_guid(const GUID& g) {
    static const BYTE base4[8] = {0x80, 0x00, 0x00, 0xAA, 0x00, 0x38, 0x9B, 0x71};
    return g.Data2 == 0x0000 && g.Data3 == 0x0010 && memcmp(g.Data4, base4, 8) == 0;
}
// Compressed subtypes the suite can request; everything else is checked as raw frames.
static bool is_compressed_subtype(const GUID& g) {
    return g == MFVideoFormat_MJPG || g == MFVideoFormat_H264 || g == MFVideoFormat_H264_ES || g == MFVideoFormat_HEVC ||
           g == MFVideoFormat_HEVC_ES || g == MFVideoFormat_MP4V || g == MFVideoFormat_VP80 || g == MFVideoFormat_VP90;
}

// Memory layout of the uncompressed formats a UVC camera can send (or MF can list): bytes per pixel of the first
// plane, and whether two half-resolution chroma planes follow (4:2:0 planar / semi-planar: total = plane0 x 1.5).
struct RawLayout { bool known = false; bool planar420 = false; UINT32 bytes_pp = 0; const char* name = ""; };
static RawLayout raw_layout(const GUID& g) {
    RawLayout r;
    auto set = [&](UINT32 bpp, bool p420, const char* nm) { r.known = true; r.bytes_pp = bpp; r.planar420 = p420; r.name = nm; };
    if (g == MFVideoFormat_RGB24) set(3, false, "RGB24");
    else if (g == MFVideoFormat_RGB32 || g == MFVideoFormat_ARGB32) set(4, false, "RGB32");
    else if (g == MFVideoFormat_RGB565 || g == MFVideoFormat_RGB555) set(2, false, "RGB16");
    else if (is_fourcc_guid(g)) {
        switch (g.Data1) {
            case fcc('Y', 'U', 'Y', '2'): case fcc('Y', 'U', 'Y', 'V'): case fcc('U', 'Y', 'V', 'Y'): case fcc('Y', 'V', 'Y', 'U'):
            case fcc('V', 'Y', 'U', 'Y'): case fcc('H', 'D', 'Y', 'C'): case fcc('U', 'Y', 'N', 'V'): case fcc('Y', '4', '2', '2'):
                set(2, false, "packed 4:2:2 (2 bytes/pixel)"); break;
            case fcc('N', 'V', '1', '2'): case fcc('N', 'V', '2', '1'): case fcc('I', '4', '2', '0'): case fcc('I', 'Y', 'U', 'V'):
            case fcc('Y', 'V', '1', '2'):
                set(1, true, "4:2:0 planar (w*h*3/2)"); break;
            case fcc('Y', '8', '0', '0'): case fcc('Y', '8', ' ', ' '): case fcc('G', 'R', 'E', 'Y'): case fcc('L', '8', ' ', ' '):
                set(1, false, "8-bit grey"); break;
            case fcc('Y', '1', '6', ' '): case fcc('L', '1', '6', ' '): set(2, false, "16-bit grey"); break;
            default: break;
        }
    }
    return r;
}

// Expected buffer length of one raw frame of a native type: |stride| x height (x 1.5 for 4:2:0), where stride is
// MF_MT_DEFAULT_STRIDE when the type carries it, else width x bytes per pixel; MF_MT_SAMPLE_SIZE as the last resort.
// A locked contiguous buffer always has the minimum stride, so this is the length IMFMediaBuffer::Lock reports.
struct RawExpect { bool raw = false; uint64_t bytes = 0; long stride = 0; std::string basis, layout; JV attrs; };
static RawExpect raw_expect(IMFMediaType* t, const GUID& sub, UINT32 w, UINT32 h) {
    RawExpect x; x.attrs = JV::obj();
    UINT32 cmp = 0; bool has_cmp = SUCCEEDED(t->GetUINT32(MF_MT_COMPRESSED, &cmp));
    x.attrs["compressed"] = has_cmp ? JV(cmp != 0) : JV();
    UINT32 ss = 0; bool has_ss = SUCCEEDED(t->GetUINT32(MF_MT_SAMPLE_SIZE, &ss));
    x.attrs["sample_size"] = has_ss ? JV(ss) : JV();
    UINT32 fixed = 0; bool has_fixed = SUCCEEDED(t->GetUINT32(MF_MT_FIXED_SIZE_SAMPLES, &fixed));
    x.attrs["fixed_size_samples"] = has_fixed ? JV(fixed != 0) : JV();
    UINT32 ds = 0; bool has_ds = SUCCEEDED(t->GetUINT32(MF_MT_DEFAULT_STRIDE, &ds));
    x.attrs["default_stride"] = has_ds ? JV((long)(INT32)ds) : JV();
    if (is_compressed_subtype(sub) || (has_cmp && cmp)) return x;
    x.raw = true;
    RawLayout lay = raw_layout(sub);
    x.layout = lay.known ? lay.name : "unknown";
    if (has_ds && (INT32)ds != 0) { x.stride = (long)(INT32)ds; x.basis = "MF_MT_DEFAULT_STRIDE"; }
    else if (lay.known) { x.stride = (long)(w * lay.bytes_pp); x.basis = "computed (width x bytes per pixel)"; }
    uint64_t plane = (uint64_t)(x.stride < 0 ? -x.stride : x.stride) * h;
    if (x.stride != 0) {
        x.bytes = lay.planar420 ? plane * 3 / 2 : plane;
        x.basis += lay.planar420 ? " x height x 3/2" : " x height";
        if (!lay.known) x.basis += " (layout unknown: one plane assumed)";
    } else if (has_ss && ss && (!has_fixed || fixed)) {
        x.bytes = ss; x.basis = "MF_MT_SAMPLE_SIZE";
    } else {
        x.basis = "unknown (no stride, no fixed sample size)";
    }
    return x;
}

// ============================================================================================ async MF streaming engine

struct StreamState {
    std::recursive_mutex mu;
    IMFSourceReader* reader = nullptr;  // raw; valid while !stop (the session owns the reference)
    bool stop = false;
    HANDLE ev_sample = nullptr, ev_flush = nullptr;
    // results
    uint64_t frames = 0, ticks = 0, nulls = 0, ok_frames = 0, soi_eoi = 0, sof_match = 0, with_meta = 0, with_capmeta = 0, bytes = 0, discont = 0;
    HRESULT err = S_OK; bool err_set = false; DWORD err_flags = 0; bool eos = false; uint64_t err_at_frame = 0;
    int64_t issue_ns = 0, first_ns = 0, last_ns = 0, progress_ns = 0;
    uint32_t req_w = 0, req_h = 0;
    uint64_t max_frames = 0;
    // raw (uncompressed) frames: checked by buffer length instead of JPEG markers (set from the negotiated type)
    bool raw = false; uint64_t expect_len = 0; uint64_t raw_len_ok = 0, raw_flat = 0, len_min = 0, len_max = 0;
    std::map<uint64_t, uint64_t> len_counts; uint64_t len_other = 0;   // distinct lengths (first 16) + the rest
    bool buf_checked = false, buf_2d = false; long buf_pitch = 0; DWORD buf_contig = 0, buf_count = 0; HRESULT buf_lock2d_hr = HR_NOT_CALLED;
    // capture outputs (null in cycle mode); for raw frames the saved-frames file is frames.raw
    FILE* jsonl = nullptr; FILE* mjpeg = nullptr; uint64_t mjpeg_off = 0; int save_mode = 0; uint64_t save_every = 1; uint64_t saved = 0;
    std::map<std::string, uint64_t> flag_counts;
    int issuing = 0;  // ReadSample calls in flight from the callback (issued outside the lock)
    StreamState() { ev_sample = CreateEventW(nullptr, FALSE, FALSE, nullptr); ev_flush = CreateEventW(nullptr, TRUE, FALSE, nullptr); }
    ~StreamState() { CloseHandle(ev_sample); CloseHandle(ev_flush); }
};

class ReaderCB : public IMFSourceReaderCallback {
    std::atomic<long> ref_{1};
    std::shared_ptr<StreamState> st_;
public:
    explicit ReaderCB(std::shared_ptr<StreamState> st) : st_(std::move(st)) {}
    virtual ~ReaderCB() = default;
    STDMETHODIMP QueryInterface(REFIID iid, void** pp) override {
        if (!pp) return E_POINTER;
        if (iid == __uuidof(IUnknown) || iid == __uuidof(IMFSourceReaderCallback)) { *pp = static_cast<IMFSourceReaderCallback*>(this); AddRef(); return S_OK; }
        *pp = nullptr; return E_NOINTERFACE;
    }
    STDMETHODIMP_(ULONG) AddRef() override { return (ULONG)++ref_; }
    STDMETHODIMP_(ULONG) Release() override { long r = --ref_; if (r == 0) delete this; return (ULONG)r; }
    STDMETHODIMP OnFlush(DWORD) override { SetEvent(st_->ev_flush); return S_OK; }
    STDMETHODIMP OnEvent(DWORD, IMFMediaEvent*) override { return S_OK; }
    STDMETHODIMP OnReadSample(HRESULT hr, DWORD, DWORD flags, LONGLONG ts, IMFSample* s) override {
        int64_t arr = qpc_ns();
        auto& st = *st_;
        ComPtr<IMFSourceReader> next;  // the next request is issued outside the lock, on an AddRef'd reader
        {
            std::lock_guard<std::recursive_mutex> lk(st.mu);
            if (FAILED(hr)) { if (!st.err_set) { st.err = hr; st.err_set = true; st.err_flags = flags; st.err_at_frame = st.frames; } SetEvent(st.ev_sample); return S_OK; }
            if (flags & MF_SOURCE_READERF_ERROR) { if (!st.err_set) { st.err = E_FAIL; st.err_set = true; st.err_flags = flags; st.err_at_frame = st.frames; } SetEvent(st.ev_sample); return S_OK; }
            if (flags & MF_SOURCE_READERF_ENDOFSTREAM) { st.eos = true; SetEvent(st.ev_sample); return S_OK; }
            if (flags & MF_SOURCE_READERF_STREAMTICK) st.ticks++;
            if (flags & MF_SOURCE_READERF_CURRENTMEDIATYPECHANGED) st.flag_counts["current_media_type_changed"]++;
            if (flags & MF_SOURCE_READERF_NATIVEMEDIATYPECHANGED) st.flag_counts["native_media_type_changed"]++;
            if (flags & MF_SOURCE_READERF_ALLEFFECTSREMOVED) st.flag_counts["all_effects_removed"]++;
            st.progress_ns = arr;
            if (s) process_sample(st, arr, flags, ts, s); else st.nulls++;
            if (!st.stop && st.reader && (st.max_frames == 0 || st.frames < st.max_frames)) { next = st.reader; st.issuing++; }
        }
        if (next) {
            HRESULT h2 = next->ReadSample((DWORD)MF_SOURCE_READER_FIRST_VIDEO_STREAM, 0, nullptr, nullptr, nullptr, nullptr);
            next.Reset();
            std::lock_guard<std::recursive_mutex> lk(st.mu);
            st.issuing--;
            if (FAILED(h2) && !st.err_set) { st.err = h2; st.err_set = true; st.err_at_frame = st.frames; }
        }
        SetEvent(st.ev_sample);
        return S_OK;
    }
    static void process_sample(StreamState& st, int64_t arr, DWORD flags, LONGLONG ts, IMFSample* s) {
        uint64_t seq = st.frames++;
        if (!st.first_ns) st.first_ns = arr;
        st.last_ns = arr;
        LONGLONG stime = 0, sdur = 0; HRESULT hst = s->GetSampleTime(&stime); s->GetSampleDuration(&sdur);
        UINT32 disc = 0; s->GetUINT32(MFSampleExtension_Discontinuity, &disc); if (disc) st.discont++;
        UINT64 devts = 0; bool has_devts = SUCCEEDED(s->GetUINT64(kMFSampleExtension_DeviceTimestamp, &devts));
        if (st.raw && !st.buf_checked) {
            // first raw sample: how the source hands the frame over (buffer count, 2D buffer, its pitch)
            st.buf_checked = true;
            s->GetBufferCount(&st.buf_count);
            ComPtr<IMFMediaBuffer> b0; ComPtr<IMF2DBuffer> b2;
            if (SUCCEEDED(s->GetBufferByIndex(0, &b0)) && SUCCEEDED(b0.As(&b2))) {
                st.buf_2d = true;
                BYTE* sc = nullptr; LONG pitch = 0;
                st.buf_lock2d_hr = b2->Lock2D(&sc, &pitch);
                if (SUCCEEDED(st.buf_lock2d_hr)) { st.buf_pitch = pitch; b2->Unlock2D(); }
                b2->GetContiguousLength(&st.buf_contig);
            }
        }
        JpegInfo ji; DWORD len = 0; int64_t off = -1; bool flat = false;
        ComPtr<IMFMediaBuffer> buf;
        if (SUCCEEDED(s->ConvertToContiguousBuffer(&buf))) {
            BYTE* p = nullptr; DWORD mx = 0;
            if (SUCCEEDED(buf->Lock(&p, &mx, &len))) {
                if (!st.raw) ji = jpeg_info(p, len);
                else if (len) {
                    // a frame of one repeated byte value (e.g. all zero) is delivered but carries no image
                    BYTE lo = p[0], hi = p[0]; DWORD step = len > 4096 ? len / 4096 : 1;
                    for (DWORD k = 0; k < len; k += step) { lo = std::min(lo, p[k]); hi = std::max(hi, p[k]); }
                    flat = lo == hi;
                }
                bool save = st.mjpeg && (st.save_mode == 1 || (st.save_mode == 2 && seq % st.save_every == 0));
                if (save) { off = (int64_t)st.mjpeg_off; fwrite(p, 1, len, st.mjpeg); st.mjpeg_off += len; st.saved++; }
                buf->Unlock();
            }
        }
        st.bytes += len;
        bool raw_len_ok = false;
        if (st.raw) {
            raw_len_ok = st.expect_len ? (uint64_t)len == st.expect_len : len > 0;
            if (raw_len_ok) { st.raw_len_ok++; st.ok_frames++; }
            if (flat) st.raw_flat++;
            if (seq == 0 || len < st.len_min) st.len_min = len;
            if (len > st.len_max) st.len_max = len;
            if (st.len_counts.count(len) || st.len_counts.size() < 16) st.len_counts[len]++; else st.len_other++;
        } else {
            bool sizeok = ji.sof_w == (int)st.req_w && ji.sof_h == (int)st.req_h;
            bool eoiok = ji.eoi || (ji.eoi_trailing >= 0);
            if (ji.soi && eoiok) st.soi_eoi++;
            if (sizeok) st.sof_match++;
            if (ji.soi && eoiok && sizeok) st.ok_frames++;
        }
        UvcMeta um; bool capmeta = false;
        ComPtr<IMFAttributes> md;
        if (SUCCEEDED(s->GetUnknown(MFSampleExtension_CaptureMetadata, IID_PPV_ARGS(&md)))) {
            capmeta = true;
            ComPtr<IMFMediaBuffer> raw;
            if (SUCCEEDED(md->GetUnknown(MF_CAPTURE_METADATA_FRAME_RAWSTREAM, IID_PPV_ARGS(&raw)))) {
                BYTE* p = nullptr; DWORD mx = 0, ml = 0;
                if (SUCCEEDED(raw->Lock(&p, &mx, &ml))) { um = parse_uvc_meta(p, ml); raw->Unlock(); }
            }
        }
        if (capmeta) st.with_capmeta++;
        if (um.present) st.with_meta++;
        if (!st.jsonl) return;
        JV f = JV::obj();
        f["seq"] = (unsigned long long)seq; f["qpc_ns"] = (long long)arr;
        f["sample_time_100ns"] = SUCCEEDED(hst) ? JV((long long)stime) : JV();
        f["sample_duration"] = (long long)sdur; f["readsample_ts_100ns"] = (long long)ts;
        f["flags"] = (unsigned long)flags; f["discontinuity"] = disc != 0;
        f["bytes"] = (unsigned long)len;
        if (st.raw) {
            // raw frame: no JPEG markers to check; the length is the check
            f["raw"] = true; f["raw_len_ok"] = raw_len_ok; f["flat"] = flat;
            f["soi"] = JV(); f["eoi"] = JV(); f["eoi_trailing_bytes"] = JV(); f["sof0_w"] = JV(); f["sof0_h"] = JV();
        } else {
            f["soi"] = ji.soi; f["eoi"] = ji.eoi; f["eoi_trailing_bytes"] = ji.eoi_trailing;
            f["sof0_w"] = ji.sof_w >= 0 ? JV(ji.sof_w) : JV(); f["sof0_h"] = ji.sof_h >= 0 ? JV(ji.sof_h) : JV();
            if (ji.sof_marker >= 0 && ji.sof_marker != 0xC0) f["sof_marker"] = ji.sof_marker;
        }
        f["uvc_pts"] = um.present ? JV(um.pts) : JV(); f["uvc_scr_stc"] = um.present ? JV(um.stc) : JV(); f["uvc_scr_sof"] = um.present ? JV(um.sof) : JV();
        f["uvc_eof_pts"] = um.present ? JV(um.eof_pts) : JV(); f["uvc_eof_scr_stc"] = um.present ? JV(um.eof_stc) : JV(); f["uvc_eof_scr_sof"] = um.present ? JV(um.eof_sof) : JV();
        f["has_metadata"] = um.present; f["capture_metadata_attr"] = capmeta;
        if (has_devts) f["mf_device_timestamp"] = (unsigned long long)devts;
        if (off >= 0 && st.raw) { f["raw_offset"] = (long long)off; f["raw_len"] = (unsigned long)len; }
        else if (off >= 0) { f["mjpeg_offset"] = (long long)off; f["mjpeg_len"] = (unsigned long)len; }
        std::string line = f.dump(0); line += "\n";
        fwrite(line.data(), 1, line.size(), st.jsonl);
        fflush(st.jsonl);  // keep every delivered frame on disk even if the process is killed
    }
};

struct Mode { UINT32 w = 0, h = 0; double fps = 0; std::string subtype = "MJPG"; };
static std::string mode_str(const Mode& m) { char b[64]; snprintf(b, sizeof b, "%s %ux%u@%g", m.subtype.c_str(), m.w, m.h, m.fps); return b; }
static bool subtype_guid(const std::string& s, GUID* g) {
    std::string u = s; for (auto& c : u) c = (char)toupper((unsigned char)c);
    if (u == "MJPG") { *g = MFVideoFormat_MJPG; return true; }
    if (u == "YUY2") { *g = MFVideoFormat_YUY2; return true; }
    if (u == "NV12") { *g = MFVideoFormat_NV12; return true; }
    if (u == "H264") { *g = MFVideoFormat_H264; return true; }
    if (u.size() == 4) { *g = MFVideoFormat_MJPG; g->Data1 = (DWORD)u[0] | ((DWORD)u[1] << 8) | ((DWORD)u[2] << 16) | ((DWORD)u[3] << 24); return true; }
    return false;
}

struct Session {
    std::string symlink, name;
    ComPtr<IMFActivate> act; ComPtr<IMFMediaSource> src; ComPtr<IMFSourceReader> reader; ComPtr<ReaderCB> cb;
    std::shared_ptr<StreamState> st;
    CtlIfaces ctl;
    JV steps = JV::arr();
    JV negotiated;
    double enumerate_ms = -1, activate_ms = -1, reader_ms = -1, settype_ms = -1, first_frame_ms = -1, open_to_first_ms = -1;
    double flush_ms = -1, reader_release_ms = -1, shutdown_ms = -1, shutdown_object_ms = -1, close_ms = -1;
    std::string stage_failed; HRESULT hr = S_OK; bool timed_out = false; bool unreleasable = false; bool found = true;
    int64_t t_open_ns = 0;
};

static void fail(Session& s, const char* stage, HRESULT hr, bool timed_out) {
    if (s.stage_failed.empty()) { s.stage_failed = stage; s.hr = hr; s.timed_out = timed_out; }
}

// enumerate (fresh each call) -> activate -> [controls-before] -> async reader -> explicit native type -> start.
// Returns true when the first ReadSample has been issued; the caller then waits for samples.
static bool open_session(Session& s, const std::string& symlink, const Mode& m, std::shared_ptr<StreamState> st,
                         const std::vector<SetReq>* controls_before, JV* controls_before_out) {
    s.st = st; s.symlink = symlink; s.t_open_ns = qpc_ns();
    g_stage = "enumerate";
    auto en = timed<std::pair<HRESULT, std::vector<MfDev>>>(G.timeout_ms, [](CallCtl&) {
        std::pair<HRESULT, std::vector<MfDev>> p; p.first = enum_mf(p.second); return p;
    });
    s.enumerate_ms = en.ms;
    s.steps.push(step_rec("enumerate", en.value.first, en.ms, en.timed_out));
    if (en.timed_out || FAILED(en.value.first)) { fail(s, "enumerate", en.value.first, en.timed_out); return false; }
    for (auto& d : en.value.second) if (lower(d.symlink) == lower(symlink)) { s.act = d.act; s.name = d.name; break; }
    if (!s.act) { s.found = false; fail(s, "device_not_found", (HRESULT)0x8007048FL, false); return false; }

    g_stage = "activate";
    auto a = activate_mf(s.act);
    s.activate_ms = a.ms;
    s.steps.push(step_rec("activate", a.value.hr, a.ms, a.timed_out));
    if (a.timed_out || FAILED(a.value.hr)) { fail(s, "activate", a.value.hr, a.timed_out); return false; }
    s.src = a.value.src;
    s.ctl = get_ifaces(s.src.Get());

    if (controls_before && !controls_before->empty()) {
        g_stage = "controls_before";
        JV arr = JV::arr();
        for (auto& rq : *controls_before) {
            auto so = apply_set(s.ctl, rq);
            arr.push(so.rec);
            if (so.timed_out) { if (controls_before_out) *controls_before_out = arr; fail(s, "controls_before", E_FAIL, true); return false; }
        }
        if (controls_before_out) *controls_before_out = arr;
    }

    g_stage = "reader_create";
    s.cb.Attach(new ReaderCB(st));
    ComPtr<IMFMediaSource> src = s.src; ComPtr<ReaderCB> cb = s.cb;
    auto rc = timed<std::pair<HRESULT, ComPtr<IMFSourceReader>>>(G.timeout_ms, [src, cb](CallCtl&) {
        std::pair<HRESULT, ComPtr<IMFSourceReader>> o;
        ComPtr<IMFAttributes> ra; MFCreateAttributes(&ra, 4);
        ra->SetUINT32(MF_READWRITE_DISABLE_CONVERTERS, TRUE);
        ra->SetUINT32(MF_SOURCE_READER_DISCONNECT_MEDIASOURCE_ON_SHUTDOWN, TRUE);
        ra->SetUnknown(MF_SOURCE_READER_ASYNC_CALLBACK, static_cast<IMFSourceReaderCallback*>(cb.Get()));
        o.first = MFCreateSourceReaderFromMediaSource(src.Get(), ra.Get(), &o.second);
        return o;
    });
    s.reader_ms = rc.ms;
    s.steps.push(step_rec("reader_create", rc.value.first, rc.ms, rc.timed_out));
    if (rc.timed_out || FAILED(rc.value.first)) { fail(s, "reader_create", rc.value.first, rc.timed_out); return false; }
    s.reader = rc.value.second;

    g_stage = "set_type";
    GUID want{}; subtype_guid(m.subtype, &want);
    ComPtr<IMFSourceReader> rd = s.reader;
    struct SetTypeOut { HRESULT hr = E_FAIL; JV n; RawExpect rx; };
    const bool allow_synth = G.allow_synth;
    auto stp = timed<SetTypeOut>(G.timeout_ms, [rd, want, m, allow_synth](CallCtl&) {
        SetTypeOut o; JV& n = o.n; n = JV::obj();
        n["requested_subtype"] = m.subtype;
        // explicit selection: exact subtype, exact size, nearest frame rate within 0.5 fps (never "first match").
        // The whole native list is read first, so a type can be compared with the one after it: MF (Frame Server)
        // lists a decoded NV12 right before each MJPG type on cameras without native NV12 (same rule as `formats`).
        struct T { DWORD idx; GUID sub; UINT32 w, h, fn, fd; ComPtr<IMFMediaType> t; };
        std::vector<T> ts;
        for (DWORD i = 0;; i++) {
            T x{}; x.idx = i; x.fd = 1;
            if (FAILED(rd->GetNativeMediaType((DWORD)MF_SOURCE_READER_FIRST_VIDEO_STREAM, i, &x.t))) break;
            x.t->GetGUID(MF_MT_SUBTYPE, &x.sub); MFGetAttributeSize(x.t.Get(), MF_MT_FRAME_SIZE, &x.w, &x.h); MFGetAttributeRatio(x.t.Get(), MF_MT_FRAME_RATE, &x.fn, &x.fd);
            ts.push_back(x);
        }
        auto synthesized = [&](size_t k) {
            const T& x = ts[k];
            return x.sub == MFVideoFormat_NV12 && k + 1 < ts.size() && ts[k + 1].sub == MFVideoFormat_MJPG && ts[k + 1].w == x.w &&
                   ts[k + 1].h == x.h && ts[k + 1].fn == x.fn && ts[k + 1].fd == x.fd;
        };
        // best genuine candidate; a flagged (likely synthesized) one only with --allow-synthesized
        size_t best = SIZE_MAX, best_flagged = SIZE_MAX; double best_err = 1e9, best_flagged_err = 1e9; int n_flagged = 0;
        JV cands = JV::arr();
        for (size_t k = 0; k < ts.size(); k++) {
            const T& x = ts[k];
            if (x.sub != want || x.w != m.w || x.h != m.h) continue;
            bool syn = synthesized(k);
            char b[64]; snprintf(b, sizeof b, "%u/%u%s", x.fn, x.fd, syn ? " (likely_mf_synthesized)" : "");
            cands.push(b);
            double e = std::fabs((x.fd ? (double)x.fn / x.fd : 0.0) - m.fps);
            if (e >= 0.5) continue;
            if (syn) { n_flagged++; if (e < best_flagged_err) { best_flagged = k; best_flagged_err = e; } }
            else if (e < best_err) { best = k; best_err = e; }
        }
        n["candidate_rates_same_size"] = cands;
        n["likely_mf_synthesized_candidates"] = n_flagged;
        if (best == SIZE_MAX && best_flagged != SIZE_MAX) {
            if (!allow_synth) {
                o.hr = MF_E_INVALIDMEDIATYPE; n["synthesized_refused"] = true;
                n["reason"] = "refused: the only matching native type is an NV12 listed right before a same-mode MJPG type "
                              "(likely MF-synthesized decode, not the camera's own frames); --allow-synthesized captures it anyway";
                return o;
            }
            best = best_flagged;
        }
        if (best == SIZE_MAX) { o.hr = MF_E_INVALIDMEDIATYPE; n["reason"] = "no native type with this subtype, size and rate"; return o; }
        const T& sel = ts[best];
        n["native_type_index"] = (unsigned long)sel.idx;
        n["likely_mf_synthesized"] = synthesized(best);
        o.rx = raw_expect(sel.t.Get(), sel.sub, sel.w, sel.h);
        n["raw"] = o.rx.raw;
        if (o.rx.raw) {
            JV r = JV::obj();
            r["expected_frame_bytes"] = o.rx.bytes ? JV((unsigned long long)o.rx.bytes) : JV(); r["basis"] = o.rx.basis;
            r["stride"] = o.rx.stride ? JV(o.rx.stride) : JV(); r["layout"] = o.rx.layout; r["native_type_attrs"] = o.rx.attrs;
            n["raw_frame"] = r;
        }
        HRESULT h = rd->SetStreamSelection((DWORD)MF_SOURCE_READER_ALL_STREAMS, FALSE);
        if (SUCCEEDED(h)) h = rd->SetStreamSelection((DWORD)MF_SOURCE_READER_FIRST_VIDEO_STREAM, TRUE);
        n["stream_selection_hr"] = hrs(h);
        o.hr = rd->SetCurrentMediaType((DWORD)MF_SOURCE_READER_FIRST_VIDEO_STREAM, nullptr, sel.t.Get());
        if (FAILED(o.hr)) return o;
        ComPtr<IMFMediaType> cur;
        HRESULT hc = rd->GetCurrentMediaType((DWORD)MF_SOURCE_READER_FIRST_VIDEO_STREAM, &cur);
        n["readback_hr"] = hrs(hc);
        if (SUCCEEDED(hc)) {
            GUID cs{}; UINT32 w = 0, hh = 0, fn = 0, fd = 1;
            cur->GetGUID(MF_MT_SUBTYPE, &cs); MFGetAttributeSize(cur.Get(), MF_MT_FRAME_SIZE, &w, &hh); MFGetAttributeRatio(cur.Get(), MF_MT_FRAME_RATE, &fn, &fd);
            n["subtype"] = subtype_fourcc(cs); n["width"] = w; n["height"] = hh; n["fps_num"] = fn; n["fps_den"] = fd; n["fps"] = fd ? (double)fn / fd : 0.0;
            UINT32 ds = 0; n["readback_default_stride"] = SUCCEEDED(cur->GetUINT32(MF_MT_DEFAULT_STRIDE, &ds)) ? JV((long)(INT32)ds) : JV();
            bool ok = cs == want && w == m.w && hh == m.h && fn == sel.fn && fd == sel.fd;
            n["readback_ok"] = ok;
            if (!ok) { o.hr = MF_E_INVALIDMEDIATYPE; n["reason"] = "GetCurrentMediaType readback differs from the selected native type"; }
        } else { n["readback_ok"] = false; o.hr = hc; }
        return o;
    });
    s.settype_ms = stp.ms;
    s.negotiated = stp.value.n;
    s.steps.push(step_rec("set_type", stp.value.hr, stp.ms, stp.timed_out));
    if (stp.timed_out || FAILED(stp.value.hr)) { fail(s, "set_type", stp.timed_out ? E_FAIL : stp.value.hr, stp.timed_out); return false; }
    {
        std::lock_guard<std::recursive_mutex> lk(st->mu);
        st->raw = stp.value.rx.raw; st->expect_len = stp.value.rx.bytes;
    }

    g_stage = "start";
    auto stt = timed<HRESULT>(G.timeout_ms, [rd, st](CallCtl&) {
        std::lock_guard<std::recursive_mutex> lk(st->mu);
        st->reader = rd.Get(); st->issue_ns = qpc_ns(); st->progress_ns = st->issue_ns;
        return rd->ReadSample((DWORD)MF_SOURCE_READER_FIRST_VIDEO_STREAM, 0, nullptr, nullptr, nullptr, nullptr);
    });
    s.steps.push(step_rec("read_sample_issue", stt.value, stt.ms, stt.timed_out));
    if (stt.timed_out || FAILED(stt.value)) { fail(s, "read_sample_issue", stt.value, stt.timed_out); return false; }
    return true;
}

// Wait for the first sample (per-sample timeout = --timeout-ms). Records first_frame_ms.
static bool wait_first(Session& s) {
    g_stage = "first_sample";
    auto& st = *s.st;
    for (;;) {
        WaitForSingleObject(st.ev_sample, 20);
        std::lock_guard<std::recursive_mutex> lk(st.mu);
        if (st.frames > 0) {
            s.first_frame_ms = (double)(st.first_ns - st.issue_ns) / 1e6;
            s.open_to_first_ms = (double)(st.first_ns - s.t_open_ns) / 1e6;
            s.steps.push(step_rec("first_sample", S_OK, s.first_frame_ms, false));
            return true;
        }
        if (st.err_set) { s.steps.push(step_rec("first_sample", st.err, (double)(qpc_ns() - st.issue_ns) / 1e6, false)); fail(s, "first_sample", st.err, false); return false; }
        if (st.eos) { s.steps.push(step_rec("first_sample", MF_E_END_OF_STREAM, 0, false)); fail(s, "first_sample", MF_E_END_OF_STREAM, false); return false; }
        if ((qpc_ns() - st.progress_ns) / 1000000 > (int64_t)G.timeout_ms) {
            s.steps.push(step_rec("first_sample", E_FAIL, (double)(qpc_ns() - st.issue_ns) / 1e6, true)); fail(s, "first_sample", E_FAIL, true); return false;
        }
    }
}

// Release in the safe order with every step bounded. Sets s.unreleasable when a step does not return.
static void close_session(Session& s) {
    g_stage = "close";
    double t0 = now_ms();
    if (s.st) {
        { std::lock_guard<std::recursive_mutex> lk(s.st->mu); s.st->stop = true; s.st->reader = nullptr; }
        // let a ReadSample already being issued by the callback return before Flush (bounded)
        double w0 = now_ms(); int inflight = 0;
        for (;;) {
            { std::lock_guard<std::recursive_mutex> lk(s.st->mu); inflight = s.st->issuing; }
            if (!inflight || now_ms() - w0 > G.timeout_ms) break;
            Sleep(1);
        }
        if (inflight) { s.steps.push(step_rec("wait_read_issue", E_FAIL, now_ms() - w0, true)); s.unreleasable = true; fail(s, "wait_read_issue", E_FAIL, true); s.close_ms = now_ms() - t0; return; }
    }
    if (s.reader) {
        ComPtr<IMFSourceReader> rd = s.reader;
        auto st = s.st;
        ResetEvent(st->ev_flush);
        auto fl = timed<HRESULT>(G.timeout_ms, [rd](CallCtl&) { return rd->Flush((DWORD)MF_SOURCE_READER_ALL_STREAMS); });
        double fwait = 0; bool flushed = false;
        if (!fl.timed_out && SUCCEEDED(fl.value)) { double w0 = now_ms(); flushed = WaitForSingleObject(st->ev_flush, G.timeout_ms) == WAIT_OBJECT_0; fwait = now_ms() - w0; }
        s.flush_ms = fl.ms + fwait;
        JV fs = step_rec("flush", fl.value, s.flush_ms, fl.timed_out); fs["on_flush_received"] = flushed; s.steps.push(fs);
        if (fl.timed_out) { s.unreleasable = true; fail(s, "flush", E_FAIL, true); s.close_ms = now_ms() - t0; return; }
        rd.Reset();
        ComPtr<IMFSourceReader> last = std::move(s.reader);
        auto rr = timed<ULONG>(G.timeout_ms, [last = std::move(last)](CallCtl&) mutable { last.Reset(); return 0UL; });
        s.reader_release_ms = rr.ms;
        s.steps.push(step_rec("reader_release", S_OK, rr.ms, rr.timed_out));
        if (rr.timed_out) { s.unreleasable = true; fail(s, "reader_release", E_FAIL, true); s.close_ms = now_ms() - t0; return; }
    }
    if (s.ctl.cc || s.ctl.pa || s.ctl.ks) {
        CtlIfaces c = std::move(s.ctl); s.ctl = CtlIfaces();
        auto cr = timed<ULONG>(G.timeout_ms, [c = std::move(c)](CallCtl&) mutable { c = CtlIfaces(); return 0UL; });
        s.steps.push(step_rec("control_interfaces_release", S_OK, cr.ms, cr.timed_out));
        if (cr.timed_out) { s.unreleasable = true; fail(s, "control_interfaces_release", E_FAIL, true); s.close_ms = now_ms() - t0; return; }
    }
    bool hung = false;
    JV sh = shutdown_mf(s.src, s.act, &hung);
    for (auto& x : sh.a) {
        auto* nm = x.get("step"); auto* ms = x.get("ms");
        if (nm && ms && nm->s == "source_shutdown") s.shutdown_ms = ms->d;
        if (nm && ms && nm->s == "activate_shutdown_object") s.shutdown_object_ms = ms->d;
        s.steps.push(x);
    }
    if (hung) { s.unreleasable = true; fail(s, "shutdown", E_FAIL, true); }
    s.cb.Reset();
    s.close_ms = now_ms() - t0;
}

static JV session_error(const Session& s) {
    if (s.stage_failed.empty()) return JV();
    const char* reason = "";
    JV e = JV::obj();
    e["stage"] = s.stage_failed;
    e["hr"] = s.timed_out ? JV() : JV(hrs(s.hr));
    e["hr_name"] = s.timed_out ? JV("timeout") : JV(hr_name(s.hr));
    e["message"] = s.timed_out ? std::string("no return within --timeout-ms") : hr_message(s.hr);
    e["class"] = s.found ? error_class(s.hr, s.timed_out, &reason) : "device_error";
    e["reason"] = s.found ? reason : "device not present at re-enumeration";
    return e;
}

// ============================================================================================ sensor activity monitor

typedef HRESULT(WINAPI* PFN_MFCreateSensorActivityMonitor)(IMFSensorActivitiesReportCallback*, IMFSensorActivityMonitor**);

class ActivityMon : public IMFSensorActivitiesReportCallback {
    std::atomic<long> ref_{1};
    std::mutex mu_;
    bool got_ = false;
    int reports_ = 0;
    double first_ms_ = -1;
    std::map<std::string, std::vector<std::pair<ULONG, bool>>> snap_;  // lower symlink -> (pid, streaming)
    std::map<std::string, std::string> orig_;                          // lower symlink -> symlink as reported
public:
    ComPtr<IMFSensorActivityMonitor> mon;
    HRESULT start_hr = E_NOTIMPL;
    virtual ~ActivityMon() = default;
    STDMETHODIMP QueryInterface(REFIID iid, void** pp) override {
        if (!pp) return E_POINTER;
        if (iid == __uuidof(IUnknown) || iid == __uuidof(IMFSensorActivitiesReportCallback)) { *pp = static_cast<IMFSensorActivitiesReportCallback*>(this); AddRef(); return S_OK; }
        *pp = nullptr; return E_NOINTERFACE;
    }
    STDMETHODIMP_(ULONG) AddRef() override { return (ULONG)++ref_; }
    STDMETHODIMP_(ULONG) Release() override { long r = --ref_; if (r == 0) delete this; return (ULONG)r; }
    STDMETHODIMP OnActivitiesReport(IMFSensorActivitiesReport* rep) override {
        std::map<std::string, std::vector<std::pair<ULONG, bool>>> m;
        std::map<std::string, std::string> orig;
        ULONG n = 0; if (rep) rep->GetCount(&n);
        for (ULONG i = 0; i < n; i++) {
            ComPtr<IMFSensorActivityReport> r;
            if (FAILED(rep->GetActivityReport(i, &r))) continue;
            wchar_t link[2048]; ULONG wr = 0; link[0] = 0;
            r->GetSymbolicLink(link, 2048, &wr);
            ULONG pc = 0; r->GetProcessCount(&pc);
            std::string ls = lower(w2u(link)); orig[ls] = w2u(link);
            auto& v = m[ls];
            for (ULONG k = 0; k < pc; k++) {
                ComPtr<IMFSensorProcessActivity> pa;
                if (FAILED(r->GetProcessActivity(k, &pa))) continue;
                ULONG pid = 0; BOOL str = FALSE; pa->GetProcessId(&pid); pa->GetStreamingState(&str);
                v.push_back({pid, str != FALSE});
            }
        }
        std::lock_guard<std::mutex> lk(mu_); if (!got_) first_ms_ = now_ms(); got_ = true; reports_++; snap_ = std::move(m); orig_ = std::move(orig);
        return S_OK;
    }
    bool start() {
        HMODULE h = LoadLibraryW(L"mfsensorgroup.dll");
        if (!h) return false;
        auto fn = (PFN_MFCreateSensorActivityMonitor)GetProcAddress(h, "MFCreateSensorActivityMonitor");
        if (!fn) return false;
        start_hr = fn(this, &mon);
        if (SUCCEEDED(start_hr)) start_hr = mon->Start();
        return SUCCEEDED(start_hr);
    }
    // in_use_by_other: true/false when a report has arrived, null otherwise. Frame Server clients only (DirectShow
    // clients going through ksproxy are not reported).
    JV query(const std::string& symlink, JV* pids) {
        std::lock_guard<std::mutex> lk(mu_);
        if (!got_) return JV();
        ULONG self = GetCurrentProcessId(); bool other = false;
        JV pl = JV::arr();
        auto it = snap_.find(lower(symlink));
        if (it != snap_.end()) for (auto& p : it->second) { if (p.first != self && p.second) other = true; JV e = JV::obj(); e["pid"] = p.first; e["streaming"] = p.second; pl.push(e); }
        if (pids) *pids = pl;
        return JV(other);
    }
    bool got() { std::lock_guard<std::mutex> lk(mu_); return got_; }
    int reports() { std::lock_guard<std::mutex> lk(mu_); return reports_; }
    double first_ms() { std::lock_guard<std::mutex> lk(mu_); return first_ms_; }
    // every symlink of the last report -> [(pid, streaming)]
    std::vector<std::pair<std::string, std::vector<std::pair<ULONG, bool>>>> all() {
        std::lock_guard<std::mutex> lk(mu_);
        std::vector<std::pair<std::string, std::vector<std::pair<ULONG, bool>>>> out;
        for (auto& kv : snap_) out.push_back({orig_.count(kv.first) ? orig_[kv.first] : kv.first, kv.second});
        return out;
    }
};

// ============================================================================================ activity

// Image path of a process id (PROCESS_QUERY_LIMITED_INFORMATION only; empty when access is denied).
static std::string process_image(ULONG pid) {
    HANDLE h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (!h) return std::string();
    wchar_t buf[1024]; DWORD n = 1024; std::string out;
    if (QueryFullProcessImageNameW(h, 0, buf, &n)) out = w2u(buf);
    CloseHandle(h);
    return out;
}
static std::string base_name(const std::string& path) {
    size_t p = path.find_last_of("\\/");
    return p == std::string::npos ? path : path.substr(p + 1);
}
static JV filetime_json(ULONGLONG ft) {
    if (!ft) return JV();
    FILETIME f; f.dwLowDateTime = (DWORD)(ft & 0xFFFFFFFF); f.dwHighDateTime = (DWORD)(ft >> 32);
    SYSTEMTIME st; if (!FileTimeToSystemTime(&f, &st)) return JV();
    char b[40]; snprintf(b, sizeof b, "%04u-%02u-%02uT%02u:%02u:%02uZ", st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond);
    return JV(b);
}
// One app key of the privacy ConsentStore (read-only): LastUsedTimeStart / LastUsedTimeStop (FILETIME QWORDs).
static void consent_app(HKEY parent, const std::wstring& sub, const std::string& kind, const std::string& scope, JV& in_use, int& n_apps) {
    HKEY k = nullptr;
    if (RegOpenKeyExW(parent, sub.c_str(), 0, KEY_READ, &k) != ERROR_SUCCESS) return;
    ULONGLONG start = 0, stop = 0; DWORD sz = sizeof(ULONGLONG), type = 0;
    bool hs = RegQueryValueExW(k, L"LastUsedTimeStart", nullptr, &type, (LPBYTE)&start, &sz) == ERROR_SUCCESS && type == REG_QWORD;
    sz = sizeof(ULONGLONG);
    bool he = RegQueryValueExW(k, L"LastUsedTimeStop", nullptr, &type, (LPBYTE)&stop, &sz) == ERROR_SUCCESS && type == REG_QWORD;
    RegCloseKey(k);
    if (!hs) return;
    n_apps++;
    if (start > 0 && (!he || stop == 0 || stop < start)) {
        std::string app = w2u(sub.c_str());
        size_t bs = app.find_last_of('\\'); if (bs != std::string::npos) app = app.substr(bs + 1);
        if (kind == "non_packaged") for (auto& c : app) if (c == '#') c = '\\';
        JV e = JV::obj(); e["app"] = app; e["kind"] = kind; e["hive"] = scope;
        e["last_used_start_utc"] = filetime_json(start); e["last_used_stop_utc"] = he ? filetime_json(stop) : JV();
        in_use.push(e);
    }
}
// Apps the Windows privacy layer currently counts as using a camera (LastUsedTimeStop == 0 or < Start). Covers MF
// and DirectShow clients, but is per capability, not per camera. Read-only registry access.
static JV consent_store_webcam() {
    JV j = JV::obj(); JV in_use = JV::arr(); int n_apps = 0;
    const wchar_t* base = L"Software\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\webcam";
    struct H { HKEY root; const char* name; } hives[] = {{HKEY_CURRENT_USER, "HKCU"}, {HKEY_LOCAL_MACHINE, "HKLM"}};
    JV opened = JV::obj();
    for (auto& hv : hives) {
        HKEY k = nullptr;
        LONG rc = RegOpenKeyExW(hv.root, base, 0, KEY_READ, &k);
        opened[hv.name] = rc == ERROR_SUCCESS;
        if (rc != ERROR_SUCCESS) continue;
        for (DWORD i = 0;; i++) {
            wchar_t name[512]; DWORD nl = 512;
            if (RegEnumKeyExW(k, i, name, &nl, nullptr, nullptr, nullptr, nullptr) != ERROR_SUCCESS) break;
            std::wstring wn(name);
            if (wn == L"NonPackaged") {
                HKEY np = nullptr;
                if (RegOpenKeyExW(k, L"NonPackaged", 0, KEY_READ, &np) == ERROR_SUCCESS) {
                    for (DWORD q = 0;; q++) {
                        wchar_t n2[1024]; DWORD l2 = 1024;
                        if (RegEnumKeyExW(np, q, n2, &l2, nullptr, nullptr, nullptr, nullptr) != ERROR_SUCCESS) break;
                        consent_app(np, n2, "non_packaged", hv.name, in_use, n_apps);
                    }
                    RegCloseKey(np);
                }
            } else {
                consent_app(k, wn, "packaged", hv.name, in_use, n_apps);
            }
        }
        RegCloseKey(k);
    }
    j["hives_opened"] = opened; j["apps_with_timestamps"] = n_apps; j["in_use"] = in_use;
    j["note"] = "privacy ConsentStore (read-only): apps whose LastUsedTimeStop is 0 or before LastUsedTimeStart are using a camera now; per capability, not per camera; covers MF and DirectShow clients";
    return j;
}

// wincam activity: who uses each camera, without opening any camera. IMFSensorActivityMonitor (Frame Server clients:
// pid + streaming state per symbolic link) plus the ConsentStore. MFEnumDeviceSources only reads property bags.
static int cmd_activity(const std::string& device_filter) {
    JV j = header("activity");
    j["camera_opened"] = false;
    j["note"] = "no IMFActivate::ActivateObject, no IMoniker::BindToObject: Frame Server activity reports + read-only registry";
    g_stage = "enumerate";
    std::vector<MfDev> mf; HRESULT eh = enum_mf(mf);
    j["mf_enum_hr"] = hrs(eh);
    ActivityMon* mon = new ActivityMon();
    double t0 = now_ms();
    g_stage = "monitor_start";
    bool ok = mon->start();
    g_stage = "monitor_wait";
    JV mj = JV::obj(); mj["available"] = ok; mj["hr"] = hrs(mon->start_hr); mj["source"] = "IMFSensorActivityMonitor (mfsensorgroup.dll)";
    if (ok) {
        while (!mon->got() && now_ms() - t0 < G.wait_ms) Sleep(10);
        if (mon->got()) Sleep(150);  // let a burst of reports settle
    }
    mj["report_received"] = mon->got(); mj["reports"] = mon->reports(); mj["wait_ms"] = (unsigned long)G.wait_ms;
    mj["first_report_ms"] = mon->got() ? JV(mon->first_ms() - t0) : JV();
    g_stage = "monitor_snapshot";
    auto all = mon->all();
    const bool got = mon->got();  // read before Release (the callback object is freed there)
    g_stage = "monitor_stop";
    if (ok && mon->mon) { auto mm = mon->mon; timed<HRESULT>(G.timeout_ms, [mm](CallCtl&) { return mm->Stop(); }); }
    mon->mon.Reset();
    mon->Release();
    j["monitor"] = mj;
    g_stage = "processes";
    ULONG self = GetCurrentProcessId();
    std::map<ULONG, std::string> img;
    auto proc_json = [&](ULONG pid, bool streaming) {
        if (!img.count(pid)) img[pid] = process_image(pid);
        JV e = JV::obj(); e["pid"] = pid; e["streaming"] = streaming; e["image"] = img[pid].empty() ? JV() : JV(img[pid]);
        e["name"] = img[pid].empty() ? JV() : JV(base_name(img[pid])); e["self"] = pid == self;
        return e;
    };
    JV devs = JV::arr(); std::map<std::string, bool> seen;
    std::string flt = lower(device_filter), fltn = norm_link(device_filter);
    auto wanted = [&](const std::string& link, const std::string& name) {
        if (flt.empty()) return true;
        return contains(lower(link), flt) || (!fltn.empty() && contains(norm_link(link), fltn)) || contains(lower(name), flt);
    };
    for (auto& d : mf) {
        if (!wanted(d.symlink, d.name)) continue;
        JV e = JV::obj(); e["friendly_name"] = d.name; e["symlink"] = d.symlink; e["match_key"] = norm_link(d.symlink); e["usb"] = parse_usb_ids(d.symlink);
        JV pl = JV::arr(); bool streaming = false;
        for (auto& a : all) {
            if (norm_link(a.first) != norm_link(d.symlink)) continue;
            seen[lower(a.first)] = true;
            for (auto& p : a.second) { pl.push(proc_json(p.first, p.second)); if (p.second) streaming = true; }
        }
        e["processes"] = pl; e["in_use"] = got ? JV(pl.size() > 0) : JV(); e["streaming"] = streaming;  // in_use null: no report arrived
        devs.push(e);
    }
    for (auto& a : all) {  // reported links without an MF device entry (e.g. sensor groups)
        if (seen.count(lower(a.first)) || !wanted(a.first, "")) continue;
        JV e = JV::obj(); e["friendly_name"] = nullptr; e["symlink"] = a.first; e["match_key"] = norm_link(a.first); e["usb"] = parse_usb_ids(a.first);
        JV pl = JV::arr(); bool streaming = false;
        for (auto& p : a.second) { pl.push(proc_json(p.first, p.second)); if (p.second) streaming = true; }
        e["processes"] = pl; e["in_use"] = pl.size() > 0; e["streaming"] = streaming; e["not_in_mf_list"] = true;
        devs.push(e);
    }
    j["devices"] = devs;
    g_stage = "consent_store";
    j["consent_store"] = consent_store_webcam();
    g_stage = "emit";
    j["coverage_note"] = "IMFSensorActivityMonitor reports Frame Server (MF / WinRT) clients only; DirectShow (ksproxy) clients are invisible to it but show in consent_store.in_use (per capability, not per camera)";
    j["error"] = nullptr;
    return emit(j, 0);
}

// ============================================================================================ capture

struct SchedItem { double at_ms; SetReq rq; std::string raw; };

static bool parse_schedule(const std::string& spec, std::vector<SchedItem>& out, std::string& err) {
    size_t p0 = 0;
    while (p0 <= spec.size()) {
        size_t p = spec.find(';', p0);
        std::string item = spec.substr(p0, p == std::string::npos ? std::string::npos : p - p0);
        p0 = p == std::string::npos ? spec.size() + 1 : p + 1;
        if (item.empty()) continue;
        size_t c = item.find(':');
        if (c == std::string::npos) { err = "bad schedule item (need ms:id=value): " + item; return false; }
        SchedItem si; si.raw = item; char* e = nullptr; si.at_ms = strtod(item.substr(0, c).c_str(), &e);
        if (!e || *e) { err = "bad schedule time: " + item; return false; }
        std::vector<SetReq> one;
        if (!parse_sets(item.substr(c + 1), 2, one, err) || one.size() != 1) { if (err.empty()) err = "one control per schedule item: " + item; return false; }
        si.rq = one[0];
        out.push_back(si);
    }
    std::stable_sort(out.begin(), out.end(), [](const SchedItem& a, const SchedItem& b) { return a.at_ms < b.at_ms; });
    return true;
}

struct CaptureOpts {
    Mode mode; uint64_t frames = 0; double seconds = 0; std::string out_dir; int save_mode = 0; uint64_t save_every = 1;
    std::string stop_file;  // stop cleanly (same release order) as soon as this file exists
    std::vector<SchedItem> schedule; std::vector<SetReq> controls_before;
};

static double proc_cpu_s(double* user, double* kern) {
    FILETIME c, e, k, u;
    if (!GetProcessTimes(GetCurrentProcess(), &c, &e, &k, &u)) return 0;
    auto f = [](const FILETIME& ft) { ULARGE_INTEGER x; x.LowPart = ft.dwLowDateTime; x.HighPart = ft.dwHighDateTime; return x.QuadPart / 1e7; };
    *user = f(u); *kern = f(k); return *user + *kern;
}

static int capture_cmd(CaptureOpts& o) {
    JV j = header("capture"); j["api"] = "mf";
    ensure_dir(o.out_dir);
    g_partial_file = o.out_dir + "\\summary.json";
    JV req = JV::obj(); req["subtype"] = o.mode.subtype; req["width"] = o.mode.w; req["height"] = o.mode.h; req["fps"] = o.mode.fps;
    req["frames"] = o.frames ? JV((unsigned long long)o.frames) : JV(); req["seconds"] = o.seconds > 0 ? JV(o.seconds) : JV();
    req["save"] = o.save_mode == 0 ? std::string("none") : (o.save_mode == 1 ? std::string("all") : "every:" + std::to_string(o.save_every));
    req["allow_synthesized"] = G.allow_synth;
    j["requested"] = req; j["out_dir"] = o.out_dir;
    MfDev dev;
    int rc = resolve_mf(G.device, &dev, j);
    if (rc) { std::string s = j.dump(1); write_text_file(g_partial_file, s); return emit(j, rc); }

    auto st = std::make_shared<StreamState>();
    st->req_w = o.mode.w; st->req_h = o.mode.h; st->max_frames = o.frames;
    GUID want{}; subtype_guid(o.mode.subtype, &want);
    const bool raw_req = !is_compressed_subtype(want);   // raw frames are saved to frames.raw, JPEG to frames.mjpeg
    const std::string saved_path = o.out_dir + (raw_req ? "\\frames.raw" : "\\frames.mjpeg");
    st->jsonl = _wfopen(u2w(o.out_dir + "\\frames.jsonl").c_str(), L"wb");
    if (o.save_mode) { st->mjpeg = _wfopen(u2w(saved_path).c_str(), L"wb"); st->save_mode = o.save_mode; st->save_every = std::max<uint64_t>(1, o.save_every); }
    if (!st->jsonl) { j["error"] = JV::obj(); j["error"]["stage"] = "output"; j["error"]["reason"] = "cannot create frames.jsonl"; return emit(j, 2); }

    Session s;
    JV cb_out = JV::arr();
    { std::lock_guard<std::mutex> lk(g_partial_mu); g_partial = JV::obj(); g_partial["stage"] = "opening"; g_partial["device"] = dev.symlink; }
    bool opened = open_session(s, dev.symlink, o.mode, st, &o.controls_before, &cb_out);
    j["controls_before"] = cb_out;
    bool ok = opened && wait_first(s);
    JV sched = JV::arr();
    double cu0 = 0, ck0 = 0, cu1 = 0, ck1 = 0;
    proc_cpu_s(&cu0, &ck0);
    int64_t cpu_t0 = qpc_ns();
    bool stream_timeout = false, ctl_timeout = false, stopped_by_file = false;
    std::wstring stopw = o.stop_file.empty() ? std::wstring() : u2w(o.stop_file);
    if (ok) {
        g_stage = "streaming";
        size_t next = 0;
        for (;;) {
            int64_t now = qpc_ns();
            int64_t first_ns, progress_ns; uint64_t frames; bool err, eos;
            { std::lock_guard<std::recursive_mutex> lk(st->mu); first_ns = st->first_ns; progress_ns = st->progress_ns; frames = st->frames; err = st->err_set; eos = st->eos; }
            double since_first_ms = (double)(now - first_ns) / 1e6;
            if (err || eos) { ok = false; fail(s, "streaming", err ? st->err : MF_E_END_OF_STREAM, false); break; }
            if (o.frames && frames >= o.frames) break;
            if (o.seconds > 0 && since_first_ms >= o.seconds * 1000.0) break;
            if (!stopw.empty() && GetFileAttributesW(stopw.c_str()) != INVALID_FILE_ATTRIBUTES) { stopped_by_file = true; break; }
            if ((now - progress_ns) / 1000000 > (int64_t)G.timeout_ms) { ok = false; stream_timeout = true; fail(s, "streaming", E_FAIL, true); break; }
            while (next < o.schedule.size() && since_first_ms >= o.schedule[next].at_ms) {
                auto& it = o.schedule[next++];
                if (ctl_timeout) { JV e = JV::obj(); e["at_ms"] = it.at_ms; e["item"] = it.raw; e["skipped"] = "earlier control call timed out"; sched.push(e); continue; }
                int64_t ta = qpc_ns(); uint64_t fseq;
                { std::lock_guard<std::recursive_mutex> lk(st->mu); fseq = st->frames; }
                auto so = apply_set(s.ctl, it.rq);
                JV e = so.rec; e["at_ms"] = it.at_ms; e["item"] = it.raw; e["applied_qpc_ns"] = (long long)ta;
                e["applied_ms_after_first_frame"] = (double)(ta - first_ns) / 1e6; e["frames_before_apply"] = (unsigned long long)fseq;
                e["done_qpc_ns"] = (long long)qpc_ns();
                sched.push(e);
                if (so.timed_out) ctl_timeout = true;
            }
            DWORD wait = 50;
            if (next < o.schedule.size()) { double due = o.schedule[next].at_ms - since_first_ms; if (due < wait) wait = (DWORD)std::max(1.0, due); }
            WaitForSingleObject(st->ev_sample, wait);
            if ((frames & 31) == 0) { std::lock_guard<std::mutex> lk(g_partial_mu); g_partial["stage"] = "streaming"; g_partial["frames"] = (unsigned long long)frames; }
        }
    }
    proc_cpu_s(&cu1, &ck1);
    int64_t cpu_t1 = qpc_ns();
    // Restore nothing automatically: the runner decides (it passes --controls-before / --schedule with auto values).
    close_session(s);
    if (st->jsonl) { fclose(st->jsonl); st->jsonl = nullptr; }
    if (st->mjpeg) { fclose(st->mjpeg); st->mjpeg = nullptr; }

    std::lock_guard<std::recursive_mutex> lk(st->mu);
    j["device"]["friendly_name"] = s.name.empty() ? dev.name : s.name;
    j["negotiated"] = s.negotiated;
    j["steps"] = s.steps;
    JV t = JV::obj();
    t["enumerate_ms"] = s.enumerate_ms; t["activate_ms"] = s.activate_ms; t["reader_ms"] = s.reader_ms; t["settype_ms"] = s.settype_ms;
    t["first_frame_ms"] = s.first_frame_ms; t["open_to_first_frame_ms"] = s.open_to_first_ms;
    t["flush_ms"] = s.flush_ms; t["reader_release_ms"] = s.reader_release_ms; t["shutdown_ms"] = s.shutdown_ms; t["shutdown_object_ms"] = s.shutdown_object_ms; t["close_ms"] = s.close_ms;
    j["timings"] = t;
    JV fr = JV::obj();
    fr["total"] = (unsigned long long)st->frames; fr["ok"] = (unsigned long long)st->ok_frames; fr["soi_eoi_ok"] = (unsigned long long)st->soi_eoi;
    fr["sof0_size_match"] = (unsigned long long)st->sof_match; fr["with_uvc_metadata"] = (unsigned long long)st->with_meta;
    fr["with_capture_metadata_attr"] = (unsigned long long)st->with_capmeta; fr["stream_ticks"] = (unsigned long long)st->ticks;
    fr["null_samples"] = (unsigned long long)st->nulls; fr["discontinuities"] = (unsigned long long)st->discont; fr["bytes_total"] = (unsigned long long)st->bytes;
    fr["saved"] = (unsigned long long)st->saved;
    JV fc = JV::obj(); for (auto& kv : st->flag_counts) fc[kv.first] = (unsigned long long)kv.second; fr["reader_flag_counts"] = fc;
    fr["raw"] = st->raw;
    fr["ok_rule"] = st->raw ? "raw: buffer length == expected_frame_bytes (any length > 0 when the layout is unknown)"
                            : "jpeg: SOI + EOI + SOF size == request";
    if (st->raw) {
        fr["raw_len_ok"] = (unsigned long long)st->raw_len_ok; fr["raw_flat"] = (unsigned long long)st->raw_flat;
        fr["raw_expected_bytes"] = st->expect_len ? JV((unsigned long long)st->expect_len) : JV();
        fr["raw_len_min"] = st->frames ? JV((unsigned long long)st->len_min) : JV();
        fr["raw_len_max"] = st->frames ? JV((unsigned long long)st->len_max) : JV();
        JV lc = JV::obj(); for (auto& kv : st->len_counts) lc[std::to_string(kv.first)] = (unsigned long long)kv.second;
        fr["raw_len_counts"] = lc; fr["raw_len_other"] = (unsigned long long)st->len_other;
        JV b = JV::obj();
        b["checked"] = st->buf_checked; b["buffer_count"] = (unsigned long)st->buf_count; b["is_2d_buffer"] = st->buf_2d;
        b["lock2d_hr"] = hrj(st->buf_lock2d_hr); b["pitch"] = st->buf_2d && SUCCEEDED(st->buf_lock2d_hr) ? JV(st->buf_pitch) : JV();
        b["contiguous_length"] = st->buf_2d ? JV((unsigned long)st->buf_contig) : JV();
        fr["buffer"] = b;
    }
    j["frames"] = fr;
    double span = st->frames > 1 ? (double)(st->last_ns - st->first_ns) / 1e9 : 0;
    j["duration_s"] = span;
    j["fps_measured"] = span > 0 ? (double)(st->frames - 1) / span : 0.0;
    j["metadata"] = JV::obj();
    j["metadata"]["uvc_pts_present"] = st->with_meta > 0;
    j["metadata"]["note"] = "UVC PTS/SCR appear only when MetadataBufferSizeInKB0 is set on this device instance (tier 1)";
    double win = (double)(cpu_t1 - cpu_t0) / 1e9;
    JV cpu = JV::obj(); cpu["user_s"] = cu1 - cu0; cpu["kernel_s"] = ck1 - ck0; cpu["window_s"] = win;
    cpu["pct_of_one_core"] = win > 0 ? 100.0 * ((cu1 - cu0) + (ck1 - ck0)) / win : 0.0; cpu["method"] = "GetProcessTimes over the streaming window";
    double tu = 0, tk = 0; proc_cpu_s(&tu, &tk); cpu["process_total_s"] = tu + tk;
    j["cpu"] = cpu;
    j["schedule"] = sched;
    if (!o.stop_file.empty()) { j["stop_file"] = o.stop_file; j["stopped_by_stop_file"] = stopped_by_file; }
    j["unreleasable"] = s.unreleasable;
    j["ok"] = ok && s.stage_failed.empty();
    j["error"] = session_error(s);
    int out_rc = 0;
    if (!s.stage_failed.empty()) out_rc = (s.timed_out || stream_timeout || s.unreleasable) ? 5 : (s.found ? 4 : 3);
    if (ctl_timeout && out_rc == 0) out_rc = 5;
    j["files"] = JV::obj(); j["files"]["frames_jsonl"] = o.out_dir + "\\frames.jsonl";
    j["files"]["frames_mjpeg"] = o.save_mode && !raw_req ? JV(saved_path) : JV();
    j["files"]["frames_raw"] = o.save_mode && raw_req ? JV(saved_path) : JV();
    JV copy = j; copy["utc_finished"] = utc_now(); copy["exit_code"] = out_rc; copy["abandoned_threads"] = g_abandoned_threads.load();
    write_text_file(g_partial_file, copy.dump(1) + "\n");
    return emit(j, out_rc);
}

// ============================================================================================ cycle

struct CycleOpts { Mode mode, alt; bool has_alt = false; int cycles = 10; uint64_t frames = 30; DWORD gap_ms = 0; std::string out_dir; };

static double pct(std::vector<double> v, double p) {
    if (v.empty()) return NAN;
    std::sort(v.begin(), v.end());
    double idx = p / 100.0 * (double)(v.size() - 1); size_t lo = (size_t)std::floor(idx), hi = (size_t)std::ceil(idx);
    return v[lo] + (v[hi] - v[lo]) * (idx - (double)lo);
}

static int cycle_cmd(CycleOpts& o) {
    JV j = header("cycle"); j["api"] = "mf";
    ensure_dir(o.out_dir);
    g_partial_file = o.out_dir + "\\summary.json";
    JV req = JV::obj(); req["mode"] = mode_str(o.mode); req["alt_mode"] = o.has_alt ? JV(mode_str(o.alt)) : JV(); req["cycles"] = o.cycles;
    req["frames_per_cycle"] = (unsigned long long)o.frames; req["gap_ms"] = (unsigned long)o.gap_ms;
    req["allow_synthesized"] = G.allow_synth;
    j["requested"] = req; j["out_dir"] = o.out_dir;
    j["release_order"] = "stop reads -> IMFSourceReader::Flush (wait OnFlush) -> reader Release -> IMFMediaSource::Shutdown -> IMFActivate::ShutdownObject; device re-enumerated every cycle";
    MfDev dev;
    int rc = resolve_mf(G.device, &dev, j);
    if (rc) { write_text_file(g_partial_file, j.dump(1)); return emit(j, rc); }
    std::string symlink = dev.symlink;
    dev.act.Reset();

    ActivityMon* mon = new ActivityMon();
    bool mon_ok = mon->start();
    j["activity_monitor"] = JV::obj(); j["activity_monitor"]["available"] = mon_ok; j["activity_monitor"]["hr"] = hrs(mon->start_hr);

    FILE* cj = _wfopen(u2w(o.out_dir + "\\cycles.jsonl").c_str(), L"wb");
    if (!cj) { j["error"] = JV::obj(); j["error"]["reason"] = "cannot create cycles.jsonl"; return emit(j, 2); }
    int ok_n = 0, fail_n = 0, timeouts = 0, hung_setup = 0; bool unreleasable = false;
    std::vector<double> ff, act_ms, close_ms, o2f, fps_v;
    std::map<std::string, int> by_stage, by_class;
    int run = 0, longest = 0; int after_fail = 0, recovered = 0; bool prev_fail = false;
    for (int i = 0; i < o.cycles; i++) {
        Mode m = (o.has_alt && (i % 2 == 1)) ? o.alt : o.mode;
        auto st = std::make_shared<StreamState>();
        st->req_w = m.w; st->req_h = m.h; st->max_frames = o.frames;
        Session s;
        int64_t c0 = qpc_ns();
        bool good = open_session(s, symlink, m, st, nullptr, nullptr) && wait_first(s);
        if (good) {
            g_stage = "cycle_frames";
            for (;;) {
                WaitForSingleObject(st->ev_sample, 20);
                std::lock_guard<std::recursive_mutex> lk(st->mu);
                if (st->frames >= o.frames) break;
                if (st->err_set) { good = false; fail(s, "streaming", st->err, false); break; }
                if (st->eos) { good = false; fail(s, "streaming", MF_E_END_OF_STREAM, false); break; }
                if ((qpc_ns() - st->progress_ns) / 1000000 > (int64_t)G.timeout_ms) { good = false; fail(s, "streaming", E_FAIL, true); break; }
            }
        }
        JV pids; JV in_use = mon_ok ? mon->query(symlink, &pids) : JV();
        close_session(s);
        JV r = JV::obj();
        r["i"] = i; r["mode"] = mode_str(m); r["ok"] = good && s.stage_failed.empty();
        r["stage_failed"] = s.stage_failed.empty() ? JV() : JV(s.stage_failed);
        r["hr"] = s.stage_failed.empty() ? JV() : (s.timed_out ? JV() : JV(hrs(s.hr)));
        r["hr_name"] = s.stage_failed.empty() ? JV() : (s.timed_out ? JV("timeout") : JV(hr_name(s.hr)));
        JV err = session_error(s);
        r["error_class"] = err.t == JV::Obj ? *err.get("class") : JV();
        r["timed_out"] = s.timed_out;
        r["enumerate_ms"] = s.enumerate_ms; r["activate_ms"] = s.activate_ms; r["reader_ms"] = s.reader_ms; r["settype_ms"] = s.settype_ms;
        r["first_frame_ms"] = s.first_frame_ms; r["open_to_first_frame_ms"] = s.open_to_first_ms;
        double cyc_fps = NAN;
        {
            std::lock_guard<std::recursive_mutex> lk(st->mu);
            r["frames"] = (unsigned long long)st->frames; r["frames_ok"] = (unsigned long long)st->ok_frames; r["with_uvc_metadata"] = (unsigned long long)st->with_meta;
            // delivered rate of this cycle: (frames - 1) / (last - first arrival), QPC at callback entry (as capture)
            double span = st->frames > 1 ? (double)(st->last_ns - st->first_ns) / 1e9 : 0.0;
            if (span > 0) cyc_fps = (double)(st->frames - 1) / span;
            r["fps_measured"] = span > 0 ? JV(cyc_fps) : JV(); r["duration_s"] = span > 0 ? JV(span) : JV();
            r["raw"] = st->raw;
            if (st->raw) { r["raw_expected_bytes"] = st->expect_len ? JV((unsigned long long)st->expect_len) : JV(); r["raw_flat"] = (unsigned long long)st->raw_flat; }
        }
        r["negotiated_subtype"] = s.negotiated.get("subtype") ? *s.negotiated.get("subtype") : JV();
        r["likely_mf_synthesized"] = s.negotiated.get("likely_mf_synthesized") ? *s.negotiated.get("likely_mf_synthesized") : JV();
        r["close_ms"] = s.close_ms; r["flush_ms"] = s.flush_ms; r["reader_release_ms"] = s.reader_release_ms; r["shutdown_ms"] = s.shutdown_ms; r["shutdown_object_ms"] = s.shutdown_object_ms;
        r["in_use_by_other"] = in_use; if (pids.t == JV::Arr) r["activity_pids"] = pids;
        r["unreleasable"] = s.unreleasable;
        r["negotiated_ok"] = s.negotiated.get("readback_ok") ? *s.negotiated.get("readback_ok") : JV();
        r["t_start_qpc_ns"] = (long long)c0; r["utc"] = utc_now();
        r["steps"] = s.steps;
        std::string line = r.dump(0); line += "\n";
        fwrite(line.data(), 1, line.size(), cj); fflush(cj);
        bool cyc_ok = good && s.stage_failed.empty();
        if (cyc_ok) {
            ok_n++; ff.push_back(s.first_frame_ms); o2f.push_back(s.open_to_first_ms);
            if (std::isfinite(cyc_fps)) fps_v.push_back(cyc_fps);
            if (prev_fail) recovered++;
            run = 0;
        } else {
            fail_n++; run++; longest = std::max(longest, run);
            by_stage[s.stage_failed]++;
            if (err.t == JV::Obj) by_class[err.get("class")->s]++;
            if (s.timed_out) timeouts++;
            if (s.timed_out && (s.stage_failed == "enumerate" || s.stage_failed == "activate" || s.stage_failed == "reader_create" || s.stage_failed == "set_type" || s.stage_failed == "read_sample_issue")) hung_setup++;
        }
        if (prev_fail) after_fail++;
        prev_fail = !cyc_ok;
        if (s.activate_ms >= 0) act_ms.push_back(s.activate_ms);
        if (s.close_ms >= 0) close_ms.push_back(s.close_ms);
        {
            std::lock_guard<std::mutex> lk(g_partial_mu);
            g_partial = JV::obj(); g_partial["cycles_done"] = i + 1; g_partial["ok"] = ok_n; g_partial["failed"] = fail_n;
        }
        wlog("cycle %d/%d %s: %s%s", i + 1, o.cycles, mode_str(m).c_str(), cyc_ok ? "ok" : "FAIL ", cyc_ok ? "" : (s.stage_failed + " " + (s.timed_out ? "timeout" : hr_name(s.hr))).c_str());
        if (s.unreleasable) { unreleasable = true; break; }
        if (hung_setup >= 2) break;
        if (o.gap_ms && i + 1 < o.cycles) Sleep(o.gap_ms);
    }
    fclose(cj);
    if (mon_ok && mon->mon) { auto mm = mon->mon; timed<HRESULT>(G.timeout_ms, [mm](CallCtl&) { return mm->Stop(); }); }
    mon->mon.Reset();
    mon->Release();
    int done = ok_n + fail_n;
    JV sm = JV::obj();
    sm["cycles_requested"] = o.cycles; sm["cycles_run"] = done; sm["ok"] = ok_n; sm["failed"] = fail_n; sm["timeouts"] = timeouts;
    sm["success_rate"] = done ? (double)ok_n / done : 0.0;
    sm["longest_failure_run"] = longest; sm["cycles_after_a_failure"] = after_fail; sm["recovered_after_failure"] = recovered;
    sm["first_frame_ms_p50"] = pct(ff, 50); sm["first_frame_ms_p95"] = pct(ff, 95); sm["first_frame_ms_max"] = ff.empty() ? NAN : *std::max_element(ff.begin(), ff.end());
    sm["first_frame_within_2s"] = (int)std::count_if(ff.begin(), ff.end(), [](double v) { return v <= 2000.0; });
    sm["fps_measured_p50"] = pct(fps_v, 50); sm["fps_measured_min"] = fps_v.empty() ? NAN : *std::min_element(fps_v.begin(), fps_v.end());
    sm["open_to_first_frame_ms_p50"] = pct(o2f, 50); sm["activate_ms_p50"] = pct(act_ms, 50); sm["close_ms_p50"] = pct(close_ms, 50); sm["close_ms_max"] = close_ms.empty() ? NAN : *std::max_element(close_ms.begin(), close_ms.end());
    JV bs = JV::obj(); for (auto& kv : by_stage) bs[kv.first] = kv.second; sm["failures_by_stage"] = bs;
    JV bc = JV::obj(); for (auto& kv : by_class) bc[kv.first] = kv.second; sm["failures_by_class"] = bc;
    sm["unreleasable"] = unreleasable; sm["stopped_after_hung_setups"] = hung_setup >= 2;
    j["summary"] = sm;
    j["files"] = JV::obj(); j["files"]["cycles_jsonl"] = o.out_dir + "\\cycles.jsonl";
    int out_rc = (unreleasable || hung_setup >= 2) ? 5 : (fail_n ? 4 : 0);
    j["error"] = nullptr;
    if (out_rc == 5) { j["error"] = JV::obj(); j["error"]["class"] = "timeout"; j["error"]["reason"] = unreleasable ? "a reader or source could not be released (unreleasable)" : "two setup steps hung; stopped"; }
    JV copy = j; copy["utc_finished"] = utc_now(); copy["exit_code"] = out_rc; copy["abandoned_threads"] = g_abandoned_threads.load();
    write_text_file(g_partial_file, copy.dump(1) + "\n");
    return emit(j, out_rc);
}

// ============================================================================================ main

static void usage() {
    fprintf(stderr,
            "%s\n"
            "usage:\n"
            "  wincam list [--out F]\n"
            "  wincam formats  --api mf|ds --device X [--hold-ms H] [--timeout-ms T] [--out F]\n"
            "  wincam activity [--wait-ms W] [--device X] [--out F]   (opens no camera)\n"
            "  wincam controls --api mf|ds --device X [--read-only | --set id=v,... [--set-flags auto|manual] [--restore]] [--timeout-ms T] [--out F]\n"
            "  wincam capture  --api mf --device X --width W --height H --fps F [--subtype MJPG|YUY2|NV12|<FOURCC>] (--frames N | --seconds S)\n"
            "                  --timeout-ms T --out-dir D [--save none|all|every:K] [--schedule \"ms:id=v;...\"] [--controls-before id=v,...]\n"
            "                  [--stop-file F]  (stop cleanly as soon as F exists) [--allow-synthesized]\n"
            "  wincam cycle    --api mf --device X --width W --height H --fps F [--subtype S] --cycles K --frames N --timeout-ms T --out D\n"
            "                  [--alt-width W2 --alt-height H2 --alt-fps F2] [--gap-ms G] [--allow-synthesized]\n"
            "raw subtypes: frames checked by length (stride x height, 4:2:0 x 1.5); an NV12 listed right before a same-mode MJPG\n"
            "              (likely MF-synthesized) is refused unless --allow-synthesized\n"
            "common: --watchdog-ms MS (process watchdog; default derived from the request)\n"
            "control ids: names (exposure, focus, gain, white_balance, ...), cc.<name>/pa.<name>, or cc<N>/pa<N>\n"
            "exit: 0 ok, 2 usage, 3 device not found, 4 camera failure, 5 timeout\n",
            kVersion);
}

static int usage_error(const std::string& msg) {
    JV j = header(G.subcommand.empty() ? "?" : G.subcommand.c_str());
    j["error"] = JV::obj(); j["error"]["class"] = "usage"; j["error"]["reason"] = msg;
    usage();
    wlog("usage error: %s", msg.c_str());
    return emit(j, 2);
}

static LONG WINAPI crash_filter(EXCEPTION_POINTERS* ep) {
    char b[256];
    snprintf(b, sizeof b, "{\"tool\":\"wincam\",\"crash\":true,\"exception_code\":\"0x%08lX\",\"stage\":\"%s\",\"exit_code\":4}\n",
             ep && ep->ExceptionRecord ? (unsigned long)ep->ExceptionRecord->ExceptionCode : 0UL, g_stage.load());
    HANDLE h = GetStdHandle(STD_OUTPUT_HANDLE); DWORD wr = 0; WriteFile(h, b, (DWORD)strlen(b), &wr, nullptr);
    TerminateProcess(GetCurrentProcess(), 4);
    return EXCEPTION_EXECUTE_HANDLER;
}

int wmain(int argc, wchar_t** wargv) {
    SetUnhandledExceptionFilter(crash_filter);
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    G.utc_started = utc_now();
    std::vector<std::string> args;
    for (int i = 0; i < argc; i++) { args.push_back(w2u(wargv[i])); G.argv.push_back(args.back()); }
    if (argc < 2) { usage(); return 2; }
    G.subcommand = args[1];
    if (G.subcommand == "-h" || G.subcommand == "--help" || G.subcommand == "help") { usage(); return 0; }
    if (G.subcommand == "--version") { printf("%s\n", kVersion); return 0; }

    ControlsOpts co; CaptureOpts cap; CycleOpts cyc;
    std::string set_flags = "manual", save = "none", schedule, ctl_before; bool have_frames = false, have_seconds = false, have_timeout = false;
    double alt_fps = 0; UINT32 alt_w = 0, alt_h = 0;
    for (size_t i = 2; i < args.size(); i++) {
        const std::string& a = args[i];
        auto nx = [&]() -> std::string { if (i + 1 >= args.size()) { usage_error("missing value for " + a); exit(2); } return args[++i]; };
        auto num = [&](const std::string& v) -> double { char* e = nullptr; double d = strtod(v.c_str(), &e); if (!e || *e) { usage_error("bad number for " + a + ": " + v); exit(2); } return d; };
        if (a == "--api") G.api = lower(nx());
        else if (a == "--device") G.device = nx();
        else if (a == "--out") { std::string v = nx(); G.out_file = v; cyc.out_dir = v; }
        else if (a == "--out-dir") cap.out_dir = nx();
        else if (a == "--timeout-ms") { G.timeout_ms = (DWORD)num(nx()); have_timeout = true; }
        else if (a == "--watchdog-ms") G.watchdog_ms = (DWORD)num(nx());
        else if (a == "--read-only") co.read_only = true;
        else if (a == "--set") { co.sets = nx(); co.read_only = false; }
        else if (a == "--set-flags") set_flags = lower(nx());
        else if (a == "--restore") co.restore = true;
        else if (a == "--width") cap.mode.w = cyc.mode.w = (UINT32)num(nx());
        else if (a == "--height") cap.mode.h = cyc.mode.h = (UINT32)num(nx());
        else if (a == "--fps") cap.mode.fps = cyc.mode.fps = num(nx());
        else if (a == "--subtype") { std::string v = nx(); cap.mode.subtype = cyc.mode.subtype = v; }
        else if (a == "--frames") { cap.frames = cyc.frames = (uint64_t)num(nx()); have_frames = true; }
        else if (a == "--seconds") { cap.seconds = num(nx()); have_seconds = true; }
        else if (a == "--save") save = lower(nx());
        else if (a == "--schedule") schedule = nx();
        else if (a == "--controls-before") ctl_before = nx();
        else if (a == "--cycles") cyc.cycles = (int)num(nx());
        else if (a == "--alt-width") alt_w = (UINT32)num(nx());
        else if (a == "--alt-height") alt_h = (UINT32)num(nx());
        else if (a == "--alt-fps") alt_fps = num(nx());
        else if (a == "--gap-ms") cyc.gap_ms = (DWORD)num(nx());
        else if (a == "--hold-ms") G.hold_ms = (DWORD)num(nx());
        else if (a == "--wait-ms") G.wait_ms = (DWORD)num(nx());
        else if (a == "--stop-file") cap.stop_file = nx();
        else if (a == "--allow-synthesized") G.allow_synth = true;
        else return usage_error("unknown argument " + a);
    }

    HRESULT ci = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (FAILED(ci)) { wlog("CoInitializeEx failed %s", hrs(ci).c_str()); return 4; }
    HRESULT ms = MFStartup(MF_VERSION);
    if (FAILED(ms)) wlog("MFStartup failed %s", hrs(ms).c_str());

    const std::string& sc = G.subcommand;
    if (sc != "list" && sc != "activity") {
        if (G.api != "mf" && G.api != "ds") return usage_error("--api mf|ds required");
        if (G.device.empty()) return usage_error("--device required");
    }
    if (set_flags == "auto") co.set_flags = 1; else if (set_flags == "manual") co.set_flags = 2; else return usage_error("--set-flags auto|manual");
    if (!co.sets.empty()) { std::vector<SetReq> tmp; std::string err; if (!parse_sets(co.sets, co.set_flags, tmp, err)) return usage_error(err); }

    DWORD wd = G.watchdog_ms;
    int rc = 0;
    if (sc == "list") {
        if (!wd) wd = 60000;
        std::thread(watchdog_thread, wd).detach();
        rc = cmd_list();
    } else if (sc == "activity") {
        if (!wd) wd = G.wait_ms + G.timeout_ms * 2 + 20000;
        std::thread(watchdog_thread, wd).detach();
        rc = cmd_activity(G.device);
    } else if (sc == "formats") {
        if (!wd) wd = G.timeout_ms * 10 + 30000 + G.hold_ms;
        std::thread(watchdog_thread, wd).detach();
        rc = G.api == "mf" ? formats_mf() : formats_ds();
    } else if (sc == "controls") {
        if (!wd) wd = G.timeout_ms * 12 + 60000;
        std::thread(watchdog_thread, wd).detach();
        rc = controls_cmd(co);
    } else if (sc == "capture") {
        if (G.api != "mf") return usage_error("capture supports --api mf only (DirectShow capture is the PyAV helper)");
        if (!cap.mode.w || !cap.mode.h || cap.mode.fps <= 0) return usage_error("--width --height --fps required");
        if (have_frames == have_seconds) return usage_error("give exactly one of --frames / --seconds");
        if (!have_timeout) return usage_error("--timeout-ms required");
        if (cap.out_dir.empty()) return usage_error("--out-dir required");
        GUID gg{}; if (!subtype_guid(cap.mode.subtype, &gg)) return usage_error("bad --subtype");
        if (save == "none") cap.save_mode = 0;
        else if (save == "all") cap.save_mode = 1;
        else if (save.rfind("every:", 0) == 0) { cap.save_mode = 2; cap.save_every = (uint64_t)atoll(save.c_str() + 6); if (!cap.save_every) return usage_error("bad --save every:K"); }
        else return usage_error("--save none|all|every:K");
        std::string err;
        if (!schedule.empty() && !parse_schedule(schedule, cap.schedule, err)) return usage_error(err);
        if (!ctl_before.empty() && !parse_sets(ctl_before, 2, cap.controls_before, err)) return usage_error(err);
        double dur_ms = have_frames ? (double)cap.frames / cap.mode.fps * 1000.0 * 3 : cap.seconds * 1000.0;
        if (!wd) wd = (DWORD)(dur_ms + G.timeout_ms * (12.0 + cap.schedule.size() + cap.controls_before.size()) + 30000);
        std::thread(watchdog_thread, wd).detach();
        rc = capture_cmd(cap);
    } else if (sc == "cycle") {
        if (G.api != "mf") return usage_error("cycle supports --api mf only");
        if (!cyc.mode.w || !cyc.mode.h || cyc.mode.fps <= 0) return usage_error("--width --height --fps required");
        if (!have_timeout) return usage_error("--timeout-ms required");
        if (cyc.out_dir.empty()) return usage_error("--out DIR required");
        if (cyc.cycles <= 0 || !have_frames || cyc.frames == 0) return usage_error("--cycles K and --frames N required");
        G.out_file.clear();  // for cycle, --out is the output directory; the JSON goes to stdout and DIR/summary.json
        if (alt_w || alt_h || alt_fps > 0) {
            if (!alt_w || !alt_h || alt_fps <= 0) return usage_error("--alt-width --alt-height --alt-fps go together");
            cyc.has_alt = true; cyc.alt = cyc.mode; cyc.alt.w = alt_w; cyc.alt.h = alt_h; cyc.alt.fps = alt_fps;
        }
        GUID gg{}; if (!subtype_guid(cyc.mode.subtype, &gg)) return usage_error("bad --subtype");
        double per = (double)cyc.frames / std::min(cyc.mode.fps, cyc.has_alt ? cyc.alt.fps : cyc.mode.fps) * 1000.0 * 2 + G.timeout_ms * 10.0 + cyc.gap_ms;
        if (!wd) wd = (DWORD)std::min(per * cyc.cycles + 30000, 4.0e9);
        std::thread(watchdog_thread, wd).detach();
        rc = cycle_cmd(cyc);
    } else {
        return usage_error("unknown subcommand " + sc);
    }
    fflush(stdout);
    // Abandoned helper threads may still hold camera objects; skip MFShutdown/CoUninitialize, which could block on them.
    if (g_abandoned_threads.load() > 0) TerminateProcess(GetCurrentProcess(), (UINT)rc);
    MFShutdown();
    CoUninitialize();
    return rc;
}
