# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy"]
# ///
import av, inspect
print("av", av.__version__, "ffmpeg", getattr(av, "ffmpeg_version_info", None))
from av.container.output import OutputContainer
print([m for m in dir(OutputContainer) if not m.startswith("__")])
for m in ("mux", "mux_one", "close", "start_encoding"):
    f = getattr(OutputContainer, m, None)
    print(m, getattr(f, "__doc__", None))
