# /// script
# requires-python = ">=3.10"
# ///
"""One W-PYAV-LIST session: optionally one camera streaming in another process, then each listing method in turn,
with USB pipe samples of EVERY camera while each method runs.

    python pyav_list_session.py SPEC.json        # prints one JSON object (the raw timeline; analysis is in the test)

The runner wraps the whole session in ONE camera lock (``ctx.camcmd([python, pyav_list_session.py, spec])``): the
streaming process and the listing must overlap. Every child is a ``common.procutil.Background`` (whole-tree kill)
with its own timeout; the streamer is nograb_session.Streamer (``--stop-file`` stop, first-frame wait).

SPEC: label, condition ("idle" | "streaming"), cameras [{key, name, instance_id}], stream_key (null | key),
out_dir, streamer (null | {argv with {out_dir} / {stop_file}, first_frame_timeout_s, stop_timeout_s}), baseline_s,
settle_s, descriptor_file, methods [{id, camera_key, argv, timeout_s}], sample {interval_s}.

Pipe samples use helpers/win_topology.collect() (cached hub-driver state; no request to any device): per camera
the open isochronous pipes and the matched alt setting. Times are time.perf_counter_ns (QPC on Windows), the clock
of wincam's ``qpc_ns`` and of pyav_list's per-call stamps. Stdlib only.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUITE_DIR = HERE.parents[1]
for _p in (str(SUITE_DIR), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from common import procutil, results  # noqa: E402
from nograb_session import Streamer, _clear, _resolve  # noqa: E402


class AllTopo:
    """win_topology sampler for every camera of the spec (keys, with the USB instance id as fallback)."""

    def __init__(self, desc_file: str | None, cameras: list[dict]) -> None:
        self.desc_file, self.cameras, self.error = desc_file, cameras, None
        try:
            import win_topology as wt  # noqa: PLC0415
            self.wt = wt
        except Exception as e:  # noqa: BLE001
            self.wt, self.error = None, f"win_topology import failed: {e!r}"

    def sample(self, tag: str = "") -> dict:
        t = time.perf_counter_ns()
        rec: dict = {"t_ns": t, "tag": tag, "cameras": {}}
        if self.wt is None:
            rec["error"] = self.error
            return rec
        try:
            obs = self.wt.observed_alts(self.wt.collect(descriptor_file=self.desc_file))
            by_dev = {str(v.get("device_id") or "").upper(): v for v in obs.values()}
            for c in self.cameras:
                o = obs.get(c["key"]) or by_dev.get(str(c.get("instance_id") or "").upper())
                if o is None:
                    rec["cameras"][c["key"]] = {"error": "not in the topology snapshot"}
                    continue
                pipes = o.get("iso_pipes") or []
                rec["cameras"][c["key"]] = {"active": bool(pipes), "current_alt": o.get("current_alt"),
                                            "iso_pipes": pipes}
        except Exception as e:  # noqa: BLE001
            rec["error"] = repr(e)
        rec["t_end_ns"] = time.perf_counter_ns()
        return rec


class Sampler(threading.Thread):
    def __init__(self, topo: AllTopo, interval_s: float) -> None:
        super().__init__(daemon=True)
        self.topo, self.interval_s = topo, interval_s
        self.samples: list[dict] = []
        self.stop_ev = threading.Event()

    def run(self) -> None:
        while not self.stop_ev.is_set():
            self.samples.append(self.topo.sample())
            self.stop_ev.wait(self.interval_s)


def run_method(m: dict, out_dir: Path, topo: AllTopo, interval_s: float) -> dict:
    so = out_dir / f"{m['id']}_{m.get('camera_slug') or 'all'}.out"
    se = out_dir / f"{m['id']}_{m.get('camera_slug') or 'all'}.err"
    _clear(so, se)
    smp = Sampler(topo, interval_s)
    smp.start()
    bg = procutil.Background(_resolve(m["argv"]), stdout_path=so, stderr_path=se).start()
    r = bg.stop(float(m.get("timeout_s") or 60))
    smp.stop_ev.set()
    smp.join(5)
    return {"id": m["id"], "camera_key": m.get("camera_key"), "argv": [str(a) for a in m["argv"]], "process": r,
            "stdout_file": str(so), "stderr_file": str(se), "topology_samples": smp.samples}


def main(spec_path: str) -> int:
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    out_dir = Path(spec["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    topo = AllTopo(spec.get("descriptor_file"), spec.get("cameras") or [])
    iv = float((spec.get("sample") or {}).get("interval_s") or 0.15)
    doc: dict = {"tool": "pyav_list_session", "label": spec.get("label"), "condition": spec.get("condition"),
                 "stream_key": spec.get("stream_key"), "utc_started": results.utc_now_iso(),
                 "t0_ns": time.perf_counter_ns(), "methods": [], "streamer_runs": [], "baseline_topology": [],
                 "events": []}
    st = Streamer(spec["streamer"], out_dir) if spec.get("streamer") else None
    try:
        if st is not None:
            rec = st.start()
            doc["events"].append({"t_ns": time.perf_counter_ns(), "event": "streamer_start", "ok": rec["started_ok"]})
            if not rec["started_ok"]:
                doc["streamer_failed"] = True
                return 0
            time.sleep(float(spec.get("baseline_s") or 2.0))
        for k in range(2):
            doc["baseline_topology"].append(topo.sample(f"baseline_{k}"))
            time.sleep(0.1)
        for m in spec.get("methods") or []:
            if st is not None and not st.alive():
                doc["methods"].append({"id": m["id"], "camera_key": m.get("camera_key"),
                                       "skipped": "the streaming process had stopped"})
                continue
            fb = st.frames() if st else None
            rec = run_method(m, out_dir, topo, iv)
            rec["streamer_frames_before"] = fb
            time.sleep(float(spec.get("settle_s") or 1.0))
            rec["t_settle_end_ns"] = time.perf_counter_ns()
            rec["streamer_alive_after"] = st.alive() if st else None
            rec["streamer_frames_after"] = st.frames() if st else None
            doc["methods"].append(rec)
    finally:
        if st is not None:
            if st.bg is not None:
                st.stop()
            doc["streamer_runs"] = st.runs
        doc["utc_finished"] = results.utc_now_iso()
        doc["t_end_ns"] = time.perf_counter_ns()
        sys.stdout.write(json.dumps(doc, default=str) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: pyav_list_session.py SPEC.json", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1:][0]))
