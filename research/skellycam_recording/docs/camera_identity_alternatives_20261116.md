## Summary

You don't need to fall back to the OS index. With item 44's real costs counted, it is the worst of the last-resort options. Almost every case that reaches it today exists only because skellycam reads identity from OpenCV's enumerator and not from the OS. For the few sources left over (software or virtual cameras with no device path), a session-scoped key, or refusing the camera, is better than a bare index.

Tags: **[R path]** from the research files, **[D source]** from documentation, **[C file:line]** from the code, **[I]** my inference.

### What skellycam has today (the same at HEAD and 169caf637)

- **No serial anywhere.** `CameraDeviceInfo` holds only the index, name, VID, PID, path and backend [C skellycam/core/device_detection/detect_cameras_devices.py:35-42].
- **The old key.** `camera_id` hashes the path; else `vid_pid_index`; else the index alone. It keeps 2 bytes of the hash [C :44-54].
- **Filtering.** Cameras whose name contains "virtual" are dropped. On Windows and Linux, so are cameras with no VID or PID [C :100-106].
- **One difference between the revisions.** 169caf637 also raised an error on colliding ids. HEAD dropped that check (`git diff 169caf637 HEAD`).
- **Windows backend.** It is DirectShow [C skellycam/core/camera/determine_backend.py, `determine_opencv_camera_backend`].
- **The "path" comes from cv2_enumerate_cameras 1.3.3** (`pyproject.toml:71` has the range `>=1.2.2`, against your pin rule):
  - **Windows:** the MSMF symbolic link or the DirectShow DevicePath. The index is the position in the list [C .venv/.../cv2_enumerate_cameras/windows_backend.py:32-34]. These paths are device-interface handles built from the instance ID, not port paths. The C930e got new ones after a driver rollback on the same port [R research/usb_cameras/REPORT.md findings 23; docs/usb_camera_report.md:114-115].
  - **Linux:** `/dev/videoN` [C linux_backend.py:61-97]. That is an enumeration number, which the research lists as unstable [R naming/camera_identity.py:27-29].
  - **macOS:** `AVCaptureDevice.uniqueID`. The index is the position after sorting by uniqueID [C macos_backend.py:57-71].

So filling the spec's `port_path` from today's `path` would give index-quality keys on Linux, labelled "port".

## 1. When a camera has neither a serial nor a port path

Columns: what the OS exposes and which API gives it / survives a reboot / survives a replug into the same port / survives a move to another port / tells a second identical camera apart.

