# Non-Python and vendor options for GigE Vision capture (TOPIC_KEY=rust-cpp-vendor)

Date of survey: 2026-10-25. Every claim below links to code, a test, or a vendor doc page that was opened and read.
The source clones are in `scratchpad/research/src/<name>/`. The test scripts are in `scratchpad/research/scripts/rust-cpp-vendor/`.

## 0. Key takeaways

* **The best non-vendor options in 2026 are the new pure-Rust GigE Vision stacks that ship Python wheels.** These are `viva-genicam` (MIT) and `telegenic` / `telegenicam` (Apache-2.0). Both are pip-installable and need no vendor SDK. Both speak GVCP/GVSP directly, so they work with any vendor's GigE Vision camera. Both are very young (`telegenic` first commit 2026-06-12) and pre-1.0.
* **I ran `viva-genicam` 0.10.0 and `telegenicam` 2.1.0 from PyPI against the Aravis software camera (`arv-fake-gv-camera-0.8`) in Docker.** Both received Mono8 512x512 frames. `viva-genicam` discovered the camera and also sent an `ACTION_CMD`, which the fake camera acknowledged when the keys matched (section 5).
* **`cameleon` (Rust) does NOT support GigE Vision**, as of its last commit on 2026-04-02 and last release 0.1.14 on 2024-12-05. It supports USB3 Vision only. Two PRs that add GigE support are still open.
* **Aravis (C, LGPL) has no action-command support.** Its GVCP command enum stops at memory read/write and PENDING_ACK, with no `ACTION_CMD` (0x0100). PTP features are reachable only through generic GenICam feature access. That also applies to `aravis-rs` and to the `aravissrc` GStreamer element.
* **The vendor SDKs lock you to their own cameras, except Vimba X and eBUS.**
  * Basler's pylon EULA says the software may be used solely to operate a Basler camera product.
  * Spinnaker says it "supports FLIR and Dalsa ... cameras".
  * LUCID describes Arena as supporting LUCID cameras only.
  * Allied Vision's Vimba X explicitly allows GenICam-compliant cameras and transport layers "from all manufacturers", free of charge.
  * Pleora eBUS works with any GigE Vision camera, but non-Pleora devices need a paid GEV-Rx receiver license, or a watermark is embossed on the images.
* **In every library, PTP is configured through GenICam SFNC features on the camera's node map.** The names are `GevIEEE1588*` (older) or `Ptp*` (newer). So any library with generic feature get/set can turn PTP on and read its status. The library-specific pieces are:
  * (a) sending the GVCP **action command**, including the scheduled variant, and
  * (b) mapping device timestamps to host time.

## 1. Rust

