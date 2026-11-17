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
    assert [t[0] for t in run_suite.select_tests(a, False)] == list(run_suite.PLAN_TESTS)
    assert (a.cycles, a.proc_cycles, a.ctrl_runs, a.multi_repeats, a.multi_seconds) == (20, 0, 1, 1, 90.0)
    assert a.request_camera and a.full and not a.ep0
    a2 = run_suite.apply_defaults(run_suite.build_parser().parse_args(["--plan", "--cycles", "5"]))
    assert a2.cycles == 5  # an explicit flag wins


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


def test_jpeg_markers_and_bytes_stats():
    # SOI, APP0 'AVI1', DQT (67 bytes), SOS: no DHT, as UVC MJPEG usually sends
    dqt = b"\xff\xdb\x00\x43\x00" + bytes(range(64))
    b = b"\xff\xd8" + b"\xff\xe0\x00\x10AVI1\x00" + b"\x00" * 9 + dqt + b"\xff\xda\x00\x08" + b"\x00" * 6
    m = mac_avf.jpeg_markers(b)
    assert m["markers"] == ["E0", "DB", "DA"] and m["app0"] == "AVI1" and m["has_dht"] is False and m["dqt_sha1"]
    s = mac_avf.bytes_stats(list(range(1, 101)))
    assert (s["min"], s["median"], s["p99"], s["max"], s["n"]) == (1, 51, 100, 100, 100)
    assert mac_avf.bytes_stats([]) is None
