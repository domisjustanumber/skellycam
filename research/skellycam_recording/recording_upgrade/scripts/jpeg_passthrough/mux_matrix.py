"""Functional matrix: camera JPEG bytes -> container (no transcode) -> read back by every reader.

Answers topic questions (a) write, (b) byte-exactness, (c) header changes, (d) readability + cv2 seek, (e) timestamps.
No timing is measured. Media goes to C:/Users/Dom/Documents/skellycam-raw/.../jpeg_passthrough/mux_matrix/ (never the repo).

Run (repo root):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/mux_matrix.py [--sets a,b] [--keep]
Writes results/jpeg_passthrough/mux_matrix.json and mux_matrix.md.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import jp_common as C  # noqa: E402
import jp_io as io  # noqa: E402

# set -> (n frames or None = all, timestamp source, rate)
DATASETS = {
    "c930e_720p_flash": (None, "real", 30),
    "c922_720p_flash": (None, "real", 30),
    "c922_1080p": (None, "borrowed", 30),
    "c930e_1080p": (None, "borrowed", 30),
    "c922_1600x896": (None, "borrowed", 30),
    "c922_720p60": (None, "borrowed_half", 60),
    "generic_1080p": (None, "borrowed", 30),
}


def compare(out_shas: list[str], in_shas: list[str]) -> dict:
    n = min(len(out_shas), len(in_shas))
    m = [i for i in range(n) if out_shas[i] == in_shas[i]]
    first_mis = next((i for i in range(n) if out_shas[i] != in_shas[i]), None)
    return {"n_out": len(out_shas), "n_in": len(in_shas), "in_order_matches": len(m),
            "byte_exact_all": len(out_shas) == len(in_shas) and len(m) == len(in_shas), "first_mismatch": first_mis}


def ts_err(got: list, exp: list[float]) -> dict | None:
    """max |got-exp| in microseconds after aligning both to their first value."""
    g = [x for x in got if x is not None]
    if not g or len(g) < 2:
        return None
    n = min(len(g), len(exp))
    g0, e0 = g[0], exp[0]
    errs = [abs((g[i] - g0) - (exp[i] - e0)) * 1e6 for i in range(n)]
    # also against the next frame's time (detects a one-frame reporting offset, e.g. cv2 POS_MSEC)
    errs_next = [abs((g[i] - g0) - (exp[i + 1] - e0)) * 1e6 for i in range(min(n, len(exp) - 1))]
    mono = all(b > a for a, b in zip(g, g[1:]))
    return {"n": n, "max_abs_err_us": round(max(errs), 3), "max_abs_err_vs_next_us": round(max(errs_next), 3) if errs_next else None,
            "strictly_increasing": mono}


def run_reader_suite(path: Path, is_pattern: bool, frames: list[bytes], expected_s: list[float], do_msmf: bool = True) -> dict:
    in_shas = [C.sha(f) for f in frames]
    r: dict = {}
    fp = io.ffprobe(path, is_pattern)
    pts = fp.pop("pts_time", None)
    r["ffprobe"] = fp
    r["ffprobe_ts"] = ts_err(pts or [], expected_s)
    pv = io.pyav_demux(path, is_pattern)
    if pv.get("ok"):
        r["pyav_bytes"] = compare(pv.pop("shas"), in_shas)
        r["pyav_ts"] = ts_err(pv.pop("pts_s"), expected_s)
    r["pyav"] = pv
    if not is_pattern:
        n = len(frames)
        r["pyav_seek"] = io.pyav_seek(path, [0, 1, n // 2, n - 1, 2], expected_s)
    fx = io.ffmpeg_extract(path, is_pattern)
    first = fx.pop("first")
    r["ffmpeg_extract_bytes"] = compare(fx.pop("shas"), in_shas)
    r["ffmpeg_extract"] = fx
    if first is not None and C.sha(first) != in_shas[0]:
        r["header_change_frame0"] = {"input": C.marker_summary(frames[0]), "extracted": C.marker_summary(first),
                                     "size_in": len(frames[0]), "size_out": len(first)}
    cv = io.cv2_read(path, "FFMPEG", frames, seek=True)
    hashes = cv.pop("_hashes", None)
    pm = cv.pop("pos_msec", [])
    r["cv2_ffmpeg"] = cv
    r["cv2_ffmpeg_ts"] = ts_err([x / 1000.0 for x in pm], expected_s)
    any_ = io.cv2_read(path, "ANY", None, seek=False)
    any_.pop("_hashes", None)
    any_.pop("pos_msec", None)
    r["cv2_any"] = any_
    if do_msmf and not is_pattern:
        ms = io.cv2_read(path, "MSMF", None, seek=False)
        ms.pop("_hashes", None)
        ms.pop("pos_msec", None)
        r["cv2_msmf"] = ms
    if is_pattern:
        im = io.cv2_read(path, "IMAGES", None, seek=False)
        im.pop("_hashes", None)
        im.pop("pos_msec", None)
        r["cv2_images"] = im
    r["freemocap_videohelper"] = io.freemocap_read(path, hashes)
    return r


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", default=",".join(DATASETS))
    ap.add_argument("--keep", action="store_true", help="keep all media outputs (default keeps only c930e_720p_flash)")
    ap.add_argument("--out", default=str(C.RESULTS / "mux_matrix.json"))
    a = ap.parse_args()
    C.TEMP.mkdir(parents=True, exist_ok=True)
    idx = C.index()
    results = {"meta": {"date": time.strftime("%Y-%m-%dT%H:%M:%S"), "python": sys.version}, "rows": []}
    import av
    import cv2
    results["meta"].update({"pyav": av.__version__, "pyav_ffmpeg_libs": {k: ".".join(map(str, v)) for k, v in av.library_versions.items()},
                            "opencv": cv2.__version__})
    for name in a.sets.split(","):
        n, tsrc, rate = DATASETS[name]
        frames = C.load_set(name, n)
        w, h = idx[name]["width"], idx[name]["height"]
        if tsrc == "real":
            ts = C.real_timestamps_ns(name, frames)[: len(frames)]
        else:
            ts = C.jitter_timestamps_ns(len(frames))
            if tsrc == "borrowed_half":
                ts = [t // 2 for t in ts]
        ts = [t - ts[0] for t in ts]
        us = [t // 1000 for t in ts]
        vfr_s = [u / 1e6 for u in us]
        cfr_s = [k / rate for k in range(len(frames))]
        d = C.MEDIA / "mux_matrix" / name
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        jobs = []
        for cont in io.CONTAINERS:
            jobs.append(("pyav", "vfr", cont))
            jobs.append(("pyav", "cfr", cont))
            if len(io.CONTAINERS[cont]) == 3:
                jobs.append(("ffmpeg", "cfr", cont))
        for cont in io.PY_CONTAINERS:
            jobs.append(("python", "vfr", cont))
        for writer, mode, cont in jobs:
            p = io.out_path(d, cont, f"{writer}_{mode}")
            t0 = time.time()
            if writer == "pyav":
                wr = io.pyav_write(p, cont, frames, w, h, us if mode == "vfr" else None, rate=rate)
            elif writer == "ffmpeg":
                wr = io.ffmpeg_write(p, cont, frames, rate=rate)
            else:
                wr = io.python_write(p, cont, frames, ts)
            row = {"set": name, "frames_in": len(frames), "w": w, "h": h, "ts_source": tsrc, "writer": writer, "mode": mode,
                   "container": cont, "write": wr, "payload_bytes": sum(map(len, frames))}
            if wr.get("ok"):
                exp = vfr_s if mode == "vfr" else cfr_s
                if cont == "raw_sidecar":
                    fr2, pts2 = io.read_sidecar(p)
                    row["sidecar_reader_bytes"] = compare([C.sha(x) for x in fr2], [C.sha(x) for x in frames])
                    row["sidecar_reader_ts_exact_ns"] = pts2 == ts
                    row["readers"] = run_reader_suite(p, False, frames, exp, do_msmf=False)
                elif cont == "jpg_folder":
                    files = sorted(p.parent.glob("frame_*.jpg"))
                    row["folder_reader_bytes"] = compare([C.sha(f.read_bytes()) for f in files], [C.sha(x) for x in frames])
                    row["readers"] = run_reader_suite(p, True, frames, exp)
                else:
                    row["readers"] = run_reader_suite(p, False, frames, exp)
            row["wall_s_functional_only"] = round(time.time() - t0, 1)  # not a benchmark: concurrent machine
            results["rows"].append(row)
            print(name, writer, mode, cont, "ok" if wr.get("ok") else wr.get("error", wr.get("stderr_flags")), flush=True)
        if not a.keep and name != "c930e_720p_flash":
            shutil.rmtree(d, ignore_errors=True)
    C.write_json(Path(a.out), results)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
