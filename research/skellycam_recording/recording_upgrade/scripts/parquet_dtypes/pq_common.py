"""Shared test-data builder and writer for the parquet_dtypes study (no uv metadata: imported by the scripts).

Data: real freemocap sample data (freemocap_sample_data_h264, 1108 frames) laid out as freemocap's canonical
tidy-long `<rec>_data.parquet` (arrow_schema.py:15-29 on upstream/development-streaming c27fc299), batched like
ChannelSeries.batches (channel_series.py:38-77): one channel at a time, whole frames, <=65536 rows per batch,
one write_batch per batch, as publish_parquet does (parquet_writer.py:80).
"""
import csv
import json
import math
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

SCR = Path(r"C:\Users\Dom\AppData\Local\Temp\claude\ca7e9b09df19a3f5\ef960e37-035d-4929-84c6-9e035d622496\scratchpad\parquet_dtypes")
SAMPLE = Path(r"C:\Users\Dom\Downloads\freemocap_sample_data_h264")
RESULTS = Path(__file__).resolve().parents[2] / "results" / "parquet_dtypes"
FPS = 30.0
BATCH = 65536
GROUP = "mocap"
WORLD = "recording_world"

STR = pa.string()
BASE_FIELDS = [
    pa.field("timestamp_s", pa.float64(), nullable=False),
    pa.field("sensor_group", STR, nullable=False),
    pa.field("frame_number", pa.int64(), nullable=False),
    pa.field("source", STR, nullable=False),
    pa.field("reference_frame", STR),
    pa.field("channel", STR, nullable=False),
    pa.field("name", STR, nullable=False),
    pa.field("component", STR, nullable=False),
    pa.field("value", pa.float64()),
    pa.field("units", STR, nullable=False),
    pa.field("run_id", pa.int64(), nullable=False),
]


def schema_for(design: str) -> pa.Schema:
    fields = list(BASE_FIELDS)
    if design in ("C", "D_main", "A"):
        fields[8] = pa.field("value", pa.float32())
    if design == "A":
        fields.insert(9, pa.field("value_f64", pa.float64()))
    return pa.schema(fields)


# design -> files it produces (D is two files)
DESIGNS = {"f64": ["f64"], "f64w": ["f64w"], "A": ["A"], "C": ["C"], "D": ["D_main", "D_timing"]}
ENCODINGS = ["dict", "plain", "bss"]
CODECS = [("zstd", None), ("zstd", 1), ("zstd", 3), ("zstd", 9), ("zstd", 19), ("snappy", None), ("lz4", None),
          ("gzip", None), ("brotli", None), ("none", None)]


def codec_label(codec, level):
    return codec if level is None else f"{codec}{level}"


def is_time(ch) -> bool:
    return set(ch["components"].values()) == {"s"}


# ---------------------------------------------------------------- source data

def _names_from_csv(path: Path) -> list[str]:
    with path.open(newline="") as handle:
        return [row["keypoint"] for row in csv.DictReader(handle) if row["frame"] == "0"]


def _rodrigues(rvec):
    rvec = np.asarray(rvec, float)
    theta = np.linalg.norm(rvec)
    if theta == 0:
        return np.eye(3)
    k = rvec / theta
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(theta) * K + (1 - math.cos(theta)) * K @ K


def _cameras():
    import tomllib
    cal = tomllib.loads((SAMPLE / "freemocap_sample_data_camera_calibration.toml").read_text())
    return [cal[k] for k in sorted(k for k in cal if k.startswith("cam_"))]


def _quat_mul(a, b):
    w1, x1, y1, z1 = np.moveaxis(a, -1, 0)
    w2, x2, y2, z2 = np.moveaxis(b, -1, 0)
    return np.stack([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2], -1)


