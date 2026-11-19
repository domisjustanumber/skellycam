"""T-REC-04, 05, 10, 28, 31, 33, 34: the camera file (MKV) and the placeholder.

specs/recorder.md, sections 6.3, 6.4 and 6.9. The camera files are read with the test's own EBML
walker (`ebml.py`), not with the product.
"""

import ast
import hashlib
import re
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

from skellycam.tests.take_recorder import ebml, jpeg_tools, sidecar_check
from skellycam.tests.take_recorder.rec_api import (
    DAMAGED_BYTES, WRITER, Run, block_time_ms, damaged_take, dead_take, default_duration_ns, fixed_clock,
    rec, ring_flags, take_camera)


def block_bytes(path):
    data = Path(path).read_bytes()
    return data, ebml.walk(data)


def is_black_placeholder(payload, layout_payload):
    """A placeholder: the size and factors of the camera's frames (M2), and Y = 0 (M1)."""
    sof, camera = jpeg_tools.parse_sof(payload), jpeg_tools.parse_sof(layout_payload)
    if (sof.width, sof.height, sof.factors) != (camera.width, camera.height, camera.factors):
        return False
    _, y = jpeg_tools.decode_pyav(payload)
    return int(y.max()) == 0


@pytest.mark.parametrize("rate", [(30, 1), (30000, 1001), (60, 1)], ids=["30_1", "30000_1001", "60_1"])
def test_t_rec_04_matroska_structure_and_block_times(tmp_path, runs, rate):
    """T-REC-04 [SFF-732, SFF-733, SFF-735, SFF-736, M1]: 50 frames, frames 10 and 11 damaged.
    DocType `matroska`; one track `V_MJPEG` with a number below 128; one keyframe `SimpleBlock` with
    no lacing for each row; TimestampScale 1,000,000; block k at ⌊(2k·den·1000 + num)/(2·num)⌋ ms
    with no jump; `DefaultDuration` ⌊10^9·den/num⌋; no `Projection` and no other track."""
    frame_flag, _ = ring_flags()
    num, den = rate
    run = Run(tmp_path / "take", [take_camera("0a1b", rate=rate), take_camera("ff00", rate=rate, os_index=1)])
    runs.append(run)
    for k in range(50):
        for camera_id in ("0a1b", "ff00"):
            damaged = camera_id == "0a1b" and k in (10, 11)
            run.give(camera_id, k, payload=DAMAGED_BYTES if damaged else None,
                     flags=frame_flag.CAPTURE_ERROR if damaged else 0)
    run.finish(50)
    for camera_id in ("0a1b", "ff00"):
        _, mkv = block_bytes(run.mkv(camera_id))
        assert mkv.doc_type == "matroska" and mkv.timestamp_scale == 1_000_000
        assert len(mkv.tracks) == 1
        track = mkv.tracks[0]
        assert track.codec_id == "V_MJPEG" and track.number < 128 and track.track_type == 1
        assert track.default_duration == default_duration_ns(num, den)
        assert len(mkv.blocks) == 50
        assert all(b.simple and b.keyframe and b.lacing == 0 and b.track == track.number for b in mkv.blocks)
        assert [b.time_ms for b in mkv.blocks] == [block_time_ms(k, num, den) for k in range(50)]
        assert not mkv.ids & {ebml.PROJECTION, ebml.PROJECTION_POSE_ROLL}
        assert (track.width, track.height) == (640, 480)  # the mode size [agent 26]
    if rate == (30000, 1001):
        assert mkv.tracks[0].default_duration == 33_366_666


def variant_payloads():
    """The payloads of T-REC-05 and their ring flags: bytes after EOI, APP0, APP1 (EXIF), APP14, and
    a JPEG with no DHT through the capture check of the ring (`DHT_INSERTED`)."""
    from skellycam.core.ipc.frame_ring import check_jpeg

    base = [jpeg_tools.synthetic_jpeg(k, 640, 480) for k in range(6)]
    stripped = jpeg_tools.strip_dht(base[5])
    inserted, flags = check_jpeg(stripped, delivered_len=len(stripped), driver_error=False)
    return [
        (base[0] + b"\x00\x11trailing bytes after EOI", 0),
        (jpeg_tools.insert_segment(base[1], jpeg_tools.APP0, b"JFIF\x00\x01\x02\x00\x00\x01\x00\x01\x00\x00"), 0),
        (jpeg_tools.insert_segment(base[2], jpeg_tools.APP1, jpeg_tools.exif_segment()), 0),
        (jpeg_tools.insert_segment(base[3], jpeg_tools.APP14, b"Adobe\x00\x64\x00\x00\x00\x00\x01"), 0),
        (base[4], 0),
        (inserted, int(flags)),
    ]


