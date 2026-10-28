# GenICam GenTL route: Harvesters + `genicam` + a GigE Vision GenTL producer (.cti)

Research date: 2026-10-25. Every statement below links to code, a spec, vendor docs, or a test run recorded in this directory.

Local artifacts (all under `C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/f77e9c4e-e1ea-4406-8a36-bef826a63a0e/scratchpad/research/`):
- `src/harvesters/`: clone of genicam/harvesters (master = tag 1.4.3 = `383494e36ebb80e2daa271ac0e980dde2093970c`)
- `src/hg-viva-genicam/`: clone of VitalyVorobyev/viva-genicam @ `60c9c329a4175290b7065a74027c151cb0acd9ef` (2026-10-24)
- `src/hg-viva-release/`: viva-genicam v0.10.0 release `.cti` (SHA-256 verified against SHA256SUMS.txt)
- `src/emva-docs/`: GenTL 1.6, GenTL SFNC 1.2, SFNC 2.8 PDFs and text extractions
- `src/impactacquire/`: Balluff Impact Acquire 3.7.2 `versionInfo.txt` + Linux installer (downloaded, NOT installed, see "EULA" below)
- `src/vendor-pages/`: saved vendor pages (Basler release notes and EULA, Allied Vision release notes, Pleora datasheet)
- `scripts/harvesters-gentl/`: Dockerfile, test scripts, run logs (`run1..run5*.log`)

---------------------------------------------------------------------------

## 1. Harvesters: status, licence, Python support

| Item | Value | Source |
|---|---|---|
| Latest PyPI release | **1.4.3**, uploaded 2024-05-16 | https://pypi.org/pypi/harvesters/json (queried 2026-10-25) |
| Latest GitHub release/tag | 1.4.3, published 2024-05-16; tag commit `383494e` dated 2024-05-08 | https://github.com/genicam/harvesters/releases/tag/1.4.3 |
| `master` last commit | 2024-05-08 (same commit as 1.4.3) | `git log` in `src/harvesters` |
| Activity since | branch `dev-gendc`: 15 commits, last 2026-04-01 (`86a9309`), adds GenDC + multipart tests, moves to `pyproject.toml` with **version 1.5.0, `requires-python >=3.10`, `genicam>=1.6.0,<2`, `numpy>=2`** -- unreleased | https://github.com/genicam/harvesters/blob/86a93095ebb38309ff6320ccefe3a8e2a23cada9/pyproject.toml ; https://github.com/genicam/harvesters/tree/dev-gendc |
| Repo | not archived, 614 stars, 106 open issues, pushed 2026-04-01 | GitHub API `repos/genicam/harvesters` |
| Licence | Apache-2.0 | https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/LICENSE.txt |
| Deps (1.4.3) | `genicam>=1.2`, `numpy`; no `python_requires` | https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/setup.py#L70-L74 |
| Supported Python | "defined by the `genicam` package" | https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/docs/INSTALL.rst#L23 |

