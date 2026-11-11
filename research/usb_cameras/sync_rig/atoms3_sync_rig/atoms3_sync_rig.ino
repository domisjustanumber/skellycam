/*
  atoms3_sync_rig.ino -- strobe-only sync rig firmware for the M5Stack AtomS3 Lite (ESP32-S3FN8) (DRAFT)

  Status: first draft. Compiles (see README.md in this folder for the exact command), never flashed,
  never run on hardware, nothing measured. Every timing claim below is a design intent to be checked
  with a logic analyzer (README "Bring-up checklist").

  Port of ../esp32_sync_rig/esp32_sync_rig.ino (classic ESP32) with a reduced scope:
    - Strobe: one MOSFET-switched LED, single or double pulse per period, phase relative to an epoch.
      Hardware edges from an MCPWM generator; same command syntax, limits and error strings as the
      classic sketch.
    - FSIN: one trigger output (the classic sketch had two pins carrying the same waveform).
    - Every strobe edge (and FSIN rise, CAP1_ROLE=1) is wired back to an MCPWM capture input and
      timestamped by the 80 MHz capture timer (12.5 ns ticks; APB clock on the ESP32-S3 too).
    - No LED bar: BAR / STEP / MODE CODE reply "ERR <CMD> unsupported".
    - Serial link: the S3's native USB Serial/JTAG controller (CDC-ACM), not a UART bridge.
      There is no UART RX pin to capture, so PONG's 4th token is always "B" (estimated).
    - USB SOF stamping (../DESIGN.md section C option 4): a task on core 0 polls the
      USB_SERIAL_JTAG_FRAM_NUM register (11-bit SOF frame index) and stamps each change on the
      esp_timer clock. Exposed as trailing PONG tokens and as rate-limited "EV U" events.

  Timebases:
    - esp_timer (64-bit us since boot) is THE reported timebase, as in the classic sketch. All "esp_ns"
      values are esp_timer microseconds x 1000 plus a sub-us part.
    - Sub-us reads of esp_timer: esp_timer on the ESP32-S3 is systimer counter 0 (16 MHz, 62.5 ns
      ticks; IDF esp_private/systimer.h). fine_ns() reads that counter directly, so it is the same
      clock as esp_timer_get_time() at 62.5 ns resolution. STATUS reports sys_off_ns, the measured
      difference between the two (expected |sys_off_ns| < 1000).
    - MCPWM capture timer: 32-bit, APB 80 MHz on the S3 (IDF soc/esp32s3 clk_tree_defs.h:
      MCPWM_CAPTURE_CLK_SRC_DEFAULT = APB; there is no capture prescaler on ESP32/ESP32-S3).
      Mapped to esp_ns through a soft-catch anchor, as in the classic sketch.
    - MCPWM PWM timers: 2 MHz (0.5 us ticks) from PLL_F160M, same as the classic sketch.

  Board settings (Arduino-ESP32 core 3.x): FQBN esp32:esp32:m5stack_atoms3, which defaults to
  USB Mode = "Hardware CDC and JTAG" and USB CDC On Boot = "Enabled". See README.md.
*/

#include <Arduino.h>
#include "esp_arduino_version.h"

#if !defined(ESP_ARDUINO_VERSION_MAJOR) || ESP_ARDUINO_VERSION_MAJOR < 3
#error "This sketch needs Arduino-ESP32 core 3.x (it calls the ESP-IDF 5.x MCPWM driver)."
#endif
#if !CONFIG_IDF_TARGET_ESP32S3
#error "This sketch is for the ESP32-S3 (M5Stack AtomS3 Lite). Use ../esp32_sync_rig for the classic ESP32."
#endif
#if !ARDUINO_USB_MODE || !ARDUINO_USB_CDC_ON_BOOT
#error "Select USB Mode = Hardware CDC and JTAG and USB CDC On Boot = Enabled (FQBN esp32:esp32:m5stack_atoms3 does by default)."
#endif

#include "driver/mcpwm_prelude.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include "esp_cpu.h"
#include "esp_rom_sys.h"
#include "esp_private/systimer.h"
#include "hal/systimer_ll.h"
#include "soc/systimer_struct.h"
#include "soc/usb_serial_jtag_reg.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"

// =====================================================================================
// Configuration: every pin and constant lives here
// =====================================================================================

#define FW_NAME    "atoms3_sync_rig"
#define FW_VERSION "0.1.0-draft"

// ---- Serial link: USB Serial/JTAG CDC. The baud rate is ignored by the USB link. ----
static const uint32_t SERIAL_BAUD = 921600;
static const size_t CMD_LINE_MAX = 96;           // longest accepted command line
static const uint32_t SERIAL_TX_TIMEOUT_MS = 20; // HWCDC: max block per write when the host is slow

// ---- Pins (AtomS3 Lite; source: M5Stack pin map C124_PinMap_01.jpg and schematic Sch_M5_AtomS3_v1.0.pdf
//      linked from https://docs.m5stack.com/en/core/AtomS3%20Lite, fetched 2026-11-06) ----
// Exposed: header 3V3 G5 G6 G7 G8 | header G39 G38 5V GND | PORT.A (HY2.0-4P) GND 5V G2 G1.
// Avoided: strapping 0/3/45/46 (G0 is also driven by the board's reset/boot circuit, G3 has a 10k pull-up),
//          USB D-/D+ 19/20, UART0 43/44, on-board IR LED G4, RGB LED G35, button G41.
static const int PIN_STROBE = 5;      // strobe MOSFET gate, MCPWM0 timer0 generator; wire to PIN_CAP_STROBE
static const int PIN_CAP_STROBE = 6;  // capture 0 input (internal pull-down): strobe loopback
static const int PIN_FSIN = 7;        // FSIN sink gate, MCPWM0 timer1 generator; wire to PIN_CAP_FSIN
static const int PIN_CAP_FSIN = 8;    // capture 1 input (internal pull-down): FSIN loopback (CAP1_ROLE=1)
static const int PIN_SYNC = 39;       // internal MCPWM sync trigger (GPIO io_loop_back). Leave unconnected;
                                      // its rising edge marks START on a logic analyzer
static const int PIN_CAP_SYNC = 39;   // capture 2 input: the SYNC edge (same pad, routed in the GPIO matrix)
                                      // and the soft-catch anchors. Set to 38 + wire 39->38 if the same-pad
                                      // route does not capture on hardware (bring-up step 2)
static const int PIN_BUTTON = 41;     // on-board button, 10k pull-up on the board, active low
static const int PIN_RGB = 35;        // on-board WS2812 status LED (never a strobe: addressable, internal PWM)
static const int PIN_IR = 4;          // on-board IR LED (G4 -> LED -> 22R -> GND). Held low, never used
// Spare: G38 (header), G1, G2 (PORT.A).

// ---- Feature switches (set from the build, e.g. --build-property "compiler.cpp.extra_flags=-DCAP1_ROLE=0") ----
#define CAP1_ROLE_NONE 0
#define CAP1_ROLE_FSIN 1
#ifndef CAP1_ROLE
#define CAP1_ROLE CAP1_ROLE_FSIN      // capture channel 1 watches the FSIN loopback on G8
#endif
#ifndef STATUS_LED
#define STATUS_LED 1                  // 0: keep the RGB LED dark (if it is in a camera's view)
#endif
#ifndef STATUS_LED_LEVEL
#define STATUS_LED_LEVEL 6            // 0-255, keep it dim
#endif

