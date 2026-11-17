# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""Size and parse time of one hour of the proposed audio CSV sidecar (48 kHz, 1024-sample callbacks =
168,750 rows), with realistic values: host_ns since take start with 3 ms jitter, adc_ns ~6 ms earlier with
0.7 ms jitter (prior evidence, audio_skellycam §4.1), a 10 ppm clock. Variants:
  proposed  : block,first_sample,n_samples,host_ns,adc_ns,flags,crc32
  +offsets  : proposed + byte_offset,byte_size (FLAC frame location, for a WebCodecs player)
  minimal   : first_sample,host_ns
Also writes csv_example.csv (header, 12 rows, an example footer) to the results folder.

Usage: uv run --script .../csv_size.py      Output: results/audio_single_file/csv_size.json
"""
import json
import os
import sys
import time
import zlib

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import asf_common as C  # noqa: E402

ROWS = 3600 * C.RATE // C.BLOCK


def rows(variant, n):
    rng = np.random.default_rng(1)
    k = np.arange(n, dtype=np.int64)
    first = k * C.BLOCK
    true_ns = 50_000_000 + (first + C.BLOCK) * 1e9 / (C.RATE * (1 + 10e-6))
    host = (true_ns + 2_000_000 + np.abs(rng.normal(0, 3e6, n))).astype(np.int64)
    adc = (true_ns + rng.normal(0, 0.7e6, n)).astype(np.int64)
    off = 8286 + np.cumsum(np.r_[0, rng.integers(3000, 4200, n - 1)])
    size = rng.integers(3000, 4200, n)
    out = []
    for i in range(n):
        if variant == "minimal":
            out.append(f"{first[i]},{host[i]}\n")
            continue
        body = f"{i},{first[i]},{C.BLOCK},{host[i]},{adc[i]},0"
        if variant == "+offsets":
            body += f",{off[i]},{size[i]}"
        out.append(f"{body},{zlib.crc32(body.encode()):08x}\n")
    return out


def main():
    res = dict(rows_per_hour=ROWS, variants={})
    head = C.csv_header("6f1c2c1e-1d7e-4c47-9a3e-2f2b3c4d5e6f", "flac", "flac",
                        {"device": "example", "host_api": "WASAPI", "block": C.BLOCK, "clock_hz": 10_000_000})
    footer = ("# fit segment=0 first_row=0 rows=168750 n0=0 t0_ns=50021333 rate_hz=47999.520 ppm=-10.00 resid_p99_ns=2400000\n"
              "# end rows=168750 samples=172800000 audio_crc32=1a2b3c4d\n")
    for v in ("proposed", "+offsets", "minimal"):
        body = "".join(rows(v, ROWS))
        p = os.path.join(C.SCRATCH, f"csv_1h_{v.strip('+')}.csv")
        with open(p, "w", newline="\n") as f:
            f.write(head + body + footer)
        sz = os.path.getsize(p)
        r = dict(bytes=sz, mb_per_hour=round(sz / 1e6, 2), bytes_per_row=round(sz / ROWS, 1))
        if v == "proposed":
            t0 = time.perf_counter(); cs = C.parse_csv(p); r["strict_parse_s"] = round(time.perf_counter() - t0, 2)
            r["parsed_rows"] = len(cs["rows"]); r["footer_lines"] = len(cs["footer"])
        res["variants"][v] = r
        os.remove(p)
    with open(os.path.join(C.RESULTS, "csv_example.csv"), "w", newline="\n") as f:
        f.write(head + "".join(rows("proposed", 12)) + "# ...\n" + footer)
    json.dump(res, open(os.path.join(C.RESULTS, "csv_size.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
