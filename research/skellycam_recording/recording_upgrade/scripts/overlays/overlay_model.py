"""Shared overlay model for the G3 (overlays) study.

What is in here
- Deterministic synthetic overlay DATA shaped like what skellycam / FreeMoCap draw today:
    * stamp:    skellycam's burned-in text  "camera.id{cam}.idx{idx}.fr{N}"  (opencv_get_frame.py:79-83)
    * skeleton: 33-point MediaPipe body (names + 35 connections from mediapipe_body_schema.json), x/y/visibility
    * charuco:  a ChArUco board with 100 inner corners (11x11 squares) + its ArUco markers, projected
                with a slowly moving homography; a few corners drop out per frame ("undetected")
  The coordinates are synthetic (no tracker is run); the SHAPE (counts, fields) follows
  freemocap/core/viz/image_overlay/{skeleton,charuco}_overlay_data.py.
- A render-level primitive list (circle/line/poly/text/diamond) built from the data + a static style.
- Serializers / parsers:
    data level  (semantic, schema in a header):  jsonl, msgpack (length-prefixed, msgspec), bin (custom, CRC per record)
    render level (pre-drawn vectors):            svg per frame, one svg per recording, ass (subtitle drawing), vtt (JSON cues)
- A cv2 burn-in renderer that mirrors skellycam's draw_doubled_text and skellytracker's
  KeypointAnnotator / CharucoAnnotator calls (circle r=4, line w=2, drawMarker diamond 10/2,
  doubled text 0.5/2, polylines w=2, "Undetected Corners" list).

Only numpy, cv2 and msgspec are needed (all in the skellycam venv).
"""
from __future__ import annotations

import io
import json
import math
import re
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SCHEMA = json.loads((HERE / "mediapipe_body_schema.json").read_text())
SK_NAMES: list[str] = SCHEMA["tracked_points"]
SK_CONN: list[tuple[int, int]] = [(SK_NAMES.index(a), SK_NAMES.index(b)) for a, b in SCHEMA["connections"]]

# ---------------------------------------------------------------------------------------------
# synthetic data
# ---------------------------------------------------------------------------------------------
# A rough standing-person template in a unit box (x right, y down); index order = SK_NAMES.
_TEMPLATE = {
    "nose": (0.50, 0.10), "left_eye_inner": (0.52, 0.085), "left_eye": (0.535, 0.085), "left_eye_outer": (0.55, 0.085),
    "right_eye_inner": (0.48, 0.085), "right_eye": (0.465, 0.085), "right_eye_outer": (0.45, 0.085),
    "left_ear": (0.57, 0.095), "right_ear": (0.43, 0.095), "mouth_left": (0.52, 0.125), "mouth_right": (0.48, 0.125),
    "left_shoulder": (0.62, 0.22), "right_shoulder": (0.38, 0.22), "left_elbow": (0.68, 0.36), "right_elbow": (0.32, 0.36),
    "left_wrist": (0.70, 0.49), "right_wrist": (0.30, 0.49), "left_pinky": (0.71, 0.53), "right_pinky": (0.29, 0.53),
    "left_index": (0.705, 0.535), "right_index": (0.295, 0.535), "left_thumb": (0.69, 0.52), "right_thumb": (0.31, 0.52),
    "left_hip": (0.57, 0.52), "right_hip": (0.43, 0.52), "left_knee": (0.58, 0.72), "right_knee": (0.42, 0.72),
    "left_ankle": (0.585, 0.92), "right_ankle": (0.415, 0.92), "left_heel": (0.575, 0.94), "right_heel": (0.425, 0.94),
    "left_foot_index": (0.62, 0.95), "right_foot_index": (0.38, 0.95),
}
assert set(_TEMPLATE) == set(SK_NAMES)
_TPL = np.array([_TEMPLATE[n] for n in SK_NAMES], dtype=np.float64)

BOARD_SQ = 11  # 11x11 squares -> (11-1)^2 = 100 inner ChArUco corners
N_CORNERS = (BOARD_SQ - 1) ** 2


