# /// script
# requires-python = ">=3.10"
# ///
"""Static checks of the Linux/macOS goal-1 drafts that can run on any OS (no camera needed).

  uv run --script research/usb_cameras/mjpeg/drafts/check_drafts.py

- python -m py_compile on every .py under mjpeg/ (drafts import mjpeg_common + pyav_capture/summarize from there)
- bash -n on every .sh under mjpeg/
- v4l2_mmap_mjpeg.py --selftest (ctypes struct sizes/offsets + ioctl numbers vs. LP64 Linux reference values)
- the runners reference only files that exist
- each runner writes into a fresh mjpeg_run_<UTC stamp> root and passes --root to every script that writes results
Writes results/<platform>/<host>/mjpeg_drafts_check/<UTC stamp>/summary.json (earlier checks are kept). This does NOT show the drafts work on a real
Linux/macOS camera: those claims stay documented-untested until run_linux_mjpeg.sh / run_macos_mjpeg.sh are run.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MJ = HERE.parent
sys.path.insert(0, str(MJ))
import mjpeg_common as mc  # noqa: E402

res = {"py_compile": {}, "bash_n": {}, "runner_refs": {}}
for f in sorted(MJ.rglob("*.py")):
    if "__pycache__" in f.parts:
        continue
    p = subprocess.run([sys.executable, "-m", "py_compile", str(f)], capture_output=True, text=True)
    res["py_compile"][str(f.relative_to(MJ)).replace("\\", "/")] = "ok" if p.returncode == 0 else p.stderr[-500:]
bash = shutil.which("bash")
for f in sorted(MJ.rglob("*.sh")):
    p = subprocess.run([bash, "-n", str(f)], capture_output=True, text=True) if bash else None
    res["bash_n"][str(f.relative_to(MJ)).replace("\\", "/")] = ("ok" if p.returncode == 0 else p.stderr[-500:]) if p else "bash not found"
uv = shutil.which("uv")
st = subprocess.run([uv, "run", "--script", str(HERE / "linux" / "v4l2_mmap_mjpeg.py"), "--selftest"], capture_output=True, text=True, timeout=300)
res["v4l2_selftest"] = {"returncode": st.returncode, "pass": "SELFTEST PASS" in st.stdout, "output": st.stdout[-4000:]}
for runner in (HERE / "linux" / "run_linux_mjpeg.sh", HERE / "macos" / "run_macos_mjpeg.sh"):
    txt = runner.read_text()
    refs = {}
    for var, rel in re.findall(r'^(\w+_PY)="\$(?:HERE|MJPEG_DIR)/([^"]+)"', txt, flags=re.M):
        path = (runner.parent / rel) if f'{var}="$HERE/' in txt else (MJ / rel)
        refs[var] = {"path": str(path.relative_to(MJ)).replace("\\", "/"), "exists": path.exists()}
    res["runner_refs"][runner.name] = refs
    res.setdefault("runner_layout", {})[runner.name] = {
        "fresh_run_root": bool(re.search(r'^RES="\$USB_ROOT/results/(linux|macos)/\$HOST/mjpeg_run_\$\(date -u', txt, flags=re.M)),
        "uv_run_calls": len(re.findall(r'uv run --script "\$(V4L2_PY|PYAV_PY|SUMMARIZE_PY|PROBE_PY|AGGREGATE_PY)"', txt)),
        # every result-writing script call (V4L2/probe/summarize/aggregate; pyav_capture writes only to scratch) carries --root
        "result_writer_calls": len(re.findall(r'uv run --script "\$(V4L2_PY|SUMMARIZE_PY|PROBE_PY|AGGREGATE_PY)"[^\n]*', txt)),
        "result_writer_calls_with_root": len([m for m in re.findall(r'uv run --script "\$(?:V4L2_PY|SUMMARIZE_PY|PROBE_PY|AGGREGATE_PY)"[^\n]*', txt)
                                              if '--root "$RES"' in m or "--list-tsv" in m]),
        "multiline_capture_cmds_with_root": len(re.findall(r'--root "\$RES"', txt))}
    lay = res["runner_layout"][runner.name]
    lay["ok"] = lay["fresh_run_root"] and lay["result_writer_calls"] == lay["result_writer_calls_with_root"]
ok = all(v == "ok" for v in res["py_compile"].values()) and all(v == "ok" for v in res["bash_n"].values()) \
    and res["v4l2_selftest"]["pass"] and all(r["exists"] for d in res["runner_refs"].values() for r in d.values()) \
    and all(v["ok"] for v in res["runner_layout"].values())
out = mc.results_dir("mjpeg_drafts_check", mc.utc_stamp())
(out / "summary.json").write_text(json.dumps({"test": "mjpeg_drafts_check", "platform": mc.plat(), "hostname": mc.HOST, "utc_started": mc.utc_now(),
                                              "command": "uv run --script research/usb_cameras/mjpeg/drafts/check_drafts.py",
                                              "environment": mc.environment(), "all_ok": ok, **res}, indent=1))
print("all_ok", ok)
print("wrote", out / "summary.json")
sys.exit(0 if ok else 1)
