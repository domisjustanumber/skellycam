/*
 * uvc_capture_test.c - libuvc/libusb user-space UVC capture probe for the skellycam research.
 *
 * Build:   Windows: research/usb_cameras/libusb/build_windows.ps1
 *          Linux/macOS: research/usb_cameras/libusb/linux/run_libuvc_linux.sh / macos/... (they
 *          build this file with the same patched libuvc).
 * Needs:   upstream libuvc + patches/0001-frame-timing-and-iso-override.patch (for per-frame
 *          PTS/SCR/host timing and the alt-setting override). Without the patch it does not compile
 *          (LIBUVC_HAS_SKELLYCAM_PATCH guard).
 *
 * Usage:
 *   uvc_capture_test --list [--json-out FILE]
 *       Enumerate every USB device via libusb: VID/PID, bus, port path, speed, serial (read
 *       without opening when libusb >= 1.0.30 supports it, else after open), UVC yes/no, and
 *       whether libusb can open it (on Windows only WinUSB/libusbK/libusb0 devices can be).
 *       Exit code 3 + "no accessible device" when no UVC device can be opened.
 *   uvc_capture_test --vid 046d --pid 0843 [--serial S] [--port-path 1-4.2] [--index N]
 *       [--width 1280 --height 720 --fps 30] [--seconds 10]
 *       [--alt N | --min-packet-bytes B | --bandwidth-factor F] [--packets-per-transfer P]
 *       [--exposure-abs E (100us units; sets AE manual)] [--wb-temp K (sets WB manual)]
 *       [--probe-only] [--out-dir DIR] [--save-jpeg K] [--save-jpeg-deferred] [--camera-key KEY] [--frame-qpc]
 *       --controls-after-start: re-apply --exposure-abs / --wb-temp 0.5 s after streaming starts (some
 *       cameras reset controls at COMMIT) and record the read-back in result.json controls.after_start_*.
 *       --save-jpeg-deferred: keep the first K JPEGs in RAM and write them after the stream stops, so
 *       disk writes never run in the libusb event thread during capture (they would delay later
 *       transfer callbacks and bias host_*_payload_ns / host_arrival_ns). Files: frame_<seq>.jpg.
 *   uvc_capture_test --frame-qpc-only SECONDS --out-dir DIR      (Windows, no camera needed)
 *       Opens the camera, prints the PROBE/COMMIT negotiation, streams MJPEG and writes
 *       DIR/frames.jsonl (README per-frame schema + extra libuvc fields) and DIR/result.json.
 *
 * Bandwidth options (goal 3):
 *   --alt N                 force bAlternateSetting N even if its packets are smaller than the
 *                           camera's dwMaxPayloadTransferSize (libuvc would refuse / pick bigger)
 *   --min-packet-bytes B    pick the first alt with packets >= B instead of dwMaxPayloadTransferSize
 *   --bandwidth-factor F    pupil-labs/pyuvc formula (copied from Linux uvc_fixup_video_ctrl):
 *                           B = w*h/8*F * (1e7/interval + 1) / 1000 / 8 + 12  (high speed)
 *
 * Clocks: every host_* value is CLOCK_MONOTONIC in ns (QueryPerformanceCounter on Windows via
 * compat/win32/pthread.h; CLOCK_MONOTONIC on Linux and macOS).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>
#include <errno.h>
#include "libuvc/libuvc.h"
#include "libuvc/libuvc_internal.h" /* devh->info->ctrl_if.dwClockFrequency / bcdUVC */
#include <libusb.h>

#ifndef LIBUVC_HAS_SKELLYCAM_PATCH
#error "apply patches/0001-frame-timing-and-iso-override.patch to libuvc"
#endif

#ifdef _WIN32
#include <windows.h>
#include <cfgmgr32.h>
#include <direct.h>
#define MKDIR(p) _mkdir(p)
#define PLATFORM_NAME "windows"
#else
#include <unistd.h>
#include <sys/stat.h>
#include <sys/utsname.h>
#define MKDIR(p) mkdir(p, 0755)
#ifdef __APPLE__
#define PLATFORM_NAME "macos"
#else
#define PLATFORM_NAME "linux"
#endif
#endif

#ifndef LIBUVC_GIT_COMMIT
#define LIBUVC_GIT_COMMIT "unknown"
#endif

static int64_t now_ns(void) {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return (int64_t)ts.tv_sec * 1000000000LL + ts.tv_nsec;
}

#ifdef _WIN32
/* ---- Windows: USB bus frame number <-> QPC model from the xHCI driver (--frame-qpc) ----------
 * IOCTL_USB_START_TRACKING_FOR_TIME_SYNC / IOCTL_USB_GET_FRAME_NUMBER_AND_QPC_FOR_TIME_SYNC on each
 * GUID_DEVINTERFACE_USB_HOST_CONTROLLER interface (works unprivileged; see tests/win_usb_frame_qpc.c
 * and results/windows/<host>/win_usb_frame_qpc). Sampled every 50 ms during capture so the 11-bit
 * SOF in each frame's SCR can later be mapped to QPC. */
#include <setupapi.h>
#include <initguid.h>
#include <usbiodef.h>
#include <winioctl.h>
#include <usbioctl.h>
#pragma comment(lib, "setupapi.lib")
#define MAX_HC 8
static struct { HANDLE h[MAX_HC]; HANDLE track[MAX_HC]; char path[MAX_HC][256]; int n; FILE *f; volatile LONG stop; HANDLE thr; LARGE_INTEGER qpf; } g_fq;

static int64_t qpc_to_ns(LONGLONG c) {
  return (int64_t)(c / g_fq.qpf.QuadPart) * 1000000000LL + (int64_t)((c % g_fq.qpf.QuadPart) * 1000000000LL / g_fq.qpf.QuadPart);
}

