/*
 * uvc_probe_quality.c -- goal 3 (USB bandwidth), phase 2: does the CAMERA lower its requested
 * dwMaxPayloadTransferSize (and/or its JPEG sizes) when the host asks for a lower wCompQuality
 * or a smaller dwMaxPayloadTransferSize in VS_PROBE_CONTROL?
 *
 * Build (Windows, after libusb/build_windows.ps1; from a vcvars64 shell):
 *   cl /nologo /O2 /DWIN32_LEAN_AND_MEAN /D_CRT_SECURE_NO_WARNINGS
 *      /I research\usb_cameras\libusb\compat\win32 /I research\usb_cameras\libusb\build\deps\libuvc\include
 *      /I research\usb_cameras\libusb\build\cmake\libuvc\include /I research\usb_cameras\libusb\build\libusb-msvc
 *      research\usb_cameras\bandwidth\libuvc_forced_alt\uvc_probe_quality.c
 *      research\usb_cameras\libusb\build\cmake\libuvc\Release\uvc.lib research\usb_cameras\libusb\build\libusb-msvc\libusb-1.0.lib
 *      /Fe:<out>\uvc_probe_quality.exe
 *   (Linux/macOS: cc -O2 ... -luvc $(pkg-config --cflags --libs libusb-1.0) -lpthread)
 *
 * Usage:
 *   uvc_probe_quality --vid 046d --pid 0843 --width 1280 --height 720 --fps 30
 *       [--quality-list 0,1,10,30,61,100,1000,5000,9999,10000]  PROBE with bmHint |= wCompQuality (D3)
 *       [--payload-list 192,512,944,1984,3072]                   PROBE asking for a smaller dwMaxPayloadTransferSize
 *       [--stream-q 61,1 --seconds 8 [--alt N]]                   COMMIT each quality and stream it (frame size stats)
 *       [--exposure-abs E] [--wb-temp K] [--focus-auto 0|1] [--focus-abs F] [--controls-only] [--out result.json]
 *   --controls-only: set/report the controls (focus etc.) and exit (no PROBE). NOTE: --stream-q streams only the
 *   FIRST value reliably; later COMMITs in the same process returned UVC_ERROR_ACCESS (-3) on the C930e -> one per run.
 * Every PROBE is SET_CUR then GET_CUR; the JSON records what was sent and what the camera returned.
 * GET_MIN/GET_MAX/GET_DEF/GET_RES of PROBE (after the base SET_CUR) are recorded too.
 * NOTE: needs the camera on a libusb-accessible driver (Windows: WinUSB). Wrap in tools/camlock.py.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>
#include "libuvc/libuvc.h"
#include "libuvc/libuvc_internal.h"
#include <libusb.h>
#ifdef _WIN32
#include <windows.h>
#define SLEEP_MS(x) Sleep(x)
#else
#include <unistd.h>
#define SLEEP_MS(x) usleep((x) * 1000)
#endif

#define MAXF 4096
typedef struct { uint32_t n, ok; uint32_t sz[MAXF]; uint32_t err; } fstats_t;

static int parse_list(const char *s, long *out, int max) {
  int n = 0;
  while (s && *s && n < max) { out[n++] = strtol(s, (char **)&s, 10); if (*s == ',') s++; }
  return n;
}
static void pctl(FILE *o, const uvc_stream_ctrl_t *c) {
  fprintf(o, "{\"bmHint\":%u,\"bFormatIndex\":%u,\"bFrameIndex\":%u,\"dwFrameInterval\":%u,\"wKeyFrameRate\":%u,"
             "\"wPFrameRate\":%u,\"wCompQuality\":%u,\"wCompWindowSize\":%u,\"wDelay\":%u,\"dwMaxVideoFrameSize\":%u,"
             "\"dwMaxPayloadTransferSize\":%u,\"dwClockFrequency\":%u,\"bmFramingInfo\":%u}",
          c->bmHint, c->bFormatIndex, c->bFrameIndex, c->dwFrameInterval, c->wKeyFrameRate, c->wPFrameRate, c->wCompQuality,
          c->wCompWindowSize, c->wDelay, c->dwMaxVideoFrameSize, c->dwMaxPayloadTransferSize, c->dwClockFrequency, c->bmFramingInfo);
}
static int cmpu(const void *a, const void *b) { uint32_t x = *(const uint32_t *)a, y = *(const uint32_t *)b; return x < y ? -1 : x > y; }
static void cb(uvc_frame_t *f, void *u) {
  fstats_t *s = (fstats_t *)u;
  const uint8_t *p = (const uint8_t *)f->data;
  size_t n = f->data_bytes;
  int ok = 0;
  if (n >= 4 && p[0] == 0xFF && p[1] == 0xD8)
    for (size_t i = n - 1; i >= 1 && i + 64 >= n; i--) if (p[i - 1] == 0xFF && p[i] == 0xD9) { ok = 1; break; }
  if (s->n < MAXF) s->sz[s->n] = (uint32_t)n;
  s->n++; s->ok += ok; s->err += f->error_payload_count;
}

int main(int argc, char **argv) {
  int vid = 0x046d, pid = 0x0843, w = 1280, h = 720, fps = 30, secs = 8, alt = 0, exp_abs = 0, wbk = 0, focus_auto = -1, focus_abs = -1, controls_only = 0;
  long ql[64], pl[64], sq[64];
  int nq = 0, np = 0, ns = 0;
  const char *outp = NULL;
  for (int i = 1; i < argc; i++) {
    const char *a = argv[i];
#define NX() (i + 1 < argc ? argv[++i] : (fprintf(stderr, "missing value for %s\n", a), exit(1), (char *)0))
    if (!strcmp(a, "--vid")) vid = (int)strtol(NX(), NULL, 16);
    else if (!strcmp(a, "--pid")) pid = (int)strtol(NX(), NULL, 16);
    else if (!strcmp(a, "--width")) w = atoi(NX());
    else if (!strcmp(a, "--height")) h = atoi(NX());
    else if (!strcmp(a, "--fps")) fps = atoi(NX());
    else if (!strcmp(a, "--seconds")) secs = atoi(NX());
    else if (!strcmp(a, "--alt")) alt = atoi(NX());
    else if (!strcmp(a, "--exposure-abs")) exp_abs = atoi(NX());
    else if (!strcmp(a, "--wb-temp")) wbk = atoi(NX());
    else if (!strcmp(a, "--quality-list")) nq = parse_list(NX(), ql, 64);
    else if (!strcmp(a, "--payload-list")) np = parse_list(NX(), pl, 64);
    else if (!strcmp(a, "--stream-q")) ns = parse_list(NX(), sq, 64);
    else if (!strcmp(a, "--out")) outp = NX();
    else if (!strcmp(a, "--focus-auto")) focus_auto = atoi(NX());
    else if (!strcmp(a, "--focus-abs")) focus_abs = atoi(NX());
    else if (!strcmp(a, "--controls-only")) controls_only = 1;
    else { fprintf(stderr, "unknown arg %s (see header)\n", a); return 1; }
  }
  FILE *o = outp ? fopen(outp, "w") : stdout;
  if (!o) { fprintf(stderr, "cannot write %s\n", outp); return 2; }
  uvc_context_t *ctx; uvc_device_t *dev; uvc_device_handle_t *devh;
  uvc_error_t r;
  if ((r = uvc_init(&ctx, NULL)) < 0) { uvc_perror(r, "uvc_init"); return 2; }
  if ((r = uvc_find_device(ctx, &dev, vid, pid, NULL)) < 0) { uvc_perror(r, "uvc_find_device"); return 3; }
  if ((r = uvc_open(dev, &devh)) < 0) { uvc_perror(r, "uvc_open"); return 3; }
  if (exp_abs > 0) { uvc_set_ae_mode(devh, 1); uvc_set_exposure_abs(devh, (uint32_t)exp_abs); }
  if (wbk > 0) { uvc_set_white_balance_temperature_auto(devh, 0); uvc_set_white_balance_temperature(devh, (uint16_t)wbk); }
  /* focus (UVC CT_FOCUS_AUTO / CT_FOCUS_ABSOLUTE); the camera keeps these after the process exits */
  int fa_rc = -999, fb_rc = -999;
  if (focus_auto >= 0) fa_rc = uvc_set_focus_auto(devh, (uint8_t)focus_auto);
  if (focus_abs >= 0) fb_rc = uvc_set_focus_abs(devh, (uint16_t)focus_abs);
  uint8_t fa_cur = 0; uint16_t fb_cur = 0, fb_min = 0, fb_max = 0;
  int fa_g = uvc_get_focus_auto(devh, &fa_cur, UVC_GET_CUR), fb_g = uvc_get_focus_abs(devh, &fb_cur, UVC_GET_CUR);
  uvc_get_focus_abs(devh, &fb_min, UVC_GET_MIN); uvc_get_focus_abs(devh, &fb_max, UVC_GET_MAX);
  fprintf(o, "{\"test\":\"uvc_probe_quality\",\"focus\":{\"set_auto_rc\":%d,\"set_abs_rc\":%d,\"auto_cur\":%u,\"auto_get_rc\":%d,\"abs_cur\":%u,\"abs_get_rc\":%d,\"abs_min\":%u,\"abs_max\":%u},",
          fa_rc, fb_rc, fa_cur, fa_g, fb_cur, fb_g, fb_min, fb_max);
  if (controls_only) { fprintf(o, "\"controls_only\":true}\n"); if (o != stdout) fclose(o); uvc_close(devh); uvc_unref_device(dev); uvc_exit(ctx); return 0; }
  fprintf(o, "\"command\":\"");
  for (int i = 0; i < argc; i++) {
    fputs(i ? " " : "", o);
    for (const char *c = argv[i]; *c; c++) { if (*c == '\\' || *c == '"') fputc('\\', o); fputc(*c, o); }
  }
  {
    const struct libusb_version *v = libusb_get_version();
    fprintf(o, "\",\"libusb\":\"%u.%u.%u\",\"bcdUVC\":\"%x\",\"mode\":{\"format\":\"MJPEG\",\"width\":%d,\"height\":%d,\"fps\":%d},",
            v->major, v->minor, v->micro, devh->info->ctrl_if.bcdUVC, w, h, fps);
  }
  uvc_stream_ctrl_t base;
  r = uvc_get_stream_ctrl_format_size(devh, &base, UVC_FRAME_FORMAT_MJPEG, w, h, fps);
  fprintf(o, "\"base_probe_rc\":%d,\"base_probe\":", r);
  pctl(o, &base);
  if (r < 0) { fprintf(o, "}\n"); return 4; }
  /* GET_MIN/MAX/DEF/RES of PROBE (camera state after the base SET_CUR) */
  const enum uvc_req_code reqs[] = {UVC_GET_MIN, UVC_GET_MAX, UVC_GET_DEF, UVC_GET_RES};
  const char *rn[] = {"GET_MIN", "GET_MAX", "GET_DEF", "GET_RES"};
  fprintf(o, ",\"probe_ranges\":{");
  for (int k = 0; k < 4; k++) {
    uvc_stream_ctrl_t c = base;
    int rr = uvc_query_stream_ctrl(devh, &c, 1, reqs[k]);
    fprintf(o, "%s\"%s\":{\"rc\":%d,\"ctrl\":", k ? "," : "", rn[k], rr);
    pctl(o, &c);
    fprintf(o, "}");
  }
  fprintf(o, "},\"quality_probes\":[");
  for (int k = 0; k < nq; k++) {
    uvc_stream_ctrl_t c = base, sent;
    c.bmHint = 0x0001 | 0x0008; /* keep dwFrameInterval, prefer wCompQuality */
    c.wCompQuality = (uint16_t)ql[k];
    sent = c;
    int r1 = uvc_query_stream_ctrl(devh, &c, 1, UVC_SET_CUR);
    int r2 = uvc_query_stream_ctrl(devh, &c, 1, UVC_GET_CUR);
    fprintf(o, "%s{\"requested_wCompQuality\":%ld,\"set_rc\":%d,\"get_rc\":%d,\"sent\":", k ? "," : "", ql[k], r1, r2);
    pctl(o, &sent);
    fprintf(o, ",\"returned\":");
    pctl(o, &c);
    fprintf(o, "}");
  }
  fprintf(o, "],\"payload_probes\":[");
  for (int k = 0; k < np; k++) {
    uvc_stream_ctrl_t c = base, sent;
    c.dwMaxPayloadTransferSize = (uint32_t)pl[k];
    sent = c;
    int r1 = uvc_query_stream_ctrl(devh, &c, 1, UVC_SET_CUR);
    int r2 = uvc_query_stream_ctrl(devh, &c, 1, UVC_GET_CUR);
    fprintf(o, "%s{\"requested_dwMaxPayloadTransferSize\":%ld,\"set_rc\":%d,\"get_rc\":%d,\"sent\":", k ? "," : "", pl[k], r1, r2);
    pctl(o, &sent);
    fprintf(o, ",\"returned\":");
    pctl(o, &c);
    fprintf(o, "}");
  }
  fprintf(o, "],\"streams\":[");
  for (int k = 0; k < ns; k++) {
    uvc_stream_ctrl_t c = base;
    uvc_stream_handle_t *strmh = NULL;
    static fstats_t st;
    memset(&st, 0, sizeof st);
    c.bmHint = 0x0001 | 0x0008;
    c.wCompQuality = (uint16_t)sq[k];
    int r1 = uvc_probe_stream_ctrl(devh, &c); /* SET_CUR + GET_CUR probe */
    uvc_stream_ctrl_t probed = c;
    int r2 = uvc_stream_open_ctrl(devh, &strmh, &c); /* COMMIT */
    int r3 = -99, chosen = 0, ppt = 0, ntr = 0; size_t bpp = 0;
    if (r2 >= 0) {
      uvc_stream_set_iso_override(strmh, alt, 0, 0);
      r3 = uvc_stream_start(strmh, cb, &st, 0);
      uvc_stream_get_iso_info(strmh, &chosen, &bpp, &ppt, &ntr);
      if (r3 >= 0) { SLEEP_MS(secs * 1000); uvc_stream_stop(strmh); }
      uvc_stream_close(strmh);
    }
    uint32_t m = st.n < MAXF ? st.n : MAXF;
    uint32_t med = 0, p99 = 0, mx = 0, mn = 0;
    if (m) { qsort(st.sz, m, sizeof(uint32_t), cmpu); mn = st.sz[0]; med = st.sz[m / 2]; p99 = st.sz[(m * 99) / 100 < m ? (m * 99) / 100 : m - 1]; mx = st.sz[m - 1]; }
    fprintf(o, "%s{\"requested_wCompQuality\":%ld,\"probe_rc\":%d,\"commit_rc\":%d,\"start_rc\":%d,\"probed\":", k ? "," : "", sq[k], r1, r2, r3);
    pctl(o, &probed);
    fprintf(o, ",\"alt\":%d,\"bytes_per_packet\":%zu,\"seconds\":%d,\"frames\":%u,\"fps\":%.3f,\"jpeg_soi_eoi_ok\":%u,\"error_payloads\":%u,"
               "\"bytes_min\":%u,\"bytes_median\":%u,\"bytes_p99\":%u,\"bytes_max\":%u}",
            chosen, bpp, secs, st.n, (double)st.n / secs, st.ok, st.err, mn, med, p99, mx);
    fflush(o);
  }
  fprintf(o, "]}\n");
  if (o != stdout) fclose(o);
  uvc_close(devh);
  uvc_unref_device(dev);
  uvc_exit(ctx);
  return 0;
}
