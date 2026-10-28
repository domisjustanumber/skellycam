"""(e) End-to-end run of the REAL SkellyCam camera-group stack with synthetic 60 fps cameras.

What is real (unmodified SkellyCam HEAD 23ccbf20 code):
  WorkerRegistry(WorkerMode.PROCESS) + heartbeat, CameraGroupManager.create_and_start_camera_group,
  CameraGroup/CameraManager/CameraWorker/ManagedProcess (spawned camera processes), opencv_camera_worker_method,
  setup_opencv_camera_loop, run_opencv_camera_loop (lockstep orchestrator, opencv_get_frame incl. putText overlay,
  put_frame(overwrite=True), handle_video_recording -> VideoRecorder.record_frame, check_framerate_reset),
  start_recording_all_groups / stop_recording_all_groups (pause, RecordingInfoMessage, RecordingFinalizer incl.
  validate_recording), and the UI read path CameraGroupManager.get_latest_frontend_payloads (called the way
  WebsocketServer._frontend_image_relay calls it: await_10ms, then build, instant ack).

What is substituted (benchmark-process-only monkeypatch, applied at import of this script, which spawn re-imports
as __mp_main__ in every camera child before the worker runs):
  create_cv2_video_capture -> returns FakeCapture(cv2.VideoCapture subclass). FakeCapture models a free-running
  sensor at SENSOR_FPS with "latest frame wins" (CAP_PROP_BUFFERSIZE=1-like) semantics: grab() blocks until the next
  sensor tick if the loop is early; if the loop is late, the skipped ticks are counted as sensor frames the loop
  never grabbed. retrieve(image=buf):
     mjpeg  : cv2.imdecode(pre-encoded JPEG q90 of the synthetic frame) then np.copyto(buf)  (decode CPU cost; adds one
              memcpy that an in-place backend decode might not have)
     memcpy : np.copyto(buf, synthetic frame)  (lower bound: no decode cost)
  This assumption about DSHOW buffering is an assumption (no real camera used), see README limitations.
Also instrumented (parent only): RecordingFinalizer.create is wrapped to keep a copy of the per-frame metadata.

Run:  cd C:\\Users\\Dom\\GitHub\\freemocap\\skellycam && .venv\\Scripts\\python.exe research\\frame_ring_buffer\\baseline\\bench_e_e2e.py [size] [mjpeg|memcpy] [ui|noui] [record_s]
"""
from __future__ import annotations

import multiprocessing.queues  # noqa: F401  workaround for skellycam type_overloads.py L23 (see README)
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cv2  # noqa: E402
import numpy as np  # noqa: E402

N_CAMS = int(os.environ.get("BENCH_E2E_NCAMS", "5"))
SENSOR_FPS = float(os.environ.get("BENCH_SENSOR_FPS", "60"))
RETRIEVE_MODE = os.environ.get("BENCH_E2E_RETRIEVE", "mjpeg")
CAP_LOG_DIR = os.environ.get("BENCH_E2E_CAPLOG", "")


