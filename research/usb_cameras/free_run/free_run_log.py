"""Free-run logger: each camera in its own process reads EVERY frame of the product's Media Foundation
source (no gate) and logs its times. No image is decoded or stored.

Run with the Python of the skellycam-connect worktree (read-only use of its classes), for example:
  <worktree>/.venv/Scripts/python.exe -I free_run_log.py --product <worktree> --out <temp dir> --seconds 300

Output in --out: one CSV per camera (label.csv) and meta.json. Labels come from the USB IDs; no device
path is written.
"""

import argparse
import csv
import json
import multiprocessing as mp
import re
import sys
import time
from pathlib import Path

CAMERAS = {"C922": (0x046D, 0x085C), "C930e": (0x046D, 0x0843), "KiyoPro": (0x1532, 0x0E05)}
STALL_S = 3.0  # no frame for this long: the camera is marked stalled (Kiyo Pro rule: no revive)


def usb_id(link):
    found = [re.search(key + r"_([0-9a-f]{4})", link.lower()) for key in ("vid", "pid")]
    return tuple(int(m.group(1), 16) for m in found) if all(found) else None


def camera_main(label, product, fps, exposure, out, to_main, stop):
    sys.path.insert(0, product)
    from time import perf_counter_ns

    from skellycam.core.camera.capture.media_foundation import com, detect
    from skellycam.core.camera.capture.media_foundation.source import MediaFoundationSource
    from skellycam.core.camera.capture.source import CaptureFailure, CaptureRequest, ControlSetting

    info = dict(label=label)
    com.startup()
    found = com.enumerate_devices("open")
    links = [link for _, link, _ in found if usb_id(link) == CAMERAS[label]]
    for _, _, activate in found:
        com.release(activate)
    if len(links) != 1:
        to_main.put(dict(info, status=f"{len(links)} devices with this USB ID"))
        return
    source = MediaFoundationSource()
    try:
        t0 = time.perf_counter()
        mode = source.open(CaptureRequest(camera_id=detect.camera_id_of(links[0]), width=1280, height=720,
                                          framerate=fps, capture_fourcc="MJPG"))
        info["open_s"] = round(time.perf_counter() - t0, 3)
        info["mode"] = [mode.width, mode.height, mode.fps_num, mode.fps_den, mode.format]
        setting = ControlSetting(auto=True, value=None) if exposure == "auto" else ControlSetting(False, int(exposure))
        readback = source.set_controls({"exposure": setting})
        info["controls_set_ns"] = perf_counter_ns()
        info["readback"] = {k: [v.present, v.auto, v.value] for k, v in readback.items()}
    except CaptureFailure as failure:
        to_main.put(dict(info, status=f"open failed: {failure.stage}: {failure.reason}"))
        return
    to_main.put(dict(info, status="ready"))  # logging starts now; the main process sets stop.value later
    rows, append, status = [], None, "ok"
    append = rows.append
    last_ns = perf_counter_ns()
    try:
        while True:
            frame = source.read_frame(0.5)
            now = perf_counter_ns()
            if frame is not None:  # the per-frame work: one tuple
                append((frame.arrival_ns, frame.sample_ns, frame.source_frame_number, int(frame.discontinuity),
                        frame.delivered_len, int(frame.driver_error), now))
                last_ns = now
            elif now - last_ns > STALL_S * 1e9:
                status = f"stalled: no frame for {STALL_S:g} s"
                break
            if now >= stop.value:
                break
    except CaptureFailure as failure:
        status = f"stream failed: {failure.stage}: {failure.reason}"
    info["replaced_count"] = source.replaced_count
    try:
        t0 = time.perf_counter()
        source.close()
        info["close_s"] = round(time.perf_counter() - t0, 3)
        com.shutdown()
    except CaptureFailure as failure:
        status += f"; close failed: {failure.reason}"
    with open(Path(out) / f"{label}.csv", "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["arrival_ns", "sample_ns", "source_frame_number", "discontinuity", "jpeg_len",
                         "driver_error", "read_ns"])
        writer.writerows(rows)
    to_main.put(dict(info, status=status, frames=len(rows)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--product", required=True, help="the skellycam-connect worktree (read-only)")
    parser.add_argument("--out", required=True)
    parser.add_argument("--cameras", default="C922,C930e,KiyoPro")
    parser.add_argument("--seconds", type=float, default=300)
    parser.add_argument("--settle", type=float, default=3.0, help="wait after all are ready, before the window")
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--exposure", default="-7", help="manual value, or 'auto'")
    args = parser.parse_args()
    import psutil

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    context = mp.get_context("spawn")
    to_main = context.Queue()
    labels = args.cameras.split(",")
    stop = context.Value("q", 2 ** 62, lock=False)
    procs = {label: context.Process(target=camera_main, name=f"free-run {label}", daemon=True,
                                    args=(label, args.product, args.fps, args.exposure, str(out), to_main, stop))
             for label in labels}
    for p in procs.values():
        p.start()
    ready, final = {}, {}
    deadline = time.monotonic() + 40
    while len(ready) < len(labels) and time.monotonic() < deadline:
        try:
            msg = to_main.get(timeout=1)
        except Exception:
            continue
        ready[msg["label"]] = msg
        if msg["status"] != "ready":
            final[msg["label"]] = msg
    for label in labels:
        ready.setdefault(label, dict(label=label, status="no answer in 40 s"))
    live = [label for label in labels if ready[label]["status"] == "ready"]
    go_ns = time.perf_counter_ns() + int(args.settle * 1e9)
    stop_ns = go_ns + int(args.seconds * 1e9)
    stop.value = stop_ns
    children = {label: psutil.Process(procs[label].pid) for label in live}
    cpu0 = {label: sum(c.cpu_times()[:2]) for label, c in children.items()}
    psutil.cpu_percent(None)
    machine = []
    while time.perf_counter_ns() < stop_ns:
        machine.append(psutil.cpu_percent(interval=1.0))
    cpu1 = {}
    for label, c in children.items():
        try:
            cpu1[label] = sum(c.cpu_times()[:2])
        except psutil.Error:
            cpu1[label] = None
    deadline = time.monotonic() + 30
    while len(final) < len(labels) and time.monotonic() < deadline:
        try:
            msg = to_main.get(timeout=1)
            final[msg["label"]] = msg
        except Exception:
            continue
    killed = []
    for label, p in procs.items():
        p.join(10)
        if p.is_alive():
            p.kill()
            killed.append(label)
    span = (stop_ns - go_ns) / 1e9
    meta = dict(go_ns=go_ns, stop_ns=stop_ns, seconds=args.seconds, fps=args.fps, exposure=args.exposure,
                utc_start=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - span)),
                cameras={label: final.get(label, ready[label]) for label in labels}, killed=killed,
                machine_cpu_percent=dict(n=len(machine), mean=sum(machine) / max(1, len(machine)),
                                         max=max(machine, default=None), samples=machine),
                logical_cpus=psutil.cpu_count(),
                child_cpu_cores={label: None if cpu1.get(label) is None else (cpu1[label] - cpu0[label]) / span
                                 for label in children})
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    for label in labels:
        info = meta["cameras"][label]
        print(label, info.get("status"), "frames", info.get("frames"), "replaced", info.get("replaced_count"),
              "readback", info.get("readback", {}).get("exposure"), "open_s", info.get("open_s"))
    print("machine CPU % mean", round(meta["machine_cpu_percent"]["mean"], 1), "max", meta["machine_cpu_percent"]["max"],
          "killed", killed)


if __name__ == "__main__":
    main()
