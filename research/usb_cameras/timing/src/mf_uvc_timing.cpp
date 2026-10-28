// mf_uvc_timing.cpp -- Windows Media Foundation capture tool that logs every timestamp available per frame.
//
// Purpose (skellycam research, goal 2): for each frame delivered by usbvideo.sys through the MF Source Reader,
// record host QPC on arrival, MF sample time, every MFSampleExtension_* attribute, and -- when the UVC metadata
// pin is enabled (registry MetadataBufferSizeInKB0, see timing/scripts/enable_uvc_metadata.ps1) -- the UVC payload
// header PTS / SCR (STC + SOF counter) for the first and last payload of the frame (KSSTREAM_UVC_METADATA).
//
// Build:  timing\build_mf.bat   (MSVC 2022, x64)  -> timing\build\mf_uvc_timing.exe
// Usage:
//   mf_uvc_timing.exe --list
//   mf_uvc_timing.exe --out <dir> --seconds 20 [--save-mjpeg]
//        --cam "<symlink substring>[,W,H,FPS[,exposure_log2[,wb_kelvin]]]"  (repeatable, one thread per camera)
//   e.g. --cam "vid_046d&pid_085c,1280,720,30,-7,4500"   exposure_log2: DirectShow units (2^v seconds); "auto" = leave
// Output per camera: <dir>/<key>.frames.jsonl (README per-frame schema + extra fields), <dir>/<key>.mjpeg (optional,
// raw concatenated MJPEG samples exactly as delivered), and <dir>/<key>.session.json (media type, controls, attr names).
// All host times are QPC converted to ns (QueryPerformanceCounter * 1e9 / QueryPerformanceFrequency).
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfreadwrite.h>
#include <mferror.h>
#include <mfcaptureengine.h>
#include <ks.h>
#include <ksmedia.h>
#include <strmif.h>
#include <atomic>
#include <cstdio>
#include <cstdint>
#include <string>
#include <vector>
#include <thread>
#include <algorithm>
#include <map>

#pragma comment(lib, "mfplat.lib")
#pragma comment(lib, "mf.lib")
#pragma comment(lib, "mfreadwrite.lib")
#pragma comment(lib, "mfuuid.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "strmiids.lib")

template <class T> struct Com {
    T* p = nullptr;
    ~Com() { if (p) p->Release(); }
    T** operator&() { return &p; }
    T* operator->() const { return p; }
    operator T*() const { return p; }
};

static int64_t g_qpf = 0;
static inline int64_t qpc_ns() {
    LARGE_INTEGER t; QueryPerformanceCounter(&t);
    return (int64_t)((long double)t.QuadPart * 1e9L / (long double)g_qpf);
}
static inline int64_t qpc_ticks() { LARGE_INTEGER t; QueryPerformanceCounter(&t); return t.QuadPart; }

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
static std::string jesc(const std::string& s) {
    std::string o; for (char c : s) { if (c == '"' || c == '\\') { o += '\\'; o += c; } else if ((unsigned char)c < 0x20) { char b[8]; sprintf_s(b, "\\u%04x", c); o += b; } else o += c; } return o;
}
static std::string guid_str(const GUID& g) {
    char b[64]; sprintf_s(b, "%08lX-%04X-%04X-%02X%02X-%02X%02X%02X%02X%02X%02X", g.Data1, g.Data2, g.Data3, g.Data4[0], g.Data4[1], g.Data4[2], g.Data4[3], g.Data4[4], g.Data4[5], g.Data4[6], g.Data4[7]);
    return b;
}
static std::string fourcc(const GUID& g) { char b[5] = {0}; memcpy(b, &g.Data1, 4); for (int i = 0; i < 4; ++i) if (b[i] < 32 || b[i] > 126) b[i] = '?'; return b; }

