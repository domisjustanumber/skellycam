"""Scratch harness (not shipped): run gev_ptp_sync_test.main() against two viva fakes (127.0.0.1/.2) with
SIMULATED PTP registers and clocks, to exercise code paths no emulator implements.
usage: python harness_ptp_sim.py <gige_dir> synced|unsynced"""
import sys, time
sys.path.insert(0, sys.argv[1])
import gev_common as gev
import gev_ptp_sync_test as t

MODE = sys.argv[2]
sim = {}  # (ip, addr) -> value
calls = {"status": 0}
real_read, real_write = gev.GvcpClient.read_reg, gev.GvcpClient.write_reg
CAP_EXTRA = gev.CAP["ieee1588"] | gev.CAP["action"] | gev.CAP["scheduled_action"]

def read_reg(self, addr):
    if addr == gev.REG_GVCP_CAPABILITY:
        return real_read(self, addr) | CAP_EXTRA
    if addr == gev.REG_IEEE1588_STATUS:
        calls["status"] += 1
        if calls["status"] < 6:
            return 4  # Listening
        if MODE == "unsynced":
            return 6  # both Master -> never settles
        return 6 if self.ip == "127.0.0.1" else 9
    if (self.ip, addr) in sim:
        return sim[(self.ip, addr)]
    if addr in (gev.REG_N_ACTION_SIGNALS,):
        return 2
    return real_read(self, addr)

def write_reg(self, addr, value, restore=False):
    if addr in (gev.REG_GVCP_CONFIGURATION, gev.REG_ACTION_DEVICE_KEY) or 0x9800 <= addr < 0x9900 or addr == gev.REG_TIMESTAMP_CONTROL:
        if restore and addr not in self._restored_addrs:
            self._restore.append((addr, sim.get((self.ip, addr), 0))); self._restored_addrs.add(addr)
        sim[(self.ip, addr)] = value & 0xFFFFFFFF
        return
    return real_write(self, addr, value, restore)

def latch(self):
    t0 = time.perf_counter_ns(); time.sleep(0.0002); t1 = time.perf_counter_ns()
    mid = (t0 + t1) // 2
    if MODE == "synced":
        dev = mid + 5_000_000_000 + (150 if self.ip == "127.0.0.2" else 0)
    else:  # 3 s apart and 25 ppm drift
        dev = mid + (3_000_000_000 + int(mid * 25e-6) if self.ip == "127.0.0.2" else 5_000_000_000)
    return t0, t1, dev

gev.GvcpClient.read_reg = read_reg
gev.GvcpClient.write_reg = write_reg
gev.GvcpClient.latch_timestamp = latch
rc = t.main(["--ip", "127.0.0.1", "--ip", "127.0.0.2", "--enable-ptp", "--ptp-timeout", "8", "--settle-s", "1",
             "--duration", "4", "--interval", "0.1", "--device-key", "0x42", "--group-key", "1", "--group-mask", "1",
             "--delay-ms", "200"])
print("main() returned", rc)
