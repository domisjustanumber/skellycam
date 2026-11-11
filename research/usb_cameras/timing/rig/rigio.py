"""Rig event log, ping file and ESP32 <-> host clock mapping (DESIGN.md §F items 1-2). Stdlib + numpy.

Files written by rig_session.py into one run folder:
    rig_events.log    one line per serial line received: "<host_first_ns>\t<host_last_ns>\t<text>"
                      (every line: EV events, OK/ERR replies, PONGs). host_* = QPC ns on Windows.
    rig_pings.csv     one row per answered PING, same columns as sync_rig/host/esp32_clock_sync.py's pings_<utc>.csv
    rig_session.json  standard result JSON; parameters.strobe holds the strobe command, measurements.reply_bytes the
                      mean PONG length used for the serialization correction

Conventions: ESP32 times are esp_timer ns (EV lines are already ns; PONG fields are us and are multiplied by 1000).
Host times are QPC ns, the same clock as host_arrival_ns in the frame logs. offset = esp_ns - host_ns.

The clock fit itself is NOT reimplemented: esp32_clock_sync.analyse() / fit_offset_drift() are imported from
sync_rig/host/esp32_clock_sync.py (its top level imports only the standard library).
"""
from __future__ import annotations

import csv
import importlib.util
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

AREA_ROOT = Path(__file__).resolve().parents[2]  # research/usb_cameras
CLOCK_SYNC_PATH = AREA_ROOT / "sync_rig" / "host" / "esp32_clock_sync.py"
DEFAULT_BAUD = 921600


