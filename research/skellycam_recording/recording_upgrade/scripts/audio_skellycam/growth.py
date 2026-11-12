"""'Virtual kill' probe: how far behind the input is the decodable audio on disk, after every block?

For each format: feed 1024-sample int16 blocks (48 kHz mono synthetic tone, like a PortAudio callback),
and after every 4th block copy the file as it is on disk at that moment (bytes the OS already has,
with the header as written so far). Each copy is what a hard kill at that moment would leave
(the process dies, the OS keeps what was written). Decode each copy with PyAV and count samples.

lag = samples handed to the writer - samples decodable from the copy.

Usage: python -I growth.py <outdir_json> [seconds]
"""
import json
import os
import shutil
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ac_common import FORMATS, SCRATCH, BlockWriter, decode_pyav, synth  # noqa: E402

BLOCK = 1024
EVERY = 4


def run(name, seconds, work):
    path = os.path.join(work, name + FORMATS[name]["ext"])
    w = BlockWriter(name, path)
    rate = w.rate
    snaps = []
    n, k = 0, 0
    mux_ns = []
    while n < rate * seconds:
        t0 = time.perf_counter_ns()
        w.write(synth(n, BLOCK, rate))
        mux_ns.append(time.perf_counter_ns() - t0)
        n += BLOCK
        k += 1
        if k % EVERY == 0:
            sp = os.path.join(work, f"{name}_snap{k:05d}")
            if os.path.exists(path):
                shutil.copyfile(path, sp)
            else:  # PyAV creates the file at the first mux (start_encoding); nothing on disk yet
                open(sp, "wb").close()
            snaps.append((k, n, sp))
    w.close()
    final = decode_pyav(path)
    lags, sizes_zero = [], 0
    for k, n_in, sp in snaps:
        if os.path.getsize(sp) == 0:
            sizes_zero += 1
        d = decode_pyav(sp)
        lags.append(dict(block=k, n_in=n_in, decoded=d["samples"], err=d["error"]))
        os.remove(sp)
    lag_samples = [x["n_in"] - x["decoded"] for x in lags]
    lag_ms = [1000.0 * v / rate for v in lag_samples]
    errs = sum(1 for x in lags if x["err"])
    # an error before any audio could exist (headers only, or no file yet) is "nothing yet", not corruption
    seen, errs_after = False, 0
    for x in lags:
        if x["decoded"] > 0:
            seen = True
        if x["err"] and seen:
            errs_after += 1
    first_audio_block = next((x["block"] for x in lags if x["decoded"] > 0), None)
    os.remove(path)
    return dict(
        format=name, settings=FORMATS[name], seconds=seconds, rate=rate, snapshots=len(lags),
        snapshots_unreadable=errs, unreadable_after_first_audio=errs_after,
        first_decodable_ms=(round(1000.0 * first_audio_block * BLOCK / rate, 1) if first_audio_block else None), snapshots_zero_bytes=sizes_zero,
        lag_ms_min=round(min(lag_ms), 1), lag_ms_median=round(statistics.median(lag_ms), 1),
        lag_ms_p95=round(sorted(lag_ms)[int(0.95 * (len(lag_ms) - 1))], 1), lag_ms_max=round(max(lag_ms), 1),
        final_decoded=final["samples"], final_in=n,
        write_us_median=round(statistics.median(mux_ns) / 1e3, 1),
        write_us_p99=round(sorted(mux_ns)[int(0.99 * (len(mux_ns) - 1))] / 1e3, 1),
        lag_ms_series=[round(v, 1) for v in lag_ms[:60]],
        first_err=next((x["err"] for x in lags if x["err"]), None),
    )


def main():
    out = sys.argv[1]
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 12.0
    work = os.path.join(SCRATCH, "growth")
    os.makedirs(work, exist_ok=True)
    res = []
    for name in FORMATS:
        r = run(name, seconds, work)
        print(name, r["lag_ms_min"], r["lag_ms_median"], r["lag_ms_max"], "unreadable", r["snapshots_unreadable"], "after_audio", r["unreadable_after_first_audio"], "first_ms", r["first_decodable_ms"], flush=True)
        res.append(r)
    import av
    json.dump(dict(pyav=av.__version__, block=BLOCK, every=EVERY, results=res), open(out, "w"), indent=1)


if __name__ == "__main__":
    main()
