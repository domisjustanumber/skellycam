"""W-MULTI: several cameras at once (the skellycam pattern), and the topology's predicted conflicting pairs.

Plan section 6.2 (MULTI), section 5 (runtime algorithm and message template) and section 3 (G-BW thresholds).

Steps:
1. Topology: ``helpers/win_topology.collect()`` (no device requests; a W-TOPO descriptor JSON is used for alt
   numbers when one exists in the run folder). Bandwidth domains come from common.topology_model.
2. Learn each needed (camera, mode)'s real cost (plan section 5 "open it once alone and read the granted alt"):
   each camera alone through MF for a few seconds while a topology snapshot reads its open isochronous pipe.
   The cache is the RUN-ROOT ModeAltCache W-TOPO seeded (``<out_dir>/mode_alt_cache.json``, B4): learned entries
   are added to it and saved both there and to ``W-MULTI/mode_alt_cache.json``. Raw modes PyAV-as-is will
   negotiate (YUY2 where the camera natively offers it at the requested size and rate) are learned too.
3. (a) all cameras started together, one process per camera, default mode (MJPG 720p30 or nearest), --multi-reps
   times (10 / quick 2) with MF (wincam), DirectShow MJPEG (``ds``: pyav_ds --engine ffmpeg, i.e. the ffmpeg CLI
   with -vcodec mjpeg) and PyAV as-is (``pyav_ds``, which silently gets YUY2 where offered);
   (b) the same with starts staggered by 2.5 s (every camera overlaps the others for >= 2.5 s);
   (c) for every high-speed domain holding two or more cameras: camera A (the one with more in-scope MJPEG modes)
   at its default mode, at its switch partner (largest other in-scope size at ~30 fps), at its highest in-scope rate
   and at its smallest in-scope size, each with camera B at its default mode; per API. Mode scope (Dom 2026-11-06,
   common/modescope.py): only modes at >= 30 fps and >= 720 lines; each pair records its predicted verdict per A
   mode, and when no in-scope pair is predicted to fit, ``fits_side`` = "fits-side not testable under mode scope"
   (the predicted-over pairs and the cross-domain all-at-once runs still run). On Gerald every C922 + generic
   in-scope pair is predicted over (the old 640x480@30 / 1080p@5 "fits" pairs need ``--all-modes``).
4. Each failure is classified with ``topology_model.classify_failure`` with the FFmpeg log, the open duration and
   whether the camera was removed / re-arrived within ~1 s of the failure (multi_topo.md B1/B2/B8 per verifier):
   ``device_not_ready`` (RenderStream in the log, open > 2 s, or the camera dropping off the bus) is NOT a refusal;
   a refusal is a bandwidth_* class, or any other non-device class while another camera of the domain streams.
   Each refusal gets the user message (``explain``) and a retry of the losing camera alone (budget per (api, loser,
   run kind); for DirectShow-family APIs the retry first waits for the camera's re-arrival when the camera is the
   re-enumerating kind: up to 25 s before its first observed reset, then its learned delay + 2 s, extended to 25 s
   only while it is seen absent). Every child failure goes to the suite-wide first-failure record
   (``ctx.record_failure``); a helper's own timeout counts as a hang (health check), and a camera the suite marks
   faulted mid-test (``ctx.camera_faulted``) is skipped from the next run on. The message's "N s apart" is the real
   start gap between the two colliding cameras.
5. pyav_ds is predicted with the format it will actually negotiate (B3); a run whose observed format differs from
   the prediction is re-predicted with the observed pipe and tagged ``format_mismatch``.
6. Timing: absolute UTC start/end per run, camera and retry try; camera arrivals/removals are attributed by
   timestamp (an arrival up to 30 s after a failure of the same camera is "caused" by that failure), which fixes
   the one-run shift of the old per-run arrival check (B5).
7. Dead-device gate: a camera that returns device_error (e.g. 0x8007001F) or hangs past the watchdog and then fails
   a 1-frame MF health check is marked faulted and skipped ("untested: device fault since <ts>") in later runs;
   it is re-probed once at the start of each API phase and un-faulted if it answers.
All launches of one run share ONE camera lock (helpers/multi_launch.py), so the children really overlap.

Offline re-analysis (no camera, original files untouched):
    python w_multi.py --reanalyze RUN_DIR   # writes RUN_DIR/reanalysis/W-MULTI.json and reanalysis/messages.md
"""
from __future__ import annotations

import datetime as _dt
import itertools
import json
import sys
import time
from pathlib import Path