static DWORD WINAPI frame_qpc_thread(LPVOID unused) {
  (void)unused;
  while (!g_fq.stop) {
    for (int i = 0; i < g_fq.n; i++) {
      USB_FRAME_NUMBER_AND_QPC_FOR_TIME_SYNC_INFORMATION q;
      DWORD br = 0;
      memset(&q, 0, sizeof q);
      q.TimeTrackingHandle = g_fq.track[i];
      int64_t t0 = now_ns();
      BOOL ok = DeviceIoControl(g_fq.h[i], IOCTL_USB_GET_FRAME_NUMBER_AND_QPC_FOR_TIME_SYNC, &q, sizeof q, &q, sizeof q, &br, NULL);
      int64_t t1 = now_ns();
      if (ok)
        fprintf(g_fq.f, "{\"hc\":%d,\"call_before_ns\":%lld,\"call_after_ns\":%lld,\"usb_frame\":%lu,\"hw_frame\":%lu,\"uframe\":%lu,"
                        "\"frame_qpc_ns\":%lld,\"accuracy_us\":%lu,\"generation\":%lu}\n",
                i, (long long)t0, (long long)t1, q.CurrentUSBFrameNumber, q.CurrentHardwareFrameNumber,
                q.CurrentHardwareMicroFrameNumber, (long long)qpc_to_ns(q.CurrentQueryPerformanceCounter.QuadPart),
                q.PredictedAccuracyInMicroSeconds, q.CurrentGenerationID);
    }
    Sleep(50);
  }
  return 0;
}

static int frame_qpc_start(const char *out_path) {
  HDEVINFO di = SetupDiGetClassDevsA(&GUID_DEVINTERFACE_USB_HOST_CONTROLLER, NULL, NULL, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE);
  SP_DEVICE_INTERFACE_DATA ifd;
  QueryPerformanceFrequency(&g_fq.qpf);
  g_fq.f = fopen(out_path, "w");
  if (!g_fq.f) return -1;
  ifd.cbSize = sizeof ifd;
  for (DWORD i = 0; g_fq.n < MAX_HC && SetupDiEnumDeviceInterfaces(di, NULL, &GUID_DEVINTERFACE_USB_HOST_CONTROLLER, i, &ifd); i++) {
    char buf[1024];
    SP_DEVICE_INTERFACE_DETAIL_DATA_A *d = (SP_DEVICE_INTERFACE_DETAIL_DATA_A *)buf;
    USB_START_TRACKING_FOR_TIME_SYNC_INFORMATION st;
    DWORD br = 0;
    d->cbSize = sizeof(*d);
    if (!SetupDiGetDeviceInterfaceDetailA(di, &ifd, d, sizeof buf, NULL, NULL)) continue;
    HANDLE h = CreateFileA(d->DevicePath, GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);
    if (h == INVALID_HANDLE_VALUE) continue;
    memset(&st, 0, sizeof st);
    if (!DeviceIoControl(h, IOCTL_USB_START_TRACKING_FOR_TIME_SYNC, &st, sizeof st, &st, sizeof st, &br, NULL)) { CloseHandle(h); continue; }
    g_fq.h[g_fq.n] = h;
    g_fq.track[g_fq.n] = st.TimeTrackingHandle;
    snprintf(g_fq.path[g_fq.n], sizeof g_fq.path[0], "%s", d->DevicePath);
    fprintf(g_fq.f, "{\"hc\":%d,\"path\":\"", g_fq.n);
    for (const char *p = d->DevicePath; *p; p++) { if (*p == '\\' || *p == '"') fputc('\\', g_fq.f); fputc(*p, g_fq.f); }
    fprintf(g_fq.f, "\",\"qpc_frequency\":%lld}\n", g_fq.qpf.QuadPart);
    g_fq.n++;
  }
  SetupDiDestroyDeviceInfoList(di);
  g_fq.stop = 0;
  g_fq.thr = CreateThread(NULL, 0, frame_qpc_thread, NULL, 0, NULL);
  return g_fq.n;
}

static void frame_qpc_stop(void) {
  if (!g_fq.f) return;
  InterlockedExchange(&g_fq.stop, 1);
  if (g_fq.thr) { WaitForSingleObject(g_fq.thr, 2000); CloseHandle(g_fq.thr); }
  for (int i = 0; i < g_fq.n; i++) {
    USB_STOP_TRACKING_FOR_TIME_SYNC_INFORMATION sp;
    DWORD br = 0;
    sp.TimeTrackingHandle = g_fq.track[i];
    DeviceIoControl(g_fq.h[i], IOCTL_USB_STOP_TRACKING_FOR_TIME_SYNC, &sp, sizeof sp, NULL, 0, &br, NULL);
    CloseHandle(g_fq.h[i]);
  }
  fclose(g_fq.f);
  g_fq.f = NULL;
}
#endif

static void utc_now_iso(char *buf, size_t n) {
  time_t t = time(NULL);
  struct tm tmv;
#ifdef _WIN32
  gmtime_s(&tmv, &t);
#else
  gmtime_r(&t, &tmv);
#endif
  strftime(buf, n, "%Y-%m-%dT%H:%M:%SZ", &tmv);
}

static void get_hostname(char *buf, size_t n) {
#ifdef _WIN32
  DWORD sz = (DWORD)n;
  if (!GetComputerNameA(buf, &sz)) snprintf(buf, n, "unknown");
#else
  if (gethostname(buf, n) != 0) snprintf(buf, n, "unknown");
#endif
}

/* JSON string escaper into a static rotating buffer (enough for our short strings). */
static const char *js(const char *s) {
  static char bufs[8][1024];
  static int k = 0;
  char *o = bufs[k = (k + 1) % 8];
  size_t j = 0;
  if (!s) return "null";
  o[j++] = '"';
  for (; *s && j < sizeof(bufs[0]) - 8; s++) {
    unsigned char c = (unsigned char)*s;
    if (c == '"' || c == '\\') { o[j++] = '\\'; o[j++] = (char)c; }
    else if (c < 0x20) { j += (size_t)snprintf(o + j, 8, "\\u%04x", c); }
    else o[j++] = (char)c;
  }
  o[j++] = '"';
  o[j] = 0;
  return o;
}

static const char *speed_name(int s) {
  switch (s) {
  case LIBUSB_SPEED_LOW: return "low";
  case LIBUSB_SPEED_FULL: return "full";
  case LIBUSB_SPEED_HIGH: return "high";
  case LIBUSB_SPEED_SUPER: return "super";
  case LIBUSB_SPEED_SUPER_PLUS: return "super_plus";
  default: return "unknown";
  }
}

static int port_path_str(libusb_device *dev, char *out, size_t n) {
  uint8_t ports[16];
  int np = libusb_get_port_numbers(dev, ports, (int)sizeof(ports));
  size_t j = 0;
  out[0] = 0;
  j += (size_t)snprintf(out, n, "%u", libusb_get_bus_number(dev));
  for (int i = 0; i < np && j < n; i++)
    j += (size_t)snprintf(out + j, n - j, "%s%u", i == 0 ? "-" : ".", ports[i]);
  return np;
}

