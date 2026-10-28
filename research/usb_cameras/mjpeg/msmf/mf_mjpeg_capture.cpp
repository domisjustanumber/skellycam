// mf_mjpeg_capture.cpp -- Media Foundation IMFSourceReader native-MJPEG capture probe (Windows).
//
// Goal 1 (native MJPEG extraction) harness for the skellycam USB camera investigation.
// Opens one or more UVC cameras through Media Foundation, selects the camera's NATIVE MJPG media
// type with converters disabled (MF_READWRITE_DISABLE_CONVERTERS=TRUE), verifies the reader's
// current output subtype is still MJPG (i.e. no MJPEG decoder was inserted), and records every
// sample's bytes + all timestamps/attributes MF attaches. Optionally (--decode-to NV12|RGB32)
// it lets MF insert its decoder instead, as a CPU-cost comparison of the decode path.
//
// Build (from a "x64 Native Tools" prompt, or via build.bat next to this file):
//   cl /nologo /EHsc /O2 /std:c++17 /W3 mf_mjpeg_capture.cpp /Fe:..\build\mf_mjpeg_capture.exe
//      mfplat.lib mf.lib mfreadwrite.lib mfuuid.lib ole32.lib strmiids.lib
//
// Usage:
//   mf_mjpeg_capture.exe --list [--dev SUBSTR ...]    (JSON of devices + native media types on stdout; activates every
//                                                      source, or only the --dev matches when given)
//   mf_mjpeg_capture.exe --list-enum | --list-dshow   (MF / DirectShow enumeration order only; opens no camera)
//   mf_mjpeg_capture.exe --dshow-formats --dev SUBSTR (IAMStreamConfig caps of the DirectShow capture pin)
//   mf_mjpeg_capture.exe --dev vid_046d&pid_085c [--dev ...] --width 1280 --height 720 --fps 30
//        [--seconds 10] [--warmup 2] [--out DIR] [--exposure -7] [--wb 4500] [--aux-pid PID]
//        [--attr-dump 5] [--decode-to NV12|RGB32] [--controls-only]
// Output in DIR: meta.json, frames.jsonl (one line per sample), frames_<i>.bin (records:
// u32 cam, u64 seq, u32 len, bytes) which tools/summarize via mjpeg_common.py.
// Exit code 0 on success; non-zero with an "error" message on stderr otherwise.

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfreadwrite.h>
#include <mferror.h>
#include <strmif.h>
#include <ks.h>
#include <ksmedia.h>
#include <ksproxy.h>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <string>
#include <thread>
#include <vector>
#include <algorithm>
#include <sstream>

#pragma comment(lib, "mfplat.lib")
#pragma comment(lib, "mf.lib")
#pragma comment(lib, "mfreadwrite.lib")
#pragma comment(lib, "mfuuid.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "strmiids.lib")
#pragma comment(lib, "advapi32.lib")
#include <intrin.h>
#include <dshow.h>
#include <dvdmedia.h>
#pragma comment(lib, "oleaut32.lib")

// GUIDs that may not be in every SDK's import libs
static const GUID kMFSampleExtension_DeviceTimestamp = {0x8f3e35e7, 0x2dcd, 0x4887, {0x86, 0x22, 0x2a, 0x58, 0xba, 0xa6, 0x52, 0xb0}};
static const GUID kMFSampleExtension_DeviceReferenceSystemTime = {0x6523775a, 0xba2d, 0x405f, {0xb2, 0xc5, 0x01, 0xff, 0x88, 0xe2, 0xe8, 0xf6}};

template <class T> static void SafeRelease(T** p) { if (*p) { (*p)->Release(); *p = nullptr; } }

static std::string W2U(const wchar_t* w) {
    if (!w) return "";
    int n = WideCharToMultiByte(CP_UTF8, 0, w, -1, nullptr, 0, nullptr, nullptr);
    std::string s(n > 0 ? n - 1 : 0, '\0');
    if (n > 1) WideCharToMultiByte(CP_UTF8, 0, w, -1, &s[0], n, nullptr, nullptr);
    return s;
}
static std::string JEsc(const std::string& s) {
    std::string o;
    for (char c : s) {
        switch (c) {
            case '"': o += "\\\""; break;
            case '\\': o += "\\\\"; break;
            case '\n': o += "\\n"; break;
            case '\r': o += "\\r"; break;
            case '\t': o += "\\t"; break;
            default:
                if ((unsigned char)c < 0x20) { char b[8]; sprintf_s(b, "\\u%04x", c); o += b; }
                else o += c;
        }
    }
    return o;
}
static std::string GuidStr(const GUID& g) {
    wchar_t buf[64]; StringFromGUID2(g, buf, 64); return W2U(buf);
}
static std::string FourCC(const GUID& sub) {
    // MF video subtypes are FOURCC-based: Data1 holds the fourcc (or a D3DFMT number)
    DWORD d = sub.Data1; char c[5] = {(char)(d & 0xff), (char)((d >> 8) & 0xff), (char)((d >> 16) & 0xff), (char)((d >> 24) & 0xff), 0};
    bool printable = true; for (int i = 0; i < 4; i++) if (c[i] < 32 || c[i] > 126) printable = false;
    if (printable) return std::string(c);
    char b[16]; sprintf_s(b, "D3DFMT_%lu", d); return b;
}

static int64_t QpcNow() { LARGE_INTEGER t; QueryPerformanceCounter(&t); return t.QuadPart; }
static int64_t QpcFreq() { static int64_t f = 0; if (!f) { LARGE_INTEGER x; QueryPerformanceFrequency(&x); f = x.QuadPart; } return f; }
static int64_t QpcToNs(int64_t q) { int64_t f = QpcFreq(); return (q / f) * 1000000000LL + ((q % f) * 1000000000LL) / f; }

static double FileTimeToSec(const FILETIME& ft) { ULARGE_INTEGER u; u.LowPart = ft.dwLowDateTime; u.HighPart = ft.dwHighDateTime; return u.QuadPart / 1e7; }
static bool ProcCpu(HANDLE h, double* user, double* kern) {
    FILETIME c, e, k, u; if (!GetProcessTimes(h, &c, &e, &k, &u)) return false;
    *user = FileTimeToSec(u); *kern = FileTimeToSec(k); return true;
}
static ULONG64 ProcCycles(HANDLE h) { ULONG64 c = 0; if (!h || !QueryProcessCycleTime(h, &c)) return 0; return c; }
// PID of the svchost that hosts the Windows Camera Frame Server service (0 if not running)
static DWORD FrameServerPid() {
    SC_HANDLE scm = OpenSCManagerW(nullptr, nullptr, SC_MANAGER_CONNECT); if (!scm) return 0;
    SC_HANDLE svc = OpenServiceW(scm, L"FrameServer", SERVICE_QUERY_STATUS); DWORD pid = 0;
    if (svc) { SERVICE_STATUS_PROCESS ssp{}; DWORD need = 0; if (QueryServiceStatusEx(svc, SC_STATUS_PROCESS_INFO, (LPBYTE)&ssp, sizeof(ssp), &need)) pid = ssp.dwProcessId; CloseServiceHandle(svc); }
    CloseServiceHandle(scm); return pid;
}

