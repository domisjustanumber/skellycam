"""P9 - short REAL-camera check of the decode-into-slot idea (bonus; one camera at a time, no SkellyCam process running).

For each DirectShow camera index that opens (0..MAX_INDEX), at 1280x720 and 1920x1080, MJPG, 60 fps requested,
CAP_PROP_BUFFERSIZE=1 (as SkellyCam's create_cv2_video_capture sets it; see the verified code map), RUN_S s per mode:
  grab_retrieve_private : grab() then retrieve() into a NEW array each time, then np.copyto into a SeqRing slot (1 copy)
  grab_retrieve_slot    : grab() then retrieve(image=<SeqRing slot view>) - the frame is written straight into shared memory
For each: delivered fps, grab() and retrieve() median / p99 ms, CPU ms per frame (process_time), and whether retrieve
really wrote into the slot (same data pointer, non-zero pixels).
The split of grab() vs retrieve() time answers the baseline's open question: does DSHOW decode MJPEG inside retrieve()
(the baseline 'mjpeg' stand-in) or on its own graph thread (closer to the 'memcpy' stand-in)?

Also probes (3 s each) whether the backend can hand over the camera's compressed MJPEG bytes (needed for real MJPEG
passthrough recording): DSHOW with CAP_PROP_CONVERT_RGB=0, and MSMF with CAP_PROP_FORMAT=-1. A buffer that starts with
FF D8 is a JPEG.

Nothing is restarted or reconfigured outside OpenCV (no pnputil). Cameras busy in another app are reported and skipped.
Run (from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam): .venv\\Scripts\\python.exe research\\frame_ring_buffer\\prototypes\\p9_real_camera.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

RUN_S = float(os.environ.get("P9_RUN_S", "10"))
MAX_INDEX = int(os.environ.get("P9_MAX_INDEX", "3"))  # indices 0-3 = the 4 UVC cameras attached (index 4 was not a camera in run 1)
DSHOW_NAMES = ["c922 Pro Stream Webcam", "Logitech Webcam C930e", "Razer Kiyo Pro", "USB Camera"]  # Get-PnpDevice -Class Camera
SIZES = [(1280, 720), (1920, 1080)]


def open_cap(idx, w, h, api):
    import cv2
    cap = cv2.VideoCapture(idx, api)
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    cap.set(cv2.CAP_PROP_FPS, 60)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    # SkellyCam then applies the config again, resolution first and FOURCC last (opencv_apply_config.py L74-85 @23ccbf20).
    # Run 1 of this script skipped this step and most cameras stayed in YUY2 (results/run1_fourcc_first_p9_real_camera.md).
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    return cap


def fourcc_str(v):
    v = int(v)
    return "".join(chr((v >> 8 * i) & 0xFF) for i in range(4))


def measure(cap, mode, ring, shape):
    import proto_common as pcm
    pc = time.perf_counter_ns
    # warm-up 1 s
    t_w = time.perf_counter() + 1.0
    while time.perf_counter() < t_w:
        cap.read()
    g_ns, r_ns, fails = [], [], 0
    k = 0
    info = {}
    cpu0 = time.process_time()
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < RUN_S:
        a = pc()
        ok = cap.grab()
        b = pc()
        if not ok:
            fails += 1
            continue
        s = ring.begin(k)
        view = ring.image_view(s, shape)
        if mode == "grab_retrieve_slot":
            if k == 0:
                view[:] = 0
            ok, out = cap.retrieve(image=view)
            if k == 0:
                info["inplace_verified"] = bool(ok and out is not None and out.shape == view.shape and
                                                out.__array_interface__["data"][0] == view.__array_interface__["data"][0]
                                                and int(view.sum(dtype=np.int64)) > 0)
        else:
            ok, out = cap.retrieve()
            if ok and out is not None and out.shape == view.shape:
                np.copyto(view, out)
            elif k == 0:
                info["shape_mismatch"] = None if out is None else list(out.shape)
        c = pc()
        ring.commit(k, s, frame_number=k, tick_ns=a)
        g_ns.append(b - a)
        r_ns.append(c - b)
        k += 1
    el = time.perf_counter() - t0
    cpu = time.process_time() - cpu0
    return dict(mode=mode, frames=k, fps=k / el, grab_fails=fails, grab=pcm.stats_ms(g_ns), retrieve_and_publish=pcm.stats_ms(r_ns),
                cpu_ms_per_frame=1000 * cpu / max(k, 1), cpu_pct=100 * cpu / el, **info)


def raw_probe(idx, w, h):
    import cv2
    out = {}
    for name, api, prop, val in (("dshow_convert_rgb_0", cv2.CAP_DSHOW, cv2.CAP_PROP_CONVERT_RGB, 0),
                                 ("msmf_format_minus1", cv2.CAP_MSMF, cv2.CAP_PROP_FORMAT, -1)):
        cap = open_cap(idx, w, h, api)
        if cap is None:
            out[name] = "did not open"
            continue
        try:
            set_ok = cap.set(prop, val)
            n = 0
            sizes = []
            first = None
            t0 = time.perf_counter()
            while time.perf_counter() - t0 < 3.0:
                ok, fr = cap.read()
                if not ok or fr is None:
                    continue
                n += 1
                sizes.append(int(fr.size))
                if first is None:
                    first = dict(shape=list(fr.shape), dtype=str(fr.dtype), starts_ffd8=bool(fr.size > 2 and fr.reshape(-1)[0] == 0xFF and fr.reshape(-1)[1] == 0xD8))
            out[name] = dict(set_returned=bool(set_ok), frames=n, fps=n / 3.0, first=first,
                             median_bytes=float(np.median(sizes)) if sizes else None,
                             width=cap.get(cv2.CAP_PROP_FRAME_WIDTH), height=cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        finally:
            cap.release()
    return out


def pyav_dshow_probe(name, w, h, seconds=5.0):
    """FFmpeg dshow input via PyAV with vcodec=mjpeg: demux packets WITHOUT decoding = the camera's own JPEG bytes
    (what an MJPEG-passthrough recorder needs). Reports fps, bytes/frame, FF D8 check and CPU ms per packet."""
    import av
    try:
        c = av.open(f"video={name}", format="dshow", options={"vcodec": "mjpeg", "video_size": f"{w}x{h}", "framerate": "60",
                                                              "rtbufsize": "64M"})
    except Exception as e:
        return dict(opened=False, error=repr(e)[:200])
    try:
        st = c.streams.video[0]
        n, nbytes, ffd8 = 0, [], 0
        cpu0 = time.process_time()
        t0 = time.perf_counter()
        for pkt in c.demux(st):
            if pkt.size == 0:
                continue
            mv = memoryview(pkt)
            if mv[0] == 0xFF and mv[1] == 0xD8:
                ffd8 += 1
            n += 1
            nbytes.append(pkt.size)
            if time.perf_counter() - t0 >= seconds:
                break
        el = time.perf_counter() - t0
        cpu = time.process_time() - cpu0
        return dict(opened=True, codec=st.codec_context.name, negotiated_rate=float(st.average_rate or 0), width=st.width, height=st.height,
                    packets=n, fps=n / el, packets_starting_ffd8=ffd8, median_bytes=float(np.median(nbytes)) if nbytes else None,
                    cpu_ms_per_packet=1000 * cpu / max(n, 1))
    finally:
        c.close()


def main():
    import cv2
    import proto_common as pcm
    out = dict(env=pcm.env_summary(), run_s=RUN_S, cameras=[])
    for idx in range(MAX_INDEX + 1):
        for (w, h) in SIZES:
            cap = open_cap(idx, w, h, cv2.CAP_DSHOW)
            if cap is None:
                if (w, h) == SIZES[0]:
                    out["cameras"].append(dict(index=idx, opened=False))
                break
            ok, fr = cap.read()
            if not ok or fr is None:
                cap.release()
                out["cameras"].append(dict(index=idx, opened=True, first_read_ok=False, requested=[w, h]))
                break
            aw, ah = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            row = dict(index=idx, opened=True, backend=cap.getBackendName(), requested=[w, h, 60], actual=[aw, ah, cap.get(cv2.CAP_PROP_FPS)],
                       fourcc=fourcc_str(cap.get(cv2.CAP_PROP_FOURCC)), frame_shape=list(fr.shape), modes=[])
            shape = fr.shape
            ring = pcm.SeqRing.create(16, int(np.prod(shape)), prefault=True)
            try:
                for mode in ("grab_retrieve_private", "grab_retrieve_slot"):
                    r = measure(cap, mode, ring, shape)
                    row["modes"].append(r)
                    print(f"cam{idx} {aw}x{ah} {row['fourcc']} {mode}: {r['fps']:.1f} fps grab {r['grab']['median_ms']:.2f}/{r['grab']['p99_ms']:.2f} "
                          f"retrieve+pub {r['retrieve_and_publish']['median_ms']:.2f}/{r['retrieve_and_publish']['p99_ms']:.2f} ms "
                          f"cpu {r['cpu_ms_per_frame']:.2f} ms/f inplace {r.get('inplace_verified')}", flush=True)
            finally:
                cap.release()
                ring.close()
            row["raw_bytes_probe"] = raw_probe(idx, w, h)
            print(f"cam{idx} {w}x{h} raw probe: {row['raw_bytes_probe']}", flush=True)
            out["cameras"].append(row)
            pcm.write_json("p9_real_camera.json", out)
    out["pyav_dshow_raw_mjpeg"] = []
    for name in DSHOW_NAMES:
        for (w, h) in SIZES:
            r = pyav_dshow_probe(name, w, h)
            r.update(device=name, requested=[w, h, 60])
            out["pyav_dshow_raw_mjpeg"].append(r)
            print("PYAV", r, flush=True)
    pcm.write_json("p9_real_camera.json", out)
    L = ["# P9 - real cameras (DSHOW, MJPG requested, BUFFERSIZE=1), one at a time", "",
         f"{RUN_S}s per mode. FOURCC set before AND after the size, as SkellyCam does. retrieve+pub = retrieve() (+ np.copyto into the shm slot for the private mode) + seq commit.", "",
         "| index | requested | actual WxH @ fps (fourcc) | mode | delivered fps | grab median / p99 ms | retrieve+publish median / p99 ms | CPU ms/frame | in-place verified |",
         "|---|---|---|---|---|---|---|---|---|"]
    for c in out["cameras"]:
        if not c.get("opened") or "modes" not in c:
            L.append(f"| {c['index']} | - | not opened / no frame | - | - | - | - | - | - |")
            continue
        for r in c["modes"]:
            L.append(f"| {c['index']} | {c['requested'][0]}x{c['requested'][1]}@60 | {c['actual'][0]}x{c['actual'][1]} @ {c['actual'][2]:.0f} ({c['fourcc']}) | {r['mode']} | "
                     f"{r['fps']:.1f} | {r['grab']['median_ms']:.2f} / {r['grab']['p99_ms']:.2f} | {r['retrieve_and_publish']['median_ms']:.2f} / "
                     f"{r['retrieve_and_publish']['p99_ms']:.2f} | {r['cpu_ms_per_frame']:.2f} | {r.get('inplace_verified', '-')} |")
    L += ["", "## Camera JPEG bytes via PyAV FFmpeg dshow input (vcodec=mjpeg, demux only, no decode), 5 s each", "",
          "| device | requested | opened | negotiated WxH @ rate | delivered fps | packets starting FF D8 / packets | median bytes/frame | CPU ms per packet |",
          "|---|---|---|---|---|---|---|---|"]
    for r in out["pyav_dshow_raw_mjpeg"]:
        if not r.get("opened"):
            L.append(f"| {r['device']} | {r['requested'][0]}x{r['requested'][1]}@60 | no: {r.get('error')} | - | - | - | - | - |")
        else:
            L.append(f"| {r['device']} | {r['requested'][0]}x{r['requested'][1]}@60 | yes ({r['codec']}) | {r['width']}x{r['height']} @ {r['negotiated_rate']:.1f} | "
                     f"{r['fps']:.1f} | {r['packets_starting_ffd8']} / {r['packets']} | {r['median_bytes']} | {r['cpu_ms_per_packet']:.3f} |")
    L += ["", "## Raw MJPEG byte access through OpenCV (3 s each)", "", "| index | size | probe | result |", "|---|---|---|---|"]
    for c in out["cameras"]:
        for k, v in (c.get("raw_bytes_probe") or {}).items():
            L.append(f"| {c['index']} | {c['requested'][0]}x{c['requested'][1]} | {k} | {v} |")
    pcm.write_text("p9_real_camera.md", "\n".join(L) + "\n")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
