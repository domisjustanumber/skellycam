# /// script
# requires-python = ">=3.10"
# ///
"""Clean-build / cross-check every Rust candidate and record the outcome, wall time and binary size.

Usage (Windows, from repo root; MSVC env needed for crates that compile C):
    cmd /c "call "C:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\VC\\Auxiliary\\Build\\vcvars64.bat" && uv run --script research/usb_cameras/rust/compile_checks/run_compile_checks.py"
Linux/macOS:
    uv run --script research/usb_cameras/rust/compile_checks/run_compile_checks.py
Options: --only name1,name2   --targets host|all (all = also `cargo check` for the other OS targets)
Writes results/<platform>/<host>/rust_compile_checks/<utc>/summary.json (+ per-item logs).
Each build uses a fresh CARGO_TARGET_DIR under compile_checks/build/, so times are clean builds
(the crates.io download cache is warm).
"""
import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUST = HERE.parent
RESULTS = RUST.parent / "results"

# (name, manifest dir, package or None, expected: "ok" | "fail", kind: "build" for host)
ITEMS = [
    ("nokhwa_probe", RUST, "nokhwa_probe", "ok"),
    ("uvc_iso", RUST, "uvc_iso", "ok"),
    # same crate, libusb backend compiled in too (vendored C libusb: cross `check` needs a cross C compiler)
    ("uvc_iso+libusb", RUST, "uvc_iso", "ok"),
    ("cc_nusb_bulk_ok", HERE / "cc_nusb_bulk_ok", None, "ok"),
    ("cc_nusb_iso_fail", HERE / "cc_nusb_iso_fail", None, "fail"),
    ("cc_rusb_iso_ffi", HERE / "cc_rusb_iso_ffi", None, "ok"),
    ("cc_rawusb_uvc", HERE / "cc_rawusb_uvc", None, "ok"),
    ("cc_uvc_libuvc", HERE / "cc_uvc_libuvc", None, "?"),
    ("cc_libuvc_crate", HERE / "cc_libuvc_crate", None, "?"),
    ("cc_camera_rs", HERE / "cc_camera_rs", None, "?"),
]
CROSS = ["x86_64-unknown-linux-gnu", "aarch64-apple-darwin"]


def host_platform():
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")


def cargo():
    c = shutil.which("cargo")
    if c:
        return c
    p = Path.home() / ".cargo" / "bin" / ("cargo.exe" if os.name == "nt" else "cargo")
    return str(p)


def run(cmd, cwd, env, log):
    t = time.perf_counter()
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, errors="replace")
    dt = time.perf_counter() - t
    log.write_text(f"$ {' '.join(cmd)}\n(cwd={cwd})\n--- stdout\n{p.stdout}\n--- stderr\n{p.stderr}")
    errs = [l for l in p.stderr.splitlines() if l.startswith("error")]
    return p.returncode, dt, errs[:8], p.stderr.splitlines()[-6:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--targets", default="all", choices=["host", "all"])
    a = ap.parse_args()
    only = set(filter(None, a.only.split(",")))
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out = RESULTS / host_platform() / socket.gethostname().split(".")[0] / "rust_compile_checks" / stamp
    out.mkdir(parents=True, exist_ok=True)
    cg = cargo()
    ver = subprocess.run([cg, "--version"], capture_output=True, text=True).stdout.strip()
    rv = subprocess.run([str(Path(cg).with_name("rustc" + (".exe" if os.name == "nt" else ""))), "--version"], capture_output=True, text=True).stdout.strip()
    rows = []
    for name, mdir, pkg, expected in ITEMS:
        if only and name not in only:
            continue
        tdir = HERE / "build" / name.replace("+", "_")
        shutil.rmtree(tdir, ignore_errors=True)
        env = dict(os.environ, CARGO_TARGET_DIR=str(tdir))
        base = [cg]
        pk = ["-p", pkg] if pkg else []
        if "+" in name:
            pk += ["--features", name.split("+", 1)[1]]
        rc, dt, errs, tail = run(base + ["build", "--release"] + pk, mdir, env, out / f"{name}__host.log")
        exe = None
        size = None
        rel = tdir / "release"
        bn = (pkg or name) + (".exe" if os.name == "nt" else "")
        if (rel / bn).exists():
            exe = str((rel / bn).relative_to(RUST.parent.parent.parent))
            size = (rel / bn).stat().st_size
        row = {"name": name, "target": "host", "action": "build --release", "expected": expected, "exit_code": rc,
               "outcome": "ok" if rc == 0 else "fail", "clean_build_s": round(dt, 1), "binary": exe, "binary_bytes": size,
               "errors": errs, "stderr_tail": tail, "log": f"{name}__host.log"}
        rows.append(row)
        print(f"{name:18s} host  rc={rc} {dt:6.1f}s size={size} {errs[:1]}", flush=True)
        if a.targets == "all":
            for tgt in CROSS:
                if tgt.split("-")[2 if 'apple' in tgt else 2] and host_platform() in tgt:
                    continue
                rc, dt, errs, tail = run(base + ["check", "--release", "--target", tgt] + pk, mdir, env, out / f"{name}__{tgt}.log")
                rows.append({"name": name, "target": tgt, "action": "check --release", "expected": expected, "exit_code": rc,
                             "outcome": "ok" if rc == 0 else "fail", "check_s": round(dt, 1), "errors": errs, "stderr_tail": tail,
                             "log": f"{name}__{tgt}.log"})
                print(f"{name:18s} {tgt:26s} rc={rc} {dt:6.1f}s {errs[:1]}", flush=True)
        shutil.rmtree(tdir, ignore_errors=True)
    res = {"test": "rust_compile_checks", "platform": host_platform(), "hostname": socket.gethostname(),
           "utc_started": stamp, "command": " ".join(sys.argv),
           "environment": {"os": platform.platform(), "cargo": ver, "rustc": rv, "cpu_count": os.cpu_count()},
           "note": "cross-target rows are `cargo check` only (no linking); C-building crates may fail cross-check for lack of a cross C toolchain, see errors",
           "items": rows}
    (out / "summary.json").write_text(json.dumps(res, indent=1))
    print(out / "summary.json")


if __name__ == "__main__":
    main()
