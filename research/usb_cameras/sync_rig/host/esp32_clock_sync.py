# /// script
# requires-python = ">=3.10"
# dependencies = ["pyserial>=3.5"]
# ///
"""ESP32 sync rig: correlate the ESP32 clock with the host clock over serial PING/PONG (DRAFT).

Opens no camera (no camlock needed). Opens one serial port to the rig firmware in
../esp32_sync_rig/esp32_sync_rig.ino and runs, for --duration seconds:

    host:  t1 = host clock;  write "PING <t1>\\n"
    esp:   "PONG <t1> <esp_us_rx> <esp_us_tx> <E|B>"   (E: RX start bit captured on GPIO39, B: estimated)
    host:  t4 = host clock when the first bytes of that PONG were seen

Host clock: time.perf_counter_ns on Windows (QueryPerformanceCounter), CLOCK_MONOTONIC on Linux,
time.perf_counter_ns elsewhere (mach_absolute_time on macOS). Same clocks as the per-frame
log field host_arrival_ns (see ../../README.md).

Estimator (NTP-style, per ping):
    delay  = (t4 - t1) - (esp_tx - esp_rx)            path delay with the ESP32 turnaround removed
    offset = ((esp_rx - t1) + (esp_tx - t4)) / 2      esp_ns - host_ns, exact if the two paths are equal
Then min-delay filtering: in each --window seconds keep the ping with the smallest delay, and fit
offset = a + b * (t1 - t_ref) by least squares. b * 1e6 is the ESP32 rate relative to the host in ppm.
The unknown path asymmetry is bounded only by +-min_delay/2; that bound is reported, not removed.
A second offset assumes the bridge forwards the PONG only after its last byte (serialization time
on the return path only) and is reported alongside; which one is closer is unknown until the
S3 SOF path (README "Clock options") calibrates it.

RUN (from the repo root):
  uv run --script research/usb_cameras/sync_rig/host/esp32_clock_sync.py --list-ports
  uv run --script research/usb_cameras/sync_rig/host/esp32_clock_sync.py --port COM5 --duration 60
  uv run --script research/usb_cameras/sync_rig/host/esp32_clock_sync.py --self-test   (no hardware)

Writes results/<platform>/<hostname>/sync_rig_clock/result_<utc>.json and pings_<utc>.csv
under research/usb_cameras/ (or --out-dir).
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import math
import platform
import random
import socket
import statistics
import sys
import time
from pathlib import Path

AREA_ROOT = Path(__file__).resolve().parents[2]  # research/usb_cameras
TEST_NAME = "sync_rig_clock"
DEFAULT_BAUD = 921600


# ---------------------------------------------------------------------------------------------
# Host clock and platform naming
# ---------------------------------------------------------------------------------------------

def host_clock():
    """Return (now_ns function, description). Must match host_arrival_ns in the frame logs."""
    if sys.platform.startswith("linux"):
        return (lambda: time.clock_gettime_ns(time.CLOCK_MONOTONIC)), "CLOCK_MONOTONIC (time.clock_gettime_ns)"
    if sys.platform == "win32":
        return time.perf_counter_ns, "QueryPerformanceCounter (time.perf_counter_ns)"
    return time.perf_counter_ns, "time.perf_counter_ns (mach_absolute_time on macOS)"


def platform_name() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux" if sys.platform.startswith("linux") else sys.platform


def environment(clock_desc: str) -> dict:
    env = {
        "os": platform.platform(),
        "os_version": platform.version(),
        "python": sys.version,
        "host_clock": clock_desc,
    }
    try:
        info = time.get_clock_info("perf_counter")
        env["perf_counter_info"] = {"implementation": info.implementation, "resolution_s": info.resolution}
    except Exception:  # pragma: no cover - informational only
        pass
    try:
        import serial  # noqa: PLC0415

        env["pyserial"] = serial.__version__
    except ImportError:
        env["pyserial"] = None
    return env


# ---------------------------------------------------------------------------------------------
# Serial line reader (busy-polls in_waiting so arrival stamps are taken as early as possible)
# ---------------------------------------------------------------------------------------------

class LineReader:
    def __init__(self, ser, clock):
        self.ser, self.clock = ser, clock
        self.buf = bytearray()
        self.buf_first_ns = None  # arrival time of the chunk holding the first byte of self.buf
        self.lines: list[tuple[int, int, str]] = []  # (first_byte_ns, last_byte_ns, text)

    def poll(self) -> None:
        n = self.ser.in_waiting
        if not n:
            return
        t = self.clock()
        data = self.ser.read(n)
        for b in data:
            if not self.buf and self.buf_first_ns is None:
                self.buf_first_ns = t
            if b in (10, 13):  # \n or \r ends a line
                if self.buf:
                    text = self.buf.decode("ascii", "replace")
                    self.lines.append((self.buf_first_ns, t, text))
                self.buf.clear()
                self.buf_first_ns = None
            else:
                self.buf.append(b)

    def take(self) -> list[tuple[int, int, str]]:
        out, self.lines = self.lines, []
        return out


def wait_for(reader: LineReader, predicate, timeout_s: float, sink: list | None = None):
    """Poll until a line satisfies predicate; other lines go to sink. Returns the line tuple or None."""
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        reader.poll()
        for item in reader.take():
            if predicate(item[2]):
                return item
            if sink is not None:
                sink.append(item[2])
    return None


def strip_tag(text: str) -> list[str]:
    tok = text.split()
    return tok[1:] if tok and tok[0].startswith("#") else tok


def send_command(ser, reader: LineReader, cmd: str, timeout_s: float = 1.0, sink: list | None = None) -> str | None:
    ser.write((cmd + "\n").encode("ascii"))
    word = cmd.split()[0].upper()

    def is_reply(text: str) -> bool:
        tok = strip_tag(text)
        return len(tok) >= 2 and tok[0] in ("OK", "ERR") and tok[1] == word

    got = wait_for(reader, is_reply, timeout_s, sink)
    return got[2] if got else None


def port_info(port: str) -> dict:
    try:
        from serial.tools import list_ports  # noqa: PLC0415
    except ImportError:
        return {"port": port}
    for p in list_ports.comports():
        if p.device == port:
            return {
                "port": p.device,
                "vid": f"{p.vid:04X}" if p.vid is not None else None,
                "pid": f"{p.pid:04X}" if p.pid is not None else None,
                "description": p.description,
                "manufacturer": p.manufacturer,
                "serial_number": p.serial_number,
                "hwid": p.hwid,
            }
    return {"port": port}


# ---------------------------------------------------------------------------------------------
# Estimation (pure functions; also exercised by --self-test)
# ---------------------------------------------------------------------------------------------

def per_ping(sample: dict) -> tuple[int, float]:
    """Return (delay_ns, offset_ns) for one ping. Integer maths first: host ns values exceed float precision."""
    t1, t4 = sample["host_tx_ns"], sample["host_rx_ns"]
    rx, tx = sample["esp_rx_us"] * 1000, sample["esp_tx_us"] * 1000
    delay = (t4 - t1) - (tx - rx)
    offset = ((rx - t1) + (tx - t4)) / 2
    return delay, offset


def pct(values: list[float], q: float) -> float:
    s = sorted(values)
    if not s:
        return math.nan
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def summary_us(values_ns: list[float]) -> dict:
    v = [x / 1000 for x in values_ns]
    if not v:
        return {"n": 0}
    return {
        "n": len(v),
        "min": round(min(v), 3),
        "p05": round(pct(v, 0.05), 3),
        "p50": round(pct(v, 0.50), 3),
        "p95": round(pct(v, 0.95), 3),
        "max": round(max(v), 3),
    }


def fit_offset_drift(samples: list[dict], window_s: float, serialization_ns: float) -> dict:
    """Min-delay per window, then least-squares offset/drift fit. Offsets are esp_ns - host_ns."""
    if len(samples) < 2:
        return {"error": "fewer than 2 pings"}
    t_ref = samples[0]["host_tx_ns"]
    window_ns = int(window_s * 1e9)
    best: dict[int, tuple[int, float, dict]] = {}
    for s in samples:
        d, off = per_ping(s)
        w = (s["host_tx_ns"] - t_ref) // window_ns
        if w not in best or d < best[w][0]:
            best[w] = (d, off, s)
    pts = [((s["host_tx_ns"] - t_ref) / 1e9, off, d) for d, off, s in best.values()]  # (seconds, ns, ns)
    pts.sort()
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    if len(pts) >= 2 and max(xs) > min(xs):
        xm, ym = statistics.fmean(xs), statistics.fmean(ys)
        sxx = sum((x - xm) ** 2 for x in xs)
        slope = sum((x - xm) * (y - ym) for x, y in zip(xs, ys)) / sxx  # ns per s
        intercept = ym - slope * xm
    else:
        slope, intercept = 0.0, ys[0]
    resid = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    mad = statistics.median([abs(r - statistics.median(resid)) for r in resid]) if resid else math.nan
    min_delay = min(p[2] for p in pts)
    ref_esp_ns = t_ref + round(intercept)
    return {
        "method": f"min-delay ping per {window_s:g} s window, least-squares line through the window minima",
        "n_windows": len(pts),
        "ref_host_ns": t_ref,
        "ref_esp_ns": ref_esp_ns,
        "offset_ns_at_ref": round(intercept, 1),
        "offset_ns_at_ref_if_reply_seen_after_last_byte": round(intercept + serialization_ns / 2, 1),
        "drift_ppm_esp_vs_host": round(slope / 1e3, 4),  # ns/s -> ppm
        "residual_std_us": round(statistics.pstdev(resid) / 1000, 3) if len(resid) > 1 else None,
        "residual_mad_us": round(mad / 1000, 3),
        "residual_max_abs_us": round(max(abs(r) for r in resid) / 1000, 3),
        "min_delay_us": round(min_delay / 1000, 3),
        "asymmetry_bound_us": round(min_delay / 2000, 3),
        "mapping": "host_ns = ref_host_ns + (esp_ns - ref_esp_ns) / (1 + drift_ppm_esp_vs_host * 1e-6)",
    }


def analyse(samples: list[dict], window_s: float, baud: int, reply_bytes: float) -> dict:
    delays, rtts, turn, writes = [], [], [], []
    for s in samples:
        d, _ = per_ping(s)
        delays.append(d)
        rtts.append(s["host_rx_ns"] - s["host_tx_ns"])
        turn.append((s["esp_tx_us"] - s["esp_rx_us"]) * 1000)
        writes.append(s["host_write_done_ns"] - s["host_tx_ns"])
    serialization_ns = reply_bytes * 10 / baud * 1e9
    n_edge = sum(1 for s in samples if s.get("rx_src") == "E")
    return {
        "n_pings": len(samples),
        "rx_stamp_source_edge_fraction": round(n_edge / len(samples), 4) if samples else None,
        "rtt_us": summary_us(rtts),
        "delay_us": summary_us(delays),
        "esp_turnaround_us": summary_us(turn),
        "host_write_call_us": summary_us(writes),
        "reply_serialization_us": round(serialization_ns / 1000, 3),
        "fit": fit_offset_drift(samples, window_s, serialization_ns),
    }


# ---------------------------------------------------------------------------------------------
# Hardware run
# ---------------------------------------------------------------------------------------------

def run_hardware(a, clock, clock_desc) -> int:
    import serial  # noqa: PLC0415

    utc_started = datetime.datetime.now(datetime.timezone.utc)
    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout, ser.write_timeout = a.port, a.baud, 0, 1.0
    if not a.allow_reset:
        # Classic DevKit auto-reset: DTR/RTS de-asserted keeps EN and IO0 high. Some drivers still pulse them.
        ser.dtr = False
        ser.rts = False
    ser.open()
    reader = LineReader(ser, clock)
    other_lines: list[str] = []
    try:
        boot = wait_for(reader, lambda t: t.startswith("EV B"), a.boot_wait, other_lines)
        ser.reset_input_buffer()
        version = send_command(ser, reader, "VERSION", sink=other_lines)
        if version is None:
            print(f"no reply to VERSION on {a.port} at {a.baud} baud; is the rig firmware flashed?", file=sys.stderr)
            return 2
        status_before = send_command(ser, reader, "STATUS", sink=other_lines)
        if not a.keep_events:
            send_command(ser, reader, "EVENTS OFF", sink=other_lines)

        samples: list[dict] = []
        lost = 0
        period = 1.0 / a.rate
        t_end = time.perf_counter() + a.duration
        next_t = time.perf_counter()
        seq = 0
        reply_lens: list[int] = []
        while time.perf_counter() < t_end:
            # jittered schedule so pings do not phase-lock to the 1 ms USB frame
            next_t += period * (0.5 + random.random())
            while time.perf_counter() < next_t:
                reader.poll()
                other_lines.extend(t for _, _, t in reader.take())
            t1 = clock()
            msg = b"PING %d\n" % t1
            ser.write(msg)
            t1w = clock()
            want = str(t1)

            def is_pong(text: str, want=want) -> bool:
                tok = strip_tag(text)
                return len(tok) >= 4 and tok[0] == "PONG" and tok[1] == want

            got = wait_for(reader, is_pong, a.timeout, other_lines)
            seq += 1
            if got is None:
                lost += 1
                continue
            first_ns, last_ns, text = got
            tok = strip_tag(text)
            reply_lens.append(len(text) + 2)  # firmware println adds \r\n
            samples.append({
                "seq": seq,
                "host_tx_ns": t1,
                "host_write_done_ns": t1w,
                "host_rx_ns": first_ns,
                "host_rx_last_ns": last_ns,
                "esp_rx_us": int(tok[2]),
                "esp_tx_us": int(tok[3]),
                "rx_src": tok[4] if len(tok) > 4 else None,
            })

        if not a.keep_events:
            send_command(ser, reader, "EVENTS ON", sink=other_lines)
        status_after = send_command(ser, reader, "STATUS", sink=other_lines)
    finally:
        ser.close()

    dev = port_info(a.port)
    notes = []
    if dev.get("vid") == "0403":
        notes.append("FTDI bridge: set the driver latency timer to 1 ms (default 16 ms) or delays are quantized.")
    if not samples:
        print("no PONG received", file=sys.stderr)
        return 3
    reply_bytes = statistics.fmean(reply_lens)
    rec = {
        "test": TEST_NAME,
        "platform": platform_name(),
        "hostname": socket.gethostname(),
        "utc_started": utc_started.isoformat(),
        "command": " ".join(sys.argv),
        "environment": environment(clock_desc),
        "cameras": [],
        "device": {
            **dev,
            "baud": a.baud,
            "boot_line": boot[2] if boot else None,
            "version_line": version,
            "status_before": status_before,
            "status_after": status_after,
        },
        "parameters": {
            "duration_s": a.duration,
            "rate_hz": a.rate,
            "window_s": a.window,
            "timeout_s": a.timeout,
            "allow_reset": a.allow_reset,
            "events_during_run": a.keep_events,
        },
        "measurements": {
            **analyse(samples, a.window, a.baud, reply_bytes),
            "pings_sent": seq,
            "pings_lost": lost,
            "other_lines_seen": len(other_lines),
            "other_lines_head": other_lines[:20],
        },
        "notes": notes + [
            "offset = esp_ns - host_ns; esp_ns = esp_timer_get_time() * 1000 on the rig.",
            "Absolute accuracy is limited by path asymmetry (|bias| <= asymmetry_bound_us); repeatability by residual_std_us.",
            "DRAFT script: written before any hardware run.",
        ],
    }
    out_dir = a.out_dir or (AREA_ROOT / "results" / platform_name() / socket.gethostname() / TEST_NAME)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_started.strftime("%Y%m%dT%H%M%SZ")
    pings_path = out_dir / f"pings_{stamp}.csv"
    with pings_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(samples[0].keys()))
        w.writeheader()
        w.writerows(samples)
    rec["raw_pings_file"] = pings_path.name
    result_path = out_dir / f"result_{stamp}.json"
    result_path.write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec["measurements"]["fit"], indent=1))
    print(f"wrote {result_path}")
    return 0


# ---------------------------------------------------------------------------------------------
# Synthetic self-test (no serial port): known offset/drift, asymmetric random delays
# ---------------------------------------------------------------------------------------------

def self_test(a) -> int:
    rng = random.Random(1)
    offset0_ns, drift_ppm = 3_217_000_000.0, 12.5
    fwd_base, back_base = 180_000, 180_000 + 40 * 10 / a.baud * 1e9  # back path carries a 40-byte reply
    samples = []
    t = 1_000_000_000_000
    for i in range(int(a.duration * a.rate)):
        t += int(1e9 / a.rate)
        fwd = fwd_base + rng.expovariate(1 / 150_000)
        back = back_base + rng.expovariate(1 / 150_000)
        turn = 300_000 + rng.random() * 50_000
        off = offset0_ns + drift_ppm * 1e-6 * (t - 1_000_000_000_000)
        rx_ns = t + fwd + off
        tx_ns = rx_ns + turn
        t4 = int(tx_ns - (off + drift_ppm * 1e-6 * (fwd + turn)) + back)
        samples.append({
            "seq": i, "host_tx_ns": t, "host_write_done_ns": t + 20_000, "host_rx_ns": t4, "host_rx_last_ns": t4,
            "esp_rx_us": int(rx_ns // 1000), "esp_tx_us": int(tx_ns // 1000), "rx_src": "E",
        })
    res = analyse(samples, a.window, a.baud, 40)
    fit = res["fit"]
    true_at_ref = offset0_ns + drift_ppm * 1e-6 * (samples[0]["host_tx_ns"] - 1_000_000_000_000)
    err_raw = fit["offset_ns_at_ref"] - true_at_ref
    err_ser = fit["offset_ns_at_ref_if_reply_seen_after_last_byte"] - true_at_ref
    ok = abs(fit["drift_ppm_esp_vs_host"] - drift_ppm) < 0.5 and abs(err_ser) < 10_000 and \
        abs(err_raw) <= fit["asymmetry_bound_us"] * 1000
    print(json.dumps({
        "self_test": "pass" if ok else "FAIL",
        "true_drift_ppm": drift_ppm,
        "fit_drift_ppm": fit["drift_ppm_esp_vs_host"],
        "offset_error_raw_us": round(err_raw / 1000, 3),
        "offset_error_serialization_corrected_us": round(err_ser / 1000, 3),
        "asymmetry_bound_us": fit["asymmetry_bound_us"],
        "residual_std_us": fit["residual_std_us"],
    }, indent=1))
    return 0 if ok else 1


# ---------------------------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", help="serial port of the rig (COM5, /dev/ttyUSB0, ...)")
    ap.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    ap.add_argument("--duration", type=float, default=60.0, help="seconds of pinging (default 60)")
    ap.add_argument("--rate", type=float, default=50.0, help="mean pings per second (default 50)")
    ap.add_argument("--window", type=float, default=1.0, help="min-delay window in seconds (default 1)")
    ap.add_argument("--timeout", type=float, default=0.2, help="per-ping reply timeout in seconds")
    ap.add_argument("--boot-wait", type=float, default=2.5, help="seconds to wait for the EV B boot line")
    ap.add_argument("--allow-reset", action="store_true", help="do not hold DTR/RTS low on open (DevKit may reset)")
    ap.add_argument("--keep-events", action="store_true", help="leave firmware EV lines on during the run")
    ap.add_argument("--out-dir", type=Path, help="override results/<platform>/<hostname>/sync_rig_clock/")
    ap.add_argument("--list-ports", action="store_true", help="list serial ports and exit")
    ap.add_argument("--self-test", action="store_true", help="run the estimator on synthetic pings (no hardware)")
    a = ap.parse_args()

    clock, clock_desc = host_clock()
    if a.self_test:
        return self_test(a)
    if a.list_ports:
        from serial.tools import list_ports  # noqa: PLC0415

        for p in list_ports.comports():
            print(f"{p.device}\t{p.vid and f'{p.vid:04X}'}:{p.pid and f'{p.pid:04X}'}\t{p.description}\t{p.serial_number}")
        return 0
    if not a.port:
        ap.error("--port is required (or --list-ports / --self-test)")
    return run_hardware(a, clock, clock_desc)


if __name__ == "__main__":
    sys.exit(main())