def load_clock_sync():
    """Import sync_rig/host/esp32_clock_sync.py as a module (no pyserial needed at import time)."""
    spec = importlib.util.spec_from_file_location("esp32_clock_sync", CLOCK_SYNC_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------------------------------------------

@dataclass
class RigEvents:
    strobes: list[dict] = field(default_factory=list)   # {k, t_rise_ns, t_fall_ns, host_first_ns}
    anchors: list[dict] = field(default_factory=list)   # EV K
    boots: list[str] = field(default_factory=list)      # EV B lines
    errors: list[str] = field(default_factory=list)     # EV E lines
    replies: list[str] = field(default_factory=list)    # OK / ERR lines
    other: int = 0
    lines: int = 0


def parse_event_line(text: str) -> tuple[str, list[str]] | None:
    """Return (kind, tokens) for an EV line ("S", "K", "B", "E", "A", "F", "BTN") or None. Tags are stripped."""
    tok = text.split()
    if tok and tok[0].startswith("#"):
        tok = tok[1:]
    if len(tok) >= 2 and tok[0] == "EV":
        return tok[1], tok[2:]
    return None


def read_events(path: Path) -> RigEvents:
    ev = RigEvents()
    with Path(path).open("r", encoding="ascii", errors="replace") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if not line:
                continue
            parts = line.split("\t", 2)
            if len(parts) != 3:
                continue
            first_ns, _last_ns, text = int(parts[0]), int(parts[1]), parts[2]
            ev.lines += 1
            p = parse_event_line(text)
            if p is None:
                tok = text.split()
                if tok and tok[0].startswith("#"):
                    tok = tok[1:]
                if tok and tok[0] in ("OK", "ERR"):
                    ev.replies.append(text)
                else:
                    ev.other += 1
                continue
            kind, args = p
            try:
                if kind == "S" and len(args) >= 3:
                    ev.strobes.append({"k": int(args[0]), "t_rise_ns": int(args[1]), "t_fall_ns": int(args[2]),
                                       "host_first_ns": first_ns})
                elif kind == "K" and len(args) >= 4:
                    ev.anchors.append({"cap_ticks64": int(args[0]), "esp_ns": int(args[1]), "resid_ns": int(args[2]),
                                       "half_ns": int(args[3]), "host_first_ns": first_ns})
                elif kind == "B":
                    ev.boots.append(text)
                elif kind == "E":
                    ev.errors.append(text)
                else:
                    ev.other += 1
            except ValueError:
                ev.other += 1
    return ev


def strobe_table(strobes: list[dict], gap_ns: float | None) -> dict:
    """Arrays of strobe centres and pulse identity.

    t_c = (t_rise + t_fall) / 2 is used everywhere: for a linear sensor the 50 % crossing of each band edge sits
    exactly half a pulse width after the rise (sync_rig/DESIGN.md §B, written there for w -> 0).
    pulse = 1 for single strobes and the first pulse of a double strobe, 2 for the second pulse. Pulse 2 is
    recognised by its spacing to the previous captured edge (within 25 % of gap_us), not by the parity of k, so a
    lost event cannot flip the labelling.
    cycle = index of the double-strobe cycle (pulse 2 shares its pulse 1's cycle).
    """
    if not strobes:
        z = np.zeros(0)
        return {"t_c": z, "t_rise": z, "width": z, "pulse": z.astype(int), "cycle": z.astype(int), "k": z.astype(int)}
    s = sorted(strobes, key=lambda r: r["t_rise_ns"])
    rise = np.array([r["t_rise_ns"] for r in s], dtype=np.int64)
    fall = np.array([r["t_fall_ns"] for r in s], dtype=np.int64)
    k = np.array([r["k"] for r in s], dtype=np.int64)
    pulse = np.ones(len(s), dtype=int)
    if gap_ns:
        d = np.diff(rise).astype(float)
        is2 = np.abs(d - gap_ns) < 0.25 * gap_ns
        pulse[1:][is2] = 2
    cycle = np.cumsum(pulse == 1) - 1
    # rise + (fall - rise)/2 in integer ns keeps full precision at ~1e12 ns
    t_c = rise + (fall - rise) // 2
    return {"t_c": t_c, "t_rise": rise, "width": (fall - rise), "pulse": pulse, "cycle": cycle, "k": k}


# ---------------------------------------------------------------------------------------------------------------
# Pings and clock fit
# ---------------------------------------------------------------------------------------------------------------

def read_pings(path: Path) -> list[dict]:
    out = []
    with Path(path).open(newline="") as f:
        for r in csv.DictReader(f):
            out.append({
                "seq": int(r["seq"]), "host_tx_ns": int(r["host_tx_ns"]), "host_write_done_ns": int(r["host_write_done_ns"]),
                "host_rx_ns": int(r["host_rx_ns"]), "host_rx_last_ns": int(r["host_rx_last_ns"]),
                "esp_rx_us": int(r["esp_rx_us"]), "esp_tx_us": int(r["esp_tx_us"]), "rx_src": r.get("rx_src") or None,
                # any PONG tokens after the 4th (e.g. the AtomS3 port's USB SOF frame number), kept raw, unused here
                "extra": r.get("extra") or "",
            })
    return out


def asymmetry_source(device: dict) -> str:
    """Where the unknown ping-path asymmetry comes from, by USB VID of the rig's serial port."""
    vid = (device or {}).get("vid")
    if vid and vid.upper() == "303A":
        return "native USB CDC (bulk IN polling), Espressif VID 303A (e.g. AtomS3 Lite USB Serial/JTAG)"
    if vid:
        return f"USB-serial bridge (VID {vid}): UART serialization + bridge forwarding + bulk IN polling"
    return "unknown serial path (port VID not recorded)"


@dataclass
class ClockMap:
    """host_ns <-> esp_ns from the min-delay ping fit. Two variants of the offset are carried (README "Clock
    correlation"): 'first_byte' (PONG stamped at its first bytes) and 'last_byte' (bridge forwards after the last byte).
    Neither is known to be right until the ESP32-S3 SOF lock (test plan V7) exists, so absolute results carry both."""
    ref_host_ns: int
    offset_first_ns: float
    offset_last_ns: float
    drift_ppm: float                 # ESP32 rate relative to host, ppm
    asymmetry_bound_us: float
    residual_std_us: float | None
    fit: dict

    def esp_to_host(self, esp_ns, variant: str = "first_byte"):
        off = self.offset_first_ns if variant == "first_byte" else self.offset_last_ns
        ref_esp = self.ref_host_ns + off
        return self.ref_host_ns + (np.asarray(esp_ns, dtype=np.float64) - ref_esp) / (1.0 + self.drift_ppm * 1e-6)

    def host_to_esp(self, host_ns, variant: str = "first_byte"):
        off = self.offset_first_ns if variant == "first_byte" else self.offset_last_ns
        ref_esp = self.ref_host_ns + off
        return ref_esp + (np.asarray(host_ns, dtype=np.float64) - self.ref_host_ns) * (1.0 + self.drift_ppm * 1e-6)

    def esp_delta_to_host(self, esp_delta_ns):
        """Offset-free mapping of a duration (only the rate matters)."""
        return np.asarray(esp_delta_ns, dtype=np.float64) / (1.0 + self.drift_ppm * 1e-6)


def clock_fit(pings: list[dict], baud: int = DEFAULT_BAUD, reply_bytes: float = 45.0, window_s: float = 1.0) -> dict:
    cs = load_clock_sync()
    return cs.analyse(pings, window_s, baud, reply_bytes)


def clock_map_from_fit(fit: dict) -> ClockMap:
    f = fit["fit"] if "fit" in fit else fit
    if "error" in f:
        raise ValueError(f"clock fit failed: {f['error']}")
    return ClockMap(ref_host_ns=int(f["ref_host_ns"]), offset_first_ns=float(f["offset_ns_at_ref"]),
                    offset_last_ns=float(f["offset_ns_at_ref_if_reply_seen_after_last_byte"]),
                    drift_ppm=float(f["drift_ppm_esp_vs_host"]), asymmetry_bound_us=float(f["asymmetry_bound_us"]),
                    residual_std_us=f.get("residual_std_us"), fit=f)


def load_rig_run(run_dir: Path) -> dict:
    """Read rig_session.json, rig_events.log and rig_pings.csv from a run folder and fit the clock."""
    run_dir = Path(run_dir)
    ses = json.loads((run_dir / "rig_session.json").read_text())
    params = ses.get("parameters", {})
    strobe = params.get("strobe", {})
    gap_us = float(strobe.get("gap_us") or 0)
    ev = read_events(run_dir / "rig_events.log")
    pings = read_pings(run_dir / "rig_pings.csv")
    baud = int(ses.get("device", {}).get("baud") or DEFAULT_BAUD)
    reply_bytes = float(ses.get("measurements", {}).get("reply_bytes") or 45.0)
    fit = clock_fit(pings, baud, reply_bytes) if len(pings) >= 2 else {"fit": {"error": "fewer than 2 pings"}}
    cmap = None
    try:
        cmap = clock_map_from_fit(fit)
    except (ValueError, KeyError):
        pass
    st = strobe_table(ev.strobes, gap_us * 1000 if gap_us else None)
    ks = np.array([s["k"] for s in sorted(ev.strobes, key=lambda r: r["t_rise_ns"])], dtype=np.int64)
    lost = int(np.sum(np.diff(ks) - 1)) if len(ks) > 1 else 0
    return {"session": ses, "strobe_cfg": strobe, "gap_ns": gap_us * 1000, "events": ev, "strobes": st,
            "pings": pings, "clock_fit": fit, "clock": cmap, "strobe_k_lost": lost,
            "asymmetry_source": asymmetry_source(ses.get("device", {})),
            "rx_src_counts": {s: sum(1 for p in pings if p.get("rx_src") == s) for s in {p.get("rx_src") for p in pings}}}
