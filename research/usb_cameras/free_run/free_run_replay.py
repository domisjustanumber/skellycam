"""Offline replay of pairing rules over the logs of free_run_log.py. Pure Python, deterministic.

  python free_run_replay.py --selftest
  python free_run_replay.py <run dir> [<run dir> ...]     (prints Markdown tables)

Times are in ns on the perf_counter base. "arrival" = arrival_ns (OnReadSample), "sample" = sample_ns
(the driver's sample time, converted by the product). Neither clock is the moment of exposure.
"""

import bisect
import csv
import itertools
import json
import sys
from pathlib import Path

P = 1e9 / 30  # one nominal frame period (ns)
NO_SAMPLE_NS = -2 ** 63
WAKE_NS = 1_200_000  # gate of today: the next round opens about 1.2 ms after the close (spread analysis)
BUDGETS_MS = (0, 17, 33, 50)


# ----- loading -----

def load(run):
    run = Path(run)
    meta = json.loads((run / "meta.json").read_text())
    cams = {}
    for label, info in meta["cameras"].items():
        path = run / f"{label}.csv"
        if not path.exists() or not info.get("frames"):
            continue
        rows = [tuple(map(int, r)) for r in list(csv.reader(path.open()))[1:]]
        rows = [r for r in rows if meta["go_ns"] <= r[0] <= meta["stop_ns"]]
        cams[label] = dict(a=[r[0] for r in rows], s=[r[1] for r in rows], n=[r[2] for r in rows],
                           disc=[r[3] for r in rows], size=[r[4] for r in rows], read=[r[6] for r in rows])
    return meta, cams


# ----- small statistics -----

def q(values, p):
    v = sorted(values)
    if not v:
        return float("nan")
    k = (len(v) - 1) * p
    lo = int(k)
    return v[lo] + (v[min(lo + 1, len(v) - 1)] - v[lo]) * (k - lo)


def summary(values_ns):
    ms = [v / 1e6 for v in values_ns]
    return dict(median=q(ms, .5), p95=q(ms, .95), max=max(ms, default=float("nan")),
                above=100 * sum(v > P / 1e6 for v in ms) / max(1, len(ms)), n=len(ms))


# ----- a. per camera -----

def camera_stats(c):
    a, s, n = c["a"], c["s"], c["n"]
    span_n = n[-1] - n[0]
    gaps_n = sum(y - x - 1 for x, y in zip(n, n[1:]))
    ia = [y - x for x, y in zip(a, a[1:])]
    grid = {16: 0, 32: 0, 48: 0, 64: 0, "other": 0}
    for d in ia:
        k = round(d / 16e6) * 16
        if abs(d - k * 1e6) < 2e6 and k in grid:
            grid[k] += 1
        elif d > 56e6:
            grid[64] += 1
        else:
            grid["other"] += 1
    off = [(x % 16_000_000) for x in a]  # position on a 16.000 ms grid
    valid = [x != NO_SAMPLE_NS for x in s]
    stats = dict(frames=len(a), period_arrival=(a[-1] - a[0]) / span_n / 1e6,
                 source_gaps=gaps_n, discontinuities=sum(c["disc"]), grid=grid,
                 grid_offset_ms=(q(off, .05) / 1e6, q(off, .5) / 1e6, q(off, .95) / 1e6),
                 jpeg_kb=sum(c["size"]) / len(a) / 1e3,
                 read_lag_ms=(q([r - x for r, x in zip(c["read"], a)], .5) / 1e6,
                              q([r - x for r, x in zip(c["read"], a)], .99) / 1e6,
                              max(r - x for r, x in zip(c["read"], a)) / 1e6),
                 sample_valid=all(valid))
    if all(valid):
        d = [x - y for x, y in zip(a, s)]
        si = [y - x for x, y in zip(s, s[1:])]
        stats.update(period_sample=(s[-1] - s[0]) / span_n / 1e6,
                     arr_minus_sample_ms=tuple(f(d) / 1e6 for f in (min, lambda v: q(v, .05), lambda v: q(v, .5),
                                                                     lambda v: q(v, .95), max)),
                     sample_interval_ms=(q(si, .01) / 1e6, q(si, .5) / 1e6, q(si, .99) / 1e6),
                     sample_gaps=sum(1 for x in si if x > 1.5 * P))
    return stats


# ----- the rules: each returns a list of groups (tuple of index or None per camera) and latencies -----

