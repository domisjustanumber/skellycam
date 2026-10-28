# Fact-check: harvesters-gentl (2026-10-25)

Working dir: `scratchpad/research/src/verify-harvesters-gentl/` (harvesters clone, viva clone at 60c9c329, EMVA PDFs re-downloaded, vendor pages).
Test scripts: `scratchpad/research/tools-verify/hg/` (v_tsfreq.py, v_gil.py, v_dupes.py, v_serial.py). All run in Docker image `hg-harvesters-test` (ubuntu:24.04 + harvesters 1.4.3 + genicam 1.6.0 + numpy 2.5.4 + aravis-tools), using the viva_gentl v0.10.0 .cti from `src/hg-viva-release/`.

## Independent tests I ran

1. timestamp_frequency bug (viky.cti, `--network none`):
   `docker run --rm --network none -v .../tools-verify/hg:/v:ro hg-harvesters-test /opt/hv/bin/python -I /v/v_tsfreq.py /opt/hv/lib/python3.12/site-packages/genicam/viky.cti`
   -> Device.timestamp_frequency raises `_gentl.NotAvailableException ... Timestamp not handled in this example`; then `b.timestamp_frequency` raises bare `AttributeError` from harvesters core.py L232 (`_Delegate.__getattr__`) because `GevTimestampTickFrequency` is absent from the node map and only `GenTL_GenericException` is caught (core.py L1228-L1232). Same code still present in dev-gendc (core.py L1488-L1492 on 86a9309).
   Also: Component2DImage data is a view (`data.base is not None`, `OWNDATA False`) for RGBa8 -> zero-copy confirmed.
2. GIL (viva_gentl + `arv-fake-gv-camera-0.8 -i 127.0.0.1`), other thread does `time.sleep(0.001)` and measures overshoot:
   - 2 fps, update timeout 1 ms: idle 0.08 ms -> live median 5.6 ms (= Python 5 ms switch interval)
   - 2 fps, update timeout 1000 ms: idle 0.09 ms -> live median **499 ms** (whole inter-frame gap)
   - 25 fps, update timeout 1000 ms: live median 39 ms (= frame period)
   => the blocking `update_event_data` (genicam SWIG call) does not release the GIL. Confirms issue #508.
   Caveat from researcher's own run4 log: with viky.cti at 1 ms poll the median latency was unaffected (0.045 ms; p95 10 ms), so "5–20 ms" is producer/timing dependent.
3. Duplicates per interface (viva_gentl, bridge network, fake bound on 127.0.0.1):
   device list: `GEV:00:00:00:00:00:00 GV01 eth0` and `... GV01 lo`; create(0) OK; create(1) -> `IoException ... open the camera at 127.0.0.1: timeout waiting for acknowledgement (ID: -1010)`.
   With fake bound to the container eth0 IP: listed once only.
   `h.create({'serial_number':'GV01'})` -> `ValueError multiple devices found: provide sufficient search key` (core.py L3070-L3071).
   viva book states the design: "One interface per network interface of the host, loopback included".
4. genicam libpython: stock `ubuntu:24.04` + python3-venv + `pip install genicam==1.6.0` -> `ImportError: libpython3.12.so.1.0` for both genapi and gentl; after `apt install libpython3.12t64` import OK.
   uv-managed CPython 3.12.15 (python-build-standalone, `ghcr.io/astral-sh/uv:debian`, uv 0.13.5): `import genicam.genapi, genicam.gentl; from harvesters.core import Harvester` OK even though ldd still says libpython "not found" -> the issue only bites distro Pythons without the shared lib package.