def _r2(a):
    return np.round(np.asarray(a, dtype=np.float64), 2)


@dataclass
class FrameData:
    f: int
    t_ns: int
    cam: str
    idx: int
    skel: np.ndarray | None = None  # (33,3) x,y,vis
    ch_ids: np.ndarray | None = None  # (n,) int
    ch_xy: np.ndarray | None = None  # (n,2)
    aruco: list[tuple[int, np.ndarray]] = field(default_factory=list)  # (id, (4,2))

    @property
    def stamp(self) -> str:
        return f"camera.id{self.cam}.idx{self.idx}.fr{self.f}"


def make_frames(n: int, w: int, h: int, kind: str, fps: float = 30.0, cam: str = "0", idx: int = 0, seed: int = 1,
                first_frame: int = 0, board_frac: float = 0.55) -> list[FrameData]:
    """kind in {'text', 'skeleton', 'charuco', 'all'}; deterministic for (n,w,h,kind,seed)."""
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        f = first_frame + i
        fd = FrameData(f=f, t_ns=int(round(f * 1e9 / fps)) + int(rng.integers(-2_000_000, 2_000_000)), cam=cam, idx=idx)
        if kind in ("skeleton", "all"):
            ph = 2 * math.pi * f / 90.0
            box_h = 0.85 * h
            box_w = box_h * 0.6
            ox = (w - box_w) / 2 + 0.15 * w * math.sin(ph)
            oy = 0.07 * h
            xy = _TPL.copy()
            xy[:, 0] = ox + xy[:, 0] * box_w + rng.normal(0, 1.5, len(xy))
            xy[:, 1] = oy + xy[:, 1] * box_h + rng.normal(0, 1.5, len(xy))
            # swing the wrists
            for nm, s in (("left_wrist", 1), ("right_wrist", -1)):
                k = SK_NAMES.index(nm)
                xy[k, 1] -= 0.12 * h * (0.5 + 0.5 * math.sin(ph * 2 * s))
            vis = np.clip(0.9 + rng.normal(0, 0.08, len(xy)), 0, 1)
            fd.skel = _r2(np.column_stack([xy, vis]))
        if kind in ("charuco", "all"):
            ang = 0.25 * math.sin(2 * math.pi * f / 150.0)
            sc = board_frac * min(w, h) / BOARD_SQ
            cx, cy = w / 2 + 0.1 * w * math.cos(2 * math.pi * f / 200), h / 2
            persp = 0.0006 * math.sin(2 * math.pi * f / 120)
            H = np.array([[sc * math.cos(ang), -sc * math.sin(ang), cx],
                          [sc * math.sin(ang), sc * math.cos(ang), cy],
                          [persp * sc, 0.0, 1.0]])

            def proj(u, v):
                p = H @ np.array([u - BOARD_SQ / 2, v - BOARD_SQ / 2, 1.0])
                return p[:2] / p[2]

            ids, pts = [], []
            for cid in range(N_CORNERS):
                u, v = cid % (BOARD_SQ - 1) + 1, cid // (BOARD_SQ - 1) + 1
                if rng.random() < 0.05:  # 5% undetected
                    continue
                ids.append(cid)
                pts.append(proj(u, v) + rng.normal(0, 0.3, 2))
            fd.ch_ids = np.array(ids, dtype=np.int64)
            fd.ch_xy = _r2(np.array(pts))
            mid = 0
            for v in range(BOARD_SQ):
                for u in range(BOARD_SQ):
                    if (u + v) % 2 == 1:  # markers on alternate squares
                        if rng.random() > 0.08:
                            m = 0.1
                            c = np.array([proj(u + m, v + m), proj(u + 1 - m, v + m), proj(u + 1 - m, v + 1 - m), proj(u + m, v + 1 - m)])
                            fd.aruco.append((mid, _r2(c)))
                        mid += 1
        out.append(fd)
    return out


