# Cross-platform UVC capture test suites

The test suites from [docs/xplat_capture_plan.md](../docs/xplat_capture_plan.md) section 6. They measure, on Windows, Linux and macOS, how well each capture route meets these goals:

| ID | Goal |
| --- | --- |
| G-ID | a stable identity per camera |
| G-TS | accurate per-frame timestamps |
| G-MJPEG | native MJPEG at every mode |
| G-CTRL | camera controls |
| G-BW | the USB topology, bandwidth conflicts and port suggestions |

Results are rated with the thresholds in plan section 3 on tier 0 only: the cameras as found, with no admin configuration. Dom's decision of 2026-11-09: no registry changes and no UVC PTS/SCR timestamp testing (device timestamps are judged unreliable from published work). The Windows suite and the shared code follow it; the Linux `l_ts` still has its UVC-metadata (SCR/PTS) cells and is not yet updated.

Paths below are relative to `research/usb_cameras/` unless noted.

## Rules every suite follows

These are from plan section 6.1. Breaking any of them is a bug.

- **No driver change, ever.**
  - No WinUSB or libusbK.
  - No `libusb_detach_kernel_driver`, `claim_interface`, `set_configuration` or `set_interface`.
  - No unbind or rebind.
  - No device restart, disable or remove: no `pnputil /restart-device`, `/remove-device` or `Disable-PnpDevice`.
  - The suites never write, delete or revert a registry value or module parameter.
  - Tier 0 only (2026-11-09). No Windows test reads, compares or rates UVC PTS/SCR/SOF: W-TS keeps the MF sample time, MF QPC arrival, DS/PyAV arrival and pts, ffmpeg-CLI pts and the frame-index fit; fps references and drop counts come from those host-side times. The suite never sets, removes or reverts the `MetadataBufferSizeInKB0` value. W-ENV records whether it is present (read only) as environment context, since it could change MF's per-sample work; no test depends on it. (Set on Gerald on 2026-11-08; an elevated step outside the suite removed it on 2026-11-09 08:49, see `results/windows/Gerald/metadata_revert_20261109/`.) wincam and pymf may still write their metadata fields into `frames.jsonl`; nothing reads them.
- **All cameras as found, the Razer Kiyo Pro (1532:0E05) included.**
  - Every camera call has a timeout, and camera work runs in child processes that the runner kills on a hang (`common/procutil.py`).
  - A hang, or `0x8007001F` from the Kiyo, is recorded as a result. It never crashes the run.
  - Cameras are never filtered out by default.
- **Discover at run time.**
  - No instance IDs, ports or camera lists are hard-coded. VID:PID is used only for labels such as `is_kiyo`.
  - Bandwidth contention is a test case. On Gerald, the C922 and the generic camera share root port HS13 on purpose.
- **Windows: every command that opens a camera runs under the camera lock.**

  ```text
  uv run --script research/usb_cameras/tools/camlock.py --timeout-s 600 -- <absolute exe path | uv run --script ...>
  ```

  - Exe paths must be absolute.
  - The time spent waiting for the lock counts against an outer timeout. Put the timeout *inside*, on the child.
  - camlock serves waiters FIFO (a ticket queue in `%TEMP%`; dead tickets are cleaned up).
- **Results:** one JSON file per test, with the standard fields (below). They go to `results/<windows|linux|macos>/<hostname>/suite_<UTC stamp>/`; `--out-dir` overrides this.
- **Raw frames stay out of the repo.**
  - Windows: `%USERPROFILE%/Documents/skellycam-raw/<same relative path>`.
  - POSIX: `~/skellycam-raw/...`.
  - `$SKELLYCAM_RAW_ROOT` overrides both.
  - Only small sample frames (JPEG headers) and JSONL files go into `results/`.

## Layout

