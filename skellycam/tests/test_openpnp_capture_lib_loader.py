"""Tests for openpnp-capture native library discovery (optional real DLL)."""

import pytest

from skellycam.core.camera.openpnp_capture.types import OpenPnPCaptureLibraryNotFoundError


def test_load_openpnp_capture_library_smoke() -> None:
    from skellycam.core.camera.openpnp_capture._lib_loader import load_openpnp_capture_library

    try:
        lib = load_openpnp_capture_library()
    except OpenPnPCaptureLibraryNotFoundError:
        pytest.skip("openpnp-capture native library not installed (see skellycam/_vendor/openpnp_capture/README.md)")
    assert lib is not None


def test_cap_create_context_roundtrip() -> None:
    from skellycam.core.camera.openpnp_capture._bindings import get_cap_functions

    try:
        cap = get_cap_functions()
    except OpenPnPCaptureLibraryNotFoundError:
        pytest.skip("openpnp-capture native library not installed")
    ctx = cap.Cap_createContext()
    try:
        assert ctx is not None
        n = cap.Cap_getDeviceCount(ctx)
        assert isinstance(n, int)
    finally:
        cap.Cap_releaseContext(ctx)
