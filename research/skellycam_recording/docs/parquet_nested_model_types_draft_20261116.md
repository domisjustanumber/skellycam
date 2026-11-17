# Nested model types for `parquet-descriptor.md`: draft, sources, disagreements, example

## 0. Summary

- None of the thirteen types is defined in the freemocap repo at c27fc299, and only one at sfn26. Eleven are stdlib dataclasses in **skellyforge** and one is in **skellytracker**. `RigidObjectGeometry` is a pydantic model that exists only on freemocap `sfn26`.
- Five further types are referenced and not defined in the spec part: `EulerConvention`, `RotationQuaternion`, `ComLandmarkWeight`, the `Handedness` enum (integer valued), and the mapping-entry forms of `TrackerMappingSnapshot.entries`. The draft includes them.
- The example in section 4 loads, round-trips byte-equal and restores (`to_bundle()`) against the real `RecordedModel` at c27fc299 with the lock-pinned skellyforge and skellytracker.
- The sfn26 form could not be validated. No skellyforge `sfn26` checkout exists on this machine, so `SkeletonSnapshot.presentation` is unknown.

Revisions read:

| Repo | Revision | Where read |
|---|---|---|
| freemocap | `c27fc29902220307c4ecea59c2a22faf5ce7aef2` | `git show` in `c:\Users\Dom\GitHub\freemocap\freemocap` |
| freemocap | `upstream/sfn26` = `ca0c17ccaca2ea0d5bd39b30e5b92976004a1b05` (2026-11-14) | same |
| skellyforge | `f5404db5791c69afedf95652ef7cebca316e5ec0` (pinned in `c27fc299:uv.lock:2647`) | uv cache checkout `C:\Users\Dom\AppData\Local\uv\cache\git-v0\checkouts\9974341064142b12\f5404db` |
| skellytracker | `03b9c1dc10dfa14fd49ca15b35d17ac71c569345` (pinned in `c27fc299:uv.lock:2676`) | `git show` in `c:\Users\Dom\GitHub\freemocap\skellytracker` |
| skellytracker | `upstream/sfn26` = `2d356a6c41f831484251677050fafb2576193060` | same |

Two kinds of rule appear in the code. I kept them apart in section 2 and merged them as "must" in the draft:
- **Load rules**: the descriptor is refused when freemocap parses it (pydantic and dataclass `__post_init__`).
- **Restore rules**: the descriptor loads, but `RecordedModel.to_bundle()` fails. Most cross-reference rules are of this kind.

---

## 1. Drafted section (replaces the paragraph at lines 243-249)

