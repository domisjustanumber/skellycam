"""GA-01 to GA-09: failing tests of the PROPOSED gate rule (specs/windows-capture-gate-amendment.md).

The rule is proposed. The user has not decided it. These tests have the marker `gate_amendment`.
`conftest.py` deselects them unless `SKELLYCAM_GATE_AMENDMENT=1` is set, also when the command line
gives its own `-m`. The CI selections also leave them out. Run them with
`SKELLYCAM_GATE_AMENDMENT=1 uv run pytest skellycam/tests/capture -m gate_amendment`.
GA-01 to GA-08 fail on the gate rule of today (D26) with the measured value in the message. GA-09
(the pull source) passes today: it guards the pull-source rule of the amendment (A-3.6).

The proposed rule: a round closes when every camera in the gate has a frame newer than the one it
gave last. The close time is the latest arrival time of those first fresh frames. Each camera gives
its newest frame that arrived by the close time, and keeps a later frame for the next round. The
other frames that it took count as replaced.

Arrival model (GA-01 to GA-08), from `research/usb_cameras/docs/camera_spread_analysis_20261120.md`
(branch `dom/research`): three cameras with true frame periods of 33.333, 33.313 and 33.279 ms. Each
camera delivers on its own 16 ms grid, so its intervals are 32 or 48 ms. The phase set is fixed:
true phase 0 for each camera, grid phases 0, 5 and 10 ms, and the second camera 32 ms late, with
its sample time 32.3 ms before its arrival (the Kiyo Pro of T-CAP-59). The schedules are absolute on
the virtual clock, so the start-up order does not change the phases. The bounds of the tests follow
from the model of the rule for THIS phase set (amendment A-8). Other phases give other numbers, and
a hardware run has its own, wider pass rule (A-9).

Two seams of this file only (no change of `fake_source.py` or `capture_session.py`):

- `absolute_schedules`: a fake whose script has `arrivals_ns` takes its next arrival from that list.
- `gate_clock`: the virtual clock does not move while a loop that waits at the gate could pass it
  now. With `delay_ms`, each camera sees the open gate (the close) a random time from 0 to `delay_ms`
  later, in virtual time: the wake delay of a real camera process.
"""

import bisect
import logging
import math
import random
import statistics
import threading
import time

import numpy as np
import psutil
import pytest

from skellycam.tests.capture.capture_session import (
    CaptureApp, OpenCVFakeFactory, RingWatcher, Spies, capture_app, capture_logs, ready_app_steps, sfn_gaps)
from skellycam.tests.capture.fake_source import FakeScript, FakeSource, VirtualClock

pytestmark = pytest.mark.gate_amendment

START_NS = VirtualClock.START_NS
PERIOD_NS = 1e9 / 30
PERIOD_MS = PERIOD_NS / 1e6
GRID_US = 16_000
SCHEDULE_S = 200  # longer than each run
PERIODS_US = (33_333, 33_313, 33_279)  # the camera periods of section 4 of the analysis
LATE_US = (0, 32_000, 0)  # the Kiyo Pro delivers about 32 ms after its sample time
SAMPLE_OFFSET_MS = (-0.33, -32.3, -0.33)  # T-CAP-59: arrival minus sample time
OWN_GRID_US = (0, 5_000, 10_000)  # each camera on its own 16 ms grid, as the cameras of the hardware run
DELAY_GRID_US = (0, 2_500, 5_000)  # GA-08: arrivals 2.5 ms apart, the smallest offset of the review
POLL_NS = 1_000_000  # GA-02: a loop may see the close up to 1 ms late
LIMIT_NS = 100_000_000  # the limit of T-CAP-108: no gap above 100 ms after a camera dies
SETTLE_ROUNDS = 30
LOSS_BOUND = 6  # A-6: lost frames per camera per 1,800 with wake delays up to 10 ms (the review replay)


# ---------------------------------------------------------------------------
# Arrival schedules and seams
# ---------------------------------------------------------------------------