```text
suite/
  README.md                 this file
  .gitignore                build/, __pycache__, *.exe, *.obj, *.pdb, ...
  common/                   OS-neutral shared code (package "common"); stdlib only except imgmetrics
    results.py              standard result JSON, default results/raw paths
    procutil.py             run(argv, timeout_s) with whole-tree kill on timeout
    jpegcheck.py            check_jpeg(): SOI/EOI/SOF0/header SHA-1, lenient + strict decode
    identity.py             camera_key(): serial if usable and unique, else port path
    topology_model.py       bandwidth domains, prediction, failure classes, port suggestions, user message
    tsanalysis.py           timestamp grid, frame-index fit, drop detection (fit_device_clock kept for Linux l_ts)
    imgmetrics.py           luma / R:B ratio / sharpness of a JPEG (Pillow + numpy)
    cycstats.py             open/close cycle statistics (Wilson CI, percentiles, recovery)
    rating.py               plan section 3 ratings (+ rate_fmt_nograb)
    modescope.py            streaming mode scope (exactly 720 lines at >= 30 fps; --min-fps / --min-height / --max-height / --all-modes)
    nograb.py               FMT-NOGRAB analysis: completeness vs descriptors, disturbance, blocking, stream started
    tests/                  unit tests, including the Gerald layout fixture (gerald_fixture.py)
  windows/
    run_suite.py            Windows runner (PEP 723)
    suitectx.py             the ctx dataclass passed to every test module
    tests/w_<name>.py       one module per test, each exposing run(ctx) -> dict (the result JSON)
    helpers/pyav_ds.py      PyAV DirectShow 'vcodec=mjpeg' capture/cycle (frames.jsonl / cycles.jsonl schema)
    helpers/opencv_ds.py    OpenCV CAP_DSHOW cycle baseline (opens by index resolved from the DS device order)
    helpers/raw_ds.py       raw (YUY2/NV12) capture: PyAV pixel_format, ffmpeg CLI -pixel_format, OpenCV CONVERT_RGB=0
    helpers/opencv_ctrl.py  OpenCV CAP_DSHOW/CAP_MSMF control probe with a DirectShow side channel (W-OCV-CTRL)
    helpers/pyav_list.py    timed PyAV/ffmpeg dshow list_devices / list_options (W-PYAV-LIST)
    helpers/pyav_list_session.py  listing session with all-camera pipe samples (W-PYAV-LIST)
    helpers/win_topology.py Windows topology collector -> topology snapshot (schema below)
    pymf/                   pure-Python MF probe (comtypes + ctypes, no compiled extension); cli.py mirrors wincam
                            list/formats/controls/capture/cycle; W-PYMF compares it with wincam
    native/wincam.cpp       MF + DirectShow probe tool; native/build.bat -> native/build/wincam.exe
  linux/, macos/            the Linux and macOS suites (same runner and result contract; plan sections 2.5-2.6)
```

## How to run

### Unit tests for `common/` (any OS, no camera)

```text
uv run --isolated --python 3.13 --no-project --with pytest pytest research/usb_cameras/suite/common/tests
uv run --isolated --python 3.13 --no-project --with pytest --with pillow --with numpy --with simplejpeg \
    pytest research/usb_cameras/suite/common/tests        # also runs the imgmetrics and strict-decode tests
```

- `--isolated` matters on Gerald. Without it, uv resolves Python to the skellycam `.venv`, whose site-packages leak into the test environment.
- The tests also pass with plain `python3 -m pytest` on Linux; they were run in Docker `python:3.12-slim`.

### Offline tests for the Windows, Linux and macOS suites (no camera)

```text
cd research/usb_cameras
uv run --isolated --python 3.12 --no-project --with pytest --with numpy --with pillow --with simplejpeg --with comtypes \
    pytest suite/common/tests suite/windows/tests -c suite/common/tests/pytest.ini -q
uv run --isolated --python 3.12 --no-project --with pytest --with numpy --with pillow --with simplejpeg pytest suite/linux/unit -q
uv run --isolated --python 3.12 --no-project --with pytest --with numpy --with pillow --with simplejpeg pytest suite/macos/unittests -q
```

