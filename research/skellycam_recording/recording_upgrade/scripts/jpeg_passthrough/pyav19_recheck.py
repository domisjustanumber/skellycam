# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy"]
# ///
"""PyAV 19.0.2 functional re-check of the jpeg_passthrough results that were made with PyAV 18.0.0 (FINDINGS step, 2026-11-09).

No timing is measured. Everything is functional (bytes, timestamps, flags, errors).

A) Byte-exactness + timestamp error, all 7 MJPEG corpus sets, VFR (real / borrowed intervals) and CFR, written IN MEMORY
   (io.BytesIO, so no media lands on disk), every container incl. the new fMP4 variants with stream time_base 1/1e6.
B) fMP4 (1 s and per-frame fragments) with stream time_base 1/1e6 on c930e_720p_flash VFR written to the media folder,
   then inspected with ffprobe (pts_time, nb_frames, packet count). Files deleted afterwards.
C) Hard kill: child process (this same uv env, PyAV 19.0.2) muxes 600 c930e_720p_flash frames and calls os._exit(1)
   without closing; PyAV 19.0.2 demux counts packets and the byte-exact prefix. Files deleted afterwards.
D) Setup details on PyAV 19.0.2: add_mux_stream without width/height, is_keyframe=False, add_stream_from_template
   (mp4/mov/avi), DHT-stripped frames byte-exact.

Run (repo root):
  uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/pyav19_recheck.py
Writes results/jpeg_passthrough/pyav19_recheck.json
"""
from __future__ import annotations

import io as pyio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import jp_common as C  # noqa: E402

# name -> (format, ext, muxer options, stream time_base: None | "rate" | "us")
FRAG1S = {"movflags": "frag_keyframe+empty_moov+default_base_moof", "min_frag_duration": "1000000"}
FRAGPF = {"movflags": "frag_keyframe+empty_moov+default_base_moof"}
CONTS = {
    "mkv": ("matroska", ".mkv", {}, None),
    "webm": ("webm", ".webm", {}, None),
    "mp4": ("mp4", ".mp4", {}, None),
    "mp4_tb_us": ("mp4", ".mp4", {}, "us"),
    "fmp4_1s": ("mp4", ".mp4", FRAG1S, None),
    "fmp4_1s_tb_us": ("mp4", ".mp4", FRAG1S, "us"),
    "fmp4_perframe": ("mp4", ".mp4", FRAGPF, None),
    "fmp4_perframe_tb_us": ("mp4", ".mp4", FRAGPF, "us"),
    "mov": ("mov", ".mov", {}, None),
    "mov_tb_us": ("mov", ".mov", {}, "us"),
    "avi": ("avi", ".avi", {}, None),
    "avi_tb_rate": ("avi", ".avi", {}, "rate"),
    "nut": ("nut", ".nut", {}, None),
    "nut_tb_us": ("nut", ".nut", {}, "us"),
    "mjpeg_raw_mux": ("mjpeg", ".mjpeg", {}, None),
}
DATASETS = {"c930e_720p_flash": ("real", 30), "c922_720p_flash": ("real", 30), "c922_1080p": ("borrowed", 30),
            "c930e_1080p": ("borrowed", 30), "c922_1600x896": ("borrowed", 30), "c922_720p60": ("borrowed_half", 60),
            "generic_1080p": ("borrowed", 30)}
MEDIA = C.MEDIA / "pyav19_recheck"
TEMP = Path("C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/jpeg_passthrough")
KILL_CONTS = ["mkv", "mp4", "fmp4_1s", "fmp4_1s_tb_us", "fmp4_perframe", "mov", "avi_tb_rate", "nut", "mjpeg_raw_mux"]


