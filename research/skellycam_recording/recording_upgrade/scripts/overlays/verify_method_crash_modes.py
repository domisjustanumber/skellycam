# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy", "msgspec==0.21.1"]
# ///
"""Verifier check (functional, no timing): crash/corruption modes beyond clean tail truncation for the overlay sidecars.
Modes: zero-filled tail after a cut; a 4 KiB zero hole mid-file; one changed byte inside record 150."""
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, r"C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/overlays")
import overlay_model as M

n, W, H = 300, 1280, 720
frames = M.make_frames(n, W, H, "all")
hdr = M.header(W, H, 30.0, "all")
tmp = Path(tempfile.mkdtemp())
out = {}
for fmt, (Wr, R) in M.DATA_FORMATS.items():
    p = tmp / f"x{Wr.ext}"
    w = Wr(p, hdr)
    for fd in frames: w.write(fd)
    w.close()
    data = p.read_bytes()
    tol = 1e-3 if fmt == "bin" else 0.0
    def score(buf):
        try:
            _, got, bad = R(buf)
        except Exception as e:
            return {"exception": f"{type(e).__name__}: {e}"[:120]}
        byf = {f.f: f for f in frames}
        wrong = sum(1 for g in got if g.f not in byf or not M.frames_equal(byf[g.f], g, tol))
        return {"returned": len(got), "returned_but_wrong": wrong, "bad": bad}
    res = {}
    cut = len(data) // 2 + 37
    res["zero_tail_64k"] = score(data[:cut] + b"\0" * 65536)
    res["clean_cut_same_point"] = score(data[:cut])
    h0 = (len(data) // 2) // 4096 * 4096
    res["zero_hole_4k_mid"] = score(data[:h0] + b"\0" * 4096 + data[h0 + 4096:])
    # change one byte in the middle of record 150's numeric payload
    s = M.BinWriter.encode(frames[150]) if fmt == "bin" else None
    if fmt == "bin":
        i = data.find(s) + len(s) // 2
    elif fmt in ("jsonl", "vtt"):
        key = (json.dumps(M.to_dict(frames[150]), separators=(",", ":"))).encode()
        st = data.find(key); i = st + len(key) // 2
        while not (48 <= data[i] <= 57): i += 1   # a digit
    else:
        import msgspec
        key = msgspec.msgpack.encode(M.to_dict(frames[150])); st = data.find(key); i = st + len(key) // 2
    b = bytearray(data)
    if fmt in ("jsonl", "vtt"):
        b[i] = 48 + ((b[i] - 48 + 1) % 10)
    else:
        b[i] ^= 0x01
    res["one_byte_changed_in_record_150"] = score(bytes(b))
    out[fmt] = res
print(json.dumps(out, indent=1))
