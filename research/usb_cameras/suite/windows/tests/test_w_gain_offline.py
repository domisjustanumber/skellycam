"""W-GAIN offline tests (no camera): rho / D / masks on synthetic frames with known noise, the reference caps and the
monotonic check, the 5.2a rule (g_lim, no gain needed, gain ineffective, motion guard, exposure first) against a
synthetic camera, T4 analysis, the grid row analysis on a synthetic capture folder, and a whole quick run against a
fake ctx whose camcmd emulates wincam, in which the Kiyo Pro dies mid-test and must get no further command.

    uv run --isolated --python 3.12 --no-project --with pytest --with numpy --with simplejpeg pytest \
        suite/windows/tests/test_w_gain_offline.py -c suite/common/tests/pytest.ini
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import simplejpeg

HERE = Path(__file__).resolve().parent
WIN = HERE.parent
for p in (str(WIN.parent), str(WIN), str(WIN / "helpers"), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import capkit as ck  # noqa: E402
import suitectx  # noqa: E402
import w_gain as wg  # noqa: E402

H, W = 96, 160


# ================================================================================================== synthetic scene
def reflectance(h=H, w=W):
    """Left half flat (1.0); right half vertical stripes 0.4 / 1.0 with a 4 px period."""
    r = np.ones((h, w), np.float32)
    cols = np.arange(w)
    stripes = np.where((cols // 2) % 2 == 0, 0.4, 1.0).astype(np.float32)
    r[:, w // 2:] = stripes[w // 2:]
    return r


REFL = reflectance()


def frames(L, rho, n, seed=0, blur=False, rowband=0.0, motion_from=None):
    """n frames of the scene at flat luma L with temporal noise sigma = rho * mu (per pixel), uint8.
    ``blur``: 3-tap horizontal smear of the texture (detail loss); ``rowband``: per-frame per-row offsets (sigma, grey
    levels: flicker); ``motion_from``: a bright square that moves 6 px per frame across the flat area."""
    rng = np.random.default_rng(seed)
    base = REFL * L
    if blur:
        base = (np.roll(base, 1, axis=1) + base + np.roll(base, -1, axis=1)) / 3.0
    out = []
    for i in range(n):
        f = base + rng.normal(0.0, 1.0, base.shape).astype(np.float32) * (rho * base)
        if rowband:
            f = f + rng.normal(0.0, rowband, (base.shape[0], 1)).astype(np.float32)
        if motion_from is not None:
            x = 12 + (i * 6) % 40
            f[30:70, x:x + 30] += 120.0
        out.append(np.clip(np.round(f), 0, 255).astype(np.uint8))
    return out


# ================================================================================================== image analysis
def test_rho_sigma_known_noise():
    st = wg.stack_stats(frames(100.0, 0.03, 64, seed=1))
    assert st["mask_px"] >= wg.MIN_MASK_PX
    assert st["rho"] == pytest.approx(0.03, rel=0.05)
    assert st["sigma_flat"] == pytest.approx(3.0, rel=0.06)
    assert st["sigma_two_frame"] == pytest.approx(3.0, rel=0.08)
    assert st["mu_mask"] == pytest.approx(100.0, abs=0.5)
    assert st["flicker_variance_share"] < 0.1               # no row banding
    # ideal analog gain: signal and noise scale together, rho stays
    st2 = wg.stack_stats(frames(180.0, 0.03, 64, seed=2), st["_masks"])
    assert st2["rho"] == pytest.approx(st["rho"], rel=0.05)
    assert st2["own_masks"] is False and st2["mask_px"] == st["mask_px"]


def test_row_mean_flicker_part():
    st = wg.stack_stats(frames(100.0, 0.02, 64, seed=3, rowband=4.0))
    assert st["rowmean_sigma"] > 3.0
    assert st["flicker_variance_share"] > 0.5
    assert st["sigma_flat_row_removed"] < st["sigma_flat"] * 0.7


def test_detail_scale_invariant_and_blur():
    a = wg.stack_stats(frames(60.0, 0.0, 8))
    b = wg.stack_stats(frames(120.0, 0.0, 8), a["_masks"])
    assert b["D"] == pytest.approx(a["D"], rel=0.02)         # gain that only scales: D unchanged
    c = wg.stack_stats(frames(60.0, 0.0, 8, blur=True), a["_masks"])
    assert c["D"] / a["D"] < wg.D_MIN_RATIO                   # noise-reduction smear: detail drops


def test_dark_scene_has_no_flat_mask():
    st = wg.stack_stats(frames(12.0, 0.05, 16))
    assert st["mask_px"] < wg.MIN_MASK_PX and st["rho"] is None and "mask_note" in st


def test_motion_fraction():
    still = wg.stack_stats(frames(100.0, 0.02, 8))
    moving = wg.stack_stats(frames(100.0, 0.02, 8, motion_from=0), still["_masks"])
    assert still["motion_frac_max"] < 0.01 and moving["motion_frac_max"] > wg.MOTION_FRAC


def test_jpeg_decode_strict_and_lenient():
    f = frames(100.0, 0.02, 1)[0]
    b = simplejpeg.encode_jpeg(f[..., None], quality=90, colorspace="GRAY")
    y, ok, err = wg.decode_y(b)
    assert ok is True and y.shape == f.shape and abs(float(y.mean()) - float(f.mean())) < 1.0
    y2, ok2, err2 = wg.decode_y(b[: len(b) // 2])             # truncated: strict fails, lenient may still decode
    assert ok2 is False and err2


# ================================================================================================== planning helpers
def test_grid_values_and_ceilings():
    g = {"min": 0, "max": 255, "step": 1}
    assert wg.grid_gains(g, False) == [0, 26, 64, 128, 191, 230, 255]
    assert wg.grid_gains(g, True) == [0, 128, 255]
    gen = {"min": 1, "max": 7, "step": 1}
    assert wg.grid_gains(gen, False) == [1, 2, 3, 4, 5, 6, 7]           # generic: every value
    e = {"min": -11, "max": -2, "step": 1}
    assert wg.grid_exposures(e, False) == [-11, -10, -9, -8, -7, -6, -5]
    assert wg.reduced_exposures(wg.grid_exposures(e, False), e) == [-11, -9, -7, -5]
    ge = {"min": -7, "max": 3, "step": 1}
    assert not wg.log2_units(ge) and wg.grid_exposures(ge, False) == [-7, -6, -5, -4, -3, -2, -1]
    assert wg.expected_ceiling(30.0) == -5 and wg.expected_ceiling(60.0) == -6
    assert wg.t4_exposures(e, 30.0, False) == list(range(-11, -1))
    assert wg.t4_exposures(e, 30.0, True) == [-6, -5, -4]
    assert wg.t4_exposures(ge, 30.0, False) == list(range(-7, 4))


def test_row_plan_first_set_after_one_second():
    mode = ck.Mode(1280, 720, 30, 1)
    p = wg.row_plan(mode, -7, [0, 128, 255], {"white_balance": 4000, "focus": 30}, 64,
                    {"min": -11, "max": -2, "step": 1})
    items = p["schedule"].split(";")
    assert items[:2] == ["600:white_balance=4000", "600:focus=30"]
    assert items[2:4] == ["1200:exposure=-7", "1200:gain=0"]
    assert p["cells"][0]["set_ms"] >= 1000                         # C930e: >= 1 s after the first frame
    assert items[-2:] == [f"{p['end_ms']}:exposure=manual", f"{p['end_ms']}:gain=manual"]
    assert p["slot_ms"] >= (wg.SETTLE_S + 64 / 30.0) * 1000
    assert "exposure=-7" in p["controls_before"] and "gain=0" in p["controls_before"]


# ================================================================================================== caps
def _cell(e, g, mu, rho, D, valid=True, clip=0.0):
    return {"exposure": e, "gain": g, "valid": valid,
            "metrics": {"rho": rho, "D": D, "mu_mask": mu, "mask_clip_frac": clip, "roi_luma_median": mu}}


def _grid(rho_mult, d_mult=lambda g: 1.0, gains=(0, 26, 64, 128, 191, 230, 255), resp=lambda g: 1 + g / 255):
    cells = []
    for e, base in ((-9, 12.0), (-7, 40.0), (-5, 150.0)):
        for g in gains:
            cells.append(_cell(e, g, base * resp(g), 0.02 * rho_mult(g), 0.5 * d_mult(g)))
    return cells


def test_same_exposure_cap_and_bracket():
    cells = _grid(lambda g: 1.0 if g <= 128 else 1.8)
    caps = wg.same_exposure_caps(cells)
    assert caps["-7"]["cap"] == 128 and caps["-7"]["next_fail"] == 191 and caps["-7"]["stopped_by"] == "fail"
    caps_d = wg.same_exposure_caps(_grid(lambda g: 1.0, lambda g: 1.0 if g < 230 else 0.7))
    assert caps_d["-7"]["cap"] == 191 and caps_d["-7"]["next_fail"] == 230
    # no rise (generic): the cap is gain minimum
    flat = wg.same_exposure_caps(_grid(lambda g: 1.0, resp=lambda g: 1.0))
    assert flat["-7"]["cap"] == 0 and flat["-7"]["next_fail"] == 26
    # an unusable reference cell leaves the exposure unknown
    bad = _grid(lambda g: 1.0)
    bad[7]["valid"] = False                                         # (-7, 0)
    assert wg.same_exposure_caps(bad)["-7"]["status"] == "unknown"


def test_matched_luma_cap_uses_long_exposure_references():
    # long exposures are cleaner at the same luma: rho at gain minimum falls with exposure
    cells = []
    for e, base, r0 in ((-9, 20.0, 0.06), (-7, 50.0, 0.04), (-5, 125.0, 0.02)):
        for g in (0, 64, 128, 255):
            mu = base * (1 + g / 128)
            cells.append(_cell(e, g, mu, r0, 0.5))
    m = wg.matched_luma_caps(cells)
    refs = m["references"]
    assert [r["exposure"] for r in refs] == [-9, -7, -5]
    # (-9, 128): mu 40 -> reference interpolated between -9 (20, .06) and -7 (50, .04): ~0.045 -> ratio 1.33 pass;
    # (-9, 255): mu ~60 -> reference ~0.038 -> ratio 1.57 fail
    row = m["per_exposure"]["-9"]
    assert row["cap"] == 128 and row["next_fail"] == 255
    r0, d0, how = wg.interp_ref(wg.matched_luma_refs(cells), 40.0)
    assert 0.04 < r0 < 0.06 and "interpolated" in how
    assert wg.interp_ref(wg.matched_luma_refs(cells), 400.0)[0] is None


def test_rho_monotonic():
    assert wg.rho_monotonic(_grid(lambda g: 1 + g / 255))["monotonic"] is True
    assert wg.rho_monotonic(_grid(lambda g: 1.0))["monotonic"] is True           # flat within tolerance
    dip = wg.rho_monotonic(_grid(lambda g: 0.8 if g == 128 else 1.0))
    assert dip["monotonic"] is False and dip["per_exposure"]["-7"]["dips"][0][0] == 128


def test_compare_run_and_rate():
    caps = {"-7": {"cap": 128, "next_fail": 191, "stopped_by": "fail"}}
    ok = wg.compare_run({"label": "forced_1", "exposure": -7, "g_lim": 169, "limit_reached": True, "probe_step": 1},
                        caps, 1)
    assert ok["comparable"] and ok["within"] and ok["bracket"] == [128, 191]
    far = wg.compare_run({"exposure": -7, "g_lim": 240, "limit_reached": True, "probe_step": 1}, caps, 1)
    assert far["comparable"] and not far["within"]
    tgt = wg.compare_run({"exposure": -7, "g_lim": 60, "limit_reached": False, "target_reached": True}, caps, 1)
    assert not tgt["comparable"] and "target" in tgt["why"]
    mono = {"monotonic": True, "rows_checked": 3}
    assert wg.rate_rule([ok, ok], [ok, ok], mono, 2, {})["rating"] == "yes"
    assert wg.rate_rule([ok, far], [ok, far], mono, 2, {})["rating"] == "partial"
    assert wg.rate_rule([far, far], [far, far], mono, 2, {})["rating"] == "no"
    assert wg.rate_rule([ok, ok], [ok, ok], {"monotonic": False}, 2, {})["rating"] == "partial"
    assert wg.rate_rule([tgt], [tgt], mono, 1, {})["rating"] == "untested"


# ================================================================================================== the rule
class RuleCam:
    """A synthetic camera for run_rule: luma = L0 * 2^(e - e0) * resp(g) at the flat patch; temporal noise
    rho(g) * mu; optional motion above a gain."""

    def __init__(self, L0=40.0, e0=-9, resp=lambda g: 1 + g / 255, rho=lambda g: 0.02, motion_above=None):
        self.L0, self.e0, self.resp, self.rho, self.motion_above = L0, e0, resp, rho, motion_above
        self.e, self.g, self.n_sets, self.seed = None, None, 0, 100

    def _frames(self, n):
        self.seed += 1
        L = min(250.0, self.L0 * 2.0 ** (self.e - self.e0) * self.resp(self.g))
        mov = 0 if (self.motion_above is not None and self.g > self.motion_above) else None
        ys = frames(L, self.rho(self.g), n, seed=self.seed, motion_from=mov)
        return {"ok": True, "ys": ys, "seqs": list(range(n)), "frames": [[None, None]] * n}

    def probe(self, e, g, n, discard_s):
        if (e, g) != (self.e, self.g):
            self.n_sets += 1
        self.e, self.g = e, g
        out = self._frames(n)
        out["set"] = {"items": {"exposure": e, "gain": g}}
        return out

    def more(self, n):
        return self._frames(n)


P = {"v_min": -11, "v_max": -2, "g_min": 0, "g_max": 255, "g_step": 1, "band": [95.0, 125.0]}


def test_rule_finds_the_noise_limit():
    # rho rises above gain 150: x1.5 at 170 (realistic noise: sigma 0.8 grey levels at gain minimum, so uint8
    # quantization lifts the reference a little and the measured crossing lands a few units higher); the scene
    # never reaches the band (max luma 80), so the limit is hit
    cam = RuleCam(rho=lambda g: 0.02 * (1.0 if g <= 150 else 1 + (g - 150) / 40))
    r = wg.run_rule(cam, {**P, "v_ceil": -9, "label": "forced_1"})
    assert r["exposure"] == -9 and r["gain_needed"] is True
    assert r["limit_reached"] is True and not r["target_reached"]
    assert 165 <= r["g_lim"] <= 180, r["g_lim"]
    assert r["rho_ratio"] <= wg.RHO_MAX_RATIO and r["n_gain_probes"] <= wg.MAX_GAIN_PROBES
    assert r["probe_step"] == 1 and r["time_s"] >= 0 and "too_dark_factor" in r
    caps = {"-9": {"cap": 128, "next_fail": 191, "stopped_by": "fail"}}
    assert wg.compare_run(r, caps, 1)["within"] is True


def test_rule_range_max_when_noise_never_rises():
    cam = RuleCam()
    r = wg.run_rule(cam, {**P, "v_ceil": -9})
    assert r["g_lim"] == 255 and r["limit_is_range_max"] and r["limit_reached"]


def test_rule_no_gain_needed_in_bright_light():
    cam = RuleCam(L0=110.0)
    r = wg.run_rule(cam, {**P, "v_ceil": -9})
    assert r["gain_needed"] is False and r["gain"] == 0 and r["g_lim"] is None and r["n_gain_probes"] == 0


def test_rule_exposure_first_steps_down_from_the_ceiling():
    cam = RuleCam(L0=200.0, e0=-5)                       # -5: 200 (above the band), -6: 100 (in it)
    r = wg.run_rule(cam, {**P, "v_ceil": -5})
    assert r["exposure"] == -6 and r["n_exposure_probes"] == 2 and r["gain_needed"] is False


def test_rule_ceiling_below_device_min():
    cam = RuleCam(L0=40.0, e0=-7)
    r = wg.run_rule(cam, {**P, "v_min": -7, "v_max": 3, "v_ceil": -9})
    assert "ceiling_below_device_min" in r["flags"] and r["exposure"] == -7


def test_rule_generic_gain_ineffective():
    cam = RuleCam(L0=60.0, resp=lambda g: 1.0)
    r = wg.run_rule(cam, {**P, "g_min": 1, "g_max": 7, "v_ceil": -9})
    assert r["g_lim"] == 1 and "gain_ineffective" in r["flags"] and r["limit_reached"]
    caps = wg.same_exposure_caps(_grid(lambda g: 1.0, gains=(1, 2, 3, 4, 5, 6, 7), resp=lambda g: 1.0))
    assert caps["-9"]["cap"] == 1
    assert wg.compare_run(r, caps, 1)["within"] is True


def test_rule_motion_guard_falls_back_and_flags():
    cam = RuleCam(motion_above=100)
    r = wg.run_rule(cam, {**P, "v_ceil": -9})
    assert "gain_limit_unverified" in r["flags"] and r["g_lim"] <= 100
    assert r["n_motion_retries"] >= wg.MOTION_RETRIES and r["limit_reached"] is False


def test_choose_forced_ceiling():
    cells = []
    for e, L in ((-11, 5.0), (-9, 15.0), (-7, 45.0), (-5, 160.0)):
        c = _cell(e, 0, L, 0.03, 0.5)
        if L < 30:
            c["metrics"]["rho"] = None                    # no flat mask in the dark rows
        cells.append(c)
    f = wg.choose_forced(cells, -5, {"min": -11, "max": -2, "step": 1})
    assert f["v_ceil"] == -7 and f["forced_by"] == "ceiling"
    bright = [_cell(-7, 0, 150.0, 0.03, 0.5), _cell(-5, 0, 200.0, 0.03, 0.5)]
    fb = wg.choose_forced(bright, -5, {"min": -11, "max": -2, "step": 1})
    assert fb["forced_by"] == "band" and fb["band"][0] > 150


# ================================================================================================== T4
def test_t4_analysis_finds_the_ceiling():
    plan = wg.t4_plan([-7, -6, -5, -4], 0, {})
    rows, events, t, seq = [], [], 0, 0
    t_first = 10_000_000_000
    cur = -7
    steps = {s["set_ms"]: s["exposure"] for s in plan["steps"]}
    while t < plan["end_ms"] * 1e6:
        for at, v in steps.items():
            if at * 1e6 <= t and not any(e["at_ms"] == at for e in events):
                cur = v
                events.append({"control": "cc.exposure", "at_ms": float(at), "applied_qpc_ns": t_first + t,
                               "done_qpc_ns": t_first + t + 5e6, "readback_value": v, "readback_flags": 2})
        rows.append({"seq": seq, "qpc_ns": t_first + t})
        seq += 1
        t += int(max(1 / 30.0, 2.0 ** cur * 1.05) * 1e9)
    events.append({"control": "cc.exposure", "at_ms": float(plan["end_ms"]), "applied_qpc_ns": t_first + t})
    out = wg.analyse_t4(rows, {"schedule": events}, plan, 30.0, {"min": -11, "max": -2, "step": 1})
    assert out["expected_ceiling"] == -5 and out["measured_ceiling"] == -5
    assert out["first_step_lowering_rate"]["exposure"] == -4 and out["first_step_lowering_rate"]["fps"] < 17
    assert [s["readback_ok"] for s in out["steps"]] == [True] * 4
    assert wg.rate_t4(out)["rating"] == "yes"
    assert wg.rate_t4({**out, "measured_ceiling": -6})["rating"] == "no"       # -5 already drops the rate
    gen = wg.analyse_t4(rows, {"schedule": events}, plan, 30.0, {"min": -7, "max": 3, "step": 1})
    assert gen["expected_ceiling"] is None and wg.rate_t4(gen)["rating"] == "untested"


# ================================================================================================== grid row analysis
def _write_capture(od: Path, plan: dict, cam_model, fps=30.0, save=True, drop_hold_at=None):
    """A synthetic wincam capture folder for one row plan: frames.jsonl, frames.mjpeg (real JPEG), summary dict."""
    od.mkdir(parents=True, exist_ok=True)
    items = []
    for it in plan["schedule"].split(";"):
        at, kv = it.split(":", 1)
        k, v = kv.split("=")
        items.append((float(at), k, v))
    state = {"exposure": None, "gain": None}
    for kv in plan["controls_before"].split(","):
        k, v = kv.split("=")
        if k in state:
            state[k] = int(v)
    t_first, rows, events, k_it = 5_000_000_000, [], [], 0
    n = int((plan["end_ms"] / 1000.0 + 0.3) * fps)
    with (od / "frames.mjpeg").open("wb") as fm, (od / "frames.jsonl").open("w") as fj:
        for i in range(n):
            t = t_first + int(i * 1e9 / fps)
            while k_it < len(items) and t_first + items[k_it][0] * 1e6 <= t:
                at, k, v = items[k_it]
                if k in state:
                    before = state[k]
                    if drop_hold_at is not None and k == "gain" and before is not None and at == drop_hold_at:
                        before = 3                         # the camera put gain back during the previous cell
                    if v != "manual":
                        state[k] = int(v)
                    events.append({"control": ("cc." if k == "exposure" else "pa.") + k, "at_ms": at,
                                   "before_value": before, "before_flags": 2, "readback_value": state[k],
                                   "readback_flags": 2, "matches": True,
                                   "applied_qpc_ns": t_first + int(at * 1e6),
                                   "done_qpc_ns": t_first + int(at * 1e6) + 4_000_000})
                k_it += 1
            y = cam_model(state["exposure"], state["gain"], i)
            b = simplejpeg.encode_jpeg(y[..., None], quality=95, colorspace="GRAY")
            row = {"seq": i, "qpc_ns": t, "bytes": len(b)}
            if save:
                row["mjpeg_offset"], row["mjpeg_len"] = fm.tell(), len(b)
                fm.write(b)
            fj.write(json.dumps(row) + "\n")
            rows.append(row)
    return {"ok": True, "schedule": events, "frames": {"total": n}}


def _model(e, g, i, L0=40.0, e0=-7):
    L = min(240.0, L0 * 2.0 ** ((e if e is not None else e0) - e0) * (1 + (g or 0) / 255))
    return frames(L, 0.04, 1, seed=1000 + i)[0]


def test_analyse_row_cells_readback_held_and_compaction(tmp_path):
    mode = ck.Mode(1280, 720, 30, 1)
    rng = {"exposure": {"min": -11, "max": -2, "step": 1}, "gain": {"min": 0, "max": 255, "step": 1}}
    plan = wg.row_plan(mode, -7, [0, 128, 255], {}, 16, rng["exposure"])
    s = _write_capture(tmp_path / "row", plan, _model)
    cells = wg.analyse_row(tmp_path / "row", s, plan, 16, rng, None)
    masks = cells[0].pop("_masks")
    assert masks["flat_ok"]
    assert [c["gain"] for c in cells] == [0, 128, 255]
    assert all(c["valid"] for c in cells), [c.get("why") for c in cells]
    assert all(c["n_frames"] == 16 and c["readback_ok"] and c["held"] for c in cells)
    assert cells[0]["settle_ms"] >= wg.SETTLE_S * 1000
    m0, m2 = cells[0]["metrics"], cells[2]["metrics"]
    assert m2["mu_mask"] / m0["mu_mask"] == pytest.approx(2.0, rel=0.05)
    assert m2["rho"] / m0["rho"] == pytest.approx(1.0, abs=0.25)        # ideal gain, after JPEG
    assert cells[0]["bytes"]["max"] >= cells[0]["bytes"]["p95"] >= 0 and cells[0]["fps"] == pytest.approx(30, rel=0.02)
    assert cells[0]["strict_decode_failures"] == 0
    comp = wg.compact_cells(tmp_path / "row", cells)
    assert comp["kept"] == 48 and comp["full_stream_deleted"] and not (tmp_path / "row" / "frames.mjpeg").exists()
    first = json.loads((tmp_path / "row" / "cells.jsonl").read_text().splitlines()[0])
    data = (tmp_path / "row" / "cells.mjpeg").read_bytes()[first["mjpeg_offset"]:first["mjpeg_offset"] + first["mjpeg_len"]]
    assert wg.decode_y(data)[1] is True


def test_analyse_row_flags_a_value_that_did_not_hold(tmp_path):
    mode = ck.Mode(1280, 720, 30, 1)
    rng = {"exposure": {"min": -11, "max": -2, "step": 1}, "gain": {"min": 0, "max": 255, "step": 1}}
    plan = wg.row_plan(mode, -7, [0, 128, 255], {}, 16, rng["exposure"])
    s = _write_capture(tmp_path / "row", plan, _model, drop_hold_at=float(plan["cells"][2]["set_ms"]))
    cells = wg.analyse_row(tmp_path / "row", s, plan, 16, rng, None)
    assert cells[1]["held"] is False and not cells[1]["valid"] and "changed during the cell" in cells[1]["why"]
    assert cells[0]["valid"] and cells[2]["valid"]


# ================================================================================================== whole run, fake ctx
KIYO = {"key": "1532:0e05:sn=K1", "name": "Razer Kiyo Pro", "vid": "1532", "pid": "0e05", "serial": "K1",
        "is_kiyo": True, "mf_symlink": r"\\?\usb#vid_1532&pid_0e05&mi_00#k1#{e5323777}\global",
        "ds_path": r"\\?\usb#vid_1532&pid_0e05&mi_00#k1#{65e8773d}\global"}
C922 = {"key": "046d:085c:sn=C1", "name": "C922 Pro Stream Webcam", "vid": "046d", "pid": "085c", "serial": "C1",
        "is_kiyo": False, "mf_symlink": r"\\?\usb#vid_046d&pid_085c&mi_00#c1#{e5323777}\global",
        "ds_path": r"\\?\usb#vid_046d&pid_085c&mi_00#c1#{65e8773d}\global"}

CTRL_DEFS = {"exposure": ("cc.", -11, -2, 1, -5, ["auto", "manual"]), "gain": ("pa.", 0, 255, 1, 0, ["manual"]),
             "white_balance": ("pa.", 2000, 7500, 10, 4000, ["auto", "manual"]),
             "focus": ("cc.", 0, 250, 5, 0, ["auto", "manual"]),
             "auto_exposure_priority": ("cc.", 0, 1, 1, 0, ["manual"]),
             "brightness": ("pa.", 0, 255, 1, 128, ["manual"])}


class FakeDevice:
    def __init__(self, cam, modes, L0=40.0):
        self.cam, self.modes, self.L0 = cam, modes, L0
        self.state = {"exposure": [-6, 1], "gain": [0, 2], "white_balance": [4000, 1], "focus": [30, 1],
                      "auto_exposure_priority": [1, 2], "brightness": [128, 2]}

    def controls_json(self):
        out = []
        for n, (pre, lo, hi, st, de, caps) in CTRL_DEFS.items():
            v, f = self.state[n]
            out.append({"name": n, "key": pre + n, "supported": True, "get_ok": True, "value": v, "flags": f,
                        "flags_names": ["auto"] if f & 1 else ["manual"], "min": lo, "max": hi, "step": st,
                        "default": de, "caps_flags_names": caps})
        return {"controls": out, "error": None}

    def apply(self, name, raw, flags=2):
        st = self.state[name]
        before = list(st)
        if raw == "auto":
            st[1] = 1
        elif raw == "manual":
            st[1] = 2
        else:
            st[0], st[1] = int(raw), flags
        pre = CTRL_DEFS[name][0]
        return {"control": pre + name, "requested": raw, "before_value": before[0], "before_flags": before[1],
                "readback_value": st[0], "readback_flags": st[1], "matches": True}

    def luma(self):
        e, g = self.state["exposure"][0], self.state["gain"][0]
        return min(250.0, self.L0 * 2.0 ** (e + 7) * (1 + g / 255))

    def rho(self):
        g = self.state["gain"][0]
        return 0.02 * (1.0 if g <= 150 else 1 + (g - 150) / 40)

    def frame(self, seed):
        return frames(self.luma(), self.rho(), 1, seed=seed)[0]


class FakeLive:
    """The rule leg's camera for the fake run (no files)."""

    def __init__(self, dev: FakeDevice):
        self.dev, self.fault, self.sets, self.clock_mode, self.seed = dev, None, [], "fake", 5000

    def start(self):
        pass

    def wait_first(self, timeout_s):
        return True

    def alive(self):
        return self.fault is None

    def stop(self):
        return {"summary": {"ok": True, "frames": {"total": 1}}, "run": {"rc": 0}}

    def set_checked(self, items, label=""):
        for k, v in items.items():
            self.dev.apply(k, str(v))
        rec = {"label": label, "items": items, "per": {k: {"ok": True} for k in items}, "_t_end_ns": 0}
        self.sets.append({"label": label, "items": items})
        return rec

    def _f(self, n):
        self.seed += 1
        ys = [self.dev.frame(self.seed * 100 + i) for i in range(n)]
        return {"ok": True, "ys": ys, "seqs": list(range(n)), "frames": [[None, None]] * n}

    def probe(self, e, g, n, discard_s):
        self.dev.apply("exposure", str(e))
        self.dev.apply("gain", str(g))
        return {**self._f(n), "set": {"items": {"exposure": e, "gain": g}}}

    def more(self, n):
        return self._f(n)