```markdown
## Nested types of `RecordedModel`

Each type of this section is closed. A writer must write each member, also when the member is null
or empty, except where a row says "omitted when null". The source of each type is skellyforge at
f5404db, skellytracker at 03b9c1d or freemocap `sfn26`.

A name is text with 1 or more characters. In this section, "landmark" is the `name` of an item of
`skeleton.landmarks`, "segment" is the `name` of an item of `skeleton.segments` and "joint" is the
`name` of an item of `skeleton.joints`.

### `SkeletonSnapshot` (closed)

| Member | Type | Rule |
|---|---|---|
| `name` | text | 1 or more characters |
| `landmarks` | array of `LandmarkSnapshot` | Each `name` is different |
| `segments` | array of `SegmentSnapshot` | 1 or more. Each `name` is different |
| `joints` | array of `JointSnapshot` | Each `name` is different. Can be `[]` |
| `chains` | array of `ChainSnapshot` | Each `name` is different. Can be `[]` |
| `landmark_groups` | array of `LandmarkGroup` | Each `name` is different. Can be `[]` |
| `landmark_connections` | array of `LandmarkConnectionGroup` | Each `name` is different. Can be `[]` |
| `derived_quantities` | array of text | Each item is one of `inertia`, `extrapolated_center_of_mass`, `center_of_pressure`, `centroidal_moment_pivot`, `roll_resolution`. The writer sorts the items. Can be `[]` |
| `coordinate_system` | text | 1 or more characters. freemocap writes `blender` |

Reference rules:
- each landmark is in the `landmarks` of exactly one segment, and its `segment` is the name or an
  alias of a segment;
- no two landmarks have the same name or alias;
- each point name of each `frame` and `observation_frame` is a landmark;
- each name in `landmark_groups` and `landmark_connections` is a landmark;
- when `joints` is not empty, each segment is the `child` of at most one joint, exactly one segment
  is the `child` of no joint, and the joints make no cycle;
- when `derived_quantities` contains `inertia`, no segment has a null `anatomical_segment`.

### `LandmarkSnapshot` (closed)

| Member | Type | Rule |
|---|---|---|
| `name` | text | 1 or more characters |
| `definition` | text | 1 or more characters. The anatomical description of the point |
| `position` | 3 floats | x, y, z. The rest position in the local frame of the segment `segment` |
| `segment` | text | The segment that owns the landmark |
| `aliases` | array of text | Other names of the landmark. Each is different, not empty and not `name`. Can be `[]` |

### `SegmentSnapshot` (closed)

| Member | Type | Rule |
|---|---|---|
| `name` | text | 1 or more characters |
| `landmarks` | array of text | The landmarks that the segment owns |
| `frame` | `FrameSnapshot` | The local frame of the segment. Its `primary_point` is in `landmarks`. Its `origin` is in `landmarks` or is a landmark of the parent segment |
| `aliases` | array of text | Other names of the segment. Each is different, not empty and not `name`. Can be `[]` |
| `anatomical_segment` | text or null | The anatomical mass segment of the rigid body |
| `observation_frame` | `FrameSnapshot` | Omitted when null. When present, its `secondary_point` and `secondary_axis` are not null |

When the `origin` of `frame` is in `landmarks`, the `position` of that landmark is [0, 0, 0].

### `FrameSnapshot` (closed)

| Member | Type | Rule |
|---|---|---|
| `origin` | text | The landmark at the origin of the frame |
| `primary_point` | text | The landmark on the primary axis. It is not `origin` |
| `primary_axis` | [index, sign] | 2 integers. `index` is 0 (x), 1 (y) or 2 (z). `sign` is 1 or -1 |
| `secondary_point` | text or null | The landmark near the secondary axis. It is not `origin` and not `primary_point` |
| `secondary_axis` | [index, sign] or null | Its `index` is not the `index` of `primary_axis` |
| `handedness` | integer | 1 (right-handed) or -1 (left-handed) |

`secondary_point` and `secondary_axis` are both null or both not null. `handedness` is an integer,
not text.

### `JointSnapshot` (closed)

| Member | Type | Rule |
|---|---|---|
| `name` | text | 1 or more characters |
| `parent` | text | A segment |
| `child` | text | A segment. It is not `parent` |
| `connect_at` | text | A landmark of the `landmarks` of the parent segment. The origin of the child is on it |
| `joint_type` | text | `ball`, `hinge`, `universal` or `fixed` |
| `convention` | `EulerConvention` | |

### `EulerConvention` (closed)

| Member | Type | Rule |
|---|---|---|
| `sequence` | text | 3 letters, each `x`, `y` or `z`. Two adjacent letters are different |
| `angle_names` | 3 texts | Each is different. One name for each letter of `sequence`, in order |
| `zero_offsets` | 3 floats | Radians. freemocap adds them after the decomposition. Default [0.0, 0.0, 0.0] |

### `ChainSnapshot` (closed)

| Member | Type | Rule |
|---|---|---|
| `name` | text | 1 or more characters |
| `segments` | array of text | 3 or more segments, proximal first |
| `joints` | array of text | Joints, in the same order. The number of items is the number of `segments` minus 1 |

### `LandmarkGroup` (closed)

| Member | Type | Rule |
|---|---|---|
| `name` | text | 1 or more characters |
| `landmark_names` | array of text | 1 or more landmarks; each different |
| `tags` | array of text | Each is different and not empty. The most specific tag is first. Can be `[]` |

### `LandmarkConnectionGroup` (closed)

| Member | Type | Rule |
|---|---|---|
| `name` | text | 1 or more characters |
| `pairs` | array of pairs of text | 1 or more. Each pair is 2 different landmarks |
| `tags` | array of text | Each is different and not empty. Can be `[]` |

### `RestPoseSnapshot` (closed)

| Member | Type | Rule |
|---|---|---|
| `name` | text | |
| `root_segment_name` | text | A segment |
| `parents` | map of segment to segment or null | One key for each segment. Exactly one value is null: that of `root_segment_name` |
| `connect_ats` | map of segment to landmark | One key for the `child` of each joint |
| `orientations` | map of segment to `RotationQuaternion` | One key for each segment. The rotation of the segment relative to its parent |

For each joint, `parents[child]` is its `parent` and `connect_ats[child]` is its `connect_at`.

### `RotationQuaternion` (closed)

`w`, `x`, `y`, `z` (floats). The norm is 1, to 1e-9.

### `TrackerMappingSnapshot` (closed)

| Member | Type | Rule |
|---|---|---|
| `entries` | map of landmark to a mapping entry | Can be `{}` |
| `prefix` | text or null | When it is not null, freemocap adds it before each keypoint name of `entries` |
| `known_tracker_keypoints` | array of text or null | The keypoint names that the tracker can give. The writer sorts them |
| `passthrough` | boolean | When true, each tracker keypoint is a landmark of the same name |

- When `passthrough` is true, `entries` is `{}` and `known_tracker_keypoints` has 1 or more items.
- When `known_tracker_keypoints` is not null, each keypoint name of `entries`, after `prefix`, is in
  it.

A mapping entry has one of four forms:

| Form | JSON | Meaning |
|---|---|---|
| Name | text | The landmark is that keypoint |
| Mean | array of text, 1 or more | The landmark is the mean of the keypoints |
| Weighted sum | map of keypoint to float, 1 or more | The landmark is the weighted sum |
| Offset | an object with `form` equal to `anatomical_offset` | The landmark is off the surface (below) |

The offset form has these members:

| Member | Type | Rule |
|---|---|---|
| `form` | text | `anatomical_offset` |
| `origin` | array of text | 1 or more keypoints. Their mean is the origin of the frame |
| `frame` | map of axis name to `{from, to, kind}` | Exactly 2 axes. `from` and `to` are a keypoint or an array of 1 or more keypoints. `kind` is `exact` for one axis and `approximate` for the other |
| `offset` | map of axis name to float | 1 or more. Each value is a ratio of the reference length |
| `reference_length` | `{from, to}` | Each is a keypoint or an array of 1 or more keypoints |

### `CenterOfMassDefinitions` (closed)

`definitions` (a map of text to `SegmentComDefinition`, 1 or more items). Each key is the `name` of
its value.

### `SegmentComDefinition` (closed)

| Member | Type | Rule |
|---|---|---|
| `name` | text | The anatomical segment name, with no side |
| `proximal` | text | The landmark at the proximal end |
| `distal` | text | The landmark at the distal end |
| `weights` | array of `ComLandmarkWeight` | 1 or more. The sum of the weights is 1.0, to 1e-6 |
| `sided` | boolean | Default false |

When `sided` is false, the definition gives one segment name, `name`, and its landmark names are
used as written. When `sided` is true, the definition gives two segment names, `left_<name>` and
`right_<name>`, and each landmark name gets the same prefix (`left_` or `right_`). Each landmark
name that results is a landmark of the skeleton. The keys of `RecordedModel.segment_masses` are
exactly the segment names that all definitions give.

### `ComLandmarkWeight` (closed)

`landmark` (text) and `weight` (float, more than 0).

### `RigidObjectGeometry` (closed)

From `sfn26`.

| Member | Type | Rule |
|---|---|---|
| `feature_names` | array of text | |
| `segment_name` | text | |
| `source_mesh_units` | text | The units of the original mesh |
| `mesh_sha256` | text or null | The member is always present |
| `reference_unit_mm` | float | More than 0 |
| `object_to_segment_reference` | 16 floats | Row-major 4 × 4. Input: object millimetres. Output: segment reference units |
| `source_mesh_to_segment_reference` | 16 floats | Row-major 4 × 4. Input: original mesh units. Output: segment reference units |
| `segment_reference_to_source_mesh` | 16 floats | Row-major 4 × 4 |

A matrix multiplies a homogeneous column vector.
```

