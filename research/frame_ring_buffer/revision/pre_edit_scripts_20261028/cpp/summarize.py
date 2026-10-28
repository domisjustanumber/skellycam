"""Builds results/cpp_comparison.md and results/cpp_comparison.json from every result file of the cpp stage.

  .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\cpp\\summarize.py

Reads: results/micro_{cpp,py}.json, results/memcpy_{cpp,py}.json, results/ring_write/*.json, results/ring_spsc/*.json,
results/codec/*.json, results/load_*.json; and, for reference rows, ../baseline/results/a_write.json, b_read.json and
../prototypes/results/p1_write_skellycamvenv.json (only quoted, never re-measured here).
"""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent
R = HERE / "results"
OUT = {}
L = []


def load(p):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return None


def f(x, d=3):
    if x is None:
        return "-"
    if isinstance(x, (int,)) and not isinstance(x, bool):
        return str(x)
    return f"{x:.{d}f}"


def md_table(header, rows):
    L.append("| " + " | ".join(header) + " |")
    L.append("|" + "---|" * len(header))
    for r in rows:
        L.append("| " + " | ".join(str(c) for c in r) + " |")
    L.append("")


# ------------------------------------------------------------------------------------------------ ring: write-only
def ring_write_rows():
    out = []
    for p in sorted((R / "ring_write").glob("*.json")):
        d = load(p)
        if not d:
            continue
        ws = [r for r in d["roles"] if r["role"] == "writer"]
        rb = d["record_bytes"]
        agg = sum(r["fps"] for r in ws)
        out.append(dict(run=p.stem, size=f"{d['w']}x{d['h']}", n=d["ncams"], impl=d["impl"],
                        put_median_ms=st.median(r["op"]["median_ms"] for r in ws), put_worst_p99_ms=max(r["op"]["p99_ms"] for r in ws),
                        put_max_ms=max(r["op"]["max_ms"] for r in ws),
                        min_cam_fps=min(r["fps"] for r in ws), agg_fps=agg, agg_GBps=agg * rb / 1e9,
                        first_lap_median_ms=st.median(r["first_lap"]["median_ms"] for r in ws) if ws[0]["first_lap"]["n"] else None,
                        cpu_ms_per_frame=st.mean(r["cpu_ms_per_frame"] for r in ws), verified=all(r["verified"] for r in ws),
                        ring_len=d["ring_len"], record_bytes=rb, slot_stride=d["slot_stride"]))
    return out


def spsc_rows():
    out = []
    for p in sorted((R / "ring_spsc").glob("*.json")):
        d = load(p)
        if not d:
            continue
        ws = sorted([r for r in d["roles"] if r["role"] == "writer"], key=lambda r: r["cam"])
        rs = sorted([r for r in d["roles"] if r["role"] == "reader"], key=lambda r: r["cam"])
        rb = d["record_bytes"]
        impl = d["impl"] if d["tool"] == "py_ring" else ("cpp_thread" if d["topology"] == "thread" else "cpp_proc")
        sustained = [r["n"] / r["elapsed_s"] for r in rs]
        out.append(dict(run=p.stem, size=f"{d['w']}x{d['h']}", n=d["ncams"], impl=impl, paced=d["paced_fps"],
                        frames_written=sum(w["n"] for w in ws), frames_read=sum(r["n"] for r in rs),
                        lost=sum(w["n"] for w in ws) - sum(r["n"] for r in rs), torn=sum(r["torn"] for r in rs),
                        seq_rejects=sum(r["seq_rejects"] for r in rs),
                        pub_median_ms=st.median(w["op"]["median_ms"] for w in ws), pub_worst_p99_ms=max(w["op"]["p99_ms"] for w in ws),
                        read_median_ms=st.median(r["op"]["median_ms"] for r in rs), read_worst_p99_ms=max(r["op"]["p99_ms"] for r in rs),
                        e2e_median_ms=st.median(r["e2e"]["median_ms"] for r in rs), e2e_worst_p99_ms=max(r["e2e"]["p99_ms"] for r in rs),
                        e2e_max_ms=max(r["e2e"]["max_ms"] for r in rs),
                        min_cam_sustained_fps=min(sustained), agg_sustained_fps=sum(sustained),
                        agg_GBps=sum(sustained) * rb / 1e9, writer_blocked_events=sum(w["blocked_events"] for w in ws),
                        writer_cpu_ms_per_frame=st.mean(w["cpu_ms_per_frame"] for w in ws),
                        reader_cpu_ms_per_frame=st.mean(r["cpu_ms_per_frame"] for r in rs), record_bytes=rb, ring_len=d["ring_len"]))
    return out


