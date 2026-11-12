"""Media Foundation operations of pymf, each a line-by-line port of the wincam.cpp function it names.

Threading model (the same as wincam): the process is in the MTA; every blocking camera call runs through
``bounded.call`` (worker thread + deadline); samples arrive through the ASYNC source reader on MF's own work-queue
threads, into ``ReaderCallback`` (a comtypes COMObject implementing IMFSourceReaderCallback).

Why async and not a synchronous ReadSample on a worker thread: (1) a stalled stream then shows up as "no sample for
--timeout-ms" while the reader stays usable, so the close path (Flush, wait for OnFlush, release, Shutdown) runs in
the normal order; a synchronous ReadSample that never returns pins the reader inside a call that cannot be
cancelled, and the only way out is to abandon it. (2) The arrival time (QPC via time.perf_counter_ns, taken first
thing in OnReadSample) is measured at the same point as wincam's ``qpc_ns`` (callback entry), so the timestamp
comparison between the two probes is like for like. (3) It is the design a product would ship. The cost, which this
probe exists to measure, is that each sample enters Python (GIL acquisition on an MF thread, comtypes dispatch).
One honest difference remains: ctypes takes the GIL before OnReadSample's first line runs, so pymf's ``qpc_ns`` is
"callback entry + GIL wait". The controlling thread only holds the GIL briefly between Event waits, so the wait is
normally microseconds; W-PYMF's fps / timestamp comparison would show it if it were not.
"""
from __future__ import annotations

import ctypes
import json
import threading
import time
from ctypes import POINTER, byref, c_ulong, c_void_p
from typing import Any

import comtypes
from comtypes import COMObject, GUID

from . import bounded
from . import com as C
from . import parse as P

MASK = 0xFFFFFFFF
STAGE = {"stage": "start"}
PARTIAL: dict = {}
PARTIAL_LOCK = threading.Lock()


def set_stage(s: str) -> None:
    STAGE["stage"] = s


def qpc_ns() -> int:
    return time.perf_counter_ns()


def step_rec(name: str, hr: int | None, ms: float, timed_out: bool, exc: str | None = None) -> dict:
    """wincam step_rec(): {step, hr, hr_name, ms, timed_out}."""
    s = {"step": name, "hr": None if timed_out or hr is None else P.hr_hex(hr),
         "hr_name": "timeout" if timed_out else (None if hr is None else P.hr_name(hr)), "ms": ms, "timed_out": timed_out}
    if exc:
        s["python_exception"] = exc[-600:]
    return s


def error_obj(stage: str, hr: int | None, timed_out: bool, found: bool = True) -> dict:
    """wincam set_error() / session_error(): {stage, hr, hr_name, message, class, reason}."""
    if not found:
        cls, reason = "device_error", "device not present at re-enumeration"
    else:
        cls, reason = P.error_class(hr, timed_out)
    return {"stage": stage, "hr": None if timed_out or hr is None else P.hr_hex(hr),
            "hr_name": "timeout" if timed_out else (None if hr is None else P.hr_name(hr)),
            "message": "no return within --timeout-ms" if timed_out else (C.hr_message(hr) if hr is not None else ""),
            "class": cls, "reason": reason}


# ============================================================================================================ devices
def enum_mf() -> tuple[int, list[dict]]:
    """wincam enum_mf(): MFEnumDeviceSources(video capture) -> [{index, name, symlink, act}]. Reads attributes of
    the IMFActivate objects only (no ActivateObject)."""
    hr, a = C.new_attributes(1)
    if hr:
        return hr, []
    out: list[dict] = []
    try:
        hr = a.SetGUID(byref(C.MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE), byref(C.MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID)) & MASK
        if hr:
            return hr, []
        arr, n = POINTER(c_void_p)(), C.UINT32()
        hr = C.MFEnumDeviceSources(a, byref(arr), byref(n)) & MASK
        if hr:
            return hr, []
        for i in range(n.value):
            act = C.own(arr[i], C.IMFActivate)
            out.append({"index": i, "name": C.get_string(act, C.MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME) or "",
                        "symlink": C.get_string(act, C.MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK) or "",
                        "act": act})
        C.CoTaskMemFree(arr)
    finally:
        C.release(a)
    return 0, out


def release_devices(devs: list[dict], keep: Any = None) -> None:
    for d in devs:
        if d.get("act") is not None and d["act"] is not keep:
            C.release(d["act"])
            d["act"] = None


def resolve_mf(want: str, timeout_ms: int, j: dict) -> tuple[int, dict | None]:
    """wincam resolve_mf(): bounded enumeration + match_device. Returns (rc, device dict with 'act') and fills
    j["device"] / j["error"] / j["enumerate_ms"]."""
    t0 = time.perf_counter_ns()
    r = bounded.call(timeout_ms, lambda ctl: enum_mf())
    j["enumerate_ms"] = (time.perf_counter_ns() - t0) / 1e6
    if r.timed_out:
        j["error"] = {"stage": "enumerate", "class": "timeout"}
        return 5, None
    if r.exc or r.value is None:
        j["error"] = {"stage": "enumerate", "class": "other", "python_exception": (r.exc or "")[-600:]}
        return 4, None
    hr, devs = r.value
    if hr:
        j["error"] = {"stage": "enumerate", "hr": P.hr_hex(hr), "hr_name": P.hr_name(hr), "class": "other"}
        return 4, None
    idx, amb = P.match_device(want, [(d["symlink"], d["name"]) for d in devs])
    if idx == -2:
        j["error"] = {"stage": "match", "reason": "ambiguous --device", "matches": amb}
        release_devices(devs)
        return 2, None
    if idx < 0:
        j["error"] = {"stage": "match", "class": "device_error", "reason": "no MF device matches --device",
                      "available": [d["symlink"] for d in devs]}
        release_devices(devs)
        return 3, None
    dev = devs[idx]
    release_devices(devs, keep=dev["act"])
    j["device"] = {"index": dev["index"], "friendly_name": dev["name"], "symlink": dev["symlink"],
                   "usb": P.parse_usb_ids(dev["symlink"])}
    return 0, dev


def ref(p, iface):
    """A second, independent COM reference to ``p`` for a bounded closure: wincam's by-value ComPtr capture
    (``[act]``, an AddRef). ``C.release`` NULLs the caller's wrapper in place, and comtypes' __del__ Releases a
    wrapper that goes out of scope, so without its own reference an abandoned worker could still be inside a call on
    an object whose last caller reference is gone (close_session's shutdown, or a dropped device list): a
    use-after-free. The closure releases its reference when (if ever) its call returns. None for None / NULL."""
    if p is None or not p:
        return None
    return C.borrow(ctypes.cast(p, c_void_p).value, iface)


