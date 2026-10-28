"""Write the codec inputs both languages read (so C++ and Python decode / encode byte-identical data).

  .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\cpp\\make_inputs.py <inputs_dir>

For 720p and 1080p and seeds 0-4 (one per camera):
  <size>_seed<s>_<i>.jpg  i = 0..29 : bench_common.synthetic_frames(h, w, n=30, seed=s, noise=8) encoded with cv2.imencode q90
                                    (identical recipe to prototypes/p1_write_variants.py L137-138 and baseline/bench_g_decode_ref.py L25-26)
  <size>_seed<s>.raw                : bench_common.synthetic_frames(h, w, n=60, seed=s) as 60 contiguous BGR frames
                                    (identical recipe to baseline/bench_c_record.py L44, the VideoRecorder benchmark)
Writes <inputs_dir>/inputs_manifest.json with every file's size.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "baseline"))
import bench_common as bc  # noqa: E402


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    man = {"opencv_used_to_encode": cv2.__version__, "files": {}}
    for size, (h, w) in bc.SIZES.items():
        for s in range(5):
            frames = bc.synthetic_frames(h, w, n=30, seed=s, noise=8)
            for i, f in enumerate(frames):
                ok, enc = cv2.imencode(".jpg", f, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                p = out / f"{size}_seed{s}_{i}.jpg"
                enc.tofile(p)
                man["files"][p.name] = p.stat().st_size
            raw = bc.synthetic_frames(h, w, n=60, seed=s)
            p = out / f"{size}_seed{s}.raw"
            np.ascontiguousarray(raw).tofile(p)
            man["files"][p.name] = p.stat().st_size
            print(size, s, flush=True)
    man["total_bytes"] = sum(man["files"].values())
    (out / "inputs_manifest.json").write_text(json.dumps(man, indent=1))
    print("total bytes", man["total_bytes"])


if __name__ == "__main__":
    main()
