# /// script
# requires-python = "==3.12.*"
# dependencies = []
# ///
"""Per file x reader seek-error summary of the seek_*.json results (sets crash, torn, repaired).
error = landed - target in samples at 48 kHz (< 0 = early). ps0 files: reported on the file timeline (+312), i.e.
0 = the reader is exact in file samples (then the CSV's file_sample_offset=312 maps it to the device).
VLC errors are corrected for the ms rounding of the request (set_time and --start-time take ms).
Usage: uv run --script .../opus_crash/summarize.py      Output: results/.../opus_crash/summary_<set>.csv
"""
import csv
import json
import os
import statistics as st

RES = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "results", "audio_single_file", "opus_crash"))
SR = 48000


def stats(v):
    v = [x for x in v if x is not None]
    if not v:
        return dict(n=0)
    return dict(n=len(v), min=min(v), max=max(v), median=st.median(v), exact=sum(1 for x in v if x == 0), within_1=sum(1 for x in v if abs(x) <= 1))


def ms_req(t):
    return round(t / SR * 1000) * SR // 1000 - t


def main():
    for s in ("crash", "torn", "repaired"):
        p = os.path.join(RES, f"seek_std_{s}.json")
        if not os.path.exists(p):
            continue
        std = json.load(open(p))
        files = std["files"]
        rows = {}

        def add(f, reader, i, err, past):
            if err is not None and "ps0" in f:
                err += 312
            rows.setdefault((f, reader), dict(inr=[], near=[], past=[]))
            n_t = sum(1 for x in std["seeks"] if x["file"] == f and not x["past_end"])
            key = "past" if past else ("near" if i >= n_t - (6 if n_t >= 20 else 2) else "inr")
            rows[(f, reader)][key].append(err)

        for x in std["seeks"]:
            f, t, past = x["file"], x["target"], x["past_end"]
            add(f, "pyav_pts", x["i"], x["pyav"].get("error_samples"), past)
            add(f, "ffmpeg_ss", x["i"], x["ffmpeg_ss"].get("error_samples"), past)
            e = x["vlc_set_time"].get("error_samples")
            add(f, "vlc_set_time", x["i"], None if e is None else e - ms_req(t), past)
            e = x["vlc_start_time"].get("error_samples")
            add(f, "vlc_start_time", x["i"], None if e is None else e - ms_req(t), past)
        for ev in ("e35", "e45"):
            q = os.path.join(RES, f"seek_electron_{s}_{ev}.json")
            if not os.path.exists(q):
                continue
            el = json.load(open(q))["files"]
            for f, a in el.items():
                L = files[f]["pyav"]["samples"]
                for i, sk in enumerate(a.get("wc", {}).get("seeks", [])):
                    add(f, f"wc_{ev}", i, sk.get("error_samples"), sk["n"] >= L)
                for i, sk in enumerate(a.get("el", {}).get("seeks", [])):
                    add(f, f"audio_currentTime_{ev}", i, round(sk["seekedAt"] * SR - sk["n"]) - (312 if "ps0" in f else 0), sk["n"] >= L)
        q = os.path.join(RES, f"seek_blender_{s}.json")
        if os.path.exists(q):
            for f, a in json.load(open(q))["files"].items():
                L = files[f]["pyav"]["samples"]
                for i, sk in enumerate(a["seeks"]):
                    add(f, "blender_aud", i, sk.get("error_samples"), sk["n"] >= L)
        out = os.path.join(RES, f"summary_{s}.csv")
        with open(out, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["file", "reader", "targets_in_range", "landed_in_range", "min", "max", "median", "exact", "within_1",
                        "near_end_targets", "near_min", "near_max", "near_landed", "past_end_targets", "past_landed"])
            for (f, r), v in rows.items():
                a, b = stats(v["inr"]), stats(v["near"])
                w.writerow([f, r, len(v["inr"]), a["n"], a.get("min"), a.get("max"), a.get("median"), a.get("exact"), a.get("within_1"),
                            len(v["near"]), b.get("min"), b.get("max"), b["n"], len(v["past"]), sum(1 for x in v["past"] if x is not None)])
        print("wrote", out)
        json.dump(facts(s, std), open(os.path.join(RES, f"facts_{s}.json"), "w"), indent=1)


