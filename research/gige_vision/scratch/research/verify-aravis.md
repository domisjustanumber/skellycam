# Fact-check: topic "aravis" (verified 2026-10-25)

Method: cloned AravisProject/aravis and checked out 482547a3d56e3aa8d22d7ffed33c9f1588bfe17a (committed 2026-10-22). Also cloned robohouse-delft/aravis-rs at a911bf0 (2025-02-10). Both are under `research/src/verify-aravis/`.

I queried GitHub (gh), PyPI, anaconda.org, formulae.brew.sh, packages.msys2.org, Launchpad and crates.io directly. Docker tests are in `research/verify-aravis-work/`.

## Per-claim verdicts

| id | verdict | note |
|---|---|---|
| license | partially-supported | §3 text confirmed. The AGPL-3 compatibility step goes via GPLv3 and is not shown by the links. §6(b) literally requires a library "already present on the user's computer system", so a copy bundled inside a PyInstaller onedir is not clearly 6(b). |
| releases | partially-supported | Tags, versions and 49 commits are confirmed. The cited CI runs 39925980711/39925980920 are a **fork PR** (dkogan/aravis, NV12, head b81396e4), not main. Main HEAD 482547a3 push CI is green on **2026-10-22** (runs 39839548731/…908/…757/…793/…815). |
| no-ptp-in-lib | supported | `grep -rniE "ptp\|1588" src/` is empty. gstaravis.c L563-567 and L1203-1209 are confirmed. Commit ee31d82f1 (2026-10-03) is in no tag. Issue #258 was closed 2019-07-24 by the maintainer with the "set GenICam features" answer. |
| no-action-commands | supported | The enum has no ACTION_CMD, and the capability bit 1<<6 is at L102. #184 ("Scheduled Action Commands") has been open since 2018-08-09; the last comment is 2023-12-16. PR #468 is a draft: last commits 2021-07-21, converted to draft 2021-08-11, and the commit says "Without implementation for now". |
| timestamps | supported | Confirmed. Missed nuance: the tick frequency is read **once in `constructed`** (arvgvstream.c L1617/L1644). I proved this in Docker (below). |
| raw-frames | supported (nuance) | arvbuffer.h L64-92 is confirmed. CHUNK_DATA is also documented "(not supported)" yet is handled in gvstream L488-494. Aravis never decodes; it delivers the bytes. GVSP H264/GenDC content types return 0 expected packets (gvstream L316-320). |
| fake-cam-test | supported | The researcher's log matches. Note the default (25 Hz) run had device-ts std 10.55 ms, not 0.16 ms; 0.16 ms is from the 100 Hz run. The HEAD run at 100 Hz got only 90.7 fps (std 10 ms). |
| head-test-suite | supported | The log shows 10/10 OK and `ARAVIS_HAS_PACKET_SOCKET 1`. |
| packet-socket-linux-only | supported | meson.build L96-119 and gvstream L1386-1392 confirmed, plus ethernet.md (setcap cap_net_raw). |
| packaging | supported | PyPI aravis 404, conda-forge aravis 404, and PyGObject has 0 wheels across 67 releases (latest 3.58.1). The conda-forge pygobject build is 3.58.1 for win-64, osx-64/arm64 and linux. brew is 0.8.36 (arm64 + Intel `sonoma` bottles). MSYS2 is 0.8.33-4 (clang64/clangarm64/ucrt64). |
| ci-introspection | supported | Line numbers verified. |
| windows-perf-issue | supported (context) | #752 is open: "average speed was still 20MiB/s" against "90MiB/s" on Ubuntu20. A commenter points to small packet size, jumbo frames and a Windows MTU-update bug, so this is not proven to be an Aravis defect. |
| packet-resend | supported | arvgvstream.c L1847-1859 and arvgvdevice.c L1904-1905. |
| rust | supported | Cargo: system-deps `aravis-0.8`, features up to v0_8_31, BSD-2-Clause. crates.io 0.11.1 was published 2025-02-10. README: "Not all of the API has been tested." |
| device-id-collision | partially-supported | The evidence link (arvsystem.h) does not show it. The real code is arvgvinterface.c L444-480: a `g_hash_table_replace` keyed by id, user_id, serial, alias and MAC. The advice "open by serial" is unsafe for identical fake cameras, because both report serial GV01. Opening by IP bypasses the table (L700-740). |

## Independent test: tick-frequency caching
`verify-aravis-work/tick_cache_test.py`, run with:

```
MSYS_NO_PATHCONV=1 docker run --rm --network none -v <verify-aravis-work>:/work:ro skellycam-aravis-test bash /work/run.sh
```

The image is ubuntu:24.04 with libaravis 0.8.30 and python3-gi 3.48.2.

- [A] Tick register set to 1 MHz **before** `create_stream`: the device_ts/system_ts ratio is 2.0. The conversion used the new value, and the uint64 wrapped.
- [B] Tick register set to 1 MHz **after** `create_stream`: the ratio is 1.0. The old cached 1 GHz was used.

Conclusion: configure PTP or anything else that changes GevTimestampTickFrequency **before** creating the stream. Log: `verify-aravis-work/tick_cache_test.log`.

## Missed points
- Aravis 0.9.x (development series, API 0.10) has a **GenTL consumer**. It loads vendor .cti producers from `GENICAM_GENTL{32/64}_PATH` (docs/reference/aravis/gentl.md; src/meson.build L103-106 builds it unconditionally). There is also an optional experimental GenTL *producer* (meson_options.txt L13).
  - It was added in commit 1676fdc6c (2023-11-15) and first tagged in 0.9.0. The stable tag 0.8.36 has none of the gentl files.
  - aravis-rs binds only aravis-0.8, so it cannot use this.
- Aravis source marks GVSP status `NO_REF_TIME` 0x8013 and `ACTION_LATE` 0x8016 as "GEV 2.0" (arvgvspprivate.h L89-92). This is a hint, not authoritative, that the PTP and action features predate GEV 3.
- Ubuntu: 26.04 LTS "resolute" ships 0.8.34-1build2 and 26.10 "stonking" ships 0.8.36-2 (Launchpad). 24.04 is not the only LTS option.
- The socket-buffer default is FIXED (arvgvstream.c L1826-1833). The researcher's own log shows FIXED with size 0, so AUTO must be set explicitly.
- The Homebrew formula has gobject-introspection as a build dependency, and meson `introspection` defaults to `auto`. A typelib is therefore likely in the bottle, but I did not verify this.