def header(w: int, h: int, fps: float, kind: str, cam: str = "0") -> dict:
    return {
        "format": "skellycam-overlay", "version": 1, "camera_id": cam, "image_width": w, "image_height": h,
        "nominal_fps": fps, "kind": kind,
        "skeleton_schema": {"tracker_id": "mediapipe_body", "points": SK_NAMES, "connections": SK_CONN},
        "charuco_board": {"squares_x": BOARD_SQ, "squares_y": BOARD_SQ, "n_corners": N_CORNERS},
    }


# ---------------------------------------------------------------------------------------------
# semantic (data-level) dict form shared by jsonl / msgpack / vtt
# ---------------------------------------------------------------------------------------------
def to_dict(fd: FrameData) -> dict:
    d = {"f": fd.f, "t": fd.t_ns, "cam": fd.cam, "idx": fd.idx}
    if fd.skel is not None:
        d["sk"] = fd.skel.reshape(-1).tolist()
    if fd.ch_ids is not None:
        d["ci"] = fd.ch_ids.tolist()
        d["cxy"] = fd.ch_xy.reshape(-1).tolist()
        d["ar"] = [[mid, c.reshape(-1).tolist()] for mid, c in fd.aruco]
    return d


def from_dict(d: dict) -> FrameData:
    fd = FrameData(f=d["f"], t_ns=d["t"], cam=d["cam"], idx=d["idx"])
    if "sk" in d:
        fd.skel = np.array(d["sk"], dtype=np.float64).reshape(-1, 3)
    if "ci" in d:
        fd.ch_ids = np.array(d["ci"], dtype=np.int64)
        fd.ch_xy = np.array(d["cxy"], dtype=np.float64).reshape(-1, 2)
        fd.aruco = [(m, np.array(c, dtype=np.float64).reshape(4, 2)) for m, c in d["ar"]]
    return fd


def frames_equal(a: FrameData, b: FrameData, tol: float = 0.0) -> bool:
    if (a.f, a.t_ns, a.cam, a.idx) != (b.f, b.t_ns, b.cam, b.idx):
        return False
    for x, y in ((a.skel, b.skel), (a.ch_xy, b.ch_xy)):
        if (x is None) != (y is None):
            return False
        if x is not None and (x.shape != y.shape or np.max(np.abs(x - y), initial=0) > tol):
            return False
    if a.ch_ids is not None and not np.array_equal(a.ch_ids, b.ch_ids):
        return False
    if len(a.aruco) != len(b.aruco):
        return False
    for (m1, c1), (m2, c2) in zip(a.aruco, b.aruco):
        if m1 != m2 or np.max(np.abs(c1 - c2)) > tol:
            return False
    return True


# ---------------------------------------------------------------------------------------------
# data-level writers (append-only, one record per frame) and tolerant readers
# ---------------------------------------------------------------------------------------------
class JsonlWriter:
    ext = ".jsonl"

    def __init__(self, path: Path, hdr: dict):
        self.fh = open(path, "wb")
        self.fh.write(json.dumps({"header": hdr}, separators=(",", ":")).encode() + b"\n")

    def write(self, fd: FrameData):
        self.fh.write(json.dumps(to_dict(fd), separators=(",", ":")).encode() + b"\n")

    def close(self):
        self.fh.close()


def read_jsonl(data: bytes) -> tuple[dict | None, list[FrameData], int]:
    """returns header, frames, n_bad_lines (a torn last line is counted as bad and skipped)."""
    hdr, frames, bad = None, [], 0
    for line in data.split(b"\n"):
        if not line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if "header" in d:
            hdr = d["header"]
        else:
            frames.append(from_dict(d))
    return hdr, frames, bad


class MsgpackWriter:
    """u32 little-endian length + msgspec msgpack payload, per record. Record 0 = header."""
    ext = ".msgpack"

    def __init__(self, path: Path, hdr: dict):
        import msgspec
        self.enc = msgspec.msgpack.Encoder()
        self.fh = open(path, "wb")
        self._put({"header": hdr})

    def _put(self, obj):
        b = self.enc.encode(obj)
        self.fh.write(struct.pack("<I", len(b)) + b)

    def write(self, fd: FrameData):
        self._put(to_dict(fd))

    def close(self):
        self.fh.close()