def write(target, cont: str, frames: list[bytes], w: int, h: int, pts_us: list[int] | None, rate: int,
          setup: str = "mux_stream", keyframe: bool = True, tmpl_path: Path | None = None) -> dict:
    import av
    fmt, _, opts, stb = CONTS[cont]
    r = {"ok": False}
    c = None
    tmpl = None
    try:
        c = av.open(target, "w", format=fmt, options=dict(opts))
        if setup == "mux_stream":
            st = c.add_mux_stream("mjpeg", rate=rate, width=w, height=h)
        elif setup == "nodims":
            st = c.add_mux_stream("mjpeg", rate=rate)
        elif setup == "template":
            tmpl = av.open(str(tmpl_path))
            st = c.add_stream_from_template(tmpl.streams.video[0])
        else:
            raise ValueError(setup)
        if stb == "rate":
            st.time_base = Fraction(1, rate)
        elif stb == "us":
            st.time_base = Fraction(1, 1_000_000)
        ptb = Fraction(1, rate) if pts_us is None else Fraction(1, 1_000_000)
        for k, fb in enumerate(frames):
            p = av.Packet(fb)
            p.stream = st
            p.time_base = ptb
            p.pts = p.dts = k if pts_us is None else pts_us[k]
            p.is_keyframe = keyframe
            c.mux(p)
            if k == 0:
                r["stream_tb"] = str(st.time_base)
        c.close()
        c = None
        r["ok"] = True
    except Exception as e:  # noqa: BLE001
        r["error"] = f"{type(e).__name__}: {e}"[-220:]
        try:
            if c is not None:
                c.close()
        except Exception:  # noqa: BLE001
            pass
    finally:
        if tmpl is not None:
            tmpl.close()
    return r


def demux(src, fmt: str | None = None) -> dict:
    import av
    out = {"ok": False}
    try:
        with av.open(src, format=fmt) as c:
            st = c.streams.video[0]
            shas, pts, kf = [], [], 0
            for pkt in c.demux(st):
                if pkt.size == 0:
                    continue
                shas.append(C.sha(bytes(pkt)))
                pts.append(None if pkt.pts is None else float(pkt.pts * pkt.time_base))
                kf += bool(pkt.is_keyframe)
            out.update(ok=True, shas=shas, pts_s=pts, keyframe_flagged=kf, time_base=str(st.time_base))
    except Exception as e:  # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"[-220:]
    return out


def compare(out_shas, in_shas) -> dict:
    pre = 0
    for a, b in zip(out_shas, in_shas):
        if a != b:
            break
        pre += 1
    return {"n_out": len(out_shas), "n_in": len(in_shas), "exact_prefix": pre,
            "byte_exact_all": len(out_shas) == len(in_shas) and pre == len(in_shas)}


def ts_err(got, exp) -> dict | None:
    g = [x for x in got if x is not None]
    if len(g) < 2:
        return None
    n = min(len(g), len(exp))
    errs = [abs((g[i] - g[0]) - (exp[i] - exp[0])) * 1e6 for i in range(n)]
    return {"n": n, "max_abs_err_us": round(max(errs), 3), "strictly_increasing": all(b > a for a, b in zip(g, g[1:]))}


