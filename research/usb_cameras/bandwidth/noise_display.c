/*
 * noise_display.c -- goal 3 worst-case JPEG load: fill one monitor with full-contrast random noise that
 * changes every refresh (high detail + high motion), so a camera viewing that monitor produces its largest
 * MJPEG frames. Windows/GDI, no dependencies. Esc closes it.
 *
 * Build (vcvars64 shell): cl /nologo /O2 research\usb_cameras\bandwidth\noise_display.c user32.lib gdi32.lib /Fe:<out>\noise_display.exe
 * Usage: noise_display.exe [--monitor 0] [--seconds 30] [--block 2] [--seed 1]
 *   --monitor  index in EnumDisplayMonitors order (same order as timing/src/flash_timecode.cpp --list)
 *   --block    noise cell size in screen pixels (default 2)
 * Prints one JSON line on exit: monitor rect, block, frames drawn, seconds.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>

typedef struct { RECT rc[16]; int n; } mons_t;
static BOOL CALLBACK enum_mon(HMONITOR hm, HDC dc, LPRECT r, LPARAM p) {
  mons_t *m = (mons_t *)p; MONITORINFO mi; (void)dc; (void)r;
  mi.cbSize = sizeof mi; GetMonitorInfoW(hm, &mi);
  if (m->n < 16) m->rc[m->n++] = mi.rcMonitor;
  return TRUE;
}
static volatile int g_quit = 0;
static LRESULT CALLBACK wndproc(HWND h, UINT msg, WPARAM w, LPARAM l) {
  if ((msg == WM_KEYDOWN && w == VK_ESCAPE) || msg == WM_DESTROY) { g_quit = 1; return 0; }
  return DefWindowProcW(h, msg, w, l);
}
int main(int argc, char **argv) {
  int monitor = 0, block = 2; double seconds = 30; unsigned seed = 1;
  for (int i = 1; i + 1 < argc; i += 2) {
    if (!strcmp(argv[i], "--monitor")) monitor = atoi(argv[i + 1]);
    else if (!strcmp(argv[i], "--seconds")) seconds = atof(argv[i + 1]);
    else if (!strcmp(argv[i], "--block")) block = atoi(argv[i + 1]);
    else if (!strcmp(argv[i], "--seed")) seed = (unsigned)atoi(argv[i + 1]);
  }
  SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
  mons_t m; m.n = 0;
  EnumDisplayMonitors(NULL, NULL, enum_mon, (LPARAM)&m);
  if (monitor < 0 || monitor >= m.n) { fprintf(stderr, "monitor %d not found (%d)\n", monitor, m.n); return 2; }
  RECT rc = m.rc[monitor];
  int W = rc.right - rc.left, H = rc.bottom - rc.top, w = W / block, h = H / block;
  WNDCLASSW wc; memset(&wc, 0, sizeof wc);
  wc.lpfnWndProc = wndproc; wc.hInstance = GetModuleHandleW(NULL); wc.lpszClassName = L"noise_display";
  RegisterClassW(&wc);
  HWND hwnd = CreateWindowExW(WS_EX_TOPMOST, wc.lpszClassName, L"noise_display", WS_POPUP | WS_VISIBLE, rc.left, rc.top, W, H, NULL, NULL, wc.hInstance, NULL);
  ShowCursor(FALSE);
  struct { BITMAPINFOHEADER h; RGBQUAD pal[256]; } bi; memset(&bi, 0, sizeof bi);
  bi.h.biSize = sizeof bi.h; bi.h.biWidth = w; bi.h.biHeight = -h; bi.h.biPlanes = 1; bi.h.biBitCount = 8; bi.h.biClrUsed = 256;
  for (int i = 0; i < 256; i++) { bi.pal[i].rgbRed = bi.pal[i].rgbGreen = bi.pal[i].rgbBlue = (BYTE)i; }
  int stride = (w + 3) & ~3;
  uint8_t *px = (uint8_t *)malloc((size_t)stride * h);
  uint32_t x = seed ? seed : 1;
  LARGE_INTEGER f, t0, t; QueryPerformanceFrequency(&f); QueryPerformanceCounter(&t0);
  long frames = 0; MSG msg; HDC dc = GetDC(hwnd);
  while (!g_quit) {
    while (PeekMessageW(&msg, NULL, 0, 0, PM_REMOVE)) { TranslateMessage(&msg); DispatchMessageW(&msg); }
    for (size_t i = 0; i < (size_t)stride * h; i++) { x ^= x << 13; x ^= x >> 17; x ^= x << 5; px[i] = (x & 1) ? 255 : 0; }
    StretchDIBits(dc, 0, 0, W, H, 0, 0, w, h, px, (BITMAPINFO *)&bi, DIB_RGB_COLORS, SRCCOPY);
    GdiFlush(); frames++;
    QueryPerformanceCounter(&t);
    if ((double)(t.QuadPart - t0.QuadPart) / f.QuadPart > seconds) break;
    Sleep(1);
  }
  QueryPerformanceCounter(&t);
  double s = (double)(t.QuadPart - t0.QuadPart) / f.QuadPart;
  printf("{\"tool\":\"noise_display\",\"monitor\":%d,\"rect\":[%ld,%ld,%ld,%ld],\"block\":%d,\"frames\":%ld,\"seconds\":%.3f,\"fps\":%.2f}\n",
         monitor, rc.left, rc.top, rc.right, rc.bottom, block, frames, s, frames / s);
  ReleaseDC(hwnd, dc); DestroyWindow(hwnd);
  return 0;
}
