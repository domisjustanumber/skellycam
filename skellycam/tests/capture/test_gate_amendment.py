"""GA-01 to GA-07: failing tests of the PROPOSED gate rule (specs/windows-capture-gate-amendment.md).

The rule is proposed. The user has not decided it. These tests have the marker `gate_amendment`.
The default selection (`addopts` in `pyproject.toml`) and the CI selections deselect them, so the
accepted suite stays green. Run them with `uv run pytest skellycam/tests/capture -m gate_amendment`.
Each test fails on the gate rule of today (D26) with the measured value in its message.

The proposed rule: a round closes when every camera in the gate has a frame newer than the one it
gave last. Each camera then gives its newest frame. Frames that it took earlier count as replaced.

Arrival model (GA-01 to GA-06), from `research/usb_cameras/docs/camera_spread_analysis_20261120.md`
(branch `dom/research`): three cameras with true frame periods of 33.333, 33.313 and 33.279 ms. Each
camera delivers on its own 16 ms grid, so its intervals are 32 or 48 ms. The second camera delivers
32 ms late, and its sample time is 32.3 ms before its arrival (the Kiyo Pro of T-CAP-59). The
schedules are absolute on the virtual clock, so the start-up order does not change the phases.

Two seams of this file only (no change of `fake_source.py` or `capture_session.py`):

- `absolute_schedules`: a fake whose script has `arrivals_ns` takes its next arrival from that list.
- `exact_gate_clock`: the virtual clock does not move while a loop that waits at the gate could pass
  it now. Without it, the clock can move to the next arrival before the loop sees the open gate, and
  the loop then takes a later frame than the rule gives. It applies to each rule in the same way.
"""

import bisect
import logging
import statistics
import threading
import time

import numpy as np
import psutil
import pytest

from skellycam.tests.capture.capture_session import (
    RingWatcher, Spies, capture_app, capture_logs, ready_app_steps, sfn_gaps)
from skellycam.tests.capture.fake_source import FakeScript, FakeSource, VirtualClock

pytestmark = pytest.mark.gate_amendment

START_NS = VirtualClock.START_NS
PERIOD_NS = 1e9 / 30
GRID_US = 16_000
SCHEDULE_S = 200  # longer than each run
PERIODS_US = (33_333, 33_313, 33_279)  # the camera periods of section 4 of the analysis
LATE_US = (0, 32_000, 0)  # the Kiyo Pro delivers about 32 ms after its sample time
SAMPLE_OFFSET_MS = (-0.33, -32.3, -0.33)  # T-CAP-59: arrival minus sample time
OWN_GRID_US = (0, 5_000, 10_000)  # each camera on its own 16 ms grid: reproduces the measured spread
ONE_GRID_US = (0, 0, 0)  # all cameras on one 16 ms grid: ties at one instant, more replaced frames
POLL_NS = 1_000_000  # one wait step of 4.3: a loop sees a closed round within 1 ms
LIMIT_NS = 100_000_000  # the limit of T-CAP-108: no gap above 100 ms after a camera dies
SETTLE_ROUNDS = 30


# ---------------------------------------------------------------------------
# Arrival schedules and seams
# ---------------------------------------------------------------------------

