# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "scipy==1.16.2", "simplejpeg==1.9.0",
#                 "nvidia-nvimgcodec-cu12[nvjpeg]==0.10.0.9", "psutil==7.2.2"]
# ///
"""BENCHMARK (timing, 23:00 queue): single-stream intra encode at MATCHED QUALITY, JPEG vs H.264 intra vs HEVC intra.

Paths and settings: results/intra_compare/matched_settings.json (target A by default; --target B = PSNR-Y 45 dB).
Sources, ranges and the per-frame work inside the timed loop: benchpaths.py docstring.
Per (path, size, source): 1 warm-up rep (recorded, excluded from medians) + --reps timed reps. Each rep opens a fresh
encoder (+ decoder for MJPEG sources), pushes 10 untimed frames, then --frames timed frames, unpaced, one thread,
packets discarded (bytes counted, no file I/O); a rep runs at least --frames frames AND --min-seconds seconds
(so the 1 s typeperf GPU sampler gets samples). Per rep: fps, process CPU s (psutil user+system, all threads incl.
driver threads), cpu_ms_per_frame, cpu_cores, bytes_per_frame, nvidia-smi samples and GPU Engine utilisation of
this process per adapter (typeperf; Intel iGPU included). After the reps an untimed quality check
(benchpaths.quality_check) reports the PSNR-Y / SSIM-Y this pipeline actually produced.
Background load is recorded by the queue runner before the item (scripts/bench_runner/run_queue.py).

Run from the repo root on a QUIET machine (one bench at a time):
  uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_compare/bench_matched_stream.py \
      --paths all --sizes 720p,1080p --sources nv12,yuy2,mjpeg_cpu,mjpeg_qsv,rgb --frames 300 --reps 3 --label A
  --skip-qsv  drop every path/source that needs the Intel iGPU.   --smoke  tiny run (numbers meaningless).
Writes results/intra_compare/bench/matched_stream_<label>_<UTC>.json (or --outdir).
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).parent))
import benchpaths as B  # noqa: E402
import iclib  # noqa: E402


def one_rep(prep: B.Prepared, e: dict, n: int, min_s: float = 0.0, keep: list | None = None) -> dict:
    """One rep; returns the record plus perf_counter window (_t0, _t1) for the cell-level GPU sampler."""
    rec: dict = {}
    try:
        t = time.perf_counter()
        enc = B.Encoder(prep.path, prep.w, prep.h, e)
        feed = B.Feed(prep)
        rec["open_s"] = round(time.perf_counter() - t, 4)
        if keep is not None:  # keep the warm-up encoder/decoder alive: its GPU devices make this process's GPU
            keep.append((enc, feed))  # Engine counter instances exist when the cell's typeperf sampler starts
        for _ in range(10):  # untimed warm-up frames
            enc.encode(feed.next())
        proc = psutil.Process()
        nbytes = npk = 0
        if True:
            c0 = proc.cpu_times()
            t0 = time.perf_counter()
            i = 0
            while i < n or time.perf_counter() - t0 < min_s:  # at least n frames and at least min_s seconds
                for d in enc.encode(feed.next()):
                    nbytes += len(d)
                    npk += 1
                i += 1
            n = i
            for d in enc.flush():
                nbytes += len(d)
                npk += 1
            wall = time.perf_counter() - t0
            c1 = proc.cpu_times()
        cpu = (c1.user - c0.user) + (c1.system - c0.system)
        rec.update(ok=True, frames=n, wall_s=round(wall, 4), fps=round(n / wall, 2), cpu_s=round(cpu, 4),
                   cpu_ms_per_frame=round(1000 * cpu / n, 3), cpu_cores=round(cpu / wall, 3),
                   bytes_per_frame=round(nbytes / max(npk, 1)), packets=npk, _t0=t0, _t1=t0 + wall)
    except Exception as ex:  # noqa: BLE001
        rec.update(ok=False, error=f"{type(ex).__name__}: {ex}"[:300])
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", default="all")
    ap.add_argument("--sizes", default="720p,1080p")
    ap.add_argument("--sources", default="nv12,yuy2,mjpeg_cpu,mjpeg_qsv,rgb")
    ap.add_argument("--target", default="A", choices=["A", "B"])
    ap.add_argument("--frames", type=int, default=300)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--min-seconds", type=float, default=3.0, help="each timed rep runs at least this long")
    ap.add_argument("--qcheck-frames", type=int, default=4)
    ap.add_argument("--skip-qsv", action="store_true")
    ap.add_argument("--label", default="")
    ap.add_argument("--outdir", default="")
    ap.add_argument("--smoke", action="store_true", help="frames 8, reps 1, qcheck 1 (numbers meaningless)")
    a = ap.parse_args()
    if a.smoke:
        a.frames, a.reps, a.qcheck_frames, a.min_seconds = 8, 1, 1, 0.0
    paths = B.ALL_PATHS if a.paths == "all" else a.paths.split(",")
    matched = B.load_matched()
    try:
        adapters = B.dxgi_adapters()
    except Exception as ex:  # noqa: BLE001
        adapters = {"error": repr(ex)}
    out = {"bench": "matched_stream", "args": vars(a), "matched_settings": str(B.MATCHED), "target": a.target,
           "system_before": B.snapshot(), "dxgi_adapters": adapters, "runs": [], "summary": [], "skipped": []}
    srcs_cache: dict[str, list] = {}
    for size in a.sizes.split(","):
        for source in a.sources.split(","):
            ic = B.input_class(source, size)
            for path in paths:
                ok, why = B.compatible(path, source)
                if not ok:
                    continue
                if a.skip_qsv and B.is_qsv(path, source):
                    out["skipped"].append({"path": path, "source": source, "size": size, "why": "--skip-qsv"})
                    continue
                if ic not in srcs_cache:
                    srcs_cache[ic] = iclib.load_input(ic)
                e = B.entry(matched, path, ic, a.target)
                prep = B.Prepared(path, source, size, srcs_cache[ic])
                keep: list = []
                warm = one_rep(prep, e, a.frames, a.min_seconds, keep)  # warm-up rep: no GPU sampling
                warm["warmup"] = True
                warm.pop("_t0", None), warm.pop("_t1", None)
                with B.GpuSampler() as gs:  # one sampler per cell, started after warm-up; sliced per rep below
                    reps = [one_rep(prep, e, a.frames, a.min_seconds) for _ in range(a.reps)]
                del keep
                for r in reps:
                    if "_t0" in r:
                        r["gpu"] = gs.summary(adapters, r.pop("_t0"), r.pop("_t1"))
                qc = B.quality_check(prep, e, a.qcheck_frames)
                base = {"path": path, "encoder": e["encoder"], "size": size, "source": source, "input_class": ic,
                        "options": e["options"], "pix_fmt_fed": e.get("pix_fmt_fed"), "gop_size": e.get("gop_size")}
                for i, r in enumerate([warm] + reps):
                    out["runs"].append({**base, "rep": "warmup" if i == 0 else i, **r})
                good = [r for r in reps if r.get("ok")]
                s = {**base, "reps_ok": len(good), "quality_check": qc}
                if good:
                    for k in ("fps", "cpu_ms_per_frame", "cpu_cores", "bytes_per_frame"):
                        s[k + "_median"] = statistics.median(r[k] for r in good)
                        s[k + "_min"] = min(r[k] for r in good)
                        s[k + "_max"] = max(r[k] for r in good)
                else:
                    s["error"] = (reps[0] if reps else warm).get("error")
                out["summary"].append(s)
                print({k: s.get(k) for k in ("path", "size", "source", "reps_ok", "error")},
                      {"q": {k: qc.get(k) for k in ("psnr_y", "ssim_y", "error")}}, flush=True)
    out["system_after"] = B.snapshot()
    B.write(Path(a.outdir) if a.outdir else B.BENCH, f"matched_stream_{a.label or a.target}", out)


if __name__ == "__main__":
    main()