| Case | OS | What the OS exposes, and the API | Reboot | Same port | Other port | 2nd identical |
|---|---|---|---|---|---|---|
| **(a) No USB serial.** C930e, Kiyo Pro and the generic camera have none; the C922 does [R usb_camera_report.md:100-107]. No Brio was measured. | Windows | `DEVPKEY_Device_LocationPaths` of the USB parent, read with cfgmgr32 without admin. The instance ID is `<parent-hash>&0&<port>`. The ContainerId is a generated v1 UUID, new for each port, whose node field looks like the host's network MAC address [R REPORT.md 22-23; PRIVACY_REVIEW_20261111.md:38,96] | Expected yes; the controlled test never ran [R usb_camera_report.md:118] | Yes. Measured over re-enumeration and a driver rollback [R REPORT.md 23] | No. A new instance and ContainerId for each port [R usb_camera_report.md:112] | Only by port. Swapping the cables can't be detected [R :100] |
| | Linux | sysfs devpath (`3-13.1.4`) plus the controller's PCI address; udev `ID_PATH` / `ID_PATH_WITH_USB_REVISION`; `/dev/v4l/by-path` [R results/agent_reports/plan_20261106/linux.md:258-276] | Yes if the bus number is dropped [D libcamera-devel 2020 review; R camera_identity.py:23] | Yes [I] | No | `by-path` tells them apart. `by-id` collides [R linux.md:258-259]. Plain `ID_PATH` can collide across an xHCI controller's USB 2 and USB 3 root hubs, which is why systemd v254 added the revision [R topology_linux.md:17] |
| | macOS | IOKit `locationID` of the `IOUSBHostDevice`. The uniqueID is the hex of `locationID<<32 \| VID<<16 \| PID` [R topology_macos.md:16; xplat_capture_plan.md:174] | Yes on built-in ports. The bus byte swapped across a reboot on controllers in Thunderbolt or PCIe enclosures [R topology_macos.md:189; D developer.apple.com/forums/thread/836729] | Yes | No | Yes, by locationID |
| **(b) The backend can't give the port, but the OS knows it** | Windows | OpenCV gives an interface path or an index, never LocationPaths. The OS path is reached from the symbolic link: device instance, then up to the USB parent, then LocationPaths [R camera_identity.py:138-157; capture_stack_options_plan.md:90]. PyAV dshow opens by index or name only [R capture_stack_options_plan.md:126] | As in (a) | | | |
| | Linux | OpenCV gives `/dev/videoN`. sysfs and udev hold the real path. A sandbox without `/sys` or `/run/udev` (Flatpak, Snap, containers) could hide it [I] | | | | |
| | macOS | AVFoundation gives the uniqueID (port-encoded) but no serial. The serial is in the IORegistry (`USB Serial Number`) [R xplat_capture_plan.md:174; D Apple forum thread 757573] | | | | |
| **(c) Not USB: built-in MIPI or ACPI camera** | Windows | Instance ID `ACPI\…` (or under the IPU driver) and an ACPI or PCI LocationPath. Many "built-in" laptop cameras are really USB on a fixed internal port, which is case (a) [I] | Yes. "A device instance ID is persistent across system restarts" [D learn.microsoft.com …/install/device-instance-ids] | n/a | n/a | Different firmware paths [I] |
| | Linux | libcamera camera ID, built from the firmware path (ACPI or device tree); `by-path` `platform-…` | Yes. Designed as "unique and persistent between reboots" [D libcamera-devel 2020-07, camera ID series] | n/a | n/a | Yes |
| | macOS | `uniqueID`. No locationID, except the T2 FaceTime camera on a virtual iBridge bus at `0x80200000` [R topology_macos.md:110] | Yes. Apple documents that it "persists on one system across device connections and disconnections, application restarts, and reboots" [D AVCaptureDevice.uniqueID docs, as quoted in forum thread 836729] | n/a | n/a | n/a |
| **(c) Virtual camera** (OBS, NDI, Windows 11 virtual camera, v4l2loopback, CMIO extension) | Windows | **MF virtual camera** (build 22000+): "keyed off the parameters passed in". It survives a reboot only with `MFVirtualCameraLifetime_System`; with `CurrentUser`, each user gets their own camera [D learn.microsoft.com MFCreateVirtualCamera]. **DirectShow filter cameras:** a CLSID and a name only, no DevicePath. openpnp falls back to `"<name> <index>"` for them [R prior_art/SURVEY.md:52] | MF: depends on the app. DirectShow: name and CLSID yes, index no | n/a | n/a | MF: per instance. DirectShow: no |
| | Linux | v4l2loopback: `bus_info` `platform:v4l2loopback-NNN`, a `card_label`, and a node number set by `video_nr` or else the first free one [D debian v4l2loopback.h; I] | Only if `video_nr` is pinned | n/a | n/a | Only by number |
| | macOS | `uniqueID`, chosen by the extension author. It may be the same on every machine [I, unverified] | Yes [D] | n/a | n/a | Unknown |
| **(c) Continuity Camera** | macOS | `uniqueID`. It may be tied to the paired iPhone [I, unverified] | Yes [D] | n/a | n/a | n/a |
| **(c) Capture card** | all | USB cards are case (a), often with a serial. PCIe cards have a PCI location path: Windows LocationPaths `PCIROOT(0)#PCI(..)`, Linux `by-path` `pci-0000:03:00.0` [I] | Yes while it stays in its slot [I] | n/a | Slot move: no | By slot |
| **(c) IP camera** | all | No OS capture device; skellycam has no path for one. An RTSP URL may carry the IP address and credentials. ONVIF `GetDeviceInformation` returns `SerialNumber` [D ONVIF Device Management spec] | Serial: yes | n/a | n/a | Serial: yes |