def activate(act, timeout_ms: int) -> bounded.Timed:
    """wincam activate_mf(): IMFActivate::ActivateObject(IMFMediaSource), bounded. value = (hr, src). A call that
    completes after the caller gave up shuts its own source down. The worker holds its own IMFActivate reference
    (``ref``), so close_session may shut down and release the session's reference while ActivateObject hangs."""
    mine = ref(act, C.IMFActivate)

    def f(ctl: bounded.CallCtl):
        try:
            raw = c_void_p()
            hr = mine.ActivateObject(byref(C.IMFMediaSource._iid_), byref(raw)) & MASK
            src = C.own(raw, C.IMFMediaSource)
            if ctl.abandoned and src is not None:
                src.Shutdown()
                mine.ShutdownObject()
                C.release(src)
                src = None
            return hr, src
        finally:
            C.release(mine)
    return bounded.call(timeout_ms, f)


def resolve_url(url: str, timeout_ms: int) -> bounded.Timed:
    """Offline self-test source (no camera): IMFSourceResolver::CreateObjectFromURL(MEDIASOURCE | READ) on a local
    file. value = (hr, src)."""
    def f(ctl: bounded.CallCtl):
        raw = c_void_p()
        hr = C.MFCreateSourceResolver(byref(raw)) & MASK
        if hr:
            return hr, None
        res = C.own(raw, C.IMFSourceResolver)
        ot, unk = ctypes.c_int(), c_void_p()
        hr = res.CreateObjectFromURL(url, C.MF_RESOLUTION_MEDIASOURCE | C.MF_RESOLUTION_READ, None, byref(ot),
                                     byref(unk)) & MASK
        C.release(res)
        if hr:
            return hr, None
        u = C.own(unk, comtypes.IUnknown)
        qh, src = C.query(u, C.IMFMediaSource)
        C.release(u)
        return qh, src
    return bounded.call(timeout_ms, f)


def shutdown_mf(holder: dict, timeout_ms: int) -> tuple[list[dict], bool]:
    """wincam shutdown_mf(): IMFMediaSource::Shutdown, then IMFActivate::ShutdownObject, each bounded, each releasing
    its object on the worker. ``holder`` = {"src": ..., "act": ...}; both are taken out of it. Returns (steps, hung)."""
    steps, hung = [], False
    src, holder["src"] = holder.get("src"), None
    if src is not None:
        def fs(ctl, s=src):
            h = s.Shutdown() & MASK
            C.release(s)
            return h
        r = bounded.call(timeout_ms, fs)
        steps.append(step_rec("source_shutdown", r.value if not r.exc else P.E_FAIL, r.ms, r.timed_out, r.exc))
        hung |= r.timed_out
    src = None
    act, holder["act"] = holder.get("act"), None
    if act is not None:
        def fa(ctl, a=act):
            h = a.ShutdownObject() & MASK
            C.release(a)
            return h
        r = bounded.call(timeout_ms, fa)
        steps.append(step_rec("activate_shutdown_object", r.value if not r.exc else P.E_FAIL, r.ms, r.timed_out, r.exc))
        hung |= r.timed_out
    return steps, hung


# ============================================================================================================ attributes
def attrs_json(a) -> dict:
    """wincam attrs_json(): every attribute of an IMFAttributes, named via parse.GUID_NAMES."""
    o: dict[str, Any] = {}
    if a is None:
        return o
    n = C.UINT32()
    a.GetCount(byref(n))
    for i in range(n.value):
        key, v = GUID(), C.PROPVARIANT()
        if a.GetItemByIndex(i, byref(key), byref(v)) & 0x80000000:
            continue
        k = P.guid_name(C.gtext(key))
        vt = v.vt
        try:
            if vt == C.VT_UI4:
                o[k] = v.u.ulVal
            elif vt == C.VT_UI8:
                q = v.u.uhVal
                o[k] = [(q >> 32) & MASK, q & MASK] if C.gtext(key) in C.PAIR_ATTRS else q
            elif vt == C.VT_I8:
                o[k] = v.u.hVal
            elif vt == C.VT_R8:
                o[k] = v.u.dblVal
            elif vt == C.VT_CLSID:
                o[k] = P.guid_name(C.gtext(v.u.puuid.contents)) if v.u.puuid else None
            elif vt == C.VT_LPWSTR:
                o[k] = ctypes.wstring_at(v.u.pwszVal) if v.u.pwszVal else ""
            elif vt == (C.VT_VECTOR | C.VT_UI1):
                cnt = v.u.caub.cElems
                head = ctypes.string_at(v.u.caub.pElems, min(cnt, 48)) if cnt else b""
                o[k] = {"blob_bytes": cnt, "hex_head": head.hex()}
            elif vt == C.VT_UNKNOWN:
                o[k] = "<IUnknown>"
            else:
                o[k] = f"<vt {vt}>"
        finally:
            C.PropVariantClear(byref(v))
    return o


def type_fields(t) -> dict:
    """Subtype / size / rate of an IMFMediaType (MFGetAttributeSize / MFGetAttributeRatio semantics: a missing
    attribute leaves w = h = 0 and fps 0/1, as wincam's initial values)."""
    _hr, sg = C.get_guid(t, C.MF_MT_SUBTYPE)
    sg = sg or "00000000-0000-0000-0000-000000000000"
    _ok, w, h = C.get_pair(t, C.MF_MT_FRAME_SIZE)
    ok, fn, fd = C.get_pair(t, C.MF_MT_FRAME_RATE, (0, 1))
    return {"subtype_guid": sg, "subtype": P.subtype_text(sg), "width": w, "height": h, "fps_num": fn,
            "fps_den": fd if ok else 1}


# ============================================================================================================ formats
def presentation_streams(src) -> tuple[int, list[dict]]:
    """wincam formats_mf() presentation-descriptor part: per stream attributes, stream id, handler type count."""
    out: list[dict] = []
    raw = c_void_p()
    hr = src.CreatePresentationDescriptor(byref(raw)) & MASK
    if hr:
        return hr, out
    pd = C.own(raw, C.IMFPresentationDescriptor)
    try:
        n = C.DWORD()
        pd.GetStreamDescriptorCount(byref(n))
        for i in range(n.value):
            sel, sraw = C.BOOL(), c_void_p()
            if pd.GetStreamDescriptorByIndex(i, byref(sel), byref(sraw)) & 0x80000000:
                continue
            sd = C.own(sraw, C.IMFStreamDescriptor)
            sid = C.DWORD()
            sd.GetStreamIdentifier(byref(sid))
            s = {"stream_index": i, "selected_by_default": bool(sel.value), "stream_identifier": sid.value,
                 "attributes": attrs_json(sd)}
            hraw, tc = c_void_p(), C.DWORD()
            if not sd.GetMediaTypeHandler(byref(hraw)) & 0x80000000:
                th = C.own(hraw, C.IMFMediaTypeHandler)
                th.GetMediaTypeCount(byref(tc))
                major = GUID()
                if not th.GetMajorType(byref(major)) & 0x80000000:
                    s["major_type"] = P.guid_name(C.gtext(major))
                C.release(th)
            s["handler_type_count"] = tc.value
            out.append(s)
            C.release(sd)
    finally:
        C.release(pd)
    return 0, out


