/*
 * win_usb_frame_qpc.c - can an unprivileged user-mode process get (USB frame number <-> QPC) pairs
 * from the Windows USB stack, independent of which driver owns the camera?
 *
 * Why: every UVC payload header SCR carries an 11-bit USB SOF (frame) number sampled by the camera
 * together with its STC. If the host can map USB frame numbers to QueryPerformanceCounter, the
 * device clock can be mapped to host time to ~1 ms (frame) or 125 us (microframe) without relying
 * on when a transfer completion was scheduled. WinUSB has WinUsb_GetCurrentFrameNumberAndQpc (needs
 * the WinUSB interface handle, i.e. the camera on WinUSB); the hub/host-controller IOCTLs
 * IOCTL_USB_START_TRACKING_FOR_TIME_SYNC / IOCTL_USB_GET_FRAME_NUMBER_AND_QPC_FOR_TIME_SYNC
 * (usbioctl.h, Windows 10 1709+) are documented without saying who may send them. This program
 * tries them on every USB host controller (GUID_DEVINTERFACE_USB_HOST_CONTROLLER) and root/external
 * hub (GUID_DEVINTERFACE_USB_HUB) device interface and reports what happens.
 *
 * Build: research/usb_cameras/libusb/tests/build_win_tests.bat
 * Run:   research\usb_cameras\libusb\build\tests\win_usb_frame_qpc.exe <out.json>
 * Needs no camera and no admin; does not touch any USB device other than opening hub/HC handles.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <setupapi.h>
#include <initguid.h>
#include <usbiodef.h>
#include <winioctl.h>
#include <usbioctl.h>
#include <stdio.h>
#include <stdint.h>

static void jstr(FILE *f, const char *s) {
  fputc('"', f);
  for (; *s; s++) { if (*s == '"' || *s == '\\') fputc('\\', f); fputc(*s, f); }
  fputc('"', f);
}

static int try_iface(FILE *f, const char *kind, const char *path, int first) {
  HANDLE h;
  DWORD err_open = 0, br = 0;
  USB_START_TRACKING_FOR_TIME_SYNC_INFORMATION st;
  USB_FRAME_NUMBER_AND_QPC_FOR_TIME_SYNC_INFORMATION q;
  LARGE_INTEGER qpf;
  QueryPerformanceFrequency(&qpf);
  fprintf(f, "%s{\"kind\":\"%s\",\"path\":", first ? "" : ",", kind);
  jstr(f, path);
  h = CreateFileA(path, GENERIC_WRITE, FILE_SHARE_WRITE | FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
  if (h == INVALID_HANDLE_VALUE) {
    err_open = GetLastError();
    h = CreateFileA(path, 0, FILE_SHARE_WRITE | FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
  }
  if (h == INVALID_HANDLE_VALUE) {
    fprintf(f, ",\"open_error\":%lu,\"open_error_noaccess\":%lu}", err_open, GetLastError());
    return 0;
  }
  fprintf(f, ",\"opened_with\":\"%s\"", err_open ? "0 access" : "GENERIC_WRITE");
  memset(&st, 0, sizeof st);
  BOOL ok = DeviceIoControl(h, IOCTL_USB_START_TRACKING_FOR_TIME_SYNC, &st, sizeof st, &st, sizeof st, &br, NULL);
  fprintf(f, ",\"start_tracking_ok\":%s,\"start_tracking_error\":%lu", ok ? "true" : "false", ok ? 0 : GetLastError());
  if (ok) {
    /* sample current frame/QPC pairs over ~300 ms, plus a prediction for a future frame */
    fprintf(f, ",\"samples\":[");
    for (int i = 0; i < 60; i++) {
      LARGE_INTEGER t0, t1;
      memset(&q, 0, sizeof q);
      q.TimeTrackingHandle = st.TimeTrackingHandle;
      QueryPerformanceCounter(&t0);
      BOOL g = DeviceIoControl(h, IOCTL_USB_GET_FRAME_NUMBER_AND_QPC_FOR_TIME_SYNC, &q, sizeof q, &q, sizeof q, &br, NULL);
      QueryPerformanceCounter(&t1);
      if (!g) { fprintf(f, "%s{\"error\":%lu}", i ? "," : "", GetLastError()); break; }
      fprintf(f, "%s{\"qpc_before\":%lld,\"qpc_after\":%lld,\"CurrentQueryPerformanceCounter\":%lld,"
                 "\"CurrentUSBFrameNumber\":%lu,\"CurrentHardwareFrameNumber\":%lu,\"CurrentHardwareMicroFrameNumber\":%lu,"
                 "\"PredictedAccuracyInMicroSeconds\":%lu,\"CurrentGenerationID\":%lu,\"QueryPerformanceCounterFrequency\":%lld}",
              i ? "," : "", t0.QuadPart, t1.QuadPart, q.CurrentQueryPerformanceCounter.QuadPart, q.CurrentUSBFrameNumber,
              q.CurrentHardwareFrameNumber, q.CurrentHardwareMicroFrameNumber, q.PredictedAccuracyInMicroSeconds,
              q.CurrentGenerationID, q.QueryPerformanceCounterFrequency.QuadPart);
      Sleep(5);
    }
    fprintf(f, "]");
    /* QPC predicted for frame (current + 10), microframe 0 */
    memset(&q, 0, sizeof q);
    q.TimeTrackingHandle = st.TimeTrackingHandle;
    DeviceIoControl(h, IOCTL_USB_GET_FRAME_NUMBER_AND_QPC_FOR_TIME_SYNC, &q, sizeof q, &q, sizeof q, &br, NULL);
    {
      ULONG cur32 = q.CurrentUSBFrameNumber, cur11 = q.CurrentHardwareFrameNumber;
      struct { const char *name; ULONG frame; ULONG uframe; } v[] = {
        {"usb32_plus10", cur32 + 10, 0}, {"usb32_minus10", cur32 - 10, 0}, {"usb32_minus10_uf4", cur32 - 10, 4},
        {"usb32_minus500", cur32 - 500, 0}, {"usb32_current", cur32, 0},
        {"hw11_minus10", (cur11 - 10) & 0x7ff, 0}, {"hw11_plus10", (cur11 + 10) & 0x7ff, 0},
      };
      fprintf(f, ",\"input_frame_queries\":[");
      for (int k = 0; k < (int)(sizeof v / sizeof v[0]); k++) {
        memset(&q, 0, sizeof q);
        q.TimeTrackingHandle = st.TimeTrackingHandle;
        q.InputFrameNumber = v[k].frame;
        q.InputMicroFrameNumber = v[k].uframe;
        BOOL g = DeviceIoControl(h, IOCTL_USB_GET_FRAME_NUMBER_AND_QPC_FOR_TIME_SYNC, &q, sizeof q, &q, sizeof q, &br, NULL);
        fprintf(f, "%s{\"variant\":\"%s\",\"ok\":%s,\"error\":%lu,\"InputFrameNumber\":%lu,\"InputMicroFrameNumber\":%lu,"
                   "\"QpcAtInput\":%lld,\"CurrentQpc\":%lld,\"CurrentUSBFrameNumber\":%lu,\"CurrentHardwareMicroFrameNumber\":%lu}",
                k ? "," : "", v[k].name, g ? "true" : "false", g ? 0 : GetLastError(), v[k].frame, v[k].uframe,
                q.QueryPerformanceCounterAtInputFrameOrMicroFrame.QuadPart, q.CurrentQueryPerformanceCounter.QuadPart,
                q.CurrentUSBFrameNumber, q.CurrentHardwareMicroFrameNumber);
      }
      fprintf(f, "]");
    }
    USB_STOP_TRACKING_FOR_TIME_SYNC_INFORMATION sp;
    sp.TimeTrackingHandle = st.TimeTrackingHandle;
    ok = DeviceIoControl(h, IOCTL_USB_STOP_TRACKING_FOR_TIME_SYNC, &sp, sizeof sp, NULL, 0, &br, NULL);
    fprintf(f, ",\"stop_tracking_ok\":%s", ok ? "true" : "false");
  }
  fprintf(f, ",\"qpc_frequency\":%lld}", qpf.QuadPart);
  CloseHandle(h);
  return 1;
}

