"""Write synthetic V_MJPEG Matroska files where each missing frame is a BLACK placeholder JPEG block.

Usage: python make_files.py OUT_DIR
Every file has one block per row (300 rows, row r at r/30 s). Media goes to OUT_DIR only (outside the repo).
"""

import json
import sys
from fractions import Fraction
from pathlib import Path

import av
import cv2
import numpy as np

N, FPS = 300, 30
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
SIZES = {"S": (640, 480), "L": (1920, 1080)}
SF = {"422": cv2.IMWRITE_JPEG_SAMPLING_FACTOR_422, "420": cv2.IMWRITE_JPEG_SAMPLING_FACTOR_420,
      "444": cv2.IMWRITE_JPEG_SAMPLING_FACTOR_444}
PATTERNS = {"one": {100}, "run": set(range(100, 190)), "tail": set(range(200, 300)), "head": set(range(10))}


def sof(jpeg: bytes) -> dict:
    """Parse the first SOFn segment: size and per-component sampling factors."""
    i = 2
    while True:
        assert jpeg[i] == 0xFF
        m, ln = jpeg[i + 1], int.from_bytes(jpeg[i + 2:i + 4], "big")
        if m in (0xC0, 0xC1, 0xC2):
            h, w, nc = int.from_bytes(jpeg[i + 5:i + 7], "big"), int.from_bytes(jpeg[i + 7:i + 9], "big"), jpeg[i + 9]
            samp = [(jpeg[i + 11 + 3 * k] >> 4, jpeg[i + 11 + 3 * k] & 15) for k in range(nc)]
            return {"marker": hex(m), "w": w, "h": h, "samp": samp}
        i += 2 + ln


def layout(jpeg: bytes) -> str:
    s = sof(jpeg)["samp"]
    if len(s) == 1:
        return "gray"
    assert s[1] == s[2] == (1, 1), s
    return {(2, 1): "422", (2, 2): "420", (1, 1): "444"}[s[0]]


def enc(img: np.ndarray, sf: str | None, q: int = 90, opt: bool = False) -> bytes:
    p = [cv2.IMWRITE_JPEG_QUALITY, q, cv2.IMWRITE_JPEG_OPTIMIZE, int(opt)]
    if sf:
        p += [cv2.IMWRITE_JPEG_SAMPLING_FACTOR, SF[sf]]
    ok, buf = cv2.imencode(".jpg", img, p)
    assert ok
    return buf.tobytes()