def rule_gate(cams, start, wake=WAKE_NS):
    """D26: a round opens `wake` after the previous close; each camera takes its newest untaken frame
    that arrived by the open, else waits for its next; the round closes at the last take."""
    nxt = [0] * len(cams)
    open_t, groups, lat = start, [], []
    while True:
        picks, takes = [], []
        for k, a in enumerate(cams):
            j = bisect.bisect_right(a, open_t) - 1
            if j >= nxt[k]:
                picks.append(j), takes.append(open_t)
            elif nxt[k] < len(a):
                picks.append(nxt[k]), takes.append(a[nxt[k]])
            else:
                return groups, lat
        close = max(takes)
        groups.append(tuple(picks))
        lat.append(close - min(a[j] for a, j in zip(cams, picks)))
        nxt = [j + 1 for j in picks]
        open_t = close + wake


def rule_amendment(cams, start):
    """A-3: the close time is the latest arrival of the first fresh frames; each camera gives its newest
    frame that arrived by the close time (wake delay 0)."""
    close, groups, lat = start, [], []
    while True:
        first = [bisect.bisect_right(a, close) for a in cams]
        if any(f >= len(a) for f, a in zip(first, cams)):
            return groups, lat
        close = max(a[f] for a, f in zip(cams, first))
        picks = tuple(bisect.bisect_right(a, close) - 1 for a in cams)
        groups.append(picks)
        lat.append(close - min(a[j] for a, j in zip(cams, picks)))


def rule_causal(arr, clock, budget_ns, drop_ns=0):
    """Free run, causal pairing with a look-ahead budget. The head of a camera is its oldest frame that
    is newer than its last paired frame. When every camera has a head (at time T, by arrival), the
    window ends at W = T + budget. The candidate cuts: the heads; then the oldest head (on `clock`)
    swapped for that camera's next frame; then the next oldest swapped; ... (at most k - 1 swaps, each
    only if the next frame arrived by W). The rule picks the cut with the smallest
    spread + drop_ns per swapped frame (`drop_ns` is a hysteresis: each swap leaves a frame unpaired).
    Then each camera moves to a newer frame that arrived by the decision and does not raise the spread.
    The decision time is the arrival of the last frame looked at, or W when a swap had no frame by W.
    Returns groups, added latency (decision minus the latest arrival in the group) and group age
    (decision minus the earliest arrival in the group)."""
    k = len(arr)
    head = [0] * k
    groups, added, age = [], [], []
    while True:
        if any(h >= len(a) for h, a in zip(head, arr)):
            return groups, added, age
        t = max(a[h] for h, a in zip(head, arr))
        window = t + budget_ns
        decide, chain = t, [list(head)]
        for _ in range(k - 1):  # drop the oldest head, then the next oldest, ...: the possible cuts
            state = chain[-1]
            times = [c[h] for c, h in zip(clock, state)]
            old = min(range(k), key=lambda i: (times[i], i))
            nxt = state[old] + 1
            if nxt >= len(arr[old]) or arr[old][nxt] > window:
                decide = window
                break
            decide = max(decide, arr[old][nxt])
            chain.append(state[:old] + [nxt] + state[old + 1:])

        def cost(r):
            times = [c[h] for c, h in zip(clock, chain[r])]
            return max(times) - min(times) + r * drop_ns
        head = chain[min(range(len(chain)), key=lambda r: (cost(r), r))]
        top = max(c[h] for c, h in zip(clock, head))
        for i in range(k):  # a newer frame that arrived by the decision and does not raise the spread: take it
            while head[i] + 1 < len(arr[i]) and arr[i][head[i] + 1] <= decide and clock[i][head[i] + 1] <= top:
                head[i] += 1
        groups.append(tuple(head))
        arrivals = [a[h] for a, h in zip(arr, head)]
        added.append(decide - max(arrivals))
        age.append(decide - min(arrivals))
        head = [h + 1 for h in head]


