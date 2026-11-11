"""Offline tests for pymf (pure-Python MF probe) and W-PYMF. NO camera is opened and no camera is enumerated.

    uv run --isolated --python 3.12 --no-project --with pytest --with comtypes --with pillow \\
        pytest research/usb_cameras/suite/windows/tests/test_pymf_offline.py

Layers:
1. pure parsing (any OS): the KSCAMERA_METADATA_ITEMHEADER / KSSTREAM_UVC_METADATA walk on synthetic buffers, JPEG
   checks, native-type selection (never the synthesized NV12), device matching, control tables, KS member lists;
2. W-PYMF analysis (any OS): format / control / capture / cycle comparisons, the equivalence rating, the 720-line
   mode scope, --reanalyze on a synthetic run folder;
3. COM declarations (Windows + comtypes): every hand-declared vtable against the SDK 10.0.22621 reference extracted
   from the headers, IIDs and GUID values, struct sizes;
4. COM objects without a camera (Windows + comtypes): the capture-metadata path through real MF samples and
   attribute stores, the Python IMFSourceReaderCallback called through its vtable, bounded-call timeouts;
5. the CLI end to end on a generated MJPEG AVI (Windows + comtypes + pillow; ``--url``, a file source): formats,
   capture (byte-exact saves, frames.jsonl keys equal to a real wincam row), cycle, usage errors.
What only a camera can test (Kiyo hangs, IAM / KS control calls, MFEnumDeviceSources, ActivateObject, real UVC
metadata, CPU and latency against wincam) is W-PYMF itself.
"""
from __future__ import annotations

