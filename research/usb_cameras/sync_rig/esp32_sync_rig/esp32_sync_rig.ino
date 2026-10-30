/*
  esp32_sync_rig.ino -- ESP32 timing / sync test rig for the USB camera research (DRAFT)

  Status: first draft. Compiles for esp32:esp32:esp32 (see ../README.md for the exact check),
  never flashed, never run on hardware, nothing measured. Treat every timing claim in the
  comments as a design intent to be verified with a logic analyzer (README "Bring-up").

  What it does (classic ESP32-WROOM-32 DevKit, Arduino-ESP32 core 3.x = ESP-IDF 5.x drivers):
    - LED time-code bar: 128 channels of daisy-chained 16-bit constant-current sink drivers
      (STP16CP05 / TLC5926 / MBI5026). A one-hot "fine" bar (100 LEDs) steps every STEP us,
      a 20-bit Gray counter counts fine-bar revolutions, 4 fiducials are always on.
      Outputs change together on the LE (latch) edge, which is an MCPWM hardware edge.
    - Strobe: one MOSFET-switched LED, single or double pulse per period, with a phase
      relative to the code epoch. Hardware edges (MCPWM generator), width/duty capped.
    - FSIN: optional trigger output (two pins, same waveform) for cameras with a frame-sync input.
    - Every timing-critical edge (strobe, LE or FSIN, UART RX start bit) is wired back to an
      MCPWM capture input and timestamped by the 80 MHz capture timer (12.5 ns ticks).
    - Line-based serial protocol (921600 baud): PING/PONG for host clock correlation,
      MODE/STEP/BAR/STROBE/FSIN/START/STOP/STATUS, and unsolicited "EV ..." event lines.

  Timebases:
    - esp_timer_get_time(): 64-bit microseconds since boot. This is THE reported timebase.
    - MCPWM capture timer: 32-bit, 80 MHz (APB). Captured edges are converted to esp_timer
      nanoseconds through a software anchor (soft-catch bracketed by two esp_timer reads),
      so events are reported as "esp_ns" (esp_timer microseconds * 1000 plus sub-us part).
    - MCPWM PWM timers: 2 MHz (0.5 us ticks) from the 160 MHz PLL clock. They are not read
      directly; their edges are captured through the loopback wires.

  Not done in this draft (see README "Open TODOs"): S3 USB SOF lock, LCD_CAM DMA for the bar,
  protocol-2 "<...>" framing from ../../../arduino_sync/PLAN.md, frequency sweep command.
*/

#include <Arduino.h>
#include "esp_arduino_version.h"

#if !defined(ESP_ARDUINO_VERSION_MAJOR) || ESP_ARDUINO_VERSION_MAJOR < 3
#error "This sketch needs Arduino-ESP32 core 3.x (it calls the ESP-IDF 5.x MCPWM / SPI drivers)."
#endif
#if !CONFIG_IDF_TARGET_ESP32
#error "Pin map and capture layout are for the classic ESP32 (ESP32-WROOM-32 DevKit). See README for S3 notes."
#endif

#include "driver/mcpwm_prelude.h"
#include "driver/spi_master.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"

// =====================================================================================
// Configuration: every pin and constant lives here
// =====================================================================================

#define FW_NAME    "esp32_sync_rig"
#define FW_VERSION "0.1.0-draft"

// ---- Serial link (UART0 through the DevKit's CP2102 / CH340) ----
static const uint32_t SERIAL_BAUD = 921600;
static const uint8_t SERIAL_RX_TIMEOUT_SYMBOLS = 2;  // UART RX idle timeout before bytes reach the ring buffer
static const size_t CMD_LINE_MAX = 96;                   // longest accepted command line

// ---- Pins (classic ESP32 DevKit; strapping 0/2/5/12/15, flash 6-11, 14, 16/17 avoided) ----
static const int PIN_SPI_SCLK = 18;     // VSPI IOMUX SCLK -> driver CLK (33 ohm series)
static const int PIN_SPI_MOSI = 23;     // VSPI IOMUX MOSI -> driver SDI
static const int PIN_LE = 21;           // latch enable, MCPWM0 timer0 generator; loop back to PIN_CAP_LE_FSIN
static const int PIN_OE_N = 22;         // driver /OE, 10k pull-up so the bar is dark at boot. Never PWM it.
static const int PIN_STROBE = 25;       // strobe MOSFET gate, MCPWM0 timer1 generator; loop back to PIN_CAP_STROBE
static const int PIN_FSIN1 = 26;        // FSIN sink gate 1, MCPWM0 timer2 generator A
static const int PIN_FSIN2 = 27;        // FSIN sink gate 2, MCPWM0 timer2 generator B
static const int PIN_CAP_LE_FSIN = 34;  // capture 1 input (input-only pin): LE loopback or FSIN1 loopback
static const int PIN_CAP_STROBE = 35;   // capture 0 input (input-only pin): strobe loopback
static const int PIN_CAP_UART_RX = 39;  // capture 2 input (input-only pin): wire from GPIO3 (UART0 RX)
static const int PIN_CAP_SOFT_ONLY = 19;  // capture 2 input when USE_RX_EDGE_CAPTURE == 0 (nothing wired)
static const int PIN_SYNC = 4;          // internal MCPWM sync trigger (GPIO loopback); leave unconnected,
                                        // its rising edge marks START on a logic analyzer
static const int PIN_BUTTON = 32;       // start/mark button to GND (internal pull-up)
static const int PIN_STATUS_LED = 33;   // on while outputs run
// GPIO36 (ADC1) is reserved for the optional photodiode; this draft does not read it.

// ---- Feature switches ----
// Capture channel 1 can watch either the LE loopback (start-up epoch anchor) or FSIN1.
// The design shares GPIO34 between them; pick one per build until FSIN hardware exists.
// Both switches can also be set from the build, e.g. --build-property "compiler.cpp.extra_flags=-DCAP1_ROLE=1".
#define CAP1_ROLE_LE_ANCHOR 0
#define CAP1_ROLE_FSIN 1
#ifndef CAP1_ROLE
#define CAP1_ROLE CAP1_ROLE_LE_ANCHOR
#endif
// 1: timestamp the UART RX start bit of each PING on capture 2 (needs the GPIO3 -> GPIO39 wire).
// 0: estimate the RX time from when the line was read (worse, documented in PONG field 4).
#ifndef USE_RX_EDGE_CAPTURE
#define USE_RX_EDGE_CAPTURE 1
#endif

