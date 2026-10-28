/*
 * test_payload_timing.c - hardware-free unit test of patches/0001 Part A (per-frame payload-header
 * timing in libuvc). Feeds synthetic UVC payloads straight into libuvc's _uvc_process_payload()
 * (non-static in stream.c) and checks what _uvc_populate_frame() puts into uvc_frame_t.
 *
 * Build: part of research/usb_cameras/libusb/CMakeLists.txt (target test_payload_timing)
 * Run:   test_payload_timing <out.json>     exit 0 = all checks passed
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "libuvc/libuvc.h"
#include "libuvc/libuvc_internal.h"

void _uvc_process_payload(uvc_stream_handle_t *strmh, uint8_t *payload, size_t payload_len);
void _uvc_populate_frame(uvc_stream_handle_t *strmh);

static int n_fail = 0, n_ok = 0;
static FILE *out;
#define CHECK(name, cond) do { int _c = (cond); fprintf(out, "%s{\"check\":\"%s\",\"pass\":%s}", (n_ok + n_fail) ? "," : "", name, _c ? "true" : "false"); if (_c) n_ok++; else { n_fail++; fprintf(stderr, "FAIL %s\n", name); } } while (0)

/* build one payload: 12-byte header (PTS+SCR when flags say so) + data */
static size_t mk(uint8_t *b, uint8_t bfh, uint32_t pts, uint32_t stc, uint16_t sof, const uint8_t *data, size_t n) {
  size_t h = 2;
  b[1] = bfh;
  if (bfh & UVC_STREAM_PTS) { memcpy(b + h, &pts, 4); h += 4; }
  if (bfh & UVC_STREAM_SCR) { memcpy(b + h, &stc, 4); memcpy(b + h + 4, &sof, 2); h += 6; }
  b[0] = (uint8_t)h;
  if (n) memcpy(b + h, data, n);
  return h + n;
}

