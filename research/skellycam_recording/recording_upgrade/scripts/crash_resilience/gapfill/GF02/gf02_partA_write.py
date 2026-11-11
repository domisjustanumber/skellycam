# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""GF02 Part A writer (functional, no timing): clean-closed files, PyAV 19.0.2.

Inputs (built as scripts/jpeg_passthrough/verify_method_writer.py:88-92 builds them):
  c930e_full  c930e_720p_flash, 891 frames, real capture timestamps (jp_common.real_timestamps_ns)
  gap60       c930e frames 300..359 removed (831 frames), real timestamps kept (one 2 s gap)
  drop50      every 50th c930e frame removed (k % 50 == 49; 874 written), real timestamps kept
  c922_full   c922_720p_flash, 893 frames, real capture timestamps
  long        c930e_720p_flash looped to 54,000 frames, real c930e intervals looped (bench_open_long.py:49-54 shape;
              jp_common.jitter_timestamps_ns), no gap. Only mkv_fp and fmp4_1s_fp.
Containers (gf02_common.CONTAINERS): mkv_fp, mkv_fp_empty, fmp4pf_fp, fmp4_1s_fp; each with pts_mode real (stream
time base requested 1/1e6) and index (requested 1/30). Writer = GF02Writer (recwriter sidecar).
Per file: PyAV byte-exact demux, PyAV seek-by-pts identity at 11 targets, ffprobe packet count, ffprobe size list,
EBML scan (MKV). Writes results/crash_resilience/gapfill/GF02_partA_write.json and the reader job list.

Run (repo root):  uv run --script research/.../GF02/gf02_partA_write.py --skip-long   (then again with --long-only)
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gf02_common as G  # noqa: E402

C = G.C


def targets11(n: int) -> list[int]:
    return [0] + [n * p // 10 for p in range(1, 10)] + [n - 1]


def main() -> None:
    import av
    av.logging.set_level(av.logging.ERROR)
    skip_long = "--skip-long" in sys.argv
    long_only = "--long-only" in sys.argv  # second invocation: only the 54,000-frame files
    d = G.MEDIA / "partA"
    if d.exists() and not long_only:
        shutil.rmtree(d)
    d.mkdir(parents=True, exist_ok=True)
    c930 = C.load_set("c930e_720p_flash")
    ts930 = C.real_timestamps_ns("c930e_720p_flash", c930)
    c922 = C.load_set("c922_720p_flash")
    ts922 = C.real_timestamps_ns("c922_720p_flash", c922)
    inputs = {
        "c930e_full": ("c930e_720p_flash", list(range(len(c930)))),
        "gap60": ("c930e_720p_flash", [k for k in range(len(c930)) if not 300 <= k < 360]),
        "drop50": ("c930e_720p_flash", [k for k in range(len(c930)) if k % 50 != 49]),
        "c922_full": ("c922_720p_flash", list(range(len(c922)))),
    }
    src = {"c930e_720p_flash": (c930, ts930), "c922_720p_flash": (c922, ts922)}
    free = shutil.disk_usage(str(G.MEDIA)).free
    res = {"env": G.ffmpeg_versions(), "free_bytes_before": free, "files": {}, "jobs": []}
    for inp, (setname, keep) in inputs.items():
        if long_only:
            break
        frames, ts = src[setname]
        fr = [frames[k] for k in keep]
        for cont in G.CONTAINERS:
            for mode in ("real", "index"):
                stem = d / f"A_{inp}_{cont}_{mode}"
                w = G.GF02Writer(stem, 1280, 720, cont, pts_mode=mode)
                pts = [w.write(frames[k], k, ts[k]) for k in keep]
                w.close()
                p = w.video_path
                side = G.rw.read_sidecar(w.bin_path)
                row = {"input": inp, "set": setname, "container": cont, "pts_mode": mode, "n_written": len(fr),
                       "time_base": str(w.tb), "bytes": p.stat().st_size, "sidecar_records": int(len(side.records)),
                       "pts_adjusted": int(sum(1 for r in side.records if r["flags"] & G.rw.FLAG_PTS_ADJUSTED)),
                       "pyav": G.pyav_check(p, fr), "ffprobe": G.ffprobe_count(p), "ffprobe_sizes": G.ffprobe_sizes(p)}
                row["pyav_seek"] = [G.pyav_seek_identity(p, k, pts[k], fr[k]) for k in targets11(len(fr))]
                row["pyav_seek_exact"] = sum(1 for s in row["pyav_seek"] if s.get("match"))
                if cont.startswith("mkv"):
                    row["ebml"] = G.ebml_scan(p)
                res["files"][p.name] = row
                res["jobs"].append({"path": str(p), "set": setname, "idx": keep, "targets": targets11(len(fr)),
                                    "seq": True, "fmc": True, "tag": p.name})
                print(p.name, row["pyav"]["all_exact"], row["pyav"]["packets"], row["ffprobe"].get("nb_read_packets"),
                      row["pyav_seek_exact"], row["time_base"], flush=True)
    # long set
    if skip_long or free < 30 * 2**30:
        res["long_skipped"] = f"skip_long={skip_long}, free={free}"
    else:
        n = 54_000
        lts = C.jitter_timestamps_ns(n)
        for cont in ("mkv_fp", "fmp4_1s_fp"):
            for mode in ("real", "index"):
                stem = d / f"L_long_{cont}_{mode}"
                w = G.GF02Writer(stem, 1280, 720, cont, pts_mode=mode)
                pts = [w.write(c930[k % 891], k, lts[k]) for k in range(n)]
                w.close()
                p = w.video_path
                exp = [c930[k % 891] for k in range(n)]
                row = {"input": "long", "set": "c930e_720p_flash looped", "container": cont, "pts_mode": mode,
                       "n_written": n, "time_base": str(w.tb), "bytes": p.stat().st_size,
                       "pyav": G.pyav_check(p, exp), "ffprobe": G.ffprobe_count(p)}
                row["pyav_seek"] = [G.pyav_seek_identity(p, k, pts[k], exp[k]) for k in targets11(n)]
                row["pyav_seek_exact"] = sum(1 for s in row["pyav_seek"] if s.get("match"))
                res["files"][p.name] = row
                res["jobs"].append({"path": str(p), "set": "c930e_720p_flash", "loop": n, "targets": targets11(n),
                                    "seq": False, "fmc": True, "tag": p.name, "delete_after": True})
                print(p.name, row["pyav"]["all_exact"], row["pyav"]["packets"], row["ffprobe"].get("nb_read_packets"),
                      row["pyav_seek_exact"], row["time_base"], flush=True)
    tag = "_long" if long_only else ""
    G.write_json(G.RES / f"GF02_partA{tag}_write.json", res)
    G.write_json(G.TEMP / f"jobs_partA{tag}.json", res["jobs"])


if __name__ == "__main__":
    main()
