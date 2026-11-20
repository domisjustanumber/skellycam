"""T-CAP-43, T-CAP-45 to T-CAP-47, T-CAP-49 and T-CAP-50: the source setting, the dependency, the
Media Foundation module, no compiled extension, and the two "local" tests (specs/windows-capture.md,
sections 3, 4.3, 5.6, 14.2, 15 and 16.1).
"""

import asyncio
import re
import subprocess
import sys
import threading
import time
import tomllib
from pathlib import Path
from types import SimpleNamespace

import psutil
import pytest

from skellycam.tests.capture.capture_session import capture_app, product, ready_app_steps
from skellycam.tests.capture.fake_source import FakeScript

REPO_ROOT = Path(__file__).resolve().parents[3]
WINDOWS = sys.platform == "win32"
INTERFACES = ("IMFActivate", "IMFAttributes", "IMFMediaSource", "IMFSourceReader", "IMFSourceReaderCallback",
              "IMFMediaType", "IMFSample", "IMFMediaBuffer", "IAMCameraControl", "IAMVideoProcAmp", "IKsControl")


@pytest.mark.skipif(not WINDOWS, reason="the setting chooses the source on Windows only (14.2)")
def test_t_cap_43_source_setting_on_windows(monkeypatch):
    """T-CAP-43, section 14.2 [D8, agent 38]: on Windows: no setting, `opencv`, `media_foundation`, a
    wrong value. OpenCV, OpenCV, Media Foundation, an error that names the allowed values. Runs only
    before the last commit of phase 3 (16.1); that commit deletes this test with the setting."""
    worker = product("skellycam.core.camera.camera_worker")
    monkeypatch.delenv("SKELLYCAM_WINDOWS_CAPTURE", raising=False)
    assert worker.select_capture_source() == "opencv"
    monkeypatch.setenv("SKELLYCAM_WINDOWS_CAPTURE", "opencv")
    assert worker.select_capture_source() == "opencv"
    monkeypatch.setenv("SKELLYCAM_WINDOWS_CAPTURE", "media_foundation")
    assert worker.select_capture_source() == "media_foundation"
    monkeypatch.setenv("SKELLYCAM_WINDOWS_CAPTURE", "directshow")
    with pytest.raises(ValueError) as error:
        worker.select_capture_source()
    assert "opencv" in str(error.value) and "media_foundation" in str(error.value)


def test_t_cap_45_comtypes_pinned_for_windows_only():
    """T-CAP-45, section 3 [D7]: read `pyproject.toml` and `uv.lock`. `comtypes==1.5.0` with the marker
    `sys_platform == "win32"`; locked at 1.5.0."""
    from packaging.requirements import Requirement

    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    found = [Requirement(item) for item in project["dependencies"] if Requirement(item).name == "comtypes"]
    assert len(found) == 1, "comtypes is not a dependency"
    assert str(found[0].specifier) == "==1.5.0"
    assert str(found[0].marker) == 'sys_platform == "win32"'
    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    assert [p["version"] for p in lock["package"] if p["name"] == "comtypes"] == ["1.5.0"]


# The body of T-CAP-46 in a fresh process. The product does each Media Foundation call in a fresh
# process (the camera process and the detection child); the main process never imports comtypes.
T_CAP_46_CHILD = """
import ctypes
import sys
from skellycam.core.camera.capture.media_foundation import com, detect
missing = [name for name in sys.argv[1].split(",") if not hasattr(com, name)]
assert not missing, f"missing interface declarations: {missing}"
try:
    ctypes.WinDLL("mfplat.dll")
except OSError:
    print("NO MFPLAT")
    sys.exit(0)
com.startup()
try:
    assert isinstance(detect.MediaFoundationBackend().devices(), list)
finally:
    com.shutdown()
print("ENUMERATED")
"""


