# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "opencv-python==5.0.0.93", "numpy==2.2.6"]
# ///
"""Version-bump check (isolated uv env; the skellycam .venv is untouched): do PyAV 19.0.2 and opencv-python 5.0.0.93
change anything for JPEG passthrough vs the pinned PyAV 18.0.0 / OpenCV 4.12.0 results in mux_matrix.json?

PyAV 19.0.2: re-run the passthrough writers (add_mux_stream) for c930e_720p_flash (VFR real timestamps) into every container,
             check PyAV byte-exactness, timestamps and seek.
OpenCV 5.0.0.93: read the same files with CAP_FFMPEG / CAP_MSMF: frame count prop, frames read, POS_FRAMES seek, POS_MSEC.

Run (repo root):
  uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/version_bump_check.py
Writes results/jpeg_passthrough/version_bump.json
"""
from __future__ import annotations

import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import jp_common as C  # noqa: E402
import jp_io as io  # noqa: E402
from mux_matrix import compare, ts_err  # noqa: E402


def main() -> None:
    import av
    import cv2
    bi = cv2.getBuildInformation()
    m = re.search(r"Video I/O:(.*?)Parallel framework", bi, re.S)
    res = {"meta": {"date": time.strftime("%Y-%m-%dT%H:%M:%S"), "pyav": av.__version__,
                    "pyav_ffmpeg_libs": {k: ".".join(map(str, v)) for k, v in av.library_versions.items()},
                    "opencv": cv2.__version__, "opencv_videoio_build": m.group(1).strip() if m else None}, "rows": []}
    name = "c930e_720p_flash"
    frames = C.load_set(name)
    in_shas = [C.sha(f) for f in frames]
    ts = C.real_timestamps_ns(name, frames)
    us = [(t - ts[0]) // 1000 for t in ts]
    d = C.MEDIA / "version_bump"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    for cont in io.CONTAINERS:
        for mode in ("vfr", "cfr"):
            p = io.out_path(d, cont, f"pyav19_{mode}")
            wr = io.pyav_write(p, cont, frames, 1280, 720, us if mode == "vfr" else None)
            row = {"container": cont, "mode": mode, "write_ok": wr.get("ok"), "write_error": wr.get("error"),
                   "stream_tb": wr.get("stream_time_base_after_first_mux")}
            if wr.get("ok"):
                exp = [u / 1e6 for u in us] if mode == "vfr" else [k / 30 for k in range(len(frames))]
                pv = io.pyav_demux(p, decode=False)
                row["pyav19_bytes"] = compare(pv.pop("shas", []), in_shas)
                row["pyav19_ts"] = ts_err(pv.pop("pts_s", []), exp)
                row["pyav19_seek_exact"] = sum(1 for s in io.pyav_seek(p, [0, 1, 445, 890, 2], exp) if s.get("exact"))
                for be in ("FFMPEG", "MSMF"):
                    cv = io.cv2_read(p, be, None, seek=(be == "FFMPEG"))
                    cv.pop("_hashes", None)
                    pm = cv.pop("pos_msec", [])
                    row[f"cv5_{be}"] = {k: cv.get(k) for k in ("opened", "backend", "frames_read", "frame_count_prop", "fps_prop", "seek_exact", "seek_total")}
                    if be == "FFMPEG":
                        row["cv5_ffmpeg_ts"] = ts_err([x / 1000 for x in pm], exp)
            res["rows"].append(row)
            print(cont, mode, {k: v for k, v in row.items() if k in ("write_ok", "write_error")}, row.get("pyav19_bytes", {}).get("byte_exact_all"),
                  row.get("cv5_FFMPEG", {}).get("frames_read"), row.get("cv5_FFMPEG", {}).get("frame_count_prop"), flush=True)
    shutil.rmtree(d, ignore_errors=True)
    C.write_json(C.RESULTS / "version_bump.json", res)
    print("wrote", C.RESULTS / "version_bump.json")


if __name__ == "__main__":
    main()