def grid_schedule(period_us, grid_us, late_us, phase_us=0):
    """Absolute arrival times (ns): the true time phase + k * period, delivered at the next point of the
    camera's own 16 ms grid, plus the delivery delay. A grid of None gives the true times."""
    out, k = [], 0
    while True:
        true_us = phase_us + k * period_us
        arrival_us = (math.ceil((true_us - grid_us) / GRID_US) * GRID_US + grid_us if grid_us is not None
                      else true_us) + late_us
        out.append(START_NS + round(arrival_us * 1000))
        if arrival_us > SCHEDULE_S * 1_000_000:
            return tuple(out)
        k += 1


def scripts_for(periods_us, grids_us, lates_us, phases_us=(0, 0, 0), modes=None, offsets=SAMPLE_OFFSET_MS):
    scripts = []
    for index, (period, grid, late, phase) in enumerate(zip(periods_us, grids_us, lates_us, phases_us)):
        script = FakeScript(sample_offset_ms=offsets[index]) if modes is None else FakeScript(modes=modes[index])
        script.arrivals_ns = grid_schedule(period, grid, late, phase)
        scripts.append(script)
    return scripts


def measured_scripts(grids_us=OWN_GRID_US):
    return scripts_for(PERIODS_US, grids_us, LATE_US)


def absolute_schedules(monkeypatch):
    original = FakeSource._interval_ns

    def interval(self, previous_arrival):
        arrivals = getattr(self.script, "arrivals_ns", None)
        if arrivals is None:
            return original(self, previous_arrival)
        return arrivals[bisect.bisect_right(arrivals, previous_arrival)] - previous_arrival

    monkeypatch.setattr(FakeSource, "_interval_ns", interval)


def product_gate():
    """The gate of the product, before `capture_app` wraps it with its clock probe. The loop module is
    imported first, as `capture_app` does."""
    import skellycam.core.camera.capture.camera_loop  # noqa: F401
    from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator

    return CameraOrchestrator.should_grab_by_id


def gate_clock(monkeypatch, app, should_grab, delay_ms=0.0, seed=1):
    """The two parts of the `gate_clock` seam (module docstring)."""
    from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator

    at_gate = {}  # thread ident -> (orchestrator, camera_id)
    seen = {}  # (camera_id, gate count) -> the virtual time at which the camera sees the open gate
    rng = random.Random(seed)
    probe = CameraOrchestrator.should_grab_by_id
    clock = app.clock

    def record(self, camera_id):
        at_gate[threading.get_ident()] = (self, camera_id)
        if delay_ms and should_grab(self, camera_id):
            key = (camera_id, self.camera_statuses[camera_id].frame_count.value)
            if key not in seen:
                seen[key] = clock.now_ns() + round(rng.uniform(0.0, delay_ms) * 1e6)
            clock.wait_until(seen[key])
        return probe(self, camera_id)

    monkeypatch.setattr(CameraOrchestrator, "should_grab_by_id", record)
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
    """The app context manager and the product gate, with the schedule seam."""
    absolute_schedules(monkeypatch)
    return product_gate(), capture_app(monkeypatch, scripts, track=track)


def run_group(monkeypatch, scripts, seconds, delay_ms=0.0, writes=False):
    """Run the group for `seconds` of the virtual clock. Gives (camera_ids, frames, rounds, delivered, writes)."""
    gate, app_context = start_group(monkeypatch, scripts)
    with app_context as app:
        gate_clock(monkeypatch, app, gate, delay_ms)
        spies = Spies(monkeypatch, app)
        written = record_writes(monkeypatch, app) if writes else None
        ready_app_steps(app)
        app.wait_clock(seconds, f"{seconds} s of group frames")
        app.client.delete("/skellycam/camera/group/close/all")
        cids = app.factory.camera_ids
        frames, rounds = group_frames(spies, cids)
        delivered = {cid: [app.factory.logs[cid].frames[k][0] for k in range(len(app.factory.logs[cid].frames))]
                     for cid in cids}
    return cids, frames, rounds, delivered, written


def group_frames(spies, camera_ids):
    """{camera_id: {ring frame_number: event}} and the frame numbers that each camera has."""
    frames = {cid: {e["frame_number"]: e for e in spies.of("jpeg", cid)} for cid in camera_ids}
    common = sorted(set.intersection(*(set(f) for f in frames.values())))
    return frames, common


