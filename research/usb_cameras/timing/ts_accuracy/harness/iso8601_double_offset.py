"""Reproduce the local ISO 8601 double-offset in skellycam timebase_mapping.py.
Usage: uv run --with numpy --with tzdata python -I iso8601_double_offset.py <path to skellycam repo root>
Loads timebase_mapping.py by file path with two stub modules, so no skellycam package import runs.
"""
import importlib.util, sys, types, time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np

root = Path(sys.argv[1])
zone = ZoneInfo(sys.argv[2] if len(sys.argv) > 2 else "America/New_York")

dt_mod = types.ModuleType("skellycam.core.types.numpy_record_dtypes")
dt_mod.TIMEBASE_MAPPING_DTYPE = np.dtype([('utc_time_ns', np.int64), ('perf_counter_ns', np.int64), ('local_time_utc_offset', np.int32)], align=True)
tu_mod = types.ModuleType("skellycam.utilities.time_unit_conversion")
tu_mod.LOCAL_TIMEZONE = zone
tz_mod = types.ModuleType("tzlocal"); tz_mod.get_localzone = lambda: zone
for name, mod in [("skellycam.core.types.numpy_record_dtypes", dt_mod), ("skellycam.utilities.time_unit_conversion", tu_mod), ("tzlocal", tz_mod)]:
    sys.modules[name] = mod
spec = importlib.util.spec_from_file_location("tbm", root / "skellycam/core/timestamps/timebase_mapping.py")
tbm = importlib.util.module_from_spec(spec); spec.loader.exec_module(tbm)

true_utc = datetime(2026, 11, 9, 11, 6, 0, tzinfo=timezone.utc)
m = tbm.TimebaseMapping(utc_time_ns=int(true_utc.timestamp() * 1e9), perf_counter_ns=1_000_000_000)
print("zone:", zone, "offset_s:", m.local_time_utc_offset)
print("true local time        :", true_utc.astimezone(zone).isoformat())
print("per-camera CSV (code)  :", m.convert_perf_counter_ns_to_local_iso8601(1_000_000_000))
utc_s = m.convert_perf_counter_ns_to_unix_ns(1_000_000_000, local_time=False) / 1e9
print("multiframe CSV (code)  :", datetime.fromtimestamp(utc_s, tz=timezone.utc).astimezone(zone).isoformat())
