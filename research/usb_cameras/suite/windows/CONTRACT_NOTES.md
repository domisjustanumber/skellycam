# Windows suite: contract notes (enumeration half)

Clarifications of contract 3 by the agent that wrote `suitectx.py`, `helpers/winpnp.py`, `helpers/timed_run.py`, `helpers/win_topology.py`, `helpers/win_descriptors.py` and the tests `w_env`, `w_policy`, `w_topo`, `w_id`, `w_fmt`, `w_ctrl_list`. Nothing here removes a contract field; everything is additive or a precise reading of an ambiguous point.

## `suitectx.SuiteCtx`

| Field / method | Exact meaning |
| --- | --- |
| `out_dir`, `raw_dir` | `Path`, resolved, created by `build_ctx`. |
| `args` | argparse `Namespace`. `build_ctx` only reads `out_dir`, `raw_dir`, `wincam` from it (via `getattr`, so they may be missing). Tests read `quick`, `only`, `skip`, `cycles`, `proc_cycles`, `frames`, `mjpeg_seconds` with `getattr(..., default)`. `suitectx.add_common_args(parser)` defines all of them plus `--repeats` (W-ID, default 20); `suitectx.default_args(**over)` gives a Namespace with defaults. |
| `cameras` | list of camera dicts (see below). |
| `wincam` | absolute `Path` to `native/build/wincam.exe`. |
| `helpers_dir` | the "python helpers dir" (`suite/windows/helpers`). Alias property: `python_helpers_dir`. |
| `log(msg)` | timestamped line to stderr and `<out_dir>/suite_log.txt`. |
| `camcmd(argv, timeout_s)` | see below. |
| `write(name, obj)` | `<out_dir>/<name>.json` (adds `.json` if missing) via `common.results.write_json`; returns the `Path`. |
| extras | `run(argv, timeout_s)` (procutil.run without camlock, for enumeration-only commands), `helper_cmd(script, *args)` (`uv run --python 3.12 --script <helpers_dir/script> ...`), `test_dir(name)`, `raw_test_dir(name)`, `camera(key)`, `kiyo()`, `camera_summaries()`, `arrivals()`, `rediscover()`, `discovery` (the raw discovery record), `stamp`, `hostname`, `suite_dir`, `windows_dir`, `research_root`, `camlock`, `camlock_timeout_s` (600), `python` ("3.12"). |

Factory: `suitectx.build_ctx(args=None, out_dir=None, raw_dir=None, wincam=None, cameras=None)` resolves folders, runs discovery in a child process (no camera opened) and writes `<out_dir>/discovery.json`. Pass `cameras=` to skip discovery.

### `camcmd(argv, timeout_s)`

Runs

```text
uv run --script tools/camlock.py --timeout-s 600 -- <sys.executable> helpers/timed_run.py --timeout-s <timeout_s> -- argv...
```

- The timeout is applied to the camera command **after the lock is acquired** (`timed_run.py` uses `common.procutil.run`, whole-tree kill). The outer process gets `600 + timeout_s + 90` s.
- `argv[0]` may be relative (`uv`); `timed_run.py` resolves it with `shutil.which`. camlock itself always gets an absolute exe (`sys.executable`).
- Returns the procutil fields **of the camera command**: `rc`, `stdout`, `stderr` (the camlock/timed_run lines are kept, only the final `@@TIMED_RUN@@` line is stripped), `elapsed_s`, `timed_out`, `killed`, `kill_method`, `spawn_error`, `pid`; plus `lock_wait_s`, `camlock_rc` (75 = lock wait timed out), `lock_timed_out`, `outer` {rc, elapsed_s, timed_out, killed, kill_method}, `inner` (the timed_run record), `argv`, `timeout_s`.
- When the child times out, `rc` is the killed child's code and `timed_out` is true; the timed_run process itself exits 124.
- `suitectx.parse_json_stdout(r)` returns `(obj, error)` for a command that prints one JSON object.

## Camera dict

Contract fields, exact meaning:

