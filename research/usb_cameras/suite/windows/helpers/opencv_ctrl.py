# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-contrib-python==4.12.*", "numpy"]
# ///
"""OpenCV camera-control probe for W-OCV-CTRL: CAP_PROP_AUTO_EXPOSURE / EXPOSURE / AUTOFOCUS / FOCUS through
CAP_DSHOW or CAP_MSMF, set -> get readback -> the camera's real state -> the image.

    uv run --script opencv_ctrl.py run --backend dshow|msmf --index N --expect-path <link> --width 1280 --height 720
        --fps 30 --timeout-ms 8000 --open-timeout-ms 120000 --out-dir D --wincam <wincam.exe> --ds-device <DS path>
        --phase after|before [--exp-values -9,-6,-4] [--focus-values 0,60,125,190,250]
        [--exp-before V --focus-before F --ae-manual X --ae-auto Y --af-off A --af-on B]

Run it under tools/camlock.py (ctx.camcmd) like every camera command. It calls ``wincam controls --api ds`` itself
(subprocesses with a timeout) to read the camera's REAL control state (value + auto/manual flag through a second
DirectShow filter instance, which works while OpenCV streams) and, in the convention probe, to put the camera into a
known state first. OpenCV opens by INDEX only; ``--expect-path`` records which device the index was meant to be, and
with CAP_MSMF ``wincam activity`` after the first frame shows whether THIS process streams that device (DirectShow
clients are invisible to the activity monitor).

Phase ``after`` (one open): format sets (DSHOW: FOURCC MJPG, W, H, FPS in skellycam's order; MSMF: W, H, FPS),
first read, ``baseline`` segment (the caller set auto before the open), then:
1. convention probe: for each CAP_PROP_AUTO_EXPOSURE value in --ae-probe, the camera is put in auto, OpenCV sets
   the value, the real state is read; then the same from manual. Same for CAP_PROP_AUTOFOCUS (--af-probe). The
   value that turns the auto mode off from both states is the "manual" value, the one that turns it on the "auto"
   value (``derive_convention``);
2. AE off with that value, CAP_PROP_EXPOSURE set to each --exp-values entry (set, get, real state, segment);
   when the last entry is < 2 steps (--exp-step) from AE's own value read after the baseline, one more set to a
   sweep value >= 2 steps away (``exp_pre_ae`` set and segment), so the AE-on transition can leave the luma band
   (Gerald 2026-11-06: 75% of -11..-2 = -4 was the C922's and the Kiyo's AE value);
3. AE on (``ae_on`` segment, longer: the recovery is measured on the image);
4. AF off, CAP_PROP_FOCUS set to each --focus-values entry (set, get, real state, segment);
5. AF on (``af_on`` segment).
Phase ``before`` (a second open): before the first read, AE off + EXPOSURE --exp-before and AF off + FOCUS
--focus-before (set, get, real state), then the first read, a segment, the real state again (held through the
stream start?), a second segment.

Frames: every ``--save-every``-th frame is JPEG-encoded (quality 95) into D/frames.mjpeg with rows in D/frames.jsonl
(``seq``, ``qpc_ns`` = perf_counter_ns when read() returned (QPC on Windows, the clock wincam and multi_launch use),
``mjpeg_offset``, ``mjpeg_len``, ``segment``), so the suite measures them with common.imgmetrics exactly like the
wincam frames. OpenCV delivers decoded BGR (DSHOW decodes the MJPEG; MSMF delivers MF-decoded frames): the JPEG here
is the harness's re-encode, not the camera's bytes.

Every OpenCV call runs on ONE worker thread (opencv_ds.Worker: OpenCV DSHOW crashes when calls hop threads) with a
bound (--timeout-ms; the open --open-timeout-ms: MSMF opens took 39-41 s on the Logitech cameras; the MSMF format
sets also --open-timeout-ms, since MSMF rebuilds the reader per set; ``format.per_set_ms`` records each). A call that does
not return is recorded (``hung``) and the process exits 5 after writing D/summary.json. Exit: 0 done, 2 usage,
4 open failed / no frame, 5 a call hung.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SUITE_DIR = HERE.parents[1]
for _p in (str(SUITE_DIR), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from opencv_ds import bounded, fourcc_str  # noqa: E402

TOOL_VERSION = "opencv_ctrl 1.2 (2026-11-09)"
FLAG_AUTO, FLAG_MANUAL = 1, 2
PROPS = ("AUTO_EXPOSURE", "EXPOSURE", "AUTOFOCUS", "FOCUS")


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


# ------------------------------------------------------------------------------------------------ conventions
def mode_of(flags: Any) -> str | None:
    if not isinstance(flags, int) or isinstance(flags, bool):
        return None
    if flags & FLAG_AUTO:
        return "auto"
    if flags & FLAG_MANUAL:
        return "manual"
    return None


def meaning(from_auto: str | None, from_manual: str | None) -> str:
    """What one OpenCV value did to the camera's auto mode, from a known auto state and a known manual state."""
    if from_auto is None or from_manual is None:
        return "unknown"
    if from_auto == "manual" and from_manual == "manual":
        return "manual"
    if from_auto == "auto" and from_manual == "auto":
        return "auto"
    if from_auto == "auto" and from_manual == "manual":
        return "ignored"
    return "toggles"


