"""Reader half of the VERIFY_method checks (2026-11-09): OpenCV 4.12.0 (skellycam .venv, read-only use) and FreeMoCap's
real VideoHelper on the files written by verify_method_writer.py (PyAV 19.0.2). Functional only, no timing.

Records frame-count property, frames read, seek (jp_io.cv2_read), and FreeMoCap reads matched against OpenCV's own
sequential decode hashes (the earlier check passed ref_hashes=None, so it only tested "no exception").

Run (repo root):
  .venv/Scripts/python.exe .../verify_method_reader.py DIR
Writes results/jpeg_passthrough/verify_method_reader.json and deletes DIR.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import jp_common as C  # noqa: E402
import jp_io as io  # noqa: E402


def main() -> None:
    import cv2
    d = Path(sys.argv[1])
    w = json.loads((C.RESULTS / "verify_method_writer.json").read_text())
    res = {"meta": {"opencv": cv2.__version__, "note": "functional only; no timing"}, "files": {}}
    allf = {**w["V2_files"], **w["V3_files"]}
    for fname, info in allf.items():
        p = d / fname
        if fname.startswith("long_"):  # jp_io.cv2_read stops at 20,001 frames; count with grab() instead
            cap = cv2.VideoCapture(str(p), cv2.CAP_FFMPEG)
            r = {"n_written": info["n_frames"], "cv2": {"frame_count_prop": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
                                                       "fps_prop": cap.get(cv2.CAP_PROP_FPS)}}
            g = 0
            while cap.grab():
                g += 1
            r["cv2"]["frames_grabbed"] = g
            cap.release()
            fm = io.freemocap_read(p, None)
            r["freemocap"] = {"frame_count": fm.get("frame_count"), "error": fm.get("error"),
                              "reads": [{k: x.get(k) for k in ("k", "ok", "error")} for x in fm.get("reads", [])]}
            res["files"][fname] = r
            print(fname, r, flush=True)
            continue
        cv = io.cv2_read(p, "FFMPEG", None, seek=True)
        hashes = cv.pop("_hashes", [])
        cv.pop("pos_msec", None)
        fm = io.freemocap_read(p, hashes)
        r = {"n_written": info["n_frames"],
             "cv2": {k: cv.get(k) for k in ("frame_count_prop", "fps_prop", "frames_read", "unique_frame_hashes", "seek_exact", "seek_total")},
             "freemocap": {"frame_count": fm.get("frame_count"), "error": fm.get("error"),
                           "reads": [{k: x.get(k) for k in ("k", "ok", "match_cv2_sequential", "error")} for x in fm.get("reads", [])]}}
        res["files"][fname] = r
        print(fname, r, flush=True)
    shutil.rmtree(d, ignore_errors=True)
    C.write_json(C.RESULTS / "verify_method_reader.json", res)


if __name__ == "__main__":
    main()
