# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy", "opencv-python==4.12.0.88", "psutil"]
# ///
"""Run the repo's write_throughput functional_tests.py main() under PyAV 19.0.2 (args passed through)."""
import runpy, sys
SCR = "C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/write_throughput/functional_tests.py"
sys.argv = [SCR] + sys.argv[1:]
if __name__ == "__main__":
    runpy.run_path(SCR, run_name="__main__")
