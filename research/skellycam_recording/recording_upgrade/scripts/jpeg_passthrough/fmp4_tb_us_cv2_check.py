"""Reader check for fMP4 written by PyAV 19.0.2 with stream time_base 1/1e6 (open question from NOTES section 15).

Readers: OpenCV 4.12.0 CAP_FFMPEG (frame count prop, frames read, POS_FRAMES seek, POS_MSEC error vs the real capture
timestamps), CAP_ANY backend, CAP_MSMF, and FreeMoCap's real VideoHelper. Uses the skellycam .venv read-only.
Functional only; no timing.

Run (repo root):
  uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/pyav19_recheck.py --write-fmp4-us C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/jpeg_passthrough/fmp4_tb_us
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/fmp4_tb_us_cv2_check.py C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/jpeg_passthrough/fmp4_tb_us
Writes results/jpeg_passthrough/pyav19_fmp4_tb_us_readers.json and deletes the media folder.
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import jp_common as C  # noqa: E402
import jp_io as io  # noqa: E402
from mux_matrix import ts_err  # noqa: E402


def main() -> None:
    import cv2
    d = Path(sys.argv[1])
    name = "c930e_720p_flash"
    frames = C.load_set(name)
    ts = C.real_timestamps_ns(name, frames)
    exp = [((t - ts[0]) // 1000) / 1e6 for t in ts]
    res = {"meta": {"date": time.strftime("%Y-%m-%dT%H:%M:%S"), "opencv": cv2.__version__, "writer": "PyAV 19.0.2 (pyav19_recheck.py --write-fmp4-us)",
                    "set": name, "frames": len(frames), "note": "functional only; no timing"}, "files": {}}
    for p in sorted(d.glob("*.mp4")):
        r = {}
        cv = io.cv2_read(p, "FFMPEG", frames, seek=True)
        cv.pop("_hashes", None)
        pm = cv.pop("pos_msec", [])
        r["cv2_ffmpeg"] = {k: cv.get(k) for k in ("opened", "backend", "frames_read", "frame_count_prop", "fps_prop", "seek_exact", "seek_total")}
        r["cv2_ffmpeg_ts"] = ts_err([x / 1000.0 for x in pm], exp)
        an = io.cv2_read(p, "ANY", None, seek=False)
        r["cv2_any"] = {k: an.get(k) for k in ("opened", "backend", "frame_count_prop")}
        ms = io.cv2_read(p, "MSMF", None, seek=False)
        r["cv2_msmf"] = {k: ms.get(k) for k in ("opened", "frames_read", "frame_count_prop")}
        fm = io.freemocap_read(p, None)
        r["freemocap"] = {"frame_count": fm.get("frame_count"), "error": fm.get("error"),
                          "reads_ok": sum(1 for x in fm.get("reads", []) if x.get("ok")), "reads": len(fm.get("reads", []))}
        res["files"][p.stem] = r
        print(p.stem, r, flush=True)
    shutil.rmtree(d, ignore_errors=True)
    C.write_json(C.RESULTS / "pyav19_fmp4_tb_us_readers.json", res)
    print("wrote", C.RESULTS / "pyav19_fmp4_tb_us_readers.json")


if __name__ == "__main__":
    main()
