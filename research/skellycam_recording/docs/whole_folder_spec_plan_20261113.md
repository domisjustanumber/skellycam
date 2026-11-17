# skellyfileformat as the spec of the whole recording folder: plan

Status: plan for Dom's review, 2026-11-13. Dom's decisions are marked accepted; everything else is proposed.

Written for: Dom and future agent sessions working on skellyfileformat, skellycam and freemocap development-streaming.

This is a plan, not the spec. **Accepted (Dom, 2026-11-13):**
- D27 (MCAP) reversed, back to spec v0: per-camera MJPEG `.mkv` with index (constant-rate) PTS; FLAC (`frame_size=1024`) in `.mka`; binary `.skvt`/`.skat` timing sidecars always in separate files, never embedded; no legacy timestamp CSVs written; sensor orientation stored with `display_rotation` in the sidecar (E/68Z6 and v0 SFF-102/103 stand).
- The `.mkv`/`.mka` hold only video, audio and timestamps. Sidecars hold everything else, including 2D and 3D tracking. No burned-in overlays.
- "skellyfileformat must include all of the associated sidecar files. It must be the spec for the whole folder."
- freemocap is not tested now; "we'll implement our reader into freemocap".
- REV decisions 1–5 (REV:488-494).

Every other choice below is **proposed**.

No code was run. Sources were re-opened read-only for this plan. A claim without a citation is marked "not verified".

Citation keys:
- **v0S** = SFF `bd62b60:spec/SPEC.md` (v0 rev 2). **v0C** = `bd62b60:spec/conformance.md`.
- **S1** = SFF main `spec/SPEC.md` (MCAP draft v1). **C1** = main `spec/conformance.md`. **RM** = main `README.md`. **OW** = `decisions/open-work.md`. **E/<id>** = `decisions/entries/<id>-*.md`.
- **RC** = FMC `RECORDING_CONTRACT.md`. **PJ** = FMC `shared/recording-contract/paths.json`. **TC** = FMC `freemocap/tests/test_recording_folder_contract.py`. **FMC** = freemocap `upstream/development-streaming` @c27fc299. **RFC** = FMC `current-work-plans/03-transport/recording-folder-contract.md`.
- **SCds** = skellycam `remotes/upstream/development-streaming`.
- **A73** = Blender addon commit 73e1b3e, the commit FMC locks (REV:11). **A73 was not re-opened for this plan** (the uv git cache named at REV:11 was not found); its lines come from REV and DTB1.
- **REV** = `SC\research\skellycam_recording\docs\spec_v0_revival_tracking_sidecars_20261113.md`. **DTB1** = `SC\research\skellycam_recording\recording_upgrade\results\blender_mkv\FINDINGS.md`. **RFF**, **MFR**, **SDD**, **TFD** = docs `recording_folder_files.md`, `manifest_field_review.md`, `spec_draft_decisions_20261112.md`, `tracking_file_decisions_20261113.md`. **HO** = `SC\research\HANDOFF_20261113_freemocap_phase2_work_items.md`.

---

## 1. Summary

**What the whole-folder spec covers (proposed).** One take folder: every file and subfolder in it.
- Each file gets a class: in the format (a), reserved (b), legacy (c), or not allowed (d) (§4). How deep class b goes is Dom's call (A7).
- **In the format, fully specified:**
  - the skellycam device files: `.mkv`, `.skvt`, `.mka`, `.skat`, and their live and temp states. These come from v0;
  - both info JSONs, the calibration TOML and the tracking Parquet (2D and 3D);
  - the folder rules: names, discovery, membership, cross-file links, the reader result, crash and atomic-write rules, privacy and safety.
- **Reserved:** freemocap's derived output, caches and operational files. The default proposal fixes their names and owners, not their contents; A7 asks whether that meets Dom's wording.
- **Legacy:** old layouts. The spec says how to recognise them and what result a reader reports.

**Main approach (proposed).**
1. Restore v0 rev 2 for the device files, with REV's accepted changes, and take the reader states and codes from E/WG08. Then add a folder layer on top.
2. Specify freemocap's files as a **frozen core plus owner extensions**:
   - SFF fully defines the parts another reader needs: Parquet columns, descriptor key, the 2D/3D channels, units, reference frames, the null policy, take links, and the TOML camera fields.
   - freemocap-only members, such as stage provenance, are named as owner extensions that readers keep and ignore.
3. Take the names freemocap and skellycam **write today**, not RC/PJ's canonical names, which no production writer uses. Evidence: RC:219 lists writer migration as pending; `create_on_disk()` (FMC `freemocap/system/recording_structure/recording_structure.py:134`) has only a test caller (TC:38, by `git grep`); FMC `freemocap/core/recording/result_processing/saved_observations.py:70` says "The application still records and imports synchronized_videos/" (§5).
4. Find folder files by fixed name and device files by content, inside the media folder. Never take an arbitrary first match (RC:87-88). Recognise a new take by its content, not by folder names (§5, §18).
5. Tie every file to its take by `take_uuid` and to each camera by `camera_key`. This needs `camera_key` to become a MUST (C12).
6. Spec-first gates: spec text plus test list (gate 1), then tests plus golden folders (gate 2), then code (E/TDB5:24-26). **Release gate:** no skellycam release writes the new format until freemocap reads it (D5, §10).

---

## 2. Documentation basis

| Document | Status | What we take | What we do not take |
|---|---|---|---|
| v0S (SFF bd62b60) | Archived draft, being revived | Device-file byte layouts (§4–7); versioning SFF-050..058 (v0S:112-139); Segment UID and offsets §10 (v0S:760); names table §12 (v0S:820-847); recognition §13, SFF-550 binding (v0S:851-856); take facts SFF-650..653 (v0S:895-908); opening SFF-654..659 (v0S:912-931) | §9 embedding and appender (REV decision 1 accepted); §15.3 manifest (withdrawn by E/TDB5:13-14); FLAC inside the camera MKV (§8; REV decision 6, proposed); v0's reader state names SFF-666 (v0S:983-989), replaced by E/WG08 |
| v0C | Archived draft | The test IDs for the revived sections | Embed, manifest and appender tests |
| S1, C1 (SFF main) | Normative draft v1 for MCAP; superseded in substance by the D27 reversal | Container-independent rules: reader result JSON SFF-678..680 (S1:813-841); take grouping SFF-674 (S1:796-798) | Everything MCAP |
| E/WG08 | Accepted (WG08:3) | File states `unsupported_version`, `invalid`, `damaged`, `unfinished`, `repaired`, `finished`, `not_in_format`; reason codes; warning scope; `files` vs `other_files` (WG08:13-27). REV:632 says port these | The MCAP-specific causes (`opus_head`, `bad_chunking`, MCAP profile) |
| RM | Normative | Compatibility promise (RM:39-45), conformance (RM:69-76), package version rule (RM:65-67) | MCAP scope text (RM:3-7, 15-37); "format version = skellycam release" (RM:49-53) |
| E/TDB5 | Accepted, the only active scope entry | Scope wording (TDB5:7-12); no manifest (:13-14); take grouping (:15-18); one canonical reader result for the Python reader, the JavaScript reader and golden files (:19-21); spec-first, IDs, golden files (:24-32) | Items 1, 5 and 6 (device files only; info JSON out, :22; legacy out, :23). These need superseding (§6) |
| E/W4PF | Accepted | One package with a Python reader/writer **and a JavaScript reader** (items 1-2, :7-11); spec-alone goal (:12-14); no overlay file (:19) | Item 4, no names (:15-17); item 8, tracking is later work (:21) |
| E/25VV, E/5PP8, E/41VF | Superseded | History: 5PP8 included layout and names (5PP8:13-14). 25VV **rejected by name** fixing the media file names and `synchronized_videos/` (25VV:68-69) | — |
| E/DK8S, E/7K3C, E/X1G6, E/68Z6, E/D9N1, E/WD9A, E/10JC | Accepted | 68Z6 items 1-3 (sensor orientation; `display_rotation`; no rotation written anywhere else, :7-13); 7K3C items 2-6 (version fields, reader rules, package version, :11-23); X1G6 item 1 (read old) | DK8S as a whole (MCAP profile; item 12 no names, :33); 7K3C item 1 (version = skellycam release, :7-10); X1G6 items 2 (MCAP) and 6 (legacy outside the spec, :15); D9N1 (Opus, overturned by the FLAC decision, REV:140); WD9A and 10JC (Lichtblick). OW:30-31 counts only X1G6 items 2 and 3 as spec content; items 1, 4, 5, 6 are skellycam rules. This plan moves item 1's meaning into the spec (§18) |
| RC | **Normative** for freemocap ("maintained target, version 1", RC:3) | Tree (RC:18-41) as the location list; ownership table (RC:63-70); mixed-layout rules (RC:83-94); lock and scratch files are operational (RC:58-59); runs model (RC:98-111) | Canonical `videos/synchronized/`, `_calibration.toml` and `output/`: no production writer uses them (§1 item 3) |
| PJ | Normative data, enforced by TC | Name inventory (PJ:1-24) | Canonical folder and TOML names (PJ:4-6, 9); `legacy_v1` as a legacy test (it holds the names this plan makes current, §5) |
| TC | Tests | Pattern for cross-language name checks (TC:17-33) | TC:44-56's rule that `synchronized_videos/` means a legacy layout |
| FMC Parquet code: `sample_encoding/arrow_schema.py`, `data_descriptors/recording_descriptor.py`, `result_processing/observation_inputs.py`, `observation_publication.py`, `parquet_storage/parquet_writer.py` | Code: the de-facto spec | Columns (arrow_schema.py:15-29, per digest); descriptor key (:30, per digest); `RecordingMetadata` (recording_descriptor.py:191-196); `Descriptor` base `extra="forbid"` (:18-19); camera source fields `camera_id`, `video_filename`, `timing_method`, `nominal_fps`, `inferred_offset_s` (observation_inputs.py:178-183); image size = video size (observation_publication.py:103-108, per digest); name check (parquet_writer.py:44-45) | Internals freemocap must stay free to change (stage provenance, fits) |
| FMC `core/recording/recording_info.py` | Code | `processed` block, schema_version 1, `parquet_sha256` (:29-36); atomic write (:37-47) | Copying every capture field, including absolute paths (:12-16) |
| FMC `tasks/calibration/shared/calibration_toml.py`, `calibration_metadata.py`, `calibration_paths.py`, `calibration_save.py` | Code | TOML layout: one `metadata` table plus camera tables (calibration_toml.py:180-193); name and lookup rule (calibration_paths.py:18-20, 28-39); three save locations (calibration_save.py:37-51) | Embedded skellycam `RecordingInfo` (calibration_metadata.py:4, 30); the `*calibration*.toml` glob fallback (calibration_paths.py:35-39) as a rule for new takes |
| SCds `recording_info.py`, `recording_metadata.py`, `video_filename.py`, `default_paths.py`, `recording_timing_reader.py`, `recording_statistics.py`, `recording_finalizer.py` | Code | Info JSON fields (recording_info.py:21-27, 80-104); name pattern (video_filename.py:7, per REV:67); timing and statistics seams (recording_timing_reader.py:18-31; recording_statistics.py:10-17) | The `*_info.json` glob (recording_metadata.py:16); non-atomic write (recording_info.py:103-104); absolute `recording_directory` (:23); CSV timing paths (:93-97) |
| FMC `current-work-plans/02-pipeline/app-workflow-todo.md` | Plan, current | Only the Parquet is written by posthoc; no tracker_schema.json (:30-33); observation JSON, reconstructed-board NPY and realtime ChArUco disk cache disabled (:35-36); "A future output layout must be agreed" (:36) | — |
| RFC | Dated audit; "not a second normative contract" (:3-4, per digest) | Gap list; reference recordings have `output/diagnostics.yaml` and no capture info JSON (:55-59); `ready.json` lives outside recording folders (:61-63) | Normative weight |
| FMC `recording-data-model-proposal.md` | Proposal; tree superseded | Null policy (:184, per digest) | Tree |
| FMC `02-pipeline/calibration-export-policy.md`, `secondary-exports.md`, `recording-access.md`, `full-recording-loop.md`; `core/recording/recording_guide.md`; `exports/README.md`; `skeletons/rotation-output-contract.md` | Plans and guides | Export locations, e.g. `exports/calibration_copies/` (calibration-export-policy.md:9, per draft). Not re-read for this plan: not verified | Contents of exports |
| FMC `freemocap/tests/REAL_DATA.md` | Test doc | Reference datasets for legacy golden folders | Contents not re-checked: not verified |
| FMC `freemocap-docs/.../backend-recording-structure.mdx` | **Stale, AI-generated** (banner, :6-8, per draft) | Nothing | All |
| FMC `freemocap-docs/.../backend-mocap.mdx`, `guides/posthoc-mocap.mdx` | Stale | Nothing (they describe tracker_schema.json; per draft, not re-read) | All |
| REV | Proposal; decisions 1–5 accepted (REV:488) | Layout evidence (REV:54-72); Parquet as 2D sidecar (REV:224-240); imports (REV:376-379); decision-log update list (REV:593-640) | REV:254, "reference the Parquet schema, do not re-specify it" (conflicts; §6) |
| DTB1 | Desk-test result | Index PTS pass, real PTS fail (DTB1:7-9); gaps squeezed out (:57) | It ran Blender with no add-ons (:32); the addon was not run on an `.mkv` take (:48) |
| RFF, MFR, SDD | Research | MFR privacy findings (MFR:59, 114, per digest); version field for the info JSON (RFF:58, 63) | RFF:54's ownership rule (superseded by Dom's decision; §6) |
| TFD | Grilling decisions, MCAP era | Content decisions listed in the digest (Q1, Q2, Q9-Q12, Q19, Q26, Q37, Q42...) | MCAP, Lichtblick, layout (Q13-Q18) |
| HO | Handoff, MCAP era | Work-item list | "replaces only skellycam's half" (HO:31) |

