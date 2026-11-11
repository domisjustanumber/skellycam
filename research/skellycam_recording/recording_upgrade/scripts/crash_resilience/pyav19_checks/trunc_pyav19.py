# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy"]
# ///
"""Emulated power loss (prefix cuts) on the PyAV 19.0.2 drained:150 kill images. 12 seeded cuts per variant.
ideal = packets of the image (ffprobe pos+size) entirely before the cut. Readers: ffprobe -count_frames; PyAV 19
naive loop (stop at first exception); for MJPEG, whether the LAST packet PyAV demuxes is byte-identical to the camera JPEG
(False = a torn JPEG is handed to the decoder).
usage: uv run --script trunc_pyav19.py <out_json>"""
import json, random, sys, zlib
from pathlib import Path
sys.path.insert(0, "C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/crash_resilience")
import common_cr as cc
import av
M = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/crash_resilience/pyav19_check")
T = M / "trunc"; T.mkdir(exist_ok=True)
ref = [cc.sha(b) for b in cc.load_jpegs(cc.DEFAULT_SET, 150)]
VARS = [("mjpeg", "mkv+fp"), ("mjpeg", "fmp4_every+fp"), ("mjpeg", "nut+fp"), ("av1", "mkv_cl0+fp"), ("av1", "fmp4_every+fp")]
out = {"env": {"pyav": av.__version__, "libavformat": ".".join(map(str, av.library_versions["libavformat"]))}, "cuts_per_variant": 12, "variants": []}
for p, c in VARS:
    img = cc.out_path(M, p, c, "drained150")
    data = img.read_bytes()
    pk = [(int(x["pos"]), int(x["size"])) for x in cc.ffprobe_packets(str(img)) if x.get("pos") not in (None, "N/A")]
    rng = random.Random(zlib.crc32(f"{p}{c}".encode()))
    offs = sorted(set(rng.randrange(64, len(data)) for _ in range(12)))
    rows = []
    for o in offs:
        dst = T / f"{img.stem}__cut{o}{img.suffix}"
        dst.write_bytes(data[:o])
        ideal = sum(1 for pos, sz in pk if pos + sz <= o)
        ff = cc.ffprobe_count(str(dst))["frames"]
        n = 0; last_exact = None; err = None
        try:
            with av.open(str(dst)) as ic:
                st = ic.streams.video[0]
                i = 0
                for pkt in ic.demux(st):
                    if pkt.size == 0:
                        for _ in pkt.decode(): n += 1
                        continue
                    if p == "mjpeg":
                        last_exact = cc.sha(bytes(pkt)) == ref[i]
                    i += 1
                    for _ in pkt.decode(): n += 1
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:100]}"
        rows.append({"offset": o, "ideal": ideal, "ffprobe": ff, "pyav": n, "pyav_error": err, "mjpeg_last_packet_byte_exact": last_exact})
        dst.unlink()
    s = {"payload": p, "container": c, "image_bytes": len(data), "cuts": len(rows),
         "ffprobe_eq_ideal": sum(r["ffprobe"] == r["ideal"] for r in rows),
         "ffprobe_eq_ideal_plus1": sum(r["ffprobe"] == r["ideal"] + 1 for r in rows),
         "ffprobe_lt_ideal": sum(r["ffprobe"] < r["ideal"] for r in rows),
         "max_ffprobe_shortfall": max([r["ideal"] - r["ffprobe"] for r in rows] + [0]),
         "pyav_lt_ffprobe": sum(r["pyav"] < r["ffprobe"] for r in rows),
         "max_pyav_short_vs_ffprobe": max([r["ffprobe"] - r["pyav"] for r in rows] + [0]),
         "mjpeg_torn_last_packet_delivered": sum(r["mjpeg_last_packet_byte_exact"] is False for r in rows) if p == "mjpeg" else None,
         "rows": rows}
    out["variants"].append(s)
    print({k: v for k, v in s.items() if k != "rows"}, flush=True)
Path(sys.argv[1]).write_text(json.dumps(out, indent=1))
