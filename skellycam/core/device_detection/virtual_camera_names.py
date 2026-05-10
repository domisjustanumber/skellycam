"""Name patterns used to classify common virtual webcam sources."""

from __future__ import annotations

import re

# Must match prefixes requested for the UI "ignore virtual cameras" checklist.
LISTED_VIRTUAL_CAMERA_NAME_PREFIXES: tuple[str, ...] = (
    "OBS-Camera",
    "Spout",
    "NDI Webcam",
    "Camera (NVIDIA Broadcast)",
)

_VIRTUAL_WORD = re.compile(r"\bvirtual\b", re.IGNORECASE)


def name_contains_virtual_word(name: str) -> bool:
    """True if ``name`` contains the whole word *virtual* (case-insensitive)."""
    return bool(_VIRTUAL_WORD.search(name.strip()))


def matches_listed_virtual_camera_prefix(name: str) -> bool:
    """Listed virtual sources: known prefixes or any name containing the word *virtual*."""
    n = name.strip()
    if name_contains_virtual_word(n):
        return True
    return any(n.startswith(prefix) for prefix in LISTED_VIRTUAL_CAMERA_NAME_PREFIXES)