---

## 3. Proposed structure of the spec

### 3.1 Outline of SPEC.md (whole folder)

| § | Part | Source |
|---|---|---|
| 1 | Scope and terms: take, take folder, media folder, device file, folder file, classes a–d | New; v0S:11-24 rewritten |
| 2 | Conventions (byte order, UID text form, JSON integer strings) | v0S §2 |
| 3 | Versioning: format version, part versions, compatibility table (§3.4 below) | v0S §3 plus new |
| 4 | MKV video profile, index PTS | v0S §4, minus embed rules (REV §2) |
| 5 | `.skvt` video timing sidecar (header, clocks, records, times) | v0S §5 |
| 6 | FLAC in `.mka` (frame_size 1024) | v0S §6 (REV decision 5 accepted) |
| 7 | `.skat` audio timing sidecar | v0S §7 |
| 8 | skellysync device files | v0S §8/§14, reworked (REV decision 6, proposed) |
| 9 | Live, crashed and repaired device files | v0S §11 plus the PV6S/5G42 content (REV:630-631) |
| 10 | Segment UID, live and final offsets; media-to-sidecar binding (SFF-550) | v0S §10 (v0S:760), §13 (v0S:851-856) |
| 11 | Take facts in every sidecar header (`take_uuid`, take start times, `utc_offset_min`, `group_size`, `clock_id`) | v0S §15.1, SFF-650..652 (v0S:895-905) |
| 12 | **Folder layout and names**: fixed names, media folder, reserved names | New; RC:18-41, PJ, today's writers |
| 13 | **Opening a folder**: discovery, membership, take grouping, ambiguity, mixed layouts, new-vs-legacy by content | v0S §15.2 plus RC:83-94 plus new |
| 14 | **Capture info JSON** (`<rec>_info.json`, skellycam), including what `videos`, `camera_timing`, `multiframe_timing` mean in a new take (C13) | New, from SCds recording_info.py:80-104 |
| 15 | **Recording info JSON** (`<rec>_recording_info.json`, freemocap) | New, from FMC recording_info.py:29-36 |
| 16 | **Calibration TOML**, including the calibration model (C11) | New, from FMC calibration_toml.py:180-193 |
| 17 | **Tracking Parquet** (2D and 3D): columns, descriptor core, channels, frames, null policy, take links | New, from arrow_schema.py and the descriptor code |
| 18 | **Cross-file consistency** (take_uuid, camera_key, counts, dimensions, rotation, file references, the synchronized timeline, parquet_sha256) | New |
| 19 | **Reserved files** (derived, caches, operational) | RC:53-59, 176-197 |
| 20 | **Legacy layouts**: recognition and reader result | v0S §13 plus new (content first, names only for truly old outputs) |
| 21 | Privacy and safety | v0S SFF-653 (v0S:907-908), widened to every class-a file; a no-execution rule (C17) |
| 22 | Atomic writing of folder files | New; FMC parquet_writer.py, recording_info.py:37-47 |
| 23 | Reader result JSON (device files plus folder files) | E/WG08, S1:813-841 plus new |
| App. A | Golden folders | New |

**Where the sub-specs live (proposed).** One normative SPEC.md, per W4PF items 1-3. Long schemas go in normative appendices under `spec/parts/` (e.g. `parquet.md`, `calibration_toml.md`, `info_json.md`), cited from SPEC.md with their own requirement IDs. Machine-readable schemas sit next to them: JSON Schema for the JSONs, an Arrow schema dump, and a name table that replaces PJ's role.

**IDs.** v0 IDs were marked "withdrawn, Draft v0" in S1 (e.g. S1:699), and IDs are never reused (E/TDB5:28-29). Proposed: revived v0 rules get new IDs, and each cites its v0 ID. Folder parts take a new range (e.g. SFF-700+).

### 3.2 Re-specify or reference (W4PF item 3, "spec alone")

E/W4PF:12-14 requires that another program can implement the format from the spec alone.
- **Device files:** fully re-specified, as in v0 (v0S:11-14).
- **Parquet:** Apache Parquet and Arrow are referenced like Matroska: an external container standard. The **content** is re-specified in SFF: the 11 columns, the metadata key `freemocap.recording`, the core descriptor members, the channel kinds for 2D/3D, reference frames, units, the null policy and the validation rules (arrow_schema.py:15-30 and :126-257 come from the digest; not re-read). Proposed: freemocap-only members are "owner extensions" (`runs[*].processing`, stage provenance (RC:115-117), fits, models). The spec names them and says a reader preserves them, but does not define them.
- **TOML, both JSONs:** re-specified in full. They are small.
- REV:254 ("the format spec references the Parquet schema ... and does not re-specify it") conflicts with this. Proposed: supersede it (§6).
- **JavaScript reader.** W4PF item 2 (:9-11) and TDB5 item 4 (:19-21) require a JS reader compared against the canonical reader result. Putting the Parquet, TOML and JSONs in class a means the JS reader must read Parquet and TOML too, or the spec must say which parts it covers. Decision A8.

### 3.3 Ownership and governance

**Proposed (depends on A1/A4).**
- RC's ownership table stays true for **who writes** (RC:63-70). SFF becomes the **one document that defines** the folder.
- A change to a class-a part of a freemocap file (Parquet core, TOML, recording info) needs an SFF decision entry and a spec change first. A change to an owner extension does not.
- RC keeps its freemocap-internal rules: runs, provenance, export retention, acceptance (RC:96-324). Its "Paths" and "Compatibility" sections would cite SFF.
- PJ becomes generated from, or tested against, the SFF name table.
- RC:93-94 ("Capture-writer changes belong to a separate SkellyCam stage with a human-owned commit/push handoff. FreeMoCap must continue accepting installed capture output.") still applies. SFF entries that change writers are handed off. Nothing is pushed without asking Dom.
- freemocap maintainers have not agreed to this model: not verified.

### 3.4 Versioning

| Part | Version today | Evidence |
|---|---|---|
| `.skvt`/`.skat` | u16 major/minor/prerelease in the header | v0S:112-124 |
| MKV/MKA | None; takes its sidecar's version | v0S SFF-057 (v0S:135-136) |
| Parquet descriptor | `schema_version: Literal[1]`; `extra="forbid"` | recording_descriptor.py:192, :18-19 |
| Stage provenance | Version 1; outer descriptor kept at 1 "for installed reader compatibility" | RC:115-117 (per draft) |
| Recording info `processed` | `schema_version=1` | FMC recording_info.py:31 |
| Folder names | `contract_version: 1` | PJ:2 |
| Calibration TOML | None found | calibration_toml.py:180-193; CalibrationMetadata fields :15-35 of calibration_metadata.py (no version member) |
| skellycam info JSON | None | SCds recording_info.py:21-27 (no version field); RFF:58 and :63 recommend adding one |

