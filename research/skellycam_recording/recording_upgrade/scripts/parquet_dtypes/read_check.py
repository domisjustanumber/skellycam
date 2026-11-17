# /// script
# requires-python = "==3.12.*"
# dependencies = ["pyarrow==26.0.0", "numpy==2.4.6", "pandas==2.3.3", "polars==2.0.0", "duckdb==2.0.0",
#                 "fastparquet==2026.9.0", "cramjam==2.14.0"]
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""Read every test file with each Python reader and compare every column with the expected Arrow IPC, bit for bit.

  uv run --script read_check.py --readers pyarrow,polars,duckdb,pandas,fastparquet --tag pa26
  uv run --script read_check.py --hyparquet <hyparquet_check.mjs output json> --tag hyparquet

Writes results/parquet_dtypes/readers_<tag>.csv. Floats: null masks and raw bits must match (NaN in pandas-style
readers counts as null because the source has no NaN); value dtype must be the file's dtype.
"""
import argparse
import csv
import hashlib
import json
import time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

import pq_common as C


def read_pyarrow(path):
    return pq.read_table(path)


def read_polars(path):
    import polars as pl
    return pl.read_parquet(path).to_arrow()


def read_duckdb(path):
    import duckdb
    con = duckdb.connect()
    rel = con.execute("select * from read_parquet(?)", [str(path)])
    for name in ("to_arrow_table", "fetch_arrow_table", "arrow"):
        if hasattr(rel, name):
            out = getattr(rel, name)()
            return out.read_all() if isinstance(out, pa.RecordBatchReader) else out
    raise RuntimeError("no arrow export on duckdb result")


def _from_pandas(df):
    df = df.reset_index(drop=True)
    for col in df.columns:
        if str(df[col].dtype) == "category":
            df[col] = df[col].astype(object)
    return pa.Table.from_pandas(df, preserve_index=False)


def read_pandas(path):
    import pandas as pd
    return _from_pandas(pd.read_parquet(path, engine="pyarrow"))


def read_fastparquet(path):
    import fastparquet
    return _from_pandas(fastparquet.ParquetFile(str(path)).to_pandas())


READERS = dict(pyarrow=read_pyarrow, polars=read_polars, duckdb=read_duckdb, pandas=read_pandas, fastparquet=read_fastparquet)


def versions():
    out = dict(pyarrow=pa.__version__, numpy=np.__version__)
    for mod in ("pandas", "polars", "duckdb", "fastparquet", "cramjam"):
        try:
            out[mod] = __import__(mod).__version__
        except Exception:
            pass
    return out


def all_files():
    return sorted((C.SCR / "files").glob("*/*.parquet"))


def expected_for(path, cache={}):
    part = path.name.split("__")[0]
    if part not in cache:
        cache.clear()  # keep one design in memory
        with pa.memory_map(str(C.SCR / "expected" / f"{part}.arrow")) as src:
            cache[part] = pa.ipc.open_file(src).read_all()
    return cache[part]


def py_readers(names, tag):
    rows = []
    for path in all_files():
        exp = expected_for(path)
        design, enc, codec = path.parent.name, *path.stem.split("__")[1:]
        for reader in names:
            row = dict(reader=reader, design=design, part=path.name.split("__")[0], encoding=enc, codec=codec)
            try:
                t = time.perf_counter()
                table = READERS[reader](path)
                row["read_s"] = round(time.perf_counter() - t, 4)
                table = table.replace_schema_metadata(None)
                row["value_types"] = "/".join(str(table.schema.field(n).type) for n in C.value_cols(exp.schema) if n in table.column_names)
                bad = C.tables_equal(table, exp)
                row["ok"] = not bad
                row["mismatched"] = ";".join(bad)
                del table
            except Exception as error:
                row["ok"] = False
                row["error"] = f"{type(error).__name__}: {str(error)[:300]}"
            rows.append(row)
            print(json.dumps(row), flush=True)
    return rows


def expected_hashes(exp):
    out = {}
    for name in exp.column_names:
        col = exp.column(name).combine_chunks()
        if pa.types.is_floating(col.type):
            mask = col.is_null().to_numpy(zero_copy_only=False)
            data = col.fill_null(0).to_numpy(zero_copy_only=False).astype(np.float64)
            out[name] = dict(values=hashlib.sha256(data.tobytes()).hexdigest(), nulls=hashlib.sha256(mask.astype(np.uint8).tobytes()).hexdigest())
        else:
            text = "\x1f".join("\x00" if v is None else str(v) for v in col.to_pylist())
            out[name] = dict(values=hashlib.sha256(text.encode("utf-8")).hexdigest())
    return out


def hyparquet_rows(result_path):
    data = json.loads(open(result_path).read())
    rows, cache = [], {}
    for path_s, rec in data["files"].items():
        path = C.SCR.__class__(path_s)
        part = path.name.split("__")[0]
        if part not in cache:
            cache[part] = expected_hashes(expected_for(path))
        exp = cache[part]
        row = dict(reader="hyparquet", design=path.parent.name, part=part, encoding=path.stem.split("__")[1], codec=path.stem.split("__")[2])
        if "error" in rec:
            row.update(ok=False, error=rec["error"][:300])
        else:
            bad = [n for n, h in exp.items() if rec["columns"].get(n, {}).get("values") != h["values"]
                   or ("nulls" in h and rec["columns"][n].get("nulls") != h["nulls"])]
            row.update(ok=not bad, mismatched=";".join(bad), read_s=round(rec["decode_ms"] / 1000, 4),
                       value_types="/".join(rec["columns"][n]["type"] for n in rec["columns"] if n.startswith("value")),
                       file_codecs="/".join(rec["codecs"]), file_value_encodings="/".join(rec["value_encodings"]))
        rows.append(row)
    return rows, dict(node=data["node"], **data["versions"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--readers", default="pyarrow,polars,duckdb,pandas,fastparquet")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--hyparquet", default=None)
    args = ap.parse_args()
    if args.hyparquet:
        rows, vers = hyparquet_rows(args.hyparquet)
    else:
        vers = versions()
        rows = py_readers(args.readers.split(","), args.tag)
    fields = sorted({k for r in rows for k in r}, key=lambda k: ["reader", "design", "part", "encoding", "codec", "ok"].index(k) if k in ["reader", "design", "part", "encoding", "codec", "ok"] else 99)
    with (C.RESULTS / f"readers_{args.tag}.csv").open("w", newline="") as handle:
        w = csv.DictWriter(handle, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    (C.RESULTS / f"readers_{args.tag}_versions.json").write_text(json.dumps(vers, indent=1))
    fails = [r for r in rows if not r["ok"]]
    print(f"{len(rows)} reads, {len(fails)} failures; versions {vers}")


if __name__ == "__main__":
    main()
