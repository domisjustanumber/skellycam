"""
Does the realtime aggregator keep producing outputs when NOBODY sets result_consumed_event
(i.e. no websocket client)? Tests claim H15 against the real FreeMoCap RealtimePipeline code
(freemocap @5632778a, installed skellycam @777b058c), using real CameraGroupSharedMemory and a
synthetic writer thread in place of cameras (pattern copied from
freemocap/tests/pipelines/mocks/mock_camera_group.py). Workers run in THREAD mode.

Pipeline config: charuco only (skeleton tracking off), so no GPU/ONNX needed.

Two regimes:
  fast_writer: frames written every ~1 ms  (capture outpaces the pipeline)
  slow_writer: frames written every 200 ms (pipeline outpaces capture)
In both, the script NEVER touches result_ready_event / result_consumed_event; it only drains
pipeline.aggregation_output_subscription and counts distinct output frame numbers.

Run: C:/Users/Dom/GitHub/freemocap/freemocap/.venv/Scripts/python.exe -I <this file>
"""
import sys
sys.dont_write_bytecode = True
# freemocap .venv ships an older skellytracker (2024.9.1019) that lacks modules freemocap@5632778a imports;
# prepend the sibling skellytracker checkout (source only, nothing installed).
sys.path.insert(0, r"C:/Users/Dom/GitHub/freemocap/skellytracker")
import logging
import multiprocessing
import queue
import threading
import time

import numpy as np

logging.basicConfig(level=logging.WARNING)

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.camera.config.image_rotation_types import RotationTypes
from skellycam.core.camera_group.camera_group import CameraGroup
from skellycam.core.ipc.process_management.managed_worker import WorkerMode
from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry
from skellycam.core.ipc.shared_memory.camera_group_shared_memory import CameraGroupSharedMemory
from skellycam.core.timestamps.timebase_mapping import TimebaseMapping
from skellycam.core.types.frame_dtype_factories import create_frame_dtype
from skellycam.utilities.create_camera_group_id import create_camera_group_id

from freemocap.core.pipeline.realtime.camera_node_config import CameraNodeConfig
from freemocap.core.pipeline.realtime.realtime_pipeline import RealtimePipeline
from freemocap.core.pipeline.realtime.realtime_pipeline_config import RealtimePipelineConfig


class _IPC:
    def __init__(self, kill_flag):
        self.global_kill_flag = kill_flag
        self.group_id = create_camera_group_id()


def make_group(kill_flag, n_cams=2, w=320, h=240):
    configs = {
        str(i): CameraConfig(camera_id=str(i), camera_index=i,
                             resolution=ImageResolution(width=w, height=h),
                             color_channels=3, rotation=RotationTypes.NO_ROTATION)
        for i in range(n_cams)
    }
    tbm = TimebaseMapping()
    shm = CameraGroupSharedMemory.create(camera_configs=configs, timebase_mapping=tbm, read_only=False)
    g = object.__new__(CameraGroup)
    g.ipc = _IPC(kill_flag)
    g.configs = configs
    g.cameras = None
    g.shm = shm
    g.started = True
    g._audio_recorder = None
    recs = {}
    for cid, cfg in configs.items():
        r = np.recarray(1, dtype=create_frame_dtype(cfg))
        r.frame_metadata.camera_info = cfg.to_frame_camera_info()[0]
        r.frame_metadata.timebase_mapping = tbm.to_numpy_record_array()[0]
        r.image[0][:] = 128
        recs[cid] = r
    return g, recs


def run(regime: str, write_period_s: float, duration_s: float = 8.0):
    kill_flag = multiprocessing.Value("b", False)
    registry = WorkerRegistry(global_kill_flag=kill_flag, worker_mode=WorkerMode.THREAD)
    group, recs = make_group(kill_flag)
    cfg = RealtimePipelineConfig(
        camera_node_config=CameraNodeConfig(worker_mode=WorkerMode.THREAD,
                                            skeleton_tracking_enabled=False,
                                            charuco_tracking_enabled=True),
        use_centralized_inference=True,
        log_pipeline_times=False,
    )
    pipeline = RealtimePipeline.create(camera_group=group, worker_registry=registry, pipeline_config=cfg)
    stop = threading.Event()
    written = [0]

    def writer():
        i = 0
        while not stop.is_set():
            for cid, r in recs.items():
                r.frame_metadata.frame_number[0] = i
                now = time.perf_counter_ns()
                r.frame_metadata.timestamps.pre_frame_grab_ns[0] = now
                r.frame_metadata.timestamps.post_frame_grab_ns[0] = now
                group.shm.camera_shms[cid].put_frame(frame_rec_array=r, overwrite=True)
            i += 1
            written[0] = i
            time.sleep(write_period_s)

    wt = threading.Thread(target=writer, daemon=True)
    wt.start()
    pipeline.start()
    seen = []
    t0 = time.perf_counter()
    try:
        while time.perf_counter() - t0 < duration_s:
            try:
                msg = pipeline.aggregation_output_subscription.get(timeout=0.1)
                seen.append(msg.frame_number)
            except queue.Empty:
                pass
            if kill_flag.value:
                print(f"[{regime}] global kill flag set during run!")
                break
    finally:
        stop.set()
        wt.join(timeout=2)
        print(f"[{regime}] write period={write_period_s*1e3:.0f}ms  frames written={written[0]}  "
              f"aggregator outputs observed={len(seen)}  distinct={len(set(seen))}  "
              f"first={seen[:5]}  last={seen[-5:]}  "
              f"result_consumed_event.is_set()={pipeline.result_consumed_event.is_set()}  "
              f"result_ready_event.is_set()={pipeline.result_ready_event.is_set()}")
        try:
            pipeline.shutdown()
        except Exception as e:
            print(f"[{regime}] shutdown error: {e!r}")
        group.shm.unlink_and_close()


if __name__ == "__main__":
    run("fast_writer", write_period_s=0.001)
    run("slow_writer", write_period_s=0.2)
