"""UVC control logic with a fake transport, descriptor summaries, child plumbing, IOKit safety lists."""
import fake_mac
import childutil
import iokit_usb
import mac_ep0
import uvc_ctrl


def entities():
    return mac_ep0.summarize_config(fake_mac.uvc_config(fake_mac.C922_ALTS, [(640, 480, [30])]))["entities"]


def test_summarize_config():
    s = mac_ep0.summarize_config(fake_mac.uvc_config(fake_mac.C922_ALTS, [(640, 480, [30, 15]), (1920, 1080, [30, 5])]))
    assert s["entities"]["camera_terminal"]["id"] == 1 and s["entities"]["processing_unit"]["id"] == 2
    assert "exposure_time_absolute" in s["entities"]["camera_terminal"]["controls"]
    assert "gain" in s["entities"]["processing_unit"]["controls"]
    a9 = [a for a in s["alt_table"] if a["alt"] == 9][0]
    assert (a9["max_packet"], a9["mult"]) == (992, 2)
    assert [(f["w"], f["h"], f["fps"]) for f in s["frames"]] == [(640, 480, [30.0, 15.0]), (1920, 1080, [30.0, 5.0])]


def test_read_set_readback():
    c = uvc_ctrl.UVCControls(fake_mac.FakeUVCTransport(), entities())
    r = c.read("exposure_time_absolute")
    assert r["ok"] and (r["min"], r["max"], r["def"], r["cur"]) == (3, 2047, 250, 156)
    assert r["info"]["get"] and r["info"]["set"] and r["info"]["autoupdate"]
    ae = c.read("auto_exposure_mode")
    assert ae["modes_supported"] == ["manual", "aperture_priority"]
    b = c.read("brightness")
    assert b["cur"] == -10 and b["min"] == -64  # signed
    s = c.set_cur("exposure_time_absolute", 300)
    assert s["ok"] and s["readback"] == 300 and s["readback_matches"]
    assert c.get_interface(1)["alt"] == 4


def test_stall_and_not_responding():
    c = uvc_ctrl.UVCControls(fake_mac.FakeUVCTransport(), entities())
    z = c.read("zoom_absolute")  # advertised in the fake descriptor but not answered
    assert not z["ok"] and z["calls"][0]["rc_name"] == "kIOUSBPipeStalled"
    dead = uvc_ctrl.UVCControls(fake_mac.FakeUVCTransport(dead_after=0), entities())
    r = dead.read("gain")
    assert r.get("aborted") and len(r["calls"]) == 1 and r["calls"][0]["rc_name"] == "kIOReturnNotResponding"


def test_ctrl_list_with_fake_session():
    class S:
        def __init__(self):
            self.entities = entities()
            self.t = fake_mac.FakeUVCTransport()
            self.log = []

        def controls(self):
            return uvc_ctrl.UVCControls(self.t, self.entities, 500, self.log)

    out = mac_ep0.ctrl_list(S(), all_selectors=True)
    names = {r["name"]: r for r in out["controls"]}
    assert names["gain"]["ok"] and names["gain"]["advertised_in_descriptor"]
    assert not names["focus_auto"]["advertised_in_descriptor"]
    assert out["n_advertised"] == 13


def test_rc_names_and_values():
    assert uvc_ctrl.rc_name(0xE00002EC) == "kIOReturnNoBandwidth"
    assert uvc_ctrl.rc_name(-536870164) == "kIOReturnNoBandwidth"
    assert uvc_ctrl.rc_name(-3) == "LIBUSB_ERROR_ACCESS"
    assert uvc_ctrl.rc_name(0xE0004061) == "kIOUSBUnknownPipeErr"  # iokit_usb_err(0x61)
    assert uvc_ctrl.rc_name(0xE0004057) == "kIOUSBEndpointNotFound"  # iokit_usb_err(0x57)
    assert uvc_ctrl.pick_values({"min": 2800, "max": 6500, "res": 10}) == [3420, 4650, 5880]
    assert uvc_ctrl.exposure_values({"min": 3, "max": 2047}) == [3, 32, 333]
    pc = uvc_ctrl.parse_probe_commit(bytes(2) + bytes([1, 3]) + (333333).to_bytes(4, "little") + bytes(10)
                                     + (614400).to_bytes(4, "little") + (3072).to_bytes(4, "little"))
    assert pc["bFormatIndex"] == 1 and pc["bFrameIndex"] == 3 and pc["dwMaxPayloadTransferSize"] == 3072


def test_iokit_never_exposes_forbidden_slots():
    for allowed in (iokit_usb.ALLOWED_DEVICE_SLOTS, iokit_usb.ALLOWED_INTERFACE_SLOTS):
        assert not set(allowed.values()) & iokit_usb.FORBIDDEN
    # slot numbers of the forbidden calls (IOUSBLib.h) are not allowed
    assert 23 not in iokit_usb.ALLOWED_DEVICE_SLOTS and 25 not in iokit_usb.ALLOWED_DEVICE_SLOTS  # Set/Reset
    assert 29 not in iokit_usb.ALLOWED_DEVICE_SLOTS and 8 not in iokit_usb.ALLOWED_DEVICE_SLOTS  # open/seize
    assert 8 not in iokit_usb.ALLOWED_INTERFACE_SLOTS and 22 not in iokit_usb.ALLOWED_INTERFACE_SLOTS  # open/SetAlt
    assert bytes(iokit_usb.uuid_bytes("kIOCFPlugInInterfaceID").b).hex() == "c244e858109c11d491d40050e4c6426f"
    import ctypes
    assert ctypes.sizeof(iokit_usb.IOUSBDevRequestTO) == ctypes.sizeof(iokit_usb.IOUSBDevRequest) + 8


def test_libusb_source_never_claims():
    import inspect
    src = inspect.getsource(mac_ep0.LibusbTransport)
    for bad in ("claimInterface", "detachKernelDriver", "setConfiguration", "setInterfaceAltSetting", "resetDevice"):
        assert bad not in src


def test_childutil_parsers():
    assert childutil.parse_kv_list("a=1, b=-2,c=0x10") == [("a", 1), ("b", -2), ("c", 16)]
    ev = childutil.parse_schedule("2000:ep0:gain=10;1000:avf:exposure=locked;1500:probe:ioreg_alt")
    assert [e["t_ms"] for e in ev] == [1000, 1500, 2000]
    assert ev[1] == {"t_ms": 1500.0, "kind": "probe", "name": "ioreg_alt", "value": None}
