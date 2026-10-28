// kiyo_ks_mf_probe.cpp -- minimal per-stage HRESULT / Win32-error probe for one camera, two independent paths:
//
//   (A) KS direct (no Media Foundation, no Frame Server, no metadata): CreateFile on the camera's KS filter
//       interface and IOCTL_KS_PROPERTY GET of UVC controls (exposure, focus, brightness, white balance).
//       A GET of a CT/PU control makes usbvideo.sys issue a UVC GET_CUR class request on EP0; it never touches the
//       streaming pin or its metadata buffer. If these fail, the failure is below/outside streaming.
//   (B) MF Source Reader with nothing extra requested: ActivateObject -> (optional) IAMCameraControl::GetRange ->
//       MFCreateSourceReaderFromMediaSource -> SetCurrentMediaType(native subtype/WxH@fps) -> ReadSample loop.
//       Records the HRESULT of every stage, every distinct ReadSample HRESULT, and how many delivered samples carry
//       MFSampleExtension_CaptureMetadata (i.e. whether the usbvideo metadata buffer is active for this device).
//       Note: an application cannot ask MF *not* to attach capture metadata; MetadataBufferSizeInKB0 is the only switch.
//
// Build: timing\build_kiyo_probe.bat  -> timing\build\kiyo_ks_mf_probe.exe
// Usage: kiyo_ks_mf_probe.exe --dev <symlink substring> [--sub MJPG] [--w 1280 --h 720 --fps 30] [--seconds 3]
//                             [--no-controls] [--ks-only] [--mf-only]
// Output: one JSON object on stdout.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <winioctl.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfreadwrite.h>
#include <mferror.h>
#include <ks.h>
#include <ksmedia.h>
#include <strmif.h>
#include <cstdio>
#include <cstdint>
#include <string>
#include <map>
#include <vector>
#pragma comment(lib, "mfplat.lib")
#pragma comment(lib, "mf.lib")
#pragma comment(lib, "mfreadwrite.lib")
#pragma comment(lib, "mfuuid.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "strmiids.lib")

template <class T> struct Com { T* p = nullptr; ~Com() { if (p) p->Release(); } T** operator&() { return &p; } T* operator->() const { return p; } operator T*() const { return p; } };
static std::string w2u(const wchar_t* w) { if (!w) return {}; int n = WideCharToMultiByte(CP_UTF8, 0, w, -1, nullptr, 0, nullptr, nullptr); std::string s(n > 0 ? n - 1 : 0, '\0'); if (n > 1) WideCharToMultiByte(CP_UTF8, 0, w, -1, s.data(), n, nullptr, nullptr); return s; }
static std::wstring u2w(const std::string& s) { int n = MultiByteToWideChar(CP_UTF8, 0, s.c_str(), -1, nullptr, 0); std::wstring w(n > 0 ? n - 1 : 0, L'\0'); if (n > 1) MultiByteToWideChar(CP_UTF8, 0, s.c_str(), -1, w.data(), n); return w; }
static std::string lower(std::string s) { for (auto& c : s) c = (char)tolower((unsigned char)c); return s; }
static std::string jesc(const std::string& s) { std::string o; for (char c : s) { if (c == '"' || c == '\\') { o += '\\'; o += c; } else if ((unsigned char)c < 0x20) { char b[8]; sprintf_s(b, "\\u%04x", c); o += b; } else o += c; } return o; }
static std::string hx(long v) { char b[16]; sprintf_s(b, "0x%08lX", (unsigned long)v); return b; }
static std::string fourcc(const GUID& g) { char b[5] = {0}; memcpy(b, &g.Data1, 4); for (int i = 0; i < 4; ++i) if (b[i] < 32 || b[i] > 126) b[i] = '?'; return b; }
static double now_s() { static LARGE_INTEGER f{}; if (!f.QuadPart) QueryPerformanceFrequency(&f); LARGE_INTEGER t; QueryPerformanceCounter(&t); return (double)t.QuadPart / f.QuadPart; }

