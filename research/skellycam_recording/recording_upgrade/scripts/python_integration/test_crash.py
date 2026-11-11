"""Functional crash-tolerance test for recwriter (G2). No timing is reported.

Part A - hard kill: a child process writes the c922_720p_flash frames (looped) through RecordingWriter, paced
roughly at 30 fps; the parent waits until the sidecar holds >= KILL_AT records, then TerminateProcess()es the
child (no close(), no finally). Then: what PyAV and cv2 can read, what the sidecar holds, and what recover()
(startup recovery + remux of the matched prefix) produces.

Part B - truncation: copies of a cleanly closed file cut at fixed fractions of its size and inside a frame,
read with PyAV (packets, decoded frames, first error) and cv2 CAP_FFMPEG (opened, FRAME_COUNT, frames read).

Run (repo root):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/python_integration/test_crash.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import av
import cv2

sys.path.insert(0, str(Path(__file__).parent))
import recwriter as rw  # noqa: E402

REPO = Path(__file__).resolve().parents[5]
CORPUS = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus")
MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/python_integration/crash")
RESULTS = REPO / "research/skellycam_recording/recording_upgrade/results/python_integration"
KILL_AT = 300
VARIANTS = [("mkv", "real"), ("mkv", "index"), ("mp4f", "real"), ("avi", "index")]

CHILD = r'''
import sys, time, pathlib
sys.path.insert(0, sys.argv[1])
import recwriter as rw
stem, cont, mode = sys.argv[2], sys.argv[3], sys.argv[4]
files = sorted(pathlib.Path(sys.argv[5]).glob("frame_*.jpg"))
frames = [f.read_bytes() for f in files]
w = rw.RecordingWriter(stem, 1280, 720, container=cont, pts_mode=mode)
t0 = time.perf_counter_ns()
i = 0
while True:  # loops the 893 frames; the parent kills us
    w.write(frames[i % len(frames)], i, time.perf_counter_ns())
    i += 1
    target = t0 + i * 33_333_333
    while time.perf_counter_ns() < target:
        time.sleep(0.001)
'''


def probe(video: Path, frames: list[bytes] | None = None) -> dict:
    out = {"bytes": video.stat().st_size if video.exists() else 0}
    if frames is not None:  # how many leading packets are byte-identical to what was written
        n_exact, last_partial = 0, None
        try:
            for i, b, _, _ in rw.RecordingReader(video).packets():
                if i < len(frames) and b == frames[i]:
                    n_exact += 1
                else:
                    last_partial = {"index": i, "bytes": len(b), "expected": len(frames[i]) if i < len(frames) else None}
                    break
        except Exception as e:  # noqa: BLE001
            last_partial = repr(e)[:120]
        out["exact_prefix_packets"], out["first_non_exact_packet"] = n_exact, last_partial
    try:
        with av.open(str(video)) as c:
            s = c.streams.video[0]
            n_pk = 0
            err = None
            try:
                for p in c.demux(s):
                    if p.size:
                        n_pk += 1
            except Exception as e:  # noqa: BLE001
                err = repr(e)[:160]
        out["pyav_packets"], out["pyav_demux_error"] = n_pk, err
    except Exception as e:  # noqa: BLE001
        out["pyav_packets"], out["pyav_demux_error"] = 0, repr(e)[:160]
    try:
        n_dec, n_corrupt, err = 0, 0, None
        with av.open(str(video)) as c:
            try:
                for f in c.decode(video=0):
                    n_dec += 1
                    n_corrupt += int(f.is_corrupt)
            except Exception as e:  # noqa: BLE001
                err = repr(e)[:160]
        out["pyav_decoded"], out["pyav_corrupt_flagged"], out["pyav_decode_error"] = n_dec, n_corrupt, err
    except Exception as e:  # noqa: BLE001
        out["pyav_decoded"], out["pyav_decode_error"] = 0, repr(e)[:160]
    cap = cv2.VideoCapture(str(video), cv2.CAP_FFMPEG)
    out["cv2_opened"] = cap.isOpened()
    out["cv2_frame_count_prop"] = cap.get(cv2.CAP_PROP_FRAME_COUNT) if cap.isOpened() else None
    n = 0
    while cap.isOpened():
        ok, _ = cap.read()
        if not ok:
            break
        n += 1
    cap.release()
    out["cv2_read_frames"] = n
    return out


def part_a() -> list[dict]:
    rows = []
    d = MEDIA / "kill"
    d.mkdir(parents=True, exist_ok=True)
    for cont, mode in VARIANTS:
        stem = d / f"killed.{cont}.{mode}"
        child = subprocess.Popen([sys.executable, "-c", CHILD, str(Path(__file__).parent), str(stem), cont, mode,
                                  str(CORPUS / "c922_720p_flash")])
        bin_path = stem.with_name(stem.name + ".frames.bin")
        deadline = time.time() + 120
        while time.time() < deadline:
            if bin_path.exists() and (bin_path.stat().st_size - rw.HEADER_SIZE) // rw.RECORD_SIZE >= KILL_AT:
                break
            time.sleep(0.05)
        child.kill()  # TerminateProcess on Windows: no close(), no flush, no finally
        child.wait()
        man = json.loads(stem.with_name(stem.name + ".recording.json").read_text())
        side = rw.read_sidecar(bin_path)
        video = stem.with_name(man["video"])
        row = {"container": cont, "pts_mode": mode, "exit_code": child.returncode, "manifest_state": man["state"],
               "sidecar_valid_records": int(len(side.records)), "sidecar_torn_tail_bytes": side.torn_tail_bytes,
               **{f"killed_{k}": v for k, v in probe(video).items()}}
        row["find_unfinished_lists_it"] = stem in rw.find_unfinished(d)
        rep = rw.recover(stem)
        row.update({f"recover_{k}": v for k, v in rep.items() if k not in ("stem",)})
        if rep.get("recovered_file"):
            row.update({f"recovered_{k}": v for k, v in probe(stem.with_name(rep["recovered_file"])).items()})
        rows.append(row)
        print("A", cont, mode, {k: row[k] for k in row if k.startswith(("sidecar", "killed_pyav_packets",
                                                                          "killed_cv2", "recover_matched",
                                                                          "recovered_cv2"))})
    return rows


def part_b() -> list[dict]:
    rows = []
    d = MEDIA / "truncate"
    d.mkdir(parents=True, exist_ok=True)
    frames = [f.read_bytes() for f in sorted((CORPUS / "c922_720p_flash").glob("frame_*.jpg"))][:300]
    for cont, mode in VARIANTS:
        stem = d / f"clean.{cont}.{mode}"
        w = rw.RecordingWriter(stem, 1280, 720, container=cont, pts_mode=mode)
        for i, f in enumerate(frames):
            w.write(f, i, 10_000_000_000 + i * 33_333_333)
        w.close()
        src = stem.with_name(stem.name + "." + rw.CONTAINERS[cont][1])
        size = src.stat().st_size
        cuts = {"50%": size // 2, "90%": size * 9 // 10, "99.9%": size * 999 // 1000, "minus_1_byte": size - 1}
        for label, n in cuts.items():
            dst = d / f"cut_{label.replace('%', 'pct')}.{cont}.{mode}{src.suffix}"
            with open(src, "rb") as fi, open(dst, "wb") as fo:
                fo.write(fi.read(n))
            row = {"container": cont, "pts_mode": mode, "cut": label, "kept_bytes": n, "full_bytes": size,
                   **probe(dst, frames)}
            rows.append(row)
            print("B", cont, mode, label, {k: row[k] for k in ("pyav_packets", "pyav_decoded", "cv2_opened",
                                                              "cv2_frame_count_prop", "cv2_read_frames")})
    return rows


def main():
    if MEDIA.exists():
        shutil.rmtree(MEDIA)
    a = part_a()
    b = part_b()
    out = {"pyav": av.__version__, "opencv": cv2.__version__, "kill_at_sidecar_records": KILL_AT,
           "part_a_kill": a, "part_b_truncate": b}
    (RESULTS / "crash.json").write_text(json.dumps(out, indent=1, default=str))
    ca = ["container", "pts_mode", "sidecar_valid_records", "sidecar_torn_tail_bytes", "killed_pyav_packets",
          "killed_pyav_decoded", "killed_cv2_opened", "killed_cv2_frame_count_prop", "killed_cv2_read_frames",
          "find_unfinished_lists_it", "recover_matched_prefix", "recovered_cv2_frame_count_prop",
          "recovered_cv2_read_frames", "recover_first_mismatch", "killed_pyav_demux_error"]
    cb = ["container", "pts_mode", "cut", "exact_prefix_packets", "first_non_exact_packet", "pyav_packets", "pyav_decoded", "pyav_corrupt_flagged", "cv2_opened",
          "cv2_frame_count_prop", "cv2_read_frames", "pyav_demux_error", "pyav_decode_error"]
    md = ["# Crash tolerance of recwriter files (functional, no timing)", "",
          f"PyAV {av.__version__}, OpenCV {cv2.__version__}. Script `scripts/python_integration/test_crash.py`.", "",
          f"## A. Writer process killed (TerminateProcess) after the sidecar held >= {KILL_AT} records", "",
          "| " + " | ".join(ca) + " |", "|" + "---|" * len(ca)]
    md += ["| " + " | ".join(str(r.get(c)) for c in ca) + " |" for r in a]
    md += ["", "## B. Cleanly closed 300-frame file truncated", "", "| " + " | ".join(cb) + " |", "|" + "---|" * len(cb)]
    md += ["| " + " | ".join(str(r.get(c)) for c in cb) + " |" for r in b]
    (RESULTS / "crash.md").write_text("\n".join(md) + "\n")


if __name__ == "__main__":
    main()