class FakeCapture(cv2.VideoCapture):
    def __init__(self, config):
        super().__init__()
        import bench_common as bc
        self.cam = config.camera_id
        self.h, self.w = config.resolution.height, config.resolution.width
        self.period = int(1e9 / SENSOR_FPS)
        rng = np.random.default_rng(int(config.camera_index))
        self.t0 = time.perf_counter_ns() + int(rng.integers(0, self.period))  # free-running, random phase
        self.frames = bc.synthetic_frames(self.h, self.w, n=30, seed=int(config.camera_index), noise=8)
        self.jpegs = [cv2.imencode(".jpg", f, [int(cv2.IMWRITE_JPEG_QUALITY), 90])[1] for f in self.frames]
        self.last_tick = -1
        self.cur = 0
        self.opened = True
        self.grab_log = []  # (tick, tick_time_ns, grab_return_ns)
        self.skipped_ticks_during_grabs = 0
        self.reads = 0
        self.created_ns = time.perf_counter_ns()

    def _next_tick(self):
        now = time.perf_counter_ns()
        tick = (now - self.t0) // self.period
        if tick <= self.last_tick:
            tick = self.last_tick + 1
            target = self.t0 + tick * self.period
            while True:
                rem = target - time.perf_counter_ns()
                if rem <= 0:
                    break
                if rem > 2_000_000:
                    time.sleep((rem - 1_500_000) / 1e9)
            skipped = 0
        else:
            skipped = tick - self.last_tick - 1
        self.last_tick = tick
        self.cur = tick
        return tick, skipped

    def isOpened(self):
        return self.opened

    def grab(self):
        tick, skipped = self._next_tick()
        if self.grab_log:
            self.skipped_ticks_during_grabs += skipped
        self.grab_log.append((int(tick), int(self.t0 + tick * self.period), time.perf_counter_ns()))
        return True

    def retrieve(self, image=None, flag=None):
        k = self.cur % len(self.frames)
        if RETRIEVE_MODE == "mjpeg":
            dec = cv2.imdecode(self.jpegs[k], cv2.IMREAD_COLOR)
        else:
            dec = self.frames[k]
        if image is None:
            return True, dec.copy()
        np.copyto(image, dec)
        return True, image

    def read(self, image=None):
        self._next_tick()
        self.reads += 1
        return self.retrieve(image)

    def get(self, prop):
        return 0.0

    def set(self, prop, value):
        return True

    def release(self):
        if self.opened and CAP_LOG_DIR:
            p = Path(CAP_LOG_DIR) / f"cap_{self.cam}_{self.created_ns}.json"
            p.write_text(json.dumps(dict(camera_id=self.cam, period_ns=self.period, t0=self.t0, reads=self.reads,
                                         skipped_ticks_during_grabs=self.skipped_ticks_during_grabs,
                                         grab_log=self.grab_log)))
        self.opened = False


def _fake_create_cv2_video_capture(config, retry_count: int = 5):
    return FakeCapture(config), config


def _install_fake_capture():
    import skellycam.core.camera.opencv.opencv_helpers.setup_opencv_camera_loop as setup_mod
    import skellycam.core.camera.opencv.opencv_camera_loop as loop_mod
    setup_mod.create_cv2_video_capture = _fake_create_cv2_video_capture
    loop_mod.create_cv2_video_capture = _fake_create_cv2_video_capture


if os.environ.get("BENCH_E2E_FAKE") == "1":
    _install_fake_capture()

CAPTURED_METADATA = {}


def _wrap_finalizer():
    from skellycam.core.recorders.recording_finalizer import RecordingFinalizer
    orig = RecordingFinalizer.create.__func__

    def create(cls, recording_info, camera_configs, frame_metadatas_by_camera):
        CAPTURED_METADATA.update({k: [np.copy(m) for m in v] for k, v in frame_metadatas_by_camera.items()})
        return orig(cls, recording_info=recording_info, camera_configs=camera_configs,
                    frame_metadatas_by_camera=frame_metadatas_by_camera)
    RecordingFinalizer.create = classmethod(create)


def _meta_arrays(mlist):
    md = np.concatenate([np.asarray(m).reshape(-1) for m in mlist])
    ts = md["timestamps"]
    return md["frame_number"].astype(np.int64), {n: ts[n].astype(np.int64) for n in ts.dtype.names}


