# Phase 5 step 5a specification: the new video recorder

Status: accepted by the user on 2026-11-20
([ADR-Z3Y7](../decisions/entries/Z3Y7-acceptance-of-the-step-5a-recorder-spec-and-test-list.md)).
Proposed by an agent on 2026-11-19 and revised on 2026-11-19 and 2026-11-20
([ADR-Q03C](../decisions/entries/Q03C-phase-5-step-5a-recorder-spec-and-test-list.md)). The user
accepted this spec and its test list before any code [R12]. The decisions R1 to R12
([ADR-VPF8](../decisions/entries/VPF8-phase-5-recorder-decisions.md)) and the later decisions M1 to
M10 and C1 to C7 ([ADR-J3QP](../decisions/entries/J3QP-missing-frames-as-black-placeholders-and-the-end-of-a-take.md))
are accepted. Section 18 gives each one in full. The revision applies M1 to M10, C1 to C7 and the
faults of an independent review (section 15.5).

Note of 2026-11-20: the user decided D1 to D3 after the code review ([ADR-C6DE](../decisions/entries/C6DE-stall-as-no-progress-limits-and-no-fat-disk.md)): a stall is no progress of
the writer for the stall limit (D1); the queue of 3 s and the stall limit of 10 s stay as starting
values (D2); a take folder on a FAT disk is refused (D3). They are cited as [C6DE D1] to [C6DE D3],
so that they differ from the decisions [Dn] of the capture spec. Dated notes apply them in sections
1.5, 4.2, 4.3, 5.3, 8.1, 10, 11, 15.1, 15.3 and 18.

## 0. How to read this spec

Marks:

- **[Rn]**: decision n of the user, 2026-11-19 (section 18,
  [ADR-VPF8](../decisions/entries/VPF8-phase-5-recorder-decisions.md)).
- **[Mn]**, **[Cn]**: later decisions of the user, 2026-11-19, on missing frames (M) and on the
  recorder (C) (section 18,
  [ADR-J3QP](../decisions/entries/J3QP-missing-frames-as-black-placeholders-and-the-end-of-a-take.md)).
  M1 to M5 replace the "row with no image" reading of R2, R3 and R4.
- **[SFF-n]**: requirement n of the skellyfileformat specification, draft v2, `spec/SPEC.md` of the
  repository `../skellyfileformat`, branch `main`, commit
  `24949df6c22093336c30b279c396ef593648de1e`. **[SFT-n]**: test n of `spec/conformance.md` of the
  same commit. A skellyfileformat entry is cited as "skellyfileformat ADR-XXXX". Before 2026-11-21,
  this spec cited commit `d67679ada704caf55c64c2e279081d317205f354`, and then commit `c1028ef`
  ([ADR-3B97](../decisions/entries/3B97-format-sync-to-the-format-commit-with-f1-to-f10.md)).
- **[F-n]**: format change n of section 13. The format holds F-1 to F-10 since commit `c1028ef`
  (skellyfileformat ADR-6AT7). Commit `24949df` adds only the acceptance of the details of
  skellyfileformat ADR-76NN. Section 13 gives the SFF number of each change.
- **[ring x.y]**: section x.y of [`frame-ring.md`](frame-ring.md)
  ([ADR-50G8](../decisions/entries/50G8-phase-2-frame-ring-spec.md)).
- **[cap x.y]**, **[Dn]**, **[Un]**: section x.y, decision Dn and answer Un of
  [`windows-capture.md`](windows-capture.md)
  ([ADR-4CQC](../decisions/entries/4CQC-phase-3-windows-capture-spec-and-test-list.md),
  [ADR-EN7A](../decisions/entries/EN7A-phase-3-windows-capture-decisions.md),
  [ADR-QKX1](../decisions/entries/QKX1-answers-of-the-user-to-the-phase-3-spec-questions.md)).
- **[P §n]**: section n of `research/NATIVE_JPEG_CAPTURE_PLAN.md`. **[M `file`]** (a path in code
  font): measured; the file holds the result. Each research file is on branch `dom/research` of this
  repository. `RU/` is short for `research/skellycam_recording/recording_upgrade/`. The study of that
  folder is closed. Its evidence stays [R7]. `RS/` is short for `research/skellycam_recording/`.
- **[review]**: a fact that the independent review of 2026-11-19 measured and that this revision
  checked again with a synthetic script (section 15.5). The script is not kept.
- **[NV]**: not verified. Nobody measured it, or the evidence does not cover it.
- **[agent n]**: an agent filled a gap that the decisions, the format and the plan do not fix.
  Section 16, item n, lists each one. Section 17 holds the questions for the user.

This spec uses British spelling. Code names come from branch `dom/recorder` at commit fd64a8e5a
(the same tree as `dom/native-jpeg` at that commit). The spec cites files, not line numbers.

## 1. Purpose, scope, non-goals, terms

### 1.1 Purpose

Step 5a replaces the old recorder (decoded image in, H.264 MP4 out) with a writer of the
skellyfileformat take folder [R1]. Each camera gets one MKV file with one JPEG block for each group
frame, and one CSV timing sidecar. The take gets a manifest and a capture info JSON [SFF-716]. A
missing frame is a black placeholder block on a row with the flag `missing` [M1, M3]. The files
survive a hard stop of a camera process. Thus the three interim rules U4, U5 and U12 of phase 3 go
[R1].

### 1.2 Scope

| Step | Delivers |
|---|---|
| 5a (this spec) | The video writer, the timing CSV, the manifest, the capture info as far as 5a can fill it, and the end of a take [R1]. A self-contained module with its own tests, fed by synthetic JPEG frames, on branch `dom/recorder` [R10]. The measurements of R11. After step 3a of phase 3 is joined, one connection commit joins the module to the shared loop (section 10) [R10]. |
| 5d (later) | Camera identity from the operating system: `camera_key` from the identity string of SFF-752, the label of SFF-720 and the full capture info (`device`, `user_name`, all controls of SFF-802, `exposure_step`) [R1, R8]. |
| 5b (later) | Audio in Opus in fragmented MP4 with its timing CSV, and the timestamp fit of each sidecar (the fit lines of SFF-775) [R1]. |
| 5c (later) | Repair of a take after a crash (SFF-793 to SFF-798) [R1]. It may also fill the short camera file of 7.4 [M5]. Step 5a holds only the small part that it needs: it completes the files of one camera with `missing` rows and the closing lines (7.4) [R4, C2]. |

### 1.3 Non-goals

- Audio. Step 5a writes no audio file. The WAV goes [R5]. Opus comes in 5b [R1]. A record start that
  names a microphone gets HTTP 422 until step 5b [C1]. Until step 5b, the microphone line of the UI
  reads "Audio recording is not available yet." [ADR-F2KY](../decisions/entries/F2KY-rulings-of-the-user-after-the-third-consistency-check.md).
- The fit lines. A finished sidecar of 5a has no `# fit` line (6.5) [R1].
- The repair of a crashed take, and the question of SFF-793 at start-up (5c) [R1].
- Camera identity from the operating system (5d) [R1, R8].
- The canvas player (phase 6). The app cannot play new takes until then [R9]. The playback list
  shows them with a mark [C7].
- The reader of the new format and the "upgrade recording" converter (phase 6) [P §8].
- A change of the shared loop before step 3a is joined [R10].
- The removal of the lockstep gate (phase 8) [P §8].
- H.264 capture [SFF-734].

### 1.4 Decided elsewhere

| Subject | Where | This spec |
|---|---|---|
| The format: one MKV with `V_MJPEG` per camera, one CSV per camera with a CRC and a flush per row, the manifest, the capture info, the folder layout | skellyfileformat SPEC draft v2; earlier decisions of section 18 | Sections 6 and 7 cite each rule. Section 13 lists the changes. |
| One writer thread per camera process; a bounded queue of about 3 s; a full queue slows capture and never drops a frame; a stall over the limit ends the take with an error; a write error finishes the sidecars and the manifest for the frames written | [P §6], section 18 | Section 5. |
| PyAV 19.0.2 for the MKV | [P §6], `pyproject.toml` (`av==19.0.2`) | Section 6.3. |
| What the writer receives per frame | [ring 5.1], [R10] | Section 4.1. |
| Recorder first, then the ring write; the same `bytes` object for both | [ring 5.3, 5.7] | Section 10. |
| Read old formats, never write them | section 18 | Section 8.3. |
| Opus in fragmented MP4 for audio | section 18 | Step 5b. |
| Camera states, dead camera, hang, gate | [cap 5.2, 6.6, 8] | Sections 5, 7 and 10. Section 14 lists the changes. |

R2 replaces the plan sentence "one camera fails mid-take: the whole take stops" [P §6]. R1 to R4 and
M1 to M5 replace the interim rules U4, U5 and U12 [cap 5.5, 5.7, 6.6]. Section 14 lists the sentences
of `windows-capture.md` that change.

### 1.5 Terms

| Term | Meaning |
|---|---|
| take | The files of one recording [SFF-716]. In the code of today, a "recording". |
| take folder | `<recording_directory>/<recording_name>` of the start request. |
| `<rec>` | The recording name: `recording_name` of the start request [SFF-715]. |
| take level | The part of the module in the main process: folder, manifest, capture info, lock, the end of the take. |
| camera level | The part of the module in a camera process: queue, writer thread, MKV, CSV rows. |
| group frame | One round of the lockstep gate during a take. Row k of each camera is group frame k [SFF-754]. |
| frame count of the take | The number of group frames of the take: `last_recording_frame_number − first_recording_frame_number` of the orchestrator (7.6). Changed on 2026-11-20: no "+ 1" (A of [ADR-JMS0](../decisions/entries/JMS0-review-decisions.md)). |
| frame | One `RecorderFrame` (4.1). |
| damaged frame | A frame with a bit of the error mask 0x0F of [ring 4] in `flags` [R3]. |
| block | One `SimpleBlock` of an MKV, with one JPEG [SFF-733]. |
| row | One data row of a CSV [SFF-744]. |
| placeholder | A black JPEG with the size and chroma layout of the camera's own frames (6.4) [M1, M2]. |
| `missing` row | A row with the flag `missing` [M3, F-1]. Its block is a placeholder, or it has no block in a short file [M5]. |
| short file | A camera file that ends before the last row of its sidecar, because nothing could write it (7.4) [M5]. |
| dead camera | A camera in the state `dead` of [cap 8.1] whose camera process still runs. |
| stall limit | The longest time that the writer may make no progress while `give` or `end` waits for it (5.3) [C6DE D1]. Changed on 2026-11-20: before, the longest time of one wait. |
| progress | A write call on the MKV or the CSV file object, or an `os.fsync` call, that returned. A call that has not returned is no progress [C6DE D1]. |

## 2. Done list

Step 5a is done when:

1. The tests of the kinds unit and process of section 12 pass on Windows, Linux and macOS in the
   workflow of 12.1 [C4].
2. The conformance subset of 12.3 gives exactly the expected results of that section.
3. The measurements of section 11 ran, and the user decided the queue size and the stall limit from
   the results [R11].
4. The user decided the format changes F-1 to F-10 of section 13 [R6]. The tests follow each
   decision.
5. After step 3a is joined: the connection commit of section 10 is in, the connection tests pass,
   and the edits of section 14 are made in `windows-capture.md` by an accepted entry.

## 3. Module layout

The module is new. It imports no code of the old recorder [agent 1]. It has two levels: the take
level in the main process and the camera level in each camera process [agent 2]:

| Path | Content |
|---|---|
| `skellycam/core/take_recorder/frame.py` | `RecorderFrame` (4.1). |
| `skellycam/core/take_recorder/take.py` | The take level: `start_take`, `Take`, `CameraTakeSpec`, `TakeSummary` (4.2). |
| `skellycam/core/take_recorder/camera_writer.py` | The camera level: `CameraTakeWriter`, `CameraTakeResult`, the queue and the writer thread (4.3, 5). |
| `skellycam/core/take_recorder/mkv.py` | The PyAV calls (6.3). |
| `skellycam/core/take_recorder/placeholder.py` | The SOF parse (`parse_sof`) and the hand-built placeholder (6.4). |
| `skellycam/core/take_recorder/sidecar.py` | Header, row, footer and CRC of the CSV; the strict read of a CSV (6.5, 8.1). |
| `skellycam/core/take_recorder/completion.py` | The completion of a short file (7.4). |
| `skellycam/core/take_recorder/folder_files.py` | Manifest, capture info, the whole-file write and the lock (6.6 to 6.8). |
| `skellycam/core/take_recorder/stop_stats.py` | The fields of the stop response, from the CSVs (8.2). |
| `skellycam/tests/take_recorder/` | The tests of section 12, the synthetic JPEG source, the child-process writer of the kill and stall tests (`child_writer.py`) and the conformance adapter (12.3). |

Dependencies: only what `pyproject.toml` pins today. `av==19.0.2` writes the MKV.
`opencv-contrib-python==5.1.0.95`, a main dependency, makes the synthetic JPEGs of the tests and
decodes in them. The placeholder needs no encoder (6.4). The standard library gives `zlib`, `threading`, `queue`, `json`,
`hashlib`, `uuid`, and `msvcrt` or `fcntl`. No new package.

## 4. Public interface

### 4.1 `RecorderFrame` [R10]

The writer input is the list of R10, with the names of [ring 5.1]. It is a frozen dataclass with
slots:

| Field | Type | Use in 5a |
|---|---|---|
| `payload` | `bytes` | The JPEG that the ring also gets: the camera's bytes, with the standard DHT when the capture check inserted it [M6, ring 5.2]. The same object as the ring gets. No copy (5.1). |
| `frame_number` | int | Not written. The camera writer checks that it increases. |
| `arrival_ns` | int | Absolute host-clock time. The CSV holds it minus the take start [SFF-755]. |
| `sample_ns` | int | Absolute host-clock time, or `NO_SAMPLE_NS` of the ring package. `NO_SAMPLE_NS` gives an empty field [SFF-755]. |
| `source_frame_number` | int | The CSV column `source_frame_number` [SFF-755], and the flags `gap` and `repeat` [SFF-756]. |
| `flags` | int | The ring flags of the capture check [ring 4, 5.2]. An error bit makes the row `missing` (7.2) [R3, M1]. |
| `delivered_len` | int | Not written. The capture check already compared it [ring 5.2]. |
| `rotation_cw_deg` | int | Not written. The take spec holds the rotation; it does not change in a take [D36]. |

### 4.2 Take level (main process)

```python
take = start_take(folder, rec, cameras, *, writer, clock=None, lock_timeout_s=10.0,
                  queue_seconds=3.0, stall_limit_s=10.0) -> Take
spec = take.camera_spec(camera_id) -> CameraTakeSpec
summary = take.finish(results, *, frame_count, ended_by_error=None) -> TakeSummary
```

- `folder` is the take folder (a `pathlib.Path`). It must not exist, or it must be empty [SFF-719]
  [agent 16].
- `rec` is `<rec>`. `start_take` refuses a value that breaks SFF-715.
- `cameras` is a list of `TakeCamera`, in the order of `group_position` [agent 19]: `camera_id`,
  `nominal_rate` (`num`, `den`) [agent 20], `width` and `height` of the opened mode,
  `rotation_cw_deg`, the capture-info facts of 6.7, `capture_format`, and `layout`: the width, the
  height and the H/V sampling factors of each component from the SOF of the camera's last good frame
  before the take, or `None` when the camera gave no good frame (6.4) [agent 22].
- `writer` is the writer string, `skellycam <version>` [SFF-712].
- `clock` is a test seam: two callables for the host clock and UTC. The default is
  `time.perf_counter_ns` and `time.time_ns`.
- `start_take` creates the folder, the media folder and the empty lock file. It reads the take start
  (6.5), writes the capture info JSON, then the manifest with `state` `recording`, both under the
  lock [SFF-724, SFF-801]. It returns after the two writes. A refusal raises `ValueError` before the
  first write.
- Added on 2026-11-20 [C6DE D3]: `start_take` refuses a take folder on a file system with a file size
  limit of 4 GiB (FAT12, FAT16, FAT32: `FAT…` on Windows, `vfat` or `msdos` on Linux, `msdos` on
  macOS). exFAT is accepted. The text names the file system and the limit. When the file system
  cannot be found, `start_take` logs a warning and goes on.
- `camera_spec` gives the picklable `CameraTakeSpec` of one camera: the paths of its MKV and CSV,
  the header values of 6.5, the mode size, the layout, the queue size and the stall limit.
- `finish` takes one `CameraTakeResult` or `None` for each camera, and the frame count of the take.
  `None` means that the camera process ended without a result. The caller passes a result or `None`
  only after the rule of 8.1 step 4 [review B2]. `finish` runs the end of the take (8.1) and returns a
  `TakeSummary`: the stop response fields of 8.2, the per-camera counts and the warnings.
  `ended_by_error` is `None` or the text of the error that ended the take (5.3, 5.4).

### 4.3 Camera level (camera process)

```python
writer = CameraTakeWriter.start(spec) -> CameraTakeWriter
writer.give(frame) -> None
writer.give_missing() -> None
result = writer.end(frame_count) -> CameraTakeResult
error = writer.abandon() -> str | None
```

- `start` opens the MKV and calls `start_encoding()`, so the MKV header is in the file before the
  first frame (6.3) [review S5]. It builds the placeholder from the layout of the spec (6.4). It opens
  the CSV, writes the header and the column line, and starts the writer thread. It returns before the
  first frame.
- `give` puts the frame in the queue. It returns at once when the queue has space. When the queue is
  full, `give` waits for space (5.2, 5.3) [agent 3]. It never drops a frame. When the writer made no
  progress for the stall limit, counted from the start of the wait or from the last progress,
  whichever is later, it raises `RecorderStalled` [C6DE D1, changed on 2026-11-20]. After a write
  error of the writer thread, it raises `RecorderWriteError` at once (5.4).
- `give_missing` puts one `missing` row with no frame in the queue: a placeholder block, and empty
  times and source frame number (7.3) [M1, M3] [agent 24]. It waits as `give` does.
- `end` puts the end marker in the queue, with `frame_count`. The writer thread writes each queued
  item, then a `missing` row with a placeholder for each group frame up to `frame_count` (7.6), then
  closes the MKV, writes the rows that wait (6.3), writes the `# end` line (6.5), forces both files
  to disk and closes them (5.6) [agent 11]. `end` waits for the put of the end marker (the queue can
  be full) and for the writer thread while the writer makes progress, however slowly. It returns a
  `CameraTakeResult`. When the writer made no progress for the stall limit (counted from the call or
  from the last progress, whichever is later), the result has `error="disk stall"`, and section 5.3
  applies [C6] [C6DE D1, changed on 2026-11-20: before, one deadline of the stall limit after the
  call].
