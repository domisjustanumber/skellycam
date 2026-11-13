"""MCAP desk test: one writer process, one file for a whole take (N cameras + mic).

    python -I msw.py scale    STRAT NCAM OUT_MCAP RESULTS_JSON [SECONDS=3600]   unpaced, 2 KB dummy JPEGs, 330 B dummy Opus
    python -I msw.py realtime STRAT MEDIA_DIR OUT_MCAP RESULTS_JSON SECONDS     paced, real 1080p JPEGs (mcap_kill media), real Opus
    python -I msw.py kill     WORK_DIR RESULTS_JSON MCAP_CLI N                  strategy b, paced, 16 cams of 2 KB + mic

STRAT: a = flush after every message (one chunk per message); b = one chunk per 33 ms frame window (all cameras + its
audio); c = one chunk per 100 ms window; d = no explicit flush, writer default chunk_size 1 MiB.
Profile (test choices only): protobuf, foxglove.CompressedImage on /camNN/image, foxglove.CompressedAudio opus on
/mic/audio, compression NONE, enable_data_crcs=True. Arrival order: per 30 fps tick, mic packets due at or before the
tick, then cameras 0..N-1. A window is flushed when the first message of the next window arrives.
"""
import json, os, random, struct, subprocess, sys, threading, time, zlib

import numpy as np
import psutil
from foxglove_schemas_protobuf.CompressedAudio_pb2 import CompressedAudio
from foxglove_schemas_protobuf.CompressedImage_pb2 import CompressedImage
from mcap.writer import CompressionType, Writer
from mcap_protobuf.schema import build_file_descriptor_set

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mcap_kill"))
import mcap_kill as mk  # noqa: E402  (reuse: media, streaming read, recover check, record walk, env info)

FPS, MIC_NS, BASE_NS = 30, 20_000_000, 10 ** 18
JPEG_DUMMY, OPUS_DUMMY = 2000, 330
FILLER = random.Random(1).randbytes(JPEG_DUMMY)
NO_AUTO_CHUNK = 1 << 62


def frame_ns(k):
    return k * 1_000_000_000 // FPS


def events(ncam, seconds):
    """(t_ns, cam or -1 for mic, index, window_b, window_c) in arrival order. Generator: no big list in RAM."""
    nframes, j = int(seconds * FPS), 0
    for k in range(nframes):
        t = frame_ns(k)
        while j * MIC_NS <= t:                       # mic first on ties
            yield j * MIC_NS, -1, j, 3 * j // 5, j // 5; j += 1
        for c in range(ncam):
            yield t, c, k, k, k // 3
    while j * MIC_NS < seconds * 1_000_000_000:
        yield j * MIC_NS, -1, j, 3 * j // 5, j // 5; j += 1


def dummy_payload(cam, idx):
    if cam < 0:
        return struct.pack("<iI", cam, idx) + FILLER[:OPUS_DUMMY - 8]
    return struct.pack("<iI", cam, idx) + FILLER[8:]


def open_writer(path, ncam, strat):
    f = open(path, "wb")
    w = Writer(f, compression=CompressionType.NONE, enable_data_crcs=True,
               chunk_size=1024 * 1024 if strat == "d" else NO_AUTO_CHUNK)
    w.start(profile="", library="mcap_single_writer desk test")
    sid_i = w.register_schema(name=CompressedImage.DESCRIPTOR.full_name, encoding="protobuf",
                              data=build_file_descriptor_set(CompressedImage).SerializeToString())
    sid_a = w.register_schema(name=CompressedAudio.DESCRIPTOR.full_name, encoding="protobuf",
                              data=build_file_descriptor_set(CompressedAudio).SerializeToString())
    cids = [w.register_channel(topic=f"/cam{c:02d}/image", message_encoding="protobuf", schema_id=sid_i) for c in range(ncam)]
    mic = w.register_channel(topic="/mic/audio", message_encoding="protobuf", schema_id=sid_a,
                             metadata=dict(sample_rate="48000", channels="1", pre_skip="312"))
    w.flush()
    return f, w, cids, mic


