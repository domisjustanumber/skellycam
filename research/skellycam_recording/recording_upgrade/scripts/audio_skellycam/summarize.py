"""Summarise crash_kill.json + killed_readers.json + electron_killed_*.json into one table (summary.json, printed).
Usage: python -I summarize.py <results_dir>
"""
import json
import os
import statistics
import sys


def main():
    d = sys.argv[1]
    ck = json.load(open(os.path.join(d, "crash_kill.json")))["results"]
    kr = {r["file"]: r for r in json.load(open(os.path.join(d, "killed_readers.json")))["results"]} if os.path.exists(os.path.join(d, "killed_readers.json")) else {}
    el = {}
    for e in ("e35", "e45"):
        p = os.path.join(d, f"electron_killed_{e}.json")
        if os.path.exists(p):
            el[e] = {f["name"]: f for f in json.load(open(p))["files"]}
    fmts = []
    for r in ck:
        if r["format"] not in fmts:
            fmts.append(r["format"])
    out = []
    for f in fmts:
        rs = [r for r in ck if r["format"] == f]
        lost = [r["lost_ms"] for r in rs]
        row = dict(format=f, kills=len(rs), lost_ms_median=statistics.median(lost), lost_ms_min=min(lost), lost_ms_max=max(lost),
                   lost_ms_exit=[r["lost_ms"] for r in rs if r["method"] == "exit"], lost_ms_term=[r["lost_ms"] for r in rs if r["method"] == "term"],
                   pyav_demux_errors=sum(1 for r in rs if r["demux_error"]), pyav_decode_errors=sum(r["decode_errors"] for r in rs))
        k = [kr[r["file"]] for r in rs if r["file"] in kr]
        if k:
            row["ffmpeg_samples_eq_pyav"] = sum(1 for x in k if x["ffmpeg"]["samples"] == x["pyav_decoded"])
            row["ffmpeg_stderr_nonempty"] = sum(1 for x in k if x["ffmpeg"]["stderr"].strip())
            row["ffprobe_duration_na"] = sum(1 for x in k if x["ffprobe"]["duration"] in (None, "N/A"))
            row["vlc_decoded_vs_pyav_ms"] = [round(1000 * ((x["vlc"]["samples"] or 0) - x["pyav_decoded"]) / 48000, 1) for x in k]
            row["vlc_play_vs_pyav_ms"] = [round(1000 * (x["vlc_play"]["samples"] * 48000 / x["vlc_play"]["rate"] - x["pyav_decoded"]) / 48000, 1)
                                          for x in k if x.get("vlc_play")]
            row["repair_ok"] = sum(1 for x in k if x["repair"].get("rc") == 0 and x["repair"].get("decoded") == x["pyav_decoded"])
            row["repair_wall_s_median"] = statistics.median(x["repair"]["wall_s"] for x in k)
            sib = [x.get("streaminfo_before") for x in k if x.get("streaminfo_before")]
            if sib:
                row["flac_total_samples_zero_before"] = sum(1 for s in sib if s["total_samples"] == 0)
                row["flac_total_samples_after_repair"] = sorted({x["repair"].get("streaminfo_after", {}).get("total_samples") == x["pyav_decoded"] for x in k})
        for e, m in el.items():
            xs = [m.get(r["file"]) for r in rs if m.get(r["file"])]
            if xs:
                row[f"{e}_decodeAudioData_ok"] = sum(1 for x in xs if "length" in (x.get("decodeAudioData") or {}))
                row[f"{e}_decodeAudioData_vs_pyav_ms"] = [round(1000 * (x["decodeAudioData"]["length"] - r["decoded"]) / 48000, 1)
                                                          for x, r in zip(xs, rs) if "length" in (x.get("decodeAudioData") or {})]
                row[f"{e}_audio_el_ok"] = sum(1 for x in xs if x["audioElement"].get("duration") is not None and not x["audioElement"].get("error"))
                row[f"{e}_audio_el_durations"] = sorted({str(x["audioElement"].get("duration"))[:8] for x in xs})[:4]
                row[f"{e}_audio_el_played"] = sum(1 for x in xs if (x["audioElement"].get("playAdvance") or 0) > 0.2)
                row[f"{e}_audio_el_errors"] = sorted({str(x["audioElement"].get("error")) for x in xs if x["audioElement"].get("error")})
        out.append(row)
        print(json.dumps(row))
    json.dump(dict(rows=out), open(os.path.join(d, "summary.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
