// flash_timecode.cpp -- ground-truth light source for camera timing tests (Windows, D3D11 + DXGI flip model).
//
// Shows a full-screen field whose brightness follows a known pseudo-random black/white sequence that can change on
// every display refresh (hold length 2..6 refreshes, seeded PRNG). For every Present it logs the present id and level;
// every frame it also logs IDXGISwapChain::GetFrameStatistics (PresentCount, PresentRefreshCount, SyncRefreshCount,
// SyncQPCTime), which gives the QPC time of the vblank at which each present reached the screen. Cameras viewing the
// screen record a brightness time-series; timing/scripts/flash_analyze.py cross-correlates it with this log to get the
// per-frame error of every camera timestamp source, and relative offsets between cameras.
//
// Why D3D11 flip model rather than pygame/pyglet: DXGI frame statistics give the vblank QPC per present (no need to
// trust "swap returned" times), flip-model full-screen windows get independent flip so one present == one refresh,
// and QPC is the same clock the capture tool uses. (The cross-platform Python fallback is flash_timecode_py.py.)
//
// Build: timing\build_mf.bat   Usage:
//   flash_timecode.exe --out <dir> [--seconds 20] [--monitor 0] [--seed 1] [--min-hold 2] [--max-hold 6]
//                      [--gray 0] [--white 255] [--windowed]
// Writes <dir>/display.jsonl (one "present" record per Present + "stats" records) and <dir>/display.session.json.
// Press Esc to abort.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <d3d11.h>
#include <dxgi1_3.h>
#include <cstdio>
#include <cstdint>
#include <string>
#include <vector>
#include <random>
#pragma comment(lib, "d3d11.lib")
#pragma comment(lib, "dxgi.lib")
#pragma comment(lib, "user32.lib")

static int64_t g_qpf;
static int64_t qpc_ticks() { LARGE_INTEGER t; QueryPerformanceCounter(&t); return t.QuadPart; }
static int64_t ticks_ns(int64_t t) { return (int64_t)((long double)t * 1e9L / (long double)g_qpf); }

static bool g_quit = false;
static LRESULT CALLBACK WndProc(HWND h, UINT m, WPARAM w, LPARAM l) {
    if (m == WM_KEYDOWN && w == VK_ESCAPE) { g_quit = true; return 0; }
    if (m == WM_DESTROY) { g_quit = true; PostQuitMessage(0); return 0; }
    return DefWindowProcW(h, m, w, l);
}

struct Mon { RECT rc; std::wstring name; };
static BOOL CALLBACK EnumMon(HMONITOR hm, HDC, LPRECT, LPARAM p) {
    MONITORINFOEXW mi{}; mi.cbSize = sizeof(mi); GetMonitorInfoW(hm, &mi);
    ((std::vector<Mon>*)p)->push_back({mi.rcMonitor, mi.szDevice});
    return TRUE;
}