// Known attribute names for readable dumps
struct NamedGuid { GUID g; const char* name; };
static const NamedGuid kKnown[] = {
    {MFSampleExtension_CleanPoint, "MFSampleExtension_CleanPoint"},
    {MFSampleExtension_Discontinuity, "MFSampleExtension_Discontinuity"},
    {MFSampleExtension_Token, "MFSampleExtension_Token"},
    {MFSampleExtension_DecodeTimestamp, "MFSampleExtension_DecodeTimestamp"},
    {MFSampleExtension_FrameCorruption, "MFSampleExtension_FrameCorruption"},
    {MFSampleExtension_Timestamp, "MFSampleExtension_Timestamp"},
    {MFSampleExtension_RepeatFrame, "MFSampleExtension_RepeatFrame"},
    {MFSampleExtension_Interlaced, "MFSampleExtension_Interlaced"},
    {MFSampleExtension_CaptureMetadata, "MFSampleExtension_CaptureMetadata"},
    {MFSampleExtension_MDLCacheCookie, "MFSampleExtension_MDLCacheCookie"},
    {kMFSampleExtension_DeviceTimestamp, "MFSampleExtension_DeviceTimestamp"},
    {kMFSampleExtension_DeviceReferenceSystemTime, "MFSampleExtension_DeviceReferenceSystemTime"},
    {MF_CAPTURE_METADATA_FRAME_RAWSTREAM, "MF_CAPTURE_METADATA_FRAME_RAWSTREAM"},
    {MF_CAPTURE_METADATA_EXPOSURE_TIME, "MF_CAPTURE_METADATA_EXPOSURE_TIME"},
    {MF_CAPTURE_METADATA_WHITEBALANCE, "MF_CAPTURE_METADATA_WHITEBALANCE"},
    {MF_CAPTURE_METADATA_SENSORFRAMERATE, "MF_CAPTURE_METADATA_SENSORFRAMERATE"},
    {MF_CAPTURE_METADATA_UVC_PAYLOADHEADER, "MF_CAPTURE_METADATA_UVC_PAYLOADHEADER"},
    {MF_CAPTURE_METADATA_FIRST_SCANLINE_START_TIME_QPC, "MF_CAPTURE_METADATA_FIRST_SCANLINE_START_TIME_QPC"},
    {MF_CAPTURE_METADATA_LAST_SCANLINE_END_TIME_QPC, "MF_CAPTURE_METADATA_LAST_SCANLINE_END_TIME_QPC"},
    {MF_CAPTURE_METADATA_SCANLINE_TIME_QPC_ACCURACY, "MF_CAPTURE_METADATA_SCANLINE_TIME_QPC_ACCURACY"},
    {MF_CAPTURE_METADATA_ISO_SPEED, "MF_CAPTURE_METADATA_ISO_SPEED"},
    {MF_CAPTURE_METADATA_FOCUSSTATE, "MF_CAPTURE_METADATA_FOCUSSTATE"},
    {MF_CAPTURE_METADATA_LENS_POSITION, "MF_CAPTURE_METADATA_LENS_POSITION"},
    {MF_CAPTURE_METADATA_EXPOSURE_COMPENSATION, "MF_CAPTURE_METADATA_EXPOSURE_COMPENSATION"},
    {MF_CAPTURE_METADATA_DIGITALWINDOW, "MF_CAPTURE_METADATA_DIGITALWINDOW"},
    {MF_CAPTURE_METADATA_FRAME_ILLUMINATION, "MF_CAPTURE_METADATA_FRAME_ILLUMINATION"},
};
static std::string GuidName(const GUID& g) {
    for (auto& k : kKnown) if (IsEqualGUID(k.g, g)) return k.name;
    return GuidStr(g);
}

// Serialize an IMFAttributes store to JSON (values truncated for blobs)
static std::string AttrsJson(IMFAttributes* a, int depth = 0) {
    std::ostringstream o; o << "{";
    UINT32 n = 0; a->GetCount(&n);
    for (UINT32 i = 0; i < n; i++) {
        GUID key; PROPVARIANT v; PropVariantInit(&v);
        if (FAILED(a->GetItemByIndex(i, &key, &v))) continue;
        if (i) o << ",";
        o << "\"" << JEsc(GuidName(key)) << "\":";
        switch (v.vt) {
            case VT_UI4: o << v.ulVal; break;
            case VT_UI8: o << v.uhVal.QuadPart; break;
            case VT_I8: o << v.hVal.QuadPart; break;
            case VT_R8: o << v.dblVal; break;
            case VT_CLSID: o << "\"" << GuidStr(*v.puuid) << "\""; break;
            case VT_LPWSTR: o << "\"" << JEsc(W2U(v.pwszVal)) << "\""; break;
            case VT_VECTOR | VT_UI1: {
                o << "{\"blob_bytes\":" << v.caub.cElems << ",\"hex_head\":\"";
                for (ULONG b = 0; b < std::min<ULONG>(v.caub.cElems, 64); b++) { char h[3]; sprintf_s(h, "%02x", v.caub.pElems[b]); o << h; }
                o << "\"}"; break;
            }
            case VT_UNKNOWN: {
                IMFAttributes* sub = nullptr;
                if (depth < 2 && v.punkVal && SUCCEEDED(v.punkVal->QueryInterface(IID_PPV_ARGS(&sub)))) { o << AttrsJson(sub, depth + 1); sub->Release(); }
                else o << "\"<IUnknown>\"";
                break;
            }
            default: o << "\"<vt " << v.vt << ">\"";
        }
        PropVariantClear(&v);
    }
    o << "}"; return o.str();
}

struct Device {
    std::string name, symlink;
    IMFActivate* act = nullptr;
};

static HRESULT EnumDevices(std::vector<Device>& out) {
    IMFAttributes* attr = nullptr; IMFActivate** acts = nullptr; UINT32 count = 0;
    HRESULT hr = MFCreateAttributes(&attr, 1);
    if (SUCCEEDED(hr)) hr = attr->SetGUID(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE, MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID);
    if (SUCCEEDED(hr)) hr = MFEnumDeviceSources(attr, &acts, &count);
    for (UINT32 i = 0; SUCCEEDED(hr) && i < count; i++) {
        Device d; d.act = acts[i];
        WCHAR* s = nullptr; UINT32 len = 0;
        if (SUCCEEDED(acts[i]->GetAllocatedString(MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME, &s, &len))) { d.name = W2U(s); CoTaskMemFree(s); }
        if (SUCCEEDED(acts[i]->GetAllocatedString(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK, &s, &len))) { d.symlink = W2U(s); CoTaskMemFree(s); }
        out.push_back(d);
    }
    CoTaskMemFree(acts); SafeRelease(&attr);
    return hr;
}

static std::string Lower(std::string s) { std::transform(s.begin(), s.end(), s.begin(), ::tolower); return s; }

