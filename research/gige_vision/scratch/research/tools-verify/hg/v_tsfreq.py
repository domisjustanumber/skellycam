import sys, traceback, genicam, harvesters
from harvesters.core import Harvester
print("genicam", genicam.__file__)
h = Harvester(); h.add_file(sys.argv[1]); h.update()
print("n devices", len(h.device_info_list))
ia = h.create(0)
ia.start()
with ia.fetch(timeout=3) as b:
    print("Buffer has _node_map:", hasattr(b, "_node_map"))
    dev = b.module.parent.parent
    print("GevTimestampTickFrequency in nodemap:", hasattr(b._node_map, "GevTimestampTickFrequency"))
    try:
        print(b.timestamp_frequency)
    except Exception:
        traceback.print_exc()
    # payload info
    print("payload_type", b.payload_type, type(b.payload).__name__)
    c = b.payload.components[0]
    print("data base is raw_buffer?", c.data.base is not None, c.data.flags['OWNDATA'])
ia.stop(); ia.destroy(); h.reset()
