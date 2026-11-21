"""The failure codes of a camera failure and their default by stage (specs/unix-capture.md, 4.6.3). Pure.

A site that gives no code gets the default: `open-failed` at a stage before streaming, else
`stream-error`. A hung failure with no code gets `hung` (each hung row of the code table of 4.6.3).
"""

CODES = ("not-found", "no-access", "no-permission", "camera-in-use", "usb-bandwidth", "no-mode", "below-floor",
         "open-failed", "first-frame-timeout", "no-native-jpeg", "not-ready", "rate-low", "rate-high",
         "control-failed", "device-removed", "stalled", "hung", "disk-stall", "previous-process-alive",
         "stream-error", "format-changed", "process-ended")

# "start stream" is the Media Foundation stage between `set mode` and `first frame` (windows-capture.md 12).
STAGES_BEFORE_STREAMING = ("detection", "open", "set mode", "start stream", "first frame", "set controls", "warm-up",
                           "rate check")


def default_code(stage: str, hung: bool = False) -> str:
    if hung:
        return "hung"
    return "open-failed" if stage in STAGES_BEFORE_STREAMING else "stream-error"