def rule_offline(clock, unpaired_cost=P, missing_cost=P, max_block=8):
    """Free run, offline best pairing (global optimum by dynamic programming).

    All frames of all cameras are merged in time order on `clock`. A group is a run of consecutive
    frames in that order; its two end frames are of different cameras and are in the group, and it
    holds at most one frame of each camera (other frames inside the run stay unpaired). The pairing
    minimises: sum of group spreads + one period per unpaired frame + one period per missing camera
    in a group. Thus a full group is kept unless its spread exceeds about two periods."""
    k = len(clock)
    merged = sorted((t, cam, j) for cam, c in enumerate(clock) for j, t in enumerate(c))
    n = len(merged)
    best, back = [0.0] * (n + 1), [None] * (n + 1)
    for j in range(n):
        best[j + 1], back[j + 1] = best[j] + unpaired_cost, ("skip", j)
        tj, cj, _ = merged[j]
        for i in range(j - 1, max(-1, j - max_block), -1):
            ti, ci, _ = merged[i]
            if tj - ti > 3 * P:
                break
            if ci == cj:
                continue
            distinct = len({m[1] for m in merged[i:j + 1]})
            cost = best[i] + (tj - ti) + unpaired_cost * (j - i + 1 - distinct) + missing_cost * (k - distinct)
            if cost < best[j + 1]:
                best[j + 1], back[j + 1] = cost, ("group", i)
    groups, j = [], n
    while j > 0:
        kind, i = back[j]
        if kind == "skip":
            j = i
            continue
        pick = [None] * k
        pick[merged[j - 1][1]] = merged[j - 1][2]
        pick[merged[i][1]] = merged[i][2]
        for _, cam, idx in merged[i + 1:j - 1]:
            if pick[cam] is None:
                pick[cam] = idx
        groups.append(tuple(pick))
        j = i
    return groups[::-1]


# ----- metrics of a list of groups -----

def spreads(groups, clock):
    return [max(c[j] for c, j in zip(clock, g)) - min(c[j] for c, j in zip(clock, g))
            for g in groups if None not in g]


def unused(groups, sizes):
    """Frames of each camera that are in no group, between its first and its last frame in a group."""
    out = []
    for k, size in enumerate(sizes):
        used = sorted(g[k] for g in groups if g[k] is not None)
        out.append((used[-1] - used[0] + 1 - len(set(used))) if used else size)
    return out


# ----- report -----

def fmt(x, d=1):
    return "n/a" if x != x else f"{x:.{d}f}"