// GUIDs we know by name (values from Windows SDK 10.0.22621 mfapi.h / mfidl.h / mfcaptureengine.h).
static const GUID kDeviceTimestamp = {0x8f3e35e7, 0x2dcd, 0x4887, {0x86, 0x22, 0x2a, 0x58, 0xba, 0xa6, 0x52, 0xb0}};
static const GUID kDeviceRefSysTime = {0x6523775a, 0xba2d, 0x405f, {0xb2, 0xc5, 0x01, 0xff, 0x88, 0xe2, 0xe8, 0xf6}};
static const GUID kUndocD06F = {0xD06F8A46, 0x60A0, 0x4C20, {0xBC, 0x33, 0xAE, 0x96, 0xBF, 0x4F, 0xB0, 0x70}}; // undocumented, QPC-like value seen on every sample
static const GUID kSampleTimestampExt = {0x1e436999, 0x69be, 0x4c7a, {0x93, 0x69, 0x70, 0x06, 0x8c, 0x02, 0x60, 0xcb}};
static std::map<std::string, std::string> g_names = {
    {guid_str(kDeviceTimestamp), "MFSampleExtension_DeviceTimestamp"},
    {guid_str(kDeviceRefSysTime), "MFSampleExtension_DeviceReferenceSystemTime"},
    {guid_str(kSampleTimestampExt), "MFSampleExtension_Timestamp"},
    {guid_str(MFSampleExtension_CaptureMetadata), "MFSampleExtension_CaptureMetadata"},
    {guid_str(MF_CAPTURE_METADATA_FRAME_RAWSTREAM), "MF_CAPTURE_METADATA_FRAME_RAWSTREAM"},
    {guid_str(MFSampleExtension_CleanPoint), "MFSampleExtension_CleanPoint"},
    {guid_str(MFSampleExtension_Discontinuity), "MFSampleExtension_Discontinuity"},
    {guid_str(MFSampleExtension_Interlaced), "MFSampleExtension_Interlaced"},
    {guid_str(MF_CAPTURE_METADATA_EXPOSURE_TIME), "MF_CAPTURE_METADATA_EXPOSURE_TIME"},
    {guid_str(MF_CAPTURE_METADATA_SENSORFRAMERATE), "MF_CAPTURE_METADATA_SENSORFRAMERATE"},
    {guid_str(MF_CAPTURE_METADATA_FRAME_ILLUMINATION), "MF_CAPTURE_METADATA_FRAME_ILLUMINATION"},
    {guid_str(MF_CAPTURE_METADATA_ISO_SPEED), "MF_CAPTURE_METADATA_ISO_SPEED"},
    {guid_str(MF_CAPTURE_METADATA_WHITEBALANCE), "MF_CAPTURE_METADATA_WHITEBALANCE"},
    {guid_str(MF_CAPTURE_METADATA_FOCUSSTATE), "MF_CAPTURE_METADATA_FOCUSSTATE"},
    {guid_str(MF_CAPTURE_METADATA_LENS_POSITION), "MF_CAPTURE_METADATA_LENS_POSITION"},
    {guid_str(MF_CAPTURE_METADATA_EXPOSURE_COMPENSATION), "MF_CAPTURE_METADATA_EXPOSURE_COMPENSATION"},
    {guid_str(MFSampleExtension_FrameCorruption), "MFSampleExtension_FrameCorruption"},
};
static std::string gname(const GUID& g) { auto s = guid_str(g); auto it = g_names.find(s); return it == g_names.end() ? s : it->second; }

// Serialize one PROPVARIANT attribute value as JSON (blobs/unknowns summarized).
static std::string pv_json(const PROPVARIANT& v) {
    char b[128];
    switch (v.vt) {
    case VT_UI4: sprintf_s(b, "%lu", v.ulVal); return b;
    case VT_UI8: sprintf_s(b, "%llu", (unsigned long long)v.uhVal.QuadPart); return b;
    case VT_I8: sprintf_s(b, "%lld", (long long)v.hVal.QuadPart); return b;
    case VT_R8: sprintf_s(b, "%.9g", v.dblVal); return b;
    case VT_LPWSTR: return "\"" + jesc(w2u(v.pwszVal)) + "\"";
    case VT_CLSID: return "\"" + guid_str(*v.puuid) + "\"";
    case VT_VECTOR | VT_UI1: {
        std::string s = "\"blob:" + std::to_string(v.caub.cElems) + ":";
        for (ULONG i = 0; i < std::min<ULONG>(v.caub.cElems, 64); ++i) { sprintf_s(b, "%02x", v.caub.pElems[i]); s += b; }
        return s + "\"";
    }
    case VT_UNKNOWN: return "\"IUnknown\"";
    default: sprintf_s(b, "\"vt=%u\"", v.vt); return b;
    }
}