def make_reader(src, callback=None) -> tuple[int, Any]:
    """MFCreateSourceReaderFromMediaSource with converters disabled and DISCONNECT_MEDIASOURCE_ON_SHUTDOWN (so the
    source shutdowns stay explicit and timed), plus the async callback when given (wincam open_session)."""
    hr, ra = C.new_attributes(3)
    if hr:
        return hr, None
    try:
        ra.SetUINT32(byref(C.MF_READWRITE_DISABLE_CONVERTERS), 1)
        ra.SetUINT32(byref(C.MF_SOURCE_READER_DISCONNECT_MEDIASOURCE_ON_SHUTDOWN), 1)
        if callback is not None:
            unk = callback.QueryInterface(comtypes.IUnknown)
            ra.SetUnknown(byref(C.MF_SOURCE_READER_ASYNC_CALLBACK), unk)
            C.release(unk)
        raw = c_void_p()
        hr = C.MFCreateSourceReaderFromMediaSource(src, ra, byref(raw)) & MASK
        return hr, C.own(raw, C.IMFSourceReader)
    finally:
        C.release(ra)


def native_types(rd) -> list[dict]:
    """wincam formats_mf() reader part: every native type of every stream, flagged, with counts and MJPG sizes."""
    streams = []
    for si in range(64):
        probe = c_void_p()
        h = rd.GetNativeMediaType(si, 0, byref(probe)) & MASK
        C.release(C.own(probe, C.IMFMediaType))
        if h == P.MF_E_INVALIDSTREAMNUMBER:
            break
        ts: list[dict] = []
        ti = 0
        while True:
            raw = c_void_p()
            if rd.GetNativeMediaType(si, ti, byref(raw)) & 0x80000000:
                break
            t = C.own(raw, C.IMFMediaType)
            x = {"stream_index": si, "type_index": ti, **type_fields(t)}
            x["fps"] = P.fps_of(x["fps_num"], x["fps_den"])
            extra: dict[str, Any] = {}
            ok, a1, a2 = C.get_pair(t, C.MF_MT_FRAME_RATE_RANGE_MIN)
            if ok:
                extra["frame_rate_range_min"] = [a1, a2]
            ok, a1, a2 = C.get_pair(t, C.MF_MT_FRAME_RATE_RANGE_MAX)
            if ok:
                extra["frame_rate_range_max"] = [a1, a2]
            hr_ss, ss = C.get_uint32(t, C.MF_MT_SAMPLE_SIZE)
            if not hr_ss:
                extra["sample_size"] = ss
            hr_mj, major = C.get_guid(t, C.MF_MT_MAJOR_TYPE)
            if not hr_mj and major:
                extra["major_type"] = P.guid_name(major)
            x["_extra"] = extra
            ts.append(x)
            C.release(t)
            ti += 1
        P.flag_types(ts)
        types = []
        for x in ts:
            e = {k: x[k] for k in ("stream_index", "type_index", "subtype", "subtype_guid", "width", "height",
                                   "fps_num", "fps_den", "fps", "flags")}
            e.update(x["_extra"])
            types.append(e)
        streams.append({"stream_index": si, "type_count": len(types), "subtype_counts": P.subtype_counts(types),
                        "mjpg_sizes": P.mjpg_sizes(types), "types": types})
    return streams


# ============================================================================================================ controls
def get_ifaces(src) -> dict:
    """wincam get_ifaces(): IAMCameraControl / IAMVideoProcAmp / IKsControl queried from the IMFMediaSource."""
    return {"cc": C.query(src, C.IAMCameraControl)[1], "pa": C.query(src, C.IAMVideoProcAmp)[1],
            "ks": C.query(src, C.IKsControl)[1]}


def release_ifaces(c: dict) -> None:
    for k in ("cc", "pa", "ks"):
        C.release(c.get(k))
        c[k] = None


def _ks_set_guid(d) -> GUID:
    return C.PROPSETID_VIDCAP_CAMERACONTROL if d[0] == 0 else C.PROPSETID_VIDCAP_VIDEOPROCAMP


def _ks_struct_type(d):
    if d[0] == 0 and d[1] in (P.CC_PANTILT, P.CC_PANTILT_RELATIVE):
        return C.KSPROPERTY_CAMERACONTROL_S2
    if d[0] == 0 and d[1] == P.CC_FOCAL_LENGTH:
        return C.KSPROPERTY_CAMERACONTROL_FOCAL_LENGTH_S
    if d[0] == 1 and d[1] == P.PA_WHITEBALANCE_COMPONENT:
        return C.KSPROPERTY_CAMERACONTROL_S2
    return C.KSPROPERTY_CAMERACONTROL_S


def _ks_input(d, flags: int):
    st = _ks_struct_type(d)()
    st.Property.s.Set = _ks_set_guid(d)
    st.Property.s.Id = d[1]
    st.Property.s.Flags = flags
    return st


def ks_describe(ks, d, typ: int) -> tuple[int, bytes]:
    """wincam ks_describe(): BASICSUPPORT / DEFAULTVALUES reply (KSPROPERTY_DESCRIPTION + member lists)."""
    inp = _ks_input(d, typ)
    out = ctypes.create_string_buffer(512)
    ret = c_ulong()
    hr = ks.KsProperty(byref(inp), ctypes.sizeof(inp), out, len(out), byref(ret)) & MASK
    if not (hr & 0x80000000) and ret.value >= P.KSDESC_SIZE:
        dsize = int.from_bytes(out.raw[4:8], "little")
        if len(out) < dsize < 65536:
            out = ctypes.create_string_buffer(dsize)
            hr = ks.KsProperty(byref(inp), ctypes.sizeof(inp), out, len(out), byref(ret)) & MASK
    if hr & 0x80000000:
        return hr, b""
    return hr, out.raw[:min(ret.value, len(out))]