Notes on the draft, not for the spec text:
- I did not add a `presentation` row to `SkeletonSnapshot`. See 3.6.
- The "Reference rules" of `SkeletonSnapshot`, the `RestPoseSnapshot` cross-rules, the `joint_type` enum, the `primary_axis` value range, the chain length, and the two `TrackerMappingSnapshot` bullets are **restore** rules in the code, not load rules. A descriptor that breaks them still loads at c27fc299.
- Text rules the code does not enforce, which I wrote as descriptions only: `LandmarkSnapshot.name` and `SkeletonSnapshot.name` non-empty at load (empty names are accepted at load, refused at restore), the meaning of `RigidObjectGeometry.feature_names` and `segment_name`.
- The STE wording is my best effort; it is not checked by a tool.

---

## 2. Source of each field

Paths are relative to each repo root. "sf" = skellyforge@f5404db, "st" = skellytracker@03b9c1d, "fmc" = freemocap.

**SkeletonSnapshot** — sf `skellyforge/core/skeleton/skeleton_snapshot.py`
- `name` :126, `landmarks` :127, `segments` :128, `joints` :129, `chains` :130, `landmark_groups` :131, `landmark_connections` :132, `derived_quantities` :133, `coordinate_system` :134
- unique names in each of the six arrays (load): :240-251
- `derived_quantities` sorted by the writer: :296
- restore rules, sf `skellyforge/core/skeleton/skeleton_definition.py`: name non-empty :121-122; coordinate_system non-empty :123-126; 1+ segments :127-128; landmark `segment` known :148-161; each landmark owned once :163-188; frame points exist :190-209; group and connection names exist :214-235; allowed `derived_quantities` :55-62, :247-258; `inertia` needs `anatomical_segment` :259-270; joint topology (one parent joint, one root, no cycle) :696-719; default `coordinate_system` "blender" :114

