"""Tests for WebSocket server-side framerate calculation. The performance data went with the capture timings
(specs/capture-timings.md 6.4, Q580)."""
import pytest

from skellycam.api.websocket.websocket_server import ServerFramerateCalculator


# ---------------------------------------------------------------------------
# ServerFramerateCalculator
# ---------------------------------------------------------------------------

class TestServerFramerateCalculator:
    def test_no_data_returns_none(self) -> None:
        calc = ServerFramerateCalculator(source_name="test")
        assert calc.current_framerate is None

    def test_single_observation_returns_none(self) -> None:
        calc = ServerFramerateCalculator(source_name="test")
        calc.update(frame_number=0, capture_timestamp_ns=1_000_000_000.0)
        assert calc.current_framerate is None

    def test_consecutive_frames_compute_framerate(self) -> None:
        calc = ServerFramerateCalculator(source_name="test")
        base_ns = 1_000_000_000.0
        interval_ns = 33_333_333.0  # ~30fps

        for i in range(10):
            calc.update(
                frame_number=i,
                capture_timestamp_ns=base_ns + i * interval_ns,
            )

        fr = calc.current_framerate
        assert fr is not None
        assert fr.mean_frames_per_second == pytest.approx(30.0, rel=0.05)
        assert fr.framerate_source == "test"

    def test_skipped_frames_compute_true_rate(self) -> None:
        """When frames are skipped (backpressure), the calculator should still
        compute the true per-frame capture rate, not the websocket send rate."""
        calc = ServerFramerateCalculator(source_name="test")
        base_ns = 1_000_000_000.0
        interval_ns = 33_333_333.0  # ~30fps

        # Send every other frame (simulating backpressure skip)
        for i in range(0, 20, 2):
            calc.update(
                frame_number=i,
                capture_timestamp_ns=base_ns + i * interval_ns,
            )

        fr = calc.current_framerate
        assert fr is not None
        # Should still be ~30fps (true capture rate), not 15fps (display rate)
        assert fr.mean_frames_per_second == pytest.approx(30.0, rel=0.1)

    def test_clear_resets(self) -> None:
        calc = ServerFramerateCalculator(source_name="test")
        base_ns = 1_000_000_000.0
        interval_ns = 33_333_333.0
        for i in range(5):
            calc.update(frame_number=i, capture_timestamp_ns=base_ns + i * interval_ns)
        assert calc.current_framerate is not None

        calc.clear()
        assert calc.current_framerate is None
