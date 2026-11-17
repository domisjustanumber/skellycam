# /// script
# requires-python = "==3.12.*"
# dependencies = ["pyarrow==26.0.0", "numpy==2.4.6", "pandas==2.3.3"]
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""Write every design x encoding x codec file, time write/read, and check the pyarrow round trip bit for bit.

  uv run --script write_matrix.py [--frames N] [--tag main] [--configs design:enc:codec,...] [--drop-files]

Outputs results/parquet_dtypes/matrix_<tag>.csv (+ precision.json, source_summary.json for tag main) and keeps
the Parquet files + expected Arrow IPC under the scratchpad (rebuildable) unless --drop-files.
"""
import argparse
import csv
import gc
import json
import statistics
import time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

import pq_common as C


def precision_stats(channels):
    out = {}
    for c in channels:
        v = c["values"].reshape(-1)
        v = v[~np.isnan(v)]
        err = np.abs(v.astype(np.float32).astype(np.float64) - v)
        rec = out.setdefault(c["kind"], dict(units=sorted(set(c["components"].values())), n=0, max_abs=0.0, max_abs_err=0.0, max_rel_err=0.0))
        rec["n"] += int(v.size)
        rec["max_abs"] = max(rec["max_abs"], float(np.abs(v).max()))
        rec["max_abs_err"] = max(rec["max_abs_err"], float(err.max()))
        nz = v != 0
        rec["max_rel_err"] = max(rec["max_rel_err"], float((err[nz] / np.abs(v[nz])).max()))
        if c["kind"].startswith("ROTATIONS"):
            q = c["values"].reshape(-1, 4)
            q = q[~np.isnan(q).any(1)]
            for label, arr in (("f64", q), ("f32", q.astype(np.float32).astype(np.float64))):
                sq = np.zeros(len(arr))
                for axis in range(4):  # validator's addition order (arrow_schema.py:207-208)
                    sq += arr[:, axis] * arr[:, axis]
                rec[f"max_norm2_dev_{label}"] = max(rec.get(f"max_norm2_dev_{label}", 0.0), float(np.abs(sq - 1).max()))
    for t0 in (0.0, 3600.0, 7200.0):  # time-valued rows if they were float32, at 0 s / 1 h / 2 h into a take
        ts = next(c for c in channels if c["kind"] == "TIMESTAMPS")["times"] + t0
        e = np.abs(ts.astype(np.float32).astype(np.float64) - ts)
        out[f"TIMESTAMPS_as_float32_offset_{int(t0)}s"] = dict(max_abs_err_s=float(e.max()), min_interval_s=float(np.diff(ts.astype(np.float32)).min()),
                                                               max_interval_s=float(np.diff(ts.astype(np.float32)).max()))
    return out


def column_bytes(path):
    md = pq.ParquetFile(path).metadata
    sizes, encodings, codecs = {}, {}, set()
    for rg in range(md.num_row_groups):
        g = md.row_group(rg)
        for j in range(g.num_columns):
            col = g.column(j)
            sizes[col.path_in_schema] = sizes.get(col.path_in_schema, 0) + col.total_compressed_size
            encodings.setdefault(col.path_in_schema, set()).update(col.encodings)
            codecs.add(col.compression)
    return sizes, {k: sorted(v) for k, v in encodings.items()}, sorted(codecs), md.num_row_groups


def timed(fn, reps):
    out = []
    for _ in range(reps):
        gc.collect()
        t = time.perf_counter()
        fn()
        out.append(time.perf_counter() - t)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=None)
    ap.add_argument("--tag", default="main")
    ap.add_argument("--configs", default=None, help="comma list of design:encoding:codeclabel")
    ap.add_argument("--reps-write", type=int, default=2)
    ap.add_argument("--reps-read", type=int, default=3)
    ap.add_argument("--drop-files", action="store_true")
    args = ap.parse_args()

    C.RESULTS.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    channels = C.build_channels(args.frames)
    meta = {b"freemocap.recording": C.descriptor_json(channels)}
    print(f"built {len(channels)} channels in {time.perf_counter() - t0:.1f}s", flush=True)
    if args.tag == "main":
        (C.RESULTS / "precision.json").write_text(json.dumps(precision_stats(channels), indent=1))
        rows_per_kind = {}
        for c in channels:
            rows_per_kind[c["kind"]] = rows_per_kind.get(c["kind"], 0) + int(c["values"].size)
        (C.RESULTS / "source_summary.json").write_text(json.dumps(dict(
            frames=int(channels[0]["values"].shape[0]), channels=len(channels), rows=sum(rows_per_kind.values()),
            rows_per_kind=rows_per_kind, null_fraction=float(sum(np.isnan(c["values"]).sum() for c in channels) / sum(rows_per_kind.values())),
            pyarrow=pa.__version__, numpy=np.__version__), indent=1))

    wanted = None
    if args.configs:
        wanted = {tuple(x.split(":")) for x in args.configs.split(",")}
    out_rows = []
    for design, parts in C.DESIGNS.items():
        if wanted and not any(w[0] == design for w in wanted):
            continue
        part_batches = {p: list(C.design_batches(p, channels)) for p in parts}
        schemas = {p: C.schema_for(p).with_metadata(meta) for p in parts}
        expected = {p: pa.Table.from_batches(part_batches[p], schema=schemas[p]).replace_schema_metadata(None) for p in parts}
        if not args.drop_files:
            (C.SCR / "expected").mkdir(parents=True, exist_ok=True)
            for p in parts:
                with pa.ipc.new_file(C.SCR / "expected" / f"{p}.arrow", expected[p].schema) as w:
                    w.write_table(expected[p])
        for enc in C.ENCODINGS:
            for codec, level in C.CODECS:
                lab = C.codec_label(codec, level)
                if wanted and (design, enc, lab) not in wanted:
                    continue
                paths = C.file_paths(design, enc, codec, level)
                paths[0].parent.mkdir(parents=True, exist_ok=True)
                write_s = timed(lambda: [C.write_parquet(path, schemas[p], part_batches[p], enc, codec, level) for p, path in zip(parts, paths)], args.reps_write)
                full_s = timed(lambda: [pq.read_table(path) for path in paths], args.reps_read)
                val_s = timed(lambda: [pq.read_table(path, columns=C.value_cols(schemas[p])) for p, path in zip(parts, paths)], args.reps_read)
                bad = []
                for p, path in zip(parts, paths):
                    bad += [f"{p}.{b}" for b in C.tables_equal(pq.read_table(path).replace_schema_metadata(None), expected[p])]
                sizes, encs, codecs, rgs = {}, {}, set(), 0
                for path in paths:
                    s, e, cd, n = column_bytes(path)
                    for k, v in s.items():
                        sizes[k] = sizes.get(k, 0) + v
                    for k, v in e.items():
                        encs[k] = sorted(set(encs.get(k, [])) | set(v))
                    codecs |= set(cd)
                    rgs += n
                vb = sum(v for k, v in sizes.items() if k.startswith("value"))
                row = dict(design=design, encoding=enc, codec=lab, file_bytes=sum(p.stat().st_size for p in paths),
                           value_bytes=vb, timestamp_bytes=sizes["timestamp_s"],
                           other_bytes=sum(sizes.values()) - vb - sizes["timestamp_s"],
                           write_s=min(write_s), read_full_s=statistics.median(full_s), read_value_s=statistics.median(val_s),
                           roundtrip_bit_exact=not bad, mismatched=";".join(bad), codec_in_file="/".join(codecs),
                           value_encodings="/".join(encs.get("value", [])), timestamp_encodings="/".join(encs["timestamp_s"]),
                           row_groups=rgs, rows=sum(expected[p].num_rows for p in parts))
                out_rows.append(row)
                print(json.dumps(row), flush=True)
                if args.drop_files:
                    for path in paths:
                        path.unlink()
        del part_batches, expected
        gc.collect()
    with (C.RESULTS / f"matrix_{args.tag}.csv").open("w", newline="") as handle:
        w = csv.DictWriter(handle, fieldnames=list(out_rows[0]))
        w.writeheader()
        w.writerows(out_rows)
    print(f"done in {time.perf_counter() - t0:.0f}s")


if __name__ == "__main__":
    main()
