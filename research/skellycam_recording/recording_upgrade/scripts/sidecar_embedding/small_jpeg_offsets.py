"""Live offsets with small JPEGs (skellyfileformat spec re-review E3). PyAV 19.0.2; run with the skellycam-phase1 venv.
Usage: python -I small_jpeg_offsets.py <outdir>

Question: FFmpeg's Matroska muxer buffers a Cluster in memory. Does the one-behind rule of spec_checks.py S1
(after mux(i) the file ends at frame i-1, so offset[i-1] = st_size - len(jpeg[i-1])) still hold when the JPEGs are
4 KiB or smaller? S1 measured 720p and 240p frames only. This reuses spec_checks.s1_s2 unchanged and feeds it
synthetic JPEGs of chosen sizes: tiny (~0.5 KiB), small (~2-4 KiB), mixed small and large, and a large control.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import av  # noqa: E402
import numpy as np  # noqa: E402
import spec_checks  # noqa: E402


def jpegs(w, h, n, noise, seed=1):
    rng = np.random.default_rng(seed)
    cc = av.CodecContext.create("mjpeg", "w")
    cc.width, cc.height, cc.pix_fmt = w, h, "yuvj420p"
    cc.time_base = spec_checks.TB
    cc.options = {"qscale": "4"}
    cc.open()
    out = []
    for i in range(n):
        img = np.full((h, w, 3), (i * 7) % 256, np.uint8)
        if noise:
            img = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
        fr = av.VideoFrame.from_ndarray(img, format="rgb24").reformat(format="yuvj420p")
        fr.pts = i
        out += [bytes(p) for p in cc.encode(fr)]
    out += [bytes(p) for p in cc.encode(None)]
    return out


def s1_opts(outdir, pk, w, h, opts, tag):
    """spec_checks.s1_s2 with extra muxer options (flush_packets=1 always)."""
    src = open(spec_checks.__file__, encoding="utf-8").read()
    fn = src[src.index("def s1_s2"):src.index("def frame_hashes_cv2")]
    fn = fn.replace('options={"flush_packets": str(flush)}', 'options={"flush_packets": str(flush), **OPTS}')
    fn = fn.replace('f"s1_fp{flush}.mkv"', 'f"s1_{TAG}.mkv"')
    ns = dict(vars(spec_checks)); ns.update(OPTS=opts, TAG=tag)
    exec(fn, ns)
    return ns["s1_s2"](outdir, pk, w, h, 1)


def main():
    outdir = sys.argv[1]
    os.makedirs(outdir, exist_ok=True)
    cases = {}
    tiny = jpegs(32, 24, 300, noise=False)
    small = jpegs(96, 72, 300, noise=True)
    big = jpegs(640, 360, 60, noise=True)
    mixed = [small[i] if i % 10 else big[i % len(big)] for i in range(300)]
    for name, pk in (("tiny", tiny), ("small", small), ("mixed", mixed), ("large_control", big)):
        sizes = sorted(len(p) for p in pk)
        r = spec_checks.s1_s2(outdir, pk, *(32, 24) if name == "tiny" else (96, 72) if name in ("small", "mixed") else (640, 360), 1)
        r.update(jpeg_bytes_min=sizes[0], jpeg_bytes_median=sizes[len(sizes) // 2], jpeg_bytes_max=sizes[-1])
        cases[name] = r
        print(name, json.dumps(r), flush=True)
    for opts in ({"cluster_size_limit": "1"}, {"cluster_time_limit": "0"}, {"cluster_size_limit": "1", "cluster_time_limit": "1"}):
        tag = "_".join(f"{k}{v}" for k, v in opts.items())
        for name, pk, wh in (("tiny", tiny, (32, 24)), ("small", small, (96, 72)), ("mixed", mixed, (96, 72))):
            r = s1_opts(outdir, pk, *wh, opts, f"{name}_{tag}")
            cases[f"{name}+{tag}"] = r
            print(name, tag, r["offset_prev_derived_from_size"], r["other"], flush=True)
    res = dict(test="small_jpeg_offsets", pyav=av.__version__, ffmpeg=av.ffmpeg_version_info, cases=cases)
    json.dump(res, open(os.path.join(outdir, "small_jpeg_offsets.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
