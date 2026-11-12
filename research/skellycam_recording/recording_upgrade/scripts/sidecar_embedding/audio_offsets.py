"""Audio vs sidecar offsets, PyAV 19.0.2 (run with the skellycam-phase1 venv).
Usage: python -I audio_offsets.py <outdir> <src_240p.mkv> <reps>

S4  Video + audio muxed in one pass (the skellysync Design A "Au2" shape, or skellycam muxing audio live):
    does "after mux(video i) the file ends at frame i-1" still hold? Audio = PCM s16le 48 kHz mono and FLAC,
    1600 samples per video frame, encoded and muxed in step with the video.
S5  Rebuild every JPEG offset from a finished file:
    (a) EBML walk that reads only element headers (Segment > Cluster > SimpleBlock), skipping payloads;
    (b) PyAV demux of the video stream (packet.pos + 4).
    Both are checked against the JPEG bytes, then timed (warm cache).
S6  Remux to add audio after the fact (today's skellysync ReattachAudio / skellycam remuxer shape):
    how many video offsets survive, and does the Segment UID change?
"""
import fractions, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import append_attachment as aa  # noqa: E402
import matrix  # noqa: E402
import spec_checks  # noqa: E402
import av  # noqa: E402
import numpy as np  # noqa: E402

TB = fractions.Fraction(1, 30)
ID_CLUSTER, ID_SIMPLEBLOCK, ID_BLOCKGROUP, ID_BLOCK = 0x1F43B675, 0xA3, 0xA0, 0xA1


def write_av(path, pk, w, h, reps, acodec):
    out = av.open(path, "w", format="matroska", options={"flush_packets": "1"})
    vs = out.add_stream("mjpeg", rate=30); vs.width, vs.height = w, h; vs.time_base = TB
    vs.codec_context.pix_fmt = "yuvj420p"
    as_ = None
    if acodec:
        as_ = out.add_stream(acodec, rate=48000); as_.layout = "mono"
        as_.format = "s16"
    sizes, jpegs, i = [], [], 0
    t = np.arange(1600)
    for _ in range(reps):
        for d in pk:
            if as_ is not None:
                samples = (3000 * np.sin(2 * np.pi * 440 * (t + i * 1600) / 48000)).astype(np.int16).reshape(1, -1)
                af = av.AudioFrame.from_ndarray(samples, format="s16", layout="mono"); af.sample_rate = 48000
                af.pts = i * 1600
                for ap in as_.encode(af):
                    out.mux(ap)
            p = av.Packet(d); p.stream = vs; p.pts = p.dts = i; p.time_base = TB; p.is_keyframe = True
            out.mux(p); jpegs.append(d); i += 1
            sizes.append(os.stat(path).st_size)
    if as_ is not None:
        for ap in as_.encode(None):
            out.mux(ap)
    out.close()
    return sizes, jpegs


def true_offsets(path, jpegs):
    blob = open(path, "rb").read()
    tab = [x for x in matrix.ffprobe_packets(path)]
    offs = [pos + 4 for pos, sz, _ in tab]
    ok = all(blob[o:o + len(jpegs[k])] == jpegs[k] for k, o in enumerate(offs))
    return offs, ok


def ebml_walk_offsets(path, video_track=1):
    """Read only element headers; return (offset, size) of each video frame payload in file order."""
    res = []
    with open(path, "rb") as f:
        hdr = f.read(64)
        eid, d, size, _ = aa.read_elem(hdr, 0)
        f.seek(d + size); h = f.read(16)
        eid, sd, ssize, _ = aa.read_elem(h, 0)
        pos = d + size + sd
        end = pos + ssize if ssize is not None else os.fstat(f.fileno()).st_size
        while pos < end:
            f.seek(pos); h = f.read(16)
            if len(h) < 2: break
            eid, dd, s, _ = aa.read_elem(h, 0)
            if eid == ID_CLUSTER:
                cpos = pos + dd
                cend = cpos + s if s is not None else end
                while cpos < cend:
                    f.seek(cpos); h = f.read(16)
                    if len(h) < 2: break
                    e2, d2, s2, _ = aa.read_elem(h, 0)
                    if e2 == ID_CLUSTER: break  # unknown-size cluster ended
                    if e2 in (ID_SIMPLEBLOCK, ID_BLOCK):
                        tn, n, _ = aa.read_vint(h, d2)
                        flags = h[d2 + n + 2]
                        if tn == video_track and not (flags & 0x06):  # no lacing
                            hdr_len = n + 3
                            res.append((cpos + d2 + hdr_len, s2 - hdr_len))
                    elif e2 == ID_BLOCKGROUP:  # descend one level for Block
                        g = cpos + d2
                        while g < cpos + d2 + s2:
                            f.seek(g); hh = f.read(16)
                            e3, d3, s3, _ = aa.read_elem(hh, 0)
                            if e3 == ID_BLOCK:
                                tn, n, _ = aa.read_vint(hh, d3)
                                if tn == video_track:
                                    res.append((g + d3 + n + 3, s3 - n - 3))
                            g += d3 + s3
                    cpos += d2 + s2
                pos = cend
            else:
                if s is None: break
                pos += dd + s
    return res