static int has_uvc_interface(libusb_device *dev, int *n_vs_alts) {
  struct libusb_config_descriptor *cfg = NULL;
  int uvc = 0;
  *n_vs_alts = 0;
  if (libusb_get_active_config_descriptor(dev, &cfg) != 0 &&
      libusb_get_config_descriptor(dev, 0, &cfg) != 0)
    return 0;
  for (int i = 0; i < cfg->bNumInterfaces; i++) {
    const struct libusb_interface *itf = &cfg->interface[i];
    if (itf->num_altsetting < 1) continue;
    const struct libusb_interface_descriptor *a = &itf->altsetting[0];
    if (a->bInterfaceClass == 0x0e && a->bInterfaceSubClass == 0x01) uvc = 1;
    if (a->bInterfaceClass == 0x0e && a->bInterfaceSubClass == 0x02 && itf->num_altsetting > *n_vs_alts)
      *n_vs_alts = itf->num_altsetting;
  }
  libusb_free_config_descriptor(cfg);
  return uvc;
}

/* Serial number: libusb >= 1.0.30 can read cached strings without opening (LIBUSB_API_VERSION
 * 0x0100010C). Returns source in *how. */
static void get_serial(libusb_device *dev, libusb_device_handle *h, const struct libusb_device_descriptor *dd,
                       char *out, int n, const char **how) {
  out[0] = 0;
  *how = "none";
#if defined(LIBUSB_API_VERSION) && (LIBUSB_API_VERSION >= 0x0100010C)
  {
    int r = libusb_get_device_string(dev, LIBUSB_DEVICE_STRING_SERIAL_NUMBER, out, n);
    if (r > 0) { out[r < n ? r : n - 1] = 0; *how = "libusb_get_device_string(no open)"; return; }
    out[0] = 0;
  }
#else
  (void)dev;
#endif
  if (h && dd->iSerialNumber) {
    int r = libusb_get_string_descriptor_ascii(h, dd->iSerialNumber, (unsigned char *)out, n);
    if (r > 0) { out[r] = 0; *how = "string descriptor (opened)"; return; }
    out[0] = 0;
  }
}

/* manufacturer/product strings without opening (libusb >= 1.0.30), JSON-quoted or null */
static const char *str_or_null(libusb_device *dev, int which) {
#if defined(LIBUSB_API_VERSION) && (LIBUSB_API_VERSION >= 0x0100010C)
  char b[256];
  int r = libusb_get_device_string(dev, (enum libusb_device_string_type)which, b, (int)sizeof b);
  if (r > 0) { b[r < (int)sizeof b ? r : (int)sizeof b - 1] = 0; return js(b); }
#else
  (void)dev; (void)which;
#endif
  return "null";
}

#ifdef _WIN32
static void win_devinst_info(libusb_device *dev, char *inst, size_t ninst, char *loc, size_t nloc) {
  inst[0] = 0; loc[0] = 0;
#if defined(LIBUSB_API_VERSION) && (LIBUSB_API_VERSION >= 0x0100010C)
  {
    DEVINST di = (DEVINST)libusb_get_session_data(dev);
    WCHAR wloc[1024];
    ULONG len = sizeof(wloc);
    ULONG type = 0;
    if (CM_Get_Device_IDA(di, inst, (ULONG)ninst, 0) != CR_SUCCESS) inst[0] = 0;
    /* REG_MULTI_SZ; first string is the PCIROOT(..)#PCI(..)#USBROOT(..)#USB(..) path */
    if (CM_Get_DevNode_Registry_PropertyW(di, CM_DRP_LOCATION_PATHS, &type, wloc, &len, 0) == CR_SUCCESS)
      WideCharToMultiByte(CP_UTF8, 0, wloc, -1, loc, (int)nloc, NULL, NULL);
    else
      loc[0] = 0;
  }
#else
  (void)dev;
#endif
}
#endif

