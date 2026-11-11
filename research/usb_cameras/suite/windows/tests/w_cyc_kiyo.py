"""W-CYC-KIYO: the Razer Kiyo Pro's W-CYC open/close cycles, run early in the suite.

Plan docs/capture_stack_options_plan.md 6.1 (W-CYC-381) asks for the Kiyo's >= 381-cycle reliability runs "within
its healthy window": it tends to wedge ~210 min after plug-in once it has streamed, and its 400-cycle MF and
DirectShow variants alone take about an hour. The runner therefore runs this segment early: after the short Kiyo
captures and the control tests (review round 3: its ~1,060 Kiyo stream starts come after the Kiyo's control work,
since cumulative stream starts are the leading wedge hypothesis; this segment may end in a fault, a recorded result),
before W-MULTI (the contention test that wedged it on 11-06) and W-PYAV-LIST (which is meant to meet a wedged Kiyo),
and W-CYC at the end of the run then cycles only the other cameras (``ctx.cyc_kiyo_first``).

Everything else (variants, profile, ratings, the Wilson claim, fault handling, partial results) is W-CYC's: see
tests/w_cyc.py. Result: <out>/W-CYC-KIYO.json with the usual ``reliability|<kiyo key>|<variant>`` verdicts.
No Kiyo attached: an empty result (nothing is opened).

Offline re-analysis: python suite/windows/tests/w_cyc.py --reanalyse <run_dir> --test W-CYC-KIYO
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (str(HERE.parent.parent), str(HERE.parent), str(HERE.parent / "helpers"), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import w_cyc  # noqa: E402

TEST = w_cyc.KIYO_TEST
INFO = {"id": TEST, "module": "tests.w_cyc_kiyo", "goal": "reliability", "opens_cameras": True,
        "description": "W-CYC's open/close cycles for the Razer Kiyo Pro only, early in its healthy window"}


def estimate_s(ctx) -> float:
    return w_cyc.estimate_s(ctx, segment="kiyo")


def run(ctx) -> dict:
    return w_cyc.run(ctx, segment="kiyo")


def reanalyse(run_dir, out=None) -> dict:
    return w_cyc.reanalyse(run_dir, out, test=TEST)