def read_msgpack(data: bytes) -> tuple[dict | None, list[FrameData], int]:
    import msgspec
    dec = msgspec.msgpack.Decoder()
    pos, hdr, frames, bad = 0, None, [], 0
    while pos + 4 <= len(data):
        (n,) = struct.unpack_from("<I", data, pos)
        if pos + 4 + n > len(data):
            bad += 1  # torn tail
            break
        try:
            d = dec.decode(data[pos + 4: pos + 4 + n])
        except msgspec.DecodeError:
            bad += 1
            break
        pos += 4 + n
        if "header" in d:
            hdr = d["header"]
        else:
            frames.append(from_dict(d))
    return hdr, frames, bad


# custom binary: file = b"SKOV" u16 ver u32 hdr_len hdr_json ; records = MAGIC u32 len payload u32 crc32
_MAGIC = b"OVR1"


class BinWriter:
    ext = ".skov"

    def __init__(self, path: Path, hdr: dict):
        self.fh = open(path, "wb")
        hb = json.dumps(hdr, separators=(",", ":")).encode()
        self.fh.write(b"SKOV" + struct.pack("<HI", 1, len(hb)) + hb)

    @staticmethod
    def encode(fd: FrameData) -> bytes:
        b = io.BytesIO()
        blocks = []
        st = fd.cam.encode()
        blocks.append((0, struct.pack("<H", len(st)) + st + struct.pack("<H", fd.idx)))
        if fd.skel is not None:
            blocks.append((1, struct.pack("<H", len(fd.skel)) + fd.skel.astype("<f4").tobytes()))
        if fd.ch_ids is not None:
            arr = np.zeros(len(fd.ch_ids), dtype=[("id", "<u2"), ("xy", "<f4", 2)])
            arr["id"], arr["xy"] = fd.ch_ids, fd.ch_xy
            blocks.append((2, struct.pack("<H", len(arr)) + arr.tobytes()))
            arr2 = np.zeros(len(fd.aruco), dtype=[("id", "<u2"), ("c", "<f4", 8)])
            for i, (m, c) in enumerate(fd.aruco):
                arr2[i] = (m, c.reshape(-1))
            blocks.append((3, struct.pack("<H", len(arr2)) + arr2.tobytes()))
        b.write(struct.pack("<qqB", fd.f, fd.t_ns, len(blocks)))
        for k, payload in blocks:
            b.write(struct.pack("<BI", k, len(payload)) + payload)
        return b.getvalue()

    def write(self, fd: FrameData):
        p = self.encode(fd)
        self.fh.write(_MAGIC + struct.pack("<I", len(p)) + p + struct.pack("<I", zlib.crc32(p)))

    def close(self):
        self.fh.close()


def _decode_bin_payload(p: bytes) -> FrameData:
    f, t, nb = struct.unpack_from("<qqB", p, 0)
    pos = 17
    fd = FrameData(f=f, t_ns=t, cam="", idx=0)
    for _ in range(nb):
        k, ln = struct.unpack_from("<BI", p, pos)
        pos += 5
        blk = p[pos: pos + ln]
        pos += ln
        if k == 0:
            (sl,) = struct.unpack_from("<H", blk, 0)
            fd.cam = blk[2: 2 + sl].decode()
            (fd.idx,) = struct.unpack_from("<H", blk, 2 + sl)
        elif k == 1:
            (n,) = struct.unpack_from("<H", blk, 0)
            fd.skel = np.frombuffer(blk, "<f4", n * 3, 2).astype(np.float64).reshape(n, 3)
        elif k == 2:
            (n,) = struct.unpack_from("<H", blk, 0)
            arr = np.frombuffer(blk, dtype=[("id", "<u2"), ("xy", "<f4", 2)], count=n, offset=2)
            fd.ch_ids = arr["id"].astype(np.int64)
            fd.ch_xy = arr["xy"].astype(np.float64)
        elif k == 3:
            (n,) = struct.unpack_from("<H", blk, 0)
            arr = np.frombuffer(blk, dtype=[("id", "<u2"), ("c", "<f4", 8)], count=n, offset=2)
            fd.aruco = [(int(a["id"]), a["c"].astype(np.float64).reshape(4, 2)) for a in arr]
    return fd


