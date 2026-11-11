# AtomS3 Lite sync rig: strobe-only firmware (draft)

A port of the classic-ESP32 rig firmware (`../esp32_sync_rig/esp32_sync_rig.ino`, documented in
[../README.md](../README.md) and [../DESIGN.md](../DESIGN.md)) to the **M5Stack AtomS3 Lite**
(ESP32-S3FN8, 8 MB flash, no PSRAM, native USB Serial/JTAG on the USB-C port). The scope is reduced to
the strobe: the strobe output with loopback capture, one optional FSIN output, the PING/PONG clock link
and periodic anchors. It adds **USB SOF stamping** (DESIGN.md §C option 4). There is no LED bar.

The serial protocol and event formats are the same as the classic sketch, so the host tools
(`../host/esp32_clock_sync.py`, `../../timing/rig/`) work unchanged. The differences are all additions:
extra trailing tokens and one new event type (see [Protocol differences](#protocol-differences)).

## Status

| Item | State |
| --- | --- |
| Firmware `atoms3_sync_rig.ino` | **Compiles, never flashed, never run.** Built on 2026-11-06 with arduino-cli 1.2.0 and the Arduino-ESP32 core 3.2.0 (ESP-IDF v5.4) for `esp32:esp32:m5stack_atoms3`, with `--warnings all`. Result: exit 0, 347,690 bytes of flash (26% of the 1.25 MB app partition), 21,156 bytes of RAM (6%). The only warnings are 4 `-Wmissing-field-initializers` from the IDF macro `MCPWM_GEN_COMPARE_EVENT_ACTION_END()` (the classic sketch has the same ones). Also compiled (exit 0): `-DCAP1_ROLE=0 -DSTATUS_LED=0`, and the generic FQBN `esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=cdc,FlashSize=8M`. With `CDCOnBoot=default` (disabled) the sketch stops at its `#error`, as intended. Build output went to a temp folder outside the repo. |
| Hardware | Nothing built, nothing measured. No timing figure on this page is a measurement. |

## Board settings

| Setting | Value | Notes |
| --- | --- | --- |
| FQBN | `esp32:esp32:m5stack_atoms3` ("M5AtomS3" in the esp32 core 3.2.0) | Its defaults are already right: USB Mode = **Hardware CDC and JTAG** (`build.usb_mode=1`), USB CDC On Boot = **Enabled** (`build.cdc_on_boot=1`), 8 MB flash, PSRAM disabled, CPU 240 MHz, loop on core 1 (checked in `boards.txt` of core 3.2.0) |
| Alternative FQBN | `esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=cdc,FlashSize=8M` | "ESP32S3 Dev Module". CDC On Boot is **disabled** by default there, so the options are required |
| Core | Arduino-ESP32 **3.x** | The sketch `#error`s on 2.x, on any target other than the ESP32-S3, and when USB CDC On Boot or Hardware CDC mode is off |
| USB Mode | Hardware CDC and JTAG | Not "USB-OTG (TinyUSB)": the SOF poller reads the USB Serial/JTAG controller's registers |

The `m5stack_atoms3` variant defines `RGB_BUILTIN` as GPIO 48, which is not the AtomS3 Lite's LED. The
sketch drives GPIO 35 explicitly. The `m5stack:esp32` core (3.2.1, also installed) was not used.

## Flashing

Only `compile` was run. The upload command was not run (no board attached).

```
arduino-cli compile --fqbn esp32:esp32:m5stack_atoms3 --warnings all research/usb_cameras/sync_rig/atoms3_sync_rig
arduino-cli upload  --fqbn esp32:esp32:m5stack_atoms3 -p COM7 research/usb_cameras/sync_rig/atoms3_sync_rig
```

On this machine arduino-cli is not on PATH. The Arduino IDE's copy is at
`C:\Users\Dom\AppData\Local\Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe`.
Build switches: `--build-property "compiler.cpp.extra_flags=-DCAP1_ROLE=0 -DSTATUS_LED=0"`.

esptool normally enters download mode on its own over the USB Serial/JTAG port (DTR/RTS sequence, see
below). If that fails (for example if the firmware is stuck), M5Stack's instructions are: with USB
connected, hold the side reset button until the internal green LED lights (about 2 s), then release; the
LED going off means download mode (source: the AtomS3 Lite docs page; the schematic shows this "BOOT"
circuit holding G0 low).

## Pinout source

Verified on 2026-11-06 from M5Stack's official sources, linked from
<https://docs.m5stack.com/en/core/AtomS3%20Lite>:
- pin map image `C124_PinMap_01.jpg` (<https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/471/C124_PinMap_01.jpg>);
- schematic `Sch_M5_AtomS3_v1.0.pdf` (<https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/471/Sch_M5_AtomS3_v1.0.pdf>).
  This is the shared AtomS3 schematic. The display parts on it are not fitted on the Lite.
- Cross-check: M5Stack's M5Unified library (`src/M5Unified.inl`, master, fetched 2026-11-06) uses
  RGB LED GPIO35 and button GPIO41 for `board_M5AtomS3Lite`.

| Item | GPIO | Source |
| --- | --- | --- |
| Header (5 pins) | 3V3, G5, G6, G7, G8 | pin map, schematic J3 |
| Header (4 pins) | G39, G38, 5V, GND | pin map, schematic J4 |
| PORT.A (HY2.0-4P, Grove-type) | GND, 5V, G2, G1 | pin map, schematic J6 |
| RGB LED (WS2812, data in) | G35 | pin map, schematic (SK_DIN) |
| IR LED | G4 (G4 → IR LED → 22 Ω → GND) | pin map, schematic R16 |
| Button | G41 (MTDI pin), 10 kΩ pull-up to 3V3, active low | pin map, schematic R4/S1 |
| USB D−/D+ | GPIO19/20 | ESP32-S3 fixed USB pins, schematic J5 |
| G0 | driven low by the reset-button "BOOT" circuit (hold 2 s) | schematic (GS321 comparator) |
| G3 | 10 kΩ pull-up (JTAG-source strapping) | schematic R3 |

The memory-based pin list in the task (G5–G8, G38, G39, Grove G1/G2, LED G35, IR G4, button G41) was
correct. On the non-Lite AtomS3 (with display), G38/G39 also carry the internal I2C bus with the IMU
(M5Unified's pin table; not on the schematic above, so unverified). This sketch is for the Lite.

## Pins used

Strapping pins (0, 3, 45, 46), USB (19, 20), UART0 (43, 44) and the on-board IR/RGB/button pins are not
used for rig signals. None of G5–G8, G38, G39 is a strapping pin.

| Function | GPIO | Where | Connects to | Notes |
| --- | --- | --- | --- | --- |
| STROBE gate | G5 | 5-pin header | AO3400A gate via 47–100 Ω, 100 kΩ gate→GND, **and** a wire to G6 | MCPWM0 timer 0 |
| Capture: STROBE loopback | G6 | 5-pin header (next to G5) | wire from G5 (take it at the G5 pin, before the series resistor) | capture channel 0, both edges, internal pull-down |
| FSIN gate | G7 | 5-pin header | FSIN sink MOSFET gate (47–100 Ω, 100 kΩ to GND), **and** a wire to G8 | MCPWM0 timer 1. One gate; for several cameras use one MOSFET per camera driven from G7, or ULN2803A inputs in parallel |
| Capture: FSIN loopback | G8 | 5-pin header (next to G7) | wire from G7 | capture channel 1 (`CAP1_ROLE=1`, default), internal pull-down. With `CAP1_ROLE=0` it is not used |
| SYNC (internal timer sync) | G39 | 4-pin header | **leave unconnected** (logic-analyzer probe is fine) | software pulse at START. The same pad is also capture channel 2, which timestamps it (`EV A 0`) and serves the soft-catch anchors |
| Button | G41 | on board | — | sends `EV BTN` |
| Status LED | G35 | on board | — | WS2812: dim blue = idle, green = running, red = hardware init failed. `-DSTATUS_LED=0` keeps it dark |
| IR LED | G4 | on board | — | held low, never used |
| Spare | G38, G1, G2 | header / PORT.A | | G38 is the fallback capture pin for SYNC (see bring-up step 2). G1 (ADC1) could take the optional photodiode later |

All capture inputs have the internal pull-down enabled, so an unwired loopback reads low instead of
floating. (The classic DevKit's GPIO34–39 had no internal pulls; every S3 pad has them.)

**The on-board RGB LED must never be used as the strobe.** It is an addressable WS2812: its brightness
is set by its own internal PWM (hundreds of Hz to kHz, unsynchronized), and the light comes on whenever its
controller latches a data frame, not on an MCPWM edge. It is also white-ish RGB, not one monochrome LED.
It is a status light only. Keep it out of the cameras' view, or build with `STATUS_LED=0`.
**The IR LED is useless as a strobe too**: webcam IR-cut filters block it.

## Wiring

```
                    +5 V external supply (not the Atom, not the PC's USB)
                           |
                     1 A polyfuse
                           |
          +----------------+----------------+
          |                |                |
     2200 uF low-ESR   10 uF ceramic    strobe LED anode (1-3 W green or deep red, no phosphor)
          |                |                |
         GND              GND          LED cathode
                                            |
                                     ~1.8 ohm 3 W (size for your LED)
                                            |
                                     AO3400A drain
   G5 --+-- 47-100 ohm -------------- gate
        |                     100 k --+
        +-- wire --> G6               |
                                     source ---- GND (star point at the supply)

   Atom GND (4-pin header) ------------------------- GND star point
```

- The LED current never flows through the Atom. Only the gate signal and the common ground connect to it.
- **Do not connect the external 5 V to the Atom's 5V pin.** On the schematic, the header and PORT.A 5V
  pins are the board's VIN_5V net: USB VBUS after the board's 6 V/1 A PPTC fuse. An external supply there
  would back-feed the PC's USB port. Power the Atom from USB only; connect only GND to the rig supply.
- Do not take LED current from the Atom's 3V3 pin either (SY8089 regulator for the ESP32-S3).
- FSIN: same as the classic rig (DESIGN.md §D). FSIN+ to +5 V, FSIN− to the low-side MOSFET (or ULN2803A)
  switched by G7. The cameras' opto inputs isolate them from the rig.
- Parts list: the Phase 0 rows of [../README.md](../README.md) "Bill of materials" (AO3400A, 47–100 Ω,
  100 kΩ, polyfuse, 2200 µF + 10 µF, 5 V supply, white card, logic analyzer).

## Serial link: USB Serial/JTAG (CDC-ACM)

The AtomS3 Lite has no USB-UART bridge. `Serial` is the ESP32-S3's built-in USB Serial/JTAG controller
(Arduino class `HWCDC`). Consequences:

- **Baud rate is ignored.** Any value works (the host script's default 921600 is fine). The link runs at
  USB full speed (12 Mbit/s) with 64-byte bulk packets.
- **Opening the port does not reset the chip by itself, but DTR/RTS can.** The controller emulates the
  classic two-transistor auto-reset circuit on the CDC line-state bits. esptool's reset sequences
  (esptool v4.8.1 `reset.py`, `USBJTAGSerialReset` and `HardReset(uses_usb=True)`) show the mapping:
  RTS asserted (with DTR de-asserted) resets the chip, and DTR asserted at the moment reset is released
  selects download mode. esptool steps through (1,1) rather than (0,0) between states, which implies that
  (1,1) is a no-action state, as in the transistor circuit. esptool also notes that on Windows, DTR is only
  sent to the device when RTS is set. This mapping comes from esptool's code, not from the ESP32-S3 TRM,
  and has **not been verified on the AtomS3**. Also from esptool (current master): a chip on its internal
  USB peripheral drops off the bus during a reset and re-enumerates, so the COM port disappears briefly.
- **Safe host settings:** set `dtr = False` and `rts = False` **before** `open()` (pyserial on Windows
  then opens with DTR/RTS control disabled) and never toggle them. `../host/esp32_clock_sync.py` already
  does this unless `--allow-reset` is given. **Never use `--allow-reset` with the AtomS3**: pyserial's
  default is to assert both on open, and the order in which Windows applies them may pass through a reset
  or download-mode state. The Arduino IDE serial monitor drives DTR/RTS for this board
  (`serial.disableDTR=false`, `serial.disableRTS=false` in boards.txt), so it may reset the board. Use the
  host script or a terminal with DTR/RTS off. (arduino-cli `monitor` has `dtr`/`rts` settings through
  `--config`, from memory, not checked.)
- **No `EV B` on open.** Since opening does not reset the chip, the host script's `--boot-wait` (2.5 s)
  normally times out harmlessly. Use `boot_id` from `STATUS` to detect a reboot. The S3 ROM prints a boot
  banner on this port after a real reset, and IDF error logs (if any) appear as non-protocol lines; host
  tools must ignore lines that are not `OK`/`ERR`/`PONG`/`EV`.
- **Stale output on open.** While no host program is reading, HWCDC keeps the newest output in its 2 KB
  TX buffer (oldest bytes dropped), so a freshly opened port may first deliver old, possibly truncated
  lines (`EV K`, `EV U`). The host script's `reset_input_buffer()` after the boot wait discards them.
  When a host is connected but not reading, a write blocks for at most 20 ms (`SERIAL_TX_TIMEOUT_MS`).

## Protocol differences

Everything in [../README.md "Serial protocol"](../README.md#serial-protocol) applies, with these changes:

| Item | Classic sketch | AtomS3 sketch |
| --- | --- | --- |
| `BAR …`, `STEP …`, `MODE CODE …` | bar control | `ERR BAR unsupported`, `ERR STEP unsupported`, `ERR MODE unsupported` |
| `STROBE`, `MODE STROBE`, `MODE OFF`, `START`, `STOP`, `ANCHOR`, `EVENTS`, `STATUS`, `VERSION`, `HELP` | | same syntax, limits and error strings. Replies keep their keys: `step_us=0`, `bar=NONE`, `le_events=0` |
| `FSIN …` | two pins, same waveform | one pin (G7), same syntax and limits |
| `PING <host_ns>` | `PONG <host_ns> <esp_us_rx> <esp_us_tx> <E\|B>` | `PONG <host_ns> <esp_us_rx> <esp_us_tx> B rx=<P\|L> rx_ns=<ns> tx_ns=<ns> sof=<frame11> sof_ns=<ns> sof_w=<ns>`. The first four tokens keep their meaning; token 4 is always `B` |
| Epoch | first LE rising edge after START | SYNC rising edge (captured on G39) + 100 µs (`EPOCH_DELAY_US`); strobe pulse 1 rises at epoch + phase. There is no LE |
| `EV A <k> <t>` | LE edge k (k = 0 is the epoch; more after `ANCHOR`) | only `EV A 0 <t_epoch_ns>` once per START (= captured SYNC edge + 100 µs). `ANCHOR` does not produce `EV A` |
| `EV U <frame11> <esp_ns> <w_ns>` | — | **new**: latest USB SOF stamp, at most 10 per second, only with `EVENTS ON` |
| `EV S`, `EV F`, `EV K`, `EV B`, `EV E OVF`, `EV E INIT`, `EV E ANCHOR`, `EV BTN` | | same formats. `EV E LATE` never occurs (no bar) |
| `EV S` k numbering | assigned in the ISR | assigned when drained, after dropping pulses earlier than epoch + phase − 5 µs (see [Strobe](#strobe-and-capture-on-the-esp32-s3)) |
| `STATUS` | | same keys plus `board`, `pre_epoch`, `epoch`, `sof`, `sof_ns`, `sof_w`, `sof_n`, `sof_rej`, `sof_age_us`, `rx_pkt_n`, `sys_hz`, `sys_off_ns`, `usb_cdc`. `cap1` is `FSIN` or `NONE`; `rx_edge=0` |
| `EV BTN`, anchor brackets | esp_timer µs × 1000 | sub-µs reads of the same clock (see Clocks) |

Times are esp_timer nanoseconds (`esp_ns`) everywhere, as in the classic sketch.

### PONG fields

```
PONG 123456789012 5012345 5012398 B rx=P rx_ns=5012345170 tx_ns=5012398820 sof=1234 sof_ns=5011876410 sof_w=230
```

| Token | Meaning |
| --- | --- |
| `<esp_us_rx>` | best estimate of when the PING arrived, µs (= `rx_ns` / 1000, truncated) |
| `<esp_us_tx>` | esp_timer just before the PONG is written into the empty HWCDC TX buffer, µs |
| `B` | always "estimated": there is no UART RX pin whose start bit could be captured |
| `rx=P` | `rx_ns` is the rising edge of the controller's raw `SERIAL_OUT_RECV_PKT` interrupt flag, seen by the core-0 poller: the end of the USB OUT transaction that carried the PING's first byte, plus ~0.1–0.3 µs poll delay (estimate) and an unknown constant flag latency. The HWCDC ISR on core 1 clears that flag a few µs later, so the poller normally sees it first |
| `rx=L` | fallback: `rx_ns` is when `loop()` first found the byte in the RX queue. Later than `P` by the ISR latency + queue + loop latency (typically a few to tens of µs, estimate; up to ms if the loop was busy writing). Used when the poller missed the packet (it pauses 1 ms every 100 ms) or the stamp was older than 2 ms |
| `rx_ns`, `tx_ns` | the same two times in ns, so the sub-µs part is not lost |
| `sof=<frame11>` | 11-bit USB frame number of the latest accepted SOF stamp before the PONG; `-1` if none yet |
| `sof_ns` | esp_timer ns at which that frame number appeared in `USB_SERIAL_JTAG_FRAM_NUM_REG` (bracket midpoint) |
| `sof_w` | width of the poll bracket around that change, ns (the change happened inside it) |

**What the rx/tx estimates mean for the ping offset.** The host computes
offset = ((rx − t1) + (tx − t4)) / 2 and delay = (t4 − t1) − (tx − rx).
- An rx stamp that is late by e_rx biases the offset by +e_rx/2 and makes the ping look e_rx shorter. With
  `rx=L`, pings with extra firmware latency therefore look *better* to a min-delay filter, which selects for
  the bias. Prefer `rx=P` pings, or check whether the result changes when `rx=L` pings are excluded.
- The tx stamp is taken before the PONG reaches the wire. The PONG then waits for the HWCDC ISR and for
  the host's next bulk IN poll (µs to ≲ 1 ms, unmeasured). That biases the offset by −e_tx/2.
- So the ping path still carries an unknown asymmetry, as on the classic rig (DESIGN.md §C option 3). The
  SOF stamps are the independent reference that can measure it.

## USB SOF stamping (DESIGN.md §C option 4)

**Register.** `USB_SERIAL_JTAG_FRAM_NUM_REG` = `DR_REG_USB_SERIAL_JTAG_BASE` (0x60038000) + 0x24 =
**0x60038024**, field `USB_SERIAL_JTAG_SOF_FRAME_INDEX`, bits [10:0], read-only: "Frame index of received
SOF frame" (checked in the ESP-IDF v5.4 header `soc/esp32s3/register/soc/usb_serial_jtag_reg.h` shipped
with core 3.2.0; the ESP32-S3 TRM itself was not opened).

**How it is stamped.** A FreeRTOS task pinned to core 0 (priority 1) busy-polls that register and the
raw interrupt register. The CPU cycle counter (240 MHz) is read before each register read, so a change is
known to lie between two consecutive reads (the bracket, ~0.1–0.3 µs per loop, estimate). On a change, the
task reads the esp_timer counter once (systimer, 62.5 ns ticks) and back-dates it to the bracket midpoint.
A stamp is accepted only if the frame number advanced by exactly 1 and the bracket is ≤ 2 µs (an
interrupt or a higher-priority task on core 0 widens it). `STATUS` reports `sof_n` (accepted) and
`sof_rej` (rejected). The task pauses for one FreeRTOS tick every 100 ms, so that core 0's idle task
can run (the task watchdog watches it); about 1% of SOFs are not stamped, which does not matter.

Why core 0: the Arduino loop and the HWCDC interrupt run on core 1. The capture interrupts also run on
core 0. They preempt the poller, which only costs a rejected stamp now and then.

**Where it is exposed, and why both.**
- **PONG trailing tokens** (`sof=`, `sof_ns=`, `sof_w=`): always present. The host clock script switches
  events off during ping runs (`EVENTS OFF`), so an event-only design would deliver nothing then. Each
  PONG carries a stamp under 1 ms old, next to the ping's own times.
- **`EV U <frame11> <esp_ns> <w_ns>`**, at most 10 per second, with `EVENTS ON`: a continuous record
  during long camera runs when no pings are sent. 10/s is far more than the ≤ 2 s re-anchoring needs and
  costs ~400 bytes/s of serial output.

**Host side (not in this folder).** The host maps frame numbers to QPC with
`IOCTL_USB_GET_FRAME_NUMBER_AND_QPC_FOR_TIME_SYNC`. REPORT finding 14 measured that mapping as exact only
for ~2–3.5 s, so it must be re-anchored every ≤ 2 s. Two further cautions:
- The frame number is 11 bits and wraps every 2.048 s. The ping offset (good to ~1 ms) is enough to
  pick the right wrap.
- The device must be on the **same xHCI controller** as the cameras under test (DESIGN.md §G). Behind a
  USB 2.0 hub, the full-speed SOF the S3 sees is generated by the hub's transaction translator from the
  high-speed microframe clock. It should keep the same frame number, but this is not checked.

**Constant offsets not removed** (each should be a few µs or less, all unmeasured): SOF token on the wire →
`FRAM_NUM` update (SOF packet ≈ 2.7 µs at 12 Mbit/s plus decoding), register read latency, and the
systimer read latency.

## Clocks on the ESP32-S3

| Clock | ESP32-S3 (this sketch) | Classic ESP32 | Source |
| --- | --- | --- | --- |
| MCPWM capture timer | **APB, 80 MHz → 12.5 ns ticks, 32 bit** (wraps every 53.7 s). `STATUS cap_res_hz` reports the driver's value | APB 80 MHz | IDF v5.4 `soc/esp32s3/include/soc/clk_tree_defs.h`: `SOC_MCPWM_CAPTURE_CLKS {SOC_MOD_CLK_APB}`, `MCPWM_CAPTURE_CLK_SRC_DEFAULT = APB`. APB stays 80 MHz at CPU 240 MHz (no power management in this sketch) |
| MCPWM PWM timers | PLL_F160M, 2 MHz after prescaling (0.5 µs) | PLL 160 MHz | same header: `SOC_MCPWM_TIMER_CLKS {SOC_MOD_CLK_PLL_F160M}` |
| esp_timer | systimer counter 0, 16 MHz (62.5 ns), read directly by `fine_ns()` | 1 µs API only | IDF `esp_private/systimer.h` (`SYSTIMER_COUNTER_ESPTIMER 0`); rate from `systimer_us_to_ticks()`, reported as `sys_hz` |
| CPU cycle counter | 240 MHz, per core | — | used only for the SOF poll brackets |

All of these derive from the 40 MHz crystal, so their ratios are fixed. The S3 has 2 MCPWM groups with 3
timers, 3 operators and 3 capture channels each (`soc_caps.h`). This sketch uses group 0: 2 timers, 2
operators, 3 capture channels, 1 GPIO sync source.

`fine_ns()` reads the esp_timer counter with the same snapshot / re-read sequence that IDF uses. It is
therefore the same clock as `esp_timer_get_time()`, at 62.5 ns resolution. `STATUS sys_off_ns` checks
this at boot (expected within ±1000 ns, the µs truncation of `esp_timer_get_time()`). It is used for the
anchor brackets, the PING/PONG stamps, the SOF stamps and `EV BTN`, which tightens the anchor half-bracket
compared with the classic sketch's 1 µs reads.

## Strobe and capture on the ESP32-S3

- **The up/down double-pulse trick carries over.** The ESP32-S3 MCPWM driver API is the same, and up/down
  counting with direction-qualified compare actions is supported. Pulse 1 = compare A then B counting up,
  pulse 2 = compare B then A counting down; gap = P − tA − tB. Nothing was redesigned. On hardware it is as
  unverified as on the classic board (see bring-up step 2).
- **Stray pulse before the first pulse 1 (also affects the classic sketch).** In double mode, after the
  sync load the up/down counter can pass the down-count compares (pulse 2 of the "previous" cycle) before
  it first reaches tA. That happens when phase + epoch delay > P − gap − width. Example: `STROBE 33333 50
  30000 10000`. The output is released ~µs after the sync, so that pulse 2 reaches the LED and the
  capture, and the classic sketch numbers it `k = 0`, breaking the pulse-1/pulse-2 parity of `k`. This
  sketch assigns `k` when draining events and drops captured pulses that rise before
  epoch + phase − 5 µs. The drops are counted in `STATUS pre_epoch`. The light pulse itself still happens
  (one extra band in one frame).
- **Epoch.** No LE exists, so the epoch is defined as the SYNC rising edge + 100 µs. The SYNC edge is
  captured on capture channel 2 (same pad as the sync output, fanned out in the GPIO matrix), and
  `EV A 0` reports the captured edge + 100 µs. The constant sync-to-timer propagation delay (a few timer
  clock cycles, unmeasured) sits between that and the real timer phase. The analysis should use the
  captured `EV S` edges anyway, not the commanded phase.
- **Capture ISRs** are created from a task on core 0, as in the classic sketch.

## Bring-up checklist

Steps 1–5 need no camera; step 7 is test plan V0. Take every measurement with the strobe LED
supply off until step 2 passes.

1. Flash with nothing wired. Open the port with DTR/RTS off (the host script without `--allow-reset`, or
   a terminal with both off). Send `VERSION` and `STATUS`. Check:
   - `cap_res_hz=80000000`, `apb_hz=80000000`, `cpu_mhz=240`, `sys_hz=16000000`, `|sys_off_ns| < 1000`;
   - `anchor_half_ns` a few hundred ns;
   - `sof_n` rising by ~990 per second, `sof_age_us` < 2000, `sof_w` a few hundred ns, `sof_rej` a small
     fraction of `sof_n`;
   - `usb_cdc=1`, and `boot_id` unchanged after closing and reopening the port (opening must not reset).
     If it changes, check the host's DTR/RTS handling before anything else.
2. Logic analyzer on G39 (SYNC), G5 (STROBE), G7 (FSIN). Send `STROBE 33333 50 1000`, `FSIN 20800 100 0`,
   `START`. Check:
   - strobe width 50 µs; the first strobe rise 1100 µs after the SYNC rising edge (epoch = SYNC + 100 µs,
     plus phase 1000 µs); the first FSIN rise 100 µs after SYNC;
   - no stray pulses around the SYNC edge;
   - an `EV A 0 …` line after START, and `STATUS epoch=1`. If not, the same-pad capture of SYNC does not
     work: rebuild with `PIN_CAP_SYNC = 38` and wire G39 to G38;
   - double strobe: `STROBE 33333 50 1000 10000`, `START` → a second rise 10 ms (rise to rise) after the
     first.
3. Wire G5→G6 and G7→G8. Compare `EV S` / `EV F` / `EV A` differences with the analyzer: this checks the
   capture loopback, the 64-bit unwrap (run > 60 s, past one capture-counter wrap) and the epoch offset.
4. Stray-pulse case: `STROBE 33333 50 30000 10000`, `START`. Expect `STATUS pre_epoch=1` and `EV S 0` to be a
   pulse 1 (its next `EV S` 10 ms later).
5. Run `../host/esp32_clock_sync.py --port COMx --duration 60 --rate 50` three times on each USB topology
   (direct root port; through a hub), and look at the `extra` PONG tokens it keeps. Check the share of `rx=P`
   pings (expect ~99%) and that rx(L) − rx(P) is positive when both can be compared.
6. Leave it running for 10 minutes: no reboots (`boot_id` unchanged), `evq_ovf=0`, `sof_rej` stable. This
   checks the core-0 poller against the task watchdog.
7. Then the camera checks from [../README.md](../README.md) step 5 (test plan V0): strobe band visible at
   720p30 MJPEG, w = 50 µs, dark room, echo-band check, line time L per camera. Make sure the Atom's RGB LED
   is not in view (or build with `STATUS_LED=0`).
8. Only then: the host SOF ↔ QPC mapping (test plan R2/V7; the `timing/rig/` host code, not this folder).

## Known limitations and open TODOs

- **Assumed, not verified on hardware** (from IDF headers, esptool code and reasoning):
  - the DTR/RTS → reset/download mapping of the USB Serial/JTAG controller, and that opening with both
    de-asserted never resets the S3;
  - that `USB_SERIAL_JTAG_FRAM_NUM_REG` updates on every SOF while the CDC port is idle, and its latency;
  - that the core-0 poller sees the raw `SERIAL_OUT_RECV_PKT` flag before the core-1 HWCDC ISR clears it;
  - capture of the SYNC edge on the same pad as the GPIO sync source (fallback: G38 plus a wire);
  - everything listed in [../README.md](../README.md) "Known limitations" for MCPWM (sync load and compare
    events, sync propagation delay, glitch-free release, `mcpwm_timer_set_period` halving in up/down mode).
- **Systimer access uses IDF internals** (`hal/systimer_ll.h`, `esp_private/systimer.h`). They compile on
  core 3.2.0 / IDF 5.4 and may change in later cores.
- **TX stamp.** `esp_us_tx` is taken before the PONG enters the TX buffer, not when the host picks it up.
  The poller could stamp the next raw `SERIAL_IN_EMPTY` rise (the host reading the IN FIFO), but that time
  would only be known after the PONG has gone. Not done.
- **No LED bar, no photodiode, no SWEEP**, as in the scope.
- **EPOCH_DELAY_US = 100** must stay larger than the time from the SYNC pulse to releasing the outputs
  (a few µs) so that the first scheduled edge is never suppressed.
- **One FSIN gate only.** Five usable header pins plus PORT.A limit the rig signals; G38, G1 and G2 remain free.
