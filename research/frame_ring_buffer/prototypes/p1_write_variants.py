"""P1 - camera-process write path: decode/capture + publish into shared memory, current vs prototypes.

N=5 spawned writer processes (multiprocessing spawn, like SkellyCam camera workers) run UNTHROTTLED for RUN_S seconds
after a warm-up, at 1280x720 and 1920x1080 BGR. Each iteration = "get the next camera frame into shm":

  variant                         what one iteration does                                        full-frame copies after decode
  cur_imdecode_putframe     [S]   cv2.imdecode(q90 JPEG) -> np.copyto(private recarray.image)     3 (copyto private, copy.copy, slot)
                                  -> REAL CameraSharedMemoryRingBuffer.put_frame(overwrite=True)    (= baseline e2e mjpeg stand-in + put_frame)
  cur_memcpy_putframe       [S]   np.copyto(private, frame) -> REAL put_frame                     2 (+1 stand-in memcpy)
  cur_vcap_putframe         [S]   cv2.VideoCapture(MJPEG .avi, CAP_FFMPEG).grab()+retrieve(image=private) -> REAL put_frame   2
  p_imdecode_copyslot             cv2.imdecode -> np.copyto(SeqRing slot view) -> seq commit        1
  p_memcpy_slot                   np.copyto(slot view, frame) -> seq commit                          1 (the stand-in memcpy itself)
  p_vcap_into_slot                VideoCapture.grab()+retrieve(image=SeqRing slot view) -> commit   0 (decoder writes the slot)
  p_simplejpeg_into_slot    [B]   simplejpeg.decode_jpeg(buffer=slot view, colorspace=BGR) -> commit 0 (libjpeg-turbo writes the slot)
  (added in the 2026-10-28 re-run; these use the REAL SkellyCam ring with ONE method replaced on the instance, in-process only)
  cur_memcpy_putdata_nocopycopy [S] as cur_memcpy_putframe, but put_data without `copy(data)` (ring_buffer_shared_memory.py L132)   2
  cur_memcpy_putdata_u8copyto   [S] as cur_memcpy_putframe, but the slot write is np.copyto between flat uint8 views of the record  2
  cur_vcap_into_sk_slot         [S] retrieve(image=<SkellyCam ring slot .image view>) + frame_number in place + last_written_index   0
  Note: cv2.imdecode has no dst argument in OpenCV 4.12's Python binding (verified: "imdecode() takes at most 2 arguments"), so
  decode-into-slot needs VideoCapture.retrieve(image=), simplejpeg(buffer=) or a native decoder.

  [S] needs the SkellyCam venv (real SkellyCam classes);  [B] needs simplejpeg (bench venv).  Variants that cannot run in
  the current interpreter are skipped; run the script in both venvs, then `--summarize` merges the two JSON files.

"decode into a preallocated destination" is how a real capture path would avoid the intermediate ndarray. No camera is
used here: cv2.VideoCapture over an MJPEG AVI (CAP_FFMPEG) is the real VideoCapture.retrieve(image=...) API (in-place
write verified per process via np.shares_memory + pointer), and simplejpeg's buffer= is libjpeg-turbo decoding in place.
JPEG content: baseline synthetic_frames(noise=8) encoded with cv2.imencode q90, 30 distinct frames cycled (same as the
baseline e2e FakeCapture). SeqRing (proto_common.py) slots = same count as SkellyCam's 1 GiB ring (388 / 172), prefaulted.

Run (from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam):
  .venv\\Scripts\\python.exe research\\frame_ring_buffer\\prototypes\\p1_write_variants.py
  research\\frame_ring_buffer\\.venv-bench\\Scripts\\python.exe research\\frame_ring_buffer\\prototypes\\p1_write_variants.py
  .venv\\Scripts\\python.exe research\\frame_ring_buffer\\prototypes\\p1_write_variants.py --summarize
"""
from __future__ import annotations

import multiprocessing as mp
import multiprocessing.queues  # noqa: F401  (skellycam type_overloads.py L23 workaround, see baseline README)
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

N_CAMS = 5
RUN_S = float(os.environ.get("P1_RUN_S", "10"))
WARM_S = 2.0
ONE_GIB = 1024 ** 3


def have_skellycam():
    try:
        import skellycam  # noqa: F401
        return True
    except Exception:
        return False


def have_simplejpeg():
    try:
        import simplejpeg  # noqa: F401
        return True
    except Exception:
        return False


