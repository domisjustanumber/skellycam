"""The expected results of T-REC-37, written by hand from specs/recorder.md section 12.3 [review S9].

They are not taken from a run. Each row is (test function and case, expected, reason). A `*` in the
name matches any text. Each collected test matches the first row whose name matches; a result that
differs is a failure of T-REC-37. When the user accepts a format change of section 13, this table
changes in the same commit as the new pin.
"""

SFF_COMMIT = "d67679ada704caf55c64c2e279081d317205f354"

EXPECTED = [
    ("test_sft_705_names_and_layout[file_of_another_take]", "pass", ""),
    ("test_sft_711_camera_file[four_rotations]", "pass", ""),
    ("test_sft_711_camera_file[rate_30000_1001]", "pass", ""),
    ("test_sft_711_camera_file[rate_1001_1]", "pass", ""),
    ("test_sft_712_jpeg_bytes[mjpeg_source]", "pass", ""),
    ("test_sft_712_jpeg_bytes[h264_request]", "pass", ""),
    ("test_sft_700_text_integers_json_ids_crcs", "fail", "it records audio (5b)"),
    ("test_sft_705_names_and_layout[plain]", "fail", "it records audio (5b)"),
    ("test_sft_705_names_and_layout[labels_of_7]", "fail", "remembered keys; 5a makes keys from camera_id [C3] (5d)"),
    ("test_sft_705_names_and_layout[labels_of_8]", "fail", "remembered keys; 5a makes keys from camera_id [C3] (5d)"),
    ("test_sft_705_names_and_layout[camera_key_0]", "fail", "a conversion writer; skellycam's converter is phase 6"),
    ("test_sft_708_manifest", "fail", "it records audio (5b)"),
    ("test_sft_711_camera_file[two_cameras]", "fail", "it records audio (5b)"),
    ("test_sft_712_jpeg_bytes[raw_source]", "fail", "raw YUYV input; the recorder takes JPEG only (3b encodes in the loop)"),
    ("test_sft_715_common_csv_rules[mono_as_g1]", "fail", "it records audio (5b)"),
    ("test_sft_715_common_csv_rules[stereo_as_g2]", "fail", "it records audio (5b)"),
    ("test_sft_717_filled_bit_provisional", "skip", "provisional in the format"),
    ("test_sft_720_*", "fail", "audio (5b)"),
    ("test_sft_721_*", "fail", "audio (5b)"),
    ("test_sft_722_*", "fail", "audio (5b)"),
    ("test_sft_725_linux_macos_provisional", "skip", "provisional in the format"),
    ("test_sft_726_fit", "fail", "audio and fit lines (5b)"),
    ("test_sft_730_whole_files_and_live_files", "fail", "audio (5b) and repair_take (5c)"),
    ("test_sft_730_fsync_provisional", "skip", "provisional in the format"),
    ("test_sft_733_camera_file_provisional[*]", "skip", "provisional in the format"),
    ("test_sft_735_capture_info_json", "fail", "audio (5b); user_name (5d)"),
    ("test_sft_766_writer_part", "fail", "it records audio (5b)"),
]