async def run(size_name, ui, record_s, warmup_s=5.0):
    import asyncio
    import multiprocessing as mp
    import shutil
    import psutil
    import bench_common as bc
    from skellycam.core.camera_group.camera_group_manager import CameraGroupManager
    from skellycam.core.ipc.process_management.managed_worker import WorkerMode
    from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry
    from skellycam.core.recorders.videos.recording_info import RecordingInfo
    from skellycam.utilities.wait_functions import await_10ms

    _wrap_finalizer()
    h, w = bc.SIZES[size_name]
    pc = time.perf_counter_ns
    kill = mp.Value("b", False)
    reg = WorkerRegistry(global_kill_flag=kill, worker_mode=WorkerMode.PROCESS)
    reg.start_heartbeat()
    cgm = CameraGroupManager(global_kill_flag=kill, worker_registry=reg)
    configs = {str(i): bc.make_config(i, h, w, framerate=SENSOR_FPS) for i in range(N_CAMS)}
    t_setup = time.perf_counter()
    group = await cgm.create_and_start_camera_group(configs)
    while not group.cameras.all_ready:
        await asyncio.sleep(0.05)
    setup_s = time.perf_counter() - t_setup

    ui_stats = dict(build_ns=[], fns=[], age_ns=[], sizes=[], errors=[], t=[])
    running = {"ui": True}

    async def ui_task():
        last = -1
        while running["ui"]:
            await await_10ms()
            a = pc()
            try:
                payloads = cgm.get_latest_frontend_payloads(if_newer_than=last, display_image_sizes=None)
            except Exception as e:  # the real relay would set global_kill_flag here
                ui_stats["errors"].append(repr(e))
                continue
            b = pc()
            for gid, (fn, mfts, payload) in payloads.items():
                ui_stats["build_ns"].append(b - a); ui_stats["fns"].append(int(fn)); ui_stats["t"].append(b)
                ui_stats["age_ns"].append(b - float(mfts)); ui_stats["sizes"].append(len(payload))
                last = int(fn)

    me = psutil.Process()
    cpu_samples = []

    async def cpu_task():
        procs = {}
        while running["ui"]:
            kids = me.children(recursive=True)
            for k in kids:
                if k.pid not in procs:
                    procs[k.pid] = k
                    try:
                        k.cpu_percent(None)
                    except Exception:
                        pass
            me.cpu_percent(None) if not cpu_samples else None
            await asyncio.sleep(1.0)
            row = {"t": time.perf_counter(), "system": psutil.cpu_percent(None), "main": me.cpu_percent(None)}
            for pid, k in procs.items():
                try:
                    row[str(pid)] = k.cpu_percent(None)
                except Exception:
                    pass
            cpu_samples.append(row)

    psutil.cpu_percent(None)
    tasks = [asyncio.create_task(cpu_task())]
    if ui:
        tasks.append(asyncio.create_task(ui_task()))
    await asyncio.sleep(warmup_s)
    rec_name = f"e2e_{size_name}_{RETRIEVE_MODE}_{'ui' if ui else 'noui'}_{int(time.time())}"
    info = RecordingInfo(recording_name=rec_name, recording_directory=str(bc.SCRATCH_TMP))
    t_rec0 = pc()
    await cgm.start_recording_all_groups(recording_info=info)
    t_rec1 = pc()
    await asyncio.sleep(record_s)
    t_stop0 = pc()
    stop_error = None
    stats_str = None
    try:
        res = await cgm.stop_recording_all_groups()
        stats_str = str(res[0][1]) if res else None
    except Exception as e:
        stop_error = repr(e)
    t_stop1 = pc()
    running["ui"] = False
    await asyncio.sleep(1.2)
    for t in tasks:
        t.cancel()
    await cgm.close_all_camera_groups()
    reg.shutdown_all()
    return dict(setup_s=setup_s, t_rec_start_call=(t_rec0, t_rec1), t_stop_call=(t_stop0, t_stop1),
                stop_error=stop_error, finalizer_stats=stats_str, ui=ui_stats, cpu_samples=cpu_samples,
                recording_folder=info.full_recording_path, kill_flag=bool(kill.value))


