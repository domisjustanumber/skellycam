"""Mock-kernel smoke test of v4l2_mmap_mjpeg.py on Windows. Writes only to the scratchpad."""
import ctypes, io, sys, time, types, os, runpy, json, collections
from pathlib import Path

SCR = Path(__file__).resolve().parent / "mockout"
SCR.mkdir(exist_ok=True)
REPO = Path(r"C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\mjpeg")
SCRIPT = REPO / "drafts" / "linux" / "v4l2_mmap_mjpeg.py"
sys.path.insert(0, str(REPO))
import mjpeg_common as mc
def _rd(test, *parts):
    p = SCR.joinpath("results", test, *parts); p.mkdir(parents=True, exist_ok=True); return p
mc.results_dir = _rd
mc.plat = lambda: "linux"

from PIL import Image
b = io.BytesIO(); Image.new("RGB", (1280, 720), (10, 200, 30)).save(b, "JPEG"); JPG = b.getvalue()

# time functions missing on Windows
t0 = time.perf_counter_ns()
time.CLOCK_MONOTONIC, time.CLOCK_REALTIME, time.CLOCK_PROCESS_CPUTIME_ID = 1, 0, 2
time.clock_gettime_ns = lambda c: {1: time.perf_counter_ns(), 0: time.time_ns(), 2: time.process_time_ns()}[c]
import platform; platform.uname(); platform.platform()
_U = collections.namedtuple("U", "sysname nodename release version machine"); os.uname = lambda: _U("Linux", "mock", "6.8.0-mock", "#1", "x86_64")
SUBST = os.environ.get("MOCK_SUBST")  # e.g. YUYV to test fallback

state = collections.defaultdict(dict)
calls = collections.Counter()


def ioctl(fd, req, arg, mut=True):
    m = sys.modules["__mockv4l2__"]
    names = {getattr(m, n): n for n in dir(m) if n.startswith("VIDIOC_")}
    n = names.get(req, hex(req)); calls[n] += 1
    st = state[fd]
    if n == "VIDIOC_QUERYCAP":
        arg.driver, arg.card, arg.bus_info = b"uvcvideo", b"Mock Cam %d" % fd, b"usb-0000:00:14.0-%d" % fd
        arg.capabilities, arg.device_caps = 0x84a00001, 0x04200001
    elif n == "VIDIOC_S_FMT":
        if SUBST: arg.fmt.pix.pixelformat = m.fourcc(SUBST)
        st["fmt"] = (arg.fmt.pix.width, arg.fmt.pix.height, arg.fmt.pix.pixelformat); arg.fmt.pix.sizeimage = 1843200
    elif n == "VIDIOC_G_FMT":
        arg.fmt.pix.width, arg.fmt.pix.height, arg.fmt.pix.pixelformat = st["fmt"]
    elif n in ("VIDIOC_S_PARM", "VIDIOC_G_PARM"):
        arg.parm.capture.capability = 0x1000; arg.parm.capture.timeperframe.numerator = 1; arg.parm.capture.timeperframe.denominator = 30
    elif n == "VIDIOC_G_CTRL":
        arg.value = st.get(arg.id, 3)
    elif n == "VIDIOC_S_CTRL":
        st[arg.id] = arg.value
    elif n == "VIDIOC_QUERYCTRL":
        arg.name, arg.minimum, arg.maximum = b"ctl", 1, 5000
    elif n == "VIDIOC_REQBUFS":
        st["q"] = collections.deque()
    elif n == "VIDIOC_QUERYBUF":
        arg.length, arg.m.offset = 2_000_000, arg.index * 4096
    elif n == "VIDIOC_QBUF":
        st["q"].append(arg.index)
    elif n == "VIDIOC_DQBUF":
        time.sleep(1 / 30)
        if not st["q"]:
            raise BlockingIOError(11, "EAGAIN")
        i = st["q"].popleft(); st["seq"] = st.get("seq", -1) + 1
        ns = time.perf_counter_ns() - 3_000_000
        arg.index, arg.bytesused, arg.flags, arg.sequence = i, len(JPG), 0x2000 | 0x10000 | 0x1, st["seq"]
        arg.timestamp.tv_sec, arg.timestamp.tv_usec = ns // 1_000_000_000, (ns % 1_000_000_000) // 1000
    elif n.startswith("VIDIOC_ENUM"):
        if arg.index > 0: raise OSError(22, "EINVAL")
        if n == "VIDIOC_ENUM_FMT": arg.pixelformat, arg.description, arg.flags = m.fourcc("MJPG"), b"Motion-JPEG", 1
        elif n == "VIDIOC_ENUM_FRAMESIZES": arg.type = 1; arg.u.discrete.width, arg.u.discrete.height = 1280, 720
        else: arg.type = 1; arg.u.discrete.numerator, arg.u.discrete.denominator = 1, 30
    return 0


class FakeMap:
    def __init__(self, *a, **k): pass
    def __getitem__(self, s): return JPG[s]
    def close(self): pass


sys.modules["fcntl"] = types.SimpleNamespace(ioctl=ioctl)
sys.modules["mmap"] = types.SimpleNamespace(mmap=FakeMap, MAP_SHARED=1, PROT_READ=1, PROT_WRITE=2)
import select as _sel
_sel.select = lambda r, w, x, t=None: (r, [], [])
_fds = iter(range(10, 100))
real_open, real_close = os.open, os.close
os.open = lambda p, fl, *a: next(_fds) if "video" in str(p) else real_open(p, fl, *a)
os.close = lambda fd: None if fd >= 10 and fd < 100 else real_close(fd)
os.O_NONBLOCK = 0x800
import psutil  # noqa: import before faking platform
sys.platform = "linux"

src = SCRIPT.read_text()
mod = types.ModuleType("__mockv4l2__"); mod.__file__ = str(SCRIPT)
sys.modules["__mockv4l2__"] = mod
sys.argv = [str(SCRIPT)] + sys.argv[1:]
exec(compile(src.replace('if __name__ == "__main__":\n    sys.exit(main())', ""), str(SCRIPT), "exec"), mod.__dict__)
_real_list_all = mod.list_all
class _P(type(Path())):
    def glob(self, pat):
        return [Path("/dev/video0"), Path("/dev/video2")] if self.as_posix() == "/dev" else super().glob(pat)
mod.Path = _P
rc = mod.main()
print("rc", rc, dict(calls))