- `abandon` puts a marker after the queued items. The writer thread writes each queued item, the row
  of the last block (6.3), and closes both files with no padding and no `# end` line. `abandon` waits
  for the put and for the writer thread as `end` does (D1). It returns the text of a write error, or None; the loop sends that error to the main process, which ends the take with it (5.4). The loop calls it
  when its take has no last frame and the take goes on (the camera ends alone): the take level
  completes the pair after the join (7.4). When no take level follows (the group stops, or the main
  process is gone), the loop does not call `abandon`: it calls `end` with the frame count of the last
  frame that section 9 gives (added on 2026-11-20, [ADR-P5VE](../decisions/entries/P5VE-review-fix-choices.md),
  [ADR-82AA](../decisions/entries/82AA-stop-last-frame-survivor-files-and-stuck-writer-limit.md)).
- After `give` or `give_missing` raised `RecorderStalled` or `RecorderWriteError`, the caller calls
  only `end`, never `give` again. `end` pads the rest with `missing` rows; else each later row would
  move by one [agent 3].
- `CameraTakeResult`: `camera_id`, `rows`, `blocks`, `missing_rows`, `last_real_row` (the position of
  the last row that is not `missing`, or `None`; a damaged frame's row is `missing`),
  `queue_high_water` (items), `give_wait_count`,
  `give_wait_ms_max`, `files_closed` (true when the writer thread ended and both files are closed),
  and `error` (`None`, `"disk stall"` or the text of a write error).
- The writer is not reusable. A call of `give` or `give_missing` before `start` or after `end`, or a
  second `end`, raises `RuntimeError`.

### 4.4 Threads

| Thread | Calls |
|---|---|
| Camera loop thread (camera process) | `start`, `give`, `give_missing`, `end` |
| Writer thread (camera process) | The MKV mux, the row writes, the fsync (5.6). Nothing else. |
| Main process, the task of the camera group | `start_take`, `camera_spec`, `finish` |

The module does not depend on the gate, the ring or IPC. Tests call all three levels in one
process [R10]. The kill and stall tests run the camera level in a child process (12.2).

## 5. Writer thread and queue

### 5.1 The queue

- One `queue.Queue` for each camera writer. Its size is ⌈`queue_seconds` × `num` / `den`⌉ items
  [agent 4]. `queue_seconds` is 3.0, the starting value of R11 and of [P §6]. Example: 90 items at
  30/1, 180 items at 60/1.
- The queue holds the `RecorderFrame` objects. Each one holds the same `bytes` object that the
  capture layer made and that the ring writer copies into its slot. The recorder makes no copy
  [ring 5.7] [R10]. A `give_missing` item holds no bytes.
- Memory: at most the queue size times the largest JPEG. At 1080p60 with JPEGs of 600 kB, that is
  180 × 600 kB = 108 MB for one camera (computed).
- The research used a queue of 2.87 s, and it absorbed writer stalls up to 329 ms with capture at
  most 2.6 ms late, at 16 × 1080p60 [M `RU/results/write_throughput/FINDINGS.md` §2.8]. Smaller
  queues are [NV] (same file, §4 item 7). Section 11 measures the value again [R11].

### 5.2 The full-queue rule

- A full queue slows capture. It never drops a frame [P §6].
- `give` waits on the condition of the queue (`Queue.put(block=True, timeout=...)`), with no poll
  [ring 8.10]. While it waits, the camera loop thread holds the frame. Thus the camera takes no new
  frame from its source [agent 3].
- With a push source and the lockstep gate, the effect is [D26, cap 5.2]:
  1. The camera does not finish its gate round. The gate does not open the next round for the other
     cameras. Thus the whole group waits.
  2. The sources of all cameras keep delivering. A new frame replaces the frame in the waiting
     place. Each replaced frame counts in `replaced_count` [D26, D27].
  3. When space comes, `give` returns. Each camera takes its newest frame. Its
     `source_frame_number` jumps by the replaced frames. The next row of each camera gets the flag
     `gap` [SFF-756]. These are the "gap rows" of [P §6]. No group frame is lost, so no row is
     `missing`.
- With the OpenCV source (pull, Linux and macOS until phase 7), the driver drops the frames and
  `source_frame_number` counts grabs [cap 4.2]. Thus the gap does not show in the flag. It shows only
  in `arrival_ns` (section 15.3).
- The 2 s stall watch of [cap 9.5] must not count the time that a loop does not grab. With the
  OpenCV source, the last arrival is the last grab. A `give` wait of more than 2 s stops the grabs of
  that camera, and it also stops the grabs of each other camera, which waits at the gate for it
  (item 1 above). Thus a healthy camera would be marked `dead`. The watch of each source counts from
  the later of the last arrival and the end of the last wait of its loop (in `give` or at the gate)
  (section 10 item 10) [agent 32]. Changed on 2026-11-20: before, of a pull source only; a push source
  has the same rule (E of [ADR-JMS0](../decisions/entries/JMS0-review-decisions.md)).
- The camera writer counts each wait (`give_wait_count`, `give_wait_ms_max`) and the queue high-water.
  The camera process logs them at the end of the take [P §6].

### 5.3 The stall limit and a disk stall [C5, C6]

- The stall limit is the longest time with no progress of the writer (1.5) while `give` or `end`
  waits for it [C6DE D1, changed on 2026-11-20]. A writer that writes slowly is never a stall. Its
  starting value is 10 s, and the queue stays 3 s [P §6, R11]; the user keeps both as starting
  values [C6DE D2].
- After the limit, `give` raises `RecorderStalled`. The frame in hand is not written. The loop then
  calls only `end` for this camera (4.3).
- A disk stall ends the take for all cameras, with a clear error [C5]:
  1. The camera process reports `RecorderStalled` with its camera ID to the main process.
  2. The main process ends the take for every camera, as a stop request does. The manifest gets the
     warning `take_error` with the text "disk stall on camera <camera_id>" [F-5]. The log carries the
     same text [C5].
  3. Each camera is told to end, with the frame count of the take (7.6). The stalled camera calls
     `end` (4.3).
  4. The main process waits for the result of each camera while that camera's writer makes
     progress. It stops the wait when no result came and the camera reported no progress for the
     stall limit plus a margin of 5 s [C6] [agent 25] [C6DE D1, changed on 2026-11-20]. The connection
     commit sends the progress time of the writer to the main process with the camera's status.
  5. A camera whose writer finished in that time returns normally. It stays `ready` [C6].
  6. A camera whose writer is still stuck after that time (a result with `error="disk stall"`, or no
     result) has its process ended (`terminate`, then `join`; then `kill` and `join` when the process
     still runs). It gets the state `failed`, stage `recording`, reason "disk stall" [C6] [agent 25].
     The user uses "apply again" or unselects it [C6, cap 8.3]. Its files are completed as a short file
     (7.4) [M5]. When its process still runs after the kill, its files are not touched, and the
     manifest stays `recording` with a `take_error` that names the camera, for the repair step (8.1)
     (added on 2026-11-20, [ADR-82AA](../decisions/entries/82AA-stop-last-frame-survivor-files-and-stuck-writer-limit.md) item 2).
- The app keeps running. A new take can start [P §6].

### 5.4 A write error [C5, C6]

- An exception of the writer thread (for example `OSError` for a full disk) stops that writer
  thread. It closes both files. The `close()` of the PyAV container can raise
  `av.error.PyAVCallbackError` after the error [review]. The writer thread catches each exception of
  the close and closes the file object in a `finally` block. The next `give` raises
  `RecorderWriteError` at once [P §6].
- The camera process reports it. The main process ends the take for every camera, as in 5.3 items
  2 and 3, with the warning `take_error` and the text of the error [C5].
- The loop calls only `end` for this camera (4.3). The camera returns normally from `end` with the
  error in its result, and it stays `ready` [C6].
- The MKV cannot be written further. A write error on one file is the second short-file case of M5
  [M5]: that camera gets a short pair (7.4), with the warnings `camera_file_short` and `take_error`,
  and no `camera_dead`. The other cameras get normal finished pairs.
- When the take level cannot write either (the disk is full), the files stay unfinished and the
  manifest stays `recording`. Step 5c repairs such a take (section 9).

### 5.5 No thread spins

Each wait of the module blocks on a condition, a queue, a lock call or a process join, with a timeout
[ring 8.10]. The writer thread waits in `Queue.get()`. No loop polls without a block. The writer
thread is a non-daemon thread with the name `take-writer-<camera_id>`. The end marker in the queue
holds the frame count [agent 5].

### 5.6 What goes to disk and when

| Data | Write | Forced to disk |
|---|---|---|
| A block | One `mux` call with `flush_packets=1` and `cluster_size_limit=1` (6.3). The muxer gives block k to the file when block k+1 comes, or at close [M `RU/results/write_throughput/FINDINGS.md` §2.3: 29 of 30 frames on disk with the writer open]. | With the CSV, once a second [SFF-788] |
| A row | One `write` call on an unbuffered file, with its LF [SFF-744] [agent 8]. Row k is written after block k is in the file (6.3) [agent 7]. | Once a second [SFF-788] |
| The fsync | `os.fsync` of the MKV descriptor, then of the CSV descriptor, on the writer thread, after a row write, when 1 s or more passed since the last fsync [agent 9]. Never on the camera loop thread. | — |
| The end of a camera | `end`: the placeholders to the frame count, close the MKV, write the last rows and the `# end` line, fsync both files, close them. | At `end` |
| Manifest, capture info | Whole-file write (6.8) [SFF-786]. | Each write |

The research measured a flush per row at +1.9 µs p50, and an fsync of two files every 30 frames
at p50 16.1 µs, p99 883 µs and a worst frame of 4.2 ms, for one writer on one NVMe drive
[M `RU/results/crash_resilience/FINDINGS.md` §2.11]. The cost for 16 writers is [NV]. Section 11
measures it [R11].

## 6. The files of a take in 5a

### 6.1 Folder layout and names

```
<take folder>/
  recording_manifest.json          6.6 [SFF-724]
  <rec>_info.json                  6.7 [SFF-801]
  .processing.lock                 6.8 [SFF-789]
  synchronized_videos/
    <rec>.<label>.mkv              6.3, one for each camera [SFF-732]
    <rec>.<label>.csv              6.5 [SFF-741]
```

- Each name is exact [SFF-716]. No other file and no other folder [SFF-719, SFF-722].
- Step 5a writes no audio file and no `<rec>.audio.csv`. `audio_count` is 0 and the manifest
  `audio` is null [SFF-749, SFF-723] [R5].
- `<rec>` is fixed at the start [SFF-715]. No program renames a file of the take [SFF-717].

### 6.2 Keys and labels before 5d [R8, C3]

- Each camera's files are named from today's `camera_id` [R8]. Today `camera_id` is 4 hexadecimal
  characters [cap 7.2]. Until 5d [C3]:
  - `camera_key` = `camera_id` + the first 12 hexadecimal characters of the SHA-256 of the UTF-8
    bytes of `camera_id`. It has 16 lowercase hexadecimal characters [SFF-752 form].
  - `camera_label` = the first 6 characters of `camera_key` [SFF-720]. It starts with `camera_id`
    and has the form of SFF-753.
  - Two cameras of one take never have one `camera_id` [D13]. Thus their labels differ.
- The capture info marks the key as provisional with `key_origin` `"provisional"` [C3, F-6].
- A reader finds the files through the manifest `cameras` items (`video`, `timing`), not by a
  guess of the name [R8, SFF-730].
- Step 5d changes the key to the identity string of SFF-752 and the label to SFF-720 [R8].

### 6.3 The camera file (MKV)

PyAV calls. This is the byte-exact recipe of the research
[M `RU/results/jpeg_passthrough/FINDINGS.md` §2.1; `RU/results/EVIDENCE_INDEX.md` §2.1], with the
option of [review B1]:

```python
raw = open(mkv_path, "xb", buffering=0)                       # [agent 6]
container = av.open(raw, mode="w", format="matroska",
                    options={"flush_packets": "1", "cluster_size_limit": "1"})
stream = container.add_mux_stream("mjpeg", rate=Fraction(num, den),
                                  width=width, height=height)
container.start_encoding()                                    # header in the file at start
# for block k (k is also the row position):
packet = av.Packet(payload)        # the frame, or the placeholder of 6.4
packet.stream = stream
packet.time_base = Fraction(1, 1000)
packet.pts = packet.dts = (2 * k * den * 1000 + num) // (2 * num)
container.mux(packet)
# at the end:
container.close()                  # each exception caught (5.4)
raw.close()
```

- `add_mux_stream` with `av.Packet` and `mux`. Never `add_stream_from_template`: it lost frames in
  MP4 and MOV and gave `EINVAL` in AVI [M `RU/results/jpeg_passthrough/FINDINGS.md` §2.1]. Never
  `add_stream(codec)` with extradata [`RU/results/write_throughput/FINDINGS.md` §4 item 12].
- `rate`, `width` and `height` must be keyword arguments. The positional form raises `TypeError`
  ("takes at most 2 positional arguments") [review S6]. Without `width` and `height` the mux fails
  with error 22 [M `RS/mkv_time_jumps/FINDINGS.md`].
- `flush_packets=1` on the container [`RU/results/crash_resilience/FINDINGS.md` §4 item 2]. No
  empty packet after each frame: that trick loses no frame on a kill, but a killed file then seeks
  one frame late and a finished file does not seek to its last frame
  [M `RU/results/EVIDENCE_INDEX.md` §2.2; `RU/results/crash_resilience/FINDINGS.md` §2.2].
- `cluster_size_limit=1` on the container. Without it, the muxer holds more than one block when the
  JPEGs are small (about 4 KiB or less), and the offsets of this section are wrong. Synthetic
  320x240 JPEGs of about 2 kB gave 22 wrong offsets of 39 without the option and 0 of 39 with it;
  640x480 JPEGs of about 6 kB gave 0 of 39 in both cases [review B1]. A placeholder at 640x480 is 2
  to 4 kB [M `RS/mkv_black_placeholder/FINDINGS.md`].
- `start_encoding()` in `start` [review S5]. Without it, a file with no block has 0 bytes. With it,
  the header is in the file (483 bytes for a 64x64 stream) [review]. PyAV `av.open` refuses a file
  with no block (`EOFError`) [review]. A file with no block occurs only as a short file (7.4).
- A Python file object, not a path [agent 6]. Thus the writer owns the descriptor for `os.fsync`
  [SFF-788] and for `tell()`. PyAV has no flush call [M `RU/results/write_throughput/FINDINGS.md`
  §2.3], and the research found no way to fsync the MKV of a path-based writer
  [`RU/results/crash_resilience/FINDINGS.md` §4 item 10]. The kill behaviour of a file-object
  writer was not tested (same file, §2.11). T-REC-KILL tests it (section 11).
- One track, `V_MJPEG`, track number below 128 [SFF-732]. One block for each row, a `SimpleBlock`
  with the keyframe flag; FFmpeg sets the flag for an intra-only stream
  [M `RU/results/jpeg_passthrough/FINDINGS.md` §2.1] [SFF-733]. No lacing [SFF-733].
- The block bytes are the payload of the frame: the camera's bytes, or the camera's bytes with the
  inserted standard DHT [M6]; or the placeholder on a `missing` row [M1]. These are the two exceptions
  to SFF-734 [M4, F-3]. Nothing else is added [SFF-737].
- No rotation element and no EXIF tag. The pixels are in sensor orientation [SFF-735].
- Time base 1/1000; TimestampScale 1,000,000 [SFF-736]. The container time of the block of row k is
  ⌊(2 × k × `den` × 1000 + `num`) / (2 × `num`)⌋ ms [SFF-736]. Each row has its block (placeholders
  included), so the block times have no jump [M1]. OpenCV and Blender then read frame i as row i,
  with exact seeks, also over runs of placeholders [M `RS/mkv_black_placeholder/FINDINGS.md`]. With
  missing blocks, both tools give wrong frames or counts [M `RS/mkv_time_jumps/FINDINGS.md`].
- `DefaultDuration` is ⌊10^9 × `den` / `num`⌋ ns [SFF-736]. T-REC-04 checks that PyAV writes it.
- `start_take` refuses a nominal rate above 1000 frames per second [SFF-736], and a `num` or `den`
  outside 1 to 2^20 [SFF-750]. It refuses a camera whose `capture_format` is H.264 [SFF-734].
- The track size is the width and height of the opened mode [agent 26].
- Live byte offsets [SFF-757] [agent 7]:
  1. The muxer gives block k to the file only when block k+1 comes, or at close (5.6). With
     `cluster_size_limit=1`, this holds also for small blocks [review B1].
  2. After the `mux` call of block k+1 returns, the end of the payload of block k is `raw.tell()`.
     Its `byte_offset` is that position minus the payload length. The writer then writes row k.
  3. For the last block, the writer notes `raw.tell()` before `container.close()`. After the close,
     it reads the bytes from that position for the payload length plus 64 bytes, finds the payload
     and checks that each byte is equal. Then it writes the last row.
  4. T-REC-10 checks each offset, live and after close, on each OS, also with small frames. This is
     the desk test DT5 of SFF-757.
- After a process kill, each written row has a block on disk. The block of the last item given to
  the muxer, and each item in the queue, are lost [M `RU/results/EVIDENCE_INDEX.md` §2.2: MKV with
  `flush_packets` lost 1 frame per kill in 48 kills]. Whether `cluster_size_limit=1` changes this is
  [NV] until T-REC-KILL.
- The structure of a live or killed file, as the pinned FFmpeg writes it: the Segment has an unknown
  size; each Cluster has a known size and holds one block (with `cluster_size_limit=1`); the first
  child of each Cluster is a CRC-32 element. A file read after 5 muxed blocks held 4 such Clusters
  [review]. The completion of 7.4 and the readers must walk these elements [SFF-739, SFF-740].

### 6.4 The placeholder [M1, M2]

- The placeholder has the width, the height, the number of components and the H/V sampling factors
  of each component of the camera's own frames [M2].
- Their source is the `layout` of the take spec: the SOF segment (`FFC0`, `FFC1` or `FFC2`) of the
  camera's last good frame before the take [agent 22]. Each camera streams before a take: it passes
  the warm-up and the rate check, and a take starts only when each selected camera is `ready`
  [cap 8.3]. Thus the layout is known at `start`, the placeholder is built in `start`, and every row is
  written live from row 0. The first block always has the camera's size and layout [M7].
- When `layout` is `None` (a test, or a camera that never gave a good frame), the writer holds the
  rows until the first good frame of the take, and takes its SOF. It holds at most the queue size of
  rows (about 3 s). When no good frame came in that time, it builds the placeholder from the mode size
  with the factors 2x1, 1x1, 1x1 (4:2:2, the layout of all 88 real camera JPEGs of the research
  [`RU/results/EVIDENCE_INDEX.md` §2.1]), writes the held rows with it, and logs one warning
  [agent 22].
- A good frame whose layout differs from the layout of the placeholder (size, number of components
  or H/V factors) is a defect, because a setting change is refused during a take [D36]. The writer
  logs one warning and keeps the placeholder.
- The SOF compare uses the size, the number of components and the H/V factors of each component
  only. It never compares bytes: cameras and encoders differ in component IDs and table selectors.
- The writer builds the placeholder by hand, with no encoder [agent 21]. It is a flat black baseline
  JPEG: SOI; one DQT with all 64 values 1; the SOF with the camera's size and factors (component IDs
  1, 2, 3, all on table 0); one DC table with two codes (category 0: `0`; category 11: `10`); one AC
  table with one code (EOB: `0`); one SOS with all components; then the entropy-coded data in MCU
  order (interleaved for 3 components, one block per MCU for 1 component). The first Y block has the
  DC difference −1024 (Y = 0); each other block has the difference 0; each block ends with EOB; the
  last byte is padded with 1 bits, and a byte 0xFF gets a 0x00 after it; then EOI. Thus each block
  costs 2 bits.