def analyse(size_name, ui, record_s, raw):
    import bench_common as bc
    from concurrent.futures import ThreadPoolExecutor
    caplogs = {}
    for p in Path(CAP_LOG_DIR).glob("cap_*.json"):
        d = json.loads(p.read_text())
        caplogs.setdefault(d["camera_id"], []).append(d)
    per_cam = {}
    grab_by_cam = {}
    for cam, mlist in sorted(CAPTURED_METADATA.items()):
        fn, ts = _meta_arrays(mlist)
        logs = caplogs.get(cam, [])
        log = max(logs, key=lambda d: len(d["grab_log"]))["grab_log"] if logs else []
        log = np.asarray(log, dtype=np.int64) if log else np.zeros((0, 3), np.int64)
        sel = fn[(fn >= 0) & (fn < len(log))]
        ticks = log[sel, 0] if len(sel) else np.array([])
        tick_t = log[sel, 1] if len(sel) else np.array([])
        sensor_frames = int(ticks[-1] - ticks[0] + 1) if len(ticks) else 0
        grab = ts["pre_frame_grab_ns"]
        grab_by_cam[cam] = dict(zip(fn.tolist(), grab.tolist()))
        dt = np.diff(grab)
        rec_done = ts["post_frame_record_ns"]
        per_cam[cam] = dict(
            recorded_frames=int(len(fn)), first_fn=int(fn[0]), last_fn=int(fn[-1]),
            consecutive=bool(np.all(np.diff(fn) == 1)),
            sensor_frames_during_recording=sensor_frames,
            sensor_frames_never_grabbed=int(sensor_frames - len(fn)) if sensor_frames else None,
            achieved_fps=float((len(fn) - 1) / ((grab[-1] - grab[0]) / 1e9)),
            grab_interval=bc.stats_ms(dt),
            retrieve=bc.stats_ms(ts["post_frame_retrieve_ns"] - ts["pre_frame_retrieve_ns"]),
            put_frame=bc.stats_ms(ts["post_copy_to_camera_shm_ns"] - ts["pre_copy_to_camera_shm_ns"]),
            record_frame_write=bc.stats_ms(ts["post_frame_record_ns"] - ts["pre_frame_record_ns"]),
            grab_to_written=bc.stats_ms(rec_done - ts["post_frame_grab_ns"]),
            sensor_tick_to_written=bc.stats_ms(rec_done[:len(tick_t)] - tick_t) if len(tick_t) else None,
        )
    # cross-camera grab spread per frame number
    common = set.intersection(*[set(d) for d in grab_by_cam.values()]) if grab_by_cam else set()
    spread = [max(grab_by_cam[c][f] for c in grab_by_cam) - min(grab_by_cam[c][f] for c in grab_by_cam) for f in sorted(common)]
    # count frames actually in files
    vids = sorted(Path(raw["recording_folder"]).rglob("*.mp4")) + sorted(Path(raw["recording_folder"]).rglob("*.avi"))

    def count(path):
        cap = cv2.VideoCapture(str(path))
        n = 0
        while cap.grab():
            n += 1
        prop = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        return dict(file=path.name, bytes=path.stat().st_size, decoded_frames=n, prop_frame_count=prop)
    with ThreadPoolExecutor(5) as ex:
        files = list(ex.map(count, vids))
    total_bytes = sum(f.stat().st_size for f in Path(raw["recording_folder"]).rglob("*") if f.is_file())
    u = raw["ui"]
    ui_summary = None
    if ui and u["fns"]:
        el = (u["t"][-1] - u["t"][0]) / 1e9
        ui_summary = dict(payloads=len(u["fns"]), payload_fps=len(u["fns"]) / el, distinct_fps=len(set(u["fns"])) / el,
                          build=bc.stats_ms(u["build_ns"]), age_when_ready=bc.stats_ms(u["age_ns"]),
                          payload_bytes_median=float(np.median(u["sizes"])), errors=u["errors"][:5], n_errors=len(u["errors"]))
    # CPU summary (mean over samples taken during the recording window)
    t0r = raw["t_rec_start_call"][1] / 1e9
    t1r = raw["t_stop_call"][0] / 1e9
    win = [s for s in raw["cpu_samples"] if t0r + 1 <= s["t"] <= t1r]
    cpu = None
    if win:
        keys = [k for k in win[0] if k not in ("t",)]
        cpu = {k: float(np.mean([s.get(k, 0) for s in win])) for k in keys}
        cpu["sum_child_processes"] = float(sum(v for k, v in cpu.items() if k not in ("system", "main")))
    return dict(size=size_name, retrieve_mode=RETRIEVE_MODE, ui=ui, record_s=record_s, n_cams=N_CAMS, sensor_fps=SENSOR_FPS,
                setup_s=raw["setup_s"], start_recording_call_s=(raw["t_rec_start_call"][1] - raw["t_rec_start_call"][0]) / 1e9,
                stop_recording_call_s=(raw["t_stop_call"][1] - raw["t_stop_call"][0]) / 1e9,
                stop_error=raw["stop_error"], kill_flag_set=raw["kill_flag"], finalizer_stats=raw["finalizer_stats"],
                per_camera=per_cam, cross_camera_grab_spread=bc.stats_ms(spread), files=files,
                recording_total_bytes=total_bytes, ui_summary=ui_summary, cpu_pct_mean_during_recording=cpu,
                capture_logs={c: [dict(reads=d["reads"], skipped=d["skipped_ticks_during_grabs"], grabs=len(d["grab_log"])) for d in v]
                              for c, v in caplogs.items()})


