""">4 GiB header-room test with PyAV 19.0.2. Usage: python -I big.py <outdir> <src_720p.mkv> <reps>
Writes two files (tags only; tags + chapters added after the header = 6 SeekHead entries), then for each:
SeekHead report with raw SeekPosition widths, ffprobe packet table, streaming SHA-256 of every byte after the
SeekHead+Void span, in-place append, then the same checks again plus ffprobe count and attachment dump."""
import fractions, hashlib, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, HERE)
import append_attachment as aa  # noqa: E402
import matrix  # noqa: E402
import av  # noqa: E402

TB = fractions.Fraction(1, 30)
NAMES = {0x1549A966: "Info", 0x1654AE6B: "Tracks", 0x1254C367: "Tags", 0x1C53BB6B: "Cues",
         0x1043A770: "Chapters", 0x1941A469: "Attachments"}


def write(dst, pk, w, h, reps, late_chapters):
    out = av.open(dst, "w", format="matroska", options={"flush_packets": "1"})
    out.metadata.update({"SKELLYCAM_CAMERA_KEY": "usb-046d-0843-SERIAL1234567890", "SKELLYCAM_ENCODER": "passthrough"})
    s = out.add_stream("mjpeg", rate=30); s.width, s.height = w, h; s.time_base = TB
    s.codec_context.pix_fmt = "yuvj420p"; s.metadata["title"] = "cam0"
    i = 0
    for _ in range(reps):
        for d in pk:
            p = av.Packet(d); p.stream = s; p.pts = p.dts = i; p.time_base = TB; p.is_keyframe = True
            out.mux(p); i += 1
    if late_chapters:  # chapters first set after the header -> written at the trailer with a second Tags element
        out.set_chapters([{"id": 1, "start": 0, "end": i, "time_base": TB,
                           "metadata": {"title": "all", "COMMENT": "added after header"}}])
    out.close()
    return i


def seek_entries(path):
    b = open(path, "rb").read(65536)
    eid, d, size, _ = aa.read_elem(b, 0)
    seg_pos = d + size
    eid, seg_data, seg_size, szlen = aa.read_elem(b, seg_pos)
    eid, sh_data, sh_size, _ = aa.read_elem(b, seg_data)
    ents, r = [], sh_data
    while r < sh_data + sh_size:
        e2, d2, s2, _ = aa.read_elem(b, r)
        if e2 == aa.ID_SEEK:
            s = d2; sid = spos = None; w = None
            while s < d2 + s2:
                e3, d3, s3, _ = aa.read_elem(b, s)
                if e3 == aa.ID_SEEKID: sid = int.from_bytes(b[d3:d3 + s3], "big")
                if e3 == aa.ID_SEEKPOS: spos = int.from_bytes(b[d3:d3 + s3], "big"); w = s3
                s = d3 + s3
            ents.append(dict(el=NAMES.get(sid, hex(sid)), abs_pos=seg_data + spos, pos_bytes=w, entry_bytes=d2 + s2 - r))
        r = d2 + s2
    end = sh_data + sh_size
    e2, vd, vsz, _ = aa.read_elem(b, end)
    span_end = vd + vsz if e2 == aa.ID_VOID else end
    return dict(entries=ents, span=span_end - seg_data, used=end - seg_data, slack=span_end - end,
                span_end_abs=span_end, segment_size=seg_size)


def sha_from(path, start):
    h = hashlib.sha256(); n = 0
    with open(path, "rb") as f:
        f.seek(start)
        while True:
            c = f.read(16 << 20)
            if not c: break
            h.update(c); n += len(c)
    return h.hexdigest(), n


def count(path):
    return subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries",
                           "stream=nb_read_packets", "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip()


def main():
    outdir, src, reps = sys.argv[1], sys.argv[2], int(sys.argv[3])
    os.makedirs(outdir, exist_ok=True)
    print("av", av.__version__, av.library_versions["libavformat"])
    pk, w, h = matrix.load_packets(src)
    results = []
    for tag, late in (("big_tags", False), ("big_late_chapters", True)):
        path = os.path.join(outdir, tag + ".mkv")
        if os.path.exists(path): os.remove(path)
        t = time.perf_counter(); n = write(path, pk, w, h, reps, late); tw = time.perf_counter() - t
        size0 = os.path.getsize(path)
        before = seek_entries(path)
        pk0 = matrix.ffprobe_packets(path)
        start = before["span_end_abs"]
        sha0, nb0 = sha_from(path, start)
        payload = os.urandom(64 + 64 * n)
        open(os.path.join(outdir, tag + "_payload.bin"), "wb").write(payload)
        t = time.perf_counter(); r = aa.append(path, payload); ta = time.perf_counter() - t
        after = seek_entries(path)
        pk1 = matrix.ffprobe_packets(path)
        sha1, nb1 = sha_from(path, start)
        with open(path, "rb") as f:   # the original body must be a prefix of the new body
            hh = hashlib.sha256(); left = nb0; f.seek(start)
            while left:
                c = f.read(min(left, 16 << 20)); hh.update(c); left -= len(c)
        dump = os.path.join(outdir, tag + "_dump.bin")
        if os.path.exists(dump): os.remove(dump)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-dump_attachment:t:0", dump, "-i", path], capture_output=True)
        res = dict(tag=tag, frames=n, size_before=size0, over_4GiB=size0 > 2**32, write_s=round(tw, 1),
                   append_ms=round(ta * 1000, 1), before=before, append=r, after=after,
                   body_after_header_unchanged=hh.hexdigest() == sha0,
                   packets_identical=f"{sum(x == y for x, y in zip(pk0, pk1))}/{len(pk0)} (after {len(pk1)})",
                   packets_past_4GiB=sum(1 for p in pk1 if p[0] > 2**32), ffprobe_count=count(path),
                   attachment_identical=os.path.exists(dump) and open(dump, "rb").read() == payload,
                   filedata_abs=r["filedata_abs"])
        results.append(res); print(json.dumps(res))
    json.dump(results, open(os.path.join(outdir, "big.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