struct CamSpec {
    std::string match; UINT32 w = 1280, h = 720, fps = 30; std::string exposure = "auto"; std::string wb = "auto";
};
struct Shared { std::atomic<bool> stop{false}; std::string outdir; double seconds = 10; bool save_mjpeg = false; };

static std::vector<std::pair<std::string, std::string>> list_devices(std::vector<Com<IMFActivate>>* keep = nullptr, IMFActivate*** raw = nullptr, UINT32* rawn = nullptr) {
    std::vector<std::pair<std::string, std::string>> out;
    Com<IMFAttributes> a; MFCreateAttributes(&a, 1);
    a->SetGUID(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE, MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID);
    IMFActivate** devs = nullptr; UINT32 n = 0;
    if (FAILED(MFEnumDeviceSources(a, &devs, &n))) return out;
    for (UINT32 i = 0; i < n; ++i) {
        WCHAR* name = nullptr; WCHAR* link = nullptr; UINT32 len = 0;
        devs[i]->GetAllocatedString(MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME, &name, &len);
        devs[i]->GetAllocatedString(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK, &link, &len);
        out.push_back({w2u(name), w2u(link)});
        CoTaskMemFree(name); CoTaskMemFree(link);
    }
    if (raw) { *raw = devs; *rawn = n; } else { for (UINT32 i = 0; i < n; ++i) devs[i]->Release(); CoTaskMemFree(devs); }
    return out;
}

static std::string key_from_link(const std::string& link) {
    // e.g. \\?\usb#vid_046d&pid_085c&mi_00#8&268da596&0&0000#{...}\global -> vid_046d_pid_085c_8_268da596_0_0000
    std::string l = lower(link); size_t a = l.find("vid_"); if (a == std::string::npos) a = 0;
    size_t e = l.find("#{"); std::string core = l.substr(a, e == std::string::npos ? std::string::npos : e - a);
    std::string k; for (char c : core) k += (isalnum((unsigned char)c) ? c : '_');
    return k;
}

static void parse_uvc_metadata(const BYTE* p, DWORD n, std::string& js, bool dump_hex) {
    // Walk KSCAMERA_METADATA_ITEMHEADER items. MetadataId_UsbVideoHeader(2) carries KSSTREAM_UVC_METADATA.
    char b[512]; DWORD off = 0; int items = 0;
    js += ",\"meta_len\":" + std::to_string(n);
    if (dump_hex) {
        js += ",\"meta_hex\":\"";
        for (DWORD i = 0; i < std::min<DWORD>(n, 96); ++i) { sprintf_s(b, "%02x", p[i]); js += b; }
        js += "\"";
    }
    js += ",\"meta_items\":[";
    while (off + sizeof(KSCAMERA_METADATA_ITEMHEADER) <= n) {
        auto* h = (const KSCAMERA_METADATA_ITEMHEADER*)(p + off);
        if (h->Size < sizeof(KSCAMERA_METADATA_ITEMHEADER) || off + h->Size > n) break;
        if (items++) js += ",";
        sprintf_s(b, "{\"id\":%lu,\"size\":%lu", h->MetadataId, h->Size); js += b;
        if (h->MetadataId == MetadataId_UsbVideoHeader && h->Size >= sizeof(KSCAMERA_METADATA_ITEMHEADER) + sizeof(KSSTREAM_UVC_METADATA)) {
            auto* m = (const KSSTREAM_UVC_METADATA*)(p + off + sizeof(KSCAMERA_METADATA_ITEMHEADER));
            const auto& s = m->StartOfFrameTimestamp; const auto& e = m->EndOfFrameTimestamp;
            sprintf_s(b, ",\"sof\":{\"pts\":%lu,\"scr_stc\":%lu,\"scr_token\":%u,\"scr_sof\":%u,\"r0\":%u,\"r1\":%lu}"
                         ",\"eof\":{\"pts\":%lu,\"scr_stc\":%lu,\"scr_token\":%u,\"scr_sof\":%u,\"r0\":%u,\"r1\":%lu}",
                      s.PresentationTimeStamp, s.SourceClockReference, s.SCRToken, (unsigned)(s.SCRToken & 0x7FF), s.Reserved0, s.Reserved1,
                      e.PresentationTimeStamp, e.SourceClockReference, e.SCRToken, (unsigned)(e.SCRToken & 0x7FF), e.Reserved0, e.Reserved1);
            js += b;
            // README schema fields (first payload of the frame = UVC "StartOfFrame" header)
            sprintf_s(b, ",\"_top\":{\"uvc_pts\":%lu,\"uvc_scr_stc\":%lu,\"uvc_scr_sof\":%u,\"uvc_eof_pts\":%lu,\"uvc_eof_scr_stc\":%lu,\"uvc_eof_scr_sof\":%u}",
                      s.PresentationTimeStamp, s.SourceClockReference, (unsigned)(s.SCRToken & 0x7FF),
                      e.PresentationTimeStamp, e.SourceClockReference, (unsigned)(e.SCRToken & 0x7FF));
            js += b;
        }
        js += "}";
        off += h->Size;
        // items are not necessarily aligned; usbvideo pads? keep walking as declared.
    }
    js += "]";
}

