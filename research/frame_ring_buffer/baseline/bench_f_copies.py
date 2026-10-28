"""(f) Count bytes copied per frame on the record path and the UI path, by instrumentation.

Runs the real SkellyCam calls in ONE process (copy counts are a property of each call, not of the process
topology) with in-process counting wrappers (no source file is modified):
  * skellycam...ring_buffer_shared_memory.copy        (the `copy(data)` in put_data L132)
  * the ring's numpy buffer replaced by a view of a recarray subclass whose __setitem__ counts the bytes
    assigned into a slot (put_data L132 slot assignment)
  * numpy.copyto (global, counts dst bytes; split into >=1 KiB "frame" copies and tiny flag/index copies)
  * numpy.copy  (flag reads in SharedMemoryElement.valid / first_data_written)
  * cv2.rotate / cv2.resize / cv2.imencode (counts output bytes = bytes written)
  * skellycam...video_recorder.copy (metadata copy L108)
  * VideoWriter.write handoff: bytes handed to the encoder and whether they share memory with the frame
Compressed-byte copies inside create_frontend_payload that cannot be hooked (jpeg_data.tobytes(), the slice
assign into _reusable_bytes_payload, and the final bytearray slice) are counted analytically from the
measured JPEG / payload sizes, and labelled as such.
tracemalloc is used to measure heap bytes allocated per call.

Run:  cd C:\\Users\\Dom\\GitHub\\freemocap\\skellycam && .venv\\Scripts\\python.exe research\\frame_ring_buffer\\baseline\\bench_f_copies.py
"""
from __future__ import annotations

import multiprocessing.queues  # noqa: F401
import sys
import tracemalloc
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cv2  # noqa: E402
import numpy as np  # noqa: E402

COUNTS = defaultdict(lambda: [0, 0])  # name -> [calls, bytes]


def add(name, nbytes):
    c = COUNTS[name]
    c[0] += 1
    c[1] += int(nbytes)


class CountingRec(np.recarray):
    def __setitem__(self, key, value):
        add("shm_slot_assignment (put_data L132)", np.asarray(value).nbytes)
        return super().__setitem__(key, value)


def install():
    import skellycam.core.ipc.shared_memory.ring_buffer_shared_memory as rb
    import skellycam.core.recorders.videos.video_recorder as vr
    from copy import copy as _copy
    orig_copyto, orig_npcopy = np.copyto, np.copy

    def copyto(dst, src, *a, **k):
        nb = np.asarray(dst).nbytes
        add("np.copyto frame-sized (>=1KiB)" if nb >= 1024 else "np.copyto tiny (<1KiB: index/flag)", nb)
        return orig_copyto(dst, src, *a, **k)

    def npcopy(a, *args, **kw):
        out = orig_npcopy(a, *args, **kw)
        add("np.copy (flag reads)", out.nbytes)
        return out

    def rb_copy(x):
        out = _copy(x)
        add("copy.copy in put_data (L132)", np.asarray(out).nbytes)
        return out

    def vr_copy(x):
        out = _copy(x)
        add("copy(frame_metadata) in record_frame (L108)", np.asarray(out).nbytes)
        return out
    np.copyto, np.copy = copyto, npcopy
    rb.copy = rb_copy
    vr.copy = vr_copy
    for fname in ("rotate", "resize", "imencode"):
        orig = getattr(cv2, fname)

        def wrap(*a, _o=orig, _n=fname, **k):
            out = _o(*a, **k)
            arr = out[1] if _n == "imencode" else out
            add(f"cv2.{_n} output", arr.nbytes)
            if _n == "imencode":
                add("JPEG bytes (imencode)", arr.nbytes)
            return out
        setattr(cv2, fname, wrap)


def snapshot_reset():
    d = {k: {"calls": v[0], "bytes": v[1]} for k, v in COUNTS.items()}
    COUNTS.clear()
    return d