// ---- MCPWM timebase ----
static const uint32_t PWM_RES_HZ = 2000000;                 // strobe + FSIN timers: 0.5 us ticks
static const uint32_t TICKS_PER_US = PWM_RES_HZ / 1000000;  // 2
static const uint32_t FIRST_EDGE_TICKS = 64;                // single-pulse rise position in the up/down cycle
static const uint32_t CAP_RES_HZ = 80000000;                // capture timer = APB clock on ESP32-S3
static const uint32_t EPOCH_DELAY_US = 100;                 // epoch = SYNC rising edge + this (no LE on this board)

// ---- Limits (checked on every command; identical to the classic sketch) ----
static const uint32_t PERIOD_MIN_US = 1000;
static const uint32_t PERIOD_MAX_US = 65535;          // up/down timer: peak <= 65535 ticks
static const uint32_t STROBE_WIDTH_MAX_US = 500;      // hard cap (LED pulse rating, eye comfort)
static const uint32_t STROBE_DUTY_MAX_PERMILLE = 10;  // 1 %
static const uint32_t FSIN_WIDTH_MIN_US = 1;
static const int64_t PRE_EPOCH_MARGIN_NS = 5000;      // captured pulses earlier than epoch+phase-margin are dropped

// ---- Tasks ----
static const BaseType_t CAPTURE_CORE = 0;   // capture ISRs + SOF poller; Arduino loop and the HWCDC ISR run on core 1
static const UBaseType_t SOF_TASK_PRIO = 1; // above IDLE0 only; it yields 1 tick every SOF_YIELD_MS
static const uint32_t SOF_YIELD_MS = 100;   // lets IDLE0 run (task watchdog) at the cost of ~1 ms of missed SOFs
static const uint32_t SOF_MAX_BRACKET_NS = 2000;  // reject SOF stamps whose poll bracket is wider (preempted)
static const uint32_t SOF_EVENT_PERIOD_MS = 100;  // "EV U" rate limit (10 per second)
static const uint32_t ANCHOR_INTERVAL_MS = 1000;
static const int ANCHOR_ATTEMPTS = 16;
static const UBaseType_t EVENT_QUEUE_LEN = 64;

// =====================================================================================
// Types
// =====================================================================================

struct RigConfig {
  bool strobe_on;
  uint32_t strobe_period_us, strobe_width_us, strobe_phase_us, strobe_gap_us;  // gap 0 = single pulse
  bool fsin_on;
  uint32_t fsin_period_us, fsin_width_us, fsin_phase_us;
};

enum EventType : uint8_t { EVT_STROBE = 0, EVT_FSIN, EVT_EPOCH };

struct CapEvent {
  uint8_t type;
  uint32_t t0;  // capture ticks (rise)
  uint32_t t1;  // capture ticks (fall, strobe only)
};

struct SofSample {
  int32_t frame;     // 11-bit SOF frame index, -1 = none yet
  int64_t esp_ns;    // esp_timer ns at the frame-number change (bracket midpoint)
  uint32_t w_ns;     // poll bracket width (the change happened inside it)
  uint32_t n;        // accepted stamps since boot
};

// =====================================================================================
// State
// =====================================================================================

static RigConfig g_cfg = {false, 33333, 50, 0, 0, false, 20800, 100, 0};
static bool g_running = false;
static bool g_events_on = true;
static bool g_hw_ok = false;
static uint32_t g_boot_id = 0;

// MCPWM handles (group 0 for everything, so all edges share one clock tree)
static mcpwm_timer_handle_t g_tmr_strobe, g_tmr_fsin;
static mcpwm_oper_handle_t g_op_strobe, g_op_fsin;
static mcpwm_cmpr_handle_t g_cmp_sa, g_cmp_sb, g_cmp_fa, g_cmp_fb;
static mcpwm_gen_handle_t g_gen_strobe, g_gen_fsin;
static mcpwm_sync_handle_t g_sync;
static mcpwm_cap_timer_handle_t g_cap_timer;
static mcpwm_cap_channel_handle_t g_cap0, g_cap1, g_cap2;
static uint32_t g_cap_res_hz = CAP_RES_HZ;
static volatile esp_err_t g_capture_init_err = ESP_FAIL;
static QueueHandle_t g_evq;

// Shared with ISRs
static volatile uint32_t g_evq_overflow = 0;
static volatile uint32_t g_strobe_rise = 0;
static volatile bool g_strobe_have_rise = false;
static volatile bool g_sync_armed = false;
static volatile bool g_soft_pending = false, g_soft_done = false;
static volatile uint32_t g_soft_ticks = 0;

// Pulse counters (loop context: k is assigned when the event is drained, after the pre-epoch filter)
static uint32_t g_strobe_k = 0, g_fsin_k = 0, g_pre_epoch_drops = 0;
static bool g_epoch_valid = false;
static int64_t g_epoch_ns = 0;
static int64_t g_run_strobe_phase_ns = 0;  // strobe phase of the current run (the config may change before START)

// Capture-timer <-> esp_timer mapping (loop context only)
static bool g_anchor_valid = false;
static int64_t g_anchor0_ticks64 = 0, g_anchor0_esp_ns = 0;  // fixed offset, set once at boot
static int64_t g_unwrap_ticks64 = 0, g_unwrap_esp_ns = 0;    // latest anchor, used to unwrap 32-bit captures
static int64_t g_anchor_resid_ns = 0, g_anchor_half_ns = 0;
static uint32_t g_last_anchor_ms = 0;

// Fine esp_timer clock (systimer counter 0)
static uint32_t g_sys_ticks_per_s = 16000000;
static int64_t g_sys_off_ns = 0;
static uint32_t g_cpu_mhz = 240;

// SOF poller -> loop (seqlocks: odd while the writer is inside)
static volatile uint32_t g_sof_seq = 0, g_sof_frame = 0, g_sof_w_ns = 0, g_sof_n = 0, g_sof_rej = 0;
static volatile int64_t g_sof_ns = 0;
static volatile uint32_t g_pkt_seq = 0, g_pkt_n = 0, g_pkt_w_ns = 0;
static volatile int64_t g_pkt_ns = 0;
static uint32_t g_sof_last_event_n = 0, g_last_sof_event_ms = 0;

// Reporting state
static uint32_t g_ovf_reported = 0;

// Serial line assembly
static char g_line[CMD_LINE_MAX + 1];
static size_t g_line_len = 0;
static bool g_line_overflow = false;
static int64_t g_line_rx_ns = 0;     // best estimate of when the first byte of the line arrived
static char g_line_rx_src = 'L';     // P = USB OUT packet stamp from the poller, L = loop saw the byte
static uint32_t g_pkt_n_used = 0;

// Button / LED
static bool g_btn_last = true;
static uint32_t g_btn_change_ms = 0;
static int g_led_state = -1;

// =====================================================================================
// Small helpers
// =====================================================================================

// Convert a tick count or difference to ns without 64-bit overflow for multi-day spans.
static int64_t ticks_to_ns(int64_t d, uint32_t res_hz) {
  int64_t whole = d / (int64_t)res_hz, rem = d % (int64_t)res_hz;
  return whole * 1000000000LL + rem * 1000000000LL / (int64_t)res_hz;
}

static int64_t ns_to_ticks(int64_t ns, uint32_t res_hz) {
  int64_t whole = ns / 1000000000LL, rem = ns % 1000000000LL;
  return whole * (int64_t)res_hz + rem * (int64_t)res_hz / 1000000000LL;
}