- Measured with a synthetic prototype (not kept), PyAV 19.0.2 and OpenCV 5.1.0 [review]: for 4:4:4,
  4:2:2, 4:2:0, 4:4:0, 4:1:1 and grey, at 640x480, 1920x1080 and 1278x719, each placeholder decodes to
  Y = 0 in OpenCV and PyAV, with the same pixel format as an OpenCV JPEG of that layout (for example
  `yuvj422p`). Sizes: 16,353 bytes at 1920x1080 4:2:2 and 2,553 bytes at 640x480 4:2:2. With the
  standard tables of ITU-T T.81 Annex K.3, the same placeholders were 48,926 and 7,526 bytes. The
  OpenCV placeholder with optimised tables was 16,484 bytes [M `RS/mkv_black_placeholder/FINDINGS.md`].
  Thus the minimal tables are used.
- The player spec builds its fixtures with a flat DC-only encoder of the same structure, with the
  Annex K tables (`specs/player.md` section 12.2, branch `dom/player`). A reader decodes either
  table set. The two specs agree on the image; the tables of a placeholder are not a format rule.
- A layout with more than 3 components, or with a sum of H × V above 10 over the components (the
  limit of ITU-T T.81 for one MCU), cannot be built. `start_take` refuses such a camera with
  `ValueError` [agent 22]. No test camera sends such a frame.
- The same `bytes` object is muxed for each `missing` row of the file. At 1080p 4:2:2 and 30 fps, one
  hour of placeholders is about 1.8 GB [M2].

### 6.5 The timing sidecar (CSV)

The file is opened with `open(csv_path, "xb", buffering=0)` [agent 8]. Each write is one complete
line: the header lines and the column line at `start`, one row for each group frame, and the footer
lines at `end` (or at the completion of 7.4).

Header lines, in the order of SFF-742 and section 8 of the format:

```
# skellyfileformat=video_timing
# format_version=2.0
# format_prerelease=1
# writer=skellycam 2.0.0
# take_uuid=<32 hex>
# take_start_host_ns=<int>
# take_start_utc_ns=<int>
# utc_offset_min=<int>
# clock=windows_qpc
# clock_hz=
# group_size=<int>
# audio_count=0
# group_position=<int>
# camera_key=<16 hex>
# camera_label=<label>
# nominal_rate=<num>/<den>
# display_rotation=<0|90|180|270>
frame,source_frame_number,arrival_ns,sample_ns,flags,byte_offset,byte_size,crc32
```

| Key | 5a value |
|---|---|
| `format_version`, `format_prerelease` | `2.0` and 1 [SFF-707, SFF-710]. |
| `writer` | `skellycam <version>`; the version from `importlib.metadata` [SFF-712]. |
| `take_uuid` | `uuid.uuid4().hex` [SFF-703]. The same in each file of the take [SFF-749]. |
| `take_start_host_ns`, `take_start_utc_ns` | `perf_counter_ns()`, then `time_ns()` at once after it, in `start_take`, before the first frame [SFF-774]. The camera processes stamp `arrival_ns` with the same clock [D28]. On Windows (QPC) and Linux (`CLOCK_MONOTONIC`) it is one clock for the whole machine; on macOS this is [NV]. |
| `utc_offset_min` | The local offset at the take start, from `datetime.now().astimezone().utcoffset()`. No time-zone name [SFF-774]. |
| `clock` | `windows_qpc`, `linux_monotonic` or `macos_uptime_raw` by OS [SFF-772]. The two last are provisional [SFF-773]. That Python 3.13 `perf_counter_ns` is `CLOCK_UPTIME_RAW` on macOS is [NV]. |
| `clock_hz` | Empty. The field is for diagnostics only [agent 18]. |
| `group_size`, `group_position` | The number of cameras; the place of the camera in `cameras` [agent 19]. |
| `audio_count` | 0 [R5]. |
| `camera_key`, `camera_label` | 6.2 [C3]. |
| `nominal_rate` | `num/den` [SFF-750] [agent 20]. |
| `display_rotation` | `rotation_cw_deg` of the camera config [SFF-751]. |

Rows:

| Column | 5a value |
|---|---|
| `frame` | The position: 0 in the first row, +1 in each row [SFF-754]. |
| `source_frame_number` | `frame.source_frame_number`; empty in a `missing` row with no camera frame [M3, F-1]. |
| `arrival_ns` | `frame.arrival_ns − take_start_host_ns` [SFF-755]; empty in a `missing` row with no camera frame [M3, F-1]. |
| `sample_ns` | `frame.sample_ns − take_start_host_ns`, or empty for `NO_SAMPLE_NS` [SFF-755]; empty in a `missing` row with no camera frame. Thus the Media Foundation sample time of [D28] goes into the CSV. |
| `flags` | 7.1 and 7.2 [SFF-756, F-1]. |
| `byte_offset`, `byte_size` | The payload of the block of the row: the frame or the placeholder [SFF-757, M3]. Empty only in a `missing` row after the end of a short file [M5, F-2]. |
| `crc32` | The CRC-32 of the bytes of the row before the comma that comes before it, 8 lowercase hexadecimal characters [SFF-744, SFF-704]. |

- Integers in the form of SFF-701. No field is quoted, and no field holds a comma or a space
  [SFF-741]. UTF-8 with no byte order mark, LF line ends [SFF-700].
- Example rows: a normal row, a row after two replaced frames (`gap`), a damaged frame (a
  placeholder with the frame's times), a dead camera (a placeholder, no times), a short file (no
  block):

  ```
  0,1000,1203311,1180002,0,4127,61234,5b1e0c2a
  1,1003,1303311,1280002,1,65438,60911,0c41aa07
  2,1004,1336644,1313335,16,126426,16353,9e01b2c3
  300,,,,16,9480122,16353,77a0f1d2
  301,,,,16,,,3a9c0d11
  ```

  The CRC values above are not real. T-REC-08 computes the real ones.

Footer lines [SFF-745]:

```
# repair cut_bytes=<n> media_cut_bytes=<m> repair_writer=skellycam 2.0.0    (only after 7.4)
# end rows=<R> gaps=<G> filled=0 missing=<M> encode_skips=0
```

- `rows`, `gaps`, `filled` and `encode_skips` follow SFF-758. `missing` is the number of rows with
  the flag `missing` [M3, F-1] [R3]. It comes before the last key, as SFF-745 requires for a new key
  [review S10].
- No `# fit` and no `# fit_segment` line in 5a [R1]. SFF-775 requires them at a normal end. Step 5b
  adds them. Until then, a reader gives the player time `arrival_ns` and the file warning
  `missing_fit` [SFF-781]. Section 15.4 lists this as a known gap of 5a.
- A sidecar without its `# end` line is unfinished [SFF-747]. A reader uses its complete rows
  [SFF-746].

### 6.6 The manifest

`recording_manifest.json` has the members of the table of section 5 of the format, in that order
[SFF-723]. The values in 5a:

| Member | 5a value |
|---|---|
| `skellyfileformat` | `"recording_manifest"` |
| `format_version`, `format_prerelease`, `writer` | As in 6.5 [SFF-707, SFF-712]. |
| `take_uuid`, `recording_name` | As in 6.5; `<rec>`. |
| `purpose` | `"motion_capture"` [agent 17]. |
| `state` | `"recording"` from `start_take`; `"finished"` from `finish` [SFF-724]. |
| `cameras` | One item for each camera, in order of `group_position`: `camera_key`, `camera_label`, `group_position`, `video`, `timing` (the two paths of 6.1), `calibration_camera` null [SFF-723]. |
| `audio` | null [R5]. |
| `calibration` | null. |
| `files` | One item: `{"path": "<rec>_info.json", "role": "capture_info", "owner": "skellycam", "sha256": <SHA-256 of the file>}` [SFF-723]. |
| `warnings` | `[]` at the start. At the end: `camera_gap` for each camera with `gaps` > 0 [SFF-727], with the `detail` `row=<k> from=<a> to=<b>` of its first gap row k, where a and b are the `source_frame_number` of rows k − 1 and k (F of [ADR-JMS0](../decisions/entries/JMS0-review-decisions.md); SFF-727 allows a text for people, so no format change; a reader does not parse it); `camera_dead` for each camera that stopped during the take, with `last_frame` [M8, F-5]; `camera_file_short` for each short file, with the block and row counts [M5, F-5]; `take_error` when an error ended the take [C5, F-5]. `source` is `"skellycam"`. |
| `privacy` | `fields`: `/camera_configs/<key>/device/os_name` of the capture info when not null, `utc_offset_min` of each timing sidecar, `/recording_name` of the manifest; sorted [SFF-881, SFF-882]. `media_shows_people`: `true`. |
| `summary` | SFF-728, with `missing` for each camera, after `filled`: the `missing` count of its `# end` line [M3, F-1]. In the state `recording`: each `duration_s`, `stored_px`, `gaps`, `filled` and `missing` is null. At the end: computed from the CSVs; `stored_px` is the size of the first block that is not a placeholder, from its SOF, or the mode size when there is no such block (SFF-728; skellyfileformat ADR-76NN item 12; [ADR-3B97](../decisions/entries/3B97-format-sync-to-the-format-commit-with-f1-to-f10.md)); `user_name` and `model` are null (5d); `exposure_us` from the capture info (6.7). F-1 gives `duration_s` when the last rows have no time. |

- Written by `start_take` before the first frame, and by `finish` after the last media file is
  closed [SFF-724]. Each write reads the file when it exists, changes it, and writes it whole, under
  the lock (6.8) [SFF-724, SFF-726, SFF-786]. It keeps each member and each item that freemocap owns
  [SFF-724].
- JSON in the form of SFF-702: the members in the order of the table, integers with no fraction,
  other numbers in the shortest form.

### 6.7 The capture info JSON

`<rec>_info.json` has the members of section 13 of the format, in that order, and no other member
[SFF-800]. `start_take` writes it before the manifest. `finish` writes it again before the
manifest, with the same content [SFF-801].

| Member | 5a value | Waits for |
|---|---|---|
| `skellyfileformat`, versions, `writer`, `take_uuid` | As in 6.6. | — |
| `camera_configs` | One member for each camera, the key is `camera_key`, in order of `group_position` [SFF-800]. | — |
| `audio` | null [R5]. | 5b |
| config `camera_label` | 6.2. | 5d |
| config `user_name` | null. | 5d |
| config `key_origin` | `"provisional"` [C3, F-6]. | 5d |
| config `device.os_name` | The friendly name of the detection (`CameraDeviceInfo.name`). | — |
| config `device.vendor_id`, `product_id` | 4 lowercase hexadecimal characters from the detection, or null. | — |
| config `device.backend` | `"media_foundation"` for the Media Foundation source; the lower-case OpenCV backend name (for example `"v4l2"`, `"avfoundation"`, `"msmf"`) for the OpenCV source [agent 23]. | — |
| config `device.os_index` | The detection index. | — |
| config `device.model`, `serial`, `port_path`, `os_device_id` | null. | 5d |
| config `requested` | `width`, `height`, `framerate` (the requested number, or `"camera_default"` for a request of -1 or 0 [D16]), `capture_format` (`"MJPG"`, `"YUYV"`, or `"NV12"` (SFF-800 of skellyspecs main, Q849; Q877 of [ADR-4TBY](../decisions/entries/4TBY-decisions-of-the-user-on-the-review-of-the-3b-code.md))), `exposure_mode` (`"auto"`, `"manual"` or `"recommend"`). | — |
| config `controls` | `exposure_us`, `gain` and `focus` from the read-back values of the config [cap 11.4]. `exposure_us` is 2^v × 10^6 for the exposure value v of skellycam (log2 seconds) [D35] [agent 29]. `auto` is the auto flag of each control [D37]. | 5d: the other controls of SFF-802 |
| config `exposure_step` | null. | 5d |

The content of the recording info of phase 3 [cap 11.6] goes to these places:

| Phase 3 item | Place in 5a |
|---|---|
| `capture.<id>.source` | `device.backend` |
| `capture.<id>.mode` | The track size and `stored_px` (size), `nominal_rate` of the CSV (rate), `requested.capture_format` (format) |
| `capture.<id>.controls_at_start` | `controls` |
| `capture.<id>.auto_controls_at_start` | `controls.<name>.auto` = `true` [D37] |
| `capture.<id>.white_balance`, `power_line_frequency` | `controls.white_balance_k`, `controls.power_line_hz` (5d) |
| `capture.<id>.input_range` | The log of the camera process only [agent 23]. The format has no place for it. |
| `dead_cameras` | The manifest warning `camera_dead` [M8, F-5] |
| The `warnings` items `auto_control`, `mixed_rate` | `controls.<name>.auto`; `nominal_rate` of each CSV. The response and the log keep them as in [cap 11.3]. |

### 6.8 Whole-file writes and the lock

- A whole-file write writes `<name>.tmp` in the same folder, forces it to disk with `os.fsync`,
  then replaces the file with `os.replace` [SFF-786].
- The lock is the file lock of the OS on `.processing.lock` [SFF-789]: on Windows `msvcrt.locking`
  with `LK_NBLCK` on byte 0 (it calls `LockFile`), on Linux and macOS `fcntl.flock` with
  `LOCK_EX | LOCK_NB` [agent 15] [F-7]. `start_take` creates the empty file.
- The take level holds the lock for each read, change and write of the manifest and of the capture
  info [SFF-724, SFF-789, SFF-801]. It tries again every 50 ms with a blocking sleep, for at most
  `lock_timeout_s` (10 s) [agent 15].
- In `start_take`, the folder is new or empty, so no other program can hold the lock. A timeout there
  cannot occur, and it is not tested [review S7]. A lock timeout in `finish` leaves the manifest in the
  state `recording`, logs an error, and gives the stop response from the CSVs [agent 15]. Step 5c
  repairs such a take.

### 6.9 What readers see [M10]

- skellycam's shared reader of video files (`SequentialVideoReader`) needs no change for the
  placeholders: it read 300 of 300 frames of each placeholder file, with no exception [M10;
  M `RS/mkv_black_placeholder/FINDINGS.md`].
- The interface notes of skellycam for freemocap and for skellytracker [P §9] must say [M10]:
  - A placeholder is a black image of the camera's size. Its row is flagged `missing` in the timing
    file.
  - "Image i of a camera file is group frame i" stays true for every camera file of a take, except
    the short file of a killed or hung camera process (7.4) [M5]. That file is shorter. Its rows
    after its last block are flagged `missing` and have empty byte fields, and the manifest warning
    `camera_file_short` names it.
  - A program that ignores the flag sees a black image [M9].

## 7. Row rules

### 7.1 A normal frame

A frame with no bit of the error mask 0x0F gives one block and one row. `flags` has:

- bit 0 (1) `gap` when `source_frame_number` is not the value of the row before plus 1 and is not
  equal to it; 0 in the first row and when this row or the row before has no
  `source_frame_number` [SFF-756];
- bit 3 (8) `repeat` when `source_frame_number` equals the value of the row before [SFF-756];
- bit 1 (2) `filled` and bit 2 (4) `encode_skip`: always 0. Step 5a copies no frame [SFF-756]. The
  encoder of step 3b falls back and loses no frame [cap 13.2, T-CAP-64]. Thus skellycam never skips
  a frame for the encoder;
- 0 in each other bit. The ring flags `DISCONTINUITY` and `DHT_INSERTED` do not go into the CSV
  [agent 30]. A frame with `DHT_INSERTED` is stored with the inserted DHT [M6].

### 7.2 A damaged frame [R3, M1]

- A frame with a bit of the error mask 0x0F of [ring 4] in `flags` is damaged [R3]. By the order of
  [ring 5.3], only `CAPTURE_ERROR` (0x02) and `NO_SOI_EOI` (0x04) can reach the recorder: the ring
  sets `OVERSIZE` and `DECODE_ERROR` after it.
- Its block is the placeholder (6.4) [M1]. The damaged bytes are not kept anywhere [R3].
- Its row has the flag `missing` (bit 4, 16) [M3, F-1]; `source_frame_number`, `arrival_ns` and
  `sample_ns` of the frame; `byte_offset` and `byte_size` of the placeholder block [M3]. The flags
  `gap` and `repeat` follow 7.1.
- The last good image is not repeated: the placeholder is black [R3]. Thus U5 goes.
- The count is the `missing` value of the `# end` line and of the manifest summary [R3, M3].

### 7.3 A dead camera [R2, M1, M8]

- A camera dies during a take [D38]. The other cameras keep recording [D38]. Its camera process
  still runs.
