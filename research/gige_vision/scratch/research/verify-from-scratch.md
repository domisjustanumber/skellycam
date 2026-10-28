# Fact-check: "from-scratch" topic (verifier notes, 2026-10-25)

Working dir for sources: `scratchpad/research/src/verify-from-scratch/` (raw files fetched at the exact commits the researcher cited; shallow clones of telegenic eb9de65, pyGigEVision 2de2531, viva-genicam 60c9c32, aravis 482547a (= meson version 0.9.3, commit date 2026-10-22), xnu f6217f8 sparse).
Re-run outputs: `src/verify-from-scratch/rerun/rerun.txt`, `src/verify-from-scratch/rerun/bench_314t_rerun.txt`.

## Verdict summary

| ID | Verdict | Note |
|---|---|---|
| C1 | supported | Wireshark `_v2_0`/`_v2_1` field names, masks and register #defines match (L118-136, L3474-3496, L3604-3607, L3692-3695, L3378-3398). Source is a dissector, not the spec. |
| C2 | supported | Press release (May 12 2026) re-fetched: RoCEv2, GVRSP, expanded control channel; no "PTP"/"1588" string. |
| C3 | supported | Wireshark L177-197; Aravis enum L267-281 (0x0004 = BYE_CMD; also lacks EVENT/EVENTDATA). |
| C4 | supported | Aravis arvgvcpprivate.h L82-137; Wireshark L71, L118-124, L3824-3845. |
| C5 | supported | Fire test + DNF + bisection (arvgvdevice.c L614-784), resend timeouts/ratio/ranges (arvgvstream.c L659-746), PF_PACKET TPACKET_V3 RX_RING (L1227-1367). |
| C6 | partially-supported | Extended resend first word: Aravis writes 0 (arvgvcp.c L429), Wireshark dissects a u16 stream-channel index at offset 0 in both modes (packet-gvcp.c L1600-1618). Status u16 lives in `ArvGvspPacket` (arvgvspprivate.h L252-255), not in the cited L132-145. |
| C7 | supported | Wireshark L2092-2115 + flag 0x80 at L2517-2518/L2820-2822; viva action.rs; telegenic gvcp.rs has no ACTION; pyGigEVision grep empty; Aravis HEAD also has no ACTION_CMD. |
| C8 | supported | packet-gvsp.c L43-54; Aravis leader structs; re-run decoded payload type 1, PFNC 0x01080001. |
| C9 | supported (citation fix) | `GevIEEE1588` Boolean is at Hikrobot.xml L49998 -> `GevIEEE1588PTPEnable_Bit` (Bit 12 of StructReg 0x0954, L51846-51900). Status MaskedIntReg at L50490 LSB31/MSB28. The Wireshark cite L3634-3637 is the *heartbeat-disable* field; clock status is L3692-3695. |
| C10 | supported | Re-ran: forced 32 MiB -> 74/74 complete (both probes), 0 rcvbuf errors. |
| C11 | supported | ldd shows `libpython3.12.so.1.0`; PyPI 1.6.0 files: cp310-cp314, win_amd64, manylinux x86_64/aarch64/armv7l, macosx_13_0_arm64 only. |
| C12 | supported | Independent top-level-node count reproduces 2165/283/406/513 and 1386/402/193/11. |
| C13 | supported | README L30-47, genicam.py docstring, gvsp.py L347-350 (`contextlib.suppress(OSError)` around 16 MiB SO_RCVBUF), recvfrom loop L548-606; PyPI 0.2.2 2026-07-08; MIT. |
| C14 | supported | telegenic Cargo 2.1.0 Apache-2.0, PyPI telegenicam 2.1.0 (2026-10-20); viva 0.10.0 MIT (2026-10-17); cameleon README L28 U3V only; Device trait lib.rs L82-95. |
| C15 | supported | 1e9/8/1538 = 81,274; /9038 = 13,830; x10. |
| C16 | supported (medium) | Matches bench files; "ceiling" Linux 620-870 kpps came from capped-buffer runs with 16-42% drops. |
| C17 | partially-supported | 7.2% drop was with the *default* 212,992 B buffer, not the 425,984 B capped one (that run lost 0.04%). Fake-camera loss reproduced (621-675 errors; 0/50 and 5/55 complete) but researcher's own probe B had 28/58 complete - variable. macOS: sbreserve silently clamps to sb_max; sb_max/high_sb_max are rescaled at boot from nmbclusters (uipc_mbuf.c L1481-1499). |
| C18 | supported (medium) | Re-ran 3.14.0rc3t: gil=0 0%/0% at 4/8 cams; gil=1 81.8%/92.2%. Note it is an rc build (uv 0.8.22 only offers rc3). |
| C19 | partially-supported | Page says "filter driver" / Socket Driver uses Socket API; does not say "NDIS". "From-scratch limited to plain socket path" is overstated: Aravis itself uses PF_PACKET RX_RING on Linux. |
| C20 | supported | WorkerMode PROCESS/THREAD (managed_worker.py L39-41), registry L137-148; `__main__.py` L42 defaults to PROCESS; camera worker at skellycam/core/camera/camera_worker.py L48. |

## Missed points
- genicam 1.6.0 has **no free-threaded (cp313t/cp314t) wheels** — https://pypi.org/pypi/genicam/json — so option (a) cannot be combined with the 3.14t no-GIL result; use one process per camera instead.
- viva-genicam's own backlog: **no PTP helpers (TC-35, not planned)**, **JPEG/multipart/GenDC payloads counted not assembled (TC-36)**, only `Local:` XML URLs (TC-33) — https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/docs/backlog.md#L41-L44
- telegenic has no PTP/1588 code (grep of src/ and py_src/ empty) and no ACTION_CMD (gvcp.rs L26-46).
- Release-date ordering in the summary is reversed: viva-genicam first on crates.io 2026-04-11, telegenic 2026-06-13.
- gev_scratch_probe.py "frames reassembled" check passes with 0 complete frames (L810: complete+incomplete>0); re-run with default buffer printed PASS with complete=0. Should be tightened before handing to users.
- GVRSP from Python is possible via rdma-core's pyverbs (Cython bindings to libibverbs), not pure Python: https://github.com/linux-rdma/rdma-core/tree/8009440e92f91e339ad3554b9ccf8800d05e5743/pyverbs
- Aravis (HEAD 482547a, 0.9.3-dev) has no PTP- or ACTION-specific code (grep for ptp/1588/ACTION_CMD in src/ empty), PTP only reachable through GenApi features.
