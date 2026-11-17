# How freemocap stored skeleton definitions (research)

Status: research report, 2026-11-15. A read-only sub-agent study for plan question Q10. The main session verified the removal commit f7580ee8 (2026-09-06) and `RecordedModel.tracker_connections` on upstream/sfn26 (recording_model.py:29).

Written for: Dom and agent sessions writing the skellyfileformat whole-folder spec.

---

Report: how freemocap stored the skeleton definition (keypoint names, edges, segments) with a recording, when each method was dropped, and what the sfn26 branches change

Short answer
- **v1.x releases:** the skeleton went into the recording folder as JSON files. Segment lengths were written through v1.1.1, names and edges through v1.3.0, and `<rec>_by_frame.json` carried "info.schemas" up to v1.8.2.
- **2.0 line:** a top-level `tracker_schema.json` was written from 2026-05-08. It was removed on development-streaming on 2026-09-06 (f7580ee8). The reason given is that the canonical Parquet is the only numerical output, and other outputs wait until a future output layout is agreed. upstream/main still writes it.
- **What replaced it:** the Parquet descriptor carries tracker keypoint names (as channel names) and a RecordedModel per skeleton. It does not carry the tracker's own keypoint edges.
- **sfn26 (all six branches, identically):** they add `RecordedModel.tracker_connections`, which puts the tracker's name-pair edges into the Parquet descriptor. They do not bring back a `tracker_schema.json` writer.

1. Every historical way the skeleton was saved into a recording folder

1a. `output_data/mediapipe_names_and_connections_dict.json`
- **Writer:** `save_dictionary_to_json(... file_name="mediapipe_names_and_connections_dict.json")`.
  - v1.0.0-rc: freemocap/core_processes/process_motion_capture_videos/process_recording_folder.py:154.
  - v1.1.1 and v1.3.0: data_saving_pipeline_functions.py (v1.3.0 lines 60-64).
- **Era:** present in every tag from v1.0.0-rc (2023-03-14) to v1.3.0 (2024-08-01). Absent from v1.3.1 (2024-09-04) onward (tag scan with git grep).
- **Removed by:** c83c8bd9 (philipqueen, 2024-09-04, "Generalize mediapipe code to other trackers (#536)"). The message is a squash list and gives no stated reason.
- **Shape** (v1.3.0: freemocap/core_processes/detecting_things_in_2d_images/mediapipe_stuff/data_models/mediapipe_skeleton_names_and_connections.py:30-47):
  `{"body": {"names": [...33 pose names...], "connections": [[i,j],...]}, "right_hand": {"names": ["right_hand_wrist",...], "connections": [[i,j],...]}, "left_hand": {...}, "face": {"names": ["right_eye","left_eye","nose_tip","mouth_center","right_ear_tragion","left_ear_tragion"], "connections": [[i,j],...]}}`
- **Caveats** (same file, lines 3-7 and 14-21):
  - Connections are integer index pairs from mediapipe POSE/HAND_CONNECTIONS, not name pairs.
  - The face edges are FACEMESH_CONTOURS indices into the 468-point mesh, but only 6 face names are listed, so the face edges do not line up with the names.

1b. `output_data/mediapipe_skeleton_segment_lengths.json`
- **Writer:**
  - v1.0.0-rc: process_recording_folder.py:148.
  - v1.0.34: process_recording_folder.py:247.
  - v1.1.1: data_saving_pipeline_functions.py:61-65.
- **Era:** v1.0.0-rc to v1.1.1 (2024-03-18). In v1.2.0 only a commented-out loader is left (v1.2.0: freemocap/data_layer/data_saver/data_loader.py:122).
- **Removed by:** cb72f4b5 (Aaron Cherian, 2024-04-16, "removing estimate segment lengths (#571)"; the body includes "commenting out skeleton lengths in DataSaver"). No other reason is stated.
- **Shape** (v1.1.1: freemocap/core_processes/post_process_skeleton_data/estimate_skeleton_segment_lengths.py:73-76): `{segment_name: {"median": mm, "mean": mm, "standard_deviation": mm}}`.
- **Segment definitions:** these were `{segment: {"proximal": joint, "distal": joint}}` (v1.0.0-rc same file, lines 47-54). They lived in code, not in this file.

