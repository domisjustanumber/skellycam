"""M5 (specs/frame-ring.md 11.3): zlib.crc32 on one BGR frame, and the full BGR write and read.

Synthetic photo-like frames, decoded from q90 4:2:0 JPEGs. 8 different frames per size are used in
turn (8 x 6.2 MB at 1080p is larger than the L3 cache), so a call does not find its frame hot in the
cache from the call before. Writes `results/m5.json`.
"""
import json
import os
import time
import zlib

import cv2
import numpy as np

import common

common.add_ring_path()
from skellycam.core.ipc.frame_ring import FrameRingCreator, FrameRingReader, FrameRingWriter, PixelFormat  # noqa: E402

CALLS = 2400
WARM = 100
HERE = os.path.dirname(os.path.abspath(__file__))


def frames(size):
    w, h = common.SIZES[size]
    out = [cv2.imdecode(np.frombuffer(j, np.uint8), cv2.IMREAD_COLOR) for j in common.jpegs(size, 8)]
    assert all(f.shape == (h, w, 3) and f.flags.c_contiguous for f in out)
    return out


def time_crc(arrays):
    for i in range(WARM):
        zlib.crc32(arrays[i % len(arrays)])
    ts = np.empty(CALLS, np.int64)
    for i in range(CALLS):
        a = arrays[i % len(arrays)]
        t0 = time.perf_counter_ns()
        zlib.crc32(a)
        ts[i] = time.perf_counter_ns() - t0
    return common.stats_ms(ts)


def time_ring(size, arrays):
    """Unpaced loop: write frame k (W1 to W7), then read frame k (R1 to R13). Each timed apart."""
    w, h = common.SIZES[size]
    creator = FrameRingCreator.create(camera_id="m5", camera_index=90, pixel_format=PixelFormat.BGR24,
                                      width=w, height=h, fps_num=60, fps_den=1)
    writer = reader = None
    try:
        writer, reader = FrameRingWriter.attach(creator.name), FrameRingReader.attach(creator.name)
        tw, tr = np.empty(CALLS, np.int64), np.empty(CALLS, np.int64)
        for k in range(WARM + CALLS):
            a = arrays[k % len(arrays)]
            t0 = time.perf_counter_ns()
            writer.write(a, frame_number=k, arrival_ns=t0, sample_ns=t0, source_frame_number=k, flags=0,
                         rotation_cw_deg=0)
            t1 = time.perf_counter_ns()
            r = reader.read(k)
            t2 = time.perf_counter_ns()
            assert r.result.name == "OK", r.result
            if k >= WARM:
                tw[k - WARM], tr[k - WARM] = t1 - t0, t2 - t1
        assert np.array_equal(r.payload, arrays[(WARM + CALLS - 1) % len(arrays)])
        return common.stats_ms(tw), common.stats_ms(tr)
    finally:
        for h_ in (reader, writer):
            if h_ is not None:
                h_.close()
        creator.close_and_unlink()


def time_copy(arrays):
    """The W3 copy alone into a 6.2 MB bytearray target, as the writer does it (memoryview slice assignment)."""
    target = memoryview(bytearray(arrays[0].nbytes))
    ts = np.empty(CALLS, np.int64)
    for i in range(WARM + CALLS):
        a = arrays[i % len(arrays)].reshape(-1)
        t0 = time.perf_counter_ns()
        target[:] = a
        if i >= WARM:
            ts[i - WARM] = time.perf_counter_ns() - t0
    return common.stats_ms(ts)


def main():
    cv2.setNumThreads(1)
    out = dict(machine=common.machine_info(), calls=CALLS, results={})
    for size in common.SIZES:
        arrays = frames(size)
        crc_cold = time_crc(arrays)
        crc_hot = time_crc(arrays[:1])
        copy = time_copy(arrays)
        write, read = time_ring(size, arrays)
        out["results"][size] = dict(frame_bytes=arrays[0].nbytes, crc32_rotating_8_frames=crc_cold,
                                    crc32_same_frame=crc_hot, copy_only=copy, bgr_write=write, bgr_read=read,
                                    crc_share_of_write_median=crc_cold["median"] / write["median"],
                                    crc_share_of_read_median=crc_cold["median"] / read["median"],
                                    crc_gb_per_s=arrays[0].nbytes / crc_cold["median"] / 1e6)
        print(size, json.dumps(out["results"][size], indent=1), flush=True)
    with open(os.path.join(HERE, "results", "m5.json"), "w") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