def dataset_ts(name: str, frames: list[bytes]) -> list[int]:
    kind, _ = DATASETS[name]
    if kind == "real":
        ts = C.real_timestamps_ns(name, frames)
        return [(t - ts[0]) // 1000 for t in ts]
    ns = C.jitter_timestamps_ns(len(frames))
    if kind == "borrowed_half":
        ns = [t // 2 for t in ns]
    return [t // 1000 for t in ns]


def child(cont: str, path: str, k: int) -> None:
    import av
    name = "c930e_720p_flash"
    allf = C.load_set(name)
    us = dataset_ts(name, allf)[:k]
    frames = allf[:k]
    fmt, _, opts, stb = CONTS[cont]
    c = av.open(path, "w", format=fmt, options=dict(opts))
    st = c.add_mux_stream("mjpeg", rate=30, width=1280, height=720)
    vfr = stb != "rate"
    if stb == "rate":
        st.time_base = Fraction(1, 30)
    elif stb == "us":
        st.time_base = Fraction(1, 1_000_000)
    for i, fb in enumerate(frames):
        p = av.Packet(fb)
        p.stream = st
        p.time_base = Fraction(1, 1_000_000) if vfr else Fraction(1, 30)
        p.pts = p.dts = us[i] if vfr else i
        p.is_keyframe = True
        c.mux(p)
    os._exit(1)


def ffprobe(path: Path) -> dict:
    cmd = ["ffprobe", "-v", "error", "-count_packets", "-show_streams", "-show_entries", "packet=pts_time,size", "-of", "json", str(path)]
    p = subprocess.run(cmd, capture_output=True)
    out = {"returncode": p.returncode, "stderr": p.stderr.decode("utf8", "replace").strip()[:300]}
    if p.returncode == 0:
        j = json.loads(p.stdout)
        s = [x for x in j.get("streams", []) if x.get("codec_type") == "video"][0]
        out.update({k: s.get(k) for k in ("codec_name", "codec_tag_string", "time_base", "nb_frames", "nb_read_packets", "avg_frame_rate")})
        out["pts_time"] = [float(x["pts_time"]) for x in j.get("packets", []) if int(x.get("size", 0)) > 0 and x.get("pts_time") not in (None, "N/A")]
    return out


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        child(sys.argv[2], sys.argv[3], int(sys.argv[4]))
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--write-fmp4-us":
        # write c930e_720p_flash VFR fMP4 (1 s and per-frame) with stream time_base 1/1e6 into DIR, for the
        # OpenCV 4.12 / FreeMoCap reader check (fmp4_tb_us_cv2_check.py, run with the skellycam .venv, read-only)
        out = Path(sys.argv[2])
        out.mkdir(parents=True, exist_ok=True)
        fr = C.load_set("c930e_720p_flash")
        u = dataset_ts("c930e_720p_flash", fr)
        for cont in ("fmp4_1s_tb_us", "fmp4_perframe_tb_us"):
            print(cont, write(str(out / f"{cont}.mp4"), cont, fr, 1280, 720, u, 30))
        return
    import av
    av.logging.set_level(av.logging.ERROR)
    TEMP.mkdir(parents=True, exist_ok=True)
    res = {"meta": {"date": time.strftime("%Y-%m-%dT%H:%M:%S"), "pyav": av.__version__,
                    "pyav_ffmpeg_libs": {k: ".".join(map(str, v)) for k, v in av.library_versions.items()},
                    "python": sys.version.split()[0], "note": "functional only; no timing"},
           "A_matrix": {}, "B_fmp4_tb_us_ffprobe": {}, "C_killed": {}, "D_setup": {}}
    idx = C.index()

    # A) in-memory matrix
    for name, (_, rate) in DATASETS.items():
        frames = C.load_set(name)
        w, h = idx[name]["width"], idx[name]["height"]
        in_shas = [C.sha(f) for f in frames]
        us = dataset_ts(name, frames)
        for cont in CONTS:
            for mode in ("vfr", "cfr"):
                buf = pyio.BytesIO()
                wr = write(buf, cont, frames, w, h, us if mode == "vfr" else None, rate)
                row = {"write_ok": wr["ok"], "error": wr.get("error"), "stream_tb": wr.get("stream_tb")}
                if wr["ok"]:
                    buf.seek(0)
                    d = demux(buf, CONTS[cont][0])
                    if d["ok"]:
                        exp = [u / 1e6 for u in us] if mode == "vfr" else [k / rate for k in range(len(frames))]
                        row["bytes"] = compare(d["shas"], in_shas)
                        row["ts"] = ts_err(d["pts_s"], exp)
                        row["keyframe_flagged"] = d["keyframe_flagged"]
                        row["demux_time_base"] = d["time_base"]
                    else:
                        row["demux_error"] = d["error"]
                    row["size_bytes"] = buf.getbuffer().nbytes
                res["A_matrix"][f"{name}|{cont}|{mode}"] = row
        print("A done", name, flush=True)

    name = "c930e_720p_flash"
    frames = C.load_set(name)
    in_shas = [C.sha(f) for f in frames]
    us = dataset_ts(name, frames)
    if MEDIA.exists():
        shutil.rmtree(MEDIA)
    MEDIA.mkdir(parents=True)

    # B) fMP4 1/1e6 on disk -> ffprobe
    for cont in ("fmp4_1s_tb_us", "fmp4_perframe_tb_us"):
        p = MEDIA / f"{cont}.mp4"
        wr = write(str(p), cont, frames, 1280, 720, us, 30)
        r = {"write": wr}
        fp = ffprobe(p)
        pts = fp.pop("pts_time", [])
        r["ffprobe"] = fp
        r["ffprobe_ts"] = ts_err(pts, [u / 1e6 for u in us])
        res["B_fmp4_tb_us_ffprobe"][cont] = r
    print("B done", flush=True)

    # C) hard kill
    for cont in KILL_CONTS:
        p = MEDIA / f"killed_{cont}{CONTS[cont][1]}"
        cp = subprocess.run([sys.executable, __file__, "--child", cont, str(p), "600"], capture_output=True)
        r = {"child_rc": cp.returncode, "bytes": p.stat().st_size if p.exists() else None}
        d = demux(str(p))
        if d["ok"]:
            r["pyav"] = compare(d["shas"], in_shas[:600])
        else:
            r["pyav_error"] = d["error"]
        fp = ffprobe(p)
        fp.pop("pts_time", None)
        r["ffprobe"] = {k: fp.get(k) for k in ("returncode", "nb_frames", "nb_read_packets", "stderr")}
        res["C_killed"][cont] = r
    print("C done", flush=True)
    shutil.rmtree(MEDIA, ignore_errors=True)

    # D) setup details (30 frames, in memory)
    f30 = frames[:30]
    s30 = in_shas[:30]
    tmpl_dir = Path(tempfile.mkdtemp(dir=TEMP, prefix="tmpl_"))
    tp = tmpl_dir / "t.jpg"
    tp.write_bytes(f30[0])
    for cont in ("mkv", "mp4", "mov", "avi", "nut", "mjpeg_raw_mux"):
        for setup, kf in (("nodims", True), ("mux_stream", False), ("template", True)):
            buf = pyio.BytesIO()
            wr = write(buf, cont, f30, 1280, 720, None, 30, setup=setup, keyframe=kf, tmpl_path=tp)
            row = {"write_ok": wr["ok"], "error": wr.get("error"), "stream_tb": wr.get("stream_tb")}
            if wr["ok"]:
                buf.seek(0)
                d = demux(buf, CONTS[cont][0])
                if d["ok"]:
                    row["bytes"] = compare(d["shas"], s30)
                    row["keyframe_flagged"] = d["keyframe_flagged"]
            res["D_setup"][f"{cont}|{setup}|kf={kf}"] = row
    # D2) template with VFR us timestamps, written to a FILE (the PyAV 18 keyframe_check.py setup), then PyAV + ffprobe
    us30 = us[:30]
    MEDIA.mkdir(parents=True, exist_ok=True)
    for cont in ("mp4", "mov", "avi", "mkv", "nut"):
        p = MEDIA / f"template_vfr_{cont}{CONTS[cont][1]}"
        wr = write(str(p), cont, f30, 1280, 720, us30, 30, setup="template", tmpl_path=tp)
        row = {"write_ok": wr["ok"], "error": wr.get("error"), "stream_tb": wr.get("stream_tb")}
        if wr["ok"]:
            d = demux(str(p))
            if d["ok"]:
                row["bytes"] = compare(d["shas"], s30)
            fp = ffprobe(p)
            fp.pop("pts_time", None)
            row["ffprobe_nb_read_packets"] = fp.get("nb_read_packets")
        res["D_setup"][f"{cont}|template_vfr_file"] = row
    shutil.rmtree(MEDIA, ignore_errors=True)
    shutil.rmtree(tmpl_dir, ignore_errors=True)
    stripped = [C.strip_dht(f) for f in f30]
    ss = [C.sha(f) for f in stripped]
    for cont in ("mkv", "mp4", "fmp4_1s", "mov", "avi_tb_rate", "nut", "mjpeg_raw_mux"):
        buf = pyio.BytesIO()
        wr = write(buf, cont, stripped, 1280, 720, None, 30)
        row = {"write_ok": wr["ok"], "error": wr.get("error")}
        if wr["ok"]:
            buf.seek(0)
            d = demux(buf, CONTS[cont][0])
            if d["ok"]:
                row["bytes"] = compare(d["shas"], ss)
        res["D_setup"][f"{cont}|dht_stripped"] = row
    print("D done", flush=True)

    # E) PyAV 19.0.2 mjpeg decoder: original vs DHT-stripped frames decode to identical pixels (30 / 30 / 11 frames)
    import numpy as np
    res["E_decode_dht_stripped"] = {}
    for dname, n in (("c930e_720p_flash", 30), ("c922_720p_flash", 30), ("generic_1080p", 11)):
        fr = C.load_set(dname, n)
        row = {"n": len(fr), "orig_ok": 0, "stripped_ok": 0, "pixels_equal": 0, "errors": []}
        for fb in fr:
            outs = []
            for b in (fb, C.strip_dht(fb)):
                try:
                    cc = av.CodecContext.create("mjpeg", "r")
                    frs = cc.decode(av.Packet(b)) + cc.decode(None)
                    outs.append(frs[0].to_ndarray(format="rgb24") if frs else None)
                except Exception as e:  # noqa: BLE001
                    outs.append(None)
                    row["errors"].append(f"{type(e).__name__}: {e}"[:120])
            row["orig_ok"] += outs[0] is not None
            row["stripped_ok"] += outs[1] is not None
            row["pixels_equal"] += bool(outs[0] is not None and outs[1] is not None and np.array_equal(outs[0], outs[1]))
        row["errors"] = row["errors"][:3]
        res["E_decode_dht_stripped"][dname] = row
    print("E done", res["E_decode_dht_stripped"], flush=True)

    out = C.RESULTS / "pyav19_recheck.json"
    C.write_json(out, res)
    print("wrote", out)


if __name__ == "__main__":
    main()
