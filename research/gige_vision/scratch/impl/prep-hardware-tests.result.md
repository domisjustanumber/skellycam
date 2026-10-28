# prep-hardware-tests (completed agent result)

> **Moved 2026-10-28.** The suite now lives in `research/gige_vision/hardware_tests/` (it was `skellycam/system/diagnostics/gige/`) and the pytest in `research/gige_vision/hardware_tests/tests/` (it was `skellycam/tests/`); it is no longer part of the skellycam package, so beartype no longer checks it. The "Structured fields" block below is the agent's result as recorded, with the old paths.

## Result

The GigE Vision hardware test suite is in `research/gige_vision/hardware_tests/` (originally `skellycam/system/diagnostics/gige/`), uncommitted. There was no real camera, so it was verified only against two software emulators (Aravis `arv-fake-gv-camera-0.8` and viva-genicam's `FakeGigeCamera`). Neither emulator has PTP, a working timestamp latch or an Action trigger, so the PTP-sync and scheduled-action logic only ran against simulated registers.

On Windows and in Linux Docker, every script runs `--help` and `--selftest` cleanly (40–43 checks each), and none crashed against either emulator. Unsupported features come out as SKIP.

## What's in the folder
- **`gev_common.py`** (standard library only, shared by all scripts):
  - **Protocol packets:** GVCP and GVSP encode/decode, including ACTION_CMD, scheduled ACTION_CMD and PACKETRESEND with 64-bit block ids (`build_action_cmd` :518, `build_packetresend` :530, `parse_gvsp_header` :581).
  - **Camera and network:** a GVCP client with heartbeat and undo-on-exit of register writes (`GvcpClient` :1336); discovery on every interface (:1246); the NIC used for action broadcasts is the one the OS routes to the camera (`broadcast_for` :1222).
  - **Stream analysis:** frame completeness, resend recovery and the raw/compressed verdict (`GvspAnalyzer` :700, `compression_verdict` :909); streaming pcap/pcapng reader (:948).
  - **Small GenICam resolver** (:1625), enough to run AcquisitionStart.
  - **Socket buffer helper** (:1842) that reports when the OS caps the buffer.
- **`gev_probe.py`**: read-only inventory (`probe_camera` :61). Reports GEV version (3.x flagged), capability bits, PTP state, packet size, and which PTP/action/compression features the camera XML has. `--enable-ptp` (:262) is the only option that changes the camera.
- **`gev_ptp_sync_test.py`**: PTP enable and Master/Slave election (:87), timestamp latch (:167), inter-camera clock offset and drift (:198), and ACTION_CMD tests (:280): wrong key ignored, immediate, scheduled, and late.
- **`gvsp_capture_report.py`**: answers "raw or compressed?" from a pcap (:111) or a live stream (:309, :432). Live mode uses a 32 MiB receive buffer and warns when capped, requests resends, can save the first frame, and can hand camera control to viva-genicam (`--control viva`).
- **`viva_sync_capture_test.py`** (needs `pip install viva-genicam`):
  - enables PTP with whichever feature the camera has, reading states by name (:337);
  - free-run mode: inter-camera timestamp spread and dropped frames (:512);
  - scheduled-action mode: Action1 with Action0 fallback, sends via viva or the stdlib sender (:668, :751);
  - writes `frames.csv` (device timestamps in separate columns from host receive time) and `summary.json`.
- **`udp_recv_benchmark.py`**: host receive capability, locally or across two machines (`--role receiver/sender`, `--max-runs`).
- **`README.md`**: per-OS prerequisites (firewall rules, MTU, receive buffers, IGMP snooping, power-cycling), exact commands, how to read results, and what to send back. It states the scripts are drafts verified only on emulators.
- I also added **`skellycam/tests/test_gige_diagnostics_selftest.py`** (now `research/gige_vision/hardware_tests/tests/test_gige_diagnostics_selftest.py`), which ran every selftest through the package import so beartype checked them. Since the 2026-10-28 move it loads the sibling modules directly and beartype no longer applies.

## Design decisions
- **One shared helper file.** Scripts import `gev_common.py` from their own folder, or from the package when installed, so the folder is copied as a whole.
- **Result labels.** SKIP means the device doesn't support a feature; FAIL means it claims support but misbehaves. Exit codes: 0 = no FAIL, 1 = FAIL, 2 = nothing to test or missing dependency.
- **Runtime type checking.** Numeric parameters accept int or float because beartype rejects an int where a float is declared. The `collections.abc` imports carry `noqa: TC003` because beartype needs them at runtime.

## Bugs found and fixed while verifying
- The prototype's "frames reassembled" check passed with 0 complete frames. It now needs at least one complete frame and 99 % completeness by default (`--min-complete`).
- `--force-rcvbuf` never fell back to a normal buffer request when the OS refused.
- Discovery merged cameras that share a MAC address.
- Losing camera control mid-run crashed the viva script; both stdlib and viva paths now report it as FAIL and retake control to restore settings.
- `--control viva` crashed when viva couldn't find the camera.
- Leftover end markers corrupted the benchmark receiver's results.
- Saved XML files of identical cameras overwrote each other.
- The full list of 15 is in `hwtests.md`.

## Verification highlights
- **tshark cross-check:** tshark 4.2.2 decodes every generated packet as intended, and agrees with the pcap report (77 leaders, 77 trailers, Mono8 512x512).
- **Receive buffer:**
  - Linux's default buffer cap gives FAIL at 0–84 % complete frames, while the same stream captured with tcpdump shows 77/77.
    > **Correction (2026-10-28):** the capped-buffer runs ranged from 0 % to 96 % complete, not 0–84 %. Under the 425,984 B cap the results were 23/77 (`docker/out/single_aravis.log`), 73/76 = 96.1 % (`docker/out/final_single_aravis.log`) and 64/76 = 84.2 % (`docker/out/final2_single_aravis.log`). The OS-default 212,992 B buffer gave 0/75 and 1/73. The same applies to "frames 0-84% complete" in the structured fields below.
  - With a forced 64 MiB buffer (container with NET_ADMIN), live capture completes 76/76 frames.
- **Packet resend:** on the viva emulator, the 4 dropped packets were requested and all 4 recovered.
- **Multi-camera:** works on a dedicated Docker network, including viva free-run pairing across two Aravis emulators.
- **Cross-container benchmark:** 0 % loss at 1 and 2.5 Gbit/s.
- **beartype:** confirmed active on these modules by deliberate type violations; ruff is clean.

## Structured fields

```json
{
 "files_changed": [
  "skellycam/system/diagnostics/gige/__init__.py",
  "skellycam/system/diagnostics/gige/gev_common.py",
  "skellycam/system/diagnostics/gige/gev_probe.py",
  "skellycam/system/diagnostics/gige/gev_ptp_sync_test.py",
  "skellycam/system/diagnostics/gige/gvsp_capture_report.py",
  "skellycam/system/diagnostics/gige/udp_recv_benchmark.py",
  "skellycam/system/diagnostics/gige/viva_sync_capture_test.py",
  "skellycam/system/diagnostics/gige/README.md",
  "skellycam/tests/test_gige_diagnostics_selftest.py"
 ],
 "tests_run": [
  {
   "command": "python <gige>/<each script>.py --selftest and --help (Windows; system Python 3.12, uv Python 3.9.25 and 3.10.20 with -I)",
   "result": "All passed: gev_common 40, gev_probe 40, gev_ptp_sync_test 41, gvsp_capture_report 43, udp_recv_benchmark 42, viva_sync_capture_test 43; every --help exits 0"
  },
  {
   "command": "<scratch>/venvs/skellycam-impl/Scripts/python.exe -m pytest skellycam/tests/test_gige_diagnostics_selftest.py -p no:cacheprovider -q",
   "result": "5 passed (under beartype_this_package)"
  },
  {
   "command": "python -m skellycam.system.diagnostics.gige.<script> ... (skellycam-impl venv, against viva fakes) plus deliberate type-violation calls",
   "result": "All scripts ran with no beartype violations; deliberate bad calls raised BeartypeCallHintParamViolation, proving beartype is active"
  },
  {
   "command": "ruff check skellycam/system/diagnostics/gige skellycam/tests/test_gige_diagnostics_selftest.py (repo config) + ruff --select F,E9,B --ignore B905",
   "result": "All checks passed"
  },
  {
   "command": "bash <scratch>/impl/windows_final.sh > <scratch>/impl/windows_final.log (Windows native vs 2 viva-genicam fakes, in-process fake, harnesses, benchmark)",
   "result": "No tracebacks. Probe/ptp/live capture OK; live resend 4 requested / 4 recovered; --no-resend gives FAIL 76/79; --control viva gives clean FAIL; viva freerun and scheduled dry runs (60/60 ACKs); benchmark PASS 0% loss"
  },
  {
   "command": "docker run --rm --network none [--cap-add NET_ADMIN] ... skellycam-gige-hwtest:1 bash /out/single_aravis.sh (Aravis fake on lo)",
   "result": "Probe/ptp degrade to SKIP; capped buffer gives FAIL (frames 0-84% complete) with hint; SO_RCVBUFFORCE+NET_ADMIN gives 76/76 PASS; pcap mode 77/77 matches tshark (77 leaders/77 trailers); tshark decodes all generated GVCP/GVSP packets correctly"
  },
  {
   "command": "docker network create gige-hwtest-net; 2 Aravis fakes + 2 viva fakes in separate containers; bash /out/multi.sh and /out/multi_viva.sh in a test container",
   "result": "Broadcast discovery over bridge finds Aravis fakes; unicast ACTION_CMD ACKs; live capture 81/81 and 75/75; --control viva 75/75; viva freerun pairing across 2 Aravis fakes with CSV/JSON; Action1/latch absence gives clean SKIP"
  },
  {
   "command": "cross-container udp_recv_benchmark (--role receiver --max-runs 3 --force-rcvbuf / --role sender via docker exec)",
   "result": "0% loss at 1472 B and 8972 B at 1000 Mbit/s and 8972 B at 2500 Mbit/s"
  },
  {
   "command": "python <scratch>/impl/harness_ptp_sim.py <gige> synced|unsynced; harness_viva_ptp_sim.py lock|nolock; harness_viva_revoke.py; harness_stdlib_revoke.py",
   "result": "Simulated PTP roles/latch/offset/drift/scheduled+late actions: PASS when synced, FAIL when 2 masters / 25 ppm; viva PTP lock PASS/FAIL and restore; control revocation reported as FAIL, registers restored, outputs written"
  }
 ],
 "untested": [
  "Any real GigE Vision camera (GEV 2.x or 3.0): no hardware was available",
  "Real PTP: election, lock time, offset values, vendor PtpStatus naming, PtpMode (Allied Vision), PtpSlaveOnly (LUCID), tick-frequency change on PTP enable",
  "Bootstrap timestamp latch on real cameras (both emulators return 0 or do not implement it)",
  "Scheduled ACTION_CMDs actually triggering exposures; measured exposure-start spread; scheduled-action queue limits; ACTION_LATE responses; broadcast ACTION_CMD to real cameras; SFNC ActionSelector to bootstrap action index mapping",
  "Fire-test (do-not-fragment) packets: neither emulator implements them",
  "PACKETRESEND on real cameras, including the 64-bit block-id form and the status 0x0100 / flag 0x01 resend marker",
  "GEV 3.0 devices: extended-id-only GVSP v2 streams, DeviceTLVersionMajor=3, GevStreamingMode GVSP/GVRSP switching (--force-gvsp)",
  "Vendor-compressed pixel formats and payload types on real streams (only synthetic captures)",
  "Mini GenICam resolver on real vendor XMLs (StructReg/SwissKnife layouts); --control viva and pcap mode are the fallbacks",
  "Real NIC performance at 1/2.5/10 GbE, Windows firewall prompts, vendor NDIS filter drivers",
  "macOS (no Mac available): interface listing via ifconfig, kern.ipc.maxsockbuf behaviour",
  "Whether reading the CCP register shows other applications' control (the probe's message is hedged)"
 ],
 "notes_file": "C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/f77e9c4e-e1ea-4406-8a36-bef826a63a0e/scratchpad/impl/hwtests.md"
}
```