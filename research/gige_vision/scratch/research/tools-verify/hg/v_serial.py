import sys
from harvesters.core import Harvester
h = Harvester(); h.add_file(sys.argv[1]); h.update()
print([ (d.serial_number, d.parent.id_) for d in h.device_info_list])
try:
    ia = h.create({'serial_number': 'GV01'}); print("create by serial OK"); ia.destroy()
except Exception as e:
    print("create by serial FAILED:", type(e).__name__, e)
h.reset()