**LandmarkSnapshot** — sf `skeleton_snapshot.py`
- `name` :29, `definition` :30, `position` :31, `segment` :32, `aliases` :33
- restore, sf `skellyforge/core/skeleton/components/anatomical_landmark.py`: name, definition, segment non-empty :47-52; alias rules :53 and `components/naming.py:40-52`; "rest position in the owning segment's local frame" :30-31

**SegmentSnapshot** — sf `skeleton_snapshot.py`
- `name` :98, `landmarks` :99, `frame` :100, `aliases` :101, `anatomical_segment` :102, `observation_frame` :104 (default None)
- `observation_frame` omitted when null: fmc c27fc299 `freemocap/core/recording/data_descriptors/recording_model.py:38-40` (sfn26: :53-55)
- restore, sf `skellyforge/core/skeleton/components/rigid_body_segment.py`: observation frame needs two axes :101-105; alias rules :107; primary point in own landmarks :129-134; own origin at zero :142-150 (tolerance `MINIMUM_VECTOR_NORM` = 1e-9, `core/math/geometry/numeric_tolerances.py:13`); snake-case segment name :106 (validator body not read)

**FrameSnapshot** — sf `skeleton_snapshot.py`
- `origin` :61, `primary_point` :62, `primary_axis` :63, `secondary_point` :64, `secondary_axis` :65, `handedness` :66
- axis values: sf `core/math/geometry/orthonormal_basis/spatial_axis.py:24-30`; handedness values: `orthonormal_basis/handedness.py:22-26`
- restore, sf `orthonormal_basis/reference_frame_definition.py`: secondary both-or-neither :52-57; origin differs from primary :58-62; axes differ :82-86; points differ :87-95

**JointSnapshot** — sf `skeleton_snapshot.py`
- `name` :109, `parent` :110, `child` :111, `connect_at` :112, `joint_type` :113, `convention` :114
- restore, sf `skellyforge/core/skeleton/linkage/joint_definition.py`: name non-empty :94-95; parent differs from child :96-99; joint types :13 and :100-104; `connect_at` owned by parent :105-110

**EulerConvention** — sf `linkage/joint_definition.py`
- `sequence` :35, `angle_names` :36, `zero_offsets` :37
- load rules: sequence :44 and sf `core/math/kinematics/euler_sequence.py:57-80`; default angle names `<axis>_angle` :46-48; three distinct names :49-53; three offsets :54-58; "radians added after decomposition" :30-32

**ChainSnapshot** — sf `skeleton_snapshot.py`
- `name` :119, `segments` :120, `joints` :121
- restore, sf `skellyforge/core/skeleton/chain/kinematic_chain.py`: name :41-42; 3+ segments :22, :43-47; joints = segments − 1 :48-53

**LandmarkGroup** — sf `skellyforge/core/skeleton/components/landmark_grouping.py`
- `name` :67, `landmark_names` :68, `tags` :69; load rules :72-88; tag rules :35-50

**LandmarkConnectionGroup** — same file
- `name` :107, `pairs` :108, `tags` :109; load rules :112-133

**RestPoseSnapshot** — sf `skeleton_snapshot.py`
- `name` :353, `root_segment_name` :354, `parents` :355, `connect_ats` :356, `orientations` :357
- restore rules :370-383; "parent-relative rotation" sf `skellyforge/core/skeleton/pose/rest_pose.py:132`

**RotationQuaternion** — sf `skellyforge/core/math/geometry/rotation_quaternion.py`
- `w` :88, `x` :89, `y` :90, `z` :91; finite and unit (load) :93-107; tolerance 1e-9 `numeric_tolerances.py:13, :21`

**TrackerMappingSnapshot** — st `skellytracker/core/io/tracker_mapping.py`
- `entries` :93 (`MappingEntry` :69), `prefix` :94, `known_tracker_keypoints` :95, `passthrough` :96
- written sorted :234; entry forms documented :5-52
- restore rules: passthrough :178-192; empty list :200-204; empty dict :212-215; other type :217-221; known-keypoint check :223-231 with prefix :277-304; offset form :512-585
- unchanged at st sfn26 (2d356a6c): the diff of this file touches only `from_yaml` (:65, :328)

**CenterOfMassDefinitions** — sf `skellyforge/core/biomechanics/center_of_mass.py`
- `definitions` :101; load rules :103-111; `all_segment_names` :123-132; landmark check (restore) :180-195

**SegmentComDefinition** — same file
- `name` :54, `proximal` :55, `distal` :56, `weights` :57, `sided` :58; load rules :60-73; sided expansion :75-94; tolerance `FRACTION_SUM_TOLERANCE` = 1000 × 1e-9, sf `skellyforge/core/biomechanics/__init__.py:25`

**ComLandmarkWeight** — same file: `landmark` :38, `weight` :39