1c. `<recording_name>_by_frame.json`, "info.schemas"
- **Writer:** DataSaver.save_to_json, which writes `{"info": InfoDict, "data_by_frame": {...}}` (v1.8.2: freemocap/data_layer/data_saver/data_saver.py:68-78).
- **Called from:** process_recording_folder.py (v1.0.15-rc line 205; v1.8.2 line 152).
- **Era:** v1.0.15-rc (2023-07-05) through v1.8.2 (2026-04-22), per the tag scan.
- **Shape in v1.0.15-rc to v1.3.0:**
  - `info = {"segment_lengths": {...}, "schemas": [SkeletonSchema.dict()]}` (v1.0.15-rc data_saver.py:104-108).
  - segment_lengths was commented out by v1.3.0 (v1.3.0 data_saver.py:100-104).
  - SkeletonSchema is `{"body": SegmentSchema, "hands": {"left": SegmentSchema, "right": SegmentSchema}, "face": SegmentSchema}`. SegmentSchema is `{point_names: [...], virtual_marker_definitions: {...}, connections: [[int,int],...], parent: str|None}` (v1.3.0: freemocap/data_layer/data_saver/data_models.py:42-77).
  - The source dict is mediapipe_skeleton_schema (v1.3.0 mediapipe_skeleton_names_and_connections.py:66-90; v1.3.0 data_loader.py:217-218).
- **Shape in v1.3.1 to v1.8.2:**
  - `info = {"schemas": model_info.segment_connections}` (v1.3.1 data_saver.py:116-120; v1.8.2 data_saver.py:171-175; v1.8.2 data_models.py:122-130).
  - segment_connections looks like `{"head": {"proximal": "left_ear", "distal": "right_ear"}, "neck": {"proximal": "head_center", "distal": "neck_center"}, ...}` (skellytracker repo f57b8ff8: skellytracker/trackers/mediapipe_tracker/mediapipe_model_info.py:68-80).
  - Names appear only as keys of `data_by_frame[n]["tracked_points"][name] = {x,y,z}` (v1.8.2 data_models.py:114-119).
- From v1.3.1, output_data holds only `{tracker}_*.npy` arrays plus split_and_save output (v1.8.2 data_saving_pipeline_functions.py:40-81). No separate names or edges JSON is written.

1d. 2.0 line: `tracker_schema.json` at the recording root
- **Writer added:** 54338385 (jonmatthis, 2026-05-08, "Add concept of 'Active Recording' plus many other changes (#788)"), at freemocap/core/tasks/mocap/posthoc_mocap_task.py:117-126. It picks MEDIAPIPE_HOLISTIC_DEFINITION when the first observation is a MediapipeObservation, otherwise RTMPOSE_WHOLEBODY_DEFINITION, then calls `write_text(json.dumps(definition.model_dump()))`.
- **Shape at 54338385:** skellytracker's TrackedObjectDefinition, `{"name", "tracker_type", "landmark_schema", "tracked_points": [...], "connections": [[a,b],...]}` with name-pair edges (skellytracker repo 185c05b0: skellytracker/trackers/base_tracker/tracked_object_definition.py:19-28).
- **Changed:** 6d4884d6 (philipqueen, 2026-07-21, "Skellytracker rewrite (#810)") made the writer always use RTMPOSE_WHOLEBODY_DEFINITION (6d4884d6 posthoc_mocap_task.py:113-116). It imports from freemocap.core.tracking.tracker_definitions. The shape became `{"name": "rtmpose_wholebody", "tracked_points": [...], "connections": [[a,b],...]}` (upstream/development-streaming: freemocap/core/tracking/tracker_definitions.py:23-28, loaded from skellytracker YAML at lines 31-42).
- **Removed on development-streaming:** f7580ee8 (jonmatthis, 2026-09-06, "works, paring down to build up"). It deletes the block at f7580ee8^:freemocap/core/tasks/mocap/posthoc_mocap_task.py:185-190 and adds a test asserting the file is not written (upstream/development-streaming: freemocap/tests/test_recording_store.py:422).
- **upstream/main still writes it:** 700c8614, 2026-10-27, version 2.0.0a25 (upstream/main: freemocap/core/tasks/mocap/posthoc_mocap_task.py:142-147; pyproject.toml:3).
- **Related live-wire handshake:** `tracker_schemas` (TrackerSchemasMessage, `{name, tracked_points, connections}` per tracker). It was added in 59a2ec24 (2026-04-19) and removed with freemocap/api/websocket/tracker_schema_message.py in b89c9569 (2026-08-14, "chkpt"). It was never a recording file.

