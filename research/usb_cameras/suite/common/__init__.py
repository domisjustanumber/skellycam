"""Shared, OS-neutral code for the skellycam UVC test suites (research/usb_cameras/suite).

Import it by putting the suite directory on sys.path first:

    import sys; from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # the suite/ directory
    from common import topology_model, results, procutil

Modules (see suite/README.md for the full contract):
    results         standard result JSON (new_result / finish_result / write_json / env_info / utc_stamp)
    procutil        run(argv, timeout_s) that kills the whole process tree on timeout and never raises
    jpegcheck       check_jpeg(bytes): SOI/EOI/SOF0/header SHA-1, lenient and strict decode
    identity        camera_key(): serial if present and unique, else port path (naming/camera_identity.py scheme)
    topology_model  USB bandwidth domains, prediction, failure classification, port suggestions, user message
    tsanalysis      timestamp grid / frame-index fit / device-clock fit / drop detection (stdlib only)
    imgmetrics      luma, R/B ratio, sharpness of a JPEG (needs Pillow + numpy)
    cycstats        open/close cycle statistics (success rate, Wilson CI, percentiles, recovery)
    rating          plan section 3 rating thresholds (yes / partial / no / untested)
    modescope       streaming-test mode scope (exactly 720 lines at >= 30 fps by default; --min-fps/--min-height/
                    --max-height/--all-modes)
    nograb          FMT-NOGRAB analysis: mode-set completeness vs the descriptors, stream disturbance, blocking

Everything except imgmetrics (and the optional strict JPEG decoders in jpegcheck) is standard library only,
so it runs on Windows, Linux and macOS with any Python >= 3.10.
"""

__all__ = ["results", "procutil", "jpegcheck", "identity", "topology_model", "tsanalysis", "imgmetrics",
           "cycstats", "rating"]
