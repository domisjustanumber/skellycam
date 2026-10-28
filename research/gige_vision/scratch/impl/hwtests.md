# GigE Vision hardware test suite: verification log

> **Moved 2026-10-28.** The suite moved out of the skellycam package, from `skellycam/system/diagnostics/gige/` to `research/gige_vision/hardware_tests/`, and the pytest moved to `research/gige_vision/hardware_tests/tests/`. The paths below point at the new location. The runs in section 2 were made through the old package import (under beartype) and are kept as recorded; beartype no longer applies to these scripts.

Deliverable: `C:/Users/Dom/GitHub/freemocap/skellycam/research/gige_vision/hardware_tests/` (originally `skellycam/system/diagnostics/gige/`). It contains
`gev_common.py`, `gev_probe.py`, `gev_ptp_sync_test.py`, `gvsp_capture_report.py`, `udp_recv_benchmark.py`,
`viva_sync_capture_test.py`, `README.md` and `__init__.py`. There is also a pytest at
`C:/Users/Dom/GitHub/freemocap/skellycam/research/gige_vision/hardware_tests/tests/test_gige_diagnostics_selftest.py` (originally `skellycam/tests/`).
Nothing was committed.

No real GigE Vision camera was available. Everything below ran against:

- **Aravis** `arv-fake-gv-camera-0.8` (aravis-tools 0.8.30, Ubuntu 24.04 Docker). It reports GEV 0.0 and capability 0x0. It has no latch, no PTP, no ACTION_CMD, no resend and no fire-test.
- **viva-genicam 0.10.0** `FakeGigeCamera`. It reports GEV 2.0 and capability 0x08000027 (no 1588 or action bits). It does ACK ACTION_CMD when the keys match, supports PACKETRESEND and has a GenICam TimestampLatch. Its bootstrap latch returns 0, and it has no Action trigger source.
- **Scratch harnesses** that inject simulated PTP and capability registers, simulated clocks, and camera-side control revocation. They reach the code paths that only real PTP cameras exercise.

Abbreviations below: `<scratch>` = `C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/f77e9c4e-e1ea-4406-8a36-bef826a63a0e/scratchpad`, `<gige>` = `C:/Users/Dom/GitHub/freemocap/skellycam/research/gige_vision/hardware_tests` (the runs were made at the old location `C:/Users/Dom/GitHub/freemocap/skellycam/skellycam/system/diagnostics/gige`).

## Environments

| Env | Details |
|---|---|
| Windows 11 (host "Gerald", 28 CPUs, 8 IPv4 interfaces, including 5 on 169.254/16) | system Python 3.12.13 without viva; `<scratch>/venvs/viva-win` = Python 3.12 + viva-genicam 0.10.0 + numpy; uv Python 3.9.25 and 3.10.20 |
| SkellyCam test env | `<scratch>/venvs/skellycam-impl`, created with `UV_PROJECT_ENVIRONMENT=<scratch>/venvs/skellycam-impl uv sync --all-extras --group dev --frozen`, plus `uv pip install viva-genicam==0.10.0`. The repo's `.venv` was not touched. |
| Docker image `skellycam-gige-hwtest:1` | `<scratch>/impl/docker/Dockerfile`: ubuntu:24.04, aravis-tools 0.8.30, tcpdump, tshark 4.2.2, python3.12, `/opt/viva` venv with viva-genicam 0.10.0. Docker 29.9.2 on WSL2 (kernel 5.15.153.1). |

## 1. Offline selftests, `--help`, Python versions

Commands (Windows, Git Bash; repeated in Docker):

```
python <gige>/gev_common.py
python <gige>/<script>.py --selftest        # each of the 5 scripts
python <gige>/<script>.py --help
$(uv python find 3.9)  -I <gige>/<script>.py --selftest ; ... --help
$(uv python find 3.10) -I <gige>/<script>.py --selftest ; ... --help
```

**Results:** every run passed. Same results on Windows 3.12 / 3.10 / 3.9 and Docker 3.12.

```
== gev_common selftest: 40 passed, 0 failed
== gev_probe selftest: 40 passed, 0 failed
== gev_ptp_sync_test selftest: 41 passed, 0 failed
== gvsp_capture_report selftest: 43 passed, 0 failed
== udp_recv_benchmark selftest: 42 passed, 0 failed
== viva_sync_capture_test selftest: 43 passed, 0 failed
<each> --help exit 0
```

