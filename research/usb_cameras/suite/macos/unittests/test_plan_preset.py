"""--plan preset (2026-11-17): test selection and sizes, the whole run with the fake child runner (summary.md,
privacy), and the Kiyo Pro dead rule in SuiteCtx.avf."""
import json
import socket
import sys

import fake_children
import mac_avf
import run_suite
import suitectx

KIYO = "1532:0e05:port=bus01/2.4"


def test_plan_selection_and_sizes():
    a = run_suite.apply_defaults(run_suite.build_parser().parse_args(["--plan"]))
    tests = run_suite.select_tests(a, False)
    assert [t[0] for t in tests] == list(run_suite.PLAN_TESTS)
    assert (a.cycles, a.proc_cycles, a.ctrl_runs, a.multi_repeats, a.multi_seconds) == (20, 0, 1, 1, 90.0)
    # the plan tests run with endpoint 0 off; the endpoint-0 phase (CTRL-LIST, CTRL-EFFECT) follows them
    assert a.request_camera and a.full and not a.ep0 and a.plan_ep0
    assert [t[0] for t in run_suite.ep0_phase_tests(a, tests)] == ["M-CTRL-LIST", "M-CTRL-EFFECT"]
    a2 = run_suite.apply_defaults(run_suite.build_parser().parse_args(["--plan", "--cycles", "5", "--ep0"]))
    assert a2.cycles == 5  # an explicit flag wins
    assert not a2.ep0  # --ep0 never reaches the plan's gating tests
    a3 = run_suite.apply_defaults(run_suite.build_parser().parse_args(["--plan", "--no-ep0"]))
    assert not a3.plan_ep0 and run_suite.ep0_phase_tests(a3, tests) == []


def test_plan_refuses_other_ep0_backends(tmp_path):
    for be in ("libusb", "iokit-dev"):
        assert run_suite.main(["--plan", "--dry-run", "--ep0-backend", be, "--ep0-allow-seize",
                               "--out-dir", str(tmp_path / "x")]) == 2
    assert run_suite.main(["--plan", "--dry-run", "--no-ep0", "--ep0-backend", "libusb",
                           "--out-dir", str(tmp_path / "x")]) == 0  # no endpoint 0 at all: nothing to refuse