VARIANTS = [
    ("cur_imdecode_putframe", "S"), ("cur_memcpy_putframe", "S"), ("cur_vcap_putframe", "S"),
    ("cur_memcpy_putdata_nocopycopy", "S"), ("cur_memcpy_putdata_u8copyto", "S"), ("cur_vcap_into_sk_slot", "S"),
    ("p_imdecode_copyslot", ""), ("p_memcpy_slot", ""), ("p_vcap_into_slot", ""), ("p_simplejpeg_into_slot", "B"),
]
COPIES_AFTER_DECODE = {"cur_imdecode_putframe": 3, "cur_memcpy_putframe": 3, "cur_vcap_putframe": 2,
                       "cur_memcpy_putdata_nocopycopy": 2, "cur_memcpy_putdata_u8copyto": 2, "cur_vcap_into_sk_slot": 0,
                       "p_imdecode_copyslot": 1, "p_memcpy_slot": 1, "p_vcap_into_slot": 0, "p_simplejpeg_into_slot": 0}
COPY_NOTE = {"cur_imdecode_putframe": "imdecode output -> private recarray (1) + copy.copy (2) + slot assignment (3)",
             "cur_memcpy_putframe": "stand-in memcpy into private (1) + copy.copy (2) + slot assignment (3)",
             "cur_vcap_putframe": "retrieve writes the private recarray in place; copy.copy (1) + slot assignment (2)",
             "cur_memcpy_putdata_nocopycopy": "stand-in memcpy into private (1) + slot assignment (2); copy.copy removed",
             "cur_memcpy_putdata_u8copyto": "stand-in memcpy into private (1) + np.copyto of the record as uint8 bytes (2); copy.copy removed",
             "cur_vcap_into_sk_slot": "retrieve writes straight into the SkellyCam ring slot's image field; metadata written in place",
             "p_imdecode_copyslot": "imdecode output -> slot (1)",
             "p_memcpy_slot": "the stand-in memcpy goes straight into the slot (1)"}


def _put_data_nocopycopy(self, data, overwrite_allowed: bool = False):
    """SharedMemoryRingBuffer.put_data (ring_buffer_shared_memory.py L118-133 @23ccbf20) with `copy(data)` removed.
    Bound onto ONE instance inside the benchmark process; SkellyCam source is not modified."""
    if self.read_only:
        raise ValueError("read-only")
    if data.dtype != self.dtype:
        raise ValueError("dtype")
    index_to_write = self.last_written_index.value + 1
    if self._check_for_overwrite(index_to_write) and not overwrite_allowed:
        raise ValueError("overwrite")
    self.ring_shm.buffer[index_to_write % self.ring_buffer_length] = data
    self.last_written_index.value = index_to_write


def _make_put_data_u8copyto(sk):
    """Same as above but the slot write is one np.copyto between flat uint8 views of the record (no structured-dtype
    assignment path)."""
    L = sk.ring_buffer_length
    slots_u8 = sk.ring_shm.buffer.view(np.uint8).reshape(L, sk.dtype.itemsize)

    def put_data(data, overwrite_allowed: bool = False):
        if data.dtype != sk.dtype:
            raise ValueError("dtype")
        index_to_write = sk.last_written_index.value + 1
        if sk._check_for_overwrite(index_to_write) and not overwrite_allowed:
            raise ValueError("overwrite")
        np.copyto(slots_u8[index_to_write % L], data.view(np.uint8).reshape(-1))
        sk.last_written_index.value = index_to_write
    return put_data


def make_mjpeg_avi(path: Path, jpegs, h, w, n_frames=300):
    import av
    c = av.open(str(path), "w", format="avi")
    st = c.add_stream("mjpeg", rate=60)
    st.width, st.height = w, h
    st.pix_fmt = "yuvj420p"
    for i in range(n_frames):
        pkt = av.Packet(bytes(jpegs[i % len(jpegs)]))
        pkt.stream = st
        pkt.pts = pkt.dts = i
        c.mux(pkt)
    c.close()


