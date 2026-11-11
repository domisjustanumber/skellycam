"""Extract the MediaPipe body (33-point) tracked points + connections from skellytracker at the commit
FreeMoCap pins (freemocap/uv.lock: skellytracker main#6f78af48...), into mediapipe_body_schema.json.

Run (from repo root; needs the sibling skellytracker checkout, read only):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/extract_schema.py
"""
import json, subprocess
from pathlib import Path

COMMIT = "6f78af48b7a3c1809d110120a7cbd1d7f6120392"
PATH = "skellytracker/core/detectors/keypoint_detectors/mediapipe/body/mediapipe_body.yaml"
REPO = Path(__file__).resolve().parents[6] / "skellytracker"

txt = subprocess.run(["git", "-C", str(REPO), "show", f"{COMMIT}:{PATH}"], capture_output=True, text=True, check=True).stdout
points, conns, sec = [], [], None
for line in txt.splitlines():
    s = line.strip()
    if s.startswith("tracked_points:"):
        sec = "p"; continue
    if s.startswith("connections:"):
        sec = "c"; continue
    if s and not s.startswith("-") and not s.startswith("#") and s.endswith(":"):
        sec = None
    if sec == "p" and s.startswith("- "):
        points.append(s[2:].strip())
    elif sec == "c" and s.startswith("- ["):
        a, b = [x.strip() for x in s[3:-1].split(",")]
        conns.append([a, b])
out = {"source": f"skellytracker@{COMMIT}:{PATH}", "tracked_points": points, "connections": conns}
Path(__file__).with_name("mediapipe_body_schema.json").write_text(json.dumps(out, indent=1))
print(len(points), "points", len(conns), "connections")
