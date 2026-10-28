"""(e-variants) Single-change variants of the baseline e2e run (bench_e_e2e.py), added by the 2026-10-28 REVISION stage.

Same real SkellyCam stack at 23ccbf20, same FakeCapture camera model, same analysis (bench_e_e2e.run / analyse are reused
unchanged). Each variant adds ONE benchmark-process-only monkeypatch (installed at import, so the spawned camera children,
which re-import this script as __mp_main__, get it too). SkellyCam source is not modified.

Variants (argv[1], comma-separated combinations allowed):
  head        : no extra patch (control run with the per-frame dump below)
  nocopycopy  : SharedMemoryRingBuffer.put_data with `copy(data)` removed (ring_buffer_shared_memory.py L132) = rank 8 alone
  cvthreads1  : cv2.setNumThreads(1) in every camera child (camera + inline recorder) = rank 9 alone
  extracpu3   : retrieve() busy-spins 3.0 ms of CPU after the decode (holds the GIL; single thread). Sensitivity stand-in for
                P9's real DSHOW retrieve CPU of 11.0-14.7 ms/frame at 1080p (stand-in decode alone is about 10 ms in e2e)
  dshowlike   : grab() returns at once; retrieve() waits for the next sensor tick, then decodes (the P9 real-DSHOW timing:
                grab 0.00-0.01 ms, retrieve about 32 ms). Throughput model unchanged; it moves where the wait is, so the
                pre_frame_grab_ns stamps no longer mark the frame's arrival.

Extra output: results/e2ev_<variant>_<size>_<mode>_<ui><rep>.json (same schema as e_e2e_*.json, NOT matched by
summarize_e2e.py's e_e2e_*.json glob) plus results/e2ev_<...>_perframe.npz with, per camera, the recorded frame numbers,
pre_frame_grab_ns, post_frame_retrieve_ns, post_frame_record_ns, the sensor tick and tick time of each recorded frame,
the full grab log (tick per grab), and the start/stop call times. The .npz is used by analyze_gap_detector.py
(rank-4 drop detector validation) and for the stop_recording pause gap.

Run (from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam):
  .venv\\Scripts\\python.exe research\\frame_ring_buffer\\baseline\\bench_e2e_variants.py nocopycopy 1080p mjpeg ui 30
  (env BENCH_E2E_REP=_rep2 to tag a repeat)
"""
from __future__ import annotations

import multiprocessing.queues  # noqa: F401  workaround for skellycam type_overloads.py L23
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

VARIANTS = set(filter(None, os.environ.get("BENCH_E2EV_VARIANT", "").split(",")))
EXTRA_CPU_NS = int(float(os.environ.get("BENCH_E2EV_EXTRA_CPU_MS", "3.0")) * 1e6)

import bench_e_e2e as base  # noqa: E402  (module-level code installs base FakeCapture when BENCH_E2E_FAKE=1)


def _put_data_nocopycopy(self, data, overwrite_allowed: bool = False):
    """SharedMemoryRingBuffer.put_data (ring_buffer_shared_memory.py L118-133 @23ccbf20) with `copy(data)` removed;
    identical to prototypes/p1_write_variants.py _put_data_nocopycopy (byte-identical slots verified there)."""
    if self.read_only:
        raise ValueError("Cannot write to read-only SharedMemoryRingBuffer.")
    if data.dtype != self.dtype:
        raise ValueError("dtype mismatch")
    index_to_write = self.last_written_index.value + 1
    if self._check_for_overwrite(index_to_write) and not overwrite_allowed:
        raise ValueError("overwrite")
    self.ring_shm.buffer[index_to_write % self.ring_buffer_length] = data
    self.last_written_index.value = index_to_write


class VariantCapture(base.FakeCapture):
    def grab(self):
        if "dshowlike" in VARIANTS:
            self._grab_call_ns = time.perf_counter_ns()
            return True
        return super().grab()

    _in_read = False

    def read(self, image=None):
        # base read() = _next_tick + retrieve; keep the grab log one entry per loop frame (fix 2026-10-28: the first
        # dshowlike run logged read() calls made during setup too, shifting its tick index; that run is superseded)
        self._in_read = True
        try:
            return super().read(image)
        finally:
            self._in_read = False

    def retrieve(self, image=None, flag=None):
        if "dshowlike" in VARIANTS and not self._in_read:
            tick, skipped = self._next_tick()
            if self.grab_log:
                self.skipped_ticks_during_grabs += skipped
            self.grab_log.append((int(tick), int(self.t0 + tick * self.period), time.perf_counter_ns()))
        ok, img = super().retrieve(image, flag)
        if "extracpu3" in VARIANTS:
            end = time.perf_counter_ns() + EXTRA_CPU_NS
            x = 0
            while time.perf_counter_ns() < end:
                x += 1
        return ok, img


def _fake_create(config, retry_count: int = 5):
    return VariantCapture(config), config


