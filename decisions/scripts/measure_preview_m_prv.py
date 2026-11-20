"""Measurements M-PRV-1 to M-PRV-5 of specs/preview.md, with fake rings and no camera (ADR-HDC9).

Main process: the rings, and uvicorn (ws "auto", as skellycam/__main__.py) with a preview route wired as
the test route of skellycam/tests/preview/ and a /health route. Writer process: paced writes of random
payloads of the largest real JPEG size (276,269 bytes at 720p, 607,032 bytes at 1080p). Client process:
a websocket client that offers permessage-deflate, as a browser does, and answers at once or never, and
a /health probe every 20 ms.

Run from the repository root:
    uv run python decisions/scripts/measure_preview_m_prv.py inprocess
    uv run python decisions/scripts/measure_preview_m_prv.py uvicorn --deflate off
    uv run python decisions/scripts/measure_preview_m_prv.py uvicorn --deflate on
"""
import asyncio
import http.client
import json
import multiprocessing as mp
import os
import socket
import struct
import sys
import threading
import time
from types import SimpleNamespace

import numpy as np

SIZES = {"720p": (1280, 720, 276_269), "1080p": (1920, 1080, 607_032)}
WARMUP_S, MEASURE_S = 2.0, 10.0


def pct(values, q):
    return round(float(np.percentile(values, q)), 3) if len(values) else None


def ring_pkg():
    from skellycam.core.ipc import frame_ring
    return frame_ring


def m1_m2_in_process():
    fr = ring_pkg()
    from skellycam.api.websocket.preview_relay import pack_camera_frame
    out = {}
    for label, (w, h, size) in SIZES.items():
        creator = fr.FrameRingCreator.create(camera_id="m1", camera_index=90, pixel_format=fr.PixelFormat.JPEG,
                                             width=w, height=h, fps_num=30, fps_den=1, generation=1000 + w)
        writer = fr.FrameRingWriter.attach(creator.name)
        reader = fr.FrameRingReader.attach(creator.name)
        for k in range(30):
            writer.write(os.urandom(size), frame_number=k, arrival_ns=k, sample_ns=k, source_frame_number=k, flags=0,
                         rotation_cw_deg=0)
        reads, packs = [], []
        for i in range(3000):
            t0 = time.perf_counter_ns()
            read = reader.read(i % 30)
            t1 = time.perf_counter_ns()
            pack_camera_frame("a1b2", read)
            t2 = time.perf_counter_ns()
            assert read.result is fr.ReadResult.OK
            reads.append((t1 - t0) / 1e6)
            packs.append((t2 - t1) / 1e6)
        out[label] = {"read_ms_p50": pct(reads, 50), "read_ms_p99": pct(reads, 99),
                      "pack_ms_p50": pct(packs, 50), "pack_ms_p99": pct(packs, 99)}
        reader.close()
        writer.close()
        creator.close_and_unlink()
    return out