struct TypeInfo { DWORD index; std::string sub; UINT32 w, h, fn, fd; GUID subguid; };

static std::vector<TypeInfo> NativeTypes(IMFSourceReader* r) {
    std::vector<TypeInfo> v;
    for (DWORD i = 0;; i++) {
        IMFMediaType* t = nullptr;
        if (FAILED(r->GetNativeMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM, i, &t))) break;
        TypeInfo ti{}; ti.index = i;
        t->GetGUID(MF_MT_SUBTYPE, &ti.subguid); ti.sub = FourCC(ti.subguid);
        MFGetAttributeSize(t, MF_MT_FRAME_SIZE, &ti.w, &ti.h);
        MFGetAttributeRatio(t, MF_MT_FRAME_RATE, &ti.fn, &ti.fd);
        v.push_back(ti); t->Release();
    }
    return v;
}

static HRESULT CreateReader(IMFMediaSource* src, bool disableConverters, bool videoProcessing, IMFSourceReader** reader) {
    IMFAttributes* a = nullptr;
    HRESULT hr = MFCreateAttributes(&a, 3);
    if (SUCCEEDED(hr)) hr = a->SetUINT32(MF_READWRITE_DISABLE_CONVERTERS, disableConverters ? TRUE : FALSE);
    if (SUCCEEDED(hr) && videoProcessing) hr = a->SetUINT32(MF_SOURCE_READER_ENABLE_VIDEO_PROCESSING, TRUE);
    if (SUCCEEDED(hr)) hr = MFCreateSourceReaderFromMediaSource(src, a, reader);
    SafeRelease(&a);
    return hr;
}

// ---- camera controls (IAMCameraControl / IAMVideoProcAmp / IKsControl for AE priority) ----
struct CtlState { bool ok = false; long val = 0, flags = 0, mn = 0, mx = 0, step = 0, def = 0, capsFlags = 0; HRESULT setHr = S_FALSE; };
static std::string CtlJson(const char* name, const CtlState& c) {
    std::ostringstream o;
    o << "\"" << name << "\":{\"supported\":" << (c.ok ? "true" : "false");
    if (c.ok) o << ",\"value\":" << c.val << ",\"flags\":" << c.flags << ",\"flags_meaning\":\"" << (c.flags == 1 ? "auto" : (c.flags == 2 ? "manual" : "other")) << "\",\"min\":" << c.mn << ",\"max\":" << c.mx << ",\"step\":" << c.step << ",\"default\":" << c.def;
    o << ",\"set_hr\":\"0x" << std::hex << (unsigned long)c.setHr << std::dec << "\"}";
    return o.str();
}

static CtlState CamCtl(IAMCameraControl* cc, long prop, bool doSet, long setVal, long setFlags) {
    CtlState s; if (!cc) return s;
    long f = 0;
    if (FAILED(cc->GetRange(prop, &s.mn, &s.mx, &s.step, &s.def, &s.capsFlags))) return s;
    if (doSet) s.setHr = cc->Set(prop, setVal, setFlags);
    s.ok = SUCCEEDED(cc->Get(prop, &s.val, &f)); s.flags = f; return s;
}
static CtlState ProcAmp(IAMVideoProcAmp* pa, long prop, bool doSet, long setVal, long setFlags) {
    CtlState s; if (!pa) return s;
    long f = 0;
    if (FAILED(pa->GetRange(prop, &s.mn, &s.mx, &s.step, &s.def, &s.capsFlags))) return s;
    if (doSet) s.setHr = pa->Set(prop, setVal, setFlags);
    s.ok = SUCCEEDED(pa->Get(prop, &s.val, &f)); s.flags = f; return s;
}
static CtlState AePriority(IUnknown* src, bool doSet, long setVal) {
    CtlState s; IKsControl* ks = nullptr;
    if (FAILED(src->QueryInterface(IID_PPV_ARGS(&ks)))) return s;
    KSPROPERTY_CAMERACONTROL_S p{}; ULONG ret = 0;
    p.Property.Set = PROPSETID_VIDCAP_CAMERACONTROL; p.Property.Id = KSPROPERTY_CAMERACONTROL_AUTO_EXPOSURE_PRIORITY;
    if (doSet) {
        p.Property.Flags = KSPROPERTY_TYPE_SET; p.Value = setVal; p.Flags = KSPROPERTY_CAMERACONTROL_FLAGS_MANUAL; p.Capabilities = 0;
        s.setHr = ks->KsProperty((PKSPROPERTY)&p, sizeof(p), &p, sizeof(p), &ret);
    }
    KSPROPERTY_CAMERACONTROL_S g{}; g.Property.Set = PROPSETID_VIDCAP_CAMERACONTROL; g.Property.Id = KSPROPERTY_CAMERACONTROL_AUTO_EXPOSURE_PRIORITY; g.Property.Flags = KSPROPERTY_TYPE_GET;
    if (SUCCEEDED(ks->KsProperty((PKSPROPERTY)&g, sizeof(g), &g, sizeof(g), &ret))) { s.ok = true; s.val = g.Value; s.flags = g.Flags; }
    ks->Release(); return s;
}

static std::string ControlsJson(IUnknown* src, bool doSet, bool setExp, long exposure, bool setWb, long wb, bool setAePri, long aePri) {
    IAMCameraControl* cc = nullptr; IAMVideoProcAmp* pa = nullptr;
    src->QueryInterface(IID_PPV_ARGS(&cc)); src->QueryInterface(IID_PPV_ARGS(&pa));
    std::ostringstream o; o << "{";
    o << CtlJson("exposure_log2s", CamCtl(cc, CameraControl_Exposure, doSet && setExp, exposure, CameraControl_Flags_Manual)) << ",";
    o << CtlJson("focus", CamCtl(cc, CameraControl_Focus, false, 0, 0)) << ",";
    o << CtlJson("white_balance_k", ProcAmp(pa, VideoProcAmp_WhiteBalance, doSet && setWb, wb, VideoProcAmp_Flags_Manual)) << ",";
    o << CtlJson("gain", ProcAmp(pa, VideoProcAmp_Gain, false, 0, 0)) << ",";
    o << CtlJson("backlight_compensation", ProcAmp(pa, VideoProcAmp_BacklightCompensation, false, 0, 0)) << ",";
    o << CtlJson("powerline_frequency", ProcAmp(pa, 13 /*VideoProcAmp_PowerlineFrequency not in all SDKs*/, false, 0, 0)) << ",";
    o << CtlJson("auto_exposure_priority", AePriority(src, doSet && setAePri, aePri));
    o << "}";
    SafeRelease(&cc); SafeRelease(&pa);
    return o.str();
}