def test_t_rec_05_block_payloads_are_the_bytes_given(tmp_path, runs):
    """T-REC-05 [SFF-734, SFF-737, M6]: the payload of each block is byte-equal to the payload given
    (SHA-256 of each), also with the DHT that the capture check inserted. The `DHT_INSERTED` frame is
    a normal row (7.1)."""
    frame_flag, _ = ring_flags()
    payloads = variant_payloads()
    assert payloads[-1][1] & frame_flag.DHT_INSERTED
    run = Run(tmp_path / "take", [take_camera("0a1b"), take_camera("ff00", os_index=1)])
    runs.append(run)
    for k, (payload, flags) in enumerate(payloads):
        run.give("0a1b", k, payload=payload, flags=flags)
        run.give("ff00", k, payload=payload, flags=flags)
    run.finish(len(payloads))
    for camera_id in ("0a1b", "ff00"):
        stored = ebml.payloads(run.mkv(camera_id))
        assert [hashlib.sha256(p).hexdigest() for p in stored] == [hashlib.sha256(p).hexdigest() for p, _ in payloads]
        rows = sidecar_check.read(run.csv(camera_id)).rows
        assert [r.flags for r in rows] == [0] * len(payloads)


def check_offsets(mkv_bytes, rows, given, placeholder_check):
    """Each row's byte range equals the frame given for it, or a placeholder."""
    for row in rows:
        payload = mkv_bytes[row.byte_offset:row.byte_offset + row.byte_size]
        kind, expected = given[row.frame]
        if kind == "frame":
            assert payload == expected, f"row {row.frame}: the byte range is not the frame given"
        else:
            assert placeholder_check(payload), f"row {row.frame}: the byte range is not a placeholder"


CASES_10 = {
    "1280x720": (1280, 720, lambda k: jpeg_tools.synthetic_jpeg(k, 1280, 720), False),
    "320x240_small": (320, 240, lambda k: jpeg_tools.small_jpeg(k, 320, 240), False),
    "640x480_placeholders": (640, 480, lambda k: jpeg_tools.synthetic_jpeg(k, 640, 480), True),
}


@pytest.mark.parametrize("case", list(CASES_10))
def test_t_rec_10_live_byte_offsets(tmp_path, runs, case):
    """T-REC-10 [SFF-757 (DT5), review B1, agent 7]: during the take, after each `give`, each
    complete row of the CSV on disk points at a byte range of the MKV on disk that equals the frame
    given or the placeholder. After the end, the values do not change, and the last row is also
    right. The small case has JPEGs of about 2 kB (below 4 KiB)."""
    width, height, make, with_placeholders = CASES_10[case]
    frame_flag, _ = ring_flags()
    if case == "320x240_small":
        assert len(make(0)) < 4096
    camera = take_camera("0a1b", width=width, height=height,
                         layout=rec().parse_sof(make(0)))
    other = take_camera("ff00", width=width, height=height, layout=rec().parse_sof(make(0)), os_index=1)
    run = Run(tmp_path / "take", [camera, other], frames=make)
    runs.append(run)
    given = {}
    reference = make(0)
    count = 40
    live_rows = {}
    for k in range(count):
        if with_placeholders and k % 2 == 1:
            if k % 4 == 1:
                run.give_missing("0a1b")
            else:
                run.give("0a1b", k, payload=DAMAGED_BYTES, flags=frame_flag.NO_SOI_EOI)
            given[k] = ("placeholder", None)
        else:
            run.give("0a1b", k, payload=make(k))
            given[k] = ("frame", make(k))
        run.give("ff00", k, payload=make(k))
        sidecar = sidecar_check.read(run.csv("0a1b"))
        mkv_bytes = run.mkv("0a1b").read_bytes()
        check_offsets(mkv_bytes, sidecar.rows, given, lambda p: is_black_placeholder(p, reference))
        for row in sidecar.rows:
            live_rows.setdefault(row.frame, (row.byte_offset, row.byte_size))
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline and len(sidecar_check.read(run.csv("0a1b")).rows) < count - 1:
        time.sleep(0.01)
    sidecar = sidecar_check.read(run.csv("0a1b"))
    assert len(sidecar.rows) >= count - 1, "rows are written one block late (6.3), not later"
    for row in sidecar.rows:
        live_rows.setdefault(row.frame, (row.byte_offset, row.byte_size))
    run.finish(count)
    final = sidecar_check.read(run.csv("0a1b"))
    assert len(final.rows) == count
    mkv_bytes = run.mkv("0a1b").read_bytes()
    check_offsets(mkv_bytes, final.rows, given, lambda p: is_black_placeholder(p, reference))
    for row in final.rows:
        if row.frame in live_rows:
            assert live_rows[row.frame] == (row.byte_offset, row.byte_size), f"row {row.frame} changed after the close"
    blocks = ebml.walk(mkv_bytes).blocks
    assert [(b.payload_offset, b.payload_size) for b in blocks] == [(r.byte_offset, r.byte_size) for r in final.rows]


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_t_rec_28_rotation_is_only_in_the_header(tmp_path, runs, rotation):
    """T-REC-28 [SFF-735, SFF-751]: the header holds `display_rotation`; the MKV has no rotation
    element; the bytes are not rotated (each block equals the frame given)."""
    cameras = [take_camera("0a1b", rotation=rotation), take_camera("ff00", rotation=rotation, os_index=1)]
    run = Run(tmp_path / "take", cameras)
    runs.append(run)
    for k in range(5):
        run.give("0a1b", k)
        run.give("ff00", k)
    run.finish(5)
    for camera_id in ("0a1b", "ff00"):
        assert sidecar_check.read(run.csv(camera_id)).header["display_rotation"] == str(rotation)
        _, mkv = block_bytes(run.mkv(camera_id))
        assert not mkv.ids & {ebml.PROJECTION, ebml.PROJECTION_POSE_ROLL}
        assert ebml.payloads(run.mkv(camera_id)) == [run.frames(k) for k in range(5)]
    assert run.info()["camera_configs"]
    assert all("rotation" not in c for c in run.info()["camera_configs"].values())


