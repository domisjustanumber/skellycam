"""Probe the MKV files with ffprobe and OpenCV. Usage: python probe_opencv.py MEDIA_DIR

Writes MEDIA_DIR/opencv_results.json and prints Markdown tables.
"""

import json
import subprocess
import sys
from pathlib import Path

import av
import cv2
import numpy as np

d = Path(sys.argv[1])
thumbs = np.load(d / "ref_thumbs.npy")
with av.open(str(d / "full.mkv")) as c:
    ref_jpegs = [bytes(p) for p in c.demux(video=0) if p.size]
assert len(ref_jpegs) == 300

FILES = ["full", "B-one", "B-run", "B-tail", "B-tail-dur10", "B-head", "B-head30", "A-one", "A-run"]
SEEK_N = [0, 5, 9, 10, 11, 50, 98, 99, 100, 101, 102, 120, 150, 188, 189, 190, 191, 199, 200, 201, 209, 210, 211, 250, 289, 290, 299]


def ident(bgr) -> tuple[int, float, float, int]:
    """Nearest reference frame: (number, mean abs diff, margin to 2nd best, max abs diff vs cv2.imdecode)."""
    g = cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (64, 48), interpolation=cv2.INTER_AREA).astype(np.float32)
    dist = np.abs(thumbs - g).mean(axis=(1, 2))
    o = np.argsort(dist)
    n = int(o[0])
    ref = cv2.imdecode(np.frombuffer(ref_jpegs[n], np.uint8), cv2.IMREAD_COLOR)
    exact = int(np.abs(ref.astype(int) - bgr.astype(int)).max()) if ref.shape == bgr.shape else -1
    return n, float(dist[o[0]]), float(dist[o[1]] - dist[o[0]]), exact


def ffprobe(path: Path) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0",
         "-show_entries", "stream=nb_frames,nb_read_packets,duration,avg_frame_rate,r_frame_rate:stream_tags=DURATION:format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    j = json.loads(r.stdout)
    s = j["streams"][0]
    return {
        "nb_read_packets": s.get("nb_read_packets"), "nb_frames": s.get("nb_frames"),
        "avg_frame_rate": s.get("avg_frame_rate"), "r_frame_rate": s.get("r_frame_rate"),
        "stream_duration": s.get("duration"), "tag_DURATION": s.get("tags", {}).get("DURATION"),
        "format_duration": j["format"].get("duration"),
    }


def pyav(path: Path) -> dict:
    with av.open(str(path)) as c:
        s = c.streams.video[0]
        info = {"frames": s.frames, "duration_s": float(s.duration * s.time_base) if s.duration else None,
                "container_duration_s": c.duration / 1e6 if c.duration else None,
                "average_rate": str(s.average_rate), "base_rate": str(s.base_rate), "guessed_rate": str(s.guessed_rate)}
        pts = [p.pts for p in c.demux(video=0) if p.size]
        info["packets"] = len(pts)
        info["pts_ms_first3_last1"] = pts[:3] + pts[-1:]
    return info


def opencv(path: Path) -> dict:
    cap = cv2.VideoCapture(str(path))
    assert cap.isOpened()
    res = {"backend": cap.getBackendName(), "frame_count": cap.get(cv2.CAP_PROP_FRAME_COUNT), "fps": cap.get(cv2.CAP_PROP_FPS)}
    reads = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        n, dist, margin, exact = ident(f)
        reads.append({"i": len(reads), "num": n, "dist": round(dist, 2), "margin": round(margin, 1), "exact_maxdiff": exact,
                      "pos_frames": cap.get(cv2.CAP_PROP_POS_FRAMES), "pos_msec": round(cap.get(cv2.CAP_PROP_POS_MSEC), 2)})
    nums = [r["num"] for r in reads]
    res["reads"] = len(reads)
    res["nums_strictly_increasing"] = all(a < b for a, b in zip(nums, nums[1:]))
    res["duplicates"] = len(nums) - len(set(nums))
    res["max_ident_dist"] = max(r["dist"] for r in reads)
    res["min_ident_margin"] = min(r["margin"] for r in reads)
    res["max_exact_diff"] = max(r["exact_maxdiff"] for r in reads)
    res["all_reads"] = reads
    seeks = []
    for prop, name in [(cv2.CAP_PROP_POS_FRAMES, "frames"), (cv2.CAP_PROP_POS_MSEC, "msec")]:
        for n in SEEK_N:
            v = n if name == "frames" else n * 1000 / 30
            set_ok = cap.set(prop, v)
            ok, f = cap.read()
            seeks.append({"by": name, "n": n, "set_ok": set_ok, "read_ok": ok,
                          "num": ident(f)[0] if ok else None,
                          "pos_frames_after": cap.get(cv2.CAP_PROP_POS_FRAMES)})
    res["seeks"] = seeks
    cap.release()
    return res


out = {"opencv_version": cv2.__version__, "pyav_version": av.__version__}
for name in FILES:
    p = d / f"{name}.mkv"
    out[name] = {"ffprobe": ffprobe(p), "pyav": pyav(p), "opencv": opencv(p)}
    print(name, "done", flush=True)
(d / "opencv_results.json").write_text(json.dumps(out, indent=1))

# Markdown tables
print("\n| file | ffprobe packets | ffprobe nb_frames | format duration s | DURATION tag | avg_frame_rate | r_frame_rate | PyAV frames | PyAV last pts ms |")
print("|---|---|---|---|---|---|---|---|---|")
for n in FILES:
    f, a = out[n]["ffprobe"], out[n]["pyav"]
    print(f"| {n} | {f['nb_read_packets']} | {f['nb_frames']} | {f['format_duration']} | {f['tag_DURATION']} | {f['avg_frame_rate']} | {f['r_frame_rate']} | {a['frames']} | {a['pts_ms_first3_last1']} |")
print("\n| file | backend | FRAME_COUNT | FPS | frames read | increasing | duplicates | first..last drawn | max exact diff |")
print("|---|---|---|---|---|---|---|---|---|")
for n in FILES:
    o = out[n]["opencv"]
    r = o["all_reads"]
    print(f"| {n} | {o['backend']} | {o['frame_count']} | {o['fps']} | {o['reads']} | {o['nums_strictly_increasing']} | {o['duplicates']} | {r[0]['num']}..{r[-1]['num']} | {o['max_exact_diff']} |")
