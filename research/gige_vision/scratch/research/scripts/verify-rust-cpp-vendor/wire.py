import socket, threading, sys
import viva_genicam as vg
srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); srv.bind(("127.0.0.1", 3956)); srv.settimeout(3)
got = []
def rx():
    for _ in range(2):
        try:
            d, a = srv.recvfrom(1500); got.append(d.hex())
        except Exception as e: got.append("timeout")
t = threading.Thread(target=rx); t.start()
print("unscheduled ->", vg.send_action(0x11223344, 0x55667788, 0xFFFFFFFF, destination="127.0.0.1", timeout_ms=100))
print("scheduled   ->", vg.send_action(0x11223344, 0x55667788, 0xFFFFFFFF, scheduled_time=0x0102030405060708, destination="127.0.0.1", timeout_ms=100))
t.join()
for g in got: print("wire:", g)