// DirectShow path for controls only (works even when MF activation fails). Matches DevicePath / FriendlyName.
// DirectShow capture-pin formats via IAMStreamConfig (what FFmpeg dshow / OpenCV CAP_DSHOW can select).
static int DshowFormats(const std::vector<std::string>& wants) {
    ICreateDevEnum* de = nullptr; IEnumMoniker* em = nullptr; int found = 0;
    if (FAILED(CoCreateInstance(CLSID_SystemDeviceEnum, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&de)))) return 0;
    if (de->CreateClassEnumerator(CLSID_VideoInputDeviceCategory, &em, 0) != S_OK) { de->Release(); return 0; }
    ICaptureGraphBuilder2* cgb = nullptr;
    CoCreateInstance(CLSID_CaptureGraphBuilder2, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&cgb));
    IMoniker* mk = nullptr; bool first = true;
    printf("{\"dshow_formats\":[");
    while (em->Next(1, &mk, nullptr) == S_OK) {
        IPropertyBag* pb = nullptr; std::string name, path;
        if (SUCCEEDED(mk->BindToStorage(nullptr, nullptr, IID_PPV_ARGS(&pb)))) {
            VARIANT v; VariantInit(&v);
            if (SUCCEEDED(pb->Read(L"FriendlyName", &v, nullptr))) name = W2U(v.bstrVal); VariantClear(&v);
            if (SUCCEEDED(pb->Read(L"DevicePath", &v, nullptr))) path = W2U(v.bstrVal); VariantClear(&v);
            pb->Release();
        }
        bool match = false; for (auto& w : wants) if (Lower(path).find(w) != std::string::npos || Lower(name).find(w) != std::string::npos) match = true;
        IBaseFilter* f = nullptr;
        if (match && cgb && SUCCEEDED(mk->BindToObject(nullptr, nullptr, IID_PPV_ARGS(&f)))) {
            IAMStreamConfig* sc = nullptr;
            HRESULT hr = cgb->FindInterface(&PIN_CATEGORY_CAPTURE, &MEDIATYPE_Video, f, IID_IAMStreamConfig, (void**)&sc);
            printf("%s{\"name\":\"%s\",\"device_path\":\"%s\",\"hr\":\"0x%08lx\",\"caps\":[", first ? "" : ",", JEsc(name).c_str(), JEsc(path).c_str(), (unsigned long)hr);
            first = false; found++;
            if (sc) {
                int n = 0, sz = 0; sc->GetNumberOfCapabilities(&n, &sz);
                std::vector<BYTE> scc(sz > 0 ? sz : 128);
                for (int i = 0; i < n; i++) {
                    AM_MEDIA_TYPE* mt = nullptr;
                    if (FAILED(sc->GetStreamCaps(i, &mt, scc.data())) || !mt) continue;
                    long w = 0, h = 0; REFERENCE_TIME atpf = 0; DWORD bic = 0; const char* ft = "other";
                    if (mt->formattype == FORMAT_VideoInfo && mt->pbFormat) { auto* vi = (VIDEOINFOHEADER*)mt->pbFormat; w = vi->bmiHeader.biWidth; h = vi->bmiHeader.biHeight; atpf = vi->AvgTimePerFrame; bic = vi->bmiHeader.biCompression; ft = "VideoInfo"; }
                    else if (mt->formattype == FORMAT_VideoInfo2 && mt->pbFormat) { auto* vi = (VIDEOINFOHEADER2*)mt->pbFormat; w = vi->bmiHeader.biWidth; h = vi->bmiHeader.biHeight; atpf = vi->AvgTimePerFrame; bic = vi->bmiHeader.biCompression; ft = "VideoInfo2"; }
                    GUID bg = mt->subtype; bg.Data1 = bic;
                    auto* vscc = (VIDEO_STREAM_CONFIG_CAPS*)scc.data();
                    printf("%s{\"i\":%d,\"formattype\":\"%s\",\"biCompression\":\"%s\",\"subtype\":\"%s\",\"w\":%ld,\"h\":%ld,\"default_fps\":%.3f,\"min_fps\":%.3f,\"max_fps\":%.3f,\"vscc_min_out\":\"%ldx%ld\",\"vscc_max_out\":\"%ldx%ld\",\"vscc_input\":\"%ldx%ld\"}", i ? "," : "", i, ft, FourCC(bg).c_str(), FourCC(mt->subtype).c_str(), w, h,
                           atpf ? 1e7 / atpf : 0.0, vscc->MaxFrameInterval ? 1e7 / vscc->MaxFrameInterval : 0.0, vscc->MinFrameInterval ? 1e7 / vscc->MinFrameInterval : 0.0,
                           vscc->MinOutputSize.cx, vscc->MinOutputSize.cy, vscc->MaxOutputSize.cx, vscc->MaxOutputSize.cy, vscc->InputSize.cx, vscc->InputSize.cy);
                    if (mt->cbFormat) CoTaskMemFree(mt->pbFormat);
                    if (mt->pUnk) mt->pUnk->Release();
                    CoTaskMemFree(mt);
                }
                sc->Release();
            }
            printf("]}");
            f->Release();
        }
        mk->Release();
    }
    printf("]}\n");
    if (cgb) cgb->Release();
    em->Release(); de->Release();
    return found;
}

static int DshowControls(const std::vector<std::string>& wants, bool setExp, long exposure, bool setWb, long wb, bool setAePri, long aePri) {
    ICreateDevEnum* de = nullptr; IEnumMoniker* em = nullptr; int found = 0;
    if (FAILED(CoCreateInstance(CLSID_SystemDeviceEnum, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&de)))) return 0;
    if (de->CreateClassEnumerator(CLSID_VideoInputDeviceCategory, &em, 0) != S_OK) { de->Release(); return 0; }
    IMoniker* mk = nullptr;
    while (em->Next(1, &mk, nullptr) == S_OK) {
        IPropertyBag* pb = nullptr; std::string name, path;
        if (SUCCEEDED(mk->BindToStorage(nullptr, nullptr, IID_PPV_ARGS(&pb)))) {
            VARIANT v; VariantInit(&v);
            if (SUCCEEDED(pb->Read(L"FriendlyName", &v, nullptr))) name = W2U(v.bstrVal); VariantClear(&v);
            if (SUCCEEDED(pb->Read(L"DevicePath", &v, nullptr))) path = W2U(v.bstrVal); VariantClear(&v);
            pb->Release();
        }
        bool match = false; for (auto& w : wants) if (Lower(path).find(w) != std::string::npos || Lower(name).find(w) != std::string::npos) match = true;
        if (match) {
            IBaseFilter* f = nullptr;
            if (SUCCEEDED(mk->BindToObject(nullptr, nullptr, IID_PPV_ARGS(&f)))) {
                std::string b = ControlsJson(f, false, false, 0, false, 0, false, 0);
                std::string a2 = ControlsJson(f, true, setExp, exposure, setWb, wb, setAePri, aePri);
                std::string e = ControlsJson(f, false, false, 0, false, 0, false, 0);
                printf("%s: before=%s\n after=%s\n end=%s\n", name.c_str(), b.c_str(), a2.c_str(), e.c_str());
                f->Release(); found++;
            }
        }
        mk->Release();
    }
    em->Release(); de->Release();
    return found;
}