def test_plan_run_with_fake_runner(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("SKELLYCAM_RAW_ROOT", str(tmp_path / "rawroot"))
    out = tmp_path / "plan_out"
    rc = run_suite.main(["--plan", "--no-camlock", "--out-dir", str(out), "--multi-seconds", "2", "--ts-seconds", "3"],
                        runner=fake_children.FakeRunner())
    assert rc == 0
    names = {p.name for p in out.glob("*.json")}
    assert {"m_mjpeg.json", "m_cyc.json", "m_multi.json", "m_ts.json"} <= names
    assert "m_fmt_nograb.json" not in names and "m_kiyo.json" not in names and "m_fx.json" not in names
    multi = json.loads((out / "m_multi.json").read_text(encoding="utf-8"))["measurements"]
    assert [x["label"] for x in multi["attempts"]] == ["all_together_0"]
    cyc = json.loads((out / "m_cyc.json").read_text(encoding="utf-8"))["measurements"]["cameras"]
    assert all([v["variant"] for v in c["variants"]] == ["in_process"] for c in cyc)
    md = (out / "summary.md").read_text(encoding="utf-8")
    assert "(Kiyo Pro)" in md and "- MJPEG MJPG 1280x720@30: JPEG bytes from AVFoundation: YES" in md
    assert "cycles in_process: 19/20 ok" in md  # the fake Kiyo Pro fails one cycle
    assert "serial 8 chars" in md and "C922SN01" not in md  # serial form only in the summary
    assert "timestamps: clock" in md and "multi (all at once)" in md
    host = socket.gethostname()
    if len(host) >= 3:
        assert host not in md


class WedgingRunner(fake_children.FakeRunner):
    """The Kiyo Pro's stream starts all deliver zero frames."""

    def capture(self, a, dev):
        if dev["uid_parsed"]["pid"] == "0e05":
            return {"ok": False, "frames": 0, "stage_failed": "first_frame", "error_class": "zero_frames",
                    "runtime_errors": [], "exit_code": 4}
        return super().capture(a, dev)


def _ctx(tmp_path, runner):
    a = run_suite.apply_defaults(run_suite.build_parser().parse_args(["--plan"]))
    ctx = suitectx.SuiteCtx(out_dir=tmp_path / "o", raw_dir=tmp_path / "r", args=a, cache_dir=None, runner=runner,
                            log_fn=lambda m: None)
    run_suite.discover(ctx)
    ctx.current_test = "M-MJPEG"
    return ctx


def test_kiyo_pro_dead_rule(tmp_path):
    runner = WedgingRunner()
    ctx = _ctx(tmp_path, runner)
    kiyo = next(c for c in ctx.cameras if c["key"] == KIYO)
    cap = ["capture", "--device", kiyo["unique_id"], "--seconds", 1, "--format-index", 0]
    ctx.avf(cap, 30, label="multi all_together_0 x")  # concurrent M-MULTI launch: never counts
    assert KIYO not in ctx.suspect
    ctx.avf(cap, 30, label="first")
    assert KIYO in ctx.suspect and KIYO not in ctx.dead
    ctx.avf(cap, 30, label="second")  # stays failed -> dead, with diagnostics
    assert ctx.dead[KIYO]["since_test"] == "M-MJPEG" and ctx.dead[KIYO]["stream_starts_this_run"] == 3
    n = len(runner.calls)
    r = ctx.avf(["ctrl-avf", "--device", kiyo["unique_id"]], 30)
    assert r["skipped"].startswith("skipped: Kiyo Pro dead since M-MJPEG") and len(runner.calls) == n  # not run
    assert KIYO not in [c["key"] for c in ctx.openable()]
    assert ctx.new_result("M-X")["suite"]["dead"][KIYO].startswith("Kiyo Pro dead")


def test_kiyo_pro_success_clears_suspicion(tmp_path):
    ctx = _ctx(tmp_path, fake_children.FakeRunner())
    kiyo = next(c for c in ctx.cameras if c["key"] == KIYO)
    ctx.suspect[KIYO] = {"test": "M-MJPEG"}
    ctx.avf(["capture", "--device", kiyo["unique_id"], "--seconds", 1, "--format-index", 0], 30, label="ok")
    assert KIYO not in ctx.suspect and not ctx.dead


# ------------------------------------------------------------------------------------------------ endpoint-0 phase
PHASE1_FILES = [t.lower().replace("-", "_") + ".json" for t in run_suite.PLAN_TESTS]


def is_ep0_call(argv: list[str]) -> bool:
    """Any child that sends (or could send) an endpoint-0 request: mac_ep0.py, or a capture with ep0 actions."""
    s = " ".join(argv)
    return "mac_ep0.py" in s or "--ep0-location" in argv or ":ep0" in s or "--controls-before" in argv


class RecordingRunner(fake_children.FakeRunner):
    """Records, at the first endpoint-0 child, which result files and which summary were already on disk."""

    def __init__(self, out, *args, **kw):
        super().__init__(*args, **kw)
        self.out, self.first_ep0, self.ep0_calls = out, None, []

    def __call__(self, argv, timeout_s, cwd=None, env=None):
        argv = [str(x) for x in argv]
        if is_ep0_call(argv):
            self.ep0_calls.append(argv)
            if self.first_ep0 is None:
                sm = self.out / "summary.md"
                self.first_ep0 = {"files": {p.name for p in self.out.glob("*.json")},
                                  "summary": sm.read_text(encoding="utf-8") if sm.exists() else None}
        return super().__call__(argv, timeout_s, cwd, env)


def _plan(tmp_path, monkeypatch, runner, *extra, out_name="plan_out"):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("SKELLYCAM_RAW_ROOT", str(tmp_path / "rawroot"))
    out = tmp_path / out_name
    if isinstance(runner, type):
        runner = runner(out)
    rc = run_suite.main(["--plan", "--no-camlock", "--out-dir", str(out), "--multi-seconds", "2", "--ts-seconds", "3",
                         *extra], runner=runner)
    return rc, out, runner


def test_ep0_phase_runs_after_every_phase1_file(tmp_path, monkeypatch):
    rc, out, r = _plan(tmp_path, monkeypatch, RecordingRunner)
    assert rc == 0 and r.first_ep0 is not None
    assert set(PHASE1_FILES) <= r.first_ep0["files"]  # (a) no ep0 child before the last phase-1 file exists
    assert not {"m_ctrl_list_ep0.json", "m_ctrl_effect_ep0.json"} & r.first_ep0["files"]
    assert "NOT FINISHED (phase-1 summary)" in r.first_ep0["summary"]  # a usable summary was already written
    for argv in r.ep0_calls:  # iokit-intf only: never libusb, never the seize flag
        assert "libusb" not in argv and "--allow-seize" not in argv and "--ep0-allow-seize" not in argv
    assert not [a for a in r.ep0_calls if "mac_ep0.py" in " ".join(a) and "--all-selectors" in a]  # bounded
    for p1 in PHASE1_FILES:  # phase-1 results say ep0 was off
        assert json.loads((out / p1).read_text(encoding="utf-8"))["suite"]["ep0"] is False
    eff = json.loads((out / "m_ctrl_effect_ep0.json").read_text(encoding="utf-8"))
    assert eff["suite"]["ep0"] is True
    c922 = next(c for c in eff["measurements"]["cameras"] if c["key"].startswith("046d:085c"))
    assert c922["ep0_runs"][0]["groups"]["exposure"]["effect"]["effect_ok"] is True and c922["restore"]["ok"]
    assert not c922["avf_runs"]  # the AVFoundation part is not repeated in the ep0 phase
    # restore: auto modes to manual first, then the values, then the auto modes as found
    assert c922["restore"]["set"][0] == "auto_exposure_mode=1" and c922["restore"]["set"][-1].startswith(
        "white_balance_temperature_auto=")
    md = (out / "summary.md").read_text(encoding="utf-8")
    assert md.count("### Manual controls via endpoint 0 (IOKit, no seize)") == 4
    assert "endpoint-0 phase (iokit-intf, nothing opened/seized/claimed/detached): done" in md
    assert "- exposure_time_absolute: advertised yes" in md and "effect on image (brightness) yes" in md
    assert "focus_absolute: not advertised by the descriptor" in md
    assert "none in AVFoundation on macOS" in md  # the AVFoundation line stays


def _frozen_clocks(monkeypatch):
    import time
    import mac_ioreg
    from common import results
    monkeypatch.setattr(results, "utc_now_iso", lambda: "2026-11-17T00:00:00+00:00")
    monkeypatch.setattr(mac_ioreg, "_utc", lambda: "2026-11-17T00:00:00+00:00")
    monkeypatch.setattr(time, "monotonic", lambda: 1000.0)
    monkeypatch.setattr(time, "time", lambda: 1.8e9)


def test_phase1_files_identical_with_and_without_ep0_phase(tmp_path, monkeypatch):
    import shutil
    _frozen_clocks(monkeypatch)
    rc, out, _ = _plan(tmp_path, monkeypatch, fake_children.FakeRunner())
    assert rc == 0 and (out / "m_ctrl_effect_ep0.json").exists()
    with_ep0 = tmp_path / "with_ep0"
    out.rename(with_ep0)
    shutil.rmtree(tmp_path / "rawroot")  # the ep0 phase cached descriptors; the second run starts as fresh
    rc, out, _ = _plan(tmp_path, monkeypatch, fake_children.FakeRunner(), "--no-ep0")
    assert rc == 0 and not (out / "m_ctrl_effect_ep0.json").exists()
    for name in PHASE1_FILES + ["discovery.json", "topology_snapshot.json"]:  # (b)
        assert (with_ep0 / name).read_bytes() == (out / name).read_bytes(), name


class HangingEp0Runner(RecordingRunner):
    """Every endpoint-0 child hangs (killed at its timeout) or crashes the runner call."""
    crash = False

    def __call__(self, argv, timeout_s, cwd=None, env=None):
        argv = [str(x) for x in argv]
        if is_ep0_call(argv):
            if self.crash:
                raise RuntimeError("fake: runner failure in an endpoint-0 child")
            return {"argv": argv, "rc": None, "stdout": '{"ok": false, "timed_out": true}', "stderr": "",
                    "elapsed_s": timeout_s, "timed_out": True, "killed": True, "pid": 1, "spawn_error": None}
        return super().__call__(argv, timeout_s, cwd, env)


class CrashingEp0Runner(HangingEp0Runner):
    crash = True


def test_hanging_or_crashing_ep0_children_keep_summary_and_exit_0(tmp_path, monkeypatch):
    for i, cls in enumerate((HangingEp0Runner, CrashingEp0Runner)):  # (c)
        rc, out, _ = _plan(tmp_path, monkeypatch, cls, out_name=f"o{i}")
        assert rc == 0
        for p1 in PHASE1_FILES:
            assert (out / p1).exists()
        md = (out / "summary.md").read_text(encoding="utf-8")
        assert "### Manual controls via endpoint 0 (IOKit, no seize)" in md and "| M-TS |" in md
        assert "endpoint-0 phase (iokit-intf, nothing opened/seized/claimed/detached): done" in md
        if cls is HangingEp0Runner:
            assert md.count("- every control NOT TESTED: the control listing returned nothing (child timed out)") == 4
        else:
            assert md.count("NOT TESTED: no endpoint-0 listing for this camera") == 4
            assert "RuntimeError" in (out / "m_ctrl_list_ep0.json").read_text(encoding="utf-8")


def test_kiyo_pro_dead_in_phase1_gets_no_ep0_call(tmp_path, monkeypatch):
    class R(RecordingRunner, WedgingRunner):
        pass
    rc, out, r = _plan(tmp_path, monkeypatch, R)
    assert rc == 0 and KIYO in json.loads((out / "kiyo_pro_dead.json").read_text(encoding="utf-8"))
    assert r.ep0_calls  # the other cameras got their ep0 phase
    assert not [a for a in r.ep0_calls if fake_children.KIYO_LOC in a]  # (d) nothing sent to the dead Kiyo Pro
    md = (out / "summary.md").read_text(encoding="utf-8")
    assert "NOT TESTED: Kiyo Pro dead since M-" in md


def test_kiyo_pro_hanging_in_ep0_phase_is_marked_dead_once(tmp_path, monkeypatch):
    class R(RecordingRunner):
        def __call__(self, argv, timeout_s, cwd=None, env=None):
            argv = [str(x) for x in argv]
            if is_ep0_call(argv) and fake_children.KIYO_LOC in argv:
                self.ep0_calls.append(argv)
                return {"argv": argv, "rc": None, "stdout": "", "stderr": "", "elapsed_s": timeout_s,
                        "timed_out": True, "killed": True, "pid": 1, "spawn_error": None}
            return super().__call__(argv, timeout_s, cwd, env)
    rc, out, r = _plan(tmp_path, monkeypatch, R)
    dead = json.loads((out / "kiyo_pro_dead.json").read_text(encoding="utf-8"))
    assert rc == 0 and dead[KIYO]["since_test"].endswith("(ep0)")
    assert len([a for a in r.ep0_calls if fake_children.KIYO_LOC in a]) == 2  # descriptors, ctrl-list; then nothing
    assert [a for a in r.ep0_calls if fake_children.KIYO_LOC not in a]  # the other cameras continue


def test_no_ep0_restores_the_old_plan_run(tmp_path, monkeypatch):
    rc, out, r = _plan(tmp_path, monkeypatch, RecordingRunner, "--no-ep0")
    assert rc == 0 and r.ep0_calls == []  # (e) not one endpoint-0 child
    assert {p.name for p in out.glob("*.json")} >= set(PHASE1_FILES)
    assert not list(out.glob("*_ep0.json"))
    md = (out / "summary.md").read_text(encoding="utf-8")
    assert "endpoint-0 phase (iokit-intf, nothing opened/seized/claimed/detached): not run (--no-ep0)" in md
    assert "NOT TESTED: --no-ep0" in md


def test_dry_run_lists_the_ep0_phase(tmp_path, capsys):
    import fake_mac
    d = fake_mac.write_fake_dir(tmp_path / "ioreg", fake_mac.apple_silicon_plists())
    avf = fake_mac.write_fake_avf(tmp_path / "avf.json")
    base = ["--plan", "--dry-run", "--fake-ioreg", str(d), "--fake-avf", str(avf), "--out-dir", str(tmp_path / "x")]
    assert run_suite.main(base) == 0
    txt = capsys.readouterr().out
    assert "== endpoint-0 phase ~4.5 min: starts only after every result file above" in txt  # (f) 4 cameras
    assert "M-CTRL-EFFECT:" in txt and "ep0 schedule capture" in txt and "advertised selectors only" in txt
    assert "--no-ep0 skips it" in txt and "estimated total" in txt
    assert not (tmp_path / "x").exists()
    assert run_suite.main(base + ["--no-ep0"]) == 0
    txt = capsys.readouterr().out
    assert "== endpoint-0 phase" not in txt and "(--no-ep0)" in txt


def test_jpeg_markers_and_bytes_stats():
    # SOI, APP0 'AVI1', DQT (67 bytes), SOS: no DHT, as UVC MJPEG usually sends
    dqt = b"\xff\xdb\x00\x43\x00" + bytes(range(64))
    b = b"\xff\xd8" + b"\xff\xe0\x00\x10AVI1\x00" + b"\x00" * 9 + dqt + b"\xff\xda\x00\x08" + b"\x00" * 6
    m = mac_avf.jpeg_markers(b)
    assert m["markers"] == ["E0", "DB", "DA"] and m["app0"] == "AVI1" and m["has_dht"] is False and m["dqt_sha1"]
    s = mac_avf.bytes_stats(list(range(1, 101)))
    assert (s["min"], s["median"], s["p99"], s["max"], s["n"]) == (1, 51, 100, 100, 100)
    assert mac_avf.bytes_stats([]) is None
