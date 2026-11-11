"""Audit which ITU-T T.81 coding process each corpus JPEG uses (licensing relevance for G1).

T.81 Annex L lists patents only for the arithmetic-coding processes (SOF9-SOF15 with DAC) and the
hierarchical lossless case. This script walks the marker segments of every frame_*.jpg in the MJPEG
corpus sets (read-only) and counts SOFn markers, DAC (0xFFCC) and DHT (0xFFC4) segments.

Usage: python jpeg_process_audit.py --corpus <corpus dir> --out <json>
"""
import argparse
import collections
import json
import pathlib

SOF_NAMES = {0xC0: "SOF0 baseline Huffman", 0xC1: "SOF1 extended Huffman", 0xC2: "SOF2 progressive Huffman",
             0xC3: "SOF3 lossless Huffman", 0xC5: "SOF5", 0xC6: "SOF6", 0xC7: "SOF7",
             0xC9: "SOF9 arithmetic", 0xCA: "SOF10 arithmetic", 0xCB: "SOF11 arithmetic",
             0xCD: "SOF13 arithmetic", 0xCE: "SOF14 arithmetic", 0xCF: "SOF15 arithmetic"}


def markers(b: bytes):
    """Yield marker codes in header segments up to and including SOS."""
    i = 2  # skip SOI
    while i + 4 <= len(b):
        if b[i] != 0xFF:
            return
        m = b[i + 1]
        if m == 0xFF:
            i += 1
            continue
        yield m
        if m == 0xDA:  # SOS: entropy-coded data follows
            return
        seglen = int.from_bytes(b[i + 2:i + 4], "big")
        i += 2 + seglen


ap = argparse.ArgumentParser()
ap.add_argument("--corpus", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()
corpus = pathlib.Path(a.corpus)
index = json.loads((corpus / "index.json").read_text())
res = {}
for name, meta in index.items():
    if meta.get("kind") != "mjpeg":
        continue
    files = sorted((corpus / name).glob("frame_*.jpg"))
    sof = collections.Counter()
    dac = dht = soi_ok = 0
    for f in files:
        b = f.read_bytes()
        soi_ok += b[:2] == b"\xff\xd8"
        ms = list(markers(b))
        for m in ms:
            if m in SOF_NAMES:
                sof[SOF_NAMES[m]] += 1
        dac += 0xCC in ms
        dht += 0xC4 in ms
    res[name] = {"files": len(files), "soi_ok": soi_ok, "sof_counts": dict(sof),
                 "frames_with_DAC": dac, "frames_with_DHT": dht}
    print(name, res[name])
pathlib.Path(a.out).write_text(json.dumps(res, indent=1), encoding="utf-8")
