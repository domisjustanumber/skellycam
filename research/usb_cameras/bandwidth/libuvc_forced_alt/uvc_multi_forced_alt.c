/*
 * uvc_multi_forced_alt.c -- goal 3 (USB bandwidth) DRAFT test, Linux + macOS. UNVERIFIED until run.
 *
 * Question: if the application (not the camera) chooses a SMALLER isochronous alt setting than the one the
 * camera asks for in dwMaxPayloadTransferSize, do MJPEG streams survive, and how many cameras then fit on one
 * USB bus -- with no root at run time (Linux: one-time udev rule; macOS: see below)?
 *
 * Mechanism (UPSTREAM libuvc, no patch): uvc_get_stream_ctrl_format_size() runs PROBE and returns the camera's
 * dwMaxPayloadTransferSize in the ctrl struct. libuvc's uvc_stream_open_ctrl() COMMITs that struct and copies it to
 * strmh->cur_ctrl; uvc_stream_start() then picks the FIRST alt setting whose bytes/interval >=
 * cur_ctrl.dwMaxPayloadTransferSize (src/stream.c, libuvc d07de4fa). Overwriting ctrl.dwMaxPayloadTransferSize
 * between the two calls therefore selects a smaller alt. (dwMaxPayloadTransferSize is a device-set field in
 * the UVC probe/commit structure; devices are expected to ignore the value the host sends in COMMIT.)
 * Limitation: this can only choose an alt whose size is >= the override; it relies on libuvc's assumption that
 * alts are sorted by size (true for every camera measured on Windows, see results/windows/.../bw_topology).
 *
 * Build (Linux):  sudo apt install build-essential cmake libusb-1.0-0-dev git pkg-config
 *   git clone https://github.com/libuvc/libuvc /tmp/libuvc && cd /tmp/libuvc && git checkout d07de4fa23905ee8cac06f5d24b2a03d42a3b363
 *   cmake -B build -DCMAKE_BUILD_TYPE=Release -DLIBUVC_NUM_TRANSFER_BUFS=10 -DCMAKE_INSTALL_PREFIX=$HOME/.local && cmake --build build -j && cmake --install build
 *   cc -O2 -std=c11 -o uvc_multi_forced_alt research/usb_cameras/bandwidth/libuvc_forced_alt/uvc_multi_forced_alt.c \
 *      -I$HOME/.local/include $(pkg-config --cflags --libs libusb-1.0) -L$HOME/.local/lib -luvc -lpthread -Wl,-rpath,$HOME/.local/lib
 *   (LIBUVC_NUM_TRANSFER_BUFS=10: upstream default is 100 on Linux; 100 x 32 packets x 3072 B = 9.8 MB of usbfs
 *    buffers per camera, and Linux caps usbfs at /sys/module/usbcore/parameters/usbfs_memory_mb = 16 MB by default,
 *    so a second camera would fail with an out-of-memory error before bandwidth is even tested.)
 * Build (macOS):  brew install libusb cmake pkg-config; same commands (no -lpthread needed; drop the rpath flag or use -Wl,-rpath,...).
 *
 * Permissions:
 *   Linux: one-time udev rule research/usb_cameras/libusb/linux/70-skellycam-uvc.rules (grants rw on /dev/bus/usb/BBB/DDD;
 *          libusb then detaches uvcvideo with USBDEVFS_DISCONNECT, which has no capability check). Run as a normal user.
 *   macOS: libusb_detach_kernel_driver needs root or the com.apple.vm.device-access entitlement (libusb darwin_usb.c).
 *          Run once WITHOUT sudo (records the failure) and once WITH sudo.
 *
 * Usage:
 *   uvc_multi_forced_alt [--format mjpeg|yuyv] [--size 1280x720] [--fps 30] [--seconds 8]
 *       [--override-bytes N | --override-frac F | --override-alt K] [--out FILE.json] VID:PID[:SERIAL] [VID:PID[:SERIAL] ...]
 *   Same VID:PID several times = the first, second, ... device with that VID:PID.
 *   No override  -> what libuvc would choose (= camera's request).
 *   --override-bytes N   set dwMaxPayloadTransferSize = N for every camera
 *   --override-frac F    set it to F * the camera's own request (e.g. 0.5)
 *   --override-alt K     set it to the bytes/interval of alt setting K of each camera
 *   Cameras are started one after another (ramp); each start's result is recorded, then all run together.
 * Output JSON (stdout, or --out): per camera: requested dwMaxPayloadTransferSize, override, alt table, alt chosen
 *   (same rule as libuvc), uvc_start_streaming result, frames, fps, bytes/s, invalid JPEG (no SOI/EOI),
 *   sequence gaps, estimated usbfs buffer bytes, and the environment (euid, usbfs_memory_mb).
 * Suggested runs (same bus/hub!):  1) no override, 2 cameras ... N cameras; 2) --override-frac 0.5; 3) --override-frac 0.25;
 *   write each to results/<linux|macos>/<hostname>/bw_forced_alt/<name>.json
 */