def spread_numbers(frames, camera_ids, rounds):
    spreads = sorted((max(frames[c][r]["arrival_ns"] for c in camera_ids)
                      - min(frames[c][r]["arrival_ns"] for c in camera_ids)) / 1e6 for r in rounds)
    over = sum(s > PERIOD_MS for s in spreads)
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


def not_newest_by_close(frames, delivered, camera_ids, rounds):
    """(round, camera) pairs where the camera gave a frame older than its newest frame that arrived by
    the latest arrival of the group frame. With the rule, that latest arrival is the close time."""
    out = []
    for r in rounds:
        closed = max(frames[c][r]["arrival_ns"] for c in camera_ids)
        for c in camera_ids:
            if bisect.bisect_right(delivered[c], closed) - 1 > frames[c][r]["sfn"]:
                out.append((r, c))
    return out


def lost_per_1800(frames, camera_ids, rounds):
    """Lost (replaced) frames of each camera between the given frames of `rounds`, per 1,800 rounds."""
    scale = 1800 / max(len(rounds) - 1, 1)
    return {c: sfn_gaps([frames[c][r]["sfn"] for r in rounds]) * scale for c in camera_ids}


def check_status_counts(frames, writes, camera_ids):
    """The `replaced_count` of the status after given frame r equals the gaps from the first given frame."""
    for cid in camera_ids:
        numbers = sorted(writes[cid])
        sfns = [frames[cid][r]["sfn"] for r in numbers]
        wrong = [(r, writes[cid][numbers[i + 1]][1], sfn_gaps(sfns[:i + 1]))
                 for i, r in enumerate(numbers[:-1]) if writes[cid][numbers[i + 1]][1] != sfn_gaps(sfns[:i + 1])]
        assert not wrong, f"camera {cid}: replaced_count differs from the gaps at {len(wrong)} frames, " \
                          f"first (frame, status, gaps): {wrong[:3]}"


def describe(numbers):
    return (f"median {numbers['median']:.1f} ms, p95 {numbers['p95']:.1f} ms, max {numbers['max']:.1f} ms, "
            f"{numbers['over']} of {numbers['n']} group frames ({numbers['share']:.1%}) above one frame period")


# ---------------------------------------------------------------------------
# GA-01: the spread inside a group frame
# ---------------------------------------------------------------------------

def test_ga_01_spread_inside_a_group_frame(monkeypatch):
    """GA-01, amendment A-2, A-3 and A-8: the arrival model with its fixed phase set, 60 s of the virtual
    clock, no wake delay. For this phase set, the offline model of the rule gives a spread of 11.0 /
    27.0 / 38.0 ms (median / p95 / max) and 0.3 % of the group frames above one period. The test
    allows: median at most 12 ms, p95 at most 28 ms, max at most 40 ms, at most 0.5 % above one
    period. The rule of today gives 38.0 / 54.0 / 70.0 ms and 64.5 % on the same set.

    These bounds hold for this phase set only. Real cameras gave 13.0 to 18.9 ms at the median across
    four runs (A-2). A hardware run has its own, wider pass rule (A-9)."""
    cids, frames, rounds, _, _ = run_group(monkeypatch, measured_scripts(), 60.0)
    numbers = spread_numbers(frames, cids, rounds[SETTLE_ROUNDS:])
    assert numbers["n"] >= 1500, f"too few group frames: {numbers['n']}"
    assert numbers["median"] <= 12.0 and numbers["p95"] <= 28.0, f"spread too large: {describe(numbers)}"
    assert numbers["share"] <= 0.005, f"too many group frames above one frame period: {describe(numbers)}"
    assert numbers["max"] <= 40.0, f"a group frame above 40 ms: {describe(numbers)}"


# ---------------------------------------------------------------------------
# GA-02: the rule at zero delay; replaced frames equal the gaps
# ---------------------------------------------------------------------------

