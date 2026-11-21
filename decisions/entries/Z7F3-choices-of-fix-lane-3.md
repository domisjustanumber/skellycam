# Z7F3 — Choices of fix lane 3

**Status:** proposed, 2026-11-21 (agent; the supervisor gave the items, after real-camera runs).

## Decision

The supervisor gave the items. The agent chose these details:

1. The restore record of a camera that rounds. At the first read of an open, a control of the record takes its
   "before" value from the record when the camera reads the same auto flag as the value that this app set last,
   and, with auto off, a value not more than one step from that value. The step is `c_step` of the range of the
   control at this open (`GetRange` on Media Foundation). A control with no range, or with a step that is not
   above 0, needs the same value. `ControlRestore.read(state, steps)` gets the steps; the Media Foundation source
   reads the ranges before the first control read ([`unix-capture.md`](../../specs/unix-capture.md) 4.7).

## Reason

1. A Logitech C930e read back manual exposure -8 in the open that set it, and -7 at the next open (the user's
   real-camera run of 2026-11-21). The old rule needed the same value, so the record was dropped, and the close
   of the next open "restored" manual -7: the camera stayed in manual exposure after its process was killed. A
   Logitech C922 read back -8 in both opens. A rounding stays inside one step of the control. A value that another
   program set (T-UNX-92 (b): -3 against -7) is more than one step away, so it still stays.

## Consequences

1. A value that another program set to not more than one step from the last value of this app now takes the
   "before" values of the record (before: only exactly that value). On the exposure scale of Media Foundation
   (step 1, log2 seconds) that is a change of one stop.

## Evidence

1. Code facts: `ControlRestore.read` of `skellycam/core/camera/capture/source.py`; `_set_and_read` of
   `skellycam/core/camera/capture/media_foundation/source.py`. Tests: T-UNX-91 (the case "a camera that rounds",
   the fake field `reopen_shift`) and T-UNX-92 (d), (e) in `skellycam/tests/capture/test_restore.py`, and
   `test_t_unx_92_the_media_foundation_source_gives_the_step_of_get_range_to_the_restore_record`. Each failed on
   the old code for the rule itself (the camera stayed manual -6; the "before" value was the read value).

## Alternatives rejected

1. Record the value that the camera reads at the end of the open too: a killed process has no end of the open,
   and the C930e read -8 to the end of that open; the change came only at the new open. A fixed tolerance of 1:
   a control with a larger step (for example focus) would still lose its record.
