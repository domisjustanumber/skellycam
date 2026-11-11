# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""Extra decode check: FFmpeg's native 'av1' decoder (not libdav1d, which PyAV picks by default and which has no
hw configs) with HWAccel d3d11va / d3d12va / cuda / dxva2 (no software fallback) on the libsvtav1 test files.
Appends results to functional_pyav19.json under "decode_extra" and to functional_pyav19.md.
  uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/decode_av1_native.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pyav19_functional as pf  # noqa: E402

P = pf.RESULTS / "functional_pyav19.json"
d = json.loads(P.read_text(encoding="utf-8"))
out = []
for tag in ("yuy2_1080p_intra_sw", "yuy2_1080p_gop30_sw"):
    path = str(pf.OUT / f"libsvtav1__{tag}.mkv")
    for hw in (None, "d3d11va", "d3d12va", "cuda", "dxva2"):
        r = pf.run_child(dict(kind="file", path=path, decoder="av1", hw=hw, fallback=False, label=f"av1 {tag}"))
        out.append(r)
        print(tag, hw, r.get("ok"), r.get("out_formats"), r.get("decoder_has_hw_config_for_device"),
              r.get("psnr_y_vs_cpu_min"), (r.get("error") or "")[:120])
d["decode_extra"] = out
P.write_text(json.dumps(d, indent=1, default=str), encoding="utf-8")
L = ["", "## Extra: native `av1` decoder + HWAccel (libsvtav1 files)", "",
     "| file | hwaccel | decoder has hw config | ok | frames | output formats | PSNR Y vs CPU (min) | error |",
     "|---|---|---|---|---|---|---|---|"]
for r in out:
    L.append(f"| {r['label']} | {r.get('hw') or 'none (sw)'} | {r.get('decoder_has_hw_config_for_device', '')} | "
             f"{'yes' if r.get('ok') else 'NO'} | {r.get('frames', '')} | {r.get('out_formats', '')} | "
             f"{r.get('psnr_y_vs_cpu_min', '')} | {(r.get('error') or '').replace('|', '/')[:160]} |")
with open(pf.RESULTS / "functional_pyav19.md", "a", encoding="utf-8") as f:
    f.write("\n".join(L) + "\n")
