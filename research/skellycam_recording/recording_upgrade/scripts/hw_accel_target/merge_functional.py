# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""Merge a subset re-run (functional_pyav19_<tag>.json) into functional_pyav19.json and rewrite the .md.

Records of the encoders present in the subset replace those in the main file; d3d12_adapter / decode lists from
the subset replace the main ones when present. Used because the first full run wrote d3d12va outputs to MKV,
whose header write fails in FFmpeg 9.0.2 (known from results/gpu_encode/ff_functional.md); the re-run uses MP4.
  uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/merge_functional.py d3d12
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pyav19_functional as pf  # noqa: E402

tag = sys.argv[1]
append = len(sys.argv) > 2 and sys.argv[2] == "--append"  # add records instead of replacing per encoder
main = json.loads((pf.RESULTS / "functional_pyav19.json").read_text(encoding="utf-8"))
sub = json.loads((pf.RESULTS / f"functional_pyav19_{tag}.json").read_text(encoding="utf-8"))
names = set() if append else {r["encoder"] for r in sub["encode"]}
first_superseded = [r for r in main["encode"] if r["encoder"] in names]
main.setdefault("superseded_records", []).extend(
    {"encoder": r["encoder"], "tag": r.get("tag"), "container": r.get("container"), "ok": r.get("ok"),
     "error": r.get("error"), "log": r.get("log", [])[:6], "superseded_by": f"functional_pyav19_{tag}.json"}
    for r in first_superseded)
out, inserted = [], False
for r in main["encode"]:
    if r["encoder"] in names:
        if not inserted:
            out += sub["encode"]
            inserted = True
        continue
    out.append(r)
if not inserted:
    out += sub["encode"]  # append mode lands here
main["encode"] = out
for k in ("d3d12_adapter", "decode"):
    if sub.get(k):
        main[k] = sub[k]
for n, v in ({} if append else sub.get("nvidia_smi_per_encoder", {})).items():
    main["nvidia_smi_per_encoder"][n] = v
main.setdefault("merged_runs", []).append({"tag": tag, "utc": sub["utc"], "append": append,
                                           "encoders": sorted({r["encoder"] for r in sub["encode"]})})
(pf.RESULTS / "functional_pyav19.json").write_text(json.dumps(main, indent=1, default=str), encoding="utf-8")
pf.write_md(main)
print("merged", sorted(names))