// Systimer counter 0 = the esp_timer counter. Same read sequence as IDF systimer_hal_get_counter_value():
// snapshot, wait for VALID, then re-read LO until it is stable around the HI read (another core may
// request a snapshot of the same counter at any time; the result is then a few ns newer, never torn).
static inline uint64_t sys_ticks() {
  systimer_dev_t *dev = &SYSTIMER;
  systimer_ll_counter_snapshot(dev, SYSTIMER_COUNTER_ESPTIMER);
  while (!systimer_ll_is_counter_value_valid(dev, SYSTIMER_COUNTER_ESPTIMER)) {}
  uint32_t lo, hi, lo_start = systimer_ll_get_counter_value_low(dev, SYSTIMER_COUNTER_ESPTIMER);
  do {
    lo = lo_start;
    hi = systimer_ll_get_counter_value_high(dev, SYSTIMER_COUNTER_ESPTIMER);
    lo_start = systimer_ll_get_counter_value_low(dev, SYSTIMER_COUNTER_ESPTIMER);
  } while (lo_start != lo);
  return ((uint64_t)hi << 32) | lo;
}

static inline int64_t fine_ns() { return ticks_to_ns((int64_t)sys_ticks(), g_sys_ticks_per_s); }

static inline int64_t cyc_to_ns(uint32_t cycles) { return (int64_t)cycles * 1000 / g_cpu_mhz; }

// 32-bit capture value -> esp_timer nanoseconds (requires g_anchor_valid).
// The 32-bit counter wraps every ~53.7 s; it is unwrapped against the latest periodic anchor.
static int64_t cap_to_esp_ns(uint32_t t32) {
  int64_t t64 = g_unwrap_ticks64 + (int32_t)(t32 - (uint32_t)g_unwrap_ticks64);
  return g_anchor0_esp_ns + ticks_to_ns(t64 - g_anchor0_ticks64, g_cap_res_hz);
}

static void sof_read(SofSample *s) {
  uint32_t s1, s2;
  do {
    s1 = g_sof_seq;
    __sync_synchronize();
    s->frame = (int32_t)g_sof_frame;
    s->esp_ns = g_sof_ns;
    s->w_ns = g_sof_w_ns;
    s->n = g_sof_n;
    __sync_synchronize();
    s2 = g_sof_seq;
  } while ((s1 & 1u) || s1 != s2);
  if (s->n == 0) s->frame = -1;
}

static void pkt_read(int64_t *ns, uint32_t *n) {
  uint32_t s1, s2;
  do {
    s1 = g_pkt_seq;
    __sync_synchronize();
    *ns = g_pkt_ns;
    *n = g_pkt_n;
    __sync_synchronize();
    s2 = g_pkt_seq;
  } while ((s1 & 1u) || s1 != s2);
}

static void led_set(int state) {  // 0 idle (blue), 1 running (green), 2 hardware init failed (red)
#if STATUS_LED
  if (state == g_led_state) return;
  g_led_state = state;
  const uint8_t L = STATUS_LED_LEVEL;
  if (state == 1) rgbLedWrite(PIN_RGB, 0, L, 0);
  else if (state == 2) rgbLedWrite(PIN_RGB, L, 0, 0);
  else rgbLedWrite(PIN_RGB, 0, 0, L);
#else
  (void)state;
#endif
}

// =====================================================================================
// USB SOF poller (core 0)
// =====================================================================================

// Busy-polls USB_SERIAL_JTAG_FRAM_NUM_REG (0x60038024, SOF_FRAME_INDEX bits [10:0]) and the raw
// SERIAL_OUT_RECV_PKT interrupt bit. The CPU cycle counter brackets each register read; on a change the
// systimer is read once and the change time is back-dated to the bracket midpoint. The HWCDC ISR on core 1
// clears the OUT_RECV_PKT raw bit a few us after it rises, so its rising edge is seen here first.
static void sof_task(void *) {
  volatile uint32_t *const fram = (volatile uint32_t *)USB_SERIAL_JTAG_FRAM_NUM_REG;
  volatile uint32_t *const intraw = (volatile uint32_t *)USB_SERIAL_JTAG_INT_RAW_REG;
  const uint32_t yield_cycles = SOF_YIELD_MS * 1000u * g_cpu_mhz;
  for (;;) {
    uint32_t last = *fram & USB_SERIAL_JTAG_SOF_FRAME_INDEX_V;
    bool pkt_prev = (*intraw & USB_SERIAL_JTAG_SERIAL_OUT_RECV_PKT_INT_RAW) != 0;
    uint32_t c_prev = esp_cpu_get_cycle_count();
    const uint32_t c_start = c_prev;
    for (;;) {
      uint32_t c = esp_cpu_get_cycle_count();
      uint32_t f = *fram & USB_SERIAL_JTAG_SOF_FRAME_INDEX_V;
      bool pkt = (*intraw & USB_SERIAL_JTAG_SERIAL_OUT_RECV_PKT_INT_RAW) != 0;
      bool fchg = (f != last), pedge = (pkt && !pkt_prev);
      if (fchg || pedge) {
        uint32_t cb = esp_cpu_get_cycle_count();
        uint64_t st = sys_ticks();
        uint32_t ca = esp_cpu_get_cycle_count();
        uint32_t w = c - c_prev;  // change happened between the previous reads and these reads
        uint32_t back = (cb - c) + (ca - cb) / 2 + w / 2;
        int64_t t_ns = ticks_to_ns((int64_t)st, g_sys_ticks_per_s) - cyc_to_ns(back);
        uint32_t w_ns = (uint32_t)cyc_to_ns(w);
        if (fchg) {
          if (f == ((last + 1) & USB_SERIAL_JTAG_SOF_FRAME_INDEX_V) && w_ns <= SOF_MAX_BRACKET_NS) {
            g_sof_seq = g_sof_seq + 1;
            __sync_synchronize();
            g_sof_frame = f;
            g_sof_ns = t_ns;
            g_sof_w_ns = w_ns;
            g_sof_n = g_sof_n + 1;
            __sync_synchronize();
            g_sof_seq = g_sof_seq + 1;
          } else {
            g_sof_rej = g_sof_rej + 1;
          }
          last = f;
        }
        if (pedge) {
          g_pkt_seq = g_pkt_seq + 1;
          __sync_synchronize();
          g_pkt_ns = t_ns;
          g_pkt_w_ns = w_ns;
          g_pkt_n = g_pkt_n + 1;
          __sync_synchronize();
          g_pkt_seq = g_pkt_seq + 1;
        }
      }
      pkt_prev = pkt;
      c_prev = c;
      if ((uint32_t)(c - c_start) > yield_cycles) break;
    }
    vTaskDelay(1);  // IDLE0 runs here (task watchdog); the next change after this is re-bracketed from scratch
  }
}

// =====================================================================================
// ISRs (IRAM, no serial, no blocking). All capture ISRs run on CAPTURE_CORE.
// =====================================================================================

static bool IRAM_ATTR on_cap_strobe(mcpwm_cap_channel_handle_t, const mcpwm_capture_event_data_t *e, void *) {
  BaseType_t woken = pdFALSE;
  if (e->cap_edge == MCPWM_CAP_EDGE_POS) {
    g_strobe_rise = e->cap_value;
    g_strobe_have_rise = true;
  } else if (g_strobe_have_rise) {
    CapEvent ev = {EVT_STROBE, g_strobe_rise, e->cap_value};
    g_strobe_have_rise = false;
    if (xQueueSendFromISR(g_evq, &ev, &woken) != pdTRUE) g_evq_overflow = g_evq_overflow + 1;
  }
  return woken == pdTRUE;
}

