# naming/ - goal 4: consistent camera identity

Harness for "which identifier names the same physical camera across reboots, replugs and port moves",
plus the USB/UVC descriptor dump reused by the bandwidth and timing work.

## Files

| file | platform | status | what it does |
| --- | --- | --- | --- |
| `usbdesc.py` | any | tested (`--selftest`, `test_parsers.py`) | stdlib parser: device / configuration / BOS / string descriptors, UVC VC+VS class descriptors, per-alt-setting bandwidth |
| `win_identity_dump.py` | Windows | tested | cfgmgr32 PnP properties + device interfaces + hub IOCTL descriptor read; writes `identity_dump.json`, `descriptors.json`, optional `snapshots/<label>.json` |
| `win_api_names.py` | Windows | tested | names/paths seen by Media Foundation, DirectShow, FFmpeg dshow, OpenCV (cv2_enumerate_cameras), mapped back to the USB device; writes `api_names.json` |
| `win_restart_test.py` + `win_restart_devices_admin.ps1` (+ `win_restart_revert_admin.ps1`) | Windows | tested | one UAC prompt; `pnputil /restart-device` on each composite parent under camlock, snapshot before/after, diff |
| `win_stability_workflow.ps1` | Windows | user-run, unverified | snapshot before/after reboot, replug same port, move port; diff |
| `linux_identity.py`, `linux_stability_workflow.sh` | Linux | DRAFT, unverified | sysfs + udev + /dev/v4l symlinks + VIDIOC_QUERYCAP + sysfs `descriptors`; same snapshot/diff workflow |
| `macos_identity.py`, `macos_stability_workflow.sh` | macOS | DRAFT, unverified | AVFoundation (pyobjc) + `ioreg` IOUSBHostDevice; checks uniqueID == `0x<locationID><vid><pid>` |
| `identity_diff.py` | any | tested on Windows snapshots | diff N snapshots into a per-identifier stability table |
| `camera_identity.py` | Win tested, Linux/mac draft | reusable module | the recommended key scheme (`list_cameras()`) |
| `test_parsers.py` | any | tested | offline checks against real descriptor bytes (incl. Linux sysfs layout) |
| `test_linux_fake_sysfs.py` | Linux/WSL | tested in WSL2 Ubuntu (fake sysfs) | plumbing test of `linux_identity.py` on a synthetic sysfs tree with real descriptor bytes; `results/linux/Gerald/` is this WSL fake-tree run, NOT real Linux hardware |
| `test_macos_fake_ioreg.py` | any | tested on Windows (synthetic plist) | plumbing test of `macos_identity.py` parsing + uniqueID matching |
| `99-skellycam-cameras.rules.example` | Linux | documented-untested | optional udev rules; not needed by the app |

All commands are run from the repo root. On the shared Windows machine wrap anything that touches cameras in
`uv run --script research/usb_cameras/tools/camlock.py -- ...`.

```
uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/naming/win_identity_dump.py --label <name>
uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/naming/win_api_names.py
uv run --script research/usb_cameras/naming/win_restart_test.py            # takes camlock itself; 1 UAC prompt
uv run --script research/usb_cameras/naming/test_parsers.py
uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/naming/camera_identity.py
```