**Coverage:**

- ACTION_CMD immediate and scheduled encoding, against known bytes.
- PACKETRESEND with 16-bit and 64-bit block ids.
- READREG, WRITEREG, READMEM and DISCOVERY encoding; ack decoding.
- DISCOVERY_ACK decoding.
- Capability bits, PFNC names and bits-per-pixel, OpenCV Bayer hint, tick conversion.
- GVSP standard and extended-ID leader, trailer and resend-flag decoding.
- Analyser:
  - completeness: 3 complete, 1 incomplete, 1 with the trailer missing;
  - block-id gap detection;
  - fps from leader timestamps;
  - verdicts UNCOMPRESSED, COMPRESSED (JPEG), LIKELY-COMPRESSED (custom PFNC, undersized frames).
- pcap and pcapng round trips, including a 128-byte snaplen.
- MiniGenApi: Command to a BigEndian IntReg; MaskedIntReg bit; StructEntry LSB/MSB enum; pAddress + LittleEndian.
- XML feature report.
- pcap-mode run on a synthetic capture: the non-GVSP flow is ignored, and the completeness check FAILs (2 of 3 frames).
- Free-run pairing and scheduled-action matching math.
- Benchmark header and line-rate arithmetic.

`python viva_sync_capture_test.py` without viva-genicam installed prints the install hint and exits 2.

## 2. SkellyCam package import under beartype, and lint

Recorded at the old package location (before 2026-10-28). The current equivalent, from the repo root, is `python -m pytest research/gige_vision/hardware_tests/tests -q` (5 passed, no beartype), and scripts are run as `python research/gige_vision/hardware_tests/<script>.py`.

```
cd C:/Users/Dom/GitHub/freemocap/skellycam
<scratch>/venvs/skellycam-impl/Scripts/python.exe -m pytest skellycam/tests/test_gige_diagnostics_selftest.py -p no:cacheprovider -q
  -> 5 passed
```

Proof that beartype is active on these modules: each call raised `BeartypeCallHintParamViolation` when
imported through the package.

- `gev_common.percentile("not a list", 50)`
- `gev_common.pfnc_name("0x01080001")`
- `gev_probe._hex("x")`

Every script was run as a package module (`python -m skellycam.system.diagnostics.gige.<script>`) in
skellycam-impl against viva fakes, with no beartype violation or traceback:

- probe; ptp test; gvsp live (2 packets resent, 2 recovered); gvsp pcap;
- udp benchmark (local, spawn children);
- viva free-run; viva scheduled dry run with the stdlib sender (30/30 ACKs).

Ruff:

- `ruff check skellycam/system/diagnostics/gige skellycam/tests/test_gige_diagnostics_selftest.py` passes with the repo config (TC rules).
- Extra `ruff --select F,E9,B --ignore B905` passes. B905 (`zip(strict=)`) is ignored because the scripts support Python 3.9.
- `collections.abc` imports carry `# noqa: TC003` because beartype resolves annotations at runtime, as pyproject.toml advises.

## 3. Windows native, against viva-genicam fakes

Full script: `<scratch>/impl/windows_final.sh`. Full output: `<scratch>/impl/windows_final.log`. Artifacts: `<scratch>/impl/win_out/`.

Fakes run out of process: `<scratch>/impl/run_viva_fakes.py -n 2 --drop "3:5,4:10,4:11,6:100"` (127.0.0.1 and 127.0.0.2, BayerRG8 640x480).

