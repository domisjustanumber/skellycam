# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-python", "cv2-enumerate-cameras", "av", "numpy"]
# ///
"""Short open/read attempts via OpenCV CAP_MSMF, OpenCV CAP_DSHOW and PyAV dshow for chosen cameras/modes.

Run under camlock. Each attempt reads for --seconds (default 2) and records: opened?, frames read, first failure,
the delivered size/FOURCC, and (PyAV) the ffmpeg dshow log lines. Device -> OpenCV index is resolved at run time by
symbolic-link substring through cv2_enumerate_cameras (MSMF and DSHOW enumerate in different orders).

usage: uv run --script kiyo_lens_cv_av.py --out <file.json> [--seconds 2]
          --cam "vid_1532&pid_0e05" [--cam ...] --mode 1280x720@30 [--mode ...] [--backends msmf,dshow,pyav]
"""
import argparse, json, logging, platform, sys, time
from datetime import datetime, timezone

import cv2
from cv2_enumerate_cameras import enumerate_cameras


def fourcc_str(v):
    v = int(v)
    return "".join(chr((v >> (8 * i)) & 0xFF) for i in range(4))


def cv_attempt(api, api_name, cam_sub, w, h, fps, seconds):
    rec = {"backend": f"opencv-{api_name}", "cam": cam_sub, "mode": f"{w}x{h}@{fps}"}
    cams = [c for c in enumerate_cameras(api) if c.path and cam_sub.lower() in c.path.lower()]
    if not cams:
        rec["error"] = "not enumerated"
        return rec
    rec["index"], rec["name"] = cams[0].index, cams[0].name
    t0 = time.perf_counter()
    # Open by index only, then set properties: OpenCV 5.0 MSMF rejects CAP_PROP_FOURCC passed as an open param
    # ("can't set property 6") even on healthy cameras, so open-params would make every MSMF attempt fail.
    cap = cv2.VideoCapture(cams[0].index, api)
    rec["set"] = {"fourcc": bool(cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))),
                  "w": bool(cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)), "h": bool(cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)),
                  "fps": bool(cap.set(cv2.CAP_PROP_FPS, fps))} if cap.isOpened() else None
    rec["open_ms"] = round((time.perf_counter() - t0) * 1e3, 1)
    rec["opened"] = bool(cap.isOpened())
    if rec["opened"]:
        rec["reported"] = {"w": cap.get(cv2.CAP_PROP_FRAME_WIDTH), "h": cap.get(cv2.CAP_PROP_FRAME_HEIGHT),
                           "fps": cap.get(cv2.CAP_PROP_FPS), "fourcc": fourcc_str(cap.get(cv2.CAP_PROP_FOURCC)),
                           "backend_name": cap.getBackendName()}
        n_ok = n_fail = 0
        first_fail_s = None
        shape = None
        ts = time.perf_counter()
        while time.perf_counter() - ts < seconds:
            ok, frame = cap.read()
            if ok and frame is not None:
                n_ok += 1
                shape = list(frame.shape)
            else:
                n_fail += 1
                if first_fail_s is None:
                    first_fail_s = round(time.perf_counter() - ts, 3)
                if n_fail > 20:
                    break
        rec.update(frames_ok=n_ok, read_failures=n_fail, first_failure_s=first_fail_s, frame_shape=shape,
                   wall_s=round(time.perf_counter() - ts, 3))
    cap.release()
    return rec


class ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, r):
        self.lines.append(f"{r.name}: {r.getMessage()}")


def pyav_attempt(cam_sub, w, h, fps, seconds):
    import av
    rec = {"backend": "pyav-dshow", "cam": cam_sub, "mode": f"{w}x{h}@{fps}"}
    cams = [c for c in enumerate_cameras(cv2.CAP_DSHOW) if c.path and cam_sub.lower() in c.path.lower()]
    if not cams:
        rec["error"] = "not enumerated"
        return rec
    name = cams[0].name
    rec["device"] = f"video={name}"
    # DirectShow friendly names can collide; ffmpeg dshow accepts the device path (moniker) as well
    h_ = ListHandler()
    logging.getLogger("libav").addHandler(h_)
    av.logging.set_level(av.logging.VERBOSE)
    t0 = time.perf_counter()
    try:
        c = av.open(f"video={name}", format="dshow",
                    options={"vcodec": "mjpeg", "video_size": f"{w}x{h}", "framerate": str(fps), "rtbufsize": "64M"})
        rec["open_ms"] = round((time.perf_counter() - t0) * 1e3, 1)
        st = c.streams.video[0]
        rec["stream"] = {"codec": st.codec_context.name, "w": st.codec_context.width, "h": st.codec_context.height}
        n = 0
        ts = time.perf_counter()
        for pkt in c.demux(st):
            if pkt.size:
                n += 1
            if time.perf_counter() - ts > seconds:
                break
        rec.update(opened=True, packets=n, wall_s=round(time.perf_counter() - ts, 3))
        c.close()
    except Exception as e:  # noqa: BLE001
        rec.update(opened=False, error=repr(e), open_ms=round((time.perf_counter() - t0) * 1e3, 1))
    finally:
        av.logging.set_level(None)
        logging.getLogger("libav").removeHandler(h_)
    rec["ffmpeg_log_dshow"] = [l for l in h_.lines if "dshow" in l.lower()][:20]
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--cam", action="append", required=True)
    ap.add_argument("--mode", action="append", required=True)
    ap.add_argument("--backends", default="msmf,dshow,pyav")
    ap.add_argument("--seconds", type=float, default=2.0)
    a = ap.parse_args()
    import av
    res = {"test": "kiyo_lens_cv_av", "platform": "windows", "hostname": platform.node(),
           "utc_started": datetime.now(timezone.utc).isoformat(), "command": sys.argv,
           "environment": {"os": platform.platform(), "python": platform.python_version(), "opencv": cv2.__version__,
                           "av": av.__version__},
           "attempts": []}
    for cam in a.cam:
        for m in a.mode:
            wh, fps = m.split("@")
            w, h = (int(x) for x in wh.split("x"))
            fps = int(fps)
            for b in a.backends.split(","):
                if b == "msmf":
                    r = cv_attempt(cv2.CAP_MSMF, "msmf", cam, w, h, fps, a.seconds)
                elif b == "dshow":
                    r = cv_attempt(cv2.CAP_DSHOW, "dshow", cam, w, h, fps, a.seconds)
                else:
                    r = pyav_attempt(cam, w, h, fps, a.seconds)
                r["utc"] = datetime.now(timezone.utc).isoformat()
                print(json.dumps(r), file=sys.stderr, flush=True)
                res["attempts"].append(r)
    with open(a.out, "w") as f:
        json.dump(res, f, indent=1)


if __name__ == "__main__":
    main()
