"""Streaming timestamp sidecar durability: per-frame CSV vs fixed-size binary records, flush vs no flush vs fsync,
under (a) process kill and (b) truncation / zero-filled tail (power-loss emulation).

Writers (child process, one row per frame, 8 int64 timestamp columns like sfn26 csv_writer.rs):
  csv_flush     csv.writer row + file.flush() per row  (the sfn26 CsvWriter pattern: write_record + flush)
  csv_noflush   csv.writer row, Python's default buffering only
  csv_fsync     csv row + flush + os.fsync per row
  bin_flush     72-byte record <q frame, 7q timestamps, I crc32, I magic> + flush per row
  bin_noflush   binary record, default buffering
Readers:
  csv: Python csv module + int() of every field; a row counts only if it has all 8 fields and each parses. pandas
       read_csv is also tried when pandas is importable.
  bin: records until the first CRC/magic failure.

usage: python sidecar_durability.py      -> results/crash_resilience/sidecar_durability.json/.md
"""
from __future__ import annotations

import csv
import io
import json
import os
import random
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_cr as cc  # noqa: E402

HDR = ["frame_number", "loop_start_ns", "frame_available_ns", "post_jpeg_extract_ns", "pre_send_ns",
       "gatherer_received_ns", "pre_frame_record_ns", "post_frame_record_ns"]
REC = struct.Struct("<8qII")
MAGIC = 0x53435453


def row(i: int) -> list[int]:
    base = 1_700_000_000_000_000_000 + i * 33_333_333
    return [i] + [base + k * 1000 for k in range(7)]


def child(kind: str, path: str, n: int):
    """write rows; print 'R i' after each row is handed to the file object (and flushed/fsynced per kind)"""
    if kind.startswith("csv"):
        f = open(path, "w", newline="")
        w = csv.writer(f)
        w.writerow(HDR)
        f.flush()
        for i in range(n):
            w.writerow(row(i))
            if kind in ("csv_flush", "csv_fsync"):
                f.flush()
            if kind == "csv_fsync":
                os.fsync(f.fileno())
            print(f"R {i + 1}", flush=True)
    else:
        f = open(path, "wb")
        for i in range(n):
            r = row(i)
            body = struct.pack("<8q", *r)
            f.write(REC.pack(*r, zlib.crc32(body), MAGIC))
            if kind == "bin_flush":
                f.flush()
            print(f"R {i + 1}", flush=True)
    print("IDLE", flush=True)
    sys.stdin.readline()


def parse_csv(b: bytes) -> dict:
    ok = 0
    err = None
    try:
        rd = csv.reader(io.StringIO(b.decode("utf-8", errors="replace"), newline=""))
        hdr = next(rd, None)
        for r in rd:
            if len(r) != 8:
                break
            try:
                vals = [int(x) for x in r]
            except ValueError:
                break
            if vals != row(ok):
                break
            ok += 1
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:80]}"
    out = {"rows_ok": ok, "csv_error": err}
    try:
        import pandas as pd
        try:
            df = pd.read_csv(io.BytesIO(b))
            out["pandas_rows"] = len(df)
            out["pandas_last_row_complete"] = bool(len(df) == 0 or df.iloc[-1].notna().all())
            if len(df):
                last = df.iloc[-1].tolist()
                out["pandas_last_row_correct"] = bool(df.iloc[-1].notna().all() and [int(x) for x in last] == row(len(df) - 1))
        except Exception as e:
            out["pandas_error"] = f"{type(e).__name__}: {str(e)[:80]}"
    except ImportError:
        out["pandas"] = "not installed"
    return out


