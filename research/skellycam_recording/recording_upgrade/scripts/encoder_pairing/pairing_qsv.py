r"""T-S6 part 1: mjpeg_qsv through PyAV with synthetic barcode frames.

(a) probe: packets per encode() call, lateness, what packet.pts/dts carry back, encode(None), copy_opaque,
    ns time base round trip, async_depth 1/2/4(default)/8.
(b) pairing: full writer (eplib.PairingWriter) + verify, 720p and 1080p, gap patterns, irregular timing.

Run: <phase1 venv>\python.exe -I pairing_qsv.py
"""
from __future__ import annotations

import json
import random
import sys
import time
from collections import Counter
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import av  # noqa: E402
import numpy as np  # noqa: E402

import eplib as E  # noqa: E402


def probe() -> dict:
    out = {}
    src = {s: E.FrameSource(s) for s in E.DIMS}
    for size in E.DIMS:
        for ad in (None, 1, 2, 8):
            enc = E.QsvEnc(size, async_depth=ad)
            per_call, packets = [], []
            for seq in range(20):
                res = enc.submit(seq, src[size].frame(seq), E.make_meta(seq))
                per_call.append(len(res))
                packets += [(o.seq, o.late_calls) for o in res]
            fl = enc.flush()
            key = f"{size}_ad{ad if ad else 'default4'}"
            lates = Counter(l for _, l in packets)
            out[key] = {"packets_per_call": per_call, "late_calls_hist": dict(lates), "flush_packets": len(fl),
                        "flush_seqs": [o.seq for o in fl], "fifo_violations": enc.fifo_violations,
                        "unknown_pts": enc.unknown_pts, "total_out": len(packets) + len(fl)}
            # encode(None) again, then encode a frame after flush
            try:
                again = list(enc.cc.encode(None))
                out[key]["second_flush"] = f"returned {len(again)} packets"
            except Exception as ex:  # noqa: BLE001
                out[key]["second_flush"] = f"{type(ex).__name__}: {ex}"[:160]
            try:
                f = E.av_frame_yuyv(src[size].frame(99), *E.DIMS[size])
                f.pts = 99
                r = list(enc.cc.encode(f))
                out[key]["encode_after_flush"] = f"returned {len(r)} packets"
            except Exception as ex:  # noqa: BLE001
                out[key]["encode_after_flush"] = f"{type(ex).__name__}: {ex}"[:160]
    # packet fields
    enc = E.QsvEnc("720p")
    fields = []
    s7 = E.FrameSource("720p")
    for seq in range(6):
        f = E.av_frame_yuyv(s7.frame(seq), 1280, 720)
        f.pts = seq * 10 + 3
        for p in enc.cc.encode(f):
            fields.append({"pts": p.pts, "dts": p.dts, "duration": p.duration, "time_base": str(p.time_base),
                           "is_keyframe": p.is_keyframe, "opaque": repr(p.opaque), "size": p.size})
    for p in enc.cc.encode(None):
        fields.append({"pts": p.pts, "dts": p.dts, "duration": p.duration, "time_base": str(p.time_base),
                       "is_keyframe": p.is_keyframe, "opaque": repr(p.opaque), "size": p.size, "from": "flush"})
    out["packet_fields_input_pts_3_13_23_33_43_53"] = fields
    # ns time base: pts = arrival_ns
    enc = E.QsvEnc("720p", pts_mode="arrival", tb=Fraction(1, 1_000_000_000))
    sent, back = [], []
    for seq in range(12):
        m = E.make_meta(seq)
        sent.append(m["arrival_ns"])
        f = E.av_frame_yuyv(s7.frame(seq), 1280, 720)
        f.pts = m["arrival_ns"]
        back += [p.pts for p in enc.cc.encode(f)]
    back += [p.pts for p in enc.cc.encode(None)]
    out["ns_time_base"] = {"sent": sent, "back": back, "exact": sum(a == b for a, b in zip(sent, back)),
                           "max_abs_err_ns": max(abs(a - b) for a, b in zip(sent, back)),
                           "note": "qsvenc rescales pts to 90 kHz and back (qsvenc.c:2117, :2669)"}
    # copy_opaque
    try:
        cc = av.CodecContext.create("mjpeg_qsv", "w")
        cc.width, cc.height, cc.pix_fmt = 1280, 720, "yuyv422"
        cc.time_base, cc.framerate = E.TB, Fraction(30)
        cc.copy_opaque = True
        cc.open()
        out["copy_opaque_open"] = "opened"
    except Exception as ex:  # noqa: BLE001
        out["copy_opaque_open"] = f"{type(ex).__name__}: {ex}"[:200]
    return out


def enc_out_all(a, b):
    return list(a) + list(b)