int main(int argc, char** argv) {
    LARGE_INTEGER f; QueryPerformanceFrequency(&f); g_qpf = f.QuadPart;
    std::string out; double seconds = 20; int monitor = 0; unsigned seed = 1; int min_hold = 2, max_hold = 6; int lo = 0, hi = 255; bool windowed = false;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        auto nx = [&]() { return std::string(i + 1 < argc ? argv[++i] : ""); };
        if (a == "--out") out = nx(); else if (a == "--seconds") seconds = atof(nx().c_str());
        else if (a == "--monitor") monitor = atoi(nx().c_str()); else if (a == "--seed") seed = (unsigned)atoi(nx().c_str());
        else if (a == "--min-hold") min_hold = atoi(nx().c_str()); else if (a == "--max-hold") max_hold = atoi(nx().c_str());
        else if (a == "--gray") lo = atoi(nx().c_str()); else if (a == "--white") hi = atoi(nx().c_str());
        else if (a == "--windowed") windowed = true;
        else if (a == "--list") out = "\x01";
        else { fprintf(stderr, "unknown arg %s\n", a.c_str()); return 2; }
    }
    SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
    std::vector<Mon> mons; EnumDisplayMonitors(nullptr, nullptr, EnumMon, (LPARAM)&mons);
    if (out == "\x01") {  // --list: monitors in --monitor index order
        printf("[\n");
        for (size_t i = 0; i < mons.size(); ++i) {
            char dn[64]; WideCharToMultiByte(CP_UTF8, 0, mons[i].name.c_str(), -1, dn, sizeof(dn), nullptr, nullptr);
            const RECT& r = mons[i].rc;
            printf("  {\"monitor\":%zu,\"device\":\"%s\",\"rect\":[%ld,%ld,%ld,%ld],\"primary\":%s}%s\n", i, dn + 4, r.left, r.top, r.right, r.bottom,
                   (r.left == 0 && r.top == 0) ? "true" : "false", i + 1 < mons.size() ? "," : "");
        }
        printf("]\n"); return 0;
    }
    if (out.empty()) { fprintf(stderr, "--out <dir> required\n"); return 2; }
    CreateDirectoryA(out.c_str(), nullptr);
    if (monitor < 0 || monitor >= (int)mons.size()) { fprintf(stderr, "monitor %d not found (%zu)\n", monitor, mons.size()); return 2; }
    RECT rc = mons[monitor].rc;
    if (windowed) { rc.right = rc.left + 640; rc.bottom = rc.top + 360; }
    int W = rc.right - rc.left, H = rc.bottom - rc.top;

    WNDCLASSW wc{}; wc.lpfnWndProc = WndProc; wc.hInstance = GetModuleHandleW(nullptr); wc.lpszClassName = L"flash_timecode"; wc.hCursor = nullptr;
    RegisterClassW(&wc);
    HWND hwnd = CreateWindowExW(WS_EX_TOPMOST, wc.lpszClassName, L"flash_timecode", WS_POPUP | WS_VISIBLE, rc.left, rc.top, W, H, nullptr, nullptr, wc.hInstance, nullptr);
    ShowCursor(FALSE);

    DXGI_SWAP_CHAIN_DESC sd{};
    sd.BufferCount = 2; sd.BufferDesc.Width = W; sd.BufferDesc.Height = H; sd.BufferDesc.Format = DXGI_FORMAT_B8G8R8A8_UNORM;
    sd.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT; sd.OutputWindow = hwnd; sd.SampleDesc.Count = 1; sd.Windowed = TRUE;
    sd.SwapEffect = DXGI_SWAP_EFFECT_FLIP_DISCARD; sd.Flags = DXGI_SWAP_CHAIN_FLAG_FRAME_LATENCY_WAITABLE_OBJECT;
    ID3D11Device* dev = nullptr; ID3D11DeviceContext* ctx = nullptr; IDXGISwapChain* sc = nullptr;
    HRESULT hr = D3D11CreateDeviceAndSwapChain(nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr, 0, nullptr, 0, D3D11_SDK_VERSION, &sd, &sc, &dev, nullptr, &ctx);
    if (FAILED(hr)) { fprintf(stderr, "D3D11CreateDeviceAndSwapChain 0x%08lx\n", hr); return 1; }
    IDXGISwapChain2* sc2 = nullptr; sc->QueryInterface(IID_PPV_ARGS(&sc2));
    HANDLE wait = nullptr; if (sc2) { sc2->SetMaximumFrameLatency(1); wait = sc2->GetFrameLatencyWaitableObject(); }
    ID3D11Texture2D* bb = nullptr; sc->GetBuffer(0, IID_PPV_ARGS(&bb));
    ID3D11RenderTargetView* rtv = nullptr; dev->CreateRenderTargetView(bb, nullptr, &rtv); bb->Release();

    // Output info (refresh rate)
    IDXGIOutput* outp = nullptr; sc->GetContainingOutput(&outp);
    DXGI_OUTPUT_DESC od{}; if (outp) outp->GetDesc(&od);
    DXGI_MODE_DESC md{}; md.Width = W; md.Height = H; md.Format = DXGI_FORMAT_B8G8R8A8_UNORM; DXGI_MODE_DESC best{};
    if (outp) outp->FindClosestMatchingMode(&md, &best, dev);

    std::string base = out + "\\display";
    FILE* fl = nullptr; fopen_s(&fl, (base + ".jsonl").c_str(), "wb");
    std::mt19937 rng(seed); std::uniform_int_distribution<int> hold(min_hold, max_hold);
    int level = 0, remaining = 0; int64_t t0 = qpc_ticks(); int64_t n_present = 0, disjoint = 0;
    UINT last_stats_pc = 0;
    MSG msg;
    while (!g_quit) {
        while (PeekMessageW(&msg, nullptr, 0, 0, PM_REMOVE)) { TranslateMessage(&msg); DispatchMessageW(&msg); }
        if (wait) WaitForSingleObjectEx(wait, 1000, TRUE);
        if (remaining <= 0) { level = 1 - level; remaining = hold(rng); }
        --remaining;
        float v = (level ? hi : lo) / 255.0f; float col[4] = {v, v, v, 1};
        ctx->OMSetRenderTargets(1, &rtv, nullptr);
        ctx->ClearRenderTargetView(rtv, col);
        int64_t tp = qpc_ticks();
        hr = sc->Present(1, 0);
        int64_t tp2 = qpc_ticks();
        UINT pc = 0; sc->GetLastPresentCount(&pc);
        fprintf(fl, "{\"type\":\"present\",\"i\":%lld,\"present_count\":%u,\"level\":%d,\"present_call_ns\":%lld,\"present_return_ns\":%lld,\"hr\":%ld}\n",
                n_present, pc, level, ticks_ns(tp), ticks_ns(tp2), hr);
        ++n_present;
        DXGI_FRAME_STATISTICS st{};
        HRESULT hs = sc->GetFrameStatistics(&st);
        if (SUCCEEDED(hs)) {
            if (st.PresentCount != last_stats_pc) {
                fprintf(fl, "{\"type\":\"stats\",\"present_count\":%u,\"present_refresh_count\":%u,\"sync_refresh_count\":%u,\"sync_qpc_ns\":%lld,\"queried_ns\":%lld}\n",
                        st.PresentCount, st.PresentRefreshCount, st.SyncRefreshCount, ticks_ns(st.SyncQPCTime.QuadPart), ticks_ns(qpc_ticks()));
                last_stats_pc = st.PresentCount;
            }
        } else if (hs == DXGI_ERROR_FRAME_STATISTICS_DISJOINT) { ++disjoint; fprintf(fl, "{\"type\":\"disjoint\",\"at_ns\":%lld}\n", ticks_ns(qpc_ticks())); }
        else { fprintf(fl, "{\"type\":\"stats_error\",\"hr\":%ld}\n", hs); }
        if ((qpc_ticks() - t0) / (double)g_qpf > seconds) break;
    }
    int64_t t1 = qpc_ticks();
    fclose(fl);
    FILE* fs = nullptr; fopen_s(&fs, (base + ".session.json").c_str(), "wb");
    char dn[64]; WideCharToMultiByte(CP_UTF8, 0, od.DeviceName, -1, dn, sizeof(dn), nullptr, nullptr);
    fprintf(fs, "{\"tool\":\"flash_timecode\",\"monitor_index\":%d,\"output\":\"%s\",\"rect\":[%ld,%ld,%ld,%ld],\"size\":[%d,%d],"
                "\"mode_refresh\":\"%u/%u\",\"seconds\":%.3f,\"presents\":%lld,\"disjoint\":%lld,\"seed\":%u,\"min_hold\":%d,\"max_hold\":%d,"
                "\"lo\":%d,\"hi\":%d,\"qpc_frequency\":%lld,\"windowed\":%s,\"swap_effect\":\"FLIP_DISCARD\",\"sync_interval\":1}\n",
            monitor, dn + 4, rc.left, rc.top, rc.right, rc.bottom, W, H, best.RefreshRate.Numerator, best.RefreshRate.Denominator,
            (t1 - t0) / (double)g_qpf, n_present, disjoint, seed, min_hold, max_hold, lo, hi, g_qpf, windowed ? "true" : "false");
    fclose(fs);
    fprintf(stderr, "presents=%lld disjoint=%lld seconds=%.2f\n", n_present, disjoint, (t1 - t0) / (double)g_qpf);
    return 0;
}