/* ------------------------------------------------------------------------------------- */
static int do_list(const char *json_out) {
  libusb_context *ctx = NULL;
  libusb_device **list = NULL;
  FILE *jf = NULL;
  int n, n_uvc = 0, n_uvc_open = 0;
#if defined(LIBUSB_API_VERSION) && (LIBUSB_API_VERSION >= 0x0100010A)
  if (libusb_init_context(&ctx, NULL, 0) != 0) { fprintf(stderr, "libusb_init failed\n"); return 2; }
#else
  if (libusb_init(&ctx) != 0) { fprintf(stderr, "libusb_init failed\n"); return 2; }
#endif
  n = (int)libusb_get_device_list(ctx, &list);
  if (n < 0) { fprintf(stderr, "libusb_get_device_list: %s\n", libusb_error_name(n)); return 2; }
  if (json_out) {
    jf = fopen(json_out, "w");
    if (!jf) { fprintf(stderr, "cannot write %s\n", json_out); return 2; }
    const struct libusb_version *v = libusb_get_version();
    char host[256], utc[64];
    get_hostname(host, sizeof host);
    utc_now_iso(utc, sizeof utc);
    fprintf(jf, "{\"test\":\"libuvc_list\",\"platform\":\"%s\",\"hostname\":%s,\"utc_started\":\"%s\","
                "\"environment\":{\"libusb\":\"%u.%u.%u.%u%s\",\"libuvc_commit\":\"%s\"},\"devices\":[",
            PLATFORM_NAME, js(host), utc, v->major, v->minor, v->micro, v->nano, v->rc, LIBUVC_GIT_COMMIT);
  }
  printf("%-9s %-14s %-6s %-10s %-4s %-5s %-34s %s\n", "VID:PID", "port_path", "addr", "speed", "uvc", "vsalt", "serial", "open");
  for (int i = 0; i < n; i++) {
    libusb_device *dev = list[i];
    struct libusb_device_descriptor dd;
    libusb_device_handle *h = NULL;
    char pp[64], serial[256];
    const char *serial_how;
    int vs_alts = 0;
    if (libusb_get_device_descriptor(dev, &dd) != 0) continue;
    int uvc = has_uvc_interface(dev, &vs_alts);
    int orc = LIBUSB_ERROR_NOT_SUPPORTED;
    if (uvc) {
      n_uvc++;
      orc = libusb_open(dev, &h);
      if (orc == 0) n_uvc_open++;
    }
    port_path_str(dev, pp, sizeof pp);
    get_serial(dev, h, &dd, serial, (int)sizeof serial, &serial_how);
    printf("%04x:%04x %-14s %-6u %-10s %-4s %-5d %-34s %s\n", dd.idVendor, dd.idProduct, pp,
           libusb_get_device_address(dev), speed_name(libusb_get_device_speed(dev)), uvc ? "yes" : "no",
           vs_alts, serial[0] ? serial : "-", uvc ? (orc == 0 ? "OK" : libusb_error_name(orc)) : "(not tried)");
    if (jf) {
      char inst[512] = "", loc[1024] = "";
#ifdef _WIN32
      win_devinst_info(dev, inst, sizeof inst, loc, sizeof loc);
#endif
      fprintf(jf, "%s{\"vid\":\"%04x\",\"pid\":\"%04x\",\"bus\":%u,\"port_path\":\"%s\",\"address\":%u,"
                  "\"speed\":\"%s\",\"is_uvc\":%s,\"vs_altsettings\":%d,\"serial\":%s,\"serial_source\":\"%s\","
                  "\"open_result\":%s,\"windows_instance_id\":%s,\"windows_location_path\":%s,"
                  "\"iManufacturer\":%u,\"iProduct\":%u,\"iSerialNumber\":%u,\"bcdDevice\":\"%04x\",\"manufacturer\":%s,\"product\":%s}",
              i ? "," : "", dd.idVendor, dd.idProduct, libusb_get_bus_number(dev), pp, libusb_get_device_address(dev),
              speed_name(libusb_get_device_speed(dev)), uvc ? "true" : "false", vs_alts,
              serial[0] ? js(serial) : "null", serial_how,
              uvc ? js(orc == 0 ? "OK" : libusb_error_name(orc)) : "null",
              inst[0] ? js(inst) : "null", loc[0] ? js(loc) : "null",
              dd.iManufacturer, dd.iProduct, dd.iSerialNumber, dd.bcdDevice,
              str_or_null(dev, 0 /* MANUFACTURER */), str_or_null(dev, 1 /* PRODUCT */));
    }
    if (h) libusb_close(h);
  }
  printf("\nUVC devices seen: %d, openable by libusb: %d\n", n_uvc, n_uvc_open);
  if (n_uvc_open == 0)
    printf("no accessible device: no UVC device is bound to a libusb-compatible driver "
           "(Windows: WinUSB/libusbK; Linux: permissions; macOS: kernel driver ownership)\n");
  if (jf) {
    fprintf(jf, "],\"uvc_devices\":%d,\"uvc_openable\":%d}\n", n_uvc, n_uvc_open);
    fclose(jf);
  }
  libusb_free_device_list(list, 1);
  libusb_exit(ctx);
  return n_uvc_open ? 0 : 3;
}

/* ------------------------------------------------------------------------------------- */
typedef struct {
  FILE *jsonl;
  const char *out_dir;
  char camera_key[256];
  uint32_t clock_hz;
  int save_jpeg;
  int saved;
  int deferred;
  uint8_t **dbuf; size_t *dlen; uint32_t *dseq;
  uint64_t frames, jpeg_ok, err_payloads, eof_closed, with_pts, with_scr;
  uint32_t first_seq, last_seq, seq_gaps;
  int64_t first_arrival, last_arrival;
  uint64_t bytes;
} cap_state_t;

static int jpeg_soi_eoi(const uint8_t *p, size_t n) {
  if (n < 4 || p[0] != 0xFF || p[1] != 0xD8) return 0;
  /* some cameras pad after EOI; search the last 64 bytes */
  for (size_t i = n - 1; i >= 1 && i + 64 >= n; i--)
    if (p[i - 1] == 0xFF && p[i] == 0xD9) return 1;
  return 0;
}

static void frame_cb(uvc_frame_t *f, void *user) {
  cap_state_t *st = (cap_state_t *)user;
  int64_t arrival = now_ns();
  int ok = (f->frame_format == UVC_FRAME_FORMAT_MJPEG) ? jpeg_soi_eoi((const uint8_t *)f->data, f->data_bytes) : -1;
  int64_t os_ts = (int64_t)f->capture_time_finished.tv_sec * 1000000000LL + f->capture_time_finished.tv_nsec;

  if (st->frames == 0) { st->first_seq = f->sequence; st->first_arrival = arrival; }
  else if (f->sequence != st->last_seq + 1) st->seq_gaps += f->sequence - st->last_seq - 1;
  st->last_seq = f->sequence;
  st->last_arrival = arrival;
  st->frames++;
  st->bytes += f->data_bytes;
  if (ok == 1) st->jpeg_ok++;
  st->err_payloads += f->error_payload_count;
  st->eof_closed += f->closed_by_eof;
  st->with_pts += f->has_pts;
  st->with_scr += f->has_scr;

  if (st->jsonl) {
    char pts_s[16] = "null", stc_s[16] = "null", sof_s[8] = "null", stc1_s[16] = "null", sof1_s[8] = "null";
    if (f->has_pts) snprintf(pts_s, sizeof pts_s, "%u", f->pts);
    if (f->has_scr) {
      snprintf(stc_s, sizeof stc_s, "%u", f->scr_stc_last);
      snprintf(sof_s, sizeof sof_s, "%u", f->scr_sof_last);
      snprintf(stc1_s, sizeof stc1_s, "%u", f->scr_stc_first);
      snprintf(sof1_s, sizeof sof1_s, "%u", f->scr_sof_first);
    }
    fprintf(st->jsonl,
            "{\"camera_key\":%s,\"backend\":\"libuvc\",\"seq\":%u,\"host_arrival_ns\":%lld,"
            "\"os_timestamp_ns\":%lld,\"os_timestamp_source\":\"libuvc capture_time_finished: CLOCK_MONOTONIC when the closing payload was processed in the libusb event thread\","
            "\"uvc_pts\":%s,\"uvc_scr_stc\":%s,\"uvc_scr_sof\":%s,\"device_clock_hz\":%u,"
            "\"payload_bytes\":%zu,\"is_valid_jpeg\":%s,\"jpeg_check\":\"soi_eoi_only\","
            "\"uvc_scr_stc_first\":%s,\"uvc_scr_sof_first\":%s,\"host_first_payload_ns\":%lld,\"host_last_payload_ns\":%lld,"
            "\"first_payload_packet_idx\":%d,\"last_payload_packet_idx\":%d,\"packets_per_transfer\":%d,"
            "\"payload_count\":%u,\"error_payload_count\":%u,\"closed_by_eof\":%s,\"fid\":%u,\"width\":%u,\"height\":%u}\n",
            js(st->camera_key), f->sequence, (long long)arrival, (long long)os_ts,
            pts_s, stc_s, sof_s, st->clock_hz, f->data_bytes,
            ok < 0 ? "null" : (ok ? "true" : "false"),
            stc1_s, sof1_s, (long long)f->host_first_payload_ns, (long long)f->host_last_payload_ns,
            f->first_payload_packet_idx, f->last_payload_packet_idx, f->packets_per_transfer,
            f->payload_count, f->error_payload_count, f->closed_by_eof ? "true" : "false", f->fid,
            f->width, f->height);
  }
  if (st->out_dir && st->saved < st->save_jpeg && ok == 1 && st->deferred && st->dbuf) {
    uint8_t *b = (uint8_t *)malloc(f->data_bytes);
    if (b) { memcpy(b, f->data, f->data_bytes); st->dbuf[st->saved] = b; st->dlen[st->saved] = f->data_bytes; st->dseq[st->saved] = f->sequence; st->saved++; }
  } else if (st->out_dir && st->saved < st->save_jpeg && ok == 1) {
    char p[1024];
    snprintf(p, sizeof p, "%s/frame_%05u.jpg", st->out_dir, f->sequence);
    FILE *jf = fopen(p, "wb");
    if (jf) { fwrite(f->data, 1, f->data_bytes, jf); fclose(jf); st->saved++; }
  }
}

