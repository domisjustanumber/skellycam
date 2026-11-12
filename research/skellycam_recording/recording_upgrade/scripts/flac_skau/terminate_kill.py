"""External TerminateProcess during live FLAC + packet-index + timing-record writes (flac_skau FINDINGS §6 open item).

The F2 test in flac_skau.py killed the writer from inside (os._exit) at chosen points. Here a parent process
kills the writer from outside with Popen.kill() (TerminateProcess on Windows) at a random time, so the kill
can land anywhere, including inside a write. PyAV 19.0.2; run with the skellycam-phase1 venv:

    python -I terminate_kill.py OUTDIR [N_FAST] [N_REALTIME]

Child (one per trial) writes, per 1,024-sample block, as the design in flac_skau FINDINGS §5 does:
  1. a 48 B timing record to <rec>.skau.live (block index, first sample, a fake clock pair, CRC of the record);
  2. the FLAC frame (frame_size=1024, flush_packets=1) to <rec>.audio.flac;
  3. a 32 B packet record to <rec>.pkt.live: offset u64, size u32, first sample i64, frame CRC-32 u32, record
     CRC-32 u32, 4 B pad.
Each live file is flushed after each record (no fsync: TerminateProcess keeps the OS cache).
Modes: "fast" writes as fast as it can and loops the source until killed (more chances to land mid-write);
"realtime" paces blocks at 48 kHz. A trial counts only if the kill landed (exit code != 0).

Per trial the parent records: torn tail bytes of each live file, records whose own CRC fails, packet records
whose frame CRC does not match the FLAC bytes, FLAC frames on disk that no packet record covers, timing records
minus packet records, and recovery: stream copy into .mka (as flac_skau.remux_mka), decoded sample count and
whether the decoded audio is an exact prefix of the source.
"""
import json, os, random, struct, subprocess, sys, time, zlib, fractions

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import av  # noqa: E402
import numpy as np  # noqa: E402
from flac_skau import RATE, BLOCK, signal, flac_header_len, remux_mka  # noqa: E402

PKT = struct.Struct("<QIqII4x")      # 32 B: offset, size, first_sample, frame_crc, record_crc (over the first 24 B)
assert PKT.size == 32
TIM_SIZE = 48                        # timing record: block u64, first_sample i64, two clocks i64, record_crc u32 (over 32 B), pad
SECONDS = 120


def child(flac_path, pkt_path, tim_path, mode):
    pcm = signal(SECONDS, 1, seed=11)
    out = av.open(flac_path, "w", format="flac", options={"flush_packets": "1"})
    st = out.add_stream("flac", rate=RATE, layout="mono")
    st.codec_context.options = {"frame_size": str(BLOCK)}
    st.time_base = fractions.Fraction(1, RATE)
    pkt, tim = open(pkt_path, "wb"), open(tim_path, "wb")
    offset, first, t0 = None, 0, time.perf_counter()
    n_blocks = len(pcm) // BLOCK                 # 5,625: the source tiles exactly
    i = 0
    while mode == "fast" or i < n_blocks:
        b0 = i * BLOCK
        if mode == "realtime":
            due = t0 + b0 / RATE
            while time.perf_counter() < due:
                time.sleep(0.001)
        body = struct.pack("<Qqqq", i, b0, time.perf_counter_ns(), time.time_ns())
        tim.write(body + struct.pack("<I", zlib.crc32(body)) + b"\0" * (TIM_SIZE - len(body) - 4)); tim.flush()
        s0 = (i % n_blocks) * BLOCK
        fr = av.AudioFrame.from_ndarray(pcm[s0:s0 + BLOCK].reshape(1, -1), format="s16", layout="mono")
        fr.sample_rate = RATE; fr.pts = b0
        for p in st.encode(fr):
            data = bytes(p)
            if not data:
                continue
            out.mux(p)
            if offset is None:
                offset = flac_header_len(open(flac_path, "rb").read(65536))[0]
                print("ready", flush=True)
            head = struct.pack("<QIqI", offset, len(data), first, zlib.crc32(data))
            pkt.write(head + struct.pack("<I", zlib.crc32(head)) + b"\0" * 4); pkt.flush()
            offset += len(data); first += BLOCK
        i += 1
    out.close()
    print("finished", flush=True)


def frames_on_disk(path):
    try:
        with av.open(path) as c:
            return sum(1 for p in c.demux(c.streams.audio[0]) if p.size), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def decode(path):
    with av.open(path) as c:
        s = c.streams.audio[0]
        return np.concatenate([f.to_ndarray().reshape(-1) for f in c.decode(s)])


