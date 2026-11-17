# Crash-safe realtime tracking storage (research)

Status: research report, 2026-11-15. A read-only sub-agent study for plan question Q13. The main session verified two claims: the realtime ChArUco recorder is never built (freemocap dev-streaming realtime_pipeline.py:255) and the Parquet write lock uses timeout=0 (parquet_writer.py:28-33). The agent's in-memory tests used random data and wrote no files.

Written for: Dom and agent sessions writing the skellyfileformat whole-folder spec.

---

REPORT: crash-safe realtime tracking, folded into <rec>_data.parquet

Citation prefixes:
- FMC = freemocap upstream/development-streaming @ c27fc299, read with git show, in C:\Users\Dom\GitHub\freemocap\freemocap
- RES = C:\Users\Dom\GitHub\freemocap\skellycam\research\skellycam_recording\recording_upgrade\results\
- REV = C:\Users\Dom\GitHub\freemocap\skellycam\research\skellycam_recording\docs\spec_v0_revival_tracking_sidecars_20261113.md

Evidence labels:
- [code] means read in the code.
- [test] means an existing result file.
- [here] means a one-off in-memory Python test I ran in this session. It used Python 3.12.13 and pyarrow 25.0.0 from freemocap\.venv; the lock pins 26.0.0 (FMC:uv.lock:1930-1931). The data was random float64 (the incompressible worst case), there were no repeats, and nothing touched the disk, so there is no flush or fsync cost in those numbers. No files were written.
- [knowledge] means not verified here.

=== 1. What realtime produces per frame, and what is saved ===

Camera node, per camera:
- The output message carries camera_id, frame_number, charuco_observation and skeleton_observation (FMC:freemocap/pubsub/pubsub_topics.py:77-82; camera_node.py:376-383) [code].
- frame_number is skellycam's connection frame number. It is not the recording frame, and the message carries no capture time (charuco_recorder_node.py:96-101) [code].
- Default mode is GPU (centralized) inference: use_centralized_inference=True (realtime_pipeline_config.py:20) [code].
  - In this mode the camera node builds no skeleton tracker (camera_node.py:196-199).
  - Skeletons come from RealtimeSkeletonInferenceNode (SkeletonInferenceResultMessage, pubsub_topics.py:98-101), which drains to the newest frame (realtime_skeleton_inference_node.py:178-201).
  - A grep of that node finds no 1€ filter. So in default mode the published 2D skeleton is the raw detector output plus its visibility (= confidence) [code; that the detector applies its threshold of 0.4 internally is not verified].
- Filtered 2D exists only in per-camera (CPU) mode (camera_node.py:328-344, enable_keypoint_filter=True at camera_node_config.py:104).
  - There the 1€ filter overwrites the body-stage x,y in place, timed by perf_counter, not capture time.
  - Then x,y with visibility below 0.4 are set to NaN in place, and visibility is kept (camera_node.py:348-353).
  - So raw and filtered 2D never exist together today. Storing both needs a copy taken before the filter.
- ChArUco: after a miss, detection is skipped for the next 10 frames (camera_node.py:42, 357-371) [code].

Aggregator, per processed multi-frame:
- Raw triangulated 3D (raw_keypoints) is computed and converted to the Blender basis, but it is not published (realtime_aggregator_node.py:891-965) [code].
- The 1€-filtered and gap-filled 3D is published as keypoints_arrays (:967-974, :1073). Predicted (extrapolated) points are mixed in and are not marked in the output; measured_keypoints stays local.
- The optional velocity gate (filter_enabled defaults to False, realtime_aggregator_node_config.py:19) overwrites filtered points (:988-997).
- One SkeletonReconstruction per model (:1008-1034; skeleton_reconstruction.py:46-60) holds:
  - mapped_keypoints, landmarks, segment_origins and rotations (world and local);
  - segment_lengths and fitted_scale_mm;
  - joint_angles and reprojected segment origins;
  - center_of_mass, extrapolated_center_of_mass and rigid_body_residuals.