import ctypes
import json
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
WIN = HERE.parent
SUITE = WIN.parent
for p in (str(SUITE), str(WIN), str(WIN / "helpers"), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

from pymf import parse as P  # noqa: E402

import w_pymf as W  # noqa: E402

REF = json.loads((WIN / "pymf" / "sdk_10.0.22621_reference.json").read_text(encoding="utf-8"))
STORED = SUITE.parent / "results" / "windows" / "Gerald" / "suite_20261106T224912Z"
IS_WIN = sys.platform == "win32"
#: one real wincam capture row (C922 1280x720@30, 2026-11-06 suite_20261106T224912Z W-CTRL-EFFECT): key fixture
WINCAM_ROW = {"seq": 0, "qpc_ns": 33172012663500, "sample_time_100ns": 331720107518, "sample_duration": 333333,
              "readsample_ts_100ns": 331720107518, "flags": 0, "discontinuity": True, "bytes": 86082, "soi": True,
              "eoi": True, "eoi_trailing_bytes": 0, "sof0_w": 1280, "sof0_h": 720, "uvc_pts": 1081605520,
              "uvc_scr_stc": 1091544920, "uvc_scr_sof": 350, "uvc_eof_pts": 1081605520, "uvc_eof_scr_stc": 1093168920,
              "uvc_eof_scr_sof": 355, "has_metadata": True, "capture_metadata_attr": True,
              "mf_device_timestamp": 331720107518, "mjpeg_offset": 0, "mjpeg_len": 86082}


def _comtypes():
    if not IS_WIN:
        pytest.skip("Windows only")
    return pytest.importorskip("comtypes")


# ============================================================================================================ 1. parse
def test_uvc_meta_single_item():
    b = P.build_uvc_item(pts=1000, stc=2000, sof=0x1234, eof_pts=1001, eof_stc=2100, eof_sof=0x7FF)
    u = P.parse_uvc_meta(b)
    assert u["present"] and u["items"] == 1 and u["raw_len"] == 8 + 32
    assert (u["pts"], u["stc"], u["eof_pts"], u["eof_stc"]) == (1000, 2000, 1001, 2100)
    assert u["sof"] == 0x1234 & 0x7FF and u["eof_sof"] == 0x7FF       # 11-bit SOF counter of SCRToken


def test_uvc_meta_after_other_items_and_reserved_bits():
    other = struct.pack("<II", 0x80000001, 8 + 12) + b"\xAA" * 12          # a custom item first
    uvc = P.build_uvc_item(pts=0xFFFFFFFF, stc=5, sof=0xF800 | 7, extra=8)  # reserved bits set, padded payload
    u = P.parse_uvc_meta(other + uvc)
    assert u["present"] and u["items"] == 2 and u["pts"] == 0xFFFFFFFF and u["sof"] == 7


def test_uvc_meta_stops_on_bad_sizes():
    good = P.build_uvc_item(1, 2, 3)
    assert not P.parse_uvc_meta(good[:-1])["present"]                       # Size > remaining: stop
    assert P.parse_uvc_meta(struct.pack("<II", 2, 4) + good)["items"] == 0  # Size < header: stop at once
    small = struct.pack("<II", 2, 8 + 16) + b"\0" * 16                       # UVC id but too short for the struct
    u = P.parse_uvc_meta(small)
    assert u["items"] == 1 and not u["present"]
    assert not P.parse_uvc_meta(b"")["present"]


def test_uvc_meta_matches_c_layout():
    """KSSTREAM_UVC_METADATATYPE_TIMESTAMP = ULONG PTS, ULONG SCR, USHORT SCRToken, USHORT Reserved0, ULONG
    Reserved1 (ks.h); the item is KSCAMERA_METADATA_ITEMHEADER {MetadataId, Size} + 2 timestamps."""
    assert P.ITEMHEADER_SIZE == 8 and P.UVC_TS_SIZE == 16 and P.UVC_METADATA_SIZE == 32
    b = P.build_uvc_item(11, 22, 33, 44, 55, 66)
    assert struct.unpack_from("<IIIIHHIIIHHI", b) == (2, 40, 11, 22, 33, 0, 0, 44, 55, 66, 0, 0)


def _jpeg(w=1280, h=720, sof=0xC0, tail=b"", app=b""):
    hdr = b"\xff\xd8" + app + b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    hdr += b"\xff\xdb\x00\x43\x00" + bytes(64)
    hdr += bytes([0xFF, sof, 0, 17, 8]) + struct.pack(">HH", h, w) + b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    hdr += b"\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00"
    return hdr + b"\x12\x34\xff\x00\x56" + b"\xff\xd9" + tail


def test_jpeg_info_basic_and_trailing():
    j = P.jpeg_info(_jpeg())
    assert j["soi"] and j["eoi"] and j["eoi_trailing"] == 0 and (j["sof_w"], j["sof_h"], j["sof_marker"]) == (1280, 720, 0xC0)
    j = P.jpeg_info(_jpeg(tail=b"\0\0\0"))
    assert not j["eoi"] and j["eoi_trailing"] == 3
    j = P.jpeg_info(_jpeg()[:-2])
    assert not j["eoi"] and j["eoi_trailing"] == -1
    assert P.jpeg_info(_jpeg(sof=0xC2))["sof_marker"] == 0xC2
    assert not P.jpeg_info(b"\x00\x01")["soi"]


def test_jpeg_info_eoi_search_window_is_last_4kb():
    far = _jpeg(tail=b"\0" * 5000)
    assert P.jpeg_info(far)["eoi_trailing"] == -1
    near = _jpeg(tail=b"\0" * 4000)
    assert P.jpeg_info(near)["eoi_trailing"] == 4000


def _types():
    """C922-like MF list: synthesized NV12 right before each MJPG type, plus YUY2."""
    out, i = [], 0
    for (w, h, fn, fd) in ((640, 480, 30, 1), (1280, 720, 30, 1), (1280, 720, 24, 1), (1280, 720, 60, 1),
                           (1920, 1080, 30, 1)):
        for sg in (P.NV12_GUID, P.MJPG_GUID):
            out.append({"type_index": i, "subtype_guid": sg, "subtype": P.subtype_text(sg), "width": w, "height": h,
                        "fps_num": fn, "fps_den": fd})
            i += 1
    out.append({"type_index": i, "subtype_guid": "32595559" + P.FOURCC_BASE_SUFFIX, "subtype": "YUY2", "width": 1280,
                "height": 720, "fps_num": 10, "fps_den": 1})
    return out


def test_select_native_type_never_first_match():
    ts = _types()
    idx, cands = P.select_native_type(ts, P.MJPG_GUID, 1280, 720, 30.0)
    assert idx == 3 and ts[idx]["subtype"] == "MJPG"              # index 2 is the NV12 of the same mode
    assert cands == ["30/1", "24/1", "60/1"]
    assert P.select_native_type(ts, P.MJPG_GUID, 1280, 720, 29.97)[0] == 3
    assert P.select_native_type(ts, P.MJPG_GUID, 1280, 720, 59.94)[0] == 7
    assert P.select_native_type(ts, P.MJPG_GUID, 1280, 720, 15.0)[0] is None     # nothing within 0.5 fps
    assert P.select_native_type(ts, P.MJPG_GUID, 800, 600, 30.0) == (None, [])


def test_flag_types_and_sizes():
    ts = P.flag_types(_types())
    assert all(t["flags"] for t in ts if t["subtype"] == "NV12")
    assert not any(t["flags"] for t in ts if t["subtype"] != "NV12")
    sizes = P.mjpg_sizes(ts)
    assert sizes[1] == {"width": 1280, "height": 720, "fps": [30.0, 24.0, 60.0]}
    assert P.subtype_counts(ts) == {"MJPG": 5, "NV12": 5, "YUY2": 1}


def test_subtype_text_and_guid():
    assert P.subtype_text(P.MJPG_GUID) == "MJPG" and P.subtype_guid_text("mjpg") == P.MJPG_GUID
    assert P.subtype_text("3F40F4F0-5622-4FF8-B6D8-A17A584BEE5E") == "MFVideoFormat_H264_ES"
    assert P.fourcc_of(21) == "D3DFMT_21"
    assert P.subtype_guid_text("MJPEG") is None


LINK_MF = r"\\?\usb#vid_046d&pid_085c&mi_00#7&2b1c3c2&0&0000#{e5323777-f976-4f5b-9b55-b94699c46e44}\global"
LINK_DS = r"\\?\usb#vid_046d&pid_085c&mi_00#7&2b1c3c2&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"


def test_links_and_matching():
    assert P.norm_link(LINK_MF) == P.norm_link(LINK_DS) == r"usb#vid_046d&pid_085c&mi_00#7&2b1c3c2&0&0000\global"
    assert P.parse_usb_ids(LINK_MF) == {"vid": "046d", "pid": "085c", "mi": "00", "instance": "7&2b1c3c2&0&0000"}
    cands = [(LINK_MF, "C922 Pro Stream Webcam"), (LINK_MF.replace("085c", "0843").replace("2b1c", "9999"),
                                                    "Logitech Webcam C930e")]
    assert P.match_device(LINK_MF.upper(), cands) == (0, [])                 # exact, case-insensitive
    assert P.match_device(LINK_DS, cands) == (0, [])                         # DS path finds the MF symlink
    assert P.match_device("c930e", cands)[0] == 1                           # friendly name
    idx, amb = P.match_device("vid_046d", cands)
    assert idx == -2 and len(amb) == 2
    assert P.match_device("nothing", cands) == (-1, [])


def test_controls_tables():
    assert P.find_ctl("exposure") == (0, 4, "exposure") and P.find_ctl("wb") == (1, 7, "white_balance")
    assert P.find_ctl("pa9") == (1, 9, "gain") and P.find_ctl("cc.focus") == (0, 6, "focus")
    assert P.find_ctl("ae_priority") == (0, 19, "auto_exposure_priority") and P.find_ctl("nope") is None
    s = P.parse_sets("exposure=-6,focus=auto,gain=manual", 2)
    assert [(x["def"][2], x["value"], x["flags"], x["is_auto"], x["is_manual_keep"]) for x in s] == \
        [("exposure", -6, 2, False, False), ("focus", 0, 1, True, False), ("gain", 0, 2, False, True)]
    with pytest.raises(ValueError):
        P.parse_sets("exposure")
    with pytest.raises(ValueError):
        P.parse_sets("bogus=1")
    assert P.flags_names(0x13) == ["auto", "manual", "relative"]
    assert len(P.CTLS) == 40


def _ks_desc(members: list[tuple[int, int, int, int, bytes]]) -> bytes:
    body = b"".join(struct.pack("<IIII", f, s, c, fl) + data for f, s, c, fl, data in members)
    size = 40 + len(body)
    return struct.pack("<II", 3, size) + bytes(24) + struct.pack("<II", len(members), 0) + body


def test_ks_parse_members():
    rng = struct.pack("<IIii", 1, 0, -13, -1)
    buf = _ks_desc([(P.KSPROPERTY_MEMBER_STEPPEDRANGES, 16, 1, 0, rng),
                    (P.KSPROPERTY_MEMBER_VALUES, 4, 1, P.KSPROPERTY_MEMBER_FLAG_DEFAULT, struct.pack("<i", -6))])
    r = P.ks_parse_members(buf, False)
    assert (r["has_range"], r["min"], r["max"], r["step"]) == (True, -13, -1, 1)
    assert (r["has_default"], r["default"]) == (True, -6)
    assert not P.ks_parse_members(buf, True)["has_range"]                  # defaults pass never sets the range
    assert P.ks_parse_members(buf[:30], False)["ranges"] == []
    assert P.ks_parse_members(buf[:60], False)["ranges"] == []             # truncated member list: stop


def test_ctl_json_keys_match_wincam():
    r = P.new_ctl_read()
    r.update(supported=True, via="IAMCameraControl", has_range=True, has_default=True, has_value=True, mn=-13, mx=-1,
             step=1, caps=3, val=-6, flags=1, hr_iam_range=0, hr_iam_get=0, hr_ks_basic=0, hr_ks_default=0,
             ks_has_range=True, ks_mn=-13, ks_mx=-1, ks_step=1, ks_ranges=[{"min": -13, "max": -1, "step": 1}])
    r["def"] = -6
    e = P.ctl_json((0, 4, "exposure"), r, 1.0)
    want = ['set', 'id', 'name', 'key', 'supported', 'via', 'min', 'max', 'step', 'default', 'caps_flags',
            'caps_flags_names', 'value', 'flags', 'flags_names', 'ks_ranges', 'ks_basicsupport', 'iam_ks_range_agree',
            'hr', 'hr_names', 'call_ms', 'get_ok', 'get_hr', 'get_hr_name']
    assert list(e.keys()) == want
    assert e["get_hr"] == "0x00000000" and e["iam_ks_range_agree"] is True and e["hr"]["ks_get"] is None
    p = STORED / "W-CTRL-LIST" / "c922_pro_stream_webcam_046d-085c_controls_mf.json"
    if p.exists():
        real = json.loads(p.read_text(encoding="utf-8"))
        exp = next(c for c in real["controls"] if c.get("name") == "exposure")
        assert list(exp.keys()) == want


def test_get_health_and_error_class():
    ok = {"supported": True, "name": "exposure", "key": "cc.exposure", "get_ok": True}
    bad = {"supported": True, "name": "gain", "key": "pa.gain", "get_ok": False, "get_hr": "0x8007001F"}
    fl = {"supported": True, "name": "focal_length", "key": "cc.focal_length", "get_ok": True}
    g = P.get_health([bad, fl])
    assert g["device_not_answering"] and g["first_fail_hr"] == 0x8007001F and g["get_failed_controls"] == ["pa.gain"]
    assert not P.get_health([ok, bad])["device_not_answering"]
    assert P.error_class(0x8007001F, False)[0] == "device_error"
    assert P.error_class(0x800718CF, False)[0] == "bandwidth_certain"
    assert P.error_class(None, True)[0] == "timeout"
    assert P.hr_name(-2147024865) == "HRESULT_FROM_WIN32(ERROR_GEN_FAILURE)"   # signed int as ctypes gives it


def test_pct_matches_wincam():
    assert P.pct([], 50) != P.pct([], 50)     # NaN
    assert P.pct([1, 2, 3, 4], 50) == 2.5 and P.pct([5], 95) == 5


# ============================================================================================================ 2. W-PYMF
def _fmt_doc(types=None):
    ts = P.flag_types(types or _types())
    rows = []
    for t in ts:
        rows.append({"stream_index": 0, "type_index": t["type_index"], "subtype": t["subtype"],
                     "subtype_guid": t["subtype_guid"], "width": t["width"], "height": t["height"],
                     "fps_num": t["fps_num"], "fps_den": t["fps_den"], "fps": t["fps_num"] / t["fps_den"],
                     "flags": t["flags"], "major_type": "MFMediaType_Video"})
    return {"streams": [{"stream_index": 0, "stream_identifier": 0, "major_type": "MFMediaType_Video",
                         "handler_type_count": len(rows), "attributes": {"MF_DEVICESTREAM_STREAM_ID": 0}}],
            "reader_streams": [{"stream_index": 0, "types": rows}], "stream_started": False}


def test_compare_formats():
    a = _fmt_doc()
    c = W.compare_formats(a, json.loads(json.dumps(a)))
    assert c["equal"] and c["n_pymf"] == 11 and c["pymf_synthesized_flagged"] == 5
    b = json.loads(json.dumps(a))
    b["reader_streams"][0]["types"].pop(3)
    c = W.compare_formats(a, b)
    assert not c["equal"] and c["only_wincam"] and not c["only_pymf"]
    b = json.loads(json.dumps(a))
    b["reader_streams"][0]["types"][2]["flags"] = []                       # NV12 not flagged by pymf
    assert not W.compare_formats(a, b)["equal"]
    assert W.compare_formats(a, None)["equal"] is None


def test_compare_formats_on_stored_wincam_output():
    p = STORED / "W-FMT" / "c922_pro_stream_webcam_046d-085c_formats_mf.json"
    if not p.exists():
        pytest.skip("stored W-FMT output not present")
    d = json.loads(p.read_text(encoding="utf-8"))
    c = W.compare_formats(d, json.loads(json.dumps(d)))
    assert c["equal"] and c["n_wincam"] > 100 and c["pymf_synthesized_flagged"] > 50


def _ctl_doc(exposure_value=-6, exposure_flags=2, gain_max=255):
    return {"supported_count": 2, "device_not_answering": False, "interfaces": {"IAMCameraControl": True},
            "controls": [
                {"key": "cc.exposure", "name": "exposure", "supported": True, "via": "IAMCameraControl", "min": -11,
                 "max": -2, "step": 1, "default": -5, "caps_flags": 3, "flags": exposure_flags,
                 "value": exposure_value, "get_ok": True, "ks_basicsupport": {"min": -11, "max": -2, "step": 1}},
                {"key": "pa.gain", "name": "gain", "supported": True, "via": "IAMVideoProcAmp", "min": 0,
                 "max": gain_max, "step": 1, "default": 0, "caps_flags": 2, "flags": 2, "value": 0, "get_ok": True,
                 "ks_basicsupport": {"min": 0, "max": gain_max, "step": 1}},
                {"key": "cc.pan", "name": "pan", "supported": False}]}


def test_compare_controls_and_auto_drift():
    assert W.compare_controls(_ctl_doc(), _ctl_doc())["equal"]
    c = W.compare_controls(_ctl_doc(-6, 1), _ctl_doc(-7, 1))              # auto exposure moved between reads
    assert c["equal"] and len(c["auto_drift"]) == 1
    c = W.compare_controls(_ctl_doc(-6, 2), _ctl_doc(-7, 2))              # manual value differs: a difference
    assert not c["equal"]
    c = W.compare_controls(_ctl_doc(), _ctl_doc(gain_max=100))
    assert not c["equal"] and {d["field"] for d in c["diffs"]} == {"max", "ks_basicsupport.max"}


def test_pick_set_values_and_roundtrip():
    before = _ctl_doc(-5, 1)                     # exposure in auto at its default value
    vals = W.pick_set_values(before)
    assert vals == {"exposure": -4, "gain": 1} or vals == {"exposure": -4}  # gain caps 2: manual-capable
    set_doc = {"exit_code": 0, "error": None,
               "sets": [{"control": "cc.exposure", "requested": "-4", "matches": True, "before_flags": 1}],
               "restore": [{"control": "cc.exposure", "restore_value": -5, "restore_flags": 1, "readback_value": -5,
                            "readback_flags": 1, "timed_out": False}]}
    rt = W.check_roundtrip(set_doc, before, _ctl_doc(-6, 1))   # auto: value may differ afterwards
    assert rt["ok"] and rt["as_found_after"][0]["as_found"]
    rt = W.check_roundtrip(set_doc, before, _ctl_doc(-4, 2))   # left in manual: not as found
    assert not rt["ok"]
    assert W.check_roundtrip(None, before, before)["ok"] is None


def _rows(n=150, fps=30.0, clock=1e7, meta=True, start=1_000_000_000_000):
    out = []
    for i in range(n):
        t = start + int(i * 1e9 / fps)
        r = {"seq": i, "qpc_ns": t, "has_metadata": meta, "capture_metadata_attr": meta}
        if meta:
            r.update(uvc_pts=(4_294_000_000 + int(i * clock / fps)) & 0xFFFFFFFF, uvc_scr_sof=(i * 33) % 2048)
        out.append(r)
    return out


def test_tier0_timing_comparison():
    """pymf's per-frame timing against wincam's: arrival delay off the sample-time grid (p99, std) and sample-time
    slots (the GIL / comtypes dispatch cost the probe exists to measure). Fine (unquantized) sample times here."""
    import random
    rnd = random.Random(1)

    def rows(jitter_ms, drop_every=0):
        out = []
        for i in range(150):
            if drop_every and i % drop_every == 0 and i:
                continue
            st = i * 333_333                                   # 100 ns units, 30 fps
            out.append({"seq": i, "sample_time_100ns": st,
                        "qpc_ns": 5_000_000_000 + st * 100 + int(rnd.uniform(0, jitter_ms) * 1e6)})
        return out
    w = {"timing": W.timing_stats(rows(0.5))}
    good = {"timing": W.timing_stats(rows(1.5))}
    bad = {"timing": W.timing_stats(rows(12.0, drop_every=10))}
    assert w["timing"]["sample_time_drops"] == 0 and bad["timing"]["sample_time_drops"] >= 10
    c = W.compare_timing(w, good)
    assert c["arrival_jitter_ok"] and c["offset_std_ok"] and c["drops_ok"]
    c = W.compare_timing(w, bad)
    assert c["arrival_jitter_ok"] is False and c["offset_std_ok"] is False and c["drops_ok"] is False
    m = {"capture": {"wincam": {"frames_total": 150}, "pymf": {"frames_total": 150}},
         "capture_compare": {"compared": True, "valid_ok": True, "fps_ok": True, "timing": c}}
    r = W.rate_camera(m)
    assert any("arrival jitter" in d for d in r["evidence"]["differences"])
    assert r["evidence"]["not_covered"] and "ONE Python process" in r["evidence"]["not_covered"][0]


def _grid_capture(n, seed, delay_ms=0.0, delay_every=0, drop_every=0):
    """A wincam-like MF capture on Windows' 16 ms host grid (Gerald 2026-11-06 W-TS): sample times on the grid
    (intervals 32 / 48 ms at 30 fps), arrival = sample time + 0.3-0.8 ms or + one grid step, in runs of frames
    (arrival minus sample time bimodal, the shares differ between windows)."""
    import random
    rnd = random.Random(seed)
    out, late = [], False
    for i in range(n):
        if i % 6 == 0:
            late = rnd.random() < 0.4
        if drop_every and i and i % drop_every == 0:
            continue
        true_ms = i * 1000.0 / 30.0 + rnd.uniform(0.0, 0.5)
        st_ms = (int(true_ms // 16.0) + 1) * 16.0
        arr_ms = st_ms + rnd.uniform(0.3, 0.8) + (16.0 if late else 0.0)
        if delay_every and i % delay_every == 0:
            arr_ms += delay_ms
        out.append({"seq": i, "sample_time_100ns": int(st_ms * 1e4), "qpc_ns": int(7e12 + arr_ms * 1e6)})
    return out


def test_tier0_timing_on_the_16ms_grid():
    """Two windows of the SAME wincam-like capture must pass every timing criterion (the old p99-p50 spread of
    arrival minus sample time was ~16 ms in every window, and '> 1.5 x median' counted every 48 ms sample-time
    interval as a drop); a few ms of extra delivery delay (a GIL wait) must still fail."""
    rows = _grid_capture(1200, seed=3)
    wins = [rows[k:k + 150] for k in range(0, 1200, 150)]
    stats = [W.timing_stats(x) for x in wins]
    for t in stats:
        a = t["arrival_minus_sample_ms"]
        assert a["grid_ms"] == 16.0 and len(a["modes"]) == 2 and a["offset_p99_ms"] < 1.0
        assert t["sample_time_drops"] == 0 and t["sample_time_slots"]["drops_detectable"] is True
    for a in range(len(wins)):
        for b in range(len(wins)):
            if a != b:
                c = W.compare_timing({"timing": stats[a]}, {"timing": stats[b]})
                assert c["arrival_jitter_ok"] and c["offset_std_ok"] and c["drops_ok"], (a, b, c)
    w = {"timing": stats[0]}
    gil = {"timing": W.timing_stats(_grid_capture(150, seed=4, delay_ms=4.0, delay_every=5))}
    c = W.compare_timing(w, gil)
    assert c["arrival_jitter_ok"] is False
    lost = {"timing": W.timing_stats(_grid_capture(150, seed=5, drop_every=10))}
    assert lost["timing"]["sample_time_drops"] >= 10
    assert W.compare_timing(w, lost)["drops_ok"] is False


def test_capture_stats_ignore_uvc_metadata():
    # tier 0 only (Dom 2026-11-09): W-PYMF neither summarises nor compares UVC PTS/SCR
    assert not hasattr(W, "metadata_stats")
    summ = {"ok": True, "frames": {"total": 150, "ok": 150}}
    with_md, without = W.capture_stats(summ, _rows(), None, None), W.capture_stats(summ, _rows(meta=False), None, None)
    assert "metadata" not in with_md and with_md == without


def _cap(fps=30.0, cpu=2.0, lat=900.0, sha="abc", valid=1.0, frames=150):
    return {"frames_total": frames, "valid_fraction": valid if frames else None, "fps_fit": fps if frames else None,
            "fps_measured": fps, "cpu_pct_of_one_core": cpu, "open_to_first_frame_ms": lat, "header_sha1": sha}


def _cyc(n=60, ok=60, p50=1000.0):
    rows = [{"i": i, "ok": i < ok, "first_frame_ms": p50, "open_to_first_frame_ms": p50, "close_ms": 300.0}
            for i in range(n)]
    from common import cycstats
    return cycstats.summarize_cycles(rows)


def _cam_m(**over):
    w, p = _cap(), _cap(cpu=3.5, lat=950.0)
    m = {"key": "k", "is_kiyo": False, "mode": "MJPG 1280x720@30",
         "list": {"in_wincam": True, "in_pymf": True, "name_equal": True},
         "formats_compare": W.compare_formats(_fmt_doc(), _fmt_doc()),
         "controls_compare": W.compare_controls(_ctl_doc(), _ctl_doc()),
         "set_roundtrip": {"ran": True, "ok": True, "sets": [1]},
         "capture": {"wincam": w, "pymf": p}, "capture_compare": W.compare_capture(w, p),
         "cycles": {"wincam": {"summary": _cyc()}, "pymf": {"summary": _cyc()}},
         "cycles_compare": W.compare_cycles(_cyc(), _cyc())}
    m.update(over)
    return m


def test_rate_camera_yes_and_no_metadata_criterion():
    r = W.rate_camera(_cam_m())
    assert r["rating"] == "yes"
    assert not any("tier-1" in c["criterion"] or "PTS" in c["criterion"] for c in r["criteria"])
    cmp_ = W.compare_capture(_cap(), _cap(cpu=3.0))
    assert not any(k.startswith("metadata") for k in cmp_)


def test_rate_camera_partial_no_and_untested():
    w, p = _cap(cpu=2.0), _cap(cpu=30.0, fps=27.0, sha="zzz")
    r = W.rate_camera(_cam_m(capture={"wincam": w, "pymf": p}, capture_compare=W.compare_capture(w, p)))
    assert r["rating"] == "partial" and len(r["evidence"]["differences"]) == 3
    w, p = _cap(), _cap(frames=0)
    r = W.rate_camera(_cam_m(capture={"wincam": w, "pymf": p}, capture_compare=W.compare_capture(w, p)))
    assert r["rating"] == "no"
    r = W.rate_camera(_cam_m(capture_untested="untested (scope): no 720-line mode", capture={}, capture_compare={},
                             cycles_untested="untested (scope)", cycles={}, cycles_compare={}))
    assert r["rating"] == "partial" and r["summary_label"] == "partial (capture, cycles untested)"
    r = W.rate_camera({"key": "k", "untested_reason": "camera has no MF symbolic link"})
    assert r["rating"] == "untested"


def test_compare_cycles_tolerances():
    assert W.compare_cycles(_cyc(), _cyc(p50=1100))["ok"]
    # per-cycle delivered rate (wincam 1.2 / pymf 0.2 rows): pymf must reach 90 % of wincam's p50
    assert W.compare_cycles(_cyc(), _cyc(), 29.5, 27.0)["fps_ok"] is True
    c = W.compare_cycles(_cyc(), _cyc(), 29.5, 20.0)
    assert c["fps_ok"] is False and not c["ok"]
    assert W.compare_cycles(_cyc(), _cyc(), None, 20.0)["fps_ok"] is None
    assert W.cycle_fps_p50([{"ok": True, "fps_measured": 29.0}, {"ok": False, "fps_measured": 5.0},
                            {"ok": True, "fps_measured": 31.0}, {"ok": True}]) == 30.0
    assert not W.compare_cycles(_cyc(), _cyc(ok=55))["ok"]                 # 91.7 % vs 100 %
    assert not W.compare_cycles(_cyc(p50=500), _cyc(p50=900))["ok"]        # +400 ms > max(150, 30 %)


def test_aggregate_worst_and_untested():
    a = W.aggregate({"a": {"rating": "yes"}, "b": {"rating": "partial", "evidence": {"differences": ["x"]}},
                     "c": {"rating": "untested"}})
    assert a["rating"] == "partial" and a["evidence"]["differences_by_criterion"] == {"x": ["b"]}
    assert W.aggregate({"c": {"rating": "untested"}})["rating"] == "untested"


def test_choose_mode_exactly_720_lines():
    import capkit as ck
    doc = _fmt_doc()
    ctx = SimpleNamespace(args=SimpleNamespace(min_fps=30.0, min_height=720, all_modes=False))
    mode, rec = W.choose_mode(ctx, doc)
    assert mode.text == "MJPG 1280x720@30" and "MJPG 1920x1080@30" not in rec["in_scope"]
    assert rec["in_scope"] == ["MJPG 1280x720@30", "MJPG 1280x720@60"]
    only1080 = _fmt_doc([t for t in _types() if t["height"] == 1080])
    assert W.choose_mode(ctx, only1080)[0] is None
    ctx.args.max_height = 0                                                # runner widened the scope: no top
    if hasattr(__import__("common.modescope", fromlist=["Scope"]).Scope, "max_height"):
        assert W.choose_mode(ctx, only1080)[0].text == "MJPG 1920x1080@30"
    assert isinstance(ck.mjpeg_modes(doc)[0], ck.Mode)


def test_knobs_and_estimate(monkeypatch):
    ctx = SimpleNamespace(args=SimpleNamespace(quick=False), cameras=[{"is_kiyo": True}, {"is_kiyo": False}])
    assert W.n_cycles(ctx) == 60 and W.capture_seconds(ctx) == 5.0
    ctx.args.quick = True
    assert W.n_cycles(ctx) == 6
    monkeypatch.setenv("SKELLYCAM_PYMF_CYCLES", "400")
    assert W.n_cycles(ctx) == 400
    ctx.args.pymf_cycles = 381
    assert W.n_cycles(ctx) == 381
    assert W.estimate_s(ctx) > 381 * 2 * 2.6
    assert W.INFO["id"] == "W-PYMF" and W.INFO["module"] == "tests.w_pymf"


def test_reanalyze_synthetic_run(tmp_path):
    cam = {"key": "046d:085c:sn=X", "name": "C922 Pro Stream Webcam", "vid": "046d", "pid": "085c", "serial": "X",
           "mf_symlink": LINK_MF}
    slug = __import__("capkit").cam_slug(cam)
    td = tmp_path / "W-PYMF"
    td.mkdir()
    for tool in ("wincam", "pymf"):
        (td / f"{slug}_{tool}_formats.json").write_text(json.dumps(_fmt_doc()), encoding="utf-8")
        (td / f"{slug}_{tool}_controls.json").write_text(json.dumps(_ctl_doc()), encoding="utf-8")
        (td / f"{slug}_{tool}_cycles.jsonl").write_text(
            "".join(json.dumps({"i": i, "ok": True, "first_frame_ms": 900, "open_to_first_frame_ms": 950}) + "\n"
                    for i in range(10)), encoding="utf-8")
        (td / f"{tool}_list.json").write_text(json.dumps({"mf": {"devices": [
            {"index": 0, "friendly_name": cam["name"], "symlink": LINK_MF}]}}), encoding="utf-8")
    m = _cam_m()
    m.pop("formats_compare")
    doc = {"test": "W-PYMF", "cameras": [cam], "measurements": {"cameras": {cam["key"]: m}}}
    (tmp_path / "W-PYMF.json").write_text(json.dumps(doc), encoding="utf-8")
    new = W.reanalyze(tmp_path)
    assert new["camera_opened"] is False
    assert new["verdicts"][f"pymf_equivalence|{cam['key']}|pymf"]["rating"] == "yes"
    # overall capped while pymf cannot set controls on a streaming source (NOT_COVERED, 2026-11-09)
    assert new["verdicts"]["pymf_equivalence"]["rating"] == "partial"
    assert new["verdicts"]["pymf_equivalence"]["summary_label"] == W.STREAMING_SET_CAP
    assert new["verdicts"][f"reliability|{cam['key']}|pymf_inproc"]["rating"] in ("yes", "partial")
    assert (tmp_path / "reanalysis" / "W-PYMF.json").exists()


def test_reanalyze_serialless_camera_uses_runtime_slug(tmp_path):
    """A camera with no serial gets its hub port in the run-time slug; the result's ``cameras`` summary must still
    find the files (the summary keeps hub_port, and the measurement keeps the slug)."""
    import capkit
    import suitectx
    full = {"key": "4c4a:4a55:port=2", "name": "USB Camera", "vid": "4c4a", "pid": "4a55", "serial": None,
            "hub_port": 2, "mf_symlink": LINK_MF}
    slug = capkit.cam_slug(full)
    assert slug.endswith("_2")
    summary = suitectx.camera_summary(full)
    assert capkit.cam_slug(summary) == slug
    td = tmp_path / "W-PYMF"
    td.mkdir()
    for tool in ("wincam", "pymf"):
        (td / f"{slug}_{tool}_formats.json").write_text(json.dumps(_fmt_doc()), encoding="utf-8")
    m = _cam_m()
    m.pop("formats_compare")
    m["slug"] = slug
    summary.pop("hub_port")                       # an older result without hub_port: the stored slug still works
    doc = {"test": "W-PYMF", "cameras": [summary], "measurements": {"cameras": {full["key"]: m}}}
    (tmp_path / "W-PYMF.json").write_text(json.dumps(doc), encoding="utf-8")
    new = W.reanalyze(tmp_path)
    assert new["measurements"]["cameras"][full["key"]]["formats_compare"]["compared"] is True


def test_list_compare():
    w = {"mf": {"devices": [{"index": 0, "friendly_name": "A", "symlink": LINK_MF}]}}
    c = W.compare_lists(w, w, [{"key": "k", "mf_symlink": LINK_MF}])
    assert c["sets_equal"] and c["per_camera"]["k"] == {"in_wincam": True, "in_pymf": True, "name_equal": True,
                                                        "order_equal": True}
    c = W.compare_lists(w, {"mf": {"devices": []}}, [{"key": "k", "mf_symlink": LINK_MF}])
    assert not c["sets_equal"] and c["per_camera"]["k"]["in_pymf"] is False


# ============================================================================================================ 3. vtables
def test_vtables_match_sdk_headers():
    _comtypes()
    from pymf import com as C
    names = {i.__name__ for i in C.INTERFACES}
    assert names == set(REF["interfaces"]), "every declared interface must be in the SDK reference (and vice versa)"
    for iface in C.INTERFACES:
        ref = REF["interfaces"][iface.__name__]
        own = [m[1] for m in iface.__dict__["_methods_"]]
        want = [m["name"] for m in ref["methods"]]
        assert own == want, f"{iface.__name__}: {own} != {want} ({ref['header']}:{ref['line']})"
        base = iface.__mro__[1].__name__
        assert base == ref["base"], f"{iface.__name__} base {base} != {ref['base']}"
        assert str(iface._iid_).upper().strip("{}") == ref["iid"], iface.__name__


def test_vtable_slot_counts():
    """Total vtable slots (IUnknown's 3 + every base's methods): catches a base declared with the wrong parent."""
    _comtypes()
    from pymf import com as C

    def slots(name):
        r = REF["interfaces"].get(name)
        return 3 if r is None else len(r["methods"]) + slots(r["base"])
    for iface in C.INTERFACES:
        n = 3 + sum(len(k.__dict__.get("_methods_", [])) for k in iface.__mro__ if k.__name__ in REF["interfaces"])
        assert n == slots(iface.__name__), iface.__name__
    assert slots("IMFActivate") == 36 and slots("IMFSample") == 47 and slots("IAMCameraControl") == 6


def test_guid_values_match_sdk_headers():
    _comtypes()
    from pymf import com as C
    for name, rec in REF["guids"].items():
        if hasattr(C, name):
            assert C.gtext(getattr(C, name)) == rec["guid"], f"{name} ({rec['header']}:{rec['line']})"
        if name in P.GUID_NAMES.values():
            g = next(k for k, v in P.GUID_NAMES.items() if v == name)
            assert g == rec["guid"], name
    assert C.gtext(C.IKsControl._iid_) == REF["interfaces"]["IKsControl"]["iid"]


def test_struct_sizes():
    _comtypes()
    import ctypes
    from pymf import com as C
    assert ctypes.sizeof(C.PROPVARIANT) == 24 and ctypes.sizeof(C.KSIDENTIFIER) == 24
    assert ctypes.alignment(C.KSIDENTIFIER) == 8
    for s in (C.KSPROPERTY_CAMERACONTROL_S, C.KSPROPERTY_CAMERACONTROL_S2, C.KSPROPERTY_CAMERACONTROL_FOCAL_LENGTH_S):
        assert ctypes.sizeof(s) == 40, s.__name__


# ============================================================================================================ 4. COM objects
@pytest.fixture(scope="module")
def mfstarted():
    _comtypes()
    from pymf import com as C
    assert C.MFStartup(C.MF_VERSION, 0) & 0xFFFFFFFF == 0
    yield C


def _mf_buffer(C, data: bytes):
    import ctypes
    from ctypes import byref, c_void_p
    raw = c_void_p()
    assert C.MFCreateMemoryBuffer(max(1, len(data)), byref(raw)) & 0xFFFFFFFF == 0
    b = C.own(raw, C.IMFMediaBuffer)
    p, mx, ln = c_void_p(), C.DWORD(), C.DWORD()
    b.Lock(byref(p), byref(mx), byref(ln))
    ctypes.memmove(p, data, len(data))
    b.Unlock()
    b.SetCurrentLength(len(data))
    return b


def _sample(C, jpeg: bytes, meta: bytes | None):
    from ctypes import byref, c_void_p
    raw = c_void_p()
    C.MFCreateSample(byref(raw))
    s = C.own(raw, C.IMFSample)
    s.SetSampleTime(1234567)
    s.SetSampleDuration(333333)
    b = _mf_buffer(C, jpeg)
    s.AddBuffer(b)
    C.release(b)
    if meta is not None:
        hr, md = C.new_attributes(1)
        mb = _mf_buffer(C, meta)
        assert md.SetUnknown(byref(C.MF_CAPTURE_METADATA_FRAME_RAWSTREAM), mb) & 0xFFFFFFFF == 0
        assert s.SetUnknown(byref(C.MFSampleExtension_CaptureMetadata), md) & 0xFFFFFFFF == 0
        C.release(mb)
        C.release(md)
    return s


def test_metadata_through_real_mf_objects(mfstarted, tmp_path):
    C = mfstarted
    from pymf import mf
    st = mf.StreamState(1280, 720)
    st.jsonl = open(tmp_path / "frames.jsonl", "w", encoding="utf-8")
    st.mjpeg = open(tmp_path / "frames.mjpeg", "wb")
    st.save_mode = 1
    jp = _jpeg()
    s = _sample(C, jp, P.build_uvc_item(1081605520, 1091544920, 350, 1081605520, 1093168920, 355))
    mf.process_sample(st, 42, 0, 1234567, s)
    s2 = _sample(C, jp, None)                                              # no tier-1 metadata: normal
    mf.process_sample(st, 43, 0, 1234568, s2)
    C.release(s)
    C.release(s2)
    st.jsonl.close()
    st.mjpeg.close()
    rows = [json.loads(x) for x in (tmp_path / "frames.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[0]["uvc_pts"] == 1081605520 and rows[0]["uvc_scr_sof"] == 350 and rows[0]["uvc_eof_scr_sof"] == 355
    assert rows[0]["has_metadata"] and rows[0]["capture_metadata_attr"]
    assert rows[1]["uvc_pts"] is None and not rows[1]["has_metadata"] and not rows[1]["capture_metadata_attr"]
    assert rows[0]["sample_time_100ns"] == 1234567 and rows[0]["sof0_w"] == 1280 and rows[0]["eoi"]
    assert st.ok_frames == 2 and st.with_meta == 1 and st.with_capmeta == 1
    assert (tmp_path / "frames.mjpeg").read_bytes() == jp + jp
    expected = set(WINCAM_ROW) - {"mf_device_timestamp"}                   # MF sets that one on camera samples only
    assert set(rows[0]) == expected


def test_callback_through_vtable(mfstarted):
    C = mfstarted
    from pymf import mf
    st = mf.StreamState(1280, 720)
    cb = mf.ReaderCallback(st)
    p = cb.QueryInterface(C.IMFSourceReaderCallback)
    s = _sample(C, _jpeg(), None)
    assert p.OnReadSample(0, 0, 0, 1234567, s) & 0xFFFFFFFF == 0           # C vtable -> Python implementation
    assert st.frames == 1 and st.ok_frames == 1 and st.first_ns > 0 and st.ev_sample.is_set()
    assert p.OnReadSample(0, 0, C.MF_SOURCE_READERF_STREAMTICK, 0, None) == 0
    assert st.ticks == 1 and st.nulls == 1
    assert p.OnFlush(0) == 0 and st.ev_flush.is_set()
    assert p.OnEvent(0, None) == 0
    assert p.OnReadSample(0x8007001F - (1 << 32), 0, 0, 0, None) == 0      # failed hrStatus: recorded, not raised
    assert st.err == 0x8007001F
    C.release(s)
    C.release(p)


def test_abandoned_call_keeps_its_own_com_reference(mfstarted):
    """mf.ref gives a bounded closure its own reference (wincam's by-value ComPtr capture): after the caller
    releases (and NULLs) its wrapper, an abandoned worker still inside a call keeps the object alive, and its call
    completes on a live object; the worker's reference is the last one and frees the object when it is released."""
    C = mfstarted
    from pymf import bounded, mf
    hr, a = C.new_attributes(1)
    assert hr == 0 and a
    gate, inside, seen = threading.Event(), threading.Event(), {}
    mine = mf.ref(a, C.IMFAttributes)
    a.AddRef()
    assert a.Release() == 2                                                # caller + worker

    def f(ctl):
        try:
            inside.set()
            gate.wait(2)                                                   # "hung" inside the call ...
            n = ctypes.c_uint()
            seen["hr"] = mine.GetCount(ctypes.byref(n)) & 0xFFFFFFFF       # ... then the call uses the object
            return seen["hr"]
        finally:
            seen["refs_left"] = C.release(mine)                            # the worker's reference was the last
    r = bounded.call(50, f)
    assert r.timed_out and inside.is_set()
    assert C.release(a) == 1                                               # the caller's cleanup: object still alive
    assert not a                                                           # its wrapper is NULLed in place
    gate.set()
    for _ in range(200):
        if not mine:
            break
        time.sleep(0.01)
    assert not mine                                                        # released by the worker after its call
    assert seen == {"hr": 0, "refs_left": 0}
    assert mf.ref(None, C.IMFAttributes) is None


def test_bounded_call_timeout_and_exception():
    _comtypes()
    from pymf import bounded
    n0 = bounded.abandoned_threads()
    r = bounded.call(50, lambda ctl: time.sleep(0.5) or 7)
    assert r.timed_out and r.value is None and r.ctl.abandoned and bounded.abandoned_threads() == n0 + 1
    r = bounded.call(2000, lambda ctl: 7)
    assert not r.timed_out and r.value == 7
    r = bounded.call(2000, lambda ctl: 1 / 0)
    assert r.value is None and "ZeroDivisionError" in r.exc


# ============================================================================================================ 5. CLI
def _avi(path: Path, w=320, h=240, fps=30, n=40) -> list[bytes]:
    """A minimal MJPEG AVI (RIFF AVI, one 'vids' MJPG stream, idx1) with distinct Pillow JPEG frames."""
    Image = pytest.importorskip("PIL.Image")
    import io

    def jpeg(i):
        b = io.BytesIO()
        Image.new("RGB", (w, h), ((i * 37) % 256, (i * 91) % 256, 128)).save(b, "JPEG", quality=80)
        return b.getvalue()

    def chunk(fcc, data):
        return fcc + struct.pack("<I", len(data)) + data + (b"\0" if len(data) % 2 else b"")

    def lst(kind, body):
        return b"LIST" + struct.pack("<I", len(body) + 4) + kind + body
    frames = [jpeg(i) for i in range(n)]
    mx = max(map(len, frames))
    avih = struct.pack("<IIIIIIIIII4I", int(1e6 / fps), 0, 0, 0x10, n, 0, 1, mx, w, h, 0, 0, 0, 0)
    strh = struct.pack("<4s4sIHHIIIIIIIIhhhh", b"vids", b"MJPG", 0, 0, 0, 0, 1, fps, 0, n, mx, 0xFFFFFFFF, 0, 0, 0,
                       w, h)
    strf = struct.pack("<IiiHH4sIiiII", 40, w, h, 1, 24, b"MJPG", w * h * 3, 0, 0, 0, 0)
    hdrl = lst(b"hdrl", chunk(b"avih", avih) + lst(b"strl", chunk(b"strh", strh) + chunk(b"strf", strf)))
    movi, idx, off = b"", b"", 4
    for f in frames:
        c = chunk(b"00dc", f)
        idx += struct.pack("<4sIII", b"00dc", 0x10, off, len(f))
        movi += c
        off += len(c)
    body = b"AVI " + hdrl + lst(b"movi", movi) + chunk(b"idx1", idx)
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
    return frames


def _cli(*args, timeout=120):
    r = subprocess.run([sys.executable, str(WIN / "pymf" / "cli.py"), *map(str, args)], capture_output=True,
                       text=True, timeout=timeout)
    return r.returncode, (json.loads(r.stdout) if r.stdout.strip().startswith("{") else None), r.stderr


@pytest.fixture(scope="module")
def avi(tmp_path_factory):
    _comtypes()
    d = tmp_path_factory.mktemp("avi")
    frames = _avi(d / "mjpg.avi")
    return d / "mjpg.avi", frames


def test_cli_formats_on_file(avi):
    rc, j, err = _cli("formats", "--url", avi[0], "--timeout-ms", 8000)
    assert rc == 0, err
    t = j["reader_streams"][0]["types"][0]
    assert (t["subtype"], t["width"], t["height"], t["fps_num"], t["fps_den"]) == ("MJPG", 320, 240, 30, 1)
    assert j["stream_started"] is False and j["tool"] == "pymf" and j["abandoned_threads"] == 0
    assert [s["step"] for s in j["steps"]] == ["resolve_url", "create_presentation_descriptor", "reader_native_types",
                                               "source_shutdown"]


def test_cli_capture_on_file_byte_exact(avi, tmp_path):
    path, frames = avi
    rc, j, err = _cli("capture", "--url", path, "--width", 320, "--height", 240, "--fps", 30, "--frames", 30,
                      "--timeout-ms", 4000, "--out-dir", tmp_path, "--save", "all")
    assert rc == 0, err
    assert j["ok"] and j["frames"]["total"] == 30 and j["frames"]["ok"] == 30 and j["negotiated"]["readback_ok"]
    assert [s["step"] for s in j["steps"]] == ["resolve_url", "reader_create", "set_type", "read_sample_issue",
                                               "first_sample", "flush", "reader_release", "source_shutdown"]
    assert next(s for s in j["steps"] if s["step"] == "flush")["on_flush_received"] is True
    rows = [json.loads(x) for x in (tmp_path / "frames.jsonl").read_text(encoding="utf-8").splitlines()]
    blob = (tmp_path / "frames.mjpeg").read_bytes()
    assert all(blob[r["mjpeg_offset"]:r["mjpeg_offset"] + r["mjpeg_len"]] == frames[r["seq"]] for r in rows)
    assert set(rows[0]) == set(WINCAM_ROW) - {"mf_device_timestamp"}
    assert json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))["exit_code"] == 0
    for k in ("negotiated", "steps", "timings", "frames", "fps_measured", "duration_s", "metadata", "cpu", "ok",
              "error", "unreleasable", "files"):
        assert k in j, k


def test_cli_capture_wrong_mode_is_rejected(avi, tmp_path):
    rc, j, _ = _cli("capture", "--url", avi[0], "--width", 640, "--height", 480, "--fps", 30, "--frames", 5,
                    "--timeout-ms", 4000, "--out-dir", tmp_path)
    assert rc == 4 and j["error"]["stage"] == "set_type" and j["error"]["hr_name"] == "MF_E_INVALIDMEDIATYPE"
    assert j["negotiated"]["candidate_rates_same_size"] == []
    assert j["steps"][-1]["step"] == "source_shutdown"                   # still released in order


def test_cli_cycle_on_file(avi, tmp_path):
    rc, j, err = _cli("cycle", "--url", avi[0], "--width", 320, "--height", 240, "--fps", 30, "--cycles", 8,
                      "--frames", 5, "--timeout-ms", 4000, "--out", tmp_path)
    assert rc == 0, err
    assert j["summary"]["ok"] == 8 and j["summary"]["failed"] == 0 and not j["summary"]["unreleasable"]
    rows = [json.loads(x) for x in (tmp_path / "cycles.jsonl").read_text(encoding="utf-8").splitlines()]
    want = {"i", "mode", "ok", "stage_failed", "hr", "hr_name", "error_class", "timed_out", "enumerate_ms",
            "activate_ms", "reader_ms", "settype_ms", "first_frame_ms", "open_to_first_frame_ms", "frames", "frames_ok",
            "with_uvc_metadata", "close_ms", "flush_ms", "reader_release_ms", "shutdown_ms", "shutdown_object_ms",
            "in_use_by_other", "unreleasable", "negotiated_ok", "t_start_qpc_ns", "utc", "steps",
            # wincam 1.2's per-cycle rate fields (same cycles.jsonl contract)
            "fps_measured", "duration_s", "raw", "negotiated_subtype", "likely_mf_synthesized"}
    assert set(rows[0]) == want and len(rows) == 8
    assert all(r["fps_measured"] and r["fps_measured"] > 0 and r["duration_s"] > 0 for r in rows)
    assert rows[0]["raw"] is False and rows[0]["negotiated_subtype"]
    assert j["summary"]["fps_measured_p50"] > 0 and j["summary"]["fps_measured_min"] > 0
    from common import cycstats
    assert cycstats.summarize_cycles(rows)["n_ok"] == 8
    assert W.cycle_fps_p50(rows) > 0


def test_cli_usage_errors():
    _comtypes()
    rc, j, _ = _cli("capture", "--url", "x.avi", "--width", 320)
    assert rc == 2 and j["error"]["class"] == "usage"
    rc, j, _ = _cli("controls", "--url", "x.avi", "--set", "bogus=1")
    assert rc == 2 and "unknown control" in j["error"]["reason"]
    rc, j, _ = _cli("formats")
    assert rc == 2 and j["error"]["reason"] == "--device required"
    rc, _j, _ = _cli("--version")
    assert rc == 0


def test_cli_missing_file_is_a_clean_failure(tmp_path):
    _comtypes()
    rc, j, _ = _cli("formats", "--url", tmp_path / "missing.avi", "--timeout-ms", 5000)
    assert rc == 4 and j["error"]["stage"] == "resolve_url" and j["error"]["hr"]


# ============================================================================================================ 6. W-PYMF run (fake ctx)
class FakeCtx:
    """A SuiteCtx stand-in: camcmd answers with canned wincam / pymf outputs and writes the files the real tools
    write (frames.jsonl, frames.mjpeg, cycles.jsonl, summary.json). Nothing is executed."""

    def __init__(self, tmp: Path, pymf_meta: bool = True, pymf_hang_cycle: bool = False, pymf_fault: bool = False,
                 probe_fails: bool = False):
        tmp.mkdir(parents=True, exist_ok=True)
        self.out_dir, self.raw_dir = tmp / "out", tmp / "raw"
        self.out_dir.mkdir()
        self.raw_dir.mkdir()
        self.args = SimpleNamespace(quick=True, min_fps=30.0, min_height=720, max_height=720, all_modes=False)
        self.wincam, self.python = Path("C:/x/wincam.exe"), "3.12"
        self.cameras = [{"key": "046d:085c:sn=X", "name": "C922 Pro Stream Webcam", "vid": "046d", "pid": "085c",
                         "serial": "X", "mf_symlink": LINK_MF, "metadata_tier1": True, "is_kiyo": False}]
        self.pymf_meta, self.pymf_hang_cycle, self.pymf_fault = pymf_meta, pymf_hang_cycle, pymf_fault
        self.probe_fails = probe_fails                 # wincam's 1-frame health probe hangs too (camera wedged)
        self.calls: list[list[str]] = []
        self.faults: dict = {}

    def log(self, msg):
        pass

    def test_dir(self, name):
        d = self.out_dir / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def raw_test_dir(self, name):
        d = self.raw_dir / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def arrivals(self):
        return {"cameras": {}}

    def camera_faulted(self, key):
        return self.faults.get(key)

    def camera_gated(self, key):
        return None

    def mark_fault(self, key, **kw):
        self.faults.setdefault(key, {"faulted": True, "since_utc": "2026-11-08T00:00:00Z", **kw})
        return self.faults[key]

    def clear_fault(self, key, **kw):
        self.faults.pop(key, None)

    @staticmethod
    def _r(obj, rc=0, timed_out=False):
        return {"rc": rc, "stdout": json.dumps(obj) if obj is not None else "", "stderr": "", "elapsed_s": 1.0,
                "timed_out": timed_out, "killed": timed_out, "lock_wait_s": 0.0, "spawn_error": None}

    def run(self, argv, timeout_s, cwd=None, env=None):
        argv = [str(a) for a in argv]
        if "--version" in argv:
            return {"rc": 0, "stdout": "pymf 0.1\n", "stderr": "", "elapsed_s": 1.0, "timed_out": False}
        return self._r({"mf": {"devices": [{"index": 0, "friendly_name": "C922 Pro Stream Webcam",
                                            "symlink": LINK_MF}]}})

    def camcmd(self, argv, timeout_s, **kw):
        argv = [str(a) for a in argv]
        self.calls.append(argv)
        tool = "pymf" if any(a.endswith("cli.py") for a in argv) else "wincam"
        sub = next(a for a in argv if a in ("formats", "controls", "capture", "cycle"))

        def val(f):
            return argv[argv.index(f) + 1] if f in argv else None
        if sub == "formats":
            return self._r({"tool": tool, **_fmt_doc()})
        if sub == "controls" and "--set" not in argv:
            return self._r({"tool": tool, **_ctl_doc(-5, 1)})
        if sub == "controls":
            sets, rest = [], []
            for item in val("--set").split(","):
                k, v = item.split("=")
                key = ("cc." if k in ("exposure", "focus") else "pa.") + k
                sets.append({"control": key, "requested": v, "matches": True})
                auto = k == "exposure"
                rest.append({"control": key, "restore_value": -5 if auto else 0, "restore_flags": 1 if auto else 2,
                             "readback_value": -5 if auto else 0, "readback_flags": 1 if auto else 2,
                             "timed_out": False})
            return self._r({"tool": tool, "exit_code": 0, "error": None, "sets": sets, "restore": rest})
        od = Path(val("--out-dir") or val("--out"))
        od.mkdir(parents=True, exist_ok=True)
        if sub == "capture":
            if self.probe_fails and tool == "wincam" and val("--frames") == "1":
                return self._r(None, rc=None, timed_out=True)
            if self.pymf_fault and tool == "pymf":
                err = {"stage": "first_sample", "hr": "0x8007001F", "class": "device_error"}
                return self._r({"ok": False, "error": err, "frames": {"total": 0}, "exit_code": 4}, rc=4)
            jp = _jpeg()
            rows, blob = [], b""
            meta = tool == "wincam" or self.pymf_meta
            for i, r in enumerate(_rows(n=60, meta=meta)):
                r.update(soi=True, eoi=True, eoi_trailing_bytes=0, sof0_w=1280, sof0_h=720, bytes=len(jp))
                if i % 5 == 0:
                    r.update(mjpeg_offset=len(blob), mjpeg_len=len(jp))
                    blob += jp
                rows.append(r)
            (od / "frames.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
            (od / "frames.mjpeg").write_bytes(blob)
            s = {"ok": True, "exit_code": 0, "error": None, "frames": {"total": 60, "ok": 60},
                 "timings": {"first_frame_ms": 400.0, "open_to_first_frame_ms": 900.0 if tool == "wincam" else 980.0,
                             "close_ms": 300.0}, "fps_measured": 30.0,
                 "cpu": {"pct_of_one_core": 1.5 if tool == "wincam" else 4.0},
                 "negotiated": {"native_type_index": 3, "readback_ok": True}, "abandoned_threads": 0}
            return self._r(s)
        n = int(val("--cycles"))
        if self.pymf_hang_cycle and tool == "pymf":
            return self._r(None, rc=None, timed_out=True)
        rows = [{"i": i, "ok": True, "first_frame_ms": 450.0, "open_to_first_frame_ms": 950.0, "close_ms": 300.0,
                 "steps": [{"step": "enumerate"}]} for i in range(n)]
        (od / "cycles.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        return self._r({"exit_code": 0, "summary": {"ok": n, "failed": 0}, "error": None})


def test_run_with_fake_ctx_yes(tmp_path):
    import capkit as ck
    ctx = FakeCtx(tmp_path)
    res = W.run(ctx)
    k = ctx.cameras[0]["key"]
    v = res["verdicts"]
    assert not res["errors"], res["errors"]
    assert v[f"pymf_equivalence|{k}|pymf"]["rating"] == "yes", v[f"pymf_equivalence|{k}|pymf"].get("note")
    assert v["pymf_equivalence"]["rating"] == "partial"                    # STREAMING_SET_CAP
    assert any("streaming source" in x for x in v["pymf_equivalence"]["evidence"]["not_covered"])
    rel = v[f"reliability|{k}|pymf_inproc"]
    assert rel["rating"] in ("yes", "partial")
    # W-CYC's labelling: a 'yes' from a few cycles is a point estimate, never plain 'yes' (smoke 2026-11-09)
    if rel["rating"] == "yes":
        assert rel["summary_label"].startswith("yes (point estimate; n=") and "Wilson lower" in rel["summary_label"]
    m = res["measurements"]["cameras"][k]
    assert m["mode"] == "MJPG 1280x720@30" and m["capture_compare"]["header_sha1_equal"] is True
    assert m["set_roundtrip"]["ok"] and m["set_roundtrip"]["requested"] == {"exposure": -4, "gain": 1}
    assert (ctx.out_dir / "W-PYMF" / f"{ck.cam_slug(ctx.cameras[0])}_pymf_cycles.jsonl").exists()
    json.dumps(res)                                                        # the result is plain JSON
    pymf_calls = [c for c in ctx.calls if any(a.endswith("cli.py") for a in c)]
    assert pymf_calls and all(c[:3] == ["uv", "run", "--python"] for c in pymf_calls)
    assert all(LINK_MF in c for c in ctx.calls)                            # camcmd can find the camera in argv


def test_run_with_fake_ctx_partial_and_faults(tmp_path):
    ctx = FakeCtx(tmp_path / "a", pymf_meta=False)                       # PTS through wincam only
    res = W.run(ctx)
    k = ctx.cameras[0]["key"]
    # tier 0 only (Dom 2026-11-09): UVC metadata in one probe's frames is not a difference
    assert res["verdicts"][f"pymf_equivalence|{k}|pymf"]["rating"] == "yes"
    ctx = FakeCtx(tmp_path / "b", pymf_hang_cycle=True)                   # pymf cycle killed at its timeout
    res = W.run(ctx)
    assert k in ctx.faults and ctx.faults[k]["cls"] == "hung_process"
    v = res["verdicts"]
    assert v[f"pymf_equivalence|{k}|pymf"]["rating"] == "no"              # pymf hung where wincam did not
    assert v[f"reliability|{k}|pymf_inproc"]["rating"] == "no"
    hp = res["measurements"]["cameras"][k]["hangs"][0]["probe_after"]
    assert hp["ok"] is True                                               # wincam streamed right after: pymf's fault
    # the same pymf hang, but wincam's 1-frame probe right after it fails too: the camera is wedged (the Kiyo's
    # 35 s hang), so the part is untested (device fault), never 'no' for pymf
    ctx = FakeCtx(tmp_path / "b2", pymf_hang_cycle=True, probe_fails=True)
    res = W.run(ctx)
    v = res["verdicts"]
    m = res["measurements"]["cameras"][k]
    assert not m.get("hangs") and m["device_hangs"][0]["probe_after"]["ok"] is False
    assert "device fault" in m["cycles_untested"]
    assert v[f"pymf_equivalence|{k}|pymf"]["rating"] == "partial"
    assert v[f"reliability|{k}|pymf_inproc"]["rating"] == "untested"
    agg = v["pymf_equivalence"]
    assert agg["rating"] == "partial" and "untested: device fault" in agg["summary_label"]
    ctx = FakeCtx(tmp_path / "c", pymf_fault=True)                        # 0x8007001F in the pymf capture
    res = W.run(ctx)
    m = res["measurements"]["cameras"][k]
    assert m["capture"]["pymf"]["fault"]["kind"] == "device_error" and k in ctx.faults
    assert "device fault" in m["capture_untested"]                        # a device fault is not an API result
    assert "device fault" in (m.get("cycles_untested") or "")             # the cycles are then skipped (gated)
    r = res["verdicts"][f"pymf_equivalence|{k}|pymf"]
    assert r["rating"] == "partial" and r["summary_label"] == "partial (capture, cycles untested)"
    assert res["verdicts"][f"reliability|{k}|pymf_inproc"]["rating"] == "untested"