class FakeCtx:
    def __init__(self, tmp: Path, devices: dict, die_after_captures: dict):
        self.out_dir, self.raw_dir = tmp / "out", tmp / "raw"
        self.out_dir.mkdir(parents=True)
        self.raw_dir.mkdir(parents=True)
        self.args = suitectx.default_args(quick=True)
        self.devices = devices
        self.cameras = [d.cam for d in devices.values()]
        self.wincam = Path("wincam.exe")
        self.dry_run = False
        self.dead: dict = {}
        self.die_after = dict(die_after_captures)
        self.captures: dict = {}
        self.cmds: list = []
        self.after_dead_cmds: list = []
        self.logs: list = []

    def log(self, msg):
        self.logs.append(msg)

    def test_dir(self, name):
        d = self.out_dir / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def raw_test_dir(self, name):
        d = self.raw_dir / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def camera_gated(self, cam):
        return None

    def camera_dead(self, cam):
        return self.dead.get(cam["key"] if isinstance(cam, dict) else cam)

    def _dev(self, argv):
        txt = "\n".join(argv)
        hits = [d for d in self.devices.values() if d.cam["mf_symlink"] in txt or d.cam["ds_path"] in txt]
        return hits[0] if len(hits) == 1 else None

    def camcmd(self, argv, timeout_s, **kw):
        argv = [str(a) for a in argv]
        dev = self._dev(argv)
        self.cmds.append((dev.cam["key"] if dev else None, argv[:3]))
        if dev is not None and dev.cam["key"] in self.dead:
            self.after_dead_cmds.append(argv)
            return {"rc": 4, "stdout": json.dumps({"ok": False, "gate_skipped": True, "device_fault": True}),
                    "stderr": ""}
        out = self._emulate(dev, argv)
        if dev is not None and argv[1:2] == ["capture"]:
            n = self.captures[dev.cam["key"]] = self.captures.get(dev.cam["key"], 0) + 1
            if self.die_after.get(dev.cam["key"]) == n:
                self.dead[dev.cam["key"]] = {"dead": True, "since_utc": "2026-11-11T23:00:00Z",
                                             "code": "0x8007001F", "test": "W-GAIN"}
        return {"rc": 0, "stdout": json.dumps(out), "stderr": "", "timed_out": False, "elapsed_s": 0.1}

    def _emulate(self, dev, argv):
        if "--rule-leg" in argv:
            spec = json.loads(Path(argv[argv.index("--rule-leg") + 1]).read_text(encoding="utf-8"))
            return wg.rule_leg_run(spec, live=FakeLive(dev))
        sub = argv[1]
        if sub == "formats":
            return {"reader_streams": [{"types": [{"subtype": "MJPG", "width": w, "height": h, "fps_num": f,
                                                   "fps_den": 1} for (w, h, f) in dev.modes]}]}
        if sub == "controls":
            if "--set" in argv:
                flags = 1 if "--set-flags" in argv and argv[argv.index("--set-flags") + 1] == "auto" else 2
                sets = [dev.apply(*kv.split("="), flags=flags) for kv in argv[argv.index("--set") + 1].split(",")]
                return {"sets": sets}
            return dev.controls_json()
        if sub == "capture":
            return self._capture(dev, argv)
        raise AssertionError(f"unexpected command {argv}")

    def _capture(self, dev, argv):
        od = Path(argv[argv.index("--out-dir") + 1])
        od.mkdir(parents=True, exist_ok=True)
        fps = float(argv[argv.index("--fps") + 1])
        secs = float(argv[argv.index("--seconds") + 1])
        save = argv[argv.index("--save") + 1] == "all"
        cb = []
        if "--controls-before" in argv:
            cb = [dev.apply(*kv.split("=")) for kv in argv[argv.index("--controls-before") + 1].split(",")]
        items = []
        if "--schedule" in argv:
            for it in argv[argv.index("--schedule") + 1].split(";"):
                at, kv = it.split(":", 1)
                k, v = kv.split("=")
                items.append((float(at), k, v))
        t_first, t, i, k_it, events = 7_000_000_000, 0, 0, 0, []
        # like wincam: frames.mjpeg exists only with --save all|every:K
        with (od / ("frames.mjpeg" if save else "nosave.tmp")).open("wb") as fm, (od / "frames.jsonl").open("w") as fj:
            while t <= secs * 1e9:
                while k_it < len(items) and items[k_it][0] * 1e6 <= t:
                    at, k, v = items[k_it]
                    e = dev.apply(k, v)
                    e.update(at_ms=at, applied_qpc_ns=t_first + t, done_qpc_ns=t_first + t + 4_000_000)
                    events.append(e)
                    k_it += 1
                row = {"seq": i, "qpc_ns": t_first + t}
                if save:
                    b = simplejpeg.encode_jpeg(dev.frame(i)[..., None], quality=95, colorspace="GRAY")
                    row.update(bytes=len(b), mjpeg_offset=fm.tell(), mjpeg_len=len(b))
                    fm.write(b)
                fj.write(json.dumps(row) + "\n")
                i += 1
                period = max(1.0 / fps, 2.0 ** dev.state["exposure"][0] * 1.02)
                t += int(period * 1e9)
        return {"ok": True, "schedule": events, "controls_before": cb, "frames": {"total": i}, "error": None,
                "unreleasable": False}


