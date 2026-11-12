"""Sidecar-spec checks with PyAV 19.0.2 (run with the skellycam-phase1 venv).
Usage: python -I spec_checks.py <outdir> <src_720p.mkv> <src_240p.mkv>

S1  Offsets during recording: after each mux(), stat the file. Does the file end exactly at a frame's JPEG
    (and which frame: the one just muxed, or the one before)? flush_packets=1 vs 0.
S2  Segment UID: readable from the file right after the header is written? Same at close?
S3  OpenCV 5 on an appended file: frame count, POS_FRAMES seeks checked by pixel hash, vs the original.
"""
import fractions, hashlib, json, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, HERE)
import append_attachment as aa  # noqa: E402
import matrix  # noqa: E402
import av  # noqa: E402
import cv2  # noqa: E402

TB = fractions.Fraction(1, 30)
ID_INFO, ID_SEGUID = 0x1549A966, 0x73A4


def segment_uid(path):
    b = open(path, "rb").read(65536)
    if len(b) < 64:
        return f"<file has {len(b)} bytes>"
    eid, d, size, _ = aa.read_elem(b, 0)
    eid, seg_data, _, _ = aa.read_elem(b, d + size)
    p = seg_data
    while p < len(b) - 16:
        e, dd, s, _ = aa.read_elem(b, p)
        if e == ID_INFO:
            q = dd
            while q < dd + s:
                e2, d2, s2, _ = aa.read_elem(b, q)
                if e2 == ID_SEGUID:
                    return b[d2:d2 + s2].hex()
                q = d2 + s2
            return None
        if s is None:
            return None
        p = dd + s
    return None


def s1_s2(outdir, pk, w, h, flush):
    path = os.path.join(outdir, f"s1_fp{flush}.mkv")
    if os.path.exists(path): os.remove(path)
    out = av.open(path, "w", format="matroska", options={"flush_packets": str(flush)})
    s = out.add_stream("mjpeg", rate=30); s.width, s.height = w, h; s.time_base = TB
    s.codec_context.pix_fmt = "yuvj420p"
    out.start_encoding()
    uid_after_header = segment_uid(path)
    sizes = []
    for i, d in enumerate(pk):
        p = av.Packet(d); p.stream = s; p.pts = p.dts = i; p.time_base = TB; p.is_keyframe = True
        out.mux(p)
        sizes.append(os.stat(path).st_size)
    out.close()
    uid_closed = segment_uid(path)
    blob = open(path, "rb").read()
    # true JPEG offsets from the final file
    pk_tab = matrix.ffprobe_packets(path)
    true_off = [pos + 4 for pos, sz, _ in pk_tab]   # SimpleBlock header: track vint(1) + int16 timecode + flags
    assert all(blob[o:o + len(pk[i])] == pk[i] for i, o in enumerate(true_off)), "offset model wrong"
    # after mux(i): does the file end exactly at the end of frame i, or of frame i-1?
    ends_at_this = sum(1 for i, sz in enumerate(sizes) if sz == true_off[i] + len(pk[i]))
    ends_at_prev = sum(1 for i, sz in enumerate(sizes) if i > 0 and sz == true_off[i - 1] + len(pk[i - 1]))
    other = len(sizes) - ends_at_this - ends_at_prev
    # can offset of frame i-1 be derived as size_after_mux(i) - len(pk[i-1])?
    derived_ok = sum(1 for i in range(1, len(sizes)) if sizes[i] - len(pk[i - 1]) == true_off[i - 1])
    growth_steps = len(set(sizes))
    return dict(flush_packets=flush, frames=len(pk), uid_after_header=uid_after_header, uid_at_close=uid_closed,
                uid_same=uid_after_header is not None and uid_after_header == uid_closed,
                file_ends_at_frame_just_muxed=ends_at_this, file_ends_at_previous_frame=ends_at_prev,
                other=other, distinct_sizes=growth_steps,
                offset_prev_derived_from_size=f"{derived_ok}/{len(sizes) - 1}")


def frame_hashes_cv2(path, targets):
    cap = cv2.VideoCapture(path, cv2.CAP_FFMPEG)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    seq = []
    while True:
        ok, fr = cap.read()
        if not ok: break
        seq.append(hashlib.sha1(fr.tobytes()).hexdigest())
    hits = 0
    for t in targets:
        cap.set(cv2.CAP_PROP_POS_FRAMES, t)
        ok, fr = cap.read()
        if ok and t < len(seq) and hashlib.sha1(fr.tobytes()).hexdigest() == seq[t]: hits += 1
    cap.release()
    return n, len(seq), hits, seq


def s3(outdir, pk, w, h, reps):
    path = os.path.join(outdir, f"s3_{reps}.mkv")
    if os.path.exists(path): os.remove(path)
    out = av.open(path, "w", format="matroska", options={"flush_packets": "1"})
    s = out.add_stream("mjpeg", rate=30); s.width, s.height = w, h; s.time_base = TB
    s.codec_context.pix_fmt = "yuvj420p"
    i = 0
    for _ in range(reps):
        for d in pk:
            p = av.Packet(d); p.stream = s; p.pts = p.dts = i; p.time_base = TB; p.is_keyframe = True
            out.mux(p); i += 1
    out.close()
    app = path.replace(".mkv", "_appended.mkv"); shutil.copyfile(path, app)
    aa.append(app, os.urandom(64 + 64 * i))
    n = i
    targets = [0, 1, n // 7, n // 3, n // 2, n - 2, n - 1, 5, n // 5 + 3, 2 * n // 3, 17]
    a = frame_hashes_cv2(path, targets); b = frame_hashes_cv2(app, targets)
    return dict(frames=n, cv2=cv2.__version__,
                orig=dict(count_prop=a[0], read=a[1], seeks=f"{a[2]}/{len(targets)}"),
                appended=dict(count_prop=b[0], read=b[1], seeks=f"{b[2]}/{len(targets)}"),
                decoded_frames_identical=a[3] == b[3])


def main():
    outdir, src720, src240 = sys.argv[1:4]
    os.makedirs(outdir, exist_ok=True)
    print("av", av.__version__, av.library_versions["libavformat"], "cv2", cv2.__version__)
    pk7, w7, h7 = matrix.load_packets(src720)
    pk2, w2, h2 = matrix.load_packets(src240)
    res = dict(S1_S2=[s1_s2(outdir, pk7, w7, h7, 1), s1_s2(outdir, pk7, w7, h7, 0),
                      s1_s2(outdir, pk2 * 3, w2, h2, 1)],
               S3=[s3(outdir, pk7, w7, h7, 1), s3(outdir, pk2, w2, h2, 20)])
    json.dump(res, open(os.path.join(outdir, "spec_checks.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
