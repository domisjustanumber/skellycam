# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Read-only scan of GF02 Part A sidecars (*.frames.bin) for FLAG_PTS_ADJUSTED (flags & 1).

Record layout from scripts/python_integration/recwriter.py:33-46: 64-byte header, then 48-byte
records "<qqqIIIII" + "I" (frame_number, timestamp_ns, pts, size, packet_crc32, flags, write_index,
reserved, record_crc32). Also lists, per file, which of GF02's PyAV seek targets hit a flagged frame
(targets from GF02_partA_write.json / GF02_partA_long_write.json `pyav_seek[].k`).
No timing. Output: results/jpeg_passthrough/step3_gf02_sidecar_flags.json
"""
import glob, json, os, struct, sys

RU = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MEDIA = "C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/crash_resilience/gapfill/GF02/partA/"
GF = os.path.join(RU, "results", "crash_resilience", "gapfill")

targets = {}
for jf in ("GF02_partA_write.json", "GF02_partA_long_write.json"):
    for name, v in json.load(open(os.path.join(GF, jf)))["files"].items():
        targets[name.rsplit(".", 1)[0]] = [s["k"] for s in v.get("pyav_seek", [])]

out = {"media_dir": MEDIA, "files": {}}
for f in sorted(glob.glob(MEDIA + "*.frames.bin")):
    stem = os.path.basename(f)[: -len(".frames.bin")]
    b = open(f, "rb").read()
    body = b[64:]
    assert len(body) % 48 == 0, f
    flagged = []
    for i in range(len(body) // 48):
        fn, ts, pts, sz, crc, fl, wi, rs, rc = struct.unpack_from("<qqqIIIIII", body, i * 48)
        if fl & 1:
            flagged.append({"record_index": i, "frame_number": fn, "pts": pts})
    tk = targets.get(stem, [])
    hit = [t for t in tk if t in {x["record_index"] for x in flagged}]
    out["files"][stem] = {"records": len(body) // 48, "pts_adjusted": len(flagged),
                          "flagged_first5": flagged[:5], "pyav_seek_targets": tk,
                          "targets_on_flagged_record": hit}
json.dump(out, open(os.path.join(RU, "results", "jpeg_passthrough", "step3_gf02_sidecar_flags.json"), "w"), indent=1)
for k, v in out["files"].items():
    if v["pts_adjusted"]:
        print(k, v["pts_adjusted"], v["flagged_first5"][:2], "hits:", v["targets_on_flagged_record"])