// ---- capture ----
struct Frame {
    uint64_t seq; int64_t arrival_qpc; int64_t mf_systime_hns; LONGLONG ts_hns; LONGLONG sample_time_hns; LONGLONG duration_hns; DWORD flags;
    bool has_devts; UINT64 devts; bool has_devref; UINT64 devref; bool has_mfts; INT64 mfts; UINT32 discontinuity; UINT32 cleanpoint;
    bool has_meta; UINT32 rawstream_bytes; UINT32 uvc_hdr_bytes; bool has_first_scan; UINT64 first_scan_qpc; bool has_last_scan; UINT64 last_scan_qpc;
    UINT32 nbuffers; size_t plen; std::vector<uint8_t> bytes;
};

struct Cam {
    int idx; Device dev; IMFMediaSource* src = nullptr; IMFSourceReader* reader = nullptr;
    std::string chosenType, outSubtype, controlsBefore, controlsAfter, error, nativeTypesJson;
    UINT32 w = 0, h = 0, fn = 0, fd = 0; UINT32 reqW = 0, reqH = 0; double reqFps = 0;
    std::vector<Frame> frames; std::vector<std::string> attrDumps; std::atomic<int64_t> firstFrameQpc{0};
    HRESULT readErr = S_OK; uint64_t streamTicks = 0, nullSamples = 0;
};

static std::atomic<bool> g_stop{false};
static bool g_noPayload = false;

static void ReadLoop(Cam* c, int attrDump) {
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    uint64_t seq = 0;
    while (!g_stop.load()) {
        DWORD stream = 0, flags = 0; LONGLONG ts = 0; IMFSample* s = nullptr;
        HRESULT hr = c->reader->ReadSample(MF_SOURCE_READER_FIRST_VIDEO_STREAM, 0, &stream, &flags, &ts, &s);
        int64_t arr = QpcNow(); MFTIME sys = MFGetSystemTime();
        if (FAILED(hr)) { c->readErr = hr; break; }
        if (flags & MF_SOURCE_READERF_STREAMTICK) c->streamTicks++;
        if (flags & (MF_SOURCE_READERF_ENDOFSTREAM | MF_SOURCE_READERF_ERROR)) { c->readErr = E_FAIL; SafeRelease(&s); break; }
        if (!s) { c->nullSamples++; continue; }
        if (c->firstFrameQpc.load() == 0) c->firstFrameQpc = arr;
        Frame f{}; f.seq = seq++; f.arrival_qpc = arr; f.mf_systime_hns = sys; f.ts_hns = ts; f.flags = flags;
        s->GetSampleTime(&f.sample_time_hns); s->GetSampleDuration(&f.duration_hns);
        f.has_devts = SUCCEEDED(s->GetUINT64(kMFSampleExtension_DeviceTimestamp, &f.devts));
        f.has_devref = SUCCEEDED(s->GetUINT64(kMFSampleExtension_DeviceReferenceSystemTime, &f.devref));
        UINT64 tmp = 0; f.has_mfts = SUCCEEDED(s->GetUINT64(MFSampleExtension_Timestamp, &tmp)); f.mfts = (INT64)tmp;
        s->GetUINT32(MFSampleExtension_Discontinuity, &f.discontinuity); s->GetUINT32(MFSampleExtension_CleanPoint, &f.cleanpoint);
        IMFAttributes* meta = nullptr;
        if (SUCCEEDED(s->GetUnknown(MFSampleExtension_CaptureMetadata, IID_PPV_ARGS(&meta)))) {
            f.has_meta = true; UINT32 sz = 0;
            if (SUCCEEDED(meta->GetBlobSize(MF_CAPTURE_METADATA_FRAME_RAWSTREAM, &sz))) f.rawstream_bytes = sz;
            if (SUCCEEDED(meta->GetBlobSize(MF_CAPTURE_METADATA_UVC_PAYLOADHEADER, &sz))) f.uvc_hdr_bytes = sz;
            f.has_first_scan = SUCCEEDED(meta->GetUINT64(MF_CAPTURE_METADATA_FIRST_SCANLINE_START_TIME_QPC, &f.first_scan_qpc));
            f.has_last_scan = SUCCEEDED(meta->GetUINT64(MF_CAPTURE_METADATA_LAST_SCANLINE_END_TIME_QPC, &f.last_scan_qpc));
            meta->Release();
        }
        if ((int)c->attrDumps.size() < attrDump) c->attrDumps.push_back(AttrsJson(s));
        DWORD nb = 0; s->GetBufferCount(&nb); f.nbuffers = nb;
        IMFMediaBuffer* b = nullptr;
        if (SUCCEEDED(s->ConvertToContiguousBuffer(&b))) {
            BYTE* p = nullptr; DWORD len = 0;
            if (SUCCEEDED(b->Lock(&p, nullptr, &len))) { f.plen = len; if (!g_noPayload) f.bytes.assign(p, p + len); b->Unlock(); }
            b->Release();
        }
        c->frames.push_back(std::move(f));
        s->Release();
    }
    CoUninitialize();
}

static void Usage() {
    fprintf(stderr, "usage: mf_mjpeg_capture --list | --dev SUBSTR [--dev ...] --width W --height H --fps F [--seconds S] [--warmup S] [--out DIR] [--exposure E] [--wb K] [--ae-priority 0|1] [--aux-pid PID] [--attr-dump N] [--decode-to NV12|RGB32] [--controls-only]\n");
}