**A gap in form 1.** A serial is only safe when it is usable and unique. The research rule rejects empty serials, characters outside 0x21–0x7F, commas, placeholders such as `0001` or `0123456789`, a single repeated character, and a serial shared by two connected cameras of the same VID:PID [R naming/camera_identity.py:13-18, 41-67, 116-127]. SFF-752 has no such check, so two cheap cameras with the same placeholder serial would share a key.

**One unexplained result.** In the 11-12 run the C922's serial key changed after a natural replug, and the reason is hidden by the redaction [R docs/windows_results_20261112.md:493-494].

## 2. The alternatives

| Option | Cost in skellycam | How stable the key is | Collision risk | Privacy risk |
|---|---|---|---|---|
| **(i) Port path from the OS, not the backend** | **Windows:** cfgmgr32 by ctypes. Symbolic link → `DEVPKEY_Device_InstanceId` → walk up to `USB\VID_` → `LocationPaths[0]`, reduced to `PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.4`. The research code exists [R naming/camera_identity.py:84-92, win_identity_dump.py]; about 150–300 lines to port [I]. **Linux:** about 30 lines of sysfs (realpath of `/sys/class/video4linux/videoN/device`). **macOS:** parse the uniqueID (trivial), or read the IORegistry with pyobjc (moderate) | Port-stable. Measured on Windows across re-enumeration and a driver swap [R REPORT.md 23]. Reboot not measured. The macOS bus byte is unstable on Thunderbolt/PCIe controllers | None on one host if Linux keeps the USB revision. Identical PCs with a camera in the same port get the same key [I] | Low. Bus topology only. The privacy review keeps instance-ID hashes [R PRIVACY_REVIEW_20261111.md:96] |
| **(ii) An OS persistent ID as its own form** (macOS uniqueID for non-USB devices; Windows instance ID of an ACPI, PCI or SWD devnode; Linux libcamera ID) | Small once (i) exists. Needs a new `device` member, because SFT-717 recomputes the key from `device` [D skellyfileformat 72QQ item: "SFF-752 (key): SFT-717, against the `device` values"] | Reboot-stable by documentation (Apple, Microsoft, libcamera) | Two machines of the same model may share built-in IDs [I] | Mostly opaque. The ID of a Continuity Camera or a per-user virtual camera may point to a person's phone or account [I, unverified]. Never use a ContainerId (it can carry the MAC) [R PRIVACY_REVIEW_20261111.md:38] or a URL. Add the member to the DM9S 15b `fields` list |
| **(iii) A key the user assigns once** | User interface, a config store, and a match rule to find the camera next time. That match still needs an OS identifier, or the user picks each session | As good as the user | None with a UUID; a wrong pick gives a wrong link | None |
| **(iv) Refuse the camera** | Trivial. Today's filters already refuse most such cameras [C detect_cameras_devices.py:100-106] | n/a | None | None |
| **(v) Key 0, link by position** | Changes SFF-752 ("capture writer MUST … not 0"). Readers link by `cam<N>` and warn `camera_key_zero` (SFF-873) | Position only | A wrong link if the order changes, but it is flagged | None |
| **(vi) OS index (item 44)** | Trivial | Low. With nothing moved, the C930e went from MF 7 to 6 and DirectShow 7 to 2. MF and DirectShow indices differ for the same camera (C922: MF 4, DirectShow 0). The lists include virtual cameras (4 NDI cameras on the test machine) [R usb_camera_report.md:114-116; skellycam_recording/results/real_recording_20261109/RESULTS.md:54] | **Silent, across takes.** Another camera at the same index on another day gets the same key; with null VID and PID, every camera at index 0 is `0000:0000:index:0`. That breaks "two different cameras must never share a key" without any warning | None |
| **(vii) Session-scoped index** (my addition): `…:session:<uuid4>:<os_index>` | Trivial plus one `device` member | Stable within one skellycam session (calibration plus takes), new each session | None (random 128-bit UUID) | None |

## 3. Recommendation

The rule, for SFF-752 and item 44:

> The identity string is the first form that applies:
> 1. `<vendor_id>:<product_id>:serial:<serial>`, when the USB serial is usable: not empty, every character 0x21–0x7F, no `,`, not a listed placeholder, not one repeated character, and not shared by another connected camera with the same IDs.
> 2. `<vendor_id>:<product_id>:port:<port_path>`, where `port_path` is the physical location that the capture writer reads from the OS, never from the capture library:
>    - Windows: `DEVPKEY_Device_LocationPaths[0]` of the USB device (for a non-USB device, of its devnode), with the `#USB(n)` tail written as `/n1.n2…`.
>    - Linux: `<PCI address of the controller>-usbv<2|3>-<port chain>`, from sysfs (`ID_PATH_WITH_USB_REVISION` without its `:config.interface` part). For a PCI or platform device, its `ID_PATH`.
>    - macOS: `bus<BB>/<p1.p2…>`, from the `locationID` of the `IOUSBHostDevice`.
> 3. `<vendor_id>:<product_id>:device:<os_device_id>`, where `os_device_id` (a new `device` member, listed under privacy) is the macOS `AVCaptureDevice.uniqueID` of a camera that is not USB, or the Windows device instance ID of a camera devnode that has no location path.
> 4. Otherwise `<vendor_id>:<product_id>:session:<session_id>:<os_index>`. `session_id` is a UUID4 (a new `device` member) that skellycam creates each time it enumerates cameras. The capture writer warns that this camera will not link to takes from other sessions.
>
> The capture writer refuses a camera only when `os_index` is null as well. IDs are 4 lowercase hex characters, `0000` when null.

Why this rule:
- Form 4 replaces item 44's index form. Within a session it does the same job, and it can never link two different cameras across sessions.
- If you would rather keep the code smaller, "refuse" (option iv) is the honest alternative for form 4. Both are better than a bare index.
- Form 2 with the revision costs nothing extra: a camera that falls back to USB 2 lands on the other root hub's port number anyway [I].

Implementation notes:
- **Windows serial:** read it from the USB parent's instance ID when that ID has no `&` (Windows used the serial). That avoids a GET_DESCRIPTOR to the Kiyo Pro. But with the `IgnoreHWSerNum` setting, the same camera gets form 2 on Windows and form 1 on Linux [I].
- **Cross-OS keys:** the key is not the same on two OSes for a port-keyed camera. The Kiyo Pro and C930e will in practice always be port-keyed, because neither has a serial [R usb_camera_report.md:105-106].

How sure I am:
- **High:** on the Windows facts and on the analysis of today's code.
- **Medium:** on the Linux and macOS behaviour. The research only drafted those, against a fake sysfs tree and a synthetic ioreg dump [R usb_camera_report.md:118].
- **Lower:** on the virtual and Continuity Camera rows.

What I could not verify:
- A reboot, a physical replug or a port move on any OS (the controlled test never ran).
- Two identical cameras.
- Whether the MF virtual camera's instance ID or symbolic link stays the same across runs.
- The uniqueID format for built-in Mac and Continuity cameras, and whether it holds anything private.
- Whether the macOS controller identity can replace the bus byte (open test MT5 in topology_macos.md).
- The Brio. It was never measured; the research tested the C922, C930e, Kiyo Pro and a generic camera.

Apple's uniqueID page would not load, so I used the quote in the forum thread. I changed no files and touched no devices.

Sources:
- https://learn.microsoft.com/en-us/windows-hardware/drivers/install/device-instance-ids
- https://learn.microsoft.com/en-us/windows/win32/api/mfvirtualcamera/nf-mfvirtualcamera-mfcreatevirtualcamera
- https://developer.apple.com/forums/thread/836729
- https://developer.apple.com/forums/thread/757573
- https://lists.libcamera.org/pipermail/libcamera-devel/2020-July/011285.html
- https://patchwork.libcamera.org/patch/9190
- https://sources.debian.org/src/v4l2loopback/0.15.2-1/v4l2loopback.h
- https://learn.microsoft.com/en-us/windows-hardware/drivers/install/overview-of-container-ids
