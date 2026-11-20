"""Write synthetic V_MJPEG Matroska files with missing frames (option A and option B).

Usage: python make_files.py OUT_DIR
Media goes to OUT_DIR only (keep it outside the repository).
"""

import json
import struct
import sys
from fractions import Fraction
from pathlib import Path

import av
import cv2
import numpy as np

N, FPS, W, H = 300, 30, 640, 480
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)


def make_jpeg(i: int) -> bytes:
    img = np.full((H, W, 3), 40, np.uint8)
    img[:, :, 0] = (i * 37) % 200  # vary the background a little per frame
    cv2.putText(img, f"{i:03d}", (40, 330), cv2.FONT_HERSHEY_SIMPLEX, 8, (255, 255, 255), 20, cv2.LINE_AA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    assert ok
    return buf.tobytes()


jpegs = [make_jpeg(i) for i in range(N)]
# Reference thumbnails (64x48 grayscale of the decoded JPEG) to identify decoded frames later.
thumbs = np.stack(
    [cv2.resize(cv2.imdecode(np.frombuffer(j, np.uint8), cv2.IMREAD_GRAYSCALE), (64, 48), interpolation=cv2.INTER_AREA) for j in jpegs]
).astype(np.float32)
np.save(out / "ref_thumbs.npy", thumbs)


def write(name: str, missing: set[int], mode: str) -> dict:
    """mode 'B': pts = row index; mode 'A': pts = stored block index."""
    path = out / f"{name}.mkv"
    c = av.open(str(path), "w", format="matroska")
    s = c.add_mux_stream("mjpeg", rate=FPS, width=W, height=H)  # width/height only take effect as kwargs
    k = 0
    for row in range(N):
        if row in missing:
            continue
        p = av.Packet(jpegs[row])
        p.stream = s
        p.time_base = Fraction(1, FPS)
        p.pts = p.dts = row if mode == "B" else k
        p.duration = 1
        p.is_keyframe = True
        c.mux(p)
        k += 1
    c.close()
    return {"file": path.name, "stored": k, "missing": f"{min(missing)}-{max(missing)}" if missing else "none"}


def patch_duration(src: Path, dst: Path, seconds: float) -> str:
    """Byte-patch Segment Info Duration (EBML 0x4489, float, in TimestampScale units = ms)."""
    b = bytearray(src.read_bytes())
    i = b.find(b"\x44\x89")
    size_byte = b[i + 2]
    assert size_byte in (0x88, 0x84), hex(size_byte)
    if size_byte == 0x88:
        old = struct.unpack(">d", b[i + 3 : i + 11])[0]
        b[i + 3 : i + 11] = struct.pack(">d", seconds * 1000)
    else:
        old = struct.unpack(">f", b[i + 3 : i + 7])[0]
        b[i + 3 : i + 7] = struct.pack(">f", seconds * 1000)
    # The per-track DURATION tag is a fixed-width string "HH:MM:SS.nnnnnnnnn".
    t = b.find(b"DURATION")
    j = b.find(b"00:00:", t)
    if t > 0 and 0 < j - t < 40:
        new = f"00:00:{seconds:012.9f}".encode()
        b[j : j + len(new)] = new
    dst.write_bytes(bytes(b))
    return f"Duration {old} ms -> {seconds * 1000} ms"


def default_duration_ns(path: Path):
    b = path.read_bytes()
    i = b.find(b"\x23\xe3\x83")
    if i < 0:
        return None
    size = b[i + 3] & 0x7F  # 1-byte EBML size (enough here)
    return int.from_bytes(b[i + 4 : i + 4 + size], "big")


hole_one = {100}
hole_run = set(range(100, 190))
hole_tail = set(range(200, 300))
hole_head = set(range(0, 10))
info = [
    write("full", set(), "B"),
    write("B-one", hole_one, "B"),
    write("B-run", hole_run, "B"),
    write("B-tail", hole_tail, "B"),
    write("B-head", hole_head, "B"),
    write("B-head30", set(range(0, 30)), "B"),  # first block at exactly 1000 ms (no ms rounding of the start)
    write("A-one", hole_one, "A"),
    write("A-run", hole_run, "A"),
]  # A-tail would be byte-identical to B-tail (no stored block after the hole)

# Try to set the container duration with PyAV (expected not settable for output).
try:
    c = av.open(str(out / "probe_dur.mkv"), "w", format="matroska")
    c.duration = 10_000_000  # type: ignore[attr-defined]
    pyav_duration_settable = "assignment accepted (effect checked below)"
    c.close()
except Exception as e:  # noqa: BLE001
    pyav_duration_settable = f"{type(e).__name__}: {e}"
(out / "probe_dur.mkv").unlink(missing_ok=True)
patch_note = patch_duration(out / "B-tail.mkv", out / "B-tail-dur10.mkv", 10.0)
info.append({"file": "B-tail-dur10.mkv", "stored": 200, "missing": "200-299", "note": patch_note})

# Verify stored bytes equal the JPEG bytes (demux packet of frame 0 and frame 150 of full).
with av.open(str(out / "full.mkv")) as c:
    pk = [bytes(p) for p in c.demux(video=0) if p.size]
assert pk[0] == jpegs[0] and pk[150] == jpegs[150], "stored bytes differ"

meta = {
    "pyav": av.__version__,
    "opencv": cv2.__version__,
    "numpy": np.__version__,
    "bytes_identical_frames_0_150": True,
    "pyav_container_duration_set": pyav_duration_settable,
    "default_duration_ns": {d["file"]: default_duration_ns(out / d["file"]) for d in info},
    "files": info,
}
(out / "files.json").write_text(json.dumps(meta, indent=1))
print(json.dumps(meta, indent=1))
