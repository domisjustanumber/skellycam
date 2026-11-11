# /// script
# dependencies = ["av==19.0.2", "numpy"]
# ///
"""For each WebM file: delta between PyAV 19 packet.pos and where the packet bytes actually start (functional, no timing)."""
import av, json, sys, collections
from pathlib import Path
res = {"pyav": av.__version__, "files": {}}
for f in sys.argv[2:]:
    data = Path(f).read_bytes(); deltas = collections.Counter(); found = 0; n = 0
    with av.open(f) as c:
        for p in c.demux(c.streams.video[0]):
            if p.size == 0: continue
            n += 1; b = bytes(p)
            at = data.find(b, max(0, p.pos), p.pos + 64 + p.size)
            if at >= 0: found += 1; deltas[at - p.pos] += 1
    res["files"][Path(f).resolve().as_posix()] = {"packets": n, "found_within_64B_after_pos": found, "delta_bytes_hist": dict(deltas)}
Path(sys.argv[1]).write_text(json.dumps(res, indent=1)); print(json.dumps(res, indent=1))