| Command | Result |
|---|---|
| `gev_probe.py --timeout 1` (broadcast on 8 interfaces, no cameras) | lists the interfaces; FAIL "no GigE Vision camera answered..." with hints; exit 2 |
| `gev_probe.py --include-loopback --no-xml` (fake on 127.0.0.1) | broadcast discovery finds it; exit 0 |
| `gev_probe.py --ip 127.0.0.1 --ip 127.0.0.2 --json probe.json --save-xml xml` | both found; GEV 2.0; capabilities `ccp_application_port_ip, pending_ack, packet_resend, write_mem, concatenation`; PTP and actions SKIP; XML 45,901 B, 161 nodes; TriggerSource `Line1, Software`; readiness WARN; table printed; exit 0 |
| `gev_ptp_sync_test.py --ip .1 --ip .2 --enable-ptp --ptp-timeout 5 --duration 2 --no-program-keys --device-key 0x42 --group-key 1 --group-mask 1` | 1588 SKIP; latch SKIP ("always 0"); wrong key ignored PASS; immediate ACK SUCCESS from both PASS; scheduled SKIP (no clock); exit 0. The fakes counted `actions 1` each. |
| `gvsp_capture_report.py --ip 127.0.0.1 --seconds 3 --save-frame frames` | 79/79 complete; UNCOMPRESSED (307,200 B/frame = BayerRG8 640x480); OpenCV hint `COLOR_BayerBG2BGR`; **resend: 4 packets in 3 ranges requested, 4 recovered** (the dropped packets); .raw/.json/.pgm saved; exit 0 |
| `gvsp_capture_report.py --ip 127.0.0.2 --seconds 3 --no-resend` | 76/79 complete, 4 missing packets: **FAIL** 96.2 % < 99 %; exit 1 |
| `gvsp_capture_report.py --ip 127.0.0.2 --control viva` (viva cannot discover .2) | clean FAIL "take control: viva-genicam did not discover"; exit 1 |
| `viva_sync_capture_test.py --fake-cameras 1 --duration 3` | PTP SKIP (no features); 79 frames, 0 lost, PASS; frame-rate WARN (the emulator gives about 26 fps for 30 requested); CSV and JSON written; exit 0 |
| `viva_sync_capture_test.py --fake-cameras 1 --mode scheduled-action` | SKIP "TriggerSource has none of Action1,Action0 (entries: Line1, Software)"; exit 0 |
| `... --mode scheduled-action --skip-trigger-config --device-key 0x42 --group-key 1 --group-mask 1 --triggers 60` | 60/60 ACKs (viva sender); 60/60 matched **by order**, which is a WARN because the fake's frame timestamps restart at acquisition start; exit 0 |
| `udp_recv_benchmark.py --sizes 1472,8972 --rates 1000,0 --seconds 2` | 1472 B at 1000 Mbit/s: 0 % loss, 84.9 kpps, 33 % CPU, PASS. 8972 B: 0 %, PASS. Unpaced 238.5 / 205.8 kpps. SO_RCVBUF 32 MiB honoured (default 64 KiB). |
| `--role receiver --max-runs 2` plus `--role sender --rates 800 --sizes 1472,8972` | 203,808/203,808 and 33,456/33,456 received; PASS |
| Python 3.9: benchmark, probe, live capture, ptp action test | all ran (53/53 frames complete; ACK SUCCESS) |

## 4. Docker, single container, `--network none`: Aravis fake on loopback

```
MSYS_NO_PATHCONV=1 docker run --rm --network none [--cap-add NET_ADMIN] -v "<gige>:/gige:ro" -v "<scratch>/impl/docker/out:/out" skellycam-gige-hwtest:1 bash /out/single_aravis.sh
```

- Script: `<scratch>/impl/docker/out/single_aravis.sh`.
- Logs: `final_single_aravis.log` (default capabilities) and `final2_single_aravis.log` (final code, `--cap-add NET_ADMIN`).
- Earlier logs: `single_aravis.log`, `force_rcvbuf_nocap.log`, `force_rcvbuf_netadmin.log`.