Proposed:
- **One format version** for the folder (`major.minor.prerelease`). It is written in every sidecar header (unchanged) and in each class-a folder file.
- Each folder file keeps its own part version. SPEC.md §3 has a table of which part versions each format version allows.
- Only 7K3C item 1 changes: the source of the version is no longer the skellycam release (E/7K3C:7-10), because freemocap will write class-a files. 7K3C item 6 already ties the package `major.minor` to the format version (E/7K3C:22-23; RM:65-67). Proposed: the skellyfileformat package release becomes the source (A2).
- **Conflict to resolve (A3):** SFF-052 says a reader skips unknown fields of a higher minor (v0S:118-120). freemocap's descriptor forbids unknown fields (`Descriptor`, recording_descriptor.py:18-19). `Source.definition` is a free dict (:36), but playback validates it strictly as `CameraRecordingDefinition` (FMC `freemocap/core/recording/playback_queries.py:131`), which is a `Descriptor` (observation_inputs.py:178). So adding `camera_key` to a camera source would break installed freemocap playback. Inference from code; not run.
- The TOML has the same problem in another form (§5, C3).

---

## 4. Folder inventory (proposed classes)

a = in format, b = reserved (default: name and owner fixed, contents owner-internal; A7 decides per file), c = legacy (read-old only), d = not allowed / out. `<rec>` = folder name (RC:13, per draft).