def body(cam, idx, t, data):
    if cam < 0:
        m = CompressedAudio(format="opus", data=data)
    else:
        m = CompressedImage(frame_id=f"cam{cam:02d}", format="jpeg", data=data)
    m.timestamp.FromNanoseconds(BASE_NS + t)
    return m.SerializeToString()


def window_of(strat, n, wb, wc):
    return n if strat == "a" else wb if strat == "b" else wc if strat == "c" else 0


def summary_layout(path):
    """Footer -> summary bytes, records per opcode, ChunkIndex count and message_index_offsets entries."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        f.seek(size - 37)
        foot = f.read(37)
        assert foot[0] == 0x02 and foot[-8:] == mk.MAGIC
        summary_start = struct.unpack_from("<Q", foot, 9)[0]
        f.seek(summary_start)
        s = f.read(size - 37 - summary_start)
    o, ops, nbytes, ci_entries = 0, {}, {}, 0
    while o < len(s):
        op, ln = s[o], struct.unpack_from("<Q", s, o + 1)[0]
        ops[op] = ops.get(op, 0) + 1; nbytes[op] = nbytes.get(op, 0) + 9 + ln
        if op == 0x08:
            ci_entries += struct.unpack_from("<I", s, o + 9 + 32)[0] // 10
        o += 9 + ln
    return dict(file_bytes=size, summary_start=summary_start, summary_bytes=size - summary_start,
                records_by_opcode={hex(k): v for k, v in ops.items()}, bytes_by_opcode={hex(k): v for k, v in nbytes.items()},
                chunk_indexes=ops.get(0x08, 0), message_index_offset_entries=ci_entries,
                chunk_index_bytes_mean=nbytes.get(0x08, 0) / max(1, ops.get(0x08, 0)))


def mem(p):
    m = p.memory_info()
    return dict(rss=m.rss, private=getattr(m, "private", None))


# ---------------------------------------------------------------- task 1: scale, unpaced
def scale(strat, ncam, path, results, seconds="3600"):
    ncam, seconds = int(ncam), float(seconds)
    p = psutil.Process()
    m0 = mem(p)
    f, w, cids, mic = open_writer(path, ncam, strat)
    total = int(seconds * FPS) * ncam + int(seconds * 1000 // 20)
    every = max(1, total // 40)
    samples, n, cur, flushes, payload = [], 0, None, 0, 0
    t0 = time.perf_counter(); cpu0 = time.process_time()
    for t, cam, idx, wb, wc in events(ncam, seconds):
        win = window_of(strat, n, wb, wc)
        if strat in "bc" and cur is not None and win != cur:
            w.flush(); flushes += 1
        cur = win
        data = dummy_payload(cam, idx)
        w.add_message(channel_id=mic if cam < 0 else cids[cam], log_time=BASE_NS + t, publish_time=BASE_NS + t,
                      data=body(cam, idx, t, data), sequence=idx)
        payload += len(data)
        if strat == "a":
            w.flush(); flushes += 1
        n += 1
        if n % every == 0:
            samples.append(dict(messages=n, s=round(time.perf_counter() - t0, 3), **mem(p)))
    t_loop = time.perf_counter() - t0
    m_before = mem(p)
    tf = time.perf_counter(); w.finish(); t_finish = time.perf_counter() - tf
    m_after = mem(p)
    f.close()
    t_total = time.perf_counter() - t0
    cpu = time.process_time() - cpu0
    mi = p.memory_info()
    lay = summary_layout(path)
    res = dict(test="scale", strat=strat, ncam=ncam, seconds=seconds, messages=n, expected_messages=total, explicit_flushes=flushes,
               payload_bytes=payload, write_loop_s=t_loop, finish_s=t_finish, total_write_s=t_total, cpu_s=cpu,
               msgs_per_s=n / t_loop, rss_start=m0, rss_before_finish=m_before, rss_after_finish=m_after,
               peak_wset=getattr(mi, "peak_wset", None), peak_private=getattr(mi, "peak_pagefile", None),
               growth_bytes_per_chunk=(m_before["private"] - m0["private"]) / max(1, lay["chunk_indexes"]) if m0["private"] else None,
               overhead_per_msg=(lay["file_bytes"] - payload) / n, rss_samples=samples, layout=lay, env=env())
    json.dump(res, open(results, "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k not in ("rss_samples", "env")}))


def env():
    from importlib.metadata import version
    vs = {q: version(q) for q in ("mcap", "mcap-protobuf-support", "foxglove-schemas-protobuf", "protobuf", "numpy", "psutil")}
    vm = psutil.virtual_memory()
    return dict(python=sys.version.split()[0], cpu_count=psutil.cpu_count(), ram_gb=round(vm.total / 2 ** 30, 1),
                ram_avail_gb=round(vm.available / 2 ** 30, 1), packages=vs, date=time.strftime("%Y-%m-%dT%H:%M:%S%z"))


# ---------------------------------------------------------------- task 3: real-size throughput, paced
def realtime(strat, media, path, results, seconds):
    seconds, ncam = float(seconds), 16
    _meta, frames, pkts = mk.load_media(media)
    before = dict(system_cpu_pct=psutil.cpu_percent(3.0), top=mk.top_procs({os.getpid()}),
                  disk_free_gb=round(psutil.disk_usage(os.path.dirname(os.path.abspath(path))).free / 1e9, 1))
    f, w, cids, mic = open_writer(path, ncam, strat)
    sys_cpu, stop = [], threading.Event()

    def sampler():
        psutil.cpu_percent(None)
        while not stop.wait(1.0):
            sys_cpu.append(psutil.cpu_percent(None))
    th = threading.Thread(target=sampler, daemon=True); th.start()
    flush_ms, add_ms, window_ms, late_cam, late_mic = [], [], [], [], []
    n, cur, win_t, payload = 0, None, 0.0, 0
    t0 = time.perf_counter(); cpu0 = time.process_time()
    for t, cam, idx, wb, wc in events(ncam, seconds):
        due = t0 + t / 1e9
        while time.perf_counter() < due:
            time.sleep(0.001)
        start = time.perf_counter()
        (late_mic if cam < 0 else late_cam).append(start - due)
        win = window_of(strat, n, wb, wc)
        if strat == "b" and cur is not None and win != cur:
            a = time.perf_counter_ns(); w.flush(); d = time.perf_counter_ns() - a
            flush_ms.append(d / 1e6); window_ms.append(win_t + d / 1e6); win_t = 0.0
        cur = win
        data = pkts[idx % len(pkts)] if cam < 0 else frames[(idx + cam) % len(frames)]
        b = body(cam, idx, t, data)
        a = time.perf_counter_ns()
        w.add_message(channel_id=mic if cam < 0 else cids[cam], log_time=BASE_NS + t, publish_time=BASE_NS + t, data=b, sequence=idx)
        if strat == "a":
            w.flush()
        d = time.perf_counter_ns() - a
        (flush_ms if strat == "a" else add_ms).append(d / 1e6); win_t += d / 1e6
        payload += len(data); n += 1
    wall = time.perf_counter() - t0
    cpu = time.process_time() - cpu0
    tf = time.perf_counter(); w.finish(); t_finish = time.perf_counter() - tf
    f.close(); stop.set(); th.join()
    after_top = mk.top_procs({os.getpid()})

    def dist(a):
        a = np.array(a)
        return dict(n=len(a), p50=float(np.percentile(a, 50)), p99=float(np.percentile(a, 99)), max=float(a.max()))
    lc, lm = np.array(late_cam) * 1e3, np.array(late_mic) * 1e3
    lay = summary_layout(path)
    res = dict(test="realtime", strat=strat, ncam=ncam, seconds=seconds, messages=n, wall_s=wall, cpu_s=cpu,
               cpu_pct_one_core=100 * cpu / wall, payload_bytes=payload, file_bytes=lay["file_bytes"],
               MB_per_s=lay["file_bytes"] / wall / 1e6, finish_s=t_finish,
               flush_latency_ms=dist(flush_ms), add_message_ms=dist(add_ms) if add_ms else None,
               window_write_ms=dist(window_ms) if window_ms else None,
               late_cam_ms=dict(p50=float(np.percentile(lc, 50)), p99=float(np.percentile(lc, 99)), max=float(lc.max()),
                                over_5ms=int((lc > 5).sum()), over_one_period=int((lc > 1e3 / FPS).sum())),
               late_mic_ms=dict(p99=float(np.percentile(lm, 99)), max=float(lm.max()), over_one_period=int((lm > 20).sum())),
               load_before=before, load_after_top=after_top,
               system_cpu_pct_during=dict(mean=float(np.mean(sys_cpu)), max=float(np.max(sys_cpu)), n=len(sys_cpu)),
               layout=lay, env=env())
    json.dump(res, open(results, "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k not in ("env", "load_before", "load_after_top")}))


# ---------------------------------------------------------------- task 4: kills of the single writer, strategy b
def kill_child(path, log_path):
    f, w, cids, mic = open_writer(path, 16, "b")
    log = open(log_path, "wb")
    print("ready", os.getpid(), flush=True)
    t0 = time.perf_counter()
    print("t0", repr(t0), flush=True)
    n, cur = 0, None
    for t, cam, idx, wb, wc in events(16, 10 ** 6):        # loops until killed
        due = t0 + t / 1e9
        while time.perf_counter() < due:
            time.sleep(0.001)
        if cur is not None and wb != cur:
            w.flush()
            log.write(struct.pack("<I", n)); log.flush()
        cur = wb
        w.add_message(channel_id=mic if cam < 0 else cids[cam], log_time=BASE_NS + t, publish_time=BASE_NS + t,
                      data=body(cam, idx, t, dummy_payload(cam, idx)), sequence=idx)
        n += 1


def expected(n):
    out = []
    for i, (t, cam, idx, wb, _wc) in enumerate(events(16, 10 ** 6)):
        if i >= n:
            break
        out.append((cam, idx, BASE_NS + t, wb))
    return out


def kill_test(work, results, cli, n):
    n = int(n)
    os.makedirs(work, exist_ok=True)
    rng = random.Random(20261113)
    exp = expected(18 * 30 * 8)                           # > 8 s of messages
    # message counts at which a window ends (what a flush can leave on disk)
    bounds = {i for i in range(1, len(exp)) if exp[i][3] != exp[i - 1][3]}
    rows, k = [], 0
    while sum(r["killed"] for r in rows) < n and k < n + 10:
        path, log_path = os.path.join(work, f"kill_{k:02d}.mcap"), os.path.join(work, f"kill_{k:02d}.log")
        delay = rng.uniform(0.3, 6.0)
        pr = subprocess.Popen([sys.executable, "-I", os.path.abspath(__file__), "kill_child", path, log_path],
                              stdout=subprocess.PIPE, text=True)
        word, pid = pr.stdout.readline().split()
        assert word == "ready", word
        word, t0 = pr.stdout.readline().split()
        assert word == "t0", word
        time.sleep(delay)
        target = psutil.Process(int(pid))
        t_kill = time.perf_counter()                      # QPC: same clock as the child's perf_counter on Windows
        target.kill()
        code = target.wait(10); pr.wait(10)
        due = sum(1 for e in exp if BASE_NS + (t_kill - float(t0)) * 1e9 >= e[2])
        lb = open(log_path, "rb").read()
        logged = struct.unpack_from("<I", lb, len(lb) - 4)[0] if len(lb) >= 4 else 0
        msgs, err, _chmeta, n_chunks, crc_bad, err2 = mk.read_streaming(path)
        got = []
        for m in msgs:
            pl = (CompressedAudio if m.channel_id == 17 else CompressedImage).FromString(m.data)
            got.append((m.channel_id, m.sequence, m.log_time, pl.data, pl.timestamp.ToNanoseconds()))
        want = [(17 if cam < 0 else cam + 1, idx, lt, dummy_payload(cam, idx), lt) for cam, idx, lt, _wb in exp[:len(got)]]
        exact = got == want
        row = dict(trial=k, kill_delay_s=round(delay, 4), writer_pid_is_popen_pid=int(pid) == pr.pid, exit_code=code,
                   killed=code != 0, logged_flushed_messages=logged, log_tail_torn_bytes=len(lb) % 4,
                   recovered_messages=len(msgs), recovered_minus_logged=len(msgs) - logged,
                   recovered_ends_on_window=len(msgs) in bounds or len(msgs) == 0,
                   due_at_kill=due, lost_vs_due=due - len(msgs), exact_prefix=exact,
                   nonseeking_end_error=err, crc_error=bool(err and "crc" in err.lower()),
                   emit_chunks_chunks=n_chunks, emit_chunks_crc_bad=crc_bad, emit_chunks_end_error=err2,
                   **{f"walk_{a}": v for a, v in mk.walk_records(open(path, "rb").read()).items()})
        row.update(mk.check_recovered(cli, path, msgs))
        os.remove(path); os.remove(log_path)
        rows.append(row); k += 1
        print(json.dumps({x: row[x] for x in ("trial", "exit_code", "logged_flushed_messages", "recovered_messages",
                                               "lost_vs_due", "exact_prefix", "recover_exit")}), flush=True)
    rs = [r for r in rows if r["killed"]]

    def counts(key):
        out = {}
        for r in rs:
            v = json.dumps(r.get(key)); out[v] = out.get(v, 0) + 1
        return out
    summary = dict(trials_killed=len(rs), not_killed=len(rows) - len(rs),
                   recovered_range=[min(r["recovered_messages"] for r in rs), max(r["recovered_messages"] for r in rs)],
                   lost_vs_due_range=[min(r["lost_vs_due"] for r in rs), max(r["lost_vs_due"] for r in rs)],
                   exact_prefix=sum(r["exact_prefix"] for r in rs), ends_on_window=sum(r["recovered_ends_on_window"] for r in rs),
                   crc_errors=sum(r["crc_error"] for r in rs) + sum(r["emit_chunks_crc_bad"] for r in rs),
                   **{f"counts_{key}": counts(key) for key in ("recovered_minus_logged", "lost_vs_due", "walk_tail_bytes",
                                                               "recover_exit", "recover_same_messages", "doctor_exit_on_recovered",
                                                               "nonseeking_end_error", "writer_pid_is_popen_pid", "exit_code")})
    json.dump(dict(test="mcap_single_writer_kill_b", env=dict(env(), mcap_cli=mk.env_info(cli)["mcap_cli"]), summary=summary, rows=rows),
              open(results, "w"), indent=1)
    print(json.dumps(summary, indent=1))


def selftest():
    ev = list(events(16, 1))
    assert sum(e[1] < 0 for e in ev) == 50 and sum(e[1] >= 0 for e in ev) == 480
    for s, ix in (("b", 3), ("c", 4)):                    # windows never go backwards, and a window holds its tick's frames
        ws = [e[ix] for e in ev]
        assert ws == sorted(ws)
    assert all(e[3] == e[2] for e in ev if e[1] >= 0) and all(frame_ns(e[3]) <= e[0] for e in ev)
    print("selftest ok")


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    {"scale": scale, "realtime": realtime, "kill": kill_test, "kill_child": kill_child, "selftest": selftest}[cmd](*args)