def test_whole_quick_run_kiyo_pro_dies_mid_test(tmp_path, monkeypatch):
    monkeypatch.setattr(wg, "FIRST_SET_MS", 1200)
    devices = {KIYO["key"]: FakeDevice(KIYO, [(1280, 720, 30)]),
               C922["key"]: FakeDevice(C922, [(1280, 720, 30), (1280, 720, 60), (1920, 1080, 30)])}
    # Kiyo Pro: dies right after its 2nd capture (T4 done, first grid row captured)
    ctx = FakeCtx(tmp_path, devices, {KIYO["key"]: 2})
    assert wg.estimate_s(ctx) > 0
    res = wg.run(ctx)
    v = res["verdicts"]
    # no command reached the Kiyo Pro after it was marked dead, and none was even attempted
    assert ctx.after_dead_cmds == []
    assert ctx.captures[KIYO["key"]] == 2
    last_kiyo = max(i for i, c in enumerate(ctx.cmds) if c[0] == KIYO["key"])
    assert all(c[0] != KIYO["key"] for c in ctx.cmds[last_kiyo + 1:])
    assert ctx.cmds[last_kiyo][1][1:2] == ["capture"]            # its last command was the capture it died in
    kslug = "1280x720_30"
    for g in ("gain_grid", "gain_rule"):
        kv = v[f"{g}|{KIYO['key']}|{kslug}"]
        assert kv["rating"] == "untested" and "device fault/dead" in kv["note"]
    kres = res["measurements"]["cameras"][KIYO["key"]]
    assert kres["device_fault"] and kres["restore"]["restored"] is None
    assert v[f"fps_ceiling|{KIYO['key']}|{kslug}"]["rating"] == "yes"      # finished before the fault
    # the C922 ran both 720-line modes (1080p is out of scope) and was restored
    c = res["measurements"]["cameras"][C922["key"]]
    assert c["modes"] == ["MJPG 1280x720@30", "MJPG 1280x720@60"]
    assert c["restore"]["restored"] is True
    assert c["locks"]["locked"] is True
    assert devices[C922["key"]].state["exposure"][1] == 1 and devices[C922["key"]].state["white_balance"][1] == 1
    for slug in ("1280x720_30", "1280x720_60"):
        assert v[f"gain_grid|{C922['key']}|{slug}"]["rating"] == "yes", v[f"gain_grid|{C922['key']}|{slug}"]
        assert v[f"fps_ceiling|{C922['key']}|{slug}"]["rating"] == "yes", res["measurements"]["cameras"][C922["key"]]["per_mode"][slug]["t4"]
        rv = v[f"gain_rule|{C922['key']}|{slug}"]
        pm = c["per_mode"][slug]
        assert pm["rule"]["forced_runs"] and len(pm["rule"]["forced_runs"]) == 2
        assert all(165 <= r["g_lim"] <= 180 for r in pm["rule"]["forced_runs"]), pm["rule"]["forced_runs"]
        assert rv["rating"] in ("yes", "partial"), rv
        assert pm["reference_cap"]["same_exposure"]["-7"]["cap"] == 128
    assert c["per_mode"]["1280x720_30"]["t4"]["measured_ceiling"] == -5
    assert c["per_mode"]["1280x720_60"]["t4"]["measured_ceiling"] == -6
    # strict JSON (no numpy objects, no NaN) and raw frames only under raw_dir
    json.dumps(res, allow_nan=False)
    assert list(ctx.raw_dir.rglob("cells.mjpeg")) and not list(ctx.out_dir.rglob("*.mjpeg"))
    # full streams are compacted to the cell frames; the only one left is the row the Kiyo Pro died in (not analysed:
    # the camera's work stops at once, and the raw stream stays as evidence)
    left = [p.parent.name for p in (ctx.raw_dir / "W-GAIN").rglob("frames.mjpeg")]
    assert left == ["1280x720_30_e-7"] or wg.KEEP_FULL_STREAMS


