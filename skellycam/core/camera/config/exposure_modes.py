from enum import Enum


class ExposureModes(float, Enum):
    AUTO = 0.75  # the exposure search of skellycam (specs/camera-requests.md 1.1), never the camera's own auto
    MANUAL = 0.25
