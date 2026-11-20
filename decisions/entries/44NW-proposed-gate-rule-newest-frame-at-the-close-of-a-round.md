# 44NW — Proposed gate rule: the newest frame at the close of a round

**Status:** proposed, 2026-11-21 (agent; waits for the user).

## Decision

An agent proposes a change of D26 of [`specs/windows-capture.md`](../../specs/windows-capture.md).
The user decides it. Until then, D26 stays in force, and the accepted spec does not change.

- The rule: a round closes when each camera in the gate has a frame newer than the frame that it
  gave last. Each camera then gives its newest frame. The frames that it took earlier count as
  replaced.
- `replaced_count` stays equal to the gaps of `source_frame_number` from the first frame that the
  camera gives in the gate (D27, W4). The loop adds the frames that it held and did not give.
- Across the camera processes: each camera has a shared `fresh_round` counter that only its own
  process writes, and a `wake` event that the others set. A camera that waits for the close waits on
  its event for at most 50 ms. No lock is held across a wait, and the gate is not polled each 1 ms.
- The pairing stays by arrival time (D28). Pairing by sample time is a later, separate step after an
  LED or moving-board test.

The amendment [`specs/windows-capture-gate-amendment.md`](../../specs/windows-capture-gate-amendment.md)
states the rule in full, each interaction, the old and new text of each changed sentence, the costs
and risks, and six questions for the user (section A-9). The failing tests GA-01 to GA-07 are in
`skellycam/tests/capture/test_gate_amendment.py`. Their marker `gate_amendment` keeps them out of the
default selection and the CI selections.

## Reason

- The first hardware run of step 3a measured a spread of arrival times inside one group frame of
  35 to 39 ms at the median and 51 to 55 ms at p95. 65 to 77 % of the group frames were above one
  frame period.
- Under D26, a camera takes its newest frame when a round opens and holds it while it waits for the
  slowest camera. The proposed rule reached the offline floor in the analysis: a median of 13 to
  14 ms and a p95 of 25 ms.

## Evidence

- `research/usb_cameras/docs/hardware_run_3a_20261120.md` and
  `research/usb_cameras/docs/camera_spread_analysis_20261120.md` (research checkout, branch
  `dom/research`; not committed on 2026-11-21).
- The fake-source tests GA-01 to GA-07 on the virtual clock, with the arrival model of the analysis:
  the gate of today gives a spread of 38.0 / 54.0 / 70.0 ms (median / p95 / max). A throwaway
  implementation outside the repository gives 11.0 / 27.0 / 38.0 ms and passes all seven tests. The
  amendment, section A-8, gives each result.

## Alternatives rejected

- Keep D26: it keeps about 23 ms of spread that a causal rule removes.
- Pair by sample time now: the true clock is not known. The Logitech sample time is stamped at
  delivery, and the Kiyo Pro sample time is 16 to 48 ms before its arrival.