typedef struct {
  int vid, pid, index;
  const char *serial, *port_path, *out_dir, *camera_key;
  int width, height, fps, seconds;
  int alt, packets_per_transfer, probe_only, save_jpeg, save_jpeg_deferred;
  long min_packet_bytes;
  double bandwidth_factor;
  int exposure_abs, wb_temp;
  int frame_qpc;          /* Windows: sample USB frame<->QPC model during capture */
  int controls_after_start; /* re-apply --exposure-abs/--wb-temp 0.5 s after the stream started */
  int frame_qpc_only_s;   /* Windows: only run the sampler for N seconds (no camera) */
} opts_t;

static void print_ctrl(FILE *o, const char *name, const uvc_stream_ctrl_t *c) {
  fprintf(o, "\"%s\":{\"bmHint\":%u,\"bFormatIndex\":%u,\"bFrameIndex\":%u,\"dwFrameInterval\":%u,"
             "\"wKeyFrameRate\":%u,\"wPFrameRate\":%u,\"wCompQuality\":%u,\"wCompWindowSize\":%u,\"wDelay\":%u,"
             "\"dwMaxVideoFrameSize\":%u,\"dwMaxPayloadTransferSize\":%u,\"dwClockFrequency\":%u,"
             "\"bmFramingInfo\":%u,\"bPreferredVersion\":%u,\"bMinVersion\":%u,\"bMaxVersion\":%u,\"bInterfaceNumber\":%u}",
          name, c->bmHint, c->bFormatIndex, c->bFrameIndex, c->dwFrameInterval, c->wKeyFrameRate, c->wPFrameRate,
          c->wCompQuality, c->wCompWindowSize, c->wDelay, c->dwMaxVideoFrameSize, c->dwMaxPayloadTransferSize,
          c->dwClockFrequency, c->bmFramingInfo, c->bPreferredVersion, c->bMinVersion, c->bMaxVersion,
          c->bInterfaceNumber);
}

static void dump_alts(FILE *o, libusb_device *dev, int vs_ifnum) {
  struct libusb_config_descriptor *cfg = NULL;
  fprintf(o, "\"vs_altsettings\":[");
  if (libusb_get_active_config_descriptor(dev, &cfg) == 0) {
    int first = 1;
    for (int i = 0; i < cfg->bNumInterfaces; i++) {
      const struct libusb_interface *itf = &cfg->interface[i];
      for (int a = 0; a < itf->num_altsetting; a++) {
        const struct libusb_interface_descriptor *d = &itf->altsetting[a];
        if (d->bInterfaceNumber != vs_ifnum) continue;
        for (int e = 0; e < d->bNumEndpoints; e++) {
          const struct libusb_endpoint_descriptor *ep = &d->endpoint[e];
          int mps = ep->wMaxPacketSize;
          int bytes = (mps & 0x7ff) * (((mps >> 11) & 3) + 1);
          struct libusb_ss_endpoint_companion_descriptor *comp = NULL;
          if (libusb_get_ss_endpoint_companion_descriptor(NULL, ep, &comp) == 0 && comp) {
            bytes = comp->wBytesPerInterval;
            libusb_free_ss_endpoint_companion_descriptor(comp);
          }
          fprintf(o, "%s{\"alt\":%u,\"ep\":%u,\"type\":%u,\"wMaxPacketSize\":%u,\"bytes_per_interval\":%d,\"bInterval\":%u}",
                  first ? "" : ",", d->bAlternateSetting, ep->bEndpointAddress, ep->bmAttributes & 3, mps, bytes, ep->bInterval);
          first = 0;
        }
      }
    }
    libusb_free_config_descriptor(cfg);
  }
  fprintf(o, "]");
}

static int match_port_path(libusb_device *dev, const char *want) {
  char pp[64];
  port_path_str(dev, pp, sizeof pp);
  return strcmp(pp, want) == 0;
}

