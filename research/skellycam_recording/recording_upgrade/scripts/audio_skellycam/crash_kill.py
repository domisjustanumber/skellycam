"""Hard-kill test (like GF02 in jpeg_passthrough/FINDINGS.md), for audio-only files.

A child process writes a paced, real-time stream of 1024-sample int16 blocks (48 kHz mono synthetic tone)
through BlockWriter (PyAV encode + mux, pts = sample count). After each write() returns it publishes the
acknowledged sample count in shared memory. Kill methods:
  exit : the child calls os._exit(1) right after block K returns (lands between blocks);
  term : the parent waits until K blocks are acknowledged, sleeps a random 0-21 ms, then
         TerminateProcess (Popen.kill on Windows) - may land inside encode/mux.
lost = acknowledged samples - samples PyAV decodes from the killed file.
Killed files are kept in the scratchpad for the reader tests (killed_readers.py).

Usage: python -I crash_kill.py <out_json> [format,format,...]
"""
import json
import multiprocessing as mp
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ac_common import FORMATS, SCRATCH, BlockWriter, decode_pyav, flac_streaminfo, mkv_tail_info, ogg_pages, synth  # noqa: E402

BLOCK = 1024
KILL_S = [1.0, 2.2, 3.7, 5.3, 7.9, 10.4]
DEFAULT = ["ogg_opus", "ogg_opus_pd20", "ogg_opus_pd60", "ogg_opus_pd100", "mka_opus", "mka_opus_ct100",
           "webm_opus_ct100", "flac_native", "flac_native_fs1024", "ogg_flac", "mka_flac_ct100", "wav_pcm"]


def child(name, path, acked, exit_after_blocks):
    w = BlockWriter(name, path)
    rate = w.rate
    t0 = time.perf_counter()
    k, n = 0, 0
    while True:
        due = t0 + (k + 1) * BLOCK / rate  # a callback delivers block k when its last sample is captured
        while True:
            d = due - time.perf_counter()
            if d <= 0:
                break
            time.sleep(min(d, 0.002))
        w.write(synth(n, BLOCK, rate))
        n += BLOCK
        k += 1
        acked.value = n
        if exit_after_blocks and k >= exit_after_blocks:
            os._exit(1)
        if k > rate * 30 / BLOCK:
            w.close()
            return


def one(name, method, kill_s, work, rng):
    rate = FORMATS[name]["rate"]
    k_target = int(round(kill_s * rate / BLOCK))
    path = os.path.join(work, f"{name}__{method}__{kill_s:.1f}s{FORMATS[name]['ext']}")
    if os.path.exists(path):
        os.remove(path)
    acked = mp.Value("q", 0, lock=False)
    p = mp.Process(target=child, args=(name, path, acked, k_target if method == "exit" else 0))
    p.start()
    jitter_ms = None
    if method == "term":
        while acked.value < k_target * BLOCK:
            time.sleep(0.001)
        jitter_ms = rng.uniform(0, 21.0)
        time.sleep(jitter_ms / 1000)
        p.kill()  # TerminateProcess on Windows
    p.join(60)
    ack = acked.value
    d = decode_pyav(path)
    r = dict(format=name, method=method, kill_s=kill_s, exitcode=p.exitcode, acked=ack,
             decoded=d["samples"], lost=ack - d["samples"], lost_ms=round(1000.0 * (ack - d["samples"]) / rate, 1),
             demux_error=d["error"], decode_errors=d["decode_errors"], packets=d["packets"],
             bytes=os.path.getsize(path) if os.path.exists(path) else None, file=os.path.basename(path),
             term_extra_sleep_ms=None if jitter_ms is None else round(jitter_ms, 1))
    if os.path.exists(path):
        fmt = FORMATS[name]["fmt"]
        if fmt == "flac":
            r["streaminfo"] = flac_streaminfo(path)
        elif fmt == "ogg":
            r["ogg"] = ogg_pages(path)
        elif fmt in ("matroska", "webm"):
            r["mkv"] = mkv_tail_info(path)
        elif fmt == "wav":
            b = open(path, "rb").read(44)
            r["wav_riff_size"] = int.from_bytes(b[4:8], "little")
            r["wav_data_size_field"] = int.from_bytes(b[40:44], "little") if b[36:40] == b"data" else None
    return r


def main():
    out = sys.argv[1]
    names = sys.argv[2].split(",") if len(sys.argv) > 2 else DEFAULT
    work = os.path.join(SCRATCH, "killed")
    os.makedirs(work, exist_ok=True)
    rng = random.Random(20261112)
    res = []
    for name in names:
        for i, ks in enumerate(KILL_S):
            for method in (("exit", "term") if i % 2 == 0 else ("term", "exit")):
                r = one(name, method, ks, work, rng)
                print(name, method, ks, "lost_ms", r["lost_ms"], "err", r["demux_error"], flush=True)
                res.append(r)
        json.dump(dict(block=BLOCK, kill_s=KILL_S, results=res), open(out, "w"), indent=1)
    import av
    json.dump(dict(pyav=av.__version__, block=BLOCK, kill_s=KILL_S, results=res), open(out, "w"), indent=1)


if __name__ == "__main__":
    main()
