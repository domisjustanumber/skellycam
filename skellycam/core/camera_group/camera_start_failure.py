"""Explain a failed camera start: what was requested, what happened, why, and what to try (port from sfn26).

The explanation is composed once, after the failure, from facts available then: the requested settings, the
failure object of each camera (specs/windows-capture.md section 12), a fresh camera detection (each camera's USB
connection, and requested cameras that are no longer detected) and, on Windows, the USB devices the system
reported surprise-removed during the start (Kernel-PnP event 1010, "surprise removed as it is reported as missing
on the bus"). It is given only where it adds a cause to the reasons of section 12: a USB reset, a camera that
sends no frames, or a camera that does not open. Other reasons (a rate check, no such mode) already say what to do.
"""
import logging
import platform
import subprocess
from collections.abc import Callable
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

NO_FRAMES_STAGES = {"start stream", "first frame", "warm-up"}
CANNOT_OPEN_STAGES = {"open"}


def usb_disconnects_since(start: datetime) -> int | None:
    """USB devices Windows reported surprise-removed since `start`; None where this is not available."""
    if platform.system() != "Windows":
        return None
    since = start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    query = f"*[System[(EventID=1010) and TimeCreated[@SystemTime>='{since}']]]"
    try:
        result = subprocess.run(["wevtutil", "qe", "Microsoft-Windows-Kernel-PnP/Device Management",
                                 f"/q:{query}", "/f:xml"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.count("<Event ") if result.returncode == 0 else None


def explain_start_failure(failures: dict, configs: dict, detected: list | None,
                          usb_disconnects: int | None) -> str | None:
    """`failures`: camera ID to the failure object of section 12. `detected`: CameraDeviceInfo from a detection
    after the failure (None if detection failed). None when no explanation adds a cause."""
    connections = {camera.camera_id: camera.usb_version for camera in detected or []}
    requested_ids = [camera_id for camera_id, config in configs.items() if config.use_this_camera]
    requested = []
    for camera_id in requested_ids:
        config = configs[camera_id]
        rate = f"{config.framerate:g} fps" if config.framerate > 0 else "the camera's default frame rate"
        connection = connections.get(camera_id) or "USB connection unknown"
        requested.append(f"{camera_id} ({connection}): {config.capture_fourcc} "
                         f"{config.resolution.width}×{config.resolution.height} at {rate}")
    # Camera IDs come from detection; when none of them match, they are not detection IDs (or every
    # camera vanished, which an empty detection shows).
    compare = detected is not None and (not detected or any(camera_id in connections for camera_id in requested_ids))
    missing = [camera_id for camera_id in requested_ids if compare and camera_id not in connections]
    stages = {failure["stage"] for failure in failures.values()}

    happened = [f"Camera {failure['camera_id']} failed during {failure['stage']}: {failure['reason']}".rstrip(". ")
                + "." for failure in failures.values()]
    if usb_disconnects:
        happened.append(f"Windows reported {usb_disconnects} USB device disconnection(s) during the start.")
    if missing:
        happened.append(f"Not detected after the failure: {', '.join(missing)}.")

    if usb_disconnects or missing:
        why = ("USB devices disconnecting while cameras start means the USB controller reset. That happens when "
               "the cameras together request more data than the USB connection can carry. The data each camera "
               "needs grows with resolution and frame rate, and a USB 2 connection carries far less than USB 3.")
        advice = ("Lower the frame rate or resolution, connect fewer cameras to the same USB controller, or move "
                  "cameras to ports on another USB controller. Detect cameras again before reconnecting.")
    elif stages & NO_FRAMES_STAGES:
        why = ("A camera that opens but sends no frames is usually in use by another program, or its USB "
               "connection cannot carry the requested resolution and frame rate.")
        advice = "Close other programs that use the camera. If none do, lower the frame rate or resolution."
    elif stages & CANNOT_OPEN_STAGES:
        why = "The camera could not be opened. It may be in use by another program, unplugged, or still reconnecting."
        advice = "Close other programs that use the camera, check its cable, and detect cameras again."
    else:
        return None
    return "\n".join([
        f"Could not start {len(failures)} of {len(requested)} camera(s) with these settings.",
        "Requested: " + "; ".join(requested) + ".",
        "What happened: " + " ".join(happened),
        "Why: " + why,
        "What to try: " + advice,
    ])


def describe_start_failure(failures: dict, configs: dict, started: datetime, detect: Callable[[], list]) -> str | None:
    """Gather the post-failure facts and explain. Never raises: the failure objects stay as they are.

    `detect` is the detection of the caller, so that a test that replaces it also replaces it here."""
    try:
        detected = detect()
    except Exception as detection_error:
        logger.warning(f"Camera detection after a failed start also failed: {detection_error}")
        detected = None
    try:
        return explain_start_failure(failures, configs, detected, usb_disconnects_since(started))
    except Exception as error:
        logger.warning(f"No explanation of the failed start: {type(error).__name__} - {error}")
        return None