static bool IRAM_ATTR on_cap_fsin(mcpwm_cap_channel_handle_t, const mcpwm_capture_event_data_t *e, void *) {
  BaseType_t woken = pdFALSE;
  CapEvent ev = {EVT_FSIN, e->cap_value, 0};
  if (xQueueSendFromISR(g_evq, &ev, &woken) != pdTRUE) g_evq_overflow = g_evq_overflow + 1;
  return woken == pdTRUE;
}

// Capture 2: software anchor catches, and the SYNC rising edge at START (the epoch reference).
static bool IRAM_ATTR on_cap_sync(mcpwm_cap_channel_handle_t, const mcpwm_capture_event_data_t *e, void *) {
  if (g_soft_pending) {
    g_soft_ticks = e->cap_value;
    g_soft_pending = false;
    g_soft_done = true;
    return false;
  }
  if (!g_sync_armed) return false;
  g_sync_armed = false;
  BaseType_t woken = pdFALSE;
  CapEvent ev = {EVT_EPOCH, e->cap_value, 0};
  if (xQueueSendFromISR(g_evq, &ev, &woken) != pdTRUE) g_evq_overflow = g_evq_overflow + 1;
  return woken == pdTRUE;
}

// =====================================================================================
// Hardware init
// =====================================================================================

#define TRY(x) \
  do { \
    esp_err_t _e = (x); \
    if (_e != ESP_OK) { \
      Serial.printf("EV E INIT %s %s\n", #x, esp_err_to_name(_e)); \
      return _e; \
    } \
  } while (0)

static esp_err_t new_cap_channel(int gpio, bool pos, bool neg, mcpwm_capture_event_cb_t cbf,
                                 mcpwm_cap_channel_handle_t *ch) {
  mcpwm_capture_channel_config_t cc;
  memset(&cc, 0, sizeof(cc));
  cc.gpio_num = gpio;
  cc.prescale = 1;
  cc.flags.pos_edge = pos;
  cc.flags.neg_edge = neg;
  cc.flags.pull_down = 1;  // an unwired loopback reads low instead of floating
  esp_err_t e = mcpwm_new_capture_channel(g_cap_timer, &cc, ch);
  if (e != ESP_OK) return e;
  mcpwm_capture_event_callbacks_t cb;
  memset(&cb, 0, sizeof(cb));
  cb.on_cap = cbf;
  if ((e = mcpwm_capture_channel_register_event_callbacks(*ch, &cb, NULL)) != ESP_OK) return e;
  return mcpwm_capture_channel_enable(*ch);
}

// Runs on CAPTURE_CORE so the capture interrupts are allocated there.
static esp_err_t capture_init() {
  mcpwm_capture_timer_config_t tc;
  memset(&tc, 0, sizeof(tc));
  tc.group_id = 0;
  tc.clk_src = MCPWM_CAPTURE_CLK_SRC_DEFAULT;  // APB 80 MHz on ESP32-S3 (the only capture clock source)
  tc.resolution_hz = CAP_RES_HZ;
  esp_err_t e = mcpwm_new_capture_timer(&tc, &g_cap_timer);
  if (e != ESP_OK) return e;
  if ((e = new_cap_channel(PIN_CAP_STROBE, true, true, on_cap_strobe, &g_cap0)) != ESP_OK) return e;
#if CAP1_ROLE == CAP1_ROLE_FSIN
  if ((e = new_cap_channel(PIN_CAP_FSIN, true, false, on_cap_fsin, &g_cap1)) != ESP_OK) return e;
#else
  (void)on_cap_fsin;
#endif
  if ((e = new_cap_channel(PIN_CAP_SYNC, true, false, on_cap_sync, &g_cap2)) != ESP_OK) return e;
  if ((e = mcpwm_capture_timer_enable(g_cap_timer)) != ESP_OK) return e;
  if ((e = mcpwm_capture_timer_start(g_cap_timer)) != ESP_OK) return e;
  return mcpwm_capture_timer_get_resolution(g_cap_timer, &g_cap_res_hz);
}

static void capture_init_task(void *arg) {
  g_capture_init_err = capture_init();
  xTaskNotifyGive((TaskHandle_t)arg);
  vTaskDelete(NULL);
}

static esp_err_t new_gen(mcpwm_oper_handle_t op, int gpio, mcpwm_gen_handle_t *gen) {
  mcpwm_generator_config_t gc;
  memset(&gc, 0, sizeof(gc));
  gc.gen_gpio_num = gpio;
  esp_err_t e = mcpwm_new_generator(op, &gc, gen);
  if (e == ESP_OK) e = mcpwm_generator_set_force_level(*gen, 0, true);  // held low until START
  return e;
}

static esp_err_t pwm_init() {
  mcpwm_timer_config_t t;
  memset(&t, 0, sizeof(t));
  t.group_id = 0;
  t.clk_src = MCPWM_TIMER_CLK_SRC_DEFAULT;     // PLL_F160M on ESP32-S3 (the only PWM timer clock source)
  t.resolution_hz = PWM_RES_HZ;               // one group prescaler fits both timers
  t.count_mode = MCPWM_TIMER_COUNT_MODE_UP_DOWN;  // up/down: one cycle can hold a double pulse
  t.period_ticks = 2 * 33334;
  TRY(mcpwm_new_timer(&t, &g_tmr_strobe));
  TRY(mcpwm_new_timer(&t, &g_tmr_fsin));

  mcpwm_operator_config_t oc;
  memset(&oc, 0, sizeof(oc));
  oc.group_id = 0;
  TRY(mcpwm_new_operator(&oc, &g_op_strobe));
  TRY(mcpwm_new_operator(&oc, &g_op_fsin));
  TRY(mcpwm_operator_connect_timer(g_op_strobe, g_tmr_strobe));
  TRY(mcpwm_operator_connect_timer(g_op_fsin, g_tmr_fsin));

  // Comparators update immediately (no shadow): values are only changed while outputs are held.
  mcpwm_comparator_config_t cc;
  memset(&cc, 0, sizeof(cc));
  TRY(mcpwm_new_comparator(g_op_strobe, &cc, &g_cmp_sa));
  TRY(mcpwm_new_comparator(g_op_strobe, &cc, &g_cmp_sb));
  TRY(mcpwm_new_comparator(g_op_fsin, &cc, &g_cmp_fa));
  TRY(mcpwm_new_comparator(g_op_fsin, &cc, &g_cmp_fb));

  TRY(new_gen(g_op_strobe, PIN_STROBE, &g_gen_strobe));
  TRY(new_gen(g_op_fsin, PIN_FSIN, &g_gen_fsin));

  // FSIN: rise at FIRST_EDGE_TICKS on the way up, fall `width` later.
  TRY(mcpwm_generator_set_actions_on_compare_event(g_gen_fsin,
        MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP, g_cmp_fa, MCPWM_GEN_ACTION_HIGH),
        MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP, g_cmp_fb, MCPWM_GEN_ACTION_LOW),
        MCPWM_GEN_COMPARE_EVENT_ACTION_END()));

  // One sync input shared by both timers: a GPIO sync source on PIN_SYNC with io_loop_back, driven by
  // software at START. The same pad also feeds capture channel 2 (created earlier), which timestamps it.
  mcpwm_gpio_sync_src_config_t sc;
  memset(&sc, 0, sizeof(sc));
  sc.group_id = 0;
  sc.gpio_num = PIN_SYNC;
  sc.flags.io_loop_back = 1;
  sc.flags.pull_down = 1;
  TRY(mcpwm_new_gpio_sync_src(&sc, &g_sync));
  TRY(gpio_set_direction((gpio_num_t)PIN_SYNC, GPIO_MODE_INPUT_OUTPUT));
  TRY(gpio_set_level((gpio_num_t)PIN_SYNC, 0));

  TRY(mcpwm_timer_enable(g_tmr_strobe));
  TRY(mcpwm_timer_enable(g_tmr_fsin));
  return ESP_OK;
}