static int walk(FILE *f, const GUID *g, const char *kind, int first) {
  HDEVINFO di = SetupDiGetClassDevsA(g, NULL, NULL, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE);
  SP_DEVICE_INTERFACE_DATA ifd;
  ifd.cbSize = sizeof ifd;
  for (DWORD i = 0; SetupDiEnumDeviceInterfaces(di, NULL, g, i, &ifd); i++) {
    char buf[1024];
    SP_DEVICE_INTERFACE_DETAIL_DATA_A *d = (SP_DEVICE_INTERFACE_DETAIL_DATA_A *)buf;
    d->cbSize = sizeof(*d);
    if (!SetupDiGetDeviceInterfaceDetailA(di, &ifd, d, sizeof buf, NULL, NULL)) continue;
    try_iface(f, kind, d->DevicePath, first);
    first = 0;
  }
  SetupDiDestroyDeviceInfoList(di);
  return first;
}

int main(int argc, char **argv) {
  FILE *f = argc > 1 ? fopen(argv[1], "w") : stdout;
  char host[256]; DWORD hs = sizeof host;
  SYSTEMTIME t;
  if (!f) { fprintf(stderr, "cannot open %s\n", argv[1]); return 2; }
  GetComputerNameA(host, &hs);
  GetSystemTime(&t);
  fprintf(f, "{\"test\":\"win_usb_frame_qpc\",\"platform\":\"windows\",\"hostname\":\"%s\","
             "\"utc_started\":\"%04d-%02d-%02dT%02d:%02d:%02dZ\",\"command\":\"win_usb_frame_qpc.exe %s\",\"cameras\":[],\"interfaces\":[",
          host, t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute, t.wSecond, argc > 1 ? argv[1] : "");
  int first = walk(f, &GUID_DEVINTERFACE_USB_HOST_CONTROLLER, "host_controller", 1);
  walk(f, &GUID_DEVINTERFACE_USB_HUB, "hub", first);
  fprintf(f, "]}\n");
  if (f != stdout) fclose(f);
  return 0;
}
