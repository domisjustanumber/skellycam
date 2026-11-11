# Linux UVC test suite

The Linux suite of [docs/xplat_capture_plan.md](../../docs/xplat_capture_plan.md), covering sections 2.6 and 6. It targets three legs:

| Leg | Distro | Kernel |
| --- | --- | --- |
| L1 | Ubuntu 24.04.5 (GA kernel) | 6.8 |
| L2 | Ubuntu 26.04 | 7.0 |
| L3 | Fedora 45 KDE | 7.2 |

All three run on Gerald from an external SSD; an AMD PC is added for TOPO and MULTI. Status: built and unit-tested on a fake sysfs tree and a simulated camera. It has not run on camera hardware yet.

## Run

From the desktop session, so that logind's `uaccess` ACL covers `/dev/video*`:

```text
bash research/usb_cameras/suite/linux/run_suite.sh                 # full unattended run (about 1 h with 4 cameras at the default mode scope)
bash research/usb_cameras/suite/linux/run_suite.sh --quick         # short run
bash research/usb_cameras/suite/linux/run_suite.sh --only MJPEG,CYC
bash research/usb_cameras/suite/linux/run_suite.sh --dry-run       # the plan: tests, cameras found in /sys, rough time; opens no /dev node
bash research/usb_cameras/suite/linux/run_suite.sh --help
```

`run_suite.sh` installs `uv` into `~/.local/bin` if it is missing, using the official installer as the current user, without sudo. It then prints the distro, kernel and session to stderr and runs `uv run --python 3.12 --script run_suite.py "$@"`. Two environment variables change this:

- `SKELLYCAM_PYTHON_ONLY=1` uses the system `python3` instead. Strict JPEG decode and image metrics then need pillow, numpy and simplejpeg to be installed already.
- `SKELLYCAM_NO_BOOTSTRAP=1` refuses to install uv.

Main flags:

| Flag | What it sets |
| --- | --- |
| `--quick` | short run |
| `--only`, `--skip` | test IDs, with or without the `L-` prefix |
| `--cycles`, `--proc-cycles`, `--frames` | L-CYC |
| `--mjpeg-seconds`, `--mjpeg-modes all\|sizes\|common` | L-MJPEG |
| `--wrappers pyav,opencv,gst` | wrapper APIs compared in L-MJPEG and L-CYC |
| `--ts-seconds` | L-TS |
| `--multi-reps` | L-MULTI |
| `--kiyo-minutes`, `--kiyo-interval-s` | L-KIYO |
| `--ctrl-runs` | L-CTRL-EFFECT |
| `--id-repeats` | L-ID |
| `--cameras` | **opt-in** filter; by default every camera is tested, the Kiyo included |
| `--out-dir`, `--raw-dir` | output folders |
| `--mode-alt-cache` | an existing ModeAltCache JSON to load |
| `--keep-raw` | keep every raw frame |
| `--no-camlock` | skip the camera lock |
| `--flash` | ground-truth hook. No Linux flash tool exists yet, so it is only recorded |
| `--min-fps`, `--min-height` | mode scope of the streaming tests (defaults 30 and 720, see below) |
| `--all-modes` | turns the mode scope off: the streaming tests use every mode and the earlier mode choices |
| `--hold-ms` | L-FMT-NOGRAB: how long each listing method keeps its handle open (or repeats) while the alt is sampled and a third process tries to capture (2000; 1500 with `--quick`) |

### Mode scope

Dom's rule of 2026-11-06 (plan section 6, "Mode scope"), to speed testing up:

- **Streaming tests use only modes at ≥ 30 fps and ≥ 720 lines.** These are L-MJPEG, L-CYC, L-MULTI, L-TS and L-CTRL-EFFECT, plus the L-KIYO stream probe and the L-FMT-NOGRAB condition streams.
- **Listing tests list and compare every mode.** These are L-FMT, L-FMT-NOGRAB's listings and L-CTRL-LIST.
- `linuxlib/scope.py` applies `common/modescope.py`, the shared rule: lines ≥ the minimum, and rate ≥ the minimum with a 0.5 % tolerance, so 29.97 fps counts as 30.
- Each streaming test records the scope and, per camera, how many advertised MJPEG modes it excluded. A camera with no in-scope MJPEG mode is rated `untested (scope)`.
- Mode choices under the scope:

  | Use | Mode |
  | --- | --- |
  | default (L-CYC, L-TS, L-CTRL-EFFECT, MULTI phase A, the NOGRAB streams) | MJPG 1280x720@30, else the nearest in-scope MJPEG mode |
  | L-CYC mode switch | the default and 1920x1080@30, else 1280x720@60, else the nearest other in-scope mode |
  | L-MULTI pairs | in-scope pairs only, chosen by prediction. When no in-scope pair is predicted to fit in a shared domain, the pair records "fits-side not testable under mode scope". The predicted-over pair, phase A and the cross-domain pair still run |
  | L-TS | the main run only. The 15 and 5 fps metadata-overflow runs, and the 64 KiB buffersize run that depends on them, are recorded as excluded |

- `--all-modes` brings back the earlier choices: 640x480 for L-CYC, L-CTRL-EFFECT and L-KIYO, and the low-fps L-TS runs.

## Output

| Where | What |
| --- | --- |
| `results/linux/<hostname>/suite_<UTC stamp>/` | `L-<TEST>.json` per test, with the standard fields plus `rearrivals`, `kernel_log` (when `journalctl -k` is readable) and `camlock_waits_s`; `summary.md`, `summary.json`, `run.json`, `runner.log`, `mode_alt_cache.json`; per-test folders with `frames.jsonl`, `meta.jsonl` and `cycles.jsonl` |
| `~/skellycam-raw/<same relative path>` | raw JPEG dumps (`$SKELLYCAM_RAW_ROOT` overrides). After analysis each capture is pruned to `samples.mjpeg`, its first 3 frames, unless `--keep-raw` is given. Frames never go into `results/` |

## Tests