// ---- MCPWM timebase ----
static const uint32_t PWM_RES_HZ = 2000000;                   // all three PWM timers: 0.5 us ticks
static const uint32_t TICKS_PER_US = PWM_RES_HZ / 1000000;    // 2
static const uint32_t LE_PULSE_TICKS = 2;                     // 1 us latch pulse
static const uint32_t FIRST_EDGE_TICKS = 64;                  // single-pulse rise position in the up/down cycle
static const uint32_t CAP_RES_HZ = 80000000;                  // capture timer = APB clock on ESP32
static const uint32_t RX_IDLE_GAP_US = 100;                   // RX line quiet this long -> next edge starts a new line
static const uint32_t RX_IDLE_GAP_TICKS = RX_IDLE_GAP_US * (CAP_RES_HZ / 1000000);

// ---- Limits (checked on every command) ----
static const uint32_t STEP_MIN_US = 50;              // render deadline: 128 bits at 10 MHz + task switch
static const uint32_t STEP_MAX_US = 32767;           // up-count timer: period <= 65535 ticks
static const uint32_t PERIOD_MIN_US = 1000;
static const uint32_t PERIOD_MAX_US = 65535;         // up/down timer: peak <= 65535 ticks
static const uint32_t STROBE_WIDTH_MAX_US = 500;     // hard cap (LED pulse rating, eye comfort)
static const uint32_t STROBE_DUTY_MAX_PERMILLE = 10; // 1 %
static const uint32_t FSIN_WIDTH_MIN_US = 1;

// ---- LED bar layout (channel numbers; channel 0 = last bit shifted = driver nearest the ESP32, OUT0) ----
static const uint32_t N_FINE = 100;      // one-hot fine bar
static const uint32_t N_GRAY = 20;       // Gray-coded revolution counter
static const uint32_t N_FIDUCIAL = 4;    // always lit (except DARK)
static const uint32_t CH_FINE0 = 0;
static const uint32_t CH_GRAY0 = 100;
static const uint32_t CH_FID0 = 120;
static const uint32_t CH_MODE = 124;     // lit in CODE mode, so a decoder can tell CODE from ALLON/ALLOFF
static const uint32_t N_CHANNELS = 128;  // 8 drivers x 16
static const size_t BAR_BYTES = N_CHANNELS / 8;
static const int SPI_CLOCK_HZ = 10000000;

// ---- Tasks ----
static const UBaseType_t RENDER_TASK_PRIO = configMAX_PRIORITIES - 1;
static const BaseType_t RENDER_CORE = 1;   // LE ISR + render task (same core as setup/loop)
static const BaseType_t CAPTURE_CORE = 0;  // capture ISRs (keeps the RX edge burst off core 1)
static const uint32_t ANCHOR_INTERVAL_MS = 1000;
static const int ANCHOR_ATTEMPTS = 16;
static const UBaseType_t EVENT_QUEUE_LEN = 64;

// =====================================================================================
// Types
// =====================================================================================

enum BarMode : uint8_t { BAR_DARK = 0, BAR_CODE, BAR_ALLON, BAR_ALLOFF };

struct RigConfig {
  uint32_t step_us;  // fine-bar step = LE period = code timebase
  BarMode bar;
  bool strobe_on;
  uint32_t strobe_period_us, strobe_width_us, strobe_phase_us, strobe_gap_us;  // gap 0 = single pulse
  bool fsin_on;
  uint32_t fsin_period_us, fsin_width_us, fsin_phase_us;
};

enum EventType : uint8_t { EVT_STROBE = 0, EVT_FSIN, EVT_LE };

struct CapEvent {
  uint8_t type;
  uint32_t k;   // pulse index since START
  uint32_t t0;  // capture ticks (rise)
  uint32_t t1;  // capture ticks (fall, strobe only)
};

// =====================================================================================
// State
// =====================================================================================

static RigConfig g_cfg = {100, BAR_DARK, false, 33333, 50, 0, 0, false, 20800, 100, 0};
static bool g_running = false;
static bool g_events_on = true;
static bool g_hw_ok = false;
static uint32_t g_boot_id = 0;

// MCPWM handles (group 0 for everything, so all edges share one clock tree)
static mcpwm_timer_handle_t g_tmr_le, g_tmr_strobe, g_tmr_fsin;
static mcpwm_oper_handle_t g_op_le, g_op_strobe, g_op_fsin;
static mcpwm_cmpr_handle_t g_cmp_le, g_cmp_sa, g_cmp_sb, g_cmp_fa, g_cmp_fb;
static mcpwm_gen_handle_t g_gen_le, g_gen_strobe, g_gen_fsin1, g_gen_fsin2;
static mcpwm_sync_handle_t g_sync;
static mcpwm_cap_timer_handle_t g_cap_timer;
static mcpwm_cap_channel_handle_t g_cap0, g_cap1, g_cap2;
static uint32_t g_cap_res_hz = CAP_RES_HZ;
static volatile esp_err_t g_capture_init_err = ESP_FAIL;

static spi_device_handle_t g_spi;
static TaskHandle_t g_render_task;
static QueueHandle_t g_evq;

// Shared with ISRs (32-bit aligned, written by one side only unless noted)
static volatile bool g_bar_dynamic = false;     // render task active (CODE mode while running)
static volatile uint32_t g_le_events = 0;       // LE edges since START = index of next pattern to latch
static volatile uint32_t g_ready_index = 0;     // pattern index sitting in the shift registers
static volatile uint32_t g_late_count = 0, g_late_last = 0;
static volatile uint32_t g_strobe_k = 0, g_fsin_k = 0, g_evq_overflow = 0;
static volatile uint32_t g_strobe_rise = 0;
static volatile bool g_strobe_have_rise = false;
static volatile bool g_le_anchor_armed = false;
static volatile bool g_soft_pending = false, g_soft_done = false;
static volatile uint32_t g_soft_ticks = 0;
static volatile uint32_t g_rx_last_edge = 0, g_rx_burst_start = 0;
static volatile uint32_t g_rx_burst_seq = 0;    // seqlock: odd while the ISR writes g_rx_burst_start