async def pass_interval():
    """M-PRV-4b: one ready camera with no new frame. Each pass does one check read."""
    fr = ring_pkg()
    from skellycam.api.websocket.preview_relay import PreviewRelay
    creator = fr.FrameRingCreator.create(camera_id="pi", camera_index=91, pixel_format=fr.PixelFormat.JPEG,
                                         width=64, height=48, fps_num=30, fps_den=1, generation=2000)
    reader = fr.FrameRingReader.attach(creator.name)
    times = []

    class Spy:
        def read(self, k):
            if k == 1:  # the check read; the probe read(0) follows it in the same pass
                times.append(time.perf_counter())
            return reader.read(k)

        def read_newest(self):
            return reader.read_newest()
        oversize_count = property(lambda self: reader.oversize_count)
        skipped_count = property(lambda self: reader.skipped_count)

    manager = SimpleNamespace(closing=False, camera_groups={"g1": SimpleNamespace(id="g1", ring_readers={"pi": Spy()})})

    async def nothing(_):
        pass
    task = asyncio.create_task(PreviewRelay(manager, nothing, nothing).run())
    await asyncio.sleep(5.0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    reader.close()
    creator.close_and_unlink()
    gaps = np.diff(times) * 1e3
    return {"pass_interval_ms_p50": pct(gaps, 50), "pass_interval_ms_p99": pct(gaps, 99),
            "pass_interval_ms_max": round(float(gaps.max()), 3), "passes": len(times)}


def writer_main(names, size, fps, duration_s):
    fr = ring_pkg()
    writers = [fr.FrameRingWriter.attach(n) for n in names]
    payloads = [os.urandom(size) for _ in range(4)]
    period = 1.0 / fps
    next_t = time.perf_counter()
    end = next_t + duration_s
    k = 0
    while time.perf_counter() < end:
        arrival = time.perf_counter_ns()
        for w in writers:
            w.write(payloads[k % 4], frame_number=k, arrival_ns=arrival, sample_ns=arrival, source_frame_number=k,
                    flags=0, rotation_cw_deg=0)
        k += 1
        next_t += period
        delay = next_t - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
    for w in writers:
        w.close()


def client_main(port, answer, duration_s, queue):
    from websockets.sync.client import connect
    received, health = {}, []
    stop = threading.Event()

    def probe():
        while not stop.is_set():
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            t0 = time.perf_counter()
            conn.request("GET", "/health")
            conn.getresponse().read()
            health.append((time.perf_counter() - t0) * 1e3)
            conn.close()
            stop.wait(0.02)
    threading.Thread(target=probe, daemon=True).start()
    last_update = None
    with connect(f"ws://127.0.0.1:{port}/preview", max_size=None) as ws:
        end = time.monotonic() + duration_s
        while time.monotonic() < end:
            try:
                message = ws.recv(timeout=0.5)
            except TimeoutError:
                continue
            if isinstance(message, bytes):
                cid = message[32:48].rstrip(b"\0").decode()
                received.setdefault(cid, []).append(struct.unpack_from("<q", message, 8)[0])
                if answer:
                    ws.send(json.dumps({"message_type": "camera_ready", "camera_id": cid}))
            else:
                data = json.loads(message)
                if data.get("message_type") == "framerate_update":
                    last_update = data
    stop.set()
    queue.put({"received": received, "health": health, "last_update": last_update})


def free_port():
    while True:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        if port != 53117:
            return port


async def scenario(n_cams, res, fps, answer, deflate, client=True):
    import uvicorn
    from fastapi import FastAPI, WebSocket
    from skellycam.api.websocket.preview_relay import PreviewRelay
    import msgspec
    fr = ring_pkg()
    w, h, size = SIZES[res]
    creators = [fr.FrameRingCreator.create(camera_id=f"c{i:03d}", camera_index=60 + i, pixel_format=fr.PixelFormat.JPEG,
                                           width=w, height=h, fps_num=fps, fps_den=1, generation=3000 + i)
                for i in range(n_cams)]
    readers = {c.name: fr.FrameRingReader.attach(c.name) for c in creators}
    published = {}  # camera id -> {frame number: published_ns}

    class Timed:
        def __init__(self, cid, reader):
            self.cid, self.reader = cid, reader
            published[cid] = {}

        def _note(self, read):
            if read.result is fr.ReadResult.OK:
                published[self.cid][read.frame_number] = read.published_ns
            return read

        def read(self, k):
            return self._note(self.reader.read(k))

        def read_newest(self):
            return self._note(self.reader.read_newest())
        oversize_count = property(lambda self: self.reader.oversize_count)
        skipped_count = property(lambda self: self.reader.skipped_count)

    ring_readers = {f"c{i:03d}": Timed(f"c{i:03d}", readers[c.name]) for i, c in enumerate(creators)}
    manager = SimpleNamespace(closing=False, camera_groups={"g1": SimpleNamespace(id="g1", ring_readers=ring_readers)})
    send_ms, latency_ms = [], []
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"alive": True, "pid": os.getpid()}

    @app.websocket("/preview")
    async def route(websocket: WebSocket):
        await websocket.accept()
        lock = asyncio.Lock()

        async def send_bytes(data):
            cid = data[32:48].rstrip(b"\0").decode()
            k = struct.unpack_from("<q", data, 8)[0]
            p = published[cid].get(k)
            async with lock:
                t0 = time.perf_counter_ns()
                if p:
                    latency_ms.append((t0 - p) / 1e6)
                await websocket.send_bytes(data)
                send_ms.append((time.perf_counter_ns() - t0) / 1e6)

        async def send_json(data):
            async with lock:
                await websocket.send_text(msgspec.json.encode(data).decode())
        relay = PreviewRelay(manager, send_bytes, send_json)
        task = asyncio.create_task(relay.run())
        try:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("text") is not None:
                    relay.handle_text(message["text"])
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning",
                                           ws_per_message_deflate=deflate))
    serve = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    total = WARMUP_S + MEASURE_S + 1.0
    wproc = mp.Process(target=writer_main, args=([c.name for c in creators], size, fps, total + 1.0))
    wproc.start()
    queue = mp.Queue()
    if client:
        cproc = mp.Process(target=client_main, args=(port, answer, total, queue))
    else:
        cproc = mp.Process(target=health_only_main, args=(port, total, queue))
    cproc.start()
    await asyncio.sleep(WARMUP_S)
    n_send, n_lat = len(send_ms), len(latency_ms)
    c0, t0 = time.thread_time(), time.perf_counter()
    await asyncio.sleep(MEASURE_S)
    cpu = (time.thread_time() - c0) / (time.perf_counter() - t0)
    sends, lats = send_ms[n_send:], latency_ms[n_lat:]
    result = await asyncio.get_running_loop().run_in_executor(None, queue.get)
    cproc.join(10)
    wproc.join(10)
    server.should_exit = True
    await serve
    for r in readers.values():
        r.close()
    for c in creators:
        c.close_and_unlink()
    out = {"deflate": deflate, "cameras": n_cams, "res": res, "fps": fps, "client": ("keeps up" if answer else "never answers")
           if client else "none (health only)", "loop_thread_cpu": round(cpu, 3),
           "health_ms_p50": pct(result["health"], 50), "health_ms_p99": pct(result["health"], 99),
           "health_n": len(result["health"])}
    if client:
        out.update({"send_ms_p50": pct(sends, 50), "send_ms_p99": pct(sends, 99),
                    "published_to_send_ms_p50": pct(lats, 50), "published_to_send_ms_p99": pct(lats, 99),
                    "messages_per_s": round(len(sends) / MEASURE_S, 1)})
        not_shown = []
        for cid, frames in result["received"].items():
            frames = frames[len(frames) // 5:]  # drop the warm-up part
            if len(frames) > 1:
                not_shown.append(((frames[-1] - frames[0] + 1) - len(frames)) / (frames[-1] - frames[0] + 1))
        out["not_shown_share_mean"] = round(float(np.mean(not_shown)), 4) if not_shown else None
        out["not_shown_share_max"] = round(float(np.max(not_shown)), 4) if not_shown else None
    return out


def health_only_main(port, duration_s, queue):
    health = []
    end = time.monotonic() + duration_s
    while time.monotonic() < end:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        t0 = time.perf_counter()
        conn.request("GET", "/health")
        conn.getresponse().read()
        health.append((time.perf_counter() - t0) * 1e3)
        conn.close()
        time.sleep(0.02)
    queue.put({"health": health})


def main():
    which = sys.argv[1]
    deflate = "--deflate" in sys.argv and sys.argv[sys.argv.index("--deflate") + 1] == "on"
    results = {"python": sys.version.split()[0], "platform": sys.platform}
    if which == "inprocess":
        results["M-PRV-1/2 in process"] = m1_m2_in_process()
        results["M-PRV-4 pass interval"] = asyncio.run(pass_interval())
    if which == "uvicorn":
        runs = []
        for args in ((4, "720p", 30, True), (4, "1080p", 30, True), (8, "1080p", 60, True),
                     (4, "720p", 30, False), (4, "1080p", 30, False), (8, "1080p", 60, False)):
            runs.append(asyncio.run(scenario(*args, deflate)))
            print(json.dumps(runs[-1]), flush=True)
        runs.append(asyncio.run(scenario(8, "1080p", 60, True, deflate, client=False)))
        print(json.dumps(runs[-1]), flush=True)
        results["M-PRV-3/4/5"] = runs
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
