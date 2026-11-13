"""Check MCAP claims against the installed mcap / mcap-protobuf-support / foxglove-schemas-protobuf."""
import inspect, io, os, struct, sys, time
from importlib.metadata import version
from mcap.writer import Writer, CompressionType
from mcap.reader import make_reader
from mcap.stream_reader import StreamReader
from mcap.records import Chunk, MessageIndex, Message, Metadata, Attachment
from foxglove_schemas_protobuf.CompressedImage_pb2 import CompressedImage
from foxglove_schemas_protobuf.RawAudio_pb2 import RawAudio
from mcap_protobuf.writer import Writer as PbWriter

out = sys.argv[1]
for p in ("mcap", "mcap-protobuf-support", "foxglove-schemas-protobuf", "protobuf"):
    print(f"{p}=={version(p)}")
sig = inspect.signature(Writer.__init__)
print("Writer params:", {k: v.default for k, v in sig.parameters.items() if k != "self"})
print("Writer.flush doc:", (Writer.flush.__doc__ or "").strip().splitlines()[0] if hasattr(Writer, "flush") else "NO flush")
print("RawAudio fields:", [f.name for f in RawAudio.DESCRIPTOR.fields])
print("CompressedImage fields:", [f.name for f in CompressedImage.DESCRIPTOR.fields])

N, JPEG = 300, os.urandom(28_000)


def raw_file(path, chunked=True, flush_each=True):
    with open(path, "wb") as f:
        w = Writer(f, compression=CompressionType.NONE, use_chunking=chunked)
        w.start()
        sid = w.register_schema(name="x", encoding="", data=b"")
        cid = w.register_channel(topic="/cam0", message_encoding="", schema_id=sid)
        w.add_metadata("take", {"clock_id": "1", "take_uuid": "abc"})
        w.add_attachment(log_time=0, create_time=0, name="genicam.xml", media_type="application/xml", data=b"<x/>")
        for i in range(N):
            w.add_message(channel_id=cid, log_time=1_000 + i, publish_time=2_000 + i, data=JPEG, sequence=i)
            if flush_each and chunked:
                w.flush()
        w.finish()
    return os.path.getsize(path)


# 1. flush() per message -> one chunk per message; overhead per frame
p = os.path.join(out, "chunk_per_frame.mcap")
size = raw_file(p)
with open(p, "rb") as f:
    s = make_reader(f).get_summary()
print(f"chunk-per-frame: chunks={len(s.chunk_indexes)} messages={s.statistics.message_count} "
      f"file={size} overhead/frame={(size - N * len(JPEG)) / N:.1f} B")

# 2. message index offsets are relative to the uncompressed chunk records
ok = 0
with open(p, "rb") as f:
    chunk = None
    for rec in StreamReader(f, skip_magic=False, emit_chunks=True).records:
        if isinstance(rec, Chunk):
            chunk = rec
        elif isinstance(rec, MessageIndex) and chunk is not None:
            for _t, off in rec.records:
                ok += chunk.data[off] == 0x05  # Message opcode
print("message-index offsets pointing at a Message opcode inside chunk.data:", ok, "/", N)

# 3. unchunked mode, metadata and attachment readback
p2 = os.path.join(out, "unchunked.mcap")
size2 = raw_file(p2, chunked=False)
with open(p2, "rb") as f:
    r = make_reader(f)
    s2 = r.get_summary()
    md = list(r.iter_metadata())
    at = list(r.iter_attachments())
    msgs = list(r.iter_messages())
print(f"unchunked: chunks={len(s2.chunk_indexes)} msgs={len(msgs)} overhead/frame={(size2 - N*len(JPEG))/N:.1f} B "
      f"metadata={[(m.name, m.metadata) for m in md]} attachments={[(a.name, a.media_type) for a in at]}")
m0 = msgs[0][2]
print("message fields:", m0.channel_id, m0.sequence, m0.log_time, m0.publish_time)

# 4. sequence is u32
try:
    raw = io.BytesIO(); w = Writer(raw); w.start()
    c = w.register_channel(topic="/t", message_encoding="", schema_id=0)
    w.add_message(channel_id=c, log_time=0, publish_time=0, data=b"", sequence=2**32)
    print("sequence 2**32: accepted (unexpected)")
except (struct.error, OverflowError, ValueError) as e:
    print("sequence 2**32 rejected:", type(e).__name__, e)

# 5. protobuf CompressedImage wrapper overhead
p3 = os.path.join(out, "pb.mcap")
with open(p3, "wb") as f:
    w = PbWriter(f, chunk_size=1, compression=CompressionType.NONE)
    for i in range(N):
        msg = CompressedImage(frame_id="cam0", format="jpeg", data=JPEG)
        msg.timestamp.FromNanoseconds(5_000 + i)
        w.write_message(topic="/cam0", message=msg, log_time=1_000 + i, publish_time=2_000 + i, sequence=i)
    w.finish()
size3 = os.path.getsize(p3)
with open(p3, "rb") as f:
    s3 = make_reader(f).get_summary()
print(f"protobuf CompressedImage, chunk_size=1: chunks={len(s3.chunk_indexes)} overhead/frame={(size3 - N*len(JPEG))/N:.1f} B")

# 6. truncated chunk-per-frame file: how many messages a streaming read gets before failing
data = open(p, "rb").read()
cut = int(len(data) * 0.6)
n = 0; err = None
try:
    for rec in StreamReader(io.BytesIO(data[:cut]), skip_magic=False, emit_chunks=True, validate_crcs=True).records:
        n += isinstance(rec, Chunk)
except Exception as e:
    err = f"{type(e).__name__}: {e}"
print(f"truncated at 60%: whole chunks read={n} of {N}; then {err}")

# 7. same truncated file through the normal non-seeking reader (no emit_chunks): messages before the error
n = 0; err = None
try:
    for _ in make_reader(io.BytesIO(data[:cut])).iter_messages(log_time_order=False):
        n += 1
except Exception as e:
    err = f"{type(e).__name__}: {e}"
print(f"truncated at 60%, make_reader().iter_messages: messages={n} of {N}; then {err}")
