"""USB isochronous bandwidth limits for multi-camera UVC on a single host controller."""

from __future__ import annotations

# Stable key for API clients (e.g. freemocap) — check ``detail.error_code`` on HTTP 409 from ``/camera/group/apply``.
USB_BANDWIDTH_ERROR_CODE = "usb_bandwidth_contention"

# Shown in HTTP responses and logs when a peer camera is streaming and this one never delivers a frame.
USB_BANDWIDTH_USER_GUIDANCE = (
    "Not enough USB video bandwidth for all cameras at this resolution and framerate. "
    "Plug each camera into a USB port on a different host controller (often front versus rear "
    "motherboard ports, or one camera on USB 3 and one on another root hub), or use a powered "
    "USB 3.0 hub for one device. Lower resolution or frame rate also reduces bandwidth."
)


class UsbBandwidthContentionError(RuntimeError):
    """Raised when a camera cannot complete capture setup because peers reserve USB bandwidth.

    Typical cause: UVC isochronous allocations for 720p MJPG (etc.) exceed what one USB 2.0
    controller can carry when multiple cameras share it.
    """

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or USB_BANDWIDTH_USER_GUIDANCE)


class CameraStartupAborted(Exception):
    """Raised inside a camera worker when startup is aborted by coordinated shutdown.

    Distinct from a programming-error ``RuntimeError``: this is the *expected* outcome
    when a peer worker fails (e.g. the peer hits ``UsbBandwidthContentionError`` and
    calls ``kill_everything``), or the user closes the camera group during startup.
    The worker entry point swallows this and returns with exit code 0 so the parent
    process is not flooded with traceback noise from a known-good failure path.
    """
