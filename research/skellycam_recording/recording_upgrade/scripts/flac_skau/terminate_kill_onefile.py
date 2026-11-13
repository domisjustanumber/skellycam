"""External kills of the live FLAC writer with ONE live audio sidecar (skellyfileformat ADR-WD1R open work; spec SFT-453).

Same method as terminate_kill.py (PyAV 19.0.2, skellycam-phase1 venv; parent kills the child with Popen.kill(),
TerminateProcess on Windows, at a seeded random time; only kills with a non-zero exit code count), but the child
writes one live file <rec>.audio.skat.live with 48-byte records in the layout of skellyfileformat spec v0 sections
7.3/7.4 (a 256-byte SKAT header first is left out here; it is written once before any record):
  type 1 timing record: sample_index i64, host_ns i64, adc_ns i64 (INT64_MIN), current_ns i64 (INT64_MIN),
                        block_index u32, frames u32, type u16 = 1, flags u16, record_crc32 u32 over bytes 0-43;
  type 2 packet record: offset u64, first_sample i64, size u32, n_samples u32, frame_crc32 u32, 12 reserved bytes,
                        type u16 = 2, reserved u16, record_crc32 u32 over bytes 0-43.
Per block: timing record, then the FLAC frame (frame_size=1024, flush_packets=1), then its packet record; each
record flushed when written.

    python -I terminate_kill_onefile.py OUTDIR [N_FAST] [N_REALTIME]
"""
import json, os, random, struct, subprocess, sys, time, zlib, fractions

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import av  # noqa: E402
import numpy as np  # noqa: E402
from flac_skau import RATE, BLOCK, signal, flac_header_len, remux_mka  # noqa: E402

REC = 48
I64_MIN = -(2 ** 63)
TIM = struct.Struct("<qqqqIIHH")        # 44 bytes, then CRC
PKT = struct.Struct("<QqIII12xHH")      # 44 bytes, then CRC
assert TIM.size == PKT.size == 44
SECONDS = 120


def rec(body):
    return body + struct.pack("<I", zlib.crc32(body))


def child(flac_path, live_path, mode):
    pcm = signal(SECONDS, 1, seed=11)
    out = av.open(flac_path, "w", format="flac", options={"flush_packets": "1"})
    st = out.add_stream("flac", rate=RATE, layout="mono")
    st.codec_context.options = {"frame_size": str(BLOCK)}
    st.time_base = fractions.Fraction(1, RATE)
    live = open(live_path, "wb")
    offset, first, t0 = None, 0, time.perf_counter()
    n_blocks = len(pcm) // BLOCK
    i = 0
    while mode == "fast" or i < n_blocks:
        b0 = i * BLOCK
        if mode == "realtime":
            due = t0 + b0 / RATE
            while time.perf_counter() < due:
                time.sleep(0.001)
        live.write(rec(TIM.pack(b0, time.perf_counter_ns(), I64_MIN, I64_MIN, i & 0xFFFFFFFF, BLOCK, 1, 0))); live.flush()
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
            live.write(rec(PKT.pack(offset, first, len(data), BLOCK, zlib.crc32(data), 2, 0))); live.flush()
            offset += len(data); first += BLOCK
        i += 1
    out.close()
    print("finished", flush=True)


def read_live(b):
    """Records up to the first bad CRC or partial record (spec SFF-450)."""
    tims, pkts, n = [], [], 0
    for i in range(0, len(b) - REC + 1, REC):
        r = b[i:i + REC]
        if zlib.crc32(r[:44]) != struct.unpack_from("<I", r, 44)[0]:
            break
        typ = struct.unpack_from("<H", r, 40)[0]
        (tims if typ == 1 else pkts).append(TIM.unpack_from(r) if typ == 1 else PKT.unpack_from(r))
        n += 1
    return tims, pkts, len(b) - n * REC


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


def order_ok(b):
    """Each packet record follows a timing record whose block holds its first sample (SFF-257)."""
    last_tim_end = 0
    for i in range(0, len(b) - REC + 1, REC):
        r = b[i:i + REC]
        if zlib.crc32(r[:44]) != struct.unpack_from("<I", r, 44)[0]:
            break
        typ = struct.unpack_from("<H", r, 40)[0]
        if typ == 1:
            t = TIM.unpack_from(r); last_tim_end = t[0] + t[5]
        elif PKT.unpack_from(r)[1] + BLOCK > last_tim_end:
            return False
    return True