class DyingLive(FakeLive):
    """A rule-leg camera whose DirectShow set reports device_not_answering after ``n`` probes."""

    def __init__(self, dev, n=3):
        super().__init__(dev)
        self.left = n

    def probe(self, e, g, n, discard_s):
        self.left -= 1
        if self.left < 0:
            self.fault = {"kind": "device_error", "code": "0x8007001F", "stage": "control_set",
                          "reason": "DirectShow side-channel set: device not answering"}
            return {"ok": False, "error": "device fault on set"}
        return super().probe(e, g, n, discard_s)


def test_rule_leg_fault_is_surfaced_for_the_camcmd_scan(monkeypatch):
    monkeypatch.setattr(wg, "FIRST_SET_MS", 0)
    dev = FakeDevice(C922, [(1280, 720, 30)])
    spec = {"locks": {"focus": 30}, "ds_path": C922["ds_path"], "deadline_s": 60,
            "runs": [{**P, "label": f"forced_{i}", "v_ceil": -7} for i in (1, 2, 3)]}
    doc = wg.rule_leg_run(spec, live=DyingLive(dev, 3))
    assert doc["error"]["class"] == "device_error" and suitectx.fault_signature(doc, {}, streaming=False)
    assert doc["runs"][0].get("error") and all("skipped" in r for r in doc["runs"][1:])


