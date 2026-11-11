"""A fake process runner for SuiteCtx: answers ioreg, mac_avf.py and mac_ep0.py command lines with synthetic
results (writing frames.jsonl / cycles.jsonl like the real helpers), so the test modules run end to end off-Mac.

Scenario: the Apple-silicon fake tree; the generic camera refuses (zero frames) in the M-MULTI shared-domain
attempts at its default mode while the C922 streams; the Kiyo's ep0 requests time out after the first poll;
image metrics follow the scheduled control values (luma ~ exposure + gain, R/B ~ 1/WB temperature, sharpness
peaks at focus 120).

M-FMT-NOGRAB plumbing: ``formats``/``descriptors`` honour --hold-ms/--hold-marker/--release-file for real
(childutil.hold); a capture with --stop-file is a background stream on the real mach clock (ready file at once,
frames every 1/30 s until the stop file appears). Switches: ``disturb_on_hold`` (no streamer frames while a hold is
active), ``block_on_hold`` (a 1-frame capture started during a hold gets zero frames), ``vs_alt_on_hold`` (the
IORegistry VS alt reads this value while a hold is active)."""
from __future__ import annotations

import argparse
import json
import os
import plistlib
import threading
import time
from pathlib import Path

import childutil

import fake_mac
import mac_ep0
import uvc_ctrl

FPS = 30.0
GEN_LOC, KIYO_LOC = "0x01120000", "0x01240000"