def analyse(base, source):
    flac, live = base + ".audio.flac", base + ".audio.skat.live"
    blob, lb = open(flac, "rb").read(), open(live, "rb").read()
    tims, pkts, trailing = read_live(lb)
    frame_crc_bad = sum(1 for o, f, s, n, c, *_ in pkts if zlib.crc32(blob[o:o + s]) != c)
    on_disk, demux_err = frames_on_disk(flac)
    row = dict(flac_bytes=len(blob), live_bytes=len(lb), live_trailing_bytes_ignored=trailing,
               live_tail_torn_bytes=len(lb) % REC, timing_records=len(tims), packet_records=len(pkts),
               packet_frame_crc_bad=frame_crc_bad, timing_minus_packet=len(tims) - len(pkts),
               write_order_ok=order_ok(lb), frames_on_disk=on_disk, demux_error=demux_err,
               frames_on_disk_not_indexed=(on_disk - len(pkts)) if on_disk is not None else None)
    if pkts:
        mka = base + ".audio.mka"
        try:
            remux_mka(flac, mka)
            dec = decode(mka)
            row.update(recovered_samples=int(len(dec)), recovered_vs_indexed_samples=int(len(dec)) - len(pkts) * BLOCK,
                       recovered_is_exact_source_prefix=bool(np.array_equal(dec, np.tile(source, len(dec) // len(source) + 1)[:len(dec)])))
        except Exception as e:  # noqa: BLE001
            row.update(recovery_error=f"{type(e).__name__}: {e}")
    return row


def trial(outdir, k, mode, delay):
    base = os.path.join(outdir, f"tk1_{mode}_{k:02d}")
    for ext in (".audio.flac", ".audio.skat.live", ".audio.mka"):
        if os.path.exists(base + ext):
            os.remove(base + ext)
    pr = subprocess.Popen([sys.executable, "-I", os.path.abspath(__file__), "child", base + ".audio.flac",
                           base + ".audio.skat.live", mode], stdout=subprocess.PIPE, text=True)
    assert pr.stdout.readline().strip() == "ready"
    time.sleep(delay)
    pr.kill()
    pr.wait()
    return dict(mode=mode, trial=k, kill_delay_s=round(delay, 4), exit_code=pr.returncode, killed=pr.returncode != 0)


def main():
    if sys.argv[1] == "child":
        child(*sys.argv[2:5]); return
    outdir = sys.argv[1]; os.makedirs(outdir, exist_ok=True)
    n_fast = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    n_rt = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    rng = random.Random(20261112)
    source = signal(SECONDS, 1, seed=11).reshape(-1)
    rows = []
    for mode, n, lo, hi in (("fast", n_fast, 0.05, 1.5), ("realtime", n_rt, 0.3, 6.0)):
        for k in range(n):
            meta = trial(outdir, k, mode, rng.uniform(lo, hi))
            meta.update(analyse(os.path.join(outdir, f"tk1_{mode}_{k:02d}"), source))
            rows.append(meta); print(json.dumps(meta), flush=True)
    keys = ("live_tail_torn_bytes", "live_trailing_bytes_ignored", "packet_frame_crc_bad", "timing_minus_packet",
            "frames_on_disk_not_indexed", "recovered_vs_indexed_samples", "write_order_ok")
    summary = {}
    for mode in ("fast", "realtime"):
        rs = [r for r in rows if r["mode"] == mode and r["killed"]]
        summary[mode] = {k: sorted({r.get(k) for r in rs}, key=lambda v: (v is None, v)) for k in keys}
        summary[mode].update(trials=len(rs), not_killed=sum(1 for r in rows if r["mode"] == mode and not r["killed"]),
                             demux_errors=sum(1 for r in rs if r["demux_error"]),
                             recovery_errors=sum(1 for r in rs if "recovery_error" in r),
                             recovered_exact_prefix=sum(1 for r in rs if r.get("recovered_is_exact_source_prefix")),
                             packet_records_range=[min(r["packet_records"] for r in rs), max(r["packet_records"] for r in rs)] if rs else None)
    result = dict(test="terminate_kill_onefile", pyav=av.__version__, python=sys.version.split()[0], platform=sys.platform,
                  seed=20261112, seconds_of_source=SECONDS, summary=summary, rows=rows)
    json.dump(result, open(os.path.join(outdir, "terminate_kill_onefile.json"), "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
