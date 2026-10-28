"""P8 - end-to-end PROTOTYPE pipeline (5 cameras, 60 fps), directly comparable with baseline/bench_e_e2e.py.

Same camera model as the baseline e2e (FakeSensor = baseline FakeCapture semantics: free-running 60 fps sensor with
random phase, latest frame wins, skipped ticks counted as "sensor frames never grabbed"), same synthetic content
(synthetic_frames noise=8, q90 JPEG, 30 frames cycled), same 2 x cv2.putText overlay per frame, same writer for the
msmf variants (cv2 'X264' -> MSMF H.264). What changes is the architecture:

  * camera process (spawned, one per camera): grab -> decode/copy INTO the SeqRing slot -> overlay in the slot ->
    seq commit. No lockstep gate, no encode, no copy.copy, no private recarray.
  * recorder process (spawned, one per camera): consumes its camera's ring strictly in order via a gated cursor
    (block policy, ring sized like SkellyCam's 1 GiB). Encoder fed the slot VIEW (msmf / nvenc) or the camera JPEG
    bytes (passthrough -> .mkv, no re-encode).
  * UI consumer in the parent: asyncio relay shape (await 10 ms), latest-frame-wins (build only when every camera has
    a new frame), seqlock views -> resize(dst=prealloc, 0.5) -> imencode q60 in a ThreadPoolExecutor(5).

Variants (argv[1]):  decode=imdecode|simplejpeg|memcpy   rec=msmf|passthrough|nvenc   e.g.  1080p imdecode msmf
  imdecode   : cv2.imdecode(jpeg) -> np.copyto(slot)             (1 full-frame copy after decode)
  simplejpeg : simplejpeg.decode_jpeg(jpeg, buffer=slot)          (0 copies; bench venv only)
  memcpy     : np.copyto(slot, frame)                             (decode-free stand-in, = baseline 'memcpy' mode)
  imdecode_off (passthrough recorder only; added 2026-10-28): the capture loop ONLY copies the JPEG bytes into the
             byte ring (the recorder muxes them, gated = lossless); P8_NDEC (default 2) decoder threads in the camera
             process decode the newest JPEGs into the BGR ring for the UI / realtime consumers (latest-wins; frames
             they skip are counted as decode_skipped, never as recording losses). cv2.imdecode releases the GIL.
  passthrough recorder: the camera ALSO copies its JPEG bytes into a 1 MiB-slot byte ring (1 compressed copy);
              the recorder gates on that ring; the BGR ring is then not gated (pixels are for UI/pose only).

Options added 2026-10-28 by the REVISION stage (env vars; all default off, so the original rows are unchanged):
  P8_LOCKSTEP=1     SkellyCam-style lockstep gate before every grab: a camera grabs only when every camera's published
                    frame count >= its own (camera_orchestrator.py L96-109), polled with time.sleep(1e-5) like wait_10us
                    (wait_functions.py L29-30); counts live in one shared int64 array.
  P8_META=1         per frame, the camera also writes frame_number + 31 timestamp fields into a real SkellyCam frame
                    recarray (bench_common.make_frame_recarray, create_frame_dtype) through recarray field access, the
                    per-frame metadata cost the original P8 left out (cpp/results/micro_py.json: 13.5 us per nested write).
  P8_RECTHREAD=1    the recorder runs as a (non-daemon) thread inside its camera process instead of its own process.
  P8_EXTRA_CPU_MS=x busy-spin x ms of CPU (GIL held) after the decode, as a sensitivity stand-in for P9's real DSHOW
                    retrieve CPU (11.0-14.7 ms/frame at 1080p vs about 9 ms for the imdecode stand-in).
  Every run now also records the cross-camera spread of grab times and of sensor tick times per frame number
  ("cross_camera_spread"). Not modelled even with these options: camera_loop_update_checks / pubsub polling, the
  deepcopy in should_grab_by_id, the start/stop recording handshake and RecordingFinalizer.

Run (from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam):
  .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\prototypes\\p8_e2e_proto.py 1080p imdecode msmf 30
  benchmarks\\frame_pipeline\\.venv-bench\\Scripts\\python.exe benchmarks\\frame_pipeline\\prototypes\\p8_e2e_proto.py 1080p simplejpeg passthrough 30
  .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\prototypes\\p8_e2e_proto.py --summarize
"""
from __future__ import annotations

