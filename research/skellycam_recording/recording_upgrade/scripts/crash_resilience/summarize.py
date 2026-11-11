"""Condense kill_matrix_{a,b}.json, truncation_{a,b}.json and electron_*.json into results/crash_resilience/summary.md.

usage: python summarize.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_cr as cc  # noqa: E402


def load(name):
    p = cc.RES / name
    return json.loads(p.read_text()) if p.exists() else None


def kill_table(runs, n):
    by = {}
    for r in runs:
        by.setdefault((r["payload"], r["container"]), {})[r.get("mode")] = r
    L = ["## Kill summary (ffprobe -count_frames on the file as left on disk; PyAV and cv2 agree unless noted)", "",
         f"`drained` = all {n} frames fed + encoder drained, killed before close; `idle` = killed after {n // 2} frames fed "
         "(encoder not drained); `rt` = fed at 30 fps, killed after the parent saw "
         f"{n // 2} frames fed; `busy` = killed while writing flat out after {n // 2} packets muxed. "
         "Cells: readable / muxed-before-kill (fed if different). `-` = file missing or unreadable header. "
         "`rep` = frames after ffmpeg -c copy to .mkv of the drained file.", "",
         "| payload | container | clean | drained | idle | rt | busy | dur w/o repair | PyAV seek (drained) | rep (drained) | note |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for (p, c) in cc.combos():
        m = by.get((p, c))
        if not m:
            continue
        first = next(iter(m.values()))
        if "summary" not in first:
            L.append(f"| {p} | {c} | refused: {first['status'][:70]} | | | | | | | | |")
            continue

        def cell(mode):
            r = m.get(mode)
            if not r or "summary" not in r:
                return "?"
            s = r["summary"]
            got = s["ffprobe"]
            mux = r["packets_muxed_reported"]
            fed = r["frames_fed_reported"]
            txt = f"{got}/{mux}" + (f" (fed {fed})" if fed != mux else "")
            if s["pyav"] != got or s["cv2"] != got:
                txt += f" [PyAV {s['pyav']}, cv2 {s['cv2']}]"
            return txt
        dr = m.get(f"drained:{n}", {})
        ds = dr.get("summary", {})
        rp = dr.get("repair", {})
        rep = (rp.get("ffmpeg_copy_read") or {}).get("ffprobe", rp.get("frames_total", rp.get("frames", "")))
        note = ""
        if "rawidx" in ds:
            note = f"idx+scan parser {ds['rawidx']}"
        if ds.get("byte_exact") is not None:
            note += f" byte-exact {ds['byte_exact']}"
        L.append(f"| {p} | {c} | {cell('clean')} | {cell(f'drained:{n}')} | {cell(f'idle:{n // 2}')} | {cell('rt')} | "
                 f"{cell('busy')} | {ds.get('dur')} | {ds.get('pyav_seek')} | {rep} | {note.strip()} |")
    return L


def trunc_table(variants):
    L = ["## Truncation summary (24 cuts of the drained image; sums over cuts)", "",
         "ratio = recovered / ideal (ffprobe); total-loss = cuts where ffprobe got 0 frames though ideal > 0; "
         "PyAV < ffprobe = cuts where the PyAV stop-at-first-error loop got fewer frames than ffprobe.", "",
         "| payload | container | cuts (mid-packet) | ideal | ffprobe ratio | total-loss | max short | PyAV < ffprobe | seek ok | repaired ratio |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for v in variants:
        if "agg" not in v:
            L.append(f"| {v['payload']} | {v['container']} | {v.get('skipped')} | | | | | | | |")
            continue
        g = v["agg"]
        rows = v["rows"]
        lt = sum(1 for r in rows if r["pyav"] < r["ffprobe"])
        ratio = f"{g['ffprobe_sum'] / g['ideal_sum']:.3f}" if g["ideal_sum"] else "n/a"
        rr = f"{g['repaired_sum'] / g['ideal_sum']:.3f}" if g.get("repaired_sum") is not None and g["ideal_sum"] else "n/a"
        L.append(f"| {v['payload']} | {v['container']} | {g['offsets']} ({g['mid_packet_offsets']}) | {g['ideal_sum']} | {ratio} | "
                 f"{g['ffprobe_total_loss']} | {g['ffprobe_max_short']} | {lt} | {g['seek_ok_when_ge4']} | {rr} |")
    return L


def electron_table(e):
    v = e["versions"]
    by = {}
    for r in e["results"]:
        by.setdefault((r["payload"], r["container"]), []).append(r)
    L = [f"## Electron {v['electron']} (Chromium {v['chrome']}) summary", "",
         "Per case: `ok` = loadedmetadata and 'ended' fired; decoded/expected frames during play; dur = duration before "
         "play (Infinity = unknown); `seek` = seek to the middle fired 'seeked'. `ERR n` = MediaError code n.", "",
         "| payload | container | case | result | decoded/expected | dur | seek |", "|---|---|---|---|---|---|---|"]
    for (p, c), rs in by.items():
        for r in rs:
            if r.get("probe_timeout"):
                res = "probe timeout (60 s)"
            elif r.get("loadedmetadata") is not True:
                er = r.get("error") or {}
                res = f"ERR {er.get('code')}: {str(er.get('message', ''))[:50]}" if er else f"no metadata ({r.get('loadedmetadata')})"
            else:
                res = "ok" if r.get("ended") is True else f"ended={r.get('ended')}, play={r.get('play_error', 'ok')}"
            L.append(f"| {p} | {c} | {r['case']} | {res} | {r.get('decoded_during_play', '')}/{r['expected_frames']} | "
                     f"{r.get('duration', '')} | {r.get('seek_mid', '')} |")
    return L


def repair_check(runs):
    n = same = seek_ok = seek_tested = 0
    odd = []
    for r in runs:
        sm = r.get("summary")
        if not sm or sm["ffprobe"] == 0:
            continue
        rp = r.get("repair") or {}
        x = rp.get("ffmpeg_copy_read")
        if x is None and "frames_total" not in rp and "frames" not in rp:
            continue
        got = x["ffprobe"] if x else rp.get("frames_total", rp.get("frames"))
        n += 1
        same += int(got == sm["ffprobe"])
        if x and x.get("pyav_seek") is not None:
            seek_tested += 1
            seek_ok += int(bool(x["pyav_seek"]) and x.get("dur") not in (None, "N/A"))
        if got != sm["ffprobe"]:
            odd.append(f"{r['payload']} {r['container']} {r.get('mode')}: {sm['ffprobe']} -> {got}")
    return ["## Repair check (ffmpeg -c copy -> .mkv of killed files with >= 1 readable frame)", "",
            f"- files: {n}; same ffprobe frame count after repair: {same}; PyAV seek ok and duration present: "
            f"{seek_ok}/{seek_tested} (seek is tested only for files with >= 4 frames)",
            *[f"- count changed: {o}" for o in odd]]


def main():
    L = ["# crash_resilience - condensed tables (generated by summarize.py from the JSON results)", ""]
    runs = []
    n = 150
    for t in ("kill_matrix_a.json", "kill_matrix_b.json"):
        d = load(t)
        if d:
            runs += d["runs"]
            n = d["n"]
    L += kill_table(runs, n) + [""]
    L += repair_check(runs) + [""]
    variants = []
    for t in ("truncation_a.json", "truncation_b.json"):
        d = load(t)
        if d:
            variants += d["variants"]
    order = {pc: i for i, pc in enumerate(cc.combos())}
    variants.sort(key=lambda v: order.get((v["payload"], v["container"]), 999))
    L += trunc_table(variants) + [""]
    for lab in ("e35", "e45"):
        e = load(f"electron_{lab}.json")
        if e:
            L += electron_table(e) + [""]
    (cc.RES / "summary.md").write_text("\n".join(L) + "\n")
    print("wrote", cc.RES / "summary.md")


if __name__ == "__main__":
    main()
