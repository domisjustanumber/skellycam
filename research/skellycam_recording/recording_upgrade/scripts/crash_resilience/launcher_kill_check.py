"""usage: python launcher_kill_check.py   (writes results/crash_resilience/launcher_kill_check.json)
Does Popen.kill() on the venv python.exe launcher also end the real interpreter it starts?"""
import subprocess, sys, time, os, json
VENV = r"C:\Users\Dom\GitHub\freemocap\skellycam\.venv\Scripts\python.exe"
hb = r"C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/crash_resilience/heartbeat.txt"
code = f"import os,time\nwhile True:\n open(r'{hb}','w').write(str(os.getpid())+' '+str(time.time()))\n time.sleep(0.05)"
p = subprocess.Popen([VENV, "-c", code])
time.sleep(2.0)
inner_pid = int(open(hb).read().split()[0])
res = {"launcher_pid": p.pid, "inner_pid": inner_pid, "inner_differs_from_launcher": inner_pid != p.pid}
p.kill(); p.wait()
t_kill = time.time()
time.sleep(1.0)
last = float(open(hb).read().split()[1])
res["heartbeat_age_s_1s_after_kill"] = round(time.time() - last, 2)
res["inner_still_running"] = str(inner_pid) in subprocess.run(["tasklist", "/FI", f"PID eq {inner_pid}", "/NH"], capture_output=True, text=True).stdout
print(json.dumps(res))
open(r"C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/results/crash_resilience/launcher_kill_check.json","w").write(json.dumps(res, indent=1))