def parse_bin(b: bytes) -> dict:
    ok = 0
    for k in range(len(b) // REC.size):
        v = REC.unpack_from(b, k * REC.size)
        if v[9] != MAGIC or zlib.crc32(struct.pack("<8q", *v[:8])) != v[8] or v[0] != ok:
            break
        ok += 1
    return {"rows_ok": ok, "trailing_bytes": len(b) - ok * REC.size}


def parse(kind: str, b: bytes) -> dict:
    return parse_csv(b) if kind.startswith("csv") else parse_bin(b)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        child(sys.argv[2], sys.argv[3], int(sys.argv[4]))
        return
    d = cc.TEMP / "sidecar"
    d.mkdir(parents=True, exist_ok=True)
    kinds = ["csv_flush", "csv_noflush", "csv_fsync", "bin_flush", "bin_noflush"]
    res = {"python": sys.version.split()[0], "kill": [], "truncation": []}
    try:
        import pandas
        res["pandas"] = pandas.__version__
    except ImportError:
        res["pandas"] = None
    # (a) kill after K rows reported
    for kind in kinds:
        for k in (1, 37, 500):
            p = d / f"{kind}_kill{k}.{'csv' if kind.startswith('csv') else 'bin'}"
            pr = subprocess.Popen([str(cc.VENV_PY), __file__, "--child", kind, str(p), str(k)], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, text=True)
            last = 0
            for line in pr.stdout:
                if line.startswith("R "):
                    last = int(line.split()[1])
                if line.strip() == "IDLE":
                    pr.kill()
                    break
            pr.wait()
            b = p.read_bytes()
            r = {"kind": kind, "rows_reported": last, "bytes": len(b), **parse(kind, b)}
            res["kill"].append(r)
            print("kill", r, flush=True)
    # (b) truncation and zero-filled tails of a complete 2000-row file
    for kind in ("csv_flush", "bin_flush"):
        p = d / f"{kind}_full.{'csv' if kind.startswith('csv') else 'bin'}"
        pr = subprocess.Popen([str(cc.VENV_PY), __file__, "--child", kind, str(p), "2000"], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, text=True)
        for line in pr.stdout:
            if line.strip() == "IDLE":
                pr.kill()
                break
        pr.wait()
        full = p.read_bytes()
        rng = random.Random(20261109)
        offs = sorted(rng.randrange(1, len(full)) for _ in range(24))
        rowsz = REC.size if kind.startswith("bin") else None
        for off in offs:
            for tail in ("cut", "cut+zeros4096"):
                b = full[:off] + (b"\x00" * 4096 if tail != "cut" else b"")
                if kind.startswith("csv"):
                    ideal = full[:off].count(b"\n") - 1  # complete lines after the header
                else:
                    ideal = off // rowsz
                r = {"kind": kind, "offset": off, "tail": tail, "ideal_rows": max(ideal, 0), **parse(kind, b)}
                res["truncation"].append(r)
    (cc.RES / "sidecar_durability.json").write_text(json.dumps(res, indent=1))
    L = ["# Timestamp sidecar durability (generated by sidecar_durability.py)", "",
         f"Python {res['python']}; pandas {res['pandas']}. Kill = Popen.kill() after the child reported K rows written.", "",
         "## Process kill", "", "| writer | rows reported written | bytes on disk | rows parsed ok | parser error / note |", "|---|---|---|---|---|"]
    for r in res["kill"]:
        note = r.get("csv_error") or (f"pandas rows {r.get('pandas_rows')}" if "pandas_rows" in r else r.get("pandas_error", "")) or ""
        if "trailing_bytes" in r:
            note = f"trailing bytes {r['trailing_bytes']}"
        L.append(f"| {r['kind']} | {r['rows_reported']} | {r['bytes']} | {r['rows_ok']} | {note} |")
    L += ["", "## Truncation (24 offsets) and truncation + 4096 zero bytes (size extended, data never written)", "",
          "| writer | tail | offsets | rows ok == ideal | rows ok < ideal | rows ok > ideal | parser exceptions | pandas: rows | pandas: last row NaN-padded / silently wrong values / errors |",
          "|---|---|---|---|---|---|---|---|---|"]
    for kind in ("csv_flush", "bin_flush"):
        for tail in ("cut", "cut+zeros4096"):
            rs = [r for r in res["truncation"] if r["kind"] == kind and r["tail"] == tail]
            eq = sum(r["rows_ok"] == r["ideal_rows"] for r in rs)
            lt = sum(r["rows_ok"] < r["ideal_rows"] for r in rs)
            gt = sum(r["rows_ok"] > r["ideal_rows"] for r in rs)
            ex = sum(1 for r in rs if r.get("csv_error"))
            pdr = "n/a" if kind.startswith("bin") else f"{sum(1 for r in rs if 'pandas_rows' in r and r['pandas_rows'] > r['ideal_rows'])} offsets with pandas rows > ideal"
            pde = "n/a" if kind.startswith("bin") else (f"{sum(1 for r in rs if r.get('pandas_last_row_complete') is False)} / "
                  f"{sum(1 for r in rs if r.get('pandas_last_row_complete') is True and r.get('pandas_last_row_correct') is False)} / "
                  f"{sum(1 for r in rs if 'pandas_error' in r)}")
            L.append(f"| {kind} | {tail} | {len(rs)} | {eq} | {lt} | {gt} | {ex} | {pdr} | {pde} |")
    (cc.RES / "sidecar_durability.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
