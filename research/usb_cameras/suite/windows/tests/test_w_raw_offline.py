"""Offline unit tests for W-RAW (no camera is opened: every capture is replaced by a fake that writes the files the
real tools write).

    uv run --isolated --python 3.12 --no-project --with pytest pytest suite/windows/tests/test_w_raw_offline.py \
        -c suite/common/tests/pytest.ini

Covers: raw-mode listing (MF-synthesized NV12 and H.264 excluded), the 2026-11-08 scope (exactly 720 lines,
>= 30 fps, no raw exception -> 'untested (no raw mode in scope)'), expected frame lengths, per-route ratings
(decoded BGR from OpenCV = no, a wrong length = partial, a rate the camera does not honour on every route = a camera
finding, not a failure), UVC metadata in the frames never changing a rating nor being reported (tier 0 only, Dom
2026-11-09), the device-fault stop, the contention plan, the
byte-layout plausibility check, --reanalyze, and the wincam source markers the test relies on.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
WIN = HERE.parent
for p in (str(WIN.parent), str(WIN), str(WIN / "helpers"), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import capkit as ck  # noqa: E402
import w_raw  # noqa: E402
from common import modescope, results  # noqa: E402

W, H = 1280, 720
YUY2_LEN, NV12_LEN = W * H * 2, W * H * 3 // 2

KIYO = {"key": "1532:0e05:port=P/4", "name": "USB Video Device", "vid": "1532", "pid": "0e05", "is_kiyo": True,
        "speed": "SS", "mf_symlink": "\\\\?\\usb#vid_1532&pid_0e05#kiyo-mf", "ds_path": "\\\\?\\usb#vid_1532&pid_0e05#kiyo-ds",
        "mf_index": 3, "ds_index": 3, "metadata_tier1": True}
C922 = {"key": "046d:085c:sn=B7", "name": "C922 Pro Stream Webcam", "vid": "046d", "pid": "085c", "is_kiyo": False,
        "speed": "HS", "mf_symlink": "c922-mf", "ds_path": "c922-ds", "mf_index": 0, "ds_index": 0,
        "metadata_tier1": True}
KIYO2 = dict(KIYO, key="1532:0e05:port=P/5", mf_symlink="kiyo2-mf", ds_path="kiyo2-ds", mf_index=4, ds_index=4)


def t(sub, w, h, fps, idx, flags=()):
    return {"subtype": sub, "width": w, "height": h, "fps_num": fps, "fps_den": 1, "fps": float(fps),
            "type_index": idx, "flags": list(flags)}


SYN = "nv12_immediately_before_same_mode_mjpg:likely_mf_synthesized_decode"
KIYO_FMT = {"reader_streams": [{"stream_index": 0, "types": [
    t("YUY2", 1920, 1080, 5, 0), t("YUY2", 1280, 720, 60, 1), t("YUY2", 1280, 720, 30, 2), t("YUY2", 1280, 720, 24, 3),
    t("YUY2", 640, 480, 30, 4), t("NV12", 1280, 720, 60, 5), t("NV12", 1280, 720, 30, 6), t("MJPG", 1280, 720, 30, 7),
    t("H264", 1280, 720, 30, 8), t("MFVideoFormat_H264_ES", 1280, 720, 30, 9)]}]}
C922_FMT = {"reader_streams": [{"stream_index": 0, "types": [
    t("YUY2", 1280, 720, 10, 0), t("YUY2", 1280, 720, 5, 1), t("YUY2", 640, 480, 30, 2),
    t("NV12", 1280, 720, 30, 3, [SYN]), t("MJPG", 1280, 720, 30, 4), t("NV12", 1280, 720, 60, 5, [SYN]),
    t("MJPG", 1280, 720, 60, 6)]}]}
FORMATS = {KIYO["key"]: KIYO_FMT, C922["key"]: C922_FMT, KIYO2["key"]: KIYO_FMT}


# ------------------------------------------------------------------------------------------------ synthetic frames
def frame(sub: str, w: int = W, h: int = H) -> bytes:
    """A plausible raw frame: luma is a gradient (varies), chroma sits near 128 (varies little)."""
    if sub == "YUY2":
        out = bytearray(w * h * 2)
        for i in range(0, len(out), 2):
            out[i] = (i // 2) % w * 255 // w           # Y
            out[i + 1] = 126 + (i // 4) % 5             # U/V
        return bytes(out)
    y = bytes((i % w) * 255 // w for i in range(w * h))
    c = bytes(126 + (i % 5) for i in range(w * h // 2))
    return y + c


FRAMES = {"YUY2": frame("YUY2"), "NV12": frame("NV12")}


def write_capture(od: Path, summary: dict, n: int, fps: float, length: int, payload: bytes | None,
                  shape=None, meta: bool = False, key: str = "qpc_ns") -> tuple[dict, dict, list[dict]]:
    od.mkdir(parents=True, exist_ok=True)
    rows = []
    with (od / "frames.raw").open("wb") as fr:
        for i in range(n):
            r = {"seq": i, key: int(1e12 + i * 1e9 / fps), "bytes": length}
            if shape is not None:
                r["shape"] = shape
            if meta:
                r["uvc_pts"] = i * 1000
            if i == 3 and payload is not None:
                r["raw_offset"] = fr.tell()
                r["raw_len"] = len(payload)
                fr.write(payload)
            rows.append(r)
    for name, obj in (("summary.json", summary),):
        (od / name).write_text(json.dumps(summary), encoding="utf-8")
    with (od / "frames.jsonl").open("w", encoding="utf-8") as fj:
        for r in rows:
            fj.write(json.dumps(r) + "\n")
    return summary, {"rc": 0, "timed_out": False}, rows


class Behaviour:
    """What each fake route delivers. Defaults: every route correct at the requested rate."""

    def __init__(self, **kw):
        self.fps = kw.get("fps")                       # delivered rate (None = the request)
        self.ocv_dshow_bgr = kw.get("ocv_dshow_bgr", False)
        self.pyav_short = kw.get("pyav_short", False)  # PyAV delivers truncated frames
        self.meta = kw.get("meta", False)              # UVC PTS on MF frames (must be ignored)
        self.fault_on = kw.get("fault_on")             # (camera key, api) that faults with 0x8007001F
        self.calls: list[tuple] = []


def fake_run_capture(beh: Behaviour):
    def _run(ctx, cam, m, api, od, secs):
        beh.calls.append((cam["key"], m.text, api))
        fps = beh.fps or m.fps
        n = int(fps * secs)
        exp = w_raw.expected_bytes(m.subtype, m.w, m.h)
        data = FRAMES[m.subtype]
        if beh.fault_on == (cam["key"], api):
            s = {"ok": False, "error": {"stage": "first_sample", "hr": "0x8007001F", "class": "device_error"},
                 "negotiated": {}, "frames": {"total": 0}}
            return write_capture(od, s, 0, fps, 0, None)
        if api == "mf":
            s = {"ok": True, "negotiated": {"subtype": m.subtype, "readback_ok": True, "raw": True,
                                            "likely_mf_synthesized": False, "native_type_index": 2,
                                            "raw_frame": {"expected_frame_bytes": exp, "basis": "MF_MT_DEFAULT_STRIDE"}},
                 "frames": {"total": n, "with_uvc_metadata": n if beh.meta else 0, "raw": True}, "fps_measured": fps}
            return write_capture(od, s, n, fps, exp, data, meta=beh.meta)
        if api in ("pyav", "ffmpeg"):
            pix = w_raw.RAW_FORMATS[m.subtype]["pix_fmt"]
            ln = exp - 64 if (api == "pyav" and beh.pyav_short) else exp
            s = {"ok": True, "codec": "rawvideo", "pix_fmt": pix, "fps_measured": fps}
            return write_capture(od, s, n, fps, ln, data[:ln], key="qpc_ns" if api == "pyav" else "pts_ns")
        if api == "ocv_dshow" and beh.ocv_dshow_bgr:
            s = {"ok": True, "delivered": {"fourcc_readback": m.subtype, "shapes": [[m.h, m.w, 3]]},
                 "fps_measured": fps}
            return write_capture(od, s, n, fps, m.w * m.h * 3, None, shape=[m.h, m.w, 3])
        shape = [1, exp] if api == "ocv_msmf" else [m.h, m.w, 2] if m.subtype == "YUY2" else [1, exp]
        s = {"ok": True, "delivered": {"fourcc_readback": m.subtype, "shapes": [shape]}, "fps_measured": fps}
        return write_capture(od, s, n, fps, exp, data, shape=shape)
    return _run


class FakeCtx:
    def __init__(self, tmp_path, cams, quick=True, **args):
        self.cameras = cams
        self.out_dir = tmp_path / "out"
        self.raw_dir = tmp_path / "raw"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.args = types.SimpleNamespace(quick=quick, min_fps=30.0, min_height=720, all_modes=False, raw_seconds=1.0,
                                          **args)
        self.wincam = Path("wincam.exe")
        self.python = "3.12"
        self.logs: list[str] = []

    def log(self, m):
        self.logs.append(m)

    def camera(self, key):
        return next((c for c in self.cameras if c["key"] == key), None)

    def arrivals(self):
        return {"cameras": {c["key"]: {"present": True, "last_arrival": None} for c in self.cameras}}

    def camcmd(self, *a, **kw):  # pragma: no cover - a test that reaches this has opened a camera
        raise AssertionError("camcmd called: a camera would have been opened")

    def run(self, *a, **kw):  # pragma: no cover
        raise AssertionError("ctx.run called")


@pytest.fixture
def patched(monkeypatch):
    beh = Behaviour()
    monkeypatch.setattr(w_raw, "load_formats", lambda ctx, cam, cache: (FORMATS.get(cam["key"]), {"source": "fixture"}))
    monkeypatch.setattr(w_raw, "camera_domains", lambda ctx: ({KIYO["key"]: "ss|tb|4", C922["key"]: "hs|x|13",
                                                               KIYO2["key"]: "ss|tb|4"}, "fixture"))
    monkeypatch.setattr(ck, "activity_for_camera", lambda ctx, cam, doc=None: {"ok": None, "fixture": True})
    monkeypatch.setattr(w_raw, "run_capture", fake_run_capture(beh))
    return beh


def v(res, cam, api):
    return res["verdicts"][f"G-RAW|{cam['key']}|{api}"]


# ------------------------------------------------------------------------------------------------ pure functions
def test_expected_bytes_and_raw_subtypes():
    assert w_raw.expected_bytes("YUY2", 1280, 720) == 1_843_200
    assert w_raw.expected_bytes("NV12", 1280, 720) == 1_382_400
    assert w_raw.expected_bytes("ABCD", 1280, 720) is None
    assert w_raw.is_raw_subtype("YUY2") and w_raw.is_raw_subtype("NV12") and w_raw.is_raw_subtype("D3DFMT_20")
    assert not any(w_raw.is_raw_subtype(s) for s in ("MJPG", "H264", "MFVideoFormat_H264_ES"))


def test_raw_modes_exclude_synthesized_and_compressed():
    modes, info = w_raw.raw_modes(C922_FMT)
    assert [m.text for m in modes] == ["YUY2 640x480@30", "YUY2 1280x720@5", "YUY2 1280x720@10"]
    assert info["synthesized_excluded"] == ["NV12 1280x720@30", "NV12 1280x720@60"]
    kmodes, kinfo = w_raw.raw_modes(KIYO_FMT)
    assert {m.subtype for m in kmodes} == {"YUY2", "NV12"} and kinfo["compressed_types"] == 3


def test_scope_exactly_720_lines_no_raw_exception():
    sc = modescope.from_args(types.SimpleNamespace(min_fps=30, min_height=720, all_modes=False))
    kept, rec = w_raw.scope_raw(sc, w_raw.raw_modes(KIYO_FMT)[0])
    assert sorted(m.text for m in kept) == ["NV12 1280x720@30", "NV12 1280x720@60", "YUY2 1280x720@30",
                                            "YUY2 1280x720@60"]           # 1080p@5, 720p24, 480p30 excluded
    kept, rec = w_raw.scope_raw(sc, w_raw.raw_modes(C922_FMT)[0])
    assert kept == [] and rec["untested_reason"].startswith("untested (no raw mode in scope)")
    assert "YUY2 1280x720@10" in rec["untested_reason"]
    allm = modescope.from_args(types.SimpleNamespace(all_modes=True))
    assert len(w_raw.scope_raw(allm, w_raw.raw_modes(C922_FMT)[0])[0]) == 3


class OldScope:
    """The 2026-11-06 modescope.Scope (>= min_height lines, no max_height attribute)."""
    min_fps, min_height, all_modes, text = 30.0, 720, False, ">= 30 fps and >= 720 lines"

    def contains(self, w, h, fps):
        return h >= 720 and fps >= 30 * 0.995

    def as_dict(self):
        return {"min_fps": 30.0, "min_height": 720, "all_modes": False, "text": self.text}


def test_scope_exact_height_added_for_an_old_modescope():
    modes = w_raw.raw_modes(KIYO_FMT)[0] + [ck.Mode(1920, 1080, 30, 1, "YUY2")]
    kept, rec = w_raw.scope_raw(OldScope(), modes)
    assert all(m.h == 720 for m in kept) and len(kept) == 4
    assert rec["rule"].startswith("exactly 720 lines")


def test_layout_check_detects_swapped_byte_order():
    good = w_raw.layout_check("YUY2", W, H, FRAMES["YUY2"])
    assert good["plausible"] is True
    # the same bytes read as UYVY put chroma where luma should be
    assert w_raw.layout_check("UYVY", W, H, FRAMES["YUY2"])["plausible"] is False
    assert w_raw.layout_check("NV12", W, H, FRAMES["NV12"])["plausible"] is True
    assert w_raw.layout_check("YUY2", W, H, bytes(YUY2_LEN))["plausible"] is None      # flat frame: inconclusive


def test_contention_plan():
    m = ck.Mode(W, H, 30, 1, "YUY2")
    one = w_raw.contention_plan({"a": [m], "b": []}, {"a": "d1", "b": "d1"})
    assert one["run"] is False and "only 1 camera" in one["reason"]
    apart = w_raw.contention_plan({"a": [m], "b": [m]}, {"a": "d1", "b": "d2"})
    assert apart["run"] is False and "different bandwidth domains" in apart["reason"]
    shared = w_raw.contention_plan({"a": [m], "b": [m]}, {"a": "d1", "b": "d1"})
    assert shared["run"] is True and shared["pair"] == ["a", "b"] and shared["domain"] == "d1"


# ------------------------------------------------------------------------------------------------ run()
def test_run_rates_each_route(tmp_path, patched):
    patched.ocv_dshow_bgr = True
    res = w_raw.run(FakeCtx(tmp_path, [C922, KIYO]))
    for api in w_raw.APIS:                         # C922: nothing streamed, labelled untested (no raw mode in scope)
        x = v(res, C922, api)
        assert x["rating"] == "untested" and x["summary_label"] == "untested (no raw mode in scope)"
    assert not any(c[0] == C922["key"] for c in patched.calls)
    for api in ("mf", "pyav", "ffmpeg", "ocv_msmf"):
        assert v(res, KIYO, api)["rating"] == "yes", api
    bgr = v(res, KIYO, "ocv_dshow")
    assert bgr["rating"] == "no" and "no raw frames" in bgr["summary_label"]
    cam = res["measurements"]["cameras"][KIYO["key"]]
    assert len(cam["modes"]) == 4
    row = cam["modes"][0]
    assert row["layout_agree"] is True and row["lengths_by_api"]["mf"] in (YUY2_LEN, NV12_LEN)
    assert row["apis"]["mf"]["layout"]["plausible"] is True
    con = res["measurements"]["contention"]
    assert con["run"] is False and "only 1 camera" in con["reason"]
    assert "tier1_extra" not in cam


def test_frame_metadata_never_changes_a_rating_nor_is_reported(tmp_path, monkeypatch, patched):
    # tier 0 only (Dom 2026-11-09): MF frames that happen to carry UVC PTS (when the registry value is present)
    # rate exactly like frames without it, and nothing about the metadata reaches the result
    a = w_raw.run(FakeCtx(tmp_path / "a", [KIYO]))
    patched.meta = True
    b = w_raw.run(FakeCtx(tmp_path / "b", [KIYO]))
    assert {k: x["rating"] for k, x in a["verdicts"].items()} == {k: x["rating"] for k, x in b["verdicts"].items()}
    cam = b["measurements"]["cameras"][KIYO["key"]]
    txt = json.dumps(cam)
    assert "tier1_extra" not in cam and '"uvc_pts' not in txt and 'uvc_metadata"' not in txt


def test_wrong_length_is_partial_and_rate_not_honoured_is_a_camera_finding(tmp_path, patched):
    patched.pyav_short = True
    patched.fps = 15.0                              # every route agrees on 15 fps at a 30/60 fps request
    res = w_raw.run(FakeCtx(tmp_path, [KIYO]))
    assert v(res, KIYO, "pyav")["rating"] == "partial"
    assert v(res, KIYO, "mf")["rating"] == "yes"
    row = res["measurements"]["cameras"][KIYO["key"]]["modes"][0]
    assert row["rate_honoured"]["honoured"] is False and row["fps_reference_basis"] == "apis_agree"


def test_harness_exception_is_untested_not_a_route_failure(tmp_path, monkeypatch, patched):
    good = fake_run_capture(patched)

    def boom(ctx, cam, m, api, od, secs):
        if api == "pyav":
            raise RuntimeError("uv could not resolve the helper environment")
        return good(ctx, cam, m, api, od, secs)
    monkeypatch.setattr(w_raw, "run_capture", boom)
    res = w_raw.run(FakeCtx(tmp_path, [KIYO]))
    x = v(res, KIYO, "pyav")
    assert x["rating"] == "untested" and "harness exception" in json.dumps(x), x
    assert v(res, KIYO, "mf")["rating"] == "yes"


def test_raw_ds_import_failures_are_marked_untested():
    src = (WIN / "helpers" / "raw_ds.py").read_text(encoding="utf-8")
    assert src.count("untested=True") + src.count('"untested": True') >= 3     # ffmpeg missing, cv2, PyAV import


def test_device_fault_stops_the_camera(tmp_path, patched):
    patched.fault_on = (KIYO["key"], "mf")
    res = w_raw.run(FakeCtx(tmp_path, [KIYO]))
    for api in w_raw.APIS:
        x = v(res, KIYO, api)
        assert x["rating"] == "untested" and x["summary_label"] == "untested (device fault)"
    assert len(patched.calls) == 1                  # nothing after the fault
    modes = res["measurements"]["cameras"][KIYO["key"]]["modes"]
    assert all(m.get("skipped") for m in modes[1:])


def test_contention_runs_for_two_cameras_in_one_domain(tmp_path, monkeypatch, patched):
    seen = {}

    def fake_multi(ctx, spec, spec_path, timeout_s):
        seen["labels"] = [c["label"] for c in spec["commands"]]
        out = {"commands": [{"label": c["label"], "stdout": json.dumps(
            {"ok": i == 0, "frames": {"total": 30 if i == 0 else 0}, "negotiated": {"subtype": "YUY2"},
             "error": None if i == 0 else {"stage": "first_sample", "hr": "0x800718CF"}}), "timed_out": False}
            for i, c in enumerate(spec["commands"])]}
        return out, {"rc": 0}

    monkeypatch.setattr(ck, "multi_launch", fake_multi)
    res = w_raw.run(FakeCtx(tmp_path, [KIYO, KIYO2]))
    con = res["measurements"]["contention"]
    assert con["run"] is True and set(seen["labels"]) == {KIYO["key"], KIYO2["key"]}
    loser = con["outcomes"][KIYO2["key"]]
    assert loser["ok"] is False and loser["classification"]["class"] == "bandwidth_certain"


def test_reanalyze_round_trip(tmp_path, patched):
    ctx = FakeCtx(tmp_path, [C922, KIYO])
    res = w_raw.run(ctx)
    results.write_json(ctx.out_dir / "W-RAW.json", res)
    doc = w_raw.reanalyze(ctx.out_dir)
    assert not [c for c in doc["rating_changes"] if c["changed"]]
    assert (ctx.out_dir / "reanalysis" / "W-RAW.json").exists()
    assert doc["verdicts"][f"G-RAW|{C922['key']}|mf"]["summary_label"] == "untested (no raw mode in scope)"


def test_estimate_uses_only_files_on_disk(tmp_path):
    ctx = FakeCtx(tmp_path, [C922, KIYO])
    est = w_raw.estimate_s(ctx)                     # no listing on disk: SuperSpeed Kiyo counts 4 modes, C922 0
    assert est > 15 and est < 15 + 4 * 200
    d = ctx.out_dir / "W-FMT"
    d.mkdir()
    (d / "usb_video_device_1532-0e05_formats_mf.json").write_text(json.dumps(KIYO_FMT), encoding="utf-8")
    (d / "c922_046d-085c_formats_mf.json").write_text(json.dumps(C922_FMT), encoding="utf-8")
    assert w_raw.estimate_s(ctx) == est


def test_helper_argv_routes(tmp_path):
    ctx = FakeCtx(tmp_path, [KIYO])
    m = ck.Mode(W, H, 30, 1, "NV12")
    argv, to = w_raw.helper_argv(ctx, KIYO, m, "pyav", tmp_path / "o", 3.0)
    assert "--pixel-format" in argv and argv[argv.index("--pixel-format") + 1] == "nv12" and KIYO["ds_path"] in argv
    argv, to = w_raw.helper_argv(ctx, KIYO, m, "ocv_msmf", tmp_path / "o", 3.0)
    assert argv[argv.index("--backend") + 1] == "msmf" and argv[argv.index("--index") + 1] == "3"
    assert KIYO["mf_symlink"] in argv and to >= 120     # the MSMF open bound is inside the child timeout
    assert isinstance(w_raw.helper_argv(ctx, dict(KIYO, ds_path=None), m, "ffmpeg", tmp_path, 3.0), str)


def test_wincam_source_has_the_raw_support_this_test_needs():
    src = (WIN / "native" / "wincam.cpp").read_text(encoding="utf-8")
    for marker in ("--allow-synthesized", "likely_mf_synthesized", "expected_frame_bytes", "raw_len_ok",
                   'r["fps_measured"]', "frames.raw", "MF_MT_DEFAULT_STRIDE"):
        assert marker in src, marker


def test_negotiated_raw_type_with_zero_frames_rates_no():
    """Review round 3: a route that negotiates the raw type and then streams nothing did not deliver the format."""
    m = ck.Mode(W, H, 60, 1, "YUY2")
    s = {"ok": False, "negotiated": {"subtype": "YUY2", "readback_ok": True, "raw": True},
         "error": {"stage": "first_frame", "class": "timeout"}}
    a = w_raw.analyse("mf", s, {"rc": 4}, [], m)
    assert a["format_ok"] is False and a["frames"] == 0 and a["fault"] is None
    p = w_raw.analyse("pyav", {"ok": False, "codec": "rawvideo", "pix_fmt": "yuyv422"}, {"rc": 4}, [], m)
    assert p["format_ok"] is False
    row = w_raw.finish_mode({"mode": m.text, "apis": {"mf": a, "pyav": p}}, m)
    for api in ("mf", "pyav"):
        v = w_raw.rate_api([row], api, 1)
        assert v["rating"] == "no" and v["summary_label"] == "no (no raw frames in the requested format)"