**RigidObjectGeometry** — fmc `upstream/sfn26` (ca0c17cc) `freemocap/core/skeletons/rigid_object_geometry.py`
- config :7, `feature_names` :8, `segment_name` :9, `source_mesh_units` :10, `mesh_sha256` :11, `reference_unit_mm` :12, matrix comment :13-14, `object_to_segment_reference` :15, `source_mesh_to_segment_reference` :16, `segment_reference_to_source_mesh` :17

**RecordedModel** (context) — fmc c27fc299 `freemocap/core/recording/data_descriptors/recording_model.py:15-64`; sfn26 same path :16-79 (new fields :29-31, omission rules :44-52). The descriptor is written with `model_dump_json()`, fmc c27fc299 `freemocap/core/recording/parquet_storage/parquet_writer.py:58`.

---

## 3. Disagreements

### 3.1 Spec conventions against the code

1. **Enum as text.** Spec line 19: "An enum is its text value." Code: `Handedness` is `RIGHT_HANDED = 1`, `LEFT_HANDED = -1` (sf `handedness.py:25-26`). The real model refuses `"RIGHT_HANDED"` with "Input should be 1 or -1" (tested).
2. **"A writer writes every member ... except where a row says omitted".** Three omissions in the code have no row in the spec:
   - `observation_frame`: `if segment.get("observation_frame") is None: segment.pop("observation_frame", None)` (c27fc299 `recording_model.py:39-40`).
   - `tracker_connections` at sfn26: `if not self.tracker_connections: result.pop("tracker_connections", None)` (sfn26 :48-49). Spec line 231 has no "omitted when empty".
   - `skeleton.presentation` at sfn26 (see 3.6).
3. **Quaternion tolerance.** Spec row rule 5 (line 290): "They are a unit quaternion (to 1e-5)". For the rest-pose quaternions in the descriptor the code requires `abs(norm - 1.0) > UNIT_QUATERNION_TOLERANCE` to be false, with tolerance 1e-9. Tested: norm 1 + 1e-8 is refused, 1 + 1e-10 is accepted. A generator that rounds to float32 will fail.

### 3.2 Spec `RecordedModel` rows against the code

4. **`tracker_connections` membership.** Spec line 231: "Each name is in `tracker_keypoint_names`". sfn26 code has no such check: `validate_inputs` (sfn26 :58-79) does not read the field, and `TrackedSkeletonBundle.__post_init__` (sfn26 `tracked_skeleton_bundle.py:109-111`) checks only the anchor. The inventory (section 4.2) agrees with the code: "Validation: none for this field."
5. **`tracker_connections` marker.** Spec line 231 marks it "**v2** (from `sfn26`)"; lines 240-241 mark the two other sfn26 fields "From `sfn26`" with no v2. All three have the same origin (sfn26 `recording_model.py:29-31`).
6. **`segment_topology`.** Spec line 232: "**v2.** SPEC.md SFF-832". No such field exists at c27fc299 or sfn26. Both refuse it ("Extra inputs are not permitted", tested at c27fc299). Expected for a v2 addition, but no existing code can validate it.
7. **`segment_masses` keys.** Spec line 237: "Keys are the segment names of `center_of_mass`". Code: `set(self.segment_masses) != set(self.center_of_mass.all_segment_names)` (c27fc299 :58-59), and `all_segment_names` expands a sided definition `X` to `left_X` and `right_X` (sf `center_of_mass.py:81-83, 123-132`). The keys of `center_of_mass.definitions` are the unsided names. The spec text is ambiguous; the draft states the expansion.
8. **`anchor_segment_name`.** The spec gives no rule. Code refuses an unknown segment at restore: "Unknown reconstruction anchor" (c27fc299 `tracked_skeleton_bundle.py:105-106`).
9. **"closed".** `RecordedModel` is closed and, in practice, so are the nested dataclasses: an unknown key in any of them is refused at c27fc299 (tested for skeleton, landmark, frame, rest pose, mapping, COM definition, quaternion). The exception is `TrackerMappingSnapshot.entries`, whose values are `str | list[str] | dict[str, float] | dict[str, Any]` (st `tracker_mapping.py:69`): any object passes the load.

### 3.3 c27fc299 against sfn26

10. `RecordedModel` gains `tracker_connections`, `object_geometry`, `tracker_stage_path` (sfn26 :29-31). c27fc299 refuses all three, also as `null` or `[]` (tested).
11. sfn26 pops `skeleton.presentation` when null (sfn26 :51-52). skellyforge f5404db `SkeletonSnapshot` has no such field and refuses the key (tested).
12. `ReconstructionSourceDefinition.joint_angle_names`: c27fc299 `reconstruction_samples.py:60` is `dict[str, tuple[str, str, str]]`. The inventory says sfn26 changes it to `tuple[str, ...]`; the spec (line 123) says "map of joint to an array of text". I did not re-read the sfn26 line. Note that `EulerConvention.angle_names` is still exactly 3 at f5404db.
13. The skellyforge and skellytracker revisions differ: c27fc299 pins f5404db and 03b9c1d by SHA; sfn26 `uv.lock:2530-2531, 2593-2594` uses editable paths `../skellyforge` and `../skellytracker`, and `pyproject.toml:65-66` names branch `sfn26` with no SHA. So the sfn26 form of the eleven skellyforge types is not pinned anywhere.