- The writer keeps writing placeholders to the end of the take [M1]. The camera loop calls
  `give_missing` once for each group frame of the take after the death (section 10 item 7), and `end`
  adds a placeholder for each group frame that is still missing at the end (4.3) [agent 24].
- Each such row has `frame`, `flags` (16), `byte_offset`, `byte_size` and `crc32`. The times and the
  source frame number are empty [M3, F-1].
- The MKV is closed normally, with its index, and has one block for each row [M1].
- The manifest gets a warning `camera_dead` with `last_frame`: the position of the last row that is
  not `missing` (`last_real_row`), or `none` [M8, F-5]. A damaged frame's row is `missing`, so it does
  not count. The player shows "camera lost at frame N" with N = `last_frame` + 1, the first group
  frame with no image from that camera, and N = 0 for `none` [M8].
- The camera process sends its result at once after `end` returns, before it closes the source
  [cap 6.9] (section 10 item 7).
- Thus every camera file of the take has the same number of rows and of blocks [R2, M1]. U4 goes.

### 7.4 A killed or hung camera process: the short file [R4, M5, C2]

- A call of a camera hangs during a take [cap 6.6]. The camera process reports, then ends at once
  with `os._exit`. It does not try to finish the files [R4]. Thus U12 goes. A camera process that is
  killed, that crashes, or that the main process ends after a disk stall (5.3) is the same case.
- Nothing can write its video file then. That file ends early [M5].
- The take level completes the files of that camera in `finish`, at the end of the same take, in
  the same run of the app [R4, C2] [agent 12]. It does this only after the camera's process has been
  joined, or after the camera's result says `files_closed` (5.4) [M5, review B2]. It skips a CSV that
  already ends with an `# end` line (a camera that ended normally before its process ended):
  1. It walks the EBML elements of the MKV from the start of the Segment data and finds the complete
     blocks [SFF-740].
  2. It reads the CSV strictly [SFF-746]. It keeps the rows up to the first row that is not
     complete or has a wrong CRC.
  3. n is the smaller of two numbers: the number of kept rows and the number of complete blocks.
     The pair keeps the first n blocks and the first n rows [SFF-795]. After a process kill, the CSV
     normally has no extra row, because a row is written only after its block (6.3).
  4. It cuts the MKV after block n − 1 and the CSV after row n − 1. It changes no byte before a cut
     and appends nothing to the MKV [SFF-794].
  5. It appends a `missing` row with empty byte fields and no times for each group frame from n up to
     the frame count of the take (7.6). These rows have no block [M5, F-2].
  6. It appends `# repair cut_bytes=<n> media_cut_bytes=<m> repair_writer=<writer>`, then the
     `# end` line [SFF-795]. A reader then reports the pair as `repaired` [C2]. A repaired camera file
     needs no Cues [SFF-794]. It writes no fit lines: they come with step 5b [R1, review S11].
- A camera file with no block (the process ended before its first block reached the file) keeps only
  the header of 6.3: it holds no Cluster, only the elements before the first Cluster (SFF-754;
  skellyfileformat ADR-76NN item 9). Its sidecar holds
  only `missing` rows with empty byte fields [F-2].
- The manifest gets the warnings `camera_dead` (reason "hang", "disk stall", the reason of the stall watch of
  [`unix-capture.md`](unix-capture.md) 4.10, or the exit code) and
  `camera_file_short` with `blocks=<n> rows=<frame count>` [M5, M8, F-5].
- A write error on one file (5.4) is the second short-file case [M5]. The same steps 1 to 6 apply
  after `end` returned with `files_closed`. The manifest gets `camera_file_short` and `take_error`,
  and no `camera_dead`: the camera stays `ready` [C6].
- The user is not asked: the program that records a take may complete that take's files [C2, F-4].
  Step 5c reuses the steps 1 to 4 for its repair, and may fill the short file later [M5].

### 7.5 A camera that stalled or had a write error

- A disk stall: a camera whose writer finishes within the limit of 5.3 ends normally. Its `end`
  pads with placeholders to the frame count, as 7.3 does. A camera whose writer stays stuck gets the
  short file of 7.4 [C6, M5].
- A write error: the MKV cannot be written further, so the camera gets a short pair (7.4), the second
  short-file case of M5 [M5]. The camera stays `ready` [C6].

### 7.6 Equal row counts

- Each CSV of a finished take has the frame count of the take as its number of rows [SFF-754, R2].
  Each camera file has one block for each row, except a short file [M1, M5].
- The frame count of the take is `last_recording_frame_number − first_recording_frame_number` of
  the orchestrator: the group frames of the take, first to last − 1 [agent 11]. The camera writer gets
  it in `end`, and `finish` gets it from the main process. Changed on 2026-11-20: before, "+ 1", which
  counted a row with no frame (A of [ADR-JMS0](../decisions/entries/JMS0-review-decisions.md)).
- A finished CSV with another number of rows is a defect: `finish` logs it and adds `take_error`.

### 7.7 Rotation

- The frames stay in sensor orientation [SFF-735]. The header holds `display_rotation` [SFF-751].
- The container holds no rotation element [SFF-735]. VLC 3.0.24 honours no rotation flag in MKV
  [M `research/skellycam_recording/docs/spec_v0_revival_tracking_sidecars_20261113.md`].
- A setting change is refused during a take [D36]. Thus the rotation does not change in a take.

## 8. The end of a take

### 8.1 Order of the steps

1. The stop request (or the error of 5.3 or 5.4) sets the last frame of the take in the orchestrator
   (`last_recording_frame_number`). Each live camera records to that frame. Each dead camera gives
   placeholders to that frame (7.3). Changed on 2026-11-20 ([ADR-82AA](../decisions/entries/82AA-stop-last-frame-survivor-files-and-stuck-writer-limit.md) item 1): the stop does not pause the cameras.
   The last frame is the largest gate count plus 2 (the gate lets a camera hold one frame more than the
   largest count), and at least the first frame. Before, the stop paused the cameras, and a push source
   lost the frames of the pause before row N − 2 (a `gap`).
   The stop reads the gate count and writes the last frame under the lock of
   `last_recording_frame_number`, and only when the value is still −1: a last frame that a camera set
   first stays. Then it unpauses the cameras, with no wait, so that a paused camera records to that
   frame. (The public pause route is removed: [ADR-V8RS](../decisions/entries/V8RS-pause-freezes-the-ui-display-only.md).)
   While the stop holds that lock, a camera that decides a frame waits for it, and a camera that waits
   at the gate for that camera reads no frame. A push source replaces each frame that comes in that
   time (5.2). Thus a hold that is longer than one frame interval (a main process that is busy between
   the read and the write) can give a `gap` on the last row of the take, and a `camera_gap` warning.
   The warning is true: frames were lost. It can come only on the last row: the frame of each row
   before it was in hand before the hold [ADR-HQE5](../decisions/entries/HQE5-choices-of-fix-lane-4.md).
2. The main process tells each camera to end, with the frame count of the take (7.6).
3. Each camera process calls `end(frame_count)` and sends its `CameraTakeResult` (4.3).
4. The main process waits for each camera while its writer makes progress, and at most the stall
   limit plus 5 s after the last progress that the camera reported (5.3 item 4) [C6] [agent 25]
   [C6DE D1, changed on 2026-11-20]:
   - a result with no error and `files_closed`: the camera is done;
   - a result with a write error and `files_closed`: the camera is done, and its files wait for 7.4;
   - a process that has already ended (hang, crash): the main process joins it;
   - no result in time, or a result with `error="disk stall"`: the main process ends the process
     (`terminate`, then `kill` when it still runs), joins it, and gives the camera the state `failed`
     of 5.3 [C6].
   The main process never touches a camera's files before one of these four cases [review B2]. A
   process that still runs after the kill is none of them: `finish` does not complete its files, and
   it writes the manifest with `state` `"recording"` and a `take_error` for that camera, for the repair
   step (added on 2026-11-20, [ADR-82AA](../decisions/entries/82AA-stop-last-frame-survivor-files-and-stuck-writer-limit.md) item 2).
   A stall or a write error that comes while a stop runs is the `take_error` of that take, as in 5.3
   and 5.4.
5. `Take.finish(results, frame_count=...)`:
   1. It completes each short file (7.4).
   2. It reads each CSV strictly [SFF-746] and checks the row count (7.6).
   3. It writes the capture info JSON again (6.7) [SFF-801].
   4. It writes the manifest last: `state` `"finished"`, the warnings, the summary [SFF-724,
      SFF-728].
   5. It computes the stop response fields from the CSVs (8.2).

The manifest is written last. Thus `state` `"finished"` means that every file of the take is
finished [SFF-724].

### 8.2 The stop response (R5)

`StopRecordingResponse` keeps each field [R5]. Each field comes from the CSVs of the take
[agent 14]. A `missing` row is left out of each statistic, as the NaN values are left out today:

| Field | Source in 5a |
|---|---|
| `recording_name` | `<rec>`. |
| `recording_path` | The take folder. |
| `number_of_cameras` | `group_size`. |
| `number_of_frames` | The frame count of the take (7.6). |
| `total_duration_sec` | `duration_s` of the manifest summary [SFF-728, F-1]. |
| `mean_framerate` | The frame rate of the take: frames divided by the elapsed time (M of [ADR-JMS0](../decisions/entries/JMS0-review-decisions.md), changed on 2026-11-20; the user decided on 2026-11-23 (Q609) that this is the headline rate of a take [ADR-81RE](../decisions/entries/81RE-decisions-of-the-user-on-the-restore-file-the-take-rate-and-pace-tests.md)). For camera i: F_i is the group frames from its first to its last row that is not `missing` (the row index of the last minus the row index of the first), and T_i is the time between the `arrival_ns` of these two rows, in s. A camera with fewer than two such rows, or with T_i not above 0, is left out. The group value is ΣF_i / ΣT_i over the cameras that are left, rounded to 2 decimals. Null (NaN) when no camera is left. Changed on 2026-11-23 [ADR-HQE5](../decisions/entries/HQE5-choices-of-fix-lane-4.md): before, the group value was the mean of F_i / T_i, and a camera with two rows 1 ms apart (a process killed after its first frames) gave 1000 fps for itself. With ΣF / ΣT, such a camera adds almost nothing. With cameras of the same length, the value is the mean of before. The arrival grid of 16 ms changes T_i by one step at most at each end: 0.1 % of a take of 30 s. The name stays (a client reads it); its meaning is the rate of the take. |
| `mean_inter_camera_sync_ms` | The mean of the range of frame k: the largest minus the smallest `arrival_ns` of the cameras whose row is not `missing`, in ms. Rounded to 2 decimals. |
| `framerate_stats` | Median, mean, standard deviation, min and max of the rate of each group frame k ≥ 1: 1 / the median over the cameras of `arrival_ns`(k) − `arrival_ns`(k − 1), in s, for each camera with neither row `missing` and a time that increases ([ADR-F8C0](../decisions/entries/F8C0-third-review-choices.md) item 11). A median, not a mean (a decision of the user of 2026-11-21): a burst of queued frames of one camera (one run gave a mean of 136 fps and a max of 2775 fps) does not make the rate of the frame [ADR-Z7F3](../decisions/entries/Z7F3-choices-of-fix-lane-3.md). With two cameras, the median is the mean of the two durations. These are figures of each frame interval, not the rate of the take [U Q609]: on a camera whose arrival times fall on a 16 ms grid, the intervals are 16, 33 or 50 ms, and `framerate_stats.median` reads 31.25 for a take at 30.02 fps (a real-camera run of 2026-11-23). The rate of the take is `mean_framerate`. The median of B2 of [ADR-TFD7](../decisions/entries/TFD7-search-limit-stop-rate-median-role-flag-and-restore-after-a-failed-loop.md) stays only here. |
| `frame_duration_stats` | The same of the median frame duration of each frame k ≥ 1 (the median over the cameras), in ms. |
| `inter_camera_grab_range_ms_stats` | The same of the ranges of `mean_inter_camera_sync_ms`. |

Today these values come from the midpoints of the grab stamps of the old frame record. From step 3a,
both grab stamps hold `arrival_ns` [cap 5.4]. Thus the meaning stays the same. A take that an error
ended gives the same response; the error text is in the log and in the manifest [C5].

A take that an error ended is ended at once for all cameras. The main process keeps its summary.
The next stop request returns that summary, one time. Each later stop request, and a stop request
with no take, gets HTTP 409 with the text "No recording runs". Two stop requests at the same time
end the take one time: the second gets the 409 (B of [ADR-JMS0](../decisions/entries/JMS0-review-decisions.md), added on 2026-11-20).

### 8.3 What is no longer written, and the code that goes

Step 5a writes none of these [R5]: the H.264 MP4; the 28-column timestamp CSV of each camera; the
combined (multi-frame) CSV; the statistics files; the WAV; the recording info JSON of
`RecordingInfo.save_to_file`; `synchronized_videos_README.md` [SFF-722].

The connection commit (section 10) deletes the code that writes them, after a search for its
callers:

| Code | Reason |
|---|---|
| `core/recorders/videos/video_recorder.py`, `pyav_video_writer.py` | The old writer. |
| `core/recorders/recording_finalizer.py`, `core/recorders/video_audio_remuxer.py` | The old end of a take. |
| `core/recorders/audio/audio_recorder.py` | The WAV [R5]. Step 5b writes Opus. |
| `core/timestamps/numpy_timestamps/create_camera_csvs.py`, `create_multi_frame_csvs.py`, `process_and_save_recording_timestamps.py`, `process_recording_timestamps.py`, `save_timestamps_statistics_summary.py` | The old CSVs and the statistics files. |
| `core/timestamps/recording_timestamp_stats.py` | The old stop statistics. `stop_stats.py` replaces it. |
| `core/camera/opencv/opencv_helpers/handle_recording_updates.py`, `handle_video_recording_loop.py` | The old recorder calls of the loop. |
| `RecordingFinishedMessage` with its frame metadata (`core/ipc/pubsub/pubsub_topics.py`) | Replaced by a message with a `CameraTakeResult`. |
| `RecordingInfo.save_to_file` and the write paths of `RecordingInfo` | The recording info JSON. The request fields stay. |

The readers of old recordings stay: `recording_timing_reader.py`, `recording_statistics.py`,
`video_associations.py`, `video_file_metadata.py`, `sequential_video_reader.py`, `browser_stream.py`
and the playback router [section 18, read old formats]. `fourcc_codec_helpers.py` stays while
`camera_config.py` imports it. The tests of the deleted code go with it. The search of section 10
lists each file.

### 8.4 The state "ended with an error" (added on 2026-11-20)

The user decided: when a take ends by itself with an error, the state changes to "ended with an
error". The app state no longer says that a recording runs, the record button of the UI returns to
"Start", and the error and the summary of the take show at once, with no click on "Stop" ([ADR-H0BQ](../decisions/entries/H0BQ-user-rulings-of-the-spec-integration.md)).

Before 2026-11-21, `CameraGroup.to_state()` gave `recording_in_progress: self.take is not None or
self.ended_take is not None`: after a take that an error ended, the state still said that a recording
ran until the next stop request fetched the summary (8.2), and the summary reached a client only
through that stop request. The behaviour above is the ruling of the user. The two fields below are a proposed design
(item 16 of [ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md)). The new rule:

- `CameraGroupState` gets the field `take_state`: `"none"`, `"recording"` or `"ended_with_error"`.
  `recording_in_progress` is true only for `"recording"`.
- `"recording"` starts when the record start succeeds; until then a record start keeps
  `"ended_with_error"` [ADR-QJH6](../decisions/entries/QJH6-choices-of-the-fix-lane.md). A stop request that ends the take gives
  `"none"`. A take that the error of 5.3 or 5.4 ends gives `"ended_with_error"` as soon as
  `Take.finish` returns (8.1 step 5).
- A record start that fails changes nothing: `"ended_with_error"` and its summary stay. This applies
  to a refusal before `start_take` returns (HTTP 409 or 422) [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md), and to a failure after it
  (the take folder of the failed start is finished with zero rows, 10 item 13) [ADR-QJH6](../decisions/entries/QJH6-choices-of-the-fix-lane.md).
  Only a record start that succeeds drops the old summary.
- `CameraGroupState` gets the field `ended_take_summary`: `null`, or, while `take_state` is
  `"ended_with_error"`, the object `{"take_error": <the text of the error>, "camera_id": <the camera of
  the error, or null>, "summary": <the fields of the stop response of 8.2>}`. The name differs from
  the attribute `CameraGroup.ended_take` (a `TakeSummary`) on purpose.
- The live state (the `app_state` message of the websocket and `GET /camera/group/state`) carries
  both fields. The server sends the state each second when it changes, so a client sees the change
  within about 1 s.
- `"ended_with_error"` stays until the next record start (`"recording"`), the stop request that
  returns the summary (8.2; then `"none"`), or the close of the group. The stop request keeps the rule
  of 8.2 for a client with no websocket.
- The UI takes the error and the summary from the live state: [`camera-requests.md`](camera-requests.md)
  8.4.

## 9. When the app is killed during a take (before 5c)

| File | State after a kill |
|---|---|
| Each MKV | Unfinished: no index, the last open cluster can be cut [SFF-740]. Each block before the block that the muxer held is complete. |
| Each CSV | Unfinished: no footer. Each row points to a complete block (6.3). The last line can be torn on an OS crash [SFF-746]. |
| The manifest | `state` `"recording"` [SFF-724]. A `.tmp` file can stay after a kill during a whole-file write [SFF-790]. |
| The capture info | The version of the take start. |

Frames lost per camera: the items in the queue, plus the block that the muxer held. T-REC-KILL
measures it (section 11).

At its next start, the app does nothing with an unfinished take. It does not scan for unfinished
takes, it does not ask the question of SFF-793, and it changes no file. The manifest state
`recording` marks the take [SFF-724]. Step 5c adds the scan, the question and the repair [R1].

Added on 2026-11-20 (L of [ADR-JMS0](../decisions/entries/JMS0-review-decisions.md), [ADR-F8C0](../decisions/entries/F8C0-third-review-choices.md), [ADR-82AA](../decisions/entries/82AA-stop-last-frame-survivor-files-and-stuck-writer-limit.md)):

