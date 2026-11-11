"""Probe how freemocap's video readers see raw-MJPEG and VFR containers.

No camera is opened. Synthetic 1280x720 JPEG frames are muxed WITHOUT re-encoding
(as a raw-MJPEG capture path would write them), then probed the way
freemocap development-streaming does:
  - frame count / fps: cv2.CAP_PROP_FRAME_COUNT / CAP_PROP_FPS
    (skellycam VideoFileMetadata.from_path, used by VideoGroupHelper and import check)
  - frames: PyAV container.decode(video=0) in order (skellycam SequentialVideoReader)
  - is_corrupt flag (SequentialVideoReader.read_bgr raises on it)
Usage: python -I mjpeg_container_probe.py <out_dir>
"""
import json
import sys
from fractions import Fraction
from pathlib import Path

import av
import cv2
import numpy as np

W, H, N = 1280, 720, 90


def jpeg(k: int) -> bytes:
    img = np.full((H, W, 3), (k * 7) % 255, np.uint8)
    cv2.putText(img, str(k), (50, 300), cv2.FONT_HERSHEY_SIMPLEX, 8, (255, 255, 255), 12)
    ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    assert ok
    return enc.tobytes()


def mux(path: Path, pts_ms: list[int], corrupt_index: int | None = None, fmt: str | None = None) -> None:
    # AVI has one fixed frame period, so packets go in 1/30 s ticks (rounded); others keep ms.
    tb = Fraction(1, 30) if fmt == "avi" else Fraction(1, 1000)
    with av.open(str(path), "w", format=fmt) as out:
        st = out.add_stream("mjpeg", rate=30)
        st.width, st.height, st.pix_fmt = W, H, "yuvj420p"
        st.time_base = tb
        for i, t_ms in enumerate(pts_ms):
            t = round(t_ms * 30 / 1000) if fmt == "avi" else t_ms
            data = jpeg(i)
            if i == corrupt_index:
                data = data[: len(data) // 3]  # truncated JPEG, like a short USB payload
            pkt = av.Packet(data)
            pkt.pts = pkt.dts = t
            pkt.time_base = tb
            pkt.stream = st
            pkt.is_keyframe = True
            out.mux(pkt)


def probe(path: Path) -> dict:
    cap = cv2.VideoCapture(str(path))
    res = {"file": path.name, "cv2_opened": cap.isOpened(),
           "cv2_frame_count": cap.get(cv2.CAP_PROP_FRAME_COUNT), "cv2_fps": cap.get(cv2.CAP_PROP_FPS)}
    cap.release()
    decoded, corrupt, pts = 0, [], []
    err = None
    try:
        with av.open(str(path)) as c:
            s = c.streams.video[0]
            res["pyav_avg_rate"] = str(s.average_rate)
            res["pyav_stream_frames"] = s.frames
            for f in c.decode(video=0):
                if f.is_corrupt:
                    corrupt.append(decoded)
                pts.append(None if f.pts is None else float(f.pts * f.time_base))
                decoded += 1
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    res.update(pyav_decoded=decoded, pyav_corrupt_indices=corrupt, pyav_error=err,
               first_pts_s=pts[:4], pts_intervals_ms_sample=[round((b - a) * 1000, 3) for a, b in zip(pts[:6], pts[1:7])
                                                            if a is not None and b is not None])
    return res


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    cfr = [round(k * 1000 / 30) for k in range(N)]
    rng = np.random.default_rng(0)
    vfr = []
    t = 0.0
    for k in range(N):
        vfr.append(int(round(t)))
        t += 33.333 + rng.normal(0, 4)
        if k == 40:
            t += 33.333  # one dropped slot
    cases = [
        ("mjpeg_cfr.avi", cfr, None, "avi"),
        ("mjpeg_cfr.mkv", cfr, None, "matroska"),
        ("mjpeg_vfr_drop.mkv", vfr, None, "matroska"),
        ("mjpeg_vfr_drop.avi", vfr, None, "avi"),
        ("mjpeg_truncated_frame.avi", cfr, 45, "avi"),
        ("mjpeg_vfr_drop.mp4", vfr, None, "mp4"),
    ]
    results = []
    for name, pts, bad, fmt in cases:
        p = out / name
        try:
            mux(p, pts, bad, fmt)
            results.append(probe(p))
        except Exception as e:  # noqa: BLE001
            results.append({"file": name, "mux_error": f"{type(e).__name__}: {e}"})
    meta = {"frames_written": N, "size": [W, H], "cv2": cv2.__version__, "pyav": av.__version__,
            "ffmpeg_libs": str(av.library_versions.get("libavformat"))}
    (out / "probe_results.json").write_text(json.dumps({"meta": meta, "results": results}, indent=2))
    print(json.dumps({"meta": meta, "results": results}, indent=2))


if __name__ == "__main__":
    main()
