r"""T-S6 part 2: libjpeg-turbo (simplejpeg 1.9.0) in N worker processes, results out of order, reorder buffer keyed by
seq feeding the writer in order. Checks 100 % pairing and in-order container pts; measures reorder hold time and
memory.

Run: <scratch tjvenv>\python.exe -I pairing_turbo.py   (venv: Python 3.13, av==19.0.2, numpy==2.5.4, simplejpeg==1.9.0)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import av  # noqa: E402
import numpy as np  # noqa: E402
import simplejpeg  # noqa: E402

import eplib as E  # noqa: E402
from pairing_qsv import gap_pattern  # noqa: E402


def run(size: str, workers: int, jitter_ms: float, timing: str, n: int, fail_mod: int = 0,
        pattern: str = "bursty") -> dict:
    name = f"turbo_{size}_w{workers}_j{int(jitter_ms)}_{timing}_{pattern}" + (f"_fail{fail_mod}" if fail_mod else "")
    d = E.SCRATCH / "pairing"
    d.mkdir(parents=True, exist_ok=True)
    stem = d / name
    src = E.FrameSource(size)
    sfns = gap_pattern(pattern, n)
    pool = E.TurboPool(size, workers, fail_mod=fail_mod, jitter_ms=jitter_ms)
    pool.warm()
    w = E.PairingWriter(stem, *E.DIMS[size], pool.name)
    lat = []
    t_next = time.perf_counter()
    t0 = time.perf_counter()
    for seq, sfn in enumerate(sfns):
        a = src.frame(sfn)
        if timing == "paced":
            now = time.perf_counter()
            if t_next > now:
                time.sleep(t_next - now)
            t_next += 1 / E.FPS
        for o in pool.submit(seq, a, E.make_meta(sfn)):
            lat.append((o.t_out - o.t_submit) * 1000)
            w.write(o)
    for o in pool.flush():
        lat.append((o.t_out - o.t_submit) * 1000)
        w.write(o)
    w.close()
    wall = time.perf_counter() - t0
    pool.close()
    v = E.verify(stem)
    v["mkv_bytes"] = w.mkv.stat().st_size
    w.mkv.unlink()
    st = pool.stats()
    lm = np.array(lat)
    raw_frame_bytes = E.DIMS[size][0] * E.DIMS[size][1] * 2
    expected_records = len(sfns) - len(st["skipped"])
    return {"name": name, "size": size, "workers": workers, "jitter_ms": jitter_ms, "timing": timing,
            "pattern": pattern, "fail_mod": fail_mod, "frames_in": len(sfns), "packets_out": w.count,
            "expected_records": expected_records, "fps_achieved": round(len(sfns) / wall, 1),
            "submit_to_release_ms_p50": round(float(np.percentile(lm, 50)), 2),
            "submit_to_release_ms_p99": round(float(np.percentile(lm, 99)), 2),
            "in_flight_raw_bytes_cap": st["max_in_flight_cap"] * raw_frame_bytes,
            "pool": st, "verify": v,
            "ok": v["all_pairs_ok"] and v["records"] == expected_records and v["mkv_pts_in_order"]}


def main():
    res = {"versions": {"python": sys.version.split()[0], "av": av.__version__, "ffmpeg": av.ffmpeg_version_info,
                        "numpy": np.__version__, "simplejpeg": simplejpeg.__version__},
           "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
    runs = []
    for workers in (2, 3, 4):
        for jitter in (0, 15):
            runs.append(run("1080p", workers, jitter, "unpaced", 600))
            print(runs[-1]["name"], runs[-1]["ok"], runs[-1]["pool"]["out_of_order_arrivals"], flush=True)
        runs.append(run("1080p", workers, 0, "paced", 300))
        print(runs[-1]["name"], runs[-1]["ok"], runs[-1]["pool"]["out_of_order_arrivals"], flush=True)
    runs.append(run("720p", 3, 15, "unpaced", 600, pattern="switch"))
    print(runs[-1]["name"], runs[-1]["ok"], flush=True)
    runs.append(run("1080p", 3, 15, "unpaced", 600, fail_mod=97))
    print(runs[-1]["name"], runs[-1]["ok"], runs[-1]["pool"]["skipped"], flush=True)
    res["runs"] = runs
    res["summary"] = {"runs": len(runs), "ok": sum(r["ok"] for r in runs),
                      "records": sum(r["verify"]["records"] for r in runs),
                      "out_of_order_arrivals": sum(r["pool"]["out_of_order_arrivals"] for r in runs)}
    res["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    E.RESULTS.mkdir(parents=True, exist_ok=True)
    (E.RESULTS / "turbo_pairing.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps(res["summary"]))


if __name__ == "__main__":
    main()