- An ordinary exit of the app (the shutdown endpoint, the end of the server, Ctrl-C) stops a running
  take through the take level (8.1) and closes the camera groups before it sets the kill flag. The
  manifest is then `finished`. The shutdown endpoint answers at once; the close runs after the
  answer. A camera process ignores Ctrl-C: the main process drives the exit. A stop or an exit gives
  up on a stuck writer after 15 s with no progress ([ADR-82AA](../decisions/entries/82AA-stop-last-frame-survivor-files-and-stuck-writer-limit.md) item 3).
  The exit of `skellycam/__main__.py` has no fixed wait before `WorkerRegistry.shutdown_all()`:
  `uvicorn.Server.serve()` returns only after its shutdown, and `shutdown_all()` sets the kill flag
  and waits for each worker itself [ADR-NYT6](../decisions/entries/NYT6-choices-of-fix-lane-2.md).
- The main process writes a heartbeat once a second from a thread of its own. A camera process that
  sees no heartbeat for 10 s (`HEARTBEAT_TIMEOUT_SECONDS`) takes the main process as dead: the camera
  processes notice a dead server after 10 seconds, not 300. They then finish their files and release
  the cameras (L). A lost heartbeat sets no global kill flag. Each such camera gets the state `dead`
  with the reason "lost the server's heartbeat". When the main process is in fact alive, it ends a
  running take with the `take_error` "camera `<id>` lost the server's heartbeat", and a later apply
  opens the camera again.
- With no take level, the first camera that ends sets the last frame of the take two group frames
  after the latest group frame, at least the first frame, under the lock of that value (the gate lets
  one camera be one frame ahead) ([ADR-82AA](../decisions/entries/82AA-stop-last-frame-survivor-files-and-stuck-writer-limit.md) item 1). Each camera then ends its writer with that frame count:
  its pair has placeholders to that frame (7.3), the `# end` line, and the same rows as each other
  pair. When no main process is alive, the manifest stays `recording` (step 5c).

## 10. Connection to the shared loop (after step 3a)

The module stays apart from the loop until step 3a of phase 3 is joined [R10]. Then one connection
commit, with the connection tests of 12.2, does these steps:

1. **Hand-over point.** In step 6 of [cap 5.1], the loop calls `give` with a `RecorderFrame` for each
   recorded frame, before the JPEG ring write [ring 5.3]. The fields come from `CapturedFrame` and
   from the capture check [cap 4.2, ring 5.2].
2. **The bytes.** `payload` is the object that the capture check gives to the ring: the camera's
   bytes, with the standard DHT when the check inserted it [M6, ring 5.2, ring 5.7].
3. **The layout.** The loop keeps the payload of its last good frame. When the take starts, the
   camera process parses its SOF (`parse_sof`) and gives the `layout` to the take level (6.4).
4. **The first frame.** The first frame of a take is one agreed group frame for every camera. The
   rule of today stays: `first_recording_frame_number` is the gate count plus 3
   (`CameraGroup.start_recording` in `camera_group.py`) [M7, review B4]. Row 0 of each camera is
   that group frame.
5. **Start and end.** The recording-info message to the camera processes carries the
   `CameraTakeSpec`. The camera process calls `start` when it gets it. After the last group frame of
   the take, it calls `end(frame_count)` with the frame count of 7.6. The finished message carries the
   `CameraTakeResult`.
6. **The interim decode goes** [D9]: the decode of [cap 5.5] for the old recorder, and the BGR
   conversion of [cap 13.2] for the old recorder. A camera with a BGR ring keeps one decode, in the
   decode stage on its own thread [ring 8.2 to 8.4]. Item 5 of [cap 17.2] then no longer applies.
7. **A dead camera.** U4 goes. During a take, a camera that becomes `dead` does not end its process
   [M1]. Its loop waits on the group frame counter of the orchestrator (the largest gate count of the
   cameras in the gate), with blocking sleeps of 1 ms or more [cap 4.3], and calls `give_missing`
   once for each new group frame up to the last frame of the take (7.3). Then it calls `end`, sends
   its result at once, closes the source with the bounded steps of [cap 6.9], reports and ends [D38]
   [agent 24]. Thus a slow close of the source does not delay the end of the take.
8. **U5 goes.** A damaged frame gives a placeholder on a `missing` row (7.2).
9. **U12 goes.** On a hang during a take, the camera process reports, then ends at once with
   `os._exit` (7.4).
10. **The stall watch.** For each source, the 2 s stall watch of [cap 9.5] counts from the later of
    the last arrival and the end of the last wait of the loop, in `give` or at the gate (5.2)
    [agent 32]. Changed on 2026-11-20: before, for a pull source only (E of [ADR-JMS0](../decisions/entries/JMS0-review-decisions.md)).
11. **The stall and the write error.** The loop catches `RecorderStalled` and `RecorderWriteError`,
    reports them, and from then on calls only `end` for that camera (4.3). The main process ends the take (5.3, 5.4) [C5]. The state transitions are those
    of 5.3 and 5.4 [C6]. Section 14 adds them to section 8 of `windows-capture.md`.
12. **The end of a take.** `CameraGroup.stop_recording` follows 8.1 and calls `Take.finish`. The stop
    endpoint builds `StopRecordingResponse` from `TakeSummary` (8.2). The old finaliser goes (8.3).
13. **The start of a take.** The start endpoint calls `start_take`. A `<rec>` that breaks SFF-715 gets
    HTTP 422. A take folder that holds files gets HTTP 409 [agent 16]. A request that names a
    microphone (`mic_device_index` 0 or more) gets HTTP 422 with the text "audio recording returns in
    step 5b; start again with no microphone" [C1]. Added on 2026-11-20: a take folder on a FAT disk
    gets HTTP 422 with the text of `start_take` (4.2), for example "The folder is on a FAT32 disk.
    FAT32 cannot hold a file larger than 4 GiB, and one camera reaches that in minutes. Choose a
    folder on another disk." [C6DE D3]. Added on 2026-11-20 (D of [ADR-JMS0](../decisions/entries/JMS0-review-decisions.md)): a record start that fails
    after `start_take` finishes the take folder at once with zero rows: each camera writer that started
    ends with frame count 0, and `finish` writes `take_error` "the record start failed: <text>". The
    manifest does not stay `recording`. A camera writer that cannot start keeps its camera running; the
    start then fails with HTTP 500 and the text "camera <camera_id>: the take writer did not start:
    <error>"
    ([ADR-P5VE](../decisions/entries/P5VE-review-fix-choices.md)). The failed start does not wait for the cameras to unpause. Before `finish`, it waits for
    each camera that has a writer or is in the gate: its result, or its refusal. A camera that gets its
    take spec when the take has ended or its start failed (first frame −1, or a last frame set)
    refuses it with the text "camera <camera_id>: the take ended before its writer started". Thus
    `finish` never completes the files of a live writer (8.1 step 4).
