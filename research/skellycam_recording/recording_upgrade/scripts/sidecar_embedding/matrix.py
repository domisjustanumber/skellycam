"""PyAV 19.0.2 header-room matrix for appending a sidecar attachment to a finalised MKV.

Run with the skellycam-phase1 venv (av==19.0.2, FFmpeg 9.0.2):
  python -I matrix.py <outdir> <src_720p.mkv> <src_240p.mkv>
For each variant: write the MKV with PyAV, report the SeekHead (entries, span, slack),
append a sidecar-sized payload with append_attachment.py, then check
packets (pos,size,pts) unchanged, JPEG bytes identical, ffprobe frame count, and the
attachment extracted by ffmpeg is byte-identical.
"""
import fractions, hashlib, json, os, shutil, subprocess, sys, multiprocessing as mp

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import append_attachment as aa  # noqa: E402

import av  # noqa: E402

TB30 = fractions.Fraction(1, 30)
REC = 64  # bytes per sidecar record assumed (prototype is 48; leave room for the offset field and 3 timestamps)


def load_packets(src):
    with av.open(src) as inp:
        ist = inp.streams.video[0]
        return [bytes(p) for p in inp.demux(ist) if p.size], ist.codec_context.width, ist.codec_context.height


def write_mkv(dst, pk, w, h, nrep, tags=False, chapters=False, kill_after=None):
    out = av.open(dst, "w", format="matroska", options={"flush_packets": "1"})
    if tags:
        out.metadata.update({"SKELLYCAM_CAMERA_KEY": "usb-046d-0843-SERIAL1234567890",
                             "SKELLYCAM_ENCODER": "passthrough", "SKELLYCAM_FORMAT": "MJPG 1280x720@30"})
    ost = out.add_stream("mjpeg", rate=30)
    ost.width, ost.height = w, h
    ost.time_base = fractions.Fraction(1, 30)
    ost.codec_context.pix_fmt = "yuvj420p"
    if tags:
        ost.metadata.update({"title": "cam0", "SKELLYCAM_SERIAL": "SERIAL1234567890"})
    if chapters:
        n = len(pk) * nrep
        out.set_chapters([{"id": 1, "start": 0, "end": n // 2, "time_base": fractions.Fraction(1, 30),
                           "metadata": {"title": "first half"}},
                          {"id": 2, "start": n // 2, "end": n, "time_base": fractions.Fraction(1, 30),
                           "metadata": {"title": "second half"}}])
    i = 0
    for _ in range(nrep):
        for data in pk:
            # fixed 1/30: the muxer switches ost.time_base to 1/1000 at the header, so copying it per packet
            # after frame 0 would space frames 1 ms apart (the bug in the first run)
            p = av.Packet(data); p.stream = ost; p.pts = p.dts = i; p.time_base = TB30; p.is_keyframe = True
            out.mux(p); i += 1
            if kill_after is not None and i == kill_after:
                os._exit(1)  # crash: no trailer, unknown-size Segment, SeekHead never filled in
    out.close()
    return i


def remux(src, dst):
    """Crash recovery as row 1.7 plans it: stream-copy the readable packets into a fresh MKV."""
    n = 0
    with av.open(src) as inp:
        ist = inp.streams.video[0]
        out = av.open(dst, "w", format="matroska", options={"flush_packets": "1"})
        ost = out.add_stream_from_template(ist)
        try:
            for p in inp.demux(ist):
                if p.size == 0 or p.pts is None:
                    continue
                p.stream = ost; out.mux(p); n += 1
        except av.error.FFmpegError as e:  # torn tail
            print("  remux stopped at torn tail:", type(e).__name__)
        out.close()
    return n


def seekhead_report(path):
    b = open(path, "rb").read(64 * 1024)
    eid, d, size, _ = aa.read_elem(b, 0)
    eid, seg_data, seg_size, _ = aa.read_elem(b, d + size)
    eid, sh_data, sh_size, _ = aa.read_elem(b, seg_data)
    if eid != aa.ID_SEEKHEAD:
        return dict(seekhead=False, segment_size_known=seg_size is not None)
    names = {0x1549A966: "Info", 0x1654AE6B: "Tracks", 0x1254C367: "Tags", 0x1C53BB6B: "Cues",
             0x1043A770: "Chapters", 0x1941A469: "Attachments"}
    ents = [names.get(i, hex(i)) for i, _ in aa.parse_seekhead(b, sh_data, sh_size)]
    end = sh_data + sh_size
    e2, vd, vsz, _ = aa.read_elem(b, end)
    span_end = vd + vsz if e2 == aa.ID_VOID else end
    return dict(seekhead=True, entries=ents, span=span_end - seg_data, used=end - seg_data,
                slack=span_end - end, segment_size_known=seg_size is not None)


