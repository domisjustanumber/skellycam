# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""GF09: check the Chromium test media themselves (PyAV software decode of the 60-frame MKV/MP4 cuts, frames 0/1/7
against the .ref_f<k>.nv12 files). Functional only. Writes results/uncompressed_intra/gapfill/GF09_chromium_media_check.json"""
import json
from pathlib import Path
import av
import numpy as np
D = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/uncompressed_intra/gapfill/GF09/chromium")
OUT = Path(__file__).resolve().parents[4] / "results" / "uncompressed_intra" / "gapfill" / "GF09_chromium_media_check.json"
M = json.loads((D / "manifest.json").read_text())
w, h = M["w"], M["h"]
rows = []
for c in M["clips"]:
    for f in (c["mkv"]["file"], c["mp4"]["file"]):
        with av.open(str(D / f)) as ic:
            frames = [fr for fr in ic.decode(video=0)]
        r = {"file": f, "frames_decoded": len(frames), "pix_fmt": frames[0].format.name, "refs": {}}
        for k in M["ref_frames"]:
            ref = np.frombuffer((D / f"{c['id']}.ref_f{k}.nv12").read_bytes(), np.uint8)
            fr = frames[k]
            y = np.frombuffer(memoryview(fr.planes[0]), np.uint8).reshape(-1, fr.planes[0].line_size)[:h, :w]
            u = np.frombuffer(memoryview(fr.planes[1]), np.uint8).reshape(-1, fr.planes[1].line_size)[:h // 2, :w // 2]
            v = np.frombuffer(memoryview(fr.planes[2]), np.uint8).reshape(-1, fr.planes[2].line_size)[:h // 2, :w // 2]
            ry = ref[: w * h].reshape(h, w); ruv = ref[w * h:].reshape(h // 2, w)
            r["refs"][k] = all(np.array_equal(a, b) for a, b in ((y, ry), (u, ruv[:, 0::2]), (v, ruv[:, 1::2])))
        rows.append(r); print(r)
OUT.write_text(json.dumps({"av_version": av.__version__, "rows": rows}, indent=1))