def main():
    import bench_common as bc
    install()
    from skellycam.core.ipc.shared_memory.camera_group_shared_memory import CameraGroupSharedMemory
    from skellycam.core.ipc.shared_memory.camera_shared_memory_ring_buffer import CameraSharedMemoryRingBuffer
    from skellycam.core.recorders.videos.recording_info import RecordingInfo
    from skellycam.core.recorders.videos.video_recorder import VideoRecorder
    from skellycam.core.timestamps.timebase_mapping import TimebaseMapping
    from skellycam.core.types.frontend_payload_bytearray import create_frontend_payload
    from skellycam.core.camera.config.image_rotation_types import RotationTypes

    out = {"env": bc.env_summary(), "cases": []}
    lines = ["# (f) bytes copied per frame (instrumented real calls)", ""]
    N = 5
    for size_name in ("720p", "1080p"):
        h, w = bc.SIZES[size_name]
        frame_bytes = h * w * 3
        for rot in (RotationTypes.NO_ROTATION, RotationTypes.CLOCKWISE_90):
            configs = {str(i): bc.make_config(i, h, w, rotation=rot) for i in range(N)}
            shm = CameraGroupSharedMemory.create(camera_configs=configs, timebase_mapping=TimebaseMapping(), read_only=True)
            writers = {cid: CameraSharedMemoryRingBuffer.recreate(dto=d, read_only=False) for cid, d in shm.camera_shm_dtos.items()}
            for wr in writers.values():
                wr.ring_shm.buffer = wr.ring_shm.buffer.view(CountingRec)
            frs = {cid: bc.make_frame_recarray(configs[cid]) for cid in configs}
            content = bc.synthetic_frames(h, w, n=4, seed=1)
            info = RecordingInfo(recording_name=f"f_{size_name}_{rot.name}", recording_directory=str(bc.SCRATCH_TMP))
            rec = VideoRecorder.create(recording_info=info, config=configs["0"], framerate=60.0)
            # warm up (allocate payload buffer etc.)
            for k in range(3):
                for cid, fr in frs.items():
                    fr.image[0] = content[k % 4]
                    fr.frame_metadata.frame_number[0] += 1
                    writers[cid].put_frame(frame_rec_array=fr, overwrite=True)
                rec.record_frame(frame=frs["0"])
                create_frontend_payload(latest_frames=shm.get_latest_multiframe(), display_image_sizes=None)
            snapshot_reset()
            ITER = 20
            case = {"size": size_name, "rotation": rot.name, "frame_image_bytes": frame_bytes,
                    "frame_record_bytes": int(frs["0"].dtype.itemsize), "iterations": ITER}
            # ---- record path, per camera per frame: put_frame + record_frame (camera-loop order L96-105)
            tracemalloc.start()
            peaks_put, peaks_rec = [], []
            handoff_shares = []
            orig_write = rec.video_writer.write
            for k in range(ITER):
                fr = frs["0"]
                fr.image[0] = content[k % 4]
                fr.frame_metadata.frame_number[0] += 1
                tracemalloc.reset_peak(); b0 = tracemalloc.get_traced_memory()[0]
                writers["0"].put_frame(frame_rec_array=fr, overwrite=True)
                peaks_put.append(tracemalloc.get_traced_memory()[1] - b0)
                tracemalloc.reset_peak(); b0 = tracemalloc.get_traced_memory()[0]
                rec.record_frame(frame=fr)
                peaks_rec.append(tracemalloc.get_traced_memory()[1] - b0)
                if rot == RotationTypes.NO_ROTATION:
                    handoff_shares.append(bool(np.shares_memory(fr.image[0], fr)))
            tracemalloc.stop()
            rp = snapshot_reset()
            case["record_path_per_frame"] = {k: {"calls": v["calls"] / ITER, "bytes": v["bytes"] / ITER} for k, v in rp.items()}
            case["record_path_heap_peak_bytes_put_frame"] = float(np.median(peaks_put))
            case["record_path_heap_peak_bytes_record_frame"] = float(np.median(peaks_rec))
            case["encoder_handoff_is_view_of_frame"] = all(handoff_shares) if handoff_shares else "rotated: cv2.rotate output"
            # ---- UI path, per multiframe: SkellyCam (get_latest_multiframe) and FreeMoCap (get_images_by_frame_number)
            for path in ("skellycam_ui", "freemocap_ui_by_number"):
                tracemalloc.start()
                peaks, payload_lens, jpeg_lens = [], [], []
                for k in range(ITER):
                    for cid, fr in frs.items():
                        fr.image[0] = content[k % 4]
                        fr.frame_metadata.frame_number[0] += 1
                        writers[cid].put_frame(frame_rec_array=fr, overwrite=True)
                    snapshot_before = snapshot_reset()  # discard writer counts
                    for kk, vv in snapshot_before.items():
                        pass
                    tracemalloc.reset_peak(); b0 = tracemalloc.get_traced_memory()[0]
                    if path == "skellycam_ui":
                        mf = shm.get_latest_multiframe()
                    else:
                        mf = shm.get_images_by_frame_number(frame_number=shm.latest_multiframe_number)
                    fn, ts, payload = create_frontend_payload(latest_frames=mf, display_image_sizes=None)
                    peaks.append(tracemalloc.get_traced_memory()[1] - b0)
                    payload_lens.append(len(payload))
                    jpeg_lens.append(COUNTS["JPEG bytes (imencode)"][1])
                    if k < ITER - 1:
                        # accumulate ui counts across iterations
                        acc = case.setdefault(f"_{path}_acc", defaultdict(lambda: [0, 0]))
                        for kk, vv in COUNTS.items():
                            acc[kk][0] += vv[0]; acc[kk][1] += vv[1]
                        COUNTS.clear()
                tracemalloc.stop()
                acc = case.pop(f"_{path}_acc")
                for kk, vv in COUNTS.items():
                    acc[kk][0] += vv[0]; acc[kk][1] += vv[1]
                COUNTS.clear()
                per = {k: {"calls": v[0] / ITER, "bytes": v[1] / ITER} for k, v in acc.items()}
                jpeg_total = float(np.mean(jpeg_lens))
                payload_len = float(np.mean(payload_lens))
                per["(analytic) jpeg_data.tobytes() copy L147"] = {"calls": N, "bytes": jpeg_total}
                per["(analytic) slice-assign into _reusable_bytes_payload L176 (+headers)"] = {"calls": N, "bytes": payload_len}
                per["(analytic) return _reusable_bytes_payload[:current_pos] slice copy L197"] = {"calls": 1, "bytes": payload_len}
                case[f"{path}_per_multiframe"] = per
                case[f"{path}_heap_peak_bytes"] = float(np.median(peaks))
                case[f"{path}_payload_bytes"] = payload_len
            rec.finish_and_close()
            for wr in writers.values():
                wr.close()
            shm.unlink_and_close()
            out["cases"].append(case)
            bc.write_json("f_copies.json", out)
            # human summary
            lines.append(f"## {size_name}, rotation={rot.name} (image {frame_bytes:,} B, shm record {case['frame_record_bytes']:,} B)")
            lines.append("")
            lines.append("Record path, per camera per frame (put_frame + record_frame):")
            lines.append("")
            lines.append("| step | calls | bytes | x image |")
            lines.append("|---|---|---|---|")
            for k, v in sorted(case["record_path_per_frame"].items()):
                lines.append(f"| {k} | {v['calls']:.1f} | {v['bytes']:,.0f} | {v['bytes'] / frame_bytes:.2f} |")
            lines.append(f"| heap allocated (tracemalloc peak) put_frame / record_frame | | "
                         f"{case['record_path_heap_peak_bytes_put_frame']:,.0f} / {case['record_path_heap_peak_bytes_record_frame']:,.0f} | |")
            lines.append(f"| encoder handoff is a view of the private frame (no copy) | {case['encoder_handoff_is_view_of_frame']} | | |")
            for path in ("skellycam_ui", "freemocap_ui_by_number"):
                lines.append("")
                lines.append(f"UI path `{path}`, per 5-camera multiframe:")
                lines.append("")
                lines.append("| step | calls | bytes | x one image |")
                lines.append("|---|---|---|---|")
                for k, v in sorted(case[f"{path}_per_multiframe"].items()):
                    lines.append(f"| {k} | {v['calls']:.1f} | {v['bytes']:,.0f} | {v['bytes'] / frame_bytes:.2f} |")
                lines.append(f"| heap allocated (tracemalloc peak) | | {case[f'{path}_heap_peak_bytes']:,.0f} | {case[f'{path}_heap_peak_bytes'] / frame_bytes:.2f} |")
            lines.append("")
    bc.write_text("f_copies.md", "\n".join(lines) + "\n")
    print("\n".join(lines))
    sys.stdout.flush()
    import os
    os._exit(0)  # first run hung at interpreter exit after writing all results (timeout 124)


if __name__ == "__main__":
    main()
