"""Functional test: can the GPL libx264/libx265 DLLs simply be removed from a PyAV wheel install?

Copies the installed `av` package and its `av.libs` folder (delvewheel layout, Windows) into a temp dir,
deletes libx264-*.dll and libx265-*.dll from the copy, then tries `import av` from the copy in a
subprocess. The installed environment is not modified.
Usage: <python with av installed> pyav_strip_gpl_test.py --tmp <empty temp dir> --out <json>
"""
import argparse
import json
import pathlib
import shutil
import subprocess
import sys

import av

ap = argparse.ArgumentParser(); ap.add_argument("--tmp", required=True); ap.add_argument("--out", required=True)
a = ap.parse_args()
src_pkg = pathlib.Path(av.__file__).parent
src_libs = src_pkg.parent / "av.libs"
tmp = pathlib.Path(a.tmp) / f"av_{av.__version__}_nogpl"
if tmp.exists():
    shutil.rmtree(tmp)
tmp.mkdir(parents=True)
shutil.copytree(src_pkg, tmp / "av")
shutil.copytree(src_libs, tmp / "av.libs")
removed = []
for pat in ("libx264-*.dll", "libx265-*.dll"):
    for f in (tmp / "av.libs").glob(pat):
        removed.append(f.name); f.unlink()
code = ("import sys; sys.path.insert(0, %r)\n"
        "import av; print('IMPORT_OK', av.__file__)\n") % str(tmp)
r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
res = {"pyav_version": av.__version__, "removed": removed, "returncode": r.returncode,
       "stdout": r.stdout.strip()[-400:], "stderr_tail": r.stderr.strip()[-400:],
       "import_ok": "IMPORT_OK" in r.stdout}
pathlib.Path(a.out).write_text(json.dumps(res, indent=1), encoding="utf-8")
print(json.dumps(res, indent=1))
