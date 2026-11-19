# 4CQC — Phase 3 spec and test list: Windows native capture (proposed)

**Status:** proposed, 2026-11-19 (agent; waits for the user).

## Decision

[`specs/windows-capture.md`](../../specs/windows-capture.md) is proposed as the spec of phase 3, with
its test list T-CAP-01 to T-CAP-91. It follows the decisions D1 to D49 of
[ADR-EN7A](EN7A-phase-3-windows-capture-decisions.md), the answers U1 to U15 of
[ADR-QKX1](QKX1-answers-of-the-user-to-the-phase-3-spec-questions.md), the ring spec and the plan.
It waits for the acceptance of the user. No product code and no test code is written before that.
The four revisions of 2026-11-19 apply the answers of the user and the fixes of an independent
reviews.

An agent made these choices where the sources leave a gap. Section 18 of the spec states each one in
full, and the body marks each one [agent n]:

1. Module layout and names.
2. Fake source; markers `camera_hardware`, `capture_local`; run rules of T-CAP-43 and T-CAP-76.
3. `set_controls({})` reads only.
4. The rules of `WaitingPlace`, with items 46 and 50.
5. Ring `frame_number` counts taken frames; the gate count continues.
6. `newer_frame_waiting=False` while the gate exists.
7. `arrival_ns` in both grab stamps.
8. Decode only recorded frames or for a BGR ring.
9. The old recorder gets the mode rate.
10. `sample_ns` and its `NO_SAMPLE_NS` rule.
11. `driver_error` is `False` for Media Foundation.
12. Open the device whose hashed link equals `camera_id`.
13. Hash the lower-case link.
14. 5 s per bounded call and first frame; the 15 s timer and its owner.
15. HRESULT sets for "in use" and "device removed".
16. On a hang: report, then `os._exit`; a camera failure for the main process.
17. Detection in a short-lived child process.
18. Rates rounded to 2 decimal places.
19. `capture_modes`: fields, order, no synthesized NV12.
20. The one-rate rule in the whole-request check, from the detection data.
21. State names, status fields, `camera_failures`.
22. Process ends of failed and dead cameras.
23. Device removed or a stall in `starting` is `failed`.
24. Unselect is `use_this_camera: false`.
25. Recording only when every selected camera is `ready`; one HTTP rule (422 or 409).
26. Rate through `source_frame_number` differences.
27. No early decision at start-up; a new change restarts the check.
28. Slow warning rule during a recording.
29. `RECOMMEND` in the shared loop; the config then holds `MANUAL`.
30. Config names `gain`, `gain_auto`, `focus`, `focus_auto`.
31. Exposure, gain and focus in the status from 3a, read each second.
32. Camera data in the recording info JSON until phase 5.
33. The `warnings` lists: one item form, the kind `auto_control`.
34. Stage names.
35. Reason `{type}: {message}`; diagnostics to the log.
36. 3b: `input_range`, short raw frames flagged, one shared BGR conversion.
37. Done lists of 3b and 3c.
38. `SKELLYCAM_WINDOWS_CAPTURE` is the setting of D8.
39. CI file, runner labels, test selection, late load of `mfplat.dll`.
40. Comparison run: three cameras, 60 s, today's OpenCV loop as the reference.
41. Pass thresholds of the test table.
42. The main process reads the error pipes.
43. MTA threads; `MFStartup` per camera process.
44. The config stores the read-back values.
45. The `starting`, `waiting` and `failed` cells of table 8.3.
46. A discontinuity moves from a replaced frame to the next frame.
47. The states that the gate counts.
48. Reason texts.
49. `replaced_count` from the first frame taken in the gate.
50. An error marker wakes the loop.
51. The state `waiting`.
52. `last_frame_number` is the gate count.
53. The field `reason` of `capture_modes` and its texts.
54. Relay details: a camera with no frame is left out; the header frame number.
55. HTTP 422 for a request more than 0.5 fps below the floor.
56. OpenCV one-rate check on the requested rates; real-rate differences warn only.
57. Auto chooses 29.97 when there is no 30.
58. The floor on the exact chosen mode rate; where each floor case is decided.
59. OpenCV and the floor after the open.
60. A hang while open gives `dead`, stage `streaming`.
61. The interim decode on the loop thread.
62. A stream error or end of stream: dead at once.
63. The kind `mixed_rate` and the interval in whole seconds.
64. A failed live change as a `warnings` item of the kind `control_change_failed`.

No question for the user is open. The user answered the last two questions on 2026-11-19 (U14 and
U15 of [ADR-QKX1](QKX1-answers-of-the-user-to-the-phase-3-spec-questions.md)).

## Reason

- D3: a spec and a test list before any code. The user reviews it.
- Each choice is the smallest that the spec needs to be complete. The user decided each point where
  two readings were possible and the choice mattered (U1 to U15).

## Open work

See [open-work.md](../open-work.md).
