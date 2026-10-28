# Fact-check: rust-cpp-vendor (2026-10-25)

Sources cloned to `scratchpad/research/src/verify-rust-cpp-vendor/`. Test scripts are in `scratchpad/research/scripts/verify-rust-cpp-vendor/`.

## Verdicts
- **c1: supported.** README L28 says USB3 Vision only. lib.rs L146-150 has no gige module. 0.1.14 shipped 2024-12-05 (crates.io API). PRs #198 and #223 are open drafts (GitHub API), last updated 2026-01-13 and 2026-06-01. Nuance: `cameleon/examples/gige/register_map.rs` uses `cameleon::gige::enumerate_cameras`, which does not exist. It is a stale example and does not mean GigE support exists.
- **c2: supported.** PyPI 0.10.0 ships wheels for macOS arm64, manylinux_2_28 x86_64 and win_amd64, uploaded 2026-10-17. There is no macOS x86_64 or Linux aarch64 wheel, so those platforms need an sdist build with a Rust toolchain.
- **c3: supported, with a correction.** The permalink cites commit 60c9c329 (2026-10-24), which is 4 commits after the py-v0.10.0 tag (d53a48f). In v0.10.0, `_native.send_action` returns `(sent, acks)`. The Python wrapper turns that into `AckSummary(sent, acks)`. The 3-tuple that includes refusals exists only after the release.
  - Wire format, my test: a UDP listener on 127.0.0.1:3956 in Docker captured
    - `42 01 0100 000c ...` for an unscheduled command;
    - `42 81 0100 0014 ... 0102030405060708` for a scheduled one.
  - So the opcode is 0x0100. Flags are 0x01, plus 0x80 when scheduled. The payload is 12 bytes, or 20 when scheduled.
  - The researcher's ack test ran against viva-genicam's **own** FakeGigeCamera, which is not an independent implementation.
  - Against the Aravis fake: `AckSummary(sent=1, acks=0)`.
  - A comment in action.rs says a real Allied Vision Manta G-125B answered NOT_IMPLEMENTED.
- **c4: supported.** In v0.10.0, `time_calibrate` is at lib.rs L394+. Frame fields are `ts_dev: Option<u64>` and `ts_host: Option<SystemTime>` (frame.rs L73-75). The mapping is to the host monotonic `Instant` via GVCP register round trips. It is not PTP.
- **c5: supported.**
  - Apache-2.0 confirmed. The first commit is 2026-06-12 and v2.1.0 is 2026-10-20.
  - The command constants in gvcp.rs L26-43 have no ACTION_CMD. The only action-related items are `CAP_ACTION` and `ACTION_LATE`.
  - frame.rs fields match the claim.
  - Minor: the PyPI example uses `cam.snapshot_session().snap()`.
- **c6: supported.**
  - The enum is at arvgvcpprivate.h L267-281. Aravis names 0x0004 "BYE_CMD", but in the spec 0x0004 is FORCEIP_CMD.
  - 0.9.2 was tagged 2026-04-23 and HEAD is 482547a dated 2026-10-22.
  - aravis crate 0.11.1 shipped 2025-02-10 under BSD-2-Clause.
- **c7: supported, with a caveat.** ee31d82 (2026-10-03) is in no tag.
  - The meta uses `arv_buffer_get_timestamp`.
  - For GigE, Aravis falls back to host `g_get_real_time()` when the tick frequency is 0 (arvgvstream.c L482-486 and L530). In that case a meta labelled `timestamp/x-ptp` would carry host wall-clock time.
- **c8: partially supported.**
  - gc_config L280-299 only *reads* PtpEnable/PtpStatus/PtpOffsetFromMaster after PtpDataSetLatch. The toggle is `-t 1|0` → `setString("PtpEnable")` at L173 (help text at L331).
  - The "Minimum Requirements" section starts at L33, so L33-39 is fine.
  - The Baumer license.txt is labelled an EULA for "Baumer Camera Explorer", but clause 1 is MIT-style permissive text.
  - The bundled Baumer binaries are under Ubuntu-14.04/16.04 and Win32/Win64 directories.
- **c9: supported, with a nuance.** EULA Version 137, release date 19 October 2026. §4: "CUSTOMER may solely use the SOFTWARE for the purpose to operate a BASLER camera product".
  - pypylon's GitHub LICENSE is BSD-3, but its PyPI license metadata is "Other/Proprietary License" because the wheels bundle pylon.
  - Wheels: macOS 14 arm64/x86_64, manylinux_2_31 x86_64/aarch64, win_amd64.
- **c10: supported.** IEEE 1588-2008. GevIEEE1588* for most models; PtpDataSetLatch/PtpServoStatus/BslPtp* on ace 2 and dart M. PtpEnable appears only in the ace 2 sample code. TriggerSource=Action1. `IssueActionCommand(4711,1,0xffffffff,"192.168.1.255")`.
- **c11: supported.**
  - Product page: "supports FLIR and Dalsa USB3, GigE, 5GigE, and most 10GigE area scan cameras".
  - OSes: Windows 11, Ubuntu 20.04.5–24.04.4, macOS Sequoia/Tahoe, ARM64 Linux. Login is required to download.
  - ROS doc L320-366 and blackfly_s.yaml L79-84 match.
- **c12: supported.** The compatibility page quote matches. vmbpy 1.2.3 (2026-10-06) has wheels for manylinux_2_27 aarch64/x86_64 and win_amd64. The action_commands.py lines match.
- **c13: supported.** Feature names match, and all of them are on the device nodemap. LUCID: PTP "has since been integrated into GigE Vision 2.0".
- **c14: supported.** eBUS 7.0. GEV-Rx and Developer Seat are both needed. Watermark quote confirmed. No macOS listed.
- **c15: supported.** dpkg says `aravis-tools: /usr/bin/arv-fake-gv-camera-0.8` (0.8.30-1build2). arv-tool-0.8 is *not* in aravis-tools. arv-fake-camera.xml has no matches for 1588/Ptp/Action, either at 0.8.30 or at HEAD.
- **c16: supported (my test).** On the default bridge, a raw GVCP DISCOVERY_CMD broadcast from a python:3.12-slim container got a DISCOVERY_ACK from an Aravis fake in another container (172.17.0.3). On a user-defined network, nothing was found.

## Missed points
- **GigE Vision 3.0 does exist.** A3 released it in May 2026 ([AssemblyMag, 2026-05-13](https://www.assemblymag.com/articles/100068-a3-releases-gige-vision-30-opening-new-possibilities-in-machine-vision)).
  - It adds RoCEv2 RDMA streaming (GVRSP) and does not mention PTP.
  - PTP came with GigE Vision 2.0 ([LUCID](https://thinklucid.com/multi-camera-synchronization-using-ptp-and-scheduled-action-commands/)).
  - None of viva-genicam, telegenic, Aravis, aravis-port or rc_genicam_api contain GVRSP/RoCE code (git grep).
- **aravis-port licensing.** The README calls it "A pure-Rust ... port of the GigE Vision subset of Aravis 0.9.2", but it ships only LICENSE-MIT and LICENSE-APACHE. Aravis is LGPL-2.1, so this is a licensing risk.
- **Aravis timestamp fallback.** When the tick frequency is unknown, Aravis substitutes the host timestamp (arvgvstream.c).
