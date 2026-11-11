"""Functional test of overlay storage formats (G3): size, round trip, truncation tolerance.

No timing is measured here (sizes and correctness are deterministic).

For each overlay kind (text = today's stamp only; skeleton = stamp + 33-pt skeleton; charuco = stamp + 100-corner
board with labels; all) and each format, write N frames, then:
  * bytes on disk -> bytes/frame and bytes/hour at 30 fps (extrapolated linearly from N frames)
  * round trip: parse back and compare with the generated data (data-level formats)
  * truncation: cut the file at 25 offsets; count recovered frames vs complete records before the cut
Outputs (synthetic sidecars, no imagery) go to  <raw>/overlays/formats/ ; results JSON + MD to results/overlays/.

Run from repo root:
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/formats_functional.py [--frames 300]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import overlay_model as M  # noqa: E402

RAW = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/overlays/formats")
RES = HERE.parents[1] / "results" / "overlays"


def record_ends(fmt: str, path: Path) -> list[int]:
    """Byte offset at which each frame record ends (to know how many complete records precede a cut)."""
    data = path.read_bytes()
    ends = []
    if fmt in ("jsonl",):
        pos = data.index(b"\n") + 1  # header line
        while True:
            j = data.find(b"\n", pos)
            if j < 0:
                break
            ends.append(j + 1)  # line incl. newline
            pos = j + 1
    elif fmt == "msgpack":
        import struct
        pos = 0
        first = True
        while pos + 4 <= len(data):
            (n,) = struct.unpack_from("<I", data, pos)
            pos += 4 + n
            if first:
                first = False
                continue
            ends.append(pos)
    elif fmt == "bin":
        import struct
        (hl,) = struct.unpack_from("<I", data, 6)
        pos = 10 + hl
        while pos + 8 <= len(data):
            (n,) = struct.unpack_from("<I", data, pos + 4)
            pos += 8 + n + 4
            ends.append(pos)
    elif fmt == "vtt":
        pos = data.index(b"\n\n") + 2
        while True:
            j = data.find(b"\n\n", pos)
            if j < 0:
                break
            ends.append(j + 2)
            pos = j + 2
    return ends


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=300)
    a = ap.parse_args()
    n = a.frames
    RAW.mkdir(parents=True, exist_ok=True)
    RES.mkdir(parents=True, exist_ok=True)
    rows = []
    for (w, h) in ((1280, 720), (1920, 1080)):
        for kind in ("text", "skeleton", "charuco", "all"):
            frames = M.make_frames(n, w, h, kind)
            hdr = M.header(w, h, 30.0, kind)
            for fmt, (W, R) in M.DATA_FORMATS.items():
                p = RAW / f"{kind}_{h}p{W.ext}"
                wr = W(p, hdr)
                for fd in frames:
                    wr.write(fd)
                wr.close()
                data = p.read_bytes()
                _, got, bad = R(data)
                tol = 1e-3 if fmt == "bin" else 0.0  # bin stores float32
                # VTT/JSON store the 2-decimal values exactly; bin stores float32
                rt = len(got) == n and bad == 0 and all(M.frames_equal(x, y, tol) for x, y in zip(frames, got))
                ends = record_ends(fmt, p)
                assert len(ends) == n, (fmt, len(ends))
                cuts = sorted({int(len(data) * k / 26) for k in range(1, 26)} | {ends[n // 2] - 1, ends[n // 2], ends[n // 2] + 1})
                trunc_ok, trunc_err, plus_one = 0, [], 0
                for c in cuts:
                    expect = sum(1 for e in ends if e <= c)
                    try:
                        _, g2, _ = R(data[:c])
                        # ok = every complete record recovered, and nothing corrupt returned (a record cut
                        # exactly before its terminating newline may legitimately parse as complete: expect+1)
                        ok = len(g2) in (expect, expect + 1) and all(M.frames_equal(x, y, tol) for x, y in zip(frames, g2))
                        if len(g2) == expect + 1:
                            plus_one += 1
                    except Exception as e:  # noqa: BLE001
                        ok = False
                        trunc_err.append(f"cut {c}: {type(e).__name__}: {e}"[:160])
                    trunc_ok += ok
                rows.append({"res": f"{w}x{h}", "kind": kind, "format": fmt, "frames": n, "bytes": len(data),
                             "bytes_per_frame": round(len(data) / n, 1), "MB_per_hour_30fps": round(len(data) / n * 30 * 3600 / 1e6, 1),
                             "round_trip_exact": rt, "trunc_cuts": len(cuts), "trunc_recovered_all_complete": trunc_ok,
                             "trunc_errors": trunc_err[:3], "trunc_cuts_with_extra_record_before_newline": plus_one})
            for fmt, W in M.RENDER_FORMATS.items():
                p = RAW / f"{kind}_{h}p{W.ext}"
                if p.is_dir():
                    shutil.rmtree(p)
                wr = W(p, hdr)
                for fd in frames:
                    wr.write(fd)
                wr.close()
                if p.is_dir():
                    files = sorted(p.glob("frame_*.svg"))
                    size = sum(f.stat().st_size for f in files)
                    extra = {"files": len(files)}
                    # each file must parse strictly
                    import xml.etree.ElementTree as ET
                    okp = sum(1 for f in files if ET.fromstring(f.read_bytes()) is not None)
                    extra["files_parse_strict"] = okp
                    data = None
                else:
                    data = p.read_bytes()
                    size = len(data)
                    extra = {}
                if fmt == "svg_single":
                    extra["strict_parse_groups"] = M.read_svg_single_strict(data)
                    cuts = [int(len(data) * k / 26) for k in range(1, 26)]
                    strict_fail = 0
                    lenient = []
                    for c in cuts:
                        try:
                            M.read_svg_single_strict(data[:c])
                        except Exception:  # noqa: BLE001
                            strict_fail += 1
                        lenient.append(len(M.read_svg_single_lenient(data[:c])))
                    extra["trunc_cuts"] = len(cuts)
                    extra["trunc_strict_parse_failures"] = strict_fail
                    extra["trunc_lenient_groups_recovered_min_max"] = [min(lenient), max(lenient)]
                rows.append({"res": f"{w}x{h}", "kind": kind, "format": fmt, "frames": n, "bytes": size,
                             "bytes_per_frame": round(size / n, 1), "MB_per_hour_30fps": round(size / n * 30 * 3600 / 1e6, 1), **extra})
            print(w, h, kind, "done")
    (RES / "formats_functional.json").write_text(json.dumps(rows, indent=1))
    md = ["| res | kind | format | bytes/frame | MB/hour @30fps | round trip | truncation: cuts fully recovered | notes |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if "round_trip_exact" in r:
            rt, tr = str(r["round_trip_exact"]), f'{r["trunc_recovered_all_complete"]}/{r["trunc_cuts"]}'
            note = "; ".join(r["trunc_errors"])
        else:
            rt, tr = "n/a", ""
            note = ""
            if "files" in r:
                note = f'{r["files"]} files, {r["files_parse_strict"]} parse'
            if "trunc_strict_parse_failures" in r:
                tr = f'strict XML parse fails {r["trunc_strict_parse_failures"]}/{r["trunc_cuts"]}'
                note = f'lenient regex recovers {r["trunc_lenient_groups_recovered_min_max"][0]}-{r["trunc_lenient_groups_recovered_min_max"][1]} groups'
        md.append(f'| {r["res"]} | {r["kind"]} | {r["format"]} | {r["bytes_per_frame"]} | {r["MB_per_hour_30fps"]} | {rt} | {tr} | {note} |')
    (RES / "formats_functional.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