14. **Playback list.** `list_recordings` shows a folder whose `recording_manifest.json` has
    `"skellyfileformat": "recording_manifest"` with the mark "needs the new player" [C7]: the entry
    gets `needs_new_player: true`, `video_count` from the manifest `cameras`, and null statistics.
    Only the old video endpoints (the video list and the stream of today's player) give HTTP 409 with
    the same text for such a take. The mark never blocks opening: when the new player exists, the UI
    sends a new-format folder to it before any call to the old video endpoints [agent 33]. Old
    recordings do not change.
15. **Deletions** of 8.3, after a search for each caller.

The tests of `windows-capture.md` that change are in section 14.

## 11. The measurements of R11

Each runs on synthetic JPEG frames with no camera [R11]. The synthetic source is a thread that makes
frames on an absolute schedule and puts them in a waiting place, as the fake source of [cap 4.4]
does. The frames are JPEGs of a moving test pattern from `cv2.imencode` at quality 90: 1280x720
(about 60 kB) and 1920x1080 (about 200 kB), and for the small-frame cases 640x480 placeholders of
about 2.7 kB [agent 27]. Each benchmark writes a JSON summary to the path in `SKELLYCAM_BENCH_OUT`,
outside the repository. An evidence entry reports the summary with the tool versions (Python
3.13.18, PyAV 19.0.2) and the machine. The user gets the results before the two numbers are fixed
[R11].

| ID | Method | Recorded | Kind | Decides |
|---|---|---|---|---|
| T-REC-STALL | 1 and 4 camera processes, 720p30 and 1080p60. The MKV file object of one writer blocks one time for 0.5, 2, 10 and 15 s at frame 300. Each run is 60 s. Plan: "Once to a slow USB stick" — an optional run by the user on a USB stick, with no injected stall [P §7]. | Queue high-water (items, s); `give` waits (count, longest); frames replaced in the source; rows of each camera; capture lateness of the other camera processes (arrival against schedule, p50, p99, max). | Benchmark with pass parts: for 0.5 s and 2 s, no `give` wait and no lost frame; for 10 s, the queue fills, `give` waits about 7 s, no lost frame, equal rows; for 15 s, the take ends with `take_error` "disk stall", each file is finished, equal rows. | The queue size (`queue_seconds`) and the stall limit [R11]. |
| T-REC-KILL | 1 camera process, 720p30, and a 640x480 case where every second item is a placeholder. 20 kills during normal writing and 20 kills with a full queue (a blocked writer), at random frames; `TerminateProcess` on Windows, `SIGKILL` on Linux and macOS. | Frames given minus rows written, against the queue depth at the kill; torn bytes. | Process test with pass parts: each row has a correct CRC and its block bytes equal the frame given or the placeholder; blocks − rows is 0 or 1; each complete block parses. | The cost of a larger queue on a kill; it confirms the file-object writer with `cluster_size_limit=1` [agent 6]. |
| T-REC-FSYNC | 16 camera processes at 1080p60, fsync once per second on and off, 3 runs of 60 s each, and one run of 10 min with fsync on. | Per-frame write time (p50, p99, p99.9, max); fsync time (p50, max); queue high-water; capture lateness; CPU of each process. | Benchmark, no pass value. | Whether SFF-788 (once per second) stays; input for the queue size and the stall limit [R11]. |
| T-REC-GIL | 4 camera processes at 720p30 and 1 at 720p60, 10 min, writer on and off [P §7]. In each process: the source thread, the loop thread and the writer thread. | Arrival lateness against the schedule, interval jitter, loop step time (p50, p99, max), writer on against off. | Benchmark, no pass value. | Whether the writer thread delays capture [R11]. |

Note of 2026-11-20: the measurements ran (ADR-8RES). The user keeps the queue of 3 s and the stall
limit of 10 s as starting values [C6DE D2]. A slow disk (USB, spinning) is still to be measured on
the user's hardware (15.1).

The plan names T-REC-GIL with cameras [P §7]. R11 moves it to synthetic frames. The mix of 30 and
60 fps is allowed here, because these processes have no gate. In the app, D18 refuses that mix. The
plan test T-REC-MF-DEFER needs a camera. It is not in R11 and waits for the connection (section
15.1).

## 12. Tests

### 12.1 Kinds, markers, workflow and parity

- **unit**: in one process, with synthetic frames and the module only.
- **process**: spawns or kills processes, with the child script `child_writer.py` (section 3)
  [review]. Marker `recorder_slow` for a test that runs longer than 10 s [agent 27].
- **benchmark**: section 11. Marker `recorder_bench`. They run only with `SKELLYCAM_BENCH=1`, on the
  machines of the user, because the shared CI runners give no stable times [agent 27]. The pass parts
  of T-REC-STALL and T-REC-KILL also run in CI in a short form (5 kills, stalls of 0.5 and 15 s, with
  `queue_seconds` and the stall limit scaled down by 10).
  In the short form of T-REC-STALL, the check "no `give` wait" of the stall of 0.5 s is a `pace` test of
  [cap 16.1] (`test_t_rec_stall_short_has_no_give_wait`): a busy runner makes the writers of each camera
  fall behind the queue of 0.3 s. No lost frame, equal rows and finished files stay in the blocking test
  `test_t_rec_stall_short_pass_parts` [U Q905] [ADR-P3EZ](../decisions/entries/P3EZ-decision-of-the-user-on-the-give-wait-check-of-the-short-stall-test.md).
- **connection**: T-REC-40 to T-REC-49. They come with the connection commit and use the fake source
  of [cap 16.1].
- `test_a_slow_stop_ends_each_camera_at_the_last_frame` of
  `skellycam/tests/take_recorder/test_connection.py` (the stop of 8.1 step 1) runs on the real clock.
  A code step gives it the marker `capture_timing`, so that the macOS job runs it in its own step
  [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md).
  It blocks with no marker `pace` of [cap 16.1]: its row counts are the lock rule of 8.1 step 1, not the
  pace, and it accepts no warning other than `camera_gap`. A gap depends on the pace: a busy machine gives
  a gap in any row (a Windows run under load: rows 1, 7 and 26). So
  `test_a_slow_stop_has_a_gap_only_on_the_last_row` (marker `pace`) holds the rule that a `camera_gap` is
  only on the last row of a camera
  [ADR-HQE5](../decisions/entries/HQE5-choices-of-fix-lane-4.md).
- **Workflow** [C4] [agent 34]: a new `.github/workflows/recorder.yml`, on the pattern of
  `ring-arm64.yml` and of the capture workflow of [cap 15]: the same actions pinned by full SHA, uv
  `0.13.7`, Python `3.13.18`, `permissions: contents: read`, a concurrency group. Trigger: each push to
  `dom/recorder` that changes `skellycam/core/take_recorder/**`, `skellycam/tests/take_recorder/**`,
  `specs/recorder.md`, `pyproject.toml`, `uv.lock` or the workflow file; and by hand. Three blocking
  jobs: `recorder-windows` (`windows-2025`), `recorder-linux` (`ubuntu-24.04`, with PortAudio as the
  arm64 job installs it) and `recorder-macos` (`macos-15`). Each runs
  `uv run pytest skellycam/tests/take_recorder -m "not recorder_bench"`. The job `recorder-macos` runs
  only by hand (`if: github.event_name == 'workflow_dispatch'`), not on a push
  [ADR-N14T](../decisions/entries/N14T-decisions-of-the-user-on-the-ci-review-of-2026-11-25.md).
- **Where each test runs**:

  | Tests | Windows | Linux | macOS |
  |---|---|---|---|
  | unit and process tests, the short pass parts of T-REC-STALL and T-REC-KILL, T-REC-37 | `recorder.yml` | `recorder.yml` | `recorder.yml` (by hand) |
  | connection tests (after 3a) | `recorder.yml` | `recorder.yml` | `recorder.yml` (by hand) |
  | benchmarks | the user's machine | the user's machine, when available | the user's machine, when available |

  The capture spec runs its fake-source tests on Windows and Linux only [D47, cap 15]. The connection
  tests also run the shared loop on macOS. A failure there that comes from the shared loop, not from
  the recorder, goes to the user (section 15.2).
- The kill uses `TerminateProcess` on Windows and `SIGKILL` elsewhere; the lock uses `msvcrt` on
  Windows and `fcntl` elsewhere (6.8). No test is for one OS only.

### 12.2 Test list

Each test of the kinds unit and process uses at least two cameras unless it says one.

| ID | Kind | What it does | Pass criterion |
|---|---|---|---|
| T-REC-01 | unit | Start a take with two cameras, give 100 frames to each, end it. List the take folder. | Exactly the files and folders of 6.1 with their exact names. No MP4, no WAV, no `timestamps/` folder, no other CSV, no statistics file, no recording info JSON, no `synchronized_videos_README.md` [SFF-716, SFF-719, SFF-722, R5]. |
| T-REC-02 | unit | `start_take` with each bad `<rec>` of SFF-715 (empty, 129 bytes, `.`, each of `/ \ : * ? " < > \|`, a control character, a leading space, `CON`, `com1`, `LPT9`), a folder that holds a file, a rate of 1001/1, a rate of 0/1 and 2^20 + 1, `capture_format` H.264. | Each raises `ValueError`; no file or folder is created or changed [SFF-715, SFF-719, SFF-736, SFF-750, SFF-734]. |
| T-REC-03 | unit | Cameras with `camera_id` `0a1b` and `ff00`. | `camera_key` and `camera_label` follow 6.2; the label starts with `camera_id` and has the form of SFF-753; the file names use the label; the manifest `cameras` items are in order of `group_position` with the exact `video` and `timing` paths; `key_origin` is `"provisional"` [R8, C3, SFF-720, SFF-723, F-6]. |
| T-REC-04 | unit | Takes at 30/1, 30000/1001 and 60/1, 50 frames, with damaged frames 10 and 11. Walk the EBML elements of each MKV with the test's own parser. | DocType `matroska`; one track, `V_MJPEG`, number below 128; one `SimpleBlock` for each row, with the keyframe flag and no lacing; TimestampScale 1,000,000; the block of row k at ⌊(2k·den·1000 + num)/(2·num)⌋ ms, with no jump; `DefaultDuration` ⌊10^9·den/num⌋ (33,366,666 for 30000/1001); no `Projection`, no other rotation element, no other track [SFF-732, SFF-733, SFF-735, SFF-736, M1]. |
| T-REC-05 | unit | Give JPEGs with bytes after EOI, with APP0, APP1 (EXIF) and APP14 segments, and frames whose DHT the capture check inserted (`DHT_INSERTED`). | The payload of each block is byte-equal to the payload given (SHA-256 of each), also with the inserted DHT [SFF-734, SFF-737, M6]. |
| T-REC-06 | unit | Give 1,000 frames to a writer whose thread is held, then release it. Track the queue items and the allocations with `tracemalloc`. | Each queue item holds the same object as the frame given (`is`); no allocation of the payload size in `give` [ring 5.7, R10]. |
| T-REC-07 | unit | Read each CSV header of a take. | Each key of 6.5 in its order with its value; the take keys are equal in each CSV; `clock` is the value of the OS; `audio_count` 0; UTF-8, no byte order mark, LF; the column line of section 8 of the format [SFF-700, SFF-707, SFF-710, SFF-742, SFF-743, SFF-749, SFF-772, SFF-774]. |
| T-REC-08 | unit | Give frames with known arrival and sample times, frames with `NO_SAMPLE_NS`, and `give_missing` items. | `frame` is 0, 1, 2 …; the times are relative to `take_start_host_ns`; an empty `sample_ns` for `NO_SAMPLE_NS`; empty times and source number for `give_missing`; each integer in the form of SFF-701; no quote; each CRC is correct [SFF-701, SFF-704, SFF-741, SFF-744, SFF-754, SFF-755, M3]. |
| T-REC-09 | unit | `source_frame_number` sequences: +1, +3, equal, and frames with `DISCONTINUITY` and `DHT_INSERTED`. | `gap` and `repeat` as in 7.1; 0 in the first row; `filled` and `encode_skip` 0; the two ring flags change no flag [SFF-756]. |
| T-REC-10 | unit | During a take, after each `give`, read the CSV and the MKV that are on disk. After the end, read them again. Cases: 1280x720 frames; 320x240 frames of about 2 kB; 640x480 with placeholders. | Each complete row points at a byte range of the MKV that equals the frame given or the placeholder; the values do not change after the close; the last row also [SFF-757 (DT5), review B1, agent 7]. |
| T-REC-11 | unit | End a take with one gap, two damaged frames and a dead camera. | Each CSV ends with `# end rows= gaps= filled= missing= encode_skips=` in this order with the right counts; no `# fit` line; the manifest summary has the `missing` of each camera [SFF-745, SFF-758, F-1, R1, M3]. |
| T-REC-12 | unit | Give frames 0 to 99; frames 20 and 21 have `CAPTURE_ERROR`, frame 50 has `NO_SOI_EOI`; repeat with each bit of 0x0F. | Rows 20, 21 and 50 are `missing` rows with the frame's times and the byte fields of a placeholder block; 100 blocks; the damaged bytes are not in the MKV; `missing=3` [R3, M1, M3]. |
| T-REC-13 | unit | Spy on the writes of the CSV file object. | One `write` call for each row, with its LF; the file on disk holds only complete lines after each call [SFF-744, SFF-787]. |
| T-REC-14 | unit | Read the manifest after `start_take`, during the take and after the end. | The members of SFF-723 in order; `state` `recording`, then `finished`; `files` with the SHA-256 of the capture info; the summary nulls at the start and the values at the end; `camera_gap` for the camera with a gap; `privacy` of 6.6; the JSON form of SFF-702 [SFF-702, SFF-723, SFF-724, SFF-727, SFF-728, SFF-881, SFF-882]. |
| T-REC-15 | unit | Trace the file actions of `start_take` and `finish`. Put an unknown member and a freemocap `files` item in the manifest during the take. | Each whole-file write is `.tmp`, fsync, one rename, inside lock and unlock; the read comes after the lock; the unknown member and the freemocap item stay [SFF-724, SFF-726, SFF-786, SFF-789, SFF-801]. |
| T-REC-16 | process | A second process holds `.processing.lock` with the lock of 6.8 at the end of a take. Case 1: it releases after 2 s. Case 2: it holds 15 s. | Case 1: `finish` waits and then writes. Case 2: the manifest stays `recording`, an error is logged, and the stop response is given [SFF-789, F-7, review S7]. |
| T-REC-17 | unit | Read the capture info after the start and after the end. | The members of section 13 of the format in order and no other; keys in order of `group_position`; the values of 6.7; null for the 5d fields; no `rotation`; written at the start and the end [SFF-800, SFF-801, SFF-802, F-6]. |
| T-REC-18 | unit | Inject the two clocks of `start_take`. | The host clock is read first, the UTC clock at once after it, both before the first frame; `utc_offset_min` is the local offset [SFF-774]. |
| T-REC-19 | unit | Hold the writer thread. Give frames until the queue is full, then one more from a second thread. Release the writer. | The extra `give` waits; while it waits, the process uses under 2 % of one core; it returns when space comes; each frame is in the CSV; the counts of 5.2 are right [P §6, ring 8.10]. |
| T-REC-20 | unit | Queue sizes at 30/1, 30000/1001 and 60/1. | 90, 90 and 180 items (5.1) [agent 4]. |
| T-REC-21 | process | Camera A writes in a child process; its MKV file object blocks forever. The stall limit is scaled down. A second camera writes in the main process. | `give` of A raises `RecorderStalled` at the limit (±10 %); A gets no `give` after it; the take ends for both; B ends normally with placeholders to the frame count; A's process is ended no later than the time of its end message plus the limit plus the margin; A's result is `"disk stall"`; A's files are completed as a short file only after the join; the manifest has `take_error` "disk stall on camera <id>", `camera_dead` and `camera_file_short` [C5, C6, M5, review B2, review S8]. |
| T-REC-22 | unit | The MKV file object of one camera raises `OSError(ENOSPC)` at frame 50; the container close then raises. | No exception leaves the writer thread; the next `give` raises `RecorderWriteError`; `end` returns with the error and `files_closed`; the take level completes a short pair for that camera (rows to the frame count, MKV cut after its last block with a row, `missing` rows with no block, `# repair`, `# end`); the other camera is a normal finished pair; the manifest has `take_error` with the error text and `camera_file_short`, and no `camera_dead` [C5, C6, M5, review]. |
| T-REC-23 | unit | Camera B dies at row 300 of a take of 600 group frames: the test calls `give_missing` for rows 300 to 549, then `end(600)`. Case 2: rows 297 to 299 of B are damaged frames before the death. Case 3: B dies before its first frame. Case 4 (added on 2026-11-21): B dies before its first frame of a take of 10 group frames, and its layout (320x240) is not its mode size (640x480). | Case 4: `stored_px` of B is the mode size [SFF-728, [ADR-3B97](../decisions/entries/3B97-format-sync-to-the-format-commit-with-f1-to-f10.md)]. Cases 1 to 3: B's CSV has 600 rows; rows 300 to 599 are `missing` rows with empty times and placeholder byte fields; B's MKV has 600 blocks and a normal end; `missing=300`; `camera_dead` with `last_frame=299` (case 2: `last_frame=296`, `missing=303`; case 3: `last_frame=none`); the stop statistics leave out the `missing` rows [R2, M1, M3, M8, F-5]. |
| T-REC-24 | process | Camera B writes in a child process (`child_writer.py`). It ends with `os._exit` at 20 kill points: during a `mux`, between a `mux` and its row write, during a row write. The take ends 100 frames later. | `finish` runs only after the join; B's MKV is cut after its last block with a row; the CSV keeps each good row; `missing` rows with empty byte fields reach the frame count; `# repair` then `# end`; no fit line; each row's bytes equal the frame given; each kept block parses; `camera_dead` and `camera_file_short` [R4, M5, C2, SFF-794, SFF-795, F-2, F-4]. |
| T-REC-25 | unit | Mixes: all live; one dead at 10; one short at 20 and one dead at 30; all dead. | Equal rows in every case, equal to the frame count; equal blocks except the short file [R2, M1, M5, SFF-754]. |
| T-REC-26 | unit | Trace the end of a take. | The order of 8.1: each camera's `end`, then the completions, the CSV reads, the capture info, the manifest last [SFF-724]. |
| T-REC-27 | unit | CSVs with known arrival times, also `missing` rows, through `stop_stats`. | Each field of 8.2 equals the value computed by hand to 1e-9 [R5]. |
| T-REC-28 | unit | Display rotations 0, 90, 180, 270. | The header value; no rotation element; the bytes unrotated [SFF-735, SFF-751]. |
| T-REC-29 | unit | Inject the clock of the writer thread. | One fsync of the MKV and one of the CSV for each second with a row, on the writer thread only; one fsync of each at `end` [SFF-788, agent 9]. |
| T-REC-30 | process | A camera process is killed before its first block reaches the file. | The MKV holds only the header of 6.3 (the test's own EBML parser finds the EBML header, the Segment and the Tracks, and no Cluster); the CSV holds only `missing` rows with empty byte fields; `camera_file_short` with `blocks=0`; `stored_px` from the mode size [F-2, review S5]. |
| T-REC-31 | unit | Open each finished MKV of T-REC-12 and T-REC-23 with PyAV 19.0.2, with OpenCV 5.1.0 (`CAP_PROP_FRAME_COUNT`, 11 `POS_FRAMES` seeks, over and after the placeholders) and with `SequentialVideoReader`. | The counts equal the rows; each seek gives the expected row; placeholders decode to 0; `SequentialVideoReader` reads every frame [M `RS/mkv_black_placeholder/FINDINGS.md`, M10]. |
| T-REC-32 | unit | Call `give` and `give_missing` before `start` and after `end`; call `end` twice. | Each raises `RuntimeError` (4.3). |
| T-REC-33 | unit | Search the module for PyAV calls. | Only the calls of 6.3; no `add_stream_from_template`, no `add_stream(`; `add_mux_stream` with `rate`, `width` and `height` as keywords; the container options hold `flush_packets` `"1"` and `cluster_size_limit` `"1"`; `start_encoding` in `start` [M `RU/results/jpeg_passthrough/FINDINGS.md` §2.1, review B1, S5, S6]. |
| T-REC-34 | unit | Hand-built placeholders for 4:2:2, 4:2:0, 4:4:4, 4:4:0, 4:1:1 and grey, at 640x480, 1920x1080 and 1278x719; and a layout of 4 components. | The size, component count and H/V factors of each placeholder SOF equal the layout; each decodes to Y = 0 in PyAV and in OpenCV, with the same pixel format as an OpenCV JPEG of that layout; 1920x1080 4:2:2 is at most 16,353 bytes plus 1 %; the 4-component layout is refused by `start_take` [M2, agent 21, agent 22]. |
| T-REC-35 | unit | A take whose spec has a layout and whose frames 0 to 2 are damaged; a spec with `layout` `None` and damaged frames 0 to 2, then good frames; a spec with `layout` `None` and only damaged frames for longer than the queue size. | Case 1: rows 0 to 2 are on disk before frame 3 is given, with the spec's placeholder; case 2: rows 0 to 2 wait and get the layout of frame 3; case 3: after the queue size of rows, the held rows are written with a 4:2:2 placeholder of the mode size and one warning [M2, M7, agent 22]. |
| T-REC-36 | unit | A take at 1080p with frames of 600 kB at 60/1, 30 s, in one process. | No `give` wait on a free disk; every frame in the CSV (a sanity check, not a measurement). |
| T-REC-37 | unit | Run the conformance subset of 12.3. | Exactly the expected results of 12.3. |
| T-REC-STALL | benchmark | Section 11. | Section 11. The short form in CI (12.1): its check "no `give` wait" is a `pace` test [U Q905]. |
| T-REC-KILL | process | Section 11. | Section 11. |
| T-REC-FSYNC | benchmark | Section 11. | No pass value. |
| T-REC-GIL | benchmark | Section 11. | No pass value. |
| T-REC-40 | connection | Three fake cameras in the shared loop at 30 fps; the writer of one is held 2 s. | All three loops wait; after it, each camera's next row has `gap`; for each camera the sum of the gaps of `source_frame_number` equals the increase of `replaced_count` [D26, D27]; equal rows. |
| T-REC-41 | connection | Record with and without a BGR ring; count `cv2.imdecode` calls on the loop thread and on the decode thread. | No decode for the recorder; one decode per frame on the decode thread only when a BGR ring exists [D9, ring 8.2]. |
| T-REC-42 | connection | The fake delivers a cut-off JPEG during a take. | A placeholder on a `missing` row; the previous image is not stored again; no decode call [R3, M1]. |
| T-REC-43 | connection | Three fakes record; one gives device removed at frame 300. | That camera is `dead`; its process runs to the end of the take and writes placeholders; its MKV is closed normally; every CSV and MKV has the same rows and blocks; `camera_dead` in the manifest; no recording info JSON [R2, M1, D38]. |
| T-REC-44 | connection | A bounded call of one fake hangs during a take. | The failure is reported; the process ends within 1 s of the report; the take level completes its short file after the join; the others record to the stop [R4, M5]. |
| T-REC-45 | connection | Start and stop a take over HTTP with fake sources (not port 53117); then a start request with `mic_device_index` 0. | The stop response has each field of `StopRecordingResponse` with the values of 8.2 [R5]; the second start gets HTTP 422 with the text of section 10 item 13 [C1]. |
| T-REC-46 | connection | A fake sends a JPEG with no DHT. | The ring slot and the MKV block hold the same bytes, with the inserted DHT; the row has no flag for it [M6]. |
| T-REC-47 | connection | Two fakes start a take at gate count 100. | Row 0 of each camera is group frame 103 [review B4, M7]. |
| T-REC-48 | connection | Two OpenCV fakes record; the writer of one is held 3 s; then a fake writer is held past the stall limit and then released; then held for good. | Case 1: neither camera is marked `dead`, also the one that waited at the gate (5.2); case 2: the take ends with `take_error`, the camera stays `ready`; case 3: the camera is `failed`, stage `recording`, reason "disk stall", and "apply again" reopens it [agent 32, C5, C6]. |
| T-REC-50 | connection | Two fakes record; the writer of one is held past the stall limit; read the live state each 0.5 s, then send a stop request, then start and stop a new take. | `take_state` is `"recording"`, then `"ended_with_error"` within 1.5 s after `Take.finish` returns, with `recording_in_progress` false and `ended_take_summary` holding `take_error` "disk stall on camera <id>", the camera ID and the fields of 8.2; the stop request returns that summary and the state becomes `"none"` with `ended_take_summary` null; the new take gives `"recording"`, then `"none"` (8.4). |
| T-REC-51 | connection | A take ends with a write error; no stop request; then a record start. | `take_state` stays `"ended_with_error"` until the record start, which gives `"recording"` and `ended_take_summary` null; a stop request after that ends the new take normally; a record start that gets 409 before it, or that fails after `start_take` (HTTP 500), keeps `"ended_with_error"` and the summary (8.4). |
| T-REC-49 | connection | List the playback recordings with one old recording and one new take; ask for the videos of the new take. | Both are listed; the new take has `needs_new_player: true`; the old video list endpoint gives HTTP 409 with the mark text for it; no endpoint of the take folder itself is blocked [C7]. |

### 12.3 Conformance check against skellyfileformat

- skellyfileformat has runnable conformance tests in `tests/conformance/`. They reach a program
  through a test adapter. The Python adapter exposes `TakeWriter` with `write_frame`, `write_audio`,
  `add_warning` and `close`, `repair_take`, `release_check`, the reader `read_folder` and the detail
  functions (`spec/conformance.md`, "The test adapter"; `tests/conformance/INTERFACE_NOTES_capture.md`).
  The environment variable `SKELLYFILEFORMAT_ADAPTER` names the module.
- Step 5a adds `skellycam/tests/take_recorder/sff_adapter.py` [agent 28]. It exposes only
  `TakeWriter` on top of `start_take`, `CameraTakeWriter` and `finish`, in one process. It has no
  `write_audio` (5b), no `repair_take` (5c), no reader (phase 6) and no `release_check` (5b). It
  derives the `camera_id` of a camera dict from its `device.os_index`. Added on 2026-11-21 ([ADR-3B97](../decisions/entries/3B97-format-sync-to-the-format-commit-with-f1-to-f10.md)):
  `write_frame` passes each JPEG through the capture check `check_jpeg` of the program, which
  inserts the standard DHT [F-3, ring 5.2]; `data` None gives a frame with `CAPTURE_ERROR` (7.2);
  `camera_stopped(index, reason)` marks a dead camera for `finish` (7.3). The reader functions
  `camera_lost_at` and `short_file_counts` are not in the adapter: it has no reader.
- T-REC-37 checks out skellyfileformat at commit `24949df6c22093336c30b279c396ef593648de1e` next to
  the repository (`../skellyfileformat`) or in CI, and runs only the test functions that use the
  fixture `writer` and not `reader`. Before 2026-11-21, the commit was
  `d67679ada704caf55c64c2e279081d317205f354`; from 2026-11-21 to 2026-11-23, it was `c1028ef`.
- The expected results are written by hand here, each with its reason [review S9]. They are not taken
  from a run. A result that differs is a failure of T-REC-37:

  | Test function and case | Expected | Reason |
  |---|---|---|
  | `test_sft_705_names_and_layout[file_of_another_take]` | pass | |
  | `test_sft_711_camera_file[four_rotations]`, `[rate_30000_1001]`, `[rate_1001_1]` | pass | |
  | `test_sft_712_jpeg_bytes[mjpeg_source]`, `[h264_request]`, `[no_dht]` | pass | |
  | `test_sft_730_lock_form` | pass | |
  | `test_sft_771_missing_rows_and_placeholder` | pass | |
  | `test_sft_700_text_integers_json_ids_crcs` | fail | it records audio (5b) |
  | `test_sft_705_names_and_layout[plain]` | fail | it records audio (5b) |
  | `test_sft_705_names_and_layout[labels_of_7]`, `[labels_of_8]` | fail | remembered keys; 5a makes keys from `camera_id` [C3] (5d) |
  | `test_sft_705_names_and_layout[camera_key_0]` | fail | a conversion writer; skellycam's converter is phase 6 |
  | `test_sft_708_manifest` | fail | it records audio (5b); `add_warning` has no call in 5a |
  | `test_sft_711_camera_file[two_cameras]` | fail | it records audio (5b) |
  | `test_sft_712_jpeg_bytes[raw_source]` | fail | raw YUYV input; the recorder takes JPEG only (3b encodes in the loop) |
  | `test_sft_715_common_csv_rules[mono_as_g1]`, `[stereo_as_g2]` | fail | they record audio (5b) |
  | `test_sft_717_filled_bit_provisional` | skip | provisional in the format |
  | `test_sft_720_*`, `test_sft_721_*`, `test_sft_722_*` | fail | audio (5b) |
  | `test_sft_725_linux_macos_provisional` | skip | provisional in the format |
  | `test_sft_726_fit` | fail | audio and fit lines (5b) |
  | `test_sft_730_whole_files_and_live_files` | fail | audio (5b) and `repair_take` (5c) |
  | `test_sft_730_fsync_provisional` | skip | provisional in the format |
  | `test_sft_733_camera_file_provisional[*]` | skip | provisional in the format |
  | `test_sft_735_capture_info_json` | fail | audio (5b) |
  | `test_sft_766_writer_part` | fail | it records audio (5b) |

- When the pinned format commit changes, this table changes in the same commit as the new pin.
  The limit of a format commit that is only on the machine of the user ended on 2026-11-23 ([ADR-3B97](../decisions/entries/3B97-format-sync-to-the-format-commit-with-f1-to-f10.md)).

### 12.4 Decision to tests

| Decision | Tests |
|---|---|
| R1 | Section 2 (the order of the steps); T-REC-11 (no fit lines in 5a); T-REC-40 to T-REC-44 (U4, U5, U12 and the interim decode go) |
| R2 | T-REC-23, T-REC-25, T-REC-43 |
| R3 | T-REC-12, T-REC-42 |
| R4 | T-REC-24, T-REC-44 |
| R5 | T-REC-01, T-REC-27, T-REC-45 |
| R6, R7, R12 | No test: the proposals, the cited evidence, the order of the work. |
| R8 | T-REC-03, T-REC-17 |
| R9 | T-REC-49 |
| R10 | T-REC-06; each unit test runs with no camera; the connection tests come only with the connection |
| R11 | T-REC-STALL, T-REC-KILL, T-REC-FSYNC, T-REC-GIL |
| M1 | T-REC-04, T-REC-12, T-REC-23, T-REC-25, T-REC-42, T-REC-43 |
| M2 | T-REC-34, T-REC-35 |
| M3 | T-REC-08, T-REC-11, T-REC-12, T-REC-23 |
| M4 | T-REC-05, T-REC-12 (the two exceptions) |
| M5 | T-REC-21, T-REC-22 (the second case), T-REC-24, T-REC-25, T-REC-30, T-REC-44 |
| M6 | T-REC-05, T-REC-46 |
| M7 | T-REC-35, T-REC-47 |
| M8 | T-REC-23 |
| M9 | No test in 5a: the player (phase 6). |
| M10 | T-REC-31; the interface notes of 6.9 have no test |
| C1 | T-REC-45 |
| C2 | T-REC-24 |
| C3 | T-REC-03 |
| C4 | The workflow of 12.1 |
| C5 | T-REC-21, T-REC-22, T-REC-48 |
| C6 | T-REC-21, T-REC-22, T-REC-48 |
| C7 | T-REC-49 |
| 8.4 ([ADR-H0BQ](../decisions/entries/H0BQ-user-rulings-of-the-spec-integration.md)) | T-REC-50, T-REC-51 |

### 12.5 Format rules to tests

| Rules | Tests | Note |
|---|---|---|
| SFF-700, 701, 702, 703, 704 | T-REC-07, 08, 14 | |
| SFF-707, 710, 712 | T-REC-07, 14, 17 | |
| SFF-715, 716, 717, 719, 722 | T-REC-01, 02 | SFF-717: no rename call exists. |
| SFF-720, 752, 753 | T-REC-03 | 6.2 and F-6 until 5d [C3]. |
| SFF-723, 724, 726, 727, 728 | T-REC-14, 15, 23 | F-1 and F-5 add a summary member and codes. |
| SFF-732 to 737 | T-REC-04, 05, 28, 31, 33 | F-3 for SFF-734. |
| SFF-741 to 745, 749, 750, 751, 754 to 758 | T-REC-07 to 13, 23, 30 | F-1, F-2. SFF-757 is provisional (DT5). |
| SFF-772, 774 | T-REC-07, 18 | SFF-773 provisional. |
| SFF-786, 787, 788, 789 | T-REC-13, 15, 16, 29 | SFF-788 provisional; T-REC-FSYNC. F-7. |
| SFF-794, 795, 894 (the completion only) | T-REC-21, 22, 24 | F-4. |
| SFF-800, 801, 802 | T-REC-17 | SFF-802 partly until 5d. |
| SFF-881, 882 | T-REC-14 | |
| SFF-884 | No test: the module writes JSON and CSV only. | |
| SFF-760 to 771, 775 to 779 | None in 5a | Audio and fit: 5b [R1]. |
| SFF-793, 796 to 798 | None in 5a | Repair: 5c [R1]. |
| SFF-708, 709, 711, 713, 714, 718, 721, 729 to 731, 738 to 740, 746 to 748, 759, 780 to 785, 790 to 792, 799, 803, 864 to 893, 895 | None in 5a | Reader rules: phase 6. |
| SFF-725, 804 to 863 | None | freemocap, Blender addon, skellysync. |

### 12.6 Counts

| Kind | Tests |
|---|---|
| unit | 33 (T-REC-01 to T-REC-15, T-REC-17 to T-REC-20, T-REC-22, T-REC-23, T-REC-25 to T-REC-29, T-REC-31 to T-REC-37) |
| process | 5 (T-REC-16, T-REC-21, T-REC-24, T-REC-30, T-REC-KILL) |
| benchmark | 3 (T-REC-STALL, T-REC-FSYNC, T-REC-GIL) |
| connection | 12 (T-REC-40 to T-REC-51) |
| All | 53 |

The short pass parts of T-REC-STALL also run in CI (12.1). T-REC-38 and T-REC-39 are not used, so
that the connection tests keep their numbers.

## 13. Proposed format changes (one list for the recorder and the player)

Status of 2026-11-23: the format holds F-1 to F-10 since commit `c1028ef` of `../skellyfileformat`
(skellyfileformat ADR-6AT7). This spec cites commit `24949df6c22093336c30b279c396ef593648de1e`. The
user decided the ten changes [R6]. skellyfileformat ADR-5B03 and ADR-76NN (both accepted by the
user) give the details that the list did not fix. Before, this section
held the proposed rule text of each change. That text is in the git history of this file and in
skellyfileformat ADR-6AT7. Now the format text applies, and the names F-1 to F-10 stay as references
([ADR-3B97](../decisions/entries/3B97-format-sync-to-the-format-commit-with-f1-to-f10.md)).

| Change | Format requirements | Details |
|---|---|---|
| F-1: `missing` rows and the placeholder [M1, M2, M3] | SFF-728, SFF-729, SFF-745, SFF-754 to SFF-758, SFF-781, SFF-782, SFF-885, the columns of section 8 | `stored_px` is the size of the first stored JPEG that is not a placeholder, or the mode size (ADR-5B03 item 5; ADR-76NN item 12). A reader compares the summary `missing` with the `# end` line only when both hold it (ADR-76NN item 11). |
| F-2: the short file [M5] | SFF-740, SFF-754, SFF-757, SFF-759, SFF-795 | The term "rows with byte fields". A camera file with no block holds no Cluster (ADR-76NN item 9). A reader refuses a pair (`invalid`, `bad_metadata`) for a row with one empty byte field, for empty byte fields with no flag `missing`, and for a row with byte fields after a row with empty byte fields (ADR-76NN item 10). |
| F-3: two exceptions to unchanged camera bytes [M4, M6] | SFF-734 | The order of the four Annex K.3 tables is the choice of the writer (ADR-5B03 item 6). |
| F-4: the completion of a take by its own writer [R4, C2] | SFF-894, SFF-793 | Also after a failed write (ADR-5B03 item 3). The number of rows of the take (ADR-76NN item 10). |
| F-5: three warning codes [R2, M5, M8, C5] | SFF-727, SFF-895 | The codes are not warnings of the reader result: SFF-887 does not change (ADR-5B03 item 7). "camera lost at frame N", and the warning with no frame number when a `detail` does not parse, are display rules of a player. The take warnings of the skellycam player are the list of the player (`specs/player.md` 6.2, 7.3). |
| F-6: a provisional key [C3] | SFF-752, SFF-803, the `key_origin` of section 13 | The words "cannot read the values" and "not 0" (ADR-76NN item 5). |
| F-7: the lock on each OS | SFF-789 | |
| F-8: equal player times (from the player spec) | SFF-783 | |
| F-9: when a player checks the block count (from the player spec) | SFF-759 | |
| F-10: a `missing` row in a player [M9] (from the player spec) | SFF-783 | A take time in a `missing` row with no player time, and a camera with no earlier frame that is not `missing` (ADR-5B03 items 1 and 2). |

The earlier recorder P-2 (block times that count blocks) is withdrawn: with placeholders, rows and
blocks are equal, and SFF-736 already counts positions [review S13].

**Out of the list.** The player spec (section 14.2) names four cases that the format leaves open: a
missing column that a reader needs; a `frame` value that is not the position; a player time that
decreases; a camera file whose track is not `V_MJPEG`. They are not in F-1 to F-10. They stay open.

## 14. Edits needed in `specs/windows-capture.md`

Step 5a does not edit `windows-capture.md`. The connection commit of section 10 makes these edits,
through an accepted entry:

| Section | Sentence now | Replacement |
|---|---|---|
| 1.3 | "The recorder of phase 5. The old recorder (decoded image in, H.264 out) stays [D9]." | Delete. Add to 1.4: "The recorder: [`recorder.md`](recorder.md)." |
| 2.3 item 2 | "White balance and power line frequency are read and written to the recording info." | "… are read; step 5d writes them to the capture info." |
| 5.1 step 6 | "**Recorder.** If the frame is recorded, decode it (5.5) and give it to the old recorder [ring 5.3, D9]." | "**Recorder.** If the frame is recorded, give it to the recorder ([`recorder.md`](recorder.md) section 10) [ring 5.3]." |
| 5.4 | "The old frame record gets `arrival_ns` in both `pre_frame_grab_ns` and `post_frame_grab_ns`. Thus the midpoint that `create_camera_csvs.py` computes is the arrival time [agent 7]." | Delete. |
| 5.4 | "A timestamp column is written only when that stage was stamped [D41]. …" (the bullet to "…stamped.") | Delete: R5 removes the old CSV. |
| 5.4 | "The recorder refuses a frame whose camera ID does not match its config [D41]." | "Each camera process has its own camera writer. The connection refuses a take spec whose `camera_id` is not the camera of the process [D41]." |
| 5.4 | "The frame rate given to the old recorder is the mode rate, not the median of the frame intervals [agent 9]." | "The nominal rate of the recorder is the mode rate ([`recorder.md`](recorder.md) 6.5)." |
| 5.4 | "`sample_ns` goes into the slot header, and nothing uses it yet [D28]. Phase 5 decides." | "`sample_ns` goes into the slot header and into the CSV of the recorder [D28]." |
| 5.5 | The whole section. | "The decode of a JPEG runs only for a BGR ring, in the decode stage [ring 8.2 to 8.4]." Title: "Decode for the BGR ring". |
| 5.7 | The whole section (U4). | "A dead camera during a recording: [`recorder.md`](recorder.md) 7.3. Its process runs to the end of the recording and writes placeholders [M1]." |
| 6.6 | "On a hang during a recording, the camera process reports, then tries to finish the recording files of that camera for at most 5 s. Then it ends hard [U12]. The hung call is on a worker thread, so the loop thread can still close the files." and "This is an interim rule of phase 3. The recorder of phase 5 writes files that survive a hard stop. Then the rule goes [U12]." | "On a hang during a recording, the camera process reports, then ends at once. The main process completes its files after the process has ended ([`recorder.md`](recorder.md) 7.4) [R4, M5]." |
| 8.2, transitions table | (new rows) | "`recording` \| the take ends because of a disk stall or a write error of any camera, and this camera's writer finished \| `ready` [C5, C6]" and "`recording` \| this camera's writer is stuck past the limit of [`recorder.md`](recorder.md) 5.3 \| `failed`, stage `recording`, reason "disk stall"; the main process ends the process [C6]". |
| 8.2 | "The process of a dead camera reports, finishes its recording files [D38], closes the source with the bounded steps of 6.9 and ends. Thus a dead process lives until its files are finished and its close steps end. After a hang during a recording, the file finish has a limit of 5 s (U12), and then the process ends hard." | "The process of a camera that dies while no recording runs reports, closes the source with the bounded steps of 6.9 and ends. During a recording, it first writes placeholders to the end of the recording and ends its camera writer ([`recorder.md`](recorder.md) 7.3) [D38, M1]. After a hang, the process ends at once [R4]." |
| 8.1, `failed` row | "The start failed: …" | Add: "or the writer of the recorder stayed stuck past its limit (disk stall) [C6]." |
| 9.5 | (add) | "The watch restarts after each wait of the loop in the recorder ([`recorder.md`](recorder.md) 5.2)." |
| 11.3 | "The recording info records that the control was in auto for this take (11.6) [D37]." | "The capture info records it in `controls.<name>.auto` [D37]." |
| 11.5 | "White balance is read only. Its value and auto flag go to the recording info [D43]." and "Step 3c reads it and writes it to the recording info [D44]." | "… go to the capture info (step 5d) …" in both sentences. |
| 11.6 | The whole section. | "The capture data goes to the capture info JSON and the manifest ([`recorder.md`](recorder.md) 6.7)." |
| 12, stage table | (new row) | "`recording` \| the writer of the recorder stuck past its limit (disk stall) [C6]". |
| 13.2 | "The old recorder takes BGR in phase 3 (D9). … A frame is never converted two times [agent 36]." | "The recorder takes the encoded JPEG. A BGR conversion runs only for a BGR ring [ring 8.7]." |
| 13.3 | "The range goes into the recording info (11.6) [notes: Input range]." | "The camera process logs the range ([`recorder.md`](recorder.md) 6.7)." |
| 17.2 | Items 5 and 12. | Item 5: "Resolved by step 5a." Item 12: delete. |
| 16.2 | T-CAP-07, T-CAP-09, T-CAP-10, T-CAP-34, T-CAP-35, T-CAP-39, T-CAP-58, T-CAP-65, T-CAP-67, T-CAP-74, T-CAP-85 | T-CAP-07: the CSV time is the recorder CSV `arrival_ns`. T-CAP-09: replaced by T-REC-41. T-CAP-10: replaced by T-REC-42. T-CAP-34: "the capture info has `controls.exposure_us.auto` true". T-CAP-35: replaced by T-REC-43. T-CAP-39: drop the CSV column part; keep the refusal of a wrong camera ID. T-CAP-58: "the manifest has `camera_dead` for the C922, and its file has placeholders to the stop". T-CAP-65: "the log holds it". T-CAP-67: "the recorder gets the encoded JPEG". T-CAP-74: "both are in the capture info (step 5d)". T-CAP-85: replaced by T-REC-44. |

The decisions D9, D38, D41, U4, U5 and U12 keep their text in section 20 of `windows-capture.md`.
VPF8 and J3QP record that R1 to R5, M1 to M5 and C5, C6 replace their effect.

## 15. Measurements owed, open points, weak points, contradictions, review

### 15.1 Measurements owed

| ID | Measurement | When |
|---|---|---|
| T-REC-STALL, T-REC-KILL, T-REC-FSYNC, T-REC-GIL | Section 11 [R11] | Step 5a |
| T-REC-MF-DEFER | How Media Foundation behaves while the loop holds a frame for 0.5, 2 and 5 s [P §7]. With D26 the source keeps reading, so frames are replaced, not held back. A camera is needed. | After the connection |
| DT5 | The live byte offsets (T-REC-10) on each OS [SFF-757] | Step 5a |
| Slow disk | T-REC-STALL on a USB disk and on a spinning disk of the user, for the two starting values [C6DE D2] (added on 2026-11-20) | By the user |
| Real camera JPEGs | Placeholders next to real camera JPEGs (their own tables, restart markers, APP variants) in OpenCV and Blender; the evidence used synthetic frames only [`RS/mkv_black_placeholder/FINDINGS.md`, "Not tested"] | After the connection |
| Blender | The frame count of a 5a MKV with placeholders in Blender 5.2.3 (SFT-711 external) | By the user, one time |

### 15.2 Open points

1. The UI display of the queue event [P §6: "shown in the UI"]. Step 5a logs the counts. Who shows
   them in the UI, and in which phase, is open.
2. `capture_format` of the capture info for NV12 (3b): skellyspecs main adds `NV12` to SFF-800 (Q849). An NV12
   take records `"NV12"` (Q877 of [ADR-4TBY](../decisions/entries/4TBY-decisions-of-the-user-on-the-review-of-the-3b-code.md)).
3. The fsync of the folder after a rename on Linux and macOS. SFF-786 does not ask for it; a rename
   can be lost on a power loss without it.
4. The camera-side drop that only the flag `DISCONTINUITY` shows [D34] is not in the CSV (7.1). The
   fit of step 5b counts frames by `source_frame_number` [SFF-777]. A frame that the camera dropped
   then shifts the fit by one period. Step 5b decides.
5. The format changes F-1 to F-10 are in the format since commit `c1028ef` (section 13). The user
   accepted the details of skellyfileformat ADR-76NN ([ADR-3B97](../decisions/entries/3B97-format-sync-to-the-format-commit-with-f1-to-f10.md)).
6. The connection tests run the shared loop on macOS, where the capture spec runs no fake-source
   test [D47]. A macOS failure of the shared loop itself goes to the user.

### 15.3 Weak points

- The offset method of 6.3 rests on one behaviour of the FFmpeg Matroska muxer (it gives block k to
  the file at block k+1, with `cluster_size_limit=1` also for small blocks). T-REC-10 checks it.
- The file-object writer (agent 6) differs from the path-based writer of each kill test of the
  research. T-REC-KILL must confirm the loss of one frame per kill.
- With the OpenCV source, a full queue drops frames in the driver, and `source_frame_number` shows
  no gap [cap 4.2]. Only `arrival_ns` shows the pause. This lasts until native capture on Linux and
  macOS (phase 7).
- While `give` waits, the camera writes no ring slot. The preview of the group stops for that time.
- A camera that gave no good frame before the take holds its first rows in memory (6.4). A kill in
  that time loses them. In the app this does not occur: each camera is `ready` before a take.
- The placeholder encoder is new code. T-REC-34 checks it in two decoders; Blender is checked by the
  user (15.1).
- One hour of placeholders at 1080p 4:2:2 and 30 fps is 1.8 GB [M2].
- The 3 s queue and the 10 s stall limit are starting values that the user chose after section 11
  [R11, C6DE D2]. The data supports 3 s on one NVMe drive only. Nothing measured chooses 10 s.
- The research numbers come from one machine with one NVMe drive [M `RU/results/EVIDENCE_INDEX.md`
  §1].

### 15.4 Contradictions found

1. **R2, R3 and R4 against SFF-754, SFF-759 and SFF-740.** The format counts rows as blocks and has
   no rule for a dead camera. M1 to M3 solve it with placeholders (F-1). The short file of M5 stays an
   exception (F-2).
2. **R3 against SFF-756 and SFF-758.** R3 calls the row a "gap row" and its count "the count of
   gaps". In the format, `gap` is a jump of `source_frame_number`. M3 adds the flag `missing` and the
   count `missing=` (F-1).
3. **R4 against SFF-793.** No program changes a file of the take before the user agrees. C2 allows
   the completion by the writer of the take (F-4).
4. **R8 against SFF-720, SFF-752, SFF-753 and SFF-803.** C3 decides the key; F-6 adds the value
   `provisional`.
5. **R1 against SFF-775 and SFF-795.** The fit lines are a MUST at a normal end and in a repair; R1
   puts the fit in 5b. A finished 5a sidecar and a completed sidecar (7.4) have no fit line until 5b
   [review S11].
6. **R5 with R1.** No WAV from 5a and no Opus until 5b. C1 refuses a start with a microphone.
7. **[P §6] against D38 and R2.** "One camera fails mid-take: the whole take stops" [P §6]; D38 and
   R2 keep the other cameras. R2 replaces the plan sentence.
8. **D38 against R2.** D38 says "frame counts are then unequal across cameras". R2 and M1 make the
   row and block counts equal.
9. **SFF-734 against [ring 5.2] step 6 and M1.** The format stores the camera bytes unchanged. M4 and
   M6 make two exceptions (F-3).
10. **SFF-757 (live offsets) against the evidence.** The muxer holds the last block, and with small
    JPEGs more than one [M `RU/results/write_throughput/FINDINGS.md` §2.3, review B1]. Rows are
    written one block late, and `cluster_size_limit=1` is needed (6.3).
11. **SFF-788 against the evidence.** A path-based PyAV MKV cannot be forced to disk
    [`RU/results/crash_resilience/FINDINGS.md` §4 item 10]. Agent 6 uses a file object; the kill
    evidence used a path.
12. **[P §6] "frame requests are held back" against D26.** With a push source, the source keeps
    reading and the waiting place replaces frames [cap 4.3, 6.5].
13. **[P §7] T-REC-GIL (cameras at 30 and 60 fps together) against D18.** Allowed only on synthetic
    frames with no gate (section 11).
14. **[cap 11.6] against SFF-800.** `input_range` has no place in the capture info (6.7) [agent 23].
15. **SFF-727 against R2 and M5.** The list of skellycam codes is closed. F-5 adds three.
16. **SFF-789 on Linux and macOS.** "The file lock of the operating system" is two different locks
    there (F-7).
17. **[cap 8.2] against M1.** The capture spec ends the process of a dead camera after its files are
    finished. M1 keeps it until the take ends, writing placeholders (section 14).
18. **[cap 9.5] with a long `give` wait.** The 2 s stall watch of the OpenCV pull source would mark a
    healthy camera `dead` (5.2) [agent 32].
19. **M5 ("one case stays short") against a write error.** After a write error, nothing can write
    that MKV either. The user decided on 2026-11-20 that a write error is the second short-file case
    [M5].
20. **[ring 5.1] `frame_number` against [cap 5.3].** Already in [cap 17.2] item 2. The recorder does
    not write `frame_number`, so it does not matter here.

### 15.5 Faults of the independent review

Each fault was checked. Faults B1, S5 and S6 were measured again with a synthetic script (PyAV
19.0.2, OpenCV 5.1.0, Windows) and gave the same results.

| Fault | Change |
|---|---|
| B1 small JPEGs held by the muxer | Accepted. `cluster_size_limit=1` (6.3); small frames in T-REC-10 and T-REC-KILL; T-REC-33. |
| B2 completion before the join | Accepted. 4.2, 7.4, 8.1 step 4. |
| B3 the stall limit | Replaced by C5 and C6 (5.3); transitions in section 14. |
| B4 the first frame of a take | Accepted. Section 10 item 4; T-REC-47. |
| S5 a camera file with no block | Accepted. `start_encoding()` in `start`; T-REC-30 rewritten; rule in F-2. |
| S6 the positional form | Accepted. The old T-REC-34 and its note are gone; keywords in 6.3. Its number now holds the placeholder test. |
| S7 lock timeout at the start | Accepted. The case is dropped (6.8, T-REC-16). |
| S8 T-REC-21 | Accepted. A process test with C6. |
| S9 conformance list | Accepted. A hand-written table (12.3). |
| S10 `missing=` place and columns | Accepted. F-1, 6.5. |
| S11 no fit lines in a completion | Accepted. 7.4, F-4, contradiction 5. |
| S12 parity and the workflow | Accepted. 12.1 with `recorder.yml` [C4]. |
| S13 withdraw P-2 | Accepted. Section 13. |
| `close()` after ENOSPC | Accepted. 5.4; T-REC-22. |
| opencv dependency | Accepted. Section 3. |
| SFF-753 twice in 12.5 | Accepted. Removed from the reader row. |
| "during the take" against `finish` | Accepted. 7.4 says "at the end of the same take". |
| T-REC-24 needs a child script | Accepted. `child_writer.py` (section 3). |
| P-6 and `LockFile` | Accepted. F-7. |
| Status member and `ValueError` (old choices 31 and 33) | Accepted. Both dropped. |
| The 2 s stall watch of the OpenCV source | Accepted: the fault is real (contradiction 18). 5.2, section 10 item 10, T-REC-48. |

No fault is rejected.

## 16. Choices of the agent

Each item fills a gap that the decisions, the format, the plan and the two accepted specs do not
fix. The body marks each one [agent n]. Items of the first draft that are now decisions of the user
(C3, M6, C5 to C7) or that the review dropped have new content or are marked "(now …)".

1. The package `skellycam/core/take_recorder/` and its file names; the tests in
   `skellycam/tests/take_recorder/`.
2. Two levels: the take level in the main process, the camera level in each camera process.
3. `give` waits while the queue is full, with the frame held by the loop thread; the stall limit
   counts the wait of one `give` call.
4. The queue size ⌈`queue_seconds` × rate⌉ items.
5. The writer thread is a non-daemon thread named `take-writer-<camera_id>`; the end marker holds the
   frame count.
6. The MKV through a Python file object (`open(path, "xb", buffering=0)`), not a path.
7. Row k is written after block k is in the file; `byte_offset` from `tell()`; the last block found
   by a read after the close.
8. The CSV unbuffered, one `write` per line.
9. The fsync of both live files once per second, on the writer thread, after a row.
10. (now C3)
11. The camera writer pads with placeholders and writes its own `# end` line; the frame count is
    `last − first` of the orchestrator (A of [ADR-JMS0](../decisions/entries/JMS0-review-decisions.md), 2026-11-20); a
    row count that differs is a defect.
12. The completion of 7.4: after the join, cut both files to equal rows and blocks, `missing` rows
    with no block, `# repair`, `# end`.
13. `last_frame` is the position of the last row that is not `missing`.
14. The definitions of the stop response fields (8.2); `missing` rows left out;
    `total_duration_sec` is the summary `duration_s`.
15. The lock calls (`msvcrt.locking`, `fcntl.flock`), retries every 50 ms up to 10 s, and what a
    timeout at the end does.
16. The take folder must not exist or must be empty; HTTP 422 for a bad `<rec>`, 409 for a folder
    with files.
17. `purpose` is always `motion_capture` in 5a.
18. `clock_hz` is empty.
19. `group_position` is the order of the cameras in the take: the order of the `camera_index` of the
    apply request, which is the camera number of the camera list of the UI
    ([`camera-requests.md`](camera-requests.md) 8.1; changed on 2026-11-20, H6 of
    [ADR-6QFG](../decisions/entries/6QFG-pause-in-the-ui-search-on-native-sources-and-restore-at-close.md)).
20. The nominal rate: `fps_num/fps_den` from Media Foundation; for OpenCV, a float rate within 0.01
    of 30000/1001 or 60000/1001 gives that fraction, and each other rate gives its value in
    thousandths, reduced.
21. The placeholder is built by hand: one DQT of 1s, a DC table of two codes, an AC table of one code
    (2 bits per block); the SOF compare uses size, component count and H/V factors only.
22. The `layout` of the take spec from the SOF of the camera's last good frame before the take; with
    no layout, the rows wait for the first good frame, at most the queue size, then a 4:2:2
    placeholder of the mode size; a layout that cannot be built is refused at the start.
23. The capture info values of 6.7, the `device.backend` names, and `input_range` in the log only.
24. `give_missing` for a dead camera, and `end(frame_count)` pads the rest; the dead camera's loop
    follows the group frame counter with sleeps of 1 ms or more.
25. The end wait: the time told to end plus the stall limit plus 5 s; `terminate` then `join`; the
    stage name `recording` for the state `failed` of C6.
26. The track size is the size of the opened mode; `stored_px` comes from the SOF of the first block
    that is not a placeholder.
27. The test markers `recorder_slow` and `recorder_bench`, `SKELLYCAM_BENCH`, `SKELLYCAM_BENCH_OUT`,
    the synthetic JPEG sizes and the short CI form of the benchmark pass parts.
28. The conformance adapter `sff_adapter.py` with `TakeWriter` only, `camera_id` from
    `device.os_index`, and the commit pin.
29. `exposure_us` = 2^v × 10^6 from the log2 exposure value.
30. The ring flags `DISCONTINUITY` and `DHT_INSERTED` do not go into the CSV in 5a.
31. (now M5, second case: the user decided it on 2026-11-20)
32. (now E of [ADR-JMS0](../decisions/entries/JMS0-review-decisions.md), for each source) The stall watch of a pull source counts from the
    later of the last arrival and the end of the last wait of its loop (in `give` or at the gate).
33. The playback list field `needs_new_player` and HTTP 409 on the video endpoints of a new take.
34. The workflow `recorder.yml`: its trigger paths, the runner labels `windows-2025`, `ubuntu-24.04`
    and `macos-15`, and its test selection.

## 17. Questions for the user

Each question is worded so that "yes" accepts the recommended answer. The questions Q1 to Q3 of the
first draft are answered: C1 (microphone), M1 (the placeholder makes the old Q2 moot) and C4 (CI).

No question is open. The user answered Q1 of the second draft on 2026-11-20: a write error on one
file is the second short-file case [M5].

## 18. Decisions of the user

The user decided R1 to R12 on 2026-11-19, in the grilling of Q205 to Q216
([ADR-VPF8](../decisions/entries/VPF8-phase-5-recorder-decisions.md)), and M1 to M10 and C1 to C7
later the same day
([ADR-J3QP](../decisions/entries/J3QP-missing-frames-as-black-placeholders-and-the-end-of-a-take.md)).
They are binding. M1 to M5 replace the "row with no image" reading of R2, R3 and R4.

- R1 (Q205): Phase 5 has four steps, in this order, each with tests first: 5a the video writer, the
  timing CSV, the manifest and the end of a take (it replaces the old recorder, and removes the
  interim decode and the three interim rules U4, U5, U12 of `specs/windows-capture.md`); 5d camera
  identity from the operating system and the full capture info; 5b audio in Opus and the timestamp
  fit that keeps audio and video in step; 5c repair of a take after a crash.
- R2 (Q206): A camera dies during a take (D38 of the capture spec: the other cameras keep
  recording). In the new format every camera's CSV keeps the same number of rows: the dead camera
  gets a "gap" row for each remaining frame of the take. The manifest names the dead camera and its
  last real frame. This is what the user meant by "must change back" for U4: the files have equal
  lengths again. It replaces the plan's sentence "one camera fails mid-take: the whole take stops".
- R3 (Q207): A damaged frame (a frame with an error flag) during a take gets a gap row and no image
  is stored. The last good image is NOT repeated (this removes U5). The damaged bytes are not kept.
  The count of gaps is in the CSV's end line.
- R4 (Q208): A hung camera call during a take: the camera process ends at once after its report,
  with no attempt to finish the files (this removes U12). The main process completes that camera's
  files. The camera then gets gap rows to the end of the take, as R2. Because repair (5c) is the last
  step, step 5a holds the small part it needs: finish one camera's files with gap rows and the
  closing lines.
- R5 (Q209): The old output files are no longer written: the H.264 MP4, the 28-column timestamp
  CSVs, the combined (multi-frame) CSV, the statistics files, the WAV. The stop response of the HTTP
  API keeps the same fields, computed from the new CSVs.
- R6 (Q210): This session may propose changes to the skellyfileformat repository where the recorder
  needs them, as local commits there, pushed only on the user's word. The first one is the rule for a
  dead camera's rows (R2), which the draft does not have (its SFF-754 requires equal rows per camera
  and has no rule for a dead camera).
- R7 (Q211): The old recording upgrade study is closed. Its evidence stays and is cited.
- R8 (Q212): Before step 5d, each camera's files are named from today's `camera_id`, and the capture
  info marks that as provisional. Step 5d switches the label to the identity from the operating
  system, as the format specifies. A reader finds the files through the manifest, not by guessing
  names.
- R9 (Q213): The app's own player cannot show new takes until the canvas player of phase 6 exists;
  the user accepts that gap, on the condition that the player is designed and built as its own
  parallel line so the gap is short.
- R10 (Q214): Step 5a is built as a self-contained module with its own tests, in its own worktree
  and branch (`dom/recorder`, off `dom/native-jpeg`), fed by synthetic JPEG frames. It is connected
  to the camera loop only after step 3a of phase 3 is joined. The writer's input is what the ring
  spec fixed: a JPEG payload, frame_number, arrival_ns, sample_ns, source_frame_number, flags,
  delivered length, rotation.
- R11 (Q215): The measurements that the plan still owes run in step 5a, on synthetic frames with no
  camera: a writer stalled by a slow disk (T-REC-STALL), a process killed while its queue is full,
  the cost of forcing data to disk once per second with 16 writers (SFF-788), and whether the writer
  thread delays capture (T-REC-GIL). They decide two numbers that are starting values today: the
  queue of about 3 s and the stall limit of 10 s. The results go to the user before those numbers
  are fixed.
- R12 (Q216): The spec of step 5a and its test list are written first, reviewed, and accepted by the
  user before any code.
- M1: A missing frame is stored as a black placeholder JPEG block on its row. Cases: a damaged frame,
  and a dead camera whose process still runs (the writer keeps writing placeholders to the end of the
  take). Every camera file then has exactly one block for each group frame, constant block times (no
  time jump), and equal block counts across cameras.
- M2: The placeholder has the same width, height and chroma layout (sampling factors) as that
  camera's own frames, taken from the SOF segment of that camera's first frame. It is made once for
  each camera file, with optimised Huffman tables (measured: 16.5 kB at 1080p 4:2:2, 1.8 GB for one
  hour at 30 fps). A different layout breaks Blender; a different size breaks every tool when it is
  the first block.
- M3: The row of a placeholder has the flag `missing` (one new flag bit; the word "gap" keeps its
  format meaning of a jump in the source frame number). The end line of the timing file gets a
  `missing=` count (placed where SFF-745 allows a new key). The manifest says how many rows of each
  camera are placeholders. The row's byte offset and size point at the placeholder block. Which other
  row fields are empty (times, source frame number) is as recorder P-1 said: kept for a damaged frame
  that had them, empty for a dead camera. A row with no time has no player time.
- M4: The format rule "the stored bytes are the camera's bytes" gets two stated exceptions: the
  placeholder on a `missing` row (M1), and the inserted DHT table (M6).
- M5: One case stays short: when a camera process is killed or hangs, nothing can write its video
  file. That file ends early. The main process completes its files (timing rows with `missing`, no
  block) only after the process has ended, and the manifest says that the video file is shorter than
  the row count. Crash repair in step 5c may fill it later. This is the one exception to "one block
  for each row", and readers get the rule: a `missing` row whose byte fields are empty has no block.
  Second case (2026-11-20, answer to Q1): a write error on one file gives that camera a short pair
  (rows to the frame count, the MKV cut after its last block with a row, `missing` rows with no
  block, `# repair`, `# end`), with `camera_file_short` and `take_error` and no `camera_dead`; the
  camera stays `ready`; the other cameras get normal finished pairs. A full disk leaves the take
  unfinished (`state` `recording`).
- M6: The recorder stores the JPEG bytes with the DHT table that the ring inserted when the camera
  sent none (the ring flag DHT_INSERTED says which frames). The format rule changes to allow this one
  insertion.
- M7: A take starts at the first group frame; the first block of a file is never smaller than the
  camera's frames (M2 guarantees it).
- M8: A dead camera is also recorded in the manifest: warning `camera_dead` with `last_frame`. In the
  player, "camera lost at frame N": N is the first group frame with no image from that camera.
- M9: The player never shows the black placeholder as a picture. It shows the last real image with
  the "no frame" mark, from the `missing` flag. Other programs that ignore the flag see black.
- M10: skellycam's shared reader (`SequentialVideoReader`) needs no change for M1 (tested: 300 of
  300 frames). The interface notes for freemocap and skellytracker say: a placeholder row is black
  and is flagged `missing` in the timing file; "image i is group frame i" stays true, except for a
  file of a killed camera process (M5), which is shorter.