def codec_rows():
    out = []
    for p in sorted((R / "codec").glob("*.json")):
        d = load(p)
        if not d:
            continue
        lang = d.get("lang", "cpp")
        tag = p.stem
        if d["mode"] == "decode":
            ps = d["procs"]
            out.append(dict(run=tag, mode="decode", lang=lang, opencv=d["opencv"], size=d["size"], n=d["nprocs"], inplace=d.get("inplace"),
                            median_ms=st.median(x["lat"]["median_ms"] for x in ps), worst_p99_ms=max(x["lat"]["p99_ms"] for x in ps),
                            min_fps=min(x["fps"] for x in ps), agg_fps=sum(x["fps"] for x in ps),
                            cpu_ms_per_frame=st.mean(x["cpu_ms_per_frame"] for x in ps),
                            content_ok=all(x["content_ok"] for x in ps), inplace_ok=all(x["inplace_ok"] for x in ps)))
        elif d["mode"] == "imencode":
            for x in d["rows"]:
                out.append(dict(run=tag, mode="imencode", lang=lang, opencv=d["opencv"], size=d["size"], variant=x["variant"],
                                median_ms=x["lat"]["median_ms"], p99_ms=x["lat"]["p99_ms"], fps=x["fps"], cpu_ms_per_frame=x["cpu_ms_per_frame"],
                                mean_kb=x["mean_kb"]))
        else:
            ps = d["procs"]
            out.append(dict(run=tag, mode="videowriter", lang=lang, opencv=d["opencv"], size=d["size"], n=d["nprocs"], paced=d["paced_fps"],
                            threads=d["threads"], backend=",".join(sorted({x["backend"] for x in ps})),
                            write_median_ms=st.median(x["lat"]["median_ms"] for x in ps), write_worst_p99_ms=max(x["lat"]["p99_ms"] for x in ps),
                            late_writes=sum(x["late_writes"] for x in ps), release_s_max=max(x["release_s"] for x in ps),
                            min_encode_fps_incl_release=min(x["encode_fps_incl_release"] for x in ps),
                            sum_cpu_pct=sum(x["cpu_pct"] for x in ps),
                            frames_ok=all(x["frames_in_file"] == x["n"] for x in ps), file_bytes=[x["file_bytes"] for x in ps],
                            mbit_s_per_cam=st.mean(x["file_bytes"] * 8 / 1e6 / (x["n"] / 60.0) for x in ps)))
    return out


def loads():
    out = []
    for p in sorted(R.glob("load_*.json")):
        d = load(p)
        if not d:
            continue
        dur = d["during"]
        top = d["before"]["top_processes"][:3]
        out.append(dict(step=d["name"], verdict=d["verdict"], elapsed_s=d["elapsed_s"], before_sys=d["before"]["system_cpu_pct"],
                        after_sys=d["after"]["system_cpu_pct"], mem_before=d["before"]["memory_pct"], mem_after=d["after"]["memory_pct"],
                        bg_mean=dur["background_mean"], bg_p95=dur["background_p95"], bg_max=dur["background_max"],
                        top_before=", ".join(f"{t['name']}:{t['cpu_pct_of_machine']}" for t in top), killed=d["killed_leftover_pids"]))
    return out


