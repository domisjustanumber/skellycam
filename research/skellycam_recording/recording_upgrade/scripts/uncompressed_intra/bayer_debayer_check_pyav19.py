# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "opencv-python==5.0.0.93"]
# ///
"""Re-run bayer_debayer_check.py (functional, no timing) under PyAV 19.0.2 + OpenCV 5.0.0.93.
Writes results/uncompressed_intra/bayer_debayer_check_pyav19.0.2.json and leaves the PyAV 18 file untouched.
Run from repo root:
  uv run --script research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/bayer_debayer_check_pyav19.py
"""
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bayer_debayer_check as b  # noqa: E402

final = b.RESULTS / "bayer_debayer_check_pyav19.0.2.json"
with tempfile.TemporaryDirectory() as td:
    b.RESULTS = Path(td)
    b.main()
    final.write_text((Path(td) / "bayer_debayer_check.json").read_text())
print("copied to", final)
