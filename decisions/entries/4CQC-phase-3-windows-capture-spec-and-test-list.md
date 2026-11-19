# 4CQC — Phase 3 spec and test list: Windows native capture (proposed)

**Status:** proposed, 2026-11-19 (agent; waits for the user).

## Decision

[`specs/windows-capture.md`](../../specs/windows-capture.md) is proposed as the spec of phase 3, with
its test list T-CAP-01 to T-CAP-79. It follows the decisions D1 to D49 of
[ADR-EN7A](EN7A-phase-3-windows-capture-decisions.md), the ring spec and the plan. It waits for the
acceptance of the user. No product code and no test code is written before that.

An agent made these choices where the sources leave a gap. Section 18 of the spec states each one in
full, and the body marks each one [agent n]:

1. Module layout and names (section 3).
2. Fake source in `skellycam/tests/capture/`; marker `camera_hardware`, `SKELLYCAM_HARDWARE=1`.
3. `set_controls({})` reads only.
4. Reuse `WaitingPlace` of the ring package.
5. Ring `frame_number` counts taken frames; the gate count continues; a rejoining camera takes the
   group count.
6. `newer_frame_waiting=False` while the gate exists.
7. `arrival_ns` in both grab stamps of the old frame record.
8. Decode only recorded frames or for a BGR ring; a flagged frame repeats the last image.
9. The old recorder gets the mode rate.
10. `sample_ns = 100 x GetSampleTime`, checked by T-CAP-59.
11. `driver_error` is `False` for Media Foundation.
12. Open the device whose hashed link equals `camera_id`.
13. Hash the lower-case link.
14. 5 s per bounded call; 15 s from the open to the end of the rate check.
15. HRESULT sets for "in use" and "device removed".
16. On a hang: report, finish the files, `os._exit`; the main process sees a camera failure.
17. Detection in a short-lived child process.
18. Rates rounded to 2 decimal places.
19. `capture_modes`: fields, order, no synthesized NV12.
20. Group rate rule before the open (Media Foundation) or after it (OpenCV); a refusal fails the apply.
21. State names, status fields, `camera_failures`.
22. A camera that fails at start ends its process.
23. A stall in `starting` is `failed`.
24. Unselect is `use_this_camera: false`.
25. Recording only when every selected camera is `ready`; HTTP 409.
26. Rate through `source_frame_number` differences.
27. No early decision at start-up; a new change restarts the check.
28. Slow warning rule during a recording.
29. `RECOMMEND` in the shared loop before the read-back.
30. Config names `gain`, `gain_auto`, `focus`, `focus_auto`.
31. Exposure status from 3a, gain and focus from 3c; read each second.
32. Camera data in the recording info JSON until phase 5.
33. Fixed warning text of D37; the record start response does not change.
34. Stage names.
35. Reason `{type}: {message}`; diagnostics to the log.
36. First failure kept per camera.
37. 3b: `input_range`, short raw frames flagged, BGR for the old recorder.
38. Done lists of 3b and 3c.
39. `SKELLYCAM_WINDOWS_CAPTURE` is the setting of D8.
40. CI file, runner labels, paths, late load of `mfplat.dll`.
41. Comparison run: three cameras, 60 s each, criteria on the native run.
42. Pass thresholds of the test table.
43. The main process reads the error pipes.
44. A dead camera outside a recording counts as failed.
45. MTA threads; `MFStartup` per camera process.

Questions for the user (section 19 of the spec; "yes" accepts the recommendation):

1. The OpenCV source on Windows finds its DirectShow index by the device instance of the link.
2. No burned-in stamp and no 30-slow-frame reopen on any OS from 3a.
3. The criteria of D48 item 3 apply to the native run; the OpenCV run is the reference.
4. With a dead camera, multi-frame rows continue with the cameras that are alive.
5. D38 also applies without a recording; dead counts as failed.
6. A group with different mode rates fails the whole apply.
7. H.264 is listed in `capture_modes` with `selectable: false`.
8. The first failure is kept per camera; one failure does not stop the group.

## Reason

- D3: a spec and a test list before any code. The user reviews it.
- Each choice is the smallest that the spec needs to be complete. Each question is a point where two
  readings are possible and the choice matters to the user.

## Open work

See [open-work.md](../open-work.md).