static bool set_ctrl_cam(IAMCameraControl* cc, long prop, const std::string& v, std::string& rec, const char* name) {
    long mn = 0, mx = 0, st = 0, df = 0, caps = 0; char b[256];
    HRESULT hr = cc ? cc->GetRange(prop, &mn, &mx, &st, &df, &caps) : E_NOINTERFACE;
    if (FAILED(hr)) { sprintf_s(b, "\"%s\":{\"supported\":false}", name); rec += b; return false; }
    if (v != "auto") cc->Set(prop, atol(v.c_str()), CameraControl_Flags_Manual);
    long cur = 0, fl = 0; cc->Get(prop, &cur, &fl);
    sprintf_s(b, "\"%s\":{\"requested\":\"%s\",\"min\":%ld,\"max\":%ld,\"step\":%ld,\"default\":%ld,\"value\":%ld,\"flags\":%ld,\"manual\":%s}",
              name, v.c_str(), mn, mx, st, df, cur, fl, (fl & CameraControl_Flags_Manual) ? "true" : "false");
    rec += b; return true;
}
static bool set_ctrl_amp(IAMVideoProcAmp* pa, long prop, const std::string& v, std::string& rec, const char* name) {
    long mn = 0, mx = 0, st = 0, df = 0, caps = 0; char b[256];
    HRESULT hr = pa ? pa->GetRange(prop, &mn, &mx, &st, &df, &caps) : E_NOINTERFACE;
    if (FAILED(hr)) { sprintf_s(b, "\"%s\":{\"supported\":false}", name); rec += b; return false; }
    if (v != "auto") pa->Set(prop, atol(v.c_str()), VideoProcAmp_Flags_Manual);
    long cur = 0, fl = 0; pa->Get(prop, &cur, &fl);
    sprintf_s(b, "\"%s\":{\"requested\":\"%s\",\"min\":%ld,\"max\":%ld,\"step\":%ld,\"default\":%ld,\"value\":%ld,\"flags\":%ld,\"manual\":%s}",
              name, v.c_str(), mn, mx, st, df, cur, fl, (fl & VideoProcAmp_Flags_Manual) ? "true" : "false");
    rec += b; return true;
}

