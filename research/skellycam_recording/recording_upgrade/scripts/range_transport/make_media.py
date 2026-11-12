"""T-S5 test media. PyAV 19.0.2 (skellycam-phase1 venv, run with python -I).
Usage: python -I make_media.py <outdir> [--big]

Writes into <outdir>:
  pattern.bin            256 MiB; the uint32 LE word at byte offset o (o % 4 == 0) is o // 4. Any aligned range
                         can be checked without a reference copy.
  rec/rangetest/cam0.mkv JPEG-in-MKV, 1280x720, 300 frames (~150 KB each), with a 64 B/frame sidecar appended as a
                         Matroska attachment (sidecar_embedding/append_attachment.py). For the locator and for
                         skellycam's playback route as it is today.
  rec/rangetest/h264.mp4 H.264 MP4 (libx264), so the route as it is today serves it without transcoding.
  big.mkv (--big)        ~4.7 GB JPEG-in-MKV with the sidecar appended past 4 GiB.
  media.json             sizes, SHA-256 of each embedded payload, and SHA-256 of fixed ranges past 4 GiB.
"""
import fractions, hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "sidecar_embedding"))
import append_attachment as aa  # noqa: E402
import av  # noqa: E402
import numpy as np  # noqa: E402

TB = fractions.Fraction(1, 30)
W, H = 1280, 720


def jpeg_packets(n_distinct=30, q=4):
    """Encode n_distinct noisy 720p frames to JPEG (~150 KB each at qscale q)."""
    enc = av.CodecContext.create("mjpeg", "w")
    enc.width, enc.height, enc.pix_fmt = W, H, "yuvj420p"
    enc.time_base = TB
    enc.options = {"qscale": str(q)}
    enc.flags |= av.codec.context.Flags.qscale
    enc.qscale = q
    rng = np.random.default_rng(5)
    yy, xx = np.mgrid[0:H, 0:W]
    out = []
    for i in range(n_distinct):
        base = ((xx * (1 + i % 5) + yy * 2 + i * 13) % 256).astype(np.int16)
        img = np.clip(base[..., None] + rng.normal(0, 5, (H, W, 3)), 0, 255).astype(np.uint8)
        fr = av.VideoFrame.from_ndarray(img, format="rgb24").reformat(format="yuvj420p")
        fr.pts = i
        for p in enc.encode(fr):
            out.append(bytes(p))
    for p in enc.encode(None):
        out.append(bytes(p))
    return out


def write_mkv(path, pk, n_frames):
    out = av.open(path, "w", format="matroska", options={"flush_packets": "1"})
    s = out.add_stream("mjpeg", rate=30)
    s.width, s.height = W, H
    s.time_base = TB
    s.codec_context.pix_fmt = "yuvj420p"
    for i in range(n_frames):
        p = av.Packet(pk[i % len(pk)]); p.stream = s; p.pts = p.dts = i; p.time_base = TB; p.is_keyframe = True
        out.mux(p)
    out.close()


def write_h264(path, n_frames=300):
    out = av.open(path, "w", format="mp4")
    s = out.add_stream("libx264", rate=30)
    s.width, s.height, s.pix_fmt = W, H, "yuv420p"
    s.options = {"preset": "ultrafast", "crf": "18"}
    rng = np.random.default_rng(9)
    for i in range(n_frames):
        img = rng.integers(0, 255, (H, W, 3), dtype=np.uint8) if i % 30 == 0 else img
        fr = av.VideoFrame.from_ndarray(np.roll(img, i, axis=1), format="rgb24")
        for p in s.encode(fr):
            out.mux(p)
    for p in s.encode(None):
        out.mux(p)
    out.close()


def sha_range(path, off, n):
    with open(path, "rb") as f:
        f.seek(off)
        return hashlib.sha256(f.read(n)).hexdigest()


def main():
    outdir = sys.argv[1]
    big = "--big" in sys.argv
    rec = os.path.join(outdir, "rec", "rangetest")
    os.makedirs(rec, exist_ok=True)
    meta = {"av": av.__version__}
    pat = os.path.join(outdir, "pattern.bin")
    if not os.path.exists(pat) or os.path.getsize(pat) != 256 << 20:
        np.arange((256 << 20) // 4, dtype="<u4").tofile(pat)
    meta["pattern"] = {"path": pat, "size": os.path.getsize(pat)}
    pk = jpeg_packets()
    meta["jpeg_sizes"] = [min(map(len, pk)), int(np.median(list(map(len, pk)))), max(map(len, pk))]
    cam0 = os.path.join(rec, "cam0.mkv")
    write_mkv(cam0, pk, 300)
    payload = hashlib.sha256(b"cam0").digest() * 2 * 300 + b"\0" * 64   # 64 B/frame + 64 B header
    r = aa.append(cam0, payload)
    meta["cam0"] = {"path": cam0, "size": os.path.getsize(cam0), "payload_sha256": hashlib.sha256(payload).hexdigest(),
                    "payload_len": len(payload), "filedata_abs": r.get("filedata_abs")}
    h264 = os.path.join(rec, "h264.mp4")
    write_h264(h264)
    meta["h264"] = {"path": h264, "size": os.path.getsize(h264)}
    if big:
        bp = os.path.join(outdir, "big.mkv")
        n = (4_700_000_000 // meta["jpeg_sizes"][1]) + 1
        write_mkv(bp, pk, n)
        bpay = os.urandom(64 + 64 * n)
        r = aa.append(bp, bpay)
        size = os.path.getsize(bp)
        checks = []
        for off, ln in ((4_294_967_296 - 8, 16), (4_500_000_000, 153_600), (size - 16, 16)):
            checks.append({"off": off, "len": ln, "sha256": sha_range(bp, off, ln)})
        meta["big"] = {"path": bp, "size": size, "frames": n, "payload_sha256": hashlib.sha256(bpay).hexdigest(),
                       "payload_len": len(bpay), "filedata_abs": r.get("filedata_abs"), "range_sha256": checks}
    json.dump(meta, open(os.path.join(outdir, "media.json"), "w"), indent=1)
    print(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main()