| Command | Result |
|---|---|
| `gev_probe.py --ip 127.0.0.1 --save-xml` | GEV "0.0", WARN "invalid; emulator?"; capabilities none; PTP and actions SKIP; XML 15,975 B, 69 nodes; exit 0 |
| `gev_ptp_sync_test.py --ip 127.0.0.1 --enable-ptp` | 1588 SKIP; latch SKIP (always 0); action keys SKIP (no capability); exit 0, no crash |
| `gvsp_capture_report.py --ip 127.0.0.1 --seconds 3` (rmem_max cap: 425,984 B) | WARN CAPPED + `sysctl` hint; kernel RcvbufErrors WARN; **FAIL** 23/77 (first run), 73/76, 64/76; exit 1 |
| same with `--rcvbuf 0` (212,992 B) | FAIL 0/75 and 1/73 complete; thousands of kernel drops |
| same with `--force-rcvbuf --packet-size 8000 --test-packet`, **no** NET_ADMIN | FORCE gets EPERM, falls back to SO_RCVBUF 425,984 (WARN); test packet WARN (not implemented or MTU); FAIL 0/76 |
| same **with** `--cap-add NET_ADMIN` | SO_RCVBUFFORCE gives 67,108,864 B, PASS; **76/76 complete**, PASS |
| `tcpdump -i lo -s 128` during the capped run, then `gvsp_capture_report.py --pcap aravis_live.pcap --tick-hz 1e9` | **77/77 complete** on the wire (the host socket dropped the rest). Mono8 512x512; UNCOMPRESSED (262,144 B/frame); 25.00 fps from device timestamps; 1400 B packets; GVCP commands seen READREG 12 / READMEM 33 / WRITEREG 8 |
| tshark 4.2.2 on the same pcap | leaders 77, trailers 77; `0x0001 0x01080001 512 512` matches the report |
| tshark on `selftest_gvcp.pcap` (generated) | ACTION_CMD flags 0x01 / 0x81, device key 0x12345678, group key 1, mask 0xffffffff / 1, Action Scheduled Time 0x000001e23f5a1000; PACKETRESEND 16-bit (block 0x1234, ids 5..9) and 64-bit (block 0x0000000100000002, ids 5..9, flag 0x10); READREG, WRITEREG, READMEM count 512, DISCOVERY flags 0x11 |
| tshark `-d udp.port==40000,gvsp` on `selftest_gvsp.pcap` | standard leader block 7, BayerRG8 64x48, ts 0x075bcd15; extended-ID (format 0x81/0x83) block 8589934592, Mono8 |
| `udp_recv_benchmark.py` local with the capped buffer | WARN capped; 0 % loss when the container was idle; 0.5–1.7 % loss (FAIL, kernel RcvbufErrors) while the fake camera was streaming in the same container. With `--force-rcvbuf` + NET_ADMIN: PASS 0 %. |

## 5. Docker, dedicated network: multi-camera

```
docker network create --subnet 172.31.77.0/24 gige-hwtest-net
docker run -d --rm --name gx-arv1 --network gige-hwtest-net --ip 172.31.77.11 -v "<gige>:/gige:ro" skellycam-gige-hwtest:1 arv-fake-gv-camera-0.8 -i eth0
docker run -d --rm --name gx-arv2 --network gige-hwtest-net --ip 172.31.77.12 skellycam-gige-hwtest:1 arv-fake-gv-camera-0.8 -i eth0
docker run -d --rm --name gx-viva1 --network gige-hwtest-net --ip 172.31.77.21 -v "<scratch>/impl/docker/out:/out" skellycam-gige-hwtest:1 /opt/viva/bin/python /out/run_viva_fakes.py --ips 172.31.77.21 --seconds 900
docker run -d --rm --name gx-viva2 ... --ip 172.31.77.22 ... --ips 172.31.77.22
docker run --rm --name gx-test --network gige-hwtest-net --ip 172.31.77.100 --cap-add NET_ADMIN -v "<gige>:/gige:ro" -v "<scratch>/impl/docker/out:/out" skellycam-gige-hwtest:1 bash /out/multi.sh        # -> final_multi.log
docker run --rm ... bash /out/multi_viva.sh                                                                                                                                                                  # -> final_multi_viva.log
docker rm -f gx-arv1 gx-arv2 gx-viva1 gx-viva2; docker network rm gige-hwtest-net
```

