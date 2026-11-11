# /// script
# requires-python = "==3.12.*"
# dependencies = ["opencv-contrib-python==4.12.*", "cv2-enumerate-cameras>=1.2.2", "numpy", "av"]
# ///
"""Emulate skellycam's OpenCV DirectShow capture loop (development-streaming @ 169caf63) and log every stamp.

Modes
  skellycam : one process per camera, the orchestrator lockstep gate (grab only when own frame_count <= every
              other camera's frame_count, polled with time.sleep(1e-5)), stamps pre/post grab and pre/post
              retrieve, overlay text drawn into the image, copy into shared memory, optional in-loop video encode
              (--record, as VideoRecorder.record_frame does), frame_count updated last.  Stored stamp = grab midpoint.
  free      : the revised loop: same capture setup, no gate, stored stamp = post-retrieve; optional encode runs on a
              separate thread (--record) so it never delays retrieve().

Capture setup follows skellycam exactly (code refs are to sc_ds/skellycam/core/camera/opencv/opencv_helpers):
  create_cv2_video_capture.py:57-75  FOURCC MJPG, width, height, (FPS not set: DEFAULT_FRAMERATE=-1), BUFFERSIZE=1, read()
  opencv_apply_config.py:117-181     MANUAL exposure: AUTO_EXPOSURE=1, EXPOSURE=<value>; width/height; FOURCC again
  setup_opencv_camera_loop.py:348-350 while not all ready: read(); sleep 10 ms
Deviation (documented in the results README): in the ready phase every camera's exposure is set again 1.5 s after the
first post-configuration frame (the C930e drops exposure set before/at stream start; REPORT finding 11), and the gate
opens only once every camera has streamed 2.5 s after configuration.

Output: <out>/<label>_<vidpid>.frames.csv (one row per frame, all stamps in perf_counter_ns = QPC ns) and
<out>/<label>.session.json (setup readbacks, set() returns, brightness before/after the exposure re-set, timings).
"""
from __future__ import annotations

import argparse
import csv
import json
import multiprocessing as mp
import os
import queue
import sys
import threading
import time
from multiprocessing import shared_memory
from pathlib import Path

W, H = 1280, 720


def resolve_indices(vidpids: list[str]) -> dict[str, dict]:
    import cv2
    from cv2_enumerate_cameras import enumerate_cameras
    found = {}
    for c in enumerate_cameras(cv2.CAP_DSHOW):
        if c.vid and c.pid:
            key = f"{c.vid:04X}:{c.pid:04X}"
            if key in vidpids and key not in found:
                found[key] = {"index": c.index, "name": c.name, "path": c.path}
    return found


def pick_writer(path_stub: str):
    """Mimic fourcc_codec_helpers.resolve_writer_fourcc: X264, then H264/avc1, then pyav libx264 (crf 18, fast), mp4v."""
    import cv2
    import numpy as np
    for fcc in ("X264", "H264", "avc1"):
        # _probe_codec (fourcc_codec_helpers.py:95-154): open, write one frame, require >= 100 bytes on disk
        pp = f"{path_stub}_probe_{fcc}.mp4"
        w = cv2.VideoWriter(pp, cv2.VideoWriter.fourcc(*fcc), 30.0, (W, H))
        ok = w.isOpened()
        if ok:
            w.write(np.zeros((H, W, 3), np.uint8))
        w.release()
        try:
            ok = ok and os.path.getsize(pp) >= 100
            os.remove(pp)
        except OSError:
            ok = False
        if ok:
            p = f"{path_stub}_{fcc}.mp4"
            return fcc, cv2.VideoWriter(p, cv2.VideoWriter.fourcc(*fcc), 30.0, (W, H)), p
    try:
        import av

        class Pyav:
            def __init__(self, path):
                self.c = av.open(path, mode="w")
                self.s = self.c.add_stream("libx264", rate=30)
                self.s.width, self.s.height, self.s.pix_fmt = W, H, "yuv420p"
                self.s.options = {"crf": "18", "preset": "fast"}
                self.n = 0

            def write(self, img):
                f = av.VideoFrame.from_ndarray(img, format="bgr24")
                f.pts = self.n
                self.n += 1
                for pk in self.s.encode(f):
                    self.c.mux(pk)

            def release(self):
                for pk in self.s.encode():
                    self.c.mux(pk)
                self.c.close()

        p = f"{path_stub}_pyav.mp4"
        return "pyav-libx264", Pyav(p), p
    except Exception:  # noqa: BLE001
        p = f"{path_stub}_mp4v.mp4"
        return "mp4v", cv2.VideoWriter(p, cv2.VideoWriter.fourcc(*"mp4v"), 30.0, (W, H)), p