## Per-claim verdicts (short)
- hv-release: supported (PyPI JSON: 1.4.3 2024-05-16; git: 1.4.3 = master = 383494e 2024-05-08; dev-gendc 86a9309 2026-04-01, version 1.5.0, requires-python >=3.10, genicam >=1.6.0,<2, numpy >=2,<3).
- hv-license: supported (LICENSE.txt Apache 2.0; INSTALL.rst L23).
- genicam-wheels: supported (PyPI JSON; 1.6.0 drops cp39; 1.5.1 has cp39–cp314 and no mac; last x86_64 mac 1.3.0 2023-07-27; first arm64 mac 1.4.0 2024-05-16; no sdists ever).
- genicam-libpython: supported (reproduced); add that uv-managed Python works.
- genicam-license: supported (GenICam_License.pdf in wheel: "available for free ... in binary", "modified BSD", "without modification", "must not modify").
- hv-zero-copy: supported (frombuffer at L969-L970; __exit__ -> queue at L1187-L1188). Nuance: pf_proxy.expand() can copy for packed formats.
- hv-payload-types: supported (L1279-L1325; PayloadJPEG/JPEG2000/H264 classes L1473-L1510 build no components).
- hv-timestamps: supported (GenTL 1.6 p.147 BUFFER_INFO_TIMESTAMP_NS, level G/O = optional).
- hv-tsfreq-bug: supported (reproduced; root cause L1230 / L232).
- hv-chunk: supported (default True at L1617; applied in _finalize_fetching_process L2489; adapter bound to remote_device.node_map L1729-L1730). L106 is the enum key.
- hv-gil: supported (reproduced, stronger evidence); magnitude producer dependent.
- hv-multicam-dupes: partially supported (reproduced with viva only; cited core.py lines do not show it; "exclusive control" is inference; other producers untested).
- hv-e2e: supported (reproduced Mono8 512x512 at ~25 fps in my GIL runs).
- gentl-sfnc-action: supported (GenTL SFNC 1.2.0 2020-07-08 Table 2-7 p.26, §3.2.3 Level Recommended, TLType GigEVision).
- sfnc-ptp: supported (SFNC 2.8 2026-04-08, §27.3 pp.529-534 Optional; §27.4.38 GevIEEE1588 deprecated "See PtpEnable"; §14 Action Control).
- viva-no-action: supported for viva-gentl (no "action" string anywhere in crates/viva-gentl), but viva-gige implements ACTION_CMD incl. scheduled (crates/viva-gige/src/action.rs) and exposes it to Python (crates/viva-pygenicam/src/gige.rs).
- basler-no-action: supported (26.06, release date 2026-06-18, Restrictions: "GenTL/GigE: The GenTL producer for GigE Vision does not support action commands."; EULA §4 "solely use the SOFTWARE for the purpose to operate a BASLER camera product unless otherwise negotiated"; §3.1.1 Acquisition Version "solely allows CUSTOMER to operate Basler hardware products").
- balluff-impact: supported (versionInfo 3.7.2 27.07.2026; 3.7.0 21.05.2026 GEV 3.0 incl. RoCEv2 — **only 64-bit Windows and Linux x86_64/arm64**; 3.0.0 13.10.2023 overlay after 200 images; 2.50.0 macOS 12 ARM64 "initially only GEV devices"; mvGigECapture2.sys NDIS filter; action cmds L4496, L675, L989). Package listing: x86_64 exe, x86_64/arm64/armhf linux .sh, ARM64 macOS dmg.
- av-vimba: partially supported (GigETL 1.11.0, 1.5.0 actions, 1.9.1 scheduled, filter driver 2.5.13 — confirmed; compatibility page "Usage with cameras and TLs from third-party vendors is free of charge" refers to Vimba X consuming third-party TLs, not VimbaGigETL streaming third-party cameras; 1.10.0 "Cameras from SVS-Vistek are enabled by default" implies gating; no date on page).
- baumer-neutral: partially supported (wiki: "No for GEV and Yes for U3V"; but heikohimu = Heiko Hirschmüller, rc_genicam_api contributor, not identified as a Baumer engineer; the issue does not say which producer streamed the Point Grey camera; 2018 statement).
- tis-action: supported (1.6.0.1250 2026-04-20; Win10 x64, Win11 x64/ARM64, Ubuntu 22.04+; 1.3.1.860 "Initial release for Linux x86_64 and aarch64" and "Add ActionCommandToAllInterfaces feature").
- pleora-watermark: supported (datasheet: "Unlicensed Receive applications will introduce a watermark"; no GenTL/.cti mention). Datasheet also lists "Action commands" and no macOS.
- spinnaker: supported (product page + distribution page "Spinnaker_GenTL.cti for Spinnaker 4.x or newer").
- lucid-3cti: supported (only filename given is "GenTL_RDMA_LUCID_v140.cti.not_used" in a rename step).
- euresys: supported for the JSON claim; the summary's "paid add-on" is not stated on the page (only "optional library", product code PC4400, "Where to buy").
- viky-bundled: supported (reproduced 3 devices).

## Missed points
- PTP is not a GigE Vision 3 feature: SFNC 2.8 revision history (p.30, SFNC 1.5.2 draft 2, 2012-01-23) "Added GigE Vision 2.0 support ... Added support for IEEE 1588 ... Added support for unconditional and scheduled action commands".
- Impact Acquire's GEV 3.0/RoCEv2 (GVRSP) path is Windows x64 + Linux x86_64/arm64 only, not macOS.
- Host-side ACTION_CMD is a plain GVCP UDP datagram; it can be sent without producer support (viva-gige action.rs, Python binding in viva-pygenicam).
- Harvesters create() with a dict search key raises ValueError when the same camera is enumerated on multiple interfaces.
- genicam import problem does not occur with uv-managed Python (relevant: SkellyCam uses uv).
- viva_gentl Linux build needs glibc 2.39 (Ubuntu 24.04)+, 64-bit only, macOS build unsigned (book/src/gentl.md).
- Bugs (padding, timestamp_frequency) are still present on dev-gendc.
- Issue #508 opened 2026-08-19, open, no maintainer reply; covers try_fetch as well.
