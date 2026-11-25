# Research on exclusive use of a camera (2026-11-25)

This file holds the evidence of
[ADR-AA4X](../entries/AA4X-decisions-of-the-user-on-exclusive-access-of-a-camera.md). A sub-agent made it on
2026-11-25, read only, with no camera open. Tags: **[documented]** means a primary source says it; **[observed]**
means our own evidence shows it; **[inferred]** means reasoning that is not checked. The specs carry an inferred
fact only as [NV], with the certify check that verifies it.

## Findings

| OS | Second app streaming | Others changing controls | Seeing who holds it |
|---|---|---|---|
| Windows | One controlling source at a time; any number of shared readers can join [documented S1]. A second Media Foundation open of a held C930e got `0xC00D3704` at the first sample, and the running stream was not disturbed [observed: `research/usb_cameras/docs/windows_results_20261112.md` §1.2, `windows_results_20261113.md` §2.4]. | Shared readers cannot change the media type or ExtendedCameraControl, but can change the legacy controls (exposure, gain, focus) and the extension units [documented S1]; that nothing stops it is [inferred]. `MFCreateCameraControlMonitor` reports changes by another app, Windows 11 22621 or later [documented S6, S7]. | `MFCreateSensorActivityMonitor` (Windows 10 1703 or later) lists each attached process with its id, streaming state and mode [documented S2 to S4]. It showed LogiTuneAgent on all four cameras, attached and not streaming [observed: `windows_results_20261110.md` §9]. It reports again "when a new report is available" [documented S5]; that it fires on each join is [inferred]. The ConsentStore registry did not change in a run [observed]. |
| Linux | The first handle that allocates buffers owns the stream; others get `EBUSY` [documented S9, S10]. | `VIDIOC_S_PRIORITY` RECORD blocks control, format and stream calls of other handles with `EBUSY` [documented S11, S12]. The raw `UVCIOC_CTRL_QUERY` gets no priority check [documented S10]. `V4L2_EVENT_CTRL` goes to each subscriber except the one that made the change [documented S14]; the feedback flag is cited from memory [S15]. | `/proc/*/fd` names processes of the same user only [documented S13]. |
| macOS | No AVFoundation API refuses a second app [documented S16, S17]. CoreMediaIO hog mode exists [documented S18]; that a UVC camera lets a client set it is [inferred]. | `lockForConfiguration` blocks configuration by other processes (-11817) [documented S16, S20]; raw UVC requests through IOKit are not covered [inferred]. | `isInUseByAnotherApplication` is a yes or no and is observable [documented S17]; a process id exists only for a hog or master holder [documented S18]. |

Not checked: whether DirectShow clients go through Frame Server; what a second MediaCapture app in exclusive mode
gets; the page of S15. The kernel facts come from the master branch, not from a released kernel.

The code of `dom/integration` at `cf40e5657` used none of these: no activity monitor, no control monitor, no
priority lock, no configuration lock, and certify passed `shared`. The in-use set of `errors.py` was
`0xC00D3704`, `0xC00D3EA3`, `0x80070964` and `0x800700AA`; it did not hold `0x80070020`.

## Sources

- S1 https://learn.microsoft.com/en-us/windows/win32/medfound/mf-devsource-attribute-frameserver-share-mode
- S2 https://learn.microsoft.com/en-us/windows/win32/api/mfidl/nn-mfidl-imfsensoractivitymonitor
- S3 https://learn.microsoft.com/en-us/windows/win32/api/mfidl/nn-mfidl-imfsensorprocessactivity
- S4 https://learn.microsoft.com/en-us/windows/win32/api/mfidl/ne-mfidl-mfsensordevicemode
- S5 https://learn.microsoft.com/en-us/windows/win32/api/mfidl/nf-mfidl-imfsensoractivitiesreportcallback-onactivitiesreport
- S6 https://learn.microsoft.com/en-us/windows/win32/api/mfidl/nn-mfidl-imfcameracontrolnotify
- S7 https://learn.microsoft.com/en-us/windows/win32/api/mfidl/nf-mfidl-imfcameracontrolmonitor-addcontrolsubscription
- S8 https://learn.microsoft.com/en-us/uwp/api/windows.media.capture.mediacapturesharingmode
- S9 https://docs.kernel.org/userspace-api/media/v4l/open.html
- S10 https://github.com/torvalds/linux/blob/master/drivers/media/usb/uvc/uvc_v4l2.c
- S11 https://docs.kernel.org/userspace-api/media/v4l/vidioc-g-priority.html
- S12 https://github.com/torvalds/linux/blob/master/drivers/media/v4l2-core/v4l2-ioctl.c, with `v4l2-dev.c` and
  `uvc_driver.c`
- S13 https://man7.org/linux/man-pages/man5/proc_pid_fd.5.html
- S14 https://github.com/torvalds/linux/blob/master/drivers/media/usb/uvc/uvc_ctrl.c
- S15 https://docs.kernel.org/userspace-api/media/v4l/vidioc-subscribe-event.html (not fetched)
- S16 https://developer.apple.com/documentation/avfoundation/avcapturedevice/lockforconfiguration()
- S17 https://developer.apple.com/documentation/avfoundation/avcapturedevice/isinusebyanotherapplication
- S18 `CMIOHardwareDevice.h` of the macOS SDK (the MacOSX11.3 SDK copy at github.com/phracker/MacOSX-SDKs)
- S19 https://developer.apple.com/documentation/avfoundation/averror-swift.struct/code/deviceinusebyanotherapplication
- S20 https://developer.apple.com/documentation/avfoundation/averror-swift.struct/code/devicelockedforconfigurationbyanotherprocess