def camera(i: int, w: int, h: int, sf: str) -> bytes:
    k = h / 480
    img = np.full((h, w, 3), 40, np.uint8)
    img[:, :, 0] = (i * 37) % 200  # background varies per frame
    img[: h // 6, : w // 3] = ((i * 11) % 255, 60, 200)  # a coloured patch so chroma errors would show
    cv2.putText(img, f"{i:03d}", (int(40 * k), int(330 * k)), cv2.FONT_HERSHEY_SIMPLEX, 8 * k, (255, 255, 255),
                int(20 * k), cv2.LINE_AA)
    return enc(img, sf)


def placeholders(w: int, h: int, sf: str) -> dict:
    z3, z1 = np.zeros((h, w, 3), np.uint8), np.zeros((h, w), np.uint8)
    return {"same": enc(z3, sf), "samemin": enc(z3, sf, 1, True), "420": enc(z3, "420"), "gray": enc(z1, None),
            "small": enc(np.zeros((16, 16, 3), np.uint8), sf)}


def write(path: Path, blocks: list[bytes], w: int, h: int) -> None:
    c = av.open(str(path), "w", format="matroska")
    s = c.add_mux_stream("mjpeg", rate=FPS, width=w, height=h)  # width/height only take effect as kwargs
    for row, b in enumerate(blocks):
        p = av.Packet(b)
        p.stream, p.time_base, p.pts, p.dts, p.duration, p.is_keyframe = s, Fraction(1, FPS), row, row, 1, True
        c.mux(p)
    c.close()
    with av.open(str(path)) as c:  # stored bytes must equal the source bytes, every block
        assert [bytes(p) for p in c.demux(video=0) if p.size] == blocks, path


# Placeholder byte sizes (q90, q1, q1+optimized Huffman), all layouts, both sizes.
sizes = {}
for sz, (w, h) in SIZES.items():
    for lay in ["422", "420", "444", "gray"]:
        img = np.zeros((h, w) if lay == "gray" else (h, w, 3), np.uint8)
        sf = None if lay == "gray" else lay
        sizes[f"{w}x{h} {lay}"] = {"q90": len(enc(img, sf)), "q1": len(enc(img, sf, 1)), "q1opt": len(enc(img, sf, 1, True)),
                                   "q90opt": len(enc(img, sf, 90, True))}
for lay in ["422", "420", "444"]:
    sizes[f"16x16 {lay}"] = {"q90": len(enc(np.zeros((16, 16, 3), np.uint8), lay))}

# Variants per camera layout. For a 4:2:0 camera P-420 is the same bytes as P-same, so it is not repeated.
VARIANTS = {"422": ["same", "samemin", "420", "gray", "small"], "420": ["same"], "444": ["same", "420"]}
files, layouts = [], {}
for sz, (w, h) in SIZES.items():
    for lay, variants in VARIANTS.items():
        cfg = f"{sz}{lay}"
        cam = [camera(i, w, h, lay) for i in range(N)]
        ph = placeholders(w, h, lay)
        layouts[cfg] = {"camera_sof": sof(cam[0]), "camera_layouts": sorted({layout(j) for j in cam}),
                        "camera_bytes_mean": int(np.mean([len(j) for j in cam])),
                        "placeholders": {k: {"bytes": len(v), "layout": layout(v), "sof": sof(v)} for k, v in ph.items()}}
        assert layouts[cfg]["camera_layouts"] == [lay]
        thumbs = np.stack([cv2.resize(cv2.imdecode(np.frombuffer(j, np.uint8), cv2.IMREAD_GRAYSCALE), (64, 48),
                                      interpolation=cv2.INTER_AREA) for j in cam]).astype(np.float32)
        np.save(out / f"{cfg}_thumbs.npy", thumbs)
        write(out / f"{cfg}__full.mkv", cam, w, h)
        files.append({"file": f"{cfg}__full.mkv", "cfg": cfg, "variant": "none", "pattern": "full", "ph_rows": []})
        for v in variants:
            for pat, rows in PATTERNS.items():
                name = f"{cfg}__{v}__{pat}.mkv"
                write(out / name, [ph[v] if r in rows else cam[r] for r in range(N)], w, h)
                files.append({"file": name, "cfg": cfg, "variant": v, "pattern": pat, "ph_rows": sorted(rows)})
        print(cfg, "done", flush=True)

# One hour of 1080p 4:2:2 placeholders (smallest form) at 30 fps: measured file size.
hour = out / "L422__samemin__hour.mkv"
blk = placeholders(1920, 1080, "422")["samemin"]
c = av.open(str(hour), "w", format="matroska")
s = c.add_mux_stream("mjpeg", rate=FPS, width=1920, height=1080)
for row in range(FPS * 3600):
    p = av.Packet(blk)
    p.stream, p.time_base, p.pts, p.dts, p.duration, p.is_keyframe = s, Fraction(1, FPS), row, row, 1, True
    c.mux(p)
c.close()
hour_info = {"blocks": FPS * 3600, "block_bytes": len(blk), "file_bytes": hour.stat().st_size,
             "overhead_per_block": (hour.stat().st_size - FPS * 3600 * len(blk)) / (FPS * 3600)}
hour.unlink()  # 1.7 GB; only the size is needed

meta = {"pyav": av.__version__, "opencv": cv2.__version__, "numpy": np.__version__, "placeholder_sizes": sizes,
        "layouts": layouts, "hour": hour_info, "files": files, "all_blocks_byte_identical": True}
(out / "files.json").write_text(json.dumps(meta, indent=1))
print(json.dumps({k: meta[k] for k in ["placeholder_sizes", "hour"]}, indent=1))
print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "placeholders"} | {"ph": {p: (x["bytes"], x["layout"]) for p, x in v["placeholders"].items()}} for k, v in layouts.items()}, indent=1))