2. Why it was dropped on development-streaming, and what replaced it

Stated reason: f7580ee8 adds this text (upstream/development-streaming: current-work-plans/02-pipeline/app-workflow-todo.md:24-36, "Output scope — 2026-09-06"):
> "Pause additional export development for a data-model discussion. A recording represents a capture volume, with potentially multiple humans, animals, objects and calibration boards; it is not a single tracked person's model container. The only numerical data output currently enabled by posthoc mocap is the canonical Parquet, including its self-describing model/measurement data. No provisional `output_data` NPY/CSV files, top-level `tracker_schema.json`, or model/measurement JSON mirror are written. ... A future output layout must be agreed before rebuilding exports piece by piece."

The same commit changes current-work-plans/03-transport/recording-data-model-proposal.md so that recording metadata JSON holds only capture-level information and "Publication does not write a JSON copy of the Parquet descriptor".

Replacement: the Parquet descriptor
- It is embedded under the key `b"freemocap.recording"` (upstream/development-streaming: freemocap/core/recording/sample_encoding/arrow_schema.py:30).
- Structure: `RecordingMetadata{schema_version: 1, recording_id, selected_run_id, recording_info, runs: {id: RunDescriptor}}` (recording_descriptor.py:191-196). RunDescriptor has `sources`, `models: dict[str, RecordedModel]`, `channels`, `static_channels`, `scale_fits` and more (recording_descriptor.py:98-111).
- **Channel `names`:** the tracker keypoint names. Overlay channels use `names=request.tracker.point_names` (observation_inputs.py:218). Names only; no edges (recording_descriptor.py:39-46).
- **Sources `definition`:** for TRACKER sources this is only the run configuration (`Source(kind=TRACKER, definition=self.configuration)`, observation_inputs.py:67-68). The configuration is `config.model_dump()` plus execution info (freemocap/core/pipeline/dataflow/recording_pipeline.py:236-242). It holds no point list and no edges. `point_names` is dropped by `to_source()`.
- **`models` / RecordedModel** (recording_model.py:15-27): `model_id`, `detector_type`, `tracker_keypoint_names`, `skeleton: SkeletonSnapshot`, `rest_pose: RestPoseSnapshot`, `mappings: TrackerMappingSnapshot[]`, `center_of_mass`, `segment_masses`, `scale_reference_name`, `anchor_segment_name`.
  - There is no tracker-edge field on development-streaming.
  - The snapshot types are skellyforge's. Their serialized field layout is not verified, because skellyforge source on the development-streaming branch is not available locally. A test shows `skeleton.segments` is a list of objects with `name` and `observation_frame` (freemocap/tests/test_recorded_observation_frames.py:42-56).
  - TrackerMappingSnapshot = `{entries, prefix, known_tracker_keypoints, passthrough}` (skellytracker repo upstream/development-streaming: skellytracker/core/io/tracker_mapping.py:91-96).