- Run the Linux and macOS folders in separate pytest calls: both have a `test_modescope_nograb.py`.
- Without `--with comtypes`, the COM layers of `test_pymf_offline.py` are skipped.
- On Windows the Linux `linux_only` tests are skipped.

### Windows suite (Gerald)

1. Build the native tool:

   ```text
   research\usb_cameras\suite\windows\native\build.bat
   ```

   It writes `native\build\wincam.exe` (VS 2022 MSVC, `/W4 /permissive- /std:c++17`). With no Windows SDK installed (Gerald since 2026-11-07), it downloads the Windows SDK 10.0.22621 NuGet packages once into `native\build\sdk\` (git-ignored, hash-checked) and builds against them; see `native/README.md`.
2. Run the unattended suite. The runner's flags are `--quick`, `--only`, `--skip`, `--cyc-profile quick|standard|reliability`, `--reliability-cycles` (400), `--cycles`, `--proc-cycles`, `--frames`, `--mjpeg-seconds`, `--out-dir`, `--plan` / `--dry-run` [`--plan-cameras discovery.json`], `--max-height`, `--auto-toggles`, `--raw-seconds`, `--list-repeats`, `--pymf-cycles` and `--pymf-seconds`; `run_suite.py --help` has the exact spellings. `--plan` prints the order, per-test estimates and the total, and opens no camera.

   ```text
   uv run --python 3.12 --script research/usb_cameras/suite/windows/run_suite.py [flags]
   ```

   - The runner discovers the cameras and the topology at start-up.
   - Each test module runs in turn. Camera work goes through `ctx.camcmd()`, which uses camlock plus a child timeout.
   - The runner writes one JSON per test plus `summary.md`.
   - Order (2026-11-09, W-CYC-KIYO moved after the control tests in review round 3): W-ENV, W-POLICY, W-TOPO, W-ID, W-FMT, W-FMT-NOGRAB, W-CTRL-LIST, W-MJPEG, W-RAW, W-TS, W-PYMF, W-CTRL-EFFECT, W-AUTO, W-OCV-CTRL, W-CYC-KIYO, W-MULTI, W-PYAV-LIST, W-CYC; W-KIYO runs as a background poller for the whole run. The Kiyo-sensitive captures (W-MJPEG, W-RAW, W-TS, W-PYMF: a Kiyo age of about 17-43 min with a fresh replug) and the control tests run first, within about 200 Kiyo stream starts: the leading wedge hypothesis in docs/windows_results_20261106.md section 8 is cumulative stream starts (about 270 preceded the 11-06 R2 onset), not plug-in age alone. Then the Kiyo's own W-CYC reliability cycles (W-CYC-KIYO, about 1 h 24 min and about 1,060 Kiyo stream starts) run as the last Kiyo-early work; they may end in a fault, which is a recorded result. The runner puts the cameras Kiyo first (then discovery order), so every per-camera test does its Kiyo share at its start. W-PYAV-LIST runs late so it meets a wedged Kiyo, and W-CYC, which then cycles only the other cameras, runs last; it keeps `W-CYC.partial.json` after every variant, so a stopped run keeps what it measured. `--plan` prints the Kiyo's projected plug-in age and cumulative stream starts per test, warns when a Kiyo control test (W-CTRL-EFFECT, W-AUTO, W-OCV-CTRL) would start after more than 250 projected Kiyo stream starts, and warns for tests whose Kiyo work would end past 200 min (with a fresh replug and the estimates: W-CYC-KIYO at 2 h 18 min-3 h 43 min and W-MULTI at 3 h 43 min-4 h 06 min; no order fits all of them, since about 4 h of camera work precedes W-PYAV-LIST, and the 11-06 tests ran at 75-80 % of their estimates). It exits 3 when a Kiyo-early test (W-MJPEG, W-RAW, W-TS, W-PYMF, W-CTRL-EFFECT, W-AUTO, W-OCV-CTRL) is projected past 200 min for a Kiyo plugged in at the run start: an order error. The tests added on 2026-11-08 (W-AUTO, W-OCV-CTRL, W-RAW, W-PYAV-LIST, W-PYMF) are left out with a log line while their module is missing. `--only` / `--skip` take comma lists (`W-` optional). An exception or a missing module becomes that test's result JSON; the run continues.
   - Full defaults: `--cyc-profile reliability` (400 `mf_inproc` and 400 `ds_ffmpeg_inproc` cycles per camera, 100 `mf_newproc`, the other W-CYC variants at `--cycles 50 --proc-cycles 15`), `--frames 30 --mjpeg-seconds 3`. `run_suite.py --plan` prints the estimate: about 7 h 00 min on Gerald with four cameras, 4 h 13 min of it W-CYC (1 h 24 min in W-CYC-KIYO, 2 h 49 min in W-CYC at the end; 2026-11-09). In the reliability profile, mf_inproc / ds_ffmpeg_inproc / mf_newproc rate "yes" only at a Wilson 95 % lower bound >= 0.99 (W-CYC-381); mf_newproc's 100 cycles cannot reach it and are labelled so. `--quick` uses `--cyc-profile quick` and 4 / 2 / 10 / 1.5, three MJPEG modes per camera, 2 W-MULTI reps, 8 s W-TS, 1 W-CTRL-EFFECT run and 2 min of W-KIYO. Extra knobs: `--multi-reps`, `--ts-seconds`, `--ctrl-runs`, `--kiyo-minutes`, and `--camera TEXT`, an opt-in debugging filter. By default every camera is tested.
   - An ETA is printed before each test, from each module's `estimate_s(ctx)`.
   - Mode scope (Dom, 2026-11-08; `common/modescope.py`): the streaming tests (MJPEG, RAW, CYC, MULTI, TS, CTRL-EFFECT, AUTO, PYMF, on every OS) use only modes with exactly 720 lines at >= 30 fps (`--min-fps 30`, `--min-height 720`, `--max-height 720`; `--max-height 0` restores the >= 720 rule). There is no exception for raw formats: a camera with no in-scope raw mode is `untested (no raw mode in scope)`. `--all-modes` disables the filter. Listing tests (FMT, CTRL-LIST, FMT-NOGRAB) still use every mode. Each streaming test records `mode_scope` per camera (advertised / in-scope / excluded); a camera with no in-scope MJPEG mode is rated `untested (scope)`.
   - W-FMT-NOGRAB (`--nograb-hold-ms`, 2500): which format-listing method (hub IOCTL descriptors, MF, DirectShow, `ffmpeg -list_options`) lists every descriptor mode without grabbing the camera, idle and while another process streams it through MF or DirectShow. Each condition is one `ctx.camcmd` around `helpers/nograb_session.py`, so the streamer, the listing and the third-process open overlap under one camera lock.

3. Capture-side pieces (`windows/capkit.py` plus helpers):

   | File | Role |
   | --- | --- |
   | `helpers/pyav_ds.py` | PyAV DirectShow `capture` / `cycle`, using the same `frames.jsonl` / `cycles.jsonl` / `summary.json` schema as wincam. `capture --engine ffmpeg` runs the ffmpeg CLI with `-vcodec mjpeg -c copy` instead |
   | `helpers/opencv_ds.py` | OpenCV `CAP_DSHOW` cycle baseline. It opens by the DirectShow index resolved just before the run, and every call runs on one worker thread |
   | `helpers/multi_launch.py` | Starts several camera commands concurrently under ONE camera lock, and takes `win_topology` snapshots mid-stream (W-MULTI, and the W-CTRL-EFFECT DirectShow side channel) |
   | `helpers/raw_ds.py` | Raw capture (W-RAW) through PyAV dshow `pixel_format`, the ffmpeg CLI `-pixel_format`, and OpenCV `CAP_DSHOW` / `CAP_MSMF` with `CONVERT_RGB=0`; writes `frames.jsonl`, `frames.raw` and `summary.json` |
   | `helpers/opencv_ctrl.py` | OpenCV `CAP_DSHOW` / `CAP_MSMF` control probe (W-OCV-CTRL): AUTO_EXPOSURE / AUTOFOCUS sets, with OpenCV's readback and the camera's real value read through a DirectShow side channel |
   | `helpers/pyav_list.py`, `helpers/pyav_list_session.py` | Timed PyAV / ffmpeg dshow `list_devices` / `list_options`, and the listing session with pipe samples of every camera (W-PYAV-LIST) |
   | `pymf/cli.py` | Pure-Python MF probe (W-PYMF), with the same subcommands and JSON fields as wincam's MF half |

   **PyAV cannot request MJPEG** (measured 2026-11-06):
   - FFmpeg's dshow demuxer takes the codec from `AVFormatContext.video_codec_id`. Only the ffmpeg CLI's input `-vcodec` sets that field. The `vcodec` option passed through PyAV is silently ignored.
   - dshow then takes the first caps entry matching the size and rate. So PyAV gets YUY2/NV12 whenever the camera offers a raw format at that size and rate: the Kiyo at every mode, and the Logitech cameras at small sizes.
   - In W-MJPEG, `ds` is DirectShow through PyAV, or through the ffmpeg CLI where PyAV fell back; `pyav_ds` is PyAV alone.
   - In W-MULTI, `ds` uses the ffmpeg CLI and `pyav_ds` is PyAV as-is. PyAV's raw fallback needs a larger alt, so it is refused at modes the mapper rightly predicts fit for MJPEG.

### Linux and macOS suites

These are built but not yet run on hardware (plan section 6.3). Each has the same single entry point under `suite/<os>/` and the same result contract.

## Shared contracts

### Result JSON (every test)

`common/results.py`:

```python
res = results.new_result(test, platform=None, command=sys.argv, cameras=cams)  # utc_started, environment, ...
results.finish_result(res, measurements={...}, verdicts={...}, errors=[...])  # utc_finished, elapsed_s
results.write_json(out_dir / f"{test}.json", res)                               # atomic, strict JSON (NaN -> null)
```

| Field | Content |
| --- | --- |
| `test` | test name |
| `platform` | `windows`, `linux` or `macos` |
| `hostname` | machine name |
| `utc_started`, `utc_finished`, `elapsed_s` | timing |
| `command`, `argv` | how the test was invoked |
| `environment` | from `env_info()`: OS build or kernel, Python, package versions |
| `cameras` | the cameras the test covered |
| `measurements` | the test's data |
| `verdicts` | `{goal: rating}` from `common/rating.py`. Each rating is `{"rating": "yes"\|"partial"\|"no"\|"untested", "criteria": [{"criterion", "met", "detail"}], "evidence": ...}` |
| `errors` | errors met during the test |

Other helpers:
- `utc_stamp()` returns a stamp like `20261106T152337Z`.
- `default_results_dir()` and `default_raw_dir(out_dir)` give the default locations.
- `append_jsonl()` and `read_jsonl()` handle JSONL files; `read_jsonl()` tolerates a partial last line.

### Process control

`common/procutil.py`:

```python
r = procutil.run(argv, timeout_s, cwd=None, env=None)
# -> {argv, rc, stdout, stderr, elapsed_s, timed_out, killed, pid, spawn_error, kill_method}
```

- It never raises on child failure. `rc` is None if the process could not be started.
- On Windows, the child starts suspended and is put in a Job Object with kill-on-close, then resumed.
  - On timeout, the job is terminated, so camlock, uv, python and the camera exe all die together. `taskkill /T /F` is the fallback.
  - When the job handle closes, any grandchild still running is killed.
- On POSIX, the child gets its own session, and on timeout the whole process group gets SIGKILL.

### Camera identity

`common/identity.py` uses the scheme of `naming/camera_identity.py`. The logic is **copied**, and `tests/test_identity.py` checks it against the original whenever that file is present.

```python
identity.camera_key(vid, pid, serial, port_path, all_serials)  # all_serials: (vid, pid, serial) of connected cams
# "046d:085c:sn=C922SN01"  or  "4c4a:4a55:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.2"
```

The port-path formats are:

| OS | Port path |
| --- | --- |
| Windows | `LocationPaths[0]` split at `USBROOT(n)` |
| Linux | `pci-<controller>/<port chain>` |
| macOS | `bus<xx>/<nibbles>` from `locationID` |

### JPEG checks

`common/jpegcheck.py` provides `check_jpeg(bytes)`. It returns these fields, plus `bytes_before_soi`, `trailing_after_eoi`, `marker_ok`, `strict_method` and `strict_error`:

| Field | Meaning |
| --- | --- |
| `soi`, `eoi` | start and end markers present |
| `sof0_w`, `sof0_h` | frame size from the SOF0 header |
| `header_sha1` | full SHA-1 of SOI through the end of the SOS segment; its first 12 hex digits match `mjpeg_common.jpeg_header` |
| `lenient_ok` | marker walk, plus a lenient decode when one is importable |
| `strict_ok` | libjpeg-turbo strict decode via simplejpeg or PyTurboJPEG; None if neither is installed |
| `extra_bytes_before_eoi` | the N in libjpeg's "N extraneous bytes before marker 0xd9" |

- The generic 4C4A camera's 1080p frames trip the `extra_bytes_before_eoi` warning (REPORT finding 6).
- libjpeg reads a few bytes ahead, so its count can be up to about 5 below the bytes actually present.

`parse_sof0(bytes)` and `summarize_checks(list, w, h)` are also provided.

### Topology snapshot

Each OS collector produces this snapshot; `common/topology_model.py` consumes it:

```text
{"os", "collected_utc",
 "controllers": [{"id","name","pci_id","vendor","kind","policy_hint"}],
 "ports": [{"id","controller_id","hub_device_id"|None,"port_number","path","is_root_port",
            "half":"usb2"|"usb3"|"unknown","companion_id"|None,"connectable":"user"|"internal"|"not_used"|"unknown",
            "connector":"A"|"C"|"internal"|"unknown","label_parts":{...},"occupant_device_id"|None,"speed_max"|None}],
 "devices": [{"id","vid","pid","serial"|None,"name","speed":"LS"|"FS"|"HS"|"SS"|"SS+"|"unknown","port_id",
              "parent_device_id"|None,"is_hub","hub_tt"|None,"controller_id","root_port_id","bcd_device"|None,
              "periodic_pipes":[{"ep","type":"iso"|"int","max_packet","mult","interval"}]}],
 "cameras": [{"key","device_id","name","is_kiyo","alt_table":[{"alt","max_packet","mult"}]|None,"current_alt"|None}]}