def facts(s, std):
    """Per file: duration/length/strip as each reader reports it, load/open times, and what happens past the end."""
    out = {}
    for f, a in std["files"].items():
        L = a["pyav"]["samples"]
        past = [x for x in std["seeks"] if x["file"] == f and x["past_end"]]
        r = dict(L=L, csv_lead=a["csv"]["cover"] - L if a.get("csv") else None, ffprobe_duration_minus_L_ms=None if a["ffprobe"]["duration"] is None else round(float(a["ffprobe"]["duration"]) * 1000 - L / 48, 1),
                 libvlc_length_minus_L_ms=a["libvlc"]["length_ms"] - round(L / 48), libvlc_seekable=a["libvlc"]["seekable"],
                 pyav_seek_s_max=max((x["pyav"].get("s", 0) for x in std["seeks"] if x["file"] == f), default=None),
                 ffmpeg_ss_s_max=max((x["ffmpeg_ss"].get("s", 0) for x in std["seeks"] if x["file"] == f), default=None),
                 vlc_open_s_max=max((x["vlc_set_time"].get("open_s", 0) for x in std["seeks"] if x["file"] == f), default=None),
                 past_end=[dict(target_minus_L=x["target"] - L, pyav=x["pyav"].get("nonzero_len", x["pyav"].get("error") or "no frames"),
                                ffmpeg=x["ffmpeg_ss"].get("nonzero_len"), vlc_set_time=dict(time_ms=x["vlc_set_time"].get("time_ms"), state=x["vlc_set_time"].get("state"), landed=x["vlc_set_time"].get("landed")),
                                vlc_start_time=dict(landed=x["vlc_start_time"].get("landed"), samples=x["vlc_start_time"].get("samples"))) for x in past])
        for ev in ("e35", "e45"):
            q = os.path.join(RES, f"seek_electron_{s}_{ev}.json")
            if not os.path.exists(q):
                continue
            e = json.load(open(q))["files"].get(f, {})
            wc, el, d = e.get("wc", {}), e.get("el", {}), e.get("decodeAudioData", {})
            idx_end = None if wc.get("indexedEndUntrimmed") is None else wc["indexedEndUntrimmed"] - (wc.get("preskip") or 0) - L
            r[ev] = dict(wc_load_ms=wc.get("loadMs"), wc_error=wc.get("loadError") or wc.get("skipped"), wc_index_end_minus_L=idx_end,
                         wc_errors=sorted({x.get("error") or x.get("decoderError") for x in wc.get("seeks", []) if x.get("error") or x.get("decoderError")}),
                         wc_past_end=[dict(n_minus_L=x["n"] - L, error=x.get("error"), nonzero_len=x.get("nonzero_len")) for x in wc.get("seeks", []) if x["n"] >= L],
                         wc_end_vs_decoded=sorted({x.get("end_vs_decoded") for x in wc.get("seeks", []) if x["n"] < L and x.get("end_vs_decoded") is not None and x["n"] + 96000 > L}),
                         dad_ms=d.get("ms"), dad_length_minus_L=d.get("length_minus_pyav"), dad_click_offsets=d.get("clickOffsets"), dad_error=d.get("error"),
                         el_meta_ms=el.get("metaMs"), el_duration_minus_L_ms=None if el.get("duration") is None else round(el["duration"] * 1000 - L / 48, 1),
                         el_seekable_end_minus_L_ms=None if el.get("seekableEnd") is None else round(el["seekableEnd"] * 1000 - L / 48, 1),
                         el_play_to_end=el.get("playToEnd"), el_error=el.get("error"), el_seek_ms_max=max((x["ms"] for x in el.get("seeks", [])), default=None),
                         el_past_end=[dict(n_minus_L=x["n"] - L, seekedAt_minus_L_ms=round(x["seekedAt"] * 1000 - L / 48, 1)) for x in el.get("seeks", []) if x["n"] >= L])
        q = os.path.join(RES, f"seek_blender_{s}.json")
        if os.path.exists(q):
            b = json.load(open(q))["files"].get(f, {})
            r["blender"] = dict(aud_samples_minus_L=None if b.get("aud_samples") is None else b["aud_samples"] - L, aud_error=b.get("aud_error"),
                                vse_frames=b.get("vse_frame_final_duration"), vse_expected=b.get("vse_expected_frames"), full_decode_s=b.get("aud_full_decode_s"),
                                seek_s_max=max((x.get("s", 0) for x in b.get("seeks", [])), default=None),
                                past_end=[dict(n_minus_L=x["n"] - L, samples=x.get("samples"), error=x.get("error")) for x in b.get("seeks", []) if x["n"] >= L])
        out[f] = r
    return out


if __name__ == "__main__":
    main()