// =====================================================================================
// Clock anchor: capture timer <-> esp_timer
// =====================================================================================

// One soft catch bracketed by two fine esp_timer reads. Returns false if no catch completed.
static bool soft_catch(uint32_t *ticks, int64_t *esp_ns_mid, int64_t *half_ns) {
  int64_t best_half = INT64_MAX;
  bool ok = false;
  for (int i = 0; i < ANCHOR_ATTEMPTS; i++) {
    g_soft_done = false;
    g_soft_pending = true;
    int64_t a = fine_ns();
    esp_err_t err = mcpwm_capture_channel_trigger_soft_catch(g_cap2);
    int64_t b = fine_ns();
    if (err != ESP_OK) {
      g_soft_pending = false;
      return false;
    }
    uint32_t t0 = micros();
    while (!g_soft_done && (micros() - t0) < 2000) {}
    if (!g_soft_done) {
      g_soft_pending = false;
      continue;
    }
    int64_t half = (b - a) / 2;
    if (half < best_half) {  // keep the tightest bracket
      best_half = half;
      *ticks = g_soft_ticks;
      *esp_ns_mid = a + half;
      *half_ns = half;
      ok = true;
    }
  }
  return ok;
}

// First call fixes the offset; later calls only refresh the unwrap base and report the residual.
static bool clock_anchor(bool report) {
  uint32_t t32;
  int64_t mid, half;
  if (!soft_catch(&t32, &mid, &half)) {
    Serial.println("EV E ANCHOR soft_catch_failed");
    return false;
  }
  if (!g_anchor_valid) {
    g_anchor0_ticks64 = t32;
    g_anchor0_esp_ns = mid;
    g_unwrap_ticks64 = t32;
    g_unwrap_esp_ns = mid;
    g_anchor_valid = true;
  } else {
    int64_t pred = g_unwrap_ticks64 + ns_to_ticks(mid - g_unwrap_esp_ns, g_cap_res_hz);
    int64_t t64 = pred + (int32_t)(t32 - (uint32_t)pred);
    g_unwrap_ticks64 = t64;
    g_unwrap_esp_ns = mid;
    g_anchor_resid_ns = mid - (g_anchor0_esp_ns + ticks_to_ns(t64 - g_anchor0_ticks64, g_cap_res_hz));
  }
  g_anchor_half_ns = half;
  if (report && g_events_on)
    Serial.printf("EV K %lld %lld %lld %lld\n", (long long)g_unwrap_ticks64, (long long)g_unwrap_esp_ns,
                  (long long)g_anchor_resid_ns, (long long)half);
  return true;
}

// Fine clock vs esp_timer_get_time(): both should read systimer counter 0, so the offset should be ~0.
static void measure_sys_offset() {
  int64_t best = INT64_MAX;
  for (int i = 0; i < 8; i++) {
    int64_t a = fine_ns();
    int64_t us = esp_timer_get_time();
    int64_t b = fine_ns();
    if (b - a < best) {
      best = b - a;
      g_sys_off_ns = us * 1000 - (a + b) / 2;  // expect -500..+500 (us truncation) plus read latency
    }
  }
}

// =====================================================================================
// Output control
// =====================================================================================

static void gen_hold_low(mcpwm_gen_handle_t g) { mcpwm_generator_set_force_level(g, 0, true); }

static void gen_release(mcpwm_gen_handle_t g) {
  mcpwm_generator_set_force_level(g, -1, true);  // remove the continuous force
  mcpwm_generator_set_force_level(g, 0, false);  // one-shot low; normal actions take over
}

static void stop_outputs() {
  gen_hold_low(g_gen_strobe);
  gen_hold_low(g_gen_fsin);
  if (g_running) {
    mcpwm_timer_start_stop(g_tmr_strobe, MCPWM_TIMER_STOP_EMPTY);
    mcpwm_timer_start_stop(g_tmr_fsin, MCPWM_TIMER_STOP_EMPTY);
    vTaskDelay(pdMS_TO_TICKS(PERIOD_MAX_US / 1000 + 5));  // let the up/down timers reach zero
  }
  g_running = false;
  led_set(g_hw_ok ? 0 : 2);
}

// Sync-load position for an up/down timer so that its counter reaches `tA` going UP exactly
// `delay_ticks` after the sync edge. Cycle time tau in [0, P): count = tau (up) or P - tau (down).
static void updown_phase(uint32_t P, uint32_t delay_ticks, uint32_t tA, uint32_t *count, mcpwm_timer_direction_t *dir) {
  uint32_t tau = (tA + P - (delay_ticks % P)) % P;
  uint32_t peak = P / 2;
  if (tau <= peak) {
    *count = tau;
    *dir = MCPWM_TIMER_DIRECTION_UP;
  } else {
    *count = P - tau;
    *dir = MCPWM_TIMER_DIRECTION_DOWN;
  }
}

#define TRY_S(x) \
  do { \
    esp_err_t _e = (x); \
    if (_e != ESP_OK) return esp_err_to_name(_e); \
  } while (0)

static void drain_events();