static int do_capture(const opts_t *o, int argc, char **argv) {
  uvc_context_t *ctx = NULL;
  uvc_device_t **devs = NULL, *dev = NULL;
  uvc_device_handle_t *devh = NULL;
  uvc_stream_handle_t *strmh = NULL;
  uvc_stream_ctrl_t probe, commit;
  uvc_error_t r;
  cap_state_t st;
  FILE *res = stdout;
  char resp[1024], jp[1024], host[256], utc[64];
  int rc = 0, idx = 0;

  memset(&st, 0, sizeof st);
  get_hostname(host, sizeof host);
  utc_now_iso(utc, sizeof utc);

  if ((r = uvc_init(&ctx, NULL)) < 0) { uvc_perror(r, "uvc_init"); return 2; }
  if ((r = uvc_get_device_list(ctx, &devs)) < 0) { uvc_perror(r, "uvc_get_device_list"); return 2; }
  for (int i = 0; devs[i]; i++) {
    uvc_device_descriptor_t *d = NULL;
    libusb_device *ud = libusb_ref_device(((struct uvc_device *)devs[i])->usb_dev);
    if (uvc_get_device_descriptor(devs[i], &d) != UVC_SUCCESS) { libusb_unref_device(ud); continue; }
    int ok = (!o->vid || d->idVendor == o->vid) && (!o->pid || d->idProduct == o->pid) &&
             (!o->serial || (d->serialNumber && strcmp(d->serialNumber, o->serial) == 0)) &&
             (!o->port_path || match_port_path(ud, o->port_path));
    uvc_free_device_descriptor(d);
    libusb_unref_device(ud);
    if (ok && idx++ == o->index) { dev = devs[i]; uvc_ref_device(dev); break; }
  }
  uvc_free_device_list(devs, 1);
  if (!dev) {
    fprintf(stderr, "no matching UVC device (vid=%04x pid=%04x serial=%s port=%s index=%d)\n",
            o->vid, o->pid, o->serial ? o->serial : "*", o->port_path ? o->port_path : "*", o->index);
    uvc_exit(ctx);
    return 3;
  }
  r = uvc_open(dev, &devh);
  if (r < 0) {
    fprintf(stderr, "no accessible device: uvc_open failed: %s (%d). On Windows the camera must be on "
                    "WinUSB/libusbK (see winusb/), on Linux check udev permissions, on macOS see macos/.\n",
            uvc_strerror(r), r);
    uvc_unref_device(dev);
    uvc_exit(ctx);
    return 3;
  }

  libusb_device *udev = libusb_get_device(uvc_get_libusb_handle(devh));
  uvc_device_descriptor_t *dd = NULL;
  uvc_get_device_descriptor(dev, &dd);
  char pp[64];
  port_path_str(udev, pp, sizeof pp);
  if (o->camera_key) snprintf(st.camera_key, sizeof st.camera_key, "%s", o->camera_key);
  else if (dd && dd->serialNumber && dd->serialNumber[0])
    snprintf(st.camera_key, sizeof st.camera_key, "usb:%04x:%04x:sn:%s", dd->idVendor, dd->idProduct, dd->serialNumber);
  else
    snprintf(st.camera_key, sizeof st.camera_key, "usb:%04x:%04x:port:%s", dd ? dd->idVendor : 0, dd ? dd->idProduct : 0, pp);
  st.clock_hz = devh->info->ctrl_if.dwClockFrequency;

  /* manual exposure / WB (record what the camera reports back) */
  int ae_set = -999, exp_set = -999, wb_auto_set = -999, wb_set = -999;
  uint8_t ae_mode = 0; uint32_t exp_abs = 0; uint8_t wb_auto = 0; uint16_t wb = 0;
  if (o->exposure_abs > 0) {
    ae_set = uvc_set_ae_mode(devh, 1); /* 1 = manual */
    exp_set = uvc_set_exposure_abs(devh, (uint32_t)o->exposure_abs);
  }
  if (o->wb_temp > 0) {
    wb_auto_set = uvc_set_white_balance_temperature_auto(devh, 0);
    wb_set = uvc_set_white_balance_temperature(devh, (uint16_t)o->wb_temp);
  }
  int ae_get = uvc_get_ae_mode(devh, &ae_mode, UVC_GET_CUR);
  int exp_get = uvc_get_exposure_abs(devh, &exp_abs, UVC_GET_CUR);
  int wba_get = uvc_get_white_balance_temperature_auto(devh, &wb_auto, UVC_GET_CUR);
  int wb_get = uvc_get_white_balance_temperature(devh, &wb, UVC_GET_CUR);

  r = uvc_get_stream_ctrl_format_size(devh, &probe, UVC_FRAME_FORMAT_MJPEG, o->width, o->height, o->fps);
  if (r < 0) {
    uvc_perror(r, "uvc_get_stream_ctrl_format_size (MJPEG mode not available?)");
    rc = 4;
    goto out;
  }
  r = uvc_stream_open_ctrl(devh, &strmh, &probe); /* sends COMMIT */
  if (r < 0) { uvc_perror(r, "uvc_stream_open_ctrl"); rc = 4; goto out; }
  uvc_stream_get_current_ctrl(strmh, &commit);

  size_t min_bytes = o->min_packet_bytes > 0 ? (size_t)o->min_packet_bytes : 0;
  if (o->bandwidth_factor > 0) {
    /* pupil-labs libuvc fork (stream.c) == Linux uvc_fixup_video_ctrl with bpp replaced by factor */
    double b = (double)o->width * o->height / 8.0 * o->bandwidth_factor;
    b *= 10000000.0 / commit.dwFrameInterval + 1;
    b /= 1000.0;
    if (libusb_get_device_speed(udev) >= LIBUSB_SPEED_HIGH) b /= 8.0;
    b += 12;
    min_bytes = (size_t)b;
  }
  uvc_stream_set_iso_override(strmh, o->alt, min_bytes, o->packets_per_transfer);

  if (o->out_dir) {
    MKDIR(o->out_dir);
    snprintf(jp, sizeof jp, "%s/frames.jsonl", o->out_dir);
    snprintf(resp, sizeof resp, "%s/result.json", o->out_dir);
    st.out_dir = o->out_dir;
    st.save_jpeg = o->save_jpeg;
    st.deferred = o->save_jpeg_deferred;
    if (st.deferred && st.save_jpeg > 0) {
      st.dbuf = (uint8_t **)calloc((size_t)st.save_jpeg, sizeof(uint8_t *));
      st.dlen = (size_t *)calloc((size_t)st.save_jpeg, sizeof(size_t));
      st.dseq = (uint32_t *)calloc((size_t)st.save_jpeg, sizeof(uint32_t));
    }
    if (!o->probe_only) {
      st.jsonl = fopen(jp, "w");
      if (!st.jsonl) { fprintf(stderr, "cannot write %s\n", jp); rc = 2; goto out; }
      setvbuf(st.jsonl, NULL, _IOFBF, 1 << 20);
    }
    res = fopen(resp, "w");
    if (!res) { fprintf(stderr, "cannot write %s\n", resp); rc = 2; goto out; }
  }

  int64_t t_start = 0, t_stop = 0;
  int ae2_set = -999, exp2_set = -999; uint8_t ae2_mode = 0; uint32_t exp2_abs = 0;
  int start_err = 0, chosen_alt = 0, ppt = 0, ntr = 0;
  size_t chosen_bytes = 0;
#ifdef _WIN32
  char fqp[1100];
  int n_hc = -1;
  if (o->frame_qpc && o->out_dir && !o->probe_only) {
    snprintf(fqp, sizeof fqp, "%s/usb_frame_qpc.jsonl", o->out_dir);
    n_hc = frame_qpc_start(fqp);
    fprintf(stderr, "frame-qpc sampler: %d host controllers -> %s\n", n_hc, fqp);
  }
#endif
  if (!o->probe_only) {
    t_start = now_ns();
    r = uvc_stream_start(strmh, frame_cb, &st, 0);
    if (r < 0) { start_err = r; uvc_perror(r, "uvc_stream_start"); rc = 5; }
    uvc_stream_get_iso_info(strmh, &chosen_alt, &chosen_bytes, &ppt, &ntr);
    fprintf(stderr, "streaming: alt=%d bytes/packet=%zu packets/transfer=%d transfers=%d (min_bytes override=%zu)\n",
            chosen_alt, chosen_bytes, ppt, ntr, min_bytes);
    if (r >= 0 && o->controls_after_start) {
#ifdef _WIN32
      Sleep(500);
#else
      usleep(500000);
#endif
      if (o->exposure_abs > 0) { ae2_set = uvc_set_ae_mode(devh, 1); exp2_set = uvc_set_exposure_abs(devh, (uint32_t)o->exposure_abs); }
      if (o->wb_temp > 0) { uvc_set_white_balance_temperature_auto(devh, 0); uvc_set_white_balance_temperature(devh, (uint16_t)o->wb_temp); }
      uvc_get_ae_mode(devh, &ae2_mode, UVC_GET_CUR);
      uvc_get_exposure_abs(devh, &exp2_abs, UVC_GET_CUR);
      fprintf(stderr, "controls re-applied after start: ae_set=%d exp_set=%d ae_mode=%u exposure_abs=%u\n", ae2_set, exp2_set, ae2_mode, exp2_abs);
    }
    if (r >= 0) {
      for (int s = 0; s < o->seconds * 10; s++) {
#ifdef _WIN32
        Sleep(100);
#else
        usleep(100000);
#endif
      }
      uvc_stream_stop(strmh);
    }
    t_stop = now_ns();
  }
#ifdef _WIN32
  frame_qpc_stop();
#endif
  if (st.deferred && st.dbuf) {
    for (int i = 0; i < st.saved; i++) {
      char p[1024];
      snprintf(p, sizeof p, "%s/frame_%05u.jpg", st.out_dir, st.dseq[i]);
      FILE *jf = fopen(p, "wb");
      if (jf) { fwrite(st.dbuf[i], 1, st.dlen[i], jf); fclose(jf); }
      free(st.dbuf[i]);
    }
    free(st.dbuf); free(st.dlen); free(st.dseq); st.dbuf = NULL;
  }

  /* ---- result JSON ---- */
  {
    const struct libusb_version *v = libusb_get_version();
    fprintf(res, "{\"test\":\"libuvc_capture\",\"platform\":\"%s\",\"hostname\":%s,\"utc_started\":\"%s\",\"command\":\"",
            PLATFORM_NAME, js(host), utc);
    for (int i = 0; i < argc; i++) { const char *q = js(argv[i]); fprintf(res, "%s%.*s", i ? " " : "", (int)strlen(q) - 2, q + 1); }
    fprintf(res, "\",\"environment\":{\"libusb\":\"%u.%u.%u.%u%s\",\"libuvc_commit\":\"%s\",\"libuvc_patch\":\"0001-frame-timing-and-iso-override\","
                 "\"host_clock\":\"CLOCK_MONOTONIC%s\"},",
            v->major, v->minor, v->micro, v->nano, v->rc, LIBUVC_GIT_COMMIT,
#ifdef _WIN32
            " (QueryPerformanceCounter via compat shim)"
#else
            ""
#endif
    );
    fprintf(res, "\"cameras\":[{\"camera_key\":%s,\"vid\":\"%04x\",\"pid\":\"%04x\",\"serial\":%s,\"product\":%s,"
                 "\"port_path\":\"%s\",\"speed\":\"%s\",\"bcdUVC\":\"%x\",\"dwClockFrequency_vc_header\":%u,",
            js(st.camera_key), dd ? dd->idVendor : 0, dd ? dd->idProduct : 0,
            dd && dd->serialNumber ? js(dd->serialNumber) : "null", dd && dd->product ? js(dd->product) : "null",
            pp, speed_name(libusb_get_device_speed(udev)), devh->info->ctrl_if.bcdUVC, st.clock_hz);
    dump_alts(res, udev, commit.bInterfaceNumber);
    fprintf(res, "}],\"requested\":{\"format\":\"MJPEG\",\"width\":%d,\"height\":%d,\"fps\":%d,\"seconds\":%d,"
                 "\"alt\":%d,\"min_packet_bytes\":%ld,\"bandwidth_factor\":%g,\"packets_per_transfer\":%d},",
            o->width, o->height, o->fps, o->seconds, o->alt, o->min_packet_bytes, o->bandwidth_factor, o->packets_per_transfer);
    fprintf(res, "\"controls\":{\"ae_mode_set_rc\":%d,\"exposure_abs_set_rc\":%d,\"wb_auto_set_rc\":%d,\"wb_temp_set_rc\":%d,"
                 "\"ae_mode\":%d,\"ae_mode_get_rc\":%d,\"exposure_abs_100us\":%u,\"exposure_get_rc\":%d,"
                 "\"wb_temperature_auto\":%d,\"wb_auto_get_rc\":%d,\"wb_temperature_K\":%u,\"wb_get_rc\":%d,"
                 "\"controls_after_start\":%d,\"after_start_ae_set_rc\":%d,\"after_start_exposure_set_rc\":%d,\"after_start_ae_mode\":%u,\"after_start_exposure_abs_100us\":%u},",
            ae_set, exp_set, wb_auto_set, wb_set, ae_mode, ae_get, exp_abs, exp_get, wb_auto, wba_get, wb, wb_get,
            o->controls_after_start, ae2_set, exp2_set, ae2_mode, exp2_abs);
    fprintf(res, "\"negotiation\":{");
    print_ctrl(res, "probe", &probe);
    fprintf(res, ",");
    print_ctrl(res, "commit", &commit);
    fprintf(res, "},\"iso\":{\"chosen_altsetting\":%d,\"bytes_per_packet\":%zu,\"packets_per_transfer\":%d,"
                 "\"transfers_queued\":%d,\"min_bytes_override\":%zu,\"stream_start_error\":%d,\"stream_start_error_name\":%s},",
            chosen_alt, chosen_bytes, ppt, ntr, min_bytes, start_err, start_err ? js(uvc_strerror(start_err)) : "null");
    double dur = st.frames > 1 ? (st.last_arrival - st.first_arrival) / 1e9 : 0;
    fprintf(res, "\"measurements\":{\"probe_only\":%s,\"frames\":%llu,\"wall_s\":%.3f,\"fps_from_arrivals\":%.3f,"
                 "\"seq_gaps\":%u,\"jpeg_soi_eoi_ok\":%llu,\"error_payloads\":%llu,\"frames_closed_by_eof\":%llu,"
                 "\"frames_with_pts\":%llu,\"frames_with_scr\":%llu,\"mean_frame_bytes\":%.1f,\"saved_jpegs\":%d,\"save_jpeg_deferred\":%d,"
                 "\"frames_jsonl\":%s}}\n",
            o->probe_only ? "true" : "false", (unsigned long long)st.frames, (t_stop - t_start) / 1e9,
            dur > 0 ? (st.frames - 1) / dur : 0.0, st.seq_gaps, (unsigned long long)st.jpeg_ok,
            (unsigned long long)st.err_payloads, (unsigned long long)st.eof_closed, (unsigned long long)st.with_pts,
            (unsigned long long)st.with_scr, st.frames ? (double)st.bytes / st.frames : 0.0, st.saved, st.deferred,
            (o->out_dir && !o->probe_only) ? js(jp) : "null");
  }
  fprintf(stderr, "frames=%llu jpeg_ok=%llu seq_gaps=%u error_payloads=%llu\n", (unsigned long long)st.frames,
          (unsigned long long)st.jpeg_ok, st.seq_gaps, (unsigned long long)st.err_payloads);
  if (o->out_dir) fprintf(stderr, "wrote %s\n", resp);

out:
  if (st.jsonl) fclose(st.jsonl);
  if (res && res != stdout) fclose(res);
  if (strmh) uvc_stream_close(strmh);
  if (dd) uvc_free_device_descriptor(dd);
  if (devh) uvc_close(devh);
  uvc_unref_device(dev);
  uvc_exit(ctx);
  return rc;
}

