"""Make one synthetic take for the Lichtblick desk test: 2 camera MCAPs + 2 mic MCAP variants.

Run (after `unset VIRTUAL_ENV`):
  uv run --no-project --python 3.13 --with mcap==1.6.0 --with mcap-protobuf-support==0.6.0 \
    --with foxglove-schemas-protobuf==0.4.0 --with av==19.0.2 --with pillow==13.0.0 \
    python -I make_take.py <outdir>

Writes cam0.mcap, cam1.mcap, mic_opus.mcap (foxglove.CompressedAudio opus),
mic_pcm.mcap (foxglove.RawAudio pcm-s16) and take.json (what was written, for the checker).
All files share one synthetic clock: T0 = 1_000_000_000_000 ns.
Every whole second: cam frames are a white flash, audio has a click.
Each frame shows cam id, frame number, time in ms and a 10-bit frame-number barcode (bottom strip).
"""
import base64, io, json, math, struct, sys
from array import array
from pathlib import Path

import av
from PIL import Image, ImageDraw, ImageFont
from mcap.writer import CompressionType, Writer
from mcap_protobuf.schema import register_schema
from foxglove_schemas_protobuf.CompressedImage_pb2 import CompressedImage
from foxglove_schemas_protobuf.CompressedAudio_pb2 import CompressedAudio
from foxglove_schemas_protobuf.RawAudio_pb2 import RawAudio

T0 = 1_000_000_000_000
SECONDS, FPS, W, H = 30, 30, 640, 360
SR, OPUS_FRAME = 48_000, 960
BITS = 10  # frame-number barcode width, 2**10 > 900 frames
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
font_big = ImageFont.load_default(size=72)
font_small = ImageFont.load_default(size=36)


def frame_ns(i: int) -> int:
    return T0 + i * 1_000_000_000 // FPS


def open_writer(path, topic, cls, metadata=None):
    f = open(path, "wb")
    w = Writer(f, compression=CompressionType.NONE)
    w.start(profile="", library="skellycam lichtblick_check make_take.py")
    sid = register_schema(w, cls)
    cid = w.register_channel(topic=topic, message_encoding="protobuf", schema_id=sid, metadata=metadata or {})
    w.add_metadata("take", {"take_id": "desk_b", "clock": "synthetic", "t0_ns": str(T0)})
    return f, w, cid


def jpeg(cam: int, i: int) -> bytes:
    flash = i % FPS == 0
    img = Image.new("RGB", (W, H), (255, 255, 255) if flash else ((20, 20, 60) if cam == 0 else (60, 20, 20)))
    d = ImageDraw.Draw(img)
    ink = (0, 0, 0) if flash else (255, 255, 255)
    t_ms = (frame_ns(i) - T0) / 1e6
    d.text((20, 20), f"cam{cam}", font=font_small, fill=ink)
    d.text((20, 90), f"F {i:04d}", font=font_big, fill=ink)
    d.text((20, 200), f"{t_ms:9.1f} ms", font=font_big, fill=ink)
    # Machine-readable frame number: 10 blocks of 64 px across the bottom 40 px, MSB first, 1 = white, 0 = grey
    for b in range(BITS):
        d.rectangle((b * 64, H - 40, b * 64 + 63, H - 1), fill=(255, 255, 255) if (i >> (BITS - 1 - b)) & 1 else (100, 100, 100))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return buf.getvalue()


summary = {"t0_ns": T0, "fps": FPS, "seconds": SECONDS, "sample_rate": SR}

for cam in (0, 1):
    f, w, cid = open_writer(out / f"cam{cam}.mcap", f"/cam{cam}/image", CompressedImage)
    for i in range(SECONDS * FPS):
        t = frame_ns(i)
        msg = CompressedImage(frame_id=f"cam{cam}", data=jpeg(cam, i), format="jpeg")
        msg.timestamp.FromNanoseconds(t)
        w.add_message(channel_id=cid, log_time=t, publish_time=t, data=msg.SerializeToString(), sequence=i)
        w.flush()
    w.finish(); f.close()
summary["frames_per_cam"] = SECONDS * FPS

# Signal: silence with a 2 ms decaying 3 kHz click starting exactly at each whole second.
n = SECONDS * SR
s16 = array("h", bytes(2 * n))  # little-endian on x86
click = [round(32767 * 0.9 * math.sin(2 * math.pi * 3000 * k / SR) * math.exp(-k / 24)) for k in range(96)]
for s in range(SECONDS):
    s16[s * SR : s * SR + len(click)] = array("h", click)

# Control: RawAudio pcm-s16, 20 ms per message.
f, w, cid = open_writer(out / "mic_pcm.mcap", "/mic/audio", RawAudio)
for m, start in enumerate(range(0, n, OPUS_FRAME)):
    t = T0 + start * 1_000_000_000 // SR
    msg = RawAudio(data=s16[start : start + OPUS_FRAME].tobytes(), format="pcm-s16", sample_rate=SR, number_of_channels=1)
    msg.timestamp.FromNanoseconds(t)
    w.add_message(channel_id=cid, log_time=t, publish_time=t, data=msg.SerializeToString(), sequence=m)
    w.flush()
w.finish(); f.close()
summary["pcm_messages"] = m + 1

# Opus: raw 20 ms packets from libopus.
ctx = av.CodecContext.create("libopus", "w")
ctx.sample_rate, ctx.layout, ctx.format, ctx.bit_rate = SR, "mono", "s16", 64_000
ctx.open()
pre_skip = ctx.initial_padding
packets = []
for start in range(0, n, OPUS_FRAME):
    fr = av.AudioFrame(format="s16", layout="mono", samples=OPUS_FRAME)
    fr.planes[0].update(s16[start : start + OPUS_FRAME].tobytes())
    fr.sample_rate, fr.pts = SR, start
    packets += ctx.encode(fr)
packets += ctx.encode(None)
head = b"OpusHead" + struct.pack("<BBHIhB", 1, 1, pre_skip, SR, 0, 0)
assert ctx.extradata in (None, b"", head), (ctx.extradata, head)  # libopus extradata is the OpusHead
meta = {"sample_rate": str(SR), "channels": "1", "pre_skip": str(pre_skip), "opus_head": base64.b64encode(head).decode()}
f, w, cid = open_writer(out / "mic_opus.mcap", "/mic/audio", CompressedAudio, meta)
pts = []
for m, p in enumerate(packets):
    # packet pts (1/48000) already counts the encoder delay: first decoded sample time = T0 + pts/SR
    t = T0 + p.pts * 1_000_000_000 // SR
    pts.append(p.pts)
    msg = CompressedAudio(data=bytes(p), format="opus")
    msg.timestamp.FromNanoseconds(t)
    w.add_message(channel_id=cid, log_time=t, publish_time=t, data=msg.SerializeToString(), sequence=m)
    w.flush()
w.finish(); f.close()
assert all(b - a == OPUS_FRAME for a, b in zip(pts, pts[1:])), "opus packets are not 960 samples apart"
summary.update(opus_packets=len(packets), opus_pre_skip=pre_skip, opus_first_pts=pts[0], opus_head_b64=meta["opus_head"],
               opus_extradata_b64=base64.b64encode(ctx.extradata or b"").decode(),
               sizes={p.name: p.stat().st_size for p in sorted(out.glob("*.mcap"))})
(out / "take.json").write_text(json.dumps(summary, indent=1))
print(json.dumps(summary, indent=1))
