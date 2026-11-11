# macOS suite

The macOS leg of the cross-platform UVC test suite: [docs/xplat_capture_plan.md](../../docs/xplat_capture_plan.md) sections 2.5 and 6, with the research in `results/agent_reports/plan_20261106/macos.md` and `topology_macos.md` (where their verifier notes disagree with the main text, the verifier notes win).

> **Status: built 2026-11-06 on Windows. It has never run on a Mac.**
> Every PyObjC, IOKit and `ioreg` call is written from headers, docs and the repo's unrun drafts. Expect a few fixes on the first run. See [What is untested](#what-is-untested) before trusting any result.

Paths are relative to `research/usb_cameras/` unless noted.

## Where it runs (plan 2.5)

| Leg | Machine | Suite |
| --- | --- | --- |
| M1 | Apple silicon, latest macOS 27.x | full |
| M2 | Apple silicon, latest macOS 26.7.x | full |
| M3 | Intel Mac, macOS 26.7.x | reduced |
| M4 | Apple silicon, latest macOS 15.8.x | reduced |

- The runner picks the reduced suite by itself on an Intel Mac or on macOS earlier than 26. `--full` and `--reduced` override this.
- The reduced suite runs ENV, TCC, TOPO, ID, FMT, FMT-NOGRAB, CTRL-LIST, MJPEG and CYC. TCC and TOPO are added to the plan's list because they open no stream and cost nothing.
- If the shell runs under Rosetta, the wrapper prints a warning. Use a native arm64 terminal.

## Before a run

1. **Camera permission (TCC) belongs to the app that launches the suite**: Terminal, iTerm2, VS Code and so on.
   - Grant it in System Settings > Privacy & Security > Camera, then quit and reopen that app.
   - Over SSH no permission prompt can appear, so grant it from a local terminal first.
   - A process without permission gets zero frames and **no error**. For that reason the runner records every camera-opening test except M-TCC as *untested* when permission is denied, restricted or not yet determined. Pass `--run-without-permission` to run them anyway.
   - `--request-camera` triggers the permission prompt.
2. Close Photo Booth, FaceTime, Zoom, OBS, browsers and Logi Tune. They hold cameras or write camera controls.
3. Turn Edge Light off (Control Center > Video Effects), then pass `--edge-light-off`. No device property exposes Edge Light, so the suite can only record that you checked.
4. Attach every camera as found, **the Razer Kiyo Pro included**. To exercise contention, put two cameras on one USB 2.0 hub (plan G-BW).

## How to run

```text
bash research/usb_cameras/suite/macos/run_suite.sh --dry-run     # print the plan; opens and writes nothing
bash research/usb_cameras/suite/macos/run_suite.sh --quick       # smoke run (roughly 10-20 min with 4 cameras)
bash research/usb_cameras/suite/macos/run_suite.sh --edge-light-off             # full unattended run (roughly 1-1.5 h)
bash research/usb_cameras/suite/macos/run_suite.sh --edge-light-off --ep0       # second pass: endpoint-0 controls
```

What `run_suite.sh` does:
- finds uv, or installs it into `~/.local/bin` with the official installer after saying so;
- records `sw_vers`, `uname -m`, `hw.model`, the CPU, whether Rosetta is translating, the launching app and whether this is an SSH session, and passes all of it to every result;
- runs `uv run --python 3.12 --script run_suite.py`.

The PEP 723 environment of `run_suite.py` pins PyObjC 13.0 (`pyobjc-core`, `-Cocoa`, `-AVFoundation`, `-CoreMedia`, `-Quartz` and `-libdispatch`, all `==13.0`), plus numpy, Pillow, simplejpeg and libusb1. The runner itself imports only the standard library and `suite/common`. It starts the camera helpers with its own interpreter, so they share that environment. `run_suite.py --help`, `--list-tests` and `--dry-run` work on any OS without PyObjC; `--dry-run --fake-ioreg DIR --fake-avf FILE` plans against fake data.

Flags (`run_suite.py --help` has them all):