// (Re)start every output from one common sync edge. Returns NULL or an error string.
//   epoch = SYNC rising edge + EPOCH_DELAY_US (reported as "EV A 0 <t>" from the captured SYNC edge)
//   strobe pulse 1 rises at epoch + phase + j * period; pulse 2 (double mode) gap later
//   FSIN rises at epoch + phase + j * period
static const char *start_outputs() {
  if (!g_hw_ok) return "hardware_init_failed";
  stop_outputs();
  drain_events();  // print what the previous run left in the queue before the counters reset

  const uint32_t epoch_ticks = EPOCH_DELAY_US * TICKS_PER_US;
  mcpwm_timer_sync_phase_config_t ph;
  memset(&ph, 0, sizeof(ph));
  ph.sync_src = g_sync;

  // --- timer 0: strobe (up/down; pulse 1 on the way up, optional pulse 2 on the way down) ---
  {
    uint32_t P = g_cfg.strobe_period_us * TICKS_PER_US;
    uint32_t w = g_cfg.strobe_width_us * TICKS_PER_US;
    bool dbl = g_cfg.strobe_gap_us > 0;
    // Double: rise1 = tA, fall1 = tB (up); rise2 = P - tB, fall2 = P - tA (down). gap = P - tA - tB.
    uint32_t tA = dbl ? (P - g_cfg.strobe_gap_us * TICKS_PER_US - w) / 2 : FIRST_EDGE_TICKS;
    uint32_t tB = tA + w;
    TRY_S(mcpwm_timer_set_period(g_tmr_strobe, P));
    TRY_S(mcpwm_comparator_set_compare_value(g_cmp_sa, tA));
    TRY_S(mcpwm_comparator_set_compare_value(g_cmp_sb, tB));
    mcpwm_generator_action_t down_b = dbl ? MCPWM_GEN_ACTION_HIGH : MCPWM_GEN_ACTION_KEEP;
    mcpwm_generator_action_t down_a = dbl ? MCPWM_GEN_ACTION_LOW : MCPWM_GEN_ACTION_KEEP;
    TRY_S(mcpwm_generator_set_actions_on_compare_event(g_gen_strobe,
          MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP, g_cmp_sa, MCPWM_GEN_ACTION_HIGH),
          MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP, g_cmp_sb, MCPWM_GEN_ACTION_LOW),
          MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_DOWN, g_cmp_sb, down_b),
          MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_DOWN, g_cmp_sa, down_a),
          MCPWM_GEN_COMPARE_EVENT_ACTION_END()));
    uint32_t cnt;
    mcpwm_timer_direction_t dir;
    updown_phase(P, epoch_ticks + g_cfg.strobe_phase_us * TICKS_PER_US, tA, &cnt, &dir);
    ph.count_value = cnt;
    ph.direction = dir;
    TRY_S(mcpwm_timer_set_phase_on_sync(g_tmr_strobe, &ph));
  }

  // --- timer 1: FSIN (up/down, single pulse) ---
  {
    uint32_t P = g_cfg.fsin_period_us * TICKS_PER_US;
    uint32_t tA = FIRST_EDGE_TICKS, tB = tA + g_cfg.fsin_width_us * TICKS_PER_US;
    TRY_S(mcpwm_timer_set_period(g_tmr_fsin, P));
    TRY_S(mcpwm_comparator_set_compare_value(g_cmp_fa, tA));
    TRY_S(mcpwm_comparator_set_compare_value(g_cmp_fb, tB));
    uint32_t cnt;
    mcpwm_timer_direction_t dir;
    updown_phase(P, epoch_ticks + g_cfg.fsin_phase_us * TICKS_PER_US, tA, &cnt, &dir);
    ph.count_value = cnt;
    ph.direction = dir;
    TRY_S(mcpwm_timer_set_phase_on_sync(g_tmr_fsin, &ph));
  }

  // --- reset counters ---
  g_strobe_k = 0;
  g_fsin_k = 0;
  g_pre_epoch_drops = 0;
  g_strobe_have_rise = false;
  g_epoch_valid = false;
  g_run_strobe_phase_ns = (int64_t)g_cfg.strobe_phase_us * 1000;

  // --- start both timers (outputs still held low), then align them with one sync edge ---
  TRY_S(mcpwm_timer_start_stop(g_tmr_strobe, MCPWM_TIMER_START_NO_STOP));
  TRY_S(mcpwm_timer_start_stop(g_tmr_fsin, MCPWM_TIMER_START_NO_STOP));
  g_sync_armed = true;
  gpio_set_level((gpio_num_t)PIN_SYNC, 1);
  esp_rom_delay_us(2);  // the timers sync on the rising edge; 2 us keeps the pulse well above any sampling clock
  gpio_set_level((gpio_num_t)PIN_SYNC, 0);
  // First scheduled edge is >= EPOCH_DELAY_US (100 us) after the sync, so the release below comes first.
  if (g_cfg.strobe_on) gen_release(g_gen_strobe);
  if (g_cfg.fsin_on) gen_release(g_gen_fsin);
  g_running = true;
  led_set(1);
  return NULL;
}

// =====================================================================================
// Validation (identical limits and error strings to the classic sketch)
// =====================================================================================

static const char *check_strobe(uint32_t p, uint32_t w, uint32_t ph, uint32_t gap) {
  if (p < PERIOD_MIN_US || p > PERIOD_MAX_US) return "period_us_out_of_range_1000_65535";
  if (w < 1 || w > STROBE_WIDTH_MAX_US) return "width_us_out_of_range_1_500";
  uint32_t pulses = gap ? 2 : 1;
  if ((uint64_t)pulses * w * 1000 > (uint64_t)STROBE_DUTY_MAX_PERMILLE * p) return "duty_over_1_percent";
  if (ph >= p) return "phase_must_be_below_period";
  if (gap) {
    if (gap <= w) return "gap_must_exceed_width";
    // As in the classic sketch, the 64 is applied in us here (more conservative than 64 ticks).
    if ((uint64_t)gap + w + FIRST_EDGE_TICKS > p) return "gap_plus_width_too_close_to_period";
  } else if (FIRST_EDGE_TICKS + w * TICKS_PER_US >= p) {
    return "width_too_long_for_period";
  }
  return NULL;
}

static const char *check_fsin(uint32_t p, uint32_t w, uint32_t ph) {
  if (p < PERIOD_MIN_US || p > PERIOD_MAX_US) return "period_us_out_of_range_1000_65535";
  if (w < FSIN_WIDTH_MIN_US || FIRST_EDGE_TICKS + w * TICKS_PER_US >= p) return "width_out_of_range";
  if (ph >= p) return "phase_must_be_below_period";
  return NULL;
}

// =====================================================================================
// Serial protocol
// =====================================================================================

static char g_tag[24];  // optional "#tag" echoed in front of the reply

