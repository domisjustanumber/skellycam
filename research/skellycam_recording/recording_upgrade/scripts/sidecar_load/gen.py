"""T-S4: generate synthetic sidecars for 16 cameras x 1 h, in the layouts the player-load test compares.

Usage: python -I gen.py <out_dir> <fps> [cameras=16] [seconds=3600]   (env SL_ONLY_SKFR=1: write only camNN.skfr)

Per camera NN it writes into <out_dir>/fps<fps>/:
  camNN.skfr  S1 sidecar: 512 B header + N x 64 B records (row-major, as accepted)
              + a compact player index section after the records (layout c, "inside"):
                time_ns i64[N] (the chosen player time), offset u64[N], size u32[N]  = 20 B/frame, 8-aligned.
  camNN.skfc  layout b, fully columnar: 512 B header + one array per field. The player's five columns
              (arrival, fitted, offset, flags, size; 32 B/frame) come first so one Range read gets them.
  camNN.skix  layout c as a separate attachment: 64 B header + the same 20 B/frame columns.
  camNN.mkv   a tiny FFmpeg-written MJPEG MKV with ONE Attachments element holding two AttachedFiles:
              skellycam_frames.skfr (= camNN.skfr) and skellycam_index.skix (= camNN.skix).
              (The JPEG offsets in the sidecar don't point into this dummy MKV: only the load path is tested.)
The synthetic header is NOT the spec header; it only carries what the test needs (n, index position).
"""
import json, os, struct, sys, zlib
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "sidecar_embedding"))
import append_attachment as aa   # helpers only (read-only use)

REC = np.dtype([("arrival", "<i8"), ("sample", "<i8"), ("legacy", "<i8"), ("fitted", "<i8"),
                ("offset", "<u8"), ("size", "<u4"), ("jcrc", "<u4"), ("sfn", "<u4"), ("widx", "<u4"),
                ("flags", "<u4"), ("rcrc", "<u4")])
assert REC.itemsize == 64
F_GAP, F_FIT_VALID, F_OFFSET_FINAL = 1, 1 << 3, 1 << 5
HDR = 512
INT64_MIN = -(1 << 63)


def make_records(cam, fps, seconds, rng):
    period = 1e9 / fps
    n_src = int(round(seconds * fps))
    drop = rng.random(n_src) < 0.002           # ~0.2 % drops
    drop[:5] = False
    sfn = np.nonzero(~drop)[0].astype(np.int64)
    n = sfn.size
    T0 = 300_000_000_000_000 + cam * 7_000_000 + int(rng.integers(0, 1_000_000))   # ~3.5 days of QPC uptime
    drift = 1 + rng.normal(0, 50e-6)
    t_cap = T0 + (sfn * period * drift)
    lat = 30e6
    arrival = (t_cap + lat + rng.exponential(1.0e6, n) + rng.normal(0, 0.2e6, n)).astype(np.int64)
    arrival = np.maximum.accumulate(arrival + np.arange(n))   # strictly increasing
    sample = (np.round((t_cap + rng.normal(0, 0.05e6, n)) / 100) * 100).astype(np.int64)
    legacy = arrival + rng.integers(100_000, 400_000, n)
    fitted = (t_cap + lat + 0.6e6).astype(np.int64)
    size = np.clip(rng.normal(192_000, 15_000, n), 40_000, 400_000).astype(np.uint32)
    overhead = 12 + (np.arange(n) % 30 == 0) * 40      # SimpleBlock header; a Cluster header every 30
    offset = (5_000 + np.concatenate(([0], np.cumsum((size + overhead).astype(np.uint64))[:-1]))).astype(np.uint64)
    flags = np.full(n, F_OFFSET_FINAL, np.uint32)
    fit_valid = cam != 15                         # camera 15: fit not valid -> player uses arrival
    if fit_valid:
        flags |= F_FIT_VALID
    else:
        fitted[:] = INT64_MIN
    gap = np.diff(sfn, prepend=sfn[0] - 1) > 1
    flags[gap] |= F_GAP
    r = np.zeros(n, REC)
    r["arrival"], r["sample"], r["legacy"], r["fitted"] = arrival, sample, legacy, fitted
    r["offset"], r["size"] = offset, size
    r["jcrc"] = rng.integers(0, 2**32, n, dtype=np.uint64).astype(np.uint32)
    r["sfn"], r["widx"], r["flags"] = sfn.astype(np.uint32), np.arange(n, dtype=np.uint32), flags
    raw = r.tobytes()
    mv = memoryview(raw)
    crc = np.fromiter((zlib.crc32(mv[i:i + 60]) for i in range(0, n * 64, 64)), np.uint32, n)
    r["rcrc"] = crc
    chosen = fitted if fit_valid else arrival
    return r, chosen


