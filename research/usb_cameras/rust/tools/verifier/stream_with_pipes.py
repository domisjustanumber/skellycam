# /// script
# requires-python = ">=3.10"
# ///
"""Run a streaming command; after --delay s take win_usb_topology --pipes-only snapshots (C930e only);
wait for the command; write <snapdir>/pipes.json. Usage: stream_with_pipes.py --snap FILE --delay S -- cmd..."""
import json, subprocess, sys, time
from pathlib import Path
a=sys.argv[1:]; i=a.index("--"); opts=dict(zip(a[:i:2],a[1:i:2])); cmd=a[i+1:]
topo=r"C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\bandwidth\win_usb_topology.py"
p=subprocess.Popen(cmd)
snaps=[]
for k in range(2):
    time.sleep(float(opts["--delay"]) if k==0 else 2.0)
    r=subprocess.run([sys.executable,topo,"--pipes-only"],capture_output=True,text=True)
    try:
        js=json.loads(r.stdout)
    except Exception:
        js={"raw":r.stdout[-2000:],"stderr":r.stderr[-2000:]}
    snaps.append({"t_after_start_s":round(time.time(),3),"snapshot":js})
rc=p.wait()
Path(opts["--snap"]).parent.mkdir(parents=True,exist_ok=True)
Path(opts["--snap"]).write_text(json.dumps({"cmd":cmd,"rc":rc,"snapshots":snaps},indent=1))
print("rc",rc); sys.exit(rc)