def test_ga_02_newest_frame_by_the_close_time_and_the_status_count(monkeypatch):
    """GA-02, amendment A-3.1 to A-3.3 [D27, W4, agent 49]: the arrival model, 60 s, no wake delay.

    (1) For each camera and each given frame r, the `replaced_count` of the status after frame r
    equals the sum of the gaps of `source_frame_number` from the first frame given in the gate to
    frame r (the loop sets it at each given frame, 8.4).
    (2) The rule: the close time of round r is the latest of the first arrivals after the frames of
    round r - 1. Each camera gives its newest frame that arrived by the close time (1 ms is allowed for
    the order of the threads). The rule of today gives older frames: the test counts the rounds."""
    cids, frames, rounds, delivered, writes = run_group(monkeypatch, measured_scripts(), 60.0, writes=True)
    assert len(rounds) >= 1500, len(rounds)
    check_status_counts(frames, writes, cids)
    differ = []
    for previous, current in zip(rounds[SETTLE_ROUNDS:], rounds[SETTLE_ROUNDS + 1:]):
        closed = max(delivered[cid][frames[cid][previous]["sfn"] + 1] for cid in cids)
        for cid in cids:
            newest = bisect.bisect_right(delivered[cid], closed) - 1
            latest = bisect.bisect_right(delivered[cid], closed + POLL_NS) - 1
            given = frames[cid][current]["sfn"]
            if not newest <= given <= latest:
                differ.append((current, cid, given, newest))
    checked = len(rounds) - SETTLE_ROUNDS - 1
    assert not differ, f"{len({d[0] for d in differ})} of {checked} rounds do not give the newest frame by the " \
                       f"close time; first (round, camera, given sfn, newest sfn): {differ[:3]}"


# ---------------------------------------------------------------------------
# GA-03, GA-04: a camera that dies or stalls does not hold the round
# ---------------------------------------------------------------------------

def test_ga_03_a_camera_that_dies_mid_round_does_not_hold_the_round(monkeypatch):
    """GA-03, amendment A-4.2 [D38, agent 82]: after 10 s, the late camera gives device removed. It is
    `dead`. The round that waited for its fresh frame closes at its death, not before (the live cameras
    did not give their frames of that round before the error) and within 100 ms after it (the limit of
    T-CAP-108). The rule of today gives the live frames of that round at its open, before the error."""
    gate, app_context = start_group(monkeypatch, measured_scripts())
    with app_context as app:
        gate_clock(monkeypatch, app, gate)
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
    """GA-04, amendment A-4.2 [D38, 9.5]: after 10 s, the late camera stops delivering. It is `dead` 2.0
    to 2.25 s after its last arrival (T-CAP-36). The round that waited for it closes then, with the time
    of the death as its close time: each live camera gives a frame that arrived at most one period plus
    one grid step before the 2 s point. The rule of today gives the frames that the live cameras took
    at the open of that round, about 2 s older."""
    gate, app_context = start_group(monkeypatch, measured_scripts(), track=True)
    with app_context as app:
        gate_clock(monkeypatch, app, gate)
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
        assert age <= PERIOD_MS + 16.0, f"camera {cid}: its frame of round {held_round} arrived {age:.0f} ms " \
                                        f"before the 2 s point"


# ---------------------------------------------------------------------------
# GA-05: 29.97 fps with two 30 fps cameras, on the delivery grid
# ---------------------------------------------------------------------------

RC30_PERIODS_US = (1001e3 / 30, 1e6 / 30, 1e6 / 30)
RC30_PHASES_US = (0, 10_000, 20_000)


def rule_replay(delivered, camera_ids, first):
    """The rule at zero delay, replayed on the delivered arrival times from the given frames `first` of
    one round: the close time is the latest next arrival; each camera takes its newest frame by then."""
    last, out = dict(first), [dict(first)]
    while all(last[c] + 1 < len(delivered[c]) for c in camera_ids):
        closed = max(delivered[c][last[c] + 1] for c in camera_ids)
        last = {c: bisect.bisect_right(delivered[c], closed) - 1 for c in camera_ids}
        out.append(dict(last))
    return out


