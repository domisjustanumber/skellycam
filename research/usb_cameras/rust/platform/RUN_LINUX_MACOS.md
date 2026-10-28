# Running the Rust probes on Linux and macOS

These were drafted on Windows and have **not been run on Linux or macOS yet**, so treat every expectation below as unverified until a result JSON exists.

## Programs

| program | what it tests | crate(s) |
| --- | --- | --- |
| `nokhwa_probe` | Does nokhwa 0.10.11 hand back the camera's MJPEG bytes untouched? What timestamp and device id does it expose? | nokhwa 0.10.11 (`default-features = false`, `input-native`) |
| `uvc_iso` | A from-scratch UVC streamer over raw isochronous USB. It produces native MJPEG plus per-frame PTS/SCR, and the app picks the alternate setting (so the app picks the bandwidth). | rawusb 0.1.7 (pure Rust) or libusb1-sys 0.7.0 (vendored libusb 1.0.27) |

## One-shot runners (run from the repo root)

```
bash research/usb_cameras/rust/platform/run_linux.sh  [--seconds 15] [--sudo]
bash research/usb_cameras/rust/platform/run_macos.sh  [--seconds 15] [--no-sudo]
```

Each runner builds both programs, runs every step, and writes to `research/usb_cameras/results/<linux|macos>/<hostname>/rust_*/<ts>/`. When it's done, send back the whole `results/<platform>/<hostname>/` folder.

## Manual commands

```
cd research/usb_cameras/rust
cargo build --release -p nokhwa_probe
cargo build --release -p uvc_iso --features libusb        # drop --features libusb for pure Rust only
cd ../../..                                                # repo root, so results land in research/usb_cameras/results
research/usb_cameras/rust/build/release/nokhwa_probe list
research/usb_cameras/rust/build/release/nokhwa_probe capture --cameras 0 --width 1280 --height 720 --fps 30 --seconds 15
research/usb_cameras/rust/build/release/uvc_iso list --backend libusb
research/usb_cameras/rust/build/release/uvc_iso stream --backend libusb --vid 046d --pid 085c --alt device --seconds 15
research/usb_cameras/rust/build/release/uvc_iso stream --backend libusb --vid 046d --pid 085c --alt payload:1024 --seconds 15
```

## Permissions and prerequisites

### Linux

- **Build:** install `rustup`, then `build-essential pkg-config clang libclang-dev linux-libc-dev libudev-dev`. nokhwa's V4L2 bindings (`v4l2-sys-mit`) run bindgen, which needs libclang.
- **nokhwa:** needs read/write on `/dev/videoN`, which normally means being in the `video` group.
- **uvc_iso:** needs write access to `/dev/bus/usb/BBB/DDD`. Get it either with `sudo -E` or with a udev rule; `run_linux.sh` prints one in its header.
  - While uvc_iso streams, it detaches `uvcvideo` from the camera's interfaces, so `/dev/videoN` disappears and comes back afterwards.
  - It needs **no module parameter and no `quirks=128`**: the app picks the alt setting itself.
- **Kernel source note (read, not tested):** in current mainline, `uvc_fixup_video_ctrl()` applies `UVC_QUIRK_FIX_BANDWIDTH` (0x80 = 128) only to formats *without* `UVC_FMT_FLAG_COMPRESSED`. So `quirks=128` should not change MJPEG bandwidth. The bandwidth tests should confirm or refute this on the user's kernel by comparing `dmesg` / `/sys/module/uvcvideo/parameters/trace` output for MJPEG and YUYV.

### macOS

- **Build:** run `xcode-select --install`, then install `rustup`.
- **nokhwa:** the terminal app needs Camera permission. The first run triggers the prompt; accept it and run again.
- **Source reading (not tested):** `capture_out_callback` copies the decoded `CVPixelBuffer` (`CMSampleBufferGetImageBuffer`) and labels it `GRAY`. Expect `frames_with_soi = 0`, meaning no native MJPEG.
- **uvc_iso:** on recent macOS the UVC device is owned by the system's user-space UVC driver, so `claim` may fail as a normal user and possibly even as root. The runner tries both. A claim error in `summary.json` (`error.stage = claim_vc/claim_vs`) is the result we're looking for, not a harness bug.

## Output schema

- `summary.json`: test, platform, hostname, command, environment, settings, results. For `uvc_iso stream` it also has `probe_commit`, `alt_selected` (the chosen alt plus every iso alt with its bytes/interval), `device_clock_fit` and `controls`.
- `frames_*.jsonl`: the frame-log schema from `research/usb_cameras/README.md`. uvc_iso fills `uvc_pts`, `uvc_scr_stc`, `uvc_scr_sof` and `device_clock_hz`. `os_timestamp_ns` is the PTS mapped to the host clock by the SCR/arrival fit.
- Analyse the frame logs with `uv run --script research/usb_cameras/rust/tools/analyze_frames_rust.py <run_dir>...`.