def derive_convention(probe: list[dict]) -> dict:
    """{"manual_value", "auto_value", "meanings": {value: meaning}} from probe rows {"value", "from_auto",
    "from_manual"} (camera modes after OpenCV's set). The first value meaning 'manual' / 'auto' wins."""
    mean = {}
    for r in probe:
        mean[str(r.get("value"))] = meaning(r.get("from_auto"), r.get("from_manual"))
    man = next((r["value"] for r in probe if mean.get(str(r["value"])) == "manual"), None)
    aut = next((r["value"] for r in probe if mean.get(str(r["value"])) == "auto"), None)
    return {"manual_value": man, "auto_value": aut, "meanings": mean}


# ------------------------------------------------------------------------------------------------ side channel
class Side:
    """``wincam controls --api ds`` on the expected device (real camera state; bounded subprocesses)."""

    def __init__(self, wincam: str | None, dev: str | None, timeout_s: float = 20.0) -> None:
        self.wincam, self.dev, self.timeout_s = wincam, dev, timeout_s
        self.calls = 0

    def _run(self, extra: list[str]) -> dict:
        if not self.wincam or not self.dev:
            return {"ok": False, "error": "no wincam / DS device given"}
        self.calls += 1
        argv = [self.wincam, "controls", "--api", "ds", "--device", self.dev, *extra, "--timeout-ms", "4000"]
        t0 = time.perf_counter_ns()
        try:
            p = subprocess.run(argv, capture_output=True, text=True, errors="replace", timeout=self.timeout_s)
            out, rc, to = p.stdout, p.returncode, False
        except subprocess.TimeoutExpired as e:
            out, rc, to = (e.stdout or "") if isinstance(e.stdout, str) else "", None, True
        t1 = time.perf_counter_ns()
        try:
            j = json.loads(out[out.find("{"):out.rfind("}") + 1]) if "{" in out else None
        except ValueError:
            j = None
        rec: dict = {"t_start_ns": t0, "t_end_ns": t1, "rc": rc, "timed_out": to, "ok": j is not None and not to}
        if j is None:
            return rec
        state = {}
        for c in j.get("controls") or []:
            if c.get("supported") and c.get("name") in ("exposure", "focus"):
                state[c["name"]] = {"value": c.get("value"), "flags": c.get("flags"), "mode": mode_of(c.get("flags"))}
        for s in j.get("sets") or []:
            n = str(s.get("control", "")).split(".")[-1]
            if n in ("exposure", "focus"):
                state[n] = {"value": s.get("readback_value"), "flags": s.get("readback_flags"),
                            "mode": mode_of(s.get("readback_flags")), "set_matches": s.get("matches")}
        rec["state"] = state
        rec["error"] = j.get("error")
        rec["device_not_answering"] = j.get("device_not_answering")
        return rec

    def read(self) -> dict:
        return self._run(["--read-only"])

    def set(self, spec: str) -> dict:
        return self._run(["--set", spec])


