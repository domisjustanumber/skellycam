# /// script
# requires-python = ">=3.10"
# dependencies = ["pyserial>=3.5"]
# ///
"""ESP32 sync-rig session for the timestamp-anchor test: strobe + raw event log + interleaved clock pings.

Opens no camera. Target board: M5Stack AtomS3 Lite (ESP32-S3, native USB Serial/JTAG, enumerates as a USB CDC
COM port with VID 303A; firmware port in ../../sync_rig/atoms3_sync_rig/). The classic DevKit firmware
(../../sync_rig/esp32_sync_rig/) speaks the same protocol (../../sync_rig/README.md "Serial protocol").

  uv run --script research/usb_cameras/timing/rig/rig_session.py --list-ports
  uv run --script research/usb_cameras/timing/rig/rig_session.py --port COM7 --out-dir <dir>
        --period-us 33366 --width-us 50 [--phase-us 1000] [--gap-us 10000] [--defer-start]
        [--duration 3600] [--ping-rate 20] [--stop-file <path>]
  uv run --script research/usb_cameras/timing/rig/rig_session.py --simulate --out-dir <dir> --duration 5   (no hardware)

Sequence: open the port with DTR/RTS held in a fixed state (--line-state, below) -> wait --boot-wait s for EV B
(only appears if the open reset the board; a new boot_id means any earlier clock fit is void) -> VERSION, STATUS,
EVENTS ON, STOP (idle), BAR DARK, STROBE <period> <width> <phase> [gap] -> START (now, or on request with
--defer-start) -> until stopped: log EVERY received line with host QPC stamps and send a PING on a jittered
schedule (EV lines stay on, so PONGs are picked out from among them) -> STOP, STATUS -> clock fit.

Line state (--line-state): on the ESP32-S3 USB Serial/JTAG peripheral, DTR/RTS transitions drive the chip's reset
and boot-strap logic (esptool uses them to reset into download mode); on the classic DevKit they drive EN/IO0 through
the auto-reset transistors. 'deassert' (default) sets DTR = RTS = False BEFORE opening, the non-reset state on both
boards; 'dtr' sets DTR = True, RTS = False (some USB CDC stacks only transmit to an open terminal with DTR set; RTS
stays low, so no reset); 'untouched' leaves pyserial's defaults (which assert both on Windows and MAY reset the
board; only for debugging). Whatever happens, an EV B line is detected and recorded.

Control while running (all optional; the orchestrator uses files):
  --stop-file PATH      session ends when PATH exists (also: Ctrl+C / SIGBREAK, a line "stop" on stdin, --duration)
  <out>/rig_cmd_*.txt   one command word per file, executed in name order then deleted: START (strobe start, new
                        epoch, k restarts at 0) or STOP (strobe stop). Used for --defer-start.
  <out>/rig_ready.json  written once the strobe config is accepted (and, unless --defer-start, the first EV S seen)
  <out>/rig_state.json  rewritten on every START/STOP with the current strobe state and the latest epoch

Outputs in --out-dir: rig_events.log ("<host_first_ns>\\t<host_last_ns>\\t<line>" for every line, unknown EV types
included), rig_pings.csv (esp32_clock_sync.py columns + 'extra' = any PONG tokens after the 4th, e.g. the AtomS3
port's SOF fields), rig_session.json (standard result fields; clock fit by sync_rig/host/esp32_clock_sync.py).
PONG field 4 is 'B' (RX time estimated) on the AtomS3: it has no UART RX pin to capture.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import importlib.util
import json
import random
import signal
import socket
import statistics
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
AREA_ROOT = HERE.parents[1]
CLOCK_SYNC = AREA_ROOT / "sync_rig" / "host" / "esp32_clock_sync.py"


def load_cs():
    spec = importlib.util.spec_from_file_location("esp32_clock_sync", CLOCK_SYNC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)  # type: ignore[union-attr]
    return m


cs = load_cs()


# ---------------------------------------------------------------------------------------------------------------
# Simulated firmware (no hardware): same line protocol, ESP clock 15 ppm fast, strobe EV S lines, PONG with 'B'
# ---------------------------------------------------------------------------------------------------------------

class FakeSerial:
    """Minimal stand-in for serial.Serial (in_waiting, read, write, close) that speaks the rig protocol."""

    def __init__(self, clock, ppm: float = 15.0, boot: bool = True):
        self.clock = clock
        self.t0 = clock()
        self.ppm = ppm
        self.out = bytearray()
        self.lock = threading.Lock()
        self.running = False
        self.cfg = None
        self.k = 0
        self.next_rise = None
        self.events_on = True
        self.pending: list[tuple[int, bytes]] = []  # (host time when the bytes become readable, data)
        if boot:
            self._emit("EV B 1a2b3c4d esp32_sync_rig sim hw_ok=1", delay_ns=0)

    def esp_ns(self, host_ns=None):
        h = self.clock() if host_ns is None else host_ns
        return 5_000_000_000 + int((h - self.t0) * (1 + self.ppm * 1e-6))

    def _emit(self, text: str, delay_ns: int = 150_000):
        with self.lock:
            self.pending.append((self.clock() + delay_ns, (text + "\r\n").encode()))

    def _pump(self):
        now = self.clock()
        if self.running and self.cfg:
            p, w, ph, gap = self.cfg
            while self.next_rise is not None and self.esp_ns(now) > self.next_rise + w * 1000:
                r = self.next_rise
                if self.events_on:
                    self._emit(f"EV S {self.k} {r} {r + w * 1000}")
                self.k += 1
                if gap and self.k % 2 == 1:
                    self.next_rise = r + gap * 1000
                else:
                    self.next_rise = (r - gap * 1000 if gap else r) + p * 1000
        with self.lock:
            ready = [d for t, d in self.pending if t <= now]
            self.pending = [(t, d) for t, d in self.pending if t > now]
        for d in ready:
            self.out += d

    @property
    def in_waiting(self):
        self._pump()
        return len(self.out)

    def read(self, n):
        d = bytes(self.out[:n])
        del self.out[:n]
        return d

    def reset_input_buffer(self):
        self.out.clear()

    def write(self, data: bytes):
        rx_ns = self.esp_ns()
        for line in data.decode().splitlines():
            tok = line.strip().upper().split()
            if not tok:
                continue
            c = tok[0]
            if c == "PING":
                tx = self.esp_ns() + 30_000
                self._emit(f"PONG {line.split()[1]} {rx_ns // 1000} {tx // 1000} B 1234 {tx // 1000 - 300}", 200_000)
            elif c == "VERSION":
                self._emit("OK VERSION esp32_sync_rig sim core=3.2.0")
            elif c == "STATUS":
                self._emit(f"OK STATUS running={int(self.running)} esp_us={self.esp_ns() // 1000}")
            elif c == "EVENTS":
                self.events_on = tok[1] == "ON"
                self._emit(f"OK EVENTS {tok[1]}")
            elif c == "BAR":
                self._emit(f"OK BAR {tok[1]} live={int(self.running)}")
            elif c == "STROBE":
                self.cfg = tuple(int(x) for x in tok[1:5]) + ((0,) if len(tok) < 5 else ())
                self.cfg = self.cfg[:4]
                self._emit(f"OK STROBE {' '.join(tok[1:])} applies_at=START")
            elif c == "START":
                self.running, self.k = True, 0
                self.next_rise = self.esp_ns() + 100_000 + self.cfg[2] * 1000
                self._emit("OK START step_us=100 bar=DARK strobe=1 fsin=0")
            elif c == "STOP":
                self.running = False
                self._emit(f"OK STOP le_events=0 strobe_k={self.k} fsin_k=0")
            else:
                self._emit(f"ERR {c} unknown_command")
        return len(data)

    def close(self):
        pass


# ---------------------------------------------------------------------------------------------------------------

class Session:
    def __init__(self, ser, clock, log_path: Path):
        self.ser, self.clock = ser, clock
        self.reader = cs.LineReader(ser, clock)
        self.log = log_path.open("w", encoding="ascii", errors="replace", newline="\n")
        self.n_lines = 0
        self.counts: dict[str, int] = {}
        self.boot_lines: list[str] = []
        self.ev_e: list[str] = []
        self.first_ev_s = None
        self.last_flush = time.perf_counter()

    def pump(self) -> list[tuple[int, int, str]]:
        self.reader.poll()
        items = self.reader.take()
        for first, last, text in items:
            self.log.write(f"{first}\t{last}\t{text}\n")
            self.n_lines += 1
            tok = cs.strip_tag(text)
            key = (tok[0] + (" " + tok[1] if tok[0] == "EV" and len(tok) > 1 else "")) if tok else ""
            self.counts[key] = self.counts.get(key, 0) + 1
            if key == "EV B":
                self.boot_lines.append(text)
            elif key == "EV E":
                self.ev_e.append(text)
            elif key == "EV S" and self.first_ev_s is None:
                self.first_ev_s = text
        if time.perf_counter() - self.last_flush > 1.0:
            self.log.flush()
            self.last_flush = time.perf_counter()
        return items

    def wait_for(self, pred, timeout_s: float):
        end = time.perf_counter() + timeout_s
        while time.perf_counter() < end:
            for it in self.pump():
                if pred(it[2]):
                    return it
        return None

    def command(self, cmd: str, timeout_s: float = 1.0) -> str | None:
        self.ser.write((cmd + "\n").encode("ascii"))
        word = cmd.split()[0].upper()

        def is_reply(text):
            tok = cs.strip_tag(text)
            return len(tok) >= 2 and tok[0] in ("OK", "ERR") and tok[1] == word

        got = self.wait_for(is_reply, timeout_s)
        return got[2] if got else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port")
    ap.add_argument("--baud", type=int, default=921600, help="ignored by USB CDC, used for the serialization estimate")
    ap.add_argument("--out-dir", type=Path)
    ap.add_argument("--period-us", type=int, default=33366)
    ap.add_argument("--width-us", type=int, default=50)
    ap.add_argument("--phase-us", type=int, default=1000)
    ap.add_argument("--gap-us", type=int, default=0, help="> 0: double strobe, second rise gap_us after the first")
    ap.add_argument("--defer-start", action="store_true", help="configure but wait for a START command file")
    ap.add_argument("--duration", type=float, default=3600.0, help="hard cap in seconds")
    ap.add_argument("--ping-rate", type=float, default=20.0, help="mean pings per second")
    ap.add_argument("--ping-timeout", type=float, default=0.2)
    ap.add_argument("--boot-wait", type=float, default=2.5)
    ap.add_argument("--line-state", choices=("deassert", "dtr", "untouched"), default="deassert")
    ap.add_argument("--stop-file", type=Path)
    ap.add_argument("--list-ports", action="store_true")
    ap.add_argument("--simulate", action="store_true", help="run against a simulated firmware (no hardware)")
    a = ap.parse_args()

    clock, clock_desc = cs.host_clock()
    if a.list_ports:
        from serial.tools import list_ports  # noqa: PLC0415
        for p in list_ports.comports():
            tag = "  <- Espressif native USB (AtomS3 Lite?)" if p.vid == 0x303A else ""
            print(f"{p.device}\t{p.vid and f'{p.vid:04X}'}:{p.pid and f'{p.pid:04X}'}\t{p.description}\t{p.serial_number}{tag}")
        return 0
    if not a.out_dir:
        ap.error("--out-dir is required")
    if not a.simulate and not a.port:
        ap.error("--port is required (or --simulate / --list-ports)")
    out = a.out_dir
    out.mkdir(parents=True, exist_ok=True)
    for stale in list(out.glob("rig_cmd_*.txt")) + [out / "rig_ready.json", out / "rig_state.json"]:
        stale.unlink(missing_ok=True)

    stop_flag = threading.Event()
    reason = {"why": "duration"}

    def on_signal(signum, frame):  # noqa: ARG001
        reason["why"] = f"signal {signum}"
        stop_flag.set()

    signal.signal(signal.SIGINT, on_signal)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, on_signal)

    def stdin_watch():
        try:
            for line in sys.stdin:
                if line.strip().lower() in ("stop", "q", "quit"):
                    reason["why"] = "stdin stop"
                    stop_flag.set()
                    return
        except Exception:  # noqa: BLE001
            return

    if not sys.stdin.isatty():
        threading.Thread(target=stdin_watch, daemon=True).start()

    utc_started = dt.datetime.now(dt.timezone.utc)
    if a.simulate:
        ser = FakeSerial(clock)
        dev = {"port": "SIMULATED", "vid": "303A", "pid": "1001", "description": "simulated rig firmware"}
    else:
        import serial  # noqa: PLC0415
        ser = serial.Serial()
        ser.port, ser.baudrate, ser.timeout, ser.write_timeout = a.port, a.baud, 0, 1.0
        if a.line_state == "deassert":
            ser.dtr, ser.rts = False, False
        elif a.line_state == "dtr":
            ser.rts, ser.dtr = False, True
        ser.open()
        dev = cs.port_info(a.port)
    sess = Session(ser, clock, out / "rig_events.log")
    pings_f = (out / "rig_pings.csv").open("w", newline="")
    cols = ["seq", "host_tx_ns", "host_write_done_ns", "host_rx_ns", "host_rx_last_ns", "esp_rx_us", "esp_tx_us", "rx_src", "extra"]
    pw = csv.DictWriter(pings_f, fieldnames=cols)
    pw.writeheader()
    samples: list[dict] = []
    reply_lens: list[int] = []
    epochs: list[dict] = []
    replies: dict[str, str | None] = {}
    rc = 0
    lost = 0
    strobe_args = f"{a.period_us} {a.width_us} {a.phase_us}" + (f" {a.gap_us}" if a.gap_us else "")
    state = {"strobe_running": False}

    def write_state():
        (out / "rig_state.json").write_text(json.dumps({**state, "epochs": epochs, "host_ns": clock()}))

    def strobe_start():
        r = sess.command("START")
        epochs.append({"cmd": "START", "host_ns": clock(), "reply": r})
        state["strobe_running"] = bool(r) and cs.strip_tag(r)[:1] == ["OK"]
        write_state()
        return r

    def strobe_stop():
        r = sess.command("STOP")
        epochs.append({"cmd": "STOP", "host_ns": clock(), "reply": r})
        state["strobe_running"] = False
        write_state()
        return r

    try:
        boot = sess.wait_for(lambda t: t.startswith("EV B"), a.boot_wait)
        replies["VERSION"] = sess.command("VERSION")
        if replies["VERSION"] is None:
            print(f"no reply to VERSION on {a.port}; is the rig firmware flashed? (try --line-state dtr)", file=sys.stderr)
            return 2
        replies["STATUS_before"] = sess.command("STATUS")
        replies["EVENTS"] = sess.command("EVENTS ON")
        replies["STOP_initial"] = sess.command("STOP")
        replies["BAR"] = sess.command("BAR DARK")
        replies["STROBE"] = sess.command(f"STROBE {strobe_args}")
        if not replies["STROBE"] or "ERR" in replies["STROBE"].split()[:2]:
            print(f"strobe config refused: {replies['STROBE']}", file=sys.stderr)
            return 3
        if not a.defer_start:
            strobe_start()
            got = sess.wait_for(lambda t: cs.strip_tag(t)[:2] == ["EV", "S"], 3.0)
            if got is None:
                print("no EV S within 3 s of START: check the STROBE loopback wire", file=sys.stderr)
        (out / "rig_ready.json").write_text(json.dumps({"host_ns": clock(), "deferred": a.defer_start, "strobe": strobe_args,
                                                        "boot_line": boot[2] if boot else None}))
        print("RIG_READY", flush=True)
        period = 1.0 / a.ping_rate
        t_end = time.perf_counter() + a.duration
        next_t = time.perf_counter()
        seq = 0
        while time.perf_counter() < t_end and not stop_flag.is_set():
            if a.stop_file and a.stop_file.exists():
                reason["why"] = "stop file"
                break
            for f in sorted(out.glob("rig_cmd_*.txt")):
                word = f.read_text().strip().upper()
                f.unlink(missing_ok=True)
                if word == "START":
                    strobe_start()
                elif word == "STOP":
                    strobe_stop()
            next_t += period * (0.5 + random.random())
            while time.perf_counter() < next_t:
                sess.pump()
            t1 = clock()
            ser.write(b"PING %d\n" % t1)
            t1w = clock()
            want = str(t1)
            got = sess.wait_for(lambda t, want=want: (lambda tok: len(tok) >= 4 and tok[0] == "PONG" and tok[1] == want)(cs.strip_tag(t)),
                                a.ping_timeout)
            seq += 1
            if got is None:
                lost += 1
                continue
            first_ns, last_ns, text = got
            tok = cs.strip_tag(text)
            reply_lens.append(len(text) + 2)
            row = {"seq": seq, "host_tx_ns": t1, "host_write_done_ns": t1w, "host_rx_ns": first_ns, "host_rx_last_ns": last_ns,
                   "esp_rx_us": int(tok[2]), "esp_tx_us": int(tok[3]), "rx_src": tok[4] if len(tok) > 4 else None,
                   "extra": " ".join(tok[5:])}
            samples.append(row)
            pw.writerow(row)
            if seq % 50 == 0:
                pings_f.flush()
        if state["strobe_running"]:
            strobe_stop()
        replies["STATUS_after"] = sess.command("STATUS")
    finally:
        pings_f.close()
        sess.log.close()
        ser.close()

    meas: dict = {"lines": sess.n_lines, "line_counts": sess.counts, "ev_e": sess.ev_e[:50], "boot_lines": sess.boot_lines,
                  "pings_sent": len(samples) + lost, "pings_answered": len(samples),
                  "reply_bytes": statistics.fmean(reply_lens) if reply_lens else None, "epochs": epochs,
                  "stop_reason": reason["why"],
                  "rx_src_counts": {s: sum(1 for x in samples if x["rx_src"] == s) for s in {x["rx_src"] for x in samples}}}
    if len(samples) >= 2:
        meas["clock"] = cs.analyse(samples, 1.0, a.baud, meas["reply_bytes"] or 45.0)
    asym = ("native USB CDC (bulk IN polling)" if (dev.get("vid") or "").upper() == "303A"
            else "USB-serial bridge (UART serialization + bridge forwarding)")
    rec = {
        "test": "rig_session", "platform": cs.platform_name(), "hostname": socket.gethostname(),
        "utc_started": utc_started.isoformat(), "utc_finished": dt.datetime.now(dt.timezone.utc).isoformat(),
        "command": " ".join(sys.argv), "environment": cs.environment(clock_desc), "cameras": [],
        "device": {**dev, "baud": a.baud, "line_state": a.line_state, "simulated": a.simulate, "replies": replies},
        "parameters": {"strobe": {"period_us": a.period_us, "width_us": a.width_us, "phase_us": a.phase_us, "gap_us": a.gap_us},
                       "defer_start": a.defer_start, "ping_rate_hz": a.ping_rate, "duration_cap_s": a.duration},
        "measurements": meas,
        "notes": [f"Ping-path asymmetry source: {asym}. Both ping offsets are reported; neither is validated (test plan V6/V7).",
                  "EV lines stayed ON during pings: a PONG queued behind an EV line has a longer delay; the min-delay filter keeps the clean ones.",
                  "SIMULATED firmware: no hardware involved." if a.simulate else "Hardware run."],
    }
    (out / "rig_session.json").write_text(json.dumps(rec, indent=1))
    fit = meas.get("clock", {}).get("fit", {})
    print(json.dumps({"stop_reason": reason["why"], "lines": sess.n_lines, "ev_s": sess.counts.get("EV S", 0),
                      "pings": len(samples), "drift_ppm": fit.get("drift_ppm_esp_vs_host"),
                      "residual_std_us": fit.get("residual_std_us"), "asymmetry_bound_us": fit.get("asymmetry_bound_us")}))
    return rc


if __name__ == "__main__":
    sys.exit(main())
