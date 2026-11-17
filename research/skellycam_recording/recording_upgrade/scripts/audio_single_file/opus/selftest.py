# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""Assert-based self-check of the opus_common timing locator on synthetic player outputs (no media files).
Usage: uv run --script .../opus/selftest.py"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import opus_common as O  # noqa: E402

src = O.src_f(30 * O.RATE)
for tgt, sil in [(240000, 0), (240000, 500), (100123, 0)]:  # 0.6 s from the start, [silence], then content from tgt
    r = O.seek_landing(np.r_[src[:28800], np.zeros(sil), src[tgt:tgt + 48000]], src, tgt)
    assert r["error_samples"] == 0 and r["silence_after_jump"] == sil and r["timeline_error_samples"] == -sil, r
r = O.seek_landing(np.r_[np.zeros(3000), src[240000 - 312:288000]], src, 240000)  # starts 312 early after silence
assert r["error_samples"] == -312, r
y = np.r_[src[:28800], np.random.default_rng(1).normal(0, 0.1, 480), src[240480:288000]]  # 10 ms of garbage
r = O.seek_landing(y, src, 240000)  # (decoder convergence) after the jump: content still lands on time
assert r["error_samples"] == 0 and r["convergence_samples"] >= 240, r
r = O.seek_landing(np.r_[np.zeros(312), src[:28800], src[240000 - 312:288000]], src, 240000)  # plays 312 late
assert r["lag_pre"] == -312 and r["error_samples"] == -312, r
r = O.seek_landing(np.r_[src[:2400], src[240144:290000]], src, 240144)  # 50 ms from 0, then the jump
assert r["error_samples"] == 0 and r["jump_at_output_sample"] == 2400, r
x = np.r_[src[312:10 * O.RATE]]  # a decode that drops the first 312 samples = audio early
t = O.timing(x, 11 * O.RATE)
assert t["click_offsets"] == [-312] and t["corr_lag"] == -312, t
print("selftest ok")