static void run_camera(CamSpec spec, Shared* sh) {
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    IMFActivate** devs = nullptr; UINT32 n = 0;
    auto list = list_devices(nullptr, &devs, &n);
    int idx = -1;
    for (UINT32 i = 0; i < n; ++i) if (lower(list[i].second).find(lower(spec.match)) != std::string::npos) { idx = (int)i; break; }
    if (idx < 0) { fprintf(stderr, "[%s] no device matches\n", spec.match.c_str()); return; }
    std::string name = list[idx].first, link = list[idx].second, key = key_from_link(link);
    Com<IMFMediaSource> src;
    HRESULT hr = devs[idx]->ActivateObject(IID_PPV_ARGS(&src));
    for (UINT32 i = 0; i < n; ++i) devs[i]->Release(); CoTaskMemFree(devs);
    if (FAILED(hr)) { fprintf(stderr, "[%s] ActivateObject hr=0x%08lx\n", key.c_str(), hr); return; }

    // Controls (exposure / white balance) via the KS proxy interfaces the MF device source exposes.
    std::string controls = "{";
    { Com<IAMCameraControl> cc; src->QueryInterface(IID_PPV_ARGS(&cc));
      Com<IAMVideoProcAmp> pa; src->QueryInterface(IID_PPV_ARGS(&pa));
      set_ctrl_cam(cc, CameraControl_Exposure, spec.exposure, controls, "exposure_log2"); controls += ",";
      set_ctrl_amp(pa, VideoProcAmp_WhiteBalance, spec.wb, controls, "white_balance_k"); controls += ",";
      set_ctrl_amp(pa, VideoProcAmp_Gain, "auto", controls, "gain"); controls += ",";
      set_ctrl_cam(cc, CameraControl_Focus, "auto", controls, "focus"); controls += ",";
      set_ctrl_amp(pa, VideoProcAmp_BacklightCompensation, "auto", controls, "backlight_comp"); }
    controls += "}";

    Com<IMFAttributes> ra; MFCreateAttributes(&ra, 4);
    ra->SetUINT32(MF_READWRITE_DISABLE_CONVERTERS, TRUE);
    ra->SetUINT32(MF_SOURCE_READER_DISABLE_DXVA, TRUE);
    Com<IMFSourceReader> rd;
    hr = MFCreateSourceReaderFromMediaSource(src, ra, &rd);
    if (FAILED(hr)) { fprintf(stderr, "[%s] reader hr=0x%08lx\n", key.c_str(), hr); return; }

    // Pick the native MJPG type matching WxH@fps (fallback: any MJPG of that size).
    Com<IMFMediaType> chosen; std::string types_json = "[";
    for (DWORD i = 0;; ++i) {
        Com<IMFMediaType> t; if (FAILED(rd->GetNativeMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM, i, &t))) break;
        GUID sub{}; t->GetGUID(MF_MT_SUBTYPE, &sub); UINT32 w = 0, h = 0, fn = 0, fd = 1;
        MFGetAttributeSize(t, MF_MT_FRAME_SIZE, &w, &h); MFGetAttributeRatio(t, MF_MT_FRAME_RATE, &fn, &fd);
        char b[128]; sprintf_s(b, "%s{\"i\":%lu,\"sub\":\"%s\",\"w\":%u,\"h\":%u,\"fps\":\"%u/%u\"}", i ? "," : "", i, fourcc(sub).c_str(), w, h, fn, fd); types_json += b;
        if (!chosen.p && sub == MFVideoFormat_MJPG && w == spec.w && h == spec.h && fd && (fn + fd / 2) / fd == spec.fps) { chosen.p = t.p; chosen.p->AddRef(); }
    }
    types_json += "]";
    if (!chosen.p) { fprintf(stderr, "[%s] no MJPG %ux%u@%u\n", key.c_str(), spec.w, spec.h, spec.fps); return; }
    hr = rd->SetCurrentMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM, nullptr, chosen);
    if (FAILED(hr)) { fprintf(stderr, "[%s] SetCurrentMediaType hr=0x%08lx\n", key.c_str(), hr); return; }

    std::string base = sh->outdir + "\\" + key;
    FILE* fl = nullptr; fopen_s(&fl, (base + ".frames.jsonl").c_str(), "wb");
    FILE* fm = nullptr; if (sh->save_mjpeg) fopen_s(&fm, (base + ".mjpeg").c_str(), "wb");
    std::map<std::string, int> attr_seen; uint64_t mjpeg_off = 0;
    int64_t t_start = qpc_ns(); int64_t seq = 0, errors = 0; int64_t first_arrival = 0;
    fprintf(stderr, "[%s] streaming %s %ux%u@%u\n", key.c_str(), name.c_str(), spec.w, spec.h, spec.fps);
    while (!sh->stop) {
        DWORD stream = 0, flags = 0; LONGLONG ts = 0; Com<IMFSample> s;
        int64_t t_call = qpc_ns();
        hr = rd->ReadSample(MF_SOURCE_READER_FIRST_VIDEO_STREAM, 0, &stream, &flags, &ts, &s);
        int64_t t_arr = qpc_ns();
        if (FAILED(hr)) { if (errors < 3) fprintf(stderr, "[%s] ReadSample hr=0x%08lx\n", key.c_str(), hr); if (++errors > 20) break; continue; }
        if (!s.p) { if (flags & MF_SOURCE_READERF_ENDOFSTREAM) break; continue; }
        if (!first_arrival) first_arrival = t_arr;
        std::string js; char b[512];
        sprintf_s(b, "{\"camera_key\":\"%s\",\"backend\":\"msmf-sourcereader-cpp\",\"seq\":%lld,\"host_arrival_ns\":%lld,\"readsample_call_ns\":%lld,\"mf_sample_time_100ns\":%lld,\"reader_flags\":%lu",
                  key.c_str(), seq, t_arr, t_call, ts, flags);
        js += b;
        LONGLONG dur = 0; if (SUCCEEDED(s->GetSampleDuration(&dur))) { js += ",\"mf_sample_duration_100ns\":" + std::to_string(dur); }
        // Payload
        Com<IMFMediaBuffer> buf; DWORD len = 0;
        if (SUCCEEDED(s->ConvertToContiguousBuffer(&buf))) {
            BYTE* p = nullptr; DWORD mx = 0;
            if (SUCCEEDED(buf->Lock(&p, &mx, &len))) {
                bool soi = len >= 2 && p[0] == 0xFF && p[1] == 0xD8;
                bool eoi = false; for (DWORD i = len; i >= 2 && i + 64 > len; --i) if (p[i - 2] == 0xFF && p[i - 1] == 0xD9) { eoi = true; break; }
                if (fm) { fwrite(p, 1, len, fm); }
                sprintf_s(b, ",\"payload_bytes\":%lu,\"jpeg_soi\":%s,\"jpeg_eoi\":%s,\"mjpeg_offset\":%llu", len, soi ? "true" : "false", eoi ? "true" : "false", (unsigned long long)mjpeg_off);
                js += b; mjpeg_off += len;
                buf->Unlock();
            }
        }
        // All sample attributes
        UINT32 cnt = 0; s->GetCount(&cnt);
        js += ",\"attrs\":{";
        bool firsta = true; std::string meta_js;
        for (UINT32 i = 0; i < cnt; ++i) {
            GUID g; PROPVARIANT v; PropVariantInit(&v);
            if (FAILED(s->GetItemByIndex(i, &g, &v))) continue;
            std::string nm = gname(g); attr_seen[nm]++;
            if (!firsta) js += ","; firsta = false;
            js += "\"" + nm + "\":" + pv_json(v);
            PropVariantClear(&v);
        }
        js += "}";
        // Typed extraction of known timestamps
        UINT64 u64 = 0;
        if (SUCCEEDED(s->GetUINT64(kDeviceTimestamp, &u64))) js += ",\"mf_device_timestamp\":" + std::to_string(u64);
        // README schema: MF capture sample times are QPC-based 100 ns units (verified in results/.../baseline_nometa_auto)
        js += ",\"os_timestamp_ns\":" + std::to_string((long long)ts * 100) + ",\"os_timestamp_source\":\"mf_sample_time (usbvideo KS presentation time, QPC 100ns)\"";
        { UINT64 v = 0; if (SUCCEEDED(s->GetUINT64(kUndocD06F, &v))) js += ",\"mf_undoc_d06f8a46_ns\":" + std::to_string((long long)v * 100); }
        if (SUCCEEDED(s->GetUINT64(kDeviceRefSysTime, &u64))) js += ",\"mf_device_ref_system_time\":" + std::to_string(u64);
        // Capture metadata
        Com<IMFAttributes> md;
        if (SUCCEEDED(s->GetUnknown(MFSampleExtension_CaptureMetadata, IID_PPV_ARGS(&md)))) {
            UINT32 mc = 0; md->GetCount(&mc);
            js += ",\"capture_metadata\":{";
            for (UINT32 i = 0; i < mc; ++i) {
                GUID g; PROPVARIANT v; PropVariantInit(&v);
                if (FAILED(md->GetItemByIndex(i, &g, &v))) continue;
                std::string nm = gname(g); attr_seen["capture_metadata." + nm]++;
                if (i) js += ","; js += "\"" + nm + "\":" + pv_json(v);
                PropVariantClear(&v);
            }
            js += "}";
            Com<IMFMediaBuffer> raw;
            if (SUCCEEDED(md->GetUnknown(MF_CAPTURE_METADATA_FRAME_RAWSTREAM, IID_PPV_ARGS(&raw)))) {
                BYTE* p = nullptr; DWORD mx = 0, ml = 0;
                if (SUCCEEDED(raw->Lock(&p, &mx, &ml))) { parse_uvc_metadata(p, ml, js, seq < 5); raw->Unlock(); }
            }
        }
        js += "}\n";
        fwrite(js.data(), 1, js.size(), fl);
        ++seq;
        if ((t_arr - t_start) / 1e9 > sh->seconds) break;
    }
    int64_t t_end = qpc_ns();
    fclose(fl); if (fm) fclose(fm);
    std::string ses = "{\"camera_key\":\"" + key + "\",\"friendly_name\":\"" + jesc(name) + "\",\"symbolic_link\":\"" + jesc(link) + "\",";
    char b[256]; sprintf_s(b, "\"requested\":{\"w\":%u,\"h\":%u,\"fps\":%u},\"frames\":%lld,\"errors\":%lld,\"wall_s\":%.3f,", spec.w, spec.h, spec.fps, seq, errors, (t_end - t_start) / 1e9);
    ses += b; ses += "\"controls\":" + controls + ",\"native_types\":" + types_json + ",\"attr_counts\":{";
    bool f = true; for (auto& kv : attr_seen) { if (!f) ses += ","; f = false; ses += "\"" + kv.first + "\":" + std::to_string(kv.second); }
    ses += "}}\n";
    FILE* fs = nullptr; fopen_s(&fs, (base + ".session.json").c_str(), "wb"); if (fs) { fwrite(ses.data(), 1, ses.size(), fs); fclose(fs); }
    fprintf(stderr, "[%s] done: %lld frames in %.2f s\n", key.c_str(), seq, (t_end - t_start) / 1e9);
    rd.p->Release(); rd.p = nullptr;
    src->Shutdown();
    CoUninitialize();
}

