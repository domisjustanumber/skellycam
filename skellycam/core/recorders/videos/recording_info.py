import uuid

from pydantic import BaseModel, Field

from skellycam.core.timestamps.full_timestamp import FullTimestamp


class RecordingInfo(BaseModel):
    """The fields of a record start request. The take recorder writes the files (recorder.md 8.3)."""
    recording_name: str
    recording_directory: str  # Path to the directory where the recording will be saved, e.g., "~/skellycam_data/recordings"
    recording_uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    mic_device_index: int = -1

    recording_start_timestamp: FullTimestamp = Field(default_factory=FullTimestamp.now)

    def __str__(self):
        return f"RecordingInfo(name={self.recording_name},\n directory={self.recording_directory},\n uuid={self.recording_uuid})"