def test_ga_05_rate_class_30_replaced_counts(monkeypatch):
    """GA-05, amendment A-4.1 [U15, D18, 7.5]: a fake at 30000/1001 and two fakes at 30/1, each on its
    own 16 ms grid (0, 5 and 10 ms) with true phases 0, 10 and 20 ms. Over 100 s from the first gate
    frame, the replaced frames of each camera equal those of the rule replayed offline on the same
    arrival times (+/-1). With the grid, the 29.97 fps camera also loses frames, and a 30 fps camera can
    lose more than the 3 of the warning text of U15 (A-4.1 gives the numbers). The group gives 2997
    (+/-3) frames. No camera gives a frame that arrived before the previous group frame was complete:
    the rule of today fails here."""
    modes = [((640, 480, 30000, 1001, "MJPG"),), ((640, 480, 30, 1, "MJPG"),), ((640, 480, 30, 1, "MJPG"),)]
    scripts = scripts_for(RC30_PERIODS_US, OWN_GRID_US, (0, 0, 0), RC30_PHASES_US, modes=modes)
    gate, app_context = start_group(monkeypatch, scripts)
    with app_context as app:
        gate_clock(monkeypatch, app, gate)
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        cids = app.factory.camera_ids
        app.wait(lambda: spies.of("jpeg", cids[1]), "the first gate frame")
        t0 = spies.of("jpeg", cids[1])[0]["arrival_ns"]
        app.wait(lambda: app.clock.now_ns() > t0 + 101 * 10**9, "100 simulated seconds")
        app.client.delete("/skellycam/camera/group/close/all")
        frames, rounds = group_frames(spies, cids)
        delivered = {cid: [app.factory.logs[cid].frames[k][0] for k in range(len(app.factory.logs[cid].frames))]
                     for cid in cids}
    t1 = t0 + 100 * 10**9
    in_window = [r for r in rounds if t0 <= frames[cids[1]][r]["arrival_ns"] <= t1]
    replaced = tuple(sfn_gaps([frames[cid][r]["sfn"] for r in in_window]) for cid in cids)
    replay = rule_replay(delivered, cids, {cid: frames[cid][rounds[0]]["sfn"] for cid in cids})
    model_rounds = [rnd for rnd in replay if t0 <= delivered[cids[1]][rnd[cids[1]]] <= t1]
    expected = tuple(sfn_gaps([rnd[cid] for rnd in model_rounds]) for cid in cids)
    logging.getLogger(__name__).info(f"GA-05: replaced {replaced}, model {expected}, rounds {len(in_window)}")
    assert all(abs(got - want) <= 1 for got, want in zip(replaced, expected)),         f"replaced frames in 100 s {replaced}; the rule replayed on the same arrivals gives {expected}"
    assert abs(len(in_window) - 2997) <= 3, f"{len(in_window)} group frames in 100 s"
    stale = stale_rounds(frames, cids, rounds)
    assert not stale, f"{len(stale)} of {len(rounds) - 1} group frames hold a frame that arrived before the "                       f"previous group frame was complete; replaced frames {replaced}, model {expected}"


# ---------------------------------------------------------------------------
# GA-06: frame order and one frame of each camera
# ---------------------------------------------------------------------------