| Group | Flags |
| --- | --- |
| Selection | `--only`, `--skip` (test names, with or without the `M-` prefix), `--full`, `--reduced`, `--quick`, `--list-tests`, `--dry-run` |
| Sizes | `--cycles` (20), `--proc-cycles` (10), `--frames` (10), `--mjpeg-seconds` (3), `--mjpeg-variants` (`nil,empty,dmb1,chromium`; `jpeg4cc` and `dmb1_sized` are extra), `--mjpeg-modes all\|ends`, `--ts-seconds` (20), `--ctrl-runs` (3), `--multi-repeats` (3), `--multi-seconds` (6), `--id-repeats` (20), `--id-proc-repeats` (5), `--kiyo-minutes` (5), `--kiyo-interval-s` (10), `--child-timeout-scale` |
| Mode scope | `--min-fps` (30), `--min-height` (720), `--all-modes` (from `common/modescope.py`, the same flags on every OS) |
| M-FMT-NOGRAB | `--hold-ms` (2000), `--nograb-baseline-s` (2), `--no-nograb-block-probe`, `--nograb-cond3 skip\|avf-dmb1` |
| Endpoint 0 | `--ep0`, `--ep0-backend iokit-intf\|iokit-dev\|libusb`, `--ep0-allow-seize` (required with `libusb`; the runner refuses `libusb` without it) |
| Other | `--flash` (recorded only), `--edge-light-off`, `--request-camera`, `--run-without-permission`, `--out-dir`, `--raw-dir`, `--no-camlock`, `--camlock-timeout-s` |

`--quick` lowers the size defaults to 5 / 3 / 5 / 1.5 s / `ends` / 8 s / 1 / 1 / 4 s / 2 / 1 min.

### Mode scope (plan section 6, Dom 2026-11-06)

- The streaming tests (M-MJPEG, M-CYC, M-MULTI, M-TS, M-CTRL-EFFECT) use only modes at **>= 30 fps and >= 720 lines** by default. The listing tests (M-FMT, M-CTRL-LIST, M-FMT-NOGRAB) still list and compare every mode.
- `--all-modes` restores the full set; `--min-fps` and `--min-height` move the thresholds. The rule (`in_scope`, 0.5 % rate tolerance, so 29.97 fps counts as 30) is `common/modescope.py`; `mac_modescope.py` adds the AVFoundation view (a mode = one format x rate, both ends of every range) and falls back to a local copy if `common/modescope.py` is missing.
- The default mode of M-CYC, M-MULTI, M-TS and M-CTRL-EFFECT is MJPEG 1280x720@30, else the nearest in-scope MJPEG mode. When AVFoundation lists no JPEG subtype, the formats at the descriptor's MJPEG sizes count as the MJPEG modes.
- A camera with no in-scope MJPEG mode is recorded and rated **untested (scope)**.
- Each streaming test records `measurements.mode_scope` (`common.modescope.record` layout: `scope`, `advertised`, `in_scope`, `excluded`, the mode lists), per camera and in total.

## Output

| What | Where |
| --- | --- |
| Results | `results/macos/<hostname>/suite_<UTC stamp>/`: one JSON per test (`m_env.json` ... `m_kiyo.json`, standard fields from `common/results.py`), `discovery.json`, `topology_snapshot.json`, `children.json` (every child command with rc, timeout and elapsed time), `summary.md`, and small per-cell JSONL files (`fmt_nograb/`, `mjpeg/`, `cyc/`, `ctrl_effect/`, `multi/`, `ts/`) |
| Raw data | `~/skellycam-raw/<same relative path>/`, outside the repo: the `ioreg` plists, the first two JPEG frames of each MJPEG cell, the `system_profiler` JSON |
| Caches | `~/skellycam-raw/suite_cache/<hostname>/`: `uvc_descriptors.json` (written by `--ep0` runs) and `mode_alt_cache.json` (the mode-to-alt cache of the bandwidth model) |

`$SKELLYCAM_RAW_ROOT` overrides `~/skellycam-raw`.

Verdicts follow plan section 3 through `common/rating.py`. Every verdict is tier 0: no tier-1 (admin configuration) knob is known on macOS.

## Tests (plan 6.2)