def grid_schedule(period_us, grid_us, late_us, phase_us=0):
    """Absolute arrival times (ns): the true time phase + k * period, delivered at the next point of the
    camera's own 16 ms grid, plus the delivery delay."""
    out, k = [], 0
    while True:
        true_us = phase_us + k * period_us
        arrival_us = -(-(true_us - grid_us) // GRID_US) * GRID_US + grid_us + late_us
        out.append(START_NS + arrival_us * 1000)
        if arrival_us > SCHEDULE_S * 1_000_000:
            return tuple(out)
        k += 1


def exact_schedule(period_ns, phase_ns):
    """Absolute arrival times (ns) with no grid: exact mode periods (29.97 and 30 fps)."""
    count = int(SCHEDULE_S * 1e9 / period_ns) + 2
    return tuple(START_NS + round(phase_ns + k * period_ns) for k in range(count))


def measured_scripts(grids):
    scripts = []
    for period, grid, late, offset in zip(PERIODS_US, grids, LATE_US, SAMPLE_OFFSET_MS):
        script = FakeScript(sample_offset_ms=offset)
        script.arrivals_ns = grid_schedule(period, grid, late)
        scripts.append(script)
    return scripts


def absolute_schedules(monkeypatch):
    original = FakeSource._interval_ns

    def interval(self, previous_arrival):
        arrivals = getattr(self.script, "arrivals_ns", None)
        if arrivals is None:
            return original(self, previous_arrival)
        return arrivals[bisect.bisect_right(arrivals, previous_arrival)] - previous_arrival

    monkeypatch.setattr(FakeSource, "_interval_ns", interval)


def product_gate():
    """The gate of the product, before `capture_app` wraps it with its clock probe."""
    from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator

    return CameraOrchestrator.should_grab_by_id


def exact_gate_clock(monkeypatch, app, should_grab):
    from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator

    at_gate = {}  # thread ident -> (orchestrator, camera_id)
    probe = CameraOrchestrator.should_grab_by_id

    def record(self, camera_id):
        at_gate[threading.get_ident()] = (self, camera_id)
        return probe(self, camera_id)

    monkeypatch.setattr(CameraOrchestrator, "should_grab_by_id", record)
    clock = app.clock
    advance = clock._advance

    def exact_advance(force=False):
        if not force:
            for ident, state in list(clock._states.items()):
                if state == "gate" and ident in at_gate:
                    orchestrator, camera_id = at_gate[ident]
                    try:
                        if should_grab(orchestrator, camera_id):
                            return
                    except Exception:
                        pass
        advance(force)

    clock._advance = exact_advance


def record_writes(monkeypatch, app):
    """For each JPEG ring write: (frame_number, clock ns, `replaced_count` of the status before the write).
    The status value before the write of frame r + 1 is the value that the loop set after frame r."""
    from skellycam.core.ipc.frame_ring import FrameRingWriter

    spy = FrameRingWriter.write
    writes = {}

    def write(writer, payload, **kwargs):
        if payload is not None and not isinstance(payload, np.ndarray):
            camera_id = next((cid for cid, info in list(app.group.ring_infos.items())
                              if info.jpeg_ring_name == writer.name), None)
            replaced = app.group.cameras.orchestrator.camera_statuses[camera_id].replaced_count.value
            writes.setdefault(camera_id, {})[kwargs["frame_number"]] = (app.clock.now_ns(), replaced)
        return spy(writer, payload, **kwargs)

    monkeypatch.setattr(FrameRingWriter, "write", write)
    return writes


def start_group(monkeypatch, scripts, track=False):
    """The app context manager and the product gate, with the two seams."""
    absolute_schedules(monkeypatch)
    return product_gate(), capture_app(monkeypatch, scripts, track=track)


def group_frames(spies, camera_ids):
    """{camera_id: {ring frame_number: event}} and the frame numbers that each camera has."""
    frames = {cid: {e["frame_number"]: e for e in spies.of("jpeg", cid)} for cid in camera_ids}
    common = sorted(set.intersection(*(set(f) for f in frames.values())))
    return frames, common


def spread_numbers(frames, camera_ids, rounds):
    spreads = sorted((max(frames[c][r]["arrival_ns"] for c in camera_ids)
                      - min(frames[c][r]["arrival_ns"] for c in camera_ids)) / 1e6 for r in rounds)
    over = sum(s > PERIOD_NS / 1e6 for s in spreads)
    return dict(median=statistics.median(spreads), p95=spreads[int(0.95 * len(spreads))], max=spreads[-1],
                over=over, share=over / len(spreads), n=len(spreads))


def stale_rounds(frames, camera_ids, rounds):
    """Rounds in which a camera gave a frame that arrived before the previous group frame was complete
    (the frame was taken at the open of the round and held while the round waited, D26)."""
    stale = []
    for previous, current in zip(rounds, rounds[1:]):
        if current != previous + 1:
            continue
        closed = max(frames[c][previous]["arrival_ns"] for c in camera_ids)
        if any(frames[c][current]["arrival_ns"] <= closed for c in camera_ids):
            stale.append(current)
    return stale


def describe(numbers):
    return (f"median {numbers['median']:.1f} ms, p95 {numbers['p95']:.1f} ms, max {numbers['max']:.1f} ms, "
            f"{numbers['over']} of {numbers['n']} group frames ({numbers['share']:.1%}) above one frame period")


# ---------------------------------------------------------------------------
# GA-01: the spread inside a group frame
# ---------------------------------------------------------------------------

def test_ga_01_spread_inside_a_group_frame(monkeypatch):
    """GA-01, amendment sections 2 and 3: three cameras on the measured arrival model, 60 s of the
    virtual clock. The spread of arrival times inside each group frame has a median under 17 ms. At
    most 0.5 % of the group frames are above one frame period, and none is above one period plus one
    grid step (49.3 ms). The rule of today gives a median above 30 ms on this model.

    With a 16 ms delivery grid, a few group frames exceed one period also under the causal rule of the
    analysis (fewer than 0.5 %, max 34 to 41 ms). Thus the test uses that measured bound, not "no group
    frame above one frame period"."""
    gate, app_context = start_group(monkeypatch, measured_scripts(OWN_GRID_US))
    with app_context as app:
        exact_gate_clock(monkeypatch, app, gate)
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        app.wait_clock(60.0, "60 s of group frames")
        app.client.delete("/skellycam/camera/group/close/all")
        cids = app.factory.camera_ids
        frames, rounds = group_frames(spies, cids)
    numbers = spread_numbers(frames, cids, rounds[SETTLE_ROUNDS:])
    assert numbers["n"] >= 1500, f"too few group frames: {numbers['n']}"
    assert numbers["median"] < 17.0, f"spread too large: {describe(numbers)}"
    assert numbers["share"] <= 0.005, f"too many group frames above one frame period: {describe(numbers)}"
    assert numbers["max"] <= PERIOD_NS / 1e6 + 16.0, f"a group frame above one period plus one grid step: " \
                                                      f"{describe(numbers)}"


# ---------------------------------------------------------------------------
# GA-02: replaced frames equal the gaps; each camera gives its newest frame at the close
# ---------------------------------------------------------------------------

def test_ga_02_replaced_count_equals_the_gaps_and_the_rule_choice(monkeypatch):
    """GA-02, amendment section 3.3 [D27, W4, agent 49]: three cameras on ONE common 16 ms grid, so
    that arrivals tie and the loop drops many frames that it took and held. 60 s.

    (1) For each camera and each given frame r, the `replaced_count` of the status after frame r
    equals the sum of the gaps of `source_frame_number` from the first frame given in the gate to
    frame r (the loop sets it at each taken frame, 8.4).
    (2) The rule: round r closes at the latest of the first arrivals after the frames of round r - 1.
    Each camera gives the newest frame that arrived by then (or within one wait step after it, 4.3).
    The rule of today gives older frames: the test counts the rounds that differ."""
    gate, app_context = start_group(monkeypatch, measured_scripts(ONE_GRID_US))
    with app_context as app:
        exact_gate_clock(monkeypatch, app, gate)
        spies = Spies(monkeypatch, app)
        writes = record_writes(monkeypatch, app)
        ready_app_steps(app)
        app.wait_clock(60.0, "60 s of group frames")
        app.client.delete("/skellycam/camera/group/close/all")
        cids = app.factory.camera_ids
        frames, rounds = group_frames(spies, cids)
        delivered = {cid: app.factory.logs[cid].frames for cid in cids}
    assert len(rounds) >= 1500, len(rounds)
    for cid in cids:
        sfns = [frames[cid][r]["sfn"] for r in sorted(frames[cid])]
        numbers = sorted(writes[cid])
        wrong = [(r, writes[cid][numbers[i + 1]][1], sfn_gaps(sfns[:i + 1]))
                 for i, r in enumerate(numbers[:-1]) if writes[cid][numbers[i + 1]][1] != sfn_gaps(sfns[:i + 1])]
        assert not wrong, f"camera {cid}: replaced_count differs from the gaps at {len(wrong)} frames, " \
                          f"first (frame, status, gaps): {wrong[:3]}"
    arrivals = {cid: [delivered[cid][k][0] for k in range(len(delivered[cid]))] for cid in cids}
    differ = []
    for previous, current in zip(rounds[SETTLE_ROUNDS:], rounds[SETTLE_ROUNDS + 1:]):
        closed = max(arrivals[cid][frames[cid][previous]["sfn"] + 1] for cid in cids)
        for cid in cids:
            newest = bisect.bisect_right(arrivals[cid], closed) - 1
            latest = bisect.bisect_right(arrivals[cid], closed + POLL_NS) - 1
            given = frames[cid][current]["sfn"]
            if not newest <= given <= latest:
                differ.append((current, cid, given, newest))
    checked = len(rounds) - SETTLE_ROUNDS - 1
    assert not differ, f"{len({d[0] for d in differ})} of {checked} rounds do not give the newest frame at the " \
                       f"close; first (round, camera, given sfn, newest sfn): {differ[:3]}"


# ---------------------------------------------------------------------------
# GA-03, GA-04: a camera that dies or stalls does not hold the round
# ---------------------------------------------------------------------------

def test_ga_03_a_camera_that_dies_mid_round_does_not_hold_the_round(monkeypatch):
    """GA-03, amendment section 4.2 [D38, agent 82]: after 10 s, the late camera gives device removed.
    It is `dead`. The round that waited for its fresh frame closes at its death, not before (the live
    cameras did not give their frames of that round before the error) and within 100 ms after it (the
    limit of T-CAP-108). The rule of today gives the live frames of that round at its open, before
    the error."""
    gate, app_context = start_group(monkeypatch, measured_scripts(OWN_GRID_US))
    with app_context as app:
        exact_gate_clock(monkeypatch, app, gate)
        spies = Spies(monkeypatch, app)
        writes = record_writes(monkeypatch, app)
        ready_app_steps(app)
        cids = app.factory.camera_ids
        dying, live = cids[1], (cids[0], cids[2])
        app.wait_clock(10.0, "10 s of group frames")
        source = app.factory.sources[dying]
        source.remove_now()
        app.wait_state(dying, "dead")
        app.wait_clock(1.0, "1 s after the death")
        app.client.delete("/skellycam/camera/group/close/all")
        removed = source.removed_frame
        schedule = source.script.arrivals_ns
        t_error = schedule[bisect.bisect_right(schedule, app.factory.logs[dying].frames[removed][0])]
        last_round = max(e["frame_number"] for e in spies.of("jpeg", dying))
    held_round = last_round + 1
    for cid in live:
        assert held_round in writes[cid], f"camera {cid} has no group frame after the death"
        t_write = writes[cid][held_round][0]
        assert t_error <= t_write, f"camera {cid} gave its frame of round {held_round} " \
                                   f"{(t_error - t_write) / 1e6:.1f} ms before the error of the dead camera"
        assert t_write <= t_error + LIMIT_NS, f"camera {cid}: round {held_round} closed " \
                                              f"{(t_write - t_error) / 1e6:.1f} ms after the error"


def test_ga_04_a_camera_that_stalls_is_dead_after_2_s_and_the_round_closes(monkeypatch):
    """GA-04, amendment section 4.2 [D38, 9.5]: after 10 s, the late camera stops delivering. It is
    `dead` 2.0 to 2.25 s after its last arrival (T-CAP-36). The round that waited for it closes then:
    each live camera gives a frame that arrived at most one period plus one grid step before the 2 s
    point, its newest frame. The rule of today gives the frames that the live cameras took at the open
    of that round, about 2 s older."""
    gate, app_context = start_group(monkeypatch, measured_scripts(OWN_GRID_US), track=True)
    with app_context as app:
        exact_gate_clock(monkeypatch, app, gate)
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        cids = app.factory.camera_ids
        stalled, live = cids[1], (cids[0], cids[2])
        app.wait_clock(10.0, "10 s of group frames")
        app.factory.sources[stalled].stop_now()
        app.wait_state(stalled, "dead")
        app.wait_clock(1.0, "1 s after the death")
        app.client.delete("/skellycam/camera/group/close/all")
        delivered = app.factory.logs[stalled].frames
        t_last = delivered[max(delivered)][0]
        t_dead = app.tracker.first(stalled, "dead")
        last_round = max(e["frame_number"] for e in spies.of("jpeg", stalled))
        frames = {cid: {e["frame_number"]: e for e in spies.of("jpeg", cid)} for cid in live}
    assert t_dead is not None
    assert 2.0 <= (t_dead - t_last) / 1e9 <= 2.25, f"dead {(t_dead - t_last) / 1e9:.3f} s after the last arrival"
    held_round = last_round + 1
    for cid in live:
        arrival = frames[cid][held_round]["arrival_ns"]
        age = (t_last + 2 * 10**9 - arrival) / 1e6
        assert age <= PERIOD_NS / 1e6 + 16.0, f"camera {cid}: its frame of round {held_round} arrived {age:.0f} ms " \
                                               f"before the 2 s point"


# ---------------------------------------------------------------------------
# GA-05: 29.97 fps with two 30 fps cameras
# ---------------------------------------------------------------------------

def test_ga_05_rate_class_30_replaced_counts(monkeypatch):
    """GA-05, amendment section 4.1 [U15, D18, 7.5]: a fake at 30000/1001 and two fakes at 30/1, with
    exact periods (no grid) and fixed phases (0, 10 and 20 ms). Over 100 s from the first gate frame:
    each 30 fps camera has 3 (+/-1) replaced frames, as U15 predicts (1001/30 s = 33.4 s for each);
    the 29.97 fps camera has none; the group gives 2997 (+/-2) frames. These counts are the same under
    the rule of today. The test fails today because the 30 fps cameras give held frames: no camera may
    give a frame that arrived before the previous group frame was complete."""
    modes = [((640, 480, 30000, 1001, "MJPG"),), ((640, 480, 30, 1, "MJPG"),), ((640, 480, 30, 1, "MJPG"),)]
    scripts = []
    for mode, period, phase in zip(modes, (1001e6 / 30, 1e9 / 30, 1e9 / 30), (0, 10_000_000, 20_000_000)):
        script = FakeScript(modes=mode)
        script.arrivals_ns = exact_schedule(period, phase)
        scripts.append(script)
    gate, app_context = start_group(monkeypatch, scripts)
    with app_context as app:
        exact_gate_clock(monkeypatch, app, gate)
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        cids = app.factory.camera_ids
        app.wait(lambda: spies.of("jpeg", cids[1]), "the first gate frame")
        t0 = spies.of("jpeg", cids[1])[0]["arrival_ns"]
        app.wait(lambda: app.clock.now_ns() > t0 + 101 * 10**9, "100 simulated seconds")
        app.client.delete("/skellycam/camera/group/close/all")
        frames, rounds = group_frames(spies, cids)
    t1 = t0 + 100 * 10**9
    replaced = {}
    for cid in cids:
        sfns = [frames[cid][r]["sfn"] for r in rounds if t0 <= frames[cid][r]["arrival_ns"] <= t1]
        replaced[cid] = sfn_gaps(sfns)
    in_window = [r for r in rounds if t0 <= frames[cids[1]][r]["arrival_ns"] <= t1]
    assert replaced[cids[0]] == 0, f"the 29.97 fps camera lost frames: {replaced}"
    for cid in cids[1:]:
        assert 2 <= replaced[cid] <= 4, f"camera {cid}: {replaced[cid]} frames replaced in 100 s (U15: 3)"
    assert abs(len(in_window) - 2997) <= 2, f"{len(in_window)} group frames in 100 s"
    stale = stale_rounds(frames, cids, rounds)
    assert not stale, f"{len(stale)} of {len(rounds) - 1} group frames hold a frame that arrived before the " \
                      f"previous group frame was complete; replaced counts {replaced}"


# ---------------------------------------------------------------------------
# GA-06: frame order and one frame of each camera
# ---------------------------------------------------------------------------

def test_ga_06_frame_order_and_one_frame_of_each_camera(monkeypatch):
    """GA-06, amendment section 3.2: the measured arrival model, 60 s. Each group frame holds exactly
    one frame of each live camera; no camera gives a frame older than one it gave before; and no camera
    gives a frame that arrived before the previous group frame was complete (the frame is fresh). The
    rule of today breaks the last point in most rounds (61 to 73 % in the analysis)."""
    gate, app_context = start_group(monkeypatch, measured_scripts(OWN_GRID_US))
    with app_context as app:
        exact_gate_clock(monkeypatch, app, gate)
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        app.wait_clock(60.0, "60 s of group frames")
        app.client.delete("/skellycam/camera/group/close/all")
        cids = app.factory.camera_ids
        frames, rounds = group_frames(spies, cids)
    numbers = [set(frames[cid]) for cid in cids]
    last = min(max(n) for n in numbers)
    assert all(set(range(last + 1)) <= n for n in numbers), "a group frame lacks a camera"
    for cid in cids:
        sfns = [frames[cid][r]["sfn"] for r in sorted(frames[cid])]
        assert all(b > a for a, b in zip(sfns, sfns[1:])), f"camera {cid} gave an older frame"
    stale = stale_rounds(frames, cids, rounds[:last + 1])
    assert not stale, f"{len(stale)} of {last} group frames ({len(stale) / last:.0%}) hold a frame that arrived " \
                      f"before the previous group frame was complete"


# ---------------------------------------------------------------------------
# GA-07: no busy loop while a camera waits for a slow camera
# ---------------------------------------------------------------------------

def test_ga_07_a_waiting_camera_uses_no_busy_loop(monkeypatch):
    """GA-07, amendment section 3.5 [ring 8.10, 4.3]: two camera processes on the real clock. The second
    fake delivers 30 fps for 300 frames (the start-up), then 1 fps, so the first camera waits about
    1 s for each round. Over 10 s of the slow part: the process of the first camera uses under 2 % of
    one core (the limit of T-CAP-49), and in each group frame the frame of the first camera arrived at
    most one period plus 16 ms before the frame of the slow camera (its newest frame at the close).
    The rule of today gives the frame that the first camera took at the open, about 1 s older."""
    scripts = [FakeScript(), FakeScript(intervals_ms=(100 / 3,) * 300 + (1000.0,) * 60)]
    with capture_logs(), capture_app(monkeypatch, scripts, workers="process") as app:
        ready_app_steps(app)
        waiting, slow = app.factory.camera_ids
        rings = {cid: RingWatcher(app.ring_name(cid)) for cid in (waiting, slow)}
        try:
            def slow_part():
                times = [f[1] for f in rings[slow].frames]
                return len(times) >= 2 and times[-1] - times[-2] > 900_000_000
            app.wait(slow_part, "the slow part")
            cpu = psutil.Process(app.worker(waiting).worker.pid)
            before, t0 = cpu.cpu_times(), time.perf_counter()
            time.sleep(10.0)
            after, t1 = cpu.cpu_times(), time.perf_counter()
        finally:
            for ring in rings.values():
                ring.stop()
    used = (after.user - before.user + after.system - before.system) / (t1 - t0)
    by_round = {cid: {f[0]: f[1] for f in ring.frames} for cid, ring in rings.items()}
    slow_rounds = sorted(r for r in by_round[slow] if r - 1 in by_round[slow] and r in by_round[waiting]
                         and by_round[slow][r] - by_round[slow][r - 1] > 900_000_000)
    assert len(slow_rounds) >= 8, f"too few slow rounds: {len(slow_rounds)}"
    ages = [(by_round[slow][r] - by_round[waiting][r]) / 1e6 for r in slow_rounds]
    old = [a for a in ages if abs(a) > PERIOD_NS / 1e6 + 16.0]
    logging.getLogger(__name__).info(f"GA-07: CPU {used:.2%} of one core; ages {ages}")
    assert used < 0.02, f"the waiting camera process used {used:.1%} of one core"
    assert not old, f"{len(old)} of {len(ages)} group frames: the waiting camera's frame is far from the slow " \
                    f"camera's frame (ms): {old[:5]}"
