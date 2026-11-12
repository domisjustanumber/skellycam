"""Summarise T-S5 Electron results. Usage: python -I summarize.py func <e35_func.json> <e45_func.json> <out.json>
                                          python -I summarize.py bench <e35_bench.json> <e45_bench.json> <out.json>"""
import json, statistics as st, sys


def probes_table(sem):
    rows = {}
    for t, v in sem.items():
        if t.startswith("localhost"):
            continue
        pr = {}
        for p in v["probes"]:
            key = f"{p.get('method')} {p.get('range')}"
            pr[key] = p.get("error") or f"{p.get('status')} CR={p.get('contentRange')} CL={p.get('contentLength')} AR={p.get('acceptRanges')}"
        rows[t] = {"probes": pr, "checks": v["checks"],
                   "past4GiB": {k: (x.get("error") or f"{x['status']} sha_ok={x['sha_ok']} CR={x['contentRange']}") for k, x in v["past4GiB"].items()}}
    if "localhost_vs_ipv4_4KB_seq" in sem:
        rows["localhost_vs_ipv4_4KB_seq"] = sem["localhost_vs_ipv4_4KB_seq"]
    return rows


def correct_table(cor):
    out = {}
    for t, v in cor.items():
        r = {"exception": v.get("exception", "").split("\n")[0] or None}
        for k in ("locator_cam0", "locator_big"):
            x = v.get(k)
            r[k] = x if isinstance(x, str) else {kk: x.get(kk) for kk in ("ok", "reason", "sha_ok", "reads", "ms")}
        r["flac"] = {}
        for n, f in (v.get("flac") or {}).items():
            if isinstance(f, str) or "full" not in f:
                r["flac"][n] = f
                continue
            r["flac"][n] = {"decoded": f"{f['full']['decoded_samples']}/{f['ref_samples']}", "max_lsb16": f["full"]["max_abs_diff_lsb16"],
                            "from_700_max_lsb16": f["from_packet_700"]["max_abs_diff_lsb16"], "errors": [f["full"]["error"], f["from_packet_700"]["error"]],
                            "range_short": f["full"]["range_short"], "decode_ms_1406_reads": f["full"]["ms"],
                            "skau_locator": {kk: f["locator_skau"].get(kk) for kk in ("ok", "sha_ok", "reads", "ms")}}
        r["jpeg_conc16"] = v.get("jpeg_conc16")
        out[t] = r
    return out


def func(paths, out):
    res = {}
    for p in paths:
        d = json.load(open(p))
        key = "E" + d["electron"]
        ph = d["phases"]
        res[key] = {"electron": d["electron"], "chrome": d["chrome"], "error": d.get("error"),
                    "semantics_file_origin": probes_table(ph["semantics"]),
                    "semantics_skr_origin": {"origin": ph["origin_skr"]["origin"], **probes_table(ph["origin_skr"]["semantics"])} if "origin_skr" in ph else None,
                    "diag_http_cache": ph.get("diag"), "correctness": correct_table(ph["correct"]),
                    "net_errors": d.get("net_errors"), "handler_counts": d.get("handler_counts"),
                    "handler_first_headers": {k: v[:2] for k, v in d.get("handler_seen", {}).items()}}
    json.dump(res, open(out, "w"), indent=1)
    print(json.dumps(res, indent=1))


def bench(paths, out):
    res = {}
    for p in paths:
        d = json.load(open(p))
        key = "E" + d["electron"]
        groups = {}
        for r in d["phases"]["bench"]:
            g = (r["transport"], r["kind"], r["len"], r["conc"])
            groups.setdefault(g, []).append(r)
        rows = []
        for (t, kind, ln, conc), rs in groups.items():
            def agg(f, rs=rs):
                vals = [f(r) for r in rs if f(r) is not None]
                return None if not vals else {"med": round(st.median(vals), 2), "min": round(min(vals), 2), "max": round(max(vals), 2)}
            cpu = lambda name: (lambda r: (r["electron_cpu_pct"].get(name) or {}).get("cum_based"))
            row = {"transport": t, "kind": kind, "len": ln, "conc": conc, "runs": len(rs),
                   "p50_ms": agg(lambda r: r["p50_ms"]), "p99_ms": agg(lambda r: r["p99_ms"]),
                   "reads_per_s": agg(lambda r: r["reads_per_s"]), "MB_per_s": agg(lambda r: r["MB_per_s"]),
                   "bad": sum(r["bad"] for r in rs), "errors": sum(r["errors"] for r in rs), "reads": sum(r["reads"] for r in rs),
                   "cpu_renderer_pct": agg(cpu("Tab")), "cpu_browser_pct": agg(cpu("Browser")),
                   "cpu_network_pct": agg(lambda r: sum((v.get("cum_based") or 0) for k, v in r["electron_cpu_pct"].items() if "network" in k.lower()) or None),
                   "cpu_gpu_pct": agg(cpu("GPU")),
                   "server_cpu_pct": agg(lambda r: r.get("server_cpu_pct")), "server_conns": agg(lambda r: r.get("server_conns"))}
            if kind == "paced":
                row["target_reads"] = rs[0]["target_reads"]
                row["dropped_ticks"] = agg(lambda r: r["dropped_ticks"])
            rows.append(row)
        res[key] = {"electron": d["electron"], "chrome": d["chrome"], "started": d["started"], "finished": d["finished"],
                    "error": d.get("error"), "net_errors": d.get("net_errors"), "rows": rows,
                    "cpu_keys_seen": sorted({k for r in d["phases"]["bench"] for k in r["electron_cpu_pct"]})}
    json.dump(res, open(out, "w"), indent=1)
    for k, v in res.items():
        print("==", k, v["started"], v["finished"], v["error"], v["net_errors"]["counts"] if v["net_errors"] else None)
        for r in v["rows"]:
            f = lambda x: "-" if x is None else f"{x['med']}[{x['min']}-{x['max']}]"
            print(f"{r['transport']:20s} {r['kind']:9s} {r['len']:6d} c{r['conc']:<2d} p50 {f(r['p50_ms']):22s} p99 {f(r['p99_ms']):22s} "
                  f"rps {f(r['reads_per_s']):24s} bad {r['bad']} err {r['errors']} rend {f(r['cpu_renderer_pct'])} brow {f(r['cpu_browser_pct'])} "
                  f"net {f(r['cpu_network_pct'])} srv {f(r['server_cpu_pct'])} conns {f(r['server_conns'])}"
                  + (f" drop {f(r['dropped_ticks'])}/{r['target_reads']}" if r["kind"] == "paced" else ""))


if __name__ == "__main__":
    {"func": func, "bench": bench}[sys.argv[1]](sys.argv[2:4], sys.argv[4])
