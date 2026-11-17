# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""Size of one hour of the audio CSV sidecar for Opus, against ../csv_size.py (callback rows, 9.97 MB/h measured):
  callback : unchanged from WAV (block,first_sample,n_samples,host_ns,adc_ns,flags,crc32), 168,750 rows/h
             (rows from ../csv_size.py rows('proposed'))
  packet   : one row per 20 ms Opus packet for a WebCodecs player: packet,first_sample,byte_offset,byte_size,crc32
             (180,000 rows/h; byte sizes from the clean stereo 256 kbit/s Ogg file of kill_opus.py, repeated)
Strict-parse time for the packet variant with asf_common.parse_csv is not needed (same parser, same row count order).

Usage: uv run --script .../opus/csv_size_opus.py     Output: results/audio_single_file/opus/csv_size_opus.json
"""
import json
import os
import sys
import zlib

import av
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import opus_common as O  # noqa: E402
import csv_size  # noqa: E402

C = O.C


def main():
    with av.open(os.path.join(O.SCRATCH, "clean", "ogg_pd20__clean.opus")) as c:
        sizes = np.array([p.size for p in c.demux(c.streams.audio[0]) if p.size])
    rows_h = 3600 * 50
    sz = np.resize(sizes, rows_h)
    off = 4096 + np.cumsum(np.r_[0, sz[:-1] + 28])  # + Ogg page header per packet (one packet per page)
    head = C.csv_header("6f1c2c1e-1d7e-4c47-9a3e-2f2b3c4d5e6f", "opus", "opus", {"pre_skip": O.PRESKIP, "rows": "packet"})
    lines = []
    for i in range(rows_h):
        body = f"{i},{i * 960 - O.PRESKIP},{off[i]},{sz[i]}"
        lines.append(f"{body},{zlib.crc32(body.encode()):08x}\n")
    pkt = len(head) + sum(len(s) for s in lines)
    cb = len(head) + sum(len(s) for s in csv_size.rows("proposed", csv_size.ROWS))
    res = dict(callback=dict(rows=csv_size.ROWS, mb_per_hour=round(cb / 1e6, 2)),
               packet=dict(rows=rows_h, mb_per_hour=round(pkt / 1e6, 2), bytes_per_row=round(pkt / rows_h, 1),
                           mean_packet_bytes=round(float(sizes.mean()), 1)))
    json.dump(res, open(os.path.join(O.RESULTS, "csv_size_opus.json"), "w"), indent=1)
    print(res)


if __name__ == "__main__":
    main()