int main(int argc, char** argv) {
    bool list = false, listEnum = false, dshowFormats = false, listDshow = false, viaDshow = false, controlsOnly = false, setExp = false, setWb = false, setAePri = false;
    std::vector<std::string> devs; std::vector<std::string> modeStrs; UINT32 W = 0, H = 0; double FPS = 0; double seconds = 10, warmup = 2;
    long exposure = 0, wb = 0, aePri = 0; DWORD auxPid = 0; int attrDump = 5; std::string outDir, decodeTo, subtypeWant = "MJPG";
    for (int i = 1; i < argc; i++) {
        std::string a = argv[i]; auto nx = [&]() -> std::string { if (i + 1 >= argc) { Usage(); exit(2); } return argv[++i]; };
        if (a == "--list") list = true;
        else if (a == "--list-enum") listEnum = true;
        else if (a == "--dev") devs.push_back(Lower(nx()));
        else if (a == "--width") W = std::stoul(nx());
        else if (a == "--height") H = std::stoul(nx());
        else if (a == "--fps") FPS = std::stod(nx());
        else if (a == "--mode") modeStrs.push_back(nx());  // per --dev, in order: WxH@FPS
        else if (a == "--seconds") seconds = std::stod(nx());
        else if (a == "--warmup") warmup = std::stod(nx());
        else if (a == "--out") outDir = nx();
        else if (a == "--exposure") { exposure = std::stol(nx()); setExp = true; }
        else if (a == "--wb") { wb = std::stol(nx()); setWb = true; }
        else if (a == "--ae-priority") { aePri = std::stol(nx()); setAePri = true; }
        else if (a == "--aux-pid") auxPid = std::stoul(nx());
        else if (a == "--attr-dump") attrDump = std::stoi(nx());
        else if (a == "--decode-to") decodeTo = nx();
        else if (a == "--subtype") subtypeWant = nx();
        else if (a == "--controls-only") controlsOnly = true;
        else if (a == "--via-dshow") viaDshow = true;
        else if (a == "--no-payload") g_noPayload = true;
        else if (a == "--list-dshow") listDshow = true;
        else if (a == "--dshow-formats") dshowFormats = true;
        else { Usage(); return 2; }
    }
    HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (dshowFormats) { int n = DshowFormats(devs); return n == (int)devs.size() ? 0 : 3; }
    if (listDshow) {  // DirectShow video-input enumeration order (= OpenCV CAP_DSHOW index order)
        ICreateDevEnum* de = nullptr; IEnumMoniker* em = nullptr; IMoniker* mk = nullptr; int i = 0;
        printf("{\"dshow_video_input_devices\":[");
        if (SUCCEEDED(CoCreateInstance(CLSID_SystemDeviceEnum, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&de))) && de->CreateClassEnumerator(CLSID_VideoInputDeviceCategory, &em, 0) == S_OK) {
            while (em->Next(1, &mk, nullptr) == S_OK) {
                IPropertyBag* pb = nullptr; std::string name, path;
                if (SUCCEEDED(mk->BindToStorage(nullptr, nullptr, IID_PPV_ARGS(&pb)))) {
                    VARIANT v; VariantInit(&v);
                    if (SUCCEEDED(pb->Read(L"FriendlyName", &v, nullptr))) name = W2U(v.bstrVal); VariantClear(&v);
                    if (SUCCEEDED(pb->Read(L"DevicePath", &v, nullptr))) path = W2U(v.bstrVal); VariantClear(&v);
                    pb->Release();
                }
                printf("%s{\"index\":%d,\"name\":\"%s\",\"device_path\":\"%s\"}", i ? "," : "", i, JEsc(name).c_str(), JEsc(path).c_str()); i++;
                mk->Release();
            }
            em->Release();
        }
        if (de) de->Release();
        printf("]}\n"); return 0;
    }
    if (controlsOnly && viaDshow) {
        int n = DshowControls(devs, setExp, exposure, setWb, wb, setAePri, aePri);
        if (n != (int)devs.size()) { fprintf(stderr, "error: matched %d of %zu devices via DirectShow\n", n, devs.size()); return 3; }
        return 0;
    }
    hr = MFStartup(MF_VERSION);
    if (FAILED(hr)) { fprintf(stderr, "error: MFStartup 0x%08lx\n", hr); return 1; }
    std::vector<Device> all; hr = EnumDevices(all);
    if (FAILED(hr)) { fprintf(stderr, "error: MFEnumDeviceSources 0x%08lx\n", hr); return 1; }

    if (listEnum) {  // MFEnumDeviceSources order (= OpenCV CAP_MSMF index order); no source is activated
        printf("{\"devices\":[");
        for (size_t i = 0; i < all.size(); i++) printf("%s{\"index\":%zu,\"name\":\"%s\",\"symbolic_link\":\"%s\"}", i ? "," : "", i, JEsc(all[i].name).c_str(), JEsc(all[i].symlink).c_str());
        printf("]}\n");
        return 0;
    }
    if (list) {
        printf("{\"devices\":[\n");
        bool firstDev = true;
        for (auto& d : all) {
            // with --dev filters, only matching sources are activated (so an excluded/flaky camera is never opened)
            if (!devs.empty()) { bool m = false; for (auto& w : devs) if (Lower(d.symlink).find(w) != std::string::npos || Lower(d.name).find(w) != std::string::npos) m = true; if (!m) continue; }
            IMFMediaSource* src = nullptr; IMFSourceReader* r = nullptr; std::vector<TypeInfo> types; std::string err;
            hr = d.act->ActivateObject(IID_PPV_ARGS(&src));
            if (SUCCEEDED(hr)) hr = CreateReader(src, true, false, &r);
            if (SUCCEEDED(hr)) types = NativeTypes(r); else { char b[32]; sprintf_s(b, "0x%08lx", hr); err = b; }
            printf("%s{\"name\":\"%s\",\"symbolic_link\":\"%s\",\"error\":\"%s\",\"native_types\":[", firstDev ? "" : ",\n", JEsc(d.name).c_str(), JEsc(d.symlink).c_str(), err.c_str());
            firstDev = false;
            for (size_t i = 0; i < types.size(); i++) {
                auto& t = types[i];
                printf("%s{\"index\":%lu,\"subtype\":\"%s\",\"width\":%u,\"height\":%u,\"fps_num\":%u,\"fps_den\":%u}", i ? "," : "", t.index, t.sub.c_str(), t.w, t.h, t.fn, t.fd);
            }
            printf("]}");
            SafeRelease(&r); if (src) { src->Shutdown(); src->Release(); }
            d.act->ShutdownObject();
        }
        printf("\n]}\n");
        return 0;
    }
    if (devs.empty()) { Usage(); return 2; }
    if (!controlsOnly && (W == 0 || H == 0 || FPS <= 0)) { Usage(); return 2; }

    bool decode = !decodeTo.empty();
    GUID outSub = MFVideoFormat_NV12;
    if (decodeTo == "RGB32") outSub = MFVideoFormat_RGB32; else if (decode && decodeTo != "NV12") { fprintf(stderr, "error: --decode-to NV12|RGB32\n"); return 2; }

    std::vector<Cam*> cams;
    for (auto& want : devs) {
        Device* found = nullptr;
        for (auto& d : all) if (Lower(d.symlink).find(want) != std::string::npos || Lower(d.name).find(want) != std::string::npos) { found = &d; break; }
        if (!found) { fprintf(stderr, "error: no device matches '%s'\n", want.c_str()); return 3; }
        Cam* c = new Cam(); c->idx = (int)cams.size(); c->dev = *found; cams.push_back(c);
        c->reqW = W; c->reqH = H; c->reqFps = FPS;
        if (!modeStrs.empty()) {
            if (modeStrs.size() != devs.size()) { fprintf(stderr, "error: give one --mode per --dev\n"); return 2; }
            unsigned mw = 0, mh = 0; double mf = 0;
            if (sscanf_s(modeStrs[c->idx].c_str(), "%ux%u@%lf", &mw, &mh, &mf) != 3) { fprintf(stderr, "error: bad --mode %s\n", modeStrs[c->idx].c_str()); return 2; }
            c->reqW = mw; c->reqH = mh; c->reqFps = mf;
        }
        hr = found->act->ActivateObject(IID_PPV_ARGS(&c->src));
        if (FAILED(hr)) { fprintf(stderr, "error: ActivateObject %s 0x%08lx\n", found->name.c_str(), hr); return 4; }
        c->controlsBefore = ControlsJson(c->src, false, false, 0, false, 0, false, 0);
        c->controlsAfter = ControlsJson(c->src, true, setExp, exposure, setWb, wb, setAePri, aePri);
        if (controlsOnly) continue;
        hr = CreateReader(c->src, !decode, decode, &c->reader);
        if (FAILED(hr)) { fprintf(stderr, "error: CreateSourceReader 0x%08lx\n", hr); return 4; }
        auto types = NativeTypes(c->reader);
        std::ostringstream nt; nt << "[";
        const TypeInfo* best = nullptr;
        for (size_t i = 0; i < types.size(); i++) {
            auto& t = types[i];
            nt << (i ? "," : "") << "{\"index\":" << t.index << ",\"subtype\":\"" << t.sub << "\",\"width\":" << t.w << ",\"height\":" << t.h << ",\"fps_num\":" << t.fn << ",\"fps_den\":" << t.fd << "}";
            double f = t.fd ? (double)t.fn / t.fd : 0;
            if (t.sub == subtypeWant && t.w == c->reqW && t.h == c->reqH && fabs(f - c->reqFps) < 0.5 && !best) best = &t;
        }
        nt << "]"; c->nativeTypesJson = nt.str();
        if (!best) { fprintf(stderr, "error: %s has no native %s %ux%u@%.2f type\n", c->dev.name.c_str(), subtypeWant.c_str(), c->reqW, c->reqH, c->reqFps); return 5; }
        IMFMediaType* nat = nullptr;
        c->reader->GetNativeMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM, best->index, &nat);
        hr = c->reader->SetCurrentMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM, nullptr, nat);
        nat->Release();
        if (FAILED(hr)) { fprintf(stderr, "error: SetCurrentMediaType(native) 0x%08lx\n", hr); return 6; }
        // also select the device's native type on the source itself (so the device streams MJPG) then request decoded output
        if (decode) {
            IMFMediaType* out = nullptr; MFCreateMediaType(&out);
            out->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Video); out->SetGUID(MF_MT_SUBTYPE, outSub);
            MFSetAttributeSize(out, MF_MT_FRAME_SIZE, c->reqW, c->reqH);
            hr = c->reader->SetCurrentMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM, nullptr, out); out->Release();
            if (FAILED(hr)) { fprintf(stderr, "error: SetCurrentMediaType(decoded %s) 0x%08lx\n", decodeTo.c_str(), hr); return 6; }
        }
        IMFMediaType* cur = nullptr;
        c->reader->GetCurrentMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM, &cur);
        GUID cs{}; cur->GetGUID(MF_MT_SUBTYPE, &cs); c->outSubtype = FourCC(cs);
        MFGetAttributeSize(cur, MF_MT_FRAME_SIZE, &c->w, &c->h); MFGetAttributeRatio(cur, MF_MT_FRAME_RATE, &c->fn, &c->fd);
        cur->Release();
        std::ostringstream ct; ct << best->sub << " " << best->w << "x" << best->h << "@" << best->fn << "/" << best->fd << " (native index " << best->index << ")";
        c->chosenType = ct.str();
    }

    HANDLE self = GetCurrentProcess(); HANDLE aux = nullptr; DWORD auxErr = 0;
    double u0 = 0, k0 = 0, u1 = 0, k1 = 0, au0 = 0, ak0 = 0, au1 = 0, ak1 = 0; bool auxOk = false;
    ULONG64 cy0 = 0, cy1 = 0, acy0 = 0, acy1 = 0; unsigned long long tsc0 = 0, tsc1 = 0;
    int64_t qStart = 0, qEnd = 0, qOpen = QpcNow();
    std::vector<std::thread> threads;
    if (!controlsOnly) {
        for (auto* c : cams) threads.emplace_back(ReadLoop, c, attrDump);
        Sleep((DWORD)(warmup * 1000));
        if (auxPid == 0) auxPid = FrameServerPid();
        if (auxPid) { aux = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, auxPid); if (!aux) auxErr = GetLastError(); }
        qStart = QpcNow(); tsc0 = __rdtsc(); ProcCpu(self, &u0, &k0); cy0 = ProcCycles(self); if (aux) { auxOk = ProcCpu(aux, &au0, &ak0); acy0 = ProcCycles(aux); }
        Sleep((DWORD)(seconds * 1000));
        qEnd = QpcNow(); tsc1 = __rdtsc(); ProcCpu(self, &u1, &k1); cy1 = ProcCycles(self); if (aux && auxOk) { auxOk = ProcCpu(aux, &au1, &ak1); acy1 = ProcCycles(aux); }
        g_stop = true;
        for (auto& t : threads) t.join();
    }
    for (auto* c : cams) {
        if (c->reader) c->reader->Flush(MF_SOURCE_READER_ALL_STREAMS);
        // controls state after streaming (to prove settings held)
        if (!controlsOnly) c->controlsAfter = c->controlsAfter; // value right after set is kept; read again below
    }
    std::vector<std::string> controlsEnd;
    for (auto* c : cams) controlsEnd.push_back(ControlsJson(c->src, false, false, 0, false, 0, false, 0));

    if (!outDir.empty()) {
        CreateDirectoryA(outDir.c_str(), nullptr);
        std::string mp = outDir + "\\meta.json";
        FILE* m = nullptr; fopen_s(&m, mp.c_str(), "wb");
        if (!m) { fprintf(stderr, "error: cannot write %s\n", mp.c_str()); return 7; }
        double wall = qEnd > qStart ? (double)(qEnd - qStart) / QpcFreq() : 0;
        fprintf(m, "{\"backend\":\"%s\",\"requested\":{\"subtype\":\"%s\",\"width\":%u,\"height\":%u,\"fps\":%.3f},\"decode_to\":\"%s\",\"disable_converters\":%s,",
                decode ? "msmf-sourcereader-decoded" : "msmf-sourcereader", subtypeWant.c_str(), W, H, FPS, decodeTo.c_str(), decode ? "false" : "true");
        fprintf(m, "\"qpc_freq\":%lld,\"window\":{\"start_ns\":%lld,\"end_ns\":%lld,\"wall_s\":%.6f,\"warmup_s\":%.3f,\"open_ns\":%lld},", QpcFreq(), QpcToNs(qStart), QpcToNs(qEnd), wall, warmup, QpcToNs(qOpen));
        double tscHz = wall > 0 ? (double)(tsc1 - tsc0) / wall : 0;
        fprintf(m, "\"cpu\":{\"method\":\"GetProcessTimes (tick-sampled) + QueryProcessCycleTime/TSC-rate (precise)\",\"process_user_s\":%.6f,\"process_kernel_s\":%.6f,\"process_cpu_pct_of_one_core_ticks\":%.3f,\"process_cycles\":%llu,\"tsc_hz\":%.0f,\"process_cpu_pct_of_one_core\":%.3f,",
                u1 - u0, k1 - k0, wall > 0 ? 100.0 * ((u1 - u0) + (k1 - k0)) / wall : 0, (unsigned long long)(cy1 - cy0), tscHz, (wall > 0 && tscHz > 0) ? 100.0 * (double)(cy1 - cy0) / tscHz / wall : 0);
        fprintf(m, "\"frameserver_pid\":%lu,\"frameserver_open_error\":%lu,\"frameserver_ok\":%s,\"frameserver_cpu_pct_of_one_core_ticks\":%.3f,\"frameserver_cycles\":%llu,\"frameserver_cpu_pct_of_one_core\":%s},",
                auxPid, auxErr, auxOk ? "true" : "false", (wall > 0 && auxOk) ? 100.0 * ((au1 - au0) + (ak1 - ak0)) / wall : 0, (unsigned long long)(acy1 - acy0),
                (wall > 0 && auxOk && tscHz > 0) ? std::to_string(100.0 * (double)(acy1 - acy0) / tscHz / wall).c_str() : "null");
        fprintf(m, "\"cameras\":[");
        for (size_t i = 0; i < cams.size(); i++) {
            auto* c = cams[i];
            fprintf(m, "%s{\"idx\":%d,\"name\":\"%s\",\"symbolic_link\":\"%s\",\"chosen_native_type\":\"%s\",\"reader_output_subtype\":\"%s\",\"output_w\":%u,\"output_h\":%u,\"output_fps_num\":%u,\"output_fps_den\":%u,",
                    i ? "," : "", c->idx, JEsc(c->dev.name).c_str(), JEsc(c->dev.symlink).c_str(), c->chosenType.c_str(), c->outSubtype.c_str(), c->w, c->h, c->fn, c->fd);
            fprintf(m, "\"requested_mode\":{\"width\":%u,\"height\":%u,\"fps\":%.3f},", c->reqW, c->reqH, c->reqFps);
            fprintf(m, "\"read_error\":\"0x%08lx\",\"stream_ticks\":%llu,\"null_samples\":%llu,\"frames_total\":%zu,\"first_frame_latency_ms\":%.3f,",
                    (unsigned long)c->readErr, c->streamTicks, c->nullSamples, c->frames.size(), c->firstFrameQpc ? 1000.0 * (c->firstFrameQpc - qOpen) / QpcFreq() : -1.0);
            fprintf(m, "\"controls_before\":%s,\"controls_after_set\":%s,\"controls_end\":%s,\"native_types\":%s,\"sample_attribute_dumps\":[",
                    c->controlsBefore.c_str(), c->controlsAfter.c_str(), controlsEnd[i].c_str(), c->nativeTypesJson.empty() ? "[]" : c->nativeTypesJson.c_str());
            for (size_t j = 0; j < c->attrDumps.size(); j++) fprintf(m, "%s%s", j ? "," : "", c->attrDumps[j].c_str());
            fprintf(m, "]}");
        }
        fprintf(m, "]}\n"); fclose(m);
        std::string fp = outDir + "\\frames.jsonl";
        FILE* fj = nullptr; fopen_s(&fj, fp.c_str(), "wb");
        for (auto* c : cams) {
            std::string bp = outDir + "\\frames_" + std::to_string(c->idx) + ".bin";
            FILE* fb = nullptr; fopen_s(&fb, bp.c_str(), "wb");
            for (auto& f : c->frames) {
                bool soi = f.bytes.size() >= 2 && f.bytes[0] == 0xFF && f.bytes[1] == 0xD8;
                bool eoi = f.bytes.size() >= 2 && f.bytes[f.bytes.size() - 2] == 0xFF && f.bytes[f.bytes.size() - 1] == 0xD9;
                int64_t arrNs = QpcToNs(f.arrival_qpc);
                bool inWin = f.arrival_qpc >= qStart && f.arrival_qpc <= qEnd;
                fprintf(fj, "{\"camera_key\":\"%s\",\"backend\":\"%s\",\"cam_idx\":%d,\"seq\":%llu,\"host_arrival_ns\":%lld,\"in_window\":%s,"
                            "\"os_timestamp_ns\":%lld,\"os_timestamp_source\":\"IMFSourceReader::ReadSample llTimestamp (100ns units, x100)\","
                            "\"uvc_pts\":null,\"uvc_scr_stc\":null,\"uvc_scr_sof\":null,\"device_clock_hz\":null,\"payload_bytes\":%zu,\"is_valid_jpeg\":null,"
                            "\"soi\":%s,\"eoi_at_end\":%s,\"mf_systime_at_arrival_hns\":%lld,\"readsample_ts_hns\":%lld,\"sample_time_hns\":%lld,\"sample_duration_hns\":%lld,\"reader_flags\":%lu,"
                            "\"device_timestamp\":%s,\"device_reference_system_time\":%s,\"mfsampleextension_timestamp\":%s,\"discontinuity\":%u,\"cleanpoint\":%u,"
                            "\"has_capture_metadata\":%s,\"rawstream_bytes\":%u,\"uvc_payloadheader_bytes\":%u,\"first_scanline_qpc\":%s,\"last_scanline_qpc\":%s,\"nbuffers\":%u}\n",
                        JEsc(c->dev.symlink).c_str(), decode ? "msmf-sourcereader-decoded" : "msmf-sourcereader", c->idx, f.seq, arrNs, inWin ? "true" : "false",
                        (long long)f.ts_hns * 100LL, f.plen, soi ? "true" : "false", eoi ? "true" : "false", f.mf_systime_hns, f.ts_hns, f.sample_time_hns, f.duration_hns, f.flags,
                        f.has_devts ? std::to_string(f.devts).c_str() : "null", f.has_devref ? std::to_string(f.devref).c_str() : "null", f.has_mfts ? std::to_string(f.mfts).c_str() : "null",
                        f.discontinuity, f.cleanpoint, f.has_meta ? "true" : "false", f.rawstream_bytes, f.uvc_hdr_bytes,
                        f.has_first_scan ? std::to_string(f.first_scan_qpc).c_str() : "null", f.has_last_scan ? std::to_string(f.last_scan_qpc).c_str() : "null", f.nbuffers);
                if (fb) {
                    uint32_t cam = c->idx; uint64_t seq = f.seq; uint32_t len = (uint32_t)f.bytes.size();
                    fwrite(&cam, 4, 1, fb); fwrite(&seq, 8, 1, fb); fwrite(&len, 4, 1, fb); if (len) fwrite(f.bytes.data(), 1, len, fb);
                }
            }
            if (fb) fclose(fb);
        }
        if (fj) fclose(fj);
    } else {
        for (auto* c : cams) printf("%s: before=%s\n after=%s\n end=%s\n", c->dev.name.c_str(), c->controlsBefore.c_str(), c->controlsAfter.c_str(), ControlsJson(c->src, false, false, 0, false, 0, false, 0).c_str());
    }
    for (auto* c : cams) {
        if (!controlsOnly) printf("cam %d %s: %zu frames, out=%s, err=0x%08lx\n", c->idx, c->dev.name.c_str(), c->frames.size(), c->outSubtype.c_str(), (unsigned long)c->readErr);
        SafeRelease(&c->reader); if (c->src) { c->src->Shutdown(); c->src->Release(); }
    }
    if (aux) CloseHandle(aux);

    MFShutdown(); CoUninitialize();
    return 0;
}