def skfr_bytes(r, chosen, fps, cam):
    n = r.size
    rec = r.tobytes()
    idx_off = HDR + len(rec)
    assert idx_off % 8 == 0
    index = chosen.astype("<i8").tobytes() + r["offset"].astype("<u8").tobytes() + r["size"].astype("<u4").tobytes()
    h = bytearray(HDR)
    h[0:4] = b"SKFR"
    struct.pack_into("<HHHHI", h, 4, 1, HDR, 64, 0, 0)
    struct.pack_into("<QQQII", h, 16, n, idx_off, n, 1, 0)
    h[48:64] = os.urandom(16)
    struct.pack_into("<qd", h, 64, 0, float(fps))
    js = json.dumps({"synthetic": True, "camera": cam, "fps": fps}).encode()
    struct.pack_into("<I", h, 80, len(js)); h[84:84 + len(js)] = js
    return bytes(h) + rec, index


def skix_bytes(index, n):
    h = bytearray(64)
    h[0:4] = b"SKIX"
    struct.pack_into("<HHIQ", h, 4, 1, 64, 0, n)
    return bytes(h) + index


def skfc_bytes(r, fps):
    n = r.size
    order = ["arrival", "fitted", "offset", "flags", "size", "sample", "legacy", "jcrc", "sfn", "widx"]
    h = bytearray(HDR)
    h[0:4] = b"SKFC"
    struct.pack_into("<HHHHIQ", h, 4, 1, HDR, 0, 0, 0, n)
    body, pos = [], HDR
    for k, name in enumerate(order):
        col = np.ascontiguousarray(r[name]).tobytes()
        pad = (-len(col)) % 8
        struct.pack_into("<4sIQ", h, 64 + 16 * k, name[:4].encode(), r.dtype[name].itemsize, pos)
        body.append(col + b"\0" * pad); pos += len(col) + pad
    return bytes(h) + b"".join(body)


def tiny_mkv(path, fps):
    import av
    from fractions import Fraction
    c = av.open(path, "w", format="matroska")
    s = c.add_stream("mjpeg", rate=fps)
    s.width, s.height, s.pix_fmt = 64, 48, "yuvj420p"
    tb = Fraction(1, fps)
    for i in range(5):
        img = np.full((48, 64, 3), i * 40, np.uint8)
        for p in s.encode(av.VideoFrame.from_ndarray(img, format="rgb24").reformat(format="yuvj420p")):
            p.time_base = tb; c.mux(p)
    for p in s.encode():
        c.mux(p)
    c.close()