def main():
    import asyncio
    import shutil
    import bench_common as bc
    size_name = sys.argv[1] if len(sys.argv) > 1 else "1080p"
    ui = (sys.argv[3] if len(sys.argv) > 3 else "ui") == "ui"
    record_s = float(sys.argv[4]) if len(sys.argv) > 4 else 30.0
    tag = f"e_e2e_{size_name}_{RETRIEVE_MODE}_{'ui' if ui else 'noui'}"+ os.environ.get("BENCH_E2E_REP", "")
    raw = asyncio.run(run(size_name, ui, record_s))
    res = analyse(size_name, ui, record_s, raw)
    res["env"] = bc.env_summary()
    bc.write_json(f"{tag}.json", res)
    shutil.rmtree(raw["recording_folder"], ignore_errors=True)
    for p in Path(CAP_LOG_DIR).glob("cap_*.json"):
        p.unlink()
    print("RESULT", json.dumps({k: res[k] for k in ("size", "retrieve_mode", "ui", "stop_error", "kill_flag_set")}))
    for cam, d in res["per_camera"].items():
        print("CAM", cam, f"fps={d['achieved_fps']:.2f} rec={d['recorded_frames']} sensor={d['sensor_frames_during_recording']} "
              f"never_grabbed={d['sensor_frames_never_grabbed']} put={d['put_frame']['median_ms']:.2f} "
              f"write={d['record_frame_write']['median_ms']:.2f}/{d['record_frame_write']['p99_ms']:.2f} "
              f"interval p99={d['grab_interval']['p99_ms']:.2f} max={d['grab_interval']['max_ms']:.2f}")
    print("FILES", res["files"])
    print("UI", json.dumps(res["ui_summary"])[:400])
    print("CPU", res["cpu_pct_mean_during_recording"])
    sys.stdout.flush()
    os._exit(0)  # same as skellycam entry_point; avoids a hang at interpreter exit seen in the first run


if __name__ == "__main__":
    if sys.argv[2:3]:
        os.environ["BENCH_E2E_RETRIEVE"] = sys.argv[2]
        RETRIEVE_MODE = sys.argv[2]
    os.environ["BENCH_E2E_FAKE"] = "1"
    cap_dir = Path(__import__("bench_common").SCRATCH_TMP) / "caplogs"
    cap_dir.mkdir(exist_ok=True)
    os.environ["BENCH_E2E_CAPLOG"] = str(cap_dir)
    CAP_LOG_DIR = str(cap_dir)
    _install_fake_capture()
    main()