def analyse(run):
    meta, cams = load(run)
    labels = list(cams)
    arr = [cams[l]["a"] for l in labels]
    samp = [cams[l]["s"] for l in labels]
    have_sample = all(all(x != NO_SAMPLE_NS for x in s) for s in samp)
    sizes = [len(a) for a in arr]
    start = meta["go_ns"]
    lines = [f"### {Path(run).name}", "",
             f"Window {meta['seconds']:.0f} s from {meta['utc_start']} UTC. Machine CPU during the window: mean "
             f"{meta['machine_cpu_percent']['mean']:.1f} %, max {meta['machine_cpu_percent']['max']:.1f} % of "
             f"{meta['logical_cpus']} logical CPUs. Logger processes: " +
             ", ".join(f"{l} {v:.3f} cores" for l, v in meta["child_cpu_cores"].items() if v is not None) + ".", ""]
    for l in meta["cameras"]:
        info = meta["cameras"][l]
        lines.append(f"- {l}: status {info.get('status')}; exposure read back {info.get('readback', {}).get('exposure')}; "
                     f"open {info.get('open_s')} s, close {info.get('close_s')} s; replaced in the waiting place "
                     f"{info.get('replaced_count')}")
    lines += ["", "**a. Per camera** (periods from the first and last frame of the window and the source frame numbers)", "",
              "| Camera | Frames | Period by arrival (ms) | Period by sample (ms) | Source-number gaps | Sample gaps > 1.5 P | "
              "Arrival intervals 16/32/48/64+/other | Position on a 16 ms grid p5/p50/p95 (ms) | Arrival minus sample min/p5/p50/p95/max (ms) | "
              "Sample interval p1/p50/p99 (ms) | Read lag p50/p99/max (ms) | JPEG kB |", "|" + "---|" * 12]
    st = {l: camera_stats(cams[l]) for l in labels}
    for l in labels:
        x = st[l]
        g = x["grid"]
        lines.append(f"| {l} | {x['frames']} | {x['period_arrival']:.4f} | {fmt(x.get('period_sample', float('nan')), 4)} | "
                     f"{x['source_gaps']} | {x.get('sample_gaps', 'n/a')} | {g[16]}/{g[32]}/{g[48]}/{g[64]}/{g['other']} | "
                     + "/".join(fmt(v) for v in x["grid_offset_ms"]) + " | "
                     + ("/".join(fmt(v) for v in x["arr_minus_sample_ms"]) if "arr_minus_sample_ms" in x else "n/a") + " | "
                     + ("/".join(fmt(v, 2) for v in x["sample_interval_ms"]) if "sample_interval_ms" in x else "n/a") + " | "
                     + "/".join(fmt(v, 2) for v in x["read_lag_ms"]) + f" | {x['jpeg_kb']:.0f} |")
    lines += ["", "Drift (period by arrival relative to the C922; frames over the window):", ""]
    ref = labels[0]
    for l in labels[1:]:
        r = st[l]["period_arrival"] / st[ref]["period_arrival"] - 1
        lines.append(f"- {l} vs {ref}: {100 * r:+.3f} % ; frames {st[l]['frames'] - st[ref]['frames']:+d} "
                     f"(source-number span {cams[l]['n'][-1] - cams[l]['n'][0] - cams[ref]['n'][-1] + cams[ref]['n'][0]:+d})")
    # rules
    results = []
    g, lat = rule_gate(arr, start)
    results.append(("b. Gate of today (D26, wake 1.2 ms)", g, lat, None))
    g0, _ = rule_gate(arr, start, wake=0)
    results.append(("b'. Gate of today, wake 0", g0, None, None))
    g, lat = rule_amendment(arr, start)
    results.append(("c. Amendment (A-3, wake 0)", g, lat, None))
    clocks = [("arrival", arr)] + ([("sample", samp)] if have_sample else [])
    for name, clock in clocks:
        results.append((f"d. Free run, offline best, paired by {name}", rule_offline(clock), None, name))
        results.append((f"d'. Offline best, full groups only, paired by {name}",
                        rule_offline(clock, missing_cost=1e18), None, name))
    for name, clock in clocks:
        for h in (0, 16):
            for d in BUDGETS_MS:
                if d == 0 and h:
                    continue  # H changed nothing at D=0 in the sweep over run 1
                gc, added, age = rule_causal(arr, clock, d * 1_000_000, h * 1_000_000)
                results.append((f"e. Causal D={d} ms, H={h} ms, paired by {name}", gc, (added, age), name))
    lines += ["", "**b-e. Spread inside each group frame** (ms: median / p95 / max / % above one period). Unused = frames "
              "of a camera in no group (replaced for b, c; unpaired for d, e), between its first and last grouped frame.", "",
              "| Rule | Groups | Lacking a camera | Spread by arrival | Spread by sample | Unused " + "/".join(labels) +
              " | Latency (ms, median/p95) |", "|---|---|---|---|---|---|---|"]
    out = {}
    for name, groups, lat, _ in results:
        sa, ss = summary(spreads(groups, arr)), summary(spreads(groups, samp)) if have_sample else None
        un = unused(groups, sizes)
        if lat is None:
            lt = ""
        elif isinstance(lat, tuple):
            lt = (f"added {fmt(q(lat[0], .5) / 1e6)}/{fmt(q(lat[0], .95) / 1e6)}; age of the oldest frame "
                  f"{fmt(q(lat[1], .5) / 1e6)}/{fmt(q(lat[1], .95) / 1e6)}")
        else:
            lt = f"age of the oldest frame at the close {fmt(q(lat, .5) / 1e6)}/{fmt(q(lat, .95) / 1e6)}"
        cell = lambda m: "n/a" if m is None else f"{fmt(m['median'])} / {fmt(m['p95'])} / {fmt(m['max'])} / {fmt(m['above'])} %"
        lines.append(f"| {name} | {len(groups)} | {sum(None in x for x in groups)} | {cell(sa)} | {cell(ss)} | "
                     f"{'/'.join(map(str, un))} | {lt} |")
        out[name] = dict(groups=len(groups), arrival=sa, sample=ss, unused=un)
    # self-consistency on real data: the amendment equals the causal rule at D=0 by arrival
    same = rule_amendment(arr, start)[0] == rule_causal(arr, arr, 0)[0]
    lines += ["", f"Check: the amendment and the causal rule at D=0 by arrival give the same groups: {same}.", ""]
    return "\n".join(lines), out, st


# ----- self-check on synthetic data with known answers -----

