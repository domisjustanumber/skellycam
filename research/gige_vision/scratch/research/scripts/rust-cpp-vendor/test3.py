import inspect, traceback, sys
which = sys.argv[1]
if which == "tele":
    import telegenic
    cam = telegenic.Camera("127.0.0.1"); cam.connect()
    fr = cam.snap(timeout=5.0)
    print("tele Frame attrs:", [a for a in dir(fr) if not a.startswith("_")])
    print("tele frame:", fr.width, fr.height, fr.pixel_format, len(fr.data()))
    for a in ("timestamp", "block_id"):
        if hasattr(fr, a):
            v = getattr(fr, a); print("  ", a, "=", v() if callable(v) else v)
    print("tele Camera methods:", [a for a in dir(cam) if not a.startswith("_")])
else:
    import viva_genicam as vg
    from viva_genicam.testing import FakeGigeCamera
    print("FakeGigeCamera doc:", (FakeGigeCamera.__doc__ or "")[:600])
    print("sig:", inspect.signature(FakeGigeCamera))
    print("attrs:", [a for a in dir(FakeGigeCamera) if not a.startswith("_")])
    with FakeGigeCamera() as fake:
        print("fake:", fake)
        cams = [fake.device_info()]
        print("discovered:", cams)
        cam = vg.connect_gige(cams[0])
        for f in ("ActionDeviceKey","ActionGroupKey","ActionGroupMask","GevIEEE1588","GevIEEE1588Status","GevIEEE1588OffsetFromMasterLatched_Val","PtpEnable","PtpStatus","TriggerSource"):
            try: print("  ", f, "=", cam.get(f))
            except Exception as e: print("  ", f, "ERR", type(e).__name__, e)
        for k in ("ActionDeviceKey","ActionGroupKey","ActionGroupMask"):
            try: print("  set", k, cam.set(k, "1"))
            except Exception as e: print("  set", k, "ERR", e)
        try: print("send_action ->", vg.send_action(1, 1, 1, destination="127.0.0.1", timeout_ms=300))
        except Exception: traceback.print_exc()
        for a in ("actions", "action_count", "stats"):
            if hasattr(fake, a):
                v = getattr(fake, a); print("  fake.", a, "=", v() if callable(v) else v)
        print("  FakeGigeCamera keys:", FakeGigeCamera.DEVICE_KEY, FakeGigeCamera.GROUP_KEY, FakeGigeCamera.GROUP_MASK)
        print("  send_action with fake keys ->", vg.send_action(FakeGigeCamera.DEVICE_KEY, FakeGigeCamera.GROUP_KEY, FakeGigeCamera.GROUP_MASK, destination="127.0.0.1", timeout_ms=300), "fake.actions()=", fake.actions())
