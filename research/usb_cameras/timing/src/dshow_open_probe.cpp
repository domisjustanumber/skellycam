// dshow_open_probe.cpp -- per-stage HRESULTs of a minimal DirectShow capture graph (ksproxy path: no Frame Server,
// and DirectShow never requests usbvideo capture metadata). capture filter -> Null Renderer.
// Stages: bind moniker, IAMCameraControl::Get(Exposure), IAMStreamConfig::SetFormat(subtype WxH@fps),
//         ICaptureGraphBuilder2::RenderStream, IMediaControl::Run, state after 1.5 s, Stop.
// Build: timing\build_kiyo_probe.bat -> timing\build\dshow_open_probe.exe
// Usage: dshow_open_probe.exe --dev <DevicePath substring> [--sub MJPG] [--w 1280 --h 720 --fps 30]
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <dshow.h>
#include <cstdio>
#include <string>
#pragma comment(lib, "strmiids.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "oleaut32.lib")
static const CLSID CLSID_NullRendererX = {0xC1F400A4, 0x3F08, 0x11D3, {0x9F, 0x0B, 0x00, 0x60, 0x08, 0x03, 0x9E, 0x37}};
static std::string hx(HRESULT v) { char b[16]; sprintf_s(b, "0x%08lX", (unsigned long)v); return b; }
static std::string w2u(const wchar_t* w) { if (!w) return {}; int n = WideCharToMultiByte(CP_UTF8, 0, w, -1, nullptr, 0, nullptr, nullptr); std::string s(n > 0 ? n - 1 : 0, '\0'); if (n > 1) WideCharToMultiByte(CP_UTF8, 0, w, -1, s.data(), n, nullptr, nullptr); return s; }
static std::string lower(std::string s) { for (auto& c : s) c = (char)tolower((unsigned char)c); return s; }
static std::string jesc(const std::string& s) { std::string o; for (char c : s) { if (c == '"' || c == '\\') { o += '\\'; o += c; } else o += c; } return o; }
template <class T> struct Com { T* p = nullptr; ~Com() { if (p) p->Release(); } T** operator&() { return &p; } T* operator->() const { return p; } operator T*() const { return p; } };

