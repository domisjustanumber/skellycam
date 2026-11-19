"""Self-tests of the recorder test helpers. They pass before the product code of step 5a exists.

They check the synthetic JPEG maker and the SOF parser, the EBML walker, the sidecar reader, the
fake disk and the child process helper with no product code, so that a failure of a T-REC test comes
from the product, not from a helper.
"""

import errno
import sys
import threading
import time
from fractions import Fraction

import av
import pytest

from skellycam.tests.take_recorder import ebml, jpeg_tools, sidecar_check
from skellycam.tests.take_recorder.rec_api import block_time_ms, camera_key, camera_label, queue_size


# ---------------------------------------------------------------------------
# Synthetic JPEGs and the SOF parser
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("layout", list(jpeg_tools.LAYOUTS))
@pytest.mark.parametrize(("width", "height"), [(640, 480), (1278, 719)])
def test_synthetic_jpeg_has_the_layout_and_decodes(layout, width, height):
    data = jpeg_tools.synthetic_jpeg(3, width, height, layout)
    sof = jpeg_tools.parse_sof(data)
    assert (sof.width, sof.height, sof.factors) == (width, height, jpeg_tools.LAYOUTS[layout])
    assert jpeg_tools.layout_name(sof) == layout
    image = jpeg_tools.decode_bgr(data)
    assert image is not None and image.shape[:2] == (height, width)
    pix_fmt, y = jpeg_tools.decode_pyav(data)
    assert pix_fmt == jpeg_tools.PYAV_PIX_FMT[layout]
    assert y.shape == (height, width)


def test_synthetic_jpegs_differ_by_index_and_are_repeatable():
    assert jpeg_tools.synthetic_jpeg(1) == jpeg_tools.synthetic_jpeg(1)
    assert jpeg_tools.synthetic_jpeg(1) != jpeg_tools.synthetic_jpeg(2)


def test_parse_sof_reads_a_progressive_sof2():
    import cv2

    ok, encoded = cv2.imencode(".jpg", jpeg_tools.pattern(0, 64, 48), [cv2.IMWRITE_JPEG_PROGRESSIVE, 1])
    assert ok
    sof = jpeg_tools.parse_sof(encoded.tobytes())
    assert sof.marker == 0xC2 and (sof.width, sof.height) == (64, 48)


def test_parse_sof_refuses_data_with_no_sof():
    with pytest.raises(ValueError):
        jpeg_tools.parse_sof(b"\xff\xd8\xff\xda\x00\x02")


def test_segment_edits_keep_a_decodable_jpeg():
    data = jpeg_tools.synthetic_jpeg(0, 64, 48)
    edited = jpeg_tools.insert_segment(data, jpeg_tools.APP1, jpeg_tools.exif_segment())
    edited = jpeg_tools.insert_segment(edited, jpeg_tools.APP14, b"Adobe\x00\x64\x00\x00\x00\x00\x01")
    assert [m for m, _, _ in jpeg_tools.segments(edited)][:2] == [jpeg_tools.APP14, jpeg_tools.APP1]
    assert jpeg_tools.decode_bgr(edited + b"trailing bytes") is not None
    stripped = jpeg_tools.strip_dht(data)
    assert jpeg_tools.DHT not in [m for m, _, _ in jpeg_tools.segments(stripped)]


def test_stripped_dht_is_inserted_by_the_ring_capture_check():
    from skellycam.core.ipc.frame_ring import FrameFlag, check_jpeg

    stripped = jpeg_tools.strip_dht(jpeg_tools.synthetic_jpeg(0, 64, 48))
    payload, flags = check_jpeg(stripped, delivered_len=len(stripped), driver_error=False)
    assert flags & FrameFlag.DHT_INSERTED
    assert jpeg_tools.DHT in [m for m, _, _ in jpeg_tools.segments(payload)]
    assert jpeg_tools.decode_bgr(payload) is not None


# ---------------------------------------------------------------------------
# The EBML walker
# ---------------------------------------------------------------------------

FRAMES = [bytes([k]) * (100 + k) for k in range(5)]