def selftest():
    ms = 1_000_000
    per = int(P)
    # 1. equal periods, phases 0/10/30 ms, no jitter
    cams = [[k * per + ph * ms for k in range(300)] for ph in (0, 10, 30)]
    g, _ = rule_amendment(cams, -1)
    assert {round(s / ms, 2) for s in spreads(g, cams)} == {30.0}, "amendment spread 30"
    assert rule_causal(cams, cams, 0)[0] == g, "causal D=0 equals the amendment"
    gc = rule_causal(cams, cams, 17 * ms)[0]
    assert {round(s / ms, 2) for s in spreads(gc[1:], cams)} == {13.33}, "causal D=17 finds the 13.33 ms cut"
    go = rule_offline(cams)
    sp = spreads(go, cams)
    assert all(abs(s - 13.333 * ms) < 0.01 * ms for s in sp), "offline best: period minus the largest gap"
    assert sum(None in x for x in go) <= 2 and sum(unused(go, [300] * 3)) == 0
    # 2. phases 0/10/20: the best cut gives 20 ms for every rule
    cams = [[k * per + ph * ms for k in range(300)] for ph in (0, 10, 20)]
    assert {round(s / ms, 2) for s in spreads(rule_offline(cams), cams)} == {20.0}
    # 3. hand case for the gate of today against the amendment
    A, B, C = [0, 30, 60, 90], [5, 35, 65, 95], [25, 58, 91]
    cams = [[x * ms for x in c] for c in (A, B, C)]
    g, _ = rule_gate(cams, -1, wake=1 * ms)
    assert g == [(0, 0, 0), (1, 1, 1), (2, 2, 2)] and [s // ms for s in spreads(g, cams)] == [25, 28, 31]
    g, _ = rule_amendment(cams, -1)
    assert g == [(0, 0, 0), (1, 1, 1), (3, 2, 2)] and [s // ms for s in spreads(g, cams)] == [25, 28, 26]
    # 4. drift: periods 33.30 / 33.333 / 33.37 ms over 300 s: the fast camera's extra frames end unpaired
    pers = (33.30, 33.3333, 33.37)
    cams = [[int(k * p * ms) + ph * ms for k in range(int(300_000 / p))] for p, ph in zip(pers, (0, 7, 3))]
    extra = len(cams[0]) - len(cams[2])
    go = rule_offline(cams)
    un = unused(go, [len(c) for c in cams])
    # the middle camera's extras pair with the fast camera in groups that lack the slow one
    lacking = sum(x[2] is None for x in go)
    assert abs(un[0] - (len(cams[0]) - len(cams[1]))) <= 2 and abs(lacking - (len(cams[1]) - len(cams[2]))) <= 2, \
        (un, lacking)
    g, _ = rule_amendment(cams, -1)
    un = unused(g, [len(c) for c in cams])
    assert abs(un[0] - un[2] - extra) <= 2, (un, extra)
    print("selftest ok")


def rate_summary(run):
    """The rate test: frames 6 to 90 after the controls were set (as the product's rate check, 10.1) and the
    whole window, both as (source-number span) / (arrival span); the mean JPEG size."""
    run = Path(run)
    meta = json.loads((run / "meta.json").read_text())
    rows = []
    for label, info in meta["cameras"].items():
        path = run / f"{label}.csv"
        if not path.exists() or not info.get("frames"):
            rows.append((label, info.get("status"), None, None, None, None))
            continue
        r = [tuple(map(int, x)) for x in list(csv.reader(path.open()))[1:]]
        after = [x for x in r if x[0] > info["controls_set_ns"]]
        s0 = after[0][2]
        by_n = {x[2]: x for x in after}
        f6, f90 = by_n.get(s0 + 5), by_n.get(s0 + 89)
        check = None if not (f6 and f90) else (f90[2] - f6[2]) * 1e9 / (f90[0] - f6[0])
        w = [x for x in r if meta["go_ns"] <= x[0] <= meta["stop_ns"]]
        whole = (w[-1][2] - w[0][2]) * 1e9 / (w[-1][0] - w[0][0])
        rows.append((label, info.get("readback", {}).get("exposure"), check, whole,
                     sum(x[4] for x in w) / len(w) / 1e3, info.get("status")))
    return meta, rows


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    elif sys.argv[1] == "--rate":
        for run in sys.argv[2:]:
            meta, rows = rate_summary(run)
            for label, readback, check, whole, kb, status in rows:
                ok = None if check is None else (0.97 * meta["fps"] <= check <= 1.03 * meta["fps"])
                print(f"{Path(run).name} | {label} | {meta['exposure']} | readback {readback} | 6-90: "
                      f"{fmt(check or float('nan'), 2)} | whole: {fmt(whole or float('nan'), 2)} | pass {ok} | "
                      f"{fmt(kb or float('nan'), 0)} kB | {status}")
    else:
        for run in sys.argv[1:]:
            text, _, _ = analyse(run)
            print(text)