```

Collector notes:

- `periodic_pipes` lists the pipes that are open *now*:
  - Windows: the hub IOCTL open-pipe list.
  - Linux: the interface's current `bAlternateSetting` plus its `ep_XX` endpoints.
  - macOS: the IORegistry.
- `max_packet` is the base packet size, and `mult` the number of transactions per microframe. For SuperSpeed, `mult` is bursts × mult.
- For a high-speed device, `root_port_id` and `controller_id` are those of the **USB 2.0** parent chain. If they point at a USB 3 half, the model follows `companion_id`; this happens on Gerald's Thunderbolt USB-C ports.
- `label_parts` keys are all optional:
  - `acpi_name`
  - `panel`: set it only when it can be trusted, and drop the all-zero `_PLD` defaults
  - `position_text`, `color`
  - `type_c`, `usb3_capable`
  - `socket_evidence`
  - `friendly`, `location_path`
- A hub that is the internal hub of a dock can carry `"is_dock": true`. The message then says that all USB 2.0 ports on the dock share one connection.

### Topology model functions

`topology_model.py` follows `results/agent_reports/plan_20261106/bandwidth_domain_model.md` sections 4–6. Where the report and its verifier notes disagree, the verifier notes are followed.

| Function | What it does |
| --- | --- |
| `cost_us(max_packet, mult, speed='HS')` | USB 2.0 §5.11.3 high-speed isochronous cost, `m · (38·8·2.083 + 2.083·⌊3.167 + 1.1667·8·n⌋)` ns, as in `bandwidth/hs_budget_model.py`. The budget is 100 µs, 80% of a microframe |
| `domain_key(snapshot, device_id)` | see the key formats below |
| `compute_domains(snapshot)` | `[{key, kind, controller_id, root_port_id, members, cameras, load_us, budget_us, pct_budget, pct_microframe, verdict, policy, ...}]` |
| `predict(snapshot, requests, mode_alt_cache)` | per-domain predicted load and verdict, plus conflicts and warnings (details below) |
| `classify_failure(os, code, context)` | `{"class", "reason", "code", "code_hex", "name", "retry_advised"}`. The classes are `bandwidth_certain`, `bandwidth_probable`, `in_use`, `device_error`, `permission`, `timeout` and `other` (details below) |
| `suggest_ports(snapshot, conflict, moving_camera_key, ...)` | `[{"group_label", "ports": [{"port_id", "label", "rank", "shares_with", ...}]}]`, best group first (details below) |
| `stay_here_alternatives(snapshot, conflict, cache)` | the highest cached mode per camera that makes the domain fit |
| `build_message(conflict, failure, suggestions, alternatives)` | the plan section 5 template, exactly: "{A} and {B} share USB bandwidth: both connect through {shared_hop}. …" "Suggest moving one of those cameras to any of the following controller ports:" followed by one `  {group}: {label}, ...` line per group, then "Or, to keep both where they are, lower {B} to …". Percentages are of the 100 µs budget |
| `explain(snapshot, requests, cache, failure)` | runs prediction, suggestions, alternatives and the message for every conflict |
| `ModeAltCache` | JSON cache of the granted alt setting per (vid, pid, bcd_device, format, w, h, fps). Key text: `046d:085c:0016:MJPG:1280x720@30`. Falls back to another bcdDevice, flagged `other_firmware` |
| `LearnedPolicies` | per-controller-model learned facts: escalation to `controller` after 2 consistent pooling refusals (verifier V4.4), and a pass/fail bracket |
| `policy_for(controller)` | the per-controller policy table (below) |

**Domain keys:**

| Key | When |
| --- | --- |
| `hs\|<controller>\|<usb2 root port>` | high-speed device on a per-root-port controller |
| `hs\|<controller>\|*` | pooled controller: EHCI, an Intel rate-matching hub in the chain, or AMD |
| `ss\|<controller>\|<root port>` | SuperSpeed device |
| `fs\|<controller>\|<root port>` | full- or low-speed device directly on a root port |

**`predict()`:**
- Each request is `{"camera_key", "mode", "alt"|None, "max_packet"|None, "mult"|None}`.
- A camera's cost comes from, in order of preference:
  1. an explicit packet size;
  2. an explicit alt;
  3. the cache;
  4. the largest alt, as a worst case;
  5. unknown.
- Thresholds: `fits` ≤ 93.75 µs (75% of a microframe); `marginal` ≤ 100 µs; `over` above that. A learned bracket replaces these.
- A conflict is a domain predicted `over` that holds a requested camera.

**Accounting:**
- `calibrated` is the default. It counts isochronous pipes only, which is how the 26/26 Gerald calibration was derived.
- `full` also counts interrupt pipes and a TT charge.
- Never mix them (verifier V2).

**`classify_failure()`:**
- Bandwidth, certain: MF `0x800718CF`, Linux `ENOSPC`, `kIOReturnNoBandwidth`.
- Bandwidth, probable: DirectShow `E_ACCESSDENIED` or `OSError(5)`, Panther Point `ENOMEM`, libusb `-1`, or zero frames. Each counts only when another camera in the same domain is streaming and the predicted load is over.
- Not bandwidth: Linux `EIO` at STREAMON is "no fast enough alt". `0x8007001F`, `MF_E_REBOOT_REQUIRED` and `0xC00D3EA2` are device errors.

**`suggest_ports()`:**
- Candidates are empty, user-connectable USB 2.0-capable ports. Ports on internal hubs are allowed.
- It never suggests a port in the conflicting domain, so never the same hub or dock, and never the SuperSpeed twin of the conflicting connector.
- It skips connectors whose USB 3 half is occupied.
- Ranks:
  1. an empty domain on a controller known to be per-root-port;
  2. an empty domain on a different controller;
  3. an empty domain on the same uncertain controller;
  4. a domain that already has devices, listed as `shares_with`.
- Labels fall back from the `_PLD` position, to "port N (HSnn, connector kind, user-accessible)", to the ACPI name or location path.

**Policy table** (`policy_for()`):

| Controller | High-speed domain |
| --- | --- |
| Intel xHCI, including 8086:7A60 (measured) and the TB4 8086:1138 | per root port |
| Intel Panther Point 8086:1E31 | per root port, with the software-blocks budget |
| MediaTek | per root port, with a 6144 B payload budget |
| Apple DWC3 | per root port |
| EHCI | whole controller |
| AMD | whole controller, uncertain (verifier V1) |
| anything else | per root port, flagged uncertain |

A collector's `policy_hint` overrides the table.

### Timestamps, cycles and image metrics

**`common/tsanalysis.py`** (stdlib only):

| Function | What it does |
| --- | --- |
| `grid_analysis(times_ns, nominal_period_ns=None)` | finds a quantisation step (15.625 or 16 ms host grid, 1 ms, …) and histograms the intervals |
| `fit_frame_index(arrival_ns, causal=True\|False)` | fits period and offset, with frame slots taken by rounding so drops leave gaps. Returns the fitted times, residuals and stats. Causal uses frames 0..i for frame i |
| `fit_device_clock(pts_ticks, host_ns, clock_hz, causal)` | linear PTS→host fit with 32-bit unwrap; reports ppm against the nominal clock. Used by the Linux `l_ts` only; the Windows suite is tier 0 only and no longer fits device clocks |
| `detect_drops(pts_or_seq, period)` | finds drops in sequence numbers or periodic timestamps |
| `score_against_truth()` | scores against a ground truth (flash or LED rig) |

**`common/cycstats.py`:** `summarize_cycles(rows)` returns:
- the success rate with a Wilson 95% interval;
- the share of cycles with a first frame within 2 s;
- per-field timing percentiles;
- failure classes;
- hangs and unreleasable cycles;
- the recovery-after-failure rate;
- the longest failure run.

**`common/imgmetrics.py`** (Pillow and numpy):
- `luma_mean(jpeg, roi)`, `rb_ratio(jpeg, roi)`, and `sharpness(jpeg, roi)`, which is the Laplacian variance normalised by mean luma squared.
- `roi` is `(left, top, right, bottom)` as fractions of the image.

### Ratings

`common/rating.py` provides `rate_id`, `rate_ts`, `rate_mjpeg`, `rate_ctrl`, `rate_reliability`, `rate_bw` and `rate_fmt_nograb`. They implement the plan section 3 thresholds, and each returns the rating with its criteria and evidence. Helpers:
- `untested(reason)`
- `worst(ratings)`

A `rate_id` that has passed everything except the attended persistence steps (A1) comes back `partial`, with the note "provisional yes".

## Status (2026-11-06)

`common/` is complete. Its unit tests pass:

| Platform | Python versions |
| --- | --- |
| Windows | 3.10, 3.12, 3.13 |
| Linux (Docker `python:3.12-slim`) | 3.12, with and without Pillow, numpy and simplejpeg |

The Gerald fixture reproduces bandwidth_domain_model.md section 3:

| Pair on HS13 | Load (of a microframe) | Prediction |
| --- | --- | --- |
| C922 alt 9 + generic | 81.1% | over |
| C922 alt 4 + generic | 59.7% | fits |
| C922 alt 5 + generic | 62.2% | fits |

The fixture's message suggests HS01, 02, 04, 05, 06, 09, 12, 15 and 16 and the four ports of the HS10 internal hub. It never suggests a port on the HS13 dock, the Thunderbolt SuperSpeed twins, or HS07.