| Field | Meaning |
| --- | --- |
| `key` | `common.identity` key (`naming/camera_identity.py` scheme). Serial = the instance-ID suffix when Windows used the serial (suffix has no `&`); no descriptor request is sent during discovery. W-FMT cross-checks this against the serial string descriptor. |
| `instance_id` | the **USB device** instance (composite parent), e.g. `USB\VID_046D&PID_085C\C922SN01`. The video function (`...&MI_00\...`) is in `function_instance_id`. |
| `parent_instance_id` | the **hub** the USB device is plugged into (`USB\VID_05E3&PID_0610\...` or `USB\ROOT_HUB30\...`). |
| `mf_symlink` | from `wincam list` (MF), else the PnP `KSCATEGORY_VIDEO_CAMERA` interface. |
| `ds_name`, `ds_path` | from `wincam list` (DS): FriendlyName and `DevicePath` (a `KSCATEGORY_CAPTURE` interface path). |
| `location_path` | `DEVPKEY_Device_LocationPaths[0]` of the USB device. |
| `metadata_tier1` | bool: `MetadataBufferSizeInKB<n>` > 0 under `DeviceClasses\{KSCATEGORY_CAPTURE or KSCATEGORY_VIDEO_CAMERA}\##?#<function instance>#{guid}\#GLOBAL\Device Parameters` of the **current** function instance. Details in `metadata_registry`. Environment context only (read by W-ENV): since Dom's tier-0-only decision of 2026-11-09 no test reads UVC metadata or rates on this flag; the name stays for the result contract. |

Useful extras: `ds_index` (DirectShow enumeration order = OpenCV `CAP_DSHOW` index, also `opencv_dshow_index`), `mf_index` (= OpenCV `CAP_MSMF` index, `opencv_msmf_index`), `ds_ffmpeg_name` (`@device_pnp_` + `ds_path`, the FFmpeg dshow "Alternative name", what PyAV should open), `speed` (`HS`/`SS`/`SS+`/`FS`/`LS` from cached hub data, V2 flags), `bcd_device` (cached device descriptor; part of the ModeAltCache key), `last_arrival`, `problem_code`, `dn_warn` (e.g. `DN_NEED_RESTART`, `DN_HAS_PROBLEM`), `port_path`, `hub_port`, `serial_source`.

Cameras are sorted by `mf_index`, then `ds_index`, then key. Virtual cameras (NDI, OBS, NVIDIA Broadcast, SpoutCam) are not in `cameras`; they are listed in `discovery["virtual_devices"]`.

## Re-arrivals

`suitectx.arrival_snapshot(cameras)` and `suitectx.diff_arrivals(before, after)` (CfgMgr only) give per-key `present`, `last_arrival`, `problem_code`, `dn_warn`. The enumeration tests record a before/after pair in their measurements (`arrivals`).

## Topology snapshot

`helpers/win_topology.py` (module + CLI) produces the `common.topology_model` snapshot. `win_topology.collect(descriptor_file=None)` is cached-state only (no request to any device). Camera `alt_table`s need the configuration descriptor: `helpers/win_descriptors.py` reads it (EP0 GET_DESCRIPTOR) in a child process under camlock; pass its JSON as `--descriptors FILE` / `descriptor_file=`. Without it, `alt_table` is None and the model falls back to the mode-alt cache.

`win_topology.observed_alts(snapshot)` maps each camera key to the alt matched from its currently open isochronous pipe. W-MULTI can call `collect()` while streams run to read granted alts (no admin, no device request).

## Files the enumeration tests leave in `<out_dir>` (for other tests)

