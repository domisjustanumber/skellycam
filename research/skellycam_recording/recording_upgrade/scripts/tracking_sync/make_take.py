"""Make the synthetic take for the Lichtblick tracking-sync desk test: 2 camera MCAPs + tracking MCAP variants.

Run (after `unset VIRTUAL_ENV`):
  uv run --no-project --python 3.13 --with mcap==1.6.0 --with mcap-protobuf-support==0.6.0 \
    --with foxglove-schemas-protobuf==0.4.0 --with protobuf==7.36.2 --with pillow==13.0.0 \
    python -I make_take.py <outdir>

One synthetic clock, 30 fps, 20 s, 640x360 JPEG (foxglove.CompressedImage).
  c1.mcap  /cameras/c1/image  log_time = arrival, timestamp = arrival - (8 +- 3) ms
  c2.mcap  /cameras/c2/image  log_time = arrival, timestamp UNSET
Each frame: its number as big text and as a 10-bit barcode (y 320..360, 1 = white, 0 = grey).
Tracking files (foxglove.ImageAnnotations on /cameras/<cam>/tracking/annotations), one per variant.
Each tracking result draws its source frame number as text, a frame-dependent line, and as a 10-bit
barcode of filled circles at y = 270 (1 = green, 0 = red), so the overlay frame is decodable from pixels.
take.json records every image and every tracking message (frame, log_time, timestamps) for the checker.
"""
import io, json, random, sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from mcap.writer import CompressionType, Writer
from mcap_protobuf.schema import register_schema
from foxglove_schemas_protobuf.CompressedImage_pb2 import CompressedImage
from foxglove_schemas_protobuf.ImageAnnotations_pb2 import ImageAnnotations
from foxglove_schemas_protobuf.PointsAnnotation_pb2 import PointsAnnotation

T0 = 1_000_000_000_000
SECONDS, FPS, W, H, BITS = 20, 30, 640, 360, 10
LATE_NS = 70_000_000
NF = SECONDS * FPS
GAP = range(300, 330)  # ~1 s with no tracking result (10.0 s .. 11.0 s)
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
rng = random.Random(20261113)
font = ImageFont.load_default(size=96)