static void usage(void) {
  fprintf(stderr, "see header of uvc_capture_test.c for usage\n");
}

int main(int argc, char **argv) {
  opts_t o;
  const char *json_out = NULL;
  int list = 0;
  memset(&o, 0, sizeof o);
  o.width = 1280; o.height = 720; o.fps = 30; o.seconds = 10; o.alt = 0;
  for (int i = 1; i < argc; i++) {
    const char *a = argv[i];
#define NEXT() (i + 1 < argc ? argv[++i] : (usage(), exit(1), (char *)0))
    if (!strcmp(a, "--list")) list = 1;
    else if (!strcmp(a, "--json-out")) json_out = NEXT();
    else if (!strcmp(a, "--vid")) o.vid = (int)strtol(NEXT(), NULL, 16);
    else if (!strcmp(a, "--pid")) o.pid = (int)strtol(NEXT(), NULL, 16);
    else if (!strcmp(a, "--serial")) o.serial = NEXT();
    else if (!strcmp(a, "--port-path")) o.port_path = NEXT();
    else if (!strcmp(a, "--index")) o.index = atoi(NEXT());
    else if (!strcmp(a, "--width")) o.width = atoi(NEXT());
    else if (!strcmp(a, "--height")) o.height = atoi(NEXT());
    else if (!strcmp(a, "--fps")) o.fps = atoi(NEXT());
    else if (!strcmp(a, "--seconds")) o.seconds = atoi(NEXT());
    else if (!strcmp(a, "--alt")) o.alt = atoi(NEXT());
    else if (!strcmp(a, "--min-packet-bytes")) o.min_packet_bytes = atol(NEXT());
    else if (!strcmp(a, "--bandwidth-factor")) o.bandwidth_factor = atof(NEXT());
    else if (!strcmp(a, "--packets-per-transfer")) o.packets_per_transfer = atoi(NEXT());
    else if (!strcmp(a, "--exposure-abs")) o.exposure_abs = atoi(NEXT());
    else if (!strcmp(a, "--wb-temp")) o.wb_temp = atoi(NEXT());
    else if (!strcmp(a, "--probe-only")) o.probe_only = 1;
    else if (!strcmp(a, "--out-dir")) o.out_dir = NEXT();
    else if (!strcmp(a, "--save-jpeg")) o.save_jpeg = atoi(NEXT());
    else if (!strcmp(a, "--save-jpeg-deferred")) o.save_jpeg_deferred = 1;
    else if (!strcmp(a, "--camera-key")) o.camera_key = NEXT();
    else if (!strcmp(a, "--frame-qpc")) o.frame_qpc = 1;
    else if (!strcmp(a, "--controls-after-start")) o.controls_after_start = 1;
    else if (!strcmp(a, "--frame-qpc-only")) o.frame_qpc_only_s = atoi(NEXT());
    else { fprintf(stderr, "unknown option %s\n", a); usage(); return 1; }
  }
  if (list) return do_list(json_out);
  if (o.frame_qpc_only_s > 0) {
#ifdef _WIN32
    char p[1100];
    if (!o.out_dir) { fprintf(stderr, "--frame-qpc-only needs --out-dir\n"); return 1; }
    MKDIR(o.out_dir);
    snprintf(p, sizeof p, "%s/usb_frame_qpc.jsonl", o.out_dir);
    int n = frame_qpc_start(p);
    fprintf(stderr, "frame-qpc sampler: %d host controllers -> %s\n", n, p);
    Sleep((DWORD)o.frame_qpc_only_s * 1000);
    frame_qpc_stop();
    return n > 0 ? 0 : 3;
#else
    fprintf(stderr, "--frame-qpc-only is Windows-only\n");
    return 1;
#endif
  }
  return do_capture(&o, argc, argv);
}
