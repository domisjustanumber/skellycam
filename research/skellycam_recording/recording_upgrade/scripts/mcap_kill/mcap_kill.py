"""MCAP desk test: external TerminateProcess kills of a chunk-per-message writer, and 4 cam + 1 mic throughput.

Copies the method of scripts/flac_skau/terminate_kill.py (FINDINGS section 7): the parent kills the writer from
outside (psutil kill = TerminateProcess) after a random delay; children loop their source until killed; only
trials with a non-zero exit code count.

    python -I mcap_kill.py media     MEDIA_DIR
    python -I mcap_kill.py kill      MEDIA_DIR WORK_DIR RESULTS_JSON MCAP_CLI KIND MODE N   (KIND cam|mic, MODE paced|fast)
    python -I mcap_kill.py throughput MEDIA_DIR WORK_DIR RESULTS_JSON MCAP_CLI SECONDS

Writer profile (test choices, not decisions): mcap.writer.Writer, compression NONE, enable_data_crcs=True,
flush() after every message (one chunk per message). Camera: foxglove.CompressedImage, format jpeg, log_time =
perf_counter_ns at arrival, timestamp = synthetic 30 fps clock, sequence = frame number. Mic:
foxglove.CompressedAudio, format opus, one 20 ms packet per message, log_time = timestamp = BASE + k * 20 ms.
Ground truth: after each flush() returns, the child appends its message count (u32) to a .log file and flushes it.
"""
import base64, fractions, json, os, random, struct, subprocess, sys, time, zlib

import av
import numpy as np
import psutil
from foxglove_schemas_protobuf.CompressedAudio_pb2 import CompressedAudio
from foxglove_schemas_protobuf.CompressedImage_pb2 import CompressedImage
from mcap.reader import NonSeekingReader, make_reader
from mcap.records import Chunk
from mcap.stream_reader import StreamReader
from mcap.writer import CompressionType, Writer
from mcap_protobuf.schema import build_file_descriptor_set

RATE, PKT_SAMPLES, FPS = 48_000, 960, 30
BASE_NS = 10 ** 18                       # synthetic clock origin
N_FRAMES, TARGET_JPEG = 30, 163_000      # distinct source frames, target size per 1080p frame
CLICK_FIRST, CLICK_STEP, CLICK_AMP = 1_000, 9_601, 29_000   # click sample positions: FIRST + k * STEP
MAGIC = b"\x89MCAP0\r\n"


# ---------------------------------------------------------------- media (built once)
def make_frame(sigma, seed):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:1080, 0:1920]
    base = ((x / 1920 * 200 + y / 1080 * 55)[..., None] + np.array([0, 30, 60])) % 256
    return np.clip(base + rng.normal(0, sigma, (1080, 1920, 3)), 0, 255).astype(np.uint8)


def jpeg_bytes(arr):
    import io
    from PIL import Image
    b = io.BytesIO(); Image.fromarray(arr).save(b, "JPEG", quality=85); return b.getvalue()


def audio_signal(seconds):
    n = seconds * RATE
    sig = (600 * np.sin(2 * np.pi * 440 * np.arange(n) / RATE)).astype(np.int16)
    clicks = np.arange(CLICK_FIRST, n, CLICK_STEP)
    sig[clicks] = CLICK_AMP
    return sig, clicks


def opus_head(pre_skip):  # RFC 7845 section 5.1, mapping family 0
    return b"OpusHead" + struct.pack("<BBHIhB", 1, 1, pre_skip, RATE, 0, 0)


