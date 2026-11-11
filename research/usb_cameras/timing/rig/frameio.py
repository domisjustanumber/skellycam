"""Frame I/O for the rig analysis (sync_rig/DESIGN.md §F item 3): frames.jsonl, session/controls JSON, MJPEG -> row
profiles, and the per-frame timestamp sources. numpy + OpenCV.

frames.jsonl follows ../../README.md "Per-frame log schema" plus the extra fields of timing/src/mf_uvc_timing.cpp
(UVC fields nested in meta_items[*]._top are hoisted, as tools/analyze_frames.py does). Each row's JPEG is found by
mjpeg_offset / payload_bytes in <key>.mjpeg.

Timestamp sources found automatically:
  host clock (QPC ns): every top-level integer field ending in _ns except readsample_call_ns (when ReadSample was
                       CALLED, not a frame time) -> host_arrival_ns, os_timestamp_ns (MF sample time, ~16 ms grid,
                       REPORT finding 7), mf_undoc_d06f8a46_ns, and any synthetic *_ns field.
  camera clock (ticks): uvc_pts, uvc_scr_stc, uvc_eof_pts, uvc_eof_scr_stc (32-bit, unwrapped). Exact duplicates of
                       another source are dropped (the C922 sends the same PTS in the first and last header).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

HOST_EXCLUDE = {"readsample_call_ns"}
CAMERA_FIELDS = ("uvc_pts", "uvc_scr_stc", "uvc_eof_pts", "uvc_eof_scr_stc")


def load_frames(path: Path) -> list[dict]:
    rows = []
    with Path(path).open("rb") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            for it in r.get("meta_items", []) or []:
                top = it.get("_top")
                if top:
                    for k, v in top.items():
                        r.setdefault(k, v)
            if r.get("os_timestamp_ns") is None and r.get("mf_sample_time_100ns") is not None:
                r["os_timestamp_ns"] = int(r["mf_sample_time_100ns"]) * 100
            rows.append(r)
    rows.sort(key=lambda r: r.get("seq", 0))
    return rows


def load_json(path: Path) -> dict | None:
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None


def load_jsonl(path: Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def unwrap(x: np.ndarray, bits: int = 32) -> np.ndarray:
    m = 1 << bits
    x = x.astype(np.int64)
    d = np.diff(x)
    d = (d + m // 2) % m - m // 2
    return np.concatenate([[x[0]], x[0] + np.cumsum(d)]).astype(np.int64)


def timestamp_sources(frames: list[dict]) -> dict[str, dict]:
    """name -> {"kind": "host"|"camera", "values": int64 array (0 where missing), "valid": bool array}."""
    n = len(frames)
    keys: set[str] = set()
    for r in frames[: min(n, 50)]:
        for k, v in r.items():
            if k.endswith("_ns") and k not in HOST_EXCLUDE and isinstance(v, int) and not isinstance(v, bool):
                keys.add(k)
    out: dict[str, dict] = {}
    for k in sorted(keys):
        vals = np.zeros(n, dtype=np.int64)
        ok = np.zeros(n, dtype=bool)
        for i, r in enumerate(frames):
            v = r.get(k)
            if isinstance(v, int) and not isinstance(v, bool):
                vals[i], ok[i] = v, True
        if ok.sum() >= 3 and np.ptp(vals[ok]) > 0:
            out[k] = {"kind": "host", "values": vals, "valid": ok}
    for k in CAMERA_FIELDS:
        vals = np.zeros(n, dtype=np.int64)
        ok = np.zeros(n, dtype=bool)
        for i, r in enumerate(frames):
            v = r.get(k)
            if isinstance(v, int) and not isinstance(v, bool):
                vals[i], ok[i] = v, True
        if ok.sum() < 3:
            continue
        idx = np.flatnonzero(ok)
        uw = unwrap(vals[idx], 32)
        if np.ptp(uw) == 0:
            continue
        full = np.zeros(n, dtype=np.int64)
        full[idx] = uw
        dup = any(s["kind"] == "camera" and np.array_equal(s["valid"], ok) and np.array_equal(s["values"], full)
                  for s in out.values())
        if not dup:
            out[k] = {"kind": "camera", "values": full, "valid": ok}
    return out


def _cache_key(mjpeg: Path, channel: str, cols: tuple[float, float], gamma: float, n: int) -> str:
    st = mjpeg.stat()
    s = f"{mjpeg.name}|{st.st_size}|{int(st.st_mtime)}|{channel}|{cols[0]:.4f},{cols[1]:.4f}|{gamma:.4f}|{n}|v1"
    return hashlib.sha1(s.encode()).hexdigest()[:16]


def decode_profiles(mjpeg: Path, frames: list[dict], channel: str = "luma", cols: tuple[float, float] = (0.2, 0.8),
                    gamma: float = 2.2, cache_dir: Path | None = None) -> tuple[np.ndarray, dict]:
    """Per-frame LINEAR row profile: mean over the column ROI of lut[pixel], lut = (v/255)**gamma (gamma=1 -> raw).

    channel: 'luma' (JPEG Y, decoded as grayscale) or 'green' (G of the BGR decode). cols: fraction of the width.
    Frames that fail to decode get a NaN row. Returns (profiles [N, H] float32, info)."""
    import cv2  # noqa: PLC0415

    mjpeg = Path(mjpeg)
    if cache_dir is not None:
        cache_dir = Path(cache_dir)
        cache = cache_dir / f"{mjpeg.stem}.profiles_{_cache_key(mjpeg, channel, cols, gamma, len(frames))}.npz"
        if cache.exists():
            z = np.load(cache, allow_pickle=False)
            return z["profiles"], json.loads(str(z["info"]))
    lut = ((np.arange(256, dtype=np.float64) / 255.0) ** gamma).astype(np.float32)
    data = mjpeg.read_bytes()
    profs: list[np.ndarray | None] = []
    shape = None
    bad = 0
    flag = cv2.IMREAD_GRAYSCALE if channel == "luma" else cv2.IMREAD_COLOR
    for r in frames:
        o, n = r.get("mjpeg_offset"), r.get("payload_bytes")
        im = None
        if o is not None and n and o + n <= len(data):
            im = cv2.imdecode(np.frombuffer(data, np.uint8, n, o), flag)
        if im is None:
            profs.append(None)
            bad += 1
            continue
        if channel == "green":
            im = im[:, :, 1]
        H, W = im.shape[:2]
        shape = (H, W)
        c0, c1 = int(round(cols[0] * W)), max(int(round(cols[1] * W)), int(round(cols[0] * W)) + 1)
        profs.append(lut[im[:, c0:c1]].mean(axis=1))
    if shape is None:
        raise ValueError(f"no decodable frame in {mjpeg}")
    P = np.full((len(frames), shape[0]), np.nan, dtype=np.float32)
    for i, p in enumerate(profs):
        if p is not None and len(p) == shape[0]:
            P[i] = p
    info = {"decoded_shape": list(shape), "channel": channel, "cols_frac": list(cols), "gamma": gamma,
            "undecodable_frames": bad, "mjpeg": str(mjpeg)}
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cache, profiles=P, info=json.dumps(info))
    return P, info
