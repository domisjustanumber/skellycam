"""Functional round-trip test of recwriter.RecordingWriter / RecordingReader on the real-camera corpus.

For every MJPEG corpus set x container (mkv, mp4f, avi):
  - write every frame with its timestamp (real MF host-arrival QPC ns for the two *_flash sets, read from the
    capture's frames.jsonl; for the short sets a synthetic 33.333 ms lattice with +-2 ms deterministic jitter),
  - read the packets back (no decode) and check: byte-exact JPEG, packet count, container PTS == sidecar PTS,
    sidecar timestamp_ns == input exactly, |PTS*tb - (t - t0)| <= tb/2 unless the writer flagged PTS_ADJUSTED,
  - check that every frame decodes with PyAV and with cv2 (count), and what cv2 reports (FRAME_COUNT, FPS, FOURCC).
Also writes one file with a deliberate frame-number gap to check FLAG_FRAME_GAP.
No timing is measured. Media goes to the raw folder (outside the repo); JSON + Markdown go to results/.

Run (repo root):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/python_integration/test_roundtrip.py
"""
from __future__ import annotations

import json
import shutil
import sys
import zlib
from fractions import Fraction
from pathlib import Path

import av
import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import recwriter as rw  # noqa: E402

REPO = Path(__file__).resolve().parents[5]
CORPUS = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus")
MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/python_integration/roundtrip")
RESULTS = REPO / "research/skellycam_recording/recording_upgrade/results/python_integration"
FLASH = REPO / "research/usb_cameras/results/windows/Gerald/timing/flash_run1_repositioned/capture"
FLASH_KEYS = {"c930e_720p_flash": "vid_046d_pid_0843_mi_00_8_39dec205_0_0000",
              "c922_720p_flash": "vid_046d_pid_085c_mi_00_8_268da596_0_0000"}


def load_set(name: str):
    files = sorted((CORPUS / name).glob("frame_*.jpg"))
    frames = [f.read_bytes() for f in files]
    if name in FLASH_KEYS:
        rows = [json.loads(l) for l in (FLASH / f"{FLASH_KEYS[name]}.frames.jsonl").read_text().splitlines()]
        assert len(rows) == len(frames) and all(r["payload_bytes"] == len(b) for r, b in zip(rows, frames))
        ts = [int(r["host_arrival_ns"]) for r in rows]
        src = "real: MF host_arrival_ns (QPC) from frames.jsonl"
    else:
        fps = int(json.loads((CORPUS / "index.json").read_text())[name]["nominal_fps"])
        base = 10_000_000_000_000
        ts = [base + round(i * 1e9 / fps) + ((i * 7919) % 4001 - 2000) * 1000 for i in range(len(frames))]
        src = f"synthetic: {fps} fps lattice +-2 ms deterministic jitter"
    return frames, ts, src


def check(stem: Path, frames, ts, fns, writer_tb: Fraction):
    man = json.loads(stem.with_name(stem.name + ".recording.json").read_text())
    video = stem.with_name(man["video"])
    side = rw.read_sidecar(stem.with_name(man["sidecar"]))
    pk = list(rw.RecordingReader(video).packets())
    res = {"container_time_base": man["time_base"], "packets": len(pk), "sidecar_records": int(len(side.records)),
           "bytes_exact": len(pk) == len(frames) and all(b == f for (_, b, _, _), f in zip(pk, frames)),
           "sidecar_crc_ok": side.bad_crc_records == 0 and side.torn_tail_bytes == 0,
           "sidecar_ts_exact": bool(np.array_equal(side.records["timestamp_ns"], np.array(ts, dtype=np.int64))),
           "sidecar_fn_exact": bool(np.array_equal(side.records["frame_number"], np.array(fns, dtype=np.int64))),
           "container_pts_eq_sidecar": len(pk) == len(side.records) and all(
               p[2] == int(r["pts"]) for p, r in zip(pk, side.records)),
           "pts_adjusted_frames": int(np.count_nonzero(side.records["flags"] & rw.FLAG_PTS_ADJUSTED)),
           "frame_gap_flags": int(np.count_nonzero(side.records["flags"] & rw.FLAG_FRAME_GAP))}
    tb = Fraction(man["time_base"])
    t0 = ts[0]
    errs = []
    for (_, _, pts, _), t, r in zip(pk, ts, side.records):
        if r["flags"] & rw.FLAG_PTS_ADJUSTED or man.get("pts_mode") == "index":
            continue
        errs.append(abs(float(pts * tb) - (t - t0) / 1e9))
    res["max_abs_pts_error_s_unadjusted"] = max(errs) if errs else None
    res["half_tick_s"] = float(tb / 2)
    res["pts_within_half_tick"] = all(e <= float(tb / 2) + 1e-12 for e in errs)
    # decode checks
    with av.open(str(video)) as c:
        n_av = sum(1 for f in c.decode(video=0) if not f.is_corrupt)
    res["pyav_decoded"] = n_av
    cap = cv2.VideoCapture(str(video), cv2.CAP_FFMPEG)
    res["cv2_ffmpeg_opened"] = cap.isOpened()
    res["cv2_frame_count_prop"] = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    res["cv2_fps_prop"] = round(cap.get(cv2.CAP_PROP_FPS), 4)
    fcc = int(cap.get(cv2.CAP_PROP_FOURCC))
    res["cv2_fourcc"] = "".join(chr((fcc >> 8 * i) & 0xFF) for i in range(4))
    n_cv = 0
    while True:
        ok, _ = cap.read()
        if not ok:
            break
        n_cv += 1
    cap.release()
    res["cv2_read_frames"] = n_cv
    res["video_bytes"] = video.stat().st_size
    res["payload_bytes"] = sum(len(f) for f in frames)
    res["container_overhead_bytes_per_frame"] = round((res["video_bytes"] - res["payload_bytes"]) / len(frames), 1)
    return res


