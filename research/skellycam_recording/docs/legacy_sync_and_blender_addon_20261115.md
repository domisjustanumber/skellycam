# skelly_synchronize and Blender addon outputs in freemocap v1 releases (inventory)

Status: research report, 2026-11-15. A sub-agent downloaded the exact pinned wheels from PyPI (checked against PyPI sha256; network use approved by Dom; nothing was run) and read them. The main session checked the freemocap v1.5.2 pin. Complements `legacy_release_inventory_20261115.md`.

Written for: Dom and agent sessions writing the skellyfileformat legacy annex and the future `.blend` section.

---

REPORT: skelly_synchronize and the Blender addon (ajc27_freemocap_blender_addon) across freemocap v1.0.25 to v1.8.2

Where things are
- I downloaded wheels only (these are what pip installs) and checked each against the PyPI sha256. I unzipped them to C:\Users\Dom\AppData\Local\Temp\claude\ca7e9b09df19a3f5\ef960e37-035d-4929-84c6-9e035d622496\scratchpad\pinned_pkgs\<name>-<version>\src\. Every file:line below is relative to that src\ folder. I did not run any package code and changed no repo state.
- The PyPI and GitHub metadata JSON is in ...\scratchpad\meta\.
- The real package name is ajc27-freemocap-blender-addon on PyPI (import name ajc27_freemocap_blender_addon). Its source repo is github.com/freemocap/freemocap_blender_addon; freemocap pins also used the old URL .../ajc27_freemocap_blender_addon.git. "freemocap-blender-addon" returns 404 on PyPI.

======================================================================
1. PINS PER FREEMOCAP TAG (checked with git show <tag>:pyproject.toml; the previous scan had some ranges wrong)
======================================================================
skelly_synchronize:
- v1.0.25 (2023-11-09): 2023.10.1027. This is a poetry pin, and poetry.lock agrees.
- v1.0.26 to v1.0.31: ">=2023.9.1026", unpinned. At release time this resolved to 2023.10.1027 (INFERENCE). 2023.12.1028 and 2023.12.1029 were uploaded 2023-12-11 at 23:04Z and 23:08Z, which is after the v1.0.31 tag (16:52Z).
- v1.0.32 to v1.2.2: 2023.12.1029.
- v1.3.0 to v1.5.4: 2024.07.1032, which is PyPI 2024.7.1032.
- v1.6.0 to v1.8.2: 2025.04.1037, which is PyPI 2025.4.1037.

Blender addon:
- v1.0.25: "*" in poetry. poetry.lock resolves it to 0.2.12.
- v1.0.26 and v1.0.27 (2023-11-12): git+URL with no ref. At release time main HEAD was commit 919d149 ("bump version", 2023-11-08 18:13Z). PyPI 0.2.12 was uploaded one minute later, and the next commit is dated Nov 14. So this is the 0.2.12 code (INFERENCE).
- v1.0.28 (Nov 12): unpinned, resolves to 0.2.12 (INFERENCE).
- v1.0.29 to v1.0.31 (Dec 7 to Dec 11): unpinned, resolves to 0.2.14 (INFERENCE; 0.2.15 was uploaded Dec 12).
- v1.0.32 to v1.1.1: 2023.10.1016 (uploaded 2023-12-12 01:51Z, just before the v1.0.32 tag at 03:25Z).
- v1.2.0 to v1.2.2: 2023.10.1017.
- v1.3.0: v2024.07.1022.
- v1.3.1 to v1.4.7: v2024.09.1024. The previous scan said v1.4.6 to v1.5.4 used 2024.12 to 2025.1; that was wrong.
- v1.5.0 and v1.5.1: v2024.12.1033.
- v1.5.2: v2024.12.1034. This version is NOT on PyPI and NOT a GitHub tag (see Gaps).
- v1.5.3 to v1.6.3: v2025.1.1035.
- v1.7.0 to v1.7.2: v2025.8.1037.
- v1.7.3 and v1.7.4: v2025.11.1038.
- v1.8.0 to v1.8.2: 2026.04.1039, which is PyPI 2026.4.1039.

Compatibility trap for the unpinned releases:
- In freemocap v1.0.25 to v1.0.31, run_simple.py calls `ajc27_freemocap_blender_addon.run_as_main.ajc27_run_as_main_function(recording_path=..., save_path=...)`.
- Addon 2023.10.1016 renamed that argument to blend_file_path (2023.10.1016 run_as_main.py:10-16).
- Addon 2023.10.1017 removed run_as_main.py and replaced it with main.py.
- PEP 440 sorts 2023.10.x above 0.2.x. So anyone who installed v1.0.26 to v1.0.31 after 2023-12-12 got an addon that fails: a TypeError with 1016, an ImportError with 1017 and later. They would have no Blender outputs.
- v1.0.32 to v1.1.1 already pass blend_file_path, and v1.2.x and later import .main, so they match their pins.

Distinct versions analysed:
- skelly_synchronize: 2023.10.1027, 2023.12.1029, 2024.7.1032, 2025.4.1037.
- Addon: 0.2.12, 0.2.14, 2023.10.1016, 2023.10.1017, 2024.7.1022, 2024.9.1024, 2024.12.1033, 2025.1.1035, 2025.8.1037, 2025.11.1038, 2026.4.1039.

