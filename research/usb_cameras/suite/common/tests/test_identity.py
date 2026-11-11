"""identity.camera_key: same keys as naming/camera_identity.py (copied logic; cross-checked when present)."""
import importlib.util
import sys
from pathlib import Path

import pytest

from common import identity as idn

NAMING = Path(__file__).resolve().parents[3] / "naming" / "camera_identity.py"


def test_serial_key_and_port_fallback():
    assert idn.camera_key("046D", "085C", "C922SN01", "x/13.1.4", [("046d", "085c", "C922SN01")]) == \
        "046d:085c:sn=C922SN01"
    # duplicate serial among connected cameras of the same model -> port path
    peers = [("046d", "085c", "C922SN01"), ("046d", "085c", "C922SN01")]
    assert idn.camera_key("046d", "085c", "C922SN01", "x/2", peers) == "046d:085c:port=x/2"
    # same serial on a different model does not count
    assert idn.camera_key("046d", "085c", "AB12", "x/2", [("046d", "085c", "AB12"), ("1532", "0e05", "AB12")]) \
        == "046d:085c:sn=AB12"
    for bad in (None, "", "0123456789", "AB,CD", "AB CD", "0000", "aaaa"):
        assert idn.camera_key(0x046D, 0x085C, bad, "p", None) == "046d:085c:port=p"
    assert idn.camera_key("4c4a", "4a55", None, None) == "4c4a:4a55:port=None"


def test_port_paths():
    assert idn.port_path_from_windows_location_paths("PCIROOT(0)#PCI(1400)#USBROOT(0)#USB(13)#USB(1)#USB(4)") == \
        "PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.4"
    assert idn.port_path_from_linux("0000:00:14.0", "3-13.1.4") == "pci-0000:00:14.0/13.1.4"
    assert idn.port_path_from_mac_location_id(0x14130000) == "bus14/1.3"


def test_assign_keys():
    cams = [{"vid": "046d", "pid": "085c", "serial": "S1", "port_path": "a"},
            {"vid": "046d", "pid": "085c", "serial": "S1", "port_path": "b"},
            {"vid": "4c4a", "pid": "4a55", "serial": None, "port_path": "c"}]
    idn.assign_keys(cams)
    assert [c["key_kind"] for c in cams] == ["port", "port", "port"]
    assert cams[0]["serial_reason"].startswith("serial shared")


@pytest.mark.skipif(not NAMING.exists(), reason="naming/camera_identity.py not present")
def test_matches_naming_camera_identity():
    spec = importlib.util.spec_from_file_location("camera_identity_orig", NAMING)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["camera_identity_orig"] = mod  # dataclasses needs the module registered
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop("camera_identity_orig", None)
    cases = [("046D", "085C", "C922SN01", "x/1"), ("046d", "085c", None, "x/1"), ("4c4a", "4a55", "0123456789", "y"),
             ("1532", "0e05", "AB,CD", "z"), ("046d", "0843", "  ", "w"), ("046d", "0843", "1111", "w")]
    for vid, pid, sn, pp in cases:
        flat = dict(vid=vid, pid=pid, usb_serial=sn, port_path=pp)
        assert mod.derive(flat, [flat])[0] == idn.camera_key(vid, pid, sn, pp, [(vid, pid, sn)])
    a = dict(vid="046d", pid="085c", usb_serial="S", port_path="p1")
    b = dict(vid="046d", pid="085c", usb_serial="S", port_path="p2")
    assert mod.derive(a, [a, b])[0] == idn.camera_key("046d", "085c", "S", "p1", [a, b])