#define _POSIX_C_SOURCE 200809L
#include <libuvc/libuvc.h>
#include <libusb.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define MAXCAM 16
#define MAXALT 32

typedef struct {
    int vid, pid; char serial[128]; int nth;
    uvc_device_t *dev; uvc_device_handle_t *devh; uvc_stream_ctrl_t ctrl;
    uint32_t requested, used; int iface;
    int nalt; int alt_no[MAXALT]; int alt_bytes[MAXALT]; int alt_chosen; int speed;
    uvc_error_t open_err, ctrl_err, start_err;
    pthread_mutex_t mu; long frames, bytes, invalid, seq_gaps; uint32_t last_seq; double t_first, t_last;
    int streaming;
} cam_t;

static double now_s(void) { struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts); return ts.tv_sec + ts.tv_nsec * 1e-9; }
static enum uvc_frame_format g_fmt = UVC_FRAME_FORMAT_MJPEG;
static double g_warm_until = 0;

static void cb(uvc_frame_t *f, void *p) {
    cam_t *c = (cam_t *)p;
    double t = now_s();
    pthread_mutex_lock(&c->mu);
    if (t >= g_warm_until) {
        if (c->t_first == 0) c->t_first = t; else { c->frames++; c->bytes += (long)f->data_bytes; }
        c->t_last = t;
        if (g_fmt == UVC_FRAME_FORMAT_MJPEG) {
            const unsigned char *d = (const unsigned char *)f->data; size_t n = f->data_bytes; int eoi = 0;
            for (size_t i = (n > 64 ? n - 64 : 0); i + 1 < n; i++) if (d[i] == 0xFF && d[i + 1] == 0xD9) eoi = 1;
            if (n < 4 || d[0] != 0xFF || d[1] != 0xD8 || !eoi) c->invalid++;
        }
        if (c->last_seq && f->sequence != c->last_seq + 1) c->seq_gaps++;
    }
    c->last_seq = f->sequence;
    pthread_mutex_unlock(&c->mu);
}

/* bytes per service interval for every alt setting of the VS interface (HS: mult x size; SS: companion) */
static void alt_table(cam_t *c) {
    libusb_device *ud = libusb_get_device(uvc_get_libusb_handle(c->devh));
    struct libusb_config_descriptor *cfg = NULL;
    c->speed = libusb_get_device_speed(ud);
    if (libusb_get_active_config_descriptor(ud, &cfg) != 0) return;
    for (int i = 0; i < cfg->bNumInterfaces; i++) {
        const struct libusb_interface *itf = &cfg->interface[i];
        if (itf->num_altsetting < 1 || itf->altsetting[0].bInterfaceNumber != c->ctrl.bInterfaceNumber) continue;
        c->iface = itf->altsetting[0].bInterfaceNumber;
        for (int a = 0; a < itf->num_altsetting && c->nalt < MAXALT; a++) {
            const struct libusb_interface_descriptor *as = &itf->altsetting[a];
            int bytes = 0;
            for (int e = 0; e < as->bNumEndpoints; e++) {
                const struct libusb_endpoint_descriptor *ep = &as->endpoint[e];
                if ((ep->bmAttributes & 3) != LIBUSB_TRANSFER_TYPE_ISOCHRONOUS) continue;
                struct libusb_ss_endpoint_companion_descriptor *ss = NULL;
                if (c->speed >= LIBUSB_SPEED_SUPER && libusb_get_ss_endpoint_companion_descriptor(NULL, ep, &ss) == 0 && ss) {
                    bytes = ss->wBytesPerInterval; libusb_free_ss_endpoint_companion_descriptor(ss);
                } else bytes = (ep->wMaxPacketSize & 0x7ff) * (((ep->wMaxPacketSize >> 11) & 3) + 1);
            }
            c->alt_no[c->nalt] = as->bAlternateSetting; c->alt_bytes[c->nalt] = bytes; c->nalt++;
        }
    }
    libusb_free_config_descriptor(cfg);
}