@pytest.mark.skipif(not WINDOWS, reason="the Windows runner only (15)")
def test_t_cap_46_media_foundation_module_loads():
    """T-CAP-46, section 15 [D1, D7, D47, agent 39]: on the Windows runner: import the Media Foundation
    module; if `mfplat.dll` loads, call `MFStartup`, enumerate, `MFShutdown`. The import passes; the
    interface declarations exist; an enumeration returns a list.

    The enumeration lists the devices. It does not activate or open a device. The steps run in a fresh
    process, as in the product: comtypes joins the MTA at import, and the main thread of the test
    process can already be in a single-threaded apartment (sounddevice puts it there at import)."""
    process = subprocess.run([sys.executable, "-c", T_CAP_46_CHILD, ",".join(INTERFACES)],
                             cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
    assert process.returncode == 0, process.stderr[-2000:]
    if "NO MFPLAT" in process.stdout:
        pytest.skip("mfplat.dll does not load on this runner (M-CAP-5); the import and the declarations passed")
    assert "ENUMERATED" in process.stdout, process.stdout


def test_codec_probe_of_a_record_start_on_a_camera_loop_thread(monkeypatch):
    """A record start probes the video codec on the camera loop thread. With THREAD workers that thread
    is not the main thread, and CPython refuses `signal.signal` there (CI run of d8989972d, Linux and
    macOS). The stand-in `signal` module has that rule of CPython, so this test fails without the fix
    on each system, also on Windows, where the product uses no alarm."""
    helpers = product("skellycam.core.recorders.videos.fourcc_codec_helpers")

    def main_thread_only(*args):
        if threading.current_thread() is not threading.main_thread():
            raise ValueError("signal only works in main thread of the main interpreter")

    monkeypatch.setattr(helpers, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(helpers, "signal", SimpleNamespace(SIGALRM=14, signal=main_thread_only, alarm=main_thread_only))
    result = []
    thread = threading.Thread(target=lambda: result.append(helpers.resolve_writer_fourcc("MJPG", (64, 48))))
    thread.start()
    thread.join(60)
    assert result == ["MJPG"]


def test_t_cap_47_no_compiled_extension():
    """T-CAP-47, section 3 [D1]: search the package. No compiled extension of its own and no
    `_skellycam_rust` import. The capture tests themselves are not searched."""
    package = REPO_ROOT / "skellycam"
    own = Path(__file__).resolve().parent
    compiled = [p for p in package.rglob("*") if p.suffix.lower() in {".pyd", ".so", ".dll", ".dylib", ".pyx", ".c", ".cpp"}
                and ".venv" not in p.parts]
    assert not compiled, f"compiled extension files in the package: {compiled}"
    pattern = re.compile(r"^\s*(import|from)\s+_skellycam_rust\b|import_module\(\s*['\"]_skellycam_rust")
    hits = [f"{p.relative_to(REPO_ROOT)}:{n}" for p in package.rglob("*.py") if own not in p.parents
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if pattern.search(line)]
    assert not hits, f"_skellycam_rust imports: {hits}"
    build = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")).get("tool", {})
    assert "maturin" not in build and "setuptools-rust" not in str(build)


@pytest.mark.capture_local
@pytest.mark.skipif(not WINDOWS, reason="the Windows development machine only (16.1)")
def test_t_cap_49_idle_cpu_of_the_shared_loop(monkeypatch):
    """T-CAP-49, sections 4.3 and 2.1 [D48]: marker `capture_local`. Run T-RING-31 with the shared loop
    on the Windows development machine: a camera process with a fake source, paused for 10 s. Process
    CPU under 2 % of one core. Windows counts CPU time in steps of 15.6 ms, so 10 s keeps that step
    under 0.2 %. Real time: about 20 s."""
    with capture_app(monkeypatch, [FakeScript()], workers="process") as app:
        ready_app_steps(app)
        camera_id = app.factory.camera_ids[0]
        asyncio.run(app.group.cameras.orchestrator.pause(await_paused=False))  # the internal pause (Q495)
        app.wait(lambda: app.status(camera_id)["is_paused"], "the camera pauses")
        time.sleep(0.5)
        cpu = psutil.Process(app.worker(camera_id).worker.pid)
        before, t0 = cpu.cpu_times(), time.perf_counter()
        time.sleep(10.0)
        after, t1 = cpu.cpu_times(), time.perf_counter()
    used = (after.user - before.user + after.system - before.system) / (t1 - t0)
    assert used < 0.02, f"the paused camera process used {used:.1%} of one core"


@pytest.mark.capture_local
@pytest.mark.skipif(not WINDOWS, reason="the Windows development machine only (16.1)")
def test_t_cap_50_libjpeg_warning_limit_on_windows():
    """T-CAP-50, section 5.6 [D42, D48]: marker `capture_local`. Run T-RING-46 on the Windows
    development machine. It passes (not an expected failure)."""
    node = "skellycam/tests/frame_ring/test_decode_stage.py::test_t_ring_46_libjpeg_warnings_do_not_flood_the_log"
    process = subprocess.run([sys.executable, "-m", "pytest", node, "-q", "-p", "no:cacheprovider", "-W", "ignore"],
                             cwd=REPO_ROOT, capture_output=True, text=True, timeout=300)
    summary = process.stdout.strip().splitlines()[-1] if process.stdout.strip() else process.stderr[-500:]
    assert process.returncode == 0 and re.search(r"\b1 passed\b", summary) and "xfail" not in summary, summary