// Capture-timer <-> esp_timer mapping (loop context only)
static bool g_anchor_valid = false;
static int64_t g_anchor0_ticks64 = 0, g_anchor0_esp_ns = 0;  // fixed offset, set once at boot
static int64_t g_anchor0_half_ns = 0;
static int64_t g_unwrap_ticks64 = 0, g_unwrap_esp_ns = 0;    // latest anchor, used to unwrap 32-bit captures
static int64_t g_anchor_resid_ns = 0, g_anchor_half_ns = 0;
static uint32_t g_last_anchor_ms = 0;

// LE epoch (first LE edge after START), loop context only
static bool g_le0_valid = false;
static int64_t g_le0_esp_ns = 0;

// Reporting state
static uint32_t g_late_reported = 0, g_ovf_reported = 0;

// Serial line assembly
static char g_line[CMD_LINE_MAX + 1];
static size_t g_line_len = 0;
static bool g_line_overflow = false;
static int64_t g_line_first_us = 0;
static bool g_line_burst_ok = false;
static uint32_t g_line_burst_t32 = 0;

// Button
static bool g_btn_last = true;
static uint32_t g_btn_change_ms = 0;

// =====================================================================================
// Small helpers
// =====================================================================================

static const char *bar_mode_name(BarMode m) {
  switch (m) {
    case BAR_CODE: return "CODE";
    case BAR_ALLON: return "ALLON";
    case BAR_ALLOFF: return "ALLOFF";
    default: return "DARK";
  }
}

// Convert a tick difference to ns without 64-bit overflow for multi-day spans.
static int64_t ticks_to_ns(int64_t d, uint32_t res_hz) {
  int64_t whole = d / (int64_t)res_hz, rem = d % (int64_t)res_hz;
  return whole * 1000000000LL + rem * 1000000000LL / (int64_t)res_hz;
}

static int64_t ns_to_ticks(int64_t ns, uint32_t res_hz) {
  int64_t whole = ns / 1000000000LL, rem = ns % 1000000000LL;
  return whole * (int64_t)res_hz + rem * (int64_t)res_hz / 1000000000LL;
}

// 32-bit capture value -> esp_timer nanoseconds (requires g_anchor_valid).
// The 32-bit counter wraps every ~53.7 s; it is unwrapped against the latest periodic anchor
// (taken every ANCHOR_INTERVAL_MS), then mapped with the fixed boot offset and the nominal rate.
static int64_t cap_to_esp_ns(uint32_t t32) {
  int64_t t64 = g_unwrap_ticks64 + (int32_t)(t32 - (uint32_t)g_unwrap_ticks64);
  return g_anchor0_esp_ns + ticks_to_ns(t64 - g_anchor0_ticks64, g_cap_res_hz);
}

// =====================================================================================
// LED bar: pattern + SPI
// =====================================================================================

static inline void bar_set(uint8_t *buf, uint32_t ch) {
  // SPI sends byte 0 first, MSB first. The first bit sent ends up furthest down the chain,
  // so channel c (0 = nearest driver OUT0) is transmit bit position 127 - c.
  // VERIFY on hardware with "STEP 32000" + "MODE CODE": the fine LED must walk 0 -> 99.
  uint32_t p = (N_CHANNELS - 1) - ch;
  buf[p >> 3] |= (uint8_t)(0x80u >> (p & 7));
}

static void build_pattern(uint32_t idx, BarMode mode, uint8_t *buf) {
  memset(buf, 0, BAR_BYTES);
  if (mode == BAR_DARK) return;
  for (uint32_t i = 0; i < N_FIDUCIAL; i++) bar_set(buf, CH_FID0 + i);
  if (mode == BAR_CODE) {
    bar_set(buf, CH_FINE0 + (idx % N_FINE));
    uint32_t rev = idx / N_FINE;
    uint32_t gray = rev ^ (rev >> 1);
    for (uint32_t b = 0; b < N_GRAY; b++)
      if ((gray >> b) & 1u) bar_set(buf, CH_GRAY0 + b);
    bar_set(buf, CH_MODE);
  } else if (mode == BAR_ALLON) {
    for (uint32_t i = 0; i < N_FINE; i++) bar_set(buf, CH_FINE0 + i);
    for (uint32_t b = 0; b < N_GRAY; b++) bar_set(buf, CH_GRAY0 + b);
  }
  // BAR_ALLOFF: fiducials only, so the decoder can still find the board in the dark frame.
}

static void bar_send(const uint8_t *buf) {
  spi_transaction_t t;
  memset(&t, 0, sizeof(t));
  t.length = BAR_BYTES * 8;
  t.tx_buffer = buf;
  spi_device_polling_transmit(g_spi, &t);  // ~13 us of clocking at 10 MHz
}

static void bar_output_enable(bool on) {
  digitalWrite(PIN_OE_N, on ? LOW : HIGH);
}

// Render task: after every LE, shift in the pattern for the NEXT LE. Highest priority on core 1.
static void render_task(void *) {
  uint8_t buf[BAR_BYTES];
  for (;;) {
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    if (!g_bar_dynamic) continue;
    uint32_t next = g_le_events;  // the next LE latches pattern number `next`
    build_pattern(next, BAR_CODE, buf);
    bar_send(buf);
    g_ready_index = next;
  }
}

// =====================================================================================
// ISRs (IRAM, no serial, no blocking)
// =====================================================================================

// LE falling edge (comparator on timer 0). The latch is closed again, so shifting is safe.
static bool IRAM_ATTR on_le_fall(mcpwm_cmpr_handle_t, const mcpwm_compare_event_data_t *, void *) {
  uint32_t k = g_le_events;  // pattern number that was just latched
  g_le_events = k + 1;
  BaseType_t woken = pdFALSE;
  if (g_bar_dynamic) {
    if (g_ready_index != k) {  // missed deadline: stale or half-shifted data was latched
      g_late_count = g_late_count + 1;
      g_late_last = k;
    }
    vTaskNotifyGiveFromISR(g_render_task, &woken);
  }
  return woken == pdTRUE;
}

