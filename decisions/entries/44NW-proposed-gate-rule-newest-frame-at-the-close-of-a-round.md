# 44NW — Proposed gate rule: the newest frame at the close of a round

**Status:** proposed, 2026-11-21 (agent; waits for the user).

## Decision

An agent proposes a change of D26 of [`specs/windows-capture.md`](../../specs/windows-capture.md).
The user decides it. Until then, D26 stays in force, and the accepted spec does not change.

- The rule: a round closes when each camera in the gate has a frame newer than the frame that it
  gave last. The close time is the latest arrival time of those first fresh frames, or the time of a
  gate change (a camera leaves the gate, or an unpause). Each camera gives its newest frame that
  arrived by the close time, and keeps a later frame for the next round. The other frames count as
  replaced.
- `replaced_count` stays equal to the gaps of `source_frame_number` from the first frame that the
  camera gives in the gate (D27, W4). The loop adds the frames that it took and did not give.
- Across the camera processes: each camera has a `fresh` pair (round, arrival time) that only its
  own process writes, and a `wake` event that the others set. The group has a `round_close` pair
  (round, close time) that the first camera to see the close writes, and a `gate_changed_ns` time.
  A waiting camera waits on its event for at most 50 ms. No lock is held across a wait, and the gate
  is not polled each 1 ms.
- A pull source (OpenCV) gives the first frame after its own give. Linux and macOS keep a spread
  like today until phase 7.
- The pairing stays by arrival time (D28). Pairing by sample time is a later, separate step.
- The agent recommends a trial before the decision: a product-code implementation on a branch that
  is not merged, with a log of each delivered frame, and a three-camera run against the rule of
  today.

The amendment [`specs/windows-capture-gate-amendment.md`](../../specs/windows-capture-gate-amendment.md)
states the rule in full, each interaction, the old and new text of each changed sentence, the costs
and risks, and nine questions for the user (section A-9). The failing tests GA-01 to GA-09 are in
`skellycam/tests/capture/test_gate_amendment.py`. `skellycam/tests/capture/conftest.py` deselects
them unless `SKELLYCAM_GATE_AMENDMENT=1`.

## Reason

- The first hardware run of step 3a measured a spread of arrival times inside one group frame of
  35.0 to 39.1 ms at the median. 60 to 77 % of the group frames were above one frame period.
- Under D26, a camera takes its newest frame when a round opens and holds it while it waits for the
  slowest camera.
- On the real arrival times of four runs, the rule gives a median spread of 13.0 to 18.9 ms. The
  cost is 1 to 3 more lost frames per camera per minute, and up to about 10 in the worst phase.
- The close time is necessary: without it, a frame that arrives in the wake delay replaces the frame
  of the round, and wake delays of 5 to 10 ms lose 27 to 68 frames per camera per 1,800.

## Evidence

- `research/usb_cameras/docs/hardware_run_3a_20261120.md` and
  `research/usb_cameras/docs/camera_spread_analysis_20261120.md` (research checkout, branch
  `dom/research`; not committed on 2026-11-21).
- An independent review replayed the rule on the real arrival times of four runs, with phase sweeps,
  wake delays and a model of the protocol (scratch scripts, not kept). The amendment, section A-2,
  gives its ranges.
- The fake-source tests GA-01 to GA-09 on the virtual clock: the gate of today fails GA-01 to GA-08;
  a throwaway implementation of the rule outside the repository passes all of them. The amendment,
  section A-8, gives each result.

## Alternatives rejected

- Keep D26: it keeps about 20 ms of spread that a causal rule removes.
- The first wording of this proposal (give the frame that is newest when the camera sees the close):
  it loses frames with each wake delay.
- The protocol of today with a frame that arrived before the open dropped: it needs a tuned back-off
  constant and loses 26 to 52 frames per camera per 1,800 with wake delays up to 5 ms.
- Pair by sample time now: the true clock is not known.