def writer(variant, cam, h, w, spec, dto, avi_path, ready_q, start_evt, result_q):
    import cv2
    import proto_common as pcm
    cv2.setNumThreads(1)  # one camera process = one core's worth of decode, like a per-camera worker
    frames = pcm.synthetic_frames(h, w, n=30, seed=cam, noise=8)
    jpegs = [cv2.imencode(".jpg", f, [int(cv2.IMWRITE_JPEG_QUALITY), 90])[1] for f in frames]
    jbytes = [j.tobytes() for j in jpegs]
    pc = time.perf_counter_ns
    shape = (h, w, 3)
    info = {}
    ring = None
    sk = None
    if variant.startswith("cur_"):
        import bench_common as bc
        from skellycam.core.ipc.shared_memory.camera_shared_memory_ring_buffer import CameraSharedMemoryRingBuffer
        sk = CameraSharedMemoryRingBuffer.recreate(dto=dto, read_only=False)
        fr = bc.make_frame_recarray(bc.make_config(cam, h, w))
        priv = fr.image[0]
        if variant == "cur_memcpy_putdata_nocopycopy":
            import types
            sk.put_data = types.MethodType(_put_data_nocopycopy, sk)
        elif variant == "cur_memcpy_putdata_u8copyto":
            sk.put_data = _make_put_data_u8copyto(sk)
        elif variant == "cur_vcap_into_sk_slot":
            sk_L = sk.ring_buffer_length
            sk_images = sk.ring_shm.buffer.image          # (L, h, w, 3) view of every slot's image field
            sk_fn = sk.ring_shm.buffer.frame_metadata.frame_number  # (L,) view
            sk_md = sk.ring_shm.buffer.frame_metadata
            sk_md[:] = fr.frame_metadata[0]                # camera_info etc. once, as put_frame would carry them
    else:
        ring = pcm.SeqRing.attach(spec)
    cap = None
    if "vcap" in variant:
        cap = cv2.VideoCapture(str(avi_path), cv2.CAP_FFMPEG)
        info["vcap_backend"] = cap.getBackendName()
    if variant == "p_simplejpeg_into_slot":
        import simplejpeg
    k = 0

    def one():
        nonlocal k
        t0 = pc()
        j = k % 30
        if variant == "cur_imdecode_putframe":
            np.copyto(priv, cv2.imdecode(jpegs[j], cv2.IMREAD_COLOR)); t1 = pc()
            fr.frame_metadata.frame_number[0] = k
            sk.put_frame(frame_rec_array=fr, overwrite=True)
        elif variant in ("cur_memcpy_putframe", "cur_memcpy_putdata_nocopycopy", "cur_memcpy_putdata_u8copyto"):
            np.copyto(priv, frames[j]); t1 = pc()
            fr.frame_metadata.frame_number[0] = k
            sk.put_frame(frame_rec_array=fr, overwrite=True)  # put_data replaced on this instance for the two proto rows
        elif variant == "cur_vcap_into_sk_slot":
            idx = sk.last_written_index.value + 1
            if not cap.grab():
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0); cap.grab()
            cap.retrieve(image=sk_images[idx % sk_L]); t1 = pc()
            sk_fn[idx % sk_L] = k
            sk.last_written_index.value = idx  # publish (same index store put_data does)
        elif variant == "cur_vcap_putframe":
            if not cap.grab():
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0); cap.grab()
            cap.retrieve(image=priv); t1 = pc()
            fr.frame_metadata.frame_number[0] = k
            sk.put_frame(frame_rec_array=fr, overwrite=True)
        else:
            s = ring.begin(k)
            view = ring.image_view(s, shape)
            if variant == "p_imdecode_copyslot":
                np.copyto(view, cv2.imdecode(jpegs[j], cv2.IMREAD_COLOR))
            elif variant == "p_memcpy_slot":
                np.copyto(view, frames[j])
            elif variant == "p_vcap_into_slot":
                if not cap.grab():
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0); cap.grab()
                cap.retrieve(image=view)
            elif variant == "p_simplejpeg_into_slot":
                simplejpeg.decode_jpeg(jbytes[j], colorspace="BGR", buffer=view)
            t1 = pc()
            ring.commit(k, s, frame_number=k, tick_ns=t0)
        t2 = pc()
        k += 1
        return t0, t1, t2

    # in-place / content verification for the prototype variants
    if variant in ("cur_memcpy_putdata_nocopycopy", "cur_memcpy_putdata_u8copyto"):
        np.copyto(priv, frames[7]); fr.frame_metadata.frame_number[0] = 12345
        sk.put_frame(frame_rec_array=fr, overwrite=True)
        got = sk.get_latest_data(None)
        info["inplace_verified"] = bool(np.array_equal(got.image[0], frames[7]) and int(got.frame_metadata.frame_number[0]) == 12345
                                        and got.tobytes() == fr.tobytes())  # whole record identical, metadata included
    if variant == "cur_vcap_into_sk_slot":
        idx = sk.last_written_index.value + 1
        view = sk_images[idx % sk_L]; view[:] = 0
        cap.grab(); ok, out = cap.retrieve(image=view)
        sk.last_written_index.value = idx
        got = sk.get_latest_data(None)
        info["inplace_verified"] = bool(out is not None and out.__array_interface__["data"][0] == view.__array_interface__["data"][0]
                                        and int(got.image[0].sum(dtype=np.int64)) > 0 and np.array_equal(got.image[0], out))
    if variant == "p_vcap_into_slot":
        s = 0; view = ring.image_view(s, shape); view[:] = 0
        cap.grab(); ok, out = cap.retrieve(image=view)
        info["inplace_verified"] = bool(out is not None and np.shares_memory(out, view)
                                        and out.__array_interface__["data"][0] == view.__array_interface__["data"][0]
                                        and int(view.sum(dtype=np.int64)) > 0)
    if variant == "p_simplejpeg_into_slot":
        s = 0; view = ring.image_view(s, shape); view[:] = 0
        out = simplejpeg.decode_jpeg(jbytes[0], colorspace="BGR", buffer=view)
        ref = cv2.imdecode(jpegs[0], cv2.IMREAD_COLOR)
        info["inplace_verified"] = bool(np.shares_memory(out, view) and int(view.sum(dtype=np.int64)) > 0)
        info["max_abs_diff_vs_cv2_imdecode"] = int(np.abs(view.astype(np.int16) - ref.astype(np.int16)).max())
    # warm-up: one full ring lap (first-touch) + WARM_S
    L = sk.ring_buffer_length if sk is not None else ring.L
    for _ in range(L):
        one()
    tw = pc() + int(WARM_S * 1e9)
    while pc() < tw:
        one()
    ready_q.put(cam)
    start_evt.wait()
    dec, pub, tot = [], [], []
    cpu0 = time.process_time()
    t_start = pc()
    deadline = t_start + int(RUN_S * 1e9)
    while True:
        t0, t1, t2 = one()
        dec.append(t1 - t0); pub.append(t2 - t1); tot.append(t2 - t0)
        if t2 >= deadline:
            break
    el = (pc() - t_start) / 1e9
    cpu = time.process_time() - cpu0
    n = len(tot)
    if cap is not None:
        cap.release()
    result_q.put(dict(cam=cam, n=n, elapsed_s=el, fps=n / el, cpu_ms_per_frame=1000 * cpu / n,
                      cpu_pct=100 * cpu / el, decode_or_capture=pcm.stats_ms(dec), publish=pcm.stats_ms(pub),
                      total=pcm.stats_ms(tot), ring_len=L, **info))
    if sk is not None:
        sk.close()
    else:
        ring.close()