def test_ga_06_frame_order_and_one_frame_of_each_camera(monkeypatch):
    """GA-06, amendment A-3.2: the arrival model, 60 s. Each group frame holds exactly one frame of each
    live camera; no camera gives a frame older than one it gave before; and no camera gives a frame that
    arrived before the previous group frame was complete (the frame is fresh). The rule of today breaks
    the last point in most rounds (61 to 73 % in the analysis)."""
    cids, frames, rounds, _, _ = run_group(monkeypatch, measured_scripts(), 60.0)
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
    """GA-07, amendment A-3.5 [ring 8.10, 4.3]: two camera processes on the real clock. The second
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
    old = [a for a in ages if abs(a) > PERIOD_MS + 16.0]
    logging.getLogger(__name__).info(f"GA-07: CPU {used:.2%} of one core; ages {ages}")
    assert used < 0.02, f"the waiting camera process used {used:.1%} of one core"
    assert not old, f"{len(old)} of {len(ages)} group frames: the waiting camera's frame is far from the slow " \
                    f"camera's frame (ms): {old[:5]}"


# ---------------------------------------------------------------------------
# GA-08: a wake delay does not cost frames
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("delay_ms", [5.0, 10.0], ids=["wake delay up to 5 ms", "wake delay up to 10 ms"])
def test_ga_08_a_wake_delay_does_not_cost_frames(monkeypatch, delay_ms):
    """GA-08, amendment A-3.2, A-3.5 and A-6: the arrival model with grid phases 0, 2.5 and 5 ms (so that
    the arrivals of two cameras can be closer than the delay), 60 s, and each camera sees each close a
    random 0 to `delay_ms` later (virtual time). With the close time of A-3.5, a frame that arrives
    in the delay is kept for the next round, not given:

    (1) each camera loses at most 2 frames per 1,800 rounds more than the rule at zero delay, replayed
    on the same arrival times, and at most 6 (the bound of the review replay on the real arrival times,
    where the first wording of the rule lost 27 to 33 at 5 ms and 62 to 68 at 10 ms);
    (2) the `replaced_count` of the status equals the gaps at each given frame;
    (3) in at most 6 rounds per 1,800 for each camera, a camera gives a frame older than its newest
    frame that arrived by the latest arrival of the group frame (the close time). Such a round needs
    two arrivals of one camera in its wake delay, and the waiting place holds one frame.
    The rule of today loses 2 frames or fewer here, but it fails (3) in most rounds."""
    cids, frames, rounds, delivered, writes = run_group(monkeypatch, measured_scripts(DELAY_GRID_US), 60.0, delay_ms,
                                                         writes=True)
    settled = rounds[SETTLE_ROUNDS:]
    assert len(settled) >= 1500, len(settled)
    lost = lost_per_1800(frames, cids, settled)
    replay = rule_replay(delivered, cids, {cid: frames[cid][settled[0]]["sfn"] for cid in cids})
    end = {cid: frames[cid][settled[-1]]["sfn"] for cid in cids}
    replay = [rnd for rnd in replay if all(rnd[c] <= end[c] for c in cids)]
    zero = {c: sfn_gaps([rnd[c] for rnd in replay]) * 1800 / max(len(replay) - 1, 1) for c in cids}
    over = {c: round(lost[c] - zero[c], 1) for c in cids}
    assert max(over.values()) <= 2.0 and max(lost.values()) <= LOSS_BOUND, \
        f"lost frames per camera per 1,800: { {c: round(v, 1) for c, v in lost.items()} }; at zero delay " \
        f"{ {c: round(v, 1) for c, v in zero.items()} }"
    check_status_counts(frames, writes, cids)
    older = not_newest_by_close(frames, delivered, cids, settled)
    per_camera = {c: sum(1 for _, cc in older if cc == c) * 1800 / len(settled) for c in cids}
    assert max(per_camera.values()) <= LOSS_BOUND, \
        f"rounds per 1,800 that give an older frame than the newest by the close: " \
        f"{ {c: round(v, 1) for c, v in per_camera.items()} }; first {older[:3]}"


# ---------------------------------------------------------------------------
# GA-09: a pull source (OpenCV)
# ---------------------------------------------------------------------------

def test_ga_09_a_pull_source_reads_one_frame_for_each_round(monkeypatch):
    """GA-09, amendment A-3.6: two OpenCV fakes (pull sources) in one group on the virtual clock, 20 s.
    The loop reads one frame after its own give, holds it and gives it at the close. It never reads a
    pull source while it holds a frame. Thus for each camera: `source_frame_number` has no gap between
    given frames, and `replaced_count` stays 0. This test passes on the rule of today. It fails on an
    implementation that reads a pull source while it holds, as for a push source."""
    factory = OpenCVFakeFactory(monkeypatch, count=2)
    app = CaptureApp(monkeypatch, factory)
    try:
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        app.wait_clock(20.0, "20 s of group frames")
        cids = factory.camera_ids
        replaced = {cid: app.status(cid)["replaced_count"] for cid in cids}
        app.client.delete("/skellycam/camera/group/close/all")
        frames, rounds = group_frames(spies, cids)
    finally:
        app.close()
    assert len(rounds) >= 500, len(rounds)
    for cid in cids:
        sfns = [frames[cid][r]["sfn"] for r in rounds]
        assert sfn_gaps(sfns) == 0, f"camera {cid}: the loop dropped {sfn_gaps(sfns)} frames of a pull source"
    assert replaced == {cid: 0 for cid in cids}, replaced