def build_channels(frames: int | None = None, seed: int = 20261115) -> list[dict]:
    """Return channel dicts with values (F, names, components) float64 and per-frame timestamps.

    frames > 1108 tiles the real data forward/backward (mirror) so trajectories stay continuous; timestamps
    are regenerated for the full length (30 fps + 0.5 ms capture jitter), starting at 0 s.
    """
    out = SAMPLE / "output_data"
    real_f = 1108
    total = frames or real_f
    period = np.r_[np.arange(real_f), np.arange(real_f - 2, 0, -1)]
    idx = period[np.arange(total) % len(period)]
    rng = np.random.default_rng(seed)

    rtm = np.load(out / "rtmpose_skeleton_3d.npy")[idx]
    rtm_names = (_names_from_csv(out / "rtmpose_body_3d_xyz.csv") + [f"left_hand.{n}" for n in _names_from_csv(out / "rtmpose_left_hand_3d_xyz.csv")]
                 + [f"right_hand.{n}" for n in _names_from_csv(out / "rtmpose_right_hand_3d_xyz.csv")]
                 + [f"face.{n}" for n in _names_from_csv(out / "rtmpose_face_3d_xyz.csv")])
    assert len(rtm_names) == rtm.shape[1] == 137, (len(rtm_names), rtm.shape)
    rigid = np.load(out / "rtmpose_body_rigid_3d_xyz.npy")[idx]
    rigid_names = _names_from_csv(out / "rtmpose_body_rigid_3d_xyz.csv")
    mp = np.concatenate([np.load(out / f"mediapipe_{p}_3d_xyz.npy") for p in ("body", "left_hand", "right_hand")], 1)[idx]
    mp_names = (_names_from_csv(out / "mediapipe_body_3d_xyz.csv") + [f"left_hand.{n}" for n in _names_from_csv(out / "mediapipe_left_hand_3d_xyz.csv")]
                + [f"right_hand.{n}" for n in _names_from_csv(out / "mediapipe_right_hand_3d_xyz.csv")])
    com = np.concatenate([np.load(out / "rtmpose_body_segment_center_of_mass.npy"), np.load(out / "rtmpose_body_total_body_center_of_mass.npy")], 1)[idx]
    com_names = _names_from_csv(out / "rtmpose_body_segment_center_of_mass.csv") + ["total_body_center_of_mass"]
    angles_deg = np.load(out / "joint_angles.npy")[idx]
    with (out / "joint_angles.csv").open() as handle:
        angle_names = handle.readline().strip().split(",")
    assert len(angle_names) == angles_deg.shape[1]

    import pandas as pd
    bone = pd.read_csv(SAMPLE / "saved_data" / "freemocap_sample_data_h264_bone_and_joint_data.csv")
    bones = sorted({c.split("_head_center")[0] for c in bone.columns if c.endswith("_head_center_world_x")})
    heads_m = np.stack([bone[[f"{b}_head_center_world_{a}" for a in "xyz"]].to_numpy() for b in bones], 1)[:real_f][idx]
    quat = np.stack([bone[[f"{b}_rotation_quaternion_{a}" for a in "wxyz"]].to_numpy() for b in bones], 1)[:real_f][idx]
    quat = quat / np.linalg.norm(quat, axis=-1, keepdims=True)  # pipeline-style float64 renormalisation
    spine = quat[:, bones.index("spine")][:, None, :]
    local = _quat_mul(spine * np.array([1, -1, -1, -1]), quat)
    local = local / np.linalg.norm(local, axis=-1, keepdims=True)

    # timing: per-camera capture clocks and the group's synchronized timeline (relative seconds)
    cams = _cameras()
    base = np.arange(total) / FPS
    capture = [base + 0.0002 * i + rng.normal(0, 0.0005, total) for i in range(len(cams))]
    sync = np.mean(capture, axis=0)

    ch = []

    def add(kind, source, ref, names, comps, values, times):
        values = np.ascontiguousarray(values, dtype=np.float64).reshape(total, len(names), len(comps))
        ch.append(dict(kind=kind, source=source, reference_frame=ref, names=tuple(names), components=dict(comps),
                       values=values, times=np.asarray(times, np.float64)))

    weights_all = []
    obs_all = []
    for ci, cam in enumerate(cams):
        R = _rodrigues(cam["rotation"])
        t = np.asarray(cam["translation"], float)
        K = np.asarray(cam["matrix"], float)
        k1 = cam["distortions"][0]
        width, height = cam["size"]
        Xc = rtm @ R.T + t
        xn = Xc[..., :2] / Xc[..., 2:3]
        r2 = (xn ** 2).sum(-1, keepdims=True)
        xd = xn * (1 + k1 * r2)
        uv = np.stack([K[0, 0] * xd[..., 0] + K[0, 2], K[1, 1] * xd[..., 1] + K[1, 2]], -1)
        noise = rng.normal(0, 0.5, uv.shape)
        uvn = uv + noise
        vis = rng.beta(8, 2, uv.shape[:2])
        valid = (Xc[..., 2] > 0) & (uvn[..., 0] >= 0) & (uvn[..., 0] < width) & (uvn[..., 1] >= 0) & (uvn[..., 1] < height) & (vis > 0.3)
        overlay = np.concatenate([uvn, vis[..., None]], -1)
        overlay[~valid] = np.nan
        image = f"camera:{ci}:image"
        add("OVERLAY_2D", "rtmpose_wholebody", image, rtm_names, {"x": "px", "y": "px", "visibility": "1"}, overlay, capture[ci])
        add("TIMESTAMPS", f"camera:{ci}", None, ["capture"], {"timestamp_s": "s"}, capture[ci], capture[ci])
        with np.errstate(invalid="ignore"):
            u_ok = np.where(valid, uvn[..., 0], np.nan)
            v_ok = np.where(valid, uvn[..., 1], np.nan)
            box = np.stack([np.nanmin(u_ok, 1) - 10, np.nanmin(v_ok, 1) - 10, np.nanmax(u_ok, 1) + 10, np.nanmax(v_ok, 1) + 10,
                            np.clip(0.85 + 0.05 * rng.normal(size=total), 0, 1), (np.arange(total) % 10 == 0).astype(float)], -1)
        add("BOXES_2D", "rtmdet_person", image, ["person"], {"x1": "px", "y1": "px", "x2": "px", "y2": "px", "confidence": "1", "detector_ran": "1"}, box, capture[ci])
        weights_all.append(np.where(valid, vis, 0.0))
        obs_all.append((valid, np.where(valid, np.linalg.norm(noise, axis=-1), np.nan)))
    add("TIMESTAMPS", f"timing:{GROUP}", None, ["synchronized"], {"timestamp_s": "s"}, sync, sync)
    wsum = np.sum(weights_all, 0)
    for ci, (valid, err) in enumerate(obs_all):
        src, image = f"camera:{ci}", f"camera:{ci}:image"
        add("REPROJECTION_ERROR", src, image, rtm_names, {"error": "px"}, err, sync)
        add("RECONSTRUCTION_COVERAGE", src, image, rtm_names, {"observed": "1", "reconstructed": "1"},
            np.stack([valid, valid & (wsum > 0)], -1).astype(float), sync)
        add("TRIANGULATION_WEIGHTS", src, image, rtm_names, {"weight": "1"}, np.divide(weights_all[ci], wsum, out=np.zeros_like(wsum), where=wsum > 0), sync)
    mm = {"x": "mm", "y": "mm", "z": "mm"}
    add("RAW_KEYPOINTS_3D", "rtmpose_wholebody", WORLD, rtm_names, mm, rtm, sync)
    add("MAPPED_KEYPOINTS_3D", "model:human_body", WORLD, rigid_names, mm, rigid, sync)
    add("LANDMARKS_3D", "model:human_body", WORLD, mp_names, mm, mp, sync)
    add("SEGMENT_ORIGINS", "model:human_body", WORLD, bones, mm, heads_m * 1000.0, sync)
    quat_c = {"w": "1", "x": "1", "y": "1", "z": "1"}
    add("ROTATIONS_WORLD", "model:human_body", WORLD, bones, quat_c, quat, sync)
    add("ROTATIONS_LOCAL", "model:human_body", "model:human_body:parent", bones, quat_c, local, sync)
    angles = np.deg2rad(angles_deg)
    if frames is None or frames <= real_f:
        # codec edge cases (labelled in the report): negative zero, smallest float32 subnormal, one null
        angles[0, 0], angles[0, 1], angles[1, 0] = -0.0, float(np.float32(1.401298464324817e-45)), np.nan
    add("JOINT_ANGLES", "model:human_body", WORLD, angle_names, {"radians": "rad"}, angles, sync)
    add("DERIVED_POINTS", "model:human_body", WORLD, com_names, mm, com, sync)
    pairs = [(5, 7), (7, 9), (6, 8), (8, 10), (11, 13), (13, 15), (12, 14), (14, 16), (5, 6), (11, 12), (5, 11), (6, 12)]
    seg_names = [f"{rtm_names[a]}-{rtm_names[b]}" for a, b in pairs]
    measured = np.stack([np.linalg.norm(rtm[:, a] - rtm[:, b], axis=-1) for a, b in pairs], 1)
    add("RIGID_BODY_RESIDUALS", "model:human_body", WORLD, seg_names, {"measured_length": "mm", "residual": "mm"},
        np.stack([measured, measured - np.median(measured, 0)], -1), sync)
    for c in ch:
        c["sensor_group"] = GROUP
        assert not np.isinf(c["values"]).any()
    return ch


