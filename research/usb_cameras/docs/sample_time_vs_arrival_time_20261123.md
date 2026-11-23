# Sample time against arrival time: what each one is good for

Date: 2026-11-23. Status: a summary of earlier measurements, written for the stage that removes the lockstep
gate. No new measurement was made for this note. Every number comes from
[timestamp_accuracy_options.md](timestamp_accuracy_options.md) (2026-11-09) unless a line says otherwise.

## 1. Summary

- For the **time** of a frame, the sample time is not more accurate than the arrival time. Fitted to a regular
  grid, arrival times reach about 0.5 ms against flash ground truth. That equals the camera's own clock.
- For the **identity** of a frame (which frame slot it belongs to), the sample time is better. It stays correct
  when frames arrive in a burst or are read late. Arrival does not.
- The sample time has an offset per camera model. It must not be compared between cameras without a
  calibration.
- skellycam stores both times for each frame. Today it uses only the arrival time, as taken, with no fit.
- When the lockstep gate goes, frames are paired by time. Then the choice of time matters much more than it
  does today. Section 7 lists what that stage must decide.

## 2. The three times of a frame

| Name | Who makes it | Clock | Available |
|---|---|---|---|
| Arrival time | skellycam reads the computer's steady clock when the frame reaches it (`arrival_ns`) | The computer's clock (QPC on Windows, `perf_counter_ns`) | Always, on each capture route |
| Sample time | The camera driver puts it on the frame (`sample_ns`) | Windows: not declared by the driver. Measured: the same time base as the computer's clock. Linux: the driver declares it (not tested by us). | Media Foundation: yes. OpenCV with Media Foundation: only with one special output setting, otherwise invented at exact 33.333 ms steps. OpenCV with DirectShow: no. |
| Camera clock (UVC PTS and SCR) | The camera, in the header of each USB packet | The camera's internal clock | Windows: only with a registry value for each camera (`MetadataBufferSizeInKB0`, an administrator step, no driver change), or with a swapped driver. Not used by skellycam. |

The user decided on 2026-11-09: no registry value and no camera-clock route in the product ("tier 0 only").
The camera clock was used once, only as a measuring reference, and the registry value was removed after it.

## 3. What was measured on Windows

Cameras: Logitech C922, Logitech C930e, Razer Kiyo Pro, one generic camera (4c4a:4a55). All on Windows with
Media Foundation.

**The time base of the sample time.** Arrival minus sample time sits at about 0.3 to 1 ms, or at about
16 ms, on the C922, the C930e and the Kiyo Pro. A different clock would give a large or wandering difference.
On the generic camera the sample time is one frame (32 ms) earlier than on the others. No camera showed a
wall-clock or a camera-internal time base.

**Accuracy against a flash seen by the camera** (one 30 s run, 85 and 95 ground-truth frames; standard
deviation in ms; the floor of the method is about 0.5 ms):

| Method | C922 | C930e |
|---|---|---|
| Sample time, as given | 4.8 | 5.2 |
| Arrival time, as taken | 4.7 | 5.1 |
| Sample times fitted to a grid, robust, whole run | 0.56 | 2.0 |
| Arrival times fitted to a grid, robust, whole run | 0.56 | 0.54 |
| Arrival fit: period from the whole run, offset from a 10 s window | 0.56 | 0.52 |
| Arrival fit, causal (10 s trailing window) | 0.57 | 3.3 |
| Reference: camera clock mapped to the arrival envelope | 0.56 | 0.54 |

**What the table says:**

- As given, both times have about 5 ms of noise. Neither is a good stamp alone.
- The grid fit is the step that gives the accuracy, and it works on arrival alone.
- The camera clock gives the same result as the arrival fit. The test could not show a gain from it.
- The C930e has a latency that is 22.8 ms higher in its first 2 s. That pulls a fit on sample time and a
  causal fit off. A whole-run fit or a two-stage fit on arrival is not affected.

**Frame identity.**

- Kiyo Pro: frames sometimes arrive in bursts. Slots taken from arrival alone gave 3 false drops and a grid
  29.7 ms away from the camera clock. Slots taken from sample time were correct.