static void reply(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static void reply(const char *fmt, ...) {
  char out[768];
  int n = 0;
  if (g_tag[0]) n = snprintf(out, sizeof(out), "%s ", g_tag);
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(out + n, sizeof(out) - n, fmt, ap);
  va_end(ap);
  Serial.println(out);
}

static bool parse_u32(const char *s, uint32_t *v) {
  if (!s || !*s) return false;
  char *end;
  unsigned long x = strtoul(s, &end, 10);
  if (*end) return false;
  *v = (uint32_t)x;
  return true;
}

static bool is_int_token(const char *s) {
  if (!s || !*s) return false;
  if (*s == '-') s++;
  size_t n = 0;
  for (; *s; s++, n++)
    if (*s < '0' || *s > '9') return false;
  return n > 0 && n <= 20;
}

static void print_status() {
  SofSample s;
  sof_read(&s);
  int64_t now = fine_ns();
  long long sof_age_us = s.n ? (long long)((now - s.esp_ns) / 1000) : -1;
  reply("OK STATUS fw=%s/%s core=%d.%d.%d board=atoms3_lite running=%d bar=NONE step_us=0 "
        "strobe=%d,%u,%u,%u,%u fsin=%d,%u,%u,%u le_events=0 late=0 strobe_k=%u fsin_k=%u evq_ovf=%u "
        "pre_epoch=%u epoch=%d cap1=%s rx_edge=0 cap_res_hz=%u anchor_half_ns=%lld anchor_resid_ns=%lld "
        "sof=%d sof_ns=%lld sof_w=%u sof_n=%u sof_rej=%u sof_age_us=%lld rx_pkt_n=%u sys_hz=%u sys_off_ns=%lld "
        "usb_cdc=%d xtal_mhz=%u apb_hz=%u cpu_mhz=%u boot_id=%08x esp_us=%lld",
        FW_NAME, FW_VERSION, ESP_ARDUINO_VERSION_MAJOR, ESP_ARDUINO_VERSION_MINOR, ESP_ARDUINO_VERSION_PATCH,
        (int)g_running,
        (int)g_cfg.strobe_on, (unsigned)g_cfg.strobe_period_us, (unsigned)g_cfg.strobe_width_us,
        (unsigned)g_cfg.strobe_phase_us, (unsigned)g_cfg.strobe_gap_us,
        (int)g_cfg.fsin_on, (unsigned)g_cfg.fsin_period_us, (unsigned)g_cfg.fsin_width_us, (unsigned)g_cfg.fsin_phase_us,
        (unsigned)g_strobe_k, (unsigned)g_fsin_k, (unsigned)g_evq_overflow,
        (unsigned)g_pre_epoch_drops, (int)g_epoch_valid,
        CAP1_ROLE == CAP1_ROLE_FSIN ? "FSIN" : "NONE", (unsigned)g_cap_res_hz,
        (long long)g_anchor_half_ns, (long long)g_anchor_resid_ns,
        (int)s.frame, (long long)s.esp_ns, (unsigned)s.w_ns, (unsigned)s.n, (unsigned)g_sof_rej, sof_age_us,
        (unsigned)g_pkt_n, (unsigned)g_sys_ticks_per_s, (long long)g_sys_off_ns,
        (int)(bool)Serial,
        (unsigned)getXtalFrequencyMhz(), (unsigned)getApbFrequency(), (unsigned)getCpuFrequencyMhz(),
        (unsigned)g_boot_id, (long long)esp_timer_get_time());
}

// PING <host_ns>  ->  PONG <host_ns> <esp_us_rx> <esp_us_tx> B rx=<P|L> rx_ns=<ns> tx_ns=<ns>
//                                                     sof=<frame11> sof_ns=<ns> sof_w=<ns>
//   esp_us_rx: when the PING arrived. Always "B" (estimated): there is no UART RX pin to capture.
//              rx=P: rising edge of the USB OUT-packet-received flag seen by the core-0 poller
//              (end of the OUT transaction, + poll latency ~0.1-0.3 us). rx=L: when loop() first saw
//              the byte (later by the HWCDC ISR + queue + loop latency, typically a few to tens of us).
//   esp_us_tx: just before the PONG is written to the (empty) HWCDC TX buffer.
//   sof=...:   latest accepted SOF frame-number change before the PONG (sof=-1 if none yet).
static void handle_ping(const char *host_tok) {
  int64_t rx_ns = g_line_rx_ns;
  char src = g_line_rx_src;
  Serial.flush();  // TX buffer empty, so the PONG follows the stamp without queueing behind events
  SofSample s;
  sof_read(&s);
  int64_t tx_ns = fine_ns();
  reply("PONG %s %lld %lld B rx=%c rx_ns=%lld tx_ns=%lld sof=%d sof_ns=%lld sof_w=%u", host_tok,
        (long long)(rx_ns / 1000), (long long)(tx_ns / 1000), src, (long long)rx_ns, (long long)tx_ns,
        (int)s.frame, (long long)s.esp_ns, (unsigned)s.w_ns);
}

static void handle_line(char *line, size_t len) {
  for (size_t i = 0; i < len; i++) line[i] = (char)toupper((unsigned char)line[i]);
  char *tok[8];
  int nt = 0;
  for (char *p = strtok(line, " \t"); p && nt < 8; p = strtok(NULL, " \t")) tok[nt++] = p;
  if (nt == 0) return;
  int base = 0;
  g_tag[0] = 0;
  if (tok[0][0] == '#') {
    strncpy(g_tag, tok[0], sizeof(g_tag) - 1);
    g_tag[sizeof(g_tag) - 1] = 0;
    base = 1;
  }
  if (nt <= base) return;
  const char *cmd = tok[base];
  char **arg = tok + base + 1;
  int na = nt - base - 1;
  const char *err;
  uint32_t a, b, c, d = 0;

  if (!strcmp(cmd, "PING")) {
    if (na < 1 || !is_int_token(arg[0])) return reply("ERR PING need_host_ns");
    return handle_ping(arg[0]);
  }
  if (!strcmp(cmd, "STATUS")) return print_status();
  if (!strcmp(cmd, "VERSION"))
    return reply("OK VERSION %s %s core=%d.%d.%d", FW_NAME, FW_VERSION, ESP_ARDUINO_VERSION_MAJOR,
                 ESP_ARDUINO_VERSION_MINOR, ESP_ARDUINO_VERSION_PATCH);
  if (!strcmp(cmd, "HELP"))
    return reply("OK HELP PING <host_ns> | STATUS | VERSION | "
                 "MODE STROBE <period_us> <width_us> <phase_us> [gap_us] | MODE OFF | "
                 "STROBE <period_us> <width_us> <phase_us> [gap_us] | STROBE OFF | "
                 "FSIN <period_us> <width_us> [phase_us] | FSIN OFF | START | STOP | ANCHOR | EVENTS ON|OFF "
                 "(no LED bar on this board: BAR, STEP, MODE CODE are unsupported)");

  // LED bar commands: this board has no bar.
  if (!strcmp(cmd, "STEP") || !strcmp(cmd, "BAR")) return reply("ERR %s unsupported", cmd);

  if (!strcmp(cmd, "STROBE")) {
    if (na >= 1 && !strcmp(arg[0], "OFF")) {
      g_cfg.strobe_on = false;
      if (g_running) gen_hold_low(g_gen_strobe);
      return reply("OK STROBE OFF");
    }
    if (na < 3 || !parse_u32(arg[0], &a) || !parse_u32(arg[1], &b) || !parse_u32(arg[2], &c) ||
        (na >= 4 && !parse_u32(arg[3], &d)))
      return reply("ERR STROBE need_period_width_phase");
    if ((err = check_strobe(a, b, c, d))) return reply("ERR STROBE %s", err);
    g_cfg.strobe_on = true;
    g_cfg.strobe_period_us = a;
    g_cfg.strobe_width_us = b;
    g_cfg.strobe_phase_us = c;
    g_cfg.strobe_gap_us = d;
    return reply("OK STROBE %u %u %u %u applies_at=START", (unsigned)a, (unsigned)b, (unsigned)c, (unsigned)d);
  }
  if (!strcmp(cmd, "FSIN")) {
    if (na >= 1 && !strcmp(arg[0], "OFF")) {
      g_cfg.fsin_on = false;
      if (g_running) gen_hold_low(g_gen_fsin);
      return reply("OK FSIN OFF");
    }
    if (na < 2 || !parse_u32(arg[0], &a) || !parse_u32(arg[1], &b) || (na >= 3 && !parse_u32(arg[2], &d)))
      return reply("ERR FSIN need_period_width");
    if ((err = check_fsin(a, b, d))) return reply("ERR FSIN %s", err);
    g_cfg.fsin_on = true;
    g_cfg.fsin_period_us = a;
    g_cfg.fsin_width_us = b;
    g_cfg.fsin_phase_us = d;
    return reply("OK FSIN %u %u %u applies_at=START", (unsigned)a, (unsigned)b, (unsigned)d);
  }
  if (!strcmp(cmd, "MODE")) {
    if (na < 1) return reply("ERR MODE need_CODE_STROBE_OFF");  // classic string kept for parity
    if (!strcmp(arg[0], "OFF")) {
      stop_outputs();
      return reply("OK MODE OFF");
    }
    if (!strcmp(arg[0], "CODE")) return reply("ERR MODE unsupported");
    if (strcmp(arg[0], "STROBE")) return reply("ERR MODE unknown_mode");
    if (na < 4 || !parse_u32(arg[1], &a) || !parse_u32(arg[2], &b) || !parse_u32(arg[3], &c) ||
        (na >= 5 && !parse_u32(arg[4], &d)))
      return reply("ERR MODE need_period_width_phase");
    if ((err = check_strobe(a, b, c, d))) return reply("ERR MODE %s", err);
    g_cfg.strobe_on = true;
    g_cfg.strobe_period_us = a;
    g_cfg.strobe_width_us = b;
    g_cfg.strobe_phase_us = c;
    g_cfg.strobe_gap_us = d;
    if ((err = start_outputs())) return reply("ERR MODE %s", err);
    return reply("OK MODE STROBE step_us=0");
  }
  if (!strcmp(cmd, "START")) {
    if ((err = start_outputs())) return reply("ERR START %s", err);
    return reply("OK START step_us=0 bar=NONE strobe=%d fsin=%d", (int)g_cfg.strobe_on, (int)g_cfg.fsin_on);
  }
  if (!strcmp(cmd, "STOP")) {
    stop_outputs();
    drain_events();
    return reply("OK STOP le_events=0 strobe_k=%u fsin_k=%u", (unsigned)g_strobe_k, (unsigned)g_fsin_k);
  }
  if (!strcmp(cmd, "ANCHOR")) {
    if (!clock_anchor(false)) return reply("ERR ANCHOR soft_catch_failed");
    return reply("OK ANCHOR %lld %lld %lld %lld", (long long)g_unwrap_ticks64, (long long)g_unwrap_esp_ns,
                 (long long)g_anchor_resid_ns, (long long)g_anchor_half_ns);
  }
  if (!strcmp(cmd, "EVENTS")) {
    if (na < 1) return reply("ERR EVENTS need_ON_OFF");
    g_events_on = !strcmp(arg[0], "ON");
    return reply("OK EVENTS %s", g_events_on ? "ON" : "OFF");
  }
  reply("ERR %s unknown_command", cmd);
}

static void poll_serial() {
  while (Serial.available() > 0) {
    int ch = Serial.read();
    if (ch < 0) break;
    if (g_line_len == 0 && !g_line_overflow && ch != '\n' && ch != '\r') {
      // First byte of a new line: prefer the poller's OUT-packet stamp if it is new and plausible.
      int64_t seen = fine_ns(), pkt_ns;
      uint32_t pkt_n;
      pkt_read(&pkt_ns, &pkt_n);
      if (pkt_n != 0 && pkt_n != g_pkt_n_used && pkt_ns <= seen && seen - pkt_ns < 2000000LL) {
        g_line_rx_ns = pkt_ns;
        g_line_rx_src = 'P';
        g_pkt_n_used = pkt_n;
      } else {
        g_line_rx_ns = seen;
        g_line_rx_src = 'L';
      }
    }
    if (ch == '\n' || ch == '\r') {
      if (g_line_overflow) {
        reply("ERR LINE too_long");
      } else if (g_line_len > 0) {
        g_line[g_line_len] = 0;
        handle_line(g_line, g_line_len);
      }
      g_line_len = 0;
      g_line_overflow = false;
      continue;
    }
    if (g_line_len < CMD_LINE_MAX) g_line[g_line_len++] = (char)ch;
    else g_line_overflow = true;
  }
}

// =====================================================================================
// Event output
// =====================================================================================

static void drain_events() {
  CapEvent ev;
  while (xQueueReceive(g_evq, &ev, 0) == pdTRUE) {
    if (!g_anchor_valid) continue;
    int64_t t0 = cap_to_esp_ns(ev.t0);
    switch (ev.type) {
      case EVT_EPOCH:
        g_epoch_ns = t0 + (int64_t)EPOCH_DELAY_US * 1000;
        g_epoch_valid = true;
        if (g_events_on) Serial.printf("EV A 0 %lld\n", (long long)g_epoch_ns);
        break;
      case EVT_STROBE: {
        // In double mode a stray pulse 2 can precede the first pulse 1 when phase is near the period end
        // (the up/down timer passes the down-count compares before reaching tA). Drop it so k parity holds.
        if (g_epoch_valid && t0 < g_epoch_ns + g_run_strobe_phase_ns - PRE_EPOCH_MARGIN_NS) {
          g_pre_epoch_drops++;
          break;
        }
        uint32_t k = g_strobe_k++;
        if (g_events_on) Serial.printf("EV S %u %lld %lld\n", (unsigned)k, (long long)t0, (long long)cap_to_esp_ns(ev.t1));
        break;
      }
      case EVT_FSIN: {
        uint32_t k = g_fsin_k++;
        if (g_events_on) Serial.printf("EV F %u %lld\n", (unsigned)k, (long long)t0);
        break;
      }
    }
  }
  uint32_t ovf = g_evq_overflow;
  if (ovf != g_ovf_reported) {
    Serial.printf("EV E OVF %u\n", (unsigned)ovf);
    g_ovf_reported = ovf;
  }
}

static void poll_sof_event() {
  uint32_t now = millis();
  if (now - g_last_sof_event_ms < SOF_EVENT_PERIOD_MS) return;
  g_last_sof_event_ms = now;
  SofSample s;
  sof_read(&s);
  if (!g_events_on || s.n == 0 || s.n == g_sof_last_event_n) return;
  g_sof_last_event_n = s.n;
  Serial.printf("EV U %d %lld %u\n", (int)s.frame, (long long)s.esp_ns, (unsigned)s.w_ns);
}

static void poll_button() {
  bool level = digitalRead(PIN_BUTTON);
  uint32_t now = millis();
  if (level != g_btn_last && now - g_btn_change_ms > 20) {
    g_btn_change_ms = now;
    g_btn_last = level;
    if (!level && g_events_on) Serial.printf("EV BTN %lld\n", (long long)fine_ns());
  }
}

// =====================================================================================
// Arduino entry points
// =====================================================================================

void setup() {
  // Outputs safe first. The strobe/FSIN gates also have external 100k pull-downs.
  pinMode(PIN_IR, OUTPUT);
  digitalWrite(PIN_IR, LOW);
  pinMode(PIN_BUTTON, INPUT_PULLUP);

  Serial.setRxBufferSize(1024);
  Serial.setTxBufferSize(2048);
  Serial.begin(SERIAL_BAUD);  // HWCDC: the ISR is allocated on this core (1)
  Serial.setTxTimeoutMs(SERIAL_TX_TIMEOUT_MS);
  // Wi-Fi and Bluetooth are never started by this sketch.

  g_cpu_mhz = getCpuFrequencyMhz();
  g_sys_ticks_per_s = (uint32_t)systimer_us_to_ticks(1000000);
  measure_sys_offset();
  g_boot_id = esp_random();
  g_evq = xQueueCreate(EVENT_QUEUE_LEN, sizeof(CapEvent));

  // Capture channels are created from a task on CAPTURE_CORE so their ISRs run there.
  xTaskCreatePinnedToCore(capture_init_task, "cap_init", 4096, xTaskGetCurrentTaskHandle(), 5, NULL, CAPTURE_CORE);
  ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(2000));
  bool cap_ok = (g_capture_init_err == ESP_OK);
  if (!cap_ok) Serial.printf("EV E INIT capture %s\n", esp_err_to_name(g_capture_init_err));

  bool pwm_ok = (pwm_init() == ESP_OK);
  g_hw_ok = cap_ok && pwm_ok;
  if (cap_ok) clock_anchor(false);
  g_last_anchor_ms = millis();

  xTaskCreatePinnedToCore(sof_task, "sof_poll", 3072, NULL, SOF_TASK_PRIO, NULL, CAPTURE_CORE);

  led_set(g_hw_ok ? 0 : 2);
  Serial.printf("EV B %08x %s %s hw_ok=%d\n", (unsigned)g_boot_id, FW_NAME, FW_VERSION, (int)g_hw_ok);
}

void loop() {
  poll_serial();
  drain_events();
  poll_sof_event();
  poll_button();
  if (g_hw_ok && millis() - g_last_anchor_ms >= ANCHOR_INTERVAL_MS) {
    g_last_anchor_ms = millis();
    clock_anchor(true);
  }
}
