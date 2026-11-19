"""T-REC-STALL, T-REC-KILL, T-REC-FSYNC and T-REC-GIL: the measurements of R11 (specs/recorder.md,
sections 11 and 12.1).

Each runs on synthetic JPEG frames with no camera. The benchmarks have the marker `recorder_bench`
and run only with `SKELLYCAM_BENCH=1`, on the machines of the user. Each writes a JSON summary into
the folder in `SKELLYCAM_BENCH_OUT`, outside the repository. The pass parts of T-REC-STALL and
T-REC-KILL also run in CI in a short form: 5 kills, and the stalls of 0.5 s and 15 s with the queue,
the stall limit and the stalls scaled down by 10 (ADR-QEQ8). Without `SKELLYCAM_BENCH=1`,
T-REC-KILL runs its short form.
"""

import json
import platform
import random
import sys
import time
from importlib import metadata
from pathlib import Path

import pytest

from skellycam.tests.take_recorder import ebml, jpeg_tools, sidecar_check
from skellycam.tests.take_recorder.children import REPO_ROOT, ChildError
from skellycam.tests.take_recorder.rec_api import BENCH, BENCH_OUT, Run, camera_label, rec, take_camera, warnings_of

MARGIN_S = 5.0


def write_summary(name, summary):
    """Write a benchmark summary to `SKELLYCAM_BENCH_OUT/<name>.json`, outside the repository."""
    if not BENCH_OUT:
        pytest.fail("SKELLYCAM_BENCH_OUT must name a folder outside the repository (spec section 11)")
    out = Path(BENCH_OUT).resolve()
    assert not out.is_relative_to(REPO_ROOT.resolve()), "the benchmark output must be outside the repository"
    out.mkdir(parents=True, exist_ok=True)
    summary = {"tool_versions": {"python": platform.python_version(), "av": metadata.version("av"),
                                 "opencv-contrib-python": metadata.version("opencv-contrib-python")},
               "platform": sys.platform, **summary}
    (out / f"{name}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def paced_take(tmp_path, runs, children, *, groups, seconds, stall=None, writer_on=True, fsync_on=True,
               queue_seconds=3.0, stall_limit_s=10.0, name="take"):
    """One run of section 11. `groups` is a list of (camera processes, width, height, rate); each group
    is one take, and all camera processes of all groups run at the same time. Each process has a source
    thread, a loop thread and (with `writer_on`) a writer thread. `stall` is (camera index, frame,
    seconds). The test is the main process of 8.1: when a camera reports `RecorderStalled`, it stops
    the others and ends each take for all its cameras."""
    procs, takes = [], []  # procs: (child, run or None, camera_id)
    index = 0
    for group, (cameras, width, height, rate) in enumerate(groups):
        ids = [f"{0xa000 + index + i:04x}" for i in range(cameras)]
        run = None
        folder = tmp_path / f"{name}_{group}"
        folder.mkdir(parents=True, exist_ok=True)
        if writer_on:
            cams = [take_camera(c, rate=rate, width=width, height=height, os_index=i) for i, c in enumerate(ids)]
            run = Run(folder / "take", cams, start_writers=False, queue_seconds=queue_seconds, stall_limit_s=stall_limit_s,
                      frames=lambda k, w=width, h=height: jpeg_tools.synthetic_jpeg(k, w, h))
            runs.append(run)
            takes.append((run, ids))
        for camera_id in ids:
            config = {"mode": "paced", "spec": run.take.camera_spec(camera_id) if run else None, "width": width,
                      "height": height, "rate": rate, "seconds": seconds, "writer_on": writer_on, "fsync_on": fsync_on,
                      "root": str(run.folder if run else folder), "rules": [], "quality": 90}
            if stall and stall[0] == index:
                config["stall"] = {"at_frame": stall[1], "seconds": stall[2]}
            procs.append((children(config), run, camera_id))
            index += 1
    for child, _, _ in procs:
        child.expect("started", timeout=120.0)
    done, stalled = {}, None
    deadline = time.monotonic() + seconds + 120.0
    while len(done) < len(procs) and time.monotonic() < deadline:
        for i, (child, _, _) in enumerate(procs):
            if i in done:
                continue
            try:
                event = child.next_event(timeout=0.05)
            except ChildError:
                continue
            if event["event"] == "stalled" and stalled is None:
                stalled = i
                for other, _, _ in procs:
                    if other is not child:
                        other.send("stop")
            elif event["event"] == "done":
                done[i] = event
    assert len(done) == len(procs), "each camera process ends its run"
    frame_counts = {}
    for i, (_, run, _) in enumerate(procs):
        frame_counts[id(run)] = max(frame_counts.get(id(run), 0), done[i]["given"])
    told = time.monotonic()
    if writer_on:
        for child, run, _ in procs:
            child.send("end", frame_count=frame_counts[id(run)])
    summaries, results = [], {}
    for child, _, camera_id in procs:
        try:
            summary = child.expect("summary", timeout=max(0.1, told + stall_limit_s + MARGIN_S - time.monotonic()))
        except ChildError:
            child.terminate_and_join()
            summary = None
        summaries.append(summary)
        result = summary and summary["result"]
        results[camera_id] = rec().CameraTakeResult(**result) if result else None
    all_ids = [camera_id for _, _, camera_id in procs]
    manifests = []
    for run, ids in takes:
        error = f"disk stall on camera {all_ids[stalled]}" if stalled is not None else None
        dead = {c: "disk stall" for c in ids if results[c] is None or results[c].error == "disk stall"}
        extra = {"dead_cameras": dead} if dead else {}
        run.take.finish([results[c] for c in ids], frame_count=frame_counts[id(run)], ended_by_error=error, **extra)
        manifests.append(run.manifest())
    first = takes[0][0] if takes else None
    return {"run": first, "ids": all_ids, "summaries": summaries, "results": results, "stalled": stalled,
            "frame_count": frame_counts[id(first)] if first else None, "manifest": manifests[0] if manifests else None}