def read_ctl_ks(c: dict, d, r: dict, want_value: bool) -> None:
    """wincam read_ctl_ks(): KS BASICSUPPORT (range), DEFAULTVALUES (default) and GET (value, flags, caps)."""
    ks = c["ks"]
    r["hr_ks_basic"], buf = ks_describe(ks, d, C.KSPROPERTY_TYPE_BASICSUPPORT)
    k_basic = P.ks_parse_members(buf, False) if not (r["hr_ks_basic"] & 0x80000000) else None
    if k_basic is not None:
        r["ks_basic_len"] = len(buf)
        if len(buf) >= P.KSDESC_SIZE:
            r["ks_members_lists"] = int.from_bytes(buf[32:36], "little")
        if not k_basic["has_range"]:
            r["ks_basic_hex"] = buf[:96].hex()
    r["hr_ks_default"], buf2 = ks_describe(ks, d, C.KSPROPERTY_TYPE_DEFAULTVALUES)
    k_def = P.ks_parse_members(buf2, True) if not (r["hr_ks_default"] & 0x80000000) else None
    ranges = (k_basic or {}).get("ranges", []) + (k_def or {}).get("ranges", [])
    r["ks_ranges"] = ranges
    if k_basic and k_basic["has_range"]:
        r.update(ks_has_range=True, ks_mn=k_basic["min"], ks_mx=k_basic["max"], ks_step=k_basic["step"])
    dflt = next((x for x in (k_basic, k_def) if x and x["has_default"]), None)
    if dflt:
        r.update(ks_has_default=True, ks_def=dflt["default"])
    if not want_value:
        return
    st = _ks_input(d, C.KSPROPERTY_TYPE_GET)
    ret = c_ulong()
    r["hr_ks_get"] = ks.KsProperty(byref(st), ctypes.sizeof(st), byref(st), ctypes.sizeof(st), byref(ret)) & MASK
    if not (r["hr_ks_get"] & 0x80000000):
        r["has_value"] = True
        if isinstance(st, C.KSPROPERTY_CAMERACONTROL_FOCAL_LENGTH_S):
            r.update(val=st.lOcularFocalLength, has_value2=True, val2=st.lObjectiveFocalLengthMax)
        elif isinstance(st, C.KSPROPERTY_CAMERACONTROL_S2):
            r.update(val=st.Value1, flags=st.Flags, caps=st.Capabilities, val2=st.Value2, has_value2=True)
        else:
            r.update(val=st.Value, flags=st.Flags, caps=st.Capabilities)


def read_ctl(c: dict, d, full: bool = True) -> dict:
    """wincam read_ctl(): IAM GetRange + Get first; then (listing) always the KS cross-check, with the KS range taken
    when the IAM range is degenerate (0..0 step 0); when IAM rejects the id, the KS path alone."""
    r = P.new_ctl_read()
    iface = c["cc"] if d[0] == 0 else c["pa"]
    if iface is not None:
        mn, mx, step, dflt, caps = (ctypes.c_long() for _ in range(5))
        r["hr_iam_range"] = iface.GetRange(d[1], byref(mn), byref(mx), byref(step), byref(dflt), byref(caps)) & MASK
        if not (r["hr_iam_range"] & 0x80000000):
            r.update(supported=True, via="IAMCameraControl" if d[0] == 0 else "IAMVideoProcAmp", has_range=True,
                     has_default=True, mn=mn.value, mx=mx.value, step=step.value, caps=caps.value)
            r["def"] = dflt.value
            v, f = ctypes.c_long(), ctypes.c_long()
            r["hr_iam_get"] = iface.Get(d[1], byref(v), byref(f)) & MASK
            r["has_value"] = not (r["hr_iam_get"] & 0x80000000)
            if r["has_value"]:
                r.update(val=v.value, flags=f.value)
    if r["supported"]:
        if full and c["ks"] is not None:
            tmp = P.new_ctl_read()
            read_ctl_ks(c, d, tmp, False)
            for k in ("hr_ks_basic", "hr_ks_default", "ks_ranges", "ks_basic_hex", "ks_basic_len", "ks_members_lists",
                      "ks_has_range", "ks_mn", "ks_mx", "ks_step", "ks_has_default", "ks_def"):
                r[k] = tmp[k]
            if r["mn"] == 0 and r["mx"] == 0 and r["step"] == 0 and r["ks_has_range"] and \
                    not (r["ks_mn"] == 0 and r["ks_mx"] == 0):
                r.update(iam_range_degenerate=True, mn=r["ks_mn"], mx=r["ks_mx"], step=r["ks_step"])
                if r["ks_has_default"]:
                    r["def"] = r["ks_def"]
        return r
    if c["ks"] is None:
        return r
    r.update(mn=0, mx=0, step=0, caps=0)
    r["def"] = 0
    read_ctl_ks(c, d, r, True)
    r.update(has_range=r["ks_has_range"], mn=r["ks_mn"], mx=r["ks_mx"], step=r["ks_step"],
             has_default=r["ks_has_default"])
    r["def"] = r["ks_def"]
    if (r["hr_ks_get"] is not None and not (r["hr_ks_get"] & 0x80000000)) or \
            (r["hr_ks_basic"] is not None and not (r["hr_ks_basic"] & 0x80000000)):
        r.update(supported=True, via="IKsControl")
    return r


def set_ctl(c: dict, d, via: str, value: int, flags: int) -> int:
    """wincam set_ctl(): IAM Set, else KS SET for single-value controls (multi-value controls: E_NOTIMPL)."""
    if via == "IAMCameraControl" and c["cc"] is not None:
        return c["cc"].Set(d[1], value, flags) & MASK
    if via == "IAMVideoProcAmp" and c["pa"] is not None:
        return c["pa"].Set(d[1], value, flags) & MASK
    if c["ks"] is None:
        return P.E_NOINTERFACE
    if _ks_struct_type(d) is not C.KSPROPERTY_CAMERACONTROL_S:
        return P.E_NOTIMPL
    s = _ks_input(d, C.KSPROPERTY_TYPE_SET)
    s.Value, s.Flags, s.Capabilities = value, flags, 0
    ret = c_ulong()
    return c["ks"].KsProperty(byref(s), ctypes.sizeof(s), byref(s), ctypes.sizeof(s), byref(ret)) & MASK


