"""Run viva-genicam (PyPI) and telegenicam against arv-fake-gv-camera-0.8 on loopback."""
import sys, time, traceback
IP = "127.0.0.1"

def t_viva():
    import viva_genicam as vg
    print("viva_genicam version:", getattr(vg, "__version__", "?"))
    print("public API:", [n for n in dir(vg) if not n.startswith("_")])
    try:
        cams = vg.discover(timeout_ms=800)
        print("discover():", cams)
    except Exception as e:
        print("discover error:", e)
    try:
        cams = vg.discover(timeout_ms=800, iface="lo") if "iface" in vg.discover.__doc__ else []
    except Exception as e:
        cams = []
    try:
        if not cams:
            cams = vg.discover(timeout_ms=800)
        cam = vg.connect_gige(cams[0])
        print("connected:", cam)
        for f in ["DeviceVendorName", "DeviceModelName", "Width", "Height", "PixelFormat"]:
            try: print(" ", f, "=", cam.get(f))
            except Exception as e: print(" ", f, "ERR", e)
        n = 0
        with cam.stream() as frames:
            for fr in frames:
                arr = fr.to_numpy()
                print("frame", n, arr.shape, arr.dtype, "ts", getattr(fr, "timestamp", None) if not callable(getattr(fr,"timestamp",None)) else fr.timestamp())
                n += 1
                if n >= 3: break
    except Exception:
        traceback.print_exc()
    try:
        from viva_genicam import gige
        print("gige module:", [n for n in dir(gige) if not n.startswith("_")])
    except Exception as e:
        print("no gige submodule:", e)

def t_tele():
    import telegenic
    print("telegenic API:", [n for n in dir(telegenic) if not n.startswith("_")])
    try:
        cam = telegenic.Camera(IP)
        cam.connect()
        print("connected; Width=", cam.get_int("Width") if hasattr(cam, "get_int") else "?")
        fr = cam.snap(timeout=5.0) if hasattr(cam, "snap") else None
        print("snap:", fr if fr is None else (fr.width, fr.height, fr.pixel_format, len(bytes(fr.data)) if hasattr(fr, "data") else "?"))
    except Exception:
        traceback.print_exc()

which = sys.argv[1]
{"viva": t_viva, "tele": t_tele}[which]()
