# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.3.4"]
# ///
"""Revise-step functional check with controls (no timing): copy the PyAV 19.0.2 package + av.libs to a temp
dir and try `import av` from the copy in 4 variants: unmodified (control), libx264 removed, libx265 removed,
both removed. The uv environment itself is not modified.
Usage: uv run --script pyav_strip_gpl_control.py <tmp dir> <out.json>"""
import json, pathlib, shutil, subprocess, sys
import av

tmp_root = pathlib.Path(sys.argv[1]); out = pathlib.Path(sys.argv[2])
src_pkg = pathlib.Path(av.__file__).parent
src_libs = src_pkg.parent / "av.libs"
res = {"pyav_version": av.__version__, "variants": {}}
for name, pats in [("control_unmodified", []), ("no_x264", ["libx264-*.dll"]), ("no_x265", ["libx265-*.dll"]),
                   ("no_x264_no_x265", ["libx264-*.dll", "libx265-*.dll"])]:
    d = tmp_root / f"av_{av.__version__}_{name}"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    shutil.copytree(src_pkg, d / "av"); shutil.copytree(src_libs, d / "av.libs")
    removed = []
    for p in pats:
        for f in (d / "av.libs").glob(p):
            removed.append(f.name); f.unlink()
    code = f"import sys; sys.path.insert(0, {str(d)!r})\nimport av; print('IMPORT_OK', av.__file__)\n"
    r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
    res["variants"][name] = {"removed": removed, "returncode": r.returncode, "import_ok": "IMPORT_OK" in r.stdout,
                             "imported_from_copy": str(d) in r.stdout, "stderr_last_line": (r.stderr.strip().splitlines() or [""])[-1][:300]}
out.write_text(json.dumps(res, indent=1), encoding="utf-8")
print(json.dumps(res, indent=1))