def apply_set(c: dict, rq: dict, timeout_ms: int) -> dict:
    """wincam apply_set(): read before, set, read back, all in one bounded call. Returns {rec, timed_out, prev}."""
    d = rq["def"]

    def f(ctl):
        t0 = time.perf_counter_ns()
        before = read_ctl(c, d, False)
        j = {"control": P.ctl_key(d), "requested": rq["raw_value"], "supported": before["supported"],
             "via": before["via"] or None, "before_value": before["val"] if before["has_value"] else None,
             "before_flags": before["flags"] if before["has_value"] else None}
        if not before["supported"]:
            j.update(hr_set=P.hr_hex(P.E_PROP_ID_UNSUPPORTED), hr_set_name=P.hr_name(P.E_PROP_ID_UNSUPPORTED),
                     matches=False)
            return j, before
        v = before["val"] if (rq["is_auto"] or rq["is_manual_keep"]) else rq["value"]
        hs = set_ctl(c, d, before["via"], v, rq["flags"])
        j.update(set_value=v, set_flags=rq["flags"], set_flags_names=P.flags_names(rq["flags"]), hr_set=P.hr_hex(hs),
                 hr_set_name=P.hr_name(hs))
        after = read_ctl(c, d, False)
        j.update(readback_value=after["val"] if after["has_value"] else None,
                 readback_flags=after["flags"] if after["has_value"] else None,
                 readback_flags_names=P.flags_names(after["flags"]) if after["has_value"] else None)
        j["matches"] = (not P.failed(hs)) and after["has_value"] and (
            bool(after["flags"] & 1) if (rq["flags"] & 1) else (after["val"] == v and bool(after["flags"] & 2)))
        j["call_ms"] = (time.perf_counter_ns() - t0) / 1e6
        return j, before
    r = bounded.call(timeout_ms, f)
    if r.timed_out or r.value is None:
        rec = {"control": P.ctl_key(d), "requested": rq["raw_value"], "timed_out": r.timed_out, "call_ms": r.ms}
        if r.exc:
            rec["python_exception"] = r.exc[-600:]
        return {"rec": rec, "timed_out": r.timed_out, "prev": None}
    rec, before = r.value
    rec["timed_out"] = False
    prev = (before["via"], before["val"], before["flags"]) if before["has_value"] and before["via"] else None
    return {"rec": rec, "timed_out": False, "prev": prev}


def restore_one(c: dict, d, via: str, val: int, flags: int, timeout_ms: int) -> tuple[dict, bool]:
    """wincam restore_one()."""
    def f(ctl):
        j = {"control": P.ctl_key(d), "restore_value": val, "restore_flags": flags}
        h = set_ctl(c, d, via, val, flags)
        j.update(hr_set=P.hr_hex(h), hr_set_name=P.hr_name(h))
        a = read_ctl(c, d, False)
        j.update(readback_value=a["val"] if a["has_value"] else None,
                 readback_flags=a["flags"] if a["has_value"] else None)
        return j
    r = bounded.call(timeout_ms, f)
    if r.timed_out or r.value is None:
        return {"control": P.ctl_key(d), "timed_out": True}, True
    r.value["timed_out"] = False
    return r.value, False


def run_controls(src, j: dict, read_only: bool, sets: str, set_flags: int, restore: bool, timeout_ms: int) -> int:
    """wincam run_controls(): list every control (bounded per control), GET health, then sets and restore. rc."""
    c = get_ifaces(src)
    to = False   # a control call timed out: the interfaces are then left alone (never touch a hung source again)
    try:
        j["interfaces"] = {"IAMCameraControl": c["cc"] is not None, "IAMVideoProcAmp": c["pa"] is not None,
                           "IKsControl": c["ks"] is not None}
        lst = []
        for d in P.CTLS:
            base = {"set": "camera_control" if d[0] == 0 else "video_proc_amp", "id": d[1], "name": d[2]}
            if to:
                lst.append({**base, "skipped": "earlier control call timed out"})
                continue
            t0 = time.perf_counter_ns()
            r = bounded.call(timeout_ms, lambda ctl, d=d: read_ctl(c, d))
            if r.timed_out:
                to = True
                lst.append({**base, "timed_out": True, "call_ms": r.ms})
                continue
            if r.value is None:
                lst.append({**base, "supported": False, "python_exception": (r.exc or "")[-600:], "call_ms": r.ms})
                continue
            lst.append(P.ctl_json(d, r.value, (time.perf_counter_ns() - t0) / 1e6))
        j["controls"] = lst
        j["supported_count"] = sum(1 for e in lst if e.get("supported") is True)
        if to:
            j["error"] = error_obj("control_query", P.E_FAIL, True)
            return 5
        g = P.get_health(lst)
        first = g.pop("first_fail_hr")
        j.update(g)
        if g["device_not_answering"]:
            j["error"] = error_obj("control_get", first, False)
            j["sets"] = []
            return 4
        if read_only or not sets:
            j["sets"] = []
            return 0
        reqs = P.parse_sets(sets, set_flags)
        out, prevs = [], []
        for rq in reqs:
            so = apply_set(c, rq, timeout_ms)
            out.append(so["rec"])
            if so["timed_out"]:
                to = True
                break
            if so["prev"]:
                prevs.append((rq["def"],) + so["prev"])
        j["sets"] = out
        if restore and not to:
            rs = []
            for d, via, v, f in reversed(prevs):
                rec, t = restore_one(c, d, via, v, f, timeout_ms)
                rs.append(rec)
                if t:
                    to = True
                    break
            j["restore"] = rs
        if to:
            j["error"] = error_obj("control_set", P.E_FAIL, True)
            return 5
        return 0
    finally:
        if not to:
            release_ifaces(c)


# ============================================================================================================ streaming
class StreamState:
    """wincam StreamState: counters and outputs shared by the callback and the controlling thread."""

    def __init__(self, req_w: int = 0, req_h: int = 0, max_frames: int = 0):
        self.mu = threading.RLock()
        self.reader = None
        self.stop = False
        self.ev_sample = threading.Event()
        self.ev_flush = threading.Event()
        self.frames = self.ticks = self.nulls = self.ok_frames = self.soi_eoi = self.sof_match = 0
        self.with_meta = self.with_capmeta = self.bytes = self.discont = 0
        self.err: int | None = None
        self.err_flags = 0
        self.err_at_frame = 0
        self.err_exc: str | None = None
        self.eos = False
        self.issue_ns = self.first_ns = self.last_ns = self.progress_ns = 0
        self.req_w, self.req_h, self.max_frames = req_w, req_h, max_frames
        self.jsonl = None
        self.mjpeg = None
        self.mjpeg_off = 0
        self.save_mode = 0
        self.save_every = 1
        self.saved = 0
        self.flag_counts: dict[str, int] = {}
        self.issuing = 0
        self.callback_ns_total = 0      # time spent inside OnReadSample (Python), for the CPU comparison
        self.sample_fn = None           # per-sample handler (st, arr, flags, ts, sample); None = process_sample

    def set_err(self, hr: int, flags: int = 0) -> None:
        if self.err is None:
            self.err, self.err_flags, self.err_at_frame = hr & MASK, flags, self.frames