def build_media(media):
    os.makedirs(media, exist_ok=True)
    lo, hi = 0.0, 60.0
    for _ in range(14):                  # bisect noise sigma for ~163 KB frames
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if len(jpeg_bytes(make_frame(mid, 0))) < TARGET_JPEG else (lo, mid)
    sigma = (lo + hi) / 2
    sizes, crcs = [], []
    for i in range(N_FRAMES):
        data = jpeg_bytes(make_frame(sigma, 1000 + i))
        open(os.path.join(media, f"frame_{i:03d}.jpg"), "wb").write(data)
        sizes.append(len(data)); crcs.append(zlib.crc32(data))
    assert len(set(crcs)) == N_FRAMES
    sig, clicks = audio_signal(120)
    cc = av.CodecContext.create("libopus", "w")
    cc.sample_rate, cc.layout, cc.format, cc.bit_rate = RATE, "mono", "s16", 64_000
    cc.time_base = fractions.Fraction(1, RATE)
    cc.open()
    pkts = []
    for k in range(len(sig) // PKT_SAMPLES):
        fr = av.AudioFrame.from_ndarray(sig[k * PKT_SAMPLES:(k + 1) * PKT_SAMPLES].reshape(1, -1), format="s16", layout="mono")
        fr.sample_rate, fr.pts = RATE, k * PKT_SAMPLES
        pkts += [bytes(p) for p in cc.encode(fr)]
    pkts += [bytes(p) for p in cc.encode(None)]
    pre_skip = cc.initial_padding
    with open(os.path.join(media, "opus.bin"), "wb") as f:
        for p in pkts:
            f.write(struct.pack("<I", len(p)) + p)
    meta = dict(jpeg_quality=85, noise_sigma=round(sigma, 3), frame_sizes=sizes, frame_crcs=crcs,
                opus_packets=len(pkts), opus_bytes=sum(map(len, pkts)), opus_bitrate=64_000, pre_skip=pre_skip,
                frame_size=cc.frame_size, opus_head_b64=base64.b64encode(opus_head(pre_skip)).decode())
    json.dump(meta, open(os.path.join(media, "media.json"), "w"), indent=1)
    # baseline: clicks in a full decode of the source packets
    meta["full_decode_clicks"] = click_errors(decode_opus(pkts, pre_skip), len(pkts))
    print(json.dumps({k: v for k, v in meta.items() if k not in ("frame_sizes", "frame_crcs")}))
    return meta


def load_media(media):
    meta = json.load(open(os.path.join(media, "media.json")))
    frames = [open(os.path.join(media, f"frame_{i:03d}.jpg"), "rb").read() for i in range(N_FRAMES)]
    blob, pkts, o = open(os.path.join(media, "opus.bin"), "rb").read(), [], 0
    while o < len(blob):
        n = struct.unpack_from("<I", blob, o)[0]; pkts.append(blob[o + 4:o + 4 + n]); o += 4 + n
    return meta, frames, pkts


def decode_opus(pkts, pre_skip):
    dc = av.CodecContext.create("opus", "r")
    dc.sample_rate, dc.layout = RATE, "mono"
    out = [f.to_ndarray().reshape(-1) for p in pkts for f in dc.decode(av.Packet(p))]
    pcm = np.concatenate(out) if out else np.zeros(0, np.float32)
    return pcm[pre_skip:]


def click_errors(pcm, n_packets, win=200):
    """Error in samples between each expected click and the |peak| near it, for clicks fully inside pcm."""
    errs = []
    for c in range(CLICK_FIRST, len(pcm) - win, CLICK_STEP):
        seg = np.abs(pcm[c - win:c + win + 1]); errs.append(int(np.argmax(seg)) - win)
    return dict(decoded_samples=int(len(pcm)), packets=n_packets, clicks_checked=len(errs),
                exact=sum(e == 0 for e in errs), max_abs_error=max(map(abs, errs)) if errs else None,
                errors_seen=sorted(set(errs)))


# ---------------------------------------------------------------- child writer
def child(kind, mode, path, log_path, media, label, stats_path, seconds):
    meta, frames, pkts = load_media(media)
    seconds = float(seconds)
    f, log = open(path, "wb"), open(log_path, "wb")
    w = Writer(f, compression=CompressionType.NONE, enable_data_crcs=True)
    w.start(profile="", library="mcap_kill desk test")
    cls = CompressedImage if kind == "cam" else CompressedAudio
    sid = w.register_schema(name=cls.DESCRIPTOR.full_name, encoding="protobuf",
                            data=build_file_descriptor_set(cls).SerializeToString())
    if kind == "cam":
        cid = w.register_channel(topic=f"/{label}/image", message_encoding="protobuf", schema_id=sid)
        rate = FPS
    else:
        cid = w.register_channel(topic="/mic/audio", message_encoding="protobuf", schema_id=sid, metadata=dict(
            sample_rate=str(RATE), channels="1", pre_skip=str(meta["pre_skip"]), output_gain="0", opus_head=meta["opus_head_b64"]))
        rate = RATE / PKT_SAMPLES
    w.add_metadata("skellyfileformat", dict(take_uuid="00000000-0000-4000-8000-000000000001", camera_label=label,
                                            clock_id="1", nominal_rate="30/1" if kind == "cam" else "50/1"))
    w.flush()
    print("ready", os.getpid(), flush=True)
    t0 = time.perf_counter()
    n, timings, lateness, payload, pb_bytes = 0, [], [], 0, 0
    cpu0 = time.process_time()
    while True:
        due = t0 + n / rate
        if mode != "fast":
            if mode == "run" and due - t0 >= seconds:
                break
            while time.perf_counter() < due:
                time.sleep(0.001)
        start = time.perf_counter()
        if kind == "cam":
            data = frames[n % N_FRAMES]
            arrival = time.perf_counter_ns()
            msg = CompressedImage(frame_id=label, format="jpeg", data=data)
            msg.timestamp.FromNanoseconds(BASE_NS + n * 1_000_000_000 // FPS)
            log_time = arrival
        else:
            data = pkts[n % len(pkts)]
            log_time = BASE_NS + n * 20_000_000
            msg = CompressedAudio(format="opus", data=data)
            msg.timestamp.FromNanoseconds(log_time)
        body = msg.SerializeToString()
        a = time.perf_counter_ns()
        w.add_message(channel_id=cid, log_time=log_time, publish_time=log_time, data=body, sequence=n)
        w.flush()
        timings.append(time.perf_counter_ns() - a)
        n += 1
        log.write(struct.pack("<I", n)); log.flush()
        lateness.append(start - due); payload += len(data); pb_bytes += len(body)
    cpu = time.process_time() - cpu0
    wall = time.perf_counter() - t0
    w.finish(); f.close()
    t = np.array(timings) / 1e6
    late = np.array(lateness) * 1e3
    json.dump(dict(kind=kind, label=label, messages=n, wall_s=wall, cpu_s=cpu, cpu_pct_one_core=100 * cpu / wall,
                   payload_bytes=payload, protobuf_bytes=pb_bytes, file_bytes=os.path.getsize(path),
                   write_ms_p50=float(np.percentile(t, 50)), write_ms_p99=float(np.percentile(t, 99)), write_ms_max=float(t.max()),
                   late_ms_p99=float(np.percentile(late, 99)), late_ms_max=float(late.max()),
                   late_over_5ms=int((late > 5).sum()), late_over_one_period=int((late > 1e3 / rate).sum()),
                   expected_messages=int(round(seconds * rate))), open(stats_path, "w"))
    print("finished", flush=True)


def spawn(kind, mode, path, log_path, media, label, stats_path="-", seconds=0):
    pr = subprocess.Popen([sys.executable, "-I", os.path.abspath(__file__), "child", kind, mode, path, log_path, media,
                           label, stats_path, str(seconds)], stdout=subprocess.PIPE, text=True)
    word, pid = pr.stdout.readline().split()
    assert word == "ready", word
    return pr, int(pid)


# ---------------------------------------------------------------- analysis of a killed file
def walk_records(blob):
    """Top-level record framing: complete records, complete chunks, bytes after the last complete record."""
    if blob[:8] != MAGIC:
        return dict(records=0, chunks=0, tail_bytes=len(blob))
    o, recs, chunks = 8, 0, 0
    while o + 9 <= len(blob):
        op, ln = blob[o], struct.unpack_from("<Q", blob, o + 1)[0]
        if o + 9 + ln > len(blob):
            break
        recs += 1; chunks += op == 0x06; o += 9 + ln
    return dict(records=recs, chunks=chunks, tail_bytes=len(blob) - o)


def read_streaming(path):
    msgs, err, channel_meta = [], None, None
    with open(path, "rb") as f:
        try:
            for _s, ch, m in NonSeekingReader(f, validate_crcs=True).iter_messages(log_time_order=False):
                msgs.append(m); channel_meta = dict(ch.metadata)
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {str(e)[:160]}"
    n_chunks, crc_bad, err2 = 0, 0, None
    with open(path, "rb") as f:
        try:
            for r in StreamReader(f, skip_magic=False, emit_chunks=True).records:
                if isinstance(r, Chunk):
                    n_chunks += 1; crc_bad += zlib.crc32(r.data) != r.uncompressed_crc
        except Exception as e:  # noqa: BLE001
            err2 = f"{type(e).__name__}: {str(e)[:160]}"
    return msgs, err, channel_meta, n_chunks, crc_bad, err2


def check_prefix(kind, msgs, frames, pkts, crcs):
    for i, m in enumerate(msgs):
        if kind == "cam":
            p = CompressedImage.FromString(m.data)
            ok = (m.sequence == i and zlib.crc32(p.data) == crcs[i % N_FRAMES] and p.data == frames[i % N_FRAMES]
                  and p.timestamp.ToNanoseconds() == BASE_NS + i * 1_000_000_000 // FPS and p.format == "jpeg")
        else:
            p = CompressedAudio.FromString(m.data)
            ok = (m.sequence == i and p.data == pkts[i % len(pkts)] and m.log_time == BASE_NS + i * 20_000_000
                  and p.timestamp.ToNanoseconds() == m.log_time and p.format == "opus")
        if not ok:
            return False, i
    return True, None


def run_cli(cli, *args):
    r = subprocess.run([cli, "--color", "never", *args], capture_output=True, text=True)
    return r.returncode, r.stderr.strip().splitlines()[-3:]


def check_recovered(cli, path, msgs):
    out = path + ".recovered.mcap"
    code, tail = run_cli(cli, "recover", path, "-o", out)
    row = dict(recover_exit=code, recover_stderr_tail=tail)
    if os.path.exists(out):
        try:
            with open(out, "rb") as f:
                r = make_reader(f)
                s = r.get_summary()
                got = [(m.sequence, m.log_time, m.data) for _s, _c, m in r.iter_messages()]
            row.update(recovered_file_summary=s is not None, recovered_file_messages=len(got),
                       recover_same_messages=got == [(m.sequence, m.log_time, m.data) for m in msgs])
        except Exception as e:  # noqa: BLE001
            row.update(recovered_file_error=f"{type(e).__name__}: {str(e)[:160]}")
        row["doctor_exit_on_recovered"] = run_cli(cli, "doctor", out)[0]
        os.remove(out)
    return row


def analyse(kind, path, log_path, cli, meta, frames, pkts):
    blob = open(path, "rb").read()
    lb = open(log_path, "rb").read()
    logged = len(lb) // 4
    log_last = struct.unpack_from("<I", lb, (logged - 1) * 4)[0] if logged else 0
    msgs, err, chmeta, n_chunks, crc_bad, err2 = read_streaming(path)
    exact, first_bad = check_prefix(kind, msgs, frames, pkts, meta["frame_crcs"])
    row = dict(file_bytes=len(blob), logged_flushes=logged, log_tail_torn_bytes=len(lb) % 4, log_last_value_ok=log_last == logged,
               recovered_messages=len(msgs), recovered_minus_logged=len(msgs) - logged, exact_prefix=exact, first_bad_index=first_bad,
               nonseeking_end_error=err, crc_error=bool(err and "crc" in err.lower()), emit_chunks_chunks=n_chunks,
               emit_chunks_crc_bad=crc_bad, emit_chunks_end_error=err2, **{f"walk_{k}": v for k, v in walk_records(blob).items()})
    # metadata record + DataEnd absent is expected; seeking reader should fail on a killed file
    try:
        with open(path, "rb") as f:
            row["make_reader_messages"] = sum(1 for _ in make_reader(f).iter_messages())
    except Exception as e:  # noqa: BLE001
        row["make_reader_error"] = type(e).__name__
    if kind == "mic":
        row["channel_metadata_ok"] = chmeta == dict(sample_rate=str(RATE), channels="1", pre_skip=str(meta["pre_skip"]),
                                                     output_gain="0", opus_head=meta["opus_head_b64"]) if msgs else None
        row["clicks"] = click_errors(decode_opus([CompressedAudio.FromString(m.data).data for m in msgs], meta["pre_skip"]), len(msgs))
    row.update(check_recovered(cli, path, msgs))
    return row


def kill_test(media, work, results, cli, kind, mode, n):
    meta, frames, pkts = load_media(media)
    os.makedirs(work, exist_ok=True)
    rng = random.Random(20261113 + zlib.crc32(f"{kind}/{mode}".encode()))
    lo, hi = (0.05, 1.0) if mode == "fast" else (0.3, 6.0)
    rows, k = [], 0
    while sum(r["killed"] for r in rows) < n and k < n + 10:
        path, log_path = os.path.join(work, f"{kind}_{mode}_{k:02d}.mcap"), os.path.join(work, f"{kind}_{mode}_{k:02d}.log")
        delay = rng.uniform(lo, hi)
        pr, pid = spawn(kind, mode, path, log_path, media, "cam0" if kind == "cam" else "mic")
        time.sleep(delay)
        target = psutil.Process(pid)
        target.kill()                                  # TerminateProcess on the writing interpreter itself
        code = target.wait(10)
        pr.wait(10)
        row = dict(kind=kind, mode=mode, trial=k, kill_delay_s=round(delay, 4), writer_pid_is_popen_pid=pid == pr.pid,
                   exit_code=code, popen_exit_code=pr.returncode, killed=code != 0)
        row.update(analyse(kind, path, log_path, cli, meta, frames, pkts))
        os.remove(path); os.remove(log_path)
        rows.append(row); k += 1
        print(json.dumps({x: row[x] for x in ("trial", "exit_code", "logged_flushes", "recovered_messages", "exact_prefix", "recover_exit")}), flush=True)
    rs = [r for r in rows if r["killed"]]

    def vals(key):
        out = {}
        for r in rs:
            v = json.dumps(r.get(key)); out[v] = out.get(v, 0) + 1
        return out
    summary = dict(trials_killed=len(rs), not_killed=len(rows) - len(rs),
                   kill_delay_range=[min(r["kill_delay_s"] for r in rs), max(r["kill_delay_s"] for r in rs)],
                   recovered_range=[min(r["recovered_messages"] for r in rs), max(r["recovered_messages"] for r in rs)],
                   exact_prefix=sum(r["exact_prefix"] for r in rs), crc_errors=sum(r["crc_error"] for r in rs) + sum(r["emit_chunks_crc_bad"] for r in rs),
                   **{f"counts_{key}": vals(key) for key in ("recovered_minus_logged", "walk_tail_bytes", "log_tail_torn_bytes", "recover_exit",
                                                             "recover_same_messages", "recovered_file_summary", "doctor_exit_on_recovered",
                                                             "nonseeking_end_error", "emit_chunks_end_error", "make_reader_error",
                                                             "make_reader_messages", "writer_pid_is_popen_pid", "channel_metadata_ok")},
                   chunks_equal_messages=sum(r["emit_chunks_chunks"] == r["recovered_messages"] for r in rs))
    if kind == "mic":
        summary.update(clicks_checked_total=sum(r["clicks"]["clicks_checked"] for r in rs),
                       clicks_exact_total=sum(r["clicks"]["exact"] for r in rs),
                       click_errors_seen=sorted({e for r in rs for e in r["clicks"]["errors_seen"]}),
                       full_decode_baseline=click_errors(decode_opus(pkts, meta["pre_skip"]), len(pkts)))
    json.dump(dict(test=f"mcap_kill_{kind}_{mode}", env=env_info(cli), media=media_summary(meta), summary=summary, rows=rows),
              open(results, "w"), indent=1)
    print(json.dumps(summary, indent=1))


# ---------------------------------------------------------------- throughput
def top_procs(exclude, secs=3.0, n=8):
    ps = {}
    for p in psutil.process_iter(["name", "pid"]):
        try:
            p.cpu_percent(None); ps[p.pid] = p
        except psutil.Error:
            pass
    time.sleep(secs)
    out = []
    for pid, p in ps.items():
        try:
            if pid not in exclude and pid != 0:
                out.append((round(p.cpu_percent(None), 1), p.info["name"], pid))
        except psutil.Error:
            pass
    return sorted(out, reverse=True)[:n]


def throughput(media, work, results, cli, seconds):
    seconds = float(seconds)
    os.makedirs(work, exist_ok=True)
    before = dict(system_cpu_pct=psutil.cpu_percent(3.0), top=top_procs({os.getpid()}),
                  node_procs=sum(1 for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower().startswith("node")))
    kids = []
    for label, kind in (("cam0", "cam"), ("cam1", "cam"), ("cam2", "cam"), ("cam3", "cam"), ("mic", "mic")):
        b = os.path.join(work, f"tp_{label}")
        pr, pid = spawn(kind, "run", b + ".mcap", b + ".log", media, label, b + ".stats.json", seconds)
        kids.append((label, b, pr, psutil.Process(pid)))
    for *_x, p in kids:
        p.cpu_percent(None)
    psutil.cpu_percent(None)
    sys_samples, kid_samples = [], {k[0]: [] for k in kids}
    while any(k[2].poll() is None for k in kids):
        time.sleep(1.0)
        sys_samples.append(psutil.cpu_percent(None))
        for label, _b, pr, p in kids:
            try:
                if pr.poll() is None:
                    kid_samples[label].append(p.cpu_percent(None))
            except psutil.Error:
                pass
    after_top = top_procs({os.getpid()})
    rows = []
    for label, b, pr, p in kids:
        st = json.load(open(b + ".stats.json"))
        with open(b + ".mcap", "rb") as f:
            r = make_reader(f)
            s = r.get_summary()
            n_iter = sum(1 for _ in r.iter_messages())
            md = [(m.name, dict(m.metadata)) for m in r.iter_metadata()]
        st.update(exit_code=pr.returncode, psutil_cpu_pct_mean=float(np.mean(kid_samples[label][1:] or [0])),
                  write_MB_per_s=st["file_bytes"] / st["wall_s"] / 1e6,
                  overhead_per_msg_vs_payload=(st["file_bytes"] - st["payload_bytes"]) / st["messages"],
                  overhead_per_msg_vs_protobuf=(st["file_bytes"] - st["protobuf_bytes"]) / st["messages"],
                  summary_present=s is not None, summary_message_count=s.statistics.message_count if s else None,
                  summary_chunk_count=len(s.chunk_indexes) if s else None, statistics_chunk_count=s.statistics.chunk_count if s else None,
                  seeking_reader_messages=n_iter, metadata_records=md, doctor_exit=run_cli(cli, "doctor", b + ".mcap")[0])
        st["chunks_equal_messages"] = st["summary_chunk_count"] == st["messages"] == n_iter
        rows.append(st)
    # synthetic torn tail (the kills never produced one): cut a copy of cam0 at 60 % of its data, then recover it
    src, cut_path = os.path.join(work, "tp_cam0.mcap"), os.path.join(work, "tp_cam0_cut60.mcap")
    blob = open(src, "rb").read()
    open(cut_path, "wb").write(blob[:int(len(blob) * 0.6)])
    msgs = read_streaming(cut_path)[0]
    cut = dict(cut_bytes=int(len(blob) * 0.6), walk=walk_records(blob[:int(len(blob) * 0.6)]), streaming_messages=len(msgs),
               **check_recovered(cli, cut_path, msgs))
    os.remove(cut_path); del blob
    json.dump(dict(test="mcap_throughput", env=env_info(cli), media=media_summary(json.load(open(os.path.join(media, "media.json")))),
                   seconds=seconds, load_before=before, load_after_top=after_top, truncated_copy_recover=cut,
                   system_cpu_pct_during=dict(mean=float(np.mean(sys_samples)), max=float(np.max(sys_samples)), n=len(sys_samples)),
                   processes=rows), open(results, "w"), indent=1)
    for label, b, *_x in kids:
        for ext in (".mcap", ".log", ".stats.json"):
            os.remove(b + ext)
    print(json.dumps(rows, indent=1))


def media_summary(meta):
    s = meta["frame_sizes"]
    return dict(jpeg_bytes_mean=sum(s) / len(s), jpeg_bytes_min=min(s), jpeg_bytes_max=max(s), frames=len(s),
                jpeg_quality=meta["jpeg_quality"], noise_sigma=meta["noise_sigma"], opus_packets=meta["opus_packets"],
                opus_bytes_mean=meta["opus_bytes"] / meta["opus_packets"], opus_bitrate=meta["opus_bitrate"], pre_skip=meta["pre_skip"])


def env_info(cli):
    from importlib.metadata import version
    vs = {p: version(p) for p in ("mcap", "mcap-protobuf-support", "foxglove-schemas-protobuf", "protobuf", "av", "numpy", "pillow", "psutil")}
    return dict(python=sys.version.split()[0], platform=sys.platform, cpu_count=psutil.cpu_count(), packages=vs,
                mcap_cli=subprocess.run([cli, "--version"], capture_output=True, text=True).stdout.strip(),
                date=time.strftime("%Y-%m-%dT%H:%M:%S%z"))


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    {"media": build_media, "child": child, "kill": lambda *a: kill_test(*a[:6], int(a[6])), "throughput": throughput}[cmd](*args)
