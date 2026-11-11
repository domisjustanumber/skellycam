"""GF02: merge the writer/reader JSON into GF02_container_matrix.json and print the Markdown tables (stdlib only).

usage: python gf02_report.py   (reads RES/GF02_partA_write.json, RES/GF02_partA_long_write.json, RES/GF02_partB_kills.json
       and the cv2 reader outputs in TEMP; writes RES/GF02_container_matrix.json and TEMP/tables.md)
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

RU = Path("C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade")
RES = RU / "results/crash_resilience/gapfill"
TEMP = Path("C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step3/GF02")
CONTS = ["mkv_fp", "mkv_fp_empty", "fmp4pf_fp", "fmp4_1s_fp"]
LABEL = {"mkv_fp": "MKV + fp", "mkv_fp_empty": "MKV + fp + empty pkt", "fmp4pf_fp": "fMP4 per-frame + fp",
         "fmp4_1s_fp": "fMP4 1 s + fp"}


def load(p: Path):
    return json.loads(p.read_text()) if p.exists() else None


def main() -> None:
    aw = load(RES / "GF02_partA_write.json")
    alw = load(RES / "GF02_partA_long_write.json")
    ar = load(TEMP / "partA_read.json")
    alr = load(TEMP / "partA_long_read.json")
    bw = load(RES / "GF02_partB_kills.json")
    br = load(TEMP / "partB_read.json")
    rd = {r["tag"]: r for r in (ar["results"] if ar else []) + (alr["results"] if alr else [])}
    brd = {r["tag"]: r for r in (br["results"] if br else [])}
    files = {**(aw or {}).get("files", {}), **(alw or {}).get("files", {})}
    rows_a = []
    for name, w in files.items():
        r = rd.get(name, {})
        rows_a.append({"file": name, **{k: w[k] for k in ("input", "container", "pts_mode", "n_written", "time_base", "bytes")},
                       "pyav_all_exact": w["pyav"]["all_exact"], "pyav_packets": w["pyav"]["packets"],
                       "pyav_empty_packets_seen": w["pyav"]["empty_packets"],
                       "ffprobe_packets": w["ffprobe"].get("nb_read_packets"), "ffprobe_duration": w["ffprobe"].get("duration"),
                       "ffprobe_zero_size_listed": (w.get("ffprobe_sizes") or {}).get("zero_size"),
                       "ebml": w.get("ebml"), "pyav_seek_exact": w["pyav_seek_exact"],
                       "pyav_seek_miss": [s for s in w["pyav_seek"] if not s.get("match")],
                       "cv2_frame_count": r.get("frame_count_prop"), "cv2_fps": r.get("fps_prop"),
                       "cv2_grab": r.get("grab_count"), "cv2_read": r.get("read_count"),
                       "cv2_seq_matches_input": r.get("seq_matches_input"), "cv2_seek_exact_input": r.get("seek_exact_input"),
                       "cv2_seek_exact_seq": r.get("seek_exact_seq"), "cv2_seek_total": r.get("seek_total"),
                       "cv2_seek": r.get("seek"), "freemocap": r.get("freemocap"), "freemocap_ok": r.get("freemocap_ok"),
                       "deleted_after_read": r.get("deleted_after_read")})
    rows_b = []
    for w in (bw or {}).get("rows", []):
        key = f"{w['container']}|{w['pts_mode']}|{w['kill_at']}|{w['method']}"
        kr, rr = brd.get("killed|" + key, {}), brd.get("recovered|" + key, {})
        rows_b.append({**w, "killed_cv2": {k: kr.get(k) for k in ("frame_count_prop", "fps_prop", "grab_count", "seek")},
                       "recovered_cv2": {k: rr.get(k) for k in ("frame_count_prop", "fps_prop", "grab_count", "seek")}})
    out = {"env_writer": (aw or {}).get("env"), "env_reader": {"opencv": (ar or {}).get("opencv"), "python": (ar or {}).get("python")},
           "free_bytes_before_partA": (aw or {}).get("free_bytes_before"), "long_free_bytes": (alw or {}).get("free_bytes_before"),
           "reference_counts": (ar or {}).get("reference_counts"), "partA": rows_a, "partB_kill_points": (bw or {}).get("kills"),
           "partB": rows_b, "note": "functional only; no timing recorded"}
    (RES / "GF02_container_matrix.json").write_text(json.dumps(out, indent=1, default=str))

    L = ["### Part A table", "", "Cell = cv2 FRAME_COUNT / written; cv2 POS_FRAMES seeks exact (identity vs input) of 11; "
         "FreeMoCap ok (count = written and 4 reads match). All files: PyAV byte-exact, ffprobe count = written.", "",
         "| container | PTS | c930e full (891) | gap60 (831) | drop50 (874) | c922 full (893) | long 54,000 | PyAV seek n/11 |",
         "|---|---|---|---|---|---|---|---|"]
    by = {(r["container"], r["pts_mode"], r["input"]): r for r in rows_a}
    for c in CONTS:
        for m in ("real", "index"):
            cells, ps = [], []
            for inp in ("c930e_full", "gap60", "drop50", "c922_full", "long"):
                r = by.get((c, m, inp))
                if not r:
                    cells.append("-")
                    continue
                cnt = r["cv2_frame_count"]
                cnt = int(cnt) if isinstance(cnt, float) and cnt.is_integer() else cnt
                ok = "ok" if r["freemocap_ok"] else "FAIL"
                ex = "" if r["pyav_all_exact"] and r["ffprobe_packets"] == r["n_written"] else " (!exact)"
                cells.append(f"{cnt} / {r['n_written']}; {r['cv2_seek_exact_input']}/11; {ok}{ex}")
                ps.append(str(r["pyav_seek_exact"]))
            L.append(f"| {LABEL[c]} | {m} | " + " | ".join(cells) + f" | {', '.join(ps)} |")
    L += ["", "### Part B table", "",
          "| container | PTS | kills (exit/term) | lost vs sidecar min/med/max | lost vs last M line min/med/max | torn tail seen (flagged is_corrupt) | ffprobe = PyAV packets | cv2 count killed (= exact frames) | cv2 grab killed = packets | PyAV / cv2 seek killed | recover matched = exact | recovered byte-exact | cv2 count recovered (= frames) | cv2 seek recovered |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in CONTS:
        for m in ("real", "index"):
            rs = [r for r in rows_b if r["container"] == c and r["pts_mode"] == m]
            if not rs:
                continue
            ls = [r["lost_vs_sidecar"] for r in rs]
            lm = [r["lost_vs_M_line"] for r in rs]
            torn = [r for r in rs if r["killed_pyav"].get("first_non_exact")]
            flagged = [r for r in torn if r["killed_pyav"]["first_non_exact"].get("packet_is_corrupt")]
            ffp = sum(1 for r in rs if r["killed_ffprobe"].get("nb_read_packets") == r["killed_pyav"]["packets"])
            cnts = [r["killed_cv2"]["frame_count_prop"] for r in rs]
            cnt_eq = sum(1 for r in rs if r["killed_cv2"]["frame_count_prop"] == r["killed_pyav"]["exact_prefix"])
            uniq = sorted({(int(x) if isinstance(x, float) and abs(x) < 1e15 and x.is_integer() else x) for x in cnts}, key=str)
            cnt_txt = f"{cnt_eq}/{len(rs)}" + ("" if cnt_eq == len(rs) else f" (values seen: {', '.join(map(str, uniq[:4]))}{'...' if len(uniq) > 4 else ''})")
            gr = sum(1 for r in rs if r["killed_cv2"]["grab_count"] == r["killed_pyav"]["packets"])
            ps = sum(1 for r in rs if (r.get("killed_pyav_seek") or {}).get("match"))
            cs = sum(1 for r in rs if (r["killed_cv2"]["seek"] or [{}])[0].get("match_input"))
            rm = sum(1 for r in rs if (r.get("recover") or {}).get("matched_prefix") == r["killed_pyav"]["exact_prefix"])
            rx = sum(1 for r in rs if r.get("recovered_pyav") and r["recovered_pyav"]["exact_prefix"] == r["recovered_pyav"]["packets"]
                     == (r.get("recover") or {}).get("matched_prefix"))
            rc = sum(1 for r in rs if r.get("recovered_pyav") and r["recovered_cv2"]["frame_count_prop"] == r["recovered_pyav"]["packets"])
            rsk = sum(1 for r in rs if (r["recovered_cv2"]["seek"] or [{}])[0].get("match_input"))
            ne = sum(1 for r in rs if r["method"] == "exit")
            n = len(rs)
            L.append(f"| {LABEL[c]} | {m} | {n} ({ne}/{n - ne}) | {min(ls)}/{statistics.median(ls):g}/{max(ls)} | "
                     f"{min(lm)}/{statistics.median(lm):g}/{max(lm)} | {len(torn)} ({len(flagged)}) | {ffp}/{n} | {cnt_txt} | "
                     f"{gr}/{n} | {ps}/{n} / {cs}/{n} | {rm}/{n} | {rx}/{n} | {rc}/{n} | {rsk}/{n} |")
    (TEMP / "tables.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