def test_rule_leg_fault_gives_dead_verdict_and_no_restore(tmp_path):
    dev = FakeDevice(C922, [(1280, 720, 30)])
    ctx = FakeCtx(tmp_path, {C922["key"]: dev}, {})
    orig = ctx._emulate

    def emulate(d, argv):
        if "--rule-leg" in argv:
            spec = json.loads(Path(argv[argv.index("--rule-leg") + 1]).read_text(encoding="utf-8"))
            doc = wg.rule_leg_run(spec, live=DyingLive(d, 4))
            ctx.dead[d.cam["key"]] = {"dead": True, "since_utc": "2026-11-11T23:30:00Z", "code": "0x8007001F"}
            return doc
        return orig(d, argv)
    ctx._emulate = emulate
    res = wg.run(ctx)
    k, slug = C922["key"], "1280x720_30"
    assert ctx.after_dead_cmds == []
    assert ctx.cmds[-1][1][2:3] == ["--rule-leg"] or "--rule-leg" in ctx.cmds[-1][1]
    assert res["verdicts"][f"gain_rule|{k}|{slug}"]["summary_label"] == "untested (device fault/dead)"
    assert res["verdicts"][f"gain_grid|{k}|{slug}"]["rating"] == "yes"            # finished before the fault
    c = res["measurements"]["cameras"][k]
    assert c["restore"]["restored"] is None and c["per_mode"][slug]["rule"]["fault"]["kind"] == "device_error"


def test_gated_camera_gets_no_command(tmp_path):
    devices = {KIYO["key"]: FakeDevice(KIYO, [(1280, 720, 30)])}
    ctx = FakeCtx(tmp_path, devices, {})
    ctx.dead[KIYO["key"]] = {"dead": True, "since_utc": "2026-11-11T22:00:00Z", "code": "0x8007001F"}
    res = wg.run(ctx)
    assert ctx.cmds == []
    assert res["verdicts"][f"gain_rule|{KIYO['key']}|mf"]["note"].startswith("untested: device fault/dead")