class ReaderCallback(COMObject):
    """IMFSourceReaderCallback in Python (wincam ReaderCB). OnReadSample runs on an MF work-queue thread."""
    _com_interfaces_ = [C.IMFSourceReaderCallback]

    def __init__(self, st: StreamState):
        super().__init__()
        self.st = st

    def OnFlush(self, this, stream_index):  # noqa: N802 - COM method name
        self.st.ev_flush.set()
        return 0

    def OnEvent(self, this, stream_index, event):  # noqa: N802
        return 0

    def OnReadSample(self, this, hr, stream_index, flags, ts, psample):  # noqa: N802
        arr = time.perf_counter_ns()
        st = self.st
        nxt = None
        try:
            with st.mu:
                hr &= MASK
                if hr & 0x80000000:
                    st.set_err(hr, flags)
                    st.ev_sample.set()
                    return 0
                if flags & C.MF_SOURCE_READERF_ERROR:
                    st.set_err(P.E_FAIL, flags)
                    st.ev_sample.set()
                    return 0
                if flags & C.MF_SOURCE_READERF_ENDOFSTREAM:
                    st.eos = True
                    st.ev_sample.set()
                    return 0
                if flags & C.MF_SOURCE_READERF_STREAMTICK:
                    st.ticks += 1
                for bit, name in ((C.MF_SOURCE_READERF_CURRENTMEDIATYPECHANGED, "current_media_type_changed"),
                                  (C.MF_SOURCE_READERF_NATIVEMEDIATYPECHANGED, "native_media_type_changed"),
                                  (C.MF_SOURCE_READERF_ALLEFFECTSREMOVED, "all_effects_removed")):
                    if flags & bit:
                        st.flag_counts[name] = st.flag_counts.get(name, 0) + 1
                st.progress_ns = arr
                if psample:
                    s = C.borrow(psample, C.IMFSample)
                    try:
                        (st.sample_fn or process_sample)(st, arr, flags, ts, s)
                    finally:
                        C.release(s)
                else:
                    st.nulls += 1
                if not st.stop and st.reader is not None and (st.max_frames == 0 or st.frames < st.max_frames):
                    nxt = st.reader
                    nxt.AddRef()
                    st.issuing += 1
            if nxt is not None:
                h2 = nxt.ReadSample(C.MF_SOURCE_READER_FIRST_VIDEO_STREAM, 0, None, None, None, None) & MASK
                nxt.Release()
                nxt = None
                with st.mu:
                    st.issuing -= 1
                    if h2 & 0x80000000:
                        st.set_err(h2)
        except BaseException as e:  # noqa: BLE001 - never raise into MF
            with st.mu:
                st.set_err(P.E_FAIL)
                st.err_exc = f"{type(e).__name__}: {e}"
        finally:
            st.callback_ns_total += time.perf_counter_ns() - arr
            st.ev_sample.set()
        return 0


def process_sample(st: StreamState, arr: int, flags: int, ts: int, s) -> None:
    """wincam ReaderCB::process_sample(): per-frame checks, optional byte-exact save, UVC metadata, frames.jsonl."""
    seq = st.frames
    st.frames += 1
    if not st.first_ns:
        st.first_ns = arr
    st.last_ns = arr
    stime, sdur = C.LONGLONG(), C.LONGLONG()
    hst = s.GetSampleTime(byref(stime)) & MASK
    s.GetSampleDuration(byref(sdur))
    _h, disc = C.get_uint32(s, C.MFSampleExtension_Discontinuity)
    if disc:
        st.discont += 1
    hdev, devts = C.get_uint64(s, C.MFSampleExtension_DeviceTimestamp)
    data, off = b"", -1
    braw = c_void_p()
    if not s.ConvertToContiguousBuffer(byref(braw)) & 0x80000000:
        buf = C.own(braw, C.IMFMediaBuffer)
        hl, data = C.lock_bytes(buf)
        C.release(buf)
    ji = P.jpeg_info(data)
    n = len(data)
    if st.mjpeg is not None and (st.save_mode == 1 or (st.save_mode == 2 and seq % st.save_every == 0)):
        off = st.mjpeg_off
        st.mjpeg.write(data)
        st.mjpeg_off += n
        st.saved += 1
    st.bytes += n
    sizeok = ji["sof_w"] == st.req_w and ji["sof_h"] == st.req_h
    eoiok = ji["eoi"] or ji["eoi_trailing"] >= 0
    if ji["soi"] and eoiok:
        st.soi_eoi += 1
    if sizeok:
        st.sof_match += 1
    if ji["soi"] and eoiok and sizeok:
        st.ok_frames += 1
    um, capmeta = None, False
    mraw = c_void_p()
    if not s.GetUnknown(byref(C.MFSampleExtension_CaptureMetadata), byref(C.IMFAttributes._iid_), byref(mraw)) \
            & 0x80000000:
        capmeta = True
        md = C.own(mraw, C.IMFAttributes)
        rraw = c_void_p()
        if not md.GetUnknown(byref(C.MF_CAPTURE_METADATA_FRAME_RAWSTREAM), byref(C.IMFMediaBuffer._iid_),
                             byref(rraw)) & 0x80000000:
            rb = C.own(rraw, C.IMFMediaBuffer)
            hl, mbytes = C.lock_bytes(rb)
            if not hl:
                um = P.parse_uvc_meta(mbytes)
            C.release(rb)
        C.release(md)
    if capmeta:
        st.with_capmeta += 1
    present = bool(um and um["present"])
    if present:
        st.with_meta += 1
    if st.jsonl is None:
        return
    f: dict[str, Any] = {"seq": seq, "qpc_ns": arr, "sample_time_100ns": stime.value if not hst else None,
                         "sample_duration": sdur.value, "readsample_ts_100ns": ts, "flags": flags,
                         "discontinuity": disc != 0, "bytes": n, "soi": ji["soi"], "eoi": ji["eoi"],
                         "eoi_trailing_bytes": ji["eoi_trailing"],
                         "sof0_w": ji["sof_w"] if ji["sof_w"] >= 0 else None,
                         "sof0_h": ji["sof_h"] if ji["sof_h"] >= 0 else None}
    if ji["sof_marker"] >= 0 and ji["sof_marker"] != 0xC0:
        f["sof_marker"] = ji["sof_marker"]
    for k_out, k_in in (("uvc_pts", "pts"), ("uvc_scr_stc", "stc"), ("uvc_scr_sof", "sof"), ("uvc_eof_pts", "eof_pts"),
                        ("uvc_eof_scr_stc", "eof_stc"), ("uvc_eof_scr_sof", "eof_sof")):
        f[k_out] = um[k_in] if present else None
    f["has_metadata"] = present
    f["capture_metadata_attr"] = capmeta
    if not hdev:
        f["mf_device_timestamp"] = devts
    if off >= 0:
        f["mjpeg_offset"] = off
        f["mjpeg_len"] = n
    st.jsonl.write(json.dumps(f, separators=(",", ":")) + "\n")
    st.jsonl.flush()


