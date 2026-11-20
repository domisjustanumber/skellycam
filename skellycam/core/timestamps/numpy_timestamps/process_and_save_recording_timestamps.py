import logging
import time

import numpy as np
from skellycam.core.camera.config.camera_config import CameraConfigs
from skellycam.core.timestamps.numpy_timestamps.create_camera_csvs import create_and_save_camera_csvs, stamped_columns
from skellycam.core.timestamps.numpy_timestamps.create_multi_frame_csvs import \
    create_and_save_multiframe_csv
from skellycam.core.timestamps.numpy_timestamps.process_recording_timestamps import \
    process_recording_timestamps
from skellycam.core.timestamps.numpy_timestamps.save_timestamps_statistics_summary import \
    save_timestamp_statistics_summary
from skellycam.core.timestamps.recording_timestamp_stats import RecordingTimestampsStats
from skellycam.core.timestamps.timebase_mapping import TimebaseMapping
from skellycam.core.recorders.videos.recording_info import RecordingInfo
from skellycam.core.types.type_overloads import CameraIdString

logger = logging.getLogger(__name__)


def validate_frame_metadatas(frame_metadatas_by_camera: dict[CameraIdString, list[np.recarray]],
                             camera_configs: CameraConfigs) -> tuple[list[int], TimebaseMapping]:
    """
    Validate that all frame metadatas contain the same number of frames, and that the frame numbers match within each cameras' metadata.

    Args:
        frame_metadatas_by_camera: Dictionary mapping camera IDs to arrays of frame metadata.

    Raises:
        ValueError: If the number of frames is inconsistent across cameras.
    """
    # interim (U4): removed in phase 5; a dead camera has fewer frames, from the same first frame (spec 5.7)
    number_of_frames = max(len(frame_metadatas) for frame_metadatas in frame_metadatas_by_camera.values())
    # Check that frame numbers are consistent across cameras
    frame_numbers = []
    for frame_number in range(number_of_frames):
        frame_number = set([metadata[frame_number].frame_number[0] for metadata in frame_metadatas_by_camera.values()
                            if frame_number < len(metadata)])
        if len(frame_number) != 1:
            raise ValueError(f"Inconsistent frame numbers found across cameras: {frame_number}. "
                             f"Expected all cameras to have the same frame numbers.")
        frame_numbers.append(int(frame_number.pop()))

    # Verify camera_id in frame metadata matches the expected camera_id
    for camera_id, metadata in frame_metadatas_by_camera.items():
        frame_camera_id = str(metadata[0].camera_info.camera_id[0])
        if frame_camera_id != camera_id:
            raise ValueError(
                f"Camera ID mismatch: expected {camera_id}, "
                f"got {frame_camera_id} in frame metadata."
            )

    timebase_mapping_recarray: np.recarray | None = None
    for camera_id, metadata in frame_metadatas_by_camera.items():
        for frame_index in range(len(metadata)):
            if timebase_mapping_recarray is None:
                timebase_mapping_recarray = metadata[frame_index].timebase_mapping[0]
            elif metadata[frame_index].timebase_mapping[0] != timebase_mapping_recarray:
                raise ValueError(f"Camera {camera_id} has inconsistent timebase mapping across frames.")
    if timebase_mapping_recarray is None:
        raise ValueError("No timebase mapping found in frame metadata.")

    return frame_numbers, TimebaseMapping.from_numpy_record_array(timebase_mapping_recarray)


async def process_and_save_recording_timestamps(
        frame_metadatas_by_camera: dict[CameraIdString, list[np.recarray]],
        camera_configs: CameraConfigs,
        recording_info: RecordingInfo, ) -> RecordingTimestampsStats:
    tik = time.perf_counter()
    (frame_numbers, timebase_mapping) = validate_frame_metadatas(frame_metadatas_by_camera=frame_metadatas_by_camera,
                                                                 camera_configs=camera_configs)

    # Find the earliest timestamp as recording start time
    first_timestamps = {camera_id: md[0].timestamps[0] for camera_id, md in frame_metadatas_by_camera.items()}
    recording_start_time_ns: int = int(min(
        np.min(ts.pre_frame_grab_ns) for ts in first_timestamps.values()
    ))
    tik_cams = time.perf_counter()
    # Process timestamps
    (all_timestamps,
     all_durations) =  await process_recording_timestamps(
        frame_metadatas_by_camera=frame_metadatas_by_camera,
        frame_numbers=frame_numbers,
    )

    frame_counts = [len(metadata) for metadata in frame_metadatas_by_camera.values()]
    timestamps_rows_by_camera = create_and_save_camera_csvs(
        frame_counts=frame_counts,
        all_timestamps=all_timestamps,
        all_durations=all_durations,
        recording_info=recording_info,
        camera_configs=camera_configs,
        connection_frame_numbers=frame_numbers,
        recording_start_time_ns=recording_start_time_ns,
        timebase_mapping=timebase_mapping
    )
    tok_cams = time.perf_counter()
    print(f"Processed timestamps for {len(frame_metadatas_by_camera)} cameras in {tok_cams - tik_cams:.3f} seconds.")

    tik_mf = time.perf_counter()
    present = np.arange(len(frame_numbers))[None, :] < np.array(frame_counts)[:, None]
    multiframe_rows = create_and_save_multiframe_csv(timestamps_rows_by_camera=timestamps_rows_by_camera,
                                                     present=present,
                                                     recording_info=recording_info,
                                                     stamped=stamped_columns(all_timestamps, frame_counts),
                                                     )
    tok_mf = time.perf_counter()
    print(f"Processed multiframe timestamps in {tok_mf - tik_mf:.3f} seconds.")

    # Save statistics summary
    return save_timestamp_statistics_summary(multiframe_rows_recarray=multiframe_rows,
                                             recording_info=recording_info,
                                             number_of_cameras=len(frame_metadatas_by_camera))
