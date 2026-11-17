# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "soundfile==0.13.1"]
# ///
"""Per killed file (short + long): acked samples, decoded samples (PyAV), lost = acked - decoded, CSV rows cover,
CSV lead = cover - decoded, CSV footer present (fit / end), torn CSV bytes.
Usage: uv run --script .../opus_crash/loss.py      Output: results/audio_single_file/opus_crash/loss.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crash_common as K  # noqa: E402
import seek_crash as S  # noqa: E402


def main():
    out = []
    for s in ("short", "long"):
        for f in json.load(open(os.path.join(K.RESULTS, f"make_crash_{s}.json")))["files"]:
            p = os.path.join(K.SCRATCH, s, f["file"])
            info, _ = K.O.decode_all(p)
            cv = S.csv_cover(p + ".csv")
            out.append(dict(file=f["file"], set=s, writer=f["writer"], kill_s=f["kill_s"], acked=f["acked_samples"], decoded=info["samples"],
                            lost=f["acked_samples"] - info["samples"], csv=cv, csv_lead=cv["cover"] - info["samples"]))
            print(out[-1], flush=True)
    json.dump(out, open(os.path.join(K.RESULTS, "loss.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