| File | Written by | Content |
| --- | --- | --- |
| `discovery.json` | `build_ctx` | the full discovery record (cameras, virtual devices, wincam list, errors) |
| `descriptors/descriptors.json` | first of W-TOPO / W-FMT / W-CTRL-LIST (`_enum_util.get_descriptors`) | `win_descriptors.py` output for every camera (`devices[]` with `configuration`, `alt_table`, `serial_number`, `camera_key`) plus per-camera run records. Read once per run, so the Kiyo gets one set of GET_DESCRIPTOR requests. Pass it to `win_topology.collect(descriptor_file=...)` for alt numbers. |
| `W-TOPO/snapshot.json` | W-TOPO | topology snapshot with alt tables |
| `mode_alt_cache.json` | W-TOPO | `common.topology_model.ModeAltCache` seeded with the 10-27 measured alts (source `seed_measured_20261027`; C922 0016, C930e 0013, generic 0100). Load it with `ModeAltCache.load(path)` and `put()` observed alts (source `observed`); the seed never overwrites an existing key. |
| `mjpeg_modes.json` | W-FMT | `{cameras: {key: [{width, height, fps, interval_100ns, in_mf, in_ds}]}}`: every descriptor MJPEG frame x interval and whether MF and DS offer it |
| `W-FMT/<slug>_formats_{mf,ds}.json`, `W-CTRL-LIST/<slug>_controls_{mf,ds}.json` | W-FMT, W-CTRL-LIST | raw wincam output per camera |

The enumeration test modules write their own `<TEST_ID>.json` (via `ctx.write`) and also return the dict; the runner writing it again is harmless. Each records an `arrivals` before/after pair (`measurements.arrivals`, with `unexplained_re_arrival`). Each can run alone: `uv run --python 3.12 --script tests/w_topo.py --out-dir D [--reuse-discovery] [--quick]`.

Verdict keys used by these modules: W-POLICY `policy_traps`; W-TOPO `mapper` (pseudo-rating) and `G-BW` (untested here); W-ID `G-ID`, `G-ID_per_api` ({api: rating}), `key_source_stability`; W-FMT `fmt_equivalence`; W-CTRL-LIST `ctrl_list_equivalence` and `G-CTRL` (untested here). W-ENV has no verdict (context only).

## Mode scope (Dom, 2026-11-06)

