"""Shared helpers of the BGR ring benchmarks (M5, M6, M7). Synthetic images only; nothing is saved."""
import os
import platform
import subprocess
import sys

import cv2
import numpy as np
import psutil

SIZES = {"720p": (1280, 720), "1080p": (1920, 1080)}
NOISE_SIGMA = 2.0  # q90 4:2:0: about 160 kB at 720p and 335 kB at 1080p


def photo_like(width, height, seed=0):
    """A photo-like BGR image: smooth colour regions, hard edges, texture and sensor-like noise."""
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 256, (height // 40 + 2, width // 40 + 2, 3), dtype=np.uint8)
    img = cv2.resize(small, (width, height), interpolation=cv2.INTER_CUBIC).astype(np.float32)
    for _ in range(40):  # hard-edged shapes
        colour = rng.integers(0, 256, 3).tolist()
        centre = (int(rng.integers(0, width)), int(rng.integers(0, height)))
        if rng.random() < 0.5:
            cv2.circle(img, centre, int(rng.integers(10, height // 4)), colour, -1, cv2.LINE_AA)
        else:
            size = (int(rng.integers(10, width // 4)), int(rng.integers(10, height // 4)))
            cv2.rectangle(img, centre, (centre[0] + size[0], centre[1] + size[1]), colour, -1)
    texture = cv2.GaussianBlur(rng.normal(0, 12, (height, width, 1)).astype(np.float32), (0, 0), 1.5)
    img += texture.reshape(height, width, 1) + rng.normal(0, NOISE_SIGMA, img.shape).astype(np.float32)
    return np.clip(img, 0, 255).astype(np.uint8)


def jpeg(img, sampling="420", quality=90):
    factor = {"420": cv2.IMWRITE_JPEG_SAMPLING_FACTOR_420, "422": cv2.IMWRITE_JPEG_SAMPLING_FACTOR_422}[sampling]
    ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality, cv2.IMWRITE_JPEG_SAMPLING_FACTOR, factor])
    assert ok
    return enc.tobytes()


def jpegs(size, count=8, sampling="420"):
    """`count` different JPEGs of one size (seeds 0..count-1)."""
    w, h = SIZES[size]
    return [jpeg(photo_like(w, h, seed), sampling) for seed in range(count)]


def stats_ms(values_ns):
    a = np.asarray(values_ns, dtype=np.float64) / 1e6
    return dict(n=int(a.size), median=float(np.median(a)), p95=float(np.percentile(a, 95)),
                p99=float(np.percentile(a, 99)), max=float(a.max()), mean=float(a.mean()))


def machine_info(pre_load_s=3.0):
    """CPU model, cores, versions and the CPU load of the machine before the run."""
    cpu = platform.processor()
    if sys.platform == "win32":
        try:
            cpu = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"],
                                 capture_output=True, text=True, timeout=20).stdout.strip() or cpu
        except Exception:
            pass
    import zlib
    procs = [p for p in psutil.process_iter() if p.pid not in (0, os.getpid()) and _alive(p)]  # the first cpu_percent call primes each process
    load = psutil.cpu_percent(interval=pre_load_s)
    busy = []
    for p in procs:
        try:
            busy.append((p.cpu_percent(None), p.name()))
        except psutil.Error:
            pass
    busy.sort(reverse=True)
    return dict(cpu=cpu, logical_cores=os.cpu_count(), physical_cores=psutil.cpu_count(logical=False),
                os=f"{platform.system()} {platform.release()} {platform.version()}",
                python=sys.version.split()[0], opencv=cv2.__version__, numpy=np.__version__,
                zlib_runtime=zlib.ZLIB_RUNTIME_VERSION, psutil=psutil.__version__,
                pre_run_cpu_percent=load,
                top_processes_pre_run=[dict(name=n, cpu_percent_of_one_core=round(c, 1)) for c, n in busy[:5]])


def _alive(p):
    try:
        p.cpu_percent(None)
        return True
    except psutil.Error:
        return False


def add_ring_path():
    """Put the implementation worktree on sys.path (env var SKELLYCAM_IMPL, default ../../../../skellycam-native-jpeg)."""
    root = os.environ.get("SKELLYCAM_IMPL") or os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "skellycam-native-jpeg"))
    if root not in sys.path:
        sys.path.insert(0, root)