- The sample time stays correct for a frame that the reader took late (measured on OpenCV with Media
  Foundation; inferred for the native source).
- Generic camera: a false drop at frame 0 from sample time.
- No scored run contained a real dropped frame. So the detection of a real drop is not tested.

**Drift of the camera against the computer's clock:** C922 -1.6 ppm, C930e +39.9 ppm. At 40 ppm, a 10 min
take is 24 ms off if a nominal period is used. A whole-run fit removes it.

## 4. What each time is good for

| Use | Arrival time | Sample time |
|---|---|---|
| Time of a frame, after a grid fit | Good: about 0.5 ms | Same on the C922, worse on the C930e |
| Time of a frame, with no fit | About 5 ms of noise | About 5 ms of noise |
| Compare two cameras | Good: one clock in one computer | Not safe: an offset per model (the generic camera is 32 ms early) |
| Decide the slot of a frame in a burst or after a late read | Wrong by up to one frame | Good |
| Always available | Yes | No |

**The method the study recommended:** take the frame slots from the sample time where it exists, then fit the
times of the slots on arrival. This gives the burst benefit without the offset per camera.

## 5. What skellycam does today (integration branch, 2026-11-23)

- Each frame carries `arrival_ns` and `sample_ns` in the ring header and in the timing CSV of a take. The
  native Windows source keeps a sample time only when it is within 200 ms before the arrival.
- The recording, the stop statistics and the sync use the arrival time, as taken. No slotting and no grid fit
  exist in the product. [Not checked today: that the player timeline reads the arrival column.]
- Cameras are paired by the lockstep gate (one frame for each camera for each tick), not by time. In a burst
  the app keeps the newest frame and counts the older one as replaced. So a burst costs a frame; it does not
  pair wrong frames. But the second frame of a burst gets an arrival time that is wrong by up to one frame.
- Certify compares the two times on each run: no sample time later than its arrival, and the 95th percentile
  of the difference inside a limit. The user decided on 2026-11-23 (Q585) that the full gate on Windows needs
  only these two measured checks, because Windows does not declare the clock of the sample time.

## 6. Limits of the evidence

- Flash ground truth: one 30 s run, two cameras, about 90 frames each.
- Kiyo Pro: one scored run. Its camera clock deviates about 1 ms from a grid; the cause is open.
- All runs are 30 to 75 s. Long takes, and the two period modes of the C930e (about 0.12 % apart), are not
  tested.
- The constant delay from light to stamp for each model is not measured. Flash hints at several ms up to
  about 30 ms between models. The strobe rig that can measure it is built in firmware and never used.
- Nothing is measured on Linux or macOS.
- The free-run log of 2026-11-20 ([free_run_log_20261120.md](free_run_log_20261120.md)) found that the camera
  clocks disagree by one frame for the Kiyo Pro, and asked for an LED or moving-board test before any design.

## 7. For the stage "remove the lockstep gate"

Review this note at the start of that stage. Without the gate, frames are paired by time, so these points
become design decisions:

1. Which time pairs the frames: arrival as taken, arrival after a fit, or slots from sample time with times
   from arrival (the two-part method of section 4).
2. If a fit is used: where it runs (live and causal, or when the take ends). The causal fit was poor on the
   C930e (3.3 ms), so a live pairing rule cannot rely on it in the first seconds.
3. How a burst is handled when no gate replaces frames: both frames of a burst are then kept, and the second
   one has a wrong arrival time. The sample time is the only value that separates them.
4. The offset of the sample time per model (32 ms on the generic camera): a calibration per model, or never
   compare sample times between cameras.
5. A source with no sample time (OpenCV routes, possibly Linux and macOS): the rule must work on arrival
   alone.
6. The tests that must come first: an LED or moving-board run with all cameras for the true offset between
   cameras; a run with real dropped frames; takes of 10 to 30 min.
7. Whether the recording format needs a new field (a slot number or a fitted time), or whether the two stored
   times are enough for a later tool.