======================================================================
2. SKELLY_SYNCHRONIZE: WHAT IT WRITES
======================================================================
How freemocap calls it (all v1 tags):
- The Import Videos wizard sets the target to <recording_sessions>/<name>/synchronized_videos, with default name "import_<source folder name>" (freemocap v1.8.2 import_videos_wizard.py:71,87).
- SynchronizeVideosThreadWorker calls synchronize_videos_from_audio or synchronize_videos_from_brightness(raw_video_folder_path=<source folder>, synchronized_video_folder_path=<rec>/synchronized_videos, create_debug_plots_bool=False) (synchronize_videos_thread_worker.py:49-61).
- When the worker finishes, the wizard itself calls create_audio_debug_plots or create_brightness_debug_plots (import_videos_wizard.py:225-238). So debug_plot.png is written.
- The video handler is the default, "deffcode".
- Without sync, freemocap just copies the files (freemocap_main_window.py:528-544 in v1.8.2).

Versions 2023.10.1027, 2023.12.1029 and 2024.7.1032 have the same output logic. The only differences are __init__ prints and the Qt binding in the GUI. Citations use skelly_synchronize-2024.7.1032\src\skelly_synchronize\.

Written inside <rec>/synchronized_videos/:
- synced_<stem>.mp4, one per input video.
  - A leading "raw_" is stripped: utils/path_handling_utilities.py:24-32. Prefix and suffix constants: system/paths_and_file_names.py:23-24.
  - Inputs are globbed from mp4, mkv, avi, mpeg and mov in upper and lower case (utils/get_video_files.py:5-22). The output is always .mp4.
  - Encoding: frames are decoded by deffcode as bgr24 and re-encoded with cv2.VideoWriter FourCC "mp4v" (MPEG-4 Part 2) at the decoder's output_framerate (core_processes/video_functions/deffcode_functions.py:26-41).
  - Trim: start_frame = int(lag*fps), and length = int(min over videos of (duration - lag) * fps) frames (video_utilities.py:48-112, 115-127).
  - Rotation: if OpenCV and deffcode disagree on width/height, the code adds "-noautorotate" and "transpose=1" (deffcode_functions.py:16-24; utils/check_if_video_has_reversed_metadata.py:7-37).
- Audio method only: each synced mp4 is rewritten with an AAC audio track and the video stream copied (ffmpeg -c:v copy -c:a aac).
  - The temp file sits in a TemporaryDirectory inside synchronized_videos and is then moved over the mp4 (video_utilities.py:130-165; ffmpeg_functions.py:158-183).
  - On failure, versions up to 2024.7.1032 only print, so a synced video can be left without audio.
  - Audio is looked up as "<stem after first '_'>.wav". So an input named raw_cam1 makes synced_cam1, looks for cam1.wav, and finds no file (video_utilities.py:146-150). This is a latent bug.
- audio_files/<stem>.wav (audio method only).
  - Written by plain `ffmpeg -y -i video out.wav`, so ffmpeg's default WAV codec, which is PCM s16le at the source rate and channels (ffmpeg default, inference).
  - Code: ffmpeg_functions.py:5-23, audio_utilities.py:30-61, skelly_synchronize.py:77-80,108-112.
- audio_files/trimmed_audio/<stem>.wav (audio method only).
  - Loaded with librosa (default mono=True), sliced [lag*sr : lag*sr + synced_len*sr], and written by soundfile as PCM_24. So it is mono, 24-bit, at the original sample rate (audio_utilities.py:64-90).
- synchronization_debug.toml (skelly_synchronize.py:142-152 audio, 252-259 brightness; debug_output.py:5-16; key names in paths_and_file_names.py:9,13-16).
  - [Raw_video_information.<stem>] and [Synchronized_video_information.<synced stem>] each hold: "video filepath", "video pathstring", "camera name", "video duration" (ffprobe format=duration, seconds), "video fps" (r_frame_rate as a float) (video_utilities.py:23-45).
    - The synced durations are measured before audio is attached.
  - [Audio_information."<stem>.wav"] holds "sample rate", "camera name", "audio duration" (audio method only; audio_utilities.py:54-59).
  - [Lag_dictionary] maps stem to seconds.
    - Audio method: lags come from FFT cross-correlation against the first file in the list. They are normalized so the latest-starting video has lag 0 and all others are positive (correlation_functions.py:92-118).
    - Brightness method: lag = first frame where diff*double-diff >= threshold (default 1000), divided by fps. These lags are NOT normalized (correlation_functions.py:27-53, 121-136).
  - Serialization caveat, from reading toml 0.10.2's encoder in a local uv cache (dump_value falls back to "%r"; this is what freemocap pins): non-builtin values such as pathlib.Path and numpy.float64 are written as quoted repr strings. So "video filepath" probably looks like "WindowsPath('...')", and the lags look like "0.0333" (numpy 1.x) or "np.float64(0.0333)" (numpy 2.x). In 2025.4.1037 the brightness lags are Python floats and come out as real TOML floats. A reader must accept strings and floats here. This is an inference from code; I did not see a real file.
