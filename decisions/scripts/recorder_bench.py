"""The measurements of R11 for ADR-8RES (specs/recorder.md, section 11).

Usage (from the repository root, with the output folder outside the repository)::

    uv run python decisions/scripts/recorder_bench.py fsync-matrix OUT WORK
    uv run python decisions/scripts/recorder_bench.py table OUT

`fsync-matrix` runs the fsync cost with 1, 4, 8 and 16 writers at 1080p30 and 1080p60, fsync on and
off, 60 s each, through `paced_take` of the T-REC tests (one camera process for each writer, with
its source, loop and writer thread). It writes `fsync_matrix_<n>cam_<fps>_<on|off>.json` to OUT and
deletes the media in WORK after each run. `table` prints the Markdown tables of the JSON summaries
in OUT: the files of `SKELLYCAM_BENCH=1` and of `fsync-matrix`.
"""

import json
import shutil
import statistics
import sys
from pathlib import Path

MS = 1e6


def fsync_matrix(out, work):
    from skellycam.tests.take_recorder.children import Child
    from skellycam.tests.take_recorder.test_benchmarks import bench_record, paced_take

    out, work = Path(out), Path(work)
    out.mkdir(parents=True, exist_ok=True)
    for cameras in (1, 4, 8, 16):
        for fps in (30, 60):
            for fsync_on in (True, False):
                folder = work / f"{cameras}_{fps}_{fsync_on}"
                runs, children = [], []

                def start(config, folder=folder, children=children):
                    children.append(Child(config, folder / "children"))
                    return children[-1]

                try:
                    record = bench_record(paced_take(folder, runs, start, groups=[(cameras, 1920, 1080, (fps, 1))],
                                                     seconds=60.0, fsync_on=fsync_on))
                finally:
                    for run in runs:
                        run.close()
                    for child in children:
                        child.close()
                    shutil.rmtree(folder, ignore_errors=True)
                name = f"fsync_matrix_{cameras}cam_{fps}_{'on' if fsync_on else 'off'}"
                (out / f"{name}.json").write_text(json.dumps({"cameras": cameras, "fps": fps, "fsync_on": fsync_on,
                                                              "runs": [record]}, indent=2), encoding="utf-8")
                print(name, "done", flush=True)


def ms(value):
    return "-" if value is None else f"{value / MS:.2f}"


def worst(cameras, key, stat):
    values = [c[key][stat] for c in cameras if c and c[key][stat] is not None]
    return max(values) if values else None


def median_of(cameras, key, stat):
    values = [c[key][stat] for c in cameras if c and c[key][stat] is not None]
    return statistics.median(values) if values else None


def write_rows(name, data):
    """One row of the fsync and GIL tables: the median over the camera processes of each p50, and the
    largest p99 and max."""
    rows = []
    for index, cameras in enumerate(data["runs"]):
        high = max(c["result"]["queue_high_water"] for c in cameras if c and c["result"])
        cpu = statistics.fmean(c["cpu_s"] for c in cameras if c)
        rows.append(f"| {name} #{index + 1} | {ms(median_of(cameras, 'write_ns', 'p50'))} / "
                    f"{ms(worst(cameras, 'write_ns', 'p99'))} / {ms(worst(cameras, 'write_ns', 'p999'))} / "
                    f"{ms(worst(cameras, 'write_ns', 'max'))} | {ms(median_of(cameras, 'fsync_ns', 'p50'))} / "
                    f"{ms(worst(cameras, 'fsync_ns', 'max'))} | {high} | {ms(median_of(cameras, 'lateness_ns', 'p50'))} / "
                    f"{ms(worst(cameras, 'lateness_ns', 'p99'))} / {ms(worst(cameras, 'lateness_ns', 'max'))} | "
                    f"{cpu:.1f} |")
    return rows


def table(out):
    files = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(out).glob("*.json"))}
    print("## T-REC-STALL\n")
    print("| cameras | mode | stall s | stalled | frame count | high-water items (s) | give waits | longest wait ms "
          "| replaced | lateness of the other cameras p50 / p99 / max ms |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for name, data in files.items():
        if not name.startswith("t_rec_stall_"):
            continue
        cams = data["per_camera"]
        first, others = cams[0], [c for c in cams[1:] if c["lateness_ns"]]
        late = " / ".join(ms(max(c["lateness_ns"][s] for c in others)) for s in ("p50", "p99", "max")) if others else "-"
        print(f"| {data['cameras']} | {data['size']} {data['rate']} | {data['stall_s']} | {data['stalled']} | "
              f"{data['frame_count']} | {first['queue_high_water_items']} ({first['queue_high_water_s']:.2f}) | "
              f"{first['give_wait_count']} | {first['give_wait_ms_max']:.0f} | {first['replaced']} | {late} |")
    if "t_rec_kill" in files:
        print("\n## T-REC-KILL\n")
        print("| case | queue | kills | lost frames min / median / max | blocks - rows | torn CSV bytes max |")
        print("|---|---|---|---|---|---|")
        groups = {}
        for kill in files["t_rec_kill"]["kills"]:
            groups.setdefault((kill["case"], kill["full_queue"]), []).append(kill)
        for (case, full), kills in groups.items():
            lost = [k["lost"] for k in kills]
            extra = sorted({k["blocks"] - k["rows"] for k in kills})
            print(f"| {case}, {'full queue' if full else 'normal writing'} | {kills[0]['queue_size']} | {len(kills)} | "
                  f"{min(lost)} / {statistics.median(lost):g} / {max(lost)} | {extra} | "
                  f"{max(k['torn_bytes'] for k in kills)} |")
    print("\n## T-REC-FSYNC\n")
    print("| run | MKV write p50 / p99 / p99.9 / max ms | fsync p50 / max ms | high-water items | "
          "lateness p50 / p99 / max ms | CPU s per process |")
    print("|---|---|---|---|---|---|")
    for name, data in files.items():
        if name.startswith(("t_rec_fsync_", "fsync_matrix_")):
            label = name.removeprefix("t_rec_fsync_").removeprefix("fsync_matrix_")
            print("\n".join(write_rows(label, data)))
    print("\n## T-REC-GIL\n")
    print("| writer | rate | lateness p50 / p99 / max ms | interval jitter p50 / p99 / max ms | "
          "loop step p50 / p99 / max ms |")
    print("|---|---|---|---|---|")
    for name, data in files.items():
        if not name.startswith("t_rec_gil_"):
            continue
        for label, cams in (("30 fps (4)", data["cameras"][:4]), ("60 fps (1)", data["cameras"][4:])):
            cells = [" / ".join(ms(f(cams, key, s)) for f, s in ((median_of, "p50"), (worst, "p99"), (worst, "max")))
                     for key in ("lateness_ns", "interval_jitter_ns", "loop_step_ns")]
            print(f"| {'on' if data['writer_on'] else 'off'} | {label} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    {"fsync-matrix": fsync_matrix, "table": table}[sys.argv[1]](*sys.argv[2:])