static bool IRAM_ATTR on_cap_strobe(mcpwm_cap_channel_handle_t, const mcpwm_capture_event_data_t *e, void *) {
  BaseType_t woken = pdFALSE;
  if (e->cap_edge == MCPWM_CAP_EDGE_POS) {
    g_strobe_rise = e->cap_value;
    g_strobe_have_rise = true;
  } else if (g_strobe_have_rise) {
    CapEvent ev = {EVT_STROBE, g_strobe_k, g_strobe_rise, e->cap_value};
    g_strobe_k = g_strobe_k + 1;
    g_strobe_have_rise = false;
    if (xQueueSendFromISR(g_evq, &ev, &woken) != pdTRUE) g_evq_overflow = g_evq_overflow + 1;
  }
  return woken == pdTRUE;
}

static bool IRAM_ATTR on_cap1(mcpwm_cap_channel_handle_t, const mcpwm_capture_event_data_t *e, void *) {
  BaseType_t woken = pdFALSE;
#if CAP1_ROLE == CAP1_ROLE_LE_ANCHOR
  // LE edges arrive every STEP us; only the armed one is reported.
  if (!g_le_anchor_armed) return false;
  g_le_anchor_armed = false;
  CapEvent ev = {EVT_LE, 0, e->cap_value, 0};
#else
  CapEvent ev = {EVT_FSIN, g_fsin_k, e->cap_value, 0};
  g_fsin_k = g_fsin_k + 1;
#endif
  if (xQueueSendFromISR(g_evq, &ev, &woken) != pdTRUE) g_evq_overflow = g_evq_overflow + 1;
  return woken == pdTRUE;
}

// Capture 2: software anchor catches, and (optionally) UART RX falling edges.
static bool IRAM_ATTR on_cap2(mcpwm_cap_channel_handle_t, const mcpwm_capture_event_data_t *e, void *) {
  uint32_t t = e->cap_value;
  if (g_soft_pending) {
    g_soft_ticks = t;
    g_soft_pending = false;
    g_soft_done = true;
    return false;
  }
#if USE_RX_EDGE_CAPTURE
  // The first falling edge after a quiet gap is the start bit of the first byte of a line.
  if ((uint32_t)(t - g_rx_last_edge) > RX_IDLE_GAP_TICKS) {
    g_rx_burst_seq = g_rx_burst_seq + 1;  // odd: writing
    g_rx_burst_start = t;
    g_rx_burst_seq = g_rx_burst_seq + 1;  // even: stable
  }
  g_rx_last_edge = t;
#endif
  return false;
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

// Runs on CAPTURE_CORE so the capture interrupts are allocated there.
static esp_err_t capture_init() {
  mcpwm_capture_timer_config_t tc;
  memset(&tc, 0, sizeof(tc));
  tc.group_id = 0;
  tc.clk_src = MCPWM_CAPTURE_CLK_SRC_DEFAULT;  // APB 80 MHz on ESP32
  tc.resolution_hz = CAP_RES_HZ;
  esp_err_t e = mcpwm_new_capture_timer(&tc, &g_cap_timer);
  if (e != ESP_OK) return e;

  mcpwm_capture_channel_config_t cc;
  mcpwm_capture_event_callbacks_t cb;

  memset(&cc, 0, sizeof(cc));
  cc.gpio_num = PIN_CAP_STROBE;
  cc.prescale = 1;
  cc.flags.pos_edge = 1;
  cc.flags.neg_edge = 1;
  if ((e = mcpwm_new_capture_channel(g_cap_timer, &cc, &g_cap0)) != ESP_OK) return e;
  cb.on_cap = on_cap_strobe;
  if ((e = mcpwm_capture_channel_register_event_callbacks(g_cap0, &cb, NULL)) != ESP_OK) return e;

  memset(&cc, 0, sizeof(cc));
  cc.gpio_num = PIN_CAP_LE_FSIN;
  cc.prescale = 1;
  cc.flags.pos_edge = 1;
  if ((e = mcpwm_new_capture_channel(g_cap_timer, &cc, &g_cap1)) != ESP_OK) return e;
  cb.on_cap = on_cap1;
  if ((e = mcpwm_capture_channel_register_event_callbacks(g_cap1, &cb, NULL)) != ESP_OK) return e;

  memset(&cc, 0, sizeof(cc));
#if USE_RX_EDGE_CAPTURE
  cc.gpio_num = PIN_CAP_UART_RX;
#else
  cc.gpio_num = PIN_CAP_SOFT_ONLY;
  cc.flags.pull_down = 1;
#endif
  cc.prescale = 1;
  cc.flags.neg_edge = 1;  // UART start bit
  if ((e = mcpwm_new_capture_channel(g_cap_timer, &cc, &g_cap2)) != ESP_OK) return e;
  cb.on_cap = on_cap2;
  if ((e = mcpwm_capture_channel_register_event_callbacks(g_cap2, &cb, NULL)) != ESP_OK) return e;

  if ((e = mcpwm_capture_channel_enable(g_cap0)) != ESP_OK) return e;
  if ((e = mcpwm_capture_channel_enable(g_cap1)) != ESP_OK) return e;
  if ((e = mcpwm_capture_channel_enable(g_cap2)) != ESP_OK) return e;
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
  t.clk_src = MCPWM_TIMER_CLK_SRC_DEFAULT;  // PLL 160 MHz, same resolution for all three timers
  t.resolution_hz = PWM_RES_HZ;            // so one group prescaler fits them all
  t.count_mode = MCPWM_TIMER_COUNT_MODE_UP;
  t.period_ticks = g_cfg.step_us * TICKS_PER_US;
  TRY(mcpwm_new_timer(&t, &g_tmr_le));
  t.count_mode = MCPWM_TIMER_COUNT_MODE_UP_DOWN;  // up/down: one cycle can hold a double pulse
  t.period_ticks = 2 * 33334;
  TRY(mcpwm_new_timer(&t, &g_tmr_strobe));
  TRY(mcpwm_new_timer(&t, &g_tmr_fsin));

  mcpwm_operator_config_t oc;
  memset(&oc, 0, sizeof(oc));
  oc.group_id = 0;
  TRY(mcpwm_new_operator(&oc, &g_op_le));
  TRY(mcpwm_new_operator(&oc, &g_op_strobe));
  TRY(mcpwm_new_operator(&oc, &g_op_fsin));
  TRY(mcpwm_operator_connect_timer(g_op_le, g_tmr_le));
  TRY(mcpwm_operator_connect_timer(g_op_strobe, g_tmr_strobe));
  TRY(mcpwm_operator_connect_timer(g_op_fsin, g_tmr_fsin));

  // Comparators update immediately (no shadow): values are only changed while outputs are held.
  mcpwm_comparator_config_t cc;
  memset(&cc, 0, sizeof(cc));
  TRY(mcpwm_new_comparator(g_op_le, &cc, &g_cmp_le));
  TRY(mcpwm_new_comparator(g_op_strobe, &cc, &g_cmp_sa));
  TRY(mcpwm_new_comparator(g_op_strobe, &cc, &g_cmp_sb));
  TRY(mcpwm_new_comparator(g_op_fsin, &cc, &g_cmp_fa));
  TRY(mcpwm_new_comparator(g_op_fsin, &cc, &g_cmp_fb));

  TRY(new_gen(g_op_le, PIN_LE, &g_gen_le));
  TRY(new_gen(g_op_strobe, PIN_STROBE, &g_gen_strobe));
  TRY(new_gen(g_op_fsin, PIN_FSIN1, &g_gen_fsin1));
  TRY(new_gen(g_op_fsin, PIN_FSIN2, &g_gen_fsin2));

  // LE: high at counter zero, low LE_PULSE_TICKS later. The comparator event drives the render ISR.
  TRY(mcpwm_comparator_set_compare_value(g_cmp_le, LE_PULSE_TICKS));
  TRY(mcpwm_generator_set_action_on_timer_event(g_gen_le,
        MCPWM_GEN_TIMER_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP, MCPWM_TIMER_EVENT_EMPTY, MCPWM_GEN_ACTION_HIGH)));
  TRY(mcpwm_generator_set_action_on_compare_event(g_gen_le,
        MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP, g_cmp_le, MCPWM_GEN_ACTION_LOW)));
  mcpwm_comparator_event_callbacks_t ccb;
  memset(&ccb, 0, sizeof(ccb));
  ccb.on_reach = on_le_fall;
  TRY(mcpwm_comparator_register_event_callbacks(g_cmp_le, &ccb, NULL));

  // FSIN: rise at FIRST_EDGE_TICKS on the way up, fall `width` later. Both pins identical.
  TRY(mcpwm_generator_set_actions_on_compare_event(g_gen_fsin1,
        MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP, g_cmp_fa, MCPWM_GEN_ACTION_HIGH),
        MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP, g_cmp_fb, MCPWM_GEN_ACTION_LOW),
        MCPWM_GEN_COMPARE_EVENT_ACTION_END()));
  TRY(mcpwm_generator_set_actions_on_compare_event(g_gen_fsin2,
        MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP, g_cmp_fa, MCPWM_GEN_ACTION_HIGH),
        MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP, g_cmp_fb, MCPWM_GEN_ACTION_LOW),
        MCPWM_GEN_COMPARE_EVENT_ACTION_END()));

  // One sync input shared by all three timers: a GPIO sync source on PIN_SYNC with io_loop_back,
  // driven by software at START. (A soft sync source binds to a single timer in IDF 5.x.)
  mcpwm_gpio_sync_src_config_t sc;
  memset(&sc, 0, sizeof(sc));
  sc.group_id = 0;
  sc.gpio_num = PIN_SYNC;
  sc.flags.io_loop_back = 1;
  sc.flags.pull_down = 1;
  TRY(mcpwm_new_gpio_sync_src(&sc, &g_sync));
  TRY(gpio_set_direction((gpio_num_t)PIN_SYNC, GPIO_MODE_INPUT_OUTPUT));
  TRY(gpio_set_level((gpio_num_t)PIN_SYNC, 0));

  TRY(mcpwm_timer_enable(g_tmr_le));
  TRY(mcpwm_timer_enable(g_tmr_strobe));
  TRY(mcpwm_timer_enable(g_tmr_fsin));
  return ESP_OK;
}