### 3.4 Inventory against the code

14. The inventory lists fields correctly for all types that I checked; I found no wrong field name or type. It leaves out rules that the code has:
    - `LandmarkConnectionGroup.pairs` must have 1 or more items (sf `landmark_grouping.py:114-118`). Inventory: "each pair exactly 2 names, no self-edges".
    - Tags must be non-empty and different (sf :35-50). Inventory: `tags: tuple[str] = ()`.
    - `JointSnapshot.joint_type`: inventory says `str`; restore allows only `ball`, `hinge`, `universal`, `fixed`.
    - `ChainSnapshot`: 3 or more segments at restore. Not in the inventory.
    - Quaternion and weight tolerances. Inventory: "finite and unit length", "sum 1.0".
15. Inventory: "All are stdlib dataclasses, so pydantic serialises them as objects. [inferred]". Confirmed by the round trip.
16. Inventory cites `sfn26:…/standard_human_skeleton.py:58-59` for `tracker_connections`; I see it on :59 and a second producer on :84 (hands) and `dlc_object_skeleton.py:25`. Not a conflict, only more producers.

### 3.5 Load against restore (inside the code itself)

Accepted at load but refused by `to_bundle()` at c27fc299 (all tested): `primary_axis: [5, 7]`; unknown `joint_type`; unknown joint segment; a chain of fewer than 3 segments; empty `segments`; a group naming an unknown landmark; unknown `derived_quantities`; empty `coordinate_system`; `rest_pose.parents` missing a segment; an empty mapping list entry; `passthrough: true` with entries; a mapping that names an unknown keypoint; a COM landmark that the skeleton does not have; unknown `anchor_segment_name`. The spec must decide which of these a reader must refuse. I wrote them all as rules.

Also accepted at load when omitted, although freemocap always writes them: `LandmarkGroup.tags`, `LandmarkConnectionGroup.tags`, `SegmentComDefinition.sided`, `EulerConvention.angle_names`, `EulerConvention.zero_offsets`, `anchor_segment_name`. Every other member is required, including the null-valued `secondary_point`, `secondary_axis`, `prefix`, `anatomical_segment` and `mesh_sha256`.

`EulerConvention.sequence` accepts upper case (`"ZYX"` loads and restores). The validator lower-cases only for the letter check (sf `euler_sequence.py:69`). I wrote the rule as lower case `x`, `y`, `z`, which is what the docstring says; the code is looser.

### 3.6 `presentation` (open)

sfn26 freemocap reads `skeleton.presentation` from the dumped snapshot, so skellyforge `sfn26` `SkeletonSnapshot` has that field. Its type is not available locally. A related shape exists in the sfn26 websocket contract (`packages/freemocap-client/src/transport/message-contract.ts:155-165`: `attached_lines`, `excluded_origin_edges`, `excluded_bones`, `connection_materials`), but that is the stream message built in `freemocap/core/streaming/message_model.py:353-360`, not the snapshot. I did not copy it into the draft.

---

## 4. Minimal example

This is one `RecordedModel` value (a value of `models["stick"]`). It uses every nested type of c27fc299: 3 segments (a chain needs 3), 2 joints, 1 chain, 1 group, 1 connection group, an `observation_frame` on one segment and omitted on the others, three of the four mapping-entry forms, and 3 COM definitions.