- debug_plot.png: matplotlib, two panels, "Before" and "After" (debug_plots.py:16-49, 97-127).
  - Audio method: waveforms of audio_files/*.wav vs trimmed_audio/*.wav.
  - Brightness method: brightness curves. The x axis is labelled "Time (s)" but is actually frame index (debug_plots.py:64-94).
- synced_<stem>_brightness.npy (brightness method only): float64, shape (n_frames,), the mean grayscale per frame of each synced video (skelly_synchronize.py:261-262; correlation_functions.py:56-76).

Written outside the recording folder:
- <source folder>/<stem>_brightness.npy (brightness method).
- <source folder>/normalized_videos/<stem>.mp4, made only when fps or audio rates differ. It uses ffmpeg -r <min fps> -ar <min rate> (normalize_framerates.py:11-42; ffmpeg_functions.py:105-130).
- A log file under ~/skelly_synchronize_data/logs_info_and_settings/logs/, only if the root logger has no handlers (__init__.py:38; system/default_paths.py).

Changes in 2025.4.1037 (freemocap v1.6.0 and later). The file layout and names are unchanged.
- Input list is sorted case-insensitively (utils/get_video_files.py:26). This changes which camera is the cross-correlation reference and the order of keys in the TOML.
- Rotation handling now uses deffcode's source_video_orientation and picks transpose clock or cclock, or a double transpose for 180 degrees (deffcode_functions.py:10-20, 37-44).
- Duration is now taken from the v:0 stream instead of the container (ffmpeg_functions.py:87-113).
- Failures now raise RuntimeError instead of printing, including audio attach (ffmpeg_functions.py:244-275).
- The brightness lag frame is cast to int, so brightness lags become floats in the TOML.

======================================================================
3. BLENDER ADDON: READS, WRITES, SCENE
======================================================================
How freemocap invokes it (all v1 tags):
- `blender --background --python run_simple.py -- <recording_folder> <blend_path>`.
- blend_path = <rec>/<rec_name>.blend (freemocap path_getters.get_blender_file_path / get_blender_file_name).
- From v1.3.x on, freemocap first checks that output_data/mediapipe_* npy files exist (run_ajc_addon_main.py:126-181 in v1.8.2).
- The addon names everything after Path(recording_path).stem. Its outputs go under recording_path (saved_data via the saver, 3d_models, output_data) or blend_path.parent (bone CSV). These are the same folder when freemocap runs it.

----- Era A1: 0.2.12, 0.2.14 and 2023.10.1016 (freemocap v1.0.25 to v1.1.1) -----
These three have the same I/O.
- 0.2.14 only adds a guard for zero-length bones in enforce_rigid_bones.py:40-53.
- 2023.10.1016 renames save_path to blend_file_path and adds an empty create_video_output stub (core_functions/video_output/create_video_output.py:3-4). It also defines _output_video_path, which is unused.
- Citations: ajc27_freemocap_blender_addon-0.2.12\src\ajc27_freemocap_blender_addon\.

Pipeline (core_functions/main_controller.py:342-363): load data, add virtual trajectories, move to the inertial frame, enforce rigid bones, fix hand data, save_data_to_disk, then empties, rig, bone CSV, rigid-body meshes, skelly mesh, COM mesh, videos, setup_scene, save .blend.

READS:
- output_data/mediapipe_body_3d_xyz.npy, mediapipe_right_hand_3d_xyz.npy, mediapipe_left_hand_3d_xyz.npy, mediapipe_face_3d_xyz.npy, all divided by 1000 so the data is in metres (data_models/freemocap_data/helpers/freemocap_data_paths.py:24-33; freemocap_data_model.py:166-182).
- output_data/center_of_mass/total_body_center_of_mass_xyz.npy, divided by 1000, shape (F,3).
- output_data/center_of_mass/segmentCOM_frame_joint_xyz.npy: only checked for existence (__post_init__ at freemocap_data_paths.py:46-50), never loaded.
- output_data/raw_data/mediapipe3dData_numFrames_numTrackedPoints_reprojectionError.npy, shape (F, 553).
  - It is split into 33/21/21/478 columns, and the column count must match exactly (freemocap_data_model.py:179-234). Point counts come from mediapipe_names/mediapipe_trajectory_names.py:6 (face = 478).
  - So a face array with 468 points, or any other tracker, fails.
- Videos: annotated_videos/*.mp4|*.MP4 if that folder exists, otherwise synchronized_videos/*.mp4 (core_functions/load_data/load_videos.py:13-21, 62-89).
  - They are only referenced as image or movie textures, not copied.
  - On save, Blender's default relative_remap probably stores them as //annotated_videos/... (Blender default, inference).
- No TOML or JSON from the recording folder is read in this era.
- Package assets: assets/skelly_lowpoly_mesh.fbx.

WRITES (FreemocapDataSaver, core_functions/freemocap_data_handler/helpers/saver.py):
- saved_data/_FREEMOCAP_DATA_README.md (:104-107).
  - It describes the files as *_frame_name_xyz.csv and the JSON key as "hands". The real files are *_trajectories.csv and the real keys are right_hand and left_hand.
- saved_data/info/freemocap_data_handler.pkl (:109-114). A pickle of the handler object; it needs the addon package to load and is unsafe to unpickle.
- saved_data/info/trajectory_names.json (:147-164): {"body":[39 names], "right_hand":[21], "left_hand":[21], "face":[478], "other":{"center_of_mass":["center_of_mass"]}}.
  - Body = 33 mediapipe names plus 6 virtual ones: head_center, neck_center, trunk_center, hips_center, right_hand_middle, left_hand_middle (data_models/mediapipe_names/virtual_trajectories.py:1-26).
  - Hand names look like right_hand_wrist.
  - Face names: face_right_eye, face_left_eye, nose_tip, mouth_center, right_ear_tragion, left_ear_tragion, then face_6 to face_477 (mediapipe_trajectory_names.py:84-98).
- saved_data/info/metadata.json (:123-145). Keys:
  - recording_path
  - data_paths (dict of the npy paths read)
  - original_origin_reference, rotation_matrix (put_skeleton_on_ground.py:71-77)
  - bone_data (per bone: head, tail, lengths, median, stdev), body_dimensions, skeleton_hierarchy (enforce_rigid_bones.py:70-75)
- saved_data/npy/ (:80-102), all in metres, translated and rotated, rigid-bone-enforced and hand-fixed:
  - body_frame_name_xyz.npy (F,39,3)
  - right_hand_frame_name_xyz.npy and left_hand_frame_name_xyz.npy (F,21,3)
  - face_frame_name_xyz.npy (F,478,3)
  - center_of_mass_frame_name_xyz.npy, (F,3) or (F,1,3). The all_frame_name_xyz property reshapes the COM array in place (handler.py:81-100), so the saved shape depends on whether that property was read first. Treat both shapes as valid.
  - all_frame_name_xyz.npy (F,560,3), in the order body, right hand, left hand, face, COM.
- saved_data/csv/{body,right_hand,left_hand,face,center_of_mass}_trajectories.csv and saved_data/all_trajectories.csv (:41-78).
  - Written by np.savetxt with fmt '%s' and delimiter ','.
  - The header line starts with "# " and reads "name_x, name_y, name_z," per point: comma-space inside a triple, no space between triples, trailing comma.
  - Columns are points*3: 117, 63, 63, 1434, 3, and 1680 for all_trajectories.csv. One row per frame, no frame column.
- saved_data/<rec>_bone_and_joint_data.csv (main_controller.py:226; core_functions/rig/save_bone_and_joint_angles_from_rig.py:10-48).
  - csv.DictWriter with a plain header and no '#'.
  - Rows cover frames 0..N inclusive, so N+1 rows. The last row is the held last keyframe.
  - Columns are "<bone>_<field>" with 30 fields per bone (:50-82): head_center_world_x/y/z, tail_center_world_x/y/z, rotation_quaternion_x/y/z/w, rotation_euler_x/y/z, rotation_euler_order (a string such as XYZ), matrix_0_0 .. matrix_3_3.
  - Values come from PoseBone.head, .tail and .matrix, which are in armature space. "world" is a misnomer unless the armature sits at identity.
  - Bones included: pose bones of the rig whose names are in ALL_BONES_CONSTRAINT_DEFINITIONS (63 names, including pelvis and face; data_models/bones/bone_constraints.py:1). Order follows rig.pose.bones.
- saved_data/_BONE_AND_JOINT_DATA_README.md (:15, :45-46).
- <rec>.blend at the path freemocap passes (main_controller.py:335-340, bpy.ops.wm.save_as_mainfile).
- UI-only, not part of freemocap's automatic export: "Export FBX" writes <rec>/<rec>.fbx (core_functions/export/fbx.py:20-27; operator in blender_interface/operators/_export_fbx.py).

.blend scene in era A1:
- Parent empties (main_controller.py:89-117; setup_scene/make_parent_empties.py):
  - "<rec>_origin" (ARROWS, the root)
  - children: "empties_parent" (PLAIN_AXES), "rigid_body_meshes_parent" (CUBE), "videos_parent" (IMAGE), "center_of_mass_data_parent" (SPHERE)
  - all children hidden (:328-332)
- Marker empties (core_functions/empties/creation/create_freemocap_empties.py:12-54; create_empty_from_trajectory.py:10-62):
  - One keyframed empty per body point (SPHERE, size 0.03) and per hand point (PLAIN_AXES, size 0.015), named exactly after the trajectory names, under empties_parent.
  - One "center_of_mass" empty (ARROWS) under center_of_mass_data_parent.
  - NO face empties.
  - Location keyframes at frames 0..F-1.
  - The scene frame range is 0..F (setup_scene/set_start_end_frame.py:8-14).
- Armature: a Rigify human metarig, renamed. Object name and armature data name are both "<rec>_rig" (core_functions/rig/add_rig.py:24-37). Bones are renamed, e.g. spine.003 to spine.001 and spine.004 to neck (:200, :505). Bones are constrained to the empties.
- Meshes:
  - "fmc_mesh" / "mesh": rigid-body bone meshes, mode "custom" from default_parameters.json (attach_mesh_to_rig.py:297).
  - "skelly_mesh": imported from Skelly_LowPoly_Mesh FBX (meshes/skelly_mesh/attach_skelly_mesh.py:56,100).
  - "center_of_mass_mesh" with "center_of_mass_material".
- Video planes:
  - Made with io_import_images_as_planes, emission shader, named "video_0".."video_N". The numbering is arbitrary because the code de-duplicates with set().
  - Laid out in a row at y=4, z=3, scale 5, rotated 90 degrees about X, parented to videos_parent (load_videos.py:24-59).
- No capture cameras, no calibration use, no lights, no ground plane.

----- 2023.10.1017 (freemocap v1.2.x) -----
- The automatic pipeline and outputs are the same as era A1.
- The data layer moved to freemocap_data_handler/; data paths, model and saver are textually unchanged.
- run_as_main.py became main.py.
- run_all: main_controller.py:354-377. create_video is commented out (:375), and create_scene_objects is commented out (:333).
- setup_scene now also deletes "Cube".
- New UI-only "Create video" writes <rec>/<rec>.mp4 with the FFMPEG MPEG4 container and H264 (core_functions/create_video/create_video.py:13-36).

----- Era A2: 2024.7.1022 (v1.3.0) and 2024.9.1024 (v1.3.1 to v1.4.7) -----
- The files saved are the same as A1. The saver gains handling for dataclasses (saver.py), with no change in format.
- The rig is now built "BY_BONE" (main_controller.py: add_rig_method=AddRigMethods.BY_BONE).
  - A plain armature named "root", with armature data also "root" (core_functions/rig/add_rig.py:936-940). This is NOT "<rec>_rig".
  - Bones are the 62 from data_models/bones/bone_definitions.py: pelvis.R/L, spine, spine.001, neck, head_nose, shoulder, upper_arm, forearm, hand, thumb.carpal/01-03, palm.01-04, f_index/middle/ring/pinky.01-03, thigh, shin, foot, heel.02, each .L and .R where it applies.
- The bone CSV still filters on the constraint-definition keys.
- Skelly mesh: built per bone from assets/skelly_bones/*.fbx, joined as "skelly_mesh" (attach_skelly_mesh.py:31-50, 165).
- Rigid-body meshes: create_rigid_body_meshes, "fmc_mesh" (attach_rigid_body_meshes_to_rig.py:291).
- 2024.9.1024 changes only the data paths (freemocap_data_paths.py:20-45). It reads output_data/center_of_mass/mediapipe_total_body_center_of_mass_xyz.npy, mediapipe_segmentCOM_frame_joint_xyz.npy and raw_data/mediapipe_3dData_numFrames_numTrackedPoints_reprojectionError.npy, falling back to the old unprefixed names. This matches freemocap v1.3.1, which introduced tracker-prefixed names; v1.3.0 still writes the old names, so 1022 is consistent with it.

----- Era A3: 2024.12.1033 (v1.5.0, v1.5.1) and 2025.1.1035 (v1.5.3 to v1.6.3) -----
- Entry point: main.py:21 now calls controller.load_data(), which is the old run_all (main_controller.py:373-397).
- NEW WRITE: <rec>/3d_models/<rec>.fbx and <rec>/3d_models/<rec>.bvh (core_functions/export_3d_model/export_3d_model.py:25-71; called at main_controller.py:396 before the .blend is saved).
  - FBX: the selected armature plus its child meshes, baked animation, add_leaf_bones=True.
  - BVH: frames frame_start..frame_end, which is 0..N.
- Rig object is named "<rec>_rig" again; its armature data is "root_bone" (core_functions/create_rig/add_rig_bone_method.py:56-60; core_functions/data_models/armatures/root_bone_name.py:1).
- The bone CSV now filters on metadata bone_data keys, the 62 bones (core_functions/create_rig/save_bone_and_joint_angles_from_rig.py, bone_names argument).
- "center_of_mass_data_parent" is removed. The COM empty and mesh are parented to "<rec>_origin", and the origin empty itself is hidden (main_controller.py:111, 335).
- UI-only video export:
  - <rec>/video_export/<rec>_<profile>.mp4
  - <rec>/video_export/render_cameras/<rec>_<camera>.mp4
  - (create_video/helpers/composite_video.py:33-34, 232-234; render_cameras.py:24-27)
- 2025.1.1035 changes only the video loader. On Blender 4.2 and later it uses bpy.ops.image.import_as_mesh_planes:
  - planes keep the default names from the image file names
  - height 3, centred, z = 2.0
  - linked into a new "Videos" collection and parented to videos_parent
  - On older Blender the "video_N" path is kept.
  - (2025.1.1035 core_functions/load_videos/load_videos.py, first function, and the version switch near the end)

----- Era A4: 2025.8.1037 (v1.7.0 to v1.7.2) -----
- NEW READ: the first match of glob("*calibration.toml") in the recording root (freemocap_data_paths.py:36-37). It reads metadata.groundplane_calibration (freemocap_data_model.py:175-180, tomllib).
  - If that is true, put_data_in_inertial_reference_frame is SKIPPED (main_controller.py:400). The data stays in the calibration frame, and metadata.json then has no original_origin_reference or rotation_matrix.
  - metadata.json data_paths gains a "calibration_toml" key, which may be null.
- Skelly mesh: default strategy BY_VERTEX_GROUP. It appends object "skelly_mesh" from assets/skelly_full_mesh_20k_faces.blend (meshes/skelly_mesh/attach_skelly_mesh.py:63; strategies/attach_skelly_by_vertex_groups.py:19-29).
- 3d_models export: the name is <origin name without "_origin">, i.e. still <rec>.fbx and <rec>.bvh, written to 3d_models/ (add_subfolder=True). The FBX is now exported after the armature is posed to its rest pose by markers, with armature_nodetype NULL and primary/secondary bone axes Y and X (export_3d_model.py:43-46, 82-132).
- The COM empty is hidden. The origin is registered in scene.freemocap_properties if the addon UI is loaded.

----- Era A5: 2025.11.1038 (v1.7.3, v1.7.4) -----
- NEW WRITE: <rec>/output_data/joint_angles.csv and joint_angles.npy (main_controller.py:189-217, path at :207; core_functions/calculate_joint_angles/calculate_joint_angles.py:216-251).
  - Computed after fix_hand_data and before save_data_to_disk, on body plus hands in metres in the inertial frame (or the calibration frame if groundplane).
  - CSV: one header line with no '#', 23 comma-joined names, one row per frame (F rows), fmt %.8f, "nan" where a calculation failed, units degrees.
  - Names, in order (joint_angle_definitions.py:27-608): left/right_elbow_extension_flexion, left/right_shoulder_extension_flexion, left/right_shoulder_abduction_adduction, left/right_knee_extension_flexion, left/right_hip_extension_flexion, left/right_hip_abduction_adduction, neck_extension_flexion, neck_lateral_flexion, neck_rotation, left/right_ankle_dorsiflexion_plantarflexion, left/right_ankle_inversion_eversion, spine_extension_flexion, spine_lateral_flexion, left/right_hand_extension_flexion. The file interleaves left and right in blocks; the exact order is in the file.
  - NPY: shape (F,23), float64.
  - NOTE: this lands inside freemocap's own output_data/ folder.
- NEW READ plus scene objects: add_capture_cameras (core_functions/add_capture_cameras/add_capture_cameras.py:18-158).
  - It takes the LAST *.toml in os.listdir(recording) order (:24-26). This is a different rule from the data-paths glob.
  - It does nothing unless metadata.groundplane_calibration is true (:42-48). freemocap TOMLs have had a [metadata] table since v1.0.25, and freemocap v1.7.0 and later write groundplane_calibration.
  - For each [cam_*] table it creates a camera object named "Capture_cam_N" (:126), parented to an empty "capture_cameras_parent" (ARROWS, hidden), which is itself parented to the "*_origin" empty (:56-74).
    - location = world_position / 1000 (mm to m) (:94)
    - rotation = quaternion(world_orientation 3x3) @ 180 degrees about X (:100-108)
    - sensor width 36 mm, lens_mm = fx * 36 / max(width, height) taken from size (:111-123)
    - scene resolution = cam_0 size (:77-78)
  - Background clips: synchronized_videos/*.mp4 is listed with os.listdir (:87-88). Camera cam_N gets the Nth file in listdir order as a MOVIE_CLIP background image (alpha 1, frame_offset 1) (:137-156).
  - The run order puts add_capture_cameras after add_videos and before setup_scene (main_controller.py:498). An exception here is re-raised and would stop the .blend from being saved.
- The toml or tomllib fallback is added in freemocap_data_model.py:13-21, 184-192.
- UI export_video: <rec>/video_export/<rec><suffix>.mp4 with suffix _debug, _showcase, _scientific, _multiview or "" (custom), plus video_export/render_cameras/<rec>_<cam>.mp4 (export_video/helpers/composite_video.py:80-82, 141-142; create_render_scenes.py:33-36; data_models/parameter_models/video_config.py:5-192).

----- Era A6: 2026.4.1039 (v1.8.0 to v1.8.2) -----
- create_scene_objects is now called (main_controller.py:384). It adds:
  - a "Front_Camera" set as the scene camera, at x=0, y computed from the empties' extents, z=mid-height, rotated 90 degrees about X (setup_scene/scene_objects/cameras/create_cameras.py:49-86)
  - "ground_plane", a 10 m plane with "ground_plane_material", a checkerboard (ground_plane/create_ground_plane.py:22-31)
  - a SPOT "Light" 2 m above the Front_Camera (lights/create_lights.py:13-26)
- The video loader adds a Blender 5 path: planes named "video_<file>" or by the importer default, in a "Videos" collection.
  - On Blender 4.2 to 4.x it uses align_axis '+Y' and size_mode ABSOLUTE (load_videos.py:19-53, 56-210).
  - The folder choice is still annotated_videos, else synchronized_videos (load_videos.py:265-268).
- All other I/O is identical to 2025.11.1038.

======================================================================
4. ERA TABLE (freemocap release, sync version, addon version, what you will find)
======================================================================
Sync groups:
- S1 = skelly_synchronize 2023.10.1027 / 2023.12.1029 / 2024.7.1032. Identical outputs.
- S2 = skelly_synchronize 2025.4.1037. Same layout; sorted inputs, new rotation handling, stream-based duration, raises on error.

- v1.0.25 | S1 | addon 0.2.12 | A1: <rec>.blend, saved_data/{csv,npy,info,READMEs, <rec>_bone_and_joint_data.csv, all_trajectories.csv}
- v1.0.26 to v1.0.28 | S1 (inferred) | addon 0.2.12 or git HEAD (inferred) | A1
- v1.0.29 to v1.0.31 | S1 (inferred) | addon 0.2.14 (inferred) | A1 (if installed later: no Blender outputs)
- v1.0.32 to v1.1.1 | S1 | addon 2023.10.1016 | A1
- v1.2.0 to v1.2.2 | S1 | addon 2023.10.1017 | A1 (adds a UI video export to <rec>.mp4)
- v1.3.0 | S1 | addon 2024.7.1022 | A2: same files as A1; .blend has a by-bone rig named "root"
- v1.3.1 to v1.4.7 | S1 | addon 2024.9.1024 | A2 plus reading of mediapipe_-prefixed COM and reprojection files
- v1.5.0 and v1.5.1 | S1 | addon 2024.12.1033 | A3: plus 3d_models/<rec>.fbx and <rec>.bvh; rig "<rec>_rig" with armature data "root_bone"; no COM parent empty
- v1.5.2 | S1 | addon v2024.12.1034 (not available) | unknown; most likely A3
- v1.5.3 and v1.5.4 | S1 | addon 2025.1.1035 | A3 (on Blender 4.2 and later: "Videos" collection, planes named after the files)
- v1.6.0 to v1.6.3 | S2 | addon 2025.1.1035 | A3
- v1.7.0 to v1.7.2 | S2 | addon 2025.8.1037 | A4: reads the calibration TOML; may skip re-orientation; full-mesh skelly
- v1.7.3 and v1.7.4 | S2 | addon 2025.11.1038 | A5: plus output_data/joint_angles.csv and .npy, plus Capture_cam_N cameras
- v1.8.0 to v1.8.2 | S2 | addon 2026.4.1039 | A6: plus Front_Camera, ground_plane, Light

======================================================================
5. DETECTION RULES (by content, no version stamp needed)
======================================================================
skelly_synchronize import vs. native recording:
- synchronized_videos/synchronization_debug.toml with tables Raw_video_information, Synchronized_video_information and Lag_dictionary means the recording was imported and synced.
- If it also has Audio_information, plus an audio_files/ and audio_files/trimmed_audio/ subtree and AAC audio in the mp4s, the audio method was used.
- *_brightness.npy files and no Audio_information mean the brightness method.
- Videos named synced_*.mp4 with the mpeg4 (mp4v) codec, plus debug_plot.png. Imports have no synchronized_videos/timestamps/.
- An unsynced import has none of these: plain copied files with their original names.
- S1 vs S2 cannot be told apart reliably. Weak hints: in S2 the TOML keys are sorted alphabetically (case-insensitive), and brightness lags are TOML floats rather than quoted strings.
- An Audio_information table with mp4s that have no audio means the attach step failed silently (S1 only).

Blender-addon eras:
- Any addon run: <rec>/<rec>.blend plus saved_data/info/metadata.json plus saved_data/npy/all_frame_name_xyz.npy of shape (F,560,3).
- 3d_models/ present means 2024.12.1033 or later (A3 and later).
- output_data/joint_angles.csv (23 columns, header with no '#') plus joint_angles.npy means 2025.11.1038 or later. Do NOT confuse these with freemocap's own outputs.
- metadata.json data_paths:
  - a "calibration_toml" key means 2025.8.1037 or later
  - mediapipe_-prefixed center_of_mass or reprojection paths mean 2024.9.1024 or later AND a freemocap v1.3.1 or later recording
  - missing rotation_matrix and original_origin_reference (with calibration_toml set) means the groundplane path in 2025.8.1037 or later, so the data is in the calibration frame, not re-oriented
- Inside the .blend (needs a .blend reader):
  - armature object "<rec>_rig" with armature data "<rec>_rig" and Rigify bone names: A1 (0.2.x to 2023.10.1017)
  - object "root" with data "root": 2024.7.1022 or 2024.9.1024
  - object "<rec>_rig" with data "root_bone": 2024.12.1033 or later
  - "center_of_mass_data_parent" present: before 2024.12.1033
  - planes "video_N" under videos_parent: an addon before 2025.1.1035 or Blender older than 4.2
  - a "Videos" collection: addon 2025.1.1035 or later on Blender 4.2 or later
  - "capture_cameras_parent" and "Capture_cam_N": 2025.11.1038 or later with a groundplane calibration
  - "Front_Camera", "ground_plane" and "Light": 2026.4.1039
- Bone CSV: the column set and order differ between the Rigify era (filtered on the 63 constraint keys) and 2024.12.1033 and later (the 62 bone_data keys). A sample file is needed to pin the exact header.

======================================================================
6. GAPS AND CAVEATS
======================================================================
- freemocap v1.5.2 pins ajc27_freemocap_blender_addon==v2024.12.1034. That version is on neither PyPI (which has 2024.12.1033, then 2025.1.1034 and 2025.1.1035) nor the GitHub tags. A pip install of freemocap 1.5.2 probably could not resolve, unless the published freemocap wheel differs from the tag. I did not check the freemocap PyPI metadata because that package was outside the approved scope.
- Unpinned resolutions for v1.0.26 to v1.0.31 (both packages) are inferences from upload times. Users who installed later got newer versions, and for the addon those break, as described in section 1.
- I did not download 0.2.13, 0.2.15, 2024.12.1034 or 2025.1.1034. 0.2.13 sits between 0.2.12 and 0.2.14, which differ only in one guard.
- Everything here comes from reading code. No sample .blend, TOML or CSV was inspected. The following need a real file to confirm:
  - TOML value types (numpy/Path written as repr strings)
  - the COM npy shape, (F,3) vs (F,1,3)
  - the exact bone-CSV columns
  - Blender's relative video paths in the .blend
- Fragile behaviours in the addon:
  - Capture-camera to video matching depends on os.listdir order.
  - The calibration TOML is picked by two different rules: the data paths take the first *calibration.toml from glob; the cameras take the last *.toml from listdir.
  - The addon only accepts mediapipe data with a 478-point face and a reprojection error of exactly 553 columns.

======================================================================
7. URLS FETCHED (package names and versions only; GET requests with a generic User-Agent)
======================================================================
- https://pypi.org/pypi/skelly-synchronize/json
- https://pypi.org/pypi/ajc27-freemocap-blender-addon/json
- https://pypi.org/pypi/freemocap-blender-addon/json (404)
- https://files.pythonhosted.org/packages/39/fe/f0b68566ce6adc387f2add17b37cd1ff4d6909b4b9d744123c1ac4ea6571/skelly_synchronize-2023.10.1027-py3-none-any.whl
- https://files.pythonhosted.org/packages/d8/b5/19a5941ff56ee16595cf7be6322dae9e9481b1fb401b0031801cb408ad04/skelly_synchronize-2023.12.1029-py3-none-any.whl
- https://files.pythonhosted.org/packages/31/66/792afe2a1bf5cb9ecb6a329dfb835b476aa8c92c713d614d6a69931af69c/skelly_synchronize-2024.7.1032-py3-none-any.whl
- https://files.pythonhosted.org/packages/9b/22/22c73e9df8dc814167892c33d55225fc85d42413a486647648beddc55dc8/skelly_synchronize-2025.4.1037-py3-none-any.whl
- https://files.pythonhosted.org/packages/81/1c/97273771575fe9b3d415043c97ae28b5cedc253767c621f5199de53d4374/ajc27_freemocap_blender_addon-0.2.12-py2.py3-none-any.whl
- https://files.pythonhosted.org/packages/ff/4e/7107b92133ae0a6f1a6727fa9f685459f1fde2b1aa2a4cabdcbada1a1215/ajc27_freemocap_blender_addon-0.2.14-py2.py3-none-any.whl
- https://files.pythonhosted.org/packages/cf/23/4f772d6a0b9741a850bb2147e94a6f4d9bc344e714b33d47fe8b1626fe44/ajc27_freemocap_blender_addon-2023.10.1016-py3-none-any.whl
- https://files.pythonhosted.org/packages/c3/f0/bd50e28ced7198c4cf0fe1012ac54fb4abfc99886c3320d1a83f1be427f3/ajc27_freemocap_blender_addon-2023.10.1017-py3-none-any.whl
- https://files.pythonhosted.org/packages/86/59/a9fc6aeac21267206a356f06418badb5df44fab2d455218bfd738788d653/ajc27_freemocap_blender_addon-2024.7.1022-py3-none-any.whl
- https://files.pythonhosted.org/packages/49/15/403788d84a52cc9006583494092d08f341600f6c6b921fd510481f4d99f9/ajc27_freemocap_blender_addon-2024.9.1024-py3-none-any.whl
- https://files.pythonhosted.org/packages/f7/6b/bac1c5d976ad2654d4c95e2cab9e8162b05c99e247b4658e78cb9531af0f/ajc27_freemocap_blender_addon-2024.12.1033-py3-none-any.whl
- https://files.pythonhosted.org/packages/2f/c5/044fdb1d527a8f4422f1e77b4c323631fb312aaccd73400b3cf923d27792/ajc27_freemocap_blender_addon-2025.1.1035-py3-none-any.whl
- https://files.pythonhosted.org/packages/45/47/d13c65dc872f3e0aad374f292abf94f3fa309012028decdb82990a4c4c4a/ajc27_freemocap_blender_addon-2025.8.1037-py3-none-any.whl
- https://files.pythonhosted.org/packages/3a/ca/0cc1ade3f02d50d5cb6161e6e09c3f4eb3f03c83ef4d67595c85c8b6b24a/ajc27_freemocap_blender_addon-2025.11.1038-py3-none-any.whl
- https://files.pythonhosted.org/packages/3e/f5/1b9c3cc6a86ef3c7fdc3cd395faff2fcfe8c79d45988175e6f7da6948fce/ajc27_freemocap_blender_addon-2026.4.1039-py3-none-any.whl
- https://api.github.com/repos/freemocap/freemocap_blender_addon/tags?per_page=100
- https://api.github.com/repos/freemocap/freemocap_blender_addon/commits?since=2023-11-01T00:00:00Z&until=2023-11-16T00:00:00Z&per_page=100

Not checked: I read wheels, not sdists or git trees, and I ran nothing, so the .blend contents and value types come from code only. Biggest risk: the v1.5.2 pin is unresolvable, and v1.0.26 to v1.0.31 installs made after Dec 2023 produce no Blender output at all.