def run(variant, size_name):
    import cv2
    import proto_common as pcm
    h, w = pcm.SIZES[size_name]
    ctx = mp.get_context("spawn")
    ring = None
    skshm = None
    dtos = {}
    specs = {}
    rings = []
    if variant.startswith("cur_"):
        import bench_common as bc
        from skellycam.core.ipc.shared_memory.camera_group_shared_memory import CameraGroupSharedMemory
        from skellycam.core.timestamps.timebase_mapping import TimebaseMapping
        configs = {str(i): bc.make_config(i, h, w) for i in range(N_CAMS)}
        skshm = CameraGroupSharedMemory.create(camera_configs=configs, timebase_mapping=TimebaseMapping(), read_only=True)
        dtos = skshm.camera_shm_dtos
    else:
        rec_bytes = 632 + h * w * 3  # same per-slot budget as a SkellyCam record -> same slot count for 1 GiB
        L = ONE_GIB // rec_bytes
        for i in range(N_CAMS):
            r = pcm.SeqRing.create(L, h * w * 3, prefault=True)
            rings.append(r)
            specs[str(i)] = r.spec()
    avi = {}
    if "vcap" in variant:
        for i in range(N_CAMS):
            frames = pcm.synthetic_frames(h, w, n=30, seed=i, noise=8)
            jpegs = [cv2.imencode(".jpg", f, [int(cv2.IMWRITE_JPEG_QUALITY), 90])[1] for f in frames]
            p = pcm.SCRATCH_TMP / f"p1_{size_name}_cam{i}.avi"
            make_mjpeg_avi(p, jpegs, h, w)
            avi[str(i)] = p
    ready_q, result_q, start_evt = ctx.Queue(), ctx.Queue(), ctx.Event()
    procs = [ctx.Process(target=writer, args=(variant, i, h, w, specs.get(str(i)), dtos.get(str(i)), avi.get(str(i)),
                                              ready_q, start_evt, result_q)) for i in range(N_CAMS)]
    for p in procs:
        p.start()
    for _ in procs:
        ready_q.get(timeout=300)
    start_evt.set()
    res = sorted([result_q.get(timeout=300) for _ in procs], key=lambda r: r["cam"])
    for p in procs:
        p.join(30)
    if skshm is not None:
        skshm.unlink_and_close()
    for r in rings:
        r.close()
    avi_bytes = {k: v.stat().st_size for k, v in avi.items()}
    for v in avi.values():
        v.unlink()
    fb = h * w * 3
    agg = sum(r["fps"] for r in res)
    return dict(variant=variant, size=size_name, n_cams=N_CAMS, run_s=RUN_S, per_camera=res,
                min_cam_fps=min(r["fps"] for r in res), aggregate_fps=agg, aggregate_GBps_frames=agg * fb / 1e9,
                median_total_ms=float(np.median([r["total"]["median_ms"] for r in res])),
                worst_p99_total_ms=max(r["total"]["p99_ms"] for r in res),
                median_decode_ms=float(np.median([r["decode_or_capture"]["median_ms"] for r in res])),
                median_publish_ms=float(np.median([r["publish"]["median_ms"] for r in res])),
                worst_p99_publish_ms=max(r["publish"]["p99_ms"] for r in res),
                cpu_ms_per_frame=float(np.median([r["cpu_ms_per_frame"] for r in res])),
                full_frame_copies_after_decode=COPIES_AFTER_DECODE[variant], copy_note=COPY_NOTE.get(variant, ""),
                avi_bytes=avi_bytes, inplace_verified=[r.get("inplace_verified") for r in res])