- C1: A record start that names a microphone is refused with HTTP 422 until step 5b.
- C2: The program that records a take may complete that take's files without asking, and marks a
  completed file as `repaired` (new format rule; no fit lines until 5b).
- C3: Until 5d: camera key = `camera_id` + 12 hex characters of its SHA-256, marked `"provisional"`.
- C4: CI runs the 5a tests on Windows, Linux and macOS on each push to the recorder branch.
- C5: A disk stall or a write error on one camera's file ends the take for all cameras, with a clear
  error.
- C6: Only a camera whose writer is stuck past the limit has its process ended. It then has the
  state `failed` with the reason "disk stall"; the user uses "apply again" or unselects it. A plain
  write error returns normally and the camera stays `ready`. The time limit counts from the moment
  that camera was told to end, plus a margin.
- C7: Today's playback list shows new-format takes with a mark "needs the new player"; they are not
  playable there and not hidden.

Added on 2026-11-20, after the code review
([ADR-C6DE](../decisions/entries/C6DE-stall-as-no-progress-limits-and-no-fat-disk.md)):

- C6DE D1: a stall is no progress of the writer for the stall limit, not a total time. At the end of
  a take, a camera whose writer still writes, however slowly, is left to finish. Only a writer with
  no progress for the stall limit is a disk stall (C6). The same rule applies to `give` during the
  take. The margin of the main process stays.
- C6DE D2: the queue of 3 s and the stall limit of 10 s stay as starting values.
- C6DE D3: a take is refused at its start when the file system of the take folder has a file size
  limit of 4 GiB (FAT). exFAT is accepted. When the file system cannot be found, the take starts and a
  warning is logged.

Decided before these (cited, not repeated): the format (skellyfileformat SPEC, draft v2: one MKV per
camera with `V_MJPEG`, camera bytes unchanged; one CSV per camera with a CRC and a flush for each
row; the manifest; the capture info; the folder layout); the writer design (one writer thread per
camera process, a bounded queue of about 3 s; a full queue slows capture and never drops a frame; a
stall over the limit ends the take with an error; a write error finishes the sidecars and the
manifest for the frames written); PyAV 19.0.2 for the MKV; recorder first, ring write after
([ring 5.3]); read old formats, never write them; Opus in fragmented MP4 for audio (step 5b).
