"""(h) Camera JPEG edge cases: generic_1080p (extra bytes before EOI) and frames with DHT stripped (UVC MJPEG may omit DHT).

1. Decode raw bytes with cv2.imdecode, Pillow, PyAV (FFmpeg mjpeg decoder), djpeg.exe (libjpeg-turbo 3.2.1); record errors/warnings
   and whether DHT-stripped frames decode to the same pixels as the originals (same decoder).
2. Compare the cameras' DHT tables with the standard tables FFmpeg's mjpeg2jpeg bsf inserts (ITU-T T.81 Annex K tables).
3. Store stripped frames in each container (PyAV packets, no transcode), read back with the full reader suite
   (byte-exact, decode, cv2) and compare cv2-decoded pixels with the same container built from the original frames.
4. What mjpeg2jpeg does to camera frames with and without DHT.

Run (repo root):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/edge_cases.py --djpeg <scratchpad>/jpeg_passthrough/ljt321/bin/djpeg.exe
Writes results/jpeg_passthrough/edge_cases.json
"""
from __future__ import annotations

import argparse
import hashlib
import io as _io
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import jp_common as C  # noqa: E402
import jp_io as io  # noqa: E402
from mux_matrix import compare, run_reader_suite  # noqa: E402


def parse_dht(b: bytes) -> dict:
    tabs = {}
    for name, off, ln, _ in C.segments(b)["markers"]:
        if name != "DHT":
            continue
        p = off + 4
        end = off + ln
        while p < end:
            tc_th = b[p]
            bits = list(b[p + 1:p + 17])
            n = sum(bits)
            vals = list(b[p + 17:p + 17 + n])
            tabs[f"class{tc_th >> 4}_id{tc_th & 15}"] = (bits, vals)
            p += 17 + n
    return tabs