def summarize():
    import json
    import proto_common as pcm
    rows = []
    envs = {}
    for tag in ("skellycamvenv", "benchvenv"):
        p = pcm.RESULTS / f"p1_write_{tag}.json"
        if p.exists():
            d = json.loads(p.read_text())
            envs[tag] = {k: d["env"].get(k) for k in ("time", "system_cpu_pct_1s_before_run", "executable", "simplejpeg")}
            rows += [dict(r, venv=tag) for r in d["rows"]]
    order = [v for v, _ in VARIANTS]
    rows.sort(key=lambda r: (r["size"], order.index(r["variant"])))
    L = ["# P1 - camera write path: decode/capture + publish into shm (5 spawned processes, unthrottled)",
         "", f"RUN_S={RUN_S}s per config after 1 ring lap + {WARM_S}s warm-up; cv2.setNumThreads(1) per process; 30 distinct q90 JPEGs.",
         "`total` = decode/capture + publish per frame. `publish` = everything after the pixels exist (put_frame, or seq commit).",
         "", "| size | variant | venv | per-cam fps (min) | total median / worst p99 ms | decode/capture median ms | publish median / worst p99 ms | CPU ms/frame | full-frame copies after decode | which copies | in-place / content verified |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['size']} | {r['variant']} | {r['venv']} | {r['min_cam_fps']:.0f} | {r['median_total_ms']:.3f} / {r['worst_p99_total_ms']:.3f} | "
                 f"{r['median_decode_ms']:.3f} | {r['median_publish_ms']:.3f} / {r['worst_p99_publish_ms']:.3f} | {r['cpu_ms_per_frame']:.3f} | "
                 f"{r['full_frame_copies_after_decode']} | {r.get('copy_note', '')} | {r['inplace_verified'] if any(v is not None for v in r['inplace_verified']) else '-'} |")
    L += ["", "Environment (per run): " + json.dumps(envs)]
    pcm.write_text("p1_write.md", "\n".join(L) + "\n")
    print("\n".join(L))


def main():
    import proto_common as pcm
    if "--summarize" in sys.argv:
        summarize(); return
    sk, sj = have_skellycam(), have_simplejpeg()
    tag = "skellycamvenv" if sk else "benchvenv"
    sel = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = {"env": pcm.env_summary(), "run_s": RUN_S, "rows": []}
    for size_name in ("720p", "1080p"):
        for v, need in VARIANTS:
            if sel and v not in sel:
                continue
            if (need == "S" and not sk) or (need == "B" and not sj):
                continue
            if tag == "benchvenv" and need == "" and v != "p_imdecode_copyslot":
                continue  # the venv-independent variants run once (skellycam venv) + one cross-check row here
            r = run(v, size_name)
            out["rows"].append(r)
            pcm.write_json(f"p1_write_{tag}.json", out)
            print(f"{size_name} {v}: min fps {r['min_cam_fps']:.0f}, total {r['median_total_ms']:.3f}/{r['worst_p99_total_ms']:.3f} ms, "
                  f"decode {r['median_decode_ms']:.3f}, publish {r['median_publish_ms']:.3f}/{r['worst_p99_publish_ms']:.3f}, "
                  f"cpu {r['cpu_ms_per_frame']:.3f} ms/f, inplace {r['inplace_verified']}", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
