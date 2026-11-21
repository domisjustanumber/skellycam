"""T-UNX-76: `MediaFoundationSource` with the stand-in interfaces of `mf_standins.py` (specs/unix-capture.md
4.2 item 2, 4.6.2). Windows only (U18). Each case runs in a fresh process (see
`mf_standins.py`)."""

import json
import subprocess
import sys

import pytest

from skellycam.tests.capture.capture_session import product

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="the media_foundation package is Windows only (U18)")


def run_case(case):
    process = subprocess.run([sys.executable, "-m", "skellycam.tests.capture.mf_standins", case],
                             capture_output=True, text=True, timeout=120)
    assert process.returncode == 0, process.stderr[-3000:]
    return json.loads(process.stdout.strip().splitlines()[-1])


def test_t_unx_76_media_foundation_diagnostics():
    """T-UNX-76: every key of 4.6.2; `id_source` `mf-link`; `native_domain` `hresult`; `clock` `unknown`;
    the `t_*_ms` keys of the steps that Media Foundation has are filled (it has no buffer step)."""
    source = product("skellycam.core.camera.capture.source")
    result = run_case("diagnostics")
    data = result["diagnostics"]
    assert result["frames"] == 10
    assert set(data) == set(source.SOURCE_KEYS)
    assert (data["backend"], data["id_source"], data["native_domain"], data["clock"]) == (
        "media-foundation", "mf-link", "hresult", "unknown")
    times = {key: data[key] for key in source.SOURCE_KEYS if key.startswith("t_")}
    assert times.pop("t_buffers_ms") is None
    assert all(isinstance(value, float) and value >= 0 for value in times.values()), times
    assert (data["requested_w"], data["granted_w"], data["granted_fps_num"], data["delivered"]) == (640, 640, 30, "jpeg")
    assert data["frames"] >= 10 and len(data["frame_log"]) == min(64, data["frames"])
    assert data["sample_minus_arrival_p50_ms"] == pytest.approx(-4.0, abs=0.01)
    assert data["later_than_arrival"] == 0 and data["sample_time_kept"] is True
    assert (data["exposure_present"], data["exposure_value"], data["control_path"]) == (True, -7, "iam")
    assert data["focus_present"] is False and data["fail_code"] is None

