"""Build R/cv2_compat_table.md from the cv2_read_probe JSON files (OpenCV 4.12 venv vs 5.0.0.93 uv).

  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/python_integration/summarize_cv2_probe.py
"""
import json
from pathlib import Path

R = Path(__file__).resolve().parents[2] / "results/python_integration"
TAGS = ["cv2_4.12_venv", "cv2_5.0.0.93_uv"]


def cell(x):
    if not x.get("opened"):
        return f"not opened {x.get('error', '')}".strip()
    s = f"{x.get('backend')}; count {x.get('frame_count_prop'):g}; fps {x.get('fps_prop')}; read {x.get('frames_read')}"
    if x.get("sequence_exact") is not None:
        s += f"; seq {'ok' if x['sequence_exact'] else 'BAD'}; seek {'ok' if x.get('seek_all_exact') else 'BAD'}"
    return s


def main():
    data = {t: json.loads((R / f"cv2_read_probe_{t}.json").read_text()) for t in TAGS if (R / f"cv2_read_probe_{t}.json").exists()}
    tags = list(data)
    lines = [f"Versions: " + "; ".join(f"{t}: OpenCV {d['opencv']}, numpy {d['numpy']}" for t, d in data.items()), "",
             "| clip | " + " | ".join(f"{t} CAP_ANY" for t in tags) + " | " + " | ".join(f"{t} CAP_FFMPEG" for t in tags) + " |",
             "|---|" + "---|" * (2 * len(tags))]
    names = list(data[tags[0]]["clips"])
    for n in names:
        row = [n] + [cell(data[t]["clips"].get(n, {}).get("CAP_ANY", {})) for t in tags] + \
              [cell(data[t]["clips"].get(n, {}).get("CAP_FFMPEG", {})) for t in tags]
        lines.append("| " + " | ".join(row) + " |")
    diffs = []
    if len(tags) == 2:
        for n in names:
            for api in ("CAP_ANY", "CAP_FFMPEG", "CAP_MSMF"):
                a, b = data[tags[0]]["clips"][n].get(api, {}), data[tags[1]]["clips"].get(n, {}).get(api, {})
                keys = ("opened", "frame_count_prop", "frames_read", "sequence_exact", "seek_results")
                if any(a.get(k) != b.get(k) for k in keys):
                    diffs.append(f"- {n} {api}: " + "; ".join(f"{k}: {a.get(k)} -> {b.get(k)}" for k in keys if a.get(k) != b.get(k)))
    lines += ["", "Differences 4.12 -> 5.0.0.93 (any API):", *(diffs or ["- none"])]
    (R / "cv2_compat_table.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