| Command | Result |
|---|---|
| `gev_probe.py` (broadcast; test container has `lo` + `eth0 172.31.77.100/24`) | finds both Aravis fakes over the bridge. The viva fakes are bound to their unicast IP, so they cannot hear broadcasts; that is an emulator limitation, and unicast works. exit 0 |
| `gev_ptp_sync_test.py --enable-ptp` (all found) | all SKIP, clean; exit 0 |
| `gev_ptp_sync_test.py --ip .21 --ip .22 --no-program-keys --device-key 0x42 ...` (auto → subnet broadcast 172.31.77.255) | wrong key ignored PASS; immediate: SKIP for both ("no ACK, camera does not advertise action"); the fakes can't hear broadcasts |
| same with `--action-dest unicast` | immediate ACK SUCCESS from both, PASS |
| `gvsp_capture_report.py --ip 172.31.77.21 --force-rcvbuf` (viva fake, stdlib control) | 81/81 complete, BayerRG8, UNCOMPRESSED; exit 0 |
| `gvsp_capture_report.py --ip 172.31.77.11 --force-rcvbuf` (Aravis fake) | 75/75 complete, Mono8, UNCOMPRESSED; exit 0 |
| `gvsp_capture_report.py --ip 172.31.77.12 --control viva` (multi_viva) | viva-genicam takes control, the stdlib socket receives: 75/75 complete; exit 0 |
| `gvsp_capture_report.py --ip 172.31.77.22 --control viva` | clean FAIL "viva-genicam did not discover"; exit 1 |
| `viva_sync_capture_test.py --ip 172.31.77.11 --ip 172.31.77.12 --fps 25 --duration 6 --skip-ptp` (two Aravis fakes over viva) | 151–152 frames each. 1–2 incomplete frames (no resend in the Aravis fake) gave a FAIL at the 0.5 % limit, which is a real detection. Pairing 98.7 % (INFO: clocks not PTP-synced). Spread median 0.0 / p95 1.0 / max 3654 µs. Phase drift +21.5 ppm. frames.csv and summary.json written. |
| same, `--expect-aligned` | spread is still INFO, because PTP is not active (by design) |
| `--mode scheduled-action` against the Aravis fakes | SKIP: TriggerSource has only Line0 and Software |
| `--mode scheduled-action --skip-trigger-config` against the Aravis fakes | SKIP: "camera 0's timestamp latch returns 0" |
| `--fake-cameras 1` free-run and scheduled dry run (viva and stdlib senders) | 60/60 ACKs with each sender. 2–3 incomplete frames in Docker (viva receiver and fake in one process) gave a FAIL, which is a real detection. |
| cross-container `udp_recv_benchmark.py`: receiver `--role receiver --max-runs 3 --force-rcvbuf` (172.31.77.110); sender `docker exec gx-arv1 ... --role sender --target 172.31.77.110` | 1472 B at 1000 Mbit/s 254,768/254,768; 8972 B at 1000 Mbit/s 41,824/41,824; 8972 B at 2500 Mbit/s 104,512/104,512 (0 % loss, SO_RCVBUFFORCE 64 MiB). Results: `final_bench_xcontainer.log` |

## 6. Simulated-register harnesses (scratch only, not shipped)

| Harness | What it injects | Result |
|---|---|---|
| `<scratch>/impl/harness_ptp_sim.py <gige> synced` (2 viva fakes) | capability gets the 1588 / action / scheduled bits; 0x096C reads Listening, then Master (.1) and Slave (.2); clocks 150 ns apart, 0 ppm | IEEE 1588 PASS; enable PASS; **roles settled after 1.5 s, master .1, slave .2**; latch PASS (1000.000 MHz); offset +0.1 µs (±512 µs), drift 0 ppm, PASS; keys programmed; wrong key ignored; immediate, scheduled (+200 ms) and past-scheduled actions ACKed (the late one INFO "executes late actions immediately"); verdict "PTP clock sync: VERIFIED", "scheduled ACTION_CMD accepted by all: YES" |
| `harness_ptp_sim.py <gige> unsynced` | both cameras Master; clocks 2 s apart, 25 ppm drift | roles **FAIL** with the IGMP-snooping / power-cycle hint; offset **FAIL** (+611,854 µs, +25.000 ppm); clock vs host +25.000 ppm reported; verdict NOT VERIFIED; exit 1 |
| `harness_viva_ptp_sim.py <gige> lock` | GenICam PtpEnable / PtpDataSetLatch / PtpStatus / PtpOffsetFromMaster nodes | `PtpEnable: false -> true`; PTP lock PASS (Master, 0 ns); `--restore-ptp` sets it back to false |
| `harness_viva_ptp_sim.py <gige> nolock` | status stays Listening | PTP lock FAIL after 6 s with hints; restore still runs |
| `harness_viva_revoke.py <gige>` | `FakeGigeCamera.revoke_control()` 1.5 s into a free-run (camera-side heartbeat expiry) | no crash; "camera control" **FAIL**; restore succeeds after `reclaim_control()`; CSV and JSON written |
| `harness_stdlib_revoke.py <gige>` | same, during `gvsp_capture_report` live capture | "camera control" **FAIL**; registers restored after re-taking control (SCDA back to 0); control released (`controller after: None`) |

## 7. Bugs found and fixed during verification

