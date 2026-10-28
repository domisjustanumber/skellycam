# rust-cpp-vendor

## Summary (survey date 2026-10-25)

The full notes, with every link, are in `C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/f77e9c4e-e1ea-4406-8a36-bef826a63a0e/scratchpad/research/rust-cpp-vendor.md`. The test scripts are in `.../scratchpad/research/scripts/rust-cpp-vendor/`.

### Main findings
* **Best non-vendor options: two new pure-Rust GigE Vision stacks that ship Python wheels.** Both talk GVCP/GVSP directly over UDP and need no vendor SDK, so they work with any vendor's camera.
  * [viva-genicam](https://github.com/VitalyVorobyev/viva-genicam) (MIT, v0.10.0 on 2026-10-17). Wheels for win_amd64, macOS arm64 and manylinux x86_64.
  * [telegenic / `telegenicam`](https://github.com/valstad-shipworks/telegenic) (Apache-2.0, v2.1.0 on 2026-10-20). Wheels for win x64/arm64, macOS arm64 and Linux x64/aarch64.
  * I installed both from PyPI in Docker and streamed Mono8 frames from Aravis' `arv-fake-gv-camera-0.8`.
* **viva-genicam is the only open-source library I found that sends GVCP `ACTION_CMD`, including the scheduled variant.** See [action.rs#L17-L45](https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/crates/viva-gige/src/action.rs#L17-L45) and the Python [`send_action`](https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/crates/viva-pygenicam/src/gige.rs#L43-L67).
  * It also has a device-to-host timestamp fit, [`time_calibrate`](https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/crates/viva-genicam/src/lib.rs#L394-L460).
  * Tested: its FakeGigeCamera did not acknowledge a command with the wrong keys (`acks=0`). With matching keys it acknowledged and acted (`acks=1, fake.actions()=1`).
  * Through generic `get()` I read the PTP node `GevIEEE1588OffsetFromMasterLatched_Val` on the fake.
* **cameleon has no GigE Vision support.** Its README says "supports only USB3 Vision" ([README#L28](https://github.com/cameleon-rs/cameleon/blob/1ab3fbf82a11f94da56e35a62893a6042054df4b/README.md#L28)), and its modules are only `camera/genapi/payload/u3v` ([lib.rs#L146-L150](https://github.com/cameleon-rs/cameleon/blob/1ab3fbf82a11f94da56e35a62893a6042054df4b/cameleon/src/lib.rs#L146-L150)).
  * Last release 0.1.14 on 2024-12-05.
  * The GigE work sits in open PRs [#198](https://github.com/cameleon-rs/cameleon/pull/198) and [#223](https://github.com/cameleon-rs/cameleon/pull/223).
* **Aravis (LGPL) cannot send action commands.** Its GVCP command enum has no ACTION_CMD ([arvgvcpprivate.h#L267-L281](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcpprivate.h#L267-L281)). The same limit applies to aravis-rs (0.11.1, 2025-02-10) and the GStreamer `aravissrc` element.
  * `aravissrc` works: tested with gst-launch, 5 buffers, bayer 512x512, EOS.
  * On main only (unreleased, commit 2026-10-03) it gained `add-reference-timestamp-meta`, which attaches the absolute device timestamp as `timestamp/x-ptp` ([gstaravis.c#L564-L567](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/gst/gstaravis.c#L564-L567)).
* **rc_genicam_api (C++, BSD-3) runs on Linux and Windows only, with no macOS.**
  * It is a GenTL consumer that bundles the GenICam reference implementation and a closed-source Baumer GigE GenTL producer under the Baumer EULA. Its README says "GigE Vision 2.0 compatible" ([README#L4-L8](https://github.com/roboception/rc_genicam_api/blob/1f7aad7ab30d92ddd323992f9eb605b481aca252/README.md#L4-L8)).
  * PTP is toggled through `PtpEnable` / `PtpDataSetLatch` / `PtpStatus` / `PtpOffsetFromMaster` in [gc_config.cc#L280-L299](https://github.com/roboception/rc_genicam_api/blob/1f7aad7ab30d92ddd323992f9eb605b481aca252/tools/gc_config.cc#L280-L299).
    > **Correction (2026-10-28):** lines 280-299 only read `PtpEnable`/`PtpStatus`/`PtpOffsetFromMaster` after `PtpDataSetLatch`. The toggle is `gc_config -t 1|0`, which sets `PtpEnable` at L173. Also, the bundled Baumer license text is labelled an EULA (for "Baumer Camera Explorer"), but its clause 1 is MIT-style permissive text (verifier c8).
* **Vendor SDKs mostly lock you to their own cameras:**
  * **Basler pylon:** the [EULA §4](https://docs.baslerweb.com/pylon-end-user-license-agreement) says "solely ... to operate a BASLER camera product".
  * **Spinnaker:** "supports FLIR and Dalsa ... cameras" ([product page](https://www.teledynevisionsolutions.com/products/spinnaker-sdk/)).
  * **LUCID Arena:** "supports all LUCID GigE Vision cameras" ([page](https://thinklucid.com/arena-software-development-kit/)).
  * **Allied Vision Vimba X** is the exception: "GenICam-compliant cameras and transport layers ... from all manufacturers", free of charge ([compatibility](https://docs.alliedvision.com/compatibility.html)). But the VmbPy wheels have no macOS build, and transport layers must be installed separately.
  * **Pleora eBUS** works with any vendor, but non-Pleora streams carry a watermark unless you buy a GEV-Rx license, plus a developer seat license ([eBUS Receive](https://www.pleora.com/?p=7076)).
* **PTP is configured with SFNC GenICam features on the camera in every library.** The names are `GevIEEE1588*` or `Ptp*`, for example in [Basler's PTP doc](https://docs.baslerweb.com/precision-time-protocol), [FLIR via the ROS driver](https://github.com/ros-drivers/flir_camera_driver/blob/a73f62c2b3bd23e2e555aa8ebf38f5f02187caf0/spinnaker_camera_driver/doc/index.rst#L320-L366) and [LUCID's app note](https://thinklucid.com/multi-camera-synchronization-using-ptp-and-scheduled-action-commands/). Any library with generic feature get/set can enable PTP. What differs between libraries:
  * whether they can send a (scheduled) action command;
  * whether they expose device timestamps per frame;
  * whether they provide a host-time mapping.

### Comparison table
| Option | Lang | License | Win/mac/Linux | Any vendor? | PTP features accessible | Action cmds | Last release |
|---|---|---|---|---|---|---|---|
| cameleon | Rust | MPL-2.0 | Y/Y/Y | **No GigE** (U3V only) | n/a | No | 0.1.14, 2024-12-05 |
| viva-genicam | Rust+Py | MIT | Y/Y(arm64)/Y(x64) | Yes | Yes (generic features + time_calibrate) | **Yes, incl. scheduled (tested)** | 0.10.0, 2026-10-17 |
| telegenic (telegenicam) | Rust+Py | Apache-2.0 | Y/Y(arm64)/Y | Yes | Yes (generic; frames carry device and host ns) | No | 2.1.0, 2026-10-20 |
| aravis-port | Rust | MIT/Apache | pure Rust (untested by me) | Yes | generic | No | 0.2.0, 2026-10-08 |
| aravis-rs → Aravis | Rust FFI | BSD-2 + LGPL | via Aravis | Yes | generic | No | 0.11.1, 2025-02-10 |
| Aravis | C | LGPL-2.1+ | Y/Y/Y (CI) | Yes | generic | **No** | 0.9.2 (2026-04-23) |
| aravissrc (GStreamer) | C | LGPL | as Aravis | Yes | `features=` prop; PTP ts meta on main | No | with Aravis |
| rc_genicam_api | C++ | BSD-3 + GenICam + Baumer EULA | Y/**N**/Y | Yes (GenTL; bundled Baumer TL) | Yes | not in tools | v2.8.9 tag, 2026-10-06 |
| EMVA genicam + harvesters | C++/Py | GenICam / Apache-2.0 | Y/Y/Y | needs a vendor .cti | generic | via TL | 1.6.0, 2026-09-01 / 1.4.3, 2024-05-16 |
| Basler pypylon | Py | BSD-3 wrapper + proprietary EULA | Y/Y/Y | **No (EULA)** | Yes | Yes (`IssueActionCommand`) | 26.9, 2026-10-23 |
| FLIR Spinnaker/PySpin | Py/C++ | proprietary, login download | Y/Y/Y | No | Yes (GevIEEE1588, GevIEEE1588Mode) | not verified | 4.x (no date) |
| Vimba X / VmbPy | Py | BSD-2 wrapper; SDK free | Y / (old build, no wheel) / Y | **Yes** (with TL) | per camera | Yes (Interface `ActionCommand`) | 2026-3; vmbpy 1.2.3, 2026-10-06 |
| LUCID Arena | Py/C++ | proprietary, free | Y/N/Y | No | Yes | Yes (`ActionCommandFireCommand`) | not stated |
| Pleora eBUS | Py/C++ | commercial seat + GEV-Rx | Y/N/Y | Yes (watermark without license) | not verified | not verified | 7.0 |

### Tests (Docker ubuntu:24.04)
* Two packaging details:
  * `arv-fake-gv-camera-0.8` is in the `aravis-tools` package, not `aravis-tools-cli`. Run it with `-i lo`.
  * Ubuntu's `libaravis-0.8-0` 0.8.30 ships `libgstaravis.0.8.so`.
* `arv-tool-0.8` showed the Aravis fake has no `GevIEEE1588` or `PtpEnable` nodes, so it cannot be used to test PTP.
* **Gotcha:** on Docker's default bridge network, GVCP broadcast discovery found a fake camera running in another container. Use a dedicated `docker network create` network for isolated tests.
* Not tested: pypylon, PySpin, Arena, VmbPy and eBUS. The pylon EULA restricts use to Basler cameras, and the others are login-gated.

## Open questions

- Do viva-genicam and telegenicam sustain multi-camera full-rate GigE streams without packet loss on Windows and macOS? Only loopback against fake cameras was tested.
- What are the PTP feature names on current Allied Vision models (e.g. Alvium G5)? Does Vimba X's own GigE transport layer enumerate non-Allied Vision cameras, or does it only accept third-party TLs?
- Does Spinnaker/PySpin expose a host-side action-command or scheduled-action API? The docs are login-gated.
- Does the pylon GigE TL technically enumerate non-Basler devices? This was not tested because the EULA restricts use to Basler cameras.
- What are the current versions and release dates of the Arena SDK (arena_api) and PySpin? They are not on the public pages.
- Does a GigE Vision 3.0 spec revision exist and change PTP or action commands (vs GigE Vision 2.x, which vendors cite for IEEE 1588-2008)? Not verified in this topic; none of the vendor pages read mention GigE Vision 3.0.
- telegenic has no action command, so would SkellyCam need viva-genicam (or its own GVCP ACTION_CMD sender) for synchronized triggering?

## Verification: Counter({'supported': 13, 'partially-supported': 3})

- [partially-supported] c3: viva-genicam implements GVCP ACTION_CMD (opcode 0x0100) including scheduled action commands (64-bit action time, flag bit 7) and exposes it in Python as viva_genicam.send_action(device_key, group_key, group_mask, scheduled_time=None, destination='255.255.255.255', timeout_ms=200); a fake camera acked only when keys matched.
  REASON: Encoding confirmed by code and by my own wire capture.
- consts.rs: ACTION_COMMAND = 0x0100.
- gvcp.rs sets flag byte 0x80 for SCHEDULED_ACTION.
- action.rs: the payload is 12 bytes, or 20 bytes with a u64 time.

Wire capture: viva-genicam 0.10.0 sending to a Python UDP listener in Docker produced:
- unscheduled: 42 01 0100 000c 11223344 55667788 ffffffff
- scheduled: 42 81 0100 0014 ... 0102030405060708

Corrections:
1. The cited permalink 60c9c329 (2026-10-24) is 4 commits after the released tag py-v0.10.0 (d53a48f). In the release, _native.send_action returns (sent, acks). The Python wrapper exposes that as AckSummary(sent, acks), which is what my test printed. The 3-tuple with refusals is unreleased.
2. The 'acked only when keys matched' test ran against viva-genicam's own FakeGigeCamera, not an independent device. Sent to the Aravis fake, the result was AckSummary(sent=1, acks=0) because Aravis does not implement ACTION_CMD.
3. Per the comment in action.rs, a real Allied Vision Manta G-125B answered NOT_IMPLEMENTED. So camera-side support varies.
  CORRECTED: viva-genicam sends GVCP ACTION_CMD (opcode 0x0100) with ACK_REQUIRED (0x01) and, for scheduled actions, flag 0x80 plus a 64-bit action time (20-byte payload). This is verified on the wire.

In the released 0.10.0, Python send_action(device_key, group_key, group_mask, scheduled_time=None, destination='255.255.255.255', timeout_ms=200) returns AckSummary(sent, acks).

Acknowledgement has been demonstrated only against the library's own emulator. No real camera's acceptance of a scheduled action has been shown here.
  BETTER: ['https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/src/gige.rs#L40-L66', 'https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/crates/viva-gige/src/gvcp.rs#L119-L131', 'https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/crates/viva-gige/src/consts.rs#L66', 'https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/crates/viva-gige/src/action.rs#L57-L68']

- [partially-supported] c7: The GStreamer aravissrc element works against a GigE Vision device (tested 0.8.30 from Ubuntu 24.04, which ships libgstaravis.0.8.so in libaravis-0.8-0); Aravis main (unreleased, commit ee31d82f1 on 2026-10-03) adds add-reference-timestamp-meta that attaches the absolute device timestamp as timestamp/x-ptp reference meta.
  REASON: The code is confirmed:
- gstaravis.c L564-567 defines timestamp/x-ptp caps.
- L632-640 adds a GstReferenceTimestampMeta when timestamp_ns != 0.
- Commit ee31d82 (2026-10-03) is contained in no tag (git tag --contains returns nothing), so it is unreleased.

The researcher's own gst-launch run was not reproduced here.

Caveat: timestamp_ns comes from arv_buffer_get_timestamp. For GigE streams, Aravis replaces the device timestamp with host g_get_real_time() whenever the timestamp tick frequency reads 0, and for unknown payload types (arvgvstream.c L482-486, L530). A buffer tagged timestamp/x-ptp can therefore carry host wall-clock time. It only carries device PTP time when the camera reports a tick frequency and is actually PTP-locked.
  CORRECTED: Aravis main (unreleased ee31d82, 2026-10-03) adds aravissrc add-reference-timestamp-meta. It attaches arv_buffer_get_timestamp() as a timestamp/x-ptp reference meta. That value is the device timestamp converted with GevTimestampTickFrequency, or host realtime when the frequency is 0. It is PTP time only if the camera is PTP-synchronized.
  BETTER: ['https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L482-L486', 'https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L526-L531']

- [partially-supported] c8: rc_genicam_api (BSD-3 Roboception code + EMVA GenICam reference implementation + bundled closed-source Baumer GigE/USB GenTL producer v2.9.2 under a Baumer EULA) targets Linux and Windows only (no macOS), describes itself as for GigE Vision 2.0 compatible cameras, and its gc_config tool toggles PtpEnable and reads PtpStatus/PtpOffsetFromMaster after PtpDataSetLatch.
  REASON: Confirmed:
- README L4-8 says 'GenICam / GigE Vision 2.0 compatible' and 'compiled under Linux and Windows'. Minimum Requirements at L33+ lists only Linux, ARM and Windows.
- LICENSE.md covers BSD-3 for rc_genicam_api/tools, Baumer for baumer/ and GenICam for genicam/.
- baumer/README.md L6 says v2.9.2.22969.
- Tag v2.8.9 is commit 1f7aad7, dated 2026-10-06.

Corrections:
1. gc_config.cc L280-299 only READS PtpEnable, PtpStatus and PtpOffsetFromMaster after calling PtpDataSetLatch. The toggle is the '-t 1|0' option, which calls setString(nodemap, "PtpEnable", ...) at L173 (help text at L331).
2. baumer/license.txt is headed as an EULA for 'Baumer Camera Explorer', but clause 1 grants MIT-style permissive rights ('free of charge ... without restriction ... sell copies'). It is closed-source binary, but not restrictive in the way 'under a Baumer EULA' implies.
3. The bundled .cti binaries sit under Ubuntu-14.04/16.04 and Win32/Win64 directories.
  CORRECTED: rc_genicam_api v2.8.9 (2026-10-06) consists of BSD-3 Roboception code, the EMVA GenICam reference implementation and a bundled binary Baumer GenTL producer v2.9.2.22969 under a permissive Baumer license text. It targets Linux and Windows and says it is for GigE Vision 2.0 compatible cameras. gc_config can switch PTP with '-t 1|0' (PtpEnable, L173), and in info mode it latches and prints PtpEnable/PtpStatus/PtpOffsetFromMaster (L280-299).
  BETTER: ['https://github.com/roboception/rc_genicam_api/blob/1f7aad7ab30d92ddd323992f9eb605b481aca252/tools/gc_config.cc#L171-L174', 'https://github.com/roboception/rc_genicam_api/blob/1f7aad7ab30d92ddd323992f9eb605b481aca252/baumer/README.md']

## Missed points

- The user's premise is wrong. GigE Vision 3.0 was released by A3 in May 2026, and its headline changes are RoCEv2 RDMA streaming (the new GVRSP protocol), zero-copy transfer and a larger control channel. The article does not mention PTP. PTP itself came with GigE Vision 2.0 (LUCID: 'has since been integrated into GigE Vision 2.0'). So single-cable PTP sync needs a GigE Vision 2.x camera with PTP and scheduled action support, not GigE Vision 3. Sources: https://www.assemblymag.com/articles/100068-a3-releases-gige-vision-30-opening-new-possibilities-in-machine-vision and https://thinklucid.com/multi-camera-synchronization-using-ptp-and-scheduled-action-commands/
- No library surveyed implements GigE Vision 3.0 GVRSP/RoCEv2 streaming. git grep -iE 'gvrsp|rocev2|rdma' found no code hits in viva-genicam, telegenic, Aravis (482547a), aravis-port or rc_genicam_api. viva-genicam's only hits were false positives in SVG and TSX files. Repos: https://github.com/VitalyVorobyev/viva-genicam https://github.com/valstad-shipworks/telegenic https://github.com/AravisProject/aravis
- aravis-port (0.2.0, 2026-10-08) calls itself 'A pure-Rust, zero-unsafe port of the GigE Vision (GEV) subset of Aravis 0.9.2', but ships only LICENSE-MIT and LICENSE-APACHE. Aravis is LGPL-2.1, so a port presented under MIT/Apache is a licensing risk worth flagging. git grep finds no ACTION_CMD or PTP code in aravis-port. https://github.com/javerik/aravis-port/blob/389d5c8d14851c2c5920ddd7ad1072932f18a0f1/README.md
- Aravis does not always give the device timestamp. If GevTimestampTickFrequency reads 0, or the payload type is unknown, ArvBuffer's timestamp_ns silently becomes the host g_get_real_time(). Any 'PTP timestamp' pipeline built on Aravis must check that the tick frequency is non-zero. https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L482-L486
- viva-genicam's cited permalink (60c9c329) is unreleased HEAD. The PyPI 0.10.0 release is tag py-v0.10.0 = d53a48f. Since then, 4 commits (2026-10-24) added real-hardware fixes from a run on an Allied Vision Manta G-125B. In that run the camera refused ACTION_CMD with NOT_IMPLEMENTED, so not every GigE Vision camera supports action commands; check GevGVCPCapability bit 6 or GevSupportedOptionScheduledAction. https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/crates/viva-gige/src/action.rs#L57-L68
- Basler's action-command doc says plain action commands do not execute 'at exactly the same time'; that needs Scheduled Action Commands. Its PTP doc lists PTP as the enabler for Periodic Signal, Scheduled Action Commands and Synchronous Free Run, which are alternatives to a host-sent trigger. https://docs.baslerweb.com/action-commands https://docs.baslerweb.com/precision-time-protocol
- The FLIR ROS driver doc warns that a camera PHC boots at zero. In SlaveOnly mode with no grandmaster it reports LIS status and its timestamps are wrong. A host ptp4l (and phc2sys) master is required, which means a NIC with PTP hardware timestamping on the host. https://github.com/ros-drivers/flir_camera_driver/blob/a73f62c2b3bd23e2e555aa8ebf38f5f02187caf0/spinnaker_camera_driver/doc/index.rst#L320-L366