def main():
    index = json.loads((CORPUS / "index.json").read_text())
    if MEDIA.exists():
        shutil.rmtree(MEDIA)
    MEDIA.mkdir(parents=True)
    out = {"pyav": av.__version__, "libavformat": av.library_versions["libavformat"], "opencv": cv2.__version__,
           "rows": []}
    for name, meta in index.items():
        if meta["kind"] != "mjpeg":
            continue
        frames, ts, src = load_set(name)
        fns = list(range(1000, 1000 + len(frames)))
        for cont, mode in [(c, "real") for c in rw.CONTAINERS] + [("mkv", "index"), ("avi", "index")]:
            stem = MEDIA / f"{name}.{cont}.{mode}"
            w = rw.RecordingWriter(stem, meta["width"], meta["height"], container=cont,
                                   nominal_fps=int(meta["nominal_fps"]), pts_mode=mode)
            for f, fn, t in zip(frames, fns, ts):
                w.write(f, fn, t)
            w.close()
            row = {"set": name, "container": cont, "pts_mode": mode, "frames_in": len(frames), "timestamps": src,
                   **check(stem, frames, ts, fns, w.tb)}
            out["rows"].append(row)
            print(name, cont, {k: row[k] for k in ("packets", "bytes_exact", "container_pts_eq_sidecar",
                                                     "pts_within_half_tick", "pts_adjusted_frames",
                                                     "pyav_decoded", "cv2_read_frames", "cv2_frame_count_prop")})
    # frame-gap case: drop frame numbers 1010..1012 (frames still contiguous in the file)
    frames, ts, src = load_set("c922_720p_flash")
    frames, ts = frames[:60], ts[:60]
    fns = [1000 + i + (3 if i >= 10 else 0) for i in range(60)]
    stem = MEDIA / "gap_test.mkv"
    w = rw.RecordingWriter(stem, 1280, 720, container="mkv")
    for f, fn, t in zip(frames, fns, ts):
        w.write(f, fn, t)
    w.close()
    side = rw.read_sidecar(stem.with_name(stem.name + ".frames.bin"))
    out["gap_test"] = {"frames": 60, "gap_flagged_at": np.nonzero(side.records["flags"] & rw.FLAG_FRAME_GAP)[0].tolist(),
                       "expected": [10]}
    print("gap test", out["gap_test"])
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "roundtrip.json").write_text(json.dumps(out, indent=1, default=str))
    cols = ["set", "container", "pts_mode", "frames_in", "container_time_base", "packets", "bytes_exact", "sidecar_ts_exact",
            "container_pts_eq_sidecar", "pts_within_half_tick", "pts_adjusted_frames", "pyav_decoded",
            "cv2_read_frames", "cv2_frame_count_prop", "cv2_fps_prop", "cv2_fourcc",
            "container_overhead_bytes_per_frame"]
    md = ["# Round trip: RecordingWriter -> RecordingReader (functional, no timing)", "",
          f"PyAV {out['pyav']} (libavformat {out['libavformat']}), OpenCV {out['opencv']}. "
          "Script: `scripts/python_integration/test_roundtrip.py`. Timestamps: flash sets = real MF host arrival "
          "(QPC ns); other sets = synthetic lattice (see script).", "",
          "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in out["rows"]:
        md.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    md += ["", f"Frame-gap flag test: flagged at {out['gap_test']['gap_flagged_at']} (expected {out['gap_test']['expected']})."]
    (RESULTS / "roundtrip.md").write_text("\n".join(md) + "\n")


if __name__ == "__main__":
    main()