// ---- (A) KS direct property GET with a timeout (a wedged device can hang EP0 requests) ----
static std::string ks_get(HANDLE h, const GUID& set, ULONG id, const char* name) {
    KSPROPERTY_VIDEOPROCAMP_S s{}; // same layout as KSPROPERTY_CAMERACONTROL_S: {KSPROPERTY, Value, Flags, Capabilities}
    s.Property.Set = set; s.Property.Id = id; s.Property.Flags = KSPROPERTY_TYPE_GET;
    OVERLAPPED ov{}; ov.hEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    DWORD ret = 0; double t0 = now_s();
    // output buffer: the full *_S struct (usbvideo rejects shorter buffers with ERROR_INSUFFICIENT_BUFFER for PU props)
    struct { KSPROPERTY_VIDEOPROCAMP_S v; BYTE pad[64]; } obuf{}; obuf.v = s;
    BOOL ok = DeviceIoControl(h, IOCTL_KS_PROPERTY, &s, sizeof(s), &obuf, sizeof(obuf.v), &ret, &ov);
    DWORD err = ok ? 0 : GetLastError(); bool timeout = false;
    if (!ok && err == ERROR_IO_PENDING) {
        DWORD w = WaitForSingleObject(ov.hEvent, 5000);
        if (w == WAIT_TIMEOUT) { timeout = true; CancelIoEx(h, &ov); WaitForSingleObject(ov.hEvent, 2000); err = WAIT_TIMEOUT; }
        else { ok = GetOverlappedResult(h, &ov, &ret, FALSE); err = ok ? 0 : GetLastError(); }
    }
    double ms = (now_s() - t0) * 1e3; CloseHandle(ov.hEvent);
    char b[320];
    sprintf_s(b, "\"%s\":{\"ok\":%s,\"win32_error\":%lu,\"hresult\":\"%s\",\"timeout\":%s,\"ms\":%.2f,\"bytes\":%lu,\"value\":%ld,\"flags\":%lu}",
              name, ok ? "true" : "false", err, hx(ok ? 0 : HRESULT_FROM_WIN32(err)).c_str(), timeout ? "true" : "false", ms, ret,
              ok ? obuf.v.Value : 0, ok ? obuf.v.Flags : 0);
    return b;
}
static std::string ks_probe(const std::string& link) {
    std::string out = "{\"path\":\"" + jesc(link) + "\",";
    HANDLE h = CreateFileW(u2w(link).c_str(), GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, nullptr);
    if (h == INVALID_HANDLE_VALUE) { DWORD e = GetLastError(); return out + "\"open_ok\":false,\"open_win32_error\":" + std::to_string(e) + "}"; }
    out += "\"open_ok\":true,";
    out += ks_get(h, PROPSETID_VIDCAP_CAMERACONTROL, KSPROPERTY_CAMERACONTROL_EXPOSURE, "ct_exposure") + ",";
    out += ks_get(h, PROPSETID_VIDCAP_CAMERACONTROL, KSPROPERTY_CAMERACONTROL_FOCUS, "ct_focus") + ",";
    out += ks_get(h, PROPSETID_VIDCAP_VIDEOPROCAMP, KSPROPERTY_VIDEOPROCAMP_BRIGHTNESS, "pu_brightness") + ",";
    out += ks_get(h, PROPSETID_VIDCAP_VIDEOPROCAMP, KSPROPERTY_VIDEOPROCAMP_WHITEBALANCE, "pu_white_balance");
    CloseHandle(h);
    return out + "}";
}

