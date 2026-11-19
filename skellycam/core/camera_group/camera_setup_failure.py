"""Serializable camera failures shared by workers and their parent (specs/windows-capture.md, section 12)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CameraSetupFailure:
    camera_id: str
    stage: str
    reason: str

    def __str__(self) -> str:
        return f"Camera {self.camera_id} failed during {self.stage}: {self.reason}"


class CameraSetupFailedException(RuntimeError):
    """Recoverable group startup failure; must not kill the whole backend."""
