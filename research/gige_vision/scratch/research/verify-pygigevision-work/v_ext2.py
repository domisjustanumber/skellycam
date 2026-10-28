import socket, struct, time, sys
sys.argv = ["x", "none"]
exec(open("/w/v_synth.py").read().split("test = sys.argv[1]")[0])
import threading
errs = []
threading.excepthook = lambda a: errs.append(f"{a.exc_type.__name__}: {a.exc_value}")
rx = GVSPReceiver(local_ip="127.0.0.1", camera_ip="127.0.0.2", packet_size=1500); rx.start()
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); dst = ("127.0.0.1", rx.port)
for bid in (65535, 65536):
    s.sendto(leader(bid, 320, 240, 0x01080001, True), dst)
    for i in range(52):
        if i + 1 != 5: s.sendto(data(bid, i + 1, True, bytes(1480)), dst)
    time.sleep(0.2)   # let socket timeout trigger the gap check before trailer
    s.sendto(trailer(bid, 53, 240, True), dst)
    r = rx.get_frame_with_info(1.0)
    print(f"block {bid}: frame={'None' if r is None else r[1]['complete']} thread_alive={rx._thread.is_alive()} errors={errs}")