```json
{
 "model_id": "stick",
 "detector_type": "synthetic",
 "tracker_keypoint_names": ["kp_a", "kp_b", "kp_c", "kp_d", "kp_e"],
 "skeleton": {
  "name": "stick",
  "landmarks": [
   {"name": "a", "definition": "Base origin", "position": [0.0, 0.0, 0.0], "segment": "base", "aliases": []},
   {"name": "b", "definition": "Base end and tip origin", "position": [0.0, 0.0, 1.0], "segment": "base", "aliases": []},
   {"name": "c", "definition": "Base side point", "position": [1.0, 0.0, 0.0], "segment": "base", "aliases": ["c_alias"]},
   {"name": "d", "definition": "Tip end", "position": [0.0, 0.0, 1.0], "segment": "tip", "aliases": []},
   {"name": "e", "definition": "End point", "position": [0.0, 0.0, 1.0], "segment": "end", "aliases": []}
  ],
  "segments": [
   {"name": "base", "landmarks": ["a", "b", "c"],
    "frame": {"origin": "a", "primary_point": "b", "primary_axis": [2, 1], "secondary_point": "c", "secondary_axis": [0, 1], "handedness": 1},
    "aliases": [], "anatomical_segment": null},
   {"name": "tip", "landmarks": ["d"],
    "frame": {"origin": "b", "primary_point": "d", "primary_axis": [2, 1], "secondary_point": null, "secondary_axis": null, "handedness": 1},
    "aliases": [], "anatomical_segment": null,
    "observation_frame": {"origin": "b", "primary_point": "d", "primary_axis": [2, 1], "secondary_point": "c", "secondary_axis": [0, 1], "handedness": 1}},
   {"name": "end", "landmarks": ["e"],
    "frame": {"origin": "d", "primary_point": "e", "primary_axis": [2, 1], "secondary_point": null, "secondary_axis": null, "handedness": 1},
    "aliases": [], "anatomical_segment": null}
  ],
  "joints": [
   {"name": "base_tip", "parent": "base", "child": "tip", "connect_at": "b", "joint_type": "ball",
    "convention": {"sequence": "zyx", "angle_names": ["z_angle", "y_angle", "x_angle"], "zero_offsets": [0.0, 0.0, 0.0]}},
   {"name": "tip_end", "parent": "tip", "child": "end", "connect_at": "d", "joint_type": "hinge",
    "convention": {"sequence": "zyx", "angle_names": ["z_angle", "y_angle", "x_angle"], "zero_offsets": [0.0, 0.0, 0.0]}}
  ],
  "chains": [{"name": "stick_chain", "segments": ["base", "tip", "end"], "joints": ["base_tip", "tip_end"]}],
  "landmark_groups": [{"name": "all_points", "landmark_names": ["a", "b", "c", "d", "e"], "tags": ["stick"]}],
  "landmark_connections": [{"name": "stick_edges", "pairs": [["a", "b"], ["b", "d"], ["d", "e"]], "tags": []}],
  "derived_quantities": [],
  "coordinate_system": "blender"
 },
 "rest_pose": {
  "name": "stick_rest",
  "root_segment_name": "base",
  "parents": {"base": null, "tip": "base", "end": "tip"},
  "connect_ats": {"tip": "b", "end": "d"},
  "orientations": {
   "base": {"w": 1.0, "x": 0.0, "y": 0.0, "z": 0.0},
   "tip": {"w": 1.0, "x": 0.0, "y": 0.0, "z": 0.0},
   "end": {"w": 1.0, "x": 0.0, "y": 0.0, "z": 0.0}
  }
 },
 "mappings": [
  {"entries": {"a": "kp_a", "b": ["kp_b"], "c": {"kp_c": 1.0}, "d": "kp_d", "e": "kp_e"},
   "prefix": null,
   "known_tracker_keypoints": ["kp_a", "kp_b", "kp_c", "kp_d", "kp_e"],
   "passthrough": false}
 ],
 "center_of_mass": {
  "definitions": {
   "base": {"name": "base", "proximal": "a", "distal": "b", "weights": [{"landmark": "a", "weight": 0.5}, {"landmark": "b", "weight": 0.5}], "sided": false},
   "tip": {"name": "tip", "proximal": "b", "distal": "d", "weights": [{"landmark": "d", "weight": 1.0}], "sided": false},
   "end": {"name": "end", "proximal": "d", "distal": "e", "weights": [{"landmark": "e", "weight": 1.0}], "sided": false}
  }
 },
 "segment_masses": {"base": 0.5, "tip": 0.3, "end": 0.2},
 "scale_reference_name": "stick_length",
 "anchor_segment_name": null
}
```

**Validated: yes, for c27fc299.** I imported the real `RecordedModel` without changing any repo: freemocap c27fc299 exported with `git archive` into the scratchpad, skellyforge f5404db and skellytracker 03b9c1d from the uv cache checkouts, run with the freemocap `.venv` interpreter and `PYTHONDONTWRITEBYTECODE=1`. Results:
- `RecordedModel.model_validate_json` accepts it;
- `model_dump_json` gives back the same JSON value (round trip equal);
- `to_bundle()` succeeds, so the restore rules also pass.

Limits of that validation:
- pydantic in that `.venv` is 2.13.4; `c27fc299:uv.lock` pins 2.14.1.
- The fourth mapping form (`anatomical_offset`) is not in the example. I tested it separately; this entry loads, restores and dumps unchanged: `{"form":"anatomical_offset","origin":["kp_a"],"frame":{"up":{"from":"kp_a","to":["kp_b"],"kind":"exact"},"side":{"from":"kp_a","to":"kp_c","kind":"approximate"}},"offset":{"up":0.1},"reference_length":{"from":"kp_a","to":"kp_b"}}`.
- `"sided": true` is not in the example (it needs `left_`/`right_` landmarks and mass keys).