def pyav_offsets(path):
    with av.open(path) as c:
        vs = c.streams.video[0]
        return [(p.pos + 4, p.size) for p in c.demux(vs) if p.size]


def remux_add_audio(src, dst):
    with av.open(src) as inp:
        out = av.open(dst, "w", format="matroska")
        vo = out.add_stream_from_template(inp.streams.video[0])
        ao = out.add_stream("flac", rate=48000); ao.layout = "mono"; ao.format = "s16"
        n = inp.streams.video[0].frames or 0
        for k, p in enumerate(inp.demux(inp.streams.video[0])):
            if not p.size: continue
            p.stream = vo; out.mux(p)
            af = av.AudioFrame.from_ndarray(np.zeros((1, 1600), np.int16), format="s16", layout="mono")
            af.sample_rate = 48000; af.pts = k * 1600
            for ap in ao.encode(af): out.mux(ap)
        for ap in ao.encode(None): out.mux(ap)
        out.close()


def main():
    outdir, src240, reps = sys.argv[1], sys.argv[2], int(sys.argv[3])
    os.makedirs(outdir, exist_ok=True)
    pk, w, h = matrix.load_packets(src240)
    res = dict(av=av.__version__, S4=[], S5=[], S6=None)
    for acodec in (None, "pcm_s16le", "flac"):
        path = os.path.join(outdir, f"s4_{acodec or 'noaudio'}.mkv")
        if os.path.exists(path): os.remove(path)
        sizes, jpegs = write_av(path, pk, w, h, 2, acodec)
        offs, ok = true_offsets(path, jpegs)
        n = len(jpegs)
        ends_prev = sum(1 for i in range(1, n) if sizes[i] == offs[i - 1] + len(jpegs[i - 1]))
        ends_this = sum(1 for i in range(n) if sizes[i] == offs[i] + len(jpegs[i]))
        res["S4"].append(dict(audio=acodec or "none", frames=n, offsets_model_ok=ok,
                              file_ends_at_previous_frame=f"{ends_prev}/{n - 1}",
                              file_ends_at_frame_just_muxed=f"{ends_this}/{n}"))
    # S5 on a long file with audio and one without
    for acodec in (None, "flac"):
        path = os.path.join(outdir, f"s5_{acodec or 'noaudio'}.mkv")
        if os.path.exists(path): os.remove(path)
        sizes, jpegs = write_av(path, pk, w, h, reps, acodec)
        offs, ok = true_offsets(path, jpegs)
        truth = [(o, len(j)) for o, j in zip(offs, jpegs)]
        ebml_walk_offsets(path); pyav_offsets(path)  # warm
        t = time.perf_counter(); a = ebml_walk_offsets(path); ta = time.perf_counter() - t
        t = time.perf_counter(); b = pyav_offsets(path); tb = time.perf_counter() - t
        res["S5"].append(dict(audio=acodec or "none", frames=len(jpegs), bytes=os.path.getsize(path),
                              ebml_walk=dict(match=a == truth, ms=round(ta * 1000, 1)),
                              pyav_demux=dict(match=b == truth, ms=round(tb * 1000, 1))))
    # S6 remux to add audio afterwards
    src = os.path.join(outdir, "s4_noaudio.mkv"); dst = os.path.join(outdir, "s6_remux_audio.mkv")
    if os.path.exists(dst): os.remove(dst)
    remux_add_audio(src, dst)
    a0 = ebml_walk_offsets(src); a1 = ebml_walk_offsets(dst)
    res["S6"] = dict(frames=len(a0), offsets_unchanged=sum(1 for x, y in zip(a0, a1) if x == y),
                     sizes_unchanged=sum(1 for x, y in zip(a0, a1) if x[1] == y[1]),
                     uid_before=spec_checks.segment_uid(src), uid_after=spec_checks.segment_uid(dst))
    json.dump(res, open(os.path.join(outdir, "audio_offsets.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
