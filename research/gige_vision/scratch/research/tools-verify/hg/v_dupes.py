import sys, traceback
from harvesters.core import Harvester
h = Harvester(); h.add_file(sys.argv[1]); h.update()
for i,d in enumerate(h.device_info_list):
    print(i, d.id_, d.serial_number, d.parent.id_ if hasattr(d.parent,'id_') else d.parent)
ias=[]
for i in range(len(h.device_info_list)):
    try:
        ias.append(h.create(i)); print("create", i, "OK")
    except Exception as e:
        print("create", i, "FAILED", type(e).__name__, e)
for ia in ias: ia.destroy()
h.reset()
