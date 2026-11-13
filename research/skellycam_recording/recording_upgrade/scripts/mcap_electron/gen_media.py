"""Desk test media for the MCAP-in-Electron check (2026-11-13). Provisional test choices, not format decisions.

Usage (unset VIRTUAL_ENV first):
  uv run --no-project --python 3.13 --with mcap==1.6.0 --with mcap-protobuf-support==0.6.0 \
    --with foxglove-schemas-protobuf==0.4.0 --with av==19.0.2 --with numpy==2.5.4 python -I gen_media.py <outdir>

Writes into <outdir>:
  cam0.mcap        /cam0/image, foxglove.CompressedImage (protobuf), jpeg 1920x1080, 1800 frames at 30 fps,
                   compression NONE, flush after each frame (one chunk per frame), chunk + data CRCs.
                   Frame index is a 16-bit code in the top 64 rows: block b (96x64 px at x=96*b) is white if bit b is set.
  cam0_cut60.mcap  first 60 % of cam0.mcap (no summary, no footer).
  mic.mcap         /mic/audio, foxglove.CompressedAudio, format opus, one 20 ms libopus packet per message, 60 s,
                   48 kHz mono; clicks at known sample positions. Channel metadata: sample_rate, channels, pre_skip,
                   opus_head (base64 of the encoder's OpusHead extradata).
  mic_ref.f32      the PCM that went into the encoder (float32 LE), for analysis.
  media.json       frame CRC32 table, frame period, click positions, chunk layout facts, cut offset.
"""
import base64, fractions, json, os, sys, zlib
import av
import numpy as np
from mcap.reader import make_reader
from mcap.stream_reader import StreamReader
from mcap.records import Chunk
from mcap.writer import Writer, CompressionType
from mcap_protobuf.schema import build_file_descriptor_set
from foxglove_schemas_protobuf.CompressedImage_pb2 import CompressedImage
from foxglove_schemas_protobuf.CompressedAudio_pb2 import CompressedAudio

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
W, H, FPS, N = 1920, 1080, 30, 1800
PERIOD_NS = 1_000_000_000 // FPS          # 33,333,333 ns; frame i at T0 + i * PERIOD_NS (rounded, see below)
T0 = 1_000_000_000                        # 1 s, keeps audio log_time (which starts 312 samples early) positive
BLOCK_W, CODE_H, BITS = 96, 64, 16
rng = np.random.default_rng(13)


def frame_ns(i):
    return T0 + (i * 1_000_000_000) // FPS


def jpeg_encoder(q):
    enc = av.CodecContext.create("mjpeg", "w")
    enc.width, enc.height, enc.pix_fmt = W, H, "yuvj420p"
    enc.time_base = fractions.Fraction(1, FPS)
    enc.flags |= av.codec.context.Flags.qscale
    enc.qscale = q
    enc.options = {"qscale": str(q)}
    return enc


