# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""Can the running PyAV decode FFV1 v4 (experimental) files written by the ffmpeg 9.0.2 CLI?
Writes a 5-frame 320x240 random 12-bit bayer_rggb16le and gray16le clip with
`ffmpeg -c:v ffv1 -level 4 -strict experimental -g 1` (and a level 3 gray16le control), then decodes each with PyAV
and compares bytes. No timing.

  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/ffv1_v4_cross_version.py
  uv run --script research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/ffv1_v4_cross_version.py
Writes results/uncompressed_intra/ffv1_v4_cross_version_pyav<ver>.json
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import av
import numpy as np

RES = Path(__file__).resolve().parents[2] / "results" / "uncompressed_intra"
TMP = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/uncompressed_intra/cross_version")


def main() -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    raw = np.random.default_rng(0).integers(0, 4096, (5, 240, 320), dtype="<u2")
    rp = TMP / "rand12.raw"
    raw.tofile(rp)
    out = {"pyav": av.__version__, "pyav_ffmpeg": getattr(av, "ffmpeg_version_info", "?"),
           "writer": subprocess.run(["ffmpeg", "-hide_banner", "-version"], capture_output=True, text=True).stdout.splitlines()[0],
           "cases": {}}
    for name, pix, lvl in (("v4_bayer16", "bayer_rggb16le", "4"), ("v4_gray16", "gray16le", "4"), ("v3_gray16", "gray16le", "3")):
        f = TMP / f"{name}.mkv"
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", pix, "-s", "320x240",
               "-i", str(rp), "-c:v", "ffv1", "-level", lvl, "-g", "1"] + (["-strict", "experimental"] if lvl == "4" else []) + [str(f)]
        e = subprocess.run(cmd, capture_output=True, text=True)
        r = {"cmd": " ".join(cmd), "encode_rc": e.returncode}
        try:
            with av.open(str(f)) as c:
                frs = list(c.decode(video=0))
            r["decoded_frames"] = len(frs)
            r["decoded_pix_fmt"] = frs[0].format.name
            a = np.frombuffer(memoryview(frs[0].planes[0]), np.uint8).reshape(240, -1)[:, :640].copy().view("<u2")
            r["frame0_bit_exact"] = bool(np.array_equal(a, raw[0]))
        except Exception as ex:  # noqa: BLE001
            r["decode_error"] = f"{type(ex).__name__}: {ex}"
        out["cases"][name] = r
        f.unlink(missing_ok=True)
        print(name, json.dumps(r)[:200])
    rp.unlink()
    p = RES / f"ffv1_v4_cross_version_pyav{av.__version__}.json"
    p.write_text(json.dumps(out, indent=1))
    print("wrote", p)


if __name__ == "__main__":
    main()