def main():
    L.append("# C++ vs Python head-to-head (cpp stage) - generated by summarize.py")
    L.append("")
    L.append("All numbers below are from the files under `cpp/results/`. Ring rows use 1 GiB rings (L = 1 GiB // record), records of "
             "632 B metadata + HxWx3 image, 10 s per run. `sk_head` = the real SkellyCam ring (HEAD 23ccbf20); `cpp_head_port` = the same "
             "algorithm (fresh heap temp + 2 copies) in C++; `py_seq` = numpy seqlock ring, 1 copy; `hybrid` = C++ ring called from Python "
             "via pybind11; `hybrid_ctypes` = the same C function via ctypes; `cpp_one_copy` / `cpp_proc` / `cpp_thread` = pure C++ "
             "(processes / threads).")
    L.append("")
    # ---- load
    ld = loads()
    OUT["load"] = ld
    L.append("## Machine load per step (run_with_load.py; idle rule: background mean and p95 < 10 %, system < 10 % before and after)")
    L.append("")
    md_table(["step", "verdict", "s", "sys % before / after", "mem % before / after", "background mean / p95 / max %", "top before"],
             [[x["step"], x["verdict"], x["elapsed_s"], f"{x['before_sys']} / {x['after_sys']}", f"{x['mem_before']} / {x['mem_after']}",
               f"{x['bg_mean']} / {x['bg_p95']} / {x['bg_max']}", x["top_before"]] for x in ld])
    # ---- ring write
    rw = ring_write_rows()
    OUT["ring_write"] = rw
    L.append("## 1a. Ring write, unthrottled (shape of baseline/bench_a_write.py), N spawned writer processes")
    L.append("")
    md_table(["run", "put median ms", "worst p99 ms", "max ms", "slowest-camera fps", "aggregate GB/s", "first-lap median ms",
              "CPU ms/frame", "slot verified"],
             [[x["run"], f(x["put_median_ms"], 4), f(x["put_worst_p99_ms"], 4), f(x["put_max_ms"], 3), f(x["min_cam_fps"], 0),
               f(x["agg_GBps"], 2), f(x["first_lap_median_ms"], 4), f(x["cpu_ms_per_frame"], 4), x["verified"]] for x in rw])
    # ---- spsc
    sp = spsc_rows()
    OUT["ring_spsc"] = sp
    L.append("## 1b. Ring SPSC: N writer + N reader processes (or threads), lossless gating, reader copies every frame out")
    L.append("")
    md_table(["run", "written / read / lost / torn", "publish median / p99 ms", "read median / p99 ms", "publish->read e2e median / p99 / max ms",
              "slowest-camera sustained fps", "aggregate GB/s", "writer blocked events", "CPU ms/frame writer / reader"],
             [[x["run"], f"{x['frames_written']} / {x['frames_read']} / {x['lost']} / {x['torn']}", f"{f(x['pub_median_ms'], 4)} / {f(x['pub_worst_p99_ms'], 4)}",
               f"{f(x['read_median_ms'], 4)} / {f(x['read_worst_p99_ms'], 4)}",
               f"{f(x['e2e_median_ms'], 3)} / {f(x['e2e_worst_p99_ms'], 3)} / {f(x['e2e_max_ms'], 3)}",
               f(x["min_cam_sustained_fps"], 0), f(x["agg_GBps"], 2), x["writer_blocked_events"],
               f"{f(x['writer_cpu_ms_per_frame'], 4)} / {f(x['reader_cpu_ms_per_frame'], 4)}"] for x in sp])
    # ---- memcpy
    mc, mp_ = load(R / "memcpy_cpp.json"), load(R / "memcpy_py.json")
    OUT["memcpy"] = {"cpp": mc, "py": mp_}
    if mc and mp_:
        L.append("## 2. Copy bandwidth (memcpybench.exe vs py_memcpy.py)")
        L.append("")
        rows = []
        for r in mc["rows"] + mp_["rows"]:
            if r["scenario"] == "pixel_op":
                continue
            lat = r.get("lat")
            rows.append([r["lang"], r["size"], r["scenario"], r["variant"], r["threads"], f(r["gbps_median"], 2),
                         f"{f(r['gbps_min'], 2)}-{f(r['gbps_max'], 2)}",
                         f"{lat['median_ms'] * 1e3:.2f} / {lat['p99_ms'] * 1e3:.2f}" if lat else "-"])
        rows.sort(key=lambda x: (x[2], x[1], x[4], x[0], x[3]))
        md_table(["lang", "size", "scenario", "variant", "threads", "GB/s median", "GB/s min-max (5 reps)", "per-copy median / p99 us"], rows)
        L.append("Pixel ops (hypothesis C2):")
        L.append("")
        md_table(["lang", "size", "op", "median / p99 ms", "check"],
                 [[r["lang"], r["size"], r["variant"], f"{f(r['lat']['median_ms'], 4)} / {f(r['lat']['p99_ms'], 4)}", r.get("check")]
                  for r in mc["rows"] + mp_["rows"] + ((load(R / "pixel_cv2_py.json") or {}).get("rows", []))
                  if r["scenario"] == "pixel_op"])
    # ---- micro
    mic, mip = load(R / "micro_cpp.json"), load(R / "micro_py.json")
    OUT["micro"] = {"cpp": mic, "py": mip}
    if mic and mip:
        L.append("## 3. Per-operation fixed costs (microbench.exe vs py_micro.py)")
        L.append("")
        rows = []
        for r in mic["rows"] + mip["rows"]:
            if "lat" in r:
                rows.append([r["lang"], r["group"], r["op"], f"{r['lat']['median_ms'] * 1e3:.3f} / {r['lat']['p99_ms'] * 1e3:.3f} us (n={r['lat']['n']})"])
            else:
                rows.append([r["lang"], r["group"], r["op"], f"{r['ns_per_op_median']:.2f} ns/op ({r['ns_min']:.2f}-{r['ns_max']:.2f})"])
        md_table(["lang", "group", "op", "value (median / p99, or ns/op median and min-max of 5 reps)"], rows)
    # ---- codec
    cr = codec_rows()
    OUT["codec"] = cr
    L.append("## 4. Decode / encode / record (codecbench.exe with OpenCV 4.8.0 C++ SDK vs py_codec.py with cv2 4.8.0 and cv2 4.12.0)")
    L.append("")
    md_table(["run", "OpenCV", "procs", "median / worst p99 ms", "slowest fps", "CPU ms/frame", "content ok", "in place"],
             [[x["run"], x["opencv"], x["n"], f"{f(x['median_ms'])} / {f(x['worst_p99_ms'])}", f(x["min_fps"], 1), f(x["cpu_ms_per_frame"]),
               x["content_ok"], x["inplace_ok"]] for x in cr if x["mode"] == "decode"])
    md_table(["run", "OpenCV", "variant", "median / p99 ms", "fps", "CPU ms/frame", "mean KB"],
             [[x["run"], x["opencv"], x["variant"], f"{f(x['median_ms'])} / {f(x['p99_ms'])}", f(x["fps"], 1), f(x["cpu_ms_per_frame"]), f(x["mean_kb"], 1)]
              for x in cr if x["mode"] == "imencode"])
    md_table(["run", "OpenCV", "backend", "write median / worst p99 ms", "late writes", "max release s", "slowest encode fps incl. release",
              "summed CPU %", "frames in file == written", "Mbit/s per camera"],
             [[x["run"], x["opencv"], x["backend"], f"{f(x['write_median_ms'])} / {f(x['write_worst_p99_ms'])}", x["late_writes"], f(x["release_s_max"], 2),
               f(x["min_encode_fps_incl_release"], 1), f(x["sum_cpu_pct"], 0), x["frames_ok"], f(x["mbit_s_per_cam"], 1)]
              for x in cr if x["mode"] == "videowriter"])
    # ---- references
    aw = load(HERE.parent / "baseline" / "results" / "a_write.json")
    if aw:
        ref = [[r["size"], r["n_cams"], r["mode"], f(r["median_of_cam_median_ms"], 3), f(r["max_cam_p99_ms"], 3), f(r["min_cam_fps"], 0), f(r["aggregate_GBps"], 2)]
               for r in aw["rows"] if r["n_cams"] in (1, 5)]
        OUT["reference_baseline_a_write"] = ref
        L.append("## Reference: baseline/results/a_write.json (idle 20261027 run, same workload as 1a; quoted, not re-measured)")
        L.append("")
        md_table(["size", "N", "mode", "median ms", "worst p99 ms", "slowest fps", "aggregate GB/s"], ref)
    (R / "cpp_comparison.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (R / "cpp_comparison.json").write_text(json.dumps(OUT, indent=1, default=str))
    print("\n".join(L))


if __name__ == "__main__":
    main()