def closest_row(image, run, k, rows):
    """The row among k - 1, k and k + 1 whose frame given is closest to `image` (mean absolute difference)."""
    candidates = [j for j in (k - 1, k, k + 1) if 0 <= j < len(rows) and not rows[j].missing]
    diffs = {}
    for j in candidates:
        reference = cv2.imdecode(np.frombuffer(run.frames(j), np.uint8), cv2.IMREAD_COLOR)
        diffs[j] = float(np.abs(image.astype(np.int16) - reference.astype(np.int16)).mean())
    return min(diffs, key=diffs.get)


def check_row_image(image, run, k, rows, tool):
    if rows[k].missing:
        assert int(image.max()) == 0, f"{tool}: the placeholder of row {k} is not black"
    else:
        assert closest_row(image, run, k, rows) == k, f"{tool}: frame {k} is not row {k}"


def seek_points(rows):
    """11 positions: the ends, the first, a middle and the last placeholder, the row after the last
    placeholder, and evenly spaced positions."""
    n, missing = len(rows), [r.frame for r in rows if r.missing]
    must = [0, n - 1]
    if missing:
        must += [missing[0], missing[len(missing) // 2], missing[-1]] + ([missing[-1] + 1] if missing[-1] + 1 < n else [])
    points = sorted(set(must))
    for p in np.linspace(0, n - 1, 11).astype(int):
        if len(points) >= 11:
            break
        if int(p) not in points:
            points.append(int(p))
    return points[:11]


def check_readers(run, camera_id):
    import av

    from skellycam.core.recorders.videos.sequential_video_reader import SequentialVideoReader

    rows = sidecar_check.read(run.csv(camera_id)).rows
    path = run.mkv(camera_id)
    with av.open(str(path)) as container:
        decoded = [frame.to_ndarray(format="bgr24") for frame in container.decode(video=0)]
    assert len(decoded) == len(rows)
    for k, image in enumerate(decoded):
        check_row_image(image, run, k, rows, "PyAV")
    capture = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
    try:
        assert int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) == len(rows)
        points = seek_points(rows)
        assert len(points) == 11
        for point in points:
            capture.set(cv2.CAP_PROP_POS_FRAMES, point)
            ok, image = capture.read()
            assert ok, f"OpenCV: no frame after the seek to {point}"
            check_row_image(image, run, point, rows, f"OpenCV seek to {point}")
    finally:
        capture.release()
    reader = SequentialVideoReader(path=path)
    try:
        for k in range(len(rows)):
            check_row_image(reader.read_bgr(frame_number=k), run, k, rows, "SequentialVideoReader")
    finally:
        reader.close()


def test_t_rec_31_readers_open_files_with_placeholders(tmp_path, runs):
    """T-REC-31 [M10, M `RS/mkv_black_placeholder/FINDINGS.md`]: the finished MKVs of T-REC-12 and
    T-REC-23 open in PyAV 19.0.2, in OpenCV 5.1.0 (`CAP_PROP_FRAME_COUNT` and 11 `POS_FRAMES` seeks,
    over and after the placeholders) and in `SequentialVideoReader`. The counts equal the rows; each
    seek gives the expected row; the placeholders decode to 0; the reader reads every frame."""
    run12, _ = damaged_take(tmp_path / "t12", runs)
    check_readers(run12, "0a1b")
    run23 = dead_take(tmp_path / "t23", runs, case=1)
    check_readers(run23, "ff00")


def package_sources():
    package = Path(rec().__file__).parent
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(package.rglob("*.py"))}


