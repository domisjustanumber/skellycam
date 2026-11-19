"""T-REC-07 to T-REC-09 and T-REC-11 to T-REC-13: the timing sidecar (CSV).

specs/recorder.md, sections 6.5, 7.1 and 7.2. The sidecars are read with the test's own strict
reader (`sidecar_check.py`), not with the product.
"""

import datetime
import re
import sys

import pytest

from skellycam.tests.take_recorder import ebml, jpeg_tools, sidecar_check
from skellycam.tests.take_recorder.fake_disk import _REAL_OPEN
from skellycam.tests.take_recorder.rec_api import (
    DAMAGED_BYTES, T0, UTC0, WRITER, Run, camera_key, camera_label, damaged_take, ring_flags, simple_take,
    take_camera)

CLOCKS = {"win32": "windows_qpc", "linux": "linux_monotonic", "darwin": "macos_uptime_raw"}


def local_offset_min():
    return int(datetime.datetime.now().astimezone().utcoffset().total_seconds() // 60)


def test_t_rec_07_header_keys_and_values(tmp_path, runs):
    """T-REC-07 [SFF-700, SFF-707, SFF-710, SFF-742, SFF-743, SFF-749, SFF-772, SFF-774]: each key of
    6.5 in its order with its value; the take keys are equal in each CSV; `clock` is the value of the
    OS; `audio_count` 0; UTF-8 with no byte order mark and LF line ends; the column line."""
    run = simple_take(tmp_path / "take", runs, frames=3)
    sidecars = [sidecar_check.read(run.csv(camera_id)) for camera_id in ("0a1b", "ff00")]
    offset = local_offset_min()
    for position, (camera_id, sidecar) in enumerate(zip(("0a1b", "ff00"), sidecars)):
        data = run.csv(camera_id).read_bytes()
        assert not data.startswith(b"\xef\xbb\xbf") and b"\r" not in data and data.endswith(b"\n")
        data.decode("utf-8")
        assert sidecar.header_order == list(sidecar_check.HEADER_KEYS)
        assert sidecar.columns == list(sidecar_check.COLUMNS)
        header = sidecar.header
        assert data.split(b"\n")[len(sidecar_check.HEADER_KEYS)] == b"frame,source_frame_number,arrival_ns,sample_ns,flags,byte_offset,byte_size,crc32"
        assert header["skellyfileformat"] == "video_timing"
        assert (header["format_version"], header["format_prerelease"], header["writer"]) == ("2.0", "1", WRITER)
        assert re.fullmatch(r"[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}", header["take_uuid"])  # uuid4 hex
        assert (header["take_start_host_ns"], header["take_start_utc_ns"]) == (str(T0), str(UTC0))
        assert header["utc_offset_min"] == str(offset)
        assert header["clock"] == CLOCKS[sys.platform] and header["clock_hz"] == ""
        assert (header["group_size"], header["audio_count"], header["group_position"]) == ("2", "0", str(position))
        assert (header["camera_key"], header["camera_label"]) == (camera_key(camera_id), camera_label(camera_id))
        assert (header["nominal_rate"], header["display_rotation"]) == ("30/1", "0")
    take_keys = [[s.header[k] for k in sidecar_check.TAKE_KEYS] for s in sidecars]
    assert take_keys[0] == take_keys[1]
    assert run.manifest()["take_uuid"] == sidecars[0].header["take_uuid"]


def test_t_rec_08_row_fields(tmp_path, runs):
    """T-REC-08 [SFF-701, SFF-704, SFF-741, SFF-744, SFF-754, SFF-755, M3]: `frame` is 0, 1, 2 …; the
    times are relative to `take_start_host_ns`; `sample_ns` is empty for `NO_SAMPLE_NS`; a
    `give_missing` row has empty times and source number; each integer has the form of SFF-701; no
    quote; each CRC is correct."""
    run = Run(tmp_path / "take", [take_camera("0a1b"), take_camera("ff00", os_index=1)])
    runs.append(run)
    plan = [  # (kind, arrival offset, sample offset or None for NO_SAMPLE_NS)
        ("frame", 1_203_311, 1_180_002), ("frame", 1_303_311, None), ("missing", None, None),
        ("frame", 1_400_000, -5), ("frame", 0, 0), ("missing", None, None), ("frame", 2**40, 2**40 - 1),
    ]
    for k, (kind, arrival, sample) in enumerate(plan):
        for camera_id in ("0a1b", "ff00"):
            if kind == "missing":
                run.give_missing(camera_id)
            else:
                run.give(camera_id, k, arrival_ns=T0 + arrival, sample_ns=None if sample is None else T0 + sample)
    run.finish(len(plan))
    for camera_id in ("0a1b", "ff00"):
        data = run.csv(camera_id).read_bytes()
        assert b'"' not in data and b" " not in data.split(b"frame,source_frame_number")[1].split(b"# end")[0]
        sidecar = sidecar_check.read(run.csv(camera_id))
        assert sidecar.bad_row is None and len(sidecar.rows) == len(plan)
        for k, ((kind, arrival, sample), row) in enumerate(zip(plan, sidecar.rows)):
            assert row.frame == k
            if kind == "missing":
                assert (row.source_frame_number, row.arrival_ns, row.sample_ns) == (None, None, None)
                assert row.flags == sidecar_check.MISSING and row.byte_offset is not None and row.byte_size
            else:
                assert row.source_frame_number == 1000 + k
                assert row.arrival_ns == arrival and row.sample_ns == sample
            assert row.crc32 == sidecar_check.row_crc(row.raw)


SEQUENCE_09 = [  # (source frame number or None for give_missing, ring flag name or None)
    (1000, None), (1001, None), (1004, None), (1004, None), (1005, "DISCONTINUITY"), (1006, "DHT_INSERTED"),
    (None, None), (1009, None), (1010, None), (1010, "DISCONTINUITY"), (1013, "DHT_INSERTED"),
]


def test_t_rec_09_gap_and_repeat_flags(tmp_path, runs):
    """T-REC-09 [SFF-756]: `gap` and `repeat` as 7.1 gives them; 0 in the first row and after a row
    with no source frame number; `filled` and `encode_skip` are 0; the ring flags `DISCONTINUITY` and
    `DHT_INSERTED` change no flag."""
    frame_flag, _ = ring_flags()
    run = Run(tmp_path / "take", [take_camera("0a1b"), take_camera("ff00", os_index=1)])
    runs.append(run)
    for k, (sfn, flag) in enumerate(SEQUENCE_09):
        for camera_id in ("0a1b", "ff00"):
            if sfn is None:
                run.give_missing(camera_id)
            else:
                run.give(camera_id, k, sfn=sfn, flags=getattr(frame_flag, flag) if flag else 0)
    run.finish(len(SEQUENCE_09))
    expected, previous = [], None
    for sfn, _ in SEQUENCE_09:
        expected.append(sidecar_check.expected_flags(previous, sfn, sfn is None))
        previous = sfn
    assert expected[:4] == [0, 0, sidecar_check.GAP, sidecar_check.REPEAT]
    for camera_id in ("0a1b", "ff00"):
        rows = sidecar_check.read(run.csv(camera_id)).rows
        assert [r.flags for r in rows] == expected
        assert not any(r.flags & (sidecar_check.FILLED | sidecar_check.ENCODE_SKIP) for r in rows)


def test_t_rec_11_end_line_and_no_fit_lines(tmp_path, runs):
    """T-REC-11 [SFF-745, SFF-758, F-1, R1, M3]: a take with one gap (camera A), two damaged frames
    (camera B) and a dead camera (C, from row 30 of 50). Each CSV ends with
    `# end rows= gaps= filled= missing= encode_skips=` in this order with the right counts; no `# fit`
    line; the manifest summary has the `missing` count of each camera."""
    frame_flag, _ = ring_flags()
    ids = ("0a1b", "ff00", "c3d4")
    run = Run(tmp_path / "take", [take_camera(c, os_index=i) for i, c in enumerate(ids)])
    runs.append(run)
    for k in range(50):
        run.give("0a1b", k, sfn=1000 + k + (2 if k >= 10 else 0))  # one gap at row 10
        if k in (5, 6):
            run.give("ff00", k, payload=DAMAGED_BYTES, flags=frame_flag.CAPTURE_ERROR)
        else:
            run.give("ff00", k)
        if k < 30:
            run.give("c3d4", k)
        elif k < 40:
            run.give_missing("c3d4")
    run.finish(50, dead_cameras={"c3d4": "device removed"})
    expected = {"0a1b": (1, 0), "ff00": (0, 2), "c3d4": (0, 20)}  # (gaps, missing)
    summary = run.manifest()["summary"]["cameras"]
    for position, camera_id in enumerate(ids):
        data = run.csv(camera_id).read_bytes()
        last = data.rstrip(b"\n").split(b"\n")[-1].decode()
        gaps, missing = expected[camera_id]
        assert last == f"# end rows=50 gaps={gaps} filled=0 missing={missing} encode_skips=0"
        sidecar = sidecar_check.read(run.csv(camera_id))
        assert sidecar.footer_words() == ["end"]
        assert b"# fit" not in data
        assert summary[position]["missing"] == missing and summary[position]["gaps"] == gaps
        assert list(summary[position]).index("missing") == list(summary[position]).index("filled") + 1


ERROR_BITS = {"OVERSIZE": 0x01, "CAPTURE_ERROR": 0x02, "NO_SOI_EOI": 0x04, "DECODE_ERROR": 0x08}


@pytest.mark.parametrize("case", ["spec_mix", *ERROR_BITS], ids=lambda c: c.lower())
def test_t_rec_12_damaged_frames_are_placeholder_rows(tmp_path, runs, case):
    """T-REC-12 [R3, M1, M3]: frames 0 to 99; frames 20 and 21 have `CAPTURE_ERROR`, frame 50
    `NO_SOI_EOI`; then the same with each bit of the error mask 0x0F. Rows 20, 21 and 50 are
    `missing` rows with the times of the frame and the byte fields of a placeholder block; 100
    blocks; the damaged bytes are not in the MKV; `missing=3`."""
    flags = None if case == "spec_mix" else {k: ERROR_BITS[case] for k in (20, 21, 50)}
    run, used = damaged_take(tmp_path / "take", runs, flags=flags)
    sidecar = sidecar_check.read(run.csv("0a1b"))
    data = run.mkv("0a1b").read_bytes()
    mkv = ebml.walk(data)
    assert len(sidecar.rows) == 100 and len(mkv.blocks) == 100
    reference = jpeg_tools.parse_sof(run.frames(0))
    placeholders = set()
    for row in sidecar.rows:
        if row.frame in used:
            assert row.flags & sidecar_check.MISSING
            assert row.source_frame_number == 1000 + row.frame and row.arrival_ns is not None and row.sample_ns is not None
            payload = data[row.byte_offset:row.byte_offset + row.byte_size]
            sof = jpeg_tools.parse_sof(payload)
            assert (sof.width, sof.height, sof.factors) == (reference.width, reference.height, reference.factors)
            assert int(jpeg_tools.decode_pyav(payload)[1].max()) == 0
            placeholders.add(payload)
        else:
            assert not row.flags & sidecar_check.MISSING
            assert data[row.byte_offset:row.byte_offset + row.byte_size] == run.frames(row.frame)
    assert len(placeholders) == 1, "one placeholder for each camera file (M2)"
    assert DAMAGED_BYTES[:40] not in data
    assert sidecar.end["missing"] == 3
    assert sidecar_check.read(run.csv("ff00")).end["missing"] == 0


def test_t_rec_13_one_write_for_each_row(tmp_path, runs, disk):
    """T-REC-13 [SFF-744, SFF-787]: a spy on the writes of the CSV file object. One `write` call for
    each row, with its LF; the file on disk holds only complete lines after each call."""
    faults = []

    def after_write(handle, data):
        if handle.kind != ".csv":
            return
        if not data.endswith(b"\n") or data.count(b"\n") != 1:
            faults.append(("not one line", data[:60]))
        with _REAL_OPEN(handle.path, "rb") as reader:
            content = reader.read()
        if not content.endswith(b"\n"):
            faults.append(("incomplete line on disk", content[-60:]))

    disk.after_write = after_write
    run = simple_take(tmp_path / "take", runs, frames=30)
    assert faults == []
    for camera_id in ("0a1b", "ff00"):
        path = run.csv(camera_id).resolve()
        rows = [e for e in disk.events_of("write") if e[3] == path.relative_to(disk.root).as_posix()]
        sidecar = sidecar_check.read(path)
        lines = len(sidecar.header) + 1 + len(sidecar.rows) + len(sidecar.footer)
        assert len(rows) == lines, "one write call for each line"
