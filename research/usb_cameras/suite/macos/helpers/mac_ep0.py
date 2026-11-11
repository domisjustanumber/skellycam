# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "libusb1>=3.1; sys_platform == 'darwin'",
# ]
# ///
"""Endpoint-0 UVC control probe for macOS (child process of the macOS suite). OPT-IN: the runner calls it only
with --ep0. UNTESTED on a Mac (written on Windows).

Why opt-in (macos.md section 5 + verifier notes, topology_macos.md verifier note 8):
- UVC class requests on endpoint 0 with no interface claim work in practice on macOS 12+ (CameraController PR
  #26, uvc-util, one uvc-avf measurement), but an unopened request is outside Apple's documented contract.
- libusb is worse: its darwin enumeration calls USBDeviceOpenSeize on EVERY device while caching descriptors,
  and libusb_open calls USBDeviceOpenSeize again (darwin_usb.c). A successful seize takes the device away from
  its current owner; the brief's Windows experience says enumeration can disturb a faulty camera (the Kiyo).

Backends (``--backend``):
- ``iokit-intf`` (default): IOUSBLib interface plug-in on the camera's VideoControl interface, ControlRequest on
  pipe 0 WITHOUT USBInterfaceOpen (the CameraController / uvc-util pattern). Requests to a VideoStreaming
  interface (GET_INTERFACE, VS_COMMIT GET_CUR) go through that interface's own plug-in.
- ``iokit-dev``: IOUSBLib device plug-in, DeviceRequest WITHOUT USBDeviceOpen (the libusb/USB Prober pattern).
- ``libusb``: python-libusb1 control transfers on a handle. NEVER claims, detaches, sets a configuration or an
  alt setting; records the libusb_open result. Seizes as described above, so it is a separate opt-in
  (``--ep0-backend libusb`` on the runner).
Descriptors always come from the device plug-in's GetConfigurationDescriptorPtr (the OS's cached copy, no
request) unless ``--desc-request`` asks for a standard GET_DESCRIPTOR.

Subcommands (each prints one JSON object):
  probe        set up the transport and verify the vtable layout; nothing is sent to the camera
  descriptors  configuration descriptor (hex) + UVC summary + VS alt table + MJPEG frame list
  ctrl-list    GET_INFO/MIN/MAX/RES/DEF/CUR for every CT/PU control in bmControls (``--all-selectors`` adds the
               unadvertised ones, expected to STALL)
  get          GET_CUR of ``--controls a,b,c``
  set          SET_CUR ``--set name=value,...`` with readback (``--restore`` puts the previous values back)
  stream-state GET_INTERFACE + cached alt + VS_COMMIT GET_CUR per VideoStreaming interface (read-only)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SUITE_DIR = HERE.parents[1]
for p in (str(SUITE_DIR), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import childutil  # noqa: E402
import usbdesc  # noqa: E402
import uvc_ctrl  # noqa: E402

BACKENDS = ("iokit-intf", "iokit-dev", "libusb")


# ----------------------------------------------------------------------------------------- descriptor helpers
def alt_table_from_uvc(uvc: dict | None) -> list[dict]:
    """VideoStreaming isochronous IN alts: [{"interface","alt","ep","max_packet","mult","interval"}]."""
    out = []
    for s in (uvc or {}).get("streaming_interfaces") or []:
        for a in s.get("alt_settings") or []:
            if a.get("transfer_type") == "isochronous" and a.get("bAlternateSetting"):
                out.append({"interface": s["bInterfaceNumber"], "alt": a["bAlternateSetting"],
                            "ep": a.get("bEndpointAddress"), "max_packet": a.get("bytes_per_transaction"),
                            "mult": a.get("transactions_per_microframe") or 1, "interval": a.get("bInterval"),
                            "ss_bytes_per_interval": (a.get("ss_companion") or {}).get("wBytesPerInterval")})
    return out


def frame_list_from_uvc(uvc: dict | None) -> list[dict]:
    """Every (format, frame) of every VS interface: [{"interface","format","fourcc","format_index","frame_index",
    "w","h","fps":[..]|None,"fps_range":[min,max]|None,"interval_type"}]."""
    out = []
    for s in (uvc or {}).get("streaming_interfaces") or []:
        for f in s.get("formats") or []:
            for fr in f.get("frames") or []:
                rec = {"interface": s["bInterfaceNumber"], "format": f.get("format"), "fourcc": f.get("fourcc"),
                       "format_index": f.get("bFormatIndex"), "frame_index": fr.get("bFrameIndex"),
                       "w": fr.get("wWidth"), "h": fr.get("wHeight"), "interval_type": fr.get("interval_type"),
                       "fps": None, "fps_range": None}
                if fr.get("interval_type") == "discrete":
                    rec["fps"] = [x for x in fr.get("fps") or [] if x]
                elif fr.get("interval_type") == "continuous":
                    rec["fps_range"] = [fr.get("fps_min"), fr.get("fps_max")]
                out.append(rec)
    return out


def summarize_config(blob: bytes, speed: str | None = "high") -> dict:
    cfg = usbdesc.parse_configuration(blob, speed)
    uvc = cfg.get("uvc")
    return {"uvc": uvc, "entities": uvc_ctrl.entities_from_uvc_summary(uvc), "alt_table": alt_table_from_uvc(uvc),
            "frames": frame_list_from_uvc(uvc), "interfaces": [
                {k: i.get(k) for k in ("bInterfaceNumber", "bAlternateSetting", "bInterfaceClass", "bInterfaceSubClass",
                                       "bNumEndpoints", "kind")} for i in cfg.get("interfaces") or []]}


# ----------------------------------------------------------------------------------------- libusb backend
class LibusbTransport:
    """python-libusb1 handle; no claim, no detach, no set_configuration, no set_interface, no reset."""
    name = "libusb"

    def __init__(self, location_id: int, vid: str | None, pid: str | None):
        self.location_id, self.vid, self.pid = int(location_id), vid, pid
        self.ctx = self.handle = self.dev = None
        self.info: dict[str, Any] = {"backend": self.name, "location_id": f"0x{self.location_id:08x}",
                                     "claim_attempted": False, "detach_attempted": False,
                                     "warning": "libusb enumeration on darwin calls USBDeviceOpenSeize on every "
                                                "device; libusb_open calls it again on this camera"}

    def setup(self) -> dict:
        try:
            import usb1  # type: ignore
        except Exception as e:
            self.info["error"] = f"python libusb1 not importable: {e!r}"
            return self.info
        self.usb1 = usb1
        t0 = time.perf_counter()
        try:
            self.ctx = usb1.USBContext()
            self.ctx.open()
            for dev in self.ctx.getDeviceIterator(skip_on_error=True):
                try:
                    bus = dev.getBusNumber()
                    ports = dev.getPortNumberList()
                except Exception:
                    continue
                loc = (bus & 0xFF) << 24
                for i, n in enumerate(ports[:6]):
                    loc |= (n & 0xF) << (20 - 4 * i)
                if loc == self.location_id and (not self.vid or f"{dev.getVendorID():04x}" == self.vid) \
                        and (not self.pid or f"{dev.getProductID():04x}" == self.pid):
                    self.dev = dev
                    break
        except Exception as e:
            self.info["error"] = f"libusb enumeration failed: {e!r}"
            return self.info
        self.info["enumeration_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        if self.dev is None:
            self.info["error"] = "device not found by libusb (bus/port path vs locationID)"
            return self.info
        try:
            self.handle = self.dev.open()
            self.info["open_rc"] = 0
        except usb1.USBError as e:
            self.info["open_rc"] = getattr(e, "value", None)
            self.info["open_rc_name"] = uvc_ctrl.rc_name(getattr(e, "value", None))
            self.info["error"] = f"libusb_open failed: {e!r}"
        return self.info

    def ctrl_in(self, bm, req, wv, wi, length, timeout_ms):
        if self.handle is None:
            return -4, b""
        try:
            return 0, bytes(self.handle.controlRead(bm, req, wv, wi, length, timeout=int(timeout_ms)))
        except self.usb1.USBError as e:
            return int(getattr(e, "value", -99)), b""

    def ctrl_out(self, bm, req, wv, wi, data, timeout_ms):
        if self.handle is None:
            return -4
        try:
            self.handle.controlWrite(bm, req, wv, wi, bytes(data), timeout=int(timeout_ms))
            return 0
        except self.usb1.USBError as e:
            return int(getattr(e, "value", -99))

    def close(self) -> None:
        try:
            if self.handle is not None:
                self.handle.close()
        finally:
            if self.ctx is not None:
                self.ctx.close()


# ----------------------------------------------------------------------------------------- session
class Ep0Session:
    """Descriptors + entities + a control transport for one camera. Library entry point (mac_avf.py imports it for
    scheduled ep0 actions during a capture)."""

    def __init__(self, location_id: int, vid: str | None = None, pid: str | None = None, backend: str = "iokit-intf",
                 vc_interface: int | None = None, entities: dict | None = None, timeout_ms: int = 500,
                 desc_request: bool = False, allow_seize: bool = False):
        if backend not in BACKENDS:
            raise ValueError(f"backend must be one of {BACKENDS}")
        self.allow_seize = bool(allow_seize)
        self.location_id, self.vid, self.pid, self.backend = int(location_id), vid, pid, backend
        self.vc_interface, self.entities, self.timeout_ms = vc_interface, entities, int(timeout_ms)
        self.desc_request = desc_request
        self.transport = None
        self.desc: dict | None = None
        self.log: list[dict] = []
        self.info: dict[str, Any] = {"backend": backend}
        self._vs_transports: dict[int, Any] = {}

    def descriptors(self, hold: Any = None) -> dict:
        """The configuration descriptor (the OS's cached copy; a GET_DESCRIPTOR request only with desc_request).
        ``hold()`` (optional) runs while the device plug-in is still held, before it is released (M-FMT-NOGRAB)."""
        import iokit_usb
        out: dict[str, Any] = {"source": None}
        dev = iokit_usb.IOKitDeviceTransport(self.location_id, self.vid, self.pid, allow_requests=self.desc_request
                                             or self.backend == "iokit-dev")
        out["device_transport"] = dev.setup()
        try:
            if dev.obj is not None:
                kr, blob = dev.config_descriptor(0)
                out["GetConfigurationDescriptorPtr_kr"] = kr
                if kr == 0 and blob:
                    out["source"] = "GetConfigurationDescriptorPtr (cached, no request)"
                elif self.desc_request:
                    rc, head = dev.ctrl_in(0x80, 6, 0x0200, 0, 9, self.timeout_ms)
                    if rc == 0 and len(head) >= 4:
                        total = int.from_bytes(head[2:4], "little")
                        rc, blob = dev.ctrl_in(0x80, 6, 0x0200, 0, total, self.timeout_ms)
                        out["source"] = "GET_DESCRIPTOR request" if rc == 0 else None
                    out["get_descriptor_rc"] = uvc_ctrl.rc_name(rc)
                if out["source"]:
                    out["config_hex"] = blob.hex()
                    speed = {0: "low", 1: "full", 2: "high", 3: "super", 4: "super_plus"}.get(
                        (out["device_transport"].get("verify") or {}).get("speed"), "high")
                    out.update(summarize_config(blob, speed))
            if hold is not None:
                out["hold"] = hold()
        finally:
            dev.close()
        self.desc = out
        if out.get("entities"):
            ent = dict(out["entities"])
            if self.vc_interface is not None:
                ent["vc_interface"] = self.vc_interface
            self.entities = self.entities or ent
        return out

    def setup(self) -> dict:
        import iokit_usb  # noqa: F401  (import errors are reported by the caller)
        if self.entities is None:
            self.descriptors()
        vc_if = self.vc_interface if self.vc_interface is not None else (self.entities or {}).get("vc_interface")
        if self.backend == "iokit-intf":
            import iokit_usb as K
            if vc_if is None:
                self.info["error"] = "VideoControl interface number unknown"
                return self.info
            self.transport = K.IOKitInterfaceTransport(self.location_id, vc_if, self.vid, self.pid)
        elif self.backend == "iokit-dev":
            import iokit_usb as K
            self.transport = K.IOKitDeviceTransport(self.location_id, self.vid, self.pid, allow_requests=True)
        else:
            if not self.allow_seize:
                # libusb's darwin backend calls USBDeviceOpenSeize while enumerating EVERY device and again in
                # libusb_open (plan 6.1: no seize). Refuse unless the operator explicitly accepted that.
                self.info["error"] = ("backend 'libusb' seizes USB devices (USBDeviceOpenSeize during enumeration and "
                                      "libusb_open); refused without --allow-seize")
                self.info["ok"] = False
                self.info["refused_seize"] = True
                return self.info
            self.transport = LibusbTransport(self.location_id, self.vid, self.pid)
        self.info["transport"] = self.transport.setup()
        self.info["ok"] = not self.info["transport"].get("error")
        return self.info

    def controls(self) -> uvc_ctrl.UVCControls:
        ent = dict(self.entities or {})
        if self.vc_interface is not None:
            ent["vc_interface"] = self.vc_interface
        return uvc_ctrl.UVCControls(self.transport, ent, self.timeout_ms, self.log)

    def vs_transport(self, vs_if: int):
        """Transport for requests addressed to a VideoStreaming interface."""
        if self.backend != "iokit-intf":
            return self.transport
        if vs_if not in self._vs_transports:
            import iokit_usb as K
            t = K.IOKitInterfaceTransport(self.location_id, vs_if, self.vid, self.pid)
            t.setup()
            self._vs_transports[vs_if] = t
        return self._vs_transports[vs_if]

    def stream_state(self, vs_interfaces: list[int]) -> list[dict]:
        out = []
        bcd = (self.entities or {}).get("bcdUVC")
        for n in vs_interfaces:
            t = self.vs_transport(n)
            c = uvc_ctrl.UVCControls(t, self.entities or {}, self.timeout_ms, self.log)
            rec: dict[str, Any] = {"interface": n, "transport": getattr(t, "info", {}).get("error")}
            if hasattr(t, "cached_alt"):
                rec["cached_alt"] = t.cached_alt()
            rec["get_interface"] = c.get_interface(n)
            rec["commit"] = c.get_commit(n, bcd)
            out.append(rec)
        return out

    def close(self) -> None:
        for t in self._vs_transports.values():
            try:
                t.close()
            except Exception:
                pass
        if self.transport is not None:
            try:
                self.transport.close()
            except Exception:
                pass


def ctrl_list(sess: Ep0Session, all_selectors: bool = False) -> dict:
    ent = sess.entities or {}
    c = sess.controls()
    listed = []
    for unit, names in (("ct", (ent.get("camera_terminal") or {}).get("controls") or []),
                        ("pu", (ent.get("processing_unit") or {}).get("controls") or [])):
        listed += [(unit, n, True) for n in names]
    if all_selectors:
        adv = {n for _, n, _ in listed}
        listed += [("ct", n, False) for n in uvc_ctrl.CT_CONTROLS if n not in adv and ent.get("camera_terminal")]
        listed += [("pu", n, False) for n in uvc_ctrl.PU_CONTROLS if n not in adv and ent.get("processing_unit")]
    rows = []
    for unit, name, advertised in listed:
        r = c.read(name)
        r["unit"], r["advertised_in_descriptor"] = unit, advertised
        r["listed_by_device"] = bool(r.get("info") and (r["info"].get("get") or r["info"].get("set")))
        rows.append(r)
        if r.get("aborted") and r.get("calls") and r["calls"][0].get("rc_name") in ("kIOReturnNoDevice",
                                                                                 "LIBUSB_ERROR_NO_DEVICE"):
            break
    return {"controls": rows, "n_advertised": sum(1 for _, _, a in listed if a),
            "n_ok": sum(1 for r in rows if r.get("ok")), "extension_units": ent.get("extension_units"),
            "note": "extension-unit (XU) controls are listed from the descriptor only; never read or set blind"}


# ----------------------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="UVC endpoint-0 probe (opt-in; see module docstring)")
    ap.add_argument("cmd", choices=["probe", "descriptors", "ctrl-list", "get", "set", "stream-state"])
    ap.add_argument("--location", required=True, help="IORegistry locationID, e.g. 0x01100000")
    ap.add_argument("--vid")
    ap.add_argument("--pid")
    ap.add_argument("--backend", choices=BACKENDS, default="iokit-intf")
    ap.add_argument("--vc-if", type=int, default=None)
    ap.add_argument("--vs-if", default="", help="comma list of VideoStreaming interface numbers")
    ap.add_argument("--entities", default=None, help="JSON file with the 'entities' of a descriptors run")
    ap.add_argument("--controls", default="")
    ap.add_argument("--set", dest="set_", default="")
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--all-selectors", action="store_true")
    ap.add_argument("--desc-request", action="store_true")
    ap.add_argument("--allow-seize", action="store_true",
                    help="required for --backend libusb: WARNING libusb on darwin seizes every USB device")
    ap.add_argument("--timeout-ms", type=int, default=500)
    ap.add_argument("--deadline-s", type=float, default=60.0)
    ap.add_argument("--hold-ms", type=float, default=0.0, help="descriptors: keep the device plug-in N ms after reading")
    ap.add_argument("--hold-marker", default=None, help="descriptors: file written when the hold starts")
    ap.add_argument("--release-file", default=None, help="descriptors: the hold ends once this file exists")
    ap.add_argument("--hold-cap-ms", type=float, default=None)
    a = ap.parse_args(argv)
    t0 = time.time()
    state: dict[str, Any] = {"cmd": a.cmd, "backend": a.backend, "location": a.location, "in_progress": "setup",
                             "utc_started": t0, "host_ns_start": childutil.mach_ns()}
    if sys.platform != "darwin":
        state.update(ok=False, error="macOS only (IOKit)", exit_code=childutil.EXIT_USAGE)
        childutil.emit(state)
        return childutil.EXIT_USAGE
    entities = None
    if a.entities:
        try:
            d = json.loads(Path(a.entities).read_text(encoding="utf-8"))
            entities = d.get("entities", d)
        except Exception as e:
            state["entities_error"] = repr(e)
    sess = Ep0Session(int(a.location, 0), a.vid, a.pid, a.backend, a.vc_if, entities, a.timeout_ms, a.desc_request,
                      allow_seize=a.allow_seize)
    dl = childutil.Deadline(a.deadline_s, lambda: {**state, "requests_log": sess.log[-50:]}).start()
    rc = childutil.EXIT_OK
    try:
        if a.cmd == "descriptors":
            state["in_progress"] = "descriptors"
            hold = (lambda: childutil.hold(a.hold_ms, a.hold_marker, a.release_file, a.hold_cap_ms,
                                           info={"cmd": "descriptors"})) if a.hold_ms else None
            d = sess.descriptors(hold=hold)
            state.update(d)
            state["ok"] = bool(d.get("source"))
            if not state["ok"]:
                rc = childutil.EXIT_CAMERA
        else:
            state["in_progress"] = "transport setup"
            info = sess.setup()
            state["setup"] = info
            state["entities"] = sess.entities
            if not info.get("ok"):
                state.update(ok=False, error=(info.get("transport") or {}).get("error") or info.get("error"))
                if info.get("refused_seize"):
                    rc = childutil.EXIT_USAGE
                else:
                    rc = childutil.EXIT_NOT_FOUND if "not found" in str(state["error"]) else childutil.EXIT_CAMERA
            elif a.cmd == "probe":
                state["ok"] = True
            elif a.cmd == "ctrl-list":
                state["in_progress"] = "ctrl-list"
                state.update(ctrl_list(sess, a.all_selectors))
                state["ok"] = True
            elif a.cmd == "get":
                state["in_progress"] = "get"
                c = sess.controls()
                names = [n for n in a.controls.split(",") if n.strip()]
                state["values"] = [c.get_cur(n.strip()) for n in names]
                state["ok"] = all(v.get("ok") for v in state["values"]) if names else True
                if not state["ok"]:
                    rc = childutil.EXIT_CAMERA
            elif a.cmd == "set":
                state["in_progress"] = "set"
                c = sess.controls()
                pairs = childutil.parse_kv_list(a.set_)
                before = {n: c.get_cur(n) for n, _ in pairs}
                state["before"] = before
                state["sets"] = [c.set_cur(n, v) for n, v in pairs]
                if a.restore:
                    state["restore"] = [c.set_cur(n, before[n]["value"]) for n, _ in reversed(pairs)
                                        if before[n].get("ok") and before[n].get("value") is not None]
                state["ok"] = all(s.get("ok") for s in state["sets"])
                if not state["ok"]:
                    rc = childutil.EXIT_CAMERA
            elif a.cmd == "stream-state":
                state["in_progress"] = "stream-state"
                vs = [int(x) for x in a.vs_if.split(",") if x.strip()]
                state["streams"] = sess.stream_state(vs)
                state["ok"] = True
    except Exception as e:
        state.update(ok=False, error=f"{type(e).__name__}: {e}", error_class="exception")
        rc = childutil.EXIT_CAMERA
    finally:
        try:
            sess.close()
        except Exception:
            pass
    dl.cancel()
    state["in_progress"] = None
    state["requests_log"] = sess.log
    state["elapsed_s"] = round(time.time() - t0, 3)
    state["host_ns_end"] = childutil.mach_ns()
    state["exit_code"] = rc
    childutil.emit(state)
    return rc


if __name__ == "__main__":
    sys.exit(main())
