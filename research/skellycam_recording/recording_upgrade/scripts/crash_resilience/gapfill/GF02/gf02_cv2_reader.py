"""GF02 reader (functional, no timing): OpenCV 4.12 CAP_FFMPEG and FreeMoCap's real VideoHelper on GF02 files.
Runs in the skellycam .venv READ-ONLY, like scripts/jpeg_passthrough/verify_method_reader.py (imports jp_io from there).

Reference hashes: cv2.VideoCapture(<corpus set>/frame_%06d.jpg, CAP_FFMPEG) sequential decode (FFmpeg image2 demuxer +
the same mjpeg decoder cv2 uses for the containers), sha1 of the BGR array as jp_io._fh does. Frame k of a file is
expected to equal reference[input index of k].

Job fields: path, set, idx (input index per written frame) or loop (n frames = set looped), targets (POS_FRAMES seek
targets, frame indices of the written sequence), seq (sequential read + identity), fmc (FreeMoCap read), tag,
delete_after (delete the file after reading; used for the 54,000-frame files).

usage: .venv/Scripts/python.exe gf02_cv2_reader.py <jobs.json> <out.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RU = Path("C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade")
sys.path.insert(0, str(RU / "scripts/jpeg_passthrough"))
import jp_common as C  # noqa: E402
import jp_io as io  # noqa: E402

_REF: dict[str, list[str]] = {}


def ref_hashes(setname: str) -> list[str]:
    import cv2
    if setname not in _REF:
        cap = cv2.VideoCapture(str(C.CORPUS / setname / "frame_%06d.jpg"), cv2.CAP_FFMPEG)
        h = []
        while True:
            ok, fr = cap.read()
            if not ok or fr is None:
                break
            h.append(io._fh(fr))
        cap.release()
        _REF[setname] = h
    return _REF[setname]


def read_job(job: dict) -> dict:
    import cv2
    p = Path(job["path"])
    ref = ref_hashes(job["set"])
    if "idx" in job:
        exp = [ref[k] for k in job["idx"]]
    else:
        exp = [ref[k % len(ref)] for k in range(job["loop"])]
    n = len(exp)
    r = {"tag": job["tag"], "n_written": n, "exists": p.exists()}
    if not p.exists():
        return r
    cap = cv2.VideoCapture(str(p), cv2.CAP_FFMPEG)
    r["opened"] = bool(cap.isOpened())
    if not r["opened"]:
        return r
    r["frame_count_prop"] = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    r["fps_prop"] = cap.get(cv2.CAP_PROP_FPS)
    g = 0
    while cap.grab():
        g += 1
    cap.release()
    r["grab_count"] = g
    seq = None
    if job.get("seq"):
        cap = cv2.VideoCapture(str(p), cv2.CAP_FFMPEG)
        seq = []
        while True:
            ok, fr = cap.read()
            if not ok or fr is None:
                break
            seq.append(io._fh(fr))
        cap.release()
        r["read_count"] = len(seq)
        r["seq_matches_input"] = sum(1 for a, b in zip(seq, exp) if a == b)
    sk = []
    cap = cv2.VideoCapture(str(p), cv2.CAP_FFMPEG)
    for t in job.get("targets", []):
        okset = cap.set(cv2.CAP_PROP_POS_FRAMES, t)
        ok, fr = cap.read()
        h = io._fh(fr) if ok and fr is not None else None
        row = {"k": t, "set_ok": bool(okset), "read_ok": bool(ok), "match_input": h is not None and t < n and h == exp[t]}
        if seq is not None:
            row["match_seq"] = h is not None and t < len(seq) and h == seq[t]
            row["got_seq_index"] = seq.index(h) if h in seq else -1
        if not row["match_input"] and h is not None:
            near = [j for j in range(max(0, t - 70), min(n, t + 70)) if exp[j] == h]
            row["got_input_index_near"] = near[:3]
        sk.append(row)
    cap.release()
    r["seek"] = sk
    r["seek_exact_input"] = sum(1 for s in sk if s["match_input"])
    if seq is not None:
        r["seek_exact_seq"] = sum(1 for s in sk if s.get("match_seq"))
    r["seek_total"] = len(sk)
    if job.get("fmc"):
        fm = io.freemocap_read(p, exp)
        r["freemocap"] = {"frame_count": fm.get("frame_count"), "fps": fm.get("fps"), "error": fm.get("error"),
                          "reads": [{k: x.get(k) for k in ("k", "ok", "match_cv2_sequential", "error")}
                                    for x in fm.get("reads", [])]}
        reads = r["freemocap"]["reads"]
        r["freemocap_ok"] = (fm.get("error") is None and len(reads) == 4
                             and all(x.get("ok") and x.get("match_cv2_sequential") for x in reads)
                             and fm.get("frame_count") == n)
    if job.get("delete_after"):
        try:
            p.unlink()
            r["deleted_after_read"] = True
        except OSError as e:
            r["deleted_after_read"] = repr(e)
    return r


def main() -> None:
    import cv2
    jobs = json.loads(Path(sys.argv[1]).read_text())
    out = {"opencv": cv2.__version__, "python": sys.version.split()[0], "note": "functional only; no timing",
           "results": []}
    for job in jobs:
        r = read_job(job)
        out["results"].append(r)
        print(r["tag"], {k: r.get(k) for k in ("frame_count_prop", "fps_prop", "grab_count", "read_count",
                                                "seq_matches_input", "seek_exact_input", "freemocap_ok")}, flush=True)
    out["reference_counts"] = {k: len(v) for k, v in _REF.items()}
    Path(sys.argv[2]).write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