def stall_pass_parts(out, stall_s, queue_s, limit_s):
    """The pass parts of T-REC-STALL (section 11)."""
    run, ids, frame_count = out["run"], out["ids"], out["frame_count"]
    rows = {c: sidecar_check.read(run.csv(c)) for c in ids}
    for i, camera_id in enumerate(ids):
        sidecar, summary = rows[camera_id], out["summaries"][i]
        assert summary is not None, f"camera {camera_id} gave no result in time"
        real = sum(1 for r in sidecar.rows if not r.missing)
        assert real == summary["given"], "no lost frame: each frame given is in the CSV"
        assert len(sidecar.rows) == frame_count, "equal rows"
        assert sidecar.footer_words() == ["end"], "each file is finished"
    waits = [s["result"]["give_wait_count"] for s in out["summaries"]]
    if stall_s < queue_s:
        assert waits == [0] * len(ids), "no give wait"
        assert out["stalled"] is None
    elif stall_s < queue_s + limit_s:
        assert out["stalled"] is None and max(waits) >= 1
        longest = max(s["result"]["give_wait_ms_max"] for s in out["summaries"]) / 1000
        assert longest == pytest.approx(stall_s - queue_s, abs=0.15 * stall_s + 0.2), "give waits about stall - queue"
    else:
        assert out["stalled"] is not None
        details = [w["detail"] for w in warnings_of(out["manifest"], "take_error")]
        assert details == [f"disk stall on camera {ids[out['stalled']]}"]


@pytest.mark.recorder_slow
@pytest.mark.parametrize("stall_s", [0.05, 1.5], ids=["0.5_s_scaled", "15_s_scaled"])
def test_t_rec_stall_short_pass_parts(tmp_path, runs, children, stall_s):
    """T-REC-STALL, the short CI form (12.1): two camera processes at 720p30 for 6 s; the MKV file
    object of camera 0 blocks one time at frame 30; the queue (0.3 s), the stall limit (1.0 s) and the
    stalls (0.05 s and 1.5 s) are scaled down by 10. 0.05 s: no `give` wait and no lost frame. 1.5 s:
    the take ends with `take_error` "disk stall"; each file is finished; equal rows."""
    out = paced_take(tmp_path, runs, children, groups=[(2, 1280, 720, (30, 1))], seconds=6.0,
                     stall=(0, 30, stall_s), queue_seconds=0.3, stall_limit_s=1.0)
    stall_pass_parts(out, stall_s, 0.3, 1.0)


