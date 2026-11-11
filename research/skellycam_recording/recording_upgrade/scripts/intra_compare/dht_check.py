"""Which JPEG paths use the standard (ITU-T T.81 Annex K) Huffman tables and which write optimised ones?

Reads the sample JPEGs saved by sweep.py --keep-media (skellycam-raw/.../intra_compare/samples/<input>/) and one
camera JPEG per corpus set, parses every DHT segment and compares each table's 16 code-length counts (BITS) with
Annex K tables K.3 (DC luma), K.4 (DC chroma), K.5 (AC luma), K.6 (AC chroma). Also records the DQT table count.
Plain Python, no third-party imports:
  python research/skellycam_recording/recording_upgrade/scripts/intra_compare/dht_check.py
Writes results/intra_compare/dht_check.json.
"""
from __future__ import annotations

import json
from pathlib import Path

RAW = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109")
OUT = Path(__file__).resolve().parents[2] / "results/intra_compare/dht_check.json"
STD = {  # BITS (number of codes of length 1..16)
    "K.3 DC luma": [0, 1, 5, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
    "K.4 DC chroma": [0, 3, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0],
    "K.5 AC luma": [0, 2, 1, 3, 3, 2, 4, 3, 5, 5, 4, 4, 0, 0, 1, 0x7D],
    "K.6 AC chroma": [0, 2, 1, 2, 4, 4, 3, 4, 7, 5, 4, 4, 0, 1, 2, 0x77],
}


def segments(jb: bytes):
    i = 2
    while i < len(jb) - 4 and jb[i] == 0xFF:
        m = jb[i + 1]
        ln = int.from_bytes(jb[i + 2:i + 4], "big")
        yield m, jb[i + 4:i + 2 + ln]
        if m == 0xDA:
            return
        i += 2 + ln


def tables(jb: bytes) -> dict:
    dht, ndqt = [], 0
    for m, body in segments(jb):
        if m == 0xDB:
            j = 0
            while j < len(body):
                ndqt += 1
                j += 1 + 64 * (2 if body[j] >> 4 else 1)
        if m == 0xC4:
            j = 0
            while j < len(body):
                tc, th = body[j] >> 4, body[j] & 15
                bits = list(body[j + 1:j + 17])
                n = sum(bits)
                std = [k for k, v in STD.items() if v == bits]
                dht.append({"class": "AC" if tc else "DC", "id": th, "codes": n, "standard": std[0] if std else None})
                j += 17 + n
    return {"dqt_tables": ndqt, "dht": dht, "all_dht_standard": bool(dht) and all(t["standard"] for t in dht),
            "has_dht": bool(dht)}


def main() -> None:
    rep: dict = {"samples": {}, "camera": {}}
    for p in sorted((RAW / "intra_compare" / "samples").glob("*/*_000.jpg")):
        rep["samples"][f"{p.parent.name}/{p.name}"] = tables(p.read_bytes())
    for s in ("c930e_720p_flash", "c922_720p_flash", "c930e_1080p", "c922_1080p"):
        p = sorted((RAW / "corpus" / s).glob("frame_*.jpg"))[0]
        rep["camera"][s] = tables(p.read_bytes())
    OUT.write_text(json.dumps(rep, indent=1))
    for k, v in {**rep["samples"], **rep["camera"]}.items():
        print(k, "DQT", v["dqt_tables"], "DHT", len(v["dht"]), "all standard" if v["all_dht_standard"] else
              [(t["class"], t["id"], t["standard"]) for t in v["dht"]])


if __name__ == "__main__":
    main()