int main(int argc, char** argv) {
    std::string dev, sub = "MJPG"; UINT32 W = 1280, H = 720, FPS = 30; double seconds = 3; bool no_controls = false, ks_only = false, mf_only = false;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i]; auto nx = [&]() { return std::string(i + 1 < argc ? argv[++i] : ""); };
        if (a == "--dev") dev = nx(); else if (a == "--sub") sub = nx(); else if (a == "--w") W = atoi(nx().c_str());
        else if (a == "--h") H = atoi(nx().c_str()); else if (a == "--fps") FPS = atoi(nx().c_str()); else if (a == "--seconds") seconds = atof(nx().c_str());
        else if (a == "--no-controls") no_controls = true; else if (a == "--ks-only") ks_only = true; else if (a == "--mf-only") mf_only = true;
    }
    if (dev.empty()) { fprintf(stderr, "--dev required\n"); return 2; }
    CoInitializeEx(nullptr, COINIT_MULTITHREADED); MFStartup(MF_VERSION);
    std::string js = "{\"tool\":\"kiyo_ks_mf_probe\",\"dev\":\"" + jesc(dev) + "\",\"request\":{\"sub\":\"" + sub + "\",\"w\":" + std::to_string(W) + ",\"h\":" + std::to_string(H) + ",\"fps\":" + std::to_string(FPS) + ",\"seconds\":" + std::to_string(seconds) + ",\"no_controls\":" + (no_controls ? "true" : "false") + "}";
    SYSTEMTIME st; GetSystemTime(&st); char tb[64]; sprintf_s(tb, ",\"utc\":\"%04d-%02d-%02dT%02d:%02d:%02d.%03dZ\"", st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond, st.wMilliseconds); js += tb;

    Com<IMFAttributes> ea; MFCreateAttributes(&ea, 1); ea->SetGUID(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE, MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID);
    IMFActivate** devs = nullptr; UINT32 n = 0; HRESULT hr = MFEnumDeviceSources(ea, &devs, &n);
    int idx = -1; std::string link, name;
    for (UINT32 i = 0; i < n; ++i) {
        WCHAR* s = nullptr; UINT32 l = 0; devs[i]->GetAllocatedString(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK, &s, &l);
        std::string sl = w2u(s); CoTaskMemFree(s);
        if (idx < 0 && lower(sl).find(lower(dev)) != std::string::npos) { idx = (int)i; link = sl; WCHAR* fn = nullptr; devs[i]->GetAllocatedString(MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME, &fn, &l); name = w2u(fn); CoTaskMemFree(fn); }
    }
    js += ",\"enum_hr\":\"" + hx(hr) + "\",\"n_devices\":" + std::to_string(n) + ",\"name\":\"" + jesc(name) + "\",\"symbolic_link\":\"" + jesc(link) + "\"";
    if (idx < 0) { printf("%s,\"error\":\"no device matches\"}\n", js.c_str()); return 3; }

    if (!mf_only) {
        // the same device via the KSCATEGORY_CAPTURE interface too (DirectShow's path)
        std::string cap = link; size_t p = lower(cap).find("{e5323777-f976-4f5b-9b55-b94699c46e44}");
        if (p != std::string::npos) cap.replace(p, 38, "{65e8773d-8f56-11d0-a3b9-00a0c9223196}");
        js += ",\"ks_video_camera\":" + ks_probe(link) + ",\"ks_capture\":" + ks_probe(cap);
    }
    if (ks_only) { for (UINT32 i = 0; i < n; ++i) devs[i]->Release(); CoTaskMemFree(devs); printf("%s}\n", js.c_str()); return 0; }

    Com<IMFMediaSource> src; double t0 = now_s();
    hr = devs[idx]->ActivateObject(IID_PPV_ARGS(&src));
    for (UINT32 i = 0; i < n; ++i) devs[i]->Release(); CoTaskMemFree(devs);
    char b[512]; sprintf_s(b, ",\"mf\":{\"activate_hr\":\"%s\",\"activate_ms\":%.1f", hx(hr).c_str(), (now_s() - t0) * 1e3); js += b;
    if (FAILED(hr)) { printf("%s}}\n", js.c_str()); return 4; }
    if (!no_controls) {
        Com<IAMCameraControl> cc; HRESULT qh = src->QueryInterface(IID_PPV_ARGS(&cc));
        long mn = 0, mx = 0, stp = 0, df = 0, caps = 0, cur = 0, fl = 0;
        HRESULT gr = cc ? cc->GetRange(CameraControl_Exposure, &mn, &mx, &stp, &df, &caps) : E_NOINTERFACE;
        HRESULT gg = cc ? cc->Get(CameraControl_Exposure, &cur, &fl) : E_NOINTERFACE;
        Com<IAMVideoProcAmp> pa; HRESULT qp = src->QueryInterface(IID_PPV_ARGS(&pa));
        long bv = 0, bf = 0; HRESULT bg = pa ? pa->Get(VideoProcAmp_Brightness, &bv, &bf) : E_NOINTERFACE;
        sprintf_s(b, ",\"qi_camctl_hr\":\"%s\",\"exposure_getrange_hr\":\"%s\",\"exposure_range\":[%ld,%ld],\"exposure_get_hr\":\"%s\",\"exposure\":%ld,\"qi_procamp_hr\":\"%s\",\"brightness_get_hr\":\"%s\",\"brightness\":%ld",
                  hx(qh).c_str(), hx(gr).c_str(), mn, mx, hx(gg).c_str(), cur, hx(qp).c_str(), hx(bg).c_str(), bv);
        js += b;
    }
    Com<IMFAttributes> ra; MFCreateAttributes(&ra, 2); ra->SetUINT32(MF_READWRITE_DISABLE_CONVERTERS, TRUE);
    Com<IMFSourceReader> rd; hr = MFCreateSourceReaderFromMediaSource(src, ra, &rd);
    js += ",\"reader_hr\":\"" + hx(hr) + "\"";
    if (FAILED(hr)) { printf("%s}}\n", js.c_str()); return 5; }
    Com<IMFMediaType> chosen; int nt = 0, chosen_i = -1;
    for (DWORD i = 0;; ++i) {
        Com<IMFMediaType> t; if (FAILED(rd->GetNativeMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM, i, &t))) break; ++nt;
        GUID g{}; t->GetGUID(MF_MT_SUBTYPE, &g); UINT32 w = 0, h = 0, fn = 0, fd = 1;
        MFGetAttributeSize(t, MF_MT_FRAME_SIZE, &w, &h); MFGetAttributeRatio(t, MF_MT_FRAME_RATE, &fn, &fd);
        if (!chosen.p && fourcc(g) == sub && w == W && h == H && fd && (fn + fd / 2) / fd == FPS) { chosen.p = t.p; chosen.p->AddRef(); chosen_i = (int)i; }
    }
    js += ",\"n_native_types\":" + std::to_string(nt) + ",\"chosen_native_index\":" + std::to_string(chosen_i);
    if (!chosen.p) { printf("%s,\"error\":\"requested type not offered\"}}\n", js.c_str()); return 6; }
    hr = rd->SetCurrentMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM, nullptr, chosen);
    js += ",\"set_type_hr\":\"" + hx(hr) + "\"";
    if (FAILED(hr)) { printf("%s}}\n", js.c_str()); return 7; }
    std::map<long, int> errs; std::vector<std::string> first_errs; int samples = 0, with_meta = 0, nulls = 0, jpeg_soi = 0; double t_first = -1;
    double ts = now_s(); int consecutive = 0;
    while (now_s() - ts < seconds) {
        DWORD si = 0, flags = 0; LONGLONG t = 0; Com<IMFSample> s;
        double c0 = now_s(); HRESULT r = rd->ReadSample(MF_SOURCE_READER_FIRST_VIDEO_STREAM, 0, &si, &flags, &t, &s);
        if (FAILED(r)) {
            errs[r]++; if (first_errs.size() < 3) { sprintf_s(b, "{\"hr\":\"%s\",\"after_ms\":%.1f,\"call_ms\":%.1f}", hx(r).c_str(), (c0 - ts) * 1e3, (now_s() - c0) * 1e3); first_errs.push_back(b); }
            if (++consecutive > 20) break; continue;
        }
        consecutive = 0;
        if (!s.p) { ++nulls; if (flags & MF_SOURCE_READERF_ENDOFSTREAM) break; continue; }
        if (t_first < 0) t_first = now_s() - ts;
        ++samples; UINT32 bs = 0; if (SUCCEEDED(s->GetBlobSize(MFSampleExtension_CaptureMetadata, &bs)) ) ++with_meta;
        else { Com<IUnknown> u; if (SUCCEEDED(s->GetUnknown(MFSampleExtension_CaptureMetadata, IID_PPV_ARGS(&u)))) ++with_meta; }
        Com<IMFMediaBuffer> mb; if (SUCCEEDED(s->ConvertToContiguousBuffer(&mb))) { BYTE* p = nullptr; DWORD mx = 0, len = 0; if (SUCCEEDED(mb->Lock(&p, &mx, &len))) { if (len >= 2 && p[0] == 0xFF && p[1] == 0xD8) ++jpeg_soi; mb->Unlock(); } }
    }
    double wall = now_s() - ts;
    std::string ej = "{"; bool f = true; for (auto& kv : errs) { ej += (f ? "" : ",") + std::string("\"") + hx(kv.first) + "\":" + std::to_string(kv.second); f = false; } ej += "}";
    std::string fe = "["; for (size_t i = 0; i < first_errs.size(); ++i) fe += (i ? "," : "") + first_errs[i]; fe += "]";
    sprintf_s(b, ",\"samples\":%d,\"null_samples\":%d,\"samples_with_capture_metadata\":%d,\"samples_jpeg_soi\":%d,\"first_sample_s\":%.3f,\"wall_s\":%.3f,\"fps\":%.2f",
              samples, nulls, with_meta, jpeg_soi, t_first, wall, wall > 0 ? samples / wall : 0.0);
    js += b; js += ",\"readsample_errors\":" + ej + ",\"first_errors\":" + fe + "}}";
    printf("%s\n", js.c_str());
    rd.~Com(); rd.p = nullptr; src->Shutdown();
    MFShutdown(); CoUninitialize();
    return samples > 0 ? 0 : 1;
}
