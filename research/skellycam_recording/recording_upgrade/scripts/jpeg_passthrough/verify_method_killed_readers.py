"""VERIFY_method (2026-11-09): OpenCV 4.12.0 (skellycam .venv, read-only use) + FreeMoCap VideoHelper on hard-killed files
written by PyAV 19.0.2 (pyav19_recheck.py --child <cont> <path> 600: os._exit(1) after 600 mux calls).
Functional only, no timing. FreeMoCap reads are matched against OpenCV's own sequential decode.

Run (repo root):
  for c in fmp4_1s_tb_us fmp4_perframe mkv nut: uv run --script .../pyav19_recheck.py --child $c DIR/killed_$c.<ext> 600
  .venv/Scripts/python.exe .../verify_method_killed_readers.py DIR
Writes results/jpeg_passthrough/verify_method_killed_readers.json and deletes DIR.
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
    res = {"meta": {"opencv": cv2.__version__, "writer": "PyAV 19.0.2, pyav19_recheck.py --child (os._exit after 600 mux calls)",
                    "set": "c930e_720p_flash", "note": "functional only; no timing"}, "files": {}}
    for p in sorted(d.iterdir()):
        cv = io.cv2_read(p, "FFMPEG", None, seek=False)
        h = cv.pop("_hashes", [])
        cv.pop("pos_msec", None)
        fm = io.freemocap_read(p, h)
        res["files"][p.name] = {
            "bytes": p.stat().st_size,
            "cv2": {k: cv.get(k) for k in ("opened", "frame_count_prop", "frames_read")},
            "freemocap": {"frame_count": fm.get("frame_count"), "error": (fm.get("error") or "")[:160] or None,
                          "reads": [{k: x.get(k) for k in ("k", "ok", "match_cv2_sequential", "error")} for x in fm.get("reads", [])]}}
        print(p.name, res["files"][p.name], flush=True)
    shutil.rmtree(d, ignore_errors=True)
    C.write_json(C.RESULTS / "verify_method_killed_readers.json", res)


if __name__ == "__main__":
    main()
