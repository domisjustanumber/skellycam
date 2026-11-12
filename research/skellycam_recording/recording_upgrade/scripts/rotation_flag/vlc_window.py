"""What VLC 3 actually shows: open the video in a real Direct3D11 window (rc interface, paused, stepped one
frame), read the window's client size, and grab its pixels from the screen.

Why: VLC 3 applies orientation in the video output/display. The scene filter and the rc `snapshot` command
both see the picture before that, so they show unrotated pixels even for a rotated MP4 (measured).

Usage: python -I vlc_window.py <video> <out_dir> [zoom] [extra VLC args...]
Writes <out_dir>/window.png, <out_dir>/vlc.log; prints JSON with client size.
"""
import ctypes, ctypes.wintypes as W, json, os, socket, subprocess, sys, time
from PIL import ImageGrab

VLC = r"C:\Program Files\VideoLAN\VLC\vlc.exe"
u32 = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    u32.SetProcessDPIAware()


def windows_of(pid):
    out = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, W.HWND, W.LPARAM)
    def cb(h, _):
        p = W.DWORD(); u32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u32.IsWindowVisible(h):
            n = ctypes.create_unicode_buffer(256); u32.GetWindowTextW(h, n, 256)
            out.append((h, n.value))
        return True
    u32.EnumWindows(cb, 0)
    return out


def client_rect_screen(h):
    r = W.RECT(); u32.GetClientRect(h, ctypes.byref(r))
    pt = W.POINT(0, 0); u32.ClientToScreen(h, ctypes.byref(pt))
    return pt.x, pt.y, pt.x + r.right, pt.y + r.bottom


def run(video, out, zoom="0.5", *extra, port=47124, timeout=40):
    video, out = os.path.normpath(os.path.abspath(video)), os.path.normpath(os.path.abspath(out))
    os.makedirs(out, exist_ok=True)
    log = os.path.join(out, "vlc.log")
    args = [VLC, "-I", "rc", f"--rc-host=127.0.0.1:{port}", "--rc-quiet", "--vout=direct3d11", "--no-audio",
            "--start-paused", "--no-loop", f"--zoom={zoom}", "--video-on-top", "--no-video-deco",
            "--video-x=40", "--video-y=40", "--no-osd", "--no-video-title-show",
            "--verbose=2", "--file-logging", f"--logfile={log}", *extra, video]
    p = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    res = dict(zoom=zoom, extra=list(extra))
    s = None
    try:
        t0 = time.time()
        while time.time() - t0 < 15:
            try:
                s = socket.create_connection(("127.0.0.1", port), timeout=2); break
            except OSError:
                time.sleep(0.3)
        if s is None:
            res["error"] = "no rc connection"
        else:
            time.sleep(2.0)
            s.sendall(b"frame\n"); time.sleep(1.5)
            wins = windows_of(p.pid)
            res["windows"] = [t for _, t in wins]
            vw = [h for h, t in wins if "Direct3D11" in t or "VLC" in t] or [h for h, _ in wins]
            if vw:
                h = vw[0]
                x0, y0, x1, y1 = client_rect_screen(h)
                res["client_w"], res["client_h"] = x1 - x0, y1 - y0
                u32.SetForegroundWindow(h); time.sleep(0.5)
                ImageGrab.grab(bbox=(x0, y0, x1, y1), all_screens=True).save(os.path.join(out, "window.png"))
                res["png"] = "window.png"
            s.sendall(b"quit\n"); time.sleep(0.5)
        res["rc"] = p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill(); res["rc"] = "timeout"
    finally:
        if s: s.close()
    return res


if __name__ == "__main__":
    print(json.dumps(run(*sys.argv[1:]), indent=1))