@pytest.mark.parametrize("unknown_segment", [True, False])
def test_walker_finds_blocks_times_and_crc_children(unknown_segment):
    data = ebml.build_mkv(FRAMES, unknown_segment=unknown_segment)
    mkv = ebml.walk(data)
    assert mkv.doc_type == "matroska" and mkv.timestamp_scale == 1_000_000
    assert mkv.segment_unknown_size is unknown_segment
    assert [t.codec_id for t in mkv.tracks] == ["V_MJPEG"] and mkv.tracks[0].default_duration == 33333333
    assert [data[b.payload_offset:b.payload_offset + b.payload_size] for b in mkv.blocks] == FRAMES
    assert [b.time_ms for b in mkv.blocks] == [33 * k for k in range(5)]
    assert all(b.keyframe and b.lacing == 0 and b.simple and b.track == 1 for b in mkv.blocks)
    assert all(c.first_child == ebml.CRC32 and c.crc_ok and c.block_count == 1 for c in mkv.clusters)
    assert mkv.cut_at is None


def test_walker_detects_a_bad_crc():
    data = bytearray(ebml.build_mkv(FRAMES))
    data[-3] ^= 0xFF  # a byte of the last block payload
    assert ebml.walk(bytes(data)).clusters[-1].crc_ok is False


def test_walker_stops_at_a_cut_file():
    data = ebml.build_mkv(FRAMES)
    cut = data[:-10]
    mkv = ebml.walk(cut)
    assert len(mkv.blocks) == 4 and mkv.cut_at is not None
    header_only = ebml.walk(ebml.build_mkv([]))
    assert header_only.blocks == [] and header_only.tracks and header_only.doc_type == "matroska"


def pyav_mkv(path, frames, num=30, den=1, width=64, height=48, close=True):
    raw = open(path, "xb", buffering=0)
    container = av.open(raw, mode="w", format="matroska", options={"flush_packets": "1", "cluster_size_limit": "1"})
    stream = container.add_mux_stream("mjpeg", rate=Fraction(num, den), width=width, height=height)
    container.start_encoding()
    for k, frame in enumerate(frames):
        packet = av.Packet(frame)
        packet.stream = stream
        packet.time_base = Fraction(1, 1000)
        packet.pts = packet.dts = block_time_ms(k, num, den)
        container.mux(packet)
    if close:
        container.close()
        raw.close()
    return container, raw


def test_walker_reads_a_pyav_file_live_and_finished(tmp_path):
    frames = [jpeg_tools.synthetic_jpeg(k, 64, 48) for k in range(6)]
    container, raw = pyav_mkv(tmp_path / "a.mkv", frames, 30000, 1001, close=False)
    live = ebml.walk_file(tmp_path / "a.mkv")
    assert live.segment_unknown_size and len(live.blocks) == 5  # the muxer holds the last block
    assert all(c.first_child == ebml.CRC32 and c.crc_ok for c in live.clusters)
    container.close()
    raw.close()
    done = ebml.walk_file(tmp_path / "a.mkv")
    assert ebml.payloads(tmp_path / "a.mkv") == frames
    assert [b.time_ms for b in done.blocks] == [block_time_ms(k, 30000, 1001) for k in range(6)]
    assert done.tracks[0].default_duration == 33_366_666 and done.has_cues
    assert ebml.PROJECTION not in done.ids


# ---------------------------------------------------------------------------
# The sidecar reader
# ---------------------------------------------------------------------------

HEADER = "".join(f"# {key}=v\n" for key in sidecar_check.HEADER_KEYS) + ",".join(sidecar_check.COLUMNS) + "\n"


def test_sidecar_reader_reads_rows_and_footer():
    rows = sidecar_check.make_row(0, 1000, 5, None, 0, 4127, 61234) + sidecar_check.make_row(1, None, None, None, 16, None, None)
    data = HEADER.encode() + rows + b"# repair cut_bytes=1 media_cut_bytes=2 repair_writer=skellycam 2.0.0\n# end rows=2 gaps=0 filled=0 missing=1 encode_skips=0\n"
    sidecar = sidecar_check.parse(data)
    assert sidecar.header_order == list(sidecar_check.HEADER_KEYS) and sidecar.columns == list(sidecar_check.COLUMNS)
    assert [r.frame for r in sidecar.rows] == [0, 1] and sidecar.rows[1].missing
    assert sidecar.rows[0].sample_ns is None and sidecar.rows[1].byte_offset is None
    assert sidecar.footer_words() == ["repair", "end"]
    assert sidecar.footer[0][1]["repair_writer"] == "skellycam 2.0.0"
    assert sidecar.end == {"rows": 2, "gaps": 0, "filled": 0, "missing": 1, "encode_skips": 0}
    assert sidecar.bad_row is None and sidecar.torn_bytes == 0