def descriptor_json(channels) -> bytes:
    """Stand-in for the 'freemocap.recording' schema-metadata descriptor (realistic size, not the real model)."""
    return json.dumps({"recording_id": "parquet_dtypes_test", "runs": {"0": {"channels": [
        {k: c[k] for k in ("sensor_group", "source", "reference_frame", "kind", "names", "components")} | {"stage": "x"}
        for c in channels]}}}).encode()


# ---------------------------------------------------------------- batches per design

def _value_columns(design, time_channel, v, count):
    mask = np.isnan(v)
    f32 = lambda x: pa.array(x.astype(np.float32), mask=mask, type=pa.float32())
    f64 = lambda x: pa.array(x, mask=mask, type=pa.float64())
    if design in ("f64", "D_timing"):
        return [f64(v)]
    if design == "f64w":
        return [f64(v) if time_channel else f64(v.astype(np.float32).astype(np.float64))]
    if design in ("C", "D_main"):
        return [pa.nulls(count, pa.float32()) if time_channel else f32(v)]
    if design == "A":
        return [pa.nulls(count, pa.float32()), f64(v)] if time_channel else [f32(v), pa.nulls(count, pa.float64())]
    raise ValueError(design)


def design_batches(design: str, channels, run_id: int = 0):
    schema = schema_for(design)
    for c in channels:
        t = is_time(c)
        if (design == "D_main" and t) or (design == "D_timing" and not t):
            continue
        comps = tuple(c["components"])
        ncomp = len(comps)
        per_frame = len(c["names"]) * ncomp
        flat = c["values"].reshape(-1)
        names = pa.array(c["names"], type=STR)
        cnames = pa.array(comps, type=STR)
        units = pa.array(tuple(c["components"].values()), type=STR)
        rows = (BATCH // per_frame) * per_frame or BATCH
        for start in range(0, flat.size, rows):
            ind = np.arange(start, min(start + rows, flat.size))
            fr = ind // per_frame
            pts = (ind // ncomp) % len(c["names"])
            ax = ind % ncomp
            n = len(ind)
            cols = [pa.array(c["times"][fr], type=pa.float64()),
                    pa.repeat(pa.scalar(c["sensor_group"], STR), n),
                    pa.array(fr.astype(np.int64), type=pa.int64()),
                    pa.repeat(pa.scalar(c["source"], STR), n),
                    pa.repeat(pa.scalar(c["reference_frame"], STR), n),
                    pa.repeat(pa.scalar(c["kind"], STR), n),
                    names.take(pts), cnames.take(ax),
                    *_value_columns(design, t, flat[ind], n),
                    units.take(ax),
                    pa.repeat(pa.scalar(run_id, pa.int64()), n)]
            yield pa.RecordBatch.from_arrays(cols, schema=schema)


def value_cols(schema):
    return [n for n in schema.names if n.startswith("value")]


def writer_kwargs(schema, encoding, codec, level):
    kw = dict(compression=codec)
    if level is not None:
        kw["compression_level"] = level
    vc = value_cols(schema)
    if encoding != "dict":
        kw["use_dictionary"] = [n for n in schema.names if n not in vc]
    if encoding == "bss":
        kw["use_byte_stream_split"] = vc
    return kw


def write_parquet(path, schema, batches, encoding, codec, level):
    with pq.ParquetWriter(path, schema, **writer_kwargs(schema, encoding, codec, level)) as w:
        for b in batches:
            w.write_batch(b)


def file_paths(design, encoding, codec, level):
    lab = codec_label(codec, level)
    return [SCR / "files" / design / f"{part}__{encoding}__{lab}.parquet" for part in DESIGNS[design]]


def float_bits_equal(a, b) -> bool:
    """Bit-exact float compare including nulls (and -0.0 on non-null slots)."""
    a = a.combine_chunks() if isinstance(a, pa.ChunkedArray) else a
    b = b.combine_chunks() if isinstance(b, pa.ChunkedArray) else b
    if a.type != b.type or len(a) != len(b):
        return False
    na = a.is_null().to_numpy(zero_copy_only=False)
    if not np.array_equal(na, b.is_null().to_numpy(zero_copy_only=False)):
        return False
    view = np.uint32 if a.type == pa.float32() else np.uint64
    xa = a.fill_null(0).to_numpy(zero_copy_only=False).view(view)
    xb = b.fill_null(0).to_numpy(zero_copy_only=False).view(view)
    return bool(np.array_equal(xa[~na], xb[~na]))


def tables_equal(read: pa.Table, expected: pa.Table) -> list[str]:
    """Column names that differ (floats bit-exact, others value-equal after casting to the expected type)."""
    if read.column_names != expected.column_names:
        return ["<columns>"]
    bad = []
    for name in expected.column_names:
        e, r = expected.column(name), read.column(name)
        if pa.types.is_floating(e.type):
            ok = float_bits_equal(r, e)
        else:
            try:
                ok = r.cast(e.type).combine_chunks().equals(e.combine_chunks())
            except Exception:
                ok = False
        if not ok:
            bad.append(name)
    return bad
