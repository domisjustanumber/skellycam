"""Offline unit tests for the Windows enumeration half (no camera, no hub IOCTL, no registry write).

    uv run --isolated --python 3.12 --no-project --with pytest pytest suite/windows/tests/test_enum_offline.py

Covers: FFmpeg / PyAV dshow listing parser (FFmpeg 9 '[in#0 @ ...]' and older '[dshow @ ...]' prefixes), _PLD decode
(zero position defaults are 'unspecified'), link -> instance ID, the descriptor -> KS control map against
naming/usbdesc.py's bit names, W-FMT mode normalization and tolerance matching, ModeAltCache seeding and the
Gerald pair predictions on the common Gerald fixture through W-TOPO's seed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
WIN = HERE.parent
SUITE = WIN.parent
RESEARCH = SUITE.parent
for p in (str(SUITE), str(WIN), str(WIN / "helpers"), str(HERE), str(RESEARCH / "naming"), str(SUITE / "common" / "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows suite (winpnp needs cfgmgr32)")

FFMPEG9 = r'''[in#0 @ 0000019a84a351c0] "c922 Pro Stream Webcam" (video)
[in#0 @ 0000019a84a351c0]   Alternative name "@device_pnp_\\?\usb#vid_046d&pid_085c&mi_00#8&268da596&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"
[in#0 @ 0000019a84a351c0] "NDI Webcam Video 1" (video)
[in#0 @ 0000019a84a351c0]   Alternative name "@device_pnp_\\?\root#media#0002#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\vidsource0"
[in#0 @ 0000019a84a351c0] "Microphone (Revelator IO 24)" (audio)
[in#0 @ 0000019a84a351c0]   Alternative name "@device_cm_{33D9A762-90C8-11D0-BD43-00A0C911CE86}\wave_{X}"
'''
FFMPEG4 = r'''[dshow @ 000001] DirectShow video devices (some may be both video and audio devices)
[dshow @ 000001]  "USB Camera"
[dshow @ 000001]     Alternative name "@device_pnp_\\?\usb#vid_4c4a&pid_4a55&mi_00#8&232e60d4&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"
'''


def test_parse_dshow_ffmpeg9_and_4():
    from enum_apis import _parse_dshow_lines
    d = _parse_dshow_lines(FFMPEG9)
    assert [x["name"] for x in d] == ["c922 Pro Stream Webcam", "NDI Webcam Video 1"]   # audio excluded
    assert d[0]["path"].startswith("@device_pnp_\\\\?\\usb#vid_046d&pid_085c")
    assert [x["index"] for x in d] == [0, 1]
    d4 = _parse_dshow_lines(FFMPEG4)
    assert d4 and d4[0]["name"] == "USB Camera" and "vid_4c4a" in d4[0]["path"]


def test_link_to_instance_id_and_usb_ids():
    import winpnp as wp
    link = r"@device_pnp_\\?\usb#vid_046d&pid_085c&mi_00#8&268da596&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"
    assert wp.link_to_instance_id(link) == r"USB\VID_046D&PID_085C&MI_00\8&268DA596&0&0000"
    assert wp.parse_usb_ids(r"USB\VID_1532&PID_0E05\9&3A0ECB01&0&4") == ("1532", "0e05", None)


def test_pld_zero_position_is_unspecified():
    import winpnp as wp
    # revision 2, user_visible, panel/vpos/hpos 0, shape 1 (oval), 8x3 mm, group_position 19 (Gerald HS13 style)
    v = 2 | (8 << 32) | (3 << 48) | (1 << 64) | (1 << 74) | (19 << 87)
    h = v.to_bytes(20, "little").hex()
    d = wp.decode_pld(h)
    assert d["position_all_zero"] is True and d["all_zero_defaults"] is False
    assert d["shape"] == 1 and d["width_mm"] == 8 and d["height_mm"] == 3 and d["user_visible"]
    v2 = v | (5 << 67)  # panel = back
    assert wp.decode_pld(v2.to_bytes(20, "little").hex())["position_all_zero"] is False


def test_ioctl_allow_list_blocks_unsafe_codes():
    import winpnp as wp
    for fn in (260, 262, 263, 273, 275):
        with pytest.raises(PermissionError):
            wp.ioctl(None, fn, b"", 0)
    with pytest.raises(PermissionError):
        wp.user_request(None, 0x10000001, 0)
    # the raw ioctl() path must refuse USBUSER_OP_* / HCTEST codes too, not only user_request() (review 2026-11-06)
    import struct
    for code in (0x10000001, 0x20000001, 0x20000005, 3):
        with pytest.raises(PermissionError):
            wp.ioctl(None, 270, struct.pack("<IIII", code, 0, 16, 0), 16)
    with pytest.raises(PermissionError):
        wp.ioctl(None, 270, b"", 16)


def test_ctrl_map_covers_usbdesc_bits():
    import usbdesc
    from w_ctrl_list import CT_MAP, PU_MAP
    ct = [b for b in usbdesc.CAMERA_CONTROL_BITS if not b.startswith("reserved")]
    assert set(ct) <= set(CT_MAP), set(ct) - set(CT_MAP)
    assert set(usbdesc.PROCESSING_CONTROL_BITS) <= set(PU_MAP), set(usbdesc.PROCESSING_CONTROL_BITS) - set(PU_MAP)


def test_fmt_normalization_and_tolerance():
    from w_fmt import _match, ds_modes, mf_modes
    mf = {"reader_streams": [{"stream_index": 0, "types": [
        {"subtype": "NV12", "width": 640, "height": 480, "fps_num": 30, "fps_den": 1,
         "flags": ["nv12_immediately_before_same_mode_mjpg:likely_mf_synthesized_decode"]},
        {"subtype": "MJPG", "width": 640, "height": 480, "fps_num": 30, "fps_den": 1, "flags": []},
        {"subtype": "MJPG", "width": 640, "height": 480, "fps_num": 10000000, "fps_den": 666666, "flags": []}]}],
        "streams": [{"stream_index": 0, "attributes": {"MF_DEVICESTREAM_STREAM_CATEGORY": "PIN_CATEGORY_CAPTURE"}}]}
    mm = mf_modes(mf)
    assert ("MJPG", 640, 480, 333333) in mm[0]["modes"] and len(mm[0]["synthesized"]) == 1
    ds = {"pins": [{"pin_index": 0, "direction": "output", "name": "Capture", "category_name": "PIN_CATEGORY_CAPTURE",
                    "modes": [{"subtype": "MJPG", "width": 640, "height": 480, "header_kinds": ["VIH", "VIH2"],
                               "frame_rate_list_100ns": [333333, 666667]}]}]}
    dd = ds_modes(ds)
    a, b = _match(mm[0]["modes"], dd[0]["modes"])
    assert not a and not b   # 666666 vs 666667 within tolerance


def test_topo_seed_and_gerald_pairs(tmp_path):
    from common import topology_model as tm
    from w_topo import GERALD_PAIRS, seed_cache
    import gerald_fixture as gf
    cache = seed_cache(tmp_path / "mode_alt_cache.json")
    assert (tmp_path / "mode_alt_cache.json").exists() and len(cache) >= 19
    snap = gf.build_snapshot()
    got = {}
    for label, mode, expected in GERALD_PAIRS:
        pred = tm.predict(snap, [{"camera_key": gf.C922_KEY, "mode": mode},
                                 {"camera_key": gf.GENERIC_KEY, "mode": "MJPG 1280x720@30"}], cache)
        dom = next(d for d in pred["domains"] if gf.C922_KEY in d["members"])
        got[label] = (dom["verdict"], dom["pct_microframe"])
        assert dom["verdict"] == expected, (label, dom)
    assert got[GERALD_PAIRS[0][0]][1] == pytest.approx(81.1, abs=0.1)
    assert got[GERALD_PAIRS[1][0]][1] == pytest.approx(59.7, abs=0.1)
    assert got[GERALD_PAIRS[2][0]][1] == pytest.approx(62.2, abs=0.1)


def test_alt_table_from_configuration_superspeed_mult():
    from win_descriptors import alt_table_from_configuration
    cfg = {"uvc": {"streaming_interfaces": [{"bInterfaceNumber": 1, "alt_settings": [
        {"bAlternateSetting": 1, "transfer_type": "isochronous", "wMaxPacketSize_raw": 0x1400, "bEndpointAddress": "0x81",
         "bInterval": 1, "bytes_per_interval": 3072},
        {"bAlternateSetting": 2, "transfer_type": "isochronous", "wMaxPacketSize_raw": 0x0400, "bEndpointAddress": "0x81",
         "bInterval": 1, "bytes_per_interval": 33792, "ss_companion": {"bMaxBurst": 10, "bmAttributes": 2,
                                                                       "wBytesPerInterval": 33792}}]}]}}
    hs = alt_table_from_configuration(cfg, "high")
    assert hs[0]["max_packet"] == 1024 and hs[0]["mult"] == 3
    ss = alt_table_from_configuration(cfg, "super")
    assert ss[1]["mult"] == 33 and ss[1]["max_packet"] == 1024
