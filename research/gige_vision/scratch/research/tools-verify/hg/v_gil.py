import sys, threading, time, statistics
from harvesters.core import Harvester
h = Harvester(); h.add_file(sys.argv[1]); h.update()
ia = h.create(0)
fps=float(sys.argv[2]); tmo=int(sys.argv[3])
try:
    ia.remote_device.node_map.AcquisitionFrameRate.value = fps
except Exception as e: print("fps set failed", e)
ia.timeout_period_on_update_event_data_call = tmo
print("fps", ia.remote_device.node_map.AcquisitionFrameRate.value, "update timeout ms", tmo)
stop=threading.Event(); n=[0]
def grab():
    while not stop.is_set():
        try:
            with ia.fetch(timeout=5): n[0]+=1
        except Exception as e: print("fetch err", e)
def lat():
    out=[]
    for _ in range(30):
        t=time.perf_counter(); time.sleep(0.001); out.append((time.perf_counter()-t-0.001)*1000)
        time.sleep(0.013)
    return out
print("idle sleep overshoot ms median/max", statistics.median(lat()), max(lat()))
ia.start(); th=threading.Thread(target=grab,daemon=True); th.start(); time.sleep(0.5)
L=lat(); print("live sleep overshoot ms median/p90/max", statistics.median(L), sorted(L)[26], max(L), "frames", n[0])
stop.set(); th.join(6); ia.stop(); ia.destroy(); h.reset()