- Also published: reprojection_diagnostics, calibration_bindings and calibration_applicable (pubsub_topics.py:155-166).
- The filters are timed by perf_counter at processing (:897, :971, :992) [code].

Frame skipping:
- The aggregator always requests the newest shared-memory frame (:671-686, :845-850).
- It waits until the websocket consumer has taken the previous result (result_consumed_event at :679; realtime_pipeline.py:257-266, :470-490).
- It gives up on a frame's skeleton after a timeout (:779).
- So realtime output is sparse, and its rate depends on the UI consumer [code].

What is saved today: nothing.
- The only realtime file writer, CharucoRecorderNode, pickles at stop (charuco_recorder_node.py:183-227). It is never built: realtime_pipeline.py:255 sets it to None and never reassigns it. The FMC plan current-work-plans/02-pipeline/app-workflow-todo.md says the "realtime Charuco disk-cache production [is] disabled" [code].
- Aggregator output goes only to the websocket (realtime_pipeline.py:470-490).
- No realtime path calls publish_recording. Its only non-test callers are checkpoint_publication.py:183 and observation_publication.py:247 [code, git grep].

The posthoc Parquet contains 2D, not only 3D [code]:
- OVERLAY_2D per camera: x and y in px plus visibility, reference_frame camera:<id>:image (observation_inputs.py:212-225; observation_samples.py:98-109).
- BOXES_2D (x1, y1, x2, y2, confidence, detector_ran), only when a detector ran (observation_inputs.py:231-254).
- Per-camera capture timing channels plus synchronized timing (observation_publication.py:222-234).
- Then the 3D families.
- A missing point is stored as x,y = null with visibility 0.0 (observation_samples.py:135-136).

=== 2. Is the Parquet writer crash-safe? Can Parquet be appended live? ===

What the writer does [code]:
- It writes zstd batches to a mkstemp *.parquet.tmp, fsyncs, and then replaces the destination atomically (ReplaceFileW / os.replace). The temp file is unlinked in `finally` (parquet_writer.py:70-91; shared_file.py:43-60).
- Every publish rewrites the whole file, all runs included (checkpoint_publication.py:174-193).
- It holds a FileLock with timeout=0, so it fails at once if another writer holds the lock (parquet_writer.py:28-33).

What a crash during a take does:
- The old Parquet stays intact. That is the atomic part.
- But nothing realtime was ever in it, so a crash loses all realtime results.
- A crash during the fold itself leaves the old file plus, at worst, a stray .tmp, because the `finally` never runs on a hard kill [inferred].

Parquet cannot be read before the writer closes it:
- [here] pq.ParquetWriter into a buffer, 50 row groups written and not closed (3.2 MB): pq.read_table raised ArrowInvalid "Parquet magic bytes not found". After close() it read 200 rows and 50 row groups.
- [knowledge] The footer (FileMetaData + PAR1) is written only on close. Row groups already on disk can't be found without it, and pyarrow has no recovery mode. So "append row groups live" is not crash-safe.
- The only safe live form is many small Parquet files, each written atomically (option E below).

=== 3. Live formats, folded into the Parquet at take end ===

Payload size:
- One 2D set is 4 cameras × 553 points × 3 float64 = 53,088 B per frame.
- Raw + filtered 2D + raw/filtered 3D comes to about 133 KB per frame, i.e. about 4.0 MB/s or about 14 GB/h at a full 30 fps (arithmetic). Realtime skips frames, so this is an upper bound; float32 halves it.
- For comparison, video is about 1.66 MB/s per 720p camera (RES\crash_resilience\FINDINGS.md:342).
- Tidy-long, that is about 16.6k Parquet rows per frame, about 1.8e9 rows/h (arithmetic). Fold time is NOT measured: test DT13.

Shared durability evidence:
- A flush per record survived process kill at 1/37/500 rows, for both CSV and CRC binary; default buffering lost rows (RES\crash_resilience\sidecar_durability.md:9-23).
- A flush costs +1.9 µs.
- fsync costs about 200 µs each on the SN850X. fsync every 30 frames kept p50 at 16.1 µs (RES\crash_resilience\FINDINGS.md:325-333).
- A flush does not cover power loss [knowledge].