1. **Discovery deduplicated by MAC.** It hid cameras that share a MAC, such as emulators. It now deduplicates by MAC + IP + source address.
2. **SO_RCVBUFFORCE fallback.** When FORCE failed with EPERM, the code kept retrying FORCE at halving sizes and never fell back to SO_RCVBUF. The result was the OS default of 212,992 B instead of 425,984 B. Fixed and re-verified with and without NET_ADMIN.
3. **Fire-test packet check.** A missing fire-test packet was a FAIL that blamed the MTU. The emulator simply doesn't implement fire-test, so it is now a WARN that names both causes.
4. **Prototype "frames reassembled" check (verifier finding).** It passed with 0 complete frames. The analyser now requires at least 1 complete frame and completeness ≥ `--min-complete`, and counts never-seen frames (block-id gaps). Confirmed FAIL at 0/75 and PASS at 76/76.
5. **Resend reporting.** It warned when resent packets lacked the status 0x0100 / flag 0x01 marker; the viva fake does not mark them. The report now counts requested packet ids that later arrive ("4 requested, 4 recovered").
6. **Benchmark receiver role.** Stray END markers from the previous run produced bogus rows and wrong sent counts, and the size column showed the maximum size instead of the observed one. Fixed, and `--max-runs` added.
7. **`--control viva` crash.** It crashed with a traceback when viva could not find the camera. It is now a clean FAIL.
8. **viva scheduled mode with a latch value of 0.** It scheduled against time 0. It now SKIPs.
9. **Wrong NIC for action broadcasts on multi-NIC hosts.** With several NICs on 169.254/16 the broadcast address could come from the wrong NIC. It now uses the NIC that owns the routed local IP (`gev_common.broadcast_for`).
10. **viva free-run frame-rate check.** A FAIL when a camera ran slower than the requested fps without losing frames. It is now a WARN; a FAIL is reserved for real losses.
11. **Order-matched triggers.** "triggered frames" matched by order was a PASS. It is now a WARN, because it cannot prove the actions triggered the frames.
12. **Lost camera control (viva).** The stream exit raised `GenApiError` inside the ExitStack and the run ended with no report. It is now caught; control loss is reported as FAIL; restore retries after `reclaim_control()`.
13. **Stdlib clients and control loss.** They now report a lost-control heartbeat as FAIL. Restore re-takes control once on ACCESS_DENIED, and `GvcpClient.close()` returns restore problems for reporting.
14. **XML file collisions.** XML files of cameras with identical vendor/model/serial overwrote each other. The IP is now part of the filename.
15. **PEP 585 deprecation warnings.** beartype warned about `typing.Callable` and `typing.Iterator`; they now come from `collections.abc`.

**Test-environment caveat.** Two viva fakes bound to the same `127.0.0.1:3956` in different processes split GVCP traffic between them, which produced a spurious "control lost" (Windows allows the double bind). The test scripts now wait for each fake process to exit before starting the next.

## 8. Not verified (needs real GEV 2.x / 3.0 PTP cameras)

- PTP election and lock time, real offset values, vendor PtpStatus naming. The viva script reads PtpStatus by entry name, so vendor numbering (1-based in SFNC, 0-based on newer Allied Vision firmware) does not matter; the stdlib script uses the standard bootstrap values 1..9.
- PtpMode (Allied Vision) and PtpSlaveOnly (LUCID).
- Bootstrap timestamp latch on real cameras, and tick-frequency changes when PTP is enabled.
- Scheduled actions actually triggering exposures, the measured µs spread, scheduled-action queue limits, ACTION_LATE responses.
- The SFNC ActionSelector=1 to bootstrap index 0 mapping.
- Broadcast ACTION_CMD to real cameras.
- Fire-test packets (neither emulator implements them).
- PACKETRESEND on real cameras, including the 64-bit id form and the status 0x0100 / flag marker.
- GEV 3.0 devices: extended-id-only streams, `DeviceTLVersionMajor=3`, GevStreamingMode.
- Vendor-compressed pixel formats and payload types (only synthetic captures tested).
- The mini GenICam resolver on real vendor XMLs (Basler/FLIR/LUCID/AV StructReg/SwissKnife layouts). `--control viva` and pcap mode are the fallbacks.
- Real NIC performance at 1/2.5/10 GbE; Windows firewall prompts; vendor filter drivers.
- macOS (no Mac available).
- The CCP read semantics: whether a read shows other applications' control.
