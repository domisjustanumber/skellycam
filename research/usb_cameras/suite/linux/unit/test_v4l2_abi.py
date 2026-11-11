"""V4L2 ABI tables and the UVCH metadata parser (pure functions; run anywhere ctypes does)."""
import struct

import v4l2


def test_struct_sizes_offsets_ioctls():
    st = v4l2.selftest()
    assert st["ok"], st["problems"]


def test_fourcc_and_ids():
    assert v4l2.fourcc_str(v4l2.PIX_FMT_MJPEG) == "MJPG"
    assert v4l2.META_FMT_UVC == 0x48435655
    assert v4l2.CID["exposure_time_absolute"] == 0x009A0902
    assert v4l2.CID["white_balance_temperature"] == 0x0098091A
    assert v4l2.CID["focus_automatic_continuous"] == 0x009A090C
    assert v4l2.CID_NAME[0x00980913] == "gain"


def _blk(ns, sof, flags, pts=None, stc=None, dsof=None, length=None):
    body = b""
    if pts is not None:
        body += struct.pack("<I", pts)
    if stc is not None:
        body += struct.pack("<IH", stc, dsof)
    std = 2 + len(body)
    return struct.pack("<QHBB", ns, sof, length if length is not None else std, flags) + body


def test_parse_uvc_meta_blocks():
    f = v4l2.UVC_STREAM_PTS | v4l2.UVC_STREAM_SCR
    data = (_blk(1000, 10, f, pts=111, stc=222, dsof=0x7FF | 0x800) + _blk(2000, 11, f | v4l2.UVC_STREAM_EOF,
                                                                          pts=111, stc=333, dsof=5, length=14)
            + _blk(3000, 12, v4l2.UVC_STREAM_SCR, stc=444, dsof=6))
    blocks, an = v4l2.parse_uvc_meta(data)
    assert [b["ns"] for b in blocks] == [1000, 2000, 3000]
    assert blocks[0]["pts"] == 111 and blocks[0]["stc"] == 222 and blocks[0]["dev_sof"] == 0x7FF  # 11-bit SOF
    assert blocks[2]["pts"] is None and blocks[2]["stc"] == 444
    assert an["length_ne_std"] == 1 and an["truncated"] == 0


def test_parse_uvc_meta_truncated():
    f = v4l2.UVC_STREAM_PTS | v4l2.UVC_STREAM_SCR
    data = _blk(1, 1, f, pts=1, stc=2, dsof=3)
    blocks, an = v4l2.parse_uvc_meta(data[:-3])
    assert blocks == [] and an["truncated"] == 1


def test_decode_flags():
    d = v4l2.decode_buf_flags(0x2000 | 0x10000 | 0x40 | 0x1)
    assert d["ts_type"] == "MONOTONIC" and d["ts_src"] == "SOE" and d["error"] and "MAPPED" in d["names"]


def test_query_ext_ctrls_walks_past_a_failing_control(monkeypatch):
    """A control whose GET_INFO/MIN/MAX fails (EPIPE: the Kiyo symptom) must not end the walk: the remaining
    standard ids are probed one by one and the NEXT_CTRL walk resumes after them."""
    import errno
    import types
    ok_ids = [0x00980900, 0x009A0902, 0x009A090A]
    bad = 0x00980913

    def fake_ioctl(fd, req, arg, mutate=True):
        if req == v4l2.VIDIOC_QUERYMENU:
            raise OSError(errno.EINVAL, "no menu")
        assert req == v4l2.VIDIOC_QUERY_EXT_CTRL
        raw = arg.id
        nxt = raw & (v4l2.CTRL_FLAG_NEXT_CTRL | v4l2.CTRL_FLAG_NEXT_COMPOUND)
        cid = raw & ~(v4l2.CTRL_FLAG_NEXT_CTRL | v4l2.CTRL_FLAG_NEXT_COMPOUND) & 0xFFFFFFFF
        allids = sorted(ok_ids + [bad])
        if nxt:
            later = [x for x in allids if x > cid]
            if not later:
                raise OSError(errno.EINVAL, "end")
            cid = later[0]
        elif cid not in allids:
            raise OSError(errno.EINVAL, "no such control")
        if cid == bad:
            raise OSError(errno.EPIPE, "stall")
        arg.id, arg.type, arg.minimum, arg.maximum, arg.step = cid, 1, 0, 100, 1
        arg.name = b"ctrl"
        return 0

    monkeypatch.setattr(v4l2, "fcntl", types.SimpleNamespace(ioctl=fake_ioctl))
    d = v4l2.Device.__new__(v4l2.Device)
    d.fd, d.path = -1, "/dev/null"
    calls = []
    out = d.query_ext_ctrls(menus=False, progress=calls.append)
    got = [c["id"] for c in out if c.get("id") is not None]
    assert got == ok_ids
    errs = [c for c in out if c.get("query_errno")]
    assert errs and errs[0]["query_errno"] == "EPIPE"
    assert any(c.get("probe_id") == f"0x{bad:08x}" for c in errs)   # the failing id is named by the probe
    assert len(calls) >= len(ok_ids)                                  # watchdog re-armed per query