A. Append-only CSV, flushed per row, with a CRC column
- Crash: no loss under kill (as above). Strict parser 48/48 on cuts. pandas returned an extra row in 23/24 cuts, and 6/24 looked complete but had wrong values (sidecar_durability.md:27-30). So it needs a strict reader.
- Cost [here]: one wide row per camera (1,659 floats, repr, crc32): 127,935 B and about 1.88 ms per frame, single-threaded. That is about 5.6 % of a 33 ms frame period, and 2.4× the binary size.
- Readable: yes. Dependencies: none.
- Fold: parse, then build batches.
- Verdict: good for low-rate streams (parameter events, per-frame status), poor for 553-point × 4-camera arrays.

B. JSONL
- Crash: clean cuts 28/28. Resyncs after a zero hole. Returns a corrupted record silently (RES\overlays\verify_method_crash_modes.json; overlays\FINDINGS.md:141-147).
- Cost [here]: about 1.77 ms and 134,538 B per frame. The [test] for 133 points was 125.4 µs (overlays\FINDINGS.md:98-100).
- Readable: yes. Not recommended: cost, size, and no corruption detection.

C. Length-prefixed MessagePack or CBOR
- Without framing [test]: stops at a 4 KiB zero hole (149/300) and returns a corrupted record silently. It was the fastest to write, at 23.7 µs (verify_method_crash_modes.json; overlays\FINDINGS.md:484, 548).
- With magic + CRC framing it becomes option E-primary with a different payload.
- Dependencies are already locked: msgspec 0.22.0 and cbor2 6.1.5 (FMC:uv.lock:213-214, 1244-1245); the pyproject uses ranges (pyproject.toml:26-27). Pin with ==.
- Note: the existing websocket ChannelBlock packs float32 (message_model.py:405-435). Persisting it as is would be lossy against the float64 Parquet.

D. Arrow IPC stream (one record batch per frame)
- [here] Measured with 300 frames of 53,400 B each:
  - write p50 13.8 µs, p99 1.81 ms (in memory);
  - truncation: 24/24 cuts gave exactly the complete batches;
  - a stream with no end-of-stream marker read all 300;
  - **4 KiB zero hole: stopped at 150, with no resync;**
  - **cut + 64 KiB zero tail: returned 151 instead of 150, and the extra batch had wrong values (3/3 cut positions).** This is the "size extended, data never written" power-loss pattern;
  - one flipped byte: returned silently, 1 wrong batch.
- Behaves like unframed MessagePack: fine for a process kill, unsafe after torn writes.
- Readable: no. Dependency: pyarrow, already used (pin ==26.0.0).
- Fold: open_stream, then transform. Easy.

E-primary. CRC-framed binary journal (.skov pattern: magic + len + payload + crc32)
- [test] .skov:
  - 28/28 clean cuts;
  - 298/300 after a 4 KiB zero hole (it resyncs);
  - the only format that rejected a 1-byte change (299, 0 wrong);
  - 29.3 µs and 3,283 B per frame for 133 points, float32 (overlays\FINDINGS.md:98, 141-147, 482).
- Same framing as the timestamp sidecars, which recovered exactly the complete records in 48/48 kills (RES\crash_resilience\FINDINGS.md:112, 274-276).
- [here] 53,109 B and 27.6 µs per frame, including crc32 of 53 KB.
- Readable: no. It needs a small reader, about 30 lines of struct + zlib + numpy.
- Dependencies: none beyond numpy.
- Recovery: scan for magic, check len and CRC, skip bad records, stop at the torn tail, report counts.
- Fold: header record (JSON) declaring each channel exactly as the Parquet Channel (kind, source, reference_frame, names, components, units). Data records: record type, channel index, connection_frame_number, processing time, then N×K float64. The fold maps records to ChannelSeries batches.

