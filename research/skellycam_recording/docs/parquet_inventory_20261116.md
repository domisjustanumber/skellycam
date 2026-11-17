# Parquet inventory (freemocap c27fc299)

Status: research report, 2026-11-16, for the skellyfileformat spec draft v2 (section 16). A read-only sub-agent study of freemocap c27fc299 (and sfn26). The main session saved it; spot-checks are noted at the end.


Scope: `<rec>/<rec>_data.parquet` as written at `c27fc299` (= `upstream/development-streaming`). All citations are `path:line` at c27fc299 unless prefixed `sfn26:`. External packages were read at the revisions pinned in `c27fc299:uv.lock`:
- skellyforge `f5404db` (uv.lock:2645-2647)
- skellytracker `03b9c1d` (uv.lock:2674-2676)
- skellycam `169caf63` (uv.lock:2613-2615)

Citations into them are prefixed `skellyforge@f5404db:`, `skellytracker@03b9c1d:` and `skellycam@169caf63:`. (The repo's `.venv` has a different skellyforge, `ddf24f3`; I did not use it.) pyarrow is locked at 26.0.0 (uv.lock:1930-1931) and pydantic at 2.14.1 (uv.lock:1982-1983).

---

## 1. Arrow/Parquet physical schema

### 1.1 Columns (`SAMPLE_SCHEMA`, `freemocap/core/recording/sample_encoding/arrow_schema.py:15-29`)

The file is a "tall" table: one row per scalar sample (frame × name × component).

| # | Column | Arrow type | Nullable | Meaning / allowed values |
|---|---|---|---|---|
| 1 | `timestamp_s` | float64 | no (:17) | Sample time in recording-relative seconds. Must be finite (arrow_schema.py:106-114, 193-195). Strictly increasing per trajectory (:138-145, :196-197). |
| 2 | `sensor_group` | string | no (:18) | Sampling-grid ID. Must be a key of `runs[run_id].sensor_groups` (recording_descriptor.py:162-166). Written as `camera_group:<6 hex>` (see §3.3). |
| 3 | `frame_number` | int64 | no (:19) | Sample ID on that grid. Must be ≥0 (arrow_schema.py:109, 193) and strictly increasing per trajectory (:140-145). |
| 4 | `source` | string | no (:20) | Producer ID. Must be a key of `runs[run_id].sources` (recording_descriptor.py:162-166). Naming in §3.3. |
| 5 | `reference_frame` | string | **yes** (:21) | Coordinate/reference ID, a key of `runs[run_id].reference_frames`, or null (recording_descriptor.py:167-171). Null for `TIMESTAMPS` rows (observation_inputs.py:262). |
| 6 | `channel` | string | no (:22) | The channel kind: a `ChannelKind` value (§2.3). |
| 7 | `name` | string | no (:23) | Entity name. Must be in the declared `Channel.names` (arrow_schema.py:98-104). |
| 8 | `component` | string | no (:24) | Component name. Must be a key of `Channel.components` (:100). |
| 9 | `value` | float64 | **yes** (:25) | The scalar value. Null means missing. NaN and ±inf are rejected (:108-114, :193-195). |
| 10 | `units` | string | no (:26) | Must equal `Channel.components[component]` (:100, :185-187). |
| 11 | `run_id` | int64 | no (:27) | Retained run slot. Must be a key of `runs` (:92-97 via channel_index :52-62); ≥0 (recording_descriptor.py:200-203). |

- **Column order, types and nullability must match exactly.** The writer checks `batch.schema.equals(SAMPLE_SCHEMA, check_metadata=False)` (arrow_schema.py:66-67). The reader checks `schema.equals(SAMPLE_SCHEMA, check_metadata=False)` (parquet_reader.py:40-41). Required columns must contain no nulls (arrow_schema.py:68-70).
- [inferred from pyarrow Field equality] A third-party file must therefore decode in pyarrow as plain `string`, `int64` and `float64`: not `large_string`, `dictionary<…>` or `int32`. Nine columns must be REQUIRED and two (`reference_frame`, `value`) OPTIONAL.
- **No Arrow dictionary types** are used in the schema (arrow_schema.py:15-29). Writer batches build plain `pa.string()` arrays (channel_series.py:53-55, 65-76).

### 1.2 Writer settings (`freemocap/core/recording/parquet_storage/parquet_writer.py`)

| Setting | Value | Citation |
|---|---|---|
| Writer | `pq.ParquetWriter(temporary, schema=schema, compression="zstd")` | parquet_writer.py:80 |
| Compression | `zstd`. No level is passed. | :80 |
| Schema metadata | `SAMPLE_SCHEMA.with_metadata({b"freemocap.recording": metadata.model_dump_json().encode("utf-8")})` | :57-59; key at arrow_schema.py:30 |
| `use_dictionary`, `write_statistics`, `data_page_size`, `version`, `row_group_size`, `store_schema`, sorting columns, bloom filters | **Not set.** pyarrow defaults apply. [inferred: dictionary page encoding on, statistics on, format 2.6, Arrow schema stored in `ARROW:schema`] | :80 (only `compression` passed) |
| Row groups | `writer.write_batch(batch=batch)` once per yielded batch (:81-84). [inferred: pyarrow writes ≥1 row group per call, default cap 1 Mi rows.] Batches are ≤65536 rows: `SeriesSampling.batch_size = 65536` (channel_series.py:19); whole-frame batching at channel_series.py:56-57; `batch_size=65536` at observation_publication.py:206, 221, 227, 233. | |
| Sort order | **None declared.** Rows appear in generation order (§1.3). | |
| Durability | `os.fsync` on the temp file before replace | parquet_writer.py:85-86 |

- **Readers rely on row-group boundaries.** `recording_batches` iterates one row group at a time, in batches of 65536 (parquet_reader.py:48-56). The comment there: merging groups "can split complete frame grids or combine different channels, defeating columnar validation" (:49-53).

### 1.3 Row order as written (not normative, but this is what files contain)

- **Inside one channel batch** (`ChannelSeries.batches`, channel_series.py:58-63), rows are frame-major, then `name` in declared order, then `component` in declared dict order. Each batch holds whole frames when a frame fits in the batch (:56-57).
- **Fresh file** (observation_publication.py:174-234), in this order:
  1. reprojection diagnostics, per camera;
  2. reconstruction channels, per model;
  3. spatial series (`RAW_KEYPOINTS_3D`, then `KEYPOINTS_3D`; recording_pipeline.py:273-275);
  4. per camera: `OVERLAY_2D`, then `BOXES_2D`, then capture `TIMESTAMPS`;
  5. last, the group `synchronized` `TIMESTAMPS`.
- **Checkpoint republish** (checkpoint_publication.py:63-88), in this order:
  1. every other run's rows, verbatim (:63-69);
  2. reusable rows of the base run, relabelled with the target `run_id` (:70-82);
  3. newly computed batches, which must target only the planned channels (:83-88).
- **The validator's fast path** needs single-channel rectangular batches (arrow_schema.py:155-187). Any other batch falls back to scalar validation (:71-75), which accepts arbitrary interleaving with one exception: the four quaternion components of a (trajectory name, frame) must be contiguous (:116-137).

### 1.4 Publication mechanics (temp file, atomic replace, lock)

| Item | Rule | Citation |
|---|---|---|
| Path | `{base}/{recording_name}/{recording_name}_data.parquet` | system/recording_structure/recording_structure.py:124-127 |
| `recording_id` must equal the folder name | Writer: `ValueError("Recording descriptor ID must match its directory name")` | parquet_writer.py:44-45 |
| | Reader (`recording_view`): `metadata.recording_id != path.parent.name` raises | parquet_storage/recording_view.py:46-47 |
| | Also checked in `read_saved_observations` | result_processing/saved_observations.py:33-34 |
| Lock | `FileLock(<recording folder>/.processing.lock, timeout=0)` (`filelock` package). Non-blocking: fails if held. | parquet_writer.py:28-33 |
| | The caller holds it from run allocation through publication | :43; observation_publication.py:240 |
| | Readers that rebuild inputs also take it | saved_observations.py:31 |
| Temp file | `tempfile.mkstemp(dir=<recording folder>, suffix=".parquet.tmp")`, so the name is `tmp<random>.parquet.tmp` | parquet_writer.py:74-78 |
| | Always unlinked in `finally` | :90-91 |
| Cancellation | Checked per batch and once more before replace | :82-83, :87-88 |
| Replace (Windows) | `ReplaceFileW(dest, src, …)` when the destination exists. Retried only on error 1175, with delays 0.01/0.05/0.1/0.25/0.5 s. | parquet_storage/shared_file.py:43-60 |
| Replace (other OS) | `os.replace` | shared_file.py:59-60 |
| Readers on Windows | Open with FILE_SHARE_READ\|WRITE\|DELETE so atomic replace works under readers | shared_file.py:63-79 |
| Companion JSON | `write_recording_info` runs after the Parquet replace. It writes `{rec}_recording_info.json` via an `.info.tmp` temp file and `replace`, with a `processed` block (see below). | parquet_writer.py:63; recording_info.py:9-47 |

The `processed` block in the companion JSON holds: `schema_version=1`, `parquet_sha256`, `recording_id`, `parquet`, `selected_run_id`, a per-run summary, and conventions: `quaternion_order='wxyz'`, `units='per component'`, `coordinates='per reference frame'`, `array_order='frames, names, components'` (recording_info.py:31-34).

---

## 2. File-level metadata key and descriptor model tree

### 2.1 Key and encoding

- **Key:** `b"freemocap.recording"`, stored in the Arrow schema metadata and hence the Parquet key-value metadata (arrow_schema.py:30; parquet_writer.py:57-59).
- **Value:** UTF-8 JSON from pydantic `RecordingMetadata.model_dump_json()` (parquet_writer.py:58). It is compact (no indent), all fields are emitted (defaults included), and fields appear in declaration order. [inferred: pydantic v2 default behaviour]
- **Read:** `RecordingMetadata.model_validate_json(payload)`. A validation error becomes `ValueError("Recording metadata is incompatible or invalid …")` (parquet_reader.py:27-35). A missing key raises "Missing recording descriptor" (:42-44).
- **JSON quirks:**
  - `runs` is `dict[int, …]`, so its keys serialise as strings. recording_status.py:237 indexes `runs[str(selected_run_id)]`.
  - Tuples serialise as arrays and enums as their values. [inferred: pydantic]
- A second, hand-rolled reader parses this JSON directly with `json.loads` for the Blender stage check (system/recording_status/recording_status.py:233-250).

### 2.2 Model tree

Every freemocap model below inherits `Descriptor`: `ConfigDict(extra="forbid", frozen=True)` (recording_descriptor.py:18-19), unless noted otherwise.

#### `RecordingMetadata` (root), recording_descriptor.py:191-204

| Field | Type | Default | Constraints |
|---|---|---|---|
| `schema_version` | `Literal[1]` | 1 | :192 |
| `recording_id` | str | required | min_length=1 (:193); must equal the folder name (§1.4) |
| `selected_run_id` | int | required | ≥0 (:194); must be a key of `runs` (:200-203) |
| `recording_info` | `dict[str, JsonValue]` | `{}` | :195. Neither freemocap construction site at c27fc299 fills it (observation_publication.py:244-246; checkpoint_publication.py:177-182 copies it forward). [inferred: always `{}` in practice] |
| `runs` | `dict[int, RunDescriptor]` | required | All keys ≥0 (:200-203) |

#### `RunDescriptor`, recording_descriptor.py:98-188

| Field | Type | Default |
|---|---|---|
| `calibration_updates` | `dict[str, CalibrationUpdateRequest]` | `{}` (:99) |
| `scale_fits` | `tuple[RecordingScaleFit, ...]` | `()` (:100) |
| `camera_geometry` | `dict[str, tuple[CameraModel, ...]]` | `{}` (:101-103) |
| `sensor_groups` | `dict[str, SensorGroup]` | required (:104) |
| `sources` | `dict[str, Source]` | required (:105) |
| `reference_frames` | `dict[str, dict[str, JsonValue]]` | required (:106). Free JSON; shapes in §3.4 |
| `models` | `dict[str, RecordedModel]` | required (:107) |
| `processing` | `dict[str, JsonValue]` | required (:108). Shapes in §2.4 |
| `channels` | `tuple[Channel, ...]` | required (:109) |
| `static_channels` | `tuple[StaticChannel, ...]` | `()` (:110) |
| `checkpoints` | `tuple[StageCheckpoint, ...]` | `()` (:111) |

Validator `validate_references` (:113-188):
- `calibration_updates` keys ⊆ `sensor_groups` (:115-116).
- `models[k].model_id == k` (:117-118).
- `scale_fits` are unique per `(sensor_group, source)` (:119-121), and each fit's group, source and reference must exist (:122-130).
- `reference_frames[fit.reference_frame]["units"] == fit.units` (:131-134).
- `camera_geometry` keys ⊆ `sensor_groups` (:135-136), and camera ids are unique within a group (:137-139).
- Channel keys `(sensor_group, source, reference_frame, kind)` are unique across `channels` and `static_channels` (:140-161; key fn :94-95).
- `MODEL_SCALE`, `SEGMENT_SCALES` and `SEGMENT_LENGTHS` channels are forbidden when a non-null fit exists for the same group and source: "derived from the stored fit, not duplicated" (:146-158).
- A channel's group and source must exist (:162-166), and a non-null `reference_frame` must exist (:167-171).
- `(sensor_group, stage)` checkpoints are unique, and their groups must exist (:172-176).
- When `processing[group]` contains `stage_provenance`:
  - the group must exist (:180-181);
  - each `output_source` must exist (:183-184);
  - each provenance stage needs a checkpoint or a channel with that group and stage (:185-187).

#### `SensorGroup`, :22-24

| Field | Type | Constraints |
|---|---|---|
| `clock_description` | str | min_length=1. Writer value: `"recording-relative seconds; timing method declared per source"` (observation_publication.py:156) |
| `sample_count` | int | ≥0. **Every** declared (name, component) trajectory in the group must have exactly this many rows (arrow_schema.py:244-251) |

#### `SourceKind` (StrEnum), :27-31

Members: `INSTANCE="instance"`, `TRACKER="tracker"`, `CAMERA="camera"`, `TIMING="timing"`.

#### `Source`, :34-36

| Field | Type | Notes |
|---|---|---|
| `kind` | `SourceKind` | |
| `definition` | `dict[str, JsonValue]` | Free JSON at this level. Shapes per kind are in §3.3. Playback re-validates the camera and instance shapes strictly (playback_queries.py:131, 137). |

#### `Channel`, :39-67

| Field | Type |
|---|---|
| `sensor_group` | str |
| `source` | str |
| `reference_frame` | `str \| None` (required; no default) |
| `kind` | `ChannelKind` |
| `names` | `tuple[str, ...]` |
| `components` | `dict[str, str]` (component → units, ordered) |
| `stage` | `ProcessingStage` |

Validator (:48-67):
- kind, names and components must be nonempty (:50-51).
- Names must be unique and nonempty (:52-55).
- Component names and units must be nonempty (:56-59).
- For `ROTATIONS_LOCAL` or `ROTATIONS_WORLD`: components must equal `{"w":"1","x":"1","y":"1","z":"1"}` (:60-64), and `reference_frame` must be non-null (:65-66).

#### `StageCheckpoint`, :70-73

Fields: `sensor_group: str`, `stage: ProcessingStage`, `signature: str` (min_length=1).

#### `StaticChannel`, :76-91

| Field | Type |
|---|---|
| `channel` | `Channel` |
| `values` | `dict[str, dict[str, float]]` (name → component → value) |

Validator: the name set equals `channel.names`, the component set equals `channel.components`, and all values are finite (:80-91). Static channels are **not stored as rows**. `read_static_channels` = authored `static_channels` plus views derived from `scale_fits` (parquet_reader.py:17-19; fit_channels.py:18-57).

#### `ChannelKind` (StrEnum), core/types/channel_kind.py:6-26

All 20 members, value = name:

`KEYPOINTS_3D`, `MAPPED_KEYPOINTS_3D`, `LANDMARKS_3D`, `SEGMENT_ORIGINS`, `ROTATIONS_LOCAL`, `ROTATIONS_WORLD`, `DERIVED_POINTS`, `JOINT_ANGLES`, `OVERLAY_2D`, `BOXES_2D`, `SEGMENT_LENGTHS`, `SEGMENT_SCALES`, `MODEL_SCALE`, `OVERLAY_REPROJECTIONS`, `TIMESTAMPS`, `RAW_KEYPOINTS_3D`, `TRIANGULATION_WEIGHTS`, `REPROJECTION_ERROR`, `RECONSTRUCTION_COVERAGE`, `RIGID_BODY_RESIDUALS`.

`OVERLAY_REPROJECTIONS` appears only in streaming (core/streaming/producers/overlay_producer.py:60). No Parquet writer for it was found.

#### `ProcessingStage` (StrEnum), core/pipeline/posthoc/processing_request.py:8-16

Members, in order (`STAGE_ORDER` :19): `TIMING="timing"`, `OBSERVATIONS="observations"`, `TRIANGULATION="triangulation"`, `FILTERING="filtering"`, `SCALE_FIT="scale_fit"`, `RECONSTRUCTION="reconstruction"`, `BIOMECHANICS="biomechanics"`, `REPROJECTION="reprojection"`. No channel is written with stage `reprojection` [inferred from §3.1].

#### `SampleComponent`, `SampleUnit`, `TimingSampleName` (StrEnums), data_descriptors/sample_conventions.py:6-36

| Enum | Members |
|---|---|
| `SampleComponent` | `LENGTH="length"`, `SCALE="scale"`, `RADIANS="radians"`, `W="w"`, `X="x"`, `Y="y"`, `Z="z"`, `VISIBILITY="visibility"`, `TIMESTAMP="timestamp_s"`, `X1="x1"`, `Y1="y1"`, `X2="x2"`, `Y2="y2"`, `CONFIDENCE="confidence"`, `DETECTOR_RAN="detector_ran"` |
| `SampleUnit` | `RADIANS="rad"`, `PIXELS="px"`, `DIMENSIONLESS="1"`, `SECONDS="s"`, `MILLIMETERS="mm"` |
| `TimingSampleName` | `CAPTURE="capture"`, `SYNCHRONIZED="synchronized"` |

Some components are written as literal strings outside these enums: `measured_length`, `residual` (reconstruction_samples.py:172); `error`, `observed`, `reconstructed`, `weight` (diagnostic_samples.py:24, 29, 36).

#### `RecordingScaleFit`, data_descriptors/scale_fit.py:13-30

`ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)`.

| Field | Type |
|---|---|
| `sensor_group` | str |
| `source` | str |
| `reference_frame` | str |
| `units` | `SampleUnit`, restricted to `px` or `mm` (:26-30) |
| `fit` | `ModelScaleFit \| None` |
| `inputs` | `RecordingFitInputs` |

`RecordingFitInputs` (core/reconstruction/recording_fit.py:17-23), `extra="forbid"`, frozen:

| Field | Type |
|---|---|
| `algorithm_version` | int ≥1 (writer uses 1, :36) |
| `keypoint_names` | `tuple[str, ...]` |
| `points` | str, exactly 64 chars (signature) |
| `model` | str, exactly 64 chars (signature) |

`ModelScaleFit` is a skellyforge dataclass (skellyforge@f5404db:skellyforge/core/skeleton/pose/model_scale_fitting.py:126-165):

| Field | Type / rule |
|---|---|
| `fitted_scale` | float, finite and >0 |
| `segment_scales` | Mapping[str, float]: finite, >0, and the same nonempty key set as `segment_lengths` |
| `segment_lengths` | Mapping[str, float]: finite, ≥0 |
| `measured_segment_names` | frozenset[str]: ⊆ `segment_scales` |
| `voting_segment_names` | frozenset[str] |

#### `StageProvenance` / `StageProvenanceSet`, data_descriptors/stage_provenance.py:15-56

These are stored inside `processing[group]["stage_provenance"]` (`PROVENANCE_KEY` :15).

`StageProvenanceSet` (:47-50), `extra="forbid"`:
- `version: Literal[1]` (default 1)
- `stages: dict[ProcessingStage, StageProvenance]` (default `{}`)

`StageProvenance` (:18-44), `extra="forbid", allow_inf_nan=False`:

| Field | Type / default |
|---|---|
| `attempt_id` | str, min_length=1 (writer: uuid4 hex; result_processing/provenance.py:59) |
| `recorded_at` | datetime, must carry a timezone (:34-35) |
| `effective_settings` | `dict[str, JsonValue]` |
| `default_settings` | `dict[str, JsonValue] \| None` |
| `input_signatures` | `dict[str, str]`, nonempty, with nonempty values (:36-37) |
| `software` | `dict[str, JsonValue]`, nonempty (:40-41). Writer shape: `{python, packages:{name:{version,commit}}, core_sha256}` (provenance.py:35-48) |
| `output_sources` | `tuple[str, ...]`, nonempty and unique (:38-39) |
| `limitations` | `tuple[str, ...]`, default `()` |
| `base_run_id` | `int \| None`, ≥0 |
| `base_descriptor_signature` | `str \| None`. Must be given together with `base_run_id` (:42-43) |

#### `RecordedModel`, data_descriptors/recording_model.py:15-64

`ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)` (:16).

| Field | Type | Default |
|---|---|---|
| `model_id` | str | required, nonempty (:46) |
| `detector_type` | str | required, nonempty (:47) |
| `tracker_keypoint_names` | `tuple[str, ...]` | required; nonempty and unique (:54-57) |
| `skeleton` | `SkeletonSnapshot` | required |
| `rest_pose` | `RestPoseSnapshot` | required |
| `mappings` | `tuple[TrackerMappingSnapshot, ...]` | required, nonempty (:49) |
| `center_of_mass` | `CenterOfMassDefinitions` | required |
| `segment_masses` | `dict[str, float]` | required; keys == `center_of_mass.all_segment_names`, all values >0 (:58-63) |
| `scale_reference_name` | str | required, nonempty (:48) |
| `anchor_segment_name` | `str \| None` | None (:27) |

- **Serializer** (:29-41): drops `skeleton.segments[*].observation_frame` when it is None.
- **Equality** compares `model_dump()` (:66-69).
- Writers build it with `RecordedModel.from_bundle` (:71-84), keyed by `model_id` (observation_publication.py:162).

Nested skellyforge and skellytracker types. All are stdlib dataclasses, so pydantic serialises them as objects. [inferred]

| Type | Fields (citation) |
|---|---|
| `SkeletonSnapshot` | `name: str`, `landmarks: tuple[LandmarkSnapshot]`, `segments: tuple[SegmentSnapshot]`, `joints: tuple[JointSnapshot]`, `chains: tuple[ChainSnapshot]`, `landmark_groups: tuple[LandmarkGroup]`, `landmark_connections: tuple[LandmarkConnectionGroup]`, `derived_quantities: tuple[str]`, `coordinate_system: str`. Names must be unique within each collection. (skellyforge@f5404db:skellyforge/core/skeleton/skeleton_snapshot.py:124-251) |
| `LandmarkSnapshot` | `name`, `definition: str`, `position: (float, float, float)`, `segment: str`, `aliases: tuple[str]` (:27-33) |
| `FrameSnapshot` | `origin: str`, `primary_point: str`, `primary_axis: (int index, int sign)`, `secondary_point: str \| None`, `secondary_axis: (int, int) \| None`, `handedness: Handedness` (:57-66) |
| `SegmentSnapshot` | `name`, `landmarks: tuple[str]`, `frame: FrameSnapshot`, `aliases: tuple[str]`, `anatomical_segment: str \| None`, `observation_frame: FrameSnapshot \| None = None` (:96-104) |
| `JointSnapshot` | `name`, `parent`, `child`, `connect_at`, `joint_type: str`, `convention: EulerConvention` (:107-114) |
| `ChainSnapshot` | `name`, `segments: tuple[str]`, `joints: tuple[str]` (:117-121) |
| `RestPoseSnapshot` | `name`, `root_segment_name`, `parents: dict[str, str\|None]`, `connect_ats: dict[str,str]`, `orientations: dict[str, RotationQuaternion]` (:351-357) |
| `Handedness` (Enum) | `RIGHT_HANDED=1`, `LEFT_HANDED=-1` (skellyforge@f5404db:.../orthonormal_basis/handedness.py:22-26) |
| `SpatialAxis` (Enum, stored as `(index, sign)`) | `X=(0,1)`, `Y=(1,1)`, `Z=(2,1)`, `NEGATIVE_X=(0,-1)`, `NEGATIVE_Y=(1,-1)`, `NEGATIVE_Z=(2,-1)` (…/spatial_axis.py:24-30) |
| `EulerConvention` | `sequence: str` (xyz letters, no repeated adjacent axis), `angle_names: (str,str,str)` (distinct; default `<axis>_angle`), `zero_offsets: (float,float,float) = (0,0,0)` (…/linkage/joint_definition.py:23-58) |
| `RotationQuaternion` | `w, x, y, z: float`, finite and unit length (…/rotation_quaternion.py:65-107) |
| `LandmarkGroup` | `name`, `landmark_names: tuple[str]` (nonempty, no duplicates), `tags: tuple[str] = ()` (…/landmark_grouping.py:54-88) |
| `LandmarkConnectionGroup` | `name`, `pairs: tuple[tuple[str,...]]` (each pair exactly 2 names, no self-edges), `tags = ()` (:92-133) |
| `CenterOfMassDefinitions` | `definitions: Mapping[str, SegmentComDefinition]`, keyed by its own `name`, nonempty (skellyforge@f5404db:skellyforge/core/biomechanics/center_of_mass.py:98-111) |
| `SegmentComDefinition` | `name`, `proximal`, `distal`, `weights: tuple[ComLandmarkWeight]` (each >0, sum 1.0), `sided: bool = False` (:42-73). Sided segments expand to `left_<name>` and `right_<name>` (:75-83). |
| `ComLandmarkWeight` | `landmark: str`, `weight: float` (:29-39) |
| `TrackerMappingSnapshot` | `entries: dict[str, str \| list[str] \| dict[str, float] \| dict[str, Any]]`, `prefix: str \| None`, `known_tracker_keypoints: tuple[str] \| None`, `passthrough: bool` (skellytracker@03b9c1d:skellytracker/core/io/tracker_mapping.py:69, 91-101). The entry forms (name, list, weights, `anatomical_offset`) are documented at :24-52. |

#### `CameraModel`, core/tasks/calibration/shared/camera_model.py:13-48

`ConfigDict(extra="forbid", arbitrary_types_allowed=True)` (:16). It is not frozen.

| Field | Type | Default / rule |
|---|---|---|
| `id` | str (`CameraIdString = str`, skellycam@169caf63:skellycam/core/types/type_overloads.py:7) | required |
| `index` | int (`CameraIndexInt`, :11) | required |
| `image_size` | `(int, int)`, as **(width, height)** | :20 |
| `intrinsics` | `CameraIntrinsics` | |
| `extrinsics` | `CameraExtrinsics` | |
| `world_position` | float64[3] as a JSON list | `zeros(3)`; finite (:23, :26-32); mm per `__str__` (:109) |
| `world_orientation` | float64[3×3] as a JSON list of lists | `eye(3)`; finite (:24, :34-40); camera→world (:111) |

`CameraIntrinsics` (camera_intrinsics.py:7-19), `extra="forbid"`:
- `fx, fy, cx, cy: float`
- `k1, k2, p1, p2: float`, each default 0.0

`CameraExtrinsics` (camera_extrinsics.py:8-34), `extra="forbid"`:
- `quaternion_wxyz`: 4 finite floats
- `translation`: 3 finite floats (mm per camera_model.py:104)
- The rotation is world→camera (camera_model.py:105). World position = −Rᵀt (camera_extrinsics.py:52-55).

#### `CalibrationUpdateRequest`, core/tasks/calibration/shared/calibration_update.py:56-62

`extra="forbid"`, frozen.

| Field | Type |
|---|---|
| `path` | Path |
| `expected_mtime_ms` | finite float |
| `transformations` | `tuple[CalibrationTransform, ...]`, min_length=1 |
| `recording_id` | `str \| None` = None |

`CalibrationTransform` (calibration_transform.py:27-44), `extra="forbid"`, frozen:
- `operation: CalibrationTransformType`, one of `CHARUCO="charuco"`, `PERSON="person"`, `MANUAL="manual"` (:21-24)
- `quaternion_wxyz`: 4 finite floats, unit length
- `translation_mm`: 3 finite floats

The docstring gives the transform frame: "X right, Y forward, Z up", millimetres, scalar-first quaternion (:28-32).

### 2.3 Minimal valid descriptor

From a test, an empty run is valid (tests/test_tall_csv_export.py:191-194):
```json
{"schema_version":1,"recording_id":"empty","selected_run_id":0,"recording_info":{},
 "runs":{"0":{"calibration_updates":{},"scale_fits":[],"camera_geometry":{},"sensor_groups":{},
  "sources":{},"reference_frames":{},"models":{},"processing":{},"channels":[],
  "static_channels":[],"checkpoints":[]}}}
```
The test passes only the required run fields; the dump adds defaults.

A one-channel example also appears in a test: one `BOXES_2D` channel, `Source(kind="tracker", definition={})`, and `reference_frames={REF: {"width":1280,"height":720}}` (tests/test_box_samples.py:73-91).

[constructed from validators, not copied from a test] A minimal file with data would declare:
- one sensor group `{"clock_description":"…","sample_count":N}`;
- one source `"timing:<group>": {"kind":"timing","definition":{"method":"recorded"}}`;
- one channel `{"sensor_group":"<group>","source":"timing:<group>","reference_frame":null,"kind":"TIMESTAMPS","names":["synchronized"],"components":{"timestamp_s":"s"},"stage":"timing"}`;
- N rows with `value == timestamp_s`.

### 2.4 `processing[group]` contents written by freemocap (free JSON)

| Key | Content | Citation |
|---|---|---|
| `filtering` | `PosthocFilterReport.model_dump(mode="json")`: `algorithm_version: Literal[1]`, `config: PosthocFilterConfig`, `sampling_rate_hz: float\|None`, `filtered_runs ≥0`, `preserved_short_runs ≥0`, `gap_filling: GapFillingReport\|None` | observation_publication.py:164; core/reconstruction/posthoc_filtering.py:27-35 |
| `camera_assignment` | `{status, source_to_calibration:{source:camera.id}, fitness:{status, mean_cost, cameras:[…]}\|null, error_units:"pixels_at_1000_pixel_image_diagonal"}` | observation_publication.py:165; core/pipeline/dataflow/scientific_recording.py:42-50 |
| `stage_provenance` | `StageProvenanceSet` (§2.2) | stage_provenance.py:59-68 |

I did not inventory `PosthocFilterConfig` or `GapFillingReport` further.

---

## 3. Semantics an independent writer needs

### 3.1 Channels as freemocap writes them

| `channel` | source | reference_frame | names | components → units | stage | Citation |
|---|---|---|---|---|---|---|
| `TIMESTAMPS` (capture) | `camera:<id>` | null | `("capture",)` | `{timestamp_s: s}` | timing | observation_inputs.py:226-230, 256-267 |
| `TIMESTAMPS` (group) | `timing:<group>` | null | `("synchronized",)` | `{timestamp_s: s}` | timing | observation_publication.py:121-128 |
| `OVERLAY_2D` | tracker (`keypoint_model:…`) | `camera:<id>:image` | tracker point names `"<stage>.<point>"` | `{x: px, y: px, visibility: 1}` | observations | observation_inputs.py:213-225 |
| `BOXES_2D` (only if a detector exists) | `object_detector:yolox-m` | `camera:<id>:image` | detection stage names (e.g. `body`) | `{x1,y1,x2,y2: px, confidence: 1, detector_ran: 1}` | observations | observation_inputs.py:231-253 |
| `REPROJECTION_ERROR` | `camera:<id>` | `camera:<id>:image` | diagnostic point names | `{error: px}` (or `"1"` if not pixels) | triangulation | diagnostic_samples.py:20-26, 40-49 |
| `RECONSTRUCTION_COVERAGE` | `camera:<id>` | `camera:<id>:image` | same | `{observed: 1, reconstructed: 1}` | triangulation | :27-33 |
| `TRIANGULATION_WEIGHTS` | `camera:<id>` | `camera:<id>:image` | same | `{weight: 1}` | triangulation | :34-38 |
| `RAW_KEYPOINTS_3D` | tracker | `calibrated_world` or `camera_plane` | triangulated keypoint names, stage prefix stripped | `{x,y,z: mm or px}` | triangulation | spatial_points.py:85-100; posthoc_reconstruction.py:146 |
| `KEYPOINTS_3D` | tracker | same | same | same | filtering | spatial_points.py:100 |
| `RIGID_BODY_RESIDUALS` | `model:<model_id>` | spatial reference | segment names | `{measured_length, residual: ref units}` | reconstruction | reconstruction_samples.py:168-174 |
| `MAPPED_KEYPOINTS_3D` | `model:<id>` | spatial ref | `landmark_names` | `{x,y,z: ref units}` | reconstruction | :176-180, 212-228 |
| `LANDMARKS_3D` | `model:<id>` | spatial ref | `landmark_names` | `{x,y,z}` | reconstruction | :181-185 |
| `SEGMENT_ORIGINS` | `model:<id>` | spatial ref | segment names | `{x,y,z}` | reconstruction | :186-190 |
| `ROTATIONS_WORLD` | `model:<id>` | spatial ref | segment names | `{w,x,y,z: 1}` | reconstruction | :191-200 |
| `ROTATIONS_LOCAL` | `model:<id>` | `<model_id>:segment_parents` | segment names | `{w,x,y,z: 1}` | reconstruction | :201-216 |
| `JOINT_ANGLES` (if any joints) | `model:<id>` | `<model_id>:segment_parents` | all joints' Euler angle names, flattened | `{radians: rad}` | reconstruction | :229-242 |
| `DERIVED_POINTS` (if COM computed) | `model:<id>` | spatial ref | `("center_of_mass",)` | `{x,y,z}` | biomechanics | :243-259; core/types/derived_point_name.py:7 |
| `MODEL_SCALE` / `SEGMENT_SCALES` / `SEGMENT_LENGTHS` | `model:<id>` | fit reference | scale_reference_name / segments / segments | `{scale}` / `{scale}` / `{length}`, units = fit units | scale_fit | **Static only**, derived on read (fit_channels.py:18-57) |

- `DerivedPointName.XCOM="xcom"` exists (derived_point_name.py:8). No writer for it was found.
- Strict shape checks apply to the per-kind encoders:
  - `TIMESTAMPS`: observation_samples.py:39-47
  - `OVERLAY_2D`: :98-109
  - `BOXES_2D`: :171-181
  - Rotations: recording_descriptor.py:60-66

### 3.2 Values, nulls and timing

- **Null policy:** missing equals null, never NaN.
  - `ChannelSeries` turns NaN into Arrow null via `mask=np.isnan(values)` (channel_series.py:73).
  - Infinite values are rejected (:35-36).
  - The validator rejects any non-null non-finite value (arrow_schema.py:108-114, 193-195).
- **Complete coverage:** every declared (name, component) of every channel must have exactly `sensor_groups[group].sample_count` rows (arrow_schema.py:244-251). Missing samples are null rows, not absent rows.
- **Per-trajectory ordering:** the trajectory key is `(run_id, sensor_group, source, reference_frame, channel, name, component)`. Within it, both `frame_number` and `timestamp_s` must strictly increase across the whole file in write order (arrow_schema.py:138-145, 216-220).
- **Shared grid:** all trajectories in the same `(run_id, sensor_group, source, reference_frame)` context must carry an identical `(frame_number, timestamp_s)` sequence. This spans channel kinds and is checked by a SHA-256 chain over `struct.pack("<qd", frame, t)` (arrow_schema.py:146-151, 236-258).
- **Quaternions:** each (name, frame) must be unit length within 1e-5, or all four components null (arrow_schema.py:116-137, 198-211). Order is wxyz.
- **`OVERLAY_2D`:**
  - Undeclared names are rejected (observation_samples.py:127-128).
  - Visibility must be finite and in [0,1] (:129-130).
  - Coordinates must not be infinite (:131-133).
  - Points absent on a frame get **x,y null and visibility 0.0** (:135-139).
- **`BOXES_2D`:**
  - Only the first box per stage is used (:257-264).
  - A stage with no box on a frame gets **all six components null**, including `confidence` and `detector_ran` (:201-205).
  - A NaN corner becomes null (:216-217).
  - Confidence must be finite (:218-220).
  - `detector_ran` is 1.0 if any stage of that name ran the detector, else 0.0 (:222-224, 267-271; meaning at observation_inputs.py:243-245).
  - An undeclared stage name is rejected (:199-200).
- **`TIMESTAMPS`:** `value == timestamp_s`, `component="timestamp_s"`, `units="s"`, `reference_frame=null` (observation_samples.py:61-74).
- **`frame_number` origin:**
  - It is the video frame index. Observations must cover `range(video.start_frame, video.end_frame)` (core/reconstruction/recording_timing.py:27-28).
  - All cameras must agree on it (observation_publication.py:102-104).
  - `ObservationGroup.frame_numbers` is the first camera's `Observation.frame_number` (observation_inputs.py:103-106; skellytracker@03b9c1d:skellytracker/core/data_primitives/observation.py:29).
- **`timestamp_s` origin** (recording_timing.py:19-48; skellycam@169caf63:skellycam/core/timestamps/recording_timing_reader.py):
  - **Per camera:** taken from the skellycam camera timing CSV, columns `recording_frame_number` and `timestamp.from_recording_start.sec` (`TimingMethod.RECORDED`). The CSV must cover `range(frame_count)` (:61-71, 86-91). Without a sidecar, `offset_s + frame/fps` is used (`INFERRED_FROM_FPS`) with `offset_s=0.0` (:72-77; recording_timing.py:31).
  - **Group:** taken from the multiframe timing CSV, column `multiframe_number` (`RECORDED`). Otherwise it is the mean of the camera times per frame (`MEAN_CAMERA_TIMES`) (recording_timing.py:36-47).
  - **Which channels use which clock:**
    - `OVERLAY_2D`, `BOXES_2D` and capture `TIMESTAMPS` use the **per-camera** capture times (observation_publication.py:194-228).
    - Diagnostics, 3D series, reconstruction channels and the group `TIMESTAMPS` use the **synchronized** group times (:174-191, 229-234).
  - The clock is described as "recording-relative seconds" (:156). The tracker config also records `"timestamp_policy": "relative_recording_group_milliseconds"` in `execution` (core/pipeline/dataflow/recording_pipeline.py:237).
- **`TimingMethod` (StrEnum)** members: `RECORDED="recorded"`, `INFERRED_FROM_FPS="inferred_from_fps"`, `MEAN_CAMERA_TIMES="mean_camera_times"` (skellycam@169caf63:…/recording_timing_reader.py:34-37).

### 3.3 Naming: sensor groups and sources

- **`sensor_group`** = `camera_group:` + the first 6 hex characters of `sha256("|".join(sorted(camera_ids)))` (observation_inputs.py:40-52).
  - Used at core/pipeline/dataflow/video_sources.py:68 and core/tasks/mocap/posthoc_mocap_task.py:116.
  - The latter may instead reuse a saved `task_config.sensor_group`.
- **Sources** are namespaced so a reader can split on the first colon (reconstruction_samples.py:31-40):

| Source name | `Source.kind` | `definition` shape | Citation |
|---|---|---|---|
| `camera:<camera_id>` | camera | `CameraRecordingDefinition` (below) | observation_inputs.py:178-190 |
| `timing:<sensor_group>` | timing | `GroupTimingDefinition`: `{method: TimingMethod}` (`extra="forbid"`) | observation_inputs.py:193-197; observation_publication.py:121-122 |
| `keypoint_model:<model name>` | tracker | The tracker configuration (`PosthocMocapPipelineConfig` dump, plus `execution`) | observation_inputs.py:55-68; recording_pipeline.py:130, 236-242; posthoc_mocap_task.py:117, 124 |
| `object_detector:yolox-m` | tracker | Same configuration blob | observation_inputs.py:71-88; recording_pipeline.py:243-246; posthoc_mocap_task.py:118-119, 127-129 |
| `model:<model_id>` | instance | `ReconstructionSourceDefinition` (below) | reconstruction_samples.py:52-112 |

- `<model name>` is the RTMPose weights variant, or `MEDIAPIPE_WHOLEBODY_DEFINITION.name` for MediaPipe (posthoc_mocap_task.py:68-78).

**`CameraRecordingDefinition`** (observation_inputs.py:178-183; `extra="forbid"`). Playback validates the camera source definition against this model strictly (playback_queries.py:129-133). Writer values come from observation_publication.py:89-95.

| Field | Type | Writer value |
|---|---|---|
| `camera_id` | str | the video-group key: from the manifest `videos` map, otherwise the full filename (core/pipeline/posthoc/video_group_helper.py:384-401) |
| `video_filename` | str | `video.file_path.name` |
| `timing_method` | `TimingMethod` | the per-camera timeline's method |
| `nominal_fps` | float | `video.fps`, the container's reported FPS (video_group_helper.py:138) |
| `inferred_offset_s` | float | always `0.0` at c27fc299 (observation_publication.py:94) |

Playback additionally requires `nominal_fps > 0` and finite (playback_queries.py:54).

**`ReconstructionSourceDefinition`** (reconstruction_samples.py:52-88; `extra="forbid"`):

| Field | Type |
|---|---|
| `point_kind` | `RAW_KEYPOINTS_3D` or `KEYPOINTS_3D` (spatial_points.py:21) |
| `model_id` | str |
| `tracker` | str (tracker source name) |
| `scale_reference_name` | str |
| `landmark_names` | `tuple[str]` |
| `segment_origins` | `dict[segment, landmark]` |
| `segment_parents` | `dict[segment, segment \| None]` |
| `joint_angle_names` | `dict[joint, (str, str, str)]` |

Rules (:73-88):
- identity fields are nonempty;
- `segment_parents` and `segment_origins` have the same key set;
- every origin is a declared landmark;
- every non-null parent is a declared segment.

Readers that depend on these source shapes:
- `read_saved_observations` reads `nominal_fps`, `timing_method` and `video_filename` (saved_observations.py:56-69), and the group `method` (:110).
- `read_saved_observations` re-validates the OVERLAY_2D source definition as `PosthocMocapPipelineConfig` (:40-46).

### 3.4 Reference frames (`RunDescriptor.reference_frames`, free JSON)

| Name | Shape | Citation |
|---|---|---|
| `camera:<camera_id>:image` | `ImageReference`: `{camera_id: str, calibration_camera_id: str\|null, width: int, height: int}` (`extra="forbid"` when built) | observation_inputs.py:167-175; observation_publication.py:96-101 |
| `calibrated_world` / `camera_plane` | `SpatialReference`: `{name, basis="blender_x_right_y_forward_z_up", units, alignment: ReferenceAlignmentDescriptor\|null, additional_transform: ReferenceTransform\|null}` | spatial_points.py:48-75 |
| `<model_id>:segment_parents` | `ParentRotationReference`: `{parents: dict[str, str\|null], root_reference: str}`. Parent-relative rotations; roots use the named world frame. | reconstruction_samples.py:123-133, 325-329 |

Details for the camera image reference:
- `width` and `height` are the video dimensions. Every observation's `image_size` must equal `(video.height, video.width)` (observation_publication.py:105-108; `image_size` is (height, width) per skellytracker@03b9c1d:…/observation.py:30).
- No range check on pixel coordinates was found.
- On merge, `calibration_camera_id` is carried over from the previous run if the new value is null (observation_publication.py:318-321). It is ignored when comparing retained frames (checkpoint_publication.py:119-126).

Details for the spatial references:
- `SpatialReferenceName` members: `CALIBRATED_WORLD="calibrated_world"`, `CAMERA_PLANE="camera_plane"` (spatial_points.py:24-26).
- `SpatialBasis` has one member: `BLENDER="blender_x_right_y_forward_z_up"` (:29-30).
- Units are enforced: `camera_plane` ⇒ `px`, otherwise `mm` (:55-64).
- Writers choose `camera_plane`/px for 1 camera and `calibrated_world`/mm for ≥2 (:67-75; recording_pipeline.py:265).

`ReferenceAlignmentDescriptor` (spatial_points.py:33-37):
- `outcome`: one of `PRESERVED_REFERENCE="preserved_reference"`, `DISABLED="disabled"`, `FOOT_SUPPORT="foot_support"`, `BODY_REFERENCE="body_reference"`, `INSUFFICIENT_EVIDENCE="insufficient_evidence"`. The legacy value `"explicit_ground"` maps to `preserved_reference` (skellyforge@f5404db:skellyforge/core/biomechanics/reference_alignment.py:22-34).
- `rotation_wxyz`: 4 floats
- `translation_mm`: 3 floats
- `anchor_segment`: `str \| None`

`ReferenceTransform` (core/reconstruction/reference_transform.py:10-27): `matrix`, 16 floats, row-major homogeneous, X' = RX + t. Bottom row [0,0,0,1]; R orthonormal with det +1 (tolerance 1e-5); `extra="forbid"`; no inf or NaN.

### 3.5 Coordinate frames, axes and units for 3D

- **Saved 3D points use the Blender basis:** +X right, +Y forward, +Z up, right-handed.
  - `SpatialReference.basis` default (spatial_points.py:50).
  - Triangulated points are converted from the calibration convention (`ros`: +X forward, +Y left, +Z up) to the default (`blender`) before saving (core/reconstruction/posthoc_reconstruction.py:143-145; core/reconstruction/coordinate_conventions.py:8-10; skellyforge@f5404db:skellyforge/definitions/coordinate_systems/coordinate_systems.yaml:23-45).
- **Units:** mm for multi-camera, px for single-camera `camera_plane` (spatial_points.py:55-75).
- **`camera_geometry` extrinsics:** [inferred] stored in the calibration (`ros`) convention, in mm. Alignment code converts reconstruction points to calibration coordinates before applying camera extrinsics (core/reconstruction/mocap_alignment.py:65-71). Applied transforms are converted with `RECONSTRUCTION_TO_CALIBRATION` (calibration_transform.py:87-98). The recording guide says "Recording adds no camera model or basis label" (core/recording/recording_guide.md:71-72).
- **Skeleton coordinate system:** the Blender stage check requires `skeleton.coordinate_system == "blender"` and basis `blender_x_right_y_forward_z_up` (recording_status.py:247-250).
- **Pixel origin and half-pixel convention: not found.** I searched freemocap `.py`/`.ts`/`.md` and skellytracker `.py` for "top-left", "upper-left", "pixel origin", "pixel center".

### 3.6 `name` / `component` contents per kind

- **`OVERLAY_2D` names:**
  - Prefixed `"<stage>.<point>"` by skellytracker's stage-tree flattening (skellytracker@03b9c1d:…/observation.py:34-60).
  - Ordered by first appearance across all frames and cameras (recording_pipeline.py:240-242; posthoc_mocap_task.py:124-126).
  - Readers split on the first `.` to rebuild stages (saved_observations.py:84-88).
- **3D keypoint names (`RAW_KEYPOINTS_3D`/`KEYPOINTS_3D`):** the stage prefix is stripped (posthoc_reconstruction.py:146).
- **Model channels:** names are skeleton landmark or segment names. `JOINT_ANGLES` names are the `EulerConvention.angle_names` of each joint, concatenated, and must be unique across joints (Channel validator; reconstruction_samples.py:235-239).
- **`BOXES_2D` names:** top-level detection stage names (`observation.stages`, recording_pipeline.py:244-245). The encoder walks the full stage tree (observation_samples.py:248-254).
- **Components:** see §3.1.

### 3.7 Runs

- **One file holds all retained runs.** Every row carries `run_id`, and `selected_run_id` names the run to show (RECORDING_CONTRACT.md:98-99).
- **A fresh file** gets `runs={target: run}` with `selected_run_id=target` (observation_publication.py:243-248). The first run is 0: "A recording without saved results starts at Run 0" (run_save_session.py:28-29).
- **New-run allocation** (`RunSaveSession.resolve`, `mode='new_run'`):
  - target = `max(runs)+1`, bumped past any `run-<n>` directories under `exports/`, the recording folder and `annotated_videos` (run_save_session.py:30-37);
  - the ID is reserved by `mkdir exports/run-<target>` (:38-44).
  - `build_execution_plan` uses `max(runs)+1` when `keep` is set, else the base ID (core/pipeline/posthoc/stage_execution_plan.py:90).
- **Overwrite and keep:**
  - Other runs are copied verbatim (checkpoint_publication.py:63-69).
  - The target run is replaced by `retained` + `computed` (:70-88, 175-182).
  - The base run's channels, fits, checkpoints and provenance for invalidated stages and groups are dropped (stage_execution_plan.py:97-127).
  - Many preservation checks apply (checkpoint_publication.py:101-174).
  - `selected_run_id` is always set to the target run (:179).
- **Realtime vs posthoc: not distinguished.** There is no run-type field in the descriptor. No realtime writer of `_data.parquet` was found: I grepped `core/pipeline/realtime`, `core/streaming` and `api` for `parquet`/`publish_*`. All publishers are posthoc: `publish_posthoc_observations` (recording_pipeline.py:256, 284, 295, 363; scientific_recording.py:224; posthoc_mocap_task.py:138, 288, 323) and `publish_checkpoint` (saved_stage_processing.py:206; numerical_checkpoint.py:114). The only execution identity is `processing[group].stage_provenance` (attempt_id, recorded_at, software).

### 3.8 Validation summary

**Writer** (all enforced in-process before the file is replaced):
- schema equality (arrow_schema.py:66-67) and no nulls in required columns (:68-70);
- declared channel and name, and units match (:92-104);
- finite values and nonnegative frames (:105-115);
- quaternion contiguity and unit norm (:116-137);
- strictly increasing per trajectory (:138-145);
- exact sample_count coverage and a shared grid per context (:233-258);
- `recording_id` == folder (parquet_writer.py:44-45);
- the descriptor's pydantic validators (§2.2).

**Reader:**
- schema equality, key present, descriptor validates (parquet_reader.py:38-45);
- `recording_id == parent folder name` in `recording_view` (recording_view.py:46-47).

The read path does not re-run `SampleValidator`. Republishing a file through `publish_checkpoint` does re-validate every row (checkpoint_publication.py:183-194 → parquet_writer.py:46-52).

---

## 4. Skeleton and topology

### 4.1 Where keypoint names live at c27fc299

| What | Where |
|---|---|
| Tracker keypoint names | `RecordedModel.tracker_keypoint_names` (recording_model.py:20) |
| Model landmarks | `RecordedModel.skeleton.landmarks[*].name` (skellyforge@f5404db:…/skeleton_snapshot.py:27-33, 127) |
| Landmark edges for drawing | `skeleton.landmark_connections[*].pairs` (:132; landmark_grouping.py:92-133) |
| Segment and joint tree | `skeleton.segments`, `skeleton.joints`, `rest_pose.parents` |
| Per-run and channel names | `Channel.names` and `ReconstructionSourceDefinition.landmark_names` / `segment_origins` / `segment_parents` |
| Tracker → landmark mapping | `RecordedModel.mappings` |

**No tracker-keypoint connection list exists at c27fc299.**

### 4.2 `tracker_connections` (sfn26)

- **Field:** `sfn26:freemocap/core/recording/data_descriptors/recording_model.py:29`, `tracker_connections: tuple[tuple[str, str], ...] = ()`.
- **Meaning:** "Tracker-authored display edges, preserved in recordings" (`sfn26:freemocap/core/skeletons/tracked_skeleton_bundle.py:81`). Each pair is two tracker keypoint names, in the same unprefixed namespace as `tracker_keypoint_names`. They come from the skellytracker detector YAML schemas via `tracker_profile(detector_type).connections` (`sfn26:freemocap/core/skeletons/standard_human_skeleton.py:58-59`).
- **Source in skellytracker** (`skellytracker remotes/upstream/sfn26 (2d356a6c):skellytracker/core/io/tracker_profiles.py:16-21, 61-93`):
  - hand edges are prefixed `<side>_hand_…` (:69-71);
  - `rtmw_mediapipe_hands` keeps only body edges whose endpoints survive (:80-83).
- **Validation:** none for this field. It is not checked against `tracker_keypoint_names` in `RecordedModel.validate_inputs` (`sfn26:…/recording_model.py:58-79`) or `TrackedSkeletonBundle.__post_init__` (`sfn26:…/tracked_skeleton_bundle.py:109-111`).
- **Serialization:** omitted from JSON when empty (`sfn26:…/recording_model.py:48-49`).

### 4.3 Other descriptor and format differences, c27fc299 → sfn26

Unchanged at sfn26 (byte-identical or absent from the diff): `arrow_schema.py` (`SAMPLE_SCHEMA`, `DESCRIPTOR_KEY`, validator), `parquet_writer.py`, `shared_file.py`, `channel_kind.py`, `sample_conventions.py`, `stage_provenance.py`, `scale_fit.py`, `spatial_points.py`, `camera_model.py`, `recording_info.py`.

| Change | Citation | Format impact |
|---|---|---|
| `RecordedModel` gains `object_geometry: RigidObjectGeometry \| None = None`, omitted when None. `RigidObjectGeometry` (`extra="forbid"`, no inf/NaN): `feature_names`, `segment_name`, `source_mesh_units`, `mesh_sha256: str\|None`, `reference_unit_mm >0`, and three 16-float row-major matrices `object_to_segment_reference`, `source_mesh_to_segment_reference`, `segment_reference_to_source_mesh`. | sfn26:…/recording_model.py:30, 44-45; sfn26:freemocap/core/skeletons/rigid_object_geometry.py:6-17 | New optional descriptor key. c27fc299 rejects it (`extra="forbid"`). [inferred] |
| `RecordedModel` gains `tracker_stage_path: tuple[str, ...] \| None = None`, omitted when None. Hand bundles use `("hands",)`. | sfn26:…/recording_model.py:31, 46-47; sfn26:…/standard_human_skeleton.py:88 | New optional key; rejected by c27fc299. [inferred] |
| The serializer pops `skeleton.presentation` when None, so skellyforge sfn26's `SkeletonSnapshot` has a `presentation` field. I did not inspect it: no sfn26 skellyforge checkout is available locally. | sfn26:…/recording_model.py:50-52 | Possibly a new nested key |
| `ReconstructionSourceDefinition.joint_angle_names` changes from `tuple[str,str,str]` to `tuple[str, ...]` | sfn26:freemocap/core/recording/sample_encoding/reconstruction_samples.py:60 | `model:` source definitions may carry ≠3 angle names |
| `Channel.tensor_layout()` method added; nothing new is serialised | sfn26:…/recording_descriptor.py:50-62 | None |
| Timing and box encoders now go through `ChannelSeries` (frame-major columnar). Box semantics unchanged: absent box ⇒ all six components null. | sfn26:…/observation_samples.py:43-73, 133, 218-267 | Same column layout; row order inside box batches is frame→name→component as before [inferred] |
| `SeriesSampling` validates timing via skellyforge `SampleTiming` | sfn26:…/channel_series.py:22-44 | None on disk [inferred] |
| Checkpoint republish reads via `selected_batches`/`recording_view`. The model-preservation rule is relaxed: a fit-only model may change `anchor_segment_name`. | sfn26:…/checkpoint_publication.py (diff) | Same rows; slightly different acceptance rule |
| The UI reader moved to an SDK (next row); `freemocap-ui/.../playback-parquet.ts` only re-exports `@freemocap/client/recording` | sfn26:freemocap-ui/src/services/recording/playback-parquet.ts:1-2 | n/a |
| SDK reader: `packages/freemocap-client/src/recording/playback-parquet.ts` | sfn26:packages/freemocap-client/src/recording/playback-parquet.ts | n/a |
| The SDK reader checks physical types: `run_id`/`frame_number` INT32\|INT64, `timestamp_s`/`value` FLOAT\|DOUBLE, others BYTE_ARRAY | sfn26:packages/freemocap-client/src/recording/playback-parquet.ts:4-5, 35-44 | Looser than the Python reader |
| skelly* dependencies follow branch `sfn26` | sfn26:pyproject.toml:64-66 | — |

---

## 5. Readers of the Parquet in this repo (c27fc299)

| Entry point | What it needs |
|---|---|
| `parquet_reader.read_metadata` / `metadata_from_schema` (core/recording/parquet_storage/parquet_reader.py:22-45) | Exact schema and the `freemocap.recording` key |
| `parquet_reader.read_batches` (:59-76) | `run_id` and `sensor_group`. The run and groups must be declared. Iterates per row group (:48-56). |
| `recording_view` (parquet_storage/recording_view.py:37-48) | Schema and descriptor; `recording_id == folder`. Revision = sha256 of dev:ino:size:mtime. |
| `playback_manifest` (core/recording/playback_queries.py:86-157) | All rows with `channel=="TIMESTAMPS"` and `component=="timestamp_s"`: `run_id`, `sensor_group`, `source`, `frame_number`, `timestamp_s`. Equal frames must have equal times. It also validates camera sources as `CameraRecordingDefinition` and instance sources as `ReconstructionSourceDefinition`. |
| `read_saved_channel` (core/recording/result_processing/saved_reconstruction.py:200-260) | Filters on `run_id`, `sensor_group`, `source`, `channel`, `reference_frame` (null-aware), and reads `frame_number`, `timestamp_s`, `name`, `component`, `value` |
| `read_saved_observations` (saved_observations.py:29-111) | Exactly one `OVERLAY_2D` tracker source per group; `"<stage>.<point>"` names; `camera:<id>` sources with `nominal_fps`, `timing_method`, `video_filename`; image references with `camera_id`, `width`, `height`; one `TIMESTAMPS ("synchronized",)` channel whose source has `method`; consecutive frames |
| `read_saved_reconstruction` (saved_reconstruction.py:84-190) | `RAW_KEYPOINTS_3D` or `KEYPOINTS_3D` per policy (:38-44, 112) |
| Tall CSV export (core/recording/exports/tall_csv.py:45-95) | `recording_view`; iterates all batches |
| Wide/scientific export (core/recording/exports/wide_csv.py:150-155, 361-366) | Maps `RAW_KEYPOINTS_3D`, `KEYPOINTS_3D`, `LANDMARKS_3D` to tables (:32-34) |
| Recording health report (core/diagnostics/recording_health_report.py:95-113) | `metadata_from_schema`; the diagnostic kinds `REPROJECTION_ERROR`, `RECONSTRUCTION_COVERAGE`, `TRIANGULATION_WEIGHTS`, `RIGID_BODY_RESIDUALS` (:26-29) |
| Blender stage status (system/recording_status/recording_status.py:222-250) | Raw JSON: `schema_version==1`; selected run has exactly one `model:standard_human` `LANDMARKS_3D` channel, plus matching `SEGMENT_ORIGINS` and `ROTATIONS_WORLD`; reference `basis=="blender_x_right_y_forward_z_up"`; `models.standard_human.skeleton.coordinate_system=="blender"` |
| HTTP serving (api/http/playback/playback_router.py:632-647) | Serves the file via `recording_view` |
| Dataset tools (tools/datasets/preparation.py:128; stage_matrix.py:44; concurrency_benchmark.py:53; storage_batch_benchmark.py:86) | Dev tooling |

**JS/TS reader: `freemocap-ui/src/services/recording/playback-parquet.ts:1-92`.**
- Libraries: `hyparquet` ^1.25.6 and `hyparquet-compressors` ^1.1.2, plus zod (freemocap-ui/package.json:40-41, 53).
- It reads all 11 columns per row group (:6-12, 37-45).
- It decodes only the `RecordingChannelKind` "scene" kinds: `MAPPED_KEYPOINTS_3D`, `RAW_KEYPOINTS_3D`, `LANDMARKS_3D`, `SEGMENT_ORIGINS`, `ROTATIONS_WORLD`, `ROTATIONS_LOCAL`, `DERIVED_POINTS`, `SEGMENT_LENGTHS`, `MODEL_SCALE` (freemocap-ui/src/services/recording/playback-data.ts:7-12).
- It requires:
  - `run_id` and `frame_number` to be nonnegative integers (coerced); `reference_frame` and `value` may be null (:7-11);
  - name, component and units to match the manifest channel (:60-63);
  - no duplicate (frame, name, component) and a consistent time per frame (:64-72);
  - a complete grid per frame (:84);
  - strictly increasing timestamps (:85).
- Null values become NaN in memory (:71).
- It takes channel declarations from the playback manifest (HTTP), not from the Parquet key directly.

---

Not checked: I read skellyforge, skellytracker and skellycam only at the pinned revisions and only as far as each nested type, so `PosthocFilterConfig`, `GapFillingReport` and the camera-fitness entry shape are not inventoried, and sfn26's skellyforge `presentation` field is unseen. I ran no code: the pyarrow defaults (dictionary page encoding, statistics, row-group cap, `ARROW:schema`) and pydantic JSON behaviour are marked [inferred], not verified against a written file.

Main-session spot-check (2026-11-16): `SAMPLE_SCHEMA` (arrow_schema.py:15-30), `CameraRecordingDefinition` (observation_inputs.py:178-183) and sfn26 `tracker_connections` (recording_model.py:29) match the source.
