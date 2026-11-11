import json, sys
sys.path.insert(0, "C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/crash_resilience")
import common_cr as cc
from pathlib import Path
M = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/crash_resilience/pyav19_check")
T = M / "electron_trunc"; T.mkdir(exist_ok=True)
items = []
def add(p, payload, cont, case):
    items.append({"path": str(p).replace("\\", "/"), "id": p.stem, "payload": payload, "container": cont, "case": case,
                  "expected_frames": cc.ffprobe_count(str(p))["frames"], "timeout_ms": 8000})
kills = [("mjpeg", "mkv+fp"), ("av1", "mkv+fp"), ("av1", "mkv_cl0+fp"), ("av1", "webm_cl0+fp"), ("av1", "fmp4_every+fp"),
         ("h264nv", "mkv+fp"), ("h264nv", "mkv_cl0+fp"), ("h264nv", "fmp4_every+fp"), ("h264nv", "fmp4_kf+fp")]
for pl, c in kills:
    img = cc.out_path(M, pl, c, "drained150")
    add(img, pl, c, "drained:150 (PyAV 19 kill)")
    if pl != "mjpeg" and c in ("mkv_cl0+fp", "webm_cl0+fp", "fmp4_every+fp"):
        data = img.read_bytes()
        for frac in (0.6, 0.95):
            dst = T / f"{img.stem}__trunc{int(frac*100)}{img.suffix}"
            dst.write_bytes(data[: int(len(data) * frac)])
            add(dst, pl, c, f"truncated {int(frac*100)}%")
Path(sys.argv[1]).write_text(json.dumps(items, indent=1))
print(len(items))