class FakeRunner:
    def __init__(self, plists: dict | None = None, avf: dict | None = None):
        self.plists = plists or fake_mac.apple_silicon_plists()
        self.avf = avf or fake_mac.apple_silicon_avf()
        self.calls: list[list[str]] = []
        self.t_ns = 10_000_000_000
        self.kiyo_ep0_calls = 0
        self.transport = fake_mac.FakeUVCTransport()
        self.disturb_on_hold = False
        self.block_on_hold = False
        self.vs_alt_on_hold: int | None = None
        self.holds_active = 0
        self.hold_windows: list[tuple[int, int]] = []
        self._lock = threading.Lock()

    def __call__(self, argv, timeout_s, cwd=None, env=None):
        argv = [str(a) for a in argv]
        self.calls.append(argv)
        out = {"argv": argv, "rc": 0, "stdout": "", "stderr": "", "elapsed_s": 0.01, "timed_out": False,
               "killed": False, "pid": 1, "spawn_error": None, "kill_method": None}
        if argv[0].endswith("ioreg"):
            q = argv[argv.index("-c") + 1]
            key = {"AppleUSBHostController": "controllers", "AppleHPM": "hpm", "IOPCIDevice": "pci",
                   "IOUSBHostInterface": "interfaces", "IOUSBHostDevice": "controllers"}.get(q)
            data = self.plists.get(key, [])
            if q == "IOUSBHostInterface" and self.vs_alt_on_hold is not None and self.holds_active:
                data = _with_vs_alt(data, self.vs_alt_on_hold)
            out["stdout"] = plistlib.dumps(data).decode() if key else ""
            return out
        if len(argv) < 2 or not argv[1].endswith(".py"):
            out["stdout"] = {"sw_vers": "ProductName: macOS\nProductVersion: 27.2\nBuildVersion: 27C55",
                             "id": "staff admin everyone",
                             "ps": "  PID COMM\n    1 /sbin/launchd\n  400 "
                                   "/System/Library/Frameworks/CoreMediaIO.framework/UVCAssistant",
                             "sysctl": "Mac14,13", "uname": "Darwin 27.2.0 arm64"}.get(argv[0], "")
            return out
        script = Path(argv[1]).name
        try:
            res = (self.avf_cmd if script == "mac_avf.py" else self.ep0_cmd)(argv[2:])
        except _Timeout as t:
            out.update(timed_out=True, killed=True, rc=None, stdout=json.dumps(t.partial))
            return out
        out["stdout"] = "log line\n" + json.dumps(res)
        out["rc"] = res.get("exit_code", 0 if res.get("ok") else 4)
        return out

    # ------------------------------------------------------------------ mac_avf.py
    def avf_cmd(self, args: list[str]) -> dict:
        import mac_avf
        a = mac_avf.build_parser().parse_args(args)
        devs = self.avf["devices"]
        by_uid = {d["unique_id"]: d for d in devs}
        if a.cmd == "list":
            run = {"elapsed_ms": 4.0, "devices": devs}
            return {"ok": True, "runs": [dict(run, i=i) for i in range(a.repeat)], "devices": devs,
                    "legacy": {"elapsed_ms": 2.0, "devices": devs}, "authorization": "authorized"}
        if a.cmd == "formats":
            out = {"ok": True, "device": by_uid[a.device], "list_ms": 12.5, "session_created": False}
            if a.hold_ms:
                out["hold"] = self._hold(a)
            return out
        if a.cmd == "tcc":
            return {"ok": True, "video": "authorized", "audio": "notDetermined"}
        if a.cmd == "ctrl-avf":
            return {"ok": True, "flags": {"exposure_modes_supported": {"locked": True, "auto_expose": False,
                                                                       "continuous_auto_exposure": True, "custom": False},
                                          "wb_modes_supported": {"locked": True, "continuous_auto_white_balance": True},
                                          "focus_modes_supported": {"locked": False}}}
        if a.cmd == "fx":
            return {"ok": True, "class_properties": {"reactionEffectsEnabled": True},
                    "devices": [{"flags_idle": {"isCenterStageActive": False, "reactionEffectsInProgress": []},
                                 "flags_streaming": [{"t_s": 0.5, "isCenterStageActive": False}],
                                 "frames_while_sampling": 80, "format_support": []}]}
        if a.cmd == "capture":
            return self.capture(a, by_uid[a.device])
        if a.cmd == "cycle":
            return self.cycle(a, by_uid[a.device])
        raise ValueError(a.cmd)

    def _hold(self, a) -> dict:
        with self._lock:
            self.holds_active += 1
        t0 = childutil.mach_ns()
        try:
            return childutil.hold(a.hold_ms, a.hold_marker, a.release_file, a.hold_cap_ms or a.hold_ms + 20_000)
        finally:
            with self._lock:
                self.holds_active -= 1
                self.hold_windows.append((t0, childutil.mach_ns()))

    def background_capture(self, a, dev: dict) -> dict:
        """--stop-file: stream on the real clock until the stop file appears (bounded)."""
        Path(a.out_dir).mkdir(parents=True, exist_ok=True)
        t0 = childutil.mach_ns()
        childutil.touch(a.ready_file, {"mach_ns": t0, "first_frame": True})
        end = time.monotonic() + min(float(a.seconds or 60), 60.0)
        while time.monotonic() < end and not os.path.exists(a.stop_file):
            time.sleep(0.01)
        t1 = childutil.mach_ns()
        rows, i, t = [], 0, t0
        step = int(1e9 / FPS)
        while t <= t1:
            if not (self.disturb_on_hold and any(w0 <= t <= w1 for w0, w1 in self.hold_windows)):
                rows.append({"seq": i, "mach_ns": t, "host_ns": t, "pts_ns": t, "kind": "image", "subtype": "420v"})
                i += 1
            t += step
        with open(Path(a.out_dir) / "frames.jsonl", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        return {"ok": bool(rows), "frames": len(rows), "fps_measured": FPS, "stopped_by": "stop_file",
                "runtime_errors": [], "notifications": [], "exit_code": 0 if rows else 4}

    def capture(self, a, dev: dict) -> dict:
        if a.stop_file:
            return self.background_capture(a, dev)
        if a.frames and self.block_on_hold and self.holds_active:
            return {"ok": False, "frames": 0, "error": "fake: device busy during hold", "error_class": "zero_frames",
                    "stage_failed": "first_frame", "exit_code": 4, "runtime_errors": []}
        loc = dev["uid_parsed"]["location_hex"]
        fmt = dev["formats"][a.format_index if a.format_index is not None else 0]
        multi_default = "1500:probe:ioreg_alt" in (a.schedule or "") and a.first_frame_timeout_s == 4.0 \
            and loc == GEN_LOC and fmt["w"] >= 1280
        jpeg = fmt["subtype"] == "dmb1" and a.variant in ("nil", "empty", "dmb1")
        n = 0 if multi_default else int((a.seconds or 3) * FPS)
        if a.frames:
            n = a.frames
        t0 = self.t_ns
        self.t_ns += int(((a.seconds or 3) + 2) * 1e9)
        state = {"exposure_time_absolute": 156, "gain": 0, "white_balance_temperature": 4600, "focus_absolute": 60}
        events = []
        for e in __import__("childutil").parse_schedule(a.schedule):
            t = t0 + int(e["t_ms"] * 1e6)
            res = {"ok": True}
            if e["kind"] == "ep0":
                res = {"ok": True, "name": e["name"], "value": int(e["value"]), "readback": int(e["value"]),
                       "readback_matches": True, "rc_name": "kIOReturnSuccess"}
            elif e["kind"] == "avf":
                res = {"ok": True, "readback_matches": True}
            elif e["name"] == "ioreg_alt":
                res = {"ok": True, "interfaces": [{"number": 1, "subclass": 2, "alt": 9 if fmt["w"] >= 1280 else 4}]}
            events.append(dict(e, host_ns_before=t, host_ns_after=t + 2_000_000, result=res))
        rows = []
        for i in range(n):
            t = t0 + int(i * 1e9 / FPS)
            for e in events:
                if e["kind"] == "ep0" and e["host_ns_after"] <= t and e["name"] in state:
                    state[e["name"]] = int(e["value"])
            r = {"seq": i, "host_ns": t + 4_000_000 + (i % 3) * 300_000, "pts_ns": t, "pts_host_ns": t,
                 "dur_ns": int(1e9 / FPS), "cmio_seq": i + (1 if i > n // 2 else 0), "kind": "block" if jpeg else "image",
                 "subtype": "dmb1" if jpeg else "420v"}
            if jpeg:
                r.update(soi=True, eoi=True, sof0_w=fmt["w"], sof0_h=fmt["h"], header_sha1="ab" * 20, strict_ok=True,
                         lenient_ok=True, bytes=50000)
            if a.metrics_every and i % a.metrics_every == 0:
                r["metrics"] = {"luma": 20 + state["exposure_time_absolute"] * 0.2 + state["gain"] * 0.3,
                                "rb": 6000.0 / state["white_balance_temperature"],
                                "sharp": 1.0 + 2.0 / (1 + abs(state["focus_absolute"] - 120) / 20)}
            rows.append(r)
        if a.out_dir:
            Path(a.out_dir).mkdir(parents=True, exist_ok=True)
            with open(Path(a.out_dir) / "frames.jsonl", "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r) + "\n")
        jp = [r for r in rows if r.get("soi")]
        before = []
        readback = []
        for name, val in __import__("childutil").parse_kv_list(a.controls_before):
            before.append({"kind": "ep0", "name": name, "value": str(val), "result": {"ok": True}})
            readback.append({"kind": "ep0get", "name": name, "result": {"ok": True, "value": val if name != "exposure_time_absolute" else 250}})
        return {"ok": n > 0, "frames": n, "fps_measured": FPS if n else None, "first_frame_ms": 180.0 if n else None,
                "is_jpeg": bool(jp) and len(jp) == n if n else None, "sample_kinds": {"block": len(jp), "image": n - len(jp)},
                "sample_subtypes": {"dmb1" if jpeg else "420v": n},
                "jpeg": {"n_checked": len(jp), "strict_valid_fraction": 1.0 if jp else None,
                         "lenient_valid_fraction": 1.0 if jp else None, "sof_match_fraction": 1.0 if jp else None,
                         "header_sha1_set": ["ab" * 20] if jp else [], "n_header_sha1": 1 if jp else 0},
                "runtime_errors": [], "dropped_callbacks": 0, "schedule_events": events, "controls_before": before,
                "controls_readback_after_start": readback,
                "stream": {"active_format_matches": True, "video_settings_accepted": True,
                           "clocks": {"sync_api": "synchronizationClock", "sync_is_host_clock": True,
                                      "port_clock_is_host_clock": False, "port_rate_vs_host": 1.000012}},
                "exit_code": 0 if n else 4, "stage_failed": None if n else "first_frame"}

    def cycle(self, a, dev: dict) -> dict:
        rows = []
        is_kiyo = dev["uid_parsed"]["pid"] == "0e05"
        for i in range(a.cycles):
            ok = not (is_kiyo and i == 2 and a.cycles > 3)
            rows.append({"i": i, "ok": ok, "stage_failed": None if ok else "first_frame", "input_ms": 3.0,
                         "configure_ms": 20.0, "start_ms": 150.0, "first_frame_ms": 210.0 if ok else None,
                         "frames": a.frames + 1 if ok else 0, "close_ms": 40.0,
                         "code": None if ok else -11800})
        if a.out_dir:
            Path(a.out_dir).mkdir(parents=True, exist_ok=True)
            with open(Path(a.out_dir) / "cycles.jsonl", "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r) + "\n")
        return {"ok": all(r["ok"] for r in rows), "cycles": len(rows), "n_ok": sum(r["ok"] for r in rows),
                "rows": rows}

    # ------------------------------------------------------------------ mac_ep0.py
    def ep0_cmd(self, args: list[str]) -> dict:
        ap = argparse.ArgumentParser()
        ap.add_argument("cmd")
        for k in ("--location", "--vid", "--pid", "--backend", "--vc-if", "--vs-if", "--entities", "--controls",
                  "--set", "--deadline-s", "--timeout-ms", "--hold-marker", "--release-file"):
            ap.add_argument(k)
        ap.add_argument("--hold-ms", type=float, default=0.0)
        ap.add_argument("--hold-cap-ms", type=float, default=None)
        ap.add_argument("--all-selectors", action="store_true")
        ap.add_argument("--restore", action="store_true")
        a = ap.parse_args(args)
        if a.location == KIYO_LOC and a.cmd == "get":
            self.kiyo_ep0_calls += 1
            if self.kiyo_ep0_calls > 1:
                raise _Timeout({"ok": False, "timed_out": True, "in_progress": "get"})
        cfg = fake_mac.uvc_config(fake_mac.GENERIC_ALTS if a.location == GEN_LOC else fake_mac.C922_ALTS,
                                  [(640, 480, [30, 15]), (1280, 720, [30]), (1920, 1080, [30])])
        s = mac_ep0.summarize_config(cfg)
        if a.cmd == "descriptors":
            out = {"ok": True, "source": "GetConfigurationDescriptorPtr (cached, no request)", "config_hex": cfg.hex(), **s}
            if a.hold_ms:
                out["hold"] = self._hold(a)
            return out

        class Sess:
            entities = s["entities"]
            log: list = []

            def controls(inner):
                return uvc_ctrl.UVCControls(self.transport, s["entities"])

        if a.cmd == "ctrl-list":
            return {"ok": True, "setup": {"ok": True}, **mac_ep0.ctrl_list(Sess(), a.all_selectors)}
        c = Sess().controls()
        if a.cmd == "get":
            vals = [c.get_cur(n) for n in (a.controls or "").split(",") if n]
            return {"ok": all(v["ok"] for v in vals), "values": vals}
        if a.cmd == "set":
            sets = [c.set_cur(n, v) for n, v in __import__("childutil").parse_kv_list(a.set)]
            return {"ok": all(x["ok"] for x in sets), "sets": sets}
        return {"ok": True}


def _with_vs_alt(roots: list, alt: int) -> list:
    """A deep copy of an IOUSBHostInterface dump with every VideoStreaming interface at bAlternateSetting=alt."""
    import copy
    out = copy.deepcopy(roots)
    stack = list(out)
    while stack:
        n = stack.pop()
        if not isinstance(n, dict):
            continue
        if n.get("IOObjectClass") == "IOUSBHostInterface" and n.get("bInterfaceClass") == 14 \
                and n.get("bInterfaceSubClass") == 2:
            n["bAlternateSetting"] = alt
        stack.extend(n.get("IORegistryEntryChildren") or [])
    return out


class _Timeout(Exception):
    def __init__(self, partial):
        super().__init__("timeout")
        self.partial = partial