def append_two(path, files):
    """Like append_attachment.append, but one Attachments element with several AttachedFiles."""
    with open(path, "r+b") as f:
        head = f.read(64 * 1024)
        file_len = os.fstat(f.fileno()).st_size
        eid, d, size, _ = aa.read_elem(head, 0)
        seg_pos = d + size
        eid, seg_data, seg_size, seg_szlen = aa.read_elem(head, seg_pos)
        assert eid == aa.ID_SEGMENT and seg_size is not None and seg_data + seg_size == file_len
        eid, sh_data, sh_size, _ = aa.read_elem(head, seg_data)
        assert eid == aa.ID_SEEKHEAD
        entries = aa.parse_seekhead(head, sh_data, sh_size)
        span_end = sh_data + sh_size
        eid, vd, vsz, _ = aa.read_elem(head, span_end)
        if eid == aa.ID_VOID: span_end = vd + vsz
        span = span_end - seg_data
        new_entries = entries + [(aa.ID_ATTACHMENTS, file_len - seg_data)]
        sh_body = b"".join(aa.el(aa.ID_SEEK, aa.el(aa.ID_SEEKID, aa.enc_id(i)) + aa.el(aa.ID_SEEKPOS, aa.uint(p))) for i, p in new_entries)
        if aa.read_elem(head, sh_data)[0] == 0xBF:
            sh_body = b"\xbf\x84" + struct.pack("<I", zlib.crc32(sh_body)) + sh_body
        new_sh = aa.el(aa.ID_SEEKHEAD, sh_body)
        pad = span - len(new_sh)
        if pad == 1:
            new_sh = aa.el(aa.ID_SEEKHEAD, sh_body, width=len(aa.enc_size(len(sh_body))) + 1); pad = 0
        assert pad >= 0
        afs = b""
        for name, mime, payload in files:
            uid = int.from_bytes(os.urandom(8), "big") or 1
            afs += aa.el(aa.ID_ATTACHEDFILE, aa.el(aa.ID_FILENAME, name.encode()) + aa.el(aa.ID_FILEMEDIATYPE, mime.encode())
                         + aa.el(aa.ID_FILEUID, uid.to_bytes(8, "big")) + aa.el(aa.ID_FILEDATA, payload))
        att = aa.el(aa.ID_ATTACHMENTS, afs)
        f.seek(file_len); f.write(att)
        f.seek(seg_pos + len(aa.enc_id(aa.ID_SEGMENT))); f.write(aa.enc_size(seg_size + len(att), seg_szlen))
        f.seek(seg_data); f.write(new_sh + (aa.void_of_total(pad) if pad else b""))


def main():
    out, fps = sys.argv[1], int(sys.argv[2])
    cams = int(sys.argv[3]) if len(sys.argv) > 3 else 16
    secs = int(sys.argv[4]) if len(sys.argv) > 4 else 3600
    d = os.path.join(out, f"fps{fps}" + (f"_{secs // 3600}h" if secs != 3600 else ""))
    os.makedirs(d, exist_ok=True)
    tiny = os.path.join(d, "_tiny.mkv")
    tiny_mkv(tiny, fps)
    tiny_b = open(tiny, "rb").read()
    rng = np.random.default_rng(1000 + fps)
    meta = {"fps": fps, "cameras": cams, "seconds": secs, "cams": []}
    for cam in range(cams):
        r, chosen = make_records(cam, fps, secs, rng)
        sk, index = skfr_bytes(r, chosen, fps, cam)
        ix = skix_bytes(index, r.size)
        open(os.path.join(d, f"cam{cam:02d}.skfr"), "wb").write(sk + index)
        only = os.environ.get("SL_ONLY_SKFR") == "1"   # stress sets: only the .skfr (layouts a, c-inside, d)
        if only:
            meta["cams"].append({"cam": cam, "n": int(r.size)}); print(cam, r.size, flush=True); continue
        open(os.path.join(d, f"cam{cam:02d}.skix"), "wb").write(ix)
        open(os.path.join(d, f"cam{cam:02d}.skfc"), "wb").write(skfc_bytes(r, fps))
        mkv = os.path.join(d, f"cam{cam:02d}.mkv")
        open(mkv, "wb").write(tiny_b)
        append_two(mkv, [("skellycam_frames.skfr", "application/x-skellycam-frames", sk + index),
                         ("skellycam_index.skix", "application/x-skellycam-index", ix)])
        meta["cams"].append({"cam": cam, "n": int(r.size), "first": int(chosen[0]), "last": int(chosen[-1]),
                             "skfr_bytes": len(sk) + len(index), "records_bytes": r.size * 64,
                             "index_bytes": len(index), "drops": int((np.diff(r["sfn"].astype(np.int64)) - 1).sum()),
                             "max_offset": int(r["offset"][-1])})
        print(cam, r.size, flush=True)
    json.dump(meta, open(os.path.join(d, "meta.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