class Session:
    """wincam Session: one open of one camera (or of a file source in --url self-test mode)."""

    def __init__(self) -> None:
        self.symlink = ""
        self.name = ""
        self.act = None
        self.src = None
        self.reader = None
        self.cb: ReaderCallback | None = None
        self.st: StreamState | None = None
        self.ctl: dict = {"cc": None, "pa": None, "ks": None}
        self.steps: list[dict] = []
        self.negotiated: dict = {}
        self.enumerate_ms = self.activate_ms = self.reader_ms = self.settype_ms = -1.0
        self.first_frame_ms = self.open_to_first_ms = -1.0
        self.flush_ms = self.reader_release_ms = self.shutdown_ms = self.shutdown_object_ms = self.close_ms = -1.0
        self.stage_failed = ""
        self.hr: int | None = 0
        self.timed_out = False
        self.unreleasable = False
        self.found = True
        self.t_open_ns = 0

    def fail(self, stage: str, hr: int | None, timed_out: bool) -> None:
        if not self.stage_failed:
            self.stage_failed, self.hr, self.timed_out = stage, hr, timed_out

    def error(self) -> dict | None:
        if not self.stage_failed:
            return None
        return error_obj(self.stage_failed, self.hr, self.timed_out, self.found)


def open_session(s: Session, target: str, mode: dict, st: StreamState, timeout_ms: int, url: bool = False) -> bool:
    """wincam open_session(): enumerate (fresh each call) -> activate -> async reader -> explicit native type ->
    first ReadSample. ``mode`` = {subtype, w, h, fps}. With ``url`` the source is a local file (offline self-test)."""
    s.st, s.symlink, s.t_open_ns = st, target, qpc_ns()
    if url:
        set_stage("resolve_url")
        r = resolve_url(target, timeout_ms)
        s.activate_ms = r.ms
        hr, src = r.value if r.value else (P.E_FAIL, None)
        s.steps.append(step_rec("resolve_url", hr, r.ms, r.timed_out, r.exc))
        if r.timed_out or P.failed(hr) or src is None:
            s.fail("resolve_url", hr, r.timed_out)
            return False
        s.src, s.name = src, target
    else:
        set_stage("enumerate")
        en = bounded.call(timeout_ms, lambda ctl: enum_mf())
        s.enumerate_ms = en.ms
        ehr, devs = en.value if en.value else (P.E_FAIL, [])
        s.steps.append(step_rec("enumerate", ehr, en.ms, en.timed_out, en.exc))
        if en.timed_out or P.failed(ehr):
            s.fail("enumerate", ehr, en.timed_out)
            return False
        for d in devs:
            if d["symlink"].lower() == target.lower():
                s.act, s.name = d["act"], d["name"]
                break
        release_devices(devs, keep=s.act)
        if s.act is None:
            s.found = False
            s.fail("device_not_found", P.HR_DEVICE_NOT_CONNECTED, False)
            return False
        set_stage("activate")
        a = activate(s.act, timeout_ms)
        s.activate_ms = a.ms
        ahr, src = a.value if a.value else (P.E_FAIL, None)
        s.steps.append(step_rec("activate", ahr, a.ms, a.timed_out, a.exc))
        if a.timed_out or P.failed(ahr) or src is None:
            s.fail("activate", ahr, a.timed_out)
            return False
        s.src = src
    s.ctl = get_ifaces(s.src)

    set_stage("reader_create")
    s.cb = ReaderCallback(st)
    src, cb = ref(s.src, C.IMFMediaSource), s.cb       # the worker's own source reference (see ``ref``)

    def mk(ctl):
        try:
            return make_reader(src, cb)
        finally:
            C.release(src)
    rc = bounded.call(timeout_ms, mk)
    s.reader_ms = rc.ms
    rhr, rd = rc.value if rc.value else (P.E_FAIL, None)
    s.steps.append(step_rec("reader_create", rhr, rc.ms, rc.timed_out, rc.exc))
    if rc.timed_out or P.failed(rhr) or rd is None:
        s.fail("reader_create", rhr, rc.timed_out)
        return False
    s.reader = rd

    set_stage("set_type")
    want = P.subtype_guid_text(mode["subtype"]) or P.MJPG_GUID

    def choose_on(rd, ctl):
        n: dict[str, Any] = {}
        types, ptrs = [], {}
        i = 0
        while True:
            raw = c_void_p()
            if rd.GetNativeMediaType(C.MF_SOURCE_READER_FIRST_VIDEO_STREAM, i, byref(raw)) & 0x80000000:
                break
            t = C.own(raw, C.IMFMediaType)
            x = {"type_index": i, **type_fields(t)}
            types.append(x)
            if x["subtype_guid"].upper() == want.upper() and (x["width"], x["height"]) == (mode["w"], mode["h"]):
                ptrs[i] = t                   # keep the candidates; the rest are released now
            else:
                C.release(t)
            i += 1
        best, cands = P.select_native_type(types, want, mode["w"], mode["h"], mode["fps"])
        n["candidate_rates_same_size"] = cands
        try:
            if best is None:
                n["reason"] = "no native type with this subtype, size and rate"
                return P.MF_E_INVALIDMEDIATYPE, n
            bt = next(x for x in types if x["type_index"] == best)
            n["native_type_index"] = best
            h = rd.SetStreamSelection(C.MF_SOURCE_READER_ALL_STREAMS, 0) & MASK
            if not P.failed(h):
                h = rd.SetStreamSelection(C.MF_SOURCE_READER_FIRST_VIDEO_STREAM, 1) & MASK
            n["stream_selection_hr"] = P.hr_hex(h)
            hr = rd.SetCurrentMediaType(C.MF_SOURCE_READER_FIRST_VIDEO_STREAM, None, ptrs[best]) & MASK
            if P.failed(hr):
                return hr, n
            craw = c_void_p()
            hc = rd.GetCurrentMediaType(C.MF_SOURCE_READER_FIRST_VIDEO_STREAM, byref(craw)) & MASK
            n["readback_hr"] = P.hr_hex(hc)
            if P.failed(hc):
                n["readback_ok"] = False
                return hc, n
            cur = C.own(craw, C.IMFMediaType)
            cf = type_fields(cur)
            C.release(cur)
            n.update(subtype=cf["subtype"], width=cf["width"], height=cf["height"], fps_num=cf["fps_num"],
                     fps_den=cf["fps_den"], fps=P.fps_of(cf["fps_num"], cf["fps_den"]))
            ok = (cf["subtype_guid"].upper() == want.upper() and cf["width"] == mode["w"] and cf["height"] == mode["h"]
                  and cf["fps_num"] == bt["fps_num"] and cf["fps_den"] == bt["fps_den"])
            n["readback_ok"] = ok
            if not ok:
                n["reason"] = "GetCurrentMediaType readback differs from the selected native type"
                return P.MF_E_INVALIDMEDIATYPE, n
            return 0, n
        finally:
            for t in ptrs.values():
                C.release(t)

    rd_choose = ref(rd, C.IMFSourceReader)              # the worker's own reader reference (see ``ref``)

    def choose(ctl):
        try:
            return choose_on(rd_choose, ctl)
        finally:
            C.release(rd_choose)

    stp = bounded.call(timeout_ms, choose)
    s.settype_ms = stp.ms
    shr, s.negotiated = stp.value if stp.value else (P.E_FAIL, {})
    s.steps.append(step_rec("set_type", shr, stp.ms, stp.timed_out, stp.exc))
    if stp.timed_out or P.failed(shr):
        s.fail("set_type", shr, stp.timed_out)
        return False

    set_stage("start")

    rd_start = ref(rd, C.IMFSourceReader)               # the worker's own reader reference (see ``ref``)

    def start(ctl):
        try:
            with st.mu:
                st.reader = rd          # the session's wrapper: the callback issues the next reads through it
                st.issue_ns = qpc_ns()
                st.progress_ns = st.issue_ns
            return rd_start.ReadSample(C.MF_SOURCE_READER_FIRST_VIDEO_STREAM, 0, None, None, None, None) & MASK
        finally:
            C.release(rd_start)

    stt = bounded.call(timeout_ms, start)
    ihr = stt.value if stt.value is not None else P.E_FAIL
    s.steps.append(step_rec("read_sample_issue", ihr, stt.ms, stt.timed_out, stt.exc))
    if stt.timed_out or P.failed(ihr):
        s.fail("read_sample_issue", ihr, stt.timed_out)
        return False
    return True