Maintainer activity in issues: a `MEMBER` (sunavlis) responded on the macOS-wheel issue through 2026-05 (https://github.com/genicam/harvesters/issues/497). Several 2026 issues have zero maintainer replies (e.g. #502 memory leak on create/destroy, #503, #507 wrong `__version__`, #508 GIL).

## 2. `genicam` PyPI package (EMVA GenApi/GenTL bindings)

From https://pypi.org/pypi/genicam/json (queried 2026-10-25):

| version | uploaded | wheels |
|---|---|---|
| **1.6.0** | 2026-09-01 | cp310-cp314 x {`win_amd64`, `manylinux2014_x86_64`, `manylinux2014_aarch64`, `manylinux2014_armv7l`, `macosx_13_0_arm64`} (25 files) |
| 1.5.1 | 2025-11-11 | cp39-cp314 x {win_amd64, manylinux x86_64/aarch64/armv7l}; **no macOS** |
| 1.5.0 | 2025-08-29 | cp38-cp313; macOS arm64 only for cp39-cp313; Linux x86_64 only |
| 1.4.0 | 2024-05-16 | cp37-cp311; macOS arm64 cp39-cp311 |
| 1.3.0 | 2023-07-27 | last version with **macOS x86_64** wheels (`macosx_12_0_x86_64`, cp37-cp311) |

- No sdist; binary-only. Intel Macs have no wheel for genicam >= 1.4.0.
- SkellyCam (Python >= 3.11): cp311/cp312/cp313/cp314 wheels exist for Windows x64, Linux x64/arm64, macOS arm64 in 1.6.0.
- Licence: "GenICam License" (EMVA, v1.0, 2023-10-09, shipped inside the wheel as `genicam/licenses/GenICam_License.pdf`): runtime "available for free to anybody in binary format", "modified BSD", redistribution permitted **without modification** (sec. 4). Extracted text: `src/genicam-wheel/lic.txt`.
- **Linux gotcha (tested):** the Linux wheel's `_genapi.so` is linked against `libpython3.12.so.1.0`; on a stock `ubuntu:24.04` venv it fails with `ImportError: libpython3.12.so.1.0: cannot open shared object file` until `libpython3.12t64` is installed (`scripts/harvesters-gentl/ldd_genicam.log`). Static-libpython interpreters (some uv/pyenv/python-build-standalone builds) may hit the same issue -- untested.
- The wheel bundles **`viky.cti`**, a simulated "Custom" TL producer (MVTec GenTL Producer Framework; "Machine Vision Games Ltd. Viky", 3 RGBa8 400x400 cameras with chunk data). Useful for CI of a Harvesters integration without a network camera (run3 below).

## 3. How Harvesters delivers frames (code permalinks, tag 1.4.3)

Base: `https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py`

- `Harvester.add_file(cti)` / `update()` / `create(search_key)` -> `ImageAcquirer` ([L2987-L3088](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L2987-L3088)). Search key may be index, dict of device-info fields, or `DeviceInfo`.
- `ImageAcquirer.fetch(timeout, is_raw, cycle_s)` ([L2520-L2568](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L2520-L2568)) returns a `Buffer` (or **a list** if the device has >1 data stream, L2568). Use as context manager: `__exit__` re-queues the buffer to the producer ([L1184-L1188](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L1184-L1188)) -- so copy the numpy array if you keep it.
- Internally `_fetch` is a Python polling loop calling `monitor.update_event_data(timeout_ms)` with a default **1 ms** timeout ([L2412-L2473](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L2412-L2473), default at [L1703](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L1703)). Incomplete buffers are re-queued and `None` returned.
- Payload typing from GenTL `BUFFER_INFO_PAYLOADTYPE`: Image, RawData, File, **JPEG, JPEG2000, H264**, ChunkOnly, MultiPart ([L1272-L1325](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L1272-L1325); classes L1427-L1546). Only Image/MultiPart get a decoded `Component2DImage`; JPEG/H264 payload classes expose no components (no decoder). GigE Vision streams normally arrive as uncompressed `PAYLOAD_TYPE_IMAGE` with a PFNC pixel format (observed: payload type 1, `Mono8`, run1).
- `Component2DImage._to_np_array` = **zero-copy `numpy.frombuffer`** over the producer's buffer, then PFNC `expand()` for unpacking ([L904-L977](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L904-L977)). Note a latent bug: `numpy.delete(...)` result discarded at [L974](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L974), so line padding (`padding_x>0`) is not actually stripped. Bayer is delivered raw (data_format e.g. `BayerRG8`); demosaic is the consumer's job.
- Timestamps: `Buffer.timestamp_ns` -> GenTL `BUFFER_INFO_TIMESTAMP_NS`; `Buffer.timestamp` falls back to `BUFFER_INFO_TIMESTAMP` (unit producer-defined) or 0; `timestamp_frequency` tries TL/device then `GevTimestampTickFrequency` ([L1193-L1235](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L1193-L1235)). GenTL 1.6 defines `BUFFER_INFO_TIMESTAMP_NS` (id 28) as ns, producer must convert from device ticks; `BUFFER_INFO_TIMESTAMP` is "device/implementation dependent" (GenTL 1.6 pp. 140-147, https://www.emva.org/wp-content/uploads/GenICam_GenTL_1_6.pdf). For GigE Vision the device timestamp is the camera's GVSP leader timestamp, i.e. the PTP clock when PTP is enabled -- the producer side is producer-specific (viva-gentl converts ticks->ns at [stream.rs L868-L876](https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/crates/viva-gentl/src/stream.rs#L868-L876)).
- **Bug found (tested):** `Buffer.timestamp_frequency` raises a bare `AttributeError` (not caught) when the producer lacks `BUFFER_INFO_TIMESTAMP_NS` (run3 with viky.cti). Wrap in try/except.
- Chunk data: auto-attached to the **remote device node map** on each fetch by default (`ParameterKey.ENABLE_AUTO_CHUNK_DATA_UPDATE`, [L106](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L106); `_update_chunk_data` uses GenApi `ChunkAdapterGEV/U3V/Generic` [L1812-L1818](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L1812-L1818), [L2327-L2377](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L2327-L2377)). So `ia.remote_device.node_map.ChunkTimestamp.value` after fetch = that frame's chunk. Verified with viky (`ChunkNrBounces` read after fetch, run3). Upstream test: [test_manual_chunk_update](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/test/test_harvester_core.py#L940).
- Node maps for every GenTL module: `ia.system`, `ia.interface`, `ia.device`, `ia.data_streams[i]`, `ia.remote_device` each have `.node_map` ([L1968-L2005](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L1968-L2005), `Module` [L271-L470](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L271-L470)).

### Multi-camera
- One `ImageAcquirer` per device; upstream test `test_multiple_image_acquirers` creates one per discovered device and fetches from each ([test_harvester_core.py L162-L200](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/test/test_harvester_core.py#L162-L200)). Several producers can be loaded at once (README "Multiple loading of GenTL Producers", [README.rst L36-L37](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/README.rst#L36-L37)).
- **A camera reachable from several NICs is listed once per interface** (observed: same Aravis fake listed 3x via lo/eth0 with viva-gentl, run1 first attempt / run2). Opening the duplicate fails with `IoException ... timeout waiting for acknowledgement` (exclusive control already held). De-duplicate by vendor+serial before `create()`.
- **GIL (tested, confirms issue #508):** `fetch()` holds the GIL inside the C call. With a background thread fetching at 25 fps, an unrelated Python thread's throughput halves (default 1 ms poll) and Event wake-up latency goes from 0.05 ms to 5-20 ms; raising the poll to 50 ms makes the starvation worse (throughput 1/8, wake-up ~40 ms = one frame period), which shows the GIL is held while blocked in `update_event_data` ([run4_gil_probe.log](scripts/harvesters-gentl/run4_gil_probe.log); issue https://github.com/genicam/harvesters/issues/508 reports the same with Spinnaker's .cti and contrasts PySpin which releases the GIL). Implication for SkellyCam: one **process** per camera (or per small group), never N fetch threads in one process.

## 4. Tests run in Docker (no real camera)

Image: `scripts/harvesters-gentl/Dockerfile` = `ubuntu:24.04` + apt `aravis-tools aravis-tools-cli` (0.8.30, provides `arv-fake-gv-camera-0.8`) + `libpython3.12t64` + venv `harvesters==1.4.3 genicam==1.6.0 numpy==2.5.4`.
Producer: viva-genicam v0.10.0 `viva_gentl-x86_64-unknown-linux-gnu.cti` (MIT, SHA-256 `d03701ff...86763` matches release SHA256SUMS.txt).

Commands (from Git Bash, `R=<research dir>`):
```
docker build -t hg-harvesters-test scripts/harvesters-gentl
MSYS_NO_PATHCONV=1 docker run --rm --network none -v "$R/src/hg-viva-release:/cti:ro" -v "$R/scripts/harvesters-gentl:/scripts:ro" hg-harvesters-test \
  bash -c "arv-fake-gv-camera-0.8 -i 127.0.0.1 -s GV01 & sleep 2; cd /tmp && /opt/hv/bin/python -I /scripts/probe_harvesters.py /cti/viva_gentl-x86_64-unknown-linux-gnu.cti 30"
```
NB: use `--network none` or a private `--internal` network: on the default bridge, discovery picked up fake cameras from *other* containers (first run, discarded).

| run | what | result |
|---|---|---|
| run1 | viva_gentl.cti + Aravis fake (lo only) | 1 device, system TL `viva-genicam viva-gentl 0.10.0`, GenTL 1.6; 30 frames 512x512 `Mono8` uint8, payload type 1 (Image), ~24 fps, `timestamp_ns` present (ns, 40 ms median delta = 25 fps), `timestamp_frequency` 1e9. Interface module exposes **no** `ActionControl` features; Aravis fake exposes no PTP/chunk features. |
| run2 | 2 Aravis fakes (lo + eth0 on private network) | viva-gentl listed GV01 three times and never GV02; both fakes report MAC 00:00:00:00:00:00 so the producer's device ID (`GEV:00:00:00:00:00:00`) collides. Multi-GEV-camera test therefore inconclusive with Aravis fakes (not a Harvesters limitation). |
| run3 | `viky.cti` (bundled in genicam wheel), 3 cameras | 3 acquirers concurrently, 20 frames each, RGBa8 (400,400,4); chunk `ChunkNrBounces` readable from remote node map after fetch; `timestamp_ns` -> `NotAvailableException`; `timestamp_frequency` -> uncaught `AttributeError` (bug). |
| run4 | GIL probe (`gil_probe.py`) | see section 3. |
| run5 | `ptp_action_harvesters.py` against Aravis fake | script runs end to end; reports absent PTP/action/chunk features, falls back to TriggerSoftware; first software trigger timed out (fake-camera startup), rest OK. |

Not run: any vendor producer. Balluff Impact Acquire's Linux installer only installs with `-u/--unattended` or `-m/--minimal`, which per its own help text means "you explicitly accept the EULA" (installer lines 884-888). I did not accept vendor EULAs on the user's behalf. Same consideration for Baumer (its EULA says "Your use of the software constitutes your agreement").

## 5. PTP and action commands through Harvesters

- **PTP is a camera (remote device) feature**, not a GenTL feature: SFNC 2.8 sec. 27.3 "PTP Control" (`PtpEnable`, `PtpStatus`, `PtpDataSetLatch`, `PtpOffsetFromMaster`, `PtpClockID`, ...; all Level *Optional*), deprecated predecessors `GevIEEE1588*` in sec. 27.4.38-27.4.40 (SFNC v2.8, 2026-04-08, pp. 529-552, https://www.emva.org/wp-content/uploads/GenICam_SFNC_v2_8.pdf). Through Harvesters: `ia.remote_device.node_map.PtpEnable.value = True`. Grep of GenTL SFNC 1.2 finds no PTP features at system/interface level.
- Device-side action configuration is SFNC 2.8 ch. 14 "Action Control" (`ActionSelector`, `ActionDeviceKey`, `ActionGroupKey`, `ActionGroupMask`, `TriggerSource=Action1`; usage example p. 297).
- **Host-side sending of action commands = GenTL SFNC 1.2 Interface module, sec. 2.2.3 / 3.2.3 "Action Control"** (pp. 26, 72-75): `ActionControl`, `ActionCommand` (ICommand), `ActionDeviceKey`, `ActionGroupKey`, `ActionGroupMask`, `ActionScheduledTimeEnable`, `ActionScheduledTime`, `GevActionDestinationIPAddress`; TLType GigEVision, Level **Recommended** (not Mandatory) (https://www.emva.org/wp-content/uploads/GenICam_GenTL_SFNC_1_2.pdf, 2020-07-08). Harvesters gives you `ia.interface.node_map`, so if the producer implements them you can do `inm.ActionDeviceKey.value=...; inm.ActionCommand.execute()`. Whether it works is **entirely up to the producer**:
  - Balluff/MATRIX VISION mvGenTLProducer.cti: "Support for GEV Action commands added to the ... InterfaceModule" (changelog line ~4496) and "Action Commands can now be sent via limited broadcast address" (line ~675) in `versionInfo.txt` (https://static.matrix-vision.com/mvIMPACT_Acquire/3.7.2/versionInfo.txt).
  - Basler pylon: "The GenTL producer for GigE Vision does not support action commands." (pylon 26.06 release notes, 2026-06-18, https://docs.baslerweb.com/pylon-software-suite-26-06-release-notes).
  - Allied Vision VimbaGigETL.cti: "Added functionality for Action Commands" (1.5.0), "Scheduled Action Commands support" (1.9.1) (https://docs.alliedvision.com/GigETL.html).
  - The Imaging Source GEV producer: "Add ActionCommandToAllInterfaces feature" (1.3.1.860) (https://dl-gui.theimagingsource.com/en_US/a885e79c-f10a-53d7-9f65-affd27591f14/).
  - viva-gentl 0.10.0: interface node map has none of the features (run1).
- Scheduled actions need the cameras' PTP time: latch a camera timestamp (`TimestampLatch`/`TimestampLatchValue`, SFNC 3.68-3.69) and add a margin. The stand-alone script does this.

## 6. GigE Vision GenTL producer catalogue

| Producer (.cti) | Vendor-neutral? | Free? / licence | OS (latest) | Win filter driver | Action cmds via GenTL | Evidence |
|---|---|---|---|---|---|---|
| **Balluff (MATRIX VISION) Impact Acquire / mvGenTLProducer.cti** 3.7.2 (2026-07-27) | Works with third-party GenICam devices **but since 3.0.0 (2023-10-13) "third party GenICam imaging devices require a license ... Without a license, an overlay will be added to each image once 200 have been captured"** | Free download; 3rd-party use licensed | Win x86_64, Linux x86_64/arm64/armhf, **macOS ARM64** (since 2.50.0 "initially, only GEV devices") | Yes (`mvGigECapture2.sys`, NDIS 6) | Yes (InterfaceModule) | versionInfo.txt lines 38-46 ("full GEV 3.0 support including RoCEv2 (RDMA...)" in 3.7.0, 2026-05-21), 560-590, 626-640; directory listing https://static.matrix-vision.com/mvIMPACT_Acquire/3.7.2/ . Harvesters INSTALL.rst still recommends it as non-blocking (written 2018, pre-3.0.0) [INSTALL.rst L124-L128](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/docs/INSTALL.rst#L124-L128). Whether the overlay is applied when the .cti is driven by Harvesters is untested. |
| **Basler pylon** GigE GenTL producer | **No**: EULA "CUSTOMER may solely use the SOFTWARE for the purpose to operate a BASLER camera product" | Free (Acquisition Version) | GenTL officially Win, Linux x86, Linux ARM (app note AW001343, 2017); pylon itself on macOS | (pylon has GigE perf driver; not verified for GenTL) | **No** (26.06 release notes) | https://docs.baslerweb.com/pylon-end-user-license-agreement ; https://docs.baslerweb.com/pylon-software-suite-26-06-release-notes ; Harvesters wiki marks Basler "Proprietary: Yes" https://github.com/genicam/harvesters/wiki |
| **Teledyne FLIR Spinnaker** `Spinnaker_GenTL.cti` (Spinnaker 4.x) | Product page: supports "FLIR and Dalsa ... cameras"; "Teledyne GigE Vision, USB Vision cameras" -- third-party not stated | Login required for download | Win 11, Ubuntu 20.04-24.04, macOS Sequoia/Tahoe; Intel/AMD, ARM64 (Linux), Apple Silicon | "LWF Driver (Spinnaker 2.x+3.x)", "Sapera Driver (4.0)" | not documented | https://www.teledynevisionsolutions.com/products/spinnaker-sdk/ ; https://www.teledynevisionsolutions.com/support/support-center/technical-guidance/iis/distributing-spinnaker-applications/ (2023-11-07) |
| **Allied Vision Vimba X** `VimbaGigETL.cti` 1.11.0 (Vimba X 2026-3) | Vimba X: "Usage with cameras and TLs from third-party vendors is free of charge"; but GigETL 1.10.0 note "Cameras from SVS-Vistek are enabled by default" suggests vendor gating in the TL -- unclear | Free | Win, Linux, ARM64, macOS (M2 hardware listed) | Yes ("Vimba GigE Filter Driver 2.5.13") | Yes, incl. scheduled | https://docs.alliedvision.com/GigETL.html ; https://docs.alliedvision.com/compatibility.html |
| **Baumer GAPI** `bgapi2_gige.cti` | **Yes** for GEV (Harvesters wiki "No for GEV, Yes for U3V"); Baumer engineer: "should work with all standard GigE Vision 2.0 cameras"; user streamed a Point Grey Blackfly (2018) | Free; 2019 EULA bundled in rc_genicam_api is MIT-like ("free of charge ... use, copy, modify, merge, publish, distribute, sublicense") + no reverse engineering | Windows, Linux (x86_64; rc_genicam_api ships arm64/i686/x86_64 Linux builds of v2.9.2) | Yes (per Baumer Windows page, not opened) | not verified | https://github.com/genicam/harvesters/wiki ; https://github.com/roboception/rc_genicam_api/issues/8 ; https://github.com/roboception/rc_genicam_api/blob/5998f464f84113f2a33a02ffab7c88a56154f018/baumer/license.txt |
| **LUCID Arena** | not stated | Free SDK | Win (x64Release path documented) | -- | -- | Arena installs **three** CTIs (UDP, TCP, RDMA), e.g. `GenTL_RDMA_LUCID_v140.cti` https://support.thinklucid.com/using-matlab-image-acquisition-toolbox-for-windows/ |
| **Pleora eBUS SDK** | eBUS "Works with ... imaging devices from any vendor" | Paid seat + runtime licences; unlicensed receive = **watermark** | Win, Linux x86_64/ARM | "eBUS Universal Pro Driver" | -- | Datasheet (2026-03) https://www.pleora.com/wp-content/uploads/2026/03/Pleora_DS_eBUS-SDK.pdf -- datasheet does **not** mention a GenTL producer. |
| **Euresys eGrabber Gigelink** (`gigelink.cti` per secondary sources) | "Compatible with any GigE Vision camera" | Optional paid add-on (licence terms not on product page) | Win 10/11 x64, Linux x86_64/AArch64; macOS packages in eGrabber download area | not on product page | not on product page | https://euresys.com/en/Products/Machine-Vision-Software/eGrabber/eGrabber-Gigelink |
| **The Imaging Source** GEV GenTL producer 1.6.0.1250 (2026-04-20) | Description: "for GigE Vision Cameras manufactured by The Imaging Source" | Free download | Win 10/11 x64+ARM64, Ubuntu 22.04+ (x86_64, aarch64) | not mentioned | `ActionCommandToAllInterfaces` | https://dl-gui.theimagingsource.com/en_US/a885e79c-f10a-53d7-9f65-affd27591f14/ |
| **STEMMER CVB** GEVTL | Harvesters wiki: "No" (not proprietary) | CVB licensing not verified | -- | -- | -- | https://github.com/genicam/harvesters/wiki |
| **viva-genicam `viva_gentl.cti`** v0.10.0 (2026-10-17), MIT | Yes (pure GVCP/GVSP, no vendor SDK) | MIT | Linux x86_64 (glibc >= 2.39), macOS Apple Silicon, Windows x86_64 | No (user-space sockets) | **No** interface ActionControl | [book/src/gentl.md L13-L40](https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/book/src/gentl.md#L13-L40); CI job runs Harvesters 1.4.3 against it [ci.yml L116-L161](https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/.github/workflows/ci.yml#L116-L161); producer merged 2026-10-12 (PR #204), 10 stars -- very young. Tested here (run1). |
| GenTLite (MIT, Rust) | claims GEV+U3V | MIT | -- | -- | -- | README says GigE untested (search result only; not opened) -> open question |
| Aravis-based GenTL producer | none found | -- | -- | -- | -- | Aravis is a GObject API, not a .cti; no evidence of an Aravis GenTL producer found. |

macOS (Apple Silicon) GEV producers with evidence: Balluff Impact Acquire (ARM64 dmg), Teledyne Spinnaker (Apple Silicon on product page), Allied Vision Vimba X (macOS release notes referenced), viva_gentl (aarch64-apple-darwin .cti), Euresys (macOS packages listed). Combined with `genicam` 1.6.0 `macosx_13_0_arm64` wheels, Harvesters on Apple Silicon is now possible (issue #497 user confirms 1.6.0 "Works great").

## 7. Stand-alone tests for the user (machines with real cameras)

In `scripts/harvesters-gentl/`:
- `probe_harvesters.py <cti> [n]`: enumerate, de-dup, dump TL/interface/remote features (incl. GenTL-SFNC ActionControl presence, SFNC PTP/timestamp/chunk features), fetch n frames from every camera, print shape/dtype/pixel format/payload type/timestamps.
- `ptp_action_harvesters.py <cti> --frames 20 --schedule-ms 50 --out result.json`: enable PTP on all cameras, wait for Master/Slave, latch timestamps, configure `TriggerSource=Action1`, enable `ChunkTimestamp`, send (scheduled) action commands from each distinct GenTL interface, report per-trigger cross-camera spread of buffer and chunk timestamps; falls back to software trigger if the producer has no interface action features.
- `gil_probe.py <cti> [idx] [poll_ms]`: reproduces Harvesters issue #508 on the user's producer.

Install: `pip install harvesters==1.4.3 genicam==1.6.0 numpy` (Python 3.10-3.14; Linux needs shared libpython).
