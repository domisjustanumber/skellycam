"""Tests for recording info, frame dtypes, rotation names and descriptive statistics."""

import uuid
from pathlib import Path

import numpy as np
import pytest

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.camera.config.image_rotation_types import (
    RotationTypes,
    rotation_int_to_name,
)
from skellycam.core.recorders.videos.recording_info import RecordingInfo
from skellycam.core.types.frame_dtype_factories import (
    create_frame_dtype,
    create_multiframe_dtype,
)
from skellycam.core.types.numpy_record_dtypes import (
    FRAME_METADATA_DTYPE,
    FRAME_CAMERA_INFO_DTYPE,
)
from skellycam.utilities.descriptive_statistics import DescriptiveStatistics


# ---------------------------------------------------------------------------
# Numpy Dtype Construction
# ---------------------------------------------------------------------------


class TestNumpyDtypes:
    def test_create_frame_dtype(self) -> None:
        config = CameraConfig(
            resolution=ImageResolution(height=48, width=64),
            color_channels=3,
        )
        dtype = create_frame_dtype(config)
        assert "frame_metadata" in dtype.names
        assert "image" in dtype.names

    def test_create_multiframe_dtype(self) -> None:
        configs = {
            "cam0": CameraConfig(
                camera_id="cam0",
                camera_index=0,
                resolution=ImageResolution(height=48, width=64),
            ),
            "cam1": CameraConfig(
                camera_id="cam1",
                camera_index=1,
                resolution=ImageResolution(height=48, width=64),
            ),
        }
        dtype = create_multiframe_dtype(configs)
        assert "cam0" in dtype.names
        assert "cam1" in dtype.names

    def test_frame_metadata_dtype_has_expected_fields(self) -> None:
        assert "camera_info" in FRAME_METADATA_DTYPE.names
        assert "frame_number" in FRAME_METADATA_DTYPE.names
        assert "timebase_mapping" in FRAME_METADATA_DTYPE.names
        assert "timestamps" in FRAME_METADATA_DTYPE.names


# ---------------------------------------------------------------------------
# RecordingInfo
# ---------------------------------------------------------------------------


class TestRecordingInfo:
    def test_equality(self) -> None:
        shared_ts = RecordingInfo(recording_name="t", recording_directory="/tmp/t").recording_start_timestamp
        a = RecordingInfo(
            recording_name="a",
            recording_directory="/tmp/a",
            recording_uuid="uuid1",
            recording_start_timestamp=shared_ts,
        )
        b = RecordingInfo(
            recording_name="a",
            recording_directory="/tmp/a",
            recording_uuid="uuid1",
            recording_start_timestamp=shared_ts,
        )
        c = RecordingInfo(
            recording_name="c",
            recording_directory="/tmp/c",
            recording_uuid="uuid2",
            recording_start_timestamp=shared_ts,
        )
        assert a == b
        assert a != c

    def test_str(self) -> None:
        info = RecordingInfo(recording_name="rec", recording_directory="/tmp/test")
        s = str(info)
        assert "RecordingInfo" in s
        assert info.recording_name in s


# ---------------------------------------------------------------------------
# RotationTypes utilities
# ---------------------------------------------------------------------------


class TestRotationTypes:
    def test_rotation_int_to_name_known(self) -> None:
        assert rotation_int_to_name(-1) == "NO_ROTATION"
        assert rotation_int_to_name(1) == "ROTATE_180"

    def test_rotation_int_to_name_unknown(self) -> None:
        assert rotation_int_to_name(9999) == "UNKNOWN_ROTATION"


# ---------------------------------------------------------------------------
# DescriptiveStatistics
# ---------------------------------------------------------------------------


class TestDescriptiveStatistics:
    def test_basic_statistics(self) -> None:
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        stats = DescriptiveStatistics.from_samples(
            samples=data, name="test", units="ms"
        )
        assert stats.mean == pytest.approx(3.0)
        assert stats.median == pytest.approx(3.0)
        assert stats.min == pytest.approx(1.0)
        assert stats.max == pytest.approx(5.0)
        assert stats.range == pytest.approx(4.0)
        assert stats.number_of_samples == 5

    def test_single_sample(self) -> None:
        stats = DescriptiveStatistics.from_samples(samples=[42.0], name="single")
        assert stats.mean == pytest.approx(42.0)
        assert stats.standard_deviation == pytest.approx(0.0)

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            DescriptiveStatistics.from_samples(samples=[], name="empty")

    def test_numpy_array_input(self) -> None:
        data = np.array([10.0, 20.0, 30.0])
        stats = DescriptiveStatistics.from_samples(samples=data, name="numpy")
        assert stats.mean == pytest.approx(20.0)

    def test_str_representation(self) -> None:
        stats = DescriptiveStatistics.from_samples(
            samples=[1.0, 2.0, 3.0, 4.0, 5.0],
            name="test",
            units="Hz",
        )
        s = str(stats)
        assert "test" in s
        assert "Hz" in s

    def test_model_dump(self) -> None:
        stats = DescriptiveStatistics.from_samples(
            samples=[1.0, 2.0, 3.0],
            name="dump_test",
            units="s",
        )
        d = stats.model_dump()
        assert isinstance(d, dict)
        assert d["name"] == "dump_test"
        assert d["units"] == "s"
        assert "max" in d
        assert "min" in d
