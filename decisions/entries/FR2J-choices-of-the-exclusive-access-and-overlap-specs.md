# FR2J — Choices of the agent in the specs of exclusive access, the overlaps with freemocap and the light data

**Status:** absorbed into [`specs/windows-capture.md#21-exclusive-access-of-a-camera`](../../specs/windows-capture.md#21-exclusive-access-of-a-camera),
[`specs/unix-capture.md#413-exclusive-access-of-a-camera-lands-with-phase-7`](../../specs/unix-capture.md#413-exclusive-access-of-a-camera-lands-with-phase-7),
[`specs/unix-capture.md#69-tests-of-exclusive-access-413-lands-with-phase-7`](../../specs/unix-capture.md#69-tests-of-exclusive-access-413-lands-with-phase-7),
[`specs/certify.md#20-exclusive-access-the-public-calls-for-freemocap-and-the-light-data`](../../specs/certify.md#20-exclusive-access-the-public-calls-for-freemocap-and-the-light-data),
2026-11-25 (commit to dom/exclusive-access-spec; was accepted, 2026-11-25 (user, Q813 of
ADR-5PAR); was proposed, 2026-11-25 (agent; the spec lane of Q799 of [ADR-AA4X](AA4X-decisions-of-the-user-on-exclusive-access-of-a-camera.md); commit to dom/exclusive-access-spec)).

## Decision

The specs mark each item as [X n]: section 21 of `windows-capture.md`, 4.13 and 6.9 of `unix-capture.md`, and
section 20 of `certify.md`.

1. The source compares the process ids of a report with its own process id: in one group only the camera process
   of a camera attaches to it. Risk: at a reopen, the dying process of the earlier open counts as another process
   (T-CAP-145).
2. The newest report of the monitor whose link gives the `camera_id` of the camera is the report of that camera.
3. A process name is the image file name with no folder (`QueryFullProcessImageNameW`, last part); else "another
   program".
4. With no activity monitor, the source works as before; the diagnostics key `activity_monitor` is `false`.
5. The wait for the first report before the open is at most 1 s [NV, certify reports `first_report_ms`]; a second
   check after the first frame.
6. `0xC00D3704` with no holder seen stays `camera-in-use`, with the reason "in use by another program, or not
   enough USB bandwidth"; it becomes `usb-bandwidth` only after a certify result (the monitor missed Signal on
   2026-11-10).
7. A record start while a streaming other process is on a camera gets HTTP 409 that names the camera and the process.
8. A change notice within 1 s of an own set of the same control is own.
9. A difference at the take start gives a warning and a mark; the source does not set the value back.
10. Withdrawn: the read of 11.4 during a take is question QX-1 for the user (`windows-capture.md` 21.6).
11. The take marks are the manifest warnings `camera_shared` (`rows=<a>-<b> by=<name>`) and `camera_control_changed`
    (`row=<k> control=<name>`).
12. The status warnings `camera_attached`, `camera_shared`, `control_changed_by_other`, and their texts.
13. The test IDs start at T-CAP-130: T-CAP-114 is on `dom/integration` (fix lane 8), and `dom/gate-rule` (not merged)
    uses T-CAP-114 to T-CAP-122.
14. Linux reads `/proc` only after an in-use failure.
15. The new diagnostics keys `priority_record`, `ctrl_events_other`, `holder_names`, `config_locked`,
    `in_use_flag_changes`, and the call name `s-priority`.
16. macOS holds `lockForConfiguration` from the start to the close, not only during a take, so that the settings also
    hold in the preview and no other process can take the lock between takes.
17. `certify_plan` gives the line before a run in `details.before_run`.
18. `<label>:opens` gets `others_attached` (a count); the report holds no name of a program outside the allow-list of
    `system:camera-apps`.
19. Withdrawn: the holder of `<label>:in-use:other-program` is question QX-2 for the user (`certify.md` 20.3).
20. The script of `<label>:in-use-mid-take` (join at 3 s, a control set at 5 s, leave at 7 s), its 2 s warning limit,
    and its `not-run` `no-shared-mode` before Windows build 26100.
21. The script of `probe:<model>:hog-mode`, and `replug` when hog mode does not go back to -1.
22. The name and the form `is_model_checked(device, *, os_key=None) -> bool`.
23. A progress message holds each ended check of the run and `details` as far as it goes.
24. The name `CameraGroup.create_without_cameras(camera_configs, *, rings=None)`; a group counts as open only with a
    `CameraManager`.
25. `details.limits_uncalibrated` lists `dark_luma`.
26. The reason code `no-frame`.
27. `system:kernel` drops only `kernel_major` and `kernel_minor`, and keeps the driver facts.
28. The new reason codes `not-refused`, `holder-failed`, `not-warned`, `not-marked`, `no-shared-mode`,
    `hog-not-settable` and `hog-not-exclusive`, and the tests T-CAP-130 to T-CAP-145, T-UNX-102 to T-UNX-108 and
    T-CERT-135 to T-CERT-148.
29. The activity monitor is created and started before step 3 of `windows-capture.md` 6.2.
30. The control monitor adds its subscription before `Start` and starts after the first frame.
31. Linux: a value event of a dependent control within 1 s of an own set of its master is own; flags-only events and
    value events of a control in auto are ignored.
32. Linux: the subscription comes after `STREAMON`, one `VIDIOC_SUBSCRIBE_EVENT` for each listed control.
33. macOS: a failed `lockForConfiguration` (-11817) gives `camera-in-use` with `busy_call` `lock-config`.
34. On Windows 11 22621 or later the control mark is a pass condition of `<label>:in-use-mid-take`.
35. The Linux variant of `<label>:in-use-mid-take`: the holder calls `VIDIOC_S_CTRL`; `EBUSY` or a mark passes.
36. The order in phase F: `<label>:in-use`, then the two checks of `certify.md` 20.3, then the 60 fps checks.
37. The read-backs compare the auto flag always and the value only for a control in manual.

## Reason

Each item fills a gap that the decisions of the user leave. Items 3, 14 and 18 keep private data (a folder with the
user name, another program's name) out of the logs and the reports. Items 6, 19 and 20 turn an inferred fact into a
certify check. Item 16 is the simpler rule of the two, and it covers the take.

## Open work

[open-work.md](../open-work.md)