- **Segment edges** exist only by derivation after restoring through skellyforge. Playback runs `model.to_bundle()` and then `compose_messages` (freemocap/core/recording/playback_queries.py:110-115, 145). ModelDefinition builds `connections` as (parent_segment, child_segment) from `rest_pose.parents`, and `landmark_connections` from `skeleton.landmark_connections` (freemocap/core/streaming/message_model.py:305-317, 350-387).

Playback router fallback (upstream/development-streaming: freemocap/api/http/playback/playback_router.py)
- `GET /{id}/tracker-schema` (lines 703-735) reads `<recording>/tracker_schema.json`. If the file is missing, it logs a warning and returns `{"name": "fallback", "tracker_type": "unknown", "tracked_points": [], "connections": [], "landmark_schema": "generic"}` (lines 725-734).
- The bundle endpoint (lines 839-845) sets `tracker_schema = None` when the file is missing, and records a TRACKER_SCHEMA resource error when the file is invalid (test: freemocap/tests/test_bundle_resources.py:35-38).
- For development-streaming recordings this endpoint therefore always yields the empty fallback or null.

Where the UI gets connections today (development-streaming)
- Playback takes `run.models: ModelDefinition[]` from the playback manifest (freemocap-ui/src/components/viewport3d/RecordingPlaybackProvider.tsx:90-91; freemocap-ui/src/services/recording/playback-data.ts:43).
- ModelConnectionRenderer draws `definition.connections` (segment edges) and `definition.landmark_connections` (freemocap-ui/src/components/viewport3d/renderers/ModelConnectionRenderer.tsx:5-7, 74, 91).
- Face edges come from a hardcoded index table (freemocap-ui/src/components/viewport3d/helpers/face-contours.ts:5-24).
- tracked-object-definition.ts still describes the `tracker_schemas` handshake (lines 1-21), but no other UI file imports it (git grep finds only the file itself). No Python sender exists anymore (git grep 'tracker_schemas' over *.py on upstream/development-streaming returns nothing).
- `trackerSchema` is stored in playback-data-slice.ts:36 and :127. I found no other readers.
- The plan docs say the handshake was removed (current-work-plans/04-ui/ui-integration.md:95).
- Some docs are stale: they still describe the file (freemocap-docs/docs/architecture/backend-mocap.mdx:122, 138; freemocap-docs/docs/guides/posthoc-mocap.mdx:145, 151).

3. Later branches (sfn26 and siblings)
- **Latest commits:**
  - sfn26: 3ae9842d, 2026-11-04.
  - sfn26-machine-benchmarks: 5a2187b0, 2026-11-06.
  - sfn26-ui-harness: 142f73eb, 2026-11-04.
  - sfn26-ui-integration: af266ac4, 2026-11-03.
  - sfn26-ui-refactor: 74612f0b, 2026-11-03.
  - sfn26-ultraskelly: 2ae48efa, 2026-11-03.
  - development-streaming: c27fc299, 2026-10-18.
