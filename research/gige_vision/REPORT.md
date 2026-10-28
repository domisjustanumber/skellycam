# GigE Vision cameras with PTP sync — Report

Status as of 2026-10-28: **paused since 2026-10-25**. Research and the stand-alone hardware test suite are done. The SkellyCam backend has not been started. The report ([docs/gige_vision_report.md](docs/gige_vision_report.md)) has 4 of 8 sections filled. Raw material: [RESUME.md](RESUME.md), [scratch/](scratch/) (digests, notes, logs, benchmark output), [hardware_tests/](hardware_tests/) and [workflows/](workflows/).

## Executive summary

The request was to add GigE Vision camera capture to SkellyCam, with "single-cable" PTP clock sync between cameras, and to explain how frames arrive and how PTP timing works ([RESUME.md](RESUME.md)). Nine research topics were each written up by one agent and fact-checked by a second. The 161 checked claims came out as 132 supported, 27 partly supported and 2 refuted (counts in each [scratch/digest/](scratch/digest/) file). The user's starting assumption was wrong. PTP (IEEE 1588) and scheduled action commands arrived in GigE Vision 2.0 (2011), not 3.0. GigE Vision 3.0 (May 2026) mainly adds RDMA streaming for 10 GbE and faster links, and PTP is optional in every version. Frames normally arrive as raw, uncompressed Bayer or Mono pixels over UDP. Two things limit capture: link bandwidth, and the host's ability to receive UDP bursts. A small socket receive buffer loses the tail of each frame, and several Python receive threads in one process lose 39–88% of packets at 4–8 simulated 1 GbE cameras (loopback, 1500-byte packets) because of the GIL (Python's global interpreter lock). The recommended library is viva-genicam 0.10.0, an MIT-licensed Rust library with Python wheels. It is the only open-source library found that sends scheduled action commands. The plan is to run one camera per process, which is SkellyCam's default worker mode. For SkellyCam this means three changes: a pluggable camera-backend interface, since OpenCV is hard-wired today; a separate per-frame record for device and PTP timestamps; and keeping host frame numbers as the pairing key. **No real camera was ever used.** Everything ran against two software emulators on one Windows 11 PC and in Docker under WSL2. Sync accuracy, PTP behaviour and real-NIC throughput are therefore unmeasured.

## Key findings

Confidence labels: **measured** = run here and logged; **sourced** = taken from specs, vendor documents or library source code and checked by a verifier; **computed** = arithmetic from stated inputs; **inferred** = a judgement drawn from the above.

1. **PTP is a GigE Vision 2.0 feature. GEV 3.0 adds RDMA streaming.** *Sourced.*
   - IEEE 1588 and unconditional/scheduled action commands are listed for GEV 2.0 (Nov 2011) in the SFNC 2.8 change history and in Wireshark's dissector.
   - GEV 2.1 (Aug 2018) added an updated IEEE 1588 profile.
   - GEV 3.0 was approved on 17 Apr 2026 and announced on 12–13 May 2026. It adds optional GVRSP (RDMA over RoCEv2), larger control packets, and drops legacy GVSP v1. The A3 FAQ puts RDMA at 10G and up, so it does not help 1 GbE rigs.
   - PTP is optional. A host must check GVCP capability register 0x0934 bits 0x00080000 (1588) and 0x00020000 (scheduled action), or the GenICam features.
   - Sources: [spec-versions.md](scratch/digest/spec-versions.md), [frame-transport.md](scratch/digest/frame-transport.md).
   - One verifier refutation applies here: SFNC 2.8 *does* already define GEV 3.0 features (`GevStreamingMode` = GVSP/GVRSP).

2. **Frames arrive raw and uncompressed.** *Sourced + measured on emulators.*
   - The normal payload is IMAGE (0x0001) in a PFNC pixel format (Bayer/Mono), sent over GVSP/UDP as leader + N data packets + trailer. The 64-bit device timestamp is in the leader.
   - JPEG/JPEG 2000/H.264 payload types (0x6–0x8) exist. Only one camera found (Baumer VLXT.I.JP) uses a standard compressed type. Vendor lossless schemes (FLIR, Basler Compression Beyond, LUCID QOI) need the vendor SDK.
   - Of the open-source stacks checked, Aravis returns "not supported" for compressed payloads, Harvesters has no decoder for them, and viva-genicam counts them without assembling them ([from-scratch.md](scratch/digest/from-scratch.md) missed points).
   - Every emulator capture was reported as UNCOMPRESSED by the test suite ([hwtests.md](scratch/impl/hwtests.md)).
   - Source: [frame-transport.md](scratch/digest/frame-transport.md).

3. **Bandwidth is the binding limit at 1 GbE.** *Computed* ([bandwidth.txt](scratch/research/scripts-ft/out/bandwidth.txt)).
   - Usable 1 GbE throughput is about 119.0 MB/s with 1500-byte packets and 124.0 MB/s with 9000-byte jumbo packets.
   - 1920×1200 BayerRG8 at 60 fps is 138.24 MB/s (1105.9 Mbit/s). That is 0.86 cameras per link, so not even one camera fits (single-camera maximum 51.6 fps, or 53.8 fps with jumbo frames).
   - At 30 fps the same stream is 553.0 Mbit/s, which allows 1.72 cameras per link.
   - 1440×1080 BayerRG8 at 60 fps is 746.5 Mbit/s, which allows 1.28 cameras per link. One camera fits, but two do not share a link.
   - Several cameras behind one uplink need `DeviceLinkThroughputLimit` or an inter-packet delay (SCPD).

4. **The host socket receive buffer decides whether frames arrive complete.** *Measured (emulators, loopback/Docker).*
   - A frame arrives as one burst of packets, and a small buffer drops the tail.
   - Linux in Docker caps an `SO_RCVBUF` request at 425,984 B (`net.core.rmem_max`).
   - With that cap, the Aravis emulator gave 23/77, 73/76 and 64/76 complete frames in three runs. tcpdump showed 77/77 complete on the wire, so the host socket dropped the rest.
   - With `SO_RCVBUFFORCE` at 64 MiB (needs CAP_NET_ADMIN): 76/76 complete ([hwtests.md](scratch/impl/hwtests.md) §4).
   - Earlier research and verifier runs with the capped buffer ranged from 0/50 to 28/58 complete, against 75/75 with a forced 32 MiB buffer ([from-scratch.md](scratch/digest/from-scratch.md), verifier C17). **The capped result varies a lot between runs**, but the direction is consistent.
   - Synthetic sender, 1 Gbit/s, MTU 9000: Linux's default 212,992 B buffer lost 7.23%, and the capped 425,984 B buffer lost 0.04% ([bench_linux_docker_default_rmem.txt](scratch/research/bench_linux_docker_default_rmem.txt)).
   - Windows defaulted to 64 KiB and honoured a 16 MiB request ([bench_windows_defbuf.txt](scratch/research/bench_windows_defbuf.txt), [bench_windows.txt](scratch/research/bench_windows.txt)).

5. **Several Python receive threads in one process collapse under the GIL. A single receiver is fine.** *Measured (loopback, synthetic senders, 1 Gbit/s per simulated camera).*
   - **Threads, 4 cameras at MTU 1500:**
     - Python 3.12, WSL2 Docker: 74.77% lost ([bench_multicam_linux.txt](scratch/research/bench_multicam_linux.txt)).
     - Python 3.12, Windows 11: 39.33% lost ([bench_multicam_windows.txt](scratch/research/bench_multicam_windows.txt)).
   - **Threads, 8 cameras:** 88.04% lost (Linux) and 76.71% lost (Windows).
   - **Free-threaded Python 3.14.0rc3 with the GIL off:** 0% lost at 8 cameras × 1 GbE, at both packet sizes, using 1.39 cores at MTU 1500 ([bench_multicam_linux_freethreaded.txt](scratch/research/bench_multicam_linux_freethreaded.txt)). The same build with the GIL on lost 80.49% at 4 cameras ([bench_multicam_linux_314t_gil_on.txt](scratch/research/bench_multicam_linux_314t_gil_on.txt)).
   - **One receiver, alone:** a single Python receiver at 1 Gbit/s lost 0% with 1472-byte packets. It used 31–34% of one core on Windows ([bench_windows.txt](scratch/research/bench_windows.txt)) and 21–26% in WSL2 Docker with a forced buffer ([bench_linux_docker_forced_rcvbuf.txt](scratch/research/bench_linux_docker_forced_rcvbuf.txt)).
   - **Caveat:** "one process per camera" was not benchmarked with this harness. The only multi-process data point is pyGigEVision: two receivers in two processes each got about 100% complete frames at about 200 MB/s, while two in one process fell to about 20 fps each ([pygigevision.md](scratch/digest/pygigevision.md)).
   - SkellyCam already defaults to one process per camera (`WorkerMode.PROCESS` in `skellycam/__main__.py`).

6. **viva-genicam 0.10.0 is the only open-source library found that sends scheduled ACTION_CMDs, and it releases the GIL.** *Measured on emulators + sourced.*
   - The verifier captured both the immediate and the scheduled encoding on the wire.
   - viva's own `FakeGigeCamera` acknowledged actions only when the keys matched. The Aravis emulator does not acknowledge them at all.
   - A busy Python thread kept 100–106% of its speed while frames streamed ([prep-viva-api.result.md](scratch/impl/prep-viva-api.result.md), [viva_api.md](scratch/impl/viva_api.md)).
   - Gaps in 0.10.0:
     - no PTP helpers;
     - no Python control of `SO_RCVBUF` (the engine requests max(4 MiB, 2 × frame));
     - a fixed 4-frame drop-oldest queue;
     - no open-by-IP (`discover_ip` exists only on unreleased main);
     - no host arrival timestamp on frames.
   - `ts_host` is a host↔device line fit, not a receive time. It clamps earlier ticks to a constant, and on the emulator every frame got the same `ts_host`. Store `ts_dev` instead.
   - A real Allied Vision Manta G-125B answered NOT_IMPLEMENTED to ACTION_CMD in the upstream author's own hardware run ([rust-cpp-vendor.md](scratch/digest/rust-cpp-vendor.md)), so camera support varies.
   - Sources: [rust-cpp-vendor.md](scratch/digest/rust-cpp-vendor.md), [viva_api.md](scratch/impl/viva_api.md).

7. **The other options were ruled out for concrete reasons.** *Sourced + measured on emulators.*
   - **Aravis:** no PyPI or conda-forge package, PyGObject is sdist-only, no ACTION_CMD (issue #184 has been open since 2018), and a Windows throughput issue (#752) is open ([aravis.md](scratch/digest/aravis.md)).
   - **Harvesters 1.4.3:** last released 2024-05-16. `fetch()` holds the GIL (reproduced: a 1 ms poll halved another thread's loop rate, 16.3 M to 7.96 M iterations/s, with viva_gentl). Action commands depend on the vendor producer, and Basler's producer has none ([harvesters-gentl.md](scratch/digest/harvesters-gentl.md), [run4_gil_probe.log](scratch/research/scripts/harvesters-gentl/run4_gil_probe.log)).
   - **pyGigEVision 0.2.2:** has no GenApi (no feature access by name) and no PTP or actions. In testing, the XML download read zeros (hex address parsed as decimal), Bayer/RGB frames came back wrong, frames over 2048×2048 px were dropped, 82.6% of packets got resend requests on a lossless stream, and the receiver thread dies silently once extended block ids pass 65535 ([pygigevision.md](scratch/digest/pygigevision.md)).
   - **Vendor SDKs:** mostly vendor-locked by licence or design. Allied Vision Vimba X is the partial exception, but whether its own GigE producer streams other vendors' cameras is unverified ([rust-cpp-vendor.md](scratch/digest/rust-cpp-vendor.md), [harvesters-gentl.md](scratch/digest/harvesters-gentl.md)).

8. **PTP sync has two layers: clock sync and exposure alignment.** *Sourced.*
   - The cameras elect a grandmaster among themselves (BMCA, the IEEE 1588 Best Master Clock Algorithm), so no host master is needed. The shared timescale is then arbitrary, not UTC.
   - Aligning exposures needs one of three methods: scheduled ACTION_CMD (0x0100, flag 0x80, 64-bit execution time), a vendor PTP free-run mode, or pairing frames afterwards by leader timestamp.
   - Vendor accuracy figures: Allied Vision measured under ±1 µs maximum offset over 69 h and about 125 ns between two cameras on a scope (its "within 2 µs" is a definition, not a measurement). Teledyne says "a few microseconds". LUCID's sample printout implies about 9 µs spread across 7 cameras; that figure is the researcher's arithmetic, not LUCID's.
   - Basler: IGMP snooping on the switch breaks PTP, and many models lack scheduled actions.
   - Windows' built-in PTP is a client only. macOS had no supported option found.
   - Source: [ptp-sync.md](scratch/digest/ptp-sync.md).

9. **SkellyCam integration needs a backend seam and a separate device-timing record.** *Sourced from code reading + measured with a prototype.*
   - `CameraWorker.create` always uses the OpenCV worker, so there is no backend abstraction.
   - Cameras are paired by equal host `frame_number`, and dropped device frames would be silently mis-paired.
   - The frame metadata has no field for a device timestamp.
   - Proposed design:
     - a `@runtime_checkable` `CameraBackend` Protocol;
     - a `device_timing` sub-record (not the lifecycle-timestamp dtype, which subtracts a host-clock offset);
     - new `device.*` CSV columns.
   - A prototype showed that beartype accepts a runtime-checkable Protocol and rejects a plain one ([backend-protocol-prototype.log](scratch/research/backend-protocol-prototype.log)).
   - Source: [skellycam-arch.md](scratch/digest/skellycam-arch.md).

10. **The stand-alone hardware test suite is ready but only emulator-verified.** *Measured.*
    - Six scripts are in [hardware_tests/](hardware_tests/). Five need only the standard library; `viva_sync_capture_test.py` needs viva-genicam.
    - Every `--selftest` passes on Windows (Python 3.9, 3.10 and 3.12) and in Docker (3.12).
    - Fifteen bugs were found and fixed during verification ([hwtests.md](scratch/impl/hwtests.md) §7).
    - Simulated-register harnesses exercised the PTP pass/fail logic: synced clocks gave +0.1 µs and 0 ppm (PASS); unsynced clocks gave +611,854 µs and +25 ppm (FAIL).
    - The scheduled-action test passes when the p95 exposure spread is ≤ 100 µs (default) ([hardware_tests/README.md](hardware_tests/README.md)).

## Techniques compared

### A. Libraries and approaches

| Option | Licence / packaging | Scheduled ACTION_CMD | Python threading | Platforms | Tested here | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| viva-genicam 0.10.0 | MIT; PyPI wheels | Yes (wire-verified; acked by own emulator only) | Releases GIL (measured) | win_amd64, macOS arm64, manylinux x86_64 | Windows + Docker, emulators | **Chosen** |
| telegenic 2.1.0 | Apache-2.0; PyPI wheels | No | Not measured | Win x64/arm64, macOS arm64, Linux x64/aarch64 | Docker, streamed from Aravis emulator | Fallback (needs a separate action sender) |
| Aravis 0.8.36 | LGPL-2.1+; no PyPI/conda | No (#184 open) | Not measured for GIL | Linux first; macOS via Homebrew; Windows via MSYS2, lagging | Docker, emulator | Rejected for pip/uv packaging and no actions |
| Harvesters 1.4.3 + GenTL producer | Apache-2.0 + vendor `.cti` | Only if the producer implements it | Holds GIL in `fetch()` (measured) | Depends on producer | Docker, viva_gentl and viky | Rejected |
| pyGigEVision 0.2.2 | MIT; pure Python | No | One thread per stream; GIL contention seen with 2 cameras | CI on Win + Linux | Docker, emulator | Rejected (many measured bugs); reference code only |
| Write from scratch | — | Would have to be written | Depends | Any | ~830-line stdlib client streamed 75/75 frames | Not chosen: estimated 6–18 person-weeks, versus 1–3 to adopt viva/telegenic (estimates, not measured) |
| Vendor SDKs (pylon, Spinnaker, Arena, eBUS, Vimba X) | Proprietary / vendor-locked (Vimba X partly open) | Yes for pylon, Vimba X, Arena; not verified for Spinnaker, eBUS | Not measured | Varies | Not run (EULAs) | Rejected as the default path |

Sources: [rust-cpp-vendor.md](scratch/digest/rust-cpp-vendor.md), [aravis.md](scratch/digest/aravis.md), [harvesters-gentl.md](scratch/digest/harvesters-gentl.md), [pygigevision.md](scratch/digest/pygigevision.md), [from-scratch.md](scratch/digest/from-scratch.md).

viva-genicam wins because it is the only pip-installable, vendor-neutral option that can send scheduled action commands, and it does not hold the GIL. The caveats are significant. viva-genicam is pre-1.0 and has a single maintainer. Its first PyPI release was 2026-04-14, and the from-scratch summary had this date swapped with telegenic's ([from-scratch.md](scratch/digest/from-scratch.md) missed points). It has no PTP helpers. Its action support has only been shown against its own emulator.

### B. Python receive architecture (loopback, 1 Gbit/s per simulated camera, 1472-byte packets)

| Architecture | Interpreter / OS | 4 cameras lost | 8 cameras lost | CPU (cores) at 8 cams | Verdict |
| --- | --- | --- | --- | --- | --- |
| Threads in one process | CPython 3.12, WSL2 Docker | 74.77% | 88.04% | 1.25 | Fails |
| Threads in one process | CPython 3.12, Windows 11 | 39.33% | 76.71% | 2.17 | Fails |
| Threads in one process | CPython 3.14.0rc3, GIL on | 80.49% | 91.52% | 1.26 | Fails |
| Threads in one process | CPython 3.14.0rc3t, GIL off | 0.00% | 0.00% | 1.39 | Works on loopback, but the EMVA genicam wheel that a from-scratch Python client would need has no free-threaded build |
| One receiver per process | CPython 3.12, Windows / WSL2 | — (single receiver: 0%, 31–34% / 21–26% of a core) | — | — | **Chosen**; matches SkellyCam's default `WorkerMode.PROCESS`; not benchmarked at N processes |

Sources: the `bench_multicam_*.txt` and `bench_*.txt` files in [scratch/research/](scratch/research/). With jumbo (8972-byte) packets the threaded runs did better (Windows lost 0% at 4 cameras), but Linux 3.12 still lost 13.77% at 4 cameras. All of this is loopback with no NIC interrupts or wire bursts.

### C. Exposure alignment methods (none tested on hardware)

| Method | Host traffic per frame | Vendor-neutral? | Expected alignment | Status here | Verdict |
| --- | --- | --- | --- | --- | --- |
| Scheduled ACTION_CMD | One broadcast per frame | Yes, if the camera supports it (Manta G-125B refused it; many Basler models lack it) | µs-level per vendor figures | Encoding verified; emulator ACKs only | **Primary** |
| Vendor PTP free-run (Basler Synchronous Free Run, LUCID PTPSync, AV PtpAcquisitionGateTime) | None | No | µs-level per vendors | Not tested | Per-vendor option |
| Free-run, pair by device timestamp afterwards | None | Yes | Up to half a frame period (inferred, not sourced) | Pairing logic tested on emulator (timestamps are host time there) | Fallback |

Source: [ptp-sync.md](scratch/digest/ptp-sync.md). The test suite is built to measure the first and third methods on real cameras with `viva_sync_capture_test.py` ([hardware_tests/README.md](hardware_tests/README.md)).

## Areas of interest

- **Recordings pair frames by host frame number.** A device-dropped frame would be silently paired with the wrong one. A GigE backend must keep `frame_number` as the host lockstep counter and compare it with the device block id ([skellycam-arch.md](scratch/digest/skellycam-arch.md)).
- **Prior art repeats an anti-pattern.** A branch in the user's fork (`dom/openpnp-capture-mf`) put `hardware_timestamp_ns` into the lifecycle-timestamp dtype. That is exactly the case where a host offset gets subtracted from a device-clock value ([skellycam-arch.md](scratch/digest/skellycam-arch.md)).
- **OpenCV's Bayer names are swapped relative to PFNC.** PFNC `BayerRG8` decodes with `cv2.COLOR_BayerBG2BGR`. That was verified empirically; the PFNC side of the mapping is assumed ([skellycam-arch.md](scratch/digest/skellycam-arch.md)).
- **Mono recording is broken end to end in SkellyCam.** `cv2.VideoWriter` writes 0 frames, and PyAV `bgr24` raises ([skellycam-arch.md](scratch/digest/skellycam-arch.md), verifier A9).
- **Enable PTP before opening streams.** Aravis caches the tick frequency when the stream is created (proven in Docker). Basler ace Classic/U/L cameras switch from 125 MHz to 1 GHz when PTP is enabled ([aravis.md](scratch/digest/aravis.md), [ptp-sync.md](scratch/digest/ptp-sync.md)).
- **A Windows PC probably cannot simply slave to the cameras.** Windows' inbox PTP client syncs only to grandmasters with the PTP timescale and UTC-reasonable flags set, which a free-running camera grandmaster likely lacks, so mapping camera time to PC time should use a timestamp latch bracketed by host clock reads ([ptp-sync.md](scratch/digest/ptp-sync.md)).
- **Duplicate devices on multi-NIC hosts.** Aravis's device table is last-reply-wins by id/serial/MAC. viva_gentl lists a camera once per host NIC. Open cameras by IP or MAC ([aravis.md](scratch/digest/aravis.md), [harvesters-gentl.md](scratch/digest/harvesters-gentl.md)).
- **Neither emulator implements PTP, the timestamp latch, or Action trigger sources.** The Aravis emulator reports GEV 0.0 and capability 0x0 ([hwtests.md](scratch/impl/hwtests.md)). The sync-critical path cannot be tested without hardware.

## Limitations and caveats

- **No real camera, NIC or switch was used.** Everything ran on one Windows 11 PC ("Gerald", 28 CPUs), natively and in Docker on WSL2 (kernel 5.15.153.1). The camera emulators were Aravis `arv-fake-gv-camera-0.8` (versions 0.8.26–0.8.36 across topics) and viva-genicam 0.10.0's `FakeGigeCamera`. All throughput numbers are loopback or Docker-bridge figures ([hwtests.md](scratch/impl/hwtests.md)).
- **Small samples.** The capped-buffer completeness results vary widely between runs: 0/50 to 73/76 complete frames across research, verifier and test-suite runs. Benchmarks are mostly single runs of a few seconds.
- **The Harvesters GIL magnitude depends on the producer.** The digest's "5–20 ms" wake-up latency matches the viva_gentl run (median 5.4 ms, max 21.7 ms). With viky.cti at a 1 ms poll the median was unaffected at 0.045 ms (p95 10.2 ms) ([run4_gil_probe.log](scratch/research/scripts/harvesters-gentl/run4_gil_probe.log), [harvesters-gentl.md](scratch/digest/harvesters-gentl.md)).
- **Known errors in earlier write-ups, corrected by verifiers:**
  - SFNC 2.8 does contain GEV 3.0 features ([spec-versions.md](scratch/digest/spec-versions.md)).
  - Wireshark decodes GVSP without the heuristic flag when the capture includes the SCP register write ([frame-transport.md](scratch/digest/frame-transport.md)).
  - The from-scratch summary had the viva and telegenic first-release dates reversed.
  - The pyGigEVision RGB8 failure is silent corruption (frames flagged complete), not "never completes".
  - Aravis's 100% completeness in the pyGigEVision comparison used its packet-socket path. Its plain UDP path got 81–94%.
- **Release dates differ across notes.** Aravis 0.8.36 and 0.9.2 were both tagged 2026-04-23 and published on GitHub 2026-04-26. The comparison table in [rust-cpp-vendor.md](scratch/digest/rust-cpp-vendor.md) lists "0.9.2 (2026-04-23)" as the last release, and [spec-versions.md](scratch/digest/spec-versions.md) gives "0.8.36 from 2026-04-26". The [report doc](docs/gige_vision_report.md) says viva's first release was "Apr 2026", which matches the verifier.
- **Estimates and bandwidth figures are not measurements.** The effort estimates (person-weeks) come from line counts of reference implementations, not a SkellyCam prototype. The bandwidth figures are arithmetic.
- **Old paths in raw records.** Paths in raw logs, journals and digests refer to `plans/gige-vision/`, `skellycam/system/diagnostics/gige/` or a deleted temp scratchpad ([RESUME.md](RESUME.md)). Cloned third-party repos, venvs and pcaps were not copied here.
- **Unreviewed pieces.** `scratch/research/ptp-sync-tests/gentl_ptp_sync_test.py` (Harvesters path) was never run against hardware. Only `selftest` of the research-phase `gev_ptp_sync_test.py` passed. The later version in `hardware_tests/` supersedes it.

## Proposed further investigation

1. **Run `hardware_tests/` on at least two real PTP-capable GigE cameras on one PoE switch** (probe → ptp → viva free-run → scheduled-action). *Why:* every sync claim here is unverified. *Decides:* whether the cameras support 1588 and scheduled actions, the PTP lock time, and whether the p95 exposure-start spread meets the ≤ 100 µs pass mark. It also confirms vendor feature names and ACTION_LATE behaviour.
2. **Two-PC, real-NIC receive tests** with `udp_recv_benchmark.py --role sender/receiver` at MTU 1500 and 9000, then N cameras in N processes through viva-genicam. *Why:* loopback has no interrupt load or wire bursts, and process-per-camera has not been benchmarked at N > 2. *Decides:* how many 1 GbE cameras one PC can take without loss, and whether viva's fixed 4 MiB-minimum buffer and 4-frame queue are enough.
3. **Resume the implement workflow** ([workflows/gige-implement-wf_d9795230-c81.js](workflows/gige-implement-wf_d9795230-c81.js); steps in [RESUME.md](RESUME.md)): `CameraBackend` Protocol, `OpenCVBackend` wrapper, viva GigE backend, `device_timing` record, UI pass-through, review. *Decides:* the real integration cost and whether frame-number lockstep holds with device drops. Also decide where shipped diagnostics live.
4. **Ask upstream or patch viva-genicam** for Python `rcvbuf_bytes`, `discover_ip`, a host arrival timestamp and NACK reporting. *Decides:* whether SkellyCam can avoid working around these gaps, or needs telegenic plus its own ACTION_CMD sender.
5. **Measure the scheduled-action alternatives on the target vendor** (vendor PTP free-run versus post-hoc pairing), if the cameras chosen lack scheduled actions. *Decides:* the fallback sync method.
6. **macOS check** (no Mac was available): socket-buffer limits (`kern.ipc.maxsockbuf`), the firewall, and viva's arm64 wheel. *Decides:* whether macOS is a supported GigE platform.

## Where to look

- [RESUME.md](RESUME.md): status, verified key findings, how to resume, environment notes.
- [hardware_tests/](hardware_tests/): the stand-alone test suite. [README.md](hardware_tests/README.md) is the runbook for testers; the pytest wrapper is in [tests/](hardware_tests/tests/).
- [scratch/digest/](scratch/digest/): per-topic summaries with verifier verdicts, corrections and missed points (`*.md`), plus claim lists (`*.claims.json`).
- [scratch/research/](scratch/research/): full research notes per topic, verifier notes (`verify-*.md`), benchmark output (`bench_*.txt/json`), benchmark scripts, and test scripts and logs per topic (`scripts/`, `scripts-ft/`, `ptp-sync-tests/`, `viva-api-tests/`, `results/`).
- [scratch/impl/](scratch/impl/): viva-genicam API reference ([viva_api.md](scratch/impl/viva_api.md)), the test-suite verification log ([hwtests.md](scratch/impl/hwtests.md)), Windows run output (`windows_final.log`, `win_out/`), simulated-register harnesses, and Docker files.
- [workflows/](workflows/): the research workflow (`wf_c906087f-470`) and implement workflow (`wf_d9795230-c81`) scripts, with journals holding each agent's full result.
- Report (4 of 8 sections filled): [docs/gige_vision_report.md](docs/gige_vision_report.md)
