r"""T-S6 part 3: hard kills of a child process running capture -> encode -> mux -> sidecar.

Kills: os._exit(1) at chosen writer points (before_mux, after_mux, mid_record = torn record, after_record, flush,
after_container_close), and TerminateProcess (Popen.kill) from the parent at a random time.
After each kill: every on-disk record must describe a complete JPEG on disk (CRC, barcode, times); loss accounting
from the child's event log (S = submitted, M = muxed, R = record written); then recovery (remux + offset rebuild)
and a second verify.

Run: <scratch tjvenv>\python.exe -I crash_kill.py      (child = same interpreter, `child` argv)
"""
from __future__ import annotations

import ctypes
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import numpy as np  # noqa: E402

import eplib as E  # noqa: E402
from pairing_qsv import gap_pattern  # noqa: E402

SIZE = "720p"


# ------------------------------------------------------------------ child
def child(mode: str, stem: str, point: str, at: int, n: int):
    stem = Path(stem)
    src = E.FrameSource(SIZE)
    if mode == "passthrough":
        import simplejpeg
        enc = E.PassthroughEnc()
    elif mode.startswith("qsv"):
        enc = E.QsvEnc(SIZE, async_depth=1 if mode == "qsv_ad1" else None)
    else:
        enc = E.TurboPool(SIZE, int(mode.split("_w")[1]))
        enc.warm()
        Path(str(stem) + ".pids").write_text(" ".join(map(str, enc.worker_pids())))
    log = open(str(stem) + ".log", "w")

    def hook(p, wi):
        if p == point and wi == at:
            if p == "mid_record":
                return "torn"
            os._exit(1)
        return None

    w = E.PairingWriter(stem, *E.DIMS[SIZE], enc.name, hook=hook, log=log)
    sfns = gap_pattern("bursty", n, seed=5)
    t_next = time.perf_counter()
    log.write("READY\n")
    log.flush()
    for seq, sfn in enumerate(sfns):
        now = time.perf_counter()
        if t_next > now:
            time.sleep(t_next - now)
        t_next += 1 / E.FPS
        a = src.frame(sfn)
        payload = simplejpeg.encode_jpeg_yuv_planes(*E.yuyv_planes(a), quality=95, fastdct=False) \
            if mode == "passthrough" else a
        log.write(f"S {seq} {sfn}\n")
        log.flush()
        for o in enc.submit(seq, payload, E.make_meta(sfn)):
            w.write(o)
    outs = enc.flush()
    for k, o in enumerate(outs):
        hook("flush", k)
        w.write(o)
    w.close()
    log.write("CLOSED\n")
    log.flush()
    enc.close()


# ------------------------------------------------------------------ parent
def alive(pid: int) -> bool:
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    k32.GetExitCodeProcess(h, ctypes.byref(code))
    k32.CloseHandle(h)
    return code.value == 259


def analyze(stem: Path) -> dict:
    ev = {"S": [], "M": [], "R": []}
    closed = False
    lp = Path(str(stem) + ".log")
    for line in lp.read_text().splitlines():
        parts = line.split()
        if parts and parts[0] in ev:
            ev[parts[0]].append(int(parts[1]))
        closed |= line == "CLOSED"
    v = E.verify(stem)
    S, M, R = set(ev["S"]), set(ev["M"]), set(ev["R"])
    recs = E.read_sidecar(Path(str(stem) + ".skfr"))["records"]
    on_disk_pk = v["mkv_packets"]
    muxed = len(M)
    out = {"submitted": len(S), "muxed": muxed, "records_logged": len(R), "records_on_disk": v["records"],
           "closed": closed,
           "lost_total": len(S) - v["records"],
           "lost_in_encoder_or_pool": len(S) - muxed,
           "lost_muxed_not_on_disk": muxed - on_disk_pk,
           "lost_on_disk_without_record": on_disk_pk - v["records"],
           "records_subset_of_muxed": set(int(r["write_index"]) for r in recs) <= set(range(muxed)),
           "verify": v}
    out["every_record_pairs"] = (v["records"] == 0 or v["all_pairs_ok"])
    return out