E-fallback. Rolling Parquet segments (e.g. every 1-10 s, each tmp + rename)
- Crash: loses at most the open segment. Each closed segment is a complete Parquet (the same atomic pattern as parquet_writer.py).
- [here] A 30-frame segment took 14.2 ms with zstd, done off-thread, i.e. about 0.47 ms per frame amortised.
- Readable: with any Parquet tool. No new format or reader. pyarrow is already pinned.
- Fold: concatenate, then publish.
- Cost: 360-3,600 files per hour, and the last segment's seconds are lost. So it is "bounded-loss", not "crash-safe" in the strict sense.

F. SQLite WAL
- [knowledge only] WAL commits survive a process kill. Power loss can drop the last commits but should not corrupt the database. Stdlib, but the SQLite version comes with the Python build.
- Write cost not measured. Adds -wal/-shm files and lock behaviour on Windows.
- Not recommended: a third storage engine in the take folder for no gain over E.

MCAP (tested elsewhere)
- 120/120 kills recovered exact prefixes (RES\mcap_kill\FINDINGS.md short answer).
- Dom reversed MCAP on 11-13, so it is listed only as evidence that one CRC'd chunk per message works.

**Recommendation**
- **Primary: E, the CRC-framed binary journal.**
  - It is the only tested format that survives kill, truncation, zero holes and bit flips without returning wrong data.
  - It has the same framing family as the .skvt timing sidecar, costs about 28 µs per frame at full size, and needs no new dependency.
  - Writer: flush per record, plus fsync every about 1 s off the hot path.
  - Write it from a new SourceNode that subscribes to AggregationNodeOutputTopic and CameraNodeOutputTopic. The relay fans out to one queue per subscriber (pubsub_manager.py:64-75; pubsub_abcs.py:61-71), so the aggregator never waits on disk. Subscriptions must be created in the main process.
  - Still needed: a kill test with real data (DT11).
- **Fallback: E-fallback, rolling Parquet segments.** Zero new format or reader code, and loss bounded by the segment length.
- **Rejected: Arrow IPC.** It had no resync and returned a silently wrong batch after a zero tail [here].

Fold requirements [code]:
- Every channel must hold exactly sensor_group.sample_count samples, with strictly increasing frame numbers and timestamps, and unit or all-null quaternions (arrow_schema.py:116-153, 233-258).
- Values may be null (arrow_schema.py:25).
- Map connection_frame_number to the recording frame through the timing sidecar (the posthoc code already does this: video_node.py:353-397). Drop records outside the take.
- **Emit null rows for skipped frames, so the realtime run uses the same frame grid as posthoc.** Publishing refuses a different sample grid against its base run (checkpoint_publication.py:159-160; observation_publication.py:303-308).
- Raw and filtered 2D for the same camera need different `source` values (for example `<tracker>` and `<tracker>:realtime_filtered`). A duplicate (group, source, reference_frame, kind) key is rejected (recording_descriptor.py:159-161).
- 3D maps to the existing kinds: RAW_KEYPOINTS_3D and KEYPOINTS_3D, plus the reconstruction kinds (channel_kind.py:6-26).

=== 4. Marking a realtime run as possibly noisy ===

What the descriptor offers [code]:
- Descriptor is extra="forbid" and schema_version is Literal[1] (recording_descriptor.py:18-19, 192). A new top-level field would break installed readers.
- SourceKind is a closed enum (:27-31). A new "realtime" kind would break them too.
- The intended extension point is run.processing[group]["stage_provenance"]. "older readers ignore it" (stage_provenance.py:1-5).
- StageProvenance already holds effective_settings, default_settings, software, input_signatures, output_sources and limitations (:18-30).
- Caution: a posthoc run built on a base run merges the base's processing (observation_publication.py:310-316). Per-stage provenance entries are replaced for executed stages, but a group-level key would leak into the posthoc run. **So put the origin inside each stage's StageProvenance, not at group level.**