arrival = [T0 + i * 1_000_000_000 // FPS + rng.randint(-2_000_000, 2_000_000) for i in range(NF)]
sample = [a - rng.randint(5_000_000, 11_000_000) for a in arrival]
assert all(b > a for a, b in zip(arrival, arrival[1:]))

# Sparse tracked frames: irregular steps of 2..4 frames, nothing inside GAP.
tracked, i = [], 1
while i < NF:
    if i not in GAP:
        tracked.append(i)
    i += rng.choice((2, 3, 3, 4))
tracked_set = set(tracked)


def open_writer(path, topic, cls):
    f = open(path, "wb")
    w = Writer(f, compression=CompressionType.NONE)
    w.start(profile="", library="skellycam tracking_sync make_take.py")
    cid = w.register_channel(topic=topic, message_encoding="protobuf", schema_id=register_schema(w, cls))
    return f, w, cid


def jpeg(cam, i):
    img = Image.new("RGB", (W, H), (20, 20, 60) if cam == "c1" else (60, 20, 20))
    d = ImageDraw.Draw(img)
    d.text((20, 10), f"{cam} F{i:04d}", font=font, fill=(255, 255, 255))
    for b in range(BITS):
        d.rectangle((b * 64, H - 40, b * 64 + 63, H - 1), fill=(255, 255, 255) if (i >> (BITS - 1 - b)) & 1 else (100, 100, 100))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def color(m, r, g, b):
    m.r, m.g, m.b, m.a = r, g, b, 1.0


def annotations(i, stamp_ns):
    """Full tracking result for frame i. stamp_ns None = leave every annotation timestamp unset."""
    msg = ImageAnnotations()
    stamped = []
    for b in range(BITS):
        c = msg.circles.add(diameter=36, thickness=2)
        c.position.x, c.position.y = b * 64 + 32, 270
        color(c.fill_color, *((0, 1, 0) if (i >> (BITS - 1 - b)) & 1 else (1, 0, 0)))
        color(c.outline_color, 0, 0, 0)
        stamped.append(c)
    x = 40 + (i * 7) % 560  # frame-dependent "skeleton"
    p = msg.points.add(type=PointsAnnotation.LINE_STRIP, thickness=4)
    for dx, dy in ((0, 150), (20, 190), (40, 150), (60, 200)):
        q = p.points.add(); q.x, q.y = x + dx, dy
    color(p.outline_color, 1, 1, 0)
    stamped.append(p)
    t = msg.texts.add(text=f"T{i:04d}", font_size=40)
    t.position.x, t.position.y = 400, 120
    color(t.text_color, 0, 1, 1); color(t.background_color, 0, 0, 0)
    stamped.append(t)
    for s in stamped:
        if stamp_ns is not None:
            s.timestamp.FromNanoseconds(stamp_ns)
            s.timestamp.SetInParent()  # keep the field present even when stamp_ns == 0
    return msg


def placeholder(stamp_ns):
    """No visible content, but one annotation carrying the image stamp (so sync mode has a key)."""
    msg = ImageAnnotations()
    p = msg.points.add(type=PointsAnnotation.POINTS, thickness=1)
    color(p.outline_color, 0, 0, 0)
    p.timestamp.FromNanoseconds(stamp_ns)
    return msg


take = {"t0_ns": T0, "fps": FPS, "frames": NF, "late_ns": LATE_NS, "gap": [GAP.start, GAP.stop - 1],
        "arrival": arrival, "sample": sample, "tracked": tracked, "variants": {}}

for cam in ("c1", "c2"):
    f, w, cid = open_writer(out / f"{cam}.mcap", f"/cameras/{cam}/image", CompressedImage)
    for i in range(NF):
        msg = CompressedImage(frame_id=cam, data=jpeg(cam, i), format="jpeg")
        if cam == "c1":
            msg.timestamp.FromNanoseconds(sample[i])
        w.add_message(channel_id=cid, log_time=arrival[i], publish_time=arrival[i], data=msg.SerializeToString(), sequence=i)
    w.finish(); f.close()

# name: (camera, frames, delay_ns, annotation stamp rule, untracked-frame filler)
STAMP = {"sample": lambda i: sample[i], "unset": lambda i: None, "logtime": lambda i: arrival[i], "zero": lambda i: 0}
VARIANTS = {
    "c1_copy": ("c1", tracked, 0, "sample", None),
    "c1_late": ("c1", tracked, LATE_NS, "sample", None),
    "c1_dense": ("c1", range(NF), 0, "sample", None),
    "c1_empty_copy": ("c1", tracked, 0, "sample", "empty"),
    "c1_fill_copy": ("c1", tracked, 0, "sample", "placeholder"),
    "c1_fill_late": ("c1", tracked, LATE_NS, "sample", "placeholder"),
    "c2_copy_unset": ("c2", tracked, 0, "unset", None),
    "c2_copy_logtime": ("c2", tracked, 0, "logtime", None),
    "c2_copy_zero": ("c2", tracked, 0, "zero", None),
    "c2_late_unset": ("c2", tracked, LATE_NS, "unset", None),
    "c2_late_logtime": ("c2", tracked, LATE_NS, "logtime", None),
    "c2_dense_logtime": ("c2", range(NF), 0, "logtime", None),
}
for name, (cam, frames, delay, rule, filler) in VARIANTS.items():
    fs = set(frames)
    rows = []  # [frame, log_time, kind]
    f, w, cid = open_writer(out / f"trk_{name}.mcap", f"/cameras/{cam}/tracking/annotations", ImageAnnotations)
    for i in range(NF):
        if i in fs:
            msg, kind = annotations(i, STAMP[rule](i)), "result"
        elif filler == "empty":
            msg, kind = ImageAnnotations(), "empty"
        elif filler == "placeholder":
            msg, kind = placeholder(sample[i]), "placeholder"
        else:
            continue
        t = arrival[i] + delay
        w.add_message(channel_id=cid, log_time=t, publish_time=t, data=msg.SerializeToString(), sequence=len(rows))
        rows.append([i, t, kind])
    w.finish(); f.close()
    take["variants"][name] = {"camera": cam, "delay_ns": delay, "stamp": rule, "filler": filler, "messages": rows}

take["sizes"] = {p.name: p.stat().st_size for p in sorted(out.glob("*.mcap"))}
(out / "take.json").write_text(json.dumps(take))
print(f"frames {NF}, tracked {len(tracked)}, total MB {sum(take['sizes'].values()) / 1e6:.1f}")