def run_one(mode: str, point: str, at: int, n: int, terminate_after: float | None = None) -> dict:
    d = E.SCRATCH / "crash"
    d.mkdir(parents=True, exist_ok=True)
    tag = f"{mode}_{point}_{at}" if terminate_after is None else f"{mode}_terminate_{terminate_after:.2f}s"
    stem = d / tag
    for suf in (".mkv", ".skfr", ".log", ".pids", ".recovered.mkv", ".recovered.skfr"):
        p = Path(str(stem) + suf)
        if p.exists():
            p.unlink()
    cmd = [sys.executable, "-I", __file__, "child", mode, str(stem), point, str(at), str(n)]
    out_path = Path(str(stem) + ".out")
    out_fh = open(out_path, "wb")  # a file, not a pipe: workers inherit the handle and would hold a pipe open
    proc = subprocess.Popen(cmd, stdout=out_fh, stderr=subprocess.STDOUT)
    killed_by = "os._exit(1)" if terminate_after is None else "TerminateProcess"
    if terminate_after is not None:
        lp = Path(str(stem) + ".log")
        t_end = time.time() + 60
        while time.time() < t_end and not (lp.exists() and "READY" in lp.read_text()):
            time.sleep(0.05)
        time.sleep(terminate_after)
        proc.kill()  # TerminateProcess on Windows
    try:
        proc.wait(timeout=120)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    out_fh.close()
    outp = out_path.read_bytes()
    res = {"tag": tag, "mode": mode, "kill": killed_by, "point": point, "at": at, "exit_code": proc.returncode,
           "child_output_tail": outp.decode(errors="replace")[-300:]}
    pids_p = Path(str(stem) + ".pids")
    if pids_p.exists():
        pids = [int(x) for x in pids_p.read_text().split()]
        time.sleep(2.0)
        res["orphan_workers_after_2s"] = [p for p in pids if alive(p)]
        for p in res["orphan_workers_after_2s"]:  # clean up so the matrix continues
            subprocess.run(["taskkill", "/F", "/PID", str(p)], capture_output=True)
    res.update(analyze(stem))
    try:
        rec = E.recover(stem)
        rv = E.verify(Path(rec["out_stem"]))
        res["recovery"] = rec
        res["recovered_verify"] = {k: rv[k] for k in ("records", "all_pairs_ok", "mkv_packets",
                                                      "mkv_packets_without_record", "container_pts_offset_crc_ok",
                                                      "mkv_pts_in_order", "bad_examples")}
    except Exception as ex:  # noqa: BLE001
        res["recovery_error"] = f"{type(ex).__name__}: {ex}"[:300]
    keep = tag in ("qsv_after_record_90", "turbo_w3_after_record_90")
    if not keep:
        for suf in (".mkv", ".recovered.mkv"):
            p = Path(str(stem) + suf)
            if p.exists():
                p.unlink()
    return res


def save(res: dict, runs: list):
    res["runs"] = runs
    (E.RESULTS / "crash_kill.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")


def main():
    import av
    res = {"versions": {"python": sys.version.split()[0], "av": av.__version__, "numpy": np.__version__},
           "size": SIZE, "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
    try:
        import simplejpeg
        res["versions"]["simplejpeg"] = simplejpeg.__version__
    except ImportError:
        pass
    runs = []
    points = [("before_mux", 90), ("after_mux", 90), ("mid_record", 89), ("after_record", 90), ("flush", 0),
              ("flush", 1), ("after_container_close", 150)]
    rnd = random.Random(2026)
    for mode in ("passthrough", "qsv", "qsv_ad1", "turbo_w3"):
        for point, at in points:
            if point == "flush" and mode == "passthrough":
                continue
            n = 150 if point in ("flush", "after_container_close") else 400
            r = run_one(mode, point, at, n)
            runs.append(r)
            save(res, runs)
            print(r["tag"], "pairs", r["every_record_pairs"], "lost", r["lost_total"],
                  (r["lost_in_encoder_or_pool"], r["lost_muxed_not_on_disk"], r["lost_on_disk_without_record"]),
                  "torn", r["verify"]["torn_tail_bytes"], "rec", r.get("recovered_verify", {}).get("all_pairs_ok"),
                  flush=True)
        for _ in range(3):
            r = run_one(mode, "none", -1, 100000, terminate_after=rnd.uniform(1.5, 4.0))
            runs.append(r)
            save(res, runs)
            print(r["tag"], "pairs", r["every_record_pairs"], "lost", r["lost_total"],
                  (r["lost_in_encoder_or_pool"], r["lost_muxed_not_on_disk"], r["lost_on_disk_without_record"]),
                  "torn", r["verify"]["torn_tail_bytes"], "rec", r.get("recovered_verify", {}).get("all_pairs_ok"),
                  flush=True)
    res["runs"] = runs
    res["summary"] = {"runs": len(runs), "every_record_pairs": sum(r["every_record_pairs"] for r in runs),
                      "recovered_all_pairs_ok": sum(bool(r.get("recovered_verify", {}).get("all_pairs_ok"))
                                                    for r in runs)}
    res["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    (E.RESULTS / "crash_kill.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps(res["summary"]))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "child":
        child(sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]), int(sys.argv[6]))
    else:
        main()