def decoders(b: bytes, djpeg: str) -> dict:
    import av
    import cv2
    import numpy as np
    from PIL import Image
    out = {}
    a = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)
    out["cv2_imdecode"] = {"ok": a is not None, "sha": hashlib.sha1(a.tobytes()).hexdigest() if a is not None else None}
    try:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            im = Image.open(_io.BytesIO(b))
            im.load()
            arr = np.asarray(im.convert("RGB"))
        out["pillow"] = {"ok": True, "sha": hashlib.sha1(arr.tobytes()).hexdigest(), "warnings": [str(x.message)[:120] for x in w][:3]}
    except Exception as e:  # noqa: BLE001
        out["pillow"] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:160]}
    try:
        cc = av.CodecContext.create("mjpeg", "r")
        frs = cc.decode(av.Packet(b))
        if not frs:
            frs = cc.decode(None)
        fr = frs[0]
        arr = fr.to_ndarray(format="rgb24")
        out["pyav_mjpeg"] = {"ok": True, "sha": hashlib.sha1(arr.tobytes()).hexdigest(), "pix_fmt": fr.format.name}
    except Exception as e:  # noqa: BLE001
        out["pyav_mjpeg"] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:160]}
    p = subprocess.run([djpeg, "-ppm"], input=b, capture_output=True)
    out["djpeg_3.2.1"] = {"ok": p.returncode == 0 and len(p.stdout) > 0, "rc": p.returncode,
                          "stderr": p.stderr.decode("latin1").strip()[:160], "sha": hashlib.sha1(p.stdout).hexdigest() if p.stdout else None}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--djpeg", required=True)
    ap.add_argument("--n", type=int, default=30)
    a = ap.parse_args()
    import PIL
    import av
    import cv2
    res = {"meta": {"date": time.strftime("%Y-%m-%dT%H:%M:%S"), "pyav": av.__version__, "opencv": cv2.__version__, "pillow": PIL.__version__,
                    "djpeg": a.djpeg}}
    sets = {"c930e_720p_flash": C.load_set("c930e_720p_flash", a.n), "c922_720p_flash": C.load_set("c922_720p_flash", a.n),
            "generic_1080p": C.load_set("generic_1080p")}
    # 1. decoders on raw bytes
    dec = {}
    for s, frames in sets.items():
        rows = []
        for k, f in enumerate(frames):
            o = decoders(f, a.djpeg)
            st = C.strip_dht(f)
            d2 = decoders(st, a.djpeg)
            row = {"k": k, "bytes": len(f), "stripped_bytes": len(st), "markers": C.marker_summary(f), "stripped_markers": C.marker_summary(st)}
            for dn in o:
                row[dn] = {"orig_ok": o[dn]["ok"], "stripped_ok": d2[dn]["ok"],
                           "stripped_pixels_equal_orig": o[dn].get("sha") is not None and o[dn].get("sha") == d2[dn].get("sha"),
                           "orig_msg": o[dn].get("stderr") or o[dn].get("warnings") or o[dn].get("error"),
                           "stripped_msg": d2[dn].get("stderr") or d2[dn].get("warnings") or d2[dn].get("error")}
            rows.append(row)
        dec[s] = {"rows": rows, "summary": {dn: {"orig_ok": sum(r[dn]["orig_ok"] for r in rows), "stripped_ok": sum(r[dn]["stripped_ok"] for r in rows),
                                                 "stripped_equal": sum(r[dn]["stripped_pixels_equal_orig"] for r in rows), "n": len(rows)}
                                            for dn in ("cv2_imdecode", "pillow", "pyav_mjpeg", "djpeg_3.2.1")}}
        print(s, dec[s]["summary"], flush=True)
    res["decoders"] = dec
    # 2. camera DHT vs standard (mjpeg2jpeg-inserted) DHT
    tmp = Path(tempfile.mkdtemp(dir=C.TEMP, prefix="edge_"))
    std = None
    bsf_rows = {}
    for s, frames in sets.items():
        for variant, fr in (("orig", frames[:5]), ("stripped", [C.strip_dht(x) for x in frames[:5]])):
            mk = tmp / f"{s}_{variant}.mkv"
            w, h = C.index()[s]["width"], C.index()[s]["height"]
            io.pyav_write(mk, "mkv", fr, w, h, None)
            fx = io.ffmpeg_extract(mk, bsf="mjpeg2jpeg")
            first = fx["first"]
            bsf_rows[f"{s}|{variant}"] = {"rc": fx["returncode"], "n": fx["n"], "in_markers": C.marker_summary(fr[0]),
                                          "out_markers": C.marker_summary(first) if first else None,
                                          "out_bytes_minus_in": (len(first) - len(fr[0])) if first else None,
                                          "decoders_out": {k: v["ok"] for k, v in decoders(first, a.djpeg).items()} if first else None}
            if first and variant == "stripped" and std is None:
                std = parse_dht(first)
    cam = {s: parse_dht(fr[0]) for s, fr in sets.items()}
    res["dht_vs_standard"] = {s: {k: (k in std and std[k] == v) for k, v in t.items()} for s, t in cam.items()}
    res["dht_tables_count"] = {s: len(t) for s, t in cam.items()}
    res["mjpeg2jpeg"] = bsf_rows
    print("dht_vs_standard", res["dht_vs_standard"], flush=True)
    # 3. stripped frames through containers
    ctab = {}
    s = "c930e_720p_flash"
    frames = sets[s]
    stripped = [C.strip_dht(x) for x in frames]
    ts = C.real_timestamps_ns(s, C.load_set(s))[: len(frames)]
    us = [(t - ts[0]) // 1000 for t in ts]
    d = C.MEDIA / "edge_cases"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    for cont in ["mkv", "mp4", "fmp4_1s", "mov", "avi_tb_rate", "nut", "mjpeg_raw_mux"]:
        row = {}
        for variant, fr in (("orig", frames), ("stripped", stripped)):
            p = d / f"{variant}_{cont}{io.CONTAINERS[cont][1]}"
            vfr = cont != "avi_tb_rate"
            wr = io.pyav_write(p, cont, fr, 1280, 720, us if vfr else None)
            row[variant + "_write"] = wr.get("ok"), wr.get("error")
            if wr.get("ok"):
                exp = [u / 1e6 for u in us] if vfr else [k / 30 for k in range(len(fr))]
                rr = run_reader_suite(p, False, fr, exp, do_msmf=True)
                cv = io.cv2_read(p, "FFMPEG", None, seek=False)
                row[variant + "_cv2_hashes"] = cv.pop("_hashes", [])
                row[variant] = {"pyav_bytes": rr.get("pyav_bytes"), "ffx_bytes": rr.get("ffmpeg_extract_bytes"),
                                "pyav_decoded": rr.get("pyav", {}).get("decoded_frames"), "pyav_decode_errors": rr.get("pyav", {}).get("decode_error_count"),
                                "cv2_ffmpeg_frames": rr.get("cv2_ffmpeg", {}).get("frames_read"), "cv2_seek": f"{rr.get('cv2_ffmpeg', {}).get('seek_exact')}/{rr.get('cv2_ffmpeg', {}).get('seek_total')}",
                                "cv2_msmf_frames": rr.get("cv2_msmf", {}).get("frames_read"), "freemocap": rr.get("freemocap_videohelper")}
        oh, sh = row.pop("orig_cv2_hashes", []), row.pop("stripped_cv2_hashes", [])
        row["cv2_pixels_stripped_equal_orig"] = f"{sum(1 for x, y in zip(oh, sh) if x == y)}/{max(len(oh), len(sh))}"
        ctab[cont] = row
        print(cont, row["cv2_pixels_stripped_equal_orig"], row.get("stripped", {}).get("pyav_bytes"), flush=True)
    # sidecar + folder for stripped frames: python writers, byte-exact by construction; decode via cv2 folder reader
    p = d / "stripped_folder" / "frame_%06d.jpg"
    io.python_write(p, "jpg_folder", stripped, ts)
    rr = run_reader_suite(p, True, stripped, [u / 1e6 for u in us])
    ctab["jpg_folder"] = {"stripped": {"ffx_bytes": rr.get("ffmpeg_extract_bytes"), "pyav_decoded": rr.get("pyav", {}).get("decoded_frames"),
                                       "cv2_ffmpeg_frames": rr.get("cv2_ffmpeg", {}).get("frames_read"), "cv2_images_frames": rr.get("cv2_images", {}).get("frames_read")}}
    res["containers_stripped_c930e_720p"] = ctab
    shutil.rmtree(tmp, ignore_errors=True)
    C.write_json(C.RESULTS / "edge_cases.json", res)
    print("wrote", C.RESULTS / "edge_cases.json")


if __name__ == "__main__":
    main()