# ------------------------------------------------------------------------------------------------ session
class Session:
    def __init__(self, cv2, a: argparse.Namespace) -> None:
        self.cv2, self.a = cv2, a
        self.T = a.timeout_ms / 1000.0
        self.cap = None
        self.out = Path(a.out_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        self.fj = (self.out / "frames.jsonl").open("w", encoding="utf-8", newline="\n")
        self.fm = (self.out / "frames.mjpeg").open("wb")
        self.seq = 0
        self.events: list[dict] = []
        self.segments: list[dict] = []
        self.hung: dict | None = None
        self.side = Side(a.wincam, a.ds_device)
        self.read_errors = 0

    # -- bounded OpenCV calls ------------------------------------------------------------------------
    def call(self, what: str, fn, timeout_s: float | None = None):
        done, val, exc, ms = bounded(fn, timeout_s or self.T)
        if not done:
            self.hung = {"call": what, "after_ms": round(ms, 1), "utc": utc_now()}
            raise TimeoutError(what)
        if exc is not None:
            raise exc
        return val, ms

    def prop(self, name: str) -> int:
        return getattr(self.cv2, f"CAP_PROP_{name}")

    def set_get(self, name: str, value: float, tag: str, side: bool = True) -> dict:
        t0 = time.perf_counter_ns()
        ret, ms = self.call(f"set {name}", lambda: self.cap.set(self.prop(name), float(value)))
        got, _ = self.call(f"get {name}", lambda: self.cap.get(self.prop(name)))
        ev = {"tag": tag, "op": "set", "prop": name, "value": value, "ret": bool(ret), "got": got,
              "set_ms": round(ms, 2), "t_ns": t0, "t_end_ns": time.perf_counter_ns()}
        if side:
            ev["side"] = self.side.read()
        self.events.append(ev)
        return ev

    def get_all(self, tag: str) -> dict:
        vals = {}
        for n in PROPS:
            try:
                vals[n], _ = self.call(f"get {n}", lambda n=n: self.cap.get(self.prop(n)))
            except TimeoutError:
                raise
            except Exception as e:  # noqa: BLE001
                vals[n] = repr(e)
        ev = {"tag": tag, "op": "get_all", "got": vals, "t_ns": time.perf_counter_ns(), "side": self.side.read()}
        self.events.append(ev)
        return ev

    def stream(self, label: str, seconds: float, min_frames: int = 0) -> dict:
        """Read frames for ``seconds`` (and at least ``min_frames``); every --save-every-th frame is saved (JPEG
        re-encode)."""
        cv2 = self.cv2
        seg = {"label": label, "t_start_ns": time.perf_counter_ns(), "frames": 0, "failed_reads": 0}
        t_end = time.perf_counter() + seconds
        while time.perf_counter() < t_end or seg["frames"] < min_frames:
            res, _ = self.call("read", self.cap.read)
            tq = time.perf_counter_ns()
            ok, fr = (res if isinstance(res, tuple) else (False, None))
            if not ok or fr is None:
                seg["failed_reads"] += 1
                self.read_errors += 1
                if seg["failed_reads"] >= 5 and (seg["frames"] == 0 or seg["frames"] < min_frames):
                    break
                continue
            row: dict = {"seq": self.seq, "qpc_ns": tq, "segment": label, "shape": list(fr.shape)}
            if self.seq % max(1, self.a.save_every) == 0:
                ok2, buf = cv2.imencode(".jpg", fr, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
                if ok2:
                    b = buf.tobytes()
                    row["mjpeg_offset"] = self.fm.tell()
                    row["mjpeg_len"] = len(b)
                    self.fm.write(b)
            self.fj.write(json.dumps(row) + "\n")
            self.seq += 1
            seg["frames"] += 1
        seg["t_end_ns"] = time.perf_counter_ns()
        self.segments.append(seg)
        return seg

    def close_files(self) -> None:
        for f in (self.fj, self.fm):
            try:
                f.close()
            except Exception:  # noqa: BLE001
                pass


def _floats(s: str | None) -> list[float]:
    return [float(x) for x in (s or "").split(",") if x.strip()]


def pre_ae_exposure(ev: list[float], ae_value, step: float | None) -> float | None:
    """The last manual exposure before AE goes back on, when the sweep's last value is < 2 steps from AE's own
    value (read in auto after the baseline): a sweep value (in range) >= 2 steps away, darker preferred (it keeps
    the frame rate), the nearest such one. None = not needed, AE value unknown, or no sweep value qualifies."""
    if not ev or not isinstance(ae_value, (int, float)):
        return None
    need = 2 * (step or 1)
    if abs(ev[-1] - ae_value) >= need:
        return None
    darker = [v for v in ev if ae_value - v >= need]
    if darker:
        return max(darker)
    far = [v for v in ev if abs(v - ae_value) >= need]
    return min(far, key=lambda v: abs(v - ae_value)) if far else None


def probe(ses: Session, prop: str, ctl: str, values: list[float], manual_spec: str) -> list[dict]:
    """For each value: camera to auto (side set), OpenCV set, real mode; camera to manual (side set), OpenCV set,
    real mode."""
    rows = []
    for v in values:
        row: dict = {"value": v}
        for start, spec in (("from_auto", f"{ctl}=auto"), ("from_manual", manual_spec)):
            pre = ses.side.set(spec)
            ev = ses.set_get(prop, v, f"probe_{prop}_{start}")
            row[start] = ((ev.get("side") or {}).get("state") or {}).get(ctl, {}).get("mode")
            row[f"{start}_pre_mode"] = ((pre.get("state") or {}).get(ctl) or {}).get("mode")
            row[f"{start}_ret"] = ev["ret"]
            row[f"{start}_got"] = ev["got"]
        rows.append(row)
    return rows


def phase_after(ses: Session, a: argparse.Namespace, doc: dict) -> None:
    ses.stream("baseline", a.baseline_s)
    st0 = ses.get_all("after_baseline")
    exp_state = ((st0.get("side") or {}).get("state") or {}).get("exposure") or {}
    foc_state = ((st0.get("side") or {}).get("state") or {}).get("focus") or {}
    ev = _floats(a.exp_values)
    fv = _floats(a.focus_values)
    mid_e = int(ev[len(ev) // 2]) if ev else exp_state.get("value")
    mid_f = int(fv[len(fv) // 2]) if fv else foc_state.get("value")
    conv: dict = {}
    if ev:
        rows = probe(ses, "AUTO_EXPOSURE", "exposure", _floats(a.ae_probe), f"exposure={mid_e}")
        conv["auto_exposure"] = {"probe": rows, **derive_convention(rows)}
    if fv:
        rows = probe(ses, "AUTOFOCUS", "focus", _floats(a.af_probe), f"focus={mid_f}")
        conv["autofocus"] = {"probe": rows, **derive_convention(rows)}
    doc["convention"] = conv
    # back to auto (known state) before the effect sets
    ses.side.set(",".join(x for x, ok in (("exposure=auto", ev), ("focus=auto", fv)) if ok) or "exposure=auto")
    if ev:
        ae = conv["auto_exposure"]
        man = ae.get("manual_value")
        if man is not None:
            ses.set_get("AUTO_EXPOSURE", man, "ae_off")
        for i, v in enumerate(ev):
            ses.set_get("EXPOSURE", v, f"exp{i}")
            ses.stream(f"exp{i}", a.seg_s)
        pre = pre_ae_exposure(ev, exp_state.get("value"), a.exp_step)
        if pre is not None:
            ses.set_get("EXPOSURE", pre, "exp_pre_ae")
            ses.stream("exp_pre_ae", a.seg_s)
        aut = ae.get("auto_value")
        if aut is not None:
            ses.set_get("AUTO_EXPOSURE", aut, "ae_on")
        else:
            ses.events.append({"tag": "ae_on", "op": "skipped", "why": "no CAP_PROP_AUTO_EXPOSURE value turned AE on",
                               "t_ns": time.perf_counter_ns()})
        ses.stream("ae_on", a.ae_on_s)
    if fv:
        af = conv["autofocus"]
        off = af.get("manual_value")
        if off is not None:
            ses.set_get("AUTOFOCUS", off, "af_off")
        for i, v in enumerate(fv):
            ses.set_get("FOCUS", v, f"focus{i}")
            ses.stream(f"focus{i}", a.focus_seg_s)
        on = af.get("auto_value")
        if on is not None:
            ses.set_get("AUTOFOCUS", on, "af_on")
        else:
            ses.events.append({"tag": "af_on", "op": "skipped", "why": "no CAP_PROP_AUTOFOCUS value turned AF on",
                               "t_ns": time.perf_counter_ns()})
        ses.stream("af_on", a.af_on_s)


def phase_before(ses: Session, a: argparse.Namespace, doc: dict) -> None:
    """Sets before the first read(); then the first frame and two segments with a real-state read between."""
    if a.exp_before is not None:
        if a.ae_manual is not None:
            ses.set_get("AUTO_EXPOSURE", a.ae_manual, "before_ae_off")
        ses.set_get("EXPOSURE", a.exp_before, "before_exp")
    if a.focus_before is not None:
        if a.af_off is not None:
            ses.set_get("AUTOFOCUS", a.af_off, "before_af_off")
        ses.set_get("FOCUS", a.focus_before, "before_focus")
    t0 = time.perf_counter()
    first = ses.stream("first", 0.0, min_frames=1)
    doc["first_frame_ms_after_sets"] = round((time.perf_counter() - t0) * 1000.0, 1) if first["frames"] else None
    ses.stream("before0", a.seg_s)
    ses.get_all("after_first_frame")
    ses.stream("before1", a.seg_s)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("--backend", choices=["dshow", "msmf"], required=True)
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--expect-path", default=None)
    p.add_argument("--width", type=int, required=True)
    p.add_argument("--height", type=int, required=True)
    p.add_argument("--fps", type=float, required=True)
    p.add_argument("--timeout-ms", type=int, default=8000)
    p.add_argument("--open-timeout-ms", type=int, default=120000)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--wincam", default=None)
    p.add_argument("--ds-device", default=None)
    p.add_argument("--phase", choices=["after", "before"], required=True)
    p.add_argument("--exp-values", default="")
    p.add_argument("--focus-values", default="")
    p.add_argument("--exp-step", type=float, default=1.0)
    p.add_argument("--ae-probe", default="0.25,0.75,0,1,3")
    p.add_argument("--af-probe", default="0,1")
    p.add_argument("--exp-before", type=float, default=None)
    p.add_argument("--focus-before", type=float, default=None)
    p.add_argument("--ae-manual", type=float, default=None)
    p.add_argument("--af-off", type=float, default=None)
    p.add_argument("--baseline-s", type=float, default=3.0)
    p.add_argument("--seg-s", type=float, default=2.0)
    p.add_argument("--focus-seg-s", type=float, default=1.5)
    p.add_argument("--ae-on-s", type=float, default=4.5)
    p.add_argument("--af-on-s", type=float, default=6.5)
    p.add_argument("--save-every", type=int, default=2)
    try:
        a = ap.parse_args()
    except SystemExit as e:
        sys.exit(2 if e.code not in (0, None) else 0)
    import cv2  # noqa: PLC0415
    api = cv2.CAP_DSHOW if a.backend == "dshow" else cv2.CAP_MSMF
    doc: dict[str, Any] = {"tool": "opencv_ctrl", "version": TOOL_VERSION, "utc_started": utc_now(), "pid": os.getpid(),
                           "argv": sys.argv, "opencv": cv2.__version__, "backend": a.backend, "index": a.index,
                           "expect_path": a.expect_path, "phase": a.phase, "timeout_ms": a.timeout_ms,
                           "open_timeout_ms": a.open_timeout_ms,
                           "requested": {"width": a.width, "height": a.height, "fps": a.fps}}
    ses = Session(cv2, a)
    rc = 0
    try:
        t0 = time.perf_counter_ns()
        ses.cap, ms = ses.call("open", lambda: cv2.VideoCapture(a.index, api), a.open_timeout_ms / 1000.0)
        opened, _ = ses.call("isOpened", ses.cap.isOpened)
        doc["open_ms"] = round(ms, 1)
        doc["opened"] = bool(opened)
        doc["t_open_ns"] = t0
        if not opened:
            doc["error"] = {"stage": "open", "reason": "isOpened() is False (OpenCV hides the HRESULT in its log)"}
            rc = 4
        else:
            sets: dict = {"per_set_ms": {}}
            doc["format"] = sets            # filled as it goes: a hang still shows which set it was in

            def timed(name: str, fn):
                t1 = time.perf_counter()
                sets["per_set_ms"][name] = None          # started, not returned (yet)
                v = fn()
                sets["per_set_ms"][name] = round((time.perf_counter() - t1) * 1000.0, 1)
                return v

            def fmt() -> dict:
                if a.backend == "dshow":
                    sets["fourcc"] = timed("fourcc", lambda: ses.cap.set(cv2.CAP_PROP_FOURCC,
                                                                         cv2.VideoWriter_fourcc(*"MJPG")))
                sets["w"] = timed("w", lambda: ses.cap.set(cv2.CAP_PROP_FRAME_WIDTH, a.width))
                sets["h"] = timed("h", lambda: ses.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, a.height))
                sets["fps"] = timed("fps", lambda: ses.cap.set(cv2.CAP_PROP_FPS, a.fps))
                sets["got_fourcc"] = fourcc_str(ses.cap.get(cv2.CAP_PROP_FOURCC))
                sets["got_w"] = ses.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                sets["got_h"] = ses.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                sets["got_fps"] = ses.cap.get(cv2.CAP_PROP_FPS)
                return sets
            # MSMF rebuilds its source reader on each format set (smoke 2026-11-09: the three sets took > 30 s on
            # the C930e and the C922, ~9 s on the Kiyo): bounded by the open timeout, as W-RAW bounds
            # "VideoCapture() and the property sets"; DSHOW keeps the call bound (>= 30 s)
            fmt_bound = a.open_timeout_ms / 1000.0 if a.backend == "msmf" else max(ses.T, 30.0)
            doc["format_bound_s"] = fmt_bound
            _, ms = ses.call("format sets", fmt, fmt_bound)
            doc["format"]["set_ms"] = round(ms, 1)
            doc["initial_get"] = ses.get_all("initial")
            if a.phase == "after":
                phase_after(ses, a, doc)
            else:
                phase_before(ses, a, doc)
            if a.backend == "msmf" and a.wincam:
                try:
                    p2 = subprocess.run([a.wincam, "activity", "--wait-ms", "1500"], capture_output=True, text=True,
                                        errors="replace", timeout=20)
                    j = json.loads(p2.stdout[p2.stdout.find("{"):p2.stdout.rfind("}") + 1])
                    doc["activity"] = [{"match_key": d.get("match_key"), "streaming": d.get("streaming"),
                                        "processes": [{k: x.get(k) for k in ("pid", "name", "streaming")}
                                                      for x in d.get("processes") or []]}
                                       for d in j.get("devices") or []]
                except Exception as e:  # noqa: BLE001
                    doc["activity"] = {"error": repr(e)}
            if not any(s["frames"] for s in ses.segments):
                doc["error"] = {"stage": "first_frame", "reason": "no frame read"}
                rc = 4
    except TimeoutError:
        rc = 5
        doc["error"] = {"stage": (ses.hung or {}).get("call"), "class": "timeout", "reason": "OpenCV call did not return"}
    except Exception as e:  # noqa: BLE001
        rc = 4
        doc["error"] = {"stage": "exception", "reason": repr(e)}
    finally:
        if ses.cap is not None and ses.hung is None:
            try:
                _, ms = ses.call("release", ses.cap.release)
                doc["close_ms"] = round(ms, 1)
            except TimeoutError:
                rc = 5
        ses.close_files()
    doc.update(events=ses.events, segments=ses.segments, hung=ses.hung, side_calls=ses.side.calls,
               frames_total=ses.seq, read_errors=ses.read_errors, unreleasable=ses.hung is not None,
               files={"frames_jsonl": str(ses.out / "frames.jsonl"), "frames_mjpeg": str(ses.out / "frames.mjpeg")},
               utc_finished=utc_now(), exit_code=rc, ok=rc == 0)
    (ses.out / "summary.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    sys.stdout.write(json.dumps(doc, default=str) + "\n")
    sys.stdout.flush()
    if rc == 5:
        os._exit(rc)
    sys.exit(rc)


if __name__ == "__main__":
    main()