Options added for the 2026-10-27 re-run (defaults unchanged):
- `--exclude-vidpid vvvv:pppp` (repeatable) on `win_identity_dump.py`, `win_api_names.py`, `camera_identity.py`
  (or env `NAMING_EXCLUDE_VIDPID=vvvv:pppp,...`): the device is skipped before any property read or hub IOCTL, so no
  GET_DESCRIPTOR reaches it. `win_api_names.py` still lists it in the MF/DShow/FFmpeg/OpenCV enumerations (no stream).
  On `libusb_identity.py` the device is never `libusb_open`ed (libusb's own bus enumeration still sees it).
- `--out-dir DIR` on `win_api_names.py`, `test_parsers.py`, `test_macos_fake_ioreg.py`, `test_linux_fake_sysfs.py`
  so re-runs don't overwrite the cited result files; `camera_identity.py --out FILE` writes a result JSON with
  metadata and the in-process listing time.

## descriptors.json schema

`results/<platform>/<host>/naming/descriptors.json` (Windows: read through the parent hub with
`IOCTL_USB_GET_DESCRIPTOR_FROM_NODE_CONNECTION`; Linux draft: sysfs `descriptors`). Top level:
`test, platform, hostname, utc_started, command, environment, cameras[]`. Each camera:

| key | content |
| --- | --- |
| `camera` | `vid, pid` (lower-case hex str), `product, manufacturer, serial` (USB string descriptors, null if index 0), Windows: `composite_instance_id, location_paths, friendly_name`; Linux: `sysfs_usb_name` |
| `speed` | `"low" / "full" / "high" / "super" / "super_plus"` - operating speed (Windows: `..._EX` Speed, upgraded to super if `_EX_V2` says SuperSpeed, because the `_EX` field stops at high speed) |
| `device` | parsed device descriptor (`bcdUSB` "2.00", `idVendor`, `idProduct`, `bcdDevice`, string indices, ...) |
| `strings` | `{index: text}` for every string index referenced anywhere in the descriptors (LANGID 0x0409 if offered) |
| `bos` | BOS capabilities (USB >= 2.01 devices) incl. `ContainerID` if the device has one |
| `configuration_summary` | `wTotalLength, bNumInterfaces, bConfigurationValue, bmAttributes, max_power_mA, interface_associations[]` |
| `uvc` | flattened UVC view, below |
| `interfaces[]` | every interface alt setting in descriptor order: standard fields, `kind` (`video_control`/`video_streaming`/`audio_*`), `class_specific[]` (each parsed CS descriptor + `raw` hex), `endpoints[]` (+ `ss_companion`, `bandwidth`) |
| `raw_hex` | `device`, `configuration`, `bos` exact bytes as hex (Linux: `sysfs_descriptors`) |

`uvc`:
```
bcdUVC            "1.00"                      VC header
dwClockFrequency  int Hz                      VC header (device clock for PTS/SCR; timing work)
vc_interface, vc_interrupt_endpoint
units[]           VC_INPUT_TERMINAL (camera: bmControls + decoded `controls` names), VC_PROCESSING_UNIT
                  (decoded `controls`), VC_EXTENSION_UNIT (guidExtensionCode, known_as), VC_OUTPUT_TERMINAL, ...
streaming_interfaces[]:
  bInterfaceNumber, transport ("isochronous"|"bulk"), input_header{bEndpointAddress, bNumFormats, bStillCaptureMethod, ...}
  formats[]: format ("UNCOMPRESSED"|"MJPEG"|"FRAME_BASED"|"H264"...), bFormatIndex, fourcc ("YUY2","MJPG","H264","NV12"..),
             guidFormat, bDefaultFrameIndex, color_matching{...}
     frames[]: bFrameIndex, wWidth, wHeight, dwMinBitRate, dwMaxBitRate, dwMaxVideoFrameBufferSize,
               dwDefaultFrameInterval, interval_type "discrete" -> dwFrameInterval[] (100 ns) + fps[]
                                       | "continuous" -> dwMin/Max/StepFrameInterval + fps_min/fps_max
  alt_settings[]: bAlternateSetting, bEndpointAddress, transfer_type, wMaxPacketSize_raw, bInterval, ss_companion,
                  bytes_per_transaction (= wMaxPacketSize & 0x7ff), transactions_per_microframe (HS: 1 + bits 12:11),
                  bytes_per_interval (HS: size*mult; SS: companion wBytesPerInterval), service_interval_us,
                  max_bytes_per_second (bytes_per_interval / service interval)   <- what the host must reserve
```
`max_bytes_per_second` is derived arithmetic from the descriptors, not a measurement.

## Snapshot (`naming.snapshot`) fields

Flat per-camera identifier dict used by `identity_diff.py`. Windows: `vid, pid, bcdDevice, usb_serial,
usb_manufacturer, usb_product, composite_instance_id, video_function_instance_id, serial_used_in_instance_id,
container_id, container_id_uuid_version, location_paths, location_info, port_number, hub_port_chain,
usb_device_address, friendly_name, bus_reported_device_desc, ks_video_camera_symlink, ks_capture_symlink, speed,
mf_index, mf_friendly_name, mf_symbolic_link, dshow_index, dshow_friendly_name, ffmpeg_dshow_alternative_name,
mf_device_count, dshow_device_count, camera_key`. Linux: see `linux_identity.flat()`; macOS: `macos_identity.collect_flat()`.