**Not validated: the sfn26 and v2 members.** For a v2 test file, the generator must add the members below. No real class checked them; the first three follow sfn26 source, the fourth follows only SPEC.md SFF-832.

```json
"tracker_connections": [["kp_a", "kp_b"], ["kp_b", "kp_d"], ["kp_d", "kp_e"]],
"tracker_stage_path": ["stage"],
"object_geometry": {
 "feature_names": ["kp_a"], "segment_name": "base", "source_mesh_units": "mm", "mesh_sha256": null,
 "reference_unit_mm": 1.0,
 "object_to_segment_reference": [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1],
 "source_mesh_to_segment_reference": [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1],
 "segment_reference_to_source_mesh": [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]
},
"segment_topology": [
 {"name": "base", "parent": null, "proximal": "kp_a", "distal": "kp_b"},
 {"name": "tip", "parent": "base", "proximal": "kp_b", "distal": "kp_d"},
 {"name": "end", "parent": "tip", "proximal": "kp_d", "distal": "kp_e"}
]
```

Files left in the scratchpad (nothing was written in any repo):
- `C:\Users\Dom\AppData\Local\Temp\claude\ca7e9b09df19a3f5\029f251e-0080-49b0-9a55-d0aa4588bc9c\scratchpad\example_model.json` (the validated example)
- `C:\Users\Dom\AppData\Local\Temp\claude\ca7e9b09df19a3f5\029f251e-0080-49b0-9a55-d0aa4588bc9c\scratchpad\validate.py` (the load, round-trip, restore and probe script)
- `...\scratchpad\fmc_c27`, `...\scratchpad\fmc_sfn26`, `...\scratchpad\st_sfn26` (exported source trees, safe to delete)

---

## 5. Not found or not verified

1. **skellyforge `sfn26`.** No checkout or cached copy exists on this machine. So I could not read `SkeletonSnapshot.presentation`, `StlRigidBodyDefinition`, or confirm that the other ten skellyforge types are unchanged on sfn26. All skellyforge rows in the draft are f5404db.
2. **sfn26 validation.** The sfn26 `RecordedModel` could not be imported: `rigid_object_geometry.py:3` imports `skellyforge.core.skeleton.stl_rigid_body`, absent at f5404db, and skellytracker sfn26 needs `filelock`, absent from the `.venv`. `RigidObjectGeometry` rules are from reading the source only.
3. **`RigidObjectGeometry` semantics.** The code gives no rule or docstring for `feature_names`, `segment_name` (must it be a skeleton segment?) or the allowed values of `source_mesh_units`. The output units of `segment_reference_to_source_mesh` are not stated; the code comment covers only the two forward matrices. No check that the matrices are affine or inverse to each other.
4. **`tracker_stage_path`.** Type `tuple[str, ...] | None`, no validator, no docstring. The only values I saw are `("hands",)` and `metadata.stage_path` for DLC objects. Its relation to the `<stage>.<point>` names of `OVERLAY_2D` is not stated in the code that I read.
5. **Units of `LandmarkSnapshot.position`.** The code says only "rest position in the owning segment's local frame". I did not find a statement of units; the relation to `scale_reference_name` is my guess and is not in the draft.
6. **`known_tracker_keypoints` against `tracker_keypoint_names`.** No code compares them. Whether they must agree, and whether `prefix` applies to one of them, is not decided by the code.
7. **Weighted-sum entries.** I found no check that the weights of a mapping `dict[str, float]` sum to 1 or are positive. I only read the constructor, not `apply`.
8. **Not read:** `build_rest_pose` (sf `rest_pose.py`), `raise_unless_snake_case_segment_name`, `LandmarkNameResolver.from_landmarks`, and `_normalize_keypoint_list`. They can add restore rules beyond those listed (for example the exact pattern of a segment name). The example passes them, so lower-case snake-case names are safe.
9. **`connect_ats` and the root.** A docstring line says "The root's entry is its own origin landmark" (sf `rest_pose.py:130-131`), which suggests freemocap writes a `connect_ats` key for the root too. The example without a root key restores correctly, so the key is not required. I did not dump a real freemocap model to see what it writes; the draft row says "one key for the `child` of each joint", which is the enforced minimum.
10. **`joint_angle_names` at sfn26** (item 12 in section 3): taken from the inventory, not re-read.
11. The draft was not run through the repo doc checks (`tools/check_links.py`, traceability). It adds no SFF ID.

Skipped: dumping a real freemocap bundle (human or ChArUco) to compare against the draft, and fetching skellyforge `sfn26` from the network (it would need a download; ask if you want it). Main risk: the sfn26 `SkeletonSnapshot` has at least one member (`presentation`) that this draft does not define, so a v2 generator built from the draft matches c27fc299 skeletons, not confirmed sfn26 ones.
