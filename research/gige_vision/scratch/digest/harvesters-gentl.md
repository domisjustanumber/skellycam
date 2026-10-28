# harvesters-gentl

## Bottom line
Harvesters plus the EMVA `genicam` bindings is a workable, vendor-neutral Python consumer. It is a thin layer, though: the transport, the Windows performance filter driver, PTP support and action-command sending all live in the **GenTL producer (.cti)**, and there is no free, vendor-neutral GigE Vision producer with full features on every OS.

I ran the stack end to end in Docker with two test setups: an Aravis fake camera behind the MIT-licensed `viva_gentl.cti`, and the `viky.cti` simulator that ships inside the genicam wheel. It works. The runs also found two practical problems:
- **GIL:** [Harvesters#508](https://github.com/genicam/harvesters/issues/508) is confirmed (`fetch()` holds the GIL), so SkellyCam would need one process per camera.
- **`timestamp_frequency` bug:** `Buffer.timestamp_frequency` raises an uncaught `AttributeError` when the producer gives no ns timestamps.

## Harvesters status
- **Last release:** 1.4.3 on 2024-05-16. `master` has not moved since 2024-05-08 ([tag commit](https://github.com/genicam/harvesters/tree/383494e36ebb80e2daa271ac0e980dde2093970c)).
- **Unreleased work:** branch `dev-gendc` (last commit 2026-04-01) is versioned 1.5.0. It requires Python >=3.10, `genicam>=1.6.0` and numpy>=2 ([pyproject](https://github.com/genicam/harvesters/blob/86a93095ebb38309ff6320ccefe3a8e2a23cada9/pyproject.toml)).
- **Licence:** Apache-2.0. Supported Python versions are "defined by the genicam package" ([INSTALL.rst L23](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/docs/INSTALL.rst#L23)).

## `genicam` wheels (from the PyPI JSON)
- **1.6.0 (2026-09-01):** cp310–cp314 for win_amd64, manylinux2014 x86_64/aarch64/armv7l and **macosx_13_0_arm64**.
- **1.5.1:** has no macOS wheels.
- **Intel Mac:** the last macOS x86_64 wheel was 1.3.0 (2023).
- **Licence:** the EMVA GenICam License. It is a modified BSD that allows free binary redistribution but no modification.
- **Linux catch:** the wheel links to `libpython3.12.so.1.0`, so a stock ubuntu:24.04 venv needs `libpython3.12t64` installed (I hit this in testing).

## How frames arrive
Code references are from [core.py @1.4.3](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py).
- **Fetching:** `fetch()` ([L2520-L2568](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L2520-L2568)) is a Python loop that polls `update_event_data` with a 1 ms timeout ([L1703](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L1703), [L2412-L2473](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L2412-L2473)).
- **Image data:** `Component2DImage` wraps the producer's buffer with **zero-copy `numpy.frombuffer`** and unpacks the PFNC pixel format ([L904-L977](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L904-L977)). Leaving the `with` block hands the buffer back to the producer, so copy anything you keep.
- **Raw or compressed:** Harvesters recognises JPEG, JPEG2000 and H264 payload types but has no decoder for them ([L1272-L1325](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L1272-L1325)). The GigE test stream arrived as uncompressed `PAYLOAD_TYPE_IMAGE` Mono8.
- **Timestamps:** `timestamp_ns` comes from GenTL `BUFFER_INFO_TIMESTAMP_NS`, which [GenTL 1.6](https://www.emva.org/wp-content/uploads/GenICam_GenTL_1_6.pdf) (p. 147) requires producers to convert to ns ([L1193-L1235](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L1193-L1235)).
- **Chunk data:** it is attached automatically to `remote_device.node_map` on each fetch ([L2327-L2377](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L2327-L2377)). I confirmed this with viky.
- **Padding bug:** at [L974](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L974) the result of `numpy.delete` is thrown away, so line padding is not stripped.
- **Multi-camera:** create one ImageAcquirer per device ([upstream test](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/test/test_harvester_core.py#L162-L200)). A camera visible through several network cards is listed once per card, so de-duplicate by serial number. Otherwise opening the duplicate fails because the first handle has exclusive control (observed in testing).

## GIL test (run4)
I fetched at 25 fps in a background thread and measured an unrelated Python thread:
- **Default 1 ms poll:** its throughput halved and its wake-up latency went from 0.05 ms to 5–20 ms.
- **50 ms poll:** throughput fell to about 1/8 and wake-up latency was about 40 ms, one frame period. That shows the GIL is held while the C call is blocked.

## PTP and action commands through Harvesters
- **PTP is a camera feature.** It is SFNC 2.8 §27.3 (`PtpEnable`, `PtpStatus`, `PtpOffsetFromMaster`; all Optional). `GevIEEE1588` is deprecated ([SFNC 2.8](https://www.emva.org/wp-content/uploads/GenICam_SFNC_v2_8.pdf) pp. 529–552). You reach it through `ia.remote_device.node_map`.
- **Camera-side action setup:** SFNC ch. 14 (`TriggerSource=Action1`, Action keys and mask).
- **Host-side sending** belongs to the GenTL **Interface module**. [GenTL SFNC 1.2](https://www.emva.org/wp-content/uploads/GenICam_GenTL_SFNC_1_2.pdf) §2.2.3/§3.2.3 (pp. 26, 72–75) defines `ActionCommand`, `ActionDeviceKey/GroupKey/GroupMask`, `ActionScheduledTimeEnable/Time` and `GevActionDestinationIPAddress`, all **Recommended**, not Mandatory. Harvesters exposes `ia.interface.node_map`, so action commands work only if the producer implements these features.
- **Producer support:**
  - Balluff mvGenTLProducer: yes.
  - Allied Vision VimbaGigETL: yes, including scheduled actions.
  - The Imaging Source: has `ActionCommandToAllInterfaces`.
  - Basler pylon: "The GenTL producer for GigE Vision does not support action commands" ([26.06 notes](https://docs.baslerweb.com/pylon-software-suite-26-06-release-notes)).
  - viva-gentl: none of the action features (tested).

## Producer catalogue (details in notes)
- **Balluff/MATRIX VISION Impact Acquire 3.7.2 (2026-07-27):**
  - Covers Windows, Linux x64/arm64/armhf and **macOS ARM64**, and includes a Windows NDIS filter driver.
  - 3.7.0 added "full GEV 3.0 support including RoCEv2 (RDMA)".
  - Since 3.0.0, third-party devices need a licence: "an overlay will be added to each image once 200 have been captured" ([versionInfo](https://static.matrix-vision.com/mvIMPACT_Acquire/3.7.2/versionInfo.txt)).
- **Basler:** the EULA says it may be used "solely ... to operate a BASLER camera product", so it is vendor-locked.
- **Baumer GAPI:** vendor-neutral for GigE ([wiki](https://github.com/genicam/harvesters/wiki), [rc_genicam_api#8](https://github.com/roboception/rc_genicam_api/issues/8)). The 2019 EULA is permissive.
- **Allied Vision Vimba X:** free, with a filter driver and macOS support. Whether its GigE layer accepts other vendors' cameras is unclear.
- **Spinnaker:** supports Teledyne/FLIR/Dalsa cameras, including on Apple Silicon.
- **Pleora eBUS:** unlicensed receive adds a watermark, and its datasheet does not mention a GenTL producer.
- **Euresys Gigelink:** "any GigE Vision camera", paid add-on.
- **The Imaging Source:** a free producer, described as being for TIS cameras.
- **viva_gentl.cti:** MIT licensed, for Linux, macOS arm64 and Windows, with no filter driver. Merged 2026-10-12 and tested here.

## Stand-alone tests delivered
`scripts/harvesters-gentl/`:
- `probe_harvesters.py`: lists cameras and features and fetches frames.
- `ptp_action_harvesters.py`: enables PTP, sends scheduled action commands from each interface, and reports the timestamp spread across cameras.
- `gil_probe.py`: reproduces the GIL test.

The folder also has the Dockerfile and the run logs.

I did not run any vendor producer. Their installers or EULAs require accepting a licence, and I did not do that on the user's behalf.

## Open questions

- Does the Balluff Impact Acquire third-party-device overlay (after 200 images, since 3.0.0) also apply when mvGenTLProducer.cti is driven by an external consumer like Harvesters? Not tested, because installing requires accepting the EULA (-u/-m flags).
- Does Allied Vision's VimbaGigETL.cti discover/stream non-Allied-Vision GigE Vision cameras? The release note 'Cameras from SVS-Vistek are enabled by default' suggests vendor gating, but no explicit statement was found.
- Does the Teledyne Spinnaker GenTL producer work with non-Teledyne cameras? The EULA was not found or read.
- Licence terms and filter-driver availability of Euresys Gigelink: the product page does not state them, and the handbook PDF link returned HTML.
- Is the current Baumer GAPI EULA still as permissive as the 2019 copy bundled in rc_genicam_api? Do Baumer producers exist for macOS or Linux ARM64 today? Does Baumer's GEV producer implement GenTL-SFNC interface ActionCommand?
- Does Pleora ship a GenTL producer (.cti) at all in current eBUS SDK?
- STEMMER CVB GEVTL licensing and whether it can be used standalone by a third-party consumer.
- Multi-GigE-camera behaviour of viva_gentl.cti could not be tested with Aravis fakes: both report MAC 00:00:00:00:00:00, so device IDs collide. It needs viva-fake-gige (not in the release tarball) or real cameras.
- Real PTP lock times, achievable cross-camera timestamp spread, and scheduled-action jitter via Harvesters + a vendor producer are untested. They need the user's hardware (ptp_action_harvesters.py provided).
- GigE Vision 3 premise: Impact Acquire's changelog presents GEV 3.0 mainly as RoCEv2/RDMA streaming, and SFNC has PTP features with deprecated GevIEEE1588 predecessors. That suggests PTP predates GEV 3, but the GigE Vision spec itself (which version introduced IEEE 1588) was not read in this topic.

## Verification: Counter({'supported': 23, 'partially-supported': 3})

- [partially-supported] hv-multicam-dupes: A GigE camera reachable via several host interfaces is listed once per interface by the producer, and opening the duplicate fails because the first handle holds exclusive control, so consumers must de-duplicate by serial.
  REASON: The cited core.py lines do not show this behaviour, and the IoException is not in any saved log. I reproduced it only with viva_gentl, using an Aravis fake bound to 127.0.0.1 on a bridge network. The device list showed 'GV01 eth0' and 'GV01 lo'; create(0) succeeded and create(1) failed with 'IoException ... open the camera at 127.0.0.1: timeout waiting for acknowledgement (ID: -1010)'. With the fake bound to the eth0 IP it was listed once. viva's book documents 'One interface per network interface of the host, loopback included'. That the failure is caused by exclusive control is an inference, and other producers are untested. Also, Harvester.create({'serial_number': ...}) raises ValueError 'multiple devices found' in this case (L3070-L3071).
  CORRECTED: With viva_gentl.cti (which creates one GenTL interface per host NIC, loopback included), the same GigE camera can be enumerated under several interfaces. Opening the second entry fails with an IoException (GVCP open timeout), and Harvester.create() by serial_number raises ValueError 'multiple devices found'. De-duplicate by serial or MAC before create(). Behaviour with vendor producers is untested.
  BETTER: ['https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/book/src/gentl.md#L13-L21', 'https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L3070-L3071']

- [partially-supported] av-vimba: Allied Vision VimbaGigETL.cti 1.11.0 (Vimba X 2026-3) supports action commands (1.5.0) and scheduled action commands (1.9.1) and ships a Windows GigE filter driver (2.5.13). Vimba X states that third-party cameras and TLs are free to use.
  REASON: GigETL.html confirms 1.11.0, actions added in 1.5.0, scheduled actions in 1.9.1 and filter driver 2.5.13; it gives no dates, and nothing ties 1.11.0 to 'Vimba X 2026-3'. The compatibility page's 'Usage with cameras and TLs from third-party vendors is free of charge' is about Vimba X consuming third-party GenICam TLs and cameras in general. It does not say VimbaGigETL streams non-AV cameras, and GigETL 1.10.0 'Cameras from SVS-Vistek are enabled by default' suggests vendor gating. PTP is not mentioned on the GigETL page.
  CORRECTED: VimbaGigETL 1.11.0 supports action commands (since 1.5.0) and scheduled action commands (since 1.9.1) and pairs with Vimba GigE Filter Driver 2.5.13. Vimba X says third-party cameras and TLs can be used free of charge, but whether VimbaGigETL itself streams non-Allied-Vision GigE cameras is unverified.
  BETTER: ['https://docs.alliedvision.com/GigETL.html', 'https://docs.alliedvision.com/compatibility.html']

- [partially-supported] baumer-neutral: Baumer's GigE GenTL producer is not vendor-locked for GigE Vision: the Harvesters wiki lists it as not proprietary for GEV, and a Baumer engineer said it should work with all standard GigE Vision 2.0 cameras. A user streamed a Point Grey camera through it.
  REASON: The Harvesters wiki lists Baumer GAPI SDK as 'No for GEV and Yes for U3V' proprietary. But the commenter in rc_genicam_api#8 is heikohimu (Heiko Hirschmüller), a contributor to the Roboception repo, and the issue does not identify him as a Baumer engineer. The issue (Oct 2018) also does not say which producer was used when the Point Grey Blackfly finally streamed after a firmware update; the same user had earlier reported success with a Pleora producer. The statement was 'should work with all standard GigE Vision 2.0 cameras', and 1.x support was unclear.
  CORRECTED: The Harvesters wiki marks Baumer's GAPI GenTL producer as non-proprietary for GigE Vision. In 2018 the rc_genicam_api maintainer (not a Baumer employee, as far as the thread shows) said it 'should work with all standard GigE Vision 2.0 cameras'. Third-party streaming through it is not clearly demonstrated in that thread.
  BETTER: ['https://github.com/genicam/harvesters/wiki', 'https://github.com/roboception/rc_genicam_api/issues/8', 'https://github.com/heikohimu']

## Missed points

- The 'GigE Vision 3 is needed for PTP' premise is wrong. The SFNC 2.8 revision history (p.30, SFNC 1.5.2 Draft 2, 23.01.2012) says 'Added GigE Vision 2.0 support ... Added support for IEEE 1588 ... Added support for unconditional and scheduled action commands'. PTP and scheduled actions arrived with GigE Vision 2.0. https://www.emva.org/wp-content/uploads/GenICam_SFNC_v2_8.pdf
- Impact Acquire 3.7.0's 'full GEV 3.0 support' is RoCEv2/GVRSP streaming available only on 64-bit Windows and Linux x86_64/arm64, not macOS or armhf (versionInfo.txt, 21.05.2026 entry). https://static.matrix-vision.com/mvIMPACT_Acquire/3.7.2/versionInfo.txt
- Sending action commands from the host does not need GenTL producer support. ACTION_CMD is a GVCP UDP datagram, and viva-genicam implements it, scheduled variant included, in crates/viva-gige/src/action.rs with a Python binding in viva-pygenicam. A Harvesters app can send actions out-of-band even when the producer (viva_gentl, Basler) exposes no Interface ActionCommand. https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/crates/viva-gige/src/action.rs#L108-L141
- When a camera is enumerated on several interfaces, Harvester.create({'serial_number': ...}) raises ValueError 'multiple devices found: provide sufficient search key' (reproduced with viva_gentl plus an Aravis fake on lo with a bridge network), so de-duplication must happen before create. https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L3070-L3071
- The genicam libpython problem does not occur with uv-managed Python (python-build-standalone 3.12.15 via uv 0.13.5): genicam 1.6.0 and harvesters 1.4.3 import fine in Docker. This matters because SkellyCam uses uv. It only affects distro Pythons without libpython3.12t64. https://pypi.org/project/genicam/1.6.0/
- Both Harvesters bugs the researcher found, the discarded numpy.delete padding strip and the uncaught AttributeError in timestamp_frequency, are still present on the unreleased dev-gendc branch (86a9309, 2026-04-01; core.py ~L1076 and L1488-L1492). https://github.com/genicam/harvesters/blob/86a93095ebb38309ff6320ccefe3a8e2a23cada9/src/harvesters/core.py
- viva_gentl.cti limits: 64-bit only, the Linux build needs glibc 2.39 (Ubuntu 24.04) or newer, the macOS build is unsigned (quarantine must be cleared), and it creates one GenTL interface per host NIC including loopback. https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/book/src/gentl.md#L13-L45
- BUFFER_INFO_TIMESTAMP_NS is Optional (G/O) in GenTL 1.6. Consumers must handle its absence, and viky does not provide it. They then need BUFFER_INFO_TIMESTAMP plus a tick frequency, which is exactly the path that crashes in Harvesters 1.4.3. https://www.emva.org/wp-content/uploads/GenICam_GenTL_1_6.pdf
- Pleora's eBUS SDK datasheet lists 'Action commands' as a feature and lists no macOS support. https://www.pleora.com/wp-content/uploads/2026/03/Pleora_DS_eBUS-SDK.pdf