@pytest.mark.recorder_bench
@pytest.mark.parametrize("stall_s", [0.5, 2.0, 10.0, 15.0])
@pytest.mark.parametrize(("width", "height", "rate"), [(1280, 720, (30, 1)), (1920, 1080, (60, 1))], ids=["720p30", "1080p60"])
@pytest.mark.parametrize("cameras", [1, 4])
def test_t_rec_stall_benchmark(tmp_path, runs, children, cameras, width, height, rate, stall_s):
    """T-REC-STALL (section 11, R11): 1 and 4 camera processes, 720p30 and 1080p60; the MKV file
    object of one writer blocks one time for 0.5, 2, 10 and 15 s at frame 300; each run is 60 s. It
    records the queue high-water, the `give` waits, the frames replaced in the source, the rows of
    each camera and the capture lateness of the other camera processes. Pass parts: 0.5 s and 2 s, no
    `give` wait and no lost frame; 10 s, the queue fills, `give` waits about 7 s, no lost frame, equal
    rows; 15 s, the take ends with `take_error` "disk stall", each file is finished, equal rows."""
    out = paced_take(tmp_path, runs, children, groups=[(cameras, width, height, rate)], seconds=60.0,
                     stall=(0, 300, stall_s))
    summary = {"cameras": cameras, "size": f"{width}x{height}", "rate": f"{rate[0]}/{rate[1]}", "stall_s": stall_s,
               "frame_count": out["frame_count"], "stalled": out["stalled"],
               "per_camera": [{"camera_id": c, "queue_high_water_items": s and s["result"]["queue_high_water"],
                               "queue_high_water_s": s and s["result"]["queue_high_water"] * rate[1] / rate[0],
                               "give_wait_count": s and s["result"]["give_wait_count"],
                               "give_wait_ms_max": s and s["result"]["give_wait_ms_max"], "replaced": s and s["replaced"],
                               "rows": s and s["result"]["rows"], "lateness_ns": s and s["lateness_ns"]}
                              for c, s in zip(out["ids"], out["summaries"])]}
    write_summary(f"t_rec_stall_{cameras}cam_{width}x{height}_{stall_s}s", summary)
    stall_pass_parts(out, stall_s, 3.0, 10.0)


def check_killed_pair(mkv_path, csv_path, payload_of):
    """The pass parts of T-REC-KILL on the files of a killed camera process: each row has a correct
    CRC and its block bytes equal the frame given or a placeholder; blocks - rows is 0 or 1; each
    complete block parses. Returns (rows, blocks, torn_bytes)."""
    data = mkv_path.read_bytes()
    mkv = ebml.walk(data)
    sidecar = sidecar_check.read(csv_path)
    assert sidecar.bad_row is None, sidecar.bad_row
    assert all(c.crc_ok is not False for c in mkv.clusters if c.complete)
    for row in sidecar.rows:
        payload = data[row.byte_offset:row.byte_offset + row.byte_size]
        if row.missing:
            assert int(jpeg_tools.decode_pyav(payload)[1].max()) == 0
        else:
            assert payload == payload_of(row.frame), f"row {row.frame}"
    assert len(mkv.blocks) - len(sidecar.rows) in (0, 1), (len(mkv.blocks), len(sidecar.rows))
    for row, block in zip(sidecar.rows, mkv.blocks):
        assert (row.byte_offset, row.byte_size) == (block.payload_offset, block.payload_size)
    return len(sidecar.rows), len(mkv.blocks), sidecar.torn_bytes


def kill_once(tmp_path, children, index, *, full_queue, missing_every, width, height, rng):
    run = Run(tmp_path / f"kill_{index}", [take_camera("0a1b", width=width, height=height)], start_writers=False,
              frames=lambda k: jpeg_tools.synthetic_jpeg(k, width, height))
    child = children({"mode": "writer", "spec": run.take.camera_spec("0a1b"), "width": width, "height": height,
                      "layout": "422", "root": str(run.folder), "rules": []})
    child.expect("started", timeout=120.0)
    queue = run.take.camera_spec("0a1b").queue_size
    if full_queue:
        child.send("give", k_from=0, k_to=10, missing_every=missing_every)
        for _ in range(10):
            child.expect("gave")
        child.send("arm", rule={"kind": ".mkv", "action": "hold", "match": camera_label("0a1b")})
        child.expect("armed")
        target = 10 + queue + rng.randrange(0, 3)
        child.send("give", k_from=10, k_to=target + 10, missing_every=missing_every)
    else:
        target = rng.randrange(5, 120)
        child.send("give", k_from=0, k_to=target + 50, missing_every=missing_every)
    given = 0
    deadline = time.monotonic() + 30
    while given < target and time.monotonic() < deadline:
        try:
            event = child.next_event(timeout=0.5)
        except ChildError:
            break  # a full queue: give waits, so no event comes
        if event["event"] == "gave":
            given = event["k"] + 1
    child.kill()
    payload_of = run.frames
    rows, blocks, torn = check_killed_pair(run.mkv("0a1b"), run.csv("0a1b"), payload_of)
    return {"given": given, "rows": rows, "blocks": blocks, "lost": given - rows, "torn_bytes": torn,
            "queue_size": queue, "full_queue": full_queue}