def analyse(base, source):
    flac, pkt_p, tim_p = base + ".audio.flac", base + ".pkt.live", base + ".skau.live"
    blob, pb, tb = open(flac, "rb").read(), open(pkt_p, "rb").read(), open(tim_p, "rb").read()
    recs = [PKT.unpack_from(pb, i) for i in range(0, len(pb) - len(pb) % 32, 32)]
    rec_crc_bad = sum(1 for i in range(0, len(pb) - len(pb) % 32, 32) if zlib.crc32(pb[i:i + 24]) != PKT.unpack_from(pb, i)[4])
    frame_crc_bad = sum(1 for o, s, f, c, rc in recs if zlib.crc32(blob[o:o + s]) != c)
    tim_n = len(tb) // TIM_SIZE
    tim_crc_bad = sum(1 for i in range(tim_n) if zlib.crc32(tb[i * 48:i * 48 + 32]) != struct.unpack_from("<I", tb, i * 48 + 32)[0])
    on_disk, demux_err = frames_on_disk(flac)
    end_indexed = recs[-1][0] + recs[-1][1] if recs else (flac_header_len(blob)[0] if len(blob) >= 42 else 0)
    row = dict(flac_bytes=len(blob), packet_records=len(recs), packet_tail_torn_bytes=len(pb) % 32,
               packet_record_crc_bad=rec_crc_bad, packet_frame_crc_bad=frame_crc_bad,
               timing_records=tim_n, timing_tail_torn_bytes=len(tb) % TIM_SIZE, timing_record_crc_bad=tim_crc_bad,
               timing_minus_packet=tim_n - len(recs), frames_on_disk=on_disk, demux_error=demux_err,
               frames_on_disk_not_indexed=(on_disk - len(recs)) if on_disk is not None else None,
               bytes_after_last_indexed=len(blob) - end_indexed)
    if recs:
        mka = base + ".audio.mka"
        try:
            remux_mka(flac, mka)
            dec = decode(mka)
            row.update(recovered_samples=int(len(dec)), recovered_vs_indexed_samples=int(len(dec)) - len(recs) * BLOCK,
                       recovered_is_exact_source_prefix=bool(np.array_equal(dec, np.tile(source, len(dec) // len(source) + 1)[:len(dec)])))
        except Exception as e:  # noqa: BLE001
            row.update(recovery_error=f"{type(e).__name__}: {e}")
    return row


def trial(outdir, k, mode, delay):
    base = os.path.join(outdir, f"tk_{mode}_{k:02d}")
    for ext in (".audio.flac", ".pkt.live", ".skau.live", ".audio.mka"):
        if os.path.exists(base + ext):
            os.remove(base + ext)
    pr = subprocess.Popen([sys.executable, "-I", os.path.abspath(__file__), "child", base + ".audio.flac",
                           base + ".pkt.live", base + ".skau.live", mode], stdout=subprocess.PIPE, text=True)
    assert pr.stdout.readline().strip() == "ready"
    time.sleep(delay)
    pr.kill()                      # TerminateProcess on Windows
    pr.wait()
    return dict(mode=mode, trial=k, kill_delay_s=round(delay, 4), exit_code=pr.returncode, killed=pr.returncode != 0)


def main():
    if sys.argv[1] == "child":
        child(*sys.argv[2:6]); return
    outdir = sys.argv[1]; os.makedirs(outdir, exist_ok=True)
    n_fast = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    n_rt = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    rng = random.Random(20261112)
    source = signal(SECONDS, 1, seed=11).reshape(-1)
    rows = []
    for mode, n, lo, hi in (("fast", n_fast, 0.05, 1.5), ("realtime", n_rt, 0.3, 6.0)):
        for k in range(n):
            meta = trial(outdir, k, mode, rng.uniform(lo, hi))
            meta.update(analyse(os.path.join(outdir, f"tk_{mode}_{k:02d}"), source))
            rows.append(meta); print(json.dumps(meta), flush=True)
    keys = ("packet_tail_torn_bytes", "packet_record_crc_bad", "packet_frame_crc_bad", "timing_tail_torn_bytes",
            "timing_record_crc_bad", "timing_minus_packet", "frames_on_disk_not_indexed", "recovered_vs_indexed_samples")
    summary = {}
    for mode in ("fast", "realtime"):
        rs = [r for r in rows if r["mode"] == mode and r["killed"]]
        summary[mode] = {k: sorted({r.get(k) for r in rs}, key=lambda v: (v is None, v)) for k in keys}
        summary[mode].update(trials=len(rs), not_killed=sum(1 for r in rows if r["mode"] == mode and not r["killed"]), demux_errors=sum(1 for r in rs if r["demux_error"]),
                             recovery_errors=sum(1 for r in rs if "recovery_error" in r),
                             recovered_exact_prefix=sum(1 for r in rs if r.get("recovered_is_exact_source_prefix")),
                             packet_records_range=[min(r["packet_records"] for r in rs), max(r["packet_records"] for r in rs)])
    result = dict(test="terminate_kill", pyav=av.__version__, python=sys.version.split()[0], platform=sys.platform,
                  seconds_of_source=SECONDS, summary=summary, rows=rows)
    json.dump(result, open(os.path.join(outdir, "terminate_kill.json"), "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
