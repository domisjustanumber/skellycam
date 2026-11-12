"""T-S2: cost of learning each JPEG's offset live (file size after every mux) at 16 x 1080p60.
PyAV 19.0.2 (skellycam-phase1 venv). Usage: python -I stat_cost.py <outdir> <jpeg_source.mkv> [seconds] [reps]

16 writer threads, each pacing 60 fps and muxing real JPEG packets (looped from a source MKV, padded to ~1080p size)
into its own MKV with flush_packets=1, as the row-1.5 writer does. Modes, interleaved per rep:
  none  - mux only
  stat  - mux, then os.stat(path).st_size
  fstat - mux, then os.fstat(fd).st_size on a read-only handle opened on the same file after the header
Per thread: mux latency, size-query latency, total per-frame latency (p50/p99/p99.9/max), late frames
(a frame starts more than one period after its due time), and a check that the derived offset of frame i-1
(size after mux(i) - len(frame i-1)) matches the bytes on disk.
"""
import fractions, json, os, statistics, sys, threading, time

import av
import numpy as np

FPS, CAMS = 60, 16
TB = fractions.Fraction(1, FPS)


def load_packets(src, target_kb=250):
    with av.open(src) as c:
        s = c.streams.video[0]
        pk = [bytes(p) for p in c.demux(s) if p.size]
    out = []
    for d in pk:                                   # pad inside the JPEG after EOI-less trailer: append COM-free zeros
        if len(d) < target_kb * 1024:              # keep SOI..EOI intact, append padding after EOI (decoders ignore it)
            d = d + b"\x00" * (target_kb * 1024 - len(d))
        out.append(d)
    return out


def pct(a, q):
    return float(np.percentile(a, q)) if len(a) else None


def writer(idx, outdir, mode, packets, seconds, t0, res):
    path = os.path.join(outdir, f"{mode}_cam{idx:02d}.mkv")
    if os.path.exists(path):
        os.remove(path)
    out = av.open(path, "w", format="matroska", options={"flush_packets": "1"})
    st = out.add_stream("mjpeg", rate=FPS)
    st.width, st.height, st.time_base = 1920, 1080, TB
    st.codec_context.pix_fmt = "yuvj422p"
    out.start_encoding()
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0)) if mode == "fstat" else None
    n = int(seconds * FPS)
    mux_us, q_us, tot_us, late = [], [], [], 0
    sizes, lens = [], []
    for i in range(n):
        due = t0 + i / FPS
        now = time.perf_counter()
        if now < due:
            time.sleep(due - now)
        elif now - due > 1 / FPS:
            late += 1
        d = packets[(i + idx * 7) % len(packets)]
        p = av.Packet(d); p.stream = st; p.pts = p.dts = i; p.time_base = TB; p.is_keyframe = True
        a = time.perf_counter_ns()
        out.mux(p)
        b = time.perf_counter_ns()
        if mode == "stat":
            sz = os.stat(path).st_size
        elif mode == "fstat":
            sz = os.fstat(fd).st_size
        else:
            sz = None
        c = time.perf_counter_ns()
        mux_us.append((b - a) / 1e3); tot_us.append((c - a) / 1e3)
        if sz is not None:
            q_us.append((c - b) / 1e3); sizes.append(sz)
        lens.append(len(d))
    out.close()
    if fd is not None:
        os.close(fd)
    ok = None
    if sizes:                                       # check derived offsets of frame i-1 on a sample
        blob_check = 0; good = 0
        with open(path, "rb") as f:
            for i in range(1, len(sizes), max(1, len(sizes) // 60)):
                off = sizes[i] - lens[i - 1]
                f.seek(off); head = f.read(4)
                blob_check += 1; good += head[:2] == b"\xff\xd8"
        ok = f"{good}/{blob_check}"
    res[idx] = dict(mux_us=mux_us, q_us=q_us, tot_us=tot_us, late=late, frames=n, offset_check=ok)
    os.remove(path)


def run(outdir, mode, packets, seconds):
    res = {}
    t0 = time.perf_counter() + 0.5
    th = [threading.Thread(target=writer, args=(i, outdir, mode, packets, seconds, t0, res)) for i in range(CAMS)]
    for t in th: t.start()
    for t in th: t.join()
    mux = np.concatenate([r["mux_us"] for r in res.values()])
    tot = np.concatenate([r["tot_us"] for r in res.values()])
    q = np.concatenate([r["q_us"] for r in res.values()]) if mode != "none" else np.array([])
    return dict(mode=mode, frames=int(sum(r["frames"] for r in res.values())),
                late=int(sum(r["late"] for r in res.values())),
                mux_us={k: pct(mux, v) for k, v in (("p50", 50), ("p99", 99), ("p999", 99.9))} | {"max": float(mux.max())},
                query_us=({k: pct(q, v) for k, v in (("p50", 50), ("p99", 99), ("p999", 99.9))} | {"max": float(q.max())}) if len(q) else None,
                total_us={k: pct(tot, v) for k, v in (("p50", 50), ("p99", 99), ("p999", 99.9))} | {"max": float(tot.max())},
                offset_checks=sorted({r["offset_check"] for r in res.values() if r["offset_check"]}))


def main():
    outdir, src = sys.argv[1], sys.argv[2]
    seconds = float(sys.argv[3]) if len(sys.argv) > 3 else 20
    reps = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    os.makedirs(outdir, exist_ok=True)
    packets = load_packets(src)
    meta = dict(av=av.__version__, libavformat=list(av.library_versions["libavformat"]), cams=CAMS, fps=FPS,
                seconds=seconds, reps=reps, packet_bytes_mean=int(statistics.mean(len(p) for p in packets)),
                started=time.strftime("%Y-%m-%dT%H:%M:%S"))
    rows = []
    for r in range(reps):
        for mode in (("none", "stat", "fstat") if r % 2 == 0 else ("fstat", "stat", "none")):
            row = run(outdir, mode, packets, seconds); row["rep"] = r; rows.append(row)
            print(json.dumps(row), flush=True)
    meta["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    json.dump(dict(meta=meta, rows=rows), open(os.path.join(outdir, "stat_cost.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