def _install():
    import skellycam.core.camera.opencv.opencv_helpers.setup_opencv_camera_loop as setup_mod
    import skellycam.core.camera.opencv.opencv_camera_loop as loop_mod
    setup_mod.create_cv2_video_capture = _fake_create
    loop_mod.create_cv2_video_capture = _fake_create
    if "nocopycopy" in VARIANTS:
        from skellycam.core.ipc.shared_memory.ring_buffer_shared_memory import SharedMemoryRingBuffer
        SharedMemoryRingBuffer.put_data = _put_data_nocopycopy
    if "cvthreads1" in VARIANTS and __name__ != "__main__":  # camera children only (spawn imports us as __mp_main__)
        import cv2
        cv2.setNumThreads(1)


if os.environ.get("BENCH_E2E_FAKE") == "1":
    _install()


def main():
    import asyncio
    import shutil
    import bench_common as bc
    variant = sys.argv[1]
    size_name = sys.argv[2] if len(sys.argv) > 2 else "1080p"
    ui = (sys.argv[4] if len(sys.argv) > 4 else "ui") == "ui"
    record_s = float(sys.argv[5]) if len(sys.argv) > 5 else 30.0
    tag = f"e2ev_{variant.replace(',', '+')}_{size_name}_{base.RETRIEVE_MODE}_{'ui' if ui else 'noui'}" + os.environ.get("BENCH_E2E_REP", "")
    raw = asyncio.run(base.run(size_name, ui, record_s))
    # per-frame dump BEFORE analyse/cleanup
    caplogs = {}
    for p in Path(base.CAP_LOG_DIR).glob("cap_*.json"):
        d = json.loads(p.read_text())
        caplogs.setdefault(d["camera_id"], []).append(d)
    dump = {"t_rec_start_call": np.array(raw["t_rec_start_call"], np.int64), "t_stop_call": np.array(raw["t_stop_call"], np.int64)}
    for cam, mlist in sorted(base.CAPTURED_METADATA.items()):
        fn, ts = base._meta_arrays(mlist)
        logs = caplogs.get(cam, [])
        log = np.asarray(max(logs, key=lambda d: len(d["grab_log"]))["grab_log"], np.int64) if logs else np.zeros((0, 3), np.int64)
        sel = fn[(fn >= 0) & (fn < len(log))]
        dump[f"cam{cam}_fn"] = fn
        for k in ("pre_frame_grab_ns", "post_frame_grab_ns", "pre_frame_retrieve_ns", "post_frame_retrieve_ns", "post_frame_record_ns"):
            dump[f"cam{cam}_{k}"] = ts[k]
        dump[f"cam{cam}_tick"] = log[sel, 0]
        dump[f"cam{cam}_tick_ns"] = log[sel, 1]
        dump[f"cam{cam}_grablog"] = log
        dump[f"cam{cam}_period_ns"] = np.array([logs[0]["period_ns"] if logs else 0], np.int64)
    res = base.analyse(size_name, ui, record_s, raw)
    res["variant"] = variant
    res["variant_doc"] = __doc__.split("Variants")[1].split("Extra output")[0]
    res["env"] = bc.env_summary()
    bc.write_json(f"{tag}.json", res)
    np.savez_compressed(bc.RESULTS / f"{tag}_perframe.npz", **dump)
    shutil.rmtree(raw["recording_folder"], ignore_errors=True)
    for p in Path(base.CAP_LOG_DIR).glob("cap_*.json"):
        p.unlink()
    print("RESULT", tag, json.dumps({k: res[k] for k in ("size", "retrieve_mode", "ui", "stop_error", "kill_flag_set")}))
    for cam, d in res["per_camera"].items():
        print("CAM", cam, f"fps={d['achieved_fps']:.2f} rec={d['recorded_frames']} sensor={d['sensor_frames_during_recording']} "
              f"never_grabbed={d['sensor_frames_never_grabbed']} retrieve={d['retrieve']['median_ms']:.2f} put={d['put_frame']['median_ms']:.2f} "
              f"write={d['record_frame_write']['median_ms']:.2f} interval med={d['grab_interval']['median_ms']:.2f} p99={d['grab_interval']['p99_ms']:.2f}")
    print("FILES", res["files"])
    print("UI", json.dumps(res["ui_summary"])[:300])
    print("CPU", res["cpu_pct_mean_during_recording"])
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    os.environ["BENCH_E2EV_VARIANT"] = sys.argv[1]
    VARIANTS = set(sys.argv[1].split(","))
    if sys.argv[3:4]:
        os.environ["BENCH_E2E_RETRIEVE"] = sys.argv[3]
        base.RETRIEVE_MODE = sys.argv[3]
    os.environ["BENCH_E2E_FAKE"] = "1"
    cap_dir = Path(__import__("bench_common").SCRATCH_TMP) / "caplogs"
    cap_dir.mkdir(exist_ok=True)
    for p in cap_dir.glob("cap_*.json"):
        p.unlink()
    os.environ["BENCH_E2E_CAPLOG"] = str(cap_dir)
    base.CAP_LOG_DIR = str(cap_dir)
    _install()
    main()
