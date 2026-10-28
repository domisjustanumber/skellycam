"""send_action timing / directed broadcast, Bayer decode cost.

usage: t7_misc.py FAKE_IP DIRECTED_BROADCAST
"""
import sys, time
import numpy as np
import viva_genicam as vg
from viva_genicam.testing import FakeGigeCamera

ip, directed = sys.argv[1], sys.argv[2]
K = (FakeGigeCamera.DEVICE_KEY, FakeGigeCamera.GROUP_KEY, FakeGigeCamera.GROUP_MASK)
with FakeGigeCamera(width=1280, height=1024, fps=30, bind_ip=ip, pixel_format="BayerRG8") as fake:
    for to in (0, 50, 200):
        t = time.perf_counter()
        r = vg.send_action(*K, destination=ip, timeout_ms=to)
        print(f"send_action(timeout_ms={to}) unicast -> {r} in {(time.perf_counter() - t) * 1e3:.1f} ms; fake.actions={fake.actions()}")
    for dest in (directed, "255.255.255.255"):
        before = fake.actions()
        t = time.perf_counter()
        try:
            r = vg.send_action(*K, destination=dest, timeout_ms=200)
        except Exception as e:
            r = f"{type(e).__name__}: {e}"
        print(f"send_action(dest={dest}) -> {r} in {(time.perf_counter() - t) * 1e3:.1f} ms; acted {fake.actions() - before}")
    cam = vg.connect_gige(next(i for i in vg.discover(timeout_ms=600, all=True) if i.ip == ip))
    with cam.stream() as frames:
        fr = frames.next_frame(timeout_ms=3000)
    print("frame", fr, "pixel_format", fr.pixel_format)
    for name, fn in [
        ("to_numpy() Bayer mosaic", lambda: fr.to_numpy()),
        ("np.frombuffer(payload())", lambda: np.frombuffer(fr.payload(), np.uint8).reshape(fr.height, fr.width)),
        ("to_numpy(demosaic=True)", lambda: fr.to_numpy(demosaic=True)),
        ("to_rgb8()", lambda: fr.to_rgb8()),
    ]:
        t = time.perf_counter()
        for _ in range(20):
            a = fn()
        print(f"  {name:28s} {(time.perf_counter() - t) / 20 * 1e3:.3f} ms {a.shape} {a.dtype}")
    mosaic = fr.to_numpy()
    rgb = fr.to_numpy(demosaic=True)
    try:
        import cv2
        for code in ("COLOR_BayerRG2RGB", "COLOR_BayerBG2RGB"):
            ref = cv2.cvtColor(mosaic, getattr(cv2, code))
            print(f"  mean |viva demosaic - cv2.{code}| = {np.abs(rgb.astype(int) - ref.astype(int)).mean():.2f}")
    except ImportError:
        print("  (cv2 not installed; skipped demosaic comparison)")
    print("  mosaic top-left 4x4:\n", mosaic[:4, :4])
    cam.close()
