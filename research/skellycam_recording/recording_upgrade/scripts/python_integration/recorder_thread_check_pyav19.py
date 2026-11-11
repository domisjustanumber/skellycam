# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""Functional check (no timing) of recwriter.RecorderThread under PyAV 19.0.2.

Case "block": 5 cameras (mkv real, mkv index, mp4f real, avi index, mkv real), 120 c922_720p_flash frames each,
submitted from 5 producer threads at once, unpaced, policy="block". Expect 0 drops, no thread error, every file
byte-exact and sidecar == container.
Case "drop": 1 camera, maxsize=2, policy="drop", 120 frames submitted unpaced. Expect: drops counted (any
number), frames in the file == submitted - dropped, every written packet byte-equal to the frame the
sidecar says it is (CRC + size), sidecar records == container packets, FLAG_FRAME_GAP set where frames were
dropped.
Media -> raw folder python_integration/recorder_thread_pyav19; JSON -> argv[1].
"""
from __future__ import annotations

import json
import shutil
import sys
import threading
import zlib
from pathlib import Path

import av
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import recwriter as rw  # noqa: E402

CORPUS = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus")
OUT = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/python_integration/recorder_thread_pyav19")
N = 120


def verify(stem: Path, frames: list[bytes]) -> dict:
    man = json.loads(stem.with_name(stem.name + ".recording.json").read_text())
    side = rw.read_sidecar(stem.with_name(man["sidecar"]))
    pk = list(rw.RecordingReader(stem.with_name(man["video"])).packets())
    recs = side.records
    by_fn = {i: f for i, f in enumerate(frames)}
    return {"manifest_state": man["state"], "packets": len(pk), "sidecar_records": int(len(recs)),
            "packets_match_sidecar_crc_size": len(pk) == len(recs) and all(
                zlib.crc32(b) == int(r["packet_crc32"]) and len(b) == int(r["size"]) for (_, b, _, _), r in zip(pk, recs)),
            "packets_equal_source_frame": all(b == by_fn[int(r["frame_number"])] for (_, b, _, _), r in zip(pk, recs)),
            "frame_gap_flags": int(np.count_nonzero(recs["flags"] & rw.FLAG_FRAME_GAP))}


def main():
    dst = Path(sys.argv[1])
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    frames = [f.read_bytes() for f in sorted((CORPUS / "c922_720p_flash").glob("frame_*.jpg"))][:N]
    out = {"what": "RecorderThread functional check; no timing", "pyav": av.__version__,
           "ffmpeg": av.ffmpeg_version_info, "date": "2026-11-09", "block": [], "drop": None}
    variants = [("mkv", "real"), ("mkv", "index"), ("mp4f", "real"), ("avi", "index"), ("mkv", "real")]
    recs, stems = [], []
    for k, (cont, mode) in enumerate(variants):
        stem = OUT / f"block_cam{k}.{cont}.{mode}"
        recs.append(rw.RecorderThread(rw.RecordingWriter(stem, 1280, 720, container=cont, pts_mode=mode),
                                      maxsize=256, policy="block"))
        stems.append(stem)

    def produce(r):
        for i, f in enumerate(frames):
            r.submit(f, i, 10_000_000_000 + i * 33_333_333)
    ths = [threading.Thread(target=produce, args=(r,)) for r in recs]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    for (cont, mode), r, stem in zip(variants, recs, stems):
        man = r.stop()
        out["block"].append({"container": cont, "pts_mode": mode, "dropped": man["dropped"],
                             "thread_error": man["thread_error"], **verify(stem, frames)})
    stem = OUT / "drop_cam.mkv.real"
    r = rw.RecorderThread(rw.RecordingWriter(stem, 1280, 720, container="mkv"), maxsize=2, policy="drop")
    produce(r)
    man = r.stop()
    out["drop"] = {"submitted": N, "dropped": man["dropped"], "thread_error": man["thread_error"],
                   **verify(stem, frames)}
    out["drop"]["written_eq_submitted_minus_dropped"] = out["drop"]["packets"] == N - man["dropped"]
    dst.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