def ffprobe_packets(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pos,size,pts",
                          "-of", "json", p], capture_output=True, text=True, check=True).stdout
    return [(int(x["pos"]), int(x["size"]), int(x["pts"])) for x in json.loads(out)["packets"]]


def check_append(path, outdir, tag):
    n = len(ffprobe_packets(path))
    payload = os.urandom(64 + REC * n)
    app = os.path.join(outdir, tag + "_appended.mkv")
    shutil.copyfile(path, app)
    res = dict(tag=tag, frames=n, before=seekhead_report(path))
    try:
        r = aa.append(app, payload)
    except ValueError as e:
        res["append"] = f"REFUSED: {e}"; return res
    res["append"] = dict(void_pad=r["void_pad"], new_seekhead_len=r["new_seekhead_len"], span=r["seekhead_span"],
                         payload_len=r["payload_len"])
    res["after"] = seekhead_report(app)
    a, b = ffprobe_packets(path), ffprobe_packets(app)
    ob, nb = open(path, "rb").read(), open(app, "rb").read()
    res["packets_identical"] = f"{sum(x == y for x, y in zip(a, b))}/{len(a)} (new count {len(b)})"
    res["jpeg_bytes_identical"] = sum(1 for pos, sz, _ in b if nb[pos + 4:pos + 4 + sz] == ob[pos + 4:pos + 4 + sz]
                                      and nb[pos + 4:pos + 6] == b"\xff\xd8")
    diff = [i for i in range(len(ob)) if ob[i] != nb[i]] if len(ob) < 50_000_000 else None
    if diff is not None:
        res["bytes_changed_in_original"] = f"{len(diff)} in [{min(diff)},{max(diff)}]" if diff else "0"
    cnt = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries",
                          "stream=nb_read_packets", "-of", "csv=p=0", app], capture_output=True, text=True).stdout.strip()
    res["ffprobe_count"] = cnt
    dump = os.path.join(outdir, tag + "_dump.bin")
    if os.path.exists(dump): os.remove(dump)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-dump_attachment:t:0", dump, "-i", app], capture_output=True)
    res["attachment_identical"] = os.path.exists(dump) and hashlib.sha256(open(dump, "rb").read()).digest() == \
        hashlib.sha256(payload).digest()
    return res


def main():
    outdir, src720, src240 = sys.argv[1:4]
    os.makedirs(outdir, exist_ok=True)
    print("av", av.__version__, "libavformat", av.library_versions["libavformat"], "ffmpeg", av.ffmpeg_version_info)
    pk720, w7, h7 = load_packets(src720)
    pk240, w2, h2 = load_packets(src240)
    variants = [
        ("v1_plain_90", pk720, w7, h7, 1, {}),
        ("v2_tags_90", pk720, w7, h7, 1, dict(tags=True)),
        ("v3_tags_chapters_90", pk720, w7, h7, 1, dict(tags=True, chapters=True)),
        ("v4_tags_54000", pk240, w2, h2, 60, dict(tags=True)),           # 30 min @30 fps: big Cues, 8-byte positions
        ("v5_tags_chapters_54000", pk240, w2, h2, 60, dict(tags=True, chapters=True)),
    ]
    results = []
    for tag, pk, w, h, nrep, kw in variants:
        path = os.path.join(outdir, tag + ".mkv")
        if os.path.exists(path): os.remove(path)
        try:
            n = write_mkv(path, pk, w, h, nrep, **kw)
        except Exception as e:  # e.g. set_chapters missing
            results.append(dict(tag=tag, write_error=f"{type(e).__name__}: {e}")); print(tag, "write error", e); continue
        print(tag, "wrote", n, "frames", os.path.getsize(path), "bytes")
        results.append(check_append(path, outdir, tag))
    # crash + remux
    for tag, kw in (("v6_crash_remux", dict(tags=True)),):
        killed = os.path.join(outdir, tag + "_killed.mkv")
        if os.path.exists(killed): os.remove(killed)
        pr = mp.Process(target=write_mkv, args=(killed, pk720, w7, h7, 1), kwargs=dict(kill_after=61, **kw))
        pr.start(); pr.join()
        rep_killed = seekhead_report(killed)
        try:
            aa.append(shutil.copyfile(killed, os.path.join(outdir, tag + "_killed_try.mkv")), b"x" * 100)
            killed_append = "appended?!"
        except ValueError as e:
            killed_append = f"REFUSED: {e}"
        rem = os.path.join(outdir, tag + ".mkv")
        if os.path.exists(rem): os.remove(rem)
        n = remux(killed, rem)
        r = check_append(rem, outdir, tag)
        r.update(killed_exit=pr.exitcode, killed_report=rep_killed, killed_append=killed_append, remuxed_frames=n)
        results.append(r)
    json.dump(results, open(os.path.join(outdir, "matrix.json"), "w"), indent=1)
    for r in results:
        print(json.dumps(r))


if __name__ == "__main__":
    main()