int main(int argc, char** argv) {
    std::string dev, sub = "MJPG"; int W = 1280, H = 720, FPS = 30;
    for (int i = 1; i < argc; ++i) { std::string a = argv[i]; auto nx = [&]() { return std::string(i + 1 < argc ? argv[++i] : ""); };
        if (a == "--dev") dev = nx(); else if (a == "--sub") sub = nx(); else if (a == "--w") W = atoi(nx().c_str()); else if (a == "--h") H = atoi(nx().c_str()); else if (a == "--fps") FPS = atoi(nx().c_str()); }
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    std::string js = "{\"tool\":\"dshow_open_probe\",\"dev\":\"" + jesc(dev) + "\",\"request\":\"" + sub + " " + std::to_string(W) + "x" + std::to_string(H) + "@" + std::to_string(FPS) + "\"";
    SYSTEMTIME st; GetSystemTime(&st); char tb[64]; sprintf_s(tb, ",\"utc\":\"%04d-%02d-%02dT%02d:%02d:%02dZ\"", st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond); js += tb;
    Com<ICreateDevEnum> de; CoCreateInstance(CLSID_SystemDeviceEnum, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&de));
    Com<IEnumMoniker> em; HRESULT hr = de->CreateClassEnumerator(CLSID_VideoInputDeviceCategory, &em, 0);
    Com<IBaseFilter> src; std::string path, name;
    if (hr == S_OK) for (;;) {
        IMoniker* m = nullptr; if (em->Next(1, &m, nullptr) != S_OK) break;
        Com<IPropertyBag> pb; m->BindToStorage(nullptr, nullptr, IID_PPV_ARGS(&pb));
        VARIANT v; VariantInit(&v); std::string p;
        if (pb && SUCCEEDED(pb->Read(L"DevicePath", &v, nullptr))) p = w2u(v.bstrVal); VariantClear(&v);
        if (!src.p && lower(p).find(lower(dev)) != std::string::npos) {
            if (pb && SUCCEEDED(pb->Read(L"FriendlyName", &v, nullptr))) name = w2u(v.bstrVal); VariantClear(&v);
            path = p; hr = m->BindToObject(nullptr, nullptr, IID_PPV_ARGS(&src)); js += ",\"bind_hr\":\"" + hx(hr) + "\"";
        }
        m->Release();
    }
    js += ",\"name\":\"" + jesc(name) + "\",\"device_path\":\"" + jesc(path) + "\"";
    if (!src.p) { printf("%s,\"error\":\"no device\"}\n", js.c_str()); return 3; }
    { Com<IAMCameraControl> cc; HRESULT q = src->QueryInterface(IID_PPV_ARGS(&cc)); long v = 0, f = 0; HRESULT g = cc ? cc->Get(CameraControl_Exposure, &v, &f) : q;
      js += ",\"camctl_exposure_get_hr\":\"" + hx(g) + "\",\"exposure\":" + std::to_string(v); }
    Com<IGraphBuilder> gb; CoCreateInstance(CLSID_FilterGraph, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&gb));
    Com<ICaptureGraphBuilder2> cgb; CoCreateInstance(CLSID_CaptureGraphBuilder2, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&cgb));
    cgb->SetFiltergraph(gb);
    hr = gb->AddFilter(src, L"src"); js += ",\"addfilter_hr\":\"" + hx(hr) + "\"";
    Com<IAMStreamConfig> sc; hr = cgb->FindInterface(&PIN_CATEGORY_CAPTURE, &MEDIATYPE_Video, src, IID_IAMStreamConfig, (void**)&sc);
    js += ",\"streamconfig_hr\":\"" + hx(hr) + "\"";
    bool set = false;
    if (sc.p) {
        int n = 0, sz = 0; sc->GetNumberOfCapabilities(&n, &sz); BYTE caps[256];
        for (int i = 0; i < n && !set; ++i) {
            AM_MEDIA_TYPE* mt = nullptr; if (FAILED(sc->GetStreamCaps(i, &mt, caps))) continue;
            char fc[5] = {0}; memcpy(fc, &mt->subtype.Data1, 4);
            if (mt->formattype == FORMAT_VideoInfo && sub == fc) {
                auto* vih = (VIDEOINFOHEADER*)mt->pbFormat;
                if (vih->bmiHeader.biWidth == W && vih->bmiHeader.biHeight == H) {
                    vih->AvgTimePerFrame = 10000000LL / FPS; hr = sc->SetFormat(mt); js += ",\"setformat_hr\":\"" + hx(hr) + "\",\"caps_index\":" + std::to_string(i); set = true;
                }
            }
            if (mt->cbFormat) CoTaskMemFree(mt->pbFormat); if (mt->pUnk) mt->pUnk->Release(); CoTaskMemFree(mt);
        }
        js += ",\"n_caps\":" + std::to_string(n);
    }
    if (!set) js += ",\"setformat\":\"no matching caps\"";
    Com<IBaseFilter> nr; hr = CoCreateInstance(CLSID_NullRendererX, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&nr)); js += ",\"nullrenderer_hr\":\"" + hx(hr) + "\"";
    if (nr.p) gb->AddFilter(nr, L"null");
    hr = cgb->RenderStream(&PIN_CATEGORY_CAPTURE, &MEDIATYPE_Video, src, nullptr, nr); js += ",\"renderstream_hr\":\"" + hx(hr) + "\"";
    Com<IMediaControl> mc; gb->QueryInterface(IID_PPV_ARGS(&mc));
    if (SUCCEEDED(hr)) {
        hr = mc->Run(); js += ",\"run_hr\":\"" + hx(hr) + "\"";
        OAFilterState fs = 0; HRESULT gs = mc->GetState(1500, &fs); js += ",\"getstate_hr\":\"" + hx(gs) + "\",\"state\":" + std::to_string((int)fs);
        Sleep(1500);
        Com<IMediaEvent> me; gb->QueryInterface(IID_PPV_ARGS(&me)); long ev = 0; LONG_PTR p1 = 0, p2 = 0; std::string evs = "[";
        while (me && me->GetEvent(&ev, &p1, &p2, 0) == S_OK) { char b[64]; sprintf_s(b, "%s{\"code\":%ld,\"p1\":\"%s\"}", evs.size() > 1 ? "," : "", ev, hx((HRESULT)p1).c_str()); evs += b; me->FreeEventParams(ev, p1, p2); }
        js += ",\"graph_events\":" + evs + "]";
        mc->Stop();
    }
    printf("%s}\n", js.c_str());
    return 0;
}
