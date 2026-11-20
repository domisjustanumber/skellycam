import logging
from datetime import datetime, timezone

import numpy as np

from skellycam.core.recorders.videos.recording_info import RecordingInfo
from skellycam.core.types.numpy_record_dtypes import CAMERA_TIMESTAMPS_CSV_ROW_DTYPE, MULTI_FRAME_TIMESTAMP_CSV_ROW
from skellycam.utilities.time_unit_conversion import ns_to_ms

logger = logging.getLogger(__name__)


def create_and_save_multiframe_csv(timestamps_rows_by_camera: np.recarray,
                                   recording_info: RecordingInfo,
                                   present: np.ndarray | None = None,
                                   stamped: list[str] | None = None) -> np.recarray:
    """
    Create a multiframe CSV that combines timestamps from all cameras.

    Args:
        timestamps_rows_by_camera: A dictionary mapping camera IDs to their respective CSV row recarrays.
        stamped: the columns of the camera CSVs (D41). The statistics of each other `frame.`, `duration.`
            and `total.` column are NaN: the source does not stamp that stage (Media Foundation and the
            fake source have no retrieve), so no value exists.

    Returns:
        A numpy recarray containing the combined multiframe data.
    """
    if not timestamps_rows_by_camera.dtype == CAMERA_TIMESTAMPS_CSV_ROW_DTYPE:
        raise ValueError(f"timestamps_rows_by_camera must be a numpy recarray with dtype CAMERA_TIMESTAMPS_CSV_ROW, "
                         f"got {type(timestamps_rows_by_camera)} with dtype {timestamps_rows_by_camera.dtype}")

    (number_of_cameras, number_of_frames) = timestamps_rows_by_camera.shape
    if present is None:
        present = np.ones((number_of_cameras, number_of_frames), dtype=bool)

    def by_camera(column_name: str) -> np.ndarray:
        """The values of the cameras that have the frame; NaN for a dead camera (interim U4, spec 5.7)."""
        return np.where(present, timestamps_rows_by_camera[column_name].astype(np.float64), np.nan)
    multiframe_csv_rows = np.recarray(
        number_of_frames,
        dtype=MULTI_FRAME_TIMESTAMP_CSV_ROW
    )

    # Process non-statistical columns first (these are faster)
    # Check that all cameras have the same recording frame numbers
    value_set = set(np.unique(timestamps_rows_by_camera['recording_frame_number']))
    if len(value_set) != number_of_frames:
        raise ValueError(f"Inconsistent recording_frame_number values found across cameras")

    # Copy recording frame numbers to multiframe numbers
    multiframe_csv_rows['multiframe_number'] = timestamps_rows_by_camera[0, :]['recording_frame_number']

    # Process simple mean-based columns
    for column_name in ['timestamp.from_recording_start.sec', 'timestamp.utc.seconds', 'timestamp.perf_counter_ns.ns']:
        multiframe_csv_rows[column_name] = np.nanmean(by_camera(column_name), axis=0)

    # Calculate local ISO timestamps from UTC seconds
    utc_seconds = multiframe_csv_rows['timestamp.utc.seconds']
    for i in range(number_of_frames):
        utc_dt = datetime.fromtimestamp(utc_seconds[i], tz=timezone.utc)
        local_dt = utc_dt.astimezone()
        multiframe_csv_rows[i]['timestamp.local.iso8601'] = local_dt.isoformat()

    # Calculate inter-camera frame grab range
    perf_counter_ns = by_camera('timestamp.perf_counter_ns.ns')
    multiframe_csv_rows['inter_camera.frame_grab_range.ms'] = ns_to_ms(
        np.nanmax(perf_counter_ns, axis=0) - np.nanmin(perf_counter_ns, axis=0)
    )

    # Process from_previous columns
    for column_name in ['from_previous.frame_duration.ms', 'from_previous.framerate.hz']:
        column_data = np.zeros(number_of_frames)
        for i in range(number_of_frames):
            slice_data = by_camera(column_name)[:, i]
            if np.any(~np.isnan(slice_data)):
                column_data[i] = np.nanmean(slice_data)
            else:
                column_data[i] = np.nan
        # First frame has no previous frame
        column_data[0] = np.nan
        multiframe_csv_rows[column_name] = column_data

    # Process statistical columns in batches by type
    timestamp_columns = [col for col in CAMERA_TIMESTAMPS_CSV_ROW_DTYPE.names
                         if col.startswith(('frame.', 'duration.', 'total.'))]

    for column_name in timestamp_columns:
        if stamped is not None and column_name not in stamped:
            base_name = column_name.replace('.ns', '')
            for suffix in ('ms.mean', 'ms.median', 'ms.standard_deviation', 'ms.range',
                           'proportion.coefficient_of_variation'):
                multiframe_csv_rows[f'{base_name}.{suffix}'] = np.nan
            continue
        # Get data for all cameras and frames for this column
        column_data = by_camera(column_name)

        # Convert to ms if needed
        if '.ns' in column_name:
            column_data = column_data / 1e6

        # Calculate statistics across cameras (axis=0)
        mean_values = np.nanmean(column_data, axis=0)
        median_values = np.nanmedian(column_data, axis=0)
        std_values = np.nanstd(column_data, axis=0)
        min_values = np.nanmin(column_data, axis=0)
        max_values = np.nanmax(column_data, axis=0)
        range_values = max_values - min_values
        # Avoid division by zero in coefficient of variation
        cv_values = np.zeros_like(mean_values)
        nonzero_mask = mean_values != 0
        cv_values[nonzero_mask] = std_values[nonzero_mask] / mean_values[nonzero_mask]

        # Map to output column names
        if '.ns' in column_name:
            base_name = column_name.replace('.ns', '')
            multiframe_csv_rows[f'{base_name}.ms.mean'] = mean_values
            multiframe_csv_rows[f'{base_name}.ms.median'] = median_values
            multiframe_csv_rows[f'{base_name}.ms.standard_deviation'] = std_values
            multiframe_csv_rows[f'{base_name}.ms.range'] = range_values
            multiframe_csv_rows[f'{base_name}.proportion.coefficient_of_variation'] = cv_values
        else:
            base_name = column_name
            multiframe_csv_rows[f'{base_name}.ms.mean'] = mean_values
            multiframe_csv_rows[f'{base_name}.ms.median'] = median_values
            multiframe_csv_rows[f'{base_name}.ms.standard_deviation'] = std_values
            multiframe_csv_rows[f'{base_name}.ms.range'] = range_values
            multiframe_csv_rows[f'{base_name}.proportion.coefficient_of_variation'] = cv_values

    # Save to CSV
    np.savetxt(recording_info.timestamp_file_path,
               multiframe_csv_rows,
               delimiter=',',
               fmt='%s',
               header=",".join(MULTI_FRAME_TIMESTAMP_CSV_ROW.names),
               comments='')

    return multiframe_csv_rows