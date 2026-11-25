# FR2J — Choices of the agent in the specs of exclusive access, the overlaps with freemocap and the light data

**Status:** proposed, 2026-11-25 (agent; the spec lane of Q799 of
[ADR-AA4X](AA4X-decisions-of-the-user-on-exclusive-access-of-a-camera.md); commit to dom/exclusive-access-spec).

## Decision

The specs mark each item as [X n]: section 21 of `windows-capture.md`, 4.13 and 6.9 of `unix-capture.md`, and
section 20 of `certify.md`.

1. The source compares the process ids of a report with its own process id: in one group only the camera process
   of a camera attaches to it.
2. The newest report of the monitor whose link gives the `camera_id` of the camera is the report of that camera.
3. A process name is the image file name with no folder (`QueryFullProcessImageNameW`, last part); else "another
   program".
4. With no activity monitor, the source works as before; the diagnostics key `activity_monitor` is `false`.
5. The wait for the first report before the open is at most 1 s; a second check after the first frame.
6. `0xC00D3704` with no other process gives `usb-bandwidth`, with the reason text of 21.4 item 4.
7. A record start while a streaming other process is on a camera gets HTTP 409 that names the camera and the process.
8. A change notice within 1 s of an own set of the same control is own.
9. A difference at the take start gives a warning and a mark; the source does not set the value back.
10. The read of 11.4, one time each second, is not used to find a change.
11. The take marks are the manifest warnings `camera_shared` (`rows=<a>-<b> by=<name>`) and `camera_control_changed`
    (`row=<k> control=<name>`).
12. The status warnings `camera_attached`, `camera_shared`, `control_changed_by_other`, and their texts.
13. The test IDs T-CAP-130 to T-CAP-140 leave room for T-CAP-114 to T-CAP-122 of branches that are not merged.
14. Linux reads `/proc` only after an in-use failure.
15. The new diagnostics keys `priority_record`, `ctrl_events_other`, `holder_names`, `config_locked`,
    `in_use_flag_changes`, and the call name `s-priority`.
16. macOS holds `lockForConfiguration` from the start to the close, not only during a take, so that the settings also
    hold in the preview and no other process can take the lock between takes.
17. `certify_plan` gives the line before a run in `details.before_run`.
18. `<label>:opens` gets `others_attached` (a count); the report holds no name of a program outside the allow-list of
    `system:camera-apps`.
19. The holder of `<label>:in-use:other-program` is OpenCV (`CAP_DSHOW`, `CAP_V4L2`, `CAP_AVFOUNDATION`), so the check
    also shows whether the activity monitor sees a DirectShow client.
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
    `hog-not-settable` and `hog-not-exclusive`, and the tests T-UNX-102 to T-UNX-108 and T-CERT-135 to T-CERT-148.

## Reason

Each item fills a gap that the decisions of the user leave. Items 3, 14 and 18 keep private data (a folder with the
user name, another program's name) out of the logs and the reports. Items 6, 19 and 20 turn an inferred fact into a
certify check. Item 16 is the simpler rule of the two, and it covers the take.

## Open work

[open-work.md](../open-work.md)