- `common/modescope.py` is the one shared helper (all OS suites): `in_scope(w, h, fps, min_fps=30, min_height=720)` (0.5 % rate tolerance, so 29.97 counts), `Scope` / `DEFAULT` / `ALL`, `split` / `filter_modes` / `sort_modes` / `nearest` / `partner`, `record(scope, advertised, kept)`, `no_scope_mode_reason`, `add_args(parser)` and `from_args(ns)`.
- Runner flags (via `suitectx.add_common_args`, so standalone tests get them too): `--min-fps` (30), `--min-height` (720), `--all-modes`. `run_suite.py` logs the scope and puts it in `summary.md`.
- capkit: `mode_scope(ctx)`, `scoped(ctx, modes)` → (in-scope modes, record), `scoped_default(ctx, modes)` → (1280x720@30 or the nearest in-scope MJPEG mode, record; None + `untested_reason` when none is in scope), `switch_mode(modes, default)` (largest other in-scope size at ~30 fps, else the default size at another rate), `scope_untested(ctx, record)` (rating-shaped `untested`, `summary_label` "untested (scope)").
- Streaming tests record `mode_scope` per camera (`scope`, `advertised`, `in_scope`, `excluded`, the mode lists, `default_mode`): W-MJPEG (sweeps the in-scope modes; criterion "every in-scope MJPEG mode was captured", `summary_label` "yes (in-scope modes)" when modes were excluded), W-CYC (default + `switch_mode` partner for the mode-switch variants, e.g. 1280x720@30 vs 1920x1080@30, or 720p60; no partner → no mode-switch variants), W-MULTI (pairs from in-scope modes: default, switch partner, fastest, smallest; `pairs[].predicted` per A mode and `fits_side`; `pairs_note` "fits-side not testable under mode scope" when no in-scope pair is predicted to fit; the predicted-over pairs and the all-at-once runs still run; ``--all-modes`` adds back the plan section 5 candidates, 640x480@30 and the largest size's lowest rate), W-TS and W-CTRL-EFFECT (default 1280x720@30 MJPEG, nearest in-scope if absent). A camera with no in-scope MJPEG mode is skipped and rated `untested (scope)`.
- Listing tests (W-FMT, W-CTRL-LIST, W-FMT-NOGRAB) are unchanged: every mode.

## W-FMT-NOGRAB (Dom, 2026-11-06)

- Module `tests/w_fmt_nograb.py`, runs right after W-FMT. Per camera and condition (`idle`, `streaming_native` = wincam capture (MF) in another process, `streaming_second_api` = pyav_ds capture (DirectShow) in another process) ONE `ctx.camcmd([python, helpers/nograb_session.py, spec.json], 240 s)`: the streamer, the listing method and the third-process open must overlap, so the whole session holds the camera lock once. Every child inside is a `common.procutil.Background` (whole-tree kill, own timeout). Specs go to `W-FMT-NOGRAB/<slug>_<condition>_spec.json`; raw session output, method stdout/stderr and streamer frames to `<raw_dir>/W-FMT-NOGRAB/<slug>/<condition>/`.
- Methods: `hub_ioctl` (win_descriptors.py), `mf` / `ds` (`wincam formats --hold-ms`, default 2500, runner flag `--nograb-hold-ms`), `ffmpeg` (`-list_options true -f dshow`); `opencv` and `winrt` are recorded as `no` ("cannot list without opening capture"), camera `all`.
- Verdict keys `fmt_nograb|<camera key>|<method>` from `common.rating.rate_fmt_nograb` (yes / partial / no; `summary_label` "no (incomplete)", "no (failed)", "no (needs a stream)", "no (cannot list without opening capture)" (OpenCV, WinRT), "partial (idle only)", "partial (disturbs)", "partial (blocks)", "partial (provisional)"). Analysis helpers are OS-neutral in `common/nograb.py` (`compare`, `disturbance`, `blocked`, `stream_started`).
- Reference = the run's cached descriptors (`descriptors/descriptors.json`, W-FMT's EP0 read). Completeness: every descriptor (fourcc, size, interval) of the capture streams, MJPEG and raw separately (`other`, e.g. H.264, reported but not required); interval tolerance 3 x 100 ns (ffmpeg: 0.15 % because it prints rates with few digits).
- Stream / bandwidth: idle only, from `win_topology.collect()` samples overlapping the method's run (before the third-process open starts). Disturbance: streaming conditions only, from the streamer's `frames.jsonl` arrival times (gap threshold max(3 x baseline p50, 1.5 x baseline max, baseline max + 25 ms), bad JPEG frames when the baseline frames are valid, the streamer exiting). Blocking: idle only, 1-frame MF capture 0.6 s into the hold vs a control capture without the method (no-hold methods are rerun with a concurrent capture); "delayed until release" (first frame after HOLD_END and > 800 ms later than the control) counts as blocked.
- Pipe-sampler positive control: each streaming condition samples the camera's pipes before the first method (`baseline_pipe_active`); `pipe_sampler_validated` per camera is True when that sample saw the streamer's open pipe. When the streamer ran but no sample saw its pipe (False), the idle `stream_started: false` results are reset to unmeasured (`stream_started_note`), so the rating cannot claim "no stream" from a blind sampler. Live 2026-11-06: validated on all four cameras (C922 alt 9, C930e alt 11).
- A camera gated by the dead-device gate is skipped and every method rated `ctx.fault_untested`; a fault found in a session's streamers / third-process opens marks the camera (`ctx.mark_fault`, source `w_fmt_nograb`) and the remaining conditions are untested.

## `wincam activity` (opens no camera)

- `capkit.wincam_activity(ctx)` runs it through `ctx.run` (no camera lock, so it sees other processes while a test holds the lock); `capkit.activity_entry(doc, cam)` matches a camera by wincam's `match_key` (MF symlink and DS DevicePath give the same key); `capkit.activity_for_camera(ctx, cam)` is the compact per-camera record (`in_use`, `streaming_by_other`, `other_processes`, `consent_in_use`).
- Used by W-KIYO's background poller every round (`activity_changes`, per-poll `activity_processes`, `first_failure_activity_processes` in the onset record), by W-MJPEG (`activity_at_first_stream`) and W-CYC (`activity_at_first_stream`, read before the camera's pre-probe), and by W-FMT-NOGRAB (`activity_before`, `activity_at_start` / `_at_end`).