def gap_pattern(name: str, n: int, seed: int = 3) -> list[int]:
    rnd = random.Random(seed)
    sfns, s = [], 0
    if name == "none":
        return list(range(n))
    if name == "periodic":
        while len(sfns) < n:
            if s % 7 != 6:
                sfns.append(s)
            s += 1
        return sfns
    if name == "bursty":
        while len(sfns) < n:
            if rnd.random() < 0.03:
                s += rnd.randint(1, 10)
            sfns.append(s)
            s += 1
        return sfns
    if name == "switch":  # the gap pattern changes mid-stream
        while len(sfns) < n:
            k = len(sfns)
            if k < n // 4:
                pass
            elif k < n // 2:
                if rnd.random() < 0.05:
                    s += rnd.randint(1, 15)
            elif k < 3 * n // 4:
                if s % 3 == 2:
                    s += 1
            elif k == 3 * n // 4:
                s += 1000
            sfns.append(s)
            s += 1
        return sfns
    raise ValueError(name)


def run_pairing(size: str, pattern: str, async_depth, timing: str, pts_mode: str = "seq", n: int = 600) -> dict:
    irregular = timing == "irregular"
    name = f"qsv_{size}_{pattern}_{timing}_ad{async_depth or 'def'}_{pts_mode}"
    d = E.SCRATCH / "pairing"
    d.mkdir(parents=True, exist_ok=True)
    stem = d / name
    src = E.FrameSource(size)
    sfns = gap_pattern(pattern, n)
    enc = E.QsvEnc(size, async_depth=async_depth, pts_mode=pts_mode)
    w = E.PairingWriter(stem, *E.DIMS[size], enc.name)
    lates = Counter()
    lat_ms = []
    rnd = random.Random(11)
    t_next = time.perf_counter()
    t0 = time.perf_counter()
    for seq, sfn in enumerate(sfns):
        a = src.frame(sfn)
        if timing in ("paced", "irregular"):
            now = time.perf_counter()
            if t_next > now:
                time.sleep(t_next - now)
            step = 1 / E.FPS
            if irregular:
                step *= rnd.uniform(0.3, 1.7)
                if seq % 100 == 99:
                    step += 0.3  # a 300 ms camera stall
            t_next += step
        for o in enc.submit(seq, a, E.make_meta(sfn, irregular)):
            lates[o.late_calls] += 1
            lat_ms.append((o.t_out - o.t_submit) * 1000)
            w.write(o)
    fl = enc.flush()
    for o in fl:
        lat_ms.append((o.t_out - o.t_submit) * 1000)
        w.write(o)
    w.close()
    wall = time.perf_counter() - t0
    v = E.verify(stem, irregular)
    v["mkv_bytes"] = w.mkv.stat().st_size
    if not (size == "720p" and pattern == "switch" and timing == "irregular"):
        w.mkv.unlink()  # keep one example file; the rest is rebuildable
    lm = np.array(lat_ms)
    return {"name": name, "size": size, "pattern": pattern, "timing": timing, "async_depth": async_depth or 4,
            "pts_mode": pts_mode, "frames_in": len(sfns), "packets_out": w.count, "late_calls_hist": dict(lates),
            "flush_packets": len(fl), "fifo_violations": enc.fifo_violations, "unknown_pts": enc.unknown_pts,
            "submit_to_packet_ms_p50": round(float(np.percentile(lm, 50)), 2),
            "submit_to_packet_ms_max": round(float(lm.max()), 2), "wall_s": round(wall, 2), "verify": v}


def main():
    res = {"versions": {"python": sys.version.split()[0], "av": av.__version__, "ffmpeg": av.ffmpeg_version_info,
                        "numpy": np.__version__}, "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
    res["probe"] = probe()
    runs = []
    for size in ("720p", "1080p"):
        for pattern in ("none", "periodic", "bursty", "switch"):
            for ad in (None, 1):
                runs.append(run_pairing(size, pattern, ad, "unpaced"))
                print(runs[-1]["name"], runs[-1]["verify"]["all_pairs_ok"], runs[-1]["late_calls_hist"], flush=True)
        runs.append(run_pairing(size, "switch", None, "irregular", n=450))
        print(runs[-1]["name"], runs[-1]["verify"]["all_pairs_ok"], flush=True)
        runs.append(run_pairing(size, "bursty", None, "paced", n=300))
        print(runs[-1]["name"], runs[-1]["verify"]["all_pairs_ok"], flush=True)
    runs.append(run_pairing("720p", "bursty", None, "unpaced", pts_mode="sfn"))
    print(runs[-1]["name"], runs[-1]["verify"]["all_pairs_ok"], flush=True)
    res["pairing"] = runs
    res["summary"] = {"runs": len(runs), "all_pairs_ok": sum(r["verify"]["all_pairs_ok"] for r in runs),
                      "records": sum(r["verify"]["records"] for r in runs),
                      "frames_in": sum(r["frames_in"] for r in runs)}
    res["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    E.RESULTS.mkdir(parents=True, exist_ok=True)
    (E.RESULTS / "qsv_pairing.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps(res["summary"]))


if __name__ == "__main__":
    main()
