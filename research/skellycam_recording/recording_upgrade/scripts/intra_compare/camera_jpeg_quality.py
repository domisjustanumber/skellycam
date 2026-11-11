# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "scipy==1.16.2", "simplejpeg==1.9.0"]
# ///
"""Camera passthrough reference (FUNCTIONAL, no timing).

1. For every corpus MJPEG set used by intra_compare: camera JPEG bytes/frame (= passthrough cost, no re-encode),
   the DQT tables of every frame (distinct table sets), and the IJG quality whose scaled Annex K tables are closest
   to the camera's (exact match flagged). IJG scaling (libjpeg jcparam.c jpeg_quality_scaling / jpeg_add_quant_table):
   scale = 5000/q (q<50) else 200-2q; entry = clamp((std*scale + 50)/100, 1, 255).
2. "Camera-equivalent quality on uncompressed frames": the same camera model's raw YUY2 1080p frames encoded by
   libjpeg-turbo (simplejpeg 1.9.0, 4:2:2 planes, full range) at that camera's IJG-equivalent quality; PSNR-Y/SSIM-Y
   vs the raw YUY2 (iclib.metrics, source domain = limited range). Used to justify the matched-quality target.
Writes results/intra_compare/camera_jpeg_quality.json and .md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import simplejpeg

sys.path.insert(0, str(Path(__file__).parent))
import iclib  # noqa: E402

# ITU-T T.81 Annex K tables K.1 (luminance) and K.2 (chrominance), natural (row-major) order
K1 = [16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55, 14, 13, 16, 24, 40, 57, 69, 56, 14, 17, 22, 29, 51,
      87, 80, 62, 18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92, 49, 64, 78, 87, 103, 121, 120, 101,
      72, 92, 95, 98, 112, 100, 103, 99]
K2 = [17, 18, 24, 47, 99, 99, 99, 99, 18, 21, 26, 66, 99, 99, 99, 99, 24, 26, 56, 99, 99, 99, 99, 99, 47, 66, 99, 99, 99,
      99, 99, 99] + [99] * 32
ZZ = [0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14, 21, 28,
      35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47,
      55, 62, 63]  # zigzag index -> natural index


def ijg_table(std: list[int], q: int) -> list[int]:
    s = 5000 // q if q < 50 else 200 - 2 * q
    return [min(255, max(1, (v * s + 50) // 100)) for v in std]


def dqt_tables(jb: bytes) -> dict[int, list[int]]:
    """Parse DQT segments before SOS; returns {table_id: 64 entries in natural order}."""
    out, i = {}, 2
    while i < len(jb) - 4:
        if jb[i] != 0xFF:
            break
        m = jb[i + 1]
        ln = int.from_bytes(jb[i + 2:i + 4], "big")
        if m == 0xDB:
            j = i + 4
            while j < i + 2 + ln:
                pq, tq = jb[j] >> 4, jb[j] & 15
                n = 64 * (2 if pq else 1)
                raw = jb[j + 1:j + 1 + n]
                vals = [int.from_bytes(raw[2 * k:2 * k + 2], "big") for k in range(64)] if pq else list(raw)
                nat = [0] * 64
                for z, v in enumerate(vals):
                    nat[ZZ[z]] = v
                out[tq] = nat
                j += 1 + n
        if m == 0xDA:
            break
        i += 2 + ln
    return out


def best_q(tab: list[int], std: list[int]) -> dict:
    errs = [(sum(abs(a - b) for a, b in zip(tab, ijg_table(std, q))), q) for q in range(1, 101)]
    e, q = min(errs)
    return {"q": q, "sum_abs_err": e, "exact": e == 0}


def main() -> None:
    sets = {"c930e_720p_flash": 120, "c922_720p_flash": 120, "c930e_1080p": 19, "c922_1080p": 19}
    rep: dict = {"sets": {}, "camera_equivalent_on_yuy2": []}
    for s, n in sets.items():
        files = sorted((iclib.CORPUS / s).glob("frame_*.jpg"))[:n]
        sizes = [p.stat().st_size for p in files]
        tabs = [dqt_tables(p.read_bytes()) for p in files]
        distinct = {json.dumps(t, sort_keys=True) for t in tabs}
        t0 = tabs[0]
        rec = {"frames": len(files), "bytes_per_frame_mean": round(float(np.mean(sizes)), 1),
               "bytes_per_frame_median": float(np.median(sizes)), "bytes_min": min(sizes), "bytes_max": max(sizes),
               "distinct_dqt_sets": len(distinct), "table_ids": sorted(t0)}
        if 0 in t0:
            rec["luma_ijg"] = best_q(t0[0], K1)
            rec["luma_table_first8"] = t0[0][:8]
        if 1 in t0:
            rec["chroma_ijg"] = best_q(t0[1], K2)
        rep["sets"][s] = rec
        print(s, rec)
    # camera-equivalent quality on the same camera model's raw YUY2 1080p frames
    srcs = iclib.load_input("yuy2_1080p")
    for cam, yset, jsets in (("c930e", "c930e_1080p_yuy2", ("c930e_1080p", "c930e_720p_flash")),
                             ("c922", "c922_1080p_yuy2", ("c922_1080p", "c922_720p_flash"))):
        qs = sorted({rep["sets"][j]["luma_ijg"]["q"] for j in jsets})
        for q in qs:
            per = []
            for s in [x for x in srcs if x.cam == yset]:
                planes = iclib.map_range([s.y, s.u, s.v], "lim", "full")
                jb = simplejpeg.encode_jpeg_yuv_planes(*[np.ascontiguousarray(p) for p in planes], quality=q)
                dec = __import__("av").CodecContext.create("mjpeg", "r")
                dp, _ = iclib.decode_jpeg(jb, dec)
                m = iclib.metrics(s, dp, "full")
                m["bytes"] = len(jb)
                per.append(m)
            r = {"camera": cam, "yuy2_set": yset, "ijg_q_from_camera_dqt": q, "frames": len(per),
                 **iclib.summarize(per)}
            rep["camera_equivalent_on_yuy2"].append(r)
            print(r)
    out = iclib.RESULTS / "camera_jpeg_quality.json"
    out.write_text(json.dumps(rep, indent=1))
    L = ["# Camera JPEG passthrough reference (intra_compare)", "",
         "Generated by `scripts/intra_compare/camera_jpeg_quality.py` (PyAV 19.0.2, simplejpeg 1.9.0 / libjpeg-turbo 3.1.2).", "",
         "| set | frames | bytes/frame mean | median | distinct DQT sets | luma IJG-equivalent q (exact?) | chroma IJG-equivalent q (exact?) |",
         "|---|---|---|---|---|---|---|"]
    for s, r in rep["sets"].items():
        L.append(f"| {s} | {r['frames']} | {r['bytes_per_frame_mean']} | {r['bytes_per_frame_median']} | {r['distinct_dqt_sets']} | "
                 f"{r.get('luma_ijg', {}).get('q')} ({r.get('luma_ijg', {}).get('exact')}, err {r.get('luma_ijg', {}).get('sum_abs_err')}) | "
                 f"{r.get('chroma_ijg', {}).get('q')} ({r.get('chroma_ijg', {}).get('exact')}, err {r.get('chroma_ijg', {}).get('sum_abs_err')}) |")
    L += ["", "## libjpeg-turbo at the camera-equivalent q on the same camera's raw YUY2 1080p frames (4:2:2)", "",
          "| camera | YUY2 set | q | frames | bytes/frame | PSNR-Y mean (min) | SSIM-Y mean (min) | PSNR-YUV 4:2:2 |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rep["camera_equivalent_on_yuy2"]:
        L.append(f"| {r['camera']} | {r['yuy2_set']} | {r['ijg_q_from_camera_dqt']} | {r['frames']} | {r['bytes_per_frame']} | "
                 f"{r['psnr_y']} ({r['psnr_y_min']}) | {r['ssim_y']} ({r['ssim_y_min']}) | {r['psnr_yuv_422']} |")
    (iclib.RESULTS / "camera_jpeg_quality.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