int main(int argc, char** argv) {
    LARGE_INTEGER f; QueryPerformanceFrequency(&f); g_qpf = f.QuadPart;
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    MFStartup(MF_VERSION);
    Shared sh; std::vector<CamSpec> cams; bool do_list = false;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "--list") do_list = true;
        else if (a == "--out" && i + 1 < argc) sh.outdir = argv[++i];
        else if (a == "--seconds" && i + 1 < argc) sh.seconds = atof(argv[++i]);
        else if (a == "--save-mjpeg") sh.save_mjpeg = true;
        else if (a == "--cam" && i + 1 < argc) {
            CamSpec c; std::string v = argv[++i]; std::vector<std::string> parts; size_t p0 = 0;
            while (true) { size_t p = v.find(',', p0); parts.push_back(v.substr(p0, p == std::string::npos ? std::string::npos : p - p0)); if (p == std::string::npos) break; p0 = p + 1; }
            c.match = parts[0];
            if (parts.size() > 3) { c.w = atoi(parts[1].c_str()); c.h = atoi(parts[2].c_str()); c.fps = atoi(parts[3].c_str()); }
            if (parts.size() > 4) c.exposure = parts[4];
            if (parts.size() > 5) c.wb = parts[5];
            cams.push_back(c);
        } else { fprintf(stderr, "unknown arg %s\n", a.c_str()); return 2; }
    }
    if (do_list || cams.empty()) {
        auto l = list_devices();
        printf("[\n");
        for (size_t i = 0; i < l.size(); ++i) printf("  {\"name\":\"%s\",\"symbolic_link\":\"%s\"}%s\n", jesc(l[i].first).c_str(), jesc(l[i].second).c_str(), i + 1 < l.size() ? "," : "");
        printf("]\n");
        return 0;
    }
    if (sh.outdir.empty()) { fprintf(stderr, "--out required\n"); return 2; }
    CreateDirectoryA(sh.outdir.c_str(), nullptr);
    printf("{\"qpc_frequency\":%lld,\"start_qpc_ns\":%lld}\n", g_qpf, qpc_ns());
    std::vector<std::thread> th;
    for (auto& c : cams) th.emplace_back(run_camera, c, &sh);
    for (auto& t : th) t.join();
    MFShutdown();
    return 0;
}