def worker(cam_i: int, vidpid: str, index: int, args, counts, ready, warm, go, stop, out_q):
    import cv2
    import numpy as np
    pc = time.perf_counter_ns
    info: dict = {"vidpid": vidpid, "index": index, "sets": {}, "events": []}
    rows: list[tuple] = []
    cap = None
    shm = None
    writer = None
    try:
        t0 = pc()
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        info["open_s"] = (pc() - t0) / 1e9
        if not cap.isOpened():
            raise RuntimeError("VideoCapture did not open")
        s = info["sets"]
        s["fourcc_1"] = cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))
        s["width_1"] = cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
        s["height_1"] = cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
        s["buffersize_1"] = cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        t1 = pc()
        ok, img = cap.read()
        info["first_read_s"] = (pc() - t1) / 1e9
        info["first_read_ok"] = bool(ok)
        if not ok:
            raise RuntimeError("first read failed")
        # apply_camera_configuration(prior_config=None): exposure, size, FOURCC
        s["auto_exposure_2"] = cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
        s["exposure_2"] = cap.set(cv2.CAP_PROP_EXPOSURE, float(args.exposure))
        s["width_2"] = cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
        s["height_2"] = cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
        t2 = pc()
        s["fourcc_2"] = cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))
        info["fourcc_2_call_s"] = (pc() - t2) / 1e9
        fcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        info["readback"] = {
            "fourcc": "".join(chr((fcc >> (8 * k)) & 0xFF) for k in range(4)),
            "width": cap.get(cv2.CAP_PROP_FRAME_WIDTH), "height": cap.get(cv2.CAP_PROP_FRAME_HEIGHT),
            "fps": cap.get(cv2.CAP_PROP_FPS), "exposure": cap.get(cv2.CAP_PROP_EXPOSURE),
            "auto_exposure": cap.get(cv2.CAP_PROP_AUTO_EXPOSURE), "buffersize": cap.get(cv2.CAP_PROP_BUFFERSIZE),
            "pos_msec": cap.get(cv2.CAP_PROP_POS_MSEC), "convert_rgb": cap.get(cv2.CAP_PROP_CONVERT_RGB),
        }
        shm = shared_memory.SharedMemory(create=True, size=W * H * 3)
        shm_img = np.ndarray((H, W, 3), dtype=np.uint8, buffer=shm.buf)
        if args.record:
            stub = str(Path(args.video_dir) / f"{args.label}_{vidpid.replace(':', '')}")
            wname, writer, wpath = pick_writer(stub)
            info["writer"] = {"codec": wname, "path": wpath}
        ready[cam_i] = 1
        # ready phase (setup_opencv_camera_loop.py:348-350) + exposure re-set + brightness evidence
        t_cfg = None
        reset_done = False
        bright = {}
        while not go.value and not stop.value:
            ok, img = cap.read()
            now = pc()
            if ok and t_cfg is None:
                t_cfg = now
                info["first_frame_after_config_ns"] = now
            if ok and t_cfg is not None:
                el = (now - t_cfg) / 1e9
                if "before_reset" not in bright and el >= 1.2:
                    bright["before_reset"] = float(img[::8, ::8].mean())
                if not reset_done and el >= 1.5:
                    a = cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
                    b = cap.set(cv2.CAP_PROP_EXPOSURE, float(args.exposure))
                    info["events"].append({"event": "exposure_reset", "t_s": el, "set_auto": a, "set_exp": b,
                                           "readback": cap.get(cv2.CAP_PROP_EXPOSURE)})
                    reset_done = True
                if reset_done and "after_reset" not in bright and el >= 2.4:
                    bright["after_reset"] = float(img[::8, ::8].mean())
                if el >= 2.5 and reset_done:
                    warm[cam_i] = 1
            time.sleep(0.01)
        info["brightness_mean"] = bright

        n_cams = len(counts)
        image = np.zeros((H, W, 3), dtype=np.uint8)
        frame_number = 0
        rec_q: queue.Queue | None = None
        rec_th = None
        rec_times: list[tuple] = []
        if args.record and args.mode == "free":
            rec_q = queue.Queue(maxsize=120)

            def rec_loop():
                while True:
                    item = rec_q.get()
                    if item is None:
                        return
                    fn, im = item
                    a = pc()
                    writer.write(im)
                    rec_times.append((fn, a, pc()))
            rec_th = threading.Thread(target=rec_loop, daemon=True)
            rec_th.start()
        rec_dropped = 0
        slow_streak = 0
        would_reset = 0
        prev_tik = pc()
        while not stop.value:
            t_wait0 = pc()
            if args.mode == "skellycam":
                # CameraOrchestrator.should_grab_by_id: all ready, own count <= every count
                while not stop.value:
                    if all(ready[k] for k in range(n_cams)):
                        cs = [counts[k] for k in range(n_cams)]
                        if all(cs[cam_i] <= c for c in cs):
                            break
                    time.sleep(1e-5)
                if stop.value:
                    break
            t_gate = pc()
            fails = 0
            ok = False
            while not ok and fails < 30 and not stop.value:
                fails += 1
                a = pc(); g = cap.grab(); b = pc()
                if not g:
                    continue
                c = pc(); r, _ = cap.retrieve(image=image); d = pc()
                ok = bool(r)
                tik = pc()
                prev_tik = tik
            if not ok:
                info["events"].append({"event": "frame_fail", "frame_number": frame_number, "fails": fails})
                if stop.value:
                    break
                raise RuntimeError(f"no frame after {fails} attempts")
            frame_number += 1
            txt = f"camera.id{cam_i}.idx{index}.fr{frame_number}"
            cv2.putText(image, txt, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 8)
            cv2.putText(image, txt, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 210, 210), 2)
            e = pc(); np.copyto(shm_img, image); f = pc()
            g0 = g1 = 0
            if args.record:
                if args.mode == "skellycam":
                    g0 = pc(); writer.write(image); g1 = pc()
                else:
                    try:
                        rec_q.put_nowait((frame_number, image.copy()))
                    except queue.Full:
                        rec_dropped += 1
            # check_framerate_reset (opencv_camera_loop.py:150-170): logged only, never resets here
            if frame_number > 100:
                dur_ms = (pc() - prev_tik) / 1e6
                slow_streak = slow_streak + 1 if dur_ms > 2 * 1000 / 30 else 0
                if slow_streak > 30:
                    would_reset += 1
                    slow_streak = 0
            bri = float(image[::16, ::16].mean()) if frame_number % 30 == 0 else -1.0
            h = pc()
            counts[cam_i] = frame_number
            rows.append((frame_number, t_wait0, t_gate, a, b, c, d, e, f, g0, g1, h, fails, bri))
        if rec_q is not None:
            rec_q.put(None)
            rec_th.join(timeout=30)
        info["record_queue_dropped"] = rec_dropped
        info["would_framerate_reset"] = would_reset
        info["frames"] = frame_number
        out = Path(args.out) / f"{args.label}_{vidpid.replace(':', '')}.frames.csv"
        with open(out, "w", newline="") as fh:
            wr = csv.writer(fh)
            wr.writerow(["frame_number", "loop_start_ns", "gate_open_ns", "pre_grab_ns", "post_grab_ns",
                         "pre_retrieve_ns", "post_retrieve_ns", "pre_copy_ns", "post_copy_ns", "pre_record_ns",
                         "post_record_ns", "count_set_ns", "attempts", "brightness"])
            wr.writerows(rows)
        info["csv"] = out.name
    except Exception as ex:  # noqa: BLE001
        info["error"] = f"{type(ex).__name__}: {ex}"
        stop.value = 1
    finally:
        try:
            if writer is not None:
                writer.release()
                if not args.keep_video and info.get("writer"):
                    try:
                        os.remove(info["writer"]["path"])
                        info["writer"]["deleted"] = True
                    except OSError:
                        pass
        except Exception as ex:  # noqa: BLE001
            info["writer_release_error"] = str(ex)
        if cap is not None:
            cap.release()
        if shm is not None:
            shm.close(); shm.unlink()
        out_q.put(info)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["skellycam", "free"], required=True)
    ap.add_argument("--cams", required=True, help="comma list of VID:PID, e.g. 046D:0843,1532:0E05")
    ap.add_argument("--seconds", type=float, default=75)
    ap.add_argument("--exposure", type=float, default=-7)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--keep-video", action="store_true")
    ap.add_argument("--video-dir", default=os.environ.get("TEMP", "."))
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--setup-timeout-s", type=float, default=60)
    args = ap.parse_args()
    Path(args.out).mkdir(parents=True, exist_ok=True)
    vidpids = [v.strip().upper() for v in args.cams.split(",")]
    idx = resolve_indices(vidpids)
    session = {"label": args.label, "mode": args.mode, "argv": sys.argv, "python": sys.version,
               "resolved": idx, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    import cv2
    session["opencv"] = cv2.__version__
    missing = [v for v in vidpids if v not in idx]
    if missing:
        session["missing"] = missing
    cams = [v for v in vidpids if v in idx]
    n = len(cams)
    ctx = mp.get_context("spawn")
    counts = ctx.Array("q", n)
    ready = ctx.Array("b", n)
    warm = ctx.Array("b", n)
    go = ctx.Value("b", 0)
    stop = ctx.Value("b", 0)
    out_q = ctx.Queue()
    procs = [ctx.Process(target=worker, args=(i, v, idx[v]["index"], args, counts, ready, warm, go, stop, out_q),
                         daemon=True) for i, v in enumerate(cams)]
    for p in procs:
        p.start()
    t0 = time.monotonic()
    while not all(warm[k] for k in range(n)):
        if stop.value or time.monotonic() - t0 > args.setup_timeout_s:
            session["setup_failed"] = True
            break
        time.sleep(0.05)
    if not session.get("setup_failed"):
        session["go_ns"] = time.perf_counter_ns()
        go.value = 1
        t_end = time.monotonic() + args.seconds
        while time.monotonic() < t_end and not stop.value:
            time.sleep(0.1)
        session["early_stop"] = bool(stop.value)
    stop.value = 1
    infos = []
    deadline = time.monotonic() + 60
    while len(infos) < n and time.monotonic() < deadline:
        try:
            infos.append(out_q.get(timeout=1))
        except Exception:  # noqa: BLE001
            if not any(p.is_alive() for p in procs):
                break
    for p in procs:
        p.join(timeout=5)
        if p.is_alive():
            p.kill()
            session.setdefault("killed", []).append(p.pid)
    session["cameras"] = infos
    session["ended_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(Path(args.out) / f"{args.label}.session.json", "w") as fh:
        json.dump(session, fh, indent=1, default=str)
    errs = [i.get("error") for i in infos if i.get("error")]
    print(json.dumps({"label": args.label, "frames": {i["vidpid"]: i.get("frames") for i in infos},
                      "errors": errs, "setup_failed": session.get("setup_failed", False)}))
    return 1 if errs or session.get("setup_failed") else 0


if __name__ == "__main__":
    sys.exit(main())