static int pick_alt(cam_t *c, uint32_t need) {  /* libuvc rule: first alt (descriptor order) with bytes >= need */
    for (int a = 0; a < c->nalt; a++) if (c->alt_bytes[a] > 0 && (uint32_t)c->alt_bytes[a] >= need) return c->alt_no[a];
    return -1;
}

static long read_long_file(const char *p) { FILE *f = fopen(p, "r"); long v = -1; if (f) { if (fscanf(f, "%ld", &v) != 1) v = -1; fclose(f); } return v; }

int main(int argc, char **argv) {
    int w = 1280, h = 720, fps = 30; double seconds = 8; long ov_bytes = -1; double ov_frac = -1; int ov_alt = -1;
    const char *out = NULL; cam_t cams[MAXCAM]; int n = 0;
    memset(cams, 0, sizeof cams);
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--format") && i + 1 < argc) { i++; g_fmt = !strcmp(argv[i], "yuyv") ? UVC_FRAME_FORMAT_YUYV : UVC_FRAME_FORMAT_MJPEG; }
        else if (!strcmp(argv[i], "--size") && i + 1 < argc) { if (sscanf(argv[++i], "%dx%d", &w, &h) != 2) { fprintf(stderr, "bad --size\n"); return 1; } }
        else if (!strcmp(argv[i], "--fps") && i + 1 < argc) fps = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--seconds") && i + 1 < argc) seconds = atof(argv[++i]);
        else if (!strcmp(argv[i], "--override-bytes") && i + 1 < argc) ov_bytes = atol(argv[++i]);
        else if (!strcmp(argv[i], "--override-frac") && i + 1 < argc) ov_frac = atof(argv[++i]);
        else if (!strcmp(argv[i], "--override-alt") && i + 1 < argc) ov_alt = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--out") && i + 1 < argc) out = argv[++i];
        else if (argv[i][0] != '-' && n < MAXCAM) {
            cam_t *c = &cams[n]; unsigned v, p; char sn[128] = "";
            if (sscanf(argv[i], "%x:%x:%127s", &v, &p, sn) < 2) { fprintf(stderr, "bad device %s (want VID:PID[:SERIAL])\n", argv[i]); return 1; }
            c->vid = (int)v; c->pid = (int)p; strcpy(c->serial, sn);
            for (int k = 0; k < n; k++) if (cams[k].vid == c->vid && cams[k].pid == c->pid && !strcmp(cams[k].serial, c->serial)) c->nth++;
            pthread_mutex_init(&c->mu, NULL); n++;
        } else { fprintf(stderr, "unknown arg %s\n", argv[i]); return 1; }
    }
    if (!n) { fprintf(stderr, "usage: see header comment\n"); return 1; }
    uvc_context_t *ctx = NULL;
    uvc_error_t r = uvc_init(&ctx, NULL);
    if (r < 0) { fprintf(stderr, "uvc_init: %s\n", uvc_strerror(r)); return 2; }

    for (int i = 0; i < n; i++) {
        cam_t *c = &cams[i];
        uvc_device_t **list = NULL;
        c->open_err = uvc_find_devices(ctx, &list, c->vid, c->pid, c->serial[0] ? c->serial : NULL);
        if (c->open_err == UVC_SUCCESS) {
            int k = 0; while (list[k] && k < c->nth) k++;
            if (!list[k]) c->open_err = UVC_ERROR_NO_DEVICE;
            else { c->dev = list[k]; uvc_ref_device(c->dev); }
            uvc_free_device_list(list, 1);
        }
        if (c->open_err == UVC_SUCCESS) c->open_err = uvc_open(c->dev, &c->devh);
        if (c->open_err != UVC_SUCCESS) { fprintf(stderr, "[%04x:%04x#%d] open: %s\n", c->vid, c->pid, c->nth, uvc_strerror(c->open_err)); continue; }
        c->ctrl_err = uvc_get_stream_ctrl_format_size(c->devh, &c->ctrl, g_fmt, w, h, fps);
        if (c->ctrl_err != UVC_SUCCESS) { fprintf(stderr, "[%04x:%04x#%d] get_stream_ctrl: %s\n", c->vid, c->pid, c->nth, uvc_strerror(c->ctrl_err)); continue; }
        alt_table(c);
        c->requested = c->ctrl.dwMaxPayloadTransferSize;
        uint32_t use = c->requested;
        if (ov_bytes > 0) use = (uint32_t)ov_bytes;
        else if (ov_frac > 0) use = (uint32_t)(c->requested * ov_frac);
        else if (ov_alt >= 0) for (int a = 0; a < c->nalt; a++) if (c->alt_no[a] == ov_alt) use = (uint32_t)c->alt_bytes[a];
        if (use < 1) use = 1;
        c->ctrl.dwMaxPayloadTransferSize = use;   /* <- the whole trick; see header */
        c->used = use;
        c->alt_chosen = pick_alt(c, use);
    }
    /* ramp: start one after another, 1.5 s apart, so a bandwidth failure is attributed to the camera that hit it */
    for (int i = 0; i < n; i++) {
        cam_t *c = &cams[i];
        if (c->open_err || c->ctrl_err) continue;
        c->start_err = uvc_start_streaming(c->devh, &c->ctrl, cb, c, 0);
        c->streaming = c->start_err == UVC_SUCCESS;
        fprintf(stderr, "[%04x:%04x#%d] requested=%u used=%u alt=%d start=%s\n", c->vid, c->pid, c->nth, c->requested, c->used,
                c->alt_chosen, uvc_strerror(c->start_err));
        usleep(1500000);
    }
    g_warm_until = now_s() + 1.0;
    usleep((useconds_t)((seconds + 1.0) * 1e6));
    for (int i = 0; i < n; i++) if (cams[i].streaming) uvc_stop_streaming(cams[i].devh);

    FILE *o = out ? fopen(out, "w") : stdout;
    if (!o) o = stdout;
    long mb = read_long_file("/sys/module/usbcore/parameters/usbfs_memory_mb");
    fprintf(o, "{\"test\":\"bw_forced_alt\",\"euid\":%d,\"usbfs_memory_mb\":%ld,\"format\":\"%s\",\"size\":\"%dx%d\",\"fps\":%d,\"seconds\":%.1f,"
               "\"override\":{\"bytes\":%ld,\"frac\":%.3f,\"alt\":%d},\"cameras\":[\n",
            (int)geteuid(), mb, g_fmt == UVC_FRAME_FORMAT_MJPEG ? "mjpeg" : "yuyv", w, h, fps, seconds, ov_bytes, ov_frac, ov_alt);
    for (int i = 0; i < n; i++) {
        cam_t *c = &cams[i];
        double dt = c->t_last > c->t_first ? c->t_last - c->t_first : 0;
        /* libuvc: LIBUVC_NUM_TRANSFER_BUFS x min(32, ceil(dwMaxVideoFrameSize/bpi)) x bpi bytes of iso buffers */
        long bpi = 0; for (int a = 0; a < c->nalt; a++) if (c->alt_no[a] == c->alt_chosen) bpi = c->alt_bytes[a];
        long ppt = bpi ? (long)((c->ctrl.dwMaxVideoFrameSize + bpi - 1) / bpi) : 0; if (ppt > 32) ppt = 32;
        fprintf(o, " {\"vid\":\"%04x\",\"pid\":\"%04x\",\"serial\":\"%s\",\"nth\":%d,\"speed\":%d,\"open\":\"%s\",\"get_ctrl\":\"%s\","
                   "\"requested_dwMaxPayloadTransferSize\":%u,\"used_dwMaxPayloadTransferSize\":%u,\"dwMaxVideoFrameSize\":%u,"
                   "\"alt_chosen\":%d,\"start\":\"%s\",\"frames\":%ld,\"fps\":%.3f,\"bytes_per_s\":%.0f,\"invalid_jpeg\":%ld,\"seq_gaps\":%ld,"
                   "\"iso_bytes_per_transfer\":%ld,\"alts\":[",
                c->vid, c->pid, c->serial, c->nth, c->speed, uvc_strerror(c->open_err), uvc_strerror(c->ctrl_err), c->requested, c->used,
                c->ctrl.dwMaxVideoFrameSize, c->alt_chosen, uvc_strerror(c->start_err), c->frames, dt > 0 ? c->frames / dt : 0.0,
                dt > 0 ? c->bytes / dt : 0.0, c->invalid, c->seq_gaps, ppt * bpi);
        for (int a = 0; a < c->nalt; a++) fprintf(o, "%s[%d,%d]", a ? "," : "", c->alt_no[a], c->alt_bytes[a]);
        fprintf(o, "]}%s\n", i + 1 < n ? "," : "");
    }
    fprintf(o, "]}\n");
    if (o != stdout) fclose(o);
    for (int i = 0; i < n; i++) { if (cams[i].devh) uvc_close(cams[i].devh); if (cams[i].dev) uvc_unref_device(cams[i].dev); }
    uvc_exit(ctx);
    return 0;
}