def test_sidecar_row_crc_is_zlib_crc32_of_the_bytes_before_the_last_comma():
    line = sidecar_check.make_row(0, 1000, 1203311, 1180002, 0, 4127, 61234)
    body = b"0,1000,1203311,1180002,0,4127,61234"
    assert line == body + b"," + f"{__import__('zlib').crc32(body):08x}".encode() + b"\n"


@pytest.mark.parametrize(("damage", "reason"), [
    (lambda row: row[:-3] + (b"0" if row[-3:-2] != b"0" else b"1") + row[-2:], "crc_mismatch"),
    (lambda row: row.replace(b"0,1000,", b"0,01000,", 1), "crc_mismatch"),
])
def test_sidecar_reader_stops_at_a_bad_row(damage, reason):
    good = sidecar_check.make_row(0, 1000, 5, 4, 0, 10, 20)
    data = HEADER.encode() + damage(good) + sidecar_check.make_row(1, 1001, 6, 5, 0, 30, 20)
    sidecar = sidecar_check.parse(data)
    assert sidecar.rows == [] and sidecar.bad_row == reason


def test_sidecar_reader_refuses_a_non_canonical_integer():
    body = b"0,01000,5,4,0,10,20,"
    line = body + sidecar_check.row_crc(body + b"x").encode() + b"\n"
    sidecar = sidecar_check.parse(HEADER.encode() + line)
    assert sidecar.rows == [] and "SFF-701" in sidecar.bad_row


def test_sidecar_reader_counts_a_torn_last_line():
    row = sidecar_check.make_row(0, 1000, 5, 4, 0, 10, 20)
    sidecar = sidecar_check.parse(HEADER.encode() + row + row[:7])
    assert len(sidecar.rows) == 1 and sidecar.torn_bytes == 7 and sidecar.end is None


def test_sidecar_reader_refuses_a_byte_order_mark_and_cr():
    with pytest.raises(ValueError):
        sidecar_check.parse(b"\xef\xbb\xbf" + HEADER.encode())
    with pytest.raises(ValueError):
        sidecar_check.parse(HEADER.replace("\n", "\r\n").encode())


def test_expected_flags_follow_7_1_and_7_2():
    f = sidecar_check.expected_flags
    assert f(None, 5, False) == 0 and f(5, 6, False) == 0 and f(5, 8, False) == 1
    assert f(5, 5, False) == 8 and f(5, None, True) == 16 and f(None, 7, True) == 16 and f(5, 9, True) == 17


# ---------------------------------------------------------------------------
# The spec rules of rec_api
# ---------------------------------------------------------------------------

def test_key_label_time_and_queue_rules():
    key = camera_key("0a1b")
    assert key.startswith("0a1b") and len(key) == 16 and key == key.lower()
    assert camera_label("0a1b") == key[:6]
    assert block_time_ms(1, 30000, 1001) == 33 and block_time_ms(3, 30000, 1001) == 100
    assert (queue_size(30, 1), queue_size(30000, 1001), queue_size(60, 1)) == (90, 90, 180)


# ---------------------------------------------------------------------------
# The fake disk
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("code", [errno.ENOSPC, errno.EFBIG, errno.EIO])
def test_fake_disk_raises_at_the_chosen_write(disk, tmp_path, code):
    disk.fail(".csv", after=2, errno_code=code)
    with open(tmp_path / "a.csv", "xb", buffering=0) as handle:
        handle.write(b"1\n")
        handle.write(b"2\n")
        with pytest.raises(OSError) as raised:
            handle.write(b"3\n")
        assert raised.value.errno == code
        with pytest.raises(OSError):
            handle.write(b"4\n")
    assert (tmp_path / "a.csv").read_bytes() == b"1\n2\n"


