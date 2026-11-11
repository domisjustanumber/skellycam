"""Test-frame sources for the uncompressed_intra topic (shared by the functional matrix and the benches).

Every frame is a list of 2-D uint8 arrays, one per plane, tight rows (rows x row_bytes), in the
plane order libav uses for that pix_fmt. Only numpy is needed, so this works in the pinned venv
and in isolated `uv run --script` environments.

Where the inputs come from (real camera data; no camera is opened):
  * yuyv422      : the cameras' own packed YUY2 bytes, corpus sets c930e_1080p_yuy2 / c922_1080p_yuy2.
  * 720p sources : corpus MJPEG set c930e_720p_flash decoded with PyAV's mjpeg decoder to yuvj422p
                   (the cameras send 4:2:2 JPEG), then repacked to yuyv422 exactly (pure byte
                   interleave). This is "derived", not a camera-native uncompressed frame.
Derived formats (all derived from a yuyv422 frame; the derivation is part of the result):
  * uyvy422      : byte swap of each Y/C pair - exact, reversible.
  * yuv422p      : de-interleave - exact, reversible.
  * nv12/yuv420p : 4:2:2 -> 4:2:0 by averaging vertically adjacent chroma rows (rounding up).
  * gray         : the Y plane.
  * gray16le     : 12-bit values in 16-bit LE containers (like V4L2 Y12 / UVC Y16 low-aligned):
                   (Y << 4) | 4 pseudo-random low bits (seeded) standing in for sensor noise.
  * p010le       : MSB-aligned 10-bit (10-bit value << 6), 10-bit value = (8-bit << 2) | 2 noise bits.
  * rgb24/bgr24  : BT.601 limited-range YUV->RGB in numpy (float, rounded, clipped).
  * bayer_rggb8  : RGGB mosaic sampled from the rgb24 frame (R at even/even, B at odd/odd).
  * bayer_rggb16le (12-bit): (bayer8 << 4) | 4 noise bits, low-aligned in 16-bit LE.
  * raw12_packed : MIPI CSI-2 RAW12 packing of the 12-bit mosaic (2 px -> 3 bytes), stored as a
                   gray8 image of width W*3/2.
  * raw10_packed : MIPI CSI-2 RAW10 packing of a 10-bit mosaic ((bayer8<<2)|2 noise bits), 4 px -> 5 bytes,
                   stored as a gray8 image of width W*5/4.
  * bayer8_quad  : the same rearrangement of the 8-bit mosaic, as gray.
  * bayer16_quad : the 12-bit mosaic rearranged into four W/2 x H/2 colour planes tiled 2x2
                   (R | G1 / G2 | B) as gray16le - exact, reversible; tests whether predictive
                   lossless codecs compress de-interleaved CFA better.
The noise bits matter for compressed size: real sensor low bits are noisy, so noise-free padded
values would flatter lossless codecs. Pass noise=False to get zero low bits instead.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

CORPUS = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus")

# pix_fmt -> plane geometry as (rows_factor, rowbytes_factor) relative to (H, W)
PLANES = {
    "yuyv422": [(1, 2)], "uyvy422": [(1, 2)],
    "yuv422p": [(1, 1), (1, 0.5), (1, 0.5)],
    "yuv420p": [(1, 1), (0.5, 0.5), (0.5, 0.5)],
    "nv12": [(1, 1), (0.5, 1)], "nv16": [(1, 1), (1, 1)],
    "p010le": [(1, 2), (0.5, 2)],
    "gray": [(1, 1)], "gray16le": [(1, 2)], "gray12le": [(1, 2)], "gray10le": [(1, 2)],
    "bayer_rggb8": [(1, 1)], "bayer_rggb16le": [(1, 2)],
    "rgb24": [(1, 3)], "bgr24": [(1, 3)], "bgr0": [(1, 4)],
    "gbrp": [(1, 1)] * 3, "gbrp16le": [(1, 2)] * 3,
    "yuv444p": [(1, 1)] * 3,
    "yuv422p10le": [(1, 2), (1, 1), (1, 1)],
    "yuv420p10le": [(1, 2), (0.5, 1), (0.5, 1)],
    "yuv444p16le": [(1, 2)] * 3,
    "rgb48le": [(1, 6)],
}


def plane_shapes(pix_fmt: str, w: int, h: int) -> list[tuple[int, int]]:
    return [(int(h * r), int(w * b)) for r, b in PLANES[pix_fmt]]


def load_index() -> dict:
    return json.loads((CORPUS / "index.json").read_text())


def load_yuy2(set_name: str = "c930e_1080p_yuy2", n: int | None = None) -> tuple[list[np.ndarray], int, int]:
    """Real camera YUY2 frames -> list of (H, 2W) uint8 arrays."""
    meta = load_index()[set_name]
    w, h = meta["width"], meta["height"]
    files = sorted((CORPUS / set_name).glob("frame_*.yuy2"))[: n or None]
    frames = [np.fromfile(f, dtype=np.uint8).reshape(h, w * 2) for f in files]
    return frames, w, h


def load_jpeg_as_yuy2(set_name: str = "c930e_720p_flash", n: int = 8) -> tuple[list[np.ndarray], int, int]:
    """Decode real camera JPEGs (4:2:2) with PyAV and repack exactly to yuyv422."""
    import av  # local import: only needed for the 720p source

    files = sorted((CORPUS / set_name).glob("frame_*.jpg"))[:n]
    out = []
    w = h = 0
    for f in files:
        cc = av.CodecContext.create("mjpeg", "r")
        frames = cc.decode(av.Packet(f.read_bytes())) + cc.decode(None)
        fr = frames[0]
        w, h = fr.width, fr.height
        if fr.format.name not in ("yuvj422p", "yuv422p"):
            raise RuntimeError(f"{f}: decoded as {fr.format.name}, expected 4:2:2")
        y, u, v = (read_planes(fr, "yuv422p"))
        out.append(planar422_to_yuyv(y, u, v))
    return out, w, h


def read_planes(frame, pix_fmt: str | None = None) -> list[np.ndarray]:
    """av.VideoFrame -> tight per-plane uint8 arrays (strips libav line padding)."""
    fmt = pix_fmt or frame.format.name
    if fmt.startswith("yuvj"):
        fmt = "yuv" + fmt[4:]
    shapes = plane_shapes(fmt, frame.width, frame.height)
    res = []
    for p, (rows, rb) in zip(frame.planes, shapes):
        a = np.frombuffer(memoryview(p), dtype=np.uint8).reshape(-1, p.line_size)[:rows, :rb]
        res.append(a.copy())
    return res


def make_frame(planes: list[np.ndarray], pix_fmt: str, w: int, h: int):
    """Tight per-plane arrays -> av.VideoFrame of pix_fmt (bytes copied as-is; no conversion)."""
    import av

    fr = av.VideoFrame(w, h, pix_fmt)
    for p, a in zip(fr.planes, planes):
        dst = np.frombuffer(memoryview(p), dtype=np.uint8).reshape(-1, p.line_size)
        dst[: a.shape[0], : a.shape[1]] = a
    return fr


def planar422_to_yuyv(y: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    h, w = y.shape
    out = np.empty((h, w * 2), np.uint8)
    out[:, 0::2] = y
    out[:, 1::4] = u
    out[:, 3::4] = v
    return out


def yuyv_split(yuyv: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return yuyv[:, 0::2].copy(), yuyv[:, 1::4].copy(), yuyv[:, 3::4].copy()


def _noise(shape, bits: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 1 << bits, size=shape, dtype=np.uint16)


def yuyv_to_rgb24(yuyv: np.ndarray) -> np.ndarray:
    y, u, v = yuyv_split(yuyv)
    u = np.repeat(u, 2, axis=1).astype(np.float32) - 128.0
    v = np.repeat(v, 2, axis=1).astype(np.float32) - 128.0
    yf = (y.astype(np.float32) - 16.0) * 1.164383
    r = yf + 1.596027 * v
    g = yf - 0.391762 * u - 0.812968 * v
    b = yf + 2.017232 * u
    return np.clip(np.rint(np.stack([r, g, b], axis=-1)), 0, 255).astype(np.uint8)


def to_u8_rows(a16: np.ndarray) -> np.ndarray:
    """uint16 (h, w) -> little-endian uint8 rows (h, 2w)."""
    return a16.astype("<u2").view(np.uint8).reshape(a16.shape[0], -1)


def bayer8_from_rgb(rgb: np.ndarray) -> np.ndarray:
    h, w, _ = rgb.shape
    m = np.empty((h, w), np.uint8)
    m[0::2, 0::2] = rgb[0::2, 0::2, 0]  # R
    m[0::2, 1::2] = rgb[0::2, 1::2, 1]  # G1
    m[1::2, 0::2] = rgb[1::2, 0::2, 1]  # G2
    m[1::2, 1::2] = rgb[1::2, 1::2, 2]  # B
    return m


def pack_raw12(m12: np.ndarray) -> np.ndarray:
    p0 = m12[:, 0::2]
    p1 = m12[:, 1::2]
    out = np.empty((m12.shape[0], m12.shape[1] // 2 * 3), np.uint8)
    out[:, 0::3] = (p0 >> 4).astype(np.uint8)
    out[:, 1::3] = (p1 >> 4).astype(np.uint8)
    out[:, 2::3] = (((p1 & 0xF) << 4) | (p0 & 0xF)).astype(np.uint8)
    return out


def unpack_raw12(b: np.ndarray) -> np.ndarray:
    b = b.astype(np.uint16)
    p0 = (b[:, 0::3] << 4) | (b[:, 2::3] & 0xF)
    p1 = (b[:, 1::3] << 4) | (b[:, 2::3] >> 4)
    out = np.empty((b.shape[0], b.shape[1] // 3 * 2), np.uint16)
    out[:, 0::2], out[:, 1::2] = p0, p1
    return out


def pack_raw10(m10: np.ndarray) -> np.ndarray:
    q = [m10[:, i::4] for i in range(4)]
    out = np.empty((m10.shape[0], m10.shape[1] // 4 * 5), np.uint8)
    for i in range(4):
        out[:, i::5] = (q[i] >> 2).astype(np.uint8)
    out[:, 4::5] = ((q[0] & 3) | ((q[1] & 3) << 2) | ((q[2] & 3) << 4) | ((q[3] & 3) << 6)).astype(np.uint8)
    return out


def unpack_raw10(b: np.ndarray) -> np.ndarray:
    b = b.astype(np.uint16)
    lo = b[:, 4::5]
    out = np.empty((b.shape[0], b.shape[1] // 5 * 4), np.uint16)
    for i in range(4):
        out[:, i::4] = (b[:, i::5] << 2) | ((lo >> (2 * i)) & 3)
    return out


def quad_from_mosaic(m: np.ndarray) -> np.ndarray:
    h, w = m.shape
    q = np.empty_like(m)
    q[: h // 2, : w // 2] = m[0::2, 0::2]
    q[: h // 2, w // 2 :] = m[0::2, 1::2]
    q[h // 2 :, : w // 2] = m[1::2, 0::2]
    q[h // 2 :, w // 2 :] = m[1::2, 1::2]
    return q


def mosaic_from_quad(q: np.ndarray) -> np.ndarray:
    h, w = q.shape
    m = np.empty_like(q)
    m[0::2, 0::2] = q[: h // 2, : w // 2]
    m[0::2, 1::2] = q[: h // 2, w // 2 :]
    m[1::2, 0::2] = q[h // 2 :, : w // 2]
    m[1::2, 1::2] = q[h // 2 :, w // 2 :]
    return m


# Source formats this topic tests. Value: (libav pix_fmt to tag the data with, note)
SOURCES = {
    "yuyv422": ("yuyv422", "real camera YUY2"),
    "uyvy422": ("uyvy422", "derived: byte swap of YUY2"),
    "nv12": ("nv12", "derived: YUY2 chroma averaged 4:2:2->4:2:0"),
    "yuv420p": ("yuv420p", "derived: as nv12, planar (I420)"),
    "gray": ("gray", "derived: Y plane"),
    "gray16le": ("gray16le", "derived: 12-bit (Y<<4|noise) in 16-bit LE"),
    "p010le": ("p010le", "derived: 10-bit MSB-aligned"),
    "rgb24": ("rgb24", "derived: BT.601 YUV->RGB"),
    "bgr24": ("bgr24", "derived: BT.601 YUV->RGB, BGR order"),
    "bayer_rggb8": ("bayer_rggb8", "derived: RGGB mosaic of rgb24"),
    "bayer_rggb16le": ("bayer_rggb16le", "derived: 12-bit RGGB mosaic, low-aligned 16-bit LE"),
    "raw12_packed": ("gray", "derived: MIPI RAW12 packed bytes as gray8 W*3/2 wide"),
    "raw10_packed": ("gray", "derived: MIPI RAW10 packed bytes as gray8 W*5/4 wide"),
    "bayer16_quad": ("gray16le", "derived: 12-bit mosaic de-interleaved to 4 tiled colour planes"),
    "bayer8_quad": ("gray", "derived: 8-bit mosaic de-interleaved to 4 tiled colour planes"),
}


def derive(src: str, yuyv: np.ndarray, w: int, h: int, idx: int = 0, noise: bool = True):
    """Return (planes, pix_fmt, width, height) for source format `src` derived from one YUY2 frame."""
    def nz(shape, bits):
        return _noise(shape, bits, 1000 + idx) if noise else np.zeros(shape, np.uint16)

    y, u, v = yuyv_split(yuyv)
    if src == "yuyv422":
        return [yuyv.copy()], "yuyv422", w, h
    if src == "uyvy422":
        o = np.empty_like(yuyv)
        o[:, 0::2], o[:, 1::2] = yuyv[:, 1::2], yuyv[:, 0::2]
        return [o], "uyvy422", w, h
    if src in ("nv12", "yuv420p"):
        u4 = ((u[0::2].astype(np.uint16) + u[1::2] + 1) >> 1).astype(np.uint8)
        v4 = ((v[0::2].astype(np.uint16) + v[1::2] + 1) >> 1).astype(np.uint8)
        if src == "yuv420p":
            return [y, u4, v4], "yuv420p", w, h
        uv = np.empty((h // 2, w), np.uint8)
        uv[:, 0::2], uv[:, 1::2] = u4, v4
        return [y, uv], "nv12", w, h
    if src == "gray":
        return [y], "gray", w, h
    if src == "gray16le":
        return [to_u8_rows((y.astype(np.uint16) << 4) | nz(y.shape, 4))], "gray16le", w, h
    if src == "p010le":
        pl, _, _, _ = derive("nv12", yuyv, w, h, idx, noise)
        y10 = (pl[0].astype(np.uint16) << 2) | nz(pl[0].shape, 2)
        c10 = (pl[1].astype(np.uint16) << 2) | nz(pl[1].shape, 2)
        return [to_u8_rows(y10 << 6), to_u8_rows(c10 << 6)], "p010le", w, h
    rgb = yuyv_to_rgb24(yuyv)
    if src == "rgb24":
        return [rgb.reshape(h, w * 3)], "rgb24", w, h
    if src == "bgr24":
        return [rgb[:, :, ::-1].copy().reshape(h, w * 3)], "bgr24", w, h
    m8 = bayer8_from_rgb(rgb)
    if src == "bayer_rggb8":
        return [m8], "bayer_rggb8", w, h
    if src == "bayer8_quad":
        return [quad_from_mosaic(m8)], "gray", w, h
    m12 = (m8.astype(np.uint16) << 4) | nz(m8.shape, 4)
    if src == "bayer_rggb16le":
        return [to_u8_rows(m12)], "bayer_rggb16le", w, h
    if src == "raw12_packed":
        p = pack_raw12(m12)
        return [p], "gray", p.shape[1], h
    if src == "raw10_packed":
        p = pack_raw10((m8.astype(np.uint16) << 2) | nz(m8.shape, 2))
        return [p], "gray", p.shape[1], h
    if src == "bayer16_quad":
        return [to_u8_rows(quad_from_mosaic(m12))], "gray16le", w, h
    raise KeyError(src)


def self_test() -> None:
    rng = np.random.default_rng(0)
    m12 = rng.integers(0, 4096, (4, 16), dtype=np.uint16)
    assert np.array_equal(unpack_raw12(pack_raw12(m12)), m12)
    m10 = rng.integers(0, 1024, (4, 16), dtype=np.uint16)
    assert np.array_equal(unpack_raw10(pack_raw10(m10)), m10)
    assert np.array_equal(mosaic_from_quad(quad_from_mosaic(m12)), m12)
    print("uintra_frames self-test ok")


if __name__ == "__main__":
    self_test()
