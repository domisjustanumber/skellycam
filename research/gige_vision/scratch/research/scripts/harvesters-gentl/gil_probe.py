"""Does Harvesters' ImageAcquirer.fetch() hold the GIL while blocked?
(cf. https://github.com/genicam/harvesters/issues/508)

Usage: python gil_probe.py <producer.cti> [device_index] [update_event_timeout_ms]

Measures wake-up latency of an unrelated thread (threading.Event round trip)
while idle vs while another thread loops on ia.fetch(timeout=...). Also
measures how much pure-Python work a counter thread achieves per second in
both phases.
"""
import statistics
import sys
import threading
import time

from harvesters.core import Harvester

N = 40


class Pinger:
    def __init__(self):
        self.request = threading.Event()
        self.response = threading.Event()
        self.woke_at = 0.0
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            self.request.wait()
            self.woke_at = time.perf_counter()
            self.request.clear()
            self.response.set()

    def ping_ms(self):
        self.response.clear()
        sent = time.perf_counter()
        self.request.set()
        self.response.wait()
        return (self.woke_at - sent) * 1000.0


def counter_rate(seconds=1.0):
    n = 0
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        n += 1
    return n / seconds


def measure(pinger, label):
    t = []
    for _ in range(N):
        t.append(pinger.ping_ms())
        time.sleep(0.02)
    rate = counter_rate()
    print(f"{label}: wake-up latency ms median={statistics.median(t):.3f} "
          f"p95={sorted(t)[int(0.95*N)-1]:.3f} max={max(t):.3f}; "
          f"python loop iterations/s={rate:,.0f}")


def main():
    cti = sys.argv[1]
    idx = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    h = Harvester()
    h.add_file(cti)
    h.update()
    ia = h.create(idx)
    if len(sys.argv) > 3:
        # ms; Harvesters 1.4.3 default is 1 ms (core.py L1703)
        ia.timeout_period_on_update_event_data_call = int(sys.argv[3])
    print(f"timeout_period_on_update_event_data_call = "
          f"{ia.timeout_period_on_update_event_data_call} ms")
    pinger = Pinger()
    measure(pinger, "IDLE")

    stop = threading.Event()
    frames = [0]

    def grab():
        while not stop.is_set():
            with ia.fetch(timeout=2.0):
                frames[0] += 1

    ia.start()
    th = threading.Thread(target=grab, daemon=True)
    th.start()
    time.sleep(0.5)
    measure(pinger, "LIVE (fetch loop in other thread)")
    stop.set()
    th.join(timeout=5)
    ia.stop()
    print(f"frames fetched during LIVE: {frames[0]}")
    ia.destroy()
    h.reset()


if __name__ == "__main__":
    main()