def read_bin(data: bytes) -> tuple[dict | None, list[FrameData], int]:
    """Sequential read; a bad magic/len/CRC triggers a resync scan for the next MAGIC (counts as bad)."""
    if data[:4] != b"SKOV" or len(data) < 10:
        return None, [], 1
    _, hl = struct.unpack_from("<HI", data, 4)
    if 10 + hl > len(data):
        return None, [], 1
    hdr = json.loads(data[10: 10 + hl])
    pos, frames, bad = 10 + hl, [], 0
    while pos + 8 <= len(data):
        if data[pos: pos + 4] != _MAGIC:
            bad += 1
            nxt = data.find(_MAGIC, pos + 1)
            if nxt < 0:
                break
            pos = nxt
            continue
        (n,) = struct.unpack_from("<I", data, pos + 4)
        end = pos + 8 + n + 4
        if end > len(data):
            bad += 1
            break
        p = data[pos + 8: pos + 8 + n]
        (crc,) = struct.unpack_from("<I", data, pos + 8 + n)
        if zlib.crc32(p) != crc:
            bad += 1
            nxt = data.find(_MAGIC, pos + 1)
            if nxt < 0:
                break
            pos = nxt
            continue
        frames.append(_decode_bin_payload(p))
        pos = end
    return hdr, frames, bad


# ---------------------------------------------------------------------------------------------
# render-level primitives + style (colours follow the FreeMoCap UI / skellytracker defaults)
# ---------------------------------------------------------------------------------------------
STYLE = {
    "stamp": {"size": 0.8, "fill": (255, 210, 210), "outline": (0, 0, 0)},  # BGR, opencv_get_frame.py:88-90
    "sk_center": (0, 170, 0), "sk_left": (255, 136, 68), "sk_right": (68, 68, 255),  # annotation_style.py:13-15 (BGR)
    "corner": (255, 0, 255), "corner_text": (215, 115, 40), "aruco": (0, 255, 0),  # charuco_annotator.py:19-25 (BGR)
}


def _side_color(name: str):
    n = name.lower()
    return STYLE["sk_left"] if "left" in n else STYLE["sk_right"] if "right" in n else STYLE["sk_center"]


def primitives(fd: FrameData, w: int, h: int, label_positions: dict | None = None) -> list[dict]:
    """Render-level list. Coordinates in source-image pixels. label_positions: optional {corner_id: (x,y)}."""
    P = []
    P.append({"k": "text", "x": 10, "y": 40, "s": fd.stamp, "size": 0.8, "fill": STYLE["stamp"]["fill"], "ow": 8, "w": 2})
    if fd.skel is not None:
        sk = fd.skel
        for a, b in SK_CONN:
            if sk[a, 2] >= 0.5 and sk[b, 2] >= 0.5:
                nm = SK_NAMES[a] if _side_color(SK_NAMES[a]) != STYLE["sk_center"] else SK_NAMES[b]
                P.append({"k": "line", "x1": sk[a, 0], "y1": sk[a, 1], "x2": sk[b, 0], "y2": sk[b, 1], "c": _side_color(nm), "w": 2})
        for i, nm in enumerate(SK_NAMES):
            if sk[i, 2] >= 0.5:
                P.append({"k": "circle", "x": sk[i, 0], "y": sk[i, 1], "r": 4, "c": _side_color(nm)})
    if fd.ch_ids is not None:
        for mid, c in fd.aruco:
            P.append({"k": "poly", "pts": c.tolist(), "c": STYLE["aruco"], "w": 2})
        off = max(1, int(h * 0.01))
        for cid, (x, y) in zip(fd.ch_ids.tolist(), fd.ch_xy.tolist()):
            P.append({"k": "diamond", "x": x, "y": y, "size": 10, "c": STYLE["corner"], "w": 2})
            lx, ly = (label_positions or {}).get(cid, (x + off, y + off))
            P.append({"k": "text", "x": lx, "y": ly, "s": f"Corner#{cid}", "size": 0.5, "fill": STYLE["corner_text"], "ow": 4, "w": 2})
        undet = sorted(set(range(N_CORNERS)) - set(fd.ch_ids.tolist()))
        if undet:
            P.append({"k": "text", "x": w - 200, "y": 20, "s": "Undetected Corners:", "size": 0.5, "fill": STYLE["corner_text"], "ow": 4, "w": 2})
            for i, cid in enumerate(undet):
                P.append({"k": "text", "x": w - 200, "y": 40 + i * 20, "s": f" - {cid}", "size": 0.5, "fill": STYLE["corner_text"], "ow": 4, "w": 2})
    return P