| Path | Writer | Class | Evidence |
|---|---|---|---|
| `synchronized_videos/<rec>.id-<cam>.idx-<i>.mkv` | skellycam, converter | a | v0S §4; pattern SCds video_filename.py:7 (REV:67); folder SCds recording_info.py:46-50 |
| `.../<same stem>.skvt` | skellycam, converter | a | v0S §12 (v0S:822-833, per draft) |
| `.../<rec>.audio.mka` | skellycam | a | v0S §6; name proposed in REV:56. No writer today: not verified |
| `.../<rec>.audio.skat` | skellycam | a | v0S §7, §12 |
| Live states (`.skat.live`, live `.flac`) and `*.tmp` | skellycam | a (transient) | v0S SFF-503 (v0S:843-844). The live `.flac` and `.skat.live` stay under accepted decision 5a (REV:140: it "keeps the `.flac`/`.skat.live` delete step") |
| skellysync device files | skellysync | a | v0S §8/§14; separate `.mka` proposed (REV decision 6) |
| `<rec>_info.json` | skellycam | a (new; today out by E/TDB5:22) | Fields: SCds recording_info.py:80-104. Its `camera_configs[*].rotation` (:98-101) conflicts with E/68Z6 item 3 (§6 #23, C14) |
| `<rec>_recording_info.json` | freemocap | a | FMC recording_info.py:9-47; RC:20 |
| `<rec>_camera_calibration.toml` | freemocap calibration | a, subject to the calibration model (C11) | calibration_paths.py:18-20; authority RC:67. The same file is also written outside any take (calibration_save.py:43-48) |
| `<rec>_data.parquet` (2D plus 3D) | freemocap | a (core) plus owner extensions | arrow_schema.py:15-30 (per digest); RC:22, 66; 2D as OVERLAY_2D (REV:227). One file for 2D and 3D is REV decision 11 (proposed, C15) |
| `synchronized_videos/synchronized_videos_README.md` | skellycam | b, informative | SCds recording_finalizer.py:64, 69-71 |
| `annotated_videos/` | freemocap | b | FMC default_paths.py:13 (per draft); RC:27; REV decision 14 |
| `exports/` (csv/, npy/, .npz, run-N/, calibration_copies/) | freemocap | b | RC:29-40, 176-197; calibration-export-policy.md:9 (per draft) |
| `logs/` | none found | b, reserved with no current writer | Only `create_on_disk()` makes it (recording_structure.py:111-112, 136), and that has no production caller (§1). RFC:51 says the dataset workflow saves logs outside the recording |
| `<rec>.blend` | freemocap / Blender | b | RC:53-54; PJ:12 |
| `.processing.lock`, `*.parquet.tmp`, `*.info.tmp` | freemocap | b (operational) | parquet_writer.py:31, 75 (per draft); recording_info.py:37; RC:58-59 |
| `output_data/charuco_observations_realtime.pkl` | freemocap realtime | b (disposable cache), **writer disabled** | charuco_recorder_node.py:31, 42, 227; RC:55-58; read by video_node.py:350, 419 (`pickle.load`); disabled per app-workflow-todo.md:35-36. Safety: C17 |
| `output_data/charuco_3d_xyz.npy` | freemocap anipose path | b (cache), **writer disabled** | `freemocap/core/tasks/calibration/anipose_calibration/helpers/anipose_calibration_helpers.py:143-145`; "reconstructed-board NPY ... disabled" (app-workflow-todo.md:35-36) |
| `charuco_board_info.json` | not verified | b (optional calibration input) | RC:55 names it as an input; it gives no writer |
| `output_data/` other files (NPY/CSV), `output_data/freemocap_data_by_frame.parquet` | old freemocap | c | PJ:17, 22; RC:84; app-workflow-todo.md:30-32 (no `output_data` NPY/CSV written now) |
| **`output_data/` rule (proposed):** the two cache names above are b; every other file in `output_data/` is c | | | |
| `output/diagnostics.yaml` | reference recordings | c | RFC:55-56. RC:78 says no `output/` directory is created now |
| `tracker_schema.json` | none (read by playback only) | c | Read at FMC `freemocap/api/http/playback/playback_router.py:725`; never written (app-workflow-todo.md:31-32; test_recording_store.py:422 per digest) |
| `synchronized_videos/*.mp4`, `*.avi`, `.web.mp4` | old skellycam, imports | c | SCds video_filename.py:8 (REV:67); RFF:59 |
| Remuxed H.264 MP4 with AAC audio and a `skellycam_data` metadata tag | old skellycam remuxer | c candidate; **release status not verified** | SCds video_audio_remuxer.py:64, 69, 93; the call is commented out (recording_finalizer.py:63). Whether the video is VFR: not verified |
| `synchronized_videos/timestamps/**.csv`, `*_stats.json`, `*_stats.txt` | old skellycam | c | SCds recording_info.py:52-78; REV decision 3 accepted (no new CSVs) |
| WAV plus `audio_timestamps.json` | old skellycam | c | RFF:59 |
| Old rotated-pixel calibration TOML and 2D | old freemocap | c | HO:34; REV §7 (REV:285) |
| Imported or skelly_synchronize videos | freemocap import | c (foreign input) | mocap_router.py:337-366; REV decision 27 (proposed) |
| `.skov`, burned-in overlay files | — | d | E/W4PF:19 |
| MCAP device files (draft v1) | prerelease only | d (`not_in_format`) | S1 never released (RM:9, per draft) |
| Lichtblick layout `.json` | — | d, **if** REV decision 20 is accepted | E/WD9A and E/10JC are still accepted (§6 #25) |
| Audio track inside a camera MKV | — | d, if REV decision 6 is accepted | REV:495 |
| New legacy CSVs from new skellycam | — | d | REV decision 3 (accepted) |
| Any unknown file | anyone | ignored; **proposed:** listed in `other_files` | S1 lists only MCAP-magic files that are not in the format and ignores the rest (S1:701-702, 829-830). This widens it |

Not in the take inventory: `ready.json`. It is written in prepared dataset roots by the dataset tools (FMC `freemocap/tools/datasets/__main__.py:53`; RC:300), which live outside recording folders (RFC:61-63).

---

## 5. Names and layout

| Item | RC/PJ canonical | Written today | REV proposal |
|---|---|---|---|
| Media folder | `videos/synchronized` (RC:23-24; PJ:4) | `synchronized_videos` (SCds recording_info.py:46-50; FMC default_paths.py:12) | Keep `synchronized_videos` (REV:72, decision 10) |
| Annotated | `videos/annotated` (PJ:5) | `annotated_videos` (FMC default_paths.py:13) | Keep |
| Calibration | `<rec>_calibration.toml` (PJ:9) | `<rec>_camera_calibration.toml` (calibration_paths.py:18-20) | Keep the written name (REV:283) |
| Timing | `videos/synchronized/timestamps/camera_timestamps/` (RC:25-26) | `synchronized_videos/timestamps/camera_timestamps` (SCds recording_info.py:62-66) | `.skvt` next to its media file (v0S §12) |

**Evidence for the written names.**
- At least seven FMC production sites hard-code `synchronized_videos` (REV:65, from `git grep`). `create_on_disk()` has only a test caller and saved_observations.py:70 falls back to `synchronized_videos/` (§1).
- The Blender addon looks only in `annotated_videos` or `synchronized_videos`, and today picks a folder only if it holds a `.mp4` and lists only `.mp4` files (A73 `parquet_scene.py:160-165`, per REV:65 and DTB1:48; not re-read). It takes exactly one `*_data.parquet` from the folder root (A73 `parquet_recording.py:16-20`, per draft; not re-read).
- RC itself lists writer migration as "Pending staged work" (RC:219).

**Prior rejection.** E/25VV rejected exactly this: "The spec fixes the media file names and the `synchronized_videos/` folder (today's freemocap contract): it ties the format to a contract that belongs to skellycam and freemocap" (25VV:68-69). A names entry would reverse that rejected alternative. The reason is Dom's 11-13 decision that SFF is the spec for the whole folder.

**Recommendation (proposed).** Names as written today: `synchronized_videos/`, `annotated_videos/`, `<rec>_camera_calibration.toml`. Change RC:18-41, PJ:4-6, 9 and the frontend presets to match.
- **TC cannot just "stay green".** PJ's `legacy_v1` (PJ:14-24) holds almost exactly the names this plan makes current: `synchronized_videos`, `annotated_videos`, `{rec}_camera_calibration.toml`, `{rec}_recording_info.json`, `{rec}.blend`, `exports`, `logs`. Only `output_data` and `output_data/freemocap_data_by_frame.parquet` are really old. TC:44-56 asserts that a `synchronized_videos/` folder makes `inventory.is_legacy_layout` true, and that flag is true "if any legacy marker exists" (recording_structure.py:48). So PJ `legacy_v1` must be renamed or split, and TC:44-56 and `is_legacy_layout` must change.

**How a reader finds each file (proposed).**
- Folder files (class a/b at the root): exact fixed names built from `<rec>`. No globbing.
  - Today skellycam reads `*_info.json` (SCds recording_metadata.py:16). That glob matches both info JSONs and raises when they disagree on a field (:26-27).
  - freemocap reaches capture timing through skellycam's readers (FMC `freemocap/core/reconstruction/recording_timing.py:6-9`; SCds recording_timing_reader.py:18-31).
  - freemocap's calibration lookup falls back to globbing any `*calibration*.toml` (calibration_paths.py:35-39). Under this rule that fallback is legacy read only (C11).
- Device files: by content (magic plus sidecar), as in v0 SFF-504/550 (v0S:846-856). Only directly in `synchronized_videos/`.
- **New take or legacy: by content.** A folder is a new take when `synchronized_videos/` holds a device file with an accepted `.skvt` or `.skat` (v0 SFF-550). Names decide only for truly old outputs: `output_data/`, the old Parquet path, CSV timestamps, WAV (§18).
- `<rec>`: the folder name. Gap: the folder was renamed after writing. Proposed: compare with the name in the take facts or descriptor; if they disagree, report it, and never pick the first match (RC:87-88). See B5 for what freemocap does today.
- Membership: a take = the folder root (fixed names) plus `synchronized_videos/` (content). Other subfolders are reserved (b), legacy (c) or ignored. This replaces "no subfolders" (v0S:912-914; S1:796-798).

**Links (proposed).**

| File | Take link | Camera link |
|---|---|---|
| `.skvt`/`.skat` | `take_uuid` (v0S SFF-650, :895-897) | `camera_label`, `camera_key` (v0S:289-290). `camera_key` is a SHOULD and 0 when unset (v0S:289, SFF-162 :305); C12 |
| `<rec>_info.json` | `recording_uuid` exists (SCds recording_info.py:24). It is `str(uuid.uuid4())`, with dashes; the v0 UID text form is 32 hex digits (v0S:942). Proposed: `recording_uuid == take_uuid` after normalising both to 32 lowercase hex digits | Maps keyed by camera id (recording_info.py:86-97) |
| Parquet | None today: `recording_id` = folder name (observation_publication.py:244-245) | `camera:<id>` labels only (observation_inputs.py:186-187). Proposed: `camera_key` plus the `.skvt` file name per camera source |
| TOML | None. Proposed: `calibration_take_uuid` plus per-camera `camera_key` (TFD Q42 at TFD:62), inside `[metadata]` (C3) | Camera tables by camera ID (calibration_toml.py:180-185) |
| `<rec>_recording_info.json` | Holds the uuid **only when** a capture info JSON already exists: it copies `<rec>_recording_info.json` or else skellycam's `<rec>_info.json`, and otherwise falls back to the descriptor's `recording_info` (recording_info.py:12-16), which the production writer leaves empty (observation_publication.py:244-246; default `{}` at recording_descriptor.py:195) | — |
| `<rec>_recording_info.json` → Parquet | `processed.parquet_sha256` (recording_info.py:29-31). The Parquet and this file are replaced one after the other (parquet_writer.py:55-63), so a crash between them leaves a stale hash | — |

Placement constraint: the descriptor forbids unknown members (recording_descriptor.py:18-19). `recording_info` is a free dict (:195). Putting take facts there avoids a schema bump; a new member needs `schema_version` 2. Decision C1.

---

## 6. Conflicts with existing decisions and documents

| # | Conflict | Where | Change needed (proposed) |
|---|---|---|---|
| 1 | Scope lists device files only | E/TDB5 item 1 (:7-12) | New scope entry superseding TDB5: whole folder, all classes |
| 2 | skellycam info JSON "not part of the format" | E/TDB5 item 5 (:22); 25VV item 5 (:27-28, per draft); v0S:20; S1:24 | Same entry: both info JSONs in the format |
| 3 | Spec fixes no file or folder names; fixing `synchronized_videos/` rejected by name | E/25VV item 2 (:16-20) and rejected alternative (:68-69); DK8S item 12 (:33); W4PF item 4 (:15-17); SDD:38 (Q22), :54 (D1) (per draft) | Names entry: fixed names for class a/b; reverses 25VV:68-69 on Dom's 11-13 decision |
| 4 | Spec alone vs referencing freemocap code | E/W4PF item 3 (:12-14); REV:254 | Entry: re-specify the content, reference only container standards (§3.2) |
| 5 | No overlay file; tracking "later work" | E/W4PF items 6, 8 (:19, :21) | Keep item 6 ("overlay" = burned-in drawings). Supersede item 8: tracking Parquet in the format |
| 6 | Reader looks only directly in one folder | v0 SFF-504, SFF-654 (v0S:846, 912); S1 SFF-554, SFF-674 (S1:701, 796); test SFT-551 (C1:446-451, per draft) | Folder-opening rules (§13 of the outline) with the media folder and fixed names; rewrite the test |
| 7 | Format version = skellycam release | E/7K3C item 1 (:7-10); RM:49-53 | Versioning entry: changes only item 1; keeps items 2-6 |
| 8 | Writers = skellycam and skellysync only | E/X7FT item 2 (:8-9, per draft); X1G6 item 2 (:8-9) | Restate X7FT (MKV/FLAC) and add freemocap as writer of class-a folder files |
| 9 | Legacy reading outside the spec | E/X1G6 item 6 (:15); TDB5 item 6 (:23); v0S SFF-551 (:858-859); OW:30-31 (X1G6 items 1, 4-6 are skellycam rules) | Legacy-recognition part (§20 of the outline). Reading details stay in owner code (A6) |
| 10 | "Two documents own one file" rejected | E/5PP8, E/25VV alternatives (25VV:70-71) | **Proposed (depends on A1/A4):** moot if SFF becomes the only defining document for class-a files; record it in the scope entry |
| 11 | "Spec of the writing program defines the file" | RFF:54 | Mark RFF superseded by Dom's 2026-11-13 decision (header note) |
| 12 | Format replaces only skellycam's half | HO:31 | Status header on HO (REV:621 already lists it) |
| 13 | Layout not part of the format spec | TFD Q13 (TFD:36, per draft) | Void with Lichtblick; TFD gets a status header (REV:620 already lists this) |
| 14 | `annotated_videos/` "derived, outside the format" | REV decision 14 (REV:503) | Class b in this plan; restate the decision |
| 15 | RC/PJ canonical paths vs writers; TC treats `synchronized_videos/` as legacy | RC:18-41; PJ:4-6, 9, 14-24; TC:44-56; recording_structure.py:48 | Proposed FMC change: canonical = written names; split PJ `legacy_v1`; rewrite TC:44-56 and `is_legacy_layout` |
| 16 | Stale freemocap docs | backend-recording-structure.mdx; backend-mocap.mdx; posthoc-mocap.mdx (per draft) | Propose replacing them with a pointer to SFF (freemocap's call) |
| 17 | Missing values NaN vs null | TFD Q27 (TFD:49) vs FMC null policy (REV:228) | Adopt null (C4) |
| 18 | Confidence naming | TFD Q37 (TFD:60, `confidence`) vs Parquet `visibility` 0..1 (REV:227, 233) | Use `visibility` in the Parquet; record the NWB mapping as informative (C5) |
| 19 | Unknown-field rule vs `extra="forbid"` | v0S SFF-052 (:118-120) vs recording_descriptor.py:18-19; playback_queries.py:131; calibration_toml.py:113-118, 126, 183-185 | Versioning entry: forward-compat rule per part (§3.4, A3) |
| 20 | Revived v0 IDs were withdrawn in S1 | S1:699 and neighbours; E/TDB5 item 9 (:28-29) | New IDs that cite the v0 IDs |
| 21 | Scope and README say MCAP | RM:3-7, 15-37; OW:6-33 | Rewrite after the entries (REV:593-640 lists the reversal entries) |
| 22 | Recording info `processed` vs app-workflow-todo "Recording metadata JSON ... left untouched" | app-workflow-todo.md:32-33 vs parquet_writer.py:63 | `write_recording_info` writes only `<rec>_recording_info.json` (recording_info.py:11, 45), so "left untouched" can only be true of skellycam's `<rec>_info.json`. Ask freemocap to reword |
| 23 | Rotation written outside `display_rotation` | E/68Z6 item 3 (:12-13) vs SCds recording_info.py:98-101 (`camera_configs[*].rotation`) | C14 |
| 24 | Reader state names | E/WG08 items 2-5 (:13-27) vs v0 SFF-666 (v0S:983-989) | Take WG08's states and codes; `folder_files` extends that vocabulary (D2) |
| 25 | Opus audio and Lichtblick still accepted | E/D9N1 (accepted 2026-11-13); E/WD9A, E/10JC (accepted) | D9N1 superseded by Dom's FLAC decision (REV:140); WD9A and 10JC superseded only if REV decision 20 is accepted |
| 26 | DK8S accepted as a whole (MCAP profile files and names) | E/DK8S (items 2, 8, 11, 12) | Supersede in full; port items 2, 8, 11 content per REV:638 |

---

## 7. Gaps to fill

| Gap | Proposed approach |
|---|---|
| Membership across subfolders | Root plus `synchronized_videos/` only (§5). Reserved subfolders listed by name |
| Names vs discovery; both programs reading `*_info.json` | Exact-name reads; a spec rule that a reader never globs folder files; change SCds recording_metadata.py:16 |
| Take linkage for Parquet, TOML, info JSONs | §5 links table; cross-file tests (§9) |
| `camera_key` optional in v0 | C12. Without it the per-camera links have nothing to match on |
| Versioning of non-sidecar files | Part-version table (§3.4); add a version to the TOML (inside `[metadata]`) and to the skellycam info JSON |
| Schemas only in code (TOML fields and units, recording info fields, nodes/edges) | Write them into `spec/parts/`. TOML translation units: probably mm (REV:286, from the addon); not verified |
| Synchronized (multi-frame) timing in a new take | No CSVs (REV decision 3). Today freemocap's synchronized timeline and skellycam's statistics read the multiframe CSV through `multiframe_timing` (SCds recording_info.py:97; recording_statistics.py:13-17; FMC recording_timing.py:36-47). C13 |
| Calibration model | C11 |
| Reader result covers device files only | Add `folder_files` with each fixed-name file and a state that extends E/WG08 (proposed: `present`, `missing`, `ambiguous`, `invalid`, `legacy`, `reserved`), plus `take_links` checks |
| Derived and cache files unclassified | §4 class b; depth decided per file (A7) |
| Crash and atomic rules for non-media files | Every class-a folder file is written tmp, fsync, replace. Today skellycam's info JSON is not (SCds recording_info.py:103-104); freemocap's are (recording_info.py:37-47; parquet_writer.py). Rule for a stale `parquet_sha256` after a crash between the two replaces (parquet_writer.py:55-63) |
| Privacy | SFF-653 widened to all class-a files. Today `recording_directory` is absolute (SCds recording_info.py:23) and is copied into recording info (FMC recording_info.py:12-16). It reaches the TOML metadata by this code path: `result.recording_info = recording_info` (posthoc_calibration_task.py:137), then `save_calibration_copies(save_fn=result.save_toml ...)` (:142-146), with `recording_info: RecordingInfo` in CalibrationMetadata (calibration_metadata.py:30). Code path read; not verified by writing a file. MFR:59, 114 |
| Safety of cache files | The ChArUco cache is unpickled from the take folder (video_node.py:419). C17 |
| skellysync folders | A take folder with device files only. RFF:48 says skellysync's SCOPE never mentions an info JSON (SCOPE not re-read) |
| Imported takes | Class c (REV decision 27). After a skelly_synchronize run each destination is named `<src.stem>.mp4` whatever its contents (mocap_router.py:357); without sync the original names are kept (:359-360) |
| Legacy freemocap outputs | Recognise by content first; names only for `output_data/`, the old Parquet path, CSVs and WAV. PJ `legacy_v1` is split (§5) |
| Frame grid and `filled` flag | REV decision 17 (proposed). Spec says Parquet `frame_number` = `.skvt` write index (REV:231, from recording_timing.py:27-35) |
| Parquet run_ids, realtime vs posthoc | Spec states only that `run_id` exists and `selected_run_id` names a retained run (recording_descriptor.py:194, 198-204). Realtime persistence is REV decision 12 (C16) |
| Rotation of 2D/calibration under sensor orientation | Parquet image width/height and 2D in stored-pixel space (TFD Q10, TFD:33). Old takes are rotated (HO:34). Desk test DT-K3 |
| Two rotation values in one take | `camera_configs[*].rotation` vs `.skvt` `display_rotation` (C14) |
| Renamed or moved folder | `<rec>` mismatch rule (§5, B5) |
| Pixel origin convention of OVERLAY_2D | Not verified (REV:236). Desk test before spec text |
| Readers outside freemocap's Python | Blender addon (`.mp4` filters, TOML choice, rotation; DTB1:48-50, REV:284) and freemocap-ui Electron (`freemocap-ui/electron/main/api.ts`, per REV:65-67; not re-read) |

---

## 8. Decisions for Dom (all proposed)

Grouped for a grilling session. The outline blockers come first.

**Group A: scope and governance (block the outline)**
- **A1 Scope model.** (a) SFF fully defines every file. (b) SFF fully defines the device files, the folder rules and a frozen core of the freemocap files; owner extensions reserved. (c) SFF covers the folder rules only and references owner docs. **Recommend (b).** (a) freezes freemocap internals; (c) fails W4PF item 3.
- **A2 Source of the format version.** Only 7K3C item 1 changes; item 6 (package `major.minor` = format version) already exists (E/7K3C:22-23). (a) Keep item 1 (skellycam release). (b) The skellyfileformat package release is the source. **Recommend (b).**
- **A3 Versioning scheme.** (a) One format version plus a part-version table, with a forward-compat rule per part (SFF-052 vs `extra="forbid"`). (b) Independent per-file versions only. **Recommend (a).**
- **A4 Governance.** A change to a class-a part of a freemocap file needs an SFF entry first; RC cites SFF for the folder. (a) Yes. (b) RC stays the authority for freemocap files. **Recommend (a)**, subject to freemocap maintainers' agreement (not verified).
- **A5 Info JSONs.** (a) Both in the format, each with a defined core, exact-name reads, and a precedence rule for the capture fields that `<rec>_recording_info.json` copies (recording_info.py:12-16): proposed, `<rec>_info.json` wins and a disagreement is a warning. (b) Merge into one `<rec>_recording_info.json` (REV decision 18b). **Recommend (a)** for reuse; (b) is the cleaner option.
- **A6 Legacy in SFF.** (a) SFF defines recognition plus the reader result for legacy layouts; reading stays in owner code. (b) Fully out (X1G6 item 6). **Recommend (a).**
- **A7 Depth for class-b files** (Dom's "must include all of the associated sidecar files"). Per file: (i) fully specified, (ii) name and owner only, (iii) out of the folder. Recommend: (i) for `charuco_board_info.json` (a calibration input other programs read); (ii) for `annotated_videos/`, `exports/`, `<rec>.blend`, `logs/`, lock and tmp files, the README; (iii) or (ii)-with-safety-rule for the ChArUco pickle (C17); (ii) for `output_data/charuco_3d_xyz.npy` while its writer is disabled. Only (i) for every file matches Dom's wording literally; (ii) is a narrower reading Dom must confirm.
- **A8 JavaScript reader scope.** (a) Covers all class-a files, including Parquet and TOML. (b) Device files plus folder rules and the JSONs; Parquet and TOML parts Python-only, with the reader result marking them "not checked". **Recommend (b)** for now; JS Parquet/TOML dependencies would have to be pinned exactly. Not verified which JS libraries would be needed.

**Group B: names and layout**
- **B1 Media folder.** (a) `synchronized_videos/`. (b) `videos/synchronized/`. **Recommend (a)** (§5). This reverses E/25VV's rejected alternative (25VV:68-69).
- **B2 Calibration name.** (a) `<rec>_camera_calibration.toml`. (b) `<rec>_calibration.toml`. **Recommend (a).**
- **B3 Fixed names.** (a) Fixed names for folder files, content discovery for device files. (b) Writer-chosen names everywhere. **Recommend (a).**
- **B4 Device file names.** (a) Fix skellycam's pattern `<rec>.id-<cam>.idx-<i>` (SCds video_filename.py:7) as a MUST for writers, with readers still binding by content. (b) A SHOULD. **Recommend (b)**: v0 readers take only the sidecar binding and the temp state from names (SFF-502, v0S:840-841; the manifest part is withdrawn).
- **B5 Renamed folder.** (a) Report a mismatch and continue with the found files. (b) Refuse. **Recommend (a)** for the SFF reader. Consequences today: freemocap refuses to publish a Parquet whose `recording_id` differs from the folder name (parquet_writer.py:44-45), and the exact-name TOML lookup misses (calibration_paths.py:32), falling to the glob.
- **B6 New vs legacy recognition.** (a) By content (an accepted `.skvt`/`.skat` in the media folder); names only for truly old outputs. (b) By PJ `legacy_v1` names. **Recommend (a)**; (b) would call every new take legacy (§5).

**Group C: content and links**
- **C1 take_uuid in the Parquet.** (a) In `recording_info` (free dict, no schema bump). (b) A new descriptor member and `schema_version` 2. **Recommend (a)** for installed readers. `recording_info` is empty today (observation_publication.py:244-246), so (a) also needs a writer change. Not verified that `recording_info` round-trips.
- **C2 Per-camera link in the Parquet.** `camera_key` plus `.skvt` name in the camera source. Needs a freemocap change because of strict validation (playback_queries.py:131). (a) Coordinated freemocap change. (b) Link by `video_filename` only. **Recommend (a).**
- **C3 TOML.** Add a version, `calibration_take_uuid` and per-camera `camera_key`; drop embedded paths. They must go **inside `[metadata]` and the camera tables**: every top-level table other than `metadata` is parsed as a camera (calibration_toml.py:183-185). Installed freemocap drops them on round-trip: the metadata loader copies only known fields (:113-118), `CameraToml` ignores unknown keys (:126), and `from_camera` writes no `camera_key` (:140-152). Inferred from code, not run. **Recommend yes, with a coordinated freemocap change.**
- **C4 Missing values.** (a) null (Parquet today). (b) NaN (TFD Q27). **Recommend (a).**
- **C5 Confidence.** (a) `visibility` 0..1. (b) Rename to `confidence`. **Recommend (a).**
- **C6 2D pixel space.** Stored-JPEG pixels under sensor orientation (TFD Q10). **Recommend yes, after DT-K3.**
- **C7 Skeleton nodes and edges.** (a) In the Parquet descriptor. (b) Bring back tracker_schema.json as class a. (c) Defer. **Recommend (c)** now, then (a).
- **C8 Derived and cache files** as class b, reserved names. **Recommend yes**, with depth per A7.
- **C9 Imported takes.** (a) Legacy or foreign inputs. (b) Convert at import. **Recommend (a)** (REV decision 27).
- **C10 skellysync folder.** Device files only; info JSON optional. **Recommend yes.**
- **C11 Calibration model.** The TOML is written in the calibration take's folder and also to `~/freemocap_data/calibrations/<rec>_camera_calibration.toml` and `last_successful_camera_calibration.toml` (calibration_save.py:37-51; calibration_paths.py:15, 23-25). A mocap take finds its TOML by exact name, else by glob (calibration_paths.py:28-39), and the geometry used is frozen into each Parquet run (RC:67; `CameraModel` imported into the descriptor, recording_descriptor.py:11-12). Questions: (i) is a standalone TOML outside a take folder in the format; (ii) does a consuming take reference its calibration by `calibration_take_uuid` only, or also hold a copy; (iii) does the glob fallback stay as legacy read; (iv) which wins when TOML and Parquet geometry disagree. **Recommend:** standalone TOMLs are in the format as files (same schema, no take membership); a consuming take holds a copy plus `calibration_take_uuid`; glob is legacy read only; the Parquet run's frozen geometry wins for that run, and a disagreement is a warning.
- **C12 `camera_key` MUST.** v0 makes it a SHOULD, 0 when unset (v0S:289, 305); TFD Q42 wants a MUST for capture writers (TFD:62). (a) MUST for skellycam capture; skellysync and the converter may write 0. (b) Stay SHOULD. **Recommend (a).** When the key is 0, cross-file camera checks fall back to `camera_label` and report a warning.
- **C13 Info JSON timing members and the synchronized timeline in new takes.** Today `camera_timing` and `multiframe_timing` hold CSV paths (SCds recording_info.py:93-97). Options: (a) `camera_timing` points at each `.skvt`, `multiframe_timing` is absent, and the spec defines the synchronized time per frame from the `.skvt` player times (SFF-176, REV decision 16). (b) Both absent; readers derive everything from the `.skvt` files. **Recommend (a)**, with the synchronized timeline defined in the spec, because freemocap's readers key off these fields (§10 D5).
- **C14 Rotation in `camera_configs`.** (a) New takes write no `rotation` in `camera_configs` (E/68Z6 item 3). (b) Keep it, defined as the requested setting, with `.skvt` `display_rotation` authoritative. **Recommend (a)**; if (b), a cross-file test checks they agree.
- **C15 Tracking file shape** (REV decision 11). (a) One Parquet with 2D and 3D. (b) Separate files. **Recommend (a).**
- **C16 Realtime tracking persistence** (REV decision 12). (a) Publish a Parquet run at take end through the existing writer (not verified, DT10). (b) Live CRC-framed journal folded into the Parquet later. **Recommend (a)** for phase 2; (b) if realtime results must survive a crash.
- **C17 Cache safety.** Format readers never execute file content. (a) The ChArUco pickle is replaced with a non-executable format or tracker records (REV decision 19b). (b) Keep the pickle, loaded only from folders this install wrote. **Recommend (a).**

**Group D: reader and writing**
- **D1 Subfolders.** Root plus the media folder only. **Recommend yes.**
- **D2 Reader result.** File states and codes from E/WG08; add `folder_files` and `take_links` sections that extend WG08's vocabulary. **Recommend yes.**
- **D3 Atomic writes** for all class-a folder files. **Recommend yes.**
- **D4 Privacy** rule over all class-a files: no absolute paths, user names or raw serials. **Recommend yes.**
- **D5 Release gate.** No skellycam release writes the new format until freemocap reads it (§10 step 7). **Recommend yes.**

---

## 9. Test list outline

Proposed families, with SFT IDs assigned at gate 1.

| Family | What it checks |
|---|---|
| F1 Folder discovery | Fixed names found; no glob; unknown files listed in `other_files` (widened, §4); `.tmp` ignored |
| F2 Membership | Root plus `synchronized_videos/` only; device files elsewhere are ignored and reported |
| F3 Names | Writer emits the fixed names; `<rec>` = folder name; renamed folder gives a mismatch warning |
| F4 Device files | Revived v0C tests (header, records, index PTS, FLAC, binding by Segment UID) |
| F5 Per-file validation | Info JSON schemas; TOML schema; Parquet columns, descriptor core, null policy, grid rules |
| F6 Cross-file: take | take_uuid equal across `.skvt`, `.skat`, info JSON (after UID normalisation), Parquet, TOML; mismatch → warning code |
| F7 Cross-file: camera | camera_key in the Parquet source and the TOML matches a `.skvt`; duplicate or missing key; key 0 → label fallback plus warning |
| F8 Cross-file: frames | Parquet `frame_number` per camera within `[0, n_records)` of its `.skvt` |
| F9 Cross-file: dimensions and rotation | Parquet image width/height = MKV stored dimensions (sensor orientation); `display_rotation` from `.skvt`; `camera_configs` rotation absent or agreeing (C14) |
| F10 Cross-file: references | Parquet `video_filename` resolves to a present `.mkv`; info JSON `videos` and timing maps resolve; `processed.parquet_sha256` matches the Parquet |
| F11 Missing and ambiguous | Two Parquets, two TOMLs, both info JSONs disagreeing → `ambiguous`, no first pick (RC:87-88) |
| F12 Crash | Killed take: live device files plus a missing or tmp Parquet/info JSON; Parquet new but recording info stale (hash mismatch); duplicated capture fields that disagree |
| F13 Legacy | Truly old folder (`output_data/`, old Parquet path, MP4+CSV, WAV), mixed layout → `legacy` states, no writes; a new take with `synchronized_videos/` is **not** legacy |
| F14 Privacy | Writer output contains no absolute path, user name or raw serial |
| F15 Read-only | The reader never creates, moves or edits files (RC:51, 91-92; TC:44-61 pattern) |
| F16 Timing | A new-format take's per-camera and synchronized timing method is `recorded`, never a silent `inferred_from_fps` or `mean_camera_times` (SCds recording_timing_reader.py:34-37, 72-77; FMC recording_timing.py:42-47) |
| F17 Calibration | TOML geometry vs the geometry frozen in the Parquet run; standalone TOML outside a take; glob fallback only in legacy mode |
| F18 Safety | The reader never unpickles or executes folder content (C17) |
| F19 JS parity | JS reader result equals the canonical result for the parts A8 assigns it |

**Golden folders needed.**
1. Capture-only take (cameras plus audio).
2. Processed take (plus Parquet, TOML, both info JSONs).
3. Rotated camera (`display_rotation` 90).
4. Crashed take, including a stale `parquet_sha256`.
5. Two takes in one folder.
6. Ambiguous folder files.
7. Mismatch set: take_uuid, camera_key, frame range, dimensions, rotation, unresolved `video_filename`.
8. Renamed folder.
9. Legacy freemocap folder (`output_data/` results, old Parquet path).
10. Real mixed layout: `synchronized_videos/` with MP4 + CSVs, `output_data/`, a root Parquet, `output/diagnostics.yaml`.
11. Imported videos (with and without skelly_synchronize).
12. skellysync folder.
13. Privacy violation.
14. Calibration take plus a consuming take that holds a copy.

---

## 10. Work plan

1. **Grill Dom on Group A, then B** (§8). Gate: Dom's answers recorded as accepted only on Dom's word.
2. **Write the SFF decision entries** as `proposed`:
   - reversal entries (REV:593-640), including D9N1, DK8S and, if REV decision 20 is accepted, WD9A and 10JC;
   - whole-folder scope (supersedes TDB5 items 1, 5, 6);
   - names (supersedes the 25VV/DK8S/W4PF item 4 lineage, reverses 25VV:68-69);
   - versioning (changes 7K3C item 1 only);
   - read-old (restates X7FT; replaces X1G6);
   - tracking (supersedes W4PF item 8);
   - reader result (WG08 ported plus folder sections).
   Gate: Dom accepts each one. Local commits only, after asking.
3. **Desk tests that block spec text:** 2D pixel convention (DT-K3), descriptor round-trip of `recording_info` (C1), addon on an MKV take (DT-B3), addon rotation from `display_rotation` (DT-B4). Gate: results files.
4. **Spec draft v2, whole folder** (§3 outline) plus a conformance test list (§9). Built from the entries, not from S1 (REV:640). Gate 1: Dom's review.
5. **Proposed freemocap doc changes** (written as proposals, not applied): RC Paths and Compatibility cite SFF; PJ canonical = written names and `legacy_v1` split; TC:44-56, `is_legacy_layout` and layout presets follow; app-workflow-todo.md:32-33 reworded; stale freemocap-docs pages. Needs Dom's approval. freemocap is not tested now (Dom, 11-13).
6. **Runnable tests plus golden folders.** Gate 2: Dom's review.
7. **Implementation**, in this order:
   - skellyfileformat reader and writer (Python; JS per A8).
   - **Integration seam:** freemocap already reads capture data through skellycam's readers: `recording_timing_reader` (FMC recording_timing.py:6-9), `recording_statistics`, `VideoAssociations`, and `RecordingInfo` (imported by calibration_metadata.py:4 and posthoc_calibration_task.py:18). Switching those skellycam readers to skellyfileformat reaches freemocap through a skellycam pin bump. "We'll implement our reader into freemocap" then covers the Parquet/TOML side.
   - skellycam writer changes: atomic info JSON, no `recording_directory`, take_uuid, exact-name read, C13 timing members, C14 rotation. These go through the RC:93-94 human-owned handoff.
   - **Release gate (D5):** no skellycam release writes the new format until freemocap reads it. Reason: with no CSVs and no timing fields, freemocap silently falls back to nominal-fps timing per camera (SCds recording_timing_reader.py:18-24, 72-77) and to the mean of camera times for the synchronized timeline (FMC recording_timing.py:42-47). If `camera_timing` points at a `.skvt`, the CSV parser path is taken (recording_timing_reader.py:61-64); how it fails on binary input: not verified. RC:94 requires freemocap to keep accepting installed capture output.
   - Blender addon: MKV filter (parquet_scene.py:161, 165; add_capture_cameras.py:142, per DTB1:48), TOML selection by freemocap's rule (REV:284), rotation from `display_rotation` (via the Parquet camera source or an SFF reader; DT-B4).
8. Nothing is pushed anywhere without asking Dom. Research write-ups stay as Markdown in SC\research.

---

## 11. Risks

- **freemocap coupling.** Class-a freemocap files need SFF changes first. That can slow freemocap work, and freemocap's maintainers have not agreed to it (not verified).
- **Installed readers break.** Parquet: `extra="forbid"` (recording_descriptor.py:18-19) and strict camera-source validation (playback_queries.py:131) mean new fields can break shipped freemocap. TOML: a new top-level table would be parsed as a camera (calibration_toml.py:183-185), and new `metadata` or camera keys are dropped on re-save (:113-118, :126). Inferred from code, not run.
- **Change-over gap.** A skellycam release that writes the new format before freemocap reads it gives silently inferred timing (§10 step 7). Mitigated only by D5.
- **Canonical-name churn.** Changing RC/PJ breaks TC:44-56 and `is_legacy_layout`, and touches the frontend presets. Moving files instead would touch many sites (REV:65).
- **Scope growth.** Specifying the TOML, both JSONs, the Parquet core and the calibration model multiplies the gate-1 review load. The JS reader multiplies it again under A8(a).
- **Moving target.** freemocap dev-streaming code is the source for the Parquet and TOML schemas, and it changes. Pin the commit in the spec's evidence.
- **Unverified pieces.** Pixel convention, TOML units, the addon on MKV (DTB1:48), the import outputs (REV:378), remuxed-MP4 release status, the `charuco_board_info.json` writer, the JS libraries for A8(a).
- **Privacy.** Absolute paths may already be in shared TOMLs and recording info files (MFR:114). Old files stay as written (read-old).
- **Safety.** A shared take with a crafted ChArUco pickle runs code when freemocap posthoc loads it (video_node.py:419), if the realtime cache path is ever re-enabled or a user supplies the file. Inferred from code, not run.
- **Legacy breadth.** Mixed real-world layouts (RC:85-86) may not fit clean recognition rules.

Not re-read for this plan: arrow_schema.py (columns and validation, :15-30, :126-257), observation_publication.py:103-108, the 02-pipeline guides, REAL_DATA.md, skellysync's SCOPE, the freemocap-docs pages, A73 (cache not found), freemocap-ui. Those citations come from the digest, REV or DTB1.

---

## Grilling log

### Round 1 answers (Dom, 2026-11-15)

- **A1 Scope: (a) accepted.** skellyfileformat fully defines every file. "This must be a spec that others can implement to create compatible folders, or read the output from freemocap."
- **A2 Format version: from freemocap**, not from skellycam or the skellyfileformat package. A change to the Parquet format also requires a skellycam update.
- **A6 Legacy: yes (a)**, plus a scan of every previous freemocap release (not alpha builds) for file types and quirks. The scan started 2026-11-15.
- **B1 `synchronized_videos/`: yes.** **B2 `<rec>_camera_calibration.toml`: yes.** **B3 fixed names for folder files, device files found by content: yes.** **B4 device-file name pattern is a SHOULD: yes.** **B6 new vs legacy recognised by content: yes.** **C12 `camera_key` MUST for skellycam capture: yes.** **D1 root plus `synchronized_videos/` only: yes.**
- **D5 Release gate: no.** freemocap and skellycam v2.x.x release at the same time. skellycam v2.0.0 prereleases can be built freely until then.
- **B5 Renamed folder:** Dom asked for examples (round 2).
- **New question from Dom:** what is the impact of putting the `.skvt`/`.skat` data into restructured CSVs, so it stays human-readable? This reopens REV decisions 2 and 3 (round 2).

### Round 2 answers (Dom, 2026-11-15)

- **Q1 (CSV timing files):** not yet decided. Dom asked how audio is handled now ("a single file would be preferable"), how important `.skvt`/`.skat` are, what they are for, and what happens without them.
- **Q2 version = freemocap major.minor that last changed the format, with skellyfileformat and skellycam in step: yes.** **Q3 every file change goes through a skellyfileformat spec change approved by Dom: yes.**
- **Q4 third-party formats specified by name, container and content mapping: yes.** The spec should also describe the `.blend` contents (the scene, how the cameras are laid out). That is future freemocap work, to be defined as freemocap writes `.blend` files.
- **Q5 renaming:** the take folder can be renamed to anything. **A manifest file explains all the file and folder links** (this reverses TDB5 item 2, "no manifest"). Renaming files inside the take folder breaks things and is not allowed.
- **Q6 two info JSONs, no copied fields: yes.** **Q7 adopt the Parquet conventions: yes.** **Q8 proper link fields, Parquet descriptor schema_version 2, TOML fields: yes.** **Q9 2D in stored-JPEG pixels: yes.**
- **Q10 skeleton definitions:** a sub-agent is researching how this was done before, why it was dropped, and later upstream branches (sfn26).
- **Q11 calibration:** Dom asked what "glob becomes legacy-read only" means. Background from Dom: a calibration file is a setup file. Several takes with the same setup can reuse it. It changes only when the setup changes (a camera moved, a different lens or focus). It is always produced from a take, but keeping that calibration take is optional (heavily desired).
- **Q12:** Dom asked what else is in `camera_configs`.
- **Q13 realtime tracking must be crash-safe.** A sub-agent is researching: what the Parquet holds (raw 2D, all realtime data, or only 3D), crash-safe live formats folded into a Parquet at the end, and how a realtime run is marked so users know it may be noisy.
- **Q14 pickle:** Dom asked for an example.
- **Q15 reader results and privacy: yes.** Dom asked how temp-file-and-rename affects crash resilience.
- **Q16 Python reference reader covers every file, JavaScript only what the player needs: yes.**
- **Q17 family plus narrowest release range: yes. Only v1 or later files are supported.** **Q18 informative legacy annex: yes.** **Q19 named warnings for known-bad legacy data: yes.** **Q20 download the pinned skelly_synchronize and Blender addon versions: yes**, via a sub-agent (running).

### Round 3 answers (Dom, 2026-11-15)

- **R3-Q16 Blender addon outputs are spec files with exact names; in new takes they move to one owned folder (e.g. `blender/`), with `<rec>.blend` at the root; the addon pickle is dropped; legacy addon layouts go in the annex: yes.**
- Dom's bare "yes" covered R3-Q16 only.
- **R3-Q2 one sidecar per media file: video + its own CSV sidecar** (so timing sidecars are CSV, replacing REV decision 2, binary). Dom also wants a standard audio file with one CSV timing sidecar that plays in standard players such as VLC. A sub-agent is investigating and may run tests.
- **R3-Q11 skeleton definitions in the Parquet descriptor (sfn26 `tracker_connections`, plus a documented plain-JSON segment topology), no tracker_schema.json: yes.**
- **R3-Q12:** not yet decided. Dom asked whether "off thread" means it does not disrupt other tasks.
- **R3-Q13 store everything realtime computes, float32 in the journal: yes.** A sub-agent is investigating why the Parquet uses float64.
- **R3-Q14 mark realtime runs (origin, coverage, null visibility for skipped frames, reader warning): yes. What posthoc does with a realtime run is freemocap's business**, so the spec does not define it.
- **R3-Q15 delete the journal only after a verified fold, keep it on failure, fold leftovers at start-up: yes.**
- R3-Q1 (implied by R3-Q2, to confirm) and R3-Q3 to R3-Q10: not yet answered.
- Research saved 2026-11-15: `legacy_release_inventory_20261115.md`, `legacy_sync_and_blender_addon_20261115.md`, `skeleton_definition_history_20261115.md`, `realtime_tracking_storage_20261115.md`.

### Round 3, continued (Dom, 2026-11-15)

- **R3-Q1 every camera and the audio keep per-frame/per-packet timing in their own CSV sidecar: yes** (replaces REV decision 2, binary).
- **R3-Q3 fixed-name manifest `recording_manifest.json` (format version, take_uuid, original recording name, every file with its role, camera links; skellycam writes it at start and finish, freemocap updates it under `.processing.lock`): yes.**
- **R3-Q4 missing manifest: rebuild by scanning, warn `manifest_missing`, offer to rewrite: yes.**
- **R3-Q5 calibration as a setup file (calibration_uuid, optional source_take_uuid, identical copy in each take recorded in the manifest with a hash, new uuid on setup change, glob only for v1 reads): yes.** Dom asked what "the library copy in ~/freemocap_data/calibrations/, same schema" means.
- **R3-Q6:** a sub-agent will review where camera information goes (camera_configs in the info JSON, the manifest, the per-camera CSV sidecar headers), what skellycam and freemocap read from where today, and what makes a useful human-readable overview of the take.
- **R3-Q7: no.** "Users can enter names and they can contain private info." (Interpretation to confirm in round 4.)
- **R3-Q8 ban pickle and other code-running formats; ChArUco observations as tracking rows: yes.** **R3-Q9 writing rules (whole files via .tmp+flush+replace; live files append+flush; readers report stray .tmp; Windows replace-in-place kill test): yes.** **R3-Q10 pre-v1 folders identified as unsupported: yes.**
- **R3-Q17: yes to the change, but most values move to float32 and only the values that need it stay float64.** A sub-agent will run every test needed to confirm reader compatibility, and assess whether zstd is a standard Parquet option and what other compression settings would do.
- R3-Q18 (WAV vs FLAC): Dom asked for Opus to be assessed too (sub-agent running). R3-Q12 and R3-Q19: not yet answered.

### Round 4 answers (Dom, 2026-11-15)

- **R4-Q1 `last_successful_camera_calibration.toml` is a plain identical copy of the newest library file; takes reference calibrations only by `calibration_uuid`, never by that name: yes.**
- **R4-Q2 privacy of camera identity:** the device model string is not safe either. "Warn users if there is private data, but otherwise the goal of the field is to identify a camera as specifically as possible, which necessitates friendly names, serial numbers, or other private information." This reverses v0 SFF-653 and DK8S item 8 ("never a raw serial") for camera identity fields. Scope and warning mechanism to confirm (R4-Q3, R4-Q4).
- **Privacy, final (Dom, 2026-11-15): private information is allowed in any field** (all 31 rows of the private-field table given in chat, including absolute paths). Users get an option to strip some fields where practical. This replaces the privacy ban in R3-Q15 and the v0 SFF-653 / DK8S item 8 rules; R4-Q3 (scope of a ban) is moot. Earlier R4-Q2 guidance stands: warn users when private data is present.
- **R4-Q5 strip option: dropped for now** (Dom, 2026-11-15). "Just tell the user what's in the file. Stripping it can be a later feature."
- Dom asked for all remaining open questions to be asked again together once every sub-agent has reported (pending: Opus audio assessment; Parquet float32/float64 and compression tests).
- **Audio testing priority (Dom, 2026-11-15):** test how the audio file syncs in skellycam's own playback; that is the most important playback type. Being slightly off in VLC is OK. A sub-agent is testing WAV, FLAC and Opus (fragmented MP4) in skellycam's player path. Opus results saved: `recording_upgrade/results/audio_single_file/opus/FINDINGS.md`.
- Parquet number-type and compression tests saved: `recording_upgrade/results/parquet_dtypes/FINDINGS.md` (proposed: `value` float32 + `value_f64` float64 by per-channel dtype, byte-stream-split, no dictionary on value columns, ZSTD level 3: about 36% of today's file; avoid LZ4 (freemocap-ui's hyparquet-compressors fails) and BROTLI).
- Audio sync in skellycam playback saved: `recording_upgrade/results/audio_single_file/skellycam_playback/FINDINGS.md`. skellycam has no audio playback today; in a harness of the planned player, WAV, FLAC and Opus fMP4 all sync to within 0.24 ms (clock) on a 60-minute take when the player uses the CSV fit and the audio output clock; without the fit, drift reaches 35.6 ms at 59 min. All sub-agents have reported; next: the combined round of open questions.

### Round 5 answers (Dom, 2026-11-16)

- **Q1 audio format:** not yet decided. A sub-agent will review Opus further: does a crashed file still seek correctly, and what is the repair process?
- **Q2 insert silence for audio gaps, flagged in the CSV: yes.** **Q3 normative reader-timing section (CSV fit, stated sample offset, PREV frame by sidecar time) plus an informative player-guidance annex: yes.**
- **Q7 exports print float32 in shortest exact form, checks compare in float32: yes.** **Q8 manifest `privacy` list + `may_contain_private_data` in the reader result + freemocap notice on export/share: yes.**
- **Q12 manifest `summary` block as the informative overview (amend 68Z6; no README; drop synchronized_videos_README.md): yes.** **Q13 manifest `warnings[]` (skellycam at finish, freemocap appends): yes.**
- **Constraint (Dom): skellycam must not write Parquet files.** It writes standard video, standard audio and human-readable sidecars only. Once freemocap generates tracking data, freemocap copies/migrates that data into the Parquet file.
- Not yet answered: Q4 (realtime journal), Q5 (Parquet two value columns + encodings), Q6 (accept fastparquet incompatibility), Q9 (camera_key link key), Q10 (labels and file names), Q11 (one fact, one home), Q14 (no per-row wall-clock columns).
- **Opus crash follow-up saved:** `recording_upgrade/results/audio_single_file/opus_crash/FINDINGS.md`.
  - A process kill leaves per-packet fMP4 ending on a complete fragment (0 torn bytes, 8/8). The planned player seeks killed files sample-exactly (240/240, E35 + E45), the same as WAV.
  - fMP4 needs no repair after a kill, for skellycam or for standard players. Truncation to the last complete moof+mdat is needed only for power-loss torn tails. Remuxing to plain MP4 breaks the planned player.
  - MKA needs an 11-byte Duration write, and the planned player can't index it.
  - Cost of per-packet fragments, crashed or clean: open time grows linearly (VLC about 6.5 s/h, FFmpeg about 4.2 s/h). Re-fragmenting to 1 s fixes it, losslessly.
  - Player rules needed: clamp to min(CSV cover, indexed length); skip index entries that run past EOF; fit from the CSV rows when the footer is missing (also needed for WAV).
- **Follow-up, Opus with 1 s fragments written live** (Dom asked whether 1–2 s of loss per crash is acceptable): `opus_crash/FINDINGS.md` §7.
  - Loss per kill 54.5–990.5 ms (16 kills); torn tail 0/16; about 53.7 MB/h mono.
  - Found a defect in the proposed repair: blind zero-tail stripping cuts a good last fragment when the audio ends in 0x00 (2/8 per run). Strip only when the box walk is incomplete.

### Round 6 answers (Dom, 2026-11-16)

- **Q1 audio format: Opus in fragmented MP4 with 1 s fragments, written live** (Dom: "size matters, and losing 1-2 seconds from a crash and a clean up is also acceptable"). This replaces D19's FLAC and decision 4 of the v0 revival. Evidence: `opus_crash/FINDINGS.md` §7 (loss under 1 s per kill, about 53.7 MB/h mono) and §2–§3 (seek accuracy, repair).
  - Writer settings, proposed: libopus, 20 ms packets, VBR, `empty_moov+default_base_moof`, `frag_duration=1000000`, `flush_packets=1`, standard pre-skip (no ps0). The bitrate per channel count is still to be agreed; tests used 128 kbit/s mono.
  - Recovery, proposed: truncate to the last complete moof+mdat. Strip a zero tail only when the box walk is incomplete. Then write the CSV `# fit` / `# end` footer from the rows. No remux.
  - File name, proposed: `<rec>.audio.m4a` + `<rec>.audio.csv` (`.m4a` needs `-f mp4` when remuxed).
- Still open: Q2 (crash reader rules) and Q3–Q9 of the combined round.
- **Audio (b) crash clean-up: accepted (Dom, 2026-11-16).** Truncate to the last complete fragment. Strip a zero tail only when the box walk is incomplete. Write the CSV footer from the rows. No remux.
- **Audio (c) file names `<rec>.audio.m4a` + `<rec>.audio.csv`: accepted (Dom, 2026-11-16).**
- **Audio (a) writer settings: open.** Dom asked whether it needs libopus, how well libopus is maintained, and which other encoders exist or were tested.
  - Checked 2026-11-16 (gh API; FFmpeg CLI): only libopus 1.6.1 (in the `av==19.0.2` wheel) was tested.
  - libopus tags: 1.5.2 2024-04-10, 1.6 2025-12-15, 1.6.1 2026-01-13. Commits monthly through 2026-11. Main author jmvalin has 3,991 of the commits.
  - FFmpeg 9.0.2 CLI has a native `opus` encoder marked experimental (48 kHz, fltp, mono/stereo only). The PyAV wheel lacks it. Not tested.
- **Audio (a): accepted (Dom, 2026-11-16).**
  - Encoder: libopus through PyAV, version fixed by the exact `av==` pin. The release check asserts the encoder resolves to libopus. FFmpeg's native encoder is not used.
  - Settings: 48 kHz, 20 ms packets, VBR, `application=audio`, `empty_moov+default_base_moof`, `frag_duration=1000000`, `flush_packets=1`, standard pre-skip, 128 kbit/s mono.
  - Still open: the stereo bitrate (and a stereo 1 s kill test).
- **Q5/Q6 fastparquet: accepted (Dom, 2026-11-16).** Value columns use BYTE_STREAM_SPLIT. fastparquet 2026.9.0 cannot read these files ("Encoding 9"). The spec states the encoding so implementers know a reader must support it (parquet-format ≥ 2.8.0).
  - Readers that pass: pyarrow 25/26 (freemocap; Blender addon 73e1b3e `utilities/dependencies.py:43-44`), polars 2.0.0, DuckDB 2.0.0, pandas 2.3.3, hyparquet 1.25.6.
  - fastparquet is not in freemocap's dev-streaming uv.lock.
  - Not yet tested: MATLAB, R, Java/Spark, DuckDB-wasm.
  - Rest of Q5 (float32 `value` + float64 `value_f64` by channel dtype, no dictionary on value columns, ZSTD 3, no LZ4/Brotli) is not yet separately answered.

### Round 7 answers (Dom, 2026-11-16): "approve 1-8"

1. **Stereo audio: 256 kbit/s, accepted**, plus a stereo kill test with 1 s fragments (to run).
2. **Crash rules for readers, accepted** (normative reader section):
   - usable length = min(CSV row cover, indexed audio length);
   - ignore index entries whose bytes run past EOF;
   - with no `# fit` footer, fit from the strict-parsed rows.
3. **Realtime tracking journal, accepted:**
   - freemocap's own subscriber node writes it, as a CRC-framed binary file (magic + len + payload + crc32) with a JSON header record.
   - Flush per record; fsync about every 1 s off the hot path.
   - Folded at take end into a Parquet run marked `origin=realtime` with coverage stats. The journal is deleted only after a verified fold.
   - An on/off load test runs before adoption.
   - It is binary but freemocap's file, so outside the skellycam human-readable rule. Dom asked about CSV first: CSV is about 2.4× the size and about 68× the write time (realtime_tracking_storage_20261115.md §3).
4. **Parquet layout, accepted:** `value` float32 + `value_f64` float64, chosen by per-channel dtype; BYTE_STREAM_SPLIT; no dictionary on value columns; ZSTD level 3; no LZ4 or Brotli.
5. **`camera_key` is the only link key, accepted** (manifest, info JSON, calibration TOML, Parquet). `camera_label` is for people only.
6. **Labels and file names, accepted:**
   - label = 6–8 hex digits of `camera_key`, unique in the take;
   - files `<rec>.<label>.mkv` / `<rec>.<label>.csv`; drop `idx-`;
   - user camera names live only in the info JSON (plus the summary copy).
7. **One fact, one home, accepted** (camera_info_placement_20261115.md §2). The manifest `summary` is the one allowed informative copy; readers must not use it (amends 68Z6).
8. **No per-row wall-clock columns, accepted.** Rows hold ns since take start; UTC and the offset appear once in the header.
- **Stereo kill test done (2026-11-16):** Opus 256 kbit/s stereo with 1 s fragments. 8 kills: loss 54.5–955.8 ms, torn tail 0/8, about 108 MB/h (`opus_crash/FINDINGS.md` §7.1). Matches mono.
- **Carried-over items closed:** R3-Q12 (live realtime format) = Round 7 item 3, accepted. R3-Q19 (insert silence for audio gaps, flagged in the CSV) = Round 5 Q2, accepted. R3-Q18 (audio format) = Round 6, Opus fMP4 1 s.
- **All grilling questions are answered as of 2026-11-16.** Next, for Dom's approval before any build:
  1. list the superseding skellyfileformat decision-log entries;
  2. then draft the whole-folder spec and its test list (spec and tests before code).

### Decision log and spec draft v2 (2026-11-16)

- Dom approved the decision-log supersessions without review and asked for the spec draft.
- Written in skellyfileformat `main`, **not committed**:
  - 14 accepted entries (2C9V, 5XNA, 6RSB, 92TM, 9DV4, CZQ9, DE9S, G1YG, KW3G, N6HS, P76Y, Q9X2, QS7B, T8PK), superseding the 15 MCAP-era entries;
  - 2 proposed entries for my own choices (VPD9, 3D33);
  - `spec/SPEC.md` draft v2 (SFF-700 to SFF-892), `spec/parts/parquet-descriptor.md`, `spec/legacy-annex.md`, `spec/conformance.md` (SFT-700 to SFT-769);
  - README, AGENTS.md purpose, the index and open-work updates.
- All doc checks pass, and 223 tool tests pass.
- Inventories used: `parquet_inventory_20261116.md` and `folder_files_inventory_20261116.md`.
- Assembly sources (symbolic IDs, rebuildable) are in the session scratchpad `spec_src/`.