Proposed (in `proposed` entries, not accepted):
- (a) In each published stage's StageProvenance:
  - effective_settings.origin = "realtime";
  - the realtime config: filter min_cutoff, beta, d_cutoff, confidence threshold, velocity gate, max_reprojection_error_px, triangulation config, detector and execution provider, GPU/CPU mode, calibration id plus reload events;
  - limitations, as plain text:
    - "causal 1€ filter, timed by processing time";
    - "latest-frame scheduling: frames skipped";
    - "gap-filled 3D points are not marked";
    - "journal ended uncleanly" when that applies.
- (b) A coverage block in the same effective_settings, per camera and per group:
  - frames_in_take and frames_processed;
  - skipped frames by reason: latency / skeleton timeout / ChArUco skip gate / calibration not applicable;
  - journal records_ok, records_rejected_crc and torn_tail_bytes;
  - clean_close: bool;
  - latency p50 and p99.
- (c) Per-frame marker without a new ChannelKind:
  - For a skipped frame, write x, y AND visibility as null.
  - "Processed, not seen" stays x,y null with visibility 0.0, as posthoc writes it (observation_samples.py:135-136).
  - For 3D, a per-group TIMESTAMPS channel named, say, `realtime_processed` (value = processing time, null if skipped). TimingSampleName is an enum of capture/synchronized only (sample_conventions.py:34-36), so this needs an extension check.
- (d) **Write no StageCheckpoints for realtime stages.** Posthoc restart requires matching checkpoint signatures (stage_execution_plan.py:75-87). Without them, posthoc can never resume from realtime observations.
  - read_saved_observations also requires one tracker source per group and validates the source as a PosthocMocapPipelineConfig (saved_observations.py:36-46). That accidentally blocks reuse; do not rely on it.
- (e) Selection rules:
  - The fold sets selected_run_id to the realtime run only if it is the only run. Publishing normally selects the new run (checkpoint_publication.py:177-180).
  - **When the base run is realtime, posthoc must use keep=True.** The default is keep=False, target = base (processing_request.py:25-26; stage_execution_plan.py:90). A default posthoc run on realtime run 0 would overwrite it.
- (f) Reader warning:
  - Whenever a realtime-origin run is read or exported: "Realtime run: N/M frames processed (x %), causal filters, may contain dropped and extrapolated frames; prefer a posthoc run."
  - Plus a hard warning when clean_close is false.
  - The UI shows a badge on the run.

=== 5. The journal after a successful fold ===

Option 1: Delete after a verified fold
- How: re-read the Parquet run and compare per-channel counts and a values digest with the journal.
- For: no duplicate truth, saves disk (up to about 14 GB/h).
- Against: realtime results can't be rebuilt; posthoc computes a different result. If the run is later overwritten (keep=False) or the fold had a bug, the data is gone.

Option 2: Keep forever
- For: safest.
- Against: disk use; two sources that can disagree; readers must be told the Parquet is canonical.

Option 3: Keep until a posthoc run exists, or until the user cleans up (mark it folded by an appended "folded" record or by renaming *.live to *.folded)
- For: covers the overwrite risk during the period when posthoc is most likely to run.
- Against: needs a cleanup tool and a state to track.

Option 4: Compress and archive after the fold
- Cost: CPU, and still disk.

Recommendation:
- Option 1 is safe only if 4(e) is enforced, i.e. realtime runs can't be overwritten silently. Otherwise use Option 3.
- In every option:
  - Never delete before the verified fold.
  - Keep the journal if the fold fails validation.
  - At app start, fold any unfolded journals. The fold can lose the timeout=0 lock to posthoc (parquet_writer.py:28-33), so it must retry or defer.

Not checked:
- No disk-level, power-loss or real-tracker tests. The [here] numbers are a single in-memory run on random data.
- Fold time for about 1.8e9 rows/h is unmeasured.
- The GPU-mode "raw 2D" claim rests on a grep of the inference node, not a run.
- Whether retained_run carries the realtime run's sources into a posthoc run is not traced.

Risk: in today's default (GPU) mode no filtered 2D exists, and raw 3D is never published. "Store raw and filtered 2D and 3D" therefore needs freemocap code changes in camera_node and the aggregator, not only a writer.