WIN = Path(__file__).resolve().parents[1]
for _p in (str(WIN.parent), str(WIN), str(WIN / "helpers"), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import capkit as ck  # noqa: E402
import suitectx  # noqa: E402
from common import rating, results, topology_model as tm  # noqa: E402

TEST = "W-MULTI"
#: mf = wincam (Media Foundation); ds = DirectShow through the ffmpeg CLI with -vcodec mjpeg (the MJPEG mode the
#: prediction assumes); pyav_ds = PyAV as-is, which takes the first dshow caps entry matching size and rate, i.e.
#: YUY2 where the camera natively offers it (predicted with that format, see pyav_format)
APIS = ("mf", "ds", "pyav_ds")
DS_FAMILY = ("ds", "pyav_ds")
TIMEOUT_MS = 5000
STAGGER_S = 2.5
#: classes that are never a bandwidth refusal, even while another camera of the domain streams
NOT_BW = ("device_error", "in_use", "permission", "device_not_ready")
RETRIES_PER_KEY = 2            # retry budget per (api, loser camera, run kind)  (B6)
REARRIVAL_WAIT_S = 25.0        # wait for a re-enumerating camera after a DirectShow failure (verifier F8: ~10.4-24.6 s)
REARRIVAL_MARGIN_S = 2.0       # after the first reset: wait the learned delay + this (extended to 25 s if seen absent)
GONE_WINDOW_S = (-1.0, 1.5)    # an arrival / removal this close to the failure end => device_not_ready
ATTRIBUTE_WINDOW_S = 30.0      # an arrival up to this long after a failure of the same camera is attributed to it
POLL_S = 0.5


# ============================================================================================================ helpers
def reps(ctx) -> tuple[int, int, int, float]:
    k = int(ck.arg(ctx, "multi_reps", 10, 2))
    stag = max(1, k // 2) if not ck.quick(ctx) else 1
    pair_reps = 1 if ck.quick(ctx) else 2
    secs = 3.0 if ck.quick(ctx) else 5.0
    return k, stag, pair_reps, secs


def estimate_s(ctx) -> float:
    k, stag, pr, secs = reps(ctx)
    n = max(1, len(ctx.cameras))
    learn = (n + 5) * (secs + 3)
    a = len(APIS) * k * (secs + 6)
    b = len(APIS) * stag * (secs + STAGGER_S * (n - 1) + 6)
    # shared-domain pair runs: up to 4 in-scope A modes per pair (default, switch partner, fastest, smallest)
    c = len(APIS) * 4 * pr * (secs + 8) + 30
    settle = len(DS_FAMILY) * (k + stag + 4 * pr) * 8   # waits for a re-enumerating camera's re-arrival
    return learn + a + b + c + settle


def parse_utc(s) -> float | None:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    try:
        return _dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def utc_iso(t: float | None) -> str | None:
    if t is None:
        return None
    return _dt.datetime.fromtimestamp(t, _dt.timezone.utc).isoformat()


def native_raw_modes(formats_mf: dict | None) -> set:
    """{('YUY2', w, h, fps rounded to 0.01)} natively offered (first stream with types). NV12 is ignored: MF lists
    NV12 types it synthesizes from MJPEG, which DirectShow (and so PyAV) does not offer."""
    out = set()
    for s in (formats_mf or {}).get("reader_streams") or []:
        types = s.get("types") or []
        if not types:
            continue
        for t in types:
            if str(t.get("subtype", "")).upper() != "YUY2":
                continue
            try:
                fps = int(t["fps_num"]) / max(1, int(t["fps_den"]))
                out.add(("YUY2", int(t["width"]), int(t["height"]), round(fps, 2)))
            except (KeyError, TypeError, ValueError):
                continue
        break
    return out


def pyav_format(raw: set, w: int, h: int, fps: float) -> str:
    """Format PyAV-as-is negotiates for a requested size and rate: YUY2 when the camera natively offers it there
    (dshow takes the first caps entry matching size and rate, and the raw entries come first), else MJPG."""
    for f, rw, rh, rf in raw:
        if f == "YUY2" and rw == w and rh == h and abs(rf - fps) < 0.5:
            return "YUY2"
    return "MJPG"


def mode_fmt_text(mode_text: str, fmt: str) -> str:
    p = tm.parse_mode(mode_text) or {}
    if not p:
        return mode_text
    return f"{fmt} {p['width']}x{p['height']}@{p['fps']:.4g}"


def negotiated_format(api: str, summary: dict | None, requested: str = "MJPG") -> str | None:
    """Format the camera actually delivered: MF and ds use the requested subtype (ds forces -vcodec mjpeg);
    pyav_ds reports the stream codec (mjpeg / rawvideo + pix_fmt)."""
    s = summary or {}
    if api != "pyav_ds":
        return requested
    neg = s.get("negotiated") or s.get("stream") or {}
    codec = str(neg.get("codec") or "").lower()
    pix = str(neg.get("pix_fmt") or "").lower()
    if codec == "mjpeg":
        return "MJPG"
    if "nv12" in pix:
        return "NV12"
    if codec in ("rawvideo", "yuyv422") or "yuyv" in pix or "yuy2" in pix or s.get("format_fallback"):
        return "YUY2"
    return None


def classify_camera(api: str, oc: dict, others_streaming: bool, predicted_verdict: str | None,
                    device_gone: bool) -> dict:
    """classify_failure with the device-not-ready context (FFmpeg log, open duration, device gone)."""
    err = oc.get("error") or {}
    ctxd = {"api": {"mf": "mf", "ds": "pyav_ds"}.get(api, api), "stage": oc.get("stage") or "",
            "timed_out": bool(oc.get("timed_out")), "frames": oc.get("frames"),
            "other_streaming_in_domain": bool(others_streaming), "device_gone": bool(device_gone)}
    if predicted_verdict:
        ctxd["predicted_verdict"] = predicted_verdict
    if api in DS_FAMILY:
        ctxd["log"] = err.get("ffmpeg_log") if isinstance(err, dict) else None
        if oc.get("t_end_s") is not None and oc.get("t_start_s") is not None:
            ctxd["open_duration_s"] = round(float(oc["t_end_s"]) - float(oc["t_start_s"]), 3)
    try:
        return tm.classify_failure("windows", oc.get("code"), ctxd)
    except Exception as e:  # noqa: BLE001
        return {"class": "other", "reason": f"classify_failure raised {e!r}", "code": oc.get("code")}


def counts_as_refusal(cls: str | None, others_streaming: bool) -> bool:
    """A bandwidth class, or any non-device class while another camera of the domain streams (verifier: keep the
    others-streaming rule so an unforeseen refusal at a 'fits' prediction still counts; exclude device_not_ready)."""
    return str(cls).startswith("bandwidth") or (bool(others_streaming) and cls not in NOT_BW)


def arrival_events(prev: dict, now: dict, tag: str) -> list[dict]:
    """Timestamped camera events between two arrival snapshots: 'arrival' (new LastArrivalDate, t = that date),
    'removal' (new LastRemovalDate), 'absent' / 'present' (presence flips, t = the check time)."""
    out = []
    if not (isinstance(prev, dict) and isinstance(now, dict) and "cameras" in prev and "cameras" in now):
        return out
    t_check = parse_utc(now.get("utc"))
    for k in sorted(set(prev["cameras"]) | set(now["cameras"])):
        a, b = prev["cameras"].get(k, {}), now["cameras"].get(k, {})
        if b.get("last_arrival") and b.get("last_arrival") != a.get("last_arrival"):
            out.append({"key": k, "kind": "arrival", "utc": b["last_arrival"], "t": parse_utc(b["last_arrival"]),
                        "seen_after": tag})
        if b.get("last_removal") and b.get("last_removal") != a.get("last_removal"):
            out.append({"key": k, "kind": "removal", "utc": b["last_removal"], "t": parse_utc(b["last_removal"]),
                        "seen_after": tag})
        if a.get("present") is True and b.get("present") is False:
            out.append({"key": k, "kind": "absent", "utc": now.get("utc"), "t": t_check, "seen_after": tag})
        if a.get("present") is False and b.get("present") is True:
            out.append({"key": k, "kind": "present", "utc": now.get("utc"), "t": t_check, "seen_after": tag})
    return out


def device_gone(key: str, fail_end: float | None, run_end: float | None, timeline: list[dict]) -> dict | None:
    """The camera was removed or re-arrived within GONE_WINDOW_S of its failure end (the open met a device that
    was dropping off the bus), or was absent at the first check after a run in which it was the last to end."""
    if fail_end is None:
        return None
    lo, hi = fail_end + GONE_WINDOW_S[0], fail_end + GONE_WINDOW_S[1]
    for e in timeline:
        if e["key"] != key or e.get("t") is None:
            continue
        if e["kind"] in ("arrival", "removal") and lo <= e["t"] <= hi:
            return {**e, "delta_s": round(e["t"] - fail_end, 3)}
        if e["kind"] == "absent" and run_end is not None and fail_end >= run_end - 1.5 and \
                fail_end <= e["t"] <= run_end + 30:
            return {**e, "delta_s": round(e["t"] - fail_end, 3), "note": "absent at the first check after the run"}
    return None


def attribute_arrivals(timeline: list[dict], failures: list[dict]) -> list[dict]:
    """For every arrival / absence, the latest failure of the same camera that ended before it (within
    ATTRIBUTE_WINDOW_S): [{event, failure (run tag, api, try), delay_s}]."""
    out = []
    for e in timeline:
        if e["kind"] not in ("arrival", "absent") or e.get("t") is None:
            continue
        cand = [f for f in failures if f["camera"] == e["key"] and f.get("t_end") is not None
                and f["t_end"] - 1.0 <= e["t"] <= f["t_end"] + ATTRIBUTE_WINDOW_S]
        if not cand:
            out.append({"event": e, "failure": None, "delay_s": None})
            continue
        f = max(cand, key=lambda x: x["t_end"])
        out.append({"event": e, "failure": {k: f.get(k) for k in ("run", "api", "camera", "where", "class",
                                                                  "utc_end")},
                    "delay_s": round(e["t"] - f["t_end"], 3)})
    return out


def _video_pipe(pipes: list[dict]) -> dict | None:
    iso = [p for p in pipes or [] if p.get("type") == "iso" and p.get("max_packet")]
    if not iso:
        return None
    return max(iso, key=lambda p: int(p["max_packet"]) * int(p.get("mult") or 1))


def _cost(pipe: dict | None, speed: str | None) -> float | None:
    if not pipe:
        return None
    return round(tm.cost_us(int(pipe["max_packet"]), int(pipe.get("mult") or 1),
                            "SS" if speed in ("SS", "SS+") else "HS"), 2)


# ============================================================================================================ events
def effective_requests(rec: dict) -> tuple[list[dict], bool]:
    """Requests with the format each camera actually delivered (observed pipe when it streamed), and whether any
    camera's observed format differs from the predicted one."""
    reqs, mismatch = [], False
    for oc in rec["cameras"]:
        if not oc.get("snapshot_key"):
            continue
        pf = oc.get("predicted_format") or "MJPG"
        of = oc.get("observed_format")
        streamed = bool(oc.get("ok") or oc.get("frames"))
        r = {"camera_key": oc["snapshot_key"], "mode": oc.get("predicted_mode") or oc.get("mode")}
        if streamed and of and of != pf:
            mismatch = True
            r["mode"] = mode_fmt_text(oc.get("mode"), of)
            if oc.get("observed_pipe"):
                r["max_packet"] = int(oc["observed_pipe"]["max_packet"])
                r["mult"] = int(oc["observed_pipe"].get("mult") or 1)
        reqs.append(r)
    return reqs, mismatch


def build_events(rec: dict, pred: dict, pred_eff: dict | None) -> list[dict]:
    """G-BW events of one run (one per domain holding 2+ requested cameras, or holding a refusal / not-ready)."""
    api, tag = rec["api"], rec["tag"]
    use = pred_eff or pred
    dom_req = {d["key"]: d for d in pred.get("domains", [])}
    evs = []
    for d in use.get("domains", []):
        members = [oc for oc in rec["cameras"] if oc.get("snapshot_key") in d.get("members", [])]
        dnr = [oc for oc in members if (oc.get("classification") or {}).get("class") == "device_not_ready"]
        losers = [oc for oc in members if oc.get("counts_as_refusal")]
        if len(members) < 2 and not losers:   # a camera alone in its domain is not a G-BW event
            continue
        streamed = [oc for oc in members if oc.get("ok") or oc.get("frames")]
        pf = {oc["camera"]: oc.get("predicted_format") for oc in members}
        of = {oc["camera"]: oc.get("observed_format") for oc in members if oc.get("ok") or oc.get("frames")}
        ev = {"api": api, "run": tag, "label": rec["label"], "kind": rec["kind"], "domain": d["key"],
              "predicted_verdict": d["verdict"],
              "predicted_verdict_as_planned": (dom_req.get(d["key"]) or {}).get("verdict"),
              "predicted_pct_microframe": d.get("pct_microframe"),
              "predicted_formats": pf, "observed_formats": of,
              "format_fallback": any(f and f != "MJPG" for f in list(pf.values()) + list(of.values())),
              "format_mismatch": pred_eff is not None,
              "observed_refused": bool(losers),
              "classified_class": (losers[0]["classification"].get("class") if losers else
                                   ("device_not_ready" if dnr else None)),
              "expected_bandwidth": True, "losers": [oc["camera"] for oc in losers],
              "device_not_ready": [oc["camera"] for oc in dnr],
              "excluded_device_not_ready": bool(dnr) and not losers,
              "all_streamed": len(streamed) == len(members),
              "message_ports_other_domains": None, "retry_ok": None}
        evs.append(ev)
    return evs


# ============================================================================================================ outcomes
def _find_descriptors(ctx) -> str | None:
    for p in sorted(Path(ctx.out_dir).rglob("*descriptor*.json")):
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")[:4000]
        except OSError:
            continue
        if '"devices"' in txt and "configuration" in txt:
            return str(p)
    return None


def _snapshot(desc: str | None) -> dict:
    import win_topology as wt  # noqa: PLC0415
    return wt.collect(descriptor_file=desc)


def _launch(ctx, items: list[tuple[str, list, float, float]], snaps_at: list[float], workdir: Path,
            desc: str | None, tag: str) -> tuple[dict | None, dict]:
    spec = {"commands": [{"label": lab, "argv": argv, "start_at_s": st, "timeout_s": to}
                         for lab, argv, st, to in items],
            "snapshots_at_s": snaps_at, "descriptor_file": desc, "snapshot_dir": None}
    tmax = max((st + to) for _, _, st, to in items) if items else 10
    return ck.multi_launch(ctx, spec, workdir / f"spec_{tag}.json", timeout_s=tmax + 60)


def _outcome(api: str, cmd: dict, requested_fmt: str = "MJPG") -> dict:
    s, _ = suitectx.parse_json_stdout({"stdout": cmd.get("stdout") or ""})
    s = s or {}
    fr = s.get("frames") or {}
    # the helper's own timeout counts too (ffmpeg CLI "timed out", a PyAV stage that never returned): the Kiyo's 35 s
    # DS hang on 11-06 was ended by pyav_ds itself, so cmd.timed_out was False and no health check ran
    timed_out = bool(cmd.get("timed_out") or s.get("timed_out") or s.get("hung"))
    code, stage, err = ck.failure_code(api, s, {"timed_out": timed_out})
    ok = bool(s.get("ok")) and not timed_out
    if api == "pyav_ds" and s.get("format_fallback") and (fr.get("total") or 0) > 0 and not timed_out:
        ok = True  # streamed (bandwidth question answered), format issue recorded separately
    return {"ok": ok, "frames": fr.get("total") or 0, "fps": s.get("fps_measured"), "rc": cmd.get("rc"),
            "timed_out": timed_out, "launcher_timed_out": bool(cmd.get("timed_out")),
            "code": code, "stage": stage, "error": err or None,
            "t_start_s": cmd.get("t_start_s"), "t_end_s": cmd.get("t_end_s"),
            "timings": s.get("timings"), "format_fallback": s.get("format_fallback"),
            "negotiated": s.get("negotiated"), "observed_format": negotiated_format(api, s, requested_fmt),
            "no_json": not bool(s), "stderr_tail": (cmd.get("stderr_tail") or "")[-400:] if not s else None}


def _ctx_call(ctx, name: str, *a, **kw):
    """Call a suite-wide fault-gate method of SuiteCtx when the runner provides it (camera_gated, mark_fault,
    health_probe, fault_reason); None otherwise or on error (the gate must never break the test)."""
    f = getattr(ctx, name, None)
    if not callable(f):
        return None
    try:
        return f(*a, **kw)
    except Exception:  # noqa: BLE001
        return None


class Multi:
    def __init__(self, ctx, snap: dict, desc: str | None, cache: tm.ModeAltCache, work: Path, raw: Path,
                 raw_modes: dict | None = None):
        self.ctx, self.snap, self.desc, self.cache, self.work, self.raw = ctx, snap, desc, cache, work, raw
        self.raw_modes = raw_modes or {}   # ctx key -> native raw modes (pyav_format)
        self.skey = {}       # ctx key -> snapshot camera key
        by_dev = {c["device_id"].upper(): c["key"] for c in snap.get("cameras", [])}
        snap_keys = {c["key"] for c in snap.get("cameras", [])}
        for c in ctx.cameras:
            k = by_dev.get(str(c.get("instance_id") or "").upper())
            if k is None and c["key"] in snap_keys:
                k = c["key"]
            self.skey[c["key"]] = k
        self.domain_of = {}  # snapshot camera key -> domain key
        dev_dom = {}
        for d in tm.compute_domains(snap):
            for m in d.get("members", []):
                dev_dom[m] = d["key"]
        for c in snap.get("cameras", []):
            self.domain_of[c["key"]] = dev_dom.get(c["device_id"])
        self.events: dict[str, list] = {api: [] for api in APIS}
        self.messages: list = []
        self.retry_used: dict[str, int] = {}
        self.n = 0
        self.last_arrivals = ck.arrivals_before(ctx)
        self.timeline: list[dict] = []
        self.failures: list[dict] = []     # every failure (runs and retry tries) with its absolute end time
        self.reenum: set = set()           # camera keys seen re-enumerating after a failure
        self.last_fail_end: dict[str, float] = {}
        self.faults: dict[str, dict] = {}  # dead-device gate (this test)
        self.fault_log: list[dict] = []
        self.settle_waits: list[dict] = []
        self.runs: list[dict] = []
        self.reset_delays: dict[str, list] = {}   # camera key -> observed re-arrival delays after its failures (s)

    # ------------------------------------------------------------------ helpers
    def argv(self, api: str, cam: dict, mode, secs: float, tag: str) -> list:
        od = self.raw / tag / ck.cam_slug(cam)
        if api == "mf":
            return ck.wincam_capture_argv(self.ctx, cam, mode, od, secs, timeout_ms=TIMEOUT_MS)
        a = ck.pyav_capture_argv(self.ctx, cam, mode, od, secs, timeout_ms=TIMEOUT_MS)
        return a + ["--engine", "ffmpeg"] if api == "ds" else a

    def has(self, api: str, cam: dict) -> bool:
        return bool(cam.get("mf_symlink") if api == "mf" else cam.get("ds_path"))

    def fmt_for(self, api: str, cam: dict, mode) -> str:
        if api == "pyav_ds":
            return pyav_format(self.raw_modes.get(cam["key"], set()), mode.w, mode.h, mode.fps)
        return mode.subtype or "MJPG"

    def predict(self, plan: list[tuple[dict, object]], api: str = "mf") -> dict:
        reqs = [{"camera_key": self.skey.get(c["key"]), "mode": mode_fmt_text(m.text, self.fmt_for(api, c, m))}
                for c, m in plan if self.skey.get(c["key"])]
        try:
            return tm.predict(self.snap, reqs, self.cache)
        except Exception as e:  # noqa: BLE001
            return {"error": repr(e), "domains": [], "conflicts": []}

    def poll_arrivals(self, tag: str) -> list[dict]:
        now = ck.arrivals_before(self.ctx)
        evs = arrival_events(self.last_arrivals, now, tag)
        if isinstance(now, dict) and "cameras" in now:
            self.last_arrivals = now
        for e in evs:
            self.timeline.append(e)
            if e["kind"] in ("arrival", "absent", "removal"):
                f = self.last_fail_end.get(e["key"])
                if f is not None and e.get("t") is not None and f - 1.0 <= e["t"] <= f + ATTRIBUTE_WINDOW_S:
                    if e["key"] not in self.reenum:
                        self.ctx.log(f"{TEST}: {e['key']} re-enumerates after a failure ({e['kind']} "
                                     f"{e['t'] - f:+.1f} s after it)")
                    self.reenum.add(e["key"])
                    if e["kind"] == "arrival" and e["t"] - f > 1.0:
                        self.reset_delays.setdefault(e["key"], []).append(round(e["t"] - f, 3))
        return evs

    def arrived_since(self, key: str, since_t: float) -> dict | None:
        for e in reversed(self.timeline):
            if e["key"] == key and e["kind"] == "arrival" and e.get("t") is not None and e["t"] >= since_t - 1.0:
                return e
        return None

    def learned_delay(self, key: str) -> float | None:
        """Median re-arrival delay of this camera after its own failures (seconds), None before its first reset."""
        d = sorted(self.reset_delays.get(key) or [])
        return d[len(d) // 2] if d else None

    def gone_since(self, key: str, since_t: float) -> bool:
        """The camera was seen absent or removed after ``since_t`` (it is dropping off the bus right now)."""
        return any(e["key"] == key and e["kind"] in ("absent", "removal") and e.get("t") is not None
                   and e["t"] >= since_t - 1.0 for e in self.timeline)

    def wait_rearrival(self, key: str, since_t: float, tag: str) -> dict:
        """Wait (bounded) until the camera re-arrives after ``since_t``: polls CfgMgr only, opens nothing.

        Deadline (analysis multi_topo H10 + verifier): before the camera's first observed reset, REARRIVAL_WAIT_S
        (25 s; run 1 saw a 24.6 s re-arrival); after it, the learned delay + REARRIVAL_MARGIN_S (11-06: every reset
        came 10.0-10.1 s after the failure), extended to REARRIVAL_WAIT_S only while the camera is seen absent or
        removed during the wait."""
        t0 = time.time()
        learned = self.learned_delay(key)
        short = since_t + learned + REARRIVAL_MARGIN_S if learned is not None else None
        deadline = min(short, since_t + REARRIVAL_WAIT_S) if short is not None else since_t + REARRIVAL_WAIT_S
        extended = False
        e = self.arrived_since(key, since_t)
        while e is None and time.time() < deadline:
            time.sleep(POLL_S)
            self.poll_arrivals(tag)
            e = self.arrived_since(key, since_t)
            if not extended and short is not None and self.gone_since(key, since_t):
                deadline, extended = since_t + REARRIVAL_WAIT_S, True
        present = ((self.last_arrivals or {}).get("cameras") or {}).get(key, {}).get("present")
        return {"camera": key, "since_utc": utc_iso(since_t), "waited_s": round(time.time() - t0, 2),
                "arrived_utc": e.get("utc") if e else None, "timed_out": e is None, "present": present,
                "learned_delay_s": learned, "deadline_after_failure_s": round(deadline - since_t, 2),
                "extended_because_absent": extended}

    # ------------------------------------------------------------------ dead-device gate
    def faulted(self, cam: dict) -> dict | None:
        """This test's fault record, or the suite gate's (SuiteCtx.camera_gated) for a camera faulted earlier."""
        if cam["key"] in self.faults:
            return self.faults[cam["key"]]
        gated = _ctx_call(self.ctx, "camera_gated", cam["key"])
        # a fault raised DURING this test (camcmd scan, the W-KIYO poller, a health probe) is not in camera_gated,
        # which holds only the cameras gated at begin_test; 11-06: the Kiyo was launched 15 more times after it
        rec = gated or _ctx_call(self.ctx, "camera_faulted", cam["key"])
        if rec:
            src = "suite gate" if gated else f"suite fault during {TEST} ({rec.get('source')})"
            info = {"camera": cam["key"], "since_utc": rec.get("since_utc"), "test": rec.get("test"),
                    "mode": rec.get("mode"), "code": rec.get("code"), "class": rec.get("class"), "source": src,
                    "reason": _ctx_call(self.ctx, "fault_reason", cam["key"])}
            self.faults[cam["key"]] = info
            self.fault_log.append({"event": f"faulted ({src})", "utc": results.utc_now_iso(), **info})
            return info
        return None

    def mark_fault(self, cam: dict, where: str, api: str, mode, code, cls: str, reason: str | None) -> None:
        """Dead-device gate: skip the camera in later runs. Also reported to the suite-wide gate (the SuiteCtx
        camcmd scanner cannot see inside a multi_launch child's output)."""
        if cam["key"] in self.faults:
            return
        info = {"camera": cam["key"], "since_utc": results.utc_now_iso(), "test": TEST, "where": where, "api": api,
                "mode": getattr(mode, "text", str(mode)), "code": code, "class": cls, "reason": reason}
        self.faults[cam["key"]] = info
        self.fault_log.append({"event": "faulted", **info})
        _ctx_call(self.ctx, "mark_fault", cam, test=TEST, mode=info["mode"], code=code, api=api, stage=where,
                  cls=cls, source=f"{TEST} multi_launch child", detail={"reason": reason})
        self.ctx.log(f"{TEST}: {cam['key']} marked faulted ({cls} {code} at {where}); skipped until it answers a "
                     "1-frame health check")

    def health_check(self, cam: dict, mode, tag: str) -> dict:
        """1-frame MF capture under camlock with a timeout: SuiteCtx.health_probe when available (it also updates
        the suite-wide fault state), else capkit.wincam_capture."""
        hp = _ctx_call(self.ctx, "health_probe", cam["key"], test=TEST, mode=mode, timeout_ms=3000,
                       reason=f"{TEST} {tag}")
        if isinstance(hp, dict) and hp.get("ok") is not None:
            return hp
        if not cam.get("mf_symlink") or mode is None:
            return {"ok": None, "note": "no MF link or mode"}
        try:
            s, r = ck.wincam_capture(self.ctx, cam, mode, self.raw / "health" / tag / ck.cam_slug(cam), frames=1,
                                     timeout_ms=3000, timeout_s=25)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": repr(e)}
        s = s or {}
        frames = (s.get("frames") or {}).get("total") or 0
        return {"ok": bool(s.get("ok")) and frames >= 1, "frames": frames, "error": s.get("error"),
                "timed_out": r.get("timed_out"), "utc": results.utc_now_iso()}

    def reprobe_faults(self, modes: dict, phase: str) -> None:
        """Re-probe every faulted camera once (1-frame MF) at the start of an API phase; un-fault it if it answers."""
        for cam in self.ctx.cameras:
            if not self.faulted(cam):
                continue
            hc = self.health_check(cam, modes.get(cam["key"]), f"reprobe_{phase}")
            self.fault_log.append({"event": "reprobe", "camera": cam["key"], "phase": phase,
                                   "health": {k: hc.get(k) for k in ("ok", "frames", "code", "class", "utc",
                                                                     "timed_out", "recovered")}})
            if hc.get("ok"):
                info = self.faults.pop(cam["key"])
                self.fault_log.append({"event": "recovered", "camera": cam["key"], "phase": phase,
                                       "faulted_since": info.get("since_utc"), "utc": results.utc_now_iso()})
                self.ctx.log(f"{TEST}: {cam['key']} answers again ({phase}); un-faulted")

    # ------------------------------------------------------------------ learning
    def learn(self, plan: list[tuple[dict, object]], secs: float) -> list[dict]:
        """Open each (camera, mode) alone through MF, read the open iso pipe mid-stream, store in the cache."""
        items, snaps, meta = [], [], []
        t = 0.0
        skipped = []
        for i, (cam, mode) in enumerate(plan):
            if not cam.get("mf_symlink"):
                continue
            if self.faulted(cam):   # dead-device gate: recorded, not opened
                skipped.append({"camera": cam["key"], "mode": mode.text,
                                "untested": f"device fault since {self.faulted(cam).get('since_utc')}"})
                continue
            items.append((f"learn{i}", self.argv("mf", cam, mode, secs, f"learn/{i}"), t, secs + 25))
            snaps.append(t + min(secs, 2.0) + 1.2)
            meta.append((cam, mode, t))
            t += secs + 3.5
        if not items:
            return [{"skipped_faulted": skipped}] if skipped else []
        out, run = _launch(self.ctx, items, snaps, self.work, self.desc, "learn")
        learned = []
        snap_list = (out or {}).get("snapshots") or []
        cmds = (out or {}).get("commands") or []
        for j, (cam, mode, _t) in enumerate(meta):
            sk = self.skey.get(cam["key"])
            oc = _outcome("mf", cmds[j], mode.subtype) if j < len(cmds) else {"ok": False}
            sn = snap_list[j] if j < len(snap_list) else {}
            obs = (sn.get("observed") or {}).get(sk) or {}
            pipe = _video_pipe(obs.get("iso_pipes"))
            rec = {"camera": cam["key"], "snapshot_key": sk, "mode": mode.text, "capture_ok": oc.get("ok"),
                   "frames": oc.get("frames"), "observed_alt": obs.get("current_alt"), "pipe": pipe,
                   "snapshot_error": sn.get("error")}
            if not oc.get("ok") and j < len(cmds):
                cl = classify_camera("mf", oc, False, None, False)
                rec["classification"] = cl
                if cl.get("class") == "device_error" and _wedged_code(cl):
                    self.mark_fault(cam, "learn", "mf", mode, cl.get("code_hex") or oc.get("code"), cl["class"],
                                    cl.get("reason"))
            if pipe and oc.get("ok"):
                self.cache.put(cam.get("vid"), cam.get("pid"), cam.get("bcd_device"), mode.subtype, mode.w, mode.h,
                               mode.fps, obs.get("current_alt"), max_packet=int(pipe["max_packet"]),
                               mult=int(pipe.get("mult") or 1), source="observed W-MULTI learn",
                               utc=results.utc_now_iso())
                rec["cost_us"] = _cost(pipe, cam.get("speed"))
            learned.append(rec)
        return learned + [{"launcher_run": run, "skipped_faulted": skipped}]

    # ------------------------------------------------------------------ one concurrent run
    def run_set(self, api: str, plan: list[tuple[dict, object]], secs: float, stagger: float, label: str,
                kind: str) -> dict:
        skipped = [{"camera": c["key"], "untested": f"device fault since {self.faulted(c).get('since_utc')}",
                    "fault": self.faulted(c)} for c, m in plan if self.faulted(c)]
        plan = [(c, m) for c, m in plan if self.has(api, c) and m is not None and not self.faulted(c)]
        self.n += 1
        tag = f"{api}_{label}_{self.n:03d}"
        n = len(plan)
        items = []
        for i, (cam, mode) in enumerate(plan):
            st = i * stagger
            dur = secs + (n - 1 - i) * stagger
            items.append((cam["key"], self.argv(api, cam, mode, dur, tag), st, dur + 30))
        snap_at = [(n - 1) * stagger + 1.5 + secs / 2.0]  # mid-overlap: last camera started, first still on
        pred = self.predict(plan, api)
        t_call = time.time()
        out, run = _launch(self.ctx, items, snap_at, self.work, self.desc, tag) if items else (None, {})
        t_back = time.time()
        cmds = (out or {}).get("commands") or []
        snaps = (out or {}).get("snapshots") or []
        obs = (snaps[0].get("observed") if snaps else None) or {}
        # absolute time of the launcher's t0 (same QPC clock as t_start_s / t_end_s)
        ends = [c.get("t_end_s") for c in cmds if c.get("t_end_s") is not None]
        fin = parse_utc((out or {}).get("utc_finished"))
        if fin is not None and ends:
            t0, t0_src = fin - max(ends), "utc_finished - max(t_end_s)"
        else:
            t0, t0_src = t_call + float(run.get("lock_wait_s") or 0), "call time + lock wait (approximate)"
        dom_verdict = {d["key"]: d["verdict"] for d in pred.get("domains", [])}
        req_cost = {r.get("camera_key"): r.get("cost_us") for r in pred.get("requests", [])}
        cams = []
        for i, (cam, mode) in enumerate(plan):
            pf = self.fmt_for(api, cam, mode)
            oc = _outcome(api, cmds[i], pf) if i < len(cmds) else {"ok": False, "no_json": True, "frames": 0}
            sk = self.skey.get(cam["key"])
            pipe = _video_pipe((obs.get(sk) or {}).get("iso_pipes"))
            oc.update(camera=cam["key"], name=cam.get("name"), mode=mode.text, snapshot_key=sk,
                      predicted_format=pf, predicted_mode=mode_fmt_text(mode.text, pf),
                      domain=self.domain_of.get(sk), predicted_domain_verdict=dom_verdict.get(self.domain_of.get(sk)),
                      predicted_cost_us=req_cost.get(sk), observed_pipe=pipe, observed_cost_us=_cost(pipe, cam.get("speed")),
                      utc_start=utc_iso(t0 + oc["t_start_s"]) if oc.get("t_start_s") is not None else None,
                      utc_end=utc_iso(t0 + oc["t_end_s"]) if oc.get("t_end_s") is not None else None)
            cams.append(oc)
        run_end = t0 + max(ends) if ends else t_back
        rec = {"api": api, "label": label, "kind": kind, "tag": tag, "stagger_s": stagger, "seconds": secs,
               "utc_start": utc_iso(t0), "utc_end": utc_iso(run_end), "t0_source": t0_src,
               "cameras": cams, "skipped_faulted": skipped, "launcher": run,
               "snapshot_error": snaps[0].get("error") if snaps else "no snapshot"}
        # arrivals right after the run (wait until the GONE window after the last failure has passed, max 2 s)
        fails = [parse_utc(oc.get("utc_end")) for oc in cams if not oc["ok"] and oc.get("utc_end")]
        if fails:
            ck.wait_s(min(2.0, max(0.0, max(fails) + GONE_WINDOW_S[1] - time.time())))
        rec["arrival_events"] = self.poll_arrivals(tag)
        self.classify_run(rec, pred)
        # effective prediction when a camera delivered another format than predicted (PyAV fallback, B3)
        reqs_eff, mismatch = effective_requests(rec)
        pred_eff = None
        if mismatch:
            try:
                pred_eff = tm.predict(self.snap, reqs_eff, self.cache)
            except Exception as e:  # noqa: BLE001
                rec["effective_prediction_error"] = repr(e)
        rec["prediction"] = _pred_brief(pred)
        if pred_eff is not None:
            rec["prediction_observed_formats"] = _pred_brief(pred_eff)
        evs = build_events(rec, pred, pred_eff)
        for ev in evs:
            if ev["observed_refused"]:
                loser = next(oc for oc in cams if oc["camera"] == ev["losers"][0])
                msg = self.message(rec, reqs_eff, ev["domain"], loser)
                ev["message_ports_other_domains"] = msg.get("ports_other_domains")
                ev["labels_raw"] = msg.get("labels_raw")
                ev["message_index"] = msg.get("index")
                r = self.retry(api, loser, plan, kind, tag)
                if r is not None:
                    ev["retry_ok"], ev["retry_first_try_ok"], ev["retry"] = r
            self.events[api].append(ev)
        rec["events"] = [{k: ev.get(k) for k in ("domain", "predicted_verdict", "observed_refused",
                                                 "classified_class", "losers", "device_not_ready")} for ev in evs]
        self.settle(rec)
        self.runs.append(rec)
        return rec

    def classify_run(self, rec: dict, pred: dict) -> None:
        cams = rec["cameras"]
        run_end = parse_utc(rec.get("utc_end"))
        for oc in cams:
            if oc["ok"]:
                continue
            others = [x for x in cams if x is not oc and x.get("domain") and x["domain"] == oc.get("domain")
                      and (x["ok"] or x["frames"])]
            fe = parse_utc(oc.get("utc_end"))
            gone = device_gone(oc["camera"], fe, run_end, self.timeline)
            oc["device_gone"] = gone
            cl = classify_camera(rec["api"], oc, bool(others), oc.get("predicted_domain_verdict"), bool(gone))
            oc["classification"] = cl
            oc["counts_as_refusal"] = counts_as_refusal(cl.get("class"), bool(others))
            if fe is not None:
                self.last_fail_end[oc["camera"]] = fe
                self.failures.append({"run": rec["tag"], "api": rec["api"], "camera": oc["camera"], "where": "run",
                                      "class": cl.get("class"), "t_end": fe, "utc_end": oc.get("utc_end")})
                if any(e["key"] == oc["camera"] and e["kind"] in ("arrival", "absent", "removal") and e.get("t")
                       and fe - 1.0 <= e["t"] <= fe + ATTRIBUTE_WINDOW_S for e in self.timeline):
                    self.reenum.add(oc["camera"])
            cam = next((c for c in self.ctx.cameras if c["key"] == oc["camera"]), None)
            # the suite-wide first failure per camera: camcmd cannot see inside a multi_launch child (11-06: the C922's
            # 33 W-MULTI failures left no entry, and the Kiyo's 03:03.8 DS hang was not its first failure)
            if cam is not None:
                _ctx_call(self.ctx, "record_failure", cam, test=TEST, mode=oc.get("mode"),
                          code=cl.get("code_hex") or oc.get("code") or ("timeout" if oc.get("timed_out") else None),
                          api=rec["api"], stage=oc.get("stage"), cls=cl.get("class"),
                          source=f"{TEST} multi_launch child ({rec['tag']})", utc=oc.get("utc_start"),
                          detail={"run": rec["tag"], "counts_as_refusal": oc.get("counts_as_refusal")})
            if cam is not None and cl.get("class") == "device_error" and _wedged_code(cl):
                self.mark_fault(cam, rec["tag"], rec["api"], oc.get("mode"), cl.get("code_hex") or oc.get("code"),
                                cl["class"], cl.get("reason"))
            elif cam is not None and oc.get("timed_out"):   # hung past the watchdog: confirm with a health check
                hc = self.health_check(cam, _mode_from_text(oc.get("mode")), rec["tag"])
                oc["health_check_after_hang"] = hc
                if not hc.get("ok"):
                    self.mark_fault(cam, rec["tag"], rec["api"], oc.get("mode"), "watchdog timeout", "hang",
                                    "reader hung past the watchdog and the 1-frame health check failed")

    def settle(self, rec: dict) -> None:
        """Before the next run: wait for a re-enumerating camera that failed under a DirectShow-family API to come
        back (bounded), so the next run does not meet a device that is dropping off the bus."""
        if rec["api"] not in DS_FAMILY:
            return
        for oc in rec["cameras"]:
            k = oc["camera"]
            if oc["ok"] or k not in self.reenum or k in self.faults:
                continue
            since = self.last_fail_end.get(k)
            if since is None or self.arrived_since(k, since):
                continue
            w = self.wait_rearrival(k, since, f"settle_{rec['tag']}")
            w["after_run"] = rec["tag"]
            self.settle_waits.append(w)
            rec.setdefault("settle_waits", []).append(w)

    def message(self, rec: dict, reqs: list[dict], dom_key: str, loser: dict) -> dict:
        failure = message_failure(rec, loser)
        try:
            ex = tm.explain(self.snap, reqs, self.cache, failure=failure)
        except Exception as e:  # noqa: BLE001
            self.messages.append({"run": rec["tag"], "domain": dom_key, "error": repr(e)})
            return {"index": len(self.messages) - 1, "ports_other_domains": None}
        return record_message(self.messages, rec, ex, dom_key, loser, failure)

    def retry(self, api: str, loser: dict, plan, kind: str, tag: str) -> tuple[bool, bool, dict] | None:
        key = f"{api}|{loser['camera']}|{kind}"
        if self.retry_used.get(key, 0) >= RETRIES_PER_KEY:
            return None
        self.retry_used[key] = self.retry_used.get(key, 0) + 1
        cam = next(c for c, _ in plan if c["key"] == loser["camera"])
        mode = next(m for c, m in plan if c["key"] == loser["camera"])
        od = self.raw / "retry" / f"{api}_{self.n:03d}_{ck.cam_slug(cam)}"   # short: MAX_PATH
        fail_end = parse_utc(loser.get("utc_end")) or time.time()
        tries = []
        for k in range(2):  # retry once; if that fails, once more to see whether the camera recovers at all
            wait = None
            if api in DS_FAMILY and (cam["key"] in self.reenum or k == 1):
                wait = self.wait_rearrival(cam["key"], fail_end, f"retry_{tag}")
            elif k == 1:
                time.sleep(1.0)
            ts = time.time()
            if api == "mf":
                s, r = ck.wincam_capture(self.ctx, cam, mode, od / f"try{k}", seconds=2.0, timeout_ms=TIMEOUT_MS)
            else:
                extra = ["--engine", "ffmpeg"] if api == "ds" else []
                s, r = ck.pyav_capture(self.ctx, cam, mode, od / f"try{k}", seconds=2.0, timeout_ms=TIMEOUT_MS,
                                       extra=extra)
            te = time.time()
            s = s or {}
            frames = (s.get("frames") or {}).get("total") or 0
            ok = bool(s.get("ok")) or (api != "mf" and frames > 0)
            tries.append({"ok": ok, "frames": frames, "error": s.get("error"), "run": r, "utc_start": utc_iso(ts),
                          "utc_end": utc_iso(te), "waited_for_rearrival": wait})
            self.poll_arrivals(f"{tag}_retry{k}")
            if ok:
                break
            fail_end = te
            self.last_fail_end[cam["key"]] = te
            self.failures.append({"run": tag, "api": api, "camera": cam["key"], "where": f"retry try{k}",
                                  "class": None, "t_end": te, "utc_end": utc_iso(te)})
        final_ok, first_ok = tries[-1]["ok"], tries[0]["ok"]
        return final_ok, first_ok, {"ok": final_ok, "first_try_ok": first_ok,
                                    "recovered_on_second_try": tries[1]["ok"] if len(tries) > 1 else None,
                                    "tries": tries, "budget_key": key,
                                    "note": "the losing camera alone after the refused run; for DirectShow-family "
                                            "APIs a re-enumerating camera's re-arrival is awaited first "
                                            f"(up to {REARRIVAL_WAIT_S:g} s); retry_ok = the final try"}


#: device_error codes that mean "wedged until a replug" (dead-device gate); transient ones (device invalidated,
#: not connected: a re-enumeration) are not faults
WEDGED_CODES = (0x8007001F, 0xC00D7167, 0x800701E3)


def _wedged_code(cl: dict) -> bool:
    c = cl.get("code")
    try:
        return (int(c) & 0xFFFFFFFF) in WEDGED_CODES
    except (TypeError, ValueError):
        return False


def _mode_from_text(text: str | None):
    p = tm.parse_mode(text)
    if not p or not p.get("fps"):
        return None
    fps = p["fps"]
    num, den = (int(round(fps)), 1) if abs(fps - round(fps)) < 1e-6 else (int(round(fps * 1000)), 1000)
    return ck.Mode(p["width"], p["height"], num, den, p["format"])


def _pred_brief(pred: dict) -> dict:
    return {"domains": pred.get("domains"),
            "conflicts": [{k: c.get(k) for k in ("domain_key", "cameras", "pct_total", "pct_microframe", "verdict")}
                          for c in pred.get("conflicts", [])]}


def message_failure(rec: dict, loser: dict) -> dict:
    """classify_failure output + loser + stagger context for build_message. ``stagger_s`` is the real start gap
    between the loser and the nearest same-domain camera (analysis multi_topo H7: with the Kiyo starting between
    them, the C922 and the generic camera were 5.0 s apart, not the 2.5 s step); the run's step is kept as
    ``stagger_step_s``."""
    failure = dict(loser.get("classification") or {})
    failure["loser"] = loser["snapshot_key"]
    st = float(rec.get("stagger_s") or 0)
    if st > 0:
        failure["stagger_step_s"] = st
        failure["stagger_s"] = st
        same = [oc for oc in rec["cameras"] if oc.get("domain") == loser.get("domain")]
        order = sorted(same, key=lambda oc: oc.get("t_start_s") or 0)
        if len(order) >= 2:
            failure["loser_position"] = "first" if order[0] is loser else ("last" if order[-1] is loser else None)
            gap = start_gap_s(loser, [oc for oc in same if oc is not loser])
            if gap is not None and gap > 0:
                failure["stagger_s"] = round(gap, 2)
    return failure


def start_gap_s(loser: dict, others: list[dict]) -> float | None:
    """Seconds between the loser's start and the nearest same-domain camera that started before it (or, when the
    loser started first, the next one after it). None without start times."""
    t = loser.get("t_start_s")
    ts = [oc.get("t_start_s") for oc in others if oc.get("t_start_s") is not None]
    if t is None or not ts:
        return None
    before = [x for x in ts if x <= t]
    return float(t - max(before)) if before else float(min(ts) - t)


def record_message(messages: list, rec: dict, ex: dict, dom_key: str, loser: dict, failure: dict) -> dict:
    m = next((x for x in ex.get("messages", []) if x["domain_key"] == dom_key), None)
    if m is None:
        messages.append({"run": rec["tag"], "domain": dom_key, "loser": loser["camera"], "message": None,
                         "failure": failure,
                         "note": "no conflict predicted for this domain: the refusal was not foreseen, so no message "
                                 "was built"})
        return {"index": len(messages) - 1, "ports_other_domains": None}
    ports = [p for g in m.get("suggestions", []) for p in g.get("ports", [])]
    other = all(p.get("domain_key") != dom_key for p in ports) if ports else None
    raw_labels = tm.labels_raw([p.get("label", "") for p in ports])
    messages.append({"run": rec["tag"], "api": rec["api"], "kind": rec["kind"], "domain": dom_key,
                     "loser": loser["camera"], "failure": failure, "message": m["message"],
                     "moving_camera": m.get("moving_camera_key"),
                     "suggested_ports": [{k: p.get(k) for k in ("port_id", "label", "rank", "domain_key",
                                                                "shares_with", "evidence")} for p in ports],
                     "label_tiers": sorted({tm.label_tier(p.get("label", "")) for p in ports}),
                     "alternatives": m.get("alternatives")})
    return {"index": len(messages) - 1, "ports_other_domains": other, "labels_raw": raw_labels}


def rate_events(events: dict[str, list]) -> tuple[dict, dict]:
    """G-BW verdict per API plus a per-API summary (device_not_ready and format events counted separately)."""
    verdicts, summary = {}, {}
    for api in APIS:
        evs = events.get(api) or []
        lr = [e.get("labels_raw") for e in evs if "labels_raw" in e and e.get("labels_raw") is not None]
        labels_raw = any(lr) if lr else None
        amb = [api] if any(e.get("classified_class") == "bandwidth_probable" for e in evs) else []
        verdicts[f"G-BW|all|{api}"] = rating.rate_bw(evs, labels_raw=labels_raw, ambiguous_apis=amb)
        summary[api] = {
            "events": len(evs), "refusals": sum(1 for e in evs if e.get("observed_refused")),
            "device_not_ready_events": sum(1 for e in evs if e.get("device_not_ready")),
            "excluded_device_not_ready": sum(1 for e in evs if e.get("excluded_device_not_ready")),
            "format_mismatch_events": sum(1 for e in evs if e.get("format_mismatch")),
            "format_fallback_events": sum(1 for e in evs if e.get("format_fallback")),
            "false_fits": sum(1 for e in evs if e.get("observed_refused") and e.get("predicted_verdict") == "fits"),
            "false_over": sum(1 for e in evs if e.get("predicted_verdict") == "over" and e.get("all_streamed")),
            "retried": sum(1 for e in evs if e.get("retry_ok") is not None),
            "retry_final_ok": sum(1 for e in evs if e.get("retry_ok") is True),
            "retry_first_try_ok": sum(1 for e in evs if e.get("retry_first_try_ok") is True),
            "rating": verdicts[f"G-BW|all|{api}"].get("rating")}
    return verdicts, summary


# ============================================================================================================ run
def run(ctx) -> dict:
    res = ck.new_result(ctx, TEST)
    arr0 = ck.arrivals_before(ctx)
    k, stag, pair_reps, secs = reps(ctx)
    errors: list = []
    work = Path(ctx.out_dir) / TEST
    raw = Path(ctx.raw_dir) / TEST
    work.mkdir(parents=True, exist_ok=True)
    desc = _find_descriptors(ctx)
    try:
        snap = _snapshot(desc)
    except Exception as e:  # noqa: BLE001
        res = results.finish_result(res, measurements={}, verdicts={"G-BW": rating.untested(f"topology failed: {e!r}")},
                                    errors=[repr(e)])
        return res
    results.write_json(work / "topology_snapshot.json", snap)
    # the run-root cache W-TOPO seeded (B4); seeded here when W-TOPO did not run
    root_cache = Path(ctx.out_dir) / "mode_alt_cache.json"
    try:
        from w_topo import seed_cache  # noqa: PLC0415
        cache = seed_cache(root_cache)
    except Exception as e:  # noqa: BLE001
        errors.append({"cache": f"seeding failed: {e!r}"})
        cache = tm.ModeAltCache.load(root_cache)
    cache.path = root_cache
    # modes per camera (MJPEG) and native raw modes (what PyAV-as-is negotiates)
    cache_f: dict = {}
    modes_of, dflt, raw_modes, scope_of = {}, {}, {}, {}
    for cam in ctx.cameras:
        fm, _ = ck.get_formats(ctx, cam, cache_f)
        advertised = ck.mjpeg_modes(fm)
        # mode scope (common/modescope.py): only modes at >= 30 fps and >= 720 lines unless --all-modes
        modes_of[cam["key"]], scope_of[cam["key"]] = ck.scoped(ctx, advertised)
        dflt[cam["key"]] = ck.default_mode(modes_of[cam["key"]]) if modes_of[cam["key"]] else None
        scope_of[cam["key"]]["default_mode"] = dflt[cam["key"]].text if dflt[cam["key"]] else None
        if advertised and not modes_of[cam["key"]]:
            scope_of[cam["key"]]["untested_reason"] = ck.modescope.no_scope_mode_reason(ck.mode_scope(ctx),
                                                                                        len(advertised))
            ctx.log(f"{TEST}: {cam.get('name')}: {scope_of[cam['key']]['untested_reason']}")
        raw_modes[cam["key"]] = native_raw_modes(fm)
    mt = Multi(ctx, snap, desc, cache, work, raw, raw_modes)
    # pairs from shared high-speed domains
    by_dom: dict[str, list] = {}
    for cam in ctx.cameras:
        dk = mt.domain_of.get(mt.skey.get(cam["key"]))
        if dk and dk.startswith("hs|") and dflt.get(cam["key"]):
            by_dom.setdefault(dk, []).append(cam)
    pair_plans = []
    for dk, cams in by_dom.items():
        if len(cams) < 2:
            continue
        for a, b in itertools.combinations(cams, 2):
            A, B = (a, b) if len(modes_of[a["key"]]) >= len(modes_of[b["key"]]) else (b, a)
            ma = modes_of[A["key"]]
            a_modes = []
            # in-scope candidates for A (B at its default): the default, the switch partner (largest other size at
            # ~30 fps), the highest rate and the smallest in-scope size (the cheapest guess for a "fits" pair)
            fastest = max(ma, key=lambda x: (x.fps, -x.w * x.h)) if ma else None
            smallest = min(ma, key=lambda x: (x.w * x.h, x.fps)) if ma else None
            cands = [dflt[A["key"]], ck.switch_mode(ma, dflt[A["key"]]), fastest, smallest]
            if ck.mode_scope(ctx).all_modes:
                # --all-modes: also the plan section 5 pairs (C922 640x480@30 / 1080p@5 + generic, predicted fits)
                cands += [ck.alt_mode(ma, dflt[A["key"]]), ck.lowest_rate_largest(ma)]
            for m in cands:
                if m is not None and m not in a_modes:
                    a_modes.append(m)
            pair_plans.append({"domain": dk, "A": A, "B": B, "a_modes": a_modes})
    # 1. learn costs (each camera alone at its default; pair A's extra modes; raw modes PyAV will negotiate)
    learn_plan = [(c, dflt[c["key"]]) for c in ctx.cameras if dflt.get(c["key"])]
    for pp in pair_plans:
        for m in pp["a_modes"]:
            if (pp["A"], m) not in learn_plan:
                learn_plan.append((pp["A"], m))
    for c, m in list(learn_plan):
        if pyav_format(raw_modes.get(c["key"], set()), m.w, m.h, m.fps) == "YUY2":
            ym = ck.Mode(m.w, m.h, m.fps_num, m.fps_den, "YUY2")
            if (c, ym) not in learn_plan:
                learn_plan.append((c, ym))
    ctx.log(f"{TEST}: learning {len(learn_plan)} (camera, mode) costs; {len(pair_plans)} shared-domain pairs")
    learned = mt.learn(learn_plan, secs=min(secs, 3.0))
    cache.save(root_cache)
    cache.save(work / "mode_alt_cache.json")
    # predicted verdict of each in-scope pair (learned costs); under the mode scope a shared domain may have no
    # pair predicted to fit: then only the refused side is testable there (fits side: cameras in other domains)
    for pp in pair_plans:
        pp["predicted"] = {}
        for m in pp["a_modes"]:
            pr = mt.predict([(pp["A"], m), (pp["B"], dflt[pp["B"]["key"]])])
            dv = {d.get("key"): d.get("verdict") for d in pr.get("domains", [])}
            pp["predicted"][m.text] = dv.get(pp["domain"]) or ("error" if pr.get("error") else None)
        pp["fits_testable"] = any(v == "fits" for v in pp["predicted"].values())
    all_plan = [(c, dflt[c["key"]]) for c in ctx.cameras if dflt.get(c["key"])]
    pred_all = mt.predict(all_plan)
    for api in APIS:
        if api != APIS[0]:   # the runner (SuiteCtx.begin_test) already re-probed faulted cameras at test start
            mt.reprobe_faults(dflt, api)
        for i in range(k):
            ctx.log(f"{TEST}: {api} all-at-once {i + 1}/{k}")
            try:
                mt.run_set(api, all_plan, secs, 0.0, "all_together", "simultaneous")
            except Exception as e:  # noqa: BLE001
                errors.append({"api": api, "kind": "simultaneous", "exception": repr(e)})
        for i in range(stag):
            ctx.log(f"{TEST}: {api} staggered {i + 1}/{stag}")
            try:
                mt.run_set(api, all_plan, secs, STAGGER_S, "staggered", "staggered")
            except Exception as e:  # noqa: BLE001
                errors.append({"api": api, "kind": "staggered", "exception": repr(e)})
        for pp in pair_plans:
            for m in pp["a_modes"]:
                plan = [(pp["A"], m), (pp["B"], dflt[pp["B"]["key"]])]
                lab = f"pair_{ck.cam_slug(pp['A'])}_{m.slug}+{ck.cam_slug(pp['B'])}"
                for i in range(pair_reps):
                    ctx.log(f"{TEST}: {api} pair {m.text} + {pp['B'].get('name')} ({i + 1}/{pair_reps})")
                    try:
                        mt.run_set(api, plan, secs, 0.0, lab, "pair")
                    except Exception as e:  # noqa: BLE001
                        errors.append({"api": api, "kind": "pair", "label": lab, "exception": repr(e)})
    mt.poll_arrivals("end")
    runs = mt.runs
    verdicts, summary = rate_events(mt.events)
    meas = {"quick": ck.quick(ctx), "reps_simultaneous": k, "reps_staggered": stag, "reps_pairs": pair_reps,
            "seconds": secs, "descriptor_file": desc, "topology_snapshot": f"{TEST}/topology_snapshot.json",
            "domains": tm.compute_domains(snap), "camera_domains": {c["key"]: mt.domain_of.get(mt.skey.get(c["key"]))
                                                                   for c in ctx.cameras},
            "pairs": [{"domain": p["domain"], "A": p["A"]["key"], "B": p["B"]["key"],
                       "a_modes": [m.text for m in p["a_modes"]], "predicted": p.get("predicted"),
                       "fits_side": "testable" if p.get("fits_testable")
                       else "fits-side not testable under mode scope"} for p in pair_plans],
            "mode_scope": {"scope": ck.mode_scope(ctx).as_dict(), "cameras": scope_of},
            "pyav_formats": {c["key"]: {m.text: pyav_format(raw_modes.get(c["key"], set()), m.w, m.h, m.fps)
                                        for m in {mm for cc, mm in learn_plan if cc is c and mm.subtype == "MJPG"}}
                             for c in ctx.cameras},
            "native_raw_modes": {kk: sorted(map(list, v)) for kk, v in raw_modes.items()},
            "learned_costs": learned, "mode_alt_cache_file": str(root_cache), "mode_alt_cache": cache.entries,
            "prediction_all_default": pred_all, "runs": runs, "events": mt.events, "messages": mt.messages,
            "summary_by_api": summary, "retry_budget": {"per_key": RETRIES_PER_KEY, "used": mt.retry_used},
            "predicted_vs_observed": _pvo(runs), "non_bandwidth_failures": _non_bw(runs),
            "timeline": mt.timeline, "arrival_attribution": attribute_arrivals(mt.timeline, mt.failures),
            "re_enumerating_cameras": sorted(mt.reenum), "settle_waits": mt.settle_waits,
            "device_faults": mt.faults, "device_fault_log": mt.fault_log,
            "re_arrivals_by_run": _rearrivals_by_run(runs, attribute_arrivals(mt.timeline, mt.failures)),
            "arrivals": ck.arrivals_after(ctx, arr0)}
    for key, info in mt.faults.items():
        verdicts.setdefault(f"G-BW|{key}|all", rating.untested(f"device fault since {info.get('since_utc')}", info))
    if not pair_plans:
        meas["pairs_note"] = "no high-speed domain holds two cameras: no predicted-conflict pairs to test"
    elif not any(p.get("fits_testable") for p in pair_plans):
        meas["pairs_note"] = ("fits-side not testable under mode scope: no in-scope pair is predicted to fit in a "
                              "shared domain; the predicted-over pairs and the cross-domain all-at-once runs were run "
                              "(--all-modes restores the low-rate / small modes)")
    for key, sc in scope_of.items():
        if sc.get("untested_reason"):
            verdicts.setdefault(f"G-BW|{key}|all", ck.scope_untested(ctx, sc))
    return results.finish_result(res, measurements=meas, verdicts=verdicts, errors=errors)


def _pvo(runs: list[dict]) -> list[dict]:
    return [{"api": r["api"], "label": r["label"], "run": r.get("tag"), "camera": oc["camera"], "mode": oc["mode"],
             "predicted_format": oc.get("predicted_format"), "observed_format": oc.get("observed_format"),
             "predicted_cost_us": oc.get("predicted_cost_us"), "observed_cost_us": oc.get("observed_cost_us"),
             "predicted_domain_verdict": oc.get("predicted_domain_verdict"), "ok": oc["ok"],
             "class": (oc.get("classification") or {}).get("class")} for r in runs for oc in r["cameras"]]


def _non_bw(runs: list[dict]) -> list[dict]:
    return [dict(api=r["api"], label=r["label"], run=r.get("tag"), camera=oc["camera"],
                 cls=oc["classification"].get("class"), code=oc.get("code"))
            for r in runs for oc in r["cameras"]
            if not oc["ok"] and not oc.get("counts_as_refusal") and oc.get("classification")]


def _rearrivals_by_run(runs: list[dict], attribution: list[dict]) -> list[dict]:
    """Arrivals attributed by timestamp to the run whose failure caused them (not the run whose check saw them)."""
    by_run: dict[str, list] = {}
    for a in attribution:
        f = a.get("failure")
        if f:
            by_run.setdefault(f["run"], []).append({"camera": a["event"]["key"], "kind": a["event"]["kind"],
                                                    "utc": a["event"]["utc"], "after_failure_s": a["delay_s"],
                                                    "failure_where": f.get("where")})
    out = []
    for r in runs:
        if r.get("tag") in by_run:
            out.append({"api": r["api"], "label": r["label"], "run": r["tag"], "re_arrivals": by_run[r["tag"]]})
    return out


# ============================================================================================================ offline
def _spec_t0(run_dir: Path, tag: str) -> float | None:
    p = run_dir / TEST / f"spec_{tag}.json"
    try:
        return p.stat().st_mtime
    except OSError:
        return None


def _offline_timeline(m: dict, runs: list[dict], t0s: list[float | None]) -> list[dict]:
    """Arrival events from the stored per-run checks (absolute LastArrivalDate values; absences at the check time,
    approximated by the run's spec-file mtime + its last t_end_s)."""
    tl = []
    seen = set()
    for i, r in enumerate(runs):
        t_chk = (t0s[i] + max((oc.get("t_end_s") or 0) for oc in r["cameras"])) if t0s[i] else None
        for c in r.get("re_arrivals") or []:
            chg = c.get("changes") or {}
            if "last_arrival" in chg and chg["last_arrival"][1] and (c["key"], chg["last_arrival"][1]) not in seen:
                seen.add((c["key"], chg["last_arrival"][1]))
                tl.append({"key": c["key"], "kind": "arrival", "utc": chg["last_arrival"][1],
                           "t": parse_utc(chg["last_arrival"][1]), "seen_after": f"run#{i}"})
            if "present" in chg and chg["present"] == [True, False]:
                tl.append({"key": c["key"], "kind": "absent", "utc": utc_iso(t_chk), "t": t_chk,
                           "seen_after": f"run#{i}"})
    for c in (m.get("arrivals") or {}).get("changes") or []:
        chg = c.get("changes") or {}
        if "last_arrival" in chg and chg["last_arrival"][1] and (c["key"], chg["last_arrival"][1]) not in seen:
            seen.add((c["key"], chg["last_arrival"][1]))
            tl.append({"key": c["key"], "kind": "arrival", "utc": chg["last_arrival"][1],
                       "t": parse_utc(chg["last_arrival"][1]), "seen_after": "end"})
    return sorted(tl, key=lambda e: e.get("t") or 0)


def _offline_raw_modes(run_dir: Path, cams: list[dict], runs: list[dict]) -> tuple[dict, dict]:
    """Native raw modes per camera from the raw-dir format cache, else inferred from pyav_ds runs that streamed
    with a format fallback (that (camera, mode) is raw)."""
    out, src = {}, {}
    raw_dir = results.default_raw_dir(run_dir)
    for c in cams:
        f = raw_dir / "_cache" / f"formats_mf_{ck.cam_slug(c)}.json"
        if f.exists():
            try:
                out[c["key"]] = native_raw_modes(json.loads(f.read_text(encoding="utf-8")))
                src[c["key"]] = str(f)
                continue
            except ValueError:
                pass
        s = set()
        for r in runs:
            for oc in r["cameras"]:
                if r["api"] == "pyav_ds" and oc["camera"] == c["key"] and oc.get("format_fallback"):
                    p = tm.parse_mode(oc["mode"])
                    s.add(("YUY2", p["width"], p["height"], round(p["fps"], 2)))
        out[c["key"]] = s
        src[c["key"]] = "inferred from pyav_ds format_fallback observations"
    return out, src


def reanalyze(run_dir: str | Path, write: bool = True) -> dict:
    """Offline re-rating of a finished W-MULTI run with the fixed classification, events, prediction formats,
    attribution and messages. Retries cannot be re-run: the stored retries are re-attached (retry_ok = final
    try). Absolute run times come from the spec-file mtimes (written just before each launch, so delays measured
    from them are upper bounds by ~0.3-1 s). Writes reanalysis/W-MULTI.json and reanalysis/messages.md."""
    rd = Path(run_dir)
    orig = json.loads((rd / f"{TEST}.json").read_text(encoding="utf-8"))
    m = orig["measurements"]
    snap = json.loads((rd / TEST / "topology_snapshot.json").read_text(encoding="utf-8"))
    cams = json.loads((rd / "discovery.json").read_text(encoding="utf-8")).get("cameras", [])
    cam_by_key = {c["key"]: c for c in cams}
    cache = tm.ModeAltCache.load(rd / "mode_alt_cache.json")
    cache.merge(tm.ModeAltCache.load(rd / TEST / "mode_alt_cache.json"), overwrite=True)
    cache.path = None
    try:
        from w_topo import seed_cache  # noqa: PLC0415
        cache = seed_cache(None, save=False, base=cache)
    except Exception:  # noqa: BLE001
        pass
    runs_in = m["runs"]
    raw_modes, raw_src = _offline_raw_modes(rd, cams, runs_in)
    by_dev = {c["device_id"].upper(): c["key"] for c in snap.get("cameras", [])}
    skey = {c["key"]: by_dev.get(str(c.get("instance_id") or "").upper(), c["key"]) for c in cams}
    dev_dom = {}
    for d in tm.compute_domains(snap):
        for mm in d.get("members", []):
            dev_dom[mm] = d["key"]
    domain_of = {c["key"]: dev_dom.get(c["device_id"]) for c in snap.get("cameras", [])}
    tags = [f"{r['api']}_{r['label']}_{i + 1:03d}" for i, r in enumerate(runs_in)]
    t0s = [_spec_t0(rd, t) for t in tags]
    timeline = _offline_timeline(m, runs_in, t0s)
    old_events = {(e["run"], e["domain"]): e for api in APIS for e in (m.get("events") or {}).get(api, [])}
    events: dict[str, list] = {api: [] for api in APIS}
    messages: list = []
    runs_out, failures = [], []
    for i, r in enumerate(runs_in):
        api, tag, t0 = r["api"], tags[i], t0s[i]
        rec = {"api": api, "label": r["label"], "kind": r["kind"], "tag": tag, "stagger_s": r.get("stagger_s"),
               "seconds": r.get("seconds"), "utc_start": utc_iso(t0), "t0_source": "spec-file mtime (upper bound)",
               "cameras": []}
        ends = [oc.get("t_end_s") for oc in r["cameras"] if oc.get("t_end_s") is not None]
        rec["utc_end"] = utc_iso(t0 + max(ends)) if (t0 and ends) else None
        for oc0 in r["cameras"]:
            oc = {k: v for k, v in oc0.items() if k not in ("classification", "counts_as_refusal")}
            cam = cam_by_key.get(oc["camera"], {})
            p = tm.parse_mode(oc["mode"]) or {}
            pf = pyav_format(raw_modes.get(oc["camera"], set()), p.get("width"), p.get("height"),
                             p.get("fps") or 0) if api == "pyav_ds" else "MJPG"
            oc["predicted_format"] = pf
            oc["predicted_mode"] = mode_fmt_text(oc["mode"], pf)
            streamed = bool(oc.get("ok") or oc.get("frames"))
            oc["observed_format"] = (("YUY2" if oc.get("format_fallback") else "MJPG") if api == "pyav_ds"
                                     else "MJPG") if streamed else None
            if t0 and oc.get("t_start_s") is not None:
                oc["utc_start"] = utc_iso(t0 + oc["t_start_s"])
                oc["utc_end"] = utc_iso(t0 + oc["t_end_s"])
            oc["snapshot_key"] = oc.get("snapshot_key") or skey.get(oc["camera"])
            oc["domain"] = domain_of.get(oc["snapshot_key"])
            oc["_speed"] = cam.get("speed")
            rec["cameras"].append(oc)
        reqs = [{"camera_key": oc["snapshot_key"], "mode": oc["predicted_mode"]} for oc in rec["cameras"]]
        pred = tm.predict(snap, reqs, cache)
        dv = {d["key"]: d["verdict"] for d in pred.get("domains", [])}
        cost = {q.get("camera_key"): q.get("cost_us") for q in pred.get("requests", [])}
        for oc in rec["cameras"]:
            oc["predicted_domain_verdict"] = dv.get(oc["domain"])
            oc["predicted_cost_us"] = cost.get(oc["snapshot_key"])
            oc.pop("_speed", None)
        run_end = parse_utc(rec["utc_end"])
        for oc in rec["cameras"]:
            if oc["ok"]:
                continue
            others = [x for x in rec["cameras"] if x is not oc and x.get("domain") == oc.get("domain")
                      and (x["ok"] or x["frames"])]
            fe = parse_utc(oc.get("utc_end"))
            gone = device_gone(oc["camera"], fe, run_end, timeline)
            oc["device_gone"] = gone
            cl = classify_camera(api, oc, bool(others), oc["predicted_domain_verdict"], bool(gone))
            oc["classification"] = cl
            oc["counts_as_refusal"] = counts_as_refusal(cl.get("class"), bool(others))
            if fe is not None:
                failures.append({"run": tag, "api": api, "camera": oc["camera"], "where": "run",
                                 "class": cl.get("class"), "t_end": fe, "utc_end": oc.get("utc_end")})
        reqs_eff, mismatch = effective_requests(rec)
        pred_eff = tm.predict(snap, reqs_eff, cache) if mismatch else None
        rec["prediction"] = _pred_brief(pred)
        if pred_eff is not None:
            rec["prediction_observed_formats"] = _pred_brief(pred_eff)
        for ev in build_events(rec, pred, pred_eff):
            if ev["observed_refused"]:
                loser = next(oc for oc in rec["cameras"] if oc["camera"] == ev["losers"][0])
                failure = message_failure(rec, loser)
                ex = tm.explain(snap, reqs_eff, cache, failure=failure)
                msg = record_message(messages, rec, ex, ev["domain"], loser, failure)
                ev["message_ports_other_domains"] = msg.get("ports_other_domains")
                ev["labels_raw"] = msg.get("labels_raw")
                ev["message_index"] = msg.get("index")
                old = old_events.get((tag, ev["domain"])) or {}
                rt = old.get("retry")
                if rt and rt.get("tries") and old.get("losers") and old["losers"][0] == loser["camera"]:
                    tries = rt["tries"]
                    ev["retry_ok"], ev["retry_first_try_ok"] = tries[-1]["ok"], tries[0]["ok"]
                    ev["retry"] = {"ok": tries[-1]["ok"], "first_try_ok": tries[0]["ok"],
                                   "tries": [{k: t.get(k) for k in ("ok", "frames")} for t in tries],
                                   "note": "re-attached from the original run; retry_ok = the final try"}
            events[api].append(ev)
        runs_out.append(rec)
    verdicts, summary = rate_events(events)
    attribution = attribute_arrivals(timeline, failures)
    orig_ratings = {k: (v or {}).get("rating") for k, v in (orig.get("verdicts") or {}).items()}
    out = {"test": TEST, "kind": "offline_reanalysis", "utc": results.utc_now_iso(), "source_run": str(rd),
           "inputs": [f"{TEST}.json", f"{TEST}/topology_snapshot.json", "discovery.json",
                      "mode_alt_cache.json + W-MULTI/mode_alt_cache.json (read only) + W-TOPO seeds",
                      f"{TEST}/spec_<tag>.json mtimes (absolute run start, upper bound)"],
           "raw_modes_source": raw_src,
           "original_ratings": orig_ratings,
           "ratings": {k: v.get("rating") for k, v in verdicts.items()},
           "changes_applied": [
               "device_not_ready class (RenderStream in the FFmpeg log, open > 2 s, or the camera removed / "
               "re-arriving within ~1 s of the failure) is not a refusal",
               "counts_as_refusal keeps the others-streaming rule and excludes device_not_ready",
               "pyav_ds predicted with the format it negotiates (YUY2 where natively offered); observed-format "
               "mismatches re-predicted with the observed pipe",
               "run-root ModeAltCache (W-TOPO seeds incl. C922 YUY2 1080p@5) used for prediction and stay-here",
               "arrivals attributed by timestamp (spec-file mtime + t_end_s), not by the next run's check",
               "retry_ok = the final try (stored tries re-attached; retries cannot be re-run offline)",
               "labels via topology_model.label_tier (controller + port number is not raw)",
               "message wording: EIO is a DirectShow start error, timeouts are not called bandwidth errors, staggered "
               "starts say 'one after another, 2.5 s apart'; stay-here keeps format and fps; header-evidence ports "
               "last; 'user-accessible' only with evidence beyond _UPC"],
           "not_recoverable_offline": ["PyAV FFmpeg logs (empty in every pyav_ds failure)",
                                       "retries under the new budget / re-arrival wait policy",
                                       "exact absolute run start times (spec mtimes only)"],
           "summary_by_api": summary, "verdicts": verdicts,
           "measurements": {"runs": runs_out, "events": events, "messages": messages, "timeline": timeline,
                            "arrival_attribution": attribution,
                            "re_arrivals_by_run": _rearrivals_by_run(runs_out, attribution),
                            "predicted_vs_observed": _pvo(runs_out), "non_bandwidth_failures": _non_bw(runs_out)}}
    if write:
        results.write_json(rd / "reanalysis" / f"{TEST}.json", out)
        (rd / "reanalysis").mkdir(parents=True, exist_ok=True)
        (rd / "reanalysis" / "messages.md").write_text(messages_markdown(out), encoding="utf-8")
    return out


def messages_markdown(out: dict) -> str:
    """The regenerated user messages, verbatim, grouped by identical text."""
    msgs = out["measurements"]["messages"]
    groups: dict[str, list] = {}
    nulls = []
    for i, mm in enumerate(msgs):
        if mm.get("message") is None:
            nulls.append((i, mm))
            continue
        groups.setdefault(mm["message"], []).append((i, mm))
    lines = ["# W-MULTI user messages, regenerated offline", "",
             f"Source run: `{Path(out['source_run']).name}`. Regenerated {out['utc'][:19]}Z by "
             "`suite/windows/tests/w_multi.py --reanalyze` with the fixed topology_model "
             "(original files untouched).",
             f"{len(msgs)} message records: {len(msgs) - len(nulls)} messages in {len(groups)} distinct texts, "
             f"{len(nulls)} without a message (refusal not foreseen).", "",
             "Ratings (original -> re-analysis): " + ", ".join(
                 f"`{k}` {out['original_ratings'].get(k)} -> {v}" for k, v in out["ratings"].items()), ""]
    for n, (text, items) in enumerate(groups.items(), 1):
        runs = ", ".join(f"`{mm['run']}`" for _, mm in items)
        cls = sorted({(mm.get("failure") or {}).get("class") for _, mm in items})
        lines += [f"## Text {n} ({len(items)} records: {', '.join(c for c in cls if c)})", "",
                  f"Runs: {runs}", "", "```text", text, "```", ""]
    if nulls:
        lines += ["## Refusals with no message (no conflict predicted for the domain)", ""]
        for i, mm in nulls:
            lines.append(f"- record {i}: `{mm['run']}`, loser `{mm['loser']}`, class "
                         f"{(mm.get('failure') or {}).get('class')}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--reanalyze":
        r = reanalyze(sys.argv[2])
        print(json.dumps({"original": r["original_ratings"], "reanalysis": r["ratings"],
                          "summary": r["summary_by_api"]}, indent=1))
        sys.exit(0)
    print("usage: w_multi.py --reanalyze RUN_DIR   (the live test runs from run_suite.py)", file=sys.stderr)
    sys.exit(2)