| ID | Answers | What it does |
| --- | --- | --- |
| L-ENV | context | Kernel and expected uvcvideo features by version; `modinfo` and parameters; usbcore quirks; systemd, PipeWire, WirePlumber and libcamera packages; user services; session (seat or SSH, groups); kernel-log access; controllers. Per camera: driver, bcdDevice, speed, power and LPM settings, the NO_LPM quirk bit. Tier-1 state is **detected only** |
| L-TOPO | G-BW mapper | Builds the topology snapshot from sysfs (`linuxlib/topology.py`). Computes domains, free ports with labels, and each camera's domain and predicted conflict at its default mode. Builds the pre-open messages |
| L-ID | G-ID | Maps every enumeration path to the identity key, repeated `--id-repeats` times: sysfs, QUERYCAP `bus_info`, `/dev/v4l/by-id`, by-path (plain and usbv2/usbv3), udev properties, and PipeWire nodes via `pw-dump` |
| L-DESK | desktop | Who holds the nodes (`fuser -v` and a `/proc` scan), whether each camera is streaming now (VS alt ≠ 0), PipeWire and WirePlumber state, and permissions. The EBUSY probe (REQBUFS only) runs **only where another process holds the node**. Runs before the camera tests |
| L-FMT | G-MJPEG coverage | `ENUM_FMT`, `FRAMESIZES` and `FRAMEINTERVALS` versus the sysfs `descriptors`; metadata formats (UVCH, and UVCM on 6.17+) |
| L-FMT-NOGRAB | format discovery | Which method lists a camera's formats correctly **without grabbing it or starting a stream**. Four methods: the sysfs `descriptors` blob (cached, no bus traffic; also the reference); `ENUM_FMT/FRAMESIZES/FRAMEINTERVALS` on a read-only fd with no `STREAMON` (`camworker formats --hold-ms`); `v4l2-ctl --list-formats-ext`; PipeWire `EnumFormat` from `pw-dump`. Three conditions: idle; streaming in another process through raw V4L2; streaming through PyAV (or a second raw-V4L2 process). Measures completeness vs the descriptors (MJPEG and raw separately), time, disturbance of the other stream, the VS alt while the method holds the device, and whether a third process's 1-frame capture still works during the hold. Rated per method with `common.rating.rate_fmt_nograb` |
| L-CTRL-LIST | G-CTRL | Full `QUERY_EXT_CTRL` walk with menus and current values, compared with the descriptors' bmControls. Records per-control errno and time. A query that fails (Kiyo EPIPE/ETIMEDOUT) no longer ends the walk: the remaining standard ids are probed one by one. The worker re-arms its watchdog per query and exits with the partial list before the runner's timeout. Extension units are recorded but never set. `per_control` (listed, and the camera's range consistent) feeds G-CTRL criterion 1 in L-CTRL-EFFECT |
| L-MJPEG | G-MJPEG | Every MJPEG mode through raw V4L2 mmap (the reference); each frame size through PyAV v4l2, OpenCV `CAP_V4L2` (`CONVERT_RGB=0`) and GStreamer when installed. Checks the S_FMT readback, strict decode, SOF0 size, fps, ERROR flags, sequence gaps and the header SHA-1 across APIs. For raw V4L2, buffers flagged `V4L2_BUF_FLAG_ERROR` (delivered from 6.14, dropped before) are left out of the valid-JPEG fraction and the rated fps, so L1 and L2/L3 rate the same thing; their count is reported. Feeds the ModeAltCache |
| L-CYC | reliability | Open/close cycles in one process, in a new process each time, and alternating two modes, for raw V4L2, PyAV and OpenCV. Every failure keeps its stage and errno and is classified; recovery after a failure and a health check after each batch are recorded |
| L-CTRL-EFFECT | G-CTRL | Exposure, gain, WB temperature and focus. Each is set before STREAMON and changed twice while streaming; the effect is judged in the image (luma, R/B ratio, sharpness). Also the EACCES case, persistence across close/reopen after idling past the autosuspend delay (runtime PM; granular PM from 6.16), and 3 runs. At the end the originals are restored, using the control default where the original could not be read. If that restore fails, the auto modes are retried on their own. Criterion 1 (listed with the descriptor's range) comes from L-CTRL-LIST's `per_control`. UVC descriptors carry no ranges, so the range half means the camera answered a consistent GET_MIN/MAX/RES/DEF |
| L-TS | G-TS | Buffer-timestamp flags and grid; metadata node captured in parallel; STC→host fit and PTS→host per frame; frame-index fits; drops; metadata overflow at low fps; meta buffersize on 7.1+. `hwtimestamps` is read only |
| L-MULTI | G-BW | All cameras together, then staggered. Predicted over and fits pairs per domain, with the mode pair for each variant chosen by the prediction (ModeAltCache, else largest alt). Each refusal is classified and retried once while the other camera streams. The camera is then opened alone, with one more try if that start delivers no frame (REPORT finding 19). The message is built from a mid-stream snapshot. A cross-domain pair checks that separate domains don't compete |
| L-KIYO | Kiyo | Control poll every 10 s for N minutes. Records LPM state, plug-in age, the NO_LPM quirk bit, a 1 s stream and a focus set every third poll, and when it stops answering |

## Rules this suite follows

- **No driver change, no sudo.**
  - No unbind/rebind, no libusb, no `set_interface`.
  - No module-parameter, sysfs or registry writes: `grep` the code.
  - Tier-1 items (`hwtimestamps`, `quirks`, `nodrop`, `usbcore.quirks=1532:0e05:k`, video-group membership) are detected and reported only.
- **Every camera operation runs in a child process with a timeout.** The runner itself opens no `/dev` node.
  - The children are `linuxlib/camworker.py` (stdlib ctypes V4L2) and `helpers/*.py` (PEP 723, through `uv run --script`).
  - `common/procutil.py` kills the process group on a hang.
  - camworker's own watchdog writes partial JSON and exits 5.
  - A process stuck in an uninterruptible ioctl can exit only when the kernel returns; uvcvideo's control timeout is about 5 s.
- **Camera lock.**
  - It uses the same `research/usb_cameras/.camlock` flock as `tools/camlock.py`, taken in-process.
  - Waiting for the lock never counts against a child's timeout.
  - L-MULTI holds the lock once across its concurrent children.
- **All cameras, the Razer Kiyo Pro included.** A hang or EPIPE/ETIMEDOUT is a result.
  - L-MJPEG stops a camera's mode sweep only after 3 consecutive device errors **and** a failed health check, and records why.
- **Never S_FMT a camera someone else streams.**
  - Each test first checks the VS interface alt and the holders (`tutil.gate`).
  - S_FMT sends a PROBE before it returns EBUSY.
- **Discover at run time.** Nothing is hard-coded except VID:PID labels such as `is_kiyo`.
  - Identity keys come from `common/identity.py` (serial if usable and unique, else `pci-<controller>/<port chain>`).
  - Note that these keys drop the bus number, so a USB 2.0 and a USB 3 root port with the same number collide. L-ID reports any collision.

## Attended items (not automatic)

| ID | Item |
| --- | --- |
| A1 | Reboot, same-port replug and port move, then rerun `--only ID` |
| A2 | Move a camera to a port the message suggests, then rerun `--only MULTI` |
| A4 | Kiyo with NO_LPM on a kernel that lacks it (`usbcore.quirks=1532:0e05:k` on the kernel command line, then replug), or on a USB 2.0 port |
| A5 | Ground truth with the ESP32 rig |
| DESK | Start a browser or portal stream, then rerun `--only DESK` to see EBUSY |
| Tier 1 | `hwtimestamps=1` (root) for the TS comparison leg; `quirks=0x10080` + replug for LX-BW3 |

## Layout

| Path | What it is |
| --- | --- |
| `run_suite.sh` | entry point: uv bootstrap, then the runner |
| `run_suite.py` | runner (PEP 723) |
| `suitectx.py` | the `ctx` passed to `tests/l_*.py`: `run(ctx) -> dict` |
| `linuxlib/v4l2.py` | V4L2 ABI: ctypes structs, ioctls, `QUERY_EXT_CTRL`, UVCH parser, self-test |
| `linuxlib/camworker.py` | child for every raw-V4L2 operation: `info`, `enum`, `formats` (with `--hold-ms`), `controls`, `capture`, `cycle`, `desk_probe`, `selftest` |
| `linuxlib/sysfs.py` | camera discovery, descriptor summary, power state, holders, re-arrival detection (sysfs only) |
| `linuxlib/topology.py` | sysfs to the `common/topology_model.py` snapshot |
| `linuxlib/apis.py`, `analysis.py`, `tutil.py` | capture by API, frame and step analysis (and the per-control listing for G-CTRL criterion 1), test helpers |
| `linuxlib/scope.py` | the mode scope of the streaming tests, over `common/modescope.py` |
| `linuxlib/usbdesc.py` | copy of `naming/usbdesc.py` |
| `helpers/pyav_v4l2.py` | PyAV 19.0.2 v4l2 `input_format=mjpeg` capture and cycle |
| `helpers/opencv_v4l2.py` | OpenCV `CAP_V4L2` raw-buffer capture and cycle |
| `tests/l_*.py` | the 13 tests |
| `unit/` | pytest: fake Gerald sysfs (`fakesysfs.py`, with real descriptor bytes) and a simulated camera (`simcam.py`) |

## Unit tests (no camera)

```text
docker run --rm -v <repo>/research/usb_cameras/suite:/suite:ro python:3.12-slim \
  bash -c "pip install -q pytest pillow numpy simplejpeg && cd /suite/linux/unit && python -m pytest -q"
uv run --isolated --python 3.12 --no-project --with pytest pytest research/usb_cameras/suite/linux/unit   # Windows: the Linux-only tests skip
```

The fake-sysfs tests need Linux symlink semantics, so run them in Docker or in WSL with pytest installed. Never point the suite at cameras from WSL.