def test_t_rec_33_only_the_pyav_calls_of_6_3(tmp_path, runs):
    """T-REC-33 [review B1, S5, S6, M `RU/results/jpeg_passthrough/FINDINGS.md` §2.1]: no
    `add_stream_from_template` and no `add_stream(`; `add_mux_stream` with `rate`, `width` and
    `height` as keywords; the container options hold `flush_packets` `"1"` and
    `cluster_size_limit` `"1"`; `start_encoding` runs in `start` (the MKV header is on disk before the
    first frame)."""
    sources = package_sources()
    text = "\n".join(sources.values())
    assert "add_stream_from_template" not in text
    assert not re.search(r"\badd_stream\s*\(", text)
    assert re.search(r"[\"']flush_packets[\"']\s*:\s*[\"']1[\"']", text)
    assert re.search(r"[\"']cluster_size_limit[\"']\s*:\s*[\"']1[\"']", text)
    calls = []
    for source in sources.values():
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_mux_stream":
                calls.append(node)
    assert calls, "no add_mux_stream call"
    for node in calls:
        assert len(node.args) <= 1, "rate, width and height must be keywords [review S6]"
        assert {"rate", "width", "height"} <= {k.arg for k in node.keywords}
    assert "start_encoding" in text
    run = Run(tmp_path / "take", [take_camera("0a1b"), take_camera("ff00", os_index=1)])
    runs.append(run)
    mkv = ebml.walk_file(run.mkv("0a1b"))
    assert mkv.doc_type == "matroska" and mkv.tracks and not mkv.blocks, "the header is in the file at start [S5]"
    run.give("0a1b", 0)
    run.give("ff00", 0)
    run.finish(1)


SIZES_34 = [(640, 480), (1920, 1080), (1278, 719)]


@pytest.mark.parametrize("layout", list(jpeg_tools.LAYOUTS))
@pytest.mark.parametrize(("width", "height"), SIZES_34, ids=[f"{w}x{h}" for w, h in SIZES_34])
def test_t_rec_34_hand_built_placeholder(layout, width, height):
    """T-REC-34 [M2, agent 21]: the placeholder SOF has the size, the component count and the H/V
    factors of the layout; it decodes to Y = 0 in PyAV and in OpenCV, with the pixel format of an
    OpenCV JPEG of that layout; at 1920x1080 4:2:2 it is at most 16,353 bytes plus 1 %."""
    camera_frame = jpeg_tools.synthetic_jpeg(0, width, height, layout)
    placeholder = rec().build_placeholder(rec().parse_sof(camera_frame))
    sof = jpeg_tools.parse_sof(placeholder)
    camera = jpeg_tools.parse_sof(camera_frame)
    assert (sof.width, sof.height, len(sof.factors), sof.factors) == (width, height, len(camera.factors), camera.factors)
    pix_fmt, y = jpeg_tools.decode_pyav(placeholder)
    assert pix_fmt == jpeg_tools.decode_pyav(camera_frame)[0]
    assert y.shape == (height, width) and int(y.max()) == 0
    grey = cv2.imdecode(np.frombuffer(placeholder, np.uint8), cv2.IMREAD_GRAYSCALE)
    assert grey is not None and grey.shape == (height, width) and int(grey.max()) == 0
    if (width, height, layout) == (1920, 1080, "422"):
        assert len(placeholder) <= 16_353 * 1.01


@pytest.mark.parametrize("factors", [((1, 1),) * 4, ((4, 4), (1, 1), (1, 1))], ids=["4_components", "sum_hv_18"])
def test_t_rec_34_refuses_a_layout_that_cannot_be_built(tmp_path, factors):
    """T-REC-34 [agent 22]: a layout of 4 components (and, by 6.4, a sum of H x V above 10) is
    refused by `start_take` with `ValueError`."""
    layout = rec().JpegLayout(width=640, height=480, factors=factors)
    with pytest.raises(ValueError):
        cameras = [take_camera("0a1b"), take_camera("ff00", layout=layout, os_index=1)]
        rec().start_take(tmp_path / "take", "take", cameras, writer=WRITER, clock=fixed_clock())
    assert not (tmp_path / "take").exists()

