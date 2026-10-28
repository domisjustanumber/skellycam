"""Offline selftests of the stand-alone GigE Vision hardware tests in research/gige_vision/hardware_tests.

The scripts moved out of the skellycam package (formerly skellycam/system/diagnostics/gige) on 2026-10-28.
They are now loaded as plain sibling modules from the parent folder, the same way the scripts load
gev_common.py, so beartype (beartype_this_package) is NO LONGER applied to them automatically; this test
only checks the selftest results. No network access and no viva-genicam needed.

Run from the repo root: python -m pytest research/gige_vision/hardware_tests/tests -q
"""
import os
import sys

import pytest

_HARDWARE_TESTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HARDWARE_TESTS_DIR not in sys.path:
    sys.path.insert(0, _HARDWARE_TESTS_DIR)

import gev_common  # noqa: E402
import gev_ptp_sync_test  # noqa: E402
import gvsp_capture_report  # noqa: E402
import udp_recv_benchmark  # noqa: E402
import viva_sync_capture_test  # noqa: E402


@pytest.mark.parametrize(
    "extra",
    [
        None,
        gev_ptp_sync_test.selftest_extra,
        gvsp_capture_report.selftest_extra,
        udp_recv_benchmark.selftest_extra,
        viva_sync_capture_test.selftest_extra,
    ],
    ids=["gev_common", "gev_ptp_sync_test", "gvsp_capture_report", "udp_recv_benchmark", "viva_sync_capture_test"],
)
def test_gige_selftest(extra):
    """Packet encode/decode, GVSP analyser, pcap I/O, mini GenApi and script-specific checks all pass."""
    rep = gev_common.Reporter("pytest", quiet=True)
    gev_common.run_selftest(rep)
    if extra is not None:
        extra(rep)
    failed = [r.as_dict() for r in rep.results if r.status == gev_common.FAIL]
    assert not failed
    assert len(rep.results) >= 40