@pytest.mark.recorder_slow
def test_t_rec_kill(tmp_path, children):
    """T-REC-KILL (section 11): one camera process at 720p30, and a 640x480 case where every second
    item is a placeholder. Kills during normal writing and with a full queue (a blocked writer), at
    random frames; `TerminateProcess` on Windows, `SIGKILL` elsewhere. Pass parts: each row has a
    correct CRC and its block bytes equal the frame given or the placeholder; blocks - rows is 0 or 1;
    each complete block parses. Short form (CI): 5 kills during normal writing. With
    `SKELLYCAM_BENCH=1`: 20 + 20 kills for each case, and a JSON summary."""
    rng = random.Random(20261120)
    plans = ([(False, 0, 1280, 720)] * 5 if not BENCH else
             [(fq, me, w, h) for (me, w, h) in ((0, 1280, 720), (2, 640, 480)) for fq in (False, True) for _ in range(20)])
    records = []
    for index, (full_queue, missing_every, width, height) in enumerate(plans):
        record = kill_once(tmp_path, children, index, full_queue=full_queue, missing_every=missing_every,
                           width=width, height=height, rng=rng)
        record["case"] = f"{width}x{height}" + (" placeholders" if missing_every else "")
        records.append(record)
    if BENCH:
        write_summary("t_rec_kill", {"kills": records})


def bench_record(out):
    keys = ("lateness_ns", "interval_jitter_ns", "loop_step_ns", "write_ns", "row_write_ns", "fsync_ns", "cpu_s",
            "replaced", "result")
    return [s and {"camera_id": c, **{k: s[k] for k in keys}} for c, s in zip(out["ids"], out["summaries"])]


@pytest.mark.recorder_bench
@pytest.mark.parametrize(("fsync_on", "seconds", "repeat"), [(True, 60.0, 3), (False, 60.0, 3), (True, 600.0, 1)],
                         ids=["on_3x60s", "off_3x60s", "on_10min"])
def test_t_rec_fsync(tmp_path, runs, children, fsync_on, seconds, repeat):
    """T-REC-FSYNC (section 11, R11): 16 camera processes at 1080p60, fsync once a second on and off,
    3 runs of 60 s, and one run of 10 min with fsync on. It records the per-frame write time, the
    fsync time, the queue high-water, the capture lateness and the CPU of each process. No pass
    value."""
    runs_out = [bench_record(paced_take(tmp_path, runs, children, groups=[(16, 1920, 1080, (60, 1))], seconds=seconds,
                                        fsync_on=fsync_on, name=f"fsync_{i}")) for i in range(repeat)]
    write_summary(f"t_rec_fsync_{'on' if fsync_on else 'off'}_{int(seconds)}s", {"fsync_on": fsync_on, "runs": runs_out})


@pytest.mark.recorder_bench
@pytest.mark.parametrize("writer_on", [True, False], ids=["writer_on", "writer_off"])
def test_t_rec_gil(tmp_path, runs, children, writer_on):
    """T-REC-GIL (section 11, R11): 4 camera processes at 720p30 and 1 at 720p60, 10 min, writer on and
    off. In each process: the source thread, the loop thread and the writer thread. It records the
    arrival lateness against the schedule, the interval jitter and the loop step time. No pass value.
    The 30 and 60 fps processes run together here, because they have no gate (section 11)."""
    out = paced_take(tmp_path, runs, children, groups=[(4, 1280, 720, (30, 1)), (1, 1280, 720, (60, 1))],
                     seconds=600.0, writer_on=writer_on, name="gil")
    write_summary(f"t_rec_gil_{'on' if writer_on else 'off'}", {"writer_on": writer_on, "cameras": bench_record(out)})