- **Branch point:** all six share merge-base 0700621b (2026-10-15). Each is 5 commits behind development-streaming and 62 to 121 ahead (git rev-list).
- **Same diff everywhere:** `git diff --stat` against development-streaming is identical on all six for recording_descriptor.py, recording_model.py, observation_inputs.py, tracker_definitions.py, message_model.py and playback_router.py.
- **Change, added in 72235c4d** (jonmatthis, 2026-11-01, "Refine hybrid tracking, graph processing, and skeleton presentation"):
  - New RecordedModel fields `tracker_connections: tuple[tuple[str,str],...] = ()`, `object_geometry` and `tracker_stage_path` (upstream/sfn26: freemocap/core/recording/data_descriptors/recording_model.py:29-31). These are omitted from the serialized form when empty, so old fingerprints stay the same (lines 33-56).
  - The edges are filled from `tracker_profile(detector_type).connections` (upstream/sfn26: freemocap/core/skeletons/standard_human_skeleton.py:59) and from DLC metadata (dlc_object_skeleton.py:25).
  - They are passed into `ModelDefinition.tracker_connections` (message_model.py:327, 413).
  - tracker_definitions.py now comes from skellytracker `tracker_profile` (upstream/sfn26: freemocap/core/tracking/tracker_definitions.py:1-18).
  - Stated rationale (upstream/sfn26: SKELETON_PRESENTATION.md:68-71): "Tracker remains the topology owner. Core carries its existing profile connections through `TrackedSkeletonBundle`, `RecordedModel`, and shared `MessageComposition` into optional static `ModelDefinition.tracker_connections`. New recordings preserve those edges; old recordings without them keep face points without invented edges."
- **No writer re-added:** git grep on upstream/sfn26 finds only readers.
  - playback_router.py:645-672 keeps the same fallback, and :777-783 is the bundle read.
  - The read endpoint is now also exposed at upstream/sfn26: freemocap/api/http/recordings/resources_router.py:32 and in the generated client (packages/freemocap-client/src/generated/operations.ts:143; schema.ts:510).
  - test_recording_store.py:422 still asserts the file is absent, and app-workflow-todo.md:32 keeps the same text.
- **Net effect on sfn26:** edges come back, inside the Parquet descriptor's RecordedModel, rather than as a file.

4. Assessment: can a third party rebuild the skeleton from the Parquet descriptor without freemocap code?

**Names: yes.** Channel `names` (recording_descriptor.py:44) and `RecordedModel.tracker_keypoint_names` (recording_model.py:20) are plain JSON strings.

**Tracker keypoint edges: no on development-streaming.**
- No field holds them: Source definition is the configuration only (observation_inputs.py:68), and RecordedModel has no edge field (recording_model.py:18-27).
- A reader would need the skellytracker YAML for the tracker named in the configuration. Those are the edges `tracker_schema.json` used to carry (f7580ee8^:posthoc_mocap_task.py:185-190).
- On sfn26 they are present as plain name pairs in `tracker_connections` (upstream/sfn26 recording_model.py:29), but only when non-empty. Recordings made before that change have none (SKELETON_PRESENTATION.md:71).

**Segment edges and segment definitions: only implicit.**
- The skeleton/rest-pose snapshots presumably contain segments and parent relations, since freemocap rebuilds them (playback_queries.py:113; message_model.py:361, 384-386).
- The serialized layout belongs to external skellyforge types and is not described in the descriptor. There is no per-model schema version; only `RecordingMetadata.schema_version: 1` exists (recording_descriptor.py:192).
- freemocap derives the parent→child edge list after `restore()`. It is not stored as a ready edge list.
- Whether a third party can read parents, segment endpoints or landmark_connections straight from the JSON is not verified (skellyforge snapshot source not checked).

**Segment lengths:** there is a SEGMENT_LENGTHS channel kind and `scale_fits` (recording_descriptor.py:100, 146-158). I did not check whether runs actually write them.

**What is missing for a code-free reader:**
- On development-streaming, tracker edges.
- On both branches:
  - A documented, self-contained form of segment topology (segment name, parent, proximal/distal landmarks) that does not depend on skellyforge class layouts.
  - A published schema for the `models` block.

Not checked:
- skellyforge SkeletonSnapshot/RestPoseSnapshot field layout.
- Whether the SEGMENT_LENGTHS or static channels are populated in real runs.
- v1.2.0 `_get_info_dict` directly (inferred from the cb72f4b5 message and v1.3.0).
- The sfn26-* branches beyond the listed paths and the tracker_schema grep.

Risk: upstream/main still writes `tracker_schema.json` and development-streaming does not, so recordings from the two lines differ.