### 1.1 cameleon (cameleon-rs/cameleon)
* Repo: https://github.com/cameleon-rs/cameleon. HEAD is `1ab3fbf8` (2026-04-02). Latest crate release is 0.1.14 (2024-12-05), from the crates.io API and git tag `cameleon-v0.1.14` = `5a9efbc5`, dated 2024-12-05. License is MPL-2.0 ([LICENSE](https://github.com/cameleon-rs/cameleon/blob/1ab3fbf82a11f94da56e35a62893a6042054df4b/LICENSE)).
* The README says: "Currently, `cameleon` supports only `USB3 Vision` cameras, but it's planned to support other protocols including `GigE Vision`" ([README.md#L28](https://github.com/cameleon-rs/cameleon/blob/1ab3fbf82a11f94da56e35a62893a6042054df4b/README.md#L28)). The roadmap puts "Add support for GigE cameras" under v0.2.0 ([README.md#L167-L171](https://github.com/cameleon-rs/cameleon/blob/1ab3fbf82a11f94da56e35a62893a6042054df4b/README.md#L167-L171)).
* The public modules are only `camera`, `genapi`, `payload` and `u3v` ([cameleon/src/lib.rs#L146-L150](https://github.com/cameleon-rs/cameleon/blob/1ab3fbf82a11f94da56e35a62893a6042054df4b/cameleon/src/lib.rs#L146-L150)).
* There is a leftover example, `cameleon/examples/gige/register_map.rs`, that uses `cameleon::gige`. That module does not exist.
* GigE support is in open PRs only:
  * [#198 "Naive GigE implementation"](https://github.com/cameleon-rs/cameleon/pull/198), opened 2024-11-20. It covers a single stream channel and has "No request of the lost packets".
  * [#223 "Resume gige implementation"](https://github.com/cameleon-rs/cameleon/pull/223), opened 2026-02-26 and last updated 2026-06-01. Both are still open (GitHub API).
* PTP and action commands: no matches for ptp/1588/action in the source tree (grep).

### 1.2 viva-genicam (VitalyVorobyev/viva-genicam): pure Rust GigE Vision + U3V, with Python wheels
* Repo: https://github.com/VitalyVorobyev/viva-genicam. HEAD is `60c9c329` (2026-10-24). Release v0.10.0 is dated 2026-10-17 on both crates.io and PyPI. License is MIT.
* PyPI `viva-genicam` 0.10.0 has wheels for `win_amd64`, `macosx_11_0_arm64` and `manylinux_2_28_x86_64` (PyPI JSON API). There is no macOS-x86_64 or Linux-aarch64 wheel, though an sdist exists.
* The README says users "have run discovery, control and streaming against real GigE Vision cameras from several vendors, on Linux, Windows and macOS". It lists "Events & actions -- ... trigger synchronized acquisition via action commands" and "map device timestamps to host time" ([README](https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/README.md)). The known gaps are tracked in [issue #191](https://github.com/VitalyVorobyev/viva-genicam/issues/191).
* Action command implementation ([crates/viva-gige/src/action.rs#L17-L45](https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/crates/viva-gige/src/action.rs#L17-L45), [#L108](https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/crates/viva-gige/src/action.rs#L108)):
  * The payload is 12 bytes (device_key, group_key, group_mask).
  * A scheduled action adds a 64-bit action time, sets flag bit 7, and uses opcode 0x0100. The unit tests check this against the spec bytes.
* The Python binding is `viva_genicam.send_action(device_key, group_key, group_mask, scheduled_time=None, destination="255.255.255.255", timeout_ms=200)` ([crates/viva-pygenicam/src/gige.rs#L43-L67](https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/crates/viva-pygenicam/src/gige.rs#L43-L67)). The book documents it under ["Action commands and IP configuration"](https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/book/src/python/control.md).
* Host and device time mapping: `time_calibrate(samples, interval_ms)` ([crates/viva-genicam/src/lib.rs#L394-L460](https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/crates/viva-genicam/src/lib.rs#L394-L460)):
  * It executes the SFNC timestamp-latch command and reads the latched TimestampValue.
  * It reads the tick frequency, or the GenCP timestamp increment.
  * It fits (device ticks, host `Instant`) pairs.
  * Frames expose `ts_dev` and `ts_host`.
* PTP: there is no dedicated PTP API. PTP nodes go through generic `cam.get/set`.
  * The fake camera exposes `GevIEEE1588OffsetFromMasterLatched_Val`, with a register layout "copied in shape from the FLIR BFS-PGE-31S4C-C" ([crates/viva-fake-gige/src/registers.rs](https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/crates/viva-fake-gige/src/registers.rs)).
  * Changelog 0.6 records a fix for "a FLIR Blackfly (#140, a PTP offset failing whenever it went negative)" ([changelog/0.6.md#L90-L100](https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/changelog/0.6.md#L90-L100)).
* There is a built-in fake GigE camera (`viva_genicam.testing.FakeGigeCamera`) that counts the action commands it receives. That makes it usable in CI.

### 1.3 telegenic / telegenicam (valstad-shipworks/telegenic): pure Rust GigE Vision with Python wheels
* Repo: https://github.com/valstad-shipworks/telegenic. HEAD is `eb9de657` (2026-10-20). The first commit was 2026-06-12, and there are 26 commits total. License is Apache-2.0 (Cargo.toml).
* The PyPI package is `telegenicam` 2.1.0 (2026-10-20), with the import name `telegenic`. Its wheels are win_amd64, win_arm64, macosx_11_0_arm64, manylinux2014 x86_64 and manylinux2014 aarch64.
* The README says "the only backend right now is GigE Vision ... speaks GVCP ... and GVSP directly over UDP, with no vendor SDK." It also mentions per-thread and per-socket real-time tuning on Linux, Windows and macOS ([README](https://github.com/valstad-shipworks/telegenic/blob/eb9de6579dde096b4a60ccead934edcc3795d6c3/README.md)).
* Each frame carries `timestamp_ticks`, `timestamp_ns` (device) and `system_timestamp_ns` (host CLOCK_REALTIME at leader reception) ([src/gige/stream/frame.rs#L140-L145](https://github.com/valstad-shipworks/telegenic/blob/eb9de6579dde096b4a60ccead934edcc3795d6c3/src/gige/stream/frame.rs#L140-L145)).
* Action commands: none. Grep for ACTION/0x0100/action_cmd found no GVCP action command. PTP is reachable only through generic `set_boolean`/`get_integer` feature access.

### 1.4 aravis-port (javerik/aravis-port): pure Rust port of Aravis' GEV subset
* Repo: https://github.com/javerik/aravis-port. HEAD is `389d5c8d` (2026-10-08). Version 0.2.0. License is MIT OR Apache-2.0.
* The README says it is "A pure-Rust, zero-`unsafe` port of the GigE Vision (GEV) subset of Aravis 0.9.2". It has been validated against an in-process fake and AT-Automation Technology C5/C6 cameras ([README](https://github.com/javerik/aravis-port/blob/389d5c8d14851c2c5920ddd7ad1072932f18a0f1/README.md)).
* It has no Python binding and no action command (grep).

### 1.5 aravis-rs (robohouse-delft/aravis-rs): Rust bindings to Aravis C
* Repo: https://github.com/robohouse-delft/aravis-rs. Last commit and release are `a911bf00`, 0.11.1, dated 2025-02-10. The binding's license is BSD-2-Clause ([LICENSE.md](https://github.com/robohouse-delft/aravis-rs/blob/a911bf002a0511a1c9a0c68a0bcd7ef4aa32aabe/LICENSE.md)), and it links to LGPL Aravis. The bindings are GIR-generated, and the README says "Not all of the API has been tested."
* Capabilities match Aravis (section 2.1): no action commands, and PTP only through generic features.

Other crates.io results (API search for gige/gvsp/gvcp/genicam, 2026-10-25):
* `aravis-camera` 0.1.1 (2026-03-12, no repo listed, 50 downloads).
* `hik-mvs-sdk` 0.1.2 (vendor SDK bindings).
* `neuromorphic-drivers` (event cameras).
I did not review these in depth.

## 2. C / C++

### 2.1 Aravis (AravisProject/aravis)
* HEAD is `482547a3` (2026-10-22). The last tag is `0.9.2`, at a commit dated 2026-04-23. License is LGPL-2.1-or-later ([README](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/README.md)). CI badges cover Linux, macOS, MinGW and MSVC.
* The GVCP command set has no ACTION_CMD ([src/arvgvcpprivate.h#L267-L281](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcpprivate.h#L267-L281)). Only the capability bit `ARV_GVBS_GVCP_CAPABILITY_ACTION` and the error code `ACTION_LATE` are defined.
* The headers `src/arvcamera.h` and `src/arvgvdevice.h` have no PTP-specific API (grep).

### 2.2 GStreamer `aravissrc`
* It is part of the Aravis repo (`gst/gstaravis.c`). Properties include `camera`, `packet-size`, `auto-packet-size`, `packet-resend`, `features` (a free-form feature assignment list), `trigger` and `add-reference-timestamp-meta`.
* `add-reference-timestamp-meta` was added on main on 2026-10-03 (commit `ee31d82f1`, after 0.9.2, so not yet released). It attaches the absolute device timestamp as `timestamp/x-ptp` reference meta ([gst/gstaravis.c#L564-L567](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/gst/gstaravis.c#L564-L567), [#L632-L640](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/gst/gstaravis.c#L632-L640)).
* Without it, the PTS is first-frame-relative device time (lines 620-629).
* Ubuntu 24.04 ships the plugin inside `libaravis-0.8-0` 0.8.30 (`/usr/lib/x86_64-linux-gnu/gstreamer-1.0/libgstaravis.0.8.so`). This was verified in Docker (section 5).

### 2.3 rc_genicam_api (roboception/rc_genicam_api)
* HEAD is `1f7aad7a` (2026-10-06), and the latest tag v2.8.9 is from the same day. The latest GitHub *release* with binaries is v2.8.4 (2026-05-20). It ships .deb packages for jammy and noble (amd64, arm64, armhf) and a win64 zip.
* The README describes it as the "Roboception convenience layer ... with the GenICam reference implementation and a GigE Vision transport layer ... GenICam / GigE Vision 2.0 compatible cameras ... can be compiled under Linux and Windows" ([README.md#L4-L8](https://github.com/roboception/rc_genicam_api/blob/1f7aad7ab30d92ddd323992f9eb605b481aca252/README.md#L4-L8)). macOS is not listed. The minimum requirements are Linux x64/ARM and Windows 10 ([#L33-L39](https://github.com/roboception/rc_genicam_api/blob/1f7aad7ab30d92ddd323992f9eb605b481aca252/README.md#L33-L39)).
* It is a GenTL consumer. It loads any `.cti` producer from `GENICAM_GENTL64_PATH`, and it bundles **Baumer's** GigE and USB GenTL producer v2.9.2 as binary `.cti` files for Win32/Win64 and Ubuntu 14.04/16.04 builds ([baumer/README.md](https://github.com/roboception/rc_genicam_api/blob/1f7aad7ab30d92ddd323992f9eb605b481aca252/baumer/README.md)).
* Licenses ([LICENSE.md](https://github.com/roboception/rc_genicam_api/blob/1f7aad7ab30d92ddd323992f9eb605b481aca252/LICENSE.md)):
  * The Roboception code is BSD-3-Clause.
  * `genicam/` uses the EMVA GenICam license.
  * The Baumer `.cti` is under a Baumer EULA ([baumer/license.txt](https://github.com/roboception/rc_genicam_api/blob/1f7aad7ab30d92ddd323992f9eb605b481aca252/baumer/license.txt)). The EULA is MIT-like for redistribution but forbids reverse engineering, and the software is closed source.
* PTP: the `gc_config -t 1|0` tool toggles `PtpEnable`, executes `PtpDataSetLatch`, and prints `PtpStatus` and `PtpOffsetFromMaster` ([tools/gc_config.cc#L280-L299](https://github.com/roboception/rc_genicam_api/blob/1f7aad7ab30d92ddd323992f9eb605b481aca252/tools/gc_config.cc#L280-L299)).
* `gc_stream` computes mean latency only when `PtpEnable` or `GevIEEE1588` is true ([tools/gc_stream.cc#L998](https://github.com/roboception/rc_genicam_api/blob/1f7aad7ab30d92ddd323992f9eb605b481aca252/tools/gc_stream.cc#L998)).
* No action-command helper was found (grep).

### 2.4 GenICam reference implementation (EMVA)
* PyPI `genicam` 1.6.0 (2026-09-01) is "The official Python Binding for the GenICam GenApi & the GenTL Producers", authored by the GenICam Committee. License is `LicenseRef-GenICam-1.6`. Wheels exist for win_amd64, macOS 13 arm64, and manylinux2014 x86_64/aarch64/armv7l.
* It is a GenApi plus GenTL *consumer* only. It needs a vendor `.cti` producer to talk to cameras.
* The Python consumer built on it is `harvesters` 1.4.3 (2024-05-16, Apache-2.0).

## 3. Vendor SDKs with Python bindings

### 3.1 Basler pylon / pypylon
* `pypylon` 26.9 was uploaded to PyPI on 2026-10-23. Wheels: win_amd64, macosx_14_0 arm64/x86_64, manylinux_2_31 x86_64/aarch64. The wrapper is BSD-3-Clause ([github.com/basler/pypylon](https://github.com/basler/pypylon)).
* The PyPI README says installing pylon is "strongly recommended but not mandatory". It also says "pylon Software Suite 26.06 supports Windows 10/11 64 bit, Linux x86_64 and Linux aarch64 ... macOS Sonoma or newer".
* The pylon EULA ([docs.baslerweb.com/pylon-end-user-license-agreement](https://docs.baslerweb.com/pylon-end-user-license-agreement), Version 137, 2026-10-19):
  * §4: "CUSTOMER may solely use the SOFTWARE for the purpose to operate a BASLER camera product".
  * §3: "sublicensing and distribution to a third party is not permitted", with an exception for Derivatives under conditions, including a license "at least as restrictive".
  * In short, pylon is Basler-only.
* PTP (https://docs.baslerweb.com/precision-time-protocol):
  * The standard is IEEE 1588-2008.
  * Features: `GevIEEE1588`, `GevIEEE1588DataSetLatch`, `GevIEEE1588Status[Latched]` and `GevIEEE1588OffsetFromMaster`. On ace 2 and dart M the equivalents are `PtpEnable`, `PtpDataSetLatch` and `PtpServoStatus` (=Locked).
  * Basler recommends PTP-enabled switches. Scheduled Action Commands, Periodic Signal and Synchronous Free Run are listed as features built on PTP.
* Action commands (https://docs.baslerweb.com/action-commands):
  * Device features: `ActionDeviceKey`, `ActionGroupKey`, `ActionGroupMask`, `ActionSelector`, and `TriggerSource=Action1`.
  * API: `IGigETransportLayer::IssueActionCommand(deviceKey, groupKey, groupMask, broadcastAddr)`.

### 3.2 Teledyne FLIR Spinnaker / PySpin
* Product page (https://www.teledynevisionsolutions.com/products/spinnaker-sdk/):
  * Platforms: Windows 11, Ubuntu 20.04 to 24.04, macOS Sequoia/Tahoe, and Linux ARM64.
  * Languages: C++, C#, C, VB.NET and Python.
  * Supported cameras: "supports FLIR and Dalsa USB3, GigE, 5GigE, and most 10GigE area scan cameras". I found no statement about third-party cameras.
  * Downloads require a login.
* PyPI has a `spinnaker-python` 2.4.0.144 from 2021-08-09, win_amd64 only. It is stale, and the current PySpin comes from the vendor download.
* PTP usage, evidenced by the ROS driver [ros-drivers/flir_camera_driver @ a73f62c (2026-08-01)](https://github.com/ros-drivers/flir_camera_driver/blob/a73f62c2b3bd23e2e555aa8ebf38f5f02187caf0/spinnaker_camera_driver/doc/index.rst#L320-L366):
  * Nodes: `TransportLayerControl/GigEVision/GevIEEE1588` and `GevIEEE1588Mode` (Auto/SlaveOnly) ([config/blackfly_s.yaml#L79-L84](https://github.com/ros-drivers/flir_camera_driver/blob/a73f62c2b3bd23e2e555aa8ebf38f5f02187caf0/spinnaker_camera_driver/config/blackfly_s.yaml#L79-L84)).
  * The doc says "Only FLIR GigE cameras are PTP capable, but not all ... Blackfly S series does."
  * It recommends running `ptp4l` on the host as master, plus `phc2sys`.

### 3.3 Allied Vision Vimba X / VmbPy
* Vimba X compatibility page (https://docs.alliedvision.com/compatibility.html, Vimba X 2026-3): "You can use GenICam-compliant cameras and transport layers for all camera interfaces from all manufacturers." Also: "Usage with cameras and TLs from third-party vendors is free of charge. You don't need any additional licenses."
* The product page says it "Runs on Windows, Linux, Linux ARM, and macOS". However, the macOS download is an older 2023-4 build (https://www.alliedvision.com/en/products/software/vimba-x-sdk/).
* VmbPy:
  * License is BSD-2-Clause (repo HEAD `c006dbb1`, 2026-09-08).
  * PyPI `vmbpy` 1.2.3 (2026-10-06) has wheels for manylinux_2_27 x86_64/aarch64 and win_amd64 only, with no macOS.
  * The wheels with libs include VmbC "but this `.whl` does not include any Transport Layers", which must be installed separately. TLs are loaded from `GENICAM_GENTL64_PATH` (README).
* Action commands: [Examples/action_commands.py#L112-L153](https://github.com/alliedvision/VmbPy/blob/c006dbb14902794a7124f84a2f7cb307abc468c5/Examples/action_commands.py#L112-L153):
  * Camera side: `TriggerSource='Action0'`, `ActionDeviceKey`, `ActionGroupKey` and `ActionGroupMask`.
  * Interface side: `inter.ActionDeviceKey/GroupKey/GroupMask.set(...)` then `inter.ActionCommand.run()`.
* PTP feature names for current Allied Vision models (e.g. Alvium G5) are NOT verified here (open question).

### 3.4 LUCID Arena SDK / arena_api
* Product page (https://thinklucid.com/arena-software-development-kit/): "supports all LUCID GigE Vision cameras" on "Windows, Linux, and ARM platforms". It has a Python API, and macOS and third-party cameras are not mentioned.
* The PTP plus scheduled action app note (https://thinklucid.com/multi-camera-synchronization-using-ptp-and-scheduled-action-commands/) uses these device node map features:
  * `PtpEnable`, `PtpSlaveOnly`, `PtpStatus`, `PtpDataSetLatch` and `PtpDataSetLatchValue`.
  * `TransferControlMode=UserControlled`, `TriggerSource=Action0` and `ActionUnconditionalMode`.
  * `ActionDeviceKey/GroupKey/GroupMask` and `ActionCommandFireCommand`.
  * In the logged run with 7 cameras, the FrameID 1 timestamps spread about 9 µs. That figure is my own calculation from the article's log.

### 3.5 Pleora eBUS SDK (Python)
* Product page (https://pleora.com/products/ebus-sdk), eBUS SDK 7.0:
  * Platforms: Windows 10/11 x64, RHEL/CentOS 9, Ubuntu 20.04–24.04 x64, Jetson ARM, Raspberry Pi OS, Yocto and OpenSTLinux. No macOS.
  * Python is supported.
  * Licenses: "eBUS SDK Seat License" and "GEV-Rx License".
* The eBUS Receive page (https://www.pleora.com/?p=7076) says:
  * "When a license is activated, the embossed watermark that appears on received images is no longer applied."
  * GEV-Rx is "required for applications which need to receive GigE Vision streams" from non-Pleora devices.
  * "To access eBUS SDK, a Developer Seat license is also required."
  * In short, eBUS works with any vendor, but it is commercial per seat and per receiver, which makes it unsuitable to bundle into an open-source app.

## 4. Comparison table

| Option | Lang | License | Win / mac / Linux | Any vendor GigE? | PTP features accessible | Action cmds | Maintained (last release) |
|---|---|---|---|---|---|---|---|
| cameleon | Rust | MPL-2.0 | Y/Y/Y (U3V via libusb) | **No GigE at all** (U3V only; PRs #198/#223 open) | n/a | No | 0.1.14, 2024-12-05; last commit 2026-04-02 |
| viva-genicam | Rust + Py wheels | MIT | Y / Y (arm64 wheel) / Y (x86_64 wheel) | Yes (own GVCP/GVSP) | Yes, via generic features; `time_calibrate` for timestamp mapping | **Yes**, incl. scheduled (`send_action`) – tested | 0.10.0, 2026-10-17 |
| telegenic / telegenicam | Rust + Py wheels | Apache-2.0 | Y (x64, arm64) / Y (arm64) / Y (x64, aarch64) | Yes | Yes, via generic features; frames carry device and host ns | No | 2.1.0, 2026-10-20 (project started 2026-06) |
| aravis-port | Rust | MIT/Apache-2.0 | (pure Rust; not tested by me) | Yes (tested by author on AT cameras) | generic features | No | 0.2.0, 2026-10-08 |
| aravis-rs → Aravis | Rust (FFI) | BSD-2 + LGPL | via Aravis | Yes | generic features | No (Aravis lacks ACTION_CMD) | 0.11.1, 2025-02-10 |
| Aravis | C (GObject; Py via PyGObject) | LGPL-2.1+ | Y (MinGW/MSVC CI) / Y / Y | Yes | generic features | **No** | 0.9.2 (tag 2026-04-23); HEAD 2026-10-22 |
| aravissrc (GStreamer) | C | LGPL | as Aravis | Yes | `features=` property; PTP reference-timestamp meta on main only | No | ships with Aravis; tested with 0.8.30 |
| rc_genicam_api | C++ | BSD-3 + EMVA GenICam + Baumer EULA (.cti binary) | Y / **N** / Y | Yes via any GenTL producer (bundled Baumer GigE TL) | Yes (`gc_config -t`, PtpEnable etc.) | not exposed in tools | tag v2.8.9, 2026-10-06 (binary release v2.8.4, 2026-05-20) |
| EMVA `genicam` + harvesters | C++/Py | GenICam license / Apache-2.0 | Y/Y/Y | Only with a GenTL producer (.cti) | generic features | via producer TL node map | genicam 1.6.0, 2026-09-01; harvesters 1.4.3, 2024-05-16 |
| Basler pypylon | Py/C++ | BSD-3 wrapper + proprietary pylon EULA | Y/Y/Y | **No** (EULA: Basler cameras only) | Yes (GevIEEE1588*/Ptp*) | Yes (`IssueActionCommand`) | 26.9, 2026-10-23 |
| FLIR Spinnaker / PySpin | Py/C++ | Proprietary (login download) | Y/Y/Y | No ("FLIR and Dalsa" cameras) | Yes (GevIEEE1588, GevIEEE1588Mode) | (not verified) | Spinnaker 4.x (version/date not on page) |
| Allied Vision Vimba X / VmbPy | Py/C/C++ | VmbPy BSD-2; Vimba X proprietary, free | Y / Y (old 2023-4 build; no VmbPy wheel) / Y | **Yes** (states "from all manufacturers", needs TL) | features per camera | Yes (Interface `ActionCommand`) | Vimba X 2026-3; vmbpy 1.2.3, 2026-10-06 |
| LUCID Arena / arena_api | Py/C++ | Proprietary, free | Y / N / Y (+ARM) | No (LUCID cameras) | Yes (PtpEnable, PtpSlaveOnly, …) | Yes (`ActionCommandFireCommand`, scheduled) | (version/date not stated) |
| Pleora eBUS | Py/C++ | Commercial (seat + GEV-Rx) | Y / N / Y (+ARM) | Yes, but watermark without GEV-Rx license | (not verified) | (not verified) | eBUS 7.0 |

## 5. Tests run (Docker, ubuntu:24.04, 2026-10-25)

The scripts are in `scratchpad/research/scripts/rust-cpp-vendor/` (`run.sh`, `test_viva.py`, `run3.sh`, `test3.py`). The commands are run from Git Bash:

```
MSYS_NO_PATHCONV=1 docker run --rm -v "<scripts>:/scripts:ro" ubuntu:24.04 bash /scripts/run.sh
docker network create rcv-isolated
MSYS_NO_PATHCONV=1 docker run --rm --network rcv-isolated -v "<scripts>:/scripts:ro" ubuntu:24.04 bash /scripts/run3.sh
```

**Packaging note.** `arv-fake-gv-camera-0.8` is in the Ubuntu package `aravis-tools`, not `aravis-tools-cli`. The latter only has `arv-tool-0.8`. Start it with `-i lo`.

Test A (run.sh): Aravis fake camera on lo, then arv-tool, viva-genicam, telegenicam and gst.
```
aravis pkg: libaravis-0.8-0:amd64	0.8.30-1build2
/usr/lib/x86_64-linux-gnu/gstreamer-1.0/libgstaravis.0.8.so
== arv-tool-0.8 against fake
DeviceVendorName = Aravis / DeviceModelName = Fake / PixelFormat = Mono8 / Width = 512 / Height = 512
Feature 'GevIEEE1588' not found
Feature 'PtpEnable' not found        <- Aravis fake has no PTP nodes
== viva  (viva-genicam 0.10.0 from PyPI)
discover(): [GigeDeviceInfo(ip='127.0.0.1', mac='00:00:00:00:00:00', manufacturer='Aravis', model='Fake', transport='gige')]
  DeviceVendorName = Aravis, Width = 512, Height = 512, PixelFormat = Mono8
frame 0 (512, 512) uint8   frame 1 (512, 512) uint8   frame 2 (512, 512) uint8
Frame attrs include ts_dev (=1792950017161862000), ts_host (None without calibration), block_id, missing_packets
== telegenic (telegenicam 2.1.0 from PyPI)
tele frame: 512 512 Mono8 262144     (attrs: timestamp_ns, timestamp_ticks, system_timestamp_ns, frame_id, ...)
== gst-inspect aravissrc: Version 0.8.30, License LGPL
== gst-launch-1.0 aravissrc camera-name=127.0.0.1 num-buffers=5 ! fakesink
caps = video/x-bayer, format=(string)bggr, width=(int)512, height=(int)512, framerate=(fraction)25/1
Got EOS from element "pipeline0".
```

Test B (run3.sh): viva-genicam's own FakeGigeCamera and action commands, on an isolated network.
```
fake: FakeGigeCamera(running, 640x480 @ 30 fps on 127.0.0.1:3956, pixel_format=0x01080001)
discovered: [GigeDeviceInfo(ip='127.0.0.1', mac='DE:AD:BE:EF:CA:FE', manufacturer='viva-genicam', model='FakeGigE', ...)]
   GevIEEE1588OffsetFromMasterLatched_Val = -1234567     <- PTP node read via generic get()
   ActionDeviceKey ERR node not found (fake's XML doesn't expose the key features)
send_action(1,1,0xFFFFFFFF) -> AckSummary(sent=1, acks=0)     <- wrong keys: no ack
FakeGigeCamera keys: 66 1 1
send_action(66,1,1) -> AckSummary(sent=1, acks=1) fake.actions()= 1   <- matching keys: acked + acted
```

**Gotcha found while testing.** On Docker's *default* bridge network, GVCP broadcast discovery from one container found an Aravis fake camera running in *another* container (172.17.0.5). This came from parallel research jobs. Use a dedicated `docker network create` network, or `--network none`, for isolated GigE tests.

Not tested: pypylon, Spinnaker, Arena, Vimba X and eBUS against the fake camera. The pylon EULA restricts use to Basler cameras, and the others need login-gated downloads.

## 6. Open questions
* Whether `telegenicam`'s async/stream API and `viva-genicam` sustain multi-camera full-rate GigE streams on Windows and macOS without drops. This needs real cameras, and only loopback was tested.
* PTP feature names on current Allied Vision models (Alvium G5) and whether Vimba X's own GigE TL enumerates non-Allied Vision cameras. The docs say third-party cameras *and TLs* can be used, but not explicitly that AV's GigE TL drives them.
* Whether Spinnaker exposes a host-side action-command API (vendor docs are login-gated).
* Whether pylon's GigE TL technically enumerates non-Basler devices. This was not tested because of the EULA.
* Arena SDK and PySpin current version numbers and release dates. They are not on the public pages.
