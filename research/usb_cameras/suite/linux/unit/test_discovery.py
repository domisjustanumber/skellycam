"""Camera discovery from the fake sysfs tree (sysfs only, no /dev access)."""
import pytest

import sysfs
from gerald_fixture import C922_ALTS, C930E_ALTS, GENERIC_ALTS

pytestmark = pytest.mark.linux_only


def _by_pid(cams):
    return {c["pid"]: c for c in cams}


def test_four_cameras_with_keys(fake_root):
    cams = sysfs.discover_cameras()
    assert len(cams) == 4
    by = _by_pid(cams)
    assert by["085c"]["key"] == "046d:085c:sn=C922SN01" and by["085c"]["key_kind"] == "serial"
    assert by["4a55"]["key"] == "4c4a:4a55:port=pci-0000:00:14.0/13.1.2"
    assert by["0843"]["key"] == "046d:0843:port=pci-0000:00:14.0/7"
    assert by["0e05"]["key"] == "1532:0e05:port=pci-0000:3a:00.0/2.4"
    assert by["0e05"]["is_kiyo"] and not by["085c"]["is_kiyo"]


def test_nodes_and_links(fake_root):
    by = _by_pid(sysfs.discover_cameras())
    c = by["085c"]
    assert c["node"] == "/dev/video0" and c["meta_node"] == "/dev/video1"
    assert c["by_id"] == ["usb-046d_C922_Pro_Stream_Webcam_C922SN01-video-index0"]
    assert c["by_path"] == ["pci-0000:00:14.0-usb-0:13.1.4:1.0-video-index0"]
    assert c["interface_driver"] == "uvcvideo"
    assert by["0e05"]["speed"] == "SS" and by["085c"]["speed"] == "HS"


def test_mjpeg_mode_counts_match_windows_mf(fake_root):
    """MF lists one native MJPG type per (size, interval): C922 120, C930e 119, generic 10, Kiyo 28 (plan 2.1)."""
    by = _by_pid(sysfs.discover_cameras())
    assert {p: len(by[p]["modes"]["all_mjpeg"]) for p in by} == {"085c": 120, "0843": 119, "4a55": 10, "0e05": 28}
    assert by["085c"]["modes"]["default"] == {"fourcc": "MJPG", "w": 1280, "h": 720, "fps": 30.0}
    assert by["085c"]["modes"]["small"] == {"fourcc": "MJPG", "w": 640, "h": 480, "fps": 30.0}


def test_alt_tables_match_windows_topology(fake_root):
    by = _by_pid(sysfs.discover_cameras())

    def tab(c):
        return {a["alt"]: (a["max_packet"], a["mult"]) for a in c["descriptors"]["streams"][0]["alt_table"]}
    assert tab(by["085c"]) == C922_ALTS
    assert tab(by["0843"]) == C930E_ALTS
    assert tab(by["4a55"]) == GENERIC_ALTS


def test_descriptor_controls_and_clock(fake_root):
    by = _by_pid(sysfs.discover_cameras())
    d = by["085c"]["descriptors"]
    assert d["dwClockFrequency"] == 300_000_000 and d["bcdUVC"] == "1.00"
    assert "exposure_time_absolute" in d["ct_controls"] and "white_balance_temperature" in d["pu_controls"]
    assert by["4a55"]["descriptors"]["ct_controls"] == ["auto_exposure_mode", "exposure_time_absolute"]


def test_kiyo_no_lpm_quirk_and_power(fake_root):
    k = _by_pid(sysfs.discover_cameras())["0e05"]
    assert k["no_lpm_quirk"] is True and k["quirks"] == "0x400"
    assert k["power"]["usb3_hardware_lpm_u1"] == "disabled"


def test_streaming_alt_and_arrivals(fake_root_streaming):
    cams = sysfs.discover_cameras()
    c922 = _by_pid(cams)["085c"]
    assert c922["vs_interfaces"] == [{"interface": "1-13.1.4:1.1", "number": 1, "alt": 9}]
    a = sysfs.arrival_state(cams)
    assert sysfs.compare_arrivals(a, a) == []
    b = {k: dict(v) for k, v in a.items()}
    b[c922["key"]]["devnum"] = "99"
    ev = sysfs.compare_arrivals(a, b)
    assert ev and ev[0]["event"] == "re-arrived"


def test_holders_scan_never_raises(fake_root):
    h = sysfs.holders(["/dev/video0", "/dev/video99"])
    assert set(h) == {"/dev/video0", "/dev/video99"}