int main(int argc, char **argv) {
  static uvc_stream_handle_t S;
  static struct uvc_device_handle D;
  static uvc_streaming_interface_t SI;
  static uvc_format_desc_t FMT;
  static uvc_frame_desc_t FR;
  uint8_t pkt[4096], data[1024];
  uvc_stream_handle_t *s = &S;
  out = argc > 1 ? fopen(argv[1], "w") : stdout;
  if (!out) return 2;

  /* minimal stream/format/frame descriptors so _uvc_populate_frame can look up width/height */
  FR.bFrameIndex = 1; FR.wWidth = 64; FR.wHeight = 48; FR.parent = &FMT; FR.prev = &FR; FR.next = NULL;
  FMT.bFormatIndex = 1; FMT.frame_descs = &FR; FMT.prev = &FMT; FMT.next = NULL; FMT.parent = &SI;
  SI.format_descs = &FMT; SI.prev = &SI; SI.next = NULL;
  D.is_isight = 0;
  s->devh = &D; s->stream_if = &SI;
  s->cur_ctrl.bFormatIndex = 1; s->cur_ctrl.bFrameIndex = 1; s->cur_ctrl.dwMaxVideoFrameSize = 1 << 16;
  s->frame_format = UVC_FRAME_FORMAT_MJPEG; s->frame.library_owns_data = 1;
  s->outbuf = malloc(1 << 16); s->holdbuf = malloc(1 << 16);
  s->meta_outbuf = malloc(LIBUVC_XFER_META_BUF_SIZE); s->meta_holdbuf = malloc(LIBUVC_XFER_META_BUF_SIZE);
  pthread_mutex_init(&s->cb_mutex, NULL); pthread_cond_init(&s->cb_cond, NULL);
  s->fid = 0; s->seq = 1; s->packets_per_transfer = 32;
  memset(&s->cur_timing, 0, sizeof s->cur_timing);
  s->cur_timing.first_payload_packet_idx = s->cur_timing.last_payload_packet_idx = -1;
  memset(data, 0xAB, sizeof data);
  data[0] = 0xFF; data[1] = 0xD8;

  fprintf(out, "{\"test\":\"libuvc_patch_payload_timing\",\"cameras\":[],\"checks\":[");
  const uint8_t P = UVC_STREAM_PTS | UVC_STREAM_SCR;

  /* frame A: FID 0, three payloads in transfer #1 (host 1000) packets 3..5, EOF on last */
  s->xfer_host_ns = 1000; s->xfer_packet_idx = 3;
  _uvc_process_payload(s, pkt, mk(pkt, 0 | P, 111, 2000, 0x0123, data, 100));
  s->xfer_packet_idx = 4;
  _uvc_process_payload(s, pkt, mk(pkt, 0 | P, 111, 2100, 0x0124, data, 100));
  s->xfer_host_ns = 2000; s->xfer_packet_idx = 5; /* closing payload arrives in a later transfer */
  _uvc_process_payload(s, pkt, mk(pkt, 0 | P | UVC_STREAM_EOF, 111, 2200, 0x0125, data, 50));
  _uvc_populate_frame(s);
  uvc_frame_t *f = &s->frame;
  CHECK("A_bytes_250", f->data_bytes == 250);
  CHECK("A_pts", f->has_pts && f->pts == 111);
  CHECK("A_scr_first", f->has_scr && f->scr_stc_first == 2000 && f->scr_sof_first == 0x123);
  CHECK("A_scr_last", f->scr_stc_last == 2200 && f->scr_sof_last == 0x125);
  CHECK("A_host_first_last", f->host_first_payload_ns == 1000 && f->host_last_payload_ns == 2000);
  CHECK("A_packet_idx", f->first_payload_packet_idx == 3 && f->last_payload_packet_idx == 5);
  CHECK("A_counts", f->payload_count == 3 && f->error_payload_count == 0);
  CHECK("A_closed_by_eof", f->closed_by_eof == 1 && f->fid == 0);
  CHECK("A_ppt", f->packets_per_transfer == 32);

  /* idle header-only payload with old FID 0 and a stale SCR: must NOT leak into frame B */
  s->xfer_host_ns = 2500; s->xfer_packet_idx = 0;
  _uvc_process_payload(s, pkt, mk(pkt, 0 | P, 111, 9999, 0x07ff, NULL, 0));

  /* frame B: FID 1, SOF field with reserved high bits set (must be masked to 11 bits), no EOF */
  s->xfer_host_ns = 3000; s->xfer_packet_idx = 1;
  _uvc_process_payload(s, pkt, mk(pkt, 1 | P, 222, 3000, (uint16_t)(0xF800 | 0x0010), data, 300));
  /* an errored payload during B */
  _uvc_process_payload(s, pkt, mk(pkt, 1 | UVC_STREAM_ERR, 0, 0, 0, data, 10));
  s->xfer_host_ns = 4000; s->xfer_packet_idx = 7;
  _uvc_process_payload(s, pkt, mk(pkt, 1 | P, 222, 3100, 0x0011, data, 300));
  /* frame C starts (FID 0) without B having had EOF -> B is closed by FID toggle */
  s->xfer_host_ns = 5000; s->xfer_packet_idx = 2;
  _uvc_process_payload(s, pkt, mk(pkt, 0 | P, 333, 4000, 0x0020, data, 100));
  _uvc_populate_frame(s);
  f = &s->frame;
  CHECK("B_bytes_600", f->data_bytes == 600);
  CHECK("B_pts", f->pts == 222);
  CHECK("B_no_stale_scr_from_idle_payload", f->scr_stc_first == 3000);
  CHECK("B_sof_masked", f->scr_sof_first == 0x0010 && f->scr_sof_last == 0x0011);
  CHECK("B_closed_by_fid_toggle", f->closed_by_eof == 0 && f->fid == 1);
  CHECK("B_error_payloads_1", f->error_payload_count == 1);
  CHECK("B_host", f->host_first_payload_ns == 3000 && f->host_last_payload_ns == 4000);
  CHECK("B_seq_increments", f->sequence == 2);

  /* frame C continues and ends with EOF; its timing must start from the toggle payload */
  s->xfer_host_ns = 6000; s->xfer_packet_idx = 9;
  _uvc_process_payload(s, pkt, mk(pkt, 0 | P | UVC_STREAM_EOF, 333, 4100, 0x0021, data, 20));
  _uvc_populate_frame(s);
  f = &s->frame;
  CHECK("C_bytes_120", f->data_bytes == 120);
  CHECK("C_scr_first_is_toggle_payload", f->scr_stc_first == 4000 && f->scr_stc_last == 4100);
  CHECK("C_host", f->host_first_payload_ns == 5000 && f->host_last_payload_ns == 6000);
  CHECK("C_eof", f->closed_by_eof == 1 && f->error_payload_count == 0);

  /* iso override API rejects a running stream and stores values otherwise */
  s->running = 1;
  CHECK("override_rejected_while_running", uvc_stream_set_iso_override(s, 3, 0, 0) == UVC_ERROR_INVALID_PARAM);
  s->running = 0;
  CHECK("override_ok", uvc_stream_set_iso_override(s, 3, 500, 16) == UVC_SUCCESS && s->iso_force_altsetting == 3 &&
                           s->iso_min_bytes_per_packet == 500 && s->iso_packets_per_transfer == 16);

  fprintf(out, "],\"passed\":%d,\"failed\":%d}\n", n_ok, n_fail);
  if (out != stdout) fclose(out);
  printf("passed=%d failed=%d\n", n_ok, n_fail);
  return n_fail ? 1 : 0;
}