| Test | Opens a stream | What it does | Verdict |
| --- | --- | --- | --- |
| M-ENV | no | `sw_vers`, `uname`, `sysctl` (model, CPU, Rosetta), admin group, `pmset`, the processes that hold or change cameras, controllers and camera health from the IORegistry, `system_profiler` for reference, tier-1 (none), Edge Light attestation | context |
| M-TCC | 2 s, only when permission is missing | `authorizationStatus` for video and audio; without permission, one short capture records the zero-frame, no-error behaviour | permission detected before streaming |
| M-TOPO | no | IORegistry to topology snapshot, then `compute_domains`, `predict` for each camera's default mode (using the mode-to-alt cache), free ports with labels, `explain()` messages. The schema report lists port classes, which port-number keys appear (`port`, `usb-port-number`, `port-number`), `port-status` values outside the SDK 11.3 layout, and AppleHPM labels | G-BW untested (mapper only) |
| M-ID | no | AVFoundation discovery session x 20 in one process, the deprecated `devicesWithMediaType`, a new process each time x 5, and IORegistry x 20. Each entry maps to its `camera_identity` key through uniqueID, locationID, VID/PID, the IORegistry and the serial. Also checks the uniqueID and modelID formats and records enumeration time | G-ID (`rate_id`; persistence is attended A1) |
| M-FMT | no | `AVCaptureDevice.formats` against the UVC descriptors: missing or extra modes, MJPEG sizes offered only as `420v`/`yuvs`/`2vuy`, discrete or continuous rates. Descriptors come from an IORegistry property, the cache, or `--ep0` | listing only |
| M-FMT-NOGRAB | background stream only | Which method lists the formats **without grabbing the camera or starting a stream**. Methods: `AVCaptureDevice.formats` with no session (`mac_avf.py formats --hold-ms`); the IORegistry device subtree (records what format information it carries; none expected); with `--ep0` only, `mac_ep0.py descriptors` (the cached `GetConfigurationDescriptorPtr` copy). Conditions: idle; the camera streaming in another process through AVFoundation (scoped default mode); condition (iii) is skipped because macOS has no second capture API (`--nograb-cond3 avf-dmb1` runs a second AVFoundation process with the `dmb1` passthrough instead). Per method x condition: success, completeness vs the descriptors (MJPEG and raw separately), elapsed, the other stream's largest frame gap and runtime errors during the listing vs its baseline, the VS `bAlternateSetting` from `ioreg` while the method holds its device object (`--hold-ms`), and whether a third process's 1-frame capture still works during the hold (compared with the same probe without the method). Every camera, the Kiyo included; a camera the suite has gated as faulted is untested. Without Camera permission only the idle condition runs | `fmt_nograb` (best method) and `fmt_nograb:<method>`: yes / partial / no (`nograb.rate_method`); untested without a descriptor reference |
| M-CTRL-LIST | no | AVFoundation `is*ModeSupported` flags and current modes. With `--ep0`: GET_INFO/MIN/MAX/RES/DEF/CUR for every CT/PU control, compared with the descriptor's `bmControls` (the unadvertised selectors are probed too, except with `--quick`). XU controls are listed from the descriptor and never read or set | listing only |
| **M-MJPEG** (gating) | yes | Every in-scope JPEG-subtype format (`dmb1`/`jpeg`/`mjpa`/`mjpb`) x the variants nil, `{}`, `{PixelFormatType: 'dmb1'}` and `chromium` (Chromium's exact dictionary: `'dmb1'` + width + height + `AVVideoScalingModeKey` ResizeAspectFill): which buffer type arrives (CMBlockBuffer or CVPixelBuffer), SOI/EOI, strict decode (simplejpeg), SOF0 size, fps, CPU, header SHA-1 per variant. A camera with no JPEG subtype is tried at its descriptor MJPEG sizes. The IORegistry alt (+1 s) fills the mode-to-alt cache; with `--ep0`, VS_COMMIT GET_CUR (+1.2 s) proves the wire format | G-MJPEG (`rate_mjpeg`) |
| M-CYC | yes | K in-process cycles (re-fetch device, input, session, start, first frame, N frames, stop), K' one-process-per-cycle cycles, a 500 ms gap variant and a mode-switching variant (the last two only in the full suite; the switch alternates the default with another in-scope mode: 1920x1080@30 <-> 1280x720@30, else 720p60), then a health probe. A hung cycle ends its child (AVFoundation cannot abandon a hung call in-process); the remaining cycles continue in a fresh child, up to 3 times. Every failure is classified | Reliability (`rate_reliability`) |
| M-CTRL-EFFECT | yes | AVFoundation lock-mode schedule (readback). With `--ep0`: exposure x3 (luma), gain x3 (luma), WB x3 (R/B), focus x3 (sharpness), a set before start read back after the first frame and again with no session open (persistence across close), and every touched control restored in a `finally` block (initial GET_CUR, else the CUR from M-CTRL-LIST). G-CTRL criterion 1 (listed with the descriptor's range) comes from M-CTRL-LIST's `per_control`: an ep0 control counts as listed when the descriptor advertises it, GET_INFO says it is implemented and every GET answered, and its range matches when GET_MIN/MAX/RES/DEF form a valid range; an AVFoundation lock counts when the descriptor advertises the matching auto control. The AVFoundation exposure/WB/focus modes are also put back to their original values in a `finally` block (`ctrl-avf --set-modes`). Metrics come from the JPEG bytes, else from the CVPixelBuffer (420v/420f/2vuy/yuvs/BGRA) | G-CTRL (`rate_ctrl`) |
| M-MULTI | yes | All cameras together (one process each), then staggered by 1 s, repeated. Then each predicted shared-domain group: the over side at each camera's largest in-scope mode, and the fits side at the cheapest in-scope combination `predict` says fits. When none fits (every C922 + generic pair on Gerald-like layouts), the group records "fits-side not testable under mode scope"; the fits side is then covered by cameras in different domains in the all-at-once runs. Detects the three possible signals (runtime error, zero frames, reduced fps), runs `classify_failure`, builds the user message, retries the loser alone, and reads the granted alt (IORegistry; GET_INTERFACE with `--ep0`). A failure of a camera that is alone in its (known) domain and not classified as bandwidth (a Kiyo hang, in use, permission) is listed under `non_bandwidth_failures`, not scored as a false 'fits' | G-BW (`rate_bw`) |
| M-TS | yes | Which fields exist (PTS, duration, CMIO sequence number, attachments); the grid of PTS and of arrival times; arrival minus PTS; frame-index fits (causal and whole-run); drops from sequence-number gaps, PTS gaps and drop callbacks; `CFEqual(synchronizationClock, host clock)`; the port clock's rate against the host clock in ppm | G-TS (`rate_ts`; no ground truth) |
| M-FX | 3 s | Center Stage, Portrait, Studio Light, Background Replacement and Reactions flags per camera and per format, idle and while streaming, plus the class properties | context; a warning when any effect is active |
| M-KIYO | yes | Every 10 s for 5 min: IORegistry presence and entry ID, AVFoundation flags, GET_CUR of three controls (`--ep0`), and one open/close cycle. Records the first control failure, the first stream failure, and whether streaming survives a control failure | context |

Every test applies the plan 6.1 rules. Each camera call runs in a child process with its own deadline (it prints partial JSON and exits 5), inside a `procutil` timeout that kills the process group. A hang, a crash or a Kiyo failure is written as a result. Cameras are discovered at run time; VID:PID is used only for the `is_kiyo` label. Before and after each test the IORegistry entry ID of every camera is compared, and an unexplained re-arrival is flagged in that test's JSON.

Each run takes the camera lock once: `research/usb_cameras/.camlock`, the same `flock` that `tools/camlock.py` uses. This differs from Windows, where camlock wraps each command. Per-command camlock would serialise the concurrent captures of M-MULTI.

## Endpoint 0: why it is opt-in, and how it avoids claiming

UVC class requests (GET_* and SET_CUR to the VideoControl interface) are the only route on macOS to absolute exposure, gain, WB and focus. AVFoundation on macOS has only locked and auto modes (macos.md section 5). They are also the only way to read descriptors and the alt that macOS granted.

The evidence:
- They work without claiming an interface on macOS 12+: CameraController PR #26, uvc-util, and one uvc-avf measurement.
- An unopened request is still outside Apple's documented contract. libusb's own source says so: "Apple's USB Prober doesn't bother".
- libusb is the riskier route. Its darwin enumeration calls `USBDeviceOpenSeize` on **every** USB device, and `libusb_open` seizes again (`darwin_usb.c`; macos.md M27). A successful seize takes the device away from its owner. On Windows, enumeration has already disturbed the faulty Kiyo.

Decision: endpoint-0 work is opt-in (`--ep0`), and the default backend is the one that opens and seizes nothing.

| `--ep0-backend` | Route | Opens or seizes? |
| --- | --- | --- |
| `iokit-intf` (default) | IOUSBLib interface plug-in on the camera's VideoControl `IOUSBHostInterface`; `ControlRequest(TO)` on pipe 0, the CameraController / uvc-util pattern | no `USBInterfaceOpen`, no seize |
| `iokit-dev` | IOUSBLib device plug-in; `DeviceRequest(TO)` | no `USBDeviceOpen`, no seize |
| `libusb` | python-libusb1 `controlRead`/`controlWrite` on a handle | **seizes**: enumeration seizes every device and `libusb_open` seizes the camera. It never claims, detaches, sets a configuration, sets an alt or resets. The open result is recorded. Because seizing breaks plan 6.1, the runner refuses this backend unless `--ep0-allow-seize` is also given (then it warns and waits 10 s), and `mac_ep0.py` / `mac_avf.py` refuse it without `--allow-seize` / `--ep0-allow-seize` |

`helpers/iokit_usb.py` safeguards:
- A whitelist of vtable slots; `USBDeviceOpen(Seize)`, `USBInterfaceOpen(Seize)`, `SetConfiguration`, `SetAlternateInterface`, `ResetDevice` and `USBDeviceReEnumerate` are never callable.
- Before any request, getters check the vtable layout against the IORegistry: VID, PID, locationID, interface class and number.
- Descriptors always come from `GetConfigurationDescriptorPtr`, the OS's cached copy, so no request is sent. The verifier notes that whether this causes bus traffic is unverified.
- The plan's "record the USBInterfaceOpen return code" item is **deliberately not done**. A successful open would amount to a claim.

Recommended order: run the suite once without `--ep0`. Then run `--only ctrl-list --ep0` on its own and look at `m_ctrl_list.json` and the Kiyo before the full `--ep0` pass. The `--ep0` run also fills the descriptor cache, which later runs without `--ep0` use for the bandwidth model.

## Layout

```text
suite/macos/
  run_suite.sh        entry point (bootstraps uv, records the machine, TCC notes)
  run_suite.py        runner (PEP 723; stdlib + common only in-process)
  suitectx.py         SuiteCtx passed to every test + mode helpers
  macanalysis.py      pure analysis (MJPEG cells, control effects, timestamps, refusal signals)
  nograb.py           pure analysis for M-FMT-NOGRAB (completeness, disturbance, blocking, alt evidence, rating)
  mac_modescope.py    mode scope: common/modescope.py + the AVFoundation format x rate view
  tests/m_*.py        one module per test: run(ctx) -> result dict, plan(ctx) -> dry-run lines
  helpers/
    mac_avf.py        PyObjC AVFoundation worker: list, formats, ctrl-avf, fx, tcc, capture, cycle, multi
    mac_ep0.py        endpoint-0 UVC probe: probe, descriptors, ctrl-list, get, set, stream-state
    iokit_usb.py      ctypes IOUSBLib transports (no open, no seize)
    uvc_ctrl.py       UVC selectors, GET/SET logic, VS_COMMIT parse (pure)
    mac_ioreg.py      ioreg plists -> common topology snapshot (pure parsing + ioreg runner)
    childutil.py      child deadline, one-line JSON emit, mach clock, schedule parser
    usbdesc.py        copy of naming/usbdesc.py (descriptor parser)
  unittests/          pytest, any OS: fake ioreg trees, fake UVC camera, fake child runner
```

## Unit tests (any OS, no camera)

```text
uv run --isolated --python 3.12 --no-project --with pytest pytest research/usb_cameras/suite/macos/unittests
```

They pass on Windows (Python 3.11, 3.12 and 3.13) and in a `python:3.12-slim` Linux container. They cover:
- the IORegistry collector on fake Apple-silicon (two DRD controllers plus a Fresco PCIe xHCI, a USB 3 hub seen twice, AppleHPM labels), Intel (PCH plus the T2 virtual bus), macOS 26 port-key and devices-only fallback trees;
- domains, the 81.1% "over" and the "fits" predictions for C922 alt 9 + generic, and the exact suggestion sentence;
- UVC control logic against a fake camera: signed values, a stall, a Kiyo-style NotResponding abort;
- that the IOKit and libusb code cannot reach a forbidden call;
- every test module run end to end through a fake child runner, with and without `--ep0`;
- the mode scope (thresholds, records, default and mode-switch choices, a camera with no in-scope MJPEG mode, M-MULTI's "fits-side not testable" and `--all-modes`);
- M-FMT-NOGRAB: completeness, disturbance, blocking and alt evidence on synthetic data, the hold / ready / stop handshakes, and end to end with injected disturbance, blocking and a non-zero alt during the hold, without permission, and with a gated Kiyo;
- G-CTRL criterion 1 fed from M-CTRL-LIST (this run, its JSON file, or this test's own reads);
- the runner's real `main()` loop.

`--help` and `--dry-run` are run in a subprocess, which checks that PyObjC is never imported. All of this is plumbing. None of it shows that macOS behaves this way.

## What is untested

**Nothing in this folder has run on macOS.** In order of risk:

1. **PyObjC call patterns** (`helpers/mac_avf.py`): the sample-buffer delegate class and its protocol, `dispatch_queue_create`, CMTime round trips (`minFrameDuration` passed straight back to `setActiveVideoMinFrameDuration_`), `CMSyncConvertTime`, `CMSyncGetRelativeRate`, notifications and `NSUnderlyingError` chains, `objc.autorelease_pool`, and Python attributes set on NSObject instances. Block-buffer bytes, CVPixelBuffer planes and the CMIO sequence number are read through ctypes on the raw pointer (`__c_void_p__`, `__pointer__` or `pyobjc_id`). The ctypes route avoids PyObjC buffer conventions, but whether those pointer accessors exist on CF proxies in PyObjC 13 is unverified.
2. **IOKit through ctypes** (`helpers/iokit_usb.py`): the plug-in and interface UUIDs and the vtable slot numbers come from memory of `IOUSBLib.h`, not from a header on disk. The getter check catches a wrong layout before any request is sent, and a wrong UUID only makes QueryInterface fail. Other unknowns: whether an unopened `ControlRequest` answers on macOS 15, 26 and 27; whether `GetConfigurationDescriptorPtr` works without an open; whether `IOUSBHostInterface` nodes carry `locationID` (there is a fallback through the device's children).
3. **`ioreg` schema** (`helpers/mac_ioreg.py`):
   - whether `-r -c AppleUSBHostController` returns the whole tree on Apple silicon and Intel;
   - the port classes, and whether `IORegistryEntryLocation` appears in `-a` output;
   - the macOS 26/27 port keys (M-TOPO records which appear);
   - the AppleHPM `port-number` join to the controller;
   - the IOPCIDevice parent match;
   - companion pairing on real hubs;
   - whether the T2 bus class name is `AppleUSBVHCIBCE`.
4. **Whether `IOUSBHostInterface bAlternateSetting` tracks the live alt** (topology_macos MT4). M-MJPEG feeds the mode-to-alt cache from it, and M-FMT-NOGRAB's "starts a stream / reserves bandwidth" criterion reads it. A stale value would give the bandwidth model wrong costs; `--ep0` GET_INTERFACE is the cross-check.
5. **What a bandwidth refusal looks like in AVFoundation.** This is undocumented. M-MULTI accepts an error, zero frames or reduced fps. The AVError numbers in `common/topology_model.py` are from memory. Without descriptors (no `--ep0` run yet), camera costs are unknown, the prediction is marked incomplete, and refusals classify as "other", so G-BW rates "no".
6. **Effect thresholds** (`macanalysis.effect_verdict`: luma +15% for exposure, +10% for gain, R/B 5% for WB, sharpness x1.2 for focus) and the exposure values (≤ 33 ms so 30 fps is not forced down) are first guesses.
7. **CPU accounting** uses `getrusage` of the child (user + system). The time UVCAssistant spends is not counted.
8. **`sessionID`** is recorded raw for the Kiyo plug-in age. Its meaning is unverified.
9. **The macOS 26.2+ Edge Light** cannot be detected. Its state is only the operator's attestation.

Attended items are not automated: A1 (reboot, replug, port move for M-ID), A2 (move a camera to a suggested port), A4 (Kiyo on a USB 2.0 port), A5 (the ESP32 rig for G-TS ground truth) and MX7 (Reactions gestures and the Video menu).
