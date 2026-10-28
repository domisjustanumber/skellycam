"""cProfile of create_frontend_payload for 5x1080p (skellycam @ 23ccbf20). Run with the skellycam venv python."""
import cProfile, pstats, sys, io, logging
logging.disable(logging.CRITICAL)
sys.path.insert(0, r"C:\Users\Dom\GitHub\freemocap\skellycam")
import numpy as np
from ui_tap_bench import synthetic_image
from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.types.frame_dtype_factories import create_frame_dtype
from skellycam.core.types.frontend_payload_bytearray import create_frontend_payload
h, w = 1080, 1920
frames = {}
for i in range(5):
    cfg = CameraConfig(camera_id=f"cam{i}", camera_index=i, resolution=ImageResolution(height=h, width=w))
    f = np.recarray(1, dtype=create_frame_dtype(cfg))
    f.frame_metadata.camera_info[0] = cfg.to_frame_camera_info()
    f.frame_metadata.frame_number[0] = 0
    f.image[0] = synthetic_image(h, w, i)
    frames[f"cam{i}"] = f
print("rotation field:", frames["cam0"].frame_metadata.camera_info.rotation)
create_frontend_payload(latest_frames=frames)
pr = cProfile.Profile(); pr.enable()
for _ in range(30):
    create_frontend_payload(latest_frames=frames)
pr.disable()
s = io.StringIO(); pstats.Stats(pr, stream=s).sort_stats("tottime").print_stats(12); print(s.getvalue())