import asyncio
import json
import multiprocessing as mp
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

N_CAMS = int(os.environ.get("P8_NCAMS", "5"))
FPS = 60.0
JSLOT = 1 << 20
N_DEC = int(os.environ.get("P8_NDEC", "2"))  # decoder threads per camera for decode=imdecode_off
DEC_MAX_LAG = int(os.environ.get("P8_DEC_MAX_LAG", "2"))
LOCKSTEP = os.environ.get("P8_LOCKSTEP") == "1"
META = os.environ.get("P8_META") == "1"
RECTHREAD = os.environ.get("P8_RECTHREAD") == "1"
EXTRA_CPU_NS = int(float(os.environ.get("P8_EXTRA_CPU_MS", "0")) * 1e6)


def camera(spec, jspec, cam, h, w, decode, rec, run_s, ready_q, go, out_q, counts_name=None, rec_args=None):
    import cv2
    import proto_common as pcm
    from multiprocessing import shared_memory as _shm
    cnt_shm = cnt = None
    if counts_name:
        cnt_shm = _shm.SharedMemory(name=counts_name)
        cnt = np.ndarray((N_CAMS,), np.int64, buffer=cnt_shm.buf)
    fr = ts_names = None
    if META:
        import bench_common as bc
        fr = bc.make_frame_recarray(bc.make_config(cam, h, w, framerate=FPS))
        ts_names = list(fr.frame_metadata.timestamps.dtype.names)
    rthread = None
    if rec_args is not None:
        rthread = threading.Thread(target=recorder, args=rec_args, daemon=False)
        rthread.start()
    ring = pcm.SeqRing.attach(spec)
    jring = pcm.SeqRing.attach(jspec) if jspec else None
    frames = pcm.synthetic_frames(h, w, n=30, seed=cam, noise=8)
    jpegs = [cv2.imencode(".jpg", f, [int(cv2.IMWRITE_JPEG_QUALITY), 90])[1] for f in frames]
    jbytes = [j.tobytes() for j in jpegs]
    if decode == "simplejpeg":
        import simplejpeg
    shape = (h, w, 3)
    gate_ring = jring if rec == "passthrough" else ring
    off = decode == "imdecode_off"
    if off:
        assert jring is not None, "imdecode_off needs the passthrough JPEG ring"
        import threading
        lock = threading.Lock()
        dstop = threading.Event()
        dst = dict(next=0, decoded=0, skipped=0, torn=0, dec_ns=[], lat_ns=[])
        F = pcm

        def decoder():
            """Off-loop decoder thread: takes the next published JPEG (in order; if it falls more than DEC_MAX_LAG
            frames behind it jumps to the newest and COUNTS the skipped frames - these pixels feed only the UI /
            realtime path; the recorder keeps every JPEG), decodes into the BGR slot, overlays, publishes."""
            while not dstop.is_set():
                with lock:
                    hd = jring.head
                    nk = dst["next"]
                    if nk > hd:
                        k2 = None
                    else:
                        if hd - nk > DEC_MAX_LAG:
                            dst["skipped"] += hd - nk
                            nk = hd
                        k2 = nk
                        dst["next"] = nk + 1
                if k2 is None:
                    time.sleep(0.0002)
                    continue
                js = k2 % jring.L
                s1 = int(jring.meta[js, F.F_SEQ])
                if s1 != 2 * k2 + 2:
                    dst["torn"] += 1
                    continue
                nb = int(jring.meta[js, F.F_NBYTES])
                t_tick2 = int(jring.meta[js, F.F_TICK])
                a2 = time.perf_counter_ns()
                sl = k2 % ring.L
                ring.meta[sl, F.F_SEQ] = 2 * k2 + 1
                v2 = ring.image_view(sl, shape)
                np.copyto(v2, cv2.imdecode(jring.bytes_view(js, nb), cv2.IMREAD_COLOR))
                txt2 = f"camera.id:{cam}, idx:{cam}, fr:{k2}"
                cv2.putText(v2, txt2, (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 4)
                cv2.putText(v2, txt2, (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 255), 2)
                if int(jring.meta[js, F.F_SEQ]) != s1:
                    dst["torn"] += 1  # JPEG slot reused during decode (cannot happen while the recorder gates jring)
                m2 = ring.meta[sl]
                m2[F.F_FN] = k2
                m2[F.F_TICK] = t_tick2
                m2[F.F_PUB] = time.perf_counter_ns()
                ring.meta[sl, F.F_SEQ] = 2 * k2 + 2
                with lock:
                    if k2 > int(ring.hdr[F.H_HEAD]):
                        ring.hdr[F.H_HEAD] = k2  # head only moves forward (decoders may finish out of order)
                b2 = time.perf_counter_ns()
                dst["dec_ns"].append(b2 - a2)
                dst["lat_ns"].append(b2 - t_tick2)
                dst["decoded"] += 1
        dthreads = [threading.Thread(target=decoder, daemon=True) for _ in range(N_DEC)]
        for t_ in dthreads:
            t_.start()
    ready_q.put(cam)
    go.wait()
    sensor = pcm.FakeSensor(FPS, seed=cam)
    t_end = time.perf_counter_ns() + int(run_s * 1e9)
    k = 0
    dec_ns, pub_ns, loop_ns, blocked_ns = [], [], [], []
    ticks = []
    cpu0 = time.process_time()
    t0w = time.perf_counter()
    last = None
    grab_ns, tick_ns_l, gate_ns = [], [], []
    while time.perf_counter_ns() < t_end:
        if cnt is not None:
            q0 = time.perf_counter_ns()
            while int(cnt.min()) < k and time.perf_counter_ns() < t_end:
                time.sleep(1e-5)
            gate_ns.append(time.perf_counter_ns() - q0)
        tick, t_tick = sensor.grab()
        g = time.perf_counter_ns()
        grab_ns.append(g); tick_ns_l.append(t_tick)
        if last is not None:
            loop_ns.append(g - last)
        last = g
        if not gate_ring.can_write(k, 1):
            b0 = time.perf_counter_ns()
            while not gate_ring.can_write(k, 1):
                time.sleep(0.0002)
            blocked_ns.append(time.perf_counter_ns() - b0)
        j = tick % 30
        a = time.perf_counter_ns()
        if not off:
            s = ring.begin(k)
            view = ring.image_view(s, shape)
            if decode == "imdecode":
                np.copyto(view, cv2.imdecode(jpegs[j], cv2.IMREAD_COLOR))
            elif decode == "simplejpeg":
                simplejpeg.decode_jpeg(jbytes[j], colorspace="BGR", buffer=view)
            else:
                np.copyto(view, frames[j])
        if EXTRA_CPU_NS:
            e_end = time.perf_counter_ns() + EXTRA_CPU_NS
            while time.perf_counter_ns() < e_end:
                pass
        if fr is not None:
            fr.frame_metadata.frame_number[0] = k
            for i_ in range(31):
                fr.frame_metadata.timestamps[ts_names[i_ % len(ts_names)]][0] = time.perf_counter_ns()
        b = time.perf_counter_ns()
        if not off:
            # same overlay as skellycam opencv_get_frame.py L79-91 (draw_doubled_text: 2 x putText), in place in the slot
            txt = f"camera.id:{cam}, idx:{cam}, fr:{k}"
            cv2.putText(view, txt, (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 4)
            cv2.putText(view, txt, (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 255), 2)
            ring.commit(k, s, frame_number=k, tick_ns=t_tick, aux0=tick)
        if jring is not None:
            s2 = jring.begin(k)
            jring.bytes_view(s2, jpegs[j].size)[:] = jpegs[j]
            jring.commit(k, s2, frame_number=k, tick_ns=t_tick, nbytes=jpegs[j].size, aux0=tick)
        c = time.perf_counter_ns()
        dec_ns.append(b - a); pub_ns.append(c - b)
        ticks.append(tick)
        k += 1
        if cnt is not None:
            cnt[cam] = k
    el = time.perf_counter() - t0w
    offloop = None
    if off:
        time.sleep(0.1)  # let the decoders finish the last published frame
        dstop.set()
        for t_ in dthreads:
            t_.join(5)
        offloop = dict(n_decoder_threads=N_DEC, max_lag=DEC_MAX_LAG, decoded=dst["decoded"], decoded_fps=dst["decoded"] / el,
                       decode_skipped=dst["skipped"], torn=dst["torn"], decode_overlay_publish=pcm.stats_ms(dst["dec_ns"]),
                       tick_to_decoded=pcm.stats_ms(dst["lat_ns"]))
    out_q.put(dict(cam=cam, produced=k, achieved_fps=(k - 1) / el, sensor_skipped=sensor.skipped,
                   sensor_frames=int(ticks[-1] - ticks[0] + 1) if ticks else 0,
                   decode_into_slot=pcm.stats_ms(dst["dec_ns"]) if off else pcm.stats_ms(dec_ns),
                   overlay_and_publish=pcm.stats_ms(pub_ns), grab_interval=pcm.stats_ms(loop_ns),
                   block_events=len(blocked_ns), blocked_total_s=sum(blocked_ns) / 1e9, cpu_pct=100 * (time.process_time() - cpu0) / el,
                   offloop_decoder=offloop, grab_ns=grab_ns, tick_ns=tick_ns_l,
                   lockstep_gate_wait=pcm.stats_ms(gate_ns) if gate_ns else None, options=dict(
                       lockstep=cnt is not None, meta=fr is not None, recorder_thread=rec_args is not None, extra_cpu_ns=EXTRA_CPU_NS)))
    if cnt is not None:
        cnt[cam] = 1 << 60  # release the others' gates once this camera stops
    if rthread is not None:
        rthread.join()
    if cnt_shm is not None:
        del cnt
        cnt_shm.close()
    ring.close()
    if jring:
        jring.close()


def recorder(spec, jspec, cam, h, w, rec, path, ready_q, go, stop, out_q):
    import cv2
    import av
    import proto_common as pcm
    ring = pcm.SeqRing.attach(spec)
    jring = pcm.SeqRing.attach(jspec) if jspec else None
    src = jring if rec == "passthrough" else ring
    vw = c = st = None
    if rec == "msmf":
        vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"X264"), FPS, (w, h))
    else:
        c = av.open(str(path), "w")
        if rec == "passthrough":
            st = c.add_stream("mjpeg", rate=60)
            st.width, st.height, st.pix_fmt = w, h, "yuvj420p"
        else:
            st = c.add_stream("h264_nvenc", rate=60)
            st.width, st.height, st.pix_fmt = w, h, "yuv420p"
            st.options = {"preset": "p4", "tune": "ll", "rc": "vbr", "cq": "23"}
            i420 = np.empty((h * 3 // 2, w), np.uint8)
    ready_q.put(cam)
    go.wait()
    nxt = 0
    fns, lat, wl = [], [], []
    t_first = None
    cpu0 = time.process_time()
    t0 = time.perf_counter()
    while True:
        if nxt > src.head:
            if stop.is_set() and src.head < nxt:
                break
            time.sleep(0.0003)
            continue
        sl = nxt % src.L
        m = src.meta[sl]
        t_tick = int(m[pcm.F_TICK])
        a = time.perf_counter_ns()
        if rec == "msmf":
            vw.write(ring.image_view(sl, (h, w, 3)))
        elif rec == "passthrough":
            if t_first is None:
                t_first = t_tick
            pk = av.Packet(jring.bytes_view(sl, int(m[pcm.F_NBYTES])))
            pk.stream = st; pk.time_base = Fraction(1, 1000); pk.pts = pk.dts = (t_tick - t_first) // 1_000_000
            c.mux(pk)
        else:
            cv2.cvtColor(ring.image_view(sl, (h, w, 3)), cv2.COLOR_BGR2YUV_I420, dst=i420)
            f = av.VideoFrame.from_ndarray(i420, format="yuv420p"); f.pts = nxt
            for pk in st.encode(f):
                c.mux(pk)
        b = time.perf_counter_ns()
        fns.append(int(m[pcm.F_FN])); lat.append(b - t_tick); wl.append(b - a)
        src.set_cursor(0, nxt)
        nxt += 1
    loop_s = time.perf_counter() - t0
    r0 = time.perf_counter()
    if vw is not None:
        vw.release()
    else:
        if rec == "nvenc":
            for pk in st.encode():
                c.mux(pk)
        c.close()
    rel = time.perf_counter() - r0
    out_q.put(dict(cam=cam, recorded=len(fns), consecutive=bool(len(fns) < 2 or np.all(np.diff(fns) == 1)),
                   tick_to_written=pcm.stats_ms(lat), write_call=pcm.stats_ms(wl), release_s=rel,
                   cpu_pct=100 * (time.process_time() - cpu0) / (loop_s + rel)))
    ring.close()
    if jring:
        jring.close()


async def ui_relay(rings, h, w, run_s, stats):
    import cv2
    loop = asyncio.get_running_loop()
    pool = ThreadPoolExecutor(len(rings))
    small = [np.empty((h // 2, w // 2, 3), np.uint8) for _ in rings]
    out = [bytearray(8 << 20), bytearray(8 << 20)]
    flip = 0
    last = [-1] * len(rings)

    def enc(i, k):
        r = rings[i]
        cv2.resize(r.image_view(k % r.L, (h, w, 3)), (w // 2, h // 2), dst=small[i], interpolation=cv2.INTER_LINEAR)
        return cv2.imencode(".jpg", small[i], [int(cv2.IMWRITE_JPEG_QUALITY), 60])[1]
    t_end = time.perf_counter() + run_s
    while time.perf_counter() < t_end:
        await asyncio.sleep(0.01)
        ks = [r.head for r in rings]
        if any(k <= lk for k, lk in zip(ks, last)):
            stats["skipped"] += 1
            continue
        seqs = [int(r.meta[k % r.L, 0]) for r, k in zip(rings, ks)]
        a = time.perf_counter_ns()
        parts = await asyncio.gather(*[loop.run_in_executor(pool, enc, i, k) for i, k in enumerate(ks)])
        b = time.perf_counter_ns()
        ok = all(s == 2 * k + 2 and int(r.meta[k % r.L, 0]) == s for r, k, s in zip(rings, ks, seqs))
        buf = out[flip]; flip ^= 1
        mv = memoryview(buf); pos = 24
        for p in parts:
            pb = memoryview(p).cast("B")
            pos += 56
            mv[pos:pos + len(pb)] = pb
            pos += len(pb)
        pos += 24
        e = time.perf_counter_ns()
        stats["build_ns"].append(e - a); stats["blocked_ns"].append((e - a) - (b - a)); stats["t"].append(e)
        stats["sizes"].append(pos); stats["invalid"] += int(not ok)
        stats["age_ns"].append(e - min(int(r.meta[k % r.L, 2]) for r, k in zip(rings, ks)))
        last = ks
    pool.shutdown()


def run(size_name, decode, rec, run_s):
    import proto_common as pcm
    h, w = pcm.SIZES[size_name]
    ctx = mp.get_context("spawn")
    L = (1024 ** 3) // (632 + h * w * 3)
    rings = [pcm.SeqRing.create(L, h * w * 3, prefault=True) for _ in range(N_CAMS)]
    jrings = [pcm.SeqRing.create(1024, JSLOT, prefault=True) for _ in range(N_CAMS)] if rec == "passthrough" else [None] * N_CAMS
    ext = {"msmf": "mp4", "passthrough": "mkv", "nvenc": "mp4"}[rec]
    paths = [pcm.SCRATCH_TMP / f"p8_{size_name}_{decode}_{rec}_cam{i}.{ext}" for i in range(N_CAMS)]
    rq, oc, orr = ctx.Queue(), ctx.Queue(), ctx.Queue()
    go, stop = ctx.Event(), ctx.Event()
    from multiprocessing import shared_memory as _shm
    cnt_shm = _shm.SharedMemory(create=True, size=8 * N_CAMS) if LOCKSTEP else None
    if cnt_shm is not None:
        np.ndarray((N_CAMS,), np.int64, buffer=cnt_shm.buf)[:] = 0
    rargs = [(rings[i].spec(), jrings[i].spec() if jrings[i] else None, i, h, w, rec, paths[i], rq, go, stop, orr) for i in range(N_CAMS)]
    cams = [ctx.Process(target=camera, args=(rings[i].spec(), jrings[i].spec() if jrings[i] else None, i, h, w, decode, rec, run_s, rq, go, oc,
                                             cnt_shm.name if cnt_shm else None, rargs[i] if RECTHREAD else None))
            for i in range(N_CAMS)]
    recs = [] if RECTHREAD else [ctx.Process(target=recorder, args=rargs[i]) for i in range(N_CAMS)]
    for p in cams + recs:
        p.start()
    for _ in range(2 * N_CAMS):
        rq.get(timeout=300)
    import psutil
    samples = []
    cs = threading.Event()
    pids = [p.pid for p in cams + recs] + [os.getpid()]
    th = threading.Thread(target=pcm.cpu_sampler, args=(pids, cs, samples), daemon=True)
    th.start()
    ui = dict(build_ns=[], blocked_ns=[], t=[], sizes=[], invalid=0, skipped=0, age_ns=[])
    go.set()
    asyncio.run(ui_relay(rings, h, w, run_s, ui))
    cres = sorted([oc.get(timeout=120) for _ in cams], key=lambda r: r["cam"])
    stop.set()
    rres = sorted([orr.get(timeout=300) for _ in recs], key=lambda r: r["cam"])
    cs.set()
    for p in cams + recs:
        p.join(30)
    for r in rings + [j for j in jrings if j]:
        r.close()
    if cnt_shm is not None:
        cnt_shm.close()
        cnt_shm.unlink()
    # cross-camera spread per frame number (frames every camera produced)
    nmin = min(len(c["grab_ns"]) for c in cres)
    G = np.array([c["grab_ns"][:nmin] for c in cres], np.int64)
    T = np.array([c["tick_ns"][:nmin] for c in cres], np.int64)
    spread = dict(frames=int(nmin), grab_spread=pcm.stats_ms(G.max(0) - G.min(0)), tick_spread=pcm.stats_ms(T.max(0) - T.min(0)),
                  note="tick_spread = max - min over cameras of the sensor tick time of the frame each camera produced as "
                       "frame number k (capture-instant spread of multiframe k); grab_spread = same for grab() return times")
    for c in cres:
        c.pop("grab_ns")
        c.pop("tick_ns")
    cpu = pcm.summarize_cpu(samples)
    cam_p, rec_p = {str(p.pid) for p in cams}, {str(p.pid) for p in recs}
    cpu_split = dict(cameras=sum(v for k, v in cpu.items() if k in cam_p), recorders=sum(v for k, v in cpu.items() if k in rec_p),
                     main=cpu.get(str(os.getpid())), system=cpu["system"]) if cpu else None
    files = []
    for i, p in enumerate(paths):
        files.append(dict(file=p.name, bytes=p.stat().st_size, decoded_frames=pcm.count_video_frames(p),
                          produced=cres[i]["produced"], recorded=rres[i]["recorded"]))
    sizes_before_delete = {f["file"]: f["bytes"] for f in files}
    for p in paths:
        p.unlink()
    el = (ui["t"][-1] - ui["t"][0]) / 1e9 if len(ui["t"]) > 1 else float("nan")
    ui_sum = dict(payloads=len(ui["t"]), payload_fps=len(ui["t"]) / el if el == el else None, build=pcm.stats_ms(ui["build_ns"]),
                  event_loop_blocked=pcm.stats_ms(ui["blocked_ns"]), age_when_ready=pcm.stats_ms(ui["age_ns"]),
                  payload_bytes_median=float(np.median(ui["sizes"])) if ui["sizes"] else None, invalid=ui["invalid"])
    return dict(size=size_name, decode=decode, recorder=rec, run_s=run_s, n_cams=N_CAMS, ring_len=L, cameras=cres, recorders=rres,
                files=files, file_bytes_before_delete=sizes_before_delete, ui=ui_sum, cross_camera_spread=spread,
                options=dict(lockstep=LOCKSTEP, meta=META, recorder_thread=RECTHREAD, extra_cpu_ms=EXTRA_CPU_NS / 1e6), cpu_psutil_mean=cpu, cpu_split=cpu_split,
                min_cam_fps=min(c["achieved_fps"] for c in cres),
                sensor_never_grabbed_total=sum(c["sensor_skipped"] for c in cres),
                files_equal_produced=all(f["decoded_frames"] == f["produced"] for f in files),
                all_consecutive=all(r["consecutive"] for r in rres))


COPIES = {("imdecode", "msmf"): "cam: decode alloc + 1 copy into slot; rec: 0 (view to encoder)",
          ("imdecode", "passthrough"): "cam: decode alloc + 1 copy into slot + 1 JPEG copy; rec: 1 JPEG copy",
          ("imdecode", "nvenc"): "cam: decode alloc + 1 copy into slot; rec: I420 convert + from_ndarray copy (1.5 B/px each)",
          ("simplejpeg", "msmf"): "cam: 0 (decoder writes the slot); rec: 0",
          ("simplejpeg", "passthrough"): "cam: 0 + 1 JPEG copy; rec: 1 JPEG copy",
          ("simplejpeg", "nvenc"): "cam: 0; rec: I420 convert + from_ndarray copy",
          ("memcpy", "msmf"): "cam: 1 (stand-in copy into slot); rec: 0", ("memcpy", "passthrough"): "cam: 1 + 1 JPEG; rec: 1 JPEG",
          ("memcpy", "nvenc"): "cam: 1; rec: I420 + from_ndarray",
          ("imdecode_off", "passthrough"): "cam loop: 1 JPEG copy; decoder thread: decode alloc + 1 copy into BGR slot; rec: 1 JPEG copy"}


def offl(r):
    o = [c.get("offloop_decoder") for c in r["cameras"]]
    if not o or o[0] is None:
        return "-"
    return f"{min(x['decoded_fps'] for x in o):.2f} / {sum(x['decode_skipped'] for x in o)}"


def summarize():
    import proto_common as pcm
    rows = []
    for p in sorted(pcm.RESULTS.glob(os.environ.get("P8_SUMMARY_GLOB", "p8_e2e_*.json"))):
        d = json.loads(p.read_text())
        d["_file"] = p.name
        rows.append(d)
    L = ["# P8 - end-to-end prototype (5 cameras x 60 fps FakeSensor, decoupled recorders, seqlock ring, threaded UI)", "",
         "Directly comparable with baseline/results/e_e2e_summary.md (same sensor model, content, overlay, writer for msmf rows).", "",
         "| file | size | decode into slot | recorder | per-cam fps (min) | sensor frames never grabbed (sum) | files decode == produced | consecutive | decode median / p99 ms | overlay+publish median ms | grab interval p99 / max ms | tick->written median / p99 / max ms (worst cam) | UI payloads/s | UI build median / p99 ms | event-loop blocked median ms | CPU % cams / recorders / main | off-loop decoder: decoded fps (min cam) / skipped (sum) | copies per frame |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        dec = max(r["cameras"], key=lambda c: c["decode_into_slot"]["p99_ms"])["decode_into_slot"]
        gi = max(r["cameras"], key=lambda c: c["grab_interval"]["max_ms"])["grab_interval"]
        tw = max(r["recorders"], key=lambda x: x["tick_to_written"]["p99_ms"])["tick_to_written"]
        cs = r["cpu_split"] or {}
        u = r["ui"]
        L.append(f"| {r['_file']} | {r['size']} | {r['decode']} | {r['recorder']} | {r['min_cam_fps']:.2f} | {r['sensor_never_grabbed_total']} | "
                 f"{r['files_equal_produced']} | {r['all_consecutive']} | {dec['median_ms']:.2f} / {dec['p99_ms']:.2f} | "
                 f"{float(np.median([c['overlay_and_publish']['median_ms'] for c in r['cameras']])):.3f} | {gi['p99_ms']:.1f} / {gi['max_ms']:.1f} | "
                 f"{tw['median_ms']:.1f} / {tw['p99_ms']:.1f} / {tw['max_ms']:.1f} | {u['payload_fps']:.1f} | {u['build']['median_ms']:.2f} / {u['build']['p99_ms']:.2f} | "
                 f"{u['event_loop_blocked']['median_ms']:.3f} | {cs.get('cameras', float('nan')):.0f} / {cs.get('recorders', float('nan')):.0f} / {cs.get('main') or float('nan'):.0f} | "
                 f"{offl(r)} | {COPIES.get((r['decode'], r['recorder']), '')} |")
    L += ["", "Baseline rows to compare (baseline/results/e_e2e_summary.md, idle 20261027 re-run, real SkellyCam stack): 1080p mjpeg+UI 53.56 / 53.57 fps, "
          "964 / 964 sensor frames never grabbed, tick->written 23.9 / 34.4 / 37.4 ms, UI 36.9 / 36.6 payloads/s (build 15.2 ms), children CPU 1345 / 1361 %, "
          "main 131 / 134 %; 1080p mjpeg no UI 55.94 fps, 605 never grabbed; 1080p memcpy+UI 59.99 / 59.99 fps, 0 / 0 never grabbed, UI 39.9 / 40.8/s, "
          "children CPU 994 / 928 %; 720p mjpeg+UI 60.00 fps, 0 never grabbed, UI 57.0/s, tick->written 5.5 / 7.7 / 10.9 ms."]
    pcm.write_text(os.environ.get("P8_SUMMARY_OUT", "p8_e2e_summary.md"), "\n".join(L) + "\n")
    print("\n".join(L))


def main():
    import proto_common as pcm
    if "--summarize" in sys.argv:
        return summarize()
    size_name = sys.argv[1] if len(sys.argv) > 1 else "1080p"
    decode = sys.argv[2] if len(sys.argv) > 2 else "imdecode"
    rec = sys.argv[3] if len(sys.argv) > 3 else "msmf"
    run_s = float(sys.argv[4]) if len(sys.argv) > 4 else 30.0
    env = pcm.env_summary()
    r = run(size_name, decode, rec, run_s)
    r["env"] = env
    tag = f"{os.environ.get('P8_PREFIX', 'p8_e2e_')}{size_name}_{decode}_{rec}{os.environ.get('P8_REP', '')}.json"
    pcm.write_json(tag, r)
    print(f"RESULT {size_name} {decode} {rec}: min fps {r['min_cam_fps']:.2f}, never grabbed {r['sensor_never_grabbed_total']}, files==produced "
          f"{r['files_equal_produced']}, consecutive {r['all_consecutive']}, UI {r['ui']['payload_fps']:.1f}/s build {r['ui']['build']['median_ms']:.2f} ms, "
          f"cpu {r['cpu_split']}")
    for c, rr in zip(r["cameras"], r["recorders"]):
        print(f"  cam{c['cam']}: fps {c['achieved_fps']:.2f} skipped {c['sensor_skipped']} dec {c['decode_into_slot']['median_ms']:.2f}/{c['decode_into_slot']['p99_ms']:.2f} "
              f"pub {c['overlay_and_publish']['median_ms']:.3f} block_events {c['block_events']} | rec {rr['recorded']} tick->written "
              f"{rr['tick_to_written']['median_ms']:.1f}/{rr['tick_to_written']['p99_ms']:.1f}/{rr['tick_to_written']['max_ms']:.1f} write {rr['write_call']['median_ms']:.2f}/{rr['write_call']['p99_ms']:.2f}")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