def make_frames(q=3):
    # qscale 2, 3 and 4 gave the same sizes here; frame size (~150-160 KB) is set by the noise level instead
    enc = jpeg_encoder(q)
    yy, xx = np.mgrid[0:H, 0:W]
    pool = [np.clip(((xx // 4 + yy // 3 + 40 * k) % 256)[..., None] + rng.normal(0, 2.6, (H, W, 3)), 0, 255)
            .astype(np.uint8) for k in range(6)]
    for i in range(N):
        img = np.roll(pool[i % 6], 7 * i, axis=1).copy()
        img[:CODE_H] = 0
        for b in range(BITS):
            if (i >> b) & 1:
                img[:CODE_H, b * BLOCK_W:(b + 1) * BLOCK_W] = 255
        fr = av.VideoFrame.from_ndarray(img, format="rgb24").reformat(format="yuvj420p")
        fr.pts = i
        pk = enc.encode(fr)
        assert len(pk) == 1, len(pk)
        yield bytes(pk[0])


def write_cam(path):
    sizes, crcs = [], []
    with open(path, "wb") as f:
        w = Writer(f, compression=CompressionType.NONE, enable_crcs=True, enable_data_crcs=True)
        w.start(profile="", library="skellycam-desk-test")
        sid = w.register_schema(name="foxglove.CompressedImage", encoding="protobuf",
                                data=build_file_descriptor_set(CompressedImage).SerializeToString())
        cid = w.register_channel(topic="/cam0/image", message_encoding="protobuf", schema_id=sid)
        for i, jpg in enumerate(make_frames()):
            msg = CompressedImage(frame_id="cam0", format="jpeg", data=jpg)
            msg.timestamp.FromNanoseconds(frame_ns(i))
            w.add_message(channel_id=cid, log_time=frame_ns(i), publish_time=frame_ns(i),
                          data=msg.SerializeToString(), sequence=i)
            w.flush()
            sizes.append(len(jpg)); crcs.append(zlib.crc32(jpg))
        w.finish()
    return sizes, crcs


def mic_signal(seconds=60, sr=48000):
    n = seconds * sr
    t = np.arange(n) / sr
    x = 0.08 * np.sin(2 * np.pi * 220 * t) + 0.04 * np.sin(2 * np.pi * 1375 * t) + 0.01 * rng.normal(0, 1, n)
    clicks = [int(sr * (0.5 + k)) + 37 * k for k in range(59)]          # one per second, odd offsets
    for c in clicks:
        x[c:c + 48] += 0.8 * np.hanning(48) * np.sign(np.sin(2 * np.pi * 4000 * np.arange(48) / sr))
    return np.clip(x, -1, 1).astype(np.float32), clicks


def write_mic(path, ref_path):
    sr = 48000
    x, clicks = mic_signal()
    x.tofile(ref_path)
    enc = av.CodecContext.create("libopus", "w")
    enc.sample_rate, enc.layout, enc.format = sr, "mono", "s16"
    enc.time_base = fractions.Fraction(1, sr)
    enc.bit_rate = 64000
    enc.open()
    head = bytes(enc.extradata)
    pre_skip = int.from_bytes(head[10:12], "little")
    pcm = (x * 32767).round().astype(np.int16)
    packets = []
    for s in range(0, len(pcm), 960):
        fr = av.AudioFrame.from_ndarray(pcm[None, s:s + 960], format="s16", layout="mono")
        fr.sample_rate, fr.pts, fr.time_base = sr, s, enc.time_base
        packets += enc.encode(fr)
    packets += enc.encode(None)
    with open(path, "wb") as f:
        w = Writer(f, compression=CompressionType.NONE, enable_crcs=True, enable_data_crcs=True)
        w.start(profile="", library="skellycam-desk-test")
        sid = w.register_schema(name="foxglove.CompressedAudio", encoding="protobuf",
                                data=build_file_descriptor_set(CompressedAudio).SerializeToString())
        cid = w.register_channel(topic="/mic/audio", message_encoding="protobuf", schema_id=sid, metadata={
            "sample_rate": str(sr), "channels": "1", "pre_skip": str(pre_skip),
            "opus_head": base64.b64encode(head).decode()})
        pts = []
        for k, p in enumerate(packets):
            t = T0 + (p.pts * 1_000_000_000) // sr        # packet's first (decoded) sample; pts starts at -pre_skip
            msg = CompressedAudio(format="opus", data=bytes(p))
            msg.timestamp.FromNanoseconds(t)
            w.add_message(channel_id=cid, log_time=t, publish_time=t, data=msg.SerializeToString(), sequence=k)
            pts.append(p.pts)
        w.finish()                                       # default chunk_size: many packets per chunk
    return dict(sample_rate=sr, pre_skip=pre_skip, opus_head_hex=head.hex(), n_input_samples=len(x),
                n_packets=len(packets), first_pts=pts[0], last_pts=pts[-1], packet_samples=960,
                packet_bytes_mean=float(np.mean([p.size for p in packets])), clicks=clicks, click_len=48)


def chunk_facts(path):
    with open(path, "rb") as f:
        s = make_reader(f).get_summary()
    recs_per_chunk = []
    with open(path, "rb") as f:
        for r in StreamReader(f, emit_chunks=True).records:
            if isinstance(r, Chunk):
                ops, o = [], 0
                while o < len(r.data):
                    ops.append(r.data[o]); o += 9 + int.from_bytes(r.data[o + 1:o + 9], "little")
                recs_per_chunk.append(ops)
    ci = s.chunk_indexes
    return dict(n_chunks=len(ci), n_messages=s.statistics.message_count,
                first_chunk_opcodes=recs_per_chunk[0], later_chunk_opcode_sets=sorted({tuple(x) for x in recs_per_chunk[1:]}),
                ), [(c.chunk_start_offset, c.chunk_length, c.message_index_offsets, c.message_index_length) for c in ci]


cam = os.path.join(out, "cam0.mcap")
sizes, crcs = write_cam(cam)
facts, ci = chunk_facts(cam)
size = os.path.getsize(cam)
cut = int(size * 0.6)
with open(cam, "rb") as f, open(os.path.join(out, "cam0_cut60.mcap"), "wb") as g:
    g.write(f.read(cut))
complete = sum(1 for (o, ln, mio, mil) in ci if o + ln <= cut)
complete_with_index = sum(1 for (o, ln, mio, mil) in ci if o + ln + mil <= cut)
mic = write_mic(os.path.join(out, "mic.mcap"), os.path.join(out, "mic_ref.f32"))
json.dump(dict(
    camera=dict(file_size=size, frames=N, width=W, height=H, fps=FPS, t0_ns=T0, frame_ns=[frame_ns(i) for i in range(N)],
                jpeg_bytes_min=min(sizes), jpeg_bytes_max=max(sizes), jpeg_bytes_mean=sum(sizes) / N,
                crc32=crcs, code=dict(block_w=BLOCK_W, height=CODE_H, bits=BITS), **facts,
                cut60=dict(offset=cut, chunks_complete=complete, chunks_complete_with_message_index=complete_with_index)),
    mic=dict(file_size=os.path.getsize(os.path.join(out, "mic.mcap")), **mic)), open(os.path.join(out, "media.json"), "w"))
print(json.dumps({k: v for k, v in facts.items()}), size, min(sizes), max(sizes), sum(sizes) / N, cut, complete,
      complete_with_index, {k: mic[k] for k in ("pre_skip", "n_packets", "first_pts", "last_pts", "packet_bytes_mean")})