def test_fake_disk_counts_only_rows_when_asked(disk, tmp_path):
    disk.fail(".csv", after=1, row_only=True)
    with open(tmp_path / "a.csv", "xb", buffering=0) as handle:
        handle.write(b"# header\n")
        handle.write(b"0,row\n")
        handle.write(b"# another header\n")
        with pytest.raises(OSError):
            handle.write(b"1,row\n")


def test_fake_disk_stalls_and_holds(disk, tmp_path):
    disk.stall(".mkv", 0.3, after=1)
    with open(tmp_path / "a.mkv", "xb", buffering=0) as handle:
        handle.write(b"a")
        started = time.monotonic()
        handle.write(b"b")
        assert time.monotonic() - started >= 0.29
        rule = disk.hold(".mkv")
        done = threading.Event()
        threading.Thread(target=lambda: (handle.write(b"c"), done.set()), daemon=True).start()
        assert disk.wait_holding(rule, 5.0) and not done.wait(0.3)
        rule.release.set()
        assert done.wait(5.0)
    assert (tmp_path / "a.mkv").read_bytes() == b"abc"


def test_fake_disk_traces_fsync_replace_and_lock(disk, tmp_path):
    import os

    (tmp_path / ".processing.lock").write_bytes(b"")
    with open(tmp_path / ".processing.lock", "r+b") as lock:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    with open(tmp_path / "m.json.tmp", "wb") as handle:
        handle.write(b"{}")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path / "m.json.tmp", tmp_path / "m.json")
    names = [e for e, _ in disk.trace("lock", "unlock", "fsync", "replace")]
    assert names == ["lock", "unlock", "fsync", "replace"]
    assert disk.trace("replace") == [("replace", "m.json")]


def test_fake_disk_wraps_a_pyav_writer_and_a_write_error_reaches_pyav(disk, tmp_path):
    frames = [jpeg_tools.synthetic_jpeg(k, 64, 48) for k in range(3)]
    pyav_mkv(tmp_path / "ok.mkv", frames)
    assert ebml.payloads(tmp_path / "ok.mkv") == frames
    assert disk.events_of("write", ".mkv")
    disk.fail(".mkv", after=len(disk.events_of("write", ".mkv")) + 2)
    with pytest.raises(Exception):  # noqa: B017 - PyAV raises its own error class for a failed write
        pyav_mkv(tmp_path / "bad.mkv", frames * 20)


# ---------------------------------------------------------------------------
# The child process helper
# ---------------------------------------------------------------------------

def test_child_ends_inside_a_chosen_write(children, tmp_path):
    rules = [{"kind": ".csv", "action": "exit", "after": 2, "partial": True, "row_only": True}]
    child = children({"mode": "selftest", "root": str(tmp_path), "rules": rules})
    child.expect("started")
    child.send("open", path=str(tmp_path / "a.csv"))
    child.expect("opened")
    child.send("write", lines=5)
    assert child.wait(30) == 9
    assert (tmp_path / "a.csv").read_bytes() == b"0,line\n1,line\n2,l"


def test_child_is_killed_at_a_chosen_point(children, tmp_path):
    child = children({"mode": "selftest", "root": str(tmp_path), "rules": []})
    child.expect("started")
    child.send("open", path=str(tmp_path / "b.csv"))
    child.expect("opened")
    child.send("write", lines=1)
    child.expect("wrote")
    assert child.kill() != 0
    assert (tmp_path / "b.csv").read_bytes() == b"0,line\n"


def try_lock(path):
    handle = open(path, "r+b")
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return True
    except OSError:
        return False
    finally:
        handle.close()


def test_lock_child_holds_the_lock_of_6_8(children, tmp_path):
    path = tmp_path / ".processing.lock"
    path.write_bytes(b"")
    child = children({"mode": "lock", "path": str(path), "hold_s": 30.0})
    child.expect("locked")
    assert not try_lock(path)
    child.send("release")
    child.expect("released")
    assert try_lock(path)