static esp_err_t spi_init() {
  spi_bus_config_t bus;
  memset(&bus, 0, sizeof(bus));
  bus.mosi_io_num = PIN_SPI_MOSI;
  bus.miso_io_num = -1;
  bus.sclk_io_num = PIN_SPI_SCLK;
  bus.quadwp_io_num = -1;
  bus.quadhd_io_num = -1;
  bus.max_transfer_sz = BAR_BYTES;
  TRY(spi_bus_initialize(SPI3_HOST, &bus, SPI_DMA_DISABLED));  // VSPI
  spi_device_interface_config_t dev;
  memset(&dev, 0, sizeof(dev));
  dev.clock_speed_hz = SPI_CLOCK_HZ;
  dev.mode = 0;            // drivers sample SDI on the rising CLK edge
  dev.spics_io_num = -1;   // no CS: LE does the latching
  dev.queue_size = 1;
  TRY(spi_bus_add_device(SPI3_HOST, &dev, &g_spi));
  TRY(spi_device_acquire_bus(g_spi, portMAX_DELAY));  // keep the bus: lower per-transfer overhead
  return ESP_OK;
}

// =====================================================================================
// Clock anchor: capture timer <-> esp_timer
// =====================================================================================

// One soft catch bracketed by two esp_timer reads. Returns false if it could not get a tight bracket.
static bool soft_catch(uint32_t *ticks, int64_t *esp_ns_mid, int64_t *half_ns) {
  int64_t best_half = INT64_MAX;
  bool ok = false;
  for (int i = 0; i < ANCHOR_ATTEMPTS; i++) {
    g_soft_done = false;
    g_soft_pending = true;
    int64_t a = esp_timer_get_time();
    esp_err_t err = mcpwm_capture_channel_trigger_soft_catch(g_cap2);
    int64_t b = esp_timer_get_time();
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
    int64_t half = (b - a) * 500;  // ns
    if (half < best_half) {        // keep the tightest bracket
      best_half = half;
      *ticks = g_soft_ticks;
      *esp_ns_mid = (a + b) * 500;
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
    g_anchor0_half_ns = half;
    g_unwrap_ticks64 = t32;
    g_unwrap_esp_ns = mid;
    g_anchor_valid = true;
  } else {
    // predict the 64-bit tick count from esp_timer, then unwrap the 32-bit capture near it
    int64_t pred = g_unwrap_ticks64 + ns_to_ticks(mid - g_unwrap_esp_ns, g_cap_res_hz);
    int64_t t64 = pred + (int32_t)(t32 - (uint32_t)pred);
    g_unwrap_ticks64 = t64;
    g_unwrap_esp_ns = mid;
    // residual > a few us that keeps growing means the two clocks do not share a rate
    g_anchor_resid_ns = mid - (g_anchor0_esp_ns + ticks_to_ns(t64 - g_anchor0_ticks64, g_cap_res_hz));
  }
  g_anchor_half_ns = half;
  if (report && g_events_on)
    Serial.printf("EV K %lld %lld %lld %lld\n", (long long)g_unwrap_ticks64, (long long)g_unwrap_esp_ns,
                  (long long)g_anchor_resid_ns, (long long)half);
  return true;
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
  g_bar_dynamic = false;
  gen_hold_low(g_gen_strobe);
  gen_hold_low(g_gen_fsin1);
  gen_hold_low(g_gen_fsin2);
  gen_hold_low(g_gen_le);
  bar_output_enable(false);
  if (g_running) {
    mcpwm_timer_start_stop(g_tmr_le, MCPWM_TIMER_STOP_EMPTY);
    mcpwm_timer_start_stop(g_tmr_strobe, MCPWM_TIMER_STOP_EMPTY);
    mcpwm_timer_start_stop(g_tmr_fsin, MCPWM_TIMER_STOP_EMPTY);
    vTaskDelay(pdMS_TO_TICKS(PERIOD_MAX_US / 1000 + 5));  // let the up/down timers reach zero
  }
  g_running = false;
  digitalWrite(PIN_STATUS_LED, LOW);
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

// (Re)start every output from one common sync edge. Returns NULL or an error string.
//   epoch = first LE rising edge after the sync (reported as "EV A 0 <t>" when CAP1 watches LE)
//   strobe pulse 1 rises at epoch + phase + j * period; pulse 2 (double mode) gap later
//   FSIN rises at epoch + phase + j * period
static const char *start_outputs() {
  if (!g_hw_ok) return "hardware_init_failed";
  stop_outputs();

  // --- timer 0: LE / code timebase (up-count) ---
  uint32_t p0 = g_cfg.step_us * TICKS_PER_US;
  TRY_S(mcpwm_timer_set_period(g_tmr_le, p0));
  mcpwm_timer_sync_phase_config_t ph;
  memset(&ph, 0, sizeof(ph));
  ph.sync_src = g_sync;
  ph.count_value = 1;  // load 1, not 0, so the sync itself never looks like a counter-zero event
  ph.direction = MCPWM_TIMER_DIRECTION_UP;
  TRY_S(mcpwm_timer_set_phase_on_sync(g_tmr_le, &ph));
  uint32_t epoch_ticks = p0 - 1;  // sync -> first counter zero -> first LE rise

  // --- timer 1: strobe (up/down; pulse 1 on the way up, optional pulse 2 on the way down) ---
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

  // --- timer 2: FSIN (up/down, single pulse) ---
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

  // --- reset counters and preload bar pattern 0 (latched by the first LE) ---
  uint8_t buf[BAR_BYTES];
  g_late_count = 0;
  g_late_last = 0;
  g_late_reported = 0;
  g_strobe_k = 0;
  g_fsin_k = 0;
  g_strobe_have_rise = false;
  build_pattern(0, g_cfg.bar, buf);
  bar_send(buf);
  g_ready_index = 0;
  bar_output_enable(g_cfg.bar != BAR_DARK);
  g_le0_valid = false;
#if CAP1_ROLE == CAP1_ROLE_LE_ANCHOR
  g_le_anchor_armed = true;
#endif

  // --- start all three timers (outputs still held low), then align them with one sync edge ---
  TRY_S(mcpwm_timer_start_stop(g_tmr_le, MCPWM_TIMER_START_NO_STOP));
  TRY_S(mcpwm_timer_start_stop(g_tmr_strobe, MCPWM_TIMER_START_NO_STOP));
  TRY_S(mcpwm_timer_start_stop(g_tmr_fsin, MCPWM_TIMER_START_NO_STOP));
  gpio_set_level((gpio_num_t)PIN_SYNC, 1);
  gpio_set_level((gpio_num_t)PIN_SYNC, 0);
  // LE ISRs that fired between start and sync do not count. Wait a moment so a pending one has
  // run, then reset. The first real LE is (step - 0.5 us) >= 49.5 us after the sync.
  delayMicroseconds(5);
  g_le_events = 0;
  g_bar_dynamic = (g_cfg.bar == BAR_CODE);
  gen_release(g_gen_le);
  if (g_cfg.strobe_on) gen_release(g_gen_strobe);
  if (g_cfg.fsin_on) {
    gen_release(g_gen_fsin1);
    gen_release(g_gen_fsin2);
  }
  g_running = true;
  digitalWrite(PIN_STATUS_LED, HIGH);
  return NULL;
}

// Change the bar pattern while running. One LE may latch a half-shifted pattern; it is reported as LATE.
static void apply_bar_live(BarMode m) {
  uint8_t buf[BAR_BYTES];
  g_bar_dynamic = false;
  vTaskDelay(2);  // let an in-flight render finish
  if (m == BAR_DARK) {
    bar_output_enable(false);
    return;
  }
  if (m == BAR_CODE) {
    uint32_t next = g_le_events;
    build_pattern(next, BAR_CODE, buf);
    bar_send(buf);
    g_ready_index = next;
    g_bar_dynamic = true;
  } else {
    build_pattern(0, m, buf);
    bar_send(buf);  // static: re-latched unchanged at every LE
  }
  bar_output_enable(true);
}

// =====================================================================================
// Validation
// =====================================================================================

static const char *check_step(uint32_t s) {
  return (s < STEP_MIN_US || s > STEP_MAX_US) ? "step_us_out_of_range_50_32767" : NULL;
}

static const char *check_strobe(uint32_t p, uint32_t w, uint32_t ph, uint32_t gap) {
  if (p < PERIOD_MIN_US || p > PERIOD_MAX_US) return "period_us_out_of_range_1000_65535";
  if (w < 1 || w > STROBE_WIDTH_MAX_US) return "width_us_out_of_range_1_500";
  uint32_t pulses = gap ? 2 : 1;
  if ((uint64_t)pulses * w * 1000 > (uint64_t)STROBE_DUTY_MAX_PERMILLE * p) return "duty_over_1_percent";
  if (ph >= p) return "phase_must_be_below_period";
  if (gap) {
    if (gap <= w) return "gap_must_exceed_width";
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
  char out[400];
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
  reply("OK STATUS fw=%s/%s core=%d.%d.%d running=%d bar=%s step_us=%u "
        "strobe=%d,%u,%u,%u,%u fsin=%d,%u,%u,%u le_events=%u late=%u strobe_k=%u fsin_k=%u evq_ovf=%u "
        "cap1=%s rx_edge=%d cap_res_hz=%u anchor_half_ns=%lld anchor_resid_ns=%lld "
        "xtal_mhz=%u apb_hz=%u cpu_mhz=%u boot_id=%08x esp_us=%lld",
        FW_NAME, FW_VERSION, ESP_ARDUINO_VERSION_MAJOR, ESP_ARDUINO_VERSION_MINOR, ESP_ARDUINO_VERSION_PATCH,
        (int)g_running, bar_mode_name(g_cfg.bar), (unsigned)g_cfg.step_us,
        (int)g_cfg.strobe_on, (unsigned)g_cfg.strobe_period_us, (unsigned)g_cfg.strobe_width_us,
        (unsigned)g_cfg.strobe_phase_us, (unsigned)g_cfg.strobe_gap_us,
        (int)g_cfg.fsin_on, (unsigned)g_cfg.fsin_period_us, (unsigned)g_cfg.fsin_width_us, (unsigned)g_cfg.fsin_phase_us,
        (unsigned)g_le_events, (unsigned)g_late_count, (unsigned)g_strobe_k, (unsigned)g_fsin_k, (unsigned)g_evq_overflow,
        CAP1_ROLE == CAP1_ROLE_LE_ANCHOR ? "LE" : "FSIN", USE_RX_EDGE_CAPTURE, (unsigned)g_cap_res_hz,
        (long long)g_anchor_half_ns, (long long)g_anchor_resid_ns,
        (unsigned)getXtalFrequencyMhz(), (unsigned)getApbFrequency(), (unsigned)getCpuFrequencyMhz(),
        (unsigned)g_boot_id, (long long)esp_timer_get_time());
}

// PING <host_ns>  ->  PONG <host_ns> <esp_us_rx> <esp_us_tx> <E|B>
//   esp_us_rx: start bit of the PING's first byte (E = captured edge, B = estimated from the read time)
//   esp_us_tx: esp_timer just before the PONG's first byte enters the empty UART TX FIFO
static void handle_ping(const char *host_tok, size_t line_len) {
  int64_t rx_ns = 0;
  char src = 'B';
#if USE_RX_EDGE_CAPTURE
  if (g_line_burst_ok && g_anchor_valid) {
    int64_t e = cap_to_esp_ns(g_line_burst_t32);
    int64_t first_ns = g_line_first_us * 1000;
    if (e <= first_ns && e > first_ns - 5000000LL) {
      rx_ns = e;
      src = 'E';
    }
  }
#endif
  if (src == 'B') {
    // whole line assumed to arrive in one chunk, after the UART RX idle timeout
    int64_t bits = (int64_t)(line_len + 1 + SERIAL_RX_TIMEOUT_SYMBOLS) * 10;
    rx_ns = g_line_first_us * 1000 - bits * 1000000000LL / SERIAL_BAUD;
  }
  Serial.flush();  // TX FIFO empty, so the PONG start bit follows the stamp within ~1 us
  int64_t tx_us = esp_timer_get_time();
  reply("PONG %s %lld %lld %c", host_tok, (long long)(rx_ns / 1000), (long long)tx_us, src);
}

static void handle_line(char *line, size_t len) {
  // tokenize in place (upper-case first; numbers are unaffected)
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
    return handle_ping(arg[0], len);
  }
  if (!strcmp(cmd, "STATUS")) return print_status();
  if (!strcmp(cmd, "VERSION"))
    return reply("OK VERSION %s %s core=%d.%d.%d", FW_NAME, FW_VERSION, ESP_ARDUINO_VERSION_MAJOR,
                 ESP_ARDUINO_VERSION_MINOR, ESP_ARDUINO_VERSION_PATCH);
  if (!strcmp(cmd, "HELP"))
    return reply("OK HELP PING <host_ns> | STATUS | VERSION | MODE CODE [step_us] | "
                 "MODE STROBE <period_us> <width_us> <phase_us> [gap_us] | MODE OFF | STEP <us> | "
                 "BAR CODE|ALLON|ALLOFF|DARK | STROBE <period_us> <width_us> <phase_us> [gap_us] | STROBE OFF | "
                 "FSIN <period_us> <width_us> [phase_us] | FSIN OFF | START | STOP | ANCHOR | EVENTS ON|OFF");

  if (!strcmp(cmd, "STEP")) {
    if (na < 1 || !parse_u32(arg[0], &a)) return reply("ERR STEP need_us");
    if ((err = check_step(a))) return reply("ERR STEP %s", err);
    g_cfg.step_us = a;
    return reply("OK STEP %u applies_at=START", (unsigned)a);
  }
  if (!strcmp(cmd, "BAR")) {
    BarMode m;
    if (na < 1) return reply("ERR BAR need_mode");
    if (!strcmp(arg[0], "CODE")) m = BAR_CODE;
    else if (!strcmp(arg[0], "ALLON")) m = BAR_ALLON;
    else if (!strcmp(arg[0], "ALLOFF")) m = BAR_ALLOFF;
    else if (!strcmp(arg[0], "DARK")) m = BAR_DARK;
    else return reply("ERR BAR unknown_mode");
    g_cfg.bar = m;
    if (g_running) apply_bar_live(m);
    return reply("OK BAR %s live=%d", bar_mode_name(m), (int)g_running);
  }
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
      if (g_running) {
        gen_hold_low(g_gen_fsin1);
        gen_hold_low(g_gen_fsin2);
      }
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
    if (na < 1) return reply("ERR MODE need_CODE_STROBE_OFF");
    if (!strcmp(arg[0], "OFF")) {
      stop_outputs();
      return reply("OK MODE OFF");
    }
    if (!strcmp(arg[0], "CODE")) {
      if (na >= 2) {
        if (!parse_u32(arg[1], &a) || (err = check_step(a))) return reply("ERR MODE step_us_out_of_range_50_32767");
        g_cfg.step_us = a;
      }
      g_cfg.bar = BAR_CODE;
      g_cfg.strobe_on = false;
    } else if (!strcmp(arg[0], "STROBE")) {
      if (na < 4 || !parse_u32(arg[1], &a) || !parse_u32(arg[2], &b) || !parse_u32(arg[3], &c) ||
          (na >= 5 && !parse_u32(arg[4], &d)))
        return reply("ERR MODE need_period_width_phase");
      if ((err = check_strobe(a, b, c, d))) return reply("ERR MODE %s", err);
      g_cfg.strobe_on = true;
      g_cfg.strobe_period_us = a;
      g_cfg.strobe_width_us = b;
      g_cfg.strobe_phase_us = c;
      g_cfg.strobe_gap_us = d;
      g_cfg.bar = BAR_DARK;
    } else {
      return reply("ERR MODE unknown_mode");
    }
    if ((err = start_outputs())) return reply("ERR MODE %s", err);
    return reply("OK MODE %s step_us=%u", arg[0], (unsigned)g_cfg.step_us);
  }
  if (!strcmp(cmd, "START")) {
    if ((err = start_outputs())) return reply("ERR START %s", err);
    return reply("OK START step_us=%u bar=%s strobe=%d fsin=%d", (unsigned)g_cfg.step_us, bar_mode_name(g_cfg.bar),
                 (int)g_cfg.strobe_on, (int)g_cfg.fsin_on);
  }
  if (!strcmp(cmd, "STOP")) {
    stop_outputs();
    return reply("OK STOP le_events=%u strobe_k=%u fsin_k=%u", (unsigned)g_le_events, (unsigned)g_strobe_k,
                 (unsigned)g_fsin_k);
  }
  if (!strcmp(cmd, "ANCHOR")) {
#if CAP1_ROLE == CAP1_ROLE_LE_ANCHOR
    if (g_running) g_le_anchor_armed = true;  // next LE edge is reported as "EV A <k> <t>"
#endif
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
      // first byte of a new line: note when we saw it and which RX burst it belongs to
      g_line_first_us = esp_timer_get_time();
      uint32_t s1 = g_rx_burst_seq;
      uint32_t t = g_rx_burst_start;
      uint32_t s2 = g_rx_burst_seq;
      g_line_burst_ok = ((s1 & 1u) == 0) && (s1 == s2) && (s1 != 0);
      g_line_burst_t32 = t;
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
    if (!g_events_on || !g_anchor_valid) continue;
    int64_t t0 = cap_to_esp_ns(ev.t0);
    switch (ev.type) {
      case EVT_STROBE:
        Serial.printf("EV S %u %lld %lld\n", (unsigned)ev.k, (long long)t0, (long long)cap_to_esp_ns(ev.t1));
        break;
      case EVT_FSIN:
        Serial.printf("EV F %u %lld\n", (unsigned)ev.k, (long long)t0);
        break;
      case EVT_LE: {
        uint32_t k = 0;
        if (!g_le0_valid) {
          g_le0_valid = true;
          g_le0_esp_ns = t0;
        } else {
          int64_t step_ns = (int64_t)g_cfg.step_us * 1000;
          k = (uint32_t)((t0 - g_le0_esp_ns + step_ns / 2) / step_ns);
        }
        Serial.printf("EV A %u %lld\n", (unsigned)k, (long long)t0);
        break;
      }
    }
  }
  uint32_t late = g_late_count;
  if (late != g_late_reported) {
    Serial.printf("EV E LATE %u %u\n", (unsigned)late, (unsigned)g_late_last);
    g_late_reported = late;
  }
  uint32_t ovf = g_evq_overflow;
  if (ovf != g_ovf_reported) {
    Serial.printf("EV E OVF %u\n", (unsigned)ovf);
    g_ovf_reported = ovf;
  }
}

static void poll_button() {
  bool level = digitalRead(PIN_BUTTON);
  uint32_t now = millis();
  if (level != g_btn_last && now - g_btn_change_ms > 20) {
    g_btn_change_ms = now;
    g_btn_last = level;
    if (!level && g_events_on) Serial.printf("EV BTN %lld\n", (long long)esp_timer_get_time() * 1000);
  }
}

// =====================================================================================
// Arduino entry points
// =====================================================================================

void setup() {
  // Outputs safe first: bar dark, status LED off. Gates have external pull-downs.
  pinMode(PIN_OE_N, OUTPUT);
  digitalWrite(PIN_OE_N, HIGH);
  pinMode(PIN_STATUS_LED, OUTPUT);
  digitalWrite(PIN_STATUS_LED, LOW);
  pinMode(PIN_BUTTON, INPUT_PULLUP);

  Serial.setRxBufferSize(1024);
  Serial.begin(SERIAL_BAUD);
  Serial.setRxTimeout(SERIAL_RX_TIMEOUT_SYMBOLS);
  // Wi-Fi and Bluetooth are never started by this sketch.

  g_boot_id = esp_random();
  g_evq = xQueueCreate(EVENT_QUEUE_LEN, sizeof(CapEvent));
  xTaskCreatePinnedToCore(render_task, "bar_render", 3072, NULL, RENDER_TASK_PRIO, &g_render_task, RENDER_CORE);

  // Capture channels are created from a task on CAPTURE_CORE so their ISRs run there.
  xTaskCreatePinnedToCore(capture_init_task, "cap_init", 4096, xTaskGetCurrentTaskHandle(), 5, NULL, CAPTURE_CORE);
  ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(2000));
  bool cap_ok = (g_capture_init_err == ESP_OK);
  if (!cap_ok) Serial.printf("EV E INIT capture %s\n", esp_err_to_name(g_capture_init_err));

  bool spi_ok = (spi_init() == ESP_OK);
  bool pwm_ok = (pwm_init() == ESP_OK);
  g_hw_ok = cap_ok && spi_ok && pwm_ok;
  if (cap_ok) clock_anchor(false);
  g_last_anchor_ms = millis();

  Serial.printf("EV B %08x %s %s hw_ok=%d\n", (unsigned)g_boot_id, FW_NAME, FW_VERSION, (int)g_hw_ok);
}

void loop() {
  poll_serial();
  drain_events();
  poll_button();
  if (g_hw_ok && millis() - g_last_anchor_ms >= ANCHOR_INTERVAL_MS) {
    g_last_anchor_ms = millis();
    clock_anchor(true);
  }
}
