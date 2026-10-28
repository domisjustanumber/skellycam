# /// script
# requires-python = ">=3.10"
# ///
"""Count shared vs platform-specific source lines for the Rust candidates.

Usage:
    uv run --script research/usb_cameras/rust/tools/count_platform_code.py [--out DIR]

Counts non-blank, non-comment lines ("code lines") per file and classifies each file:
  - our programs: research/usb_cameras/rust/{uvc_iso,nokhwa_probe}/src/**.rs — a file is
    "platform-specific" if it is only compiled under a cfg(windows|target_os=...) module gate
    (declared in the parent with #[cfg(windows)] etc.) or lives in a platform directory;
    inside shared files, lines inside `#[cfg(windows)]`/`#[cfg(target_os = ...)]` items are
    counted separately (brace matching, best effort).
  - third-party crates from ~/.cargo/registry/src/*/: rawusb-0.1.7/src/sys/{windows,linux,macos},
    nusb-0.2.9/src/platform/*, nokhwa backends (bindings-windows / -linux / -macos),
    libusb1-sys-0.7.0/libusb/libusb/os/* (C).
Writes results/<platform>/<host>/rust_platform_code_count/<ts>/summary.json.
"""
import json
import os
import platform as pf
import re
import socket
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUST = HERE.parent
RESULTS = RUST.parent / "results"


def code_lines(text: str, c_style=True) -> int:
    n = 0
    in_block = False
    for line in text.splitlines():
        s = line.strip()
        if in_block:
            if "*/" in s:
                in_block = False
            continue
        if not s or s.startswith("//"):
            continue
        if s.startswith("/*"):
            if "*/" not in s:
                in_block = True
            continue
        n += 1
    return n


CFG_RE = re.compile(r"#\[cfg\((?:all\()?\s*(windows|unix|target_os\s*=\s*\"(linux|macos|ios)\"|not\(windows\))")


def cfg_gated_lines(text: str) -> dict:
    """Lines inside items directly preceded by a platform #[cfg(...)] attribute (brace matched)."""
    lines = text.splitlines()
    out = {}
    i = 0
    while i < len(lines):
        m = CFG_RE.search(lines[i])
        if m and lines[i].strip().startswith("#[cfg"):
            key = m.group(1).replace(" ", "")
            # find the item start and match braces
            j = i + 1
            depth = 0
            started = False
            count = 0
            while j < len(lines):
                l = lines[j]
                s = l.strip()
                if s and not s.startswith("//"):
                    count += 1
                depth += l.count("{") - l.count("}")
                if "{" in l:
                    started = True
                if (started and depth <= 0) or (not started and s.endswith(";")):
                    break
                j += 1
            out[key] = out.get(key, 0) + count
            i = j + 1
            continue
        i += 1
    return out


def ours():
    res = []
    for crate in ["uvc_iso", "nokhwa_probe"]:
        src = RUST / crate / "src"
        if not src.is_dir():
            continue
        for f in sorted(src.rglob("*.rs")):
            t = f.read_text(encoding="utf-8", errors="replace")
            name = f.name
            whole_file_platform = None
            if name in ("winsof.rs", "wincontrols.rs") or "mf_native_types" in name:
                whole_file_platform = "windows"
            res.append({"file": str(f.relative_to(RUST)).replace("\\", "/"), "code_lines": code_lines(t),
                        "whole_file_platform": whole_file_platform, "cfg_gated_lines": cfg_gated_lines(t)})
    return res


def registry_root():
    base = Path.home() / ".cargo" / "registry" / "src"
    roots = list(base.glob("*")) if base.is_dir() else []
    return roots[0] if roots else None


def third_party():
    root = registry_root()
    if not root:
        return {"error": "no ~/.cargo/registry/src"}
    groups = {
        "rawusb-0.1.7": {"shared": ["src/*.rs", "src/uvc/*.rs"], "windows": ["src/sys/windows/*.rs"], "linux": ["src/sys/linux/*.rs"], "macos": ["src/sys/macos/*.rs"]},
        "nusb-0.2.9": {"shared": ["src/*.rs", "src/transfer/*.rs", "src/io/*.rs"], "windows": ["src/platform/windows_winusb/*.rs"], "linux": ["src/platform/linux_usbfs/*.rs"], "macos": ["src/platform/macos_iokit/*.rs"]},
        "nokhwa-0.10.11": {"shared": ["src/*.rs", "src/backends/*.rs", "src/backends/capture/mod.rs"], "windows": ["src/backends/capture/msmf_backend.rs"], "linux": [], "macos": ["src/backends/capture/avfoundation.rs"]},
        "nokhwa-bindings-windows-0.4.6": {"windows": ["src/*.rs"]},
        "nokhwa-bindings-linux-0.1.4": {"linux": ["src/*.rs"]},
        "nokhwa-bindings-macos-0.2.4": {"macos": ["src/*.rs"]},
        "nokhwa-core-0.1.9": {"shared": ["src/*.rs"]},
        "libusb1-sys-0.7.0/libusb/libusb": {"shared": ["*.c"], "windows": ["os/windows_*.c"], "linux": ["os/linux_*.c"], "macos": ["os/darwin_*.c"]},
    }
    out = {}
    for crate, g in groups.items():
        d = root / crate
        if not d.exists():
            out[crate] = {"error": "not in registry (run cargo fetch)"}
            continue
        row = {}
        for k, pats in g.items():
            n = 0
            files = 0
            for p in pats:
                for f in d.glob(p):
                    n += code_lines(f.read_text(encoding="utf-8", errors="replace"))
                    files += 1
            row[k] = {"code_lines": n, "files": files}
        out[crate] = row
    return out


def main():
    out_dir = None
    if "--out" in sys.argv:
        out_dir = Path(sys.argv[sys.argv.index("--out") + 1])
    host = socket.gethostname().split(".")[0]
    plat = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(pf.system(), pf.system().lower())
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out_dir = out_dir or RESULTS / plat / host / "rust_platform_code_count" / ts
    o = ours()
    shared = sum(r["code_lines"] for r in o if not r["whole_file_platform"])
    gated = {}
    for r in o:
        if r["whole_file_platform"]:
            gated[r["whole_file_platform"]] = gated.get(r["whole_file_platform"], 0) + r["code_lines"]
        for k, v in r["cfg_gated_lines"].items():
            gated[k] = gated.get(k, 0) + v
    res = {"test": "rust_platform_code_count", "platform": plat, "hostname": host,
           "utc_started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "command": " ".join(sys.argv), "environment": {"python": sys.version},
           "ours_files": o,
           "ours_totals": {"code_lines_in_shared_files_including_cfg_blocks": shared, "platform_specific_lines": gated},
           "third_party": third_party(),
           "method": "code line = non-blank, non-// and non-/* */ line; cfg-gated lines = lines of items directly under a #[cfg(windows|unix|target_os=..)] attribute (best-effort brace matching)"}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(res, indent=1))
    print(out_dir / "summary.json")
    print(json.dumps(res["ours_totals"]))
    for k, v in res["third_party"].items():
        print(k, v)


if __name__ == "__main__":
    main()
