"""Shared helpers for the jpeg_passthrough topic (recording-upgrade study, 2026-11-09).

Paths, corpus loading, real per-frame capture timestamps, JPEG marker walking, DHT stripping.
No camera is touched; everything reads the on-disk corpus built by scripts/common/build_corpus.py.
"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

REPO = Path("C:/Users/Dom/GitHub/freemocap/skellycam")
STUDY = REPO / "research/skellycam_recording/recording_upgrade"
RESULTS = STUDY / "results/jpeg_passthrough"
BENCH_RESULTS = RESULTS / "bench"
RAW = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109")
CORPUS = RAW / "corpus"
MEDIA = RAW / "jpeg_passthrough"  # videos / frame dumps: never in the repo
TEMP = Path("C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/jpeg_passthrough")

# Real capture timestamps for the two "flash" sets: MF IMFSourceReader sample time (QPC, 100 ns) per frame,
# recorded by the usb_cameras timing study. Same capture files the corpus was split from (seq == frame index).
FLASH_JSONL = REPO / "research/usb_cameras/results/windows/Gerald/timing/flash_run1_repositioned/capture"
TS_SOURCE = {
    "c930e_720p_flash": FLASH_JSONL / "vid_046d_pid_0843_mi_00_8_39dec205_0_0000.frames.jsonl",
    "c922_720p_flash": FLASH_JSONL / "vid_046d_pid_085c_mi_00_8_268da596_0_0000.frames.jsonl",
}


def index() -> dict:
    return json.loads((CORPUS / "index.json").read_text())


def load_set(name: str, n: int | None = None) -> list[bytes]:
    files = sorted((CORPUS / name).glob("frame_*.jpg"))
    if n is not None:
        files = files[:n]
    return [f.read_bytes() for f in files]


def load_looped(name: str, n: int) -> list[bytes]:
    """n frames, looping the set's frames in order (stated wherever used)."""
    base = load_set(name)
    return [base[i % len(base)] for i in range(n)]


def real_timestamps_ns(name: str, frames: list[bytes] | None = None) -> list[int]:
    """Per-frame os_timestamp_ns (MF sample time, QPC-based) for a flash set; checks payload sizes match."""
    rows = [json.loads(line) for line in TS_SOURCE[name].read_text().splitlines() if line.strip()]
    rows.sort(key=lambda r: r["seq"])
    if frames is not None:
        for k, (r, f) in enumerate(zip(rows, frames)):
            if r["payload_bytes"] != len(f):
                raise ValueError(f"{name} frame {k}: jsonl payload_bytes {r['payload_bytes']} != corpus {len(f)}")
    return [int(r["os_timestamp_ns"]) for r in rows]


def jitter_timestamps_ns(n: int) -> list[int]:
    """n timestamps that reuse the real inter-frame intervals of c930e_720p_flash (looped).

    Used for sets that have no recorded timestamps (1080p sets): real capture jitter, borrowed.
    """
    ts = real_timestamps_ns("c930e_720p_flash")
    d = [b - a for a, b in zip(ts, ts[1:])]
    out = [0]
    for i in range(1, n):
        out.append(out[-1] + d[(i - 1) % len(d)])
    return out


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


APP_NAMES = {0xE0 + i: f"APP{i}" for i in range(16)}
MARKER_NAMES = {0xC0: "SOF0", 0xC1: "SOF1", 0xC2: "SOF2", 0xC4: "DHT", 0xDB: "DQT", 0xDD: "DRI",
                0xDA: "SOS", 0xFE: "COM", **APP_NAMES}


def segments(b: bytes) -> dict:
    """Walk JPEG header markers up to SOS. Returns marker list (name, offset, length, id-string) and tail facts."""
    out = {"soi": b[:2] == b"\xff\xd8", "markers": [], "eoi_at_end": b.endswith(b"\xff\xd9")}
    pos = 2
    while pos + 4 <= len(b):
        if b[pos] != 0xFF:
            out["markers"].append(("JUNK", pos, 0, ""))
            break
        m = b[pos + 1]
        if m == 0xFF:  # fill byte
            pos += 1
            continue
        L = struct.unpack(">H", b[pos + 2:pos + 4])[0]
        ident = ""
        if 0xE0 <= m <= 0xEF:
            ident = b[pos + 4:pos + 4 + 5].split(b"\x00")[0].decode("latin1", "replace")
        out["markers"].append((MARKER_NAMES.get(m, hex(m)), pos, L + 2, ident))
        if m == 0xDA:
            out["sos_at"] = pos
            break
        pos += 2 + L
    last_eoi = b.rfind(b"\xff\xd9")
    out["last_eoi_at"] = last_eoi
    out["bytes_after_last_eoi"] = len(b) - (last_eoi + 2) if last_eoi >= 0 else None
    return out


def marker_summary(b: bytes) -> str:
    s = segments(b)
    return " ".join(f"{n}{('(' + i + ')') if i else ''}" for n, _, _, i in s["markers"])


def strip_dht(b: bytes) -> bytes:
    """Remove every DHT segment before SOS (UVC MJPEG cameras are allowed to omit DHT)."""
    s = segments(b)
    out = bytearray(b[:2])
    pos = 2
    for name, off, ln, _ in s["markers"]:
        if name == "SOS":
            out += b[off:]
            return bytes(out)
        if name != "DHT":
            out += b[off:off + ln]
    raise ValueError("no SOS")


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, default=str))