def wait_first(s: Session, timeout_ms: int) -> bool:
    """wincam wait_first(): wait for the first sample; the timeout counts from the last progress."""
    set_stage("first_sample")
    st = s.st
    while True:
        st.ev_sample.wait(0.02)
        st.ev_sample.clear()
        with st.mu:
            if st.frames > 0:
                s.first_frame_ms = (st.first_ns - st.issue_ns) / 1e6
                s.open_to_first_ms = (st.first_ns - s.t_open_ns) / 1e6
                s.steps.append(step_rec("first_sample", 0, s.first_frame_ms, False))
                return True
            if st.err is not None:
                s.steps.append(step_rec("first_sample", st.err, (qpc_ns() - st.issue_ns) / 1e6, False, st.err_exc))
                s.fail("first_sample", st.err, False)
                return False
            if st.eos:
                s.steps.append(step_rec("first_sample", P.MF_E_END_OF_STREAM, 0, False))
                s.fail("first_sample", P.MF_E_END_OF_STREAM, False)
                return False
            if (qpc_ns() - st.progress_ns) / 1e6 > timeout_ms:
                s.steps.append(step_rec("first_sample", P.E_FAIL, (qpc_ns() - st.issue_ns) / 1e6, True))
                s.fail("first_sample", P.E_FAIL, True)
                return False


def close_session(s: Session, timeout_ms: int) -> None:
    """wincam close_session(): stop issuing reads -> wait for an in-flight ReadSample issue -> Flush (wait OnFlush) ->
    final reader Release -> release the control interfaces -> IMFMediaSource::Shutdown -> IMFActivate::ShutdownObject.
    Every step is bounded; a step that does not return sets ``unreleasable`` and stops the close there."""
    set_stage("close")
    t0 = time.perf_counter_ns()

    def done() -> None:
        s.close_ms = (time.perf_counter_ns() - t0) / 1e6

    if s.st is not None:
        with s.st.mu:
            s.st.stop = True
            s.st.reader = None
        w0 = time.perf_counter_ns()
        while True:
            with s.st.mu:
                inflight = s.st.issuing
            if not inflight or (time.perf_counter_ns() - w0) / 1e6 > timeout_ms:
                break
            time.sleep(0.001)
        if inflight:
            s.steps.append(step_rec("wait_read_issue", P.E_FAIL, (time.perf_counter_ns() - w0) / 1e6, True))
            s.unreleasable = True
            s.fail("wait_read_issue", P.E_FAIL, True)
            return done()
    if s.reader is not None:
        rd, st = s.reader, s.st
        st.ev_flush.clear()
        fl = bounded.call(timeout_ms, lambda ctl: rd.Flush(C.MF_SOURCE_READER_ALL_STREAMS) & MASK)
        fwait, flushed = 0.0, False
        if not fl.timed_out and fl.value is not None and not P.failed(fl.value):
            w0 = time.perf_counter_ns()
            flushed = st.ev_flush.wait(timeout_ms / 1000.0)
            fwait = (time.perf_counter_ns() - w0) / 1e6
        s.flush_ms = fl.ms + fwait
        fs = step_rec("flush", fl.value if fl.value is not None else P.E_FAIL, s.flush_ms, fl.timed_out, fl.exc)
        fs["on_flush_received"] = flushed
        s.steps.append(fs)
        if fl.timed_out:
            s.unreleasable = True
            s.fail("flush", P.E_FAIL, True)
            return done()
        last, s.reader, rd = s.reader, None, None
        rr = bounded.call(timeout_ms, lambda ctl, p=last: C.release(p) or 0)
        last = None
        s.reader_release_ms = rr.ms
        s.steps.append(step_rec("reader_release", 0, rr.ms, rr.timed_out, rr.exc))
        if rr.timed_out:
            s.unreleasable = True
            s.fail("reader_release", P.E_FAIL, True)
            return done()
    if any(s.ctl.get(k) is not None for k in ("cc", "pa", "ks")):
        c, s.ctl = s.ctl, {"cc": None, "pa": None, "ks": None}
        cr = bounded.call(timeout_ms, lambda ctl, c=c: release_ifaces(c) or 0)
        s.steps.append(step_rec("control_interfaces_release", 0, cr.ms, cr.timed_out, cr.exc))
        if cr.timed_out:
            s.unreleasable = True
            s.fail("control_interfaces_release", P.E_FAIL, True)
            return done()
    holder = {"src": s.src, "act": s.act}
    s.src = s.act = None
    sh, hung = shutdown_mf(holder, timeout_ms)
    for x in sh:
        if x["step"] == "source_shutdown":
            s.shutdown_ms = x["ms"]
        if x["step"] == "activate_shutdown_object":
            s.shutdown_object_ms = x["ms"]
        s.steps.append(x)
    if hung:
        s.unreleasable = True
        s.fail("shutdown", P.E_FAIL, True)
    s.cb = None
    done()