def _hex(bgr) -> str:
    b, g, r = bgr
    return f"#{r:02x}{g:02x}{b:02x}"


def _f(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def svg_body(P: list[dict]) -> str:
    """SVG elements for one frame (no <svg> wrapper). Hershey scale s ~ font-size 30*s px."""
    o = []
    for p in P:
        k = p["k"]
        if k == "line":
            o.append(f'<line x1="{_f(p["x1"])}" y1="{_f(p["y1"])}" x2="{_f(p["x2"])}" y2="{_f(p["y2"])}" stroke="{_hex(p["c"])}" stroke-width="{p["w"]}"/>')
        elif k == "circle":
            o.append(f'<circle cx="{_f(p["x"])}" cy="{_f(p["y"])}" r="{p["r"]}" fill="{_hex(p["c"])}"/>')
        elif k == "poly":
            pts = " ".join(f"{_f(x)},{_f(y)}" for x, y in p["pts"])
            o.append(f'<polygon points="{pts}" fill="none" stroke="{_hex(p["c"])}" stroke-width="{p["w"]}"/>')
        elif k == "diamond":
            x, y, s = p["x"], p["y"], p["size"] / 2
            o.append(f'<path d="M{_f(x)} {_f(y - s)}L{_f(x + s)} {_f(y)}L{_f(x)} {_f(y + s)}L{_f(x - s)} {_f(y)}Z" fill="none" stroke="{_hex(p["c"])}" stroke-width="{p["w"]}"/>')
        elif k == "text":
            s = p["s"].replace("&", "&amp;").replace("<", "&lt;")
            o.append(f'<text x="{_f(p["x"])}" y="{_f(p["y"])}" font-size="{_f(30 * p["size"])}" fill="{_hex(p["fill"])}" stroke="#000" stroke-width="{p["ow"] / 2:g}" paint-order="stroke">{s}</text>')
    return "".join(o)


SVG_HEAD = '<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="sans-serif">'


class SvgPerFrameWriter:
    ext = "_svgdir"

    def __init__(self, path: Path, hdr: dict):
        self.dir = Path(str(path))
        self.dir.mkdir(parents=True, exist_ok=True)
        self.w, self.h = hdr["image_width"], hdr["image_height"]
        (self.dir / "header.json").write_text(json.dumps(hdr))

    def write(self, fd: FrameData):
        s = SVG_HEAD.format(w=self.w, h=self.h) + f'<g data-f="{fd.f}" data-t="{fd.t_ns}">' + svg_body(primitives(fd, self.w, self.h)) + "</g></svg>"
        (self.dir / f"frame_{fd.f:06d}.svg").write_bytes(s.encode())

    def close(self):
        pass


class SvgSingleWriter:
    """One SVG per recording, one <g id="f{N}" data-t=..> per frame, appended; closing tag written on close()."""
    ext = ".svg"

    def __init__(self, path: Path, hdr: dict):
        self.w, self.h = hdr["image_width"], hdr["image_height"]
        self.fh = open(path, "wb")
        self.fh.write((SVG_HEAD.format(w=self.w, h=self.h) + "<style>g{display:none}g.on{display:inline}</style>\n").encode())

    def write(self, fd: FrameData):
        self.fh.write((f'<g id="f{fd.f}" data-t="{fd.t_ns}">' + svg_body(primitives(fd, self.w, self.h)) + "</g>\n").encode())

    def close(self):
        self.fh.write(b"</svg>\n")
        self.fh.close()


def read_svg_single_strict(data: bytes) -> int:
    """Strict XML parse; returns number of frame groups (raises on malformed XML)."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(data)
    return sum(1 for g in root if g.tag.endswith("g"))


_G_RE = re.compile(rb'<g id="f(\d+)" data-t="(-?\d+)">.*?</g>\n', re.S)


def read_svg_single_lenient(data: bytes) -> list[int]:
    """Regex recovery of complete <g> groups from a torn file (what a custom reader could do)."""
    return [int(m.group(1)) for m in _G_RE.finditer(data)]


def _vtt_ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    hh, ms = divmod(ms, 3_600_000)
    mm, ms = divmod(ms, 60_000)
    ss, ms = divmod(ms, 1000)
    return f"{hh:02d}:{mm:02d}:{ss:02d}.{ms:03d}"


class VttWriter:
    """WebVTT metadata track; one cue per frame, cue id = frame number, payload = JSON of the data dict.
    Cue time = [pts, next_pts) of the video frame (here pts = f/fps unless pts_s given)."""
    ext = ".vtt"

    def __init__(self, path: Path, hdr: dict):
        self.fps = hdr["nominal_fps"]
        self.fh = open(path, "wb")
        self.fh.write(b"WEBVTT\n\n")

    def write(self, fd: FrameData, pts_s: float | None = None, dur_s: float | None = None):
        st = fd.f / self.fps if pts_s is None else pts_s
        en = st + (1 / self.fps if dur_s is None else dur_s)
        payload = json.dumps(to_dict(fd), separators=(",", ":"))
        self.fh.write(f"{fd.f}\n{_vtt_ts(st)} --> {_vtt_ts(en)}\n{payload}\n\n".encode())

    def close(self):
        self.fh.close()


def read_vtt(data: bytes) -> tuple[None, list[FrameData], int]:
    frames, bad = [], 0
    blocks = data.decode("utf-8", "replace").split("\n\n")
    for b in blocks[1:]:
        lines = b.strip("\n").split("\n")
        if len(lines) < 3:
            if b.strip():
                bad += 1
            continue
        try:
            frames.append(from_dict(json.loads(lines[2])))
        except ValueError:
            bad += 1
    return None, frames, bad


def _ass_ts(sec: float) -> str:
    cs = int(round(sec * 100))
    hh, cs = divmod(cs, 360000)
    mm, cs = divmod(cs, 6000)
    ss, cs = divmod(cs, 100)
    return f"{hh}:{mm:02d}:{ss:02d}.{cs:02d}"


class AssWriter:
    """ASS subtitles. Text items as Dialogue text with \\pos; vectors as one \\p1 drawing per frame."""
    ext = ".ass"

    def __init__(self, path: Path, hdr: dict):
        self.fps = hdr["nominal_fps"]
        self.w, self.h = hdr["image_width"], hdr["image_height"]
        self.fh = open(path, "wb")
        self.fh.write((
            "[Script Info]\nScriptType: v4.00+\nPlayResX: {w}\nPlayResY: {h}\nScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
            "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Arial,24,&H00D2D2FF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,7,0,0,0,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n").format(w=self.w, h=self.h).encode())

    def write(self, fd: FrameData):
        st, en = _ass_ts(fd.f / self.fps), _ass_ts((fd.f + 1) / self.fps)
        P = primitives(fd, self.w, self.h)
        lines = []
        draw = []
        for p in P:
            if p["k"] == "text":
                lines.append(f"Dialogue: 1,{st},{en},Default,,0,0,0,,{{\\an1\\pos({_f(p['x'])},{_f(p['y'])})\\fs{_f(30 * p['size'])}}}{p['s']}")
            elif p["k"] == "line":
                draw.append(f"m {int(p['x1'])} {int(p['y1'])} l {int(p['x2'])} {int(p['y2'])} {int(p['x2']) + 1} {int(p['y2']) + 1} {int(p['x1']) + 1} {int(p['y1']) + 1}")
            elif p["k"] in ("poly",):
                pts = p["pts"]
                draw.append("m " + f"{int(pts[0][0])} {int(pts[0][1])} l " + " ".join(f"{int(x)} {int(y)}" for x, y in pts[1:]))
            elif p["k"] in ("circle", "diamond"):
                x, y, r = int(p["x"]), int(p["y"]), int(p.get("r", p.get("size", 8) / 2))
                draw.append(f"m {x} {y - r} l {x + r} {y} {x} {y + r} {x - r} {y}")
        if draw:
            lines.append(f"Dialogue: 0,{st},{en},Default,,0,0,0,,{{\\an7\\pos(0,0)\\p1\\bord0\\1c&H00FF00&}}" + " ".join(draw) + "{\\p0}")
        self.fh.write(("\n".join(lines) + "\n").encode())

    def close(self):
        self.fh.close()


DATA_FORMATS = {"jsonl": (JsonlWriter, read_jsonl), "msgpack": (MsgpackWriter, read_msgpack), "bin": (BinWriter, read_bin),
                "vtt": (VttWriter, read_vtt)}
RENDER_FORMATS = {"svg_per_frame": SvgPerFrameWriter, "svg_single": SvgSingleWriter, "ass": AssWriter}


# ---------------------------------------------------------------------------------------------
# cv2 burn-in (mirrors the code that draws today)
# ---------------------------------------------------------------------------------------------
def burn_in(img: np.ndarray, P: list[dict]) -> None:
    import cv2
    for p in P:
        k = p["k"]
        if k == "line":
            cv2.line(img, (int(p["x1"]), int(p["y1"])), (int(p["x2"]), int(p["y2"])), p["c"], p["w"])
        elif k == "circle":
            cv2.circle(img, (int(p["x"]), int(p["y"])), p["r"], p["c"], -1)
        elif k == "poly":
            cv2.polylines(img, [np.array(p["pts"], dtype=np.int32)], True, p["c"], p["w"])
        elif k == "diamond":
            cv2.drawMarker(img, (int(p["x"]), int(p["y"])), p["c"], cv2.MARKER_DIAMOND, p["size"], p["w"])
        elif k == "text":
            # stamp: skellycam draw_doubled_text (no LINE_AA, outline thickness*4); charuco: skellytracker (+2, LINE_AA)
            if p["size"] == 0.8:
                cv2.putText(img, p["s"], (int(p["x"]), int(p["y"])), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 8)
                cv2.putText(img, p["s"], (int(p["x"]), int(p["y"])), cv2.FONT_HERSHEY_SIMPLEX, 0.8, p["fill"], 2)
            else:
                cv2.putText(img, p["s"], (int(p["x"]), int(p["y"])), cv2.FONT_HERSHEY_SIMPLEX, p["size"], (0, 0, 0), p["w"] + 2, cv2.LINE_AA)
                cv2.putText(img, p["s"], (int(p["x"]), int(p["y"])), cv2.FONT_HERSHEY_SIMPLEX, p["size"], p["fill"], p["w"], cv2.LINE_AA)


def render_rgba(P: list[dict], w: int, h: int) -> np.ndarray:
    """Overlay-only BGRA image (transparent background) for the alpha-video options.
    Difference matting: draw on black and on white; alpha = 255 - (white - black); colour = black / alpha."""
    blk = np.zeros((h, w, 3), np.uint8)
    wht = np.full((h, w, 3), 255, np.uint8)
    burn_in(blk, P)
    burn_in(wht, P)
    a = 255 - (wht.astype(np.int16) - blk.astype(np.int16)).max(axis=2)
    a = np.clip(a, 0, 255).astype(np.uint8)
    col = np.where(a[..., None] > 0, np.clip(blk.astype(np.float32) * 255.0 / np.maximum(a[..., None], 1), 0, 255), 0).astype(np.uint8)
    return np.dstack([col, a])
